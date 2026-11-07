"""Průvodce souběhem s Rouvy, Zwiftem a podobnými aplikacemi.

Jeden ANT+ dongle může mít v jednu chvíli jen jeden program. Když AntFan
pozná běžící tréninkovou aplikaci (výpis procesů z usb_diag, Windows
i macOS), nebo když dongle drží jiný program, poradí podle situace:

  a) dva dongly – každý program má svůj, není co řešit,
  b) dongle má Rouvy (ANT+) → AntFan přepne na Bluetooth verze senzorů,
  c) AntFan má dongle (ANT+) → v Rouvy párovat senzory přes Bluetooth.

Bluetooth senzor (trenažér, pás) obvykle dovolí jen 1–2 spojení naráz,
proto ho nemá smysl připojovat přes BT k oběma programům.

Logika je bez GUI (testy: tests/test_coexist.py). App volá probe() ve
vlákně a advise() s výsledkem; text ukazuje v pruhu v okně jízdy
a na stránce Nastavení → Souběh.
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field

from . import usb_diag
from .ant_backend import FE_TYPE, HR_TYPE, PM_TYPE, FoundDevice, base_type, is_ble
from .i18n import _, N_

log = logging.getLogger("antfan.coexist")

# tréninkové aplikace, které čtou senzory (podřetězec názvu procesu malými písmeny)
TRAINING_APPS = {
    "rouvy": "ROUVY",
    "zwift": "Zwift",
    "trainerroad": "TrainerRoad",
    "mywhoosh": "MyWhoosh",
    "fulgaz": "FulGaz",
    "indievelo": "TrainingPeaks Virtual",
    "trainingpeaks": "TrainingPeaks Virtual",
    "systm": "Wahoo SYSTM",
    "kinomap": "Kinomap",
    "bkool": "BKOOL",
    "biketerra": "Biketerra",
}
# pomocné procesy, které senzory nečtou (Zwift Launcher drží dongle, ale nejezdí se v něm)
_IGNORE = ("crashpad", "helper", "updater", "webview", "installer")

BT_LIMIT = (N_("Trenažér i pás obvykle dovolí jen 1–2 Bluetooth spojení naráz, proto stejný senzor "
            "nepřipojujte přes Bluetooth k oběma programům."))


@dataclass
class Situation:
    apps: list[str] = field(default_factory=list)   # běžící tréninkové aplikace
    dongles: int = 0                                 # zapojené ANT+ dongly (0 = nevíme / žádný)
    busy: bool = False                               # dongle drží jiný program


@dataclass
class Advice:
    kind: str          # "two_dongles" | "antfan_bt" | "app_bt" | "bt_clash"
    short: str         # jeden řádek do pruhu
    text: str          # celé doporučení (stránka Souběh)
    can_switch: bool = False  # nabídnout „Přepnout na Bluetooth senzory“


# ------------------------------------------------------------------ detekce
def _mac_processes() -> list[tuple[int, str, str]]:
    try:
        out = subprocess.run(["ps", "-axo", "pid=,comm="], capture_output=True, text=True,
                             timeout=10).stdout
    except Exception as e:  # noqa: BLE001
        log.info("ps selhalo: %s", e)
        return []
    procs = []
    for line in out.splitlines():
        m = re.match(r"\s*(\d+)\s+(.*)$", line)
        if m:
            path = m.group(2).strip()
            procs.append((int(m.group(1)), os.path.basename(path), path))
    return procs


def list_processes() -> list[tuple[int, str, str]]:
    procs = usb_diag.list_processes()
    if not procs and sys.platform == "darwin":
        procs = _mac_processes()
    return procs


def training_apps(procs) -> list[str]:
    """Názvy běžících tréninkových aplikací (každá jednou)."""
    me = os.getpid()
    found: list[str] = []
    for pid, name, cmd in procs:
        if pid == me:
            continue
        low = name.lower()
        # macOS: název aplikace je v cestě (…/Zwift.app/Contents/MacOS/ZwiftAppSilicon)
        app = re.search(r"/([^/]+)\.app/", cmd or "")
        hay = low + " " + (app.group(1).lower() if app else "")
        if any(x in low for x in _IGNORE):
            continue
        for key, label in TRAINING_APPS.items():
            if key in hay:
                if label not in found:
                    found.append(label)
                break
    return found


def probe(count_dongles: bool = True) -> Situation:
    """Zjistí situaci (pomalé: výpis procesů, volat mimo GUI vlákno)."""
    sit = Situation(apps=training_apps(list_processes()))
    if count_dongles:
        try:
            devs = usb_diag.find_dongles()
            sit.dongles = len(devs)
            usb_diag._dispose(devs)  # noqa: SLF001
        except Exception as e:  # noqa: BLE001
            log.info("Počet donglů nezjištěn: %s", e)
    return sit


def is_busy_error(text: str) -> bool:
    """Je chyba z ANT+ hláška usb_diag.busy_message (dongle drží jiný program)?"""
    return text.startswith(usb_diag.busy_message([], []).split("\n")[0])


# ------------------------------------------------------------------ doporučení
def advise(sit: Situation, selected: list[FoundDevice], devices: list[FoundDevice]) -> Advice | None:
    if not sit.apps and not sit.busy:
        return None
    who = ", ".join(sit.apps) if sit.apps else _("jiný program")
    uses_bt = any(is_ble(d.device_type) for d in selected)
    uses_ant = any(not is_ble(d.device_type) for d in selected)

    if sit.dongles >= 2 and not sit.busy:
        return Advice("two_dongles", _("Běží {who}. Máte dva ANT+ dongly, každý program má svůj.").format(who=who),
                      _("Běží {who} a jsou zapojené dva ANT+ dongly. AntFan si vezme volný, {who} ten druhý. V obou programech párujte senzory přes ANT+, ANT+ senzor vysílá všem naráz. Na Bluetooth nic neměňte.").format(who=who))

    if sit.busy and (uses_ant or not uses_bt):
        counterpart = bt_counterparts(selected, devices)
        can = any(v is not None for v in counterpart.values())
        how = (_("Klikněte na „Přepnout na Bluetooth senzory“, AntFan vybere BT verze vašich senzorů.")
               if can else _("V Nastavení → Senzory spusťte hledání a vyberte senzory s označením (BT)."))
        return Advice("antfan_bt", _("ANT+ dongle drží {who}. AntFan může jet přes Bluetooth.").format(who=who),
                      _("ANT+ dongle drží {who}. Nechte ho tam a AntFan připojte k senzorům přes Bluetooth. {how}\n\nV {who} pak párujte senzory jen přes ANT+, ať se o Bluetooth nepřetahujete. {BT_LIMIT}\n\nSpolehlivější je druhý ANT+ dongle: AntFan si vezme ten volný a vše zůstane na ANT+.").format(who=who, how=how, BT_LIMIT=_(BT_LIMIT)), can_switch=can)

    if uses_bt:
        return Advice("bt_clash", _("Běží {who} a AntFan čte senzory přes Bluetooth.").format(who=who),
                      _("Běží {who} a AntFan je připojen k senzorům přes Bluetooth. {BT_LIMIT} Když {who} používá ANT+, je vše v pořádku. Pokud i {who} jede přes Bluetooth, připojte jeden z programů přes ANT+ (AntFan: vyberte senzory bez označení (BT)).").format(who=who, BT_LIMIT=_(BT_LIMIT)))

    return Advice("app_bt", _("Běží {who}. V něm párujte senzory přes Bluetooth.").format(who=who),
                  _("Běží {who}. ANT+ dongle má AntFan, takže v {who} párujte senzory přes Bluetooth (ANT+ senzory, které umí obojí, vysílají i BT). {BT_LIMIT}\n\nKdyž chcete mít v obou programech ANT+, zapojte druhý dongle.").format(who=who, BT_LIMIT=_(BT_LIMIT)))


# ----------------------------------------------------------- BT protějšky
def _kind(t: int) -> str:
    bt = base_type(t)
    return "hr" if bt == HR_TYPE else ("power" if bt in (PM_TYPE, FE_TYPE) else "?")


def bt_counterparts(selected: list[FoundDevice], devices: list[FoundDevice]
                    ) -> dict[tuple[int, int], FoundDevice | None]:
    """Pro každý vybraný ANT+ senzor jeho Bluetooth verzi (nebo None).

    Shoda: BT název obsahuje ANT+ ID (Tacx, Garmin, Wahoo to tak dělají),
    jinak jediný BT senzor stejného druhu v dosahu. Trenažér přes BT:
    přednost má FTMS, pro powermetr Cycling Power.
    """
    ble = [d for d in devices if is_ble(d.device_type)]
    ant_ids = {d.device_id for d in list(devices) + list(selected) if not is_ble(d.device_type)}
    out: dict[tuple[int, int], FoundDevice | None] = {}
    for d in selected:
        if is_ble(d.device_type):
            continue
        kind = _kind(d.device_type)
        cands = [b for b in ble if _kind(b.device_type) == kind]
        by_name = [b for b in cands if b.name and re.search(rf"(?<!\d){d.device_id}(?!\d)", b.name)]
        # bez shody v názvu jen jediný kandidát, a to ne BT verze jiného ANT+ senzoru
        free = [b for b in cands if not any(re.search(rf"(?<!\d){i}(?!\d)", b.name or "")
                                            for i in ant_ids - {d.device_id})]
        pool = by_name or (free if len({b.device_id for b in free}) == 1 else [])
        if not pool:
            out[d.key] = None
            continue
        want = FE_TYPE if base_type(d.device_type) == FE_TYPE else PM_TYPE
        pool.sort(key=lambda b: (base_type(b.device_type) != want, -(b.rssi or -999)))
        out[d.key] = pool[0]
    return out


def switch_to_bt(selected: list[FoundDevice], devices: list[FoundDevice]
                 ) -> tuple[list[FoundDevice], list[FoundDevice]]:
    """Nový výběr s BT verzemi senzorů. Vrací (výběr, ANT+ senzory bez BT protějšku)."""
    cp = bt_counterparts(selected, devices)
    new, missing = [], []
    for d in selected:
        if is_ble(d.device_type):
            new.append(d)
        elif cp.get(d.key) is not None:
            if cp[d.key].key not in {n.key for n in new}:
                new.append(cp[d.key])
        else:
            missing.append(d)
            new.append(d)
    return new, missing
