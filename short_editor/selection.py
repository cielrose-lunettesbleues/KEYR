from __future__ import annotations

from typing import Protocol, TypeVar


class HasTimeRange(Protocol):
    start_seconds: float
    end_seconds: float


T = TypeVar("T", bound=HasTimeRange)


def overlap_ratio_from_ranges(a_start: float, a_end: float, b_start: float, b_end: float) -> float:
    left = max(a_start, b_start)
    right = min(a_end, b_end)
    if right <= left:
        return 0.0
    inter = right - left
    shortest = max(0.001, min(a_end - a_start, b_end - b_start))
    return inter / shortest


def ranges_too_close(
    a_start: float,
    a_end: float,
    b_start: float,
    b_end: float,
    overlap_threshold: float = 0.35,
    min_center_distance_seconds: float = 60.0,
) -> bool:
    if overlap_ratio_from_ranges(a_start, a_end, b_start, b_end) > overlap_threshold:
        return True
    a_center = a_start + ((a_end - a_start) / 2.0)
    b_center = b_start + ((b_end - b_start) / 2.0)
    return abs(a_center - b_center) < min_center_distance_seconds


def ranges_too_close_dict(
    a: dict[str, float],
    b: dict[str, float],
    overlap_threshold: float = 0.35,
    min_center_distance_seconds: float = 60.0,
) -> bool:
    return ranges_too_close(
        float(a["start_seconds"]),
        float(a["end_seconds"]),
        float(b["start_seconds"]),
        float(b["end_seconds"]),
        overlap_threshold=overlap_threshold,
        min_center_distance_seconds=min_center_distance_seconds,
    )


def clips_too_close(a: HasTimeRange, b: HasTimeRange, overlap_threshold: float, min_center_distance_seconds: float = 60.0) -> bool:
    return ranges_too_close(
        a.start_seconds,
        a.end_seconds,
        b.start_seconds,
        b.end_seconds,
        overlap_threshold=overlap_threshold,
        min_center_distance_seconds=min_center_distance_seconds,
    )


def select_non_overlapping_candidates(
    existing: list[T],
    candidates: list[T],
    needed: int,
    overlap_threshold: float = 0.4,
) -> list[T]:
    if needed <= 0:
        return []
    selected: list[T] = []
    for candidate in candidates:
        too_close = any(clips_too_close(candidate, item, overlap_threshold) for item in existing)
        too_close = too_close or any(clips_too_close(candidate, item, overlap_threshold) for item in selected)
        if too_close:
            continue
        selected.append(candidate)
        if len(selected) >= needed:
            break
    return selected


def select_non_overlapping_dicts(
    existing: list[dict[str, float]],
    candidates: list[dict[str, float]],
    needed: int,
    overlap_threshold: float = 0.35,
) -> list[dict[str, float]]:
    if needed <= 0:
        return []
    selected: list[dict[str, float]] = []
    for candidate in candidates:
        too_close = any(ranges_too_close_dict(candidate, item, overlap_threshold) for item in existing)
        too_close = too_close or any(ranges_too_close_dict(candidate, item, overlap_threshold) for item in selected)
        if too_close:
            continue
        selected.append(candidate)
        if len(selected) >= needed:
            break
    return selected
