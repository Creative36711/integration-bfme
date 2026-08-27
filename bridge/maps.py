#!/usr/bin/env python3
"""
Карты и их стартовые позиции (оборона и атака).

На каждой карте фиксировано 8 точек:
  - первые 4 — позиции обороны (defense_positions), отсортированные по приоритету
  - вторые 4 — позиции атаки (attack_positions), отсортированные по приоритету

Механика назначения: расстановка идёт по порядку возрастания слотов (1, 2, 3, ...).
Клик по первой точке назначает слот 1 (игрока), клик по следующей точке сразу
назначает следующий свободный слот (слот 2), затем слот 3 и т.д. — по 1 клику на каждую позицию.

При расстановке по приоритету:
  - N защитников получают первые N точек обороны;
  - M атакующих получают первые M точек атаки.

При случайной расстановке:
  - N защитников получают N случайных точек из 4 оборонительных;
  - M атакующих получают M случайных точек из 4 атакующих.
  Защитник никогда не попадает на позицию атакующего, и наоборот.
"""

import random

MAPS = {
    "westmarch": {
        "name": "Вестмарш",
        "map_name": "map mp tournament westmarch",
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
        "defense_positions": [
            (0.4906, 0.3458),
            (0.4844, 0.3250),
            (0.4977, 0.3306),
            (0.4820, 0.3694),
        ],
        "attack_positions": [
            (0.4664, 0.4278),
            (0.4961, 0.4264),
            (0.5203, 0.4319),
            (0.5258, 0.3222),
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


def calculate_slot_positions(map_key, player_role, total_players,
                             player_faction, bot_factions,
                             random_positions=False):
    """Вычислить координаты стартовых позиций для каждого слота.

    Параметры:
      - map_key: ключ карты (например, "westmarch", "dagorlad")
      - player_role: "defender" (защитник) или "attacker" (атакующий)
      - total_players: общее число игроков (1..8)
      - player_faction: фракция игрока (слот 1)
      - bot_factions: dict {slot: faction_key} для слотов 2..N
      - random_positions: bool — расставлять позиции случайно (отдельно
        для защитников и атакующих) или по приоритету (по порядку списка).

    Возвращает:
      (slot_positions, defender_slots, attacker_slots)
      где slot_positions = {slot: (fx, fy)}
    """
    map_data = MAPS.get(map_key)
    if not map_data:
        map_data = get_map(map_key)
    if not map_data:
        return {}, [], []

    def_coords = list(map_data["defense_positions"])
    atk_coords = list(map_data["attack_positions"])

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

    # Подбор координат для защиты
    if random_positions:
        n_def = min(len(defender_slots), len(def_coords))
        chosen_def = random.sample(def_coords, n_def)
    else:
        chosen_def = def_coords[:len(defender_slots)]

    # Подбор координат для атаки
    if random_positions:
        n_atk = min(len(attacker_slots), len(atk_coords))
        chosen_atk = random.sample(atk_coords, n_atk)
    else:
        chosen_atk = atk_coords[:len(attacker_slots)]

    slot_positions = {}
    for slot, pos in zip(defender_slots, chosen_def):
        slot_positions[slot] = pos
    for slot, pos in zip(attacker_slots, chosen_atk):
        slot_positions[slot] = pos

    return slot_positions, defender_slots, attacker_slots
