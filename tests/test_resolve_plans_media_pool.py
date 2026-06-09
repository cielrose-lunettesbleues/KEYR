from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from resolve_integration.resolve_app.media_pool import ensure_batch_folder, ensure_shorteditor_subfolder, list_subtitle_template_candidates, path_from_clip_properties
from resolve_integration.resolve_app.plans import parse_manifest, plan_key, safe_name_token, suffix_timeline_name


def fake_safe_call(obj: Any, method: str, *args: Any, default: Any = None, required: bool = False) -> Any:
    try:
        return getattr(obj, method)(*args)
    except Exception:
        if required:
            raise
        return default


class FakeClip:
    def __init__(self, name: str, props: dict[str, Any] | None = None) -> None:
        self.name = name
        self.props = props or {}

    def GetName(self) -> str:
        return self.name

    def GetClipProperty(self) -> dict[str, Any]:
        return self.props


class FakeFolder:
    def __init__(self, clips: list[FakeClip], folders: list["FakeFolder"] | None = None, name: str = "folder") -> None:
        self.name = name
        self.clips = clips
        self.folders = folders or []

    def GetName(self) -> str:
        return self.name

    def GetClipList(self) -> list[FakeClip]:
        return self.clips

    def GetSubFolderList(self) -> list["FakeFolder"]:
        return self.folders


class FakeMediaPool:
    def __init__(self, root: FakeFolder) -> None:
        self.root = root
        self.current_folder: FakeFolder | None = None

    def GetRootFolder(self) -> FakeFolder:
        return self.root

    def AddSubFolder(self, parent: FakeFolder, name: str) -> FakeFolder:
        folder = FakeFolder([], name=name)
        parent.folders.append(folder)
        return folder

    def SetCurrentFolder(self, folder: FakeFolder) -> bool:
        self.current_folder = folder
        return True



class ResolvePlanAndMediaPoolTests(unittest.TestCase):
    def test_parse_manifest_skips_invalid_ranges_and_keeps_plan_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            manifest_path = Path(tmp_dir) / "batch.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "batch_id": "batch_001",
                        "clips": [
                            {
                                "clip_id": "clip_ok",
                                "display_name": "Auto 1",
                                "timeline_name": "Short_Auto_1",
                                "source_path": "vod.mp4",
                                "start_seconds": 10,
                                "end_seconds": 20,
                                "seed_type": "fallback_discovery",
                            },
                            {
                                "clip_id": "clip_bad",
                                "source_path": "vod.mp4",
                                "start_seconds": 20,
                                "end_seconds": 10,
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )

            batch_id, plans = parse_manifest(manifest_path)

            self.assertEqual(batch_id, "batch_001")
            self.assertEqual(len(plans), 1)
            self.assertEqual(plans[0].display_name, "Auto 1")
            self.assertEqual(plan_key(plans[0]), "clip_ok")

    def test_list_subtitle_template_candidates_walks_nested_folders(self) -> None:
        root = FakeFolder(
            clips=[FakeClip("Gameplay"), FakeClip("Clean Text+", {"Type": "Generator"})],
            folders=[FakeFolder([FakeClip("Subtitle Pop", {"Clip Type": "Fusion Title"})])],
        )
        media_pool = FakeMediaPool(root)

        names = list_subtitle_template_candidates(media_pool, fake_safe_call, ("Forced A", "Forced B"))

        self.assertIn("Clean Text+", names)
        self.assertIn("Subtitle Pop", names)
        self.assertNotIn("Gameplay", names)
        self.assertEqual(names[0], "Forced B")
        self.assertEqual(names[1], "Forced A")

    def test_path_from_clip_properties_returns_existing_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            source = Path(tmp_dir) / "vod.mp4"
            source.write_text("", encoding="utf-8")

            self.assertEqual(path_from_clip_properties({"File Path": str(source)}), str(source))

    def test_safe_name_token_and_suffix_timeline_name(self) -> None:
        self.assertEqual(safe_name_token('Auto: 1 / boss?'), "Auto 1 boss")
        self.assertEqual(safe_name_token('***'), "clip")
        self.assertEqual(suffix_timeline_name('Timeline 1'), "Timeline 1__silence_cut")
        self.assertEqual(suffix_timeline_name('Timeline 1__silence_cut'), "Timeline 1__silence_cut")

    def test_ensure_shorteditor_subfolder_reuses_existing_folder(self) -> None:
        target = FakeFolder([], name="Batch 1")
        short_editor = FakeFolder([], [target], name="ShortEditor")
        media_pool = FakeMediaPool(FakeFolder([], [short_editor], name="root"))

        out = ensure_shorteditor_subfolder(media_pool, "Batch 1", fake_safe_call)

        self.assertIs(out, target)
        self.assertIs(media_pool.current_folder, target)

    def test_ensure_batch_folder_creates_missing_path(self) -> None:
        root = FakeFolder([], name="root")
        media_pool = FakeMediaPool(root)

        out = ensure_batch_folder(media_pool, "batch_001", fake_safe_call)

        self.assertEqual(out.GetName(), "batch_001")
        self.assertEqual(root.folders[0].GetName(), "ShortEditor")
        self.assertIs(media_pool.current_folder, out)


if __name__ == "__main__":
    unittest.main()
