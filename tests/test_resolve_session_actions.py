from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any

from resolve_integration.resolve_app.session_actions import SessionActionDeps, generate_session_batch, update_session_composition


class SessionActionsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.manifest = self.root / "output" / "manifests" / "batch.json"
        self.manifest.parent.mkdir(parents=True, exist_ok=True)
        self.manifest.write_text("{}", encoding="utf-8")
        self.vod = self.root / "input" / "vod.mp4"
        self.vod.parent.mkdir(parents=True, exist_ok=True)
        self.vod.write_bytes(b"fake")
        self.logs: list[str] = []
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _presets_data(self) -> dict[str, Any]:
        return {
            "presets": {"p1": {"mode": "single", "max_clip_seconds": 45}},
            "subtitle_presets": {"Minimal clean": {"font": "Arial", "words_per_subtitle": 3}},
        }

    def _params(self, **overrides: Any) -> dict[str, Any]:
        out = {
            "output": str(self.root / "renders"),
            "render_preset": "H264",
            "render_master": False,
            "preset_id": "p1",
            "subtitle_preset_id": "Minimal clean",
            "query": "",
            "use_transcript_for_selection": False,
            "strict_manifest": False,
            "require_subtitles": False,
            "preview_safe_quality": True,
            "generate_optimized_media_quality": True,
            "subtitle_template_name": "Auto-detect (Recommended)",
            "subtitle_offset_ms": "-500",
            "vod_dir": "",
        }
        out.update(overrides)
        return out

    def _deps(self, **overrides: Any) -> SessionActionDeps:
        def build_from_manifest(*args: Any, **kwargs: Any) -> tuple[str, dict[str, Any], list[Any], list[str]]:
            self.calls.append(("build", kwargs))
            return "batch_1", {"clip": object()}, [object(), object()], []

        def generate_manifest_for_vod(*args: Any, **kwargs: Any) -> Path:
            self.calls.append(("generate_manifest", kwargs))
            generated = self.root / "output" / "manifests" / "generated.json"
            generated.write_text("{}", encoding="utf-8")
            return generated

        values: dict[str, Any] = {
            "read_manifest_safe": lambda path: {"meta": {}},
            "default_subtitle_presets": lambda: {"Minimal clean": {"font": "Arial", "words_per_subtitle": 3}},
            "subtitle_style_from_preset": lambda preset: {"font": str((preset or {}).get("font", ""))},
            "merge_subtitle_preset_into_config": lambda cfg, preset: {**cfg, "captions": {"words_per_subtitle": (preset or {}).get("words_per_subtitle", 3)}},
            "load_pipeline_config": lambda root: {"captions": {}},
            "manifest_has_valid_subtitles": lambda root, data: False,
            "apply_preview_safe_playback": lambda project: ["preview warning"],
            "transcript_path_for_vod": lambda root, vod: root / "output" / "transcripts" / f"{vod.stem}.json",
            "find_reusable_quality_manifest": lambda root, vod, preset_id, use_transcript, subtitle_preset_id: None,
            "generate_manifest_for_vod": generate_manifest_for_vod,
            "build_from_manifest": build_from_manifest,
            "log": self.logs.append,
            "ensure_transcript": lambda source, cfg, output_dir, progress_cb: output_dir / f"{source.stem}.json",
        }
        values.update(overrides)
        return SessionActionDeps(**values)

    def test_generate_fast_builds_from_existing_manifest(self) -> None:
        session = {"manifest": self.manifest, "detected_vod": self.vod, "used_manifest_fallback": False}

        result = generate_session_batch(
            self.root,
            object(),
            object(),
            session,
            self.manifest,
            self._presets_data(),
            self._params(),
            self._deps(),
            "Minimal clean",
            "Auto-detect (Recommended)",
        )

        self.assertEqual(result["message"], "2 timeline(s) générée(s)")
        self.assertEqual(session["batch_id"], "batch_1")
        self.assertEqual([name for name, _ in self.calls], ["build"])
        self.assertFalse(self.calls[0][1]["require_subtitles"])
        self.assertTrue(self.calls[0][1]["queue_render"])

    def test_generate_quality_uses_reusable_manifest_when_transcript_cached(self) -> None:
        transcript = self.root / "output" / "transcripts" / "vod.json"
        transcript.parent.mkdir(parents=True, exist_ok=True)
        transcript.write_text("{}", encoding="utf-8")
        reusable = self.root / "output" / "manifests" / "quality.json"
        reusable.write_text("{}", encoding="utf-8")
        session = {"manifest": self.manifest, "detected_vod": self.vod, "used_manifest_fallback": False}

        result = generate_session_batch(
            self.root,
            object(),
            object(),
            session,
            self.manifest,
            self._presets_data(),
            self._params(require_subtitles=True),
            self._deps(find_reusable_quality_manifest=lambda root, vod, preset_id, use_transcript, subtitle_preset_id: reusable),
            "Minimal clean",
            "Auto-detect (Recommended)",
        )

        self.assertIn("timeline(s) générée(s)", result["message"])
        self.assertEqual(session["manifest"], reusable)
        self.assertEqual([name for name, _ in self.calls], ["build"])
        self.assertTrue(self.calls[0][1]["require_subtitles"])
        self.assertTrue(any("quality_manifest_cache_hit" in line for line in self.logs))

    def test_generate_quality_strict_blocks_fallback_manifest(self) -> None:
        session = {"manifest": self.manifest, "detected_vod": self.vod, "used_manifest_fallback": True}

        result = generate_session_batch(
            self.root,
            object(),
            object(),
            session,
            self.manifest,
            self._presets_data(),
            self._params(require_subtitles=True, strict_manifest=True),
            self._deps(),
            "Minimal clean",
            "Auto-detect (Recommended)",
        )

        self.assertIn("Sous-titres auto annulés", result["message"])
        self.assertEqual(self.calls, [])

    def test_update_composition_builds_without_render_queue(self) -> None:
        session = {"batch_id": "batch_1", "manifest": self.manifest, "detected_vod": self.vod, "used_manifest_fallback": False}

        result = update_session_composition(
            self.root,
            object(),
            object(),
            session,
            self.manifest,
            self._presets_data(),
            self._params(),
            self._deps(),
            "Minimal clean",
            "Auto-detect (Recommended)",
        )

        self.assertEqual(result["message"], "Composition mise à jour sur 2 timeline(s)")
        self.assertEqual([name for name, _ in self.calls], ["build"])
        self.assertFalse(self.calls[0][1]["queue_render"])
        self.assertFalse(self.calls[0][1]["render_master"])


if __name__ == "__main__":
    unittest.main()
