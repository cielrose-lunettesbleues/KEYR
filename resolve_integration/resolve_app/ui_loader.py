from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable

Logger = Callable[[str], None]


def load_gif_frames(tk_mod: Any, gif_path: Path) -> list[Any]:
    frames: list[Any] = []
    if not gif_path.exists():
        return frames
    index = 0
    while True:
        try:
            frame = tk_mod.PhotoImage(file=str(gif_path), format=f"gif -index {index}")
            frames.append(frame)
            index += 1
        except Exception:
            break
    return frames


class KirbyLoader:
    def __init__(self, project_root: Path, log: Logger) -> None:
        self.project_root = project_root
        self.log = log
        self.root: Any | None = None
        self.loading_text: Any | None = None
        self.loading_step_text: Any | None = None
        self.loading_percent_text: Any | None = None
        self.loading_progress_canvas: Any | None = None
        self.loading_progress_fill: Any | None = None
        self.loading_progress_value = 0
        self.loading_text_canvas: Any | None = None
        self.loading_text_items: list[Any] = []
        self.text_message = "Kirby eats your VOD..."
        self.text_wave_job: Any | None = None
        self.text_wave_index = 0
        self.loading_image_label: Any | None = None
        self.loading_mode = "text"
        self.loader_closing = False
        self.frame_job: Any | None = None
        self.phase_job: Any | None = None
        self.anim_frames: dict[str, list[Any]] = {"idle": [], "suck": [], "digest": [], "dance": []}
        self.anim_state: dict[str, Any] = {"name": "", "idx": 0, "loop": True}
        self._init_ui()

    def _init_ui(self) -> None:
        try:
            import tkinter as tk

            self.root = tk.Tk()
            self.root.title("Short Editor")
            self.root.geometry("500x156")
            self.root.configure(bg="#E7ECFF")
            self.root.attributes("-topmost", True)
            self.loading_text = tk.StringVar(value=self.text_message)
            self.loading_text_canvas = tk.Canvas(self.root, width=440, height=40, bg="#E7ECFF", highlightthickness=0, bd=0)
            self.loading_text_canvas.pack(pady=(8, 2))
            self.loading_image_label = tk.Label(self.root, bg="#E7ECFF")
            self.loading_image_label.pack(pady=(2, 4))

            assets = self.project_root / "resolve_integration" / "assets"
            self.anim_frames["idle"] = load_gif_frames(tk, assets / "kirby_idle.gif")
            self.anim_frames["suck"] = load_gif_frames(tk, assets / "kirby_suck.gif")
            self.anim_frames["digest"] = load_gif_frames(tk, assets / "kirby_digest.gif")
            self.anim_frames["dance"] = load_gif_frames(tk, assets / "kirby_dance.gif")
            if self.anim_frames["idle"] and self.anim_frames["suck"] and self.anim_frames["digest"] and self.anim_frames["dance"]:
                self.loading_mode = "gif"
                self.log("kirby_loader_start")
            else:
                self.log("kirby_loader_fallback_text_mode")
            tk.Label(
                self.root,
                text="Short Editor",
                bg="#E7ECFF",
                fg="#6D4DFF",
                font=("Segoe UI", 12, "bold"),
            ).pack(pady=(8, 2))
            self.loading_step_text = tk.StringVar(value="Step: Initializing")
            self.loading_percent_text = tk.StringVar(value="0%")
            tk.Label(
                self.root,
                textvariable=self.loading_step_text,
                bg="#E7ECFF",
                fg="#1E1E2A",
                font=("Segoe UI", 9, "bold"),
            ).pack(pady=(0, 1))
            tk.Label(
                self.root,
                textvariable=self.loading_percent_text,
                bg="#E7ECFF",
                fg="#6D4DFF",
                font=("Segoe UI", 9, "bold"),
            ).pack(pady=(0, 3))

            self.loading_progress_canvas = tk.Canvas(self.root, width=360, height=16, bg="#E7ECFF", highlightthickness=0, bd=0)
            self.loading_progress_canvas.pack(pady=(0, 6))
            self.loading_progress_canvas.create_rectangle(2, 2, 358, 14, fill="#FFF3B3", outline="#7E69D9", width=1)
            self.loading_progress_fill = self.loading_progress_canvas.create_rectangle(3, 3, 3, 13, fill="#6D4DFF", outline="#6D4DFF", width=0)
            self.log("loader_bar_canvas_init_ok")

            self.build_text_wave_items(self.text_message)
            self.animate_text_wave()
            self.root.update_idletasks()
            self.root.update()
        except Exception as exc:
            self.log(f"Loading UI disabled: {exc}")
            self.root = None

    def alive(self) -> bool:
        if self.root is None:
            return False
        try:
            return bool(self.root.winfo_exists())
        except Exception:
            return False

    def build_text_wave_items(self, message: str) -> None:
        if self.loading_text_canvas is None:
            return
        self.loading_text_canvas.delete("all")
        self.loading_text_items = []
        x = 16
        for char in message:
            item = self.loading_text_canvas.create_text(
                x,
                18,
                text=char,
                fill="#FF6FAE",
                font=("Segoe UI", 16, "bold"),
                anchor="w",
            )
            self.loading_text_items.append(item)
            x += 10 if char != " " else 8

    def animate_text_wave(self) -> None:
        if self.loading_text_canvas is None or not self.loading_text_items:
            return
        if not self.alive():
            return
        base_y = 18
        non_space_indices = [i for i, char in enumerate(self.text_message) if char != " "]
        if not non_space_indices:
            return
        active = non_space_indices[self.text_wave_index % len(non_space_indices)]
        for idx, item in enumerate(self.loading_text_items):
            lift = 0.0
            if idx == active:
                lift = 6.0
            elif idx == active - 1 or idx == active + 1:
                lift = 2.0
            y = base_y - lift
            coords = self.loading_text_canvas.coords(item)
            if len(coords) >= 2:
                self.loading_text_canvas.coords(item, coords[0], y)
        self.text_wave_index += 1
        if self.root is not None:
            self.text_wave_job = self.root.after(95, self.animate_text_wave)

    def animate_tick(self) -> None:
        if self.loading_image_label is None:
            return
        if not self.alive():
            return
        name = str(self.anim_state["name"])
        frames = self.anim_frames.get(name, [])
        if not frames:
            return
        if name == "digest":
            idx = min(int(self.anim_state["idx"]), len(frames) - 1)
        else:
            idx = int(self.anim_state["idx"]) % len(frames)
        self.loading_image_label.configure(image=frames[idx])
        self.loading_image_label.image = frames[idx]
        self.anim_state["idx"] = int(self.anim_state["idx"]) + 1
        if self.root is not None:
            self.frame_job = self.root.after(70, self.animate_tick)

    def set_anim(self, name: str) -> None:
        if self.loading_mode != "gif" or self.root is None:
            return
        if self.frame_job is not None:
            try:
                self.root.after_cancel(self.frame_job)
            except Exception:
                pass
        self.anim_state["name"] = name
        self.anim_state["idx"] = 0
        self.animate_tick()

    def start_phase_loop(self) -> None:
        if self.loading_mode != "gif" or self.root is None:
            return
        if not self.anim_state.get("loop", True):
            return
        phases = [("idle", 3000), ("suck", 2000), ("digest", 700), ("dance", 3000)]

        def step(index: int) -> None:
            if not self.alive() or not self.anim_state.get("loop", True):
                return
            phase_name, duration = phases[index % len(phases)]
            self.log(f"loader_phase={phase_name}")
            self.set_anim(phase_name)
            if self.root is not None:
                self.phase_job = self.root.after(duration, lambda: step(index + 1))

        step(0)

    def stop_phase_loop(self) -> None:
        self.anim_state["loop"] = False
        root_ref = self.root
        if root_ref is None:
            self.phase_job = None
            self.frame_job = None
            self.text_wave_job = None
            return
        for attr in ("phase_job", "frame_job", "text_wave_job"):
            job = getattr(self, attr)
            if job is None:
                continue
            try:
                root_ref.after_cancel(job)
            except Exception:
                pass
            setattr(self, attr, None)

    def destroy(self) -> None:
        if self.loader_closing:
            return
        self.loader_closing = True
        self.stop_phase_loop()
        root_ref = self.root
        self.root = None
        if root_ref is None:
            self.log("kirby_loader_end")
            return
        try:
            if root_ref.winfo_exists():
                root_ref.destroy()
        except Exception:
            pass
        self.log("kirby_loader_end")

    def final_dance_then_close(self) -> None:
        if not self.alive():
            return
        self.log("loader_final_dance_start")
        try:
            self.set_anim("dance")
        except Exception:
            self.destroy()
            return

        try:
            if self.root is not None:
                self.root.after(2000, self.destroy)
        except Exception:
            self.destroy()

    def set_loading(self, message: str) -> None:
        self.log(message)
        if self.root is not None and self.loading_text is not None:
            self.loading_text.set(self.text_message)
            self.pump_once()

    def set_progress(self, step_label: str, percent: int | None = None, indeterminate: bool = False) -> None:
        self.log(f"loader_step={step_label} percent={percent if percent is not None else 'indeterminate'}")
        if self.root is None:
            return
        if self.loading_step_text is not None:
            self.loading_step_text.set(f"Step: {step_label}")
        if self.loading_percent_text is not None:
            if percent is None:
                self.loading_percent_text.set("...")
            else:
                clipped = max(0, min(100, int(percent)))
                self.loading_percent_text.set(f"{clipped}%")
        if self.loading_progress_canvas is not None and self.loading_progress_fill is not None:
            try:
                if percent is None:
                    if indeterminate:
                        self.loading_progress_value = (self.loading_progress_value + 4) % 100
                    progress_value = self.loading_progress_value
                else:
                    progress_value = max(0, min(100, int(percent)))
                    self.loading_progress_value = progress_value
                x2 = 3 + int((355 * progress_value) / 100)
                if x2 < 3:
                    x2 = 3
                self.loading_progress_canvas.coords(self.loading_progress_fill, 3, 3, x2, 13)
                self.log(f"loader_bar_update percent={progress_value}")
            except Exception:
                pass
        self.pump_once()

    def lift_focus(self) -> None:
        if self.root is None:
            return
        try:
            self.root.lift()
            self.root.focus_force()
            self.pump_once()
        except Exception:
            pass

    def pump_once(self) -> None:
        if self.root is None:
            return
        try:
            self.root.update_idletasks()
            self.root.update()
        except Exception:
            pass

    def pump_until_closed(self, sleep_seconds: float = 0.03) -> None:
        while self.root is not None:
            try:
                if not self.root.winfo_exists():
                    break
            except Exception:
                break
            try:
                self.root.update_idletasks()
                self.root.update()
            except Exception:
                break
            time.sleep(sleep_seconds)
