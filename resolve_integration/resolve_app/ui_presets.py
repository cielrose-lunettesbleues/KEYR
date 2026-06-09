from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

TRANSFORM_GROUPS = ("single", "gameplay", "camera")
TRANSFORM_KEYS = ("zoom_x", "zoom_y", "pan", "tilt", "crop_top", "crop_bottom", "crop_left", "crop_right")


def slider_bounds(prop_key: str) -> tuple[float, float, float]:
    if prop_key.startswith("zoom"):
        return 0.1, 8.0, 0.01
    if prop_key in ("pan", "tilt"):
        return -1.0, 1.0, 0.01
    return 0.0, 1.0, 0.01


def coerce_layers_count(raw_value: Any, mode: str) -> int:
    try:
        return max(1, min(4, int(float(str(raw_value).strip()))))
    except Exception:
        return 2 if mode == "fixed_split" else 1


def coerce_float_field(raw_value: Any, default: float = 0.0) -> float:
    try:
        return float(str(raw_value).strip())
    except Exception:
        return default


def editor_values_from_preset(
    preset: dict[str, Any],
    keys: tuple[str, ...] = TRANSFORM_KEYS,
    groups: tuple[str, ...] = TRANSFORM_GROUPS,
) -> dict[str, Any]:
    mode = str(preset.get("mode", "single"))
    default_layers = 2 if mode == "fixed_split" else 1
    values: dict[str, Any] = {
        "mode": mode,
        "mode_label": f"mode: {mode}",
        "safe_padding": str(preset.get("safe_padding", 0.04)),
        "layers_count": str(int(preset.get("layers_count", default_layers))),
        "fields": {},
    }
    fields: dict[str, float] = values["fields"]
    for group in groups:
        section = dict(preset.get(group, {}))
        for key in keys:
            fields[f"{group}.{key}"] = coerce_float_field(section.get(key, 0.0), 0.0)
    return values


def preset_from_editor_values(
    base: dict[str, Any],
    mode_value: Any,
    layers_count_value: Any,
    safe_padding_value: Any,
    field_values: dict[str, Any],
    keys: tuple[str, ...] = TRANSFORM_KEYS,
    groups: tuple[str, ...] = TRANSFORM_GROUPS,
) -> dict[str, Any]:
    out = dict(base)
    mode = str(mode_value).strip() or "single"
    out["mode"] = mode
    out["layers_count"] = coerce_layers_count(layers_count_value, mode)
    for group in groups:
        out[group] = {}
        for key in keys:
            raw = field_values.get(f"{group}.{key}", "")
            out[group][key] = coerce_float_field(raw, 0.0)
    out["safe_padding"] = coerce_float_field(safe_padding_value, 0.04)
    return out


def subtitle_preset_from_editor_values(
    values: dict[str, Any],
    subtitle_template_auto_label: str,
    coerce_float: Any,
    coerce_int: Any,
) -> dict[str, Any] | None:
    name = str(values.get("name", "")).strip()
    if not name:
        return None
    return {
        "name": name,
        "font": str(values.get("font", "")).strip() or "Arial",
        "font_style": str(values.get("font_style", "")).strip() or "Bold",
        "font_size": coerce_float(values.get("font_size"), 0.085, 0.01, 0.5),
        "color": str(values.get("color", "")).strip() or "#FFFFFF",
        "position_x": coerce_float(values.get("position_x"), 0.5, 0.0, 1.0),
        "position_y": coerce_float(values.get("position_y"), 0.82, 0.0, 1.0),
        "words_per_subtitle": coerce_int(values.get("words_per_subtitle"), 3, 1, 8),
        "max_chars_per_line": coerce_int(values.get("max_chars_per_line"), 24, 8, 80),
        "subtitle_template_name": str(values.get("subtitle_template_name", "")).strip() or subtitle_template_auto_label,
        "subtitle_offset_ms": coerce_int(values.get("subtitle_offset_ms"), -500, -5000, 5000),
    }


def delete_subtitle_preset_data(
    subtitle_presets: dict[str, Any],
    profiles: dict[str, Any],
    name: str,
) -> dict[str, Any]:
    target = str(name).strip()
    if target not in subtitle_presets:
        return {"status": "missing", "replacement": "", "subtitle_presets": dict(subtitle_presets), "profiles": dict(profiles)}
    if len(subtitle_presets) <= 1:
        return {"status": "last", "replacement": "", "subtitle_presets": dict(subtitle_presets), "profiles": dict(profiles)}

    next_subtitle_presets = dict(subtitle_presets)
    del next_subtitle_presets[target]
    replacement = next(iter(next_subtitle_presets.keys()))

    next_profiles: dict[str, Any] = {}
    for profile_name, profile_data in profiles.items():
        if isinstance(profile_data, dict):
            next_profile_data = dict(profile_data)
            if next_profile_data.get("active_subtitle_preset") == target:
                next_profile_data["active_subtitle_preset"] = replacement
            next_profiles[profile_name] = next_profile_data
        else:
            next_profiles[profile_name] = profile_data

    return {
        "status": "deleted",
        "replacement": replacement,
        "subtitle_presets": next_subtitle_presets,
        "profiles": next_profiles,
    }


def open_subtitle_preset_editor(
    tk: Any,
    messagebox: Any,
    parent: Any,
    colors: dict[str, str],
    ui_button: Callable[..., Any],
    sid: str,
    base: dict[str, Any],
    subtitle_template_options: list[str],
    subtitle_template_auto_label: str,
    subtitle_presets: dict[str, Any],
    presets_data: dict[str, Any],
    profiles: dict[str, Any],
    profile_var: Any,
    subtitle_preset_var: Any,
    subtitle_template_var: Any,
    subtitle_offset_ms_var: Any,
    refresh_subtitle_preset_menu: Callable[[], None],
    load_subtitle_preset: Callable[[str], None],
    save_presets: Callable[[Path, dict[str, Any]], None],
    repo_root: Callable[[], Path],
    set_status: Callable[..., None],
    coerce_float: Callable[..., float],
    coerce_int: Callable[..., int],
) -> None:
    top = tk.Toplevel(parent)
    top.title("Éditeur preset sous-titres")
    top.geometry("620x520")
    top.configure(bg=colors["panel_alt"])
    top.transient(parent)

    fields = tk.Frame(top, bg=colors["panel_alt"])
    fields.pack(fill="both", expand=True, padx=10, pady=10)

    name_var = tk.StringVar(value=sid)
    font_var = tk.StringVar(value=str(base.get("font", "Arial")))
    font_style_var = tk.StringVar(value=str(base.get("font_style", "Bold")))
    font_size_var = tk.StringVar(value=str(base.get("font_size", 0.085)))
    color_var = tk.StringVar(value=str(base.get("color", "#FFFFFF")))
    pos_x_var = tk.StringVar(value=str(base.get("position_x", 0.5)))
    pos_y_var = tk.StringVar(value=str(base.get("position_y", 0.82)))
    words_var = tk.StringVar(value=str(base.get("words_per_subtitle", 3)))
    chars_var = tk.StringVar(value=str(base.get("max_chars_per_line", 24)))
    template_var = tk.StringVar(value=str(base.get("subtitle_template_name", subtitle_template_var.get() or subtitle_template_auto_label)))
    offset_var = tk.StringVar(value=str(base.get("subtitle_offset_ms", subtitle_offset_ms_var.get() or -500)))

    rows = [
        ("Nom", name_var, "entry"),
        ("Police", font_var, "entry"),
        ("Style police", font_style_var, "entry"),
        ("Taille", font_size_var, "entry"),
        ("Couleur #RRGGBB", color_var, "entry"),
        ("Position X (0..1)", pos_x_var, "entry"),
        ("Position Y (0..1)", pos_y_var, "entry"),
        ("Mots par sous-titre", words_var, "entry"),
        ("Caractères par ligne", chars_var, "entry"),
        ("Modèle Text+", template_var, "menu"),
        ("Décalage ms", offset_var, "entry"),
    ]
    for idx, (label, var, kind) in enumerate(rows):
        tk.Label(fields, text=f"♡ {label}", bg=colors["panel_alt"], fg=colors["ink"], font=("Tahoma", 9, "bold")).grid(row=idx, column=0, sticky="w", padx=6, pady=5)
        if kind == "menu":
            opt = tk.OptionMenu(fields, var, *subtitle_template_options)
            opt.config(bg=colors["sun"], fg=colors["ink"], bd=2, relief="raised", activebackground=colors["sun_soft"])
            opt.grid(row=idx, column=1, sticky="w", padx=6, pady=5)
        else:
            tk.Entry(fields, textvariable=var, width=34, bd=3, relief="sunken", bg="#FFFFFF", fg=colors["ink"], insertbackground=colors["accent"]).grid(row=idx, column=1, sticky="w", padx=6, pady=5)

    hint = tk.Label(top, text="Position: X=0 gauche, 0.5 centre, 1 droite | Y=0 bas, 1 haut selon Fusion/Resolve.", bg=colors["panel_alt"], fg=colors["ink"], anchor="w")
    hint.pack(fill="x", padx=10, pady=(0, 6))

    def build_preset() -> dict[str, Any] | None:
        preset = subtitle_preset_from_editor_values(
            {
                "name": name_var.get(),
                "font": font_var.get(),
                "font_style": font_style_var.get(),
                "font_size": font_size_var.get(),
                "color": color_var.get(),
                "position_x": pos_x_var.get(),
                "position_y": pos_y_var.get(),
                "words_per_subtitle": words_var.get(),
                "max_chars_per_line": chars_var.get(),
                "subtitle_template_name": template_var.get(),
                "subtitle_offset_ms": offset_var.get(),
            },
            subtitle_template_auto_label,
            coerce_float,
            coerce_int,
        )
        if preset is None:
            messagebox.showerror("Short Editor", "Nom de preset sous-titres vide")
            return None
        return preset

    def save_subtitle_preset() -> None:
        preset = build_preset()
        if preset is None:
            return
        name = str(preset["name"])
        subtitle_presets[name] = preset
        presets_data["subtitle_presets"] = subtitle_presets
        profiles.setdefault(profile_var.get().strip(), {})["active_subtitle_preset"] = name
        save_presets(repo_root(), presets_data)
        subtitle_preset_var.set(name)
        subtitle_template_var.set(str(preset.get("subtitle_template_name", subtitle_template_auto_label)))
        subtitle_offset_ms_var.set(str(preset.get("subtitle_offset_ms", -500)))
        refresh_subtitle_preset_menu()
        set_status(f"Preset sous-titres enregistré: {name}", warnings=[])
        messagebox.showinfo("Short Editor", f"Preset sous-titres enregistré: {name}")

    def delete_subtitle_preset() -> None:
        name = name_var.get().strip()
        delete_result = delete_subtitle_preset_data(subtitle_presets, profiles, name)
        if delete_result.get("status") == "missing":
            return
        if delete_result.get("status") == "last":
            messagebox.showwarning("Short Editor", "Impossible de supprimer le dernier preset sous-titres.")
            return
        if not messagebox.askyesno("Supprimer", f"Supprimer le preset sous-titres '{name}' ?"):
            return
        replacement = str(delete_result.get("replacement", ""))
        subtitle_presets.clear()
        subtitle_presets.update(dict(delete_result.get("subtitle_presets", {})))
        profiles.clear()
        profiles.update(dict(delete_result.get("profiles", {})))
        presets_data["subtitle_presets"] = subtitle_presets
        save_presets(repo_root(), presets_data)
        subtitle_preset_var.set(replacement)
        load_subtitle_preset(replacement)
        refresh_subtitle_preset_menu()
        top.destroy()
        set_status(f"Preset sous-titres supprimé: {name}", warnings=[])

    controls = tk.Frame(top, bg=colors["panel_alt"])
    controls.pack(fill="x", padx=10, pady=(0, 10))
    ui_button(controls, "Enregistrer", save_subtitle_preset, primary=True).pack(side="right", padx=4)
    ui_button(controls, "Supprimer", delete_subtitle_preset, primary=False).pack(side="right", padx=4)
    ui_button(controls, "Fermer", top.destroy, primary=False).pack(side="right", padx=4)
