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
from dataclasses import dataclass

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

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
            raise MiioError("Token musí být 32 hexadecimálních znaků") from e
        if len(self.token) != 16:
            raise MiioError("Token musí mít 32 hexadecimálních znaků (16 bajtů)")
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
            raise MiioError("Příliš krátká odpověď")
        magic, length, _unk, did, stamp = struct.unpack(">HHIII", data[:16])
        if magic != 0x2131:
            raise MiioError("Neplatná odpověď (magic)")
        body = data[32:length]
        if body:
            expected = _md5(data[:16] + self.token + body)
            if expected != data[16:32]:
                raise MiioError("Neplatný kontrolní součet – špatný token?")
        return did, stamp, body

    def _socket(self) -> socket.socket:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(self.timeout)
        return s

    def handshake(self) -> None:
        with self._socket() as s:
            try:
                s.sendto(HELLO, (self.ip, MIIO_PORT))
                data, _ = s.recvfrom(1024)
            except socket.timeout as e:
                raise MiioError(
                    f"Ventilátor na {self.ip} neodpovídá (zkontrolujte IP a Wi-Fi)"
                ) from e
            except OSError as e:
                raise MiioError(f"Síťová chyba: {e}") from e
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
                    data, _ = s.recvfrom(4096)
                    _did, stamp, body = self.parse_packet(data)
                    self._stamp = stamp
                    if not body:
                        continue
                    try:
                        text = self.decrypt(body)
                    except ValueError as e:
                        raise MiioError("Nelze dešifrovat odpověď – špatný token?") from e
                    text = text.rstrip(b"\x00")
                    resp = json.loads(text.decode("utf-8", errors="replace"))
                    if resp.get("id") != msg_id and time.monotonic() < deadline:
                        continue  # odpověď na starší dotaz
                    break
            except socket.timeout as e:
                self._did = None  # příště znovu handshake
                raise MiioError(
                    "Ventilátor neodpověděl na příkaz (špatný token nebo nedostupný)"
                ) from e
            except OSError as e:
                self._did = None
                raise MiioError(f"Síťová chyba: {e}") from e
        if "error" in resp:
            raise MiioError(f"Ventilátor vrátil chybu: {resp['error']}")
        return resp.get("result")


@dataclass
class FanConfig:
    ip: str = ""
    token: str = ""
    max_level: int = 3
    power_siid: int = 2
    power_piid: int = 1
    level_siid: int = 2
    level_piid: int = 2
    mute_buzzer: bool = True   # ventilátor jinak pípne při každém příkazu
    light_off: bool = True
    buzzer_siid: int = 2
    buzzer_piid: int = 11
    light_siid: int = 2
    light_piid: int = 12


class XiaomiFan:
    """Vysokoúrovňové ovládání: stupeň 0 = vypnuto, 1..max_level = rychlost."""

    def __init__(self, cfg: FanConfig):
        self.cfg = cfg
        self.client = MiioClient(cfg.ip, cfg.token)

    def info(self) -> dict:
        return self.client.send("miIO.info", []) or {}

    def get_state(self) -> tuple[bool, int]:
        c = self.cfg
        res = self.client.send(
            "get_properties",
            [
                {"did": "power", "siid": c.power_siid, "piid": c.power_piid},
                {"did": "level", "siid": c.level_siid, "piid": c.level_piid},
            ],
        )
        vals = {r.get("did"): r.get("value") for r in (res or []) if r.get("code", 0) == 0}
        return bool(vals.get("power")), int(vals.get("level") or 0)

    def set_level(self, level: int) -> None:
        c = self.cfg
        level = max(0, min(int(level), c.max_level))
        if level == 0:
            props = [{"did": "power", "siid": c.power_siid, "piid": c.power_piid, "value": False}]
        else:
            props = [
                {"did": "power", "siid": c.power_siid, "piid": c.power_piid, "value": True},
                {"did": "level", "siid": c.level_siid, "piid": c.level_piid, "value": level},
            ]
        res = self.client.send("set_properties", props)
        for r in res or []:
            if r.get("code", 0) != 0:
                raise MiioError(f"Ventilátor odmítl nastavení {r.get('did')}: kód {r.get('code')}")

    def apply_quiet(self) -> list[str]:
        """Nastaví pípání a podsvícení podle konfigurace.

        Vrací seznam vlastností, které ventilátor nepodporuje (jiný model).
        Síťové chyby propouští dál, aby se to zkusilo znovu.
        """
        c = self.cfg
        props = [
            {"did": "buzzer", "siid": c.buzzer_siid, "piid": c.buzzer_piid, "value": not c.mute_buzzer},
            {"did": "light", "siid": c.light_siid, "piid": c.light_piid, "value": not c.light_off},
        ]
        res = self.client.send("set_properties", props)
        failed = [r.get("did") for r in (res or []) if r.get("code", 0) != 0]
        if failed:
            log.warning("Ventilátor nepodporuje: %s (%s)", failed, res)
        return failed


class SimulatedFan:
    def __init__(self, cfg: FanConfig):
        self.cfg = cfg
        self._power = False
        self._level = 1

    def info(self) -> dict:
        return {"model": "simulace", "fw_ver": "-"}

    def get_state(self) -> tuple[bool, int]:
        return self._power, self._level

    def set_level(self, level: int) -> None:
        level = max(0, min(int(level), self.cfg.max_level))
        self._power = level > 0
        if level:
            self._level = level
        log.info("SIM ventilátor -> stupeň %s", level)

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
    """

    POLL_S = 15.0
    RETRY_S = 5.0

    def __init__(self, events: "queue.Queue"):
        self.events = events
        self._fan = None
        self._desired: int | None = None
        self._sent: int | None = None
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = False
        self._last_poll = 0.0
        self._last_error = 0.0
        self._quiet_pending = False
        self._thread = threading.Thread(target=self._run, name="fan", daemon=True)
        self._thread.start()

    def configure(self, fan) -> None:
        with self._lock:
            self._fan = fan
            self._sent = None
            self._quiet_pending = fan is not None
        self._wake.set()

    def set_desired(self, level: int | None) -> None:
        with self._lock:
            self._desired = level
        self._wake.set()

    def stop(self) -> None:
        self._stop = True
        self._wake.set()

    def _emit(self, ok: bool, text: str, actual: int | None = None):
        self.events.put(("fan", ok, text, actual))

    def _run(self):
        while not self._stop:
            self._wake.wait(1.0)
            self._wake.clear()
            with self._lock:
                fan, desired, sent = self._fan, self._desired, self._sent
            if fan is None:
                continue
            now = time.monotonic()
            if now - self._last_error < self.RETRY_S:
                continue
            try:
                if self._quiet_pending:
                    failed = fan.apply_quiet()
                    self._quiet_pending = False
                    if failed:
                        self._emit(True, "připojeno (tento model nepodporuje: "
                                   + ", ".join("pípání" if f == "buzzer" else "podsvícení" for f in failed) + ")")
                if desired is None:
                    continue
                if desired != sent:
                    fan.set_level(desired)
                    with self._lock:
                        self._sent = desired
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
                    self._emit(True, "připojeno", actual)
            except Exception as e:  # noqa: BLE001
                self._last_error = time.monotonic()
                self._quiet_pending = True  # po výpadku (třeba vytažení ze zásuvky) nastavit znovu
                with self._lock:
                    self._sent = None
                log.warning("Chyba ventilátoru: %s", e)
                self._emit(False, str(e))
