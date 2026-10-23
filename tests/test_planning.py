import json
import unittest
from unittest.mock import patch

from factcheck.dossiers import render
from factcheck.exports import csv_rows, snapshot
from factcheck.planning import validate_plan
from factcheck.reporting import session_report
from factcheck.research import analyze
from factcheck.sources import search_plan
from factcheck.triage import TriageConfig
from tests import test_evidence as fixtures


def plan(**changes):
    return {"question": "Como o indicador evoluiu no período informado?", "scope": "falta_contexto", "period": "",
            "territory": "", "indicator": "", "comparison": "", "notes": "Conferir período, indicador e contexto.",
            "candidate_urls": [], **changes}


class PlanningTests(unittest.TestCase):
    setUp = fixtures.DossierTests.setUp
    tearDown = fixtures.DossierTests.tearDown
    add = fixtures.DossierTests.add

    def test_ai_draft_has_explicit_origin_without_changing_quote_or_human_review(self):
        source, claim = self.review.source(1), self.review.claims()[0]
        self.store.save_plan(self.cid, 0, plan(), origin="ai_draft")
        result = self.store.snapshot(self.cid)
        self.assertEqual(result["plan"]["origin"], "ai_draft")
        self.assertIn("Rascunho de IA", render(result))
        self.assertIsNone(result["decision"])
        self.assertIsNone(result["preliminary"])
        self.assertEqual(self.review.source(1), source)
        self.assertEqual(self.review.claims()[0], claim)

    def test_candidate_urls_remain_separate_from_collected_evidence_and_exports_protect_text(self):
        self.store.save_plan(self.cid, 0, plan(question="=Pergunta()", candidate_urls=["https://ibge.gov.br", "https://ibge.gov.br/"]))
        data = snapshot(self.review)
        self.assertEqual(data["sources"], [])
        self.assertEqual(data["dossiers"][0]["plan"]["candidate_urls"], ["https://ibge.gov.br/"])
        row = next(csv_rows(data, "claims"))
        self.assertTrue(row["plano_pergunta"].startswith("\t="))
        self.assertIn("ibge.gov.br", row["plano_urls_candidatas"])
        self.assertEqual(row["fontes_urls"], "[]")

    def test_material_plan_change_invalidates_decision_but_keeps_sources_and_history(self):
        self.add()
        self.store.decide(self.cid, 1, "inconclusiva", "Revisor fictício", "Falta contexto.")
        self.store.save_plan(self.cid, 2, plan())
        result = self.store.snapshot(self.cid)
        self.assertIsNone(result["decision"])
        self.assertIsNone(result["preliminary"])
        self.assertEqual(len(result["documents"]), 1)
        self.assertEqual(result["revision"], 3)
        with self.review.connection() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM history WHERE kind='human_decision'").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM history WHERE kind='check_plan_changed'").fetchone()[0], 1)

    def test_unchanged_plan_does_not_clear_later_decision_or_increment_revision(self):
        self.store.save_plan(self.cid, 0, plan())
        self.store.decide(self.cid, 1, "inconclusiva", "Revisor fictício", "Pendente.")
        before = self.store.snapshot(self.cid)
        self.assertFalse(self.store.save_plan(self.cid, 2, plan(question=" Como o indicador evoluiu no período informado? ")))
        self.assertEqual(self.store.snapshot(self.cid), before)

    def test_stale_editor_is_rejected_even_when_payload_matches(self):
        self.store.save_plan(self.cid, 0, plan())
        with self.assertRaisesRegex(ValueError, "dossiê mudou"):
            self.store.save_plan(self.cid, 0, plan())
        self.assertEqual(self.store.snapshot(self.cid)["revision"], 1)

    def test_plan_change_rejects_old_inflight_source_result(self):
        job = self.store.begin(self.cid, "collect")
        self.store.save_plan(self.cid, 0, plan())
        self.assertFalse(self.store.finish(job, fixtures.document()))
        result = self.store.snapshot(self.cid)
        self.assertEqual(result["documents"], [])
        self.assertEqual(result["jobs"][0]["status"], "stale")
        self.assertIsNotNone(result["plan"])

    def test_plan_survives_collection_preliminary_and_source_removal(self):
        self.store.save_plan(self.cid, 0, plan())
        saved = self.store.snapshot(self.cid)["plan"]
        self.add()
        self.assertEqual(self.store.snapshot(self.cid)["plan"], saved)
        self.assertEqual(self.store.states()[self.cid], "Fontes coletadas")
        job = self.store.begin(self.cid, "analyze")
        self.store.finish(job, fixtures.preliminary(), {"model": "fixture"})
        result = self.store.snapshot(self.cid)
        self.assertEqual(result["plan"], saved)
        self.store.remove_document(self.cid, result["revision"], "doc1", "Retirada fictícia.")
        self.assertEqual(self.store.snapshot(self.cid)["plan"], saved)
        self.assertEqual(self.store.states()[self.cid], "Planejamento salvo")

    def test_origin_revision_blocks_plan_edit_without_erasing_historical_draft(self):
        self.store.save_plan(self.cid, 0, plan(), origin="ai_draft")
        self.review.revise(1, 1, "Fala atualizada.", None)
        with self.assertRaises(ValueError):
            self.store.save_plan(self.cid, 1, plan())
        result = self.store.snapshot(self.cid)
        self.assertFalse(result["valid"])
        self.assertEqual(result["plan"]["origin"], "ai_draft")

    def test_operator_saving_ai_draft_records_transition_without_approving_transcription(self):
        self.store.save_plan(self.cid, 0, plan(), origin="ai_draft")
        self.assertTrue(self.store.save_plan(self.cid, 1, plan()))
        result = self.store.snapshot(self.cid)
        self.assertEqual(result["plan"]["origin"], "operator_input")
        self.assertEqual(result["revision"], 2)
        self.assertIsNone(result["decision"])
        self.assertFalse(self.review.source(1)["human_reviewed"])

    def test_missing_recuts_stay_blank_and_search_does_not_restore_old_model_guesses(self):
        draft = validate_plan(plan())
        self.assertEqual(draft["period"], "")
        queries = search_plan({"summary": "Resumo antigo 2025", "period": "2025", "indicator": "Indicador antigo"}, draft)
        self.assertTrue(all("2025" not in query and "Indicador antigo" not in query for query in queries))
        self.assertIn(draft["question"], queries[0])

    def test_invalid_shape_and_noninstitutional_urls_are_rejected(self):
        for candidate in (plan(scope=[]), plan(scope="desconhecido"), plan(question=""), plan(notes=""),
                          plan(candidate_urls=["https://127.0.0.1/"]), plan(candidate_urls=["https://gov.br.evil.invalid/"]),
                          plan(candidate_urls=["http://ibge.gov.br/"]), {**plan(), "verdict": "confirmada"}):
            with self.subTest(candidate=candidate), self.assertRaises(ValueError):
                validate_plan(candidate)

    def test_noncheckable_draft_requires_reason_and_does_not_discard_or_reclassify_claim(self):
        self.store.save_plan(self.cid, 0, plan(scope="nao_verificavel", question=""), origin="ai_draft")
        report = session_report(self.review)
        self.assertEqual(report["claims"]["detected_factual"], 1)
        self.assertEqual(report["claims"]["planning"]["possibly_not_checkable"], 1)
        self.assertEqual(report["claims"]["planning"]["ai_drafts"], 1)
        self.assertEqual(self.review.claims()[0]["category"], "fato")

    def test_unreviewed_draft_is_sent_as_data_and_downgrades_automatic_verdict(self):
        self.store.save_plan(self.cid, 0, plan(scope="pesquisavel"), origin="ai_draft")
        self.add()
        with patch("factcheck.research.GeminiModel") as model:
            model.return_value.generate.return_value = fixtures.preliminary()
            model.return_value.engine = {"model": "fixture"}
            result, _ = analyze(self.store.snapshot(self.cid), TriageConfig("gemini", "ficticia"), None)
        self.assertEqual(result["verdict"], "inconclusiva")
        material = json.loads(model.return_value.generate.call_args.args[1])
        self.assertEqual(material["check_plan"]["origin"], "ai_draft")
        self.assertIsNone(self.store.snapshot(self.cid)["decision"])

    def test_legacy_dossier_opens_with_no_plan_and_still_renders(self):
        result = self.store.snapshot(self.cid)
        self.assertIsNone(result["plan"])
        self.assertIn("ainda não registrados", render(result))

    def test_plan_count_includes_ambiguous_extractions_without_changing_factual_denominator(self):
        text = "Frase ambígua de teste."
        self.review.ingest({"paragraph_id": 2, "version": 1, "text": text, "source_text": text,
                            "start": 6, "end": 8, "closed": True, "parts": []})
        job, _ = self.review.begin_analysis(2)
        self.review.finish_analysis(job, [{"quote": text, "summary": text, "reason": "Exemplo fictício.", "category": "indefinida"}], {})
        cid = next(row["id"] for row in self.review.claims() if row["paragraph_id"] == 2)
        self.store.save_plan(cid, 0, plan(scope="nao_verificavel"), origin="ai_draft")
        result = session_report(self.review)
        self.assertEqual(result["claims"]["planning"]["recorded"], 1)
        self.assertEqual(result["claims"]["planning"]["possibly_not_checkable"], 1)
        self.assertEqual(result["claims"]["detected_factual"], 1)


if __name__ == "__main__":
    unittest.main()
