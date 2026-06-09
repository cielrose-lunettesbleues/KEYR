from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any

from resolve_integration.resolve_app.render_queue import collect_unique_media_items_from_timelines, queue_render_job, set_shorts_render_defaults


def fake_safe_call(obj: Any, method: str, *args: Any, default: Any = None) -> Any:
    try:
        return getattr(obj, method)(*args)
    except Exception:
        return default


class FakeProject:
    def __init__(self) -> None:
        self.loaded_presets: list[str] = []
        self.render_settings: dict[str, Any] = {}
        self.current_timeline: Any = None
        self.job_id: Any = "job_1"
        self.load_result = False
        self.codec_calls: list[tuple[str, str]] = []

    def LoadRenderPreset(self, name: str) -> bool:
        self.loaded_presets.append(name)
        return self.load_result

    def SetCurrentRenderFormatAndCodec(self, fmt: str, codec: str) -> bool:
        self.codec_calls.append((fmt, codec))
        return True

    def SetRenderSettings(self, settings: dict[str, Any]) -> bool:
        self.render_settings = settings
        return True

    def SetCurrentTimeline(self, timeline: Any) -> bool:
        self.current_timeline = timeline
        return True

    def AddRenderJob(self) -> Any:
        return self.job_id


class FakeTimeline:
    def __init__(self, name: str = "Timeline") -> None:
        self.name = name
        self.items: dict[int, list[FakeItem]] = {}

    def GetName(self) -> str:
        return self.name

    def GetTrackCount(self, track_type: str) -> int:
        if track_type != "video" or not self.items:
            return 0
        return max(self.items)

    def GetItemListInTrack(self, track_type: str, track_index: int) -> list["FakeItem"]:
        if track_type != "video":
            return []
        return self.items.get(track_index, [])


class FakeItem:
    def __init__(self, media_item: Any) -> None:
        self.media_item = media_item

    def GetMediaPoolItem(self) -> Any:
        return self.media_item


class ResolveRenderQueueTests(unittest.TestCase):
    def test_set_shorts_render_defaults_applies_vertical_settings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            project = FakeProject()

            set_shorts_render_defaults(project, Path(tmp_dir), "Short 1", fake_safe_call)

            self.assertEqual(project.render_settings["TargetDir"], tmp_dir)
            self.assertEqual(project.render_settings["CustomName"], "Short 1")
            self.assertEqual(project.render_settings["FormatWidth"], 1080)
            self.assertEqual(project.render_settings["FormatHeight"], 1920)
            self.assertEqual(project.render_settings["FrameRate"], 60)

    def test_queue_render_job_uses_loaded_preset_when_available(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            project = FakeProject()
            project.load_result = True
            timeline = FakeTimeline("Auto 1")
            logs: list[str] = []

            ok = queue_render_job(project, timeline, Path(tmp_dir), "Preset", fake_safe_call, logs.append)

            self.assertTrue(ok)
            self.assertIs(project.current_timeline, timeline)
            self.assertEqual(project.loaded_presets, ["Preset"])
            self.assertEqual(project.render_settings["CustomName"], "Auto 1")
            self.assertIn("Render settings applied for Auto 1", logs[0])

    def test_collect_unique_media_items_from_timelines_deduplicates(self) -> None:
        media_a = object()
        media_b = object()
        timeline = FakeTimeline()
        timeline.items[1] = [FakeItem(media_a), FakeItem(media_a)]
        timeline.items[2] = [FakeItem(media_b)]

        self.assertEqual(collect_unique_media_items_from_timelines([timeline], fake_safe_call), [media_a, media_b])


if __name__ == "__main__":
    unittest.main()
