from dataclasses import asdict
from io import BytesIO
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

from factcheck.discovery import ENDPOINT, SearchConfig, SearchError, TavilySearch, parse_results
from factcheck.dossiers import DossierStore, render
from factcheck.exports import snapshot as export_snapshot
from factcheck.research import ResearchTask
from factcheck.review import Debate, ReviewStore


KEY = "tvly-chave-ficticia-para-testes"
QUERY = "IPCA Brasil 2025 metodologia"
TEXT = "A inflação ficou em 3% em 2025."


def response():
    return {"results": [{"title": "Índice e metodologia", "url": "https://ibge.gov.br/teste#top",
                         "content": "Este snippet não deve virar evidência.", "raw_content": "Não persistir."}],
            "usage": {"credits": 1}, "answer": "Não usar a resposta gerada."}


class SearchClientTests(unittest.TestCase):
    def setUp(self):
        self.client = TavilySearch(SearchConfig(KEY))
        self.client.opener = Mock()
        self.cancelled = threading.Event()

    def reply(self, data):
        self.client.opener.open.return_value = BytesIO(json.dumps(data).encode())

    def test_request_uses_header_key_bounded_basic_search_and_no_generated_answer(self):
        self.reply(response())
        result, engine = self.client.search(QUERY, self.cancelled)
        request = self.client.opener.open.call_args.args[0]
        payload = json.loads(request.data)
        self.assertEqual(request.full_url, ENDPOINT)
        self.assertEqual(request.get_header("Authorization"), "Bearer " + KEY)
        self.assertNotIn(KEY, request.data.decode())
        self.assertEqual(payload["search_depth"], "basic")
        self.assertFalse(payload["auto_parameters"])
        self.assertFalse(payload["include_answer"])
        self.assertFalse(payload["include_raw_content"])
        self.assertEqual(payload["include_domains_mode"], "restrict")
        self.assertEqual(payload["max_results"], 5)
        self.assertEqual(result["candidates"][0]["url"], "https://ibge.gov.br/teste")
        self.assertNotIn("snippet", json.dumps(result))
        self.assertEqual(engine["credits"], 1)
        self.assertNotIn(KEY, repr(self.client.config))

    def test_filters_duplicates_unlisted_urls_credentials_ports_and_non_https(self):
        urls = ["https://ibge.gov.br/teste", "https://ibge.gov.br/teste#other", "https://ibge.gov.br.evil.example/x",
                "https://evilgov.br/x", "https://user:pass@ibge.gov.br/x", "https://ibge.gov.br:8443/x",
                "http://ibge.gov.br/x", "https://127.0.0.1/x", "https://www.tse.jus.br/teste"]
        data = {"results": [{"url": url} for url in urls] + [None, {"url": 42}]}
        result, _ = parse_results(data, QUERY)
        self.assertEqual([item["url"] for item in result["candidates"]], [urls[0], urls[-1]])
        self.assertEqual(result["discarded_count"], 9)

    def test_limits_results_and_handles_empty_search_without_a_factual_answer(self):
        data = {"results": [{"url": f"https://ibge.gov.br/{i}"} for i in range(9)]}
        result, _ = parse_results(data, QUERY)
        self.assertEqual(len(result["candidates"]), 5)
        self.assertEqual(result["discarded_count"], 4)
        self.reply({"results": []})
        self.assertEqual(self.client.search(QUERY, self.cancelled)[0]["candidates"], [])

    def test_quota_auth_and_redirect_errors_are_safe_and_not_retried(self):
        for status in (301, 400, 401, 403, 422, 429, 432, 433, 500):
            with self.subTest(status=status):
                body = BytesIO(KEY.encode())
                self.client.opener.open.side_effect = HTTPError(ENDPOINT, status, KEY, {}, body)
                self.client.opener.open.reset_mock()
                with self.assertRaises(SearchError) as caught:
                    self.client.search(QUERY, self.cancelled)
                self.assertNotIn(KEY, str(caught.exception))
                self.assertTrue(body.closed)
                self.client.opener.open.assert_called_once()

    def test_transport_error_does_not_leak_raw_message(self):
        self.client.opener.open.side_effect = URLError(KEY)
        with self.assertRaises(SearchError) as caught:
            self.client.search(QUERY, self.cancelled)
        self.assertNotIn(KEY, str(caught.exception))

    def test_bad_json_shape_oversized_data_and_invalid_usage_are_handled(self):
        for raw in (b"not json", b"x" * 1_000_001, b'{"results": {}}', b'null'):
            with self.subTest(raw_size=len(raw)):
                self.client.opener.open.return_value = BytesIO(raw)
                with self.assertRaises(SearchError):
                    self.client.search(QUERY, self.cancelled)
        for credits in (True, -1, float("nan"), "one", float("inf")):
            data = {**response(), "usage": {"credits": credits}}
            self.assertNotIn("credits", parse_results(data, QUERY)[1])

    def test_missing_key_invalid_query_and_cancellation_do_not_make_request(self):
        for key in ("", "has space", "key\r\nheader", "á", "x" * 513):
            with self.subTest(key_length=len(key)), self.assertRaises(ValueError):
                SearchConfig(key).validate()
        for query in ("", "\n", "x" * 1001, "line\nbreak", None):
            with self.subTest(query_type=type(query).__name__), self.assertRaises(ValueError):
                self.client.search(query, self.cancelled)
        self.cancelled.set()
        with self.assertRaises(InterruptedError):
            self.client.search(QUERY, self.cancelled)
        self.client.opener.open.assert_not_called()

    def test_response_arriving_after_cancellation_is_ignored(self):
        def reply(*args, **kwargs):
            self.cancelled.set()
            return BytesIO(json.dumps(response()).encode())
        self.client.opener.open.side_effect = reply
        with self.assertRaises(InterruptedError):
            self.client.search(QUERY, self.cancelled)


class DiscoveryWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.folder = Path(self.directory.name)
        (self.folder / "session.json").write_text(json.dumps({"debate": asdict(Debate())}), encoding="utf8")
        self.review = ReviewStore(self.folder)
        self.review.ingest({"paragraph_id": 1, "version": 1, "text": TEXT, "source_text": TEXT,
                            "start": 0, "end": 4, "closed": True, "parts": []})
        jid, _ = self.review.begin_analysis(1)
        self.review.finish_analysis(jid, [{"quote": TEXT, "summary": TEXT, "category": "fato", "topic": "Economia",
            "reason": "Indicador a conferir.", "location": None, "period": "2025", "indicator": "3%", "comparison": None}], {})
        self.cid = self.review.claims()[0]["id"]
        self.store = DossierStore(self.review)

    def tearDown(self):
        self.directory.cleanup()

    def finish_search(self):
        jid = self.store.begin(self.cid, "discover", QUERY)
        result, engine = parse_results(response(), QUERY)
        self.assertTrue(self.store.finish(jid, result, engine))
        return jid

    def test_search_is_persisted_separately_and_does_not_change_human_decision(self):
        self.store.decide(self.cid, 0, "inconclusiva", "Revisor fictício", "Faltam fontes.")
        before = self.store.snapshot(self.cid)
        self.finish_search()
        after = self.store.snapshot(self.cid)
        self.assertEqual(after["decision"], before["decision"])
        self.assertEqual(after["revision"], before["revision"])
        self.assertEqual(after["documents"], [])
        self.assertIsNone(after["preliminary"])
        self.assertTrue(after["discoveries"][0]["current"])
        self.assertEqual(DossierStore(self.review).snapshot(self.cid)["discoveries"], after["discoveries"])
        self.assertIn("candidatas, não evidências", render(after))

    def test_discard_requires_reason_preserves_history_and_does_not_affect_case(self):
        sid = self.finish_search()
        with self.assertRaises(ValueError):
            self.store.discard_candidate(self.cid, sid, "c1", " ")
        self.store.discard_candidate(self.cid, sid, "c1", "O documento trata de outro período.")
        batch = self.store.snapshot(self.cid)["discoveries"][0]
        self.assertEqual(batch["candidates"][0]["disposition"], "discarded")
        self.assertEqual(self.store.snapshot(self.cid)["revision"], 0)
        with self.assertRaises(ValueError):
            self.store.discard_candidate(self.cid, sid, "c1", "Outra justificativa.")
        with self.review.connection() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM history WHERE kind='candidate_discarded'").fetchone()[0], 1)

    def test_changed_plan_keeps_search_historical_and_rejects_late_search(self):
        sid = self.finish_search()
        jid = self.store.begin(self.cid, "discover", QUERY)
        self.store.save_plan(self.cid, 0, {"question": "Qual o IPCA nacional em 2025?", "scope": "pesquisavel",
            "period": "2025", "territory": "Brasil", "indicator": "IPCA", "comparison": "", "notes": "", "candidate_urls": []})
        self.assertFalse(self.store.finish(jid, *parse_results(response(), QUERY)))
        batch = self.store.snapshot(self.cid)["discoveries"][0]
        self.assertFalse(batch["current"])
        with self.assertRaises(ValueError):
            self.store.discard_candidate(self.cid, sid, "c1", "Antiga.")

    def test_transcript_edit_rejects_old_results(self):
        jid = self.store.begin(self.cid, "discover", QUERY)
        self.review.revise(1, 1, TEXT + " Correção.", None)
        self.assertFalse(self.store.finish(jid, *parse_results(response(), QUERY)))
        self.assertEqual(self.store.snapshot(self.cid)["discoveries"], [])

    def test_extraction_edit_rejects_old_results(self):
        jid = self.store.begin(self.cid, "discover", QUERY)
        claim = self.review.claims()[0]
        fields = {key: claim.get(key) for key in ("quote", "summary", "category", "topic")}
        fields["topic"] = "Indicadores"
        self.review.revise_claim(self.cid, 1, 1, fields, "Tema corrigido.")
        self.assertFalse(self.store.finish(jid, *parse_results(response(), QUERY)))
        self.assertEqual(self.store.snapshot(self.cid)["discoveries"], [])

    def test_search_cannot_enable_analysis_without_collected_evidence(self):
        self.finish_search()
        with self.assertRaisesRegex(ValueError, "Colete"):
            self.store.begin(self.cid, "analyze")
        with self.assertRaises(ValueError):
            self.store.decide(self.cid, 0, "confirmada", "Revisor", "Somente links.")

    def test_json_exports_searches_separately_from_evidence_and_preserves_discard(self):
        sid = self.finish_search()
        self.store.discard_candidate(self.cid, sid, "c1", "Fora do recorte.")
        data = export_snapshot(self.review)
        self.assertEqual(data["sources"], [])
        self.assertEqual(data["dossiers"][0]["discoveries"][0]["candidates"][0]["discard_reason"], "Fora do recorte.")
        self.assertFalse(data["dossiers"][0]["preliminary_current"])

    def test_controller_completes_search_and_never_invokes_document_extraction_or_gemini(self):
        done = threading.Event()
        client = TavilySearch(SearchConfig(KEY))
        client.opener = Mock()
        client.opener.open.return_value = BytesIO(json.dumps(response()).encode())
        with patch("factcheck.research.TavilySearch", return_value=client), patch("factcheck.research.download") as download, \
                patch("factcheck.research.GeminiModel") as gemini, patch("factcheck.research.extract_document") as extract:
            task = ResearchTask(self.store, self.cid, "discover", QUERY, SearchConfig(KEY), lambda *args: done.set())
            task.start()
            self.assertTrue(done.wait(5))
        self.assertEqual(task.pending, 0)
        download.assert_not_called()
        gemini.assert_not_called()
        extract.assert_not_called()
        self.assertEqual(len(self.store.snapshot(self.cid)["discoveries"]), 1)
        for file in self.folder.iterdir():
            if file.is_file():
                self.assertNotIn(KEY.encode(), file.read_bytes())

    def test_controller_cancellation_discards_a_late_response(self):
        entered, release, done = threading.Event(), threading.Event(), threading.Event()
        def late(*args):
            entered.set()
            release.wait(5)
            return parse_results(response(), QUERY)
        with patch("factcheck.research.TavilySearch") as client:
            client.return_value.search.side_effect = late
            task = ResearchTask(self.store, self.cid, "discover", QUERY, SearchConfig(KEY), lambda *args: done.set())
            task.start()
            self.assertTrue(entered.wait(3))
            task.cancel()
            release.set()
            self.assertTrue(done.wait(3))
        self.assertEqual(self.store.snapshot(self.cid)["discoveries"], [])
        self.assertEqual(self.store.snapshot(self.cid)["jobs"][0]["status"], "cancelled")

    def test_missing_key_and_query_do_not_create_running_job(self):
        for config, query in ((SearchConfig(), QUERY), (SearchConfig(KEY), "")):
            with self.assertRaises(ValueError):
                ResearchTask(self.store, self.cid, "discover", query, config, Mock())
        self.assertEqual(self.store.snapshot(self.cid)["jobs"], [])


if __name__ == "__main__":
    unittest.main()
