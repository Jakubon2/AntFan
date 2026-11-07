"""Testy výpočtu připomínky pití: python -m unittest discover tests"""
import unittest

from antfan import drink
from antfan.drink import DrinkTracker


def ride(tr, seconds, power=200, cadence=90, monitoring=True, t0=0.0, step=0.25):
    t, last = t0, None
    n = int(seconds / step)
    for _ in range(n + 1):
        r = tr.update(t, monitoring, power, cadence, 140)
        last = r if r is not None else last
        t += step
    return t, last


class Formula(unittest.TestCase):
    def test_base(self):
        self.assertEqual(drink.interval_min(None, 20), 15)
        self.assertEqual(drink.ml_per_hour(None, 20), 500)
        self.assertEqual(drink.ml_per_hour(None, None), 500)

    def test_intensity(self):
        self.assertEqual(drink.ml_per_hour(300, 20), 500)
        self.assertAlmostEqual(drink.ml_per_hour(650, 20), 625)
        self.assertEqual(drink.ml_per_hour(1200, 20), 750)
        self.assertEqual(drink.interval_min(800, 20), 12.5)
        self.assertEqual(drink.interval_min(1000, 20), 10)

    def test_heat(self):
        self.assertEqual(drink.ml_per_hour(None, 22), 500)
        self.assertEqual(drink.ml_per_hour(None, 26), 620)
        self.assertEqual(drink.ml_per_hour(1200, 40), 1050)  # strop horka 300 ml/h
        self.assertEqual(drink.interval_min(None, 26), 13)
        self.assertEqual(drink.interval_min(1200, 40), drink.MIN_INTERVAL_MIN)

    def test_long_ride(self):
        self.assertAlmostEqual(drink.interval_min(None, 20, ride_min=90), 13.5)

    def test_amount(self):
        self.assertEqual(drink.amount_ml(500, 15 * 60), 125)
        self.assertEqual(drink.amount_ml(750, 15 * 60), 200)  # 187,5 ml -> 200
        self.assertEqual(drink.amount_ml(800, 15 * 60), 200)
        self.assertEqual(drink.amount_ml(500, 10), 50)

    def test_parse(self):
        self.assertIsNone(drink.parse_temp(""))
        self.assertEqual(drink.parse_temp("24,5"), 24.5)
        self.assertRaises(ValueError, drink.parse_temp, "60")
        self.assertRaises(ValueError, drink.parse_temp, "x")
        self.assertEqual(drink.parse_interval(" "), 0)
        self.assertEqual(drink.parse_interval("10"), 10)
        self.assertRaises(ValueError, drink.parse_interval, "0")


class Tracker(unittest.TestCase):
    def test_disabled(self):
        tr = DrinkTracker(enabled=False, interval_override_s=5)
        _, r = ride(tr, 30)
        self.assertIsNone(r)
        self.assertEqual(tr.active_s, 0)

    def test_reminder_after_interval(self):
        tr = DrinkTracker(enabled=True, interval_override_s=10)
        t, r = ride(tr, 9)
        self.assertIsNone(r)
        t, r = ride(tr, 2, t0=t)
        self.assertIsNotNone(r)
        self.assertTrue(r.text.startswith("Napijte se · zhruba "))
        self.assertTrue(r.text.endswith(" ml"))

    def test_only_when_pedaling_and_monitoring(self):
        tr = DrinkTracker(enabled=True, interval_override_s=10)
        t, _ = ride(tr, 30, power=0, cadence=0)
        t, _ = ride(tr, 30, monitoring=False, t0=t)
        self.assertEqual(tr.active_s, 0)
        self.assertIsNone(tr.current)
        # coasting s kadencí 0, ale výkon > 0 (trenažér) se počítá
        ride(tr, 3, power=150, cadence=0, t0=t)
        self.assertGreater(tr.active_s, 2)

    def test_hr_only(self):
        tr = DrinkTracker(enabled=True, interval_override_s=5)
        t = 0.0
        for _ in range(40):
            tr.update(t, True, None, None, 130)
            t += 0.25
        self.assertGreater(tr.active_s, 9)

    def test_gap_not_counted(self):
        tr = DrinkTracker(enabled=True, interval_override_s=100)
        tr.update(0, True, 200, 90)
        tr.update(1, True, 200, 90)
        tr.update(600, True, 200, 90)  # uspaný počítač
        self.assertAlmostEqual(tr.active_s, 1)

    def test_hide_after_60s_and_dismiss(self):
        tr = DrinkTracker(enabled=True, interval_override_s=5)
        t, r = ride(tr, 6)
        self.assertIsNotNone(r)
        rid = r.id
        # bez šlapání (stojí), připomínka do 60 s zmizí
        t2, _ = ride(tr, 61, power=0, cadence=0, t0=t)
        self.assertIsNone(tr.current)
        t3, r = ride(tr, 6, t0=t2)
        self.assertIsNotNone(r)
        self.assertGreater(r.id, rid)
        tr.dismiss()
        self.assertIsNone(tr.current)

    def test_kj(self):
        tr = DrinkTracker(enabled=True, interval_override_s=10000)
        ride(tr, 600, power=250)
        self.assertAlmostEqual(tr.kj, 150, delta=1)
        self.assertAlmostEqual(tr.kj_per_h, 900, delta=5)
        self.assertEqual(tr.ml_h(), 750)

    def test_manual_interval_and_heat_amount(self):
        tr = DrinkTracker(enabled=True, temp_c=30, manual_min=20)
        self.assertEqual(tr.interval_s(), 1200)
        self.assertEqual(tr.next_amount(), drink.amount_ml(740, 1200))
        tr.temp_c = None
        self.assertEqual(tr.next_amount(), drink.amount_ml(500, 1200))
        self.assertIn("Každých 20 min", tr.summary())


if __name__ == "__main__":
    unittest.main()
