"""Získání IP adresy a tokenu zařízení z účtu Xiaomi přes QR kód.

Přihlášení probíhá naskenováním QR kódu v aplikaci Mi Home (nebo otevřením
odkazu v prohlížeči), takže heslo k účtu Xiaomi AntFan nikdy nevidí.
Z cloudu se jen jednou stáhne seznam zařízení; tokeny se nikam neposílají
a do logu se nezapisují.

Protokol podle projektu Xiaomi-cloud-tokens-extractor (Piotr Machowski, MIT),
přepsáno jen na standardní knihovnu.
"""
from __future__ import annotations

import base64
import hashlib
import http.cookiejar
import json
import logging
import os
import random
import socket
import time
import urllib.error
import urllib.parse
import urllib.request

log = logging.getLogger("antfan.cloud")

SERVERS = ["de", "cn", "us", "ru", "tw", "sg", "in", "i2"]


class CloudError(Exception):
    pass


def _rc4(key: bytes, data: bytes) -> bytes:
    s = list(range(256))
    j = 0
    for i in range(256):
        j = (j + s[i] + key[i % len(key)]) & 0xFF
        s[i], s[j] = s[j], s[i]
    i = j = 0
    out = bytearray()
    # Xiaomi zahazuje prvních 1024 bajtů proudu
    for n in range(1024 + len(data)):
        i = (i + 1) & 0xFF
        j = (j + s[i]) & 0xFF
        s[i], s[j] = s[j], s[i]
        if n >= 1024:
            out.append(data[n - 1024] ^ s[(s[i] + s[j]) & 0xFF])
    return bytes(out)


def _json(text: str):
    return json.loads(text.replace("&&&START&&&", ""))


class XiaomiCloud:
    def __init__(self):
        rnd = random.SystemRandom()
        self.agent = ("".join(chr(rnd.randint(97, 122)) for _ in range(18)) + "-"
                      + "".join(chr(rnd.randint(65, 69)) for _ in range(13))
                      + " APP/com.xiaomi.mihome APPV/10.5.201")
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
        self.user_id = self.ssecurity = self.service_token = None
        self.qr_png: bytes | None = None
        self.login_url: str | None = None
        self._lp_url: str | None = None
        self._timeout = 300.0

    def _get(self, url: str, params: dict | None = None, timeout: float = 15.0):
        if params:
            url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={"User-Agent": self.agent})
        return self.opener.open(req, timeout=timeout)

    # ------------------------------------------------------------ přihlášení
    def start_qr(self) -> None:
        """Krok 1: získá QR kód a odkaz pro přihlášení."""
        try:
            r = self._get("https://account.xiaomi.com/longPolling/loginUrl", {
                "_qrsize": "360", "qs": "%3Fsid%3Dxiaomiio%26_json%3Dtrue",
                "callback": "https://sts.api.io.mi.com/sts", "_hasLogo": "false",
                "sid": "xiaomiio", "serviceParam": "", "_locale": "en_GB",
                "_dc": str(int(time.time() * 1000))})
            data = _json(r.read().decode("utf-8"))
            self.login_url, self._lp_url = data["loginUrl"], data["lp"]
            self._timeout = float(data.get("timeout", 300))
            self.qr_png = self._get(data["qr"]).read()
        except (urllib.error.URLError, OSError, KeyError, ValueError) as e:
            raise CloudError(f"Nepodařilo se spojit s účtem Xiaomi ({e})") from e

    def wait_login(self, cancelled) -> None:
        """Krok 2: čeká, až uživatel QR kód naskenuje a přihlášení potvrdí."""
        start = time.time()
        data = None
        while data is None:
            if cancelled():
                raise CloudError("Zrušeno.")
            if time.time() - start > self._timeout:
                raise CloudError("Vypršel čas na naskenování QR kódu. Zkuste to znovu.")
            try:
                data = _json(self._get(self._lp_url, timeout=10).read().decode("utf-8"))
            except (socket.timeout, TimeoutError):
                continue
            except urllib.error.HTTPError:
                time.sleep(1)
                continue
            except (urllib.error.URLError, OSError) as e:
                if isinstance(getattr(e, "reason", None), (socket.timeout, TimeoutError)):
                    continue
                raise CloudError(f"Spojení s účtem Xiaomi spadlo ({e})") from e
        try:
            self.user_id, self.ssecurity = data["userId"], data["ssecurity"]
            self._get(data["location"]).read()
        except (KeyError, urllib.error.URLError, OSError) as e:
            raise CloudError(f"Přihlášení se nepodařilo dokončit ({e})") from e
        self.service_token = next((c.value for c in self.jar if c.name == "serviceToken"), None)
        if not self.service_token:
            raise CloudError("Účet Xiaomi nevrátil přihlašovací údaje.")

    # ------------------------------------------------------------ API
    def _signed_nonce(self, nonce: str) -> str:
        h = hashlib.sha256(base64.b64decode(self.ssecurity) + base64.b64decode(nonce))
        return base64.b64encode(h.digest()).decode()

    @staticmethod
    def _enc_signature(path: str, signed_nonce: str, params: dict) -> str:
        parts = ["POST", path] + [f"{k}={v}" for k, v in params.items()] + [signed_nonce]
        return base64.b64encode(hashlib.sha1("&".join(parts).encode()).digest()).decode()

    def _call(self, server: str, path: str, data: dict):
        url = "https://" + ("" if server == "cn" else server + ".") + "api.io.mi.com/app" + path
        millis = int(time.time() * 1000)
        nonce = base64.b64encode(os.urandom(8) + (millis // 60000).to_bytes(4, "big")).decode()
        sn = self._signed_nonce(nonce)
        key = base64.b64decode(sn)
        params = {"data": json.dumps(data)}
        params["rc4_hash__"] = self._enc_signature(path, sn, params)
        params = {k: base64.b64encode(_rc4(key, v.encode())).decode() for k, v in params.items()}
        params.update({"signature": self._enc_signature(path, sn, params),
                       "ssecurity": self.ssecurity, "_nonce": nonce})
        cookies = {"userId": str(self.user_id), "yetAnotherServiceToken": self.service_token,
                   "serviceToken": self.service_token, "locale": "en_GB", "timezone": "GMT+01:00",
                   "is_daylight": "1", "dst_offset": "3600000", "channel": "MI_APP_STORE"}
        req = urllib.request.Request(
            url + "?" + urllib.parse.urlencode(params), data=b"", method="POST",
            headers={"User-Agent": self.agent, "Accept-Encoding": "identity",
                     "Content-Type": "application/x-www-form-urlencoded",
                     "x-xiaomi-protocal-flag-cli": "PROTOCAL-HTTP2",
                     "MIOT-ENCRYPT-ALGORITHM": "ENCRYPT-RC4",
                     "Cookie": "; ".join(f"{k}={v}" for k, v in cookies.items())})
        try:
            with urllib.request.urlopen(req, timeout=15) as r:  # noqa: S310
                body = r.read()
        except (urllib.error.URLError, OSError) as e:
            log.info("Cloud %s %s: %s", server, path, e)
            return None
        try:
            return json.loads(_rc4(key, base64.b64decode(body)))
        except Exception:  # noqa: BLE001
            return None

    def devices(self, progress=None) -> list[dict]:
        """Všechna zařízení ze všech serverů: name, model, ip, token, server."""
        out, seen = [], set()
        for server in SERVERS:
            if progress:
                progress(f"Hledám zařízení na serveru {server}…")
            homes = []
            r = self._call(server, "/v2/homeroom/gethome",
                           {"fg": True, "fetch_share": True, "fetch_share_dev": True, "limit": 300, "app_ver": 7})
            for h in ((r or {}).get("result") or {}).get("homelist") or []:
                homes.append((h["id"], self.user_id))
            r = self._call(server, "/v2/user/get_device_cnt", {"fetch_own": True, "fetch_share": True})
            for h in (((r or {}).get("result") or {}).get("share") or {}).get("share_family") or []:
                homes.append((h["home_id"], h["home_owner"]))
            for home_id, owner in homes:
                r = self._call(server, "/v2/home/home_device_list",
                               {"home_owner": int(owner), "home_id": int(home_id), "limit": 200,
                                "get_split_device": True, "support_smart_home": True})
                for d in ((r or {}).get("result") or {}).get("device_info") or []:
                    if not d.get("token") or d.get("did") in seen:
                        continue
                    seen.add(d.get("did"))
                    out.append({"name": d.get("name", ""), "model": d.get("model", ""),
                                "ip": d.get("localip", ""), "token": d["token"], "server": server})
        log.info("Z účtu Xiaomi načteno %d zařízení", len(out))
        return out
