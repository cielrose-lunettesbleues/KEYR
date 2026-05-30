## Short Editor (Automated Twitch VOD -> Shorts)

This project is a modular, batch-oriented pipeline to turn OBS Hybrid MP4 Twitch VODs into vertical short clips.

### Goals
- Always include OBS chapter moments.
- Target 2-3 clips per hour.
- Render vertical 1080x1920 at 60 FPS.
- Use French social-style captions.
- Support multi-track audio routing with easy mute/mix controls.
- Improve output quality after every batch through feedback.

### Quick Start
1. Install Python 3.11+.
2. Ensure `ffprobe` is available in `PATH`.
3. Put VOD MP4 files in `input/`.
4. Run:

```bash
python -m short_editor.cli run-batch --config config/pipeline.json
```

Or use easy Windows commands:

```bat
.\run_shorts.bat
```

5. Review generated files in `output/` and fill feedback in `feedback/`.
6. Run:

```bash
python -m short_editor.cli learn --config config/pipeline.json --feedback feedback/latest_feedback.csv
```

Or use:

```bat
.\learn_shorts.bat
```

### Structure
- `config/` pipeline settings and profile versions
- `input/` source OBS Hybrid MP4 files
- `work/` intermediate manifests and extracted data
- `output/` clip plans and reports
- `feedback/` batch review files
- `short_editor/` source modules

### Notes
- This v1 builds production-ready manifests and clip plans, with render/transcribe steps designed as swappable modules.
- You can integrate Hyperframes / Video-use orchestration by calling these module interfaces.
- If no chapters are found in an MP4, fallback discovery uses audio-energy peaks, silence/activity filtering, and a 3-second hook score, then adds a warning in the batch manifest.
- Chapter 0 (or any chapter at 0s) is treated as auto-start and always ignored.
- If chapter clips are below target quota, fallback discovery auto-completes the batch to target clip count.
- Exported review clips are written to `output/clips/<batch_id>/`.
- A review map is generated at `output/reports/<batch_id>.review.csv` with `clip_id -> file_path`.
- Default track routing is now optimized for your setup: voice analysis on track 2, context on track 5, Spotify muted (track 4), render base on track 6, and fallback skips first 8 minutes.

### DaVinci Resolve Integration (Phase A)
- Install script for Resolve menu:

```bat
.\INSTALL_RESOLVE_SCRIPT.bat
```

- Open DaVinci Resolve (Studio 20 Beta), open your project, then run:
  - `Workspace -> Scripts -> Utility -> run_shorts_batch_resolve`

- Script behavior:
  - uses current open Resolve project
  - auto-detects VOD from current Resolve context (selected/timeline clip first)
  - if not detected, asks you to pick a VOD file
  - auto-generates a fresh batch manifest before opening UI
  - lets you select `Valo`, `Jeu`, or `React` profile
  - opens a single master window (no popup chain)
  - keeps the window open after generation
  - includes built-in preset editor (`Load`, `Save`, `Save As`), collapsed by default
  - supports `Update Composition (Batch)` without regenerating manifest
  - uses a Y2K/XP-inspired UI theme (violet + yellow)
  - creates one timeline per clip + one `MASTER_REVIEW` timeline
  - queues H.264 shorts renders for clip timelines
  - optional transcript semantic query: "Fais un clip du moment ou je dis ..."

- You can choose whether to queue a render job for `MASTER_REVIEW` too.
- Shorts render output is forced to portrait target (`1080x1920 @ 60fps`).

### Resolve Presets
- Presets are stored in `config/resolve_presets.json`.
- The app can edit and save presets from Resolve UI (`Edit selected preset before run?`).
- Default includes:
  - `Valorant Preset` (fixed split, gameplay top + cam)
  - `Jeux`
  - `Just chatting`
