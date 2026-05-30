from __future__ import annotations

import math
import os
import subprocess
import tempfile
import wave
import json
import re
from math import ceil
from pathlib import Path

from .models import ClipCandidate, VodManifest
from .feedback import load_user_lexicon


BASE_FUNNY = {"mdr", "ptdr", "lol", "haha", "rires", "incroyable", "abus", "hilarant"}
BASE_CLIVANT = {"jamais", "toujours", "nul", "incroyable", "scam", "honte", "debat", "controverse"}
BASE_ETONNANT = {"wow", "what", "attends", "serieusement", "impossible", "incroyable", "dingue", "surpris"}


def _simple_tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-zA-Z0-9']+", (text or "").lower()) if len(t) >= 3]


def _load_transcript_entries_for_vod(vod: VodManifest, cfg: dict, work_dir: Path) -> list[dict]:
    out_dir = Path(cfg.get("paths", {}).get("output_dir", "output"))
    if not out_dir.is_absolute():
        out_dir = (work_dir.parent / out_dir).resolve()
    t_path = out_dir / "transcripts" / f"{Path(vod.source_path).stem}.json"
    if not t_path.exists():
        return []
    try:
        with t_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        entries = data.get("entries", [])
        return entries if isinstance(entries, list) else []
    except Exception:
        return []


def _text_score_for_window(entries: list[dict], start: float, end: float, lexicon: dict) -> tuple[float, str]:
    text_parts: list[str] = []
    for e in entries:
        try:
            es = float(e.get("start", 0.0))
            ee = float(e.get("end", es))
        except Exception:
            continue
        if ee < start or es > end:
            continue
        text_parts.append(str(e.get("text", "")))
    text = " ".join(text_parts)
    if not text.strip():
        return 0.0, ""
    toks = _simple_tokens(text)
    if not toks:
        return 0.0, ""

    funny = sum(1 for t in toks if t in BASE_FUNNY)
    cliv = sum(1 for t in toks if t in BASE_CLIVANT)
    eton = sum(1 for t in toks if t in BASE_ETONNANT)

    lex_cats = lexicon.get("categories", {}) if isinstance(lexicon, dict) else {}
    weighted = 0.0
    matched: list[str] = []
    for cat in ("drole", "clivant", "etonnant"):
        table = lex_cats.get(cat, {}) if isinstance(lex_cats, dict) else {}
        for t in toks:
            w = float(table.get(t, 0.0)) if isinstance(table, dict) else 0.0
            if abs(w) > 0.0:
                weighted += w
                if w > 0:
                    matched.append(t)
    base = (0.45 * min(1.0, funny / 3.0)) + (0.25 * min(1.0, cliv / 3.0)) + (0.30 * min(1.0, eton / 3.0))
    learned = max(-1.0, min(1.5, weighted / max(6.0, len(toks))))
    score = max(0.0, min(1.0, base + (0.35 * learned)))
    reason_bits = []
    if funny:
        reason_bits.append(f"funny={funny}")
    if cliv:
        reason_bits.append(f"clivant={cliv}")
    if eton:
        reason_bits.append(f"etonnant={eton}")
    if matched:
        reason_bits.append("matched=" + ",".join(sorted(set(matched))[:4]))
    return score, ";".join(reason_bits)


def compute_quota(duration_seconds: float, quota_cfg: dict) -> tuple[int, int, int]:
    hours = max(duration_seconds / 3600.0, 0.01)
    min_q = ceil(quota_cfg["min_per_hour"] * hours)
    target_q = ceil(quota_cfg["target_per_hour"] * hours)
    max_q = ceil(quota_cfg["max_per_hour"] * hours)
    return min_q, target_q, max_q


def _clamp(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(value, max_value))


def _overlap_ratio_from_ranges(a_start: float, a_end: float, b_start: float, b_end: float) -> float:
    left = max(a_start, b_start)
    right = min(a_end, b_end)
    if right <= left:
        return 0.0
    inter = right - left
    shortest = max(0.001, min(a_end - a_start, b_end - b_start))
    return inter / shortest


def build_chapter_candidates(vod: VodManifest, cfg: dict) -> list[ClipCandidate]:
    video_cfg = cfg["video"]
    min_len = float(video_cfg["min_clip_seconds"])
    max_len = float(video_cfg["max_clip_seconds"])
    pre = float(video_cfg["chapter_pre_roll_seconds"])
    post = float(video_cfg["chapter_post_roll_seconds"])

    clips: list[ClipCandidate] = []
    for i, chapter in enumerate(vod.chapters):
        start = _clamp(chapter.start_seconds - pre, 0.0, vod.duration_seconds)
        end = _clamp(chapter.start_seconds + post, 0.0, vod.duration_seconds)

        length = end - start
        if length < min_len:
            end = _clamp(start + min_len, 0.0, vod.duration_seconds)
        if end - start > max_len:
            end = start + max_len

        clips.append(
            ClipCandidate(
                clip_id=f"chapter_{i:04d}",
                display_name=f"chapter_{i:04d}",
                source_path=vod.source_path,
                start_seconds=round(start, 3),
                end_seconds=round(end, 3),
                mandatory=True,
                seed_type="chapter",
                score=1.0,
                reason="OBS chapter marker",
            )
        )
    return clips


def build_chapter_candidates_with_skips(vod: VodManifest, cfg: dict) -> tuple[list[ClipCandidate], list[str]]:
    """Build chapter candidates while applying skip rules.

    Skip rules:
    - always ignore chapter index 0
    - ignore chapters that start at 0s
    """
    video_cfg = cfg["video"]
    min_len = float(video_cfg["min_clip_seconds"])
    max_len = float(video_cfg["max_clip_seconds"])
    pre = float(video_cfg["chapter_pre_roll_seconds"])
    post = float(video_cfg["chapter_post_roll_seconds"])

    clips: list[ClipCandidate] = []
    skips: list[str] = []
    for i, chapter in enumerate(vod.chapters):
        if chapter.index == 0 or chapter.start_seconds <= 0.001:
            skips.append(f"Skipped chapter {chapter.index} at {chapter.start_seconds:.3f}s: auto_start_chapter_0")
            continue

        start = _clamp(chapter.start_seconds - pre, 0.0, vod.duration_seconds)
        end = _clamp(chapter.start_seconds + post, 0.0, vod.duration_seconds)

        length = end - start
        if length < min_len:
            end = _clamp(start + min_len, 0.0, vod.duration_seconds)
        if end - start > max_len:
            end = start + max_len

        clips.append(
            ClipCandidate(
                clip_id=f"chapter_{i:04d}",
                display_name=f"chapter_{i:04d}",
                source_path=vod.source_path,
                start_seconds=round(start, 3),
                end_seconds=round(end, 3),
                mandatory=True,
                seed_type="chapter",
                score=1.0,
                reason="OBS chapter marker",
            )
        )

    return clips, skips


def tag_overflow(clips: list[ClipCandidate], max_quota: int) -> list[ClipCandidate]:
    for idx, clip in enumerate(clips):
        clip.overflow = idx >= max_quota
    return clips


def _extract_mono_wav(source: str, wav_path: Path) -> None:
    run_kwargs = {"capture_output": True, "text": True, "check": False}
    if os.name == "nt":
        run_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        source,
        "-map",
        "0:a:0",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-vn",
        str(wav_path),
    ]
    result = subprocess.run(cmd, **run_kwargs)
    if result.returncode != 0:
        raise RuntimeError(f"Audio extraction failed: {result.stderr.strip()}")


def _extract_track_wav(source: str, wav_path: Path, obs_track_number: int) -> bool:
    run_kwargs = {"capture_output": True, "text": True, "check": False}
    if os.name == "nt":
        run_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

    audio_stream_idx = max(0, obs_track_number - 1)
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        source,
        "-map",
        f"0:a:{audio_stream_idx}?",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-vn",
        str(wav_path),
    ]
    result = subprocess.run(cmd, **run_kwargs)
    return result.returncode == 0 and wav_path.exists() and wav_path.stat().st_size > 0


def _compute_window_energy(wav_path: Path, window_seconds: float = 1.0) -> list[tuple[float, float]]:
    energies: list[tuple[float, float]] = []
    with wave.open(str(wav_path), "rb") as wf:
        frame_rate = wf.getframerate()
        sample_width = wf.getsampwidth()
        frames_per_window = max(1, int(frame_rate * window_seconds))

        i = 0
        while True:
            raw = wf.readframes(frames_per_window)
            if not raw:
                break
            rms = _pcm_rms(raw, sample_width)
            t = i * window_seconds
            energies.append((t, rms))
            i += 1
    return energies


def _build_energy_map(track_energies: list[tuple[float, float]]) -> dict[int, float]:
    return {int(t): e for t, e in track_energies}


def _merge_energy_tracks(tracks: list[list[tuple[float, float]]], weights: list[float]) -> list[tuple[float, float]]:
    if not tracks:
        return []
    maps = [_build_energy_map(t) for t in tracks]
    max_t = 0
    for m in maps:
        if m:
            max_t = max(max_t, max(m.keys()))

    merged: list[tuple[float, float]] = []
    for sec in range(max_t + 1):
        val = 0.0
        for idx, m in enumerate(maps):
            val += weights[idx] * m.get(sec, 0.0)
        merged.append((float(sec), val))
    return merged


def _pcm_rms(raw: bytes, sample_width: int) -> float:
    if sample_width != 2 or not raw:
        return 0.0
    sample_count = len(raw) // 2
    if sample_count == 0:
        return 0.0
    total = 0.0
    for i in range(0, len(raw), 2):
        sample = int.from_bytes(raw[i : i + 2], byteorder="little", signed=True)
        total += float(sample * sample)
    return math.sqrt(total / sample_count)


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


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    if p <= 0:
        return min(values)
    if p >= 1:
        return max(values)
    sorted_values = sorted(values)
    idx = int(round((len(sorted_values) - 1) * p))
    return sorted_values[idx]


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
        if _extract_track_wav(vod.source_path, voice_wav, voice_track):
            energies = _compute_window_energy(voice_wav, window_seconds=window_seconds)
        elif _extract_track_wav(vod.source_path, mono_wav, render_track):
            energies = _compute_window_energy(mono_wav, window_seconds=window_seconds)
            energy_source = "render"
            warnings_out.append(f"{Path(vod.source_path).name}: trim boundary used render track fallback ({render_track}).")
        else:
            _extract_mono_wav(vod.source_path, mono_wav)
            energies = _compute_window_energy(mono_wav, window_seconds=window_seconds)
            energy_source = "mono"
            warnings_out.append(f"{Path(vod.source_path).name}: trim boundary used mono fallback.")

    if not energies:
        warnings_out.append(f"{Path(vod.source_path).name}: trim boundary skipped (no audio energy data).")
        return warnings_out

    values = [e for _, e in energies]
    activity_floor = _percentile(values, threshold_percentile)

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
        warnings_out.append(
            f"{clip.clip_id}: dead-air trim {old_start:.2f}-{old_end:.2f}s -> {new_start:.2f}-{new_end:.2f}s"
        )

    return warnings_out


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
    transcript_entries = _load_transcript_entries_for_vod(vod, cfg, work_dir)

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

        text_score, text_reason = _text_score_for_window(transcript_entries, start, end, lexicon)
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
            text_score, text_reason = _text_score_for_window(transcript_entries, start, end, lexicon)
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
            text_score, text_reason = _text_score_for_window(transcript_entries, start, end, lexicon)
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

    # De-duplicate near-identical ranges before truncating.
    deduped: list[tuple[float, float, float, float, str]] = []
    for cand in sorted(scored_candidates, key=lambda x: x[0], reverse=True):
        _, s, e, _, _ = cand
        if any(_overlap_ratio_from_ranges(s, e, ds, de) > 0.85 for _, ds, de, _, _ in deduped):
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
