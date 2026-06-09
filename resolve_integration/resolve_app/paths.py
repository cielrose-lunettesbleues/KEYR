from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def script_path() -> Path | None:
    raw = globals().get("__file__")
    if raw:
        return Path(str(raw)).resolve()
    argv0 = sys.argv[0] if sys.argv else ""
    if argv0:
        p = Path(argv0)
        if p.exists():
            return p.resolve()
    return None


def script_config_path() -> Path | None:
    sp = script_path()
    if sp is not None:
        local = sp.with_name("short_editor_resolve_config.json")
        if local.exists():
            return local

    appdata = os.environ.get("APPDATA", "")
    if appdata:
        return Path(appdata) / "Blackmagic Design" / "DaVinci Resolve" / "Support" / "Fusion" / "Scripts" / "Utility" / "short_editor_resolve_config.json"
    return None


def load_installed_config_root() -> Path | None:
    cfg = script_config_path()
    if cfg is None or not cfg.exists():
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


def repo_root() -> Path:
    configured = load_installed_config_root()
    if configured is not None:
        return configured
    module_root = Path(__file__).resolve().parents[2]
    if (module_root / "short_editor").exists():
        return module_root
    return Path.cwd()
