from __future__ import annotations

import time
from typing import Any


def progress_percent(current: int, total: int) -> int:
    safe_total = max(1, int(total))
    safe_current = max(0, int(current))
    return max(0, min(100, int(round((safe_current / safe_total) * 100))))


def progress_fill_x(percent: int, width: int) -> int:
    safe_percent = max(0, min(100, int(percent)))
    return 3 + int((max(1, width - 5) * safe_percent) / 100)


def format_elapsed(seconds: float) -> str:
    total = max(0, int(seconds))
    minutes, secs = divmod(total, 60)
    if minutes <= 0:
        return f"{secs}s"
    return f"{minutes}m{secs:02d}s"


def estimate_remaining_seconds(processed: float, total: float, elapsed_seconds: float) -> float | None:
    processed = max(0.0, float(processed))
    total = max(0.0, float(total))
    elapsed_seconds = max(0.0, float(elapsed_seconds))
    if processed <= 0 or total <= 0 or processed >= total or elapsed_seconds <= 0:
        return None
    rate = processed / elapsed_seconds
    if rate <= 0:
        return None
    return max(0.0, (total - processed) / rate)


def realtime_speed(processed_seconds: float, elapsed_seconds: float) -> float | None:
    elapsed_seconds = max(0.0, float(elapsed_seconds))
    if elapsed_seconds <= 0:
        return None
    return max(0.0, float(processed_seconds)) / elapsed_seconds


def progress_metrics_text(
    processed_seconds: float | None,
    total_seconds: float | None,
    elapsed_seconds: float,
    min_elapsed_for_eta: float = 15.0,
    min_processed_for_eta: float = 30.0,
) -> str:
    elapsed = format_elapsed(elapsed_seconds)
    if processed_seconds is None or total_seconds is None:
        return f"Écoulé: {elapsed}"
    processed = max(0.0, float(processed_seconds))
    total = max(0.0, float(total_seconds))
    speed = realtime_speed(processed, elapsed_seconds)
    speed_text = f"{speed:.1f}x temps réel" if speed is not None else "vitesse inconnue"
    if elapsed_seconds < min_elapsed_for_eta or processed < min_processed_for_eta:
        eta_text = "estimation en cours"
    else:
        remaining = estimate_remaining_seconds(processed, total, elapsed_seconds)
        eta_text = f"~{format_elapsed(remaining)} restantes" if remaining is not None else "presque terminé"
    return f"Écoulé: {elapsed} | Vitesse: {speed_text} | Restant: {eta_text}"


def heartbeat_text(detail: str, elapsed_seconds: float, stale_seconds: float) -> str:
    base = str(detail or "Traitement en cours...").strip()
    if elapsed_seconds < stale_seconds:
        return base
    return f"{base}\nToujours en cours depuis {format_elapsed(elapsed_seconds)}..."


class ModalProgress:
    def __init__(
        self,
        tk: Any,
        parent: Any,
        colors: dict[str, str],
        title: str,
        message: str,
        geometry: str = "420x120",
        show_stage: bool = False,
        show_percent: bool = False,
        show_bar: bool = False,
        bar_width: int = 360,
        fill_color_key: str = "sun",
    ) -> None:
        self.tk = tk
        self.colors = colors
        self.top = tk.Toplevel(parent)
        self.top.title(title)
        self.top.geometry(geometry)
        self.top.configure(bg=colors["panel_alt"])
        self.top.transient(parent)
        self.top.attributes("-topmost", True)
        self.top.grab_set()
        self.top.protocol("WM_DELETE_WINDOW", lambda: None)

        self.text = tk.StringVar(value=message)
        self.stage = tk.StringVar(value="Batch")
        self.percent = tk.StringVar(value="0%")
        self.metrics = tk.StringVar(value="Écoulé: 0s")
        self.bar_width = bar_width
        self.bar: Any | None = None
        self.fill: Any | None = None
        self.started_at = time.monotonic()
        self.last_update_at = self.started_at
        self.current_detail = message
        self.stale_seconds = 15.0
        self.processed_seconds: float | None = None
        self.total_seconds: float | None = None

        tk.Label(
            self.top,
            textvariable=self.text,
            bg=colors["panel_alt"],
            fg=colors["ink"],
            font=("Segoe UI", 10, "bold"),
            wraplength=max(100, bar_width + 20),
            justify="left",
            padx=12,
            pady=12,
        ).pack(fill="both", expand=True)
        if show_stage:
            tk.Label(self.top, textvariable=self.stage, bg=colors["panel_alt"], fg=colors["ink"], font=("Segoe UI", 9, "bold"), pady=2).pack()
        if show_percent:
            tk.Label(self.top, textvariable=self.percent, bg=colors["panel_alt"], fg=colors["ink"], font=("Segoe UI", 9), pady=0).pack()
        tk.Label(self.top, textvariable=self.metrics, bg=colors["panel_alt"], fg=colors["ink"], font=("Segoe UI", 8), pady=0).pack()
        if show_bar:
            self.bar = tk.Canvas(self.top, width=bar_width, height=16, bg=colors["panel_alt"], highlightthickness=0, bd=0)
            self.bar.pack(pady=(4, 10))
            self.bar.create_rectangle(2, 2, bar_width - 2, 14, fill=colors["sun_soft"], outline=colors["ink"], width=1)
            fill_color = colors.get(fill_color_key, colors["sun"])
            self.fill = self.bar.create_rectangle(3, 3, 3, 13, fill=fill_color, outline=fill_color, width=0)

    def set_text(self, message: str) -> None:
        self.current_detail = message
        self.last_update_at = time.monotonic()
        self.text.set(message)

    def set_batch_progress(
        self,
        stage: str,
        current: int,
        total: int,
        detail: str = "",
        processed_seconds: float | None = None,
        total_seconds: float | None = None,
    ) -> None:
        pct = progress_percent(current, total)
        self.last_update_at = time.monotonic()
        self.stage.set(f"Etape: {stage}")
        self.percent.set(f"{pct}% ({max(0, int(current))}/{max(1, int(total))})")
        if detail:
            self.current_detail = detail
            self.text.set(detail)
        self.processed_seconds = processed_seconds
        self.total_seconds = total_seconds
        self.metrics.set(progress_metrics_text(processed_seconds, total_seconds, time.monotonic() - self.started_at))
        self.set_bar_percent(pct)

    def set_bar_percent(self, percent: int) -> None:
        if self.bar is None or self.fill is None:
            return
        x2 = progress_fill_x(percent, self.bar_width)
        self.bar.coords(self.fill, 3, 3, max(3, x2), 13)

    def pump(self) -> None:
        self.refresh_heartbeat()
        try:
            self.top.update_idletasks()
            self.top.update()
        except Exception:
            pass

    def refresh_heartbeat(self) -> None:
        now = time.monotonic()
        elapsed = now - self.started_at
        stale = now - self.last_update_at
        if stale >= self.stale_seconds:
            self.text.set(heartbeat_text(self.current_detail, elapsed, self.stale_seconds))
        self.metrics.set(progress_metrics_text(self.processed_seconds, self.total_seconds, elapsed))

    def close(self) -> None:
        try:
            self.top.grab_release()
        except Exception:
            pass
        try:
            self.top.destroy()
        except Exception:
            pass
