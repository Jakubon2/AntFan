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
- Předstih (volitelný): když okamžitý výkon drží nad prahem vyššího stupně
  celé "lead_s" sekundy, stupeň se zvýší hned, bez čekání na průměr.
  Snižování zůstává pomalé.
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

SOURCE_MODES = {
    "smart": "Chytře: výkon zvyšuje, tep drží",
    "max": "Vyšší stupeň z výkonu a tepu",
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
    lead_enabled: bool = False      # předstih při nástupu výkonu
    lead_s: float = 3.0

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
        self._raw_power: deque[tuple[float, int | None]] = deque()
        self.lead_active = False
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

    def feed(self, kind: str, value: int, cadence: int | None = None, now: float | None = None):
        now = time.monotonic() if now is None else now
        if kind == "power":
            self._last_power = (now, value, cadence)
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
            return (pl, "předstih" if self.lead_active else "výkon") if have_p else (0, "chybí výkon")
        if mode == "hr" or (mode in ("smart", "max") and not have_p):
            return (hl, "tep") if have_h else (0, "chybí tep")
        if mode == "max":
            return (pl, "výkon") if pl >= hl else (hl, "tep")
        # smart: výkon zvyšuje, tep může jen podržet dosažený stupeň
        hold = min(self._raw_level, hl)
        if pl >= hold:
            return pl, "výkon" if not self.lead_active else "předstih"
        return hold, "tep drží stupeň"

    def _lead(self, now: float, thresholds: list[int]) -> int:
        """Předstih: celé okno lead_s nad prahem vyššího stupně => zvýšit hned."""
        win = max(1.0, self.cfg.lead_s)
        self._raw_power.append((now, self.power_now))
        while self._raw_power and now - self._raw_power[0][0] > win + 0.5:
            self._raw_power.popleft()
        vals = [v for t, v in self._raw_power if now - t <= win]
        covered = self._raw_power and now - self._raw_power[0][0] >= win
        if not covered or not vals or any(v is None for v in vals):
            return self.power_src.level
        low = min(vals)
        lead = sum(1 for t in thresholds if low >= t)
        if lead > self.power_src.level:
            self.power_src.level = lead
            self.power_src._below_since = None
        return self.power_src.level

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
        self.lead_active = False
        if c.lead_enabled:
            self.power_level = self._lead(now, c.power_levels()[:n])
            sm = self.power_smoothed
            self.lead_active = sm is not None and self.power_level > sum(
                1 for t in c.power_levels()[:n] if sm >= t)
        self.hr_level = self.hr_src.update(self.hr_smoothed, c.hr_levels()[:n],
                                           c.hr_hysteresis, c.down_delay_s, now)

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
