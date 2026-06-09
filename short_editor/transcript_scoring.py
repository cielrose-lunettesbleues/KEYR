from __future__ import annotations

import json
import re
from pathlib import Path

from .models import VodManifest


BASE_FUNNY = {"mdr", "ptdr", "lol", "haha", "rires", "incroyable", "abus", "hilarant"}
BASE_CLIVANT = {"jamais", "toujours", "nul", "incroyable", "scam", "honte", "debat", "controverse"}
BASE_ETONNANT = {"wow", "what", "attends", "serieusement", "impossible", "incroyable", "dingue", "surpris"}


def simple_tokens(text: str) -> list[str]:
    return [token for token in re.findall(r"[a-zA-Z0-9']+", (text or "").lower()) if len(token) >= 3]


def load_transcript_entries_for_vod(vod: VodManifest, cfg: dict, work_dir: Path) -> list[dict]:
    out_dir = Path(cfg.get("paths", {}).get("output_dir", "output"))
    if not out_dir.is_absolute():
        out_dir = (work_dir.parent / out_dir).resolve()
    transcript_path = out_dir / "transcripts" / f"{Path(vod.source_path).stem}.json"
    if not transcript_path.exists():
        return []
    try:
        with transcript_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        entries = data.get("entries", [])
        return entries if isinstance(entries, list) else []
    except Exception:
        return []


def text_score_for_window(entries: list[dict], start: float, end: float, lexicon: dict) -> tuple[float, str]:
    text_parts: list[str] = []
    for entry in entries:
        try:
            entry_start = float(entry.get("start", 0.0))
            entry_end = float(entry.get("end", entry_start))
        except Exception:
            continue
        if entry_end < start or entry_start > end:
            continue
        text_parts.append(str(entry.get("text", "")))
    text = " ".join(text_parts)
    if not text.strip():
        return 0.0, ""
    tokens = simple_tokens(text)
    if not tokens:
        return 0.0, ""

    funny = sum(1 for token in tokens if token in BASE_FUNNY)
    clivant = sum(1 for token in tokens if token in BASE_CLIVANT)
    etonnant = sum(1 for token in tokens if token in BASE_ETONNANT)

    lex_cats = lexicon.get("categories", {}) if isinstance(lexicon, dict) else {}
    weighted = 0.0
    matched: list[str] = []
    for category in ("drole", "clivant", "etonnant"):
        table = lex_cats.get(category, {}) if isinstance(lex_cats, dict) else {}
        for token in tokens:
            weight = float(table.get(token, 0.0)) if isinstance(table, dict) else 0.0
            if abs(weight) > 0.0:
                weighted += weight
                if weight > 0:
                    matched.append(token)

    base = (0.45 * min(1.0, funny / 3.0)) + (0.25 * min(1.0, clivant / 3.0)) + (0.30 * min(1.0, etonnant / 3.0))
    learned = max(-1.0, min(1.5, weighted / max(6.0, len(tokens))))
    score = max(0.0, min(1.0, base + (0.35 * learned)))
    reason_bits = []
    if funny:
        reason_bits.append(f"funny={funny}")
    if clivant:
        reason_bits.append(f"clivant={clivant}")
    if etonnant:
        reason_bits.append(f"etonnant={etonnant}")
    if matched:
        reason_bits.append("matched=" + ",".join(sorted(set(matched))[:4]))
    return score, ";".join(reason_bits)
