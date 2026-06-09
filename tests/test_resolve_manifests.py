from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from resolve_integration.resolve_app.manifests import (
    find_existing_manifest_for_vod,
    manifest_has_valid_textplus_source,
    manifest_matches_vod,
)


class ResolveManifestTests(unittest.TestCase):
    def test_manifest_matches_vod_from_meta(self) -> None:
        data = {"meta": {"source_vod_path": "E:/vods/session.mp4"}}

        self.assertTrue(manifest_matches_vod(data, Path("E:/other/session.mp4")))

    def test_manifest_has_valid_textplus_source_uses_transcript_not_subtitle_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            transcript = root / "output" / "transcripts" / "vod.json"
            transcript.parent.mkdir(parents=True)
            transcript.write_text('{"entries": []}', encoding="utf-8")
            data = {"meta": {"transcript_path": str(transcript)}, "clips": [{"subtitle_path": "legacy.srt"}]}

            self.assertTrue(manifest_has_valid_textplus_source(root, data))

    def test_find_existing_manifest_prefers_quality_manifest_for_vod(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            manifest_dir = root / "output" / "manifests"
            transcript = root / "output" / "transcripts" / "vod.json"
            manifest_dir.mkdir(parents=True)
            transcript.parent.mkdir(parents=True)
            transcript.write_text('{"entries": []}', encoding="utf-8")
            vod = root / "input" / "vod.mp4"
            vod.parent.mkdir(parents=True)
            vod.write_text("", encoding="utf-8")

            fast_manifest = manifest_dir / "fast.json"
            fast_manifest.write_text(json.dumps({"source_vods": [str(vod)], "clips": []}), encoding="utf-8")
            quality_manifest = manifest_dir / "quality.json"
            quality_manifest.write_text(
                json.dumps(
                    {
                        "source_vods": [str(vod)],
                        "meta": {"source_vod_path": str(vod), "generated_with_subtitles": True, "transcript_path": str(transcript)},
                        "clips": [],
                    }
                ),
                encoding="utf-8",
            )

            self.assertEqual(find_existing_manifest_for_vod(root, vod), quality_manifest)


if __name__ == "__main__":
    unittest.main()
