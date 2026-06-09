from __future__ import annotations

from pathlib import Path
from typing import Any
import unittest

from resolve_integration.resolve_app.silence_cut import (
    create_silence_cut_timeline,
    detect_audible_segments_for_silence_cut,
)


def fake_safe_call(obj: Any, method: str, *args: Any, default: Any = None) -> Any:
    try:
        return getattr(obj, method)(*args)
    except Exception:
        return default


class FakeTimeline:
    def __init__(self, name: str) -> None:
        self.name = name
        self.fps_forced = False
        self.appended: list[tuple[int, int, int, dict[str, Any]]] = []


class FakeMediaPool:
    def __init__(self) -> None:
        self.created: list[FakeTimeline] = []

    def CreateEmptyTimeline(self, name: str) -> FakeTimeline:
        timeline = FakeTimeline(name)
        self.created.append(timeline)
        return timeline


class ResolveSilenceCutTests(unittest.TestCase):
    def test_detect_audible_segments_removes_middle_silence(self) -> None:
        energies = [
            (0.0, 1.0),
            (0.2, 1.0),
            (0.4, 1.0),
            (0.6, 0.01),
            (0.8, 0.01),
            (1.0, 0.01),
            (1.2, 0.01),
            (1.4, 1.0),
            (1.6, 1.0),
            (1.8, 1.0),
        ]
        cfg = {
            "audio": {
                "silence_cut": {
                    "min_silence_seconds": 0.25,
                    "padding_seconds": 0.05,
                    "merge_gap_seconds": 0.08,
                    "min_segment_seconds": 0.2,
                }
            }
        }

        segments, stats = detect_audible_segments_for_silence_cut(energies, 0.0, 2.0, cfg, Path.cwd())

        self.assertEqual(len(segments), 2)
        self.assertGreater(stats["removed_seconds"], 0.5)
        self.assertEqual(stats["cuts"], 1.0)

    def test_detect_audible_segments_keeps_clip_when_removed_too_short(self) -> None:
        energies = [(0.0, 1.0), (0.2, 0.01), (0.4, 1.0), (0.6, 1.0)]
        cfg = {"audio": {"silence_cut": {"min_silence_seconds": 0.55}}}

        segments, stats = detect_audible_segments_for_silence_cut(energies, 0.0, 0.6, cfg, Path.cwd())

        self.assertEqual(segments, [(0.0, 0.6)])
        self.assertEqual(stats["cuts"], 0.0)

    def test_create_silence_cut_timeline_appends_valid_segments(self) -> None:
        media_pool = FakeMediaPool()
        media_item = object()
        deleted: list[str] = []

        def ensure_media_item(_media_pool: Any, _source_path: Path) -> Any:
            return media_item

        def fps_from_project(_project: Any) -> float:
            return 60.0

        def source_fps_for_media_item(_media_item: Any, _source_path: Path, _project_fps: float) -> float:
            return 30.0

        def delete_timeline_if_exists(_project: Any, _media_pool: Any, timeline_name: str) -> None:
            deleted.append(timeline_name)

        def force_timeline_fps_60(_project: Any, timeline: FakeTimeline) -> None:
            timeline.fps_forced = True

        def append_segment(
            _media_pool: Any,
            timeline: FakeTimeline,
            _media_item: Any,
            start_frame: int,
            end_frame: int,
            record_frame: int,
            preset: dict[str, Any],
        ) -> None:
            timeline.appended.append((start_frame, end_frame, record_frame, preset))

        timeline, warnings = create_silence_cut_timeline(
            Path.cwd(),
            object(),
            media_pool,
            Path("vod.mp4"),
            "Cut",
            [(1.0, 2.0), (3.0, 3.0), (4.0, 4.5)],
            {"mode": "single"},
            ensure_media_item,
            fps_from_project,
            source_fps_for_media_item,
            delete_timeline_if_exists,
            force_timeline_fps_60,
            append_segment,
            fake_safe_call,
        )

        self.assertIsNotNone(timeline)
        self.assertEqual(deleted, ["Cut"])
        self.assertTrue(timeline.fps_forced)  # type: ignore[union-attr]
        self.assertEqual(timeline.appended[0][:3], (30, 60, 0))  # type: ignore[union-attr]
        self.assertEqual(timeline.appended[1][:3], (120, 135, 60))  # type: ignore[union-attr]
        self.assertEqual(warnings, ["Segment ignoré: 3.00-3.00s"])


if __name__ == "__main__":
    unittest.main()
