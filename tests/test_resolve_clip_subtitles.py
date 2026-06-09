from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any

from resolve_integration.resolve_app.clip_subtitles import ClipSubtitleDeps, add_subtitles_to_selected_clip


class ClipSubtitlesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.source = self.root / "input" / "vod.mp4"
        self.source.parent.mkdir(parents=True, exist_ok=True)
        self.source.write_bytes(b"fake")
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _ctx(self) -> dict[str, Any]:
        return {
            "project": object(),
            "timeline": object(),
            "media_pool": object(),
            "source_path": str(self.source),
            "clip_start": 1.0,
            "clip_end": 3.0,
            "timeline_name": "Timeline",
            "item_name": "Clip",
            "subtitle_timing_segments": [{"source_start": 1.0, "source_end": 3.0, "timeline_start": 0.0}],
            "subtitle_source_start": 1.0,
        }

    def _deps(self, *, segments: list[dict[str, Any]] | None = None, import_ok: bool = True, ctx_ok: bool = True) -> ClipSubtitleDeps:
        def selected_clip_subtitle_context(_resolve: Any) -> tuple[bool, str, dict[str, Any]]:
            return (True, "ok", self._ctx()) if ctx_ok else (False, "No active timeline", {})

        def ensure_transcript(source_path: Path, cfg: dict[str, Any], output_dir: Path) -> Path:
            self.calls.append(("ensure_transcript", {"source_path": source_path, "cfg": cfg, "output_dir": output_dir}))
            output_dir.mkdir(parents=True, exist_ok=True)
            transcript = output_dir / f"{source_path.stem}.json"
            transcript.write_text("{}", encoding="utf-8")
            return transcript

        def build_segments(transcript_path: Path, clip_start: float, clip_end: float, captions_cfg: dict[str, Any]) -> list[dict[str, Any]]:
            self.calls.append(
                (
                    "build_segments",
                    {"transcript_path": transcript_path, "clip_start": clip_start, "clip_end": clip_end, "captions_cfg": captions_cfg},
                )
            )
            if segments is not None:
                return segments
            return [{"start": 0.0, "end": 1.0, "text": "Salut"}]

        def import_subtitles_to_timeline(**kwargs: Any) -> tuple[bool, str]:
            self.calls.append(("import", kwargs))
            return (True, "ok") if import_ok else (False, "Text+ failed")

        return ClipSubtitleDeps(
            selected_clip_subtitle_context=selected_clip_subtitle_context,
            load_pipeline_config=lambda root: {"captions": {"words_per_subtitle": 4}},
            merge_subtitle_preset_into_config=lambda cfg, preset: {**cfg, "captions": {"words_per_subtitle": (preset or {}).get("words_per_subtitle", 3)}},
            subtitle_style_from_preset=lambda preset: {"font": str((preset or {}).get("font", ""))},
            import_subtitles_to_timeline=import_subtitles_to_timeline,
            build_textplus_segments_for_clip=build_segments,
            ensure_transcript=ensure_transcript,
        )

    def test_add_subtitles_to_selected_clip_imports_textplus_segments(self) -> None:
        result = add_subtitles_to_selected_clip(
            self.root,
            object(),
            {"font": "Arial", "words_per_subtitle": 5},
            "ShortEditor Caption",
            "-250",
            self._deps(),
            "Auto-detect (Recommended)",
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["message"], "Sous-titre Text+ appliqué sur la timeline (strict): 1 segment(s)")
        self.assertEqual([name for name, _ in self.calls], ["ensure_transcript", "build_segments", "import"])
        import_kwargs = self.calls[-1][1]
        self.assertEqual(import_kwargs["template_name"], "ShortEditor Caption")
        self.assertEqual(import_kwargs["offset_ms"], -250)
        self.assertEqual(import_kwargs["subtitle_style"], {"font": "Arial"})
        self.assertEqual(import_kwargs["timing_segments"], [{"source_start": 1.0, "source_end": 3.0, "timeline_start": 0.0}])
        self.assertEqual(import_kwargs["subtitle_source_start"], 1.0)

    def test_add_subtitles_returns_message_when_context_missing(self) -> None:
        result = add_subtitles_to_selected_clip(
            self.root,
            object(),
            {},
            "",
            "-500",
            self._deps(ctx_ok=False),
            "Auto-detect (Recommended)",
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["message"], "No active timeline")
        self.assertEqual(self.calls, [])

    def test_add_subtitles_returns_message_when_no_segments(self) -> None:
        result = add_subtitles_to_selected_clip(
            self.root,
            object(),
            {},
            "",
            "bad-offset",
            self._deps(segments=[]),
            "Auto-detect (Recommended)",
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["message"], "Aucun contenu de sous-titres trouvé pour la plage du clip sélectionné.")
        self.assertEqual([name for name, _ in self.calls], ["ensure_transcript", "build_segments"])

    def test_add_subtitles_reports_textplus_import_failure(self) -> None:
        result = add_subtitles_to_selected_clip(
            self.root,
            object(),
            {},
            "",
            "bad-offset",
            self._deps(import_ok=False),
            "Auto-detect (Recommended)",
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["message"], "Mode strict: impossible d'appliquer le sous-titre Text+ autonome.")
        self.assertEqual(result["warnings"], ["Erreur d'import Text+: Text+ failed"])
        self.assertEqual(self.calls[-1][1]["offset_ms"], -500)
        self.assertEqual(self.calls[-1][1]["template_name"], "Auto-detect (Recommended)")


if __name__ == "__main__":
    unittest.main()
