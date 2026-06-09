from __future__ import annotations

from math import ceil

from .models import ClipCandidate, VodManifest


def compute_quota(duration_seconds: float, quota_cfg: dict) -> tuple[int, int, int]:
    hours = max(duration_seconds / 3600.0, 0.01)
    min_q = ceil(quota_cfg["min_per_hour"] * hours)
    target_q = ceil(quota_cfg["target_per_hour"] * hours)
    max_q = ceil(quota_cfg["max_per_hour"] * hours)
    return min_q, target_q, max_q


def clamp(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(value, max_value))


def build_chapter_candidates_with_skips(vod: VodManifest, cfg: dict) -> tuple[list[ClipCandidate], list[str]]:
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

        start = clamp(chapter.start_seconds - pre, 0.0, vod.duration_seconds)
        end = clamp(chapter.start_seconds + post, 0.0, vod.duration_seconds)

        length = end - start
        if length < min_len:
            end = clamp(start + min_len, 0.0, vod.duration_seconds)
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
