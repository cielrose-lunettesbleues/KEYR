from __future__ import annotations

from typing import Any, Callable

SafeCall = Callable[..., Any]
Logger = Callable[[str], None]


def safe_int_from_project_setting(project: Any, key: str, fallback: int) -> int:
    value = project.GetSetting(key)
    try:
        return int(float(value))
    except Exception:
        return fallback


def fps_from_project(project: Any, default_fps: int) -> int:
    fps = safe_int_from_project_setting(project, "timelineFrameRate", default_fps)
    if fps <= 0:
        return default_fps
    return fps


def ensure_vertical_project_settings(project: Any, safe_call: SafeCall) -> None:
    # Resolve API can vary by build; set multiple known keys.
    safe_call(project, "SetSetting", "timelineResolutionWidth", "1080")
    safe_call(project, "SetSetting", "timelineResolutionHeight", "1920")
    safe_call(project, "SetSetting", "timelineFrameRate", "60")
    safe_call(project, "SetSetting", "timelinePlaybackFrameRate", "60")
    # Extra compatibility keys/values for builds that ignore one spelling.
    for key in ("timelineFrameRate", "timelinePlaybackFrameRate", "playbackFrameRate"):
        for value in ("60", "60.0", "60.000"):
            safe_call(project, "SetSetting", key, value)
    safe_call(project, "SetSetting", "timelineOutputResolutionWidth", "1080")
    safe_call(project, "SetSetting", "timelineOutputResolutionHeight", "1920")
    # Prefer crop behavior when source is 16:9.
    safe_call(project, "SetSetting", "inputScalingPreset", "Scale full frame with crop")


def ensure_playback_fps_60(project: Any, default_fps: int, safe_call: SafeCall, log: Logger) -> bool:
    """Best-effort normalization to avoid 60->24 preview slowdown."""
    for key in ("timelinePlaybackFrameRate", "playbackFrameRate"):
        for value in ("60", "60.0", "60.000"):
            safe_call(project, "SetSetting", key, value)
    timeline_fps = safe_int_from_project_setting(project, "timelineFrameRate", default_fps)
    playback_fps = safe_int_from_project_setting(project, "timelinePlaybackFrameRate", default_fps)
    log(f"playback_fps_verify timeline={timeline_fps} playback={playback_fps}")
    return timeline_fps == 60 and playback_fps == 60


def force_timeline_fps_60(project: Any, timeline: Any, safe_call: SafeCall, log: Logger) -> None:
    safe_call(project, "SetCurrentTimeline", timeline)
    for key in ("timelineFrameRate", "timelinePlaybackFrameRate", "playbackFrameRate"):
        for value in ("60", "60.0", "60.000"):
            safe_call(timeline, "SetSetting", key, value)
    timeline_fps = safe_call(timeline, "GetSetting", "timelineFrameRate", default=None)
    playback_fps = safe_call(timeline, "GetSetting", "timelinePlaybackFrameRate", default=None)
    name = safe_call(timeline, "GetName", default="timeline")
    log(f"timeline_fps_verify name={name} timeline={timeline_fps} playback={playback_fps}")


def apply_preview_safe_playback(project: Any, safe_call: SafeCall, log: Logger) -> list[str]:
    warnings_out: list[str] = []
    attempts = [
        ("renderCacheMode", "user"),
        ("renderCacheMode", "User"),
        ("proxyMediaMode", "half"),
        ("proxyMediaMode", "Half"),
        ("timelineProxyResolution", "half"),
        ("timelineProxyResolution", "Half"),
    ]
    applied = 0
    for key, value in attempts:
        out = safe_call(project, "SetSetting", key, value, default=False)
        if out:
            applied += 1
            log(f"preview_safe_setting_applied {key}={value}")
    if applied == 0:
        warnings_out.append("Preview Safe Mode: Resolve API n'a pas expose les settings cache/proxy sur cette build.")
    else:
        log(f"preview_safe_settings_applied_count={applied}")
    return warnings_out
