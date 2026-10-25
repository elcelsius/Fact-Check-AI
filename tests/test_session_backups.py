import json
from pathlib import Path
import threading
import unittest
import zipfile

from factcheck.review import ReviewStore
from factcheck.dossiers import DossierStore
from factcheck.session_backups import create_backup, restore_backup, digest_file
from tests import test_evidence as fixtures
from tests.test_replay import wav_file


class BackupTests(unittest.TestCase):
    def setUp(self):
        fixtures.DossierTests.setUp(self)
        metadata = json.loads((self.root/"session.json").read_text())
        (self.root/"session.json").write_text(json.dumps({**metadata, "status": "completed"}))
        wav_file(self.root/"audio.wav")
        self.archive = self.root.parent / (self.root.name+".fcbak")
        self.target = self.root/"restored-sessions"

    def tearDown(self):
        self.archive.unlink(missing_ok=True)
        fixtures.DossierTests.tearDown(self)

    def test_roundtrip_keeps_audio_identity_and_human_decision_and_does_not_resume_jobs(self):
        self.store.decide(self.cid, 0, "inconclusiva", "Revisor fictício", "Sem documentos.")
        jid = self.store.begin(self.cid, "collect")
        before = digest_file(self.root/"audio.wav")
        create_backup(self.root, self.archive)
        result = restore_backup(self.archive, self.target)
        restored = ReviewStore(result["folder"])
        case = DossierStore(restored).snapshot(self.cid)
        self.assertEqual(case["decision"]["reviewer"], "Revisor fictício")
        self.assertEqual(next(job["status"] for job in case["jobs"] if job["id"] == jid), "interrupted")
        self.assertEqual(digest_file(Path(result["folder"])/"audio.wav"), before)
        self.assertEqual(digest_file(self.root/"audio.wav"), before)
        self.assertFalse(result["automatic_jobs_started"])

    def test_cancelled_creation_preserves_previous_archive_and_cancelled_restore_exposes_no_session(self):
        self.archive.write_bytes(b"previous-archive")
        signal = threading.Event()
        def cancel(_): signal.set()
        with self.assertRaises(InterruptedError): create_backup(self.root, self.archive, signal, cancel)
        self.assertEqual(self.archive.read_bytes(), b"previous-archive")
        signal.clear()
        create_backup(self.root, self.archive)
        signal.set()
        with self.assertRaises(InterruptedError): restore_backup(self.archive, self.target, signal)
        self.assertEqual(list(self.target.iterdir()), [])

    def test_manifest_hash_mismatch_and_unauthorized_paths_are_rejected_without_overwriting(self):
        create_backup(self.root, self.archive)
        with zipfile.ZipFile(self.archive) as archive:
            files = {name: archive.read(name) for name in archive.namelist()}
        for mode in ("hash", "path"):
            modified = dict(files)
            if mode == "hash": modified["session/audio.wav"] = b"corrupted"
            else: modified["../../outside.txt"] = b"do not extract"
            with zipfile.ZipFile(self.archive, "w") as archive:
                for name, data in modified.items(): archive.writestr(name, data)
            with self.assertRaises(ValueError): restore_backup(self.archive, self.target)
            self.assertEqual(list(self.target.iterdir()), [])
        self.assertFalse((self.root.parent/"outside.txt").exists())

    def test_live_capture_cannot_be_backed_up_and_other_session_is_never_replaced(self):
        import os
        metadata = json.loads((self.root/"session.json").read_text())
        (self.root/"session.json").write_text(json.dumps({**metadata, "status": "recording", "owner_pid": os.getpid()}))
        with self.assertRaises(ValueError): create_backup(self.root, self.archive)
        (self.root/"session.json").write_text(json.dumps(metadata))
        create_backup(self.root, self.archive)
        first = restore_backup(self.archive, self.target)
        second = restore_backup(self.archive, self.target)
        self.assertNotEqual(first["folder"], second["folder"])
        self.assertEqual(len(list(self.target.iterdir())), 2)

    def test_recovered_audio_file_and_timestamp_survive_roundtrip(self):
        recovered = self.root/"recovered"/("audio-"+"a"*24+".wav")
        recovered.parent.mkdir()
        wav_file(recovered)
        stamp = recovered.stat().st_mtime_ns
        create_backup(self.root, self.archive)
        restored = Path(restore_backup(self.archive, self.target)["folder"])/recovered.relative_to(self.root)
        self.assertEqual(restored.read_bytes(), recovered.read_bytes())
        self.assertEqual(restored.stat().st_mtime_ns, stamp)


if __name__ == "__main__":
    unittest.main()
