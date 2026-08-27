#!/usr/bin/env python3
"""
Тесты для модуля карт, парсинга файлов координат и назначения позиций.
"""

import io
import os
import sys
import tempfile
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


SAMPLE_COORDS_TEXT = """
2026-08-27 17:13:06  frac=(0.4906, 0.3514)  px=(1192,488)  ->  [0.4906, 0.3514],
2026-08-27 17:13:08  frac=(0.4984, 0.3306)  px=(1202,473)  ->  [0.4984, 0.3306],
2026-08-27 17:13:11  frac=(0.4813, 0.3694)  px=(1180,501)  ->  [0.4813, 0.3694],
2026-08-27 17:13:13  frac=(0.4688, 0.3861)  px=(1164,513)  ->  [0.4688, 0.3861],
2026-08-27 17:13:15  frac=(0.4656, 0.4306)  px=(1160,545)  ->  [0.4656, 0.4306],
2026-08-27 17:13:17  frac=(0.4945, 0.4250)  px=(1197,541)  ->  [0.4945, 0.4250],
2026-08-27 17:13:20  frac=(0.5211, 0.4306)  px=(1231,545)  ->  [0.5211, 0.4306],
2026-08-27 17:13:23  frac=(0.5250, 0.3208)  px=(1236,466)  ->  [0.5250, 0.3208],
"""


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

    def test_parse_coordinates_file(self):
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, suffix=".txt") as tf:
            tf.write(SAMPLE_COORDS_TEXT)
            tf_path = tf.name

        try:
            coords = maps.parse_coordinates_file(tf_path)
            self.assertEqual(len(coords), 8)
            self.assertEqual(coords[0], (0.4906, 0.3514))
            self.assertEqual(coords[1], (0.4984, 0.3306))
            self.assertEqual(coords[7], (0.5250, 0.3208))
        finally:
            os.remove(tf_path)

    def test_find_and_load_map_file_fortress(self):
        tmpdir = tempfile.mkdtemp()
        try:
            fpath = os.path.join(tmpdir, "_coordinates.txt")
            with open(fpath, "w", encoding="utf-8") as f:
                f.write(SAMPLE_COORDS_TEXT)

            found, is_fortress = maps.find_coordinates_file(fpath)
            self.assertEqual(found, fpath)
            self.assertTrue(is_fortress)

            m = maps.load_map_from_file(fpath)
            self.assertTrue(m["is_fortress"])
            self.assertEqual(len(m["defense_positions"]), 4)
            self.assertEqual(len(m["attack_positions"]), 4)
            self.assertEqual(m["defense_positions"][0], (0.4906, 0.3514))
        finally:
            import shutil
            shutil.rmtree(tmpdir)

    def test_find_and_load_map_file_regular(self):
        tmpdir = tempfile.mkdtemp()
        try:
            fpath = os.path.join(tmpdir, "coordinates.txt")
            with open(fpath, "w", encoding="utf-8") as f:
                f.write(SAMPLE_COORDS_TEXT)

            found, is_fortress = maps.find_coordinates_file(fpath)
            self.assertEqual(found, fpath)
            self.assertFalse(is_fortress)

            m = maps.load_map_from_file(fpath)
            self.assertFalse(m["is_fortress"])
            self.assertEqual(len(m["defense_positions"]), 4)
            self.assertEqual(len(m["attack_positions"]), 4)
        finally:
            import shutil
            shutil.rmtree(tmpdir)

    def test_calculate_slot_positions_from_loaded_map(self):
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, suffix=".txt") as tf:
            tf.write(SAMPLE_COORDS_TEXT)
            tf_path = tf.name

        try:
            map_data = maps.load_map_from_file(tf_path, is_fortress=True)
            bot_factions = {2: "elves", 3: "mordor", 4: "isengard"}
            pos, def_s, atk_s = maps.calculate_slot_positions(
                map_data, "defender", 4, "men", bot_factions,
                random_positions=False, fortress_owner=2
            )
            self.assertEqual(def_s, [1, 2])
            self.assertEqual(atk_s, [3, 4])
            # Slot 2 (owner) gets first defense position
            self.assertEqual(pos[2], (0.4906, 0.3514))
            self.assertEqual(pos[1], (0.4984, 0.3306))
            self.assertEqual(pos[3], (0.4656, 0.4306))
            self.assertEqual(pos[4], (0.4945, 0.4250))
        finally:
            os.remove(tf_path)

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

    def test_pyinstaller_main_spec(self):
        spec_path = os.path.join(ROOT, "packaging", "main.spec")
        self.assertTrue(os.path.exists(spec_path))

        calls = {}

        class _A:
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
        with open(spec_path, encoding="utf-8") as f:
            src = f.read()
        exec(compile(src, spec_path, "exec"), g)

        exe = calls.get("exe", {})
        self.assertEqual(calls.get("scripts"), [os.path.join(ROOT, "main.py")])
        self.assertEqual(exe.get("name"), "Main")
        self.assertTrue(exe.get("console"))
        self.assertTrue(exe.get("uac_admin"))
        self.assertIsNone(exe.get("runtime_tmpdir"))


if __name__ == "__main__":
    unittest.main()
