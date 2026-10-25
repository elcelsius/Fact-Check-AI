import json
import sqlite3
import threading
import unittest
from unittest.mock import patch

from factcheck.discovery import SearchConfig
from factcheck.priorities import PriorityStore
from factcheck.research_queue import BatchStore, QueueConfig, ResearchQueue
from factcheck.triage import validate_items
from tests import test_evidence as fixtures
from tests.test_planning import plan


class ResearchQueueTests(unittest.TestCase):
    setUp = fixtures.DossierTests.setUp
    tearDown = fixtures.DossierTests.tearDown

    def prepare(self, cid=None):
        cid = cid or self.cid
        data = self.store.snapshot(cid)
        self.store.save_plan(cid, data["revision"], plan(scope="pesquisavel", candidate_urls=["https://www.ibge.gov.br/"+cid]))

    def second_case(self):
        text = "A taxa foi de 4% no Brasil em 2025."
        self.review.ingest({"paragraph_id": 2, "version": 1, "text": text, "source_text": text, "start": 7, "end": 10, "closed": True, "parts": []})
        jid, _ = self.review.begin_analysis(2)
        self.review.finish_analysis(jid, validate_items([{"quote": text, "summary": text, "category": "fato", "reason": "Fictício.",
            "topic": None, "location": "Brasil", "period": "2025", "indicator": "4%", "comparison": None}], text), {})
        return next(claim["id"] for claim in self.review.claims() if claim["paragraph_id"] == 2)

    def factory(self, calls, hook=None):
        class FakeTask:
            def __init__(self, store, cid, kind, argument, config, emit, expected_revision=None):
                self.store, self.cid, self.kind, self.argument, self.emit = store, cid, kind, argument, emit
                self.job_id = store.begin(cid, kind, query=argument if kind == "discover" else None, expected_revision=expected_revision)
                self.pending = 1
            def start(self):
                calls.append((self.cid, self.kind))
                if hook: hook(self)
                if self.kind == "discover":
                    result = {"query": self.argument, "searched_at": "2026-10-24", "candidates": [], "discarded_count": 0}
                else:
                    result = fixtures.document(did=self.job_id, url=self.argument)
                self.store.finish(self.job_id, result, {})
                self.pending = 0
                self.emit("research_done", {"token": self.job_id})
            def cancel(self):
                self.store.fail(self.job_id, "Cancelada", True)
                self.pending = 0
        return FakeTask

    def test_approved_plan_collects_sources_without_search_analysis_or_factual_decision(self):
        self.prepare()
        calls = []
        batch = ResearchQueue(self.store, [self.cid], QueueConfig(), lambda *_: None, task_factory=self.factory(calls))
        batch._run()
        self.assertEqual(calls, [(self.cid, "collect")])
        self.assertEqual(batch.audit.rows()[0]["status"], "completed")
        self.assertEqual(len(self.store.snapshot(self.cid)["documents"]), 1)
        self.assertIsNone(self.store.snapshot(self.cid)["decision"])

    def test_pending_priority_is_applied_between_cases_without_reordering_running_task(self):
        second = self.second_case()
        self.prepare()
        self.prepare(second)
        PriorityStore(self.review).save(second, 0, 1, 1, "high", "Prioridade fictícia.")
        calls = []
        batch = ResearchQueue(self.store, [self.cid, second], QueueConfig(), lambda *_: None, task_factory=self.factory(calls))
        batch._run()
        self.assertEqual([cid for cid, _ in calls], [second, self.cid])

    def test_task_limit_prevents_next_request_and_preserves_completed_source(self):
        second = self.second_case()
        self.prepare()
        self.prepare(second)
        calls = []
        batch = ResearchQueue(self.store, [self.cid, second], QueueConfig(max_tasks=1), lambda *_: None, task_factory=self.factory(calls))
        batch._run()
        self.assertEqual(len(calls), 1)
        self.assertEqual(batch.audit.rows()[0]["status"], "limited")
        self.assertEqual(len(self.store.snapshot(self.cid)["documents"]), 1)

    def test_cancellation_before_start_and_changed_origin_do_not_start_network_tasks(self):
        self.prepare()
        calls = []
        batch = ResearchQueue(self.store, [self.cid], QueueConfig(), lambda *_: None, task_factory=self.factory(calls))
        batch.cancel()
        batch._run()
        self.assertFalse(calls)
        self.assertEqual(batch.audit.rows()[0]["status"], "cancelled")
        other = ResearchQueue(self.store, [self.cid], QueueConfig(), lambda *_: None, task_factory=self.factory(calls))
        self.review.revise(1, 1, "Correção posterior.", None)
        other._run()
        self.assertFalse(calls)
        self.assertEqual(other.audit.rows()[0]["cases"][0]["status"], "skipped")

    def test_search_key_is_never_stored_and_old_case_revision_blocks_job_creation(self):
        self.prepare()
        calls = []
        secret = "CHAVE-FICTICIA-NAO-PERSISTIR"
        batch = ResearchQueue(self.store, [self.cid], QueueConfig(search=True), lambda *_: None, SearchConfig(secret), task_factory=self.factory(calls))
        batch._run()
        self.assertNotIn(secret, json.dumps(batch.audit.rows()))
        self.assertEqual([kind for _, kind in calls], ["discover", "collect"])
        with self.assertRaises(ValueError): self.store.begin(self.cid, "collect", expected_revision=0)

    def test_missing_human_plan_or_existing_human_decision_is_not_automatically_queued(self):
        with self.assertRaises(ValueError): ResearchQueue(self.store, [self.cid], QueueConfig(), lambda *_: None)
        self.prepare()
        data = self.store.snapshot(self.cid)
        self.store.decide(self.cid, data["revision"], "inconclusiva", "Revisor fictício", "Sem fontes.")
        with self.assertRaises(ValueError): ResearchQueue(self.store, [self.cid], QueueConfig(), lambda *_: None)

    def test_real_worker_extracts_one_mocked_http_document_in_native_process(self):
        self.prepare()
        done = threading.Event()
        batch = ResearchQueue(self.store, [self.cid], QueueConfig(max_tasks=1),
            lambda _, data: done.set() if not data["pending"] else None)
        with patch("factcheck.research.download", return_value=(fixtures.HTML, "text/html", "https://www.ibge.gov.br/fonte")):
            batch.start()
            self.assertTrue(done.wait(20))
        self.assertEqual(batch.audit.rows()[0]["status"], "completed")
        self.assertEqual(len(self.store.snapshot(self.cid)["documents"]), 1)
        self.assertIsNone(self.store.snapshot(self.cid)["preliminary"])
        self.assertIsNone(self.store.snapshot(self.cid)["decision"])

    def test_failed_collections_count_toward_attempt_limit_and_leave_sources_pending(self):
        self.prepare()
        data = self.store.snapshot(self.cid)
        self.store.save_plan(self.cid, data["revision"], plan(scope="pesquisavel", candidate_urls=["https://www.ibge.gov.br/one", "https://www.ibge.gov.br/two"]))
        calls = []
        base = self.factory(calls)
        class FailedTask(base):
            def start(task):
                calls.append((task.cid, task.kind))
                task.store.fail(task.job_id, "Falha simulada.")
                task.pending = 0; task.emit("research_done", {})
        batch = ResearchQueue(self.store, [self.cid], QueueConfig(documents_per_case=1), lambda *_: None, task_factory=FailedTask)
        batch._run()
        self.assertEqual(len(calls), 1)
        result = batch.audit.rows()[0]["cases"][0]
        self.assertEqual(result["collection_attempts"], 1)
        self.assertEqual(result["status"], "needs_sources")

    def test_api_failure_halts_batch_without_next_collection_or_request(self):
        self.prepare()
        calls = []
        base = self.factory(calls)
        class FailedTask(base):
            def start(task):
                calls.append((task.cid, task.kind))
                task.store.fail(task.job_id, "Cota simulada.")
                task.pending = 0; task.emit("research_done", {})
        batch = ResearchQueue(self.store, [self.cid], QueueConfig(search=True), lambda *_: None, SearchConfig("FICTITIOUS-KEY"), task_factory=FailedTask)
        batch._run()
        self.assertEqual(calls, [(self.cid, "discover")])
        self.assertEqual(batch.audit.rows()[0]["status"], "failed")
        self.assertEqual(batch.audit.rows()[0]["cases"][0]["status"], "interrupted")

    def test_worker_start_failure_marks_created_job_failed_and_releases_queue(self):
        self.prepare()
        base = self.factory([])
        class BrokenTask(base):
            def start(task): raise RuntimeError("Falha simulada ao iniciar thread.")
        batch = ResearchQueue(self.store, [self.cid], QueueConfig(), lambda *_: None, task_factory=BrokenTask)
        batch._run()
        self.assertEqual(batch.pending, 0)
        self.assertEqual(batch.audit.rows()[0]["status"], "failed")
        self.assertNotIn("running", [job["status"] for job in self.store.snapshot(self.cid)["jobs"]])

    def test_cancel_during_child_waits_for_acknowledgment_and_starts_no_other_job(self):
        self.prepare()
        started = threading.Event(); calls = []
        base = self.factory(calls)
        class WaitingTask(base):
            def start(task): calls.append((task.cid, task.kind)); started.set()
        done = threading.Event()
        batch = ResearchQueue(self.store, [self.cid], QueueConfig(), lambda _, data: done.set() if not data["pending"] else None, task_factory=WaitingTask)
        batch.start()
        self.assertTrue(started.wait(3))
        batch.cancel()
        self.assertTrue(done.wait(3))
        self.assertEqual(batch.audit.rows()[0]["status"], "cancelled")
        self.assertEqual(len(calls), 1)

    def test_history_write_failure_releases_close_guard_and_does_not_start_prepared_child(self):
        self.prepare()
        calls = []; events = []
        batch = ResearchQueue(self.store, [self.cid], QueueConfig(), lambda _, data: events.append(data), task_factory=self.factory(calls))
        with patch.object(batch.audit, "save", side_effect=sqlite3.OperationalError("Falha de disco simulada.")):
            batch._run()
        self.assertEqual(batch.pending, 0)
        self.assertFalse(calls)
        self.assertEqual(events[-1]["pending"], 0)
        self.assertEqual(events[-1]["status"], "failed")
        self.assertNotIn("running", [job["status"] for job in self.store.snapshot(self.cid)["jobs"]])


if __name__ == "__main__":
    unittest.main()
