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
from contextlib import redirect_stderr
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from datetime import datetime, timezone
import importlib

def _load_resolve() -> Any:
    # Strategy 1: direct module import (works on many installs)
    try:
        dvr_script = importlib.import_module("DaVinciResolveScript")
        resolve = dvr_script.scriptapp("Resolve")
        if resolve is not None:
            _log("Resolve loader: DaVinciResolveScript import OK")
            return resolve
    except Exception as exc:
        _log(f"Resolve loader strategy 1 failed: {exc}")

    # Strategy 2: Resolve-injected bmd global
    try:
        bmd_obj = globals().get("bmd")
        if bmd_obj is not None:
            resolve = bmd_obj.scriptapp("Resolve")
            if resolve is not None:
                _log("Resolve loader: bmd.scriptapp OK")
                return resolve
    except Exception as exc:
        _log(f"Resolve loader strategy 2 failed: {exc}")

    # Strategy 3: extend sys.path to common Windows scripting locations
    candidates = []
    appdata = os.environ.get("APPDATA", "")
    programdata = os.environ.get("PROGRAMDATA", "")
    programfiles = os.environ.get("PROGRAMFILES", "")
    if appdata:
        candidates.append(
            Path(appdata)
            / "Blackmagic Design"
            / "DaVinci Resolve"
            / "Support"
            / "Developer"
            / "Scripting"
            / "Modules"
        )
    if programdata:
        candidates.append(
            Path(programdata)
            / "Blackmagic Design"
            / "DaVinci Resolve"
            / "Support"
            / "Developer"
            / "Scripting"
            / "Modules"
        )
    if programfiles:
        candidates.append(
            Path(programfiles)
            / "Blackmagic Design"
            / "DaVinci Resolve"
            / "Developer"
            / "Scripting"
            / "Modules"
        )

    for p in candidates:
        try:
            if p.exists():
                if str(p) not in sys.path:
                    sys.path.append(str(p))
                dvr_script = importlib.import_module("DaVinciResolveScript")
                resolve = dvr_script.scriptapp("Resolve")
                if resolve is not None:
                    _log(f"Resolve loader: imported via path {p}")
                    return resolve
        except Exception as exc:
            _log(f"Resolve loader strategy 3 failed for {p}: {exc}")

    raise RuntimeError(
        "Could not load Resolve scripting API. In Resolve, enable Preferences > System > General > External Scripting = Local, then restart Resolve."
    )


def _safe_call(obj: Any, method_name: str, *args: Any, default: Any = None, required: bool = False) -> Any:
    attr = getattr(obj, method_name, None)
    _log(f"CALL {type(obj).__name__}.{method_name} callable={callable(attr)}")
    if not callable(attr):
        msg = f"Method not callable: {type(obj).__name__}.{method_name}"
        _log(msg)
        if required:
            raise RuntimeError(msg)
        return default
    try:
        out = attr(*args)
        _log(f"OK {type(obj).__name__}.{method_name} -> {type(out).__name__}")
        return out
    except Exception as exc:
        _log(f"ERR {type(obj).__name__}.{method_name}: {exc}")
        if required:
            raise
        return default


def _repo_root() -> Path:
    configured = _load_installed_config_root()
    if configured is not None:
        return configured
    script_path = _script_path()
    if script_path is not None:
        return script_path.parent.parent
    return Path.cwd()


def _log_path() -> Path:
    return Path.home() / "Desktop" / "short_editor_resolve.log"


def _log(message: str) -> None:
    line = f"[{datetime.now().isoformat(timespec='seconds')}] {message}\n"
    try:
        with _log_path().open("a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass


def _presets_path(root: Path) -> Path:
    return root / "config" / "resolve_presets.json"


def _default_presets() -> dict[str, Any]:
    return {
        "version": "1.0",
        "profiles": {
            "valo": {
                "label": "Valo",
                "active_preset": "VALO_FIXED_SPLIT_LEFTCAM_V1",
                "max_transcript_clip_seconds": 45,
            },
            "jeu": {
                "label": "Jeu",
                "active_preset": "GAME_STANDARD_V1",
                "max_transcript_clip_seconds": 45,
            },
            "react": {
                "label": "React",
                "active_preset": "REACT_STANDARD_V1",
                "max_transcript_clip_seconds": 45,
            },
        },
        "presets": {
            "VALO_FIXED_SPLIT_LEFTCAM_V1": {
                "name": "VALO Fixed Split Left Cam",
                "profile": "valo",
                "mode": "fixed_split",
                "layers_count": 2,
                "safe_padding": 0.06,
                "max_clip_seconds": 45,
                "gameplay": {
                    "zoom_x": 1.65,
                    "zoom_y": 1.65,
                    "pan": 0.0,
                    "tilt": 0.62,
                    "crop_top": 0.0,
                    "crop_bottom": 0.42,
                    "crop_left": 0.0,
                    "crop_right": 0.0,
                },
                "camera": {
                    "zoom_x": 3.2,
                    "zoom_y": 3.2,
                    "pan": 0.72,
                    "tilt": -0.82,
                    "crop_top": 0.0,
                    "crop_bottom": 0.0,
                    "crop_left": 0.0,
                    "crop_right": 0.0,
                },
            },
            "GAME_STANDARD_V1": {
                "name": "Game Standard",
                "profile": "jeu",
                "mode": "single",
                "layers_count": 1,
                "safe_padding": 0.04,
                "max_clip_seconds": 45,
                "single": {
                    "zoom_x": 1.0,
                    "zoom_y": 1.0,
                    "pan": 0.0,
                    "tilt": 0.0,
                    "crop_top": 0.0,
                    "crop_bottom": 0.0,
                    "crop_left": 0.0,
                    "crop_right": 0.0,
                },
            },
            "REACT_STANDARD_V1": {
                "name": "React Standard",
                "profile": "react",
                "mode": "single",
                "layers_count": 1,
                "safe_padding": 0.04,
                "max_clip_seconds": 45,
                "single": {
                    "zoom_x": 1.0,
                    "zoom_y": 1.0,
                    "pan": 0.0,
                    "tilt": 0.0,
                    "crop_top": 0.0,
                    "crop_bottom": 0.0,
                    "crop_left": 0.0,
                    "crop_right": 0.0,
                },
            },
        },
    }


def _load_or_init_presets(root: Path) -> dict[str, Any]:
    path = _presets_path(root)
    if not path.exists():
        data = _default_presets()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
        return data
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _save_presets(root: Path, data: dict[str, Any]) -> None:
    path = _presets_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def _assets_dir(root: Path) -> Path:
    return root / "resolve_integration" / "assets"


def _load_gif_frames(tk_mod: Any, gif_path: Path) -> list[Any]:
    frames: list[Any] = []
    if not gif_path.exists():
        return frames
    idx = 0
    while True:
        try:
            frame = tk_mod.PhotoImage(file=str(gif_path), format=f"gif -index {idx}")
            frames.append(frame)
            idx += 1
        except Exception:
            break
    return frames


def _load_pipeline_config(root: Path) -> dict[str, Any]:
    path = root / "config" / "pipeline.json"
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _load_installed_config_root() -> Path | None:
    cfg = _script_config_path()
    if cfg is None:
        return None
    if not cfg.exists():
        return None
    try:
        with cfg.open("r", encoding="utf-8") as f:
            data = json.load(f)
        root = Path(str(data.get("project_root", ""))).resolve()
        if root.exists():
            return root
    except Exception:
        return None
    return None


def _script_path() -> Path | None:
    raw = globals().get("__file__")
    if raw:
        return Path(str(raw)).resolve()
    argv0 = sys.argv[0] if sys.argv else ""
    if argv0:
        p = Path(argv0)
        if p.exists():
            return p.resolve()
    return None


def _script_config_path() -> Path | None:
    sp = _script_path()
    if sp is not None:
        return sp.with_name("short_editor_resolve_config.json")

    appdata = os.environ.get("APPDATA", "")
    if appdata:
        p = Path(appdata) / "Blackmagic Design" / "DaVinci Resolve" / "Support" / "Fusion" / "Scripts" / "Utility" / "short_editor_resolve_config.json"
        return p
    return None


def _latest_manifest(default_dir: Path) -> Path | None:
    files = sorted(default_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def _ask_user_inputs(
    default_manifest: Path | None,
    presets_data: dict[str, Any],
    resolve: Any,
    on_generate: Any,
    on_update: Any,
    session_ref: dict[str, Any],
) -> None:
    output_dir = _repo_root() / "output" / "resolve_renders"
    preset_name = "H264_Shorts_1080x1920_60fps"

    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox

        profiles = presets_data.get("profiles", {})
        presets = presets_data.get("presets", {})
        keys = ("zoom_x", "zoom_y", "pan", "tilt", "crop_top", "crop_bottom", "crop_left", "crop_right")

        colors = {
            "bg": "#E7ECFF",
            "panel": "#C9BCFF",
            "panel_alt": "#EFE6FF",
            "accent": "#6D4DFF",
            "accent_soft": "#B8A8FF",
            "ink": "#1E1E2A",
            "sun": "#FFD84D",
            "sun_soft": "#FFF3B3",
            "line": "#7E69D9",
        }

        state = {
            "output_dir": str(output_dir),
            "vod_dir": str((_repo_root() / "input").resolve()),
            "render_preset": preset_name,
            "profile": "valo",
            "preset_id": "VALO_FIXED_SPLIT_LEFTCAM_V1",
            "query": "",
            "render_master": False,
        }

        root = tk.Tk()
        compact_geometry = "1080x800"
        expanded_geometry = "1080x980"
        root.title("Short Editor // Y2K Batch Console")
        root.geometry(compact_geometry)
        root.configure(bg=colors["bg"])
        _log("UI window created OK")

        header = tk.Frame(root, bg=colors["accent"], bd=2, relief="raised")
        header.grid(row=0, column=0, columnspan=3, sticky="we", padx=10, pady=(10, 8))
        tk.Label(
            header,
            text="Short Editor XP // Batch Launcher",
            bg=colors["accent"],
            fg="#FFFFFF",
            font=("Segoe UI", 14, "bold"),
            padx=10,
            pady=8,
        ).pack(side="left")
        tk.Label(
            header,
            text="Valo / Jeu / React",
            bg=colors["accent"],
            fg=colors["sun_soft"],
            font=("Segoe UI", 10, "bold"),
            padx=10,
        ).pack(side="right")

        form = tk.LabelFrame(root, text="Batch Settings", bg=colors["panel_alt"], fg=colors["ink"], bd=2, relief="groove", padx=8, pady=8)
        form.grid(row=1, column=0, columnspan=3, sticky="we", padx=10, pady=(0, 8))

        def ui_button(parent: Any, text: str, cmd: Any, primary: bool = False) -> Any:
            return tk.Button(
                parent,
                text=text,
                command=cmd,
                bg=colors["accent"] if primary else colors["sun"],
                fg="#FFFFFF" if primary else colors["ink"],
                activebackground=colors["accent_soft"] if primary else colors["sun_soft"],
                activeforeground=colors["ink"],
                bd=2,
                relief="raised",
                padx=10,
                pady=4,
                font=("Segoe UI", 10, "bold"),
            )

        def make_label(text: str, r: int, c: int) -> None:
            tk.Label(form, text=text, bg=colors["panel_alt"], fg=colors["ink"], font=("Segoe UI", 10, "bold")).grid(row=r, column=c, sticky="w", padx=8, pady=6)

        make_label("Output Dir", 0, 0)
        output_var = tk.StringVar(value=state["output_dir"])
        tk.Entry(form, textvariable=output_var, width=80, bd=2, relief="sunken").grid(row=0, column=1, padx=8, pady=6, sticky="we")

        def browse_output() -> None:
            p = filedialog.askdirectory(title="Select render output folder", initialdir=output_var.get())
            if p:
                output_var.set(p)

        ui_button(form, "Browse", browse_output).grid(row=0, column=2, padx=8, pady=6)

        make_label("VOD Folder (fallback)", 1, 0)
        vod_dir_var = tk.StringVar(value=state["vod_dir"])
        tk.Entry(form, textvariable=vod_dir_var, width=80, bd=2, relief="sunken").grid(row=1, column=1, padx=8, pady=6, sticky="we")

        def browse_vod_dir() -> None:
            p = filedialog.askdirectory(title="Select VOD folder", initialdir=vod_dir_var.get())
            if p:
                vod_dir_var.set(p)

        ui_button(form, "Browse", browse_vod_dir).grid(row=1, column=2, padx=8, pady=6)

        make_label("Render Preset", 2, 0)
        render_var = tk.StringVar(value=state["render_preset"])
        tk.Entry(form, textvariable=render_var, width=40, bd=2, relief="sunken").grid(row=2, column=1, padx=8, pady=6, sticky="w")

        make_label("Batch Profile", 3, 0)
        profile_var = tk.StringVar(value="valo")
        profile_menu = tk.OptionMenu(form, profile_var, *["valo", "jeu", "react"])
        profile_menu.config(bg=colors["sun"], fg=colors["ink"], bd=2, relief="raised", activebackground=colors["sun_soft"]) 
        profile_menu.grid(row=3, column=1, padx=8, pady=6, sticky="w")

        make_label("Preset ID", 4, 0)
        preset_var = tk.StringVar(value="VALO_FIXED_SPLIT_LEFTCAM_V1")
        preset_menu = tk.OptionMenu(form, preset_var, *list(presets.keys()))
        preset_menu.config(bg=colors["sun"], fg=colors["ink"], bd=2, relief="raised", activebackground=colors["sun_soft"]) 
        preset_menu.grid(row=4, column=1, padx=8, pady=6, sticky="w")

        status_setter: dict[str, Any] = {"fn": None}

        def load_current_preset() -> None:
            pid = preset_var.get().strip()
            load_editor_from_preset(pid)
            fn = status_setter.get("fn")
            if callable(fn):
                fn(f"Preset loadé: {pid}", warnings=[])
            _log(f"Preset loaded: {pid}")

        ui_button(form, "Load Current", load_current_preset).grid(row=4, column=2, padx=8, pady=6, sticky="w")

        make_label("Transcript Query", 5, 0)
        query_var = tk.StringVar(value="")
        tk.Entry(form, textvariable=query_var, width=80, bd=2, relief="sunken").grid(row=5, column=1, padx=8, pady=6, sticky="we")

        master_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            form,
            text="Queue MASTER_REVIEW render",
            variable=master_var,
            bg=colors["panel_alt"],
            fg=colors["ink"],
            selectcolor=colors["sun_soft"],
            activebackground=colors["panel_alt"],
        ).grid(row=6, column=1, padx=8, pady=6, sticky="w")

        editor_wrap = tk.Frame(root, bg=colors["bg"])
        editor_wrap.grid(row=2, column=0, columnspan=3, padx=10, pady=8, sticky="nsew")
        editor_visible = tk.BooleanVar(value=False)
        editor_toggle_text = tk.StringVar(value="▸ Preset Editor")

        preset_toolbar = tk.Frame(editor_wrap, bg=colors["bg"])
        preset_toolbar.pack(anchor="w", fill="x", padx=0, pady=(0, 6))

        editor_toggle = ui_button(preset_toolbar, editor_toggle_text.get(), lambda: None)
        editor_toggle.configure(textvariable=editor_toggle_text)
        editor_toggle.pack(side="left", padx=(0, 6))

        detect_mode_var = tk.StringVar(value="Current Frame")
        detect_mode = tk.OptionMenu(preset_toolbar, detect_mode_var, "Current Frame", "First Clip")
        detect_mode.config(bg=colors["sun"], fg=colors["ink"], bd=2, relief="raised", activebackground=colors["sun_soft"])
        detect_mode.pack(side="left", padx=(0, 6))

        detect_mode_label = tk.Label(preset_toolbar, text="Detect: Current Frame", bg=colors["bg"], fg=colors["ink"], font=("Segoe UI", 9, "bold"))
        detect_mode_label.pack(side="left", padx=(0, 6))

        editor = tk.LabelFrame(editor_wrap, text="Preset Editor", bg=colors["panel"], fg=colors["ink"], padx=8, pady=8, bd=2, relief="groove")
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
        apply_scope_var = tk.StringVar(value="Whole Clip")
        preset_mode_var = tk.StringVar(value="single")
        mode_label_var = tk.StringVar(value="mode: single")

        tk.Label(editor_fields, textvariable=mode_label_var, bg=colors["panel"], fg=colors["ink"], font=("Segoe UI", 10, "bold")).grid(row=0, column=0, columnspan=4, sticky="w")

        def _slider_bounds(prop_key: str) -> tuple[float, float, float]:
            if prop_key.startswith("zoom"):
                return (0.1, 8.0, 0.01)
            if prop_key in ("pan", "tilt"):
                return (-1.0, 1.0, 0.01)
            # crop values are 0..1 in Resolve
            return (0.0, 1.0, 0.01)

        def _add_numeric_control(parent: Any, r: int, c: int, fk: str, key: str) -> None:
            field_vars[fk] = tk.StringVar(value="0")
            slider_vars[fk] = tk.DoubleVar(value=0.0)

            tk.Label(parent, text=key, bg=colors["panel"], fg=colors["ink"]).grid(row=r, column=c, sticky="e", padx=3)
            entry = tk.Entry(parent, textvariable=field_vars[fk], width=7, bd=2, relief="sunken")
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

        tk.Label(editor_fields, text="safe_padding", bg=colors["panel"], fg=colors["ink"]).grid(row=row, column=0, sticky="e")
        tk.Entry(editor_fields, textvariable=safe_padding_var, width=10, bd=2, relief="sunken").grid(row=row, column=1, sticky="w")
        tk.Label(editor_fields, text="layers_count", bg=colors["panel"], fg=colors["ink"]).grid(row=row, column=2, sticky="e")
        layers_spin = tk.Spinbox(editor_fields, from_=1, to=4, textvariable=layers_count_var, width=6)
        layers_spin.grid(row=row, column=3, sticky="w")

        row += 1
        tk.Label(editor_fields, text="apply_scope", bg=colors["panel"], fg=colors["ink"]).grid(row=row, column=0, sticky="e")
        apply_scope_menu = tk.OptionMenu(editor_fields, apply_scope_var, "Whole Clip", "Selected Range")
        apply_scope_menu.config(bg=colors["sun"], fg=colors["ink"], bd=2, relief="raised", activebackground=colors["sun_soft"])
        apply_scope_menu.grid(row=row, column=1, sticky="w")

        def refresh_preset_menu() -> None:
            menu = preset_menu["menu"]
            menu.delete(0, "end")
            for pid in presets.keys():
                menu.add_command(label=pid, command=lambda value=pid: preset_var.set(value))

        def load_editor_from_preset(pid: str) -> None:
            p = dict(presets.get(pid, {}))
            mode = str(p.get("mode", "single"))
            preset_mode_var.set(mode)
            mode_label_var.set(f"mode: {mode}")
            safe_padding_var.set(str(p.get("safe_padding", 0.04)))
            default_layers = 2 if mode == "fixed_split" else 1
            layers_count_var.set(str(int(p.get("layers_count", default_layers))))
            for group in ("single", "gameplay", "camera"):
                section = dict(p.get(group, {}))
                for key in keys:
                    fk = f"{group}.{key}"
                    v = float(section.get(key, 0.0))
                    field_vars[fk].set(str(v))
                    if fk in slider_vars:
                        slider_vars[fk].set(v)

        def detect_preset_from_timeline() -> None:
            project_manager = _safe_call(resolve, "GetProjectManager")
            project = _safe_call(project_manager, "GetCurrentProject") if project_manager else None
            if not project:
                set_status("Detect failed: no open project")
                return
            timeline = _safe_call(project, "GetCurrentTimeline")
            if not timeline:
                set_status("Detect failed: no active timeline")
                return

            mode_label = detect_mode_var.get().strip()
            mode = "current" if mode_label == "Current Frame" else "first"
            detect_mode_label.config(text=f"Detect: {mode_label}")
            if mode == "current":
                cam_item = _get_item_at_current_frame(timeline, 1)
                game_item = _get_item_at_current_frame(timeline, 2)
            else:
                cam_item = _get_first_item_on_track(timeline, 1)
                game_item = _get_first_item_on_track(timeline, 2)

            _log(f"Detect preset mode={mode} mapping camera->T1 gameplay->T2")

            if not cam_item:
                set_status("Detect failed: no clip on Track 1")
                return
            if not game_item:
                set_status("Detect failed: no clip on Track 2")
                return

            preset_mode_var.set("fixed_split")
            mode_label_var.set("mode: fixed_split")

            def _read_prop(item: Any, prop: str) -> float | None:
                v = _safe_call(item, "GetProperty", prop, default=None)
                if v is None:
                    all_props = _safe_call(item, "GetProperty", default={}) or {}
                    v = all_props.get(prop)
                try:
                    return float(v)
                except Exception:
                    return None

            key_map = {
                "zoom_x": "ZoomX",
                "zoom_y": "ZoomY",
                "pan": "Pan",
                "tilt": "Tilt",
                "crop_top": "CropTop",
                "crop_bottom": "CropBottom",
                "crop_left": "CropLeft",
                "crop_right": "CropRight",
            }

            for key in keys:
                fk_cam = f"camera.{key}"
                fk_game = f"gameplay.{key}"
                rk = key_map[key]
                cam_v = _read_prop(cam_item, rk)
                game_v = _read_prop(game_item, rk)
                is_primary = key in ("zoom_x", "zoom_y", "pan", "tilt")

                if cam_v is not None and (is_primary or key.startswith("crop")):
                    if fk_cam in field_vars:
                        field_vars[fk_cam].set(f"{cam_v:.3f}")
                    if fk_cam in slider_vars:
                        slider_vars[fk_cam].set(cam_v)
                if game_v is not None and (is_primary or key.startswith("crop")):
                    if fk_game in field_vars:
                        field_vars[fk_game].set(f"{game_v:.3f}")
                    if fk_game in slider_vars:
                        slider_vars[fk_game].set(game_v)

            set_status("Detected preset from active timeline (track1=camera, track2=gameplay)")

        ui_button(preset_toolbar, "Detect Preset", detect_preset_from_timeline).pack(side="left", padx=(0, 6))

        def preset_from_editor(base: dict[str, Any]) -> dict[str, Any]:
            out = dict(base)
            out["mode"] = preset_mode_var.get().strip() or "single"
            try:
                out["layers_count"] = max(1, min(4, int(float(layers_count_var.get().strip()))))
            except Exception:
                out["layers_count"] = 2 if out["mode"] == "fixed_split" else 1
            for group in ("single", "gameplay", "camera"):
                out[group] = {}
                for key in keys:
                    raw = field_vars[f"{group}.{key}"].get().strip()
                    try:
                        out[group][key] = float(raw)
                    except Exception:
                        out[group][key] = 0.0
            try:
                out["safe_padding"] = float(safe_padding_var.get().strip())
            except Exception:
                out["safe_padding"] = 0.04
            return out

        status_var = tk.StringVar(value="Ready")
        last_warnings: list[str] = []

        def open_warnings_window() -> None:
            if not last_warnings:
                return
            top = tk.Toplevel(root)
            top.title("Batch Warnings")
            top.geometry("980x420")
            top.configure(bg=colors["panel_alt"])

            tk.Label(top, text=f"{len(last_warnings)} warning(s)", bg=colors["panel_alt"], fg=colors["ink"], font=("Segoe UI", 10, "bold"), anchor="w").pack(fill="x", padx=10, pady=(10, 4))

            wrap = tk.Frame(top, bg=colors["panel_alt"])
            wrap.pack(fill="both", expand=True, padx=10, pady=(0, 10))
            scroll = tk.Scrollbar(wrap, orient="vertical")
            text = tk.Text(wrap, yscrollcommand=scroll.set, wrap="word", bg="#FFFFFF", fg=colors["ink"], bd=2, relief="sunken", font=("Consolas", 10))
            scroll.config(command=text.yview)
            scroll.pack(side="right", fill="y")
            text.pack(side="left", fill="both", expand=True)

            for i, w in enumerate(last_warnings, start=1):
                text.insert("end", f"{i}. {w}\n")
            text.config(state="disabled")

        def set_status(message: str, warnings: list[str] | None = None) -> None:
            nonlocal last_warnings
            if warnings is not None:
                last_warnings = list(warnings)
            status_var.set(message)
            status_text.config(state="normal")
            status_text.delete("1.0", "end")
            status_text.insert("1.0", message)
            status_text.tag_remove("clickable_warning", "1.0", "end")
            if last_warnings:
                m = re.search(r"\(\d+\s+warnings\)", message)
                if m:
                    status_text.tag_add("clickable_warning", f"1.0+{m.start()}c", f"1.0+{m.end()}c")
            status_text.config(state="disabled")

        status_setter["fn"] = set_status

        def open_rate_batch_window() -> None:
            manifest_value = session_ref.get("manifest") or default_manifest
            if not manifest_value:
                set_status("Noter le batch indisponible: aucun manifest")
                return
            manifest_path = Path(manifest_value)
            if not manifest_path.exists():
                set_status("Noter le batch indisponible: manifest introuvable")
                return
            try:
                with manifest_path.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                clips = data.get("clips", []) if isinstance(data, dict) else []
                batch_id = str(data.get("batch_id", manifest_path.stem))
            except Exception as exc:
                set_status(f"Noter le batch indisponible: {exc}")
                return

            top = tk.Toplevel(root)
            top.title("Noter le batch")
            top.geometry("980x620")
            top.configure(bg=colors["panel_alt"])
            try:
                top.lift()
                top.focus_force()
            except Exception:
                pass

            tk.Label(top, text=f"Batch: {batch_id}", bg=colors["panel_alt"], fg=colors["ink"], font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=10, pady=(10, 2))
            search_var = tk.StringVar(value="")
            tk.Entry(top, textvariable=search_var, width=80, bd=2, relief="sunken").pack(anchor="w", padx=10, pady=(0, 8))

            wrap = tk.Frame(top, bg=colors["panel_alt"])
            wrap.pack(fill="both", expand=True, padx=10, pady=(0, 8))
            canvas = tk.Canvas(wrap, bg=colors["panel_alt"], highlightthickness=0)
            scroll = tk.Scrollbar(wrap, orient="vertical", command=canvas.yview)
            canvas.configure(yscrollcommand=scroll.set)
            scroll.pack(side="right", fill="y")
            canvas.pack(side="left", fill="both", expand=True)
            rows = tk.Frame(canvas, bg=colors["panel_alt"])
            rows_window = canvas.create_window((0, 0), window=rows, anchor="nw")

            rows.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
            canvas.bind("<Configure>", lambda e: canvas.itemconfigure(rows_window, width=e.width))

            ratings: dict[str, tk.IntVar] = {}
            indexed_rows: list[tuple[Any, str]] = []

            def draw_stars(parent: Any, rating_var: Any) -> None:
                buttons: list[Any] = []

                def refresh(v: int) -> None:
                    for idx, btn in enumerate(buttons, start=1):
                        btn.configure(text=("★" if idx <= v else "☆"))

                def set_v(v: int) -> None:
                    rating_var.set(v)
                    refresh(v)

                for i in range(1, 6):
                    b = tk.Button(parent, text="☆", bg=colors["sun_soft"], fg=colors["ink"], bd=1, relief="raised", padx=2, pady=0, command=lambda x=i: set_v(x))
                    b.pack(side="left", padx=1)
                    buttons.append(b)
                refresh(int(rating_var.get()))

            for i, c in enumerate(clips):
                clip_id = str(c.get("clip_id", f"clip_{i}"))
                display_name = str(c.get("display_name", clip_id))
                timeline_label = f"{batch_id}__{display_name}"
                seed = str(c.get("seed_type", ""))
                reason = str(c.get("reason", ""))
                matched_terms = ""
                for part in reason.split(";"):
                    p = part.strip()
                    if p.startswith("matched="):
                        matched_terms = p.replace("matched=", "").strip()
                        break
                if not matched_terms and "transcript_discovery" in reason:
                    matched_terms = "transcript"
                row = tk.Frame(rows, bg=colors["panel_alt"], bd=1, relief="groove")
                row.pack(fill="x", padx=2, pady=2)
                tk.Label(row, text=timeline_label[:54], width=54, anchor="w", bg=colors["panel_alt"], fg=colors["ink"]).pack(side="left", padx=4)
                tk.Label(row, text=seed, width=16, anchor="w", bg=colors["panel_alt"], fg=colors["ink"]).pack(side="left", padx=4)
                tk.Label(row, text=(matched_terms or "-"), width=40, anchor="w", bg=colors["panel_alt"], fg=colors["ink"]).pack(side="left", padx=4)
                rwrap = tk.Frame(row, bg=colors["panel_alt"])
                rwrap.pack(side="right", padx=8)
                ratings[clip_id] = tk.IntVar(value=3)
                draw_stars(rwrap, ratings[clip_id])
                indexed_rows.append((row, f"{timeline_label} {display_name} {clip_id} {seed} {reason} {matched_terms}".lower()))

            def apply_filter(*_args: Any) -> None:
                q = search_var.get().strip().lower()
                for row, text_blob in indexed_rows:
                    if not q or q in text_blob:
                        row.pack(fill="x", padx=2, pady=2)
                    else:
                        row.pack_forget()

            search_var.trace_add("write", apply_filter)

            def save_feedback_and_learn() -> None:
                try:
                    root_dir = _repo_root()
                    root_str = str(root_dir)
                    if root_str not in sys.path:
                        sys.path.insert(0, root_str)
                    from short_editor.feedback import enrich_lexicon_from_ratings, save_batch_ratings

                    rows_out: list[dict[str, str]] = []
                    for c in clips:
                        clip_id = str(c.get("clip_id", ""))
                        rows_out.append(
                            {
                                "batch_id": batch_id,
                                "clip_id": clip_id,
                                "rating": str(int(ratings.get(clip_id).get() if clip_id in ratings else 3)),
                                "seed_type": str(c.get("seed_type", "")),
                                "reason": str(c.get("reason", "")),
                                "start_seconds": str(c.get("start_seconds", "")),
                                "end_seconds": str(c.get("end_seconds", "")),
                                "notes": "",
                            }
                        )

                    latest, history = save_batch_ratings(batch_id, rows_out, root_dir / "feedback")

                    transcript_entries: list[dict] = []
                    if clips:
                        src = str(clips[0].get("source_path", ""))
                        if src:
                            t_path = root_dir / "output" / "transcripts" / f"{Path(src).stem}.json"
                            if t_path.exists():
                                with t_path.open("r", encoding="utf-8") as f:
                                    tdata = json.load(f)
                                transcript_entries = tdata.get("entries", []) if isinstance(tdata, dict) else []
                    enrich_lexicon_from_ratings(root_dir / "config" / "transcript_lexicon_user.json", rows_out, transcript_entries)
                    set_status(f"Feedback sauvegarde: {latest.name} | historique: {history.name}")
                    top.destroy()
                except Exception as exc:
                    _log(f"rating_save_failed: {exc}")
                    set_status(f"Feedback error: {exc}")

            controls = tk.Frame(top, bg=colors["panel_alt"])
            controls.pack(fill="x", padx=10, pady=(0, 10))
            ui_button(controls, "Valider et apprendre", save_feedback_and_learn, primary=True).pack(side="right", padx=6)
            ui_button(controls, "Fermer", top.destroy, primary=False).pack(side="right", padx=6)

        def save_overwrite() -> None:
            pid = preset_var.get().strip()
            if not pid:
                return
            base = dict(presets.get(pid, {}))
            if not base:
                base = {"name": pid, "profile": profile_var.get().strip(), "mode": "single", "max_clip_seconds": 45}
            presets[pid] = preset_from_editor(base)
            presets_data["presets"] = presets
            profiles.setdefault(profile_var.get().strip(), {})["active_preset"] = pid
            _save_presets(_repo_root(), presets_data)
            messagebox.showinfo("Short Editor", f"Preset saved: {pid}")

        def delete_selected_preset() -> None:
            pid = preset_var.get().strip()
            if not pid or pid not in presets:
                return
            if len(presets) <= 1:
                messagebox.showwarning("Short Editor", "Cannot delete the last preset.")
                return
            confirmed = messagebox.askyesno("Delete preset", f"Delete preset '{pid}' permanently?")
            if not confirmed:
                return

            deleted_profile = str(presets.get(pid, {}).get("profile", "")).strip()
            del presets[pid]

            replacement = ""
            for cand_id, cand_data in presets.items():
                if str(cand_data.get("profile", "")).strip() == deleted_profile:
                    replacement = cand_id
                    break
            if not replacement:
                replacement = next(iter(presets.keys()))

            for profile_name, profile_data in profiles.items():
                if profile_data.get("active_preset") == pid:
                    profile_data["active_preset"] = replacement
                if profile_name == deleted_profile and not profile_data.get("active_preset"):
                    profile_data["active_preset"] = replacement

            presets_data["presets"] = presets
            _save_presets(_repo_root(), presets_data)
            refresh_preset_menu()
            preset_var.set(replacement)
            load_editor_from_preset(replacement)
            set_status(f"Deleted preset: {pid}. Active preset: {replacement}")

        def apply_to_selected_clip_now() -> None:
            pid = preset_var.get().strip()
            selected_preset = dict((presets_data.get("presets", {}) or {}).get(pid, {}))
            if not selected_preset:
                set_status(f"Preset not found: {pid}")
                return
            scope_mode = "selected_range" if apply_scope_var.get().strip() == "Selected Range" else "whole_clip"
            ok, msg = _apply_preset_to_selected_clip(resolve, selected_preset, scope_mode=scope_mode)
            set_status(msg)
            if ok:
                _log(f"Apply to selected clip success: preset={pid} scope={scope_mode}")
            else:
                _log(f"Apply to selected clip failed: preset={pid} scope={scope_mode} msg={msg}")

        def save_as_new() -> None:
            top = tk.Toplevel(root)
            top.title("Save preset as")
            top.configure(bg=colors["panel_alt"])
            tk.Label(top, text="New Preset ID", bg=colors["panel_alt"], fg=colors["ink"], font=("Segoe UI", 10, "bold")).grid(row=0, column=0, padx=8, pady=8)
            new_id_var = tk.StringVar(value=preset_var.get().strip() + "_V2")
            tk.Entry(top, textvariable=new_id_var, width=36, bd=2, relief="sunken").grid(row=0, column=1, padx=8, pady=8)

            def do_save() -> None:
                nid = new_id_var.get().strip()
                if not nid:
                    return
                base = dict(presets.get(preset_var.get().strip(), {}))
                if not base:
                    base = {"name": nid, "profile": profile_var.get().strip(), "mode": "single", "max_clip_seconds": 45}
                new_preset = preset_from_editor(base)
                new_preset["name"] = nid
                presets[nid] = new_preset
                presets_data["presets"] = presets
                profiles.setdefault(profile_var.get().strip(), {})["active_preset"] = nid
                _save_presets(_repo_root(), presets_data)
                preset_var.set(nid)
                refresh_preset_menu()
                top.destroy()
                messagebox.showinfo("Short Editor", f"Preset saved as: {nid}")

            ui_button(top, "Save", do_save).grid(row=1, column=1, sticky="e", padx=8, pady=8)

        ui_button(editor_fields, "Save", save_overwrite).grid(row=row + 1, column=1, padx=6, pady=8)
        ui_button(editor_fields, "Save As", save_as_new).grid(row=row + 1, column=2, padx=6, pady=8)
        ui_button(editor_fields, "Delete Preset", delete_selected_preset).grid(row=row + 1, column=3, padx=6, pady=8)
        ui_button(editor_fields, "Apply to Selected Clip", apply_to_selected_clip_now, primary=False).grid(row=row + 2, column=0, columnspan=2, padx=6, pady=8, sticky="w")

        load_editor_from_preset(preset_var.get().strip())

        status_text = tk.Text(root, height=1, bg=colors["sun_soft"], fg=colors["ink"], bd=1, relief="sunken", wrap="none", cursor="arrow", font=("Segoe UI", 9))
        status_text.grid(row=4, column=0, columnspan=3, sticky="we", padx=10, pady=(0, 8))
        status_text.tag_configure("clickable_warning", foreground="#1D47C8", underline=1)
        status_text.tag_bind("clickable_warning", "<Button-1>", lambda _e: open_warnings_window())
        status_text.tag_bind("clickable_warning", "<Enter>", lambda _e: status_text.config(cursor="hand2"))
        status_text.tag_bind("clickable_warning", "<Leave>", lambda _e: status_text.config(cursor="arrow"))
        set_status("Ready")

        def toggle_editor() -> None:
            if editor_visible.get():
                editor.pack_forget()
                editor_visible.set(False)
                editor_toggle_text.set("▸ Preset Editor")
                root.geometry(compact_geometry)
            else:
                editor.pack(fill="both", expand=True)
                editor_visible.set(True)
                editor_toggle_text.set("▾ Preset Editor")
                root.geometry(expanded_geometry)

        editor_toggle.configure(command=toggle_editor)

        def collect_params() -> dict[str, Any]:
            return {
                "output": output_var.get().strip(),
                "vod_dir": vod_dir_var.get().strip(),
                "render_preset": render_var.get().strip() or "H264_Shorts_1080x1920_60fps",
                "profile": profile_var.get().strip() or "valo",
                "preset_id": preset_var.get().strip() or "VALO_FIXED_SPLIT_LEFTCAM_V1",
                "query": query_var.get().strip(),
                "render_master": bool(master_var.get()),
                "strict_manifest": False,
                "require_subtitles": False,
            }

        def run_now(strict_manifest: bool = False, require_subtitles: bool = False) -> None:
            params = collect_params()
            params["strict_manifest"] = bool(strict_manifest)
            params["require_subtitles"] = bool(require_subtitles)
            if require_subtitles:
                set_status("Generating batch with auto subtitles...", warnings=[])
            else:
                set_status("Generating batch (fast, no subtitles)...", warnings=[])
            root.update_idletasks()
            result = on_generate(params)
            should_open_rating = False
            if isinstance(result, dict):
                msg = str(result.get("message", "Done"))
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
            set_status("Updating composition...", warnings=[])
            root.update_idletasks()
            result = on_update(params)
            if isinstance(result, dict):
                set_status(str(result.get("message", "Done")), list(result.get("warnings", []) or []))
            else:
                set_status(str(result), warnings=[])

        footer = tk.Frame(root, bg=colors["bg"], bd=0)
        footer.grid(row=3, column=0, columnspan=3, sticky="we", padx=10, pady=(2, 12))
        ui_button(footer, "Noter le batch", open_rate_batch_window, primary=False).pack(side="left", padx=6)
        ui_button(footer, "Generate + Auto Subtitles (Quality)", run_now_quality, primary=True).pack(side="right", padx=6)
        ui_button(footer, "Generate Batch (Fast)", run_now, primary=True).pack(side="right", padx=6)
        ui_button(footer, "Update Composition (Batch)", update_now, primary=False).pack(side="right", padx=6)
        ui_button(footer, "Cancel", root.destroy, primary=False).pack(side="right", padx=6)

        root.columnconfigure(1, weight=1)
        root.rowconfigure(2, weight=1)
        form.columnconfigure(1, weight=1)
        root.mainloop()

    except Exception as exc:
        _log(f"UI ERROR: {exc}")
        raise RuntimeError(f"UI failed to open: {exc}")


def _safe_int_from_project_setting(project: Any, key: str, fallback: int) -> int:
    value = project.GetSetting(key)
    try:
        return int(float(value))
    except Exception:
        return fallback


def _fps_from_project(project: Any) -> int:
    fps = _safe_int_from_project_setting(project, "timelineFrameRate", 60)
    if fps <= 0:
        return 60
    return fps


@dataclass
class ClipPlan:
    clip_id: str
    display_name: str
    source_path: str
    start_seconds: float
    end_seconds: float
    seed_type: str
    subtitle_path: str = ""


def _overlap_ratio_from_ranges(a_start: float, a_end: float, b_start: float, b_end: float) -> float:
    left = max(a_start, b_start)
    right = min(a_end, b_end)
    if right <= left:
        return 0.0
    inter = right - left
    shortest = max(0.001, min(a_end - a_start, b_end - b_start))
    return inter / shortest


def _assign_simple_display_names_dict(clips: list[dict[str, Any]]) -> None:
    chapter_idx = 1
    auto_idx = 1
    for c in clips:
        if str(c.get("seed_type", "")) == "chapter":
            c["display_name"] = f"Chapitre {chapter_idx}"
            chapter_idx += 1
        else:
            c["display_name"] = f"Auto {auto_idx}"
            auto_idx += 1


def _select_non_overlapping_fallback(existing: list[dict[str, float]], candidates: list[dict[str, float]], needed: int) -> list[dict[str, float]]:
    if needed <= 0:
        return []
    selected: list[dict[str, float]] = []
    for c in candidates:
        c_start = float(c["start_seconds"])
        c_end = float(c["end_seconds"])
        too_close = any(
            _overlap_ratio_from_ranges(c_start, c_end, float(e["start_seconds"]), float(e["end_seconds"])) > 0.4
            for e in existing
        )
        too_close = too_close or any(
            _overlap_ratio_from_ranges(c_start, c_end, float(s["start_seconds"]), float(s["end_seconds"])) > 0.4
            for s in selected
        )
        if too_close:
            continue
        selected.append(c)
        if len(selected) >= needed:
            break
    return selected


def _auto_detect_vod_path(resolve: Any, root: Path) -> Path | None:
    project_manager = _safe_call(resolve, "GetProjectManager")
    project = _safe_call(project_manager, "GetCurrentProject") if project_manager else None
    if not project:
        return None

    # Strategy 1: current timeline video item
    timeline = _safe_call(project, "GetCurrentTimeline")
    if timeline:
        item = _safe_call(timeline, "GetCurrentVideoItem")
        if item:
            props = _safe_call(item, "GetClipProperty", default={}) or {}
            fp = str(props.get("File Path") or "")
            if fp and Path(fp).exists():
                _log(f"Auto VOD detect: current timeline clip {fp}")
                return Path(fp)

    # Strategy 2: selected clips in current media folder (if API available)
    media_pool = _safe_call(project, "GetMediaPool")
    if media_pool:
        selected = _safe_call(media_pool, "GetSelectedClips", default=[])
        if selected:
            first = selected[0]
            props = _safe_call(first, "GetClipProperty", default={}) or {}
            fp = str(props.get("File Path") or "")
            if fp and Path(fp).exists():
                _log(f"Auto VOD detect: selected media clip {fp}")
                return Path(fp)

    # Strategy 3: if exactly one input VOD exists, use it
    inputs = sorted((root / "input").glob("*.mp4"))
    if len(inputs) == 1:
        _log(f"Auto VOD detect: single input file {inputs[0]}")
        return inputs[0]
    return None


def _prompt_vod_path_native(default_dir: Path, parent: Any | None = None) -> Path | None:
    try:
        import tkinter as tk
        from tkinter import filedialog

        if parent is not None:
            chosen = filedialog.askopenfilename(
                title="Select VOD MP4",
                initialdir=str(default_dir),
                filetypes=[("MP4", "*.mp4")],
                parent=parent,
            )
        else:
            root = tk.Tk()
            root.withdraw()
            chosen = filedialog.askopenfilename(
                title="Select VOD MP4",
                initialdir=str(default_dir),
                filetypes=[("MP4", "*.mp4")],
            )
            root.destroy()
        if chosen:
            return Path(chosen)
    except Exception as exc:
        _log(f"VOD picker failed: {exc}")
    return None


def _generate_manifest_for_vod(root: Path, vod_path: Path, generate_subtitles: bool = True) -> Path:
    # Resolve scripts run from external script folders; ensure project root is importable.
    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)

    from short_editor.clip_builder import (
        build_chapter_candidates_with_skips,
        compute_quota,
        discover_fallback_candidates,
        tag_overflow,
    )
    from short_editor.ingest import probe_vod
    from short_editor.subtitles import generate_srt_for_clip
    from short_editor.transcription import ensure_transcript

    cfg = _load_pipeline_config(root)
    manifest = probe_vod(vod_path)
    chapter_clips, chapter_skips = build_chapter_candidates_with_skips(manifest, cfg)
    manifest_warnings = [f"{vod_path.name}: {msg}" for msg in chapter_skips]

    _, target_quota, max_quota = compute_quota(manifest.duration_seconds, cfg["quota"])
    selected: list[dict[str, Any]] = []
    for c in chapter_clips:
        selected.append(c.to_dict())

    if len(selected) < target_quota:
        fallback = [c.to_dict() for c in discover_fallback_candidates(manifest, cfg, root / "work")]
        needed = max(0, target_quota - len(selected))
        selected.extend(_select_non_overlapping_fallback(selected, fallback, needed))

    batch_id = f"batch_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    clip_objs = []
    for i, c in enumerate(selected):
        c["clip_id"] = f"{vod_path.stem}__{c['clip_id']}"
        c["overflow"] = i >= max_quota
        c["subtitle_path"] = ""
        clip_objs.append(c)
    _assign_simple_display_names_dict(clip_objs)

    captions_cfg = cfg.get("captions", {})
    captions_enabled = bool(captions_cfg.get("enabled", True)) and bool(generate_subtitles)
    if captions_enabled:
        def _generate_subtitles_once() -> int:
            _log(f"subtitle_generation_start vod={vod_path}")
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                with redirect_stderr(io.StringIO()):
                    transcript_path = ensure_transcript(vod_path, cfg, root / "output" / "transcripts")
                    _log(f"transcript_ok vod={vod_path} transcript={transcript_path}")
                    subtitle_dir = root / "output" / "subtitles" / batch_id
                    subtitles_generated_local = 0
                    for c in clip_objs:
                        ok = generate_srt_for_clip(
                            transcript_path,
                            float(c.get("start_seconds", 0.0)),
                            float(c.get("end_seconds", 0.0)),
                            subtitle_dir / f"{c['clip_id']}.srt",
                            captions_cfg,
                        )
                        if ok:
                            c["subtitle_path"] = str((subtitle_dir / f"{c['clip_id']}.srt").resolve())
                            subtitles_generated_local += 1
                    return subtitles_generated_local

        try:
            subtitles_generated = _generate_subtitles_once()
            _log(f"subtitle_generation_count={subtitles_generated}/{len(clip_objs)} vod={vod_path.name}")
            if subtitles_generated == 0 and clip_objs:
                manifest_warnings.append(f"{vod_path.name}: subtitle generation returned 0 files for {len(clip_objs)} clips")
        except Exception as exc:
            msg = str(exc)
            retriable = "returned a result with an exception set" in msg or "PyCapsule_GetPointer" in msg
            if retriable:
                _log(f"subtitle_generation_retry_after_runtime_error vod={vod_path.name} err={msg}")
                try:
                    subtitles_generated = _generate_subtitles_once()
                    _log(f"subtitle_generation_count={subtitles_generated}/{len(clip_objs)} vod={vod_path.name} retry=1")
                    if subtitles_generated == 0 and clip_objs:
                        manifest_warnings.append(f"{vod_path.name}: subtitle generation returned 0 files for {len(clip_objs)} clips")
                except Exception as exc_retry:
                    _log(f"subtitle_generation_error vod={vod_path.name} err={exc_retry}")
                    manifest_warnings.append(f"{vod_path.name}: subtitle generation failed: {exc_retry}")
            else:
                _log(f"subtitle_generation_error vod={vod_path.name} err={exc}")
                manifest_warnings.append(f"{vod_path.name}: subtitle generation failed: {exc}")
    else:
        _log(f"subtitle_generation_skipped vod={vod_path.name} reason=disabled_for_this_manifest")

    out = {
        "batch_id": batch_id,
        "source_vods": [str(vod_path)],
        "clips": clip_objs,
        "pipeline_version": cfg.get("pipeline_version", "0.1.0"),
        "warnings": manifest_warnings,
        "quota_summary": [
            {
                "vod": vod_path.name,
                "target_quota": target_quota,
                "max_quota": max_quota,
                "chapter_used": len([c for c in clip_objs if c.get("seed_type") == "chapter"]),
                "fallback_added": len([c for c in clip_objs if c.get("seed_type") != "chapter"]),
                "total_selected": len(clip_objs),
            }
        ],
    }

    out_dir = root / "output" / "manifests"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{batch_id}.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
        f.write("\n")
    _log(f"Auto manifest generated: {out_path}")
    return out_path


def _simple_tokenize(text: str) -> list[str]:
    return [t for t in "".join(ch.lower() if ch.isalnum() else " " for ch in text).split() if t]


def _semantic_match_score(query: str, text: str) -> float:
    q = set(_simple_tokenize(query))
    t = set(_simple_tokenize(text))
    if not q or not t:
        return 0.0
    inter = len(q.intersection(t))
    union = len(q.union(t))
    return inter / max(1, union)


def _load_transcript_entries(root: Path, source_path: str) -> list[dict[str, Any]]:
    transcript_dir = root / "output" / "transcripts"
    source_stem = Path(source_path).stem
    transcript_file = transcript_dir / f"{source_stem}.json"
    if not transcript_file.exists():
        return []
    try:
        with transcript_file.open("r", encoding="utf-8") as f:
            data = json.load(f)
        entries = data.get("entries", [])
        return entries if isinstance(entries, list) else []
    except Exception:
        return []


def _filter_plans_by_transcript_query(root: Path, plans: list[ClipPlan], query: str, max_seconds: int) -> list[ClipPlan]:
    if not query.strip():
        return plans
    filtered: list[ClipPlan] = []
    q = query.strip().lower()
    for plan in plans:
        entries = _load_transcript_entries(root, plan.source_path)
        if not entries:
            continue
        best = 0.0
        best_start = None
        for e in entries:
            text = str(e.get("text", ""))
            score = _semantic_match_score(q, text)
            if q in text.lower():
                score = max(score, 0.9)
            if score > best:
                best = score
                best_start = float(e.get("start", 0.0))
        if best >= 0.25 and best_start is not None:
            plan.start_seconds = max(0.0, best_start - 5.0)
            plan.end_seconds = plan.start_seconds + float(max_seconds)
            filtered.append(plan)
    return filtered


def _parse_manifest(manifest_path: Path) -> tuple[str, list[ClipPlan]]:
    with manifest_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    batch_id = str(data.get("batch_id", manifest_path.stem))
    raw_clips = data.get("clips", [])
    plans: list[ClipPlan] = []
    for c in raw_clips:
        try:
            start = float(c["start_seconds"])
            end = float(c["end_seconds"])
            if end <= start:
                continue
            plans.append(
                ClipPlan(
                    clip_id=str(c["clip_id"]),
                    display_name=str(c.get("display_name", c.get("clip_id", ""))),
                    source_path=str(c["source_path"]),
                    start_seconds=start,
                    end_seconds=end,
                    seed_type=str(c.get("seed_type", "unknown")),
                    subtitle_path=str(c.get("subtitle_path", "") or ""),
                )
            )
        except Exception:
            continue
    return batch_id, plans


def _walk_folder_clips(folder: Any) -> list[Any]:
    out = []
    try:
        clips = _safe_call(folder, "GetClipList", default=[])
        out.extend(clips or [])
    except Exception:
        pass
    for sub in _safe_call(folder, "GetSubFolderList", default=[]) or []:
        out.extend(_walk_folder_clips(sub))
    return out


def _find_media_pool_item_by_path(media_pool: Any, source_path: Path) -> Any | None:
    root = _safe_call(media_pool, "GetRootFolder")
    if root is None:
        return None
    source_abs = str(source_path.resolve()).lower()
    for clip in _walk_folder_clips(root):
        try:
            props = clip.GetClipProperty() or {}
            fp = str(props.get("File Path") or "").lower()
            if fp == source_abs:
                return clip
        except Exception:
            continue
    return None


def _ensure_media_item(media_pool: Any, source_path: Path) -> Any | None:
    item = _find_media_pool_item_by_path(media_pool, source_path)
    if item is not None:
        return item
    imported = _safe_call(media_pool, "ImportMedia", [str(source_path)], default=[])
    if imported and len(imported) > 0:
        return imported[0]
    return None


def _append_clip_range(
    media_pool: Any,
    timeline: Any,
    media_item: Any,
    start_frame: int,
    end_frame: int,
    track_index: int = 1,
    record_frame: int = 0,
) -> bool:
    _safe_call(media_pool, "SetCurrentTimeline", timeline)
    payload = [
        {
            "mediaPoolItem": media_item,
            "startFrame": start_frame,
            "endFrame": end_frame,
            "trackIndex": track_index,
            "recordFrame": record_frame,
        }
    ]
    result = _safe_call(media_pool, "AppendToTimeline", payload)
    return bool(result)


def _apply_item_transform(item: Any, props: dict[str, float]) -> None:
    key_map = {
        "zoom_x": "ZoomX",
        "zoom_y": "ZoomY",
        "pan": "Pan",
        "tilt": "Tilt",
        "crop_top": "CropTop",
        "crop_bottom": "CropBottom",
        "crop_left": "CropLeft",
        "crop_right": "CropRight",
    }
    for k, v in props.items():
        rk = key_map.get(k)
        if not rk:
            continue
        _safe_call(item, "SetProperty", rk, float(v))


def _get_timeline_items_on_track(timeline: Any, track_index: int) -> list[Any]:
    out = _safe_call(timeline, "GetItemListInTrack", "video", track_index, default=[])
    return out or []


def _get_item_at_current_frame(timeline: Any, track_index: int) -> Any | None:
    items = _get_timeline_items_on_track(timeline, track_index)
    if not items:
        return None
    cur = _safe_call(timeline, "GetCurrentFrame", default=0)
    try:
        cur_i = int(cur)
    except Exception:
        cur_i = 0
    for it in items:
        s = _safe_call(it, "GetStart", default=None)
        e = _safe_call(it, "GetEnd", default=None)
        if s is None or e is None:
            continue
        try:
            if int(s) <= cur_i <= int(e):
                return it
        except Exception:
            continue
    return None


def _get_first_item_on_track(timeline: Any, track_index: int) -> Any | None:
    items = _get_timeline_items_on_track(timeline, track_index)
    return items[0] if items else None


def _items_overlapping_frame_range(timeline: Any, track_index: int, start_frame: int, end_frame: int) -> list[Any]:
    items = _get_timeline_items_on_track(timeline, track_index)
    out: list[Any] = []
    for it in items:
        s = _safe_call(it, "GetStart", default=None)
        e = _safe_call(it, "GetEnd", default=None)
        if s is None or e is None:
            continue
        try:
            si = int(s)
            ei = int(e)
        except Exception:
            continue
        if ei < start_frame or si > end_frame:
            continue
        out.append(it)
    return out


def _get_timeline_selected_range(timeline: Any) -> tuple[int, int] | None:
    # Resolve APIs differ across builds; try common variants.
    for method_name in ("GetMarkInOut", "GetInOutPoints", "GetTimelineInOut"):
        data = _safe_call(timeline, method_name, default=None)
        if not isinstance(data, dict):
            continue
        for in_key, out_key in (("video", "video"), ("timeline", "timeline"), ("in", "out")):
            raw_in = data.get(in_key)
            raw_out = data.get(out_key)
            if isinstance(raw_in, dict):
                raw_in = raw_in.get("in")
            if isinstance(raw_out, dict):
                raw_out = raw_out.get("out")
            try:
                s = int(raw_in)
                e = int(raw_out)
            except Exception:
                continue
            if e >= s:
                return s, e
    return None


def _read_item_transform(item: Any) -> dict[str, float]:
    props: dict[str, float] = {}
    key_map = {
        "zoom_x": "ZoomX",
        "zoom_y": "ZoomY",
        "pan": "Pan",
        "tilt": "Tilt",
        "crop_top": "CropTop",
        "crop_bottom": "CropBottom",
        "crop_left": "CropLeft",
        "crop_right": "CropRight",
    }
    for out_key, in_key in key_map.items():
        v = _safe_call(item, "GetProperty", in_key, default=None)
        if v is None:
            d = _safe_call(item, "GetProperty", default={}) or {}
            v = d.get(in_key)
        try:
            props[out_key] = float(v)
        except Exception:
            props[out_key] = 0.0
    return props


def _apply_preset_to_selected_clip(resolve: Any, preset: dict[str, Any], scope_mode: str = "whole_clip") -> tuple[bool, str]:
    pm = _safe_call(resolve, "GetProjectManager")
    project = _safe_call(pm, "GetCurrentProject") if pm else None
    if not project:
        return False, "No open project"
    timeline = _safe_call(project, "GetCurrentTimeline")
    if not timeline:
        return False, "No active timeline"

    mode = str(preset.get("mode", "single"))
    use_range = scope_mode == "selected_range"
    range_frames = _get_timeline_selected_range(timeline) if use_range else None
    if use_range and range_frames is None:
        return False, "No selected In/Out range found on timeline"

    if mode == "fixed_split":
        if use_range and range_frames is not None:
            start_f, end_f = range_frames
            cam_items = _items_overlapping_frame_range(timeline, 1, start_f, end_f)
            game_items = _items_overlapping_frame_range(timeline, 2, start_f, end_f)
            if not cam_items or not game_items:
                return False, "Need clips on Track 1 and Track 2 in selected range"
            _log(f"Apply selected range mapping: camera->T1 items={len(cam_items)}, gameplay->T2 items={len(game_items)}")
            for it in cam_items:
                _apply_item_transform(it, dict(preset.get("camera", {})))
            for it in game_items:
                _apply_item_transform(it, dict(preset.get("gameplay", {})))
            return True, f"Applied preset to range (camera T1: {len(cam_items)}, gameplay T2: {len(game_items)})"

        cam_item = _get_item_at_current_frame(timeline, 1)
        game_item = _get_item_at_current_frame(timeline, 2)
        if not cam_item or not game_item:
            return False, "Need both track 1 (camera) and track 2 (gameplay) at playhead"
        _log("Apply selected clip mapping: camera->T1 gameplay->T2")
        _apply_item_transform(cam_item, dict(preset.get("camera", {})))
        _apply_item_transform(game_item, dict(preset.get("gameplay", {})))
        return True, "Applied preset to selected clip (track1=camera, track2=gameplay)"

    if use_range and range_frames is not None:
        start_f, end_f = range_frames
        items = _items_overlapping_frame_range(timeline, 1, start_f, end_f)
        if not items:
            return False, "No clips found on Track 1 in selected range"
        for it in items:
            _apply_item_transform(it, dict(preset.get("single", {})))
        return True, f"Applied preset to {len(items)} clip(s) in selected range"

    selected = _safe_call(timeline, "GetCurrentVideoItem")
    if not selected:
        return False, "No selected/current clip"
    _apply_item_transform(selected, dict(preset.get("single", {})))
    return True, "Applied preset to selected clip"


def _create_timeline_for_clip_with_preset(
    media_pool: Any,
    name: str,
    media_item: Any,
    start_frame: int,
    end_frame: int,
    preset: dict[str, Any],
) -> Any | None:
    timeline = _safe_call(media_pool, "CreateEmptyTimeline", name)
    if not timeline:
        return None

    mode = str(preset.get("mode", "single"))
    if mode == "fixed_split":
        # Track mapping for composition: track 1 = camera (bottom), track 2 = gameplay (top)
        _log("Build timeline mapping: camera->T1 gameplay->T2 stack_same_record_frame")
        _append_clip_range(media_pool, timeline, media_item, start_frame, end_frame, track_index=1, record_frame=0)
        _safe_call(timeline, "AddTrack", "video")
        _append_clip_range(media_pool, timeline, media_item, start_frame, end_frame, track_index=2, record_frame=0)
        items_t1 = _get_timeline_items_on_track(timeline, 1)
        items_t2 = _get_timeline_items_on_track(timeline, 2)
        if items_t1:
            _apply_item_transform(items_t1[0], dict(preset.get("camera", {})))
        if items_t2:
            _apply_item_transform(items_t2[0], dict(preset.get("gameplay", {})))
        return timeline

    ok = _append_clip_range(media_pool, timeline, media_item, start_frame, end_frame, track_index=1)
    if not ok:
        return None
    items_t1 = _get_timeline_items_on_track(timeline, 1)
    if items_t1:
        _apply_item_transform(items_t1[0], dict(preset.get("single", {})))
    return timeline


def _create_timeline_for_clip(media_pool: Any, name: str, media_item: Any, start_frame: int, end_frame: int) -> Any | None:
    timeline = _safe_call(media_pool, "CreateEmptyTimeline", name)
    if not timeline:
        return None
    ok = _append_clip_range(media_pool, timeline, media_item, start_frame, end_frame, track_index=1)
    return timeline if ok else None


def _ensure_batch_folder(media_pool: Any, batch_id: str) -> Any:
    root = _safe_call(media_pool, "GetRootFolder", required=True)
    for f in _safe_call(root, "GetSubFolderList", default=[]) or []:
        if _safe_call(f, "GetName", default="") == "ShortEditor":
            short_editor = f
            break
    else:
        short_editor = _safe_call(media_pool, "AddSubFolder", root, "ShortEditor", required=True)

    for f in _safe_call(short_editor, "GetSubFolderList", default=[]) or []:
        if _safe_call(f, "GetName", default="") == batch_id:
            batch_folder = f
            break
    else:
        batch_folder = _safe_call(media_pool, "AddSubFolder", short_editor, batch_id, required=True)

    _safe_call(media_pool, "SetCurrentFolder", batch_folder)
    return batch_folder


def _set_shorts_render_defaults(project: Any, output_dir: Path, timeline_name: str) -> None:
    loaded = False
    for preset in ("H264_Shorts_1080x1920_60fps", "H.264 Master", "YouTube"):
        try:
            if _safe_call(project, "LoadRenderPreset", preset, default=False):
                loaded = True
                break
        except Exception:
            continue

    if not loaded:
        try:
            _safe_call(project, "SetCurrentRenderFormatAndCodec", "mp4", "H264")
        except Exception:
            try:
                _safe_call(project, "SetCurrentRenderFormatAndCodec", "mp4", "H.264")
            except Exception:
                pass

    render_settings = {
        "TargetDir": str(output_dir),
        "CustomName": timeline_name,
        "FormatWidth": 1080,
        "FormatHeight": 1920,
        "ResolutionWidth": 1080,
        "ResolutionHeight": 1920,
        "FrameRate": 60,
        "VideoQuality": "Best",
        "SelectAllFrames": True,
        "UseCustomSettings": True,
    }
    _safe_call(project, "SetRenderSettings", render_settings)


def _ensure_vertical_project_settings(project: Any) -> None:
    # Resolve API can vary by build; set multiple known keys.
    _safe_call(project, "SetSetting", "timelineResolutionWidth", "1080")
    _safe_call(project, "SetSetting", "timelineResolutionHeight", "1920")
    _safe_call(project, "SetSetting", "timelineFrameRate", "60")
    _safe_call(project, "SetSetting", "timelinePlaybackFrameRate", "60")
    _safe_call(project, "SetSetting", "timelineOutputResolutionWidth", "1080")
    _safe_call(project, "SetSetting", "timelineOutputResolutionHeight", "1920")
    # Prefer crop behavior when source is 16:9.
    _safe_call(project, "SetSetting", "inputScalingPreset", "Scale full frame with crop")


def _queue_render_job(project: Any, timeline: Any, output_dir: Path, preset_name: str) -> bool:
    _safe_call(project, "SetCurrentTimeline", timeline)
    loaded = False
    try:
        loaded = bool(_safe_call(project, "LoadRenderPreset", preset_name, default=False))
    except Exception:
        loaded = False
    timeline_name = _safe_call(timeline, "GetName", default="timeline")
    if not loaded:
        _set_shorts_render_defaults(project, output_dir, timeline_name)
    else:
        _safe_call(
            project,
            "SetRenderSettings",
            {
                "TargetDir": str(output_dir),
                "CustomName": timeline_name,
                "FormatWidth": 1080,
                "FormatHeight": 1920,
                "FrameRate": 60,
                "UseCustomSettings": True,
            },
        )
    _log(f"Render settings applied for {timeline_name}: 1080x1920@60")
    job_id = _safe_call(project, "AddRenderJob")
    return bool(job_id)


def _find_timeline_by_name(project: Any, timeline_name: str) -> Any | None:
    count = _safe_call(project, "GetTimelineCount", default=0) or 0
    try:
        count = int(count)
    except Exception:
        count = 0
    for i in range(1, count + 1):
        tl = _safe_call(project, "GetTimelineByIndex", i)
        if not tl:
            continue
        name = _safe_call(tl, "GetName", default="")
        if name == timeline_name:
            return tl
    return None


def _delete_timeline_if_exists(project: Any, media_pool: Any, timeline_name: str) -> None:
    tl = _find_timeline_by_name(project, timeline_name)
    if not tl:
        return
    # API variants across Resolve builds.
    deleted = _safe_call(media_pool, "DeleteTimelines", [tl], default=False)
    if not deleted:
        _safe_call(project, "DeleteTimeline", tl, default=False)


def _import_subtitles_to_timeline(project: Any, media_pool: Any, timeline: Any, subtitle_path: Path) -> tuple[bool, str]:
    if not subtitle_path.exists():
        return False, f"Subtitle file missing: {subtitle_path}"

    def _count_track_items(track_type: str) -> int:
        total = 0
        track_count = _safe_call(timeline, "GetTrackCount", track_type, default=0)
        try:
            count_i = int(track_count)
        except Exception:
            count_i = 0
        for i in range(1, count_i + 1):
            items = _safe_call(timeline, "GetItemListInTrack", track_type, i, default=[])
            total += len(items or [])
        return total

    def _count_subtitle_items() -> int:
        return _count_track_items("subtitle")

    def _count_video_items() -> int:
        return _count_track_items("video")

    before_count = _count_subtitle_items()
    before_video_count = _count_video_items()
    _safe_call(project, "SetCurrentTimeline", timeline)
    _safe_call(media_pool, "SetCurrentTimeline", timeline)

    # Preferred APIs by build.
    for api_name in ("ImportSubtitles", "ImportSubtitleFile"):
        out = _safe_call(timeline, api_name, str(subtitle_path), default=None)
        after_count = _count_subtitle_items()
        if out or after_count > before_count:
            return True, f"Subtitles imported via timeline.{api_name}"

    for api_name in ("ImportSubtitles", "ImportSubtitleFile"):
        out = _safe_call(project, api_name, str(subtitle_path), default=None)
        after_count = _count_subtitle_items()
        if out or after_count > before_count:
            return True, f"Subtitles imported via project.{api_name}"

    # Fallback: import into media pool then append on TOP video track.
    sub_item = _ensure_media_item(media_pool, subtitle_path)
    if sub_item is not None:
        # Ensure there is a dedicated top overlay track and place subtitles at recordFrame=0
        # so SRT timecodes stay synced with the clip timeline.
        _safe_call(timeline, "AddTrack", "video")
        video_track_count = _safe_call(timeline, "GetTrackCount", "video", default=1)
        try:
            top_video_track = max(1, int(video_track_count))
        except Exception:
            top_video_track = 1

        payload_variants: list[Any] = [
            [sub_item],
            sub_item,
            [{"mediaPoolItem": sub_item}],
            [{"mediaPoolItem": sub_item, "trackIndex": top_video_track, "recordFrame": 0}],
            [{"mediaPoolItem": sub_item, "trackType": "video", "trackIndex": top_video_track, "recordFrame": 0}],
            [{"mediaPoolItem": sub_item, "mediaType": 1, "trackIndex": top_video_track, "recordFrame": 0}],
            [{"mediaPoolItem": sub_item, "startFrame": 0, "endFrame": 0, "trackIndex": top_video_track, "recordFrame": 0}],
        ]

        for idx, payload in enumerate(payload_variants, start=1):
            out = _safe_call(media_pool, "AppendToTimeline", payload)
            after_count = _count_subtitle_items()
            after_video = _count_video_items()
            _log(f"subtitle_fallback_try#{idx} out_type={type(out).__name__} top_video_track={top_video_track} after_sub={after_count} after_vid={after_video}")
            if after_count > before_count:
                return True, "Subtitles imported via fallback on top overlay track"
            if after_video > before_video_count:
                return True, "Subtitle media appended on top video track (synced at clip start)"
    after_count = _count_subtitle_items()
    after_video = _count_video_items()
    if after_count > before_count:
        return True, "Subtitles imported but API returned ambiguous result"
    if after_video > before_video_count:
        return True, "Subtitle clip appended on video track (no subtitle track API)"
    return False, "No supported subtitle import API available"


def _plan_key(plan: ClipPlan) -> str:
    return plan.clip_id


def _safe_name_token(text: str, limit: int = 72) -> str:
    forbidden = set('\\/:*?"<>|')
    cleaned = "".join(ch if (ch.isalnum() or ch in "-_ ") and ch not in forbidden else " " for ch in text)
    cleaned = " ".join(cleaned.split())
    if not cleaned:
        cleaned = "clip"
    return cleaned[:limit]


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
) -> tuple[str, dict[str, ClipPlan], list[Any], list[str]]:
    batch_id, plans = _parse_manifest(manifest_path)

    max_clip_seconds = int(selected_preset.get("max_clip_seconds", 45))
    if transcript_query.strip():
        plans = _filter_plans_by_transcript_query(root, plans, transcript_query, max_clip_seconds)
        _log(f"Transcript query filtered plans to {len(plans)} clip(s)")

    if not plans:
        return batch_id, {}, [], ["No valid clip plans in manifest."]

    _ensure_vertical_project_settings(project)
    _ensure_batch_folder(media_pool, batch_id)
    fps = _fps_from_project(project)

    created_timelines: list[Any] = []
    warnings: list[str] = []
    plan_map: dict[str, ClipPlan] = {}
    resolved_source_by_clip: dict[str, Path] = {}
    used_timeline_names: set[str] = set()
    remap_notices: set[str] = set()
    subtitle_eligible = 0
    subtitle_imported = 0

    def _resolve_existing_source(raw_source_path: str) -> Path | None:
        src = Path(raw_source_path)
        if not src.is_absolute():
            src = (root / src).resolve()
        if src.exists():
            return src

        file_name = src.name
        if detected_vod_path is not None and detected_vod_path.exists():
            remap_notices.add(f"Manifest source missing, remapped to selected Resolve clip: {detected_vod_path}")
            return detected_vod_path

        if user_vod_dir is not None and user_vod_dir.exists():
            direct = user_vod_dir / file_name
            if direct.exists():
                remap_notices.add(f"Manifest source missing, remapped from VOD folder: {direct}")
                return direct
            matches = list(user_vod_dir.rglob(file_name))
            if len(matches) == 1 and matches[0].exists():
                remap_notices.add(f"Manifest source missing, remapped from VOD folder: {matches[0]}")
                return matches[0]
            if len(matches) > 1:
                warnings.append(f"Multiple candidates for missing source '{file_name}' in VOD folder: {user_vod_dir}")
        return None

    for plan in plans:
        src = _resolve_existing_source(plan.source_path)
        if src is None:
            raw_src = Path(plan.source_path)
            if not raw_src.is_absolute():
                raw_src = (root / raw_src).resolve()
            warnings.append(f"Missing source file: {raw_src}")
            continue
        if not src.exists():
            warnings.append(f"Missing source file: {src}")
            continue

        item = _ensure_media_item(media_pool, src)
        if item is None:
            warnings.append(f"Could not import media: {src}")
            continue

        start_frame = int(round(plan.start_seconds * fps))
        end_frame = int(round(plan.end_seconds * fps))
        if end_frame <= start_frame:
            warnings.append(f"Invalid range for {plan.clip_id}")
            continue

        display = _safe_name_token(plan.display_name or plan.clip_id, limit=84)
        timeline_name = f"{batch_id}__{display}"
        if timeline_name in used_timeline_names:
            dup_idx = 2
            base_name = timeline_name
            while f"{base_name} ({dup_idx})" in used_timeline_names:
                dup_idx += 1
            timeline_name = f"{base_name} ({dup_idx})"
        used_timeline_names.add(timeline_name)
        _delete_timeline_if_exists(project, media_pool, timeline_name)
        tl = _create_timeline_for_clip_with_preset(media_pool, timeline_name, item, start_frame, end_frame, selected_preset)
        if tl is None:
            warnings.append(f"Could not create timeline for {plan.clip_id}")
            continue

        if plan.subtitle_path:
            subtitle_eligible += 1
            sub_path = Path(plan.subtitle_path)
            if not sub_path.is_absolute():
                sub_path = (root / sub_path).resolve()
            ok_sub, sub_msg = _import_subtitles_to_timeline(project, media_pool, tl, sub_path)
            if ok_sub:
                subtitle_imported += 1
                _log(f"subtitle_imported clip={plan.clip_id} path={sub_path} msg={sub_msg}")
            else:
                warnings.append(f"Subtitle import failed for {plan.clip_id}: {sub_msg}")
                _log(f"subtitle_import_failed clip={plan.clip_id} path={sub_path} msg={sub_msg}")
        elif require_subtitles:
            warnings.append(f"Subtitle missing in manifest for {plan.clip_id}")

        created_timelines.append(tl)
        plan_map[_plan_key(plan)] = plan
        resolved_source_by_clip[_plan_key(plan)] = src

    master_tl = None
    if created_timelines:
        master_name = f"{batch_id}__MASTER_REVIEW"
        _delete_timeline_if_exists(project, media_pool, master_name)
        master_tl = _safe_call(media_pool, "CreateEmptyTimeline", master_name)
        if master_tl:
            for plan in plans:
                src = resolved_source_by_clip.get(_plan_key(plan))
                item = _ensure_media_item(media_pool, src) if src and src.exists() else None
                if not item:
                    continue
                start_frame = int(round(plan.start_seconds * fps))
                end_frame = int(round(plan.end_seconds * fps))
                if end_frame <= start_frame:
                    continue
                _append_clip_range(media_pool, master_tl, item, start_frame, end_frame, track_index=1)

    if queue_render:
        queued = 0
        for tl in created_timelines:
            if _queue_render_job(project, tl, output_dir, preset_name):
                queued += 1
        if render_master and master_tl and _queue_render_job(project, master_tl, output_dir, preset_name):
            queued += 1
        _log(f"Queued render jobs: {queued}")

    for notice in sorted(remap_notices):
        warnings.append(notice)

    if require_subtitles:
        if subtitle_eligible == 0:
            warnings.append("No subtitle files were available in manifest for this batch.")
        elif subtitle_imported == 0:
            warnings.append("Subtitle import did not succeed on any timeline.")
        _log(f"subtitle_import_summary eligible={subtitle_eligible} imported={subtitle_imported}")

    return batch_id, plan_map, created_timelines, warnings


def run() -> int:
    root = _repo_root()
    presets_data = _load_or_init_presets(root)
    _log(f"Starting Resolve batch script. Root={root}")
    resolve = None

    loading_root = None
    loading_text = None
    loading_step_text = None
    loading_percent_text = None
    loading_progress_canvas = None
    loading_progress_fill = None
    loading_progress_value = 0
    loading_text_canvas = None
    loading_text_items: list[Any] = []
    text_wave_job = None
    text_wave_index = 0
    loading_image_label = None
    loading_mode = "text"
    frame_job = None
    phase_job = None
    anim_frames: dict[str, list[Any]] = {"idle": [], "suck": [], "digest": [], "dance": []}
    anim_state = {"name": "", "idx": 0, "loop": True}
    try:
        import tkinter as tk

        loading_root = tk.Tk()
        loading_root.title("Short Editor")
        loading_root.geometry("500x156")
        loading_root.configure(bg="#E7ECFF")
        loading_root.attributes("-topmost", True)
        loading_text = tk.StringVar(value="Kirby eats your VOD...")
        text_message = "Kirby eats your VOD..."
        loading_text_canvas = tk.Canvas(loading_root, width=440, height=40, bg="#E7ECFF", highlightthickness=0, bd=0)
        loading_text_canvas.pack(pady=(8, 2))
        loading_image_label = tk.Label(loading_root, bg="#E7ECFF")
        loading_image_label.pack(pady=(2, 4))

        assets = _assets_dir(root)
        anim_frames["idle"] = _load_gif_frames(tk, assets / "kirby_idle.gif")
        anim_frames["suck"] = _load_gif_frames(tk, assets / "kirby_suck.gif")
        anim_frames["digest"] = _load_gif_frames(tk, assets / "kirby_digest.gif")
        anim_frames["dance"] = _load_gif_frames(tk, assets / "kirby_dance.gif")
        if anim_frames["idle"] and anim_frames["suck"] and anim_frames["digest"] and anim_frames["dance"]:
            loading_mode = "gif"
            _log("kirby_loader_start")
        else:
            _log("kirby_loader_fallback_text_mode")
        tk.Label(
            loading_root,
            text="Short Editor",
            bg="#E7ECFF",
            fg="#6D4DFF",
            font=("Segoe UI", 12, "bold"),
        ).pack(pady=(8, 2))
        loading_step_text = tk.StringVar(value="Step: Initializing")
        loading_percent_text = tk.StringVar(value="0%")
        tk.Label(
            loading_root,
            textvariable=loading_step_text,
            bg="#E7ECFF",
            fg="#1E1E2A",
            font=("Segoe UI", 9, "bold"),
        ).pack(pady=(0, 1))
        tk.Label(
            loading_root,
            textvariable=loading_percent_text,
            bg="#E7ECFF",
            fg="#6D4DFF",
            font=("Segoe UI", 9, "bold"),
        ).pack(pady=(0, 3))

        loading_progress_canvas = tk.Canvas(loading_root, width=360, height=16, bg="#E7ECFF", highlightthickness=0, bd=0)
        loading_progress_canvas.pack(pady=(0, 6))
        loading_progress_canvas.create_rectangle(2, 2, 358, 14, fill="#FFF3B3", outline="#7E69D9", width=1)
        loading_progress_fill = loading_progress_canvas.create_rectangle(3, 3, 3, 13, fill="#6D4DFF", outline="#6D4DFF", width=0)
        _log("loader_bar_canvas_init_ok")

        def build_text_wave_items(message: str) -> None:
            nonlocal loading_text_items
            if loading_text_canvas is None:
                return
            loading_text_canvas.delete("all")
            loading_text_items = []
            x = 16
            for ch in message:
                item = loading_text_canvas.create_text(
                    x,
                    18,
                    text=ch,
                    fill="#FF6FAE",
                    font=("Segoe UI", 16, "bold"),
                    anchor="w",
                )
                loading_text_items.append(item)
                x += 10 if ch != " " else 8

        def animate_text_wave() -> None:
            nonlocal text_wave_job, text_wave_index
            if loading_root is None or loading_text_canvas is None:
                return
            if not loading_root.winfo_exists() or not loading_text_items:
                return
            base_y = 18
            non_space_indices = [i for i, ch in enumerate(text_message) if ch != " "]
            if not non_space_indices:
                return
            active = non_space_indices[text_wave_index % len(non_space_indices)]
            for idx, item in enumerate(loading_text_items):
                lift = 0.0
                if idx == active:
                    lift = 6.0
                elif idx == active - 1 or idx == active + 1:
                    lift = 2.0
                y = base_y - lift
                coords = loading_text_canvas.coords(item)
                if len(coords) >= 2:
                    loading_text_canvas.coords(item, coords[0], y)
            text_wave_index += 1
            text_wave_job = loading_root.after(95, animate_text_wave)

        build_text_wave_items(text_message)
        animate_text_wave()
        loading_root.update_idletasks()
        loading_root.update()

        def animate_tick() -> None:
            nonlocal frame_job
            if loading_root is None or loading_image_label is None:
                return
            if not loading_root.winfo_exists():
                return
            name = anim_state["name"]
            frames = anim_frames.get(name, [])
            if not frames:
                return
            if name == "digest":
                idx = min(anim_state["idx"], len(frames) - 1)
            else:
                idx = anim_state["idx"] % len(frames)
            loading_image_label.configure(image=frames[idx])
            loading_image_label.image = frames[idx]
            anim_state["idx"] += 1
            frame_job = loading_root.after(70, animate_tick)

        def set_anim(name: str) -> None:
            nonlocal frame_job
            if loading_mode != "gif" or loading_root is None:
                return
            if frame_job is not None:
                try:
                    loading_root.after_cancel(frame_job)
                except Exception:
                    pass
            anim_state["name"] = name
            anim_state["idx"] = 0
            animate_tick()

        def start_kirby_phase_loop() -> None:
            nonlocal phase_job
            if loading_mode != "gif" or loading_root is None:
                return
            if not anim_state.get("loop", True):
                return
            # idle 3s -> suck 2s -> digest 0.7s -> dance 3s
            phases = [("idle", 3000), ("suck", 2000), ("digest", 700), ("dance", 3000)]

            def step(index: int) -> None:
                nonlocal phase_job
                if loading_root is None or not loading_root.winfo_exists() or not anim_state.get("loop", True):
                    return
                phase_name, duration = phases[index % len(phases)]
                _log(f"loader_phase={phase_name}")
                set_anim(phase_name)
                phase_job = loading_root.after(duration, lambda: step(index + 1))

            step(0)

        def stop_phase_loop() -> None:
            nonlocal phase_job, frame_job, text_wave_job
            anim_state["loop"] = False
            if phase_job is not None:
                try:
                    loading_root.after_cancel(phase_job)
                except Exception:
                    pass
                phase_job = None
            if frame_job is not None:
                try:
                    loading_root.after_cancel(frame_job)
                except Exception:
                    pass
                frame_job = None
            if text_wave_job is not None:
                try:
                    loading_root.after_cancel(text_wave_job)
                except Exception:
                    pass
                text_wave_job = None

        def final_dance_then_close() -> None:
            if loading_root is None:
                return
            _log("loader_final_dance_start")
            set_anim("dance")

            def close_now() -> None:
                nonlocal loading_root
                stop_phase_loop()
                if loading_root is not None and loading_root.winfo_exists():
                    loading_root.destroy()
                    loading_root = None
                _log("kirby_loader_end")

            loading_root.after(2000, close_now)

        loading_root._set_anim = set_anim  # type: ignore[attr-defined]
        loading_root._start_phase_loop = start_kirby_phase_loop  # type: ignore[attr-defined]
        loading_root._stop_phase_loop = stop_phase_loop  # type: ignore[attr-defined]
        loading_root._final_dance_then_close = final_dance_then_close  # type: ignore[attr-defined]
    except Exception as exc:
        _log(f"Loading UI disabled: {exc}")

    def set_loading(msg: str) -> None:
        _log(msg)
        if loading_root is not None and loading_text is not None:
            loading_text.set("Kirby eats your VOD...")
            loading_root.update_idletasks()
            loading_root.update()

    def set_loading_progress(step_label: str, percent: int | None = None, indeterminate: bool = False) -> None:
        _log(f"loader_step={step_label} percent={percent if percent is not None else 'indeterminate'}")
        nonlocal loading_progress_value
        if loading_root is None:
            return
        if loading_step_text is not None:
            loading_step_text.set(f"Step: {step_label}")
        if loading_percent_text is not None:
            if percent is None:
                loading_percent_text.set("...")
            else:
                p = max(0, min(100, int(percent)))
                loading_percent_text.set(f"{p}%")
        if loading_progress_canvas is not None and loading_progress_fill is not None:
            try:
                if percent is None:
                    if indeterminate:
                        loading_progress_value = (loading_progress_value + 4) % 100
                    p = loading_progress_value
                else:
                    p = max(0, min(100, int(percent)))
                    loading_progress_value = p
                x2 = 3 + int((355 * p) / 100)
                if x2 < 3:
                    x2 = 3
                loading_progress_canvas.coords(loading_progress_fill, 3, 3, x2, 13)
                _log(f"loader_bar_update percent={p}")
            except Exception:
                pass
        try:
            loading_root.update_idletasks()
            loading_root.update()
        except Exception:
            pass

    def set_loading_anim(name: str) -> None:
        if loading_root is None:
            return
        setter = getattr(loading_root, "_set_anim", None)
        if callable(setter):
            setter(name)

    set_loading_progress("Initializing loader", 0)
    set_loading("Loading Resolve API...")
    set_loading_progress("Loading Resolve API", 4)
    resolve = _load_resolve()
    set_loading_progress("Resolve API ready", 8)

    set_loading("Detecting VOD source...")
    set_loading_progress("Detecting VOD source", 10)
    auto_vod = _auto_detect_vod_path(resolve, root)
    if auto_vod is None:
        set_loading("Select VOD file...")
        set_loading_progress("Waiting for VOD selection", 15)
        auto_vod = _prompt_vod_path_native(root / "input", parent=loading_root)
        if loading_root is not None:
            try:
                loading_root.lift()
                loading_root.focus_force()
                loading_root.update_idletasks()
                loading_root.update()
                _log("loader_focus_restored_after_picker")
            except Exception:
                pass
    if auto_vod is None:
        if loading_root is not None:
            loading_root.destroy()
        raise RuntimeError("No VOD selected. Select a VOD to continue.")

    set_loading("Generating manifest...")
    set_loading_progress("Generating manifest", 20)
    starter = getattr(loading_root, "_start_phase_loop", None)
    if callable(starter):
        starter()

    manifest_result: dict[str, Any] = {"manifest": None, "error": None}
    used_manifest_fallback = False

    def _manifest_worker() -> None:
        try:
            manifest_result["manifest"] = _generate_manifest_for_vod(root, auto_vod, generate_subtitles=False)
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
        set_loading_progress("Generating manifest", pseudo_progress)
        if loading_root is not None:
            try:
                loading_root.update_idletasks()
                loading_root.update()
            except Exception:
                pass
        time.sleep(0.03)
    if manifest_result["error"] is not None:
        err = manifest_result["error"]
        _log(f"Manifest generation error: {err.get('message', err)}")
        _log(err.get("traceback", ""))
        fallback_manifest = _latest_manifest(root / "output" / "manifests")
        if fallback_manifest is None:
            if loading_root is not None:
                loading_root.destroy()
            raise RuntimeError(f"Manifest generation failed and no fallback manifest found: {err.get('message', err)}")
        default_manifest = fallback_manifest
        used_manifest_fallback = True
        set_loading("Manifest failed. Using latest batch...")
        set_loading_progress("Using fallback manifest", 86)
        _log(f"Using fallback manifest: {default_manifest}")
    else:
        default_manifest = manifest_result["manifest"]
    set_loading("Manifest ready!")
    set_loading_progress("Manifest ready", 92)
    finalizer = getattr(loading_root, "_final_dance_then_close", None)
    if callable(finalizer):
        set_loading_progress("Finalizing", 97)
        finalizer()
        # keep pumping UI until loader closes
        while loading_root is not None:
            try:
                if not loading_root.winfo_exists():
                    break
            except Exception:
                break
            try:
                loading_root.update_idletasks()
                loading_root.update()
            except Exception:
                break
            time.sleep(0.03)
    elif loading_root is not None:
        set_loading_progress("Done", 100)
        loading_root.destroy()
        _log("kirby_loader_end")
    _log(f"Default manifest: {default_manifest}")

    project_manager = _safe_call(resolve, "GetProjectManager", required=True)
    project = _safe_call(project_manager, "GetCurrentProject", required=True)
    if project is None:
        raise RuntimeError("No open Resolve project. Open a project first.")

    media_pool = _safe_call(project, "GetMediaPool", required=True)
    if media_pool is None:
        raise RuntimeError("Could not access Media Pool.")

    session: dict[str, Any] = {
        "batch_id": None,
        "manifest": default_manifest,
        "plan_map": {},
        "detected_vod": auto_vod,
        "used_manifest_fallback": used_manifest_fallback,
    }

    def on_generate(params: dict[str, Any]) -> dict[str, Any] | str:
        manifest_value = session.get("manifest") or default_manifest
        if not manifest_value:
            return {"message": "No manifest available. Relaunch script to regenerate one.", "warnings": []}
        manifest_path = Path(manifest_value)
        output_dir = Path(params["output"])
        preset_name = str(params["render_preset"])
        render_master = bool(params["render_master"])
        preset_id = str(params["preset_id"])
        transcript_query = str(params["query"])
        strict_manifest = bool(params.get("strict_manifest", False))
        require_subtitles = bool(params.get("require_subtitles", False))
        vod_dir_raw = str(params.get("vod_dir", "")).strip()
        user_vod_dir = Path(vod_dir_raw) if vod_dir_raw else None
        detected_vod = session.get("detected_vod")

        if strict_manifest and bool(session.get("used_manifest_fallback", False)):
            fallback_msg = "Auto Subtitles canceled: manifest generation failed at startup and fallback manifest is in use. Relaunch script to regenerate a fresh manifest."
            _log(f"UI generate blocked (strict manifest): {fallback_msg}")
            return {"message": fallback_msg, "warnings": [fallback_msg]}

        if require_subtitles:
            if detected_vod is None or not Path(detected_vod).exists():
                return {"message": "Auto Subtitles requires a detected VOD source. Select a clip in Resolve and relaunch.", "warnings": []}
            try:
                manifest_path = _generate_manifest_for_vod(root, Path(detected_vod), generate_subtitles=True)
                session["manifest"] = manifest_path
                session["used_manifest_fallback"] = False
                _log(f"Regenerated manifest with subtitles: {manifest_path}")
            except Exception as exc:
                msg = f"Auto subtitle manifest generation failed: {exc}"
                _log(msg)
                return {"message": msg, "warnings": [msg]}

        selected_preset = dict((presets_data.get("presets", {}) or {}).get(preset_id, {}))
        if not selected_preset:
            return {"message": f"Preset not found: {preset_id}", "warnings": []}

        batch_id, plan_map, timelines, warnings = _build_from_manifest(
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
            user_vod_dir=user_vod_dir,
            require_subtitles=require_subtitles,
        )
        session["batch_id"] = batch_id
        session["manifest"] = manifest_path
        session["plan_map"] = plan_map
        msg = f"Generated {len(timelines)} timelines"
        if bool(session.get("used_manifest_fallback", False)):
            warnings.append(f"Using fallback manifest: {manifest_path}")
        if warnings:
            msg += f" ({len(warnings)} warnings)"
        _log(f"UI generate: {msg}")
        return {"message": msg, "warnings": warnings}

    def on_update(params: dict[str, Any]) -> dict[str, Any] | str:
        if not session.get("batch_id"):
            return {"message": "Generate batch first.", "warnings": []}
        manifest_value = session.get("manifest") or default_manifest
        if not manifest_value:
            return {"message": "No manifest available. Relaunch script to regenerate one.", "warnings": []}
        manifest_path = Path(manifest_value)
        output_dir = Path(params["output"])
        preset_name = str(params["render_preset"])
        preset_id = str(params["preset_id"])
        transcript_query = str(params["query"])
        vod_dir_raw = str(params.get("vod_dir", "")).strip()
        user_vod_dir = Path(vod_dir_raw) if vod_dir_raw else None
        detected_vod = session.get("detected_vod")
        selected_preset = dict((presets_data.get("presets", {}) or {}).get(preset_id, {}))
        if not selected_preset:
            return {"message": f"Preset not found: {preset_id}", "warnings": []}

        batch_id, plan_map, timelines, warnings = _build_from_manifest(
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
            user_vod_dir=user_vod_dir,
            require_subtitles=False,
        )
        session["batch_id"] = batch_id
        session["manifest"] = manifest_path
        session["plan_map"] = plan_map
        msg = f"Updated composition on {len(timelines)} timelines"
        if bool(session.get("used_manifest_fallback", False)):
            warnings.append(f"Using fallback manifest: {manifest_path}")
        if warnings:
            msg += f" ({len(warnings)} warnings)"
        _log(f"UI update: {msg}")
        return {"message": msg, "warnings": warnings}

    _ask_user_inputs(default_manifest, presets_data, resolve, on_generate, on_update, session)

    _log("Resolve UI session closed.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(run())
    except Exception as exc:
        _log(f"FATAL: {exc}")
        raise
