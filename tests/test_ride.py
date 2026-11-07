"""Výpočty shrnutí jízdy a profily na syntetických datech: python -m unittest discover tests"""
import datetime as dt
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from antfan import config, profiles, ride
from antfan.controller import ControlConfig

START = dt.datetime(2026, 11, 7, 10, 5)


def samples(powers, hrs=None, cad=90, fan=1, ftp=200, hr_max=190):
    hrs = hrs or [None] * len(powers)
    return [ride.Sample(float(i), p, p, cad if p else 0, h, fan, ftp, hr_max)
            for i, (p, h) in enumerate(zip(powers, hrs))]


class TestCalc(unittest.TestCase):
    def test_np_constant(self):
        self.assertAlmostEqual(ride.normalized_power([200] * 600), 200.0)

    def test_np_intervals_above_avg(self):
        # 1 min 400 W / 1 min 0 W: průměr 200 W, NP výrazně víc
        pw = ([400] * 60 + [0] * 60) * 10
        np_ = ride.normalized_power(pw)
        self.assertGreater(np_, 260)
        self.assertLess(np_, 400)

    def test_np_short(self):
        self.assertAlmostEqual(ride.normalized_power([100, 200]), 150)
        self.assertIsNone(ride.normalized_power([]))

    def test_power_zones(self):
        ftp = 200
        cases = {0: 0, 109: 0, 110: 1, 150: 1, 151: 2, 180: 2, 181: 3, 210: 3, 211: 4,
                 240: 4, 241: 5, 300: 5, 301: 6, 1000: 6}
        for w, z in cases.items():
            self.assertEqual(ride.power_zone(w, ftp), z, w)

    def test_hr_zones(self):
        for hr, z in {80: 0, 114: 0, 115: 1, 133: 1, 152: 2, 171: 3, 172: 4, 200: 4}.items():
            self.assertEqual(ride.hr_zone(hr, 190), z, hr)

    def test_decoupling(self):
        # stejný výkon, tep ve 2. polovině o 10 % vyšší => posun ≈ 9,1 %
        p = [200] * 1200
        h = [140] * 600 + [154] * 600
        d = ride.decoupling([(float(i), p[i], h[i]) for i in range(1200)])
        self.assertAlmostEqual(d, (1 - 140 / 154) * 100, places=3)
        self.assertAlmostEqual(ride.decoupling([(float(i), 200, 140) for i in range(600)]), 0.0)
        self.assertIsNone(ride.decoupling([(float(i), 200, None) for i in range(600)]))

    def test_compute(self):
        s = samples([200] * 1800 + [300] * 1800, [140] * 3600)
        st = ride.compute(s, START, 3)
        self.assertEqual(st.duration_s, 3600)
        self.assertAlmostEqual(st.avg_power, 250)
        self.assertEqual(st.max_power, 300)
        self.assertAlmostEqual(st.kj, 900)
        self.assertAlmostEqual(st.if_, st.np / 200)
        self.assertAlmostEqual(st.tss, st.if_ ** 2 * 100)
        self.assertEqual(st.power_zones[3], 1800)   # 200 W = 100 % FTP = Z4
        self.assertEqual(st.power_zones[5], 1800)   # 300 W = 150 % FTP = Z6
        self.assertTrue(st.worth_showing)

    def test_compute_zones_sum(self):
        s = samples(list(range(0, 400)) * 3, [100 + i % 90 for i in range(1200)])
        st = ride.compute(s, START, 3)
        self.assertAlmostEqual(sum(st.power_zones), st.duration_s)
        self.assertAlmostEqual(sum(st.hr_zones), st.duration_s)
        self.assertAlmostEqual(sum(st.fan_levels), st.duration_s)
        self.assertEqual(st.fan_levels[1], st.duration_s)

    def test_gap_not_counted(self):
        s = samples([200] * 400)
        for x in s[200:]:
            x.t += 120  # 2 min odpojený dongle
        st = ride.compute(s, START, 3)
        self.assertAlmostEqual(st.duration_s, 400)

    def test_short_or_empty_not_shown(self):
        self.assertFalse(ride.compute(samples([200] * 200), START).worth_showing)
        self.assertFalse(ride.compute(samples([None] * 900), START).worth_showing)
        self.assertTrue(ride.compute(samples([None] * 400, [120] * 400), START).worth_showing)

    def test_trim_cooldown(self):
        rec = ride.RideRecorder(START)
        for i in range(500):
            rec.add(1000.0 + i, 200 if i < 400 else 0, 200, 90, 140, 1, 200, 190)
        self.assertEqual(len(rec.trimmed()), 400)
        rec2 = ride.RideRecorder(START)
        for i in range(10):
            rec2.add(float(i), None, None, None, 120, 0, 200, 190)
        self.assertEqual(len(rec2.trimmed()), 10)


class TestCsv(unittest.TestCase):
    def test_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            s = samples([200, None, 0, 250] * 100, [140, 141, None, 150] * 100)
            path = ride.save_csv(s, START, Path(d))
            self.assertEqual(path.name, "2026-11-07_1005.csv")
            self.assertEqual(ride.save_csv(s, START, Path(d)).name, "2026-11-07_1005_2.csv")
            back, start = ride.load_csv(path)
            self.assertEqual(start, START)
            self.assertEqual([(x.power, x.hr, x.fan, x.ftp) for x in back],
                             [(x.power, x.hr, x.fan, x.ftp) for x in s])
            self.assertEqual(ride.compute(back, start).np, ride.compute(s, START).np)
            self.assertEqual(len(ride.list_rides(folder=Path(d))), 2)


class TestProfiles(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patch = mock.patch.object(config, "app_dir", lambda: Path(self.tmp.name))
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def test_old_config_migrates(self):
        old = {"fan": {"max_level": 3}, "control": {"ftp": 333, "hr_max": 177}, "theme": "dark"}
        (Path(self.tmp.name) / "config.json").write_text(json.dumps(old), encoding="utf-8")
        cfg = config.load()
        self.assertEqual(list(cfg.profiles), ["Výchozí"])
        self.assertEqual(cfg.active_profile, "Výchozí")
        self.assertEqual(cfg.control.ftp, 333)
        self.assertEqual(cfg.theme, "dark")

    def test_save_load_profiles(self):
        cfg = config.AppConfig()
        profiles.create(cfg, "  Tempo  ")
        cfg.control.ftp = 280
        config.save(cfg)
        raw = json.loads((Path(self.tmp.name) / "config.json").read_text(encoding="utf-8"))
        self.assertEqual(raw["control"]["ftp"], 280)  # starší verze vidí aktivní profil
        cfg2 = config.load()
        self.assertEqual(cfg2.active_profile, "Tempo")
        self.assertEqual(cfg2.control.ftp, 280)
        self.assertEqual(cfg2.profiles["Výchozí"].ftp, ControlConfig().ftp)

    def test_bad_active_profile(self):
        (Path(self.tmp.name) / "config.json").write_text(json.dumps(
            {"profiles": {"A": {"ftp": 250}}, "active_profile": "nic"}), encoding="utf-8")
        cfg = config.load()
        self.assertEqual(cfg.active_profile, "A")
        self.assertEqual(cfg.control.ftp, 250)

    def test_ops(self):
        cfg = config.AppConfig()
        profiles.create(cfg, "Jana")
        self.assertIsNot(cfg.profiles["Jana"], cfg.profiles["Výchozí"])
        with self.assertRaises(ValueError):
            profiles.create(cfg, "Jana")
        with self.assertRaises(ValueError):
            profiles.create(cfg, "   ")
        profiles.rename(cfg, "Jana", "Petr")
        self.assertEqual(list(cfg.profiles), ["Výchozí", "Petr"])
        self.assertEqual(cfg.active_profile, "Petr")
        profiles.delete(cfg, "Petr")
        self.assertEqual(cfg.active_profile, "Výchozí")
        with self.assertRaises(ValueError):
            profiles.delete(cfg, "Výchozí")


if __name__ == "__main__":
    unittest.main()
