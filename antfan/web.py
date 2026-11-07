"""Ovládání z mobilu přes domácí Wi-Fi.

Malý HTTP server ze standardní knihovny v daemon vlákně. Stránka i API leží
pod tajnou cestou /m/<klíč>; bez klíče server vrací 404.

  GET  /m/<klíč>             stránka pro mobil
  GET  /m/<klíč>/api/state   stav jako JSON
  POST /m/<klíč>/api/level   {"level": "auto" | 0..N}

Server nesahá na tkinter: stav čte ze snímku, který hlavní vlákno ukládá
přes publish(), a příkazy posílá do fronty událostí aplikace jako
("web_level", "auto" | int).
"""
from __future__ import annotations

import hmac
import json
import logging
import queue
import secrets
import socket
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import i18n
from .i18n import N_

log = logging.getLogger("antfan.web")

DEFAULT_PORT = 8686


def new_key() -> str:
    return secrets.token_urlsafe(16)


def lan_ip() -> str:
    """IP adresa počítače v místní síti. UDP connect nic neodesílá, jen vybere rozhraní."""
    for target in ("10.255.255.255", "192.168.255.255", "8.8.8.8"):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect((target, 1))
            ip = s.getsockname()[0]
            if ip and not ip.startswith("127.") and ip != "0.0.0.0":
                return ip
        except OSError:
            pass
        finally:
            s.close()
    return "127.0.0.1"


def page_url(ip: str, port: int, key: str) -> str:
    return f"http://{ip}:{port}/m/{key}"


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    # Na Windows by SO_REUSEADDR dovolil dvěma programům poslouchat na stejném portu.
    allow_reuse_address = sys.platform != "win32"


class WebServer:
    def __init__(self, events: "queue.Queue"):
        self.events = events
        self._lock = threading.Lock()
        self._state: dict = {}
        self._httpd: _Server | None = None
        self._thread: threading.Thread | None = None
        self.key = ""
        self.port = 0
        self.language = "auto"  # jazyk stránky: cs | en | auto (= podle Accept-Language)

    @property
    def running(self) -> bool:
        return self._httpd is not None

    def publish(self, state: dict) -> None:
        with self._lock:
            self._state = state

    def snapshot(self) -> dict:
        with self._lock:
            return dict(self._state)

    def start(self, port: int, key: str, host: str = "0.0.0.0") -> None:
        """Spustí server; při obsazeném portu vyhodí OSError."""
        self.stop()
        handler = type("Handler", (_Handler,), {"web": self})
        httpd = _Server((host, port), handler)
        self.key, self.port = key, httpd.server_address[1]
        self._httpd = httpd
        self._thread = threading.Thread(target=httpd.serve_forever, name="antfan-web",
                                        kwargs={"poll_interval": 0.5}, daemon=True)
        self._thread.start()
        log.info("Web pro mobil běží na portu %s", self.port)

    def stop(self) -> None:
        httpd, self._httpd = self._httpd, None
        if httpd is None:
            return
        try:
            httpd.shutdown()
            httpd.server_close()
        except Exception:  # noqa: BLE001
            log.exception("Zastavení webu")
        if self._thread is not None:
            self._thread.join(timeout=2)
        self._thread = None
        log.info("Web pro mobil zastaven")


class _Handler(BaseHTTPRequestHandler):
    web: WebServer
    server_version = "AntFan"
    sys_version = ""
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # výchozí píše na stderr, který v exe není
        log.debug("%s %s", self.address_string(), fmt % args)

    # --- pomocné
    def _route(self) -> str | None:
        """Vrátí zbytek cesty za /m/<klíč>, nebo None, když klíč nesedí."""
        path = self.path.split("?", 1)[0].split("#", 1)[0]
        parts = path.split("/", 3)  # ['', 'm', klíč, zbytek]
        key = self.web.key
        if len(parts) < 3 or parts[1] != "m" or not key:
            return None
        if not hmac.compare_digest(parts[2].encode(), key.encode()):
            return None
        return parts[3] if len(parts) > 3 else ""

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, code: int, obj) -> None:
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _not_found(self) -> None:
        self._send(404, b"Not found", "text/plain; charset=utf-8")

    # --- metody
    def do_GET(self):  # noqa: N802
        rest = self._route()
        if rest is None:
            return self._not_found()
        if rest == "":
            lang = page_language(self.web.language, self.headers.get("Accept-Language", ""))
            return self._send(200, render_page(lang).encode("utf-8"), "text/html; charset=utf-8")
        if rest == "api/state":
            return self._json(200, self.web.snapshot())
        return self._not_found()

    do_HEAD = do_GET

    def do_POST(self):  # noqa: N802
        rest = self._route()
        if rest != "api/level":
            # tělo dočíst, ať klient nečeká; a nic neprozradit
            self._drain()
            return self._not_found()
        body = self._drain()
        if body is None:
            return self._json(413, {"ok": False, "error": "příliš velký požadavek"})
        try:
            level = json.loads(body.decode("utf-8") or "{}").get("level")
        except (ValueError, AttributeError):
            return self._json(400, {"ok": False, "error": "neplatný JSON"})
        max_level = int(self.web.snapshot().get("max_level") or 0)
        if level != "auto":
            if isinstance(level, str) and level.isdigit():
                level = int(level)
            if isinstance(level, bool) or not isinstance(level, int) or not 0 <= level <= max_level:
                return self._json(400, {"ok": False, "error": f"stupeň musí být auto nebo 0–{max_level}"})
        self.web.events.put(("web_level", level))
        return self._json(200, {"ok": True, "level": level})

    def _drain(self) -> bytes | None:
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = 0
        if n > 4096:
            self.close_connection = True
            return None
        return self.rfile.read(n) if n > 0 else b""


def page_language(setting: str, accept: str) -> str:
    """cs/en: podle nastavení aplikace, při auto podle Accept-Language prohlížeče."""
    if setting in ("cs", "en"):
        return setting
    for part in (accept or "").split(","):
        tag = part.split(";", 1)[0].strip().lower()
        if tag and tag != "*":
            return "cs" if tag.startswith("cs") else "en"
    return i18n.current()


# texty stránky: (úsek v PAGE, český text uvnitř); v angličtině se text přeloží
PAGE_TEXTS = [
    ('lang="{}"', None),
    (">{}<", N_("Připojuji…")),
    (">{}<", N_("Výkon")),
    (">{}<", N_("Tep")),
    (">{}<", N_("Ventilátor")),
    (">{}<", N_("Obrazovku nechte rozsvícenou, jinak se obnovování zastaví.")),
    ('"{}"', N_("Vyp")),
    ('"{}"', N_("Výkon")),
    ('"{}"', N_("Příkaz se nepodařilo odeslat.")),
    ('"{}"', N_("Bez spojení s počítačem")),
]


def render_page(lang: str) -> str:
    if lang != "en":
        return PAGE
    from .i18n_en import EN
    page = PAGE
    for pattern, text in PAGE_TEXTS:
        if text is None:
            page = page.replace(pattern.format("cs"), pattern.format("en"))
        else:
            page = page.replace(pattern.format(text), pattern.format(EN.get(text, text)))
    return page


PAGE = r"""<!doctype html>
<html lang="cs">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="color-scheme" content="light dark">
<meta name="referrer" content="no-referrer">
<title>AntFan</title>
<style>
:root{--bg:#ffffff;--surface:#f6f5f2;--border:#e3e1db;--text:#1f1f1d;--muted:#6b6a65;--faint:#a3a19a;
--power:#D85A30;--hr:#D4537E;--fan:#185FA5;--accent:#185FA5;--accent-bg:#e6f1fb;--ok:#2f7d32;--bad:#c0392b}
@media (prefers-color-scheme: dark){:root{--bg:#1c1d20;--surface:#26272b;--border:#3a3b40;--text:#ecebe7;
--muted:#a3a29c;--faint:#6f6e69;--power:#EE7A50;--hr:#E8739B;--fan:#5E9FE3;--accent:#5E9FE3;--accent-bg:#1e3048;
--ok:#5cb860;--bad:#e8695a}}
*{box-sizing:border-box}
html,body{margin:0;background:var(--bg);color:var(--text);
font-family:-apple-system,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;-webkit-text-size-adjust:100%}
body{padding:max(12px,env(safe-area-inset-top)) 16px max(16px,env(safe-area-inset-bottom));
max-width:640px;margin:0 auto;display:flex;flex-direction:column;min-height:100vh;min-height:100dvh;gap:12px}
header{display:flex;align-items:center;justify-content:space-between;gap:12px}
h1{font-size:18px;margin:0;font-weight:600}
.st{display:flex;align-items:center;gap:8px;color:var(--muted);font-size:15px;text-align:right}
.dot{width:10px;height:10px;border-radius:50%;background:var(--faint);flex:none}
.grid{display:grid;grid-template-columns:1fr 1fr;border:1px solid var(--border);border-radius:12px;overflow:hidden}
.tile{padding:12px 14px 14px;min-width:0}
.tile+.tile{border-left:1px solid var(--border)}
.tile.wide{grid-column:1/-1;border-left:0;border-top:1px solid var(--border);display:flex;align-items:flex-end;gap:16px}
.lab{font-size:14px;color:var(--muted)}
.big{font-size:clamp(56px,23vw,128px);overflow:hidden;font-weight:600;line-height:1;font-variant-numeric:tabular-nums;
letter-spacing:-.02em;white-space:nowrap}
.unit{font-size:18px;color:var(--muted);font-weight:400;letter-spacing:0;margin-left:4px}
.sub{font-size:15px;color:var(--muted);margin-top:6px;min-height:1.2em}
.sub.bad{color:var(--bad)}
#p{color:var(--power)}#h{color:var(--hr)}#f{color:var(--fan)}
.bars{display:flex;align-items:flex-end;gap:5px;height:56px;margin-bottom:6px}
.bars i{display:block;width:16px;background:var(--border);border-radius:2px}
.bars i.on{background:var(--fan)}
.seg{display:flex;border:1px solid var(--border);border-radius:12px;overflow:hidden;background:var(--border);gap:1px}
.seg button{flex:1;min-width:0;min-height:84px;border:0;background:var(--bg);color:var(--text);font:inherit;
font-size:26px;font-weight:600;touch-action:manipulation;-webkit-tap-highlight-color:transparent;cursor:pointer}
.seg button.sel{background:var(--accent-bg);color:var(--accent)}
.seg button:active{background:var(--surface)}
.rx{display:flex;flex-wrap:wrap;gap:6px 16px;color:var(--muted);font-size:15px}
.rx .bad{color:var(--bad)}
.hint{color:var(--bad);font-size:15px}
.drink{display:none;padding:10px 14px;border-radius:12px;background:var(--accent-bg);color:var(--accent);
font-size:18px;cursor:pointer;-webkit-tap-highlight-color:transparent}
.drink.on{display:block}
.off{opacity:.45}
footer{margin-top:auto;color:var(--faint);font-size:13px}
</style>
</head>
<body>
<header><h1>AntFan</h1><div class="st"><span class="dot" id="dot"></span><span id="st">Připojuji…</span></div></header>
<main id="main" class="grid">
  <div class="tile"><div class="lab" id="pl">Výkon</div><div class="big" id="p">–</div><div class="sub" id="ps"></div></div>
  <div class="tile"><div class="lab">Tep</div><div class="big" id="h">–</div><div class="sub" id="hs"></div></div>
  <div class="tile wide"><div><div class="lab">Ventilátor</div><div class="big" id="f">–</div></div>
    <div class="bars" id="bars"></div><div class="sub" id="fs" style="flex:1;align-self:flex-end"></div></div>
</main>
<div class="drink" id="drink"></div>
<div class="seg" id="seg"></div>
<div class="rx" id="rx"></div>
<div class="hint" id="hint"></div>
<footer id="foot">Obrazovku nechte rozsvícenou, jinak se obnovování zastaví.</footer>
<script>
"use strict";
var base = location.pathname.replace(/\/+$/, "") + "/";
var $ = function (id) { return document.getElementById(id); };
var maxLevel = -1, sel = null, pending = null, lastOk = 0, drinkHidden = null;
var COL = {ok: "var(--ok)", bad: "var(--bad)", accent: "var(--accent)", faint: "var(--faint)"};

function txt(id, v) { var e = $(id); v = v == null ? "" : String(v); if (e.textContent !== v) e.textContent = v; }

function buildSeg(n) {
  var s = $("seg"); s.textContent = "";
  var opts = [["auto", "Auto"], [0, "Vyp"]];
  for (var i = 1; i <= n; i++) opts.push([i, String(i)]);
  opts.forEach(function (o) {
    var b = document.createElement("button");
    b.type = "button"; b.textContent = o[1]; b.dataset.k = String(o[0]);
    b.addEventListener("click", function () { setLevel(o[0]); });
    s.appendChild(b);
  });
  var bars = $("bars"); bars.textContent = "";
  for (var j = 1; j <= n; j++) {
    var x = document.createElement("i"); x.style.height = Math.round(56 * j / n) + "px"; bars.appendChild(x);
  }
  maxLevel = n;
}

function markSeg(k) {
  sel = String(k);
  Array.prototype.forEach.call($("seg").children, function (b) { b.classList.toggle("sel", b.dataset.k === sel); });
}

function render(s) {
  if (s.max_level !== maxLevel) buildSeg(s.max_level);
  txt("pl", s.power_label || "Výkon");
  txt("p", s.power == null ? "–" : s.power);
  txt("ps", s.power_sub); $("ps").classList.toggle("bad", !!s.power_bad);
  txt("h", s.hr == null ? "–" : s.hr);
  txt("hs", s.hr_sub);
  txt("f", s.level === 0 ? "Vyp" : s.level);
  txt("fs", s.reason);
  Array.prototype.forEach.call($("bars").children, function (b, i) { b.classList.toggle("on", i < s.level); });
  if (pending === null) markSeg(s.auto ? "auto" : s.manual);
  txt("st", s.status); $("dot").style.background = COL[s.status_color] || COL.faint;
  var rx = $("rx"); rx.textContent = "";
  (s.rx || []).forEach(function (r) {
    var e = document.createElement("span");
    e.textContent = r.name + "  " + (r.q == null ? "…" : r.q + " %");
    if (r.q != null && r.q < 80) e.className = "bad";
    rx.appendChild(e);
  });
  txt("hint", s.hint);
  var d = s.drink, de = $("drink");
  if (d) txt("drink", d.text);
  de.classList.toggle("on", !!d && d.id !== drinkHidden);
  de.dataset.id = d ? String(d.id) : "";
}

function setLevel(k) {
  pending = k; markSeg(k);
  fetch(base + "api/level", {method: "POST", headers: {"Content-Type": "application/json"},
                             body: JSON.stringify({level: k}), cache: "no-store"})
    .then(function (r) { if (!r.ok) throw new Error(r.status); })
    .catch(function () { txt("hint", "Příkaz se nepodařilo odeslat."); })
    .then(function () { setTimeout(function () { pending = null; }, 600); });
}

function poll() {
  var ctl = window.AbortController ? new AbortController() : null;
  var t = setTimeout(function () { if (ctl) ctl.abort(); }, 2500);
  fetch(base + "api/state", {cache: "no-store", signal: ctl ? ctl.signal : undefined})
    .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then(function (s) { lastOk = Date.now(); $("main").classList.remove("off"); render(s); })
    .catch(function () {
      if (Date.now() - lastOk > 3000) {
        $("main").classList.add("off"); txt("st", "Bez spojení s počítačem"); $("dot").style.background = COL.bad;
      }
    })
    .then(function () { clearTimeout(t); setTimeout(poll, 1000); });
}
$("drink").addEventListener("click", function () {
  drinkHidden = Number(this.dataset.id) || null; this.classList.remove("on");
});
poll();
</script>
</body>
</html>
"""
