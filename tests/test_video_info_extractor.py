import unittest
from pathlib import Path
from unittest.mock import patch

import video_info_extractor as vie


class VideoInfoExtractorTests(unittest.TestCase):
    def test_parse_fraction(self):
        self.assertAlmostEqual(vie._parse_fraction("30000/1001"), 29.97002997, places=4)
        self.assertEqual(vie._parse_fraction("25"), 25.0)
        self.assertIsNone(vie._parse_fraction("a/b"))
        self.assertIsNone(vie._parse_fraction("1/0"))

    @patch("video_info_extractor._run_ffprobe")
    def test_extract_metadata(self, mock_probe):
        mock_probe.return_value = {
            "format": {
                "duration": "12.5",
                "size": "2048",
                "bit_rate": "1000000",
                "format_name": "mp4",
            },
            "streams": [
                {
                    "codec_type": "video",
                    "width": 1920,
                    "height": 1080,
                    "avg_frame_rate": "30/1",
                    "codec_name": "h264",
                }
            ],
        }
        meta = vie.extract_metadata(Path("demo.mp4"))
        self.assertEqual(meta.format_name, "mp4")
        self.assertEqual(meta.width, 1920)
        self.assertAlmostEqual(meta.fps, 30.0)

    def test_build_summary_without_key_moments(self):
        meta = vie.VideoMetadata(
            path="a.mp4",
            duration_seconds=10.0,
            size_bytes=1024,
            bit_rate=1200,
            format_name="mp4",
            width=1280,
            height=720,
            fps=25.0,
            codec="h264",
        )
        lines = vie.build_summary(meta, [])
        self.assertTrue(any("未检测到明显镜头切换" in line for line in lines))


if __name__ == "__main__":
    unittest.main()
