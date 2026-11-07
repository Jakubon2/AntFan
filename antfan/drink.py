"""Připomínka pití během jízdy. Jen logika, bez UI.

Orientační pravidla (nejde o lékařské doporučení):
  * základ: připomínka každých 15 min, zhruba 500 ml za hodinu,
  * vyšší intenzita (kJ/h z výkonu) a teplota nad 22 °C: víc ml/h a kratší interval,
  * jízda delší než hodina: interval o 10 % kratší.

Čas se počítá jen během měření a když se šlape (výkon nebo kadence > 0).
Bez powermetru (jen tepový pás) se počítá čas s tepem.
"""
from __future__ import annotations

from dataclasses import dataclass

BASE_INTERVAL_MIN = 15.0
MIN_INTERVAL_MIN = 8.0
BASE_ML_H = 500.0
MAX_ML_H = 750.0         # bez horka
HEAT_FROM_C = 22.0
HEAT_ML_PER_C = 30.0     # ml/h navíc za každý °C nad 22
MAX_HEAT_ML_H = 300.0
SHOW_S = 60.0            # připomínka zmizí po 60 s
MAX_DT_S = 2.0           # delší mezera mezi ticky se nepočítá (uspání, zamrznutí)


def ml_per_hour(kj_per_h: float | None, temp_c: float | None) -> float:
    """Orientační příjem tekutin v ml/h."""
    ml = BASE_ML_H
    if kj_per_h:
        # 400 kJ/h (~110 W) a méně = základ, 900 kJ/h (~250 W) a víc = 750 ml/h
        ml += max(0.0, min(1.0, (kj_per_h - 400.0) / 500.0)) * (MAX_ML_H - BASE_ML_H)
    if temp_c is not None and temp_c > HEAT_FROM_C:
        ml += min(MAX_HEAT_ML_H, (temp_c - HEAT_FROM_C) * HEAT_ML_PER_C)
    return ml


def interval_min(kj_per_h: float | None, temp_c: float | None, ride_min: float = 0.0) -> float:
    """Interval mezi připomínkami v minutách."""
    m = BASE_INTERVAL_MIN
    if kj_per_h:
        if kj_per_h > 700:
            m -= 2.5
        if kj_per_h > 900:
            m -= 2.5
    if temp_c is not None and temp_c > HEAT_FROM_C:
        m -= min(4.0, (temp_c - HEAT_FROM_C) * 0.5)
    if ride_min > 60:
        m *= 0.9
    return max(MIN_INTERVAL_MIN, m)


def amount_ml(ml_h: float, interval_s: float) -> int:
    """Množství na jednu připomínku, zaokrouhlené na 25 ml (aspoň 50 ml)."""
    v = ml_h * interval_s / 3600.0
    return max(50, int(round(v / 25.0)) * 25)


def parse_temp(text: str) -> float | None:
    """'' = nepočítat; jinak °C v rozsahu 0–45. Vyhodí ValueError."""
    t = (text or "").strip().replace(",", ".")
    if not t:
        return None
    v = float(t)
    if not 0 <= v <= 45:
        raise ValueError("Teplota 0–45 °C.")
    return v


def parse_interval(text: str) -> float:
    """'' = automaticky (0); jinak minuty 1–120. Vyhodí ValueError."""
    t = (text or "").strip().replace(",", ".")
    if not t:
        return 0.0
    v = float(t)
    if not 1 <= v <= 120:
        raise ValueError("Interval 1–120 min.")
    return v


@dataclass
class Reminder:
    id: int
    ml: int
    shown_at: float

    @property
    def text(self) -> str:
        return f"Napijte se · zhruba {self.ml} ml"


class DrinkTracker:
    """Počítá čas jízdy a práci, hlídá, kdy připomenout.

    update() se volá z hlavní smyčky (klidně 4× za sekundu). interval_override_s
    slouží testům a ladění: pevný interval v sekundách.
    """

    def __init__(self, enabled: bool = False, temp_c: float | None = 20.0, manual_min: float = 0.0,
                 interval_override_s: float | None = None):
        self.enabled = enabled
        self.temp_c = temp_c
        self.manual_min = manual_min
        self.interval_override_s = interval_override_s
        self.reset()

    def reset(self) -> None:
        self.active_s = 0.0     # čas, kdy se šlapalo
        self.kj = 0.0
        self._last_t: float | None = None
        self._due_at = None     # active_s, kdy připomenout
        self.current: Reminder | None = None
        self._next_id = 1

    # --- výpočty
    @property
    def kj_per_h(self) -> float | None:
        if self.active_s < 120 or self.kj <= 0:
            return None  # první dvě minuty ještě nevíme
        return self.kj / (self.active_s / 3600.0)

    def interval_s(self) -> float:
        if self.interval_override_s:
            return float(self.interval_override_s)
        if self.manual_min:
            return self.manual_min * 60.0
        return interval_min(self.kj_per_h, self.temp_c, self.active_s / 60.0) * 60.0

    def ml_h(self) -> float:
        return ml_per_hour(self.kj_per_h, self.temp_c)

    def next_amount(self) -> int:
        return amount_ml(self.ml_h(), self.interval_s())

    def summary(self) -> str:
        """Krátký popis pro Nastavení."""
        return f"Každých {self.interval_s() / 60:.0f} min, zhruba {self.next_amount()} ml " \
               f"({self.ml_h():.0f} ml/h)"

    # --- běh
    def update(self, now: float, monitoring: bool, power: float | None = None,
               cadence: float | None = None, hr: float | None = None) -> Reminder | None:
        """Vrátí aktuálně zobrazenou připomínku (nebo None)."""
        last, self._last_t = self._last_t, now
        if self.current is not None and now - self.current.shown_at >= SHOW_S:
            self.current = None
        if not self.enabled:
            self.current = None
            return None
        if power is not None or cadence is not None:
            riding = bool(power and power > 0) or bool(cadence and cadence > 0)
        else:
            riding = hr is not None  # bez powermetru aspoň podle tepu
        if not monitoring or not riding or last is None:
            return self.current
        dt = now - last
        if dt <= 0 or dt > MAX_DT_S:
            return self.current
        self.active_s += dt
        if power:
            self.kj += power * dt / 1000.0
        if self._due_at is None:
            self._due_at = self.active_s + self.interval_s()
        if self.active_s >= self._due_at:
            self.current = Reminder(self._next_id, self.next_amount(), now)
            self._next_id += 1
            self._due_at = self.active_s + self.interval_s()
        return self.current

    def dismiss(self) -> None:
        self.current = None

    def reschedule(self) -> None:
        """Po změně nastavení: další připomínka za celý nový interval."""
        self._due_at = None
