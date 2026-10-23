from dataclasses import asdict
import json
from pathlib import Path
import tempfile
import unittest

from factcheck.review import Debate, ReviewStore
from factcheck.triage import validate_items


def paragraph(pid, text, start, end, **extra):
    return {"paragraph_id": pid, "version": 1, "text": text, "source_text": text,
            "start": start, "end": end, "speaker": None, "closed": True,
            "parts": [{"sequence": pid, "text": text, "start": start, "end": end}], **extra}


def analyze(store, pid):
    job, source = store.begin_analysis(pid)
    item = {"quote": source["text"], "summary": source["text"], "reason": "Exemplo fictício.",
            "category": "fato", "topic": "Economia", "location": None,
            "period": None, "indicator": None, "comparison": None}
    return job, validate_items([item], source["text"])


class GroupingTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.folder = Path(self.directory.name)
        (self.folder / "session.json").write_text(json.dumps({"debate": asdict(Debate(participants=["Ana", "Bruno"]))}), encoding="utf8")
        self.originals = [paragraph(1, "A inflação não caiu", 1.0, 4.0),
                          paragraph(2, "no estado em 2025.", 4.5, 7.0)]
        (self.folder / "paragraphs.jsonl").write_text("\n".join(json.dumps(source) for source in self.originals), encoding="utf8")
        self.store = ReviewStore(self.folder)
        self.store.import_paragraphs()

    def tearDown(self):
        self.directory.cleanup()

    def combine(self, left=1, right=2, **kwargs):
        return self.store.combine(left, self.store.source(left)["revision"], right,
                                  self.store.source(right)["revision"], **{"confirmed_unknown": True, **kwargs})

    def test_merge_preserves_originals_corrections_audio_intervals_and_history(self):
        self.store.revise(1, 1, "A inflação não caiu", "Ana", True)
        self.store.revise(2, 1, "na cidade em 2025.", "Ana", True)
        job, items = analyze(self.store, 1)
        self.store.finish_analysis(job, items, {})
        before = [self.store.source(pid) for pid in (1, 2)]
        combined = self.combine()
        self.assertLess(combined["paragraph_id"], 0)
        self.assertEqual(combined["text"], "A inflação não caiu na cidade em 2025.")
        self.assertEqual(combined["original"]["source_text"], "A inflação não caiu no estado em 2025.")
        self.assertEqual(combined["original"]["source_paragraph_ids"], [1, 2])
        self.assertEqual(combined["original"]["parts"], self.originals[0]["parts"] + self.originals[1]["parts"])
        self.assertEqual((combined["start"], combined["end"]), (1.0, 7.0))
        self.assertEqual(combined["speaker"], "Ana")
        self.assertFalse(combined["human_reviewed"])
        self.assertEqual(self.store.sources(), [combined])
        for original in before:
            child = self.store.source(original["paragraph_id"])
            self.assertEqual(child["text"], original["text"])
            self.assertEqual(child["original"], original["original"])
        self.assertTrue(self.store.claims()[0]["source_outdated"])
        with self.store.connection() as db:
            audit = json.loads(db.execute("SELECT payload FROM history WHERE kind='paragraphs_combined'").fetchone()[0])
        self.assertEqual(audit["sources"], before)

    def test_reopen_and_reimport_do_not_resurrect_hidden_paragraphs(self):
        combined = self.combine()
        reopened = ReviewStore(self.folder)
        reopened.import_paragraphs()
        self.assertEqual(reopened.sources(), [combined])
        self.assertEqual(len(reopened.sources(include_inactive=True)), 3)
        self.assertEqual((self.folder / "paragraphs.jsonl").read_text(encoding="utf8"),
                         "\n".join(json.dumps(source) for source in self.originals))

    def test_undo_restores_human_edits_and_review_flags_with_new_revisions(self):
        before = self.store.revise(1, 1, "A inflação não subiu", "Ana", True)
        combined = self.combine()
        restored = self.store.uncombine(combined["paragraph_id"], combined["revision"])
        self.assertEqual([source["paragraph_id"] for source in restored], [1, 2])
        self.assertEqual(restored[0]["text"], before["text"])
        self.assertTrue(restored[0]["human_reviewed"])
        self.assertEqual(restored[0]["speaker"], "Ana")
        self.assertGreater(restored[0]["revision"], before["revision"])
        self.assertTrue(self.store.source(combined["paragraph_id"])["retired"])
        self.assertEqual([source["paragraph_id"] for source in self.store.sources()], [1, 2])

    def test_unknown_author_requires_confirmation_but_different_known_authors_are_blocked(self):
        with self.assertRaises(ValueError):
            self.combine(confirmed_unknown=False)
        self.store.revise(1, 1, self.originals[0]["text"], "Ana")
        self.store.revise(2, 1, self.originals[1]["text"], "Bruno")
        with self.assertRaises(ValueError):
            self.combine()
        self.assertEqual(len(self.store.sources(include_inactive=True)), 2)

    def test_same_known_author_needs_no_unknown_confirmation(self):
        for pid in (1, 2):
            self.store.revise(pid, 1, self.store.source(pid)["text"], "Ana")
        self.assertEqual(self.combine(confirmed_unknown=False)["speaker"], "Ana")

    def test_only_adjacent_completed_paragraphs_may_be_combined(self):
        self.store.ingest(paragraph(3, "Outra fala.", 8.0, 10.0))
        with self.assertRaises(ValueError):
            self.combine(1, 3)
        self.store.ingest({**self.originals[1], "version": 2, "closed": False})
        with self.assertRaises(ValueError):
            self.combine()

    def test_stale_merge_request_is_atomic(self):
        self.store.revise(2, 1, "Outro texto.", None)
        with self.assertRaises(ValueError):
            self.store.combine(1, 1, 2, 1, True)
        self.assertEqual([source["paragraph_id"] for source in self.store.sources()], [1, 2])
        self.assertEqual(self.store.source(1)["revision"], 1)

    def test_late_results_for_hidden_or_retired_sources_are_rejected(self):
        job, items = analyze(self.store, 1)
        combined = self.combine()
        self.assertFalse(self.store.finish_analysis(job, items, {}))
        for operation in [lambda: self.store.begin_analysis(1),
                          lambda: self.store.revise(1, self.store.source(1)["revision"], "Texto.", None)]:
            with self.assertRaises(ValueError):
                operation()
        next_job, next_items = analyze(self.store, combined["paragraph_id"])
        self.store.uncombine(combined["paragraph_id"], 1)
        self.assertFalse(self.store.finish_analysis(next_job, next_items, {}))
        with self.assertRaises(ValueError):
            self.store.begin_analysis(combined["paragraph_id"])
        self.assertEqual(self.store.claims(), [])

    def test_old_claims_do_not_become_valid_again_after_undo(self):
        job, items = analyze(self.store, 1)
        self.store.finish_analysis(job, items, {})
        combined = self.combine()
        self.store.uncombine(combined["paragraph_id"], 1)
        self.assertEqual(self.store.claims()[0]["status"], "analise_desatualizada")
        new_job, new_items = analyze(self.store, 1)
        self.assertTrue(self.store.finish_analysis(new_job, new_items, {}))

    def test_nested_combinations_undo_one_step_at_a_time_without_id_collisions(self):
        inner = self.combine()
        self.store.ingest(paragraph(3, "Outra frase.", 8.0, 10.0))
        outer = self.combine(inner["paragraph_id"], 3)
        self.assertEqual(outer["original"]["source_paragraph_ids"], [1, 2, 3])
        self.store.ingest(paragraph(4, "Fala seguinte.", 11.0, 13.0))
        self.assertEqual([source["paragraph_id"] for source in self.store.sources()], [outer["paragraph_id"], 4])
        self.store.uncombine(outer["paragraph_id"], 1)
        self.assertEqual([source["paragraph_id"] for source in self.store.sources()], [inner["paragraph_id"], 3, 4])
        self.store.uncombine(inner["paragraph_id"], self.store.source(inner["paragraph_id"])["revision"])
        self.assertEqual([source["paragraph_id"] for source in self.store.sources()], [1, 2, 3, 4])

    def test_edited_combination_requires_reconciliation_and_cannot_drop_a_negation(self):
        combined = self.combine()
        edited = self.store.revise(combined["paragraph_id"], 1, "A inflação não caiu na cidade em 2025.", "Ana")
        for texts, confirmed in [(None, False), (["A inflação não caiu", "na cidade em 2025."], False),
                                 (["A inflação caiu", "na cidade em 2025."], True)]:
            with self.subTest(texts=texts), self.assertRaises(ValueError):
                self.store.uncombine(edited["paragraph_id"], edited["revision"], texts, confirmed)
        restored = self.store.uncombine(edited["paragraph_id"], edited["revision"],
                                        ["A inflação não caiu", "na cidade em 2025."], True)
        self.assertEqual(" ".join(source["text"] for source in restored), edited["text"])
        self.assertTrue(all(source["speaker"] == "Ana" and not source["human_reviewed"] for source in restored))
        self.assertEqual(self.store.source(2)["original"]["source_text"], "no estado em 2025.")

    def test_updated_recognition_invalidates_combination_and_undo_keeps_latest_original(self):
        combined = self.combine()
        self.store.ingest({**self.originals[0], "version": 2, "source_text": "A inflação não subiu"})
        changed = self.store.source(combined["paragraph_id"])
        self.assertTrue(changed["needs_rebase"])
        with self.assertRaises(ValueError):
            self.store.begin_analysis(changed["paragraph_id"])
        with self.assertRaises(ValueError):
            self.store.revise(changed["paragraph_id"], changed["revision"], changed["text"], None)
        restored = self.store.uncombine(changed["paragraph_id"], changed["revision"],
                                        [self.store.source(pid)["text"] for pid in (1, 2)], True)
        self.assertEqual(restored[0]["original"]["source_text"], "A inflação não subiu")
        self.assertEqual(restored[0]["text"], "A inflação não subiu")

    def test_reconciliation_after_speaker_only_edit_cannot_omit_words(self):
        combined = self.combine()
        edited = self.store.revise(combined["paragraph_id"], 1, combined["text"], "Ana", True)
        with self.assertRaises(ValueError):
            self.store.uncombine(edited["paragraph_id"], edited["revision"],
                                 ["A inflação caiu", "no estado em 2025."], True)
        self.assertEqual(self.store.sources(), [edited])

    def test_origin_updates_propagate_through_nested_groups(self):
        inner = self.combine()
        self.store.ingest(paragraph(3, "Outra frase.", 8.0, 10.0))
        outer = self.combine(inner["paragraph_id"], 3)
        self.store.ingest({**self.originals[0], "version": 2, "source_text": "A inflação não subiu"})
        changed = self.store.source(outer["paragraph_id"])
        self.assertTrue(changed["needs_rebase"])
        restored = self.store.uncombine(changed["paragraph_id"], changed["revision"],
                                        [self.store.source(pid)["text"] for pid in changed["merged_from"]], True)
        self.assertTrue(restored[0]["needs_rebase"])
        with self.assertRaises(ValueError):
            self.store.begin_analysis(inner["paragraph_id"])

    def test_stale_undo_and_repeated_undo_are_rejected(self):
        combined = self.combine()
        self.store.revise(combined["paragraph_id"], 1, combined["text"], None, False)
        with self.assertRaises(ValueError):
            self.store.uncombine(combined["paragraph_id"], 1)
        self.store.uncombine(combined["paragraph_id"], 2)
        with self.assertRaises(ValueError):
            self.store.uncombine(combined["paragraph_id"], 3)


if __name__ == "__main__":
    unittest.main()
