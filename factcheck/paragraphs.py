"""Organização incremental por pausas e regras linguísticas locais de português.

As regras sugerem limites e pontuação; não fazem análise factual ou compreensão
semântica geral. Os trechos de origem permanecem íntegros para conferência.
"""

from dataclasses import asdict, dataclass, field
import math
import re

from .transcription import TranscriptLine


_WORDS = re.compile(r"[\wÀ-ÿ]+(?:[-’'][\wÀ-ÿ]+)*", re.UNICODE)
_OPEN_ENDINGS = set("a o as os um uma uns umas de do da dos das em no na nos nas ao aos à às "
                    "para pra por pelo pela pelos pelas com sem entre desde até que porque "
                    "quando onde como se e ou mas nem não cujo cuja cujos cujas tanto".split())
_CONTINUATIONS = _OPEN_ENDINGS - {"o", "a", "os", "as", "um", "uma", "uns", "umas", "não"}
_VERBS = set("é são era eram foi foram será serão seria seriam está estão estava estavam "
             "estará estarão tem têm tinha tinham teve tiveram terá terão há havia houve "
             "vai vão vamos pode podem deve devem quero queremos fez fizemos faz fazem "
             "disse digo diz dizem sei sabe sabemos vê viu deu dá somos sou fui fomos "
             "cai caiu sobe subiu gera gerou cria criou cresce cresceu reduz reduziu ganha ganhou "
             "perde perdeu muda mudou paga pagou vale valeu custa custou atinge atingiu vota votou votem "
             "mantém mantêm manteve mantemos existe existem aparece aparecem inclui incluem "
             "garante garantem consegue conseguem afirma afirmam usa recebe mostra mostram".split())
_VERB_ENDINGS = ("amos", "emos", "imos", "aram", "eram", "iram", "avam", "ando", "endo", "indo", "ou", "eu", "iu")
_NEEDS_COMPLEMENT = set("é são era eram foi foram será serão seria seriam está estão estava estavam "
                        "tem têm tinha tinham teve tiveram terá terão há havia houve vai vão vamos "
                        "pode podem deve devem quero queremos disse diz dizem representa representam "
                        "significa significam depende dependem precisa precisam mantém mantêm manteve "
                        "mantemos inclui incluem garante garantem afirma afirmam usa recebe mostra mostram".split())
_TOPIC = re.compile(r"^(?:agora[, ]+)?(?:mudando de assunto\b|sobre outro assunto\b|"
                    r"quanto (?:a|ao|à|aos|às)\b|em relação (?:a|ao|à|aos|às)\b)", re.I)
_ABBREVIATIONS = {"sr", "sra", "dr", "dra", "prof", "profa", "art", "etc", "ex", "av", "nº"}


def words(text: str) -> list[str]:
    return [word.casefold() for word in _WORDS.findall(text)]


def complete_thought(text: str) -> bool:
    """Indício conservador de conclusão, com limites explícitos e auditáveis."""
    tokens = words(text)
    clean = text.rstrip().rstrip('"”’)]')
    if not tokens or clean.endswith(("...", "…", ",", ":", ";", "-", "—")):
        return False
    if (tokens[-1] in _OPEN_ENDINGS or tokens[-1] in _NEEDS_COMPLEMENT
            or (len(tokens[-1]) > 5 and tokens[-1].endswith(("ando", "endo", "indo")))):
        return False
    if clean.endswith(("?", "!")) or (clean.endswith(".") and tokens[-1] not in _ABBREVIATIONS):
        return True
    if (len(tokens) < 3 or (tokens[-1].isdigit() and not clean.endswith("%"))
            or tokens[-1] in {"mil", "milhão", "milhões", "bilhão", "bilhões"}):
        return False
    return any(token in _VERBS or (len(token) > 4 and token.endswith(_VERB_ENDINGS)) for token in tokens)


def continuation(text: str) -> bool:
    tokens = words(text)
    return bool(tokens and tokens[0] in _CONTINUATIONS)


def independent_start(text: str) -> bool:
    tokens = words(text)
    return bool(tokens and tokens[0] in {
        "eu", "nós", "ele", "ela", "eles", "elas", "o", "a", "os", "as", "isso", "essa", "esse",
        "este", "esta", "esses", "essas", "vocês", "você", "portanto", "também", "agora",
    })


@dataclass(frozen=True)
class ParagraphConfig:
    pause_seconds: float = 1.5
    soft_seconds: float = 30.0
    soft_words: int = 90

    def __post_init__(self):
        if (not math.isfinite(self.pause_seconds) or not 0.8 <= self.pause_seconds <= 5
                or self.soft_seconds <= 0 or self.soft_words < 1):
            raise ValueError("A pausa entre parágrafos deve ficar entre 0,8 e 5 segundos.")


@dataclass
class _Paragraph:
    paragraph_id: int
    start: float
    end: float
    speaker: str | None
    start_reason: str
    parts: list[dict] = field(default_factory=list)
    version: int = 0
    closed: bool = False
    end_reason: str | None = None

    def snapshot(self) -> dict:
        self.version += 1
        result = asdict(self)
        source = " ".join(part["text"].strip() for part in self.parts)
        text = ""
        for part in self.parts:
            incoming = part["text"].strip()
            if text:
                if complete_thought(text) and not continuation(incoming):
                    text = _full_stop(text)
                    incoming = _capitalize(incoming)
                text += " "
            else:
                incoming = _capitalize(incoming)
            text += incoming
        complete = complete_thought(source)
        result.update({
            "source_text": source, "text": _full_stop(text) if complete else text,
            "source_sequences": list(dict.fromkeys(part["sequence"] for part in self.parts)),
            "thought_complete_hint": complete, "formatting": "pontuacao_sugerida_regras_pt_v1",
            "recognition_status": "estabilizado", "review_status": "automatico_nao_revisado",
        })
        return result


def _capitalize(text: str) -> str:
    # Preservar nomes, siglas e todas as demais letras.
    return re.sub(r"[^\W\d_]", lambda match: match.group().upper(), text, count=1)


def _full_stop(text: str) -> str:
    return text if text.rstrip().endswith((".", "?", "!", "…")) else text + "."


class ParagraphAssembler:
    def __init__(self, config: ParagraphConfig | None = None):
        self.config = config or ParagraphConfig()
        self.current: _Paragraph | None = None
        self.count = 0

    def _boundary(self, line: TranscriptLine) -> str | None:
        current = self.current
        if current.speaker != line.speaker:
            return "troca_de_falante"
        previous = " ".join(part["text"] for part in current.parts)
        if not complete_thought(previous):
            return None
        if _TOPIC.match(line.text.strip()):
            return "transicao_explicita_de_assunto"
        # Complementos de lugar, período, comparação e negação ficam com a fala.
        if continuation(line.text):
            return None
        if line.start - current.end >= self.config.pause_seconds:
            return "pausa_e_conclusao"
        long = (current.end - current.start >= self.config.soft_seconds
                or len(words(previous)) >= self.config.soft_words)
        if long and independent_start(line.text):
            return "limite_suave_apos_ideia"
        return None

    def add(self, line: TranscriptLine, sequence: int) -> list[dict]:
        if not line.text.strip():
            return []
        updates = []
        reason = self._boundary(line) if self.current else None
        if reason:
            updates.extend(self.finish(reason))
        if self.current is None:
            self.count += 1
            self.current = _Paragraph(self.count, line.start, line.end, line.speaker, reason or "inicio")
        self.current.parts.append({"sequence": sequence, **line.to_dict()})
        self.current.end = max(self.current.end, line.end)
        updates.append(self.current.snapshot())
        return updates

    def finish(self, reason: str = "encerramento") -> list[dict]:
        if self.current is None:
            return []
        self.current.closed = True
        self.current.end_reason = reason
        result = self.current.snapshot()
        self.current = None
        return [result]
