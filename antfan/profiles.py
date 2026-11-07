"""Profily jezdců / druhů tréninku – každý má vlastní ControlConfig.

Čisté operace nad AppConfig (bez GUI) a ProfilesMixin pro App: výběr profilu
v horní liště okna jízdy a řádek s profilem nahoře na stránce Řízení.
Barvy se čtou z modulu app až při stavbě widgetů (mění se s motivem).
"""
from __future__ import annotations

import copy
import tkinter as tk
from tkinter import messagebox, ttk

from . import config as config_mod
from .config import DEFAULT_PROFILE, AppConfig
from .i18n import _

MAX_NAME = 30


def _clean(name: str) -> str:
    return " ".join((name or "").split())[:MAX_NAME]


def validate_name(cfg: AppConfig, name: str, old: str | None = None) -> str:
    """Vrátí upravené jméno, nebo vyhodí ValueError s českou hláškou."""
    name = _clean(name)
    if not name:
        raise ValueError(_("Zadejte jméno profilu."))
    if name != old and name in cfg.profiles:
        raise ValueError(_("Profil „{name}“ už existuje.").format(name=name))
    return name


def create(cfg: AppConfig, name: str, base: str | None = None) -> str:
    """Nový profil jako kopie `base` (výchozí: aktivního). Rovnou ho aktivuje."""
    name = validate_name(cfg, name)
    src = cfg.profiles.get(base or cfg.active_profile, cfg.control)
    cfg.profiles[name] = copy.deepcopy(src)
    cfg.active_profile = name
    return name


def rename(cfg: AppConfig, old: str, new: str) -> str:
    new = validate_name(cfg, new, old)
    if new == old:
        return new
    cfg.profiles = {(new if k == old else k): v for k, v in cfg.profiles.items()}
    if cfg.active_profile == old:
        cfg.active_profile = new
    return new


def delete(cfg: AppConfig, name: str) -> None:
    if len(cfg.profiles) <= 1:
        raise ValueError(_("Poslední profil smazat nejde."))
    names = list(cfg.profiles)
    idx = names.index(name)
    del cfg.profiles[name]
    if cfg.active_profile == name:
        rest = list(cfg.profiles)
        cfg.active_profile = rest[min(idx, len(rest) - 1)]


def activate(cfg: AppConfig, name: str) -> None:
    if name not in cfg.profiles:
        raise KeyError(name)
    cfg.active_profile = name


# ====================================================================== GUI
def _A():
    from . import app as A  # pozdní import: app importuje tento modul

    return A


def ask_name(app, title: str, prompt: str, initial: str = "") -> str | None:
    """Malý dialog ve stylu aplikace. Vrátí zadaný text, nebo None."""
    A = _A()
    parent = app.settings if app.settings.winfo_viewable() else app.root
    w = tk.Toplevel(parent)
    w.title(title)
    w.configure(bg=A.BG)
    w.transient(parent)
    w.resizable(False, False)
    box = tk.Frame(w, bg=A.BG)
    box.pack(fill="both", expand=True, padx=18, pady=14)
    tk.Label(box, text=prompt, bg=A.BG, fg=A.TEXT, font=app.fonts.body, anchor="w").pack(fill="x")
    e = ttk.Entry(box, width=32)
    e.insert(0, initial)
    e.select_range(0, "end")
    e.pack(fill="x", pady=(6, 4))
    err = tk.Label(box, text="", bg=A.BG, fg=A.BAD, font=app.fonts.small, anchor="w")
    err.pack(fill="x")
    result: list[str | None] = [None]

    def ok(_e=None):
        if not _clean(e.get()):
            err.configure(text=_("Zadejte jméno profilu."))
            return
        result[0] = e.get()
        w.destroy()

    bf = tk.Frame(box, bg=A.BG)
    bf.pack(fill="x", pady=(8, 0))
    ttk.Button(bf, text=_("Zrušit"), command=w.destroy).pack(side="right")
    ttk.Button(bf, text="OK", command=ok).pack(side="right", padx=8)
    e.bind("<Return>", ok)
    w.bind("<Escape>", lambda _e: w.destroy())
    A._titlebar(w, app.dark)  # noqa: SLF001
    w.update_idletasks()
    x = parent.winfo_rootx() + max(0, (parent.winfo_width() - w.winfo_reqwidth()) // 2)
    y = parent.winfo_rooty() + max(0, (parent.winfo_height() - w.winfo_reqheight()) // 3)
    w.geometry(f"+{x}+{y}")
    e.focus_set()
    app._dialog = w  # noqa: SLF001 – pro testy
    try:
        w.grab_set()
    except tk.TclError:
        pass
    w.wait_window()
    return result[0]


def profile_label(name: str) -> str:
    """Jméno profilu k zobrazení; výchozí profil se překládá."""
    return _(name) if name == DEFAULT_PROFILE else name


class ProfilesMixin:
    """Metody App pro profily. Stav je v self.cfg, widgety se dají kdykoli přestavět."""

    # --- widgety
    def _profile_menu(self, parent, font, fg, bg, prefix=""):
        """Label s jménem profilu, kliknutím se otevře menu s ostatními profily."""
        A = _A()
        lb = tk.Label(parent, text="", bg=bg, fg=fg, font=font, cursor="hand2", padx=6, pady=2)

        def popup(_e=None):
            m = tk.Menu(lb, tearoff=0, bg=A.SURFACE, fg=A.TEXT, activebackground=A.ACCENT_BG,
                        activeforeground=A.ACCENT, font=self.fonts.body)
            for name in self.cfg.profiles:
                m.add_radiobutton(label=profile_label(name), value=name, variable=self._profile_var,
                                  command=lambda n=name: self.on_profile(n))
            m.add_separator()
            m.add_command(label=_("Spravovat profily…"), command=lambda: self.open_settings("control"))
            try:
                m.tk_popup(lb.winfo_rootx(), lb.winfo_rooty() + lb.winfo_height())
            finally:
                m.grab_release()

        lb.bind("<Button-1>", popup)
        lb._antfan_prefix = prefix  # noqa: SLF001
        self._profile_labels.append(lb)
        return lb

    def _profile_bar(self, top):
        """Nenápadný výběr profilu v horní liště okna jízdy."""
        A = _A()
        self._profile_labels = [w for w in getattr(self, "_profile_labels", []) if w.winfo_exists()]
        if not hasattr(self, "_profile_var"):
            self._profile_var = tk.StringVar(value=self.cfg.active_profile)
        self.lbl_profile_bar = self._profile_menu(top, self.fonts.body, A.MUTED, A.BG, prefix=_("Profil: "))
        self.lbl_profile_bar.pack(side="right", padx=(0, 10))
        self._update_profile_labels()

    def _profile_row(self, p):
        """Řádek nahoře na stránce Řízení: profil + Nový / Přejmenovat / Smazat."""
        A = _A()
        self._profile_labels = [w for w in getattr(self, "_profile_labels", []) if w.winfo_exists()]
        if not hasattr(self, "_profile_var"):
            self._profile_var = tk.StringVar(value=self.cfg.active_profile)
        row = tk.Frame(p, bg=A.BG)
        row.pack(fill="x", pady=(0, 12))
        ttk.Label(row, text=_("Profil")).pack(side="left", padx=(0, 8))
        field = tk.Frame(row, bg=A.BORDER, padx=1, pady=1)
        field.pack(side="left")
        self.lbl_profile_set = self._profile_menu(field, self.fonts.body_b, A.TEXT, A.SURFACE)
        self.lbl_profile_set.configure(padx=10, pady=3, anchor="w", width=16)
        self.lbl_profile_set.pack()
        ttk.Button(row, text=_("Nový"), command=self.on_profile_new).pack(side="left", padx=(10, 0))
        ttk.Button(row, text=_("Přejmenovat"), command=self.on_profile_rename).pack(side="left", padx=(6, 0))
        self.btn_profile_del = ttk.Button(row, text=_("Smazat"), command=self.on_profile_delete)
        self.btn_profile_del.pack(side="left", padx=(6, 0))
        self._update_profile_labels()

    def _update_profile_labels(self):
        name = self.cfg.active_profile
        self._profile_var.set(name)
        for lb in getattr(self, "_profile_labels", []):
            if lb.winfo_exists():
                lb.configure(text=f"{getattr(lb, '_antfan_prefix', '')}{profile_label(name)} ▾")
        btn = getattr(self, "btn_profile_del", None)
        if btn is not None and btn.winfo_exists():
            btn.state(["disabled"] if len(self.cfg.profiles) <= 1 else ["!disabled"])

    # --- akce
    def on_profile(self, name: str):
        """Přepne profil: uloží rozepsané hodnoty, načte nové do polí a do Controlleru."""
        if name == self.cfg.active_profile or name not in self.cfg.profiles:
            self._update_profile_labels()
            return
        self.on_apply()  # neplatné hodnoty se zahodí, nevadí
        activate(self.cfg, name)
        self._profile_switched()

    def _profile_switched(self):
        if self._apply_job is not None:  # rozepsané hodnoty patří starému profilu
            self.root.after_cancel(self._apply_job)
            self._apply_job = None
        self.controller.cfg = self.cfg.control
        self.source_mode = self.cfg.control.source_mode
        self._load_control_fields()
        config_mod.save(self.cfg)
        self._update_profile_labels()

    def _load_control_fields(self):
        """Hodnoty aktivního profilu do polí stránek Řízení a Chování."""
        c = self.cfg.control

        def put(e, v):
            st = str(e.cget("state"))
            e.configure(state="normal")
            e.delete(0, "end")
            v = int(v) if float(v).is_integer() else v
            e.insert(0, str(v))
            e.configure(state=st)

        put(self.e_ftp, c.ftp)
        put(self.e_hrmax, c.hr_max)
        self.thr_mode.set(c.threshold_mode)
        self._thr_shown = c.threshold_mode
        self._fill_thr_entries()
        for attr, v in (("e_physt", c.power_hysteresis), ("e_hhyst", c.hr_hysteresis),
                        ("e_psmooth", c.power_smoothing_s), ("e_hsmooth", c.hr_smoothing_s),
                        ("e_delay", c.down_delay_s), ("e_cool_min", round(c.cooldown_s / 60, 1)),
                        ("e_cool_lvl", c.cooldown_level), ("e_nodata_lvl", c.no_data_level),
                        ("e_nodata_s", c.no_data_s)):
            put(getattr(self, attr), v)
        self._update_cards()
        self.lbl_ctrl_err.configure(text="")
        self.lbl_beh_err.configure(text="")

    def on_profile_new(self):
        name = ask_name(self, _("Nový profil"), _("Jméno nového profilu (zkopíruje se aktuální nastavení):"))
        if name is None:
            return
        self.on_apply()
        try:
            create(self.cfg, name)
        except ValueError as e:
            messagebox.showerror("AntFan", str(e), parent=self.settings)
            return
        self._profile_switched()

    def on_profile_rename(self):
        old = self.cfg.active_profile
        name = ask_name(self, _("Přejmenovat profil"), _("Nové jméno profilu:"), old)
        if name is None:
            return
        try:
            rename(self.cfg, old, name)
        except ValueError as e:
            messagebox.showerror("AntFan", str(e), parent=self.settings)
            return
        config_mod.save(self.cfg)
        self._update_profile_labels()

    def on_profile_delete(self):
        name = self.cfg.active_profile
        if len(self.cfg.profiles) <= 1:
            return
        if not messagebox.askyesno("AntFan", _("Smazat profil „{name}“?").format(name=name), parent=self.settings):
            return
        delete(self.cfg, name)
        self._profile_switched()
