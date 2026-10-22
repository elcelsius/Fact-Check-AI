import unittest

from factcheck.paragraphs import ParagraphAssembler, ParagraphConfig, complete_thought
from factcheck.transcription import TranscriptLine


class ParagraphTests(unittest.TestCase):
    def test_breathing_pause_keeps_sentences_together_and_long_pause_opens_paragraph(self):
        assembler = ParagraphAssembler()
        assembler.add(TranscriptLine(0, 2, "criamos novas vagas"), 1)
        update = assembler.add(TranscriptLine(2.4, 4, "a renda cresceu no estado"), 2)[-1]
        self.assertEqual(update["paragraph_id"], 1)
        self.assertEqual(update["text"], "Criamos novas vagas. A renda cresceu no estado.")
        updates = assembler.add(TranscriptLine(6, 8, "a produção aumentou neste ano"), 3)
        self.assertEqual([entry["paragraph_id"] for entry in updates], [1, 2])
        self.assertTrue(updates[0]["closed"])
        self.assertEqual(updates[1]["start_reason"], "pausa_e_conclusao")

    def test_location_or_period_complement_stays_with_claim_even_after_long_pause(self):
        assembler = ParagraphAssembler()
        assembler.add(TranscriptLine(0, 2, "criamos vinte mil empregos"), 1)
        update = assembler.add(TranscriptLine(4, 6, "no estado entre janeiro e junho deste ano"), 2)[-1]
        self.assertEqual(update["paragraph_id"], 1)
        self.assertEqual(update["text"], "Criamos vinte mil empregos no estado entre janeiro e junho deste ano.")
        self.assertEqual(update["source_sequences"], [1, 2])

    def test_incomplete_comparison_and_negation_are_never_split_by_pause(self):
        for before, after in [("a inflação caiu de oito para", "seis por cento"),
                              ("o candidato disse que não", "houve queda neste ano"),
                              ("o número de beneficiários foi", "vinte mil pessoas"),
                              ("a apresentadora está concorrendo", "a influenciadora de opinião")]:
            with self.subTest(before=before):
                assembler = ParagraphAssembler()
                assembler.add(TranscriptLine(0, 3, before), 1)
                update = assembler.add(TranscriptLine(6, 8, after), 2)[-1]
                self.assertEqual(update["paragraph_id"], 1)
                self.assertEqual(update["source_text"], before + " " + after)

    def test_numeric_percentage_is_kept_and_can_complete_a_sentence(self):
        self.assertTrue(complete_thought("a taxa caiu para 3,5%"))
        self.assertFalse(complete_thought("a taxa caiu para"))

    def test_irregular_verb_preserves_required_complement(self):
        self.assertTrue(complete_thought("o sistema mantém a decisão final com uma pessoa"))
        self.assertFalse(complete_thought("o sistema mantém"))

    def test_explicit_topic_transition_and_known_speaker_change_open_paragraphs(self):
        assembler = ParagraphAssembler()
        assembler.add(TranscriptLine(0, 2, "a produção aumentou neste ano", speaker="A"), 1)
        update = assembler.add(TranscriptLine(2.2, 5, "quanto à saúde criamos novas vagas", speaker="A"), 2)[-1]
        self.assertEqual(update["start_reason"], "transicao_explicita_de_assunto")
        update = assembler.add(TranscriptLine(5.1, 7, "eu discordo", speaker="B"), 3)[-1]
        self.assertEqual(update["start_reason"], "troca_de_falante")
        self.assertEqual(update["speaker"], "B")

    def test_soft_limit_waits_for_safe_boundary_instead_of_cutting_complement(self):
        assembler = ParagraphAssembler(ParagraphConfig(soft_seconds=5))
        assembler.add(TranscriptLine(0, 6, "a renda cresceu"), 1)
        update = assembler.add(TranscriptLine(6.1, 8, "no estado"), 2)[-1]
        self.assertEqual(update["paragraph_id"], 1)
        update = assembler.add(TranscriptLine(8.1, 10, "nós criamos novas vagas"), 3)[-1]
        self.assertEqual(update["paragraph_id"], 2)
        self.assertEqual(update["start_reason"], "limite_suave_apos_ideia")

    def test_source_words_numbers_and_qualifiers_are_preserved_in_every_revision(self):
        assembler = ParagraphAssembler()
        first = TranscriptLine(0, 3, "em 2025 o IBGE registrou 3,5% no Brasil")
        saved = assembler.add(first, 1)[0]
        assembler.add(TranscriptLine(3.3, 4, "segundo os dados preliminares"), 2)
        self.assertEqual(saved["source_text"], first.text)
        self.assertEqual(saved["source_sequences"], [1])
        self.assertEqual(saved["parts"][0]["text"], first.text)
        self.assertEqual(saved["version"], 1)
        final = assembler.finish("cancelamento")[0]
        self.assertEqual(final["end_reason"], "cancelamento")
        self.assertIn("3,5%", final["text"])
        self.assertIn("IBGE", final["text"])
        self.assertEqual(final["review_status"], "automatico_nao_revisado")
        self.assertEqual(assembler.finish(), [])

    def test_incomplete_end_is_kept_visible_without_suggesting_a_full_stop(self):
        assembler = ParagraphAssembler()
        assembler.add(TranscriptLine(0, 3, "a renda aumentou porque"), 1)
        final = assembler.finish()[0]
        self.assertFalse(final["thought_complete_hint"])
        self.assertEqual(final["text"], "A renda aumentou porque")

    def test_pause_is_configurable_and_invalid_values_are_rejected(self):
        assembler = ParagraphAssembler(ParagraphConfig(pause_seconds=2))
        assembler.add(TranscriptLine(0, 2, "criamos novas vagas"), 1)
        self.assertEqual(assembler.add(TranscriptLine(3.6, 5, "a renda cresceu"), 2)[-1]["paragraph_id"], 1)
        for value in [float("nan"), float("inf"), 0, 0.5, 6]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                ParagraphConfig(pause_seconds=value)

    def test_short_fragments_ellipsis_and_abbreviations_are_not_treated_as_complete(self):
        for text in ["no estado", "porque", "foram vinte mil", "a renda aumentou...", "segundo o dr."]:
            with self.subTest(text=text):
                self.assertFalse(complete_thought(text))


if __name__ == "__main__":
    unittest.main()
