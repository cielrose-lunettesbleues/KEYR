from __future__ import annotations

import unittest
from pathlib import Path
from typing import Any

from resolve_integration.resolve_app.textplus import (
    apply_textplus_style,
    build_textplus_clip_list,
    find_template_item_by_name,
    import_subtitles_to_timeline,
    parse_hex_color,
    remap_text_segments,
    set_textplus_item_text,
)


def fake_safe_call(obj: Any, method: str, *args: Any, default: Any = None) -> Any:
    try:
        return getattr(obj, method)(*args)
    except Exception:
        return default


def coerce_float(value: Any, default: float, min_value: float | None, max_value: float | None) -> float:
    try:
        out = float(value)
    except Exception:
        out = default
    if min_value is not None:
        out = max(min_value, out)
    if max_value is not None:
        out = min(max_value, out)
    return out


class FakeTool:
    def __init__(self, fail_count: int = 0) -> None:
        self.inputs: dict[str, Any] = {}
        self.fail_count = fail_count

    def SetInput(self, name: str, value: Any) -> bool:
        if self.fail_count > 0:
            self.fail_count -= 1
            return False
        self.inputs[name] = value
        return True

    def GetInput(self, name: str) -> Any:
        return self.inputs.get(name)


class FakeNoneReturningTool(FakeTool):
    def SetInput(self, name: str, value: Any) -> None:
        self.inputs[name] = value
        return None


class FakeComp:
    def __init__(self, tools: dict[str, FakeTool]) -> None:
        self.tools = tools

    def GetToolList(self, *args: Any) -> dict[str, FakeTool]:
        return self.tools


class FakeTimelineItem:
    def __init__(self, comp: FakeComp | None) -> None:
        self.comp = comp

    def GetFusionCompCount(self) -> int:
        return 1 if self.comp is not None else 0

    def GetFusionCompByIndex(self, index: int) -> FakeComp | None:
        return self.comp if index == 1 else None


class FakeClip:
    def __init__(self, name: str) -> None:
        self.name = name

    def GetName(self) -> str:
        return self.name


class FakeFolder:
    def __init__(self, clips: list[FakeClip], folders: list["FakeFolder"] | None = None) -> None:
        self.clips = clips
        self.folders = folders or []

    def GetClipList(self) -> list[FakeClip]:
        return self.clips

    def GetSubFolderList(self) -> list["FakeFolder"]:
        return self.folders


class FakeProject:
    def __init__(self) -> None:
        self.current_timeline: FakeTimeline | None = None

    def SetCurrentTimeline(self, timeline: "FakeTimeline") -> bool:
        self.current_timeline = timeline
        return True


class FakeTimeline:
    def __init__(self) -> None:
        self.video_tracks = 1
        self.subtitle_items = 0
        self.added_tracks: list[str] = []
        self.video_items: dict[int, list[Any]] = {}

    def GetTrackCount(self, track_type: str) -> int:
        if track_type == "video":
            return self.video_tracks
        if track_type == "subtitle":
            return 1 if self.subtitle_items else 0
        return 0

    def GetItemListInTrack(self, track_type: str, track_index: int) -> list[Any]:
        if track_type == "video":
            return self.video_items.get(track_index, [])
        if track_type == "subtitle" and self.subtitle_items:
            return [object()] * self.subtitle_items
        return []

    def GetSetting(self, key: str) -> str:
        if key == "timelineFrameRate":
            return "60"
        return ""

    def GetStartFrame(self) -> int:
        return 100

    def AddTrack(self, track_type: str) -> bool:
        self.added_tracks.append(track_type)
        self.video_tracks += 1
        return True


class FakeMediaPool:
    def __init__(self, root: FakeFolder, appended: list[FakeTimelineItem]) -> None:
        self.root = root
        self.appended = appended
        self.current_timeline: FakeTimeline | None = None
        self.clip_list: list[dict[str, Any]] = []

    def GetRootFolder(self) -> FakeFolder:
        return self.root

    def SetCurrentTimeline(self, timeline: FakeTimeline) -> bool:
        self.current_timeline = timeline
        return True

    def AppendToTimeline(self, clip_list: list[dict[str, Any]]) -> list[FakeTimelineItem]:
        self.clip_list = clip_list
        return self.appended


class FakePlacedTimelineItem(FakeTimelineItem):
    def __init__(self, comp: FakeComp | None, start: int, end: int) -> None:
        super().__init__(comp)
        self.start = start
        self.end = end

    def GetStart(self) -> int:
        return self.start

    def GetEnd(self) -> int:
        return self.end


class ResolveTextPlusTests(unittest.TestCase):
    def test_parse_hex_color(self) -> None:
        self.assertEqual(parse_hex_color("#FF8000"), (1.0, 128 / 255.0, 0.0))
        self.assertIsNone(parse_hex_color("nope"))

    def test_apply_textplus_style_sets_expected_inputs(self) -> None:
        tool = FakeTool()

        applied = apply_textplus_style(
            tool,
            {"font": "Arial", "font_style": "Bold", "font_size": "0.2", "color": "336699", "position_x": 0.4, "position_y": 0.8},
            fake_safe_call,
            coerce_float,
        )

        self.assertGreaterEqual(applied, 7)
        self.assertEqual(tool.inputs["Font"], "Arial")
        self.assertEqual(tool.inputs["Style"], "Bold")
        self.assertEqual(tool.inputs["Size"], 0.2)
        self.assertEqual(tool.inputs["Center"], {1: 0.4, 2: 0.8})

    def test_set_textplus_item_text_updates_first_textplus_tool(self) -> None:
        tool = FakeTool()
        item = FakeTimelineItem(FakeComp({"Text1": tool}))

        ok, style_count = set_textplus_item_text(item, "Salut", {"font": "Arial"}, fake_safe_call, coerce_float)

        self.assertTrue(ok)
        self.assertEqual(style_count, 1)
        self.assertEqual(tool.inputs["StyledText"], "Salut")

    def test_set_textplus_item_text_accepts_none_return_when_input_is_set(self) -> None:
        tool = FakeNoneReturningTool()
        item = FakeTimelineItem(FakeComp({"Text1": tool}))

        ok, style_count = set_textplus_item_text(item, "Salut", {"font": "Arial"}, fake_safe_call, coerce_float)

        self.assertTrue(ok)
        self.assertEqual(style_count, 1)
        self.assertEqual(tool.inputs["StyledText"], "Salut")
        self.assertEqual(tool.inputs["Font"], "Arial")

    def test_remap_text_segments_to_cut_timing(self) -> None:
        captions = [{"start": 10.0, "end": 14.0, "text": "hello"}]
        timing = [{"source_start": 12.0, "source_end": 20.0, "timeline_start": 3.0}]

        self.assertEqual(remap_text_segments(captions, timing, 0.0), [{"start": 3.0, "end": 5.0, "text": "hello"}])

    def test_build_textplus_clip_list_applies_offset_and_frames(self) -> None:
        template = object()
        clips = build_textplus_clip_list([{"start": 1.0, "end": 2.0, "text": "x"}], template, 60.0, 100, 3, -500)

        self.assertEqual(clips[0]["mediaPoolItem"], template)
        self.assertEqual(clips[0]["trackIndex"], 3)
        self.assertEqual(clips[0]["recordFrame"], 130)
        self.assertEqual(clips[0]["endFrame"], 60)

    def test_find_template_item_by_name_walks_nested_folders(self) -> None:
        target = FakeClip("ShortEditor Caption")
        root = FakeFolder([FakeClip("Other")], [FakeFolder([target])])

        self.assertIs(find_template_item_by_name(root, "shorteditor caption", fake_safe_call), target)

    def test_import_subtitles_to_timeline_appends_and_sets_text(self) -> None:
        template = FakeClip("ShortEditor Caption")
        root_folder = FakeFolder([template])
        tool = FakeTool()
        appended_item = FakeTimelineItem(FakeComp({"Text1": tool}))
        media_pool = FakeMediaPool(root_folder, [appended_item])
        timeline = FakeTimeline()
        project = FakeProject()
        logs: list[str] = []

        ok, message = import_subtitles_to_timeline(
            project,
            media_pool,
            timeline,
            [{"start": 1.0, "end": 2.0, "text": "Salut"}],
            root=Path("."),
            template_name="Auto-detect (Recommended)",
            auto_label="Auto-detect (Recommended)",
            primary_template_name="ShortEditor Caption",
            fallback_template_name="AutoSubs Caption",
            offset_ms=-500,
            subtitle_style={"font": "Arial"},
            timing_segments=None,
            subtitle_source_start=0.0,
            safe_call=fake_safe_call,
            log=logs.append,
            coerce_float=coerce_float,
            parse_fps_text=lambda value: float(value),
        )

        self.assertTrue(ok)
        self.assertIn("Subtitles applied via standalone Text+", message)
        self.assertIs(project.current_timeline, timeline)
        self.assertIs(media_pool.current_timeline, timeline)
        self.assertEqual(media_pool.clip_list[0]["recordFrame"], 130)
        self.assertEqual(media_pool.clip_list[0]["trackIndex"], 2)
        self.assertEqual(tool.inputs["StyledText"], "Salut")
        self.assertEqual(tool.inputs["Font"], "Arial")
        self.assertTrue(any("subtitle_textplus_apply" in line for line in logs))

    def test_import_subtitles_retries_until_textplus_comp_ready(self) -> None:
        template = FakeClip("ShortEditor Caption")
        root_folder = FakeFolder([template])
        tool = FakeTool(fail_count=2)
        appended_item = FakeTimelineItem(FakeComp({"Text1": tool}))
        media_pool = FakeMediaPool(root_folder, [appended_item])
        timeline = FakeTimeline()
        logs: list[str] = []

        ok, _ = import_subtitles_to_timeline(
            FakeProject(),
            media_pool,
            timeline,
            [{"start": 1.0, "end": 2.0, "text": "Retry"}],
            root=Path("."),
            template_name="Auto-detect (Recommended)",
            auto_label="Auto-detect (Recommended)",
            primary_template_name="ShortEditor Caption",
            fallback_template_name="AutoSubs Caption",
            offset_ms=-500,
            subtitle_style=None,
            timing_segments=None,
            subtitle_source_start=0.0,
            safe_call=fake_safe_call,
            log=logs.append,
            coerce_float=coerce_float,
            parse_fps_text=lambda value: float(value),
        )

        self.assertTrue(ok)
        self.assertEqual(tool.inputs["StyledText"], "Retry")
        self.assertTrue(any("attempt=2" in line and "applied=1/1" in line for line in logs))

    def test_import_subtitles_falls_back_to_reread_track_items(self) -> None:
        template = FakeClip("ShortEditor Caption")
        root_folder = FakeFolder([template])
        appended_item = FakeTimelineItem(None)
        media_pool = FakeMediaPool(root_folder, [appended_item])
        timeline = FakeTimeline()
        tool = FakeTool()
        reread_item = FakePlacedTimelineItem(FakeComp({"Text1": tool}), start=130, end=190)
        timeline.video_items[2] = [reread_item]
        logs: list[str] = []

        ok, _ = import_subtitles_to_timeline(
            FakeProject(),
            media_pool,
            timeline,
            [{"start": 1.0, "end": 2.0, "text": "Fallback"}],
            root=Path("."),
            template_name="Auto-detect (Recommended)",
            auto_label="Auto-detect (Recommended)",
            primary_template_name="ShortEditor Caption",
            fallback_template_name="AutoSubs Caption",
            offset_ms=-500,
            subtitle_style=None,
            timing_segments=None,
            subtitle_source_start=0.0,
            safe_call=fake_safe_call,
            log=logs.append,
            coerce_float=coerce_float,
            parse_fps_text=lambda value: float(value),
        )

        self.assertTrue(ok)
        self.assertEqual(tool.inputs["StyledText"], "Fallback")
        self.assertTrue(any("subtitle_textplus_reread_track track=2 matched=1/1" in line for line in logs))


if __name__ == "__main__":
    unittest.main()
