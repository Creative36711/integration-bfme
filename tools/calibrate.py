#!/usr/bin/env python3
"""
Калибратор координат И маркеров готовности.

Запускает игру в ОКОННОМ режиме (-win, временно понижая разрешение), после
чего по горячим клавишам:

    F8 — захватить МАРКЕР готовности (маленький кусочек экрана вокруг курсора,
         напр. треугольник-индикатор выпадающего списка). Сохраняется в
         config/menu_marker.npy + config/menu_marker.json. Нужен для детекта
         «экран загрузился» (bridge/visual_ready.py).
    F9 — снять КООРДИНАТУ курсора (доля окна) — выводится в консоль.
    F10 — выход.

Использование:
    1. Закрой игру.
    2. python tools\\calibrate.py (PowerShell ОТ АДМИНИСТРАТОРА).
    3. Дождись экрана, наведи курсор и жми нужную клавишу.

Требует numpy (pip install numpy).
"""

import json
import os
import sys
import time

# Make `bridge` / `tools` importable no matter how this script is launched.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bridge import config, elevate, launcher, navigate as nav
from bridge import options_ini
from tools import hotkey

ID_MARKER = 1
ID_CAPTURE = 2
ID_QUIT = 3

CAL_RESOLUTION = "1280 720"  # разрешение на время калибровки
RESTORE_AFTER = 5.0          # через сколько секунд после запуска вернуть прежнее

# Размер маркера в долях от меньшей стороны окна (квадрат).
MARKER_SIZE_FRAC = 0.03

MARKER_NPY = os.path.join(config.CONFIG_DIR, "menu_marker.npy")
MARKER_JSON = os.path.join(config.CONFIG_DIR, "menu_marker.json")


def capture_coord():
    """Снять координату курсора (доля окна) и вывести в консоль."""
    pos = nav.get_cursor_pos()
    hwnd, _ = nav.find_game_window()
    if not hwnd or not pos:
        print("[cal] окно/курсор недоступны")
        return
    l, t, r, b = nav.get_client_rect(hwnd)
    W, H = r - l, b - t
    fx = (pos[0] - l) / W
    fy = (pos[1] - t) / H
    print(f"[cal] frac=({fx:.4f}, {fy:.4f})   px=({pos[0]},{pos[1]})")


def capture_marker():
    """Захватить маркер готовности вокруг курсора (и сохранить позицию в долях)."""
    pos = nav.get_cursor_pos()
    hwnd, _ = nav.find_game_window()
    if not hwnd or not pos:
        print("[cal] окно/курсор недоступны")
        return
    l, t, r, b = nav.get_client_rect(hwnd)
    W, H = r - l, b - t
    fx = (pos[0] - l) / W
    fy = (pos[1] - t) / H
    box = max(8, int(min(W, H) * MARKER_SIZE_FRAC))

    # Отводим курсор в сторону, чтобы он не попал в кадр маркера.
    nav.move(l + 10, t + 10)
    time.sleep(0.3)

    arr = nav.capture_region(pos[0] - box // 2, pos[1] - box // 2, box, box)
    if arr is None:
        print("[cal] не удалось захватить область (нет numpy?)")
        return

    import numpy as np
    np.save(MARKER_NPY, arr)
    with open(MARKER_JSON, "w", encoding="utf-8") as f:
        json.dump({"fx": fx, "fy": fy, "size_frac": MARKER_SIZE_FRAC}, f,
                  indent=2)
    print(f"[cal] маркер сохранён: {MARKER_NPY} + {MARKER_JSON}")
    print(f"[cal]   позиция=({fx:.4f},{fy:.4f})  размер={box}px")


def main():
    elevate.ensure_admin()

    exe = launcher.discover_exe(config.load_config().get("exe_path"))
    if not exe:
        print("ERROR: игра не найдена (проверь config/config.json)", file=sys.stderr)
        return 1

    print(f"[cal] запускаю игру в оконном режиме: {exe.name}")

    # Перед запуском временно снижаем разрешение, чтобы окно поместилось
    # на экране; после запуска вернём прежнее (игра его уже не перечитает).
    old_res = options_ini.read_option("Resolution")
    if old_res:
        print(f"[cal] прежнее разрешение: {old_res} -> ставлю {CAL_RESOLUTION}")
        options_ini.set_option("Resolution", CAL_RESOLUTION)
    else:
        print("[cal] Resolution в Options.ini не найден — пропускаю смену")

    launcher.launch_game(exe, ["-win"])

    # Через несколько секунд возвращаем прежнее разрешение обратно.
    if old_res:
        time.sleep(RESTORE_AFTER)
        options_ini.set_option("Resolution", old_res)
        print(f"[cal] вернул разрешение {old_res}")

    print("[cal] жду окно игры...")
    deadline = time.monotonic() + 120
    hwnd = how = None
    while time.monotonic() < deadline:
        hwnd, how = nav.find_game_window()
        if hwnd:
            break
        time.sleep(0.5)
    if not hwnd:
        print("ERROR: окно игры не появилось", file=sys.stderr)
        return 1
    print(f"[cal] окно найдено ({how})")

    print("=" * 60)
    print("F8 — захватить маркер готовности (треугольник над кнопкой)")
    print("F9 — снять координату курсора")
    print("F10 — выход")
    print("=" * 60)

    hotkey.register(ID_MARKER, "F8")
    hotkey.register(ID_CAPTURE, "F9")
    hotkey.register(ID_QUIT, "F10")
    hotkey.run_loop({ID_MARKER: capture_marker, ID_CAPTURE: capture_coord,
                     ID_QUIT: hotkey.post_quit})
    return 0


if __name__ == "__main__":
    sys.exit(main())
