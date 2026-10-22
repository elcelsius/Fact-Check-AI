from types import SimpleNamespace
import unittest

from factcheck.audio import AudioChunk
from factcheck.transcription import TranscriptMerger


def chunk(start, seconds=6, final=False):
    return AudioChunk(start * 100, bytes(seconds * 100 * 2), 100, 1, final)


def segment(*words):
    return SimpleNamespace(words=[SimpleNamespace(start=start, end=end, word=text)
                                  for start, end, text in words])


class TranscriptMergerTests(unittest.TestCase):
    def test_overlap_is_committed_once_and_absolute_time_is_preserved(self):
        merger = TranscriptMerger()
        first = merger.consume(chunk(0), [segment((1, 2, "Olá"), (5, 5.5, " mundo"))])
        second = merger.consume(chunk(4), [segment((1, 1.5, " mundo"), (2, 3, " inteiro"))])
        self.assertEqual([item.text for item in first + second], ["Olá", "mundo inteiro"])
        self.assertEqual((second[0].start, second[0].end), (5, 7))

    def test_stop_flushes_last_second_without_repeating_committed_text(self):
        merger = TranscriptMerger()
        merger.consume(chunk(0), [segment((1, 2, "Primeira"), (5, 5.6, " última"))])
        tail = merger.consume(chunk(4, seconds=2, final=True), [segment((1, 1.6, " última"))])
        self.assertEqual([item.text for item in tail], ["última"])
        self.assertEqual(merger.committed_until, 6)

    def test_silence_advances_watermark_without_inventing_text(self):
        merger = TranscriptMerger()
        self.assertEqual(merger.consume(chunk(0), []), [])
        self.assertEqual(merger.committed_until, 5)

    def test_words_outside_recorded_audio_are_rejected(self):
        merger = TranscriptMerger()
        lines = merger.consume(chunk(0, final=True), [segment(
            (-1, 0, "inválida"), (1, 2, "Válida"), (6, 8, " inválida"))])
        self.assertEqual([item.text for item in lines], ["Válida"])

    def test_repeated_real_words_are_not_removed_by_text_matching(self):
        merger = TranscriptMerger()
        lines = merger.consume(chunk(0, final=True), [segment((1, 2, "Sim"), (2, 3, " sim"))])
        self.assertEqual(lines[0].text, "Sim sim")
        self.assertIsNone(lines[0].speaker)
        self.assertEqual(lines[0].review_status, "automatico_nao_revisado")


if __name__ == "__main__":
    unittest.main()
