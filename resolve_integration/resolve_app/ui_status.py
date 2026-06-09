from __future__ import annotations

import re
from typing import Any, Callable


def warning_span(message: str) -> tuple[int, int] | None:
    match = re.search(r"\(\d+\s+(?:warnings|avertissements)\)", message)
    if not match:
        return None
    return match.start(), match.end()


def open_warnings_window(tk: Any, parent: Any, colors: dict[str, str], warnings: list[str]) -> None:
    if not warnings:
        return
    top = tk.Toplevel(parent)
    top.title("Avertissements batch")
    top.geometry("980x420")
    top.configure(bg=colors["panel_alt"])

    tk.Label(
        top,
        text=f"{len(warnings)} avertissement(s)",
        bg=colors["panel_alt"],
        fg=colors["ink"],
        font=("Segoe UI", 10, "bold"),
        anchor="w",
    ).pack(fill="x", padx=10, pady=(10, 4))

    wrap = tk.Frame(top, bg=colors["panel_alt"])
    wrap.pack(fill="both", expand=True, padx=10, pady=(0, 10))
    scroll = tk.Scrollbar(wrap, orient="vertical")
    text = tk.Text(wrap, yscrollcommand=scroll.set, wrap="word", bg="#FFFFFF", fg=colors["ink"], bd=2, relief="sunken", font=("Consolas", 10))
    scroll.config(command=text.yview)
    scroll.pack(side="right", fill="y")
    text.pack(side="left", fill="both", expand=True)

    for index, warning in enumerate(warnings, start=1):
        text.insert("end", f"{index}. {warning}\n")
    text.config(state="disabled")


def set_status_text(status_var: Any, status_text: Any, message: str, last_warnings: list[str], warnings: list[str] | None = None) -> list[str]:
    if warnings is not None:
        last_warnings = list(warnings)
    status_var.set(message)
    status_text.config(state="normal")
    status_text.delete("1.0", "end")
    status_text.insert("1.0", message)
    status_text.tag_remove("clickable_warning", "1.0", "end")
    if last_warnings:
        span = warning_span(message)
        if span is not None:
            start, end = span
            status_text.tag_add("clickable_warning", f"1.0+{start}c", f"1.0+{end}c")
    status_text.config(state="disabled")
    return last_warnings


def configure_status_text_bindings(status_text: Any, open_warnings: Callable[[], None]) -> None:
    status_text.tag_configure("clickable_warning", foreground="#1D47C8", underline=1)
    status_text.tag_bind("clickable_warning", "<Button-1>", lambda _event: open_warnings())
    status_text.tag_bind("clickable_warning", "<Enter>", lambda _event: status_text.config(cursor="hand2"))
    status_text.tag_bind("clickable_warning", "<Leave>", lambda _event: status_text.config(cursor="arrow"))
