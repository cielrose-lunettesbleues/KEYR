from __future__ import annotations

import unittest
from typing import Any

from resolve_integration.resolve_app.timelines import (
    append_silence_cut_segment_with_preset,
    create_timeline_for_clip,
    create_timeline_for_clip_with_preset,
    delete_timeline_if_exists,
    find_timeline_by_name,
    force_item_normal_speed,
    get_first_item_on_track,
    get_item_at_current_frame,
    get_timeline_selected_range,
    get_track_item_count,
    items_overlapping_frame_range,
    read_speed_props,
)


def fake_safe_call(obj: Any, method: str, *args: Any, default: Any = None) -> Any:
    try:
        return getattr(obj, method)(*args)
    except Exception:
        return default


class FakeItem:
    def __init__(self, start: int, end: int, media_item: Any | None = None) -> None:
        self.start = start
        self.end = end
        self.media_item = media_item
        self.props: dict[str, Any] = {}
        self.clip_props: dict[str, Any] = {}

    def GetStart(self) -> int:
        return self.start

    def GetEnd(self) -> int:
        return self.end

    def GetProperty(self, key: str | None = None) -> Any:
        if key is None:
            return self.props
        return self.props.get(key)

    def SetProperty(self, key: str, value: Any) -> bool:
        self.props[key] = value
        return True

    def SetClipProperty(self, key: str, value: Any) -> bool:
        self.clip_props[key] = value
        return True

    def GetMediaPoolItem(self) -> Any | None:
        return self.media_item


class FakeTimeline:
    def __init__(self, name: str = "Timeline") -> None:
        self.name = name
        self.items: dict[tuple[str, int], list[FakeItem]] = {}
        self.current_frame = 0
        self.mark_in_out: dict[str, Any] | None = None

    def GetName(self) -> str:
        return self.name

    def GetTrackCount(self, track_type: str) -> int:
        indexes = [idx for (typ, idx) in self.items if typ == track_type]
        return max(indexes) if indexes else 0

    def GetItemListInTrack(self, track_type: str, track_index: int) -> list[FakeItem]:
        return self.items.get((track_type, track_index), [])

    def GetCurrentFrame(self) -> int:
        return self.current_frame

    def GetMarkInOut(self) -> dict[str, Any] | None:
        return self.mark_in_out

    def AddTrack(self, track_type: str) -> bool:
        if track_type != "video":
            return False
        next_idx = self.GetTrackCount("video") + 1
        self.items.setdefault(("video", next_idx), [])
        return True


class FakeProject:
    def __init__(self, timelines: list[FakeTimeline] | None = None) -> None:
        if timelines is None:
            timelines = []
        self.timelines = timelines
        self.deleted: list[FakeTimeline] = []

    def GetTimelineCount(self) -> int:
        return len(self.timelines)

    def GetTimelineByIndex(self, index: int) -> FakeTimeline | None:
        try:
            return self.timelines[index - 1]
        except Exception:
            return None

    def DeleteTimeline(self, timeline: FakeTimeline) -> bool:
        self.deleted.append(timeline)
        return True


class FakeMediaPool:
    def __init__(self, delete_result: bool = True) -> None:
        self.delete_result = delete_result
        self.deleted: list[list[FakeTimeline]] = []
        self.current_timeline: FakeTimeline | None = None
        self.created: list[FakeTimeline] = []

    def DeleteTimelines(self, timelines: list[FakeTimeline]) -> bool:
        self.deleted.append(timelines)
        return self.delete_result

    def CreateEmptyTimeline(self, name: str) -> FakeTimeline:
        timeline = FakeTimeline(name)
        self.created.append(timeline)
        return timeline

    def SetCurrentTimeline(self, timeline: FakeTimeline) -> bool:
        self.current_timeline = timeline
        return True

    def AppendToTimeline(self, payload: list[dict[str, Any]]) -> list[FakeItem]:
        if self.current_timeline is None:
            return []
        appended: list[FakeItem] = []
        for row in payload:
            track_idx = int(row.get("trackIndex", 1))
            record = int(row.get("recordFrame", 0))
            duration = int(row.get("endFrame", 0)) - int(row.get("startFrame", 0))
            item = FakeItem(record, record + max(1, duration), row.get("mediaPoolItem"))
            self.current_timeline.items.setdefault(("video", track_idx), []).append(item)
            appended.append(item)
        return appended


def apply_transform(item: FakeItem, props: dict[str, float]) -> None:
    item.props.update(props)


def force_timeline_fps(_project: Any, timeline: FakeTimeline) -> None:
    timeline.props = {"fps_forced": True}  # type: ignore[attr-defined]


class ResolveTimelineTests(unittest.TestCase):
    def test_track_count_sums_items_across_tracks(self) -> None:
        timeline = FakeTimeline()
        timeline.items[("video", 1)] = [FakeItem(0, 10), FakeItem(20, 30)]
        timeline.items[("video", 2)] = [FakeItem(0, 10)]

        self.assertEqual(get_track_item_count(timeline, "video", fake_safe_call), 3)

    def test_current_and_first_item_helpers(self) -> None:
        timeline = FakeTimeline()
        first = FakeItem(0, 10)
        second = FakeItem(20, 30)
        timeline.items[("video", 1)] = [first, second]
        timeline.current_frame = 25

        self.assertIs(get_first_item_on_track(timeline, 1, fake_safe_call), first)
        self.assertIs(get_item_at_current_frame(timeline, 1, fake_safe_call), second)

    def test_items_overlapping_frame_range(self) -> None:
        timeline = FakeTimeline()
        a = FakeItem(0, 10)
        b = FakeItem(20, 30)
        c = FakeItem(40, 50)
        timeline.items[("video", 1)] = [a, b, c]

        self.assertEqual(items_overlapping_frame_range(timeline, 1, 9, 21, fake_safe_call), [a, b])

    def test_selected_range_reads_nested_video_in_out(self) -> None:
        timeline = FakeTimeline()
        timeline.mark_in_out = {"video": {"in": 100, "out": 250}}

        self.assertEqual(get_timeline_selected_range(timeline, fake_safe_call), (100, 250))

    def test_speed_helpers_read_and_normalize_item_speed(self) -> None:
        item = FakeItem(0, 10)
        item.props["Speed"] = 50

        self.assertEqual(read_speed_props(item, fake_safe_call), "Speed=50")

        force_item_normal_speed(item, fake_safe_call)

        self.assertEqual(item.props["Speed"], 100.0)
        self.assertEqual(item.props["RetimeProcess"], 0)
        self.assertEqual(item.clip_props["Speed"], "100")

    def test_find_and_delete_timeline_by_name(self) -> None:
        keep = FakeTimeline("Keep")
        target = FakeTimeline("Target")
        project = FakeProject([keep, target])
        media_pool = FakeMediaPool(delete_result=True)

        self.assertIs(find_timeline_by_name(project, "Target", fake_safe_call), target)

        delete_timeline_if_exists(project, media_pool, "Target", fake_safe_call)

        self.assertEqual(media_pool.deleted, [[target]])
        self.assertEqual(project.deleted, [])

    def test_delete_timeline_falls_back_to_project_delete(self) -> None:
        target = FakeTimeline("Target")
        project = FakeProject([target])
        media_pool = FakeMediaPool(delete_result=False)

        delete_timeline_if_exists(project, media_pool, "Target", fake_safe_call)

        self.assertEqual(project.deleted, [target])

    def test_create_timeline_for_clip_appends_single_range(self) -> None:
        media_pool = FakeMediaPool()
        media_item = object()

        timeline = create_timeline_for_clip(media_pool, "Single", media_item, 10, 20, fake_safe_call)

        self.assertIsNotNone(timeline)
        self.assertEqual(len(timeline.items[("video", 1)]), 1)  # type: ignore[union-attr]
        self.assertIs(timeline.items[("video", 1)][0].media_item, media_item)  # type: ignore[union-attr]

    def test_create_timeline_for_clip_with_fixed_split_applies_transforms(self) -> None:
        project = FakeProject()
        media_pool = FakeMediaPool()
        logs: list[str] = []
        preset = {"mode": "fixed_split", "camera": {"zoom_x": 1.2}, "gameplay": {"pan": 0.1}}

        timeline = create_timeline_for_clip_with_preset(
            project,
            media_pool,
            "Split",
            object(),
            0,
            60,
            preset,
            fake_safe_call,
            logs.append,
            force_timeline_fps,
            apply_transform,
        )

        self.assertIsNotNone(timeline)
        self.assertIn("Build timeline mapping", logs[0])
        self.assertEqual(timeline.items[("video", 1)][0].props["zoom_x"], 1.2)  # type: ignore[union-attr]
        self.assertEqual(timeline.items[("video", 2)][0].props["pan"], 0.1)  # type: ignore[union-attr]
        self.assertEqual(timeline.items[("video", 1)][0].props["Speed"], 100.0)  # type: ignore[union-attr]

    def test_append_silence_cut_segment_fixed_split_targets_record_frame(self) -> None:
        media_pool = FakeMediaPool()
        timeline = FakeTimeline("Cut")
        media_pool.SetCurrentTimeline(timeline)
        preset = {"mode": "fixed_split", "camera": {"zoom_x": 1.1}, "gameplay": {"zoom_y": 1.3}}

        append_silence_cut_segment_with_preset(
            media_pool,
            timeline,
            object(),
            100,
            160,
            240,
            preset,
            fake_safe_call,
            apply_transform,
        )

        self.assertEqual(timeline.items[("video", 1)][0].start, 240)
        self.assertEqual(timeline.items[("video", 2)][0].start, 240)
        self.assertEqual(timeline.items[("video", 1)][0].props["zoom_x"], 1.1)
        self.assertEqual(timeline.items[("video", 2)][0].props["zoom_y"], 1.3)


if __name__ == "__main__":
    unittest.main()
