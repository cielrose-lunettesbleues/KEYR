from __future__ import annotations

from datetime import datetime
from pathlib import Path


def log_path() -> Path:
    return Path.home() / "Desktop" / "short_editor_resolve.log"


def log(message: str) -> None:
    line = f"[{datetime.now().isoformat(timespec='seconds')}] {message}\n"
    try:
        with log_path().open("a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass
