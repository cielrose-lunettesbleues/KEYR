from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from resolve_integration.resolve_app.session_actions import (
    SessionActionDeps,
    generate_session_batch,
)


class TestQualityGenerationFlow(unittest.TestCase):
    """Test quality batch generation with subtitles."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmpdir.name)
        (self.root / "output" / "manifests").mkdir(parents=True, exist_ok=True)
        (self.root / "output" / "transcripts").mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        """Clean up test fixtures."""
        self.tmpdir.cleanup()

    def _create_mock_vod(self) -> Path:
        """Create a mock VOD file."""
        vod_path = self.root / "test_vod.mp4"
        vod_path.touch()
        return vod_path

    def _create_mock_manifest_with_subtitles(self, vod_source: str = "test_vod.mp4") -> Path:
        """Create a manifest with subtitle metadata."""
        manifest = {
            "meta": {
                "vod_source": vod_source,
                "batch_id": "batch_quality_test",
                "subtitle_preset_id": "Minimal clean",
                "chapters_count": 2,
            },
            "clips": [
                {
                    "clip_id": "clip_1",
                    "start_seconds": 10.0,
                    "end_seconds": 40.0,
                    "chapter_index": 1,
                    "source_path": vod_source,
                    "audio_analysis": {"voice_detected": True},
                }
            ],
        }
        manifest_path = self.root / "output" / "manifests" / "batch_quality_test.json"
        with manifest_path.open("w") as f:
            json.dump(manifest, f)
        return manifest_path

    def _create_mock_transcript(self, vod_path: Path) -> Path:
        """Create a mock transcript file."""
        transcript_path = self.root / "output" / "transcripts" / f"{vod_path.stem}.json"
        transcript = {
            "language": "fr",
            "duration_seconds": 120.0,
            "segments": [
                {
                    "start": 10.0,
                    "end": 12.0,
                    "text": "Bonjour à tous",
                }
            ],
        }
        with transcript_path.open("w") as f:
            json.dump(transcript, f)
        return transcript_path

    def _create_mock_deps_quality(self, vod_path: Path) -> SessionActionDeps:
        """Create mock dependencies for quality mode."""
        logs: list[str] = []

        def mock_log(msg: str) -> None:
            logs.append(msg)

        def mock_read_manifest_safe(manifest_path: Path) -> dict[str, Any] | None:
            try:
                with manifest_path.open() as f:
                    return json.load(f)
            except Exception:
                return None

        def mock_default_subtitle_presets() -> dict[str, Any]:
            return {"Minimal clean": {"name": "Minimal clean"}}

        def mock_subtitle_style_from_preset(preset: dict[str, Any] | None) -> dict[str, Any]:
            return preset or {}

        def mock_merge_subtitle_preset_into_config(
            config: dict[str, Any], preset: dict[str, Any] | None
        ) -> dict[str, Any]:
            return config

        def mock_load_pipeline_config(root: Path) -> dict[str, Any]:
            return {"captions": {}, "video": {}}

        def mock_manifest_has_valid_subtitles(root: Path, data: dict[str, Any]) -> bool:
            # Quality manifests have valid subtitles
            return True

        def mock_apply_preview_safe_playback(project: Any) -> list[str]:
            return ["Preview safe quality applied"]

        def mock_transcript_path_for_vod(root: Path, vod_path_arg: Path) -> Path:
            return root / "output" / "transcripts" / f"{vod_path_arg.stem}.json"

        def mock_find_reusable_quality_manifest(
            root: Path, vod_path_arg: Path, preset_id: str, use_transcript: bool, subtitle_preset_id: str
        ) -> Path | None:
            # Return None to force generation of new manifest
            return None

        def mock_generate_manifest_for_vod(
            root: Path, vod_path_arg: Path, **kwargs: Any
        ) -> Path:
            return self._create_mock_manifest_with_subtitles(str(vod_path_arg))

        def mock_build_from_manifest(
            root: Path,
            project: Any,
            media_pool: Any,
            manifest_path: Path,
            output_dir: Path,
            preset_name: str,
            selected_preset: dict[str, Any],
            transcript_query: str,
            render_master: bool,
            queue_render: bool = True,
            **kwargs: Any
        ) -> tuple[str, dict[str, Any], list[Any], list[str]]:
            return (
                "batch_quality_test",
                {"clip_1": MagicMock()},
                [MagicMock()],
                ["Subtitles applied"],
            )

        return SessionActionDeps(
            read_manifest_safe=mock_read_manifest_safe,
            default_subtitle_presets=mock_default_subtitle_presets,
            subtitle_style_from_preset=mock_subtitle_style_from_preset,
            merge_subtitle_preset_into_config=mock_merge_subtitle_preset_into_config,
            load_pipeline_config=mock_load_pipeline_config,
            manifest_has_valid_subtitles=mock_manifest_has_valid_subtitles,
            apply_preview_safe_playback=mock_apply_preview_safe_playback,
            transcript_path_for_vod=mock_transcript_path_for_vod,
            find_reusable_quality_manifest=mock_find_reusable_quality_manifest,
            generate_manifest_for_vod=mock_generate_manifest_for_vod,
            build_from_manifest=mock_build_from_manifest,
            log=mock_log,
        )

    def test_quality_generation_with_subtitles(self) -> None:
        """Test quality generation flow with subtitle support."""
        vod_path = self._create_mock_vod()
        self._create_mock_transcript(vod_path)
        manifest_path = self._create_mock_manifest_with_subtitles(vod_path.name)

        session = {
            "manifest": str(manifest_path),
            "detected_vod": str(vod_path),
        }
        params = {
            "output": str(self.root / "output" / "clips"),
            "render_preset": "valo",
            "render_master": False,
            "preset_id": "valo",
            "subtitle_preset_id": "Minimal clean",
            "query": "",
            "require_subtitles": True,
            "preview_safe_quality": True,
        }
        presets_data = {"presets": {"valo": {"name": "valo"}}}
        deps = self._create_mock_deps_quality(vod_path)

        result = generate_session_batch(
            self.root,
            MagicMock(),
            MagicMock(),
            session,
            None,
            presets_data,
            params,
            deps,
            "Minimal clean",
            "Auto-detect",
        )

        self.assertIsInstance(result, dict)
        self.assertIn("timeline(s)", str(result.get("message", "")))
        warnings = result.get("warnings", [])
        self.assertIsInstance(warnings, list)

    def test_quality_generation_requires_detected_vod(self) -> None:
        """Test quality generation fails without detected VOD."""
        manifest_path = self._create_mock_manifest_with_subtitles()

        session = {"manifest": str(manifest_path)}  # No detected_vod
        params = {
            "output": str(self.root / "output" / "clips"),
            "render_preset": "valo",
            "render_master": False,
            "preset_id": "valo",
            "subtitle_preset_id": "Minimal clean",
            "query": "",
            "require_subtitles": True,
            "preview_safe_quality": True,
        }
        presets_data = {"presets": {"valo": {"name": "valo"}}}

        vod_path = self._create_mock_vod()
        deps = self._create_mock_deps_quality(vod_path)

        result = generate_session_batch(
            self.root,
            MagicMock(),
            MagicMock(),
            session,
            None,
            presets_data,
            params,
            deps,
            "Minimal clean",
            "Auto-detect",
        )

        self.assertIsInstance(result, dict)
        self.assertIn("source VOD détectée", str(result.get("message", "")))

    def test_quality_generation_uses_transcript_for_selection(self) -> None:
        """Test quality generation can use transcript for clip selection."""
        vod_path = self._create_mock_vod()
        self._create_mock_transcript(vod_path)
        manifest_path = self._create_mock_manifest_with_subtitles(vod_path.name)

        session = {
            "manifest": str(manifest_path),
            "detected_vod": str(vod_path),
        }
        params = {
            "output": str(self.root / "output" / "clips"),
            "render_preset": "valo",
            "render_master": False,
            "preset_id": "valo",
            "subtitle_preset_id": "Minimal clean",
            "query": "bonjour",
            "use_transcript_for_selection": True,
            "require_subtitles": False,  # Fast mode with transcript selection
            "preview_safe_quality": False,
        }
        presets_data = {"presets": {"valo": {"name": "valo"}}}

        deps = self._create_mock_deps_quality(vod_path)

        result = generate_session_batch(
            self.root,
            MagicMock(),
            MagicMock(),
            session,
            None,
            presets_data,
            params,
            deps,
            "Minimal clean",
            "Auto-detect",
        )

        self.assertIsInstance(result, dict)
        self.assertIn("timeline(s)", str(result.get("message", "")))


if __name__ == "__main__":
    unittest.main()
