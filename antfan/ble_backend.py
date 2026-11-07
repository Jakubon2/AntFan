"""Bluetooth (BLE) senzory: tepový pás, powermetr, trenažér s FTMS.

Knihovna bleak běží ve vlastní asyncio smyčce ve vlastním vlákně. Do GUI
jdou stejné události a ve stejném formátu jako z AntBackend
(found / value / ant_status / ant_error / scan_done), takže _poll_events
a Controller nemusí nic rozlišovat.

Klíče zařízení jsou (číslo, typ) jako u ANT+, jen typ je posunutý
o BLE_OFFSET (1120 = tepový pás přes BT). Číslo je krátké odvozené ID,
skutečná adresa (MAC na Windows, UUID na macOS) se pamatuje
v ble_devices.json vedle config.json.

CombinedBackend spojuje ANT+ a BLE: hledání hledá obojí, měření spustí
ANT pro ANT+ senzory a BLE pro BT senzory. Chybějící dongle BLE neblokuje.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import statistics
import struct
import subprocess
import sys
import threading
import time
import zlib
from collections import deque

from .ant_backend import (BLE_OFFSET, FE_TYPE, HR_TYPE, PM_TYPE, AntBackend, FoundDevice,
                          SimulatedBackend, is_ble)

log = logging.getLogger("antfan.ble")

try:  # bez bleak program funguje dál jen s ANT+
    import bleak  # noqa: F401
    HAVE_BLEAK = True
except Exception:  # noqa: BLE001
    HAVE_BLEAK = False

BLE_HR_TYPE = BLE_OFFSET + HR_TYPE    # Heart Rate 0x180D
BLE_PM_TYPE = BLE_OFFSET + PM_TYPE    # Cycling Power 0x1818
BLE_FE_TYPE = BLE_OFFSET + FE_TYPE    # Fitness Machine (FTMS) 0x1826


def _uuid16(x: int) -> str:
    return f"0000{x:04x}-0000-1000-8000-00805f9b34fb"


SERVICES = {  # typ -> (služba, charakteristika s notifikacemi)
    BLE_HR_TYPE: (_uuid16(0x180D), _uuid16(0x2A37)),
    BLE_PM_TYPE: (_uuid16(0x1818), _uuid16(0x2A63)),
    BLE_FE_TYPE: (_uuid16(0x1826), _uuid16(0x2AD2)),
}

CRANK_STALE_S = 3.0    # kadence bez nové otáčky klik => 0 rpm
CADENCE_KEEP_S = 3.0   # FTMS: kadence z dřívější notifikace, když chybí v aktuální


# ============================================================ dekódování
def parse_hr(data: bytes) -> int | None:
    """Heart Rate Measurement 0x2A37 → tep (bpm)."""
    if len(data) < 2:
        return None
    flags = data[0]
    if flags & 0x01:
        if len(data) < 3:
            return None
        return data[1] | (data[2] << 8)
    return data[1]


def parse_cp(data: bytes) -> dict | None:
    """Cycling Power Measurement 0x2A63 → {"power", "crank": (otáčky, čas 1/1024 s) | None}."""
    if len(data) < 4:
        return None
    flags, power = struct.unpack_from("<Hh", data, 0)
    off = 4
    if flags & 0x0001:   # pedal power balance
        off += 1
    if flags & 0x0004:   # accumulated torque
        off += 2
    if flags & 0x0010:   # wheel revolution data
        off += 6
    crank = None
    if flags & 0x0020 and len(data) >= off + 4:
        crank = struct.unpack_from("<HH", data, off)
    return {"power": power, "crank": crank}


# (bit, velikost pole) v pořadí podle specifikace FTMS Indoor Bike Data
_FTMS_FIELDS = [
    (1, 2),   # average speed
    (2, 2),   # instantaneous cadence (0.5 rpm)
    (3, 2),   # average cadence
    (4, 3),   # total distance
    (5, 2),   # resistance level
    (6, 2),   # instantaneous power (sint16)
]


def parse_ftms_bike(data: bytes) -> dict | None:
    """Indoor Bike Data 0x2AD2 → {"power": W | None, "cadence": rpm | None}.

    Trenažér může data rozdělit do více notifikací, proto obě hodnoty
    mohou chybět.
    """
    if len(data) < 2:
        return None
    flags = data[0] | (data[1] << 8)
    off = 2
    if not flags & 0x0001:  # bit 0 = More Data; 0 znamená, že je tu okamžitá rychlost
        off += 2
    out: dict = {"power": None, "cadence": None}
    for bit, size in _FTMS_FIELDS:
        if not flags & (1 << bit):
            continue
        if len(data) < off + size:
            return out
        if bit == 2:
            out["cadence"] = struct.unpack_from("<H", data, off)[0] // 2
        elif bit == 6:
            out["power"] = struct.unpack_from("<h", data, off)[0]
        off += size
    return out


class CrankCadence:
    """Kadence z kumulativních otáček klik (CP crank revolution data)."""

    def __init__(self):
        self._last: tuple[int, int] | None = None
        self._last_change = 0.0
        self.cadence: int | None = None

    def update(self, crank: tuple[int, int] | None, now: float) -> int | None:
        if crank is None:
            return None
        if self._last is None:
            self._last = crank
            self._last_change = now
            return self.cadence
        revs = (crank[0] - self._last[0]) & 0xFFFF
        dt = ((crank[1] - self._last[1]) & 0xFFFF) / 1024.0
        if revs and dt > 0:
            rpm = revs * 60.0 / dt
            if rpm <= 250:
                self.cadence = int(round(rpm))
            self._last = crank
            self._last_change = now
        elif now - self._last_change > CRANK_STALE_S:
            self.cadence = 0
            self._last = crank
        return self.cadence


# ============================================================ kvalita příjmu
class BleRx:
    """% očekávaných notifikací za posledních 5 s.

    Senzory posílají různě často (tep ~1 Hz, výkon 1–4 Hz), proto se
    očekávaný interval odhaduje z mediánu skutečných intervalů a omezuje
    na 0,2–1,1 s. Je to orientační údaj.
    """

    WINDOW_S = 5.0

    def __init__(self, label: str, now: float):
        self.label = label
        self._lock = threading.Lock()
        self._times: deque[float] = deque()
        self._intervals: deque[float] = deque(maxlen=30)
        self._started = now

    def restart(self, now: float) -> None:
        with self._lock:
            self._started = now

    def on_notify(self, now: float) -> None:
        with self._lock:
            if self._times:
                gap = now - self._times[-1]
                if gap < 5:
                    self._intervals.append(gap)
            self._times.append(now)
            while self._times and now - self._times[0] > 2 * self.WINDOW_S:
                self._times.popleft()

    def expected_interval(self) -> float:
        with self._lock:
            iv = list(self._intervals)
        if len(iv) < 5:
            return 1.0
        return min(1.1, max(0.2, statistics.median(iv)))

    def quality(self, now: float) -> int | None:
        interval = self.expected_interval()
        with self._lock:
            window = min(self.WINDOW_S, now - self._started)
            if window < 2.0:
                return None
            n = sum(1 for t in self._times if now - t <= window)
        return int(min(100, round(100.0 * n * interval / window)))


# ============================================================ paměť adres
class BleRegistry:
    """Adresa BT zařízení <-> krátké číslo pro klíč a seznam senzorů."""

    def __init__(self, path=None):
        self._lock = threading.Lock()
        self._path = path
        self._by_addr: dict[str, dict] = {}
        if path is not None:
            try:
                self._by_addr = json.loads(path.read_text(encoding="utf-8"))
            except FileNotFoundError:
                pass
            except Exception:  # noqa: BLE001
                log.exception("Nelze načíst %s", path)

    @classmethod
    def default(cls) -> "BleRegistry":
        from . import config

        return cls(config.app_dir() / "ble_devices.json")

    def id_for(self, address: str, name: str = "") -> int:
        addr = address.upper()
        with self._lock:
            rec = self._by_addr.get(addr)
            if rec is not None:
                if name and rec.get("name") != name:
                    rec["name"] = name
                    self._save()
                return rec["id"]
            used = {r["id"] for r in self._by_addr.values()}
            n = zlib.crc32(addr.encode()) % 90000 + 10000  # pětimístné jako ANT+ ID
            while n in used:
                n = n + 1 if n < 99999 else 10000
            self._by_addr[addr] = {"id": n, "name": name}
            self._save()
            return n

    def lookup(self, dev_id: int) -> tuple[str, str] | None:
        with self._lock:
            for addr, rec in self._by_addr.items():
                if rec["id"] == dev_id:
                    return addr, rec.get("name", "")
        return None

    def _save(self):
        if self._path is None:
            return
        try:
            tmp = self._path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._by_addr, indent=2, ensure_ascii=False), encoding="utf-8")
            tmp.replace(self._path)
        except Exception:  # noqa: BLE001
            log.exception("Nelze uložit %s", self._path)


# ============================================================ macOS: oprávnění
_mac_check: list = []  # [výsledek] po první kontrole


def probe_main() -> int:
    """Podproces `AntFan --ble-probe`: zkusí otevřít CoreBluetooth.

    Když aplikace nemá v Info.plist NSBluetoothAlwaysUsageDescription, macOS
    proces rovnou zabije (SIGABRT). Proto se to zkouší v podprocesu, ne v GUI.
    """
    async def scan():
        from bleak import BleakScanner

        async with BleakScanner():
            await asyncio.sleep(2.0)

    try:
        asyncio.run(scan())
        print("ok")
    except Exception as e:  # noqa: BLE001
        # vypnutý Bluetooth apod. – to ohlásí až skutečný sken, tady jde jen o pád
        print(f"{type(e).__name__}: {e}")
    return 0


def macos_ble_check() -> str | None:
    """None = Bluetooth jde použít; jinak česky, proč ne. Na jiných systémech vždy None."""
    if sys.platform != "darwin":
        return None
    if _mac_check:
        return _mac_check[0]
    err = None
    try:
        import CoreBluetooth as CB  # noqa: N813

        auth = int(CB.CBManager.authorization())  # jen čte, o nic nežádá
        if auth == 3:  # allowedAlways
            _mac_check.append(None)
            return None
        if auth in (1, 2):
            err = ("Bluetooth: macOS AntFanu nepovolil přístup. Povolte ho v Nastavení systému → "
                   "Soukromí a zabezpečení → Bluetooth.")
        else:
            if getattr(sys, "frozen", False):
                cmd = [sys.executable, "--ble-probe"]
                env = None
            else:
                cmd = [sys.executable, "-c",
                       "import sys; from antfan.ble_backend import probe_main; sys.exit(probe_main())"]
                root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                env = dict(os.environ, PYTHONPATH=root + os.pathsep + os.environ.get("PYTHONPATH", ""))
            r = subprocess.run(cmd, env=env, capture_output=True, timeout=30)
            if r.returncode < 0 or r.returncode == 134:  # SIGABRT od TCC
                log.warning("BT zkouška skončila kódem %s: %s", r.returncode, r.stderr[-500:])
                err = ("Bluetooth: macOS program nepustil k Bluetooth (chybí oprávnění). Spusťte "
                       "AntFan jako aplikaci AntFan.app a povolte Bluetooth v Nastavení systému → "
                       "Soukromí a zabezpečení → Bluetooth.")
    except Exception as e:  # noqa: BLE001
        log.exception("Kontrola Bluetooth na macOS")
        err = f"Bluetooth: kontrola oprávnění selhala ({type(e).__name__})."
    _mac_check.append(err)
    return err


def _friendly_ble_error(e: BaseException) -> str:
    text = str(e) or type(e).__name__
    low = text.lower()
    if "not authorized" in low or "unauthorized" in low:
        return "Bluetooth: program nemá oprávnění (macOS: Nastavení → Soukromí → Bluetooth)."
    if "turned off" in low or "powered off" in low or "radio" in low and "off" in low:
        return "Bluetooth je vypnutý."
    if "no bluetooth adapter" in low or "adapter" in low and "not" in low or "not available" in low:
        return "Bluetooth adaptér nenalezen."
    return f"Bluetooth: {type(e).__name__}: {text}"


class _Unavailable(Exception):
    pass


# ============================================================ backend
class BleBackend:
    """Skutečné BLE senzory přes bleak."""

    def __init__(self, events, registry: BleRegistry | None = None):
        self.events = events
        self.registry = registry or BleRegistry.default()
        self.state = "idle"
        self._gen = 0
        self._rx: dict[tuple[int, int], BleRx] = {}
        self._conn_state: dict[str, str] = {}
        self._tasks: list = []
        self._scan_lock: asyncio.Lock | None = None
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, name="ble", daemon=True)
        self._thread.start()

    def _run_loop(self):
        asyncio.set_event_loop(self._loop)
        self._scan_lock = asyncio.Lock()
        self._loop.run_forever()

    def _submit(self, coro):
        return asyncio.run_coroutine_threadsafe(coro, self._loop)

    def _status(self, text: str):
        self.events.put(("ant_status", text))

    # --- veřejné API (neblokuje) ------------------------------------------
    def start_scan(self, duration: float) -> None:
        self._gen += 1
        self.state = "scanning"
        self._submit(self._restart(self._scan(duration, self._gen)))

    def start_monitor(self, devices: list[FoundDevice]) -> None:
        self._gen += 1
        devices = [d for d in devices if d.device_type in SERVICES]
        self.state = "monitoring" if devices else "idle"
        now = time.monotonic()
        self._rx = {d.key: BleRx(f"{d.type_name} #{d.device_id}", now) for d in devices}
        self._submit(self._restart(self._monitor(devices, self._gen)))

    def stop(self) -> None:
        self._gen += 1
        self.state = "idle"
        self._rx = {}
        self._submit(self._restart(None))
        self._status("Bluetooth zastaven")

    def reset(self) -> None:
        pass

    def rx_quality(self) -> dict[tuple[int, int], int | None]:
        now = time.monotonic()
        return {k: m.quality(now) for k, m in list(self._rx.items())}

    def rx_diagnosis(self) -> tuple[int, dict[str, int]]:
        return 0, {}

    def shutdown(self) -> None:
        self._gen += 1
        try:
            self._submit(self._restart(None)).result(timeout=5)
        except Exception:  # noqa: BLE001
            pass
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=3)

    # --- interní (vše níže běží ve smyčce asyncio) -------------------------
    async def _restart(self, coro):
        tasks, self._tasks = self._tasks, []
        for t in tasks:
            t.cancel()
        for t in tasks:
            try:
                await t
            except BaseException:  # noqa: BLE001
                pass
        if coro is not None:
            self._tasks.append(asyncio.ensure_future(coro))

    async def _scan(self, duration: float, gen: int):
        from bleak import BleakScanner

        seen: dict[tuple[int, int], FoundDevice] = {}
        wanted = {svc: t for t, (svc, _) in SERVICES.items()}

        def on_adv(device, adv):
            try:
                uuids = {str(u).lower() for u in (adv.service_uuids or [])}
                types = [t for svc, t in wanted.items() if svc in uuids]
                if not types:
                    return
                name = adv.local_name or device.name or ""
                dev_id = self.registry.id_for(device.address, name)
                now = time.monotonic()
                for t in types:
                    key = (dev_id, t)
                    d = seen.get(key)
                    if d is None:
                        d = seen[key] = FoundDevice(dev_id, t, 0)
                        log.info("Nalezen %s #%s (%s, %s, RSSI %s)", d.type_name, dev_id, name,
                                 device.address, adv.rssi)
                    if now - d.last_seen > 0.5:
                        d.last_seen = now
                        self.events.put(("found", FoundDevice(**d.__dict__)))
            except Exception:  # noqa: BLE001
                log.exception("Chyba při zpracování BT reklamy")

        error = await self._loop.run_in_executor(None, macos_ble_check)
        try:
            if error:
                raise _Unavailable(error)
            async with self._scan_lock:
                scanner = BleakScanner(detection_callback=on_adv)
                await scanner.start()
                try:
                    self._status(f"Bluetooth: hledám ({int(duration)} s)…")
                    end = time.monotonic() + duration
                    while time.monotonic() < end and self._gen == gen:
                        await asyncio.sleep(0.25)
                finally:
                    await scanner.stop()
        except asyncio.CancelledError:
            raise
        except _Unavailable:
            pass
        except Exception as e:  # noqa: BLE001
            log.exception("BT sken selhal")
            error = _friendly_ble_error(e)
        if self._gen != gen:
            return
        self.state = "idle"
        if error:
            self.events.put(("ant_error", error))
        else:
            self._status(f"Bluetooth: vyhledávání dokončeno – nalezeno {len(seen)} senzorů")
            self.events.put(("scan_done",))

    async def _monitor(self, devices: list[FoundDevice], gen: int):
        error = await self._loop.run_in_executor(None, macos_ble_check)
        if error:
            if self._gen == gen:
                self.state = "idle"
                self.events.put(("ant_error", error))
            return
        by_addr: dict[str, list[FoundDevice]] = {}
        for d in devices:
            rec = self.registry.lookup(d.device_id)
            if rec is None:
                self._status(f"Bluetooth: {d.type_name} #{d.device_id} neznám adresu – "
                             "vyhledejte senzory znovu")
                continue
            by_addr.setdefault(rec[0], []).append(d)
        self._conn_state = {}
        if not by_addr:
            return
        conns = [asyncio.ensure_future(self._connection(addr, devs, gen))
                 for addr, devs in by_addr.items()]
        try:
            await asyncio.gather(*conns)
        finally:
            for c in conns:
                c.cancel()
            await asyncio.gather(*conns, return_exceptions=True)

    def _report(self, address: str, text: str):
        self._conn_state[address] = text
        self._status("Bluetooth: " + "; ".join(self._conn_state.values()))

    async def _connection(self, address: str, devices: list[FoundDevice], gen: int):
        """Jedno BT zařízení: připojit, odebírat notifikace, po ztrátě znovu."""
        from bleak import BleakClient, BleakScanner

        label = ", ".join(f"{d.type_name} #{d.device_id}" for d in devices)
        delay = 2.0
        while self._gen == gen:
            client = None
            try:
                self._report(address, f"{label} hledám…")
                async with self._scan_lock:
                    dev = await BleakScanner.find_device_by_address(address, timeout=10.0)
                if dev is None:
                    raise LookupError("senzor nevysílá (vypnutý, mimo dosah, nebo už je "
                                      "připojený k jinému programu)")
                lost = asyncio.Event()
                client = BleakClient(
                    dev, disconnected_callback=lambda _c: self._loop.call_soon_threadsafe(lost.set))
                self._report(address, f"{label} připojuji…")
                await client.connect(timeout=20.0)
                now = time.monotonic()
                for d in devices:
                    _svc, char = SERVICES[d.device_type]
                    await client.start_notify(char, self._make_handler(d))
                    mon = self._rx.get(d.key)
                    if mon is not None:
                        mon.restart(now)
                log.info("BT připojeno: %s (%s)", label, address)
                self._report(address, f"{label} připojen")
                delay = 2.0
                while self._gen == gen and not lost.is_set():
                    try:
                        await asyncio.wait_for(lost.wait(), 1.0)
                    except asyncio.TimeoutError:
                        pass
                if lost.is_set():
                    log.warning("BT spojení ztraceno: %s", label)
                    self._report(address, f"{label} spojení ztraceno, připojuji znovu…")
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001
                log.warning("BT %s (%s): %r", label, address, e)
                msg = str(e) if isinstance(e, LookupError) else _friendly_ble_error(e)
                self._report(address, f"{label}: {msg}")
            finally:
                if client is not None:
                    try:
                        await asyncio.wait_for(asyncio.shield(client.disconnect()), 5.0)
                    except BaseException:  # noqa: BLE001
                        pass
            if self._gen == gen:
                await asyncio.sleep(delay)
                delay = min(delay * 1.5, 10.0)

    def _make_handler(self, d: FoundDevice):
        key = d.key
        t = d.device_type
        crank = CrankCadence()
        last_cad: list = [None, 0.0]  # FTMS: (kadence, čas)

        def on_notify(_char, data: bytearray):
            now = time.monotonic()
            mon = self._rx.get(key)
            if mon is not None:
                mon.on_notify(now)
            try:
                data = bytes(data)
                if t == BLE_HR_TYPE:
                    hr = parse_hr(data)
                    if hr is not None:
                        self.events.put(("value", key, "hr", hr, None))
                elif t == BLE_PM_TYPE:
                    cp = parse_cp(data)
                    if cp is not None and 0 <= cp["power"] <= 3000:
                        cad = crank.update(cp["crank"], now)
                        self.events.put(("value", key, "power", cp["power"], cad))
                elif t == BLE_FE_TYPE:
                    ib = parse_ftms_bike(data)
                    if ib is None:
                        return
                    if ib["cadence"] is not None:
                        last_cad[0], last_cad[1] = ib["cadence"], now
                    if ib["power"] is not None and 0 <= ib["power"] <= 3000:
                        cad = last_cad[0] if now - last_cad[1] <= CADENCE_KEEP_S else None
                        self.events.put(("value", key, "power", ib["power"], cad))
            except Exception:  # noqa: BLE001
                log.exception("Chyba při dekódování BT dat %s: %s", key, list(data))

        return on_notify


class SimulatedBleBackend:
    """Falešný BT tepový pás pro simulaci."""

    SIM_DEVICES = [FoundDevice(52011, BLE_HR_TYPE, 0)]

    def __init__(self, events):
        self.events = events
        self.state = "idle"
        self._gen = 0
        self._rx: dict = {}

    def _alive(self, gen):
        return self._gen == gen

    def start_scan(self, duration: float) -> None:
        self._gen += 1
        gen = self._gen
        self.state = "scanning"

        def run():
            t0 = time.monotonic()
            while self._alive(gen) and time.monotonic() - t0 < duration:
                if time.monotonic() - t0 > 1.5:
                    for d in self.SIM_DEVICES:
                        self.events.put(("found", FoundDevice(d.device_id, d.device_type, 0, None,
                                                              time.monotonic())))
                time.sleep(0.7)
            if self._alive(gen):
                self.state = "idle"
                self.events.put(("scan_done",))

        threading.Thread(target=run, daemon=True).start()

    def start_monitor(self, devices: list[FoundDevice]) -> None:
        self._gen += 1
        gen = self._gen
        devices = [d for d in devices if d.device_type in SERVICES]
        self.state = "monitoring"
        now = time.monotonic()
        self._rx = {d.key: BleRx(d.type_name, now) for d in devices}
        self.events.put(("ant_status", "Bluetooth: " + ", ".join(
            f"{d.type_name} #{d.device_id} připojen" for d in devices)))

        def run():
            hr = 100.0
            while self._alive(gen):
                hr += random.gauss(0, 0.8) + (130 - hr) * 0.02
                for d in devices:
                    if random.random() < 0.05:
                        continue
                    self._rx[d.key].on_notify(time.monotonic())
                    if d.device_type == BLE_HR_TYPE:
                        self.events.put(("value", d.key, "hr", int(hr), None))
                time.sleep(1.0)

        threading.Thread(target=run, daemon=True).start()

    def rx_quality(self):
        now = time.monotonic()
        return {k: m.quality(now) for k, m in list(self._rx.items())}

    def rx_diagnosis(self):
        return 0, {}

    def stop(self) -> None:
        self._gen += 1
        self.state = "idle"
        self._rx = {}

    def reset(self) -> None:
        pass

    def shutdown(self) -> None:
        self._gen += 1


# ============================================================ spojení ANT+ a BLE
class _Tap:
    """Fronta, přes kterou dílčí backend posílá události kombinovanému."""

    def __init__(self, owner: "CombinedBackend", src: str):
        self._owner, self._src = owner, src

    def put(self, ev):
        self._owner._on_child(self._src, ev)


class CombinedBackend:
    """Deleguje na ANT+ a BLE backend podle typu senzoru."""

    def __init__(self, events, ant=None, ble=None, simulation: bool = False,
                 dongle_present=None):
        self.events = events
        self.simulation = simulation
        self._lock = threading.RLock()
        self.ant = ant(_Tap(self, "ant"))
        self.ble = ble(_Tap(self, "ble")) if ble is not None else None
        self._dongle_present = dongle_present
        self._op: str | None = None
        self._active: set[str] = set()
        self._done: set[str] = set()
        self._errors: dict[str, str] = {}
        self._status_by: dict[str, str] = {}
        self._found: dict[str, set] = {}
        self._notes: list[str] = []

    @property
    def _pre(self) -> str:
        return "[SIMULACE] " if self.simulation else ""

    @property
    def state(self) -> str:
        if self._op == "scan":
            return "scanning"
        states = {getattr(self, src).state for src in self._active}
        for st in ("monitoring", "unplugged"):
            if st in states:
                return st
        return "idle"

    def _parts(self):
        return [p for p in (self.ant, self.ble) if p is not None]

    def _ant_available(self) -> bool:
        if self._dongle_present is None:
            return True
        try:
            return bool(self._dongle_present())
        except Exception:  # noqa: BLE001
            return False

    # --- veřejné API -----------------------------------------------------------
    def start_scan(self, duration: float) -> None:
        with self._lock:
            self._begin("scan")
            if self.ble is None or self._ant_available():
                self._active.add("ant")
            else:
                self._notes.append("ANT+ dongle nezapojen")
            if self.ble is not None:
                self._active.add("ble")
            self._found = {s: set() for s in self._active}
        what = " a ".join(x for x, s in (("ANT+", "ant"), ("Bluetooth", "ble")) if s in self._active)
        self.events.put(("ant_status", f"{self._pre}Vyhledávám senzory {what} ({int(duration)} s)…"))
        if "ant" in self._active:
            self.ant.start_scan(duration)
        else:
            self.ant.stop()
        if "ble" in self._active:
            self.ble.start_scan(duration)

    def start_monitor(self, devices: list[FoundDevice]) -> None:
        ant_devs = [d for d in devices if not is_ble(d.device_type)]
        ble_devs = [d for d in devices if is_ble(d.device_type)]
        if self.ble is None:
            ble_devs = []
        with self._lock:
            self._begin("monitor")
            if ant_devs or not ble_devs:
                self._active.add("ant")
            if ble_devs:
                self._active.add("ble")
        if "ant" in self._active:
            self.ant.start_monitor(ant_devs)
        else:
            self.ant.stop()
        if self.ble is not None:
            if ble_devs:
                self.ble.start_monitor(ble_devs)
            else:
                self.ble.stop()

    def stop(self) -> None:
        with self._lock:
            self._begin(None)
        for p in self._parts():
            p.stop()
        self.events.put(("ant_status", f"{self._pre}Zastaveno"))

    def reset(self) -> None:
        self.ant.reset()

    def rx_quality(self) -> dict:
        out = {}
        for p in self._parts():
            try:
                out.update(p.rx_quality())
            except Exception:  # noqa: BLE001
                log.exception("rx_quality")
        return out

    def rx_diagnosis(self) -> tuple[int, dict[str, int]]:
        all_n, single = self.ant.rx_diagnosis()
        if self.ble is not None:
            single = {**single, **self.ble.rx_diagnosis()[1]}
        return all_n, single

    def shutdown(self) -> None:
        for p in self._parts():
            try:
                p.shutdown()
            except Exception:  # noqa: BLE001
                log.exception("shutdown")

    # --- interní ---------------------------------------------------------------
    def _begin(self, op):
        self._op = op
        self._active = set()
        self._done = set()
        self._errors = {}
        self._status_by = {}
        self._notes = []

    def _on_child(self, src: str, ev):
        kind = ev[0]
        with self._lock:
            if src not in self._active:
                # zbytky z dílčího backendu, který teď nepoužíváme (stop, cizí sken)
                if kind in ("found", "value"):
                    return
                if kind == "ant_status":
                    log.debug("%s: %s", src, ev[1])
                    return
                if kind in ("ant_error", "scan_done"):
                    return
            if self._op == "scan":
                self._on_scan_event(src, ev)
                return
            if kind == "ant_status":
                self._status_by[src] = ev[1]
                parts = [self._status_by[s] for s in ("ant", "ble") if s in self._status_by]
                self.events.put(("ant_status", " · ".join(parts)))
                return
            if kind == "ant_error" and len(self._active) > 1:
                # druhá část běží dál – chybu ukázat, ale nic nezastavovat
                self._status_by[src] = ev[1].split("\n")[0]
            self.events.put(ev)

    def _on_scan_event(self, src: str, ev):
        kind = ev[0]
        if kind == "found":
            self._found[src].add(ev[1].key)
            self.events.put(ev)
        elif kind == "ant_status":
            log.info("%s: %s", src, ev[1])
        elif kind in ("scan_done", "ant_error"):
            if kind == "ant_error":
                self._errors[src] = ev[1]
            self._done.add(src)
            if self._done >= self._active:
                self._finish_scan()

    def _finish_scan(self):
        self._op = None
        if self._errors and len(self._errors) == len(self._active):
            self.events.put(("ant_error", "\n\n".join(self._notes + list(self._errors.values()))))
            return
        n = sum(len(v) for v in self._found.values())
        notes = list(self._notes)
        if "ant" in self._errors:
            notes.append("ANT+: " + self._errors["ant"].split("\n")[0])
        if "ble" in self._errors:
            notes.append(self._errors["ble"].split("\n")[0])
        text = f"{self._pre}Vyhledávání dokončeno – nalezeno {n} senzorů"
        if notes:
            text += " (" + "; ".join(notes) + ")"
        self.events.put(("ant_status", text))
        self.events.put(("scan_done",))


def make_backend(events, simulation: bool = False):
    """Backend pro App: ANT+ a k němu Bluetooth, pokud je k dispozici bleak."""
    if simulation:
        return CombinedBackend(events, SimulatedBackend, SimulatedBleBackend, simulation=True)
    if not HAVE_BLEAK:
        log.info("Knihovna bleak chybí, Bluetooth senzory nebudou")
        return AntBackend(events)
    from . import usb_diag

    def dongle_present():
        usb_diag.prepare()
        return usb_diag.dongle_present()

    return CombinedBackend(events, AntBackend, BleBackend, dongle_present=dongle_present)
