"""Reconhecimento local contínuo: hipóteses revisáveis e segmentos estabilizados."""

import os
from pathlib import Path

import numpy as np

from .audio import AudioChunk
from .transcription import TranscriptLine


MODEL_NAME = "sherpa-onnx-nemotron-3.5-asr-streaming-0.6b-160ms-int8-2026-06-11"
MODEL_REPO = f"csukuangfj2/{MODEL_NAME}"
MODEL_REVISION = "b3a4dbde84fba1a13cb4270e6730b525ac6a2db6"
MODEL_FILES = ("encoder.int8.onnx", "decoder.int8.onnx", "joiner.int8.onnx", "tokens.txt")
PACKET_SECONDS = 0.2


class StreamingTranscriber:
    def __init__(self, project_root: Path):
        self.root = project_root
        self.recognizer = None
        self.stream = None
        self.sample_rate: int | None = None
        self.channels: int | None = None
        self.received_frames = 0
        self.finished = False
        self.partial = {"text": "", "start": 0.0, "end": 0.0}

    def prepare(self) -> Path:
        from sherpa_onnx import OnlineRecognizer

        model_path = self.root / "models" / MODEL_NAME
        if not all((model_path / name).is_file() and (model_path / name).stat().st_size
                   for name in MODEL_FILES):
            os.environ.setdefault("HF_HOME", str(self.root / ".cache" / "huggingface"))
            from huggingface_hub import snapshot_download
            snapshot_download(
                MODEL_REPO, revision=MODEL_REVISION, local_dir=model_path,
                cache_dir=self.root / ".cache" / "huggingface",
                allow_patterns=[*MODEL_FILES, "README.md"],
            )
        self.recognizer = OnlineRecognizer.from_transducer(
            tokens=str(model_path / "tokens.txt"), encoder=str(model_path / MODEL_FILES[0]),
            decoder=str(model_path / MODEL_FILES[1]), joiner=str(model_path / MODEL_FILES[2]),
            num_threads=min(4, max(1, (os.cpu_count() or 4) - 2)), provider="cpu",
            enable_endpoint_detection=True, rule1_min_trailing_silence=2.4,
            rule2_min_trailing_silence=0.8, rule3_min_utterance_length=15,
            decoding_method="greedy_search",
        )
        self.stream = self.recognizer.create_stream()
        self.stream.set_option("language", "pt-BR")
        return model_path

    def _decode(self) -> None:
        while self.recognizer.is_ready(self.stream):
            self.recognizer.decode_stream(self.stream)

    def _result(self) -> dict:
        result = self.recognizer.get_result_all(self.stream)
        duration = self.received_frames / self.sample_rate if self.sample_rate else 0.0
        # O relógio nativo continua após reset; os timestamps dos tokens são relativos
        # ao início do segmento. A cauda sintética de flush nunca amplia o áudio real.
        stamps = list(result.timestamps)
        start = result.start_time + (min(stamps) if stamps else 0)
        end = result.start_time + max(stamps) + 0.08 if stamps else duration
        return {"text": result.text.strip(), "start": round(max(0, min(start, duration)), 3),
                "end": round(max(0, min(max(start, end), duration)), 3)}

    @staticmethod
    def _line(result: dict) -> list[TranscriptLine]:
        if not result["text"]:
            return []
        return [TranscriptLine(**result)]

    def transcribe(self, chunk: AudioChunk) -> list[TranscriptLine]:
        if self.recognizer is None or self.stream is None:
            raise RuntimeError("O modelo contínuo ainda não foi preparado.")
        if self.finished:
            raise RuntimeError("O reconhecimento contínuo já foi encerrado.")
        if chunk.sample_rate <= 0 or chunk.channels <= 0:
            raise ValueError("Formato de áudio inválido.")
        if self.sample_rate is None:
            self.sample_rate, self.channels = chunk.sample_rate, chunk.channels
        if (chunk.sample_rate != self.sample_rate or chunk.channels != self.channels
                or chunk.start_frame != self.received_frames):
            raise ValueError("O reconhecimento contínuo exige áudio sem lacunas e formato constante.")
        if len(chunk.pcm) % (2 * self.channels):
            raise ValueError("Bloco PCM contém uma amostra incompleta.")
        samples = np.frombuffer(chunk.pcm, dtype="<i2").astype(np.float32)
        samples = samples.reshape(-1, self.channels).mean(axis=1) / 32768.0
        self.received_frames += len(samples)
        # A reamostragem para 16 kHz mantém estado dentro do motor.
        self.stream.accept_waveform(self.sample_rate, samples)
        self._decode()
        result = self._result()
        if self.recognizer.is_endpoint(self.stream):
            lines = self._line(result)
            self.recognizer.reset(self.stream)
            self.partial = {"text": "", "start": result["end"], "end": result["end"]}
            return lines
        self.partial = result
        return []

    def finish(self) -> list[TranscriptLine]:
        if self.finished:
            return []
        self.finished = True
        if self.sample_rate is None:
            return []
        # Sempre usar a taxa original: trocar a taxa do stream é erro fatal na API nativa.
        self.stream.accept_waveform(self.sample_rate, np.zeros(self.sample_rate, np.float32))
        self.stream.input_finished()
        self._decode()
        result = self._result()
        self.partial = {"text": "", "start": result["end"], "end": result["end"]}
        return self._line(result)
