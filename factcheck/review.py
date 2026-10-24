"""Cadastro, revisões e fila de afirmações, com transações por sessão."""

from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
import json
import os
from pathlib import Path
import re
import sqlite3
from urllib.parse import urlparse
import uuid

from .timeline import validate_video_position
from .grouping import active, combine, uncombine
from .persistence import paragraph_log

EVENT_KINDS = {"nao_informado": "Não informado", "debate_politico": "Debate político", "propaganda_politica": "Propaganda política",
               "noticiario": "Noticiário", "entrevista": "Entrevista", "outro": "Outro conteúdo"}


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
    title: str = "Transmissão sem título"
    event_date: str = field(default_factory=lambda: date.today().isoformat())
    source_url: str = ""
    participants: list[str] = field(default_factory=list)
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    event_kind: str = "nao_informado"

    def validate(self):
        if not isinstance(self.event_kind, str) or self.event_kind not in EVENT_KINDS:
            raise ValueError("Escolha o tipo de conteúdo da transmissão.")
        try:
            self.event_id = uuid.UUID(self.event_id).hex
        except (ValueError, AttributeError, TypeError):
            raise ValueError("Identificador do evento inválido.") from None
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
                CREATE TABLE IF NOT EXISTS video_reference (
                    id INTEGER PRIMARY KEY CHECK (id=1), revision INTEGER NOT NULL, offset_seconds INTEGER);
                CREATE TABLE IF NOT EXISTS session_identity (
                    id INTEGER PRIMARY KEY CHECK (id=1), session_id TEXT NOT NULL);
            """)
            if not db.in_transaction:
                db.execute("BEGIN IMMEDIATE")
            if db.execute("PRAGMA user_version").fetchone()[0] < 3:
                db.execute("PRAGMA user_version=3")
            db.execute("INSERT OR IGNORE INTO video_reference VALUES (1, 0, NULL)")
            needs_debate = not db.execute("SELECT 1 FROM debate").fetchone()
            needs_identity = not db.execute("SELECT 1 FROM session_identity").fetchone()
            metadata = json.loads((self.folder / "session.json").read_text(encoding="utf8")) if needs_debate or needs_identity else {}
            if needs_debate:
                data = metadata.get("debate", asdict(Debate()))
                db.execute("INSERT INTO debate VALUES (1, ?)", (json.dumps(data, ensure_ascii=False),))
            data = json.loads(db.execute("SELECT payload FROM debate WHERE id=1").fetchone()[0])
            if not data.get("event_id"):
                data["event_id"] = uuid.uuid4().hex
                db.execute("UPDATE debate SET payload=? WHERE id=1", (json.dumps(data, ensure_ascii=False),))
            session_id = metadata.get("session_id", "")
            if not isinstance(session_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,160}", session_id):
                session_id = uuid.uuid4().hex
            db.execute("INSERT OR IGNORE INTO session_identity VALUES (1,?)", (session_id,))

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

    def session_id(self) -> str:
        with self.connection() as db:
            return db.execute("SELECT session_id FROM session_identity WHERE id=1").fetchone()[0]

    def video_reference(self) -> dict:
        with self.connection() as db:
            revision, offset = db.execute("SELECT revision,offset_seconds FROM video_reference WHERE id=1").fetchone()
            return {"revision": revision, "offset_seconds": offset}

    def save_video_reference(self, offset_seconds: int | None, expected_revision: int) -> dict:
        validate_video_position(offset_seconds)
        with self.connection() as db:
            revision, previous = db.execute("SELECT revision,offset_seconds FROM video_reference WHERE id=1").fetchone()
            if revision != expected_revision:
                raise ValueError("A referência do vídeo mudou. Reabra a configuração para conferir o valor atual.")
            if previous == offset_seconds:
                return {"revision": revision, "offset_seconds": previous}
            reference = {"revision": revision + 1, "offset_seconds": offset_seconds}
            db.execute("UPDATE video_reference SET revision=?,offset_seconds=? WHERE id=1",
                       (reference["revision"], offset_seconds))
            self._audit(db, "video_reference_updated", {"previous_offset_seconds": previous, **reference})
            return reference

    def save_debate(self, debate: Debate):
        data = asdict(debate.validate())
        with self.connection() as db:
            # Não remover um nome que já foi atribuído a uma fala.
            for (payload,) in db.execute("SELECT payload FROM paragraphs"):
                speaker = json.loads(payload).get("speaker")
                if speaker and speaker not in data["participants"]:
                    raise ValueError(f"O participante {speaker} já está associado a uma fala.")
            old = json.loads(db.execute("SELECT payload FROM debate WHERE id=1").fetchone()[0])
            data["event_id"] = old["event_id"]
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
            if source and source.get("merged_from"):
                raise ValueError("Parágrafos combinados não recebem atualizações do reconhecimento.")
            if source and paragraph["version"] <= source["source_version"]:
                return source
            changed = source and any(paragraph.get(key) != source["original"].get(key)
                                     for key in ("source_text", "start", "end", "speaker"))
            if source is None:
                source = {"paragraph_id": pid, "revision": 1, "text": paragraph["source_text"],
                          "speaker": paragraph.get("speaker"), "edited": False,
                          "human_reviewed": False, "needs_rebase": False}
            elif changed:
                source["revision"] += 1
                source.pop("speaker_assignment", None)
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
            parent_id = source.get("hidden_by") if changed else None
            while parent_id is not None:
                parent = json.loads(db.execute("SELECT payload FROM paragraphs WHERE id=?", (parent_id,)).fetchone()[0])
                parent.update(revision=parent["revision"] + 1, needs_rebase=True, human_reviewed=False)
                self._save(db, parent)
                self._invalidate(db, parent_id)
                self._audit(db, "combined_origin_updated", {"source_id": pid, "combined": parent})
                parent_id = parent.get("hidden_by")
            return source

    def import_paragraphs(self):
        records, warnings = paragraph_log(self.folder / "paragraphs.jsonl")
        for paragraph in records:
            self.ingest(paragraph)
        return warnings

    def close_interrupted_paragraphs(self, expected: list[tuple[int, int]]) -> int:
        """Encerrar somente a organização editorial; nunca completar texto perdido."""
        from .recovery import SAFE_STATES, capture_state
        if capture_state(self.folder)[0] not in SAFE_STATES:
            raise ValueError("A captura ainda está ativa ou seu encerramento não foi confirmado.")
        with self.connection() as db:
            for pid, revision in expected:
                row = db.execute("SELECT payload FROM paragraphs WHERE id=?", (pid,)).fetchone()
                source = json.loads(row[0]) if row else None
                if not source or not active(source) or source["revision"] != revision or source["closed"]:
                    raise ValueError("As falas mudaram. Atualize o estado da sessão antes de encerrar os trechos.")
                source.update(closed=True, revision=revision + 1, human_reviewed=False,
                              recovery_closure={"at": now(), "reason": "encerramento_manual_apos_interrupcao"})
                self._save(db, source)
                self._invalidate(db, pid)
                self._audit(db, "interrupted_paragraph_closed", source)
        return len(expected)

    def sources(self, include_inactive: bool = False) -> list[dict]:
        with self.connection() as db:
            sources = [json.loads(row[0]) for row in db.execute("SELECT payload FROM paragraphs")]
            return sorted((source for source in sources if include_inactive or active(source)),
                          key=lambda source: (source["start"], source["end"], source["paragraph_id"]))

    def combine(self, left_id: int, left_revision: int, right_id: int, right_revision: int,
                confirmed_unknown: bool = False) -> dict:
        return combine(self, left_id, left_revision, right_id, right_revision, confirmed_unknown)

    def uncombine(self, pid: int, expected_revision: int, reconciled_texts: list[str] | None = None,
                  confirmed: bool = False) -> list[dict]:
        return uncombine(self, pid, expected_revision, reconciled_texts, confirmed)

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
            if not active(source):
                raise ValueError("O trecho foi substituído por uma combinação. Revise o parágrafo ativo.")
            if source.get("merged_from") and source["needs_rebase"]:
                raise ValueError("A origem do combinado mudou. Descombine e confira as falas atualizadas antes de editar.")
            if source["revision"] != expected_revision:
                raise ValueError("Esse trecho mudou. Reabra a revisão para conferir a versão atual.")
            debate = json.loads(db.execute("SELECT payload FROM debate WHERE id=1").fetchone()[0])
            if speaker and speaker not in debate["participants"]:
                raise ValueError("Cadastre esse participante nos dados do debate.")
            source.update({"revision": source["revision"] + 1, "text": text.strip(),
                           "speaker": speaker, "human_reviewed": reviewed, "needs_rebase": False,
                           "edited": not use_original})
            source.pop("speaker_assignment", None)
            self._invalidate(db, pid)
            self._save(db, source)
            self._audit(db, "human_revision", source)
            return source

    def begin_analysis(self, pid: int, force: bool = False, topic_vocabulary=None) -> tuple[str, dict] | None:
        from .topics import checked_snapshot, identity
        provenance = {"topic_vocabulary": identity(checked_snapshot(topic_vocabulary))} if topic_vocabulary is not None else {}
        with self.connection() as db:
            source = json.loads(db.execute("SELECT payload FROM paragraphs WHERE id=?", (pid,)).fetchone()[0])
            if not active(source):
                raise ValueError("O trecho foi substituído. Analise a versão ativa na revisão de falas.")
            if source["needs_rebase"]:
                raise ValueError("Confira a atualização do texto original antes de analisar.")
            states = ("running",) if force else ("running", "completed")
            marks = ",".join("?" for _ in states)
            if db.execute(f"SELECT 1 FROM analyses WHERE paragraph_id=? AND revision=? AND status IN ({marks})",
                          (pid, source["revision"], *states)).fetchone():
                return None
            analysis_id = uuid.uuid4().hex
            db.execute("INSERT INTO analyses VALUES (?,?,?,?,?)", (analysis_id, pid, source["revision"], "running", json.dumps({"started_at": now(), "owner_pid": os.getpid(), **provenance})))
            return analysis_id, source

    def finish_analysis(self, analysis_id: str, items: list[dict], engine: dict, topic_vocabulary=None) -> bool:
        with self.connection() as db:
            pid, revision, state = db.execute("SELECT paragraph_id,revision,status FROM analyses WHERE id=?", (analysis_id,)).fetchone()
            source = json.loads(db.execute("SELECT payload FROM paragraphs WHERE id=?", (pid,)).fetchone()[0])
            if state != "running" or not active(source) or source["revision"] != revision or source["needs_rebase"]:
                db.execute("UPDATE analyses SET status='stale' WHERE id=?", (analysis_id,))
                return False
            if topic_vocabulary is not None:
                from .topics import annotate, checked_snapshot, identity
                vocabulary = checked_snapshot(topic_vocabulary)
                items = [annotate(item, vocabulary) for item in items]
                engine = {**engine, "topic_vocabulary": identity(vocabulary)}
            self._invalidate(db, pid)
            for item in items:
                claim_id = uuid.uuid4().hex
                from .speakers import assignment_provenance
                attribution = assignment_provenance(source)
                claim = {**item, "id": claim_id, "analysis_id": analysis_id, "paragraph_id": pid,
                         "revision": revision, "speaker": source["speaker"], "start": source["start"],
                         "end": source["end"], "context": source["text"], "created_at": now(),
                         "source_paragraph_ids": source["original"].get("source_paragraph_ids", [pid]),
                         "status": "precisa_contexto" if item["category"] == "fato" and item.get("context_notes") else
                                   "aguardando_pesquisa" if item["category"] == "fato" else
                                   "precisa_contexto" if item["category"] == "indefinida" else "fora_da_fila",
                         "review_status": "automatico_nao_revisado", "claim_revision": 1, "engine": engine,
                         **({"speaker_assignment": attribution} if attribution and attribution["current"] else {})}
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
        recovered = 0
        with self.connection() as db:
            for analysis_id, payload in db.execute("SELECT id,payload FROM analyses WHERE status='running'").fetchall():
                owner = json.loads(payload).get("owner_pid")
                if not owner or not process_alive(owner):
                    data = {**json.loads(payload), "recovered_at": now(),
                            "error": "Processo responsável encerrado; nova tentativa depende do operador."}
                    db.execute("UPDATE analyses SET status='interrupted',payload=? WHERE id=?",
                               (json.dumps(data, ensure_ascii=False), analysis_id))
                    self._audit(db, "analysis_interrupted", {"id": analysis_id, **data})
                    recovered += 1
        return recovered

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

    def revise_claim(self, cid, expected_revision, expected_source_revision, fields, reason, topic_vocabulary=None):
        from .claims import revise_claim
        return revise_claim(self, cid, expected_revision, expected_source_revision, fields, reason, topic_vocabulary)
