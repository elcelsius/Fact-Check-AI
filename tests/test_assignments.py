from dataclasses import asdict
import json
from pathlib import Path
import tempfile
import unittest

from factcheck.assignments import AssignmentStore, assignment_label, assignment_payload
from factcheck.discovery import parse_results
from factcheck.dossiers import DossierStore, render
from factcheck.exports import csv_rows, snapshot
from factcheck.priorities import PriorityStore
from factcheck.reporting import session_report, render_report
from factcheck.review import Debate, ReviewStore


TEXT = "A inflação ficou em 3% em 2025."


class AssignmentTests(unittest.TestCase):
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
        self.assignments = AssignmentStore(self.review)
        self.dossiers = DossierStore(self.review)

    def tearDown(self):
        self.directory.cleanup()

    def save(self, name="Ana", reason="Acompanhar as fontes deste indicador.", expected=0, claim_revision=1):
        return self.assignments.save(self.cid, expected, claim_revision, 1, name, reason)

    def revise_extraction(self, category="fato"):
        fields = {key: self.item[key] for key in ("quote", "summary", "category", "topic")}
        fields.update(topic="Indicadores", category=category)
        self.review.revise_claim(self.cid, 1, 1, fields, "Extração corrigida no ensaio.")

    def test_unassigned_legacy_defaults_are_stable_without_inventing_dates(self):
        first, second = snapshot(self.review), snapshot(self.review)
        self.assertEqual(first["content_sha256"], second["content_sha256"])
        assignment = first["claims"][0]["assignment"]
        self.assertEqual(assignment["name"], "")
        self.assertEqual(assignment["revision"], 0)
        self.assertIsNone(assignment["updated_at"])
        self.assertFalse(assignment["current"])
        self.assertEqual(self.assignments.all(), {})

    def test_assignment_is_independent_from_decision_reviewer_claim_and_research(self):
        self.dossiers.decide(self.cid, 0, "inconclusiva", "Bruna · revisora fictícia", "Faltam documentos.")
        jid = self.dossiers.begin(self.cid, "discover", "IPCA 2025")
        before, source, claim = self.dossiers.snapshot(self.cid), self.review.source(1), self.review.claims()[0]
        self.save()
        after = self.dossiers.snapshot(self.cid)
        self.assertEqual(after["decision"], before["decision"])
        self.assertEqual(after["decision"]["reviewer"], "Bruna · revisora fictícia")
        self.assertEqual(after["assignment"]["name"], "Ana")
        self.assertEqual(after["revision"], before["revision"])
        self.assertEqual(after["jobs"], before["jobs"])
        self.assertEqual(self.review.source(1), source)
        self.assertEqual(self.review.claims()[0], claim)
        self.assertTrue(self.dossiers.finish(jid, *parse_results({"results": []}, "IPCA 2025")))
        self.assertIn("Responsável pelo caso: Ana", render(after))
        self.assertIn("Bruna · revisora fictícia", render(after))

    def test_assign_reassign_and_release_preserve_previous_names_and_reasons(self):
        self.save("  Ana   Silva  ")
        self.save("Bruna", "Redistribuição da pauta.", expected=1)
        self.save("", "Caso disponível para redistribuição.", expected=2)
        current = AssignmentStore(ReviewStore(self.folder)).all()[self.cid]
        self.assertEqual(current["name"], "")
        self.assertEqual(current["revision"], 3)
        with self.review.connection() as db:
            history = [json.loads(row[0]) for row in db.execute("SELECT payload FROM history WHERE kind='claim_assignment_changed' ORDER BY id")]
        self.assertEqual(history[0]["current"]["name"], "Ana Silva")
        self.assertEqual(history[1]["previous"]["name"], "Ana Silva")
        self.assertEqual(history[2]["previous"]["name"], "Bruna")
        self.assertEqual(history[2]["current"]["reason"], "Caso disponível para redistribuição.")

    def test_release_requires_reason_and_does_not_erase_prior_assignment(self):
        self.save()
        with self.assertRaises(ValueError):
            self.save("", " ", expected=1)
        self.assertEqual(self.assignments.all()[self.cid]["name"], "Ana")
        cleared = self.save("", "Redistribuição pendente.", expected=1)
        self.assertEqual(assignment_label(cleared), "Sem responsável")

    def test_identical_save_is_noop_but_a_new_reason_creates_a_revision(self):
        first = self.save()
        self.assertEqual(self.save(expected=1), first)
        self.assertEqual(self.save(reason="Assumir também a conferência metodológica.", expected=1)["revision"], 2)
        with self.review.connection() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM history WHERE kind='claim_assignment_changed'").fetchone()[0], 2)

    def test_invalid_names_reasons_revisions_and_missing_claim_are_rejected(self):
        for name in (None, [], "x" * 101, "Ana\nBruna", "Ana\tSilva", "Ana\x7f"):
            with self.subTest(name_type=type(name).__name__), self.assertRaises(ValueError):
                self.save(name)
        for reason in ("", " ", "x" * 2001, None):
            with self.subTest(reason_type=type(reason).__name__), self.assertRaises(ValueError):
                self.save(reason=reason)
        for revisions in ((True, 1, 1), (-1, 1, 1), (0, False, 1), (0, 1, "1")):
            with self.subTest(revisions=revisions), self.assertRaises(ValueError):
                self.assignments.save(self.cid, *revisions, "Ana", "Motivo.")
        with self.assertRaisesRegex(ValueError, "não encontrada"):
            self.assignments.save("missing", 0, 1, 1, "Ana", "Motivo.")
        self.assertEqual(self.assignments.all(), {})

    def test_stale_editor_cannot_replace_a_newer_assignment(self):
        other = AssignmentStore(self.review)
        self.save()
        with self.assertRaisesRegex(ValueError, "atribuição mudou"):
            other.save(self.cid, 0, 1, 1, "Bruna", "Editor antigo.")
        self.assertEqual(self.assignments.all()[self.cid]["name"], "Ana")

    def test_extraction_change_requires_reconfirmation_and_rejects_old_editor(self):
        self.save()
        self.revise_extraction()
        pending = self.dossiers.snapshot(self.cid)["assignment"]
        self.assertTrue(pending["needs_review"])
        self.assertFalse(pending["current"])
        self.assertEqual(assignment_label(pending), "Ana · a conferir")
        with self.assertRaisesRegex(ValueError, "afirmação ou a fala mudou"):
            self.save(expected=1)
        confirmed = self.save(expected=1, claim_revision=2)
        self.assertTrue(confirmed["current"])
        self.assertFalse(confirmed["needs_review"])
        self.assertEqual(confirmed["revision"], 2)

    def test_source_revision_keeps_only_historical_assignment(self):
        self.save()
        self.review.revise(1, 1, TEXT + " Correção.", None)
        with self.assertRaises(ValueError):
            self.save(expected=1)
        historical = self.dossiers.snapshot(self.cid)["assignment"]
        self.assertFalse(historical["current"])
        self.assertEqual(assignment_label(historical), "Ana · histórico")

    def test_discarded_claim_keeps_the_assignment_history_but_cannot_be_reassigned(self):
        self.save()
        self.review.discard_claim(self.cid, "Extração duplicada.")
        with self.assertRaises(ValueError):
            self.save("Bruna", expected=1)
        self.assertEqual(self.assignments.all()[self.cid]["name"], "Ana")
        self.assertFalse(self.dossiers.snapshot(self.cid)["assignment"]["current"])

    def test_new_triage_does_not_transfer_ownership(self):
        self.save()
        jid, _ = self.review.begin_analysis(1, force=True)
        self.review.finish_analysis(jid, [self.item], {})
        current = next(claim for claim in self.review.claims() if claim["id"] != self.cid)
        self.assertEqual(self.dossiers.snapshot(current["id"])["assignment"]["name"], "")
        self.assertFalse(self.dossiers.snapshot(self.cid)["assignment"]["current"])

    def test_priority_plan_and_discovery_remain_independent(self):
        self.save()
        priorities = PriorityStore(self.review)
        priorities.save(self.cid, 0, 1, 1, "high", "Prioridade central na pauta.")
        jid = self.dossiers.begin(self.cid, "discover", "IPCA 2025")
        self.dossiers.finish(jid, *parse_results({"results": [{"url": "https://ibge.gov.br/teste"}]}, "IPCA 2025"))
        self.save("Bruna", "Distribuir o acompanhamento.", expected=1)
        state = self.dossiers.snapshot(self.cid)
        self.assertTrue(state["priority"]["current"])
        self.assertTrue(state["discoveries"][0]["current"])
        self.dossiers.save_plan(self.cid, 0, {"question": "Qual o IPCA em 2025?", "scope": "pesquisavel", "period": "2025",
            "territory": "Brasil", "indicator": "IPCA", "comparison": "", "notes": "", "candidate_urls": []})
        self.assertTrue(self.dossiers.snapshot(self.cid)["assignment"]["current"])

    def test_json_csv_and_record_hashes_separate_case_owner_from_factual_reviewer(self):
        self.dossiers.decide(self.cid, 0, "inconclusiva", "Bruna", "Faltam fontes.")
        before = snapshot(self.review)
        self.save("=Ana", "=Motivo para testar proteção de planilha")
        after = snapshot(self.review)
        self.assertEqual(before["claims"][0]["record_id"], after["claims"][0]["record_id"])
        self.assertNotEqual(before["claims"][0]["record_sha256"], after["claims"][0]["record_sha256"])
        self.assertEqual(after["claims"][0]["assignment"]["name"], "=Ana")
        self.assertEqual(after["dossiers"][0]["decision"], before["dossiers"][0]["decision"])
        self.assertEqual(after["dossiers"][0]["revision"], before["dossiers"][0]["revision"])
        csv = next(csv_rows(after, "claims"))
        self.assertEqual(csv["responsavel_caso"], "\t=Ana")
        self.assertEqual(csv["atribuicao_atual"], "sim")
        self.assertTrue(csv["atribuicao_justificativa"].startswith("\t="))
        self.assertEqual(csv["decisao_humana_responsavel"], "Bruna")

    def test_report_separates_current_pending_and_unassigned_without_changing_quality(self):
        self.save()
        self.assertEqual(session_report(self.review)["claims"]["assignments"]["assigned_current"], 1)
        self.revise_extraction()
        report = session_report(self.review)
        summary = report["claims"]["assignments"]
        self.assertEqual(summary["assigned_current"], 0)
        self.assertEqual(summary["needs_review"], 1)
        self.assertEqual(summary["by_name"], [{"name": "Ana", "current_cases": 0, "needs_review_cases": 1}])
        self.assertEqual(report["claims"]["detected_factual"], 1)
        self.assertIsNone(report["quality"]["precision"])
        self.assertIn("Ana: 0 atuais, 1 a conferir", render_report(report))
        self.save("", "Liberado para distribuição.", expected=1, claim_revision=2)
        self.assertEqual(session_report(self.review)["claims"]["assignments"]["unassigned"], 1)

    def test_legacy_database_without_assignment_table_can_be_read_and_exported(self):
        with self.review.connection() as db:
            db.execute("DROP TABLE claim_assignments")
        self.assertEqual(snapshot(self.review)["claims"][0]["assignment"]["revision"], 0)
        self.assertEqual(self.dossiers.snapshot(self.cid)["assignment"]["name"], "")
        AssignmentStore(self.review)
        self.assertEqual(self.assignments.all(), {})

    def test_assignment_does_not_promote_opinion_or_identify_the_speaker(self):
        self.revise_extraction("opiniao")
        self.save(claim_revision=2)
        self.assertEqual(self.review.claims()[0]["category"], "opiniao")
        self.assertIsNone(self.review.source(1)["speaker"])
        self.assertFalse(self.review.source(1)["human_reviewed"])
        self.assertEqual(session_report(self.review)["claims"]["detected_factual"], 0)

    def test_metadata_projection_does_not_export_unknown_fields(self):
        value = assignment_payload(self.review.claims()[0], {"secret": "MARCADOR-NAO-EXPORTAR"})
        self.assertNotIn("secret", value)

    def test_full_assignment_history_is_readable_in_dossier_and_exported_with_reasons(self):
        self.save()
        self.save("Bruna", "Redistribuição da pauta.", expected=1)
        self.save("", "Caso disponível.", expected=2)
        dossier = self.dossiers.snapshot(self.cid)
        history = dossier["assignment_history"]
        self.assertEqual(len(history), 3)
        self.assertEqual(history[1]["previous"]["name"], "Ana")
        self.assertEqual(history[1]["current"]["name"], "Bruna")
        self.assertEqual(history[2]["current"]["reason"], "Caso disponível.")
        self.assertIn("Ana → Bruna", render(dossier))
        self.assertEqual(snapshot(self.review)["dossiers"][0]["assignment_history"], history)


if __name__ == "__main__":
    unittest.main()
