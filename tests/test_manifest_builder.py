from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from short_editor.manifest_builder import generate_manifest_for_vod
from short_editor.models import Chapter, ClipCandidate, VodManifest


class ManifestBuilderTests(unittest.TestCase):
    def test_generate_manifest_keeps_auto_clips_without_subtitle_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            vod = root / "input" / "vod.mp4"
            vod.parent.mkdir(parents=True)
            vod.write_text("", encoding="utf-8")
            cfg = {
                "pipeline_version": "test",
                "video": {
                    "min_clip_seconds": 20,
                    "preferred_clip_seconds": 40,
                    "max_clip_seconds": 60,
                    "chapter_pre_roll_seconds": 5,
                    "chapter_post_roll_seconds": 25,
                },
                "quota": {"min_per_hour": 2.0, "target_per_hour": 2.5, "max_per_hour": 3.0},
                "audio": {"trim_dead_air": {"enabled": False}},
                "captions": {"enabled": False},
            }
            manifest = VodManifest(
                source_path=str(vod),
                duration_seconds=7200.0,
                width=1920,
                height=1080,
                fps=60.0,
                chapters=[Chapter(index=1, start_seconds=100.0, end_seconds=110.0, title="chapter")],
            )
            auto = ClipCandidate(
                clip_id="fallback_0000",
                display_name="fallback_0000",
                source_path=str(vod),
                start_seconds=500.0,
                end_seconds=540.0,
                mandatory=False,
                seed_type="fallback_discovery",
                score=0.9,
                reason="auto",
            )

            with patch("short_editor.manifest_builder.probe_vod", return_value=manifest), patch(
                "short_editor.manifest_builder.discover_fallback_candidates", return_value=[auto]
            ), patch("short_editor.manifest_builder.trim_dead_air_on_boundaries", return_value=[]):
                manifest_path = generate_manifest_for_vod(root, vod, cfg, generate_subtitles=False)

            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(data["clips"][0]["display_name"], "Chapitre 1")
            self.assertEqual(data["clips"][1]["display_name"], "Auto 1")
            self.assertNotIn("subtitle_path", data["clips"][0])
            self.assertEqual(data["quota_summary"][0]["fallback_added"], 1)


if __name__ == "__main__":
    unittest.main()
