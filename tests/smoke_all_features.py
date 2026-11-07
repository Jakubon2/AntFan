import sys, json, os, tempfile, urllib.request
os.environ["ANTFAN_HOME"] = tempfile.mkdtemp(prefix="antfan-smoke-")
sys.path.insert(0, ".")
import tkinter as tk
from antfan import app as A, config, overlay
cfg = config.AppConfig(simulation=True)
cfg.overlay_enabled = True; cfg.web_autostart = True; cfg.web_port = 18686; cfg.web_key = "testkey"
cfg.drink_enabled = True; cfg.drink_interval_min = 0.3
c = cfg.control; c.source_mode = "wind"; c.lead_enabled = True
config.save(cfg)
root = tk.Tk(); a = A.App(root)
errs = []
def h(*e): errs.append(e); __import__("traceback").print_exception(*e)
root.report_callback_exception = h
def at(t, fn): root.after(int(t*1000), fn)
at(0.6, a.on_scan)
def select():
    class E: pass
    for iid in ("23456:120", "61234:17"):
        e = E(); e.y = a.tree.bbox(iid)[1] + 2; a.on_tree_click(e)
    a.settings.withdraw(); a.on_run_toggle()
at(7, select)
seen = {"reasons": set(), "alerts": set()}
def rep(tag):
    st = overlay.overlay_state(a)
    seen["reasons"].add(a.controller.reason.split(" ")[0]); [seen["alerts"].add(x.split(" ·")[0]) for x in st["alerts"]]
    try:
        js = json.loads(urllib.request.urlopen("http://127.0.0.1:18686/m/testkey/api/state", timeout=3).read())
        web = (js.get("level"), js.get("pct"), js.get("reason"), bool(js.get("drink")), js.get("hint","")[:40])
    except Exception as e: web = f"ERR {e}"
    print(tag, "| ctrl", a.controller.level, a.controller.pct, a.controller.reason, "| speed", a.controller.speed_now,
          "| overlay", st["level_text"], st["reason"], st["second"], st["alerts"], "| web", web, "| batt", a.battery, flush=True)
for s in (12, 20, 30, 40, 50): at(s, lambda s=s: rep(f"t={s}"))
def theme():
    a.theme_var.set("dark"); a.on_theme(); print("rebuild ok, overlay win:", bool(a.overlay.win) if hasattr(a.overlay, "win") else "?")
at(42, theme)
def stop(): a.on_run_toggle()
at(55, stop)
at(58, lambda: print("ride window:", [w.title() for w in root.winfo_children() if isinstance(w, tk.Toplevel)]))
at(60, a._on_close)
root.mainloop(); print("seen", seen); print("tk errors:", len(errs))
