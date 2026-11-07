"""Plynulá rychlost, vítr podle rychlosti a výstup v % (python -m unittest discover tests)."""
from __future__ import annotations

import queue
import time
import unittest

from antfan.controller import ControlConfig, Controller
from antfan.miio_fan import FanWorker
from antfan.rx import FE_TYPE, PM_TYPE, decode_speed
from antfan.vitr import PctLimiter, pct_to_level, pct_to_range, range_to_pct, smooth_pct, wind_pct


def cfg(**kw) -> ControlConfig:
    base = dict(threshold_mode="absolute", power_thresholds=[100, 200, 300], hr_thresholds=[110, 140, 160],
                power_smoothing_s=1.0, hr_smoothing_s=1.0, down_delay_s=10.0, cooldown_s=0.0,
                output_mode="smooth", smooth_min_pct=20, smooth_down_pct_s=2.0, source_mode="power")
    base.update(kw)
    return ControlConfig(**base)


def run(ctrl: Controller, t0: float, t1: float, step: float = 0.25, **feed):
    """Krmí controller stálými hodnotami od t0 do t1, vrací poslední pct."""
    t = t0
    while t <= t1 + 1e-9:
        for k, v in feed.items():
            ctrl.feed(k, v, now=t)
        ctrl.tick(t)
        t += step
    return ctrl.pct


class Mapping(unittest.TestCase):
    def test_smooth(self):
        th = [100, 200, 300]
        self.assertEqual(smooth_pct(None, th, 20), 0)
        self.assertEqual(smooth_pct(99, th, 20), 0)
        self.assertEqual(smooth_pct(100, th, 20), 20)
        self.assertAlmostEqual(smooth_pct(200, th, 20), 60)
        self.assertEqual(smooth_pct(300, th, 20), 100)
        self.assertEqual(smooth_pct(900, th, 20), 100)
        self.assertEqual(smooth_pct(150, [150], 20), 100)

    def test_wind(self):
        self.assertEqual(wind_pct(None, 45), 0)
        self.assertEqual(wind_pct(4.9, 45), 0)
        self.assertAlmostEqual(wind_pct(22.5, 45), 50)
        self.assertEqual(wind_pct(45, 45), 100)
        self.assertEqual(wind_pct(70, 45), 100)

    def test_levels_and_range(self):
        self.assertEqual(pct_to_level(0, 3), 0)
        self.assertEqual(pct_to_level(5, 3), 1)
        self.assertEqual(pct_to_level(50, 3), 2)
        self.assertEqual(pct_to_level(100, 3), 3)
        self.assertEqual(pct_to_range(50, 1, 100), 50)
        self.assertEqual(pct_to_range(100, 1, 100), 100)
        self.assertEqual(pct_to_range(1, 1, 100), 2)
        self.assertAlmostEqual(range_to_pct(50, 0, 100), 50)

    def test_decode_speed(self):
        mm = 10000  # 10 m/s = 36 km/h
        page = [0x10, 25, 0, 0, mm & 0xFF, mm >> 8, 0xFF, 0x24]
        self.assertAlmostEqual(decode_speed(FE_TYPE, page), 36.0)
        self.assertIsNone(decode_speed(PM_TYPE, page))
        self.assertIsNone(decode_speed(FE_TYPE, [0x19] + page[1:]))
        self.assertIsNone(decode_speed(FE_TYPE, [0x10, 0, 0, 0, 0xFF, 0xFF, 0, 0]))

    def test_limiter(self):
        lim = PctLimiter()
        self.assertEqual(lim.update(80, 80, 5, 2, 0), 80)
        self.assertEqual(lim.update(30, 30, 5, 2, 1), 80)   # čeká
        self.assertEqual(lim.update(30, 30, 5, 2, 5), 80)   # ještě čeká (začal v 1 s)
        self.assertAlmostEqual(lim.update(30, 30, 5, 2, 6), 78)   # 1 s × 2 %/s
        self.assertEqual(lim.update(90, 90, 5, 2, 7), 90)   # zvýšení hned


class SmoothControl(unittest.TestCase):
    def test_rises_immediately_and_falls_slowly(self):
        c = Controller(cfg(), 3)
        self.assertAlmostEqual(run(c, 0, 5, power=200), 60, delta=0.5)
        self.assertEqual(c.level, 2)
        self.assertAlmostEqual(run(c, 5.25, 8, power=300), 100, delta=0.5)
        # pokles na 100 W: prodleva 10 s drží 100 %
        p = run(c, 8.25, 17, power=100)
        self.assertEqual(p, 100)
        # pak klesá nejvýš 2 %/s
        p = run(c, 17.25, 27, power=100)
        self.assertGreater(p, 70)
        self.assertLess(p, 100)
        p = run(c, 27.25, 80, power=100)
        self.assertAlmostEqual(p, 28, delta=0.5)   # hystereze 20 W: drží cíl pro 120 W

    def test_hysteresis_keeps_speed(self):
        c = Controller(cfg(power_hysteresis=20), 3)
        run(c, 0, 5, power=200)
        p = run(c, 5.25, 60, power=185)   # 185 + 20 >= 200 => drží
        self.assertAlmostEqual(p, 60, delta=0.5)

    def test_off_below_first_threshold(self):
        c = Controller(cfg(power_hysteresis=0), 3)
        run(c, 0, 3, power=150)
        p = run(c, 3.25, 120, power=50)
        self.assertEqual(p, 0)
        self.assertEqual(c.level, 0)

    def test_hr_mode_and_smart_hold(self):
        c = Controller(cfg(source_mode="hr"), 3)
        self.assertAlmostEqual(run(c, 0, 5, hr=150), 20 + 80 * 40 / 50, delta=0.5)
        c = Controller(cfg(source_mode="smart"), 3)
        run(c, 0, 5, power=300, hr=165)
        # výkon spadl (odpočinek), tep stále vysoko => drží 100 %
        p = run(c, 5.25, 60, power=50, hr=165)
        self.assertAlmostEqual(p, 100, delta=0.5)

    def test_cooldown(self):
        c = Controller(cfg(cooldown_s=60, cooldown_level=1, down_delay_s=0, smooth_down_pct_s=100), 3)
        run(c, 0, 5, power=250)
        p = run(c, 5.25, 20, power=0)
        self.assertAlmostEqual(p, 100 / 3, delta=0.5)
        self.assertIn("dofukování", c.reason)
        p = run(c, 20.25, 70, power=0)
        self.assertEqual(p, 0)

    def test_lead(self):
        c = Controller(cfg(power_smoothing_s=30), 3)
        c.cfg.lead_enabled, c.cfg.lead_s = True, 3.0  # z feature/predstih
        run(c, 0, 30, power=100)
        p = run(c, 30.25, 34, power=300)
        self.assertGreater(p, 95)   # bez předstihu by průměr za 30 s byl ~130 W

    def test_steps_mode_untouched(self):
        c = Controller(cfg(output_mode="steps"), 3)
        run(c, 0, 5, power=250)
        self.assertIsNone(c.pct)
        self.assertEqual(c.level, 2)


class WindControl(unittest.TestCase):
    def test_wind_follows_speed(self):
        c = Controller(cfg(source_mode="wind", wind_floor=False, wind_full_kmh=45), 3)
        self.assertAlmostEqual(run(c, 0, 5, speed=36.0, power=200), 80, delta=0.5)
        self.assertIn("vítr 36 km/h", c.reason)
        p = run(c, 5.25, 30, speed=2.0, power=200)
        self.assertEqual(p, 0)

    def test_wind_floor_uphill(self):
        c = Controller(cfg(source_mode="wind", wind_floor=True), 3)
        p = run(c, 0, 10, speed=9.0, power=300)   # pomalu do kopce, vysoký výkon
        self.assertAlmostEqual(p, 100, delta=0.5)
        self.assertIn("minimum", c.reason)
        c = Controller(cfg(source_mode="wind", wind_floor=False), 3)
        p = run(c, 0, 10, speed=9.0, power=300)
        self.assertAlmostEqual(p, 20, delta=0.5)

    def test_no_speed(self):
        c = Controller(cfg(source_mode="wind", wind_floor=False), 3)
        run(c, 0, 5, power=200)
        self.assertEqual(c.pct, 0)
        self.assertEqual(c.reason, "chybí rychlost")


# ------------------------------------------------------------------ FanWorker
class FakePctFan:
    def __init__(self, quantize: float | None = None, percent=True):
        self.cfg = type("C", (), {"max_level": 3})()
        self.calls: list = []
        self.on, self.pct, self.level = False, 0.0, 0
        self.quantize = quantize
        self.percent = percent

    def supports_percent(self):
        return self.percent

    def apply_quiet(self):
        return []

    def set_percent(self, pct):
        self.calls.append(("pct", round(pct)))
        self.on = pct > 0
        if pct > 0:
            self.pct = round(pct / self.quantize) * self.quantize if self.quantize else pct

    def get_percent(self):
        self.calls.append(("get",))
        return self.on, self.pct

    def set_level(self, level):
        self.calls.append(("lvl", level))
        self.on, self.level = level > 0, level

    def get_state(self):
        return self.on, self.level


def wait(cond, timeout=3.0):
    t = time.monotonic()
    while time.monotonic() - t < timeout:
        if cond():
            return True
        time.sleep(0.02)
    return False


class Worker(unittest.TestCase):
    def setUp(self):
        self.w = FanWorker(queue.Queue())
        self.w.POLL_S = 0.3

    def tearDown(self):
        self.w.stop()

    def test_sends_only_big_changes(self):
        fan = FakePctFan()
        self.w.configure(fan)
        self.w.set_desired(2, 50.0)
        self.assertTrue(wait(lambda: ("pct", 50) in fan.calls))
        for v in (51, 52, 53, 54):
            self.w.set_desired(2, float(v))
            time.sleep(0.05)
        time.sleep(0.2)
        self.assertEqual([c for c in fan.calls if c[0] == "pct"], [("pct", 50)])
        self.w.set_desired(2, 56.0)
        self.assertTrue(wait(lambda: ("pct", 56) in fan.calls))
        self.w.set_desired(0, 0.0)
        self.assertTrue(wait(lambda: ("pct", 0) in fan.calls))
        self.assertTrue(self.w.percent_capable)

    def test_poll_corrects_manual_change(self):
        fan = FakePctFan()
        self.w.configure(fan)
        self.w.set_desired(2, 60.0)
        self.assertTrue(wait(lambda: ("pct", 60) in fan.calls))
        fan.pct = 20.0   # někdo přepnul ventilátor dálkovým ovladačem
        self.assertTrue(wait(lambda: [c for c in fan.calls if c[0] == "pct"].count(("pct", 60)) >= 2))

    def test_quantizing_fan_no_loop(self):
        fan = FakePctFan(quantize=33.3)
        self.w.configure(fan)
        self.w.set_desired(2, 50.0)
        self.assertTrue(wait(lambda: fan.calls.count(("get",)) >= 3, timeout=8))
        self.assertLessEqual([c for c in fan.calls if c[0] == "pct"].count(("pct", 50)), 2)

    def test_stepped_fan_gets_level(self):
        fan = FakePctFan(percent=False)
        self.w.configure(fan)
        self.w.set_desired(2, 60.0)
        self.assertTrue(wait(lambda: ("lvl", 2) in fan.calls))
        self.assertFalse(any(c[0] == "pct" for c in fan.calls))
        self.assertIs(self.w.percent_capable, False)


if __name__ == "__main__":
    unittest.main()
