"""Chytré párování: které z nalezených senzorů jsou moje.

Postup: AntFan spustí hledání (~20 s) a vyzve jezdce, ať zašlape a
navlhčí pás. Vlastní senzory na to zareagují, sousedovy ne:

  * powermetr / trenažér: výkon nebo kadence vyskočí z 0 na > 0 a čítač
    událostí se začne hýbat (nebo se senzor teprve probudí a objeví),
  * tepový pás: z „bez kontaktu“ (0 / žádná data) na platný tep, nebo se
    teprve objeví, nebo tep výrazně stoupne,
  * Bluetooth: ze sledování reklam hodnoty nemáme, reakce = senzor se
    objevil až během hledání (pás se probudí po navlhčení, powermetr po
    pohybu kliky),
  * síla signálu (RSSI z ANT ext. zpráv nebo BT reklam) pomůže rozhodnout:
    vlastní senzory bývají blíž.

Modul nezávisí na GUI: PairingSession dostává FoundDevice ze skenu
(feed) a analyze() vrátí návrh výběru. Testy: tests/test_pairing.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .ant_backend import FE_TYPE, HR_TYPE, PM_TYPE, FoundDevice, base_type, is_ble

PAIR_SCAN_S = 20          # jak dlouho hledat
APPEAR_AFTER_S = 3.0      # senzor, který se objevil až po této době, se „probudil“
HR_VALID = 30             # nižší tep = bez kontaktu
HR_RISE = 12              # o kolik bpm musí tep stoupnout, aby to byla reakce
NEAR_RSSI = -60           # dBm a víc = blízko (vlastní kolo)

INSTRUCTION = ("Zašlapejte (aspoň pár otáček) a navlhčete tepový pás nebo se ho dotkněte. "
               "Senzory, které zareagují, jsou vaše.")


@dataclass
class _Track:
    dev: FoundDevice
    first_seen: float
    last_seen: float
    samples: list = field(default_factory=list)   # (t, value, cadence, events)
    rssi: int | None = None


@dataclass
class Verdict:
    device: FoundDevice
    reacted: bool
    near: bool
    reason: str

    @property
    def score(self) -> int:
        return (2 if self.reacted else 0) + (1 if self.near else 0)


@dataclass
class PairingResult:
    selected: list[FoundDevice]
    verdicts: list[Verdict]
    hints: list[str]

    @property
    def ok(self) -> bool:
        return bool(self.selected)

    def summary_lines(self) -> list[str]:
        out = []
        for d in self.selected:
            v = next((v for v in self.verdicts if v.device.key == d.key), None)
            out.append(f"{d.type_name} #{d.device_id}" + (f" – {v.reason}" if v else ""))
        return out


class PairingSession:
    """Sbírá průběh hodnot ze skenu a vyhodnotí, které senzory reagovaly."""

    def __init__(self, t0: float):
        self.t0 = t0
        self.tracks: dict[tuple[int, int], _Track] = {}

    def feed(self, dev: FoundDevice, now: float) -> None:
        tr = self.tracks.get(dev.key)
        if tr is None:
            tr = self.tracks[dev.key] = _Track(dev, now, now)
        tr.dev = dev
        tr.last_seen = now
        tr.samples.append((now, dev.last_value, getattr(dev, "cadence", None),
                           getattr(dev, "events", None)))
        rssi = getattr(dev, "rssi", None)
        if rssi is not None:
            tr.rssi = rssi if tr.rssi is None else max(tr.rssi, rssi)

    # ------------------------------------------------------------ vyhodnocení
    def _verdict(self, tr: _Track) -> Verdict:
        late = tr.first_seen - self.t0 >= APPEAR_AFTER_S
        near = tr.rssi is not None and tr.rssi >= NEAR_RSSI
        bt = base_type(tr.dev.device_type)
        reacted, reason = False, ""
        if bt == HR_TYPE:
            reacted, reason = _hr_reaction(tr.samples, late)
        elif bt in (PM_TYPE, FE_TYPE):
            reacted, reason = _power_reaction(tr.samples, late)
        if not reacted and late and all(s[1] is None for s in tr.samples):
            reacted, reason = True, "objevil se až během hledání"
        if not reason:
            reason = "nereaguje, nejspíš cizí" if not near else "blízko, ale nereaguje"
        if near and reacted:
            reason += ", silný signál"
        return Verdict(tr.dev, reacted, near, reason)

    def analyze(self, prefer_ble: bool = False) -> PairingResult:
        verdicts = [self._verdict(tr) for tr in self.tracks.values()]
        verdicts.sort(key=lambda v: (-v.score, base_type(v.device.device_type), v.device.device_id))
        hr = _pick_hr(verdicts, prefer_ble)
        power = _pick_power(verdicts, prefer_ble)
        selected = [v.device for v in (hr, power) if v is not None]
        return PairingResult(selected, verdicts, _hints(verdicts, hr, power))


def _hr_reaction(samples, late) -> tuple[bool, str]:
    vals = [s[1] for s in samples]
    valid = [(i, v) for i, v in enumerate(vals) if v is not None and v >= HR_VALID]
    if not valid:
        return False, ""
    first_valid = valid[0][0]
    if any(v is not None and v < HR_VALID for v in vals[:first_valid]):
        return True, "pás začal měřit"
    if late:
        return True, "pás se probudil během hledání"
    lo_i, lo = min(valid, key=lambda x: x[1])
    hi_after = max((v for i, v in valid if i > lo_i), default=lo)
    if hi_after - lo >= HR_RISE:
        return True, f"tep stoupl o {hi_after - lo} bpm"
    return False, ""


def _moving(samples) -> bool:
    """Šlape se: výkon nebo kadence > 0 a čítač událostí se hýbe (je-li znám)."""
    prev_ev = None
    for _t, val, cad, ev in samples:
        active = (val or 0) > 0 or (cad or 0) > 0
        if active and (ev is None or (prev_ev is not None and ev != prev_ev)):
            return True
        prev_ev = ev if ev is not None else prev_ev
    return False


def _power_reaction(samples, late) -> tuple[bool, str]:
    known = [s for s in samples if s[1] is not None or s[2] is not None]
    if not known:
        return False, ""
    idle_idx = next((i for i, s in enumerate(known) if (s[1] or 0) == 0 and (s[2] or 0) == 0), None)
    if idle_idx is not None and _moving(known[idle_idx:]):
        return True, "výkon z 0 vyskočil"
    if late and _moving(known):
        return True, "probudil se šlapáním"
    return False, ""


def _rank(v: Verdict, prefer_ble: bool):
    # ANT+ / Bluetooth podle přání má přednost před silou signálu
    return (v.reacted, is_ble(v.device.device_type) == prefer_ble, v.near, v.device.rssi or -999)


def _pick_hr(verdicts, prefer_ble) -> Verdict | None:
    hrs = [v for v in verdicts if base_type(v.device.device_type) == HR_TYPE]
    good = [v for v in hrs if v.reacted]
    if good:
        return max(good, key=lambda v: _rank(v, prefer_ble))
    return _only_one(hrs)


def _only_one(cands) -> Verdict | None:
    """Jediný senzor svého druhu v dosahu – nejspíš vlastní (i když nereagoval)."""
    phys = {(is_ble(v.device.device_type), v.device.device_id) for v in cands}
    if len(phys) == 1:
        v = max(cands, key=lambda v: base_type(v.device.device_type) == FE_TYPE)
        v.reason = "jediný v dosahu (nereagoval)"
        return v
    return None


def _pick_power(verdicts, prefer_ble) -> Verdict | None:
    """Powermetr má přednost před trenažérem; trenažér (stejné ID jako PM i FE) jen jednou."""
    pw = [v for v in verdicts if base_type(v.device.device_type) in (PM_TYPE, FE_TYPE)]
    groups: dict[tuple[bool, int], list[Verdict]] = {}
    for v in pw:
        groups.setdefault((is_ble(v.device.device_type), v.device.device_id), []).append(v)
    meters, trainers = [], []
    for vs in groups.values():
        types = {base_type(v.device.device_type) for v in vs}
        reacted = any(v.reacted for v in vs)
        if FE_TYPE in types:
            fe = next(v for v in vs if base_type(v.device.device_type) == FE_TYPE)
            if reacted and not fe.reacted:  # reagoval jen „powermetr“ trenažéru
                other = next(v for v in vs if v.reacted)
                fe.reacted, fe.near, fe.reason = True, fe.near or other.near, other.reason
            trainers.append(fe)
        else:
            meters.append(vs[0])
    good_m = [v for v in meters if v.reacted]
    if good_m:
        return max(good_m, key=lambda v: _rank(v, prefer_ble))
    good_t = [v for v in trainers if v.reacted]
    if good_t:
        return max(good_t, key=lambda v: _rank(v, prefer_ble))
    return _only_one(pw)


def _hints(verdicts, hr, power) -> list[str]:
    if not verdicts:
        return ["Nenašel se žádný senzor. Zkontrolujte, že je ANT+ dongle zapojený (nebo zapnutý "
                "Bluetooth), pás nasazený a navlhčený a během hledání šlapejte, aby se powermetr "
                "probudil. Pak to zkuste znovu."]
    out = []
    if not any(v.reacted for v in verdicts):
        out.append("Žádný senzor nezareagoval. Hned po spuštění zašlapejte aspoň pár otáček a navlhčete "
                   "pás. Pokud jsou senzory spárované s Rouvy přes Bluetooth, nemusí se AntFanu ukázat.")
    if hr is None:
        if any(base_type(v.device.device_type) == HR_TYPE for v in verdicts):
            out.append("Tepový pás nepoznám: v dosahu je víc pásů a žádný nezareagoval. Navlhčete "
                       "elektrody, nasaďte pás a zkuste znovu, nebo ho vyberte ručně.")
        else:
            out.append("Tepový pás se nenašel: navlhčete elektrody a nasaďte ho, bez kontaktu nevysílá.")
    if power is None:
        if any(base_type(v.device.device_type) in (PM_TYPE, FE_TYPE) for v in verdicts):
            out.append("Výkon nepoznám: v dosahu je víc powermetrů/trenažérů a žádný nezareagoval. "
                       "Během hledání šlapejte, nebo vyberte senzor ručně.")
        else:
            out.append("Powermetr ani trenažér se nenašel: zašlapejte, probouzí se pohybem.")
    return out
