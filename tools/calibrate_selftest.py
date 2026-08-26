#!/usr/bin/env python3
"""
Офлайн-самопроверка калибратора и его упаковки.

Не требует ни Windows, ни игры, ни numpy: Win32-модули моста подменяются
заглушками, после чего прогоняется РЕАЛЬНЫЙ код tools/calibrate.py
(поиск окна -> F9 координата -> F8 маркер -> F10 выход), а также проверяются
пути конфигов в собранном exe, команда UAC-перезапуска и PyInstaller-spec.

Запуск:
    python tools/calibrate_selftest.py
"""

import importlib
import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

FAILURES = []


def check(name, cond, detail=""):
    status = "OK  " if cond else "FAIL"
    print(f"  [{status}] {name}" + (f"  ({detail})" if detail and not cond else ""))
    if not cond:
        FAILURES.append(name)


# ---------------------------------------------------------------------------
# Заглушки Win32-модулей
# ---------------------------------------------------------------------------
class FakePath:
    """Мини-замена pathlib.Path для discover_exe()."""

    def __init__(self, path):
        self._p = path
        self.name = os.path.basename(path)

    def __str__(self):
        return self._p


class FakeNav:
    HWND = 0x1234
    CLIENT = (100, 50, 1380, 770)      # -> W=1280, H=720
    CURSOR = (700, 400)                # -> fx=0.46875, fy=0.486111

    def __init__(self):
        self.moves = []
        self.captures = []
        self.visible = True

    def find_game_window(self, require_visible=True):
        if not self.visible:
            return None, None
        return self.HWND, "proc=game.dat"

    def get_cursor_pos(self):
        return self.CURSOR

    def get_client_rect(self, hwnd):
        return self.CLIENT

    def move(self, x, y):
        self.moves.append((x, y))

    def capture_region(self, x, y, w, h):
        self.captures.append((x, y, w, h))
        return [("fake-array", w, h)]


class FakeLauncher:
    def __init__(self, exe="C:\\RotWK\\lotrbfme2ep1.exe"):
        self.exe = exe
        self.launches = []

    def discover_exe(self, explicit=None):
        return FakePath(explicit or self.exe) if (explicit or self.exe) else None

    def launch_game(self, exe, args=None, elevate=False):
        self.launches.append((str(exe), list(args or [])))
        return None


class FakeOptionsIni:
    def __init__(self, current="1920 1080"):
        self.current = current
        self.calls = []

    def read_option(self, key, folder=None, filename=None):
        return self.current if key == "Resolution" else None

    def set_option(self, key, value, folder=None, filename=None):
        self.calls.append((key, value))
        self.current = value
        return "Options.ini"


class FakeHotkey:
    def __init__(self, press=(2, 1, 3)):
        self.press = press          # порядок нажатий: 2=F9, 1=F8, 3=F10
        self.registered = []
        self.quit_posted = 0

    def register(self, id_, key, modifiers=0):
        self.registered.append((id_, key))

    def post_quit(self):
        self.quit_posted += 1

    def run_loop(self, actions):
        for id_ in self.press:
            fn = actions.get(id_)
            if fn:
                fn()


class FakeNumpy:
    """Только то, что использует калибратор: np.save()."""

    def __init__(self):
        self.saved = []

    def save(self, path, arr):
        self.saved.append((path, arr))
        with open(path, "wb") as f:
            f.write(b"\x93NUMPY-FAKE")


def install_fakes(nav, launcher, options_ini, hotkey, numpy):
    """Подменить Windows-модули моста заглушками."""
    import bridge
    import tools

    bridge_mod = sys.modules.setdefault("bridge", bridge)
    tools_mod = sys.modules.setdefault("tools", tools)

    fake_netprefs = type("network_prefs", (), {
        "save_real_appdata": staticmethod(lambda: None),
        "_appdata": staticmethod(lambda: tempfile.gettempdir()),
    })
    fake_elevate = type("elevate", (), {
        "is_admin": staticmethod(lambda: True),
        "ensure_admin": staticmethod(lambda: None),
        "restore_real_appdata": staticmethod(lambda argv=None: None),
    })

    for name, mod in (("navigate", nav), ("launcher", launcher),
                      ("options_ini", options_ini),
                      ("network_prefs", fake_netprefs),
                      ("elevate", fake_elevate)):
        sys.modules[f"bridge.{name}"] = mod
        setattr(bridge_mod, name, mod)
    sys.modules["tools.hotkey"] = hotkey
    setattr(tools_mod, "hotkey", hotkey)
    sys.modules["numpy"] = numpy


# ---------------------------------------------------------------------------
# Тесты
# ---------------------------------------------------------------------------
def test_config_paths_frozen():
    print("\n[1] bridge/config.py — пути в исходниках и в собранном exe")
    import bridge.config as cfg
    importlib.reload(cfg)

    check("исходники: BASE_DIR = корень проекта",
          os.path.samefile(cfg.BASE_DIR, ROOT), cfg.BASE_DIR)
    check("исходники: CONFIG_DIR = <корень>/config",
          cfg.CONFIG_DIR == os.path.join(ROOT, "config"), cfg.CONFIG_DIR)
    check("исходники: BUNDLED_CONFIG_DIR = None",
          cfg.BUNDLED_CONFIG_DIR is None)

    tmp = tempfile.mkdtemp(prefix="calfrozen-")
    try:
        exe = os.path.join(tmp, "Calibrate.exe")
        bundle = os.path.join(tmp, "_MEIPASS")
        os.makedirs(os.path.join(bundle, "config"))
        with open(os.path.join(bundle, "config", "config.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"exe_path": "BUNDLED"}, f)

        sys.frozen = True
        sys._MEIPASS = bundle
        sys._real_executable = getattr(sys, "executable", None)
        sys.executable = exe
        try:
            importlib.reload(cfg)
            check("exe: BASE_DIR = папка exe", cfg.BASE_DIR == tmp, cfg.BASE_DIR)
            check("exe: CONFIG_DIR = <папка exe>/config",
                  cfg.CONFIG_DIR == os.path.join(tmp, "config"), cfg.CONFIG_DIR)
            check("exe: is_frozen() == True", cfg.is_frozen() is True)
            loaded = cfg.load_config()
            check("exe: config.json читается из копии внутри exe",
                  loaded.get("exe_path") == "BUNDLED", str(loaded))

            os.makedirs(os.path.join(tmp, "config"), exist_ok=True)
            with open(os.path.join(tmp, "config", "config.json"), "w",
                      encoding="utf-8") as f:
                json.dump({"exe_path": "USER"}, f)
            importlib.reload(cfg)
            check("exe: свой config.json рядом с exe важнее встроенного",
                  cfg.load_config().get("exe_path") == "USER")
        finally:
            del sys.frozen
            del sys._MEIPASS
            sys.executable = sys._real_executable
            del sys._real_executable
            importlib.reload(cfg)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_elevate_command():
    print("\n[2] bridge/elevate.py — команда UAC-перезапуска")
    from bridge import elevate

    saved_appdata = os.environ.get("APPDATA")
    saved_real = os.environ.get("_REAL_APPDATA")
    os.environ["APPDATA"] = "C:\\Users\\user\\AppData\\Roaming"
    exe, params = elevate.elevated_command(argv=["tools\\calibrate.py", "--attach"])
    check("исходники: запускается python.exe", exe == sys.executable, exe)
    first = params.split()[0].strip('"')
    check("исходники: скрипт передаётся первым аргументом",
          first == os.path.abspath("tools\\calibrate.py"), params)
    check("исходники: передан --_real_appdata",
          "--_real_appdata=C:\\Users\\user\\AppData\\Roaming" in params, params)
    check("исходники: аргументы пользователя сохранены", "--attach" in params, params)

    sys.frozen = True
    try:
        exe, params = elevate.elevated_command(argv=["C:\\dist\\Calibrate.exe"])
        check("exe: запускается сам exe", exe == sys.executable, exe)
        check("exe: путь к exe НЕ дублируется в аргументах",
              "Calibrate.exe" not in (params or ""), params)
        exe, params = elevate.elevated_command(argv=["C:\\dist\\Calibrate.exe"],
                                               extra=[])
        check("exe: без аргументов пользователя остаётся только --_real_appdata",
              (params or "").strip() ==
              "--_real_appdata=C:\\Users\\user\\AppData\\Roaming", repr(params))

        del os.environ["APPDATA"]
        os.environ.pop("_REAL_APPDATA", None)
        _exe, params = elevate.elevated_command(argv=["C:\\dist\\Calibrate.exe"],
                                                extra=[])
        check("exe: нет APPDATA -> params пустой (None)", params is None,
              repr(params))
    finally:
        if hasattr(sys, "frozen"):
            del sys.frozen
        for key, value in (("APPDATA", saved_appdata), ("_REAL_APPDATA", saved_real)):
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def test_calibrate_flow():
    print("\n[3] tools/calibrate.py — полный цикл F9 -> F8 -> F10")
    tmp = tempfile.mkdtemp(prefix="calflow-")
    try:
        import bridge.config as cfg
        cfg.BASE_DIR = tmp
        cfg.CONFIG_DIR = os.path.join(tmp, "config")
        cfg.CONFIG_FILE = os.path.join(cfg.CONFIG_DIR, "config.json")
        os.makedirs(cfg.CONFIG_DIR, exist_ok=True)
        with open(cfg.CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump({"exe_path": "C:\\RotWK\\lotrbfme2ep1.exe"}, f)

        nav = FakeNav()
        launcher = FakeLauncher()
        options_ini = FakeOptionsIni()
        hotkey = FakeHotkey()
        numpy = FakeNumpy()
        install_fakes(nav, launcher, options_ini, hotkey, numpy)

        cal = importlib.import_module("tools.calibrate")
        importlib.reload(cal)
        cal._require_windows = lambda: None    # самопроверка идёт не под Windows
        cal.RESTORE_AFTER = 0.0                # не спать 5 секунд

        code = cal.run(["--no-pause"])
        check("код возврата 0", code == 0, f"code={code}")
        check("горячие клавиши зарегистрированы (F8/F9/F10)",
            sorted(k for _i, k in hotkey.registered) == ["F10", "F8", "F9"],
            str(hotkey.registered))
        check("игра запущена с -win",
              launcher.launches == [("C:\\RotWK\\lotrbfme2ep1.exe", ["-win"])],
            str(launcher.launches))
        check("разрешение понижено и возвращено",
              options_ini.calls == [("Resolution", "1280 720"),
                                    ("Resolution", "1920 1080")],
            str(options_ini.calls))
        check("курсор отведён перед захватом маркера",
              nav.moves == [(110, 60)], str(nav.moves))

        size = int(720 * 0.03)          # 21 px
        check("область маркера = 21x21 вокруг курсора",
              nav.captures == [(700 - size // 2, 400 - size // 2, size, size)],
            str(nav.captures))

        coords = os.path.join(cfg.CONFIG_DIR, "calibrate_coords.txt")
        text = open(coords, encoding="utf-8").read() if os.path.exists(coords) else ""
        check("координата напечатана: frac=(0.4688, 0.4861)",
              "frac=(0.4688, 0.4861)" in text, text.strip())
        check("координата готова к вставке в menu_positions.json",
              "[0.4688, 0.4861]," in text, text.strip())

        marker_json = os.path.join(cfg.CONFIG_DIR, "menu_marker.json")
        check("menu_marker.json создан", os.path.exists(marker_json))
        meta = json.load(open(marker_json, encoding="utf-8")) \
            if os.path.exists(marker_json) else {}
        check("позиция маркера в долях окна",
              abs(meta.get("fx", 0) - 0.46875) < 1e-6 and
              abs(meta.get("fy", 0) - 350 / 720) < 1e-6, str(meta))
        check("size_frac = 0.03", meta.get("size_frac") == 0.03, str(meta))

        marker_npy = os.path.join(cfg.CONFIG_DIR, "menu_marker.npy")
        check("menu_marker.npy записан через numpy", os.path.exists(marker_npy)
              and numpy.saved and numpy.saved[0][0] == marker_npy)

        log = os.path.join(tmp, "calibrate_log.txt")
        log_text = open(log, encoding="utf-8").read() if os.path.exists(log) else ""
        check("лог-файл ведётся рядом с приложением", "F10" in log_text, log)
        check("в логе есть путь к папке данных", cfg.CONFIG_DIR in log_text)

        # --- второй прогон: --attach + --no-resolution --------------------
        print("\n[4] tools/calibrate.py — --attach --no-resolution")
        nav2, launcher2 = FakeNav(), FakeLauncher()
        options2, hotkey2, numpy2 = FakeOptionsIni(), FakeHotkey(press=(2, 3)), FakeNumpy()
        install_fakes(nav2, launcher2, options2, hotkey2, numpy2)
        importlib.reload(cal)
        cal._require_windows = lambda: None
        code = cal.run(["--attach", "--no-resolution", "--no-pause"])
        check("код возврата 0", code == 0, f"code={code}")
        check("игра НЕ запускалась", launcher2.launches == [], str(launcher2.launches))
        check("Options.ini не тронут", options2.calls == [], str(options2.calls))

        # --- третий прогон: игра не найдена --------------------------------
        print("\n[5] tools/calibrate.py — игра не найдена")
        with open(cfg.CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump({}, f)          # путь к игре не задан
        nav3, launcher3 = FakeNav(), FakeLauncher(exe=None)
        options3, hotkey3, numpy3 = FakeOptionsIni(), FakeHotkey(), FakeNumpy()
        install_fakes(nav3, launcher3, options3, hotkey3, numpy3)
        importlib.reload(cal)
        cal._require_windows = lambda: None
        code = cal.run(["--no-pause"])
        check("код возврата 1", code == 1, f"code={code}")
        log_text = open(log, encoding="utf-8").read()
        check("в логе подсказка про config.json",
              "игра не найдена" in log_text and "config.json" in log_text)

        # --- четвёртый прогон: --attach, но окна игры нет -----------------
        print("\n[5b] tools/calibrate.py — --attach, окно игры не найдено")
        nav4, launcher4 = FakeNav(), FakeLauncher()
        nav4.visible = False
        options4, hotkey4, numpy4 = FakeOptionsIni(), FakeHotkey(), FakeNumpy()
        install_fakes(nav4, launcher4, options4, hotkey4, numpy4)
        importlib.reload(cal)
        cal._require_windows = lambda: None
        code = cal.run(["--attach", "--wait", "0.2", "--no-pause"])
        check("код возврата 1", code == 1, f"code={code}")
        check("игра не запускалась", launcher4.launches == [], str(launcher4.launches))
        check("в логе понятная ошибка",
              "окно игры не найдено" in open(log, encoding="utf-8").read())

        # --- пятый прогон: запуск не под Windows --------------------------
        if os.name != "nt":
            print("\n[5c] tools/calibrate.py — запуск не под Windows")
            importlib.reload(cal)          # возвращаем настоящий _require_windows
            code = cal.run(["--no-pause"])
            check("код возврата 1 (а не 0)", code == 1, f"code={code}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_pyinstaller_spec():
    print("\n[6] packaging/calibrate.spec — исполняется и собирает exe")
    spec_path = os.path.join(ROOT, "packaging", "calibrate.spec")
    if not os.path.exists(spec_path):
        check("spec существует", False, spec_path)
        return

    calls = {}

    class _A:
        """Замена PyInstaller.Analysis: те же атрибуты-TOC, что использует spec."""

        def __init__(self, scripts, **kw):
            calls["analysis"] = kw
            calls["scripts"] = scripts
            self.scripts = [(os.path.basename(s), s, "PYSOURCE") for s in scripts]
            self.pure, self.binaries, self.datas = [], [], []

    def _PYZ(pure):
        return {"pyz": pure}

    def _EXE(pyz, scripts, binaries, datas, *a, **kw):
        calls["exe"] = kw
        return {"exe": kw}

    g = {"__file__": spec_path, "SPECPATH": os.path.dirname(spec_path),
         "Analysis": _A, "PYZ": _PYZ, "EXE": _EXE, "COLLECT": None,
         "BUNDLE": None, "Tree": None}
    src = open(spec_path, encoding="utf-8").read()
    exec(compile(src, spec_path, "exec"), g)

    exe = calls.get("exe", {})
    check("точка входа — tools/calibrate.py",
          calls.get("scripts") == [os.path.join(ROOT, "tools", "calibrate.py")],
          str(calls.get("scripts")))
    check("имя файла — calibrate", exe.get("name") == "calibrate", str(exe.get("name")))
    check("консоль включена (нужен вывод координат)", exe.get("console") is True)
    check("uac_admin=True (UAC при запуске exe)", exe.get("uac_admin") is True)
    check("однофайловый режим (runtime_tmpdir=None)", exe.get("runtime_tmpdir") is None)
    names = [os.path.basename(d[0]) for d in calls["analysis"].get("datas", [])]
    check("config.json и menu_positions.json вшиты в exe",
          "config.json" in names and "menu_positions.json" in names, str(names))
    hidden = calls["analysis"].get("hiddenimports", [])
    check("numpy в hiddenimports", "numpy" in hidden, str(hidden))
    check("модули моста в hiddenimports",
          "bridge.navigate" in hidden and "tools.hotkey" in hidden, str(hidden))


def test_batch_scripts():
    print("\n[7] bat-скрипты — структура (cmd.exe здесь недоступен, проверяем разбор)")
    scripts = [os.path.join(ROOT, "calibrate.bat"),
               os.path.join(ROOT, "build_calibrate_exe.bat")]
    for path in scripts:
        name = os.path.basename(path)
        if not os.path.exists(path):
            check(f"{name}: существует", False, path)
            continue
        raw = open(path, "rb").read().decode("utf-8")
        lines = raw.split("\r\n")

        check(f"{name}: окончания строк CRLF",
              raw.count("\n") == raw.count("\r\n"), "иначе goto/labels капризничают")
        check(f"{name}: начинается с @echo off", lines[0].strip() == "@echo off",
              lines[0])

        labels = {ln.strip().lstrip(":").split()[0].lower()
                  for ln in lines if ln.strip().startswith(":")}
        targets = []
        for ln in lines:
            s = ln.strip().lower()
            if s.startswith("rem"):
                continue
            for word in s.replace("(", " ").replace(")", " ").split():
                if word.startswith("goto:") or word.startswith("call:"):
                    targets.append(word.split(":", 1)[1])
        missing = [t for t in targets if t not in labels]
        check(f"{name}: все goto/call ведут на существующие метки",
              not missing, f"нет меток: {missing}")

        depth, bad = 0, []
        for n, ln in enumerate(lines, 1):
            s = ln.strip()
            low = s.lower()
            if not s or low.startswith("rem"):
                continue
            if low.startswith("echo"):
                # внутри блока скобки в echo обязаны быть экранированы ^( ^)
                if depth > 0:
                    body = s.replace("^(", "").replace("^)", "")
                    if body.count("(") != body.count(")"):
                        bad.append(f"{n}: несбалансированные скобки в echo")
                continue
            depth += s.count("(") - s.count(")")
            if depth < 0:
                bad.append(f"{n}: лишняя закрывающая скобка")
        check(f"{name}: блоки if/for сбалансированы", depth == 0 and not bad,
              f"depth={depth} {bad}")

    need = ["tools/calibrate.py", "packaging/calibrate.spec",
            "packaging/dist_readme.txt", "config/config.json",
            "config/menu_positions.json"]
    for rel in need:
        check(f"файл для сборки на месте: {rel}",
              os.path.exists(os.path.join(ROOT, *rel.split("/"))))


def main():
    print("=" * 64)
    print("Самопроверка калибратора (офлайн, без Windows/игры/numpy)")
    print("=" * 64)
    test_config_paths_frozen()
    test_elevate_command()
    test_calibrate_flow()
    test_pyinstaller_spec()
    test_batch_scripts()

    print("\n" + "=" * 64)
    if FAILURES:
        print(f"ПРОВАЛЕНО проверок: {len(FAILURES)}")
        for name in FAILURES:
            print(f"  - {name}")
        return 1
    print("Все проверки пройдены.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
