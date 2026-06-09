from __future__ import annotations

import unittest
from typing import Any

from resolve_integration.resolve_app.preset_actions import (
    delete_preset_data,
    save_new_preset_data,
    save_overwrite_preset_data,
)


def build_preset(base: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    out["built"] = True
    return out


class PresetActionsTests(unittest.TestCase):
    def test_save_overwrite_existing_preset_sets_active_profile(self) -> None:
        data = {
            "presets": {"p1": {"name": "p1", "profile": "valo", "mode": "fixed_split"}},
            "profiles": {"valo": {"active_preset": "old"}},
        }

        result = save_overwrite_preset_data(data, "p1", "valo", build_preset)

        self.assertEqual(result, {"status": "saved", "preset_id": "p1"})
        self.assertTrue(data["presets"]["p1"]["built"])
        self.assertEqual(data["presets"]["p1"]["mode"], "fixed_split")
        self.assertEqual(data["profiles"]["valo"]["active_preset"], "p1")

    def test_save_overwrite_missing_preset_uses_default_base(self) -> None:
        data: dict[str, Any] = {"presets": {}, "profiles": {}}

        result = save_overwrite_preset_data(data, "new", "valo", build_preset)

        self.assertEqual(result["status"], "saved")
        self.assertEqual(data["presets"]["new"]["name"], "new")
        self.assertEqual(data["presets"]["new"]["profile"], "valo")
        self.assertEqual(data["presets"]["new"]["max_clip_seconds"], 45)

    def test_save_new_preset_clones_current_base_and_renames(self) -> None:
        data = {
            "presets": {"p1": {"name": "p1", "profile": "valo", "mode": "single"}},
            "profiles": {"valo": {"active_preset": "p1"}},
        }

        result = save_new_preset_data(data, "p1", "p2", "valo", build_preset)

        self.assertEqual(result, {"status": "saved", "preset_id": "p2"})
        self.assertEqual(data["presets"]["p2"]["name"], "p2")
        self.assertEqual(data["presets"]["p2"]["mode"], "single")
        self.assertEqual(data["profiles"]["valo"]["active_preset"], "p2")

    def test_delete_preset_prefers_same_profile_replacement(self) -> None:
        data = {
            "presets": {
                "delete_me": {"profile": "valo"},
                "same_profile": {"profile": "valo"},
                "other": {"profile": "misc"},
            },
            "profiles": {"valo": {"active_preset": "delete_me"}, "misc": {"active_preset": "other"}},
        }

        result = delete_preset_data(data, "delete_me")

        self.assertEqual(result, {"status": "deleted", "deleted": "delete_me", "replacement": "same_profile"})
        self.assertNotIn("delete_me", data["presets"])
        self.assertEqual(data["profiles"]["valo"]["active_preset"], "same_profile")
        self.assertEqual(data["profiles"]["misc"]["active_preset"], "other")

    def test_delete_last_preset_is_blocked(self) -> None:
        data = {"presets": {"only": {"profile": "valo"}}, "profiles": {}}

        result = delete_preset_data(data, "only")

        self.assertEqual(result, {"status": "last", "deleted": "only", "replacement": ""})
        self.assertIn("only", data["presets"])


if __name__ == "__main__":
    unittest.main()
