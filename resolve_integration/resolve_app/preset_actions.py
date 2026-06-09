from __future__ import annotations

from typing import Any, Callable


BuildPreset = Callable[[dict[str, Any]], dict[str, Any]]


def default_preset_base(name: str, profile: str) -> dict[str, Any]:
    return {"name": name, "profile": profile, "mode": "single", "max_clip_seconds": 45}


def save_overwrite_preset_data(
    presets_data: dict[str, Any],
    preset_id: str,
    profile: str,
    build_preset: BuildPreset,
) -> dict[str, Any]:
    pid = str(preset_id).strip()
    if not pid:
        return {"status": "missing", "preset_id": ""}
    presets = presets_data.setdefault("presets", {})
    profiles = presets_data.setdefault("profiles", {})
    base = dict(presets.get(pid, {})) or default_preset_base(pid, profile)
    presets[pid] = build_preset(base)
    profiles.setdefault(profile, {})["active_preset"] = pid
    return {"status": "saved", "preset_id": pid}


def save_new_preset_data(
    presets_data: dict[str, Any],
    current_preset_id: str,
    new_preset_id: str,
    profile: str,
    build_preset: BuildPreset,
) -> dict[str, Any]:
    nid = str(new_preset_id).strip()
    if not nid:
        return {"status": "missing", "preset_id": ""}
    presets = presets_data.setdefault("presets", {})
    profiles = presets_data.setdefault("profiles", {})
    base = dict(presets.get(str(current_preset_id).strip(), {})) or default_preset_base(nid, profile)
    new_preset = build_preset(base)
    new_preset["name"] = nid
    presets[nid] = new_preset
    profiles.setdefault(profile, {})["active_preset"] = nid
    return {"status": "saved", "preset_id": nid}


def delete_preset_data(presets_data: dict[str, Any], preset_id: str) -> dict[str, Any]:
    pid = str(preset_id).strip()
    presets = presets_data.setdefault("presets", {})
    profiles = presets_data.setdefault("profiles", {})
    if not pid or pid not in presets:
        return {"status": "missing", "deleted": pid, "replacement": ""}
    if len(presets) <= 1:
        return {"status": "last", "deleted": pid, "replacement": ""}

    deleted_profile = str(presets.get(pid, {}).get("profile", "")).strip()
    del presets[pid]

    replacement = ""
    for candidate_id, candidate_data in presets.items():
        if str(candidate_data.get("profile", "")).strip() == deleted_profile:
            replacement = candidate_id
            break
    if not replacement:
        replacement = next(iter(presets.keys()))

    for profile_name, profile_data in profiles.items():
        if not isinstance(profile_data, dict):
            continue
        if profile_data.get("active_preset") == pid:
            profile_data["active_preset"] = replacement
        if profile_name == deleted_profile and not profile_data.get("active_preset"):
            profile_data["active_preset"] = replacement

    return {"status": "deleted", "deleted": pid, "replacement": replacement}
