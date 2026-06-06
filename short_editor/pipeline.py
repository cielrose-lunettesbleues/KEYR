from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path

from .clip_builder import (
    build_chapter_candidates_with_skips,
    compute_quota,
    discover_fallback_candidates,
    trim_dead_air_on_boundaries,
    tag_overflow,
)
from .ingest import probe_vod
from .models import BatchReport, ClipCandidate
from .render import render_clips_ffmpeg
from .subtitles import generate_srt_for_clip
from .transcription import ensure_transcript


def _assign_simple_display_names(clips: list[ClipCandidate]) -> None:
    chapter_idx = 1
    auto_idx = 1
    for c in clips:
        if c.seed_type == "chapter":
            c.display_name = f"Chapitre {chapter_idx}"
            chapter_idx += 1
        else:
            c.display_name = f"Auto {auto_idx}"
            auto_idx += 1


def _ensure_dirs(cfg: dict) -> dict[str, Path]:
    p = cfg["paths"]
    dirs = {
        "input": Path(p["input_dir"]),
        "work": Path(p["work_dir"]),
        "output": Path(p["output_dir"]),
        "feedback": Path(p["feedback_dir"]),
    }
    for d in dirs.values():
        d.mkdir(parents=True, exist_ok=True)
    (dirs["output"] / "manifests").mkdir(parents=True, exist_ok=True)
    (dirs["output"] / "reports").mkdir(parents=True, exist_ok=True)
    (dirs["output"] / "clips").mkdir(parents=True, exist_ok=True)
    (dirs["output"] / "transcripts").mkdir(parents=True, exist_ok=True)
    (dirs["output"] / "subtitles").mkdir(parents=True, exist_ok=True)
    return dirs


def _discover_vods(input_dir: Path) -> list[Path]:
    return sorted(input_dir.glob("*.mp4"))


def run_batch(cfg: dict) -> dict:
    dirs = _ensure_dirs(cfg)
    vod_files = _discover_vods(dirs["input"])

    batch_id = datetime.utcnow().strftime("batch_%Y%m%d_%H%M%S")
    all_clips: list[ClipCandidate] = []
    source_vods: list[str] = []
    warnings: list[str] = []
    quota_summary: list[dict] = []

    for vod_path in vod_files:
        manifest = probe_vod(vod_path)
        source_vods.append(str(vod_path))

        chapter_clips, chapter_skips = build_chapter_candidates_with_skips(manifest, cfg)
        for msg in chapter_skips:
            warnings.append(f"{vod_path.name}: {msg}")

        _, target_quota, max_quota = compute_quota(manifest.duration_seconds, cfg["quota"])

        for c in chapter_clips:
            c.clip_id = f"{vod_path.stem}__{c.clip_id}"

        fallback_added = 0
        if len(chapter_clips) < target_quota:
            if not chapter_clips:
                warnings.append(f"No usable chapters found for {vod_path.name}; using fallback discovery.")
            else:
                warnings.append(
                    f"{vod_path.name}: only {len(chapter_clips)} usable chapter clip(s), completing to target {target_quota} with fallback discovery."
                )
            fallback_clips = discover_fallback_candidates(manifest, cfg, dirs["work"])
            for c in fallback_clips:
                c.clip_id = f"{vod_path.stem}__{c.clip_id}"

            needed = max(0, target_quota - len(chapter_clips))
            fallback_selected = _select_non_overlapping_fallback(chapter_clips, fallback_clips, needed, overlap_threshold=0.4)
            if len(fallback_selected) < needed:
                relaxed_needed = needed - len(fallback_selected)
                relaxed_pool = [c for c in fallback_clips if c not in fallback_selected]
                relaxed_more = _select_non_overlapping_fallback(
                    chapter_clips + fallback_selected,
                    relaxed_pool,
                    relaxed_needed,
                    overlap_threshold=0.55,
                )
                fallback_selected.extend(relaxed_more)
            fallback_added = len(fallback_selected)
            chapter_clips.extend(fallback_selected)

        chapter_clips = tag_overflow(chapter_clips, max_quota)
        warnings.extend(trim_dead_air_on_boundaries(manifest, chapter_clips, cfg, dirs["work"]))

        captions_cfg = cfg.get("captions", {})
        captions_enabled = bool(captions_cfg.get("enabled", True))
        transcript_path: Path | None = None
        if captions_enabled:
            try:
                transcript_path = ensure_transcript(vod_path, cfg, dirs["output"] / "transcripts")
            except Exception as exc:
                warnings.append(f"{vod_path.name}: transcript failed: {exc}")

        if captions_enabled and transcript_path is not None:
            subtitle_dir = dirs["output"] / "subtitles" / batch_id
            for c in chapter_clips:
                out_srt = subtitle_dir / f"{c.clip_id}.srt"
                ok = generate_srt_for_clip(transcript_path, c.start_seconds, c.end_seconds, out_srt, captions_cfg)
                if ok:
                    c.subtitle_path = str(out_srt)

        all_clips.extend(chapter_clips)
        quota_summary.append(
            {
                "vod": vod_path.name,
                "target_quota": target_quota,
                "max_quota": max_quota,
                "chapter_used": len([c for c in chapter_clips if c.seed_type == "chapter"]),
                "fallback_added": fallback_added,
                "total_selected": len(chapter_clips),
            }
        )

        vod_manifest_path = dirs["work"] / f"{vod_path.stem}.manifest.json"
        with vod_manifest_path.open("w", encoding="utf-8") as f:
            json.dump(manifest.to_dict(), f, indent=2)
            f.write("\n")

    _assign_simple_display_names(all_clips)

    report = BatchReport(
        batch_id=batch_id,
        source_vods=source_vods,
        clips=all_clips,
        pipeline_version=cfg["pipeline_version"],
    )

    manifest_out = dirs["output"] / "manifests" / f"{batch_id}.json"
    with manifest_out.open("w", encoding="utf-8") as f:
        report_dict = report.to_dict()
        report_dict["warnings"] = warnings
        report_dict["quota_summary"] = quota_summary
        json.dump(report_dict, f, indent=2)
        f.write("\n")

    feedback_template = dirs["feedback"] / "latest_feedback.csv"
    _write_feedback_template(feedback_template, all_clips)

    csv_report = dirs["output"] / "reports" / f"{batch_id}.csv"
    _write_csv_report(csv_report, all_clips)

    clips_out_dir = dirs["output"] / "clips" / batch_id
    rendered_map, render_warnings = render_clips_ffmpeg(all_clips, cfg, clips_out_dir)
    warnings.extend(render_warnings)

    review_index = dirs["output"] / "reports" / f"{batch_id}.review.csv"
    _write_review_index(review_index, all_clips, rendered_map)

    return {
        "batch_id": batch_id,
        "vod_count": len(vod_files),
        "clip_count": len(all_clips),
        "rendered_clip_count": len(rendered_map),
        "warnings": warnings,
        "quota_summary": quota_summary,
        "manifest": str(manifest_out),
        "csv_report": str(csv_report),
        "review_index": str(review_index),
        "clips_dir": str(clips_out_dir),
        "feedback_template": str(feedback_template),
    }


def _overlap_ratio(a: ClipCandidate, b: ClipCandidate) -> float:
    left = max(a.start_seconds, b.start_seconds)
    right = min(a.end_seconds, b.end_seconds)
    if right <= left:
        return 0.0
    inter = right - left
    shortest = max(0.001, min(a.end_seconds - a.start_seconds, b.end_seconds - b.start_seconds))
    return inter / shortest


def _clips_too_close(a: ClipCandidate, b: ClipCandidate, overlap_threshold: float, min_center_distance_seconds: float = 60.0) -> bool:
    if _overlap_ratio(a, b) > overlap_threshold:
        return True
    a_center = a.start_seconds + ((a.end_seconds - a.start_seconds) / 2.0)
    b_center = b.start_seconds + ((b.end_seconds - b.start_seconds) / 2.0)
    return abs(a_center - b_center) < min_center_distance_seconds


def _select_non_overlapping_fallback(
    existing: list[ClipCandidate],
    candidates: list[ClipCandidate],
    needed: int,
    overlap_threshold: float = 0.4,
) -> list[ClipCandidate]:
    if needed <= 0:
        return []
    selected: list[ClipCandidate] = []
    for c in candidates:
        too_close = any(_clips_too_close(c, e, overlap_threshold) for e in existing)
        too_close = too_close or any(_clips_too_close(c, s, overlap_threshold) for s in selected)
        if too_close:
            continue
        selected.append(c)
        if len(selected) >= needed:
            break
    return selected


def _write_feedback_template(path: Path, clips: list[ClipCandidate]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["clip_id", "decision", "reason", "notes"])
        for c in clips:
            writer.writerow([c.clip_id, "", "", ""])


def _write_csv_report(path: Path, clips: list[ClipCandidate]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "clip_id",
                "display_name",
                "source_path",
                "start_seconds",
                "end_seconds",
                "mandatory",
                "seed_type",
                "score",
                "reason",
                "overflow",
                "subtitle_path",
            ]
        )
        for c in clips:
            writer.writerow(
                [
                    c.clip_id,
                    c.display_name,
                    c.source_path,
                    c.start_seconds,
                    c.end_seconds,
                    c.mandatory,
                    c.seed_type,
                    c.score,
                    c.reason,
                    c.overflow,
                    c.subtitle_path,
                ]
            )


def _write_review_index(path: Path, clips: list[ClipCandidate], rendered_map: dict[str, str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["clip_id", "display_name", "file_path", "start_seconds", "end_seconds", "seed_type", "mandatory", "reason", "overflow", "subtitle_path"])
        for c in clips:
            writer.writerow(
                [
                    c.clip_id,
                    c.display_name,
                    rendered_map.get(c.clip_id, ""),
                    c.start_seconds,
                    c.end_seconds,
                    c.seed_type,
                    c.mandatory,
                    c.reason,
                    c.overflow,
                    c.subtitle_path,
                ]
            )
