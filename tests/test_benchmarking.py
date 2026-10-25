from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from factcheck.benchmarking import audio_identity, compare, preflight, run_trial, summarize
from factcheck.streaming import MODEL_FILES, MODEL_NAME
from tests.test_replay import wav_file
from tests.test_session import FakeStreamingEngine


class BenchmarkTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.path = self.root / "input.wav"
        self.pcm = wav_file(self.path, frames=4000)
        self.output = self.root / "report.json"

    def tearDown(self):
        self.directory.cleanup()

    def models(self):
        for name, files in ((MODEL_NAME, MODEL_FILES), ("small", ("model.bin", "config.json", "tokenizer.json"))):
            folder = self.root / "models" / name
            folder.mkdir(parents=True)
            for name in files:
                (folder / name).write_bytes(b"fixture-model")

    def fixture(self, events, complete=True):
        folder = self.root / "session"
        folder.mkdir(exist_ok=True)
        wav_file(folder / "audio.wav", frames=4000)
        metadata = {"status": "completed", "transcription_complete": complete, "transcription_engine": "sherpa-onnx", "issues": []}
        (folder / "session.json").write_text(json.dumps(metadata), encoding="utf8")
        (folder / "events.jsonl").write_text("\n".join(json.dumps(row) for row in events), encoding="utf8")
        (folder / "transcript.jsonl").write_text('{"start":0,"end":0.4,"text":"Ensaio fictício"}', encoding="utf8")
        return folder

    def test_summary_separates_inference_pipeline_flush_setup_and_drain(self):
        events = [{"kind": "capture_finished", "elapsed_seconds": .5}, {"kind": "first_partial", "elapsed_seconds": .2},
                  {"kind": "transcript_delivered", "elapsed_seconds": .8, "delivery_lag_seconds": .4},
                  {"kind": "transcription_chunk", "processing_seconds": .7, "inference_seconds": .1, "queued_chunks": 3, "delivery_lag_seconds": .3},
                  {"kind": "transcription_flush", "processing_seconds": .05}]
        result = summarize(self.fixture(events), 2, .5, audio_identity(self.path))
        self.assertAlmostEqual(result["timing_seconds"]["inference_including_flush"], .15)
        self.assertAlmostEqual(result["inference_to_audio_ratio"], .3)
        self.assertEqual(result["timing_seconds"]["chunk_pipeline"]["median"], .7)
        self.assertEqual(result["timing_seconds"]["drain_after_capture"], 1)
        self.assertEqual(result["timing_seconds"]["first_stabilized"], .8)
        self.assertEqual(result["maximum_logged_queue"], 3)
        self.assertIsNone(result["quality"]["word_error_rate"])
        self.assertFalse(result["quality"]["approved_for_live_use"])
        self.assertTrue(result["pcm_matches_input"])

    def test_missing_old_measurements_remain_unknown_instead_of_zero_or_success(self):
        result = summarize(self.fixture([{"kind": "transcription_chunk", "processing_seconds": .4}]), 1, None, audio_identity(self.path))
        self.assertIsNone(result["inference_to_audio_ratio"])
        self.assertIsNone(result["timing_seconds"]["capture"])
        self.assertIsNone(result["timing_seconds"]["drain_after_capture"])
        self.assertIsNone(result["timing_seconds"]["first_partial"])

    def test_identity_detects_pcm_changes_and_rejects_truncated_source(self):
        original = audio_identity(self.path)
        self.assertEqual(original["pcm_sha256"], sha256(self.pcm).hexdigest())
        data = bytearray(self.path.read_bytes())
        data[-1] ^= 1
        self.path.write_bytes(data)
        self.assertNotEqual(audio_identity(self.path)["pcm_sha256"], original["pcm_sha256"])
        self.path.write_bytes(data[:-10])
        with self.assertRaises(ValueError):
            audio_identity(self.path)

    def test_preflight_blocks_missing_models_before_session_output_or_download(self):
        with self.assertRaisesRegex(ValueError, "não baixa"):
            compare(self.path, self.root, self.output)
        self.assertFalse(self.output.exists())
        self.assertFalse((self.root / "recordings").exists())
        self.models()
        preflight(self.root, ("streaming", "whisper"), "small")

    def test_real_replay_pipeline_preserves_pcm_and_keeps_human_review_pending(self):
        with patch("factcheck.session.StreamingTranscriber", return_value=FakeStreamingEngine()):
            result = run_trial(self.root, self.path, "streaming", "small")
        self.assertTrue(result["transcription_complete"])
        self.assertTrue(result["source_unchanged"])
        self.assertTrue(result["pcm_matches_input"])
        self.assertEqual(result["stable_segments"][0]["review_status"], "automatico_nao_revisado")
        self.assertIsNotNone(result["timing_seconds"]["capture"])
        self.assertIsNotNone(result["timing_seconds"]["inference_including_flush"])
        self.assertFalse(result["quality"]["approved_for_live_use"])

    def test_repetitions_reverse_order_and_incomplete_transcription_is_not_success(self):
        self.models()
        orders = []
        def run(root, path, engine, model, *args, **kwargs):
            orders.append(engine)
            return {"engine": engine, "compute": "cpu/int8", "transcription_complete": engine == "streaming", "source_unchanged": True,
                    "pcm_matches_input": True, "inference_to_audio_ratio": .5, "maximum_logged_queue": 1}
        with patch("factcheck.benchmarking.isolated_trial", side_effect=run):
            report = compare(self.path, self.root, self.output, repeats=2, progress=lambda _: None)
        self.assertEqual(orders, ["streaming", "whisper", "whisper", "streaming"])
        self.assertEqual(report["status"], "incomplete")
        self.assertEqual(len(json.loads(self.output.read_text())["trials"]), 4)

    def test_keyboard_interrupt_keeps_previous_results_and_reports_interrupted_status(self):
        self.models()
        result = {"engine": "streaming", "compute": "cpu/int8", "transcription_complete": True, "source_unchanged": True,
                  "pcm_matches_input": True, "inference_to_audio_ratio": .5, "maximum_logged_queue": 0}
        with patch("factcheck.benchmarking.isolated_trial", side_effect=[result, KeyboardInterrupt()]):
            with self.assertRaises(KeyboardInterrupt):
                compare(self.path, self.root, self.output, progress=lambda _: None)
        report = json.loads(self.output.read_text())
        self.assertEqual(report["status"], "interrupted")
        self.assertEqual(len(report["trials"]), 1)
        self.assertTrue(report["input_unchanged"])

    def test_changed_or_removed_input_stops_comparison_and_still_writes_partial_report(self):
        self.models()
        def remove(*args, **kwargs):
            self.path.unlink()
            raise ValueError("Entrada removida durante o ensaio")
        with patch("factcheck.benchmarking.isolated_trial", side_effect=remove):
            with self.assertRaisesRegex(ValueError, "Entrada removida"):
                compare(self.path, self.root, self.output, progress=lambda _: None)
        report = json.loads(self.output.read_text())
        self.assertFalse(report["input_unchanged"])
        self.assertEqual(report["status"], "interrupted")

    def test_existing_unrelated_json_is_preserved_before_creating_any_session(self):
        self.output.write_text('{"private":"preserve"}', encoding="utf8")
        with self.assertRaisesRegex(ValueError, "outro arquivo"):
            compare(self.path, self.root, self.output)
        self.assertEqual(json.loads(self.output.read_text()), {"private": "preserve"})
        self.assertFalse((self.root / "recordings").exists())

    def test_model_change_blocks_next_trial_and_records_failed_identity(self):
        self.models()
        result = {"engine": "streaming", "compute": "cpu/int8", "transcription_complete": True, "source_unchanged": True,
                  "pcm_matches_input": True, "inference_to_audio_ratio": .5, "maximum_logged_queue": 0}
        def replace_model(*args, **kwargs):
            (self.root / "models/small/model.bin").write_bytes(b"different-model")
            return result
        with patch("factcheck.benchmarking.isolated_trial", side_effect=replace_model) as run:
            with self.assertRaisesRegex(ValueError, "modelos mudaram"):
                compare(self.path, self.root, self.output, progress=lambda _: None)
        run.assert_called_once()
        report = json.loads(self.output.read_text())
        self.assertEqual(report["status"], "interrupted")
        self.assertFalse(report["models_unchanged"])
        self.assertEqual(len(report["trials"]), 1)


if __name__ == "__main__":
    unittest.main()
