"""Relatório operacional local: denominadores explícitos e medições registradas."""

from collections import Counter
from datetime import datetime
from hashlib import sha256
import json
import math
from statistics import median

from . import __version__
from .exports import _check, build_snapshot, read_session
from .recovery import STATE_NAMES, capture_state, inspect_audio


ISSUES = {"audio_padding", "transcription_error", "transcription_backlog", "capture_error", "metadata_error", "device_status"}
STATES = ("running", "completed", "failed", "cancelled", "interrupted", "stale", "other")


def statistics(values):
    usable = sorted(value for value in values if type(value) in {int, float} and math.isfinite(value) and value >= 0)
    p95 = None
    if len(usable) >= 20:
        position = (len(usable) - 1) * .95
        lower = math.floor(position)
        p95 = usable[lower] + (usable[math.ceil(position)] - usable[lower]) * (position - lower)
    return {"observations": len(usable), "excluded": len(values) - len(usable),
            "minimum": min(usable) if usable else None, "median": median(usable) if usable else None,
            "p95": p95, "maximum": max(usable) if usable else None}


def ratio(numerator, denominator):
    return {"numerator": numerator, "denominator": denominator,
            "fraction": numerator / denominator if denominator else None}


def elapsed(end, start):
    try:
        end_time, start_time = datetime.fromisoformat(end), datetime.fromisoformat(start)
        if end_time.utcoffset() is None or start_time.utcoffset() is None:
            return None
        value = (end_time - start_time).total_seconds()
        return value if value >= 0 else None
    except (TypeError, ValueError):
        return None


def read_events(folder, cancelled):
    events, invalid, bytes_read = [], [], 0
    path = folder / "events.jsonl"
    try:
        with path.open("rb") as stream:
            for number, line in enumerate(stream, 1):
                _check(cancelled)
                bytes_read += len(line)
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                    if not isinstance(data, dict) or not isinstance(data.get("kind"), str):
                        raise ValueError
                except (ValueError, UnicodeDecodeError):
                    invalid.append(number)
                    continue
                # O relatório nunca copia falas, mensagens livres de erro ou credenciais.
                events.append({key: data[key] for key in ("kind", "elapsed_seconds", "processing_seconds", "delivery_lag_seconds",
                              "queued_chunks", "capture_started_at", "at", "code") if key in data})
    except FileNotFoundError:
        return [], {"present": False, "bytes_read": 0, "invalid_lines": 0, "first_invalid_line": None}
    return events, {"present": True, "bytes_read": bytes_read, "invalid_lines": len(invalid),
                    "first_invalid_line": invalid[0] if invalid else None}


def session_report(review, cancelled=None):
    if capture_state(review.folder)[0] == "active":
        raise ValueError("Encerre a captura antes de gerar o relatório do ensaio.")
    records = read_session(review, cancelled)
    data = build_snapshot(records, True, cancelled)
    events, log = read_events(review.folder, cancelled)
    notices = []
    try:
        metadata = json.loads((review.folder / "session.json").read_text(encoding="utf8"))
        if not isinstance(metadata, dict):
            raise ValueError
    except (OSError, ValueError, UnicodeDecodeError):
        metadata = {}
        notices.append("Metadados da captura indisponíveis; os registros do banco foram mantidos no relatório.")
    if not log["present"]:
        notices.append("Log de eventos ausente. Tempos não registrados permanecem indisponíveis.")
    if log["invalid_lines"]:
        notices.append(f"Log parcial: {log['invalid_lines']} linha(s) inválida(s), a partir da linha {log['first_invalid_line']}.")
    paragraphs = [row for row in data["paragraphs"] if row["active"]]
    current = [row for row in data["claims"] if row["source_current"]]
    factual = [row for row in current if row["category"] == "fato"]
    dossiers = {row["claim_id"]: row for row in data["dossiers"]}
    with_sources = {row["claim_id"] for row in data["sources"] if row["claim_source_current"]}
    flow = Counter()
    for claim in factual:
        _check(cancelled)
        cid, case = claim["claim_id"], dossiers[claim["claim_id"]]
        stage = ("human_decided" if case["decision_current"] else "preliminary_pending_human" if case["preliminary_current"]
                 else "sources_only" if cid in with_sources else "pending_sources")
        flow[stage] += 1
    reviewed = flow["human_decided"]
    plans = [dossiers[row["claim_id"]].get("plan") for row in current if dossiers[row["claim_id"]].get("plan")]
    analyzed = sum(row["triage"]["status"] == "completed" for row in paragraphs)
    closed = sum(row["closed"] for row in paragraphs)
    chunks = [row for row in events if row["kind"] == "transcription_chunk"]
    deliveries = [row for row in events if row["kind"] == "transcript_delivered"]
    first_partial = statistics([row.get("elapsed_seconds") for row in events if row["kind"] == "first_partial"])
    first_stable = statistics([row.get("elapsed_seconds") for row in deliveries])
    starts = [row for row in events if row["kind"] == "started"]
    candidate = metadata.get("capture_started_at") or (starts[0].get("capture_started_at") if starts else None)
    start = candidate if elapsed(candidate, candidate) is not None else None
    anchor = "capture_started_at" if start else "not_recorded"
    if not start and starts:
        candidate = starts[0].get("at")
        if elapsed(candidate, candidate) is not None:
            start, anchor = candidate, "started_event_approximation"
    decisions = [(claim, dossiers[claim["claim_id"]]["decision"]) for claim in factual
                 if dossiers[claim["claim_id"]]["decision_current"]]
    decision_seconds = statistics([elapsed(decision.get("at"), claim.get("created_at")) for claim, decision in decisions])
    since_capture = statistics([elapsed(decision.get("at"), start) for _, decision in decisions])
    attempts = {}
    for name in ("analyses", "research_jobs"):
        rows = records["rows"][name]
        counts = Counter((row[3] if name == "analyses" else row[0]) for row in rows)
        attempts[name] = {state: counts[state] for state in STATES if state != "other"}
        attempts[name]["other"] = sum(value for state, value in counts.items() if state not in STATES[:-1])
    triage_times = [json.loads(row[4]).get("engine", {}).get("seconds") for row in records["rows"]["analyses"] if row[3] == "completed"]
    warnings = Counter(row.get("code") if isinstance(row.get("code"), str) and row["code"] in ISSUES else "other"
                       for row in events if row["kind"] == "warning")
    padding = sum(row["kind"] == "audio_padding" for row in events)
    audio = inspect_audio(review.folder)
    if audio["state"] != "ok":
        notices.append(audio["message"])
    if first_partial["minimum"] is None:
        notices.append("Primeira prévia não registrada; pode ser uma sessão antiga, outro motor ou ausência de fala provisória.")
    if not deliveries:
        notices.append("Entrega dos segmentos estabilizados não registrada; não foi estimada a partir dos pacotes.")
    result = {"format": "factcheck-session-report", "schema_version": 1, "app_version": __version__,
              "intended_use": "internal_rehearsal", "session_id": data["session_id"],
              "event": {key: data["event"][key] for key in ("event_id", "title")},
              "session_snapshot_sha256": data["content_sha256"],
              "capture": {"state": capture_state(review.folder)[0], "audio_state": audio["state"],
                          "available_audio_seconds": audio.get("duration"),
                          "transcription_complete": metadata.get("transcription_complete") if type(metadata.get("transcription_complete")) is bool else None,
                          "time_anchor": {"at": start if isinstance(start, str) else None, "source": anchor}},
              "paragraphs": {"active": len(paragraphs), "closed": closed, "unclosed": len(paragraphs) - closed,
                             "human_reviewed": sum(row["human_reviewed"] for row in paragraphs),
                             "needs_reconciliation": sum(row["needs_rebase"] for row in paragraphs),
                             "speaker_unassigned": sum(not row["speaker"] for row in paragraphs),
                             "triage_completed": analyzed, "triage_not_completed": len(paragraphs) - analyzed},
              "claims": {"current": len(current), "by_category": dict(Counter(row["category"] for row in current)),
                         "extraction_revised": sum(bool(row.get("extraction_review")) for row in current),
                         "planning": {"recorded": len(plans), "ai_drafts": sum(plan["origin"] == "ai_draft" for plan in plans),
                                      "needs_context": sum(plan["scope"] == "falta_contexto" for plan in plans),
                                      "possibly_not_checkable": sum(plan["scope"] == "nao_verificavel" for plan in plans),
                                      "needs_revision_review": sum(bool(plan.get("needs_review")) for plan in plans)},
                         "historical_or_discarded": len(data["claims"]) - len(current),
                         "detected_factual": len(factual), "factual_flow": {key: flow[key] for key in
                             ("pending_sources", "sources_only", "preliminary_pending_human", "human_decided")},
                         "human_decisions_on_detected_factual": ratio(reviewed, len(factual))},
              "timing_seconds": {"first_partial": first_partial["minimum"], "first_stabilized_delivery": first_stable["minimum"],
                                 "stabilized_delivery_lag": statistics([row.get("delivery_lag_seconds") for row in deliveries]),
                                 "chunk_processing": statistics([row.get("processing_seconds") for row in chunks]),
                                 "chunk_delivery_lag": statistics([row.get("delivery_lag_seconds") for row in chunks]),
                                 "triage_processing": statistics(triage_times),
                                 "claim_to_current_human_decision": decision_seconds,
                                 "first_current_human_decision_since_capture": since_capture["minimum"]},
              "history": {"attempts": attempts, "capture_warning_codes": dict(warnings), "silence_padding_events": padding,
                          "maximum_logged_asr_queue": statistics([row.get("queued_chunks") for row in chunks])["maximum"]},
              "log": log, "quality": {"human_reference": "not_provided", "precision": None, "recall": None,
                                        "transcript_word_error_rate": None},
              "limitations": ["Contagens e decisões descrevem registros salvos; não medem precisão ou cobertura das falas reais.",
                              "A proporção de decisões usa as extrações atuais classificadas como factuais, incluindo revisões do operador.",
                              "P95 é calculado por interpolação linear a partir de 20 observações válidas; valores ausentes ou negativos são excluídos.",
                              "Processamento e atraso dos pacotes não equivalem ao tempo para estabilizar uma palavra.",
                              "O tempo até a decisão usa o relógio civil, inclui esperas e pode ser afetado por ajustes de relógio; não mede esforço humano.",
                              "O banco é lido em uma transação; metadados, áudio e log são lidos separadamente após a captura.",
                              "O relatório não libera o piloto ao vivo; falta avaliação contra referência humana."], "notices": notices}
    digest = sha256(json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False, separators=(",", ":")).encode()).hexdigest()
    return {**result, "content_sha256": digest, "generated_at": records["captured_at"]}


def render_report(report):
    def number(value, unit=""):
        return "Não registrado" if value is None else f"{value:.3f}{unit}"

    def distribution(label, values):
        return (f"{label}: n={values['observations']}; excluídos={values['excluded']}; "
                f"mediana={number(values['median'], ' s')}; P95={number(values['p95'], ' s')}")

    def attempts(counts):
        return "; ".join(f"{label}={counts[state]}" for state, label in
                         (("running", "em andamento"), ("completed", "concluídas"), ("failed", "falhas"),
                          ("cancelled", "canceladas"), ("interrupted", "interrompidas"), ("stale", "desatualizadas"), ("other", "outras")))

    paragraphs, claims, timing = report["paragraphs"], report["claims"], report["timing_seconds"]
    planning = claims.get("planning")
    ratio_value = claims["human_decisions_on_detected_factual"]
    lines = ["RELATÓRIO DO ENSAIO · USO INTERNO", "", f"Evento: {report['event']['title']}",
             f"Sessão: {report['session_id']}", f"Gerado em: {report['generated_at']}",
             f"Versão do relatório: {report['app_version']}", "", f"Estado da captura: {STATE_NAMES[report['capture']['state']]}",
             f"Dados de áudio presentes: {number(report['capture']['available_audio_seconds'], ' s')}",
             "Transcrição integralmente finalizada, conforme metadados: " +
             {True: "Sim", False: "Não", None: "Não registrado"}[report['capture']['transcription_complete']], "",
             f"Falas ativas: {paragraphs['active']} · conferidas por pessoa: {paragraphs['human_reviewed']}",
             f"Parágrafos sem encerramento: {paragraphs['unclosed']} · origem a reconciliar: {paragraphs['needs_reconciliation']}",
             f"Participante indefinido: {paragraphs['speaker_unassigned']} · sem triagem concluída: {paragraphs['triage_not_completed']}",
             f"Afirmações atuais: {claims['current']} · históricas/descartadas: {claims['historical_or_discarded']}",
             f"Extrações revisadas pelo operador: {claims.get('extraction_revised', 'Não registrado')}",
             f"Categorias atuais: {json.dumps(claims['by_category'], ensure_ascii=False)}",
             f"Extrações atuais classificadas como factuais: {claims['detected_factual']}",
             (f"Planos registrados: {planning['recorded']} · rascunhos de IA: {planning['ai_drafts']} · "
              f"com contexto pendente: {planning['needs_context']} · possivelmente não verificáveis: {planning['possibly_not_checkable']} · "
              f"a conferir após revisão da extração: {planning.get('needs_revision_review', 'Não registrado')}"
              if planning is not None else "Planejamento: não registrado neste relatório antigo."),
             f"Decisão humana nas factuais atuais: {ratio_value['numerator']}/{ratio_value['denominator']}" +
             (f" ({ratio_value['fraction']:.1%})" if ratio_value['fraction'] is not None else " (sem denominador)"),
             f"Aguardando fontes: {claims['factual_flow']['pending_sources']}",
             f"Fontes disponíveis, sem análise/decisão: {claims['factual_flow']['sources_only']}",
             f"Análise preliminar, sem decisão humana: {claims['factual_flow']['preliminary_pending_human']}", "",
             f"Primeira prévia desde o início da captura: {number(timing['first_partial'], ' s')}",
             f"Primeira entrega de segmento estabilizado: {number(timing['first_stabilized_delivery'], ' s')}",
             distribution("Atraso de entrega dos segmentos", timing["stabilized_delivery_lag"]),
             distribution("Processamento dos pacotes/trechos", timing["chunk_processing"]),
             distribution("Atraso de entrega dos pacotes/trechos", timing["chunk_delivery_lag"]),
             distribution("Duração das tentativas de triagem concluídas", timing["triage_processing"]),
             distribution("Do registro da afirmação à decisão humana atual", timing["claim_to_current_human_decision"]),
             f"Primeira decisão humana atual desde a captura: {number(timing['first_current_human_decision_since_capture'], ' s')}",
             "Origem do horário inicial: " + {"capture_started_at": "início efetivo da captura", "not_recorded": "Não registrado",
                                              "started_event_approximation": "evento inicial (aproximado)"}[report['capture']['time_anchor']['source']], "",
             f"Tentativas de triagem no histórico: {attempts(report['history']['attempts']['analyses'])}",
             f"Tentativas de pesquisa no histórico: {attempts(report['history']['attempts']['research_jobs'])}",
             f"Avisos de captura registrados: {json.dumps(report['history']['capture_warning_codes'])}",
             f"Intervalos preenchidos com silêncio: {report['history']['silence_padding_events']}",
             "Maior fila de ASR registrada: " + (str(report['history']['maximum_logged_asr_queue']) if
                                                 report['history']['maximum_logged_asr_queue'] is not None else "Não registrado"), "",
             "Precisão, cobertura das falas reais e erro de transcrição: NÃO AVALIADOS; referência humana pendente.", "",
             *report["notices"], "", *report["limitations"], "", f"SHA256 do relatório: {report['content_sha256']}",
             f"SHA256 dos registros da sessão: {report['session_snapshot_sha256']}"]
    return "\n".join(lines) + "\n"
