from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class Chapter:
    index: int
    start_seconds: float
    end_seconds: float
    title: str = ""


@dataclass
class AudioTrackInfo:
    index: int
    codec: str
    channels: int
    sample_rate: int


@dataclass
class VodManifest:
    source_path: str
    duration_seconds: float
    width: int
    height: int
    fps: float
    chapters: list[Chapter] = field(default_factory=list)
    audio_tracks: list[AudioTrackInfo] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ClipCandidate:
    clip_id: str
    display_name: str
    source_path: str
    start_seconds: float
    end_seconds: float
    mandatory: bool
    seed_type: str
    score: float
    reason: str
    overflow: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BatchReport:
    batch_id: str
    source_vods: list[str]
    clips: list[ClipCandidate]
    pipeline_version: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "batch_id": self.batch_id,
            "source_vods": self.source_vods,
            "clips": [c.to_dict() for c in self.clips],
            "pipeline_version": self.pipeline_version,
        }
