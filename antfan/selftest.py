"""Kontrola sestaveného AntFan.exe: `AntFan.exe --selftest výsledek.txt`.

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
        assert path, "chybí libusb-1.0.dll"
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
