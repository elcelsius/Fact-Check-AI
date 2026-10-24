from copy import deepcopy
from dataclasses import asdict
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from factcheck.discovery import search_basis
from factcheck.dossiers import DossierStore, render
from factcheck.exports import snapshot
from factcheck.review import Debate, ReviewStore
from factcheck.source_library import FIELDS, SourceLibrary, filter_references, reference_snapshot, render_reference


def fields(**changes):
    return {"title": "Indicador fictício de inflação", "url": "https://ibge.gov.br/ensaio", "institution": "IBGE · ensaio",
            "topics": ["Economia", "Preços"], "methodology": "Série e metodologia a conferir no documento.",
            "periodicity": "Mensal, informada pelo operador.", "limits": "Conferir período, população e revisões.", "notes": "", **changes}


class SourceLibraryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.folder = Path(self.directory.name)
        self.library = SourceLibrary(self.folder / "library")

    def tearDown(self):
        self.directory.cleanup()

    def add(self, **changes):
        return self.library.save(fields(**changes), "Preparar referência para um ensaio.")

    def test_register_and_reopen_preserve_metadata_without_claiming_url_access(self):
        entry = self.add()
        self.assertEqual(entry["revision"], 1)
        self.assertEqual(SourceLibrary(self.folder / "library").get(entry["id"]), entry)
        self.assertNotIn("accessed_at", entry)
        self.assertNotIn("blocks", entry)
        self.assertIn("não confirma acesso à URL", render_reference(entry))
        self.assertEqual(self.library.history(entry["id"])[0]["current"], entry)

    def test_local_search_ignores_accents_and_combines_words_across_metadata(self):
        first = self.add(title="Estatísticas de Saúde", topics=["Saúde"], institution="Instituição fictícia", notes="Cobertura municipal")
        second = self.add(url="https://ibge.gov.br/outro", title="Outro indicador", topics=["Saude"])
        original = deepcopy([first, second])
        self.assertEqual(filter_references([first, second], "SAUDE MUNICIPAL"), [first])
        self.assertEqual(filter_references([first, second], topic="Saúde"), [first])
        self.assertEqual(filter_references([first, second], topic="Saude"), [second])
        self.assertEqual([first, second], original)

    def test_topic_normalization_preserves_case_and_deduplicates_exact_names(self):
        entry = self.add(topics=["  Saúde   pública  ", "Saúde pública", "saúde pública"])
        self.assertEqual(entry["topics"], ["Saúde pública", "saúde pública"])

    def test_edit_preserves_identity_creation_date_and_previous_version(self):
        first = self.add()
        updated = self.library.save(fields(title="Indicador revisado"), "Corrigir descrição.", first["id"], 1)
        self.assertEqual(updated["id"], first["id"])
        self.assertEqual(updated["created_at"], first["created_at"])
        self.assertEqual(updated["revision"], 2)
        history = self.library.history(first["id"])
        self.assertEqual(history[1]["previous"], first)
        self.assertEqual(history[1]["current"], updated)

    def test_duplicate_normalized_url_is_rejected_even_when_archived(self):
        first = self.add()
        self.library.set_archived(first["id"], 1, True, "Retirar da lista ativa.")
        with self.assertRaisesRegex(ValueError, "já está cadastrada"):
            self.add(url="https://IBGE.GOV.BR/ensaio#outro", title="Tentativa duplicada")
        self.assertEqual(len(self.library.entries()), 1)

    def test_archive_restore_and_edit_archived_preserve_all_history(self):
        first = self.add()
        archived = self.library.set_archived(first["id"], 1, True, "Fora da pauta.")
        self.assertEqual(filter_references([archived]), [])
        self.assertEqual(filter_references([archived], include_archived=True), [archived])
        edited = self.library.save(fields(notes="Conferir antes de restaurar."), "Adicionar observação.", first["id"], 2)
        self.assertTrue(edited["archived"])
        restored = self.library.set_archived(first["id"], 3, False, "Retomar pesquisa.")
        self.assertFalse(restored["archived"])
        self.assertEqual(len(self.library.history(first["id"])), 4)

    def test_stale_edit_archive_and_selection_cannot_use_an_old_catalog_revision(self):
        first = self.add()
        other = SourceLibrary(self.folder / "library")
        self.library.save(fields(notes="Nova observação."), "Atualizar cadastro.", first["id"], 1)
        with self.assertRaises(ValueError):
            other.save(fields(notes="Editor antigo."), "Outra alteração.", first["id"], 1)
        with self.assertRaises(ValueError):
            other.set_archived(first["id"], 1, True, "Estado antigo.")
        with self.assertRaises(ValueError):
            other.get(first["id"], 1, require_active=True)
        self.assertEqual(self.library.get(first["id"])["notes"], "Nova observação.")

    def test_noop_does_not_create_history_and_active_selection_rejects_archived(self):
        first = self.add()
        self.assertEqual(self.library.save(fields(), first["change_reason"], first["id"], 1), first)
        self.assertEqual(self.library.set_archived(first["id"], 1, False, "Sem mudança."), first)
        self.assertEqual(len(self.library.history(first["id"])), 1)
        archived = self.library.set_archived(first["id"], 1, True, "Arquivar.")
        with self.assertRaises(ValueError):
            self.library.get(first["id"], archived["revision"], require_active=True)

    def test_invalid_fields_topics_urls_and_reasons_do_not_write_records(self):
        invalid = [fields(title=""), fields(institution=" "), fields(url="http://ibge.gov.br/x"),
                   fields(url="https://ibge.gov.br.evil.example/x"), fields(url="https://127.0.0.1/"),
                   fields(notes="x" * 4001), fields(topics=[]), fields(topics="Economia"), fields(topics=["x"] * 9),
                   fields(topics=["x" * 101]), fields(topics=["Saúde\nEducação"]), fields(topics=["Saúde; Educação"]),
                   {**fields(), "api_key": "CAMPO-NAO-PERMITIDO"}]
        for values in invalid:
            with self.subTest(keys=list(values)), self.assertRaises(ValueError):
                self.library.save(values, "Cadastro inválido.")
        for reason in ("", None, "x" * 2001):
            with self.assertRaises(ValueError):
                self.library.save(fields(), reason)
        with self.assertRaises(ValueError):
            self.library.save(fields(), "Motivo.", expected_revision=True)
        self.assertEqual(self.library.entries(), [])

    def test_history_failure_rolls_back_the_catalog_change(self):
        first = self.add()
        with self.library.connection() as db:
            db.execute("CREATE TRIGGER fail_history BEFORE INSERT ON library_history BEGIN SELECT RAISE(ABORT,'ensaio'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.library.save(fields(title="Não deve persistir"), "Ensaio de rollback.", first["id"], 1)
        self.assertEqual(self.library.get(first["id"]), first)

    def test_snapshot_filters_unknown_fields_and_rejects_archived_or_invalid_identity(self):
        entry = self.add()
        self.assertNotIn("secret", reference_snapshot({**entry, "secret": "NAO-EXPORTAR"}))
        for change in ({"archived": True}, {"id": "invalid"}, {"revision": True}, {"updated_at": None}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                reference_snapshot({**entry, **change})


class LibraryDossierTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.project = Path(self.directory.name)
        self.library = SourceLibrary(self.project / "library")
        self.entry = self.library.save(fields(), "Preparar referência para pesquisa.")
        self.review, self.store, self.cid = self.session("sessao-a")

    def tearDown(self):
        self.directory.cleanup()

    def session(self, name):
        folder = self.project / name
        folder.mkdir()
        (folder / "session.json").write_text(json.dumps({"debate": asdict(Debate())}), encoding="utf8")
        review = ReviewStore(folder)
        text = "A inflação ficou em 3% em 2025."
        review.ingest({"paragraph_id": 1, "version": 1, "text": text, "source_text": text, "start": 0, "end": 3, "closed": True, "parts": []})
        job, _ = review.begin_analysis(1)
        review.finish_analysis(job, [{"quote": text, "summary": text, "category": "fato", "reason": "Indicador a conferir.",
            "topic": "Economia", "location": None, "period": "2025", "indicator": "3%", "comparison": None}], {})
        cid = review.claims()[0]["id"]
        return review, DossierStore(review), cid

    def basis(self, store=None, cid=None):
        data = (store or self.store).snapshot(cid or self.cid)
        return search_basis(data["claim"], data.get("plan"))

    def select(self):
        return self.store.record_library_reference(self.cid, self.basis(), self.entry, "inflação metodologia", "Economia")

    def test_same_catalog_reference_can_be_selected_independently_in_two_sessions(self):
        self.select()
        other_review, other, cid = self.session("sessao-b")
        other.record_library_reference(cid, self.basis(other, cid), self.entry)
        self.assertEqual(other.snapshot(cid)["library_references"][0]["reference"], self.entry)
        self.assertEqual(len(self.store.snapshot(self.cid)["library_references"]), 1)
        self.assertEqual(len(self.library.entries()), 1)

    def test_selection_does_not_change_decision_revision_or_create_evidence(self):
        self.store.decide(self.cid, 0, "inconclusiva", "Revisor fictício", "Faltam documentos.")
        before = self.store.snapshot(self.cid)
        self.select()
        after = self.store.snapshot(self.cid)
        self.assertEqual(after["revision"], before["revision"])
        self.assertEqual(after["decision"], before["decision"])
        self.assertEqual(after["documents"], [])
        self.assertTrue(after["library_references"][0]["current"])
        with self.assertRaisesRegex(ValueError, "Colete"):
            self.store.begin(self.cid, "analyze")
        self.assertIn("candidatas, não evidências", render(after))

    def test_repeated_selection_is_deduplicated_without_losing_lookup_context(self):
        first = self.select()
        self.assertEqual(self.select(), first)
        selected = self.store.snapshot(self.cid)["library_references"]
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["query"], "inflação metodologia")
        self.assertEqual(selected[0]["topic"], "Economia")

    def test_later_catalog_edit_or_archive_does_not_rewrite_the_selected_snapshot(self):
        self.select()
        self.library.save(fields(notes="Informação posterior."), "Atualização posterior.", self.entry["id"], 1)
        self.library.set_archived(self.entry["id"], 2, True, "Retirar da coleção ativa.")
        selected = self.store.snapshot(self.cid)["library_references"][0]
        self.assertEqual(selected["reference"], self.entry)
        self.assertTrue(selected["current"])

    def test_plan_change_marks_old_selection_historical_and_rejects_old_target(self):
        basis = self.basis()
        self.select()
        self.store.save_plan(self.cid, 0, {"question": "Qual o indicador nacional em 2025?", "scope": "pesquisavel", "period": "2025",
            "territory": "Brasil", "indicator": "IPCA", "comparison": "", "notes": "", "candidate_urls": []})
        self.assertFalse(self.store.snapshot(self.cid)["library_references"][0]["current"])
        with self.assertRaises(ValueError):
            self.store.record_library_reference(self.cid, basis, self.entry)

    def test_extraction_change_and_new_triage_do_not_transfer_old_selections(self):
        self.select()
        basis = self.basis()
        claim = self.review.claims()[0]
        item = {key: claim.get(key) for key in ("quote", "summary", "category", "topic")}
        item["topic"] = "Indicadores"
        self.review.revise_claim(self.cid, 1, 1, item, "Tema corrigido.")
        with self.assertRaises(ValueError):
            self.store.record_library_reference(self.cid, basis, self.entry)
        self.assertFalse(self.store.snapshot(self.cid)["library_references"][0]["current"])
        job, _ = self.review.begin_analysis(1, force=True)
        self.review.finish_analysis(job, [{key: claim.get(key) for key in ("quote", "summary", "category", "reason", "topic", "location", "period", "indicator", "comparison")}], {})
        new = next(value for value in self.review.claims() if value["id"] != self.cid)
        self.assertEqual(self.store.snapshot(new["id"])["library_references"], [])

    def test_corrected_source_rejects_selection_using_an_old_claim(self):
        basis = self.basis()
        source = self.review.source(1)
        self.review.revise(1, 1, source["text"] + " Correção.", None)
        with self.assertRaises(ValueError):
            self.store.record_library_reference(self.cid, basis, self.entry)
        self.assertEqual(self.store.snapshot(self.cid)["library_references"], [])

    def test_export_includes_only_selected_reference_and_never_the_whole_private_library(self):
        self.library.save(fields(url="https://ibge.gov.br/privada", notes="MARCADOR-DE-OUTRA-REFERENCIA"), "Outro cadastro.")
        self.select()
        data = snapshot(self.review)
        self.assertEqual(data["sources"], [])
        self.assertEqual(data["dossiers"][0]["library_references"][0]["reference"], self.entry)
        self.assertNotIn("MARCADOR-DE-OUTRA-REFERENCIA", json.dumps(data))

    def test_invalid_or_archived_reference_and_lookup_data_do_not_create_selection(self):
        for entry, query, topic in (({**self.entry, "archived": True}, "", None), (self.entry, "x" * 1001, None),
                                    (self.entry, "", "Tema ausente")):
            with self.assertRaises(ValueError):
                self.store.record_library_reference(self.cid, self.basis(), entry, query, topic)
        self.assertEqual(self.store.snapshot(self.cid)["library_references"], [])


if __name__ == "__main__":
    unittest.main()
