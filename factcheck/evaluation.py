"""Avaliação somente sobre referências humanas explícitas, com denominadores e versões."""

from hashlib import sha256
from contextlib import nullcontext
import json
import re
import unicodedata
import uuid

from .grouping import active
from .persistence import atomic_json
from .recovery import capture_state
from .review import now


def tokens(text):
    text = unicodedata.normalize("NFKC", text).casefold().replace("−", "-")
    return re.findall(r"[+-]?\d+(?:[.,]\d+)?%?|[^\W\d_]+(?:['’-][^\W\d_]+)*", text)


def word_errors(reference, hypothesis, cancelled=None):
    ref, hyp = tokens(reference), tokens(hypothesis)
    if len(ref) > 4000 or len(hyp) > 4000:
        raise ValueError("Divida referências acima de quatro mil palavras antes de avaliar.")
    previous = [(index, 0, 0, index) for index in range(len(hyp)+1)]
    for i, expected in enumerate(ref, 1):
        if cancelled is not None and cancelled.is_set(): raise InterruptedError("Avaliação cancelada.")
        row = [(i, 0, i, 0)]
        for j, actual in enumerate(hyp, 1):
            diagonal = previous[j-1]
            cost = int(expected != actual)
            substitute = (diagonal[0]+cost, diagonal[1]+cost, diagonal[2], diagonal[3])
            delete = (previous[j][0]+1, previous[j][1], previous[j][2]+1, previous[j][3])
            insert = (row[j-1][0]+1, row[j-1][1], row[j-1][2], row[j-1][3]+1)
            row.append(min((substitute, delete, insert), key=lambda value: value[0]))
        previous = row
    errors, substitutions, deletions, insertions = previous[-1]
    return {"reference_words": len(ref), "hypothesis_words": len(hyp), "errors": errors, "substitutions": substitutions,
            "deletions": deletions, "insertions": insertions, "wer": errors/len(ref) if ref else None}


def evaluation_material(rows, partition="evaluation"):
    sources = {data["paragraph_id"]: data for (raw,) in rows["paragraphs"] for data in [json.loads(raw)] if active(data)}
    refs = sorted(({"revision": revision, **json.loads(raw)} for _, revision, raw in rows.get("evaluation_references", [])), key=lambda ref: ref["paragraph_id"])
    eligible = [ref for ref in refs if ref["paragraph_id"] in sources and sources[ref["paragraph_id"]]["revision"] == ref["source_revision"]
                and sources[ref["paragraph_id"]]["human_reviewed"] and not sources[ref["paragraph_id"]]["needs_rebase"]
                and ref.get("partition", "evaluation") == partition]
    analyzed = {pid for _, pid, revision, state, _ in rows["analyses"] if state == "completed" and pid in sources and sources[pid]["revision"] == revision}
    predictions = []
    for (raw,) in rows["claims"]:
        claim = json.loads(raw)
        pid = claim["paragraph_id"]
        if (pid not in sources or claim["revision"] != sources[pid]["revision"] or claim.get("source_outdated") or claim.get("creation")
                or claim.get("analysis_id") is None or claim.get("engine", {}).get("provider") == "operator"):
            continue
        item = claim.get("automatic_extraction") or claim
        if item["category"] == "fato":
            predictions.append({"id": claim["id"], "paragraph_id": pid, "quote": item["quote"], "engine": claim.get("engine", {})})
    material = {"references": eligible, "predictions": sorted(predictions, key=lambda item: item["id"]), "analyzed_paragraphs": sorted(analyzed),
                "source_versions": {pid: source["revision"] for pid, source in sources.items()}, "total_references": len(refs), "partition": partition}
    encoded = json.dumps(material, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return material, sha256(encoded).hexdigest()


def quality_from_records(records):
    quality = {"human_reference": "not_provided", "precision": None, "recall": None, "transcript_word_error_rate": None}
    runs = records["rows"].get("evaluation_runs", [])
    if not runs: return quality
    result = json.loads(runs[-1][1])
    _, basis = evaluation_material(records["rows"], result["reference"].get("partition", "evaluation"))
    current = result["basis"] == basis
    return {**quality, "human_reference": "provided" if current else "stale", "evaluation_id": result["id"], "current": current,
            "method": "normalized_literal_quote_match", "reference_partition": result["reference"].get("partition", "evaluation"),
            "precision": result["metrics"]["literal_precision"] if current else None,
            "recall": result["metrics"]["literal_recall"] if current else None,
            "transcript_word_error_rate": result["metrics"]["wer"] if current else None,
            "metrics": result["metrics"] if current else None}


class EvaluationStore:
    def __init__(self, review):
        self.review = review
        with review.connection() as db:
            db.execute("CREATE TABLE IF NOT EXISTS evaluation_references (paragraph_id INTEGER PRIMARY KEY, revision INTEGER, payload TEXT)")
            db.execute("CREATE TABLE IF NOT EXISTS evaluation_runs (id TEXT PRIMARY KEY, payload TEXT)")

    def references(self):
        with self.review.connection() as db:
            return {pid: {"revision": revision, **json.loads(raw)} for pid, revision, raw in db.execute("SELECT paragraph_id,revision,payload FROM evaluation_references")}

    def save_reference(self, pid, expected_revision, source_revision, expected_facts, annotator, blind=False, partition="evaluation"):
        if partition not in {"development", "evaluation"}:
            raise ValueError("Escolha desenvolvimento ou avaliação reservada.")
        if (not isinstance(expected_facts, list) or len(expected_facts) > 50 or any(not isinstance(value, str) or not value.strip() or len(value) > 10000 for value in expected_facts)
                or not isinstance(annotator, str) or not annotator.strip() or len(annotator) > 160 or type(blind) is not bool):
            raise ValueError("Informe revisor e até cinquenta citações factuais esperadas; lista vazia significa ausência de fatos nesta fala.")
        normalized = [tuple(tokens(value)) for value in expected_facts]
        if len(set(normalized)) != len(normalized) or any(not value for value in normalized): raise ValueError("Há afirmações esperadas repetidas ou sem palavras.")
        with self.review.connection() as db:
            row = db.execute("SELECT payload FROM paragraphs WHERE id=?", (pid,)).fetchone()
            source = json.loads(row[0]) if row else None
            if not source or not active(source) or not source["human_reviewed"] or source["needs_rebase"] or not source["closed"] or source["revision"] != source_revision:
                raise ValueError("Confira primeiro a transcrição em Revisar falas e use sua revisão atual como referência.")
            if not tokens(source["text"]) or any(value not in source["text"] for value in expected_facts):
                raise ValueError("As afirmações esperadas precisam ser citações literais do texto conferido.")
            row = db.execute("SELECT revision,payload FROM evaluation_references WHERE paragraph_id=?", (pid,)).fetchone()
            current = row[0] if row else 0
            if expected_revision != current: raise ValueError("A referência mudou. Reabra a avaliação.")
            for other_pid, raw in db.execute("SELECT paragraph_id,payload FROM evaluation_references WHERE paragraph_id!=?", (pid,)):
                other = json.loads(raw)
                if other.get("partition", "evaluation") != partition and (tokens(other["reference_text"]) == tokens(source["text"])
                        or set(tuple(tokens(text)) for text in other["expected_facts"]) & set(normalized)):
                    raise ValueError("Há repetição literal entre desenvolvimento e avaliação. Use conjuntos sem essas repetições.")
            payload = {"paragraph_id": pid, "source_revision": source_revision, "reference_text": source["text"],
                       "recognition_text": source["original"]["source_text"], "expected_facts": expected_facts,
                       "annotator": annotator.strip(), "blind": blind, "partition": partition, "created_at": now()}
            db.execute("INSERT OR REPLACE INTO evaluation_references VALUES (?,?,?)", (pid, current+1, json.dumps(payload, ensure_ascii=False)))
            self.review._audit(db, "evaluation_reference_changed", {"previous": json.loads(row[1]) if row else None, "current": payload})

    def material(self, connection=None, partition="evaluation"):
        with (nullcontext(connection) if connection is not None else self.review.connection()) as db:
            rows = {"paragraphs": db.execute("SELECT payload FROM paragraphs").fetchall(), "claims": db.execute("SELECT payload FROM claims").fetchall(),
                    "analyses": db.execute("SELECT id,paragraph_id,revision,status,payload FROM analyses").fetchall(),
                    "evaluation_references": db.execute("SELECT paragraph_id,revision,payload FROM evaluation_references").fetchall()}
        return evaluation_material(rows, partition)

    def evaluate(self, cancelled=None, progress=lambda _: None, commit_lock=None, partition="evaluation"):
        if capture_state(self.review.folder)[0] == "active":
            raise ValueError("Encerre a captura antes de avaliar a sessão.")
        material, basis = self.material(partition=partition)
        if not material["references"]:
            raise ValueError("Cadastre referências humanas atuais antes de calcular métricas.")
        totals = {key: 0 for key in ("reference_words", "hypothesis_words", "errors", "substitutions", "deletions", "insertions")}
        tp = fp = fn = annotated_with_triage = 0
        details = []
        for ref in material["references"]:
            progress(f"Avaliando referência do parágrafo {ref['paragraph_id']}")
            errors = word_errors(ref["reference_text"], ref["recognition_text"], cancelled)
            for key in totals: totals[key] += errors[key]
            row = {"paragraph_id": ref["paragraph_id"], "word_errors": errors}
            if ref["paragraph_id"] in material["analyzed_paragraphs"]:
                expected = {tuple(tokens(value)) for value in ref["expected_facts"]}
                predicted = {tuple(tokens(item["quote"])) for item in material["predictions"] if item["paragraph_id"] == ref["paragraph_id"]}
                row.update(true_positives=len(expected & predicted), false_positives=len(predicted-expected), false_negatives=len(expected-predicted))
                tp += row["true_positives"]; fp += row["false_positives"]; fn += row["false_negatives"]
                annotated_with_triage += 1
            details.append(row)
        result = {"id": uuid.uuid4().hex, "created_at": now(), "basis": basis, "method_version": 1, "reference": material,
            "metrics": {**totals, "wer": totals["errors"]/totals["reference_words"] if totals["reference_words"] else None,
                        "true_positives": tp, "false_positives": fp, "false_negatives": fn,
                        "literal_precision": tp/(tp+fp) if tp+fp else None, "literal_recall": tp/(tp+fn) if tp+fn else None,
                        "annotated_paragraphs": len(material["references"]), "annotated_with_triage": annotated_with_triage,
                        "total_active_paragraphs": len(material["source_versions"]),
                        "blind_references": sum(ref["blind"] for ref in material["references"])}, "details": details,
            "limitations": ["Somente a parcela anotada foi avaliada; não é precisão de toda a transmissão ou dos vereditos.",
                "Correspondência literal normalizada de citações; equivalência semântica não é inferida.",
                "WER ignora caixa e pontuação comum, preserva sinais de números, percentuais, acentos e negações.",
                "Texto conferido pode ter sido visto após a sugestão da IA; a condição cega é declarada pelo anotador."]}
        import threading
        with commit_lock or threading.RLock():
            if cancelled is not None and cancelled.is_set(): raise InterruptedError("Avaliação cancelada.")
            with self.review.connection() as db:
                # Outra conexão não pode mudar a referência durante a confirmação desta versão.
                _, current_basis = self.material(db, partition)
                if current_basis != basis:
                    raise ValueError("Uma referência mudou. Calcule a avaliação novamente.")
                db.execute("INSERT INTO evaluation_runs VALUES (?,?)", (result["id"], json.dumps(result, ensure_ascii=False)))
                self.review._audit(db, "evaluation_completed", {"id": result["id"], "basis": basis, "metrics": result["metrics"]})
        return result

    def latest(self):
        with self.review.connection() as db:
            row = db.execute("SELECT payload FROM evaluation_runs ORDER BY rowid DESC LIMIT 1").fetchone()
        if not row: return None
        data = json.loads(row[0])
        _, basis = self.material(partition=data["reference"].get("partition", "evaluation"))
        return {**data, "current": data["basis"] == basis}
