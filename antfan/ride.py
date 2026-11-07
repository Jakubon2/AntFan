"""Záznam jízdy (1× za s), výpočty pro shrnutí a CSV soubory.

Bez GUI, aby šlo testovat samostatně. Okno shrnutí je v ride_ui.py.

Výpočty:
  * NP (normalizovaný výkon): 30s klouzavý průměr, 4. mocnina, průměr, 4. odmocnina.
  * IF = NP / FTP, TSS = délka[h] · IF² · 100.
  * Zóny výkonu: 7 zón Coggan podle % FTP. Zóny tepu: 5 zón podle % max. tepu.
  * Posun tepu (Pa:HR decoupling): poměr výkon/tep v 1. a 2. polovině jízdy,
    (EF1 − EF2) / EF1 · 100 %.
"""
from __future__ import annotations

import csv
import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path

from . import config as config_mod

MIN_RIDE_S = 300        # kratší jízdy se neukládají ani neshrnují
MAX_GAP_S = 5.0         # delší mezera mezi vzorky (odpojený dongle) se do času nepočítá
RIDES_DIR = "jizdy"

# horní hranice zón v % FTP (Coggan); poslední zóna je bez horní hranice
POWER_ZONES = [
    ("Z1", "Regenerace", 55),
    ("Z2", "Vytrvalost", 75),
    ("Z3", "Tempo", 90),
    ("Z4", "Práh", 105),
    ("Z5", "VO2max", 120),
    ("Z6", "Anaerobní", 150),
    ("Z7", "Sprint", None),
]
# horní hranice zón v % max. tepu
HR_ZONES = [
    ("Z1", "Regenerace", 60),
    ("Z2", "Vytrvalost", 70),
    ("Z3", "Tempo", 80),
    ("Z4", "Práh", 90),
    ("Z5", "Maximum", None),
]

CSV_COLUMNS = ["cas_s", "cas", "vykon_w", "vykon_prumer_w", "kadence_rpm", "tep_bpm",
               "ventilator", "ftp", "max_tep"]


@dataclass
class Sample:
    t: float                    # s od začátku jízdy
    power: int | None           # okamžitý výkon
    power_avg: int | None       # vyhlazený výkon (jako v okně jízdy)
    cadence: int | None
    hr: int | None
    fan: int
    ftp: int
    hr_max: int


class RideRecorder:
    """Sbírá vzorky během měření. `start` = čas spuštění (pro jméno souboru)."""

    def __init__(self, start: dt.datetime | None = None):
        self.start = start or dt.datetime.now()
        self.samples: list[Sample] = []
        self._t0: float | None = None

    def add(self, now: float, power, power_avg, cadence, hr, fan: int, ftp: int, hr_max: int):
        if self._t0 is None:
            self._t0 = now
        self.samples.append(Sample(
            round(now - self._t0, 2),
            None if power is None else int(round(power)),
            None if power_avg is None else int(round(power_avg)),
            None if cadence is None else int(cadence),
            None if hr is None else int(hr),
            int(fan or 0), int(ftp), int(hr_max)))

    def trimmed(self) -> list[Sample]:
        """Vzorky bez konce, kdy se už nešlapalo (dofukování); jen když byl powermetr."""
        s = self.samples
        if not any(x.power for x in s):
            return list(s)
        end = len(s)
        while end > 0 and not s[end - 1].power:
            end -= 1
        return s[:end]


# ====================================================================== výpočty
def _weights(samples: list[Sample]) -> list[float]:
    """Kolik sekund "patří" každému vzorku (do dalšího vzorku, nejvýš MAX_GAP_S)."""
    w = []
    for i, s in enumerate(samples):
        if i + 1 < len(samples):
            d = samples[i + 1].t - s.t
            w.append(d if 0 < d <= MAX_GAP_S else 1.0)
        else:
            w.append(1.0)
    return w


def normalized_power(powers: list[float], window: int = 30) -> float | None:
    """NP z výkonu po 1 s. Kratší řada než okno => obyčejný průměr."""
    vals = [p for p in powers if p is not None]
    if not vals:
        return None
    if len(vals) < window:
        return sum(vals) / len(vals)
    acc = sum(vals[:window])
    rolled = [acc / window]
    for i in range(window, len(vals)):
        acc += vals[i] - vals[i - window]
        rolled.append(acc / window)
    return (sum(r ** 4 for r in rolled) / len(rolled)) ** 0.25


def zone_index(pct: float, zones) -> int:
    for i, (_, _, hi) in enumerate(zones):
        if hi is None or pct <= hi:
            return i
    return len(zones) - 1


def power_zone(power: float, ftp: int) -> int:
    return zone_index(power / ftp * 100 if ftp else 0, POWER_ZONES)


def hr_zone(hr: float, hr_max: int) -> int:
    return zone_index(hr / hr_max * 100 if hr_max else 0, HR_ZONES)


def decoupling(pairs: list[tuple[float, float, float]]) -> float | None:
    """Posun tepu v % z (čas, výkon, tep). Kladné = tep v 2. polovině vůči výkonu stoupl."""
    pairs = [(t, p, h) for t, p, h in pairs if p is not None and h]
    if len(pairs) < 60:
        return None
    mid = (pairs[0][0] + pairs[-1][0]) / 2
    first = [(p, h) for t, p, h in pairs if t < mid]
    second = [(p, h) for t, p, h in pairs if t >= mid]
    if len(first) < 30 or len(second) < 30:
        return None

    def ef(rows):
        p = sum(r[0] for r in rows) / len(rows)
        h = sum(r[1] for r in rows) / len(rows)
        return p / h if h else 0.0

    ef1, ef2 = ef(first), ef(second)
    if ef1 <= 0:
        return None
    return (ef1 - ef2) / ef1 * 100


@dataclass
class RideStats:
    start: dt.datetime
    duration_s: float
    ftp: int
    hr_max: int
    has_power: bool = False
    has_hr: bool = False
    avg_power: float | None = None
    max_power: int | None = None
    np: float | None = None
    if_: float | None = None
    tss: float | None = None
    kj: float | None = None
    avg_hr: float | None = None
    max_hr: int | None = None
    avg_cadence: float | None = None
    power_zones: list[float] = field(default_factory=list)   # s v každé zóně
    hr_zones: list[float] = field(default_factory=list)
    fan_levels: list[float] = field(default_factory=list)    # s na stupni 0..max
    decoupling: float | None = None

    @property
    def worth_showing(self) -> bool:
        return self.duration_s >= MIN_RIDE_S and (self.has_power or self.has_hr)


def compute(samples: list[Sample], start: dt.datetime, max_level: int = 3) -> RideStats:
    if not samples:
        return RideStats(start, 0.0, 0, 0)
    w = _weights(samples)
    duration = sum(w)
    last = samples[-1]
    ftp, hr_max = last.ftp, last.hr_max
    st = RideStats(start, duration, ftp, hr_max)

    pw = [(s.power, wi) for s, wi in zip(samples, w) if s.power is not None]
    st.has_power = any(p > 0 for p, _ in pw)
    if st.has_power:
        tot = sum(wi for _, wi in pw)
        st.avg_power = sum(p * wi for p, wi in pw) / tot
        st.max_power = max(p for p, _ in pw)
        st.kj = sum(p * wi for p, wi in pw) / 1000
        st.np = normalized_power([p for p, _ in pw])
        if ftp and st.np is not None:
            st.if_ = st.np / ftp
            st.tss = duration * st.if_ ** 2 / 3600 * 100
        st.power_zones = [0.0] * len(POWER_ZONES)
        for p, wi in pw:
            st.power_zones[power_zone(p, ftp)] += wi

    hw = [(s.hr, wi) for s, wi in zip(samples, w) if s.hr]
    st.has_hr = bool(hw)
    if st.has_hr:
        st.avg_hr = sum(h * wi for h, wi in hw) / sum(wi for _, wi in hw)
        st.max_hr = max(h for h, _ in hw)
        st.hr_zones = [0.0] * len(HR_ZONES)
        for h, wi in hw:
            st.hr_zones[hr_zone(h, hr_max)] += wi

    cad = [(s.cadence, wi) for s, wi in zip(samples, w) if s.cadence]
    if cad:
        st.avg_cadence = sum(c * wi for c, wi in cad) / sum(wi for _, wi in cad)

    n = max([max_level] + [s.fan for s in samples])
    st.fan_levels = [0.0] * (n + 1)
    for s, wi in zip(samples, w):
        st.fan_levels[max(0, s.fan)] += wi

    if st.has_power and st.has_hr:
        st.decoupling = decoupling([(s.t, s.power, s.hr) for s in samples])
    return st


def fmt_duration(sec: float) -> str:
    sec = int(round(sec))
    h, rest = divmod(sec, 3600)
    m, s = divmod(rest, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def decoupling_text(value: float | None) -> str:
    if value is None:
        return "Nelze spočítat: chybí výkon nebo tep v obou polovinách jízdy."
    if value < 5:
        verdict = "Pod 5 % je dobré: tep držel krok s výkonem."
    elif value < 10:
        verdict = "5–10 %: tep ke konci stoupal, možná únava, teplo nebo málo pití."
    else:
        verdict = "Nad 10 %: tep v druhé polovině výrazně ujel, jízda byla nad aerobní kapacitou."
    return ("O kolik % se ve 2. polovině jízdy zhoršil poměr výkon/tep proti 1. polovině. "
            + verdict + " U intervalů má menší vypovídací hodnotu.")


# ====================================================================== CSV
def rides_dir() -> Path:
    d = config_mod.app_dir() / RIDES_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def _fmt(v) -> str:
    return "" if v is None else str(v)


def save_csv(samples: list[Sample], start: dt.datetime, folder: Path | None = None) -> Path:
    folder = folder or rides_dir()
    base = start.strftime("%Y-%m-%d_%H%M")
    path = folder / f"{base}.csv"
    k = 2
    while path.exists():
        path = folder / f"{base}_{k}.csv"
        k += 1
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", newline="", encoding="utf-8-sig") as f:  # BOM: Excel pozná UTF-8
        wr = csv.writer(f, delimiter=";")
        wr.writerow(CSV_COLUMNS)
        for s in samples:
            clock = (start + dt.timedelta(seconds=s.t)).strftime("%H:%M:%S")
            t = int(s.t) if float(s.t).is_integer() else s.t
            wr.writerow([t, clock, _fmt(s.power), _fmt(s.power_avg), _fmt(s.cadence), _fmt(s.hr),
                         s.fan, s.ftp, s.hr_max])
    tmp.replace(path)
    return path


def _int(v: str):
    v = (v or "").strip()
    if not v:
        return None
    try:
        return int(round(float(v.replace(",", "."))))
    except ValueError:
        return None


def start_from_name(path: Path) -> dt.datetime:
    stem = path.stem.split("_")
    try:
        return dt.datetime.strptime("_".join(stem[:2]), "%Y-%m-%d_%H%M")
    except ValueError:
        return dt.datetime.fromtimestamp(path.stat().st_mtime)


def load_csv(path: Path) -> tuple[list[Sample], dt.datetime]:
    samples: list[Sample] = []
    with Path(path).open(newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f, delimiter=";"):
            t = row.get("cas_s", "")
            try:
                t = float(t.replace(",", "."))
            except ValueError:
                continue
            samples.append(Sample(t, _int(row.get("vykon_w")), _int(row.get("vykon_prumer_w")),
                                  _int(row.get("kadence_rpm")), _int(row.get("tep_bpm")),
                                  _int(row.get("ventilator")) or 0, _int(row.get("ftp")) or 0,
                                  _int(row.get("max_tep")) or 0))
    return samples, start_from_name(Path(path))


def list_rides(limit: int = 30, folder: Path | None = None) -> list[Path]:
    folder = folder or rides_dir()
    files = sorted(folder.glob("*.csv"), key=lambda p: p.name, reverse=True)
    return files[:limit]
