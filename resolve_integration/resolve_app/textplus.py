from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any, Callable

SafeCall = Callable[..., Any]
Logger = Callable[[str], None]
CoerceFloat = Callable[[Any, float, float | None, float | None], float]
ParseFpsText = Callable[[Any], float | None]


def find_template_item_by_name(root_folder: Any, wanted_name: str, safe_call: SafeCall) -> Any | None:
    target = wanted_name.strip().lower()

    def walk(folder: Any) -> list[Any]:
        out: list[Any] = []
        out.extend(safe_call(folder, "GetClipList", default=[]) or [])
        for sub in safe_call(folder, "GetSubFolderList", default=[]) or []:
            out.extend(walk(sub))
        return out

    for clip in walk(root_folder):
        name = str(safe_call(clip, "GetName", default="") or "").strip()
        if name.lower() == target:
            return clip
    return None


def ensure_standalone_caption_template(
    media_pool: Any,
    root: Path,
    template_name: str,
    auto_label: str,
    primary_name: str,
    fallback_name: str,
    safe_call: SafeCall,
    log: Logger,
) -> tuple[Any | None, str]:
    root_folder = safe_call(media_pool, "GetRootFolder")
    if root_folder is None:
        return None, "Media Pool root folder not available"

    wanted = str(template_name or "").strip()
    is_auto = wanted == "" or wanted == auto_label
    existing = None
    if not is_auto:
        existing = find_template_item_by_name(root_folder, wanted, safe_call)
    if existing is None:
        existing = find_template_item_by_name(root_folder, primary_name, safe_call)
    if existing is None:
        existing = find_template_item_by_name(root_folder, fallback_name, safe_call)
    if existing is not None:
        log("standalone_template_found")
        return existing, "template_found"

    drb_path = (root / "resolve_integration" / "assets" / "shorteditor-caption-bin.drb").resolve()
    if not drb_path.exists():
        return None, f"Standalone caption template asset missing: {drb_path}"

    imported = safe_call(media_pool, "ImportFolderFromFile", str(drb_path), default=False)
    if not imported:
        return None, f"Failed to import standalone caption template folder: {drb_path.name}"
    log(f"standalone_template_imported_from={drb_path}")

    root_folder = safe_call(media_pool, "GetRootFolder")
    if root_folder is None:
        return None, "Media Pool root folder unavailable after template import"
    loaded = None
    if not is_auto:
        loaded = find_template_item_by_name(root_folder, wanted, safe_call)
    if loaded is None:
        loaded = find_template_item_by_name(root_folder, primary_name, safe_call)
    if loaded is None:
        loaded = find_template_item_by_name(root_folder, fallback_name, safe_call)
    if loaded is None:
        return None, f"Template '{wanted or primary_name}'/'{fallback_name}' not found after importing {drb_path.name}"
    return loaded, "template_imported"


def parse_hex_color(value: str) -> tuple[float, float, float] | None:
    raw = str(value or "").strip()
    if raw.startswith("#"):
        raw = raw[1:]
    if len(raw) != 6 or not re.fullmatch(r"[0-9a-fA-F]{6}", raw):
        return None
    return (int(raw[0:2], 16) / 255.0, int(raw[2:4], 16) / 255.0, int(raw[4:6], 16) / 255.0)


_MISSING_INPUT = object()


def values_match_for_input(actual: Any, expected: Any) -> bool:
    try:
        if actual == expected:
            return True
    except Exception:
        pass
    if isinstance(expected, str):
        try:
            return str(actual) == expected
        except Exception:
            return False
    return False


def set_tool_input(tool: Any, name: str, value: Any, safe_call: SafeCall) -> bool:
    result = safe_call(tool, "SetInput", name, value, default=False)
    if result is True:
        return True
    if result is False:
        return False
    # Resolve often returns None from mutating calls even when they succeed;
    # skip GetInput readback to avoid deadlocking on unresponsive Fusion tools.
    return result is None


def set_tool_input_any(tool: Any, names: list[str], value: Any, safe_call: SafeCall) -> bool:
    for name in names:
        if set_tool_input(tool, name, value, safe_call):
            return True
    return False


def apply_textplus_style(tool: Any, style: dict[str, Any], safe_call: SafeCall, coerce_float: CoerceFloat) -> int:
    applied = 0
    font = str(style.get("font", "")).strip()
    font_style = str(style.get("font_style", "")).strip()
    font_size = style.get("font_size")
    color = parse_hex_color(str(style.get("color", "")))
    pos_x = style.get("position_x")
    pos_y = style.get("position_y")
    if font and set_tool_input_any(tool, ["Font"], font, safe_call):
        applied += 1
    if font_style and set_tool_input_any(tool, ["Style", "FontStyle"], font_style, safe_call):
        applied += 1
    if font_size is not None and set_tool_input_any(tool, ["Size"], coerce_float(font_size, 0.085, 0.01, 0.5), safe_call):
        applied += 1
    if color is not None:
        r, g, b = color
        color_applied = 0
        if set_tool_input_any(tool, ["Red1", "Red"], r, safe_call):
            color_applied += 1
        if set_tool_input_any(tool, ["Green1", "Green"], g, safe_call):
            color_applied += 1
        if set_tool_input_any(tool, ["Blue1", "Blue"], b, safe_call):
            color_applied += 1
        if set_tool_input_any(tool, ["Alpha1", "Alpha"], 1.0, safe_call):
            color_applied += 1
        if color_applied <= 0 and set_tool_input_any(tool, ["Color", "TextColor"], {1: r, 2: g, 3: b, 4: 1.0}, safe_call):
            color_applied += 1
        applied += color_applied
    if pos_x is not None and pos_y is not None:
        x = coerce_float(pos_x, 0.5, 0.0, 1.0)
        y = coerce_float(pos_y, 0.82, 0.0, 1.0)
        if set_tool_input_any(tool, ["Center", "Position"], {1: x, 2: y}, safe_call):
            applied += 1
        elif set_tool_input_any(tool, ["Center", "Position"], [x, y], safe_call):
            applied += 1
    return applied


def set_textplus_item_text(
    timeline_item: Any,
    text_value: str,
    subtitle_style: dict[str, Any] | None,
    safe_call: SafeCall,
    coerce_float: CoerceFloat,
    log: Logger | None = None,
    debug_label: str = "",
) -> tuple[bool, int]:
    def debug(message: str) -> None:
        if callable(log):
            prefix = f" {debug_label}" if debug_label else ""
            log(f"subtitle_textplus_inject{prefix}: {message}")

    comp_count = safe_call(timeline_item, "GetFusionCompCount", default=0) or 0
    debug(f"comp_count_raw={comp_count}")
    try:
        count_i = int(comp_count)
    except Exception:
        count_i = 0
    if count_i <= 0:
        debug("no_fusion_comp")
        return False, 0
    comp = safe_call(timeline_item, "GetFusionCompByIndex", 1, default=None)
    if comp is None:
        debug("fusion_comp_missing")
        return False, 0
    tools = safe_call(comp, "GetToolList", False, "TextPlus", default=None)
    if not isinstance(tools, dict) or not tools:
        debug("textplus_toollist_empty_try_all_tools")
        tools = safe_call(comp, "GetToolList", default={}) or {}
    if not isinstance(tools, dict) or not tools:
        debug("tool_list_empty")
        return False, 0
    debug(f"tool_count={len(tools)}")
    for _, tool in tools.items():
        styled_ok = set_tool_input(tool, "StyledText", text_value, safe_call)
        text_ok = False if styled_ok else set_tool_input(tool, "Text", text_value, safe_call)
        debug(f"setinput styled={styled_ok} text={text_ok}")
        ok = styled_ok or text_ok
        if ok:
            style_count = apply_textplus_style(tool, subtitle_style or {}, safe_call, coerce_float) if subtitle_style else 0
            debug(f"success style_count={style_count}")
            return True, style_count
    debug("setinput_failed_all_tools")
    return False, 0


def timeline_ranges_for_subtitle(
    segment: dict[str, Any],
    timing_segments: list[dict[str, Any]] | None,
    subtitle_source_start: float,
) -> list[tuple[float, float]]:
    if not timing_segments:
        return [(float(segment["start"]), float(segment["end"]))]
    source_start = float(subtitle_source_start) + float(segment["start"])
    source_end = float(subtitle_source_start) + float(segment["end"])
    out: list[tuple[float, float]] = []
    for timing in timing_segments:
        try:
            timing_start = float(timing.get("source_start", 0.0))
            timing_end = float(timing.get("source_end", timing_start))
            record = float(timing.get("timeline_start", 0.0))
        except Exception:
            continue
        left = max(source_start, timing_start)
        right = min(source_end, timing_end)
        if right <= left:
            continue
        out.append((record + (left - timing_start), record + (right - timing_start)))
    return out


def remap_text_segments(
    subtitle_segments: list[dict[str, Any]],
    timing_segments: list[dict[str, Any]] | None,
    subtitle_source_start: float,
) -> list[dict[str, Any]]:
    text_segments: list[dict[str, Any]] = []
    for segment in subtitle_segments:
        for start_s, end_s in timeline_ranges_for_subtitle(segment, timing_segments, subtitle_source_start):
            if end_s <= start_s:
                continue
            text_segments.append({"start": start_s, "end": end_s, "text": str(segment.get("text", ""))})
    return text_segments


def build_textplus_clip_list(
    text_segments: list[dict[str, Any]],
    template_item: Any,
    fps: float,
    timeline_start_frame: int,
    track_index: int,
    offset_ms: int,
) -> list[dict[str, Any]]:
    clip_list: list[dict[str, Any]] = []
    time_offset = float(offset_ms) / 1000.0
    for segment in text_segments:
        shifted_start = max(0.0, float(segment["start"]) + time_offset)
        shifted_end = max(shifted_start + 0.05, float(segment["end"]) + time_offset)
        seg_start = int(round(shifted_start * fps))
        seg_end = int(round(shifted_end * fps))
        if seg_end <= seg_start:
            seg_end = seg_start + 1
        clip_list.append(
            {
                "mediaPoolItem": template_item,
                "startFrame": 0,
                "endFrame": max(1, seg_end - seg_start),
                "trackIndex": track_index,
                "recordFrame": timeline_start_frame + seg_start,
            }
        )
    return clip_list


def timeline_items_overlapping_record_frames(
    timeline: Any,
    track_index: int,
    clip_list: list[dict[str, Any]],
    safe_call: SafeCall,
) -> list[Any]:
    items = safe_call(timeline, "GetItemListInTrack", "video", track_index, default=[]) or []
    matched: list[Any] = []
    used: set[int] = set()
    for clip in clip_list:
        try:
            record = int(clip.get("recordFrame", 0))
            duration = max(1, int(clip.get("endFrame", 1)) - int(clip.get("startFrame", 0)))
            target_end = record + duration
        except Exception:
            continue
        best_idx: int | None = None
        best_distance: int | None = None
        for idx, item in enumerate(items):
            if idx in used:
                continue
            start = safe_call(item, "GetStart", default=None)
            end = safe_call(item, "GetEnd", default=None)
            try:
                start_i = int(start)
                end_i = int(end)
            except Exception:
                continue
            overlaps = not (end_i < record or start_i > target_end)
            if not overlaps:
                continue
            distance = abs(start_i - record)
            if best_distance is None or distance < best_distance:
                best_idx = idx
                best_distance = distance
        if best_idx is not None:
            used.add(best_idx)
            matched.append(items[best_idx])
    return matched


def inject_textplus_segments(
    items: list[Any],
    text_segments: list[dict[str, Any]],
    subtitle_style: dict[str, Any] | None,
    safe_call: SafeCall,
    coerce_float: CoerceFloat,
    log: Logger,
    label: str,
) -> tuple[int, int]:
    applied = 0
    style_applied = 0
    for index, item in enumerate(items):
        text = str(text_segments[index].get("text", "")) if index < len(text_segments) else ""
        ok_text, style_count = (
            set_textplus_item_text(item, text, subtitle_style, safe_call, coerce_float, log, f"{label}[{index}]") if text else (False, 0)
        )
        if ok_text:
            applied += 1
            if style_count > 0:
                style_applied += 1
    return applied, style_applied


def import_subtitles_to_timeline(
    project: Any,
    media_pool: Any,
    timeline: Any,
    subtitle_segments: list[dict[str, Any]],
    root: Path,
    template_name: str,
    auto_label: str,
    primary_template_name: str,
    fallback_template_name: str,
    offset_ms: int,
    subtitle_style: dict[str, Any] | None,
    timing_segments: list[dict[str, Any]] | None,
    subtitle_source_start: float,
    safe_call: SafeCall,
    log: Logger,
    coerce_float: CoerceFloat,
    parse_fps_text: ParseFpsText,
) -> tuple[bool, str]:
    if not subtitle_segments:
        return False, "No subtitle segments supplied"

    def count_track_items(track_type: str) -> int:
        total = 0
        track_count = safe_call(timeline, "GetTrackCount", track_type, default=0)
        try:
            count_i = int(track_count)
        except Exception:
            count_i = 0
        for index in range(1, count_i + 1):
            items = safe_call(timeline, "GetItemListInTrack", track_type, index, default=[])
            total += len(items or [])
        return total

    before_count = count_track_items("subtitle")
    before_video_count = count_track_items("video")
    safe_call(project, "SetCurrentTimeline", timeline)
    safe_call(media_pool, "SetCurrentTimeline", timeline)

    segments = list(subtitle_segments)
    if not segments:
        return False, "No valid subtitle segments"

    template_item, template_status = ensure_standalone_caption_template(
        media_pool,
        root,
        template_name,
        auto_label,
        primary_template_name,
        fallback_template_name,
        safe_call,
        log,
    )
    if template_item is None:
        return False, template_status

    frame_rate_raw = safe_call(timeline, "GetSetting", "timelineFrameRate", default="60")
    fps = parse_fps_text(frame_rate_raw) or 60.0
    timeline_start = safe_call(timeline, "GetStartFrame", default=0) or 0
    try:
        timeline_start_i = int(timeline_start)
    except Exception:
        timeline_start_i = 0
    track_count = safe_call(timeline, "GetTrackCount", "video", default=1)
    try:
        track_idx = max(1, int(track_count) + 1)
    except Exception:
        track_idx = 2
    safe_call(timeline, "AddTrack", "video")

    log(f"subtitle_textplus_offset_applied_ms={offset_ms}")
    text_segments = remap_text_segments(segments, timing_segments, subtitle_source_start)
    if timing_segments:
        log(f"subtitle_textplus_timing_remap segments={len(timing_segments)} captions={len(segments)} placed={len(text_segments)}")
    if not text_segments:
        return False, "No subtitle segments matched the cut timeline"

    clip_list = build_textplus_clip_list(text_segments, template_item, fps, timeline_start_i, track_idx, offset_ms)
    appended = safe_call(media_pool, "AppendToTimeline", clip_list, default=None)
    if not isinstance(appended, list) or not appended:
        return False, "Failed to append standalone Text+ subtitle clips to timeline"

    applied = 0
    style_applied = 0
    retry_delays = [0.0, 0.15, 0.25, 0.35, 0.5]
    for attempt, delay in enumerate(retry_delays, start=1):
        if delay > 0:
            time.sleep(delay)
        applied, style_applied = inject_textplus_segments(
            appended,
            text_segments,
            subtitle_style,
            safe_call,
            coerce_float,
            log,
            f"append_return attempt={attempt}",
        )
        log(f"subtitle_textplus_inject_attempt source=append_return attempt={attempt} applied={applied}/{len(text_segments)}")
        if applied > 0:
            break

    if applied <= 0:
        reread_items = timeline_items_overlapping_record_frames(timeline, track_idx, clip_list, safe_call)
        log(f"subtitle_textplus_reread_track track={track_idx} matched={len(reread_items)}/{len(text_segments)}")
        for attempt, delay in enumerate(retry_delays, start=1):
            if delay > 0:
                time.sleep(delay)
            applied, style_applied = inject_textplus_segments(
                reread_items,
                text_segments,
                subtitle_style,
                safe_call,
                coerce_float,
                log,
                f"reread_track attempt={attempt}",
            )
            log(f"subtitle_textplus_inject_attempt source=reread_track attempt={attempt} applied={applied}/{len(text_segments)}")
            if applied > 0:
                break

    after_count = count_track_items("subtitle")
    after_video = count_track_items("video")
    log(
        f"subtitle_textplus_apply template={primary_template_name} status={template_status} "
        f"applied={applied}/{len(text_segments)} style_applied={style_applied}/{applied} subtitle_tracks_before={before_count} subtitle_tracks_after={after_count} "
        f"video_items_before={before_video_count} video_items_after={after_video}"
    )

    if applied <= 0:
        return False, "Text+ clips appended but text injection failed"
    suffix = f", style {style_applied}/{applied}" if subtitle_style else ""
    return True, f"Subtitles applied via standalone Text+ ({applied}/{len(text_segments)}{suffix})"
