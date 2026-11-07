"""Lišta navrchu: malý proužek přes Rouvy a jiné aplikace.

Neopakuje výkon, tep ani rychlost (ty ukazuje Rouvy). Ukazuje stupeň
ventilátoru s důvodem, volitelně % max. tepu nebo tepovou zónu a upozornění
(pití, baterie, výpadek příjmu, ventilátor).

  * overlay_state(app) – jednoduchý stav z App, bez tkinteru (unit testy),
  * Overlay – okno (Toplevel bez rámečku); stav drží App a config, okno se
    po _rebuild_ui jen znovu postaví,
  * build_settings(app, parent) – volby v Nastavení → Vzhled.

Funkce z jiných větví (baterie, vítr) se čtou přes getattr, aby po sloučení
stačilo málo.
"""
from __future__ import annotations

import sys
import time
import tkinter as tk
from tkinter import ttk

from . import config as config_mod
from .i18n import _, N_

SECOND_OPTS = [("hr_pct", N_("% max. tepu")), ("zone", N_("Tepová zóna")), ("none", N_("Nic"))]
SIZES = [("mini", "Mini"), ("standard", "Standard")]
ALERT_SHOW_S = 20.0     # režim jen upozornění: jak dlouho je lišta vidět
TOPMOST_EVERY_S = 5.0   # Windows: některé hry topmost shazují
MARGIN = 20             # odsazení od rohu obrazovky
# Tepové zóny podle % max. tepu (5zónový model): Z1 od 50 %, Z2 60, Z3 70, Z4 80, Z5 90
ZONES = (50, 60, 70, 80, 90)


def hr_zone(hr: float | None, hr_max: float | None) -> int | None:
    if not hr or not hr_max:
        return None
    pct = hr / hr_max * 100
    z = sum(1 for lim in ZONES if pct >= lim)
    return max(1, z)


def short_reason(reason: str) -> str:
    """Krátký důvod z Controller.reason."""
    r = (reason or "").strip()
    if r.startswith(_("dofukování")):
        return r.replace(_("dofukování ještě"), _("dofukování"))
    return {_("tep drží stupeň"): _("tep drží"), _("žádná data ze senzorů"): _("bez dat"),
            _("čekám na data"): _("čeká na data")}.get(r, r)


def _level_name(level: int) -> str:
    return _("Vyp") if level == 0 else str(level)


def overlay_state(app, now: float | None = None) -> dict:
    """Stav lišty z App. Vrací dict: level, auto, level_text, reason, second, alerts."""
    ctrl = app.controller
    cfg = app.cfg
    backend = getattr(app, "backend", None)
    state = getattr(backend, "state", "idle")
    monitoring = state == "monitoring"
    auto = bool(app.auto_var.get())
    level = ctrl.level if auto else app.manual_level

    if not auto:
        level_text, reason = _("ručně {v}").format(v=_level_name(level)), ""
    else:
        level_text = _level_name(level)
        reason = short_reason(ctrl.reason) if monitoring else _("neměří se")
        wind = getattr(app, "wind_kmh", None)  # feature/vitr
        if monitoring and wind is not None and _("vítr") in reason:
            reason = _("vítr {wind:.0f} km/h").format(wind=wind)

    second = ""
    mode = getattr(cfg, "overlay_second", "hr_pct")
    hr, hr_max = ctrl.hr_now, cfg.control.hr_max
    if mode == "hr_pct" and hr and hr_max:
        second = f"{hr / hr_max * 100:.0f} % max"
    elif mode == "zone":
        z = hr_zone(hr, hr_max)
        second = _("zóna {z}").format(z=z) if z else ""

    alerts: list[str] = []
    drink = getattr(app, "drink", None)
    rem = getattr(drink, "current", None)
    if rem is not None:
        alerts.append(_("Napijte se · {ml} ml").format(ml=rem.ml))
    # feature/baterie: app.battery {key: (pct, status)}, app.batt_low(key)
    battery = getattr(app, "battery", None) or {}
    batt_low = getattr(app, "batt_low", None)
    if callable(batt_low) and getattr(cfg, "battery_warn", True):
        low = []
        for key in battery:
            try:
                if batt_low(key):
                    d = app.devices.get(key)
                    low.append(d.type_name if d else f"#{key[0]}")
            except Exception:  # noqa: BLE001
                pass
        if low:
            alerts.append(_("Slabá baterie · ") + ", ".join(low))
    if state == "unplugged":
        alerts.append(_("Dongle odpojen"))
    elif monitoring and ctrl.power_gap_s:
        alerts.append(_("Výpadek příjmu · {power_gap_s:.0f} s").format(power_gap_s=ctrl.power_gap_s))
    sim = bool(app.sim_var.get())
    fan_used = monitoring or not auto
    if not sim and fan_used and cfg.fan.ip and not app.fan_ok:
        alerts.append(_("Ventilátor neodpovídá"))

    return {"level": level, "auto": auto, "level_text": level_text, "reason": reason,
            "second": second, "alerts": alerts}


def next_level(auto: bool, manual: int, max_level: int):
    """Kliknutí na stupeň: Auto → 1 → 2 → … → max → Vyp → Auto."""
    if auto:
        return 1 if max_level >= 1 else 0
    if manual == 0:
        return "auto"
    if manual >= max_level:
        return 0
    return manual + 1


def _palette():
    from . import app as app_mod
    return app_mod.DARK  # lišta je vždy tmavá, čitelná přes světlou i tmavou hru


class Overlay:
    def __init__(self, app):
        self.app = app
        self.win: tk.Toplevel | None = None
        self._last_update = 0.0
        self._last_topmost = 0.0
        self._seen_alerts: set[str] = set()
        self._alert_until = 0.0
        self._drag = None
        self.state: dict = {}

    # ------------------------------------------------------------ okno
    @property
    def cfg(self):
        return self.app.cfg

    def visible(self) -> bool:
        return self.win is not None and self.win.winfo_exists() and self.win.winfo_viewable()

    def sync(self):
        """Postaví nebo zruší okno podle nastavení."""
        if self.cfg.overlay_enabled:
            self._build()
            self.update(force=True)
        else:
            self._destroy()

    def rebuild(self):
        """Po _rebuild_ui: staré okno zničil destroy potomků rootu."""
        self.win = None
        self.sync()

    def _destroy(self):
        if self.win is not None:
            try:
                self.win.destroy()
            except tk.TclError:
                pass
        self.win = None

    def _build(self):
        self._destroy()
        app, p = self.app, _palette()
        mini = self.cfg.overlay_size == "mini"
        fam = app.fonts.body[0] or "TkDefaultFont"
        scale = 1.3 if sys.platform == "darwin" else 1.0
        big = (fam, int((12 if mini else 17) * scale), "bold")
        small = (fam, int((8 if mini else 10) * scale))
        pad = int((5 if mini else 8) * app.px)

        w = self.win = tk.Toplevel(app.root)
        w.withdraw()
        w.overrideredirect(True)
        try:
            w.attributes("-topmost", True)
            w.attributes("-alpha", 0.85)
        except tk.TclError:
            pass
        w.configure(bg=p["BG"])
        # tenký okraj, aby proužek byl vidět i na tmavé scéně
        frame = tk.Frame(w, bg=p["BG"], highlightthickness=1, highlightbackground=p["BORDER"])
        frame.pack(fill="both", expand=True)
        inner = tk.Frame(frame, bg=p["BG"])
        inner.pack(padx=pad * 2, pady=pad)
        self.lbl_level = tk.Label(inner, text="–", bg=p["BG"], fg=p["FAN"], font=big, cursor="hand2")
        self.lbl_level.pack(side="left")
        self.lbl_reason = tk.Label(inner, text="", bg=p["BG"], fg=p["MUTED"], font=small)
        self.lbl_reason.pack(side="left", anchor="s", pady=(0, 2))
        self.lbl_second = tk.Label(inner, text="", bg=p["BG"], fg=p["HR"], font=small)
        self.lbl_second.pack(side="left", anchor="s", pady=(0, 2))
        self.lbl_alert = tk.Label(inner, text="", bg=p["BG"], fg=p["BAD"], font=small)
        self.lbl_alert.pack(side="left", anchor="s", pady=(0, 2))
        self._colors = p
        for wd in (w, frame, inner, self.lbl_level, self.lbl_reason, self.lbl_second, self.lbl_alert):
            wd.bind("<ButtonPress-1>", self._on_press)
            wd.bind("<B1-Motion>", self._on_motion)
            wd.bind("<ButtonRelease-1>", self._on_release)
        self._place()
        if not self.cfg.overlay_alerts_only:
            w.deiconify()
            self._raise()
        self._last_topmost = time.monotonic()

    def _place(self):
        w = self.win
        w.update_idletasks()
        ww, wh = w.winfo_reqwidth(), w.winfo_reqheight()
        sw, sh = w.winfo_screenwidth(), w.winfo_screenheight()
        x, y = self.cfg.overlay_x, self.cfg.overlay_y
        if x is None or y is None:
            x, y = sw - ww - MARGIN, MARGIN
        x = max(0, min(int(x), sw - 40))  # monitor se mohl změnit
        y = max(0, min(int(y), sh - 20))
        w.geometry(f"+{x}+{y}")

    def reset_position(self):
        self.cfg.overlay_x = self.cfg.overlay_y = None
        config_mod.save(self.cfg)
        if self.win is not None:
            self._place()

    # ------------------------------------------------------------ myš
    def _on_press(self, e):
        self._drag = (e.x_root, e.y_root, self.win.winfo_x(), self.win.winfo_y(), e.widget, False)

    def _on_motion(self, e):
        if not self._drag:
            return
        x0, y0, wx, wy, wd, moved = self._drag
        dx, dy = e.x_root - x0, e.y_root - y0
        if not moved and abs(dx) + abs(dy) < 4:
            return
        self._drag = (x0, y0, wx, wy, wd, True)
        self._drag_pos = (wx + dx, wy + dy)  # winfo_x se na macOS obnoví až později
        self.win.geometry(f"+{wx + dx}+{wy + dy}")

    def _on_release(self, e):
        drag, self._drag = self._drag, None
        if not drag:
            return
        if drag[5]:
            self.save_position(*self._drag_pos)
        elif drag[4] is self.lbl_level:
            self.on_level_click()

    def save_position(self, x: int, y: int):
        self.cfg.overlay_x, self.cfg.overlay_y = int(x), int(y)
        config_mod.save(self.cfg)

    def on_level_click(self):
        app = self.app
        app.on_segment(next_level(app.auto_var.get(), app.manual_level, app.cfg.fan.max_level))
        self.update(force=True)

    # ------------------------------------------------------------ obnova
    def tick(self, now: float):
        """Volá App._tick (4× za s); obnova 1× za s."""
        if self.win is None:
            return
        if now - self._last_update >= 1.0:
            self.update(now=now)
        if sys.platform == "win32" and now - self._last_topmost >= TOPMOST_EVERY_S:
            self._last_topmost = now
            self._raise(toggle=True)

    def _raise(self, toggle: bool = False):
        try:
            if toggle:
                self.win.attributes("-topmost", False)
            self.win.attributes("-topmost", True)
            self.win.lift()
        except tk.TclError:
            pass

    def update(self, now: float | None = None, force: bool = False):
        w = self.win
        if w is None or not w.winfo_exists():
            return
        now = time.monotonic() if now is None else now
        self._last_update = now
        st = self.state = overlay_state(self.app, now)
        p = self._colors
        self._set(self.lbl_level, st["level_text"], p["FAN"] if st["auto"] else p["TEXT"])
        # mezery a tečka v textu místo padx: prázdný label pak nezabírá místo
        self._set(self.lbl_reason, f" · {st['reason']}" if st["reason"] else "")
        self._set(self.lbl_second, f"   {st['second']}" if st["second"] else "")
        alert = st["alerts"][0] if st["alerts"] else ""
        if len(st["alerts"]) > 1:
            alert += f"  +{len(st['alerts']) - 1}"
        self._set(self.lbl_alert, f"   {alert}" if alert else "",
                  p["ACCENT"] if alert.startswith(_("Napijte")) else p["BAD"])
        if self.cfg.overlay_x is None and w.winfo_reqwidth() != getattr(self, "_req_w", 0):
            self._req_w = w.winfo_reqwidth()
            self._place()  # ve výchozím rohu držet pravý okraj
        # režim jen upozornění: vyjede při novém upozornění a po 20 s zmizí
        new = set(st["alerts"]) - self._seen_alerts
        self._seen_alerts = {a for a in self._seen_alerts | set(st["alerts"]) if a in st["alerts"]}
        if new:
            self._alert_until = now + ALERT_SHOW_S
        show = not self.cfg.overlay_alerts_only or (st["alerts"] and now < self._alert_until)
        if show and not w.winfo_viewable():
            w.deiconify()
            self._raise()
        elif not show and w.winfo_viewable():
            w.withdraw()

    @staticmethod
    def _set(lb, text, fg=None):
        if lb.cget("text") != text:
            lb.configure(text=text)
        if fg and lb.cget("fg") != fg:
            lb.configure(fg=fg)


def _c(name: str) -> str:
    from . import app as app_mod
    return getattr(app_mod, name)


def build_settings(app, p):
    """Volby lišty na stránce Nastavení → Vzhled."""
    c = app.cfg
    box = tk.Frame(p, bg=_c("BG"))
    box.pack(fill="x", pady=(16, 0))
    tk.Label(box, text=_("Lišta navrchu"), bg=_c("BG"), fg=_c("TEXT"), font=app.fonts.title,
             anchor="w").pack(fill="x")
    tk.Label(box, text=_("Malý proužek přes Rouvy: stupeň ventilátoru, důvod a upozornění. "
                       "Přetažením myší ho posunete, kliknutím na stupeň přepnete Auto, 1, 2… Vyp."),
             bg=_c("BG"), fg=_c("MUTED"), font=app.fonts.small, anchor="w", justify="left",
             wraplength=int(440 * app.px)).pack(fill="x", pady=(2, 6))
    ttk.Checkbutton(box, text=_("Zobrazit lištu"), variable=app.overlay_var,
                    command=lambda: apply(app)).pack(anchor="w")
    app._ov_size = tk.StringVar(value=c.overlay_size)
    app._ov_second = tk.StringVar(value=c.overlay_second)
    app._ov_alerts = tk.BooleanVar(value=c.overlay_alerts_only)
    for title, var, opts in ((_("Velikost"), app._ov_size, SIZES), (_("Druhé číslo"), app._ov_second, SECOND_OPTS)):
        row = tk.Frame(box, bg=_c("BG"))
        row.pack(fill="x", pady=(4, 0))
        tk.Label(row, text=title, bg=_c("BG"), fg=_c("TEXT"), font=app.fonts.body, width=12,
                 anchor="w").pack(side="left")
        for key, text in opts:
            ttk.Radiobutton(row, text=_(text), variable=var, value=key,
                            command=lambda: apply(app)).pack(side="left", padx=(0, 10))
    ttk.Checkbutton(box, text=_("Jen upozornění (jinak skrytá, při upozornění se na 20 s ukáže)"),
                    variable=app._ov_alerts, command=lambda: apply(app)).pack(anchor="w", pady=(4, 0))
    ttk.Button(box, text=_("Vrátit lištu do rohu"), command=app.overlay.reset_position).pack(
        anchor="w", pady=(8, 0))


def apply(app):
    """Uloží volby z Nastavení / přepínače v okně jízdy a lištu přestaví."""
    c = app.cfg
    c.overlay_enabled = bool(app.overlay_var.get())
    if hasattr(app, "_ov_size"):
        c.overlay_size = app._ov_size.get()
        c.overlay_second = app._ov_second.get()
        c.overlay_alerts_only = bool(app._ov_alerts.get())
    config_mod.save(c)
    app.overlay.sync()
