from dataclasses import asdict
from io import BytesIO
import json
from pathlib import Path
import queue
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

from factcheck.gemini import ENDPOINT, MODEL, GeminiError, GeminiModel, NoRedirect
from factcheck.review import Debate, ReviewStore
from factcheck.triage import TriageConfig, TriageRunner, _model_worker


TEXT = "A inflação não caiu para 3,5% em 2025."
KEY = "chave-ficticia-para-testes"


def response(items=None, **kwargs):
    item = {"quote": TEXT, "category": "fato", "summary": TEXT, "reason": "Declaração factual.",
            "topic": "Economia", "location": None, "period": "2025", "indicator": "3,5%", "comparison": None}
    return {"candidates": [{"finishReason": "STOP", "content": {"parts": [
        {"thought": True, "text": "Não persistir raciocínio."},
        {"text": json.dumps({"items": items if items is not None else [item]})}]}}],
        "usageMetadata": {"promptTokenCount": 300, "candidatesTokenCount": 100, "totalTokenCount": 400}, **kwargs}


class GeminiTests(unittest.TestCase):
    def setUp(self):
        self.config = TriageConfig("gemini", KEY, 5)
        self.model = GeminiModel(self.config)
        self.cancelled = threading.Event()
        self.transport = Mock()
        self.model.opener = self.transport

    def reply(self, data):
        self.transport.open.return_value = BytesIO(json.dumps(data).encode())

    def test_request_sends_only_text_schema_and_key_in_header(self):
        self.reply(response())
        items = self.model.analyze(TEXT, self.cancelled)
        req = self.transport.open.call_args.args[0]
        payload = json.loads(req.data)
        self.assertEqual(req.full_url, ENDPOINT)
        self.assertNotIn(KEY, req.full_url)
        self.assertNotIn(KEY, req.data.decode())
        self.assertEqual(req.get_header("X-goog-api-key"), KEY)
        self.assertEqual(set(payload), {"contents", "systemInstruction", "generationConfig"})
        self.assertEqual(payload["generationConfig"]["responseMimeType"], "application/json")
        self.assertEqual(items[0]["quote"], TEXT)
        self.assertEqual(items[0]["quote_start"], 0)
        self.assertEqual(self.model.engine["usage"]["totalTokenCount"], 400)
        self.assertNotIn(KEY, json.dumps(self.model.engine))
        self.assertNotIn(KEY, repr(self.config))

    def test_api_quota_error_is_safe_and_not_retried(self):
        body = BytesIO(("secret " + KEY).encode())
        self.transport.open.side_effect = HTTPError(ENDPOINT, 429, KEY, {}, body)
        with self.assertRaisesRegex(GeminiError, "Cota.*429") as caught:
            self.model.analyze(TEXT, self.cancelled)
        self.assertNotIn(KEY, str(caught.exception))
        self.assertTrue(body.closed)
        self.assertEqual(self.transport.open.call_count, 1)

    def test_network_failure_does_not_expose_raw_exception(self):
        self.transport.open.side_effect = URLError(KEY)
        with self.assertRaisesRegex(GeminiError, "conexão") as caught:
            self.model.analyze(TEXT, self.cancelled)
        self.assertNotIn(KEY, str(caught.exception))

    def test_rejects_truncated_blocked_empty_and_unanchored_responses(self):
        wrong = response()
        wrong["candidates"][0]["content"]["parts"] = [{"text": json.dumps({"items": [{
            "quote": "Outra declaração inexistente", "category": "fato", "summary": "Outra declaração",
            "reason": "Fato", "topic": None, "location": None, "period": None, "indicator": None, "comparison": None}]})}]
        for data in ({}, {"candidates": [{"finishReason": "MAX_TOKENS"}]},
                     {"promptFeedback": {"blockReason": "SAFETY"}}, wrong, []):
            with self.subTest(data=data):
                self.model.next_request = 0
                self.reply(data)
                with self.assertRaises(GeminiError):
                    self.model.analyze(TEXT, self.cancelled)

    def test_negation_in_api_summary_is_preserved_by_common_validator(self):
        data = response()
        items = json.loads(data["candidates"][0]["content"]["parts"][1]["text"])["items"]
        items[0]["summary"] = "A inflação caiu para 3,5% em 2025."
        self.reply(response(items))
        result = self.model.analyze(TEXT, self.cancelled)[0]
        self.assertEqual(result["summary"], TEXT)
        self.assertTrue(result["validation_notes"])

    def test_rate_wait_can_be_cancelled_without_sending_next_request(self):
        cancelled = Mock()
        cancelled.wait.return_value = True
        with patch("factcheck.gemini.time.monotonic", return_value=100):
            self.model.next_request = 112
            with self.assertRaises(InterruptedError):
                self.model.analyze(TEXT, cancelled)
        cancelled.wait.assert_called_once_with(12)
        self.transport.open.assert_not_called()

    def test_cancellation_after_response_does_not_produce_claims(self):
        def open_then_cancel(*args, **kwargs):
            self.cancelled.set()
            return BytesIO(json.dumps(response()).encode())
        self.transport.open.side_effect = open_then_cancel
        with self.assertRaises(InterruptedError):
            self.model.analyze(TEXT, self.cancelled)

    def test_redirect_is_refused(self):
        self.assertIsNone(NoRedirect().redirect_request(None, None, 302, "", {}, "https://another.example"))

    def test_missing_key_rejected_before_runner_or_model_start(self):
        with self.assertRaisesRegex(ValueError, "chave"):
            TriageRunner(Path("."), Mock(), Mock(), TriageConfig("gemini"))
        self.assertEqual(TriageConfig().validate().provider, "local")

    def test_worker_selects_gemini_without_loading_local_model(self):
        inputs, outputs = queue.Queue(), queue.Queue()
        inputs.put(("job", TEXT))
        inputs.put(None)
        with patch("factcheck.gemini.GeminiModel", return_value=self.model), patch("factcheck.triage.LocalModel") as local:
            self.reply(response())
            _model_worker(".", inputs, outputs, self.cancelled, self.config)
        local.assert_not_called()
        job, items, error, engine = outputs.get_nowait()
        self.assertEqual(job, "job")
        self.assertIsNone(error)
        self.assertEqual(items[0]["quote"], TEXT)
        self.assertEqual(engine["model"], MODEL)


class GeminiQueueTests(unittest.TestCase):
    def test_quota_failure_stops_remaining_requests_and_preserves_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "session.json").write_text(json.dumps({"debate": asdict(Debate())}), encoding="utf8")
            store = ReviewStore(root)
            for pid in (1, 2):
                store.ingest({"paragraph_id": pid, "version": 1, "source_text": TEXT, "text": TEXT,
                              "start": pid, "end": pid + 1, "closed": True, "parts": []})
            process = Mock()
            process.is_alive.return_value = True
            process.terminate.side_effect = lambda: setattr(process.is_alive, "return_value", False)
            context = SimpleNamespace(Queue=queue.Queue, Event=threading.Event, Process=Mock(return_value=process))
            done = threading.Event()
            notices = []
            def emit(kind, data):
                if kind == "triage_notice":
                    notices.append(data["message"])
                if kind == "triage_update" and runner.pending == 0:
                    done.set()
            with patch("factcheck.triage.mp.get_context", return_value=context):
                runner = TriageRunner(root, store, emit, TriageConfig("gemini", KEY))
                try:
                    runner.enqueue(1)
                    runner.enqueue(2)
                    job_id, text = runner.inputs.get(timeout=3)
                    runner.outputs.put((job_id, None, {"message": "Cota Gemini atingida (429).", "halt": True}, {}))
                    self.assertTrue(done.wait(3))
                    self.assertTrue(runner.inputs.empty())
                    self.assertTrue(runner.blocked_reason)
                    with self.assertRaisesRegex(ValueError, "Cota"):
                        runner.enqueue(1, force=True)
                    self.assertEqual(store.claims(), [])
                    self.assertEqual(len(store.sources()), 2)
                    self.assertEqual({state["status"] for state in store.analysis_states().values()}, {"failed"})
                    self.assertNotIn(KEY, " ".join(notices))
                    self.assertNotIn(KEY.encode(), (root / "review.sqlite3").read_bytes())
                finally:
                    runner.cancel()


if __name__ == "__main__":
    unittest.main()
