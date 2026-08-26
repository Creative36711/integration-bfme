#!/usr/bin/env python3
"""
BFME2: Rise of the Witch-king — locate and launch the game.

Standard library only. Windows only.

How RotWK actually starts
-------------------------
* lotrbfme2ep1.exe is a *launcher*. The real game binary is game.dat, which the
  launcher spawns in the same folder after copy-protection checks. On modern
  Windows the original SafeDisc-protected launcher frequently refuses to run;
  the community ships patched exes (official 2.01 patch / fan 2.02 patch) and
  also runs game.dat directly. Both are supported via discover_exe.
* Install path is discoverable in the registry (InstallPath / App Paths).
"""

import ctypes
import subprocess
import winreg
from ctypes import wintypes
from pathlib import Path

from bridge.log import log

EXE_NAME = "lotrbfme2ep1.exe"
GAME_PROCESS = "game.dat"  # the actual game binary (launcher spawns it)

# Registry locations where the install path may be recorded (most common first).
# value_name=None means "read the default value" (App Paths stores the full
# exe path as the default value).
_REGISTRY_PATHS = [
    (winreg.HKEY_LOCAL_MACHINE,
     r"SOFTWARE\Wow6432Node\Electronic Arts\Electronic Arts\The Lord of the Rings, The Rise of the Witch-king",
     "InstallPath"),
    (winreg.HKEY_LOCAL_MACHINE,
     r"SOFTWARE\Electronic Arts\Electronic Arts\The Lord of the Rings, The Rise of the Witch-king",
     "InstallPath"),
    (winreg.HKEY_LOCAL_MACHINE,
     r"SOFTWARE\Wow6432Node\Electronic Arts\The Lord of the Rings, The Rise of the Witch-king",
     "Install Dir"),
    (winreg.HKEY_CURRENT_USER,
     r"SOFTWARE\Electronic Arts\Electronic Arts\The Lord of the Rings, The Rise of the Witch-king",
     "InstallPath"),
    (winreg.HKEY_LOCAL_MACHINE,
     r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\lotrbfme2ep1.exe",
     None),
    (winreg.HKEY_LOCAL_MACHINE,
     r"SOFTWARE\Wow6432Node\Microsoft\Windows\CurrentVersion\App Paths\lotrbfme2ep1.exe",
     None),
]

# Likely install locations to fall back on if the registry is empty.
_DEFAULT_CANDIDATES = [
    r"C:\RotWK\lotrbfme2ep1.exe",   # the user's own layout
    r"C:\RotWK\game.dat",           # direct game binary fallback
    r"C:\Program Files (x86)\Electronic Arts\The Lord of the Rings, The Rise of the Witch-king\lotrbfme2ep1.exe",
    r"C:\Program Files\Electronic Arts\The Lord of the Rings, The Rise of the Witch-king\lotrbfme2ep1.exe",
    r"D:\Games\The Lord of the Rings, The Rise of the Witch-king\lotrbfme2ep1.exe",
]

shell32 = ctypes.windll.shell32
# ShellExecuteW(hwnd, lpOperation, lpFile, lpParameters, lpDirectory, nShowCmd)
# Returns a value > 32 on success; <= 32 is an error code.
shell32.ShellExecuteW.restype = ctypes.c_size_t


def _registry_value(_value_name):
    """Yield string values found in the registry for the install location."""
    for hive, key, val in _REGISTRY_PATHS:
        for flags in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
            try:
                with winreg.OpenKey(hive, key, 0, winreg.KEY_READ | flags) as k:
                    value, _ = winreg.QueryValueEx(k, val if val else None)
                    if isinstance(value, str) and value:
                        yield value
            except (FileNotFoundError, OSError):
                pass


def _value_to_exe_path(value):
    """Registry values are either a dir (-> join EXE_NAME) or a full exe path."""
    p = Path(value.strip().strip('"'))
    if p.suffix.lower() == ".exe":
        return p
    candidate = p / EXE_NAME
    return candidate if candidate.exists() else p / GAME_PROCESS


def discover_exe(explicit=None):
    """
    Return the best guess for the game executable path, or None.

    Priority: explicit path > registry > known candidate directories.
    """
    if explicit:
        p = Path(explicit).expanduser()
        return p if p.exists() else None

    for value in _registry_value("InstallPath"):
        p = _value_to_exe_path(value)
        if p and p.exists():
            return p

    for raw in _DEFAULT_CANDIDATES:
        p = Path(raw)
        if p.exists():
            return p

    return None


def launch_game(exe_path, args=None, elevate=False):
    """
    Launch the game (or launcher) with its own directory as cwd.

    Returns the Popen object on a normal launch, or None if it had to go
    through a UAC-elevated ShellExecute (in which case we have no handle and
    rely on process/window detection to confirm startup).

    `elevate=True` forces the UAC prompt; otherwise we try a normal launch
    first and fall back to elevation only if Windows answers ERROR_ELEVATION
    _REQUIRED (WinError 740) — e.g. the exe has "Run as administrator" set.
    """
    exe_path = Path(exe_path).expanduser()
    if not exe_path.exists():
        raise FileNotFoundError(f"Game executable not found: {exe_path}")
    cmd_args = list(args or [])
    log(f"[launch] {exe_path.name}  (cwd={exe_path.parent})  args={cmd_args}")

    if not elevate:
        try:
            return subprocess.Popen([str(exe_path)] + cmd_args,
                                    cwd=str(exe_path.parent))
        except OSError as e:
            if getattr(e, "winerror", None) != 740:  # ERROR_ELEVATION_REQUIRED
                raise
            log("[launch] exe requires elevation -> retrying via UAC (runas)")

    params = subprocess.list2cmdline(cmd_args) or None
    ret = shell32.ShellExecuteW(None, "runas", str(exe_path), params,
                                str(exe_path.parent), 1)  # SW_SHOWNORMAL
    if ret <= 32:
        raise OSError(f"ShellExecute 'runas' failed (code {ret}). "
                      f"User may have cancelled the UAC prompt.")
    log("[launch] started with elevation (no process handle; detecting "
          "startup via process/window scan)")
    return None
