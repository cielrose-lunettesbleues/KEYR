from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class AppState:
    """Manages UI application state, testable without Tk/Resolve.
    
    This class centralizes all mutable state for the Resolve script UI,
    making it easier to test, persist, and reason about state transitions.
    """

    # VOD/Manifest
    vod_path: Path | None = None
    manifest_path: Path | None = None
    batch_id: str = ""

    # Rendering
    output_dir: str = ""  # User's chosen Resolve output dir (empty = user will set in Resolve)
    render_preset: str = ""
    render_master: bool = False

    # Presets
    profile: str = ""
    preset_id: str = ""
    subtitle_preset_id: str = ""
    subtitle_template_name: str = ""
    subtitle_offset_ms: str = "-500"

    # Query/Filter
    query: str = ""
    quality_mode_enabled: bool = False
    denoise_enabled: bool = False

    def is_ready_to_generate(self) -> bool:
        """True if state is valid for batch generation.
        
        Requires:
        - VOD path exists
        - Manifest path exists
        - Preset ID is set
        """
        return bool(
            self.vod_path
            and self.vod_path.exists()
            and self.manifest_path
            and self.manifest_path.exists()
            and self.preset_id
        )

    def reset_vod(self) -> None:
        """Clear VOD-related state after clip selection changes."""
        self.vod_path = None
        self.manifest_path = None
        self.batch_id = ""

    def update_from_dict(self, data: dict[str, Any]) -> None:
        """Load state from dictionary (e.g., from config or session).
        
        Only updates fields that:
        1. Are attributes of this class
        2. Have matching keys in the input dict
        """
        for key, value in data.items():
            if hasattr(self, key):
                # Type coercion for Path fields
                if key.endswith("_path") or key in ("vod_path", "manifest_path"):
                    if value and not isinstance(value, Path):
                        value = Path(str(value))
                setattr(self, key, value)

    def to_dict(self) -> dict[str, Any]:
        """Export state to dictionary for persistence/testing.
        
        Converts Path objects to strings for JSON serialization.
        """
        data = {}
        for key in self.__dataclass_fields__.keys():
            value = getattr(self, key)
            # Convert Path to string
            if isinstance(value, Path):
                value = str(value)
            data[key] = value
        return data
