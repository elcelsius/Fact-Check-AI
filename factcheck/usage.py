"""Limite local de tentativas de API e estimativas com preços informados pelo operador."""

from decimal import Decimal
import json
import math
import os

from .evidence_notes import decimal_value
from .review import now

DEFAULTS = {"max_api_calls": 100, "currency": "USD", "budget": None, "gemini_per_million_tokens": None, "tavily_per_credit": None}


class ApiLimit(ValueError):
    pass


class UsageStore:
    def __init__(self, review):
        self.review = review
        with review.connection() as db:
            db.execute("CREATE TABLE IF NOT EXISTS operation_settings (id INTEGER PRIMARY KEY, revision INTEGER, payload TEXT)")
            db.execute("CREATE TABLE IF NOT EXISTS api_requests (id TEXT PRIMARY KEY, provider TEXT, status TEXT, payload TEXT)")
            db.execute("INSERT OR IGNORE INTO operation_settings VALUES (1,0,?)", (json.dumps({**DEFAULTS, "tracking_started_at": now()}),))

    def settings(self):
        with self.review.connection() as db:
            revision, raw = db.execute("SELECT revision,payload FROM operation_settings WHERE id=1").fetchone()
            return {"revision": revision, **json.loads(raw)}

    def configure(self, expected_revision, fields):
        if not isinstance(fields, dict) or set(fields) != set(DEFAULTS) or type(fields["max_api_calls"]) is not int or not 0 <= fields["max_api_calls"] <= 10000:
            raise ValueError("Informe limite de zero a dez mil tentativas de API por sessão.")
        if not isinstance(fields["currency"], str) or fields["currency"] not in {"USD", "BRL", "EUR"}:
            raise ValueError("Escolha a moeda de referência da estimativa.")
        for key in ("budget", "gemini_per_million_tokens", "tavily_per_credit"):
            if fields[key] is not None and decimal_value(fields[key]) < 0:
                raise ValueError("Use valores de referência não negativos ou deixe-os vazios.")
        with self.review.connection() as db:
            revision, previous = db.execute("SELECT revision,payload FROM operation_settings WHERE id=1").fetchone()
            if revision != expected_revision:
                raise ValueError("Os limites mudaram. Reabra a configuração.")
            saved = {**fields, "tracking_started_at": json.loads(previous).get("tracking_started_at")}
            db.execute("UPDATE operation_settings SET revision=?,payload=? WHERE id=1", (revision+1, json.dumps(saved)))
            self.review._audit(db, "operation_settings_changed", fields)

    def reserve(self, rid, provider, purpose):
        if provider not in {"gemini", "tavily"} or purpose not in {"triage", "discover", "analyze"}:
            raise ValueError("Provedor de API inválido.")
        with self.review.connection() as db:
            config = json.loads(db.execute("SELECT payload FROM operation_settings WHERE id=1").fetchone()[0])
            count = db.execute("SELECT count(*) FROM api_requests").fetchone()[0]
            if count >= config["max_api_calls"]:
                raise ApiLimit("Limite de tentativas de API da sessão atingido. Confira Limites e uso antes de autorizar novos envios.")
            if db.execute("SELECT 1 FROM api_requests WHERE id=?", (rid,)).fetchone():
                raise ApiLimit("Esta tentativa já foi reservada; uma repetição exige nova tarefa.")
            db.execute("INSERT INTO api_requests VALUES (?,?,'reserved',?)", (rid, provider, json.dumps({"reserved_at": now(), "purpose": purpose, "owner_pid": os.getpid()})))

    def complete(self, rid, status, engine=None):
        if status not in {"completed", "failed", "cancelled", "stale"}:
            raise ValueError("Estado de uso inválido.")
        engine = engine or {}
        usage = {key: value for key, value in engine.get("usage", {}).items()
                 if key in {"promptTokenCount", "candidatesTokenCount", "totalTokenCount", "thoughtsTokenCount", "cachedContentTokenCount"}
                 and type(value) is int and 0 <= value <= 10**10}
        credits = engine.get("credits")
        if type(credits) not in (int, float) or not math.isfinite(credits) or credits < 0:
            credits = None
        with self.review.connection() as db:
            row = db.execute("SELECT payload FROM api_requests WHERE id=? AND status='reserved'", (rid,)).fetchone()
            if row:
                data = {**json.loads(row[0]), "ended_at": now(), "usage": usage, "credits": credits}
                db.execute("UPDATE api_requests SET status=?,payload=? WHERE id=?", (status, json.dumps(data), rid))

    def summary(self):
        config = self.settings()
        with self.review.connection() as db:
            rows = [(provider, status, json.loads(raw)) for provider, status, raw in db.execute("SELECT provider,status,payload FROM api_requests")]
        return self.summarize(config, rows)

    @staticmethod
    def summarize(config, rows):
        known, unknown, tokens, credits = Decimal(0), 0, 0, Decimal(0)
        for provider, state, data in rows:
            total = data.get("usage", {}).get("totalTokenCount") if provider == "gemini" else data.get("credits")
            price = config["gemini_per_million_tokens" if provider == "gemini" else "tavily_per_credit"]
            if provider == "gemini" and total is not None: tokens += total
            if provider == "tavily" and total is not None: credits += Decimal(str(total))
            if total is None or price is None:
                unknown += 1
            else:
                known += Decimal(str(total)) * decimal_value(price) / (1000000 if provider == "gemini" else 1)
        estimated = format(known, "f") if unknown == 0 else None
        remaining = max(Decimal(0), decimal_value(config["budget"])-known) if config["budget"] is not None and not unknown else None
        return {"attempts": len(rows), "max_api_calls": config["max_api_calls"], "remaining_calls": max(0, config["max_api_calls"]-len(rows)),
                "tracking_started_at": config.get("tracking_started_at"),
                "reported_tokens": tokens, "reported_credits": format(credits, "f"), "unpriced_or_unreported_attempts": unknown,
                "currency": config["currency"], "estimated_cost": estimated, "known_cost_subtotal": format(known, "f"),
                "estimated_remaining_budget": format(remaining, "f") if remaining is not None else None,
                "budget_warning": config["budget"] is not None and known >= decimal_value(config["budget"]) and bool(rows),
                "limitations": "Preços de referência informados pelo operador; total de tokens usa taxa média configurada. Não é fatura. Tentativas canceladas ou sem uso informado continuam no limite de envios."}


def usage_from_records(records):
    settings = records["rows"].get("operation_settings", [])
    if not settings:
        return {"tracking_started_at": None, "attempts": None, "estimated_cost": None, "limitations": "Uso anterior à instrumentação não foi reconstruído por suposição."}
    config = {"revision": settings[0][0], **json.loads(settings[0][1])}
    rows = [(provider, state, json.loads(raw)) for _, provider, state, raw in records["rows"].get("api_requests", [])]
    return UsageStore.summarize(config, rows)
