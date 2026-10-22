"""Cadastro, revisões e fila de afirmações, com transações por sessão."""

from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
from urllib.parse import urlparse
import uuid


def process_alive(pid: int) -> bool:
    if os.name != "nt":
        # Na dúvida, preservar o trabalho; a aplicação de captura é para Windows.
        return True
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle:
        return ctypes.get_last_error() != 87
    try:
        code = wintypes.DWORD()
        return not kernel.GetExitCodeProcess(handle, ctypes.byref(code)) or code.value == 259
    finally:
        kernel.CloseHandle(handle)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Debate:
    title: str = "Debate sem título"
    event_date: str = field(default_factory=lambda: date.today().isoformat())
    source_url: str = ""
    participants: list[str] = field(default_factory=list)

    def validate(self):
        self.title = self.title.strip()
        if not self.title or len(self.title) > 160:
            raise ValueError("Informe um título com até 160 caracteres.")
        date.fromisoformat(self.event_date)
        if self.source_url and (urlparse(self.source_url).scheme not in {"http", "https"}
                                or not urlparse(self.source_url).netloc):
            raise ValueError("A origem do vídeo deve ser uma URL http ou https.")
        names = [name.strip() for name in self.participants if name.strip()]
        if len(names) > 30 or any(len(name) > 100 for name in names):
            raise ValueError("Cadastre até 30 participantes, com até 100 caracteres por nome.")
        if len(set(name.casefold() for name in names)) != len(names):
            raise ValueError("Há nomes de participantes repetidos.")
        self.participants = names
        return self


class ReviewStore:
    def __init__(self, folder: Path):
        self.folder = Path(folder)
        if not (self.folder / "session.json").is_file():
            raise ValueError("Escolha uma pasta de sessão com session.json.")
        self.path = self.folder / "review.sqlite3"
        with self.connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS debate (id INTEGER PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS paragraphs (id INTEGER PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS history (id INTEGER PRIMARY KEY, at TEXT, kind TEXT, payload TEXT);
                CREATE TABLE IF NOT EXISTS analyses (id TEXT PRIMARY KEY, paragraph_id INTEGER,
                    revision INTEGER, status TEXT, payload TEXT);
                CREATE INDEX IF NOT EXISTS analysis_source ON analyses(paragraph_id, revision, status);
                CREATE TABLE IF NOT EXISTS claims (id TEXT PRIMARY KEY, paragraph_id INTEGER,
                    revision INTEGER, payload TEXT);
            """)
            if not db.in_transaction:
                db.execute("BEGIN IMMEDIATE")
            if db.execute("PRAGMA user_version").fetchone()[0] == 0:
                db.execute("PRAGMA user_version=1")
            if not db.execute("SELECT 1 FROM debate").fetchone():
                metadata = json.loads((self.folder / "session.json").read_text(encoding="utf8"))
                data = metadata.get("debate", asdict(Debate()))
                db.execute("INSERT INTO debate VALUES (1, ?)", (json.dumps(data, ensure_ascii=False),))

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            with db:
                db.execute("BEGIN IMMEDIATE")
                yield db
        finally:
            db.close()

    @staticmethod
    def _audit(db, kind: str, payload: dict):
        db.execute("INSERT INTO history(at,kind,payload) VALUES (?,?,?)",
                   (now(), kind, json.dumps(payload, ensure_ascii=False)))

    @staticmethod
    def _save(db, source: dict):
        db.execute("INSERT OR REPLACE INTO paragraphs VALUES (?,?)",
                   (source["paragraph_id"], json.dumps(source, ensure_ascii=False)))

    @staticmethod
    def _invalidate(db, paragraph_id: int):
        for claim_id, payload in db.execute("SELECT id,payload FROM claims WHERE paragraph_id=?", (paragraph_id,)).fetchall():
            claim = json.loads(payload)
            claim["source_outdated"] = True
            if claim["status"] != "descartada":
                claim["status"] = "analise_desatualizada"
            db.execute("UPDATE claims SET payload=? WHERE id=?", (json.dumps(claim, ensure_ascii=False), claim_id))

    def debate(self) -> dict:
        with self.connection() as db:
            return json.loads(db.execute("SELECT payload FROM debate WHERE id=1").fetchone()[0])

    def save_debate(self, debate: Debate):
        data = asdict(debate.validate())
        with self.connection() as db:
            # Não remover um nome que já foi atribuído a uma fala.
            for (payload,) in db.execute("SELECT payload FROM paragraphs"):
                speaker = json.loads(payload).get("speaker")
                if speaker and speaker not in data["participants"]:
                    raise ValueError(f"O participante {speaker} já está associado a uma fala.")
            old = json.loads(db.execute("SELECT payload FROM debate WHERE id=1").fetchone()[0])
            db.execute("UPDATE debate SET payload=? WHERE id=1", (json.dumps(data, ensure_ascii=False),))
            self._audit(db, "debate_updated", data)
            if old != data:
                for (payload,) in db.execute("SELECT payload FROM paragraphs").fetchall():
                    source = json.loads(payload)
                    source["revision"] += 1
                    self._save(db, source)
                    self._invalidate(db, source["paragraph_id"])

    def ingest(self, paragraph: dict) -> dict:
        pid = paragraph["paragraph_id"]
        with self.connection() as db:
            row = db.execute("SELECT payload FROM paragraphs WHERE id=?", (pid,)).fetchone()
            source = json.loads(row[0]) if row else None
            if source and paragraph["version"] <= source["source_version"]:
                return source
            changed = source and paragraph["source_text"] != source["original"]["source_text"]
            if source is None:
                source = {"paragraph_id": pid, "revision": 1, "text": paragraph["source_text"],
                          "speaker": paragraph.get("speaker"), "edited": False,
                          "human_reviewed": False, "needs_rebase": False}
            elif changed:
                source["revision"] += 1
                source["human_reviewed"] = False
                if source["edited"]:
                    source["needs_rebase"] = True
                else:
                    source["text"] = paragraph["source_text"]
                self._invalidate(db, pid)
            source.update({"original": paragraph, "source_version": paragraph["version"],
                           "start": paragraph["start"], "end": paragraph["end"],
                           "closed": paragraph.get("closed", False)})
            self._save(db, source)
            if changed or not row:
                self._audit(db, "source_updated", source)
            return source

    def import_paragraphs(self):
        path = self.folder / "paragraphs.jsonl"
        if path.is_file():
            for line in path.read_text(encoding="utf8").splitlines():
                if line.strip():
                    self.ingest(json.loads(line))

    def sources(self) -> list[dict]:
        with self.connection() as db:
            return [json.loads(row[0]) for row in db.execute("SELECT payload FROM paragraphs ORDER BY id")]

    def source(self, pid: int) -> dict:
        with self.connection() as db:
            row = db.execute("SELECT payload FROM paragraphs WHERE id=?", (pid,)).fetchone()
        if not row:
            raise ValueError("Trecho não encontrado.")
        return json.loads(row[0])

    def revise(self, pid: int, expected_revision: int, text: str, speaker: str | None,
               reviewed: bool = True, use_original: bool = False) -> dict:
        if not text.strip() or len(text) > 30000:
            raise ValueError("O texto deve ter de 1 a 30.000 caracteres.")
        with self.connection() as db:
            source = json.loads(db.execute("SELECT payload FROM paragraphs WHERE id=?", (pid,)).fetchone()[0])
            if source["revision"] != expected_revision:
                raise ValueError("Esse trecho mudou. Reabra a revisão para conferir a versão atual.")
            debate = json.loads(db.execute("SELECT payload FROM debate WHERE id=1").fetchone()[0])
            if speaker and speaker not in debate["participants"]:
                raise ValueError("Cadastre esse participante nos dados do debate.")
            source.update({"revision": source["revision"] + 1, "text": text.strip(),
                           "speaker": speaker, "human_reviewed": reviewed, "needs_rebase": False,
                           "edited": not use_original})
            self._invalidate(db, pid)
            self._save(db, source)
            self._audit(db, "human_revision", source)
            return source

    def begin_analysis(self, pid: int, force: bool = False) -> tuple[str, dict] | None:
        with self.connection() as db:
            source = json.loads(db.execute("SELECT payload FROM paragraphs WHERE id=?", (pid,)).fetchone()[0])
            if source["needs_rebase"]:
                raise ValueError("Confira a atualização do texto original antes de analisar.")
            states = ("running",) if force else ("running", "completed")
            marks = ",".join("?" for _ in states)
            if db.execute(f"SELECT 1 FROM analyses WHERE paragraph_id=? AND revision=? AND status IN ({marks})",
                          (pid, source["revision"], *states)).fetchone():
                return None
            analysis_id = uuid.uuid4().hex
            db.execute("INSERT INTO analyses VALUES (?,?,?,?,?)", (analysis_id, pid, source["revision"], "running", json.dumps({"started_at": now(), "owner_pid": os.getpid()})))
            return analysis_id, source

    def finish_analysis(self, analysis_id: str, items: list[dict], engine: dict) -> bool:
        with self.connection() as db:
            pid, revision, state = db.execute("SELECT paragraph_id,revision,status FROM analyses WHERE id=?", (analysis_id,)).fetchone()
            source = json.loads(db.execute("SELECT payload FROM paragraphs WHERE id=?", (pid,)).fetchone()[0])
            if state != "running" or source["revision"] != revision or source["needs_rebase"]:
                db.execute("UPDATE analyses SET status='stale' WHERE id=?", (analysis_id,))
                return False
            self._invalidate(db, pid)
            for item in items:
                claim_id = uuid.uuid4().hex
                claim = {**item, "id": claim_id, "analysis_id": analysis_id, "paragraph_id": pid,
                         "revision": revision, "speaker": source["speaker"], "start": source["start"],
                         "end": source["end"], "context": source["text"], "created_at": now(),
                         "status": "precisa_contexto" if item["category"] == "fato" and item.get("context_notes") else
                                   "aguardando_pesquisa" if item["category"] == "fato" else
                                   "precisa_contexto" if item["category"] == "indefinida" else "fora_da_fila",
                         "review_status": "automatico_nao_revisado", "engine": engine}
                db.execute("INSERT INTO claims VALUES (?,?,?,?)", (claim_id, pid, revision, json.dumps(claim, ensure_ascii=False)))
            db.execute("UPDATE analyses SET status='completed',payload=? WHERE id=?",
                       (json.dumps({"ended_at": now(), "engine": engine, "items": len(items)}), analysis_id))
            self._audit(db, "analysis_completed", {"analysis_id": analysis_id, "paragraph_id": pid, "revision": revision, "engine": engine})
            return True

    def fail_analysis(self, analysis_id: str, message: str, cancelled: bool = False):
        with self.connection() as db:
            db.execute("UPDATE analyses SET status=?,payload=? WHERE id=? AND status='running'",
                       ("cancelled" if cancelled else "failed", json.dumps({"error": message, "at": now()}), analysis_id))

    def recover_interrupted(self):
        with self.connection() as db:
            for analysis_id, payload in db.execute("SELECT id,payload FROM analyses WHERE status='running'").fetchall():
                owner = json.loads(payload).get("owner_pid")
                if not owner or not process_alive(owner):
                    db.execute("UPDATE analyses SET status='interrupted' WHERE id=?", (analysis_id,))

    def analysis_states(self) -> dict:
        with self.connection() as db:
            return {(pid, revision): {"status": status, **json.loads(payload)} for pid, revision, status, payload
                    in db.execute("SELECT paragraph_id,revision,status,payload FROM analyses ORDER BY rowid")}

    def claims(self) -> list[dict]:
        with self.connection() as db:
            return [json.loads(row[0]) for row in db.execute("SELECT payload FROM claims ORDER BY rowid DESC")]

    def discard_claim(self, claim_id: str, reason: str):
        if not reason.strip():
            raise ValueError("Informe o motivo do descarte.")
        with self.connection() as db:
            claim = json.loads(db.execute("SELECT payload FROM claims WHERE id=?", (claim_id,)).fetchone()[0])
            claim.update({"status": "descartada", "discard_reason": reason.strip()})
            db.execute("UPDATE claims SET payload=? WHERE id=?", (json.dumps(claim, ensure_ascii=False), claim_id))
            self._audit(db, "claim_discarded", {"id": claim_id, "reason": reason})
