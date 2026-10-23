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

from factcheck.dossiers import DossierStore, render
from factcheck.research import ResearchTask, select_blocks, validate_preliminary
from factcheck.review import Debate, ReviewStore
from factcheck.sources import PinnedHTTPS, download, extract_document, public_address, read_local_document, source_url
from factcheck.triage import TriageConfig, validate_items


TEXT = "A inflação foi de 3,5% no Brasil em 2025."
HTML = ("<html><head><title>Indicador de teste</title><meta name='author' content='Equipe de testes'>"
        "<meta property='article:published_time' content='2025-12-31'></head><body><article><h1>Indicador de teste</h1>"
        "<p>Este é um documento fictício usado exclusivamente em um teste automatizado de extração.</p>"
        f"<p>{TEXT} A medição descrita usa a mesma população e o mesmo território durante todo o período.</p>"
        "<p>A metodologia e a série histórica devem ser conferidas pelo revisor. Não usar estes números como dados reais.</p>"
        "</article><script>IGNORAR SCRIPT</script></body></html>").encode()


def document(did="doc1", url="https://www.ibge.gov.br/fonte", text=TEXT):
    return {"id": did, "url": url, "title": "Documento fictício", "author": "Teste", "published_at": "2025-12-31",
            "accessed_at": "2026-10-22T12:00:00+00:00", "sha256": did, "text_sha256": did,
            "content_type": "text/html", "extractor": "test", "institution": "IBGE", "truncated": False, "warnings": [],
            "blocks": [{"id": "b1", "locator": "parágrafo extraído 1", "text": text}]}


def preliminary(**overrides):
    return {"verdict": "confirmada", "summary": TEXT, "reason": "Fonte compatível neste exemplo fictício.", "gaps": [],
            "compatibility": {k: "compativel" for k in ("period", "location", "indicator", "methodology")},
            "citations": [{"document_id": "doc1", "block_id": "b1", "quote": TEXT, "relation": "sustenta", "explanation": "Mesmo recorte."}], **overrides}


def pdf_fixture():
    from pypdf import PdfWriter
    from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
    writer = PdfWriter()
    page = writer.add_blank_page(width=500, height=500)
    font = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"), NameObject("/BaseFont"): NameObject("/Helvetica")})
    page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})})
    stream = DecodedStreamObject()
    stream.set_data(b"BT /F1 12 Tf 40 400 Td (Documento ficticio: o indicador foi de 3,5 por cento em 2025.) Tj ET")
    page[NameObject("/Contents")] = writer._add_object(stream)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


class SourceTests(unittest.TestCase):
    def test_import_rejects_unsupported_files_oversized_content_and_fake_pdf(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            invalid = root / "invalid.pdf"
            invalid.write_bytes(HTML)
            with self.assertRaisesRegex(ValueError, "PDF reconhecível"):
                read_local_document(invalid, "https://ibge.gov.br/teste", threading.Event())
            with self.assertRaisesRegex(ValueError, "PDF ou HTML"):
                read_local_document(root / "file.txt", "https://ibge.gov.br/teste", threading.Event())
            large = root / "large.html"
            large.write_bytes(b"x" * 8_000_001)
            with self.assertRaisesRegex(ValueError, "8 MB"):
                read_local_document(large, "https://ibge.gov.br/teste", threading.Event())

    def test_urls_reject_unlisted_hosts_credentials_private_networks_and_lookalikes(self):
        for url in ("http://www.ibge.gov.br/x", "https://ibge.gov.br.evil.example/x", "https://evilgov.br/x", "https://localhost/",
                    "https://127.0.0.1/", "file:///c:/windows/test", "https://user:pass@ibge.gov.br/", "https://ibge.gov.br:8443/"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                source_url(url)
        self.assertEqual(source_url("https://biblioteca.ibge.gov.br/x#page=2"), "https://biblioteca.ibge.gov.br/x")

    def test_dns_rejects_local_answer_even_mixed_with_public_ip(self):
        answers = [(None, None, None, None, ("8.8.8.8", 443)), (None, None, None, None, ("127.0.0.1", 443))]
        with patch("factcheck.sources.socket.getaddrinfo", return_value=answers), self.assertRaises(ValueError):
            public_address("www.ibge.gov.br")

    def test_connection_uses_validated_ip_alternatives_and_preserves_tls_hostname(self):
        conn = PinnedHTTPS("ibge.gov.br", ["8.8.8.8", "1.1.1.1"])
        sock = Mock()
        conn._context = Mock()
        with patch("factcheck.sources.socket.create_connection", side_effect=[OSError("Rede indisponível"), sock]) as connect:
            conn.connect()
        self.assertEqual(connect.call_count, 2)
        self.assertEqual(connect.call_args.args[0], ("1.1.1.1", 443))
        conn._context.wrap_socket.assert_called_once_with(sock, server_hostname="ibge.gov.br")

    def test_redirect_cannot_escape_allowlist(self):
        response = Mock(status=302)
        response.getheader.side_effect = lambda name, default=None: "https://evil.example/secret" if name == "Location" else default
        conn = Mock()
        conn.getresponse.return_value = response
        with patch("factcheck.sources.public_address", return_value="8.8.8.8"), patch("factcheck.sources.PinnedHTTPS", return_value=conn):
            with self.assertRaises(ValueError):
                download("https://ibge.gov.br/", threading.Event())
        conn.close.assert_called_once()

    def test_large_response_rejected_before_body_download(self):
        response = Mock(status=200)
        response.getheader.side_effect = lambda name, default=None: {"Content-Length": "8000001"}.get(name, default)
        conn = Mock()
        conn.getresponse.return_value = response
        with patch("factcheck.sources.public_address", return_value="8.8.8.8"), patch("factcheck.sources.PinnedHTTPS", return_value=conn):
            with self.assertRaisesRegex(ValueError, "8 MB"):
                download("https://ibge.gov.br/", threading.Event())
        response.read.assert_not_called()

    def test_real_html_extractor_retains_source_words_metadata_and_locators(self):
        doc = extract_document(HTML, "text/html", "https://ibge.gov.br/teste", threading.Event())
        text = "\n".join(b["text"] for b in doc["blocks"])
        self.assertIn(TEXT, text)
        self.assertNotIn("IGNORAR SCRIPT", text)
        self.assertEqual(doc["title"], "Indicador de teste")
        self.assertEqual(doc["published_at"], "2025-12-31")
        self.assertEqual(len(doc["sha256"]), 64)
        self.assertTrue(all(b["id"] and b["locator"] for b in doc["blocks"]))

    def test_pdf_page_locator_uses_real_text_extraction(self):
        doc = extract_document(pdf_fixture(), "application/pdf", "https://ibge.gov.br/teste.pdf", threading.Event())
        self.assertIn("página 1", doc["blocks"][0]["locator"])
        self.assertIn("3,5 por cento", doc["blocks"][0]["text"])

    def test_dynamic_or_empty_document_is_not_treated_as_evidence(self):
        with self.assertRaises(ValueError):
            extract_document(b"<html><body><script>app()</script></body></html>", "text/html", "https://ibge.gov.br/", threading.Event())


class DossierTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        (self.root / "session.json").write_text(json.dumps({"debate": asdict(Debate())}), encoding="utf8")
        self.review = ReviewStore(self.root)
        self.review.ingest({"paragraph_id": 1, "version": 1, "text": TEXT, "source_text": TEXT, "start": 1, "end": 5, "closed": True, "parts": []})
        jid, _ = self.review.begin_analysis(1)
        item = {"quote": TEXT, "summary": TEXT, "reason": "Fato a conferir.", "category": "fato", "topic": "Economia",
                "location": "Brasil", "period": "2025", "indicator": "3,5%", "comparison": None}
        self.review.finish_analysis(jid, validate_items([item], TEXT), {})
        self.cid = self.review.claims()[0]["id"]
        self.store = DossierStore(self.review)

    def tearDown(self):
        self.directory.cleanup()

    def add(self, doc=None):
        jid = self.store.begin(self.cid, "collect")
        self.assertTrue(self.store.finish(jid, doc or document()))

    def test_addition_and_recollection_preserve_single_active_document(self):
        self.add()
        self.add(document(did="same-content", text=TEXT))
        snapshot = self.store.snapshot(self.cid)
        self.assertEqual(len(snapshot["documents"]), 1)
        self.assertEqual(snapshot["documents"][0]["id"], "same-content")
        with self.review.connection() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM history WHERE kind='evidence_superseded'").fetchone()[0], 1)

    def test_identical_recollection_does_not_invalidate_human_decision(self):
        self.add()
        self.store.decide(self.cid, 1, "inconclusiva", "Revisor", "Falta contexto.")
        self.add()
        self.assertEqual(self.store.snapshot(self.cid)["decision"]["reviewer"], "Revisor")

    def combine_with_next(self):
        self.review.ingest({"paragraph_id": 2, "version": 1, "source_text": "Outra declaração fictícia.",
                            "text": "Outra declaração fictícia.", "start": 6, "end": 9,
                            "closed": True, "speaker": None, "parts": []})
        return self.review.combine(1, self.review.source(1)["revision"], 2, 1, True)

    def test_combination_invalidates_dossier_and_late_research_without_erasing_human_decision(self):
        self.store.decide(self.cid, 0, "inconclusiva", "Revisor", "Faltam fontes.")
        decision = self.store.snapshot(self.cid)["decision"]
        job = self.store.begin(self.cid, "collect")
        combined = self.combine_with_next()
        self.assertFalse(self.store.finish(job, document()))
        snapshot = self.store.snapshot(self.cid)
        self.assertFalse(snapshot["valid"])
        self.assertEqual(snapshot["decision"], decision)
        self.assertEqual(snapshot["documents"], [])
        self.assertIn("DESATUALIZADO", render(snapshot))
        self.review.uncombine(combined["paragraph_id"], 1)
        self.assertFalse(self.store.snapshot(self.cid)["valid"])

    def test_new_combined_claim_keeps_origin_paragraph_ids_in_dossier(self):
        combined = self.combine_with_next()
        job, source = self.review.begin_analysis(combined["paragraph_id"])
        item = {"quote": source["text"], "summary": source["text"], "reason": "Exemplo fictício.",
                "category": "fato", "topic": "Economia", "location": None,
                "period": None, "indicator": None, "comparison": None}
        self.review.finish_analysis(job, validate_items([item], source["text"]), {})
        claim = self.review.claims()[0]
        self.assertEqual(claim["source_paragraph_ids"], [1, 2])
        exported = render(self.store.snapshot(claim["id"]))
        self.assertIn("Parágrafos de origem da combinação: 1, 2", exported)
        self.assertIn("PENDENTE DE REVISÃO HUMANA", exported)

    def test_video_reference_changes_exported_times_without_changing_editorial_decision(self):
        self.store.decide(self.cid, 0, "inconclusiva", "Revisor", "Faltam fontes.")
        before = self.store.snapshot(self.cid)
        self.review.save_video_reference(750, 0)
        after = self.store.snapshot(self.cid)
        self.assertEqual(after["decision"], before["decision"])
        self.assertEqual(after["claim"], before["claim"])
        self.assertEqual(after["revision"], before["revision"])
        exported = render(after)
        self.assertIn("00:12:31 → 00:12:35", exported)
        self.assertIn("captura: 1.0–5.0 s", exported)
        self.assertIn("Referência manual atual: vídeo em 00:12:30", exported)
        self.assertIn("REVISADO POR PESSOA", exported)
        self.review.save_video_reference(None, 1)
        cleared = render(self.store.snapshot(self.cid))
        self.assertIn("Referência do vídeo não definida", cleared)
        self.assertNotIn("00:12:31", cleared)

    def test_native_local_import_requires_no_network_and_records_unconfirmed_origin(self):
        file = self.root / "documento-ficticio.html"
        file.write_bytes(HTML)
        done = threading.Event()
        task = ResearchTask(self.store, self.cid, "import", {"path": str(file), "url": "https://ibge.gov.br/teste"},
                            TriageConfig(), lambda *args: done.set())
        with patch("factcheck.research.download") as download_mock:
            task.start()
            self.assertTrue(done.wait(15))
        download_mock.assert_not_called()
        snapshot = self.store.snapshot(self.cid)
        self.assertEqual(len(snapshot["documents"]), 1)
        doc = snapshot["documents"][0]
        self.assertEqual(doc["acquisition"], "local_import")
        self.assertEqual(doc["accessed_at"], "")
        self.assertEqual(doc["file_name"], file.name)
        self.assertIn("não consultada", " ".join(doc["warnings"]))
        self.assertNotIn(str(file).encode(), self.review.path.read_bytes())
        exported = render(snapshot)
        self.assertIn("cópia importada pelo operador", exported)
        self.assertIn("acesso à URL: Não confirmado", exported)
        self.assertEqual(file.read_bytes(), HTML)

    def test_native_pdf_import_preserves_original_and_page_locator(self):
        file = self.root / "documento-ficticio.pdf"
        original = pdf_fixture()
        file.write_bytes(original)
        done = threading.Event()
        task = ResearchTask(self.store, self.cid, "import", {"path": str(file), "url": "https://ibge.gov.br/teste.pdf"},
                            TriageConfig(), lambda *args: done.set())
        with patch("factcheck.research.download") as download_mock:
            task.start()
            self.assertTrue(done.wait(15))
        download_mock.assert_not_called()
        doc = self.store.snapshot(self.cid)["documents"][0]
        self.assertEqual(doc["acquisition"], "local_import")
        self.assertIn("página 1", doc["blocks"][0]["locator"])
        self.assertIn("3,5 por cento", doc["blocks"][0]["text"])
        self.assertEqual(file.read_bytes(), original)

    def test_local_copy_cannot_downgrade_same_content_already_retrieved_online(self):
        self.add()
        self.store.decide(self.cid, 1, "inconclusiva", "Revisor", "Falta contexto.")
        local = {**document("local"), "sha256": "doc1", "acquisition": "local_import"}
        self.store.finish(self.store.begin(self.cid, "import"), local)
        snapshot = self.store.snapshot(self.cid)
        self.assertEqual(snapshot["documents"][0]["id"], "doc1")
        self.assertIsNotNone(snapshot["decision"])

    def test_online_recollection_upgrades_imported_copy_and_requires_new_review(self):
        local = {**document("local"), "sha256": "same-bytes", "acquisition": "local_import"}
        self.store.finish(self.store.begin(self.cid, "import"), local)
        self.store.decide(self.cid, 1, "inconclusiva", "Revisor", "Origem não conferida.")
        remote = {**document("remote"), "sha256": "same-bytes", "acquisition": "remote_fetch"}
        self.add(remote)
        snapshot = self.store.snapshot(self.cid)
        self.assertEqual(snapshot["documents"][0]["acquisition"], "remote_fetch")
        self.assertIsNone(snapshot["decision"])

    def test_new_evidence_clears_decision_but_preserves_history(self):
        self.add()
        self.store.decide(self.cid, 1, "confirmada", "Revisor", "Conferido neste teste.")
        self.add(document("doc2", "https://bcb.gov.br/fonte"))
        self.assertIsNone(self.store.snapshot(self.cid)["decision"])
        with self.review.connection() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM history WHERE kind='human_decision'").fetchone()[0], 1)

    def test_removing_source_preserves_copy_in_history_and_invalidates_decision(self):
        self.add()
        self.store.decide(self.cid, 1, "confirmada", "Revisor", "Conferido.")
        self.store.remove_document(self.cid, 2, "doc1", "Documento de outro indicador.")
        snapshot = self.store.snapshot(self.cid)
        self.assertEqual(snapshot["documents"], [])
        self.assertIsNone(snapshot["decision"])
        with self.review.connection() as db:
            payload = json.loads(db.execute("SELECT payload FROM history WHERE kind='evidence_removed'").fetchone()[0])
        self.assertEqual(payload["document"]["blocks"][0]["text"], TEXT)

    def test_stale_reviewer_cannot_overwrite_a_more_recent_decision(self):
        self.store.decide(self.cid, 0, "inconclusiva", "Primeiro revisor", "Faltam evidências.")
        with self.assertRaises(ValueError):
            self.store.decide(self.cid, 0, "inconclusiva", "Segundo revisor", "Outra leitura.")
        self.assertEqual(self.store.snapshot(self.cid)["decision"]["reviewer"], "Primeiro revisor")

    def test_old_analysis_cannot_overwrite_human_revision_of_dossier(self):
        self.add()
        jid = self.store.begin(self.cid, "analyze")
        self.store.decide(self.cid, 1, "inconclusiva", "Revisor", "Metodologia não identificada.")
        self.assertFalse(self.store.finish(jid, preliminary(), {}))
        self.assertIsNone(self.store.snapshot(self.cid)["preliminary"])
        self.assertEqual(self.store.snapshot(self.cid)["decision"]["verdict"], "inconclusiva")

    def test_transcript_revision_invalidates_case_and_rejects_late_collection(self):
        jid = self.store.begin(self.cid, "collect")
        self.review.revise(1, 1, TEXT + " Texto corrigido.", None)
        self.assertFalse(self.store.finish(jid, document()))
        self.assertFalse(self.store.snapshot(self.cid)["valid"])
        self.assertIn("DESATUALIZADO", render(self.store.snapshot(self.cid)))
        with self.assertRaises(ValueError):
            self.store.decide(self.cid, 0, "inconclusiva", "Revisor", "Teste.")

    def test_conclusive_human_review_requires_source_and_responsible(self):
        with self.assertRaises(ValueError):
            self.store.decide(self.cid, 0, "confirmada", "Revisor", "Sem documento.")
        with self.assertRaises(ValueError):
            self.store.decide(self.cid, 0, "inconclusiva", "", "Falta evidência.")

    def test_local_configuration_cannot_start_remote_evidence_analysis(self):
        with self.assertRaisesRegex(ValueError, "Gemini explicitamente"):
            ResearchTask(self.store, self.cid, "analyze", "", TriageConfig(), Mock())
        self.assertEqual(self.store.snapshot(self.cid)["jobs"], [])

    def test_query_and_export_remain_internal_and_distinguish_preliminary_from_decision(self):
        self.add()
        self.store.record_query(self.cid, "IPCA 2025 site:ibge.gov.br")
        jid = self.store.begin(self.cid, "analyze")
        self.store.finish(jid, preliminary(), {"model": "simulated"})
        text = render(self.store.snapshot(self.cid))
        self.assertIn("PENDENTE DE REVISÃO HUMANA", text)
        self.assertIn("não aprovada", text)
        self.assertIn("SHA-256", text)
        self.assertIn("IPCA 2025 site:ibge.gov.br", text)
        self.assertIsNone(self.store.snapshot(self.cid)["decision"])

    def test_native_extraction_process_and_simulated_gemini_complete_internal_workflow(self):
        done = threading.Event()
        with patch("factcheck.research.download", return_value=(HTML, "text/html", "https://ibge.gov.br/teste")):
            task = ResearchTask(self.store, self.cid, "collect", "https://ibge.gov.br/teste", TriageConfig(), lambda *args: done.set())
            task.start()
            self.assertTrue(done.wait(15))
        snapshot = self.store.snapshot(self.cid)
        self.assertEqual(len(snapshot["documents"]), 1)
        doc = snapshot["documents"][0]
        block = next(b for b in doc["blocks"] if TEXT in b["text"])
        result = preliminary()
        result["citations"][0].update(document_id=doc["id"], block_id=block["id"])
        result["compatibility"]["methodology"] = "indefinido"
        done.clear()
        with patch("factcheck.gemini.GeminiModel.generate", return_value=result):
            task = ResearchTask(self.store, self.cid, "analyze", "", TriageConfig("gemini", "ficticia"), lambda *args: done.set())
            task.start()
            self.assertTrue(done.wait(10))
        snapshot = self.store.snapshot(self.cid)
        self.assertEqual(snapshot["preliminary"]["verdict"], "inconclusiva")
        self.assertIsNone(snapshot["decision"])
        self.store.decide(self.cid, snapshot["revision"], "inconclusiva", "Revisor de teste", "Falta compatibilidade metodológica.")
        exported = render(self.store.snapshot(self.cid))
        self.assertIn("REVISADO POR PESSOA", exported)
        self.assertIn(doc["sha256"], exported)

    def test_recovery_preserves_running_job_owned_by_live_process(self):
        jid = self.store.begin(self.cid, "collect")
        with patch("factcheck.dossiers.process_alive", return_value=True):
            self.store.recover()
        self.assertEqual(self.store.snapshot(self.cid)["jobs"][0]["status"], "running")
        with patch("factcheck.dossiers.process_alive", return_value=False):
            self.store.recover()
        self.assertEqual(self.store.snapshot(self.cid)["jobs"][0]["status"], "interrupted")

    def test_cancel_before_start_does_not_start_network_or_save_result(self):
        process = Mock()
        process.is_alive.return_value = True
        context = SimpleNamespace(Queue=queue.Queue, Event=threading.Event, Process=Mock(return_value=process))
        done = threading.Event()
        events = []
        task = ResearchTask(self.store, self.cid, "collect", "https://ibge.gov.br/", TriageConfig(), lambda k, d: (events.append((k, d)), done.set()))
        with patch("factcheck.research.mp.get_context", return_value=context):
            task.cancel()
            task.start()
            self.assertTrue(done.wait(3))
        self.assertEqual(task.pending, 0)
        self.assertEqual(self.store.snapshot(self.cid)["documents"], [])
        self.assertEqual(self.store.snapshot(self.cid)["jobs"][0]["status"], "cancelled")
        self.assertEqual(events[0][1]["token"], task.token)

    def test_cancel_during_network_discards_response_that_arrives_later(self):
        started, release, done = threading.Event(), threading.Event(), threading.Event()
        def network(kind, argument, snapshot, config, cancelled, outputs):
            started.set()
            release.wait(3)
            outputs.put((document(), {}, None))
        self.add()
        task = ResearchTask(self.store, self.cid, "analyze", "", TriageConfig("gemini", "ficticia"), lambda *args: done.set())
        with patch("factcheck.research._network_worker", network):
            task.start()
            self.assertTrue(started.wait(2))
            task.cancel()
            self.assertTrue(done.wait(2))
            release.set()
        self.assertIsNone(self.store.snapshot(self.cid)["preliminary"])
        self.assertEqual(self.store.snapshot(self.cid)["jobs"][-1]["status"], "cancelled")


class PreliminaryTests(unittest.TestCase):
    def setUp(self):
        self.blocks = [{"document_id": "doc1", **document()["blocks"][0]}]

    def test_literal_quote_with_matching_recuts_can_produce_preliminary_result(self):
        self.assertEqual(validate_preliminary(preliminary(), self.blocks)["verdict"], "confirmada")

    def test_conclusive_analysis_based_on_imported_copy_remains_inconclusive(self):
        from factcheck.research import analyze
        doc = {**document(), "acquisition": "local_import", "accessed_at": ""}
        snapshot = {"claim": {"quote": TEXT}, "debate": {"event_date": "2026-10-22"}, "documents": [doc]}
        with patch("factcheck.research.GeminiModel") as model:
            model.return_value.generate.return_value = preliminary()
            model.return_value.engine = {"model": "simulated"}
            result, engine = analyze(snapshot, TriageConfig("gemini", "ficticia"), threading.Event())
        self.assertEqual(result["verdict"], "inconclusiva")
        self.assertTrue(any("origem online" in gap for gap in result["gaps"]))

    def test_unknown_source_or_invented_quote_is_rejected(self):
        for field, value in (("document_id", "invented"), ("block_id", "unknown"), ("quote", "Dado que não existe na fonte.")):
            result = preliminary()
            result["citations"][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_preliminary(result, self.blocks)

    def test_missing_recuts_or_citations_cannot_confirm_claim(self):
        result = preliminary()
        result["compatibility"]["period"] = "indefinido"
        self.assertEqual(validate_preliminary(result, self.blocks)["verdict"], "inconclusiva")
        self.assertEqual(validate_preliminary(preliminary(citations=[]), self.blocks)["verdict"], "inconclusiva")

    def test_negation_cannot_be_dropped_from_literal_citation(self):
        block = {"document_id": "doc1", "id": "b1", "text": "Não houve redução do indicador no período de referência."}
        result = preliminary()
        result["citations"][0]["quote"] = "houve redução do indicador no período de referência."
        with self.assertRaises(ValueError):
            validate_preliminary(result, [block])

    def test_quote_cannot_cut_a_number_in_half(self):
        block = {"document_id": "doc1", "id": "b1", "text": "O índice fechou o período em 30,5%."}
        result = preliminary()
        result["citations"][0]["quote"] = "O índice fechou o período em 30"
        with self.assertRaises(ValueError):
            validate_preliminary(result, [block])

    def test_selected_evidence_has_explicit_bounds_and_preserves_original_ids(self):
        snapshot = {"claim": {"quote": TEXT}, "documents": [document(text=TEXT * 3000)]}
        selected = select_blocks(snapshot)
        self.assertLessEqual(sum(len(b["text"]) for b in selected), 24000)
        self.assertEqual(selected[0]["id"], "b1")
        self.assertEqual(selected[0]["document_id"], "doc1")


if __name__ == "__main__":
    unittest.main()
