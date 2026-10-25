import json
import unittest

from factcheck.exports import snapshot, csv_rows
from factcheck.dossiers import render
from tests import test_evidence as fixtures


class ManualClaimTests(unittest.TestCase):
    setUp = fixtures.DossierTests.setUp
    tearDown = fixtures.DossierTests.tearDown

    def fields(self, quote="A inflação foi de 3,5%", **changes):
        return {"quote": quote, "summary": quote, "category": "fato", "topic": None, **changes}

    def create(self, fields=None, **kwargs):
        return self.review.create_claims(1, self.review.source(1)["revision"], fields or [self.fields()], "Recorte manual fictício.", **kwargs)

    def test_manual_entry_has_no_ai_attempt_or_factual_approval_and_keeps_other_claim(self):
        before = self.review.claims()
        item = self.create()[0]
        self.assertIsNone(item["analysis_id"])
        self.assertEqual(item["creation"]["origin"], "operator_input")
        self.assertEqual(len(self.review.claims()), len(before)+1)
        self.assertIsNone(self.store.snapshot(item["id"])["decision"])
        self.assertFalse(self.review.source(1)["human_reviewed"])
        exported = snapshot(self.review)
        manual = next(row for row in csv_rows(exported, "claims") if row["afirmacao_id"] == item["id"])
        self.assertEqual(manual["origem_extracao"], "operator_input")
        self.assertEqual(manual["categoria_automatica"], "")
        self.assertIn("inclusão manual", render(self.store.snapshot(item["id"])))

    def test_split_is_atomic_preserves_old_decision_as_history_and_does_not_copy_it(self):
        self.store.decide(self.cid, 0, "inconclusiva", "Revisor fictício", "Faltam fontes.")
        children = self.create([self.fields(), self.fields("no Brasil em 2025")], replaced={"id": self.cid, "revision": 1})
        old = self.store.snapshot(self.cid)
        self.assertFalse(old["valid"])
        self.assertEqual(old["decision"]["verdict"], "inconclusiva")
        self.assertEqual(old["claim"]["replaced_by"], [child["id"] for child in children])
        for item in children:
            self.assertEqual(item["creation"]["parent_claim_id"], self.cid)
            self.assertIsNone(self.store.snapshot(item["id"])["decision"])
            self.assertEqual(self.store.snapshot(item["id"])["documents"], [])

    def test_invalid_second_part_rolls_back_first_part_and_keeps_original_current(self):
        before = self.review.claims()
        with self.assertRaises(ValueError):
            self.create([self.fields(), self.fields("Declaração inventada")], replaced={"id": self.cid, "revision": 1})
        self.assertEqual(before, self.review.claims())
        self.assertTrue(self.store.snapshot(self.cid)["valid"])

    def test_duplicates_stale_source_and_stale_parent_are_rejected(self):
        with self.assertRaises(ValueError):
            self.create([self.fields(), self.fields()], replaced={"id": self.cid, "revision": 1})
        with self.assertRaises(ValueError):
            self.create([self.fields(), self.fields("no Brasil em 2025")], replaced={"id": self.cid, "revision": 999})
        self.create()
        with self.assertRaises(ValueError):
            self.create()
        with self.assertRaises(ValueError):
            self.review.create_claims(1, 999, [self.fields()], "Revisão antiga")

    def test_manual_entry_blocks_pending_ai_and_automatic_reanalysis_but_explicit_reanalysis_is_allowed(self):
        job, source = self.review.begin_analysis(1, force=True)
        self.create()
        self.assertFalse(self.review.finish_analysis(job, [], {}))
        self.assertIsNone(self.review.begin_analysis(1))
        self.assertIsNotNone(self.review.begin_analysis(1, force=True))

    def test_revising_manual_entry_does_not_invent_an_automatic_original(self):
        item = self.create()[0]
        revised = self.review.revise_claim(item["id"], 1, 1, self.fields(category="opiniao"), "Reclassificação manual.")
        self.assertIsNone(revised["automatic_extraction"])
        self.assertEqual(revised["creation"], item["creation"])


if __name__ == "__main__":
    unittest.main()
