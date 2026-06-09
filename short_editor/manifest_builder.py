from __future__ import annotations

import io
import json
import uuid
import warnings
from contextlib import redirect_stderr
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .chapters import build_chapter_candidates_with_skips, compute_quota
from .fallback import discover_fallback_candidates
from .ingest import probe_vod
from .models import ClipCandidate
from .selection import ranges_too_close, select_non_overlapping_dicts
from .trimming import trim_dead_air_on_boundaries
from .transcription import ensure_transcript


ProgressCallback = Callable[[str, int, int, str], None]
LogCallback = Callable[[str], None]


def assign_simple_display_names_dict(clips: list[dict[str, Any]]) -> None:
    chapter_idx = 1
    auto_idx = 1
    for clip in clips:
        if str(clip.get("seed_type", "")) == "chapter":
            clip["display_name"] = f"Chapitre {chapter_idx}"
            chapter_idx += 1
        else:
            clip["display_name"] = f"Auto {auto_idx}"
            auto_idx += 1


def safe_name_token(text: str, limit: int = 72) -> str:
    forbidden = set('\\/:*?"<>|')
    cleaned = "".join(ch if (ch.isalnum() or ch in "-_ ") and ch not in forbidden else " " for ch in text)
    cleaned = " ".join(cleaned.split())
    if not cleaned:
        cleaned = "clip"
    return cleaned[:limit]


def assign_timeline_names_dict(clips: list[dict[str, Any]], batch_id: str) -> None:
    used_timeline_names: set[str] = set()
    for clip in clips:
        display = safe_name_token(str(clip.get("display_name") or clip.get("clip_id") or "clip"), limit=84)
        timeline_name = f"{batch_id}__{display}"
        if timeline_name in used_timeline_names:
            dup_idx = 2
            base_name = timeline_name
            while f"{base_name} ({dup_idx})" in used_timeline_names:
                dup_idx += 1
            timeline_name = f"{base_name} ({dup_idx})"
        used_timeline_names.add(timeline_name)
        clip["timeline_name"] = timeline_name


def dedupe_fallback_clip_dicts(clips: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    kept: list[dict[str, Any]] = []
    out_warnings: list[str] = []
    for clip in clips:
        seed_type = str(clip.get("seed_type", ""))
        if seed_type == "chapter":
            kept.append(clip)
            continue

        try:
            start = float(clip.get("start_seconds", 0.0))
            end = float(clip.get("end_seconds", 0.0))
        except Exception:
            kept.append(clip)
            continue

        duplicate_of = None
        for existing in kept:
            if str(existing.get("source_path", "")) != str(clip.get("source_path", "")):
                continue
            try:
                ex_start = float(existing.get("start_seconds", 0.0))
                ex_end = float(existing.get("end_seconds", 0.0))
            except Exception:
                continue
            if ranges_too_close(start, end, ex_start, ex_end):
                duplicate_of = existing
                break

        if duplicate_of is not None:
            name = str(clip.get("clip_id") or clip.get("display_name") or "fallback")
            kept_name = str(duplicate_of.get("clip_id") or duplicate_of.get("display_name") or "clip")
            out_warnings.append(f"{name}: skipped fallback too close to {kept_name}")
            continue
        kept.append(clip)
    return kept, out_warnings


def _clip_dict_to_candidate(data: dict[str, Any], default_source_path: str) -> ClipCandidate:
    return ClipCandidate(
        clip_id=str(data.get("clip_id", "")),
        display_name=str(data.get("display_name", "")),
        source_path=str(data.get("source_path", default_source_path)),
        start_seconds=float(data.get("start_seconds", 0.0)),
        end_seconds=float(data.get("end_seconds", 0.0)),
        mandatory=bool(data.get("mandatory", False)),
        seed_type=str(data.get("seed_type", "unknown")),
        score=float(data.get("score", 0.0)),
        reason=str(data.get("reason", "")),
        overflow=bool(data.get("overflow", False)),
    )


def generate_manifest_for_vod(
    root: Path,
    vod_path: Path,
    cfg: dict[str, Any],
    generate_subtitles: bool = True,
    use_transcript_for_selection: bool = False,
    progress_cb: ProgressCallback | None = None,
    preset_id: str = "",
    subtitle_preset_id: str = "",
    log_cb: LogCallback | None = None,
) -> Path:
    def log(message: str) -> None:
        if callable(log_cb):
            log_cb(message)

    manifest = probe_vod(vod_path)
    if callable(progress_cb):
        progress_cb("Batch+Subtitles", 5, 100, "Analyse du VOD")

    transcript_path_cached = (root / "output" / "transcripts" / f"{vod_path.stem}.json").resolve()
    transcript_exists = transcript_path_cached.exists()

    if use_transcript_for_selection:
        try:
            if transcript_exists:
                log(f"transcript_selection_cache_hit vod={vod_path} transcript={transcript_path_cached}")
            else:
                ensure_transcript(vod_path, cfg, root / "output" / "transcripts", progress_cb=progress_cb)
                log(f"transcript_selection_enabled vod={vod_path}")
        except Exception as exc:
            log(f"transcript_selection_failed vod={vod_path} err={exc}")

    chapter_clips, chapter_skips = build_chapter_candidates_with_skips(manifest, cfg)
    manifest_warnings = [f"{vod_path.name}: {msg}" for msg in chapter_skips]
    _, target_quota, max_quota = compute_quota(manifest.duration_seconds, cfg["quota"])

    selected = [clip.to_dict() for clip in chapter_clips]
    if len(selected) < target_quota:
        fallback = [clip.to_dict() for clip in discover_fallback_candidates(manifest, cfg, root / "work")]
        needed = max(0, target_quota - len(selected))
        selected.extend(select_non_overlapping_dicts(selected, fallback, needed))
    if callable(progress_cb):
        progress_cb("Batch+Subtitles", 20, 100, "Selection des clips terminee")

    batch_id = f"batch_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    clip_objs: list[dict[str, Any]] = []
    for idx, clip in enumerate(selected):
        clip["clip_id"] = f"{vod_path.stem}__{clip['clip_id']}"
        clip["overflow"] = idx >= max_quota
        clip_objs.append(clip)

    trim_candidates = [_clip_dict_to_candidate(clip, manifest.source_path) for clip in clip_objs]
    trim_warnings = trim_dead_air_on_boundaries(manifest, trim_candidates, cfg, root / "work")
    for idx, candidate in enumerate(trim_candidates):
        clip_objs[idx]["start_seconds"] = candidate.start_seconds
        clip_objs[idx]["end_seconds"] = candidate.end_seconds
        clip_objs[idx]["reason"] = candidate.reason
    manifest_warnings.extend(trim_warnings)

    clip_objs, proximity_warnings = dedupe_fallback_clip_dicts(clip_objs)
    manifest_warnings.extend(proximity_warnings)
    assign_simple_display_names_dict(clip_objs)
    assign_timeline_names_dict(clip_objs, batch_id)

    captions_cfg = cfg.get("captions", {})
    captions_enabled = bool(captions_cfg.get("enabled", True)) and bool(generate_subtitles)
    if captions_enabled:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                with redirect_stderr(io.StringIO()):
                    if transcript_exists and transcript_path_cached.exists():
                        log(f"subtitle_transcript_cache_hit vod={vod_path} transcript={transcript_path_cached}")
                    else:
                        transcript_path_cached = ensure_transcript(vod_path, cfg, root / "output" / "transcripts", progress_cb=progress_cb)
                    log(f"transcript_ok_textplus vod={vod_path} transcript={transcript_path_cached}")
            if callable(progress_cb):
                progress_cb("Batch+Subtitles", 90, 100, "Transcript pret pour Text+")
        except Exception as exc:
            log(f"subtitle_transcript_generation_error vod={vod_path.name} err={exc}")
            manifest_warnings.append(f"{vod_path.name}: transcript generation failed for Text+: {exc}")
    else:
        log(f"subtitle_generation_skipped vod={vod_path.name} reason=disabled_for_this_manifest")

    out = {
        "batch_id": batch_id,
        "source_vods": [str(vod_path)],
        "clips": clip_objs,
        "pipeline_version": cfg.get("pipeline_version", "0.1.0"),
        "meta": {
            "source_vod_path": str(vod_path.resolve()),
            "preset_id": preset_id,
            "subtitle_preset_id": subtitle_preset_id,
            "generated_with_subtitles": bool(captions_enabled),
            "use_transcript_for_selection": bool(use_transcript_for_selection),
            "transcript_path": str(transcript_path_cached),
            "transcript_exists_pre_generation": bool(transcript_exists),
        },
        "warnings": manifest_warnings,
        "quota_summary": [
            {
                "vod": vod_path.name,
                "target_quota": target_quota,
                "max_quota": max_quota,
                "chapter_used": len([clip for clip in clip_objs if clip.get("seed_type") == "chapter"]),
                "fallback_added": len([clip for clip in clip_objs if clip.get("seed_type") != "chapter"]),
                "total_selected": len(clip_objs),
            }
        ],
    }

    out_dir = root / "output" / "manifests"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{batch_id}.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
        f.write("\n")
    if callable(progress_cb):
        progress_cb("Batch+Subtitles", 100, 100, "Manifest ecrit")
    log(f"Auto manifest generated: {out_path}")
    return out_path
