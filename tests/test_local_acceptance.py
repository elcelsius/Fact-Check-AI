import json
from pathlib import Path
import unittest

from factcheck.dossiers import DossierStore
from factcheck.exports import snapshot
from factcheck.review import ReviewStore
from factcheck.session_backups import create_backup, restore_backup
from tests import test_evidence as fixtures
from tests.test_replay import wav_file


class LocalAcceptanceTests(unittest.TestCase):
    setUp = fixtures.DossierTests.setUp
    tearDown = fixtures.DossierTests.tearDown

    def test_operator_case_with_calculation_export_and_restore_preserves_decision_and_provenance(self):
        metadata = json.loads((self.root/"session.json").read_text())
        (self.root/"session.json").write_text(json.dumps({**metadata, "status": "completed"}))
        wav_file(self.root/"audio.wav")
        text = "A inflação foi de 3,5%"
        item = self.review.create_claims(1, 1, [{"quote": text, "summary": text, "category": "fato", "topic": None}], "Caso fictício de aceitação.")[0]
        cid = item["id"]
        self.store.finish(self.store.begin(cid, "collect"), fixtures.document(), {})
        note = self.store.save_note(cid, self.store.snapshot(cid)["revision"], "citation", {"document_id": "doc1", "block_id": "b1", "quote": fixtures.TEXT, "relation": "contextualiza", "explanation": "Fonte fictícia usada somente no teste."})
        current = self.store.snapshot(cid)
        anchor = current["work_notes"][0]["id"]
        self.store.save_note(cid, current["revision"], "calculation", {"formula": "taxa / 100", "variables": {"taxa": "3,5"}, "unit": "fração", "note_ids": [anchor], "explanation": "Conversão reproduzível; não decide veracidade."})
        self.store.decide(cid, self.store.snapshot(cid)["revision"], "inconclusiva", "Revisor fictício", "Ensaio com fonte sintética; sem conclusão factual real.")
        exported = snapshot(self.review)
        dossier = next(row for row in exported["dossiers"] if row["claim_id"] == cid)
        self.assertEqual(dossier["decision"]["verdict"], "inconclusiva")
        self.assertEqual(dossier["work_notes"][1]["result"], "0.035")
        archive = self.root.parent/(self.root.name+"-acceptance.fcbak")
        self.addCleanup(archive.unlink, missing_ok=True)
        create_backup(self.root, archive)
        restored = restore_backup(archive, self.root/"restored")
        case = DossierStore(ReviewStore(Path(restored["folder"]))).snapshot(cid)
        self.assertEqual(case["decision"]["reviewer"], "Revisor fictício")
        self.assertTrue(all(note["current"] for note in case["work_notes"]))
        self.assertEqual(case["claim"]["creation"]["origin"], "operator_input")
        self.assertIsNone(case["preliminary"])


if __name__ == "__main__": unittest.main()
