"""Sessão local: captura independente da fila de transcrição."""

from dataclasses import asdict
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import queue
import threading
import time
from typing import Callable
import uuid
import wave

from . import __version__
from .audio import AudioChunk, AudioDevice, PCMChunker, RollingChunker, pcm_levels
from .paragraphs import ParagraphAssembler, ParagraphConfig
from .review import Debate, ReviewStore
from .persistence import atomic_json
from .streaming import MODEL_NAME, MODEL_REVISION, PACKET_SECONDS, StreamingTranscriber
from .transcription import LocalTranscriber


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class CaptureSession:
    def __init__(self, device: AudioDevice, project_root: Path,
                 emit: Callable[[str, dict], None] | None = None,
                 transcribe: bool = True, model_name: str = "small",
                 engine_name: str = "streaming", paragraph_config: ParagraphConfig | None = None,
                 debate: Debate | None = None, replay_path: Path | None = None, whisper_device: str = "cpu"):
        if engine_name not in {"streaming", "whisper"}:
            raise ValueError("Motor de transcrição desconhecido.")
        if whisper_device not in {"cpu", "cuda"} or (engine_name == "streaming" and whisper_device != "cpu"):
            raise ValueError("A opção NVIDIA está disponível somente para Whisper.")
        self.device = device
        self.root = project_root
        self.emit = emit or (lambda kind, data: None)
        self.transcribe = transcribe
        self.model_name = model_name
        self.engine_name = engine_name
        self.whisper_device = whisper_device
        self.paragraph_config = paragraph_config or ParagraphConfig()
        self.debate = (debate or Debate()).validate()
        self.replay_path = Path(replay_path).resolve() if replay_path is not None else None
        self.result_lock = threading.RLock()
        self.stop_event = threading.Event()
        self.cancel_event = threading.Event()
        self.pause_event = threading.Event()
        self.stop_requested_at: float | None = None
        self.folder: Path | None = None
        self.metadata: dict = {}

    def stop(self) -> None:
        if not self.stop_event.is_set():
            self.stop_requested_at = time.perf_counter()
            self.stop_event.set()

    def cancel(self) -> None:
        """Interrompe a captura e invalida os resultados ainda em processamento."""
        with self.result_lock:
            self.cancel_event.set()
        self.stop()

    def set_paused(self, paused):
        if type(paused) is not bool or self.folder is None or self.stop_event.is_set() or self.metadata.get("status") != "recording":
            raise ValueError("A pausa exige uma captura em andamento.")
        self.pause_event.set() if paused else self.pause_event.clear()

    def run(self, seconds: float | None = None) -> bool:
        if seconds is not None and seconds <= 0:
            raise ValueError("A duração precisa ser positiva.")
        succeeded = False
        try:
            if self.stop_event.is_set():
                return False
            engine = None
            if self.transcribe:
                self.emit("status", {"text": "Preparando Whisper NVIDIA e aquecendo o motor antes da captura…"
                          if self.whisper_device == "cuda" else "Preparando transcrição local…"})
                engine = (StreamingTranscriber(self.root) if self.engine_name == "streaming"
                          else LocalTranscriber(self.root, self.model_name, **({"device": "cuda"} if self.whisper_device == "cuda" else {})))
                engine.prepare()
            if not self.stop_event.is_set():
                succeeded = self._record(engine, seconds)
        except Exception as exc:
            self.emit("error", {"message": str(exc)})
        finally:
            self.emit("done", {"folder": str(self.folder) if self.folder else None,
                               "success": succeeded, "cancelled": self.cancel_event.is_set()})
        return succeeded

    def _record(self, engine: LocalTranscriber | StreamingTranscriber | None,
                seconds: float | None) -> bool:
        if self.replay_path is not None:
            from .replay import WaveBackend
            pa = WaveBackend(self.replay_path, self.stop)
            if (pa.info["sample_rate"],pa.info["channels"]) != (self.device.sample_rate,self.device.channels):
                raise ValueError("O formato do WAV mudou antes do ensaio. Selecione o arquivo novamente.")
        else:
            import pyaudiowpatch as pa

        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self.folder = self.root / "recordings" / f"{stamp}_{uuid.uuid4().hex[:8]}"
        self.folder.mkdir(parents=True, exist_ok=False)
        streaming = self.engine_name == "streaming"
        self.metadata = {
            "schema_version": 5, "app_version": __version__, "owner_pid": os.getpid(),
            "input_kind": "wav_replay" if self.replay_path else "system_loopback",
            **({"replay": pa.info} if self.replay_path else {}),
            "session_id": self.folder.name, "started_at": utc_now(),
            "status": "recording", "device": asdict(self.device),
            "debate": asdict(self.debate),
            "audio_format": "PCM16", "language": "pt-BR" if streaming else "pt",
            "transcription_engine": ("sherpa-onnx" if streaming else "faster-whisper") if engine else None,
            "model": (MODEL_NAME if streaming else self.model_name) if engine else None,
            "model_revision": MODEL_REVISION if engine and streaming else None,
            "compute": ("cuda/int8_float16" if not streaming and self.whisper_device == "cuda" else "cpu/int8") if engine else None,
            "cpu_threads": getattr(engine, "cpu_threads", None) if type(getattr(engine, "cpu_threads", None)) is int else None,
            "packet_seconds": PACKET_SECONDS if streaming else None,
            "context_seconds": None if streaming else 6,
            "first_seconds": None if streaming else 2,
            "update_seconds": PACKET_SECONDS if streaming else 3,
            "right_context_seconds": None if streaming else 0.5,
            "beam_size": None if streaming else 1,
            "endpoint_silence_seconds": 0.8 if streaming else None,
            "max_segment_seconds": 15 if streaming else None,
            "transcription_review_status": "automatico_nao_revisado",
            "paragraphing": {"algorithm": "regras_pt_v1", **asdict(self.paragraph_config)},
            "frames": 0, "transcript_lines": 0, "paragraph_count": 0,
            "cancelled_chunks": 0, "issues": [], "pause_intervals": [],
        }
        metadata_path = self.folder / "session.json"
        atomic_json(metadata_path, self.metadata)
        review_store = ReviewStore(self.folder)
        packets: queue.Queue = queue.Queue(maxsize=512)
        jobs: queue.Queue[AudioChunk | None] = queue.Queue(maxsize=50 if streaming else 12)
        overflow = threading.Event()
        transcription_failed = threading.Event()
        chunker = (PCMChunker(self.device.sample_rate, self.device.channels,
                              seconds=PACKET_SECONDS, overlap=0) if streaming else
                   RollingChunker(self.device.sample_rate, self.device.channels))
        log_lock = threading.Lock()
        frame_bytes = self.device.channels * 2
        capture_error = None
        capture_started: float | None = None
        frames = 0
        last_meter = 0.0
        adc_origin = None
        paragraphs = ParagraphAssembler(self.paragraph_config)
        paragraph_tail = 0
        last_paragraph_id = None
        first_partial_logged = False

        with (self.folder / "events.jsonl").open("w", encoding="utf-8") as event_log, \
                (self.folder / "transcript.jsonl").open("w", encoding="utf-8") as transcript, \
                (self.folder / "transcript.txt").open("w", encoding="utf-8") as plain_text, \
                (self.folder / "paragraphs.jsonl").open("w", encoding="utf-8") as paragraph_log, \
                (self.folder / "paragraphs.txt").open("w", encoding="utf-8") as paragraph_text:

            def event(kind: str, data: dict) -> None:
                with log_lock:
                    event_log.write(json.dumps({"at": utc_now(), "kind": kind, **data},
                                               ensure_ascii=False) + "\n")
                    event_log.flush()
                self.emit(kind, data)

            def issue(code: str, message: str, **extra) -> None:
                record = {"code": code, "message": message, **extra}
                self.metadata["issues"].append(record)
                event("warning", record)

            def save_paragraphs(updates: list[dict]) -> None:
                nonlocal paragraph_tail, last_paragraph_id
                for data in updates:
                    gaps = [{"start": max(gap["start"], data["start"]), "end": min(gap["end"] if gap["end"] is not None else frames/self.device.sample_rate, data["end"]), "reason": "operator_pause"}
                            for gap in self.metadata["pause_intervals"] if gap["start"] < data["end"] and (gap["end"] is None or gap["end"] > data["start"])]
                    gaps = [gap for gap in gaps if gap["end"] > gap["start"]]
                    if gaps: data = {**data, "audio_gaps": gaps}
                    paragraph_log.write(json.dumps(data, ensure_ascii=False) + "\n")
                    paragraph_log.flush()
                    if data["paragraph_id"] != last_paragraph_id:
                        paragraph_text.seek(0, 2)
                        paragraph_tail = paragraph_text.tell()
                        last_paragraph_id = data["paragraph_id"]
                    paragraph_text.seek(paragraph_tail)
                    speaker = f" · {data['speaker']}" if data["speaker"] else ""
                    paragraph_text.write(f"[{data['start']:08.2f} → {data['end']:08.2f}]{speaker}\n{data['text']}\n\n")
                    paragraph_text.truncate()
                    paragraph_text.flush()
                    self.metadata["paragraph_count"] = paragraphs.count
                    review_store.ingest(data)
                    self.emit("paragraph", data)

            def publish(lines) -> None:
                with self.result_lock:
                    if self.cancel_event.is_set() or transcription_failed.is_set():
                        return
                    for line in lines:
                        record = {"sequence": self.metadata["transcript_lines"] + 1,
                                  **line.to_dict(), "audio_file": "audio.wav"}
                        transcript.write(json.dumps(record, ensure_ascii=False) + "\n")
                        transcript.flush()
                        plain_text.write(f"[{line.start:08.2f} → {line.end:08.2f}] {line.text}\n")
                        plain_text.flush()
                        self.metadata["transcript_lines"] += 1
                        if capture_started is not None:
                            delivered = round(time.perf_counter() - capture_started, 6)
                            event("transcript_delivered", {"sequence": record["sequence"], "start": line.start,
                                  "end": line.end, "elapsed_seconds": delivered,
                                  "delivery_lag_seconds": round(delivered - line.end, 6)})
                        self.emit("transcript", record)
                        save_paragraphs(paragraphs.add(line, record["sequence"]))

            def transcribe_jobs() -> None:
                nonlocal first_partial_logged
                previous_partial = ""
                while True:
                    chunk = jobs.get()
                    try:
                        if chunk is None:
                            if streaming and not self.cancel_event.is_set() and not transcription_failed.is_set():
                                before = time.perf_counter()
                                lines = engine.finish()
                                flush_seconds = time.perf_counter() - before
                                publish(lines)
                                event("transcription_flush", {"processing_seconds": round(flush_seconds, 6),
                                      "elapsed_seconds": round(time.perf_counter() - capture_started, 6)})
                                self.emit("partial", {"text": ""})
                            return
                        if self.cancel_event.is_set():
                            self.metadata["cancelled_chunks"] += 1
                            continue
                        if transcription_failed.is_set():
                            continue
                        before = time.perf_counter()
                        lines = engine.transcribe(chunk)
                        inference_seconds = time.perf_counter() - before
                        if self.cancel_event.is_set():
                            self.metadata["cancelled_chunks"] += 1
                            continue
                        publish(lines)
                        if streaming:
                            with self.result_lock:
                                if not self.cancel_event.is_set() and not transcription_failed.is_set():
                                    partial = engine.partial
                                    if partial["text"] != previous_partial:
                                        if partial["text"] and not first_partial_logged:
                                            event("first_partial", {"elapsed_seconds": round(time.perf_counter() - capture_started, 6)})
                                            first_partial_logged = True
                                        self.emit("partial", {**partial, "recognition_status": "provisorio",
                                                              "review_status": "automatico_nao_revisado"})
                                        previous_partial = partial["text"]
                        event("transcription_chunk", {
                            "start": chunk.start, "end": chunk.end,
                            "processing_seconds": round(time.perf_counter() - before, 3),
                            "inference_seconds": round(inference_seconds, 6),
                            "queued_chunks": jobs.qsize(),
                            "delivery_lag_seconds": round(max(0, time.perf_counter() - capture_started -
                                (chunk.end if streaming or chunk.final else chunk.end - 0.5)), 3),
                        })
                    except Exception as exc:
                        if streaming:
                            transcription_failed.set()
                            self.emit("partial", {"text": ""})
                        issue("transcription_error", str(exc),
                              start=chunk.start if chunk else None, end=chunk.end if chunk else None)
                        if chunk is None:
                            return
                    finally:
                        jobs.task_done()

            worker = None
            if engine:
                worker = threading.Thread(target=transcribe_jobs, name="transcription", daemon=True)
                worker.start()

            def enqueue(chunk: AudioChunk) -> None:
                if not engine or self.cancel_event.is_set() or transcription_failed.is_set():
                    return
                try:
                    jobs.put_nowait(chunk)
                except queue.Full:
                    if streaming:
                        # Perder um pacote invalida o estado temporal do reconhecimento.
                        # Manter a captura íntegra e interromper apenas a transcrição.
                        transcription_failed.set()
                        self.emit("partial", {"text": ""})
                    issue("transcription_backlog", "Fila de transcrição cheia; áudio preservado para reprocessamento.",
                          start=chunk.start, end=chunk.end)

            def callback(data, frame_count, timing, flags):
                try:
                    packets.put_nowait((data, timing.get("input_buffer_adc_time", 0),
                                        flags, time.perf_counter(), self.pause_event.is_set()))
                except queue.Full:
                    overflow.set()
                    return None, pa.paAbort
                return None, pa.paContinue

            try:
                with (self.folder / "audio.wav").open("wb") as audio_file, wave.open(audio_file, "wb") as wav:
                    wav.setnchannels(self.device.channels)
                    wav.setsampwidth(2)
                    wav.setframerate(self.device.sample_rate)

                    last_flush = time.perf_counter()

                    def write_pcm(data: bytes, paused=False) -> None:
                        nonlocal frames, last_meter, last_flush
                        if not data: return
                        pauses = self.metadata["pause_intervals"]
                        edge = False
                        if paused:
                            data = bytes(len(data))
                            if not pauses or pauses[-1]["end"] is not None:
                                pauses.append({"start": frames/self.device.sample_rate, "end": None, "reason": "operator_pause"})
                                edge = True
                                issue("operator_pause", "Pausa solicitada: áudio ignorado e intervalo marcado. O vídeo continua no player.")
                                event("capture_paused", {"start": pauses[-1]["start"]})
                        elif pauses and pauses[-1]["end"] is None:
                            pauses[-1]["end"] = frames/self.device.sample_rate
                            edge = True
                            event("capture_resumed", {"end": pauses[-1]["end"]})
                        if edge:
                            # Guardar a omissão antes do PCM: uma queda não deve
                            # transformar a pausa em silêncio sem explicação.
                            self.metadata.update(frames=frames, audio_omitted_by_operator=True)
                            atomic_json(metadata_path, self.metadata)
                        # Atualizar o cabeçalho a cada pacote; disponibilizar os
                        # buffers ao sistema ao menos a cada segundo com amostras.
                        wav.writeframes(data)
                        if time.perf_counter() - last_flush >= 1:
                            audio_file.flush()
                            last_flush = time.perf_counter()
                        frames += len(data) // frame_bytes
                        for chunk in chunker.push(data):
                            enqueue(chunk)
                        now = time.perf_counter()
                        if now - last_meter >= 0.15:
                            level, peak = pcm_levels(data)
                            self.emit("level", {"dbfs": level, "peak": peak,
                                               "audio_seconds": frames / self.device.sample_rate,
                                               "queued_chunks": jobs.qsize()})
                            last_meter = now

                    def silence(frame_count: int, paused=False) -> None:
                        while frame_count > 0:
                            count = min(frame_count, self.device.sample_rate)
                            write_pcm(bytes(count * frame_bytes), paused)
                            frame_count -= count

                    def consume(packet) -> None:
                        nonlocal adc_origin
                        data, adc_time, flags, received, paused = packet
                        if flags & pa.paInputOverflow:
                            raise RuntimeError("O dispositivo perdeu amostras de áudio. A gravação foi interrompida.")
                        if flags:
                            issue("device_status", "O dispositivo sinalizou uma alteração de áudio.", flags=flags)
                        duration = len(data) / (frame_bytes * self.device.sample_rate)
                        if adc_time > 0:
                            if adc_origin is None:
                                adc_origin = adc_time - max(0, received - capture_started - duration)
                            expected = round((adc_time - adc_origin) * self.device.sample_rate)
                            gap = expected - frames
                            # WASAPI pode suspender callbacks durante silêncio. Preservar a linha do tempo.
                            if gap > self.device.sample_rate * 0.10:
                                event("audio_padding", {"start": frames / self.device.sample_rate,
                                                        "duration": gap / self.device.sample_rate,
                                                        "reason": "Intervalo sem amostras do dispositivo; preenchido com silêncio."})
                                silence(gap, paused)
                            elif gap < -self.device.sample_rate * 0.25:
                                raise RuntimeError("O relógio do dispositivo de áudio mudou. Inicie uma nova sessão.")
                        write_pcm(data, paused)

                    with pa.PyAudio() as audio:
                        info = audio.get_device_info_by_index(self.device.index)
                        if not info.get("isLoopbackDevice") or info["name"] != self.device.name:
                            raise RuntimeError("A saída de áudio mudou. Atualize a lista de dispositivos.")
                        with audio.open(format=pa.paInt16, channels=self.device.channels,
                                        rate=self.device.sample_rate, input=True,
                                        input_device_index=self.device.index, frames_per_buffer=1024,
                                        stream_callback=callback, start=False) as stream:
                            capture_started = time.perf_counter()
                            self.metadata["capture_started_at"] = utc_now()
                            stream.start_stream()
                            event("started", {"folder": str(self.folder), "device": self.device.name,
                                              "capture_started_at": self.metadata["capture_started_at"],
                                              "input_kind": self.metadata["input_kind"]})
                            while not self.stop_event.is_set():
                                if seconds is not None and time.perf_counter() - capture_started >= seconds:
                                    self.stop()
                                    break
                                if overflow.is_set():
                                    raise RuntimeError("A fila de captura excedeu o limite. A gravação foi interrompida.")
                                try:
                                    consume(packets.get(timeout=0.10))
                                except queue.Empty:
                                    if not self.stop_event.is_set() and not stream.is_active():
                                        raise RuntimeError(getattr(stream,"error",None) or "A saída de áudio foi desconectada ou interrompida.")
                                    if time.perf_counter() - last_meter > 0.5:
                                        self.emit("level", {"dbfs": -120, "peak": 0,
                                                           "audio_seconds": frames / self.device.sample_rate,
                                                           "queued_chunks": jobs.qsize()})
                            stream.stop_stream()
                            while not packets.empty():
                                consume(packets.get_nowait())
                    elapsed = (self.stop_requested_at or time.perf_counter()) - capture_started
                    remaining = round(elapsed * self.device.sample_rate) - frames
                    if not self.replay_path and remaining > self.device.sample_rate * 0.10:
                        silence(remaining, self.pause_event.is_set())
            except KeyboardInterrupt:
                self.stop()
            except Exception as exc:
                capture_error = str(exc)
                issue("capture_error", capture_error)
            finally:
                if self.metadata["pause_intervals"] and self.metadata["pause_intervals"][-1]["end"] is None:
                    self.metadata["pause_intervals"][-1]["end"] = frames/self.device.sample_rate
                self.metadata["audio_omitted_by_operator"] = bool(self.metadata["pause_intervals"])
                if capture_started is not None:
                    event("capture_finished", {"elapsed_seconds": round(time.perf_counter() - capture_started, 6),
                          "audio_seconds": frames / self.device.sample_rate, "capture_failed": capture_error is not None})
                self.metadata.update(status="finalizing", frames=frames)
                try:
                    atomic_json(metadata_path, self.metadata)
                except OSError as exc:
                    issue("metadata_error", str(exc))
                final_chunk = chunker.finish()
                if final_chunk and not self.cancel_event.is_set():
                    enqueue(final_chunk)
                if worker:
                    self.emit("status", {"text": "Cancelando pendências e preservando os arquivos…"
                                         if self.cancel_event.is_set() else
                                         "Áudio salvo. Finalizando os trechos de transcrição…"})
                    jobs.put(None)
                    worker.join()
                with self.result_lock:
                    end_reason = ("cancelamento" if self.cancel_event.is_set() else
                                  "captura_interrompida" if capture_error else
                                  "transcricao_interrompida" if any(item["code"] in {
                                      "transcription_error", "transcription_backlog"
                                  } for item in self.metadata["issues"]) else "encerramento")
                    save_paragraphs(paragraphs.finish(end_reason))
                self.metadata.update({
                    "status": "cancelled" if self.cancel_event.is_set() else
                              "capture_error" if capture_error else "completed",
                    "ended_at": utc_now(), "frames": frames,
                    "duration_seconds": round(frames / self.device.sample_rate, 3),
                    "transcription_complete": bool(engine) and not self.cancel_event.is_set() and not any(
                        item["code"] in {"transcription_backlog", "transcription_error", "capture_error"}
                        for item in self.metadata["issues"]),
                })
                if self.cancel_event.is_set():
                    event("cancelled", {"cancelled_chunks": self.metadata["cancelled_chunks"],
                                        "files_preserved": True})
                atomic_json(metadata_path, self.metadata)
            if capture_error and not self.cancel_event.is_set():
                self.emit("error", {"message": capture_error})
            return capture_error is None and not self.cancel_event.is_set()
