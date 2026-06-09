from __future__ import annotations

import concurrent.futures
import importlib
import os
import sys
from pathlib import Path
from typing import Any

from .logging import log


def load_resolve(bmd_obj: Any | None = None) -> Any:
    try:
        dvr_script = importlib.import_module("DaVinciResolveScript")
        resolve = dvr_script.scriptapp("Resolve")
        if resolve is not None:
            log("Resolve loader: DaVinciResolveScript import OK")
            return resolve
    except Exception as exc:
        log(f"Resolve loader strategy 1 failed: {exc}")

    try:
        if bmd_obj is not None:
            resolve = bmd_obj.scriptapp("Resolve")
            if resolve is not None:
                log("Resolve loader: bmd.scriptapp OK")
                return resolve
    except Exception as exc:
        log(f"Resolve loader strategy 2 failed: {exc}")

    candidates = []
    appdata = os.environ.get("APPDATA", "")
    programdata = os.environ.get("PROGRAMDATA", "")
    programfiles = os.environ.get("PROGRAMFILES", "")
    if appdata:
        candidates.append(Path(appdata) / "Blackmagic Design" / "DaVinci Resolve" / "Support" / "Developer" / "Scripting" / "Modules")
    if programdata:
        candidates.append(Path(programdata) / "Blackmagic Design" / "DaVinci Resolve" / "Support" / "Developer" / "Scripting" / "Modules")
    if programfiles:
        candidates.append(Path(programfiles) / "Blackmagic Design" / "DaVinci Resolve" / "Developer" / "Scripting" / "Modules")

    for p in candidates:
        try:
            if p.exists():
                if str(p) not in sys.path:
                    sys.path.append(str(p))
                dvr_script = importlib.import_module("DaVinciResolveScript")
                resolve = dvr_script.scriptapp("Resolve")
                if resolve is not None:
                    log(f"Resolve loader: imported via path {p}")
                    return resolve
        except Exception as exc:
            log(f"Resolve loader strategy 3 failed for {p}: {exc}")

    raise RuntimeError(
        "Could not load Resolve scripting API. In Resolve, enable Preferences > System > General > External Scripting = Local, then restart Resolve."
    )


def safe_call(obj: Any, method_name: str, *args: Any, default: Any = None, required: bool = False, timeout_sec: float = 5.0) -> Any:
    attr = getattr(obj, method_name, None)
    log(f"CALL {type(obj).__name__}.{method_name} callable={callable(attr)}")
    if not callable(attr):
        msg = f"Method not callable: {type(obj).__name__}.{method_name}"
        log(msg)
        if required:
            raise RuntimeError(msg)
        return default
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    try:
        future = executor.submit(attr, *args)
        out = future.result(timeout=timeout_sec)
        log(f"OK {type(obj).__name__}.{method_name} -> {type(out).__name__}")
        return out
    except concurrent.futures.TimeoutError:
        msg = f"TIMEOUT {type(obj).__name__}.{method_name} after {timeout_sec}s"
        log(msg)
        if required:
            raise RuntimeError(msg)
        return default
    except Exception as exc:
        log(f"ERR {type(obj).__name__}.{method_name}: {exc}")
        if required:
            raise
        return default
    finally:
        # shutdown(wait=False) so a hung Resolve RPC thread never blocks the caller
        executor.shutdown(wait=False)
