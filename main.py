#!/usr/bin/env python3
"""
BFME2: RotWK integration — AUTO FLOW (entry point).

Интерактивно спрашивает настройки боя, запускает игру, проходит меню до
комнаты создания игры и выставляет уровень сложности ботам.

Flow:
    ask setup (фракция, число игроков 2–8, сложность ботов)
    -> записать NetworkPref.ini (фракция + авто-цвет игрока)
    -> запуск игры (полный экран) -> окно -> главное меню
    -> «Сеть» -> «Лок. сеть» -> «Создать игру» -> комната
    -> выставить сложность слотам ботов (2..N)

Задержки — в bridge/timings.py. Координаты слотов — bridge/room.py,
кнопок меню — config/menu_positions.json.
"""

import argparse
import os
import sys
import time

# Make `bridge` importable no matter how this script is launched.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bridge import config
from bridge import elevate
from bridge import fortresses
from bridge import input_lock
from bridge import launcher
from bridge.log import log, start as log_start
from bridge import menu
from bridge import navigate as nav
from bridge import network_prefs
from bridge import room
from bridge import spawn
from bridge import timings
from bridge import visual_ready

T = timings.TIMINGS

# Ключ фракции -> отображаемое имя (для интерактивного опроса).
FACTION_CHOICES = [
    ("men",      "Люди"),
    ("elves",    "Эльфы"),
    ("dwarves",  "Гномы"),
    ("isengard", "Изенгард"),
    ("mordor",   "Мордор"),
    ("goblins",  "Гоблины"),
    ("angmar",   "Ангмар"),
]

DIFFICULTY_NAMES = room.DIFFICULTY_NAMES


def wait_for_window(timeout, poll=0.5):
    """Wait for the REAL game window (game.dat), not the launcher's hidden one."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        hwnd, how = nav.find_game_window()
        if hwnd:
            return hwnd, how
        time.sleep(poll)
    return None, None


def ask_faction(prompt="За какую фракцию играем?"):
    log(prompt)
    for i, (_key, name) in enumerate(FACTION_CHOICES, 1):
        log(f"  {i}. {name}")
    while True:
        s = input("> ").strip().lower()
        if s.isdigit() and 1 <= int(s) <= len(FACTION_CHOICES):
            return FACTION_CHOICES[int(s) - 1][0]
        for key, name in FACTION_CHOICES:
            if s in (key, name.lower()):
                return key
        log("  Введите номер или название фракции.")


def ask_total_players():
    while True:
        s = input("Сколько игроков всего (2–8)? > ").strip()
        if s.isdigit() and 2 <= int(s) <= 8:
            return int(s)
        log("  Введите число от 2 до 8.")


def ask_difficulty():
    log("Уровень сложности ботов:")
    for i, name in enumerate(DIFFICULTY_NAMES, 1):
        log(f"  {i}. {name}")
    while True:
        s = input("> ").strip()
        if s.isdigit() and 1 <= int(s) <= len(DIFFICULTY_NAMES):
            return int(s) - 1  # 0-based индекс
        log("  Введите номер уровня сложности.")


def ask_bot_factions(total_players):
    """Фракции ботов (слоты 2..total_players). Возвращает dict {slot: faction_key}."""
    factions = {}
    for slot in range(2, total_players + 1):
        factions[slot] = ask_faction(f"Фракция слота {slot} (бота):")
    return factions


def ask_battle_type():
    """Крепость или обычная локация."""
    log("Битва в крепости или на обычной локации?")
    log("  1. Крепость")
    log("  2. Обычная локация")
    while True:
        s = input("> ").strip().lower()
        if s in ("1", "крепость", "в крепости"):
            return "fortress"
        if s in ("2", "обычная", "обычная локация"):
            return "normal"
        log("  Введите 1 (крепость) или 2 (обычная).")


def ask_fortress():
    """Какая крепость."""
    log("В какой крепости будет битва?")
    keys = list(fortresses.FORTRESSES.keys())
    for i, k in enumerate(keys, 1):
        log(f"  {i}. {fortresses.FORTRESSES[k]['name']}")
    while True:
        s = input("> ").strip().lower()
        if s.isdigit() and 1 <= int(s) <= len(keys):
            return keys[int(s) - 1]
        for k in keys:
            if s == k or s == fortresses.FORTRESSES[k]['name'].lower():
                return k
        log("  Введите номер или название крепости.")


def ask_fortress_slot(total_players):
    """Какой слот обороняет крепость (1..total_players)."""
    while True:
        s = input(f"Какой слот обороняет крепость (1–{total_players})? > ").strip()
        if s.isdigit() and 1 <= int(s) <= total_players:
            return int(s)
        log(f"  Введите число от 1 до {total_players}.")


def ask_army(faction):
    """Состав стартовой армии игрока: список отрядов, каждый со своим уровнем
    и апгрейдами. Возвращает [{"unit":..., "level":N, "upgrades":[...]}].

    Выбор поотрядный: можно добавить несколько ОДИНАКОВЫХ отрядов с разными
    уровнями/апгрейдами (мечники 2 ур. без грейдов и мечники 5 ур. со всеми).
    """
    roster = spawn.roster(faction)
    fname = room.FACTION_NAMES.get(faction, faction)
    log(f"Состав стартовой армии ({fname}). Доступные отряды:")
    for i, (unit, label, cap, upg) in enumerate(roster, 1):
        mark = ", героич." if cap > 5 else ""
        log(f"  {i:2d}. {label} (ур. до {cap}{mark})")

    squads = []
    while True:
        s = input("Добавить отряд: номер из списка, 0 = закончить > ").strip()
        if s in ("0", ""):
            break
        if not (s.isdigit() and 1 <= int(s) <= len(roster)):
            log(f"  Введите номер 1..{len(roster)} или 0.")
            continue
        unit, label, cap, avail_upg = roster[int(s) - 1]

        # уровень
        while True:
            s2 = input(f"    Уровень «{label}» (1-{cap})? > ").strip()
            if s2.isdigit() and 1 <= int(s2) <= cap:
                level = int(s2)
                break
            log(f"    Введите число от 1 до {cap}.")

        # апгрейды
        chosen = []
        if avail_upg:
            log(f"    Апгрейды «{label}» (номера через запятую, 0 = без):")
            for i, a in enumerate(avail_upg, 1):
                log(f"      {i}. {spawn._short(a)}")
            while True:
                s3 = input("    > ").strip()
                if s3 in ("0", ""):
                    break
                parts = [p.strip() for p in s3.split(",") if p.strip()]
                if all(p.isdigit() and 1 <= int(p) <= len(avail_upg) for p in parts):
                    chosen = [avail_upg[int(p) - 1] for p in parts]
                    break
                log(f"    Введите номера 1..{len(avail_upg)} через запятую, или 0.")
        else:
            log("    (у этого отряда нет апгрейдов)")

        squads.append({"unit": unit, "level": level, "upgrades": chosen})
        log(f"    + добавлено: {label}, ур.{level}"
            + (f" [{', '.join(spawn._short(a) for a in chosen)}]" if chosen else ""))
    return squads


def ask_heroes(faction):
    """Выбор героев игрока. Возвращает (heroes, ring_heroes).

    heroes = [{"hero": имя, "level": N}, ...]  (уровни 1..10)
    ring_heroes = [имя, ...]  (без уровня/апгрейдов)
    """
    fname = room.FACTION_NAMES.get(faction, faction)
    heroes = []
    ring = []

    # Обычные герои фракции.
    hlist = spawn.heroes_for(faction)
    if hlist:
        log(f"Герои фракции ({fname}) — номера через запятую, 'r' = случайно, 0 = без:")
        for i, h in enumerate(hlist, 1):
            log(f"  {i}. {h}")
        while True:
            s = input("> ").strip()
            if s in ("r", "random", "случайно"):
                heroes = spawn.random_heroes(faction)
                ring = spawn.random_ring_hero(faction)
                return heroes, ring
            if s in ("0", ""):
                break
            parts = [p.strip() for p in s.split(",") if p.strip()]
            if parts and all(p.isdigit() and 1 <= int(p) <= len(hlist) for p in parts):
                for p in parts:
                    hname = hlist[int(p) - 1]
                    while True:
                        lv = input(f"    Уровень героя {hname} (1-10)? > ").strip()
                        if lv.isdigit() and 1 <= int(lv) <= 10:
                            heroes.append({"hero": hname, "level": int(lv)})
                            break
                        log("    Введите число от 1 до 10.")
                break
            log(f"    Введите номера 1..{len(hlist)}, 'r' или 0.")
    else:
        log(f"У фракции {fname} нет героев.")

    # Кольцевой герой — по стороне фракции.
    alignment = spawn.faction_alignment(faction)
    if alignment:
        rh = spawn.RING_HEROES[alignment][0]
        side = "добро" if alignment == "good" else "зло"
        log(f"Кольцевой герой ({side}): {rh}")
        s = input("Выбрать кольцевого героя? (1 = да, 0 = нет) > ").strip()
        if s == "1":
            ring.append(rh)

    return heroes, ring


def _ask_handicap_value(prompt):
    """Одно значение форы: 0 = без, либо -5..-95 кратное 5."""
    while True:
        s = input(f"{prompt} > ").strip()
        if s in ("", "0"):
            return 0
        s2 = s.replace("%", "").replace(" ", "")
        try:
            v = int(s2)
        except ValueError:
            log("  Введите 0 или -5..-95 (кратное 5).")
            continue
        if -95 <= v <= -5 and v % 5 == 0:
            return v
        log("  Введите 0 или -5..-95 (кратное 5).")


def ask_handicaps(total_players):
    """Фора по слотам 1..total_players. Возвращает {slot: percent} (только ненулевые)."""
    log("Фора (0 = без, шаг -5%, до -95%). Ставится на игрока и ботов:")
    handicaps = {}
    # слот 1 = игрок
    v = _ask_handicap_value("  Игрок (слот 1)")
    if v:
        handicaps[1] = v
    for slot in range(2, total_players + 1):
        v = _ask_handicap_value(f"  Бот (слот {slot})")
        if v:
            handicaps[slot] = v
    return handicaps


def main(argv=None):
    ap = argparse.ArgumentParser(description="launch game and auto-configure a battle")
    ap.add_argument("--exe", help="explicit game/launcher path")
    ap.add_argument("--arg", action="append", dest="args",
                    help="extra launch arg (repeatable)")
    ap.add_argument("--elevated", action="store_true",
                    help="launch through UAC prompt")
    ap.add_argument("--stop-at", choices=["lan", "create"], default="create",
                    help="lan = stop after entering LAN; create = also click Create Game")
    ap.add_argument("--lock-input", dest="lock_input", action="store_true", default=None,
                    help="block the user's physical keyboard/mouse during "
                         "navigation (ON by default via config.json)")
    ap.add_argument("--no-lock-input", dest="lock_input", action="store_false",
                    help="disable input blocking")
    args = ap.parse_args(argv)

    log_start()  # отсчёт времени сценария — с этого момента

    # Восстановить APPDATA реального пользователя, если передан через
    # --_real_appdata (elevate.ensure_admin() передаёт при UAC-повышении).
    elevate.restore_real_appdata()

    cfg = config.load_config()
    lock_input = args.lock_input if args.lock_input is not None \
        else cfg.get("lock_input", True)

    # Сохранить APPDATA текущего пользователя ДО повышения привилегий.
    # После elevate %APPDATA% может указывать на профиль администратора,
    # а не на профиль пользователя, из-под которого запускается игра.
    network_prefs.save_real_appdata()

    # The game runs elevated -> the script must too, or injected input is
    # silently blocked (UIPI). Re-launches itself via UAC if needed.
    elevate.ensure_admin()

    # Интерактивный опрос ДО блокировки ввода (пользователь должен печатать).
    difficulty = ask_difficulty()
    total_players = ask_total_players()
    faction = ask_faction()
    bot_factions = ask_bot_factions(total_players)
    battle_type = ask_battle_type()
    fortress_key = fortress_slot = None
    if battle_type == "fortress":
        fortress_key = ask_fortress()
        fortress_slot = ask_fortress_slot(total_players)
    army = ask_army(faction)
    if not army:
        army = spawn.random_squads(faction)
        log("[setup] войска не выбраны — случайный состав:")
        for sq in army:
            log(f"  {sq['unit']} ур.{sq['level']}"
                + (f" [{', '.join(spawn._short(a) for a in sq['upgrades'])}]"
                   if sq['upgrades'] else ""))
    heroes, ring_heroes = ask_heroes(faction)
    handicaps = ask_handicaps(total_players)
    color_name = network_prefs.FACTION_COLORS.get(faction)
    log(f"[setup] фракция={faction}  цвет={color_name}  игроков={total_players}  "
          f"сложность ботов={DIFFICULTY_NAMES[difficulty]}")
    for slot in sorted(bot_factions):
        log(f"[setup]   слот {slot}: {room.FACTION_NAMES.get(bot_factions[slot])}")
    if fortress_key:
        log(f"[setup] крепость={fortresses.FORTRESSES[fortress_key]['name']} "
              f"(слот {fortress_slot} обороняет)")
    for sq in army:
        u = sq["unit"]
        s = f"[setup] отряд: {u} ур.{sq['level']}"
        if sq["upgrades"]:
            s += " [" + ", ".join(spawn._short(a) for a in sq["upgrades"]) + "]"
        log(s)
    for h in heroes:
        log(f"[setup] герой: {h['hero']} ур.{h['level']}")
    for r in ring_heroes:
        log(f"[setup] кольцевой герой: {r}")
    for slot in sorted(handicaps):
        log(f"[setup] фора слота {slot}: {handicaps[slot]}%")

    # Lock the user's physical input for the ENTIRE run — from here until the
    # very end. Ctrl+Alt+Del still works (emergency exit).
    locked = False
    if lock_input:
        locked = input_lock.lock()
        if locked:
            log("[lock] user input blocked (for the whole run)")
        else:
            log("[lock] WARNING: lock() returned False — input NOT blocked")
    else:
        log("[lock] input lock DISABLED")

    try:
        # 0. prepare network settings BEFORE launch — the game reads
        #    NetworkPref.ini on startup (rules + player faction + color).
        settings = network_prefs.settings_for_faction(cfg.get("network_rules"), faction)
        if settings:
            network_prefs.apply_settings(settings)

        # 0b. сгенерировать спавн-патч стартовой армии (до запуска).
        spawn_path = cfg.get("spawn_big", r"C:\RotWK\wotr_generated_presets.big")
        # factions_by_slot: слот 0 = игрок, слоты 2..N = боты.
        factions_by_slot = {0: faction, **bot_factions}
        if army or heroes or ring_heroes or bot_factions:
            ok, info = spawn.generate_spawn_big(
                spawn_path, factions_by_slot, army,
                player_heroes=heroes, ring_heroes=ring_heroes)
            if ok:
                log(f"[spawn] спавн-патч создан: {spawn_path}")
            else:
                log(f"[spawn] ОШИБКА генерации: {info}", file=sys.stderr)
                return 1
        else:
            log("[spawn] армия пустая — спавн-патч не создаётся")

        # 1. find & launch
        exe = launcher.discover_exe(args.exe or cfg.get("exe_path"))
        if not exe:
            log("ERROR: game not found — use --exe or config/config.json", file=sys.stderr)
            return 1
        log(f"[found] {exe}")

        launch_args = args.args if args.args is not None else cfg.get("args", [])
        try:
            launcher.launch_game(exe, launch_args, elevate=args.elevated
                                 or cfg.get("elevated", False))
        except (OSError, FileNotFoundError) as e:
            log(f"ERROR: launch failed: {e}", file=sys.stderr)
            return 1

        # 2. wait for the window
        log(f"[wait] for game window (up to {T['window_timeout']:.0f}s)...")
        hwnd, how = wait_for_window(T["window_timeout"])
        if not hwnd:
            log("ERROR: game window never appeared", file=sys.stderr)
            return 1
        log(f"[window] found via {how}")

        # 3. ждём готовность главного меню.
        #    Основной механизм — ВИЗУАЛЬНЫЙ детект по маркеру (треугольник над
        #    кнопкой «Сеть», снят через calibrate F8): ждём, пока маркер
        #    появится на кадре. Работает одинаково в холодном и тёплом запуске.
        #    Если маркера нет — откат на фиксированный таймер menu_load.
        marker, marker_meta = visual_ready.load_marker(
            os.path.join(config.CONFIG_DIR, "menu_marker.npy"),
            os.path.join(config.CONFIG_DIR, "menu_marker.json"))

        if marker is not None:
            log("[wait] визуальный детект меню (по маркеру)...")
            if visual_ready.wait_ready(
                    marker, marker_meta,
                    poll=T["menu_poll"],
                    timeout=T["menu_timeout"]):
                log("[wait] маркер найден — меню готово")
            else:
                log(f"ERROR: маркер не найден за {T['menu_timeout']:.0f}s — "
                      f"вероятно, игра не запустилась (краш / зависание)",
                      file=sys.stderr)
                return 1
        else:
            log(f"[wait] маркера нет — пауза {T['menu_load']:.0f}s (заставки)...")
            time.sleep(T["menu_load"])

        # 4. Network -> Local Network
        log("[nav] Сеть -> Лок. сеть")
        if not menu.goto_lan():
            return 1

        if args.stop_at == "lan":
            log("[done] reached LAN screen")
            return 0

        # 5. wait for the lobby, then Create Game
        log(f"[wait] lobby load ({T['lobby_load']:.0f}s)...")
        time.sleep(T["lobby_load"])
        log("[nav] Создать игру")
        if not menu.goto_create_game():
            return 1

        # 6. wait for the room, then configure everything (column by column)
        log(f"[wait] комната load ({T['room_load']:.0f}s)...")
        time.sleep(T["room_load"])

        log("[room] настраиваю комнату (сложность -> фракции -> союзы -> цвета)...")
        if not room.configure_room(faction, color_name, bot_factions, difficulty):
            return 1

        # 6b. фора по слотам (если задана)
        if handicaps:
            log("[room] выставляю фору...")
            for slot in sorted(handicaps):
                if not room.set_handicap(slot, handicaps[slot]):
                    return 1

        # 7. крепость: назначить стартовую позицию обороняющему слоту
        if fortress_key:
            name = fortresses.FORTRESSES[fortress_key]["name"]
            pos = fortresses.FORTRESSES[fortress_key]["start_pos"]
            log(f"[room] назначаю слот {fortress_slot} в крепость «{name}»...")
            if not room.assign_start_position(fortress_slot, pos):
                return 1

        # 8. Начать игру (после клика идёт 5-сек отсчёт; ввод остаётся
        #    заблокированным, чтобы нельзя было отменить старт вручную).
        log("[room] Начать игру")
        if not room.start_game():
            return 1
        log(f"[wait] отсчёт старта ({T['start_countdown']:.0f}s, ввод заблокирован)...")
        time.sleep(T["start_countdown"])

        log("[done] бой запущен")
        return 0
    finally:
        if locked:
            input_lock.unlock()
            log("[lock] user input unblocked")


if __name__ == "__main__":
    sys.exit(main())
