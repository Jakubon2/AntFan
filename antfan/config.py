"""Uložení nastavení do %APPDATA%\\AntFan\\config.json."""
from __future__ import annotations

import json
import logging
import os
import sys
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from .controller import ControlConfig
from .miio_fan import FanConfig

log = logging.getLogger("antfan.config")


def app_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home()))
        d = base / "AntFan"
    else:
        d = Path.home() / ".antfan"
    d.mkdir(parents=True, exist_ok=True)
    return d


@dataclass
class AppConfig:
    fan: FanConfig = field(default_factory=FanConfig)
    control: ControlConfig = field(default_factory=ControlConfig)
    selected: list[list[int]] = field(default_factory=list)  # [[id, typ, trans], ...]
    scan_duration_s: int = 15
    simulation: bool = False
    auto_mode: bool = True


def _merge(cls, data: dict):
    names = {f.name for f in fields(cls)}
    return cls(**{k: v for k, v in (data or {}).items() if k in names})


def load() -> AppConfig:
    path = app_dir() / "config.json"
    if not path.exists():
        return AppConfig()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        cfg = _merge(AppConfig, {k: v for k, v in raw.items() if k not in ("fan", "control")})
        cfg.fan = _merge(FanConfig, raw.get("fan"))
        cfg.control = _merge(ControlConfig, raw.get("control"))
        return cfg
    except Exception:  # noqa: BLE001
        log.exception("Nelze načíst konfiguraci, používám výchozí")
        return AppConfig()


def save(cfg: AppConfig) -> None:
    path = app_dir() / "config.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(asdict(cfg), indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)
