"""Retrato consistente da sessão, com identificadores estáveis e arquivos atômicos."""

import csv
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile
import threading
import uuid

from . import __version__
from .grouping import active
from .review import now
from .timeline import timestamp
from .planning import PLAN_FIELDS


SCHEMA_VERSION = 1
FORMATS = {"json": "JSON completo", "paragraphs": "CSV · falas", "claims": "CSV · afirmações", "sources": "CSV · fontes",
           "report_json": "Relatório do ensaio · JSON", "report_txt": "Relatório do ensaio · TXT"}
SUFFIXES = {"json": ".json", "paragraphs": ".csv", "claims": ".csv", "sources": ".csv",
            "report_json": ".json", "report_txt": ".txt"}
ENGINE_KEYS = ("name", "provider", "model", "revision", "quantization", "compute", "prompt_version", "seconds")
CLAIM_KEYS = ("analysis_id", "paragraph_id", "revision", "speaker", "start", "end", "quote", "summary", "reason",
              "category", "topic", "location", "period", "indicator", "comparison", "context", "status",
              "review_status", "created_at", "discard_reason", "validation_notes", "context_notes")
SOURCE_KEYS = ("url", "requested_url", "title", "institution", "author", "published_at", "accessed_at", "acquisition",
               "imported_at", "sha256", "text_sha256", "content_type", "extractor", "extractor_version", "truncated", "warnings")


def _pick(data, keys):
    return {key: data[key] for key in keys if key in data}


def _digest(data):
    return sha256(json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf8")).hexdigest()


def _record(session_id, kind, local_id, data):
    record = {"record_id": f"{session_id}/{kind}/{local_id}", **data}
    return {**record, "record_sha256": _digest(record)}


def _engine(data):
    result = _pick(data or {}, ENGINE_KEYS)
    usage = (data or {}).get("usage", {})
    result["usage"] = {key: usage[key] for key in ("promptTokenCount", "candidatesTokenCount", "totalTokenCount",
                       "cachedContentTokenCount", "thoughtsTokenCount") if isinstance(usage.get(key), (int, float))}
    return result


def _check(cancelled):
    if cancelled is not None and cancelled.is_set():
        raise InterruptedError("Exportação cancelada.")


def read_session(review, cancelled=None):
    _check(cancelled)
    # Copiar as linhas na mesma transação; converter textos fora dela libera os escritores cedo.
    with review.connection() as db:
        event_raw = db.execute("SELECT payload FROM debate WHERE id=1").fetchone()[0]
        session_id = db.execute("SELECT session_id FROM session_identity WHERE id=1").fetchone()[0]
        reference_revision, offset = db.execute("SELECT revision,offset_seconds FROM video_reference WHERE id=1").fetchone()
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        raw = {name: db.execute(query).fetchall() if name in tables else [] for name, query in {
            "paragraphs": "SELECT payload FROM paragraphs ORDER BY id",
            "claims": "SELECT payload FROM claims ORDER BY id",
            "analyses": "SELECT id,paragraph_id,revision,status,payload FROM analyses ORDER BY rowid",
            "cases": "SELECT claim_id,revision,payload FROM cases ORDER BY claim_id",
            "evidence": "SELECT id,claim_id,payload FROM evidence ORDER BY id",
            "research_jobs": "SELECT status,payload FROM research_jobs ORDER BY rowid",
        }.items()}
        captured_at = now()
    return {"event_raw": event_raw, "session_id": session_id, "reference_revision": reference_revision,
            "offset": offset, "rows": raw, "captured_at": captured_at}


def snapshot(review, include_inactive=False, cancelled=None):
    return build_snapshot(read_session(review, cancelled), include_inactive, cancelled)


def build_snapshot(records, include_inactive=False, cancelled=None):
    event_raw, session_id = records["event_raw"], records["session_id"]
    reference_revision, offset = records["reference_revision"], records["offset"]
    raw, captured_at = records["rows"], records["captured_at"]
    _check(cancelled)
    paragraphs = {data["paragraph_id"]: data for (payload,) in raw["paragraphs"] for data in [json.loads(payload)]}
    cases = {cid: (revision, json.loads(payload)) for cid, revision, payload in raw["cases"]}
    analyses = {}
    for aid, pid, revision, state, payload in raw["analyses"]:
        _check(cancelled)
        data = json.loads(payload)
        analyses[pid, revision] = {"id": aid, "status": state, "engine": _engine(data.get("engine"))}

    def times(data):
        return {"video_start": data["start"] + offset if offset is not None else None,
                "video_end": data["end"] + offset if offset is not None else None,
                "video_reference_revision": reference_revision}

    claims, dossiers, wanted_claims = [], [], set()
    evidence_claims = {cid for _, cid, _ in raw["evidence"]}
    for (payload,) in raw["claims"]:
        _check(cancelled)
        claim = json.loads(payload)
        source = paragraphs[claim["paragraph_id"]]
        valid = (active(source) and not source["needs_rebase"] and source["revision"] == claim["revision"]
                 and not claim.get("source_outdated") and claim["status"] not in {"descartada", "analise_desatualizada"})
        if not include_inactive and not valid:
            continue
        cid = claim["id"]
        wanted_claims.add(cid)
        revision, case = cases.get(cid, (0, {"preliminary": None, "decision": None}))
        preliminary = case.get("preliminary")
        if preliminary:
            preliminary = {**_pick(preliminary, ("verdict", "summary", "reason", "gaps", "created_at")),
                           "compatibility": _pick(preliminary.get("compatibility", {}), ("period", "location", "indicator", "methodology")),
                           "citations": [_pick(citation, ("document_id", "block_id", "quote", "relation", "explanation"))
                                         for citation in preliminary.get("citations", [])],
                           "engine": _engine(preliminary.get("engine"))}
        decision = case.get("decision")
        if decision:
            decision = _pick(decision, ("verdict", "reviewer", "reason", "at"))
        state = ("historical" if not valid else "human_decision_recorded" if decision else "preliminary" if preliminary
                 else "sources_collected" if cid in evidence_claims else "pending")
        dossiers.append(_record(session_id, "dossier", cid,
            {"claim_id": cid, "revision": revision, "source_current": valid, "state": state,
             "preliminary_current": bool(valid and preliminary), "decision_current": bool(valid and decision),
             "preliminary": preliminary, "decision": decision,
             "plan": _pick(case["plan"], (*PLAN_FIELDS, "origin", "updated_at", "claim_revision", "needs_review")) if case.get("plan") else None}))
        claims.append(_record(session_id, "claim", cid,
            {"claim_id": cid, **_pick(claim, CLAIM_KEYS), **times(claim), "source_current": valid,
             "claim_revision": claim.get("claim_revision", 1),
             "automatic_extraction": _pick(claim["automatic_extraction"], CLAIM_KEYS) if claim.get("automatic_extraction") else None,
             "extraction_review": _pick(claim["extraction_review"], ("origin", "at", "reason")) if claim.get("extraction_review") else None,
             "source_paragraph_ids": claim.get("source_paragraph_ids", [claim["paragraph_id"]]),
             "dossier_revision": revision, "factual_state": state, "engine": _engine(claim.get("engine"))}))

    claims.sort(key=lambda row: (row["start"], row["end"], row["claim_id"]))
    selected = {pid for pid, source in paragraphs.items() if include_inactive or active(source)}
    needed = set(selected) | {claim["paragraph_id"] for claim in claims}
    pending = list(needed)
    while pending:
        source = paragraphs[pending.pop()]
        for pid in source.get("merged_from", []):
            if pid not in needed:
                needed.add(pid)
                pending.append(pid)
    main, origins = [], []
    for source in sorted(paragraphs.values(), key=lambda row: (row["start"], row["end"], row["paragraph_id"])):
        _check(cancelled)
        pid = source["paragraph_id"]
        if pid not in needed:
            continue
        record = _record(session_id, "paragraph", pid, {
            "paragraph_id": pid, **_pick(source, ("revision", "text", "speaker", "start", "end", "closed",
            "human_reviewed", "needs_rebase", "source_version", "hidden_by", "retired", "recovery_closure")), **times(source),
            "active": active(source), "recognition_text": source["original"]["source_text"],
            "source_paragraph_ids": source["original"].get("source_paragraph_ids", [pid]),
            "merged_from": source.get("merged_from", []),
            "triage": analyses.get((pid, source["revision"]), {"id": None, "status": "not_analyzed", "engine": {}}),
        })
        (main if pid in selected else origins).append(record)
    sources = []
    validity = {claim["claim_id"]: claim["source_current"] for claim in claims}
    for did, cid, payload in raw["evidence"]:
        _check(cancelled)
        if cid not in wanted_claims:
            continue
        document = json.loads(payload)
        sources.append(_record(session_id, "source", did,
            {"document_id": did, "claim_id": cid, "claim_source_current": validity[cid], **_pick(document, SOURCE_KEYS),
             "acquisition": document.get("acquisition", "unknown"),
             "url_access_confirmed": document.get("acquisition") == "remote_fetch" and bool(document.get("accessed_at")),
             "blocks": [_pick(block, ("id", "locator", "text")) for block in document.get("blocks", [])]}))
    result = {"format": "factcheck-session", "schema_version": SCHEMA_VERSION, "app_version": __version__,
              "intended_use": "internal_review",
              "scope": "including_inactive" if include_inactive else "current",
              "event": _pick(json.loads(event_raw), ("event_id", "title", "event_date", "source_url", "participants")),
              "session_id": session_id, "video_reference": {"revision": reference_revision, "offset_seconds": offset},
              "paragraphs": main, "origin_paragraphs": origins, "claims": claims, "dossiers": dossiers, "sources": sources}
    return {**result, "content_sha256": _digest(result), "exported_at": captured_at}


COMMON = ("formato_versao", "evento_id", "sessao_id", "exportado_em", "snapshot_sha256", "registro_id", "registro_sha256")
COLUMNS = {
    "paragraphs": (*COMMON, "paragrafo_id", "revisao", "ativo", "concluido", "encerramento_recuperado_em", "motivo_encerramento_recuperado", "transcricao_conferida", "precisa_reconciliar",
                   "participante", "inicio_captura_s", "fim_captura_s", "inicio_video_s", "fim_video_s", "inicio_video", "fim_video",
                   "referencia_revisao", "origens_ids", "componentes_ids", "substituido_por", "desfeito", "estado_triagem", "analise_id", "texto", "texto_reconhecido"),
    "claims": (*COMMON, "afirmacao_id", "afirmacao_revisao", "extracao_revisada", "categoria_automatica", "citacao_automatica",
               "motivo_revisao_extracao", "revisao_extracao_em", "paragrafo_id", "revisao_fala", "origens_ids", "origem_atual", "estado_triagem", "categoria",
               "participante", "inicio_captura_s", "fim_captura_s", "inicio_video", "fim_video", "referencia_revisao", "citacao", "resumo", "motivo",
               "tema", "local", "periodo", "indicador", "comparacao", "contexto_analisado", "analise_id", "modelo", "estado_dossie", "dossie_revisao",
               "preliminar_classificacao", "preliminar_resumo", "preliminar_justificativa", "preliminar_atual", "evidencias_citadas", "decisao_humana_classificacao", "decisao_humana_responsavel",
               "decisao_humana_justificativa", "decisao_humana_em", "decisao_atual", "motivo_descarte", "fontes_urls", "fonte_ids",
               "plano_pergunta", "plano_situacao", "plano_periodo", "plano_territorio", "plano_indicador", "plano_comparacao",
               "plano_observacoes", "plano_urls_candidatas", "plano_origem", "plano_precisa_revisao"),
    "sources": (*COMMON, "fonte_id", "afirmacao_id", "origem_afirmacao_atual", "titulo", "instituicao", "autoria", "url", "publicado_em",
                "acessado_em", "origem", "acesso_url_confirmado", "importado_em", "sha256", "texto_sha256", "leitura_limitada", "avisos", "localizadores"),
}


def _csv_cell(value):
    if value is None:
        return ""
    if isinstance(value, bool):
        return "sim" if value else "nao"
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if isinstance(value, str):
        index = 0
        while index < len(value) and (value[index].isspace() or value[index] == "\ufeff"):
            index += 1
        probe = value[index:]
        # CSV voltado à leitura em planilha; JSON preserva o texto literal para integração.
        if value.startswith(("\t", "\r", "\n")) or probe.startswith(tuple("=+-@＝＋－＠")):
            return "\t" + value
    return value


def csv_rows(data, kind):
    dossiers = {row["claim_id"]: row for row in data["dossiers"]}
    common = {"formato_versao": data["schema_version"], "evento_id": data["event"]["event_id"], "sessao_id": data["session_id"],
              "exportado_em": data["exported_at"], "snapshot_sha256": data["content_sha256"]}
    for row in data[kind]:
        record = {**common, "registro_id": row["record_id"], "registro_sha256": row["record_sha256"]}
        if kind in {"paragraphs", "claims"}:
            record.update(paragrafo_id=row["paragraph_id"], participante=row.get("speaker"),
                          inicio_captura_s=row["start"], fim_captura_s=row["end"],
                          inicio_video=timestamp(row["video_start"]) if row["video_start"] is not None else None,
                          fim_video=timestamp(row["video_end"]) if row["video_end"] is not None else None,
                          referencia_revisao=row["video_reference_revision"], origens_ids=row["source_paragraph_ids"])
        if kind == "paragraphs":
            closure = row.get("recovery_closure", {})
            record.update(revisao=row["revision"], ativo=row["active"], concluido=row["closed"], transcricao_conferida=row["human_reviewed"],
                          encerramento_recuperado_em=closure.get("at"), motivo_encerramento_recuperado=closure.get("reason"),
                          precisa_reconciliar=row["needs_rebase"], inicio_video_s=row["video_start"], fim_video_s=row["video_end"],
                          componentes_ids=row["merged_from"], substituido_por=row.get("hidden_by"), desfeito=row.get("retired", False),
                          estado_triagem=row["triage"]["status"], analise_id=row["triage"]["id"], texto=row["text"], texto_reconhecido=row["recognition_text"])
        elif kind == "claims":
            dossier = dossiers[row["claim_id"]]
            preliminary, decision = dossier["preliminary"] or {}, dossier["decision"] or {}
            documents = [doc for doc in data["sources"] if doc["claim_id"] == row["claim_id"]]
            plan = dossier.get("plan") or {}
            extracted, edited = row.get("automatic_extraction") or {}, row.get("extraction_review") or {}
            record.update(afirmacao_id=row["claim_id"], revisao_fala=row["revision"], origem_atual=row["source_current"], estado_triagem=row["status"],
                          afirmacao_revisao=row.get("claim_revision", 1), extracao_revisada=bool(edited),
                          categoria_automatica=extracted.get("category", row["category"]), citacao_automatica=extracted.get("quote", row["quote"]),
                          motivo_revisao_extracao=edited.get("reason"), revisao_extracao_em=edited.get("at"),
                          categoria=row["category"], citacao=row["quote"], resumo=row["summary"], motivo=row["reason"], tema=row.get("topic"),
                          local=row.get("location"), periodo=row.get("period"), indicador=row.get("indicator"), comparacao=row.get("comparison"),
                          contexto_analisado=row["context"], analise_id=row["analysis_id"], modelo=row["engine"].get("model"),
                          estado_dossie=dossier["state"], dossie_revisao=dossier["revision"], preliminar_classificacao=preliminary.get("verdict"),
                          preliminar_resumo=preliminary.get("summary"), preliminar_justificativa=preliminary.get("reason"),
                          preliminar_atual=dossier["preliminary_current"], evidencias_citadas=preliminary.get("citations", []),
                          decisao_humana_classificacao=decision.get("verdict"), decisao_humana_responsavel=decision.get("reviewer"),
                          decisao_humana_justificativa=decision.get("reason"), decisao_humana_em=decision.get("at"), decisao_atual=dossier["decision_current"],
                          motivo_descarte=row.get("discard_reason"), fontes_urls=[doc["url"] for doc in documents], fonte_ids=[doc["document_id"] for doc in documents])
            record.update(plano_pergunta=plan.get("question"), plano_situacao=plan.get("scope"), plano_periodo=plan.get("period"),
                          plano_territorio=plan.get("territory"), plano_indicador=plan.get("indicator"), plano_comparacao=plan.get("comparison"),
                          plano_observacoes=plan.get("notes"), plano_urls_candidatas=plan.get("candidate_urls", []), plano_origem=plan.get("origin"),
                          plano_precisa_revisao=plan.get("needs_review", False))
        else:
            record.update(fonte_id=row["document_id"], afirmacao_id=row["claim_id"], origem_afirmacao_atual=row["claim_source_current"], titulo=row.get("title"),
                          instituicao=row.get("institution"), autoria=row.get("author"), url=row["url"], publicado_em=row.get("published_at"),
                          acessado_em=row.get("accessed_at"), origem=row["acquisition"], acesso_url_confirmado=row["url_access_confirmed"],
                          importado_em=row.get("imported_at"), sha256=row.get("sha256"), texto_sha256=row.get("text_sha256"),
                          leitura_limitada=row.get("truncated", False), avisos=row.get("warnings", []),
                          localizadores=[_pick(block, ("id", "locator")) for block in row["blocks"]])
        yield {key: _csv_cell(record.get(key)) for key in COLUMNS[kind]}


def write_export(data, target, kind, review_folder, cancelled=None, commit_lock=None):
    if kind not in FORMATS:
        raise ValueError("Formato de exportação inválido.")
    target = Path(target).resolve()
    suffix = SUFFIXES[kind]
    if target.suffix.lower() != suffix:
        raise ValueError(f"Escolha um arquivo com extensão {suffix}.")
    folder = Path(review_folder).resolve()
    if target.is_relative_to(folder) and not target.is_relative_to(folder / "exports"):
        raise ValueError("Dentro da sessão, salve na subpasta exports para preservar os arquivos originais.")
    _check(cancelled)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf8" if kind in {"json", "report_json", "report_txt"} else "utf-8-sig", newline="",
                                         dir=target.parent, prefix=".factcheck-export-", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            if kind in {"json", "report_json"}:
                for chunk in json.JSONEncoder(ensure_ascii=False, indent=2, allow_nan=False).iterencode(data):
                    _check(cancelled)
                    stream.write(chunk)
                stream.write("\n")
            elif kind == "report_txt":
                from .reporting import render_report
                stream.write(render_report(data))
            else:
                writer = csv.DictWriter(stream, fieldnames=COLUMNS[kind], delimiter=";", quoting=csv.QUOTE_ALL, lineterminator="\r\n")
                writer.writeheader()
                for row in csv_rows(data, kind):
                    _check(cancelled)
                    writer.writerow(row)
            stream.flush()
            os.fsync(stream.fileno())
        with commit_lock or threading.RLock():
            _check(cancelled)
            os.replace(temporary, target)
        return target
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


class ExportTask:
    def __init__(self, review, target, kind, include_inactive, emit):
        self.review, self.target, self.kind, self.include_inactive, self.emit = review, target, kind, include_inactive, emit
        self.token, self.pending = "export-" + uuid.uuid4().hex, 1
        self.cancelled, self.lock = threading.Event(), threading.RLock()

    def start(self):
        threading.Thread(target=self._run, name="session-export", daemon=True).start()

    def cancel(self):
        with self.lock:
            self.cancelled.set()

    def _run(self):
        result = {"token": self.token, "success": False}
        try:
            if self.kind in {"report_json", "report_txt"}:
                from .reporting import session_report
                data = session_report(self.review, self.cancelled)
            else:
                data = snapshot(self.review, self.include_inactive, self.cancelled)
            output = write_export(data, self.target, self.kind, self.review.folder, self.cancelled, self.lock)
            result.update(success=True, message=f"Arquivo exportado: {output}", path=str(output))
        except InterruptedError:
            result["message"] = "Exportação cancelada. Nenhum arquivo foi substituído."
        except ValueError as exc:
            result["message"] = str(exc)
        except Exception:
            result["message"] = "Não foi possível exportar. Confira o destino, a permissão de escrita e o espaço disponível."
        finally:
            self.pending = 0
            self.emit("export_done", result)
