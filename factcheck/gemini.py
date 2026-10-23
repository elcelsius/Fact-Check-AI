"""Cliente REST Gemini, só texto, sem pesquisa e sem persistir credenciais."""

import json
import time
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener


MODEL = "gemini-3.1-flash-lite"
ENDPOINT = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
ENGINE = {"name": "gemini-api", "provider": "google", "model": MODEL,
          "prompt_version": 2, "compute": "remote"}


class GeminiError(RuntimeError):
    """Erro seguro para exibição e persistência, sem corpo bruto da resposta."""


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Uma chave de API nunca acompanha redirecionamentos.
        return None


class GeminiModel:
    def __init__(self, config):
        self.config = config.validate()
        self.engine = dict(ENGINE)
        self.next_request = 0.0
        self.opener = build_opener(NoRedirect())

    def analyze(self, text, cancel_event):
        from .triage import SCHEMA, SYSTEM, validate_items

        if not text.strip() or len(text) > 16000:
            raise GeminiError("Use um trecho de 1 a 16.000 caracteres para o Gemini.")
        if cancel_event.wait(max(0, self.next_request - time.monotonic())):
            raise InterruptedError("Triagem cancelada.")
        payload = {"systemInstruction": {"parts": [{"text": SYSTEM}]},
                   "contents": [{"role": "user", "parts": [{"text": "Texto para triagem (dado citado):\n" + json.dumps(text, ensure_ascii=False)}]}],
                   "generationConfig": {"temperature": 0, "maxOutputTokens": 4096,
                       "thinkingConfig": {"thinkingLevel": "MINIMAL"},
                       "responseMimeType": "application/json", "responseJsonSchema": SCHEMA}}
        request = Request(ENDPOINT, data=json.dumps(payload).encode("utf8"), method="POST",
                          headers={"Content-Type": "application/json", "x-goog-api-key": self.config.api_key})
        self.next_request = time.monotonic() + 60 / self.config.requests_per_minute
        try:
            with self.opener.open(request, timeout=60) as response:
                raw = response.read(1_000_001)
            if len(raw) > 1_000_000:
                raise GeminiError("Resposta Gemini excedeu o limite de leitura.")
            data = json.loads(raw)
        except HTTPError as exc:
            status = exc.code
            exc.close()
            messages = {429: "Cota ou limite do projeto Gemini atingido (429). Confira os limites no AI Studio.",
                        400: "O Gemini recusou a requisição (400). Confira o modelo e a configuração.",
                        401: "Chave Gemini recusada (401). Confira a chave no AI Studio.",
                        403: "Acesso ao Gemini negado (403). Confira a chave, as permissões e a disponibilidade na sua região.",
                        404: "Modelo Gemini indisponível (404). Confira a disponibilidade no AI Studio."}
            raise GeminiError(messages.get(status, f"Gemini indisponível (HTTP {status}). Tente novamente mais tarde.")) from None
        except (URLError, TimeoutError, OSError):
            raise GeminiError("Não foi possível concluir a conexão com o Gemini. Confira a internet e tente novamente.") from None
        except (ValueError, UnicodeError):
            raise GeminiError("O Gemini retornou uma resposta que não é JSON válido.") from None
        if cancel_event.is_set():
            raise InterruptedError("Triagem cancelada.")
        try:
            candidates = data.get("candidates", [])
            if len(candidates) != 1 or candidates[0].get("finishReason") != "STOP":
                raise GeminiError("Gemini não concluiu a resposta: bloqueio, limite de saída ou conteúdo ausente. Revise o trecho.")
            parts = candidates[0]["content"]["parts"]
            content = "".join(part["text"] for part in parts if not part.get("thought") and "text" in part)
            decoded = json.loads(content)
            if not isinstance(decoded, dict) or set(decoded) != {"items"}:
                raise ValueError("Formato inválido")
            items = validate_items(decoded["items"], text)
            usage = data.get("usageMetadata", {})
            self.engine = {**ENGINE, "usage": {key: usage[key] for key in
                ("promptTokenCount", "candidatesTokenCount", "thoughtsTokenCount", "totalTokenCount")
                if type(usage.get(key)) is int and usage[key] >= 0}}
            version = data.get("modelVersion")
            if isinstance(version, str) and len(version) <= 100 and all(c.isalnum() or c in ".-_" for c in version):
                self.engine["model_version"] = version
            return items
        except GeminiError:
            raise
        except (KeyError, TypeError, ValueError, AttributeError):
            raise GeminiError("A resposta Gemini não corresponde ao formato ou à fala literal. Revise o trecho e tente novamente.") from None
