from __future__ import annotations

import unittest

from resolve_integration.resolve_app.ui_presets import (
    coerce_layers_count,
    delete_subtitle_preset_data,
    editor_values_from_preset,
    preset_from_editor_values,
    slider_bounds,
    subtitle_preset_from_editor_values,
)


class ResolveUiPresetTests(unittest.TestCase):
    def test_slider_bounds_match_transform_types(self) -> None:
        self.assertEqual(slider_bounds("zoom_x"), (0.1, 8.0, 0.01))
        self.assertEqual(slider_bounds("pan"), (-1.0, 1.0, 0.01))
        self.assertEqual(slider_bounds("crop_top"), (0.0, 1.0, 0.01))

    def test_coerce_layers_count_clamps_and_defaults_by_mode(self) -> None:
        self.assertEqual(coerce_layers_count("9", "single"), 4)
        self.assertEqual(coerce_layers_count("0", "single"), 1)
        self.assertEqual(coerce_layers_count("bad", "fixed_split"), 2)
        self.assertEqual(coerce_layers_count("bad", "single"), 1)

    def test_editor_values_from_preset_prepares_fields(self) -> None:
        values = editor_values_from_preset(
            {
                "mode": "fixed_split",
                "safe_padding": 0.07,
                "camera": {"zoom_x": 1.25},
                "gameplay": {"pan": -0.2},
            }
        )

        self.assertEqual(values["mode"], "fixed_split")
        self.assertEqual(values["mode_label"], "mode: fixed_split")
        self.assertEqual(values["layers_count"], "2")
        self.assertEqual(values["fields"]["camera.zoom_x"], 1.25)
        self.assertEqual(values["fields"]["gameplay.pan"], -0.2)
        self.assertEqual(values["fields"]["single.tilt"], 0.0)

    def test_preset_from_editor_values_preserves_base_and_coerces_numbers(self) -> None:
        field_values = {
            "single.zoom_x": "1.5",
            "single.zoom_y": "bad",
            "gameplay.pan": "-0.3",
            "camera.crop_top": "0.2",
        }

        preset = preset_from_editor_values(
            {"name": "Preset", "profile": "valo"},
            "fixed_split",
            "3",
            "bad",
            field_values,
        )

        self.assertEqual(preset["name"], "Preset")
        self.assertEqual(preset["mode"], "fixed_split")
        self.assertEqual(preset["layers_count"], 3)
        self.assertEqual(preset["safe_padding"], 0.04)
        self.assertEqual(preset["single"]["zoom_x"], 1.5)
        self.assertEqual(preset["single"]["zoom_y"], 0.0)
        self.assertEqual(preset["gameplay"]["pan"], -0.3)
        self.assertEqual(preset["camera"]["crop_top"], 0.2)

    def test_subtitle_preset_from_editor_values_builds_and_clamps(self) -> None:
        preset = subtitle_preset_from_editor_values(
            {
                "name": "Clean",
                "font": "",
                "font_style": "",
                "font_size": "2.0",
                "color": "",
                "position_x": "-1",
                "position_y": "bad",
                "words_per_subtitle": "99",
                "max_chars_per_line": "2",
                "subtitle_template_name": "",
                "subtitle_offset_ms": "9999",
            },
            "Auto",
            lambda value, default, min_value=None, max_value=None: max(min_value, min(max_value, float(value))) if str(value).replace(".", "", 1).replace("-", "", 1).isdigit() else default,
            lambda value, default, min_value=None, max_value=None: max(min_value, min(max_value, int(float(value)))) if str(value).replace(".", "", 1).replace("-", "", 1).isdigit() else default,
        )

        self.assertIsNotNone(preset)
        assert preset is not None
        self.assertEqual(preset["name"], "Clean")
        self.assertEqual(preset["font"], "Arial")
        self.assertEqual(preset["font_style"], "Bold")
        self.assertEqual(preset["font_size"], 0.5)
        self.assertEqual(preset["color"], "#FFFFFF")
        self.assertEqual(preset["position_x"], 0.0)
        self.assertEqual(preset["position_y"], 0.82)
        self.assertEqual(preset["words_per_subtitle"], 8)
        self.assertEqual(preset["max_chars_per_line"], 8)
        self.assertEqual(preset["subtitle_template_name"], "Auto")
        self.assertEqual(preset["subtitle_offset_ms"], 5000)

    def test_subtitle_preset_from_editor_values_rejects_empty_name(self) -> None:
        preset = subtitle_preset_from_editor_values(
            {"name": "   "},
            "Auto",
            lambda value, default, min_value=None, max_value=None: default,
            lambda value, default, min_value=None, max_value=None: default,
        )

        self.assertIsNone(preset)

    def test_delete_subtitle_preset_data_updates_profiles(self) -> None:
        result = delete_subtitle_preset_data(
            {"A": {"name": "A"}, "B": {"name": "B"}},
            {"valo": {"active_subtitle_preset": "A"}, "jeu": {"active_subtitle_preset": "B"}},
            "A",
        )

        self.assertEqual(result["status"], "deleted")
        self.assertEqual(result["replacement"], "B")
        self.assertEqual(list(result["subtitle_presets"]), ["B"])
        self.assertEqual(result["profiles"]["valo"]["active_subtitle_preset"], "B")
        self.assertEqual(result["profiles"]["jeu"]["active_subtitle_preset"], "B")

    def test_delete_subtitle_preset_data_reports_last_and_missing(self) -> None:
        last = delete_subtitle_preset_data({"A": {}}, {}, "A")
        missing = delete_subtitle_preset_data({"A": {}}, {}, "B")

        self.assertEqual(last["status"], "last")
        self.assertEqual(missing["status"], "missing")


if __name__ == "__main__":
    unittest.main()
