"""GUI v simulaci: chytré párování a průvodce souběhem (bez vizuální kontroly).

Ověřuje stav widgetů a App. Bez displeje (Tk nejde spustit) se přeskočí.
"""
import json
import os
import tempfile
import time
import unittest
from pathlib import Path

from antfan import coexist, pairing, usb_diag
from antfan.ant_backend import HR_TYPE, PM_TYPE, SimulatedBackend
from antfan.ble_backend import BLE_HR_TYPE

try:
    import tkinter as tk

    _r = tk.Tk()
    _r.destroy()
    HAVE_TK = True
except Exception:  # noqa: BLE001
    HAVE_TK = False


@unittest.skipUnless(HAVE_TK, "bez displeje")
class GuiPairing(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._env = {k: os.environ.get(k) for k in ("HOME", "APPDATA")}
        os.environ["HOME"] = os.environ["APPDATA"] = self.tmp.name
        from antfan import config

        d = config.app_dir()
        (Path(d) / "config.json").write_text(json.dumps({"simulation": True, "theme": "light"}))
        self._old = (pairing.PAIR_SCAN_S, SimulatedBackend.SIM_REACT_S)
        pairing.PAIR_SCAN_S, SimulatedBackend.SIM_REACT_S = 8, 3.5
        from antfan.app import App

        self.root = tk.Tk()
        self.app = App(self.root)
        self.app.coex_probe = lambda count: coexist.Situation(apps=["ROUVY"], dongles=1)

    def tearDown(self):
        pairing.PAIR_SCAN_S, SimulatedBackend.SIM_REACT_S = self._old
        try:
            self.app._cleanup()
            self.root.destroy()
        finally:
            for k, v in self._env.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
            self.tmp.cleanup()

    def pump(self, cond, timeout):
        """Běží mainloop, dokud neplatí cond (root.update() na Tk 8.5 visí)."""
        end = time.monotonic() + timeout

        def check():
            if cond() or time.monotonic() > end:
                self.root.quit()
            else:
                self.root.after(50, check)

        self.root.after(50, check)
        self.root.mainloop()
        return cond()

    def test_flow(self):
        app = self.app
        self.assertTrue(app.cfg.simulation)
        # průvodce: běží Rouvy, AntFan má dongle -> doporučení (c)
        app._coex_start()
        self.assertTrue(self.pump(lambda: app.coex_advice is not None, 5))
        self.assertEqual(app.coex_advice.kind, "app_bt")
        self.assertEqual(app.coex_bar.winfo_manager(), "pack")

        # chytré párování: vlastní senzory reagují, sousedovy ne
        app.on_pair()
        self.assertEqual(app.pair_box.winfo_manager(), "pack")
        self.assertIn("Hledám", app.lbl_pair_title.cget("text"))
        self.assertTrue(self.pump(lambda: app.pair_result is not None, 20))
        res = app.pair_result
        self.assertEqual({d.key for d in res.selected}, {(23456, HR_TYPE), (41001, PM_TYPE)})
        texts = [w.cget("text") for w in app.pair_box.winfo_children() if isinstance(w, tk.Label)]
        self.assertTrue(any("sousedům" in t and "31337" in t for t in texts), texts)

        # změna motivu uprostřed: pruh i návrh se přestaví ze stavu
        app._rebuild_ui(True)
        self.root.update_idletasks()
        self.assertEqual(app.pair_box.winfo_manager(), "pack")
        self.assertEqual(app.coex_bar.winfo_manager(), "pack")

        app.on_pair_apply()
        self.assertEqual(app.selected, {(23456, HR_TYPE), (41001, PM_TYPE)})
        self.assertEqual(app.pair_box.winfo_manager(), "")
        from antfan import config

        self.assertEqual(len(config.load().selected), 2)

        # dongle drží Rouvy -> doporučení (b) a přepnutí na Bluetooth
        app._coex_on_error(usb_diag.busy_message(["ROUVY (ROUVY.exe)"], []))
        self.assertEqual(app.coex_advice.kind, "antfan_bt")
        self.assertTrue(app.coex_advice.can_switch)
        app.on_coex_switch()
        self.assertIn((52011, BLE_HR_TYPE), app.selected)
        self.assertIn((41001, PM_TYPE), app.selected)  # powermetr nemá BT verzi
        self.assertIn("Bez Bluetooth verze", app.coex_note)

        # zavřít = do konce běhu nic, ani po další kontrole
        app.on_coex_close()
        self.assertEqual(app.coex_bar.winfo_manager(), "")
        app._coex_on_event(coexist.Situation(apps=["Zwift"]))
        self.assertEqual(app.coex_bar.winfo_manager(), "")
        app.coex_guide_var.set(False)
        app.on_coex_guide_toggle()
        self.assertFalse(config.load().coexist_guide)

    def test_nothing_found_advice(self):
        app = self.app
        SimulatedBackend.SIM_REACT_S = 99  # nikdo nezašlape
        app.on_pair()
        self.assertTrue(self.pump(lambda: app.pair_result is not None, 20))
        res = app.pair_result
        self.assertFalse(res.ok)
        self.assertTrue(res.hints)
        app.on_pair_cancel()
        self.assertEqual(app.pair_box.winfo_manager(), "")


if __name__ == "__main__":
    unittest.main()
