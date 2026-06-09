from __future__ import annotations

import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from resolve_integration.resolve_app.silence_actions import SilenceActionDeps, run_silence_cut, undo_silence_cuts


def fake_safe_call(obj: Any, method: str, *args: Any, default: Any = None) -> Any:
    try:
        return getattr(obj, method)(*args)
    except Exception:
        return default


class FakeTimeline:
    def __init__(self, name: str) -> None:
        self.name = name

    def GetName(self) -> str:
        return self.name


class FakeMediaPool:
    def __init__(self) -> None:
        self.deleted: list[Any] = []
        self.current: Any | None = None

    def DeleteTimelines(self, timelines: list[Any]) -> bool:
        self.deleted.extend(timelines)
        return True

    def SetCurrentTimeline(self, timeline: Any) -> bool:
        self.current = timeline
        return True


class FakeProject:
    def __init__(self) -> None:
        self.media_pool = FakeMediaPool()
        self.timelines: dict[str, FakeTimeline] = {}
        self.current = FakeTimeline("Current")

    def GetMediaPool(self) -> FakeMediaPool:
        return self.media_pool

    def GetCurrentTimeline(self) -> FakeTimeline:
        return self.current

    def SetCurrentTimeline(self, timeline: Any) -> bool:
        self.current = timeline
        return True


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


@dataclass
class FakePlan:
    source_path: str
    start_seconds: float = 0.0
    end_seconds: float = 10.0
    display_name: str = "Plan"
    clip_id: str = "clip_1"
    timeline_name: str = ""


class SilenceActionsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.source = self.root / "input" / "vod.mp4"
        self.source.parent.mkdir(parents=True, exist_ok=True)
        self.source.write_bytes(b"fake")
        self.project = FakeProject()
        self.resolve = FakeResolve(self.project)
        self.logs: list[str] = []
        self.created: list[tuple[str, list[tuple[float, float]], dict[str, Any]]] = []
        self.progress: list[tuple[int, int, str]] = []

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _deps(self, *, cuts: float = 1.0, removed: float = 2.5, ctx_ok: bool = True) -> SilenceActionDeps:
        def selected_clip_subtitle_context(_resolve: Any) -> tuple[bool, str, dict[str, Any]]:
            if not ctx_ok:
                return False, "No active timeline", {}
            return (
                True,
                "ok",
                {
                    "source_path": str(self.source),
                    "clip_start": 1.0,
                    "clip_end": 5.0,
                    "item_name": "Clip A",
                    "timeline_name": "Timeline A",
                },
            )

        def create_silence_cut_timeline(
            _root: Path,
            _project: Any,
            _media_pool: Any,
            _source_path: Path,
            timeline_name: str,
            segments: list[tuple[float, float]],
            preset: dict[str, Any],
        ) -> tuple[Any | None, list[str]]:
            self.created.append((timeline_name, segments, preset))
            timeline = FakeTimeline(timeline_name)
            self.project.timelines[timeline_name] = timeline
            return timeline, []

        def find_timeline_by_name(_project: Any, timeline_name: str) -> Any | None:
            return self.project.timelines.get(timeline_name)

        return SilenceActionDeps(
            safe_call=fake_safe_call,
            log=self.logs.append,
            load_pipeline_config=lambda root: {"audio": {"silence_cut": {}}},
            selected_clip_subtitle_context=selected_clip_subtitle_context,
            load_audio_energy_for_silence_cut=lambda root, source, cfg, cache: ([(1.0, 1.0), (2.0, 0.0), (3.0, 1.0)], "piste voix 2", []),
            detect_audible_segments_for_silence_cut=lambda energies, start, end, cfg: ([(1.0, 2.0), (3.0, 5.0)], {"cuts": cuts, "removed_seconds": removed}),
            create_silence_cut_timeline=create_silence_cut_timeline,
            parse_manifest=lambda path: ("batch_1", [FakePlan(str(self.source), timeline_name="Plan One")]),
            suffix_timeline_name=lambda name: f"{name}__silence_cut",
            find_timeline_by_name=find_timeline_by_name,
        )

    def _progress(self, current: int, total: int, detail: str) -> None:
        self.progress.append((current, total, detail))

    def test_run_silence_cut_selected_clip_creates_timeline(self) -> None:
        result = run_silence_cut(
            self.root,
            self.resolve,
            "Clip sélectionné",
            "p1",
            {"presets": {"p1": {"mode": "single"}}},
            {},
            None,
            self._deps(),
            self._progress,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["message"], "Coupe des silences terminée: 1 timeline(s), 1 cut(s), 2.5s supprimée(s).")
        self.assertEqual(self.created[0][0], "Clip A__silence_cut")
        self.assertEqual(self.created[0][2], {"mode": "single"})
        self.assertTrue(any("silence_cut_created" in line for line in self.logs))
        self.assertEqual(self.progress[0], (1, 1, "Analyse audio: Clip A"))

    def test_run_silence_cut_returns_warning_when_no_cut_needed(self) -> None:
        result = run_silence_cut(
            self.root,
            self.resolve,
            "Clip sélectionné",
            "p1",
            {"presets": {"p1": {"mode": "single"}}},
            {},
            None,
            self._deps(cuts=0.0, removed=0.0),
            self._progress,
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["message"], "Aucune timeline silence_cut créée.")
        self.assertEqual(self.created, [])
        self.assertEqual(result["warnings"], ["Clip A: aucun silence gênant détecté (piste voix 2)."])

    def test_undo_silence_cuts_deletes_existing_target_and_reselects_original(self) -> None:
        self.project.current = FakeTimeline("Clip A__silence_cut")
        self.project.timelines["Clip A__silence_cut"] = self.project.current
        original = FakeTimeline("Clip A")
        self.project.timelines["Clip A"] = original

        result = undo_silence_cuts(
            self.resolve,
            "Clip sélectionné",
            {},
            None,
            self._deps(),
            lambda count: count == 1,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["message"], "Cuts annulés: 1 timeline(s) silence_cut supprimée(s).")
        self.assertEqual(self.project.media_pool.deleted, [self.project.timelines["Clip A__silence_cut"]])
        self.assertIs(self.project.current, original)
        self.assertTrue(any("silence_cut_deleted" in line for line in self.logs))

    def test_undo_silence_cuts_can_be_cancelled(self) -> None:
        self.project.timelines["Clip A__silence_cut"] = FakeTimeline("Clip A__silence_cut")

        result = undo_silence_cuts(
            self.resolve,
            "Clip sélectionné",
            {},
            None,
            self._deps(),
            lambda _count: False,
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["message"], "Annulation des cuts de silences annulée.")
        self.assertEqual(self.project.media_pool.deleted, [])


if __name__ == "__main__":
    unittest.main()
