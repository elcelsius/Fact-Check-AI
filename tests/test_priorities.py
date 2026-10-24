from dataclasses import asdict
import json
from pathlib import Path
import tempfile
import unittest

from factcheck.discovery import parse_results
from factcheck.dossiers import DossierStore, render
from factcheck.exports import csv_rows, snapshot
from factcheck.priorities import PriorityStore, priority_label, priority_payload
from factcheck.review import Debate, ReviewStore
from factcheck.reporting import session_report, render_report


TEXT = "A inflação ficou em 3% em 2025."


class PriorityTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.folder = Path(self.directory.name)
        (self.folder / "session.json").write_text(json.dumps({"status": "completed", "debate": asdict(Debate())}), encoding="utf8")
        self.review = ReviewStore(self.folder)
        self.review.ingest({"paragraph_id": 1, "version": 1, "text": TEXT, "source_text": TEXT,
                            "start": 0, "end": 3, "closed": True, "parts": []})
        self.item = {"quote": TEXT, "summary": TEXT, "category": "fato", "topic": "Economia", "reason": "Indicador a conferir.",
                     "period": "2025", "location": None, "indicator": "3%", "comparison": None}
        jid, _ = self.review.begin_analysis(1)
        self.review.finish_analysis(jid, [self.item], {})
        self.cid = self.review.claims()[0]["id"]
        self.priorities = PriorityStore(self.review)
        self.dossiers = DossierStore(self.review)

    def tearDown(self):
        self.directory.cleanup()

    def save(self, level="high", reason="Dado relevante para a pauta, com fonte disponível.", expected=0, claim_revision=1):
        return self.priorities.save(self.cid, expected, claim_revision, 1, level, reason)

    def revise_extraction(self):
        fields = {key: self.item[key] for key in ("quote", "summary", "category", "topic")}
        fields["topic"] = "Indicadores"
        self.review.revise_claim(self.cid, 1, 1, fields, "Tema corrigido.")

    def test_unassigned_default_is_stable_and_does_not_create_a_priority(self):
        first = snapshot(self.review)
        second = snapshot(self.review)
        self.assertEqual(first["content_sha256"], second["content_sha256"])
        priority = first["claims"][0]["priority"]
        self.assertEqual(priority["level"], "unset")
        self.assertEqual(priority["revision"], 0)
        self.assertFalse(priority["current"])
        self.assertEqual(self.priorities.all(), {})

    def test_priority_does_not_change_factual_revisions_decision_or_running_research(self):
        self.dossiers.decide(self.cid, 0, "inconclusiva", "Revisor fictício", "Faltam documentos.")
        jid = self.dossiers.begin(self.cid, "discover", "IPCA 2025")
        before = self.dossiers.snapshot(self.cid)
        source = self.review.source(1)
        claim = self.review.claims()[0]
        self.save()
        after = self.dossiers.snapshot(self.cid)
        self.assertEqual(after["revision"], before["revision"])
        self.assertEqual(after["decision"], before["decision"])
        self.assertEqual(after["jobs"], before["jobs"])
        self.assertEqual(self.review.source(1), source)
        self.assertEqual(self.review.claims()[0], claim)
        self.assertTrue(self.dossiers.finish(jid, *parse_results({"results": []}, "IPCA 2025")))
        self.assertEqual(after["priority"]["level"], "high")
        self.assertIn("Prioridade de revisão: Alta", render(after))

    def test_reopening_preserves_priority_and_previous_values_in_audit(self):
        self.save()
        self.save("low", "Pouca urgência nesta pauta.", expected=1)
        current = PriorityStore(ReviewStore(self.folder)).all()[self.cid]
        self.assertEqual(current["revision"], 2)
        self.assertEqual(current["level"], "low")
        with self.review.connection() as db:
            history = [json.loads(row[0]) for row in db.execute("SELECT payload FROM history WHERE kind='claim_priority_changed' ORDER BY id")]
        self.assertEqual(history[1]["previous"]["level"], "high")
        self.assertEqual(history[1]["current"]["level"], "low")

    def test_removing_priority_requires_reason_and_preserves_the_old_level(self):
        self.save()
        with self.assertRaises(ValueError):
            self.save("unset", " ", expected=1)
        current = self.save("unset", "A pauta foi reorganizada.", expected=1)
        self.assertEqual(current["revision"], 2)
        self.assertEqual(current["level"], "unset")
        self.assertEqual(priority_label(current), "Não definida")

    def test_identical_save_does_not_add_history_but_new_reason_does(self):
        first = self.save()
        self.assertEqual(self.save(expected=1), first)
        self.assertEqual(self.save(reason="Outra justificativa editorial.", expected=1)["revision"], 2)
        with self.review.connection() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM history WHERE kind='claim_priority_changed'").fetchone()[0], 2)

    def test_invalid_inputs_and_missing_claim_are_rejected_without_writes(self):
        for level, reason in (("urgent", "Motivo."), ([], "Motivo."), ("high", ""), ("high", "x" * 2001)):
            with self.subTest(level=level), self.assertRaises(ValueError):
                self.save(level, reason)
        for values in ((True, 1, 1), (0, False, 1), (-1, 1, 1), (0, 1, "1")):
            with self.subTest(revisions=values), self.assertRaises(ValueError):
                self.priorities.save(self.cid, *values, "high", "Motivo.")
        with self.assertRaisesRegex(ValueError, "não encontrada"):
            self.priorities.save("missing", 0, 1, 1, "high", "Motivo.")
        self.assertEqual(self.priorities.all(), {})

    def test_stale_priority_editor_cannot_overwrite_a_newer_assignment(self):
        self.save()
        with self.assertRaisesRegex(ValueError, "prioridade mudou"):
            self.save("low", "Editor antigo.")
        self.assertEqual(self.priorities.all()[self.cid]["level"], "high")

    def test_extraction_change_requires_priority_review_and_explicit_reconfirmation(self):
        self.save()
        self.revise_extraction()
        pending = self.dossiers.snapshot(self.cid)["priority"]
        self.assertTrue(pending["needs_review"])
        self.assertFalse(pending["current"])
        self.assertEqual(priority_label(pending), "A conferir · Alta")
        with self.assertRaisesRegex(ValueError, "afirmação ou a fala mudou"):
            self.save(expected=1)
        saved = self.save(expected=1, claim_revision=2)
        self.assertEqual(saved["revision"], 2)
        self.assertTrue(saved["current"])
        self.assertFalse(saved["needs_review"])

    def test_changed_transcript_and_discarded_claim_cannot_be_prioritized(self):
        self.save()
        self.review.revise(1, 1, TEXT + " Correção.", None)
        with self.assertRaises(ValueError):
            self.save(expected=1)
        old = self.dossiers.snapshot(self.cid)["priority"]
        self.assertFalse(old["current"])
        self.assertEqual(priority_label(old), "Alta · histórica")

    def test_discard_does_not_delete_historical_priority(self):
        self.save()
        self.review.discard_claim(self.cid, "Extração duplicada.")
        with self.assertRaises(ValueError):
            self.save(expected=1)
        self.assertEqual(self.priorities.all()[self.cid]["level"], "high")
        self.assertFalse(self.dossiers.snapshot(self.cid)["priority"]["current"])

    def test_new_triage_does_not_transfer_the_priority_to_a_new_claim(self):
        self.save()
        job, _ = self.review.begin_analysis(1, force=True)
        self.assertTrue(self.review.finish_analysis(job, [self.item], {}))
        current = next(claim for claim in self.review.claims() if claim["id"] != self.cid)
        self.assertEqual(self.dossiers.snapshot(current["id"])["priority"]["level"], "unset")
        self.assertFalse(self.dossiers.snapshot(self.cid)["priority"]["current"])
        self.assertEqual(self.priorities.all()[self.cid]["level"], "high")

    def test_plan_changes_and_discovery_do_not_change_manual_priority(self):
        saved = self.save()
        jid = self.dossiers.begin(self.cid, "discover", "IPCA 2025")
        self.dossiers.finish(jid, *parse_results({"results": [{"url": "https://ibge.gov.br/teste"}]}, "IPCA 2025"))
        self.assertTrue(self.dossiers.snapshot(self.cid)["discoveries"][0]["current"])
        self.save("normal", "Conferência sem urgência imediata.", expected=1)
        self.assertTrue(self.dossiers.snapshot(self.cid)["discoveries"][0]["current"])
        self.dossiers.save_plan(self.cid, 0, {"question": "Qual o IPCA em 2025?", "scope": "pesquisavel", "period": "2025",
            "territory": "Brasil", "indicator": "IPCA", "comparison": "", "notes": "", "candidate_urls": []})
        self.assertTrue(self.dossiers.snapshot(self.cid)["priority"]["current"])
        self.assertEqual(self.dossiers.snapshot(self.cid)["priority"]["level"], "normal")

    def test_json_csv_hashes_and_ids_distinguish_priority_from_the_factual_revision(self):
        before = snapshot(self.review)
        self.save(reason="=Motivo com proteção de planilha")
        after = snapshot(self.review)
        self.assertEqual(after["claims"][0]["record_id"], before["claims"][0]["record_id"])
        self.assertNotEqual(after["claims"][0]["record_sha256"], before["claims"][0]["record_sha256"])
        self.assertEqual(after["claims"][0]["claim_revision"], before["claims"][0]["claim_revision"])
        self.assertEqual(after["dossiers"][0]["revision"], before["dossiers"][0]["revision"])
        csv = next(csv_rows(after, "claims"))
        self.assertEqual(csv["prioridade"], "high")
        self.assertEqual(csv["prioridade_atual"], "sim")
        self.assertTrue(csv["prioridade_justificativa"].startswith("\t="))
        self.assertIsNone(after["dossiers"][0]["decision"])

    def test_legacy_database_without_priority_table_can_be_exported_and_read(self):
        with self.review.connection() as db:
            db.execute("DROP TABLE claim_priorities")
        self.assertEqual(snapshot(self.review)["claims"][0]["priority"]["revision"], 0)
        self.assertEqual(self.dossiers.snapshot(self.cid)["priority"]["level"], "unset")
        PriorityStore(self.review)
        self.assertEqual(self.priorities.all(), {})

    def test_metadata_projection_does_not_export_unknown_fields(self):
        claim = self.review.claims()[0]
        data = priority_payload(claim, {"secret": "MARCADOR-NAO-EXPORTAR"})
        self.assertNotIn("secret", data)

    def test_report_counts_pending_priority_review_without_changing_factual_denominators(self):
        self.save()
        self.assertEqual(session_report(self.review)["claims"]["priorities"]["high"], 1)
        self.revise_extraction()
        report = session_report(self.review)
        self.assertEqual(report["claims"]["priorities"]["high"], 0)
        self.assertEqual(report["claims"]["priorities"]["needs_review"], 1)
        self.assertEqual(report["claims"]["detected_factual"], 1)
        self.assertIsNone(report["quality"]["precision"])
        self.assertIn("A conferir: 1", render_report(report))

    def test_prioritizing_an_opinion_does_not_promote_it_to_fact_or_review_the_source(self):
        fields = {key: self.item[key] for key in ("quote", "summary", "category", "topic")}
        fields["category"] = "opiniao"
        self.review.revise_claim(self.cid, 1, 1, fields, "Reclassificação fictícia para testar separação de estados.")
        self.save(claim_revision=2)
        self.assertEqual(self.review.claims()[0]["category"], "opiniao")
        self.assertFalse(self.review.source(1)["human_reviewed"])
        self.assertEqual(session_report(self.review)["claims"]["detected_factual"], 0)


if __name__ == "__main__":
    unittest.main()
