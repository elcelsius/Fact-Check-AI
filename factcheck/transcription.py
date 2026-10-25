"""Motor local substituível e união temporal das janelas de áudio."""

from dataclasses import asdict, dataclass
import os
from pathlib import Path
from typing import Any

from .audio import AudioChunk, pcm_levels


@dataclass(frozen=True)
class TranscriptLine:
    start: float
    end: float
    text: str
    speaker: str | None = None
    review_status: str = "automatico_nao_revisado"
    recognition_status: str = "estabilizado"

    def to_dict(self) -> dict:
        return asdict(self)


class TranscriptMerger:
    """Confirma faixas temporais uma vez, mantendo a cauda para a próxima janela."""

    def __init__(self, right_context: float = 1.0):
        self.right_context = right_context
        self.committed_until = -1.0

    def consume(self, chunk: AudioChunk, segments: list[Any]) -> list[TranscriptLine]:
        cutoff = chunk.end if chunk.final else chunk.end - self.right_context
        previous = self.committed_until
        result = []
        for segment in segments:
            selected = []
            for word in segment.words or []:
                start = chunk.start + word.start
                end = chunk.start + word.end
                midpoint = (start + end) / 2
                if previous <= midpoint < cutoff and chunk.start <= start <= end <= chunk.end + 0.05:
                    selected.append((start, min(end, chunk.end), word.word))
            text = "".join(word[2] for word in selected).strip()
            if text:
                result.append(TranscriptLine(
                    start=float(round(selected[0][0], 3)),
                    end=float(round(selected[-1][1], 3)),
                    text=text,
                ))
        self.committed_until = max(previous, cutoff)
        return result


class LocalTranscriber:
    def __init__(self, project_root: Path, model_name: str = "small", *,
                 beam_size: int = 1, right_context: float = 0.5, device: str = "cpu"):
        if model_name not in {"tiny", "base", "small"}:
            raise ValueError("Modelo local não suportado pelo protótipo.")
        if device not in {"cpu", "cuda"}:
            raise ValueError("Escolha CPU ou NVIDIA para Whisper.")
        self.root = project_root
        self.model_name = model_name
        self.beam_size = beam_size
        self.device = device
        self.compute = "cuda/int8_float16" if device == "cuda" else "cpu/int8"
        self.cpu_threads = min(8, max(1, (os.cpu_count() or 4) - 2))
        self.dll_handles, self.native_handles = [], []
        self.model = None
        self.merger = TranscriptMerger(right_context=right_context)

    def prepare(self) -> Path:
        # Caches pertencem ao projeto. O áudio permanece local.
        os.environ.setdefault("HF_HOME", str(self.root / ".cache" / "huggingface"))
        os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
        if self.device == "cuda":
            from .cuda_runtime import whisper_cuda_libraries
            self.dll_handles, self.native_handles = whisper_cuda_libraries()
            os.environ.setdefault("CUDA_CACHE_PATH", str(self.root / ".cache/cuda"))
            Path(os.environ["CUDA_CACHE_PATH"]).mkdir(parents=True, exist_ok=True)
        from faster_whisper import WhisperModel
        from faster_whisper.utils import download_model

        model_path = self.root / "models" / self.model_name
        required = ("model.bin", "config.json", "tokenizer.json")
        if not all((model_path / name).is_file() for name in required):
            download_model(self.model_name, output_dir=str(model_path),
                           cache_dir=str(self.root / ".cache" / "huggingface"))
        self.model = WhisperModel(
            str(model_path), device=self.device, compute_type="int8_float16" if self.device == "cuda" else "int8",
            cpu_threads=self.cpu_threads,
        )
        if self.device == "cuda":
            # Inicializar kernels antes de abrir a captura; esta amostra não é persistida.
            import numpy as np
            segments, _ = self.model.transcribe(np.zeros(16000, np.float32), language="pt", task="transcribe",
                beam_size=1, temperature=0, word_timestamps=True, vad_filter=False, condition_on_previous_text=False)
            list(segments)
        return model_path

    def transcribe(self, chunk: AudioChunk) -> list[TranscriptLine]:
        if self.model is None:
            raise RuntimeError("O modelo de transcrição ainda não foi preparado.")
        level, _ = pcm_levels(chunk.pcm)
        if level < -90:
            return self.merger.consume(chunk, [])
        segments, _ = self.model.transcribe(
            chunk.wav_buffer(), language="pt", task="transcribe",
            beam_size=self.beam_size, temperature=0, word_timestamps=True,
            vad_filter=True, vad_parameters={"min_silence_duration_ms": 500},
            condition_on_previous_text=False,
        )
        return self.merger.consume(chunk, list(segments))
