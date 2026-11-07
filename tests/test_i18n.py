"""Překlady: každý klíč _() má anglický text a anglické UI nemá českou diakritiku."""
import ast
import datetime as dt
import json
import os
import re
import string
import tempfile
import time
import unittest
from pathlib import Path

from antfan import i18n, ride, web
from antfan.i18n_en import EN

PKG = Path(__file__).resolve().parent.parent / "antfan"
CZ = re.compile("[ěščřžýáíéůúťďňóĚŠČŘŽÝÁÍÉŮÚŤĎŇÓ]")
# jména, která se nepřekládají (autonymum jazyka, názvy zařízení ze simulace)
ALLOWED = ("Čeština",)


def translation_keys():
    """{klíč: [soubor:řádek]} ze všech _(), N_() a plural() v balíčku."""
    keys = {}
    for path in sorted(PKG.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for n in ast.walk(tree):
            if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)):
                continue
            if n.func.id in ("_", "N_"):
                args = n.args[:1]
            elif n.func.id == "plural":
                args = n.args[1:]
            else:
                continue
            for a in args:
                if isinstance(a, ast.Constant) and isinstance(a.value, str):
                    keys.setdefault(a.value, []).append(f"{path.name}:{n.lineno}")
    return keys


def fields(s):
    return sorted({f for _t, f, _s, _c in string.Formatter().parse(s) if f is not None})


def czech_left(text):
    t = text
    for a in ALLOWED:
        t = t.replace(a, "")
    return bool(CZ.search(t))


class TestDictionary(unittest.TestCase):
    def test_every_key_translated(self):
        keys = translation_keys()
        self.assertGreater(len(keys), 300)
        missing = {k: v for k, v in keys.items() if k and k not in EN}
        self.assertEqual(missing, {}, "chybí anglický překlad")

    def test_placeholders_match(self):
        bad = {k: (fields(k), fields(v)) for k, v in EN.items() if fields(k) != fields(v)}
        self.assertEqual(bad, {})

    def test_english_has_no_czech(self):
        bad = [v for v in EN.values() if czech_left(v)]
        self.assertEqual(bad, [])

    def test_no_unused_entries(self):
        keys = translation_keys()
        unused = sorted(k for k in EN if k not in keys)
        self.assertEqual(unused, [])

    def test_plural(self):
        old = i18n.current()
        env = os.environ.pop("ANTFAN_LANG", None)
        try:
            i18n.set_language("cs")
            self.assertEqual([i18n.plural(n, "senzor", "senzory", "senzorů") for n in (1, 3, 5)],
                             ["senzor", "senzory", "senzorů"])
            i18n.set_language("en")
            self.assertEqual([i18n.plural(n, "senzor", "senzory", "senzorů") for n in (1, 3, 5)],
                             ["sensor", "sensors", "sensors"])
        finally:
            if env is not None:
                os.environ["ANTFAN_LANG"] = env
            i18n.set_language(old)

    def test_resolve(self):
        env = os.environ.pop("ANTFAN_LANG", None)
        try:
            self.assertEqual(i18n.resolve("cs"), "cs")
            self.assertEqual(i18n.resolve("en"), "en")
            self.assertIn(i18n.resolve("auto"), ("cs", "en"))
        finally:
            if env is not None:
                os.environ["ANTFAN_LANG"] = env

    def test_web_page(self):
        self.assertEqual(web.page_language("auto", "cs-CZ,cs;q=0.9,en;q=0.8"), "cs")
        self.assertEqual(web.page_language("auto", "en-US,en;q=0.9"), "en")
        self.assertEqual(web.page_language("en", "cs-CZ"), "en")
        self.assertEqual(web.page_language("cs", "en-US"), "cs")
        page = web.render_page("en")
        self.assertIn('lang="en"', page)
        self.assertFalse(czech_left(page), [m.group(0) for m in CZ.finditer(page)])
        self.assertIn("Připojuji", web.render_page("cs"))


try:
    import tkinter as tk

    _r = tk.Tk()
    _r.destroy()
    HAVE_TK = True
except Exception:  # noqa: BLE001
    HAVE_TK = False


def widget_texts(w, out):
    """Všechny texty widgetu a jeho potomků (Label, Button, Treeview, Canvas, Menu, titulky)."""
    try:
        if isinstance(w, (tk.Tk, tk.Toplevel)):
            out.append(("title", w.title()))
        try:
            t = w.cget("text")
            if t:
                out.append((w.winfo_class(), str(t)))
        except tk.TclError:
            pass
        cls = w.winfo_class()
        if cls == "Treeview":
            for c in w.cget("columns"):
                out.append(("heading", w.heading(c, "text")))
            for iid in w.get_children(""):
                out.extend(("row", str(v)) for v in w.item(iid, "values"))
        elif cls == "Canvas":
            for item in w.find_all():
                if w.type(item) == "text":
                    out.append(("canvas", w.itemcget(item, "text")))
        elif cls in ("TEntry", "Entry"):
            out.append(("entry", w.get()))
    except tk.TclError:
        pass
    for c in w.winfo_children():
        widget_texts(c, out)


@unittest.skipUnless(HAVE_TK, "bez displeje")
class GuiEnglish(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._env = {k: os.environ.get(k) for k in ("HOME", "APPDATA", "ANTFAN_LANG")}
        os.environ["HOME"] = os.environ["APPDATA"] = self.tmp.name
        os.environ.pop("ANTFAN_LANG", None)
        from antfan import config

        d = config.app_dir()
        (Path(d) / "config.json").write_text(json.dumps({
            "simulation": True, "theme": "light", "language": "en", "overlay_enabled": True,
            "drink_enabled": True, "selected": [[23456, 120, 0], [61234, 17, 0]]}))
        from antfan.app import App

        self.root = tk.Tk()
        self.app = App(self.root)

    def tearDown(self):
        try:
            self.app._cleanup()
            self.root.destroy()
        finally:
            for k, v in self._env.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
            i18n.set_language(None)
            self.tmp.cleanup()

    def pump(self, cond, timeout):
        end = time.monotonic() + timeout

        def check():
            if cond() or time.monotonic() > end:
                self.root.quit()
            else:
                self.root.after(50, check)

        self.root.after(50, check)
        self.root.mainloop()
        return cond()

    def czech_texts(self):
        out = []
        widget_texts(self.root, out)
        return [x for x in out if czech_left(x[1])]

    def test_english_ui(self):
        app = self.app
        self.assertEqual(i18n.current(), "en")
        self.assertEqual(app.btn_run.cget("text"), "Start")
        # všechny stránky Nastavení jsou postavené (jen skryté); projít i každou zobrazenou
        for page in app.pages:
            app.show_page(page)
        app.open_settings("diag")
        app.on_run_toggle()  # měření v simulaci
        self.pump(lambda: app.backend.state == "monitoring" and app.controller.hr_now is not None, 15)
        self.pump(lambda: False, 3)
        self.assertEqual(app.btn_run.cget("text"), "Stop")
        app.on_fan_test()
        self.pump(lambda: False, 1)
        self.assertEqual(self.czech_texts(), [])
        # shrnutí jízdy ze syntetických vzorků
        samples = [ride.Sample(float(i), 200, 200, 90, 140, 1, 250, 190) for i in range(900)]
        stats = ride.compute(samples, dt.datetime(2026, 1, 1, 18, 0), app.cfg.fan.max_level)
        app.show_ride_summary(stats)
        self.pump(lambda: False, 0.5)
        self.assertEqual(self.czech_texts(), [])
        # stav pro mobil
        from antfan import overlay

        st = overlay.overlay_state(app)
        self.assertFalse(czech_left(json.dumps(st, ensure_ascii=False)), st)

    def test_switch_language(self):
        app = self.app
        app.lang_var.set("cs")
        app.on_language()
        self.assertEqual(i18n.current(), "cs")
        self.assertEqual(app.btn_run.cget("text"), "Spustit měření")
        from antfan import config

        self.assertEqual(config.load().language, "cs")
        app.lang_var.set("en")
        app.on_language()
        self.assertEqual(app.btn_run.cget("text"), "Start")
        self.assertEqual(self.czech_texts(), [])


if __name__ == "__main__":
    unittest.main()
