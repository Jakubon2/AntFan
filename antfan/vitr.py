"""Plynulá rychlost a vítr podle rychlosti jízdy (výstup v % místo stupňů).

* Plynulá rychlost: mezi 1. a posledním prahem roste rychlost lineárně
  z "min. %" do 100 %. Pod 1. prahem je vypnuto.
* Vítr: rychlost ventilátoru odpovídá rychlosti jízdy (z trenažéru,
  Rouvy ji promítá z virtuální trasy). Pod WIND_OFF_KMH vypnuto, lineárně
  do 100 % při "plný vítr při" km/h. Volitelně minimum podle výkonu a tepu.
* Zvýšení je okamžité, snížení až po prodlevě a nejvýš o X %/s.

Pomůcky pro převod % <-> stupeň a pro ovladače ventilátorů jsou tu taky,
ať se nemusí sahat do miio_fan.py/fans.py víc, než je nutné.
"""
from __future__ import annotations

WIND_OFF_KMH = 5.0       # pod touto rychlostí vítr nefouká
WIND_HYST_KMH = 2.0      # hystereze větru
WIND_DOWN_DELAY_S = 3.0  # vítr sleduje rychlost, čeká jen krátce
SPEED_STALE_S = 5.0      # bez rychlosti déle => neznámá
SPEED_SMOOTHING_S = 3.0
PCT_STEP = 5.0           # menší změny se ventilátoru neposílají


# --------------------------------------------------------------- mapování
def smooth_pct(value: float | None, thresholds: list[int], min_pct: float) -> float:
    """Výkon/tep -> % lineárně mezi prahy (pod 1. prahem 0)."""
    if value is None or not thresholds:
        return 0.0
    lo, hi = thresholds[0], thresholds[-1]
    if value < lo:
        return 0.0
    if hi <= lo or value >= hi:
        return 100.0
    mn = max(0.0, min(100.0, float(min_pct)))
    return mn + (100.0 - mn) * (value - lo) / (hi - lo)


def wind_pct(kmh: float | None, full_kmh: float, off_kmh: float = WIND_OFF_KMH) -> float:
    """Rychlost jízdy -> % větru (0 pod off_kmh, 100 při full_kmh)."""
    if kmh is None or kmh < off_kmh:
        return 0.0
    return max(0.0, min(100.0, 100.0 * kmh / max(1.0, full_kmh)))


def pct_to_level(pct: float | None, n: int) -> int:
    """% -> nejbližší stupeň 1..n (cokoli nad 0 % je aspoň stupeň 1)."""
    if not pct or pct <= 0:
        return 0
    n = max(1, n)
    return max(1, min(n, round(pct / 100.0 * n)))


def level_to_pct(level: int, n: int) -> float:
    return 0.0 if level <= 0 else 100.0 * min(level, max(1, n)) / max(1, n)


def pct_to_range(pct: float, lo: int, hi: int) -> int:
    """% (0 < pct <= 100) -> hodnota rychlosti ventilátoru lo..hi."""
    return max(lo, min(hi, round(lo + (hi - lo) * pct / 100.0)))


def range_to_pct(value, lo: int, hi: int) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return 0.0
    if hi <= lo:
        return 100.0
    return max(0.0, min(100.0, 100.0 * (v - lo) / (hi - lo)))


# --------------------------------------------------------------- omezovač poklesu
class PctLimiter:
    """Zvýšení hned; snížení až po prodlevě a nejvýš o rate %/s.

    up = cíl z aktuální hodnoty, keep = cíl z hodnoty + hystereze
    (dokud keep >= výstup, výstup drží).
    """

    def __init__(self):
        self.out = 0.0
        self._below_since: float | None = None
        self._t: float | None = None

    def update(self, up: float, keep: float, delay: float, rate: float, now: float) -> float:
        dt = 0.0 if self._t is None else max(0.0, now - self._t)
        self._t = now
        if up >= self.out:
            self.out = up
            self._below_since = None
        elif keep < self.out:
            if self._below_since is None:
                self._below_since = now
            if now - self._below_since >= delay:
                step = rate * dt if rate > 0 else self.out
                self.out = max(keep, self.out - step)
                if keep <= 0 and self.out < 1.0:  # dojezd na nulu = vypnout
                    self.out = 0.0
        else:
            self._below_since = None
        return self.out

