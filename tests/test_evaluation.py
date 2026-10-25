import threading
import unittest

from factcheck.evaluation import EvaluationStore, tokens, word_errors
from factcheck.reporting import session_report
from factcheck.triage import validate_items
from tests import test_evidence as fixtures


class EvaluationTests(unittest.TestCase):
    setUp = fixtures.DossierTests.setUp
    tearDown = fixtures.DossierTests.tearDown

    def reference(self, expected=None, analyzed=True):
        source = self.review.source(1)
        self.review.revise(1, source["revision"], source["text"], None, reviewed=True)
        if analyzed:
            jid, current = self.review.begin_analysis(1, force=True)
            self.review.finish_analysis(jid, validate_items([{"quote": current["text"], "summary": current["text"], "category": "fato", "reason": "Ensaio.",
                "topic": None, "location": None, "period": None, "indicator": None, "comparison": None}], current["text"]), {})
        evaluation = EvaluationStore(self.review)
        evaluation.save_reference(1, 0, self.review.source(1)["revision"], [fixtures.TEXT] if expected is None else expected, "Anotador fictício", blind=False)
        return evaluation

    def test_word_error_counts_keep_negation_numeric_signs_and_undefined_denominator(self):
        measured = word_errors("A taxa não caiu -3%.", "A taxa caiu 3%.")
        self.assertEqual(measured["errors"], 2)
        self.assertEqual(measured["reference_words"], 5)
        self.assertAlmostEqual(measured["wer"], .4)
        self.assertIsNone(word_errors("", "texto")["wer"])
        self.assertNotEqual(tokens("3,500"), tokens("3.500"))
        self.assertEqual(tokens("−3%"), tokens("-3%"))

    def test_metrics_require_explicit_reference_and_apply_only_to_annotated_subset(self):
        with self.assertRaises(ValueError): EvaluationStore(self.review).evaluate()
        evaluation = self.reference()
        result = evaluation.evaluate()
        self.assertEqual(result["metrics"]["literal_precision"], 1)
        self.assertEqual(result["metrics"]["literal_recall"], 1)
        self.assertEqual(result["metrics"]["wer"], 0)
        report = session_report(self.review)
        self.assertEqual(report["quality"]["human_reference"], "provided")
        self.assertEqual(report["quality"]["precision"], 1)
        self.assertEqual(report["quality"]["metrics"]["annotated_paragraphs"], 1)

    def test_discarded_ai_prediction_is_not_hidden_from_false_positive_count(self):
        evaluation = self.reference(expected=[])
        latest = self.review.claims()[0]
        self.review.discard_claim(latest["id"], "Falso positivo fictício.")
        result = evaluation.evaluate()
        self.assertEqual(result["metrics"]["false_positives"], 1)
        self.assertEqual(result["metrics"]["literal_precision"], 0)
        self.assertIsNone(result["metrics"]["literal_recall"])

    def test_missing_triage_is_not_treated_as_measured_zero_recall(self):
        evaluation = self.reference(analyzed=False)
        result = evaluation.evaluate()
        self.assertEqual(result["metrics"]["annotated_with_triage"], 0)
        self.assertIsNone(result["metrics"]["literal_recall"])

    def test_source_change_and_cancelled_run_never_publish_current_metrics(self):
        evaluation = self.reference()
        evaluation.evaluate()
        self.review.revise(1, self.review.source(1)["revision"], "Texto corrigido depois.", None)
        self.assertFalse(evaluation.latest()["current"])
        report = session_report(self.review)
        self.assertEqual(report["quality"]["human_reference"], "stale")
        self.assertIsNone(report["quality"]["precision"])
        signal = threading.Event(); signal.set()
        with self.assertRaises(InterruptedError): word_errors("um dois", "um três", signal)

    def test_edit_during_evaluation_is_rejected_at_commit(self):
        evaluation = self.reference()
        def change(_): self.review.revise(1, self.review.source(1)["revision"], "Alterado durante cálculo.", None)
        with self.assertRaises(ValueError): evaluation.evaluate(progress=change)
        self.assertIsNone(evaluation.latest())

    def test_reference_revision_and_reserved_partition_prevent_silent_reuse(self):
        evaluation = self.reference()
        with self.assertRaises(ValueError): evaluation.save_reference(1, 0, self.review.source(1)["revision"], [], "Outro anotador")
        source = self.review.source(1)
        self.review.ingest({"paragraph_id": 2, "version": 1, "text": source["text"], "source_text": source["text"], "start": 7, "end": 10, "closed": True, "parts": []})
        self.review.revise(2, 1, source["text"], None, reviewed=True)
        with self.assertRaises(ValueError):
            evaluation.save_reference(2, 0, self.review.source(2)["revision"], [], "Anotador fictício", partition="development")


if __name__ == "__main__":
    unittest.main()
