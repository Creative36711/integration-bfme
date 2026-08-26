#!/usr/bin/env python3
"""
Config file paths and load/save helpers.

Paths are computed from this file's location, NOT the current working
directory — so they stay correct no matter where you run the scripts from.
"""

import json
import os

# integration/  (one level above bridge/)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_DIR = os.path.join(BASE_DIR, "config")

CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")          # game path / args
POSITIONS_FILE = os.path.join(CONFIG_DIR, "menu_positions.json")  # button coords


def load_json(path, default=None):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return default if default is not None else {}


def load_config():
    """Load config.json (game path, launch args)."""
    return load_json(CONFIG_FILE, {})


def load_positions():
    """Load menu_positions.json (button coords)."""
    return load_json(POSITIONS_FILE, {})
