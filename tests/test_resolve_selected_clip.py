from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any

from resolve_integration.resolve_app.selected_clip import selected_clip_subtitle_context


def fake_safe_call(obj: Any, method: str, *args: Any, default: Any = None, required: bool = False) -> Any:
    try:
        return getattr(obj, method)(*args)
    except Exception:
        if required:
            raise
        return default


class FakeMediaItem:
    def __init__(self, path: Path) -> None:
        self.path = path

    def GetClipProperty(self) -> dict[str, Any]:
        return {"File Path": str(self.path), "FPS": "60"}

    def GetName(self) -> str:
        return self.path.name


class FakeTimelineItem:
    def __init__(self, media_item: FakeMediaItem, start: int = 0, end: int = 60, source_start: int | None = 0, source_end: int | None = 60) -> None:
        self.media_item = media_item
        self.start = start
        self.end = end
        self.source_start = source_start
        self.source_end = source_end

    def GetMediaPoolItem(self) -> FakeMediaItem:
        return self.media_item

    def GetClipProperty(self) -> dict[str, Any]:
        return self.media_item.GetClipProperty()

    def GetName(self) -> str:
        return "timeline item"

    def GetStart(self) -> int:
        return self.start

    def GetEnd(self) -> int:
        return self.end

    def GetSourceStartFrame(self) -> int | None:
        return self.source_start

    def GetSourceEndFrame(self) -> int | None:
        return self.source_end

    def GetProperty(self, key: str | None = None) -> Any:
        props = {"Source Start": self.source_start, "Source End": self.source_end}
        if key is None:
            return props
        return props.get(key)


class FakeTimeline:
    def __init__(self, name: str = "Timeline") -> None:
        self.name = name
        self.current_item: FakeTimelineItem | None = None
        self.items: dict[int, list[FakeTimelineItem]] = {}
        self.mark_in_out: dict[str, Any] | None = None

    def GetCurrentVideoItem(self) -> FakeTimelineItem | None:
        return self.current_item

    def GetTrackCount(self, track_type: str) -> int:
        if track_type != "video" or not self.items:
            return 0
        return max(self.items)

    def GetItemListInTrack(self, track_type: str, track_index: int) -> list[FakeTimelineItem]:
        if track_type != "video":
            return []
        return self.items.get(track_index, [])

    def GetCurrentFrame(self) -> int:
        return 10

    def GetName(self) -> str:
        return self.name

    def GetStartFrame(self) -> int:
        return 0

    def GetMarkInOut(self) -> dict[str, Any] | None:
        return self.mark_in_out


class FakeMediaPool:
    def __init__(self) -> None:
        self.selected: list[FakeMediaItem] = []

    def GetSelectedClips(self) -> list[FakeMediaItem]:
        return self.selected


class FakeProject:
    def __init__(self, timeline: FakeTimeline, media_pool: FakeMediaPool) -> None:
        self.timeline = timeline
        self.media_pool = media_pool

    def GetCurrentTimeline(self) -> FakeTimeline:
        return self.timeline

    def GetMediaPool(self) -> FakeMediaPool:
        return self.media_pool

    def GetSetting(self, key: str) -> str:
        return "60" if key == "timelineFrameRate" else ""


class FakeProjectManager:
    def __init__(self, project: FakeProject) -> None:
        self.project = project

    def GetCurrentProject(self) -> FakeProject:
        return self.project


class FakeResolve:
    def __init__(self, project: FakeProject) -> None:
        self.project = project

    def GetProjectManager(self) -> FakeProjectManager:
        return FakeProjectManager(self.project)


def fps_from_project(_project: Any) -> int:
    return 60


def source_fps_for_media_item(_media_item: Any, _source_path: Path, _fallback_fps: int) -> float:
    return 60.0


class ResolveSelectedClipTests(unittest.TestCase):
    def test_context_from_current_timeline_item(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            source = Path(tmp_dir) / "vod.mp4"
            source.write_text("", encoding="utf-8")
            timeline = FakeTimeline()
            timeline.current_item = FakeTimelineItem(FakeMediaItem(source), source_start=120, source_end=300)
            media_pool = FakeMediaPool()
            logs: list[str] = []

            ok, message, ctx = selected_clip_subtitle_context(
                FakeResolve(FakeProject(timeline, media_pool)), fake_safe_call, logs.append, fps_from_project, source_fps_for_media_item
            )

            self.assertTrue(ok)
            self.assertEqual(message, "ok")
            self.assertEqual(ctx["source_path"], str(source))
            self.assertEqual(ctx["clip_start"], 2.0)
            self.assertEqual(ctx["clip_end"], 5.0)

    def test_context_from_selected_media_and_timeline_range(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            source = Path(tmp_dir) / "vod.mp4"
            source.write_text("", encoding="utf-8")
            timeline = FakeTimeline()
            timeline.mark_in_out = {"in": 60, "out": 180}
            media_pool = FakeMediaPool()
            media_pool.selected = [FakeMediaItem(source)]

            ok, _, ctx = selected_clip_subtitle_context(
                FakeResolve(FakeProject(timeline, media_pool)), fake_safe_call, lambda _msg: None, fps_from_project, source_fps_for_media_item
            )

            self.assertTrue(ok)
            self.assertEqual(ctx["clip_start"], 1.0)
            self.assertEqual(ctx["clip_end"], 3.0)

    def test_context_from_silence_cut_timeline_segments(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            source = Path(tmp_dir) / "vod.mp4"
            source.write_text("", encoding="utf-8")
            media_item = FakeMediaItem(source)
            timeline = FakeTimeline("Short__silence_cut")
            timeline.items[1] = [
                FakeTimelineItem(media_item, start=0, end=60, source_start=120, source_end=180),
                FakeTimelineItem(media_item, start=60, end=120, source_start=240, source_end=300),
            ]
            media_pool = FakeMediaPool()
            logs: list[str] = []

            ok, _, ctx = selected_clip_subtitle_context(
                FakeResolve(FakeProject(timeline, media_pool)), fake_safe_call, logs.append, fps_from_project, source_fps_for_media_item
            )

            self.assertTrue(ok)
            self.assertEqual(ctx["clip_start"], 2.0)
            self.assertEqual(ctx["clip_end"], 5.0)
            self.assertEqual(len(ctx["subtitle_timing_segments"]), 2)
            self.assertTrue(any("subtitle_silence_cut_segments=2" in line for line in logs))


if __name__ == "__main__":
    unittest.main()
