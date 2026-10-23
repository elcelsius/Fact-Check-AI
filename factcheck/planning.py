"""Perguntas e recortes de pesquisa, separados da citação e do veredito."""

from .sources import source_url


SCOPES = {"pesquisavel": "Pergunta definida para pesquisar", "falta_contexto": "Falta contexto ou recorte",
          "nao_verificavel": "Possível extração sem alegação verificável"}
ORIGINS = {"operator_input": "Plano salvo pelo operador; não é decisão factual",
           "ai_draft": "Rascunho de IA; conferência humana pendente"}
TEXT_FIELDS = {"question": 2000, "period": 500, "territory": 500, "indicator": 500, "comparison": 500, "notes": 6000}
PLAN_FIELDS = ("scope", *TEXT_FIELDS, "candidate_urls")


def validate_plan(plan):
    if (not isinstance(plan, dict) or set(plan) != set(PLAN_FIELDS) or not isinstance(plan.get("scope"), str)
            or plan["scope"] not in SCOPES):
        raise ValueError("Informe os campos do plano e uma situação de pesquisa válida.")
    result = {"scope": plan["scope"]}
    for key, limit in TEXT_FIELDS.items():
        value = plan[key]
        if not isinstance(value, str) or len(value) > limit:
            raise ValueError(f"Campo {key} inválido; use até {limit} caracteres.")
        result[key] = value.strip()
    if result["scope"] != "nao_verificavel" and not result["question"]:
        raise ValueError("Defina a pergunta de checagem.")
    if result["scope"] != "pesquisavel" and not result["notes"]:
        raise ValueError("Explique a falta de contexto ou a possível ausência de alegação verificável.")
    urls = plan["candidate_urls"]
    if not isinstance(urls, list) or len(urls) > 8 or any(not isinstance(url, str) or len(url) > 2000 for url in urls):
        raise ValueError("Informe até oito URLs institucionais candidatas, com até 2.000 caracteres cada.")
    result["candidate_urls"] = list(dict.fromkeys(source_url(url) for url in urls if url.strip()))
    return result
