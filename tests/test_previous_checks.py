from dataclasses import asdict
from contextlib import closing
from hashlib import sha256
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch

from factcheck.discovery import search_basis
from factcheck.dossiers import DossierStore, render
from factcheck.exports import snapshot
from factcheck.previous_checks import (COMPARISON_FIELDS, PreviousChecksTask, filter_checked_cases, previous_snapshot,
                                      read_checked_cases, refresh_checked_case, render_previous, scan_checked_cases)
from factcheck.review import Debate, ReviewStore


def session(folder, decision=True, title="Debate fictício · inflação"):
    folder.mkdir(parents=True)
    (folder / "session.json").write_text(json.dumps({"debate": asdict(Debate(title=title))}), encoding="utf8")
    review = ReviewStore(folder)
    text = "A inflação ficou em 3% em 2025."
    review.ingest({"paragraph_id": 1, "version": 1, "text": text, "source_text": text, "start": 0, "end": 3,
                   "closed": True, "parts": []})
    job, _ = review.begin_analysis(1)
    review.finish_analysis(job, [{"quote": text, "summary": text, "category": "fato", "reason": "Indicador a conferir.",
        "topic": "Economia", "location": None, "period": "2025", "indicator": "3%", "comparison": None}], {})
    cid = review.claims()[0]["id"]
    store = DossierStore(review)
    if decision:
        store.decide(cid, 0, "inconclusiva", "Revisor fictício", "Faltam documentos para a conclusão.")
    return review, store, cid


def comparison(**changes):
    return {"outcome": "a_conferir", **{key: "Pendente de conferência humana." for key in COMPARISON_FIELDS}, **changes}


class PreviousChecksTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.project = Path(self.directory.name)
        self.root = self.project / "recordings"
        self.folder = self.root / "anterior"
        self.review, self.store, self.cid = session(self.folder)

    def tearDown(self):
        self.directory.cleanup()

    def entry(self):
        return read_checked_cases(self.folder)[0]

    def test_read_only_scan_preserves_every_original_file_and_does_not_import_new_log(self):
        (self.folder / "paragraphs.jsonl").write_text("não importar nem reparar", encoding="utf8")
        before = {path.name: sha256(path.read_bytes()).hexdigest() for path in self.folder.iterdir()}
        entry = scan_checked_cases(self.root)["entries"][0]
        after = {path.name: sha256(path.read_bytes()).hexdigest() for path in self.folder.iterdir()}
        self.assertEqual(before, after)
        self.assertEqual(entry["snapshot"]["decision"]["verdict"], "inconclusiva")
        self.assertFalse(entry["snapshot"]["transcript_reviewed"])
        self.assertTrue(entry["snapshot"]["source_current"])
        self.assertNotIn("folder", entry["snapshot"])

    def test_pending_and_preliminary_cases_are_not_presented_as_previous_human_checks(self):
        review, store, cid = session(self.root / "rascunho", decision=False)
        with review.connection() as db:
            db.execute("INSERT INTO cases VALUES (?,?,?)", (cid, 1, json.dumps({"preliminary": {"verdict": "confirmada"}, "decision": None})))
        self.assertEqual(len(scan_checked_cases(self.root)["entries"]), 1)

    def test_filters_match_accents_words_and_exact_topics_without_network_or_db_reads(self):
        entries = scan_checked_cases(self.root)["entries"]
        with patch("factcheck.previous_checks.sqlite3.connect", side_effect=AssertionError("Não reler o banco")):
            self.assertEqual(filter_checked_cases(entries, "INFLACAO 2025", "Economia", "inconclusiva"), entries)
            self.assertEqual(filter_checked_cases(entries, "inflação saúde"), [])
            self.assertEqual(filter_checked_cases(entries, topic="economia"), [])
            self.assertEqual(filter_checked_cases(entries, verdict="confirmada"), [])

    def test_historical_decision_requires_explicit_filter_and_keeps_original_context(self):
        self.review.revise(1, 1, self.review.source(1)["text"] + " Correção.", None)
        entries = scan_checked_cases(self.root)["entries"]
        self.assertFalse(entries[0]["snapshot"]["source_current"])
        self.assertEqual(filter_checked_cases(entries), [])
        self.assertEqual(filter_checked_cases(entries, include_historical=True), entries)
        self.assertIn("HISTÓRICA", render_previous(entries[0]["snapshot"]))

    def test_missing_database_is_not_created_and_missing_folder_has_visible_warning(self):
        missing = self.root / "sem-banco"
        missing.mkdir()
        (missing / "session.json").write_text("{}", encoding="utf8")
        with self.assertRaises(sqlite3.Error):
            read_checked_cases(missing)
        self.assertFalse((missing / "review.sqlite3").exists())
        self.assertTrue(scan_checked_cases(self.root)["warnings"])
        self.assertTrue(scan_checked_cases(self.project / "inexistente")["warnings"])

    def test_old_corrupt_and_locked_sessions_do_not_prevent_other_results(self):
        corrupt = self.root / "corrompida"
        corrupt.mkdir()
        (corrupt / "review.sqlite3").write_bytes(b"banco ficticio invalido")
        old = self.root / "antiga"
        old.mkdir()
        with closing(sqlite3.connect(old / "review.sqlite3")) as db:
            db.execute("CREATE TABLE claims (id TEXT)")
            db.commit()
        locked_review, _, _ = session(self.root / "bloqueada")
        with closing(sqlite3.connect(locked_review.path)) as db:
            db.execute("BEGIN EXCLUSIVE")
            result = scan_checked_cases(self.root)
            db.rollback()
        self.assertEqual(len(result["entries"]), 1)
        self.assertEqual(len(result["warnings"]), 3)
        with closing(sqlite3.connect(old / "review.sqlite3")) as db:
            self.assertEqual(db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall(), [("claims",)])

    def test_identical_copies_deduplicate_but_divergent_identity_is_omitted(self):
        clone = self.root / "copia"
        shutil.copytree(self.folder, clone)
        self.assertEqual(len(scan_checked_cases(self.root)["entries"]), 1)
        copied = ReviewStore(clone)
        DossierStore(copied).decide(self.cid, 1, "inconclusiva", "Outro revisor", "Nova justificativa.")
        result = scan_checked_cases(self.root)
        self.assertEqual(result["entries"], [])
        self.assertTrue(any("divergente" in item for item in result["warnings"]))

    def test_nested_sessions_are_not_scanned(self):
        nested = self.root / "grupo" / "sessao"
        session(nested)
        self.assertEqual(len(scan_checked_cases(self.root)["entries"]), 1)

    def test_copy_with_invalidated_decision_conflicts_with_copy_that_still_has_it(self):
        clone = self.root / "copia-invalidada"
        shutil.copytree(self.folder, clone)
        copied = ReviewStore(clone)
        claim = copied.claims()[0]
        copied.revise_claim(self.cid, 1, 1, {key: claim[key] for key in ("quote", "summary", "category", "topic")}, "Rever o contexto.")
        result = scan_checked_cases(self.root)
        self.assertEqual(result["entries"], [])
        self.assertTrue(any("divergente" in item for item in result["warnings"]))

    def test_malformed_payloads_are_omitted_with_warning_without_breaking_valid_results(self):
        for index, (table, mutation) in enumerate((("claims", lambda value: {key: item for key, item in value.items() if key != "quote"}),
                ("claims", lambda value: {**value, "context": None}), ("paragraphs", lambda value: []), ("cases", lambda value: []))):
            review, _, _ = session(self.root / f"invalida-{index}")
            with review.connection() as db:
                value = json.loads(db.execute(f"SELECT payload FROM {table}").fetchone()[0])
                db.execute(f"UPDATE {table} SET payload=?", (json.dumps(mutation(value)),))
        result = scan_checked_cases(self.root)
        self.assertEqual(len(result["entries"]), 1)
        self.assertEqual(len(result["warnings"]), 4)

    def test_stale_origin_cannot_be_used_after_decision_changes_or_is_invalidated(self):
        entry = self.entry()
        self.store.decide(self.cid, 1, "inconclusiva", "Revisor fictício", "Conferir fonte adicional.")
        with self.assertRaisesRegex(ValueError, "origem mudou"):
            refresh_checked_case(entry)
        entry = self.entry()
        claim = self.review.claims()[0]
        self.review.revise_claim(self.cid, 1, 1, {key: claim[key] for key in ("quote", "summary", "category", "topic")}, "Rever extração.")
        with self.assertRaises(ValueError):
            refresh_checked_case(entry)

    def test_document_snapshot_contains_provenance_and_locators_but_not_extracted_text_or_secrets(self):
        doc = {"id": "doc-1", "title": "Documento fictício", "url": "https://ibge.gov.br/ensaio", "institution": "Instituição fictícia",
               "acquisition": "local_import", "accessed_at": None, "imported_at": "2026-10-24T12:00:00Z", "sha256": "a" * 64,
               "blocks": [{"id": "b1", "locator": "Página 1", "text": "TEXTO-PRIVADO-NAO-COPIAR"}], "api_key": "SEGREDO-NAO-COPIAR"}
        with self.review.connection() as db:
            db.execute("INSERT INTO evidence VALUES (?,?,?)", ("doc-1", self.cid, json.dumps(doc)))
        data = self.entry()["snapshot"]
        self.assertEqual(data["documents"][0]["locators"], [{"id": "b1", "locator": "Página 1"}])
        self.assertEqual(data["documents"][0]["acquisition"], "local_import")
        self.assertIsNone(data["documents"][0]["accessed_at"])
        self.assertNotIn("NAO-COPIAR", json.dumps(data))
        self.assertIn("acesso: Não confirmado", render_previous(data))

    def test_projection_rejects_changed_fingerprint_and_invalid_decision(self):
        data = self.entry()["snapshot"]
        self.assertNotIn("api_key", previous_snapshot({**data, "api_key": "privada"}))
        for changed in ({"case_revision": 99}, {"decision": None}, {"session_id": "../outra"}, {"source_current": 1}):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                previous_snapshot({**data, **changed})

    def test_cancellation_before_or_during_scan_does_not_return_partial_results(self):
        cancelled = threading.Event()
        cancelled.set()
        with self.assertRaises(InterruptedError):
            scan_checked_cases(self.root, cancelled)
        cancelled.clear()
        original = read_checked_cases
        def cancel_after(*args, **kwargs):
            data = original(*args, **kwargs)
            cancelled.set()
            return data
        with patch("factcheck.previous_checks.read_checked_cases", side_effect=cancel_after), self.assertRaises(InterruptedError):
            scan_checked_cases(self.root, cancelled)

    def test_task_reports_cancellation_and_read_failure_without_leaking_details(self):
        emitted = []
        task = PreviousChecksTask(self.root, lambda kind, data: emitted.append((kind, data)))
        task.cancel()
        task._run()
        self.assertFalse(emitted[-1][1]["success"])
        self.assertEqual(task.pending, 0)
        task = PreviousChecksTask(self.root, lambda kind, data: emitted.append((kind, data)))
        with patch("factcheck.previous_checks.scan_checked_cases", side_effect=OSError("SEGREDO-INTERNO")):
            task._run()
        self.assertNotIn("SEGREDO-INTERNO", str(emitted))


class PreviousCheckDossierTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.project = Path(self.directory.name)
        self.old_review, self.old_store, self.old_cid = session(self.project / "anterior")
        self.entry = read_checked_cases(self.old_review.folder)[0]
        self.origin = self.entry["snapshot"]
        self.review, self.store, self.cid = session(self.project / "atual", decision=False)

    def tearDown(self):
        self.directory.cleanup()

    def basis(self):
        data = self.store.snapshot(self.cid)
        return search_basis(data["claim"], data.get("plan"))

    def record(self, **changes):
        return self.store.record_previous_check(self.cid, self.basis(), self.origin, comparison(**changes), "inflação 2025")

    def test_recording_comparison_preserves_decision_revision_jobs_and_sources(self):
        self.store.decide(self.cid, 0, "inconclusiva", "Revisor atual", "Caso distinto.")
        jid = self.store.begin(self.cid, "collect")
        before = self.store.snapshot(self.cid)
        self.record()
        after = self.store.snapshot(self.cid)
        for key in ("revision", "decision", "preliminary", "documents", "jobs"):
            self.assertEqual(after[key], before[key], key)
        self.assertEqual(after["jobs"][0]["id"], jid)
        self.assertTrue(after["previous_checks"][0]["current"])
        self.assertIn("Checagens anteriores consultadas", render(after))
        self.store.fail(jid, "Encerrar tarefa fictícia.", cancelled=True)
        with self.assertRaisesRegex(ValueError, "Colete"):
            self.store.begin(self.cid, "analyze")

    def test_repeated_comparison_deduplicates_and_changed_notes_preserve_both_versions(self):
        rid = self.record()
        self.assertEqual(self.record(), rid)
        self.record(period="Períodos distintos; não reutilizar a conclusão.", outcome="contexto_diferente")
        self.assertEqual(len(self.store.snapshot(self.cid)["previous_checks"]), 2)

    def test_origin_changes_do_not_rewrite_the_registered_snapshot(self):
        self.record()
        self.old_store.decide(self.old_cid, 1, "inconclusiva", "Revisor posterior", "Outra pesquisa.")
        saved = self.store.snapshot(self.cid)["previous_checks"][0]["origin"]
        self.assertEqual(saved, self.origin)
        self.assertNotEqual(saved, refresh_checked_case(read_checked_cases(self.old_review.folder)[0]))

    def test_plan_changes_mark_reference_historical_and_reject_stale_target(self):
        basis = self.basis()
        self.record()
        self.store.save_plan(self.cid, 0, {"question": "Qual o indicador em 2025?", "scope": "pesquisavel", "period": "2025",
            "territory": "Brasil", "indicator": "IPCA", "comparison": "", "notes": "", "candidate_urls": []})
        self.assertFalse(self.store.snapshot(self.cid)["previous_checks"][0]["current"])
        with self.assertRaises(ValueError):
            self.store.record_previous_check(self.cid, basis, self.origin, comparison())

    def test_extraction_and_transcript_changes_make_previous_consultation_historical(self):
        self.record()
        basis = self.basis()
        claim = self.review.claims()[0]
        self.review.revise_claim(self.cid, 1, 1, {key: claim[key] for key in ("quote", "summary", "category", "topic")}, "Rever o contexto.")
        self.assertFalse(self.store.snapshot(self.cid)["previous_checks"][0]["current"])
        with self.assertRaises(ValueError):
            self.store.record_previous_check(self.cid, basis, self.origin, comparison())
        self.review.revise(1, 1, self.review.source(1)["text"] + " Correção.", None)
        with self.assertRaises(ValueError):
            self.record()

    def test_new_triage_does_not_inherit_old_consultations(self):
        self.record()
        claim = self.review.claims()[0]
        job, _ = self.review.begin_analysis(1, force=True)
        self.review.finish_analysis(job, [{key: claim.get(key) for key in ("quote", "summary", "category", "reason", "topic", "location", "period", "indicator", "comparison")}], {})
        new = next(value for value in self.review.claims() if value["id"] != self.cid)
        self.assertEqual(self.store.snapshot(new["id"])["previous_checks"], [])

    def test_own_case_cannot_be_its_own_antecedent(self):
        self.store.decide(self.cid, 0, "inconclusiva", "Revisor atual", "Sem documentos.")
        own = read_checked_cases(self.review.folder)[0]["snapshot"]
        with self.assertRaisesRegex(ValueError, "próprio caso"):
            self.store.record_previous_check(self.cid, self.basis(), own, comparison())

    def test_missing_or_invalid_comparison_does_not_write(self):
        for values in (comparison(period=""), comparison(territory="x" * 2001), comparison(outcome="confirmada"), {}, None):
            with self.subTest(values=values), self.assertRaises(ValueError):
                self.store.record_previous_check(self.cid, self.basis(), self.origin, values)
        self.assertEqual(self.store.snapshot(self.cid)["previous_checks"], [])

    def test_export_only_contains_recorded_antecedent_without_path_or_unselected_cases(self):
        session(self.project / "privada", title="MARCADOR-PRIVADO-NAO-EXPORTAR")
        self.record()
        data = snapshot(self.review)
        self.assertEqual(data["dossiers"][0]["previous_checks"][0]["origin"], self.origin)
        self.assertEqual(data["sources"], [])
        self.assertNotIn("MARCADOR-PRIVADO-NAO-EXPORTAR", json.dumps(data))
        self.assertNotIn(str(self.old_review.folder), json.dumps(data))

    def test_previous_schema_without_table_still_exports_and_new_store_migrates_lazily(self):
        with self.review.connection() as db:
            db.execute("DROP TABLE previous_checks")
        self.assertEqual(snapshot(self.review)["dossiers"][0]["previous_checks"], [])
        self.store = DossierStore(self.review)
        self.record()
        self.assertEqual(len(self.store.snapshot(self.cid)["previous_checks"]), 1)


if __name__ == "__main__":
    unittest.main()
