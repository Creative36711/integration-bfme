#!/usr/bin/env python3
"""
Elevation helpers.

The game exe requires admin (WinError 740), so it runs elevated. Windows UIPI
(User Interface Privilege Isolation) blocks a NON-elevated process from
injecting input into an elevated window — clicks silently vanish. So the
automation script must run at the same (high) integrity level.

Two ways to satisfy this:
  * run PyCharm / your terminal "as administrator", OR
  * call ensure_admin() — it re-launches the current script elevated (a UAC
    prompt appears once, output then goes to a NEW console window).

APPDATA-СОХРАНЕНИЕ:
  При ShellExecuteW("runas") запускается НОВЫЙ процесс с правами админа.
  Переменные окружения текущего процесса НЕ наследуются. Чтобы дочерний
  процесс знал APPDATA реального пользователя, передаём его через скрытый
  аргумент --_real_appdata=<путь>. main.py затем восстанавливает его в
  os.environ["_REAL_APPDATA"].
"""

import ctypes
import os
import subprocess
import sys


def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def ensure_admin():
    """If not running elevated, re-launch this script elevated and exit.

    Передаёт _REAL_APPDATA через аргумент командной строки, чтобы
    повышенный процесс мог найти NetworkPref.ini в правильном профиле.
    """
    if is_admin():
        return
    script = os.path.abspath(sys.argv[0])

    # Собираем аргументы: оригинальные + _REAL_APPDATA
    extra_args = list(sys.argv[1:])
    real_appdata = os.environ.get("_REAL_APPDATA") or os.environ.get("APPDATA")
    if real_appdata:
        extra_args.append(f"--_real_appdata={real_appdata}")

    params = subprocess.list2cmdline([script] + extra_args)
    ret = ctypes.windll.shell32.ShellExecuteW(
        None, "runas", sys.executable, params, os.path.dirname(script), 1)
    if ret <= 32:
        raise SystemExit(f"Elevation failed (code {ret}). "
                         f"User may have cancelled the UAC prompt.")
    raise SystemExit(0)  # stop the non-elevated copy; the elevated one is running


def restore_real_appdata(argv=None):
    """Восстановить _REAL_APPDATA из аргументов (вызвать после argparse).

    Ищет --_real_appdata=<путь> в sys.argv, удаляет его из списка и
    устанавливает os.environ["_REAL_APPDATA"]. Безопасно вызывать, даже
    если аргумента нет.
    """
    args = argv if argv is not None else sys.argv
    to_remove = None
    for arg in args:
        if arg.startswith("--_real_appdata="):
            value = arg.split("=", 1)[1]
            if value:
                os.environ["_REAL_APPDATA"] = value
            to_remove = arg
            break
    if to_remove and to_remove in args:
        args.remove(to_remove)
