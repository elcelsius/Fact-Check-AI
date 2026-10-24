"""Descoberta de URLs candidatas; resultados de busca nunca são evidências."""

from dataclasses import dataclass, field
from hashlib import sha256
import json
import math
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener

from .gemini import NoRedirect
from .net_errors import network_message
from .review import now
from .sources import ALLOWED_DOMAINS, source_url


ENDPOINT = "https://api.tavily.com/search"
ENGINE = {"name": "tavily-search", "provider": "tavily", "search_depth": "basic"}
MAX_RESULTS = 5


class SearchError(RuntimeError):
    """Mensagem segura, sem credenciais nem resposta bruta do provedor."""


@dataclass(frozen=True)
class SearchConfig:
    api_key: str = field(default="", repr=False)

    def validate(self):
        if not isinstance(self.api_key, str) or not 1 <= len(self.api_key) <= 512 or any(not 33 <= ord(c) <= 126 for c in self.api_key):
            raise ValueError("Informe uma chave Tavily válida na janela Encontrar fontes.")
        return self


def validate_query(query):
    if not isinstance(query, str) or not query.strip() or len(query) > 1000 or any(ord(c) < 32 for c in query):
        raise ValueError("Use uma consulta de 1 a 1.000 caracteres, em uma linha.")
    return query.strip()


def search_basis(claim, plan):
    material = {"claim_revision": claim.get("claim_revision", 1), "revision": claim["revision"],
                "quote": claim["quote"], "summary": claim["summary"], "plan": plan}
    return sha256(json.dumps(material, ensure_ascii=False, sort_keys=True).encode("utf8")).hexdigest()


def parse_results(data, query):
    if not isinstance(data, dict) or not isinstance(data.get("results"), list) or len(data["results"]) > 100:
        raise SearchError("A busca retornou um formato inválido. Nenhum resultado foi aplicado.")
    candidates, seen, discarded = [], set(), 0
    for item in data["results"]:
        if not isinstance(item, dict) or not isinstance(item.get("url"), str) or len(item["url"]) > 2000:
            discarded += 1
            continue
        try:
            url = source_url(item["url"])
        except ValueError:
            discarded += 1
            continue
        if url in seen or len(candidates) >= MAX_RESULTS:
            discarded += 1
            continue
        title = item.get("title")
        if not isinstance(title, str) or not title.strip():
            title = url
        # Não persistir snippets, resposta gerada ou conteúdo bruto do provedor.
        candidates.append({"id": f"c{len(candidates) + 1}", "url": url, "title": title[:500], "disposition": "pending"})
        seen.add(url)
    usage = data.get("usage", {})
    credits = usage.get("credits") if isinstance(usage, dict) else None
    engine = dict(ENGINE)
    if type(credits) in (int, float) and math.isfinite(credits) and credits >= 0:
        engine["credits"] = credits
    return {"query": validate_query(query), "searched_at": now(), "candidates": candidates, "discarded_count": discarded}, engine


class TavilySearch:
    def __init__(self, config):
        self.config = config.validate()
        self.opener = build_opener(NoRedirect())

    def search(self, query, cancelled):
        query = validate_query(query)
        if cancelled.is_set():
            raise InterruptedError("Busca cancelada.")
        payload = {"query": query, "topic": "general", "search_depth": "basic", "max_results": MAX_RESULTS,
                   "include_domains": list(ALLOWED_DOMAINS), "include_domains_mode": "restrict",
                   "include_answer": False, "include_raw_content": False, "include_images": False,
                   "auto_parameters": False, "include_usage": True}
        request = Request(ENDPOINT, data=json.dumps(payload).encode("utf8"), method="POST",
                          headers={"Content-Type": "application/json", "Authorization": "Bearer " + self.config.api_key})
        try:
            with self.opener.open(request, timeout=30) as response:
                raw = response.read(1_000_001)
            if len(raw) > 1_000_000:
                raise SearchError("A resposta de busca excedeu o limite de leitura.")
            data = json.loads(raw)
        except HTTPError as exc:
            status = exc.code
            exc.close()
            messages = {401: "Chave Tavily recusada (401). Confira sua chave.",
                        403: "Acesso à busca Tavily negado (403). Confira as permissões do projeto.",
                        429: "Limite de chamadas Tavily atingido (429). Aguarde antes de tentar novamente.",
                        432: "Limite do plano Tavily atingido (432). Confira seu painel.",
                        433: "Limite de uso Tavily atingido (433). Confira seu painel.",
                        400: "A busca recusou a consulta (400). Revise os termos e o tamanho da consulta.",
                        422: "A busca recusou os parâmetros (422). Revise a consulta."}
            raise SearchError(messages.get(status, f"Busca indisponível (HTTP {status}). Tente mais tarde.")) from None
        except (URLError, TimeoutError, OSError) as exc:
            raise SearchError(network_message(exc, "a busca Tavily")) from None
        except (ValueError, UnicodeError):
            raise SearchError("A busca retornou uma resposta que não é JSON válido.") from None
        if cancelled.is_set():
            raise InterruptedError("Busca cancelada.")
        return parse_results(data, query)
