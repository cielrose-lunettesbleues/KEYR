from __future__ import annotations

import csv
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path


STOPWORDS_FR = {
    "je", "tu", "il", "elle", "on", "nous", "vous", "ils", "elles", "de", "du", "des", "la", "le", "les", "un", "une",
    "et", "ou", "mais", "donc", "or", "ni", "car", "que", "qui", "quoi", "dont", "dans", "sur", "pour", "par", "avec",
    "pas", "plus", "tres", "comme", "cette", "cet", "ces", "mon", "ton", "son", "ma", "ta", "sa", "mes", "tes", "ses",
}


def _tokenize(text: str) -> list[str]:
    raw = re.findall(r"[a-zA-Z0-9']+", (text or "").lower())
    out: list[str] = []
    for t in raw:
        if len(t) < 3:
            continue
        if t in STOPWORDS_FR:
            continue
        out.append(t)
    return out


def _default_user_lexicon() -> dict:
    return {
        "version": 1,
        "updated_at": "",
        "categories": {
            "drole": {},
            "clivant": {},
            "etonnant": {},
        },
    }


def load_user_lexicon(path: Path) -> dict:
    if not path.exists():
        return _default_user_lexicon()
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return _default_user_lexicon()
        return data
    except Exception:
        return _default_user_lexicon()


def save_user_lexicon(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def save_batch_ratings(batch_id: str, ratings: list[dict[str, str]], feedback_dir: Path) -> tuple[Path, Path]:
    feedback_dir.mkdir(parents=True, exist_ok=True)
    history_dir = feedback_dir / "history"
    history_dir.mkdir(parents=True, exist_ok=True)
    latest = feedback_dir / "latest_feedback.csv"
    history = history_dir / f"{batch_id}_ratings.csv"
    fields = ["batch_id", "clip_id", "rating", "seed_type", "reason", "start_seconds", "end_seconds", "notes"]

    for out_path in (latest, history):
        with out_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            for row in ratings:
                writer.writerow({k: row.get(k, "") for k in fields})
    return latest, history


def enrich_lexicon_from_ratings(lexicon_path: Path, rated_clips: list[dict], transcript_entries: list[dict]) -> dict:
    lex = load_user_lexicon(lexicon_path)
    cats = lex.setdefault("categories", {"drole": {}, "clivant": {}, "etonnant": {}})
    for name in ("drole", "clivant", "etonnant"):
        cats.setdefault(name, {})

    for clip in rated_clips:
        try:
            start = float(clip.get("start_seconds", 0.0))
            end = float(clip.get("end_seconds", 0.0))
            rating = int(float(clip.get("rating", 3) or 3))
        except Exception:
            continue
        if rating == 3:
            continue
        text_parts: list[str] = []
        for e in transcript_entries:
            try:
                es = float(e.get("start", 0.0))
                ee = float(e.get("end", es))
            except Exception:
                continue
            if ee < start or es > end:
                continue
            text_parts.append(str(e.get("text", "")))
        toks = _tokenize(" ".join(text_parts))
        if not toks:
            continue

        cat = "drole"
        reason = str(clip.get("reason", "")).lower()
        if "surpris" in reason or "wow" in reason:
            cat = "etonnant"
        elif "cliv" in reason or "debate" in reason or "hot" in reason:
            cat = "clivant"

        delta = 0.6 if rating >= 4 else -0.4
        if rating >= 5:
            delta = 0.9
        if rating <= 1:
            delta = -0.7

        table = cats[cat]
        for t in toks:
            prev = float(table.get(t, 0.0))
            nxt = max(-3.0, min(3.0, prev + delta))
            table[t] = round(nxt, 3)

    lex["updated_at"] = datetime.utcnow().isoformat(timespec="seconds")
    save_user_lexicon(lexicon_path, lex)
    return lex


def load_feedback_csv(feedback_path: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with feedback_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


def summarize_feedback(rows: list[dict[str, str]]) -> dict:
    decisions = Counter((r.get("decision") or "").strip().lower() for r in rows)
    reasons = Counter((r.get("reason") or "").strip().lower() for r in rows)
    total = len(rows)
    acceptance = 0.0
    if total:
        acceptance = (decisions.get("keep", 0) + decisions.get("post", 0)) / total
    return {
        "total": total,
        "decisions": dict(decisions),
        "reasons": dict(reasons),
        "acceptance_rate": round(acceptance, 4),
    }


def apply_learning_rules(config: dict, summary: dict) -> dict:
    updated = dict(config)
    scoring = dict(updated.get("scoring", {}))
    weights = dict(scoring.get("weights", {}))
    reasons = summary.get("reasons", {})

    if reasons.get("bad_start", 0) >= 2:
        updated["video"]["chapter_pre_roll_seconds"] = max(
            6,
            int(updated["video"]["chapter_pre_roll_seconds"] - 2),
        )

    if reasons.get("too_long", 0) >= 2:
        updated["video"]["preferred_clip_seconds"] = max(
            30,
            int(updated["video"]["preferred_clip_seconds"] - 5),
        )

    if reasons.get("audio_bad", 0) >= 2:
        duck = updated["audio"]["ducking"]["duck_gain_db"]
        updated["audio"]["ducking"]["duck_gain_db"] = min(-4.0, duck - 1.0)

    if reasons.get("not_funny", 0) >= 2:
        weights["speech_intensity"] = round(min(0.5, weights.get("speech_intensity", 0.35) + 0.05), 3)
        weights["scene_pacing"] = round(min(0.3, weights.get("scene_pacing", 0.2) + 0.03), 3)

    scoring["weights"] = weights
    updated["scoring"] = scoring
    return updated
