from contextlib import contextmanager
from dataclasses import asdict
import csv
import json
from pathlib import Path
import shutil
import tempfile
import threading
import unittest
from unittest.mock import patch

from factcheck.dossiers import DossierStore
from factcheck.exports import ExportTask, csv_rows, snapshot, write_export
from factcheck.review import Debate, ReviewStore
from factcheck.triage import validate_items


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.folder = self.root / "session"
        self.folder.mkdir()
        self.event = Debate(title="Ensaio fictício", participants=["Ana"])
        (self.folder / "session.json").write_text(json.dumps({"debate": asdict(self.event), "session_id": "sessao-teste",
                                                             "api_key": "MARCADOR-SECRETO"}), encoding="utf8")
        self.review = ReviewStore(self.folder)
        for pid, text, start, end in [(1, "A inflação não caiu em 2025.", 1.0, 4.0),
                                      (2, "Acho esta medida excelente.", 5.0, 8.0)]:
            self.review.ingest({"paragraph_id": pid, "version": 1, "source_text": text, "text": text,
                                "start": start, "end": end, "speaker": None, "closed": True, "parts": []})
        self.cid = self.analyze(1)
        self.opinion = self.analyze(2, "opiniao")
        self.dossiers = DossierStore(self.review)

    def tearDown(self):
        self.directory.cleanup()

    def analyze(self, pid, category="fato"):
        job, source = self.review.begin_analysis(pid)
        item = {"quote": source["text"], "summary": source["text"], "reason": "Exemplo fictício.", "category": category,
                "topic": "Economia", "location": None, "period": None, "indicator": None, "comparison": None}
        engine = {"name": "fixture", "model": "teste", "api_key": "MARCADOR-SECRETO", "usage": {"totalTokenCount": 12, "secret": "MARCADOR-SECRETO"}}
        self.review.finish_analysis(job, validate_items([item], source["text"]), engine)
        return self.review.claims()[0]["id"]

    def add_document(self, acquisition="local_import"):
        doc = {"id": "fonte-teste", "url": "https://ibge.gov.br/exemplo-ficticio", "title": "Documento fictício",
               "institution": "IBGE", "author": "Teste", "published_at": "2025-12-31", "accessed_at": "",
               "acquisition": acquisition, "imported_at": "2026-10-23T12:00:00+00:00", "sha256": "abc", "text_sha256": "def",
               "content_type": "text/html", "extractor": "test", "warnings": ["Origem a conferir."], "truncated": False,
               "blocks": [{"id": "b1", "locator": "parágrafo 1", "text": "Texto fictício para conferir a fonte."}],
               "local_path": "C:/privado/MARCADOR-SECRETO.html"}
        job = self.dossiers.begin(self.cid, "import")
        self.dossiers.finish(job, doc)

    def test_default_preserves_opinions_and_pending_human_review_without_mutating_store(self):
        before = self.review.path.read_bytes()
        data = snapshot(self.review)
        self.assertEqual(len(data["paragraphs"]), 2)
        self.assertEqual({claim["category"] for claim in data["claims"]}, {"fato", "opiniao"})
        self.assertTrue(all(not row["human_reviewed"] for row in data["paragraphs"]))
        self.assertTrue(all(not row["decision_current"] for row in data["dossiers"]))
        self.assertNotIn("MARCADOR-SECRETO", json.dumps(data))
        self.assertEqual(self.review.path.read_bytes(), before)

    def test_reexport_keeps_ids_and_content_hash_but_records_a_new_export_time(self):
        with patch("factcheck.exports.now", return_value="2026-10-23T12:00:00+00:00"):
            first = snapshot(self.review)
        with patch("factcheck.exports.now", return_value="2026-10-23T12:01:00+00:00"):
            second = snapshot(self.review)
        self.assertEqual(first["content_sha256"], second["content_sha256"])
        self.assertNotEqual(first["exported_at"], second["exported_at"])
        self.assertEqual(first["paragraphs"], second["paragraphs"])
        self.review.revise(1, 1, "Texto corrigido.", "Ana")
        third = snapshot(self.review)
        self.assertEqual(first["paragraphs"][0]["record_id"], third["paragraphs"][0]["record_id"])
        self.assertNotEqual(first["paragraphs"][0]["record_sha256"], third["paragraphs"][0]["record_sha256"])
        self.assertEqual(first["session_id"], third["session_id"])
        self.assertEqual(first["event"]["event_id"], third["event"]["event_id"])

    def test_discarded_claim_is_optional_but_its_transcription_is_kept(self):
        self.review.discard_claim(self.opinion, "Exemplo de descarte.")
        current = snapshot(self.review)
        self.assertEqual(len(current["paragraphs"]), 2)
        self.assertEqual([claim["claim_id"] for claim in current["claims"]], [self.cid])
        historical = snapshot(self.review, True)
        discarded = next(claim for claim in historical["claims"] if claim["claim_id"] == self.opinion)
        self.assertFalse(discarded["source_current"])
        self.assertEqual(discarded["discard_reason"], "Exemplo de descarte.")
        csv_row = next(row for row in csv_rows(historical, "claims") if row["afirmacao_id"] == self.opinion)
        self.assertEqual(csv_row["motivo_descarte"], "Exemplo de descarte.")

    def test_combined_origins_are_resolvable_without_duplicating_active_csv_rows(self):
        combined = self.review.combine(1, 1, 2, 1, True)
        cid = self.analyze(combined["paragraph_id"])
        current = snapshot(self.review)
        self.assertEqual([row["paragraph_id"] for row in current["paragraphs"]], [combined["paragraph_id"]])
        self.assertEqual([row["paragraph_id"] for row in current["origin_paragraphs"]], [1, 2])
        self.assertEqual(current["claims"][0]["claim_id"], cid)
        self.assertEqual(current["claims"][0]["source_paragraph_ids"], [1, 2])
        self.assertEqual(len(list(csv_rows(current, "paragraphs"))), 1)
        self.assertEqual(len(snapshot(self.review, True)["paragraphs"]), 3)

    def test_preliminary_and_human_decision_remain_separate_and_stale_decisions_are_marked(self):
        self.add_document()
        job = self.dossiers.begin(self.cid, "analyze")
        self.dossiers.finish(job, {"verdict": "confirmada", "summary": "Hipótese fictícia.", "reason": "Exemplo.", "gaps": [],
            "compatibility": {"period": "compativel"}, "citations": [{"document_id": "fonte-teste", "block_id": "b1",
            "quote": "Texto fictício", "relation": "sustenta", "explanation": "Exemplo."}]}, {"model": "teste"})
        data = snapshot(self.review)
        first = next(row for row in data["dossiers"] if row["claim_id"] == self.cid)
        self.assertTrue(first["preliminary_current"])
        self.assertFalse(first["decision_current"])
        self.dossiers.decide(self.cid, first["revision"], "inconclusiva", "Revisor", "Falta conferir a origem.")
        data = snapshot(self.review)
        row = next(row for row in csv_rows(data, "claims") if row["afirmacao_id"] == self.cid)
        self.assertEqual(row["preliminar_classificacao"], "confirmada")
        self.assertEqual(row["preliminar_justificativa"], "Exemplo.")
        self.assertEqual(row["decisao_humana_classificacao"], "inconclusiva")
        self.assertEqual(row["decisao_atual"], "sim")
        self.review.revise(1, 1, "A fala foi corrigida.", "Ana")
        stale = next(row for row in csv_rows(snapshot(self.review, True), "claims") if row["afirmacao_id"] == self.cid)
        self.assertEqual(stale["estado_dossie"], "historical")
        self.assertEqual(stale["decisao_atual"], "nao")
        self.assertEqual(stale["decisao_humana_responsavel"], "Revisor")
        self.assertNotIn(self.cid, [row["claim_id"] for row in snapshot(self.review)["claims"]])

    def test_imported_source_keeps_unconfirmed_origin_and_json_retains_document_text(self):
        self.add_document()
        data = snapshot(self.review)
        source = data["sources"][0]
        self.assertFalse(source["url_access_confirmed"])
        self.assertEqual(source["acquisition"], "local_import")
        self.assertEqual(source["blocks"][0]["locator"], "parágrafo 1")
        self.assertNotIn("MARCADOR-SECRETO", json.dumps(data))
        self.assertEqual(next(row for row in data["dossiers"] if row["claim_id"] == self.cid)["state"], "sources_collected")
        exported = self.root / "sessao.json"
        write_export(data, exported, "json", self.folder)
        self.assertEqual(json.loads(exported.read_text(encoding="utf8")), data)
        csv_row = list(csv_rows(data, "sources"))[0]
        self.assertEqual(csv_row["acesso_url_confirmado"], "nao")

    def test_csv_quotes_separators_newlines_and_neutralizes_formula_like_text(self):
        values = ['=1+2";=3+4', '+SUM(1;2)', '-SUM(1;2)', '@SUM(1;2)', '\t=1+2', '\r=1+2', '\n=1+2',
                  '\ufeff=1+2', '\ufeff \ufeff=1+2', '　＝1+2', '＋1+2', '－1+2', '＠SUM(1;2)']
        target = self.root / "falas.csv"
        for value in values:
            with self.subTest(value=value):
                current = self.review.source(1)
                self.review.ingest({**current["original"], "version": current["source_version"] + 1,
                                    "source_text": value, "text": value})
                data = snapshot(self.review)
                write_export(data, target, "paragraphs", self.folder)
                with target.open(encoding="utf-8-sig", newline="") as stream:
                    rows = list(csv.DictReader(stream, delimiter=";"))
                self.assertEqual(rows[0]["texto"], "\t" + value)
                self.assertEqual(data["paragraphs"][0]["text"], value)
                self.assertEqual(len(rows), 2)
                self.assertTrue(target.read_bytes().startswith(b'\xef\xbb\xbf"formato_versao";'))

    def test_csv_keeps_normal_accents_multiline_text_and_negative_numeric_ids(self):
        combined = self.review.combine(1, 1, 2, 1, True)
        text = 'Declaração; com "aspas"\ne uma segunda linha.'
        self.review.revise(combined["paragraph_id"], 1, text, "Ana")
        target = self.root / "falas.csv"
        write_export(snapshot(self.review), target, "paragraphs", self.folder)
        with target.open(encoding="utf-8-sig", newline="") as stream:
            row = next(csv.DictReader(stream, delimiter=";"))
        self.assertEqual(row["texto"], text)
        self.assertEqual(row["paragrafo_id"], "-1")

    def test_video_reference_and_reviewed_text_survive_all_formats(self):
        self.review.save_video_reference(750, 0)
        self.review.revise(1, 1, "Correção fictícia.", "Ana", True)
        data = snapshot(self.review)
        row = list(csv_rows(data, "paragraphs"))[0]
        self.assertEqual(row["inicio_video"], "00:12:31")
        self.assertEqual(row["fim_video"], "00:12:34")
        self.assertEqual(row["inicio_captura_s"], 1.0)
        self.assertEqual(row["texto"], "Correção fictícia.")
        self.assertEqual(row["texto_reconhecido"], "A inflação não caiu em 2025.")
        self.assertEqual(row["transcricao_conferida"], "sim")

    def test_late_cancellation_preserves_existing_file_and_cleans_temporary_file(self):
        target = self.root / "sessao.json"
        target.write_bytes(b"arquivo anterior")
        cancelled = threading.Event()
        with patch("factcheck.exports.os.fsync", side_effect=lambda fd: cancelled.set()):
            with self.assertRaises(InterruptedError):
                write_export(snapshot(self.review), target, "json", self.folder, cancelled)
        self.assertEqual(target.read_bytes(), b"arquivo anterior")
        self.assertEqual(list(self.root.glob(".factcheck-export-*")), [])

    def test_write_failure_preserves_existing_file_and_raw_session_cannot_be_overwritten(self):
        target = self.root / "sessao.json"
        target.write_bytes(b"arquivo anterior")
        data = snapshot(self.review)
        with patch("factcheck.exports.os.replace", side_effect=OSError("Falha fictícia.")), self.assertRaises(OSError):
            write_export(data, target, "json", self.folder)
        self.assertEqual(target.read_bytes(), b"arquivo anterior")
        self.assertEqual(list(self.root.glob(".factcheck-export-*")), [])
        original = (self.folder / "session.json").read_bytes()
        with self.assertRaises(ValueError):
            write_export(data, self.folder / "session.json", "json", self.folder)
        self.assertEqual((self.folder / "session.json").read_bytes(), original)
        with self.assertRaises(ValueError):
            write_export(data, self.root / "audio.wav", "paragraphs", self.folder)

    def test_background_task_finishes_real_export_and_cancel_before_start_writes_nothing(self):
        target = self.root / "sessao.json"
        done, results = threading.Event(), []
        def emit(kind, result):
            results.append((kind, result))
            done.set()
        task = ExportTask(self.review, target, "json", False, emit)
        task.start()
        self.assertTrue(done.wait(5))
        self.assertTrue(results[0][1]["success"])
        self.assertEqual(json.loads(target.read_text(encoding="utf8"))["session_id"], "sessao-teste")
        original = target.read_bytes()
        done.clear()
        task = ExportTask(self.review, target, "json", False, emit)
        task.cancel()
        task.start()
        self.assertTrue(done.wait(5))
        self.assertFalse(results[-1][1]["success"])
        self.assertEqual(task.pending, 0)
        self.assertEqual(target.read_bytes(), original)

    def test_empty_session_exports_csv_headers_and_valid_json(self):
        folder = self.root / "empty"
        folder.mkdir()
        (folder / "session.json").write_text('{}', encoding="utf8")
        data = snapshot(ReviewStore(folder))
        self.assertEqual(data["claims"], [])
        for kind in ("paragraphs", "claims", "sources"):
            target = self.root / f"{kind}.csv"
            write_export(data, target, kind, folder)
            with target.open(encoding="utf-8-sig", newline="") as stream:
                reader = csv.DictReader(stream, delimiter=";")
                self.assertIn("registro_id", reader.fieldnames)
                self.assertEqual(list(reader), [])

    def test_legacy_identity_migration_and_folder_copy_keep_stable_ids_without_invalidating_claims(self):
        with self.review.connection() as db:
            data = json.loads(db.execute("SELECT payload FROM debate WHERE id=1").fetchone()[0])
            del data["event_id"]
            db.execute("UPDATE debate SET payload=? WHERE id=1", (json.dumps(data),))
            db.execute("DROP TABLE session_identity")
            db.execute("PRAGMA user_version=2")
        before = self.review.claims()
        migrated = ReviewStore(self.folder)
        self.assertEqual(migrated.claims(), before)
        identity = migrated.debate()["event_id"], migrated.session_id()
        copied = self.root / "renamed-copy"
        copied.mkdir()
        for filename in ("session.json", "review.sqlite3"):
            shutil.copyfile(self.folder / filename, copied / filename)
        reopened = ReviewStore(copied)
        self.assertEqual((reopened.debate()["event_id"], reopened.session_id()), identity)
        self.assertEqual(snapshot(reopened)["content_sha256"], snapshot(migrated)["content_sha256"])

    def test_editing_event_metadata_keeps_event_and_session_identity(self):
        identity = self.review.debate()["event_id"], self.review.session_id()
        self.review.save_debate(Debate(title="Título corrigido", participants=["Ana"]))
        self.assertEqual((self.review.debate()["event_id"], self.review.session_id()), identity)

    def test_snapshot_does_not_mix_rows_with_concurrent_revision(self):
        inside, release, changed = threading.Event(), threading.Event(), threading.Event()
        results, errors = [], []
        connection = self.review.connection
        @contextmanager
        def gate():
            with connection() as db:
                if threading.current_thread().name == "export-snapshot":
                    def trace(sql):
                        if sql.startswith("SELECT id,claim_id,payload FROM evidence"):
                            inside.set()
                            if not release.wait(3):
                                raise TimeoutError("Tempo de teste excedido.")
                    db.set_trace_callback(trace)
                yield db
        def read():
            try:
                results.append(snapshot(self.review))
            except Exception as exc:
                errors.append(exc)
        def revise():
            try:
                self.review.revise(1, 1, "Texto atualizado depois da cópia.", "Ana")
                changed.set()
            except Exception as exc:
                errors.append(exc)
        with patch.object(self.review, "connection", gate):
            reader = threading.Thread(target=read, name="export-snapshot")
            writer = threading.Thread(target=revise)
            reader.start()
            try:
                self.assertTrue(inside.wait(3))
                writer.start()
                self.assertFalse(changed.wait(0.05))
            finally:
                release.set()
                reader.join(3)
                if writer.ident:
                    writer.join(3)
        self.assertEqual(errors, [])
        self.assertTrue(changed.is_set())
        self.assertEqual(results[0]["paragraphs"][0]["text"], "A inflação não caiu em 2025.")
        self.assertTrue(all(row["source_current"] for row in results[0]["claims"]))
        self.assertNotEqual(self.review.source(1)["text"], results[0]["paragraphs"][0]["text"])


if __name__ == "__main__":
    unittest.main()
