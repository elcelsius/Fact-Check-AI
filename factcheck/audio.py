"""Dispositivos WASAPI, medição PCM e segmentação sem perda de amostras."""

from dataclasses import dataclass
import io
import math
import wave

import numpy as np


@dataclass(frozen=True)
class AudioDevice:
    index: int
    name: str
    sample_rate: int
    channels: int
    is_default: bool = False


def loopback_devices() -> list[AudioDevice]:
    import pyaudiowpatch as pa

    with pa.PyAudio() as audio:
        try:
            default_index = int(audio.get_default_wasapi_loopback()["index"])
        except (OSError, ValueError, LookupError):
            default_index = -1
        return [
            AudioDevice(
                index=int(info["index"]),
                name=info["name"],
                sample_rate=int(info["defaultSampleRate"]),
                channels=int(info["maxInputChannels"]),
                is_default=int(info["index"]) == default_index,
            )
            for info in audio.get_loopback_device_info_generator()
            if info["maxInputChannels"] > 0
        ]


def pcm_levels(pcm: bytes) -> tuple[float, float]:
    """Retorna RMS em dBFS e pico normalizado para PCM16 intercalado."""
    if not pcm:
        return -120.0, 0.0
    samples = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0
    rms = float(np.sqrt(np.mean(samples * samples)))
    peak = float(np.max(np.abs(samples)))
    return max(-120.0, 20.0 * math.log10(max(rms, 1e-6))), peak


@dataclass(frozen=True)
class AudioChunk:
    start_frame: int
    pcm: bytes
    sample_rate: int
    channels: int
    final: bool = False

    @property
    def start(self) -> float:
        return self.start_frame / self.sample_rate

    @property
    def end(self) -> float:
        return self.start + len(self.pcm) / (2 * self.channels * self.sample_rate)

    def wav_buffer(self) -> io.BytesIO:
        result = io.BytesIO()
        with wave.open(result, "wb") as output:
            output.setnchannels(self.channels)
            output.setsampwidth(2)
            output.setframerate(self.sample_rate)
            output.writeframes(self.pcm)
        result.seek(0)
        return result


class PCMChunker:
    """Janelas de seis segundos com dois segundos de contexto compartilhado."""

    def __init__(self, sample_rate: int, channels: int,
                 seconds: float = 6.0, overlap: float = 2.0):
        if sample_rate <= 0 or channels <= 0 or not 0 <= overlap < seconds:
            raise ValueError("Formato de áudio ou janela inválidos.")
        self.sample_rate = sample_rate
        self.channels = channels
        self.frame_bytes = 2 * channels
        self.window_frames = round(seconds * sample_rate)
        self.step_frames = self.window_frames - round(overlap * sample_rate)
        if self.step_frames < 1:
            raise ValueError("A janela precisa avançar ao menos uma amostra.")
        self.buffer = bytearray()
        self.start_frame = 0

    def push(self, pcm: bytes) -> list[AudioChunk]:
        if len(pcm) % self.frame_bytes:
            raise ValueError("Bloco PCM contém uma amostra incompleta.")
        self.buffer.extend(pcm)
        chunks = []
        size = self.window_frames * self.frame_bytes
        while len(self.buffer) >= size:
            chunks.append(AudioChunk(self.start_frame, bytes(self.buffer[:size]),
                                     self.sample_rate, self.channels))
            del self.buffer[:self.step_frames * self.frame_bytes]
            self.start_frame += self.step_frames
        return chunks

    def finish(self) -> AudioChunk | None:
        if not self.buffer:
            return None
        chunk = AudioChunk(self.start_frame, bytes(self.buffer),
                           self.sample_rate, self.channels, final=True)
        self.buffer.clear()
        return chunk


class RollingChunker:
    """Começa cedo e mantém contexto à esquerda sem esperar uma janela inteira."""

    def __init__(self, sample_rate: int, channels: int, context_seconds: float = 6.0,
                 update_seconds: float = 3.0, first_seconds: float = 2.0):
        if (sample_rate <= 0 or channels <= 0 or not 0 < update_seconds <= context_seconds
                or not 0 < first_seconds <= context_seconds):
            raise ValueError("Formato ou intervalo de atualização inválidos.")
        self.sample_rate = sample_rate
        self.channels = channels
        self.frame_bytes = 2 * channels
        self.context_frames = round(context_seconds * sample_rate)
        self.step_frames = round(update_seconds * sample_rate)
        if self.step_frames < 1:
            raise ValueError("A atualização precisa avançar ao menos uma amostra.")
        self.buffer = bytearray()
        self.buffer_start = 0
        self.received_frames = 0
        self.next_end = round(first_seconds * sample_rate)
        if self.next_end < 1:
            raise ValueError("O primeiro trecho precisa conter ao menos uma amostra.")
        self.finished = False

    def push(self, pcm: bytes) -> list[AudioChunk]:
        if self.finished:
            raise RuntimeError("A segmentação já foi encerrada.")
        if len(pcm) % self.frame_bytes:
            raise ValueError("Bloco PCM contém uma amostra incompleta.")
        self.buffer.extend(pcm)
        self.received_frames += len(pcm) // self.frame_bytes
        result = []
        while self.next_end <= self.received_frames:
            start = max(0, self.next_end - self.context_frames)
            begin = (start - self.buffer_start) * self.frame_bytes
            end = (self.next_end - self.buffer_start) * self.frame_bytes
            result.append(AudioChunk(start, bytes(self.buffer[begin:end]),
                                     self.sample_rate, self.channels))
            self.next_end += self.step_frames
            keep_from = max(0, min(self.next_end - self.context_frames,
                                   self.received_frames - self.context_frames))
            drop = keep_from - self.buffer_start
            if drop > 0:
                del self.buffer[:drop * self.frame_bytes]
                self.buffer_start = keep_from
        return result

    def finish(self) -> AudioChunk | None:
        if self.finished:
            return None
        self.finished = True
        if not self.buffer:
            return None
        result = AudioChunk(self.buffer_start, bytes(self.buffer), self.sample_rate,
                            self.channels, final=True)
        self.buffer.clear()
        return result
