"""Consulta de decisões locais anteriores, sem migrar ou escrever nas sessões lidas."""

from contextlib import closing
from hashlib import sha256
import json
import math
from pathlib import Path
import re
import sqlite3
import threading
import uuid

from .grouping import active
from .planning import PLAN_FIELDS
from .queue_filters import normalize
from .review import now, EVENT_KINDS


VERDICTS = {"confirmada": "Confirmada", "contradita": "Contradita", "inconclusiva": "Inconclusiva"}
COMPARISONS = {"a_conferir": "Equivalência a conferir", "possivel_equivalencia": "Possível equivalência",
               "contexto_diferente": "Contexto diferente"}
COMPARISON_FIELDS = {"statement": "Afirmação e contexto", "period": "Período e validade temporal",
                     "territory": "Território", "indicator": "Indicador e comparação", "methodology": "Método e documentos de suporte"}
CLAIM_FIELDS = ("id", "paragraph_id", "revision", "claim_revision", "quote", "summary", "speaker", "category", "topic",
                "location", "period", "indicator", "comparison", "context", "start", "end", "status")
DOCUMENT_FIELDS = ("id", "url", "title", "institution", "author", "published_at", "accessed_at", "imported_at",
                   "acquisition", "sha256", "text_sha256", "warnings", "truncated")


def _pick(data, keys):
    return {key: data[key] for key in keys if key in data}


def _digest(data):
    return sha256(json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf8")).hexdigest()


def _check(cancelled):
    if cancelled is not None and cancelled.is_set():
        raise InterruptedError("Consulta cancelada.")


def previous_snapshot(data):
    """Cópia permitida para o novo caso; exclui caminhos, outras decisões e texto de documentos."""
    try:
        result = {"session_id": data["session_id"], "event": _pick(data["event"], ("event_id", "title", "event_date", "source_url", "event_kind")),
                  "claim": _pick(data["claim"], CLAIM_FIELDS), "case_revision": data["case_revision"],
                  "source_current": data["source_current"], "transcript_reviewed": data["transcript_reviewed"],
                  "decision": _pick(data["decision"], ("verdict", "reviewer", "reason", "at")),
                  "plan": _pick(data["plan"], (*PLAN_FIELDS, "origin", "updated_at", "needs_review")) if data.get("plan") else None,
                  "documents": [{**_pick(doc, DOCUMENT_FIELDS), "locators": [_pick(block, ("id", "locator"))
                                  for block in doc.get("locators", [])]} for doc in data["documents"]]}
        if (not re.fullmatch(r"[A-Za-z0-9_-]{1,160}", result["session_id"])
                or not re.fullmatch(r"[a-f0-9]{32}", result["claim"]["id"])
                or type(result["case_revision"]) is not int or result["case_revision"] < 1
                or type(result["source_current"]) is not bool or type(result["transcript_reviewed"]) is not bool
                or result["decision"]["verdict"] not in VERDICTS
                or not all(isinstance(result["decision"].get(key), str) and result["decision"][key].strip()
                           for key in ("reviewer", "reason", "at"))):
            raise ValueError()
        claim = result["claim"]
        if (any(not isinstance(result["event"].get(key), str) for key in ("title", "event_date"))
                or any(not isinstance(claim.get(key), str) or not claim[key].strip() for key in ("quote", "summary"))
                or not isinstance(claim.get("context", ""), str)
                or any(type(claim.get(key)) not in (int, float) or not math.isfinite(claim[key]) for key in ("start", "end"))
                or not 0 <= claim["start"] <= claim["end"]
                or any(not isinstance(doc.get(key, ""), str) for doc in result["documents"] for key in ("title", "institution", "url"))
                or any(not isinstance(doc.get("warnings", []), list) or
                       any(not isinstance(warning, str) for warning in doc.get("warnings", [])) for doc in result["documents"])):
            raise ValueError()
        fingerprint = _digest(result)
        if data.get("fingerprint", fingerprint) != fingerprint:
            raise ValueError()
        return json.loads(json.dumps({**result, "fingerprint": fingerprint}, ensure_ascii=False, allow_nan=False))
    except (KeyError, TypeError, AttributeError, ValueError):
        raise ValueError("O registro da checagem anterior é inválido ou mudou. Atualize a consulta.") from None


def read_checked_cases(folder, cancelled=None, include_unreviewed=False):
    """Uma transação de leitura por sessão; não importa JSONL, recupera jobs ou cria identidade."""
    folder = Path(folder).resolve()
    path = folder / "review.sqlite3"
    if path.resolve().parent != folder:
        raise ValueError("Banco fora da pasta da sessão.")
    _check(cancelled)
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=0.5)) as db:
        db.execute("PRAGMA query_only=ON")
        db.set_progress_handler(lambda: int(cancelled is not None and cancelled.is_set()), 1000)
        db.execute("BEGIN")
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {"session_identity", "debate", "paragraphs", "claims"} <= tables:
            raise ValueError("Sessão antiga: abra-a pelo aplicativo para atualizar antes de consultar.")
        if "cases" not in tables:
            return []
        sid = db.execute("SELECT session_id FROM session_identity WHERE id=1").fetchone()[0]
        event = json.loads(db.execute("SELECT payload FROM debate WHERE id=1").fetchone()[0])
        rows = db.execute("SELECT c.id,c.payload,p.payload,k.revision,k.payload FROM cases k JOIN claims c ON c.id=k.claim_id "
                          "JOIN paragraphs p ON p.id=c.paragraph_id ORDER BY c.id").fetchall()
        result = []
        for cid, claim_raw, source_raw, revision, case_raw in rows:
            _check(cancelled)
            case = json.loads(case_raw)
            if not case.get("decision"):
                if include_unreviewed:
                    result.append({"key": f"{sid}/{cid}", "folder": str(folder), "snapshot": None})
                continue
            claim, source = json.loads(claim_raw), json.loads(source_raw)
            if claim["id"] != cid:
                raise ValueError("Identidade da afirmação inconsistente.")
            claim.setdefault("claim_revision", 1)
            valid = bool(active(source) and not source.get("needs_rebase") and source["revision"] == claim["revision"]
                         and not claim.get("source_outdated") and claim["status"] not in {"descartada", "analise_desatualizada"})
            docs = []
            if "evidence" in tables:
                for (payload,) in db.execute("SELECT payload FROM evidence WHERE claim_id=? ORDER BY id", (cid,)):
                    _check(cancelled)
                    doc = json.loads(payload)
                    docs.append({**_pick(doc, DOCUMENT_FIELDS), "locators": [_pick(block, ("id", "locator")) for block in doc.get("blocks", [])]})
            record = previous_snapshot({"session_id": sid, "event": event, "claim": claim, "case_revision": revision,
                "source_current": valid, "transcript_reviewed": bool(source.get("human_reviewed")),
                "decision": case["decision"], "plan": case.get("plan"), "documents": docs})
            result.append({"key": f"{sid}/{cid}", "folder": str(folder), "snapshot": record})
        return result


def refresh_checked_case(entry):
    match = next((item for item in read_checked_cases(entry["folder"]) if item["key"] == entry["key"]), None)
    if not match or match["snapshot"]["fingerprint"] != entry["snapshot"]["fingerprint"]:
        raise ValueError("A checagem de origem mudou ou deixou de ter decisão. Atualize a consulta antes de registrar.")
    return match["snapshot"]


def scan_checked_cases(root, cancelled=None):
    """Somente subpastas imediatas; cópias idênticas deduplicam, identidades divergentes são omitidas."""
    root = Path(root).resolve()
    _check(cancelled)
    if not root.is_dir():
        return {"entries": [], "warnings": ["Pasta de sessões inexistente. Escolha a pasta que contém as gravações."], "sessions": 0}
    entries, conflicts, warnings, count = {}, set(), [], 0
    for folder in sorted(root.iterdir(), key=lambda value: value.name.casefold()):
        _check(cancelled)
        if not folder.is_dir():
            continue
        if folder.resolve().parent != root:
            warnings.append(f"{folder.name}: atalho para fora da pasta omitido.")
            continue
        if not (folder / "review.sqlite3").is_file():
            if (folder / "session.json").is_file():
                warnings.append(f"{folder.name}: ainda sem banco de revisão; abra a sessão normalmente primeiro.")
            continue
        try:
            rows = read_checked_cases(folder, cancelled, include_unreviewed=True)
            count += 1
            for row in rows:
                key = row["key"]
                if key in entries and (entries[key]["snapshot"] or {}).get("fingerprint") != (row["snapshot"] or {}).get("fingerprint"):
                    conflicts.add(key)
                else:
                    entries.setdefault(key, row)
        except (OSError, sqlite3.Error, ValueError, KeyError, TypeError, IndexError, AttributeError):
            _check(cancelled)
            warnings.append(f"{folder.name}: banco indisponível, incompatível ou inválido; sessão omitida. Abra e confira a sessão separadamente.")
    for key in sorted(conflicts):
        entries.pop(key, None)
        warnings.append(f"Identidade duplicada com conteúdo divergente ({key}); caso omitido. Confira as cópias antes de consultar.")
    _check(cancelled)
    return {"entries": [entry for entry in entries.values() if entry["snapshot"] is not None], "warnings": warnings, "sessions": count}


def filter_checked_cases(entries, query="", topic=None, verdict=None, include_historical=False):
    words = normalize(query).split()
    result = []
    for entry in entries:
        data, claim = entry["snapshot"], entry["snapshot"]["claim"]
        if not include_historical and not data["source_current"]:
            continue
        if topic is not None and (claim.get("topic") or "") != topic:
            continue
        if verdict is not None and data["decision"]["verdict"] != verdict:
            continue
        text = normalize(" ".join(str(value or "") for value in (*data["event"].values(), *claim.values(), *data["decision"].values(),
                                          *(data.get("plan") or {}).values())))
        if all(word in text for word in words):
            result.append(entry)
    return sorted(result, key=lambda row: (row["snapshot"]["decision"]["at"], row["key"]), reverse=True)


def render_previous(data):
    claim, decision, plan = data["claim"], data["decision"], data.get("plan") or {}
    lines = ["Checagem anterior · referência para pesquisa", "Decisão registrada no contexto de origem; a equivalência com outra fala precisa de conferência.",
        "Origem atual no instante da consulta." if data["source_current"] else "HISTÓRICA: fala ou extração de origem foi alterada/descartada.",
        "Transcrição conferida por pessoa." if data["transcript_reviewed"] else "Transcrição de origem ainda sem conferência humana.",
        f"Evento: {data['event'].get('title', '')} · {data['event'].get('event_date', '')}",
        "Tipo de conteúdo: " + EVENT_KINDS.get(data["event"].get("event_kind"),"Não informado"),
        f"Sessão: {data['session_id']} · afirmação {claim['id']}",
        f"Fala {claim['revision']} · extração {claim.get('claim_revision', 1)} · dossiê {data['case_revision']}",
        f"Participante: {claim.get('speaker') or 'Não identificado'} · captura {claim['start']}–{claim['end']} s",
        "", "Fala literal: " + claim["quote"], "Resumo: " + claim["summary"], "Contexto: " + claim.get("context", ""), "",
        f"Decisão humana anterior: {VERDICTS[decision['verdict']]} · {decision['at']}",
        "Revisor anterior: " + decision["reviewer"], "Justificativa anterior: " + decision["reason"], "",
        "Recortes registrados no plano anterior (não inferidos):"]
    for key, label in (("question", "Pergunta"), ("period", "Período"), ("territory", "Território"), ("indicator", "Indicador"),
                       ("comparison", "Comparação"), ("notes", "Notas / método a conferir")):
        lines.append(f"{label}: {plan.get(key) or 'Não definido'}")
    if plan.get("needs_review"):
        lines.append("Plano anterior precisa de nova conferência.")
    lines += ["", "Fontes do caso anterior; consultar os documentos e a validade antes de usá-las:"]
    for doc in data["documents"]:
        lines += [f"{doc.get('title', '')} · {doc.get('institution', '')}", doc.get("url", ""),
            f"Origem: {doc.get('acquisition', 'unknown')} · acesso: {doc.get('accessed_at') or 'Não confirmado'}",
            f"Publicação: {doc.get('published_at') or 'Não identificada'} · SHA-256: {doc.get('sha256') or 'Não registrado'}",
            "Localizadores: " + "; ".join(str(block.get("locator", "")) for block in doc["locators"]),
            "Avisos: " + "; ".join(doc.get("warnings", []))]
    if not data["documents"]:
        lines.append("Sem documentos coletados no caso anterior.")
    lines += ["", "Esta referência não acrescenta evidências nem aprova uma nova conclusão."]
    return "\n".join(lines)


class PreviousChecksTask:
    def __init__(self, folder, emit):
        self.folder, self.emit = folder, emit
        self.token, self.pending = "previous-checks-" + uuid.uuid4().hex, 1
        self.cancelled = threading.Event()

    def start(self):
        threading.Thread(target=self._run, name="previous-checks", daemon=True).start()

    def cancel(self):
        self.cancelled.set()

    def _run(self):
        result = {"token": self.token, "success": False}
        try:
            result.update(scan_checked_cases(self.folder, self.cancelled))
            _check(self.cancelled)
            result["success"] = True
        except InterruptedError:
            result["message"] = "Consulta cancelada. A lista anterior foi preservada."
        except Exception:
            result["message"] = "Não foi possível consultar a pasta. Confira sua disponibilidade e a permissão de leitura."
        finally:
            self.pending = 0
            self.emit("previous_checks_done", result)
