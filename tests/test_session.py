import json
import os
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import wave

from factcheck.audio import AudioDevice
from factcheck.session import CaptureSession
from factcheck.transcription import TranscriptLine


class FakeStream:
    def __init__(self, callback):
        self.callback = callback
        self.active = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.active = False

    def start_stream(self):
        self.active = True
        self.callback(b"\xe8\x03" * 600, 600, {"input_buffer_adc_time": 0}, 0)

    def stop_stream(self):
        self.active = False

    def is_active(self):
        return self.active


class FakeAudio:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def get_device_info_by_index(self, index):
        return {"name": "Test output", "isLoopbackDevice": True}

    def open(self, **kwargs):
        return FakeStream(kwargs["stream_callback"])


class FakeEngine:
    def __init__(self, wait=False):
        self.started = threading.Event()
        self.release = threading.Event()
        self.wait = wait
        self.calls = 0

    def prepare(self):
        pass

    def transcribe(self, chunk):
        self.calls += 1
        self.started.set()
        if self.wait and not self.release.wait(5):
            raise RuntimeError("Teste excedeu seu limite de espera.")
        return [TranscriptLine(chunk.start, chunk.start + 0.1, "Trecho automático")]


class FakeStreamingEngine(FakeEngine):
    def __init__(self, wait=False, fail=False):
        super().__init__(wait)
        self.fail = fail
        self.finish_calls = 0
        self.partial = {"text": "hipótese provisória", "start": 0, "end": 0.2}

    def transcribe(self, chunk):
        lines = super().transcribe(chunk)
        if self.fail:
            raise RuntimeError("Falha de reconhecimento simulada")
        return lines if self.wait else []

    def finish(self):
        self.finish_calls += 1
        return [TranscriptLine(0, 0.2, "Última frase estabilizada")]


class SessionCancellationTests(unittest.TestCase):
    device = AudioDevice(1, "Test output", 100, 1)

    def audio_module(self):
        return SimpleNamespace(PyAudio=FakeAudio, paAbort=2, paContinue=0,
                               paInputOverflow=2, paInt16=8)

    def test_cancel_before_start_does_not_load_model_or_create_recording(self):
        with tempfile.TemporaryDirectory() as directory:
            emitted = []
            session = CaptureSession(self.device, Path(directory),
                                     emit=lambda kind, data: emitted.append((kind, data)), engine_name="whisper")
            session.cancel()
            with patch("factcheck.session.LocalTranscriber") as model:
                self.assertFalse(session.run())
            model.assert_not_called()
            self.assertIsNone(session.folder)
            self.assertTrue(emitted[-1][1]["cancelled"])

    def test_cancel_discards_pending_results_but_preserves_audio(self):
        engine = FakeEngine(wait=True)
        with tempfile.TemporaryDirectory() as directory:
            emitted = []
            session = CaptureSession(self.device, Path(directory),
                                     emit=lambda kind, data: emitted.append((kind, data)), engine_name="whisper")
            with patch.dict("sys.modules", {"pyaudiowpatch": self.audio_module()}), \
                    patch("factcheck.session.LocalTranscriber", return_value=engine):
                runner = threading.Thread(target=session.run, daemon=True)
                runner.start()
                try:
                    self.assertTrue(engine.started.wait(3))
                    session.cancel()
                finally:
                    engine.release.set()
                    runner.join(3)
                self.assertFalse(runner.is_alive())
            metadata = json.loads((session.folder / "session.json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["status"], "cancelled")
            self.assertFalse(metadata["transcription_complete"])
            self.assertEqual(engine.calls, 1)
            self.assertEqual((session.folder / "transcript.jsonl").read_text(encoding="utf-8"), "")
            self.assertFalse(any(kind == "transcript" for kind, _ in emitted))
            with wave.open(str(session.folder / "audio.wav"), "rb") as wav:
                self.assertEqual(wav.getnframes(), 600)

    def test_normal_stop_finishes_queued_transcriptions(self):
        engine = FakeEngine()
        with tempfile.TemporaryDirectory() as directory:
            session = CaptureSession(self.device, Path(directory), engine_name="whisper")
            session.emit = lambda kind, data: session.stop() if kind == "started" else None
            with patch.dict("sys.modules", {"pyaudiowpatch": self.audio_module()}), \
                    patch("factcheck.session.LocalTranscriber", return_value=engine):
                self.assertTrue(session.run())
            self.assertEqual(session.metadata["status"], "completed")
            self.assertEqual(session.metadata["owner_pid"], os.getpid())
            self.assertEqual(session.metadata["schema_version"], 5)
            self.assertTrue(session.metadata["transcription_complete"])
            self.assertGreaterEqual(engine.calls, 3)
            self.assertGreater(session.metadata["transcript_lines"], 0)
            records = [json.loads(line) for line in (session.folder / "events.jsonl").read_text(encoding="utf8").splitlines()]
            deliveries = [record for record in records if record["kind"] == "transcript_delivered"]
            self.assertEqual(len(deliveries), session.metadata["transcript_lines"])
            self.assertAlmostEqual(deliveries[0]["delivery_lag_seconds"], deliveries[0]["elapsed_seconds"] - deliveries[0]["end"], places=5)
            self.assertNotIn("text", deliveries[0])


class StreamingSessionTests(SessionCancellationTests):
    # Reutilizar o dispositivo e os auxiliares sem repetir os testes do Whisper.
    def test_cancel_before_start_does_not_load_model_or_create_recording(self):
        with tempfile.TemporaryDirectory() as directory:
            session = CaptureSession(self.device, Path(directory))
            session.cancel()
            with patch("factcheck.session.StreamingTranscriber") as model:
                self.assertFalse(session.run())
            model.assert_not_called()

    def test_cancel_discards_pending_results_but_preserves_audio(self):
        engine = FakeStreamingEngine(wait=True)
        with tempfile.TemporaryDirectory() as directory:
            emitted = []
            session = CaptureSession(self.device, Path(directory),
                                     emit=lambda kind, data: emitted.append((kind, data)))
            with patch.dict("sys.modules", {"pyaudiowpatch": self.audio_module()}), \
                    patch("factcheck.session.StreamingTranscriber", return_value=engine):
                runner = threading.Thread(target=session.run, daemon=True)
                runner.start()
                try:
                    self.assertTrue(engine.started.wait(3))
                    session.cancel()
                finally:
                    engine.release.set()
                    runner.join(3)
            self.assertFalse(runner.is_alive())
            self.assertEqual(session.metadata["status"], "cancelled")
            self.assertEqual(engine.calls, 1)
            self.assertEqual(engine.finish_calls, 0)
            self.assertFalse(any(kind in {"transcript", "partial"} for kind, _ in emitted))
            self.assertEqual((session.folder / "transcript.jsonl").read_text(encoding="utf8"), "")
            with wave.open(str(session.folder / "audio.wav"), "rb") as wav:
                self.assertEqual(wav.getnframes(), 600)

    def test_normal_stop_finishes_queued_transcriptions(self):
        engine = FakeStreamingEngine()
        with tempfile.TemporaryDirectory() as directory:
            emitted = []
            session = CaptureSession(self.device, Path(directory))

            def emit(kind, data):
                emitted.append((kind, data))
                if kind == "started":
                    session.stop()

            session.emit = emit
            with patch.dict("sys.modules", {"pyaudiowpatch": self.audio_module()}), \
                    patch("factcheck.session.StreamingTranscriber", return_value=engine):
                self.assertTrue(session.run())
            self.assertEqual(engine.finish_calls, 1)
            self.assertTrue(session.metadata["transcription_complete"])
            events = [json.loads(line) for line in (session.folder / "events.jsonl").read_text(encoding="utf8").splitlines()]
            self.assertEqual(sum(record["kind"] == "first_partial" for record in events), 1)
            self.assertEqual(sum(record["kind"] == "transcript_delivered" for record in events), session.metadata["transcript_lines"])
            started = next(record for record in events if record["kind"] == "started")
            self.assertEqual(started["capture_started_at"], session.metadata["capture_started_at"])
            records = [json.loads(line) for line in (session.folder / "transcript.jsonl").read_text(encoding="utf8").splitlines()]
            self.assertEqual([line["text"] for line in records], ["Última frase estabilizada"])
            self.assertTrue(any(kind == "partial" and data["text"] for kind, data in emitted))
            self.assertEqual(records[0]["review_status"], "automatico_nao_revisado")
            revisions = [json.loads(line) for line in (session.folder / "paragraphs.jsonl").read_text(encoding="utf8").splitlines()]
            self.assertEqual(revisions[-1]["source_sequences"], [1])
            self.assertTrue(revisions[-1]["closed"])
            self.assertEqual(revisions[-1]["end_reason"], "encerramento")
            self.assertEqual(session.metadata["paragraph_count"], 1)
            text = (session.folder / "paragraphs.txt").read_text(encoding="utf8")
            self.assertEqual(text.count("Última frase estabilizada"), 1)

    def test_cancel_preserves_already_saved_paragraph_and_discards_only_pending_result(self):
        class TwoStageEngine(FakeStreamingEngine):
            def transcribe(self, chunk):
                self.calls += 1
                if self.calls == 1:
                    return [TranscriptLine(0, 0.2, "a renda cresceu")]
                self.started.set()
                if not self.release.wait(5):
                    raise RuntimeError("Teste excedeu seu limite de espera.")
                return [TranscriptLine(0.2, 0.4, "resultado pendente")]

        engine = TwoStageEngine()
        with tempfile.TemporaryDirectory() as directory:
            session = CaptureSession(self.device, Path(directory))
            with patch.dict("sys.modules", {"pyaudiowpatch": self.audio_module()}), \
                    patch("factcheck.session.StreamingTranscriber", return_value=engine):
                runner = threading.Thread(target=session.run, daemon=True)
                runner.start()
                try:
                    self.assertTrue(engine.started.wait(3))
                    session.cancel()
                finally:
                    engine.release.set()
                    runner.join(3)
                self.assertFalse(runner.is_alive())
            text = (session.folder / "paragraphs.txt").read_text(encoding="utf8")
            self.assertIn("A renda cresceu.", text)
            self.assertNotIn("resultado pendente", text)
            revisions = [json.loads(line) for line in (session.folder / "paragraphs.jsonl").read_text(encoding="utf8").splitlines()]
            self.assertEqual(revisions[-1]["end_reason"], "cancelamento")
            self.assertEqual(revisions[-1]["source_sequences"], [1])
            self.assertEqual(session.metadata["transcript_lines"], 1)

    def test_model_failure_stops_only_transcription_and_does_not_flush_invalid_state(self):
        engine = FakeStreamingEngine(fail=True)
        with tempfile.TemporaryDirectory() as directory:
            session = CaptureSession(self.device, Path(directory))
            session.emit = lambda kind, data: session.stop() if kind == "started" else None
            with patch.dict("sys.modules", {"pyaudiowpatch": self.audio_module()}), \
                    patch("factcheck.session.StreamingTranscriber", return_value=engine):
                self.assertTrue(session.run())
            self.assertEqual(session.metadata["frames"], 600)
            self.assertFalse(session.metadata["transcription_complete"])
            self.assertEqual(engine.calls, 1)
            self.assertEqual(engine.finish_calls, 0)
            self.assertEqual(session.metadata["issues"][0]["code"], "transcription_error")

    def test_backlog_preserves_full_audio_and_stops_stateful_recognition(self):
        engine = FakeStreamingEngine(wait=True)

        class LongStream(FakeStream):
            def start_stream(self):
                self.active = True
                self.callback(b"\xe8\x03" * 12000, 12000, {"input_buffer_adc_time": 0}, 0)

        class LongAudio(FakeAudio):
            def open(self, **kwargs):
                return LongStream(kwargs["stream_callback"])

        audio_module = self.audio_module()
        audio_module.PyAudio = LongAudio
        with tempfile.TemporaryDirectory() as directory:
            session = CaptureSession(self.device, Path(directory))

            def emit(kind, data):
                if kind == "started":
                    session.stop()
                if kind == "warning":
                    engine.release.set()

            session.emit = emit
            with patch.dict("sys.modules", {"pyaudiowpatch": audio_module}), \
                    patch("factcheck.session.StreamingTranscriber", return_value=engine):
                self.assertTrue(session.run())
            self.assertEqual(session.metadata["frames"], 12000)
            self.assertFalse(session.metadata["transcription_complete"])
            self.assertEqual(session.metadata["transcript_lines"], 0)
            self.assertEqual(engine.finish_calls, 0)
            self.assertEqual(session.metadata["issues"][0]["code"], "transcription_backlog")


if __name__ == "__main__":
    unittest.main()
