from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from resolve_integration.resolve_app.ui_main import (
    COLORS,
    COMPACT_GEOMETRY,
    EXPANDED_GEOMETRY,
    TRANSFORM_KEYS,
    active_preset_id,
    active_subtitle_preset_id,
    create_dream_background,
    create_form_label,
    create_header_and_tabs,
    create_option_menu,
    create_text_entry,
    create_ui_button,
    default_profile_id,
    initial_state,
    noop_sound,
    show_main_tab,
    start_companion_pulse,
)


class FakeButton:
    def __init__(self, parent, **kwargs):
        self.parent = parent
        self.kwargs = dict(kwargs)
        self.configs = []
        self.binds = []

    def configure(self, **kwargs):
        self.configs.append(dict(kwargs))
        self.kwargs.update(kwargs)

    def config(self, **kwargs):
        self.configure(**kwargs)

    def bind(self, event, callback, add=None):
        self.binds.append((event, callback, add))

    def pack(self, **kwargs):
        self.kwargs["pack"] = kwargs


class FakeWidget:
    instances = []

    def __init__(self, parent=None, **kwargs):
        self.parent = parent
        self.kwargs = dict(kwargs)
        self.configs = []
        self.binds = []
        self.grid_calls = []
        self.pack_calls = []
        self.forget_count = 0
        self.columnconfigure_calls = []
        self.rowconfigure_calls = []
        FakeWidget.instances.append(self)

    def grid(self, **kwargs):
        self.grid_calls.append(dict(kwargs))

    def pack(self, **kwargs):
        self.pack_calls.append(dict(kwargs))

    def grid_forget(self):
        self.forget_count += 1

    def configure(self, **kwargs):
        self.configs.append(dict(kwargs))
        self.kwargs.update(kwargs)

    def config(self, **kwargs):
        self.configure(**kwargs)

    def bind(self, event, callback, add=None):
        self.binds.append((event, callback, add))

    def columnconfigure(self, *args, **kwargs):
        self.columnconfigure_calls.append((args, kwargs))

    def rowconfigure(self, *args, **kwargs):
        self.rowconfigure_calls.append((args, kwargs))


class FakeTk:
    Button = FakeButton
    Entry = FakeWidget
    Frame = FakeWidget
    Label = FakeWidget

    @staticmethod
    def OptionMenu(parent, variable, *values):
        return FakeWidget(parent, variable=variable, values=list(values))


class FakeTkCanvas:
    def __init__(self) -> None:
        self.calls = []

    def call(self, *args):
        self.calls.append(args)


class FakeCanvas:
    instances = []

    def __init__(self, parent, **kwargs):
        self.parent = parent
        self.kwargs = dict(kwargs)
        self.operations = []
        self.tk = FakeTkCanvas()
        self._w = "canvas"
        FakeCanvas.instances.append(self)

    def place(self, **kwargs):
        self.operations.append(("place", kwargs))

    def pack(self, **kwargs):
        self.operations.append(("pack", kwargs))

    def delete(self, *args):
        self.operations.append(("delete", args))

    def create_rectangle(self, *args, **kwargs):
        self.operations.append(("rectangle", args, kwargs))

    def create_oval(self, *args, **kwargs):
        self.operations.append(("oval", args, kwargs))

    def create_text(self, *args, **kwargs):
        self.operations.append(("text", args, kwargs))


class FakeTkWithCanvas(FakeTk):
    Canvas = FakeCanvas


class FakeRoot:
    def __init__(self) -> None:
        self.binds = []
        self.after_calls = []

    def bind(self, event, callback, add=None):
        self.binds.append((event, callback, add))

    def after(self, delay, callback):
        self.after_calls.append((delay, callback))

    def winfo_width(self):
        return 640

    def winfo_height(self):
        return 480


class FakeFrame:
    def __init__(self):
        self.grid_calls = []
        self.forget_count = 0

    def grid_forget(self):
        self.forget_count += 1

    def grid(self, **kwargs):
        self.grid_calls.append(dict(kwargs))


class FakeEvent:
    def __init__(self, x=0, y=0):
        self.x = x
        self.y = y


class ResolveUiMainTests(unittest.TestCase):
    def test_constants_include_expected_window_and_transform_defaults(self) -> None:
        self.assertEqual(COMPACT_GEOMETRY, "1180x860")
        self.assertEqual(EXPANDED_GEOMETRY, "1180x1020")
        self.assertIn("zoom_x", TRANSFORM_KEYS)
        self.assertEqual(COLORS["bg"], "#6FD8FF")

    def test_default_profile_prefers_valo(self) -> None:
        self.assertEqual(default_profile_id({"misc": {}, "valo": {}}), "valo")
        self.assertEqual(default_profile_id({"first": {}, "valo2": {}}), "first")
        self.assertEqual(default_profile_id({}), "valo")

    def test_active_preset_uses_profile_when_valid_otherwise_first(self) -> None:
        profiles = {"valo": {"active_preset": "p2"}}
        presets = {"p1": {}, "p2": {}}

        self.assertEqual(active_preset_id(profiles, presets, "valo"), "p2")
        self.assertEqual(active_preset_id({"valo": {"active_preset": "missing"}}, presets, "valo"), "p1")

    def test_active_subtitle_preset_uses_default_when_empty(self) -> None:
        self.assertEqual(active_subtitle_preset_id({}, {}, "valo", "Minimal clean"), "Minimal clean")
        self.assertEqual(
            active_subtitle_preset_id({"valo": {"active_subtitle_preset": "Sub2"}}, {"Sub1": {}, "Sub2": {}}, "valo", "Minimal clean"),
            "Sub2",
        )

    def test_initial_state_builds_expected_paths_and_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            state = initial_state(
                root,
                {"valo": {"active_preset": "p1", "active_subtitle_preset": "Sub1"}},
                {"p1": {}},
                {"Sub1": {}},
                "H264",
                "Auto",
                "Minimal clean",
            )

        self.assertEqual(state["output_dir"], "")
        self.assertNotIn("vod_dir", state)
        self.assertEqual(state["render_preset"], "H264")
        self.assertEqual(state["profile"], "valo")
        self.assertEqual(state["preset_id"], "p1")
        self.assertEqual(state["subtitle_preset_id"], "Sub1")
        self.assertEqual(state["subtitle_template_name"], "Auto")
        self.assertEqual(state["subtitle_offset_ms"], "-500")

    def test_noop_sound_is_callable(self) -> None:
        self.assertIsNone(noop_sound())

    def test_create_ui_button_wraps_command_and_binds_hover_states(self) -> None:
        events = []

        def play_click() -> None:
            events.append("click")

        def play_hover() -> None:
            events.append("hover")

        def command() -> None:
            events.append("command")

        button = create_ui_button(FakeTk, object(), "Go", command, dict(COLORS), play_click, play_hover, primary=True)

        self.assertEqual(button.kwargs["text"], "✦ Go ✦")
        button.kwargs["command"]()
        self.assertEqual(events, ["click", "command"])
        enter = button.binds[0][1]
        leave = button.binds[1][1]
        enter(object())
        leave(object())
        self.assertEqual(events[-1], "hover")
        self.assertEqual(button.configs[-1]["relief"], "raised")

    def test_show_main_tab_switches_frames_and_button_styles(self) -> None:
        batch = FakeFrame()
        actions = FakeFrame()
        batch_btn = FakeButton(None)
        actions_btn = FakeButton(None)

        show_main_tab("actions", batch, actions, {"batch": batch_btn, "actions": actions_btn}, dict(COLORS))

        self.assertEqual(batch.forget_count, 1)
        self.assertEqual(actions.forget_count, 1)
        self.assertEqual(actions.grid_calls, [{"row": 0, "column": 0, "sticky": "nw"}])
        self.assertEqual(batch_btn.kwargs["relief"], "ridge")
        self.assertEqual(actions_btn.kwargs["relief"], "sunken")

    def test_create_dream_background_binds_mouse_and_schedules_draw(self) -> None:
        FakeCanvas.instances.clear()
        root = FakeRoot()
        clicks = []

        canvas, state = create_dream_background(FakeTkWithCanvas, root, dict(COLORS), lambda _msg: None, lambda: clicks.append("click"))

        self.assertIs(canvas, FakeCanvas.instances[0])
        self.assertEqual(canvas.kwargs["bg"], COLORS["sky"])
        self.assertEqual(root.binds[0][0], "<Motion>")
        self.assertEqual(root.binds[1][0], "<Button-1>")
        self.assertEqual(root.after_calls[0][0], 120)
        root.binds[0][1](FakeEvent(12, 34))
        self.assertEqual(state["mouse_x"], 12)
        root.binds[1][1](FakeEvent(20, 40))
        self.assertEqual(clicks, ["click"])
        self.assertEqual(len(state["sparkles"]), 4)
        root.after_calls[0][1]()
        self.assertGreater(state["tick"], 0)
        self.assertTrue(any(op[0] == "rectangle" for op in canvas.operations))

    def test_start_companion_pulse_schedules_and_draws_orb(self) -> None:
        root = FakeRoot()
        orb = FakeCanvas(None)

        start_companion_pulse(root, orb, dict(COLORS))

        self.assertEqual(root.after_calls[0][0], 180)
        root.after_calls[0][1]()
        self.assertTrue(any(op[0] == "oval" for op in orb.operations))
        self.assertTrue(any(op[0] == "text" for op in orb.operations))
        self.assertEqual(root.after_calls[-1][0], 160)

    def test_create_header_and_tabs_returns_main_frames_and_switcher(self) -> None:
        FakeWidget.instances.clear()
        FakeCanvas.instances.clear()
        root = FakeRoot()

        result = create_header_and_tabs(FakeTkWithCanvas, root, dict(COLORS))

        self.assertIn("tabs_body", result)
        self.assertIn("batch_tab", result)
        self.assertIn("actions_tab", result)
        self.assertIn("show_tab", result)
        self.assertEqual(result["tab_buttons"]["batch"].kwargs["text"], "☁ Batch génération ✧")
        self.assertEqual(result["tab_buttons"]["actions"].kwargs["text"], "♡ Actions timeline ★")
        self.assertEqual(root.after_calls[0][0], 180)

        result["show_tab"]("actions")

        self.assertEqual(result["actions_tab"].grid_calls[-1], {"row": 0, "column": 0, "sticky": "nw"})
        self.assertEqual(result["tab_buttons"]["actions"].kwargs["relief"], "sunken")
        self.assertEqual(result["tab_buttons"]["batch"].kwargs["relief"], "ridge")

    def test_create_form_label_entry_and_option_menu_apply_expected_style(self) -> None:
        parent = object()
        variable = object()

        label = create_form_label(FakeTk, parent, "Dossier", 1, 2, dict(COLORS))
        entry = create_text_entry(FakeTk, parent, variable, 3, 4, dict(COLORS), width=12, sticky="w")
        menu = create_option_menu(FakeTk, parent, variable, ["a", "b"], 5, 6, dict(COLORS))

        self.assertEqual(label.kwargs["text"], "♡ Dossier")
        self.assertEqual(label.grid_calls[-1], {"row": 1, "column": 2, "sticky": "w", "padx": 8, "pady": 6})
        self.assertEqual(entry.kwargs["width"], 12)
        self.assertEqual(entry.kwargs["textvariable"], variable)
        self.assertEqual(entry.grid_calls[-1]["sticky"], "w")
        self.assertEqual(menu.kwargs["values"], ["a", "b"])
        self.assertEqual(menu.kwargs["bg"], COLORS["sun"])
        self.assertEqual(menu.grid_calls[-1], {"row": 5, "column": 6, "padx": 8, "pady": 6, "sticky": "w"})


if __name__ == "__main__":
    unittest.main()
