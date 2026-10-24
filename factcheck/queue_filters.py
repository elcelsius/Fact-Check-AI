"""Filtros locais da fila: visualização sem modificar os registros da sessão."""

from dataclasses import dataclass
import unicodedata

from .grouping import active
from .priorities import FILTERS, ORDERINGS, filter_key


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
    priority: str | None = None
    assignee: str | None = None


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
    if filters.priority is not None and filters.priority not in FILTERS:
        raise ValueError("Prioridade da fila inválida.")
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
        if filters.priority is not None and filter_key(claim.get("priority")) != filters.priority:
            continue
        if filters.assignee is not None and (claim.get("assignment") or {}).get("name", "") != filters.assignee:
            continue
        text = normalize(" ".join(str(claim.get(key) or "") for key in
                                  ("quote", "summary", "context", "reason", "topic", "speaker", "location", "period", "indicator", "comparison")))
        if all(word in text for word in words):
            result.append(claim)
    return result


def sort_claims(claims, sources, order="recent"):
    if order not in ORDERINGS:
        raise ValueError("Ordenação da fila inválida.")
    if order == "recent":
        return list(claims)
    def key(claim):
        chronological = (claim["start"], claim["end"], claim["id"])
        if order == "chronological":
            return chronological
        current = is_current(claim, sources)
        metadata = claim.get("priority") or {}
        rank = {"high": 0, "normal": 1, "low": 2}.get(metadata.get("level"), 3) if current and metadata.get("current") else 3
        return (not current, rank, *chronological)
    return sorted(claims, key=key)


def field_choices(values, empty_label):
    """Os marcadores Todos/Sem valor não escondem nomes iguais cadastrados."""
    options = {"Todos": None, empty_label: ""}
    for value in sorted({value for value in values if value}, key=lambda item: (normalize(item), item)):
        label = value
        while label in options:
            label += " (cadastrado)"
        options[label] = value
    return options
