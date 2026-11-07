"""GUI aplikace AntFan (tkinter)."""
from __future__ import annotations

import atexit
import logging
import queue
import time
import tkinter as tk
from collections import deque
from logging.handlers import RotatingFileHandler
from tkinter import messagebox, ttk

from . import config as config_mod
from . import usb_diag
from .single_instance import SingleInstance
from .ant_backend import FE_TYPE, HR_TYPE, MAX_CHANNELS, PM_TYPE, AntBackend, FoundDevice, SimulatedBackend
from .controller import SOURCE_MODES, Controller
from .miio_fan import FanWorker, MiioError, SimulatedFan, XiaomiFan

log = logging.getLogger("antfan")

HISTORY_S = 300
COL_POWER = "#e8590c"
COL_HR = "#d6336c"
COL_FAN = "#d0ebff"


def setup_logging():
    path = config_mod.app_dir() / "antfan.log"
    handler = RotatingFileHandler(path, maxBytes=3_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    logging.getLogger("openant").setLevel(logging.WARNING)


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

        for d in self.cfg.selected:
            fd = FoundDevice(d[0], d[1], d[2] if len(d) > 2 else 0)
            self.devices[fd.key] = fd

        self.backend = None
        self.fan_worker = FanWorker(self.events)

        root.title("AntFan – ANT+ řízení ventilátoru")
        self._build_ui()
        self._make_backend()
        self._make_fan()
        self._refresh_tree()
        # velikost okna podle obsahu (na Windows se zvětšením 125–150 % jsou prvky větší)
        root.update_idletasks()
        need_w, need_h = root.winfo_reqwidth(), root.winfo_reqheight()
        scr_w, scr_h = root.winfo_screenwidth(), root.winfo_screenheight() - 60
        w = min(max(int(need_w * 1.12), 1280), scr_w)
        h = min(max(need_h + 40, 800), scr_h)
        root.geometry(f"{w}x{h}")
        root.minsize(min(need_w, scr_w), min(need_h, scr_h))

        root.protocol("WM_DELETE_WINDOW", self._on_close)
        root.after(100, self._poll_events)
        root.after(250, self._tick)

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        style = ttk.Style()
        style.configure("Big.TLabel", font=("Segoe UI", 34, "bold"))
        style.configure("Unit.TLabel", font=("Segoe UI", 11))
        style.configure("Head.TLabel", font=("Segoe UI", 10, "bold"))

        top = ttk.Frame(self.root, padding=(10, 8))
        top.pack(fill="x")
        self.btn_scan = ttk.Button(top, text="🔍 Hledat senzory", command=self.on_scan)
        self.btn_scan.pack(side="left")
        self.btn_start = ttk.Button(top, text="▶ Spustit měření vybraných", command=self.on_start)
        self.btn_start.pack(side="left", padx=6)
        self.btn_stop = ttk.Button(top, text="■ Zastavit", command=self.on_stop)
        self.btn_stop.pack(side="left")
        ttk.Button(top, text="⟲ Reset donglu", command=self.on_reset).pack(side="left", padx=6)
        self.sim_var = tk.BooleanVar(value=self.cfg.simulation)
        ttk.Checkbutton(top, text="Simulace (bez hardwaru)", variable=self.sim_var,
                        command=self.on_sim_toggle).pack(side="right")
        self.ant_status = tk.StringVar(value="Připraveno")
        ttk.Label(top, textvariable=self.ant_status, foreground="#495057").pack(side="left", padx=14)

        main = ttk.Frame(self.root, padding=(10, 0, 10, 10))
        main.pack(fill="both", expand=True)
        main.columnconfigure(0, weight=2, minsize=280)
        main.columnconfigure(1, weight=5, minsize=380)
        main.columnconfigure(2, weight=0)  # nastavení: přirozená šířka
        main.rowconfigure(0, weight=1)

        # --- senzory
        left = ttk.LabelFrame(main, text="Senzory ANT+ (kliknutím vyberte)", padding=6)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        cols = ("sel", "type", "id", "value", "rx")
        self.tree = ttk.Treeview(left, columns=cols, show="headings", selectmode="none")
        for c, t, w in (("sel", "✓", 30), ("type", "Typ", 92), ("id", "ID", 64),
                        ("value", "Hodnota", 72), ("rx", "Příjem", 58)):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor="center" if c != "type" else "w")
        self.tree.tag_configure("weak", foreground="#c92a2a")
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<Button-1>", self.on_tree_click)
        self.rx_hint = tk.StringVar(value="")
        ttk.Label(left, textvariable=self.rx_hint, foreground="#c92a2a",
                  wraplength=300, justify="left").pack(anchor="w", pady=(6, 0))
        ttk.Label(left, text=f"Max. {MAX_CHANNELS} senzorů. Výběr se pamatuje –\n"
                             "příště stačí rovnou „Spustit měření“.",
                  foreground="#868e96").pack(anchor="w", pady=(6, 0))

        # --- živá data
        mid = ttk.LabelFrame(main, text="Živá data", padding=8)
        mid.grid(row=0, column=1, sticky="nsew", padx=(0, 8))
        tiles = ttk.Frame(mid)
        tiles.pack(fill="x")
        for i in range(3):
            tiles.columnconfigure(i, weight=1)
        self.v_power = tk.StringVar(value="–")
        self.v_power_avg = tk.StringVar(value="")
        self.v_hr = tk.StringVar(value="–")
        self.v_hr_avg = tk.StringVar(value="")
        self.v_fan = tk.StringVar(value="–")
        self.v_fan_info = tk.StringVar(value="")
        self._tile(tiles, 0, "VÝKON", self.v_power, "W", self.v_power_avg, COL_POWER)
        self._tile(tiles, 1, "TEP", self.v_hr, "bpm", self.v_hr_avg, COL_HR)
        self._tile(tiles, 2, "VENTILÁTOR", self.v_fan, "stupeň", self.v_fan_info, "#1971c2")
        self.canvas = tk.Canvas(mid, background="white", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, pady=(10, 0))
        self.canvas.bind("<Configure>", lambda e: self._draw_chart())

        # --- nastavení
        right = ttk.Frame(main)
        right.grid(row=0, column=2, sticky="nsew")
        self._build_fan_box(right)
        self._build_control_box(right)

    def _tile(self, parent, col, title, var, unit, sub, color):
        f = ttk.Frame(parent, padding=4)
        f.grid(row=0, column=col, sticky="nsew")
        ttk.Label(f, text=title, style="Head.TLabel", foreground=color).pack(anchor="w")
        row = ttk.Frame(f)
        row.pack(anchor="w")
        ttk.Label(row, textvariable=var, style="Big.TLabel").pack(side="left")
        ttk.Label(row, text=unit, style="Unit.TLabel").pack(side="left", padx=(4, 0), pady=(14, 0))
        ttk.Label(f, textvariable=sub, foreground="#868e96").pack(anchor="w")

    def _build_fan_box(self, parent):
        box = ttk.LabelFrame(parent, text="Xiaomi Smart Fan 2 Lite", padding=8)
        box.pack(fill="x")
        box.columnconfigure(1, weight=1)
        ttk.Label(box, text="IP adresa").grid(row=0, column=0, sticky="w")
        self.e_ip = ttk.Entry(box)
        self.e_ip.insert(0, self.cfg.fan.ip)
        self.e_ip.grid(row=0, column=1, sticky="ew", pady=2)
        ttk.Label(box, text="Token").grid(row=1, column=0, sticky="w")
        self.e_token = ttk.Entry(box, show="•")
        self.e_token.insert(0, self.cfg.fan.token)
        self.e_token.grid(row=1, column=1, sticky="ew", pady=2)
        ttk.Label(box, text="Počet stupňů").grid(row=2, column=0, sticky="w")
        self.sp_levels = ttk.Spinbox(box, from_=1, to=5, width=5)
        self.sp_levels.set(self.cfg.fan.max_level)
        self.sp_levels.grid(row=2, column=1, sticky="w", pady=2)
        quiet = ttk.Frame(box)
        quiet.grid(row=3, column=0, columnspan=2, sticky="w")
        self.mute_var = tk.BooleanVar(value=self.cfg.fan.mute_buzzer)
        self.light_var = tk.BooleanVar(value=self.cfg.fan.light_off)
        ttk.Checkbutton(quiet, text="Vypnout pípání", variable=self.mute_var,
                        command=self.on_fan_save).pack(side="left")
        ttk.Checkbutton(quiet, text="Vypnout podsvícení", variable=self.light_var,
                        command=self.on_fan_save).pack(side="left", padx=8)
        bf = ttk.Frame(box)
        bf.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        ttk.Button(bf, text="Uložit a připojit", command=self.on_fan_save).pack(side="left")
        ttk.Button(bf, text="Test", command=self.on_fan_test).pack(side="left", padx=6)
        self.fan_status = tk.StringVar(value="nepřipojeno")
        self.lbl_fan_status = ttk.Label(box, textvariable=self.fan_status, foreground="#868e96",
                                        wraplength=260)
        self.lbl_fan_status.grid(row=5, column=0, columnspan=2, sticky="w", pady=(4, 0))

    def _build_control_box(self, parent):
        c = self.cfg.control
        box = ttk.LabelFrame(parent, text="Řízení ventilátoru", padding=8)
        box.pack(fill="both", expand=True, pady=(8, 0))

        mode = ttk.Frame(box)
        mode.pack(fill="x")
        self.auto_var = tk.BooleanVar(value=self.cfg.auto_mode)
        ttk.Radiobutton(mode, text="Automaticky", variable=self.auto_var, value=True,
                        command=self.on_mode).pack(side="left")
        ttk.Radiobutton(mode, text="Ručně", variable=self.auto_var, value=False,
                        command=self.on_mode).pack(side="left", padx=8)
        man = ttk.Frame(box)
        man.pack(fill="x", pady=(4, 6))
        self.manual_buttons = []
        for lvl in range(self.cfg.fan.max_level + 1):
            b = ttk.Button(man, text="Vyp" if lvl == 0 else str(lvl), width=4,
                           command=lambda l=lvl: self.on_manual(l))
            b.pack(side="left", padx=1)
            self.manual_buttons.append(b)

        ttk.Label(box, text="Řídit podle").pack(anchor="w")
        self.cb_source = ttk.Combobox(box, values=list(SOURCE_MODES.values()), state="readonly")
        self.cb_source.set(SOURCE_MODES.get(c.source_mode, SOURCE_MODES["smart"]))
        self.cb_source.pack(fill="x", pady=(0, 6))
        self.cb_source.bind("<<ComboboxSelected>>", lambda e: self.on_apply())

        nb = ttk.Notebook(box)
        nb.pack(fill="both", expand=True)
        tab_thr = ttk.Frame(nb, padding=6)
        tab_beh = ttk.Frame(nb, padding=6)
        nb.add(tab_thr, text="Prahy")
        nb.add(tab_beh, text="Chování")

        # --- záložka Prahy
        self.thr_mode = tk.StringVar(value=c.threshold_mode)
        tm = ttk.Frame(tab_thr)
        tm.pack(fill="x")
        ttk.Radiobutton(tm, text="% FTP / % max. tepu", variable=self.thr_mode, value="relative",
                        command=self.on_thr_mode).pack(side="left")
        ttk.Radiobutton(tm, text="W / bpm", variable=self.thr_mode, value="absolute",
                        command=self.on_thr_mode).pack(side="left", padx=8)
        base = ttk.Frame(tab_thr)
        base.pack(fill="x", pady=(4, 0))
        ttk.Label(base, text="FTP (W)").grid(row=0, column=0, sticky="w")
        self.e_ftp = self._num_entry(base, c.ftp, 0, 1)
        ttk.Label(base, text="Max. tep").grid(row=0, column=2, sticky="w", padx=(8, 0))
        self.e_hrmax = self._num_entry(base, c.hr_max, 0, 3)
        for e in (self.e_ftp, self.e_hrmax):
            e.bind("<KeyRelease>", lambda ev: self._update_thr_hints())

        grid = ttk.Frame(tab_thr)
        grid.pack(fill="x", pady=(6, 0))
        ttk.Label(grid, text="Stupeň od", style="Head.TLabel").grid(row=0, column=0, sticky="w")
        self.lbl_phead = ttk.Label(grid, style="Head.TLabel", foreground=COL_POWER)
        self.lbl_phead.grid(row=0, column=1)
        self.lbl_hhead = ttk.Label(grid, style="Head.TLabel", foreground=COL_HR)
        self.lbl_hhead.grid(row=0, column=2)
        self.e_pthr, self.e_hthr, self.lbl_hints = [], [], []
        n = self.cfg.fan.max_level
        for i in range(n):
            ttk.Label(grid, text=f"  {i + 1}").grid(row=i + 1, column=0, sticky="w")
            ep = ttk.Entry(grid, width=6, justify="center")
            ep.grid(row=i + 1, column=1, padx=3, pady=1)
            eh = ttk.Entry(grid, width=6, justify="center")
            eh.grid(row=i + 1, column=2, padx=3, pady=1)
            hint = ttk.Label(grid, foreground="#868e96")
            hint.grid(row=i + 1, column=3, sticky="w")
            for e in (ep, eh):
                e.bind("<KeyRelease>", lambda ev: self._update_thr_hints())
            self.e_pthr.append(ep)
            self.e_hthr.append(eh)
            self.lbl_hints.append(hint)
        r = n + 1
        ttk.Label(grid, text="Hystereze").grid(row=r, column=0, sticky="w", pady=(6, 1))
        self.e_physt = self._num_entry(grid, c.power_hysteresis, r, 1)
        self.e_hhyst = self._num_entry(grid, c.hr_hysteresis, r, 2)
        ttk.Label(grid, text="W / bpm", foreground="#868e96").grid(row=r, column=3, sticky="w")
        ttk.Label(grid, text="Vyhlazení s").grid(row=r + 1, column=0, sticky="w")
        self.e_psmooth = self._num_entry(grid, c.power_smoothing_s, r + 1, 1)
        self.e_hsmooth = self._num_entry(grid, c.hr_smoothing_s, r + 1, 2)
        self._thr_shown = c.threshold_mode
        self._fill_thr_entries()

        # --- záložka Chování
        beh = tab_beh
        ttk.Label(beh, text="Prodleva před snížením (s)").grid(row=0, column=0, sticky="w")
        self.e_delay = self._num_entry(beh, c.down_delay_s, 0, 1)
        ttk.Separator(beh).grid(row=1, column=0, columnspan=2, sticky="ew", pady=6)
        ttk.Label(beh, text="Dofukování po tréninku (min)").grid(row=2, column=0, sticky="w")
        self.e_cool_min = self._num_entry(beh, round(c.cooldown_s / 60, 1), 2, 1)
        ttk.Label(beh, text="…na stupni").grid(row=3, column=0, sticky="w")
        self.e_cool_lvl = self._num_entry(beh, c.cooldown_level, 3, 1)
        ttk.Separator(beh).grid(row=4, column=0, columnspan=2, sticky="ew", pady=6)
        ttk.Label(beh, text="Bez dat ze senzorů → stupeň").grid(row=5, column=0, sticky="w")
        self.e_nodata_lvl = self._num_entry(beh, c.no_data_level, 5, 1)
        ttk.Label(beh, text="…po (s)").grid(row=6, column=0, sticky="w")
        self.e_nodata_s = self._num_entry(beh, c.no_data_s, 6, 1)
        ttk.Label(beh, foreground="#868e96", wraplength=250, justify="left",
                  text="Chytrý režim: výkon stupeň hned zvýší, tep ho podrží, dokud neklesne – "
                       "ventilátor tak nezpomalí při krátkém odpočinku mezi intervaly."
                  ).grid(row=7, column=0, columnspan=2, sticky="w", pady=(8, 0))

        ttk.Button(box, text="Použít a uložit", command=self.on_apply).pack(anchor="e", pady=(8, 0))

    # --- prahy: přepínání % / absolutně
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
        self.lbl_phead.configure(text="Výkon % FTP" if rel else "Výkon W")
        self.lbl_hhead.configure(text="Tep % max" if rel else "Tep bpm")
        state = "normal" if rel else "disabled"
        self.e_ftp.configure(state=state)
        self.e_hrmax.configure(state=state)
        self._update_thr_hints()

    def _read_thr_entries(self):
        pth = [int(e.get()) for e in self.e_pthr]
        hth = [int(e.get()) for e in self.e_hthr]
        if pth != sorted(pth) or hth != sorted(hth):
            raise ValueError("Prahy musí být vzestupně (stupeň 1 < 2 < 3).")
        if min(pth + hth) <= 0:
            raise ValueError("Prahy musí být kladné.")
        return pth, hth

    def _update_thr_hints(self):
        if self._thr_shown != "relative":
            for h in self.lbl_hints:
                h.configure(text="")
            return
        try:
            ftp, hrmax = int(self.e_ftp.get()), int(self.e_hrmax.get())
        except ValueError:
            return
        for ep, eh, h in zip(self.e_pthr, self.e_hthr, self.lbl_hints):
            try:
                h.configure(text=f"≈ {round(ftp * int(ep.get()) / 100)} W · {round(hrmax * int(eh.get()) / 100)} bpm")
            except ValueError:
                h.configure(text="")

    def on_thr_mode(self):
        new = self.thr_mode.get()
        if new == self._thr_shown:
            return
        try:  # zapamatovat si hodnoty původního režimu
            pth, hth = self._read_thr_entries()
            pl, hl = self._thr_lists(self._thr_shown)
            pl[:], hl[:] = pth, hth
        except ValueError:
            pass
        self._thr_shown = new
        self._fill_thr_entries()

    @staticmethod
    def _num_entry(parent, value, row, col):
        e = ttk.Entry(parent, width=7, justify="center")
        v = int(value) if float(value).is_integer() else value
        e.insert(0, str(v))
        e.grid(row=row, column=col, padx=4, pady=1)
        return e

    # ------------------------------------------------------------- backends
    def _make_backend(self):
        if self.backend is not None:
            try:
                self.backend.shutdown()
            except Exception:  # noqa: BLE001
                log.exception("shutdown")
        self.backend = SimulatedBackend(self.events) if self.sim_var.get() else AntBackend(self.events)

    def _make_fan(self):
        f = self.cfg.fan
        if self.sim_var.get():
            self.fan_worker.configure(SimulatedFan(f))
            self._set_fan_status("simulovaný ventilátor", True)
        elif f.ip and f.token:
            try:
                self.fan_worker.configure(XiaomiFan(f))
                self._set_fan_status("připojuji…", True)
            except MiioError as e:
                self.fan_worker.configure(None)
                self._set_fan_status(str(e), False)
        else:
            self.fan_worker.configure(None)
            self._set_fan_status("Zadejte IP adresu a token ventilátoru", False)

    def _set_fan_status(self, text, ok):
        self.fan_status.set(text)
        self.lbl_fan_status.configure(foreground="#2b8a3e" if ok else "#c92a2a")

    # -------------------------------------------------------------- akce
    def on_scan(self):
        for k in [k for k in self.devices if k not in self.selected]:
            del self.devices[k]
        self._refresh_tree()
        self.controller.reset()
        self.backend.start_scan(self.cfg.scan_duration_s)

    def on_start(self):
        devs = [self.devices[k] for k in self.selected if k in self.devices]
        if not devs:
            messagebox.showinfo("AntFan", "Nejdřív vyhledejte senzory a kliknutím vyberte tepový pás a/nebo powermetr.")
            return
        self.controller.reset()
        self.history.clear()
        self.backend.start_monitor(devs)

    def on_stop(self):
        self.backend.stop()

    def on_reset(self):
        """Uvolní dongle a provede USB reset (jako vytažení a zapojení)."""
        self.backend.reset()

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
            messagebox.showwarning("AntFan", f"Maximálně {MAX_CHANNELS} senzorů.")
            return
        else:
            self.selected.add(key)
        self.cfg.selected = [[k[0], k[1], self.devices[k].trans_type] for k in self.selected if k in self.devices]
        config_mod.save(self.cfg)
        self._refresh_tree()

    def on_fan_save(self):
        f = self.cfg.fan
        f.ip = self.e_ip.get().strip()
        f.token = self.e_token.get().strip()
        try:
            levels = max(1, min(5, int(self.sp_levels.get())))
        except ValueError:
            levels = 3
        f.mute_buzzer = self.mute_var.get()
        f.light_off = self.light_var.get()
        restart_needed = levels != f.max_level
        f.max_level = levels
        config_mod.save(self.cfg)
        self._make_fan()
        if restart_needed:
            messagebox.showinfo("AntFan", "Počet stupňů se projeví po restartu programu.")

    def on_fan_test(self):
        self.on_fan_save()
        if self.sim_var.get():
            self._set_fan_status("simulace – OK", True)
            return
        f = self.cfg.fan

        def run():
            try:
                fan = XiaomiFan(f)
                info = fan.info()
                power, level = fan.get_state()
                msg = (f"OK: {info.get('model', '?')} (fw {info.get('fw_ver', '?')}), "
                       f"{'zapnuto' if power else 'vypnuto'}, stupeň {level}")
                self.events.put(("fan", True, msg, level if power else 0))
            except Exception as e:  # noqa: BLE001
                self.events.put(("fan", False, str(e), None))

        import threading
        threading.Thread(target=run, daemon=True).start()
        self._set_fan_status("testuji…", True)

    def on_mode(self):
        self.cfg.auto_mode = self.auto_var.get()
        config_mod.save(self.cfg)

    def on_manual(self, level):
        self.auto_var.set(False)
        self.cfg.auto_mode = False
        self.manual_level = level
        config_mod.save(self.cfg)

    def on_apply(self):
        c = self.cfg.control
        n = self.cfg.fan.max_level
        try:
            pth, hth = self._read_thr_entries()
            mode = self.thr_mode.get()
            if mode == "relative":
                if max(pth) > 200 or max(hth) > 100:
                    raise ValueError("Procenta: výkon max. 200 % FTP, tep max. 100 % max. tepu.")
                c.power_pct, c.hr_pct = pth, hth
            else:
                c.power_thresholds, c.hr_thresholds = pth, hth
            c.threshold_mode = mode
            c.ftp = max(50, int(self.e_ftp.get()))
            c.hr_max = max(100, min(240, int(self.e_hrmax.get())))
            c.power_hysteresis = int(self.e_physt.get())
            c.hr_hysteresis = int(self.e_hhyst.get())
            c.power_smoothing_s = max(1.0, float(self.e_psmooth.get()))
            c.hr_smoothing_s = max(1.0, float(self.e_hsmooth.get()))
            c.down_delay_s = max(0.0, float(self.e_delay.get()))
            c.cooldown_s = max(0.0, float(self.e_cool_min.get().replace(",", ".")) * 60)
            c.cooldown_level = max(0, min(n, int(self.e_cool_lvl.get())))
            c.no_data_level = max(0, min(n, int(self.e_nodata_lvl.get())))
            c.no_data_s = max(5.0, float(self.e_nodata_s.get()))
        except ValueError as e:
            messagebox.showerror("AntFan", f"Neplatná hodnota: {e}")
            return
        label = self.cb_source.get()
        c.source_mode = next((k for k, v in SOURCE_MODES.items() if v == label), "smart")
        config_mod.save(self.cfg)
        self._update_thr_hints()

    # ------------------------------------------------------------- smyčka
    def _poll_events(self):
        tree_dirty = False
        try:
            while True:
                ev = self.events.get_nowait()
                kind = ev[0]
                if kind == "ant_status":
                    self.ant_status.set(ev[1])
                elif kind == "ant_error":
                    self.ant_status.set("Chyba ANT+")
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
        hints = []
        try:
            all_n, single = self.backend.rx_diagnosis() if self.backend is not None else (0, {})
        except Exception:  # noqa: BLE001
            all_n, single = 0, {}
        if all_n >= 2:
            hints.append(f"Výpadky na VŠECH senzorech zároveň ({all_n}× za 5 min) → příčina je "
                         "v PC: zkuste jiný USB port (USB 2.0, ne hub), prodlužovačku, jiný dongle; "
                         "router/ventilátor dál od donglu.")
        if single:
            who = ", ".join(f"{k} {n}×" for k, n in single.items())
            hints.append(f"Vypadává jen {who} (za 5 min), ostatní senzory jdou → příčina je "
                         "u senzoru: jeho Bluetooth spojení s Rouvy, baterie, kontakt pásu.")
        if weak and not hints:
            hints.append("Slabý příjem: " + ", ".join(weak) + ". Dejte dongle blíž ke kolu "
                         "(USB prodlužovačka, ne do zadního USB 3.0 portu).")
        self.rx_hint.set("\n".join(hints))

    def _tick(self):
        now = time.monotonic()
        ctrl = self.controller
        auto_level = ctrl.tick(now)
        if self.auto_var.get():
            desired, info = auto_level, ctrl.reason
        else:
            desired, info = self.manual_level, "ručně"
        if self.backend.state == "monitoring" or not self.auto_var.get():
            self.fan_worker.set_desired(desired)
        else:
            self.fan_worker.set_desired(None)
            info = "čeká na měření"

        self.v_power.set("–" if ctrl.power_now is None else str(ctrl.power_now))
        self.v_power_avg.set("" if ctrl.power_smoothed is None else
                             f"průměr {self.cfg.control.power_smoothing_s:g} s: {ctrl.power_smoothed:.0f} W"
                             + (f" ({ctrl.power_smoothed / self.cfg.control.ftp * 100:.0f} % FTP)"
                                if self.cfg.control.ftp else "")
                             + (f" · {ctrl.cadence_now} rpm" if ctrl.cadence_now else "")
                             + (f" · ⚠ výpadek příjmu {ctrl.power_gap_s:.0f} s" if ctrl.power_gap_s else ""))
        self.v_hr.set("–" if ctrl.hr_now is None else str(ctrl.hr_now))
        self.v_hr_avg.set("" if ctrl.hr_smoothed is None else
                          f"průměr {self.cfg.control.hr_smoothing_s:g} s: {ctrl.hr_smoothed:.0f}")
        self.v_fan.set("Vyp" if desired == 0 else str(desired))
        actual = "" if self.fan_actual is None else f" · skutečně: {'Vyp' if self.fan_actual == 0 else self.fan_actual}"
        self.v_fan_info.set(info + actual)

        if now - self._last_hist >= 1.0:
            self._last_hist = now
            self.history.append((ctrl.power_smoothed, ctrl.hr_smoothed, desired))
            self._draw_chart()
            self._refresh_tree()
        self.root.after(250, self._tick)

    def _draw_chart(self):
        cv = self.canvas
        cv.delete("all")
        w, h = cv.winfo_width(), cv.winfo_height()
        if w < 50 or h < 50:
            return
        pad_l, pad_r, pad_t, pad_b = 40, 40, 10, 22
        pw, ph = w - pad_l - pad_r, h - pad_t - pad_b
        hist = list(self.history)
        p_max = max([400] + [p for p, _, _ in hist if p is not None])
        hr_lo, hr_hi = 60, 200
        n_lvl = max(1, self.cfg.fan.max_level)

        def x_of(i):
            return pad_l + pw * (HISTORY_S - len(hist) + i) / (HISTORY_S - 1)

        # pozadí = stupeň ventilátoru
        for i, (_, _, lvl) in enumerate(hist):
            if lvl:
                x0 = x_of(i)
                x1 = x_of(i + 1) if i + 1 < len(hist) else x0 + pw / HISTORY_S
                y0 = pad_t + ph * (1 - lvl / n_lvl)
                cv.create_rectangle(x0, y0, x1 + 1, pad_t + ph, fill=COL_FAN, outline="")
        # mřížka
        for k in range(5):
            y = pad_t + ph * k / 4
            cv.create_line(pad_l, y, pad_l + pw, y, fill="#f1f3f5")
            cv.create_text(pad_l - 4, y, text=f"{p_max * (1 - k / 4):.0f}", anchor="e",
                           fill=COL_POWER, font=("Segoe UI", 8))
            cv.create_text(pad_l + pw + 4, y, text=f"{hr_hi - (hr_hi - hr_lo) * k / 4:.0f}",
                           anchor="w", fill=COL_HR, font=("Segoe UI", 8))
        cv.create_text(pad_l, h - 4, text="−5 min", anchor="sw", fill="#868e96", font=("Segoe UI", 8))
        cv.create_text(pad_l + pw, h - 4, text="teď", anchor="se", fill="#868e96", font=("Segoe UI", 8))
        cv.create_text(pad_l + pw / 2, h - 4, text="W (vlevo) · bpm (vpravo) · modře stupeň ventilátoru",
                       anchor="s", fill="#868e96", font=("Segoe UI", 8))

        def line(idx, scale, color):
            pts = []
            for i, row in enumerate(hist):
                v = row[idx]
                if v is None:
                    if len(pts) >= 4:
                        cv.create_line(*pts, fill=color, width=2)
                    pts = []
                    continue
                pts += [x_of(i), pad_t + ph * (1 - max(0.0, min(1.0, scale(v))))]
            if len(pts) >= 4:
                cv.create_line(*pts, fill=color, width=2)

        line(0, lambda v: v / p_max, COL_POWER)
        line(1, lambda v: (v - hr_lo) / (hr_hi - hr_lo), COL_HR)

    def _cleanup(self):
        """Uvolní dongle – volá se při zavření okna i při ukončení procesu."""
        if getattr(self, "_cleaned", False):
            return
        self._cleaned = True
        try:
            self.fan_worker.stop()
            self.backend.shutdown()
        except Exception:  # noqa: BLE001
            log.exception("Chyba při ukončování")

    def _on_close(self):
        try:
            self.ant_status.set("Uvolňuji dongle…")
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
            "AntFan už běží. Pokud jeho okno nevidíte, ukončete ho ve Správci úloh "
            "(proces AntFan.exe nebo pythonw.exe) a spusťte program znovu.")
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
    messagebox.showerror("AntFan", "Starou instanci se nepodařilo ukončit. Zkuste Správce úloh.")
    root.destroy()
    return False


def main():
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
