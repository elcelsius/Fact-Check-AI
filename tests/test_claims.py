import json
import unittest
from unittest.mock import patch

from factcheck.exports import csv_rows, snapshot
from factcheck.planning import PLAN_FIELDS
from factcheck.reporting import session_report
from factcheck.research import analyze
from factcheck.triage import TriageConfig, validate_items
from tests import test_evidence as fixtures
from tests.test_planning import plan


class ClaimRevisionTests(unittest.TestCase):
    setUp = fixtures.DossierTests.setUp
    tearDown = fixtures.DossierTests.tearDown
    add = fixtures.DossierTests.add

    def current(self):
        return next(row for row in self.review.claims() if row["id"] == self.cid)

    def fields(self, **changes):
        row = self.current()
        return {key: changes.get(key, row.get(key)) for key in ("quote", "summary", "category", "topic")}

    def edit(self, **changes):
        row = self.current()
        return self.review.revise_claim(self.cid, row.get("claim_revision", 1), row["revision"], self.fields(**changes), "Correção editorial fictícia.")

    def test_reclassifying_keeps_id_source_and_automatic_extraction_without_deciding_truth(self):
        source = self.review.source(1)
        old = self.current()
        updated = self.edit(category="opiniao")
        self.assertEqual(updated["id"], old["id"])
        self.assertEqual(updated["claim_revision"], 2)
        self.assertEqual(updated["category"], "opiniao")
        self.assertEqual(updated["status"], "fora_da_fila")
        self.assertEqual(updated["automatic_extraction"]["category"], "fato")
        self.assertEqual(updated["automatic_extraction"]["quote"], old["quote"])
        self.assertEqual(self.review.source(1), source)
        self.assertIsNone(self.store.snapshot(self.cid)["decision"])
        report = session_report(self.review)
        self.assertEqual(report["claims"]["detected_factual"], 0)
        self.assertEqual(report["claims"]["extraction_revised"], 1)

    def test_literal_narrowing_updates_offsets_removes_old_recuts_and_repeated_save_is_noop(self):
        quote = "A inflação foi de 3,5%"
        updated = self.edit(quote=quote, summary=quote)
        self.assertEqual(updated["quote_start"], 0)
        self.assertEqual(updated["quote_end"], len(quote))
        self.assertIsNone(updated["period"])
        self.assertIsNone(updated["location"])
        self.assertTrue(updated["validation_notes"])
        result = self.edit()
        self.assertEqual(result, updated)
        self.assertEqual(self.store.snapshot(self.cid)["revision"], 1)

    def test_repeated_edits_preserve_first_automatic_value_and_audit_intermediate_revision(self):
        original = self.current()
        self.edit(category="opiniao")
        result = self.edit(category="indefinida")
        self.assertEqual(result["claim_revision"], 3)
        self.assertEqual(result["automatic_extraction"]["category"], original["category"])
        with self.review.connection() as db:
            records = [json.loads(row[0]) for row in db.execute("SELECT payload FROM history WHERE kind='claim_revised' ORDER BY id")]
        self.assertEqual(len(records), 2)
        self.assertEqual(records[1]["previous"]["category"], "opiniao")
        self.assertEqual(records[1]["current"]["category"], "indefinida")

    def test_stale_claim_editor_is_rejected_without_overwriting_newer_edit(self):
        fields = self.fields(category="promessa")
        current = self.edit(category="opiniao")
        with self.assertRaisesRegex(ValueError, "Reabra a revisão"):
            self.review.revise_claim(self.cid, 1, 1, fields, "Editor antigo.")
        self.assertEqual(self.current(), current)

    def test_invalid_quote_summary_and_missing_reason_do_not_change_data(self):
        before = self.current()
        invalid = [(self.fields(quote="Citação inventada."), "Explicação."),
                   (self.fields(summary="A taxa foi de 90%."), "Explicação."),
                   (self.fields(), ""), (self.fields(category=[]), "Explicação."),
                   ({**self.fields(), "decision": "confirmada"}, "Explicação.")]
        for fields, reason in invalid:
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                self.review.revise_claim(self.cid, 1, 1, fields, reason)
        self.assertEqual(self.current(), before)

    def test_discarding_while_editor_is_open_cannot_be_undone_by_saving_editor(self):
        self.review.discard_claim(self.cid, "Descarte fictício.")
        with self.assertRaises(ValueError):
            self.edit(category="opiniao")
        self.assertEqual(self.current()["status"], "descartada")

    def test_source_change_invalidates_the_old_claim_editor(self):
        self.review.revise(1, 1, "Fala corrigida depois da abertura.", None)
        with self.assertRaises(ValueError):
            self.review.revise_claim(self.cid, 1, 1, self.fields(), "Revisão antiga.")
        self.assertTrue(self.current()["source_outdated"])

    def test_inflight_triage_cannot_replace_manually_revised_extraction(self):
        job, source = self.review.begin_analysis(1, force=True)
        revised = self.edit(category="opiniao")
        item = {key: revised["automatic_extraction"].get(key) for key in
                ("quote", "summary", "category", "reason", "topic", "period", "location", "indicator", "comparison")}
        self.assertFalse(self.review.finish_analysis(job, validate_items([item], source["text"]), {}))
        self.assertEqual(self.current(), revised)
        self.assertTrue(self.store.snapshot(self.cid)["valid"])

    def test_inflight_research_without_saved_case_is_rejected_after_claim_revision(self):
        job = self.store.begin(self.cid, "collect")
        self.edit()
        self.assertFalse(self.store.finish(job, fixtures.document()))
        result = self.store.snapshot(self.cid)
        self.assertEqual(result["documents"], [])
        self.assertEqual(result["jobs"][0]["status"], "stale")

    def test_sources_and_decision_history_survive_but_plan_needs_new_review(self):
        self.add()
        self.store.save_plan(self.cid, 1, plan())
        self.store.decide(self.cid, 2, "inconclusiva", "Revisor fictício", "Exemplo.")
        self.edit()
        result = self.store.snapshot(self.cid)
        self.assertEqual(result["revision"], 4)
        self.assertEqual(len(result["documents"]), 1)
        self.assertIsNone(result["decision"])
        self.assertIsNone(result["preliminary"])
        self.assertTrue(result["plan"]["needs_review"])
        self.assertEqual(self.store.states()[self.cid], "Planejamento a conferir")
        self.assertEqual(result["plan"]["claim_revision"], 1)
        with self.assertRaises(ValueError):
            self.store.decide(self.cid, 3, "inconclusiva", "Revisor antigo", "Decisão desatualizada.")
        with self.review.connection() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM history WHERE kind='human_decision'").fetchone()[0], 1)
        fields = {key: result["plan"][key] for key in PLAN_FIELDS}
        self.assertTrue(self.store.save_plan(self.cid, 4, fields))
        result = self.store.snapshot(self.cid)
        self.assertFalse(result["plan"]["needs_review"])
        self.assertEqual(result["plan"]["claim_revision"], 2)
        self.assertFalse(self.review.source(1)["human_reviewed"])

    def test_new_triage_explicitly_started_after_edit_keeps_manual_version_as_history(self):
        revised = self.edit(category="opiniao")
        job, source = self.review.begin_analysis(1, force=True)
        fields = {key: revised["automatic_extraction"].get(key) for key in
                  ("quote", "summary", "category", "reason", "topic", "period", "location", "indicator", "comparison")}
        self.assertTrue(self.review.finish_analysis(job, validate_items([fields], source["text"]), {}))
        previous = self.current()
        self.assertTrue(previous["source_outdated"])
        self.assertEqual(previous["claim_revision"], 2)
        current = [row for row in snapshot(self.review)["claims"] if row["source_current"]]
        self.assertEqual(len(current), 1)
        self.assertNotEqual(current[0]["claim_id"], self.cid)

    def test_json_and_csv_distinguish_current_category_original_and_factual_decision(self):
        old = self.current()
        self.edit(category="opiniao")
        data = snapshot(self.review)
        row = data["claims"][0]
        self.assertEqual(row["claim_revision"], 2)
        self.assertEqual(row["automatic_extraction"]["quote"], old["quote"])
        self.assertEqual(row["category"], "opiniao")
        self.assertIsNone(data["dossiers"][0]["decision"])
        csv = next(csv_rows(data, "claims"))
        self.assertEqual(csv["afirmacao_revisao"], 2)
        self.assertEqual(csv["categoria_automatica"], "fato")
        self.assertEqual(csv["extracao_revisada"], "sim")
        self.assertEqual(csv["decisao_humana_classificacao"], "")

    def test_old_claim_without_revision_metadata_is_editable_as_revision_one(self):
        old = self.current()
        old.pop("claim_revision", None)
        with self.review.connection() as db:
            db.execute("UPDATE claims SET payload=? WHERE id=?", (json.dumps(old), self.cid))
        self.assertEqual(self.edit()["claim_revision"], 2)

    def test_removing_negation_is_rejected_instead_of_silently_changing_human_input(self):
        text = "A inflação não caiu em 2025."
        self.review.ingest({"paragraph_id": 2, "version": 1, "text": text, "source_text": text, "start": 6, "end": 8, "closed": True})
        job, _ = self.review.begin_analysis(2)
        fields = {"quote": text, "summary": text, "category": "fato", "reason": "Exemplo.",
                  "topic": None, "period": None, "location": None, "indicator": None, "comparison": None}
        self.review.finish_analysis(job, validate_items([fields], text), {})
        self.cid = next(row["id"] for row in self.review.claims() if row["paragraph_id"] == 2)
        with self.assertRaisesRegex(ValueError, "negações"):
            self.edit(quote="caiu em 2025.", summary="caiu em 2025.")
        with self.assertRaisesRegex(ValueError, "negações"):
            self.edit(summary="A inflação caiu em 2025.")
        self.assertEqual(self.current()["quote"], text)

    def test_duplicate_current_quote_is_rejected_without_changing_either_extraction(self):
        large = {key: self.current().get(key) for key in
                 ("quote", "summary", "category", "reason", "topic", "period", "location", "indicator", "comparison")}
        small = {**large, "quote": "inflação foi de 3,5%", "summary": "inflação foi de 3,5%"}
        job, source = self.review.begin_analysis(1, force=True)
        self.review.finish_analysis(job, validate_items([large, small], source["text"]), {})
        current = [row for row in self.review.claims() if not row.get("source_outdated")]
        self.cid = next(row["id"] for row in current if row["quote"] == small["quote"])
        before = self.current()
        with self.assertRaisesRegex(ValueError, "duplicação"):
            self.edit(quote=large["quote"], summary=large["quote"])
        self.assertEqual(self.current(), before)

    def test_changed_extraction_keeps_automatic_analysis_inconclusive_until_plan_is_rechecked(self):
        self.add()
        self.store.save_plan(self.cid, 1, plan(scope="pesquisavel"))
        self.edit()
        with patch("factcheck.research.GeminiModel") as model:
            model.return_value.generate.return_value = fixtures.preliminary()
            model.return_value.engine = {"model": "fixture"}
            result, _ = analyze(self.store.snapshot(self.cid), TriageConfig("gemini", "ficticia"), None)
        self.assertEqual(result["verdict"], "inconclusiva")


if __name__ == "__main__":
    unittest.main()
