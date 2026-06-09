from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any
import unittest

from resolve_integration.resolve_app.batch_builder import (
    BatchBuildDeps,
    build_from_manifest,
    filter_plans_by_transcript_query,
    semantic_match_score,
)
from resolve_integration.resolve_app.plans import ClipPlan


def fake_safe_call(obj: Any, method: str, *args: Any, default: Any = None) -> Any:
    try:
        return getattr(obj, method)(*args)
    except Exception:
        return default


def overlap_ratio(left_start: float, left_end: float, right_start: float, right_end: float) -> float:
    overlap = max(0.0, min(left_end, right_end) - max(left_start, right_start))
    shortest = max(0.001, min(left_end - left_start, right_end - right_start))
    return overlap / shortest


class FakeTimeline:
    def __init__(self, name: str) -> None:
        self.name = name

    def GetName(self) -> str:
        return self.name


class FakeMediaPool:
    def __init__(self) -> None:
        self.created: list[FakeTimeline] = []

    def CreateEmptyTimeline(self, name: str) -> FakeTimeline:
        timeline = FakeTimeline(name)
        self.created.append(timeline)
        return timeline


class ResolveBatchBuilderTests(unittest.TestCase):
    def test_semantic_match_score_uses_token_overlap(self) -> None:
        self.assertGreater(semantic_match_score("ace clutch", "huge ace clutch round"), 0.0)
        self.assertEqual(semantic_match_score("ace", "plant spike"), 0.0)

    def test_filter_plans_by_transcript_query_moves_plan_windows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            transcript_dir = root / "output" / "transcripts"
            transcript_dir.mkdir(parents=True)
            source = root / "vod.mp4"
            source.write_bytes(b"fake")
            (transcript_dir / "vod.json").write_text(
                json.dumps({"entries": [{"start": 42.0, "end": 45.0, "text": "massive clutch ace"}]}),
                encoding="utf-8",
            )
            plan = ClipPlan("clip1", "Clip 1", "", str(source), 0.0, 10.0, "auto")

            filtered = filter_plans_by_transcript_query(root, [plan], "clutch", 30, overlap_ratio)

            self.assertEqual(len(filtered), 1)
            self.assertEqual(filtered[0].start_seconds, 37.0)
            self.assertEqual(filtered[0].end_seconds, 67.0)

    def test_build_from_manifest_creates_timelines_and_master(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "vod.mp4"
            source.write_bytes(b"fake")
            manifest = root / "manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "batch_id": "batch_test",
                        "clips": [
                            {
                                "clip_id": "clip1",
                                "display_name": "Clip 1",
                                "source_path": str(source),
                                "start_seconds": 1.0,
                                "end_seconds": 3.0,
                                "seed_type": "auto",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            media_pool = FakeMediaPool()
            media_item = object()
            logs: list[str] = []
            deleted: list[str] = []
            appended: list[tuple[str, int, int, int]] = []

            def create_timeline_for_clip_with_preset(
                _project: Any,
                _media_pool: Any,
                name: str,
                _item: Any,
                start_frame: int,
                end_frame: int,
                _preset: dict[str, Any],
            ) -> FakeTimeline:
                appended.append((name, start_frame, end_frame, 1))
                return FakeTimeline(name)

            def append_clip_range(
                _media_pool: Any,
                timeline: FakeTimeline,
                _item: Any,
                start_frame: int,
                end_frame: int,
                track_index: int = 1,
                record_frame: int = 0,
            ) -> bool:
                appended.append((timeline.name, start_frame, end_frame, track_index + record_frame))
                return True

            deps = BatchBuildDeps(
                log=logs.append,
                load_pipeline_config=lambda _root: {},
                transcript_path_for_vod=lambda root_arg, vod_path: root_arg / "output" / "transcripts" / f"{vod_path.stem}.json",
                ensure_vertical_project_settings=lambda _project: None,
                ensure_batch_folder=lambda _pool, _batch_id: object(),
                ensure_playback_fps_60=lambda _project: True,
                fps_from_project=lambda _project: 60.0,
                safe_int_from_project_setting=lambda _project, _key, default: default,
                ensure_media_item=lambda _pool, _source: media_item,
                source_fps_for_media_item=lambda _item, _source, _project_fps: 30.0,
                delete_timeline_if_exists=lambda _project, _pool, name: deleted.append(name),
                create_timeline_for_clip_with_preset=create_timeline_for_clip_with_preset,
                log_timeline_diagnostics=lambda *_args: None,
                import_subtitles_to_timeline=lambda *_args, **_kwargs: (True, "ok"),
                append_clip_range=append_clip_range,
                queue_render_job=lambda *_args: True,
                safe_call=fake_safe_call,
            )

            batch_id, plan_map, timelines, warnings = build_from_manifest(
                root,
                object(),
                media_pool,
                manifest,
                root / "renders",
                "preset",
                {"mode": "single"},
                "",
                render_master=False,
                queue_render=False,
                deps=deps,
                overlap_ratio_from_ranges=overlap_ratio,
            )

            self.assertEqual(batch_id, "batch_test")
            self.assertEqual(list(plan_map), ["clip1"])
            self.assertEqual(len(timelines), 1)
            self.assertEqual(warnings, [])
            self.assertIn("batch_test__MASTER_REVIEW", deleted)
            self.assertEqual(appended[0], ("batch_test__Clip 1", 30, 90, 1))
            self.assertEqual(appended[1], ("batch_test__MASTER_REVIEW", 30, 90, 1))


if __name__ == "__main__":
    unittest.main()
