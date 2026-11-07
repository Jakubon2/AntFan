"""Překlady textů rozhraní.

Klíčem je český text, takže čeština ve zdrojácích funguje beze změn:
    _("Měřím · {n} {senzory}").format(n=n, senzory=plural_sensor(n))
Anglický slovník je v i18n_en.py. N_() jen označí text pro překlad
(konstanty na úrovni modulu); přeloží se až voláním _() v místě použití.

Jazyk: config `language` = "auto" | "cs" | "en". Auto = čeština, když je
systémový jazyk český, jinak angličtina. Proměnná prostředí ANTFAN_LANG
(cs/en) má přednost – hodí se pro testy.
"""
from __future__ import annotations

import locale
import os
import subprocess
import sys

LANGUAGES = ("auto", "cs", "en")
_lang = "cs"
_table: dict[str, str] = {}


def N_(text: str) -> str:
    return text


def _(text: str) -> str:
    if _lang == "cs":
        return text
    return _table.get(text, text)


def plural(n: int, one: str, few: str, many: str) -> str:
    """Český tvar podle čísla (1 / 2–4 / jinak); v angličtině jen 1 / jinak."""
    if _lang == "cs":
        return one if n == 1 else (few if 2 <= n <= 4 else many)
    return _(one) if n == 1 else _(many)


def current() -> str:
    return _lang


def system_language() -> str:
    """'cs' nebo 'en' podle jazyka systému."""
    code = ""
    try:
        if sys.platform == "win32":
            import ctypes
            import locale as _loc
            lcid = ctypes.windll.kernel32.GetUserDefaultUILanguage()
            code = _loc.windows_locale.get(lcid, "")
        elif sys.platform == "darwin":
            r = subprocess.run(["defaults", "read", "-g", "AppleLanguages"],
                               capture_output=True, text=True, timeout=2)
            for tok in r.stdout.replace("(", " ").replace(")", " ").replace(",", " ").split():
                tok = tok.strip().strip('"')
                if tok:
                    code = tok
                    break
    except Exception:  # noqa: BLE001
        code = ""
    if not code:
        try:
            code = locale.getlocale()[0] or ""
        except Exception:  # noqa: BLE001
            code = ""
        code = code or os.environ.get("LC_ALL") or os.environ.get("LANG") or ""
    code = code.lower()
    return "cs" if code.startswith(("cs", "czech")) else "en"


def resolve(setting: str | None) -> str:
    env = os.environ.get("ANTFAN_LANG", "").lower()
    if env in ("cs", "en"):
        return env
    if setting in ("cs", "en"):
        return setting
    return system_language()


def set_language(setting: str | None) -> str:
    """Nastaví jazyk (auto/cs/en); vrátí skutečně použitý ('cs' nebo 'en')."""
    global _lang, _table
    lang = resolve(setting)
    if lang == "en":
        from .i18n_en import EN
        _table = EN
    else:
        _table = {}
    _lang = lang
    return lang
