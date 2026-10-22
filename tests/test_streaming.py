from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

import numpy as np

from factcheck.audio import AudioChunk, PCMChunker
from factcheck.streaming import StreamingTranscriber


class StreamingTests(unittest.TestCase):
    def setUp(self):
        self.engine = StreamingTranscriber(Path("unused"))
        self.engine.stream = Mock()
        self.engine.recognizer = Mock()
        self.engine.recognizer.is_ready.return_value = False
        self.engine.recognizer.is_endpoint.return_value = False
        self.result = SimpleNamespace(text="", start_time=0.0, timestamps=[])
        self.engine.recognizer.get_result_all.side_effect = lambda stream: self.result

    @staticmethod
    def chunk(start=0, channels=1, rate=100):
        return AudioChunk(start, b"\x00\x20" * (20 * channels), rate, channels)

    def test_revised_hypothesis_is_replaced_until_endpoint(self):
        self.result.text = "O número foi dez"
        self.assertEqual(self.engine.transcribe(self.chunk()), [])
        self.assertEqual(self.engine.partial["text"], "O número foi dez")
        self.result.text = "O número foi doze"
        self.assertEqual(self.engine.transcribe(self.chunk(20)), [])
        self.assertEqual(self.engine.partial["text"], "O número foi doze")
        self.engine.recognizer.is_endpoint.return_value = True
        lines = self.engine.transcribe(self.chunk(40))
        self.assertEqual([line.text for line in lines], ["O número foi doze"])
        self.assertEqual(lines[0].review_status, "automatico_nao_revisado")
        self.assertEqual(self.engine.partial["text"], "")
        self.engine.recognizer.reset.assert_called_once()

    def test_stereo_downmix_keeps_original_rate_for_stateful_resampling(self):
        pcm = np.array([32767, -32767, 8192, 8192], dtype="<i2").tobytes()
        self.engine.transcribe(AudioChunk(0, pcm, 48000, 2))
        rate, samples = self.engine.stream.accept_waveform.call_args.args
        self.assertEqual(rate, 48000)
        np.testing.assert_allclose(samples, [0, 0.25])
        self.assertEqual(self.engine.received_frames, 2)

    def test_absolute_timestamps_survive_endpoint_and_are_clamped_to_audio(self):
        self.engine.transcribe(self.chunk())
        self.result = SimpleNamespace(text="A fala", start_time=0.1, timestamps=[0.05, 0.08])
        self.engine.recognizer.is_endpoint.return_value = True
        line = self.engine.transcribe(self.chunk(20))[0]
        self.assertAlmostEqual(line.start, 0.15)
        self.assertAlmostEqual(line.end, 0.26)
        self.result = SimpleNamespace(text="Cauda", start_time=0.3, timestamps=[0.1, 0.8])
        line = self.engine.transcribe(self.chunk(40))[0]
        self.assertAlmostEqual(line.start, 0.4)
        self.assertEqual(line.end, 0.6)

    def test_finish_flushes_only_once_and_uses_input_rate(self):
        self.result.text = "Última frase"
        self.result.timestamps = [0.1, 0.9]
        self.engine.transcribe(self.chunk(rate=22050))
        lines = self.engine.finish()
        self.assertEqual(lines[0].text, "Última frase")
        self.assertLessEqual(lines[0].end, 20 / 22050 + 0.001)
        rate, samples = self.engine.stream.accept_waveform.call_args.args
        self.assertEqual(rate, 22050)
        self.assertEqual(len(samples), 22050)
        self.assertEqual(self.engine.finish(), [])
        with self.assertRaises(RuntimeError):
            self.engine.transcribe(self.chunk(20, rate=22050))

    def test_gap_overlap_or_format_change_is_rejected_before_native_call(self):
        for chunk in [self.chunk(21), self.chunk(19), self.chunk(20, rate=200),
                      self.chunk(20, channels=2)]:
            with self.subTest(chunk=chunk):
                self.setUp()
                self.engine.transcribe(self.chunk())
                with self.assertRaises(ValueError):
                    self.engine.transcribe(chunk)
                self.assertEqual(self.engine.stream.accept_waveform.call_count, 1)

    def test_nonoverlapping_packets_preserve_every_sample_including_short_tail(self):
        pcm = np.arange(43, dtype="<i2").tobytes()
        chunker = PCMChunker(100, 1, seconds=0.2, overlap=0)
        chunks = chunker.push(pcm[:26]) + chunker.push(pcm[26:])
        chunks.append(chunker.finish())
        self.assertEqual([chunk.start_frame for chunk in chunks], [0, 20, 40])
        self.assertEqual(b"".join(chunk.pcm for chunk in chunks), pcm)
        self.assertTrue(chunks[-1].final)


if __name__ == "__main__":
    unittest.main()
