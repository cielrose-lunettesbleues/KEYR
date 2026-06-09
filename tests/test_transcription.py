from __future__ import annotations

import tempfile
from pathlib import Path
import unittest

from short_editor.transcription import ensure_transcript


class TranscriptionTests(unittest.TestCase):
    def test_ensure_transcript_reports_cache_hit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir)
            vod_path = output_dir / "vod.mp4"
            transcript_path = output_dir / "vod.json"
            transcript_path.write_text('{"entries": []}\n', encoding="utf-8")
            events: list[tuple[str, int, int, str]] = []

            out = ensure_transcript(vod_path, {}, output_dir, progress_cb=lambda *args: events.append(args))

            self.assertEqual(out, transcript_path)
            self.assertEqual(events, [("Transcript", 100, 100, "Transcript déjà en cache: vod.json", {})])

    def test_ensure_transcript_cache_hit_supports_legacy_callback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir)
            vod_path = output_dir / "vod.mp4"
            transcript_path = output_dir / "vod.json"
            transcript_path.write_text('{"entries": []}\n', encoding="utf-8")
            events: list[tuple[str, int, int, str]] = []

            out = ensure_transcript(vod_path, {}, output_dir, progress_cb=lambda stage, current, total, detail: events.append((stage, current, total, detail)))

            self.assertEqual(out, transcript_path)
            self.assertEqual(events, [("Transcript", 100, 100, "Transcript déjà en cache: vod.json")])


if __name__ == "__main__":
    unittest.main()
