"""Baterie senzorů v GUI: stav, upozornění v okně jízdy a volby v Nastavení → Senzory.

Mixin pro App. Stav drží App (self.battery, self._batt_*), widgety se staví
v builderech a při přepnutí motivu (_rebuild_ui) se postaví znovu.
Barvy se čtou z modulu app až při stavbě, protože je _set_palette přepisuje.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from . import battery as bat
from . import config as config_mod


def _c(name: str) -> str:
    from . import app
    return getattr(app, name)


class BatteryUIMixin:
    # ------------------------------------------------------------- stav
    def _batt_init(self):
        self.battery: dict[tuple[int, int], tuple[int | None, int | None]] = {}
        self._batt_warned: set[tuple[int, int]] = set()   # upozorněno už v tomto spuštění
        self._batt_bar_text = ""

    def batt_low(self, key) -> bool:
        st = self.battery.get(key)
        if st is None:
            return False
        c = self.cfg
        return bat.is_low(st[0], st[1], c.battery_warn_level, c.battery_warn_pct)

    def batt_text(self, key) -> str:
        st = self.battery.get(key)
        return bat.text(*st) if st else ""

    def _batt_on_event(self, ev):
        _, key, pct, status = ev
        self.battery[key] = (pct, status)
        self._batt_check()

    def _batt_check(self):
        if not self.cfg.battery_warn:
            return
        new = [k for k in self.battery if self.batt_low(k) and k not in self._batt_warned]
        if not new:
            return
        self._batt_warned.update(new)
        names = []
        for k in new:
            d = self.devices.get(k)
            name = f"{d.type_name} #{d.device_id}" if d else f"#{k[0]}"
            names.append(f"{name} ({self.batt_text(k)})")
        self._batt_bar_text = ("Slabá baterie: " + ", ".join(names) +
                               ". Vyměňte ji nebo nabijte před další jízdou.")
        self._batt_show_bar()

    # ------------------------------------------------------------- okno jízdy
    def _batt_build_bar(self, parent, after):
        """Pruh pod horní lištou; viditelný jen s nezavřeným upozorněním."""
        f = self.fonts
        self._batt_after = after
        self.batt_bar = tk.Frame(parent, bg=_c("SURFACE"))
        self.batt_lbl = tk.Label(self.batt_bar, text="", bg=_c("SURFACE"), fg=_c("BAD"),
                                 font=f.body, anchor="w", justify="left")
        self.batt_lbl.pack(side="left", fill="x", expand=True, padx=(16, 8), pady=6)
        close = tk.Label(self.batt_bar, text="Skrýt", bg=_c("SURFACE"), fg=_c("MUTED"),
                         font=f.small, cursor="hand2")
        close.pack(side="right", padx=14)
        close.bind("<Button-1>", lambda e: self._batt_hide_bar())
        self._batt_show_bar()

    def _batt_show_bar(self):
        bar = getattr(self, "batt_bar", None)
        if bar is None or not bar.winfo_exists():
            return
        if self._batt_bar_text:
            self.batt_lbl.configure(text=self._batt_bar_text)
            if not bar.winfo_manager():
                bar.pack(fill="x", after=self._batt_after)
        else:
            bar.pack_forget()

    def _batt_hide_bar(self):
        self._batt_bar_text = ""
        self._batt_show_bar()

    # ------------------------------------------------------------- Nastavení
    def _batt_build_options(self, p):
        c = self.cfg
        box = tk.Frame(p, bg=_c("BG"))
        box.pack(fill="x", pady=(12, 0))
        self._batt_var = tk.BooleanVar(value=c.battery_warn)
        ttk.Checkbutton(box, text="Upozornit na slabou baterii", variable=self._batt_var,
                        command=self._batt_save).pack(anchor="w")
        row = tk.Frame(box, bg=_c("BG"))
        row.pack(fill="x", pady=(4, 0))
        tk.Label(row, text="Hranice:", bg=_c("BG"), fg=_c("MUTED"), font=self.fonts.small).pack(side="left")
        self._batt_level_var = tk.IntVar(value=c.battery_warn_level)
        for val, t in ((bat.LOW, "slabá"), (bat.CRITICAL, "kritická")):
            ttk.Radiobutton(row, text=t, value=val, variable=self._batt_level_var,
                            command=self._batt_save).pack(side="left", padx=(8, 0))
        tk.Label(row, text="nebo pod", bg=_c("BG"), fg=_c("MUTED"),
                 font=self.fonts.small).pack(side="left", padx=(14, 6))
        self._batt_pct_entry = ttk.Entry(row, width=4, justify="center")
        self._batt_pct_entry.insert(0, str(c.battery_warn_pct))
        self._batt_pct_entry.bind("<KeyRelease>", lambda e: self._batt_save())
        self._batt_pct_entry.pack(side="left")
        tk.Label(row, text="% u senzorů, které posílají procenta", bg=_c("BG"), fg=_c("MUTED"),
                 font=self.fonts.small).pack(side="left", padx=(6, 0))

    def _batt_save(self):
        c = self.cfg
        c.battery_warn = bool(self._batt_var.get())
        c.battery_warn_level = int(self._batt_level_var.get())
        try:
            v = int(self._batt_pct_entry.get())
            if 1 <= v <= 100:
                c.battery_warn_pct = v
        except ValueError:
            pass
        config_mod.save(c)
        if not c.battery_warn:
            self._batt_hide_bar()
        self._batt_check()
        self._refresh_tree()
