from __future__ import annotations

import json
import io
import csv
import re
import sys
import os
import uuid
import time
import threading
import traceback
import warnings
import subprocess
import tempfile
from contextlib import redirect_stderr
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from datetime import datetime, timezone
import importlib


DEFAULT_FPS = 60
STANDALONE_CAPTION_TEMPLATE_NAME = "ShortEditor Caption"
STANDALONE_CAPTION_TEMPLATE_FALLBACK_NAME = "AutoSubs Caption"
SUBTITLE_TEMPLATE_AUTO_LABEL = "Auto-detect (Recommended)"

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
                "active_preset": "Valorant Preset",
                "max_transcript_clip_seconds": 45,
            },
            "jeu": {
                "label": "Jeu",
                "active_preset": "Jeux",
                "max_transcript_clip_seconds": 45,
            },
            "react": {
                "label": "React",
                "active_preset": "Just chatting",
                "max_transcript_clip_seconds": 45,
            },
        },
        "presets": {
            "Valorant Preset": {
                "name": "Valorant Preset",
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
            "Jeux": {
                "name": "Jeux",
                "profile": "valo",
                "mode": "fixed_split",
                "safe_padding": 0.06,
                "max_clip_seconds": 45,
                "gameplay": {
                    "zoom_x": 1.78,
                    "zoom_y": 1.78,
                    "pan": 117.72,
                    "tilt": 1388.18,
                    "crop_top": 0.0,
                    "crop_bottom": 0.0,
                    "crop_left": 0.0,
                    "crop_right": 0.0,
                },
                "camera": {
                    "zoom_x": 3.74,
                    "zoom_y": 3.74,
                    "pan": -1460.0,
                    "tilt": 448.62,
                    "crop_top": 0.0,
                    "crop_bottom": 0.42,
                    "crop_left": 0.0,
                    "crop_right": 0.0,
                },
            },
            "Just chatting": {
                "name": "Just chatting",
                "profile": "react",
                "mode": "fixed_split",
                "safe_padding": 0.06,
                "max_clip_seconds": 45,
                "single": {
                    "zoom_x": 0.1,
                    "zoom_y": 0.1,
                    "pan": 0.0,
                    "tilt": 0.0,
                    "crop_top": 0.0,
                    "crop_bottom": 0.0,
                    "crop_left": 0.0,
                    "crop_right": 0.0,
                },
                "gameplay": {
                    "zoom_x": 2.62,
                    "zoom_y": 2.62,
                    "pan": -1.0,
                    "tilt": 1.0,
                    "crop_top": 0.0,
                    "crop_bottom": 0.0,
                    "crop_left": 0.0,
                    "crop_right": 0.0,
                },
                "camera": {
                    "zoom_x": 3.74,
                    "zoom_y": 3.74,
                    "pan": 1.0,
                    "tilt": 1.0,
                    "crop_top": 0.0,
                    "crop_bottom": 0.42,
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
        data = json.load(f)

    presets = data.get("presets", {}) if isinstance(data, dict) else {}
    profiles = data.get("profiles", {}) if isinstance(data, dict) else {}
    if not isinstance(presets, dict):
        presets = {}
    if not isinstance(profiles, dict):
        profiles = {}

    preset_ids = list(presets.keys())
    if preset_ids:
        fallback_preset = preset_ids[0]
        changed = False
        for profile_name, profile_data in profiles.items():
            if not isinstance(profile_data, dict):
                continue
            active = str(profile_data.get("active_preset", "")).strip()
            if active and active in presets:
                continue
            preferred = next(
                (
                    pid
                    for pid, pdata in presets.items()
                    if isinstance(pdata, dict) and str(pdata.get("profile", "")).strip() == str(profile_name)
                ),
                fallback_preset,
            )
            profile_data["active_preset"] = preferred
            changed = True
        if changed:
            data["profiles"] = profiles
            _save_presets(root, data)
    return data


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


def _paths_match_lenient(left: Any, right: Any) -> bool:
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


def _manifest_matches_vod(data: dict[str, Any], vod_path: Path) -> bool:
    meta = data.get("meta", {}) if isinstance(data.get("meta", {}), dict) else {}
    meta_vod = str(meta.get("source_vod_path", "")).strip()
    if meta_vod and _paths_match_lenient(meta_vod, vod_path):
        return True

    source_vods = data.get("source_vods", [])
    if isinstance(source_vods, list):
        for src in source_vods:
            if _paths_match_lenient(src, vod_path):
                return True

    clips = data.get("clips", [])
    if isinstance(clips, list):
        for clip in clips:
            if isinstance(clip, dict) and _paths_match_lenient(clip.get("source_path", ""), vod_path):
                return True
    return False


def _find_existing_manifest_for_vod(root: Path, vod_path: Path) -> Path | None:
    manifest_dir = root / "output" / "manifests"
    if not manifest_dir.exists():
        return None
    files = sorted(manifest_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    candidates: list[tuple[int, Path]] = []
    for mf in files:
        data = _read_manifest_safe(mf)
        if not data:
            continue
        if _manifest_matches_vod(data, vod_path):
            meta = data.get("meta", {}) if isinstance(data.get("meta", {}), dict) else {}
            has_valid_subtitles = _manifest_has_valid_subtitles(root, data)
            generated_with_subtitles = bool(meta.get("generated_with_subtitles", False))
            if has_valid_subtitles:
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


def _transcript_path_for_vod(root: Path, vod_path: Path) -> Path:
    return (root / "output" / "transcripts" / f"{vod_path.stem}.json").resolve()


def _read_manifest_safe(path: Path) -> dict[str, Any] | None:
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _manifest_has_valid_subtitles(root: Path, data: dict[str, Any]) -> bool:
    clips = data.get("clips", [])
    if not isinstance(clips, list) or not clips:
        return False
    for clip in clips:
        if not isinstance(clip, dict):
            return False
        sub = str(clip.get("subtitle_path", "")).strip()
        if not sub:
            return False
        sub_path = Path(sub)
        if not sub_path.is_absolute():
            sub_path = (root / sub_path).resolve()
        if not sub_path.exists():
            return False
    return True


def _find_reusable_quality_manifest(root: Path, vod_path: Path, preset_id: str, use_transcript_for_selection: bool) -> Path | None:
    manifest_dir = root / "output" / "manifests"
    if not manifest_dir.exists():
        return None
    files = sorted(manifest_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    target_vod = str(vod_path.resolve())
    for mf in files:
        data = _read_manifest_safe(mf)
        if not data:
            continue
        meta = data.get("meta", {}) if isinstance(data.get("meta", {}), dict) else {}
        if not bool(meta.get("generated_with_subtitles", False)):
            continue
        if str(meta.get("preset_id", "")).strip() != preset_id.strip():
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
        if not _manifest_has_valid_subtitles(root, data):
            continue
        return mf
    return None


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
        pm_ui = _safe_call(resolve, "GetProjectManager")
        project_ui = _safe_call(pm_ui, "GetCurrentProject") if pm_ui else None
        media_pool_ui = _safe_call(project_ui, "GetMediaPool") if project_ui else None
        subtitle_template_options = [SUBTITLE_TEMPLATE_AUTO_LABEL]
        if media_pool_ui is not None:
            subtitle_template_options.extend(_list_subtitle_template_candidates(media_pool_ui))
        subtitle_template_options = list(dict.fromkeys([x for x in subtitle_template_options if str(x).strip()]))
        preset_ids = list(presets.keys())
        default_profile = "valo" if "valo" in profiles else (next(iter(profiles.keys()), "valo"))
        profile_info = profiles.get(default_profile, {}) if isinstance(profiles, dict) else {}
        active_from_profile = str(profile_info.get("active_preset", "")).strip() if isinstance(profile_info, dict) else ""
        default_preset_id = active_from_profile if active_from_profile in presets else (preset_ids[0] if preset_ids else "")
        keys = ("zoom_x", "zoom_y", "pan", "tilt", "crop_top", "crop_bottom", "crop_left", "crop_right")

        colors = {
            "bg": "#6FD8FF",
            "sky": "#6FD8FF",
            "cloud": "#FFFFFF",
            "panel": "#D9C7FF",
            "panel_alt": "#FFF7FF",
            "accent": "#FF7EDB",
            "accent_soft": "#FFB7E8",
            "ink": "#24304F",
            "sun": "#FFF4B2",
            "sun_soft": "#FFFBE0",
            "mint": "#CFFFE2",
            "aero": "#BDF4FF",
            "line": "#7E69D9",
            "glow": "#FFFFFF",
        }

        state = {
            "output_dir": str(output_dir),
            "vod_dir": str((_repo_root() / "input").resolve()),
            "render_preset": preset_name,
            "profile": default_profile,
            "preset_id": default_preset_id,
            "query": "",
            "render_master": False,
            "subtitle_template_name": SUBTITLE_TEMPLATE_AUTO_LABEL,
            "subtitle_offset_ms": "-500",
        }

        root = tk.Tk()
        compact_geometry = "1180x860"
        expanded_geometry = "1180x1020"
        root.title("Short Editor // Console ange digital 2003")
        root.geometry(compact_geometry)
        root.configure(bg=colors["bg"])
        _log("UI window created OK")

        def play_hover_sound() -> None:
            # Sound-ready hook: volontairement muet par défaut.
            return

        def play_click_sound() -> None:
            # Sound-ready hook: brancher ici un son court si souhaité.
            return

        def play_notification_sound() -> None:
            # Sound-ready hook: notifications désactivées par défaut.
            return

        dream_bg = tk.Canvas(root, bg=colors["sky"], highlightthickness=0, bd=0)
        dream_bg.place(x=0, y=0, relwidth=1, relheight=1)
        try:
            dream_bg.tk.call("lower", dream_bg._w)
        except Exception as exc:
            _log(f"dream_bg_lower_failed: {exc}")
        bg_state: dict[str, Any] = {"tick": 0, "mouse_x": 0, "mouse_y": 0, "sparkles": []}

        def _draw_dream_background() -> None:
            try:
                w = max(1, int(root.winfo_width()))
                h = max(1, int(root.winfo_height()))
                t = int(bg_state.get("tick", 0))
                mx = float(bg_state.get("mouse_x", 0))
                my = float(bg_state.get("mouse_y", 0))
                px = (mx - w / 2) / max(1, w)
                py = (my - h / 2) / max(1, h)
                dream_bg.delete("all")

                # Frutiger Aero sky bands and glows.
                dream_bg.create_rectangle(0, 0, w, h, fill=colors["sky"], outline="")
                dream_bg.create_oval(-160 + px * 28, -120 + py * 16, 360 + px * 28, 260 + py * 16, fill="#FFFFFF", outline="#BDF4FF")
                dream_bg.create_oval(w - 320 + px * -24, 40 + py * 18, w + 220 + px * -24, 460 + py * 18, fill="#CFFFE2", outline="#7EE8B4")
                dream_bg.create_oval(w / 2 - 260, h - 220, w / 2 + 260, h + 120, fill="#FFB7E8", outline="#FF7EDB")

                # Slow cloud layer.
                for i in range(7):
                    base_x = (i * 210 - (t * (1 + i % 2)) % (w + 240)) - 120 + px * (12 + i)
                    base_y = 64 + (i % 3) * 52 + py * (6 + i)
                    for j, r in enumerate((38, 54, 44, 32)):
                        x = base_x + j * 42
                        dream_bg.create_oval(x, base_y - r / 2, x + r * 2, base_y + r, fill="#FFFFFF", outline="#D9C7FF")

                # Floating stars, hearts and pixel sparkles.
                glyphs = ["✦", "✧", "★", "♡", "◇", "☁"]
                for i in range(42):
                    x = (i * 83 + t * (1 + i % 4)) % (w + 80) - 40 + px * (4 + i % 9)
                    y = (i * 47 + (t // 2) * (1 + i % 3)) % (h + 80) - 40 + py * (3 + i % 7)
                    color = ["#FFFFFF", "#FFF4B2", "#FF7EDB", "#B99CFF", "#5EE8A5"][i % 5]
                    font_size = 9 + (i % 5)
                    dream_bg.create_text(x, y, text=glyphs[i % len(glyphs)], fill=color, font=("Verdana", font_size, "bold"))

                # Subtle retro grain.
                for i in range(38):
                    x = (i * 131 + t * 7) % w
                    y = (i * 71 + t * 5) % h
                    dream_bg.create_rectangle(x, y, x + 1, y + 1, fill="#FFFFFF", outline="")

                # Cursor trail / click sparkles.
                next_sparkles = []
                for sp in list(bg_state.get("sparkles", [])):
                    x, y, life, glyph = sp
                    if life <= 0:
                        continue
                    dream_bg.create_text(x, y - (10 - life), text=glyph, fill="#FFFFFF", font=("Verdana", 12 + life % 5, "bold"))
                    next_sparkles.append((x, y, life - 1, glyph))
                bg_state["sparkles"] = next_sparkles
                bg_state["tick"] = t + 1
                root.after(90, _draw_dream_background)
            except Exception:
                pass

        def _remember_mouse(event: Any) -> None:
            bg_state["mouse_x"] = getattr(event, "x", 0)
            bg_state["mouse_y"] = getattr(event, "y", 0)

        def _spawn_click_sparkles(event: Any) -> None:
            play_click_sound()
            x = getattr(event, "x", 0)
            y = getattr(event, "y", 0)
            sparkles = list(bg_state.get("sparkles", []))
            for glyph in ("✦", "♡", "✧", "★"):
                sparkles.append((x, y, 10, glyph))
            bg_state["sparkles"] = sparkles[-48:]

        root.bind("<Motion>", _remember_mouse)
        root.bind("<Button-1>", _spawn_click_sparkles, add="+")
        root.after(120, _draw_dream_background)

        header = tk.Frame(root, bg=colors["accent_soft"], bd=4, relief="ridge")
        header.grid(row=0, column=0, columnspan=3, sticky="we", padx=10, pady=(10, 8))
        tk.Label(
            header,
            text="✧ Kirby Ate your VOD ! ✧",
            bg=colors["accent_soft"],
            fg=colors["ink"],
            font=("Verdana", 15, "bold"),
            padx=10,
            pady=8,
        ).pack(side="left")
        keyv_label = tk.Label(
            header,
            text="● EN LIGNE  MSN ✦ XP ✦ KEYV",
            bg=colors["sun_soft"],
            fg="#2C8A55",
            font=("Tahoma", 9, "bold"),
            padx=10,
            pady=4,
        )
        keyv_label.pack(side="right")
        keyv_label.bind("<Enter>", lambda _event: keyv_label.configure(text="Kirby Eats your VOD"))
        keyv_label.bind("<Leave>", lambda _event: keyv_label.configure(text="● EN LIGNE  MSN ✦ XP ✦ KEYV"))

        def ui_button(parent: Any, text: str, cmd: Any, primary: bool = False) -> Any:
            base_bg = colors["accent"] if primary else colors["sun"]
            hover_bg = "#FFFFFF" if primary else colors["mint"]
            btn = tk.Button(
                parent,
                text=f"✦ {text} ✦" if primary else text,
                command=lambda: (play_click_sound(), cmd()),
                bg=base_bg,
                fg="#FFFFFF" if primary else colors["ink"],
                activebackground=colors["accent_soft"] if primary else colors["sun_soft"],
                activeforeground=colors["ink"],
                bd=4,
                relief="raised",
                padx=12,
                pady=5,
                cursor="hand2",
                font=("Verdana", 9, "bold"),
            )

            def _enter(_event: Any) -> None:
                play_hover_sound()
                btn.configure(bg=hover_bg, relief="ridge")

            def _leave(_event: Any) -> None:
                btn.configure(bg=base_bg, relief="raised")

            def _press(_event: Any) -> None:
                btn.configure(relief="sunken", padx=14)

            def _release(_event: Any) -> None:
                btn.configure(relief="ridge", padx=12)

            btn.bind("<Enter>", _enter)
            btn.bind("<Leave>", _leave)
            btn.bind("<ButtonPress-1>", _press, add="+")
            btn.bind("<ButtonRelease-1>", _release, add="+")
            return btn

        def make_label(text: str, r: int, c: int) -> None:
            tk.Label(form, text=f"♡ {text}", bg=colors["panel_alt"], fg=colors["ink"], font=("Tahoma", 9, "bold"), bd=1, relief="flat").grid(row=r, column=c, sticky="w", padx=8, pady=6)

        tabs_bar = tk.Frame(root, bg=colors["sky"])
        tabs_bar.grid(row=1, column=0, columnspan=3, sticky="w", padx=10, pady=(0, 0))

        tabs_body = tk.Frame(root, bg=colors["sky"])
        tabs_body.grid(row=2, column=0, columnspan=3, sticky="nw", padx=10, pady=(0, 0))

        batch_tab = tk.Frame(tabs_body, bg=colors["sky"])
        actions_tab = tk.Frame(tabs_body, bg=colors["sky"])
        tab_buttons: dict[str, Any] = {}

        def show_tab(name: str) -> None:
            for frame in (batch_tab, actions_tab):
                frame.grid_forget()
            active_frame = batch_tab if name == "batch" else actions_tab
            active_frame.grid(row=0, column=0, sticky="nw")
            for key, btn in tab_buttons.items():
                active = key == name
                btn.configure(
                    bg=colors["accent_soft"] if active else colors["sun_soft"],
                    fg=colors["ink"],
                    relief="sunken" if active else "ridge",
                )

        tab_buttons["batch"] = tk.Button(
            tabs_bar,
            text="☁ Batch génération ✧",
            command=lambda: show_tab("batch"),
            bg=colors["accent_soft"],
            fg=colors["ink"],
            activebackground=colors["accent_soft"],
            activeforeground=colors["ink"],
            bd=4,
            relief="sunken",
            padx=12,
            pady=5,
            cursor="hand2",
            font=("Verdana", 10, "bold"),
        )
        tab_buttons["batch"].pack(side="left", padx=(0, 4), pady=(0, 6))
        tab_buttons["actions"] = tk.Button(
            tabs_bar,
            text="♡ Actions timeline ★",
            command=lambda: show_tab("actions"),
            bg=colors["sun_soft"],
            fg=colors["ink"],
            activebackground=colors["sun_soft"],
            activeforeground=colors["ink"],
            bd=4,
            relief="ridge",
            padx=12,
            pady=5,
            cursor="hand2",
            font=("Verdana", 10, "bold"),
        )
        tab_buttons["actions"].pack(side="left", padx=(0, 4), pady=(0, 6))

        companion = tk.Frame(tabs_bar, bg=colors["panel_alt"], bd=3, relief="ridge")
        companion.pack(side="right", padx=(8, 0), pady=(0, 6))
        companion_orb = tk.Canvas(companion, width=44, height=44, bg=colors["panel_alt"], highlightthickness=0, bd=0)
        companion_orb.pack(side="left", padx=(6, 4), pady=4)
        companion_text = tk.Label(
            companion,
            text="ange digital\nhumeur: rêveuse",
            bg=colors["panel_alt"],
            fg=colors["ink"],
            font=("Tahoma", 8, "bold"),
            justify="left",
        )
        companion_text.pack(side="left", padx=(0, 8), pady=4)

        def _pulse_companion(step: int = 0) -> None:
            try:
                companion_orb.delete("all")
                r = 13 + (step % 8 if step % 16 < 8 else 16 - step % 16)
                companion_orb.create_oval(22 - r, 22 - r, 22 + r, 22 + r, fill="#FFFFFF", outline=colors["accent"], width=2)
                companion_orb.create_oval(14, 10, 30, 28, fill=colors["aero"], outline="")
                companion_orb.create_text(22, 22, text="♡", fill=colors["accent"], font=("Verdana", 13, "bold"))
                companion_orb.create_text(36, 9, text="✦", fill=colors["sun"], font=("Verdana", 10, "bold"))
                root.after(160, lambda: _pulse_companion(step + 1))
            except Exception:
                pass

        root.after(180, _pulse_companion)

        tabs_body.columnconfigure(0, weight=1)
        tabs_body.rowconfigure(0, weight=0)
        batch_tab.columnconfigure(1, weight=1)

        form = tk.LabelFrame(batch_tab, text="☁ Paramètres du batch ☁", bg=colors["panel_alt"], fg=colors["ink"], bd=4, relief="ridge", padx=10, pady=10, font=("Verdana", 10, "bold"))
        form.grid(row=0, column=0, columnspan=3, sticky="we", padx=0, pady=(0, 8))

        make_label("Dossier de sortie", 0, 0)
        output_var = tk.StringVar(value=state["output_dir"])
        tk.Entry(form, textvariable=output_var, width=80, bd=3, relief="sunken", bg="#FFFFFF", fg=colors["ink"], insertbackground=colors["accent"], font=("Tahoma", 9)).grid(row=0, column=1, padx=8, pady=6, sticky="we")

        def browse_output() -> None:
            p = filedialog.askdirectory(title="Sélectionner le dossier de sortie", initialdir=output_var.get())
            if p:
                output_var.set(p)

        ui_button(form, "Parcourir", browse_output).grid(row=0, column=2, padx=8, pady=6)

        make_label("Dossier VOD de secours", 1, 0)
        vod_dir_var = tk.StringVar(value=state["vod_dir"])
        tk.Entry(form, textvariable=vod_dir_var, width=80, bd=3, relief="sunken", bg="#FFFFFF", fg=colors["ink"], insertbackground=colors["accent"], font=("Tahoma", 9)).grid(row=1, column=1, padx=8, pady=6, sticky="we")

        def browse_vod_dir() -> None:
            p = filedialog.askdirectory(title="Sélectionner le dossier VOD", initialdir=vod_dir_var.get())
            if p:
                vod_dir_var.set(p)

        ui_button(form, "Parcourir", browse_vod_dir).grid(row=1, column=2, padx=8, pady=6)

        make_label("Preset rendu", 2, 0)
        render_var = tk.StringVar(value=state["render_preset"])
        tk.Entry(form, textvariable=render_var, width=40, bd=3, relief="sunken", bg="#FFFFFF", fg=colors["ink"], insertbackground=colors["accent"], font=("Tahoma", 9)).grid(row=2, column=1, padx=8, pady=6, sticky="w")

        make_label("Profil batch", 3, 0)
        profile_var = tk.StringVar(value=state["profile"])
        profile_menu = tk.OptionMenu(form, profile_var, *["valo", "jeu", "react"])
        profile_menu.config(bg=colors["sun"], fg=colors["ink"], bd=2, relief="raised", activebackground=colors["sun_soft"]) 
        profile_menu.grid(row=3, column=1, padx=8, pady=6, sticky="w")

        make_label("Preset", 4, 0)
        preset_var = tk.StringVar(value=state["preset_id"])
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

        ui_button(form, "Charger", load_current_preset).grid(row=4, column=2, padx=8, pady=6, sticky="w")

        make_label("Recherche transcript", 5, 0)
        query_var = tk.StringVar(value="")
        tk.Entry(form, textvariable=query_var, width=80, bd=3, relief="sunken", bg="#FFFFFF", fg=colors["ink"], insertbackground=colors["accent"], font=("Tahoma", 9)).grid(row=5, column=1, padx=8, pady=6, sticky="we")

        transcript_select_var = tk.BooleanVar(value=False)
        preview_safe_quality_var = tk.BooleanVar(value=True)
        subtitle_template_var = tk.StringVar(value=state["subtitle_template_name"])
        subtitle_offset_ms_var = tk.StringVar(value=state["subtitle_offset_ms"])

        def open_keywords_editor() -> None:
            try:
                root_dir = _repo_root()
                lexicon_path = root_dir / "config" / "transcript_lexicon_user.json"
                default_categories = {"drole": {}, "clivant": {}, "etonnant": {}}
                data: dict[str, Any] = {"version": 1, "updated_at": "", "categories": default_categories}
                if lexicon_path.exists():
                    try:
                        with lexicon_path.open("r", encoding="utf-8") as f:
                            loaded = json.load(f)
                        if isinstance(loaded, dict):
                            data = loaded
                    except Exception:
                        pass

                cats = data.get("categories", {}) if isinstance(data.get("categories", {}), dict) else {}
                for cat_name in ("drole", "clivant", "etonnant"):
                    if not isinstance(cats.get(cat_name), dict):
                        cats[cat_name] = {}

                top = tk.Toplevel(root)
                top.title("Mots-clés transcript")
                top.geometry("780x560")
                top.configure(bg=colors["panel_alt"])
                top.transient(root)

                frame = tk.Frame(top, bg=colors["panel_alt"])
                frame.pack(fill="both", expand=True, padx=10, pady=10)

                text_boxes: dict[str, Any] = {}
                order = ("drole", "clivant", "etonnant")
                for idx, cat_name in enumerate(order):
                    section = tk.LabelFrame(frame, text=f"✧ {cat_name} ✧", bg=colors["panel"], fg=colors["ink"], bd=4, relief="ridge")
                    section.grid(row=0, column=idx, padx=6, pady=6, sticky="nsew")
                    frame.grid_columnconfigure(idx, weight=1)
                    frame.grid_rowconfigure(0, weight=1)

                    txt = tk.Text(section, width=24, height=24, bg=colors["sun_soft"], fg=colors["ink"], bd=3, relief="sunken", insertbackground=colors["accent"], font=("Tahoma", 9))
                    txt.pack(fill="both", expand=True, padx=6, pady=6)
                    rows: list[str] = []
                    table = cats.get(cat_name, {}) if isinstance(cats, dict) else {}
                    if isinstance(table, dict):
                        for k, v in sorted(table.items(), key=lambda kv: kv[0]):
                            rows.append(f"{k}={v}")
                    txt.insert("1.0", "\n".join(rows))
                    text_boxes[cat_name] = txt

                hint = tk.Label(
                    top,
                    text="Format: mot=poids (un par ligne). Exemple: incroyable=1.2",
                    bg=colors["panel_alt"],
                    fg=colors["ink"],
                    anchor="w",
                )
                hint.pack(fill="x", padx=10, pady=(0, 6))

                def save_keywords() -> None:
                    updated_categories: dict[str, dict[str, float]] = {"drole": {}, "clivant": {}, "etonnant": {}}
                    for cat_name, box in text_boxes.items():
                        raw = box.get("1.0", "end").splitlines()
                        for line_no, line in enumerate(raw, start=1):
                            s = line.strip()
                            if not s:
                                continue
                            if "=" not in s:
                                messagebox.showerror("Short Editor", f"{cat_name} ligne {line_no}: format attendu mot=poids")
                                return
                            key, value = s.split("=", 1)
                            token = key.strip().lower()
                            if not token:
                                messagebox.showerror("Short Editor", f"{cat_name} ligne {line_no}: mot-clé vide")
                                return
                            try:
                                weight = float(value.strip())
                            except Exception:
                                messagebox.showerror("Short Editor", f"{cat_name} ligne {line_no}: poids invalide")
                                return
                            updated_categories[cat_name][token] = round(weight, 3)

                    data["version"] = int(data.get("version", 1) or 1)
                    data["categories"] = updated_categories
                    data["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
                    lexicon_path.parent.mkdir(parents=True, exist_ok=True)
                    with lexicon_path.open("w", encoding="utf-8") as f:
                        json.dump(data, f, indent=2, ensure_ascii=False)
                        f.write("\n")
                    set_status("Mots-clés transcript enregistrés", warnings=[])
                    messagebox.showinfo("Short Editor", f"Enregistré: {lexicon_path}")

                controls = tk.Frame(top, bg=colors["panel_alt"])
                controls.pack(fill="x", padx=10, pady=(0, 8))
                ui_button(controls, "Enregistrer", save_keywords, primary=True).pack(side="right", padx=4)
                ui_button(controls, "Fermer", top.destroy, primary=False).pack(side="right", padx=4)
            except Exception as exc:
                set_status(f"Erreur éditeur mots-clés: {exc}")

        transcript_opts = tk.Frame(form, bg=colors["panel_alt"])
        transcript_opts.grid(row=6, column=1, padx=8, pady=6, sticky="w")
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

        make_label("Modèle de sous-titres", 7, 0)
        subtitle_template_menu = tk.OptionMenu(form, subtitle_template_var, *subtitle_template_options)
        subtitle_template_menu.config(bg=colors["sun"], fg=colors["ink"], bd=2, relief="raised", activebackground=colors["sun_soft"])
        subtitle_template_menu.grid(row=7, column=1, padx=8, pady=6, sticky="w")

        make_label("Décalage sous-titres (ms)", 8, 0)
        tk.Entry(form, textvariable=subtitle_offset_ms_var, width=12, bd=3, relief="sunken", bg="#FFFFFF", fg=colors["ink"], insertbackground=colors["accent"], font=("Tahoma", 9)).grid(row=8, column=1, padx=8, pady=6, sticky="w")

        master_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            form,
            text="Ajouter le rendu MASTER_REVIEW",
            variable=master_var,
            bg=colors["panel_alt"],
            fg=colors["ink"],
            selectcolor=colors["sun_soft"],
            activebackground=colors["panel_alt"],
        ).grid(row=9, column=1, padx=8, pady=6, sticky="w")

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
                set_status("Détection impossible: aucun projet ouvert")
                return
            timeline = _safe_call(project, "GetCurrentTimeline")
            if not timeline:
                set_status("Détection impossible: aucune timeline active")
                return

            mode_label = detect_mode_var.get().strip()
            mode = "current" if mode_label == "Frame actuelle" else "first"
            detect_mode_label.config(text=f"Détection: {mode_label}")
            if mode == "current":
                cam_item = _get_item_at_current_frame(timeline, 1)
                game_item = _get_item_at_current_frame(timeline, 2)
            else:
                cam_item = _get_first_item_on_track(timeline, 1)
                game_item = _get_first_item_on_track(timeline, 2)

            _log(f"Detect preset mode={mode} mapping camera->T1 gameplay->T2")

            if not cam_item:
                set_status("Détection impossible: aucun clip sur la piste 1")
                return
            if not game_item:
                set_status("Détection impossible: aucun clip sur la piste 2")
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

            set_status("Preset détecté depuis la timeline active (piste 1=caméra, piste 2=gameplay)")

        ui_button(preset_toolbar, "Détecter le preset", detect_preset_from_timeline).pack(side="left", padx=(0, 6))

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

        status_var = tk.StringVar(value="Prêt")
        last_warnings: list[str] = []

        def open_warnings_window() -> None:
            if not last_warnings:
                return
            top = tk.Toplevel(root)
            top.title("Avertissements batch")
            top.geometry("980x420")
            top.configure(bg=colors["panel_alt"])

            tk.Label(top, text=f"{len(last_warnings)} avertissement(s)", bg=colors["panel_alt"], fg=colors["ink"], font=("Segoe UI", 10, "bold"), anchor="w").pack(fill="x", padx=10, pady=(10, 4))

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
                m = re.search(r"\(\d+\s+(?:warnings|avertissements)\)", message)
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
                    set_status(f"Erreur feedback: {exc}")

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
            set_status(f"Preset supprimé: {pid}. Preset actif: {replacement}")

        def apply_preset_now(scope_mode: str) -> None:
            pid = preset_var.get().strip()
            selected_preset = dict((presets_data.get("presets", {}) or {}).get(pid, {}))
            if not selected_preset:
                set_status(f"Preset introuvable: {pid}")
                return
            ok, msg = _apply_preset_to_selected_clip(resolve, selected_preset, scope_mode=scope_mode)
            set_status(msg)
            if ok:
                _log(f"Apply preset success: preset={pid} scope={scope_mode}")
            else:
                _log(f"Apply preset failed: preset={pid} scope={scope_mode} msg={msg}")

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
                messagebox.showinfo("Short Editor", f"Preset enregistré sous: {nid}")

            ui_button(top, "Enregistrer", do_save).grid(row=1, column=1, sticky="e", padx=8, pady=8)

        ui_button(editor_fields, "Enregistrer", save_overwrite).grid(row=row + 1, column=1, padx=6, pady=8)
        ui_button(editor_fields, "Enregistrer sous", save_as_new).grid(row=row + 1, column=2, padx=6, pady=8)
        ui_button(editor_fields, "Supprimer le preset", delete_selected_preset).grid(row=row + 1, column=3, padx=6, pady=8)
        ui_button(editor_fields, "Appliquer au clip sélectionné", apply_to_selected_clip_now, primary=False).grid(row=row + 2, column=0, columnspan=2, padx=6, pady=8, sticky="w")

        load_editor_from_preset(preset_var.get().strip())

        status_text = tk.Text(root, width=72, height=1, bg=colors["sun_soft"], fg=colors["ink"], bd=3, relief="sunken", wrap="none", cursor="hand2", font=("Tahoma", 9, "bold"))
        status_text.grid(row=4, column=0, columnspan=3, sticky="e", padx=10, pady=(0, 12))
        status_text.tag_configure("clickable_warning", foreground="#1D47C8", underline=1)
        status_text.tag_bind("clickable_warning", "<Button-1>", lambda _e: open_warnings_window())
        status_text.tag_bind("clickable_warning", "<Enter>", lambda _e: status_text.config(cursor="hand2"))
        status_text.tag_bind("clickable_warning", "<Leave>", lambda _e: status_text.config(cursor="arrow"))
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
                "vod_dir": vod_dir_var.get().strip(),
                "render_preset": render_var.get().strip() or "H264_Shorts_1080x1920_60fps",
                "profile": profile_var.get().strip() or "valo",
                "preset_id": preset_var.get().strip() or state["preset_id"],
                "query": query_var.get().strip(),
                "use_transcript_for_selection": bool(transcript_select_var.get()),
                "render_master": bool(master_var.get()),
                "strict_manifest": False,
                "require_subtitles": False,
                "preview_safe_quality": bool(preview_safe_quality_var.get()),
                "generate_optimized_media_quality": True,
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

            progress_top = tk.Toplevel(root)
            progress_top.title("Short Editor")
            progress_top.geometry("420x120")
            progress_top.configure(bg=colors["panel_alt"])
            progress_top.transient(root)
            progress_top.attributes("-topmost", True)
            progress_top.grab_set()
            progress_top.protocol("WM_DELETE_WINDOW", lambda: None)

            progress_text = tk.StringVar(
                value="Génération des sous-titres, cela peut prendre quelques minutes..."
                if require_subtitles
                else "Génération du batch..."
            )
            progress_stage = tk.StringVar(value="Batch")
            progress_pct = tk.StringVar(value="0%")
            tk.Label(
                progress_top,
                textvariable=progress_text,
                bg=colors["panel_alt"],
                fg=colors["ink"],
                font=("Segoe UI", 10, "bold"),
                wraplength=380,
                justify="left",
                padx=12,
                pady=12,
            ).pack(fill="both", expand=True)

            tk.Label(
                progress_top,
                textvariable=progress_stage,
                bg=colors["panel_alt"],
                fg=colors["ink"],
                font=("Segoe UI", 9, "bold"),
                pady=2,
            ).pack()
            tk.Label(
                progress_top,
                textvariable=progress_pct,
                bg=colors["panel_alt"],
                fg=colors["ink"],
                font=("Segoe UI", 9),
                pady=0,
            ).pack()
            progress_bar = tk.Canvas(progress_top, width=360, height=16, bg=colors["panel_alt"], highlightthickness=0, bd=0)
            progress_bar.pack(pady=(4, 10))
            progress_bar.create_rectangle(2, 2, 358, 14, fill=colors["sun_soft"], outline=colors["ink"], width=1)
            progress_fill = progress_bar.create_rectangle(3, 3, 3, 13, fill=colors["sun"], outline=colors["sun"], width=0)

            result_box: dict[str, Any] = {"result": None, "error": None}
            progress_box: dict[str, Any] = {"stage": "Batch", "current": 0, "total": 1, "detail": "Initialisation"}

            def _worker_progress(stage: str, current: int, total: int, detail: str = "") -> None:
                progress_box["stage"] = stage or "Batch"
                progress_box["current"] = max(0, int(current))
                progress_box["total"] = max(1, int(total))
                progress_box["detail"] = detail or ""

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
                    progress_text.set("Génération des sous-titres... toujours en cours, merci de patienter.")
                stage = str(progress_box.get("stage", "Batch"))
                current = int(progress_box.get("current", 0))
                total = max(1, int(progress_box.get("total", 1)))
                detail = str(progress_box.get("detail", "")).strip()
                pct = max(0, min(100, int(round((current / total) * 100))))
                progress_stage.set(f"Etape: {stage}")
                progress_pct.set(f"{pct}% ({current}/{total})")
                progress_text.set(detail or ("Génération en cours..." if not require_subtitles else "Génération + sous-titres en cours..."))
                x2 = 3 + int((355 * pct) / 100)
                progress_bar.coords(progress_fill, 3, 3, max(3, x2), 13)
                try:
                    progress_top.update_idletasks()
                    progress_top.update()
                except Exception:
                    pass
                time.sleep(0.03)

            try:
                progress_top.grab_release()
            except Exception:
                pass
            try:
                progress_top.destroy()
            except Exception:
                pass

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

            progress_top = tk.Toplevel(root)
            progress_top.title("Short Editor")
            progress_top.geometry("420x120")
            progress_top.configure(bg=colors["panel_alt"])
            progress_top.transient(root)
            progress_top.attributes("-topmost", True)
            progress_top.grab_set()
            progress_top.protocol("WM_DELETE_WINDOW", lambda: None)
            progress_text = tk.StringVar(value="Transcription de la source du clip sélectionné...")
            tk.Label(
                progress_top,
                textvariable=progress_text,
                bg=colors["panel_alt"],
                fg=colors["ink"],
                font=("Segoe UI", 10, "bold"),
                wraplength=380,
                justify="left",
                padx=12,
                pady=12,
            ).pack(fill="both", expand=True)

            result_box: dict[str, Any] = {"result": None, "error": None}

            def _worker_single_sub() -> None:
                try:
                    from short_editor.subtitles import generate_srt_for_clip
                    from short_editor.transcription import ensure_transcript

                    ok_ctx, ctx_msg, ctx = _selected_clip_subtitle_context(resolve)
                    if not ok_ctx:
                        result_box["result"] = {"ok": False, "message": ctx_msg}
                        return
                    source_path = Path(str(ctx["source_path"]))
                    clip_start = float(ctx["clip_start"])
                    clip_end = float(ctx["clip_end"])
                    timeline = ctx["timeline"]
                    media_pool = ctx["media_pool"]
                    timeline_name = str(ctx["timeline_name"])
                    item_name = str(ctx["item_name"])

                    cfg = _load_pipeline_config(_repo_root())
                    transcript_path = ensure_transcript(source_path, cfg, _repo_root() / "output" / "transcripts")
                    subtitle_dir = _repo_root() / "output" / "subtitles" / "manual"
                    out_name = _safe_name_token(item_name or timeline_name, limit=120)
                    out_srt = subtitle_dir / f"{out_name}.srt"
                    ok_srt = generate_srt_for_clip(transcript_path, clip_start, clip_end, out_srt, cfg.get("captions", {}))
                    if not ok_srt:
                        result_box["result"] = {"ok": False, "message": "Aucun contenu de sous-titres trouvé pour la plage du clip sélectionné."}
                        return

                    try:
                        offset_ms_value = int(float(str(subtitle_offset_ms_var.get()).strip() or "-500"))
                    except Exception:
                        offset_ms_value = -500
                    ok_import, import_msg = _import_subtitles_to_timeline(
                        project=ctx["project"],
                        media_pool=media_pool,
                        timeline=timeline,
                        subtitle_path=out_srt,
                        template_name=str(subtitle_template_var.get().strip() or SUBTITLE_TEMPLATE_AUTO_LABEL),
                        offset_ms=offset_ms_value,
                    )
                    if not ok_import:
                        result_box["result"] = {
                            "ok": False,
                            "message": "Mode strict: impossible d'appliquer le sous-titre Text+ autonome.",
                            "warnings": [f"SRT généré sur disque: {out_srt}", f"Erreur d'import: {import_msg}"],
                        }
                        return
                    result_box["result"] = {
                        "ok": True,
                        "message": f"Sous-titre appliqué sur la timeline (strict): {out_srt.name}",
                    }
                except Exception as exc:
                    result_box["error"] = exc

            worker = threading.Thread(target=_worker_single_sub, daemon=True)
            worker.start()
            ticks = 0
            while worker.is_alive():
                ticks += 1
                if ticks % 100 == 0:
                    progress_text.set("Traitement des sous-titres du clip sélectionné toujours en cours...")
                try:
                    progress_top.update_idletasks()
                    progress_top.update()
                except Exception:
                    pass
                time.sleep(0.03)

            try:
                progress_top.grab_release()
            except Exception:
                pass
            try:
                progress_top.destroy()
            except Exception:
                pass

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

            progress_top = tk.Toplevel(root)
            progress_top.title("Couper les silences")
            progress_top.geometry("460x130")
            progress_top.configure(bg=colors["panel_alt"])
            progress_top.transient(root)
            progress_top.attributes("-topmost", True)
            progress_top.grab_set()
            progress_top.protocol("WM_DELETE_WINDOW", lambda: None)
            progress_text = tk.StringVar(value="Analyse audio en cours...")
            progress_detail = tk.StringVar(value="Préparation")
            tk.Label(
                progress_top,
                textvariable=progress_text,
                bg=colors["panel_alt"],
                fg=colors["ink"],
                font=("Verdana", 10, "bold"),
                wraplength=420,
                justify="left",
                padx=12,
                pady=10,
            ).pack(fill="x")
            tk.Label(
                progress_top,
                textvariable=progress_detail,
                bg=colors["panel_alt"],
                fg=colors["ink"],
                font=("Tahoma", 9, "bold"),
                padx=12,
                pady=2,
            ).pack(fill="x")
            progress_bar = tk.Canvas(progress_top, width=390, height=16, bg=colors["panel_alt"], highlightthickness=0, bd=0)
            progress_bar.pack(pady=(6, 10))
            progress_bar.create_rectangle(2, 2, 388, 14, fill=colors["sun_soft"], outline=colors["ink"], width=1)
            progress_fill = progress_bar.create_rectangle(3, 3, 3, 13, fill=colors["accent_soft"], outline=colors["accent_soft"], width=0)

            result_box: dict[str, Any] = {"result": None, "error": None}
            progress_box: dict[str, Any] = {"current": 0, "total": 1, "detail": "Initialisation"}

            def _set_progress(current: int, total: int, detail: str) -> None:
                progress_box["current"] = max(0, int(current))
                progress_box["total"] = max(1, int(total))
                progress_box["detail"] = detail

            def _worker_cut() -> None:
                try:
                    result_box["result"] = _run_silence_cut(scope, _set_progress)
                except Exception as exc:
                    result_box["error"] = exc

            def _run_silence_cut(selected_scope: str, progress_cb: Any) -> dict[str, Any]:
                root_dir = _repo_root()
                cfg = _load_pipeline_config(root_dir)
                energy_cache: dict[str, tuple[list[tuple[float, float]], str]] = {}
                warnings_out: list[str] = []
                total_cuts = 0
                total_removed = 0.0
                timelines_created = 0

                pm = _safe_call(resolve, "GetProjectManager")
                project = _safe_call(pm, "GetCurrentProject") if pm else None
                if not project:
                    return {"ok": False, "message": "Aucun projet Resolve ouvert.", "warnings": []}
                media_pool = _safe_call(project, "GetMediaPool")
                if not media_pool:
                    return {"ok": False, "message": "Media Pool indisponible.", "warnings": []}
                selected_preset = dict((presets_data.get("presets", {}) or {}).get(preset_var.get().strip(), {}))
                if not selected_preset:
                    return {"ok": False, "message": f"Preset introuvable: {preset_var.get().strip()}", "warnings": []}

                def _process_one(source_path: Path, start_s: float, end_s: float, base_name: str, idx: int, total: int) -> None:
                    nonlocal total_cuts, total_removed, timelines_created
                    progress_cb(idx, total, f"Analyse audio: {base_name}")
                    energies, audio_label, audio_warnings = _load_audio_energy_for_silence_cut(root_dir, source_path, cfg, energy_cache)
                    warnings_out.extend(audio_warnings)
                    if not energies:
                        warnings_out.append(f"{base_name}: analyse audio vide, clip inchangé.")
                        return
                    segments, stats = _detect_audible_segments_for_silence_cut(energies, start_s, end_s, cfg)
                    cuts = int(stats.get("cuts", 0.0))
                    removed = float(stats.get("removed_seconds", 0.0))
                    if cuts <= 0 or removed <= 0.05:
                        warnings_out.append(f"{base_name}: aucun silence gênant détecté ({audio_label}).")
                        return
                    timeline_name = _suffix_timeline_name(base_name)
                    progress_cb(idx, total, f"Création timeline: {timeline_name}")
                    tl, create_warnings = _create_silence_cut_timeline(root_dir, project, media_pool, source_path, timeline_name, segments, selected_preset)
                    warnings_out.extend(create_warnings)
                    if tl is None:
                        warnings_out.append(f"{base_name}: création timeline silence_cut échouée.")
                        return
                    timelines_created += 1
                    total_cuts += cuts
                    total_removed += removed
                    _log(f"silence_cut_created name={timeline_name} cuts={cuts} removed={removed:.3f}s segments={len(segments)} audio={audio_label}")

                if selected_scope == "Clip sélectionné":
                    ok_ctx, ctx_msg, ctx = _selected_clip_subtitle_context(resolve)
                    if not ok_ctx:
                        return {"ok": False, "message": ctx_msg, "warnings": []}
                    source_path = Path(str(ctx.get("source_path", "")))
                    if not source_path.exists():
                        return {"ok": False, "message": f"Source introuvable: {source_path}", "warnings": []}
                    item_name = str(ctx.get("item_name") or ctx.get("timeline_name") or source_path.stem)
                    _process_one(source_path, float(ctx["clip_start"]), float(ctx["clip_end"]), item_name, 1, 1)
                else:
                    manifest_value = session_ref.get("manifest") or default_manifest
                    if not manifest_value:
                        return {"ok": False, "message": "Aucun manifest disponible. Génère d'abord un batch.", "warnings": []}
                    manifest_path = Path(manifest_value)
                    if not manifest_path.exists():
                        return {"ok": False, "message": f"Manifest introuvable: {manifest_path}", "warnings": []}
                    batch_id, plans = _parse_manifest(manifest_path)
                    if not plans:
                        return {"ok": False, "message": "Aucun clip valide dans le manifest.", "warnings": []}
                    detected_vod = session_ref.get("detected_vod")
                    for idx, plan in enumerate(plans, start=1):
                        raw_src = Path(plan.source_path)
                        source_path = raw_src if raw_src.is_absolute() else (root_dir / raw_src).resolve()
                        if not source_path.exists() and detected_vod is not None and Path(detected_vod).exists():
                            source_path = Path(detected_vod)
                        if not source_path.exists():
                            warnings_out.append(f"{plan.display_name}: source introuvable, skip.")
                            continue
                        base_name = plan.timeline_name or f"{batch_id}__{plan.display_name or plan.clip_id}"
                        _process_one(source_path, float(plan.start_seconds), float(plan.end_seconds), base_name, idx, len(plans))

                if timelines_created == 0:
                    return {"ok": False, "message": "Aucune timeline silence_cut créée.", "warnings": warnings_out}
                warnings_out.append("Sous-titres: régénère-les après coupe si la timeline originale en avait.")
                return {
                    "ok": True,
                    "message": f"Coupe des silences terminée: {timelines_created} timeline(s), {total_cuts} cut(s), {total_removed:.1f}s supprimée(s).",
                    "warnings": warnings_out,
                }

            worker = threading.Thread(target=_worker_cut, daemon=True)
            worker.start()
            while worker.is_alive():
                cur = int(progress_box.get("current", 0))
                total = max(1, int(progress_box.get("total", 1)))
                pct = max(0, min(100, int(round((cur / total) * 100))))
                progress_text.set("Coupe automatique des silences en cours...")
                progress_detail.set(str(progress_box.get("detail", "Analyse")))
                progress_bar.coords(progress_fill, 3, 3, 3 + int((385 * pct) / 100), 13)
                try:
                    progress_top.update_idletasks()
                    progress_top.update()
                except Exception:
                    pass
                time.sleep(0.03)

            try:
                progress_top.grab_release()
            except Exception:
                pass
            try:
                progress_top.destroy()
            except Exception:
                pass

            if result_box["error"] is not None:
                err = result_box["error"]
                set_status(f"Échec coupe des silences: {err}", warnings=[str(err)])
                return
            result = result_box.get("result") or {}
            msg = str(result.get("message", "Coupe des silences terminée."))
            set_status(msg, list(result.get("warnings", []) or []))
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
        ).grid(row=0, column=0, columnspan=3, sticky="we", padx=4, pady=(0, 6))
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
        silence_panel.columnconfigure(2, weight=1)

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
    value = project.GetSetting(key)
    try:
        return int(float(value))
    except Exception:
        return fallback


def _fps_from_project(project: Any) -> int:
    fps = _safe_int_from_project_setting(project, "timelineFrameRate", DEFAULT_FPS)
    if fps <= 0:
        return DEFAULT_FPS
    return fps


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


@dataclass
class ClipPlan:
    clip_id: str
    display_name: str
    timeline_name: str
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


def _assign_timeline_names_dict(clips: list[dict[str, Any]], batch_id: str) -> None:
    used_timeline_names: set[str] = set()
    for c in clips:
        display = _safe_name_token(str(c.get("display_name") or c.get("clip_id") or "clip"), limit=84)
        timeline_name = f"{batch_id}__{display}"
        if timeline_name in used_timeline_names:
            dup_idx = 2
            base_name = timeline_name
            while f"{base_name} ({dup_idx})" in used_timeline_names:
                dup_idx += 1
            timeline_name = f"{base_name} ({dup_idx})"
        used_timeline_names.add(timeline_name)
        c["timeline_name"] = timeline_name


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


def _generate_manifest_for_vod(
    root: Path,
    vod_path: Path,
    generate_subtitles: bool = True,
    use_transcript_for_selection: bool = False,
    progress_cb: Any | None = None,
    preset_id: str = "",
) -> Path:
    # Resolve scripts run from external script folders; ensure project root is importable.
    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)

    from short_editor.clip_builder import (
        build_chapter_candidates_with_skips,
        compute_quota,
        discover_fallback_candidates,
        trim_dead_air_on_boundaries,
        tag_overflow,
    )
    from short_editor.ingest import probe_vod
    from short_editor.models import ClipCandidate
    from short_editor.subtitles import generate_srt_for_clip
    from short_editor.transcription import ensure_transcript

    cfg = _load_pipeline_config(root)
    manifest = probe_vod(vod_path)
    if callable(progress_cb):
        progress_cb("Batch+Subtitles", 5, 100, "Analyse du VOD")
    transcript_path_cached = _transcript_path_for_vod(root, vod_path)
    transcript_exists = transcript_path_cached.exists()

    if use_transcript_for_selection:
        try:
            if transcript_exists:
                _log(f"transcript_selection_cache_hit vod={vod_path} transcript={transcript_path_cached}")
            else:
                ensure_transcript(vod_path, cfg, root / "output" / "transcripts")
                _log(f"transcript_selection_enabled vod={vod_path}")
        except Exception as exc:
            _log(f"transcript_selection_failed vod={vod_path} err={exc}")

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
    if callable(progress_cb):
        progress_cb("Batch+Subtitles", 20, 100, "Selection des clips terminee")

    batch_id = f"batch_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    clip_objs = []
    for i, c in enumerate(selected):
        c["clip_id"] = f"{vod_path.stem}__{c['clip_id']}"
        c["overflow"] = i >= max_quota
        c["subtitle_path"] = ""
        clip_objs.append(c)

    trim_candidates: list[ClipCandidate] = []
    for c in clip_objs:
        trim_candidates.append(
            ClipCandidate(
                clip_id=str(c.get("clip_id", "")),
                display_name=str(c.get("display_name", "")),
                source_path=str(c.get("source_path", manifest.source_path)),
                start_seconds=float(c.get("start_seconds", 0.0)),
                end_seconds=float(c.get("end_seconds", 0.0)),
                mandatory=bool(c.get("mandatory", False)),
                seed_type=str(c.get("seed_type", "unknown")),
                score=float(c.get("score", 0.0)),
                reason=str(c.get("reason", "")),
                overflow=bool(c.get("overflow", False)),
                subtitle_path=str(c.get("subtitle_path", "")),
            )
        )
    trim_warnings = trim_dead_air_on_boundaries(manifest, trim_candidates, cfg, root / "work")
    for i, tc in enumerate(trim_candidates):
        clip_objs[i]["start_seconds"] = tc.start_seconds
        clip_objs[i]["end_seconds"] = tc.end_seconds
        clip_objs[i]["reason"] = tc.reason
    manifest_warnings.extend(trim_warnings)

    _assign_simple_display_names_dict(clip_objs)
    _assign_timeline_names_dict(clip_objs, batch_id)

    captions_cfg = cfg.get("captions", {})
    captions_enabled = bool(captions_cfg.get("enabled", True)) and bool(generate_subtitles)
    if captions_enabled:
        def _generate_subtitles_once() -> int:
            _log(f"subtitle_generation_start vod={vod_path}")
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                with redirect_stderr(io.StringIO()):
                    if transcript_exists and transcript_path_cached.exists():
                        transcript_path = transcript_path_cached
                        _log(f"subtitle_transcript_cache_hit vod={vod_path} transcript={transcript_path}")
                    else:
                        transcript_path = ensure_transcript(vod_path, cfg, root / "output" / "transcripts")
                    _log(f"transcript_ok vod={vod_path} transcript={transcript_path}")
                    subtitle_dir = root / "output" / "subtitles" / batch_id
                    subtitle_dir.mkdir(parents=True, exist_ok=True)
                    subtitles_generated_local = 0
                    srt_name_usage: dict[str, int] = {}
                    subtitle_index_rows: list[dict[str, str]] = []
                    total_clips = max(1, len(clip_objs))
                    for idx_clip, c in enumerate(clip_objs, start=1):
                        base_label = str(c.get("display_name") or c.get("clip_id") or "clip").strip()
                        base_name = _safe_name_token(base_label, limit=120)
                        if not base_name:
                            base_name = "clip"
                        idx = srt_name_usage.get(base_name, 0) + 1
                        srt_name_usage[base_name] = idx
                        subtitle_name = base_name if idx == 1 else f"{base_name}_{idx}"
                        srt_path = subtitle_dir / f"{subtitle_name}.srt"
                        ok = generate_srt_for_clip(
                            transcript_path,
                            float(c.get("start_seconds", 0.0)),
                            float(c.get("end_seconds", 0.0)),
                            srt_path,
                            captions_cfg,
                        )
                        if ok:
                            resolved_srt = str(srt_path.resolve())
                            c["subtitle_path"] = resolved_srt
                            subtitles_generated_local += 1
                            subtitle_index_rows.append(
                                {
                                    "clip_id": str(c.get("clip_id", "")),
                                    "display_name": str(c.get("display_name", "")),
                                    "srt_file": srt_path.name,
                                    "srt_path": resolved_srt,
                                }
                            )
                        if callable(progress_cb):
                            pct = 20 + int(round((idx_clip / total_clips) * 70))
                            progress_cb("Batch+Subtitles", min(90, pct), 100, f"Generation sous-titres {idx_clip}/{total_clips}")
                    index_path = subtitle_dir / "index.csv"
                    with index_path.open("w", encoding="utf-8", newline="") as f_idx:
                        writer = csv.DictWriter(f_idx, fieldnames=["clip_id", "display_name", "srt_file", "srt_path"])
                        writer.writeheader()
                        writer.writerows(subtitle_index_rows)
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
        "meta": {
            "source_vod_path": str(vod_path.resolve()),
            "preset_id": preset_id,
            "generated_with_subtitles": bool(captions_enabled),
            "use_transcript_for_selection": bool(use_transcript_for_selection),
            "transcript_path": str(transcript_path_cached),
            "transcript_exists_pre_generation": bool(transcript_exists),
        },
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
    if callable(progress_cb):
        progress_cb("Batch+Subtitles", 100, 100, "Manifest ecrit")
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
    q = query.strip().lower()
    min_score = 0.25
    min_distance_seconds = 12.0
    overlap_threshold = 0.8
    lead_in_seconds = 5.0

    plans_by_source: dict[str, list[ClipPlan]] = {}
    for plan in plans:
        plans_by_source.setdefault(plan.source_path, []).append(plan)

    filtered: list[ClipPlan] = []
    for source_path, source_plans in plans_by_source.items():
        entries = _load_transcript_entries(root, source_path)
        if not entries:
            continue

        candidate_windows: list[tuple[float, float, float]] = []
        for e in entries:
            text = str(e.get("text", ""))
            score = _semantic_match_score(q, text)
            if q in text.lower():
                score = max(score, 0.9)
            if score < min_score:
                continue
            raw_start = float(e.get("start", 0.0))
            start = max(0.0, raw_start - lead_in_seconds)
            end = start + float(max_seconds)
            candidate_windows.append((score, start, end))

        if not candidate_windows:
            continue

        candidate_windows.sort(key=lambda x: x[0], reverse=True)

        deduped_windows: list[tuple[float, float, float]] = []
        for score, start, end in candidate_windows:
            too_close = False
            for _, kept_start, kept_end in deduped_windows:
                if abs(start - kept_start) < min_distance_seconds:
                    too_close = True
                    break
                overlap = _overlap_ratio_from_ranges(start, end, kept_start, kept_end)
                if overlap > overlap_threshold:
                    too_close = True
                    break
            if not too_close:
                deduped_windows.append((score, start, end))

        if not deduped_windows:
            continue

        used = min(len(source_plans), len(deduped_windows))
        for idx in range(used):
            plan = source_plans[idx]
            _, start, end = deduped_windows[idx]
            plan.start_seconds = start
            plan.end_seconds = end
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
                    timeline_name=str(c.get("timeline_name", "") or ""),
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


def _list_subtitle_template_candidates(media_pool: Any) -> list[str]:
    root = _safe_call(media_pool, "GetRootFolder")
    if root is None:
        return []
    names: set[str] = set()
    for clip in _walk_folder_clips(root):
        name = str(_safe_call(clip, "GetName", default="") or "").strip()
        if not name:
            continue
        props = _safe_call(clip, "GetClipProperty", default={}) or {}
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
    for forced in (STANDALONE_CAPTION_TEMPLATE_NAME, STANDALONE_CAPTION_TEMPLATE_FALLBACK_NAME):
        if forced not in out:
            out.insert(0, forced)
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


def _ensure_media_item_with_status(media_pool: Any, source_path: Path) -> tuple[Any | None, str]:
    existing = _find_media_pool_item_by_path(media_pool, source_path)
    if existing is not None:
        return existing, "already_exists"
    imported = _safe_call(media_pool, "ImportMedia", [str(source_path)], default=[])
    if imported and len(imported) > 0:
        return imported[0], "imported"
    return None, "failed"


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


def _force_item_normal_speed(item: Any) -> None:
    # Defensive normalization against API/build differences that can retain retime state.
    for key, value in (
        ("Speed", 100.0),
        ("Clip Speed", 100.0),
        ("RetimeProcess", 0),
        ("Retime Process", 0),
    ):
        _safe_call(item, "SetProperty", key, value)
    _safe_call(item, "SetClipProperty", "Speed", "100")
    _safe_call(item, "SetClipProperty", "Clip Speed", "100")


def _get_timeline_items_on_track(timeline: Any, track_index: int) -> list[Any]:
    out = _safe_call(timeline, "GetItemListInTrack", "video", track_index, default=[])
    return out or []


def _get_track_item_count(timeline: Any, track_type: str) -> int:
    count = _safe_call(timeline, "GetTrackCount", track_type, default=0)
    try:
        count_i = int(count)
    except Exception:
        count_i = 0
    total = 0
    for idx in range(1, count_i + 1):
        items = _safe_call(timeline, "GetItemListInTrack", track_type, idx, default=[])
        total += len(items or [])
    return total


def _read_speed_props(item: Any) -> str:
    vals: list[str] = []
    for key in ("Speed", "Clip Speed", "Retime Process", "RetimeProcess"):
        v = _safe_call(item, "GetProperty", key, default=None)
        if v is None:
            props = _safe_call(item, "GetProperty", default={}) or {}
            v = props.get(key)
        if v is not None:
            vals.append(f"{key}={v}")
    return ";".join(vals) if vals else "no_speed_props"


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
        return False, "Aucun projet ouvert"
    timeline = _safe_call(project, "GetCurrentTimeline")
    if not timeline:
        return False, "Aucune timeline active"

    mode = str(preset.get("mode", "single"))
    use_range = scope_mode == "selected_range"
    use_whole_timeline = scope_mode == "whole_timeline"
    range_frames = _get_timeline_selected_range(timeline) if use_range else None
    if use_range and range_frames is None:
        return False, "Aucune plage In/Out sélectionnée sur la timeline"

    if mode == "fixed_split":
        if use_whole_timeline:
            cam_items = _get_timeline_items_on_track(timeline, 1)
            game_items = _get_timeline_items_on_track(timeline, 2)
            if not cam_items or not game_items:
                return False, "Toute la timeline: il faut des clips sur piste 1 (caméra) et piste 2 (gameplay)"
            _log(f"Apply whole timeline mapping: camera->T1 items={len(cam_items)}, gameplay->T2 items={len(game_items)}")
            for it in cam_items:
                _apply_item_transform(it, dict(preset.get("camera", {})))
            for it in game_items:
                _apply_item_transform(it, dict(preset.get("gameplay", {})))
            return True, f"Preset appliqué à toute la timeline (caméra T1: {len(cam_items)}, gameplay T2: {len(game_items)})"

        if use_range and range_frames is not None:
            start_f, end_f = range_frames
            cam_items = _items_overlapping_frame_range(timeline, 1, start_f, end_f)
            game_items = _items_overlapping_frame_range(timeline, 2, start_f, end_f)
            if not cam_items or not game_items:
                return False, "Il faut des clips sur piste 1 et piste 2 dans la plage sélectionnée"
            _log(f"Apply selected range mapping: camera->T1 items={len(cam_items)}, gameplay->T2 items={len(game_items)}")
            for it in cam_items:
                _apply_item_transform(it, dict(preset.get("camera", {})))
            for it in game_items:
                _apply_item_transform(it, dict(preset.get("gameplay", {})))
            return True, f"Preset appliqué à la plage (caméra T1: {len(cam_items)}, gameplay T2: {len(game_items)})"

        cam_item = _get_item_at_current_frame(timeline, 1)
        game_item = _get_item_at_current_frame(timeline, 2)
        if not cam_item or not game_item:
            return False, "Il faut piste 1 (caméra) et piste 2 (gameplay) au curseur de lecture"
        _log("Apply selected clip mapping: camera->T1 gameplay->T2")
        _apply_item_transform(cam_item, dict(preset.get("camera", {})))
        _apply_item_transform(game_item, dict(preset.get("gameplay", {})))
        return True, "Preset appliqué au clip sélectionné (piste 1=caméra, piste 2=gameplay)"

    if use_whole_timeline:
        try:
            track_count = int(_safe_call(timeline, "GetTrackCount", "video", default=0) or 0)
        except Exception:
            track_count = 0
        items: list[Any] = []
        for track_idx in range(1, track_count + 1):
            items.extend(_get_timeline_items_on_track(timeline, track_idx))
        if not items:
            return False, "Aucun clip vidéo trouvé sur la timeline"
        for it in items:
            _apply_item_transform(it, dict(preset.get("single", {})))
        return True, f"Preset appliqué à {len(items)} clip(s) sur toute la timeline"

    if use_range and range_frames is not None:
        start_f, end_f = range_frames
        items = _items_overlapping_frame_range(timeline, 1, start_f, end_f)
        if not items:
            return False, "Aucun clip trouvé sur la piste 1 dans la plage sélectionnée"
        for it in items:
            _apply_item_transform(it, dict(preset.get("single", {})))
        return True, f"Preset appliqué à {len(items)} clip(s) dans la plage sélectionnée"

    selected = _safe_call(timeline, "GetCurrentVideoItem")
    if not selected:
        return False, "Aucun clip sélectionné/courant"
    _apply_item_transform(selected, dict(preset.get("single", {})))
    return True, "Preset appliqué au clip sélectionné"


def _selected_clip_subtitle_context(resolve: Any) -> tuple[bool, str, dict[str, Any]]:
    pm = _safe_call(resolve, "GetProjectManager")
    project = _safe_call(pm, "GetCurrentProject") if pm else None
    if not project:
        return False, "No open project", {}
    timeline = _safe_call(project, "GetCurrentTimeline")
    if not timeline:
        return False, "No active timeline", {}

    project_fps = _fps_from_project(project)
    media_pool = _safe_call(project, "GetMediaPool")

    def _source_path_from_media_item(media_item: Any) -> str:
        if not media_item:
            return ""
        props = _safe_call(media_item, "GetClipProperty", default={}) or {}
        return str(props.get("File Path") or "").strip()

    def _item_from_playhead_or_current() -> Any | None:
        current = _safe_call(timeline, "GetCurrentVideoItem")
        if current:
            return current
        video_track_count = int(_safe_call(timeline, "GetTrackCount", "video", default=0) or 0)
        if video_track_count <= 0:
            video_track_count = 1
        for track_idx in range(video_track_count, 0, -1):
            it = _get_item_at_current_frame(timeline, track_idx)
            if it:
                return it
        return None

    item = _item_from_playhead_or_current()
    source_path = ""
    fallback_range: tuple[int, int] | None = None

    if item is not None:
        media_item = _safe_call(item, "GetMediaPoolItem")
        source_path = _source_path_from_media_item(media_item)
        if not source_path:
            return False, "Selected timeline clip has no readable source path", {}
    else:
        selected_media = _safe_call(media_pool, "GetSelectedClips", default=[]) if media_pool else []
        selected_first = selected_media[0] if selected_media else None
        if not selected_first:
            return False, "No clip at playhead and no selected clip in Media Pool", {}
        source_path = _source_path_from_media_item(selected_first)
        if not source_path:
            return False, "Selected Media Pool clip has no readable source path", {}
        fallback_range = _get_timeline_selected_range(timeline)
        if fallback_range is None:
            return False, "No clip at playhead. Select timeline In/Out range to use selected Media Pool clip", {}

    def _to_int(v: Any) -> int | None:
        try:
            return int(float(v))
        except Exception:
            return None

    src_in = None
    src_out = None

    if fallback_range is not None:
        src_in, src_out = fallback_range
    else:
        for meth in ("GetSourceStartFrame", "GetLeftOffset"):
            val = _to_int(_safe_call(item, meth, default=None))
            if val is not None:
                src_in = val
                break
        for meth in ("GetSourceEndFrame", "GetRightOffset"):
            val = _to_int(_safe_call(item, meth, default=None))
            if val is not None:
                src_out = val
                break

        if src_in is None or src_out is None:
            all_props = _safe_call(item, "GetProperty", default={}) or {}
            if src_in is None:
                src_in = _to_int(all_props.get("Source Start"))
            if src_out is None:
                src_out = _to_int(all_props.get("Source End"))

        if src_in is None or src_out is None or src_out <= src_in:
            tl_start = _to_int(_safe_call(item, "GetStart", default=None))
            tl_end = _to_int(_safe_call(item, "GetEnd", default=None))
            if tl_start is None or tl_end is None or tl_end <= tl_start:
                return False, "Could not read clip range from timeline item", {}
            src_in = 0
            src_out = max(1, tl_end - tl_start)

    clip_start = max(0.0, float(src_in) / max(1, project_fps))
    clip_end = max(clip_start + 0.1, float(src_out) / max(1, project_fps))
    return True, "ok", {
        "project": project,
        "timeline": timeline,
        "media_pool": media_pool,
        "source_path": source_path,
        "clip_start": clip_start,
        "clip_end": clip_end,
        "timeline_name": str(_safe_call(timeline, "GetName", default="timeline")),
        "item_name": str(_safe_call(item, "GetName", default="clip")),
    }


def _load_audio_energy_for_silence_cut(
    root: Path,
    source_path: Path,
    cfg: dict[str, Any],
    cache: dict[str, tuple[list[tuple[float, float]], str]],
) -> tuple[list[tuple[float, float]], str, list[str]]:
    source_key = str(source_path.resolve()).lower()
    if source_key in cache:
        energies, source_label = cache[source_key]
        return energies, source_label, []

    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)
    from short_editor.clip_builder import _compute_window_energy, _extract_mono_wav, _extract_track_wav

    audio_cfg = cfg.get("audio", {}) if isinstance(cfg.get("audio", {}), dict) else {}
    analysis_cfg = audio_cfg.get("analysis", {}) if isinstance(audio_cfg.get("analysis", {}), dict) else {}
    render_cfg = audio_cfg.get("render", {}) if isinstance(audio_cfg.get("render", {}), dict) else {}
    voice_track = int(analysis_cfg.get("voice_track", 2))
    render_track = int(render_cfg.get("base_track", 6))
    window_seconds = float(audio_cfg.get("silence_cut", {}).get("window_seconds", 0.12)) if isinstance(audio_cfg.get("silence_cut", {}), dict) else 0.12
    window_seconds = max(0.06, min(0.5, window_seconds))

    warnings_out: list[str] = []
    work_parent = root / "work"
    work_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=str(work_parent)) as tmp_dir:
        tmp = Path(tmp_dir)
        wav_path = tmp / "silence_cut.wav"
        source_label = f"piste voix {voice_track}"
        if not _extract_track_wav(str(source_path), wav_path, voice_track):
            source_label = f"piste rendu {render_track}"
            if not _extract_track_wav(str(source_path), wav_path, render_track):
                source_label = "mix mono"
                try:
                    _extract_mono_wav(str(source_path), wav_path)
                except Exception as exc:
                    warnings_out.append(f"Analyse audio impossible pour {source_path.name}: {exc}")
                    cache[source_key] = ([], source_label)
                    return [], source_label, warnings_out
                warnings_out.append(f"{source_path.name}: fallback analyse silence sur mix mono.")
            else:
                warnings_out.append(f"{source_path.name}: fallback analyse silence sur piste rendu {render_track}.")
        energies = _compute_window_energy(wav_path, window_seconds=window_seconds)

    cache[source_key] = (energies, source_label)
    return energies, source_label, warnings_out


def _detect_audible_segments_for_silence_cut(
    energies: list[tuple[float, float]],
    clip_start: float,
    clip_end: float,
    cfg: dict[str, Any],
) -> tuple[list[tuple[float, float]], dict[str, float]]:
    if clip_end <= clip_start:
        return [], {"cuts": 0.0, "removed_seconds": 0.0, "threshold": 0.0}
    root_str = str(_repo_root())
    if root_str not in sys.path:
        sys.path.insert(0, root_str)
    from short_editor.clip_builder import _percentile

    audio_cfg = cfg.get("audio", {}) if isinstance(cfg.get("audio", {}), dict) else {}
    cut_cfg = audio_cfg.get("silence_cut", {}) if isinstance(audio_cfg.get("silence_cut", {}), dict) else {}
    min_silence = max(0.25, float(cut_cfg.get("min_silence_seconds", 0.55)))
    padding = max(0.05, float(cut_cfg.get("padding_seconds", 0.18)))
    merge_gap = max(0.08, float(cut_cfg.get("merge_gap_seconds", 0.28)))
    min_segment = max(0.2, float(cut_cfg.get("min_segment_seconds", 0.45)))

    clip_energies = [(t, e) for t, e in energies if clip_start <= t <= clip_end]
    if len(clip_energies) < 3:
        return [(clip_start, clip_end)], {"cuts": 0.0, "removed_seconds": 0.0, "threshold": 0.0}

    values = [float(e) for _, e in clip_energies]
    low = _percentile(values, 0.35)
    high = _percentile(values, 0.78)
    threshold = low + max(0.0, high - low) * 0.28
    if threshold <= 0:
        threshold = max(values) * 0.12
    if threshold <= 0:
        return [(clip_start, clip_end)], {"cuts": 0.0, "removed_seconds": 0.0, "threshold": 0.0}

    active_ranges: list[tuple[float, float]] = []
    current_start: float | None = None
    last_t: float | None = None
    estimated_step = max(0.08, min_silence / 4)
    if len(clip_energies) >= 2:
        deltas = [clip_energies[i + 1][0] - clip_energies[i][0] for i in range(len(clip_energies) - 1) if clip_energies[i + 1][0] > clip_energies[i][0]]
        if deltas:
            estimated_step = max(0.06, min(0.5, sorted(deltas)[len(deltas) // 2]))

    for t, energy in clip_energies:
        is_active = float(energy) >= threshold
        if is_active and current_start is None:
            current_start = max(clip_start, t)
        if is_active:
            last_t = t
        elif current_start is not None and last_t is not None:
            active_ranges.append((current_start, min(clip_end, last_t + estimated_step)))
            current_start = None
            last_t = None
    if current_start is not None and last_t is not None:
        active_ranges.append((current_start, min(clip_end, last_t + estimated_step)))

    if not active_ranges:
        return [(clip_start, clip_end)], {"cuts": 0.0, "removed_seconds": 0.0, "threshold": threshold}

    padded = [(max(clip_start, s - padding), min(clip_end, e + padding)) for s, e in active_ranges]
    merged: list[tuple[float, float]] = []
    for s, e in padded:
        if e - s < min_segment:
            mid = (s + e) / 2.0
            s = max(clip_start, mid - min_segment / 2.0)
            e = min(clip_end, mid + min_segment / 2.0)
        if not merged:
            merged.append((s, e))
            continue
        prev_s, prev_e = merged[-1]
        gap = s - prev_e
        if gap <= merge_gap or gap < min_silence:
            merged[-1] = (prev_s, max(prev_e, e))
        else:
            merged.append((s, e))

    final_segments: list[tuple[float, float]] = []
    for s, e in merged:
        if e - s >= min_segment:
            final_segments.append((round(s, 3), round(e, 3)))
    if not final_segments:
        final_segments = [(clip_start, clip_end)]

    original_duration = max(0.0, clip_end - clip_start)
    kept_duration = sum(max(0.0, e - s) for s, e in final_segments)
    removed = max(0.0, original_duration - kept_duration)
    cuts = max(0, len(final_segments) - 1)
    if removed < min_silence:
        return [(clip_start, clip_end)], {"cuts": 0.0, "removed_seconds": 0.0, "threshold": threshold}
    return final_segments, {"cuts": float(cuts), "removed_seconds": removed, "threshold": threshold}


def _append_silence_cut_segment_with_preset(
    media_pool: Any,
    timeline: Any,
    media_item: Any,
    start_frame: int,
    end_frame: int,
    record_frame: int,
    preset: dict[str, Any],
) -> None:
    mode = str(preset.get("mode", "single"))
    if mode == "fixed_split":
        _append_clip_range(media_pool, timeline, media_item, start_frame, end_frame, track_index=1, record_frame=record_frame)
        track_count = _safe_call(timeline, "GetTrackCount", "video", default=1) or 1
        try:
            track_count_i = int(track_count)
        except Exception:
            track_count_i = 1
        if track_count_i < 2:
            _safe_call(timeline, "AddTrack", "video")
        _append_clip_range(media_pool, timeline, media_item, start_frame, end_frame, track_index=2, record_frame=record_frame)
        track1_items = _items_overlapping_frame_range(timeline, 1, record_frame, record_frame + max(1, end_frame - start_frame) + 2)
        track2_items = _items_overlapping_frame_range(timeline, 2, record_frame, record_frame + max(1, end_frame - start_frame) + 2)
        for it in track1_items:
            _force_item_normal_speed(it)
            _apply_item_transform(it, dict(preset.get("camera", {})))
        for it in track2_items:
            _force_item_normal_speed(it)
            _apply_item_transform(it, dict(preset.get("gameplay", {})))
        return

    _append_clip_range(media_pool, timeline, media_item, start_frame, end_frame, track_index=1, record_frame=record_frame)
    items = _items_overlapping_frame_range(timeline, 1, record_frame, record_frame + max(1, end_frame - start_frame) + 2)
    for it in items:
        _force_item_normal_speed(it)
        _apply_item_transform(it, dict(preset.get("single", {})))


def _create_silence_cut_timeline(
    root: Path,
    project: Any,
    media_pool: Any,
    source_path: Path,
    timeline_name: str,
    segments_seconds: list[tuple[float, float]],
    preset: dict[str, Any],
) -> tuple[Any | None, list[str]]:
    warnings_out: list[str] = []
    media_item = _ensure_media_item(media_pool, source_path)
    if media_item is None:
        return None, [f"Impossible d'importer le média: {source_path}"]
    project_fps = _fps_from_project(project)
    source_fps = _source_fps_for_media_item(media_item, source_path, project_fps)
    _delete_timeline_if_exists(project, media_pool, timeline_name)
    timeline = _safe_call(media_pool, "CreateEmptyTimeline", timeline_name)
    if not timeline:
        return None, [f"Impossible de créer la timeline: {timeline_name}"]
    _force_timeline_fps_60(project, timeline)

    record_frame = 0
    for s, e in segments_seconds:
        start_frame = int(round(s * source_fps))
        end_frame = int(round(e * source_fps))
        if end_frame <= start_frame:
            warnings_out.append(f"Segment ignoré: {s:.2f}-{e:.2f}s")
            continue
        _append_silence_cut_segment_with_preset(media_pool, timeline, media_item, start_frame, end_frame, record_frame, preset)
        record_frame += max(1, int(round((e - s) * project_fps)))
    if record_frame <= 0:
        warnings_out.append(f"Aucun segment valide pour {timeline_name}")
    return timeline, warnings_out


def _suffix_timeline_name(base_name: str, suffix: str = "__silence_cut") -> str:
    clean = _safe_name_token(base_name, limit=100)
    if clean.endswith(suffix):
        return clean
    return _safe_name_token(f"{clean}{suffix}", limit=120)


def _create_timeline_for_clip_with_preset(
    project: Any,
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
    _force_timeline_fps_60(project, timeline)

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
            _force_item_normal_speed(items_t1[0])
            _apply_item_transform(items_t1[0], dict(preset.get("camera", {})))
        if items_t2:
            _force_item_normal_speed(items_t2[0])
            _apply_item_transform(items_t2[0], dict(preset.get("gameplay", {})))
        return timeline

    ok = _append_clip_range(media_pool, timeline, media_item, start_frame, end_frame, track_index=1)
    if not ok:
        return None
    items_t1 = _get_timeline_items_on_track(timeline, 1)
    if items_t1:
        _force_item_normal_speed(items_t1[0])
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


def _ensure_shorteditor_subfolder(media_pool: Any, subfolder_name: str) -> Any:
    root = _safe_call(media_pool, "GetRootFolder", required=True)
    for f in _safe_call(root, "GetSubFolderList", default=[]) or []:
        if _safe_call(f, "GetName", default="") == "ShortEditor":
            short_editor = f
            break
    else:
        short_editor = _safe_call(media_pool, "AddSubFolder", root, "ShortEditor", required=True)

    for f in _safe_call(short_editor, "GetSubFolderList", default=[]) or []:
        if _safe_call(f, "GetName", default="") == subfolder_name:
            folder = f
            break
    else:
        folder = _safe_call(media_pool, "AddSubFolder", short_editor, subfolder_name, required=True)

    _safe_call(media_pool, "SetCurrentFolder", folder)
    return folder


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
    # Extra compatibility keys/values for builds that ignore one spelling.
    for key in ("timelineFrameRate", "timelinePlaybackFrameRate", "playbackFrameRate"):
        for value in ("60", "60.0", "60.000"):
            _safe_call(project, "SetSetting", key, value)
    _safe_call(project, "SetSetting", "timelineOutputResolutionWidth", "1080")
    _safe_call(project, "SetSetting", "timelineOutputResolutionHeight", "1920")
    # Prefer crop behavior when source is 16:9.
    _safe_call(project, "SetSetting", "inputScalingPreset", "Scale full frame with crop")


def _ensure_playback_fps_60(project: Any) -> bool:
    """Best-effort normalization to avoid 60->24 preview slowdown."""
    for key in ("timelinePlaybackFrameRate", "playbackFrameRate"):
        for value in ("60", "60.0", "60.000"):
            _safe_call(project, "SetSetting", key, value)
    timeline_fps = _safe_int_from_project_setting(project, "timelineFrameRate", DEFAULT_FPS)
    playback_fps = _safe_int_from_project_setting(project, "timelinePlaybackFrameRate", DEFAULT_FPS)
    _log(f"playback_fps_verify timeline={timeline_fps} playback={playback_fps}")
    return timeline_fps == 60 and playback_fps == 60


def _force_timeline_fps_60(project: Any, timeline: Any) -> None:
    _safe_call(project, "SetCurrentTimeline", timeline)
    for key in ("timelineFrameRate", "timelinePlaybackFrameRate", "playbackFrameRate"):
        for value in ("60", "60.0", "60.000"):
            _safe_call(timeline, "SetSetting", key, value)
    t_tl = _safe_call(timeline, "GetSetting", "timelineFrameRate", default=None)
    t_pb = _safe_call(timeline, "GetSetting", "timelinePlaybackFrameRate", default=None)
    _log(f"timeline_fps_verify name={_safe_call(timeline, 'GetName', default='timeline')} timeline={t_tl} playback={t_pb}")


def _apply_preview_safe_playback(project: Any) -> list[str]:
    warnings_out: list[str] = []
    attempts = [
        ("renderCacheMode", "user"),
        ("renderCacheMode", "User"),
        ("proxyMediaMode", "half"),
        ("proxyMediaMode", "Half"),
        ("timelineProxyResolution", "half"),
        ("timelineProxyResolution", "Half"),
    ]
    applied = 0
    for key, value in attempts:
        out = _safe_call(project, "SetSetting", key, value, default=False)
        if out:
            applied += 1
            _log(f"preview_safe_setting_applied {key}={value}")
    if applied == 0:
        warnings_out.append("Preview Safe Mode: Resolve API n'a pas expose les settings cache/proxy sur cette build.")
    else:
        _log(f"preview_safe_settings_applied_count={applied}")
    return warnings_out


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


def _collect_unique_media_items_from_timelines(timelines: list[Any]) -> list[Any]:
    seen: set[str] = set()
    out: list[Any] = []
    for tl in timelines:
        track_count = _safe_call(tl, "GetTrackCount", "video", default=0)
        try:
            track_count_i = int(track_count)
        except Exception:
            track_count_i = 0
        for track_idx in range(1, max(1, track_count_i) + 1):
            items = _safe_call(tl, "GetItemListInTrack", "video", track_idx, default=[]) or []
            for it in items:
                media_item = _safe_call(it, "GetMediaPoolItem")
                if media_item is None:
                    continue
                uid = str(id(media_item))
                if uid in seen:
                    continue
                seen.add(uid)
                out.append(media_item)
    return out


def _generate_optimized_media_for_batch(
    root: Path,
    project: Any,
    media_pool: Any,
    batch_id: str,
    timelines: list[Any],
    progress_cb: Any | None = None,
) -> tuple[list[str], Path]:
    warnings: list[str] = []
    out_dir = root / "output" / "resolve_optimized" / batch_id
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / "optimized_index.csv"

    # Try setting a dedicated optimized media location for this quality run.
    configured_path = False
    for key in ("optimizedMediaPath", "OptimizedMediaPath"):
        if _safe_call(project, "SetSetting", key, str(out_dir), default=False):
            configured_path = True
            _log(f"optimized_media_path_set key={key} path={out_dir}")
            break

    media_items = _collect_unique_media_items_from_timelines(timelines)
    total = len(media_items)
    if total == 0:
        with report_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["batch_id", "timeline", "clip_name", "source_path", "status", "notes"])
        warnings.append("Optimized media skipped: no media items found in current batch timelines.")
        return warnings, report_path

    rows: list[list[str]] = []
    success_count = 0

    def _try_generate(item: Any) -> bool:
        variants = [
            (media_pool, "GenerateOptimizedMedia", [item]),
            (media_pool, "GenerateOptimizedMedia", item),
            (project, "GenerateOptimizedMedia", [item]),
            (project, "GenerateOptimizedMedia", item),
        ]
        for obj, method, payload in variants:
            out = _safe_call(obj, method, payload, default=None)
            if bool(out):
                return True
        return False

    for idx, item in enumerate(media_items, start=1):
        if callable(progress_cb):
            progress_cb("Optimized Media", idx - 1, max(1, total), f"Optimizing media {idx}/{total}")

        clip_name = str(_safe_call(item, "GetName", default="clip"))
        props = _safe_call(item, "GetClipProperty", default={}) or {}
        source_path = str(props.get("File Path") or "")
        ok = _try_generate(item)
        status = "requested" if ok else "failed"
        if ok:
            success_count += 1
        rows.append([
            batch_id,
            "",
            clip_name,
            source_path,
            status,
            "optimized path configured" if configured_path else "resolve managed cache path",
        ])

    with report_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["batch_id", "timeline", "clip_name", "source_path", "status", "notes"])
        writer.writerows(rows)

    if callable(progress_cb):
        progress_cb("Optimized Media", total, max(1, total), f"Optimized media requested {success_count}/{total}")

    if not configured_path:
        warnings.append("Optimized media generated via Resolve cache path (API could not set dedicated optimized media folder).")
    if success_count < total:
        warnings.append(f"Optimized media requested for {success_count}/{total} item(s).")
    _log(f"optimized_media_summary batch={batch_id} requested={success_count}/{total} report={report_path}")
    return warnings, report_path


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


def _import_subtitles_to_timeline(
    project: Any,
    media_pool: Any,
    timeline: Any,
    subtitle_path: Path,
    template_name: str = SUBTITLE_TEMPLATE_AUTO_LABEL,
    offset_ms: int = -500,
) -> tuple[bool, str]:
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

    def _find_template_item_by_name(root_folder: Any, wanted_name: str) -> Any | None:
        target = wanted_name.strip().lower()

        def _walk(folder: Any) -> list[Any]:
            out: list[Any] = []
            out.extend(_safe_call(folder, "GetClipList", default=[]) or [])
            for sub in _safe_call(folder, "GetSubFolderList", default=[]) or []:
                out.extend(_walk(sub))
            return out

        for clip in _walk(root_folder):
            name = str(_safe_call(clip, "GetName", default="") or "").strip()
            if name.lower() == target:
                return clip
        return None

    def _ensure_standalone_caption_template() -> tuple[Any | None, str]:
        root_folder = _safe_call(media_pool, "GetRootFolder")
        if root_folder is None:
            return None, "Media Pool root folder not available"

        wanted = str(template_name or "").strip()
        is_auto = wanted == "" or wanted == SUBTITLE_TEMPLATE_AUTO_LABEL
        existing = None
        if not is_auto:
            existing = _find_template_item_by_name(root_folder, wanted)
        if existing is None:
            existing = _find_template_item_by_name(root_folder, STANDALONE_CAPTION_TEMPLATE_NAME)
        if existing is None:
            existing = _find_template_item_by_name(root_folder, STANDALONE_CAPTION_TEMPLATE_FALLBACK_NAME)
        if existing is not None:
            _log("standalone_template_found")
            return existing, "template_found"

        drb_path = (_repo_root() / "resolve_integration" / "assets" / "shorteditor-caption-bin.drb").resolve()
        if not drb_path.exists():
            return None, f"Standalone caption template asset missing: {drb_path}"

        imported = _safe_call(media_pool, "ImportFolderFromFile", str(drb_path), default=False)
        if not imported:
            return None, f"Failed to import standalone caption template folder: {drb_path.name}"
        _log(f"standalone_template_imported_from={drb_path}")

        root_folder = _safe_call(media_pool, "GetRootFolder")
        if root_folder is None:
            return None, "Media Pool root folder unavailable after template import"
        loaded = None
        if not is_auto:
            loaded = _find_template_item_by_name(root_folder, wanted)
        if loaded is None:
            loaded = _find_template_item_by_name(root_folder, STANDALONE_CAPTION_TEMPLATE_NAME)
        if loaded is None:
            loaded = _find_template_item_by_name(root_folder, STANDALONE_CAPTION_TEMPLATE_FALLBACK_NAME)
        if loaded is None:
            return None, (
                f"Template '{wanted or STANDALONE_CAPTION_TEMPLATE_NAME}'/'{STANDALONE_CAPTION_TEMPLATE_FALLBACK_NAME}' "
                f"not found after importing {drb_path.name}"
            )
        return loaded, "template_imported"

    def _parse_srt_segments(path: Path) -> list[dict[str, Any]]:
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            return []
        blocks = re.split(r"\r?\n\r?\n+", text.strip())
        segs: list[dict[str, Any]] = []
        ts_re = re.compile(
            r"(?P<s>\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(?P<e>\d{2}:\d{2}:\d{2},\d{3})"
        )

        def _ts_to_sec(ts: str) -> float:
            hh, mm, rest = ts.split(":")
            ss, ms = rest.split(",")
            return int(hh) * 3600 + int(mm) * 60 + int(ss) + int(ms) / 1000.0

        for block in blocks:
            lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
            if len(lines) < 2:
                continue
            m = ts_re.search(lines[1] if lines[0].isdigit() else lines[0])
            if not m:
                continue
            text_lines = lines[2:] if lines[0].isdigit() else lines[1:]
            caption = "\n".join(text_lines).strip()
            if not caption:
                continue
            start = _ts_to_sec(m.group("s"))
            end = _ts_to_sec(m.group("e"))
            if end <= start:
                continue
            segs.append({"start": start, "end": end, "text": caption})
        return segs

    def _set_textplus_item_text(timeline_item: Any, text_value: str) -> bool:
        comp_count = _safe_call(timeline_item, "GetFusionCompCount", default=0) or 0
        try:
            count_i = int(comp_count)
        except Exception:
            count_i = 0
        if count_i <= 0:
            return False
        comp = _safe_call(timeline_item, "GetFusionCompByIndex", 1, default=None)
        if comp is None:
            return False
        tools = _safe_call(comp, "GetToolList", False, "TextPlus", default=None)
        if not isinstance(tools, dict) or not tools:
            tools = _safe_call(comp, "GetToolList", default={}) or {}
        for _, tool in tools.items():
            ok = bool(_safe_call(tool, "SetInput", "StyledText", text_value, default=False))
            ok = ok or bool(_safe_call(tool, "SetInput", "Text", text_value, default=False))
            if ok:
                return True
        return False

    segments = _parse_srt_segments(subtitle_path)
    if not segments:
        return False, "SRT has no valid subtitle segments"

    template_item, template_status = _ensure_standalone_caption_template()
    if template_item is None:
        return False, template_status

    frame_rate_raw = _safe_call(timeline, "GetSetting", "timelineFrameRate", default="60")
    fps = _parse_fps_text(frame_rate_raw) or 60.0
    timeline_start = _safe_call(timeline, "GetStartFrame", default=0) or 0
    try:
        tl_start_i = int(timeline_start)
    except Exception:
        tl_start_i = 0
    track_count = _safe_call(timeline, "GetTrackCount", "video", default=1)
    try:
        track_idx = max(1, int(track_count) + 1)
    except Exception:
        track_idx = 2
    _safe_call(timeline, "AddTrack", "video")

    clip_list: list[dict[str, Any]] = []
    time_offset = float(offset_ms) / 1000.0
    _log(f"subtitle_textplus_offset_applied_ms={offset_ms}")
    for seg in segments:
        shifted_start = max(0.0, float(seg["start"]) + time_offset)
        shifted_end = max(shifted_start + 0.05, float(seg["end"]) + time_offset)
        seg_start = int(round(shifted_start * fps))
        seg_end = int(round(shifted_end * fps))
        if seg_end <= seg_start:
            seg_end = seg_start + 1
        clip_list.append(
            {
                "mediaPoolItem": template_item,
                "startFrame": 0,
                "endFrame": max(1, seg_end - seg_start),
                "trackIndex": track_idx,
                "recordFrame": tl_start_i + seg_start,
            }
        )

    appended = _safe_call(media_pool, "AppendToTimeline", clip_list, default=None)
    if not isinstance(appended, list) or not appended:
        return False, "Failed to append standalone Text+ subtitle clips to timeline"

    applied = 0
    for i, it in enumerate(appended):
        txt = str(segments[i].get("text", "")) if i < len(segments) else ""
        if txt and _set_textplus_item_text(it, txt):
            applied += 1

    after_count = _count_subtitle_items()
    after_video = _count_video_items()
    _log(
        f"subtitle_textplus_apply template={STANDALONE_CAPTION_TEMPLATE_NAME} status={template_status} "
        f"applied={applied}/{len(segments)} subtitle_tracks_before={before_count} subtitle_tracks_after={after_count} "
        f"video_items_before={before_video_count} video_items_after={after_video}"
    )

    if applied <= 0:
        return False, "Text+ clips appended but text injection failed"
    return True, f"Subtitles applied via standalone Text+ ({applied}/{len(segments)})"


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
    subtitle_template_name: str = SUBTITLE_TEMPLATE_AUTO_LABEL,
    subtitle_offset_ms: int = -500,
    progress_cb: Any | None = None,
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
    playback_ok = _ensure_playback_fps_60(project)
    project_fps = _fps_from_project(project)
    playback_fps = _safe_int_from_project_setting(project, "timelinePlaybackFrameRate", DEFAULT_FPS)
    _log(f"project_playback_diag timelineFrameRate={project_fps} timelinePlaybackFrameRate={playback_fps}")

    created_timelines: list[Any] = []
    warnings: list[str] = []
    if not playback_ok or playback_fps != 60:
        warnings.append(
            f"Resolve playback frame rate is {playback_fps} (expected 60). Preview may appear slowed/choppy until project playback is set to 60 fps."
        )
    plan_map: dict[str, ClipPlan] = {}
    resolved_source_by_clip: dict[str, Path] = {}
    source_fps_by_clip: dict[str, float] = {}
    source_fps_cache: dict[str, float] = {}
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

    total_plans = max(1, len(plans))
    if callable(progress_cb):
        progress_cb("Batch", 0, total_plans, "Preparation timelines")

    for idx_plan, plan in enumerate(plans, start=1):
        src = _resolve_existing_source(plan.source_path)
        if src is None:
            raw_src = Path(plan.source_path)
            if not raw_src.is_absolute():
                raw_src = (root / raw_src).resolve()
            warnings.append(f"Missing source file: {raw_src}")
            if callable(progress_cb):
                progress_cb("Batch", idx_plan, total_plans, f"Skip source manquante {idx_plan}/{total_plans}")
            continue
        if not src.exists():
            warnings.append(f"Missing source file: {src}")
            if callable(progress_cb):
                progress_cb("Batch", idx_plan, total_plans, f"Skip source absente {idx_plan}/{total_plans}")
            continue

        item = _ensure_media_item(media_pool, src)
        if item is None:
            warnings.append(f"Could not import media: {src}")
            if callable(progress_cb):
                progress_cb("Batch", idx_plan, total_plans, f"Skip import media {idx_plan}/{total_plans}")
            continue

        source_key = str(src.resolve()).lower()
        source_fps = source_fps_cache.get(source_key)
        if source_fps is None:
            source_fps = _source_fps_for_media_item(item, src, project_fps)
            source_fps_cache[source_key] = source_fps
        start_frame = int(round(plan.start_seconds * source_fps))
        end_frame = int(round(plan.end_seconds * source_fps))
        if end_frame <= start_frame:
            warnings.append(f"Invalid range for {plan.clip_id}")
            if callable(progress_cb):
                progress_cb("Batch", idx_plan, total_plans, f"Skip range invalide {idx_plan}/{total_plans}")
            continue
        _log(
            f"clip_frame_map clip={plan.clip_id} project_fps={project_fps} source_fps={source_fps:.3f} "
            f"start_s={plan.start_seconds:.3f} end_s={plan.end_seconds:.3f} start_f={start_frame} end_f={end_frame}"
        )

        timeline_name = str(plan.timeline_name or "").strip()
        if not timeline_name:
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
        tl = _create_timeline_for_clip_with_preset(project, media_pool, timeline_name, item, start_frame, end_frame, selected_preset)
        if tl is None:
            warnings.append(f"Could not create timeline for {plan.clip_id}")
            if callable(progress_cb):
                progress_cb("Batch", idx_plan, total_plans, f"Echec timeline {idx_plan}/{total_plans}")
            continue

        expected_duration_s = max(0.0, plan.end_seconds - plan.start_seconds)
        preset_mode = str(selected_preset.get("mode", "single"))
        _log_timeline_diagnostics(tl, plan, expected_duration_s, preset_mode)

        if plan.subtitle_path:
            subtitle_eligible += 1
            sub_path = Path(plan.subtitle_path)
            if not sub_path.is_absolute():
                sub_path = (root / sub_path).resolve()
            if not sub_path.exists():
                warnings.append(f"Subtitle file missing for timeline import: {plan.clip_id}")
                _log(f"subtitle_timeline_missing clip={plan.clip_id} path={sub_path}")
            else:
                ok_sub, sub_msg = _import_subtitles_to_timeline(
                    project,
                    media_pool,
                    tl,
                    sub_path,
                    template_name=subtitle_template_name,
                    offset_ms=subtitle_offset_ms,
                )
                if ok_sub:
                    subtitle_imported += 1
                    _log(f"subtitle_timeline_import_ok clip={plan.clip_id} msg={sub_msg}")
                    _log_timeline_diagnostics(tl, plan, expected_duration_s, preset_mode + "+sub")
                else:
                    warnings.append(f"Subtitle timeline import failed for {plan.clip_id}: {sub_msg}")
                    _log(f"subtitle_timeline_import_failed clip={plan.clip_id} msg={sub_msg}")
            if callable(progress_cb):
                progress_cb(
                    "Application sous-titres",
                    subtitle_imported,
                    max(1, subtitle_eligible),
                    f"Sous-titres timeline {subtitle_imported}/{max(1, subtitle_eligible)}",
                )
        elif require_subtitles:
            warnings.append(f"Subtitle missing in manifest for {plan.clip_id}")

        created_timelines.append(tl)
        plan_map[_plan_key(plan)] = plan
        resolved_source_by_clip[_plan_key(plan)] = src
        source_fps_by_clip[_plan_key(plan)] = source_fps
        if callable(progress_cb):
            progress_cb("Batch", idx_plan, total_plans, f"Timeline {idx_plan}/{total_plans}")

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
                source_fps = source_fps_by_clip.get(_plan_key(plan), float(max(1, project_fps)))
                start_frame = int(round(plan.start_seconds * source_fps))
                end_frame = int(round(plan.end_seconds * source_fps))
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

    if callable(progress_cb):
        progress_cb("Batch", total_plans, total_plans, "Batch termine")

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
    loader_closing = False
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

        def _loader_alive() -> bool:
            if loading_root is None:
                return False
            try:
                return bool(loading_root.winfo_exists())
            except Exception:
                return False

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
            if loading_text_canvas is None or not loading_text_items:
                return
            if not _loader_alive():
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
            if loading_image_label is None:
                return
            if not _loader_alive():
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
                if not _loader_alive() or not anim_state.get("loop", True):
                    return
                phase_name, duration = phases[index % len(phases)]
                _log(f"loader_phase={phase_name}")
                set_anim(phase_name)
                phase_job = loading_root.after(duration, lambda: step(index + 1))

            step(0)

        def stop_phase_loop() -> None:
            nonlocal phase_job, frame_job, text_wave_job
            anim_state["loop"] = False
            root_ref = loading_root
            if root_ref is None:
                phase_job = None
                frame_job = None
                text_wave_job = None
                return
            if phase_job is not None:
                try:
                    root_ref.after_cancel(phase_job)
                except Exception:
                    pass
                phase_job = None
            if frame_job is not None:
                try:
                    root_ref.after_cancel(frame_job)
                except Exception:
                    pass
                frame_job = None
            if text_wave_job is not None:
                try:
                    root_ref.after_cancel(text_wave_job)
                except Exception:
                    pass
                text_wave_job = None

        def _safe_destroy_loader() -> None:
            nonlocal loading_root, loader_closing
            if loader_closing:
                return
            loader_closing = True
            stop_phase_loop()
            root_ref = loading_root
            loading_root = None
            if root_ref is None:
                _log("kirby_loader_end")
                return
            try:
                if root_ref.winfo_exists():
                    root_ref.destroy()
            except Exception:
                pass
            _log("kirby_loader_end")

        def final_dance_then_close() -> None:
            if not _loader_alive():
                return
            _log("loader_final_dance_start")
            try:
                set_anim("dance")
            except Exception:
                _safe_destroy_loader()
                return

            def close_now() -> None:
                _safe_destroy_loader()

            try:
                if loading_root is not None:
                    loading_root.after(2000, close_now)
            except Exception:
                _safe_destroy_loader()

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
            stopper = getattr(loading_root, "_stop_phase_loop", None)
            if callable(stopper):
                stopper()
            try:
                loading_root.destroy()
            except Exception:
                pass
            loading_root = None
        raise RuntimeError("Aucune VOD sélectionnée. Sélectionne une VOD pour continuer.")

    manifest_result: dict[str, Any] = {"manifest": None, "error": None}
    used_manifest_fallback = False
    reopened_existing_manifest = False

    existing_manifest = _find_existing_manifest_for_vod(root, auto_vod)
    if existing_manifest is not None:
        set_loading("Ancien batch détecté...")
        set_loading_progress("Confirmation réouverture", 18)
        if loading_root is not None:
            try:
                loading_root.lift()
                loading_root.focus_force()
                loading_root.update_idletasks()
                loading_root.update()
            except Exception:
                pass
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
        starter = getattr(loading_root, "_start_phase_loop", None)
        if callable(starter):
            starter()

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
                    stopper = getattr(loading_root, "_stop_phase_loop", None)
                    if callable(stopper):
                        stopper()
                    try:
                        loading_root.destroy()
                    except Exception:
                        pass
                    loading_root = None
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
    finalizer = getattr(loading_root, "_final_dance_then_close", None)
    if callable(finalizer):
        set_loading_progress("Finalisation", 97)
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
        set_loading_progress("Terminé", 100)
        stopper = getattr(loading_root, "_stop_phase_loop", None)
        if callable(stopper):
            stopper()
        try:
            loading_root.destroy()
        except Exception:
            pass
        loading_root = None
        _log("kirby_loader_end")
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

    def on_generate(params: dict[str, Any]) -> dict[str, Any] | str:
        manifest_value = session.get("manifest") or default_manifest
        if not manifest_value:
            return {"message": "Aucun manifest disponible. Relance le script pour en régénérer un.", "warnings": []}
        manifest_path = Path(manifest_value)
        manifest_data = _read_manifest_safe(manifest_path)
        output_dir = Path(params["output"])
        preset_name = str(params["render_preset"])
        render_master = bool(params["render_master"])
        preset_id = str(params["preset_id"])
        transcript_query = str(params["query"])
        use_transcript_for_selection = bool(params.get("use_transcript_for_selection", False))
        strict_manifest = bool(params.get("strict_manifest", False))
        require_subtitles = bool(params.get("require_subtitles", False))
        preview_safe_quality = bool(params.get("preview_safe_quality", True))
        generate_optimized_media_quality = bool(params.get("generate_optimized_media_quality", True))
        subtitle_template_name = str(params.get("subtitle_template_name", SUBTITLE_TEMPLATE_AUTO_LABEL) or SUBTITLE_TEMPLATE_AUTO_LABEL)
        try:
            subtitle_offset_ms = int(float(str(params.get("subtitle_offset_ms", "-500") or "-500")))
        except Exception:
            subtitle_offset_ms = -500
        vod_dir_raw = str(params.get("vod_dir", "")).strip()
        user_vod_dir = Path(vod_dir_raw) if vod_dir_raw else None
        detected_vod = session.get("detected_vod")
        progress_cb = params.get("_progress_cb")

        selected_preset = dict((presets_data.get("presets", {}) or {}).get(preset_id, {}))
        if not selected_preset:
            return {"message": f"Preset introuvable: {preset_id}", "warnings": []}

        if strict_manifest and bool(session.get("used_manifest_fallback", False)):
            fallback_msg = "Sous-titres auto annulés: la génération du manifest a échoué au démarrage et un manifest de secours est utilisé. Relance le script pour régénérer un manifest frais."
            _log(f"UI generate blocked (strict manifest): {fallback_msg}")
            return {"message": fallback_msg, "warnings": [fallback_msg]}

        if require_subtitles:
            current_has_valid_subtitles = bool(manifest_data and _manifest_has_valid_subtitles(root, manifest_data))
            if detected_vod is None or not Path(detected_vod).exists():
                return {"message": "Les sous-titres auto nécessitent une source VOD détectée. Sélectionne un clip dans Resolve puis relance.", "warnings": []}
            if preview_safe_quality:
                if callable(progress_cb):
                    progress_cb("Batch+sous-titres", 1, 100, "Application du mode aperçu fluide")
                preview_warnings = _apply_preview_safe_playback(project)
            else:
                preview_warnings = []
            detected_vod_path = Path(detected_vod)
            reusable_manifest: Path | None = None
            transcript_path = _transcript_path_for_vod(root, detected_vod_path)
            transcript_ok = transcript_path.exists()
            if callable(progress_cb):
                progress_cb("Batch+sous-titres", 3 if transcript_ok else 1, 100, "Vérification du cache transcript")
            if not transcript_ok:
                try:
                    from short_editor.transcription import ensure_transcript

                    ensure_transcript(detected_vod_path, _load_pipeline_config(root), root / "output" / "transcripts")
                    transcript_ok = transcript_path.exists()
                    _log(f"quality_transcript_generated path={transcript_path}")
                except Exception as exc:
                    _log(f"quality_transcript_generation_failed err={exc}")
            else:
                _log(f"quality_transcript_cache_hit path={transcript_path}")

            if transcript_ok and not current_has_valid_subtitles:
                reusable_manifest = _find_reusable_quality_manifest(
                    root,
                    detected_vod_path,
                    preset_id,
                    use_transcript_for_selection,
                )
                if reusable_manifest is not None:
                    manifest_path = reusable_manifest
                    session["manifest"] = manifest_path
                    session["used_manifest_fallback"] = False
                    session["use_transcript_for_selection"] = use_transcript_for_selection
                    _log(f"quality_manifest_cache_hit manifest={manifest_path}")
                    if callable(progress_cb):
                        progress_cb("Batch+sous-titres", 15, 100, "Manifest + sous-titres du cache réutilisés")
                else:
                    _log("quality_manifest_cache_miss")
            elif current_has_valid_subtitles:
                _log(f"quality_manifest_current_has_valid_subtitles manifest={manifest_path}")
            try:
                if reusable_manifest is None and not current_has_valid_subtitles:
                    manifest_path = _generate_manifest_for_vod(
                        root,
                        detected_vod_path,
                        generate_subtitles=True,
                        use_transcript_for_selection=use_transcript_for_selection,
                        progress_cb=progress_cb,
                        preset_id=preset_id,
                    )
                    session["manifest"] = manifest_path
                    session["used_manifest_fallback"] = False
                    session["use_transcript_for_selection"] = use_transcript_for_selection
                    _log(f"Regenerated manifest with subtitles: {manifest_path}")
            except Exception as exc:
                msg = f"Échec de génération du manifest avec sous-titres auto: {exc}"
                _log(msg)
                return {"message": msg, "warnings": [msg]}
        elif use_transcript_for_selection:
            if detected_vod is None or not Path(detected_vod).exists():
                return {"message": "La sélection par transcript nécessite une source VOD détectée. Sélectionne un clip dans Resolve puis relance.", "warnings": []}
            try:
                manifest_path = _generate_manifest_for_vod(
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
                _log(f"Regenerated manifest with transcript selection: {manifest_path}")
            except Exception as exc:
                msg = f"Échec de génération du manifest avec sélection transcript: {exc}"
                _log(msg)
                return {"message": msg, "warnings": [msg]}

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
            subtitle_template_name=subtitle_template_name,
            subtitle_offset_ms=subtitle_offset_ms,
            progress_cb=progress_cb,
        )

        if require_subtitles and generate_optimized_media_quality:
            try:
                opt_warnings, opt_report = _generate_optimized_media_for_batch(
                    root,
                    project,
                    media_pool,
                    batch_id,
                    timelines,
                    progress_cb=progress_cb,
                )
                warnings.extend(opt_warnings)
                warnings.append(f"Rapport médias optimisés: {opt_report}")
            except Exception as exc:
                warnings.append(f"Échec de génération des médias optimisés: {exc}")
                _log(f"optimized_media_generation_failed err={exc}")

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
        _log(f"UI generate: {msg}")
        return {"message": msg, "warnings": warnings}

    def on_update(params: dict[str, Any]) -> dict[str, Any] | str:
        if not session.get("batch_id"):
            return {"message": "Génère d'abord le batch.", "warnings": []}
        manifest_value = session.get("manifest") or default_manifest
        if not manifest_value:
            return {"message": "Aucun manifest disponible. Relance le script pour en régénérer un.", "warnings": []}
        manifest_path = Path(manifest_value)
        output_dir = Path(params["output"])
        preset_name = str(params["render_preset"])
        preset_id = str(params["preset_id"])
        transcript_query = str(params["query"])
        use_transcript_for_selection = bool(params.get("use_transcript_for_selection", False))
        subtitle_template_name = str(params.get("subtitle_template_name", SUBTITLE_TEMPLATE_AUTO_LABEL) or SUBTITLE_TEMPLATE_AUTO_LABEL)
        try:
            subtitle_offset_ms = int(float(str(params.get("subtitle_offset_ms", "-500") or "-500")))
        except Exception:
            subtitle_offset_ms = -500
        vod_dir_raw = str(params.get("vod_dir", "")).strip()
        user_vod_dir = Path(vod_dir_raw) if vod_dir_raw else None
        detected_vod = session.get("detected_vod")
        progress_cb = params.get("_progress_cb")
        selected_preset = dict((presets_data.get("presets", {}) or {}).get(preset_id, {}))
        if not selected_preset:
            return {"message": f"Preset introuvable: {preset_id}", "warnings": []}

        if use_transcript_for_selection:
            if detected_vod is None or not Path(detected_vod).exists():
                return {"message": "La sélection par transcript nécessite une source VOD détectée. Sélectionne un clip dans Resolve puis relance.", "warnings": []}
            try:
                manifest_path = _generate_manifest_for_vod(
                    root,
                    Path(detected_vod),
                    generate_subtitles=False,
                    use_transcript_for_selection=True,
                    progress_cb=progress_cb,
                )
                session["manifest"] = manifest_path
                session["used_manifest_fallback"] = False
                session["use_transcript_for_selection"] = True
                _log(f"Regenerated manifest for update with transcript selection: {manifest_path}")
            except Exception as exc:
                msg = f"Échec de génération du manifest avec sélection transcript: {exc}"
                _log(msg)
                return {"message": msg, "warnings": [msg]}

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
            subtitle_template_name=subtitle_template_name,
            subtitle_offset_ms=subtitle_offset_ms,
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
