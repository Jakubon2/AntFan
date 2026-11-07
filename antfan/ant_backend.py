"""ANT+ část: vyhledání senzorů a čtení tepu / výkonu.

Postup s jedním USB donglem:
  1. Vyhledávání – dongle se přepne do "continuous scan mode", kdy přijímá
     zprávy od všech vysílačů najednou. Tak najdeme všechny pásy a
     powermetry v okolí včetně jejich ID.
  2. Měření – dongle se resetuje a pro každý vybraný senzor se otevře
     vlastní kanál (max. 8 kanálů na dongle).

Do GUI posílá události přes queue.Queue:
  ("ant_status", text)
  ("ant_error", text)
  ("found", FoundDevice)           – při vyhledávání (i opakovaně s novou hodnotou)
  ("value", (id, typ), kind, value, cadence)   kind = "hr" | "power"
      – výkon chodí s každou přijatou zprávou (~4× za s), 0 W = nešlape se
  ("scan_done",)
"""
from __future__ import annotations

import gc
import logging
import math
import queue
import random
import sys
import threading
import time
from dataclasses import dataclass

from . import usb_diag
from .rx import GapClassifier, RxMonitor

log = logging.getLogger("antfan.ant")

HR_TYPE = 120
PM_TYPE = 11
FE_TYPE = 17  # chytrý trenažér (ANT+ FE-C) – AntFan ho jen poslouchá, neovládá
SUPPORTED_TYPES = {HR_TYPE: "Tepový pás", PM_TYPE: "Powermetr", FE_TYPE: "Trenažér"}
POWER_TYPES = (PM_TYPE, FE_TYPE)
MAX_CHANNELS = 8


@dataclass
class FoundDevice:
    device_id: int
    device_type: int
    trans_type: int = 0
    last_value: int | None = None
    last_seen: float = 0.0

    @property
    def key(self) -> tuple[int, int]:
        return (self.device_id, self.device_type)

    @property
    def type_name(self) -> str:
        return SUPPORTED_TYPES.get(self.device_type, f"typ {self.device_type}")


def _friendly_error(e: Exception) -> str:
    if isinstance(e, usb_diag.DongleMissing) or type(e).__name__ == "DriverNotFound":
        if sys.platform == "darwin":  # na Macu se ovladač neinstaluje
            return "ANT+ dongle nenalezen. Je zapojený? Zkuste jiný USB port nebo redukci."
        return (
            "ANT+ dongle nenalezen. Je zapojený? Má ovladač libusbK nebo WinUSB "
            "(viz README)?"
        )
    if isinstance(e, usb_diag.DongleBusy) or usb_diag.is_busy_error(e):
        apps, antfans = usb_diag.find_blocking_processes()
        return usb_diag.busy_message(apps, antfans)
    if type(e).__name__ == "NoBackendError":
        return "Chybí knihovna libusb (pip install libusb-package)."
    return f"{type(e).__name__}: {e}"


class AntBackend:
    """Skutečný ANT+ dongle přes knihovnu openant."""

    def __init__(self, events: "queue.Queue"):
        self.events = events
        self._cmds: "queue.Queue" = queue.Queue()
        self._node = None
        self._node_thread: threading.Thread | None = None
        self._devices: list = []
        self._last_monitor: list | None = None
        self._rx: dict[tuple[int, int], RxMonitor] = {}
        self._gaps = GapClassifier()
        self._unplug_check = 0.0
        self.state = "idle"
        self._thread = threading.Thread(target=self._worker, name="ant", daemon=True)
        self._thread.start()

    # --- veřejné API (neblokuje) ------------------------------------------
    def start_scan(self, duration: float) -> None:
        self._cmds.put(("scan", duration))

    def start_monitor(self, devices: list[FoundDevice]) -> None:
        self._cmds.put(("monitor", list(devices)))

    def stop(self) -> None:
        self._cmds.put(("stop",))

    def reset(self) -> None:
        self._cmds.put(("reset",))

    def rx_quality(self) -> dict[tuple[int, int], int | None]:
        """% přijatých zpráv za posledních 5 s pro každý měřený senzor."""
        now = time.monotonic()
        return {k: m.quality(now) for k, m in list(self._rx.items())}

    def rx_diagnosis(self) -> tuple[int, dict[str, int]]:
        return self._gaps.summary(time.monotonic())

    def shutdown(self) -> None:
        self._cmds.put(("quit",))
        self._thread.join(timeout=8)

    # --- interní -------------------------------------------------------------
    def _status(self, text: str):
        self.events.put(("ant_status", text))

    def _worker(self):
        pending = None
        while True:
            if pending is not None:
                cmd, pending = pending, None
            else:
                try:
                    cmd = self._cmds.get(timeout=2.0)
                except queue.Empty:
                    cmd = ("watchdog",)
            kind = cmd[0]
            try:
                if kind == "quit":
                    self._teardown()
                    return
                if kind == "stop":
                    self._teardown()
                    self._last_monitor = None
                    self.state = "idle"
                    self._status("Zastaveno")
                elif kind == "scan":
                    self._last_monitor = None
                    pending = self._do_scan(cmd[1])
                elif kind == "monitor":
                    self._do_monitor(cmd[1])
                elif kind == "reset":
                    self._do_reset()
                elif kind == "watchdog":
                    self._watchdog()
            except Exception as e:  # noqa: BLE001
                log.exception("ANT chyba")
                self._teardown()
                self.state = "idle"
                self.events.put(("ant_error", _friendly_error(e)))

    def _watchdog(self):
        """Hlídá ztrátu donglu během měření a po zapojení měření obnoví.

        Za běhu se USB neprochází (to zbytečně zatěžuje sběrnici i Bluetooth
        adaptér) – ztrátu pozná ovladač podle chyb čtení (usb_diag.node_lost).
        """
        if self.state == "monitoring":
            now = time.monotonic()
            for mon in list(self._rx.values()):
                age = mon.silent_for(now)
                if age >= 10 and not mon.silence_logged:
                    mon.silence_logged = True
                    log.warning("Kanál %s nepřijal %.0f s žádnou zprávu (senzor nevysílá ANT+ "
                                "nebo je mimo dosah)", mon.label, age)
        if self.state == "monitoring" and self._node is not None and usb_diag.node_lost(self._node):
            log.warning("Spojení s donglem ztraceno")
            self._teardown()
            if usb_diag.dongle_present():
                # dongle je zapojený => nejspíš ho převzal jiný program
                time.sleep(1.5)
                try:
                    self._do_monitor(self._last_monitor or [], attempts=1)
                    return
                except Exception as e:  # noqa: BLE001
                    log.warning("Obnovení měření selhalo: %r", e)
                    self._teardown()
                    self.state = "idle"
                    self._last_monitor = None
                    self.events.put(("ant_error", "Spojení s ANT+ donglem se přerušilo a dongle "
                                     "teď nejde otevřít.\n\n" + _friendly_error(e)))
                    return
            self.state = "unplugged"
            self._unplug_check = 0.0
            self._status("Dongle byl odpojen – zapojte ho znovu, měření se obnoví samo")
        elif self.state == "unplugged" and time.monotonic() - self._unplug_check >= 4.0:
            self._unplug_check = time.monotonic()
            if usb_diag.dongle_present():
                time.sleep(1.5)  # Windows potřebuje chvíli na načtení ovladače
                self._status("Dongle je znovu zapojený, obnovuji měření…")
                self._do_monitor(self._last_monitor or [])

    def _do_reset(self):
        resume = self._last_monitor if self.state in ("monitoring", "unplugged") else None
        self._teardown()
        self.state = "idle"
        self._status("Resetuji dongle…")
        msg = usb_diag.usb_reset()
        time.sleep(2.0)
        self._status(msg)
        if resume:
            self._do_monitor(resume)

    def _open_node(self, attempts: int = 4):
        self._teardown()
        usb_diag.prepare()
        from openant.devices import ANTPLUS_NETWORK_KEY
        from openant.easy.node import Node

        if not usb_diag.dongle_present():
            raise usb_diag.DongleMissing()
        last: Exception | None = None
        for attempt in range(1, attempts + 1):
            self._status("Připojuji ANT+ dongle…" if attempt == 1 else
                         f"Dongle nejde otevřít, zkouším znovu ({attempt}/{attempts})…")
            node = None
            try:
                node = Node()
                node.set_network_key(0x00, ANTPLUS_NETWORK_KEY)
            except Exception as e:  # noqa: BLE001
                last = e
                log.warning("Otevření donglu, pokus %s selhal: %r", attempt, e)
                if node is not None:
                    try:
                        node.stop()
                    except Exception:  # noqa: BLE001
                        pass
                gc.collect()
                if not usb_diag.dongle_present():
                    raise usb_diag.DongleMissing() from e
                if usb_diag.is_busy_error(e) and attempt == 1:
                    # drží ho jiný program? Pak ho nechat být – žádné další
                    # pokusy ani reset, ty by mu shodily spojení
                    apps, antfans = usb_diag.find_blocking_processes()
                    if apps or antfans:
                        raise usb_diag.DongleBusy(str(e)) from e
                if attempt == 2:  # zaseknutý dongle často spraví USB reset
                    try:
                        log.info("USB reset: %s", usb_diag.usb_reset())
                    except Exception as re_:  # noqa: BLE001
                        log.info("USB reset selhal: %r", re_)
                if attempt < attempts:
                    time.sleep(1.0 + attempt)
                continue

            self._node = node

            def loop(node=node):
                while node._running:  # noqa: SLF001
                    try:
                        node.start()
                    except Exception:  # noqa: BLE001
                        log.exception("Chyba ve smyčce ANT uzlu")
                        time.sleep(1.0)

            self._node_thread = threading.Thread(target=loop, name="ant-node", daemon=True)
            self._node_thread.start()
            return node

        assert last is not None
        if usb_diag.is_busy_error(last):
            raise usb_diag.DongleBusy(str(last)) from last
        raise last

    def _hook_channel(self, dev, handle, mon: RxMonitor):
        """Naše zpracování zprávy běží jako první, přímo z kanálu.

        Chyba při parsování v openant (neznámá stránka, nečekaná hodnota od
        trenažéru) tak nemůže zablokovat výkon ani měření příjmu.
        """
        ch = dev.channel
        warned = set()
        label = mon.label

        def wrap(orig):
            def hook(data):
                try:
                    handle(data)
                    self._gaps.after_page(mon, list(self._rx.values()))
                except Exception:  # noqa: BLE001
                    log.exception("Chyba při zpracování zprávy %s", label)
                try:
                    orig(data)
                except Exception as e:  # noqa: BLE001
                    page = data[0] if len(data) else -1
                    if page not in warned:
                        warned.add(page)
                        log.warning("openant nezvládl stránku %#04x od %s: %r (data %s)",
                                    page, label, e, list(data[:8]))
            return hook

        ch.on_broadcast_data = wrap(ch.on_broadcast_data)
        ch.on_acknowledge = wrap(ch.on_acknowledge)

    def _teardown(self):
        node, self._node = self._node, None
        self._devices = []
        self._rx = {}
        if node is not None:
            try:
                node.stop()
            except Exception:  # noqa: BLE001
                log.exception("Chyba při zavírání ANT uzlu")
        if self._node_thread is not None:
            self._node_thread.join(timeout=3)
            self._node_thread = None

    def _do_scan(self, duration: float):
        from openant.easy.channel import Channel

        node = self._open_node()
        seen: dict[tuple[int, int], FoundDevice] = {}
        counts: dict[tuple[int, int], int] = {}

        def on_data(data):
            try:
                if len(data) < 13:
                    return
                dev_id = data[9] | (data[10] << 8)
                dev_type = data[11] & 0x7F
                trans = data[12]
                counts[(dev_id, dev_type)] = counts.get((dev_id, dev_type), 0) + 1
                if dev_type not in SUPPORTED_TYPES:
                    return
                # horní nibble transmission type rozšiřuje číslo zařízení
                dev_id |= ((trans >> 4) & 0x0F) << 16
                key = (dev_id, dev_type)
                dev = seen.get(key)
                if dev is None:
                    dev = FoundDevice(dev_id, dev_type, trans)
                    seen[key] = dev
                    log.info("Nalezen %s #%s", dev.type_name, dev_id)
                value = None
                if dev_type == HR_TYPE:
                    value = data[7]
                elif dev_type == PM_TYPE and data[0] == 0x10:
                    value = data[6] | (data[7] << 8)
                elif dev_type == FE_TYPE and data[0] == 0x19:
                    value = data[5] | ((data[6] & 0x0F) << 8)
                now = time.monotonic()
                if value is not None:
                    dev.last_value = value
                if now - dev.last_seen > 0.5:
                    dev.last_seen = now
                    self.events.put(("found", FoundDevice(**dev.__dict__)))
            except Exception:  # noqa: BLE001
                log.exception("Chyba při dekódování skenu")

        ch = node.new_channel(Channel.Type.BIDIRECTIONAL_RECEIVE, 0x00, None)
        ch.on_broadcast_data = on_data
        ch.on_burst_data = on_data
        ch.on_acknowledge_data = on_data
        ch.set_id(0, 0, 0)
        ch.enable_extended_messages(1)
        ch.set_rf_freq(57)
        ch.open_rx_scan_mode()
        self.state = "scanning"
        self._status(f"Vyhledávám senzory ({int(duration)} s)…")

        end = time.monotonic() + duration
        next_cmd = None
        while True:
            remaining = end - time.monotonic()
            if remaining <= 0:
                break
            try:
                next_cmd = self._cmds.get(timeout=min(remaining, 0.5))
                break
            except queue.Empty:
                pass
        self._teardown()
        self.state = "idle"
        log.info("Sken %.0f s – zprávy podle zařízení (ID, typ): %s", duration,
                 ", ".join(f"#{i} typ {t}: {n}" for (i, t), n in sorted(counts.items())) or "žádné")
        self._status(f"Vyhledávání dokončeno – nalezeno {len(seen)} senzorů")
        self.events.put(("scan_done",))
        return next_cmd

    def _do_monitor(self, devices: list[FoundDevice], attempts: int = 4):
        from openant.devices.fitness_equipment import FitnessEquipment
        from openant.devices.heart_rate import HeartRate
        from openant.devices.power_meter import PowerMeter

        devices = [d for d in devices if d.device_type in SUPPORTED_TYPES][:MAX_CHANNELS]
        self._last_monitor = devices
        if not devices:
            self._status("Nevybrán žádný senzor")
            return
        node = self._open_node(attempts)

        rx: dict[tuple[int, int], RxMonitor] = {}
        for d in devices:
            key = d.key
            mon = RxMonitor(d.device_id, d.device_type, time.monotonic())
            rx[key] = mon
            # pro 20bitová ID se spodních 16 bitů posílá jako číslo zařízení
            dev_num = d.device_id & 0xFFFF
            if d.device_type == HR_TYPE:
                dev = HeartRate(node, device_id=dev_num)

                def on_hr(_page, _name, data, key=key):
                    self.events.put(("value", key, "hr", int(data.heart_rate), None))

                dev.on_device_data = on_hr

                def handle(data, mon=mon):
                    mon.on_page(data, time.monotonic())
            else:
                cls = FitnessEquipment if d.device_type == FE_TYPE else PowerMeter
                dev = cls(node, device_id=dev_num)

                # výkon dekódujeme sami z každé stránky (viz rx.py), ne přes
                # openant on_device_data, které chodí jen při změně čítače
                def handle(data, mon=mon, key=key):
                    res = mon.on_page(data, time.monotonic())
                    if res is not None:
                        self.events.put(("value", key, "power", res[0], res[1]))

            self._hook_channel(dev, handle, mon)
            self._devices.append(dev)

        self._rx = rx
        self.state = "monitoring"
        names = ", ".join(f"{d.type_name} #{d.device_id}" for d in devices)
        self._status(f"Měřím: {names}")


class SimulatedBackend:
    """Falešný dongle pro vyzkoušení programu bez hardwaru."""

    SIM_DEVICES = [
        FoundDevice(23456, HR_TYPE, 1),
        FoundDevice(41001, PM_TYPE, 5),
        FoundDevice(31337, HR_TYPE, 1),
        FoundDevice(61234, FE_TYPE, 5),
    ]

    def __init__(self, events: "queue.Queue"):
        self.events = events
        self.state = "idle"
        self._gen = 0
        self._lock = threading.Lock()

    def _status(self, text):
        self.events.put(("ant_status", text))

    def _new_gen(self) -> int:
        with self._lock:
            self._gen += 1
            return self._gen

    def _alive(self, gen) -> bool:
        return self._gen == gen

    def start_scan(self, duration: float) -> None:
        gen = self._new_gen()
        self.state = "scanning"
        self._status(f"[SIMULACE] Vyhledávám senzory ({int(duration)} s)…")

        def run():
            t0 = time.monotonic()
            while self._alive(gen) and time.monotonic() - t0 < duration:
                el = time.monotonic() - t0
                for i, d in enumerate(self.SIM_DEVICES):
                    if el > 0.8 + i * 1.2:
                        val = 130 + random.randint(-3, 3) if d.device_type == HR_TYPE else 180 + random.randint(-20, 20)
                        self.events.put(("found", FoundDevice(d.device_id, d.device_type, d.trans_type, val, time.monotonic())))
                time.sleep(0.7)
            if self._alive(gen):
                self.state = "idle"
                self._status(f"[SIMULACE] Vyhledávání dokončeno – nalezeno {len(self.SIM_DEVICES)} senzorů")
                self.events.put(("scan_done",))

        threading.Thread(target=run, daemon=True).start()

    def start_monitor(self, devices: list[FoundDevice]) -> None:
        gen = self._new_gen()
        devices = list(devices)[:MAX_CHANNELS]
        self.state = "monitoring"
        self._status("[SIMULACE] Měřím: " + ", ".join(f"{d.type_name} #{d.device_id}" for d in devices))
        t_start = time.monotonic()
        self._rx = {d.key: RxMonitor(d.device_id, d.device_type, t_start) for d in devices}
        self._gaps = GapClassifier()
        rx = self._rx

        def run():
            t0 = time.monotonic()
            hr = 95.0
            ev = 0
            while self._alive(gen):
                now = time.monotonic()
                t = now - t0
                # intervaly: vlny 100–320 W, každých 90 s pauza 8 s (0 W)
                cycle = t % 90
                if cycle < 8:
                    power, cad = 0, 0
                else:
                    power = int(max(0, 200 + 110 * math.sin(t / 14) + random.gauss(0, 15)))
                    cad = 85 + random.randint(-4, 4)
                    ev = (ev + 1) & 0xFF  # při šlapání se čítač událostí posouvá
                target_hr = 90 + power * 0.28
                hr += (target_hr - hr) * 0.03
                # simulace rádia: ~3 % ztracených zpráv a každých 75 s výpadek 4 s
                radio_gap = 40 <= t % 75 < 44
                for d in devices:
                    if random.random() < 0.03:
                        continue
                    mon = rx[d.key]
                    if d.device_type == HR_TYPE:
                        mon.on_page([0x04, 0, 0, 0, 0, 0, 0, int(hr)], now)
                        self.events.put(("value", d.key, "hr", int(hr + random.gauss(0, 1)), None))
                        continue
                    if radio_gap:
                        continue
                    if d.device_type == PM_TYPE:
                        page = [0x10, ev, 0xFF, cad, 0, 0, power & 0xFF, power >> 8]
                    else:
                        page = [0x19, ev, cad, 0, 0, power & 0xFF, (power >> 8) & 0x0F, 0]
                    res = mon.on_page(page, now)
                    self._gaps.after_page(mon, list(rx.values()))
                    if res is not None:
                        self.events.put(("value", d.key, "power", res[0], res[1]))
                time.sleep(0.25)

        threading.Thread(target=run, daemon=True).start()

    def rx_quality(self) -> dict[tuple[int, int], int | None]:
        now = time.monotonic()
        return {k: m.quality(now) for k, m in list(getattr(self, "_rx", {}).items())}

    def rx_diagnosis(self) -> tuple[int, dict[str, int]]:
        g = getattr(self, "_gaps", None)
        return g.summary(time.monotonic()) if g else (0, {})

    def stop(self) -> None:
        self._new_gen()
        self.state = "idle"
        self._rx = {}
        self._status("[SIMULACE] Zastaveno")

    def reset(self) -> None:
        self._status("[SIMULACE] Dongle resetován")

    def shutdown(self) -> None:
        self._new_gen()
