from __future__ import annotations

import tempfile
from pathlib import Path

from .audio_analysis import compute_window_energy, extract_mono_wav, extract_track_wav, percentile
from .models import ClipCandidate, VodManifest


def _trim_clip_bounds_from_energy(
    clip: ClipCandidate,
    energies: list[tuple[float, float]],
    activity_floor: float,
    min_duration: float,
    max_trim_start: float,
    max_trim_end: float,
    headroom_seconds: float,
    window_seconds: float,
) -> tuple[float, float] | None:
    if clip.end_seconds <= clip.start_seconds:
        return None
    active_times = [t for t, e in energies if clip.start_seconds <= t <= clip.end_seconds and e > activity_floor]
    if not active_times:
        return None

    first_active = min(active_times)
    last_active = max(active_times)
    new_start = max(clip.start_seconds, first_active - headroom_seconds)
    new_end = min(clip.end_seconds, last_active + window_seconds + headroom_seconds)

    start_trim = max(0.0, new_start - clip.start_seconds)
    end_trim = max(0.0, clip.end_seconds - new_end)
    if start_trim > max_trim_start:
        new_start = clip.start_seconds + max_trim_start
    if end_trim > max_trim_end:
        new_end = clip.end_seconds - max_trim_end

    if new_end - new_start < min_duration:
        need = min_duration - (new_end - new_start)
        expand_left = min(need / 2.0, new_start - clip.start_seconds)
        expand_right = min(need - expand_left, clip.end_seconds - new_end)
        new_start -= expand_left
        new_end += expand_right
        remaining = min_duration - (new_end - new_start)
        if remaining > 0:
            take_left = min(remaining, new_start - clip.start_seconds)
            new_start -= take_left
            remaining -= take_left
        if remaining > 0:
            take_right = min(remaining, clip.end_seconds - new_end)
            new_end += take_right

    if new_end - new_start < min_duration:
        return None
    return round(new_start, 3), round(new_end, 3)


def trim_dead_air_on_boundaries(vod: VodManifest, clips: list[ClipCandidate], cfg: dict, work_dir: Path) -> list[str]:
    trim_cfg = cfg.get("audio", {}).get("trim_dead_air", {})
    if not bool(trim_cfg.get("enabled", False)):
        return []
    if not clips:
        return []

    window_ms = int(trim_cfg.get("window_ms", 500))
    window_seconds = max(0.1, window_ms / 1000.0)
    threshold_percentile = float(trim_cfg.get("threshold_percentile", 0.4))
    headroom_seconds = max(0.0, float(trim_cfg.get("headroom_ms", 350)) / 1000.0)
    max_trim_start = max(0.0, float(trim_cfg.get("max_trim_start_seconds", 6.0)))
    max_trim_end = max(0.0, float(trim_cfg.get("max_trim_end_seconds", 6.0)))
    min_duration = float(cfg.get("video", {}).get("min_clip_seconds", 20.0))

    analysis_cfg = cfg.get("audio", {}).get("analysis", {})
    voice_track = int(analysis_cfg.get("voice_track", 2))
    render_track = int(cfg.get("audio", {}).get("render", {}).get("base_track", 6))
    warnings_out: list[str] = []
    work_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(dir=str(work_dir)) as tmp_dir:
        tmp = Path(tmp_dir)
        voice_wav = tmp / "trim_voice.wav"
        mono_wav = tmp / "trim_mono.wav"

        energy_source = "voice"
        if extract_track_wav(vod.source_path, voice_wav, voice_track):
            energies = compute_window_energy(voice_wav, window_seconds=window_seconds)
        elif extract_track_wav(vod.source_path, mono_wav, render_track):
            energies = compute_window_energy(mono_wav, window_seconds=window_seconds)
            energy_source = "render"
            warnings_out.append(f"{Path(vod.source_path).name}: trim boundary used render track fallback ({render_track}).")
        else:
            extract_mono_wav(vod.source_path, mono_wav)
            energies = compute_window_energy(mono_wav, window_seconds=window_seconds)
            energy_source = "mono"
            warnings_out.append(f"{Path(vod.source_path).name}: trim boundary used mono fallback.")

    if not energies:
        warnings_out.append(f"{Path(vod.source_path).name}: trim boundary skipped (no audio energy data).")
        return warnings_out

    values = [energy for _, energy in energies]
    activity_floor = percentile(values, threshold_percentile)

    for clip in clips:
        trimmed = _trim_clip_bounds_from_energy(
            clip,
            energies,
            activity_floor,
            min_duration,
            max_trim_start,
            max_trim_end,
            headroom_seconds,
            window_seconds,
        )
        if not trimmed:
            continue
        new_start, new_end = trimmed
        if abs(new_start - clip.start_seconds) < 0.05 and abs(new_end - clip.end_seconds) < 0.05:
            continue
        old_start = clip.start_seconds
        old_end = clip.end_seconds
        clip.start_seconds = new_start
        clip.end_seconds = new_end
        clip.reason = f"{clip.reason};trim={energy_source}"
        warnings_out.append(f"{clip.clip_id}: dead-air trim {old_start:.2f}-{old_end:.2f}s -> {new_start:.2f}-{new_end:.2f}s")

    return warnings_out
