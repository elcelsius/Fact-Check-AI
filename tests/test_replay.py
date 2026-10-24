from hashlib import sha256
import json
from pathlib import Path
import struct
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import wave

from factcheck.replay import inspect_replay,replay_device
from factcheck.review import ReviewStore
from factcheck.reporting import session_report
from factcheck.session import CaptureSession
from tests.test_session import FakeStreamingEngine


def wav_file(path,frames=4000,rate=8000,channels=1):
    pcm=b"".join(struct.pack("<h",(index%1000)-500)*channels for index in range(frames))
    with wave.open(str(path),"wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(pcm)
    return pcm


class ReplayTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory()
        self.root=Path(self.directory.name)
        self.path=self.root/"ensaio.wav"
        self.pcm=wav_file(self.path)

    def tearDown(self):
        self.directory.cleanup()

    def test_paced_replay_finishes_at_eof_without_hardware_sound_or_extra_samples(self):
        original=sha256(self.path.read_bytes()).hexdigest()
        emitted=[]
        recording=CaptureSession(replay_device(self.path),self.root,lambda kind,data:emitted.append((kind,data)),transcribe=False,replay_path=self.path)
        began=time.perf_counter()
        with patch.dict("sys.modules",{"pyaudiowpatch":None}):
            self.assertTrue(recording.run())
        self.assertGreaterEqual(time.perf_counter()-began,0.45)
        with wave.open(str(recording.folder/"audio.wav"),"rb") as wav:
            self.assertEqual(wav.readframes(wav.getnframes()),self.pcm)
        self.assertEqual(sha256(self.path.read_bytes()).hexdigest(),original)
        self.assertEqual(recording.metadata["frames"],4000)
        self.assertEqual(recording.metadata["input_kind"],"wav_replay")
        self.assertFalse(recording.metadata["replay"]["audible_playback"])
        self.assertEqual(recording.metadata["status"],"completed")
        self.assertEqual(next(data["input_kind"] for kind,data in emitted if kind=="started"),"wav_replay")

    def test_replay_uses_same_transcription_paragraph_and_review_pipeline(self):
        engine=FakeStreamingEngine()
        recording=CaptureSession(replay_device(self.path),self.root,replay_path=self.path)
        with patch("factcheck.session.StreamingTranscriber",return_value=engine):
            self.assertTrue(recording.run())
        self.assertEqual(engine.finish_calls,1)
        review=ReviewStore(recording.folder)
        self.assertEqual(review.sources()[0]["text"],"Última frase estabilizada")
        self.assertFalse(review.sources()[0]["human_reviewed"])
        report=session_report(review)
        self.assertEqual(report["capture"]["input_kind"],"wav_replay")

    def test_cancelling_during_recognition_preserves_pcm_prefix_and_rejects_late_text(self):
        self.pcm=wav_file(self.path,frames=16000)
        engine=FakeStreamingEngine(wait=True)
        recording=CaptureSession(replay_device(self.path),self.root,replay_path=self.path)
        with patch("factcheck.session.StreamingTranscriber",return_value=engine):
            worker=threading.Thread(target=recording.run,daemon=True)
            worker.start()
            try:
                self.assertTrue(engine.started.wait(5))
                recording.cancel()
            finally:
                engine.release.set()
                worker.join(5)
        self.assertFalse(worker.is_alive())
        self.assertEqual(recording.metadata["status"],"cancelled")
        self.assertEqual(recording.metadata["transcript_lines"],0)
        self.assertGreater(recording.metadata["frames"],0)
        self.assertLess(recording.metadata["frames"],16000)
        with wave.open(str(recording.folder/"audio.wav"),"rb") as wav:
            data=wav.readframes(wav.getnframes())
        self.assertEqual(data,self.pcm[:len(data)])

    def test_changed_input_is_reported_without_overwriting_source(self):
        def emit(kind,data):
            if kind=="started":
                with self.path.open("r+b") as stream:
                    stream.seek(44)
                    stream.write(b"\x01\x00")
        recording=CaptureSession(replay_device(self.path),self.root,emit,transcribe=False,replay_path=self.path)
        self.assertFalse(recording.run())
        self.assertEqual(recording.metadata["status"],"capture_error")
        self.assertTrue(any("mudou" in item["message"] for item in recording.metadata["issues"]))

    def test_invalid_or_truncated_wav_is_rejected_before_new_session(self):
        for body in (b"not a wave",self.path.read_bytes()[:-3]):
            path=self.root/"invalid.wav"
            path.write_bytes(body)
            with self.assertRaises((ValueError,wave.Error,EOFError)):
                inspect_replay(path)
        self.assertFalse((self.root/"recordings").exists())

    def test_stereo_replay_preserves_channels_rate_and_all_pcm(self):
        self.pcm=wav_file(self.path,frames=12000,rate=48000,channels=2)
        recording=CaptureSession(replay_device(self.path),self.root,transcribe=False,replay_path=self.path)
        self.assertTrue(recording.run())
        with wave.open(str(recording.folder/"audio.wav"),"rb") as wav:
            self.assertEqual((wav.getnchannels(),wav.getframerate()),(2,48000))
            self.assertEqual(wav.readframes(wav.getnframes()),self.pcm)


if __name__=="__main__":
    unittest.main()
