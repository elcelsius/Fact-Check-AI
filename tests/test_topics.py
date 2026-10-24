from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import queue
import sqlite3
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from factcheck.exports import csv_rows, snapshot
from factcheck.dossiers import render
from factcheck.topics import (TopicStore, annotate, checked_snapshot, describe_topic, identity, load_snapshot, make_snapshot)
from factcheck.triage import TriageRunner, validate_items
from tests.test_previous_checks import session


def fields(**changes):
    return {"name": "Economia", "aliases": ["Inflação", "Índice de preços"], "description": "Tema fictício; confirmar os recortes em cada caso.", **changes}


class TopicStoreTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.store = TopicStore(self.root / "library")

    def tearDown(self):
        self.directory.cleanup()

    def add(self, **changes):
        return self.store.save(fields(**changes), "Preparar vocabulário para ensaio.")

    def test_missing_vocabulary_does_not_create_files_and_keeps_free_topics(self):
        other = self.root / "sem-configuracao"
        before = load_snapshot(other)
        self.assertFalse(before["configured"])
        self.assertFalse(other.exists())
        result = annotate({"topic": "Tema livre", "category": "opiniao"}, before)
        self.assertEqual(result["topic"], "Tema livre")
        self.assertEqual(result["topic_annotation"]["status"], "unconfigured")
        self.assertEqual(result["category"], "opiniao")

    def test_register_reopen_and_snapshot_have_stable_identity_and_only_active_definitions(self):
        entry = self.add()
        self.assertEqual(TopicStore(self.root / "library").entries(), [entry])
        first = load_snapshot(self.root)
        self.assertEqual(first, load_snapshot(self.root))
        self.assertEqual(first["revision"], 1)
        self.assertEqual(first["topics"][0]["id"], entry["id"])
        self.assertNotIn("reason", first["topics"][0])
        self.store.set_archived(entry["id"], 1, True, "Fora da pauta.")
        second = load_snapshot(self.root)
        self.assertEqual(second["id"], first["id"])
        self.assertEqual(second["revision"], 2)
        self.assertEqual(second["topics"], [])

    def test_normalizes_only_full_registered_names_or_aliases_ignoring_case_accents_and_spaces(self):
        self.add()
        vocabulary = load_snapshot(self.root)
        for topic in ("ECONOMIA", "  indice  de   precos ", "inflacao"):
            result = annotate({"topic": topic, "quote": "Fala literal intacta."}, vocabulary)
            self.assertEqual(result["topic"], "Economia")
            self.assertEqual(result["quote"], "Fala literal intacta.")
            self.assertEqual(result["topic_annotation"]["original"], topic)
            self.assertEqual(result["topic_annotation"]["status"], "matched")
        for topic in ("Economia e saúde", "preço", "Outro tema"):
            result = annotate({"topic": topic}, vocabulary)
            self.assertEqual(result["topic"], topic)
            self.assertEqual(result["topic_annotation"]["status"], "unmapped")
        self.assertEqual(annotate({"topic": None}, vocabulary)["topic_annotation"]["status"], "empty")
        self.assertIsNone(annotate({"topic": "   "}, vocabulary)["topic"])

    def test_aliases_are_deduplicated_and_cannot_conflict_with_names_including_archived(self):
        entry = self.add(aliases=["economía", " inflação ", "INFLACAO", "Índice de preços"])
        self.assertEqual(entry["aliases"], ["inflação", "Índice de preços"])
        for name, aliases in (("INFLACAO", []), ("Outro tema", ["economía"])):
            with self.assertRaisesRegex(ValueError, "outro tema"):
                self.add(name=name, aliases=aliases)
        self.store.set_archived(entry["id"], 1, True, "Arquivar para ensaio.")
        with self.assertRaises(ValueError):
            self.add(name="Índice de preços", aliases=[])

    def test_edit_archive_restore_keep_history_and_editing_archived_does_not_restore(self):
        entry = self.add()
        self.store.save(fields(name="Indicadores econômicos"), "Detalhar o nome.", entry["id"], 1)
        self.store.set_archived(entry["id"], 2, True, "Arquivar.")
        archived = self.store.save(fields(name="Indicadores econômicos", description="Conferir metodologia."), "Detalhar limites.", entry["id"], 3)
        self.assertTrue(archived["archived"])
        restored = self.store.set_archived(entry["id"], 4, False, "Retomar.")
        self.assertFalse(restored["archived"])
        history = self.store.history(entry["id"])
        self.assertEqual(len(history), 5)
        self.assertEqual(history[1]["previous"], entry)
        self.assertEqual(history[-1]["vocabulary_revision"], 5)

    def test_stale_edit_and_archive_do_not_replace_newer_definition(self):
        entry = self.add()
        self.store.save(fields(description="Definição posterior."), "Detalhar conceito.", entry["id"], 1)
        with self.assertRaises(ValueError):
            self.store.save(fields(name="Editor antigo"), "Outra edição.", entry["id"], 1)
        with self.assertRaises(ValueError):
            self.store.set_archived(entry["id"], 1, True, "Estado antigo.")
        self.assertEqual(self.store.entries()[0]["description"], "Definição posterior.")

    def test_noop_preserves_vocabulary_revision_and_history(self):
        entry = self.add()
        before = load_snapshot(self.root)
        self.assertEqual(self.store.save(fields(), entry["reason"], entry["id"], 1), entry)
        self.assertEqual(self.store.set_archived(entry["id"], 1, False, "Sem mudança."), entry)
        self.assertEqual(load_snapshot(self.root), before)
        self.assertEqual(len(self.store.history(entry["id"])), 1)

    def test_history_failure_rolls_back_names_identity_revision_and_definition(self):
        entry = self.add()
        before = load_snapshot(self.root)
        with self.store.connection() as db:
            db.execute("CREATE TRIGGER fail_topic_history BEFORE INSERT ON topic_history BEGIN SELECT RAISE(ABORT,'ensaio'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.save(fields(name="Nome que não deve persistir"), "Ensaio de rollback.", entry["id"], 1)
        self.assertEqual(self.store.entries(), [entry])
        self.assertEqual(load_snapshot(self.root), before)

    def test_invalid_fields_reasons_and_revision_do_not_write(self):
        for data in (fields(name=""), fields(name="Saúde\nPública"), fields(name="A; B"), fields(aliases="Inflação"),
                     fields(aliases=["x"]*13), fields(description="x"*1501), {**fields(), "api_key": "Não aceitar"}):
            with self.subTest(data=data), self.assertRaises(ValueError):
                self.store.save(data, "Motivo.")
        for reason, revision in (("", 0), ("x"*2001, 0), ("Motivo.", True)):
            with self.assertRaises(ValueError):
                self.store.save(fields(), reason, expected_revision=revision)
        self.assertEqual(self.store.entries(), [])

    def test_snapshot_rejects_tampering_or_ambiguous_terms_and_filters_unknown_fields(self):
        self.add()
        vocabulary = load_snapshot(self.root)
        data = deepcopy(vocabulary)
        data["topics"][0]["name"] = "Alteração fora do snapshot"
        with self.assertRaises(ValueError):
            checked_snapshot(data)
        data = deepcopy(vocabulary)
        data["topics"][0]["secret"] = "Não copiar"
        self.assertEqual(checked_snapshot(data), vocabulary)
        duplicate = {**vocabulary["topics"][0], "id": "a"*32}
        with self.assertRaises(ValueError):
            make_snapshot(vocabulary["id"], 2, [*vocabulary["topics"], duplicate])
        for changes in ({"archived": "false"}, {"revision": 99}):
            with self.assertRaises(ValueError):
                make_snapshot(vocabulary["id"], 1, [{**vocabulary["topics"][0], **changes}])

    def test_reading_vocabulary_is_read_only_and_invalid_file_has_safe_error(self):
        self.add()
        before = sha256(self.store.path.read_bytes()).hexdigest()
        load_snapshot(self.root)
        self.assertEqual(sha256(self.store.path.read_bytes()).hexdigest(), before)
        self.store.path.write_bytes(b"banco invalido SEGREDO-NAO-MOSTRAR")
        with self.assertRaisesRegex(ValueError, "Não foi possível ler") as error:
            load_snapshot(self.root)
        self.assertNotIn("SEGREDO", str(error.exception))


class TopicWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.review, self.dossiers, self.cid = session(self.root / "sessao")
        self.store = TopicStore(self.root / "library")
        self.entry = self.store.save(fields(), "Vocabulário fictício.")
        self.vocabulary = load_snapshot(self.root)

    def tearDown(self):
        self.directory.cleanup()

    def analyze(self, topic="inflacao", vocabulary=None):
        old = self.review.claims()[0]
        item = {key: old.get(key) for key in ("quote", "summary", "category", "reason", "topic", "location", "period", "indicator", "comparison")}
        item["topic"] = topic
        job, source = self.review.begin_analysis(1, force=True, topic_vocabulary=vocabulary or self.vocabulary)
        self.review.finish_analysis(job, validate_items([item], source["text"]), {"name": "Motor fictício"}, topic_vocabulary=vocabulary or self.vocabulary)
        return next(row for row in self.review.claims() if row["analysis_id"] == job)

    def test_queued_snapshot_keeps_old_definition_after_catalog_changes(self):
        self.store.save(fields(name="Indicadores econômicos"), "Renomear tema.", self.entry["id"], 1)
        claim = self.analyze()
        self.assertEqual(claim["topic"], "Economia")
        self.assertEqual(claim["topic_annotation"]["definition"]["revision"], 1)
        self.assertEqual(claim["engine"]["topic_vocabulary"]["revision"], 1)
        self.assertEqual(self.review.source(1)["text"], claim["quote"])

    def test_catalog_changes_do_not_change_any_existing_claim_decision_or_source(self):
        before = self.dossiers.snapshot(self.cid)
        self.store.save(fields(name="Indicadores econômicos"), "Renomear para próximas análises.", self.entry["id"], 1)
        self.store.set_archived(self.entry["id"], 2, True, "Retirar das próximas análises.")
        after = self.dossiers.snapshot(self.cid)
        self.assertEqual(before, after)

    def test_human_revision_can_choose_alias_and_preserves_automatic_original(self):
        claim = self.analyze()
        values = {key: claim.get(key) for key in ("quote", "summary", "category", "topic")}
        values["topic"] = "ÍNDICE DE PRECOS"
        edited = self.review.revise_claim(claim["id"], 1, 1, values, "Conferir tema no ensaio.", topic_vocabulary=self.vocabulary)
        self.assertEqual(edited["topic"], "Economia")
        self.assertEqual(edited["topic_annotation"]["origin"], "operator")
        self.assertEqual(edited["topic_annotation"]["original"], "ÍNDICE DE PRECOS")
        self.assertEqual(edited["automatic_extraction"]["topic_annotation"]["original"], "inflacao")
        self.assertEqual(self.dossiers.snapshot(edited["id"])["revision"], 1)
        self.assertIsNone(self.dossiers.snapshot(edited["id"])["decision"])

    def test_edit_without_vocabulary_does_not_keep_a_match_for_a_different_topic(self):
        claim = self.analyze()
        values = {key: claim.get(key) for key in ("quote", "summary", "category", "topic")}
        values["topic"] = "Tema livre diferente"
        edited = self.review.revise_claim(claim["id"], 1, 1, values, "Outro tema informado.")
        self.assertNotIn("topic_annotation", edited)
        self.assertEqual(edited["automatic_extraction"]["topic_annotation"]["definition"]["name"], "Economia")

    def test_archived_theme_is_not_used_by_later_analysis_but_old_annotation_is_kept(self):
        old = self.analyze()
        self.store.set_archived(self.entry["id"], 1, True, "Retirar da pauta.")
        new = self.analyze(vocabulary=load_snapshot(self.root))
        self.assertEqual(new["topic"], "inflacao")
        self.assertEqual(new["topic_annotation"]["status"], "unmapped")
        self.assertEqual(next(row for row in self.review.claims() if row["id"] == old["id"])["topic_annotation"], old["topic_annotation"])

    def test_unknown_term_is_preserved_without_factual_or_semantic_guess(self):
        claim = self.analyze(topic="Economia e saúde")
        self.assertEqual(claim["topic"], "Economia e saúde")
        self.assertEqual(claim["topic_annotation"]["status"], "unmapped")
        self.assertEqual(claim["category"], "fato")
        self.assertIn("Fora do vocabulário", render(self.dossiers.snapshot(claim["id"])))

    def test_exports_include_only_used_definition_and_separate_original_theme(self):
        self.store.save(fields(name="Tema reservado", aliases=[], description="MARCADOR-PRIVADO-NAO-EXPORTAR"), "Outro tema.")
        claim = self.analyze(vocabulary=load_snapshot(self.root))
        data = snapshot(self.review)
        self.assertEqual(data["claims"][0]["topic_annotation"], claim["topic_annotation"])
        self.assertNotIn("MARCADOR-PRIVADO-NAO-EXPORTAR", json.dumps(data))
        row = next(csv_rows(data, "claims"))
        self.assertEqual(row["tema"], "Economia")
        self.assertEqual(row["tema_termo_original"], "inflacao")
        self.assertEqual(row["tema_estado"], "matched")
        self.assertEqual(row["vocabulario_revisao"], 2)

    def test_legacy_claims_keep_free_theme_without_invented_provenance(self):
        data = snapshot(self.review)
        self.assertNotIn("topic_annotation", data["claims"][0])
        self.assertIn("registro anterior", describe_topic(None))
        self.assertEqual(next(csv_rows(data, "claims"))["tema_estado"], "")

    def test_actual_queue_freezes_each_job_and_sends_only_text_to_worker(self):
        first = self.review.source(1)
        self.review.ingest({**first["original"], "paragraph_id": 2, "start": 4, "end": 7})
        process = Mock()
        process.is_alive.return_value = True
        process.terminate.side_effect = lambda: setattr(process.is_alive, "return_value", False)
        context = SimpleNamespace(Queue=queue.Queue, Event=threading.Event, Process=Mock(return_value=process))
        done = threading.Event()
        def emit(kind, data):
            if kind == "triage_update" and runner.pending == 0:
                done.set()
        item = {key: self.review.claims()[0].get(key) for key in ("quote", "summary", "category", "reason", "topic", "location", "period", "indicator", "comparison")}
        item["topic"] = "inflacao"
        items = validate_items([item], first["text"])
        with patch("factcheck.triage.mp.get_context", return_value=context):
            runner = TriageRunner(self.root, self.review, emit)
            try:
                runner.enqueue(1, force=True)
                job1, text1 = runner.inputs.get(timeout=5)
                self.assertEqual(text1, first["text"])
                self.assertEqual(self.review.analysis_states()[1, 1]["topic_vocabulary"], identity(self.vocabulary))
                self.store.save(fields(name="Indicadores econômicos"), "Renomear entre tarefas.", self.entry["id"], 1)
                runner.enqueue(2)
                runner.outputs.put((job1, items, None, {"name": "Motor fictício"}))
                job2, text2 = runner.inputs.get(timeout=5)
                self.assertEqual(text2, first["text"])
                runner.outputs.put((job2, items, None, {"name": "Motor fictício"}))
                self.assertTrue(done.wait(5))
                claims = {row["analysis_id"]: row for row in self.review.claims()}
                self.assertEqual(claims[job1]["topic"], "Economia")
                self.assertEqual(claims[job2]["topic"], "Indicadores econômicos")
                self.assertEqual(claims[job2]["topic_annotation"]["vocabulary"]["revision"], 2)
            finally:
                runner.cancel()


if __name__ == "__main__":
    unittest.main()
