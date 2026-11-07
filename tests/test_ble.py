"""Testy Bluetooth části: `python -m unittest discover tests`.

Bajty jsou složené ručně podle specifikací Bluetooth SIG
(Heart Rate 0x2A37, Cycling Power Measurement 0x2A63, FTMS Indoor Bike Data 0x2AD2).
"""
import queue
import struct
import tempfile
import time
import unittest
from pathlib import Path

from antfan.ant_backend import HR_TYPE, PM_TYPE, FoundDevice, base_type, is_ble
from antfan.ble_backend import (BLE_FE_TYPE, BLE_HR_TYPE, BLE_PM_TYPE, BleRegistry, BleRx,
                                CombinedBackend, CrankCadence, parse_cp, parse_ftms_bike, parse_hr)


class HeartRate(unittest.TestCase):
    def test_uint8(self):
        self.assertEqual(parse_hr(bytes([0x00, 72])), 72)

    def test_uint8_with_contact_and_rr(self):
        # flags: kontakt podporován + zjištěn (0x06), RR intervaly (0x10)
        self.assertEqual(parse_hr(bytes([0x16, 145, 0x00, 0x04, 0x10, 0x04])), 145)

    def test_uint16(self):
        self.assertEqual(parse_hr(bytes([0x01]) + struct.pack("<H", 260)), 260)

    def test_uint16_with_energy(self):
        # 16bit tep + energy expended (0x08)
        self.assertEqual(parse_hr(bytes([0x09]) + struct.pack("<HH", 133, 500)), 133)

    def test_short(self):
        self.assertIsNone(parse_hr(b"\x00"))
        self.assertIsNone(parse_hr(b"\x01\x50"))


class CyclingPower(unittest.TestCase):
    def test_power_only(self):
        self.assertEqual(parse_cp(struct.pack("<Hh", 0x0000, 250)), {"power": 250, "crank": None})

    def test_crank_only(self):
        data = struct.pack("<HhHH", 0x0020, 312, 1000, 51200)
        self.assertEqual(parse_cp(data), {"power": 312, "crank": (1000, 51200)})

    def test_crank_after_balance_torque_wheel(self):
        flags = 0x0001 | 0x0004 | 0x0010 | 0x0020
        data = (struct.pack("<Hh", flags, 199) + bytes([100]) + struct.pack("<H", 1234)
                + struct.pack("<IH", 99999, 4000) + struct.pack("<HH", 77, 2048))
        self.assertEqual(parse_cp(data), {"power": 199, "crank": (77, 2048)})

    def test_negative_power_is_signed(self):
        self.assertEqual(parse_cp(struct.pack("<Hh", 0, -5))["power"], -5)

    def test_crank_cadence(self):
        cc = CrankCadence()
        self.assertIsNone(cc.update((10, 0), 0.0))
        # 1 otáčka za 0,666 s (682/1024) => 90 rpm
        self.assertEqual(cc.update((11, 683), 0.7), 90)
        # stejná událost znovu (notifikace mezi otáčkami) => kadence drží
        self.assertEqual(cc.update((11, 683), 1.0), 90)
        # přetečení čítačů 16 bitů
        cc2 = CrankCadence()
        cc2.update((65535, 65000), 0.0)
        self.assertEqual(cc2.update((0, (65000 + 1024) & 0xFFFF), 1.0), 60)
        # klika stojí déle než 3 s => 0 rpm
        self.assertEqual(cc.update((11, 683), 4.5), 0)


class Ftms(unittest.TestCase):
    def test_speed_cadence_power(self):
        # More Data = 0 => rychlost je přítomná; kadence (bit 2), výkon (bit 6)
        flags = 0x0004 | 0x0040
        data = struct.pack("<HHHh", flags, 3050, 180, 230)
        self.assertEqual(parse_ftms_bike(data), {"power": 230, "cadence": 90})

    def test_more_data_without_speed(self):
        flags = 0x0001 | 0x0040
        self.assertEqual(parse_ftms_bike(struct.pack("<Hh", flags, 150)), {"power": 150, "cadence": None})

    def test_all_fields_before_power(self):
        # průměrná rychlost, kadence, průměrná kadence, vzdálenost (24 bit), odpor, výkon, průměrný výkon
        flags = 0x0002 | 0x0004 | 0x0008 | 0x0010 | 0x0020 | 0x0040 | 0x0080
        data = (struct.pack("<HH", flags, 2500) + struct.pack("<H", 2400) + struct.pack("<H", 170)
                + struct.pack("<H", 160) + (12345).to_bytes(3, "little") + struct.pack("<h", 20)
                + struct.pack("<h", 275) + struct.pack("<h", 200))
        self.assertEqual(parse_ftms_bike(data), {"power": 275, "cadence": 85})

    def test_cadence_only_split_message(self):
        flags = 0x0001 | 0x0004
        self.assertEqual(parse_ftms_bike(struct.pack("<HH", flags, 172)), {"power": None, "cadence": 86})

    def test_truncated(self):
        flags = 0x0040
        self.assertEqual(parse_ftms_bike(struct.pack("<HH", flags, 1000)), {"power": None, "cadence": None})


class Types(unittest.TestCase):
    def test_names_and_types(self):
        self.assertEqual(FoundDevice(1, BLE_HR_TYPE).type_name, "Tepový pás (BT)")
        self.assertEqual(FoundDevice(1, BLE_PM_TYPE).type_name, "Powermetr (BT)")
        self.assertEqual(FoundDevice(1, BLE_FE_TYPE).type_name, "Trenažér (BT)")
        self.assertEqual(FoundDevice(1, HR_TYPE).type_name, "Tepový pás")
        self.assertTrue(is_ble(BLE_PM_TYPE) and not is_ble(PM_TYPE))
        self.assertEqual(base_type(BLE_PM_TYPE), PM_TYPE)


class Registry(unittest.TestCase):
    def test_stable_ids_and_persistence(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "ble.json"
            r = BleRegistry(p)
            a = r.id_for("aa:bb:cc:dd:ee:ff", "Polar H10 1234")
            b = r.id_for("11:22:33:44:55:66")
            self.assertNotEqual(a, b)
            self.assertTrue(10000 <= a <= 99999)
            self.assertEqual(r.id_for("AA:BB:CC:DD:EE:FF"), a)
            r2 = BleRegistry(p)
            self.assertEqual(r2.lookup(a), ("AA:BB:CC:DD:EE:FF", "Polar H10 1234"))


class Quality(unittest.TestCase):
    def test_rate_estimate(self):
        rx = BleRx("x", 0.0)
        for i in range(40):  # 4 Hz
            rx.on_notify(i * 0.25)
        self.assertEqual(rx.quality(10.0), 100)
        rx2 = BleRx("y", 0.0)
        for i in range(10):  # 1 Hz, polovina ztracená v posledních 5 s
            if i < 5 or i % 2 == 0:
                rx2.on_notify(float(i))
        q = rx2.quality(10.0)
        self.assertTrue(40 <= q <= 70, q)
        self.assertIsNone(BleRx("z", 0.0).quality(1.0))


class FakePart:
    """Dílčí backend s ručně řízenými událostmi."""

    def __init__(self, events):
        self.events = events
        self.state = "idle"
        self.calls = []

    def start_scan(self, duration):
        self.calls.append("scan")
        self.state = "scanning"

    def start_monitor(self, devices):
        self.calls.append(("monitor", [d.key for d in devices]))
        self.state = "monitoring"

    def stop(self):
        self.calls.append("stop")
        self.state = "idle"

    def reset(self):
        pass

    def rx_quality(self):
        return {}

    def rx_diagnosis(self):
        return 0, {}

    def shutdown(self):
        pass


def drain(q):
    out = []
    while True:
        try:
            out.append(q.get_nowait())
        except queue.Empty:
            return out


class Combined(unittest.TestCase):
    def make(self, dongle=True):
        q = queue.Queue()
        cb = CombinedBackend(q, FakePart, FakePart, dongle_present=lambda: dongle)
        return q, cb

    def test_scan_both_then_one_scan_done(self):
        q, cb = self.make()
        cb.start_scan(5)
        self.assertEqual(cb.state, "scanning")
        cb.ant.events.put(("found", FoundDevice(1, HR_TYPE)))
        cb.ble.events.put(("found", FoundDevice(2, BLE_HR_TYPE)))
        cb.ant.events.put(("ant_status", "Vyhledávání dokončeno – nalezeno 1 senzorů"))
        cb.ant.events.put(("scan_done",))
        self.assertEqual(cb.state, "scanning")
        self.assertNotIn(("scan_done",), drain(q))
        cb.ble.events.put(("scan_done",))
        ev = drain(q)
        self.assertEqual(ev[-1], ("scan_done",))
        self.assertIn("nalezeno 2 senzorů", ev[-2][1])
        self.assertEqual(cb.state, "idle")

    def test_scan_without_dongle_runs_ble_only(self):
        q, cb = self.make(dongle=False)
        cb.start_scan(5)
        self.assertNotIn("scan", cb.ant.calls)
        self.assertIn("scan", cb.ble.calls)
        cb.ble.events.put(("scan_done",))
        ev = drain(q)
        self.assertEqual(ev[-1], ("scan_done",))
        self.assertIn("ANT+ dongle nezapojen", ev[-2][1])
        self.assertFalse(any(e[0] == "ant_error" for e in ev))

    def test_scan_ant_error_does_not_block_ble(self):
        q, cb = self.make()
        cb.start_scan(5)
        cb.ant.events.put(("ant_error", "ANT+ dongle nejde otevřít.\n\nDetail"))
        self.assertEqual(cb.state, "scanning")
        cb.ble.events.put(("found", FoundDevice(2, BLE_HR_TYPE)))
        cb.ble.events.put(("scan_done",))
        ev = drain(q)
        self.assertFalse(any(e[0] == "ant_error" for e in ev))
        self.assertIn("ANT+: ANT+ dongle nejde otevřít.", ev[-2][1])

    def test_scan_both_fail(self):
        q, cb = self.make()
        cb.start_scan(5)
        cb.ant.events.put(("ant_error", "A"))
        cb.ble.events.put(("ant_error", "B"))
        ev = drain(q)
        self.assertEqual(ev[-1], ("ant_error", "A\n\nB"))

    def test_monitor_split(self):
        q, cb = self.make()
        ant_d, ble_d = FoundDevice(1, HR_TYPE), FoundDevice(2, BLE_PM_TYPE)
        cb.start_monitor([ant_d, ble_d])
        self.assertIn(("monitor", [ant_d.key]), cb.ant.calls)
        self.assertIn(("monitor", [ble_d.key]), cb.ble.calls)
        self.assertEqual(cb.state, "monitoring")
        # chyba donglu: BLE měří dál, stav zůstává monitoring
        cb.ant.state = "idle"
        cb.ant.events.put(("ant_error", "ANT+ dongle nenalezen."))
        cb.ble.events.put(("value", ble_d.key, "power", 200, 90))
        ev = drain(q)
        self.assertIn(("value", ble_d.key, "power", 200, 90), ev)
        self.assertEqual(cb.state, "monitoring")

    def test_monitor_ble_only_does_not_touch_ant(self):
        q, cb = self.make()
        cb.start_monitor([FoundDevice(2, BLE_HR_TYPE)])
        self.assertEqual(cb.ant.calls, ["stop"])
        cb.ant.events.put(("ant_status", "Zastaveno"))  # nesmí přepsat stav BLE
        cb.ble.events.put(("ant_status", "Bluetooth: připojen"))
        self.assertEqual([e[1] for e in drain(q)], ["Bluetooth: připojen"])

    def test_monitor_status_merged(self):
        q, cb = self.make()
        cb.start_monitor([FoundDevice(1, HR_TYPE), FoundDevice(2, BLE_HR_TYPE)])
        cb.ant.events.put(("ant_status", "Měřím: Tepový pás #1"))
        cb.ble.events.put(("ant_status", "Bluetooth: připojen"))
        self.assertEqual(drain(q)[-1][1], "Měřím: Tepový pás #1 · Bluetooth: připojen")


class Simulation(unittest.TestCase):
    def test_simulated_combined(self):
        from antfan.ble_backend import make_backend

        q = queue.Queue()
        b = make_backend(q, simulation=True)
        try:
            b.start_scan(3)
            t0 = time.monotonic()
            found = set()
            done = False
            while time.monotonic() - t0 < 6 and not done:
                try:
                    ev = q.get(timeout=0.2)
                except queue.Empty:
                    continue
                if ev[0] == "found":
                    found.add(ev[1].key)
                done = ev[0] == "scan_done"
            self.assertTrue(done)
            self.assertTrue(any(is_ble(k[1]) for k in found))
            self.assertTrue(any(not is_ble(k[1]) for k in found))
            b.start_monitor([FoundDevice(52011, BLE_HR_TYPE), FoundDevice(41001, PM_TYPE)])
            kinds = set()
            t0 = time.monotonic()
            while time.monotonic() - t0 < 3:
                try:
                    ev = q.get(timeout=0.2)
                except queue.Empty:
                    continue
                if ev[0] == "value":
                    kinds.add((ev[1][1], ev[2]))
            self.assertIn((BLE_HR_TYPE, "hr"), kinds)
            self.assertIn((PM_TYPE, "power"), kinds)
            self.assertEqual(b.state, "monitoring")
        finally:
            b.stop()
            b.shutdown()


from tests import czech_module  # noqa: E402

setUpModule, tearDownModule = czech_module()


if __name__ == "__main__":
    unittest.main()
