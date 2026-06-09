from __future__ import annotations

from pathlib import Path
from typing import Any, Callable


COMPACT_GEOMETRY = "1180x860"
EXPANDED_GEOMETRY = "1180x1020"
TRANSFORM_KEYS = ("zoom_x", "zoom_y", "pan", "tilt", "crop_top", "crop_bottom", "crop_left", "crop_right")

COLORS = {
    "bg": "#6FD8FF",
    "sky": "#6FD8FF",
    "cloud": "#FFFFFF",
    "panel": "#D9C7FF",
    "panel_alt": "#FFF7FF",
    "accent": "#FF7EDB",
    "accent_soft": "#FFB7E8",
    "ink": "#24304F",
    "sun": "#FFF4B2",
    "sun_soft": "#FFFBE0",
    "mint": "#CFFFE2",
    "aero": "#BDF4FF",
    "line": "#7E69D9",
    "glow": "#FFFFFF",
}


def default_profile_id(profiles: dict[str, Any]) -> str:
    return "valo" if "valo" in profiles else next(iter(profiles.keys()), "valo")


def active_preset_id(profiles: dict[str, Any], presets: dict[str, Any], profile_id: str) -> str:
    profile_info = profiles.get(profile_id, {}) if isinstance(profiles, dict) else {}
    active = str(profile_info.get("active_preset", "")).strip() if isinstance(profile_info, dict) else ""
    if active in presets:
        return active
    return next(iter(presets.keys()), "")


def active_subtitle_preset_id(
    profiles: dict[str, Any],
    subtitle_presets: dict[str, Any],
    profile_id: str,
    default_subtitle_preset_id: str,
) -> str:
    profile_info = profiles.get(profile_id, {}) if isinstance(profiles, dict) else {}
    active = str(profile_info.get("active_subtitle_preset", "")).strip() if isinstance(profile_info, dict) else ""
    if active in subtitle_presets:
        return active
    return next(iter(subtitle_presets.keys()), default_subtitle_preset_id)


def initial_state(
    repo_root: Path,
    profiles: dict[str, Any],
    presets: dict[str, Any],
    subtitle_presets: dict[str, Any],
    render_preset: str,
    subtitle_template_auto_label: str,
    default_subtitle_preset_id: str,
) -> dict[str, Any]:
    profile_id = default_profile_id(profiles)
    return {
        "output_dir": "",
        "render_preset": render_preset,
        "profile": profile_id,
        "preset_id": active_preset_id(profiles, presets, profile_id),
        "subtitle_preset_id": active_subtitle_preset_id(profiles, subtitle_presets, profile_id, default_subtitle_preset_id),
        "query": "",
        "render_master": False,
        "subtitle_template_name": subtitle_template_auto_label,
        "subtitle_offset_ms": "-500",
    }


def noop_sound() -> None:
    return


def create_ui_button(
    tk: Any,
    parent: Any,
    text: str,
    command: Callable[[], Any],
    colors: dict[str, str],
    play_click_sound: Callable[[], None] = noop_sound,
    play_hover_sound: Callable[[], None] = noop_sound,
    primary: bool = False,
) -> Any:
    base_bg = colors["accent"] if primary else colors["sun"]
    hover_bg = "#FFFFFF" if primary else colors["mint"]

    def run_command() -> Any:
        play_click_sound()
        return command()

    btn = tk.Button(
        parent,
        text=f"✦ {text} ✦" if primary else text,
        command=run_command,
        bg=base_bg,
        fg="#FFFFFF" if primary else colors["ink"],
        activebackground=colors["accent_soft"] if primary else colors["sun_soft"],
        activeforeground=colors["ink"],
        bd=4,
        relief="raised",
        padx=12,
        pady=5,
        cursor="hand2",
        font=("Verdana", 9, "bold"),
    )

    def enter(_event: Any) -> None:
        play_hover_sound()
        btn.configure(bg=hover_bg, relief="ridge")

    def leave(_event: Any) -> None:
        btn.configure(bg=base_bg, relief="raised")

    def press(_event: Any) -> None:
        btn.configure(relief="sunken", padx=14)

    def release(_event: Any) -> None:
        btn.configure(relief="ridge", padx=12)

    btn.bind("<Enter>", enter)
    btn.bind("<Leave>", leave)
    btn.bind("<ButtonPress-1>", press, add="+")
    btn.bind("<ButtonRelease-1>", release, add="+")
    return btn


def show_main_tab(name: str, batch_tab: Any, actions_tab: Any, tab_buttons: dict[str, Any], colors: dict[str, str]) -> None:
    for frame in (batch_tab, actions_tab):
        frame.grid_forget()
    active_frame = batch_tab if name == "batch" else actions_tab
    active_frame.grid(row=0, column=0, sticky="nw")
    for key, button in tab_buttons.items():
        active = key == name
        button.configure(
            bg=colors["accent_soft"] if active else colors["sun_soft"],
            fg=colors["ink"],
            relief="sunken" if active else "ridge",
        )


def create_dream_background(
    tk: Any,
    root: Any,
    colors: dict[str, str],
    log: Callable[[str], None],
    play_click_sound: Callable[[], None] = noop_sound,
) -> tuple[Any, dict[str, Any]]:
    dream_bg = tk.Canvas(root, bg=colors["sky"], highlightthickness=0, bd=0)
    dream_bg.place(x=0, y=0, relwidth=1, relheight=1)
    try:
        dream_bg.tk.call("lower", dream_bg._w)
    except Exception as exc:
        log(f"dream_bg_lower_failed: {exc}")

    bg_state: dict[str, Any] = {"tick": 0, "mouse_x": 0, "mouse_y": 0, "sparkles": []}

    def draw_dream_background() -> None:
        try:
            w = max(1, int(root.winfo_width()))
            h = max(1, int(root.winfo_height()))
            t = int(bg_state.get("tick", 0))
            mx = float(bg_state.get("mouse_x", 0))
            my = float(bg_state.get("mouse_y", 0))
            px = (mx - w / 2) / max(1, w)
            py = (my - h / 2) / max(1, h)
            dream_bg.delete("all")

            dream_bg.create_rectangle(0, 0, w, h, fill=colors["sky"], outline="")
            dream_bg.create_oval(-160 + px * 28, -120 + py * 16, 360 + px * 28, 260 + py * 16, fill="#FFFFFF", outline="#BDF4FF")
            dream_bg.create_oval(w - 320 + px * -24, 40 + py * 18, w + 220 + px * -24, 460 + py * 18, fill="#CFFFE2", outline="#7EE8B4")
            dream_bg.create_oval(w / 2 - 260, h - 220, w / 2 + 260, h + 120, fill="#FFB7E8", outline="#FF7EDB")

            for i in range(7):
                base_x = (i * 210 - (t * (1 + i % 2)) % (w + 240)) - 120 + px * (12 + i)
                base_y = 64 + (i % 3) * 52 + py * (6 + i)
                for j, radius in enumerate((38, 54, 44, 32)):
                    x = base_x + j * 42
                    dream_bg.create_oval(x, base_y - radius / 2, x + radius * 2, base_y + radius, fill="#FFFFFF", outline="#D9C7FF")

            glyphs = ["✦", "✧", "★", "♡", "◇", "☁"]
            for i in range(42):
                x = (i * 83 + t * (1 + i % 4)) % (w + 80) - 40 + px * (4 + i % 9)
                y = (i * 47 + (t // 2) * (1 + i % 3)) % (h + 80) - 40 + py * (3 + i % 7)
                color = ["#FFFFFF", "#FFF4B2", "#FF7EDB", "#B99CFF", "#5EE8A5"][i % 5]
                font_size = 9 + (i % 5)
                dream_bg.create_text(x, y, text=glyphs[i % len(glyphs)], fill=color, font=("Verdana", font_size, "bold"))

            for i in range(38):
                x = (i * 131 + t * 7) % w
                y = (i * 71 + t * 5) % h
                dream_bg.create_rectangle(x, y, x + 1, y + 1, fill="#FFFFFF", outline="")

            next_sparkles = []
            for sparkle in list(bg_state.get("sparkles", [])):
                x, y, life, glyph = sparkle
                if life <= 0:
                    continue
                dream_bg.create_text(x, y - (10 - life), text=glyph, fill="#FFFFFF", font=("Verdana", 12 + life % 5, "bold"))
                next_sparkles.append((x, y, life - 1, glyph))
            bg_state["sparkles"] = next_sparkles
            bg_state["tick"] = t + 1
            root.after(90, draw_dream_background)
        except Exception:
            pass

    def remember_mouse(event: Any) -> None:
        bg_state["mouse_x"] = getattr(event, "x", 0)
        bg_state["mouse_y"] = getattr(event, "y", 0)

    def spawn_click_sparkles(event: Any) -> None:
        play_click_sound()
        x = getattr(event, "x", 0)
        y = getattr(event, "y", 0)
        sparkles = list(bg_state.get("sparkles", []))
        for glyph in ("✦", "♡", "✧", "★"):
            sparkles.append((x, y, 10, glyph))
        bg_state["sparkles"] = sparkles[-48:]

    root.bind("<Motion>", remember_mouse)
    root.bind("<Button-1>", spawn_click_sparkles, add="+")
    root.after(120, draw_dream_background)
    return dream_bg, bg_state


def start_companion_pulse(root: Any, companion_orb: Any, colors: dict[str, str]) -> None:
    def pulse_companion(step: int = 0) -> None:
        try:
            companion_orb.delete("all")
            radius = 13 + (step % 8 if step % 16 < 8 else 16 - step % 16)
            companion_orb.create_oval(22 - radius, 22 - radius, 22 + radius, 22 + radius, fill="#FFFFFF", outline=colors["accent"], width=2)
            companion_orb.create_oval(14, 10, 30, 28, fill=colors["aero"], outline="")
            companion_orb.create_text(22, 22, text="♡", fill=colors["accent"], font=("Verdana", 13, "bold"))
            companion_orb.create_text(36, 9, text="✦", fill=colors["sun"], font=("Verdana", 10, "bold"))
            root.after(160, lambda: pulse_companion(step + 1))
        except Exception:
            pass

    root.after(180, pulse_companion)


def create_header_and_tabs(tk: Any, root: Any, colors: dict[str, str]) -> dict[str, Any]:
    header = tk.Frame(root, bg=colors["accent_soft"], bd=4, relief="ridge")
    header.grid(row=0, column=0, columnspan=3, sticky="we", padx=10, pady=(10, 8))
    tk.Label(
        header,
        text="✧ Kirby Ate your VOD ! ✧",
        bg=colors["accent_soft"],
        fg=colors["ink"],
        font=("Verdana", 15, "bold"),
        padx=10,
        pady=8,
    ).pack(side="left")
    keyv_label = tk.Label(
        header,
        text="● EN LIGNE  MSN ✦ XP ✦ KEYV",
        bg=colors["sun_soft"],
        fg="#2C8A55",
        font=("Tahoma", 9, "bold"),
        padx=10,
        pady=4,
    )
    keyv_label.pack(side="right")
    keyv_label.bind("<Enter>", lambda _event: keyv_label.configure(text="Kirby Eats your VOD"))
    keyv_label.bind("<Leave>", lambda _event: keyv_label.configure(text="● EN LIGNE  MSN ✦ XP ✦ KEYV"))

    tabs_bar = tk.Frame(root, bg=colors["sky"])
    tabs_bar.grid(row=1, column=0, columnspan=3, sticky="w", padx=10, pady=(0, 0))
    tabs_body = tk.Frame(root, bg=colors["sky"])
    tabs_body.grid(row=2, column=0, columnspan=3, sticky="nw", padx=10, pady=(0, 0))

    batch_tab = tk.Frame(tabs_body, bg=colors["sky"])
    actions_tab = tk.Frame(tabs_body, bg=colors["sky"])
    tab_buttons: dict[str, Any] = {}

    def show_tab(name: str) -> None:
        show_main_tab(name, batch_tab, actions_tab, tab_buttons, colors)

    tab_buttons["batch"] = tk.Button(
        tabs_bar,
        text="☁ Batch génération ✧",
        command=lambda: show_tab("batch"),
        bg=colors["accent_soft"],
        fg=colors["ink"],
        activebackground=colors["accent_soft"],
        activeforeground=colors["ink"],
        bd=4,
        relief="sunken",
        padx=12,
        pady=5,
        cursor="hand2",
        font=("Verdana", 10, "bold"),
    )
    tab_buttons["batch"].pack(side="left", padx=(0, 4), pady=(0, 6))
    tab_buttons["actions"] = tk.Button(
        tabs_bar,
        text="♡ Actions timeline ★",
        command=lambda: show_tab("actions"),
        bg=colors["sun_soft"],
        fg=colors["ink"],
        activebackground=colors["sun_soft"],
        activeforeground=colors["ink"],
        bd=4,
        relief="ridge",
        padx=12,
        pady=5,
        cursor="hand2",
        font=("Verdana", 10, "bold"),
    )
    tab_buttons["actions"].pack(side="left", padx=(0, 4), pady=(0, 6))

    companion = tk.Frame(tabs_bar, bg=colors["panel_alt"], bd=3, relief="ridge")
    companion.pack(side="right", padx=(8, 0), pady=(0, 6))
    companion_orb = tk.Canvas(companion, width=44, height=44, bg=colors["panel_alt"], highlightthickness=0, bd=0)
    companion_orb.pack(side="left", padx=(6, 4), pady=4)
    companion_text = tk.Label(
        companion,
        text="ange digital\nhumeur: rêveuse",
        bg=colors["panel_alt"],
        fg=colors["ink"],
        font=("Tahoma", 8, "bold"),
        justify="left",
    )
    companion_text.pack(side="left", padx=(0, 8), pady=4)
    start_companion_pulse(root, companion_orb, colors)

    tabs_body.columnconfigure(0, weight=1)
    tabs_body.rowconfigure(0, weight=0)
    batch_tab.columnconfigure(1, weight=1)

    return {
        "header": header,
        "tabs_bar": tabs_bar,
        "tabs_body": tabs_body,
        "batch_tab": batch_tab,
        "actions_tab": actions_tab,
        "tab_buttons": tab_buttons,
        "show_tab": show_tab,
        "companion_orb": companion_orb,
    }


def create_form_label(tk: Any, parent: Any, text: str, row: int, column: int, colors: dict[str, str]) -> Any:
    label = tk.Label(
        parent,
        text=f"♡ {text}",
        bg=colors["panel_alt"],
        fg=colors["ink"],
        font=("Tahoma", 9, "bold"),
        bd=1,
        relief="flat",
    )
    label.grid(row=row, column=column, sticky="w", padx=8, pady=6)
    return label


def create_text_entry(
    tk: Any,
    parent: Any,
    textvariable: Any,
    row: int,
    column: int,
    colors: dict[str, str],
    width: int = 80,
    sticky: str = "we",
) -> Any:
    entry = tk.Entry(
        parent,
        textvariable=textvariable,
        width=width,
        bd=3,
        relief="sunken",
        bg="#FFFFFF",
        fg=colors["ink"],
        insertbackground=colors["accent"],
        font=("Tahoma", 9),
    )
    entry.grid(row=row, column=column, padx=8, pady=6, sticky=sticky)
    return entry


def create_option_menu(
    tk: Any,
    parent: Any,
    variable: Any,
    values: list[Any],
    row: int,
    column: int,
    colors: dict[str, str],
    sticky: str = "w",
) -> Any:
    menu = tk.OptionMenu(parent, variable, *values)
    menu.config(bg=colors["sun"], fg=colors["ink"], bd=2, relief="raised", activebackground=colors["sun_soft"])
    menu.grid(row=row, column=column, padx=8, pady=6, sticky=sticky)
    return menu
