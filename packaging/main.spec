# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller-spec однофайлового приложения моста: dist/Main.exe

Сборка (Windows, один раз):
    build_main_exe.bat
или вручную:
    python -m PyInstaller packaging\\main.spec --noconfirm

Особенности:
  * console=True        — интерактивный опрос в консоли;
  * uac_admin=True      — манифест requireAdministrator: Windows сама
                          показывает UAC, перезапуск процесса не нужен;
  * config/*.json вшиваются в exe как «заводские» значения, а рабочие файлы
    (config.json, coordinates.txt, _coordinates.txt) ищутся РЯДОМ с exe
    (см. bridge/config.py: при sys.frozen BASE_DIR = папка exe);
  * numpy включается принудительно (для bridge/visual_ready.py и capture_region).
"""

import os

ROOT = os.path.abspath(os.path.join(SPECPATH, os.pardir))
ENTRY = os.path.join(ROOT, "main.py")
CONFIG_DIR = os.path.join(ROOT, "config")

# «Заводские» конфиги внутрь exe (читаются, если рядом с exe своих нет).
datas = []
for _name in ("config.json", "menu_positions.json"):
    _path = os.path.join(CONFIG_DIR, _name)
    if os.path.exists(_path):
        datas.append((_path, "config"))

hiddenimports = [
    "numpy",
    "bridge",
    "bridge.config",
    "bridge.elevate",
    "bridge.fortresses",
    "bridge.input_lock",
    "bridge.launcher",
    "bridge.log",
    "bridge.maps",
    "bridge.menu",
    "bridge.navigate",
    "bridge.network_prefs",
    "bridge.options_ini",
    "bridge.room",
    "bridge.spawn",
    "bridge.timings",
    "bridge.visual_ready",
    "tools.hotkey",
    "tools.big_make",
    "tools.big_edit",
]

a = Analysis(
    [ENTRY],
    pathex=[ROOT],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "PyQt5", "PySide2", "pytest"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="Main",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,          # однофайловый режим
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    uac_admin=True,
)
