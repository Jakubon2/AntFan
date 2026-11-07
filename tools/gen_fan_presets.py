"""Přegeneruje antfan/fan_presets.py ze specifikací na miot-spec.org.

    python tools/gen_fan_presets.py
"""
import json
import pathlib
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from antfan.fan_presets import LEGACY  # noqa: E402
from antfan.fans import SPEC_BASE, extract_spec  # noqa: E402

BRANDS = ("dmaker.", "zhimi.", "xiaomi.", "leshow.", "viomi.", "dreame.", "mijia.", "smartmi.", "airdog.")


def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "AntFan"}), timeout=30) as r:
        return json.loads(r.read())


best = {}
for i in get(f"{SPEC_BASE}/instances?status=released")["instances"]:
    if ":device:fan:" in i["type"] and i["model"].startswith(BRANDS):
        if i["model"] not in best or i["version"] > best[i["model"]]["version"]:
            best[i["model"]] = i
rows = []
for m, i in sorted(best.items()):
    if m in LEGACY:
        continue
    prof = extract_spec(get(f"{SPEC_BASE}/instance?type={urllib.parse.quote(i['type'], safe=':')}"))
    if prof:
        rows.append(f'    "{m}": {prof!r},')
path = pathlib.Path(__file__).resolve().parents[1] / "antfan" / "fan_presets.py"
src = path.read_text(encoding="utf-8")
head, rest = src.split("PRESETS = {\n", 1)
tail = rest[rest.index("}\n"):]
path.write_text(head + "PRESETS = {\n" + "\n".join(rows) + "\n" + tail, encoding="utf-8")
print(f"{len(rows)} modelů")
