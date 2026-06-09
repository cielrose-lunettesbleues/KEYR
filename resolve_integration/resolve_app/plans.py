from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ClipPlan:
    clip_id: str
    display_name: str
    timeline_name: str
    source_path: str
    start_seconds: float
    end_seconds: float
    seed_type: str


def parse_manifest(manifest_path: Path) -> tuple[str, list[ClipPlan]]:
    with manifest_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    batch_id = str(data.get("batch_id", manifest_path.stem))
    raw_clips = data.get("clips", [])
    plans: list[ClipPlan] = []
    for clip in raw_clips:
        try:
            start = float(clip["start_seconds"])
            end = float(clip["end_seconds"])
            if end <= start:
                continue
            plans.append(
                ClipPlan(
                    clip_id=str(clip["clip_id"]),
                    display_name=str(clip.get("display_name", clip.get("clip_id", ""))),
                    timeline_name=str(clip.get("timeline_name", "") or ""),
                    source_path=str(clip["source_path"]),
                    start_seconds=start,
                    end_seconds=end,
                    seed_type=str(clip.get("seed_type", "unknown")),
                )
            )
        except Exception:
            continue
    return batch_id, plans


def plan_key(plan: ClipPlan) -> str:
    return plan.clip_id


def safe_name_token(text: str, limit: int = 72) -> str:
    forbidden = set('\\/:*?"<>|')
    cleaned = "".join(ch if (ch.isalnum() or ch in "-_ ") and ch not in forbidden else " " for ch in text)
    cleaned = " ".join(cleaned.split())
    if not cleaned:
        cleaned = "clip"
    return cleaned[:limit]


def suffix_timeline_name(base_name: str, suffix: str = "__silence_cut") -> str:
    clean = safe_name_token(base_name, limit=100)
    if clean.endswith(suffix):
        return clean
    return safe_name_token(f"{clean}{suffix}", limit=120)
