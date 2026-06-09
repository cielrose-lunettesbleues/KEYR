from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable


ProgressCallback = Callable[[str, int, int, str], None]


def _emit_progress(progress_cb: Any, stage: str, current: int, total: int, detail: str, meta: dict[str, Any] | None = None) -> None:
    if not callable(progress_cb):
        return
    try:
        progress_cb(stage, current, total, detail, meta or {})
    except TypeError:
        progress_cb(stage, current, total, detail)


def ensure_transcript(vod_path: Path, cfg: dict[str, Any], output_dir: Path, progress_cb: ProgressCallback | None = None) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"{vod_path.stem}.json"
    if out_path.exists():
        _emit_progress(progress_cb, "Transcript", 100, 100, f"Transcript déjà en cache: {out_path.name}")
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

    _emit_progress(progress_cb, "Transcript", 1, 100, f"Chargement du modèle Whisper {model_size} ({device}/{compute_type})")
    model = WhisperModel(model_size, device=device, compute_type=compute_type)
    _emit_progress(progress_cb, "Transcript", 5, 100, "Transcription locale Whisper en cours (première génération potentiellement longue)")
    segments, info = model.transcribe(
        str(vod_path),
        language=language,
        vad_filter=True,
        word_timestamps=True,
        condition_on_previous_text=True,
    )

    entries: list[dict[str, Any]] = []
    duration = float(getattr(info, "duration", 0.0) or 0.0)
    for seg in segments:
        seg_end = float(getattr(seg, "end", 0.0) or 0.0)
        if duration > 0:
            pct = max(5, min(94, int(round((seg_end / duration) * 90))))
            _emit_progress(
                progress_cb,
                "Transcript",
                pct,
                100,
                f"Transcription locale Whisper: {seg_end:.0f}s / {duration:.0f}s",
                {"processed_seconds": seg_end, "total_seconds": duration},
            )
        else:
            _emit_progress(progress_cb, "Transcript", 50, 100, "Transcription locale Whisper en cours")
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
        "duration": duration,
        "entries": entries,
    }
    _emit_progress(progress_cb, "Transcript", 95, 100, "Écriture du transcript")
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
        f.write("\n")
    _emit_progress(progress_cb, "Transcript", 100, 100, f"Transcript prêt: {out_path.name}")
    return out_path
