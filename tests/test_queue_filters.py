from copy import deepcopy
import unittest

from factcheck.queue_filters import QueueFilters, display_state, field_choices, filter_claims, is_current


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


if __name__ == "__main__":
    unittest.main()
