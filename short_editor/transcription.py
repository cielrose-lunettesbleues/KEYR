from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def ensure_transcript(vod_path: Path, cfg: dict[str, Any], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"{vod_path.stem}.json"
    if out_path.exists():
        return out_path

    captions = cfg.get("captions", {})
    model_size = str(captions.get("model_size", "small"))
    device = str(captions.get("device", "auto"))
    compute_type = str(captions.get("compute_type", "int8"))
    language = str(captions.get("language", cfg.get("language", "fr")))

    try:
        from faster_whisper import WhisperModel
    except Exception as exc:
        raise RuntimeError("faster-whisper is not installed. Install faster-whisper and ctranslate2.") from exc

    model = WhisperModel(model_size, device=device, compute_type=compute_type)
    segments, info = model.transcribe(
        str(vod_path),
        language=language,
        vad_filter=True,
        word_timestamps=True,
        condition_on_previous_text=True,
    )

    entries: list[dict[str, Any]] = []
    for seg in segments:
        words = []
        for w in getattr(seg, "words", []) or []:
            ws = float(getattr(w, "start", 0.0) or 0.0)
            we = float(getattr(w, "end", ws) or ws)
            wt = str(getattr(w, "word", "") or "").strip()
            if not wt:
                continue
            words.append({"start": ws, "end": we, "word": wt})
        entries.append(
            {
                "start": float(getattr(seg, "start", 0.0) or 0.0),
                "end": float(getattr(seg, "end", 0.0) or 0.0),
                "text": str(getattr(seg, "text", "") or "").strip(),
                "words": words,
            }
        )

    payload = {
        "source_path": str(vod_path),
        "language": language,
        "detected_language": getattr(info, "language", language),
        "duration": float(getattr(info, "duration", 0.0) or 0.0),
        "entries": entries,
    }
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
        f.write("\n")
    return out_path
