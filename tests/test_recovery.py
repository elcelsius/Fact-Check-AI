from io import BytesIO
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import wave

from factcheck.dossiers import DossierStore
from factcheck.exports import csv_rows, snapshot
from factcheck.persistence import atomic_json
from factcheck.recovery import (AudioRecoveryTask, capture_state, inspect_audio, inspect_session,
                               playback_path, recover_audio)
from factcheck.review import ReviewStore


def paragraph(pid=1):
    return {"paragraph_id": pid, "version": 1, "source_text": "Fala fictícia.", "text": "Fala fictícia.",
            "start": 0, "end": .1, "speaker": None, "closed": False, "parts": []}


def wav_bytes(pcm=b"\x10\x00" * 4):
    stream = BytesIO()
    with wave.open(stream, "wb") as wav:
        wav.setparams((1, 2, 8000, 0, "NONE", "not compressed"))
        wav.writeframes(pcm)
    return stream.getvalue()


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.folder = Path(self.directory.name)
        atomic_json(self.folder / "session.json", {"status": "completed"})
        self.review = ReviewStore(self.folder)
        self.dossier = DossierStore(self.review)

    def tearDown(self):
        self.directory.cleanup()

    def damaged_audio(self, tail=b""):
        raw = bytearray(wav_bytes() + tail)
        struct.pack_into("<I", raw, 4, 38)
        struct.pack_into("<I", raw, 40, 2)
        (self.folder / "audio.wav").write_bytes(raw)
        return bytes(raw)

    def test_atomic_metadata_failure_preserves_previous_document_and_cleans_temp(self):
        target = self.folder / "session.json"
        original = target.read_bytes()
        with patch("factcheck.persistence.os.replace", side_effect=PermissionError):
            with self.assertRaises(PermissionError):
                atomic_json(target, {"status": "finalizing"})
        self.assertEqual(target.read_bytes(), original)
        self.assertEqual(list(self.folder.glob("*.tmp")), [])

    def test_complete_records_import_but_incomplete_utf8_tail_stays_untouched(self):
        raw = (json.dumps(paragraph()) + "\n").encode() + b'{"source_text":"interromp\xc3'
        path = self.folder / "paragraphs.jsonl"
        path.write_bytes(raw)
        warnings = self.review.import_paragraphs()
        self.assertEqual(len(warnings), 1)
        self.assertIn("última linha", warnings[0])
        self.assertEqual(self.review.source(1)["source_version"], 1)
        source = self.review.revise(1, 1, "Correção humana preservada.", None)
        self.review.import_paragraphs()
        self.assertEqual(self.review.source(1), source)
        self.assertEqual(path.read_bytes(), raw)

    def test_corruption_inside_log_blocks_import_before_any_records_are_ingested(self):
        path = self.folder / "paragraphs.jsonl"
        path.write_text(json.dumps(paragraph()) + '\n{"erro":\n' + json.dumps(paragraph(2)), encoding="utf8")
        with self.assertRaisesRegex(ValueError, "linha 2 inválida"):
            self.review.import_paragraphs()
        self.assertEqual(self.review.sources(), [])

    def test_invalid_record_terminated_by_newline_is_not_treated_as_crash_tail(self):
        (self.folder / "paragraphs.jsonl").write_bytes(b'{"erro":\n')
        with self.assertRaises(ValueError):
            self.review.import_paragraphs()

    def test_valid_final_record_without_newline_imports_normally(self):
        (self.folder / "paragraphs.jsonl").write_text(json.dumps(paragraph()), encoding="utf8")
        self.assertEqual(self.review.import_paragraphs(), [])
        self.assertEqual(len(self.review.sources()), 1)

    def test_valid_json_with_incompatible_record_is_not_silently_skipped(self):
        for value in ({}, {**paragraph(), "end": float("nan")}, {**paragraph(), "start": -1}, []):
            with self.subTest(value=value):
                (self.folder / "paragraphs.jsonl").write_text(json.dumps(value), encoding="utf8")
                with self.assertRaisesRegex(ValueError, "incompatível"):
                    self.review.import_paragraphs()

    def test_process_status_distinguishes_live_dead_and_unknown_owner(self):
        for status in ("recording", "finalizing"):
            atomic_json(self.folder / "session.json", {"status": status, "owner_pid": os.getpid()})
            with patch("factcheck.recovery.process_alive", return_value=True):
                self.assertEqual(capture_state(self.folder)[0], "active")
            with patch("factcheck.recovery.process_alive", return_value=False):
                self.assertEqual(capture_state(self.folder)[0], "interrupted")
        for owner in (None, "1", -1, 2**64):
            atomic_json(self.folder / "session.json", {"status": "recording", "owner_pid": owner})
            self.assertEqual(capture_state(self.folder)[0], "unknown")

    def test_bad_legacy_metadata_preserves_existing_editorial_database(self):
        self.review.ingest(paragraph())
        (self.folder / "session.json").write_bytes(b'{"status":')
        reopened = ReviewStore(self.folder)
        report = inspect_session(reopened)
        self.assertEqual(report["state"], "unknown")
        self.assertEqual(report["paragraphs"], 1)
        with self.assertRaises(ValueError):
            reopened.close_interrupted_paragraphs([(1, 1)])

    def test_manual_closure_preserves_human_text_and_originals_without_approving_transcription(self):
        self.review.ingest(paragraph())
        source = self.review.revise(1, 1, "Texto humano.", None)
        original = source["original"]
        self.assertEqual(self.review.close_interrupted_paragraphs([(1, 2)]), 1)
        closed = self.review.source(1)
        self.assertTrue(closed["closed"])
        self.assertFalse(closed["human_reviewed"])
        self.assertEqual(closed["text"], "Texto humano.")
        self.assertEqual(closed["original"], original)
        self.assertIn("recovery_closure", snapshot(self.review)["paragraphs"][0])
        self.assertTrue(next(csv_rows(snapshot(self.review), "paragraphs"))["encerramento_recuperado_em"])
        self.assertEqual(closed["revision"], 3)

    def test_closure_rejects_active_capture_and_stale_batch_rolls_back_entire_change(self):
        self.review.ingest(paragraph())
        self.review.ingest(paragraph(2))
        with self.assertRaises(ValueError):
            self.review.close_interrupted_paragraphs([(1, 1), (2, 99)])
        self.assertFalse(self.review.source(1)["closed"])
        atomic_json(self.folder / "session.json", {"status": "recording", "owner_pid": os.getpid()})
        with patch("factcheck.recovery.process_alive", return_value=True), self.assertRaises(ValueError):
            self.review.close_interrupted_paragraphs([(1, 1)])

    def test_complete_audio_is_played_directly_and_needs_no_copy(self):
        path = self.folder / "audio.wav"
        path.write_bytes(wav_bytes())
        self.assertEqual(inspect_audio(self.folder)["state"], "ok")
        self.assertEqual(playback_path(self.folder), path)
        with self.assertRaises(ValueError):
            recover_audio(self.review)

    def test_recovered_copy_includes_all_complete_pcm_frames_and_preserves_original(self):
        original = self.damaged_audio(b"\xff")
        info = inspect_audio(self.folder)
        self.assertEqual(info["dropped_bytes"], 1)
        path = recover_audio(self.review)
        with wave.open(str(path), "rb") as wav:
            self.assertEqual(wav.getnframes(), 4)
            self.assertEqual(wav.readframes(100), b"\x10\x00" * 4)
        self.assertEqual((self.folder / "audio.wav").read_bytes(), original)
        self.assertEqual(playback_path(self.folder), path)
        self.assertTrue(inspect_session(ReviewStore(self.folder))["playable"])
        with self.review.connection() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM history WHERE kind='audio_recovered'").fetchone()[0], 1)

    def test_recovery_rejects_unknown_or_live_capture(self):
        original = self.damaged_audio()
        for metadata in ({"status": "recording"}, {"status": "recording", "owner_pid": os.getpid()}):
            atomic_json(self.folder / "session.json", metadata)
            with patch("factcheck.recovery.process_alive", return_value=True), self.assertRaises(ValueError):
                recover_audio(self.review)
        self.assertEqual((self.folder / "audio.wav").read_bytes(), original)

    def test_source_change_during_copy_prevents_commit(self):
        self.damaged_audio()
        info = inspect_audio(self.folder)
        with patch("factcheck.recovery.inspect_audio", side_effect=[info, {**info, "fingerprint": "changed"}]), self.assertRaises(ValueError):
            recover_audio(self.review)
        self.assertEqual(list((self.folder / "recovered").iterdir()), [])

    def test_cancelled_copy_preserves_original_and_removes_partial_output(self):
        original = self.damaged_audio()
        cancelled = threading.Event()
        with patch.object(cancelled, "is_set", side_effect=[False, True]), self.assertRaises(InterruptedError):
            recover_audio(self.review, cancelled)
        self.assertEqual((self.folder / "audio.wav").read_bytes(), original)
        self.assertEqual(list((self.folder / "recovered").iterdir()), [])

    def test_unsupported_or_missing_audio_is_reported_without_guessing_format(self):
        self.assertEqual(inspect_audio(self.folder)["state"], "missing")
        (self.folder / "audio.wav").write_bytes(b"not a wav")
        self.assertEqual(inspect_audio(self.folder)["state"], "unsupported")
        with self.assertRaises(ValueError):
            playback_path(self.folder)

    def test_interrupted_job_recovery_is_audited_and_repeatable_without_network_or_model(self):
        self.review.ingest(paragraph())
        self.review.begin_analysis(1)
        with patch("factcheck.review.process_alive", return_value=False):
            self.assertEqual(self.review.recover_interrupted(), 1)
            self.assertEqual(self.review.recover_interrupted(), 0)
        self.assertIn("recovered_at", self.review.analysis_states()[(1, 1)])
        report = inspect_session(self.review)
        self.assertEqual(report["triage_interrupted"], 1)
        self.assertEqual(report["running"], 0)
        with self.review.connection() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM history WHERE kind='analysis_interrupted'").fetchone()[0], 1)

    def test_audio_task_cancellation_emits_completion_for_close_guard(self):
        self.damaged_audio()
        events, done = [], threading.Event()
        task = AudioRecoveryTask(self.review, lambda kind, data: (events.append((kind, data)), done.set()))
        task.cancel()
        task.start()
        self.assertTrue(done.wait(3))
        self.assertEqual(task.pending, 0)
        self.assertEqual(events[0][0], "recovery_done")
        self.assertFalse(events[0][1]["success"])

    @unittest.skipUnless(sys.platform == "win32", "Detecção e encerramento de subprocesso no Windows")
    def test_real_subprocess_crash_rolls_back_transaction_and_preserves_review(self):
        from scripts.rehearse_recovery import rehearse
        report = rehearse(self.folder / "drill")
        self.assertTrue(all(report["checks"].values()))


if __name__ == "__main__":
    unittest.main()
