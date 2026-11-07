"""Ovládání Xiaomi ventilátoru přes lokální protokol miIO (UDP 54321).

Vlastní minimální implementace protokolu (handshake + AES-128-CBC), aby
program nepotřeboval knihovnu python-miio (ta na Windows vyžaduje
kompilaci balíčku netifaces).

Výchozí hodnoty odpovídají Xiaomi Smart Standing Fan 2 Lite (dmaker.fan.1c):
    power      siid 2, piid 1   (bool)
    fan_level  siid 2, piid 2   (1..3)
"""
from __future__ import annotations

import hashlib
import json
import logging
import queue
import random
import socket
import struct
import threading
import time
from dataclasses import dataclass, field

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from .i18n import _

log = logging.getLogger("antfan.fan")

MIIO_PORT = 54321
HELLO = bytes.fromhex("21310020" + "ff" * 28)


class MiioError(Exception):
    pass


def _md5(data: bytes) -> bytes:
    return hashlib.md5(data).digest()


class MiioClient:
    """Nízkoúrovňový klient miIO protokolu."""

    def __init__(self, ip: str, token_hex: str, timeout: float = 3.0):
        token_hex = (token_hex or "").strip()
        try:
            self.token = bytes.fromhex(token_hex)
        except ValueError as e:
            raise MiioError(_("Token musí být 32 hexadecimálních znaků")) from e
        if len(self.token) != 16:
            raise MiioError(_("Token musí mít 32 hexadecimálních znaků (16 bajtů)"))
        self.ip = ip.strip()
        self.timeout = timeout
        self._key = _md5(self.token)
        self._iv = _md5(self._key + self.token)
        self._did: int | None = None
        self._stamp: int = 0
        self._handshake_at = 0.0
        self._msg_id = random.randint(1, 10000)

    # --- šifrování -------------------------------------------------------
    def encrypt(self, plain: bytes) -> bytes:
        padder = padding.PKCS7(128).padder()
        padded = padder.update(plain) + padder.finalize()
        enc = Cipher(algorithms.AES(self._key), modes.CBC(self._iv)).encryptor()
        return enc.update(padded) + enc.finalize()

    def decrypt(self, data: bytes) -> bytes:
        dec = Cipher(algorithms.AES(self._key), modes.CBC(self._iv)).decryptor()
        padded = dec.update(data) + dec.finalize()
        unpadder = padding.PKCS7(128).unpadder()
        return unpadder.update(padded) + unpadder.finalize()

    # --- pakety ------------------------------------------------------------
    def build_packet(self, payload: bytes, did: int, stamp: int) -> bytes:
        enc = self.encrypt(payload)
        header = struct.pack(">HHIII", 0x2131, 32 + len(enc), 0, did, stamp)
        checksum = _md5(header + self.token + enc)
        return header + checksum + enc

    def parse_packet(self, data: bytes) -> tuple[int, int, bytes]:
        if len(data) < 32:
            raise MiioError(_("Příliš krátká odpověď"))
        magic, length, _unk, did, stamp = struct.unpack(">HHIII", data[:16])
        if magic != 0x2131:
            raise MiioError(_("Neplatná odpověď (magic)"))
        body = data[32:length]
        if body:
            expected = _md5(data[:16] + self.token + body)
            if expected != data[16:32]:
                raise MiioError(_("Neplatný kontrolní součet – špatný token?"))
        return did, stamp, body

    def _socket(self) -> socket.socket:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(self.timeout)
        return s

    def handshake(self) -> None:
        with self._socket() as s:
            try:
                s.sendto(HELLO, (self.ip, MIIO_PORT))
                data, _u = s.recvfrom(1024)
            except socket.timeout as e:
                raise MiioError(
                    _("Ventilátor na {ip} neodpovídá (zkontrolujte IP a Wi-Fi)").format(ip=self.ip)
                ) from e
            except OSError as e:
                raise MiioError(_("Síťová chyba: {e}").format(e=e)) from e
        _magic, _len, _unk, did, stamp = struct.unpack(">HHIII", data[:16])
        self._did = did
        self._stamp = stamp
        self._handshake_at = time.monotonic()

    def send(self, method: str, params=None):
        if params is None:
            params = []
        if self._did is None or time.monotonic() - self._handshake_at > 60:
            self.handshake()
        self._msg_id = (self._msg_id + 1) % 100000 or 1
        msg_id = self._msg_id
        payload = json.dumps({"id": msg_id, "method": method, "params": params}).encode()
        packet = self.build_packet(payload + b"\x00", self._did, self._stamp + 1)
        with self._socket() as s:
            try:
                s.sendto(packet, (self.ip, MIIO_PORT))
                deadline = time.monotonic() + self.timeout
                while True:
                    data, _u = s.recvfrom(4096)
                    _did, stamp, body = self.parse_packet(data)
                    self._stamp = stamp
                    if not body:
                        continue
                    try:
                        text = self.decrypt(body)
                    except ValueError as e:
                        raise MiioError(_("Nelze dešifrovat odpověď – špatný token?")) from e
                    text = text.rstrip(b"\x00")
                    resp = json.loads(text.decode("utf-8", errors="replace"))
                    if resp.get("id") != msg_id and time.monotonic() < deadline:
                        continue  # odpověď na starší dotaz
                    break
            except socket.timeout as e:
                self._did = None  # příště znovu handshake
                raise MiioError(
                    _("Ventilátor neodpověděl na příkaz (špatný token nebo nedostupný)")
                ) from e
            except OSError as e:
                self._did = None
                raise MiioError(_("Síťová chyba: {e}").format(e=e)) from e
        if "error" in resp:
            raise MiioError(_("Ventilátor vrátil chybu: {v}").format(v=resp['error']))
        return resp.get("result")


@dataclass
class FanConfig:
    kind: str = "xiaomi"       # xiaomi | shelly | homeassistant
    ip: str = ""
    token: str = ""
    max_level: int = 3
    model: str = ""            # zjištěný model (jen pro informaci)
    auto_model: bool = True    # vlastnosti vybrat podle modelu ventilátoru
    power_siid: int = 2
    power_piid: int = 1
    level_siid: int = 2
    level_piid: int = 2
    level_values: list = field(default_factory=list)  # [] = 1..max_level, ["range", od, do] = %
    mute_buzzer: bool = True   # ventilátor jinak pípne při každém příkazu
    light_off: bool = True
    buzzer_siid: int = 2
    buzzer_piid: int = 11
    light_siid: int = 2
    light_piid: int = 12
    # Shelly / Home Assistant
    shelly_host: str = ""
    shelly_channel: int = 0
    on_level: int = 1          # od jakého stupně zapnout (zařízení jen zap/vyp)
    ha_url: str = ""
    ha_token: str = ""
    ha_entity: str = ""


def _device_error(e: Exception) -> bool:
    """Chyba vrácená ventilátorem (příkaz nepodporuje), ne síťová chyba."""
    return isinstance(e, MiioError) and _("vrátil chybu") in str(e)


class XiaomiFan:
    """Vysokoúrovňové ovládání: stupeň 0 = vypnuto, 1..max_level = rychlost.

    Při prvním spojení zjistí model a vybere vlastnosti z předvoleb
    (fan_presets), případně ze specifikace MIoT na internetu. Starší modely
    ovládá starým protokolem (set_power / s_power).
    """

    def __init__(self, cfg: FanConfig):
        self.cfg = cfg
        self.client = MiioClient(cfg.ip, cfg.token)
        self._prof = None
        self.note: str | None = None

    def info(self) -> dict:
        return self.client.send("miIO.info", []) or {}

    def _manual(self):
        c = self.cfg
        vals = tuple(c.level_values) if c.level_values else ()
        return ((c.power_siid, c.power_piid), (c.level_siid, c.level_piid), vals,
                (c.buzzer_siid, c.buzzer_piid), (c.light_siid, c.light_piid))

    def _profile(self):
        if self._prof is not None:
            return self._prof
        c = self.cfg
        if not c.auto_model:
            self._prof = self._manual()
            return self._prof
        from .fan_presets import LEGACY, PRESETS
        from .fans import spec_lookup

        model = str(self.info().get("model", ""))
        c.model = model
        if model in LEGACY:
            self._prof = ("legacy", LEGACY[model])
            self.note = _("model {model} (starší protokol, neověřeno)").format(model=model)
        elif model in PRESETS:
            self._prof = PRESETS[model]
            self.note = f"model {model}"
        else:
            prof = spec_lookup(model) if model else None
            if prof:
                self._prof = prof
                self.note = _("model {model} (podle specifikace MIoT, neověřeno)").format(model=model)
            else:
                self._prof = self._manual()
                self.note = _("model {v} neznám, používám ruční nastavení").format(v=model or '?')
        log.info("Ventilátor %s, profil %s", model, self._prof)
        return self._prof

    def get_state(self) -> tuple[bool, int]:
        from .fans import unmap_level

        prof, n = self._profile(), self.cfg.max_level
        if prof[0] == "legacy":
            if prof[1] == "p5":
                power, speed = (self.client.send("get_prop", ["power", "speed"]) or [False, 0])[:2]
                return bool(power), unmap_level(speed, n, ("range", 1, 100))
            power, speed = (self.client.send("get_prop", ["power", "speed_level"]) or ["off", 0])[:2]
            return power == "on", unmap_level(speed, n, ("range", 1, 100))
        (ps, pp), (ls, lp), vals = prof[0], prof[1], prof[2]
        res = self.client.send("get_properties", [
            {"did": "power", "siid": ps, "piid": pp},
            {"did": "level", "siid": ls, "piid": lp},
        ])
        v = {r.get("did"): r.get("value") for r in (res or []) if r.get("code", 0) == 0}
        return bool(v.get("power")), unmap_level(v.get("level"), n, vals)

    def set_level(self, level: int) -> None:
        from .fans import map_level

        prof, n = self._profile(), self.cfg.max_level
        level = max(0, min(int(level), n))
        if prof[0] == "legacy":
            pct = map_level(level, n, ("range", 1, 100)) if level else 0
            if prof[1] == "p5":
                self.client.send("s_power", [level > 0])
                if level:
                    self.client.send("s_speed", [pct])
            else:
                self.client.send("set_power", ["on" if level else "off"])
                if level:
                    self.client.send("set_speed_level", [pct])
            return
        (ps, pp), (ls, lp), vals = prof[0], prof[1], prof[2]
        if level == 0:
            props = [{"did": "power", "siid": ps, "piid": pp, "value": False}]
        else:
            props = [
                {"did": "power", "siid": ps, "piid": pp, "value": True},
                {"did": "level", "siid": ls, "piid": lp, "value": map_level(level, n, vals)},
            ]
        res = self.client.send("set_properties", props)
        for r in res or []:
            if r.get("code", 0) != 0:
                raise MiioError(_("Ventilátor odmítl nastavení {v}: kód {v2}").format(v=r.get('did'), v2=r.get('code')))

    # --- rychlost v % (jen modely s rychlostí v %, viz vitr.py)
    def _pct_range(self):
        prof = self._profile()
        if prof[0] == "legacy":
            return 1, 100
        vals = prof[2]
        if vals and vals[0] == "range":
            return int(vals[1]), int(vals[2])
        return None

    def supports_percent(self) -> bool:
        return self._pct_range() is not None

    def set_percent(self, pct: float) -> None:
        from .vitr import pct_to_range

        rng = self._pct_range()
        if rng is None or pct <= 0:
            self.set_level(0 if pct <= 0 else self.cfg.max_level)
            return
        value = pct_to_range(pct, *rng)
        prof = self._profile()
        if prof[0] == "legacy":
            if prof[1] == "p5":
                self.client.send("s_power", [True])
                self.client.send("s_speed", [value])
            else:
                self.client.send("set_power", ["on"])
                self.client.send("set_speed_level", [value])
            return
        (ps, pp), (ls, lp) = prof[0], prof[1]
        res = self.client.send("set_properties", [
            {"did": "power", "siid": ps, "piid": pp, "value": True},
            {"did": "level", "siid": ls, "piid": lp, "value": value},
        ])
        for r in res or []:
            if r.get("code", 0) != 0:
                raise MiioError(_("Ventilátor odmítl nastavení {v}: kód {v2}").format(v=r.get('did'), v2=r.get('code')))

    def get_percent(self) -> tuple[bool, float]:
        from .vitr import range_to_pct

        rng = self._pct_range() or (1, 100)
        prof = self._profile()
        if prof[0] == "legacy":
            props = ["power", "speed"] if prof[1] == "p5" else ["power", "speed_level"]
            power, speed = (self.client.send("get_prop", props) or [False, 0])[:2]
            return power in (True, "on"), range_to_pct(speed, *rng)
        (ps, pp), (ls, lp) = prof[0], prof[1]
        res = self.client.send("get_properties", [
            {"did": "power", "siid": ps, "piid": pp},
            {"did": "level", "siid": ls, "piid": lp},
        ])
        v = {r.get("did"): r.get("value") for r in (res or []) if r.get("code", 0) == 0}
        return bool(v.get("power")), range_to_pct(v.get("level"), *rng)

    def apply_quiet(self) -> list[str]:
        """Nastaví pípání a podsvícení podle konfigurace.

        Vrací seznam vlastností, které ventilátor nepodporuje (jiný model).
        Síťové chyby propouští dál, aby se to zkusilo znovu.
        """
        c = self.cfg
        prof = self._profile()
        failed = []
        if prof[0] == "legacy":
            cmds = ([("buzzer", "s_sound", [not c.mute_buzzer]), ("light", "s_light", [not c.light_off])]
                    if prof[1] == "p5" else
                    [("buzzer", "set_buzzer", ["off" if c.mute_buzzer else "on"]),
                     ("light", "set_led_b", [2 if c.light_off else 0])])
            for did, method, params in cmds:
                try:
                    self.client.send(method, params)
                except MiioError as e:
                    if not _device_error(e):
                        raise
                    failed.append(did)
            return failed
        buzzer, light = prof[3], prof[4]
        props = []
        for did, ids, val in (("buzzer", buzzer, not c.mute_buzzer), ("light", light, not c.light_off)):
            if ids is None:
                failed.append(did)
            else:
                props.append({"did": did, "siid": ids[0], "piid": ids[1], "value": val})
        if props:
            res = self.client.send("set_properties", props)
            failed += [r.get("did") for r in (res or []) if r.get("code", 0) != 0]
        if failed:
            log.warning("Ventilátor nepodporuje: %s", failed)
        return failed


class SimulatedFan:
    def __init__(self, cfg: FanConfig):
        self.cfg = cfg
        self._power = False
        self._level = 1
        self._pct = 0.0

    def info(self) -> dict:
        return {"model": "simulace", "fw_ver": "-"}

    def get_state(self) -> tuple[bool, int]:
        return self._power, self._level

    def set_level(self, level: int) -> None:
        level = max(0, min(int(level), self.cfg.max_level))
        self._power = level > 0
        if level:
            self._level = level
        self._pct = 100.0 * level / max(1, self.cfg.max_level) if level else self._pct
        log.info("SIM ventilátor -> stupeň %s", level)

    # simulovaný ventilátor umí rychlost v % (jako novější Xiaomi)
    def supports_percent(self) -> bool:
        return True

    def set_percent(self, pct: float) -> None:
        from .vitr import pct_to_level

        self._power = pct > 0
        if pct > 0:
            self._pct = float(pct)
            self._level = pct_to_level(pct, self.cfg.max_level)
        log.info("SIM ventilátor -> %.0f %%", pct)

    def get_percent(self) -> tuple[bool, float]:
        return self._power, self._pct

    def apply_quiet(self) -> list[str]:
        log.info("SIM ventilátor: pípání %s, podsvícení %s",
                 "vyp" if self.cfg.mute_buzzer else "zap", "vyp" if self.cfg.light_off else "zap")
        return []


class FanWorker:
    """Vlákno, které asynchronně posílá požadovaný stupeň na ventilátor.

    - posílá jen změny (ventilátor při každém příkazu pípne),
    - každých 15 s si přečte skutečný stav a když ho někdo změnil
      ovladačem, vrátí ho na požadovanou hodnotu,
    - při chybě to zkouší znovu po 5 s.
    - Rychlost v % (plynulé řízení, vítr): ventilátor s rychlostí v %
      ji dostane přímo, ostatní nejbližší stupeň. Posílají se jen změny
      aspoň o 5 % (a zapnutí/vypnutí).
    """

    POLL_S = 15.0
    RETRY_S = 5.0
    PCT_STEP = 5.0

    def __init__(self, events: "queue.Queue"):
        self.events = events
        self._fan = None
        self._desired: int | None = None
        self._desired_pct: float | None = None
        self._sent: int | None = None
        self._sent_pct: float | None = None
        self._ref_pct: float | None = None   # co ventilátor hlásí po nastavení (zaokrouhlí si)
        self._corrected = False
        self._target_pct: float | None = None
        self.percent_capable: bool | None = None   # None = ještě nevíme
        self.actual_pct: float | None = None
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = False
        self._last_poll = 0.0
        self._last_error = -1e9   # time.monotonic() může začínat blízko 0
        self._quiet_pending = False
        self._thread = threading.Thread(target=self._run, name="fan", daemon=True)
        self._thread.start()

    def configure(self, fan) -> None:
        with self._lock:
            self._fan = fan
            self._sent = None
            self._sent_pct = None
            self.percent_capable = None
            self.actual_pct = None
            self._quiet_pending = fan is not None
        self._wake.set()

    def set_desired(self, level: int | None, pct: float | None = None) -> None:
        """Požadovaný stupeň; pct (0–100) = plynulá rychlost, má přednost u ventilátorů s %."""
        with self._lock:
            changed = level != self._desired or (pct is None) != (self._desired_pct is None)
            if pct is not None and self._desired_pct is not None:
                changed = changed or self._pct_changed(pct, self._desired_pct)
            self._desired = level
            self._desired_pct = None if pct is None else max(0.0, min(100.0, float(pct)))
        if changed:
            self._wake.set()

    def stop(self) -> None:
        self._stop = True
        self._wake.set()

    def _emit(self, ok: bool, text: str, actual: int | None = None):
        self.events.put(("fan", ok, text, actual))

    @classmethod
    def _pct_changed(cls, new: float, old: float | None) -> bool:
        if old is None:
            return True
        if (new > 0) != (old > 0):
            return True
        if new >= 100.0 > old or new < old and new <= 0:
            return True
        return abs(new - old) >= cls.PCT_STEP

    def _capable(self, fan) -> bool:
        if self.percent_capable is None:
            sp = getattr(fan, "supports_percent", None)
            self.percent_capable = bool(sp()) if callable(sp) else False
        return self.percent_capable

    def _run(self):
        while not self._stop:
            self._wake.wait(1.0)
            self._wake.clear()
            with self._lock:
                fan, desired, sent = self._fan, self._desired, self._sent
                dpct, spct = self._desired_pct, self._sent_pct
            if fan is None:
                continue
            now = time.monotonic()
            if now - self._last_error < self.RETRY_S:
                continue
            try:
                if self._quiet_pending:
                    failed = fan.apply_quiet()
                    self._quiet_pending = False
                    note = getattr(fan, "note", None)
                    if note and not failed:
                        self._emit(True, _("připojeno: {note}").format(note=note))
                    if failed:
                        self._emit(True, _("připojeno{v} (nepodporuje: ").format(v=': ' + note if note else '')
                                   + ", ".join(_("pípání") if f == "buzzer" else _("podsvícení") for f in failed) + ")")
                if desired is None:
                    continue
                if dpct is not None and self._capable(fan):
                    self._run_pct(fan, dpct, spct, now)
                    continue
                if desired != sent:
                    fan.set_level(desired)
                    with self._lock:
                        self._sent = desired
                        self._sent_pct = None
                    self._last_poll = now
                    self._emit(True, "nastaveno", desired)
                elif now - self._last_poll > self.POLL_S:
                    self._last_poll = now
                    power, level = fan.get_state()
                    actual = level if power else 0
                    if actual != desired:
                        log.info("Stav ventilátoru %s != požadovaný %s, opravuji", actual, desired)
                        with self._lock:
                            self._sent = None
                        self._wake.set()
                    self._emit(True, _("připojeno"), actual)
            except Exception as e:  # noqa: BLE001
                self._last_error = time.monotonic()
                self._quiet_pending = True  # po výpadku (třeba vytažení ze zásuvky) nastavit znovu
                with self._lock:
                    self._sent = None
                    self._sent_pct = None
                log.warning("Chyba ventilátoru: %s", e)
                self._emit(False, str(e))

    def _run_pct(self, fan, dpct: float, spct: float | None, now: float) -> None:
        from .vitr import pct_to_level

        n = max(1, getattr(getattr(fan, "cfg", None), "max_level", 3) or 3)
        if self._pct_changed(dpct, spct):
            fan.set_percent(dpct)
            with self._lock:
                self._sent_pct = dpct
                self._sent = None
            if self._target_pct is None or self._pct_changed(dpct, self._target_pct):
                self._ref_pct, self._corrected = dpct, False   # nová hodnota, ne oprava
            self._target_pct = dpct
            self.actual_pct = dpct
            self._last_poll = now
            self._emit(True, "nastaveno", pct_to_level(dpct, n))
        elif now - self._last_poll > self.POLL_S:
            self._last_poll = now
            on, pct = fan.get_percent()
            actual = pct if on else 0.0
            self.actual_pct = actual
            want_on = (spct or 0) > 0
            ref = self._ref_pct if self._ref_pct is not None else (spct or 0)
            if on != want_on or (want_on and abs(actual - ref) > self.PCT_STEP):
                if on == want_on and self._corrected:
                    # ventilátor si hodnotu zaokrouhluje (např. jen 3 rychlosti) – přijmout
                    self._ref_pct = actual
                else:
                    log.info("Rychlost ventilátoru %.0f %% != požadovaná %.0f %%, opravuji", actual, spct or 0)
                    self._corrected = True
                    with self._lock:
                        self._sent_pct = None
                    self._wake.set()
            self._emit(True, _("připojeno"), pct_to_level(actual, n))
