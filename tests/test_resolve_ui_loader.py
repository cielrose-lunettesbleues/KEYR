from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from resolve_integration.resolve_app.ui_loader import KirbyLoader, load_gif_frames


class FakeTkModule:
    class PhotoImage:
        def __init__(self, file: str, format: str) -> None:
            index = int(format.rsplit(" ", 1)[-1])
            if index >= 3:
                raise RuntimeError("no more frames")
            self.file = file
            self.format = format


class ResolveUiLoaderTests(unittest.TestCase):
    def test_load_gif_frames_reads_until_photoimage_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            gif_path = Path(tmp_dir) / "anim.gif"
            gif_path.write_bytes(b"fake")

            frames = load_gif_frames(FakeTkModule, gif_path)

            self.assertEqual(len(frames), 3)
            self.assertEqual(frames[0].format, "gif -index 0")

    def test_load_gif_frames_missing_file_returns_empty(self) -> None:
        self.assertEqual(load_gif_frames(FakeTkModule, Path("missing.gif")), [])

    def test_loader_degrades_when_tk_unavailable(self) -> None:
        logs: list[str] = []

        loader = KirbyLoader(Path.cwd(), logs.append)

        if loader.root is None:
            self.assertTrue(any("Loading UI disabled" in line for line in logs))
        loader.destroy()


if __name__ == "__main__":
    unittest.main()
