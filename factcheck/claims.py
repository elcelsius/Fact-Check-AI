"""Revisão editorial da extração, separada da fala e da decisão factual."""

import json

from .grouping import active
from .review import now
from .triage import FIELDS, validate_items


EDITABLE = ("quote", "summary", "category", "topic")
ITEM_KEYS = (*EDITABLE, "reason", *[key for key in FIELDS if key != "topic"],
             "quote_start", "quote_end", "validation_notes", "context_notes")
CONTENT_KEYS = (*EDITABLE, "reason", *[key for key in FIELDS if key != "topic"])
REVIEWED = "extracao_revisada_pelo_operador"


def revise_claim(store, cid, expected_revision, expected_source_revision, fields, reason):
    if not isinstance(fields, dict) or set(fields) != set(EDITABLE):
        raise ValueError("Informe citação, resumo, categoria e tema da afirmação.")
    if not isinstance(fields["category"], str):
        raise ValueError("Categoria inválida.")
    if not isinstance(reason, str) or not reason.strip() or len(reason) > 2000:
        raise ValueError("Explique a revisão em até 2.000 caracteres.")
    reason = reason.strip()
    with store.connection() as db:
        row = db.execute("SELECT payload FROM claims WHERE id=?", (cid,)).fetchone()
        if not row:
            raise ValueError("Afirmação não encontrada.")
        old = json.loads(row[0])
        source = json.loads(db.execute("SELECT payload FROM paragraphs WHERE id=?", (old["paragraph_id"],)).fetchone()[0])
        if (not active(source) or source["needs_rebase"] or old.get("source_outdated")
                or old["status"] in {"descartada", "analise_desatualizada"} or old["revision"] != source["revision"]):
            raise ValueError("A afirmação foi descartada ou sua origem mudou. Abra a extração da revisão atual.")
        if old.get("claim_revision", 1) != expected_revision or source["revision"] != expected_source_revision:
            raise ValueError("A afirmação ou a fala mudou. Reabra a revisão antes de salvar.")
        item = {**fields, "reason": reason, **{key: old.get(key) for key in FIELDS if key != "topic"}}
        try:
            checked = validate_items([item], source["text"])[0]
        except ValueError as exc:
            raise ValueError(str(exc).replace("A citação da IA", "A citação informada")) from None
        # O editor não reescreve silenciosamente o recorte nem o resumo humano.
        if checked["quote"] != fields["quote"]:
            raise ValueError("Copie uma citação literal do texto atual, incluindo negações e qualificadores. Corrija a transcrição em Revisar origem.")
        if checked["summary"] != fields["summary"]:
            raise ValueError("Confira o resumo: preserve as negações e não acrescente números ausentes da fala.")
        for other_id, payload in db.execute("SELECT id,payload FROM claims WHERE paragraph_id=? AND revision=?",
                                            (old["paragraph_id"], old["revision"])):
            other = json.loads(payload)
            if (other_id != cid and not other.get("source_outdated") and other["status"] not in {"descartada", "analise_desatualizada"}
                    and other["quote"] == checked["quote"]):
                raise ValueError("Já existe outra afirmação atual com esta citação. Confira a duplicação antes de salvar.")
        if old.get("review_status") == REVIEWED and all(old.get(key) == checked.get(key) for key in CONTENT_KEYS):
            return old
        updated = {**old, **checked, "claim_revision": old.get("claim_revision", 1) + 1,
                   "review_status": REVIEWED,
                   "automatic_extraction": old.get("automatic_extraction") or {key: old[key] for key in ITEM_KEYS if key in old},
                   "extraction_review": {"origin": "operator_input", "at": now(), "reason": reason}}
        updated["status"] = ("precisa_contexto" if updated["category"] == "indefinida" or
                             updated["category"] == "fato" and updated.get("context_notes") else
                             "aguardando_pesquisa" if updated["category"] == "fato" else "fora_da_fila")
        db.execute("UPDATE claims SET payload=? WHERE id=?", (json.dumps(updated, ensure_ascii=False), cid))
        # Uma triagem que já estava em execução não pode substituir esta revisão.
        db.execute("UPDATE analyses SET status='stale' WHERE paragraph_id=? AND status='running'", (old["paragraph_id"],))
        if db.execute("SELECT 1 FROM sqlite_master WHERE name='cases'").fetchone():
            row = db.execute("SELECT revision,payload FROM cases WHERE claim_id=?", (cid,)).fetchone()
            revision, case = (row[0], json.loads(row[1])) if row else (0, {})
            plan = case.get("plan")
            if plan:
                plan = {**plan, "needs_review": True, "claim_revision": plan.get("claim_revision", old.get("claim_revision", 1))}
            case = {**case, "plan": plan, "preliminary": None, "decision": None}
            db.execute("INSERT OR REPLACE INTO cases VALUES (?,?,?)", (cid, revision + 1, json.dumps(case, ensure_ascii=False)))
            store._audit(db, "claim_dependents_invalidated", {"claim_id": cid, "case_revision": revision + 1, **case})
        store._audit(db, "claim_revised", {"previous": old, "current": updated})
        return updated
