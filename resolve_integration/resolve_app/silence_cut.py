from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import Any, Callable

SafeCall = Callable[..., Any]
EnsureMediaItem = Callable[[Any, Path], Any | None]
FpsFromProject = Callable[[Any], float]
SourceFpsForMediaItem = Callable[[Any, Path, float], float]
DeleteTimelineIfExists = Callable[[Any, Any, str], None]
ForceTimelineFps = Callable[[Any, Any], None]
AppendSegment = Callable[[Any, Any, Any, int, int, int, dict[str, Any]], None]


def load_audio_energy_for_silence_cut(
    root: Path,
    source_path: Path,
    cfg: dict[str, Any],
    cache: dict[str, tuple[list[tuple[float, float]], str]],
) -> tuple[list[tuple[float, float]], str, list[str]]:
    source_key = str(source_path.resolve()).lower()
    if source_key in cache:
        energies, source_label = cache[source_key]
        return energies, source_label, []

    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)
    from short_editor.audio_analysis import compute_window_energy, extract_mono_wav, extract_track_wav

    audio_cfg = cfg.get("audio", {}) if isinstance(cfg.get("audio", {}), dict) else {}
    analysis_cfg = audio_cfg.get("analysis", {}) if isinstance(audio_cfg.get("analysis", {}), dict) else {}
    render_cfg = audio_cfg.get("render", {}) if isinstance(audio_cfg.get("render", {}), dict) else {}
    voice_track = int(analysis_cfg.get("voice_track", 2))
    render_track = int(render_cfg.get("base_track", 6))
    window_seconds = float(audio_cfg.get("silence_cut", {}).get("window_seconds", 0.12)) if isinstance(audio_cfg.get("silence_cut", {}), dict) else 0.12
    window_seconds = max(0.06, min(0.5, window_seconds))

    warnings_out: list[str] = []
    work_parent = root / "work"
    work_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=str(work_parent)) as tmp_dir:
        tmp = Path(tmp_dir)
        wav_path = tmp / "silence_cut.wav"
        source_label = f"piste voix {voice_track}"
        if not extract_track_wav(str(source_path), wav_path, voice_track):
            source_label = f"piste rendu {render_track}"
            if not extract_track_wav(str(source_path), wav_path, render_track):
                source_label = "mix mono"
                try:
                    extract_mono_wav(str(source_path), wav_path)
                except Exception as exc:
                    warnings_out.append(f"Analyse audio impossible pour {source_path.name}: {exc}")
                    cache[source_key] = ([], source_label)
                    return [], source_label, warnings_out
                warnings_out.append(f"{source_path.name}: fallback analyse silence sur mix mono.")
            else:
                warnings_out.append(f"{source_path.name}: fallback analyse silence sur piste rendu {render_track}.")
        energies = compute_window_energy(wav_path, window_seconds=window_seconds)

    cache[source_key] = (energies, source_label)
    return energies, source_label, warnings_out


def detect_audible_segments_for_silence_cut(
    energies: list[tuple[float, float]],
    clip_start: float,
    clip_end: float,
    cfg: dict[str, Any],
    root: Path,
) -> tuple[list[tuple[float, float]], dict[str, float]]:
    if clip_end <= clip_start:
        return [], {"cuts": 0.0, "removed_seconds": 0.0, "threshold": 0.0}
    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)
    from short_editor.audio_analysis import percentile

    audio_cfg = cfg.get("audio", {}) if isinstance(cfg.get("audio", {}), dict) else {}
    cut_cfg = audio_cfg.get("silence_cut", {}) if isinstance(audio_cfg.get("silence_cut", {}), dict) else {}
    min_silence = max(0.25, float(cut_cfg.get("min_silence_seconds", 0.55)))
    padding = max(0.05, float(cut_cfg.get("padding_seconds", 0.18)))
    merge_gap = max(0.08, float(cut_cfg.get("merge_gap_seconds", 0.28)))
    min_segment = max(0.2, float(cut_cfg.get("min_segment_seconds", 0.45)))

    clip_energies = [(t, e) for t, e in energies if clip_start <= t <= clip_end]
    if len(clip_energies) < 3:
        return [(clip_start, clip_end)], {"cuts": 0.0, "removed_seconds": 0.0, "threshold": 0.0}

    values = [float(e) for _, e in clip_energies]
    low = percentile(values, 0.35)
    high = percentile(values, 0.78)
    threshold = low + max(0.0, high - low) * 0.28
    if threshold <= 0:
        threshold = max(values) * 0.12
    if threshold <= 0:
        return [(clip_start, clip_end)], {"cuts": 0.0, "removed_seconds": 0.0, "threshold": 0.0}

    active_ranges: list[tuple[float, float]] = []
    current_start: float | None = None
    last_t: float | None = None
    estimated_step = max(0.08, min_silence / 4)
    if len(clip_energies) >= 2:
        deltas = [clip_energies[i + 1][0] - clip_energies[i][0] for i in range(len(clip_energies) - 1) if clip_energies[i + 1][0] > clip_energies[i][0]]
        if deltas:
            estimated_step = max(0.06, min(0.5, sorted(deltas)[len(deltas) // 2]))

    for t, energy in clip_energies:
        is_active = float(energy) >= threshold
        if is_active and current_start is None:
            current_start = max(clip_start, t)
        if is_active:
            last_t = t
        elif current_start is not None and last_t is not None:
            active_ranges.append((current_start, min(clip_end, last_t + estimated_step)))
            current_start = None
            last_t = None
    if current_start is not None and last_t is not None:
        active_ranges.append((current_start, min(clip_end, last_t + estimated_step)))

    if not active_ranges:
        return [(clip_start, clip_end)], {"cuts": 0.0, "removed_seconds": 0.0, "threshold": threshold}

    padded = [(max(clip_start, s - padding), min(clip_end, e + padding)) for s, e in active_ranges]
    merged: list[tuple[float, float]] = []
    for s, e in padded:
        if e - s < min_segment:
            mid = (s + e) / 2.0
            s = max(clip_start, mid - min_segment / 2.0)
            e = min(clip_end, mid + min_segment / 2.0)
        if not merged:
            merged.append((s, e))
            continue
        prev_s, prev_e = merged[-1]
        gap = s - prev_e
        if gap <= merge_gap or gap < min_silence:
            merged[-1] = (prev_s, max(prev_e, e))
        else:
            merged.append((s, e))

    final_segments: list[tuple[float, float]] = []
    for s, e in merged:
        if e - s >= min_segment:
            final_segments.append((round(s, 3), round(e, 3)))
    if not final_segments:
        final_segments = [(clip_start, clip_end)]

    original_duration = max(0.0, clip_end - clip_start)
    kept_duration = sum(max(0.0, e - s) for s, e in final_segments)
    removed = max(0.0, original_duration - kept_duration)
    cuts = max(0, len(final_segments) - 1)
    if removed < min_silence:
        return [(clip_start, clip_end)], {"cuts": 0.0, "removed_seconds": 0.0, "threshold": threshold}
    return final_segments, {"cuts": float(cuts), "removed_seconds": removed, "threshold": threshold}


def create_silence_cut_timeline(
    root: Path,
    project: Any,
    media_pool: Any,
    source_path: Path,
    timeline_name: str,
    segments_seconds: list[tuple[float, float]],
    preset: dict[str, Any],
    ensure_media_item: EnsureMediaItem,
    fps_from_project: FpsFromProject,
    source_fps_for_media_item: SourceFpsForMediaItem,
    delete_timeline_if_exists: DeleteTimelineIfExists,
    force_timeline_fps_60: ForceTimelineFps,
    append_segment: AppendSegment,
    safe_call: SafeCall,
) -> tuple[Any | None, list[str]]:
    warnings_out: list[str] = []
    media_item = ensure_media_item(media_pool, source_path)
    if media_item is None:
        return None, [f"Impossible d'importer le média: {source_path}"]
    project_fps = fps_from_project(project)
    source_fps = source_fps_for_media_item(media_item, source_path, project_fps)
    delete_timeline_if_exists(project, media_pool, timeline_name)
    timeline = safe_call(media_pool, "CreateEmptyTimeline", timeline_name)
    if not timeline:
        return None, [f"Impossible de créer la timeline: {timeline_name}"]
    force_timeline_fps_60(project, timeline)

    record_frame = 0
    for s, e in segments_seconds:
        start_frame = int(round(s * source_fps))
        end_frame = int(round(e * source_fps))
        if end_frame <= start_frame:
            warnings_out.append(f"Segment ignoré: {s:.2f}-{e:.2f}s")
            continue
        append_segment(media_pool, timeline, media_item, start_frame, end_frame, record_frame, preset)
        record_frame += max(1, int(round((e - s) * project_fps)))
    if record_frame <= 0:
        warnings_out.append(f"Aucun segment valide pour {timeline_name}")
    return timeline, warnings_out
