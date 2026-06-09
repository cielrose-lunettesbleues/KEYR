from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def transcript_path_for_vod(root: Path, vod_path: Path) -> Path:
    return (root / "output" / "transcripts" / f"{vod_path.stem}.json").resolve()


def read_manifest_safe(path: Path) -> dict[str, Any] | None:
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def paths_match_lenient(left: Any, right: Any) -> bool:
    left_text = str(left or "").strip()
    right_text = str(right or "").strip()
    if not left_text or not right_text:
        return False
    try:
        if str(Path(left_text).resolve()).lower() == str(Path(right_text).resolve()).lower():
            return True
    except Exception:
        pass
    try:
        left_path = Path(left_text)
        right_path = Path(right_text)
        if left_path.name and right_path.name and left_path.name.lower() == right_path.name.lower():
            return True
    except Exception:
        pass
    return left_text.lower() == right_text.lower()


def manifest_matches_vod(data: dict[str, Any], vod_path: Path) -> bool:
    meta = data.get("meta", {}) if isinstance(data.get("meta", {}), dict) else {}
    meta_vod = str(meta.get("source_vod_path", "")).strip()
    if meta_vod and paths_match_lenient(meta_vod, vod_path):
        return True

    source_vods = data.get("source_vods", [])
    if isinstance(source_vods, list):
        for src in source_vods:
            if paths_match_lenient(src, vod_path):
                return True

    clips = data.get("clips", [])
    if isinstance(clips, list):
        for clip in clips:
            if isinstance(clip, dict) and paths_match_lenient(clip.get("source_path", ""), vod_path):
                return True
    return False


def manifest_has_valid_textplus_source(root: Path, data: dict[str, Any]) -> bool:
    meta = data.get("meta", {}) if isinstance(data.get("meta", {}), dict) else {}
    transcript = str(meta.get("transcript_path", "")).strip()
    if not transcript:
        return False
    transcript_path = Path(transcript)
    if not transcript_path.is_absolute():
        transcript_path = (root / transcript_path).resolve()
    return transcript_path.exists()


def find_existing_manifest_for_vod(root: Path, vod_path: Path) -> Path | None:
    manifest_dir = root / "output" / "manifests"
    if not manifest_dir.exists():
        return None
    files = sorted(manifest_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    candidates: list[tuple[int, Path]] = []
    for mf in files:
        data = read_manifest_safe(mf)
        if not data or not manifest_matches_vod(data, vod_path):
            continue
        meta = data.get("meta", {}) if isinstance(data.get("meta", {}), dict) else {}
        has_valid_textplus_source = manifest_has_valid_textplus_source(root, data)
        generated_with_subtitles = bool(meta.get("generated_with_subtitles", False))
        if has_valid_textplus_source:
            priority = 0
        elif generated_with_subtitles:
            priority = 1
        else:
            priority = 2
        candidates.append((priority, mf))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], -item[1].stat().st_mtime))
    return candidates[0][1]


def find_reusable_quality_manifest(root: Path, vod_path: Path, preset_id: str, use_transcript_for_selection: bool, subtitle_preset_id: str = "") -> Path | None:
    manifest_dir = root / "output" / "manifests"
    if not manifest_dir.exists():
        return None
    files = sorted(manifest_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    target_vod = str(vod_path.resolve())
    for mf in files:
        data = read_manifest_safe(mf)
        if not data:
            continue
        meta = data.get("meta", {}) if isinstance(data.get("meta", {}), dict) else {}
        if not bool(meta.get("generated_with_subtitles", False)):
            continue
        if str(meta.get("preset_id", "")).strip() != preset_id.strip():
            continue
        if subtitle_preset_id.strip() and str(meta.get("subtitle_preset_id", "")).strip() != subtitle_preset_id.strip():
            continue
        if bool(meta.get("use_transcript_for_selection", False)) != bool(use_transcript_for_selection):
            continue
        meta_vod = str(meta.get("source_vod_path", "")).strip()
        if meta_vod:
            try:
                if str(Path(meta_vod).resolve()) != target_vod:
                    continue
            except Exception:
                continue
        else:
            source_vods = data.get("source_vods", [])
            if not isinstance(source_vods, list) or not source_vods:
                continue
            try:
                if str(Path(str(source_vods[0])).resolve()) != target_vod:
                    continue
            except Exception:
                continue
        if not manifest_has_valid_textplus_source(root, data):
            continue
        return mf
    return None
