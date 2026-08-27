#!/usr/bin/env python3
"""
Карты и их стартовые позиции (оборона и атака).

Координаты могут считываться автоматически из внешнего файла:
  - _coordinates.txt — карта-крепость (is_fortress = True, имя начинается с '_');
  - coordinates.txt  — обычная карта (is_fortress = False).

Формат файла: 8 строк координат (первые 4 — оборона, следующие 4 — атака).
Поддерживаются любые форматы (из calibrate.py, списки, кортежи, raw-числа).

Если файла координат нет, программа предлагает выбор из встроенных карт.

Для карты-крепости выбирается владелец (слот из защитников), который встаёт
на самую первую координату обороны (defense_positions[0]).

Механика назначения в комнате:
  - Если на карте-крепости задан владелец (слот K): кликаем его позицию K раз,
    чтобы слот K закрепился за главной точкой крепости.
    Затем все остальные слоты назначаются по возрастанию номеров (1, 2, 3, ...)
    ровно по 1 клику (игра автоматически подставляет следующий свободный слот).
  - На обычной карте все слоты назначаются по возрастанию номеров (1, 2, 3, ...)
    ровно по 1 клику на позицию.

При расстановке по приоритету:
  - N защитников получают первые N точек обороны (первая — владельцу крепости);
  - M атакующих получают первые M точек атаки.

При случайной расстановке:
  - Владелец крепости всегда на 1-й точке обороны;
  - Оставшиеся защитники получают случайные точки из оставшихся оборонительных;
  - M атакующих получают M случайных точек из 4 атакующих.
  Защитник никогда не попадает на позицию атакующего, и наоборот.
"""

import os
import random
import re

MAPS = {
    "westmarch": {
        "name": "Вестмарш",
        "map_name": "map mp tournament westmarch",
        "is_fortress": False,
        "defense_positions": [
            (0.4484, 0.3306),
            (0.4664, 0.3403),
            (0.4492, 0.4292),
            (0.4672, 0.4125),
        ],
        "attack_positions": [
            (0.5273, 0.3389),
            (0.5430, 0.3264),
            (0.5250, 0.4167),
            (0.5437, 0.4278),
        ],
    },
    "dagorlad": {
        "name": "Дагорлад",
        "map_name": "map wor dagorlad",
        "is_fortress": False,
        "defense_positions": [
            (0.4727, 0.3167),
            (0.5039, 0.3236),
            (0.5195, 0.3417),
            (0.5352, 0.3417),
        ],
        "attack_positions": [
            (0.4555, 0.4222),
            (0.4813, 0.4403),
            (0.4898, 0.4250),
            (0.5156, 0.4347),
        ],
    },
    "dead_marshes": {
        "name": "Мёртвые топи",
        "map_name": "map wor dead marshes",
        "is_fortress": False,
        "defense_positions": [
            (0.4914, 0.3208),
            (0.4617, 0.3458),
            (0.4734, 0.3639),
            (0.4672, 0.4125),
        ],
        "attack_positions": [
            (0.5211, 0.3514),
            (0.5172, 0.4056),
            (0.5305, 0.4181),
            (0.4961, 0.4333),
        ],
    },
    "minas_tirith": {
        "name": "Минас Тирит",
        "map_name": "map wor minas tirith",
        "is_fortress": True,
        "defense_positions": [
            (0.4906, 0.3514),
            (0.4984, 0.3306),
            (0.4813, 0.3694),
            (0.4688, 0.3861),
        ],
        "attack_positions": [
            (0.4656, 0.4306),
            (0.4945, 0.4250),
            (0.5211, 0.4306),
            (0.5250, 0.3208),
        ],
    },
}

# ---------------------------------------------------------------------------
# Союзы фракций (свет / тьма)
# ---------------------------------------------------------------------------
FACTION_ALLIANCES = {
    "men": "good", "elves": "good", "dwarves": "good",           # свет
    "isengard": "evil", "mordor": "evil", "goblins": "evil",     # тьма
    "angmar": "evil",
}


def find_coordinates_file(explicit_path=None):
    """Ищет файл координат.

    Возвращает (filepath, is_fortress) или (None, False).
    Правило определения крепости:
      - Если имя файла начинается с '_' (например, _coordinates.txt) -> это крепость (is_fortress=True).
      - Иначе (например, coordinates.txt) -> обычная карта (is_fortress=False).
    """
    from bridge import config

    if explicit_path and os.path.isfile(explicit_path):
        fname = os.path.basename(explicit_path)
        is_fortress = fname.startswith("_")
        return os.path.abspath(explicit_path), is_fortress

    search_dirs = [
        os.getcwd(),
        getattr(config, "BASE_DIR", None),
        getattr(config, "CONFIG_DIR", None),
    ]
    seen = set()
    dirs = []
    for d in search_dirs:
        if d and d not in seen and os.path.isdir(d):
            seen.add(d)
            dirs.append(d)

    # 1. Сначала проверяем _coordinates.txt (крепость)
    for d in dirs:
        p = os.path.join(d, "_coordinates.txt")
        if os.path.isfile(p):
            return os.path.abspath(p), True

    # 2. Затем проверяем coordinates.txt (обычная карта)
    for d in dirs:
        p = os.path.join(d, "coordinates.txt")
        if os.path.isfile(p):
            return os.path.abspath(p), False

    return None, False


def parse_coordinates_file(filepath):
    """Считывает координаты из файла.

    Поддерживает форматы:
      1) '2026-08-27 17:13:06 frac=(0.4906, 0.3514) px=(1192,488) -> [0.4906, 0.3514],'
      2) '[cal] frac=(0.4906, 0.3514) px=(1192,488)'
      3) '[0.4906, 0.3514],' или '(0.4906, 0.3514)'
      4) '0.4906, 0.3514' или '0.4906 0.3514'

    Возвращает список кортежей [(fx, fy), ...].
    """
    coords = []
    if not filepath or not os.path.isfile(filepath):
        return coords

    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("//"):
                continue

            # 1. Формат со стрелкой: -> [0.1234, 0.5678]
            m = re.search(r'->\s*\[\s*([0-9.]+)\s*,\s*([0-9.]+)\s*\]', line)
            if m:
                coords.append((float(m.group(1)), float(m.group(2))))
                continue

            # 2. Формат frac=(0.1234, 0.5678)
            m = re.search(r'frac=\(\s*([0-9.]+)\s*,\s*([0-9.]+)\s*\)', line)
            if m:
                coords.append((float(m.group(1)), float(m.group(2))))
                continue

            # 3. Формат скобок: [0.1234, 0.5678] или (0.1234, 0.5678)
            m = re.search(r'[\[\(]\s*([0-9.]+)\s*,\s*([0-9.]+)\s*[\]\)]', line)
            if m:
                coords.append((float(m.group(1)), float(m.group(2))))
                continue

            # 4. Формат двух float
            m = re.search(r'([0-9]+\.[0-9]+)[,\s]+([0-9]+\.[0-9]+)', line)
            if m:
                coords.append((float(m.group(1)), float(m.group(2))))
                continue

    return coords


def load_map_from_file(filepath, is_fortress=None):
    """Создаёт структуру карты из файла coordinates.txt / _coordinates.txt.

    Первые 4 точки — оборона (по приоритету), следующие 4 точки — атака (по приоритету).
    """
    coords = parse_coordinates_file(filepath)
    fname = os.path.basename(filepath)
    if is_fortress is None:
        is_fortress = fname.startswith("_")

    if len(coords) >= 8:
        def_coords = coords[:4]
        atk_coords = coords[4:8]
    elif len(coords) > 0:
        half = len(coords) // 2
        def_coords = coords[:half]
        atk_coords = coords[half:]
    else:
        def_coords = []
        atk_coords = []

    type_str = "Крепость" if is_fortress else "Обычная карта"
    return {
        "name": f"{type_str} ({fname})",
        "map_name": fname,
        "is_fortress": is_fortress,
        "defense_positions": def_coords,
        "attack_positions": atk_coords,
        "source_file": filepath,
    }


def get_map(key):
    """Получить данные карты по ключу, номеру или названию."""
    if not key:
        return None
    k_str = str(key).strip().lower()
    keys = list(MAPS.keys())
    if k_str.isdigit() and 1 <= int(k_str) <= len(keys):
        return MAPS[keys[int(k_str) - 1]]
    if k_str in MAPS:
        return MAPS[k_str]
    for k, v in MAPS.items():
        if k_str in (v["name"].lower(), v["map_name"].lower()):
            return v
    for k, v in MAPS.items():
        if k_str in v["map_name"].lower().replace("map ", ""):
            return v
    return None


def is_fortress_map(key):
    """Является ли карта крепостью."""
    if isinstance(key, dict):
        return bool(key.get("is_fortress", False))
    m = get_map(key)
    return bool(m.get("is_fortress", False)) if m else False


def get_team_slots(player_role, total_players, player_faction, bot_factions):
    """Разделение слотов 1..total_players на защитников и атакующих."""
    player_alliance = FACTION_ALLIANCES.get(player_faction, "good")
    allies = [1]
    enemies = []
    for slot in range(2, total_players + 1):
        bot_all = FACTION_ALLIANCES.get(bot_factions.get(slot), None)
        if bot_all == player_alliance:
            allies.append(slot)
        else:
            enemies.append(slot)

    # Если все фракции одного союза (например, все «Свет»),
    # то делим: слот 1 (игрок) против слотов 2..N (боты).
    if not enemies and total_players > 1:
        allies = [1]
        enemies = list(range(2, total_players + 1))

    if player_role in ("defender", "защитник", "def"):
        defender_slots = list(allies)
        attacker_slots = list(enemies)
    else:
        attacker_slots = list(allies)
        defender_slots = list(enemies)

    return defender_slots, attacker_slots


def calculate_slot_positions(map_key_or_data, player_role, total_players,
                             player_faction, bot_factions,
                             random_positions=False,
                             fortress_owner=None):
    """Вычислить координаты стартовых позиций для каждого слота.

    Параметры:
      - map_key_or_data: ключ карты (str) или словарь данных карты (dict)
      - player_role: "defender" (защитник) или "attacker" (атакующий)
      - total_players: общее число игроков (1..8)
      - player_faction: фракция игрока (слот 1)
      - bot_factions: dict {slot: faction_key} для слотов 2..N
      - random_positions: bool — расставлять позиции случайно (отдельно
        для защитников и атакующих) или по приоритету (по порядку списка).
      - fortress_owner: номер слота владельца крепости (встаёт на 1-ю точку обороны).

    Возвращает:
      (slot_positions, defender_slots, attacker_slots)
      где slot_positions = {slot: (fx, fy)}
    """
    if isinstance(map_key_or_data, dict):
        map_data = map_key_or_data
    else:
        map_data = MAPS.get(map_key_or_data)
        if not map_data:
            map_data = get_map(map_key_or_data)
    if not map_data:
        return {}, [], []

    def_coords = list(map_data.get("defense_positions", []))
    atk_coords = list(map_data.get("attack_positions", []))

    defender_slots, attacker_slots = get_team_slots(
        player_role, total_players, player_faction, bot_factions
    )

    slot_positions = {}

    # Обработка позиций защиты
    if fortress_owner and fortress_owner in defender_slots and def_coords:
        # Владелец крепости гарантированно встаёт на самую первую координату обороны
        slot_positions[fortress_owner] = def_coords[0]
        rem_slots = [s for s in defender_slots if s != fortress_owner]
        rem_coords = def_coords[1:]
        if random_positions:
            n_def = min(len(rem_slots), len(rem_coords))
            chosen_def = random.sample(rem_coords, n_def)
        else:
            chosen_def = rem_coords[:len(rem_slots)]
        for slot, pos in zip(rem_slots, chosen_def):
            slot_positions[slot] = pos
    else:
        if random_positions:
            n_def = min(len(defender_slots), len(def_coords))
            chosen_def = random.sample(def_coords, n_def)
        else:
            chosen_def = def_coords[:len(defender_slots)]
        for slot, pos in zip(defender_slots, chosen_def):
            slot_positions[slot] = pos

    # Обработка позиций атаки
    if random_positions:
        n_atk = min(len(attacker_slots), len(atk_coords))
        chosen_atk = random.sample(atk_coords, n_atk)
    else:
        chosen_atk = atk_coords[:len(attacker_slots)]
    for slot, pos in zip(attacker_slots, chosen_atk):
        slot_positions[slot] = pos

    return slot_positions, defender_slots, attacker_slots
