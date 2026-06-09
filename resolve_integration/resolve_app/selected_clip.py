from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from resolve_integration.resolve_app import media_pool, timelines

SafeCall = Callable[..., Any]
Logger = Callable[[str], None]
FpsFromProject = Callable[[Any], int]
SourceFpsForMediaItem = Callable[[Any, Path, int], float]


def to_int(value: Any) -> int | None:
    try:
        return int(float(value))
    except Exception:
        return None


def selected_clip_subtitle_context(
    resolve: Any,
    safe_call: SafeCall,
    log: Logger,
    fps_from_project: FpsFromProject,
    source_fps_for_media_item: SourceFpsForMediaItem,
) -> tuple[bool, str, dict[str, Any]]:
    project_manager = safe_call(resolve, "GetProjectManager")
    project = safe_call(project_manager, "GetCurrentProject") if project_manager else None
    if not project:
        return False, "No open project", {}
    timeline = safe_call(project, "GetCurrentTimeline")
    if not timeline:
        return False, "No active timeline", {}

    project_fps = fps_from_project(project)
    pool = safe_call(project, "GetMediaPool")

    def source_path_from_media_item(media_item: Any) -> str:
        return media_pool.source_path_from_resolve_clip(media_item, safe_call)

    def source_path_from_selected_media() -> str:
        selected_media = safe_call(pool, "GetSelectedClips", default=[]) if pool else []
        selected_first = selected_media[0] if selected_media else None
        return source_path_from_media_item(selected_first)

    def log_unreadable_source(item_obj: Any) -> None:
        name = str(safe_call(item_obj, "GetName", default="") or "") if item_obj else ""
        props = safe_call(item_obj, "GetProperty", default={}) or {} if item_obj else {}
        media_item = safe_call(item_obj, "GetMediaPoolItem") if item_obj else None
        media_props = safe_call(media_item, "GetClipProperty", default={}) or {} if media_item else {}
        prop_keys = ",".join(sorted(str(k) for k in props.keys())) if isinstance(props, dict) else ""
        media_keys = ",".join(sorted(str(k) for k in media_props.keys())) if isinstance(media_props, dict) else ""
        log(f"selected_clip_source_unreadable item={name} item_keys={prop_keys} media_keys={media_keys}")

    def item_from_playhead_or_current() -> Any | None:
        current = safe_call(timeline, "GetCurrentVideoItem")
        if current:
            return current
        video_track_count = int(safe_call(timeline, "GetTrackCount", "video", default=0) or 0)
        if video_track_count <= 0:
            video_track_count = 1
        for track_idx in range(video_track_count, 0, -1):
            item = timelines.get_item_at_current_frame(timeline, track_idx, safe_call)
            if item:
                return item
        return None

    def source_frame_range_from_item(item_obj: Any, record_start: int, record_end: int, source_fps: float) -> tuple[int, int] | None:
        src_in = None
        src_out = None
        for method in ("GetSourceStartFrame", "GetLeftOffset"):
            value = to_int(safe_call(item_obj, method, default=None))
            if value is not None:
                src_in = value
                break
        for method in ("GetSourceEndFrame", "GetRightOffset"):
            value = to_int(safe_call(item_obj, method, default=None))
            if value is not None:
                src_out = value
                break
        if src_in is None or src_out is None:
            all_props = safe_call(item_obj, "GetProperty", default={}) or {}
            if src_in is None:
                src_in = to_int(all_props.get("Source Start"))
            if src_out is None:
                src_out = to_int(all_props.get("Source End"))
        if src_in is None:
            return None
        if src_out is None or src_out <= src_in:
            duration_source_frames = max(1, int(round(max(1, record_end - record_start) * (source_fps / max(1.0, float(project_fps))))))
            src_out = src_in + duration_source_frames
        if src_out <= src_in:
            return None
        return src_in, src_out

    def silence_cut_timeline_context() -> dict[str, Any] | None:
        timeline_name = str(safe_call(timeline, "GetName", default="timeline") or "timeline")
        if not timeline_name.endswith("__silence_cut"):
            return None
        items = timelines.get_timeline_items_on_track(timeline, 1, safe_call)
        if not items:
            return None

        timeline_start_frame = to_int(safe_call(timeline, "GetStartFrame", default=0)) or 0
        source_path = ""
        source_fps = float(project_fps)
        segments: list[dict[str, float]] = []
        for item_obj in sorted(items, key=lambda item: to_int(safe_call(item, "GetStart", default=0)) or 0):
            record_start = to_int(safe_call(item_obj, "GetStart", default=None))
            record_end = to_int(safe_call(item_obj, "GetEnd", default=None))
            if record_start is None or record_end is None or record_end <= record_start:
                continue
            item_source = media_pool.source_path_from_resolve_clip(item_obj, safe_call)
            if not item_source:
                continue
            if source_path and str(Path(item_source).resolve()).lower() != str(Path(source_path).resolve()).lower():
                continue
            if not source_path:
                source_path = item_source
                item_media = safe_call(item_obj, "GetMediaPoolItem")
                source_fps = source_fps_for_media_item(item_media, Path(source_path), project_fps) if item_media else float(project_fps)
            frame_range = source_frame_range_from_item(item_obj, record_start, record_end, source_fps)
            if frame_range is None:
                continue
            src_in, src_out = frame_range
            timeline_start_s = max(0.0, float(record_start - timeline_start_frame) / max(1.0, float(project_fps)))
            segments.append(
                {
                    "source_start": max(0.0, float(src_in) / max(1.0, source_fps)),
                    "source_end": max(0.0, float(src_out) / max(1.0, source_fps)),
                    "timeline_start": timeline_start_s,
                }
            )

        if not source_path or not segments:
            log(f"subtitle_silence_cut_segments_failed timeline={timeline_name} items={len(items)}")
            return None
        segments = [segment for segment in segments if float(segment["source_end"]) > float(segment["source_start"])]
        if not segments:
            return None
        clip_start = min(float(segment["source_start"]) for segment in segments)
        clip_end = max(float(segment["source_end"]) for segment in segments)
        log(f"subtitle_silence_cut_segments={len(segments)} timeline={timeline_name} source={source_path}")
        return {
            "project": project,
            "timeline": timeline,
            "media_pool": pool,
            "source_path": source_path,
            "clip_start": clip_start,
            "clip_end": clip_end,
            "timeline_name": timeline_name,
            "item_name": timeline_name,
            "subtitle_timing_segments": segments,
            "subtitle_source_start": clip_start,
        }

    silence_ctx = silence_cut_timeline_context()
    if silence_ctx is not None:
        return True, "ok", silence_ctx

    item = item_from_playhead_or_current()
    source_path = ""
    fallback_range: tuple[int, int] | None = None

    if item is not None:
        source_path = media_pool.source_path_from_resolve_clip(item, safe_call)
        if not source_path:
            source_path = source_path_from_selected_media()
        if not source_path:
            log_unreadable_source(item)
            return False, "Selected timeline clip has no readable source path. Select the source clip in Media Pool, or place the playhead on a plain video clip.", {}
    else:
        selected_media = safe_call(pool, "GetSelectedClips", default=[]) if pool else []
        selected_first = selected_media[0] if selected_media else None
        if not selected_first:
            return False, "No clip at playhead and no selected clip in Media Pool", {}
        source_path = source_path_from_media_item(selected_first)
        if not source_path:
            return False, "Selected Media Pool clip has no readable source path", {}
        fallback_range = timelines.get_timeline_selected_range(timeline, safe_call)
        if fallback_range is None:
            return False, "No clip at playhead. Select timeline In/Out range to use selected Media Pool clip", {}

    src_in = None
    src_out = None

    if fallback_range is not None:
        src_in, src_out = fallback_range
    else:
        for method in ("GetSourceStartFrame", "GetLeftOffset"):
            value = to_int(safe_call(item, method, default=None))
            if value is not None:
                src_in = value
                break
        for method in ("GetSourceEndFrame", "GetRightOffset"):
            value = to_int(safe_call(item, method, default=None))
            if value is not None:
                src_out = value
                break

        if src_in is None or src_out is None:
            all_props = safe_call(item, "GetProperty", default={}) or {}
            if src_in is None:
                src_in = to_int(all_props.get("Source Start"))
            if src_out is None:
                src_out = to_int(all_props.get("Source End"))

        if src_in is None or src_out is None or src_out <= src_in:
            timeline_start = to_int(safe_call(item, "GetStart", default=None))
            timeline_end = to_int(safe_call(item, "GetEnd", default=None))
            if timeline_start is None or timeline_end is None or timeline_end <= timeline_start:
                return False, "Could not read clip range from timeline item", {}
            src_in = 0
            src_out = max(1, timeline_end - timeline_start)

    clip_start = max(0.0, float(src_in) / max(1, project_fps))
    clip_end = max(clip_start + 0.1, float(src_out) / max(1, project_fps))
    return True, "ok", {
        "project": project,
        "timeline": timeline,
        "media_pool": pool,
        "source_path": source_path,
        "clip_start": clip_start,
        "clip_end": clip_end,
        "timeline_name": str(safe_call(timeline, "GetName", default="timeline")),
        "item_name": str(safe_call(item, "GetName", default="clip")),
    }
