"""Revisão editorial da extração, separada da fala e da decisão factual."""

import json
import uuid

from .grouping import active
from .review import now
from .triage import FIELDS, validate_items
from .topics import annotate, checked_snapshot


EDITABLE = ("quote", "summary", "category", "topic")
ITEM_KEYS = (*EDITABLE, "reason", *[key for key in FIELDS if key != "topic"],
             "quote_start", "quote_end", "validation_notes", "context_notes", "topic_annotation")
CONTENT_KEYS = (*EDITABLE, "reason", *[key for key in FIELDS if key != "topic"])
REVIEWED = "extracao_revisada_pelo_operador"


def _manual_item(fields, text, reason, vocabulary):
    if not isinstance(fields, dict) or set(fields) != set(EDITABLE):
        raise ValueError("Informe citação, resumo, categoria e tema de cada afirmação.")
    if not isinstance(fields["category"], str):
        raise ValueError("Categoria inválida.")
    if not isinstance(reason, str) or not reason.strip() or len(reason) > 2000:
        raise ValueError("Explique a inclusão ou divisão em até 2.000 caracteres.")
    checked = validate_items([{**fields, "reason": reason.strip(), **{key: None for key in FIELDS if key != "topic"}}], text)[0]
    if checked["quote"] != fields["quote"] or checked["summary"] != fields["summary"]:
        raise ValueError("Use citação literal e resumo fiel, preservando números e negações.")
    return annotate(checked, checked_snapshot(vocabulary), "operator") if vocabulary is not None else checked


def create_claims(store, pid, expected_source_revision, fields, reason, vocabulary=None, replaced=None):
    """Uma transação para inclusão ou divisão, sem transferir vereditos ou evidências."""
    if type(pid) is not int or type(expected_source_revision) is not int or not isinstance(fields, list) or not 1 <= len(fields) <= 12:
        raise ValueError("Informe de uma a doze afirmações e a revisão da fala.")
    if replaced is not None and (not isinstance(replaced, dict) or set(replaced) != {"id", "revision"} or len(fields) < 2
            or not isinstance(replaced["id"], str) or type(replaced["revision"]) is not int):
        raise ValueError("Uma divisão precisa de duas a doze partes e da versão original.")
    with store.connection() as db:
        row = db.execute("SELECT payload FROM paragraphs WHERE id=?", (pid,)).fetchone()
        source = json.loads(row[0]) if row else None
        if not source or not active(source) or source["needs_rebase"] or not source["closed"] or source["revision"] != expected_source_revision:
            raise ValueError("A fala mudou, está aberta ou foi substituída. Confira a revisão atual antes de incluir afirmações.")
        if source["original"].get("audio_gaps") and not source["human_reviewed"]:
            raise ValueError("Confira primeiro a fala que atravessa uma pausa da captura.")
        old = None
        if replaced:
            row = db.execute("SELECT payload FROM claims WHERE id=?", (replaced["id"],)).fetchone()
            old = json.loads(row[0]) if row else None
            if (not old or old["paragraph_id"] != pid or old["revision"] != expected_source_revision
                    or old.get("claim_revision", 1) != replaced["revision"] or old.get("source_outdated")
                    or old["status"] in {"descartada", "analise_desatualizada"}):
                raise ValueError("A afirmação mudou ou deixou de estar atual. Reabra a divisão.")
        checked = [_manual_item(item, source["text"], reason, vocabulary) for item in fields]
        quotes = [item["quote"] for item in checked]
        if len(set(quotes)) != len(quotes) or old and any(quote not in old["quote"] for quote in quotes):
            raise ValueError("Use partes distintas da citação original, sem acrescentar outra declaração.")
        for cid, payload in db.execute("SELECT id,payload FROM claims WHERE paragraph_id=? AND revision=?", (pid, expected_source_revision)):
            other = json.loads(payload)
            if (not replaced or cid != replaced["id"]) and not other.get("source_outdated") and other["status"] not in {"descartada", "analise_desatualizada"} and other["quote"] in quotes:
                raise ValueError("Já existe uma afirmação atual com esta citação.")
        created = []
        for item in checked:
            origin = {"origin": "operator_split" if old else "operator_input", "at": now(), "reason": reason.strip(),
                      "parent_claim_id": old["id"] if old else None, "source_revision": expected_source_revision}
            claim = {**item, "id": uuid.uuid4().hex, "analysis_id": None, "paragraph_id": pid, "revision": source["revision"],
                     "claim_revision": 1, "speaker": source["speaker"], "start": source["start"], "end": source["end"],
                     "context": source["text"], "created_at": origin["at"], "creation": origin,
                     "source_paragraph_ids": source["original"].get("source_paragraph_ids", [pid]),
                     "status": "precisa_contexto" if item["category"] == "indefinida" or item["category"] == "fato" and item.get("context_notes") else
                               "aguardando_pesquisa" if item["category"] == "fato" else "fora_da_fila",
                     "review_status": REVIEWED, "extraction_review": origin,
                     "engine": {"name": "operator-input", "provider": "operator", "compute": "manual"}}
            from .speakers import assignment_provenance
            attribution = assignment_provenance(source)
            if attribution and attribution["current"]:
                claim["speaker_assignment"] = attribution
            db.execute("INSERT INTO claims VALUES (?,?,?,?)", (claim["id"], pid, source["revision"], json.dumps(claim, ensure_ascii=False)))
            store._audit(db, "claim_created_manually", claim)
            created.append(claim)
        if old:
            previous = dict(old)
            old.update(status="analise_desatualizada", replaced_by=[item["id"] for item in created], split_reason=reason.strip())
            db.execute("UPDATE claims SET payload=? WHERE id=?", (json.dumps(old, ensure_ascii=False), old["id"]))
            store._audit(db, "claim_split", {"previous": previous, "current": old, "children": [item["id"] for item in created]})
        db.execute("UPDATE analyses SET status='stale' WHERE paragraph_id=? AND status='running'", (pid,))
        return created


def revise_claim(store, cid, expected_revision, expected_source_revision, fields, reason, topic_vocabulary=None):
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
        if topic_vocabulary is not None:
            checked = annotate(checked, checked_snapshot(topic_vocabulary), "operator")
        elif fields["topic"] == old.get("topic") and old.get("topic_annotation"):
            checked["topic_annotation"] = old["topic_annotation"]
        for other_id, payload in db.execute("SELECT id,payload FROM claims WHERE paragraph_id=? AND revision=?",
                                            (old["paragraph_id"], old["revision"])):
            other = json.loads(payload)
            if (other_id != cid and not other.get("source_outdated") and other["status"] not in {"descartada", "analise_desatualizada"}
                    and other["quote"] == checked["quote"]):
                raise ValueError("Já existe outra afirmação atual com esta citação. Confira a duplicação antes de salvar.")
        if old.get("review_status") == REVIEWED and all(old.get(key) == checked.get(key) for key in (*CONTENT_KEYS, "topic_annotation")):
            return old
        updated = {**old, **checked, "claim_revision": old.get("claim_revision", 1) + 1,
                   "review_status": REVIEWED,
                   "automatic_extraction": old.get("automatic_extraction") or ({key: old[key] for key in ITEM_KEYS if key in old} if not old.get("creation") else None),
                   "extraction_review": {"origin": "operator_input", "at": now(), "reason": reason}}
        if "topic_annotation" not in checked:
            updated.pop("topic_annotation", None)
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
