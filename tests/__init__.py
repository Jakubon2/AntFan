"""Jazyk testů: ANTFAN_LANG=cs (výchozí) nebo en. Celá sada běží v daném jazyce.

Moduly, které porovnávají konkrétní české hlášky, si češtinu vynutí přes
czech_module() (logika se tím netestuje jinak, jen texty).
"""
import os

from antfan import i18n

os.environ.setdefault("ANTFAN_LANG", "cs")
i18n.set_language(None)


def czech_module():
    """(setUpModule, tearDownModule) pro modul s českými texty v asercích."""
    saved = {}

    def setup():
        saved["env"] = os.environ.get("ANTFAN_LANG")
        os.environ["ANTFAN_LANG"] = "cs"
        i18n.set_language("cs")

    def teardown():
        if saved.get("env") is None:
            os.environ.pop("ANTFAN_LANG", None)
        else:
            os.environ["ANTFAN_LANG"] = saved["env"]
        i18n.set_language(None)

    return setup, teardown
