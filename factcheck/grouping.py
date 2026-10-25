"""Agrupamento editorial reversível; os registros de reconhecimento são preservados."""

import json


def active(source: dict) -> bool:
    return source.get("hidden_by") is None and not source.get("retired", False)


def reconciliation_needed(source: dict) -> bool:
    baseline = source.get("merge_baseline", {})
    return bool(source.get("needs_rebase") or any(source.get(key) != baseline.get(key)
                for key in ("text", "speaker", "human_reviewed")))


def _read(db, pid):
    row = db.execute("SELECT payload FROM paragraphs WHERE id=?", (pid,)).fetchone()
    if row is None:
        raise ValueError("Trecho não encontrado.")
    return json.loads(row[0])


def _current(db, pid, revision):
    source = _read(db, pid)
    if not active(source) or source["revision"] != revision:
        raise ValueError("O trecho mudou ou foi substituído. Atualize a seleção e confira a versão atual.")
    return source


def combine(store, left_id: int, left_revision: int, right_id: int, right_revision: int,
            confirmed_unknown: bool = False) -> dict:
    with store.connection() as db:
        left, right = _current(db, left_id, left_revision), _current(db, right_id, right_revision)
        sources = sorted((json.loads(row[0]) for row in db.execute("SELECT payload FROM paragraphs")),
                         key=lambda source: (source["start"], source["end"], source["paragraph_id"]))
        ids = [source["paragraph_id"] for source in sources if active(source)]
        index = ids.index(left_id)
        if ids[index + 1:index + 2] != [right_id]:
            raise ValueError("Selecione dois parágrafos adjacentes, na ordem da fala.")
        if not all(source["closed"] and not source["needs_rebase"] for source in (left, right)):
            raise ValueError("Combine apenas parágrafos concluídos e sem atualização pendente da origem.")
        speakers = {source["speaker"] for source in (left, right) if source["speaker"]}
        if len(speakers) > 1:
            raise ValueError("Não é possível combinar falas atribuídas a participantes diferentes.")
        if any(not source["speaker"] for source in (left, right)) and not confirmed_unknown:
            raise ValueError("Confira e confirme que os dois trechos pertencem à mesma pessoa.")
        text = " ".join(source["text"].strip() for source in (left, right))
        if not text.strip() or len(text) > 30000:
            raise ValueError("O texto combinado deve ter de 1 a 30.000 caracteres.")
        # IDs negativos não disputam os IDs positivos produzidos pelo reconhecimento ao vivo.
        pid = min(0, db.execute("SELECT COALESCE(MIN(id),0) FROM paragraphs").fetchone()[0]) - 1
        speaker = next(iter(speakers), None)
        original = {"paragraph_id": pid, "version": 1,
                    "source_text": " ".join(source["original"]["source_text"].strip() for source in (left, right)),
                    "start": min(left["start"], right["start"]), "end": max(left["end"], right["end"]),
                    "speaker": None, "closed": True,
                    "source_paragraph_ids": [origin for source in (left, right)
                        for origin in source["original"].get("source_paragraph_ids", [source["paragraph_id"]])],
                    "parts": [part for source in (left, right) for part in source["original"].get("parts", [])]}
        original["text"] = original["source_text"]
        gaps = [gap for source in (left, right) for gap in source["original"].get("audio_gaps", [])]
        if gaps: original["audio_gaps"] = gaps
        combined = {"paragraph_id": pid, "revision": 1, "text": text, "speaker": speaker,
                    "edited": True, "human_reviewed": False, "needs_rebase": False,
                    "closed": True, "start": original["start"], "end": original["end"],
                    "original": original, "source_version": 1, "merged_from": [left_id, right_id],
                    "merge_baseline": {"text": text, "speaker": speaker, "human_reviewed": False}}
        store._audit(db, "paragraphs_combined", {"sources": [left, right], "combined": combined})
        for source in (left, right):
            source["hidden_by"] = pid
            source["revision"] += 1
            store._save(db, source)
            store._invalidate(db, source["paragraph_id"])
        store._save(db, combined)
        return combined


def uncombine(store, pid: int, expected_revision: int, reconciled_texts: list[str] | None = None,
              confirmed: bool = False) -> list[dict]:
    with store.connection() as db:
        combined = _current(db, pid, expected_revision)
        if not combined.get("merged_from"):
            raise ValueError("O parágrafo selecionado não é uma combinação.")
        sources = [_read(db, child) for child in combined["merged_from"]]
        if any(source.get("hidden_by") != pid for source in sources):
            raise ValueError("A composição mudou. Reabra os trechos antes de descombinar.")
        needs_reconciliation = reconciliation_needed(combined)
        if needs_reconciliation and (reconciled_texts is None or not confirmed):
            raise ValueError("Houve alterações após a combinação. Confira e distribua o texto antes de descombinar.")
        if reconciled_texts is not None:
            if (not confirmed or len(reconciled_texts) != len(sources)
                    or any(not isinstance(text, str) or not text.strip() or len(text.strip()) > 30000 for text in reconciled_texts)):
                raise ValueError("Confira a distribuição e preencha os dois textos, com até 30.000 caracteres cada.")
            # Uma correção no combinado deve sobreviver integralmente à divisão.
            if ((not combined["needs_rebase"] or combined["text"] != combined["merge_baseline"]["text"])
                    and " ".join(" ".join(reconciled_texts).split()) != " ".join(combined["text"].split())):
                raise ValueError("Os dois textos devem preservar integralmente o texto combinado, na mesma ordem.")
        store._audit(db, "paragraphs_uncombined", {"combined": combined, "sources_before": sources,
                                                   "reconciled_texts": reconciled_texts})
        for index, source in enumerate(sources):
            del source["hidden_by"]
            source["revision"] += 1
            if reconciled_texts is not None:
                source.update(text=reconciled_texts[index].strip(), edited=True,
                              human_reviewed=False, needs_rebase=source["needs_rebase"] if source.get("merged_from") else False)
                if combined["speaker"] != combined["merge_baseline"]["speaker"]:
                    source["speaker"] = combined["speaker"]
            store._save(db, source)
            store._invalidate(db, source["paragraph_id"])
        combined.update(retired=True, revision=combined["revision"] + 1)
        store._save(db, combined)
        store._invalidate(db, pid)
        return sources
