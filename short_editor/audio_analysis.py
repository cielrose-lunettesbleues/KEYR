from __future__ import annotations

import math
import os
import re
import subprocess
import wave
from pathlib import Path
from typing import Callable

_TIME_RE = re.compile(r'time=(\d+):(\d+):(\d+\.?\d*)')


def _popen_kwargs() -> dict:
    kw: dict = {}
    if os.name == "nt":
        kw["creationflags"] = subprocess.CREATE_NO_WINDOW
    return kw


def get_duration_seconds(source: str) -> float | None:
    """Return media duration in seconds via ffprobe, or None on failure."""
    cmd = ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
           "-of", "default=noprint_wrappers=1:nokey=1", source]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False, **_popen_kwargs())
    if result.returncode == 0:
        try:
            return float(result.stdout.strip())
        except ValueError:
            pass
    return None


def _run_ffmpeg_tracked(
    cmd: list[str],
    duration_s: float | None,
    on_progress: Callable[[int], None] | None,
) -> int:
    """Run ffmpeg via Popen, parsing stderr for time= progress updates.

    Calls on_progress(0-100) as ffmpeg reports elapsed time.
    Returns the process returncode.
    """
    proc = subprocess.Popen(cmd, stderr=subprocess.PIPE, stdout=subprocess.DEVNULL, **_popen_kwargs())
    for raw in proc.stderr:  # type: ignore[union-attr]
        if not on_progress or not duration_s or duration_s <= 0:
            continue
        try:
            line = raw.decode("utf-8", errors="replace")
        except Exception:
            continue
        m = _TIME_RE.search(line)
        if m:
            try:
                t = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
                on_progress(min(99, int(t / duration_s * 100)))
            except Exception:
                pass
    proc.wait()
    return proc.returncode


def extract_mono_wav(source: str, wav_path: Path) -> None:
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


def count_audio_streams(source: str) -> int:
    """Return the number of audio streams in a media file using ffprobe."""
    run_kwargs = {"capture_output": True, "text": True, "check": False}
    if os.name == "nt":
        run_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    cmd = ["ffprobe", "-v", "quiet", "-select_streams", "a",
           "-show_entries", "stream=index", "-of", "csv", source]
    result = subprocess.run(cmd, **run_kwargs)
    if result.returncode != 0:
        return 0
    lines = [l for l in result.stdout.strip().splitlines() if l.strip()]
    return len(lines)


def vod_has_audio(path: Path) -> bool:
    """Return True if the file has at least one audio stream."""
    return count_audio_streams(str(path)) > 0


def create_clean_vod(
    source: str,
    output_path: Path,
    audio_track_number: int,
    on_progress: Callable[[int], None] | None = None,
) -> bool:
    """Stream-copy the VOD keeping only one audio track, producing a clean file for Resolve.

    Uses -c copy (no re-encode) so it finishes in seconds regardless of VOD length.
    audio_track_number is 1-indexed (matching OBS track numbering).
    Returns False if the requested track does not exist (use create_mixed_vod as fallback).
    on_progress is called with 0-100 as the copy progresses.
    """
    audio_stream_idx = max(0, audio_track_number - 1)
    cmd = [
        "ffmpeg", "-y",
        "-i", source,
        "-map", "0:v:0",
        "-map", f"0:a:{audio_stream_idx}",
        "-c", "copy",
        str(output_path),
    ]
    if on_progress:
        duration = get_duration_seconds(source)
        returncode = _run_ffmpeg_tracked(cmd, duration, on_progress)
        on_progress(100)
    else:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False, **_popen_kwargs())
        returncode = result.returncode
    if returncode != 0:
        output_path.unlink(missing_ok=True)
        return False
    return output_path.exists() and output_path.stat().st_size > 0 and vod_has_audio(output_path)


def create_mixed_vod(
    source: str,
    output_path: Path,
    audio_track_indices: list[int],
    on_progress: Callable[[int], None] | None = None,
) -> bool:
    """Mix multiple audio tracks (0-indexed) into one and stream-copy video.

    Used as fallback when a specific base_track does not exist in the source.
    Requires audio re-encode (AAC 320k) since tracks are mixed via amix filter.
    on_progress is called with 0-100 as processing progresses.
    """
    if not audio_track_indices:
        return False

    if len(audio_track_indices) == 1:
        idx = audio_track_indices[0]
        cmd = [
            "ffmpeg", "-y",
            "-i", source,
            "-map", "0:v:0",
            "-map", f"0:a:{idx}",
            "-c", "copy",
            str(output_path),
        ]
    else:
        inputs = "".join(f"[0:a:{idx}]" for idx in audio_track_indices)
        filter_complex = f"{inputs}amix=inputs={len(audio_track_indices)}:normalize=0[a]"
        cmd = [
            "ffmpeg", "-y",
            "-i", source,
            "-map", "0:v:0",
            "-filter_complex", filter_complex,
            "-map", "[a]",
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "320k",
            str(output_path),
        ]

    if on_progress:
        duration = get_duration_seconds(source)
        returncode = _run_ffmpeg_tracked(cmd, duration, on_progress)
        on_progress(100)
    else:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False, **_popen_kwargs())
        returncode = result.returncode
    if returncode != 0:
        output_path.unlink(missing_ok=True)
        return False
    return output_path.exists() and output_path.stat().st_size > 0 and vod_has_audio(output_path)


def extract_stereo_track_for_resolve(source: str, output_path: Path, obs_track_number: int) -> bool:
    """Extract an OBS audio track as stereo 48 kHz WAV for import into Resolve."""
    run_kwargs = {"capture_output": True, "text": True, "check": False}
    if os.name == "nt":
        run_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    audio_stream_idx = max(0, obs_track_number - 1)
    cmd = [
        "ffmpeg", "-y",
        "-i", source,
        "-map", f"0:a:{audio_stream_idx}?",
        "-ac", "2",
        "-ar", "48000",
        "-vn",
        str(output_path),
    ]
    result = subprocess.run(cmd, **run_kwargs)
    return result.returncode == 0 and output_path.exists() and output_path.stat().st_size > 0


def extract_track_wav(source: str, wav_path: Path, obs_track_number: int) -> bool:
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


def compute_window_energy(wav_path: Path, window_seconds: float = 1.0) -> list[tuple[float, float]]:
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
            rms = pcm_rms(raw, sample_width)
            t = i * window_seconds
            energies.append((t, rms))
            i += 1
    return energies


def build_energy_map(track_energies: list[tuple[float, float]]) -> dict[int, float]:
    return {int(t): e for t, e in track_energies}


def merge_energy_tracks(tracks: list[list[tuple[float, float]]], weights: list[float]) -> list[tuple[float, float]]:
    if not tracks:
        return []
    maps = [build_energy_map(t) for t in tracks]
    max_t = 0
    for energy_map in maps:
        if energy_map:
            max_t = max(max_t, max(energy_map.keys()))

    merged: list[tuple[float, float]] = []
    for sec in range(max_t + 1):
        val = 0.0
        for idx, energy_map in enumerate(maps):
            val += weights[idx] * energy_map.get(sec, 0.0)
        merged.append((float(sec), val))
    return merged


def pcm_rms(raw: bytes, sample_width: int) -> float:
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


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    if p <= 0:
        return min(values)
    if p >= 1:
        return max(values)
    sorted_values = sorted(values)
    idx = int(round((len(sorted_values) - 1) * p))
    return sorted_values[idx]
