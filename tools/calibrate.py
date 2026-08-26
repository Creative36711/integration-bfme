#!/usr/bin/env python3
"""
Калибратор координат И маркеров готовности.

Запускает игру в ОКОННОМ режиме (-win, временно понижая разрешение), после
чего по горячим клавишам:

    F8 — захватить МАРКЕР готовности (маленький кусочек экрана вокруг курсора,
         напр. треугольник-индикатор выпадающего списка). Сохраняется в
         config/menu_marker.npy + config/menu_marker.json. Нужен для детекта
         «экран загрузился» (bridge/visual_ready.py).
    F9 — снять КООРДИНАТУ курсора (доля окна) — выводится в консоль и
         дописывается в config/calibrate_coords.txt.
    F10 — выход.

КАК ЗАПУСТИТЬ (любой из трёх способов):
    1. Двойной клик по calibrate.bat в корне проекта — Python не нужен:
       bat сам найдёт Python, а если его нет — скачает портативный и поставит
       numpy. Это самый простой способ раздать инструмент другому человеку.
    2. python tools\\calibrate.py — из исходников (нужен Python 3 + numpy).
    3. dist\\Calibrate\\Calibrate.exe — собранный однофайловый exe
       (build_calibrate_exe.bat), Python на целевой машине не нужен вообще.

Полезные ключи:
    --exe "C:\\Games\\RotWK\\lotrbfme2ep1.exe"  — путь к игре вручную
    --attach            — не запускать игру, подключиться к уже открытой
    --no-resolution     — не трогать Resolution в Options.ini
    --resolution "1024 768" — своё разрешение на время калибровки
    --no-admin          — не запрашивать UAC (клики в игру не пройдут)
    --no-pause          — не ждать Enter перед выходом

Требует numpy (pip install numpy). Работает только под Windows.
"""

import argparse
import json
import os
import sys
import time
import traceback

# Make `bridge` / `tools` importable no matter how this script is launched.
# (В собранном exe PyInstaller сам разруливает импорты — путь не нужен.)
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if not getattr(sys, "frozen", False) and _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

ID_MARKER = 1
ID_CAPTURE = 2
ID_QUIT = 3

CAL_RESOLUTION = "1280 720"  # разрешение на время калибровки
RESTORE_AFTER = 5.0          # через сколько секунд после запуска вернуть прежнее
WINDOW_TIMEOUT = 120.0       # сколько ждать появления окна игры

# Размер маркера в долях от меньшей стороны окна (квадрат).
MARKER_SIZE_FRAC = 0.03

# Модули «моста» подключаются лениво (они Windows-only) — см. _load_bridge().
config = elevate = launcher = nav = options_ini = network_prefs = hotkey = None

MARKER_NPY = MARKER_JSON = COORDS_FILE = LOG_FILE = None
_LOG_READY = False


# ---------------------------------------------------------------------------
# Вывод: консоль + лог-файл рядом с приложением
# ---------------------------------------------------------------------------
def _say(msg=""):
    """Печать в консоль с одновременной записью в лог-файл."""
    print(msg)
    if not _LOG_READY:
        return
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"{msg}\n")
    except OSError:
        pass  # лог — не критично


def _start_log():
    """Завести лог-файл рядом с exe/проектом (для отчётов «не работает»)."""
    global LOG_FILE, _LOG_READY
    try:
        LOG_FILE = os.path.join(config.BASE_DIR, "calibrate_log.txt")
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"\n=== {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
        _LOG_READY = True
    except OSError:
        _LOG_READY = False


def _require_windows():
    if os.name != "nt":
        raise SystemExit("[cal] Калибровка работает только под Windows "
                         "(нужны Win32 API: окно игры, SendInput, BitBlt).")


def _load_bridge():
    """Подключить Windows-модули моста и посчитать пути к файлам данных."""
    global config, elevate, launcher, nav, options_ini, network_prefs, hotkey
    global MARKER_NPY, MARKER_JSON, COORDS_FILE

    from bridge import config as _config
    from bridge import elevate as _elevate
    from bridge import launcher as _launcher
    from bridge import navigate as _nav
    from bridge import network_prefs as _network_prefs
    from bridge import options_ini as _options_ini
    from tools import hotkey as _hotkey

    config, elevate, launcher = _config, _elevate, _launcher
    nav, options_ini, network_prefs, hotkey = (_nav, _options_ini,
                                               _network_prefs, _hotkey)

    config.ensure_config_dir()
    MARKER_NPY = os.path.join(config.CONFIG_DIR, "menu_marker.npy")
    MARKER_JSON = os.path.join(config.CONFIG_DIR, "menu_marker.json")
    COORDS_FILE = os.path.join(config.CONFIG_DIR, "calibrate_coords.txt")


def _require_numpy():
    """numpy нужен для захвата/сохранения маркера. Понятная ошибка, если нет."""
    try:
        import numpy  # noqa: F401
        return True
    except ImportError:
        _say("[cal] НЕ УСТАНОВЛЕН numpy — без него маркер (F8) сохранить нельзя.")
        _say("[cal]   Установи:  python -m pip install numpy")
        _say("[cal]   (calibrate.bat ставит numpy автоматически)")
        return False


# ---------------------------------------------------------------------------
# Действия по горячим клавишам
# ---------------------------------------------------------------------------
def _window_box():
    """(hwnd, left, top, W, H) клиентской области окна игры или None."""
    hwnd, _ = nav.find_game_window()
    pos = nav.get_cursor_pos()
    if not hwnd or not pos:
        _say("[cal] окно/курсор недоступны (игра закрыта?)")
        return None
    l, t, r, b = nav.get_client_rect(hwnd)
    return hwnd, l, t, r - l, b - t


def capture_coord():
    """Снять координату курсора (доля окна), вывести и дописать в файл."""
    box = _window_box()
    if not box:
        return
    _hwnd, l, t, W, H = box
    pos = nav.get_cursor_pos()
    fx = (pos[0] - l) / W
    fy = (pos[1] - t) / H
    line = f"[cal] frac=({fx:.4f}, {fy:.4f})   px=({pos[0]},{pos[1]})"
    _say(line)
    _say(f'[cal]   для menu_positions.json:  [{fx:.4f}, {fy:.4f}],')

    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    entry = (f"{stamp}  frac=({fx:.4f}, {fy:.4f})  px=({pos[0]},{pos[1]})"
             f"  ->  [{fx:.4f}, {fy:.4f}],\n")
    try:
        with open(COORDS_FILE, "a", encoding="utf-8") as f:
            f.write(entry)
    except OSError as e:
        _say(f"[cal] не удалось записать {COORDS_FILE}: {e}")


def capture_marker(marker_frac=MARKER_SIZE_FRAC):
    """Захватить маркер готовности вокруг курсора (и сохранить позицию в долях)."""
    box = _window_box()
    if not box:
        return
    _hwnd, l, t, W, H = box
    pos = nav.get_cursor_pos()
    fx = (pos[0] - l) / W
    fy = (pos[1] - t) / H
    size = max(8, int(min(W, H) * marker_frac))

    # Отводим курсор в сторону, чтобы он не попал в кадр маркера.
    nav.move(l + 10, t + 10)
    time.sleep(0.3)

    arr = nav.capture_region(pos[0] - size // 2, pos[1] - size // 2, size, size)
    if arr is None:
        _say("[cal] не удалось захватить область экрана")
        _require_numpy()
        return

    try:
        import numpy as np
        np.save(MARKER_NPY, arr)
    except ImportError:
        _require_numpy()
        return

    with open(MARKER_JSON, "w", encoding="utf-8") as f:
        json.dump({"fx": fx, "fy": fy, "size_frac": marker_frac}, f, indent=2)
    _say(f"[cal] маркер сохранён: {MARKER_NPY} + {MARKER_JSON}")
    _say(f"[cal]   позиция=({fx:.4f},{fy:.4f})  размер={size}px")


# ---------------------------------------------------------------------------
# Запуск игры и ожидание окна
# ---------------------------------------------------------------------------
def _wait_window(timeout=WINDOW_TIMEOUT):
    _say("[cal] жду окно игры...")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        hwnd, how = nav.find_game_window()
        if hwnd:
            _say(f"[cal] окно найдено ({how})")
            return hwnd
        time.sleep(0.5)
    return None


def _launch_game(args):
    """Найти exe, временно снизить разрешение, запустить в окне. True = окно есть."""
    exe = launcher.discover_exe(args.exe or config.load_config().get("exe_path"))
    if not exe:
        _say("ОШИБКА: игра не найдена.")
        _say(f"  Проверь путь в {config.CONFIG_FILE}")
        _say('  (формат: {"exe_path": "C:\\\\RotWK\\\\lotrbfme2ep1.exe"})')
        _say("  Или запусти с ключом:  --exe \"путь\\к\\lotrbfme2ep1.exe\"")
        return False

    _say(f"[cal] запускаю игру в оконном режиме: {exe.name}")

    # Перед запуском временно снижаем разрешение, чтобы окно поместилось
    # на экране; после запуска вернём прежнее (игра его уже не перечитает).
    old_res = None
    if not args.no_resolution:
        old_res = options_ini.read_option("Resolution")
        if old_res:
            _say(f"[cal] прежнее разрешение: {old_res} -> ставлю {args.resolution}")
            options_ini.set_option("Resolution", args.resolution)
        else:
            _say("[cal] Resolution в Options.ini не найден — пропускаю смену")

    launcher.launch_game(exe, ["-win"])

    if old_res:
        time.sleep(RESTORE_AFTER)
        options_ini.set_option("Resolution", old_res)
        _say(f"[cal] вернул разрешение {old_res}")

    return _wait_window(args.wait) is not None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def parse_args(argv=None):
    ap = argparse.ArgumentParser(
        prog="calibrate",
        description="Калибровка координат меню (F9) и маркера готовности (F8) "
                    "для BFME2: RotWK. F10 — выход.")
    ap.add_argument("--exe", help="путь к lotrbfme2ep1.exe / game.dat "
                                  "(иначе берётся из config/config.json)")
    ap.add_argument("--attach", action="store_true",
                    help="не запускать игру — подключиться к уже открытому окну")
    ap.add_argument("--resolution", default=CAL_RESOLUTION,
                    help=f'разрешение на время калибровки (по умолчанию "{CAL_RESOLUTION}")')
    ap.add_argument("--no-resolution", action="store_true",
                    help="не менять Resolution в Options.ini")
    ap.add_argument("--wait", type=float, default=WINDOW_TIMEOUT,
                    help=f"сколько секунд ждать окно игры (по умолчанию {WINDOW_TIMEOUT:.0f})")
    ap.add_argument("--marker-size", type=float, default=MARKER_SIZE_FRAC,
                    help="сторона маркера в долях окна (по умолчанию "
                         f"{MARKER_SIZE_FRAC})")
    ap.add_argument("--no-admin", action="store_true",
                    help="не запрашивать права администратора (инъекция ввода "
                         "в повышенное окно игры при этом не сработает)")
    ap.add_argument("--no-pause", action="store_true",
                    help="не ждать Enter перед закрытием окна")
    return ap.parse_args(argv)


def _pause(enabled=True):
    if not enabled:
        return
    try:
        input("\nНажми Enter для выхода...")
    except (EOFError, KeyboardInterrupt, OSError):
        pass


def main(argv=None):
    args = parse_args(argv)

    _require_windows()
    _load_bridge()
    _start_log()

    _say("[cal] калибровка BFME2: RotWK")
    _say(f"[cal] версия Python: {sys.version.split()[0]}  "
         f"(exe: {bool(getattr(sys, 'frozen', False))})")
    _say(f"[cal] папка данных: {config.CONFIG_DIR}")

    # APPDATA реального пользователя: до UAC-повышения сохраняем, после —
    # восстанавливаем (иначе Options.ini правится в профиле администратора).
    elevate.restore_real_appdata()
    network_prefs.save_real_appdata()

    if args.no_admin:
        _say("[cal] --no-admin: права администратора НЕ запрашиваются")
    else:
        elevate.ensure_admin()

    if not args.attach:
        if not _launch_game(args):
            return 1
    else:
        _say("[cal] --attach: игру не запускаю, ищу уже открытое окно")
        if not _wait_window(args.wait):
            _say("ОШИБКА: окно игры не найдено (запусти игру или увеличь --wait)")
            return 1

    _require_numpy()

    _say("=" * 60)
    _say("F8  — захватить маркер готовности (треугольник над кнопкой)")
    _say("F9  — снять координату курсора")
    _say("F10 — выход")
    _say("=" * 60)

    hotkey.register(ID_MARKER, "F8")
    hotkey.register(ID_CAPTURE, "F9")
    hotkey.register(ID_QUIT, "F10")
    hotkey.run_loop({
        ID_MARKER: lambda: capture_marker(args.marker_size),
        ID_CAPTURE: capture_coord,
        ID_QUIT: hotkey.post_quit,
    })
    _say(f"[cal] координаты сохранены в {COORDS_FILE}")
    return 0


def run(argv=None):
    """Точка входа: ловит ошибки, пишет лог и держит консоль открытой."""
    args = parse_args(argv)
    code = 1
    try:
        code = main(argv) or 0
    except SystemExit as e:
        # elevate.ensure_admin() завершает процесс кодом 0 (копия с UAC уже
        # работает); SystemExit("текст") — это ошибка, её надо показать.
        if isinstance(e.code, int):
            code = e.code
        elif e.code:
            _say(str(e.code))
            code = 1
        else:
            code = 0
    except KeyboardInterrupt:
        _say("[cal] прервано пользователем")
    except Exception:
        _say("ОШИБКА калибровки:")
        _say(traceback.format_exc())
    _pause(not args.no_pause)
    return code


if __name__ == "__main__":
    sys.exit(run())
