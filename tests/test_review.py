from dataclasses import asdict
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from factcheck.review import Debate, ReviewStore
from factcheck.triage import validate_items


def paragraph(text="A inflação caiu para 3,5% em 2025.", version=1, closed=True):
    return {"paragraph_id": 1, "version": version, "source_text": text, "text": text,
            "start": 1.0, "end": 5.0, "speaker": None, "closed": closed, "parts": []}


def item(quote="A inflação caiu para 3,5% em 2025.", category="fato", **kwargs):
    return {"quote": quote, "category": category, "summary": quote, "reason": "Declaração a revisar.",
            "topic": "Economia", "location": None, "period": None, "indicator": None, "comparison": None, **kwargs}


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.folder = Path(self.directory.name)
        (self.folder / "session.json").write_text(json.dumps({"debate": asdict(Debate(participants=["Ana", "Bruno"]))}), encoding="utf8")
        self.store = ReviewStore(self.folder)
        self.store.ingest(paragraph())

    def tearDown(self):
        self.directory.cleanup()

    def complete(self, items=None):
        job_id, source = self.store.begin_analysis(1)
        items = validate_items(items or [item()], source["text"])
        self.assertTrue(self.store.finish_analysis(job_id, items, {"name": "test"}))
        return self.store.claims()

    def test_revision_preserves_original_and_invalidates_previous_claims(self):
        self.complete()
        source = self.store.revise(1, 1, "A inflação caiu para 4% em 2025.", "Ana")
        self.assertEqual(source["revision"], 2)
        self.assertEqual(source["original"]["source_text"], paragraph()["source_text"])
        self.assertTrue(source["human_reviewed"])
        self.assertEqual(self.store.claims()[0]["status"], "analise_desatualizada")
        reloaded = ReviewStore(self.folder)
        self.assertEqual(reloaded.source(1)["speaker"], "Ana")
        with self.store.connection() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM history WHERE kind='human_revision'").fetchone()[0], 1)

    def test_stale_results_cannot_attach_to_new_source_revision(self):
        job_id, source = self.store.begin_analysis(1)
        self.store.revise(1, 1, "A inflação não caiu.", None)
        self.assertFalse(self.store.finish_analysis(job_id, validate_items([item()], source["text"]), {}))
        self.assertEqual(self.store.claims(), [])

    def test_concurrent_edit_and_analysis_cannot_leave_old_claim_active(self):
        job_id, source = self.store.begin_analysis(1)
        inside, release, edited = threading.Event(), threading.Event(), threading.Event()
        errors = []
        original = self.store._invalidate

        def pause(db, pid):
            if threading.current_thread().name == "analysis-result":
                inside.set()
                if not release.wait(3):
                    raise TimeoutError("Teste excedeu o limite.")
            original(db, pid)

        def finish():
            try:
                self.store.finish_analysis(job_id, validate_items([item()], source["text"]), {})
            except Exception as exc:
                errors.append(exc)

        def edit():
            try:
                self.store.revise(1, 1, "A inflação não caiu.", None)
                edited.set()
            except Exception as exc:
                errors.append(exc)

        with patch.object(self.store, "_invalidate", side_effect=pause):
            finisher = threading.Thread(target=finish, name="analysis-result")
            editor = threading.Thread(target=edit)
            finisher.start()
            try:
                self.assertTrue(inside.wait(2))
                editor.start()
                self.assertFalse(edited.wait(0.05))
            finally:
                release.set()
                finisher.join(3)
                if editor.ident:
                    editor.join(3)
        self.assertEqual(errors, [])
        self.assertTrue(edited.is_set())
        self.assertEqual(self.store.claims()[0]["status"], "analise_desatualizada")

    def test_new_original_does_not_overwrite_human_edit_and_requires_reconciliation(self):
        self.store.revise(1, 1, "A inflação não caiu.", "Ana")
        source = self.store.ingest(paragraph("A inflação caiu para 3,5% em 2025, segundo o instituto.", version=2))
        self.assertEqual(source["text"], "A inflação não caiu.")
        self.assertTrue(source["needs_rebase"])
        with self.assertRaises(ValueError):
            self.store.begin_analysis(1)
        source = self.store.revise(1, source["revision"], source["original"]["source_text"], "Ana", use_original=True)
        self.assertFalse(source["needs_rebase"])

    def test_closure_without_text_change_does_not_invalidate_analysis(self):
        self.complete()
        self.store.ingest(paragraph(version=2))
        self.assertEqual(self.store.source(1)["revision"], 1)
        self.assertEqual(self.store.claims()[0]["status"], "aguardando_pesquisa")
        self.assertIsNone(self.store.begin_analysis(1))

    def test_duplicate_jobs_and_stale_editor_writes_are_rejected(self):
        self.store.begin_analysis(1)
        self.assertIsNone(self.store.begin_analysis(1))
        self.store.revise(1, 1, "Outro texto.", None)
        with self.assertRaises(ValueError):
            self.store.revise(1, 1, "Alteração atrasada.", None)
        self.assertEqual(self.store.source(1)["text"], "Outro texto.")

    def test_speaker_must_be_registered_and_missing_speaker_remains_unknown(self):
        with self.assertRaises(ValueError):
            self.store.revise(1, 1, "Outro texto.", "Inventado")
        self.assertIsNone(self.complete()[0]["speaker"])

    def test_discards_keep_history_and_require_reason(self):
        claim = self.complete()[0]
        with self.assertRaises(ValueError):
            self.store.discard_claim(claim["id"], "")
        self.store.discard_claim(claim["id"], "Afirmação já analisada em outro item.")
        self.assertEqual(len(self.store.claims()), 1)
        self.assertEqual(self.store.claims()[0]["status"], "descartada")
        self.store.revise(1, 1, "Texto corrigido.", None)
        self.assertEqual(self.store.claims()[0]["status"], "descartada")
        self.assertTrue(self.store.claims()[0]["source_outdated"])

    def test_event_context_change_invalidates_claim_and_preserves_assigned_participant(self):
        self.store.revise(1, 1, paragraph()["source_text"], "Ana")
        self.complete()
        self.store.save_debate(Debate(title="Novo título", participants=["Ana", "Bruno"]))
        self.assertEqual(self.store.claims()[0]["status"], "analise_desatualizada")
        with self.assertRaises(ValueError):
            self.store.save_debate(Debate(participants=["Bruno"]))

    def test_failed_or_interrupted_jobs_can_be_retried(self):
        job, _ = self.store.begin_analysis(1)
        with patch("factcheck.review.process_alive", return_value=False):
            self.store.recover_interrupted()
        self.assertEqual(self.store.analysis_states()[(1, 1)]["status"], "interrupted")
        next_job, _ = self.store.begin_analysis(1)
        self.assertNotEqual(next_job, job)
        self.store.fail_analysis(next_job, "Cancelado", cancelled=True)
        self.assertEqual(self.store.analysis_states()[(1, 1)]["status"], "cancelled")

    def test_opening_session_does_not_interrupt_a_live_job(self):
        self.store.begin_analysis(1)
        with patch("factcheck.review.process_alive", return_value=True):
            self.store.recover_interrupted()
        self.assertEqual(self.store.analysis_states()[(1, 1)]["status"], "running")

    def test_old_session_without_debate_can_be_opened(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder / "session.json").write_text('{}', encoding="utf8")
            (folder / "paragraphs.jsonl").write_text(json.dumps(paragraph()), encoding="utf8")
            store = ReviewStore(folder)
            store.import_paragraphs()
            self.assertEqual(len(store.sources()), 1)
            self.assertEqual(store.debate()["participants"], [])

    def test_invalid_registration_is_rejected(self):
        for debate in [Debate(title=""), Debate(event_date="2026-99-01"), Debate(source_url="file:///private"), Debate(participants=["Ana", "ana"])]:
            with self.subTest(debate=debate), self.assertRaises(ValueError):
                debate.validate()


class TriageValidationTests(unittest.TestCase):
    def test_nonliteral_quote_is_rejected(self):
        with self.assertRaises(ValueError):
            validate_items([item("A inflação subiu.")], paragraph()["source_text"])

    def test_word_or_numeric_prefix_is_not_accepted_as_a_complete_quote(self):
        for quote, text in [("A taxa foi 3", "A taxa foi 30 por cento"),
                            ("A taxa foi 3", "A taxa foi 3,5%"),
                            ("O benefício foi ampli", "O benefício foi ampliado")]:
            with self.subTest(quote=quote), self.assertRaises(ValueError):
                validate_items([item(quote)], text)

    def test_terminal_punctuation_is_restored_to_unpunctuated_source_and_negation_preserved(self):
        text = "a inflação não caiu de oito para seis por cento"
        result = validate_items([item("Caiu de oito para seis por cento.", summary="Caiu de oito para seis por cento.")], text)[0]
        self.assertEqual(result["quote"], "não caiu de oito para seis por cento")
        self.assertEqual(result["summary"], result["quote"])
        self.assertEqual(text[result["quote_start"]:result["quote_end"]], result["quote"])

    def test_fields_from_another_sentence_are_removed_and_reported(self):
        text = "A inflação caiu. Aqui, no ano passado, a renda aumentou."
        result = validate_items([item("A inflação caiu.", period="ano passado", location="Brasil")], text)[0]
        self.assertIsNone(result["period"])
        self.assertIsNone(result["location"])
        self.assertEqual(len(result["validation_notes"]), 2)

    def test_unfounded_summary_number_or_missing_negation_falls_back_to_quote(self):
        for quote, summary in [("A inflação não caiu.", "A inflação caiu."),
                               ("Criamos vinte mil empregos.", "Criamos 200 mil empregos.")]:
            with self.subTest(quote=quote):
                result = validate_items([item(quote, summary=summary)], quote)[0]
                self.assertEqual(result["summary"], quote)
                self.assertTrue(result["validation_notes"])

    def test_relative_context_is_preserved_without_resolving_it(self):
        quote = "Aqui, no ano passado, a renda aumentou."
        result = validate_items([item(quote, location="Aqui", period="ano passado")], quote)[0]
        self.assertEqual(result["period"], "ano passado")
        self.assertEqual(result["context_notes"], ["aqui", "ano passado"])

    def test_output_limits_and_categories_are_validated(self):
        for items in [[item(category="confirmada")], [item()] * 13, [{"quote": "texto"}]]:
            with self.subTest(items=items), self.assertRaises(ValueError):
                validate_items(items, paragraph()["source_text"])

    def test_promise_and_opinion_are_outside_research_queue(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder / "session.json").write_text('{}', encoding="utf8")
            store = ReviewStore(folder)
            text = "Vou construir hospitais. Acho esse governo excelente."
            store.ingest(paragraph(text))
            job, _ = store.begin_analysis(1)
            items = validate_items([item("Vou construir hospitais.", "promessa"), item("Acho esse governo excelente.", "opiniao")], text)
            store.finish_analysis(job, items, {})
            self.assertTrue(all(claim["status"] == "fora_da_fila" for claim in store.claims()))


if __name__ == "__main__":
    unittest.main()
