"""GUI aplikace AntFan (tkinter).

Dvě okna:
  * Jízda (hlavní) – velká čísla čitelná ze sedla, graf posledních 10 minut,
    ruční přepínač stupně a stav příjmu senzorů.
  * Nastavení – senzory, ventilátor, řízení, chování, diagnostika.
    Změny se ukládají hned.
"""
from __future__ import annotations

import atexit
import logging
import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
from collections import deque
from logging.handlers import RotatingFileHandler
from tkinter import messagebox, ttk

from . import __version__
from . import config as config_mod
from . import drink, overlay, qr, usb_diag, web
from .ant_backend import FE_TYPE, HR_TYPE, MAX_CHANNELS, PM_TYPE, AntBackend, FoundDevice, SimulatedBackend
from .controller import Controller
from .fans import FanError, HomeAssistantFan, ShellyFan
from .miio_fan import FanWorker, MiioError, SimulatedFan, XiaomiFan
from .single_instance import SingleInstance
from . import vitr_ui

log = logging.getLogger("antfan")

HISTORY_S = 600  # graf: posledních 10 minut

# barvy – jedna barva = jeden význam; hodnoty se přepíšou podle motivu (_set_palette)
LIGHT = dict(BG="#ffffff", SURFACE="#f6f5f2", BORDER="#e3e1db", TEXT="#1f1f1d", MUTED="#6b6a65",
             FAINT="#a3a19a", POWER="#D85A30", HR="#D4537E", FAN="#185FA5", FAN_BAND="#e1ecf7",
             ACCENT="#185FA5", ACCENT_BG="#e6f1fb", OK="#2f7d32", BAD="#c0392b")
DARK = dict(BG="#1c1d20", SURFACE="#26272b", BORDER="#3a3b40", TEXT="#ecebe7", MUTED="#a3a29c",
            FAINT="#6f6e69", POWER="#EE7A50", HR="#E8739B", FAN="#5E9FE3", FAN_BAND="#1e3048",
            ACCENT="#5E9FE3", ACCENT_BG="#1e3048", OK="#5cb860", BAD="#e8695a")
BG = SURFACE = BORDER = TEXT = MUTED = FAINT = POWER = HR = FAN = FAN_BAND = ACCENT = ACCENT_BG = OK = BAD = ""
FAN_KINDS = {"xiaomi": "Xiaomi", "shelly": "Shelly zásuvka", "homeassistant": "Home Assistant"}
THEMES = [("light", "Světlý"), ("dark", "Tmavý"), ("system", "Podle systému")]


def system_is_dark() -> bool:
    try:
        if sys.platform == "win32":
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as k:
                return winreg.QueryValueEx(k, "AppsUseLightTheme")[0] == 0
        if sys.platform == "darwin":
            r = subprocess.run(["defaults", "read", "-g", "AppleInterfaceStyle"],
                               capture_output=True, text=True, timeout=2)
            return "Dark" in r.stdout
    except Exception:  # noqa: BLE001
        pass
    return False


def _set_palette(dark: bool) -> None:
    globals().update(DARK if dark else LIGHT)


def _titlebar(win, dark: bool) -> None:
    """Tmavý titulek okna na Windows 10/11 (jinak nic)."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        win.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(win.winfo_id())
        val = ctypes.c_int(1 if dark else 0)
        for attr in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE (nový / starší build)
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(val), 4) == 0:
                break
    except Exception:  # noqa: BLE001
        pass


_set_palette(False)

MODE_CARDS = [
    ("smart", "Chytře", "Výkon zvyšuje, tep drží"),
    ("power", "Jen výkon", "Reaguje hned"),
    ("hr", "Jen tep", "Bez powermetru"),
    ("max", "Vyšší z obou", "Fouká víc"),
    ("wind", "Vítr podle rychlosti", "Rychlost jízdy z trenažéru"),
]


def setup_logging():
    path = config_mod.app_dir() / "antfan.log"
    handler = RotatingFileHandler(path, maxBytes=3_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    logging.getLogger("openant").setLevel(logging.WARNING)


def _plural_senzor(n: int) -> str:
    return "senzor" if n == 1 else ("senzory" if 2 <= n <= 4 else "senzorů")


class Fonts:
    def __init__(self, root):
        fams = set(tkfont.families(root))
        base = "Segoe UI" if "Segoe UI" in fams else tkfont.nametofont("TkDefaultFont").actual()["family"]
        semi = "Segoe UI Semibold" if "Segoe UI Semibold" in fams else None
        # macOS: systémové písmo (SF) z TkDefaultFont; Tk tam bere 1 bod = 1 pixel,
        # takže stejné velikosti jako na Windows (96 dpi) by byly o třetinu menší
        k = 1.3 if sys.platform == "darwin" else 1.0

        def sz(n):
            return int(round(n * k))

        self.small = (base, sz(9))
        self.body = (base, sz(10))
        self.body_b = (semi, sz(10)) if semi else (base, sz(10), "bold")
        self.title = (semi, sz(11)) if semi else (base, sz(11), "bold")
        self.h2 = (semi, sz(13)) if semi else (base, sz(13), "bold")
        self.big = (semi, sz(40)) if semi else (base, sz(40), "bold")
        self.chart = (base, sz(8))


class StatusDot(tk.Frame):
    def __init__(self, parent, fonts):
        super().__init__(parent, bg=BG)
        self.c = tk.Canvas(self, width=10, height=10, bg=BG, highlightthickness=0)
        self.c.pack(side="left", padx=(0, 6))
        self.dot = self.c.create_oval(2, 2, 9, 9, fill=FAINT, outline="")
        self.lbl = tk.Label(self, text="", bg=BG, fg=MUTED, font=fonts.body)
        self.lbl.pack(side="left")

    def set(self, text, color):
        if self.lbl.cget("text") != text:
            self.lbl.configure(text=text)
        self.c.itemconfigure(self.dot, fill=color)


class Segmented(tk.Frame):
    """Přepínač Auto | Vyp | 1 | 2 | 3."""

    def __init__(self, parent, options, command, fonts):
        super().__init__(parent, bg=BORDER, padx=1, pady=1)
        self.items: dict = {}
        for i, (key, text) in enumerate(options):
            lb = tk.Label(self, text=text, bg=BG, fg=TEXT, font=fonts.body, padx=13, pady=4,
                          cursor="hand2")
            lb.pack(side="left", padx=(0 if i == 0 else 1, 0))
            lb.bind("<Button-1>", lambda e, k=key: command(k))
            self.items[key] = lb

    def set(self, key):
        for k, lb in self.items.items():
            sel = k == key
            lb.configure(bg=ACCENT_BG if sel else BG, fg=ACCENT if sel else TEXT)


class ChoiceCard(tk.Frame):
    def __init__(self, parent, title, desc, command, fonts):
        super().__init__(parent, bg=BG, highlightthickness=1, highlightbackground=BORDER,
                         highlightcolor=BORDER, cursor="hand2")
        t = tk.Label(self, text=title, bg=BG, fg=TEXT, font=fonts.body_b, anchor="w")
        d = tk.Label(self, text=desc, bg=BG, fg=MUTED, font=fonts.small, anchor="w")
        t.pack(fill="x", padx=10, pady=(7, 0))
        d.pack(fill="x", padx=10, pady=(0, 7))
        for w in (self, t, d):
            w.bind("<Button-1>", lambda e: command())

    def set_selected(self, sel):
        col = ACCENT if sel else BORDER
        self.configure(highlightthickness=2 if sel else 1, highlightbackground=col, highlightcolor=col)


def _hline(parent):
    tk.Frame(parent, height=1, bg=BORDER).pack(fill="x")


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.cfg = config_mod.load()
        self.events: queue.Queue = queue.Queue()
        self.devices: dict[tuple[int, int], FoundDevice] = {}
        self.selected: set[tuple[int, int]] = {(d[0], d[1]) for d in self.cfg.selected}
        self.dev_values: dict[tuple[int, int], tuple[float, int]] = {}
        self.controller = Controller(self.cfg.control, self.cfg.fan.max_level)
        self.history: deque = deque(maxlen=HISTORY_S)
        self._last_hist = 0.0
        self.fan_actual: int | None = None
        self._last_pm_value = -1e9
        self.manual_level = 0
        self._ant_error = False
        self.ant_status_full = "Připraveno"
        self.fan_status_text, self.fan_ok = "nepřipojeno", False
        self._apply_job = None
        self._last_bars = None
        self.web = web.WebServer(self.events)  # ovládání z mobilu; přežije _rebuild_ui
        self.web_error = ""
        self.web_on = self.cfg.web_autostart  # zapíná se tlačítkem Mobil, trvale jen volbou v Nastavení
        self._web_last = 0.0
        self.drink = drink.DrinkTracker(self.cfg.drink_enabled, self.cfg.drink_temp_c,
                                        self.cfg.drink_interval_min)  # připomínka pití
        self._drink_job = None
        self.overlay = overlay.Overlay(self)  # lišta navrchu; okno se staví znovu po _rebuild_ui
        self.overlay_var = tk.BooleanVar(value=self.cfg.overlay_enabled)

        for d in self.cfg.selected:
            fd = FoundDevice(d[0], d[1], d[2] if len(d) > 2 else 0)
            self.devices[fd.key] = fd

        self.backend = None
        self.fan_worker = FanWorker(self.events)
        self.sim_var = tk.BooleanVar(value=self.cfg.simulation)
        self.auto_var = tk.BooleanVar(value=self.cfg.auto_mode)
        self.source_mode = self.cfg.control.source_mode

        self.fonts = Fonts(root)
        self.px = max(1.0, root.winfo_fpixels("1i") / 96)  # měřítko pro pixely (HiDPI)
        self._native_theme = ttk.Style().theme_use()
        self.theme_var = tk.StringVar(value=self.cfg.theme if self.cfg.theme in dict(THEMES) else "system")
        self.dark = self._want_dark()
        _set_palette(self.dark)
        self._setup_style()
        root.title("AntFan")
        root.configure(bg=BG)
        self._build_ride()
        self._build_settings()
        _titlebar(root, self.dark)
        _titlebar(self.settings, self.dark)
        self._make_backend()
        self._make_fan()
        self._refresh_tree()
        self._web_sync()
        self.overlay.sync()

        root.update_idletasks()
        need_w, need_h = root.winfo_reqwidth(), root.winfo_reqheight()
        scr_w, scr_h = root.winfo_screenwidth(), root.winfo_screenheight() - 60
        w = min(max(need_w, int(900 * self.px)), scr_w)
        h = min(max(need_h + int(200 * self.px), int(620 * self.px)), scr_h)
        root.geometry(f"{w}x{h}")
        root.minsize(min(need_w, scr_w), min(need_h + int(120 * self.px), scr_h))

        root.protocol("WM_DELETE_WINDOW", self._on_close)
        root.after(100, self._poll_events)
        root.after(250, self._tick)
        if not self.selected:  # první spuštění: rovnou výběr senzorů
            root.after(300, lambda: self.open_settings("sensors"))

    # ================================================================ vzhled
    def _want_dark(self) -> bool:
        t = self.theme_var.get()
        return system_is_dark() if t == "system" else t == "dark"

    def _setup_style(self):
        st = ttk.Style()
        f = self.fonts
        if self.dark:
            # nativní motiv Windows (vista) barvy nebere, clam ano
            st.theme_use("clam")
            st.configure(".", background=BG, foreground=TEXT, fieldbackground=SURFACE, bordercolor=BORDER,
                         lightcolor=SURFACE, darkcolor=SURFACE, troughcolor=SURFACE, focuscolor=ACCENT,
                         selectbackground=ACCENT, selectforeground="#ffffff", insertcolor=TEXT,
                         arrowcolor=TEXT)
            st.configure("TButton", background=SURFACE, foreground=TEXT, padding=(10, 3))
            st.map("TButton", background=[("pressed", BORDER), ("active", BORDER)])
            for name in ("TEntry", "TSpinbox"):
                st.configure(name, fieldbackground=SURFACE, foreground=TEXT, insertcolor=TEXT)
                st.map(name, fieldbackground=[("disabled", BG)], foreground=[("disabled", FAINT)])
            for name in ("TCheckbutton", "TRadiobutton"):
                st.configure(name, indicatorbackground=SURFACE, indicatorforeground=TEXT)
                st.map(name, background=[("active", BG)], indicatorbackground=[("pressed", BORDER)])
            st.configure("Treeview", background=SURFACE, fieldbackground=SURFACE, foreground=TEXT)
            st.configure("Treeview.Heading", background=BG, foreground=MUTED)
            st.map("Treeview.Heading", background=[("active", SURFACE)])
        else:
            st.theme_use(self._native_theme)
        for name in ("TFrame", "TLabel", "TCheckbutton", "TRadiobutton"):
            st.configure(name, background=BG)
        st.configure("TLabel", foreground=TEXT, font=f.body)
        st.configure("TCheckbutton", foreground=TEXT, font=f.body)
        st.configure("TRadiobutton", foreground=TEXT, font=f.body)
        st.configure("TButton", font=f.body)
        st.configure("Treeview", font=f.body, rowheight=int(24 * self.px))
        st.configure("Treeview.Heading", font=f.small)

    def on_theme(self):
        self.cfg.theme = self.theme_var.get()
        config_mod.save(self.cfg)
        dark = self._want_dark()
        if dark != self.dark:
            self._rebuild_ui(dark)

    def _rebuild_ui(self, dark: bool):
        """Přestaví obě okna v novém motivu; stav měření a historie zůstává."""
        if self._apply_job is not None:
            self.root.after_cancel(self._apply_job)
            self._apply_job = None
        self.on_apply()
        page = getattr(self, "_page", "sensors")
        shown = self.settings.winfo_viewable()
        geo, sgeo = self.root.geometry(), self.settings.geometry()
        for w in self.root.winfo_children():
            w.destroy()
        self.dark = dark
        _set_palette(dark)
        self._setup_style()
        self.root.configure(bg=BG)
        self._last_bars = self._last_pct_bar = None
        self._build_ride()
        self._build_settings()
        self.root.geometry(geo)
        self.settings.geometry(sgeo)
        self.show_page(page)
        self._set_fan_status(self.fan_status_text, self.fan_ok)
        self._refresh_tree()
        self.overlay.rebuild()
        _titlebar(self.root, dark)
        _titlebar(self.settings, dark)
        if shown:
            self.settings.deiconify()
            self.settings.lift()

    def _lbl(self, parent, text="", fg=MUTED, font=None, **kw):
        return tk.Label(parent, text=text, bg=BG, fg=fg, font=font or self.fonts.small, **kw)

    # ================================================================ jízda
    def _build_ride(self):
        r, f = self.root, self.fonts
        top = tk.Frame(r, bg=BG)
        top.pack(fill="x", padx=14, pady=10)
        tk.Label(top, text="AntFan", bg=BG, fg=TEXT, font=f.title).pack(side="left", padx=(0, 14))
        self.st_ant = StatusDot(top, f)
        self.st_ant.pack(side="left", padx=(0, 14))
        self.st_fan = StatusDot(top, f)
        self.st_fan.pack(side="left")
        ttk.Button(top, text="Nastavení", command=lambda: self.open_settings()).pack(side="right")
        self.btn_web = ttk.Button(top, text="Zapnout mobil", command=self.on_web_button)
        self.btn_web.pack(side="right", padx=(8, 0))
        self.st_web = StatusDot(top, f)
        self.st_web.pack(side="left", padx=(14, 0))
        self.btn_run = ttk.Button(top, text="Spustit měření", command=self.on_run_toggle)
        self.btn_run.pack(side="right", padx=8)
        ttk.Checkbutton(top, text="Lišta", variable=self.overlay_var,
                        command=lambda: overlay.apply(self)).pack(side="right", padx=(0, 6))
        _hline(r)

        tiles = tk.Frame(r, bg=BG)
        tiles.pack(fill="x")
        for i in (0, 2, 4):
            tiles.columnconfigure(i, weight=1, uniform="tile")
        self.t_power = self._tile(tiles, 0, "Výkon · průměr", "W", POWER)
        tk.Frame(tiles, width=1, bg=BORDER).grid(row=0, column=1, sticky="ns")
        self.t_hr = self._tile(tiles, 2, "Tep", "bpm", HR)
        tk.Frame(tiles, width=1, bg=BORDER).grid(row=0, column=3, sticky="ns")
        self.t_fan = self._tile(tiles, 4, "Ventilátor", "", FAN, bars=True)
        _hline(r)

        self.canvas = tk.Canvas(r, background=BG, highlightthickness=0, height=int(220 * self.px))
        self.canvas.pack(fill="both", expand=True, padx=12, pady=(8, 2))
        self.canvas.bind("<Configure>", lambda e: self._draw_chart())
        legend = tk.Frame(r, bg=BG)
        legend.pack(fill="x", padx=16, pady=(0, 8))
        for text, col in (("výkon, W", POWER), ("tep, bpm (60–200)", HR), ("ventilátor", FAN)):
            self._lbl(legend, text, fg=col).pack(side="left", padx=(0, 14))
        self._lbl(legend, "posledních 10 min", fg=FAINT).pack(side="right")
        self._build_drink_strip(r)
        _hline(r)

        bottom = tk.Frame(r, bg=BG)
        bottom.pack(fill="x", padx=14, pady=10)
        opts = [("auto", "Auto"), (0, "Vyp")] + [(i, str(i)) for i in range(1, self.cfg.fan.max_level + 1)]
        self.seg = Segmented(bottom, opts, self.on_segment, f)
        self.seg.pack(side="left")
        self.rx_box = tk.Frame(bottom, bg=BG)
        self.rx_box.pack(side="right")
        self.rx_labels: list = []
        self.lbl_ride_hint = self._lbl(r, "", fg=BAD, font=f.body, justify="left", anchor="w")
        self.lbl_ride_hint.pack(fill="x", padx=16, pady=(0, 10))
        r.bind("<Configure>", lambda e: self.lbl_ride_hint.configure(
            wraplength=max(200, r.winfo_width() - 40)))
        self._update_segment()

    def _tile(self, parent, col, title, unit, color, bars=False):
        cell = tk.Frame(parent, bg=BG)
        cell.grid(row=0, column=col, sticky="nsew", padx=16, pady=(12, 12))
        head = self._lbl(cell, title, anchor="w")
        head.pack(fill="x")
        line = tk.Frame(cell, bg=BG)
        line.pack(anchor="w")
        big = tk.Label(line, text="–", bg=BG, fg=color, font=self.fonts.big)
        big.pack(side="left")
        bar_c = None
        if bars:
            bw = int(12 * self.px)
            bar_c = tk.Canvas(line, width=bw * 4, height=int(30 * self.px), bg=BG, highlightthickness=0)
            bar_c.pack(side="left", padx=(10, 0), pady=(0, int(10 * self.px)), anchor="s")
        elif unit:
            self._lbl(line, unit).pack(side="left", padx=(6, 0), pady=(0, int(10 * self.px)), anchor="s")
        sub = self._lbl(cell, "", anchor="w", justify="left")
        sub.pack(fill="x")
        return {"head": head, "big": big, "sub": sub, "bars": bar_c}

    def _draw_bars(self, level):
        n = max(1, self.cfg.fan.max_level)
        if self._last_bars == (level, n):
            return
        self._last_bars = (level, n)
        c = self.t_fan["bars"]
        c.delete("all")
        bw, gap = int(10 * self.px), int(3 * self.px)
        hmax = int(28 * self.px)
        for i in range(n):
            h = int(hmax * (i + 1) / n)
            x = i * (bw + gap)
            c.create_rectangle(x, hmax - h + 2, x + bw, hmax + 2, outline="",
                               fill=FAN if i < level else BORDER)

    # ============================================================ nastavení
    def _build_settings(self):
        w = self.settings = tk.Toplevel(self.root)
        w.title("AntFan – nastavení")
        w.configure(bg=BG)
        w.withdraw()
        w.protocol("WM_DELETE_WINDOW", w.withdraw)
        nav = tk.Frame(w, bg=SURFACE)
        nav.pack(side="left", fill="y")
        tk.Frame(w, width=1, bg=BORDER).pack(side="left", fill="y")
        host = tk.Frame(w, bg=BG)
        host.pack(side="left", fill="both", expand=True, padx=20, pady=16)
        self.pages, self.nav_items = {}, {}
        tk.Frame(nav, bg=SURFACE, height=10).pack()
        for key, title, builder in (("sensors", "Senzory", self._page_sensors),
                                    ("fan", "Ventilátor", self._page_fan),
                                    ("control", "Řízení", self._page_control),
                                    ("behavior", "Chování", self._page_behavior),
                                    ("drink", "Pití", self._page_drink),
                                    ("look", "Vzhled", self._page_look),
                                    ("mobile", "Mobil", self._page_mobile),
                                    ("diag", "Diagnostika", self._page_diag)):
            lb = tk.Label(nav, text=title, bg=SURFACE, fg=MUTED, font=self.fonts.body, anchor="w",
                          padx=14, pady=6, width=14, cursor="hand2")
            lb.pack(fill="x", padx=6, pady=1)
            lb.bind("<Button-1>", lambda e, k=key: self.show_page(k))
            self.nav_items[key] = lb
            page = tk.Frame(host, bg=BG)
            builder(page)
            self.pages[key] = page
        self.show_page("sensors")
        w.update_idletasks()
        need = max(p.winfo_reqwidth() for p in self.pages.values()) + nav.winfo_reqwidth() + 60
        hneed = max(p.winfo_reqheight() for p in self.pages.values()) + 50
        w.geometry(f"{need}x{hneed}")
        w.minsize(need, hneed)

    def show_page(self, key):
        self._page = key
        for k, p in self.pages.items():
            p.pack_forget()
            self.nav_items[k].configure(bg=BG if k == key else SURFACE, fg=TEXT if k == key else MUTED)
        self.pages[key].pack(fill="both", expand=True)

    def open_settings(self, page=None):
        if page:
            self.show_page(page)
        self.settings.deiconify()
        self.settings.lift()
        self.settings.focus_force()

    def _page_head(self, page, title, desc):
        tk.Label(page, text=title, bg=BG, fg=TEXT, font=self.fonts.h2, anchor="w").pack(fill="x")
        self._lbl(page, desc, anchor="w", justify="left", wraplength=int(440 * self.px)).pack(
            fill="x", pady=(2, 12))

    def _entry(self, parent, value, width=6):
        e = ttk.Entry(parent, width=width, justify="center")
        v = int(value) if float(value).is_integer() else value
        e.insert(0, str(v))
        e.bind("<KeyRelease>", lambda ev: self._schedule_apply())
        return e

    # --- Senzory
    def _page_sensors(self, p):
        self._page_head(p, "Senzory", "Kliknutím vyberte tepový pás a trenažér nebo powermetr. "
                                      "Výběr se pamatuje, příště stačí Spustit měření.")
        row = tk.Frame(p, bg=BG)
        row.pack(fill="x", pady=(0, 8))
        ttk.Button(row, text="Hledat senzory", command=self.on_scan).pack(side="left")
        self.lbl_scan = self._lbl(row, "", font=self.fonts.body)
        self.lbl_scan.pack(side="left", padx=10)
        cols = ("sel", "type", "id", "value", "rx")
        self.tree = ttk.Treeview(p, columns=cols, show="headings", selectmode="none", height=7)
        for c, t, wd in (("sel", "", 30), ("type", "Typ", 110), ("id", "ID", 70),
                         ("value", "Hodnota", 80), ("rx", "Příjem", 70)):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=int(wd * self.px), anchor="center" if c != "type" else "w")
        self.tree.tag_configure("weak", foreground=BAD)
        self.tree.pack(fill="x")
        self.tree.bind("<Button-1>", self.on_tree_click)
        self.lbl_sensor_hint = self._lbl(p, "", fg=BAD, font=self.fonts.body, justify="left",
                                         anchor="w", wraplength=int(440 * self.px))
        self.lbl_sensor_hint.pack(fill="x", pady=(8, 0))
        self._lbl(p, f"Najednou nejvýš {MAX_CHANNELS} senzorů. Trenažér vysílá výkon jako Trenažér "
                     "i jako Powermetr se stejným ID, stačí vybrat jeden.",
                  anchor="w", justify="left", wraplength=int(440 * self.px)).pack(fill="x", pady=(6, 0))

    # --- Ventilátor
    def _page_fan(self, p):
        f = self.cfg.fan
        self._page_head(p, "Ventilátor", "Co AntFan ovládá. Údaje zůstávají jen v tomto počítači.")
        self.fan_kind = tk.StringVar(value=f.kind if f.kind in FAN_KINDS else "xiaomi")
        kinds = tk.Frame(p, bg=BG)
        kinds.pack(fill="x", pady=(0, 10))
        for key, text in FAN_KINDS.items():
            ttk.Radiobutton(kinds, text=text, variable=self.fan_kind, value=key,
                            command=self._show_fan_kind).pack(side="left", padx=(0, 14))
        host = tk.Frame(p, bg=BG)
        host.pack(fill="x")
        wl = int(440 * self.px)

        def grid(parent):
            g = tk.Frame(parent, bg=BG)
            g.pack(fill="x")
            return g

        def row(g, r, label, widget):
            ttk.Label(g, text=label).grid(row=r, column=0, sticky="w", pady=3)
            widget.grid(row=r, column=1, sticky="w", pady=3, padx=(10, 0))
            return widget

        def entry(g, value, width=24, show=None):
            e = ttk.Entry(g, width=width, show=show) if show else ttk.Entry(g, width=width)
            e.insert(0, value)
            return e

        # Xiaomi
        fx = tk.Frame(host, bg=BG)
        g = grid(fx)
        self.e_ip = row(g, 0, "IP adresa", entry(g, f.ip))
        self.e_token = row(g, 1, "Token", entry(g, f.token, 40, "•"))
        ttk.Button(fx, text="Získat z účtu Xiaomi…", command=self.on_xiaomi_login).pack(anchor="w", pady=(4, 0))
        self._lbl(fx, "Přihlásíte se QR kódem v aplikaci Mi Home, heslo se nikam nezadává.",
                  anchor="w").pack(fill="x", pady=(2, 6))
        self.lbl_fan_model = self._lbl(fx, f"Model: {f.model}" if f.model else
                                       "Model se zjistí při připojení.", anchor="w")
        self.lbl_fan_model.pack(fill="x")
        self.mute_var = tk.BooleanVar(value=f.mute_buzzer)
        self.light_var = tk.BooleanVar(value=f.light_off)
        ttk.Checkbutton(fx, text="Vypnout pípání", variable=self.mute_var,
                        command=self.on_fan_save).pack(anchor="w", pady=(8, 0))
        ttk.Checkbutton(fx, text="Vypnout podsvícení", variable=self.light_var,
                        command=self.on_fan_save).pack(anchor="w")
        # Shelly
        fs = tk.Frame(host, bg=BG)
        g = grid(fs)
        self.e_shelly = row(g, 0, "IP adresa Shelly", entry(g, f.shelly_host))
        self.sp_shelly_ch = ttk.Spinbox(g, from_=0, to=3, width=5)
        self.sp_shelly_ch.set(f.shelly_channel)
        row(g, 1, "Výstup (kanál)", self.sp_shelly_ch)
        self.sp_on_level_s = ttk.Spinbox(g, from_=1, to=5, width=5)
        self.sp_on_level_s.set(f.on_level)
        row(g, 2, "Zapnout od stupně", self.sp_on_level_s)
        self._lbl(fs, "Obyčejný ventilátor v zásuvce Shelly umí jen zapnout a vypnout. Rychlost nastavte "
                      "na ventilátoru. Shelly musí být bez hesla.", anchor="w", justify="left",
                  wraplength=wl).pack(fill="x", pady=(6, 0))
        # Home Assistant
        fh = tk.Frame(host, bg=BG)
        g = grid(fh)
        self.e_ha_url = row(g, 0, "Adresa", entry(g, f.ha_url or "http://homeassistant.local:8123", 32))
        self.e_ha_token = row(g, 1, "Token", entry(g, f.ha_token, 40, "•"))
        self.e_ha_entity = row(g, 2, "Entita", entry(g, f.ha_entity))
        self.sp_on_level_h = ttk.Spinbox(g, from_=1, to=5, width=5)
        self.sp_on_level_h.set(f.on_level)
        row(g, 3, "Zapnout od stupně", self.sp_on_level_h)
        self._lbl(fh, "Token: v Home Assistant profil → Zabezpečení → Dlouhodobé přístupové tokeny. "
                      "Entita fan.* dostane rychlost v %, switch.* jen zapnout/vypnout od zadaného stupně.",
                  anchor="w", justify="left", wraplength=wl).pack(fill="x", pady=(6, 0))
        self.fan_frames = {"xiaomi": fx, "shelly": fs, "homeassistant": fh}

        common = tk.Frame(p, bg=BG)
        common.pack(fill="x", pady=(12, 0))
        ttk.Label(common, text="Počet stupňů").pack(side="left")
        self.sp_levels = ttk.Spinbox(common, from_=1, to=5, width=5)
        self.sp_levels.set(f.max_level)
        self.sp_levels.pack(side="left", padx=(10, 0))
        bf = tk.Frame(p, bg=BG)
        bf.pack(fill="x", pady=(12, 0))
        ttk.Button(bf, text="Uložit a připojit", command=self.on_fan_save).pack(side="left")
        ttk.Button(bf, text="Vyzkoušet", command=self.on_fan_test).pack(side="left", padx=8)
        self.lbl_fan_status = self._lbl(p, "", font=self.fonts.body, anchor="w", justify="left",
                                        wraplength=wl)
        self.lbl_fan_status.pack(fill="x", pady=(10, 0))
        self._show_fan_kind()

    def _show_fan_kind(self):
        for k, fr in self.fan_frames.items():
            fr.pack_forget()
        self.fan_frames[self.fan_kind.get()].pack(fill="x")

    def on_xiaomi_login(self):
        from .xiaomi_ui import XiaomiLoginDialog

        XiaomiLoginDialog(self)

    def use_xiaomi_device(self, ip: str, token: str, model: str):
        """Zavolá dialog účtu Xiaomi po výběru zařízení."""
        self.fan_kind.set("xiaomi")
        self._show_fan_kind()
        for e, v in ((self.e_ip, ip), (self.e_token, token)):
            e.delete(0, "end")
            e.insert(0, v)
        self.on_fan_save()
        if model:
            self.lbl_fan_model.configure(text=f"Model: {model}")

    # --- Řízení
    def _page_control(self, p):
        c = self.cfg.control
        self._page_head(p, "Řízení", "Podle čeho a od jakých hodnot ventilátor přidává.")
        self._lbl(p, "Řídit podle", fg=TEXT, font=self.fonts.body_b, anchor="w").pack(fill="x", pady=(0, 6))
        cards = tk.Frame(p, bg=BG)
        cards.pack(fill="x")
        cards.columnconfigure(0, weight=1, uniform="card")
        cards.columnconfigure(1, weight=1, uniform="card")
        self.mode_cards = {}
        for i, (key, title, desc) in enumerate(MODE_CARDS):
            card = ChoiceCard(cards, title, desc, lambda k=key: self.on_source(k), self.fonts)
            card.grid(row=i // 2, column=i % 2, sticky="nsew", padx=(0 if i % 2 == 0 else 4, 0 if i % 2 else 4), pady=4)
            self.mode_cards[key] = card
        self._update_cards()

        base = tk.Frame(p, bg=BG)
        base.pack(fill="x", pady=(14, 8))
        ttk.Label(base, text="FTP").pack(side="left")
        self.e_ftp = self._entry(base, c.ftp)
        self.e_ftp.pack(side="left", padx=(6, 4))
        self._lbl(base, "W").pack(side="left", padx=(0, 18))
        ttk.Label(base, text="Max. tep").pack(side="left")
        self.e_hrmax = self._entry(base, c.hr_max)
        self.e_hrmax.pack(side="left", padx=(6, 4))
        self._lbl(base, "bpm").pack(side="left")

        tm = tk.Frame(p, bg=BG)
        tm.pack(fill="x", pady=(0, 6))
        self.thr_mode = tk.StringVar(value=c.threshold_mode)
        ttk.Label(tm, text="Prahy v").pack(side="left", padx=(0, 8))
        ttk.Radiobutton(tm, text="% FTP a % max. tepu", variable=self.thr_mode, value="relative",
                        command=self.on_thr_mode).pack(side="left")
        ttk.Radiobutton(tm, text="W a bpm", variable=self.thr_mode, value="absolute",
                        command=self.on_thr_mode).pack(side="left", padx=10)

        grid = tk.Frame(p, bg=BG)
        grid.pack(fill="x")
        for col, text in enumerate(("Stupeň", "Výkon", "", "Tep", "")):
            self._lbl(grid, text, anchor="w").grid(row=0, column=col, sticky="w", padx=(0, 6), pady=(0, 2))
        self.e_pthr, self.e_hthr, self.lbl_phints, self.lbl_hhints = [], [], [], []
        self.lbl_punits, self.lbl_hunits = [], []
        for i in range(self.cfg.fan.max_level):
            r = i + 1
            ttk.Label(grid, text=str(r)).grid(row=r, column=0, sticky="w", pady=2)
            fp = tk.Frame(grid, bg=BG)
            fp.grid(row=r, column=1, sticky="w")
            ep = self._entry(fp, 0)
            ep.pack(side="left")
            up = self._lbl(fp, "%")
            up.pack(side="left", padx=(4, 0))
            hp = self._lbl(grid, "", anchor="w", width=9)
            hp.grid(row=r, column=2, sticky="w", padx=(4, 18))
            fh = tk.Frame(grid, bg=BG)
            fh.grid(row=r, column=3, sticky="w")
            eh = self._entry(fh, 0)
            eh.pack(side="left")
            uh = self._lbl(fh, "%")
            uh.pack(side="left", padx=(4, 0))
            hh = self._lbl(grid, "", anchor="w", width=9)
            hh.grid(row=r, column=4, sticky="w", padx=(4, 0))
            self.e_pthr.append(ep)
            self.e_hthr.append(eh)
            self.lbl_phints.append(hp)
            self.lbl_hhints.append(hh)
            self.lbl_punits.append(up)
            self.lbl_hunits.append(uh)
        self._thr_shown = c.threshold_mode
        self._fill_thr_entries()
        vitr_ui.build_control_section(self, p)
        self.lbl_ctrl_err = self._lbl(p, "", fg=BAD, font=self.fonts.body, anchor="w")
        self.lbl_ctrl_err.pack(fill="x", pady=(8, 0))
        self._lbl(p, "Změny se ukládají hned. Hystereze, vyhlazení a dofukování jsou v Chování.",
                  anchor="w").pack(fill="x", pady=(2, 0))

    # --- Chování
    def _page_behavior(self, p):
        c = self.cfg.control
        self._page_head(p, "Chování", "Jak rychle ventilátor reaguje a co dělá po tréninku.")
        g = tk.Frame(p, bg=BG)
        g.pack(fill="x")
        rows = [
            ("Hystereze výkonu", c.power_hysteresis, "W", "e_physt"),
            ("Hystereze tepu", c.hr_hysteresis, "bpm", "e_hhyst"),
            ("Vyhlazení výkonu", c.power_smoothing_s, "s", "e_psmooth"),
            ("Vyhlazení tepu", c.hr_smoothing_s, "s", "e_hsmooth"),
            ("Prodleva před snížením", c.down_delay_s, "s", "e_delay"),
            ("Dofukování po tréninku", round(c.cooldown_s / 60, 1), "min", "e_cool_min"),
            ("…na stupni", c.cooldown_level, "", "e_cool_lvl"),
            ("Bez dat ze senzorů stupeň", c.no_data_level, "", "e_nodata_lvl"),
            ("…po", c.no_data_s, "s", "e_nodata_s"),
            ("Předstih: výkon nad prahem", c.lead_s, "s", "e_lead_s"),
        ]
        for i, (label, val, unit, attr) in enumerate(rows):
            ttk.Label(g, text=label).grid(row=i, column=0, sticky="w", pady=2)
            e = self._entry(g, val)
            e.grid(row=i, column=1, sticky="w", padx=10, pady=2)
            self._lbl(g, unit).grid(row=i, column=2, sticky="w")
            setattr(self, attr, e)
        self.lead_var = tk.BooleanVar(value=c.lead_enabled)
        ttk.Checkbutton(p, text="Předstih: při nástupu výkonu zvýšit stupeň hned",
                        variable=self.lead_var, command=self.on_apply).pack(anchor="w", pady=(8, 0))
        self.lbl_beh_err = self._lbl(p, "", fg=BAD, font=self.fonts.body, anchor="w")
        self.lbl_beh_err.pack(fill="x", pady=(8, 0))
        self._lbl(p, "Hystereze: stupeň klesne, až hodnota spadne o tolik pod práh. Prodleva: jak dlouho "
                     "musí být pod prahem. Chytrý režim navíc drží stupeň podle tepu, takže ventilátor "
                     "nezpomalí v krátkém odpočinku mezi intervaly. Předstih: když okamžitý výkon drží "
                     "nad prahem vyššího stupně zadaný počet sekund, stupeň naskočí hned, ne až po průměru.",
                  anchor="w", justify="left", wraplength=int(440 * self.px)).pack(fill="x", pady=(4, 0))

    # --- Vzhled
    def _page_look(self, p):
        self._page_head(p, "Vzhled", "Tmavý motiv méně oslňuje při jízdě v šeru.")
        for key, text in THEMES:
            ttk.Radiobutton(p, text=text, variable=self.theme_var, value=key,
                            command=self.on_theme).pack(anchor="w", pady=2)
        self._lbl(p, "Podle systému: řídí se nastavením " + (
            "macOS (Nastavení systému → Vzhled)." if sys.platform == "darwin"
            else "Windows (Přizpůsobení → Barvy)."),
                  anchor="w").pack(fill="x", pady=(8, 0))
        overlay.build_settings(self, p)

    # --- Mobil
    def _page_mobile(self, p):
        self._page_head(p, "Mobil", "Hodnoty a přepínač stupně na telefonu ve stejné Wi-Fi. "
                                    "Stačí otevřít adresu v prohlížeči, nic se neinstaluje.")
        self.web_var = tk.BooleanVar(value=self.web_on)
        ttk.Checkbutton(p, text="Zapnuto", variable=self.web_var,
                        command=self.on_web_toggle).pack(anchor="w")
        self.web_auto_var = tk.BooleanVar(value=self.cfg.web_autostart)
        ttk.Checkbutton(p, text="Zapnout hned po spuštění programu", variable=self.web_auto_var,
                        command=self.on_web_autostart).pack(anchor="w")
        self._lbl(p, "Jinak se zapíná tlačítkem Zapnout mobil v hlavním okně a po zavření programu se vypne.",
                  anchor="w", justify="left", wraplength=int(440 * self.px)).pack(fill="x", pady=(2, 0))
        row = tk.Frame(p, bg=BG)
        row.pack(fill="x", pady=(8, 0))
        ttk.Label(row, text="Port").pack(side="left")
        self.e_web_port = ttk.Entry(row, width=7, justify="center")
        self.e_web_port.insert(0, str(self.cfg.web_port))
        self.e_web_port.pack(side="left", padx=(8, 0))
        self.e_web_port.bind("<Return>", lambda e: self.on_web_port())
        self.e_web_port.bind("<FocusOut>", lambda e: self.on_web_port())
        self.lbl_web_status = self._lbl(p, "", font=self.fonts.body, anchor="w", justify="left",
                                        wraplength=int(440 * self.px))
        self.lbl_web_status.pack(fill="x", pady=(8, 8))
        box = tk.Frame(p, bg=BG)
        box.pack(fill="x")
        self.qr_canvas = tk.Canvas(box, width=1, height=1, bg=BG, highlightthickness=0)
        self.qr_canvas.pack(side="left", anchor="n", padx=(0, 14))
        right = tk.Frame(box, bg=BG)
        right.pack(side="left", fill="both", expand=True)
        self._lbl(right, "Adresa", fg=TEXT, font=self.fonts.body_b, anchor="w").pack(fill="x")
        self.e_web_url = ttk.Entry(right, width=44)
        self.e_web_url.pack(fill="x", pady=(2, 6))
        bf = tk.Frame(right, bg=BG)
        bf.pack(fill="x")
        ttk.Button(bf, text="Zkopírovat adresu", command=self.on_web_copy).pack(side="left")
        ttk.Button(bf, text="Nový klíč", command=self.on_web_new_key).pack(side="left", padx=8)
        self._lbl(right, "Kdo zná adresu, může ventilátor ovládat. Nový klíč starou adresu zneplatní.",
                  anchor="w", justify="left", wraplength=int(300 * self.px)).pack(fill="x", pady=(8, 0))
        self._lbl(p, "Windows se při prvním zapnutí zeptá, zda AntFan smí do sítě. Povolte soukromé "
                     "sítě, jinak se telefon nepřipojí.",
                  anchor="w", justify="left", wraplength=int(440 * self.px)).pack(fill="x", pady=(12, 0))
        self._web_refresh_page()

    # --- Diagnostika
    def _page_diag(self, p):
        self._page_head(p, "Diagnostika", "Když něco nefunguje.")
        self._lbl(p, "Stav donglu", fg=TEXT, font=self.fonts.body_b, anchor="w").pack(fill="x")
        self.lbl_diag_status = self._lbl(p, "", font=self.fonts.body, anchor="w", justify="left",
                                         wraplength=int(440 * self.px))
        self.lbl_diag_status.pack(fill="x", pady=(2, 6))
        ttk.Button(p, text="Resetovat dongle", command=self.on_reset).pack(anchor="w")
        self._lbl(p, "Uvolní dongle a provede USB reset, jako byste ho vytáhli a znovu zapojili.",
                  anchor="w").pack(fill="x", pady=(2, 12))
        self._lbl(p, "Příjem senzorů", fg=TEXT, font=self.fonts.body_b, anchor="w").pack(fill="x")
        self.lbl_diag_rx = self._lbl(p, "", font=self.fonts.body, anchor="w", justify="left",
                                     wraplength=int(440 * self.px))
        self.lbl_diag_rx.pack(fill="x", pady=(2, 12))
        ttk.Button(p, text="Otevřít složku s logem", command=self.on_open_logs).pack(anchor="w")
        self._lbl(p, "Soubor antfan.log pošlete, když chcete poradit s problémem. Token v něm není.",
                  anchor="w").pack(fill="x", pady=(2, 12))
        ttk.Checkbutton(p, text="Simulace (bez donglu a ventilátoru)", variable=self.sim_var,
                        command=self.on_sim_toggle).pack(anchor="w")
        self._lbl(p, f"AntFan {__version__}", fg=FAINT, anchor="w").pack(fill="x", pady=(14, 0))

    # ============================================================ prahy
    def _thr_lists(self, mode):
        c = self.cfg.control
        return (c.power_pct, c.hr_pct) if mode == "relative" else (c.power_thresholds, c.hr_thresholds)

    def _fill_thr_entries(self):
        n = self.cfg.fan.max_level
        pl, hl = self._thr_lists(self._thr_shown)
        step_p, step_h = (15, 8) if self._thr_shown == "relative" else (60, 10)
        pl = (pl + [pl[-1] + step_p * (i + 1) for i in range(n)])[:n]
        hl = (hl + [hl[-1] + step_h * (i + 1) for i in range(n)])[:n]
        for e, v in zip(self.e_pthr, pl):
            e.delete(0, "end")
            e.insert(0, str(v))
        for e, v in zip(self.e_hthr, hl):
            e.delete(0, "end")
            e.insert(0, str(v))
        rel = self._thr_shown == "relative"
        for u in self.lbl_punits:
            u.configure(text="%" if rel else "W")
        for u in self.lbl_hunits:
            u.configure(text="%" if rel else "bpm")
        state = "normal" if rel else "disabled"
        self.e_ftp.configure(state=state)
        self.e_hrmax.configure(state=state)
        self._update_thr_hints()

    def _read_thr_entries(self):
        pth = [int(e.get()) for e in self.e_pthr]
        hth = [int(e.get()) for e in self.e_hthr]
        if pth != sorted(pth) or hth != sorted(hth):
            raise ValueError("Prahy musí stoupat: stupeň 1 < 2 < 3.")
        if min(pth + hth) <= 0:
            raise ValueError("Prahy musí být kladné.")
        return pth, hth

    def _update_thr_hints(self):
        rel = self._thr_shown == "relative"
        try:
            ftp, hrmax = int(self.e_ftp.get()), int(self.e_hrmax.get())
        except ValueError:
            ftp = hrmax = None
        for ep, eh, hp, hh in zip(self.e_pthr, self.e_hthr, self.lbl_phints, self.lbl_hhints):
            if not rel or ftp is None:
                hp.configure(text="")
                hh.configure(text="")
                continue
            try:
                hp.configure(text=f"≈ {round(ftp * int(ep.get()) / 100)} W")
            except ValueError:
                hp.configure(text="")
            try:
                hh.configure(text=f"≈ {round(hrmax * int(eh.get()) / 100)} bpm")
            except ValueError:
                hh.configure(text="")

    def on_thr_mode(self):
        new = self.thr_mode.get()
        if new == self._thr_shown:
            return
        try:  # zapamatovat hodnoty původního režimu
            pth, hth = self._read_thr_entries()
            pl, hl = self._thr_lists(self._thr_shown)
            pl[:], hl[:] = pth, hth
        except ValueError:
            pass
        self._thr_shown = new
        self._fill_thr_entries()
        self.on_apply()

    def on_source(self, key):
        self.source_mode = key
        self._update_cards()
        self.on_apply()

    def _update_cards(self):
        for k, card in self.mode_cards.items():
            card.set_selected(k == self.source_mode)

    def _schedule_apply(self):
        self._update_thr_hints()
        if self._apply_job is not None:
            self.root.after_cancel(self._apply_job)
        self._apply_job = self.root.after(700, self.on_apply)

    def on_apply(self) -> bool:
        self._apply_job = None
        c = self.cfg.control
        n = self.cfg.fan.max_level
        try:
            pth, hth = self._read_thr_entries()
            mode = self.thr_mode.get()
            if mode == "relative":
                if max(pth) > 200 or max(hth) > 100:
                    raise ValueError("Výkon nejvýš 200 % FTP, tep nejvýš 100 % max. tepu.")
                c.power_pct, c.hr_pct = pth, hth
            else:
                c.power_thresholds, c.hr_thresholds = pth, hth
            c.threshold_mode = mode
            c.ftp = max(50, int(self.e_ftp.get()))
            c.hr_max = max(100, min(240, int(self.e_hrmax.get())))
            c.power_hysteresis = int(self.e_physt.get())
            c.hr_hysteresis = int(self.e_hhyst.get())
            c.power_smoothing_s = max(1.0, float(self.e_psmooth.get().replace(",", ".")))
            c.hr_smoothing_s = max(1.0, float(self.e_hsmooth.get().replace(",", ".")))
            c.down_delay_s = max(0.0, float(self.e_delay.get().replace(",", ".")))
            c.cooldown_s = max(0.0, float(self.e_cool_min.get().replace(",", ".")) * 60)
            c.cooldown_level = max(0, min(n, int(self.e_cool_lvl.get())))
            c.no_data_level = max(0, min(n, int(self.e_nodata_lvl.get())))
            c.no_data_s = max(5.0, float(self.e_nodata_s.get().replace(",", ".")))
            vitr_ui.read_control_section(self, c)
            c.lead_s = max(1.0, min(10.0, float(self.e_lead_s.get().replace(",", "."))))
            c.lead_enabled = self.lead_var.get()
        except ValueError as e:
            msg = str(e) if "Prahy" in str(e) or "nejvýš" in str(e) or "km/h" in str(e) else "Zadejte čísla."
            self.lbl_ctrl_err.configure(text=f"Neuloženo: {msg}")
            self.lbl_beh_err.configure(text=f"Neuloženo: {msg}")
            return False
        c.source_mode = self.source_mode
        config_mod.save(self.cfg)
        self.lbl_ctrl_err.configure(text="")
        self.lbl_beh_err.configure(text="")
        self._update_thr_hints()
        return True

    # ============================================================ backendy
    def _make_backend(self):
        if self.backend is not None:
            try:
                self.backend.shutdown()
            except Exception:  # noqa: BLE001
                log.exception("shutdown")
        self.backend = SimulatedBackend(self.events) if self.sim_var.get() else AntBackend(self.events)

    def _fan_driver(self, f):
        """Vytvoří ovladač podle typu; vyhodí výjimku s hláškou pro uživatele."""
        if f.kind == "shelly":
            return ShellyFan(f)
        if f.kind == "homeassistant":
            return HomeAssistantFan(f)
        if not (f.ip and f.token):
            raise FanError("Zadejte IP adresu a token ventilátoru, nebo je získejte z účtu Xiaomi.")
        return XiaomiFan(f)

    def _make_fan(self):
        f = self.cfg.fan
        if self.sim_var.get():
            self.fan_worker.configure(SimulatedFan(f))
            self._set_fan_status("simulovaný ventilátor", True)
            return
        try:
            self.fan_worker.configure(self._fan_driver(f))
            self._set_fan_status("připojuji…", True)
        except (MiioError, FanError, ValueError) as e:
            self.fan_worker.configure(None)
            self._set_fan_status(str(e), False)

    def _set_fan_status(self, text, ok):
        self.fan_status_text, self.fan_ok = text, ok
        self.lbl_fan_status.configure(text=text, fg=OK if ok else BAD)
        m = self.cfg.fan.model
        if m and self.cfg.fan.kind == "xiaomi":
            self.lbl_fan_model.configure(text=f"Model: {m}")

    # ============================================================ akce
    def on_run_toggle(self):
        if self.backend.state in ("monitoring", "unplugged"):
            self.on_stop()
        else:
            self.on_start()

    def on_scan(self):
        for k in [k for k in self.devices if k not in self.selected]:
            del self.devices[k]
        self._ant_error = False
        self._refresh_tree()
        self.controller.reset()
        self.backend.start_scan(self.cfg.scan_duration_s)

    def on_start(self):
        devs = [self.devices[k] for k in self.selected if k in self.devices]
        if not devs:
            self.open_settings("sensors")
            self.lbl_sensor_hint.configure(text="Nejdřív vyhledejte senzory a kliknutím vyberte "
                                                "tepový pás a trenažér nebo powermetr.")
            return
        self._ant_error = False
        self.controller.reset()
        self.history.clear()
        self.drink.reset()
        self.backend.start_monitor(devs)

    def on_stop(self):
        self.backend.stop()

    def on_reset(self):
        self.backend.reset()

    def on_open_logs(self):
        d = str(config_mod.app_dir())
        try:
            if sys.platform == "win32":
                os.startfile(d)  # noqa: S606
            else:
                subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", d])
        except Exception as e:  # noqa: BLE001
            messagebox.showinfo("AntFan", f"Log je ve složce:\n{d}\n\n({e})")

    def on_sim_toggle(self):
        self.cfg.simulation = self.sim_var.get()
        config_mod.save(self.cfg)
        self.devices = {k: v for k, v in self.devices.items() if k in self.selected}
        self._make_backend()
        self._make_fan()
        self._refresh_tree()

    def on_tree_click(self, event):
        iid = self.tree.identify_row(event.y)
        if not iid:
            return
        dev_id, dev_type = (int(x) for x in iid.split(":"))
        key = (dev_id, dev_type)
        if key in self.selected:
            self.selected.discard(key)
        elif len(self.selected) >= MAX_CHANNELS:
            self.lbl_sensor_hint.configure(text=f"Najednou nejvýš {MAX_CHANNELS} senzorů.")
            return
        else:
            self.selected.add(key)
        self.cfg.selected = [[k[0], k[1], self.devices[k].trans_type] for k in self.selected if k in self.devices]
        config_mod.save(self.cfg)
        self._refresh_tree()

    def on_fan_save(self):
        f = self.cfg.fan

        def num(w, lo, hi, default):
            try:
                return max(lo, min(hi, int(w.get())))
            except ValueError:
                return default

        f.kind = self.fan_kind.get()
        ip, token = self.e_ip.get().strip(), self.e_token.get().strip()
        if (ip, token) != (f.ip, f.token):
            f.model = ""
        f.ip, f.token = ip, token
        f.mute_buzzer = self.mute_var.get()
        f.light_off = self.light_var.get()
        f.shelly_host = self.e_shelly.get().strip()
        f.shelly_channel = num(self.sp_shelly_ch, 0, 3, 0)
        f.ha_url = self.e_ha_url.get().strip()
        f.ha_token = self.e_ha_token.get().strip()
        f.ha_entity = self.e_ha_entity.get().strip()
        f.on_level = num(self.sp_on_level_s if f.kind == "shelly" else self.sp_on_level_h, 1, 5, 1)
        levels = num(self.sp_levels, 1, 5, 3)
        restart_needed = levels != f.max_level
        f.max_level = levels
        config_mod.save(self.cfg)
        self._make_fan()
        if restart_needed:
            messagebox.showinfo("AntFan", "Počet stupňů se projeví po restartu programu.")

    def on_fan_test(self):
        self.on_fan_save()
        if self.sim_var.get():
            self._set_fan_status("Simulace: OK", True)
            return
        f = self.cfg.fan

        def run():
            try:
                fan = self._fan_driver(f)
                info = fan.info()
                power, level = fan.get_state()
                note = getattr(fan, "note", None)
                msg = (f"Ventilátor odpovídá: {info.get('model', '?')} (firmware {info.get('fw_ver', '?')}), "
                       f"{'zapnutý' if power else 'vypnutý'}, stupeň {level if power else 0}."
                       + (f" Ovládání: {note}." if note else ""))
                if f.kind == "xiaomi" and info.get("model"):
                    f.model = str(info["model"])
                    config_mod.save(self.cfg)
                self.events.put(("fan", True, msg, level if power else 0))
            except Exception as e:  # noqa: BLE001
                self.events.put(("fan", False, str(e), None))

        threading.Thread(target=run, daemon=True).start()
        self._set_fan_status("Zkouším spojení…", True)

    def on_segment(self, key):
        if key == "auto":
            self.auto_var.set(True)
        else:
            self.auto_var.set(False)
            self.manual_level = int(key)
        self.cfg.auto_mode = self.auto_var.get()
        config_mod.save(self.cfg)
        self._update_segment()

    def _update_segment(self):
        self.seg.set("auto" if self.auto_var.get() else self.manual_level)

    # ============================================================ mobil
    def _web_sync(self):
        """Spustí nebo zastaví server podle nastavení."""
        c = self.cfg
        self.web_error = ""
        if self.web_on:
            if not c.web_key:
                c.web_key = web.new_key()
                config_mod.save(c)
            self.web.key = c.web_key
            if not (self.web.running and self.web.port == c.web_port):
                try:
                    self.web.start(c.web_port, c.web_key)
                except OSError as e:
                    log.warning("Web pro mobil nejde spustit: %s", e)
                    self.web_error = f"Port {c.web_port} nejde použít (obsazený?). Zvolte jiný."
                    self.web_on = False
        else:
            self.web.stop()
        self._web_refresh_page()

    def _web_url(self) -> str:
        return web.page_url(web.lan_ip(), self.web.port, self.web.key) if self.web.running else ""

    def _web_refresh_page(self):
        if hasattr(self, "btn_web"):  # hlavní okno
            self.btn_web.configure(text="Vypnout mobil" if self.web.running else "Zapnout mobil")
            if self.web.running:
                self.st_web.set("Mobil zapnutý", OK)
            elif self.web_error:
                self.st_web.set("Mobil: chyba", BAD)
            else:
                self.st_web.set("", BG)
        if not hasattr(self, "lbl_web_status"):
            return
        self.web_var.set(self.web.running)
        url = self._web_url()
        if self.web_error:
            text, col = self.web_error, BAD
        elif url:
            text, col = f"Běží na portu {self.web.port}. Otevřete adresu v telefonu nebo načtěte QR kód.", OK
        else:
            text, col = "Vypnuto.", MUTED
        self.lbl_web_status.configure(text=text, fg=col)
        self.e_web_url.configure(state="normal")
        self.e_web_url.delete(0, "end")
        self.e_web_url.insert(0, url)
        self.e_web_url.configure(state="readonly")
        self._draw_qr(url)

    def _draw_qr(self, url):
        cv = self.qr_canvas
        cv.delete("all")
        if not url:
            cv.configure(width=1, height=1)
            return
        try:
            m = qr.encode(url)
        except ValueError:
            cv.configure(width=1, height=1)
            return
        cell = max(2, int(3 * self.px))
        quiet = 4
        side = (len(m) + 2 * quiet) * cell
        cv.configure(width=side, height=side)
        cv.create_rectangle(0, 0, side, side, fill="#ffffff", outline="")  # QR vždy tmavé na bílém
        for y, row in enumerate(m):
            for x, dark in enumerate(row):
                if dark:
                    x0, y0 = (x + quiet) * cell, (y + quiet) * cell
                    cv.create_rectangle(x0, y0, x0 + cell, y0 + cell, fill="#000000", outline="")

    def on_web_toggle(self):
        self.web_on = self.web_var.get()
        self._web_sync()

    def on_web_button(self):
        """Tlačítko Mobil v hlavním okně: zapne/vypne server pro tento běh programu."""
        first = not self.cfg.web_key
        self.web_on = not self.web.running
        self._web_sync()
        if self.web_error or (self.web_on and first):  # poprvé ukázat QR kód, při chybě důvod
            self.open_settings("mobile")

    def on_web_autostart(self):
        self.cfg.web_autostart = self.web_auto_var.get()
        config_mod.save(self.cfg)

    def on_web_port(self):
        try:
            port = int(self.e_web_port.get())
            if not 1024 <= port <= 65535:
                raise ValueError
        except ValueError:
            self.lbl_web_status.configure(text="Port musí být číslo 1024–65535.", fg=BAD)
            return
        if port != self.cfg.web_port:
            self.cfg.web_port = port
            config_mod.save(self.cfg)
            self._web_sync()

    def on_web_new_key(self):
        self.cfg.web_key = web.new_key()
        config_mod.save(self.cfg)
        self._web_sync()

    def on_web_copy(self):
        url = self._web_url()
        if not url:
            self.lbl_web_status.configure(text="Nejdřív ovládání z mobilu povolte.", fg=BAD)
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(url)
        self.lbl_web_status.configure(text="Adresa zkopírována.", fg=OK)

    def _web_publish(self, desired, reason, status, status_col):
        """Snímek stavu pro server (volá _tick v hlavním vlákně)."""
        now = time.monotonic()
        if not self.web.running or now - self._web_last < 0.5:
            return
        self._web_last = now
        ctrl = self.controller
        try:
            rxq = self.backend.rx_quality() if self.backend is not None else {}
        except Exception:  # noqa: BLE001
            rxq = {}
        rx = []
        for key, q in rxq.items():
            d = self.devices.get(key)
            rx.append({"name": d.type_name if d else str(key[0]), "q": q})
        hint = self.lbl_ride_hint.cget("text")
        if not self.sim_var.get() and not self.fan_ok:
            hint = ("Ventilátor nepřipojen. " + hint).strip()
        p = ctrl.power_smoothed
        self.web.publish({
            "power": None if p is None else round(p),
            "power_label": self.t_power["head"].cget("text"),
            "power_sub": self.t_power["sub"].cget("text"),
            "power_bad": bool(ctrl.power_gap_s),
            "hr": ctrl.hr_now,
            "hr_sub": self.t_hr["sub"].cget("text"),
            "level": desired,
            "reason": reason,
            "auto": self.auto_var.get(),
            "manual": self.manual_level,
            "max_level": self.cfg.fan.max_level,
            "status": status,
            "status_color": {OK: "ok", BAD: "bad", ACCENT: "accent"}.get(status_col, "faint"),
            "rx": rx,
            "hint": hint,
            "drink": None if self.drink.current is None else
            {"id": self.drink.current.id, "text": self.drink.current.text, "ml": self.drink.current.ml},
        })

    # ============================================================ pití
    def _build_drink_strip(self, r):
        # holý rámeček bez obsahu nezabírá místo; pruh se do něj vkládá jen při připomínce
        self.drink_box = tk.Frame(r, bg=BG)
        self.drink_box.pack(fill="x", padx=12)
        self.lbl_drink = tk.Label(self.drink_box, text="", bg=ACCENT_BG, fg=ACCENT, font=self.fonts.body,
                                  anchor="w", padx=10, pady=4, cursor="hand2")
        self.lbl_drink.bind("<Button-1>", lambda e: self.on_drink_dismiss())
        self._drink_shown = None

    def _page_drink(self, p):
        self._page_head(p, "Pití", "Nenápadná připomínka pod grafem během jízdy. Interval a množství "
                                   "se řídí délkou jízdy, výkonem a teplotou v místnosti.")
        self.drink_var = tk.BooleanVar(value=self.cfg.drink_enabled)
        ttk.Checkbutton(p, text="Připomínat pití", variable=self.drink_var,
                        command=self._drink_apply).pack(anchor="w")
        g = tk.Frame(p, bg=BG)
        g.pack(fill="x", pady=(8, 0))
        t = self.cfg.drink_temp_c
        rows = (("Teplota v místnosti", "" if t is None else f"{t:g}", "°C, prázdné = nepočítat", "e_drink_temp"),
                ("Interval", f"{self.cfg.drink_interval_min:g}" if self.cfg.drink_interval_min else "",
                 "min, prázdné = automaticky", "e_drink_int"))
        for i, (label, val, unit, attr) in enumerate(rows):
            ttk.Label(g, text=label).grid(row=i, column=0, sticky="w", pady=2)
            e = ttk.Entry(g, width=6, justify="center")
            e.insert(0, val)
            e.grid(row=i, column=1, sticky="w", padx=10, pady=2)
            e.bind("<KeyRelease>", lambda ev: self._drink_schedule())
            e.bind("<FocusOut>", lambda ev: self._drink_apply())
            self._lbl(g, unit).grid(row=i, column=2, sticky="w")
            setattr(self, attr, e)
        self.lbl_drink_err = self._lbl(p, "", fg=BAD, font=self.fonts.body, anchor="w")
        self.lbl_drink_err.pack(fill="x", pady=(8, 0))
        self.lbl_drink_now = self._lbl(p, "", font=self.fonts.body, anchor="w")
        self.lbl_drink_now.pack(fill="x")
        self._lbl(p, "Počítá jen během měření, když šlapete. Základ je zhruba 500 ml za hodinu, při vyšším "
                     "výkonu až 750 ml, nad 22 °C víc. Jen orientační hodnoty, řiďte se i žízní. "
                     "Připomínka zmizí kliknutím nebo po minutě.",
                  anchor="w", justify="left", wraplength=int(440 * self.px)).pack(fill="x", pady=(4, 0))

    def _drink_schedule(self):
        if self._drink_job is not None:
            self.root.after_cancel(self._drink_job)
        self._drink_job = self.root.after(700, self._drink_apply)

    def _drink_apply(self):
        self._drink_job = None
        try:
            if not self.e_drink_temp.winfo_exists():
                return
            temp = drink.parse_temp(self.e_drink_temp.get())
            interval = drink.parse_interval(self.e_drink_int.get())
        except ValueError as e:
            self.lbl_drink_err.configure(text=f"Neuloženo: {e}" if "–" in str(e) else "Neuloženo: Zadejte čísla.")
            return
        except tk.TclError:
            return
        changed = (interval, temp) != (self.cfg.drink_interval_min, self.cfg.drink_temp_c)
        self.cfg.drink_enabled = self.drink_var.get()
        self.cfg.drink_temp_c, self.cfg.drink_interval_min = temp, interval
        config_mod.save(self.cfg)
        self.lbl_drink_err.configure(text="")
        d = self.drink
        d.temp_c, d.manual_min = temp, interval
        if d.enabled != self.cfg.drink_enabled or changed:
            d.reschedule()
        d.enabled = self.cfg.drink_enabled

    def on_drink_dismiss(self):
        self.drink.dismiss()
        self._drink_show(None)

    def _drink_show(self, rem):
        rid = rem.id if rem else None
        if rid == self._drink_shown:
            return
        self._drink_shown = rid
        if rem is None:
            self.lbl_drink.pack_forget()
            self.drink_box.configure(height=1)  # bez potomků by si Tk nechal poslední výšku
        else:
            self.lbl_drink.configure(text=rem.text)
            self.lbl_drink.pack(fill="x", pady=(0, 6))

    def _drink_tick(self, now):
        ctrl = self.controller
        rem = self.drink.update(now, self.backend.state == "monitoring", ctrl.power_now,
                                ctrl.cadence_now, ctrl.hr_now)
        self._drink_show(rem)
        txt = ("Teď: " + self.drink.summary()) if self.drink.enabled else ""
        if self.lbl_drink_now.cget("text") != txt:
            self.lbl_drink_now.configure(text=txt)

    # ============================================================ smyčka
    def _poll_events(self):
        tree_dirty = False
        try:
            while True:
                ev = self.events.get_nowait()
                kind = ev[0]
                if kind == "ant_status":
                    self.ant_status_full = ev[1]
                    self.lbl_scan.configure(text=ev[1] if self.backend.state == "scanning" or
                                            "Vyhledávání" in ev[1] else "")
                elif kind == "ant_error":
                    self._ant_error = True
                    self.ant_status_full = ev[1]
                    messagebox.showerror("ANT+", ev[1])
                elif kind == "found":
                    d: FoundDevice = ev[1]
                    old = self.devices.get(d.key)
                    if old is not None and d.trans_type == 0:
                        d.trans_type = old.trans_type
                    self.devices[d.key] = d
                    if d.last_value is not None:
                        self.dev_values[d.key] = (time.monotonic(), d.last_value)
                    tree_dirty = True
                elif kind == "value":
                    _, key, vkind, value, cad = ev
                    now = time.monotonic()
                    if vkind == "speed":  # rychlost jízdy (vítr), ne do seznamu senzorů
                        self.controller.feed(vkind, value)
                        continue
                    self.dev_values[key] = (now, value)
                    if key[1] == PM_TYPE:
                        self._last_pm_value = now
                    # powermetr má přednost před trenažérem (je přesnější)
                    if not (key[1] == FE_TYPE and now - self._last_pm_value < 3.0):
                        self.controller.feed(vkind, value, cad)
                    tree_dirty = True
                elif kind == "scan_done":
                    tree_dirty = True
                elif kind == "fan":
                    _, ok, text, actual = ev
                    if actual is not None:
                        self.fan_actual = actual
                    self._set_fan_status(text, ok)
                elif kind == "web_level":  # z mobilu, stejně jako kliknutí na přepínač
                    self.on_segment(ev[1])
        except queue.Empty:
            pass
        # seznam stačí překreslit max. 2× za s (hodnoty chodí ~4× za s od každého senzoru)
        if tree_dirty and time.monotonic() - getattr(self, "_last_tree", 0.0) >= 0.5:
            self._last_tree = time.monotonic()
            self._refresh_tree()
        self.root.after(100, self._poll_events)

    def _refresh_tree(self):
        now = time.monotonic()
        existing = set(self.tree.get_children())
        try:
            rxq = self.backend.rx_quality() if self.backend is not None else {}
        except Exception:  # noqa: BLE001
            rxq = {}
        weak = []
        order = sorted(self.devices.values(), key=lambda d: (d.key not in self.selected, d.device_type != HR_TYPE, d.device_id))
        for idx, d in enumerate(order):
            iid = f"{d.device_id}:{d.device_type}"
            tv = self.dev_values.get(d.key)
            if tv and now - tv[0] < 5:
                unit = "bpm" if d.device_type == HR_TYPE else "W"
                val = f"{tv[1]} {unit}"
            else:
                val = "–"
            q = rxq.get(d.key)
            rx_txt = "" if d.key not in rxq else ("…" if q is None else f"{q} %")
            tags = ()
            if q is not None and q < 80:
                tags = ("weak",)
                weak.append(f"{d.type_name} #{d.device_id} ({q} %)")
            values = ("☑" if d.key in self.selected else "☐", d.type_name, d.device_id, val, rx_txt)
            if iid in existing:
                self.tree.item(iid, values=values, tags=tags)
                self.tree.move(iid, "", idx)
                existing.discard(iid)
            else:
                self.tree.insert("", idx, iid=iid, values=values, tags=tags)
        for iid in existing:
            self.tree.delete(iid)

        # příjem v okně jízdy
        items = []
        for key, q in rxq.items():
            d = self.devices.get(key)
            name = d.type_name if d else str(key[0])
            items.append((f"{name}  {'…' if q is None else f'{q} %'}", BAD if q is not None and q < 80 else MUTED))
        while len(self.rx_labels) < len(items):
            lb = self._lbl(self.rx_box, "", font=self.fonts.body)
            lb.pack(side="left", padx=(14, 0))
            self.rx_labels.append(lb)
        for i, lb in enumerate(self.rx_labels):
            if i < len(items):
                lb.configure(text=items[i][0], fg=items[i][1])
            else:
                lb.configure(text="")

        hints = []
        try:
            all_n, single = self.backend.rx_diagnosis() if self.backend is not None else (0, {})
        except Exception:  # noqa: BLE001
            all_n, single = 0, {}
        if all_n >= 2:
            hints.append(f"Výpadky na všech senzorech zároveň ({all_n}× za 5 min). Příčina je v PC: "
                         "zkuste jiný USB port (USB 2.0, ne hub), prodlužovačku nebo jiný dongle.")
        if single:
            who = ", ".join(f"{k} {n}×" for k, n in single.items())
            hints.append(f"Vypadává jen {who} za 5 min, ostatní senzory jdou. Příčina je u senzoru: "
                         "Bluetooth spojení s Rouvy, baterie, kontakt pásu.")
        if weak and not hints:
            hints.append("Slabý příjem: " + ", ".join(weak) + ". Dejte dongle blíž ke kolu.")
        text = "\n".join(hints)
        if self.lbl_ride_hint.cget("text") != text:
            self.lbl_ride_hint.configure(text=text)
        if self.lbl_sensor_hint.cget("text") != text and (text or self.lbl_sensor_hint.cget("fg") == BAD):
            self.lbl_sensor_hint.configure(text=text)
        if rxq:
            self.lbl_diag_rx.configure(text=text or "Bez výpadků za posledních 5 minut.")
        else:
            self.lbl_diag_rx.configure(text="Měření neběží.")

    def _status_short(self):
        st = self.backend.state
        n = len(self.selected)
        if st == "monitoring":
            return f"Měřím · {n} {_plural_senzor(n)}", OK
        if st == "scanning":
            return "Hledám senzory…", ACCENT
        if st == "unplugged":
            return "Dongle odpojen", BAD
        if self._ant_error:
            return "Chyba ANT+", BAD
        return ("Simulace" if self.sim_var.get() else "Připraveno"), FAINT

    def _reason_text(self, ctrl, desired):
        c = self.cfg.control
        n = self.cfg.fan.max_level
        if not self.auto_var.get():
            return "ručně"
        if self.backend.state != "monitoring":
            return "čeká na měření"
        r = ctrl.reason
        pl, hl = c.power_levels()[:n], c.hr_levels()[:n]
        if ctrl.pct is not None:
            return r
        if r == "předstih" and pl:
            return f"předstih · výkon nad {pl[desired - 1]} W" if desired > 0 else r
        if r == "výkon" and pl:
            return f"výkon nad prahem {pl[desired - 1]} W" if desired > 0 else f"výkon pod prahem {pl[0]} W"
        if r == "tep" and hl:
            return f"tep nad prahem {hl[desired - 1]} bpm" if desired > 0 else f"tep pod prahem {hl[0]} bpm"
        return r

    def _tick(self):
        now = time.monotonic()
        ctrl = self.controller
        auto_level = ctrl.tick(now)
        desired = auto_level if self.auto_var.get() else self.manual_level
        if self.backend.state == "monitoring" or not self.auto_var.get():
            self.fan_worker.set_desired(desired, ctrl.pct if self.auto_var.get() else None)
        else:
            self.fan_worker.set_desired(None)

        c = self.cfg.control
        p = ctrl.power_smoothed
        self.t_power["big"].configure(text="–" if p is None else f"{p:.0f}")
        self.t_power["head"].configure(text=f"Výkon · průměr {c.power_smoothing_s:g} s")
        sub = []
        if p is not None and c.ftp:
            sub.append(f"{p / c.ftp * 100:.0f} % FTP")
        if ctrl.cadence_now:
            sub.append(f"{ctrl.cadence_now} rpm")
        if ctrl.power_gap_s:
            sub.append(f"výpadek příjmu {ctrl.power_gap_s:.0f} s")
        self.t_power["sub"].configure(text=" · ".join(sub), fg=BAD if ctrl.power_gap_s else MUTED)
        self.t_hr["big"].configure(text="–" if ctrl.hr_now is None else str(ctrl.hr_now))
        self.t_hr["sub"].configure(text="" if ctrl.hr_now is None or not c.hr_max else
                                   f"{ctrl.hr_now / c.hr_max * 100:.0f} % max")
        if not vitr_ui.update_fan_tile(self, desired):  # výstup v % kreslí vitr_ui
            self.t_fan["big"].configure(text="Vyp" if desired == 0 else str(desired))
            self._draw_bars(desired)
            reason = self._reason_text(ctrl, desired)
            if self.fan_actual is not None and self.fan_worker is not None and self.fan_actual != desired \
                    and (self.backend.state == "monitoring" or not self.auto_var.get()):
                reason += f" · ventilátor zatím na {'Vyp' if self.fan_actual == 0 else self.fan_actual}"
            self.t_fan["sub"].configure(text=reason)

        text, col = self._status_short()
        self.st_ant.set(text, col)
        if self.sim_var.get():
            self.st_fan.set("Simulovaný ventilátor", FAINT)
        else:
            self.st_fan.set("Ventilátor připojen" if self.fan_ok else "Ventilátor nepřipojen",
                            OK if self.fan_ok else BAD)
        running = self.backend.state in ("monitoring", "unplugged")
        want = "Zastavit" if running else "Spustit měření"
        if self.btn_run.cget("text") != want:
            self.btn_run.configure(text=want)
        self.lbl_diag_status.configure(text=self.ant_status_full)
        self._update_segment()
        self._drink_tick(now)
        self.overlay.tick(now)
        self._web_publish(desired, reason, text, col)

        if now - self._last_hist >= 1.0:
            self._last_hist = now
            self.history.append((ctrl.power_smoothed, ctrl.hr_smoothed, vitr_ui.fan_fraction(self, desired)))
            self._draw_chart()
            self._refresh_tree()
        self.root.after(250, self._tick)

    def _draw_chart(self):
        cv = self.canvas
        cv.delete("all")
        w, h = cv.winfo_width(), cv.winfo_height()
        if w < 80 or h < 60:
            return
        s = self.px
        pad_l, pad_r, pad_t, pad_b = int(36 * s), int(64 * s), int(8 * s), int(6 * s)
        pw, ph = w - pad_l - pad_r, h - pad_t - pad_b
        hist = list(self.history)
        n_lvl = max(1, self.cfg.fan.max_level)
        thr = self.cfg.control.power_levels()[:n_lvl]
        p_max = max([300, (max(thr) * 1.25 if thr else 0)] + [p for p, _, _ in hist if p is not None])
        p_max = int((p_max + 49) // 50 * 50)
        hr_lo, hr_hi = 60, 200

        def x_of(i):
            return pad_l + pw * (HISTORY_S - len(hist) + i) / (HISTORY_S - 1)

        def yp(v):
            return pad_t + ph * (1 - max(0.0, min(1.0, v / p_max)))

        # pozadí = stupeň ventilátoru (souvislé úseky)
        i = 0
        while i < len(hist):
            lvl = hist[i][2]
            j = i
            while j + 1 < len(hist) and hist[j + 1][2] == lvl:
                j += 1
            if lvl:  # podíl 0..1 (stupeň / počet stupňů, nebo % / 100)
                y0 = pad_t + ph * (1 - min(1.0, lvl))
                cv.create_rectangle(x_of(i), y0, x_of(j) + pw / HISTORY_S + 1, pad_t + ph,
                                    fill=FAN_BAND, outline="")
            i = j + 1
        # osa výkonu
        for v in (0, p_max // 2, p_max):
            cv.create_text(pad_l - 6, yp(v), text=str(v), anchor="e", fill=FAINT, font=self.fonts.chart)
        cv.create_line(pad_l, pad_t + ph, pad_l + pw, pad_t + ph, fill=BORDER)
        # prahy stupňů
        for k, v in enumerate(thr):
            y = yp(v)
            cv.create_line(pad_l, y, pad_l + pw, y, fill=FAINT, dash=(3, 3))
            cv.create_text(pad_l + pw + 6, y, text=f"{k + 1} · {v} W", anchor="w", fill=MUTED,
                           font=self.fonts.chart)

        def line(idx, scale, color):
            pts = []
            for i2, row in enumerate(hist):
                v = row[idx]
                if v is None:
                    if len(pts) >= 4:
                        cv.create_line(*pts, fill=color, width=max(1, int(2 * s)))
                    pts = []
                    continue
                pts += [x_of(i2), pad_t + ph * (1 - max(0.0, min(1.0, scale(v))))]
            if len(pts) >= 4:
                cv.create_line(*pts, fill=color, width=max(1, int(2 * s)))

        line(0, lambda v: v / p_max, POWER)
        line(1, lambda v: (v - hr_lo) / (hr_hi - hr_lo), HR)

    # ============================================================ konec
    def _cleanup(self):
        """Uvolní dongle – volá se při zavření okna i při ukončení procesu."""
        if getattr(self, "_cleaned", False):
            return
        self._cleaned = True
        try:
            self.web.stop()
            self.fan_worker.stop()
            self.backend.shutdown()
        except Exception:  # noqa: BLE001
            log.exception("Chyba při ukončování")

    def _on_close(self):
        try:
            self.st_ant.set("Uvolňuji dongle…", FAINT)
            self.root.update_idletasks()
            self._cleanup()
        finally:
            self.root.destroy()


def _check_single_instance(inst: SingleInstance) -> bool:
    """Když už AntFan běží (třeba zaseknutý na pozadí), nabídne jeho ukončení."""
    if inst.acquire():
        return True
    root = tk.Tk()
    root.withdraw()
    pid = inst.other_pid()
    procs = usb_diag.list_processes()
    verified = pid is not None and any(
        p == pid and usb_diag.is_antfan_process(n, c) for p, n, c in procs)
    if not verified:
        messagebox.showwarning(
            "AntFan už běží",
            f"AntFan už běží. Pokud jeho okno nevidíte, ukončete ho {usb_diag.task_manager_hint()} "
            "a spusťte program znovu.")
        root.destroy()
        return False
    if not messagebox.askyesno(
            "AntFan už běží",
            f"AntFan už běží (PID {pid}). Pokud jeho okno nevidíte, nejspíš visí na pozadí "
            "a drží ANT+ dongle – proto pak dongle hlásí, že je připojen k jiné aplikaci.\n\n"
            "Ukončit starou instanci a pokračovat?"):
        root.destroy()
        return False
    usb_diag.kill_process(pid)
    for _ in range(20):
        time.sleep(0.25)
        if inst.acquire():
            root.destroy()
            return True
    messagebox.showerror("AntFan", f"Starou instanci se nepodařilo ukončit. Zkuste {usb_diag.task_manager_name()}.")
    root.destroy()
    return False


def main():
    if "--selftest" in sys.argv:  # kontrola sestaveného exe (GitHub Actions)
        from .selftest import run

        i = sys.argv.index("--selftest")
        sys.exit(run(sys.argv[i + 1] if len(sys.argv) > i + 1 else None))
    setup_logging()
    try:
        from ctypes import windll  # ostré písmo na Windows s HiDPI
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:  # noqa: BLE001
        pass
    inst = SingleInstance()
    if not _check_single_instance(inst):
        return
    root = tk.Tk()
    app = App(root)
    atexit.register(app._cleanup)  # noqa: SLF001
    root.mainloop()


if __name__ == "__main__":
    main()
