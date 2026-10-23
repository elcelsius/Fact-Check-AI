import unittest

from factcheck.timeline import describe_time, parse_video_position, timestamp, validate_video_position, video_range


class TimelineTests(unittest.TestCase):
    def test_position_accepts_minutes_hours_zero_and_no_reference(self):
        for text, expected in [("12:30", 750), ("01:12:30", 4350), ("75:00", 4500),
                               ("0:00", 0), (" 00:00:00 ", 0), ("", None), ("  ", None),
                               ("999:59:59", 3599999)]:
            with self.subTest(text=text):
                self.assertEqual(parse_video_position(text), expected)

    def test_invalid_position_is_rejected_instead_of_silently_normalized(self):
        for text in ["12", "12:3", "12:60", "01:60:00", "-01:30", "1.5:00", "00:00:00:00",
                     "00:00,2", "1000:00:00", "abc", "１２:３０"]:
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_video_position(text)
        for value in [True, -1, 1.5, float("nan"), "12:30", 3600000]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_video_position(value)

    def test_video_offset_crosses_hour_boundary_without_changing_capture_range(self):
        source = {"start": 29.9, "end": 31.2}
        original = source.copy()
        self.assertEqual(video_range(source, 3570), "00:59:59 → 01:00:01")
        self.assertEqual(describe_time(source), "captura: 29.9–31.2 s")
        self.assertEqual(describe_time(source, 3570), "Vídeo (ref.): 00:59:59 → 01:00:01 · captura: 29.9–31.2 s")
        self.assertEqual(source, original)
        self.assertEqual(timestamp(360000), "100:00:00")


if __name__ == "__main__":
    unittest.main()
