"""Filtros locais da fila: visualização sem modificar os registros da sessão."""

from dataclasses import dataclass
import unicodedata

from .grouping import active


LABELS = {"aguardando_pesquisa": "Aguardando pesquisa", "precisa_contexto": "Precisa de contexto",
          "fora_da_fila": "Opinião / promessa", "analise_desatualizada": "Análise desatualizada", "descartada": "Descartada"}
CATEGORIES = {"fato": "Factual", "opiniao": "Opinião", "promessa": "Promessa", "indefinida": "Indefinida"}
SCOPES = {"all": "Todas", "current": "Somente atuais", "historical": "Históricas / descartadas"}
STATES = (*LABELS.values(), "Planejamento salvo", "Planejamento a conferir", "Fontes coletadas",
          "Análise preliminar pronta", "Revisão humana registrada")


@dataclass(frozen=True)
class QueueFilters:
    query: str = ""
    scope: str = "all"
    category: str | None = None
    state: str | None = None
    speaker: str | None = None
    topic: str | None = None


def normalize(value):
    return "".join(char for char in unicodedata.normalize("NFD", value.casefold()) if not unicodedata.combining(char))


def is_current(claim, sources):
    source = sources.get(claim["paragraph_id"])
    return bool(source and active(source) and not source["needs_rebase"] and source["revision"] == claim["revision"]
                and not claim.get("source_outdated") and claim["status"] not in {"descartada", "analise_desatualizada"})


def display_state(claim, sources, case_states):
    if claim["status"] == "descartada":
        return LABELS["descartada"]
    if not is_current(claim, sources):
        return LABELS["analise_desatualizada"]
    return case_states.get(claim["id"], LABELS[claim["status"]])


def filter_claims(claims, sources, case_states, filters):
    if filters.scope not in SCOPES:
        raise ValueError("Escopo da fila inválido.")
    words = normalize(filters.query).split()
    result = []
    for claim in claims:
        current = is_current(claim, sources)
        if filters.scope == "current" and not current or filters.scope == "historical" and current:
            continue
        if filters.category is not None and claim["category"] != filters.category:
            continue
        if filters.state is not None and display_state(claim, sources, case_states) != filters.state:
            continue
        if filters.speaker is not None and (claim.get("speaker") or "") != filters.speaker:
            continue
        if filters.topic is not None and (claim.get("topic") or "") != filters.topic:
            continue
        text = normalize(" ".join(str(claim.get(key) or "") for key in
                                  ("quote", "summary", "context", "reason", "topic", "speaker", "location", "period", "indicator", "comparison")))
        if all(word in text for word in words):
            result.append(claim)
    return result


def field_choices(values, empty_label):
    """Os marcadores Todos/Sem valor não escondem nomes iguais cadastrados."""
    options = {"Todos": None, empty_label: ""}
    for value in sorted({value for value in values if value}, key=lambda item: (normalize(item), item)):
        label = value
        while label in options:
            label += " (cadastrado)"
        options[label] = value
    return options
