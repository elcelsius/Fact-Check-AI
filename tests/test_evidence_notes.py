import json
import unittest

from factcheck.evidence_notes import calculate
from factcheck.exports import snapshot
from factcheck.dossiers import render
from tests import test_evidence as fixtures


class EvidenceNotesTests(unittest.TestCase):
    setUp = fixtures.DossierTests.setUp
    tearDown = fixtures.DossierTests.tearDown
    add = fixtures.DossierTests.add

    def citation(self):
        data = self.store.snapshot(self.cid)
        if not data["documents"]:
            self.add()
            data = self.store.snapshot(self.cid)
        doc = data["documents"][0]
        return self.store.save_note(self.cid, data["revision"], "citation", {"document_id": doc["id"], "block_id": "b1",
            "quote": fixtures.TEXT, "relation": "contextualiza", "explanation": "Citação de documento fictício."})

    def calculation(self, nid):
        data = self.store.snapshot(self.cid)
        return self.store.save_note(self.cid, data["revision"], "calculation", {"formula": "(final - inicial) / inicial * 100",
            "variables": {"inicial": "100", "final": "103"}, "unit": "%", "note_ids": [nid], "explanation": "Exemplo aritmético fictício, sem aprovação factual."})

    def test_decimal_formula_is_reproducible_and_arbitrary_code_is_rejected(self):
        self.assertEqual(calculate("a + b", {"a": "0,1", "b": "0.2"}), "0.3")
        for expression in ("__import__('os')", "a.real", "a ** 1000000", "1 / 0", "float('nan')", "[1,2]", "1e999"):
            with self.subTest(expression=expression), self.assertRaises(ValueError):
                calculate(expression, {})
        with self.assertRaises(ValueError): calculate("1 + 2", {"unused": "4"})

    def test_citation_and_calculation_keep_literal_provenance_without_factual_approval(self):
        citation = self.citation()
        calculation = self.calculation(citation["id"])
        data = self.store.snapshot(self.cid)
        self.assertIsNone(data["decision"])
        self.assertTrue(all(note["current"] for note in data["work_notes"]))
        self.assertEqual(calculation["result"], "3.00")
        self.assertEqual(calculation["note_ids"], [citation["id"]])
        self.assertIn("Resultado aritmético", render(data))
        exported = snapshot(self.review)
        self.assertEqual(len(next(row for row in exported["dossiers"] if row["claim_id"] == self.cid)["work_notes"]), 2)

    def test_retiring_citation_marks_linked_calculation_stale_and_preserves_both(self):
        citation = self.citation()
        self.calculation(citation["id"])
        data = self.store.snapshot(self.cid)
        self.store.retire_note(self.cid, data["revision"], citation["id"], "Citação substituída.")
        data = self.store.snapshot(self.cid)
        self.assertEqual(len(data["work_notes"]), 2)
        self.assertFalse(any(note["current"] for note in data["work_notes"]))
        with self.assertRaisesRegex(ValueError, "anotações desatualizadas"):
            self.store.decide(self.cid, data["revision"], "confirmada", "Revisor fictício", "Ensaio.")
        self.store.decide(self.cid, data["revision"], "inconclusiva", "Revisor fictício", "Falta conferir as anotações.")

    def test_document_removal_invalidates_notes_and_manual_decision(self):
        note = self.citation()
        data = self.store.snapshot(self.cid)
        self.store.decide(self.cid, data["revision"], "confirmada", "Revisor fictício", "Decisão fictícia.")
        data = self.store.snapshot(self.cid)
        self.store.remove_document(self.cid, data["revision"], note["document_id"], "Fonte substituída.")
        data = self.store.snapshot(self.cid)
        self.assertIsNone(data["decision"])
        self.assertEqual(len(data["work_notes"]), 1)
        self.assertFalse(data["work_notes"][0]["current"])

    def test_wrong_quote_or_stale_editor_does_not_modify_case(self):
        note = self.citation()
        data = self.store.snapshot(self.cid)
        with self.assertRaises(ValueError):
            self.store.save_note(self.cid, data["revision"], "citation", {"document_id": note["document_id"], "block_id": "b1",
                "quote": "Número inventado.", "relation": "sustenta", "explanation": "Inválido."})
        self.assertEqual(self.store.snapshot(self.cid)["revision"], data["revision"])
        with self.assertRaises(ValueError):
            self.store.retire_note(self.cid, 0, note["id"], "Editor antigo.")

    def test_source_context_and_common_origin_are_preserved_across_preliminary_updates(self):
        note = self.citation()
        data = self.store.snapshot(self.cid)
        self.store.save_note(self.cid, data["revision"], "source_context", {"document_id": note["document_id"], "period": "2025",
            "available_on": "2025-12-31", "common_origin": "Mesma série fictícia", "explanation": "Não contar reproduções como fontes independentes."})
        jid = self.store.begin(self.cid, "analyze")
        self.store.finish(jid, fixtures.preliminary(), {})
        self.assertEqual(len(self.store.snapshot(self.cid)["work_notes"]), 2)


if __name__ == "__main__":
    unittest.main()
