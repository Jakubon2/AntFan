"""Záznam jízdy v App, okno „Shrnutí jízdy“ a stránka Nastavení → Jízdy.

RideMixin se volá z App._tick jednou za sekundu (_ride_tick). Jízda končí:
  * po Zastavit (nebo když měření jinak skončí),
  * když během měření doběhne dofukování (přestali jste šlapat),
  * při zavření programu (jen se uloží, okno se neukáže).
Barvy se čtou z modulu app až při stavbě widgetů (mění se s motivem).
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from . import ride

log = logging.getLogger("antfan.ride")


def _A():
    from . import app as A  # pozdní import: app importuje tento modul

    return A


def _date_text(d) -> str:
    return f"{d.day}. {d.month}. {d.year}, {d.hour}:{d.minute:02d}"


def _num(v, fmt="{:.0f}", unit=""):
    if v is None:
        return "–"
    return fmt.format(v).replace(".", ",") + (f" {unit}" if unit else "")  # česky desetinná čárka


def open_folder(path) -> None:
    d = str(path)
    try:
        if sys.platform == "win32":
            os.startfile(d)  # noqa: S606
        else:
            subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", d])
    except Exception as e:  # noqa: BLE001
        messagebox.showinfo("AntFan", f"Jízdy jsou ve složce:\n{d}\n\n({e})")


class RideMixin:
    ride_rec: ride.RideRecorder | None = None
    _ride_cooling = False
    _ride_wait_activity = False
    _summary_win = None
    _summary_state = None      # (stats, path) otevřeného shrnutí – kvůli přestavbě motivu

    # ============================================================ záznam
    def _ride_level(self) -> int:
        return self.controller.level if self.auto_var.get() else self.manual_level

    def _ride_tick(self, now: float):
        st = self.backend.state
        ctrl = self.controller
        if st == "monitoring":
            if self.ride_rec is None:
                # po automatickém konci čekat, až se zase začne šlapat
                if self._ride_wait_activity and (getattr(ctrl, "_raw_level", 0) <= 0
                                                 or ctrl.reason == "žádná data ze senzorů"):
                    return
                self._ride_wait_activity = False
                self.ride_rec = ride.RideRecorder()
                self._ride_cooling = False
            c = self.cfg.control
            self.ride_rec.add(now, ctrl.power_now, ctrl.power_smoothed, ctrl.cadence_now, ctrl.hr_now,
                              self._ride_level(), c.ftp, c.hr_max)
            cooling = ctrl.reason.startswith("dofukování")
            if self._ride_cooling and not cooling and getattr(ctrl, "_raw_level", 0) <= 0:
                self._ride_finish()
                self._ride_wait_activity = True
            self._ride_cooling = cooling
        elif st != "unplugged":  # odpojený dongle se obnoví sám, jízda pokračuje
            self._ride_wait_activity = False
            if self.ride_rec is not None:
                self._ride_finish()

    def _ride_finish(self, show: bool = True):
        rec, self.ride_rec = self.ride_rec, None
        self._ride_cooling = False
        if rec is None:
            return None
        samples = rec.trimmed()
        stats = ride.compute(samples, rec.start, self.cfg.fan.max_level)
        if not stats.worth_showing:
            log.info("Jízda %s s se neukládá (krátká nebo bez dat)", int(stats.duration_s))
            return None
        path = None
        try:
            path = ride.save_csv(samples, rec.start)
            log.info("Jízda uložena: %s (%s)", path.name, ride.fmt_duration(stats.duration_s))
        except Exception:  # noqa: BLE001
            log.exception("Nelze uložit jízdu")
        self._refresh_rides()
        if show:
            self.show_ride_summary(stats, path)
        return path

    def _ride_after_rebuild(self):
        """Po přestavbě motivu znovu otevřít shrnutí, které bylo vidět."""
        state = self._summary_state
        self._summary_win = None
        if state is not None:
            self.show_ride_summary(*state)

    # ============================================================ okno shrnutí
    def show_ride_summary(self, stats: ride.RideStats, path: Path | None = None):
        A = _A()
        f = self.fonts
        px = self.px
        if self._summary_win is not None and self._summary_win.winfo_exists():
            self._summary_win.destroy()
        w = self._summary_win = tk.Toplevel(self.root)
        self._summary_state = (stats, path)
        w.title("Shrnutí jízdy")
        w.configure(bg=A.BG)

        def close():
            self._summary_state = None
            self._summary_win = None
            w.destroy()

        w.protocol("WM_DELETE_WINDOW", close)
        w.bind("<Escape>", lambda e: close())

        def lbl(parent, text, fg=None, font=None, **kw):
            return tk.Label(parent, text=text, bg=A.BG, fg=fg or A.MUTED, font=font or f.small, **kw)

        head = tk.Frame(w, bg=A.BG)
        head.pack(fill="x", padx=20, pady=(14, 10))
        lbl(head, "Shrnutí jízdy", fg=A.TEXT, font=f.h2, anchor="w").pack(fill="x")
        lbl(head, f"{_date_text(stats.start)} · FTP {stats.ftp} W · max. tep {stats.hr_max} bpm",
            anchor="w").pack(fill="x")
        tk.Frame(w, height=1, bg=A.BORDER).pack(fill="x")

        # --- čísla
        tiles = tk.Frame(w, bg=A.BG)
        tiles.pack(fill="x", padx=20, pady=(10, 6))
        dec = stats.decoupling
        items = [
            ("Délka", ride.fmt_duration(stats.duration_s), A.TEXT),
            ("Ø výkon", _num(stats.avg_power, unit="W"), A.POWER),
            ("Max. výkon", _num(stats.max_power, unit="W"), A.POWER),
            ("NP", _num(stats.np, unit="W"), A.POWER),
            ("IF", _num(stats.if_, "{:.2f}"), A.TEXT),
            ("TSS", _num(stats.tss), A.TEXT),
            ("Práce", _num(stats.kj, unit="kJ"), A.TEXT),
            ("Ø kadence", _num(stats.avg_cadence, unit="rpm"), A.TEXT),
            ("Ø tep", _num(stats.avg_hr, unit="bpm"), A.HR),
            ("Max. tep", _num(stats.max_hr, unit="bpm"), A.HR),
            ("Posun tepu", _num(dec, "{:+.1f}", "%"), A.TEXT if dec is None or dec < 5 else A.BAD),
        ]
        cols = 4
        for i in range(cols):
            tiles.columnconfigure(i, weight=1, uniform="st")
        self._summary_values = {}
        for i, (title, value, col) in enumerate(items):
            cell = tk.Frame(tiles, bg=A.BG)
            cell.grid(row=i // cols, column=i % cols, sticky="w", padx=(0, 16), pady=4)
            lbl(cell, title, anchor="w").pack(fill="x")
            v = lbl(cell, value, fg=col, font=f.h2, anchor="w")
            v.pack(fill="x")
            self._summary_values[title] = value
        tk.Frame(w, height=1, bg=A.BORDER).pack(fill="x", pady=(6, 0))

        # --- pruhy
        body = tk.Frame(w, bg=A.BG)
        body.pack(fill="both", expand=True, padx=20, pady=10)
        left = tk.Frame(body, bg=A.BG)
        left.grid(row=0, column=0, sticky="nw", padx=(0, 24))
        right = tk.Frame(body, bg=A.BG)
        right.grid(row=0, column=1, sticky="nw")
        bar_w = int(300 * px)

        if stats.has_power:
            rows = [(f"{z} {name}", s) for (z, name, _), s in zip(ride.POWER_ZONES, stats.power_zones)]
            self._zone_bars(left, "Čas v zónách výkonu", rows, A.POWER, bar_w)
        if stats.has_hr:
            rows = [(f"{z} {name}", s) for (z, name, _), s in zip(ride.HR_ZONES, stats.hr_zones)]
            self._zone_bars(right, "Čas v zónách tepu", rows, A.HR, bar_w)
        rows = [("Vyp" if i == 0 else f"Stupeň {i}", s) for i, s in enumerate(stats.fan_levels)]
        self._zone_bars(left if stats.has_power else right, "Stupně ventilátoru", rows, A.FAN, bar_w)
        dec_box = right if stats.has_power else left
        lbl(dec_box, "Posun tepu", fg=A.TEXT, font=f.body_b, anchor="w").pack(fill="x", pady=(12, 2))
        lbl(dec_box, ride.decoupling_text(dec), anchor="w", justify="left",
            wraplength=bar_w).pack(fill="x")

        tk.Frame(w, height=1, bg=A.BORDER).pack(fill="x")
        bf = tk.Frame(w, bg=A.BG)
        bf.pack(fill="x", padx=20, pady=10)
        ttk.Button(bf, text="Zavřít", command=close).pack(side="right")
        ttk.Button(bf, text="Otevřít složku", command=lambda: open_folder(ride.rides_dir())).pack(
            side="right", padx=8)
        if path is not None:
            lbl(bf, path.name, fg=A.FAINT, anchor="w").pack(side="left")
        A._titlebar(w, self.dark)  # noqa: SLF001
        w.update_idletasks()
        w.minsize(w.winfo_reqwidth(), min(w.winfo_reqheight(), w.winfo_screenheight() - 80))
        w.lift()
        return w

    def _zone_bars(self, parent, title, rows, color, width):
        A = _A()
        f = self.fonts
        px = self.px
        tk.Label(parent, text=title, bg=A.BG, fg=A.TEXT, font=f.body_b, anchor="w").pack(
            fill="x", pady=(0, 4))
        rh = int(22 * px)
        label_w, time_w = int(110 * px), int(86 * px)
        cv = tk.Canvas(parent, width=width, height=rh * len(rows), bg=A.BG, highlightthickness=0)
        cv.pack(anchor="w")
        total = sum(s for _, s in rows) or 1.0
        bmax = max(s for _, s in rows) or 1.0
        span = width - label_w - time_w
        for i, (name, sec) in enumerate(rows):
            y = i * rh + rh / 2
            cv.create_text(0, y, text=name, anchor="w", fill=A.MUTED, font=f.small)
            x0 = label_w
            cv.create_rectangle(x0, y - rh * 0.28, x0 + span, y + rh * 0.28, fill=A.SURFACE, outline="")
            if sec > 0:
                cv.create_rectangle(x0, y - rh * 0.28, x0 + max(2, span * sec / bmax), y + rh * 0.28,
                                    fill=color, outline="")
            cv.create_text(width, y, text=f"{ride.fmt_duration(sec)} · {sec / total * 100:.0f} %",
                           anchor="e", fill=A.TEXT if sec else A.FAINT, font=f.small)
        return cv

    # ============================================================ stránka Jízdy
    def _page_rides(self, p):
        A = _A()
        self._page_head(p, "Jízdy", "Každá jízda delší než 5 minut se uloží jako CSV. "
                                    "Dvojklikem otevřete její shrnutí.")
        cols = ("date", "dur", "pw", "np", "tss", "hr")
        self.rides_tree = ttk.Treeview(p, columns=cols, show="headings", selectmode="browse", height=9)
        for c, t, wd in (("date", "Začátek", 130), ("dur", "Délka", 70), ("pw", "Ø W", 55),
                         ("np", "NP", 55), ("tss", "TSS", 50), ("hr", "Ø tep", 55)):
            self.rides_tree.heading(c, text=t)
            self.rides_tree.column(c, width=int(wd * self.px), anchor="w" if c == "date" else "center")
        self.rides_tree.pack(fill="x")
        self.rides_tree.bind("<Double-1>", lambda e: self.on_ride_open())
        self.rides_tree.bind("<Return>", lambda e: self.on_ride_open())
        self.lbl_rides_empty = tk.Label(p, text="", bg=A.BG, fg=A.MUTED, font=self.fonts.body, anchor="w")
        self.lbl_rides_empty.pack(fill="x", pady=(6, 0))
        bf = tk.Frame(p, bg=A.BG)
        bf.pack(fill="x", pady=(8, 0))
        ttk.Button(bf, text="Otevřít shrnutí", command=self.on_ride_open).pack(side="left")
        ttk.Button(bf, text="Otevřít složku", command=lambda: open_folder(ride.rides_dir())).pack(
            side="left", padx=8)
        p.bind("<Map>", lambda e: self._refresh_rides() if e.widget is p else None)
        self._refresh_rides()

    def _ride_stats_cached(self, path: Path):
        try:
            key = (str(path), path.stat().st_mtime)
        except OSError:
            return None
        cache = self.__dict__.setdefault("_rides_cache", {})
        if key not in cache:
            try:
                samples, start = ride.load_csv(path)
                cache[key] = ride.compute(samples, start, self.cfg.fan.max_level)
            except Exception:  # noqa: BLE001
                log.exception("Nelze načíst %s", path)
                cache[key] = None
        return cache[key]

    def _refresh_rides(self):
        tree = getattr(self, "rides_tree", None)
        if tree is None or not tree.winfo_exists():
            return
        tree.delete(*tree.get_children())
        files = ride.list_rides()
        for path in files:
            st = self._ride_stats_cached(path)
            if st is None:
                vals = (path.stem, "?", "", "", "", "")
            else:
                vals = (_date_text(st.start), ride.fmt_duration(st.duration_s), _num(st.avg_power),
                        _num(st.np), _num(st.tss), _num(st.avg_hr))
            tree.insert("", "end", iid=str(path), values=vals)
        self.lbl_rides_empty.configure(text="" if files else "Zatím žádná uložená jízda.")

    def on_ride_open(self):
        tree = getattr(self, "rides_tree", None)
        sel = tree.selection() if tree is not None else ()
        if not sel:
            kids = tree.get_children() if tree is not None else ()
            if not kids:
                return
            sel = kids[:1]
        path = Path(sel[0])
        st = self._ride_stats_cached(path)
        if st is None:
            messagebox.showerror("AntFan", f"Soubor {path.name} nejde načíst.", parent=self.settings)
            return
        self.show_ride_summary(st, path)
