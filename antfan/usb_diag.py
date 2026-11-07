"""Diagnostika a zotavení ANT+ donglu.

Řeší hlavně situaci „dongle je připojený k jiné aplikaci“, i když žádná
neběží. Typické příčiny:
  * na pozadí běží Zwift Launcher, Garmin Express apod. (ikonka u hodin),
  * starý proces AntFan visí na pozadí (pythonw nemá okno),
  * po neúspěšném otevření zůstane dongle otevřený ve vlastním procesu
    (openant ho po chybě neuvolní – proto `patch_openant`),
  * dongle je v zaseknutém stavu – pomůže USB reset nebo přepojení.
"""
from __future__ import annotations

import gc
import json
import logging
import os
import subprocess
import sys
import threading
import time

log = logging.getLogger("antfan.usb")

ANT_USB_IDS = [(0x0FCF, 0x1008), (0x0FCF, 0x1009)]  # ANTUSB2, ANTUSB-m

# podřetězec v názvu procesu (malými písmeny) -> název pro uživatele
KNOWN_ANT_APPS = {
    "zwift": "Zwift / Zwift Launcher",
    "trainerroad": "TrainerRoad",
    "garmin": "Garmin Express",
    "antagent": "Garmin ANT Agent",
    "goldencheetah": "GoldenCheetah",
    "perfpro": "PerfPRO Studio",
    "rouvy": "ROUVY",
    "fulgaz": "FulGaz",
    "mywhoosh": "MyWhoosh",
    "indievelo": "indieVelo / TrainingPeaks Virtual",
    "trainingpeaks": "TrainingPeaks Virtual",
    "wahoo": "Wahoo SYSTM",
    "systm": "Wahoo SYSTM",
    "kinomap": "Kinomap",
    "bkool": "BKOOL",
    "tacx": "Tacx",
    "antware": "ANTware",
    "simulant": "SimulANT+",
    "xert": "Xert",
    "biketerra": "Biketerra",
}

# přesné názvy procesů, které nemají v názvu nic rozpoznatelného
KNOWN_ANT_EXES = {
    "express.exe": "Garmin Express",
    "expresstray.exe": "Garmin Express",
}

_CREATE_NO_WINDOW = 0x08000000
_prepared = False


class DongleBusy(Exception):
    """Dongle je fyzicky připojený, ale nejde otevřít (drží ho jiný proces)."""


class DongleMissing(Exception):
    """Dongle není vidět na USB."""


# ---------------------------------------------------------------- příprava
def prepare() -> None:
    """Nastaví libusb backend (Windows) a opraví úniky v openant. Volat jednou."""
    global _prepared
    if _prepared:
        return
    _prepared = True
    _prepare_libusb()
    _patch_openant()


def _prepare_libusb() -> None:
    try:
        import libusb_package  # type: ignore
        import usb.core

        backend = libusb_package.get_libusb1_backend()
        if backend is not None:
            orig_find = usb.core.find

            def find(*args, **kwargs):
                kwargs.setdefault("backend", backend)
                return orig_find(*args, **kwargs)

            usb.core.find = find
        path = libusb_package.get_library_path()
        if path:
            d = os.path.dirname(str(path))
            os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")
            if hasattr(os, "add_dll_directory"):
                os.add_dll_directory(d)
    except Exception as e:  # noqa: BLE001
        log.info("libusb-package není k dispozici: %s", e)


def _patch_openant() -> None:
    """openant při chybě během otevírání nechá USB otevřené a vlákno běžet.

    Pak každý další pokus hlásí „Access denied / busy“, dokud se program
    neukončí – přesně symptom „dongle je připojen k jiné aplikaci“.
    """
    try:
        from openant.base import ant as ant_mod
    except Exception:  # noqa: BLE001
        return
    Ant = ant_mod.Ant
    if getattr(Ant, "_antfan_patched", False):
        return
    orig_init = Ant.__init__

    def safe_init(self, *a, **kw):
        try:
            orig_init(self, *a, **kw)
        except Exception:
            log.warning("Otevření donglu selhalo, uvolňuji USB")
            self._running = False
            t = getattr(self, "_worker_thread", None)
            if isinstance(t, threading.Thread) and t.is_alive():
                t.join(timeout=3)
            drv = getattr(self, "_driver", None)
            if drv is not None and getattr(drv, "dev", None) is not None:
                try:
                    drv.close()
                except Exception:  # noqa: BLE001
                    pass
            raise

    Ant.__init__ = safe_init
    # openant zahazuje zprávu, která je stejná jako ta předchozí („jen nový
    # časový slot“). Pro měření kvality příjmu i pro výkon při rovnoměrném
    # šlapání chceme dostat každou zprávu – porovnání vyřadíme.
    Ant._last_data = property(lambda self: None, lambda self, value: None)
    Ant._antfan_patched = True
    _patch_usb_driver()
    _patch_channel_type()


def _patch_channel_type() -> None:
    """HLAVNÍ PŘÍČINA VÝPADKŮ: openant otevírá kanály jako „background scanning“.

    AntPlusDevice.open_channel má výchozí ext_assign=0x01 = Background
    Scanning Enable. Takový kanál se na senzor nikdy nezasynchronizuje,
    jen pořád hledá a zprávu chytí náhodou – v praxi ~10 % zpráv, výpadky
    po 2–7 s u všech senzorů. (V praxi: při skenu ~90 % zpráv,
    při měření 7–11 %.) Normální sledovací kanál = bez rozšířeného přiřazení.
    """
    try:
        from openant.devices.common import AntPlusDevice
    except Exception:  # noqa: BLE001
        return
    if getattr(AntPlusDevice, "_antfan_channel_patched", False):
        return
    orig = AntPlusDevice.open_channel

    def open_channel(self, extended=True, channel_type=None, ext_assign=None):
        return orig(self, extended=extended, channel_type=channel_type, ext_assign=ext_assign)

    AntPlusDevice.open_channel = open_channel
    AntPlusDevice._antfan_channel_patched = True


_tls = threading.local()


def _boost_current_thread() -> None:
    """Vlákno, které čte z donglu, dostane vysokou prioritu.

    Skoro pořád jen čeká na USB, procesor nebere – ale když je PC vytížené
    (Rouvy), nesmí se k donglu dostat pozdě, jinak se v něm přeplní buffer
    a zprávy od všech senzorů zároveň se ztratí.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes

        k32 = ctypes.windll.kernel32
        THREAD_PRIORITY_HIGHEST = 2
        k32.SetThreadPriority(k32.GetCurrentThread(), THREAD_PRIORITY_HIGHEST)
    except Exception as e:  # noqa: BLE001
        log.info("Nelze zvýšit prioritu vlákna: %s", e)


DEAD_AFTER_ERRORS = 5  # tolik chyb čtení po sobě => spojení s donglem je ztracené


def _patch_usb_driver() -> None:
    """Ohleduplné otevírání donglu a klidné chování při jeho ztrátě.

    Původní openant:
      * při otevření udělá USB reset donglu – a to i když ho právě používá
        jiný program (Rouvy, Zwift), kterému tím shodí spojení,
      * vezme vždy první nalezený dongle, i když je obsazený (se dvěma
        donglemi tak může sahat na ten Rouvy),
      * po vytažení / převzetí donglu čte v nekonečné smyčce bez pauzy:
        jedno jádro CPU na 100 % a log plný varování => sekání her.
    """
    try:
        import usb.core
        import usb.util
        from openant.base import driver as drv_mod
    except Exception:  # noqa: BLE001
        return
    USBDriver = getattr(drv_mod, "USBDriver", None)
    if USBDriver is None or getattr(USBDriver, "_antfan_patched", False):
        return

    def gentle_open(self):
        ids = [(self.ID_VENDOR, self.ID_PRODUCT)] + [i for i in ANT_USB_IDS
                                                      if i != (self.ID_VENDOR, self.ID_PRODUCT)]
        last: Exception | None = None
        for vid, pid in ids:
            for dev in list(usb.core.find(find_all=True, idVendor=vid, idProduct=pid) or []):
                try:
                    try:
                        if dev.is_kernel_driver_active(0):
                            dev.detach_kernel_driver(0)
                    except (NotImplementedError, usb.core.USBError):
                        pass
                    try:
                        cfg = dev.get_active_configuration()
                    except usb.core.USBError as e:
                        if is_busy_error(e):
                            raise
                        cfg = None
                    if cfg is None:
                        dev.set_configuration()
                        cfg = dev.get_active_configuration()
                    # výhradní přivlastnění – obsazený dongle tu skončí chybou
                    # a my na něj dál nesaháme (žádný reset)
                    usb.util.claim_interface(dev, 0)
                except (usb.core.USBError, NotImplementedError) as e:
                    log.info("Dongle %04x:%04x (bus %s, adr. %s) je obsazený/nedostupný: %r",
                             vid, pid, getattr(dev, "bus", "?"), getattr(dev, "address", "?"), e)
                    last = e
                    usb.util.dispose_resources(dev)
                    continue
                intf = cfg[(0, 0)]
                self.dev = dev
                self._out = usb.util.find_descriptor(
                    intf, custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress)
                    == usb.util.ENDPOINT_OUT)
                self._in = usb.util.find_descriptor(
                    intf, custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress)
                    == usb.util.ENDPOINT_IN)
                assert self._out is not None and self._in is not None
                self._antfan_errors = 0
                self._antfan_dead = False
                log.info("Používám dongle %04x:%04x (bus %s, adr. %s)", vid, pid,
                         getattr(dev, "bus", "?"), getattr(dev, "address", "?"))
                return
        if last is not None:
            raise last
        raise ValueError("Device not found")

    def calm_read(self):
        if not getattr(_tls, "boosted", False):
            _tls.boosted = True
            _boost_current_thread()
        if getattr(self, "_antfan_dead", False):
            time.sleep(0.5)  # nečinně čekáme, než nás AntFan zavře
            raise usb.core.USBTimeoutError("dongle ztracen")
        try:
            data = self._in.read(4096)
        except usb.core.USBTimeoutError:
            self._antfan_errors = 0
            raise
        except usb.core.USBError as e:
            n = self._antfan_errors = getattr(self, "_antfan_errors", 0) + 1
            if n >= DEAD_AFTER_ERRORS:
                log.warning("Spojení s donglem ztraceno (%r) – přestávám číst", e)
                self._antfan_dead = True
                raise usb.core.USBTimeoutError("dongle ztracen") from e
            time.sleep(0.2 * n)
            raise
        self._antfan_errors = 0
        return data

    def quiet_close(self):
        try:
            usb.util.dispose_resources(self.dev)
        except Exception:  # noqa: BLE001
            pass

    USBDriver.open = gentle_open
    USBDriver.read = calm_read
    USBDriver.close = quiet_close
    USBDriver._antfan_patched = True


def node_lost(node) -> bool:
    """True, když openant přestal s donglem komunikovat (vytažen / převzat)."""
    drv = getattr(getattr(node, "ant", None), "_driver", None)
    return bool(getattr(drv, "_antfan_dead", False))


# -------------------------------------------------------------- USB stav
def find_dongles() -> list:
    prepare()
    import usb.core

    found = []
    for vid, pid in ANT_USB_IDS:
        try:
            dev = usb.core.find(idVendor=vid, idProduct=pid)
        except Exception as e:  # noqa: BLE001
            log.warning("usb.core.find selhalo: %s", e)
            dev = None
        if dev is not None:
            found.append(dev)
    return found


def dongle_present() -> bool:
    devs = find_dongles()
    _dispose(devs)
    return bool(devs)


def _dispose(devs) -> None:
    try:
        import usb.util

        for d in devs:
            usb.util.dispose_resources(d)
    except Exception:  # noqa: BLE001
        pass


def is_busy_error(e: BaseException) -> bool:
    """LIBUSB_ERROR_ACCESS (-3 / errno 13) nebo LIBUSB_ERROR_BUSY (-6 / errno 16)."""
    seen = set()
    while e is not None and id(e) not in seen:
        seen.add(id(e))
        if getattr(e, "errno", None) in (13, 16):
            return True
        if getattr(e, "backend_error_code", None) in (-3, -6):
            return True
        text = str(e).lower()
        if any(s in text for s in ("access denied", "resource busy", "insufficient permissions",
                                    "busy", "in use")):
            return True
        e = e.__cause__ or e.__context__
    return False


def usb_reset() -> str:
    """Pokusí se o USB reset donglu (port reset, jako vytažení a zapojení).

    Vrací text pro uživatele. Vyhodí DongleBusy, když dongle drží jiný proces,
    a DongleMissing, když dongle není připojen.
    """
    prepare()
    devs = find_dongles()
    if not devs:
        raise DongleMissing()
    try:
        for d in devs:
            try:
                d.reset()
            except NotImplementedError:
                return ("Tento ovladač USB reset nepodporuje (WinUSB). "
                        "Vytáhněte dongle a zapojte ho znovu.")
            except Exception as e:  # noqa: BLE001
                if is_busy_error(e):
                    raise DongleBusy(str(e)) from e
                raise
        return "Dongle byl resetován."
    finally:
        _dispose(devs)
        gc.collect()


# ----------------------------------------------------------- procesy
def list_processes() -> list[tuple[int, str, str]]:
    """[(pid, název, příkazová řádka)] – jen Windows, jinde prázdné."""
    if sys.platform != "win32":
        return []
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command",
             "Get-CimInstance Win32_Process | Select-Object ProcessId,Name,CommandLine "
             "| ConvertTo-Json -Compress"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=20, creationflags=_CREATE_NO_WINDOW,
        ).stdout
        data = json.loads(out)
        if isinstance(data, dict):
            data = [data]
        return [(int(d.get("ProcessId") or 0), d.get("Name") or "", d.get("CommandLine") or "")
                for d in data]
    except Exception as e:  # noqa: BLE001
        log.info("PowerShell výpis procesů selhal (%s), zkouším tasklist", e)
    try:
        import csv
        import io

        out = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True,
                             errors="replace", timeout=20, creationflags=_CREATE_NO_WINDOW).stdout
        return [(int(r[1]), r[0], "") for r in csv.reader(io.StringIO(out)) if len(r) > 1 and r[1].isdigit()]
    except Exception as e:  # noqa: BLE001
        log.warning("Nelze vypsat procesy: %s", e)
        return []


def is_antfan_process(name: str, cmdline: str) -> bool:
    n, c = name.lower(), cmdline.lower()
    if n == "antfan.exe":
        return True
    return n.startswith("python") and ("antfan.pyw" in c or "-m antfan" in c)


def find_blocking_processes(procs=None) -> tuple[list[str], list[int]]:
    """Vrací (názvy známých ANT aplikací, PID jiných instancí AntFan)."""
    procs = list_processes() if procs is None else procs
    me = os.getpid()
    apps, antfans = [], []
    for pid, name, cmd in procs:
        if pid == me:
            continue
        if is_antfan_process(name, cmd):
            antfans.append(pid)
            continue
        low = name.lower()
        if low in KNOWN_ANT_EXES:
            entry = f"{KNOWN_ANT_EXES[low]} ({name})"
            if entry not in apps:
                apps.append(entry)
            continue
        for key, label in KNOWN_ANT_APPS.items():
            if key in low:
                entry = f"{label} ({name})"
                if entry not in apps:
                    apps.append(entry)
                break
    return apps, antfans


def busy_message(apps: list[str], antfans: list[int]) -> str:
    lines = ["ANT+ dongle je zapojený, ale nejde otevřít – drží ho jiný proces "
             "nebo je v zaseknutém stavu."]
    if apps:
        lines += ["", "Běží programy, které dongle používají:"]
        lines += [f"  • {a}" for a in apps]
        lines += ["", "Jeden dongle může mít v jednu chvíli jen jeden program. AntFan ho "
                  "druhému programu nebere, aby mu nerozbil spojení. Možnosti:",
                  "  1. Druhý ANT+ dongle – AntFan si sám vezme ten volný (nejspolehlivější).",
                  "  2. Spustit nejdřív AntFan a „Spustit měření“, až potom Rouvy/Zwift "
                  "a v něm párovat senzory jen přes Bluetooth.",
                  "  3. Ukončit ten program – zkontrolujte i ikonky u hodin (Zwift Launcher a "
                  "Garmin Express běží na pozadí i po zavření okna)."]
    if antfans:
        lines += ["", f"Běží i jiná instance AntFan (PID {', '.join(map(str, antfans))})."]
    if not apps and not antfans:
        lines += ["", "Žádný známý program, který by dongle držel, neběží. Zkuste:",
                  "  1. tlačítko „Reset donglu“,",
                  "  2. vytáhnout dongle a zapojit ho do jiného USB portu (ne do hubu),",
                  "  3. ve Správci zařízení ověřit, že dongle má ovladač libusbK."]
    return "\n".join(lines)


def kill_process(pid: int) -> bool:
    try:
        if sys.platform == "win32":
            r = subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True,
                               timeout=10, creationflags=_CREATE_NO_WINDOW)
            return r.returncode == 0
        os.kill(pid, 15)
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("Nelze ukončit PID %s: %s", pid, e)
        return False
