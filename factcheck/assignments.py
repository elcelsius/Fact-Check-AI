"""Responsável local pelo caso, separado da autoria da decisão factual."""

import json

from .grouping import active
from .review import now


DEFAULT = {"revision": 0, "name": "", "reason": "", "updated_at": None,
           "claim_revision": None, "source_revision": None}


def assignment_payload(claim, metadata=None, source_current=True):
    value = {key: (metadata or {}).get(key, default) for key, default in DEFAULT.items()}
    matches = (value["revision"] > 0 and value["claim_revision"] == claim.get("claim_revision", 1)
               and value["source_revision"] == claim["revision"])
    return {**value, "current": bool(source_current and matches),
            "needs_review": bool(value["revision"] and value["name"] and not matches)}


def assignment_label(metadata=None):
    value = metadata or DEFAULT
    label = value["name"] or "Sem responsável"
    if value.get("needs_review"):
        return label + " · a conferir"
    if value["revision"] and not value.get("current"):
        return label + " · histórico"
    return label


def describe_assignment(metadata=None):
    value = metadata or DEFAULT
    if not value["revision"]:
        return "Responsável pelo caso: ainda não atribuído."
    return (f"Responsável pelo caso: {assignment_label(value)} · revisão {value['revision']}\n"
            f"Motivo da atribuição: {value['reason']}\nAtualização: {value['updated_at']}\n"
            "Atribuição local por nome; o responsável pela decisão factual é registrado na conclusão.")


def read_assignment(db, cid):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='claim_assignments'").fetchone():
        return None
    row = db.execute("SELECT payload FROM claim_assignments WHERE claim_id=?", (cid,)).fetchone()
    return json.loads(row[0]) if row else None


def history_entry(at, payload):
    data = json.loads(payload)
    return {"at": at, "claim_id": data["claim_id"],
            "previous": {key: data["previous"].get(key, default) for key, default in DEFAULT.items()} if data.get("previous") else None,
            "current": {key: data["current"].get(key, default) for key, default in DEFAULT.items()}}


def read_assignment_history(db, cid):
    return [history_entry(at, payload) for at, payload in db.execute(
        "SELECT at,payload FROM history WHERE kind='claim_assignment_changed' AND json_extract(payload,'$.claim_id')=? ORDER BY id", (cid,))]


class AssignmentStore:
    def __init__(self, review):
        self.review = review
        with review.connection() as db:
            db.execute("CREATE TABLE IF NOT EXISTS claim_assignments (claim_id TEXT PRIMARY KEY, revision INTEGER NOT NULL, payload TEXT NOT NULL)")

    def all(self):
        with self.review.connection() as db:
            return {cid: json.loads(payload) for cid, payload in db.execute("SELECT claim_id,payload FROM claim_assignments")}

    def save(self, cid, expected_revision, expected_claim_revision, expected_source_revision, name, reason):
        if not isinstance(name, str) or len(name) > 100 or any(ord(c) < 32 or ord(c) == 127 for c in name):
            raise ValueError("Informe um nome de até 100 caracteres, em uma linha, ou deixe vazio para retirar a atribuição.")
        if not isinstance(reason, str) or not reason.strip() or len(reason) > 2000:
            raise ValueError("Explique a atribuição em até 2.000 caracteres, inclusive para trocá-la ou retirá-la.")
        if any(type(value) is not int or value < minimum for value, minimum in
               ((expected_revision, 0), (expected_claim_revision, 1), (expected_source_revision, 1))):
            raise ValueError("Revisões de atribuição, extração ou fala inválidas.")
        name = " ".join(name.split())
        with self.review.connection() as db:
            row = db.execute("SELECT payload FROM claims WHERE id=?", (cid,)).fetchone()
            if not row:
                raise ValueError("Afirmação não encontrada.")
            claim = json.loads(row[0])
            source = json.loads(db.execute("SELECT payload FROM paragraphs WHERE id=?", (claim["paragraph_id"],)).fetchone()[0])
            if (not active(source) or source["needs_rebase"] or claim.get("source_outdated")
                    or claim["status"] in {"descartada", "analise_desatualizada"} or claim["revision"] != source["revision"]):
                raise ValueError("Escolha uma afirmação atual e não descartada para atribuir um responsável.")
            if claim.get("claim_revision", 1) != expected_claim_revision or source["revision"] != expected_source_revision:
                raise ValueError("A afirmação ou a fala mudou. Reabra a atribuição antes de salvar.")
            previous = read_assignment(db, cid)
            if (previous or DEFAULT)["revision"] != expected_revision:
                raise ValueError("A atribuição mudou. Reabra a configuração antes de salvar.")
            fields = {"name": name, "reason": reason.strip(), "claim_revision": expected_claim_revision,
                      "source_revision": expected_source_revision}
            if previous and all(previous[key] == value for key, value in fields.items()):
                return assignment_payload(claim, previous)
            updated = {**fields, "revision": expected_revision + 1, "updated_at": now()}
            db.execute("INSERT OR REPLACE INTO claim_assignments VALUES (?,?,?)", (cid, updated["revision"], json.dumps(updated, ensure_ascii=False)))
            self.review._audit(db, "claim_assignment_changed", {"claim_id": cid, "previous": previous, "current": updated})
            return assignment_payload(claim, updated)
