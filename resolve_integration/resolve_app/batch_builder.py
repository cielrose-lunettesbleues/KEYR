from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from resolve_integration.resolve_app.plans import ClipPlan, parse_manifest, plan_key, safe_name_token

ProgressCallback = Callable[[str, int, int, str], None]


@dataclass
class BatchBuildDeps:
    log: Callable[[str], None]
    load_pipeline_config: Callable[[Path], dict[str, Any]]
    transcript_path_for_vod: Callable[[Path, Path], Path]
    ensure_vertical_project_settings: Callable[[Any], None]
    ensure_batch_folder: Callable[[Any, str], Any]
    ensure_playback_fps_60: Callable[[Any], bool]
    fps_from_project: Callable[[Any], float]
    safe_int_from_project_setting: Callable[[Any, str, int], int]
    ensure_media_item: Callable[[Any, Path], Any | None]
    source_fps_for_media_item: Callable[[Any, Path, float], float]
    delete_timeline_if_exists: Callable[[Any, Any, str], None]
    create_timeline_for_clip_with_preset: Callable[[Any, Any, str, Any, int, int, dict[str, Any]], Any | None]
    log_timeline_diagnostics: Callable[[Any, ClipPlan, float, str], None]
    import_subtitles_to_timeline: Callable[..., tuple[bool, str]]
    append_clip_range: Callable[..., bool]
    queue_render_job: Callable[[Any, Any, Path, str], bool]
    safe_call: Callable[..., Any]
    default_fps: int = 60


def simple_tokenize(text: str) -> list[str]:
    return [token for token in "".join(ch.lower() if ch.isalnum() else " " for ch in text).split() if token]


def semantic_match_score(query: str, text: str) -> float:
    query_tokens = set(simple_tokenize(query))
    text_tokens = set(simple_tokenize(text))
    if not query_tokens or not text_tokens:
        return 0.0
    intersection = len(query_tokens.intersection(text_tokens))
    union = len(query_tokens.union(text_tokens))
    return intersection / max(1, union)


def load_transcript_entries(root: Path, source_path: str) -> list[dict[str, Any]]:
    transcript_file = root / "output" / "transcripts" / f"{Path(source_path).stem}.json"
    if not transcript_file.exists():
        return []
    try:
        with transcript_file.open("r", encoding="utf-8") as f:
            data = json.load(f)
        entries = data.get("entries", [])
        return entries if isinstance(entries, list) else []
    except Exception:
        return []


def filter_plans_by_transcript_query(
    root: Path,
    plans: list[ClipPlan],
    query: str,
    max_seconds: int,
    overlap_ratio_from_ranges: Callable[[float, float, float, float], float],
) -> list[ClipPlan]:
    if not query.strip():
        return plans
    normalized_query = query.strip().lower()
    min_score = 0.25
    min_distance_seconds = 12.0
    overlap_threshold = 0.8
    lead_in_seconds = 5.0

    plans_by_source: dict[str, list[ClipPlan]] = {}
    for plan in plans:
        plans_by_source.setdefault(plan.source_path, []).append(plan)

    filtered: list[ClipPlan] = []
    for source_path, source_plans in plans_by_source.items():
        entries = load_transcript_entries(root, source_path)
        if not entries:
            continue

        candidate_windows: list[tuple[float, float, float]] = []
        for entry in entries:
            text = str(entry.get("text", ""))
            score = semantic_match_score(normalized_query, text)
            if normalized_query in text.lower():
                score = max(score, 0.9)
            if score < min_score:
                continue
            raw_start = float(entry.get("start", 0.0))
            start = max(0.0, raw_start - lead_in_seconds)
            end = start + float(max_seconds)
            candidate_windows.append((score, start, end))

        if not candidate_windows:
            continue

        candidate_windows.sort(key=lambda row: row[0], reverse=True)

        deduped_windows: list[tuple[float, float, float]] = []
        for score, start, end in candidate_windows:
            too_close = False
            for _, kept_start, kept_end in deduped_windows:
                if abs(start - kept_start) < min_distance_seconds:
                    too_close = True
                    break
                overlap = overlap_ratio_from_ranges(start, end, kept_start, kept_end)
                if overlap > overlap_threshold:
                    too_close = True
                    break
            if not too_close:
                deduped_windows.append((score, start, end))

        if not deduped_windows:
            continue

        used = min(len(source_plans), len(deduped_windows))
        for idx in range(used):
            plan = source_plans[idx]
            _, start, end = deduped_windows[idx]
            plan.start_seconds = start
            plan.end_seconds = end
            filtered.append(plan)

    return filtered


def resolve_existing_source(
    root: Path,
    raw_source_path: str,
    detected_vod_path: Path | None,
    user_vod_dir: Path | None,
    remap_notices: set[str],
    warnings: list[str],
    source_remap: dict[str, Path] | None = None,
) -> Path | None:
    source = Path(raw_source_path)
    if not source.is_absolute():
        source = (root / source).resolve()
    if source_remap:
        clean = source_remap.get(str(source).lower())
        if clean and clean.exists():
            remap_notices.add(f"Using clean VOD (track-filtered): {clean.name}")
            return clean
    if source.exists():
        return source

    file_name = source.name
    if detected_vod_path is not None and detected_vod_path.exists():
        remap_notices.add(f"Manifest source missing, remapped to selected Resolve clip: {detected_vod_path}")
        return detected_vod_path

    if user_vod_dir is not None and user_vod_dir.exists():
        direct = user_vod_dir / file_name
        if direct.exists():
            remap_notices.add(f"Manifest source missing, remapped from VOD folder: {direct}")
            return direct
        matches = list(user_vod_dir.rglob(file_name))
        if len(matches) == 1 and matches[0].exists():
            remap_notices.add(f"Manifest source missing, remapped from VOD folder: {matches[0]}")
            return matches[0]
        if len(matches) > 1:
            warnings.append(f"Multiple candidates for missing source '{file_name}' in VOD folder: {user_vod_dir}")
    return None


def build_from_manifest(
    root: Path,
    project: Any,
    media_pool: Any,
    manifest_path: Path,
    output_dir: Path,
    preset_name: str,
    selected_preset: dict[str, Any],
    transcript_query: str,
    render_master: bool,
    queue_render: bool,
    deps: BatchBuildDeps,
    overlap_ratio_from_ranges: Callable[[float, float, float, float], float],
    detected_vod_path: Path | None = None,
    user_vod_dir: Path | None = None,
    require_subtitles: bool = False,
    subtitle_template_name: str = "",
    subtitle_offset_ms: int = -500,
    subtitle_style: dict[str, Any] | None = None,
    subtitle_captions_cfg: dict[str, Any] | None = None,
    progress_cb: ProgressCallback | None = None,
    source_remap: dict[str, Path] | None = None,
) -> tuple[str, dict[str, ClipPlan], list[Any], list[str]]:
    batch_id, plans = parse_manifest(manifest_path)

    max_clip_seconds = int(selected_preset.get("max_clip_seconds", 45))
    if transcript_query.strip():
        plans = filter_plans_by_transcript_query(root, plans, transcript_query, max_clip_seconds, overlap_ratio_from_ranges)
        deps.log(f"Transcript query filtered plans to {len(plans)} clip(s)")

    if not plans:
        return batch_id, {}, [], ["No valid clip plans in manifest."]

    deps.ensure_vertical_project_settings(project)
    deps.ensure_batch_folder(media_pool, batch_id)
    playback_ok = deps.ensure_playback_fps_60(project)
    project_fps = deps.fps_from_project(project)
    playback_fps = deps.safe_int_from_project_setting(project, "timelinePlaybackFrameRate", deps.default_fps)
    deps.log(f"project_playback_diag timelineFrameRate={project_fps} timelinePlaybackFrameRate={playback_fps}")

    created_timelines: list[Any] = []
    warnings: list[str] = []
    if not playback_ok or playback_fps != 60:
        warnings.append(
            f"Resolve playback frame rate is {playback_fps} (expected 60). Preview may appear slowed/choppy until project playback is set to 60 fps."
        )
    plan_map: dict[str, ClipPlan] = {}
    resolved_source_by_clip: dict[str, Path] = {}
    source_fps_by_clip: dict[str, float] = {}
    source_fps_cache: dict[str, float] = {}
    used_timeline_names: set[str] = set()
    remap_notices: set[str] = set()
    subtitle_eligible = 0
    subtitle_imported = 0
    transcript_path_by_source: dict[str, Path] = {}

    if require_subtitles:
        root_str = str(root)
        if root_str not in sys.path:
            sys.path.insert(0, root_str)
        from short_editor.captions import build_textplus_segments_for_clip
        from short_editor.transcription import ensure_transcript

        captions_cfg_for_textplus = subtitle_captions_cfg or deps.load_pipeline_config(root).get("captions", {})

    total_plans = max(1, len(plans))
    if callable(progress_cb):
        progress_cb("Batch", 0, total_plans, "Preparation timelines")

    for idx_plan, plan in enumerate(plans, start=1):
        source = resolve_existing_source(root, plan.source_path, detected_vod_path, user_vod_dir, remap_notices, warnings, source_remap=source_remap)
        if source is None:
            raw_source = Path(plan.source_path)
            if not raw_source.is_absolute():
                raw_source = (root / raw_source).resolve()
            warnings.append(f"Missing source file: {raw_source}")
            if callable(progress_cb):
                progress_cb("Batch", idx_plan, total_plans, f"Skip source manquante {idx_plan}/{total_plans}")
            continue
        if not source.exists():
            warnings.append(f"Missing source file: {source}")
            if callable(progress_cb):
                progress_cb("Batch", idx_plan, total_plans, f"Skip source absente {idx_plan}/{total_plans}")
            continue

        item = deps.ensure_media_item(media_pool, source)
        if item is None:
            warnings.append(f"Could not import media: {source}")
            if callable(progress_cb):
                progress_cb("Batch", idx_plan, total_plans, f"Skip import media {idx_plan}/{total_plans}")
            continue

        source_key = str(source.resolve()).lower()
        source_fps = source_fps_cache.get(source_key)
        if source_fps is None:
            source_fps = deps.source_fps_for_media_item(item, source, project_fps)
            source_fps_cache[source_key] = source_fps
        start_frame = int(round(plan.start_seconds * source_fps))
        end_frame = int(round(plan.end_seconds * source_fps))
        if end_frame <= start_frame:
            warnings.append(f"Invalid range for {plan.clip_id}")
            if callable(progress_cb):
                progress_cb("Batch", idx_plan, total_plans, f"Skip range invalide {idx_plan}/{total_plans}")
            continue
        deps.log(
            f"clip_frame_map clip={plan.clip_id} project_fps={project_fps} source_fps={source_fps:.3f} "
            f"start_s={plan.start_seconds:.3f} end_s={plan.end_seconds:.3f} start_f={start_frame} end_f={end_frame}"
        )

        timeline_name = str(plan.timeline_name or "").strip()
        if not timeline_name:
            display = safe_name_token(plan.display_name or plan.clip_id, limit=84)
            timeline_name = f"{batch_id}__{display}"
        if timeline_name in used_timeline_names:
            dup_idx = 2
            base_name = timeline_name
            while f"{base_name} ({dup_idx})" in used_timeline_names:
                dup_idx += 1
            timeline_name = f"{base_name} ({dup_idx})"
        used_timeline_names.add(timeline_name)
        deps.delete_timeline_if_exists(project, media_pool, timeline_name)
        timeline = deps.create_timeline_for_clip_with_preset(project, media_pool, timeline_name, item, start_frame, end_frame, selected_preset)
        if timeline is None:
            warnings.append(f"Could not create timeline for {plan.clip_id}")
            if callable(progress_cb):
                progress_cb("Batch", idx_plan, total_plans, f"Echec timeline {idx_plan}/{total_plans}")
            continue

        expected_duration_s = max(0.0, plan.end_seconds - plan.start_seconds)
        preset_mode = str(selected_preset.get("mode", "single"))
        deps.log_timeline_diagnostics(timeline, plan, expected_duration_s, preset_mode)

        if require_subtitles:
            subtitle_eligible += 1
            try:
                # Use original (pre-remap) source for transcript lookup so filenames match
                if source_remap:
                    _orig = resolve_existing_source(root, plan.source_path, detected_vod_path, user_vod_dir, set(), [], source_remap=None)
                    source_for_transcript = _orig if (_orig is not None and _orig.exists()) else source
                else:
                    source_for_transcript = source
                source_key_for_transcript = str(source_for_transcript.resolve()).lower()
                transcript_path = transcript_path_by_source.get(source_key_for_transcript)
                if transcript_path is None:
                    transcript_path = deps.transcript_path_for_vod(root, source_for_transcript)
                    if not transcript_path.exists():
                        transcript_path = ensure_transcript(source_for_transcript, deps.load_pipeline_config(root), root / "output" / "transcripts", progress_cb=progress_cb)
                    transcript_path_by_source[source_key_for_transcript] = transcript_path
                segments = build_textplus_segments_for_clip(
                    transcript_path,
                    plan.start_seconds,
                    plan.end_seconds,
                    captions_cfg_for_textplus,
                )
                if not segments:
                    warnings.append(f"No transcript caption segments for {plan.clip_id}")
                    deps.log(f"subtitle_textplus_no_segments clip={plan.clip_id} transcript={transcript_path}")
                else:
                    ok_sub, sub_msg = deps.import_subtitles_to_timeline(
                        project,
                        media_pool,
                        timeline,
                        subtitle_segments=segments,
                        template_name=subtitle_template_name,
                        offset_ms=subtitle_offset_ms,
                        subtitle_style=subtitle_style,
                    )
                    if ok_sub:
                        subtitle_imported += 1
                        deps.log(f"subtitle_textplus_import_ok clip={plan.clip_id} msg={sub_msg}")
                        deps.log_timeline_diagnostics(timeline, plan, expected_duration_s, preset_mode + "+textplus")
                    else:
                        warnings.append(f"Text+ subtitle import failed for {plan.clip_id}: {sub_msg}")
                        deps.log(f"subtitle_textplus_import_failed clip={plan.clip_id} msg={sub_msg}")
            except Exception as exc:
                warnings.append(f"Text+ subtitle generation failed for {plan.clip_id}: {exc}")
                deps.log(f"subtitle_textplus_generation_failed clip={plan.clip_id} err={exc}")
            if callable(progress_cb):
                progress_cb(
                    "Application sous-titres",
                    subtitle_imported,
                    max(1, subtitle_eligible),
                    f"Sous-titres timeline {subtitle_imported}/{max(1, subtitle_eligible)}",
                )
        created_timelines.append(timeline)
        plan_map[plan_key(plan)] = plan
        resolved_source_by_clip[plan_key(plan)] = source
        source_fps_by_clip[plan_key(plan)] = source_fps
        if callable(progress_cb):
            progress_cb("Batch", idx_plan, total_plans, f"Timeline {idx_plan}/{total_plans}")

    master_timeline = None
    if created_timelines:
        master_name = f"{batch_id}__MASTER_REVIEW"
        deps.delete_timeline_if_exists(project, media_pool, master_name)
        master_timeline = deps.safe_call(media_pool, "CreateEmptyTimeline", master_name)
        if master_timeline:
            for plan in plans:
                source = resolved_source_by_clip.get(plan_key(plan))
                item = deps.ensure_media_item(media_pool, source) if source and source.exists() else None
                if not item:
                    continue
                source_fps = source_fps_by_clip.get(plan_key(plan), float(max(1, project_fps)))
                start_frame = int(round(plan.start_seconds * source_fps))
                end_frame = int(round(plan.end_seconds * source_fps))
                if end_frame <= start_frame:
                    continue
                deps.append_clip_range(media_pool, master_timeline, item, start_frame, end_frame, track_index=1)

    if queue_render:
        queued = 0
        for timeline in created_timelines:
            if deps.queue_render_job(project, timeline, output_dir, preset_name):
                queued += 1
        if render_master and master_timeline and deps.queue_render_job(project, master_timeline, output_dir, preset_name):
            queued += 1
        deps.log(f"Queued render jobs: {queued}")

    for notice in sorted(remap_notices):
        warnings.append(notice)

    if require_subtitles:
        if subtitle_eligible == 0:
            warnings.append("No clips were eligible for Text+ subtitle generation in this batch.")
        elif subtitle_imported == 0:
            warnings.append("Text+ subtitle import did not succeed on any timeline.")
        deps.log(f"subtitle_import_summary eligible={subtitle_eligible} imported={subtitle_imported}")

    if callable(progress_cb):
        progress_cb("Batch", total_plans, total_plans, "Batch termine")

    # Navigate to the first clip timeline so Resolve shows a short single-clip view,
    # not the potentially very long master review timeline.
    if created_timelines:
        deps.safe_call(project, "SetCurrentTimeline", created_timelines[0])

    return batch_id, plan_map, created_timelines, warnings
