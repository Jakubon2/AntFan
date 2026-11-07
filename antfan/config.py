"""Uložení nastavení do config.json.

Windows: %APPDATA%\\AntFan, macOS: ~/Library/Application Support/AntFan,
jinde ~/.antfan.
"""
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
    elif sys.platform == "darwin":
        d = Path.home() / "Library" / "Application Support" / "AntFan"
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
    theme: str = "system"  # light | dark | system
    web_autostart: bool = False  # ovládání z mobilu zapnout hned po spuštění
    web_port: int = 8686
    web_key: str = ""  # tajná část adresy /m/<klíč>
    drink_enabled: bool = False  # připomínka pití
    drink_temp_c: float | None = 20.0  # teplota v místnosti; None = nepočítat
    drink_interval_min: float = 0.0  # 0 = automaticky
    overlay_enabled: bool = False  # lišta navrchu přes Rouvy
    overlay_size: str = "standard"  # mini | standard
    overlay_second: str = "hr_pct"  # hr_pct | zone | none
    overlay_alerts_only: bool = False
    overlay_x: int | None = None  # None = pravý horní roh
    overlay_y: int | None = None


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
