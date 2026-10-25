"""Diagnóstico de retomada e cópia recuperada do WAV, sem alterar originais."""

import hashlib
import json
import os
from pathlib import Path
import struct
import tempfile
import threading
import uuid
import wave

from .review import now, process_alive


SAFE_STATES = {"completed", "cancelled", "capture_error", "interrupted"}
STATE_NAMES = {"completed": "Captura encerrada", "cancelled": "Captura cancelada",
               "capture_error": "Captura encerrada com erro", "interrupted": "Captura interrompida sem finalização",
               "active": "Captura ou finalização em processo ativo",
               "unknown": "Estado da captura não confirmado"}


def capture_state(folder):
    try:
        data = json.loads((Path(folder) / "session.json").read_text(encoding="utf8"))
        if not isinstance(data, dict):
            raise ValueError
    except (OSError, UnicodeDecodeError, ValueError):
        return "unknown", "session.json não pôde ser lido. Os registros já existentes no banco podem ser consultados."
    status = data.get("status")
    if not isinstance(status, str):
        return "unknown", "Os metadados não informam como a captura terminou."
    if status in {"completed", "cancelled", "capture_error", "interrupted"}:
        return status, ""
    if status in {"recording", "finalizing"}:
        owner = data.get("owner_pid")
        if type(owner) is int and 0 < owner <= 0xFFFFFFFF:
            return ("active" if process_alive(owner) else "interrupted"), ""
        return "unknown", "Sessão antiga sem identificação do processo. Confirme a origem antes de qualquer reparo."
    return "unknown", "Os metadados não informam como a captura terminou."


def inspect_audio(folder):
    path = Path(folder) / "audio.wav"
    try:
        with path.open("rb") as stream:
            stamp = os.fstat(stream.fileno())
            header = stream.read(44)
    except FileNotFoundError:
        return {"state": "missing", "message": "Áudio não encontrado."}
    except OSError:
        return {"state": "unsupported", "message": "Não foi possível ler o áudio."}
    try:
        riff, declared, kind, fmt, fmt_size, encoding, channels, rate, byte_rate, align, bits, data, size = struct.unpack(
            "<4sI4s4sIHHIIHH4sI", header)
        if (riff != b"RIFF" or kind != b"WAVE" or fmt != b"fmt " or fmt_size != 16 or encoding != 1
                or data != b"data" or bits != 16 or not 1 <= channels <= 32 or not 1 <= rate <= 384000
                or align != channels * 2 or byte_rate != rate * align):
            raise ValueError
    except (struct.error, ValueError):
        return {"state": "unsupported", "message": "Formato diferente do WAV PCM16 da captura; reparo automático indisponível."}
    available = stamp.st_size - 44
    frames, dropped = divmod(available, align)
    complete = declared + 8 == stamp.st_size and size == available and not dropped
    fingerprint = hashlib.sha256(f"{stamp.st_size}:{stamp.st_mtime_ns}:{header.hex()}".encode()).hexdigest()[:24]
    return {"state": "ok" if complete else "repairable", "frames": frames, "sample_rate": rate,
            "channels": channels, "frame_bytes": align, "duration": frames / rate,
            "dropped_bytes": dropped, "file_size": stamp.st_size, "fingerprint": fingerprint,
            "message": "WAV legível." if complete else "Cabeçalho ou última amostra incompletos; é possível criar uma cópia dos dados disponíveis."}


def recovered_path(folder, info):
    return Path(folder) / "recovered" / f"audio-{info['fingerprint']}.wav"


def playback_path(folder, info=None):
    info = info or inspect_audio(folder)
    if info["state"] == "ok":
        return Path(folder) / "audio.wav"
    if info["state"] == "repairable":
        path = recovered_path(folder, info)
        try:
            with wave.open(str(path), "rb") as wav:
                if (wav.getnframes() == info["frames"] and wav.getnchannels() == info["channels"]
                        and wav.getframerate() == info["sample_rate"] and wav.getsampwidth() == 2
                        and path.stat().st_size == 44 + info["frames"] * info["frame_bytes"]):
                    return path
        except (OSError, EOFError, wave.Error):
            pass
    raise ValueError("Áudio indisponível para reprodução. Consulte Estado da sessão para verificar a recuperação.")


def recover_audio(review, cancelled=None, commit_lock=None):
    state, _ = capture_state(review.folder)
    if state not in SAFE_STATES:
        raise ValueError("O processo da captura ainda está ativo ou não pôde ser confirmado. Reparo bloqueado.")
    info = inspect_audio(review.folder)
    if info["state"] != "repairable" or not info["frames"]:
        raise ValueError("Não há amostras recuperáveis neste formato de áudio.")
    directory = review.folder / "recovered"
    directory.mkdir(exist_ok=True)
    target = recovered_path(review.folder, info)
    temporary = None

    def check():
        if cancelled and cancelled.is_set():
            raise InterruptedError("Recuperação cancelada; áudio original preservado.")

    try:
        check()
        with (review.folder / "audio.wav").open("rb") as source, tempfile.NamedTemporaryFile(
                mode="w+b", dir=directory, prefix=".audio-", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            with wave.open(stream, "wb") as wav:
                wav.setparams((info["channels"], 2, info["sample_rate"], 0, "NONE", "not compressed"))
                source.seek(44)
                remaining = info["frames"] * info["frame_bytes"]
                while remaining:
                    check()
                    chunk = source.read(min(1024 * 1024, remaining))
                    if not chunk:
                        raise ValueError("O áudio mudou durante a cópia. Atualize o diagnóstico e tente novamente.")
                    wav.writeframesraw(chunk)
                    remaining -= len(chunk)
            stream.flush()
            os.fsync(stream.fileno())
        with commit_lock or threading.RLock():
            check()
            if inspect_audio(review.folder) != info or capture_state(review.folder)[0] not in SAFE_STATES:
                raise ValueError("A sessão mudou durante a cópia. A recuperação não foi aplicada.")
            os.replace(temporary, target)
        with review.connection() as db:
            review._audit(db, "audio_recovered", {"at": now(), "path": str(target.relative_to(review.folder)),
                          "frames": info["frames"], "dropped_bytes": info["dropped_bytes"],
                          "source_fingerprint": info["fingerprint"]})
        return target
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def inspect_session(review, warnings=()):
    state, notice = capture_state(review.folder)
    audio = inspect_audio(review.folder)
    sources = review.sources()
    with review.connection() as db:
        triage = db.execute("SELECT COUNT(*) FROM analyses WHERE status='interrupted'").fetchone()[0]
        has_research = db.execute("SELECT 1 FROM sqlite_master WHERE name='research_jobs'").fetchone()
        research = db.execute("SELECT COUNT(*) FROM research_jobs WHERE status='interrupted'").fetchone()[0] if has_research else 0
        running = db.execute("SELECT COUNT(*) FROM analyses WHERE status='running'").fetchone()[0]
        if has_research:
            running += db.execute("SELECT COUNT(*) FROM research_jobs WHERE status='running'").fetchone()[0]
    playable = False
    try:
        playable = playback_path(review.folder, audio).is_file()
    except ValueError:
        pass
    return {"state": state, "notice": notice, "warnings": list(warnings), "audio": audio, "playable": playable,
            "paragraphs": len(sources), "unclosed": [(s["paragraph_id"], s["revision"]) for s in sources if not s["closed"]],
            "unreviewed": sum(not s["human_reviewed"] for s in sources),
            "triage_interrupted": triage, "research_interrupted": research, "running": running}


def describe(report):
    audio = report["audio"]
    lines = [STATE_NAMES[report["state"]], report["notice"], "",
             f"Falas ativas salvas: {report['paragraphs']} · sem conferência humana: {report['unreviewed']}",
             f"Parágrafos sem encerramento: {len(report['unclosed'])}",
             f"Tarefas interrompidas no histórico: {report['triage_interrupted']} triagens e {report['research_interrupted']} pesquisas.",
             f"Tarefas ainda marcadas em andamento: {report['running']}", "", audio["message"]]
    if "duration" in audio:
        lines += [f"Dados de áudio presentes: {audio['duration']:.2f} s · {audio['frames']} amostras por canal.",
                  f"Bytes finais sem amostra completa: {audio['dropped_bytes']}."]
    if report["playable"] and audio["state"] == "repairable":
        lines.append("Cópia recuperada disponível; Ouvir trecho usará essa cópia.")
    lines += ["", *report["warnings"], "",
              "A duração indica dados presentes no arquivo, não garante que toda a fala foi capturada ou transcrita.",
              "Revisões, fontes e decisões já salvas continuam no banco. Confira os trechos e as lacunas antes de analisar.",
              "Encerrar parágrafos usa somente o texto existente e mantém a conferência humana pendente.",
              "Nenhuma pesquisa ou chamada à IA é reiniciada ao abrir. Use Analisar seleção ou retome a pesquisa no dossiê.",
              "Para voltar à transmissão, inicie outra captura e confira novamente a minutagem do vídeo.",
              "Após uma queda, o texto provisório e o que não chegou ao disco podem estar perdidos."]
    return "\n".join(lines)


class AudioRecoveryTask:
    def __init__(self, review, emit):
        self.review, self.emit = review, emit
        self.token, self.pending = "recovery-" + uuid.uuid4().hex, 1
        self.cancelled, self.lock = threading.Event(), threading.RLock()

    def start(self):
        threading.Thread(target=self._run, name="audio-recovery", daemon=True).start()

    def cancel(self):
        with self.lock:
            self.cancelled.set()

    def _run(self):
        result = {"token": self.token, "success": False}
        try:
            path = recover_audio(self.review, self.cancelled, self.lock)
            result.update(success=True, message=f"Cópia de áudio recuperada: {path}")
        except (ValueError, InterruptedError) as exc:
            result["message"] = str(exc)
        except Exception:
            result["message"] = "Não foi possível concluir a cópia recuperada. Confira o espaço e a permissão de escrita."
        finally:
            self.pending = 0
            self.emit("recovery_done", result)
