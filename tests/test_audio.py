import math
import struct
import unittest
import wave

import numpy as np

from factcheck.audio import AudioChunk, PCMChunker, RollingChunker, pcm_levels


class AudioTests(unittest.TestCase):
    def test_chunks_preserve_all_samples_with_overlap_and_tail(self):
        rate, channels = 100, 2
        original = b"".join(struct.pack("<hh", i, -i) for i in range(1325))
        chunker = PCMChunker(rate, channels)
        chunks = []
        for index in range(0, len(original), 148):
            chunks.extend(chunker.push(original[index:index + 148]))
        tail = chunker.finish()
        self.assertTrue(tail.final)
        chunks.append(tail)
        restored = bytearray()
        for chunk in chunks:
            covered = len(restored) // (channels * 2)
            already_seen = max(0, covered - chunk.start_frame) * channels * 2
            restored.extend(chunk.pcm[already_seen:])
        self.assertEqual(bytes(restored), original)
        self.assertEqual([item.start_frame for item in chunks], [0, 400, 800])
        self.assertAlmostEqual(chunks[-1].end, 13.25)
        self.assertIsNone(chunker.finish())

    def test_stopping_exactly_at_window_keeps_context_for_final_transcription(self):
        chunker = PCMChunker(100, 1)
        windows = chunker.push(bytes(600 * 2))
        self.assertEqual(len(windows), 1)
        tail = chunker.finish()
        self.assertEqual(tail.start_frame, 400)
        self.assertEqual(len(tail.pcm), 400)

    def test_incomplete_frame_is_rejected(self):
        with self.assertRaises(ValueError):
            PCMChunker(48000, 2).push(b"\x00\x01")

    def test_invalid_overlap_is_rejected(self):
        for overlap in (-1, 6, 7):
            with self.assertRaises(ValueError):
                PCMChunker(48000, 2, seconds=6, overlap=overlap)

    def test_levels_detect_silence_and_expected_sine_amplitude(self):
        self.assertEqual(pcm_levels(bytes(2048)), (-120.0, 0.0))
        samples = np.array([round(16384 * math.sin(2 * math.pi * i / 100))
                            for i in range(1000)], dtype="<i2")
        level, peak = pcm_levels(samples.tobytes())
        self.assertAlmostEqual(level, -9.031, places=2)
        self.assertAlmostEqual(peak, 0.5, places=3)

    def test_wav_payload_preserves_native_sample_rate_and_channels(self):
        chunk = AudioChunk(48000, bytes(48000 * 2 * 2), 48000, 2)
        with wave.open(chunk.wav_buffer(), "rb") as wav:
            self.assertEqual(wav.getparams()[:4], (2, 2, 48000, 48000))
            self.assertEqual(wav.readframes(48000), chunk.pcm)
        self.assertEqual((chunk.start, chunk.end), (1.0, 2.0))


class RollingChunkerTests(unittest.TestCase):
    def test_first_snapshot_arrives_after_two_seconds_then_every_three(self):
        chunker = RollingChunker(100, 1)
        chunks = chunker.push(bytes(1100 * 2))
        self.assertEqual([item.end for item in chunks], [2, 5, 8, 11])
        self.assertEqual([item.start for item in chunks], [0, 0, 2, 5])

    def test_overlapping_snapshots_match_original_and_tail_is_preserved(self):
        original = b"".join(struct.pack("<hh", i, -i) for i in range(1325))
        chunker = RollingChunker(100, 2)
        chunks = []
        for start in range(0, len(original), 148):
            chunks.extend(chunker.push(original[start:start + 148]))
        chunks.append(chunker.finish())
        restored = bytearray()
        for snapshot in chunks:
            first = snapshot.start_frame * 4
            self.assertEqual(snapshot.pcm, original[first:first + len(snapshot.pcm)])
            covered_frames = len(restored) // 4
            skip = max(0, covered_frames - snapshot.start_frame) * 4
            restored.extend(snapshot.pcm[skip:])
        self.assertEqual(bytes(restored), original)
        self.assertTrue(chunks[-1].final)
        self.assertEqual(chunks[-1].end, 13.25)
        self.assertIsNone(chunker.finish())

    def test_short_session_is_flushed_even_before_first_snapshot(self):
        chunker = RollingChunker(100, 1)
        self.assertEqual(chunker.push(bytes(100 * 2)), [])
        final = chunker.finish()
        self.assertEqual((final.start, final.end, final.final), (0, 1, True))
        with self.assertRaises(RuntimeError):
            chunker.push(bytes(100 * 2))

    def test_stop_at_snapshot_boundary_keeps_tail_even_with_long_cadence(self):
        chunker = RollingChunker(100, 1, update_seconds=6)
        chunker.push(bytes(200 * 2))
        final = chunker.finish()
        self.assertIsNotNone(final)
        self.assertEqual((final.start, final.end), (0, 2))

    def test_invalid_update_and_incomplete_frame_are_rejected(self):
        for update, first in ((0, 2), (7, 2), (3, 0), (3, 7)):
            with self.assertRaises(ValueError):
                RollingChunker(100, 2, update_seconds=update, first_seconds=first)
        with self.assertRaises(ValueError):
            RollingChunker(100, 2).push(bytes(2))


if __name__ == "__main__":
    unittest.main()
