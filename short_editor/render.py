from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from .models import ClipCandidate


def _probe_audio_stream_count(source: Path) -> int:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_streams",
        "-of",
        "json",
        str(source),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return 0
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return 0
    streams = data.get("streams", [])
    return sum(1 for s in streams if s.get("codec_type") == "audio")


def _candidate_obs_tracks(cfg: dict, audio_stream_count: int) -> list[int]:
    if audio_stream_count <= 0:
        return [1]

    audio_cfg = cfg.get("audio", {})
    analysis_cfg = audio_cfg.get("analysis", {})
    render_cfg = audio_cfg.get("render", {})

    muted = set(int(x) for x in audio_cfg.get("always_muted_tracks", []))
    base_track = int(render_cfg.get("base_track", 6))
    voice_track = int(analysis_cfg.get("voice_track", 2))
    context_tracks = [int(x) for x in analysis_cfg.get("context_tracks", [5])]

    preferred_obs_tracks: list[int] = [base_track, 6, 5, voice_track, 1]
    preferred_obs_tracks.extend(context_tracks)

    seen: set[int] = set()
    deduped = []
    for t in preferred_obs_tracks:
        if t not in seen:
            seen.add(t)
            deduped.append(t)

    valid_obs_tracks = [t for t in deduped if 1 <= t <= audio_stream_count and t not in muted]
    return valid_obs_tracks if valid_obs_tracks else [1]


def _measure_track_mean_db(source: Path, obs_track: int, start_seconds: float, probe_seconds: float) -> float:
    stream_idx = max(0, obs_track - 1)
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-v",
        "info",
        "-ss",
        f"{start_seconds}",
        "-t",
        f"{probe_seconds}",
        "-i",
        str(source),
        "-map",
        f"0:a:{stream_idx}?",
        "-af",
        "volumedetect",
        "-f",
        "null",
        "NUL",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    text = (result.stdout or "") + "\n" + (result.stderr or "")
    match = re.search(r"mean_volume:\s*(-?\d+(?:\.\d+)?)\s*dB", text)
    if not match:
        return -120.0
    return float(match.group(1))


def _select_best_audio_track_for_clip(source: Path, clip: ClipCandidate, cfg: dict, audio_stream_count: int) -> tuple[str, int, float]:
    candidates = _candidate_obs_tracks(cfg, audio_stream_count)
    probe_seconds = min(8.0, max(2.0, clip.end_seconds - clip.start_seconds))
    best_track = candidates[0]
    best_db = -120.0

    for obs_track in candidates:
        mean_db = _measure_track_mean_db(source, obs_track, clip.start_seconds, probe_seconds)
        if mean_db > best_db:
            best_db = mean_db
            best_track = obs_track

    stream_idx = max(0, best_track - 1)
    return f"0:a:{stream_idx}?", best_track, best_db


def render_clips_ffmpeg(clips: list[ClipCandidate], cfg: dict, output_dir: Path) -> tuple[dict[str, str], list[str]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    rendered: dict[str, str] = {}
    warnings: list[str] = []

    w = int(cfg["video"]["output_width"])
    h = int(cfg["video"]["output_height"])
    fps = int(cfg["video"]["output_fps"])

    # Center-crop landscape to 9:16 then scale.
    vf = f"crop=ih*9/16:ih:(iw-ih*9/16)/2:0,scale={w}:{h},fps={fps}"
    source_audio_count_cache: dict[str, int] = {}

    for clip in clips:
        source = Path(clip.source_path)
        source_key = str(source)
        if source_key not in source_audio_count_cache:
            source_audio_count_cache[source_key] = _probe_audio_stream_count(source)
        audio_count = source_audio_count_cache[source_key]

        audio_map, selected_track, selected_db = _select_best_audio_track_for_clip(source, clip, cfg, audio_count)
        configured_base = int(cfg.get("audio", {}).get("render", {}).get("base_track", 6))
        if selected_track != configured_base:
            warnings.append(
                f"Render audio track auto-select for {clip.clip_id}: requested track {configured_base}, using track {selected_track} (mean {selected_db:.1f} dB)."
            )
        if selected_db < -45.0:
            warnings.append(f"Very low audio level for {clip.clip_id}: {selected_db:.1f} dB.")

        safe_id = clip.clip_id.replace("/", "_").replace("\\", "_")
        target = output_dir / f"{safe_id}.mp4"
        duration = max(0.1, clip.end_seconds - clip.start_seconds)

        cmd = [
            "ffmpeg",
            "-y",
            "-sn",
            "-dn",
            "-ss",
            f"{clip.start_seconds}",
            "-i",
            str(source),
            "-map_metadata",
            "-1",
            "-map_chapters",
            "-1",
            "-t",
            f"{duration}",
            "-vf",
            vf,
            "-map",
            "0:v:0",
            "-map",
            audio_map,
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-af",
            "loudnorm=I=-16:LRA=11:TP=-1.5",
            "-ar",
            "48000",
            "-ac",
            "2",
            "-b:a",
            "160k",
            "-movflags",
            "+faststart",
            str(target),
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            warnings.append(f"Render failed for {clip.clip_id}: {result.stderr.strip().splitlines()[-1] if result.stderr else 'unknown error'}")
            continue

        rendered[clip.clip_id] = str(target)

    return rendered, warnings
