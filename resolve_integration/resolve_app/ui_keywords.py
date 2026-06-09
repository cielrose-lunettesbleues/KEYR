from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

KEYWORD_CATEGORIES = ("drole", "clivant", "etonnant")


def default_keyword_lexicon() -> dict[str, Any]:
    return {"version": 1, "updated_at": "", "categories": {name: {} for name in KEYWORD_CATEGORIES}}


def load_keyword_lexicon(path: Path) -> dict[str, Any]:
    data = default_keyword_lexicon()
    if path.exists():
        try:
            with path.open("r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                data = loaded
        except Exception:
            pass
    categories = data.get("categories", {}) if isinstance(data.get("categories", {}), dict) else {}
    for category in KEYWORD_CATEGORIES:
        if not isinstance(categories.get(category), dict):
            categories[category] = {}
    data["categories"] = categories
    return data


def keyword_rows_from_category_table(table: Any) -> list[str]:
    if not isinstance(table, dict):
        return []
    return [f"{key}={value}" for key, value in sorted(table.items(), key=lambda item: item[0])]


def parse_keyword_lines(category: str, lines: list[str]) -> tuple[dict[str, float] | None, str]:
    out: dict[str, float] = {}
    for line_no, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped:
            continue
        if "=" not in stripped:
            return None, f"{category} ligne {line_no}: format attendu mot=poids"
        key, value = stripped.split("=", 1)
        token = key.strip().lower()
        if not token:
            return None, f"{category} ligne {line_no}: mot-clé vide"
        try:
            weight = float(value.strip())
        except Exception:
            return None, f"{category} ligne {line_no}: poids invalide"
        out[token] = round(weight, 3)
    return out, ""


def parse_keyword_text_boxes(text_by_category: dict[str, list[str]]) -> tuple[dict[str, dict[str, float]] | None, str]:
    updated_categories: dict[str, dict[str, float]] = {name: {} for name in KEYWORD_CATEGORIES}
    for category in KEYWORD_CATEGORIES:
        parsed, error = parse_keyword_lines(category, text_by_category.get(category, []))
        if parsed is None:
            return None, error
        updated_categories[category] = parsed
    return updated_categories, ""


def open_keywords_editor(
    tk: Any,
    messagebox: Any,
    parent: Any,
    colors: dict[str, str],
    root_dir: Path,
    ui_button: Callable[..., Any],
    set_status: Callable[..., None],
) -> None:
    lexicon_path = root_dir / "config" / "transcript_lexicon_user.json"
    data = load_keyword_lexicon(lexicon_path)
    categories = data.get("categories", {}) if isinstance(data.get("categories", {}), dict) else {}

    top = tk.Toplevel(parent)
    top.title("Mots-clés transcript")
    top.geometry("780x560")
    top.configure(bg=colors["panel_alt"])
    top.transient(parent)

    frame = tk.Frame(top, bg=colors["panel_alt"])
    frame.pack(fill="both", expand=True, padx=10, pady=10)

    text_boxes: dict[str, Any] = {}
    for idx, category in enumerate(KEYWORD_CATEGORIES):
        section = tk.LabelFrame(frame, text=f"✧ {category} ✧", bg=colors["panel"], fg=colors["ink"], bd=4, relief="ridge")
        section.grid(row=0, column=idx, padx=6, pady=6, sticky="nsew")
        frame.grid_columnconfigure(idx, weight=1)
        frame.grid_rowconfigure(0, weight=1)

        text_box = tk.Text(section, width=24, height=24, bg=colors["sun_soft"], fg=colors["ink"], bd=3, relief="sunken", insertbackground=colors["accent"], font=("Tahoma", 9))
        text_box.pack(fill="both", expand=True, padx=6, pady=6)
        table = categories.get(category, {}) if isinstance(categories, dict) else {}
        text_box.insert("1.0", "\n".join(keyword_rows_from_category_table(table)))
        text_boxes[category] = text_box

    hint = tk.Label(
        top,
        text="Format: mot=poids (un par ligne). Exemple: incroyable=1.2",
        bg=colors["panel_alt"],
        fg=colors["ink"],
        anchor="w",
    )
    hint.pack(fill="x", padx=10, pady=(0, 6))

    def save_keywords() -> None:
        text_by_category = {category: box.get("1.0", "end").splitlines() for category, box in text_boxes.items()}
        updated_categories, parse_error = parse_keyword_text_boxes(text_by_category)
        if updated_categories is None:
            messagebox.showerror("Short Editor", parse_error)
            return

        data["version"] = int(data.get("version", 1) or 1)
        data["categories"] = updated_categories
        data["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        lexicon_path.parent.mkdir(parents=True, exist_ok=True)
        with lexicon_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
        set_status("Mots-clés transcript enregistrés", warnings=[])
        messagebox.showinfo("Short Editor", f"Enregistré: {lexicon_path}")

    controls = tk.Frame(top, bg=colors["panel_alt"])
    controls.pack(fill="x", padx=10, pady=(0, 8))
    ui_button(controls, "Enregistrer", save_keywords, primary=True).pack(side="right", padx=4)
    ui_button(controls, "Fermer", top.destroy, primary=False).pack(side="right", padx=4)
