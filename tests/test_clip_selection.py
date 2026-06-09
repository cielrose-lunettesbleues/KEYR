from __future__ import annotations

import unittest

from short_editor.chapters import build_chapter_candidates_with_skips, compute_quota
from short_editor.models import Chapter, ClipCandidate, VodManifest
from short_editor.selection import select_non_overlapping_candidates


class ClipSelectionTests(unittest.TestCase):
    def test_chapter_zero_is_skipped(self) -> None:
        cfg = {
            "video": {
                "min_clip_seconds": 20,
                "max_clip_seconds": 60,
                "chapter_pre_roll_seconds": 10,
                "chapter_post_roll_seconds": 25,
            }
        }
        vod = VodManifest(
            source_path="vod.mp4",
            duration_seconds=120.0,
            width=1920,
            height=1080,
            fps=60.0,
            chapters=[
                Chapter(index=0, start_seconds=0.0, end_seconds=5.0, title="Start"),
                Chapter(index=1, start_seconds=30.0, end_seconds=40.0, title="Moment"),
            ],
        )

        clips, skips = build_chapter_candidates_with_skips(vod, cfg)

        self.assertEqual(len(clips), 1)
        self.assertEqual(clips[0].seed_type, "chapter")
        self.assertEqual(len(skips), 1)

    def test_quota_target_keeps_auto_clip_pressure(self) -> None:
        _, target, max_quota = compute_quota(
            7200,
            {"min_per_hour": 2.0, "target_per_hour": 2.5, "max_per_hour": 3.0},
        )

        self.assertEqual(target, 5)
        self.assertEqual(max_quota, 6)

    def test_clip_candidate_manifest_has_no_subtitle_path(self) -> None:
        clip = ClipCandidate(
            clip_id="clip_1",
            display_name="Chapitre 1",
            source_path="vod.mp4",
            start_seconds=10.0,
            end_seconds=40.0,
            mandatory=True,
            seed_type="chapter",
            score=1.0,
            reason="OBS chapter marker",
        )

        self.assertNotIn("subtitle_path", clip.to_dict())

    def test_select_non_overlapping_candidates_keeps_distinct_auto_clips(self) -> None:
        existing = [
            ClipCandidate("chapter", "Chapitre 1", "vod.mp4", 100.0, 140.0, True, "chapter", 1.0, "chapter")
        ]
        candidates = [
            ClipCandidate("auto_close", "Auto close", "vod.mp4", 120.0, 150.0, False, "fallback_discovery", 0.9, "auto"),
            ClipCandidate("auto_far", "Auto far", "vod.mp4", 260.0, 300.0, False, "fallback_discovery", 0.8, "auto"),
        ]

        selected = select_non_overlapping_candidates(existing, candidates, needed=1, overlap_threshold=0.4)

        self.assertEqual([clip.clip_id for clip in selected], ["auto_far"])


if __name__ == "__main__":
    unittest.main()
