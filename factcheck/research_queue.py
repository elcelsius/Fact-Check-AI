"""Pesquisa sequencial sob comando do operador, com prioridade, limites e auditoria."""

from dataclasses import asdict, dataclass
import json
import os
import sqlite3
import threading
import time
import uuid

from .discovery import SearchConfig, search_basis
from .research import ResearchTask
from .review import now, process_alive
from .sources import search_plan, source_url
from .triage import TriageConfig


@dataclass(frozen=True)
class QueueConfig:
    max_cases: int = 10
    documents_per_case: int = 2
    max_tasks: int = 30
    timeout_seconds: int = 900
    search: bool = False
    analyze: bool = False

    def validate(self):
        for key, limit in (("max_cases", 20), ("documents_per_case", 6), ("max_tasks", 100), ("timeout_seconds", 3600)):
            value = getattr(self, key)
            if type(value) is not int or not 1 <= value <= limit:
                raise ValueError(f"Limite inválido para {key}: use de 1 a {limit}.")
        if type(self.search) is not bool or type(self.analyze) is not bool:
            raise ValueError("Escolha explicitamente busca e análise por API.")
        return self


class BatchStore:
    def __init__(self, review):
        self.review = review
        with review.connection() as db:
            db.execute("CREATE TABLE IF NOT EXISTS research_batches (id TEXT PRIMARY KEY, status TEXT, payload TEXT)")

    def recover(self):
        with self.review.connection() as db:
            for bid, payload in db.execute("SELECT id,payload FROM research_batches WHERE status='running'").fetchall():
                data = json.loads(payload)
                if not process_alive(data["owner_pid"]):
                    data.update(ended_at=now(), message="Fila interrompida; tarefas não serão retomadas automaticamente.")
                    db.execute("UPDATE research_batches SET status='interrupted',payload=? WHERE id=?", (json.dumps(data), bid))

    def save(self, bid, status, payload):
        with self.review.connection() as db:
            db.execute("INSERT OR REPLACE INTO research_batches VALUES (?,?,?)", (bid, status, json.dumps(payload, ensure_ascii=False)))

    def begin(self, bid, payload):
        with self.review.connection() as db:
            if db.execute("SELECT 1 FROM research_batches WHERE status='running'").fetchone():
                raise ValueError("Já existe uma fila de pesquisa ativa nesta sessão.")
            db.execute("INSERT INTO research_batches VALUES (?,'running',?)", (bid, json.dumps(payload, ensure_ascii=False)))

    def rows(self):
        with self.review.connection() as db:
            return [{"id": bid, "status": state, **json.loads(raw)} for bid, state, raw in db.execute("SELECT id,status,payload FROM research_batches ORDER BY rowid DESC")]


class ResearchQueue:
    def __init__(self, store, claim_ids, config, emit, search_config=None, ai_config=None, task_factory=ResearchTask):
        self.config = config.validate()
        if not isinstance(claim_ids, list) or not claim_ids or len(claim_ids) > 200 or len(set(claim_ids)) != len(claim_ids):
            raise ValueError("Selecione de uma a duzentas afirmações distintas; o limite de casos será aplicado.")
        self.store, self.emit, self.task_factory = store, emit, task_factory
        self.search_config = search_config or SearchConfig()
        self.ai_config = ai_config or TriageConfig()
        if config.search: self.search_config.validate()
        if config.analyze:
            self.ai_config.validate()
            if self.ai_config.provider != "gemini":
                raise ValueError("A análise automática da fila exige selecionar Gemini e informar sua chave explicitamente.")
        self.audit = BatchStore(store.review)
        self.audit.recover()
        if any(row["status"] == "running" for row in self.audit.rows()):
            raise ValueError("Já existe uma fila de pesquisa ativa nesta sessão.")
        self.bid = uuid.uuid4().hex
        self.token = "batch-" + self.bid
        self.cancelled = threading.Event()
        self.lock = threading.Lock()
        self.child = None
        self.pending = 1
        self.jobs_started = 0
        self.started = None
        self.claims = []
        self.data = {"owner_pid": os.getpid(), "started_at": now(), "config": asdict(config), "cases": [], "tasks": [], "message": "Fila preparada."}
        for cid in claim_ids:
            snapshot = store.snapshot(cid)
            plan = snapshot.get("plan") or {}
            if (snapshot["valid"] and snapshot["claim"]["category"] == "fato" and not snapshot["decision"] and plan.get("scope") == "pesquisavel"
                    and plan.get("origin") == "operator_input" and not plan.get("needs_review")):
                self.claims.append({"id": cid, "basis": search_basis(snapshot["claim"], plan)})
        if not self.claims:
            raise ValueError("A fila precisa de afirmações factuais atuais, sem decisão e com plano pesquisável conferido pelo operador.")
        self.audit.begin(self.bid, self.data)

    def start(self):
        threading.Thread(target=self._run, daemon=True, name="research-queue").start()

    def cancel(self):
        with self.lock:
            self.cancelled.set()
            if self.child: self.child.cancel()

    def check(self):
        if self.cancelled.is_set(): raise InterruptedError("Fila cancelada; fontes e resultados já salvos foram preservados.")
        if self.started is not None and time.monotonic()-self.started >= self.config.timeout_seconds:
            raise TimeoutError("Tempo máximo da fila atingido; fontes e pendências preservadas.")

    def current(self, entry):
        self.check()
        data = self.store.snapshot(entry["id"])
        if not data["valid"] or data["decision"] or search_basis(data["claim"], data.get("plan")) != entry["basis"]:
            raise ValueError("A afirmação ou o plano mudou, ou uma decisão humana foi registrada. Caso retirado da fila.")
        return data

    def priority(self, entry):
        data = self.store.snapshot(entry["id"])
        value = data["priority"]
        return {"high": 0, "normal": 1, "unset": 1, "low": 2}.get(value["level"], 1) if value["current"] else 1

    def update(self, message):
        self.data["message"] = message
        self.audit.save(self.bid, "running", self.data)
        self.emit("research_queue_update", {"token": self.token, "message": message, "pending": self.pending})

    def task(self, entry, kind, argument):
        self.check()
        if self.jobs_started >= self.config.max_tasks:
            raise TimeoutError("Limite de tarefas da fila atingido; nenhum envio adicional foi iniciado.")
        data = self.current(entry)
        self.jobs_started += 1
        done = threading.Event()
        with self.lock:
            self.check()
            task = self.task_factory(self.store, entry["id"], kind, argument,
                self.search_config if kind == "discover" else self.ai_config, lambda *_: done.set(), expected_revision=data["revision"])
            self.child = task
        self.data["tasks"].append({"id": task.job_id, "claim_id": entry["id"], "kind": kind})
        started = False
        try:
            self.update(f"Pesquisa em fila · tarefa {self.jobs_started}/{self.config.max_tasks} · {kind}")
            task.start()
            started = True
            while not done.wait(0.1): self.check()
        except BaseException:
            task.cancel()
            if not started:
                task.pending = 0
            if not task.pending:
                self.store.fail(task.job_id, "Tarefa da fila interrompida.", self.cancelled.is_set())
            raise
        finally:
            if self.cancelled.is_set() or self.started is not None and time.monotonic()-self.started >= self.config.timeout_seconds:
                task.cancel()
                while task.pending: time.sleep(0.05)
            with self.lock: self.child = None
        state = next(row["status"] for row in self.store.snapshot(entry["id"])["jobs"] if row["id"] == task.job_id)
        if state != "completed" and kind in {"discover", "analyze"}:
            raise RuntimeError("A busca ou análise por API não concluiu. A fila foi interrompida para evitar novos envios; confira o histórico.")
        return state == "completed"

    def _run(self):
        status = "completed"
        self.started = time.monotonic()
        try:
            remaining = list(self.claims)
            while remaining and len(self.data["cases"]) < self.config.max_cases:
                self.check()
                remaining.sort(key=self.priority)
                entry = remaining.pop(0)
                result = {"claim_id": entry["id"], "status": "completed", "documents_added": 0, "collection_attempts": 0}
                try:
                    snapshot = self.current(entry)
                    urls = list(snapshot["plan"]["candidate_urls"])
                    if self.config.search:
                        query = search_plan(snapshot["claim"], snapshot["plan"])[0]
                        self.task(entry, "discover", query)
                        snapshot = self.current(entry)
                        for batch in snapshot["discoveries"]:
                            if batch["current"]:
                                urls.extend(item["url"] for item in batch["candidates"] if item["disposition"] == "pending")
                    urls = list(dict.fromkeys(source_url(url) for url in urls))
                    existing = {doc["url"] for doc in snapshot["documents"]}
                    for url in urls:
                        if url in existing: continue
                        if result["collection_attempts"] >= self.config.documents_per_case or len(existing) >= 6: break
                        result["collection_attempts"] += 1
                        if self.task(entry, "collect", url):
                            result["documents_added"] += 1
                            existing = {doc["url"] for doc in self.current(entry)["documents"]}
                    if self.config.analyze and self.current(entry)["documents"]:
                        self.task(entry, "analyze", None)
                    if not existing:
                        result.update(status="needs_sources", message="Nenhuma fonte coletada; confira as tentativas, complete o plano ou habilite a busca.")
                except ValueError as exc:
                    result.update(status="skipped", message=str(exc))
                except Exception:
                    result.update(status="interrupted", message="Execução interrompida; confira o histórico das tarefas.")
                    self.data["cases"].append(result)
                    raise
                self.data["cases"].append(result)
                self.update(f"Pesquisa em fila · {len(self.data['cases'])} caso(s) percorrido(s); revisão humana pendente.")
            self.data["remaining_cases"] = len(remaining)
        except InterruptedError as exc:
            status = "cancelled"
            self.data["message"] = str(exc)
        except TimeoutError as exc:
            status = "limited"
            self.data["message"] = str(exc)
        except Exception:
            status = "failed"
            self.data["message"] = "A fila foi interrompida. Confira as tarefas e as pendências no dossiê; nada foi aprovado automaticamente."
        finally:
            self.data.update(ended_at=now(), jobs_started=self.jobs_started,
                             remaining_cases=max(0, len(self.claims)-len(self.data["cases"])))
            try:
                self.audit.save(self.bid, status, self.data)
            except (OSError, sqlite3.Error):
                status = "failed"
                self.data["message"] = "Falha ao gravar o histórico da fila. Confira o armazenamento e reabra o aplicativo antes de tentar outra pesquisa."
            finally:
                self.pending = 0
                self.emit("research_queue_update", {"token": self.token, "pending": 0, "message": self.data["message"], "status": status})
