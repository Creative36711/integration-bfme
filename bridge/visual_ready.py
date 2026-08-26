#!/usr/bin/env python3
"""
Визуальный детект готовности по МАРКЕРУ (маленькому стабильному элементу UI).

ЗАДАЧА:
  Точно понять, что нужный экран уже отрисован (главное меню и т.д.),
  независимо от холодного/тёплого запуска. Таймеры и CPU/диск ненадёжны.

ИДЕЯ (язык- и мод-независимо):
  У кнопок с выпадающим списком есть маленький ТРЕУГОЛЬНИК-индикатор.
  Картинки и названия каждый мод меняет, а этот элемент остаётся неизменным.
  Мы запоминаем этот треугольник как МАРКЕР: маленький кусочек экрана + его
  позиция (в долях окна). Пока маркер не найден на кадре — экран грузится;
  найден — экран готов.

МАРКЕР задаётся через tools/calibrate.py (горячая клавиша F8): курсор наводится
на треугольник, сохраняется:
  * config/menu_marker.npy  — кусочек картинки (numpy);
  * config/menu_marker.json — {"fx":…, "fy":…, "size_frac":…} позиция в долях.

Чтобы маркер работал на ЛЮБОМ разрешении, хранится его размер в долях окна;
при проверке маркер автомасштабируется под текущее разрешение.

Требует numpy.
"""

import json
import os
import time

import numpy as np

from bridge import navigate as nav

DEFAULT_MATCH = 0.85     # доля совпавших пикселей для признания «готово»
DEFAULT_TOLERANCE = 30   # допуск по каналу (0..255)


def _resize(arr, new_w, new_h):
    """Ресайз nearest-neighbor (для подгонки маркера под разрешение)."""
    if arr.shape[0] == new_h and arr.shape[1] == new_w:
        return arr
    ys = np.round(np.linspace(0, arr.shape[0] - 1, new_h)).astype(int)
    xs = np.round(np.linspace(0, arr.shape[1] - 1, new_w)).astype(int)
    return arr[ys][:, xs]


def _match_ratio(frame, template, tolerance):
    """Доля пикселей, где кадр и шаблон совпадают (в пределах tolerance)."""
    if frame.shape != template.shape:
        return 0.0
    diff = np.abs(frame.astype(np.int16) - template.astype(np.int16))
    close = (diff <= tolerance).all(axis=2)
    return float(close.mean())


def load_marker(npy_path, json_path):
    """Загрузить маркер: (template, meta). Возвращает (None, None) если нет."""
    if not os.path.exists(npy_path) or not os.path.exists(json_path):
        return None, None
    template = np.load(npy_path)
    with open(json_path, encoding="utf-8") as f:
        meta = json.load(f)
    return template, meta


def is_ready(template, meta, match=DEFAULT_MATCH, tolerance=DEFAULT_TOLERANCE):
    """True, если маркер найден на текущем кадре игры."""
    frame = nav.capture_window()
    if frame is None:
        return False
    h, w = frame.shape[:2]

    # Размер области маркера в текущем разрешении (из доли окна).
    box = max(4, int(meta["size_frac"] * min(h, w)))
    t = _resize(template, box, box)

    # Центр области по долям окна.
    cx = int(meta["fx"] * w)
    cy = int(meta["fy"] * h)
    x0 = max(0, cx - box // 2)
    y0 = max(0, cy - box // 2)
    region = frame[y0:y0 + box, x0:x0 + box]

    return _match_ratio(region, t, tolerance) >= match


def wait_ready(template, meta, match=DEFAULT_MATCH, tolerance=DEFAULT_TOLERANCE,
               poll=1.0, timeout=300.0):
    """Ждать, пока маркер не появится на кадре. True = готово, False = таймаут."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if is_ready(template, meta, match, tolerance):
            return True
        time.sleep(poll)
    return False
