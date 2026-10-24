from copy import deepcopy
import unittest

from factcheck.queue_filters import QueueFilters, display_state, field_choices, filter_claims, is_current, sort_claims
from factcheck.priorities import priority_payload


class QueueFilterTests(unittest.TestCase):
    def setUp(self):
        self.sources = {1: {"revision": 1, "needs_rebase": False}, 2: {"revision": 1, "needs_rebase": False}}
        self.claims = [
            {"id": "a", "paragraph_id": 1, "revision": 1, "status": "aguardando_pesquisa", "category": "fato", "topic": "Saúde",
             "speaker": "Ana", "quote": "O número mudou.", "summary": "Mudança no indicador.", "context": "Série histórica municipal."},
            {"id": "b", "paragraph_id": 2, "revision": 1, "status": "fora_da_fila", "category": "opiniao", "topic": None,
             "speaker": None, "quote": "Acho bom.", "summary": "Opinião de teste."},
            {"id": "c", "paragraph_id": 1, "revision": 1, "status": "descartada", "category": "fato", "topic": "Saúde",
             "speaker": "Ana", "quote": "Registro descartado.", "summary": "Registro de teste."}]
        self.states = {}

    def ids(self, **fields):
        return [claim["id"] for claim in filter_claims(self.claims, self.sources, self.states, QueueFilters(**fields))]

    def test_text_search_ignores_accents_and_case_and_combines_words_across_context(self):
        self.assertEqual(self.ids(query="SAUDE historica"), ["a"])
        self.assertEqual(self.ids(query="opiniao"), ["b"])
        self.assertEqual(self.ids(query="série inexistente"), [])

    def test_multiple_filters_are_intersections_with_exact_participant_and_theme(self):
        self.assertEqual(self.ids(category="fato", scope="current", speaker="Ana", topic="Saúde"), ["a"])
        self.assertEqual(self.ids(speaker="ana"), [])
        self.assertEqual(self.ids(category="opiniao", topic="Saúde"), [])

    def test_unassigned_and_all_values_are_distinct_filters(self):
        self.assertEqual(self.ids(speaker="", topic=""), ["b"])
        self.assertEqual(self.ids(speaker=None), ["a", "b", "c"])
        options = field_choices([None, "Todos", "Não identificado", "Ana"], "Não identificado")
        self.assertIsNone(options["Todos"])
        self.assertEqual(options["Não identificado"], "")
        self.assertEqual(options["Todos (cadastrado)"], "Todos")

    def test_current_scope_and_historical_scope_do_not_revalidate_old_sources(self):
        self.assertEqual(self.ids(scope="current"), ["a", "b"])
        self.assertEqual(self.ids(scope="historical"), ["c"])
        for change in ({"revision": 2}, {"needs_rebase": True}, {"hidden_by": -1}, {"retired": True}):
            with self.subTest(change=change):
                before = self.sources[1]
                self.sources[1] = {**before, **change}
                self.assertFalse(is_current(self.claims[0], self.sources))
                self.assertIn("a", self.ids(scope="historical"))
                self.sources[1] = before

    def test_case_state_applies_only_to_current_claims_and_discard_has_precedence(self):
        self.states = {"a": "Revisão humana registrada", "c": "Revisão humana registrada"}
        self.assertEqual(self.ids(state="Revisão humana registrada"), ["a"])
        self.assertEqual(display_state(self.claims[2], self.sources, self.states), "Descartada")
        self.claims[0]["source_outdated"] = True
        self.assertEqual(self.ids(state="Revisão humana registrada"), [])
        self.assertEqual(self.ids(state="Análise desatualizada"), ["a"])

    def test_missing_source_is_historical_even_if_no_old_flag_was_saved(self):
        del self.sources[1]
        self.assertEqual(self.ids(scope="current"), ["b"])
        self.assertEqual(self.ids(scope="historical"), ["a", "c"])

    def test_filter_keeps_input_order_and_does_not_mutate_records(self):
        original = deepcopy((self.claims, self.sources, self.states))
        self.assertEqual(self.ids(category="fato"), ["a", "c"])
        self.assertEqual((self.claims, self.sources, self.states), original)

    def test_invalid_scope_is_rejected(self):
        with self.assertRaises(ValueError):
            self.ids(scope="desconhecido")

    def test_priority_filter_combines_with_existing_facets_and_defaults(self):
        self.claims[0]["priority"] = priority_payload(self.claims[0], {"revision": 1, "level": "high", "claim_revision": 1, "source_revision": 1})
        self.assertEqual(self.ids(priority="high", category="fato", scope="current"), ["a"])
        self.assertEqual(self.ids(priority="unset"), ["b", "c"])
        self.claims[0]["priority"]["needs_review"] = True
        self.claims[0]["priority"]["current"] = False
        self.assertEqual(self.ids(priority="high"), [])
        self.assertEqual(self.ids(priority="needs_review"), ["a"])
        with self.assertRaises(ValueError):
            self.ids(priority="unknown")

    def test_priority_order_keeps_old_priorities_after_current_claims_and_ties_by_time(self):
        for index, claim in enumerate(self.claims):
            claim.update(start=3-index, end=4-index)
        self.claims[1]["priority"] = priority_payload(self.claims[1], {"revision": 1, "level": "high", "claim_revision": 1, "source_revision": 1})
        self.claims[2]["priority"] = priority_payload(self.claims[2], {"revision": 1, "level": "high", "claim_revision": 1, "source_revision": 1}, False)
        original = deepcopy(self.claims)
        self.assertEqual([row["id"] for row in sort_claims(self.claims, self.sources, "priority")], ["b", "a", "c"])
        self.assertEqual([row["id"] for row in sort_claims(self.claims, self.sources, "chronological")], ["c", "b", "a"])
        self.assertEqual(sort_claims(self.claims, self.sources), self.claims)
        self.assertEqual(self.claims, original)
        with self.assertRaises(ValueError):
            sort_claims(self.claims, self.sources, "unknown")

    def test_priority_needing_review_does_not_outrank_a_current_normal_priority(self):
        for index, claim in enumerate(self.claims):
            claim.update(start=index, end=index+1)
        self.claims[0]["priority"] = priority_payload(self.claims[0], {"revision": 1, "level": "high", "claim_revision": 0, "source_revision": 1})
        self.claims[1]["priority"] = priority_payload(self.claims[1], {"revision": 1, "level": "normal", "claim_revision": 1, "source_revision": 1})
        self.assertEqual([row["id"] for row in sort_claims(self.claims, self.sources, "priority")], ["b", "a", "c"])

    def test_assignee_filter_combines_with_existing_fields_and_matches_exact_names(self):
        self.claims[0]["assignment"] = {"name": "Ana Silva", "needs_review": True}
        self.assertEqual(self.ids(assignee="Ana Silva", category="fato", scope="current"), ["a"])
        self.assertEqual(self.ids(assignee="ana silva"), [])
        self.assertEqual(self.ids(assignee=""), ["b", "c"])
        self.assertEqual(self.ids(assignee=None), ["a", "b", "c"])

    def test_assignee_named_like_a_filter_marker_is_not_confused_with_unassigned(self):
        self.claims[0]["assignment"] = {"name": "Sem responsável"}
        options = field_choices(["Sem responsável", "Todos"], "Sem responsável")
        self.assertEqual(self.ids(assignee=options["Sem responsável"]), ["b", "c"])
        self.assertEqual(self.ids(assignee=options["Sem responsável (cadastrado)"]), ["a"])


if __name__ == "__main__":
    unittest.main()
