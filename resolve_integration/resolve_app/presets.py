from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DEFAULT_SUBTITLE_PRESET_ID = "Minimal clean"
SUBTITLE_TEMPLATE_AUTO_LABEL = "Auto-detect (Recommended)"


def presets_path(root: Path) -> Path:
    return root / "config" / "resolve_presets.json"


def default_subtitle_presets() -> dict[str, Any]:
    return {
        DEFAULT_SUBTITLE_PRESET_ID: {
            "name": DEFAULT_SUBTITLE_PRESET_ID,
            "font": "Arial",
            "font_style": "Bold",
            "font_size": 0.085,
            "color": "#FFFFFF",
            "position_x": 0.5,
            "position_y": 0.82,
            "words_per_subtitle": 3,
            "max_chars_per_line": 24,
            "subtitle_template_name": SUBTITLE_TEMPLATE_AUTO_LABEL,
            "subtitle_offset_ms": -500,
        },
        "Punchy jaune": {
            "name": "Punchy jaune",
            "font": "Arial",
            "font_style": "Bold",
            "font_size": 0.095,
            "color": "#FFF04A",
            "position_x": 0.5,
            "position_y": 0.78,
            "words_per_subtitle": 2,
            "max_chars_per_line": 20,
            "subtitle_template_name": SUBTITLE_TEMPLATE_AUTO_LABEL,
            "subtitle_offset_ms": -500,
        },
    }


def default_presets() -> dict[str, Any]:
    return {
        "version": "1.0",
        "profiles": {
            "valo": {"label": "Valo", "active_preset": "Valorant Preset", "active_subtitle_preset": DEFAULT_SUBTITLE_PRESET_ID, "max_transcript_clip_seconds": 45},
            "jeu": {"label": "Jeu", "active_preset": "Jeux", "active_subtitle_preset": DEFAULT_SUBTITLE_PRESET_ID, "max_transcript_clip_seconds": 45},
            "react": {"label": "React", "active_preset": "Just chatting", "active_subtitle_preset": DEFAULT_SUBTITLE_PRESET_ID, "max_transcript_clip_seconds": 45},
        },
        "subtitle_presets": default_subtitle_presets(),
        "presets": {
            "Valorant Preset": {
                "name": "Valorant Preset",
                "profile": "valo",
                "mode": "fixed_split",
                "layers_count": 2,
                "safe_padding": 0.06,
                "max_clip_seconds": 45,
                "gameplay": {"zoom_x": 1.65, "zoom_y": 1.65, "pan": 0.0, "tilt": 0.62, "crop_top": 0.0, "crop_bottom": 0.42, "crop_left": 0.0, "crop_right": 0.0},
                "camera": {"zoom_x": 3.2, "zoom_y": 3.2, "pan": 0.72, "tilt": -0.82, "crop_top": 0.0, "crop_bottom": 0.0, "crop_left": 0.0, "crop_right": 0.0},
            },
            "Jeux": {
                "name": "Jeux",
                "profile": "valo",
                "mode": "fixed_split",
                "safe_padding": 0.06,
                "max_clip_seconds": 45,
                "gameplay": {"zoom_x": 1.78, "zoom_y": 1.78, "pan": 117.72, "tilt": 1388.18, "crop_top": 0.0, "crop_bottom": 0.0, "crop_left": 0.0, "crop_right": 0.0},
                "camera": {"zoom_x": 3.74, "zoom_y": 3.74, "pan": -1460.0, "tilt": 448.62, "crop_top": 0.0, "crop_bottom": 0.42, "crop_left": 0.0, "crop_right": 0.0},
            },
            "Just chatting": {
                "name": "Just chatting",
                "profile": "react",
                "mode": "fixed_split",
                "safe_padding": 0.06,
                "max_clip_seconds": 45,
                "single": {"zoom_x": 0.1, "zoom_y": 0.1, "pan": 0.0, "tilt": 0.0, "crop_top": 0.0, "crop_bottom": 0.0, "crop_left": 0.0, "crop_right": 0.0},
                "gameplay": {"zoom_x": 2.62, "zoom_y": 2.62, "pan": -1.0, "tilt": 1.0, "crop_top": 0.0, "crop_bottom": 0.0, "crop_left": 0.0, "crop_right": 0.0},
                "camera": {"zoom_x": 3.74, "zoom_y": 3.74, "pan": 1.0, "tilt": 1.0, "crop_top": 0.0, "crop_bottom": 0.42, "crop_left": 0.0, "crop_right": 0.0},
            },
        },
    }


def coerce_float(value: Any, default: float, min_value: float | None = None, max_value: float | None = None) -> float:
    try:
        out = float(value)
    except Exception:
        out = default
    if min_value is not None and out < min_value:
        out = min_value
    if max_value is not None and out > max_value:
        out = max_value
    return out


def coerce_int(value: Any, default: int, min_value: int | None = None, max_value: int | None = None) -> int:
    try:
        out = int(float(str(value).strip()))
    except Exception:
        out = default
    if min_value is not None and out < min_value:
        out = min_value
    if max_value is not None and out > max_value:
        out = max_value
    return out


def subtitle_preset_captions_overrides(preset: dict[str, Any]) -> dict[str, Any]:
    words = coerce_int(preset.get("words_per_subtitle", 3), 3, 1, 8)
    max_chars = coerce_int(preset.get("max_chars_per_line", 24), 24, 8, 80)
    return {"min_words_per_chunk": 1, "preferred_words_per_chunk": words, "max_words_per_chunk": words, "max_chars_per_line": max_chars}


def merge_subtitle_preset_into_config(cfg: dict[str, Any], subtitle_preset: dict[str, Any] | None) -> dict[str, Any]:
    if not subtitle_preset:
        return cfg
    out = dict(cfg)
    captions = dict(out.get("captions", {}) if isinstance(out.get("captions", {}), dict) else {})
    captions.update(subtitle_preset_captions_overrides(subtitle_preset))
    out["captions"] = captions
    return out


def subtitle_style_from_preset(preset: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(preset, dict):
        return {}
    return {
        "font": str(preset.get("font", "Arial")).strip() or "Arial",
        "font_style": str(preset.get("font_style", "Bold")).strip() or "Bold",
        "font_size": coerce_float(preset.get("font_size", 0.085), 0.085, 0.01, 0.5),
        "color": str(preset.get("color", "#FFFFFF")).strip() or "#FFFFFF",
        "position_x": coerce_float(preset.get("position_x", 0.5), 0.5, 0.0, 1.0),
        "position_y": coerce_float(preset.get("position_y", 0.82), 0.82, 0.0, 1.0),
    }


def normalize_subtitle_presets(data: dict[str, Any]) -> bool:
    changed = False
    defaults = default_subtitle_presets()
    subtitle_presets = data.get("subtitle_presets", {}) if isinstance(data, dict) else {}
    if not isinstance(subtitle_presets, dict):
        subtitle_presets = {}
        changed = True
    for preset_id, preset_data in defaults.items():
        if preset_id not in subtitle_presets or not isinstance(subtitle_presets.get(preset_id), dict):
            subtitle_presets[preset_id] = dict(preset_data)
            changed = True
    data["subtitle_presets"] = subtitle_presets

    profiles = data.get("profiles", {}) if isinstance(data.get("profiles", {}), dict) else {}
    for profile_data in profiles.values():
        if not isinstance(profile_data, dict):
            continue
        active = str(profile_data.get("active_subtitle_preset", "")).strip()
        if not active or active not in subtitle_presets:
            profile_data["active_subtitle_preset"] = DEFAULT_SUBTITLE_PRESET_ID
            changed = True
    data["profiles"] = profiles
    return changed


def save_presets(root: Path, data: dict[str, Any]) -> None:
    path = presets_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def load_or_init_presets(root: Path) -> dict[str, Any]:
    path = presets_path(root)
    if not path.exists():
        data = default_presets()
        save_presets(root, data)
        return data
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    presets = data.get("presets", {}) if isinstance(data, dict) else {}
    profiles = data.get("profiles", {}) if isinstance(data, dict) else {}
    if not isinstance(presets, dict):
        presets = {}
    if not isinstance(profiles, dict):
        profiles = {}
    data["presets"] = presets
    data["profiles"] = profiles
    changed = normalize_subtitle_presets(data)

    preset_ids = list(presets.keys())
    if preset_ids:
        fallback_preset = preset_ids[0]
        for profile_name, profile_data in profiles.items():
            if not isinstance(profile_data, dict):
                continue
            active = str(profile_data.get("active_preset", "")).strip()
            if active and active in presets:
                continue
            preferred = next((pid for pid, pdata in presets.items() if isinstance(pdata, dict) and str(pdata.get("profile", "")).strip() == str(profile_name)), fallback_preset)
            profile_data["active_preset"] = preferred
            changed = True
    if changed:
        data["profiles"] = profiles
        save_presets(root, data)
    return data
