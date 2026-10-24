"""Coleção local de referências de pesquisa; nenhum cadastro comprova uma fala."""

from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
import uuid

from .queue_filters import normalize
from .review import now
from .sources import source_url


TEXT_FIELDS = {"title": 300, "url": 2000, "institution": 200, "methodology": 3000,
               "periodicity": 500, "limits": 3000, "notes": 4000}
FIELDS = (*TEXT_FIELDS, "topics")
META_FIELDS = ("id", "revision", "created_at", "updated_at", "archived", "change_reason")


def validate_reference(fields):
    if not isinstance(fields, dict) or set(fields) != set(FIELDS):
        raise ValueError("Informe os campos da referência e seus temas.")
    checked = {}
    for key, limit in TEXT_FIELDS.items():
        value = fields[key]
        if not isinstance(value, str) or len(value) > limit:
            raise ValueError(f"Campo {key} inválido; use até {limit} caracteres.")
        checked[key] = value.strip()
    if not checked["title"] or not checked["institution"]:
        raise ValueError("Informe título e instituição da referência.")
    checked["url"] = source_url(checked["url"])
    topics = fields["topics"]
    if (not isinstance(topics, list) or not 1 <= len(topics) <= 8
            or any(not isinstance(topic, str) or not topic.strip() or len(topic) > 100
                   or ";" in topic or any(ord(c) < 32 for c in topic) for topic in topics)):
        raise ValueError("Informe de um a oito temas, com até 100 caracteres cada.")
    checked["topics"] = list(dict.fromkeys(" ".join(topic.split()) for topic in topics))
    return checked


def reference_snapshot(entry):
    try:
        fields = validate_reference({key: entry[key] for key in FIELDS})
        if (uuid.UUID(entry["id"]).hex != entry["id"] or type(entry["revision"]) is not int or entry["revision"] < 1
                or entry["archived"] is not False):
            raise ValueError()
        if any(not isinstance(entry[key], str) or len(entry[key]) > limit for key, limit in
               (("created_at", 60), ("updated_at", 60), ("change_reason", 2000))):
            raise ValueError()
        return {**{key: entry[key] for key in META_FIELDS}, **fields}
    except (KeyError, TypeError, AttributeError, ValueError):
        raise ValueError("Escolha uma referência ativa e válida na coleção.") from None


def filter_references(entries, query="", topic=None, include_archived=False):
    words = normalize(query).split()
    result = []
    for entry in entries:
        if entry["archived"] and not include_archived or topic is not None and topic not in entry["topics"]:
            continue
        text = normalize(" ".join([*(entry[key] for key in TEXT_FIELDS), *entry["topics"]]))
        if all(word in text for word in words):
            result.append(entry)
    return result


def render_reference(entry):
    return "\n".join([f"{entry['title']} · referência {entry['id']} · versão {entry['revision']}",
        entry["url"], "Instituição informada: " + entry["institution"], "Temas: " + "; ".join(entry["topics"]),
        "Metodologia informada: " + (entry["methodology"] or "A definir"),
        "Periodicidade informada: " + (entry["periodicity"] or "A definir"),
        "Limites de uso informados: " + (entry["limits"] or "A definir"),
        "Observações: " + (entry["notes"] or "Não informadas"),
        "Cadastro atualizado em: " + entry["updated_at"],
        "Referência de pesquisa; o cadastro não confirma acesso à URL, atualidade ou pertinência do documento."])


class SourceLibrary:
    def __init__(self, folder):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.path = self.folder / "sources.sqlite3"
        with self.connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS library_entries (id TEXT PRIMARY KEY, url TEXT UNIQUE NOT NULL, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS library_history (id INTEGER PRIMARY KEY, entry_id TEXT, at TEXT, kind TEXT, payload TEXT);
                CREATE INDEX IF NOT EXISTS library_history_entry ON library_history(entry_id);
            """)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            with db:
                db.execute("BEGIN IMMEDIATE")
                yield db
        finally:
            db.close()

    def entries(self):
        with self.connection() as db:
            values = [json.loads(row[0]) for row in db.execute("SELECT payload FROM library_entries")]
        return sorted(values, key=lambda item: (normalize(item["title"]), item["id"]))

    @staticmethod
    def _get(db, entry_id):
        row = db.execute("SELECT payload FROM library_entries WHERE id=?", (entry_id,)).fetchone()
        if not row:
            raise ValueError("Referência não encontrada na coleção.")
        return json.loads(row[0])

    def get(self, entry_id, expected_revision=None, require_active=False):
        with self.connection() as db:
            entry = self._get(db, entry_id)
        if expected_revision is not None and entry["revision"] != expected_revision:
            raise ValueError("A referência mudou. Atualize a lista e confira a nova versão.")
        if require_active and entry["archived"]:
            raise ValueError("A referência foi arquivada. Confira o cadastro antes de restaurá-la.")
        return entry

    @staticmethod
    def _reason(reason, expected_revision):
        if not isinstance(reason, str) or not reason.strip() or len(reason) > 2000:
            raise ValueError("Explique o cadastro ou a alteração em até 2.000 caracteres.")
        if type(expected_revision) is not int or expected_revision < 0:
            raise ValueError("Revisão da referência inválida.")
        return reason.strip()

    @staticmethod
    def _write(db, previous, current, kind):
        db.execute("INSERT OR REPLACE INTO library_entries VALUES (?,?,?)", (current["id"], current["url"], json.dumps(current, ensure_ascii=False)))
        db.execute("INSERT INTO library_history(entry_id,at,kind,payload) VALUES (?,?,?,?)",
                   (current["id"], current["updated_at"], kind, json.dumps({"previous": previous, "current": current}, ensure_ascii=False)))

    def save(self, fields, reason, entry_id=None, expected_revision=0):
        fields = validate_reference(fields)
        reason = self._reason(reason, expected_revision)
        with self.connection() as db:
            previous = self._get(db, entry_id) if entry_id is not None else None
            if (previous["revision"] if previous else 0) != expected_revision:
                raise ValueError("A referência mudou. Reabra o cadastro antes de salvar.")
            duplicate = db.execute("SELECT id FROM library_entries WHERE url=?", (fields["url"],)).fetchone()
            if duplicate and duplicate[0] != entry_id:
                raise ValueError("Esta URL já está cadastrada, inclusive entre as arquivadas. Reabra a referência existente.")
            if previous and all(previous[key] == value for key, value in fields.items()) and previous["change_reason"] == reason:
                return previous
            stamp = now()
            current = {**fields, "id": entry_id or uuid.uuid4().hex, "revision": expected_revision + 1,
                       "created_at": previous["created_at"] if previous else stamp, "updated_at": stamp,
                       "archived": previous["archived"] if previous else False, "change_reason": reason}
            self._write(db, previous, current, "edited" if previous else "created")
            return current

    def set_archived(self, entry_id, expected_revision, archived, reason):
        reason = self._reason(reason, expected_revision)
        if type(archived) is not bool:
            raise ValueError("Estado de arquivamento inválido.")
        with self.connection() as db:
            previous = self._get(db, entry_id)
            if previous["revision"] != expected_revision:
                raise ValueError("A referência mudou. Atualize a lista antes de alterar seu estado.")
            if previous["archived"] == archived:
                return previous
            current = {**previous, "archived": archived, "revision": expected_revision + 1,
                       "updated_at": now(), "change_reason": reason}
            self._write(db, previous, current, "archived" if archived else "restored")
            return current

    def history(self, entry_id):
        with self.connection() as db:
            self._get(db, entry_id)
            return [{"at": stamp, "kind": kind, **json.loads(payload)} for stamp, kind, payload in
                    db.execute("SELECT at,kind,payload FROM library_history WHERE entry_id=? ORDER BY id", (entry_id,))]
