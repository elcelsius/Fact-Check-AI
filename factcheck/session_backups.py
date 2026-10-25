"""Cópia e restauração de sessão por arquivos próprios, sem extrair caminhos do ZIP."""

from hashlib import sha256
from contextlib import closing
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile
import threading
import uuid
import zipfile

from . import __version__
from .recovery import SAFE_STATES, capture_state
from .review import now
from .persistence import atomic_json

FILES = {"session.json", "audio.wav", "audio.recovered.wav", "transcript.jsonl", "transcript.txt", "paragraphs.jsonl", "paragraphs.txt", "events.jsonl", "review.sqlite3"}
MAX_TOTAL = 12 * 1024**3
MAX_FILES = 24


def check(cancelled):
    if cancelled is not None and cancelled.is_set():
        raise InterruptedError("Operação cancelada; arquivos anteriores foram preservados.")


def allowed(name):
    return name in FILES or isinstance(name, str) and re.fullmatch(r"recovered/audio-[0-9a-f]{24}\.wav", name) is not None


def digest_file(path, cancelled=None):
    digest = sha256()
    with Path(path).open("rb") as source:
        while block := source.read(1024*1024):
            check(cancelled)
            digest.update(block)
    return digest.hexdigest()


def create_backup(folder, destination, cancelled=None, progress=lambda _: None, commit_lock=None):
    folder, destination = Path(folder).resolve(), Path(destination).resolve()
    if capture_state(folder)[0] not in SAFE_STATES:
        raise ValueError("Encerre a captura e confirme o estado da sessão antes de criar a cópia.")
    if destination.is_relative_to(folder) or destination.suffix.lower() != ".fcbak":
        raise ValueError("Escolha um arquivo .fcbak fora da pasta da sessão.")
    candidates = [*folder.iterdir(), *(folder/"recovered").glob("audio-*.wav")]
    paths = sorted(path for path in candidates if path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(folder)
                   and allowed(path.relative_to(folder).as_posix()))
    if len(paths) > MAX_FILES or sum(path.stat().st_size for path in paths) > MAX_TOTAL or not (folder/"review.sqlite3").is_file():
        raise ValueError("Sessão acima dos limites de cópia ou banco de revisão ausente.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    with tempfile.TemporaryDirectory(dir=destination.parent, prefix=".factcheck-backup-") as stage:
        if not Path(stage).resolve().is_relative_to(destination.parent):
            raise ValueError("Destino temporário inválido.")
        db_copy = Path(stage)/"review.sqlite3"
        with closing(sqlite3.connect((folder/'review.sqlite3').as_uri()+"?mode=ro", uri=True)) as source:
            with closing(sqlite3.connect(db_copy)) as target:
                source.backup(target, pages=128, progress=lambda *_: check(cancelled))
                target.commit()
        manifest = {"format": "factcheck-session-backup", "schema_version": 1, "app_version": __version__, "created_at": now(), "files": {}}
        try:
            with tempfile.NamedTemporaryFile(dir=destination.parent, prefix=".factcheck-", suffix=".part", delete=False) as output:
                temporary = Path(output.name)
            with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=1, allowZip64=True) as archive:
                for original in paths:
                    check(cancelled)
                    name = original.relative_to(folder).as_posix()
                    source = db_copy if original.name == "review.sqlite3" else original
                    stamp = source.stat()
                    digest = sha256()
                    progress("Copiando " + original.name)
                    with source.open("rb") as reader, archive.open("session/"+name, "w", force_zip64=True) as writer:
                        while block := reader.read(1024*1024):
                            check(cancelled)
                            writer.write(block)
                            digest.update(block)
                    after = source.stat()
                    if (stamp.st_size,stamp.st_mtime_ns) != (after.st_size,after.st_mtime_ns):
                        raise ValueError("Um arquivo da sessão mudou durante a cópia. Tente novamente após encerrar as tarefas.")
                    manifest["files"][name] = {"bytes": stamp.st_size, "mtime_ns": stamp.st_mtime_ns, "sha256": digest.hexdigest()}
                archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, allow_nan=False))
            result_digest = digest_file(temporary, cancelled)
            with commit_lock or threading.RLock():
                check(cancelled)
                os.replace(temporary, destination)
        finally:
            if temporary: temporary.unlink(missing_ok=True)
    return {"path": str(destination), "files": len(manifest["files"]), "sha256": result_digest}


def restore_backup(source, recordings, cancelled=None, progress=lambda _: None, commit_lock=None):
    source, recordings = Path(source).resolve(), Path(recordings).resolve()
    recordings.mkdir(parents=True, exist_ok=True)
    final = recordings / ("restored-"+uuid.uuid4().hex[:16])
    with tempfile.TemporaryDirectory(dir=recordings, prefix=".restore-") as temporary:
        stage = Path(temporary).resolve()
        if not stage.is_relative_to(recordings):
            raise ValueError("Destino temporário inválido.")
        with zipfile.ZipFile(source) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_FILES+1 or len({item.filename for item in entries}) != len(entries) or sum(item.file_size for item in entries) > MAX_TOTAL:
                raise ValueError("Cópia acima dos limites ou com entradas repetidas.")
            manifest_info = archive.getinfo("manifest.json")
            if manifest_info.file_size > 100000:
                raise ValueError("Manifesto acima do limite.")
            manifest = json.loads(archive.read(manifest_info))
            if not isinstance(manifest, dict) or manifest.get("format") != "factcheck-session-backup" or manifest.get("schema_version") != 1 or not isinstance(manifest.get("files"), dict):
                raise ValueError("Formato da cópia não reconhecido.")
            files = manifest["files"]
            if not {"session.json", "review.sqlite3"}.issubset(files) or any(not allowed(name) or "\\" in name for name in files):
                raise ValueError("Cópia com nomes não permitidos ou sem os arquivos essenciais.")
            expected = {"manifest.json", *("session/"+name for name in files)}
            if set(item.filename for item in entries) != expected:
                raise ValueError("A cópia contém caminhos não autorizados ou arquivos sem manifesto.")
            for name, metadata in files.items():
                check(cancelled)
                info = archive.getinfo("session/"+name)
                if (info.is_dir() or (info.external_attr >> 16) & 0o170000 == 0o120000 or not isinstance(metadata, dict)
                        or type(metadata.get("bytes")) is not int or info.file_size != metadata["bytes"] or not isinstance(metadata.get("sha256"), str)):
                    raise ValueError("Entrada de cópia inválida.")
                progress("Restaurando " + name)
                digest = sha256()
                (stage/name).parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as reader, (stage/name).open("xb") as writer:
                    while block := reader.read(1024*1024):
                        check(cancelled)
                        digest.update(block)
                        writer.write(block)
                if digest.hexdigest() != metadata["sha256"]:
                    raise ValueError("A integridade de um arquivo da cópia não foi confirmada. Nenhuma sessão foi substituída.")
                if type(metadata.get("mtime_ns")) is int and 0 <= metadata["mtime_ns"] <= 2**63-1:
                    os.utime(stage/name, ns=(metadata["mtime_ns"],metadata["mtime_ns"]))
        with closing(sqlite3.connect(stage/"review.sqlite3")) as db:
            if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise ValueError("O banco restaurado não passou pela verificação de integridade.")
            if db.execute("SELECT 1 FROM sqlite_master WHERE type IN ('trigger','view') OR sql LIKE '%CREATE VIRTUAL TABLE%'").fetchone():
                raise ValueError("O banco contém estruturas não usadas pelo aplicativo.")
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not {"debate", "paragraphs", "claims"}.issubset(tables):
                raise ValueError("O banco não contém os registros essenciais da sessão.")
            for table in ("analyses", "research_jobs", "speaker_runs", "research_batches"):
                if table in tables:
                    for rid, payload in db.execute(f"SELECT id,payload FROM {table} WHERE status='running'").fetchall():
                        data = {**json.loads(payload), "owner_pid": 0, "restored_at": now(), "error": "Tarefa interrompida na restauração; retomada exige ação do operador."}
                        db.execute(f"UPDATE {table} SET status='interrupted',payload=? WHERE id=?", (json.dumps(data),rid))
            if "api_requests" in tables:
                db.execute("UPDATE api_requests SET status='interrupted' WHERE status='reserved'")
            db.execute("INSERT INTO history(at,kind,payload) VALUES (?,?,?)", (now(), "session_restored", json.dumps({"backup_created_at": manifest["created_at"], "automatic_jobs_started": False})))
            db.commit()
        metadata = json.loads((stage/"session.json").read_text(encoding="utf8"))
        if not isinstance(metadata, dict):
            raise ValueError("Metadados da captura inválidos.")
        if metadata.get("status") in {"recording", "finalizing"}:
            metadata.update(status="interrupted", owner_pid=0)
        metadata["restored_at"] = now()
        atomic_json(stage/"session.json", metadata)
        # Os dois caminhos são próprios, dentro do destino escolhido; publicação por rename.
        with commit_lock or threading.RLock():
            check(cancelled)
            if not stage.resolve().is_relative_to(recordings) or not final.resolve().is_relative_to(recordings) or final.exists():
                raise ValueError("O destino da restauração mudou ou já existe.")
            stage.rename(final)
    return {"folder": str(final), "files": len(files), "automatic_jobs_started": False}


class FileTask:
    def __init__(self, operation, arguments, emit):
        self.operation, self.arguments, self.emit = operation, arguments, emit
        self.token = "files-"+uuid.uuid4().hex
        self.pending = 1
        self.cancelled = threading.Event()
        self.lock = threading.RLock()

    def cancel(self):
        with self.lock:
            self.cancelled.set()

    def start(self):
        threading.Thread(target=self._run, daemon=True, name="session-files").start()

    def _run(self):
        result, error = None, ""
        try:
            result = self.operation(*self.arguments, cancelled=self.cancelled, commit_lock=self.lock,
                progress=lambda message: self.emit("files_progress", {"token": self.token, "message": message}))
        except (ValueError, OSError, InterruptedError, zipfile.BadZipFile, KeyError, sqlite3.DatabaseError) as exc:
            error = str(exc)
        except Exception:
            error = "Não foi possível concluir a operação de arquivos. Os originais foram preservados."
        finally:
            self.pending = 0
            self.emit("files_done", {"token": self.token, "result": result, "error": error})
