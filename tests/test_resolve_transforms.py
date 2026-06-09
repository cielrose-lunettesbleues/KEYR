from __future__ import annotations

import unittest
from typing import Any

from resolve_integration.resolve_app.transforms import apply_item_transform, apply_preset_to_selected_clip, read_item_transform


def fake_safe_call(obj: Any, method: str, *args: Any, default: Any = None) -> Any:
    try:
        return getattr(obj, method)(*args)
    except Exception:
        return default


class FakeItem:
    def __init__(self, start: int = 0, end: int = 10) -> None:
        self.start = start
        self.end = end
        self.props: dict[str, Any] = {}

    def SetProperty(self, key: str, value: Any) -> bool:
        self.props[key] = value
        return True

    def GetProperty(self, key: str | None = None) -> Any:
        if key is None:
            return self.props
        return self.props.get(key)

    def GetStart(self) -> int:
        return self.start

    def GetEnd(self) -> int:
        return self.end


class FakeTimeline:
    def __init__(self) -> None:
        self.items: dict[tuple[str, int], list[FakeItem]] = {}
        self.current_frame = 0
        self.current_item: FakeItem | None = None
        self.mark_in_out: dict[str, Any] | None = None

    def GetTrackCount(self, track_type: str) -> int:
        indexes = [idx for (typ, idx) in self.items if typ == track_type]
        return max(indexes) if indexes else 0

    def GetItemListInTrack(self, track_type: str, track_index: int) -> list[FakeItem]:
        return self.items.get((track_type, track_index), [])

    def GetCurrentFrame(self) -> int:
        return self.current_frame

    def GetCurrentVideoItem(self) -> FakeItem | None:
        return self.current_item

    def GetMarkInOut(self) -> dict[str, Any] | None:
        return self.mark_in_out


class FakeProject:
    def __init__(self, timeline: FakeTimeline | None) -> None:
        self.timeline = timeline

    def GetCurrentTimeline(self) -> FakeTimeline | None:
        return self.timeline


class FakeProjectManager:
    def __init__(self, project: FakeProject | None) -> None:
        self.project = project

    def GetCurrentProject(self) -> FakeProject | None:
        return self.project


class FakeResolve:
    def __init__(self, project: FakeProject | None) -> None:
        self.pm = FakeProjectManager(project)

    def GetProjectManager(self) -> FakeProjectManager:
        return self.pm


class ResolveTransformTests(unittest.TestCase):
    def test_apply_and_read_item_transform(self) -> None:
        item = FakeItem()

        apply_item_transform(item, {"zoom_x": 1.2, "pan": -0.1, "ignored": 999}, fake_safe_call)

        self.assertEqual(item.props["ZoomX"], 1.2)
        self.assertEqual(item.props["Pan"], -0.1)
        self.assertNotIn("ignored", item.props)
        self.assertEqual(read_item_transform(item, fake_safe_call)["zoom_x"], 1.2)

    def test_apply_single_preset_to_current_item(self) -> None:
        item = FakeItem()
        timeline = FakeTimeline()
        timeline.current_item = item
        resolve = FakeResolve(FakeProject(timeline))

        ok, message = apply_preset_to_selected_clip(resolve, {"mode": "single", "single": {"zoom_y": 1.4}}, "whole_clip", fake_safe_call, lambda _m: None)

        self.assertTrue(ok)
        self.assertIn("Preset appliqué", message)
        self.assertEqual(item.props["ZoomY"], 1.4)

    def test_apply_fixed_split_to_selected_range(self) -> None:
        cam = FakeItem(10, 30)
        gameplay = FakeItem(10, 30)
        timeline = FakeTimeline()
        timeline.items[("video", 1)] = [cam]
        timeline.items[("video", 2)] = [gameplay]
        timeline.mark_in_out = {"in": 12, "out": 20}
        resolve = FakeResolve(FakeProject(timeline))
        logs: list[str] = []

        ok, message = apply_preset_to_selected_clip(
            resolve,
            {"mode": "fixed_split", "camera": {"zoom_x": 1.1}, "gameplay": {"tilt": 0.2}},
            "selected_range",
            fake_safe_call,
            logs.append,
        )

        self.assertTrue(ok)
        self.assertIn("plage", message)
        self.assertEqual(cam.props["ZoomX"], 1.1)
        self.assertEqual(gameplay.props["Tilt"], 0.2)
        self.assertTrue(logs)

    def test_apply_fixed_split_requires_two_tracks(self) -> None:
        timeline = FakeTimeline()
        timeline.items[("video", 1)] = [FakeItem()]
        resolve = FakeResolve(FakeProject(timeline))

        ok, message = apply_preset_to_selected_clip(resolve, {"mode": "fixed_split"}, "whole_timeline", fake_safe_call, lambda _m: None)

        self.assertFalse(ok)
        self.assertIn("piste 1", message)


if __name__ == "__main__":
    unittest.main()
