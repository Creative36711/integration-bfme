#!/usr/bin/env python3
"""
Тесты для модуля карт и назначения стартовых позиций.
"""

import io
import os
import sys
import types
import unittest
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

if sys.platform != "win32":
    if "bridge.launcher" not in sys.modules:
        fake_launcher = types.ModuleType("bridge.launcher")
        fake_launcher.discover_exe = lambda exp=None: "C:\\RotWK\\lotrbfme2ep1.exe"
        fake_launcher.launch_game = lambda *a, **k: None
        sys.modules["bridge.launcher"] = fake_launcher
    if "bridge.navigate" not in sys.modules:
        fake_nav = types.ModuleType("bridge.navigate")
        fake_nav.INJECT_MAGIC = 0x42464D45
        fake_nav.viewport = lambda: (0, 0, 1920, 1080)
        fake_nav.click = lambda x, y: None
        fake_nav.move = lambda x, y: None
        fake_nav.scroll = lambda amount: None
        fake_nav.find_game_window = lambda: (None, None)
        sys.modules["bridge.navigate"] = fake_nav
    if "bridge.input_lock" not in sys.modules:
        fake_lock = types.ModuleType("bridge.input_lock")
        fake_lock.lock = lambda: True
        fake_lock.unlock = lambda: None
        sys.modules["bridge.input_lock"] = fake_lock
    if "bridge.elevate" not in sys.modules:
        fake_elevate = types.ModuleType("bridge.elevate")
        fake_elevate.is_admin = lambda: True
        fake_elevate.ensure_admin = lambda: None
        fake_elevate.restore_real_appdata = lambda argv=None: None
        sys.modules["bridge.elevate"] = fake_elevate
    if "bridge.visual_ready" not in sys.modules:
        fake_vr = types.ModuleType("bridge.visual_ready")
        fake_vr.load_marker = lambda *a: (None, None)
        fake_vr.wait_ready = lambda *a, **k: True
        sys.modules["bridge.visual_ready"] = fake_vr

from bridge import maps
from bridge import room
import main


class TestMaps(unittest.TestCase):
    def test_map_definitions(self):
        expected_keys = ["westmarch", "dagorlad", "dead_marshes", "minas_tirith"]
        self.assertEqual(list(maps.MAPS.keys()), expected_keys)

        for k, m in maps.MAPS.items():
            self.assertIn("name", m)
            self.assertIn("map_name", m)
            self.assertIn("is_fortress", m)
            self.assertEqual(len(m["defense_positions"]), 4)
            self.assertEqual(len(m["attack_positions"]), 4)
            for x, y in m["defense_positions"] + m["attack_positions"]:
                self.assertTrue(0.0 <= x <= 1.0)
                self.assertTrue(0.0 <= y <= 1.0)

        # Проверка флага крепости
        self.assertFalse(maps.is_fortress_map("westmarch"))
        self.assertFalse(maps.is_fortress_map("dagorlad"))
        self.assertFalse(maps.is_fortress_map("dead_marshes"))
        self.assertTrue(maps.is_fortress_map("minas_tirith"))

    def test_exact_coordinates(self):
        wm = maps.MAPS["westmarch"]
        self.assertEqual(wm["defense_positions"], [
            (0.4484, 0.3306),
            (0.4664, 0.3403),
            (0.4492, 0.4292),
            (0.4672, 0.4125),
        ])
        self.assertEqual(wm["attack_positions"], [
            (0.5273, 0.3389),
            (0.5430, 0.3264),
            (0.5250, 0.4167),
            (0.5437, 0.4278),
        ])

        dg = maps.MAPS["dagorlad"]
        self.assertEqual(dg["defense_positions"], [
            (0.4727, 0.3167),
            (0.5039, 0.3236),
            (0.5195, 0.3417),
            (0.5352, 0.3417),
        ])
        self.assertEqual(dg["attack_positions"], [
            (0.4555, 0.4222),
            (0.4813, 0.4403),
            (0.4898, 0.4250),
            (0.5156, 0.4347),
        ])

        dm = maps.MAPS["dead_marshes"]
        self.assertEqual(dm["defense_positions"], [
            (0.4914, 0.3208),
            (0.4617, 0.3458),
            (0.4734, 0.3639),
            (0.4672, 0.4125),
        ])
        self.assertEqual(dm["attack_positions"], [
            (0.5211, 0.3514),
            (0.5172, 0.4056),
            (0.5305, 0.4181),
            (0.4961, 0.4333),
        ])

        mt = maps.MAPS["minas_tirith"]
        self.assertEqual(mt["defense_positions"], [
            (0.4906, 0.3514),
            (0.4984, 0.3306),
            (0.4813, 0.3694),
            (0.4688, 0.3861),
        ])
        self.assertEqual(mt["attack_positions"], [
            (0.4656, 0.4306),
            (0.4945, 0.4250),
            (0.5211, 0.4306),
            (0.5250, 0.3208),
        ])

    def test_get_map(self):
        self.assertEqual(maps.get_map("1")["name"], "Вестмарш")
        self.assertEqual(maps.get_map("2")["name"], "Дагорлад")
        self.assertEqual(maps.get_map("3")["name"], "Мёртвые топи")
        self.assertEqual(maps.get_map("4")["name"], "Минас Тирит")
        self.assertEqual(maps.get_map("westmarch")["name"], "Вестмарш")
        self.assertEqual(maps.get_map("Минас Тирит")["name"], "Минас Тирит")
        self.assertEqual(maps.get_map("map wor dagorlad")["name"], "Дагорлад")
        self.assertEqual(maps.get_map("dead marshes")["name"], "Мёртвые топи")

    def test_calculate_slot_positions_priority_2v2_defender(self):
        # 2v2: player (Men, good) + bot2 (Elves, good) vs bot3 (Mordor, evil) + bot4 (Isengard, evil)
        # player is defender
        bot_factions = {2: "elves", 3: "mordor", 4: "isengard"}
        pos, def_s, atk_s = maps.calculate_slot_positions(
            "westmarch", "defender", 4, "men", bot_factions, random_positions=False
        )
        self.assertEqual(def_s, [1, 2])
        self.assertEqual(atk_s, [3, 4])
        wm = maps.MAPS["westmarch"]
        self.assertEqual(pos[1], wm["defense_positions"][0])
        self.assertEqual(pos[2], wm["defense_positions"][1])
        self.assertEqual(pos[3], wm["attack_positions"][0])
        self.assertEqual(pos[4], wm["attack_positions"][1])

    def test_calculate_slot_positions_priority_1v3_attacker(self):
        # 1v3: player (Mordor, evil) vs bot2 (Men), bot3 (Elves), bot4 (Dwarves)
        # player is attacker
        bot_factions = {2: "men", 3: "elves", 4: "dwarves"}
        pos, def_s, atk_s = maps.calculate_slot_positions(
            "dagorlad", "attacker", 4, "mordor", bot_factions, random_positions=False
        )
        self.assertEqual(atk_s, [1])
        self.assertEqual(def_s, [2, 3, 4])
        dg = maps.MAPS["dagorlad"]
        self.assertEqual(pos[1], dg["attack_positions"][0])
        self.assertEqual(pos[2], dg["defense_positions"][0])
        self.assertEqual(pos[3], dg["defense_positions"][1])
        self.assertEqual(pos[4], dg["defense_positions"][2])

    def test_calculate_slot_positions_fortress_owner(self):
        # 4v4 on Minas Tirith: defenders = [1, 2, 3, 4], attackers = [5, 6, 7, 8]
        # fortress owner = slot 4 -> slot 4 MUST get defense_positions[0]
        bot_factions = {
            2: "elves", 3: "dwarves", 4: "men",
            5: "mordor", 6: "isengard", 7: "goblins", 8: "angmar"
        }
        pos, def_s, atk_s = maps.calculate_slot_positions(
            "minas_tirith", "defender", 8, "men", bot_factions,
            random_positions=False, fortress_owner=4
        )
        mt = maps.MAPS["minas_tirith"]
        self.assertEqual(pos[4], mt["defense_positions"][0])  # Владелец на 1-й точке
        self.assertEqual(pos[1], mt["defense_positions"][1])
        self.assertEqual(pos[2], mt["defense_positions"][2])
        self.assertEqual(pos[3], mt["defense_positions"][3])
        self.assertEqual(pos[5], mt["attack_positions"][0])
        self.assertEqual(pos[6], mt["attack_positions"][1])
        self.assertEqual(pos[7], mt["attack_positions"][2])
        self.assertEqual(pos[8], mt["attack_positions"][3])

    def test_calculate_slot_positions_fortress_owner_random(self):
        # 4v4 on Minas Tirith with random mode: owner STILL gets defense_positions[0]
        bot_factions = {
            2: "elves", 3: "dwarves", 4: "men",
            5: "mordor", 6: "isengard", 7: "goblins", 8: "angmar"
        }
        mt = maps.MAPS["minas_tirith"]
        for _ in range(10):
            pos, def_s, atk_s = maps.calculate_slot_positions(
                "minas_tirith", "defender", 8, "men", bot_factions,
                random_positions=True, fortress_owner=3
            )
            self.assertEqual(pos[3], mt["defense_positions"][0])
            # Other defenders are placed on remaining defense positions
            rem_def = set(mt["defense_positions"][1:])
            self.assertIn(pos[1], rem_def)
            self.assertIn(pos[2], rem_def)
            self.assertIn(pos[4], rem_def)

    def test_calculate_slot_positions_random(self):
        # Random mode: defenders only get defense coords, attackers only get attack coords
        bot_factions = {2: "elves", 3: "mordor", 4: "isengard"}
        wm = maps.MAPS["westmarch"]
        def_coords_set = set(wm["defense_positions"])
        atk_coords_set = set(wm["attack_positions"])

        for _ in range(20):
            pos, def_s, atk_s = maps.calculate_slot_positions(
                "westmarch", "defender", 4, "men", bot_factions, random_positions=True
            )
            self.assertEqual(def_s, [1, 2])
            self.assertEqual(atk_s, [3, 4])
            # Each defender got a valid defense position
            self.assertIn(pos[1], def_coords_set)
            self.assertIn(pos[2], def_coords_set)
            self.assertNotEqual(pos[1], pos[2])  # distinct
            # Each attacker got a valid attack position
            self.assertIn(pos[3], atk_coords_set)
            self.assertIn(pos[4], atk_coords_set)
            self.assertNotEqual(pos[3], pos[4])  # distinct
            # No overlap between def and atk
            self.assertNotIn(pos[1], atk_coords_set)
            self.assertNotIn(pos[2], atk_coords_set)
            self.assertNotIn(pos[3], def_coords_set)
            self.assertNotIn(pos[4], def_coords_set)

    def test_calculate_slot_positions_same_alliance_fallback(self):
        # If all players pick Good factions (e.g. Men vs Elves)
        bot_factions = {2: "elves"}
        pos, def_s, atk_s = maps.calculate_slot_positions(
            "dead_marshes", "defender", 2, "men", bot_factions, random_positions=False
        )
        self.assertEqual(def_s, [1])
        self.assertEqual(atk_s, [2])
        dm = maps.MAPS["dead_marshes"]
        self.assertEqual(pos[1], dm["defense_positions"][0])
        self.assertEqual(pos[2], dm["attack_positions"][0])

    def test_assign_start_positions_regular_map(self):
        # Check regular map: ascending order 1, 2, 3, 4 with 1 click each
        calls = []
        orig_assign = room.assign_start_position

        def mock_assign(slot, pos, clicks=1):
            calls.append((slot, pos, clicks))
            return True

        room.assign_start_position = mock_assign
        try:
            slot_positions = {
                3: (0.3, 0.3),
                1: (0.1, 0.1),
                4: (0.4, 0.4),
                2: (0.2, 0.2),
            }
            res = room.assign_start_positions(slot_positions)
            self.assertTrue(res)
            # Must be ascending: 1, 2, 3, 4 with 1 click each
            slots_called = [c[0] for c in calls]
            clicks_called = [c[2] for c in calls]
            self.assertEqual(slots_called, [1, 2, 3, 4])
            self.assertEqual(clicks_called, [1, 1, 1, 1])
        finally:
            room.assign_start_position = orig_assign

    def test_assign_start_positions_fortress_owner(self):
        # Fortress owner slot 8 -> 8 clicks on owner's position first,
        # then remaining slots in ascending order with 1 click each
        calls = []
        orig_assign = room.assign_start_position

        def mock_assign(slot, pos, clicks=1):
            calls.append((slot, pos, clicks))
            return True

        room.assign_start_position = mock_assign
        try:
            slot_positions = {
                1: (0.1, 0.1),
                2: (0.2, 0.2),
                8: (0.8, 0.8),
                5: (0.5, 0.5),
            }
            res = room.assign_start_positions(slot_positions, fortress_owner=8)
            self.assertTrue(res)
            # First slot 8 with 8 clicks
            self.assertEqual(calls[0], (8, (0.8, 0.8), 8))
            # Then remaining slots 1, 2, 5 with 1 click each
            remaining_calls = calls[1:]
            self.assertEqual([c[0] for c in remaining_calls], [1, 2, 5])
            self.assertEqual([c[2] for c in remaining_calls], [1, 1, 1])
        finally:
            room.assign_start_position = orig_assign

    def test_ask_map(self):
        with patch("builtins.input", side_effect=["1"]):
            self.assertEqual(main.ask_map(), "westmarch")
        with patch("builtins.input", side_effect=["dagorlad"]):
            self.assertEqual(main.ask_map(), "dagorlad")
        with patch("builtins.input", side_effect=["Минас Тирит"]):
            self.assertEqual(main.ask_map(), "minas_tirith")

    def test_ask_player_role(self):
        with patch("builtins.input", side_effect=["1"]):
            self.assertEqual(main.ask_player_role(), "defender")
        with patch("builtins.input", side_effect=["защитник"]):
            self.assertEqual(main.ask_player_role(), "defender")
        with patch("builtins.input", side_effect=["2"]):
            self.assertEqual(main.ask_player_role(), "attacker")
        with patch("builtins.input", side_effect=["атакующий"]):
            self.assertEqual(main.ask_player_role(), "attacker")

    def test_ask_position_mode(self):
        with patch("builtins.input", side_effect=["1"]):
            self.assertEqual(main.ask_position_mode(), "priority")
        with patch("builtins.input", side_effect=[""]):
            self.assertEqual(main.ask_position_mode(), "priority")
        with patch("builtins.input", side_effect=["2"]):
            self.assertEqual(main.ask_position_mode(), "random")
        with patch("builtins.input", side_effect=["случайно"]):
            self.assertEqual(main.ask_position_mode(), "random")

    def test_ask_fortress_owner(self):
        # If only 1 defender, automatic selection
        self.assertEqual(main.ask_fortress_owner([1]), 1)
        # If multiple defenders, user chooses
        with patch("builtins.input", side_effect=["4"]):
            self.assertEqual(main.ask_fortress_owner([1, 2, 4]), 4)
        with patch("builtins.input", side_effect=["игрок"]):
            self.assertEqual(main.ask_fortress_owner([1, 3, 5]), 1)


if __name__ == "__main__":
    unittest.main()
