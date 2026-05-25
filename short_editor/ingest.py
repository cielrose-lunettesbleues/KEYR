from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from .models import AudioTrackInfo, Chapter, VodManifest


def _run_ffprobe_json(video_path: Path) -> dict:
    run_kwargs = {
        "capture_output": True,
        "text": True,
        "check": False,
    }
    if os.name == "nt":
        run_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_format",
        "-show_streams",
        "-show_chapters",
        "-of",
        "json",
        str(video_path),
    ]
    result = subprocess.run(cmd, **run_kwargs)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed for {video_path}: {result.stderr.strip()}")
    return json.loads(result.stdout)


def _parse_fps(rate: str) -> float:
    if not rate or rate == "0/0":
        return 0.0
    num, den = rate.split("/")
    n = float(num)
    d = float(den)
    return n / d if d else 0.0


def probe_vod(video_path: Path) -> VodManifest:
    data = _run_ffprobe_json(video_path)
    streams = data.get("streams", [])
    chapters_data = data.get("chapters", [])
    format_data = data.get("format", {})

    v_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
    if not v_stream:
        raise RuntimeError(f"No video stream found in {video_path}")

    width = int(v_stream.get("width", 0))
    height = int(v_stream.get("height", 0))
    fps = _parse_fps(v_stream.get("r_frame_rate", "0/0"))
    duration = float(format_data.get("duration", 0.0))

    chapters: list[Chapter] = []
    for i, ch in enumerate(chapters_data):
        title = ch.get("tags", {}).get("title", "")
        chapters.append(
            Chapter(
                index=i,
                start_seconds=float(ch.get("start_time", 0.0)),
                end_seconds=float(ch.get("end_time", 0.0)),
                title=title,
            )
        )

    audio_tracks: list[AudioTrackInfo] = []
    for s in streams:
        if s.get("codec_type") != "audio":
            continue
        sr = int(s.get("sample_rate", 0)) if s.get("sample_rate") else 0
        audio_tracks.append(
            AudioTrackInfo(
                index=int(s.get("index", -1)),
                codec=s.get("codec_name", "unknown"),
                channels=int(s.get("channels", 0)),
                sample_rate=sr,
            )
        )

    return VodManifest(
        source_path=str(video_path),
        duration_seconds=duration,
        width=width,
        height=height,
        fps=fps,
        chapters=chapters,
        audio_tracks=audio_tracks,
    )
