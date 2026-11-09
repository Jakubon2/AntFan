"""Měření příjmu: % zpráv, výpadky a jejich příčina podle hlášení donglu."""
import unittest

from antfan import usb_diag
from antfan.rx import HR_TYPE, PM_TYPE, GapClassifier, RxMonitor

PAGE = [0x04, 0, 0, 0, 0, 0, 0, 80]


def feed(mon, t0, t1, rate=4.0, gaps=()):
    """Pošle zprávy rychlostí rate mezi t0 a t1, kromě intervalů v gaps."""
    t = t0
    while t < t1:
        if not any(a <= t < b for a, b in gaps):
            mon.on_page(PAGE, t)
        t += 1 / rate


class QualityTest(unittest.TestCase):
    def test_full_rate_is_100(self):
        m = RxMonitor(1, HR_TYPE, 0.0)
        feed(m, 0.0, 10.0, rate=m.rate_hz)
        self.assertGreaterEqual(m.quality(10.0), 97)

    def test_half_rate_is_about_50(self):
        m = RxMonitor(1, HR_TYPE, 0.0)
        feed(m, 0.0, 10.0, rate=m.rate_hz / 2)
        self.assertAlmostEqual(m.quality(10.0), 50, delta=5)


class GapCauseTest(unittest.TestCase):
    def _gap(self, events, dongle_reports=True):
        m = RxMonitor(1, PM_TYPE, 0.0)
        if dongle_reports:  # dongle už dřív nějakou zmeškanou zprávu ohlásil
            m.on_event(usb_diag.EV_RX_FAIL)
        m.on_page(PAGE, 0.0)
        for code in events:
            m.on_event(code)
        m.on_page(PAGE, 3.0)
        return m

    def test_dongle_reported_misses_means_radio(self):
        m = self._gap([usb_diag.EV_RX_FAIL] * 11)
        self.assertEqual(m.last_gap_cause, "radio")

    def test_lost_sync_means_radio_lost(self):
        m = self._gap([usb_diag.EV_RX_FAIL] * 3 + [usb_diag.EV_RX_FAIL_GO_TO_SEARCH])
        self.assertEqual(m.last_gap_cause, "radio-lost")

    def test_silent_dongle_means_pc(self):
        m = self._gap([])
        self.assertEqual(m.last_gap_cause, "pc")

    def test_dongle_that_never_reports_is_unknown(self):
        m = self._gap([], dongle_reports=False)
        self.assertEqual(m.last_gap_cause, "unknown")

    def test_counters_reset_after_page(self):
        m = self._gap([usb_diag.EV_RX_FAIL] * 11)
        m.on_page(PAGE, 3.25)
        m.on_page(PAGE, 6.0)  # další mezera bez hlášení donglu
        self.assertEqual(m.last_gap_cause, "pc")

    def test_pc_cause_counts_as_pc_side_even_if_others_received(self):
        a, b = RxMonitor(1, PM_TYPE, 0.0), RxMonitor(2, HR_TYPE, 0.0)
        g = GapClassifier()
        feed(b, 0.0, 3.0)
        a.on_event(usb_diag.EV_RX_FAIL)
        a.on_page(PAGE, 0.0)
        a.on_page(PAGE, 3.0)
        g.after_page(a, [a, b])
        all_n, single = g.summary(3.0)
        self.assertEqual((all_n, single), (1, {}))

    def test_radio_cause_on_one_sensor_is_single(self):
        a, b = RxMonitor(1, PM_TYPE, 0.0), RxMonitor(2, HR_TYPE, 0.0)
        g = GapClassifier()
        feed(b, 0.0, 3.0)
        a.on_page(PAGE, 0.0)
        for _ in range(11):
            a.on_event(usb_diag.EV_RX_FAIL)
        a.on_page(PAGE, 3.0)
        g.after_page(a, [a, b])
        all_n, single = g.summary(3.0)
        self.assertEqual(all_n, 0)
        self.assertEqual(list(single.values()), [1])


class NodePatchTest(unittest.TestCase):
    def test_events_reach_hook_and_rx_fail_is_not_stored(self):
        usb_diag.prepare()
        from openant.easy.node import Node

        node = Node.__new__(Node)  # bez USB
        import collections
        import threading

        node._events = collections.deque()
        node._event_cond = threading.Condition()
        seen = []
        node.antfan_event_hook = lambda ch, code: seen.append((ch, code))
        node._worker_event(0, usb_diag.EV_RX_FAIL, [0])
        node._worker_event(1, usb_diag.EV_RX_FAIL_GO_TO_SEARCH, [0])
        node._worker_event(1, usb_diag.EV_CHANNEL_CLOSED, [0])
        self.assertEqual(seen, [(0, 2), (1, 8)])
        self.assertEqual([e[1] for e in node._events], [8, 7])


if __name__ == "__main__":
    unittest.main()
