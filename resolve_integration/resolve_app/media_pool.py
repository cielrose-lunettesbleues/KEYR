from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

SafeCall = Callable[..., Any]


def walk_folder_clips(folder: Any, safe_call: SafeCall) -> list[Any]:
    out = []
    try:
        clips = safe_call(folder, "GetClipList", default=[])
        out.extend(clips or [])
    except Exception:
        pass
    for sub in safe_call(folder, "GetSubFolderList", default=[]) or []:
        out.extend(walk_folder_clips(sub, safe_call))
    return out


def list_subtitle_template_candidates(
    media_pool: Any,
    safe_call: SafeCall,
    forced_names: tuple[str, ...],
) -> list[str]:
    root = safe_call(media_pool, "GetRootFolder")
    if root is None:
        return []
    names: set[str] = set()
    for clip in walk_folder_clips(root, safe_call):
        name = str(safe_call(clip, "GetName", default="") or "").strip()
        if not name:
            continue
        props = safe_call(clip, "GetClipProperty", default={}) or {}
        ctype = str(props.get("Type") or props.get("Clip Type") or "").strip().lower()
        lowered = name.lower()
        if (
            "text+" in lowered
            or "caption" in lowered
            or "subtitle" in lowered
            or "fusion title" in ctype
            or "generator" in ctype
            or "title" in ctype
        ):
            names.add(name)
    out = sorted(names)
    for forced in forced_names:
        if forced not in out:
            out.insert(0, forced)
    return out


def find_media_pool_item_by_path(media_pool: Any, source_path: Path, safe_call: SafeCall) -> Any | None:
    root = safe_call(media_pool, "GetRootFolder")
    if root is None:
        return None
    source_abs = str(source_path.resolve()).lower()
    for clip in walk_folder_clips(root, safe_call):
        try:
            props = clip.GetClipProperty() or {}
            fp = str(props.get("File Path") or "").lower()
            if fp == source_abs:
                return clip
        except Exception:
            continue
    return None


def path_from_clip_properties(props: Any) -> str:
    if not isinstance(props, dict):
        return ""
    for key in ("File Path", "Clip File Path", "Source Path", "Media Path", "Path", "Filename", "File Name"):
        raw = str(props.get(key) or "").strip()
        if not raw:
            continue
        candidate = Path(raw)
        if candidate.exists():
            return str(candidate)
    return ""


def source_path_from_resolve_clip(obj: Any, safe_call: SafeCall) -> str:
    if not obj:
        return ""

    media_item = safe_call(obj, "GetMediaPoolItem")
    if media_item:
        path = path_from_clip_properties(safe_call(media_item, "GetClipProperty", default={}) or {})
        if path:
            return path

    path = path_from_clip_properties(safe_call(obj, "GetClipProperty", default={}) or {})
    if path:
        return path

    return path_from_clip_properties(safe_call(obj, "GetProperty", default={}) or {})


def ensure_media_item(media_pool: Any, source_path: Path, safe_call: SafeCall) -> Any | None:
    item = find_media_pool_item_by_path(media_pool, source_path, safe_call)
    if item is not None:
        return item
    imported = safe_call(media_pool, "ImportMedia", [str(source_path)], default=[])
    if imported and len(imported) > 0:
        return imported[0]
    return None


def ensure_media_item_with_status(media_pool: Any, source_path: Path, safe_call: SafeCall) -> tuple[Any | None, str]:
    existing = find_media_pool_item_by_path(media_pool, source_path, safe_call)
    if existing is not None:
        return existing, "already_exists"
    imported = safe_call(media_pool, "ImportMedia", [str(source_path)], default=[])
    if imported and len(imported) > 0:
        return imported[0], "imported"
    return None, "failed"


def append_clip_range(
    media_pool: Any,
    timeline: Any,
    media_item: Any,
    start_frame: int,
    end_frame: int,
    track_index: int,
    record_frame: int,
    safe_call: SafeCall,
    *,
    media_type: int | None = None,
) -> bool:
    safe_call(media_pool, "SetCurrentTimeline", timeline)
    entry: dict[str, Any] = {
        "mediaPoolItem": media_item,
        "startFrame": start_frame,
        "endFrame": end_frame,
        "trackIndex": track_index,
        "recordFrame": record_frame,
    }
    if media_type is not None:
        entry["mediaType"] = media_type
    result = safe_call(media_pool, "AppendToTimeline", [entry])
    return bool(result)


def ensure_shorteditor_subfolder(media_pool: Any, subfolder_name: str, safe_call: SafeCall) -> Any:
    root = safe_call(media_pool, "GetRootFolder", required=True)
    for folder in safe_call(root, "GetSubFolderList", default=[]) or []:
        if safe_call(folder, "GetName", default="") == "ShortEditor":
            short_editor = folder
            break
    else:
        short_editor = safe_call(media_pool, "AddSubFolder", root, "ShortEditor", required=True)

    for folder in safe_call(short_editor, "GetSubFolderList", default=[]) or []:
        if safe_call(folder, "GetName", default="") == subfolder_name:
            out_folder = folder
            break
    else:
        out_folder = safe_call(media_pool, "AddSubFolder", short_editor, subfolder_name, required=True)

    safe_call(media_pool, "SetCurrentFolder", out_folder)
    return out_folder


def ensure_batch_folder(media_pool: Any, batch_id: str, safe_call: SafeCall) -> Any:
    return ensure_shorteditor_subfolder(media_pool, batch_id, safe_call)
