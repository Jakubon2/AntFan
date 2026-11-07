"""Dialog: přihlášení k účtu Xiaomi QR kódem a výběr ventilátoru."""
from __future__ import annotations

import base64
import threading
import tkinter as tk
import webbrowser
from tkinter import ttk

from . import app as A
from .xiaomi_cloud import CloudError, XiaomiCloud


class XiaomiLoginDialog:
    def __init__(self, app):
        self.app = app
        self.cloud = XiaomiCloud()
        self.cancelled = False
        self.devices: list[dict] = []
        f = app.fonts
        w = self.win = tk.Toplevel(app.settings)
        w.title("Účet Xiaomi")
        w.configure(bg=A.BG)
        w.transient(app.settings)
        w.protocol("WM_DELETE_WINDOW", self.close)
        A._titlebar(w, app.dark)
        body = tk.Frame(w, bg=A.BG)
        body.pack(fill="both", expand=True, padx=20, pady=16)
        tk.Label(body, text="Token z účtu Xiaomi", bg=A.BG, fg=A.TEXT, font=f.h2, anchor="w").pack(fill="x")
        self.lbl = tk.Label(body, text="Připojuji se k účtu Xiaomi…", bg=A.BG, fg=A.MUTED, font=f.body,
                            anchor="w", justify="left", wraplength=int(420 * app.px))
        self.lbl.pack(fill="x", pady=(4, 10))
        self.qr = tk.Label(body, bg="#ffffff")
        self.qr.pack(pady=(0, 8))
        self.btn_link = ttk.Button(body, text="Otevřít přihlášení v prohlížeči", command=self.open_link,
                                   state="disabled")
        self.btn_link.pack(anchor="w")
        cols = ("name", "model", "ip")
        self.tree = ttk.Treeview(body, columns=cols, show="headings", height=6, selectmode="browse")
        for c, t, wd in (("name", "Název", 160), ("model", "Model", 140), ("ip", "IP adresa", 110)):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=int(wd * app.px), anchor="w")
        self.tree.bind("<Double-1>", lambda e: self.use())
        bf = tk.Frame(body, bg=A.BG)
        bf.pack(side="bottom", fill="x", pady=(10, 0))
        self.btn_use = ttk.Button(bf, text="Použít vybraný", command=self.use, state="disabled")
        self.btn_use.pack(side="left")
        ttk.Button(bf, text="Zavřít", command=self.close).pack(side="right")
        self._qr_img = None
        threading.Thread(target=self._work, daemon=True).start()

    # vlákno -> GUI jen přes after()
    def _ui(self, fn, *a):
        try:
            self.win.after(0, fn, *a)
        except (tk.TclError, RuntimeError):
            pass

    def _status(self, text, bad=False):
        self._ui(lambda: self.lbl.winfo_exists() and self.lbl.configure(text=text, fg=A.BAD if bad else A.MUTED))

    def _work(self):
        try:
            self.cloud.start_qr()
            self._ui(self._show_qr)
            self.cloud.wait_login(lambda: self.cancelled)
            self._status("Přihlášeno. Načítám zařízení…")
            devs = self.cloud.devices(progress=self._status)
            self._ui(self._show_devices, devs)
        except CloudError as e:
            if not self.cancelled:
                self._status(str(e), bad=True)
        except Exception as e:  # noqa: BLE001
            if not self.cancelled:
                self._status(f"Nečekaná chyba: {e}", bad=True)

    def _show_qr(self):
        self.lbl.configure(text="V aplikaci Mi Home klepněte na + (nebo Profil) → Skenovat a naskenujte kód. "
                                "Pak přihlášení potvrďte v telefonu. Na tomto počítači můžete místo toho "
                                "otevřít přihlášení v prohlížeči.")
        self.btn_link.configure(state="normal")
        try:
            self._qr_img = tk.PhotoImage(data=base64.b64encode(self.cloud.qr_png).decode())
            k = max(1, round(self._qr_img.width() / int(240 * self.app.px)))
            if k > 1:
                self._qr_img = self._qr_img.subsample(k)
            self.qr.configure(image=self._qr_img)
        except tk.TclError:  # starší Tk neumí PNG
            self.qr.pack_forget()

    def _show_devices(self, devs):
        self.devices = sorted(devs, key=lambda d: (".fan." not in d["model"], d["name"]))
        self.qr.pack_forget()
        self.btn_link.pack_forget()
        self.tree.pack(fill="both", expand=True)
        for i, d in enumerate(self.devices):
            self.tree.insert("", "end", iid=str(i), values=(d["name"], d["model"], d["ip"] or "–"))
        fans = [i for i, d in enumerate(self.devices) if ".fan." in d["model"]]
        if self.devices:
            self.tree.selection_set(str(fans[0] if fans else 0))
            self.btn_use.configure(state="normal")
            self.lbl.configure(text="Vyberte ventilátor a klikněte na Použít vybraný." if fans else
                               "Na účtu není žádný ventilátor. Vyberte zařízení ručně.", fg=A.MUTED)
        else:
            self.lbl.configure(text="Na účtu se nenašlo žádné zařízení s tokenem.", fg=A.BAD)

    def open_link(self):
        if self.cloud.login_url:
            webbrowser.open(self.cloud.login_url)

    def use(self):
        sel = self.tree.selection()
        if not sel:
            return
        d = self.devices[int(sel[0])]
        self.app.use_xiaomi_device(d["ip"], d["token"], d["model"])
        self.close()

    def close(self):
        self.cancelled = True
        try:
            self.win.destroy()
        except tk.TclError:
            pass
