"""Další druhy ventilátorů a společné pomůcky.

* převod stupňů AntFan (1..N) na hodnoty ventilátoru (stupně nebo rychlost v %),
* vyhledání vlastností neznámého Xiaomi modelu ve veřejné specifikaci MIoT,
* Shelly relé (obyčejný ventilátor v chytré zásuvce, jen zapnuto/vypnuto),
* Home Assistant (jakýkoli fan.* nebo switch.* entita přes REST API).

Všechny třídy mají stejné rozhraní jako XiaomiFan:
info(), get_state() -> (zapnuto, stupeň), set_level(stupeň), apply_quiet() -> [nepodporované].
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request

log = logging.getLogger("antfan.fan")

SPEC_BASE = "https://miot-spec.org/miot-spec-v2"


class FanError(Exception):
    pass


# --------------------------------------------------------------- stupně
def map_level(level: int, n: int, values) -> int:
    """Stupeň AntFan 1..n -> hodnota pro ventilátor."""
    n = max(1, n)
    level = max(1, min(level, n))
    if not values:
        return level
    if values[0] == "range":
        lo, hi = int(values[1]), int(values[2])
        return max(lo, min(hi, round(lo + (hi - lo) * level / n)))
    k = len(values)
    if n == 1:
        return values[-1]
    return values[round((level - 1) * (k - 1) / (n - 1))] if k != n else values[level - 1]


def unmap_level(value, n: int, values) -> int:
    """Hodnota z ventilátoru -> nejbližší stupeň AntFan 1..n."""
    try:
        value = int(value)
    except (TypeError, ValueError):
        return 1
    return min(range(1, max(1, n) + 1), key=lambda lv: abs(map_level(lv, n, values) - value))


# --------------------------------------------------------------- MIoT specifikace
def _short(urn: str) -> str:
    return urn.split(":")[3]


def extract_spec(spec: dict):
    """Ze specifikace MIoT vytáhne (power, level, hodnoty, pípání, podsvícení) nebo None."""
    svcs = spec.get("services", [])
    fan = next((s for s in svcs if _short(s["type"]) == "fan"), None)
    if not fan:
        return None
    props = {_short(p["type"]): p for p in fan.get("properties", [])}
    if "on" not in props:
        return None
    power = (fan["iid"], props["on"]["iid"])
    lv = props.get("fan-level")
    if lv and lv.get("value-list"):
        vals = tuple(v["value"] for v in lv["value-list"])
    elif lv and lv.get("value-range"):
        lo, hi, st = lv["value-range"]
        vals = tuple(range(int(lo), int(hi) + 1, int(st or 1)))
    else:
        lv = props.get("speed-level")
        if not lv or not lv.get("value-range"):
            return None
        vals = ("range", int(lv["value-range"][0]), int(lv["value-range"][1]))
    if vals and vals[0] != "range" and len(vals) > 10:
        vals = ("range", vals[0], vals[-1])
    level = (fan["iid"], lv["iid"])
    buzzer = light = None
    for s in svcs:
        k = _short(s["type"])
        ps = {_short(p["type"]): p for p in s.get("properties", [])}
        if k == "alarm" and "alarm" in ps and ps["alarm"].get("format") == "bool":
            buzzer = (s["iid"], ps["alarm"]["iid"])
        if k == "indicator-light" and "on" in ps:
            light = (s["iid"], ps["on"]["iid"])
    if buzzer is None and props.get("alarm", {}).get("format") == "bool":
        buzzer = (fan["iid"], props["alarm"]["iid"])
    if light is None:
        for k in ("indicator-light", "screen", "light", "brightness"):
            if props.get(k, {}).get("format") == "bool":
                light = (fan["iid"], props[k]["iid"])
                break
    return power, level, vals, buzzer, light


def _get_json(url: str, timeout: float = 20.0):
    req = urllib.request.Request(url, headers={"User-Agent": "AntFan"})
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310
        return json.loads(r.read().decode("utf-8"))


def spec_lookup(model: str):
    """Vlastnosti neznámého modelu z miot-spec.org (výsledek se ukládá do mezipaměti)."""
    from .config import app_dir

    cache = app_dir() / "miot"
    cache.mkdir(exist_ok=True)
    path = cache / f"{model}.json"
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
        else:
            inst = _get_json(f"{SPEC_BASE}/instances?status=released")["instances"]
            mine = [i for i in inst if i.get("model") == model]
            if not mine:
                log.info("Model %s není ve specifikacích MIoT", model)
                return None
            best = max(mine, key=lambda i: i.get("version", 0))
            data = _get_json(f"{SPEC_BASE}/instance?type={urllib.parse.quote(best['type'], safe=':')}")
            path.write_text(json.dumps(data), encoding="utf-8")
        prof = extract_spec(data)
        log.info("Specifikace %s: %s", model, prof)
        return prof
    except Exception as e:  # noqa: BLE001
        log.warning("Specifikaci pro %s se nepodařilo získat: %s", model, e)
        return None


# --------------------------------------------------------------- zapnuto/vypnuto
class _OnOff:
    """Společná logika pro zařízení, která umí jen zapnout a vypnout.

    Stupeň >= on_level = zapnuto. get_state vrací poslední nastavený stupeň,
    dokud skutečný stav relé odpovídá; jinak hodnotu, která vynutí opravu.
    """

    def __init__(self, cfg):
        self.cfg = cfg
        self._last: int | None = None

    def _want_on(self, level: int) -> bool:
        return level > 0 and level >= max(1, self.cfg.on_level)

    def _state_from(self, is_on: bool) -> tuple[bool, int]:
        on_lv = max(1, self.cfg.on_level)
        if self._last is not None and is_on == self._want_on(self._last):
            return self._last > 0, self._last
        return is_on, on_lv if is_on else 0

    def apply_quiet(self) -> list[str]:
        return []


class ShellyFan(_OnOff):
    """Shelly relé v lokální síti (Gen1 i Gen2+/Plus/Pro), bez hesla."""

    def __init__(self, cfg):
        super().__init__(cfg)
        host = cfg.shelly_host.strip()
        if not host:
            raise FanError("Zadejte IP adresu Shelly.")
        self.base = host if host.startswith("http") else f"http://{host}"
        self.ch = int(cfg.shelly_channel)
        self._gen: int | None = None

    def _get(self, path: str):
        try:
            return _get_json(self.base + path, timeout=3.0)
        except urllib.error.HTTPError as e:
            if e.code == 401:
                raise FanError("Shelly má zapnuté heslo. AntFan zatím umí jen Shelly bez hesla.") from e
            raise FanError(f"Shelly vrátilo chybu {e.code}") from e
        except (urllib.error.URLError, OSError, ValueError) as e:
            raise FanError(f"Shelly na {self.base} neodpovídá ({e})") from e

    def _generation(self) -> int:
        if self._gen is None:
            info = self._get("/shelly")
            self._gen = int(info.get("gen", 1))
        return self._gen

    def info(self) -> dict:
        info = self._get("/shelly")
        self._gen = int(info.get("gen", 1))
        return {"model": f"Shelly {info.get('model') or info.get('type', '?')}",
                "fw_ver": info.get("fw_id") or info.get("fw", "?")}

    def get_state(self) -> tuple[bool, int]:
        if self._generation() >= 2:
            on = bool(self._get(f"/rpc/Switch.GetStatus?id={self.ch}").get("output"))
        else:
            on = bool(self._get(f"/relay/{self.ch}").get("ison"))
        return self._state_from(on)

    def set_level(self, level: int) -> None:
        on = self._want_on(level)
        if self._generation() >= 2:
            self._get(f"/rpc/Switch.Set?id={self.ch}&on={'true' if on else 'false'}")
        else:
            self._get(f"/relay/{self.ch}?turn={'on' if on else 'off'}")
        self._last = level


class HomeAssistantFan(_OnOff):
    """Entita v Home Assistant: fan.* (rychlost v %) nebo switch.*/input_boolean.* (zap/vyp)."""

    def __init__(self, cfg):
        super().__init__(cfg)
        url, tok, ent = cfg.ha_url.strip().rstrip("/"), cfg.ha_token.strip(), cfg.ha_entity.strip()
        if not (url and tok and ent):
            raise FanError("Zadejte adresu Home Assistant, token a entitu.")
        if "." not in ent:
            raise FanError("Entita musí mít tvar fan.nazev nebo switch.nazev.")
        self.base = url if url.startswith("http") else f"http://{url}"
        self.token, self.entity = tok, ent
        self.domain = ent.split(".", 1)[0]

    def _call(self, path: str, body: dict | None = None):
        req = urllib.request.Request(
            self.base + path, method="POST" if body is not None else "GET",
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=4.0) as r:  # noqa: S310
                txt = r.read().decode("utf-8")
                return json.loads(txt) if txt else None
        except urllib.error.HTTPError as e:
            if e.code == 401:
                raise FanError("Home Assistant odmítl token (401).") from e
            if e.code == 404:
                raise FanError(f"Home Assistant nezná entitu {self.entity}.") from e
            raise FanError(f"Home Assistant vrátil chybu {e.code}") from e
        except (urllib.error.URLError, OSError, ValueError) as e:
            raise FanError(f"Home Assistant na {self.base} neodpovídá ({e})") from e

    def info(self) -> dict:
        st = self._call(f"/api/states/{self.entity}")
        name = (st or {}).get("attributes", {}).get("friendly_name", self.entity)
        return {"model": f"Home Assistant: {name}", "fw_ver": "-"}

    def get_state(self) -> tuple[bool, int]:
        st = self._call(f"/api/states/{self.entity}") or {}
        on = st.get("state") == "on"
        if self.domain == "fan":
            pct = st.get("attributes", {}).get("percentage")
            if not on:
                return False, 0
            if pct is None:
                return self._state_from(True)
            return True, unmap_level(pct, self.cfg.max_level, ("range", 1, 100))
        return self._state_from(on)

    def set_level(self, level: int) -> None:
        ent = {"entity_id": self.entity}
        if self.domain == "fan":
            if level <= 0:
                self._call("/api/services/fan/turn_off", ent)
            else:
                pct = map_level(level, self.cfg.max_level, ("range", 1, 100))
                self._call("/api/services/fan/set_percentage", {**ent, "percentage": pct})
        else:
            svc = "turn_on" if self._want_on(level) else "turn_off"
            self._call(f"/api/services/{self.domain}/{svc}", ent)
        self._last = level
