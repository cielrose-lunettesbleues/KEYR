from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


ProgressCallback = Callable[[int, int, str], None]
ConfirmDelete = Callable[[int], bool]


@dataclass
class SilenceActionDeps:
    safe_call: Callable[..., Any]
    log: Callable[[str], None]
    load_pipeline_config: Callable[[Path], dict[str, Any]]
    selected_clip_subtitle_context: Callable[[Any], tuple[bool, str, dict[str, Any]]]
    load_audio_energy_for_silence_cut: Callable[[Path, Path, dict[str, Any], dict[str, tuple[list[tuple[float, float]], str]]], tuple[list[tuple[float, float]], str, list[str]]]
    detect_audible_segments_for_silence_cut: Callable[[list[tuple[float, float]], float, float, dict[str, Any]], tuple[list[tuple[float, float]], dict[str, float]]]
    create_silence_cut_timeline: Callable[[Path, Any, Any, Path, str, list[tuple[float, float]], dict[str, Any]], tuple[Any | None, list[str]]]
    parse_manifest: Callable[[Path], tuple[str, list[Any]]]
    suffix_timeline_name: Callable[[str], str]
    find_timeline_by_name: Callable[[Any, str], Any | None]


def run_silence_cut(
    root: Path,
    resolve: Any,
    selected_scope: str,
    preset_id: str,
    presets_data: dict[str, Any],
    session_ref: dict[str, Any],
    default_manifest: Path | None,
    deps: SilenceActionDeps,
    progress_cb: ProgressCallback,
) -> dict[str, Any]:
    cfg = deps.load_pipeline_config(root)
    energy_cache: dict[str, tuple[list[tuple[float, float]], str]] = {}
    warnings_out: list[str] = []
    total_cuts = 0
    total_removed = 0.0
    timelines_created = 0

    pm = deps.safe_call(resolve, "GetProjectManager")
    project = deps.safe_call(pm, "GetCurrentProject") if pm else None
    if not project:
        return {"ok": False, "message": "Aucun projet Resolve ouvert.", "warnings": []}
    media_pool = deps.safe_call(project, "GetMediaPool")
    if not media_pool:
        return {"ok": False, "message": "Media Pool indisponible.", "warnings": []}
    selected_preset = dict((presets_data.get("presets", {}) or {}).get(preset_id, {}))
    if not selected_preset:
        return {"ok": False, "message": f"Preset introuvable: {preset_id}", "warnings": []}

    def process_one(source_path: Path, start_s: float, end_s: float, base_name: str, idx: int, total: int) -> None:
        nonlocal total_cuts, total_removed, timelines_created
        progress_cb(idx, total, f"Analyse audio: {base_name}")
        energies, audio_label, audio_warnings = deps.load_audio_energy_for_silence_cut(root, source_path, cfg, energy_cache)
        warnings_out.extend(audio_warnings)
        if not energies:
            warnings_out.append(f"{base_name}: analyse audio vide, clip inchangé.")
            return
        segments, stats = deps.detect_audible_segments_for_silence_cut(energies, start_s, end_s, cfg)
        cuts = int(stats.get("cuts", 0.0))
        removed = float(stats.get("removed_seconds", 0.0))
        if cuts <= 0 or removed <= 0.05:
            warnings_out.append(f"{base_name}: aucun silence gênant détecté ({audio_label}).")
            return
        timeline_name = deps.suffix_timeline_name(base_name)
        progress_cb(idx, total, f"Création timeline: {timeline_name}")
        timeline, create_warnings = deps.create_silence_cut_timeline(root, project, media_pool, source_path, timeline_name, segments, selected_preset)
        warnings_out.extend(create_warnings)
        if timeline is None:
            warnings_out.append(f"{base_name}: création timeline silence_cut échouée.")
            return
        timelines_created += 1
        total_cuts += cuts
        total_removed += removed
        deps.log(f"silence_cut_created name={timeline_name} cuts={cuts} removed={removed:.3f}s segments={len(segments)} audio={audio_label}")

    if selected_scope == "Clip sélectionné":
        ok_ctx, ctx_msg, ctx = deps.selected_clip_subtitle_context(resolve)
        if not ok_ctx:
            return {"ok": False, "message": ctx_msg, "warnings": []}
        source_path = Path(str(ctx.get("source_path", "")))
        if not source_path.exists():
            return {"ok": False, "message": f"Source introuvable: {source_path}", "warnings": []}
        item_name = str(ctx.get("item_name") or ctx.get("timeline_name") or source_path.stem)
        process_one(source_path, float(ctx["clip_start"]), float(ctx["clip_end"]), item_name, 1, 1)
    else:
        manifest_value = session_ref.get("manifest") or default_manifest
        if not manifest_value:
            return {"ok": False, "message": "Aucun manifest disponible. Génère d'abord un batch.", "warnings": []}
        manifest_path = Path(manifest_value)
        if not manifest_path.exists():
            return {"ok": False, "message": f"Manifest introuvable: {manifest_path}", "warnings": []}
        batch_id, plans = deps.parse_manifest(manifest_path)
        if not plans:
            return {"ok": False, "message": "Aucun clip valide dans le manifest.", "warnings": []}
        detected_vod = session_ref.get("detected_vod")
        for idx, plan in enumerate(plans, start=1):
            raw_src = Path(plan.source_path)
            source_path = raw_src if raw_src.is_absolute() else (root / raw_src).resolve()
            if not source_path.exists() and detected_vod is not None and Path(detected_vod).exists():
                source_path = Path(detected_vod)
            if not source_path.exists():
                warnings_out.append(f"{plan.display_name}: source introuvable, skip.")
                continue
            base_name = plan.timeline_name or f"{batch_id}__{plan.display_name or plan.clip_id}"
            process_one(source_path, float(plan.start_seconds), float(plan.end_seconds), base_name, idx, len(plans))

    if timelines_created == 0:
        return {"ok": False, "message": "Aucune timeline silence_cut créée.", "warnings": warnings_out}
    warnings_out.append("Sous-titres: régénère-les après coupe si la timeline originale en avait.")
    return {
        "ok": True,
        "message": f"Coupe des silences terminée: {timelines_created} timeline(s), {total_cuts} cut(s), {total_removed:.1f}s supprimée(s).",
        "warnings": warnings_out,
    }


def undo_silence_cuts(
    resolve: Any,
    selected_scope: str,
    session_ref: dict[str, Any],
    default_manifest: Path | None,
    deps: SilenceActionDeps,
    confirm_delete: ConfirmDelete,
) -> dict[str, Any]:
    pm = deps.safe_call(resolve, "GetProjectManager")
    project = deps.safe_call(pm, "GetCurrentProject") if pm else None
    if not project:
        return {"ok": False, "message": "Aucun projet Resolve ouvert.", "warnings": []}
    media_pool = deps.safe_call(project, "GetMediaPool")
    if not media_pool:
        return {"ok": False, "message": "Media Pool indisponible.", "warnings": []}

    warnings_out: list[str] = []
    originals: list[str] = []
    targets: list[str] = []

    def add_target(name: str, original: str = "") -> None:
        clean_name = str(name or "").strip()
        if not clean_name or clean_name in targets:
            return
        targets.append(clean_name)
        if original and original not in originals:
            originals.append(original)

    if selected_scope == "Clip sélectionné":
        current_timeline = deps.safe_call(project, "GetCurrentTimeline")
        current_name = str(deps.safe_call(current_timeline, "GetName", default="") or "") if current_timeline else ""
        if current_name.endswith("__silence_cut"):
            add_target(current_name, current_name[: -len("__silence_cut")])

        ok_ctx, ctx_msg, ctx = deps.selected_clip_subtitle_context(resolve)
        if ok_ctx:
            base_name = str(ctx.get("item_name") or ctx.get("timeline_name") or "").strip()
            if base_name:
                add_target(deps.suffix_timeline_name(base_name), base_name)
        elif not targets:
            return {"ok": False, "message": ctx_msg, "warnings": []}
    else:
        manifest_value = session_ref.get("manifest") or default_manifest
        if not manifest_value:
            return {"ok": False, "message": "Aucun manifest disponible. Génère d'abord un batch.", "warnings": []}
        manifest_path = Path(manifest_value)
        if not manifest_path.exists():
            return {"ok": False, "message": f"Manifest introuvable: {manifest_path}", "warnings": []}
        batch_id, plans = deps.parse_manifest(manifest_path)
        if not plans:
            return {"ok": False, "message": "Aucun clip valide dans le manifest.", "warnings": []}
        for plan in plans:
            base_name = plan.timeline_name or f"{batch_id}__{plan.display_name or plan.clip_id}"
            add_target(deps.suffix_timeline_name(base_name), base_name)

    existing_targets: list[tuple[str, Any]] = []
    for timeline_name in targets:
        timeline = deps.find_timeline_by_name(project, timeline_name)
        if timeline:
            existing_targets.append((timeline_name, timeline))
        else:
            warnings_out.append(f"Timeline silence_cut introuvable: {timeline_name}")

    if not existing_targets:
        return {"ok": False, "message": "Aucune timeline silence_cut à supprimer.", "warnings": warnings_out}
    if not confirm_delete(len(existing_targets)):
        return {"ok": False, "message": "Annulation des cuts de silences annulée.", "warnings": []}

    deleted = 0
    for timeline_name, timeline in existing_targets:
        ok = deps.safe_call(media_pool, "DeleteTimelines", [timeline], default=False)
        if not ok:
            ok = deps.safe_call(project, "DeleteTimeline", timeline, default=False)
        if ok:
            deleted += 1
            deps.log(f"silence_cut_deleted name={timeline_name}")
        else:
            warnings_out.append(f"Suppression impossible: {timeline_name}")

    for original_name in originals:
        original_timeline = deps.find_timeline_by_name(project, original_name)
        if original_timeline:
            deps.safe_call(project, "SetCurrentTimeline", original_timeline)
            deps.safe_call(media_pool, "SetCurrentTimeline", original_timeline)
            break

    if deleted <= 0:
        return {"ok": False, "message": "Aucune timeline silence_cut supprimée.", "warnings": warnings_out}
    return {"ok": True, "message": f"Cuts annulés: {deleted} timeline(s) silence_cut supprimée(s).", "warnings": warnings_out}
