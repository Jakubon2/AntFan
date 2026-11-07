"""GUI chytrého párování a průvodce souběhem (mixin pro app.App).

Stav je na App (pairing, pair_result, coex_*), widgety se dají kdykoli
přestavět (_rebuild_ui při změně motivu): buildery jen čtou stav.
Barvy se čtou z modulu app až při stavbě, kvůli _set_palette.
"""
from __future__ import annotations

import logging
import threading
import time
import tkinter as tk
from tkinter import ttk

from . import coexist
from . import config as config_mod
from . import pairing
from .i18n import _

log = logging.getLogger("antfan.pairing")

COEX_RECHECK_MS = 90_000  # jak často znovu projít procesy (Rouvy se mohlo spustit později)


def _c():
    from . import app as A  # noqa: N812 – barvy jsou globály v app.py

    return A


class PairingUi:
    # ============================================================ stav
    def _pair_init(self):
        self.pairing: pairing.PairingSession | None = None
        self.pair_result: pairing.PairingResult | None = None
        self.pair_error = ""
        self.coex_sit = coexist.Situation()
        self.coex_advice: coexist.Advice | None = None
        self.coex_hidden = False      # pruh zavřený (do dalšího spuštění)
        self.coex_note = ""
        self._coex_switch_after_scan = False
        self._coex_probing = False
        self._coex_first = True
        self.coex_probe = coexist.probe  # testy ho nahradí falešným seznamem procesů
        self.coex_guide_var = tk.BooleanVar(value=getattr(self.cfg, "coexist_guide", True))

    # ============================================================ párování
    def on_pair(self):
        for k in [k for k in self.devices if k not in self.selected]:
            del self.devices[k]
        self._ant_error = False
        self.controller.reset()
        self.pair_result, self.pair_error = None, ""
        self.pairing = pairing.PairingSession(time.monotonic())
        self._refresh_tree()
        self.backend.start_scan(pairing.PAIR_SCAN_S)
        self._render_pair_box()
        self.root.after(500, self._pair_tick)

    def on_pair_cancel(self):
        if self.pairing is not None:
            self.backend.stop()
        self.pairing, self.pair_result, self.pair_error = None, None, ""
        self._render_pair_box()

    def on_pair_apply(self):
        res = self.pair_result
        if res is None or not res.selected:
            return
        for d in res.selected:
            self.devices.setdefault(d.key, d)
        self.selected = {d.key for d in res.selected}
        self.cfg.selected = [[d.device_id, d.device_type, d.trans_type] for d in res.selected]
        config_mod.save(self.cfg)
        self.pair_result = None
        self._render_pair_box()
        self.lbl_scan.configure(text=_("Výběr uložen: ") + ", ".join(
            f"{d.type_name} #{d.device_id}" for d in res.selected))
        self._refresh_tree()
        self._coex_refresh()

    def _pair_feed(self, d):
        if self.pairing is not None:
            self.pairing.feed(d, time.monotonic())

    def _pair_tick(self):
        if self.pairing is None:
            return
        try:
            left = max(0, int(pairing.PAIR_SCAN_S - (time.monotonic() - self.pairing.t0)))
            self.lbl_pair_title.configure(text=_("Hledám vaše senzory… {left} s").format(left=left))
        except tk.TclError:
            pass
        self.root.after(500, self._pair_tick)

    def _on_scan_done(self):
        if self.pairing is not None:
            self.pair_result = self.pairing.analyze(prefer_ble=self.coex_sit.busy)
            self.pairing = None
            log.info("Párování: návrh %s; %s", [d.key for d in self.pair_result.selected],
                     "; ".join(f"{v.device.key}: {v.reason}" for v in self.pair_result.verdicts))
            self._render_pair_box()
        if self._coex_switch_after_scan:
            self._coex_switch_after_scan = False
            self.on_coex_switch(rescan=False)

    def _build_pair_box(self, parent, before):
        A = _c()
        self.pair_box = tk.Frame(parent, bg=A.SURFACE, highlightthickness=1,
                                 highlightbackground=A.BORDER)
        self._pair_before = before
        self._render_pair_box()

    def _render_pair_box(self):
        A = _c()
        box = getattr(self, "pair_box", None)
        if box is None or not box.winfo_exists():
            return
        for w in box.winfo_children():
            w.destroy()
        res, wrap = self.pair_result, int(420 * self.px)
        if self.pairing is None and res is None and not self.pair_error:
            box.pack_forget()
            return
        box.pack(fill="x", pady=(0, 8), before=self._pair_before)

        def lbl(text, fg=None, font=None):
            w = tk.Label(box, text=text, bg=A.SURFACE, fg=fg or A.TEXT, font=font or self.fonts.body,
                         anchor="w", justify="left", wraplength=wrap)
            w.pack(fill="x", padx=12, pady=(2, 0))
            return w

        btns = tk.Frame(box, bg=A.SURFACE)
        if self.pairing is not None:
            self.lbl_pair_title = lbl(_("Hledám vaše senzory… {PAIR_SCAN_S} s").format(PAIR_SCAN_S=pairing.PAIR_SCAN_S),
                                      font=self.fonts.body_b)
            lbl(_(pairing.INSTRUCTION))
            ttk.Button(btns, text=_("Zrušit"), command=self.on_pair_cancel).pack(side="left")
        elif self.pair_error:
            lbl(_("Hledání se nepovedlo"), fg=A.BAD, font=self.fonts.body_b)
            lbl(self.pair_error, fg=A.MUTED)
            ttk.Button(btns, text=_("Zkusit znovu"), command=self.on_pair).pack(side="left")
            ttk.Button(btns, text=_("Zavřít"), command=self.on_pair_cancel).pack(side="left", padx=6)
        else:
            if res.ok:
                lbl(_("Vaše senzory"), font=self.fonts.body_b)
                for line in res.summary_lines():
                    lbl(line)
            else:
                lbl(_("Vaše senzory se nepodařilo poznat"), fg=A.BAD, font=self.fonts.body_b)
            chosen = {d.key for d in res.selected}
            others = [v for v in res.verdicts if v.device.key not in chosen and not v.reacted]
            if others:
                lbl(_("Nereagují, nejspíš patří sousedům: ") + ", ".join(
                    f"{v.device.type_name} #{v.device.device_id}" for v in others), fg=A.MUTED)
            for h in res.hints:
                lbl(h, fg=A.MUTED)
            if res.ok:
                ttk.Button(btns, text=_("Použít"), command=self.on_pair_apply).pack(side="left")
                ttk.Button(btns, text=_("Zkusit znovu"), command=self.on_pair).pack(side="left", padx=6)
            else:
                ttk.Button(btns, text=_("Zkusit znovu"), command=self.on_pair).pack(side="left")
            ttk.Button(btns, text=_("Zavřít"), command=self.on_pair_cancel).pack(side="left", padx=6)
        btns.pack(fill="x", padx=12, pady=(8, 10))

    # ============================================================ souběh
    def _coex_start(self):
        """Ve vlákně projde procesy; výsledek přijde jako událost ("coex", Situation)."""
        if self._coex_probing or not self.coex_guide_var.get():
            return
        self._coex_probing = True
        count = self._coex_first and not self.sim_var.get()
        self._coex_first = False

        def run():
            try:
                sit = self.coex_probe(count)
            except Exception:  # noqa: BLE001
                log.exception("Průvodce souběhem")
                sit = coexist.Situation()
            self.events.put(("coex", sit))

        threading.Thread(target=run, name="coex", daemon=True).start()

    def _coex_on_event(self, sit: coexist.Situation):
        self._coex_probing = False
        old = self.coex_sit
        sit.busy = sit.busy or old.busy
        if not sit.dongles:
            sit.dongles = old.dongles
        if sit.apps != old.apps:
            log.info("Průvodce souběhem: běží %s", ", ".join(sit.apps) or "nic")
        self.coex_sit = sit
        self._coex_refresh()
        if getattr(self, "_coex_job", None) is not None:
            self.root.after_cancel(self._coex_job)
        self._coex_job = self.root.after(COEX_RECHECK_MS, self._coex_start) if not self.coex_hidden else None

    def _coex_on_error(self, text: str):
        if self.pairing is not None:
            self.pairing = None
            self.pair_error = text.split("\n")[0]
            self._render_pair_box()
        if coexist.is_busy_error(text) and not self.coex_sit.busy:
            self.coex_sit.busy = True
            self._coex_first = True  # znovu spočítat dongly
            self._coex_refresh()
            self._coex_start()

    def _coex_refresh(self):
        sel = [self.devices[k] for k in self.selected if k in self.devices]
        self.coex_advice = coexist.advise(self.coex_sit, sel, list(self.devices.values()))
        self._render_coex_bar()
        self._render_coex_page()

    def on_coex_close(self):
        self.coex_hidden = True
        self._render_coex_bar()

    def on_coex_guide_toggle(self):
        self.cfg.coexist_guide = self.coex_guide_var.get()
        config_mod.save(self.cfg)
        if self.cfg.coexist_guide:
            self.coex_hidden = False
            self._coex_start()
        self._render_coex_bar()

    def on_coex_switch(self, rescan: bool = True):
        sel = [self.devices[k] for k in self.selected if k in self.devices]
        new, missing = coexist.switch_to_bt(sel, list(self.devices.values()))
        if {d.key for d in new} == {d.key for d in sel}:
            if rescan and self.backend.state != "scanning":
                self._coex_switch_after_scan = True
                self.coex_note = _("Hledám Bluetooth verze senzorů…")
                self._render_coex_page()
                self.on_scan()
                return
            self.coex_note = (_("Bluetooth verze vybraných senzorů nejsou vidět. Zapněte Bluetooth, "
                              "odpojte senzory od Rouvy na Bluetooth a vyberte senzory (BT) ručně "
                              "v Senzorech."))
        else:
            running = self.backend.state in ("monitoring", "unplugged")
            for d in new:
                self.devices.setdefault(d.key, d)
            self.selected = {d.key for d in new}
            self.cfg.selected = [[d.device_id, d.device_type, d.trans_type] for d in new]
            config_mod.save(self.cfg)
            self.coex_note = _("Vybráno: ") + ", ".join(f"{d.type_name} #{d.device_id}" for d in new)
            if missing:
                self.coex_note += (_(". Bez Bluetooth verze zůstává: ") + ", ".join(
                    f"{d.type_name} #{d.device_id}" for d in missing))
            self._refresh_tree()
            if running:
                self.on_start()
        self._coex_refresh()

    def _coex_bar_visible(self) -> bool:
        return bool(self.coex_advice) and self.coex_guide_var.get() and not self.coex_hidden

    def _build_coex_bar(self, parent):
        A = _c()
        self.coex_bar = tk.Frame(parent, bg=A.SURFACE, highlightthickness=1,
                                 highlightbackground=A.BORDER)
        self._render_coex_bar()

    def _render_coex_bar(self):
        A = _c()
        bar = getattr(self, "coex_bar", None)
        if bar is None or not bar.winfo_exists():
            return
        for w in bar.winfo_children():
            w.destroy()
        if not self._coex_bar_visible():
            bar.pack_forget()
            return
        adv = self.coex_advice
        tk.Label(bar, text=adv.short, bg=A.SURFACE, fg=A.TEXT, font=self.fonts.body,
                 anchor="w").pack(side="left", padx=(12, 8), pady=6)
        close = tk.Label(bar, text=_("Zavřít"), bg=A.SURFACE, fg=A.MUTED, font=self.fonts.small,
                         cursor="hand2")
        close.pack(side="right", padx=(6, 12))
        close.bind("<Button-1>", lambda e: self.on_coex_close())
        ttk.Button(bar, text=_("Více"), command=lambda: self.open_settings("coexist")).pack(side="right")
        if adv.kind == "antfan_bt":
            ttk.Button(bar, text=_("Přepnout na Bluetooth senzory"),
                       command=self.on_coex_switch).pack(side="right", padx=6)
        bar.pack(fill="x", padx=14, pady=(0, 10))

    def _page_coexist(self, p):
        A = _c()
        self._page_head(p, _("Souběh s Rouvy"), _("Jak jet zároveň s Rouvy, Zwiftem, TrainerRoad nebo "
                                             "MyWhoosh. Jeden ANT+ dongle může mít jen jeden program."))
        self.coex_page = tk.Frame(p, bg=A.BG)
        self.coex_page.pack(fill="x")
        ttk.Checkbutton(p, text=_("Upozornit, když běží Rouvy a podobné aplikace"),
                        variable=self.coex_guide_var,
                        command=self.on_coex_guide_toggle).pack(anchor="w", pady=(12, 0))
        wrap = int(440 * self.px)
        self._lbl(p, _("Možnosti: (a) dva ANT+ dongly, každý program má svůj; (b) Rouvy na ANT+, AntFan "
                     "na Bluetooth; (c) Rouvy na Bluetooth, AntFan na ANT+. ") + _(coexist.BT_LIMIT),
                  anchor="w", justify="left", wraplength=wrap).pack(fill="x", pady=(10, 0))
        self._render_coex_page()

    def _render_coex_page(self):
        A = _c()
        box = getattr(self, "coex_page", None)
        if box is None or not box.winfo_exists():
            return
        for w in box.winfo_children():
            w.destroy()
        wrap = int(440 * self.px)
        adv = self.coex_advice
        if adv is None:
            text = _("Teď neběží žádná známá tréninková aplikace a dongle nikdo jiný nedrží.")
        else:
            text = adv.text
        tk.Label(box, text=text, bg=A.BG, fg=A.TEXT, font=self.fonts.body, anchor="w",
                 justify="left", wraplength=wrap).pack(fill="x")
        if adv is not None and adv.kind == "antfan_bt":
            ttk.Button(box, text=_("Přepnout na Bluetooth senzory"),
                       command=self.on_coex_switch).pack(anchor="w", pady=(8, 0))
        if self.coex_note:
            tk.Label(box, text=self.coex_note, bg=A.BG, fg=A.MUTED, font=self.fonts.body, anchor="w",
                     justify="left", wraplength=wrap).pack(fill="x", pady=(6, 0))
