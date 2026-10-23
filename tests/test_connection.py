from io import BytesIO
import json
import socket
import ssl
import threading
import unittest
from unittest.mock import Mock, patch
from urllib.error import URLError

from factcheck.connection_test import ConnectionTest
from factcheck.gemini import GeminiError, GeminiModel
from factcheck.net_errors import network_message
from factcheck.triage import TriageConfig


KEY = "chave-ficticia-do-teste"


class ConnectionTests(unittest.TestCase):
    def test_probe_request_contains_only_synthetic_text_and_small_output_limit(self):
        model = GeminiModel(TriageConfig("gemini", KEY))
        model.opener = Mock()
        data = {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": '{"ok": true}'}]}}]}
        model.opener.open.return_value = BytesIO(json.dumps(data).encode())
        engine = model.test_connection(threading.Event())
        request = model.opener.open.call_args.args[0]
        body = request.data.decode()
        self.assertIn("fictício", json.loads(body)["contents"][0]["parts"][0]["text"])
        self.assertNotIn(KEY, body)
        self.assertNotIn(KEY, request.full_url)
        self.assertEqual(json.loads(body)["generationConfig"]["maxOutputTokens"], 128)
        self.assertEqual(engine["provider"], "google")

    def test_malformed_probe_cannot_validate_key(self):
        model = GeminiModel(TriageConfig("gemini", KEY))
        for response in ({"ok": 1}, {"ok": False}, {"ok": True, "extra": 1}, []):
            with self.subTest(response=response), patch.object(model, "generate", return_value=response):
                with self.assertRaises(GeminiError):
                    model.test_connection(threading.Event())

    def test_successful_probe_emits_no_credentials_and_does_not_persist_config(self):
        done, events = threading.Event(), []
        task = ConnectionTest(TriageConfig("gemini", KEY), lambda k, d: (events.append((k, d)), done.set()))
        with patch("factcheck.connection_test.GeminiModel") as model:
            model.return_value.test_connection.return_value = {"model": "simulated"}
            task.start()
            self.assertTrue(done.wait(3))
        self.assertEqual(task.pending, 0)
        self.assertEqual(events[0][0], "connection_test_done")
        self.assertTrue(events[0][1]["success"])
        self.assertNotIn(KEY, json.dumps(events))

    def test_cancelled_probe_does_not_accept_late_success(self):
        began, release, done = threading.Event(), threading.Event(), threading.Event()
        events = []
        def slow(*args):
            began.set()
            release.wait(3)
            return {"model": "simulated"}
        task = ConnectionTest(TriageConfig("gemini", KEY), lambda k, d: (events.append(d), done.set()))
        with patch("factcheck.connection_test.GeminiModel") as model:
            model.return_value.test_connection.side_effect = slow
            task.start()
            self.assertTrue(began.wait(2))
            task.cancel()
            self.assertTrue(done.wait(2))
            release.set()
        self.assertFalse(events[0]["success"])
        self.assertEqual(len(events), 1)
        self.assertIn("cancelado", events[0]["message"])

    def test_unexpected_exception_does_not_expose_key(self):
        done, events = threading.Event(), []
        task = ConnectionTest(TriageConfig("gemini", KEY), lambda k, d: (events.append(d), done.set()))
        with patch("factcheck.connection_test.GeminiModel", side_effect=RuntimeError(KEY)):
            task.start()
            self.assertTrue(done.wait(3))
        self.assertFalse(events[0]["success"])
        self.assertNotIn(KEY, json.dumps(events))

    def test_network_diagnostics_distinguish_causes_without_raw_details(self):
        cases = [(PermissionError(KEY), "bloqueou"), (socket.gaierror(KEY), "DNS"),
                 (ssl.SSLCertVerificationError(KEY), "certificado"), (TimeoutError(KEY), "tempo"), (URLError(KEY), "internet")]
        for exc, expected in cases:
            with self.subTest(expected=expected):
                message = network_message(URLError(exc), "o Gemini")
                self.assertIn(expected, message)
                self.assertNotIn(KEY, message)


if __name__ == "__main__":
    unittest.main()
