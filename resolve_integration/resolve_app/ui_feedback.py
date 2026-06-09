from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Callable

Logger = Callable[[str], None]
StatusSetter = Callable[[str], None]
RepoRoot = Callable[[], Path]
UiButton = Callable[..., Any]


def clip_rating_display_row(batch_id: str, clip: dict[str, Any], index: int) -> dict[str, str]:
    clip_id = str(clip.get("clip_id", f"clip_{index}"))
    display_name = str(clip.get("display_name", clip_id))
    timeline_label = f"{batch_id}__{display_name}"
    seed = str(clip.get("seed_type", ""))
    reason = str(clip.get("reason", ""))
    matched_terms = ""
    for part in reason.split(";"):
        value = part.strip()
        if value.startswith("matched="):
            matched_terms = value.replace("matched=", "").strip()
            break
    if not matched_terms and "transcript_discovery" in reason:
        matched_terms = "transcript"
    return {
        "clip_id": clip_id,
        "display_name": display_name,
        "timeline_label": timeline_label,
        "seed": seed,
        "reason": reason,
        "matched_terms": matched_terms,
        "search_blob": f"{timeline_label} {display_name} {clip_id} {seed} {reason} {matched_terms}".lower(),
    }


def build_rating_rows(batch_id: str, clips: list[dict[str, Any]], ratings: dict[str, Any]) -> list[dict[str, str]]:
    rows_out: list[dict[str, str]] = []
    for clip in clips:
        clip_id = str(clip.get("clip_id", ""))
        rating_value = 3
        rating_var = ratings.get(clip_id)
        if rating_var is not None:
            try:
                rating_value = int(rating_var.get())
            except Exception:
                rating_value = 3
        rows_out.append(
            {
                "batch_id": batch_id,
                "clip_id": clip_id,
                "rating": str(rating_value),
                "seed_type": str(clip.get("seed_type", "")),
                "reason": str(clip.get("reason", "")),
                "start_seconds": str(clip.get("start_seconds", "")),
                "end_seconds": str(clip.get("end_seconds", "")),
                "notes": "",
            }
        )
    return rows_out


def load_transcript_entries_for_feedback(root_dir: Path, clips: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not clips:
        return []
    source = str(clips[0].get("source_path", ""))
    if not source:
        return []
    transcript_path = root_dir / "output" / "transcripts" / f"{Path(source).stem}.json"
    if not transcript_path.exists():
        return []
    try:
        with transcript_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        entries = data.get("entries", []) if isinstance(data, dict) else []
        return entries if isinstance(entries, list) else []
    except Exception:
        return []


def open_rate_batch_window(
    tk: Any,
    parent: Any,
    colors: dict[str, str],
    ui_button: UiButton,
    manifest_value: Any,
    default_manifest: Path | None,
    repo_root: RepoRoot,
    set_status: StatusSetter,
    log: Logger,
) -> None:
    manifest_candidate = manifest_value or default_manifest
    if not manifest_candidate:
        set_status("Noter le batch indisponible: aucun manifest")
        return
    manifest_path = Path(manifest_candidate)
    if not manifest_path.exists():
        set_status("Noter le batch indisponible: manifest introuvable")
        return
    try:
        with manifest_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        clips = data.get("clips", []) if isinstance(data, dict) else []
        if not isinstance(clips, list):
            clips = []
        batch_id = str(data.get("batch_id", manifest_path.stem)) if isinstance(data, dict) else manifest_path.stem
    except Exception as exc:
        set_status(f"Noter le batch indisponible: {exc}")
        return

    top = tk.Toplevel(parent)
    top.title("Noter le batch")
    top.geometry("980x620")
    top.configure(bg=colors["panel_alt"])
    try:
        top.lift()
        top.focus_force()
    except Exception:
        pass

    tk.Label(top, text=f"Batch: {batch_id}", bg=colors["panel_alt"], fg=colors["ink"], font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=10, pady=(10, 2))
    search_var = tk.StringVar(value="")
    tk.Entry(top, textvariable=search_var, width=80, bd=2, relief="sunken").pack(anchor="w", padx=10, pady=(0, 8))

    wrap = tk.Frame(top, bg=colors["panel_alt"])
    wrap.pack(fill="both", expand=True, padx=10, pady=(0, 8))
    canvas = tk.Canvas(wrap, bg=colors["panel_alt"], highlightthickness=0)
    scroll = tk.Scrollbar(wrap, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=scroll.set)
    scroll.pack(side="right", fill="y")
    canvas.pack(side="left", fill="both", expand=True)
    rows = tk.Frame(canvas, bg=colors["panel_alt"])
    rows_window = canvas.create_window((0, 0), window=rows, anchor="nw")

    rows.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.bind("<Configure>", lambda e: canvas.itemconfigure(rows_window, width=e.width))

    ratings: dict[str, Any] = {}
    indexed_rows: list[tuple[Any, str]] = []

    def draw_stars(parent_widget: Any, rating_var: Any) -> None:
        buttons: list[Any] = []

        def refresh(value: int) -> None:
            for idx, button in enumerate(buttons, start=1):
                button.configure(text=("★" if idx <= value else "☆"))

        def set_value(value: int) -> None:
            rating_var.set(value)
            refresh(value)

        for i in range(1, 6):
            button = tk.Button(parent_widget, text="☆", bg=colors["sun_soft"], fg=colors["ink"], bd=1, relief="raised", padx=2, pady=0, command=lambda value=i: set_value(value))
            button.pack(side="left", padx=1)
            buttons.append(button)
        refresh(int(rating_var.get()))

    for index, clip in enumerate(clips):
        row_data = clip_rating_display_row(batch_id, clip, index)
        row = tk.Frame(rows, bg=colors["panel_alt"], bd=1, relief="groove")
        row.pack(fill="x", padx=2, pady=2)
        tk.Label(row, text=row_data["timeline_label"][:54], width=54, anchor="w", bg=colors["panel_alt"], fg=colors["ink"]).pack(side="left", padx=4)
        tk.Label(row, text=row_data["seed"], width=16, anchor="w", bg=colors["panel_alt"], fg=colors["ink"]).pack(side="left", padx=4)
        tk.Label(row, text=(row_data["matched_terms"] or "-"), width=40, anchor="w", bg=colors["panel_alt"], fg=colors["ink"]).pack(side="left", padx=4)
        rating_wrap = tk.Frame(row, bg=colors["panel_alt"])
        rating_wrap.pack(side="right", padx=8)
        ratings[row_data["clip_id"]] = tk.IntVar(value=3)
        draw_stars(rating_wrap, ratings[row_data["clip_id"]])
        indexed_rows.append((row, row_data["search_blob"]))

    def apply_filter(*_args: Any) -> None:
        query = search_var.get().strip().lower()
        for row, text_blob in indexed_rows:
            if not query or query in text_blob:
                row.pack(fill="x", padx=2, pady=2)
            else:
                row.pack_forget()

    search_var.trace_add("write", apply_filter)

    def save_feedback_and_learn() -> None:
        try:
            root_dir = repo_root()
            root_str = str(root_dir)
            if root_str not in sys.path:
                sys.path.insert(0, root_str)
            from short_editor.feedback import enrich_lexicon_from_ratings, save_batch_ratings

            rows_out = build_rating_rows(batch_id, clips, ratings)
            latest, history = save_batch_ratings(batch_id, rows_out, root_dir / "feedback")
            transcript_entries = load_transcript_entries_for_feedback(root_dir, clips)
            enrich_lexicon_from_ratings(root_dir / "config" / "transcript_lexicon_user.json", rows_out, transcript_entries)
            set_status(f"Feedback sauvegarde: {latest.name} | historique: {history.name}")
            top.destroy()
        except Exception as exc:
            log(f"rating_save_failed: {exc}")
            set_status(f"Erreur feedback: {exc}")

    controls = tk.Frame(top, bg=colors["panel_alt"])
    controls.pack(fill="x", padx=10, pady=(0, 10))
    ui_button(controls, "Valider et apprendre", save_feedback_and_learn, primary=True).pack(side="right", padx=6)
    ui_button(controls, "Fermer", top.destroy, primary=False).pack(side="right", padx=6)
