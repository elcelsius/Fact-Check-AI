"""Dossiês versionados: evidências, análise preliminar e decisão humana separadas."""

import json
import os
import uuid

from .review import now, process_alive
from .timeline import describe_time, timestamp
from .grouping import active as active_source
from .planning import ORIGINS, PLAN_FIELDS, SCOPES, validate_plan
from .discovery import search_basis, validate_query
from .priorities import describe_priority, priority_payload, read_priority
from .assignments import assignment_payload, describe_assignment, read_assignment, read_assignment_history


VERDICTS = {"confirmada": "Confirmada", "contradita": "Contradita", "inconclusiva": "Inconclusiva"}


class DossierStore:
    def __init__(self, review):
        self.review = review
        with review.connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS cases (claim_id TEXT PRIMARY KEY, revision INTEGER, payload TEXT);
                CREATE TABLE IF NOT EXISTS evidence (id TEXT PRIMARY KEY, claim_id TEXT, payload TEXT);
                CREATE TABLE IF NOT EXISTS research_jobs (id TEXT PRIMARY KEY, claim_id TEXT, revision INTEGER, status TEXT, payload TEXT);
                CREATE INDEX IF NOT EXISTS evidence_claim ON evidence(claim_id);
                CREATE TABLE IF NOT EXISTS discoveries (id TEXT PRIMARY KEY, claim_id TEXT, payload TEXT);
                CREATE INDEX IF NOT EXISTS discoveries_claim ON discoveries(claim_id);
            """)

    @staticmethod
    def _claim(db, cid, active=False):
        row = db.execute("SELECT payload FROM claims WHERE id=?", (cid,)).fetchone()
        if not row:
            raise ValueError("Afirmação não encontrada.")
        claim = json.loads(row[0])
        source = json.loads(db.execute("SELECT payload FROM paragraphs WHERE id=?", (claim["paragraph_id"],)).fetchone()[0])
        valid = not (claim.get("source_outdated") or claim["status"] in {"descartada", "analise_desatualizada"}
                     or source["revision"] != claim["revision"] or source["needs_rebase"] or not active_source(source))
        if active and not valid:
            raise ValueError("A afirmação foi alterada ou descartada. Use a triagem da revisão atual.")
        return claim, valid

    @staticmethod
    def _case(db, cid):
        row = db.execute("SELECT revision,payload FROM cases WHERE claim_id=?", (cid,)).fetchone()
        if row:
            return row[0], json.loads(row[1])
        return 0, {"preliminary": None, "decision": None}

    def _save(self, db, cid, revision, case, kind):
        if "plan" not in case:
            _, previous = self._case(db, cid)
            case = {**case, "plan": previous.get("plan")}
        db.execute("INSERT OR REPLACE INTO cases VALUES (?,?,?)", (cid, revision, json.dumps(case, ensure_ascii=False)))
        self.review._audit(db, kind, {"claim_id": cid, "case_revision": revision, **case})

    def snapshot(self, cid):
        with self.review.connection() as db:
            claim, valid = self._claim(db, cid)
            revision, case = self._case(db, cid)
            documents = [json.loads(row[0]) for row in db.execute("SELECT payload FROM evidence WHERE claim_id=? ORDER BY rowid", (cid,))]
            jobs = [{"id": jid, "status": status, **json.loads(payload)} for jid, status, payload in
                    db.execute("SELECT id,status,payload FROM research_jobs WHERE claim_id=? ORDER BY rowid", (cid,))]
            debate = json.loads(db.execute("SELECT payload FROM debate WHERE id=1").fetchone()[0])
            ref_revision, offset = db.execute("SELECT revision,offset_seconds FROM video_reference WHERE id=1").fetchone()
            queries = [json.loads(payload) for (payload,) in db.execute("SELECT payload FROM history WHERE kind='search_query_opened'")
                       if json.loads(payload).get("claim_id") == cid]
            discoveries = [{"id": sid, **json.loads(payload)} for sid, payload in
                           db.execute("SELECT id,payload FROM discoveries WHERE claim_id=? ORDER BY rowid", (cid,))]
            for batch in discoveries:
                batch["current"] = bool(valid and batch["basis"] == search_basis(claim, case.get("plan")))
            priority = priority_payload(claim, read_priority(db, cid), valid)
            assignment = assignment_payload(claim, read_assignment(db, cid), valid)
            return {"claim": claim, "valid": valid, "revision": revision, "documents": documents,
                    "debate": debate, "video_reference": {"revision": ref_revision, "offset_seconds": offset},
                    "jobs": jobs, "queries": queries, "discoveries": discoveries, "plan": case.get("plan"), **case,
                    "priority": priority, "assignment": assignment, "assignment_history": read_assignment_history(db, cid)}

    def save_plan(self, cid, expected_revision, plan, origin="operator_input"):
        if origin not in ORIGINS:
            raise ValueError("Origem do plano inválida.")
        plan = {**validate_plan(plan), "origin": origin}
        with self.review.connection() as db:
            claim, _ = self._claim(db, cid, active=True)
            revision, case = self._case(db, cid)
            if revision != expected_revision:
                raise ValueError("O dossiê mudou. Reabra o planejamento antes de salvar.")
            previous = case.get("plan") or {}
            same = {key: previous.get(key) for key in (*PLAN_FIELDS, "origin")} == plan
            if same and not previous.get("needs_review") and previous.get("claim_revision", 1) == claim.get("claim_revision", 1):
                return False
            case = {**case, "plan": {**plan, "updated_at": now(), "claim_revision": claim.get("claim_revision", 1),
                                    "needs_review": False}, "preliminary": None, "decision": None}
            self._save(db, cid, revision + 1, case, "check_plan_changed")
            return True

    def begin(self, cid, kind, query=None):
        if kind not in {"collect", "import", "analyze", "discover"}:
            raise ValueError("Tarefa de pesquisa inválida.")
        if kind == "discover":
            query = validate_query(query)
        with self.review.connection() as db:
            claim, _ = self._claim(db, cid, active=True)
            revision, case = self._case(db, cid)
            if db.execute("SELECT 1 FROM research_jobs WHERE claim_id=? AND status='running'", (cid,)).fetchone():
                raise ValueError("Já existe pesquisa em andamento para esta afirmação.")
            if kind == "analyze" and not db.execute("SELECT 1 FROM evidence WHERE claim_id=?", (cid,)).fetchone():
                raise ValueError("Colete ao menos uma fonte antes de analisar.")
            jid = uuid.uuid4().hex
            payload = {"kind": kind, "started_at": now(), "owner_pid": os.getpid()}
            if kind == "discover":
                payload.update(query=query, basis=search_basis(claim, case.get("plan")))
            db.execute("INSERT INTO research_jobs VALUES (?,?,?,?,?)", (jid, cid, revision, "running", json.dumps(payload)))
            return jid

    def _accept(self, db, jid):
        cid, revision, status = db.execute("SELECT claim_id,revision,status FROM research_jobs WHERE id=?", (jid,)).fetchone()
        _, valid = self._claim(db, cid)
        current, case = self._case(db, cid)
        if not valid or status != "running" or revision != current:
            if status == "running":
                db.execute("UPDATE research_jobs SET status='stale' WHERE id=?", (jid,))
            return None
        return cid, current, case

    def finish(self, jid, result, engine=None):
        with self.review.connection() as db:
            accepted = self._accept(db, jid)
            if accepted is None:
                return False
            cid, revision, case = accepted
            payload = json.loads(db.execute("SELECT payload FROM research_jobs WHERE id=?", (jid,)).fetchone()[0])
            if payload["kind"] == "discover":
                if result["query"] != payload["query"]:
                    raise ValueError("O resultado pertence a outra consulta.")
                batch = {**result, "basis": payload["basis"], "engine": engine or {}}
                db.execute("INSERT INTO discoveries VALUES (?,?,?)", (jid, cid, json.dumps(batch, ensure_ascii=False)))
                self.review._audit(db, "sources_discovered", {"claim_id": cid, "id": jid, **batch})
            elif payload["kind"] in {"collect", "import"}:
                existing = db.execute("SELECT payload FROM evidence WHERE claim_id=?", (cid,)).fetchall()
                duplicate = any(doc["url"] == result["url"] and doc["sha256"] == result["sha256"]
                                and (doc.get("acquisition", "remote_fetch") == result.get("acquisition", "remote_fetch")
                                     or doc.get("acquisition", "remote_fetch") == "remote_fetch")
                                for (raw,) in existing for doc in [json.loads(raw)])
                if not duplicate:
                    if len(existing) >= 6 and not any(json.loads(raw)["url"] == result["url"] for (raw,) in existing):
                        raise ValueError("O dossiê chegou ao limite inicial de seis fontes. Revise as evidências já coletadas.")
                    # Uma nova coleta da mesma URL substitui a versão ativa, preservando a anterior no histórico.
                    for (raw,) in existing:
                        doc = json.loads(raw)
                        if doc["url"] == result["url"]:
                            self.review._audit(db, "evidence_superseded", doc)
                            db.execute("DELETE FROM evidence WHERE id=?", (doc["id"],))
                    db.execute("INSERT INTO evidence VALUES (?,?,?)", (result["id"], cid, json.dumps(result, ensure_ascii=False)))
                    case = {"preliminary": None, "decision": None}
                    self._save(db, cid, revision + 1, case, "evidence_changed")
            else:
                case = {"preliminary": {**result, "engine": engine or {}, "created_at": now()}, "decision": None}
                self._save(db, cid, revision + 1, case, "preliminary_completed")
            payload.update({"ended_at": now(), "engine": engine or {}})
            db.execute("UPDATE research_jobs SET status='completed',payload=? WHERE id=?", (json.dumps(payload), jid))
            return True

    def fail(self, jid, message, cancelled=False):
        with self.review.connection() as db:
            db.execute("UPDATE research_jobs SET status=?,payload=json_set(payload,'$.error',?,'$.ended_at',?) WHERE id=? AND status='running'",
                       ("cancelled" if cancelled else "failed", message, now(), jid))

    def recover(self):
        recovered = 0
        with self.review.connection() as db:
            for jid, payload in db.execute("SELECT id,payload FROM research_jobs WHERE status='running'").fetchall():
                owner = json.loads(payload).get("owner_pid")
                if not owner or not process_alive(owner):
                    data = {**json.loads(payload), "recovered_at": now(),
                            "error": "Processo responsável encerrado; nova tentativa depende do operador."}
                    db.execute("UPDATE research_jobs SET status='interrupted',payload=? WHERE id=?",
                               (json.dumps(data, ensure_ascii=False), jid))
                    self.review._audit(db, "research_interrupted", {"id": jid, **data})
                    recovered += 1
        return recovered

    def record_query(self, cid, query):
        with self.review.connection() as db:
            self._claim(db, cid)
            self.review._audit(db, "search_query_opened", {"claim_id": cid, "query": query, "provider": "browser-google", "results_retrieved": False})

    def discard_candidate(self, cid, sid, candidate_id, reason):
        if not isinstance(reason, str) or not reason.strip() or len(reason) > 2000:
            raise ValueError("Informe uma justificativa de até 2.000 caracteres.")
        with self.review.connection() as db:
            claim, _ = self._claim(db, cid, active=True)
            _, case = self._case(db, cid)
            row = db.execute("SELECT payload FROM discoveries WHERE id=? AND claim_id=?", (sid, cid)).fetchone()
            if not row:
                raise ValueError("Busca não encontrada.")
            batch = json.loads(row[0])
            if batch["basis"] != search_basis(claim, case.get("plan")):
                raise ValueError("A afirmação ou o plano mudou. Faça uma nova busca.")
            candidate = next((item for item in batch["candidates"] if item["id"] == candidate_id), None)
            if not candidate or candidate["disposition"] != "pending":
                raise ValueError("A candidata já foi descartada ou não existe.")
            candidate.update(disposition="discarded", discard_reason=reason.strip(), discarded_at=now())
            db.execute("UPDATE discoveries SET payload=? WHERE id=?", (json.dumps(batch, ensure_ascii=False), sid))
            self.review._audit(db, "candidate_discarded", {"claim_id": cid, "search_id": sid, **candidate})

    def states(self):
        with self.review.connection() as db:
            states = {}
            with_sources = {row[0] for row in db.execute("SELECT DISTINCT claim_id FROM evidence")}
            for cid, payload in db.execute("SELECT claim_id,payload FROM cases"):
                case = json.loads(payload)
                if not any((case["decision"], case["preliminary"], case.get("plan"), cid in with_sources)):
                    continue
                states[cid] = ("Revisão humana registrada" if case["decision"] else "Análise preliminar pronta" if case["preliminary"] else
                               "Planejamento a conferir" if (case.get("plan") or {}).get("needs_review") else
                               "Fontes coletadas" if cid in with_sources else "Planejamento salvo" if case.get("plan") else "Aguardando pesquisa")
            return states

    def remove_document(self, cid, expected_revision, did, reason):
        if not reason.strip():
            raise ValueError("Informe o motivo para retirar a fonte.")
        with self.review.connection() as db:
            self._claim(db, cid, active=True)
            revision, _ = self._case(db, cid)
            if revision != expected_revision:
                raise ValueError("O dossiê mudou. Confira a versão atual antes de retirar uma fonte.")
            row = db.execute("SELECT payload FROM evidence WHERE id=? AND claim_id=?", (did, cid)).fetchone()
            if not row:
                raise ValueError("Fonte não encontrada.")
            self.review._audit(db, "evidence_removed", {"document": json.loads(row[0]), "reason": reason.strip()})
            db.execute("DELETE FROM evidence WHERE id=? AND claim_id=?", (did, cid))
            self._save(db, cid, revision + 1, {"preliminary": None, "decision": None}, "evidence_changed")

    def decide(self, cid, expected_revision, verdict, reviewer, reason):
        if verdict not in VERDICTS or not reviewer.strip() or not reason.strip() or len(reason) > 10000 or len(reviewer) > 160:
            raise ValueError("Informe classificação, responsável e justificativa.")
        with self.review.connection() as db:
            claim, _ = self._claim(db, cid, active=True)
            revision, case = self._case(db, cid)
            if revision != expected_revision:
                raise ValueError("O dossiê mudou. Reabra a revisão para conferir a versão atual.")
            if verdict != "inconclusiva" and not db.execute("SELECT 1 FROM evidence WHERE claim_id=?", (cid,)).fetchone():
                raise ValueError("Uma conclusão confirmada ou contradita precisa de fonte coletada.")
            if verdict != "inconclusiva" and claim["category"] != "fato":
                raise ValueError("Conclusões factuais exigem uma declaração classificada como fato.")
            case["decision"] = {"verdict": verdict, "reviewer": reviewer.strip(), "reason": reason.strip(), "at": now()}
            self._save(db, cid, revision + 1, case, "human_decision")


def render(snapshot):
    claim = snapshot["claim"]
    reference = snapshot.get("video_reference", {"revision": 0, "offset_seconds": None})
    offset = reference["offset_seconds"]
    decision, preliminary = snapshot["decision"], snapshot["preliminary"]
    state = "DESATUALIZADO — decisões abaixo são históricas" if not snapshot["valid"] else "REVISADO POR PESSOA" if decision else "PENDENTE DE REVISÃO HUMANA"
    lines = ["# Dossiê de checagem · uso interno", "", state, "", "Sem divulgação automática.", "",
             f"Evento: {snapshot['debate']['title']} · {snapshot['debate']['event_date']}",
             f"Afirmação: {claim['id']} · revisão da extração {claim.get('claim_revision', 1)} · revisão da fala {claim['revision']} · dossiê {snapshot['revision']}",
             f"Participante: {claim['speaker'] or 'Não identificado'} · parágrafo {claim['paragraph_id']} · {describe_time(claim, offset)}",
             (f"Referência manual atual: vídeo em {timestamp(offset)} no início da captura · revisão {reference['revision']}."
              if offset is not None else "Referência do vídeo não definida; horários relativos à captura."), "",
             *(["Parágrafos de origem da combinação: " + ", ".join(map(str, claim["source_paragraph_ids"])), ""]
               if len(claim.get("source_paragraph_ids", [])) > 1 else []),
             "## Fala literal", "", claim["quote"], "", "## Contexto", "", claim["context"], ""]
    plan = snapshot.get("plan")
    if claim.get("extraction_review"):
        lines += ["Extração revisada pelo operador; isso não corresponde a decisão factual.",
                  f"Justificativa da revisão: {claim['extraction_review']['reason']}",
                  f"Categoria automática original: {claim.get('automatic_extraction', {}).get('category', 'Não registrada')}", ""]
    lines += ["## Prioridade de revisão", "", describe_priority(snapshot.get("priority")), ""]
    lines += ["## Responsável pelo caso", "", describe_assignment(snapshot.get("assignment")), ""]
    for change in snapshot.get("assignment_history", []):
        previous = (change["previous"] or {}).get("name") or "Sem responsável"
        current = change["current"]
        lines += [f"Histórico · {change['at']} · atribuição {current['revision']}: {previous} → {current['name'] or 'Sem responsável'}",
                  f"Motivo: {current['reason']}",
                  f"Extração {current['claim_revision']} · fala {current['source_revision']}", ""]
    lines += ["## Planejamento da checagem", ""]
    if plan:
        if plan.get("needs_review"):
            lines += ["AFIRMAÇÃO REVISADA: confira novamente a pergunta e os recortes deste plano.", ""]
        lines += [ORIGINS[plan["origin"]], SCOPES[plan["scope"]], f"Pergunta: {plan['question'] or 'Não definida'}",
                  f"Período: {plan['period'] or 'A definir'}", f"Território: {plan['territory'] or 'A definir'}",
                  f"Indicador: {plan['indicator'] or 'A definir'}", f"Comparação: {plan['comparison'] or 'A definir'}",
                  f"Lacunas e observações: {plan['notes'] or 'Não informadas'}", "",
                  "URLs candidatas para pesquisa; não são evidências coletadas:", *plan["candidate_urls"], ""]
    else:
        lines += ["Pergunta e recortes ainda não registrados.", ""]
    lines += ["## Descoberta de fontes · candidatas, não evidências", ""]
    if not snapshot.get("discoveries"):
        lines += ["Nenhuma busca automática registrada.", ""]
    for batch in snapshot.get("discoveries", []):
        lines += [f"Consulta: {batch['query']}", f"Tavily · {batch['searched_at']} · " + ("recortes atuais" if batch["current"] else "versão anterior"),
                  f"Resultados omitidos por domínio, duplicação ou limite: {batch['discarded_count']}", ""]
        credits = batch.get("engine", {}).get("credits")
        lines += [f"Créditos informados pelo provedor: {credits if credits is not None else 'Não informado'}; não representa valor monetário.", ""]
        for item in batch["candidates"]:
            lines += [f"{item['title']} · {item['disposition']}", item["url"]]
            if item.get("discard_reason"):
                lines.append("Motivo do descarte: " + item["discard_reason"])
        lines += ["Títulos e URLs são sugestões do provedor. Coleta e conferência continuam necessárias.", ""]
    lines += ["## Fontes coletadas", ""]
    if not snapshot["documents"]:
        lines.append("Nenhuma fonte coletada. Não há evidências para concluir.")
    for doc in snapshot["documents"]:
        lines.extend([f"### {doc['title']}", "", f"ID: {doc['id']}", f"URL: {doc['url']}",
                      f"Instituição: {doc['institution']} · autoria: {doc['author'] or 'Não identificada'}",
                      f"Publicação: {doc['published_at'] or 'Não identificada'} · acesso à URL: {doc['accessed_at'] or 'Não confirmado'}",
                      f"SHA-256: {doc['sha256']}", *doc["warnings"], ""])
        if doc.get("acquisition") == "local_import":
            lines.extend([f"Origem: cópia importada pelo operador · arquivo: {doc.get('file_name', 'Não informado')}",
                          f"Importação: {doc.get('imported_at', 'Não identificada')} · conteúdo da URL não recuperado nesta coleta.", ""])
        else:
            lines.extend(["Origem: conteúdo recuperado da URL.", ""])
        for block in doc["blocks"]:
            lines.extend([f"[{block['id']}] {block['locator']}", block["text"], ""])
    lines.extend(["## Análise preliminar da IA · não aprovada", ""])
    if preliminary:
        lines.extend([VERDICTS[preliminary["verdict"]], preliminary["summary"], preliminary["reason"], "",
                      "Compatibilidade: " + ", ".join(f"{k}: {v}" for k, v in preliminary["compatibility"].items()),
                      "Lacunas: " + "; ".join(preliminary["gaps"]), ""])
        for citation in preliminary["citations"]:
            lines.extend([f"{citation['relation']} · fonte {citation['document_id']} · trecho {citation['block_id']}",
                          citation["quote"], citation["explanation"], ""])
        lines.append(f"Motor: {preliminary['engine'].get('model', 'Não informado')}")
    else:
        lines.append("Ainda não gerada. A coleta de documentos não equivale a uma conclusão factual.")
    lines.extend(["", "## Decisão humana", ""])
    if decision:
        lines.extend([VERDICTS[decision["verdict"]], f"Responsável: {decision['reviewer']} · {decision['at']}", decision["reason"]])
    else:
        lines.append("Pendente. Todas as sugestões automáticas precisam de validação.")
    lines.extend(["", "## Histórico de pesquisa", ""])
    for query in snapshot.get("queries", []):
        lines.append("Consulta aberta no navegador (resultados não coletados automaticamente): " + query["query"])
    for job in snapshot["jobs"]:
        lines.append(f"{job.get('started_at', '')} · {job.get('kind', '')} · {job['status']} · {job.get('error', '')}")
    lines.extend(["", "Recortes, anterioridade dos dados e independência das fontes exigem conferência humana."])
    return "\n".join(lines) + "\n"
