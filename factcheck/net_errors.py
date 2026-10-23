"""Mensagens de rede sem incluir URLs, cabeçalhos ou credenciais brutas."""

import socket
import ssl
from urllib.error import URLError


def network_message(exc, service):
    cause = exc.reason if isinstance(exc, URLError) else exc
    prefix = f"Não foi possível concluir a conexão com {service}. "
    if isinstance(cause, PermissionError):
        return prefix + "O Windows ou o ambiente de execução bloqueou o acesso à rede. Confira as permissões e tente abrir o aplicativo pelo iniciar.cmd."
    if isinstance(cause, ssl.SSLCertVerificationError):
        return prefix + "O certificado TLS não pôde ser validado. Confira data, hora e certificados da sua rede."
    if isinstance(cause, socket.gaierror):
        return prefix + "Falha na resolução de DNS. Confira a internet e o endereço do serviço."
    if isinstance(cause, TimeoutError):
        return prefix + "O tempo de conexão ou resposta foi excedido. Tente novamente mais tarde."
    return prefix + "Confira a internet e tente novamente."
