"""Vocabulário local versionado; correspondência textual, sem inferir assunto ou veracidade."""

from contextlib import closing, contextmanager
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import unicodedata
import uuid


FIELDS = ("name", "aliases", "description")
DEFINITION_FIELDS = ("id", "revision", *FIELDS)
STATES = {"matched": "Tema do vocabulário", "unmapped": "Fora do vocabulário", "empty": "Sem tema informado",
          "unconfigured": "Vocabulário não configurado"}


def key(value):
    return " ".join("".join(c for c in unicodedata.normalize("NFD", value.casefold()) if not unicodedata.combining(c)).split())


def _now():
    return datetime.now(timezone.utc).isoformat()


def _digest(data):
    return sha256(json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf8")).hexdigest()


def validate_topic(fields):
    if not isinstance(fields, dict) or set(fields) != set(FIELDS):
        raise ValueError("Informe nome, variações de escrita e descrição do tema.")
    def term(value):
        if (not isinstance(value, str) or not value.strip() or len(value) > 100 or ";" in value
                or any(ord(c) < 32 or ord(c) == 127 for c in value)):
            raise ValueError("Use nomes e variações de até 100 caracteres, sem ponto e vírgula ou caracteres de controle.")
        return " ".join(value.split())
    name = term(fields["name"])
    aliases = fields["aliases"]
    if not isinstance(aliases, list) or len(aliases) > 12:
        raise ValueError("Use até doze variações de escrita por tema.")
    seen, checked = {key(name)}, []
    for value in aliases:
        value = term(value)
        if key(value) not in seen:
            checked.append(value)
            seen.add(key(value))
    description = fields["description"]
    if not isinstance(description, str) or len(description) > 1500:
        raise ValueError("Use uma descrição de até 1.500 caracteres.")
    return {"name": name, "aliases": checked, "description": description.strip()}


def make_snapshot(vocabulary_id=None, revision=0, entries=()):
    configured = vocabulary_id is not None
    if (configured and uuid.UUID(vocabulary_id).hex != vocabulary_id or type(revision) is not int or revision < 0
            or not configured and revision != 0):
        raise ValueError("Identidade do vocabulário inválida.")
    definitions, terms = [], set()
    for entry in entries:
        if type(entry.get("archived", False)) is not bool:
            raise ValueError("Estado do tema inválido.")
        if entry.get("archived", False):
            continue
        fields = validate_topic({field: entry[field] for field in FIELDS})
        if uuid.UUID(entry["id"]).hex != entry["id"] or type(entry["revision"]) is not int or not 1 <= entry["revision"] <= revision:
            raise ValueError("Identidade do tema inválida.")
        names = {key(fields["name"]), *(key(value) for value in fields["aliases"])}
        if terms & names or any(value["id"] == entry["id"] for value in definitions):
            raise ValueError("Há temas ou variações ambíguos no vocabulário.")
        terms.update(names)
        definitions.append({"id": entry["id"], "revision": entry["revision"], **fields})
    if not configured and definitions:
        raise ValueError("Temas sem identidade de vocabulário.")
    data = {"configured": configured, "id": vocabulary_id, "revision": revision, "topics": sorted(definitions, key=lambda item: item["id"])}
    return {**data, "sha256": _digest(data)}


def checked_snapshot(data):
    try:
        snapshot = make_snapshot(data["id"], data["revision"], data["topics"])
        if snapshot["sha256"] != data["sha256"] or snapshot["configured"] is not data["configured"]:
            raise ValueError()
        return snapshot
    except (KeyError, TypeError, AttributeError, ValueError):
        raise ValueError("O vocabulário está inválido. Confira a aba Temas antes de analisar.") from None


def identity(snapshot):
    return {field: snapshot[field] for field in ("configured", "id", "revision", "sha256")}


def load_snapshot(root):
    path = Path(root) / "library" / "topics.sqlite3"
    if not path.exists():
        return make_snapshot()
    try:
        with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=0.5)) as db:
            db.execute("PRAGMA query_only=ON")
            db.execute("BEGIN")
            vid, revision = db.execute("SELECT vocabulary_id,revision FROM vocabulary WHERE id=1").fetchone()
            if vid is None:
                raise ValueError("Identidade do vocabulário ausente.")
            entries = [json.loads(payload) for (payload,) in db.execute("SELECT payload FROM topics ORDER BY id")]
        return make_snapshot(vid, revision, entries)
    except (OSError, sqlite3.Error, KeyError, TypeError, AttributeError, ValueError):
        raise ValueError("Não foi possível ler o vocabulário. Confira a pasta library e a aba Temas antes de analisar. A captura pode continuar.") from None


def annotate(item, snapshot, origin="ai"):
    if origin not in {"ai", "operator"}:
        raise ValueError("Origem da classificação temática inválida.")
    original = item.get("topic")
    if original is not None and (not isinstance(original, str) or len(original) > 500):
        raise ValueError("Tema inválido.")
    definition = next((entry for entry in snapshot["topics"] if original and key(original) in
                       {key(entry["name"]), *(key(alias) for alias in entry["aliases"])}), None)
    state = "empty" if not original or not original.strip() else "matched" if definition else "unmapped" if snapshot["configured"] else "unconfigured"
    return {**item, "topic": definition["name"] if definition else original if original and original.strip() else None,
            "topic_annotation": {"status": state, "original": original, "origin": origin,
                                 "vocabulary": identity(snapshot), "definition": definition}}


def describe_topic(annotation):
    if not annotation:
        return "Tema livre; registro anterior sem vocabulário associado."
    vocabulary, definition = annotation["vocabulary"], annotation.get("definition")
    lines = [STATES[annotation["status"]], f"Termo informado: {annotation['original'] or 'Não informado'}",
             "Classificação temática: " + ("normalização da sugestão da IA" if annotation["origin"] == "ai" else "revisão do operador")]
    if vocabulary["configured"]:
        lines.append(f"Vocabulário {vocabulary['id']} · revisão {vocabulary['revision']} · SHA-256 {vocabulary['sha256']}")
    if definition:
        lines += [f"Tema {definition['id']} · versão {definition['revision']}: {definition['name']}",
                  "Descrição cadastrada: " + (definition["description"] or "Não informada")]
    lines.append("Organização por tema não confere a extração nem decide a veracidade.")
    return "\n".join(lines)


class TopicStore:
    def __init__(self, folder):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.path = self.folder / "topics.sqlite3"
        with self.connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS vocabulary (id INTEGER PRIMARY KEY CHECK(id=1), vocabulary_id TEXT NOT NULL, revision INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS topics (id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS topic_terms (term TEXT PRIMARY KEY, topic_id TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS topic_history (id INTEGER PRIMARY KEY, topic_id TEXT, at TEXT, payload TEXT);
                CREATE INDEX IF NOT EXISTS history_topic ON topic_history(topic_id);
            """)
            db.execute("INSERT OR IGNORE INTO vocabulary VALUES (1,?,0)", (uuid.uuid4().hex,))

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
            entries = [json.loads(payload) for (payload,) in db.execute("SELECT payload FROM topics")]
        return sorted(entries, key=lambda item: (key(item["name"]), item["id"]))

    @staticmethod
    def _get(db, topic_id):
        row = db.execute("SELECT payload FROM topics WHERE id=?", (topic_id,)).fetchone()
        if not row:
            raise ValueError("Tema não encontrado.")
        return json.loads(row[0])

    @staticmethod
    def _reason(reason, expected_revision):
        if not isinstance(reason, str) or not reason.strip() or len(reason) > 2000 or type(expected_revision) is not int or expected_revision < 0:
            raise ValueError("Informe um motivo de até 2.000 caracteres e uma revisão válida.")
        return reason.strip()

    @staticmethod
    def _write(db, previous, current, action):
        db.execute("INSERT OR REPLACE INTO topics VALUES (?,?)", (current["id"], json.dumps(current, ensure_ascii=False)))
        db.execute("UPDATE vocabulary SET revision=revision+1 WHERE id=1")
        revision = db.execute("SELECT revision FROM vocabulary WHERE id=1").fetchone()[0]
        db.execute("INSERT INTO topic_history(topic_id,at,payload) VALUES (?,?,?)", (current["id"], current["updated_at"],
                   json.dumps({"action": action, "vocabulary_revision": revision, "previous": previous, "current": current}, ensure_ascii=False)))

    def save(self, fields, reason, topic_id=None, expected_revision=0):
        fields = validate_topic(fields)
        reason = self._reason(reason, expected_revision)
        with self.connection() as db:
            previous = self._get(db, topic_id) if topic_id is not None else None
            if (previous["revision"] if previous else 0) != expected_revision:
                raise ValueError("O tema mudou. Reabra o cadastro antes de salvar.")
            if previous and all(previous[field] == value for field, value in fields.items()) and previous["reason"] == reason:
                return previous
            stamp = _now()
            current = {**fields, "id": topic_id or uuid.uuid4().hex, "revision": expected_revision + 1,
                "archived": previous["archived"] if previous else False, "created_at": previous["created_at"] if previous else stamp,
                "updated_at": stamp, "reason": reason}
            db.execute("DELETE FROM topic_terms WHERE topic_id=?", (current["id"],))
            try:
                db.executemany("INSERT INTO topic_terms VALUES (?,?)", [(key(value), current["id"]) for value in [fields["name"], *fields["aliases"]]])
            except sqlite3.IntegrityError:
                raise ValueError("Nome ou variação já pertence a outro tema, inclusive arquivado. Confira o cadastro existente.") from None
            self._write(db, previous, current, "created" if previous is None else "edited")
            return current

    def set_archived(self, topic_id, expected_revision, archived, reason):
        reason = self._reason(reason, expected_revision)
        if type(archived) is not bool:
            raise ValueError("Estado do tema inválido.")
        with self.connection() as db:
            previous = self._get(db, topic_id)
            if previous["revision"] != expected_revision:
                raise ValueError("O tema mudou. Atualize a lista antes de arquivar ou restaurar.")
            if previous["archived"] == archived:
                return previous
            current = {**previous, "revision": expected_revision + 1, "archived": archived, "reason": reason, "updated_at": _now()}
            self._write(db, previous, current, "archived" if archived else "restored")
            return current

    def history(self, topic_id):
        with self.connection() as db:
            return [json.loads(payload) for (payload,) in db.execute("SELECT payload FROM topic_history WHERE topic_id=? ORDER BY id", (topic_id,))]
