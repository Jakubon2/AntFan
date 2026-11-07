"""Stav baterie ANT+ senzorů.

Zdroje:
  * společná stránka 0x52 (Battery Status) – posílají ji všechny profily:
      byte 6  zlomek napětí (1/256 V)
      byte 7  bity 0–3 celé volty (0xF = neplatné), bity 4–6 stav
              (1 nová, 2 dobrá, 3 OK, 4 slabá, 5 kritická)
  * tepový pás, stránka 7 (Battery Status v profilu HR):
      byte 1  baterie v % (0xFF = neuvedeno)
      byte 2  zlomek napětí, byte 3 stejné bitové pole jako byte 7 výše
U tepového pásu je nejvyšší bit čísla stránky přepínač, proto & 0x7F.

Do fronty jde ("battery", key, pct_nebo_None, stav_nebo_None) jen při změně.
"""
from __future__ import annotations

import threading

HR_TYPE = 120

NEW, GOOD, OK, LOW, CRITICAL = 1, 2, 3, 4, 5
STATUS_NAMES = {NEW: "nová", GOOD: "dobrá", OK: "OK", LOW: "slabá", CRITICAL: "kritická"}
DEFAULT_PCT = 20


def _bitfield(fraction: int, desc: int) -> tuple[int | None, float | None]:
    status = (desc >> 4) & 0x07
    status = status if status in STATUS_NAMES else None
    coarse = desc & 0x0F
    volts = None if coarse == 0x0F else round(coarse + fraction / 256.0, 2)
    return status, volts


def decode_battery(device_type: int, data) -> tuple[int | None, int | None, float | None] | None:
    """(procenta, stav, napětí V) ze stránky o baterii, jinak None."""
    if len(data) < 8:
        return None
    page = data[0] & 0x7F if device_type == HR_TYPE else data[0]
    if page == 0x52:
        status, volts = _bitfield(data[6], data[7])
        pct = None
    elif page == 0x07 and device_type == HR_TYPE:
        status, volts = _bitfield(data[2], data[3])
        pct = data[1] if data[1] <= 100 else None
    else:
        return None
    if pct is None and status is None and volts is None:
        return None
    return pct, status, volts


class BatteryTracker:
    """Pamatuje si poslední stav každého senzoru; událost vrací jen při změně."""

    def __init__(self):
        self._lock = threading.Lock()
        self._last: dict[tuple[int, int], tuple[int | None, int | None]] = {}

    def feed(self, key: tuple[int, int], data):
        dec = decode_battery(key[1], data)
        if dec is None:
            return None
        pct, status, _volts = dec
        with self._lock:
            if self._last.get(key) == (pct, status):
                return None
            self._last[key] = (pct, status)
        return ("battery", key, pct, status)


def is_low(pct: int | None, status: int | None, level: int = LOW, pct_limit: int = DEFAULT_PCT) -> bool:
    """Slabá baterie: podle % tam, kde je senzor posílá, jinak podle stavu."""
    if pct is not None:
        return pct < pct_limit
    return status is not None and status >= level


def text(pct: int | None, status: int | None) -> str:
    if pct is not None:
        return f"{pct} %"
    return STATUS_NAMES.get(status, "") if status is not None else ""


# --- pro simulaci -----------------------------------------------------------
def page_common(status: int, volts: float) -> list[int]:
    coarse = int(volts)
    frac = int(round((volts - coarse) * 256)) & 0xFF
    return [0x52, 0xFF, 0x00, 0, 0, 0, frac, (status << 4) | (coarse & 0x0F)]


def page_hr(pct: int, status: int, volts: float, hr: int = 0) -> list[int]:
    p = page_common(status, volts)
    return [0x07, pct & 0xFF, p[6], p[7], 0, 0, 0, hr & 0xFF]
