import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import wave

from factcheck.audio import AudioDevice
from factcheck.review import ReviewStore
from factcheck.reporting import session_report
from factcheck.session import CaptureSession
from factcheck.transcription import TranscriptLine
from factcheck.persistence import atomic_json
from tests.test_replay import wav_file
from tests.test_session import FakeAudio, FakeStream, FakeStreamingEngine


class CapturePauseTests(unittest.TestCase):
    def record(self, root, cancel=False):
        session = CaptureSession(AudioDevice(1, "Test output", 1000, 1), root)
        class Stream(FakeStream):
            def start_stream(self):
                self.active = True
                self.callback(b"\xe8\x03"*1000, 1000, {}, 0)
                session.set_paused(True)
                self.callback(b"\xe8\x03"*1000, 1000, {}, 0)
                if not cancel:
                    session.set_paused(False)
                    self.callback(b"\xe8\x03"*1000, 1000, {}, 0)
        class Audio(FakeAudio):
            def open(self, **kwargs): return Stream(kwargs["stream_callback"])
        class Engine(FakeStreamingEngine):
            def finish(self): return [TranscriptLine(0, 3, "A taxa foi de 3% no Brasil.")]
        session.emit = lambda kind, _: (session.cancel() if cancel else session.stop()) if kind == "started" else None
        module = SimpleNamespace(PyAudio=Audio, paAbort=2, paContinue=0, paInputOverflow=2, paInt16=8)
        with patch.dict("sys.modules", {"pyaudiowpatch": module}), patch("factcheck.session.StreamingTranscriber", return_value=Engine()):
            session.run()
        return session

    def test_pause_discards_only_marked_pcm_and_preserves_timeline_and_gap_in_export(self):
        with tempfile.TemporaryDirectory() as directory:
            session = self.record(Path(directory))
            with wave.open(str(session.folder/"audio.wav")) as wav:
                self.assertEqual(wav.getnframes(), 3000)
                self.assertEqual(wav.readframes(3000), b"\xe8\x03"*1000 + bytes(2000) + b"\xe8\x03"*1000)
            metadata = json.loads((session.folder/"session.json").read_text())
            self.assertEqual(metadata["pause_intervals"], [{"start": 1, "end": 2, "reason": "operator_pause"}])
            self.assertTrue(metadata["audio_omitted_by_operator"])
            review = ReviewStore(session.folder)
            self.assertEqual(review.source(1)["original"]["audio_gaps"], metadata["pause_intervals"])
            report = session_report(review)
            self.assertEqual(report["capture"]["operator_pause_seconds"], 1)
            self.assertTrue(any("ignorado" in item for item in report["notices"]))

    def test_cancel_while_paused_closes_interval_and_does_not_resume_recognition(self):
        with tempfile.TemporaryDirectory() as directory:
            session = self.record(Path(directory), cancel=True)
            self.assertEqual(session.metadata["status"], "cancelled")
            self.assertEqual(session.metadata["pause_intervals"][0]["end"], 2)
            self.assertEqual(session.metadata["transcript_lines"], 0)
            with self.assertRaises(ValueError): session.set_paused(False)

    def test_pause_edge_is_persisted_before_session_finalization_for_crash_diagnostics(self):
        writes = []
        def save(path, data):
            writes.append(json.loads(json.dumps(data)))
            atomic_json(path, data)
        with tempfile.TemporaryDirectory() as directory, patch("factcheck.session.atomic_json", side_effect=save):
            self.record(Path(directory))
        pauses = [row for row in writes if row["status"] == "recording" and row["pause_intervals"]]
        self.assertIsNone(pauses[0]["pause_intervals"][0]["end"])
        self.assertTrue(pauses[0]["audio_omitted_by_operator"])
        self.assertEqual(pauses[-1]["pause_intervals"][0]["end"], 2)

    def test_gap_requires_human_transcript_review_before_triage_or_manual_claim(self):
        with tempfile.TemporaryDirectory() as directory:
            session = self.record(Path(directory))
            review = ReviewStore(session.folder)
            fields = [{"quote": review.source(1)["text"], "summary": review.source(1)["text"], "category": "fato", "topic": None}]
            with self.assertRaises(ValueError): review.begin_analysis(1, force=True)
            with self.assertRaises(ValueError): review.create_claims(1, 1, fields, "Inclusão fictícia.")
            source = review.source(1)
            review.revise(1, source["revision"], source["text"], None, reviewed=True)
            self.assertIsNotNone(review.begin_analysis(1)[0])

    def test_combining_paragraphs_does_not_hide_pause_context(self):
        with tempfile.TemporaryDirectory() as directory:
            session = self.record(Path(directory))
            review = ReviewStore(session.folder)
            review.ingest({"paragraph_id": 2, "version": 1, "text": "Outra frase.", "source_text": "Outra frase.", "start": 3, "end": 4, "closed": True, "parts": []})
            combined = review.combine(1, 1, 2, 1, confirmed_unknown=True)
            self.assertEqual(combined["original"]["audio_gaps"][0]["start"], 1)
            with self.assertRaises(ValueError): review.begin_analysis(combined["paragraph_id"])

    def test_paced_wav_pause_keeps_original_file_and_total_frames(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); source = root/"input.wav"
            wav_file(source, frames=8000)
            before = source.read_bytes()
            session = CaptureSession(AudioDevice(-1, "Ensaio WAV · input.wav", 8000, 1, True), root, transcribe=False, replay_path=source)
            states = []
            def emit(kind, data):
                if kind == "level" and not session.stop_event.is_set():
                    if not states:
                        session.set_paused(True); states.append(True)
                    elif len(states) == 1 and data["audio_seconds"] >= .5:
                        session.set_paused(False); states.append(False)
            session.emit = emit
            self.assertTrue(session.run())
            self.assertEqual(source.read_bytes(), before)
            self.assertEqual(session.metadata["frames"], 8000)
            self.assertEqual(states, [True, False])
            interval = session.metadata["pause_intervals"][0]
            with wave.open(str(session.folder/"audio.wav")) as wav:
                wav.setpos(round(interval["start"]*8000))
                self.assertEqual(wav.readframes(round((interval["end"]-interval["start"])*8000)), bytes(round((interval["end"]-interval["start"])*8000)*2))


if __name__ == "__main__": unittest.main()
