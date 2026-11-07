"""Dekódování baterie na ručně složených stránkách:  python -m unittest discover tests"""
import queue
import unittest

from antfan import battery as bat


class DecodeTest(unittest.TestCase):
    def test_common_page_low(self):
        # 0x52: byte 6 = 0x80 (0,5 V), byte 7 = stav 4 (slabá) | 3 V
        page = [0x52, 0xFF, 0x00, 0x10, 0x20, 0x00, 0x80, (4 << 4) | 3]
        self.assertEqual(bat.decode_battery(11, page), (None, bat.LOW, 3.5))

    def test_common_page_states(self):
        for st in (1, 2, 3, 4, 5):
            page = [0x52, 0xFF, 0, 0, 0, 0, 0, (st << 4) | 2]
            self.assertEqual(bat.decode_battery(17, page)[1], st)

    def test_common_page_invalid(self):
        # stav 7 = neplatný, celé volty 0xF = neplatné => nic
        self.assertIsNone(bat.decode_battery(11, [0x52, 0xFF, 0, 0, 0, 0, 0x00, 0x7F]))
        # neplatné napětí, ale platný stav
        self.assertEqual(bat.decode_battery(11, [0x52, 0xFF, 0, 0, 0, 0, 0x00, 0x2F]), (None, 2, None))

    def test_hr_page7(self):
        # stránka 7 s přepínačem (bit 7) – 64 %, 2,75 V, stav dobrá
        page = [0x87, 64, 0xC0, (2 << 4) | 2, 0, 0, 0, 120]
        self.assertEqual(bat.decode_battery(120, page), (64, bat.GOOD, 2.75))

    def test_hr_page7_no_pct(self):
        page = [0x07, 0xFF, 0x00, (5 << 4) | 2, 0, 0, 0, 120]
        self.assertEqual(bat.decode_battery(120, page), (None, bat.CRITICAL, 2.0))

    def test_hr_common_page_with_toggle(self):
        self.assertEqual(bat.decode_battery(120, [0xD2, 0xFF, 0, 0, 0, 0, 0, (3 << 4) | 3])[1], bat.OK)

    def test_other_pages_ignored(self):
        self.assertIsNone(bat.decode_battery(11, [0x10, 1, 0xFF, 90, 0, 0, 200, 0]))
        self.assertIsNone(bat.decode_battery(11, [0x07, 50, 0, 0x22, 0, 0, 0, 0]))  # 7 jen u HR
        self.assertIsNone(bat.decode_battery(120, [0x04, 0, 0, 0, 0, 0, 0, 120]))
        self.assertIsNone(bat.decode_battery(11, [0x52, 0xFF]))

    def test_sim_builders_roundtrip(self):
        self.assertEqual(bat.decode_battery(17, bat.page_common(4, 3.4)), (None, 4, 3.4))
        self.assertEqual(bat.decode_battery(120, bat.page_hr(85, 2, 2.9)), (85, 2, 2.9))


class TrackerTest(unittest.TestCase):
    def test_event_only_on_change(self):
        t = bat.BatteryTracker()
        key = (61234, 17)
        self.assertEqual(t.feed(key, bat.page_common(3, 3.7)), ("battery", key, None, 3))
        self.assertIsNone(t.feed(key, bat.page_common(3, 3.6)))  # napětí se nehlásí
        self.assertEqual(t.feed(key, bat.page_common(4, 3.4)), ("battery", key, None, 4))
        self.assertIsNone(t.feed(key, [0x19, 1, 90, 0, 0, 200, 0, 0]))


class LowTest(unittest.TestCase):
    def test_thresholds(self):
        self.assertTrue(bat.is_low(None, bat.LOW))
        self.assertFalse(bat.is_low(None, bat.OK))
        self.assertFalse(bat.is_low(None, bat.LOW, level=bat.CRITICAL))
        self.assertTrue(bat.is_low(None, bat.CRITICAL, level=bat.CRITICAL))
        self.assertTrue(bat.is_low(15, bat.GOOD))           # % má přednost
        self.assertFalse(bat.is_low(25, bat.LOW))
        self.assertFalse(bat.is_low(None, None))
        self.assertEqual(bat.text(80, 2), "80 %")
        self.assertEqual(bat.text(None, 4), "slabá")


class SimBackendTest(unittest.TestCase):
    def test_sim_sends_battery_and_one_goes_low(self):
        import time
        from antfan.ant_backend import SimulatedBackend
        q = queue.Queue()
        b = SimulatedBackend(q)
        b.start_monitor(list(b.SIM_DEVICES))
        got = {}
        end = time.monotonic() + 22
        while time.monotonic() < end:
            try:
                ev = q.get(timeout=0.5)
            except queue.Empty:
                continue
            if ev[0] == "battery":
                got.setdefault(ev[1], []).append((ev[2], ev[3]))
            if got.get((61234, 17), [None])[-1] == (None, 4):
                break
        b.stop()
        self.assertEqual(got[(23456, 120)][0], (85, 2))
        self.assertEqual(got[(41001, 11)], [(None, 2)])
        self.assertEqual(got[(61234, 17)], [(None, 3), (None, 4)])


from tests import czech_module  # noqa: E402

setUpModule, tearDownModule = czech_module()


if __name__ == "__main__":
    unittest.main()
