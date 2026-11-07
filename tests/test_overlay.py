"""Testy stavu lišty navrchu: python -m unittest discover tests"""
import unittest
from types import SimpleNamespace as NS

from antfan import overlay
from antfan.config import AppConfig
from antfan.drink import Reminder


class Var:
    def __init__(self, v):
        self.v = v

    def get(self):
        return self.v


def make_app(**kw):
    cfg = AppConfig()
    cfg.fan.ip = "x"
    ctrl = NS(level=2, reason="výkon", hr_now=148, power_gap_s=0.0)
    app = NS(cfg=cfg, controller=ctrl, backend=NS(state="monitoring"), auto_var=Var(True),
             sim_var=Var(False), manual_level=0, fan_ok=True, drink=NS(current=None), devices={})
    for k, v in kw.items():
        setattr(app, k, v)
    return app


class State(unittest.TestCase):
    def test_auto(self):
        st = overlay.overlay_state(make_app())
        self.assertEqual((st["level_text"], st["reason"]), ("2", "výkon"))
        self.assertEqual(st["second"], "80 % max")  # 148 / 185
        self.assertEqual(st["alerts"], [])

    def test_manual(self):
        st = overlay.overlay_state(make_app(auto_var=Var(False), manual_level=0))
        self.assertEqual((st["level_text"], st["reason"]), ("ručně Vyp", ""))
        st = overlay.overlay_state(make_app(auto_var=Var(False), manual_level=3))
        self.assertEqual(st["level_text"], "ručně 3")

    def test_cooldown_and_idle(self):
        app = make_app()
        app.controller.reason = "dofukování ještě 1:40"
        self.assertEqual(overlay.overlay_state(app)["reason"], "dofukování 1:40")
        app.backend.state = "idle"
        self.assertEqual(overlay.overlay_state(app)["reason"], "neměří se")

    def test_wind_getattr(self):
        app = make_app(wind_kmh=38.2)
        app.controller.reason = "vítr"
        self.assertEqual(overlay.overlay_state(app)["reason"], "vítr 38 km/h")

    def test_second(self):
        app = make_app()
        app.cfg.overlay_second = "zone"
        self.assertEqual(overlay.overlay_state(app)["second"], "zóna 4")
        app.cfg.overlay_second = "none"
        self.assertEqual(overlay.overlay_state(app)["second"], "")
        app.cfg.overlay_second = "hr_pct"
        app.controller.hr_now = None
        self.assertEqual(overlay.overlay_state(app)["second"], "")

    def test_alerts(self):
        app = make_app(fan_ok=False)
        app.drink.current = Reminder(1, 200, 0.0)
        app.controller.power_gap_s = 5.2
        app.battery = {(1, 120): (10, 4)}
        app.batt_low = lambda k: True
        app.devices = {(1, 120): NS(type_name="Tep")}
        self.assertEqual(overlay.overlay_state(app)["alerts"],
                         ["Napijte se · 200 ml", "Slabá baterie · Tep", "Výpadek příjmu · 5 s",
                          "Ventilátor neodpovídá"])

    def test_fan_alert_only_when_used(self):
        app = make_app(fan_ok=False)
        app.sim_var = Var(True)
        self.assertEqual(overlay.overlay_state(app)["alerts"], [])
        app = make_app(fan_ok=False)
        app.backend.state = "idle"  # Auto bez měření ventilátor neřídí
        self.assertEqual(overlay.overlay_state(app)["alerts"], [])
        app.backend.state = "unplugged"
        self.assertEqual(overlay.overlay_state(app)["alerts"], ["Dongle odpojen"])

    def test_without_branch_features(self):
        app = make_app()  # bez battery / batt_low / wind_kmh
        self.assertEqual(overlay.overlay_state(app)["alerts"], [])


class Helpers(unittest.TestCase):
    def test_next_level(self):
        seq, auto, man = [], True, 0
        for _ in range(6):
            n = overlay.next_level(auto, man, 3)
            seq.append(n)
            auto, man = (True, man) if n == "auto" else (False, n)
        self.assertEqual(seq, [1, 2, 3, 0, "auto", 1])

    def test_zone(self):
        self.assertEqual(overlay.hr_zone(90, 185), 1)
        self.assertEqual(overlay.hr_zone(170, 185), 5)
        self.assertIsNone(overlay.hr_zone(None, 185))

    def test_short_reason(self):
        self.assertEqual(overlay.short_reason("tep drží stupeň"), "tep drží")
        self.assertEqual(overlay.short_reason("předstih"), "předstih")


from tests import czech_module  # noqa: E402

setUpModule, tearDownModule = czech_module()


if __name__ == "__main__":
    unittest.main()
