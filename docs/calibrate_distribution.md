# Калибратор для любого пользователя (bat / exe)

`tools/calibrate.py` — обычный Python-скрипт: на чужой машине без Python и
numpy он не запустится. Здесь — три способа раздать его кому угодно.

| Способ | Файл | Python на целевой машине | Интернет на целевой машине | Что отдаём |
|---|---|---|---|---|
| 1. BAT (проще всего) | `calibrate.bat` | не нужен | нужен один раз (скачает портативный Python, ~11 МБ) | архив с проектом |
| 2. EXE (надёжнее) | `dist\Calibrate\Calibrate.exe` | не нужен | не нужен | папку `dist\Calibrate\` или `dist\Calibrate.zip` |
| 3. Из исходников | `python tools\calibrate.py` | нужен 3.8+ и numpy | не нужен | репозиторий |

---

## 1. `calibrate.bat` — двойной клик, Python не нужен

Положи пользователю архив с проектом (достаточно: `calibrate.bat`,
`tools\`, `bridge\`, `config\`, `main.py`). Он делает двойной клик — дальше bat сам:

1. запрашивает права администратора через UAC (без них UIPI молча выбрасывает
   клики в окно игры);
2. ищет Python: `.runtime\python\python.exe` → `py -3` → `python`;
3. если ничего нет — качает **портативный** Python
   (`python-3.12.10-embed-amd64.zip` с python.org, запасной вариант 3.11.9)
   в `.runtime\python\`, включает в нём `import site`, ставит pip и numpy;
4. ставит numpy, если Python был свой, а numpy нет;
5. запускает `tools\calibrate.py` и держит консоль открытой.

Портативный Python скачивается **один раз** и остаётся в `.runtime\` — дальше
утилита работает офлайн. Ключи скрипта проходят насквозь:
`calibrate.bat --attach`, `calibrate.bat --exe "D:\Games\RotWK\lotrbfme2ep1.exe"`.

Если скачать Python не удалось (нет интернета), bat печатает понятную
подсказку вместо «python не является внутренней командой».

---

## 2. `dist\Calibrate\Calibrate.exe` — настоящий exe

Собирается один раз **на Windows** (нужны Python 3.8+ и интернет только для
сборки):

```bat
build_calibrate_exe.bat
```

Скрипт создаёт `.build\venv`, ставит `pyinstaller` + `numpy`, собирает
`packaging\calibrate.spec`, складывает результат в `dist\Calibrate\` и пакует
`dist\Calibrate.zip`:

```
dist\Calibrate\
├── Calibrate.exe          ~15-25 МБ, весь Python и numpy внутри
├── README.txt             инструкция для пользователя
└── config\
    ├── config.json        путь к игре (пользователь может поправить)
    └── menu_positions.json
```

Отдаём `Calibrate.zip`. Распаковал, двойной клик, «Да» в UAC — работает.

Как это устроено (важно при доработке):

* `console=True` — координаты F9 видно в консоли;
* `uac_admin=True` — в exe вшит манифест `requireAdministrator`, поэтому UAC
  показывается один раз при запуске и процесс **не перезапускается**
  (иначе вывод уехал бы в новое окно — см. `bridge/elevate.py`);
* `config/*.json` вшиты в exe как «заводские» значения, а читаются/пишутся
  файлы **рядом с exe**: при `sys.frozen` `bridge/config.py` считает
  `BASE_DIR` от `sys.executable`, а `resolve()` подменяет отсутствующий файл
  копией изнутри exe. Без этого однофайловый exe писал бы маркеры во
  временную папку `_MEIPASS`, которая удаляется при выходе;
* `numpy` указан в `hiddenimports` — в рантайме он импортируется внутри
  функции `bridge/navigate.py::capture_region`, анализатор мог бы его
  пропустить.

Проверка spec без Windows и PyInstaller:

```bat
python tools\calibrate_selftest.py
```

---

## 3. Ключи `tools\calibrate.py`

```
--exe "путь"             путь к игре (иначе config/config.json и реестр)
--attach                 не запускать игру — подключиться к уже открытой
--resolution "1024 768"  разрешение на время калибровки (по умолчанию "1280 720")
--no-resolution          не трогать Options.ini
--wait 180               сколько секунд ждать окно игры (по умолчанию 120)
--marker-size 0.05       сторона маркера в долях окна (по умолчанию 0.03)
--no-admin               не запрашивать UAC (клики в игру не пройдут)
--no-pause               не ждать Enter перед выходом
```

Что появляется после работы (всё рядом с exe/проектом):

* `config\menu_marker.npy` + `config\menu_marker.json` — маркер;
* `config\calibrate_coords.txt` — все снятые координаты и готовые строки
  `[0.3019, 0.9244],` для вставки в `menu_positions.json`;
* `calibrate_log.txt` — лог запуска (первое, что просить у пользователя).

---

## Самопроверка

`tools/calibrate_selftest.py` прогоняет реальный код калибратора без Windows,
игры и numpy (Win32-модули подменяются заглушками): поиск окна → F9 →
F8 → F10, плюс пути конфигов в собранном exe, команда UAC-перезапуска и
`packaging/calibrate.spec`.

```bat
python tools\calibrate_selftest.py
```

---

## Частые вопросы

**Антивирус удаляет exe.** Однофайловые сборки PyInstaller иногда помечаются
ложно. Лечится исключением на папку, пересборкой у себя или запуском
`calibrate.bat` из исходников.

**«игра не найдена».** Впиши путь в `config\config.json`
(`{"exe_path": "D:\\Games\\RotWK\\lotrbfme2ep1.exe"}`) или запусти с `--exe`.

**F8/F9 не срабатывают.** Клавиши заняты другим софтом (оверлеи, драйверы
клавиатуры) — закрой его.

**В консоли «кракозябры».** Bat сам ставит `chcp 65001` и `PYTHONUTF8=1`;
при запуске из своего терминала сделай то же самое.
