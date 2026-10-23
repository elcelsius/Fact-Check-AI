"""Coleta limitada de fontes institucionais públicas, com localizadores e versão."""

from hashlib import sha256
from http.client import HTTPSConnection
from io import BytesIO
from importlib.metadata import version
import ipaddress
import re
import socket
import ssl
from urllib.parse import quote, urljoin, urlsplit, urlunsplit
import uuid

from .review import now


ALLOWED_DOMAINS = ("gov.br", "jus.br", "leg.br", "who.int", "worldbank.org", "imf.org", "oecd.org", "un.org")
MAX_BYTES = 8_000_000
MAX_TEXT = 120_000
CATALOG = (
    ("IBGE", "ibge.gov.br", "População, emprego, inflação e indicadores sociais"),
    ("Banco Central", "bcb.gov.br", "Juros, crédito, câmbio e séries econômicas"),
    ("Tesouro Nacional", "tesourotransparente.gov.br", "Contas públicas e dívida"),
    ("Ipea", "ipea.gov.br", "Estudos e políticas públicas"),
    ("TSE", "tse.jus.br", "Eleições e estatísticas eleitorais"),
    ("Governo federal", "gov.br", "Saúde, educação, trabalho e políticas públicas"),
)


def source_url(value: str) -> str:
    try:
        parsed = urlsplit(value.strip())
        host = (parsed.hostname or "").encode("idna").decode().lower().rstrip(".")
        if (parsed.scheme != "https" or parsed.username or parsed.password or parsed.port not in (None, 443)
                or not any(host == domain or host.endswith("." + domain) for domain in ALLOWED_DOMAINS)
                or any(ord(c) < 33 for c in value)):
            raise ValueError()
        return urlunsplit(("https", host, quote(parsed.path or "/", safe="/%:@!$&'()*+,;=-._~"),
                           quote(parsed.query, safe="%=&/:?@!$'()*+,;=-._~"), ""))
    except (ValueError, UnicodeError):
        raise ValueError("Use uma URL HTTPS pública de gov.br, jus.br, leg.br, who.int, worldbank.org, imf.org, oecd.org ou un.org.") from None


def public_address(host):
    addresses = list(dict.fromkeys(info[4][0] for info in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)))
    if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
        raise ValueError("A fonte não pode apontar para uma rede local ou endereço reservado.")
    # IPv6 pode estar indisponível em redes Windows; manter todas as alternativas
    # públicas para o mesmo hostname, sem fazer uma segunda resolução DNS.
    return sorted(addresses, key=lambda address: ":" in address)


class PinnedHTTPS(HTTPSConnection):
    def __init__(self, host, address):
        super().__init__(host, timeout=15, context=ssl.create_default_context())
        self.address = address

    def connect(self):
        # Conectar ao IP validado, mantendo hostname para certificado e SNI.
        addresses = [self.address] if isinstance(self.address, str) else self.address
        error = None
        for address in addresses:
            sock = None
            try:
                sock = socket.create_connection((address, 443), min(5, self.timeout))
                sock.settimeout(self.timeout)
                self.sock = self._context.wrap_socket(sock, server_hostname=self.host)
                return
            except OSError as exc:
                if sock:
                    sock.close()
                error = exc
        raise error or OSError("Nenhum endereço público disponível.")


def download(url, cancelled):
    current = source_url(url)
    for _ in range(5):
        if cancelled.is_set():
            raise InterruptedError("Coleta cancelada.")
        parsed = urlsplit(current)
        address = public_address(parsed.hostname)
        if cancelled.is_set():
            raise InterruptedError("Coleta cancelada.")
        conn = PinnedHTTPS(parsed.hostname, address)
        try:
            target = parsed.path + ("?" + parsed.query if parsed.query else "")
            conn.request("GET", target, headers={"User-Agent": "FactCheckAI/0.7 (pesquisa editorial)", "Accept-Encoding": "identity"})
            response = conn.getresponse()
            if response.status in (301, 302, 303, 307, 308):
                current = source_url(urljoin(current, response.getheader("Location", "")))
                continue
            if response.status != 200:
                raise ValueError(f"Fonte indisponível ou bloqueada (HTTP {response.status}).")
            if response.getheader("Content-Encoding", "identity").lower() != "identity":
                raise ValueError("A fonte exige uma codificação de transporte não suportada.")
            length = response.getheader("Content-Length")
            if length and int(length) > MAX_BYTES:
                raise ValueError("Documento acima do limite de 8 MB.")
            chunks, total = [], 0
            while True:
                if cancelled.is_set():
                    raise InterruptedError("Coleta cancelada.")
                chunk = response.read(min(65536, MAX_BYTES + 1 - total))
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
                if total > MAX_BYTES:
                    raise ValueError("Documento acima do limite de 8 MB.")
            return b"".join(chunks), response.getheader("Content-Type", "").split(";")[0].lower(), current
        finally:
            conn.close()
    raise ValueError("A fonte excedeu o limite de redirecionamentos.")


def extract_document(raw, content_type, url, cancelled):
    blocks, warnings = [], ["A extração não substitui a conferência da fonte, das tabelas e da metodologia."]
    title, author, published = None, None, None
    truncated = False
    if raw.startswith(b"%PDF-"):
        from pypdf import PdfReader
        reader = PdfReader(BytesIO(raw), strict=False)
        if reader.is_encrypted:
            raise ValueError("PDF protegido; utilize uma versão pública acessível.")
        metadata = reader.metadata or {}
        title, author = metadata.get("/Title"), metadata.get("/Author")
        total = 0
        for number, page in enumerate(reader.pages):
            if cancelled.is_set():
                raise InterruptedError("Coleta cancelada.")
            if number >= 40 or total >= MAX_TEXT:
                truncated = True
                break
            text = (page.extract_text() or "").strip()
            if not text:
                warnings.append(f"Página {number + 1} sem texto extraível; pode precisar de OCR.")
                continue
            clipped = text[:MAX_TEXT - total]
            truncated |= len(clipped) < len(text)
            total += len(clipped)
            for offset in range(0, len(clipped), 2000):
                part = offset // 2000 + 1
                blocks.append({"id": f"p{number + 1}b{part}", "locator": f"página {number + 1}, trecho {part}", "text": clipped[offset:offset + 2000]})
        extractor = "pypdf"
    elif content_type in ("text/html", "application/xhtml+xml"):
        import trafilatura
        doc = trafilatura.bare_extraction(raw, url=url, with_metadata=True, include_comments=False,
                                         include_tables=True, favor_recall=True)
        if not doc or not doc.text:
            raise ValueError("Não foi possível extrair conteúdo: página vazia, dinâmica ou bloqueada.")
        title, author, published = doc.title, doc.author, doc.date
        text = doc.text[:MAX_TEXT]
        truncated = len(doc.text) > MAX_TEXT
        blocks = [{"id": f"b{i + 1}", "locator": f"parágrafo extraído {i + 1}", "text": line.strip()}
                  for i, line in enumerate(text.splitlines()) if line.strip()]
        extractor = "trafilatura"
        warnings.append("Os números dos parágrafos identificam a cópia extraída, não a numeração da página web.")
    else:
        raise ValueError("Formato não suportado. Use uma página HTML ou um PDF com texto.")
    if not blocks or sum(len(block["text"]) for block in blocks) < 40:
        raise ValueError("Conteúdo extraído insuficiente; use outra fonte ou versão acessível.")
    if truncated:
        warnings.append("Leitura limitada a 40 páginas ou 120.000 caracteres; documento incompleto.")
    if not published:
        warnings.append("Data de publicação não identificada; conferir anterioridade em relação ao debate.")
    else:
        warnings.append("Data de publicação extraída automaticamente; confirmar na fonte original.")
    text_hash = sha256("\n".join(block["text"] for block in blocks).encode()).hexdigest()
    host = urlsplit(url).hostname
    institution = next((name for name, domain, _ in CATALOG if host == domain or host.endswith("." + domain)), host)
    return {"id": uuid.uuid4().hex, "url": url, "title": str(title or url)[:500], "author": str(author or "")[:300],
            "published_at": str(published or "")[:30], "accessed_at": now(), "sha256": sha256(raw).hexdigest(),
            "text_sha256": text_hash, "content_type": content_type, "extractor": extractor, "extractor_version": version(extractor),
            "institution": institution, "blocks": blocks, "truncated": truncated, "warnings": warnings}


def collect(url, cancelled):
    requested = source_url(url)
    raw, content_type, final_url = download(requested, cancelled)
    document = extract_document(raw, content_type, final_url, cancelled)
    document["requested_url"] = requested
    return document


def search_plan(claim):
    # Termos são dados da fala. Nada aqui decide se a afirmação está correta.
    terms = str(claim.get("summary") or claim.get("quote") or "")
    for key in ("location", "period", "indicator"):
        value = str(claim.get(key) or "")
        if value and value.casefold() not in terms.casefold():
            terms += " " + value
    terms = re.sub(r"\s+", " ", terms)[:350]
    return [f"{terms} (site:ibge.gov.br OR site:bcb.gov.br OR site:gov.br)",
            f"{terms} série histórica metodologia revisão (site:gov.br OR site:ipea.gov.br)",
            f"{terms} comparação limitações divergência (site:gov.br OR site:jus.br OR site:leg.br)"]
