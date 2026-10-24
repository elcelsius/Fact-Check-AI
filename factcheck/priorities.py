"""Prioridade manual de revisão, independente da extração e do veredito."""

import json

from .grouping import active
from .review import now


LEVELS = {"high": "Alta", "normal": "Normal", "low": "Baixa", "unset": "Não definida"}
FILTERS = {**LEVELS, "needs_review": "A conferir"}
ORDERINGS = {"recent": "Mais recentes", "priority": "Prioridade", "chronological": "Ordem da fala"}
DEFAULT = {"revision": 0, "level": "unset", "reason": "", "updated_at": None,
           "claim_revision": None, "source_revision": None}


def priority_payload(claim, metadata=None, source_current=True):
    value = {key: (metadata or {}).get(key, default) for key, default in DEFAULT.items()}
    matches = (value["revision"] > 0 and value["claim_revision"] == claim.get("claim_revision", 1)
               and value["source_revision"] == claim["revision"])
    return {**value, "current": bool(source_current and matches),
            "needs_review": bool(value["revision"] and value["level"] != "unset" and not matches)}


def filter_key(metadata=None):
    value = metadata or DEFAULT
    return "needs_review" if value.get("needs_review") else value["level"]


def priority_label(metadata=None):
    value = metadata or DEFAULT
    label = LEVELS[value["level"]]
    if value.get("needs_review"):
        return "A conferir · " + label
    if value["revision"] and not value.get("current"):
        return label + " · histórica"
    return label


def describe_priority(metadata=None):
    value = metadata or DEFAULT
    if not value["revision"]:
        return "Prioridade de revisão: não definida pelo operador."
    return (f"Prioridade de revisão: {priority_label(value)} · revisão {value['revision']}\n"
            f"Justificativa: {value['reason']}\nAtualização: {value['updated_at']}\n"
            "Prioridade organiza o trabalho; a decisão factual é registrada separadamente.")


def read_priority(db, cid):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='claim_priorities'").fetchone():
        return None
    row = db.execute("SELECT payload FROM claim_priorities WHERE claim_id=?", (cid,)).fetchone()
    return json.loads(row[0]) if row else None


class PriorityStore:
    def __init__(self, review):
        self.review = review
        with review.connection() as db:
            db.execute("CREATE TABLE IF NOT EXISTS claim_priorities (claim_id TEXT PRIMARY KEY, revision INTEGER NOT NULL, payload TEXT NOT NULL)")

    def all(self):
        with self.review.connection() as db:
            return {cid: json.loads(payload) for cid, payload in db.execute("SELECT claim_id,payload FROM claim_priorities")}

    def save(self, cid, expected_revision, expected_claim_revision, expected_source_revision, level, reason):
        if not isinstance(level, str) or level not in LEVELS:
            raise ValueError("Escolha Alta, Normal, Baixa ou Não definida.")
        if not isinstance(reason, str) or not reason.strip() or len(reason) > 2000:
            raise ValueError("Explique a prioridade em até 2.000 caracteres, inclusive para removê-la.")
        if any(type(value) is not int or value < minimum for value, minimum in
               ((expected_revision, 0), (expected_claim_revision, 1), (expected_source_revision, 1))):
            raise ValueError("Revisões de prioridade, extração ou fala inválidas.")
        with self.review.connection() as db:
            row = db.execute("SELECT payload FROM claims WHERE id=?", (cid,)).fetchone()
            if not row:
                raise ValueError("Afirmação não encontrada.")
            claim = json.loads(row[0])
            source = json.loads(db.execute("SELECT payload FROM paragraphs WHERE id=?", (claim["paragraph_id"],)).fetchone()[0])
            if (not active(source) or source["needs_rebase"] or claim.get("source_outdated")
                    or claim["status"] in {"descartada", "analise_desatualizada"} or claim["revision"] != source["revision"]):
                raise ValueError("Escolha uma afirmação atual e não descartada para definir prioridade.")
            if claim.get("claim_revision", 1) != expected_claim_revision or source["revision"] != expected_source_revision:
                raise ValueError("A afirmação ou a fala mudou. Reabra a prioridade antes de salvar.")
            previous = read_priority(db, cid)
            if (previous or DEFAULT)["revision"] != expected_revision:
                raise ValueError("A prioridade mudou. Reabra a configuração antes de salvar.")
            fields = {"level": level, "reason": reason.strip(), "claim_revision": expected_claim_revision,
                      "source_revision": expected_source_revision}
            if previous and all(previous[key] == value for key, value in fields.items()):
                return priority_payload(claim, previous)
            updated = {**fields, "revision": expected_revision + 1, "updated_at": now()}
            db.execute("INSERT OR REPLACE INTO claim_priorities VALUES (?,?,?)", (cid, updated["revision"], json.dumps(updated, ensure_ascii=False)))
            self.review._audit(db, "claim_priority_changed", {"claim_id": cid, "previous": previous, "current": updated})
            return priority_payload(claim, updated)
