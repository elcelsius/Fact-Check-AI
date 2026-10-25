from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import os

import numpy as np

from factcheck.transcription import LocalTranscriber
from factcheck.session import CaptureSession
from factcheck.replay import replay_device
from tests.test_replay import wav_file
from tests.test_session import FakeEngine
from factcheck.cuda_runtime import whisper_cuda_libraries


class WhisperComputeTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        folder = self.root / "models/small"
        folder.mkdir(parents=True)
        for name in ("model.bin", "config.json", "tokenizer.json"):
            (folder / name).write_bytes(b"model-fixture")

    def tearDown(self):
        self.directory.cleanup()

    def test_cpu_remains_default_and_never_initializes_cuda_or_warmup(self):
        model = Mock()
        factory = Mock(return_value=model)
        with patch.dict("sys.modules", {"faster_whisper": SimpleNamespace(WhisperModel=factory), "faster_whisper.utils": SimpleNamespace(download_model=Mock())}), patch("factcheck.cuda_runtime.whisper_cuda_libraries") as cuda:
            engine = LocalTranscriber(self.root)
            engine.prepare()
        self.assertEqual(factory.call_args.kwargs["device"], "cpu")
        self.assertEqual(factory.call_args.kwargs["compute_type"], "int8")
        cuda.assert_not_called()
        model.transcribe.assert_not_called()

    def test_cuda_is_explicit_and_consumes_synthetic_warmup_before_real_audio(self):
        consumed = []
        def segments():
            consumed.append("warmup-consumed")
            yield "discarded-synthetic-result"
        model = Mock()
        model.transcribe.return_value = (segments(), None)
        factory = Mock(return_value=model)
        with patch.dict("sys.modules", {"faster_whisper": SimpleNamespace(WhisperModel=factory), "faster_whisper.utils": SimpleNamespace(download_model=Mock())}), patch("factcheck.cuda_runtime.whisper_cuda_libraries", return_value=(["handle"], ["native"])), patch.dict("os.environ", {"CUDA_CACHE_PATH": str(self.root / "cache")}):
            engine = LocalTranscriber(self.root, device="cuda")
            engine.prepare()
        self.assertEqual(factory.call_args.kwargs["device"], "cuda")
        self.assertEqual(factory.call_args.kwargs["compute_type"], "int8_float16")
        self.assertEqual(consumed, ["warmup-consumed"])
        self.assertEqual(len(model.transcribe.call_args.args[0]), 16000)
        self.assertTrue(np.all(model.transcribe.call_args.args[0] == 0))
        self.assertFalse(model.transcribe.call_args.kwargs["vad_filter"])
        self.assertEqual(engine.compute, "cuda/int8_float16")

    def test_cuda_setup_failure_does_not_silently_switch_to_cpu(self):
        factory = Mock()
        with patch.dict("sys.modules", {"faster_whisper": SimpleNamespace(WhisperModel=factory), "faster_whisper.utils": SimpleNamespace(download_model=Mock())}), patch("factcheck.cuda_runtime.whisper_cuda_libraries", side_effect=ValueError("Runtime ausente")):
            with self.assertRaisesRegex(ValueError, "Runtime ausente"):
                LocalTranscriber(self.root, device="cuda").prepare()
        factory.assert_not_called()

    def test_session_records_selected_compute_and_completes_same_audio_pipeline(self):
        path = self.root / "input.wav"
        wav_file(path)
        session = CaptureSession(replay_device(path), self.root, engine_name="whisper", replay_path=path, whisper_device="cuda")
        with patch("factcheck.session.LocalTranscriber", return_value=FakeEngine()) as factory:
            self.assertTrue(session.run())
        self.assertEqual(factory.call_args.kwargs["device"], "cuda")
        self.assertEqual(session.metadata["compute"], "cuda/int8_float16")
        self.assertTrue(session.metadata["transcription_complete"])
        self.assertEqual(session.metadata["frames"], 4000)

    def test_continuous_mode_cannot_claim_cuda_and_invalid_devices_are_rejected(self):
        with self.assertRaises(ValueError):
            LocalTranscriber(self.root, device="invented")
        with self.assertRaises(ValueError):
            CaptureSession(None, self.root, whisper_device="cuda")

    @unittest.skipUnless(os.name == "nt", "Carregador de DLLs do Windows")
    def test_missing_dlls_are_reported_before_loading_any_native_library(self):
        with patch("factcheck.cuda_runtime.sys.prefix", str(self.root)), patch("factcheck.cuda_runtime.ctypes.CDLL") as native:
            with self.assertRaisesRegex(ValueError, "requirements-gpu.lock"):
                whisper_cuda_libraries()
        native.assert_not_called()

    @unittest.skipUnless(os.name == "nt", "Carregador de DLLs do Windows")
    def test_native_load_failure_closes_scoped_search_handles_without_changing_path(self):
        vendor = self.root / "Lib/site-packages/nvidia"
        for subpath in ("cublas/bin/cublas64_12.dll", "cudnn/bin/cudnn64_9.dll"):
            path = vendor / subpath
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"dll-fixture")
        handles = [Mock(), Mock()]
        before = os.environ.get("PATH")
        with patch("factcheck.cuda_runtime.sys.prefix", str(self.root)), patch("factcheck.cuda_runtime.os.add_dll_directory", side_effect=handles), patch("factcheck.cuda_runtime.ctypes.CDLL", side_effect=OSError("runtime quebrado")):
            with self.assertRaisesRegex(ValueError, "runtime NVIDIA"):
                whisper_cuda_libraries()
        for handle in handles:
            handle.close.assert_called_once()
        self.assertEqual(os.environ.get("PATH"), before)


if __name__ == "__main__":
    unittest.main()
