from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from resolve_integration.resolve_app.transforms import TRANSFORM_KEY_MAP


@dataclass
class TimelineActionDeps:
    safe_call: Callable[..., Any]
    log: Callable[[str], None]
    get_item_at_current_frame: Callable[[Any, int], Any | None]
    get_first_item_on_track: Callable[[Any, int], Any | None]
    apply_preset_to_selected_clip: Callable[[Any, dict[str, Any], str], tuple[bool, str]]


def apply_named_preset(
    resolve: Any,
    presets_data: dict[str, Any],
    preset_id: str,
    scope_mode: str,
    deps: TimelineActionDeps,
) -> tuple[bool, str]:
    pid = str(preset_id).strip()
    selected_preset = dict((presets_data.get("presets", {}) or {}).get(pid, {}))
    if not selected_preset:
        return False, f"Preset introuvable: {pid}"
    ok, msg = deps.apply_preset_to_selected_clip(resolve, selected_preset, scope_mode)
    if ok:
        deps.log(f"Apply preset success: preset={pid} scope={scope_mode}")
    else:
        deps.log(f"Apply preset failed: preset={pid} scope={scope_mode} msg={msg}")
    return ok, msg


def read_resolve_float_property(item: Any, prop: str, safe_call: Callable[..., Any]) -> float | None:
    value = safe_call(item, "GetProperty", prop, default=None)
    if value is None:
        all_props = safe_call(item, "GetProperty", default={}) or {}
        value = all_props.get(prop)
    try:
        return float(value)
    except Exception:
        return None


def detect_fixed_split_preset_from_timeline(
    resolve: Any,
    detect_mode: str,
    deps: TimelineActionDeps,
    keys: tuple[str, ...] = tuple(TRANSFORM_KEY_MAP.keys()),
) -> dict[str, Any]:
    project_manager = deps.safe_call(resolve, "GetProjectManager")
    project = deps.safe_call(project_manager, "GetCurrentProject") if project_manager else None
    if not project:
        return {"ok": False, "message": "Détection impossible: aucun projet ouvert"}
    timeline = deps.safe_call(project, "GetCurrentTimeline")
    if not timeline:
        return {"ok": False, "message": "Détection impossible: aucune timeline active"}

    mode = "current" if str(detect_mode).strip() == "current" else "first"
    if mode == "current":
        cam_item = deps.get_item_at_current_frame(timeline, 1)
        game_item = deps.get_item_at_current_frame(timeline, 2)
    else:
        cam_item = deps.get_first_item_on_track(timeline, 1)
        game_item = deps.get_first_item_on_track(timeline, 2)

    deps.log(f"Detect preset mode={mode} mapping camera->T1 gameplay->T2")

    if not cam_item:
        return {"ok": False, "message": "Détection impossible: aucun clip sur la piste 1"}
    if not game_item:
        return {"ok": False, "message": "Détection impossible: aucun clip sur la piste 2"}

    fields: dict[str, float] = {}
    for key in keys:
        resolve_key = TRANSFORM_KEY_MAP.get(key)
        if not resolve_key:
            continue
        cam_value = read_resolve_float_property(cam_item, resolve_key, deps.safe_call)
        game_value = read_resolve_float_property(game_item, resolve_key, deps.safe_call)
        if cam_value is not None:
            fields[f"camera.{key}"] = cam_value
        if game_value is not None:
            fields[f"gameplay.{key}"] = game_value

    return {
        "ok": True,
        "message": "Preset détecté depuis la timeline active (piste 1=caméra, piste 2=gameplay)",
        "mode": "fixed_split",
        "fields": fields,
    }
