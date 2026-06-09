from __future__ import annotations

import tempfile
from pathlib import Path

from .models import ClipCandidate, VodManifest
from .feedback import load_user_lexicon
from .chapters import clamp as _clamp, compute_quota
from .selection import ranges_too_close
from .transcript_scoring import load_transcript_entries_for_vod, text_score_for_window
from .audio_analysis import (
    build_energy_map as _build_energy_map,
    compute_window_energy as _compute_window_energy,
    extract_mono_wav as _extract_mono_wav,
    extract_track_wav as _extract_track_wav,
    merge_energy_tracks as _merge_energy_tracks,
    percentile as _percentile,
)


def _pick_peak_times(energies: list[tuple[float, float]], target_count: int, min_gap_seconds: float) -> list[float]:
    if not energies or target_count <= 0:
        return []

    ranked = sorted(energies, key=lambda x: x[1], reverse=True)
    chosen: list[float] = []
    for t, _ in ranked:
        if all(abs(t - c) >= min_gap_seconds for c in chosen):
            chosen.append(t)
        if len(chosen) >= target_count:
            break
    return sorted(chosen)


def _slice_energies(energies: list[tuple[float, float]], start: float, end: float) -> list[float]:
    return [e for t, e in energies if start <= t < end]


def _activity_ratio(values: list[float], silence_floor: float) -> float:
    if not values:
        return 0.0
    active = sum(1 for v in values if v > silence_floor)
    return active / len(values)


def _hook_score(energies: list[tuple[float, float]], start: float, full_end: float) -> float:
    hook_end = min(start + 3.0, full_end)
    hook_values = _slice_energies(energies, start, hook_end)
    clip_values = _slice_energies(energies, start, full_end)
    if not hook_values or not clip_values:
        return 0.0
    hook_avg = sum(hook_values) / len(hook_values)
    clip_avg = sum(clip_values) / len(clip_values)
    if clip_avg <= 0.0:
        return 0.0
    return min(1.5, hook_avg / clip_avg)


def discover_fallback_candidates(vod: VodManifest, cfg: dict, work_dir: Path) -> list[ClipCandidate]:
    """Create fallback candidates when no chapters are available.

    Fallback strategy:
    - detect high-energy moments from audio windows
    - reject silence-heavy windows
    - prefer clips with stronger first 3s hook
    """
    video_cfg = cfg["video"]
    quota_cfg = cfg["quota"]

    _, target_quota, _ = compute_quota(vod.duration_seconds, quota_cfg)
    preferred_len = float(video_cfg["preferred_clip_seconds"])
    min_len = float(video_cfg["min_clip_seconds"])
    max_len = float(video_cfg["max_clip_seconds"])

    if target_quota <= 0:
        return []

    clips: list[ClipCandidate] = []

    analysis_cfg = cfg.get("audio", {}).get("analysis", {})
    voice_track = int(analysis_cfg.get("voice_track", 2))
    context_tracks = list(analysis_cfg.get("context_tracks", [5]))
    optional_react_track = int(analysis_cfg.get("optional_react_track", 3))
    react_with_voice = bool(analysis_cfg.get("use_optional_react_only_with_voice", True))
    intro_skip_minutes = float(analysis_cfg.get("fallback_intro_skip_minutes", 8))
    voice_floor_ratio = float(analysis_cfg.get("music_only_voice_floor_ratio", 0.45))
    lexicon_path = (work_dir.parent / "config" / "transcript_lexicon_user.json").resolve()
    lexicon = load_user_lexicon(lexicon_path)
    transcript_entries = load_transcript_entries_for_vod(vod, cfg, work_dir)

    with tempfile.TemporaryDirectory(dir=str(work_dir)) as tmp_dir:
        tmp = Path(tmp_dir)
        voice_wav = tmp / "voice.wav"
        context_wavs = [tmp / f"context_{i}.wav" for i in range(len(context_tracks))]
        react_wav = tmp / "react.wav"

        voice_ok = _extract_track_wav(vod.source_path, voice_wav, voice_track)
        context_energies: list[list[tuple[float, float]]] = []
        for i, track in enumerate(context_tracks):
            if _extract_track_wav(vod.source_path, context_wavs[i], int(track)):
                context_energies.append(_compute_window_energy(context_wavs[i], window_seconds=1.0))

        react_ok = _extract_track_wav(vod.source_path, react_wav, optional_react_track)

        if voice_ok:
            voice_energies = _compute_window_energy(voice_wav, window_seconds=1.0)
        else:
            # hard fallback for unusual files
            mono_wav = tmp / "analysis_mono.wav"
            _extract_mono_wav(vod.source_path, mono_wav)
            voice_energies = _compute_window_energy(mono_wav, window_seconds=1.0)

        energies = voice_energies
        if context_energies:
            merged_context = _merge_energy_tracks(context_energies, [1.0] * len(context_energies))
            energies = _merge_energy_tracks([voice_energies, merged_context], [0.8, 0.2])

        react_energies: list[tuple[float, float]] = []
        if react_ok:
            react_energies = _compute_window_energy(react_wav, window_seconds=1.0)

    if not energies:
        return clips

    intro_skip_seconds = max(0.0, intro_skip_minutes * 60.0)
    energies_for_pick = [(t, e) for t, e in energies if t >= intro_skip_seconds]
    voice_for_pick = [(t, e) for t, e in voice_energies if t >= intro_skip_seconds]

    all_values = [e for _, e in energies_for_pick]
    if not all_values:
        return clips

    voice_values = [e for _, e in voice_for_pick] if voice_for_pick else all_values
    silence_floor = _percentile(all_values, 0.35)
    energy_gate = _percentile(all_values, 0.65)
    voice_floor = _percentile(voice_values, 0.5)

    gated = [(t, e) for t, e in energies_for_pick if e >= energy_gate]
    peak_centers = _pick_peak_times(gated, target_quota * 2, min_gap_seconds=35.0)
    if not peak_centers:
        return clips

    voice_map = _build_energy_map(voice_energies)
    react_map = _build_energy_map(react_energies)

    scored_candidates: list[tuple[float, float, float, float, str]] = []
    for center in peak_centers:
        start = _clamp(center - preferred_len / 2.0, 0.0, vod.duration_seconds)
        end = _clamp(start + preferred_len, 0.0, vod.duration_seconds)

        if end - start < min_len:
            end = _clamp(start + min_len, 0.0, vod.duration_seconds)
        if end - start > max_len:
            end = start + max_len

        clip_values = _slice_energies(energies, start, end)
        activity = _activity_ratio(clip_values, silence_floor)
        if activity < 0.45:
            continue

        mid = int(start + (end - start) / 2.0)
        voice_mid = voice_map.get(mid, 0.0)
        if voice_mid < (voice_floor * voice_floor_ratio):
            continue

        if react_with_voice and react_map:
            react_mid = react_map.get(mid, 0.0)
            if react_mid > 0 and voice_mid <= 0:
                continue

        hook = _hook_score(energies, start, end)
        energy_norm = 0.0
        if clip_values:
            clip_avg = sum(clip_values) / len(clip_values)
            hi = max(_percentile(all_values, 0.9), 1.0)
            energy_norm = min(1.0, clip_avg / hi)

        text_score, text_reason = text_score_for_window(transcript_entries, start, end, lexicon)
        score = (0.35 * energy_norm) + (0.20 * activity) + (0.15 * min(1.0, hook)) + (0.30 * text_score)
        reason = f"voice_track={voice_track};context={context_tracks};intro_skip={int(intro_skip_minutes)}m"
        if text_reason:
            reason = reason + ";" + text_reason
        scored_candidates.append((score, start, end, hook, reason))

    if transcript_entries:
        preferred_len = float(video_cfg["preferred_clip_seconds"])
        for e in transcript_entries:
            txt = str(e.get("text", ""))
            if not txt.strip():
                continue
            try:
                center = float(e.get("start", 0.0))
            except Exception:
                continue
            if center < intro_skip_seconds:
                continue
            start = _clamp(center - preferred_len / 2.0, 0.0, vod.duration_seconds)
            end = _clamp(start + preferred_len, 0.0, vod.duration_seconds)
            text_score, text_reason = text_score_for_window(transcript_entries, start, end, lexicon)
            if text_score < 0.25:
                continue
            hook = _hook_score(energies, start, end)
            clip_values = _slice_energies(energies, start, end)
            energy_norm = 0.0
            if clip_values:
                clip_avg = sum(clip_values) / len(clip_values)
                hi = max(_percentile(all_values, 0.9), 1.0)
                energy_norm = min(1.0, clip_avg / hi)
            score = (0.50 * text_score) + (0.35 * energy_norm) + (0.15 * min(1.0, hook))
            reason = "transcript_discovery"
            if text_reason:
                reason += ";" + text_reason
            scored_candidates.append((score, start, end, hook, reason))

    # Pass 2 (relaxed transcript): keep more text-driven candidates if strict pass is sparse.
    if transcript_entries and len(scored_candidates) < max(4, target_quota):
        preferred_len = float(video_cfg["preferred_clip_seconds"])
        for e in transcript_entries:
            txt = str(e.get("text", ""))
            if not txt.strip():
                continue
            try:
                center = float(e.get("start", 0.0))
            except Exception:
                continue
            if center < intro_skip_seconds:
                continue
            start = _clamp(center - preferred_len / 2.0, 0.0, vod.duration_seconds)
            end = _clamp(start + preferred_len, 0.0, vod.duration_seconds)
            text_score, text_reason = text_score_for_window(transcript_entries, start, end, lexicon)
            if text_score < 0.12:
                continue
            hook = _hook_score(energies, start, end)
            clip_values = _slice_energies(energies, start, end)
            energy_norm = 0.0
            if clip_values:
                clip_avg = sum(clip_values) / len(clip_values)
                hi = max(_percentile(all_values, 0.9), 1.0)
                energy_norm = min(1.0, clip_avg / hi)
            score = (0.58 * text_score) + (0.30 * energy_norm) + (0.12 * min(1.0, hook))
            reason = "transcript_relaxed"
            if text_reason:
                reason += ";" + text_reason
            scored_candidates.append((score, start, end, hook, reason))

    # Pass 3 (audio safety net): if still sparse, keep best audio peaks even with low text score.
    if len(scored_candidates) < target_quota:
        for center in peak_centers:
            start = _clamp(center - preferred_len / 2.0, 0.0, vod.duration_seconds)
            end = _clamp(start + preferred_len, 0.0, vod.duration_seconds)
            if end - start < min_len:
                end = _clamp(start + min_len, 0.0, vod.duration_seconds)
            if end - start > max_len:
                end = start + max_len
            clip_values = _slice_energies(energies, start, end)
            if not clip_values:
                continue
            hook = _hook_score(energies, start, end)
            clip_avg = sum(clip_values) / len(clip_values)
            hi = max(_percentile(all_values, 0.9), 1.0)
            energy_norm = min(1.0, clip_avg / hi)
            score = (0.75 * energy_norm) + (0.25 * min(1.0, hook))
            scored_candidates.append((score, start, end, hook, "audio_safety_net"))

    # De-duplicate nearby ranges before truncating; shifted 40s windows can still feel like the same moment.
    deduped: list[tuple[float, float, float, float, str]] = []
    for cand in sorted(scored_candidates, key=lambda x: x[0], reverse=True):
        _, s, e, _, _ = cand
        if any(ranges_too_close(s, e, ds, de) for _, ds, de, _, _ in deduped):
            continue
        deduped.append(cand)

    deduped.sort(key=lambda x: x[0], reverse=True)
    top = deduped[: max(target_quota * 2, target_quota + 3)]

    for i, (score, start, end, hook, detail) in enumerate(top):
        clips.append(
            ClipCandidate(
                clip_id=f"fallback_{i:04d}",
                display_name=f"fallback_{i:04d}",
                source_path=vod.source_path,
                start_seconds=round(start, 3),
                end_seconds=round(end, 3),
                mandatory=False,
                seed_type="fallback_discovery",
                score=round(score, 4),
                reason=f"No chapters found: audio peak + activity (hook={hook:.2f}; {detail})",
            )
        )

    return clips
