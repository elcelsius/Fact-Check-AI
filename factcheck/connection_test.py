"""Teste explícito da chave, cancelável, sem falas nem persistência."""

import queue
import threading
import time
import uuid

from .gemini import GeminiError, GeminiModel


class ConnectionTest:
    def __init__(self, config, emit):
        if config.provider != "gemini":
            raise ValueError("O teste de conexão é específico para Gemini.")
        self.config = config.validate()
        self.emit = emit
        self.token = "connection-test-" + uuid.uuid4().hex
        self.cancelled = threading.Event()
        self.pending = 1

    def start(self):
        threading.Thread(target=self._run, daemon=True, name="gemini-connection-test").start()

    def cancel(self):
        self.cancelled.set()

    def _request(self, outputs):
        try:
            engine = GeminiModel(self.config).test_connection(self.cancelled)
            outputs.put((engine, None))
        except InterruptedError:
            outputs.put((None, "Teste cancelado."))
        except GeminiError as exc:
            outputs.put((None, str(exc)))
        except Exception:
            outputs.put((None, "Não foi possível concluir o teste de conexão. Confira a chave, a rede e o modelo."))

    def _run(self):
        outputs = queue.Queue()
        began = time.monotonic()
        success, engine, message = False, {}, "Teste cancelado."
        try:
            if self.cancelled.is_set():
                raise InterruptedError(message)
            request = threading.Thread(target=self._request, args=(outputs,), daemon=True)
            request.start()
            while True:
                if self.cancelled.is_set():
                    raise InterruptedError("Teste cancelado. Uma chamada já transmitida pode consumir cota.")
                if time.monotonic() - began > 70:
                    raise TimeoutError("O teste excedeu o tempo limite. Confira a conexão e tente novamente.")
                try:
                    engine, error = outputs.get(timeout=0.1)
                except queue.Empty:
                    if not request.is_alive():
                        raise RuntimeError("O teste foi interrompido antes de receber uma resposta.")
                    continue
                if self.cancelled.is_set():
                    raise InterruptedError("Teste cancelado.")
                if error:
                    raise ValueError(error)
                success = True
                message = "Conexão validada com " + engine["model"] + ". A configuração ainda precisa ser aplicada."
                break
        except Exception as exc:
            message = str(exc)
            self.cancelled.set()
        finally:
            self.pending = 0
            self.emit("connection_test_done", {"token": self.token, "success": success, "message": message,
                                               "seconds": round(time.monotonic() - began, 3)})
