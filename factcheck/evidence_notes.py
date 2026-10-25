"""Evidências selecionadas e cálculos do operador, sem aprovação factual automática."""

import ast
from datetime import date
from decimal import Decimal, DecimalException, localcontext
from hashlib import sha256
import json
import re
import uuid

from .discovery import search_basis
from .review import now

RELATIONS = {"sustenta": "Sustenta", "contradiz": "Contradiz", "contextualiza": "Contextualiza"}


def decimal_value(value):
    if not isinstance(value, str) or not re.fullmatch(r"[+-]?\d{1,24}(?:[.,]\d{1,12})?", value.strip()):
        raise ValueError("Use números decimais, sem separador de milhar ou notação exponencial.")
    return Decimal(value.strip().replace(",", "."))


def calculate(formula, variables):
    if not isinstance(formula, str) or not formula.strip() or len(formula) > 500 or not isinstance(variables, dict) or len(variables) > 20:
        raise ValueError("Informe fórmula de até 500 caracteres e até vinte variáveis.")
    if any(not isinstance(key, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,29}", key) for key in variables):
        raise ValueError("Use nomes de variáveis com letras, números e sublinhado, começando por letra.")
    values = {key: decimal_value(value) for key, value in variables.items()}
    formula = formula.strip()
    used = set()
    try:
        tree = ast.parse(formula, mode="eval")
        if len(list(ast.walk(tree))) > 100:
            raise ValueError("A fórmula contém operações demais.")
        def visit(node):
            if isinstance(node, ast.Name) and node.id in values:
                used.add(node.id)
                return values[node.id]
            if isinstance(node, ast.Constant) and type(node.value) in (int, float):
                return decimal_value(ast.get_source_segment(formula, node))
            if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
                return visit(node.operand) * (-1 if isinstance(node.op, ast.USub) else 1)
            if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)):
                left, right = visit(node.left), visit(node.right)
                if isinstance(node.op, ast.Add): return left + right
                if isinstance(node.op, ast.Sub): return left - right
                if isinstance(node.op, ast.Mult): return left * right
                return left / right
            raise ValueError("Use somente variáveis, números, parênteses e operações +, -, * e /.")
        with localcontext() as context:
            context.prec = 28
            result = visit(tree.body)
        if used != set(values) or not result.is_finite() or abs(result) > Decimal("1e100"):
            raise ValueError("Confira as variáveis utilizadas e a magnitude do resultado.")
        return format(result, "f")
    except (SyntaxError, DecimalException, RecursionError) as exc:
        raise ValueError("Fórmula inválida ou divisão por zero.") from exc


def document_fingerprint(document):
    return sha256(json.dumps({key: document.get(key) for key in ("id", "url", "text_sha256", "blocks")}, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def project_notes(claim, plan, documents, notes):
    docs = {doc["id"]: doc for doc in documents}
    basis = search_basis(claim, plan)
    projected = []
    for note in notes:
        current = (not note.get("retired_at") and not claim.get("source_outdated")
                   and claim["status"] not in {"descartada", "analise_desatualizada"} and note["basis"] == basis)
        if note["kind"] in {"citation", "source_context"}:
            doc = docs.get(note["document_id"])
            current = current and doc is not None and note["document_sha256"] == document_fingerprint(doc)
        projected.append({**note, "current": bool(current)})
    citations = {note["id"] for note in projected if note["kind"] == "citation" and note["current"]}
    return [{**note, "current": note["current"] and all(nid in citations for nid in note["note_ids"])} if note["kind"] == "calculation" else note for note in projected]


def save_note(store, cid, expected_revision, kind, fields):
    schemas = {"citation": {"document_id", "block_id", "quote", "relation", "explanation"},
               "calculation": {"formula", "variables", "unit", "note_ids", "explanation"},
               "source_context": {"document_id", "period", "available_on", "common_origin", "explanation"}}
    if kind not in schemas or not isinstance(fields, dict) or set(fields) != schemas[kind]:
        raise ValueError("Anotação fora do formato esperado.")
    if not isinstance(fields["explanation"], str) or not fields["explanation"].strip() or len(fields["explanation"]) > 2000:
        raise ValueError("Explique a evidência ou o cálculo em até 2.000 caracteres.")
    with store.review.connection() as db:
        claim, _ = store._claim(db, cid, active=True)
        revision, case = store._case(db, cid)
        if revision != expected_revision:
            raise ValueError("O dossiê mudou. Reabra as anotações antes de salvar.")
        notes = case.get("work_notes", [])
        if sum(not note.get("retired_at") for note in notes) >= 100:
            raise ValueError("O dossiê chegou a cem anotações ativas; revise as existentes.")
        docs = [json.loads(row[0]) for row in db.execute("SELECT payload FROM evidence WHERE claim_id=?", (cid,))]
        note = {**fields, "id": uuid.uuid4().hex, "kind": kind, "origin": "operator_input", "created_at": now(),
                "basis": search_basis(claim, case.get("plan")), "explanation": fields["explanation"].strip()}
        if kind in {"citation", "source_context"}:
            doc = next((doc for doc in docs if doc["id"] == fields["document_id"]), None)
            if doc is None:
                raise ValueError("Escolha uma fonte atualmente coletada neste dossiê.")
            note["document_sha256"] = document_fingerprint(doc)
            if kind == "citation":
                block = next((block for block in doc["blocks"] if block["id"] == fields["block_id"]), None)
                if (block is None or not isinstance(fields["quote"], str) or not fields["quote"].strip() or len(fields["quote"]) > 10000
                        or fields["quote"] not in block["text"] or not isinstance(fields["relation"], str) or fields["relation"] not in RELATIONS):
                    raise ValueError("Use uma citação literal do bloco escolhido e informe sua relação com a afirmação.")
                note["locator"] = block["locator"]
            else:
                if any(not isinstance(fields[key], str) or len(fields[key]) > 1000 for key in ("period", "available_on", "common_origin")):
                    raise ValueError("Contexto da fonte inválido.")
                if fields["available_on"]:
                    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", fields["available_on"]):
                        raise ValueError("Informe a data de disponibilidade como AAAA-MM-DD.")
                    date.fromisoformat(fields["available_on"])
        else:
            ids = fields["note_ids"]
            current_ids = {note["id"] for note in project_notes(claim, case.get("plan"), docs, notes) if note["kind"] == "citation" and note["current"]}
            if (not isinstance(ids, list) or not 1 <= len(ids) <= 20 or any(not isinstance(nid, str) or nid not in current_ids for nid in ids)
                    or len(set(ids)) != len(ids) or not isinstance(fields["unit"], str) or not fields["unit"].strip() or len(fields["unit"]) > 80):
                raise ValueError("Vincule o cálculo a citações atuais e informe a unidade, como %, p.p. ou pessoas.")
            note["result"] = calculate(fields["formula"], fields["variables"])
        store._save(db, cid, revision+1, {**case, "work_notes": [*notes, note], "preliminary": None, "decision": None}, "work_note_added")
        return note


def retire_note(store, cid, expected_revision, nid, reason):
    if not isinstance(reason, str) or not reason.strip() or len(reason) > 2000:
        raise ValueError("Informe o motivo da retirada em até 2.000 caracteres.")
    with store.review.connection() as db:
        store._claim(db, cid, active=True)
        revision, case = store._case(db, cid)
        if revision != expected_revision:
            raise ValueError("O dossiê mudou. Reabra as anotações.")
        notes = case.get("work_notes", [])
        note = next((note for note in notes if note["id"] == nid and not note.get("retired_at")), None)
        if note is None:
            raise ValueError("Anotação não encontrada ou já retirada.")
        note.update(retired_at=now(), retire_reason=reason.strip())
        store._save(db, cid, revision+1, {**case, "work_notes": notes, "preliminary": None, "decision": None}, "work_note_retired")
