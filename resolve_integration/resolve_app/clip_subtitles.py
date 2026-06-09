from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


@dataclass
class ClipSubtitleDeps:
    selected_clip_subtitle_context: Callable[[Any], tuple[bool, str, dict[str, Any]]]
    load_pipeline_config: Callable[[Path], dict[str, Any]]
    merge_subtitle_preset_into_config: Callable[[dict[str, Any], dict[str, Any] | None], dict[str, Any]]
    subtitle_style_from_preset: Callable[[dict[str, Any] | None], dict[str, Any]]
    import_subtitles_to_timeline: Callable[..., tuple[bool, str]]
    build_textplus_segments_for_clip: Callable[[Path, float, float, dict[str, Any]], list[dict[str, Any]]] | None = None
    ensure_transcript: Callable[[Path, dict[str, Any], Path], Path] | None = None


def _coerce_offset_ms(raw_value: Any) -> int:
    try:
        return int(float(str(raw_value).strip() or "-500"))
    except Exception:
        return -500


def _build_textplus_segments_for_clip(transcript_path: Path, clip_start: float, clip_end: float, captions_cfg: dict[str, Any]) -> list[dict[str, Any]]:
    from short_editor.captions import build_textplus_segments_for_clip

    return build_textplus_segments_for_clip(transcript_path, clip_start, clip_end, captions_cfg)


def _ensure_transcript(source_path: Path, cfg: dict[str, Any], output_dir: Path) -> Path:
    from short_editor.transcription import ensure_transcript

    return ensure_transcript(source_path, cfg, output_dir)


def add_subtitles_to_selected_clip(
    root: Path,
    resolve: Any,
    subtitle_preset: dict[str, Any],
    subtitle_template_name: str,
    subtitle_offset_ms: Any,
    deps: ClipSubtitleDeps,
    subtitle_template_auto_label: str,
) -> dict[str, Any]:
    ok_ctx, ctx_msg, ctx = deps.selected_clip_subtitle_context(resolve)
    if not ok_ctx:
        return {"ok": False, "message": ctx_msg}

    source_path = Path(str(ctx["source_path"]))
    clip_start = float(ctx["clip_start"])
    clip_end = float(ctx["clip_end"])

    cfg = deps.merge_subtitle_preset_into_config(deps.load_pipeline_config(root), subtitle_preset)
    ensure_transcript = deps.ensure_transcript or _ensure_transcript
    build_segments = deps.build_textplus_segments_for_clip or _build_textplus_segments_for_clip
    transcript_path = ensure_transcript(source_path, cfg, root / "output" / "transcripts")
    segments = build_segments(transcript_path, clip_start, clip_end, cfg.get("captions", {}))
    if not segments:
        return {"ok": False, "message": "Aucun contenu de sous-titres trouvé pour la plage du clip sélectionné."}

    template_name = str(subtitle_template_name).strip() or subtitle_template_auto_label
    ok_import, import_msg = deps.import_subtitles_to_timeline(
        project=ctx["project"],
        media_pool=ctx["media_pool"],
        timeline=ctx["timeline"],
        subtitle_segments=segments,
        template_name=template_name,
        offset_ms=_coerce_offset_ms(subtitle_offset_ms),
        subtitle_style=deps.subtitle_style_from_preset(subtitle_preset),
        timing_segments=list(ctx.get("subtitle_timing_segments", []) or []),
        subtitle_source_start=float(ctx.get("subtitle_source_start", clip_start)),
    )
    if not ok_import:
        return {
            "ok": False,
            "message": "Mode strict: impossible d'appliquer le sous-titre Text+ autonome.",
            "warnings": [f"Erreur d'import Text+: {import_msg}"],
        }
    return {
        "ok": True,
        "message": f"Sous-titre Text+ appliqué sur la timeline (strict): {len(segments)} segment(s)",
    }
