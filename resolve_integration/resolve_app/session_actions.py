from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


ProgressCallback = Callable[..., None]


@dataclass
class SessionActionDeps:
    read_manifest_safe: Callable[[Path], dict[str, Any] | None]
    default_subtitle_presets: Callable[[], dict[str, Any]]
    subtitle_style_from_preset: Callable[[dict[str, Any] | None], dict[str, Any]]
    merge_subtitle_preset_into_config: Callable[[dict[str, Any], dict[str, Any] | None], dict[str, Any]]
    load_pipeline_config: Callable[[Path], dict[str, Any]]
    manifest_has_valid_subtitles: Callable[[Path, dict[str, Any]], bool]
    apply_preview_safe_playback: Callable[[Any], list[str]]
    transcript_path_for_vod: Callable[[Path, Path], Path]
    find_reusable_quality_manifest: Callable[[Path, Path, str, bool, str], Path | None]
    generate_manifest_for_vod: Callable[..., Path]
    build_from_manifest: Callable[..., tuple[str, dict[str, Any], list[Any], list[str]]]
    log: Callable[[str], None]
    ensure_transcript: Callable[[Path, dict[str, Any], Path, Any], Path] | None = None


def _subtitle_offset_ms(params: dict[str, Any]) -> int:
    try:
        return int(float(str(params.get("subtitle_offset_ms", "-500") or "-500")))
    except Exception:
        return -500


def _selected_subtitle_preset(
    presets_data: dict[str, Any],
    subtitle_preset_id: str,
    default_subtitle_preset_id: str,
    deps: SessionActionDeps,
) -> tuple[str, dict[str, Any]]:
    preset = dict((presets_data.get("subtitle_presets", {}) or {}).get(subtitle_preset_id, {}))
    if preset:
        return subtitle_preset_id, preset
    defaults = deps.default_subtitle_presets()
    return default_subtitle_preset_id, dict(defaults[default_subtitle_preset_id])


def _ensure_transcript(
    source_path: Path,
    cfg: dict[str, Any],
    output_dir: Path,
    progress_cb: ProgressCallback | None,
    deps: SessionActionDeps,
) -> Path:
    if deps.ensure_transcript is not None:
        return deps.ensure_transcript(source_path, cfg, output_dir, progress_cb)
    from short_editor.transcription import ensure_transcript

    return ensure_transcript(source_path, cfg, output_dir, progress_cb=progress_cb)


def generate_session_batch(
    root: Path,
    project: Any,
    media_pool: Any,
    session: dict[str, Any],
    default_manifest: Path | None,
    presets_data: dict[str, Any],
    params: dict[str, Any],
    deps: SessionActionDeps,
    default_subtitle_preset_id: str,
    subtitle_template_auto_label: str,
) -> dict[str, Any] | str:
    manifest_value = session.get("manifest") or default_manifest
    if not manifest_value:
        return {"message": "Aucun manifest disponible. Relance le script pour en régénérer un.", "warnings": []}
    manifest_path = Path(manifest_value)
    manifest_data = deps.read_manifest_safe(manifest_path)
    output_dir = Path(params["output"])
    preset_name = str(params["render_preset"])
    render_master = bool(params["render_master"])
    preset_id = str(params["preset_id"])
    subtitle_preset_id = str(params.get("subtitle_preset_id", default_subtitle_preset_id) or default_subtitle_preset_id)
    transcript_query = str(params["query"])
    use_transcript_for_selection = bool(params.get("use_transcript_for_selection", False))
    strict_manifest = bool(params.get("strict_manifest", False))
    require_subtitles = bool(params.get("require_subtitles", False))
    preview_safe_quality = bool(params.get("preview_safe_quality", True))
    subtitle_template_name = str(params.get("subtitle_template_name", subtitle_template_auto_label) or subtitle_template_auto_label)
    subtitle_offset_ms = _subtitle_offset_ms(params)
    detected_vod = session.get("detected_vod")
    progress_cb = params.get("_progress_cb")

    selected_preset = dict((presets_data.get("presets", {}) or {}).get(preset_id, {}))
    if not selected_preset:
        return {"message": f"Preset introuvable: {preset_id}", "warnings": []}
    subtitle_preset_id, selected_subtitle_preset = _selected_subtitle_preset(
        presets_data,
        subtitle_preset_id,
        default_subtitle_preset_id,
        deps,
    )
    subtitle_style = deps.subtitle_style_from_preset(selected_subtitle_preset)
    subtitle_captions_cfg = deps.merge_subtitle_preset_into_config(deps.load_pipeline_config(root), selected_subtitle_preset).get("captions", {})

    if strict_manifest and bool(session.get("used_manifest_fallback", False)):
        fallback_msg = "Sous-titres auto annulés: la génération du manifest a échoué au démarrage et un manifest de secours est utilisé. Relance le script pour régénérer un manifest frais."
        deps.log(f"UI generate blocked (strict manifest): {fallback_msg}")
        return {"message": fallback_msg, "warnings": [fallback_msg]}

    preview_warnings: list[str] = []
    if require_subtitles:
        current_meta = manifest_data.get("meta", {}) if isinstance(manifest_data, dict) and isinstance(manifest_data.get("meta", {}), dict) else {}
        current_subtitle_preset_matches = str(current_meta.get("subtitle_preset_id", "")).strip() == subtitle_preset_id
        current_has_valid_subtitles = bool(manifest_data and current_subtitle_preset_matches and deps.manifest_has_valid_subtitles(root, manifest_data))
        if detected_vod is None or not Path(detected_vod).exists():
            return {"message": "Les sous-titres auto nécessitent une source VOD détectée. Sélectionne un clip dans Resolve puis relance.", "warnings": []}
        if preview_safe_quality:
            if callable(progress_cb):
                progress_cb("Batch+sous-titres", 1, 100, "Application du mode aperçu fluide")
            preview_warnings = deps.apply_preview_safe_playback(project)
        detected_vod_path = Path(detected_vod)
        reusable_manifest: Path | None = None
        transcript_path = deps.transcript_path_for_vod(root, detected_vod_path)
        transcript_ok = transcript_path.exists()
        if callable(progress_cb):
            progress_cb("Batch+sous-titres", 3 if transcript_ok else 1, 100, "Vérification du cache transcript")
        if not transcript_ok:
            try:
                deps.log(f"quality_transcript_generation_start vod={detected_vod_path} path={transcript_path}")
                generated_transcript = _ensure_transcript(detected_vod_path, deps.load_pipeline_config(root), root / "output" / "transcripts", progress_cb, deps)
                transcript_path = generated_transcript
                transcript_ok = transcript_path.exists()
                if callable(progress_cb):
                    progress_cb("Batch+sous-titres", 10, 100, "Transcript prêt pour génération Quality")
                deps.log(f"quality_transcript_generated path={transcript_path}")
            except Exception as exc:
                deps.log(f"quality_transcript_generation_failed err={exc}")
        else:
            deps.log(f"quality_transcript_cache_hit path={transcript_path}")

        if transcript_ok and not current_has_valid_subtitles:
            reusable_manifest = deps.find_reusable_quality_manifest(
                root,
                detected_vod_path,
                preset_id,
                use_transcript_for_selection,
                subtitle_preset_id,
            )
            if reusable_manifest is not None:
                manifest_path = reusable_manifest
                session["manifest"] = manifest_path
                session["used_manifest_fallback"] = False
                session["use_transcript_for_selection"] = use_transcript_for_selection
                deps.log(f"quality_manifest_cache_hit manifest={manifest_path}")
                if callable(progress_cb):
                    progress_cb("Batch+sous-titres", 15, 100, "Manifest + sous-titres du cache réutilisés")
            else:
                deps.log("quality_manifest_cache_miss")
        elif current_has_valid_subtitles:
            deps.log(f"quality_manifest_current_has_valid_subtitles manifest={manifest_path}")
        try:
            if reusable_manifest is None and not current_has_valid_subtitles:
                manifest_path = deps.generate_manifest_for_vod(
                    root,
                    detected_vod_path,
                    generate_subtitles=True,
                    use_transcript_for_selection=use_transcript_for_selection,
                    progress_cb=progress_cb,
                    preset_id=preset_id,
                    subtitle_preset_id=subtitle_preset_id,
                    subtitle_preset=selected_subtitle_preset,
                )
                session["manifest"] = manifest_path
                session["used_manifest_fallback"] = False
                session["use_transcript_for_selection"] = use_transcript_for_selection
                deps.log(f"Regenerated manifest with subtitles: {manifest_path}")
        except Exception as exc:
            msg = f"Échec de génération du manifest avec sous-titres auto: {exc}"
            deps.log(msg)
            return {"message": msg, "warnings": [msg]}
    elif use_transcript_for_selection:
        if detected_vod is None or not Path(detected_vod).exists():
            return {"message": "La sélection par transcript nécessite une source VOD détectée. Sélectionne un clip dans Resolve puis relance.", "warnings": []}
        try:
            manifest_path = deps.generate_manifest_for_vod(
                root,
                Path(detected_vod),
                generate_subtitles=False,
                use_transcript_for_selection=True,
                progress_cb=progress_cb,
                preset_id=preset_id,
            )
            session["manifest"] = manifest_path
            session["used_manifest_fallback"] = False
            session["use_transcript_for_selection"] = True
            deps.log(f"Regenerated manifest with transcript selection: {manifest_path}")
        except Exception as exc:
            msg = f"Échec de génération du manifest avec sélection transcript: {exc}"
            deps.log(msg)
            return {"message": msg, "warnings": [msg]}

    batch_id, plan_map, timelines, warnings = deps.build_from_manifest(
        root,
        project,
        media_pool,
        manifest_path,
        output_dir,
        preset_name,
        selected_preset,
        transcript_query,
        render_master,
        queue_render=True,
        detected_vod_path=detected_vod,
        user_vod_dir=None,
        require_subtitles=require_subtitles,
        subtitle_template_name=subtitle_template_name,
        subtitle_offset_ms=subtitle_offset_ms,
        subtitle_style=subtitle_style,
        subtitle_captions_cfg=subtitle_captions_cfg,
        progress_cb=progress_cb,
    )

    if require_subtitles and preview_safe_quality:
        warnings.extend(preview_warnings)
    session["batch_id"] = batch_id
    session["manifest"] = manifest_path
    session["plan_map"] = plan_map
    msg = f"{len(timelines)} timeline(s) générée(s)"
    if bool(session.get("used_manifest_fallback", False)):
        warnings.append(f"Manifest de secours utilisé: {manifest_path}")
    if warnings:
        msg += f" ({len(warnings)} avertissements)"
    deps.log(f"UI generate: {msg}")
    return {"message": msg, "warnings": warnings}


def update_session_composition(
    root: Path,
    project: Any,
    media_pool: Any,
    session: dict[str, Any],
    default_manifest: Path | None,
    presets_data: dict[str, Any],
    params: dict[str, Any],
    deps: SessionActionDeps,
    default_subtitle_preset_id: str,
    subtitle_template_auto_label: str,
) -> dict[str, Any] | str:
    if not session.get("batch_id"):
        return {"message": "Génère d'abord le batch.", "warnings": []}
    manifest_value = session.get("manifest") or default_manifest
    if not manifest_value:
        return {"message": "Aucun manifest disponible. Relance le script pour en régénérer un.", "warnings": []}
    manifest_path = Path(manifest_value)
    output_dir = Path(params["output"])
    preset_name = str(params["render_preset"])
    preset_id = str(params["preset_id"])
    subtitle_preset_id = str(params.get("subtitle_preset_id", default_subtitle_preset_id) or default_subtitle_preset_id)
    transcript_query = str(params["query"])
    use_transcript_for_selection = bool(params.get("use_transcript_for_selection", False))
    subtitle_template_name = str(params.get("subtitle_template_name", subtitle_template_auto_label) or subtitle_template_auto_label)
    subtitle_offset_ms = _subtitle_offset_ms(params)
    detected_vod = session.get("detected_vod")
    progress_cb = params.get("_progress_cb")
    selected_preset = dict((presets_data.get("presets", {}) or {}).get(preset_id, {}))
    if not selected_preset:
        return {"message": f"Preset introuvable: {preset_id}", "warnings": []}
    _, selected_subtitle_preset = _selected_subtitle_preset(presets_data, subtitle_preset_id, default_subtitle_preset_id, deps)
    subtitle_style = deps.subtitle_style_from_preset(selected_subtitle_preset)
    subtitle_captions_cfg = deps.merge_subtitle_preset_into_config(deps.load_pipeline_config(root), selected_subtitle_preset).get("captions", {})

    if use_transcript_for_selection:
        if detected_vod is None or not Path(detected_vod).exists():
            return {"message": "La sélection par transcript nécessite une source VOD détectée. Sélectionne un clip dans Resolve puis relance.", "warnings": []}
        try:
            manifest_path = deps.generate_manifest_for_vod(
                root,
                Path(detected_vod),
                generate_subtitles=False,
                use_transcript_for_selection=True,
                progress_cb=progress_cb,
                preset_id=preset_id,
                subtitle_preset_id=subtitle_preset_id,
                subtitle_preset=selected_subtitle_preset,
            )
            session["manifest"] = manifest_path
            session["used_manifest_fallback"] = False
            session["use_transcript_for_selection"] = True
            deps.log(f"Regenerated manifest for update with transcript selection: {manifest_path}")
        except Exception as exc:
            msg = f"Échec de génération du manifest avec sélection transcript: {exc}"
            deps.log(msg)
            return {"message": msg, "warnings": [msg]}

    batch_id, plan_map, timelines, warnings = deps.build_from_manifest(
        root,
        project,
        media_pool,
        manifest_path,
        output_dir,
        preset_name,
        selected_preset,
        transcript_query,
        render_master=False,
        queue_render=False,
        detected_vod_path=detected_vod,
        user_vod_dir=None,
        require_subtitles=False,
        subtitle_template_name=subtitle_template_name,
        subtitle_offset_ms=subtitle_offset_ms,
        subtitle_style=subtitle_style,
        subtitle_captions_cfg=subtitle_captions_cfg,
        progress_cb=progress_cb,
    )
    session["batch_id"] = batch_id
    session["manifest"] = manifest_path
    session["plan_map"] = plan_map
    msg = f"Composition mise à jour sur {len(timelines)} timeline(s)"
    if bool(session.get("used_manifest_fallback", False)):
        warnings.append(f"Manifest de secours utilisé: {manifest_path}")
    if warnings:
        msg += f" ({len(warnings)} avertissements)"
    deps.log(f"UI update: {msg}")
    return {"message": msg, "warnings": warnings}
