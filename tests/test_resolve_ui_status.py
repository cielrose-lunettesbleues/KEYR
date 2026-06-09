from __future__ import annotations

from typing import Any
import unittest

from resolve_integration.resolve_app.ui_status import set_status_text, warning_span


class FakeVar:
    def __init__(self) -> None:
        self.value = ""

    def set(self, value: str) -> None:
        self.value = value


class FakeStatusText:
    def __init__(self) -> None:
        self.text = ""
        self.configs: list[dict[str, Any]] = []
        self.tags_added: list[tuple[str, str, str]] = []
        self.tags_removed: list[tuple[str, str, str]] = []

    def config(self, **kwargs: Any) -> None:
        self.configs.append(kwargs)

    def delete(self, _start: str, _end: str) -> None:
        self.text = ""

    def insert(self, _start: str, value: str) -> None:
        self.text = value

    def tag_remove(self, tag: str, start: str, end: str) -> None:
        self.tags_removed.append((tag, start, end))

    def tag_add(self, tag: str, start: str, end: str) -> None:
        self.tags_added.append((tag, start, end))


class ResolveUiStatusTests(unittest.TestCase):
    def test_warning_span_detects_english_and_french_counts(self) -> None:
        self.assertEqual(warning_span("Generated (2 warnings)"), (10, 22))
        self.assertEqual(warning_span("Terminé (3 avertissements)"), (8, 26))
        self.assertIsNone(warning_span("Terminé sans warning"))

    def test_set_status_text_adds_clickable_tag_when_warnings_exist(self) -> None:
        var = FakeVar()
        text = FakeStatusText()

        out = set_status_text(var, text, "Generated (2 warnings)", [], ["a", "b"])

        self.assertEqual(out, ["a", "b"])
        self.assertEqual(var.value, "Generated (2 warnings)")
        self.assertEqual(text.text, "Generated (2 warnings)")
        self.assertEqual(text.tags_added, [("clickable_warning", "1.0+10c", "1.0+22c")])
        self.assertEqual(text.configs[0], {"state": "normal"})
        self.assertEqual(text.configs[-1], {"state": "disabled"})

    def test_set_status_text_keeps_warning_state_without_new_list(self) -> None:
        var = FakeVar()
        text = FakeStatusText()

        out = set_status_text(var, text, "Terminé", ["existing"], None)

        self.assertEqual(out, ["existing"])
        self.assertEqual(text.tags_added, [])


if __name__ == "__main__":
    unittest.main()
