from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


FILLER_RE = re.compile(r"\b(euh+|heu+|hum+|bah+|ben+|genre|du coup|en fait)\b", re.IGNORECASE)
WORD_RE = re.compile(r"[\w]+(?:['’][\w]+)?", re.UNICODE)


def _ts(seconds: float) -> str:
    ms = max(0, int(round(seconds * 1000)))
    h, rem = divmod(ms, 3600000)
    m, rem = divmod(rem, 60000)
    s, ms2 = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms2:03d}"


def _clean_text(text: str, remove_fillers: bool) -> str:
    t = " ".join(text.split())
    t = re.sub(r"(\b\w+)\s+(['’])\s*(\w+\b)", r"\1\2\3", t)
    t = re.sub(r"\s+(['’])", r"\1", t)
    if remove_fillers:
        t = FILLER_RE.sub("", t)
        t = " ".join(t.split())
    t = re.sub(r"([,.;:!?])\1+", r"\1", t)
    t = re.sub(r"\s+([,.;:!?])", r"\1", t)
    t = re.sub(r"([,.;:!?])(\w)", r"\1 \2", t)
    return t.strip()


def _word_count(text: str) -> int:
    return len(WORD_RE.findall(text))


def _has_word(text: str) -> bool:
    return bool(WORD_RE.search(text))


def _chunk_words(words: list[dict[str, Any]], cfg: dict[str, Any]) -> list[dict[str, Any]]:
    max_chars = int(cfg.get("max_chars_per_line", 36)) * int(cfg.get("max_lines", 2))
    min_dur = float(cfg.get("min_duration_ms", 700)) / 1000.0
    max_dur = float(cfg.get("max_duration_ms", 2200)) / 1000.0
    max_hold = float(cfg.get("max_hold_ms", 2600)) / 1000.0
    cps_target = float(cfg.get("cps_target", 16.0))
    min_words = max(1, int(cfg.get("min_words_per_chunk", 2)))
    preferred_words = max(min_words, int(cfg.get("preferred_words_per_chunk", 3)))
    max_words = max(preferred_words, int(cfg.get("max_words_per_chunk", 4)))
    min_gap = max(0.0, float(cfg.get("min_inter_chunk_gap_ms", 40)) / 1000.0)

    out: list[dict[str, Any]] = []
    cur: list[dict[str, Any]] = []
    last_end = 0.0

    def flush() -> None:
        nonlocal last_end
        if not cur:
            return
        start = float(cur[0]["start"])
        end = float(cur[-1]["end"])
        text = " ".join(str(w["word"]).strip() for w in cur).strip()
        if not text:
            cur.clear()
            return

        if start < last_end + min_gap:
            start = last_end + min_gap
        if end <= start:
            end = start + 0.1

        dur = max(0.1, end - start)
        if dur < min_dur:
            end = start + min_dur
            dur = min_dur
        if dur > max_hold:
            end = start + max_hold
        last_end = end
        out.append({"start": start, "end": end, "text": text})
        cur.clear()

    for w in words:
        token = str(w.get("word", "")).strip()
        if not token:
            continue
        cur.append(w)
        start = float(cur[0]["start"])
        end = float(cur[-1]["end"])
        text = " ".join(str(x["word"]).strip() for x in cur).strip()
        n_words = _word_count(text)
        dur = max(0.1, end - start)
        cps = len(text) / dur
        punctuation_strong = token.endswith((".", "!", "?", ";", ":"))
        punctuation_weak = token.endswith((","))
        should_break = False
        if n_words >= max_words:
            should_break = True
        elif n_words >= preferred_words and (dur >= max_dur * 0.8 or cps > cps_target * 1.1):
            should_break = True
        elif len(text) >= max_chars or dur >= max_dur or cps > cps_target * 1.25:
            should_break = True
        elif punctuation_strong and n_words >= min_words:
            should_break = True
        elif punctuation_weak and n_words >= preferred_words and dur >= min_dur * 0.7:
            should_break = True
        if should_break:
            flush()
    flush()
    return out


def _to_srt_lines(chunks: list[dict[str, Any]], cfg: dict[str, Any]) -> list[str]:
    max_line = int(cfg.get("max_chars_per_line", 36))
    remove_fillers = bool(cfg.get("remove_fillers", True))
    lines: list[str] = []
    idx = 1
    for c in chunks:
        text = _clean_text(str(c.get("text", "")), remove_fillers)
        if not text or not _has_word(text):
            continue
        if len(text) > max_line:
            split_at = text.rfind(" ", 0, max_line + 1)
            if split_at > 0:
                text = text[:split_at].strip() + "\n" + text[split_at + 1 :].strip()
        lines.extend([str(idx), f"{_ts(float(c['start']))} --> {_ts(float(c['end']))}", text, ""])
        idx += 1
    return lines


def _segment_chunks(entries: list[dict[str, Any]], clip_start: float, clip_end: float, cfg: dict[str, Any]) -> list[dict[str, Any]]:
    min_dur = float(cfg.get("min_duration_ms", 700)) / 1000.0
    max_hold = float(cfg.get("max_hold_ms", 2600)) / 1000.0
    min_gap = max(0.0, float(cfg.get("min_inter_chunk_gap_ms", 40)) / 1000.0)
    out: list[dict[str, Any]] = []
    last_end = 0.0
    for e in entries:
        try:
            es = float(e.get("start", 0.0))
            ee = float(e.get("end", es))
        except Exception:
            continue
        if ee < clip_start or es > clip_end:
            continue
        text = str(e.get("text", "")).strip()
        if not text:
            continue
        start_local = max(0.0, es - clip_start)
        end_local = max(start_local + 0.1, min(clip_end, ee) - clip_start)
        if start_local < last_end + min_gap:
            start_local = last_end + min_gap
        if end_local <= start_local:
            end_local = start_local + 0.1
        if end_local - start_local < min_dur:
            end_local = start_local + min_dur
        if end_local - start_local > max_hold:
            end_local = start_local + max_hold
        last_end = end_local
        out.append({"start": start_local, "end": end_local, "text": text})
    return out


def generate_srt_for_clip(
    transcript_json_path: Path,
    clip_start: float,
    clip_end: float,
    out_srt_path: Path,
    cfg: dict[str, Any],
) -> bool:
    if not transcript_json_path.exists():
        return False
    with transcript_json_path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    entries = data.get("entries", []) if isinstance(data, dict) else []
    words: list[dict[str, Any]] = []
    for e in entries:
        for w in e.get("words", []) or []:
            try:
                ws = float(w.get("start", 0.0))
                we = float(w.get("end", ws))
            except Exception:
                continue
            if we < clip_start or ws > clip_end:
                continue
            words.append(
                {
                    "start": max(0.0, ws - clip_start),
                    "end": max(0.0, we - clip_start),
                    "word": str(w.get("word", "")).strip(),
                }
            )
    chunks: list[dict[str, Any]] = []
    if words:
        chunks = _chunk_words(words, cfg)
    if not chunks:
        chunks = _segment_chunks(entries, clip_start, clip_end, cfg)
    srt_lines = _to_srt_lines(chunks, cfg)
    if not srt_lines:
        return False
    out_srt_path.parent.mkdir(parents=True, exist_ok=True)
    with out_srt_path.open("w", encoding="utf-8") as f:
        f.write("\n".join(srt_lines).strip() + "\n")
    return True
