from __future__ import annotations

from typing import Any, Callable

from resolve_integration.resolve_app import timelines

SafeCall = Callable[..., Any]
Logger = Callable[[str], None]

TRANSFORM_KEY_MAP = {
    "zoom_x": "ZoomX",
    "zoom_y": "ZoomY",
    "pan": "Pan",
    "tilt": "Tilt",
    "crop_top": "CropTop",
    "crop_bottom": "CropBottom",
    "crop_left": "CropLeft",
    "crop_right": "CropRight",
}


def apply_item_transform(item: Any, props: dict[str, float], safe_call: SafeCall) -> None:
    for key, value in props.items():
        resolve_key = TRANSFORM_KEY_MAP.get(key)
        if not resolve_key:
            continue
        safe_call(item, "SetProperty", resolve_key, float(value))


def read_item_transform(item: Any, safe_call: SafeCall) -> dict[str, float]:
    props: dict[str, float] = {}
    for out_key, in_key in TRANSFORM_KEY_MAP.items():
        value = safe_call(item, "GetProperty", in_key, default=None)
        if value is None:
            all_props = safe_call(item, "GetProperty", default={}) or {}
            value = all_props.get(in_key)
        try:
            props[out_key] = float(value)
        except Exception:
            props[out_key] = 0.0
    return props


def apply_preset_to_selected_clip(resolve: Any, preset: dict[str, Any], scope_mode: str, safe_call: SafeCall, log: Logger) -> tuple[bool, str]:
    project_manager = safe_call(resolve, "GetProjectManager")
    project = safe_call(project_manager, "GetCurrentProject") if project_manager else None
    if not project:
        return False, "Aucun projet ouvert"
    timeline = safe_call(project, "GetCurrentTimeline")
    if not timeline:
        return False, "Aucune timeline active"

    mode = str(preset.get("mode", "single"))
    use_range = scope_mode == "selected_range"
    use_whole_timeline = scope_mode == "whole_timeline"
    range_frames = timelines.get_timeline_selected_range(timeline, safe_call) if use_range else None
    if use_range and range_frames is None:
        return False, "Aucune plage In/Out sélectionnée sur la timeline"

    if mode == "fixed_split":
        if use_whole_timeline:
            cam_items = timelines.get_timeline_items_on_track(timeline, 1, safe_call)
            game_items = timelines.get_timeline_items_on_track(timeline, 2, safe_call)
            if not cam_items or not game_items:
                return False, "Toute la timeline: il faut des clips sur piste 1 (caméra) et piste 2 (gameplay)"
            log(f"Apply whole timeline mapping: camera->T1 items={len(cam_items)}, gameplay->T2 items={len(game_items)}")
            for item in cam_items:
                apply_item_transform(item, dict(preset.get("camera", {})), safe_call)
            for item in game_items:
                apply_item_transform(item, dict(preset.get("gameplay", {})), safe_call)
            return True, f"Preset appliqué à toute la timeline (caméra T1: {len(cam_items)}, gameplay T2: {len(game_items)})"

        if use_range and range_frames is not None:
            start_f, end_f = range_frames
            cam_items = timelines.items_overlapping_frame_range(timeline, 1, start_f, end_f, safe_call)
            game_items = timelines.items_overlapping_frame_range(timeline, 2, start_f, end_f, safe_call)
            if not cam_items or not game_items:
                return False, "Il faut des clips sur piste 1 et piste 2 dans la plage sélectionnée"
            log(f"Apply selected range mapping: camera->T1 items={len(cam_items)}, gameplay->T2 items={len(game_items)}")
            for item in cam_items:
                apply_item_transform(item, dict(preset.get("camera", {})), safe_call)
            for item in game_items:
                apply_item_transform(item, dict(preset.get("gameplay", {})), safe_call)
            return True, f"Preset appliqué à la plage (caméra T1: {len(cam_items)}, gameplay T2: {len(game_items)})"

        cam_item = timelines.get_item_at_current_frame(timeline, 1, safe_call)
        game_item = timelines.get_item_at_current_frame(timeline, 2, safe_call)
        if not cam_item or not game_item:
            return False, "Il faut piste 1 (caméra) et piste 2 (gameplay) au curseur de lecture"
        log("Apply selected clip mapping: camera->T1 gameplay->T2")
        apply_item_transform(cam_item, dict(preset.get("camera", {})), safe_call)
        apply_item_transform(game_item, dict(preset.get("gameplay", {})), safe_call)
        return True, "Preset appliqué au clip sélectionné (piste 1=caméra, piste 2=gameplay)"

    if use_whole_timeline:
        try:
            track_count = int(safe_call(timeline, "GetTrackCount", "video", default=0) or 0)
        except Exception:
            track_count = 0
        items: list[Any] = []
        for track_idx in range(1, track_count + 1):
            items.extend(timelines.get_timeline_items_on_track(timeline, track_idx, safe_call))
        if not items:
            return False, "Aucun clip vidéo trouvé sur la timeline"
        for item in items:
            apply_item_transform(item, dict(preset.get("single", {})), safe_call)
        return True, f"Preset appliqué à {len(items)} clip(s) sur toute la timeline"

    if use_range and range_frames is not None:
        start_f, end_f = range_frames
        items = timelines.items_overlapping_frame_range(timeline, 1, start_f, end_f, safe_call)
        if not items:
            return False, "Aucun clip trouvé sur la piste 1 dans la plage sélectionnée"
        for item in items:
            apply_item_transform(item, dict(preset.get("single", {})), safe_call)
        return True, f"Preset appliqué à {len(items)} clip(s) dans la plage sélectionnée"

    selected = safe_call(timeline, "GetCurrentVideoItem")
    if not selected:
        return False, "Aucun clip sélectionné/courant"
    apply_item_transform(selected, dict(preset.get("single", {})), safe_call)
    return True, "Preset appliqué au clip sélectionné"
