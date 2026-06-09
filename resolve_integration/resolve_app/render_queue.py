from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

SafeCall = Callable[..., Any]
Logger = Callable[[str], None]


def set_shorts_render_defaults(project: Any, output_dir: Path, timeline_name: str, safe_call: SafeCall) -> None:
    loaded = False
    for preset in ("H264_Shorts_1080x1920_60fps", "H.264 Master", "YouTube"):
        try:
            if safe_call(project, "LoadRenderPreset", preset, default=False):
                loaded = True
                break
        except Exception:
            continue

    if not loaded:
        try:
            safe_call(project, "SetCurrentRenderFormatAndCodec", "mp4", "H264")
        except Exception:
            try:
                safe_call(project, "SetCurrentRenderFormatAndCodec", "mp4", "H.264")
            except Exception:
                pass

    render_settings = {
        "TargetDir": str(output_dir),
        "CustomName": timeline_name,
        "FormatWidth": 1080,
        "FormatHeight": 1920,
        "ResolutionWidth": 1080,
        "ResolutionHeight": 1920,
        "FrameRate": 60,
        "VideoQuality": "Best",
        "SelectAllFrames": True,
        "UseCustomSettings": True,
    }
    safe_call(project, "SetRenderSettings", render_settings)


def queue_render_job(project: Any, timeline: Any, output_dir: Path, preset_name: str, safe_call: SafeCall, log: Logger) -> bool:
    safe_call(project, "SetCurrentTimeline", timeline)
    loaded = False
    try:
        loaded = bool(safe_call(project, "LoadRenderPreset", preset_name, default=False))
    except Exception:
        loaded = False
    timeline_name = safe_call(timeline, "GetName", default="timeline")
    if not loaded:
        set_shorts_render_defaults(project, output_dir, timeline_name, safe_call)
    else:
        safe_call(
            project,
            "SetRenderSettings",
            {
                "TargetDir": str(output_dir),
                "CustomName": timeline_name,
                "FormatWidth": 1080,
                "FormatHeight": 1920,
                "FrameRate": 60,
                "UseCustomSettings": True,
            },
        )
    log(f"Render settings applied for {timeline_name}: 1080x1920@60")
    job_id = safe_call(project, "AddRenderJob")
    return bool(job_id)


def collect_unique_media_items_from_timelines(timelines: list[Any], safe_call: SafeCall) -> list[Any]:
    seen: set[str] = set()
    out: list[Any] = []
    for timeline in timelines:
        track_count = safe_call(timeline, "GetTrackCount", "video", default=0)
        try:
            track_count_i = int(track_count)
        except Exception:
            track_count_i = 0
        for track_idx in range(1, max(1, track_count_i) + 1):
            items = safe_call(timeline, "GetItemListInTrack", "video", track_idx, default=[]) or []
            for item in items:
                media_item = safe_call(item, "GetMediaPoolItem")
                if media_item is None:
                    continue
                uid = str(id(media_item))
                if uid in seen:
                    continue
                seen.add(uid)
                out.append(media_item)
    return out
