from __future__ import annotations

import json
import io
import re
import sys
import os
import uuid
import time
import threading
import traceback
import warnings
import subprocess
from contextlib import redirect_stderr
from pathlib import Path
from typing import Any


def _bootstrap_project_root_for_imports() -> None:
    candidates: list[Path] = []
    raw_file = globals().get("__file__")
    if raw_file:
        candidates.append(Path(str(raw_file)).resolve().with_name("short_editor_resolve_config.json"))
    appdata = os.environ.get("APPDATA", "")
    if appdata:
        candidates.append(Path(appdata) / "Blackmagic Design" / "DaVinci Resolve" / "Support" / "Fusion" / "Scripts" / "Utility" / "short_editor_resolve_config.json")
    for cfg_path in candidates:
        try:
            if not cfg_path.exists():
                continue
            with cfg_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            root = Path(str(data.get("project_root", ""))).resolve()
            if root.exists() and str(root) not in sys.path:
                sys.path.insert(0, str(root))
                return
        except Exception:
            continue


_bootstrap_project_root_for_imports()

from resolve_integration.resolve_app.api import load_resolve as _load_resolve_impl, safe_call as _safe_call
from resolve_integration.resolve_app.batch_builder import BatchBuildDeps as _BatchBuildDeps
from resolve_integration.resolve_app import batch_builder as _batch_builder
from resolve_integration.resolve_app import clip_subtitles as _clip_subtitles
from resolve_integration.resolve_app.logging import log as _log, log_path as _log_path
from resolve_integration.resolve_app.paths import (
    load_installed_config_root as _load_installed_config_root,
    repo_root as _repo_root,
    script_config_path as _script_config_path,
    script_path as _script_path,
)
from resolve_integration.resolve_app import preset_actions as _preset_actions
from resolve_integration.resolve_app import presets as _presets
from resolve_integration.resolve_app import manifests as _manifests
from resolve_integration.resolve_app import media_pool as _media_pool
from resolve_integration.resolve_app import project_settings as _project_settings
from resolve_integration.resolve_app import render_queue as _render_queue
from resolve_integration.resolve_app import selected_clip as _selected_clip
from resolve_integration.resolve_app import session_actions as _session_actions
from resolve_integration.resolve_app import silence_actions as _silence_actions
from resolve_integration.resolve_app import silence_cut as _silence_cut
from resolve_integration.resolve_app import textplus as _textplus
from resolve_integration.resolve_app import timeline_actions as _timeline_actions
from resolve_integration.resolve_app import timelines as _timelines
from resolve_integration.resolve_app import transforms as _transforms
from resolve_integration.resolve_app import ui_feedback as _ui_feedback
from resolve_integration.resolve_app import ui_keywords as _ui_keywords
from resolve_integration.resolve_app import ui_main as _ui_main
from resolve_integration.resolve_app import ui_presets as _ui_presets
from resolve_integration.resolve_app import ui_progress as _ui_progress
from resolve_integration.resolve_app import ui_status as _ui_status
from resolve_integration.resolve_app.ui_loader import KirbyLoader as _KirbyLoader, load_gif_frames as _load_gif_frames_impl
from resolve_integration.resolve_app.plans import (
    ClipPlan,
    parse_manifest as _parse_manifest_impl,
    plan_key as _plan_key_impl,
    safe_name_token as _safe_name_token_impl,
    suffix_timeline_name as _suffix_timeline_name_impl,
)
from short_editor.selection import overlap_ratio_from_ranges, ranges_too_close, select_non_overlapping_dicts
from short_editor.manifest_builder import generate_manifest_for_vod as _build_manifest_for_vod


DEFAULT_FPS = 60
STANDALONE_CAPTION_TEMPLATE_NAME = "ShortEditor Caption"
STANDALONE_CAPTION_TEMPLATE_FALLBACK_NAME = "AutoSubs Caption"
SUBTITLE_TEMPLATE_AUTO_LABEL = "Auto-detect (Recommended)"
DEFAULT_SUBTITLE_PRESET_ID = "Minimal clean"

def _load_resolve() -> Any:
    return _load_resolve_impl(globals().get("bmd"))


def _presets_path(root: Path) -> Path:
    return _presets.presets_path(root)


def _default_presets() -> dict[str, Any]:
    return _presets.default_presets()


def _default_subtitle_presets() -> dict[str, Any]:
    return _presets.default_subtitle_presets()


def _normalize_subtitle_presets(data: dict[str, Any]) -> bool:
    return _presets.normalize_subtitle_presets(data)


def _coerce_float(value: Any, default: float, min_value: float | None = None, max_value: float | None = None) -> float:
    return _presets.coerce_float(value, default, min_value, max_value)


def _coerce_int(value: Any, default: int, min_value: int | None = None, max_value: int | None = None) -> int:
    return _presets.coerce_int(value, default, min_value, max_value)


def _subtitle_preset_captions_overrides(preset: dict[str, Any]) -> dict[str, Any]:
    return _presets.subtitle_preset_captions_overrides(preset)


def _merge_subtitle_preset_into_config(cfg: dict[str, Any], subtitle_preset: dict[str, Any] | None) -> dict[str, Any]:
    return _presets.merge_subtitle_preset_into_config(cfg, subtitle_preset)


def _subtitle_style_from_preset(preset: dict[str, Any] | None) -> dict[str, Any]:
    return _presets.subtitle_style_from_preset(preset)


def _load_or_init_presets(root: Path) -> dict[str, Any]:
    return _presets.load_or_init_presets(root)


def _save_presets(root: Path, data: dict[str, Any]) -> None:
    _presets.save_presets(root, data)


def _assets_dir(root: Path) -> Path:
    return root / "resolve_integration" / "assets"


def _load_gif_frames(tk_mod: Any, gif_path: Path) -> list[Any]:
    return _load_gif_frames_impl(tk_mod, gif_path)


def _load_pipeline_config(root: Path) -> dict[str, Any]:
    path = root / "config" / "pipeline.json"
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _latest_manifest(default_dir: Path) -> Path | None:
    files = sorted(default_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def _paths_match_lenient(left: Any, right: Any) -> bool:
    return _manifests.paths_match_lenient(left, right)


def _manifest_matches_vod(data: dict[str, Any], vod_path: Path) -> bool:
    return _manifests.manifest_matches_vod(data, vod_path)


def _find_existing_manifest_for_vod(root: Path, vod_path: Path) -> Path | None:
    return _manifests.find_existing_manifest_for_vod(root, vod_path)


def _transcript_path_for_vod(root: Path, vod_path: Path) -> Path:
    return _manifests.transcript_path_for_vod(root, vod_path)


def _read_manifest_safe(path: Path) -> dict[str, Any] | None:
    return _manifests.read_manifest_safe(path)


def _manifest_has_valid_subtitles(root: Path, data: dict[str, Any]) -> bool:
    return _manifests.manifest_has_valid_textplus_source(root, data)


def _find_reusable_quality_manifest(root: Path, vod_path: Path, preset_id: str, use_transcript_for_selection: bool, subtitle_preset_id: str = "") -> Path | None:
    return _manifests.find_reusable_quality_manifest(root, vod_path, preset_id, use_transcript_for_selection, subtitle_preset_id)


def _ask_user_inputs(
    default_manifest: Path | None,
    presets_data: dict[str, Any],
    resolve: Any,
    on_generate: Any,
    on_update: Any,
    session_ref: dict[str, Any],
) -> None:
    preset_name = "H264_Shorts_1080x1920_60fps"

    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox

        profiles = presets_data.get("profiles", {})
        presets = presets_data.get("presets", {})
        subtitle_presets = presets_data.get("subtitle_presets", {})
        if not isinstance(subtitle_presets, dict):
            subtitle_presets = _default_subtitle_presets()
            presets_data["subtitle_presets"] = subtitle_presets
        pm_ui = _safe_call(resolve, "GetProjectManager")
        project_ui = _safe_call(pm_ui, "GetCurrentProject") if pm_ui else None
        media_pool_ui = _safe_call(project_ui, "GetMediaPool") if project_ui else None
        subtitle_template_options = [SUBTITLE_TEMPLATE_AUTO_LABEL]
        if media_pool_ui is not None:
            subtitle_template_options.extend(_list_subtitle_template_candidates(media_pool_ui))
        subtitle_template_options = list(dict.fromkeys([x for x in subtitle_template_options if str(x).strip()]))
        keys = _ui_main.TRANSFORM_KEYS
        colors = dict(_ui_main.COLORS)
        state = _ui_main.initial_state(
            _repo_root(),
            profiles,
            presets,
            subtitle_presets,
            preset_name,
            SUBTITLE_TEMPLATE_AUTO_LABEL,
            DEFAULT_SUBTITLE_PRESET_ID,
        )
        default_profile = str(state["profile"])
        default_preset_id = str(state["preset_id"])
        default_subtitle_preset_id = str(state["subtitle_preset_id"])

        root = tk.Tk()
        compact_geometry = _ui_main.COMPACT_GEOMETRY
        expanded_geometry = _ui_main.EXPANDED_GEOMETRY
        root.title("Short Editor // Console ange digital 2003")
        root.geometry(compact_geometry)
        root.configure(bg=colors["bg"])
        _log("UI window created OK")

        play_hover_sound = _ui_main.noop_sound
        play_click_sound = _ui_main.noop_sound
        play_notification_sound = _ui_main.noop_sound

        _ui_main.create_dream_background(tk, root, colors, _log, play_click_sound)

        def ui_button(parent: Any, text: str, cmd: Any, primary: bool = False) -> Any:
            return _ui_main.create_ui_button(tk, parent, text, cmd, colors, play_click_sound, play_hover_sound, primary)

        def make_label(text: str, r: int, c: int) -> None:
            _ui_main.create_form_label(tk, form, text, r, c, colors)

        main_ui = _ui_main.create_header_and_tabs(tk, root, colors)
        tabs_body = main_ui["tabs_body"]
        batch_tab = main_ui["batch_tab"]
        actions_tab = main_ui["actions_tab"]
        show_tab = main_ui["show_tab"]

        form = tk.LabelFrame(batch_tab, text="☁ Paramètres du batch ☁", bg=colors["panel_alt"], fg=colors["ink"], bd=4, relief="ridge", padx=10, pady=10, font=("Verdana", 10, "bold"))
        form.grid(row=0, column=0, columnspan=3, sticky="we", padx=0, pady=(0, 8))

        make_label("Dossier de sortie", 0, 0)
        output_var = tk.StringVar(value=state["output_dir"])
        _ui_main.create_text_entry(tk, form, output_var, 0, 1, colors)

        def browse_output() -> None:
            p = filedialog.askdirectory(title="Sélectionner le dossier de sortie", initialdir=output_var.get())
            if p:
                output_var.set(p)

        ui_button(form, "Parcourir", browse_output).grid(row=0, column=2, padx=8, pady=6)

        make_label("Preset rendu", 1, 0)
        render_var = tk.StringVar(value=state["render_preset"])
        _ui_main.create_text_entry(tk, form, render_var, 1, 1, colors, width=40, sticky="w")

        make_label("Profil batch", 2, 0)
        profile_var = tk.StringVar(value=state["profile"])
        profile_menu = _ui_main.create_option_menu(tk, form, profile_var, ["valo", "jeu", "react"], 2, 1, colors)

        make_label("Preset", 3, 0)
        preset_var = tk.StringVar(value=state["preset_id"])
        preset_menu = _ui_main.create_option_menu(tk, form, preset_var, list(presets.keys()), 3, 1, colors)

        status_setter: dict[str, Any] = {"fn": None}

        def load_current_preset() -> None:
            pid = preset_var.get().strip()
            load_editor_from_preset(pid)
            fn = status_setter.get("fn")
            if callable(fn):
                fn(f"Preset loadé: {pid}", warnings=[])
            _log(f"Preset loaded: {pid}")

        ui_button(form, "Charger", load_current_preset).grid(row=3, column=2, padx=8, pady=6, sticky="w")

        query_var = tk.StringVar(value="")
        transcript_select_var = tk.BooleanVar(value=False)
        preview_safe_quality_var = tk.BooleanVar(value=True)
        subtitle_template_var = tk.StringVar(value=state["subtitle_template_name"])
        subtitle_offset_ms_var = tk.StringVar(value=state["subtitle_offset_ms"])
        subtitle_preset_var = tk.StringVar(value=state["subtitle_preset_id"])
        subtitle_preset_menu: Any | None = None

        def refresh_subtitle_preset_menu() -> None:
            try:
                menu = subtitle_preset_menu["menu"]
                menu.delete(0, "end")
                for sid in subtitle_presets.keys():
                    menu.add_command(label=sid, command=lambda value=sid: (subtitle_preset_var.set(value), load_subtitle_preset(value)))
            except Exception:
                pass

        def load_subtitle_preset(sid: str) -> None:
            p = dict(subtitle_presets.get(sid, {}))
            if not p:
                return
            subtitle_template_var.set(str(p.get("subtitle_template_name", SUBTITLE_TEMPLATE_AUTO_LABEL)) or SUBTITLE_TEMPLATE_AUTO_LABEL)
            subtitle_offset_ms_var.set(str(p.get("subtitle_offset_ms", -500)))
            profile_key = profile_var.get().strip()
            if profile_key:
                profiles.setdefault(profile_key, {})["active_subtitle_preset"] = sid
                presets_data["profiles"] = profiles
                _save_presets(_repo_root(), presets_data)
            fn = status_setter.get("fn")
            if callable(fn):
                fn(f"Preset sous-titres chargé: {sid}", warnings=[])

        def selected_subtitle_preset() -> dict[str, Any]:
            sid = subtitle_preset_var.get().strip()
            return dict(subtitle_presets.get(sid, {}))

        def open_subtitle_preset_editor() -> None:
            sid = subtitle_preset_var.get().strip() or DEFAULT_SUBTITLE_PRESET_ID
            base = dict(subtitle_presets.get(sid, _default_subtitle_presets()[DEFAULT_SUBTITLE_PRESET_ID]))
            _ui_presets.open_subtitle_preset_editor(
                tk,
                messagebox,
                root,
                colors,
                ui_button,
                sid,
                base,
                subtitle_template_options,
                SUBTITLE_TEMPLATE_AUTO_LABEL,
                subtitle_presets,
                presets_data,
                profiles,
                profile_var,
                subtitle_preset_var,
                subtitle_template_var,
                subtitle_offset_ms_var,
                refresh_subtitle_preset_menu,
                load_subtitle_preset,
                _save_presets,
                _repo_root,
                set_status,
                _coerce_float,
                _coerce_int,
            )

        make_label("Preset sous-titres", 5, 0)
        subtitle_preset_row = tk.Frame(form, bg=colors["panel_alt"])
        subtitle_preset_row.grid(row=5, column=1, padx=8, pady=6, sticky="w")
        subtitle_preset_menu = tk.OptionMenu(subtitle_preset_row, subtitle_preset_var, *list(subtitle_presets.keys()))
        subtitle_preset_menu.config(bg=colors["sun"], fg=colors["ink"], bd=2, relief="raised", activebackground=colors["sun_soft"])
        subtitle_preset_menu.pack(side="left", padx=(0, 8))
        ui_button(subtitle_preset_row, "Charger", lambda: load_subtitle_preset(subtitle_preset_var.get().strip()), primary=False).pack(side="left", padx=(0, 6))
        ui_button(subtitle_preset_row, "Éditer", open_subtitle_preset_editor, primary=False).pack(side="left")

        make_label("Recherche transcript", 6, 0)
        _ui_main.create_text_entry(tk, form, query_var, 6, 1, colors)

        def open_keywords_editor() -> None:
            try:
                _ui_keywords.open_keywords_editor(tk, messagebox, root, colors, _repo_root(), ui_button, set_status)
            except Exception as exc:
                set_status(f"Erreur éditeur mots-clés: {exc}")

        transcript_opts = tk.Frame(form, bg=colors["panel_alt"])
        transcript_opts.grid(row=7, column=1, padx=8, pady=6, sticky="w")
        tk.Checkbutton(
            transcript_opts,
            text="Utiliser le transcript pour sélectionner les clips",
            variable=transcript_select_var,
            bg=colors["panel_alt"],
            fg=colors["ink"],
            selectcolor=colors["sun_soft"],
            activebackground=colors["panel_alt"],
        ).pack(side="left", padx=(0, 8))
        ui_button(transcript_opts, "Voir les mots-clés", open_keywords_editor, primary=False).pack(side="left")
        tk.Checkbutton(
            transcript_opts,
            text="Mode aperçu fluide (Qualité)",
            variable=preview_safe_quality_var,
            bg=colors["panel_alt"],
            fg=colors["ink"],
            activebackground=colors["panel_alt"],
            selectcolor=colors["sun_soft"],
            font=("Segoe UI", 9, "bold"),
        ).pack(side="left", padx=(10, 0))

        make_label("Modèle de sous-titres", 8, 0)
        subtitle_template_menu = _ui_main.create_option_menu(tk, form, subtitle_template_var, subtitle_template_options, 8, 1, colors)

        make_label("Décalage sous-titres (ms)", 9, 0)
        _ui_main.create_text_entry(tk, form, subtitle_offset_ms_var, 9, 1, colors, width=12, sticky="w")

        master_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            form,
            text="Ajouter le rendu MASTER_REVIEW",
            variable=master_var,
            bg=colors["panel_alt"],
            fg=colors["ink"],
            selectcolor=colors["sun_soft"],
            activebackground=colors["panel_alt"],
        ).grid(row=10, column=1, padx=8, pady=6, sticky="w")
        refresh_subtitle_preset_menu()
        load_subtitle_preset(subtitle_preset_var.get().strip())

        editor_wrap = tk.Frame(batch_tab, bg=colors["sky"])
        editor_wrap.grid(row=1, column=0, columnspan=3, padx=0, pady=8, sticky="nw")
        editor_visible = tk.BooleanVar(value=False)
        editor_toggle_text = tk.StringVar(value="▸ Éditeur de preset")

        preset_toolbar = tk.Frame(editor_wrap, bg=colors["sky"])
        preset_toolbar.pack(anchor="w", padx=0, pady=(0, 6))

        editor_toggle = ui_button(preset_toolbar, editor_toggle_text.get(), lambda: None)
        editor_toggle.configure(textvariable=editor_toggle_text)
        editor_toggle.pack(side="left", padx=(0, 6))

        detect_mode_var = tk.StringVar(value="Frame actuelle")
        detect_mode = tk.OptionMenu(preset_toolbar, detect_mode_var, "Frame actuelle", "Premier clip")
        detect_mode.config(bg=colors["sun"], fg=colors["ink"], bd=2, relief="raised", activebackground=colors["sun_soft"])
        detect_mode.pack(side="left", padx=(0, 6))

        detect_mode_label = tk.Label(preset_toolbar, text="Détection: Frame actuelle", bg=colors["sky"], fg=colors["ink"], font=("Segoe UI", 9, "bold"))
        detect_mode_label.pack(side="left", padx=(0, 6))

        editor = tk.LabelFrame(editor_wrap, text="✦ Éditeur de preset ✦", bg=colors["panel"], fg=colors["ink"], padx=8, pady=8, bd=4, relief="ridge", font=("Verdana", 10, "bold"))
        # default collapsed

        editor_canvas = tk.Canvas(editor, bg=colors["panel"], highlightthickness=0)
        editor_scroll = tk.Scrollbar(editor, orient="vertical", command=editor_canvas.yview)
        editor_canvas.configure(yscrollcommand=editor_scroll.set)
        editor_scroll.pack(side="right", fill="y")
        editor_canvas.pack(side="left", fill="both", expand=True)

        editor_fields = tk.Frame(editor_canvas, bg=colors["panel"])
        editor_window = editor_canvas.create_window((0, 0), window=editor_fields, anchor="nw")

        def _on_editor_configure(_event: Any) -> None:
            editor_canvas.configure(scrollregion=editor_canvas.bbox("all"))

        def _on_canvas_configure(event: Any) -> None:
            editor_canvas.itemconfigure(editor_window, width=event.width)

        editor_fields.bind("<Configure>", _on_editor_configure)
        editor_canvas.bind("<Configure>", _on_canvas_configure)

        def _on_mousewheel(event: Any) -> None:
            delta = -1 * int(event.delta / 120) if event.delta else 0
            if delta:
                editor_canvas.yview_scroll(delta, "units")

        editor_canvas.bind_all("<MouseWheel>", _on_mousewheel)

        field_vars: dict[str, tk.StringVar] = {}
        slider_vars: dict[str, tk.DoubleVar] = {}
        safe_padding_var = tk.StringVar(value="0.04")
        layers_count_var = tk.StringVar(value="1")
        apply_scope_var = tk.StringVar(value="Clip entier")
        preset_mode_var = tk.StringVar(value="single")
        mode_label_var = tk.StringVar(value="mode: single")

        tk.Label(editor_fields, textvariable=mode_label_var, bg=colors["panel"], fg=colors["ink"], font=("Segoe UI", 10, "bold")).grid(row=0, column=0, columnspan=4, sticky="w")

        def _slider_bounds(prop_key: str) -> tuple[float, float, float]:
            return _ui_presets.slider_bounds(prop_key)

        def _add_numeric_control(parent: Any, r: int, c: int, fk: str, key: str) -> None:
            field_vars[fk] = tk.StringVar(value="0")
            slider_vars[fk] = tk.DoubleVar(value=0.0)

            tk.Label(parent, text=key, bg=colors["panel"], fg=colors["ink"]).grid(row=r, column=c, sticky="e", padx=3)
            entry = tk.Entry(parent, textvariable=field_vars[fk], width=7, bd=3, relief="sunken", bg="#FFFFFF", fg=colors["ink"], insertbackground=colors["accent"], font=("Tahoma", 8))
            entry.grid(row=r, column=c + 1, sticky="w", padx=3)

            min_v, max_v, res = _slider_bounds(key)
            scale = tk.Scale(
                parent,
                from_=min_v,
                to=max_v,
                orient="horizontal",
                resolution=res,
                length=120,
                showvalue=False,
                variable=slider_vars[fk],
                bg=colors["panel"],
                fg=colors["ink"],
                highlightthickness=0,
                troughcolor=colors["sun_soft"],
                activebackground=colors["accent_soft"],
            )
            scale.grid(row=r, column=c + 2, sticky="w", padx=(2, 8))

            def on_slider(*_args: Any) -> None:
                field_vars[fk].set(f"{slider_vars[fk].get():.3f}")

            def on_entry(*_args: Any) -> None:
                raw = field_vars[fk].get().strip()
                if not raw:
                    return
                try:
                    val = float(raw)
                except Exception:
                    return
                if val < min_v:
                    val = min_v
                if val > max_v:
                    val = max_v
                slider_vars[fk].set(val)

            slider_vars[fk].trace_add("write", on_slider)
            entry.bind("<FocusOut>", lambda _e: on_entry())
            entry.bind("<Return>", lambda _e: on_entry())

        row = 1
        for group in ("single", "gameplay", "camera"):
            tk.Label(editor_fields, text=group, bg=colors["panel"], fg=colors["ink"], font=("Segoe UI", 9, "bold")).grid(row=row, column=0, sticky="w", pady=3)
            row += 1
            for idx, key in enumerate(keys):
                fk = f"{group}.{key}"
                col_group = (idx % 2) * 3
                _add_numeric_control(editor_fields, row, col_group, fk, key)
                if idx % 2 == 1:
                    row += 1
            row += 1

        tk.Label(editor_fields, text="marge_sûre", bg=colors["panel"], fg=colors["ink"]).grid(row=row, column=0, sticky="e")
        tk.Entry(editor_fields, textvariable=safe_padding_var, width=10, bd=3, relief="sunken", bg="#FFFFFF", fg=colors["ink"], insertbackground=colors["accent"]).grid(row=row, column=1, sticky="w")
        tk.Label(editor_fields, text="nombre_de_calques", bg=colors["panel"], fg=colors["ink"]).grid(row=row, column=2, sticky="e")
        layers_spin = tk.Spinbox(editor_fields, from_=1, to=4, textvariable=layers_count_var, width=6)
        layers_spin.grid(row=row, column=3, sticky="w")

        row += 1
        tk.Label(editor_fields, text="portée_application", bg=colors["panel"], fg=colors["ink"]).grid(row=row, column=0, sticky="e")
        apply_scope_menu = tk.OptionMenu(editor_fields, apply_scope_var, "Clip entier", "Plage sélectionnée")
        apply_scope_menu.config(bg=colors["sun"], fg=colors["ink"], bd=2, relief="raised", activebackground=colors["sun_soft"])
        apply_scope_menu.grid(row=row, column=1, sticky="w")

        def refresh_preset_menu() -> None:
            menu = preset_menu["menu"]
            menu.delete(0, "end")
            for pid in presets.keys():
                menu.add_command(label=pid, command=lambda value=pid: preset_var.set(value))

        def load_editor_from_preset(pid: str) -> None:
            p = dict(presets.get(pid, {}))
            values = _ui_presets.editor_values_from_preset(p, keys)
            preset_mode_var.set(str(values["mode"]))
            mode_label_var.set(str(values["mode_label"]))
            safe_padding_var.set(str(values["safe_padding"]))
            layers_count_var.set(str(values["layers_count"]))
            for fk, value in dict(values["fields"]).items():
                if fk in field_vars:
                    field_vars[fk].set(str(value))
                if fk in slider_vars:
                    slider_vars[fk].set(float(value))

        def detect_preset_from_timeline() -> None:
            mode_label = detect_mode_var.get().strip()
            mode = "current" if mode_label == "Frame actuelle" else "first"
            detect_mode_label.config(text=f"Détection: {mode_label}")
            deps = _timeline_actions.TimelineActionDeps(
                safe_call=_safe_call,
                log=_log,
                get_item_at_current_frame=_get_item_at_current_frame,
                get_first_item_on_track=_get_first_item_on_track,
                apply_preset_to_selected_clip=_apply_preset_to_selected_clip,
            )
            result = _timeline_actions.detect_fixed_split_preset_from_timeline(resolve, mode, deps, keys)
            if not result.get("ok"):
                set_status(str(result.get("message", "Détection impossible")))
                return

            preset_mode_var.set("fixed_split")
            mode_label_var.set("mode: fixed_split")
            for field_key, value in dict(result.get("fields", {})).items():
                if field_key in field_vars:
                    field_vars[field_key].set(f"{float(value):.3f}")
                if field_key in slider_vars:
                    slider_vars[field_key].set(float(value))

            set_status(str(result.get("message", "Preset détecté")))

        ui_button(preset_toolbar, "Détecter le preset", detect_preset_from_timeline).pack(side="left", padx=(0, 6))

        def preset_from_editor(base: dict[str, Any]) -> dict[str, Any]:
            field_values = {name: var.get().strip() for name, var in field_vars.items()}
            return _ui_presets.preset_from_editor_values(
                base,
                preset_mode_var.get(),
                layers_count_var.get(),
                safe_padding_var.get(),
                field_values,
                keys,
            )

        status_var = tk.StringVar(value="Prêt")
        last_warnings: list[str] = []

        def open_warnings_window() -> None:
            _ui_status.open_warnings_window(tk, root, colors, last_warnings)

        def set_status(message: str, warnings: list[str] | None = None) -> None:
            nonlocal last_warnings
            last_warnings = _ui_status.set_status_text(status_var, status_text, message, last_warnings, warnings)

        status_setter["fn"] = set_status

        def open_rate_batch_window() -> None:
            _ui_feedback.open_rate_batch_window(
                tk,
                root,
                colors,
                ui_button,
                session_ref.get("manifest"),
                default_manifest,
                _repo_root,
                set_status,
                _log,
            )

        def save_overwrite() -> None:
            pid = preset_var.get().strip()
            result = _preset_actions.save_overwrite_preset_data(
                presets_data,
                pid,
                profile_var.get().strip(),
                preset_from_editor,
            )
            if result.get("status") != "saved":
                return
            _save_presets(_repo_root(), presets_data)
            messagebox.showinfo("Short Editor", f"Preset enregistré: {pid}")

        def delete_selected_preset() -> None:
            pid = preset_var.get().strip()
            if not pid or pid not in presets:
                return
            if len(presets) <= 1:
                messagebox.showwarning("Short Editor", "Impossible de supprimer le dernier preset.")
                return
            confirmed = messagebox.askyesno("Supprimer le preset", f"Supprimer définitivement le preset '{pid}' ?")
            if not confirmed:
                return
            result = _preset_actions.delete_preset_data(presets_data, pid)
            if result.get("status") != "deleted":
                return
            replacement = str(result.get("replacement", ""))
            _save_presets(_repo_root(), presets_data)
            refresh_preset_menu()
            preset_var.set(replacement)
            load_editor_from_preset(replacement)
            set_status(f"Preset supprimé: {pid}. Preset actif: {replacement}")

        def apply_preset_now(scope_mode: str) -> None:
            pid = preset_var.get().strip()
            deps = _timeline_actions.TimelineActionDeps(
                safe_call=_safe_call,
                log=_log,
                get_item_at_current_frame=_get_item_at_current_frame,
                get_first_item_on_track=_get_first_item_on_track,
                apply_preset_to_selected_clip=_apply_preset_to_selected_clip,
            )
            ok, msg = _timeline_actions.apply_named_preset(resolve, presets_data, pid, scope_mode, deps)
            set_status(msg)

        def apply_to_selected_clip_now() -> None:
            scope_mode = "selected_range" if apply_scope_var.get().strip() == "Plage sélectionnée" else "whole_clip"
            apply_preset_now(scope_mode)

        def save_as_new() -> None:
            top = tk.Toplevel(root)
            top.title("Enregistrer le preset sous")
            top.configure(bg=colors["panel_alt"])
            tk.Label(top, text="Nouveau preset", bg=colors["panel_alt"], fg=colors["ink"], font=("Segoe UI", 10, "bold")).grid(row=0, column=0, padx=8, pady=8)
            new_id_var = tk.StringVar(value=preset_var.get().strip() + "_V2")
            tk.Entry(top, textvariable=new_id_var, width=36, bd=2, relief="sunken").grid(row=0, column=1, padx=8, pady=8)

            def do_save() -> None:
                nid = new_id_var.get().strip()
                result = _preset_actions.save_new_preset_data(
                    presets_data,
                    preset_var.get().strip(),
                    nid,
                    profile_var.get().strip(),
                    preset_from_editor,
                )
                if result.get("status") != "saved":
                    return
                _save_presets(_repo_root(), presets_data)
                preset_var.set(nid)
                refresh_preset_menu()
                top.destroy()
                messagebox.showinfo("Short Editor", f"Preset enregistré sous: {nid}")

            ui_button(top, "Enregistrer", do_save).grid(row=1, column=1, sticky="e", padx=8, pady=8)

        ui_button(editor_fields, "Enregistrer", save_overwrite).grid(row=row + 1, column=1, padx=6, pady=8)
        ui_button(editor_fields, "Enregistrer sous", save_as_new).grid(row=row + 1, column=2, padx=6, pady=8)
        ui_button(editor_fields, "Supprimer le preset", delete_selected_preset).grid(row=row + 1, column=3, padx=6, pady=8)
        ui_button(editor_fields, "Appliquer au clip sélectionné", apply_to_selected_clip_now, primary=False).grid(row=row + 2, column=0, columnspan=2, padx=6, pady=8, sticky="w")

        load_editor_from_preset(preset_var.get().strip())

        status_text = tk.Text(root, width=72, height=1, bg=colors["sun_soft"], fg=colors["ink"], bd=3, relief="sunken", wrap="none", cursor="hand2", font=("Tahoma", 9, "bold"))
        status_text.grid(row=4, column=0, columnspan=3, sticky="e", padx=10, pady=(0, 12))
        _ui_status.configure_status_text_bindings(status_text, open_warnings_window)
        set_status("Prêt")

        def toggle_editor() -> None:
            if editor_visible.get():
                editor.pack_forget()
                editor_visible.set(False)
                editor_toggle_text.set("▸ Éditeur de preset")
                root.geometry(compact_geometry)
            else:
                editor.pack(fill="both", expand=True)
                editor_visible.set(True)
                editor_toggle_text.set("▾ Éditeur de preset")
                root.geometry(expanded_geometry)

        editor_toggle.configure(command=toggle_editor)

        def collect_params() -> dict[str, Any]:
            return {
                "output": output_var.get().strip(),
                "render_preset": render_var.get().strip() or "H264_Shorts_1080x1920_60fps",
                "profile": profile_var.get().strip() or "valo",
                "preset_id": preset_var.get().strip() or state["preset_id"],
                "subtitle_preset_id": subtitle_preset_var.get().strip() or state["subtitle_preset_id"],
                "query": query_var.get().strip(),
                "use_transcript_for_selection": bool(transcript_select_var.get()),
                "render_master": bool(master_var.get()),
                "strict_manifest": False,
                "require_subtitles": False,
                "preview_safe_quality": bool(preview_safe_quality_var.get()),
                "subtitle_template_name": subtitle_template_var.get().strip() or SUBTITLE_TEMPLATE_AUTO_LABEL,
                "subtitle_offset_ms": subtitle_offset_ms_var.get().strip() or "-500",
            }

        def run_now(strict_manifest: bool = False, require_subtitles: bool = False) -> None:
            params = collect_params()
            params["strict_manifest"] = bool(strict_manifest)
            params["require_subtitles"] = bool(require_subtitles)
            if require_subtitles:
                set_status("Génération du batch avec sous-titres auto...", warnings=[])
            else:
                set_status("Génération du batch rapide, sans sous-titres...", warnings=[])
            root.update_idletasks()

            progress = _ui_progress.ModalProgress(
                tk,
                root,
                colors,
                "Short Editor",
                "Génération des sous-titres, cela peut prendre quelques minutes..." if require_subtitles else "Génération du batch...",
                show_stage=True,
                show_percent=True,
                show_bar=True,
            )

            result_box: dict[str, Any] = {"result": None, "error": None}
            progress_box: dict[str, Any] = {"stage": "Batch", "current": 0, "total": 1, "detail": "Initialisation", "meta": {}}

            def _worker_progress(stage: str, current: int, total: int, detail: str = "", meta: dict[str, Any] | None = None) -> None:
                progress_box["stage"] = stage or "Batch"
                progress_box["current"] = max(0, int(current))
                progress_box["total"] = max(1, int(total))
                progress_box["detail"] = detail or ""
                progress_box["meta"] = dict(meta or {})

            params["_progress_cb"] = _worker_progress

            def _worker_generate() -> None:
                try:
                    result_box["result"] = on_generate(params)
                except Exception as exc:
                    result_box["error"] = exc

            worker = threading.Thread(target=_worker_generate, daemon=True)
            worker.start()

            ticks = 0
            while worker.is_alive():
                ticks += 1
                if require_subtitles and ticks % 100 == 0:
                    progress.set_text("Génération des sous-titres... toujours en cours, merci de patienter.")
                stage = str(progress_box.get("stage", "Batch"))
                current = int(progress_box.get("current", 0))
                total = max(1, int(progress_box.get("total", 1)))
                detail = str(progress_box.get("detail", "")).strip()
                meta = progress_box.get("meta", {}) if isinstance(progress_box.get("meta", {}), dict) else {}
                progress.set_batch_progress(
                    stage,
                    current,
                    total,
                    detail or ("Génération en cours..." if not require_subtitles else "Génération + sous-titres en cours..."),
                    processed_seconds=meta.get("processed_seconds"),
                    total_seconds=meta.get("total_seconds"),
                )
                progress.pump()
                time.sleep(0.03)

            progress.close()

            if result_box["error"] is not None:
                err = result_box["error"]
                set_status(f"Échec de génération: {err}", warnings=[str(err)])
                return

            result = result_box["result"]
            should_open_rating = False
            if isinstance(result, dict):
                msg = str(result.get("message", "Terminé"))
                set_status(msg, list(result.get("warnings", []) or []))
                should_open_rating = msg.lower().startswith("generated ")
            else:
                set_status(str(result), warnings=[])
                should_open_rating = str(result).lower().startswith("generated ")
            if should_open_rating:
                try:
                    open_rate_batch_window()
                except Exception as exc:
                    _log(f"auto_open_rate_batch_failed: {exc}")
                    set_status(f"Noter le batch indisponible: {exc}")

        def run_now_quality() -> None:
            run_now(strict_manifest=True, require_subtitles=True)

        def update_now() -> None:
            params = collect_params()
            set_status("Mise à jour de la composition...", warnings=[])
            root.update_idletasks()
            result = on_update(params)
            if isinstance(result, dict):
                set_status(str(result.get("message", "Terminé")), list(result.get("warnings", []) or []))
            else:
                set_status(str(result), warnings=[])

        def add_subtitles_to_selected_clip() -> None:
            set_status("Génération des sous-titres pour le clip sélectionné...", warnings=[])
            root.update_idletasks()

            progress = _ui_progress.ModalProgress(
                tk,
                root,
                colors,
                "Short Editor",
                "Transcription de la source du clip sélectionné...",
            )

            result_box: dict[str, Any] = {"result": None, "error": None}

            def _worker_single_sub() -> None:
                try:
                    deps = _clip_subtitles.ClipSubtitleDeps(
                        selected_clip_subtitle_context=_selected_clip_subtitle_context,
                        load_pipeline_config=_load_pipeline_config,
                        merge_subtitle_preset_into_config=_merge_subtitle_preset_into_config,
                        subtitle_style_from_preset=_subtitle_style_from_preset,
                        import_subtitles_to_timeline=_import_subtitles_to_timeline,
                    )
                    result_box["result"] = _clip_subtitles.add_subtitles_to_selected_clip(
                        _repo_root(),
                        resolve,
                        selected_subtitle_preset(),
                        str(subtitle_template_var.get().strip() or SUBTITLE_TEMPLATE_AUTO_LABEL),
                        subtitle_offset_ms_var.get(),
                        deps,
                        SUBTITLE_TEMPLATE_AUTO_LABEL,
                    )
                except Exception as exc:
                    result_box["error"] = exc

            worker = threading.Thread(target=_worker_single_sub, daemon=True)
            worker.start()
            ticks = 0
            while worker.is_alive():
                ticks += 1
                if ticks % 100 == 0:
                    progress.set_text("Traitement des sous-titres du clip sélectionné toujours en cours...")
                progress.pump()
                time.sleep(0.03)

            progress.close()

            if result_box["error"] is not None:
                err = result_box["error"]
                set_status(f"Échec des sous-titres du clip sélectionné: {err}", warnings=[str(err)])
                return

            res = result_box.get("result") or {}
            if bool(res.get("ok", False)):
                set_status(str(res.get("message", "Terminé")), list(res.get("warnings", []) or []))
            else:
                msg = str(res.get("message", "Erreur de sous-titres inconnue"))
                set_status(msg, warnings=[msg])

        silence_scope_var = tk.StringVar(value="Clip sélectionné")
        action_preset_scope_var = tk.StringVar(value="Clip sélectionné")

        def cut_silences_now() -> None:
            scope = silence_scope_var.get().strip() or "Clip sélectionné"
            set_status(f"Analyse des silences: {scope}...", warnings=[])
            root.update_idletasks()

            progress = _ui_progress.ModalProgress(
                tk,
                root,
                colors,
                "Couper les silences",
                "Analyse audio en cours...",
                geometry="460x130",
                show_stage=True,
                show_bar=True,
                bar_width=390,
                fill_color_key="accent_soft",
            )

            result_box: dict[str, Any] = {"result": None, "error": None}
            progress_box: dict[str, Any] = {"current": 0, "total": 1, "detail": "Initialisation"}

            def _set_progress(current: int, total: int, detail: str) -> None:
                progress_box["current"] = max(0, int(current))
                progress_box["total"] = max(1, int(total))
                progress_box["detail"] = detail

            def _worker_cut() -> None:
                try:
                    deps = _silence_actions.SilenceActionDeps(
                        safe_call=_safe_call,
                        log=_log,
                        load_pipeline_config=_load_pipeline_config,
                        selected_clip_subtitle_context=_selected_clip_subtitle_context,
                        load_audio_energy_for_silence_cut=_load_audio_energy_for_silence_cut,
                        detect_audible_segments_for_silence_cut=_detect_audible_segments_for_silence_cut,
                        create_silence_cut_timeline=_create_silence_cut_timeline,
                        parse_manifest=_parse_manifest,
                        suffix_timeline_name=_suffix_timeline_name,
                        find_timeline_by_name=_find_timeline_by_name,
                    )
                    result_box["result"] = _silence_actions.run_silence_cut(
                        _repo_root(),
                        resolve,
                        scope,
                        preset_var.get().strip(),
                        presets_data,
                        session_ref,
                        default_manifest,
                        deps,
                        _set_progress,
                    )
                except Exception as exc:
                    result_box["error"] = exc

            worker = threading.Thread(target=_worker_cut, daemon=True)
            worker.start()
            while worker.is_alive():
                cur = int(progress_box.get("current", 0))
                total = max(1, int(progress_box.get("total", 1)))
                detail = str(progress_box.get("detail", "Analyse"))
                progress.set_batch_progress(detail, cur, total, "Coupe automatique des silences en cours...")
                progress.pump()
                time.sleep(0.03)

            progress.close()

            if result_box["error"] is not None:
                err = result_box["error"]
                set_status(f"Échec coupe des silences: {err}", warnings=[str(err)])
                return
            result = result_box.get("result") or {}
            msg = str(result.get("message", "Coupe des silences terminée."))
            set_status(msg, list(result.get("warnings", []) or []))
            if result.get("ok"):
                play_notification_sound()

        def undo_silence_cuts_now() -> None:
            scope = silence_scope_var.get().strip() or "Clip sélectionné"
            set_status(f"Annulation des cuts de silences: {scope}...", warnings=[])

            def _confirm_delete(count: int) -> bool:
                try:
                    return bool(
                        messagebox.askyesno(
                            "Annuler les cuts de silences",
                            f"Supprimer {count} timeline(s) __silence_cut ?\n\n"
                            "Les timelines originales ne seront pas modifiées.",
                            parent=root,
                        )
                    )
                except Exception:
                    return True

            deps = _silence_actions.SilenceActionDeps(
                safe_call=_safe_call,
                log=_log,
                load_pipeline_config=_load_pipeline_config,
                selected_clip_subtitle_context=_selected_clip_subtitle_context,
                load_audio_energy_for_silence_cut=_load_audio_energy_for_silence_cut,
                detect_audible_segments_for_silence_cut=_detect_audible_segments_for_silence_cut,
                create_silence_cut_timeline=_create_silence_cut_timeline,
                parse_manifest=_parse_manifest,
                suffix_timeline_name=_suffix_timeline_name,
                find_timeline_by_name=_find_timeline_by_name,
            )
            result = _silence_actions.undo_silence_cuts(resolve, scope, session_ref, default_manifest, deps, _confirm_delete)
            msg = str(result.get("message", "Annulation des cuts terminée."))
            set_status(msg, warnings=list(result.get("warnings", []) or []))
            if result.get("ok"):
                play_notification_sound()

        batch_footer = tk.Frame(batch_tab, bg=colors["sky"], bd=0)
        batch_footer.grid(row=2, column=0, columnspan=3, sticky="e", padx=10, pady=(2, 12))
        ui_button(batch_footer, "Générer + sous-titres auto (Qualité)", run_now_quality, primary=True).pack(side="right", padx=6)
        ui_button(batch_footer, "Générer le batch (Rapide)", run_now, primary=True).pack(side="right", padx=6)

        actions_panel = tk.LabelFrame(actions_tab, text="♡ Actions timeline ♡", bg=colors["panel_alt"], fg=colors["ink"], bd=4, relief="ridge", padx=12, pady=12, font=("Verdana", 10, "bold"))
        actions_panel.grid(row=0, column=0, sticky="nwe", padx=10, pady=(0, 8))
        tk.Label(
            actions_panel,
            text="Actions sur le batch ou la timeline active, sans relancer une génération complète.",
            bg=colors["panel_alt"],
            fg=colors["ink"],
            font=("Segoe UI", 10, "bold"),
            anchor="w",
        ).grid(row=0, column=0, columnspan=3, sticky="we", padx=6, pady=(0, 10))
        ui_button(actions_panel, "Noter le batch", open_rate_batch_window, primary=False).grid(row=1, column=0, padx=6, pady=6, sticky="we")
        ui_button(actions_panel, "Ajouter des sous-titres au clip", add_subtitles_to_selected_clip, primary=False).grid(row=1, column=1, padx=6, pady=6, sticky="we")
        ui_button(actions_panel, "Mettre à jour la composition (Batch)", update_now, primary=False).grid(row=1, column=2, padx=6, pady=6, sticky="we")
        silence_panel = tk.LabelFrame(actions_panel, text="✂ Couper les silences ✦", bg=colors["panel"], fg=colors["ink"], bd=4, relief="ridge", padx=8, pady=8, font=("Verdana", 9, "bold"))
        silence_panel.grid(row=2, column=0, columnspan=3, sticky="we", padx=6, pady=(12, 6))
        tk.Label(
            silence_panel,
            text="Coupe les silences gênants avec une marge pour garder un rythme naturel.",
            bg=colors["panel"],
            fg=colors["ink"],
            font=("Segoe UI", 9, "bold"),
            anchor="w",
        ).grid(row=0, column=0, columnspan=4, sticky="we", padx=4, pady=(0, 6))
        tk.Radiobutton(
            silence_panel,
            text="Clip sélectionné",
            variable=silence_scope_var,
            value="Clip sélectionné",
            bg=colors["panel"],
            fg=colors["ink"],
            selectcolor=colors["sun_soft"],
            activebackground=colors["panel"],
        ).grid(row=1, column=0, sticky="w", padx=4, pady=4)
        tk.Radiobutton(
            silence_panel,
            text="Batch entier",
            variable=silence_scope_var,
            value="Batch entier",
            bg=colors["panel"],
            fg=colors["ink"],
            selectcolor=colors["sun_soft"],
            activebackground=colors["panel"],
        ).grid(row=1, column=1, sticky="w", padx=4, pady=4)
        ui_button(silence_panel, "Couper les silences", cut_silences_now, primary=True).grid(row=1, column=2, sticky="e", padx=4, pady=4)
        ui_button(silence_panel, "Annuler les cuts", undo_silence_cuts_now, primary=False).grid(row=1, column=3, sticky="e", padx=4, pady=4)
        silence_panel.columnconfigure(2, weight=1)
        silence_panel.columnconfigure(3, weight=1)

        action_preset_panel = tk.LabelFrame(actions_panel, text="✦ Appliquer le preset ✦", bg=colors["panel"], fg=colors["ink"], bd=4, relief="ridge", padx=8, pady=8, font=("Verdana", 9, "bold"))
        action_preset_panel.grid(row=3, column=0, columnspan=3, sticky="we", padx=6, pady=(10, 6))
        tk.Label(
            action_preset_panel,
            text="Applique le preset actif au clip, à la plage In/Out, ou à toute la timeline.",
            bg=colors["panel"],
            fg=colors["ink"],
            font=("Segoe UI", 9, "bold"),
            anchor="w",
        ).grid(row=0, column=0, columnspan=4, sticky="we", padx=4, pady=(0, 6))

        def _action_scope_mode() -> str:
            label = action_preset_scope_var.get().strip()
            if label == "Plage sélectionnée":
                return "selected_range"
            if label == "Toute la timeline":
                return "whole_timeline"
            return "whole_clip"

        for col, label in enumerate(("Clip sélectionné", "Plage sélectionnée", "Toute la timeline")):
            tk.Radiobutton(
                action_preset_panel,
                text=label,
                variable=action_preset_scope_var,
                value=label,
                bg=colors["panel"],
                fg=colors["ink"],
                selectcolor=colors["sun_soft"],
                activebackground=colors["panel"],
            ).grid(row=1, column=col, sticky="w", padx=4, pady=4)
        ui_button(action_preset_panel, "Appliquer le preset", lambda: apply_preset_now(_action_scope_mode()), primary=True).grid(row=1, column=3, sticky="e", padx=4, pady=4)
        action_preset_panel.columnconfigure(3, weight=1)

        sticker_panel = tk.Frame(actions_panel, bg=colors["panel_alt"])
        sticker_panel.grid(row=4, column=0, columnspan=3, sticky="we", padx=6, pady=(8, 2))
        for sticker in ("✧ cyber fairy active", "♡ pas de SaaS", "☁ dream guide online", "★ old web magic"):
            tk.Label(
                sticker_panel,
                text=sticker,
                bg=colors["mint"],
                fg=colors["ink"],
                bd=2,
                relief="ridge",
                font=("Tahoma", 8, "bold"),
                padx=6,
                pady=2,
            ).pack(side="left", padx=4)
        for col in range(3):
            actions_panel.columnconfigure(col, weight=1)

        footer = tk.Frame(root, bg=colors["sky"], bd=0)
        footer.grid(row=3, column=0, columnspan=3, sticky="e", padx=10, pady=(0, 4))
        ui_button(footer, "Annuler", root.destroy, primary=False).pack(side="right", padx=6)

        show_tab("batch")

        root.columnconfigure(1, weight=1)
        root.rowconfigure(2, weight=0)
        batch_tab.rowconfigure(1, weight=0)
        actions_tab.columnconfigure(0, weight=1)
        form.columnconfigure(1, weight=1)
        root.mainloop()

    except Exception as exc:
        _log(f"UI ERROR: {exc}")
        raise RuntimeError(f"Impossible d'ouvrir l'UI: {exc}")


def _safe_int_from_project_setting(project: Any, key: str, fallback: int) -> int:
    return _project_settings.safe_int_from_project_setting(project, key, fallback)


def _fps_from_project(project: Any) -> int:
    return _project_settings.fps_from_project(project, DEFAULT_FPS)


def _parse_fps_text(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if "/" in text:
        parts = text.split("/", 1)
        try:
            num = float(parts[0])
            den = float(parts[1])
            if den > 0:
                out = num / den
                return out if out > 0 else None
        except Exception:
            return None
    try:
        out = float(text)
        return out if out > 0 else None
    except Exception:
        return None


def _probe_video_fps(source_path: Path) -> float | None:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=r_frame_rate,avg_frame_rate",
        "-of",
        "json",
        str(source_path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except Exception:
        return None
    if result.returncode != 0:
        return None
    try:
        data = json.loads(result.stdout or "{}")
        streams = data.get("streams", [])
        if not streams:
            return None
        s0 = streams[0] if isinstance(streams[0], dict) else {}
        fps = _parse_fps_text(s0.get("avg_frame_rate"))
        if fps is None:
            fps = _parse_fps_text(s0.get("r_frame_rate"))
        if fps is None:
            return None
        if fps > 120:
            return None
        return fps
    except Exception:
        return None


def _source_fps_for_media_item(media_item: Any, source_path: Path, fallback_fps: int) -> float:
    props = _safe_call(media_item, "GetClipProperty", default={}) or {}
    for key in ("FPS", "Frame Rate", "Video Frame Rate"):
        fps_prop = _parse_fps_text(props.get(key))
        if fps_prop is not None and fps_prop <= 120:
            return fps_prop
    probed = _probe_video_fps(source_path)
    if probed is not None:
        return probed
    if fallback_fps <= 0:
        return float(DEFAULT_FPS)
    return float(fallback_fps)


def _overlap_ratio_from_ranges(a_start: float, a_end: float, b_start: float, b_end: float) -> float:
    return overlap_ratio_from_ranges(a_start, a_end, b_start, b_end)


def _ranges_too_close(
    a_start: float,
    a_end: float,
    b_start: float,
    b_end: float,
    overlap_threshold: float = 0.35,
    min_center_distance_seconds: float = 60.0,
) -> bool:
    return ranges_too_close(
        a_start,
        a_end,
        b_start,
        b_end,
        overlap_threshold=overlap_threshold,
        min_center_distance_seconds=min_center_distance_seconds,
    )


def _auto_detect_vod_path(resolve: Any, root: Path) -> Path | None:
    project_manager = _safe_call(resolve, "GetProjectManager")
    project = _safe_call(project_manager, "GetCurrentProject") if project_manager else None
    if not project:
        return None

    # Strategy 1: current timeline video item (playhead sur un clip)
    timeline = _safe_call(project, "GetCurrentTimeline")
    if timeline:
        item = _safe_call(timeline, "GetCurrentVideoItem")
        if item:
            fp = _source_path_from_resolve_clip(item)
            if fp and Path(fp).exists():
                _log(f"Auto VOD detect: current timeline clip {fp}")
                return Path(fp)

    media_pool = _safe_call(project, "GetMediaPool")

    # Strategy 2: GetSelectedClips (API variable selon version Resolve)
    if media_pool:
        selected = _safe_call(media_pool, "GetSelectedClips", default=[]) or []
        if selected:
            first = selected[0]
            props = _safe_call(first, "GetClipProperty", default={}) or {}
            fp = str(props.get("File Path") or "")
            if fp and Path(fp).exists():
                _log(f"Auto VOD detect: selected media clip {fp}")
                return Path(fp)

    # Strategy 3: clips dans le dossier courant du Media Pool
    if media_pool:
        current_folder = _safe_call(media_pool, "GetCurrentFolder", default=None)
        if current_folder:
            clips = _safe_call(current_folder, "GetClipList", default=[]) or []
            for clip in clips:
                props = _safe_call(clip, "GetClipProperty", default={}) or {}
                fp = str(props.get("File Path") or "")
                if fp and fp.lower().endswith(".mp4") and Path(fp).exists():
                    _log(f"Auto VOD detect: current folder clip {fp}")
                    return Path(fp)

    # Strategy 4: manifest le plus récent (meta.source_vod_path ou source_vods)
    manifests_dir = root / "output" / "manifests"
    if manifests_dir.exists():
        manifests = sorted(manifests_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        for manifest_path in manifests[:5]:
            try:
                data = _read_manifest_safe(manifest_path) or {}
                fp = str((data.get("meta") or {}).get("source_vod_path") or "")
                if not fp:
                    vods = data.get("source_vods") or []
                    fp = str(vods[0]) if vods else ""
                if fp and Path(fp).exists():
                    _log(f"Auto VOD detect: from manifest {manifest_path.name} path={fp}")
                    return Path(fp)
            except Exception:
                continue

    return None


def _prompt_vod_path_native(default_dir: Path, parent: Any | None = None) -> Path | None:
    try:
        import tkinter as tk
        from tkinter import filedialog

        if parent is not None:
            chosen = filedialog.askopenfilename(
                title="Sélectionner la VOD MP4",
                initialdir=str(default_dir),
                filetypes=[("MP4", "*.mp4")],
                parent=parent,
            )
        else:
            root = tk.Tk()
            root.withdraw()
            chosen = filedialog.askopenfilename(
                title="Sélectionner la VOD MP4",
                initialdir=str(default_dir),
                filetypes=[("MP4", "*.mp4")],
            )
            root.destroy()
        if chosen:
            return Path(chosen)
    except Exception as exc:
        _log(f"VOD picker failed: {exc}")
    return None


def _ask_reopen_existing_batch(manifest_path: Path, parent: Any | None = None) -> bool:
    try:
        from tkinter import messagebox

        kwargs: dict[str, Any] = {}
        if parent is not None:
            kwargs["parent"] = parent
        root = _repo_root()
        data = _read_manifest_safe(manifest_path) or {}
        has_subtitles = _manifest_has_valid_subtitles(root, data) if data else False
        subtitle_label = "avec sous-titres" if has_subtitles else "sans sous-titres"
        return bool(
            messagebox.askyesno(
                "Session existante détectée",
                f"Un ancien batch {subtitle_label} a été détecté pour cette VOD.\n\n"
                f"{manifest_path.name}\n\n"
                "Voulez-vous rouvrir la session ?",
                **kwargs,
            )
        )
    except Exception as exc:
        _log(f"existing_batch_prompt_failed: {exc}")
        return False


def _ensure_clean_vod(root: Path, vod_path: Path, cfg: dict[str, Any], progress_cb: Any = None) -> Path | None:
    """Ensure a clean VOD (single mixed audio track, no Spotify) exists in work/.

    Returns the clean VOD path on success, None on failure.
    Called both during manifest generation (pre-compute) and during Resolve build (fallback).
    """
    from short_editor.audio_analysis import (
        count_audio_streams as _count_audio_streams,
        create_clean_vod as _create_clean_vod,
        create_mixed_vod as _create_mixed_vod,
        vod_has_audio as _vod_has_audio,
    )
    _audio_base_track = int(cfg.get("audio", {}).get("render", {}).get("base_track", 6))
    _clean_vod = root / "work" / f"{vod_path.stem}_track{_audio_base_track}{vod_path.suffix}"
    _clean_vod.parent.mkdir(parents=True, exist_ok=True)

    if _clean_vod.exists() and not _vod_has_audio(_clean_vod):
        _log(f"Clean VOD has no audio, removing stale file: {_clean_vod.name}")
        _clean_vod.unlink(missing_ok=True)

    if _clean_vod.exists():
        _log(f"Clean VOD already exists with audio: {_clean_vod.name}")
        return _clean_vod

    _num_audio = _count_audio_streams(str(vod_path))
    _log(f"Source VOD audio stream count: {_num_audio}")
    if _num_audio == 0:
        _log("Source VOD has no audio streams, skipping clean VOD creation")
        return None

    def _make_on_progress(label: str) -> Any:
        if not callable(progress_cb):
            return None
        def _cb(pct: int) -> None:
            progress_cb("Préparation audio", pct, 100, f"{label}: {pct}%")
        return _cb

    if _audio_base_track <= _num_audio:
        _label = f"Copie piste {_audio_base_track}"
        _log(f"Creating clean VOD (track {_audio_base_track} copy) → {_clean_vod.name}")
        if callable(progress_cb):
            progress_cb("Préparation audio", 0, 100, f"{_label}…")
        ok = _create_clean_vod(str(vod_path), _clean_vod, _audio_base_track, _make_on_progress(_label))
        _log(f"Clean VOD stream-copy ok={ok}")
    else:
        _always_muted = set(cfg.get("audio", {}).get("always_muted_tracks", [1, 4]))
        _mix_obs_tracks = [t for t in range(1, _num_audio + 1) if t not in _always_muted]
        _mix_indices = [t - 1 for t in _mix_obs_tracks]
        _label = f"Mix pistes {_mix_obs_tracks}"
        _log(
            f"Track {_audio_base_track} not in source (only {_num_audio} streams). "
            f"Mixing OBS tracks {_mix_obs_tracks} (excluding muted {sorted(_always_muted)}) → {_clean_vod.name}"
        )
        if callable(progress_cb):
            progress_cb("Préparation audio", 0, 100, f"{_label}…")
        ok = _create_mixed_vod(str(vod_path), _clean_vod, _mix_indices, _make_on_progress(_label))
        _log(f"Clean VOD mix ok={ok}")

    return _clean_vod if ok else None


def _generate_manifest_for_vod(
    root: Path,
    vod_path: Path,
    generate_subtitles: bool = True,
    use_transcript_for_selection: bool = False,
    progress_cb: Any | None = None,
    preset_id: str = "",
    subtitle_preset_id: str = "",
    subtitle_preset: dict[str, Any] | None = None,
) -> Path:
    cfg = _merge_subtitle_preset_into_config(_load_pipeline_config(root), subtitle_preset)
    manifest_path = _build_manifest_for_vod(
        root=root,
        vod_path=vod_path,
        cfg=cfg,
        generate_subtitles=generate_subtitles,
        use_transcript_for_selection=use_transcript_for_selection,
        progress_cb=progress_cb,
        preset_id=preset_id,
        subtitle_preset_id=subtitle_preset_id,
        log_cb=_log,
    )
    # Pre-create the clean VOD while the user is already waiting (avoids delay during Resolve build)
    try:
        _ensure_clean_vod(root, vod_path, cfg, progress_cb)
    except Exception as _exc:
        _log(f"clean_vod_precompute_error: {_exc}")
    return manifest_path


def _simple_tokenize(text: str) -> list[str]:
    return _batch_builder.simple_tokenize(text)


def _semantic_match_score(query: str, text: str) -> float:
    return _batch_builder.semantic_match_score(query, text)


def _load_transcript_entries(root: Path, source_path: str) -> list[dict[str, Any]]:
    return _batch_builder.load_transcript_entries(root, source_path)


def _filter_plans_by_transcript_query(root: Path, plans: list[ClipPlan], query: str, max_seconds: int) -> list[ClipPlan]:
    return _batch_builder.filter_plans_by_transcript_query(root, plans, query, max_seconds, _overlap_ratio_from_ranges)


def _parse_manifest(manifest_path: Path) -> tuple[str, list[ClipPlan]]:
    return _parse_manifest_impl(manifest_path)


def _walk_folder_clips(folder: Any) -> list[Any]:
    return _media_pool.walk_folder_clips(folder, _safe_call)


def _list_subtitle_template_candidates(media_pool: Any) -> list[str]:
    return _media_pool.list_subtitle_template_candidates(
        media_pool,
        _safe_call,
        (STANDALONE_CAPTION_TEMPLATE_NAME, STANDALONE_CAPTION_TEMPLATE_FALLBACK_NAME),
    )


def _find_media_pool_item_by_path(media_pool: Any, source_path: Path) -> Any | None:
    return _media_pool.find_media_pool_item_by_path(media_pool, source_path, _safe_call)


def _path_from_clip_properties(props: Any) -> str:
    return _media_pool.path_from_clip_properties(props)


def _source_path_from_resolve_clip(obj: Any) -> str:
    return _media_pool.source_path_from_resolve_clip(obj, _safe_call)


def _ensure_media_item(media_pool: Any, source_path: Path) -> Any | None:
    return _media_pool.ensure_media_item(media_pool, source_path, _safe_call)


def _ensure_media_item_with_status(media_pool: Any, source_path: Path) -> tuple[Any | None, str]:
    return _media_pool.ensure_media_item_with_status(media_pool, source_path, _safe_call)


def _append_clip_range(
    media_pool: Any,
    timeline: Any,
    media_item: Any,
    start_frame: int,
    end_frame: int,
    track_index: int = 1,
    record_frame: int = 0,
) -> bool:
    return _media_pool.append_clip_range(
        media_pool,
        timeline,
        media_item,
        start_frame,
        end_frame,
        track_index,
        record_frame,
        _safe_call,
    )


def _apply_item_transform(item: Any, props: dict[str, float]) -> None:
    _transforms.apply_item_transform(item, props, _safe_call)


def _force_item_normal_speed(item: Any) -> None:
    _timelines.force_item_normal_speed(item, _safe_call)


def _get_timeline_items_on_track(timeline: Any, track_index: int) -> list[Any]:
    return _timelines.get_timeline_items_on_track(timeline, track_index, _safe_call)


def _get_track_item_count(timeline: Any, track_type: str) -> int:
    return _timelines.get_track_item_count(timeline, track_type, _safe_call)


def _read_speed_props(item: Any) -> str:
    return _timelines.read_speed_props(item, _safe_call)


def _log_timeline_diagnostics(timeline: Any, plan: ClipPlan, expected_duration_s: float, mode: str) -> None:
    tname = str(_safe_call(timeline, "GetName", default="timeline"))
    video_count = _get_track_item_count(timeline, "video")
    audio_count = _get_track_item_count(timeline, "audio")
    subtitle_count = _get_track_item_count(timeline, "subtitle")
    first_item = None
    items_t1 = _get_timeline_items_on_track(timeline, 1)
    if items_t1:
        first_item = items_t1[0]
    if first_item is None:
        _log(
            f"timeline_diag name={tname} clip={plan.clip_id} mode={mode} expected_dur={expected_duration_s:.3f} "
            f"video_items={video_count} audio_items={audio_count} subtitle_items={subtitle_count} first_item=missing"
        )
        return
    s = _safe_call(first_item, "GetStart", default=None)
    e = _safe_call(first_item, "GetEnd", default=None)
    speed_bits = _read_speed_props(first_item)
    _log(
        f"timeline_diag name={tname} clip={plan.clip_id} mode={mode} expected_dur={expected_duration_s:.3f} "
        f"item_start={s} item_end={e} video_items={video_count} audio_items={audio_count} subtitle_items={subtitle_count} {speed_bits}"
    )


def _get_item_at_current_frame(timeline: Any, track_index: int) -> Any | None:
    return _timelines.get_item_at_current_frame(timeline, track_index, _safe_call)


def _get_first_item_on_track(timeline: Any, track_index: int) -> Any | None:
    return _timelines.get_first_item_on_track(timeline, track_index, _safe_call)


def _items_overlapping_frame_range(timeline: Any, track_index: int, start_frame: int, end_frame: int) -> list[Any]:
    return _timelines.items_overlapping_frame_range(timeline, track_index, start_frame, end_frame, _safe_call)


def _get_timeline_selected_range(timeline: Any) -> tuple[int, int] | None:
    return _timelines.get_timeline_selected_range(timeline, _safe_call)


def _read_item_transform(item: Any) -> dict[str, float]:
    return _transforms.read_item_transform(item, _safe_call)


def _apply_preset_to_selected_clip(resolve: Any, preset: dict[str, Any], scope_mode: str = "whole_clip") -> tuple[bool, str]:
    return _transforms.apply_preset_to_selected_clip(resolve, preset, scope_mode, _safe_call, _log)


def _selected_clip_subtitle_context(resolve: Any) -> tuple[bool, str, dict[str, Any]]:
    return _selected_clip.selected_clip_subtitle_context(resolve, _safe_call, _log, _fps_from_project, _source_fps_for_media_item)


def _load_audio_energy_for_silence_cut(
    root: Path,
    source_path: Path,
    cfg: dict[str, Any],
    cache: dict[str, tuple[list[tuple[float, float]], str]],
) -> tuple[list[tuple[float, float]], str, list[str]]:
    return _silence_cut.load_audio_energy_for_silence_cut(root, source_path, cfg, cache)


def _detect_audible_segments_for_silence_cut(
    energies: list[tuple[float, float]],
    clip_start: float,
    clip_end: float,
    cfg: dict[str, Any],
) -> tuple[list[tuple[float, float]], dict[str, float]]:
    return _silence_cut.detect_audible_segments_for_silence_cut(energies, clip_start, clip_end, cfg, _repo_root())


def _append_silence_cut_segment_with_preset(
    media_pool: Any,
    timeline: Any,
    media_item: Any,
    start_frame: int,
    end_frame: int,
    record_frame: int,
    preset: dict[str, Any],
) -> None:
    _timelines.append_silence_cut_segment_with_preset(
        media_pool,
        timeline,
        media_item,
        start_frame,
        end_frame,
        record_frame,
        preset,
        _safe_call,
        _apply_item_transform,
    )


def _create_silence_cut_timeline(
    root: Path,
    project: Any,
    media_pool: Any,
    source_path: Path,
    timeline_name: str,
    segments_seconds: list[tuple[float, float]],
    preset: dict[str, Any],
) -> tuple[Any | None, list[str]]:
    return _silence_cut.create_silence_cut_timeline(
        root,
        project,
        media_pool,
        source_path,
        timeline_name,
        segments_seconds,
        preset,
        _ensure_media_item,
        _fps_from_project,
        _source_fps_for_media_item,
        _delete_timeline_if_exists,
        _force_timeline_fps_60,
        _append_silence_cut_segment_with_preset,
        _safe_call,
    )


def _suffix_timeline_name(base_name: str, suffix: str = "__silence_cut") -> str:
    return _suffix_timeline_name_impl(base_name, suffix)


def _create_timeline_for_clip_with_preset(
    project: Any,
    media_pool: Any,
    name: str,
    media_item: Any,
    start_frame: int,
    end_frame: int,
    preset: dict[str, Any],
) -> Any | None:
    return _timelines.create_timeline_for_clip_with_preset(
        project,
        media_pool,
        name,
        media_item,
        start_frame,
        end_frame,
        preset,
        _safe_call,
        _log,
        _force_timeline_fps_60,
        _apply_item_transform,
    )


def _create_timeline_for_clip(media_pool: Any, name: str, media_item: Any, start_frame: int, end_frame: int) -> Any | None:
    return _timelines.create_timeline_for_clip(media_pool, name, media_item, start_frame, end_frame, _safe_call)


def _ensure_batch_folder(media_pool: Any, batch_id: str) -> Any:
    return _media_pool.ensure_batch_folder(media_pool, batch_id, _safe_call)


def _ensure_shorteditor_subfolder(media_pool: Any, subfolder_name: str) -> Any:
    return _media_pool.ensure_shorteditor_subfolder(media_pool, subfolder_name, _safe_call)


def _set_shorts_render_defaults(project: Any, output_dir: Path, timeline_name: str) -> None:
    _render_queue.set_shorts_render_defaults(project, output_dir, timeline_name, _safe_call)


def _ensure_vertical_project_settings(project: Any) -> None:
    _project_settings.ensure_vertical_project_settings(project, _safe_call)


def _ensure_playback_fps_60(project: Any) -> bool:
    return _project_settings.ensure_playback_fps_60(project, DEFAULT_FPS, _safe_call, _log)


def _force_timeline_fps_60(project: Any, timeline: Any) -> None:
    _project_settings.force_timeline_fps_60(project, timeline, _safe_call, _log)


def _apply_preview_safe_playback(project: Any) -> list[str]:
    return _project_settings.apply_preview_safe_playback(project, _safe_call, _log)


def _queue_render_job(project: Any, timeline: Any, output_dir: Path, preset_name: str) -> bool:
    return _render_queue.queue_render_job(project, timeline, output_dir, preset_name, _safe_call, _log)


def _collect_unique_media_items_from_timelines(timelines: list[Any]) -> list[Any]:
    return _render_queue.collect_unique_media_items_from_timelines(timelines, _safe_call)


def _find_timeline_by_name(project: Any, timeline_name: str) -> Any | None:
    return _timelines.find_timeline_by_name(project, timeline_name, _safe_call)


def _delete_timeline_if_exists(project: Any, media_pool: Any, timeline_name: str) -> None:
    _timelines.delete_timeline_if_exists(project, media_pool, timeline_name, _safe_call)


def _import_subtitles_to_timeline(
    project: Any,
    media_pool: Any,
    timeline: Any,
    subtitle_segments: list[dict[str, Any]],
    template_name: str = SUBTITLE_TEMPLATE_AUTO_LABEL,
    offset_ms: int = -500,
    subtitle_style: dict[str, Any] | None = None,
    timing_segments: list[dict[str, Any]] | None = None,
    subtitle_source_start: float = 0.0,
) -> tuple[bool, str]:
    return _textplus.import_subtitles_to_timeline(
        project,
        media_pool,
        timeline,
        subtitle_segments,
        _repo_root(),
        template_name,
        SUBTITLE_TEMPLATE_AUTO_LABEL,
        STANDALONE_CAPTION_TEMPLATE_NAME,
        STANDALONE_CAPTION_TEMPLATE_FALLBACK_NAME,
        offset_ms,
        subtitle_style,
        timing_segments,
        subtitle_source_start,
        _safe_call,
        _log,
        _coerce_float,
        _parse_fps_text,
    )


def _plan_key(plan: ClipPlan) -> str:
    return _plan_key_impl(plan)


def _safe_name_token(text: str, limit: int = 72) -> str:
    return _safe_name_token_impl(text, limit)


def _build_from_manifest(
    root: Path,
    project: Any,
    media_pool: Any,
    manifest_path: Path,
    output_dir: Path,
    preset_name: str,
    selected_preset: dict[str, Any],
    transcript_query: str,
    render_master: bool,
    queue_render: bool,
    detected_vod_path: Path | None = None,
    user_vod_dir: Path | None = None,
    require_subtitles: bool = False,
    subtitle_template_name: str = SUBTITLE_TEMPLATE_AUTO_LABEL,
    subtitle_offset_ms: int = -500,
    subtitle_style: dict[str, Any] | None = None,
    subtitle_captions_cfg: dict[str, Any] | None = None,
    progress_cb: Any | None = None,
) -> tuple[str, dict[str, ClipPlan], list[Any], list[str]]:
    _cfg = _load_pipeline_config(root)

    # Build a source_remap: original VOD → clean VOD with only the desired audio track.
    # ffmpeg stream-copies video + one audio stream so this finishes in seconds.
    _source_remap: dict[str, Path] | None = None
    _vod_for_clean: Path | None = detected_vod_path if (detected_vod_path and detected_vod_path.exists()) else None
    if _vod_for_clean is None:
        try:
            _mdata = _read_manifest_safe(manifest_path) or {}
            _fp = str((_mdata.get("meta") or {}).get("source_vod_path") or "")
            if not _fp:
                _vods = _mdata.get("source_vods") or []
                _fp = str(_vods[0]) if _vods else ""
            if _fp and Path(_fp).exists():
                _vod_for_clean = Path(_fp)
        except Exception:
            pass
    if _vod_for_clean is not None:
        _clean_vod = _ensure_clean_vod(root, _vod_for_clean, _cfg, progress_cb)
        if _clean_vod is not None:
            _source_remap = {str(_vod_for_clean).lower(): _clean_vod}
            _log(f"source_remap: {_vod_for_clean.name} → {_clean_vod.name}")

    def _create_timeline_with_mute(
        project: Any,
        media_pool: Any,
        name: str,
        media_item: Any,
        start_frame: int,
        end_frame: int,
        preset: dict[str, Any],
    ) -> Any | None:
        return _create_timeline_for_clip_with_preset(
            project, media_pool, name, media_item, start_frame, end_frame, preset,
        )

    deps = _BatchBuildDeps(
        log=_log,
        load_pipeline_config=_load_pipeline_config,
        transcript_path_for_vod=_transcript_path_for_vod,
        ensure_vertical_project_settings=_ensure_vertical_project_settings,
        ensure_batch_folder=_ensure_batch_folder,
        ensure_playback_fps_60=_ensure_playback_fps_60,
        fps_from_project=_fps_from_project,
        safe_int_from_project_setting=_safe_int_from_project_setting,
        ensure_media_item=_ensure_media_item,
        source_fps_for_media_item=_source_fps_for_media_item,
        delete_timeline_if_exists=_delete_timeline_if_exists,
        create_timeline_for_clip_with_preset=_create_timeline_with_mute,
        log_timeline_diagnostics=_log_timeline_diagnostics,
        import_subtitles_to_timeline=_import_subtitles_to_timeline,
        append_clip_range=_append_clip_range,
        queue_render_job=_queue_render_job,
        safe_call=_safe_call,
        default_fps=DEFAULT_FPS,
    )
    return _batch_builder.build_from_manifest(
        root,
        project,
        media_pool,
        manifest_path,
        output_dir,
        preset_name,
        selected_preset,
        transcript_query,
        render_master,
        queue_render,
        deps,
        _overlap_ratio_from_ranges,
        detected_vod_path=detected_vod_path,
        user_vod_dir=user_vod_dir,
        require_subtitles=require_subtitles,
        subtitle_template_name=subtitle_template_name,
        subtitle_offset_ms=subtitle_offset_ms,
        subtitle_style=subtitle_style,
        subtitle_captions_cfg=subtitle_captions_cfg,
        progress_cb=progress_cb,
        source_remap=_source_remap,
    )


def run() -> int:
    root = _repo_root()
    presets_data = _load_or_init_presets(root)
    _log(f"Starting Resolve batch script. Root={root}")
    resolve = None

    loader = _KirbyLoader(root, _log)
    loading_root = loader.root

    def set_loading(msg: str) -> None:
        nonlocal loading_root
        loader.set_loading(msg)
        loading_root = loader.root

    def set_loading_progress(step_label: str, percent: int | None = None, indeterminate: bool = False) -> None:
        nonlocal loading_root
        loader.set_progress(step_label, percent, indeterminate)
        loading_root = loader.root

    def set_loading_anim(name: str) -> None:
        loader.set_anim(name)

    set_loading_progress("Initialisation du loader", 0)
    set_loading("Chargement de l'API Resolve...")
    set_loading_progress("Chargement de l'API Resolve", 4)
    resolve = _load_resolve()
    set_loading_progress("API Resolve prête", 8)

    set_loading("Détection de la source VOD...")
    set_loading_progress("Détection de la source VOD", 10)
    auto_vod = _auto_detect_vod_path(resolve, root)
    if auto_vod is None:
        set_loading("Sélectionner le fichier VOD...")
        set_loading_progress("En attente de sélection VOD", 15)
        auto_vod = _prompt_vod_path_native(root / "input", parent=loading_root)
        loader.lift_focus()
        loading_root = loader.root
        _log("loader_focus_restored_after_picker")
    if auto_vod is None:
        loader.destroy()
        loading_root = loader.root
        raise RuntimeError("Aucune VOD sélectionnée. Sélectionne une VOD pour continuer.")

    manifest_result: dict[str, Any] = {"manifest": None, "error": None}
    used_manifest_fallback = False
    reopened_existing_manifest = False

    existing_manifest = _find_existing_manifest_for_vod(root, auto_vod)
    if existing_manifest is not None:
        set_loading("Ancien batch détecté...")
        set_loading_progress("Confirmation réouverture", 18)
        loader.lift_focus()
        loading_root = loader.root
        if _ask_reopen_existing_batch(existing_manifest, parent=loading_root):
            default_manifest = existing_manifest
            reopened_existing_manifest = True
            set_loading("Session existante rouverte...")
            set_loading_progress("Session existante", 92)
            _log(f"Reopened existing manifest for VOD: {default_manifest}")
        else:
            _log(f"Existing manifest ignored by user: {existing_manifest}")

    if not reopened_existing_manifest:
        set_loading("Génération du manifest...")
        set_loading_progress("Génération du manifest", 20)
        loader.start_phase_loop()

        def _manifest_worker() -> None:
            try:
                manifest_result["manifest"] = _generate_manifest_for_vod(
                    root,
                    auto_vod,
                    generate_subtitles=False,
                    use_transcript_for_selection=False,
                )
            except Exception as exc:
                manifest_result["error"] = {
                    "message": str(exc),
                    "traceback": traceback.format_exc(),
                }

        worker = threading.Thread(target=_manifest_worker, daemon=True)
        worker.start()
        pseudo_progress = 20
        while worker.is_alive():
            pseudo_progress = min(82, pseudo_progress + 1)
            set_loading_progress("Génération du manifest", pseudo_progress)
            loader.pump_once()
            loading_root = loader.root
            time.sleep(0.03)
        if manifest_result["error"] is not None:
            err = manifest_result["error"]
            _log(f"Manifest generation error: {err.get('message', err)}")
            _log(err.get("traceback", ""))
            fallback_manifest = _latest_manifest(root / "output" / "manifests")
            if fallback_manifest is None:
                loader.destroy()
                loading_root = loader.root
                raise RuntimeError(f"Échec de génération du manifest et aucun manifest de secours trouvé: {err.get('message', err)}")
            default_manifest = fallback_manifest
            used_manifest_fallback = True
            set_loading("Échec du manifest. Utilisation du dernier batch...")
            set_loading_progress("Utilisation du manifest de secours", 86)
            _log(f"Using fallback manifest: {default_manifest}")
        else:
            default_manifest = manifest_result["manifest"]
    set_loading("Manifest prêt !")
    set_loading_progress("Manifest prêt", 92)
    if loader.alive():
        set_loading_progress("Finalisation", 97)
        loader.final_dance_then_close()
        loader.pump_until_closed()
        loading_root = loader.root
    elif loading_root is not None:
        set_loading_progress("Terminé", 100)
        loader.destroy()
        loading_root = loader.root
    _log(f"Default manifest: {default_manifest}")

    project_manager = _safe_call(resolve, "GetProjectManager", required=True)
    project = _safe_call(project_manager, "GetCurrentProject", required=True)
    if project is None:
        raise RuntimeError("Aucun projet Resolve ouvert. Ouvre d'abord un projet.")

    media_pool = _safe_call(project, "GetMediaPool", required=True)
    if media_pool is None:
        raise RuntimeError("Impossible d'accéder au Media Pool.")

    session: dict[str, Any] = {
        "batch_id": None,
        "manifest": default_manifest,
        "plan_map": {},
        "detected_vod": auto_vod,
        "used_manifest_fallback": used_manifest_fallback,
        "reopened_existing_manifest": reopened_existing_manifest,
        "use_transcript_for_selection": False,
    }

    session_action_deps = _session_actions.SessionActionDeps(
        read_manifest_safe=_read_manifest_safe,
        default_subtitle_presets=_default_subtitle_presets,
        subtitle_style_from_preset=_subtitle_style_from_preset,
        merge_subtitle_preset_into_config=_merge_subtitle_preset_into_config,
        load_pipeline_config=_load_pipeline_config,
        manifest_has_valid_subtitles=_manifest_has_valid_subtitles,
        apply_preview_safe_playback=_apply_preview_safe_playback,
        transcript_path_for_vod=_transcript_path_for_vod,
        find_reusable_quality_manifest=_find_reusable_quality_manifest,
        generate_manifest_for_vod=_generate_manifest_for_vod,
        build_from_manifest=_build_from_manifest,
        log=_log,
    )

    def on_generate(params: dict[str, Any]) -> dict[str, Any] | str:
        return _session_actions.generate_session_batch(
            root,
            project,
            media_pool,
            session,
            default_manifest,
            presets_data,
            params,
            session_action_deps,
            DEFAULT_SUBTITLE_PRESET_ID,
            SUBTITLE_TEMPLATE_AUTO_LABEL,
        )

    def on_update(params: dict[str, Any]) -> dict[str, Any] | str:
        return _session_actions.update_session_composition(
            root,
            project,
            media_pool,
            session,
            default_manifest,
            presets_data,
            params,
            session_action_deps,
            DEFAULT_SUBTITLE_PRESET_ID,
            SUBTITLE_TEMPLATE_AUTO_LABEL,
        )

    _ask_user_inputs(default_manifest, presets_data, resolve, on_generate, on_update, session)

    _log("Resolve UI session closed.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(run())
    except Exception as exc:
        _log(f"FATAL: {exc}")
        raise
