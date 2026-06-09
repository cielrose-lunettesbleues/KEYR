from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from short_editor.captions import build_textplus_segments_for_clip


class TextPlusCaptionTests(unittest.TestCase):
    def test_build_textplus_segments_without_srt_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            transcript = Path(tmp_dir) / "vod.json"
            transcript.write_text(
                json.dumps(
                    {
                        "entries": [
                            {
                                "start": 10.0,
                                "end": 12.0,
                                "text": "Salut tout le monde",
                                "words": [
                                    {"start": 10.0, "end": 10.4, "word": "Salut"},
                                    {"start": 10.5, "end": 10.9, "word": "tout"},
                                    {"start": 11.0, "end": 11.5, "word": "le"},
                                    {"start": 11.5, "end": 12.0, "word": "monde"},
                                ],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            segments = build_textplus_segments_for_clip(
                transcript,
                9.0,
                13.0,
                {"preferred_words_per_chunk": 2, "max_words_per_chunk": 3, "remove_fillers": True},
            )

            self.assertGreaterEqual(len(segments), 1)
            self.assertTrue(all("text" in s and "start" in s and "end" in s for s in segments))
            self.assertFalse(any(Path(tmp_dir).glob("*.srt")))


if __name__ == "__main__":
    unittest.main()
