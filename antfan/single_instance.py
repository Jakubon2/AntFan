"""Zajistí, že běží jen jedna instance AntFan.

Dvě instance by se praly o ANT+ dongle a druhá by hlásila, že je dongle
připojen k jiné aplikaci. Na Windows se používá pojmenovaný mutex (uvolní se
i při pádu procesu), jinde zámek souboru.
"""
from __future__ import annotations

import os
import sys

from . import config as config_mod

MUTEX_NAME = "Local\\AntFan_single_instance_v1"
ERROR_ALREADY_EXISTS = 183


class SingleInstance:
    def __init__(self):
        self._handle = None
        self._fd = None
        self.pid_file = config_mod.app_dir() / "antfan.pid"

    def acquire(self) -> bool:
        if sys.platform == "win32":
            import ctypes
            from ctypes import wintypes

            k32 = ctypes.WinDLL("kernel32", use_last_error=True)
            k32.CreateMutexW.restype = wintypes.HANDLE
            k32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
            handle = k32.CreateMutexW(None, False, MUTEX_NAME)
            err = ctypes.get_last_error()
            if not handle:
                return True  # mutex nejde vytvořit – raději nebránit spuštění
            if err == ERROR_ALREADY_EXISTS:
                k32.CloseHandle(handle)
                return False
            self._handle = handle
        else:
            import fcntl

            fd = os.open(str(self.pid_file.with_suffix(".lock")), os.O_RDWR | os.O_CREAT, 0o644)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                os.close(fd)
                return False
            self._fd = fd
        try:
            self.pid_file.write_text(str(os.getpid()))
        except OSError:
            pass
        return True

    def other_pid(self) -> int | None:
        try:
            pid = int(self.pid_file.read_text().strip())
            return pid if pid != os.getpid() else None
        except (OSError, ValueError):
            return None
