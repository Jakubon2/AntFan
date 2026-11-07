"""Chytré párování (pairing.py) na simulovaných průbězích hodnot."""
import queue
import time
import unittest

from antfan.ant_backend import FE_TYPE, HR_TYPE, PM_TYPE, FoundDevice, SimulatedBackend
from antfan.ble_backend import BLE_FE_TYPE, BLE_HR_TYPE, BLE_PM_TYPE, make_backend
from antfan.pairing import PairingSession


def run(tracks, t_end=20.0, step=0.5, prefer_ble=False):
    """tracks: {(id, typ): f(t) -> dict(value=, cadence=, events=, rssi=) nebo None (nevysílá)}."""
    s = PairingSession(0.0)
    t = 0.0
    while t <= t_end:
        for (dev_id, dev_type), f in tracks.items():
            v = f(t)
            if v is not None:
                s.feed(FoundDevice(dev_id, dev_type, 1, v.get("value"), t, cadence=v.get("cadence"),
                                   events=v.get("events"), rssi=v.get("rssi"), name=v.get("name", "")),
                       t)
        t += step
    return s.analyze(prefer_ble=prefer_ble)


def pm_mine(start=4.0, rssi=None):
    return lambda t: (dict(value=0, cadence=0, events=7, rssi=rssi) if t < start
                      else dict(value=200, cadence=85, events=int(t * 2) & 0xFF, rssi=rssi))


def pm_neighbor_riding(rssi=None):
    return lambda t: dict(value=230, cadence=90, events=int(t * 2) & 0xFF, rssi=rssi)


def pm_neighbor_idle(rssi=None):
    return lambda t: dict(value=0, cadence=0, events=3, rssi=rssi)


def hr_mine(start=5.0):
    return lambda t: dict(value=0, events=0) if t < start else dict(value=100 + int(t), events=int(t))


def hr_neighbor():
    return lambda t: dict(value=141, events=int(t))


def keys(res):
    return {d.key for d in res.selected}


class Pairing(unittest.TestCase):
    def test_mine_vs_neighbors(self):
        res = run({(1, HR_TYPE): hr_mine(), (2, HR_TYPE): hr_neighbor(),
                   (10, PM_TYPE): pm_mine(), (11, PM_TYPE): pm_neighbor_riding(),
                   (12, PM_TYPE): pm_neighbor_idle()})
        self.assertEqual(keys(res), {(1, HR_TYPE), (10, PM_TYPE)})
        self.assertEqual(res.hints, [])
        reacted = {v.device.key for v in res.verdicts if v.reacted}
        self.assertEqual(reacted, {(1, HR_TYPE), (10, PM_TYPE)})

    def test_power_meter_preferred_over_trainer(self):
        # trenažér 20 vysílá FE i PM se stejným ID, k tomu samostatný powermetr 10
        res = run({(20, FE_TYPE): pm_mine(), (20, PM_TYPE): pm_mine(), (10, PM_TYPE): pm_mine(6.0)})
        self.assertEqual(keys(res), {(10, PM_TYPE)})

    def test_trainer_only_once(self):
        res = run({(20, FE_TYPE): pm_mine(), (20, PM_TYPE): pm_mine(), (11, PM_TYPE): pm_neighbor_riding()})
        self.assertEqual(keys(res), {(20, FE_TYPE)})

    def test_trainer_reacting_only_as_pm(self):
        # FE stránky nechodí (starší trenažér), reaguje jen „powermetr“ se stejným ID
        res = run({(20, FE_TYPE): pm_neighbor_idle(), (20, PM_TYPE): pm_mine()})
        self.assertEqual(keys(res), {(20, FE_TYPE)})

    def test_sensor_wakes_up(self):
        # powermetr spí a ozve se až po zašlápnutí (bez klidové fáze)
        late_pm = lambda t: None if t < 6 else dict(value=180, cadence=80, events=int(t * 2))  # noqa: E731
        late_hr = lambda t: None if t < 7 else dict(value=98, events=int(t))  # noqa: E731
        res = run({(10, PM_TYPE): late_pm, (11, PM_TYPE): pm_neighbor_riding(),
                   (1, HR_TYPE): late_hr, (2, HR_TYPE): hr_neighbor()})
        self.assertEqual(keys(res), {(10, PM_TYPE), (1, HR_TYPE)})

    def test_hr_rise(self):
        rising = lambda t: dict(value=90 + int(t), events=int(t))  # noqa: E731
        res = run({(1, HR_TYPE): rising, (2, HR_TYPE): hr_neighbor()})
        self.assertEqual(keys(res), {(1, HR_TYPE)})

    def test_power_without_moving_counter_is_not_reaction(self):
        # výkon > 0, ale čítač událostí stojí (zbytková hodnota po dojetí) => nic
        stuck = lambda t: dict(value=0, cadence=0, events=5) if t < 4 else dict(value=150, cadence=0, events=5)  # noqa: E731
        res = run({(10, PM_TYPE): stuck, (11, PM_TYPE): pm_neighbor_idle()})
        self.assertFalse(res.verdicts[0].reacted or res.verdicts[1].reacted)
        self.assertEqual(keys(res), set())

    def test_rssi_breaks_tie(self):
        res = run({(1, HR_TYPE): hr_mine(), (3, HR_TYPE): hr_mine(),
                   (10, PM_TYPE): pm_mine(rssi=-80), (11, PM_TYPE): pm_mine(rssi=-45)})
        self.assertIn((11, PM_TYPE), keys(res))
        v = next(v for v in res.verdicts if v.device.key == (11, PM_TYPE))
        self.assertTrue(v.near)

    def test_ble_appears(self):
        bt = lambda t: None if t < 5 else dict(rssi=-55)  # noqa: E731
        bt_neighbor = lambda t: dict(rssi=-85)  # noqa: E731
        res = run({(500, BLE_HR_TYPE): bt, (501, BLE_HR_TYPE): bt_neighbor,
                   (600, BLE_FE_TYPE): bt, (600, BLE_PM_TYPE): bt})
        self.assertEqual(keys(res), {(500, BLE_HR_TYPE), (600, BLE_FE_TYPE)})

    def test_prefer_ant_unless_asked(self):
        bt = lambda t: None if t < 5 else dict(rssi=-55)  # noqa: E731
        tracks = {(1, HR_TYPE): hr_mine(), (500, BLE_HR_TYPE): bt}
        self.assertEqual(keys(run(tracks)), {(1, HR_TYPE)})
        self.assertEqual(keys(run(tracks, prefer_ble=True)), {(500, BLE_HR_TYPE)})

    def test_single_sensor_even_without_reaction(self):
        res = run({(1, HR_TYPE): hr_neighbor(), (10, PM_TYPE): pm_neighbor_riding()})
        self.assertEqual(keys(res), {(1, HR_TYPE), (10, PM_TYPE)})
        self.assertTrue(any("jediný" in line for line in res.summary_lines()))

    def test_nothing_found(self):
        res = run({})
        self.assertFalse(res.ok)
        self.assertIn("Nenašel se žádný senzor", res.hints[0])

    def test_nothing_reacts(self):
        res = run({(1, HR_TYPE): hr_neighbor(), (2, HR_TYPE): hr_neighbor(),
                   (10, PM_TYPE): pm_neighbor_riding(), (11, PM_TYPE): pm_neighbor_idle()})
        self.assertFalse(res.ok)
        text = " ".join(res.hints)
        self.assertIn("Žádný senzor nezareagoval", text)
        self.assertIn("Tepový pás nepoznám", text)
        self.assertIn("Výkon nepoznám", text)


class SimulatedNeighbors(unittest.TestCase):
    """SimulatedBackend + SimulatedBleBackend: sousedovy senzory nereagují."""

    def test_sim_scan(self):
        old = SimulatedBackend.SIM_REACT_S
        SimulatedBackend.SIM_REACT_S = 3.5
        q = queue.Queue()
        b = make_backend(q, simulation=True)
        s = PairingSession(time.monotonic())
        try:
            b.start_scan(7)
            t0 = time.monotonic()
            done = False
            while not done and time.monotonic() - t0 < 11:
                try:
                    ev = q.get(timeout=0.2)
                except queue.Empty:
                    continue
                if ev[0] == "found":
                    s.feed(ev[1], time.monotonic())
                done = ev[0] == "scan_done"
            self.assertTrue(done)
            res = s.analyze()
            self.assertEqual(keys(res), {(23456, HR_TYPE), (41001, PM_TYPE)})
            neighbors = {v.device.key for v in res.verdicts if not v.reacted}
            self.assertIn((31337, HR_TYPE), neighbors)
            self.assertIn((52777, PM_TYPE), neighbors)
            self.assertIn((52013, BLE_HR_TYPE), neighbors)
            res_bt = s.analyze(prefer_ble=True)
            self.assertEqual(keys(res_bt), {(52011, BLE_HR_TYPE), (41001, PM_TYPE)})
        finally:
            SimulatedBackend.SIM_REACT_S = old
            b.shutdown()


from tests import czech_module  # noqa: E402

setUpModule, tearDownModule = czech_module()


if __name__ == "__main__":
    unittest.main()
