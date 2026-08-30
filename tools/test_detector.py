#!/usr/bin/env python3
"""
Офлайн-тест определения команды-победителя по скриншоту экрана «Счёт».

Запуск:
    python tools/test_detector.py <screenshot.png> [--players "Имя,color,team,slot" ...]

    python tools/test_detector.py _tools/screenshots/3x4_score.jpg
    python tools/test_detector.py _tools/screenshots/3x4_score.jpg --players \
        "Игрок,blue,1,1" "Бот1,green,1,2" "Бот2,yellow,1,3" \
        "Бот3,red,2,4" "Бот4,orange,2,5" "Бот5,purple,2,6" "Бот6,white,2,7"

Если --players не задан, используются цвета по умолчанию (см. DEFAULT_PLAYERS),
покрывающие 7-игровые скриншоты (_tools/screenshots/*.jpg).
"""

import argparse
import json
import sys

sys.path.insert(0, ".")

from match_result_detector import MatchResultDetector  # noqa: E402


# Дефолтные игроки для 7-игровых скриншотов («3х4»):
# 3 Света + 4 Тьмы. Цвета — по привязке фракций bridge.network_prefs.
DEFAULT_PLAYERS = [
    {"name": "Игрок", "slot": 1, "color": "blue", "team": 1, "is_local_player": True},
    {"name": "Бот1", "slot": 2, "color": "green", "team": 1, "is_local_player": False},
    {"name": "Бот2", "slot": 3, "color": "yellow", "team": 1, "is_local_player": False},
    {"name": "Бот3", "slot": 4, "color": "red", "team": 2, "is_local_player": False},
    {"name": "Бот4", "slot": 5, "color": "orange", "team": 2, "is_local_player": False},
    {"name": "Бот5", "slot": 6, "color": "purple", "team": 2, "is_local_player": False},
    {"name": "Бот6", "slot": 7, "color": "white", "team": 2, "is_local_player": False},
]


def parse_players(args):
    """Разобрать --players "Имя,color,team,slot" ... -> список dict."""
    players = []
    for spec in args:
        parts = [p.strip() for p in spec.split(",")]
        name = parts[0]
        color = parts[1] if len(parts) > 1 else "blue"
        team = int(parts[2]) if len(parts) > 2 else 1
        slot = int(parts[3]) if len(parts) > 3 else len(players) + 1
        players.append({"name": name, "color": color, "team": team,
                        "slot": slot, "is_local_player": (len(players) == 0)})
    return players


def main(argv=None):
    ap = argparse.ArgumentParser(description="test match result detector on screenshot")
    ap.add_argument("screenshot", help="path to screenshot (jpg/png)")
    ap.add_argument("--players", nargs="*", default=None,
                    help='players as "Имя,color,team,slot"')
    ap.add_argument("--debug", action="store_true", help="save debug frames")
    args = ap.parse_args(argv)

    # Определяем число игроков по скриншоту? Не можем автоматически, поэтому
    # фильтруем дефолтных 7 по числу реально присутствующих иконок — но это
    # уже делает сам детектор. Для теста возьмём переданных или дефолт.
    players = parse_players(args.players) if args.players else list(DEFAULT_PLAYERS)

    if args.debug:
        cfg = {"debug": True}
    else:
        cfg = {}

    detector = MatchResultDetector(players, config=cfg,
                                   capture=lambda: None, click=None)
    result = detector.analyze_file(args.screenshot)

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())