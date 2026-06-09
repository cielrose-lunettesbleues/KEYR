from __future__ import annotations

from typing import Any, Callable

from resolve_integration.resolve_app.media_pool import append_clip_range

SafeCall = Callable[..., Any]
Logger = Callable[[str], None]
ApplyItemTransform = Callable[[Any, dict[str, float]], None]
ForceTimelineFps = Callable[[Any, Any], None]


def get_timeline_items_on_track(timeline: Any, track_index: int, safe_call: SafeCall) -> list[Any]:
    out = safe_call(timeline, "GetItemListInTrack", "video", track_index, default=[])
    return out or []


def get_track_item_count(timeline: Any, track_type: str, safe_call: SafeCall) -> int:
    count = safe_call(timeline, "GetTrackCount", track_type, default=0)
    try:
        count_i = int(count)
    except Exception:
        count_i = 0
    total = 0
    for idx in range(1, count_i + 1):
        items = safe_call(timeline, "GetItemListInTrack", track_type, idx, default=[])
        total += len(items or [])
    return total


def force_item_normal_speed(item: Any, safe_call: SafeCall) -> None:
    # Defensive normalization against API/build differences that can retain retime state.
    for key, value in (
        ("Speed", 100.0),
        ("Clip Speed", 100.0),
        ("RetimeProcess", 0),
        ("Retime Process", 0),
    ):
        safe_call(item, "SetProperty", key, value)
    safe_call(item, "SetClipProperty", "Speed", "100")
    safe_call(item, "SetClipProperty", "Clip Speed", "100")


def read_speed_props(item: Any, safe_call: SafeCall) -> str:
    values: list[str] = []
    for key in ("Speed", "Clip Speed", "Retime Process", "RetimeProcess"):
        value = safe_call(item, "GetProperty", key, default=None)
        if value is None:
            props = safe_call(item, "GetProperty", default={}) or {}
            value = props.get(key)
        if value is not None:
            values.append(f"{key}={value}")
    return ";".join(values) if values else "no_speed_props"


def get_item_at_current_frame(timeline: Any, track_index: int, safe_call: SafeCall) -> Any | None:
    items = get_timeline_items_on_track(timeline, track_index, safe_call)
    if not items:
        return None
    cur = safe_call(timeline, "GetCurrentFrame", default=0)
    try:
        cur_i = int(cur)
    except Exception:
        cur_i = 0
    for item in items:
        start = safe_call(item, "GetStart", default=None)
        end = safe_call(item, "GetEnd", default=None)
        if start is None or end is None:
            continue
        try:
            if int(start) <= cur_i <= int(end):
                return item
        except Exception:
            continue
    return None


def get_first_item_on_track(timeline: Any, track_index: int, safe_call: SafeCall) -> Any | None:
    items = get_timeline_items_on_track(timeline, track_index, safe_call)
    return items[0] if items else None


def items_overlapping_frame_range(timeline: Any, track_index: int, start_frame: int, end_frame: int, safe_call: SafeCall) -> list[Any]:
    items = get_timeline_items_on_track(timeline, track_index, safe_call)
    out: list[Any] = []
    for item in items:
        start = safe_call(item, "GetStart", default=None)
        end = safe_call(item, "GetEnd", default=None)
        if start is None or end is None:
            continue
        try:
            start_i = int(start)
            end_i = int(end)
        except Exception:
            continue
        if end_i < start_frame or start_i > end_frame:
            continue
        out.append(item)
    return out


def get_timeline_selected_range(timeline: Any, safe_call: SafeCall) -> tuple[int, int] | None:
    # Resolve APIs differ across builds; try common variants.
    for method_name in ("GetMarkInOut", "GetInOutPoints", "GetTimelineInOut"):
        data = safe_call(timeline, method_name, default=None)
        if not isinstance(data, dict):
            continue
        for in_key, out_key in (("video", "video"), ("timeline", "timeline"), ("in", "out")):
            raw_in = data.get(in_key)
            raw_out = data.get(out_key)
            if isinstance(raw_in, dict):
                raw_in = raw_in.get("in")
            if isinstance(raw_out, dict):
                raw_out = raw_out.get("out")
            try:
                start = int(raw_in)
                end = int(raw_out)
            except Exception:
                continue
            if end >= start:
                return start, end
    return None


def find_timeline_by_name(project: Any, timeline_name: str, safe_call: SafeCall) -> Any | None:
    count = safe_call(project, "GetTimelineCount", default=0) or 0
    try:
        count = int(count)
    except Exception:
        count = 0
    for index in range(1, count + 1):
        timeline = safe_call(project, "GetTimelineByIndex", index)
        if not timeline:
            continue
        name = safe_call(timeline, "GetName", default="")
        if name == timeline_name:
            return timeline
    return None


def delete_timeline_if_exists(project: Any, media_pool: Any, timeline_name: str, safe_call: SafeCall) -> None:
    timeline = find_timeline_by_name(project, timeline_name, safe_call)
    if not timeline:
        return
    # API variants across Resolve builds.
    deleted = safe_call(media_pool, "DeleteTimelines", [timeline], default=False)
    if not deleted:
        safe_call(project, "DeleteTimeline", timeline, default=False)


def append_silence_cut_segment_with_preset(
    media_pool: Any,
    timeline: Any,
    media_item: Any,
    start_frame: int,
    end_frame: int,
    record_frame: int,
    preset: dict[str, Any],
    safe_call: SafeCall,
    apply_item_transform: ApplyItemTransform,
) -> None:
    mode = str(preset.get("mode", "single"))
    frame_span = max(1, end_frame - start_frame) + 2
    if mode == "fixed_split":
        append_clip_range(media_pool, timeline, media_item, start_frame, end_frame, 1, record_frame, safe_call)
        track_count = safe_call(timeline, "GetTrackCount", "video", default=1) or 1
        try:
            track_count_i = int(track_count)
        except Exception:
            track_count_i = 1
        if track_count_i < 2:
            safe_call(timeline, "AddTrack", "video")
        append_clip_range(media_pool, timeline, media_item, start_frame, end_frame, 2, record_frame, safe_call)
        track1_items = items_overlapping_frame_range(timeline, 1, record_frame, record_frame + frame_span, safe_call)
        track2_items = items_overlapping_frame_range(timeline, 2, record_frame, record_frame + frame_span, safe_call)
        for item in track1_items:
            force_item_normal_speed(item, safe_call)
            apply_item_transform(item, dict(preset.get("camera", {})))
        for item in track2_items:
            force_item_normal_speed(item, safe_call)
            apply_item_transform(item, dict(preset.get("gameplay", {})))
        return

    append_clip_range(media_pool, timeline, media_item, start_frame, end_frame, 1, record_frame, safe_call)
    items = items_overlapping_frame_range(timeline, 1, record_frame, record_frame + frame_span, safe_call)
    for item in items:
        force_item_normal_speed(item, safe_call)
        apply_item_transform(item, dict(preset.get("single", {})))




def create_timeline_for_clip_with_preset(
    project: Any,
    media_pool: Any,
    name: str,
    media_item: Any,
    start_frame: int,
    end_frame: int,
    preset: dict[str, Any],
    safe_call: SafeCall,
    log: Logger,
    force_timeline_fps_60: ForceTimelineFps,
    apply_item_transform: ApplyItemTransform,
) -> Any | None:
    timeline = safe_call(media_pool, "CreateEmptyTimeline", name)
    if not timeline:
        return None
    force_timeline_fps_60(project, timeline)

    mode = str(preset.get("mode", "single"))
    if mode == "fixed_split":
        # Track mapping for composition: track 1 = camera (bottom), track 2 = gameplay (top)
        log("Build timeline mapping: camera->T1 gameplay->T2 stack_same_record_frame")
        append_clip_range(media_pool, timeline, media_item, start_frame, end_frame, 1, 0, safe_call)
        safe_call(timeline, "AddTrack", "video")
        append_clip_range(media_pool, timeline, media_item, start_frame, end_frame, 2, 0, safe_call)
        items_t1 = get_timeline_items_on_track(timeline, 1, safe_call)
        items_t2 = get_timeline_items_on_track(timeline, 2, safe_call)
        if items_t1:
            force_item_normal_speed(items_t1[0], safe_call)
            apply_item_transform(items_t1[0], dict(preset.get("camera", {})))
        if items_t2:
            force_item_normal_speed(items_t2[0], safe_call)
            apply_item_transform(items_t2[0], dict(preset.get("gameplay", {})))
        return timeline

    ok = append_clip_range(media_pool, timeline, media_item, start_frame, end_frame, 1, 0, safe_call)
    if not ok:
        return None
    items_t1 = get_timeline_items_on_track(timeline, 1, safe_call)
    if items_t1:
        force_item_normal_speed(items_t1[0], safe_call)
        apply_item_transform(items_t1[0], dict(preset.get("single", {})))
    return timeline


def create_timeline_for_clip(
    media_pool: Any,
    name: str,
    media_item: Any,
    start_frame: int,
    end_frame: int,
    safe_call: SafeCall,
) -> Any | None:
    timeline = safe_call(media_pool, "CreateEmptyTimeline", name)
    if not timeline:
        return None
    ok = append_clip_range(media_pool, timeline, media_item, start_frame, end_frame, 1, 0, safe_call)
    return timeline if ok else None
