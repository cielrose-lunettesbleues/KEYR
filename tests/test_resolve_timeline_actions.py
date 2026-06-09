from __future__ import annotations

import unittest
from typing import Any

from resolve_integration.resolve_app.timeline_actions import (
    TimelineActionDeps,
    apply_named_preset,
    detect_fixed_split_preset_from_timeline,
)


def fake_safe_call(obj: Any, method: str, *args: Any, default: Any = None) -> Any:
    try:
        return getattr(obj, method)(*args)
    except Exception:
        return default


class FakeItem:
    def __init__(self, props: dict[str, Any] | None = None) -> None:
        self.props = props or {}

    def GetProperty(self, key: str | None = None) -> Any:
        if key is None:
            return self.props
        return self.props.get(key)


class FakeTimeline:
    pass


class FakeProject:
    def __init__(self, timeline: Any | None) -> None:
        self.timeline = timeline

    def GetCurrentTimeline(self) -> Any | None:
        return self.timeline


class FakeProjectManager:
    def __init__(self, project: Any | None) -> None:
        self.project = project

    def GetCurrentProject(self) -> Any | None:
        return self.project


class FakeResolve:
    def __init__(self, project: Any | None) -> None:
        self.project = project

    def GetProjectManager(self) -> FakeProjectManager:
        return FakeProjectManager(self.project)


class TimelineActionsTests(unittest.TestCase):
    def _deps(self, cam_item: Any | None = None, game_item: Any | None = None) -> tuple[TimelineActionDeps, list[str], list[tuple[dict[str, Any], str]]]:
        logs: list[str] = []
        applied: list[tuple[dict[str, Any], str]] = []

        def apply_preset_to_selected_clip(_resolve: Any, preset: dict[str, Any], scope_mode: str) -> tuple[bool, str]:
            applied.append((preset, scope_mode))
            return True, "Preset appliqué"

        deps = TimelineActionDeps(
            safe_call=fake_safe_call,
            log=logs.append,
            get_item_at_current_frame=lambda timeline, track: cam_item if track == 1 else game_item,
            get_first_item_on_track=lambda timeline, track: cam_item if track == 1 else game_item,
            apply_preset_to_selected_clip=apply_preset_to_selected_clip,
        )
        return deps, logs, applied

    def test_apply_named_preset_delegates_and_logs_success(self) -> None:
        deps, logs, applied = self._deps()

        ok, message = apply_named_preset(
            object(),
            {"presets": {"p1": {"mode": "single"}}},
            "p1",
            "whole_clip",
            deps,
        )

        self.assertTrue(ok)
        self.assertEqual(message, "Preset appliqué")
        self.assertEqual(applied, [({"mode": "single"}, "whole_clip")])
        self.assertEqual(logs, ["Apply preset success: preset=p1 scope=whole_clip"])

    def test_apply_named_preset_reports_missing_preset(self) -> None:
        deps, logs, applied = self._deps()

        ok, message = apply_named_preset(object(), {"presets": {}}, "missing", "whole_clip", deps)

        self.assertFalse(ok)
        self.assertEqual(message, "Preset introuvable: missing")
        self.assertEqual(applied, [])
        self.assertEqual(logs, [])

    def test_detect_fixed_split_preset_reads_track_properties(self) -> None:
        cam = FakeItem({"ZoomX": "1.25", "Pan": "-0.1"})
        game = FakeItem({"ZoomX": "2.0", "Tilt": "0.3"})
        deps, logs, _ = self._deps(cam, game)

        result = detect_fixed_split_preset_from_timeline(
            FakeResolve(FakeProject(FakeTimeline())),
            "current",
            deps,
            ("zoom_x", "pan", "tilt"),
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["mode"], "fixed_split")
        self.assertEqual(result["fields"]["camera.zoom_x"], 1.25)
        self.assertEqual(result["fields"]["camera.pan"], -0.1)
        self.assertEqual(result["fields"]["gameplay.zoom_x"], 2.0)
        self.assertEqual(result["fields"]["gameplay.tilt"], 0.3)
        self.assertTrue(any("Detect preset mode=current" in line for line in logs))

    def test_detect_fixed_split_preset_requires_second_track(self) -> None:
        deps, _, _ = self._deps(FakeItem({"ZoomX": 1.0}), None)

        result = detect_fixed_split_preset_from_timeline(FakeResolve(FakeProject(FakeTimeline())), "first", deps)

        self.assertFalse(result["ok"])
        self.assertEqual(result["message"], "Détection impossible: aucun clip sur la piste 2")


if __name__ == "__main__":
    unittest.main()
