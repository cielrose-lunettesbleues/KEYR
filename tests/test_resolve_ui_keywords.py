from __future__ import annotations

import json
import tempfile
from pathlib import Path
import unittest

from resolve_integration.resolve_app.ui_keywords import (
    KEYWORD_CATEGORIES,
    keyword_rows_from_category_table,
    load_keyword_lexicon,
    parse_keyword_lines,
    parse_keyword_text_boxes,
)


class ResolveUiKeywordTests(unittest.TestCase):
    def test_keyword_rows_from_category_table_sorts_keys(self) -> None:
        self.assertEqual(keyword_rows_from_category_table({"z": 2, "a": 1}), ["a=1", "z=2"])
        self.assertEqual(keyword_rows_from_category_table([]), [])

    def test_parse_keyword_lines_normalizes_and_rounds(self) -> None:
        parsed, error = parse_keyword_lines("drole", ["  MDR = 1.23456 ", "", "wow=2"])

        self.assertEqual(error, "")
        self.assertEqual(parsed, {"mdr": 1.235, "wow": 2.0})

    def test_parse_keyword_lines_reports_errors(self) -> None:
        self.assertEqual(parse_keyword_lines("drole", ["bad"])[1], "drole ligne 1: format attendu mot=poids")
        self.assertEqual(parse_keyword_lines("drole", ["=1"])[1], "drole ligne 1: mot-clé vide")
        self.assertEqual(parse_keyword_lines("drole", ["x=nope"])[1], "drole ligne 1: poids invalide")

    def test_parse_keyword_text_boxes_fills_all_categories(self) -> None:
        parsed, error = parse_keyword_text_boxes({"drole": ["lol=1"], "clivant": ["hot=2"]})

        self.assertEqual(error, "")
        self.assertEqual(parsed, {"drole": {"lol": 1.0}, "clivant": {"hot": 2.0}, "etonnant": {}})

    def test_load_keyword_lexicon_normalizes_missing_categories(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "lexicon.json"
            path.write_text(json.dumps({"version": 2, "categories": {"drole": {"lol": 1}, "clivant": []}}), encoding="utf-8")

            data = load_keyword_lexicon(path)

            self.assertEqual(data["version"], 2)
            for category in KEYWORD_CATEGORIES:
                self.assertIsInstance(data["categories"][category], dict)


if __name__ == "__main__":
    unittest.main()
