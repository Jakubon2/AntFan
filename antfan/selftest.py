"""Kontrola sestaveného programu: `AntFan.exe --selftest výsledek.txt`
(macOS: `AntFan.app/Contents/MacOS/AntFan --selftest výsledek.txt`).

Ověří, že do exe se dostalo všechno potřebné (openant, pyusb + libusb DLL,
cryptography, tkinter, bleak) a že platí naše opravy openant. Nic neotvírá,
dongle ani ventilátor nepotřebuje. Návratový kód 0 = v pořádku.
"""
from __future__ import annotations

import sys
import traceback


def run(out_path: str | None = None) -> int:
    lines: list[str] = []
    ok = True

    def check(name, fn):
        nonlocal ok
        try:
            detail = fn()
            lines.append(f"OK    {name}" + (f": {detail}" if detail else ""))
        except Exception:  # noqa: BLE001
            ok = False
            lines.append(f"CHYBA {name}\n{traceback.format_exc()}")

    def t_tk():
        import tkinter

        return f"Tk {tkinter.TkVersion}"

    def t_openant():
        import openant.devices.fitness_equipment  # noqa: F401
        import openant.devices.heart_rate  # noqa: F401
        import openant.devices.power_meter  # noqa: F401
        from openant.base import driver

        assert hasattr(driver, "USBDriver"), "openant nenašel pyusb (chybí USB ovladač)"
        return "USB ovladač k dispozici"

    def t_libusb():
        import libusb_package

        path = libusb_package.get_library_path()
        assert path, "chybí knihovna libusb-1.0 (dll/dylib)"
        assert libusb_package.get_libusb1_backend() is not None, "libusb backend nejde načíst"
        return str(path)

    def t_patches():
        from openant.base import driver
        from openant.devices.common import AntPlusDevice

        from . import usb_diag

        usb_diag.prepare()
        assert getattr(AntPlusDevice, "_antfan_channel_patched", False), "chybí oprava kanálů"
        assert getattr(driver.USBDriver, "_antfan_patched", False), "chybí oprava USB"

    def t_crypto():
        from .miio_fan import MiioClient

        c = MiioClient("127.0.0.1", "00112233445566778899aabbccddeeff")
        assert c.decrypt(c.encrypt(b'{"id":1}')) == b'{"id":1}'

    def t_fans():
        from . import fan_presets, fans, xiaomi_cloud, xiaomi_ui  # noqa: F401

        assert fans.map_level(2, 3, ("range", 1, 100)) == 67
        assert "dmaker.fan.1c" in fan_presets.PRESETS
        key = b"0123456789abcdef"
        assert xiaomi_cloud._rc4(key, xiaomi_cloud._rc4(key, b"abc")) == b"abc"
    def t_web():
        import json
        import queue
        import urllib.request

        from . import qr, web

        assert len(qr.encode("http://192.0.2.10:8686/m/" + web.new_key())) == 33
        ev: queue.Queue = queue.Queue()
        srv = web.WebServer(ev)
        srv.start(0, "k", host="127.0.0.1")
        try:
            srv.publish({"max_level": 3})
            base = f"http://127.0.0.1:{srv.port}/m/k"
            with urllib.request.urlopen(base + "/api/state", timeout=5) as r:
                assert json.loads(r.read())["max_level"] == 3
        finally:
            srv.stop()
        return "server a QR kód"
    def t_ble():
        import bleak

        from . import ble_backend

        assert ble_backend.HAVE_BLEAK, "ble_backend nenašel bleak"
        if sys.platform == "win32":
            # WinRT moduly, které bleak na Windows potřebuje (PyInstaller je musí přibalit)
            from bleak.backends.winrt import client, scanner  # noqa: F401

            bleak.BleakScanner()  # jen vytvoří objekt, adaptér neotvírá
        try:
            from importlib.metadata import version

            return f"bleak {version('bleak')}"
        except Exception:  # noqa: BLE001
            return "bleak"

    def t_app():
        from . import app  # noqa: F401

    check("tkinter", t_tk)
    check("openant", t_openant)
    check("libusb", t_libusb)
    check("opravy openant", t_patches)
    check("šifrování miIO", t_crypto)
    check("ventilátory", t_fans)
    check("web pro mobil", t_web)
    check("Bluetooth (bleak)", t_ble)
    check("aplikace", t_app)
    lines.append("VÝSLEDEK: " + ("v pořádku" if ok else "CHYBA"))
    text = "\n".join(lines)
    if out_path:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    if sys.stdout is not None:
        print(text)
    return 0 if ok else 1
