"""UI pro plynulou rychlost a vítr podle rychlosti (volá se z app.py).

Barvy se čtou z modulu app při každém volání (tmavý motiv je přepíná
a App._rebuild_ui staví widgety znovu), stav je v App / ControlConfig.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .vitr import pct_to_level


def _ui():
    from . import app as A
    return A


# ------------------------------------------------------------------ Nastavení → Řízení
def build_control_section(app, p) -> None:
    A = _ui()
    c = app.cfg.control
    box = tk.Frame(p, bg=A.BG)
    box.pack(fill="x", pady=(12, 0))
    app._lbl(box, "Výstup", fg=A.TEXT, font=app.fonts.body_b, anchor="w").pack(fill="x", pady=(0, 4))
    app.out_mode_var = tk.StringVar(value=c.output_mode if c.output_mode in ("steps", "smooth") else "steps")
    r = tk.Frame(box, bg=A.BG)
    r.pack(fill="x")
    ttk.Radiobutton(r, text="Stupně", variable=app.out_mode_var, value="steps",
                    command=app.on_apply).pack(side="left")
    ttk.Radiobutton(r, text="Plynulá rychlost", variable=app.out_mode_var, value="smooth",
                    command=app.on_apply).pack(side="left", padx=10)

    g = tk.Frame(box, bg=A.BG)
    g.pack(fill="x", pady=(4, 0))
    rows = [
        ("Rychlost na 1. prahu", c.smooth_min_pct, "%", "e_smooth_min"),
        ("Pokles nejvýš", c.smooth_down_pct_s, "%/s", "e_smooth_rate"),
        ("Vítr: plná rychlost při", c.wind_full_kmh, "km/h", "e_wind_full"),
    ]
    for i, (label, val, unit, attr) in enumerate(rows):
        ttk.Label(g, text=label).grid(row=i, column=0, sticky="w", pady=2)
        e = app._entry(g, val)
        e.grid(row=i, column=1, sticky="w", padx=10, pady=2)
        app._lbl(g, unit).grid(row=i, column=2, sticky="w")
        setattr(app, attr, e)
    app.wind_floor_var = tk.BooleanVar(value=bool(c.wind_floor))
    ttk.Checkbutton(box, text="Vítr: minimum podle výkonu a tepu (pomalé stoupání do kopce)",
                    variable=app.wind_floor_var, command=app.on_apply).pack(anchor="w", pady=(4, 0))
    app._lbl(box, "Plynulá rychlost: od 1. do posledního prahu roste lineárně do 100 %. "
                  "Vítr: pod 5 km/h vypnuto, rychlost jízdy posílá trenažér (FE-C), např. z Rouvy. "
                  "Ventilátor bez rychlosti v % dostane nejbližší stupeň.",
             anchor="w", justify="left", wraplength=int(440 * app.px)).pack(fill="x", pady=(4, 0))


def read_control_section(app, c) -> None:
    """Přečte pole do ControlConfig; ValueError při nesmyslu."""
    if not hasattr(app, "out_mode_var"):
        return
    mn = int(float(app.e_smooth_min.get().replace(",", ".")))
    rate = float(app.e_smooth_rate.get().replace(",", "."))
    full = float(app.e_wind_full.get().replace(",", "."))
    if not (0 <= mn <= 100 and rate > 0 and 10 <= full <= 120):
        raise ValueError("Rychlost 0–100 %, pokles nad 0 %/s, vítr 10–120 km/h.")
    c.smooth_min_pct, c.smooth_down_pct_s, c.wind_full_kmh = mn, rate, full
    c.output_mode = app.out_mode_var.get()
    c.wind_floor = bool(app.wind_floor_var.get())


# ------------------------------------------------------------------ okno jízdy
def fan_fraction(app, desired: int) -> float:
    """Výška pásu ventilátoru v grafu (0..1)."""
    ctrl = app.controller
    if app.auto_var.get() and ctrl.pct is not None:
        return ctrl.pct / 100.0
    return desired / max(1, app.cfg.fan.max_level)


def update_fan_tile(app, desired: int) -> bool:
    """Dlaždice ventilátoru při výstupu v %. False = klasické stupně (kreslí app)."""
    ctrl = app.controller
    if not app.auto_var.get() or ctrl.pct is None:
        app._last_pct_bar = None
        return False
    A = _ui()
    n = max(1, app.cfg.fan.max_level)
    pct = ctrl.pct
    stepped = app.fan_worker.percent_capable is False
    app.t_fan["big"].configure(text="Vyp" if pct <= 0 else f"{pct:.0f} %")
    sub = []
    if app.backend.state != "monitoring":
        sub.append("čeká na měření")
    else:
        if app.cfg.control.source_mode == "wind":
            v = ctrl.speed_smoothed
            sub.append("bez rychlosti z trenažéru" if v is None else f"vítr {v:.0f} km/h")
            if ctrl.reason and not ctrl.reason.startswith(("vítr", "chybí rychlost")):
                sub.append(ctrl.reason)
        else:
            sub.append(ctrl.reason)
        if stepped:
            lv = pct_to_level(pct, n)
            sub.append("vyp" if lv == 0 else f"stupeň {lv}")
        act = app.fan_worker.actual_pct
        if not stepped and act is not None and abs(act - pct) > 10:
            sub.append(f"ventilátor zatím na {act:.0f} %")
    app.t_fan["sub"].configure(text=" · ".join(sub))
    if stepped:
        app._last_pct_bar = None
        app._draw_bars(pct_to_level(pct, n))
    else:
        _draw_pct_bar(app, pct, A)
    return True


def _draw_pct_bar(app, pct: float, A) -> None:
    key = (round(pct), A.FAN)
    if getattr(app, "_last_pct_bar", None) == key:
        return
    app._last_pct_bar = key
    app._last_bars = None
    c = app.t_fan["bars"]
    c.delete("all")
    w = int(c.cget("width"))
    hmax = int(28 * app.px)
    bw = max(4, int(w * 0.4))
    c.create_rectangle(0, 2, bw, hmax + 2, outline="", fill=A.BORDER)
    h = int(hmax * max(0.0, min(100.0, pct)) / 100)
    if h > 0:
        c.create_rectangle(0, hmax - h + 2, bw, hmax + 2, outline="", fill=A.FAN)
