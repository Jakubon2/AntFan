"""Příjem z jednoho senzoru: kvalita signálu, dekódování výkonu, diagnostika.

Proč vlastní dekódování výkonu (a ne openant PowerMeter.on_device_data):
openant hlásí výkon jen tehdy, když se v datech změní čítač událostí.
Když pár zpráv vypadne (rádio, rušení USB 3.0), nebo trenažér čítač
neposune, program pak nedostane nic a po 3 s ukáže 0 W – i když jezdec
šlape. Tady se výkon bere z KAŽDÉ přijaté stránky a nulu hlásíme jen
tehdy, když zprávy chodí, ale čítač stojí (= opravdu se nešlape).
Když zprávy nechodí vůbec, je to výpadek příjmu a řeší ho Controller
(drží poslední hodnotu).
"""
from __future__ import annotations

import logging
import threading
from collections import Counter, deque
from .i18n import _, N_

log = logging.getLogger("antfan.rx")

HR_TYPE = 120
PM_TYPE = 11
FE_TYPE = 17

# kanálové periody (1/32768 s) dle profilů ANT+ → očekávaný počet zpráv za s
PERIODS = {HR_TYPE: 8070, PM_TYPE: 8182, FE_TYPE: 8192}
NAMES = {HR_TYPE: N_("Tep"), PM_TYPE: N_("Powermetr"), FE_TYPE: N_("Trenažér")}

COAST_S = 3.5        # čítač událostí stojí déle => nešlape se => 0 W
GAP_WARN_S = 1.5     # mezera mezi zprávami, která se zapíše do logu
SUMMARY_S = 5.0      # jak často psát souhrn příjmu do logu
RATE_WINDOW_S = 5.0  # okno pro výpočet % příjmu


def decode_power(device_type: int, data) -> tuple[int, int, int | None] | None:
    """Vrátí (čítač událostí, okamžitý výkon W, kadence) nebo None, když stránka není výkonová."""
    page = data[0]
    if device_type == PM_TYPE and page == 0x10:
        ev, inst, cad = data[1], data[6] | (data[7] << 8), data[3]
        if inst == 0xFFFF:
            return None
    elif device_type == FE_TYPE and page == 0x19:
        ev, inst, cad = data[1], data[5] | ((data[6] & 0x0F) << 8), data[2]
        if inst == 0xFFF:
            return None
    else:
        return None
    if inst > 3000:  # nesmysl / poškozená zpráva
        return None
    return ev, inst, (None if cad == 0xFF else cad)


def decode_speed(device_type: int, data) -> float | None:
    """Rychlost v km/h z FE-C stránky 0x10 (General FE Data, byty 4–5 = 0,001 m/s), jinak None.

    Rouvy a podobné aplikace sem promítají rychlost z virtuální trasy.
    Rychlost z BLE FTMS (Indoor Bike Data) se posílá stejně jako ("value", key, "speed", km/h).
    """
    if device_type != FE_TYPE or data[0] != 0x10:
        return None
    raw = data[4] | (data[5] << 8)
    if raw == 0xFFFF:
        return None
    kmh = raw * 0.0036
    return kmh if kmh <= 150 else None


class RxMonitor:
    """Sleduje jeden otevřený kanál. on_page() se volá z vlákna openant."""

    def __init__(self, device_id: int, device_type: int, now: float):
        self.device_id = device_id
        self.device_type = device_type
        self.label = f"{NAMES.get(device_type, device_type)} #{device_id}"
        self.rate_hz = 32768 / PERIODS.get(device_type, 8192)
        self._lock = threading.Lock()
        self._times: deque[float] = deque()
        self._started = now
        self._last_page: float | None = None
        # výkon
        self._last_ev: int | None = None
        self._last_ev_change = now
        self._last_power: tuple[int, int | None] | None = None
        # diagnostika za aktuální souhrnné okno
        self._win_start = now
        self._win_pages = 0
        self._win_kinds: Counter = Counter()
        self._win_ev_changes = 0
        self._win_coast = 0
        self._win_max_gap = 0.0
        self.total_pages = 0
        self.total_gaps = 0
        self.silence_logged = False
        self.key = (device_id, device_type)
        self._pending_gap: tuple[float, float] | None = None

    # --------------------------------------------------------------- příjem
    def on_page(self, data, now: float) -> tuple[int, int | None] | None:
        """Zpracuje stránku; u výkonových senzorů vrátí (W, kadence) nebo None."""
        with self._lock:
            gap = None if self._last_page is None else now - self._last_page
            self._last_page = now
            if self.silence_logged:
                self.silence_logged = False
                log.info("Kanál %s znovu přijímá", self.label)
            self._times.append(now)
            while self._times and now - self._times[0] > 2 * RATE_WINDOW_S:
                self._times.popleft()
            self.total_pages += 1
            self._win_pages += 1
            self._win_kinds[data[0]] += 1
            if gap is not None:
                self._win_max_gap = max(self._win_max_gap, gap)
                if gap >= GAP_WARN_S:
                    self.total_gaps += 1
                    self._pending_gap = (now - gap, now)
                    log.warning("Výpadek příjmu %s: %.1f s bez jediné zprávy", self.label, gap)

            result = None
            dec = decode_power(self.device_type, data)
            if dec is not None:
                ev, inst, cad = dec
                if ev != self._last_ev:
                    if self._last_ev is not None:
                        self._win_ev_changes += 1
                    self._last_ev = ev
                    self._last_ev_change = now
                if now - self._last_ev_change > COAST_S:
                    self._win_coast += 1
                    result = (0, 0)
                else:
                    result = (inst, cad)
                self._last_power = result

            if now - self._win_start >= SUMMARY_S:
                self._log_summary(now)
            return result

    def _log_summary(self, now: float) -> None:
        span = now - self._win_start
        pct = 100.0 * self._win_pages / max(1e-6, span * self.rate_hz)
        kinds = " ".join(f"{k:#04x}:{n}" for k, n in sorted(self._win_kinds.items()))
        extra = ""
        if self.device_type in (PM_TYPE, FE_TYPE):
            p = self._last_power
            extra = (f", změn čítače {self._win_ev_changes}, stání čítače {self._win_coast}×"
                     f", P={p[0] if p else '-'} W, kad={p[1] if p else '-'}")
        log.info("Příjem %s: %d zpráv/%.1f s (%.0f %%), max mezera %.2f s%s, stránky %s",
                 self.label, self._win_pages, span, min(pct, 999), self._win_max_gap, extra, kinds)
        self._win_start = now
        self._win_pages = 0
        self._win_kinds.clear()
        self._win_ev_changes = 0
        self._win_coast = 0
        self._win_max_gap = 0.0

    def take_gap(self) -> tuple[float, float] | None:
        """Výpadek, který právě skončil (začátek, konec), jednou."""
        with self._lock:
            g, self._pending_gap = self._pending_gap, None
            return g

    def received_between(self, a: float, b: float) -> bool:
        with self._lock:
            return any(a < t < b for t in self._times)

    def silent_for(self, now: float) -> float:
        with self._lock:
            return now - (self._last_page if self._last_page is not None else self._started)

    # --------------------------------------------------------------- pro GUI
    def quality(self, now: float) -> int | None:
        """Kolik % očekávaných zpráv přišlo za posledních 5 s (None = ještě nevíme)."""
        with self._lock:
            window = min(RATE_WINDOW_S, now - self._started)
            if window < 2.0:
                return None
            n = sum(1 for t in self._times if now - t <= window)
        return int(min(100, round(100.0 * n / (window * self.rate_hz))))


class GapClassifier:
    """Rozliší, jestli vypadávají všechny senzory zároveň, nebo jen jeden.

    * všechny zároveň  => problém je na straně PC: dongle, USB port, rušení
      u donglu, vytížený počítač,
    * jen jeden senzor => problém je u senzoru: jeho Bluetooth spojení
      s Rouvy (rádio se dělí mezi BT a ANT+), baterie, dosah.
    """

    WINDOW_S = 300.0

    def __init__(self):
        self._lock = threading.Lock()
        self._events: deque[tuple[float, str, str]] = deque()  # (čas, druh, senzor)
        self._last_all_end = 0.0

    def after_page(self, mon: RxMonitor, monitors) -> None:
        gap = mon.take_gap()
        if gap is None:
            return
        others = [m for m in monitors if m is not mon]
        if not others:
            return
        start, end = gap
        with self._lock:
            if any(m.received_between(start + 0.3, end - 0.3) for m in others):
                self._events.append((end, "single", mon.label))
                log.warning("Výpadek jen u %s (%.1f s), ostatní senzory přijímaly – "
                            "příčina je u senzoru (Bluetooth, baterie, dosah)", mon.label, end - start)
            elif start >= self._last_all_end:
                self._last_all_end = end
                self._events.append((end, "all", ""))
                log.warning("Výpadek VŠECH senzorů zároveň (%.1f s) – příčina je na straně PC: "
                            "dongle, USB port, rušení u donglu nebo vytížený počítač", end - start)

    def summary(self, now: float) -> tuple[int, dict[str, int]]:
        """(počet společných výpadků, {senzor: počet vlastních výpadků}) za 5 min."""
        with self._lock:
            while self._events and now - self._events[0][0] > self.WINDOW_S:
                self._events.popleft()
            all_n = sum(1 for _, k, _ in self._events if k == "all")
            single: dict[str, int] = {}
            for _u, k, lbl in self._events:
                if k == "single":
                    single[lbl] = single.get(lbl, 0) + 1
            return all_n, single
