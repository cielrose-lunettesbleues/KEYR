from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from resolve_integration.resolve_app.ui_app_state import AppState


class TestAppState(unittest.TestCase):
    """Test AppState class for UI state management."""

    def test_init_defaults(self) -> None:
        """Test default initialization."""
        state = AppState()
        self.assertIsNone(state.vod_path)
        self.assertIsNone(state.manifest_path)
        self.assertEqual(state.batch_id, "")
        self.assertEqual(state.output_dir, "")
        self.assertEqual(state.render_preset, "")
        self.assertEqual(state.preset_id, "")
        self.assertFalse(state.quality_mode_enabled)

    def test_is_ready_to_generate_false_without_vod(self) -> None:
        """Test is_ready_to_generate returns False without VOD."""
        state = AppState()
        state.preset_id = "test_preset"
        self.assertFalse(state.is_ready_to_generate())

    def test_is_ready_to_generate_false_without_manifest(self) -> None:
        """Test is_ready_to_generate returns False without manifest."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state = AppState()
            state.vod_path = Path(tmpdir) / "test.mp4"
            state.vod_path.touch()
            state.preset_id = "test_preset"
            self.assertFalse(state.is_ready_to_generate())

    def test_is_ready_to_generate_false_without_preset(self) -> None:
        """Test is_ready_to_generate returns False without preset."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            state = AppState()
            state.vod_path = tmpdir_path / "test.mp4"
            state.vod_path.touch()
            state.manifest_path = tmpdir_path / "manifest.json"
            state.manifest_path.touch()
            self.assertFalse(state.is_ready_to_generate())

    def test_is_ready_to_generate_true_when_valid(self) -> None:
        """Test is_ready_to_generate returns True when state is valid."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            state = AppState()
            state.vod_path = tmpdir_path / "test.mp4"
            state.vod_path.touch()
            state.manifest_path = tmpdir_path / "manifest.json"
            state.manifest_path.touch()
            state.preset_id = "test_preset"
            self.assertTrue(state.is_ready_to_generate())

    def test_reset_vod(self) -> None:
        """Test reset_vod clears VOD-related state."""
        state = AppState()
        state.vod_path = Path("/tmp/test.mp4")
        state.manifest_path = Path("/tmp/manifest.json")
        state.batch_id = "batch_123"
        state.query = "some query"  # Should NOT be cleared
        state.reset_vod()
        self.assertIsNone(state.vod_path)
        self.assertIsNone(state.manifest_path)
        self.assertEqual(state.batch_id, "")
        self.assertEqual(state.query, "some query")  # Preserved

    def test_update_from_dict_partial(self) -> None:
        """Test update_from_dict with partial data."""
        state = AppState()
        state.update_from_dict({"preset_id": "custom", "query": "test"})
        self.assertEqual(state.preset_id, "custom")
        self.assertEqual(state.query, "test")
        self.assertEqual(state.batch_id, "")  # Unchanged

    def test_update_from_dict_ignores_unknown_keys(self) -> None:
        """Test update_from_dict ignores unknown keys."""
        state = AppState()
        state.update_from_dict({"unknown_key": "value", "preset_id": "custom"})
        self.assertEqual(state.preset_id, "custom")
        self.assertFalse(hasattr(state, "unknown_key"))

    def test_update_from_dict_converts_string_to_path(self) -> None:
        """Test update_from_dict converts string paths to Path objects."""
        state = AppState()
        test_path = "/tmp/test.mp4"
        state.update_from_dict({"vod_path": test_path})
        self.assertIsInstance(state.vod_path, Path)
        self.assertEqual(state.vod_path, Path(test_path))

    def test_update_from_dict_handles_none_path(self) -> None:
        """Test update_from_dict handles None path values."""
        state = AppState()
        state.vod_path = Path("/tmp/test.mp4")
        state.update_from_dict({"vod_path": None})
        self.assertIsNone(state.vod_path)

    def test_to_dict_converts_path_to_string(self) -> None:
        """Test to_dict converts Path objects to strings."""
        test_path = Path("/tmp/test.mp4")
        state = AppState()
        state.vod_path = test_path
        state.preset_id = "custom"
        data = state.to_dict()
        # Path objects convert to their string representation
        self.assertEqual(data["vod_path"], str(test_path))
        self.assertEqual(data["preset_id"], "custom")
        self.assertIsInstance(data["vod_path"], str)

    def test_to_dict_round_trip(self) -> None:
        """Test to_dict + update_from_dict round trip."""
        state1 = AppState(
            preset_id="preset1",
            query="test query",
            subtitle_offset_ms="-1000",
            quality_mode_enabled=True,
        )
        state1.vod_path = Path("/tmp/test.mp4")
        dict_data = state1.to_dict()

        state2 = AppState()
        state2.update_from_dict(dict_data)

        self.assertEqual(state2.preset_id, state1.preset_id)
        self.assertEqual(state2.query, state1.query)
        self.assertEqual(state2.subtitle_offset_ms, state1.subtitle_offset_ms)
        self.assertEqual(state2.quality_mode_enabled, state1.quality_mode_enabled)
        self.assertEqual(str(state2.vod_path), str(state1.vod_path))


if __name__ == "__main__":
    unittest.main()
