from __future__ import annotations

import unittest
from typing import Any

from resolve_integration.resolve_app.project_settings import (
    apply_preview_safe_playback,
    ensure_playback_fps_60,
    ensure_vertical_project_settings,
    force_timeline_fps_60,
    fps_from_project,
    safe_int_from_project_setting,
)


def fake_safe_call(obj: Any, method: str, *args: Any, default: Any = None) -> Any:
    try:
        return getattr(obj, method)(*args)
    except Exception:
        return default


class FakeProject:
    def __init__(self) -> None:
        self.settings: dict[str, Any] = {}
        self.current_timeline: Any = None
        self.preview_success = True

    def GetSetting(self, key: str) -> Any:
        return self.settings.get(key)

    def SetSetting(self, key: str, value: Any) -> bool:
        self.settings[key] = value
        if key in {"renderCacheMode", "proxyMediaMode", "timelineProxyResolution"}:
            return self.preview_success
        return True

    def SetCurrentTimeline(self, timeline: Any) -> bool:
        self.current_timeline = timeline
        return True


class FakeTimeline:
    def __init__(self) -> None:
        self.settings: dict[str, Any] = {}

    def SetSetting(self, key: str, value: Any) -> bool:
        self.settings[key] = value
        return True

    def GetSetting(self, key: str) -> Any:
        return self.settings.get(key)

    def GetName(self) -> str:
        return "Short Timeline"


class ResolveProjectSettingsTests(unittest.TestCase):
    def test_safe_int_and_fps_from_project(self) -> None:
        project = FakeProject()
        project.settings["timelineFrameRate"] = "60.0"

        self.assertEqual(safe_int_from_project_setting(project, "timelineFrameRate", 24), 60)
        self.assertEqual(fps_from_project(project, 24), 60)

        project.settings["timelineFrameRate"] = "bad"
        self.assertEqual(fps_from_project(project, 24), 24)

    def test_ensure_vertical_project_settings_sets_shorts_defaults(self) -> None:
        project = FakeProject()

        ensure_vertical_project_settings(project, fake_safe_call)

        self.assertEqual(project.settings["timelineResolutionWidth"], "1080")
        self.assertEqual(project.settings["timelineResolutionHeight"], "1920")
        self.assertEqual(project.settings["timelineFrameRate"], "60.000")
        self.assertEqual(project.settings["timelineOutputResolutionHeight"], "1920")
        self.assertEqual(project.settings["inputScalingPreset"], "Scale full frame with crop")

    def test_ensure_playback_fps_60_logs_and_returns_true(self) -> None:
        project = FakeProject()
        project.settings["timelineFrameRate"] = "60"
        project.settings["timelinePlaybackFrameRate"] = "60"
        logs: list[str] = []

        self.assertTrue(ensure_playback_fps_60(project, 24, fake_safe_call, logs.append))
        self.assertIn("playback_fps_verify timeline=60 playback=60", logs)

    def test_force_timeline_fps_60_sets_current_timeline(self) -> None:
        project = FakeProject()
        timeline = FakeTimeline()
        logs: list[str] = []

        force_timeline_fps_60(project, timeline, fake_safe_call, logs.append)

        self.assertIs(project.current_timeline, timeline)
        self.assertEqual(timeline.settings["timelineFrameRate"], "60.000")
        self.assertTrue(any("timeline_fps_verify name=Short Timeline" in line for line in logs))

    def test_apply_preview_safe_playback_warns_when_no_settings_apply(self) -> None:
        project = FakeProject()
        project.preview_success = False
        logs: list[str] = []

        warnings = apply_preview_safe_playback(project, fake_safe_call, logs.append)

        self.assertEqual(len(warnings), 1)
        self.assertEqual(logs, [])


if __name__ == "__main__":
    unittest.main()
