from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any
import unittest

from resolve_integration.resolve_app.ui_feedback import (
    build_rating_rows,
    clip_rating_display_row,
    load_transcript_entries_for_feedback,
)


class FakeRating:
    def __init__(self, value: Any) -> None:
        self.value = value

    def get(self) -> Any:
        return self.value


class ResolveUiFeedbackTests(unittest.TestCase):
    def test_clip_rating_display_row_extracts_matched_terms(self) -> None:
        row = clip_rating_display_row(
            "batch1",
            {"clip_id": "c1", "display_name": "Clip One", "seed_type": "auto", "reason": "audio; matched=ace clutch"},
            0,
        )

        self.assertEqual(row["timeline_label"], "batch1__Clip One")
        self.assertEqual(row["matched_terms"], "ace clutch")
        self.assertIn("clip one", row["search_blob"])

    def test_clip_rating_display_row_marks_transcript_discovery(self) -> None:
        row = clip_rating_display_row("batch1", {"reason": "transcript_discovery relaxed"}, 2)

        self.assertEqual(row["clip_id"], "clip_2")
        self.assertEqual(row["matched_terms"], "transcript")

    def test_build_rating_rows_defaults_missing_rating_to_neutral(self) -> None:
        clips = [
            {"clip_id": "c1", "seed_type": "chapter", "reason": "ok", "start_seconds": 1, "end_seconds": 2},
            {"clip_id": "c2", "seed_type": "auto", "reason": "ok", "start_seconds": 3, "end_seconds": 4},
        ]

        rows = build_rating_rows("batch1", clips, {"c1": FakeRating(5)})

        self.assertEqual(rows[0]["rating"], "5")
        self.assertEqual(rows[1]["rating"], "3")
        self.assertEqual(rows[0]["batch_id"], "batch1")

    def test_load_transcript_entries_for_feedback_reads_first_clip_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            transcript_dir = root / "output" / "transcripts"
            transcript_dir.mkdir(parents=True)
            source = root / "vod.mp4"
            (transcript_dir / "vod.json").write_text(json.dumps({"entries": [{"text": "hello"}]}), encoding="utf-8")

            entries = load_transcript_entries_for_feedback(root, [{"source_path": str(source)}])

            self.assertEqual(entries, [{"text": "hello"}])


if __name__ == "__main__":
    unittest.main()
