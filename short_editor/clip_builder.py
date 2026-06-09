from __future__ import annotations

# Compatibility facade. The fallback clip discovery logic now lives in
# short_editor.fallback; keep this module so older imports do not break.
from .fallback import discover_fallback_candidates
from .trimming import trim_dead_air_on_boundaries

__all__ = ["discover_fallback_candidates", "trim_dead_air_on_boundaries"]
