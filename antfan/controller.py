"""Logika: z výkonu / tepu spočítá stupeň ventilátoru.

- Výkon i tep se vzorkují v pravidelném kroku a průměrují přes okno
  (vyhlazení) – výkon na kole hodně kolísá.
- Zvýšení stupně je okamžité, jakmile průměr překročí práh.
- Snížení až když je průměr pod (prahem − hystereze) nepřetržitě
  po dobu "prodleva snížení" – ventilátor tak necvaká sem a tam.
- Prahy jdou zadat absolutně (W, bpm) nebo v % FTP a % max. tepu.
- Režim "chytrý": výkon rozhoduje o zvýšení (reaguje hned), tep jen drží
  dosažený stupeň, dokud neklesne (tep reaguje se zpožděním 30–60 s, takže
  přes krátký odpočinek mezi intervaly ventilátor nezpomalí).
- Plynulá rychlost a vítr podle rychlosti jízdy (výstup v %) jsou
  v _tick_pct a ve vitr.py; klasické stupně se tím nemění.
- Dofukování: po skončení šlapání ventilátor ještě chvíli běží na zvoleném
  stupni a teprve pak se vypne.
- Výkon chodí z ANT+ s každou zprávou (~4× za s); konec šlapání pozná
  backend a pošle 0 W. Když zprávy na chvíli nechodí vůbec (výpadek
  příjmu), drží se poslední hodnota – nespadne to na 0 W.
"""
from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field

from .vitr import (SPEED_SMOOTHING_S, SPEED_STALE_S, WIND_DOWN_DELAY_S, WIND_HYST_KMH, PctLimiter,
                   level_to_pct, pct_to_level, smooth_pct, wind_pct)

SOURCE_MODES = {
    "smart": "Chytře: výkon zvyšuje, tep drží",
    "max": "Vyšší stupeň z výkonu a tepu",
    "wind": "Vítr podle rychlosti jízdy",
    "power": "Jen výkon",
    "hr": "Jen tep",
}


@dataclass
class ControlConfig:
    source_mode: str = "smart"
    threshold_mode: str = "relative"   # "relative" = % FTP / % max. tepu, "absolute" = W / bpm
    ftp: int = 210              # výchozí FTP, v aplikaci se přepíše vlastní hodnotou
    hr_max: int = 185
    power_thresholds: list[int] = field(default_factory=lambda: [60, 160, 240])
    hr_thresholds: list[int] = field(default_factory=lambda: [105, 135, 155])
    power_pct: list[int] = field(default_factory=lambda: [30, 60, 85])
    hr_pct: list[int] = field(default_factory=lambda: [55, 70, 82])
    power_hysteresis: int = 20
    hr_hysteresis: int = 5
    power_smoothing_s: float = 10.0
    hr_smoothing_s: float = 5.0
    down_delay_s: float = 20.0
    power_stale_s: float = 3.0      # do této doby je hodnota čerstvá
    power_hold_s: float = 12.0      # výpadek příjmu: držet poslední výkon, pak "–"
    hr_stale_s: float = 5.0         # bez dat => tep neznámý
    no_data_s: float = 60.0         # žádná data => no_data_level
    no_data_level: int = 0
    cooldown_s: float = 180.0       # dofukování po skončení (0 = vypnuto)
    cooldown_level: int = 1
    # výstup v % (vitr.py)
    output_mode: str = "steps"      # "steps" = stupně, "smooth" = plynulá rychlost mezi prahy
    smooth_min_pct: int = 20        # rychlost na 1. prahu
    smooth_down_pct_s: float = 2.0  # pokles nejvýš o tolik %/s (po prodlevě)
    wind_full_kmh: float = 45.0     # vítr: 100 % při této rychlosti
    wind_floor: bool = True         # vítr: minimum podle výkonu a tepu

    def power_levels(self) -> list[int]:
        if self.threshold_mode == "relative":
            return [round(self.ftp * p / 100) for p in self.power_pct]
        return list(self.power_thresholds)

    def hr_levels(self) -> list[int]:
        if self.threshold_mode == "relative":
            return [round(self.hr_max * p / 100) for p in self.hr_pct]
        return list(self.hr_thresholds)


class SourceLevel:
    """Stupeň pro jeden zdroj (výkon nebo tep) s hysterezí a prodlevou."""

    def __init__(self):
        self.level = 0
        self._below_since: float | None = None

    def update(self, value: float | None, thresholds: list[int], hyst: float,
               down_delay: float, now: float) -> int:
        if value is None:
            self._below_since = None
            self.level = 0
            return 0
        up = sum(1 for t in thresholds if value >= t)
        if up > self.level:
            self.level = up
            self._below_since = None
            return self.level
        keep = sum(1 for t in thresholds if value >= t - hyst)
        if keep < self.level:
            if self._below_since is None:
                self._below_since = now
            elif now - self._below_since >= down_delay:
                self.level = keep
                self._below_since = None
        else:
            self._below_since = None
        return self.level


class Smoother:
    def __init__(self):
        self.samples: deque[tuple[float, float | None]] = deque()

    def add(self, t: float, v: float | None, window: float) -> float | None:
        self.samples.append((t, v))
        while self.samples and t - self.samples[0][0] > window:
            self.samples.popleft()
        vals = [x for _, x in self.samples if x is not None]
        if not vals:
            return None
        return sum(vals) / len(vals)


class Controller:
    def __init__(self, cfg: ControlConfig, max_level: int = 3):
        self.cfg = cfg
        self.max_level = max_level
        self.power_src = SourceLevel()
        self.hr_src = SourceLevel()
        self.power_avg = Smoother()
        self.hr_avg = Smoother()
        self._last_power: tuple[float, int, int | None] | None = None  # (t, W, kadence)
        self._last_hr: tuple[float, int] | None = None
        self._last_any = 0.0
        self._raw_level = 0           # stupeň bez dofukování
        self._last_on: float | None = None  # kdy byl naposledy "skutečný" stupeň > 0
        # výstupy pro GUI
        self.power_now: int | None = None
        self.power_gap_s: float = 0.0   # >0 = právě výpadek příjmu výkonu (s)
        self.cadence_now: int | None = None
        self.hr_now: int | None = None
        self.power_smoothed: float | None = None
        self.hr_smoothed: float | None = None
        self.power_level = 0
        self.hr_level = 0
        self.level = 0
        self.reason = "čekám na data"
        # výstup v % (plynulá rychlost / vítr); None = klasické stupně
        self.pct: float | None = None
        self._last_speed: tuple[float, float] | None = None
        self.speed_avg = Smoother()
        self.speed_now: float | None = None
        self.speed_smoothed: float | None = None
        self.wind_pct_now: float | None = None
        self._out = PctLimiter()
        self._wind_out = PctLimiter()
        self._raw_pct = 0.0
        self._lead_win: deque[tuple[float, int | None]] = deque()

    def feed(self, kind: str, value: int, cadence: int | None = None, now: float | None = None):
        now = time.monotonic() if now is None else now
        if kind == "power":
            self._last_power = (now, value, cadence)
        elif kind == "speed":
            self._last_speed = (now, float(value))
        elif kind == "hr":
            if 25 <= value <= 240:  # 0 = pás nemá kontakt
                self._last_hr = (now, value)
            else:
                return
        self._last_any = now

    def reset(self):
        self.__init__(self.cfg, self.max_level)

    def _combine(self, have_p: bool, have_h: bool) -> tuple[int, str]:
        mode = self.cfg.source_mode
        pl, hl = self.power_level, self.hr_level
        if mode == "power" or (mode in ("smart", "max") and not have_h):
            return (pl, "výkon") if have_p else (0, "chybí výkon")
        if mode == "hr" or (mode in ("smart", "max") and not have_p):
            return (hl, "tep") if have_h else (0, "chybí tep")
        if mode == "max":
            return (pl, "výkon") if pl >= hl else (hl, "tep")
        # smart: výkon zvyšuje, tep může jen podržet dosažený stupeň
        hold = min(self._raw_level, hl)
        if pl >= hold:
            return pl, "výkon"
        return hold, "tep drží stupeň"

    def tick(self, now: float | None = None) -> int:
        now = time.monotonic() if now is None else now
        c = self.cfg
        n = self.max_level

        self.power_gap_s = 0.0
        if self._last_power:
            age = now - self._last_power[0]
            if age <= max(c.power_stale_s, c.power_hold_s):
                # čerstvá hodnota, nebo krátký výpadek příjmu => poslední hodnota
                self.power_now, self.cadence_now = self._last_power[1], self._last_power[2]
                if age > c.power_stale_s:
                    self.power_gap_s = age
            else:
                self.power_now = self.cadence_now = None  # senzor zmizel
        else:
            self.power_now = self.cadence_now = None

        if self._last_hr and now - self._last_hr[0] <= c.hr_stale_s:
            self.hr_now = self._last_hr[1]
        else:
            self.hr_now = None

        self.power_smoothed = self.power_avg.add(now, self.power_now, c.power_smoothing_s)
        self.hr_smoothed = self.hr_avg.add(now, self.hr_now, c.hr_smoothing_s)

        self.power_level = self.power_src.update(self.power_smoothed, c.power_levels()[:n],
                                                 c.power_hysteresis, c.down_delay_s, now)
        self.hr_level = self.hr_src.update(self.hr_smoothed, c.hr_levels()[:n],
                                           c.hr_hysteresis, c.down_delay_s, now)
        if self.pct_mode():
            return self._tick_pct(now)
        self.pct = None

        if self._last_any == 0.0 or now - self._last_any > c.no_data_s:
            raw, reason = min(c.no_data_level, n), "žádná data ze senzorů"
        else:
            raw, reason = self._combine(self.power_smoothed is not None,
                                        self.hr_smoothed is not None)
        raw = min(raw, n)
        self._raw_level = raw
        if raw > 0:
            self._last_on = now

        level = raw
        cool_lvl = min(c.cooldown_level, n)
        if (c.cooldown_s > 0 and raw < cool_lvl and self._last_on is not None
                and now - self._last_on < c.cooldown_s):
            level = cool_lvl
            left = int(c.cooldown_s - (now - self._last_on))
            reason = f"dofukování ještě {left // 60}:{left % 60:02d}"
        self.level = level
        self.reason = reason
        return level

    # ================================================================ výstup v %
    def pct_mode(self) -> bool:
        return self.cfg.source_mode == "wind" or self.cfg.output_mode == "smooth"

    def _lead_power(self, now: float) -> float | None:
        """Předstih (lead_enabled z feature/predstih) i pro plynulou rychlost:
        nejnižší okamžitý výkon za posledních lead_s s, když je okno celé."""
        c = self.cfg
        if not getattr(c, "lead_enabled", False):
            self._lead_win.clear()
            return None
        win = max(1.0, float(getattr(c, "lead_s", 3.0)))
        self._lead_win.append((now, self.power_now))
        while self._lead_win and now - self._lead_win[0][0] > win + 0.5:
            self._lead_win.popleft()
        vals = [v for t, v in self._lead_win if now - t <= win]
        if not vals or any(v is None for v in vals) or now - self._lead_win[0][0] < win:
            return None
        return float(min(vals))

    def _src_targets(self, now: float) -> tuple[float, float, float, float, str]:
        """(výkon %, výkon % s hysterezí, tep %, tep % s hysterezí, poznámka)."""
        c, n = self.cfg, self.max_level
        pth, hth = c.power_levels()[:n], c.hr_levels()[:n]
        p = self.power_smoothed
        note = ""
        lead = self._lead_power(now)
        if lead is not None and p is not None and lead > p and smooth_pct(lead, pth, c.smooth_min_pct) > \
                smooth_pct(p, pth, c.smooth_min_pct):
            p, note = lead, "předstih"
        p_up = smooth_pct(p, pth, c.smooth_min_pct)
        p_keep = smooth_pct(None if p is None else p + c.power_hysteresis, pth, c.smooth_min_pct)
        h = self.hr_smoothed
        h_up = smooth_pct(h, hth, c.smooth_min_pct)
        h_keep = smooth_pct(None if h is None else h + c.hr_hysteresis, hth, c.smooth_min_pct)
        return p_up, p_keep, h_up, h_keep, note

    def _combine_pct(self, mode: str, now: float) -> tuple[float, float, str]:
        """(cíl %, cíl s hysterezí, důvod) pro výkon/tep ve stejných režimech jako stupně."""
        p_up, p_keep, h_up, h_keep, note = self._src_targets(now)
        have_p, have_h = self.power_smoothed is not None, self.hr_smoothed is not None
        p_txt = note or (f"výkon {self.power_smoothed:.0f} W" if have_p else "")
        h_txt = f"tep {self.hr_smoothed:.0f} bpm" if have_h else ""
        if mode == "power" or (mode in ("smart", "max") and not have_h):
            return (p_up, p_keep, p_txt) if have_p else (0.0, 0.0, "chybí výkon")
        if mode == "hr" or (mode in ("smart", "max") and not have_p):
            return (h_up, h_keep, h_txt) if have_h else (0.0, 0.0, "chybí tep")
        if mode == "max":
            return (p_up, p_keep, p_txt) if p_up >= h_up else (h_up, h_keep, h_txt)
        # smart: výkon zvyšuje, tep jen drží dosaženou rychlost
        hold = min(self._out.out, h_keep)
        if p_keep >= hold:
            return p_up, p_keep, p_txt
        return p_up, hold, "tep drží rychlost"

    def _tick_pct(self, now: float) -> int:
        c, n = self.cfg, self.max_level
        rate = max(0.1, float(c.smooth_down_pct_s))

        # rychlost jízdy
        if self._last_speed and now - self._last_speed[0] <= SPEED_STALE_S:
            self.speed_now = self._last_speed[1]
        else:
            self.speed_now = None
        self.speed_smoothed = self.speed_avg.add(now, self.speed_now, SPEED_SMOOTHING_S)

        no_data = self._last_any == 0.0 or now - self._last_any > c.no_data_s
        if no_data:
            raw = level_to_pct(min(c.no_data_level, n), n)
            self._out.out = self._wind_out.out = raw
            reason = "žádná data ze senzorů"
            self.wind_pct_now = None
        elif c.source_mode == "wind":
            v = self.speed_smoothed
            w_up = wind_pct(v, c.wind_full_kmh)
            w_keep = wind_pct(None if v is None else v + WIND_HYST_KMH, c.wind_full_kmh)
            self.wind_pct_now = None if v is None else w_up
            wind = self._wind_out.update(w_up, w_keep, WIND_DOWN_DELAY_S, max(rate, 5.0), now)
            reason = "chybí rychlost" if v is None else f"vítr {v:.0f} km/h"
            raw = wind
            if c.wind_floor:
                up, keep, why = self._combine_pct("smart", now)
                floor = self._out.update(up, keep, c.down_delay_s, rate, now)
                if floor > wind + 0.5:
                    raw = floor
                    reason = f"minimum: {why}" if why and not why.startswith("chybí") else "minimum podle výkonu"
            else:
                self._out.update(0.0, 0.0, 0.0, 1000.0, now)
        else:
            self.wind_pct_now = None
            up, keep, reason = self._combine_pct(c.source_mode, now)
            raw = self._out.update(up, keep, c.down_delay_s, rate, now)
        self._raw_pct = raw
        if raw > 0:
            self._last_on = now

        pct = raw
        cool = level_to_pct(min(c.cooldown_level, n), n)
        if (c.cooldown_s > 0 and raw < cool and self._last_on is not None
                and now - self._last_on < c.cooldown_s):
            pct = cool
            left = int(c.cooldown_s - (now - self._last_on))
            reason = f"dofukování ještě {left // 60}:{left % 60:02d}"
        self._raw_level = pct_to_level(raw, n)
        self.pct = round(pct, 1)
        self.level = pct_to_level(pct, n)
        self.reason = reason
        return self.level
