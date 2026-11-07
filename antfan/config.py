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


DEFAULT_PROFILE = "Výchozí"


@dataclass
class AppConfig:
    fan: FanConfig = field(default_factory=FanConfig)
    # profily jezdců / druhů tréninku, každý s vlastním řízením
    profiles: dict[str, ControlConfig] = field(default_factory=lambda: {DEFAULT_PROFILE: ControlConfig()})
    active_profile: str = DEFAULT_PROFILE
    selected: list[list[int]] = field(default_factory=list)  # [[id, typ, trans], ...]
    scan_duration_s: int = 15
    simulation: bool = False
    auto_mode: bool = True
    theme: str = "system"  # light | dark | system

    @property
    def control(self) -> ControlConfig:
        """Řízení aktivního profilu (zbytek programu pracuje jen s ním)."""
        if not self.profiles:
            self.profiles[DEFAULT_PROFILE] = ControlConfig()
        if self.active_profile not in self.profiles:
            self.active_profile = next(iter(self.profiles))
        return self.profiles[self.active_profile]

    @control.setter
    def control(self, value: ControlConfig) -> None:
        self.control  # noqa: B018 – zajistí platný aktivní profil
        self.profiles[self.active_profile] = value


def _merge(cls, data: dict):
    names = {f.name for f in fields(cls)}
    return cls(**{k: v for k, v in (data or {}).items() if k in names})


def load() -> AppConfig:
    path = app_dir() / "config.json"
    if not path.exists():
        return AppConfig()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        cfg = _merge(AppConfig, {k: v for k, v in raw.items() if k not in ("fan", "control", "profiles")})
        cfg.fan = _merge(FanConfig, raw.get("fan"))
        profiles = raw.get("profiles")
        if isinstance(profiles, dict) and profiles:
            cfg.profiles = {str(k): _merge(ControlConfig, v) for k, v in profiles.items()}
        else:  # starší config bez profilů: "control" => profil Výchozí
            cfg.profiles = {DEFAULT_PROFILE: _merge(ControlConfig, raw.get("control"))}
            cfg.active_profile = DEFAULT_PROFILE
        cfg.control  # noqa: B018 – opraví neplatný active_profile
        return cfg
    except Exception:  # noqa: BLE001
        log.exception("Nelze načíst konfiguraci, používám výchozí")
        return AppConfig()


def save(cfg: AppConfig) -> None:
    path = app_dir() / "config.json"
    tmp = path.with_suffix(".tmp")
    data = asdict(cfg)
    data["control"] = asdict(cfg.control)  # pro starší verze programu
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)
