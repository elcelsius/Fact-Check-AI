"""Comparação local pela mesma captura WAV; nenhum trabalho editorial é iniciado."""

from datetime import datetime, timezone
from hashlib import sha256
from importlib.metadata import PackageNotFoundError, version
import json
import multiprocessing as mp
import os
from pathlib import Path
import platform
import queue
import sys
import time
import wave

from . import __version__
from .persistence import atomic_json
from .replay import inspect_replay, replay_device
from .reporting import statistics
from .session import CaptureSession
from .streaming import MODEL_FILES, MODEL_NAME

PROFILES = {"streaming-cpu": ("streaming", {}), "whisper-cpu": ("whisper", {}),
            "whisper-cuda": ("whisper", {"whisper_device": "cuda"})}


def audio_identity(path):
    path = Path(path).resolve()
    info = inspect_replay(path)
    file_digest, pcm_digest = sha256(), sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            file_digest.update(block)
    frames = 0
    with wave.open(str(path), "rb") as source:
        while block := source.readframes(source.getframerate()):
            pcm_digest.update(block)
            frames += len(block) // (2 * info["channels"])
    if frames != info["frames"]:
        raise ValueError("O WAV está incompleto; recupere uma cópia antes da comparação.")
    return {**info, "file_sha256": file_digest.hexdigest(), "pcm_sha256": pcm_digest.hexdigest()}


def preflight(root, engines, model):
    if not engines or len(set(engines)) != len(engines) or any(engine not in {"streaming", "whisper"} for engine in engines):
        raise ValueError("Escolha motores diferentes entre streaming e whisper.")
    if model not in {"tiny", "base", "small"}:
        raise ValueError("Escolha tiny, base ou small para Whisper.")
    for engine in engines:
        folder = Path(root) / "models" / (MODEL_NAME if engine == "streaming" else model)
        files = MODEL_FILES if engine == "streaming" else ("model.bin", "config.json", "tokenizer.json")
        if any(not (folder / name).is_file() or not (folder / name).stat().st_size for name in files):
            raise ValueError(f"Prepare o modelo {engine} antes da comparação. O ensaio não baixa modelos.")


def model_identity(root, engines, model):
    result = {}
    for engine in engines:
        folder = Path(root) / "models" / (MODEL_NAME if engine == "streaming" else model)
        files = MODEL_FILES if engine == "streaming" else ("model.bin", "config.json", "tokenizer.json", "vocabulary.txt")
        result[engine] = {}
        for name in files:
            path = folder / name
            if not path.is_file():
                continue
            digest = sha256()
            with path.open("rb") as source:
                while block := source.read(1024 * 1024):
                    digest.update(block)
            result[engine][name] = {"bytes": path.stat().st_size, "sha256": digest.hexdigest()}
    return result


def summarize(folder, wall_seconds, capture_offset, source):
    folder = Path(folder)
    metadata = json.loads((folder / "session.json").read_text(encoding="utf8"))
    events = [json.loads(line) for line in (folder / "events.jsonl").read_text(encoding="utf8").splitlines() if line.strip()]
    chunks = [row for row in events if row["kind"] == "transcription_chunk"]
    delivered = [row for row in events if row["kind"] == "transcript_delivered"]
    capture = next((row["elapsed_seconds"] for row in events if row["kind"] == "capture_finished"), None)
    first = next((row["elapsed_seconds"] for row in events if row["kind"] == "first_partial"), None)
    inference = [row.get("inference_seconds") for row in chunks]
    flush = [row["processing_seconds"] for row in events if row["kind"] == "transcription_flush"]
    complete_measurement = bool(chunks) and all(type(value) in (int, float) for value in inference)
    processing = sum(inference) + sum(flush) if complete_measurement else None
    result_audio = audio_identity(folder / "audio.wav")
    pcm_equal = all(result_audio[key] == source[key] for key in ("frames", "sample_rate", "channels", "pcm_sha256"))
    preparation = capture_offset
    return {
        "session_id": folder.name, "session_folder": str(folder.resolve()),
        "status": metadata["status"], "transcription_complete": metadata.get("transcription_complete", False),
        "engine": metadata.get("transcription_engine"), "model": metadata.get("model"),
        "compute": metadata.get("compute"), "cpu_threads": metadata.get("cpu_threads"),
        "settings": {key: metadata.get(key) for key in ("packet_seconds", "context_seconds", "first_seconds", "update_seconds",
                     "right_context_seconds", "beam_size", "endpoint_silence_seconds", "max_segment_seconds")},
        "issue_codes": [item["code"] for item in metadata.get("issues", [])], "pcm_matches_input": pcm_equal,
        "timing_seconds": {"total_including_preparation": wall_seconds, "preparation_and_setup": preparation,
            "capture": capture, "first_partial": first, "first_stabilized": delivered[0]["elapsed_seconds"] if delivered else None,
            "drain_after_capture": max(0, wall_seconds - preparation - capture) if capture is not None and preparation is not None else None,
            "inference_including_flush": processing, "streaming_flush": sum(flush) if flush else None,
            "chunk_inference": statistics(inference),
            "chunk_pipeline": statistics([row.get("processing_seconds") for row in chunks]),
            "chunk_delivery_lag": statistics([row.get("delivery_lag_seconds") for row in chunks]),
            "stabilized_delivery_lag": statistics([row.get("delivery_lag_seconds") for row in delivered])},
        "inference_to_audio_ratio": processing / source["duration"] if processing is not None else None,
        "maximum_logged_queue": statistics([row.get("queued_chunks") for row in chunks])["maximum"],
        "stable_segments": [json.loads(line) for line in (folder / "transcript.jsonl").read_text(encoding="utf8").splitlines() if line.strip()],
        "quality": {"human_reference": "not_provided", "word_error_rate": None, "approved_for_live_use": False},
    }


def run_trial(root, path, engine, model, emit=None, **options):
    """Executado em processo próprio pela comparação; fábrica real de captura."""
    source = audio_identity(path)
    started_at = time.perf_counter()
    capture_offset = None
    last_error = ""
    def observe(kind, data):
        nonlocal capture_offset, last_error
        if kind == "error":
            last_error = data["message"]
        if kind == "started":
            capture_offset = time.perf_counter() - started_at
            if emit:
                emit("session", data["folder"])
    session = CaptureSession(replay_device(path), Path(root), observe, replay_path=Path(path),
                             engine_name=engine, model_name=model, **options)
    try:
        session.run()
    except KeyboardInterrupt:
        session.cancel()
        raise
    elapsed = time.perf_counter() - started_at
    if session.folder is None:
        raise ValueError("O motor não iniciou a sessão; confira o modelo e o ambiente local. " + last_error)
    result = summarize(session.folder, elapsed, capture_offset, source)
    result["source_unchanged"] = audio_identity(path) == source
    return result


def _worker(root, path, engine, model, outputs, options):
    try:
        result = run_trial(root, path, engine, model, lambda kind, data: outputs.put((kind, data)), **options)
        outputs.put(("result", result))
    except (ValueError, RuntimeError, OSError) as exc:
        outputs.put(("error", str(exc)[:2000]))
    except Exception:
        outputs.put(("error", "O ensaio não terminou; confira os modelos e os arquivos da sessão informada."))


def isolated_trial(root, path, engine, model, timeout, progress, **options):
    context = mp.get_context("spawn")
    outputs = context.Queue()
    process = context.Process(target=_worker, args=(str(root), str(path), engine, model, outputs, options))
    process.start()
    began = time.monotonic()
    try:
        while time.monotonic() - began < timeout:
            try:
                kind, data = outputs.get(timeout=0.5)
            except queue.Empty:
                if not process.is_alive():
                    raise ValueError("O processo do motor foi interrompido; a sessão parcial pode exigir recuperação.")
                continue
            if kind == "session":
                progress(f"Sessão de ensaio: {data}")
            elif kind == "result":
                return data
            else:
                raise ValueError(data)
        raise ValueError("O ensaio excedeu o tempo limite; a sessão parcial pode exigir recuperação.")
    finally:
        process.join(0.5)
        if process.is_alive():
            process.terminate()
            process.join(3)
        outputs.close()
        outputs.join_thread()


def compare(path, root, output, profiles=("streaming-cpu", "whisper-cpu"), model="small", repeats=1, progress=print):
    path, root, output = Path(path).resolve(), Path(root).resolve(), Path(output).resolve()
    if type(repeats) is not int or not 1 <= repeats <= 5 or output.suffix.lower() != ".json" or output == path:
        raise ValueError("Use de uma a cinco repetições e um destino JSON diferente do áudio.")
    if output.exists():
        try:
            previous = json.loads(output.read_text(encoding="utf8"))
        except (ValueError, UnicodeDecodeError):
            previous = None
        if not isinstance(previous, dict) or previous.get("format") != "factcheck-asr-comparison":
            raise ValueError("O destino já contém outro arquivo. Escolha um novo relatório para preservar o original.")
    if not profiles or len(set(profiles)) != len(profiles) or any(profile not in PROFILES for profile in profiles):
        raise ValueError("Escolha perfis diferentes entre streaming-cpu, whisper-cpu e whisper-cuda.")
    engines = tuple(dict.fromkeys(PROFILES[profile][0] for profile in profiles))
    preflight(root, engines, model)
    source = audio_identity(path)
    models = model_identity(root, engines, model)
    packages = {}
    for name in ("sherpa-onnx", "faster-whisper", "ctranslate2", "nvidia-cublas-cu12", "nvidia-cudnn-cu12"):
        try:
            packages[name] = version(name)
        except PackageNotFoundError:
            packages[name] = None
    report = {"format": "factcheck-asr-comparison", "schema_version": 1, "app_version": __version__,
        "created_at": datetime.now(timezone.utc).isoformat(), "input": {"path": str(path), **source},
        "environment": {"python": sys.version.split()[0], "platform": platform.platform(), "processor": platform.processor(),
                        "logical_cpus": os.cpu_count(), "packages": packages}, "model_files": models,
        "method": {"paced": True, "audible_playback": False, "process_per_trial": True,
            "api_calls": 0, "triage_started": False, "repeats": repeats, "order": [], "profiles": list(profiles)},
        "status": "running", "trials": [], "limitations": [
            "Primeira prévia e primeiro texto estabilizado são medidas distintas; Whisper não fornece prévia neste aplicativo.",
            "Atraso dos pacotes não equivale à latência de cada palavra. A fila é o máximo observado nos registros.",
            "Razão de inferência abaixo de um não garante ausência de atraso em outro conteúdo ou com triagem simultânea.",
            "Modelos e caches do sistema podem estar aquecidos; o hardware e a carga de outros programas não são controlados.",
            "As transcrições são automáticas, sem referência humana; velocidade não mede fidelidade ou veracidade."]}
    output.parent.mkdir(parents=True, exist_ok=True)
    atomic_json(output, report)
    try:
        for repeat in range(repeats):
            for profile in profiles if repeat % 2 == 0 else tuple(reversed(profiles)):
                engine, options = PROFILES[profile]
                if audio_identity(path) != source:
                    raise ValueError("O áudio de entrada mudou; a comparação foi interrompida.")
                if model_identity(root, engines, model) != models:
                    raise ValueError("Os modelos mudaram; a comparação foi interrompida para preservar a referência do ensaio.")
                progress(f"Repetição {repeat+1}/{repeats}: {profile} · entrada silenciosa no ritmo original.")
                report["method"]["order"].append(profile)
                trial = isolated_trial(root, path, engine, model, max(120, source["duration"] * 5 + 60), progress,
                                       **options)
                report["trials"].append({"repeat": repeat + 1, "profile": profile, **trial})
                atomic_json(output, report)
                progress(json.dumps({key: trial[key] for key in ("engine", "compute", "transcription_complete", "inference_to_audio_ratio", "maximum_logged_queue")}, ensure_ascii=False))
                if not trial["source_unchanged"] or not trial["pcm_matches_input"]:
                    raise ValueError("A integridade do áudio não foi confirmada; confira os arquivos antes de continuar.")
        report["status"] = "completed" if all(row["transcription_complete"] for row in report["trials"]) else "incomplete"
    except BaseException:
        report["status"] = "interrupted"
        raise
    finally:
        try:
            report["input_unchanged"] = audio_identity(path) == source
        except (OSError, ValueError, EOFError, wave.Error):
            report["input_unchanged"] = False
        if not report["input_unchanged"]:
            report["status"] = "interrupted"
        try:
            report["models_unchanged"] = model_identity(root, engines, model) == models
        except OSError:
            report["models_unchanged"] = False
        if not report["models_unchanged"]:
            report["status"] = "interrupted"
        atomic_json(output, report)
    return report
