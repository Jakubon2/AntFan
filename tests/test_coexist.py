"""Průvodce souběhem (coexist.py) s falešným seznamem procesů."""
import unittest

from antfan import coexist, usb_diag
from antfan.ant_backend import FE_TYPE, HR_TYPE, PM_TYPE, FoundDevice
from antfan.ble_backend import BLE_FE_TYPE, BLE_HR_TYPE, BLE_PM_TYPE
from antfan.coexist import Situation, advise, bt_counterparts, switch_to_bt, training_apps

WIN = [(4, "System", ""), (900, "explorer.exe", ""), (1200, "ROUVY.exe", "C:\\Program Files\\ROUVY\\ROUVY.exe"),
       (1300, "RouvyCrashpadHandler.exe", ""), (1400, "chrome.exe", "")]
MAC = [(1, "launchd", "/sbin/launchd"),
       (501, "ZwiftAppSilicon", "/Applications/Zwift.app/Contents/MacOS/ZwiftAppSilicon"),
       (502, "TrainerRoad", "/Applications/TrainerRoad.app/Contents/MacOS/TrainerRoad"),
       (503, "TrainerRoad Helper (GPU)", "/Applications/TrainerRoad.app/Contents/Frameworks/x")]

HR = FoundDevice(23456, HR_TYPE, 1)
TR = FoundDevice(61234, FE_TYPE, 5)
TR_PM = FoundDevice(61234, PM_TYPE, 5)
BT_HR = FoundDevice(52011, BLE_HR_TYPE, name="HRM-Dual 23456", rssi=-60)
BT_TR = FoundDevice(52012, BLE_FE_TYPE, name="Tacx Flux 61234")
BT_TR_CP = FoundDevice(52012, BLE_PM_TYPE, name="Tacx Flux 61234")
BT_OTHER = FoundDevice(52013, BLE_HR_TYPE, name="Polar H10 8C2F")


class Detection(unittest.TestCase):
    def test_windows(self):
        self.assertEqual(training_apps(WIN), ["ROUVY"])

    def test_mac(self):
        self.assertEqual(training_apps(MAC), ["Zwift", "TrainerRoad"])

    def test_nothing(self):
        self.assertEqual(training_apps([(1, "explorer.exe", ""), (2, "Garmin Express.exe", "")]), [])

    def test_mywhoosh_and_launcher(self):
        self.assertEqual(training_apps([(5, "MyWhoosh.exe", ""), (6, "ZwiftLauncher.exe", "")]),
                         ["MyWhoosh", "Zwift"])

    def test_busy_text(self):
        self.assertTrue(coexist.is_busy_error(usb_diag.busy_message(["ROUVY (ROUVY.exe)"], [])))
        self.assertTrue(coexist.is_busy_error(usb_diag.busy_message([], [])))
        self.assertFalse(coexist.is_busy_error("ANT+ dongle nenalezen."))

    def test_busy_message_mentions_bluetooth(self):
        self.assertIn("Bluetooth senzory", usb_diag.busy_message(["ROUVY (ROUVY.exe)"], []))


class Advise(unittest.TestCase):
    def test_none(self):
        self.assertIsNone(advise(Situation(), [HR, TR], []))

    def test_two_dongles(self):
        a = advise(Situation(apps=["ROUVY"], dongles=2), [HR, TR], [])
        self.assertEqual(a.kind, "two_dongles")

    def test_busy_switch_to_bt(self):
        a = advise(Situation(apps=["ROUVY"], dongles=1, busy=True), [HR, TR], [HR, TR, BT_HR, BT_TR])
        self.assertEqual(a.kind, "antfan_bt")
        self.assertTrue(a.can_switch)
        self.assertIn("ROUVY", a.short)
        self.assertIn("1–2 Bluetooth spojení", a.text)

    def test_busy_unknown_app_no_counterparts(self):
        a = advise(Situation(busy=True), [HR, TR], [HR, TR])
        self.assertEqual(a.kind, "antfan_bt")
        self.assertFalse(a.can_switch)
        self.assertIn("jiný program", a.short)

    def test_app_running_antfan_has_dongle(self):
        a = advise(Situation(apps=["Zwift"], dongles=1), [HR, TR], [])
        self.assertEqual(a.kind, "app_bt")
        self.assertIn("Bluetooth", a.text)

    def test_antfan_on_bt(self):
        a = advise(Situation(apps=["ROUVY"], busy=True), [BT_HR, BT_TR], [])
        self.assertEqual(a.kind, "bt_clash")


class Counterparts(unittest.TestCase):
    def test_by_name(self):
        cp = bt_counterparts([HR, TR], [HR, TR, TR_PM, BT_HR, BT_OTHER, BT_TR, BT_TR_CP])
        self.assertEqual(cp[HR.key].key, BT_HR.key)
        self.assertEqual(cp[TR.key].key, BT_TR.key)  # trenažér -> FTMS, ne CP

    def test_pm_prefers_cp(self):
        cp = bt_counterparts([TR_PM], [BT_TR, BT_TR_CP])
        self.assertEqual(cp[TR_PM.key].key, BT_TR_CP.key)

    def test_single_candidate_without_name(self):
        anon = FoundDevice(52020, BLE_HR_TYPE, name="")
        self.assertEqual(bt_counterparts([HR], [anon])[HR.key].key, anon.key)

    def test_ambiguous(self):
        self.assertIsNone(bt_counterparts([HR], [FoundDevice(1, BLE_HR_TYPE), FoundDevice(2, BLE_HR_TYPE)])[HR.key])

    def test_id_must_match_whole_number(self):
        other = FoundDevice(52030, BLE_HR_TYPE, name="HRM 234567")
        self.assertIsNone(bt_counterparts([HR], [other, BT_OTHER])[HR.key])

    def test_other_sensors_bt_version_is_not_counterpart(self):
        pm = FoundDevice(41001, PM_TYPE, 5)
        cp = bt_counterparts([pm], [pm, TR, BT_TR, BT_TR_CP])
        self.assertIsNone(cp[pm.key])

    def test_switch(self):
        new, missing = switch_to_bt([HR, TR], [BT_TR, BT_TR_CP])
        self.assertEqual([d.key for d in new], [HR.key, BT_TR.key])
        self.assertEqual(missing, [HR])


if __name__ == "__main__":
    unittest.main()
