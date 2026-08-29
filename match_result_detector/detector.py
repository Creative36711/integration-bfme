#!/usr/bin/env python3
"""
Главный класс MatchResultDetector — определение команды-победителя по
экрану статистики BFME2:RotWK.

Поток работы:
    1. В фоне ждём экран статистики (оба маркера: крепость + шапка «Счёт»).
    2. Кликаем «Пропустить» и вкладку «Счёт» (график с полным набором иконок).
    3. Для КАЖДОГО игрока 1..N кликаем его слот в «Рейтинге»: его линия
       становится ЯРКОЙ (насыщенной). Мы ЗНАЕМ цвет этого слота заранее,
       поэтому не «угадываем» его, а просто ищем яркую линию этого цвета и
       смотрим, к какой иконке (монета/вспышка) она приходит.
    4. Собираем результат: у кого монета -> победитель, у кого вспышка ->
       проигравший. Команда-победитель = команда любого победителя.

Формат результата (config/match_result.json):
    {
      "match_status": "COMPLETED" | "SURRENDER" | "UNKNOWN",
      "winning_team": 1 | 2 | null,
      "losing_team": 2 | 1 | null,
      "winners": [...], "losers": [...], "unmatched_players": [...],
      "raw_data": {...}
    }

Команды: 1 = Свет (добро), 2 = Тьма (зло) — bridge.room.ALLIANCE_ORDER.
"""

import json
import logging
import os
import sys
import threading
import time
from typing import Any, Callable, Dict, List, Optional

import numpy as np

# Корень проекта нужен для импорта bridge.log (он не под Windows-only).
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# Импорты модулей match_result_detector (не Windows-only, можно везде).
from . import color_analyzer
from . import icon_finder
from . import player_matcher
from .config import DetectorConfig, TEMPLATE_FILES, TEMPLATES_DIR
from .screen_monitor import ScoreScreenMonitor

# Модульный LOGGER (а не функция!). Все вызовы в коде ниже — это
# стандартный Python API: log.info(...), log.warning(...), log.exception(...).
# Чтобы вывод попадал в stdout/stderr как `[match] ...` строки (как делает
# main.py), прицепим handler, который маршрутизирует через bridge.log.log().
log = logging.getLogger("match_detector.detector")

_BRIDGE_LOG = None
try:
    from bridge.log import log as _bridge_log_func  # noqa: F811
    _BRIDGE_LOG = _bridge_log_func
except Exception:  # noqa: BLE001
    _BRIDGE_LOG = None


class _BridgeLogHandler(logging.Handler):
    def emit(self, record):  # noqa: D401
        try:
            msg = self.format(record)
        except Exception:  # noqa: BLE001
            return
        stream = sys.stderr if record.levelno >= logging.WARNING else sys.stdout
        if _BRIDGE_LOG is None:
            try:
                print(msg, file=stream)
            except Exception:  # noqa: BLE001
                pass
            return
        try:
            _BRIDGE_LOG(msg, file=stream)
        except Exception:  # noqa: BLE001
            pass


if not any(isinstance(h, _BridgeLogHandler) for h in log.handlers):
    _h = _BridgeLogHandler(level=logging.INFO)
    _h.setFormatter(logging.Formatter("%(message)s"))
    log.addHandler(_h)
log.propagate = False


BLACK_FRAME_MEAN = 6.0
BLACK_FRAME_BRIGHT_RATIO = 0.0005
BLACK_FRAME_BRIGHT_MEAN = 20.0

STATUS_COMPLETED = "COMPLETED"
STATUS_SURRENDER = "SURRENDER"
STATUS_UNKNOWN = "UNKNOWN"
STATUS_TIMEOUT = "TIMEOUT"


def _is_black_frame(frame):
    mean = float(frame.mean())
    if mean < BLACK_FRAME_MEAN:
        return True
    bright = float((frame.max(axis=2) > 60).mean())
    if mean < BLACK_FRAME_BRIGHT_MEAN and bright < BLACK_FRAME_BRIGHT_RATIO:
        return True
    return False


def _default_capture():
    try:
        from bridge import navigate as nav
    except Exception:  # noqa: BLE001
        return lambda: None

    def capture():
        try:
            return nav.capture_window()
        except Exception:  # noqa: BLE001
            return None

    return capture


def _default_game_alive():
    try:
        from bridge import navigate as nav
    except Exception:  # noqa: BLE001
        return None

    def alive():
        hwnd, _how = nav.find_game_window(require_visible=False)
        return hwnd is not None

    return alive


def _default_click():
    try:
        from bridge import navigate as nav
        return nav.click
    except Exception:  # noqa: BLE001
        return lambda x, y: None


class MatchResultDetector:
    """Детектор команды-победителя по экрану статистики BFME2."""

    def __init__(self, players: List[Dict[str, Any]],
                 screen_resolution: Optional[tuple] = None,
                 capture: Optional[Callable] = None,
                 config: Optional[Dict[str, Any]] = None,
                 game_alive: Optional[Callable] = None,
                 click: Optional[Callable] = None):
        """Создать детектор.

        Args:
            players: список dict: name, color (blue/red/...), team (1/2),
                is_local_player, slot.
            screen_resolution: (w, h); если неизвестно, берётся из кадра.
            capture: callable -> (H, W, 3) numpy RGB.
            config: dict переопределений DetectorConfig.
            game_alive: callable -> bool (жива ли игра).
            click: callable (x_px, y_px) — клик мышью.
        """
        if not players:
            raise ValueError("players list must not be empty")
        self.players = list(players)
        self._screen_resolution = tuple(screen_resolution) \
            if screen_resolution else None
        self._cfg = DetectorConfig.from_dict(config)
        self._capture = capture or _default_capture()
        self._game_alive = game_alive or _default_game_alive()
        self._click = click or _default_click()

        self._templates: Dict[str, np.ndarray] = {}
        self._monitor: Optional[ScoreScreenMonitor] = None
        self._result: Optional[Dict[str, Any]] = None
        self._result_event = threading.Event()
        self._analysis_lock = threading.Lock()

        self._capture_fail_reason = None

        # Каллбэки жизненного цикла.
        self.on_score_screen_detected: Optional[Callable] = None
        self.on_analysis_finished: Optional[Callable] = None

    # ------------------------------------------------------------------
    # Публичный API
    # ------------------------------------------------------------------
    def start_monitoring(self, on_result_callback: Optional[Callable] = None,
                         timeout: Optional[float] = None) -> None:
        self._result = None
        self._result_event.clear()
        self._on_result_callback = on_result_callback
        self._monitor = ScoreScreenMonitor(
            is_score_screen=self.is_score_screen,
            poll=self._cfg.monitor_poll,
            confirm_streak=self._cfg.confirm_streak,
            on_score_screen=self._on_score_screen_cb,
            on_timeout=self._on_monitor_timeout_cb,
            game_alive=self._game_alive,
        )
        self._monitor.start()
        if timeout:
            threading.Timer(timeout, self.stop_monitoring).start()

    def stop_monitoring(self) -> None:
        if self._monitor:
            self._monitor.stop()
            self._monitor = None

    def is_monitoring(self) -> bool:
        return bool(self._monitor and self._monitor.is_alive())

    def wait_for_result(self, timeout: Optional[float] = None) -> Optional[Dict]:
        if not self.is_monitoring():
            self.start_monitoring(timeout=self._cfg.monitor_timeout)
        self._result_event.wait(timeout=timeout)
        if self._result is None:
            return self._unknown("no result (monitor stopped or timeout)")
        return self._result

    def analyze_current_screen(self) -> Dict[str, Any]:
        frame = self._capture_frame()
        if frame is None:
            return self._unknown("capture failed")
        return self.analyze_image(frame)

    def analyze_image(self, frame: np.ndarray) -> Dict[str, Any]:
        frame = np.asarray(frame)
        if frame.ndim != 3 or frame.shape[2] < 3:
            raise ValueError("frame must be (H, W, 3) RGB array")
        frame = frame[:, :, :3].astype(np.uint8, copy=False)
        with self._analysis_lock:
            return self._analyze_locked(frame)

    def analyze_file(self, path: str) -> Dict[str, Any]:
        frame = icon_finder.load_png(path)
        if frame is None:
            raise ValueError(f"cannot load image: {path}")
        return self.analyze_image(frame)

    def is_score_screen(self, frame: Optional[np.ndarray] = None) -> bool:
        if frame is None:
            frame = self._capture_frame()
            if frame is None:
                return False
        h, w = frame.shape[:2]
        for name in self._cfg.required_screen_templates:
            tpl = self._template(name, scale=self._cfg.scale_for(w, h))
            if tpl is None:
                continue
            roi = self._screen_template_roi(name, w, h)
            threshold = self._cfg.screen_template_thresholds.get(name, 0.65)
            hits = icon_finder.find_template(
                frame, tpl, roi, threshold,
                nms_distance=max(4, tpl.shape[1] / 2))
            if not hits:
                return False
        return True

    # ------------------------------------------------------------------
    # Внутренности
    # ------------------------------------------------------------------
    def _screen_template_roi(self, name, w, h):
        if name == "fortress":
            return self._cfg.roi_pixels(self._cfg.fortress_roi, w, h)
        if name == "score_marker":
            return self._cfg.roi_pixels(self._cfg.score_marker_roi, w, h)
        return None

    def _template(self, name, scale=1.0):
        if name in self._templates:
            return self._templates[name]
        fname = TEMPLATE_FILES.get(name)
        if not fname:
            return None
        path = TEMPLATES_DIR / fname
        tpl = icon_finder.load_png(str(path))
        if tpl is None:
            return None
        if scale != 1.0:
            box = max(6, int(min(tpl.shape[:2]) * scale))
            tpl = icon_finder.resize_image(
                tpl, box, int(box * tpl.shape[1] / tpl.shape[0]))
        self._templates[name] = tpl
        return tpl

    def _analyze_locked(self, frame):
        """Анализ одного готового кадра (статичный путь, без кликов)."""
        icons = self._detect_all_icons(frame)
        result = self._match_icons_to_players(frame, icons)
        result["raw_data"]["score_screen_detected"] = self.is_score_screen(frame)
        return result

    def _capture_frame(self):
        try:
            frame = self._capture()
        except Exception as exc:  # noqa: BLE001
            frame = None
            self._capture_fail_reason = str(exc)
        if frame is None:
            return None
        frame = np.asarray(frame)
        if frame.ndim == 2:
            frame = np.stack([frame] * 3, axis=-1)
        if frame.shape[2] < 3:
            return None
        frame = frame[:, :, :3].astype(np.uint8, copy=False)
        if self._screen_resolution is None:
            self._screen_resolution = (frame.shape[1], frame.shape[0])
        return frame

    def _on_score_screen_cb(self):
        log.info("score screen detected — analysing")
        # Дать внешнему коду (main.py) возможность заблокировать физический
        # ввод на время кликов по вкладкам/слотам.
        cb = self.on_score_screen_detected
        if cb:
            try:
                cb()
            except Exception:  # noqa: BLE001
                log.exception("on_score_screen_detected callback failed")
        try:
            self._analyze_score_screen()
        except Exception as exc:  # noqa: BLE001
            log.exception("analysis failed")
            self._result = self._unknown(f"analysis exception: {exc}")
            self._result_event.set()
            fb = self.on_analysis_finished
            if fb:
                try:
                    fb()
                except Exception:  # noqa: BLE001
                    log.exception("on_analysis_finished callback failed")

    def _on_monitor_timeout_cb(self):
        log.warning("score screen not detected before timeout — TIMEOUT")
        self._result = self._unknown("score screen not detected (timeout)")
        self._result_event.set()

    def _analyze_score_screen(self):
        try:
            if self._cfg.click_skip:
                self._click_skip()
            if self._cfg.click_score_tab:
                self._click_score_tab()

            # Ожидаем стабильный кадр с иконками.
            frame = None
            deadline = time.monotonic() + self._cfg.analysis_timeout
            while time.monotonic() < deadline:
                f = self._capture_frame()
                if f is not None and not _is_black_frame(f):
                    frame = f
                    break
                time.sleep(self._cfg.analysis_retry_delay)
            if frame is None:
                self._result = self._unknown("no valid frame")
                self._result_event.set()
                return

            icons = self._detect_all_icons(frame)
            result = self._match_icons_to_players(frame, icons)
            result["raw_data"]["score_screen_detected"] = True
            self._result = result
            self._result_event.set()

            cb = getattr(self, "_on_result_callback", None)
            if cb:
                try:
                    cb(result)
                except Exception:  # noqa: BLE001
                    log.exception("on_result_callback failed")
        finally:
            # Разблокировать ввод после анализа (внешний код залочил его в
            # on_score_screen_detected). Гарантированно и на успехе, и при
            # «no valid frame».
            fb = self.on_analysis_finished
            if fb:
                try:
                    fb()
                except Exception:  # noqa: BLE001
                    log.exception("on_analysis_finished callback failed")

    def _detect_all_icons(self, frame):
        """Найти все иконки победы/поражения в области графика."""
        h, w = frame.shape[:2]
        scale = self._cfg.scale_for(w, h)
        coin = self._template("victory", scale)
        flame = self._template("defeat", scale)
        roi = self._cfg.roi_pixels(self._cfg.chart_roi, w, h)

        icons = []
        for kind, tpl in (("victory", coin), ("defeat", flame)):
            if tpl is None:
                continue
            for cx, cy, score in icon_finder.find_template(
                    frame, tpl, roi, self._cfg.icon_threshold,
                    self._cfg.icon_nms_distance * scale):
                icons.append({"kind": kind, "cx": cx, "cy": cy,
                              "score": round(float(score), 3),
                              "player": None, "color_side": None})

        # Fallback: если в chart_roi пусто — искать шире.
        if (self._cfg.full_screen_icon_fallback and not icons):
            roi2 = self._cfg.roi_pixels(self._cfg.icon_fallback_roi, w, h)
            for kind, tpl in (("victory", coin), ("defeat", flame)):
                if tpl is None:
                    continue
                for cx, cy, score in icon_finder.find_template(
                        frame, tpl, roi2, self._cfg.icon_threshold,
                        self._cfg.icon_nms_distance * scale):
                    icons.append({"kind": kind, "cx": cx, "cy": cy,
                                  "score": round(float(score), 3),
                                  "player": None, "color_side": None})

        # Дедупликация по близости (coin/flame в одной точке — берём выше score).
        icons.sort(key=lambda i: -i["score"])
        dedup = []
        for ic in icons:
            if all((ic["cx"] - d["cx"]) ** 2 + (ic["cy"] - d["cy"]) ** 2
                   > (self._cfg.icon_nms_distance) ** 2 for d in dedup):
                dedup.append(ic)
        return dedup

    def _match_icons_to_players(self, frame, icons):
        """Сопоставить иконки с игроками.

        Два пути:
          1. click-highlight (живой прогон): кликаем по каждому слоту, его
             линия становится яркой; ищем ЯРКУЮ линию ЗАДАННОГО цвета (цвета
             игрока) и смотрим, к какой иконке она приходит — это самый
             надёжный способ (цвет известен заранее).
          2. static fallback (офлайн/настройка): пишем цвет линии слева от
             каждой иконки и сопоставляем с известными цветами игроков.
        """
        base_frame = frame
        assignments = []
        log_vivid = []

        # --- Путь 1: клик по слотам для подсветки ----------------------
        if (self._cfg.click_slots and self._click is not None
                and self._viewport() is not None):
            assignments, surrendered = self._match_by_highlight(
                frame, icons, log_vivid)
            result = player_matcher.build_result(self.players, assignments,
                                                 raw={},
                                                 surrendered=surrendered)
            result["raw_data"]["icons"] = assignments
            result["raw_data"]["highlight_assignments"] = log_vivid
            result["raw_data"]["surrendered_slots"] = surrendered
            result["raw_data"]["click_slots"] = True
            if self._cfg.debug:
                self._save_debug(base_frame, assignments, result)
            return result

        # --- Путь 2: статичный кадр (без кликов) -----------------------
        for ic in icons:
            idx = self._icon_to_player_index(base_frame, ic)
            assignments.append({
                "kind": ic["kind"], "cx": ic["cx"], "cy": ic["cy"],
                "score": ic["score"], "player": idx,
                "color_side": self.players[idx].get("color") if idx is not None else None,
            })

        result = player_matcher.build_result(self.players, assignments, raw={})
        result["raw_data"]["icons"] = assignments
        result["raw_data"]["highlight_assignments"] = log_vivid
        result["raw_data"]["click_slots"] = False
        if self._cfg.debug:
            self._save_debug(base_frame, assignments, result)
        return result

    def _match_by_highlight(self, frame, icons, log_vivid):
        """Путь 1: кликаем по слотам, ищем яркую линию цвета игрока.

        Returns:
            (icon_assignments, surrendered_idx).
            icon_assignments — список dict по иконкам (player/kind/...).
            surrendered_idx — список индексов игроков, чья линия дотрассирована,
            но НЕ дошла ни до одной иконки (сдался/вышел).
        """
        base_frame = frame
        resolved = {}            # slot -> {"kind", "icon", "dist", "color"}
        surrendered_slots = set()  # slot, чья линия НЕ дошла до иконки (сдался)
        max_xy = 160.0
        max_x_gap = 80.0
        for p in self.players:
            slot = p.get("slot", 1)
            color = p.get("color")
            if not color:
                continue
            # Слот 1 активирован по умолчанию в UI — кликать не обязательно,
            # но по нему цвет уже выделен. Кликаем по слотам 2..N.
            if slot != 1:
                clicked = self._click_slot(slot)
                if not clicked:
                    log.warning("click for slot %d (%s) FAILED — line "
                                "stays dim, will likely be SURRENDER",
                                slot, color)
            f = self._capture_frame()
            if f is None:
                f = base_frame

            x_end, y_end, _pixels = color_analyzer.find_highlighted_line_endpoint(
                f, color, self._cfg, exclude_icons=icons, near_icons=icons,
                y_band=120.0)
            if x_end is not None:
                ic, dist = color_analyzer.nearest_icon(
                    x_end, y_end, icons,
                    max_xy_dist=max_xy, max_x_gap=max_x_gap)
                if ic is not None:
                    resolved[slot] = {"kind": ic["kind"], "icon": ic,
                                      "dist": dist, "color": color}
                    log_vivid.append(
                        (color, slot, ic["kind"], x_end, y_end, round(dist, 1)))
                else:
                    # Линия дотрассирована, но не дошла до иконки — сдался/вышел.
                    surrendered_slots.add(slot)
                    log_vivid.append(
                        (color, slot, "SURRENDER", x_end, y_end, round(dist, 1)))
            else:
                log.warning("could not find bright %s line at slot %d",
                            color, slot)

        # Устранение конфликтов: если в одну иконку уперлись несколько
        # слотов, оставляем тот, у кого |cx-x_end| минимальный (или если
        # ничья — отдаём ближайшему по прямой). Остальных переводим в
        # SURRENDER.
        if resolved:
            grouped_by_icon: Dict[int, List[Tuple[int, dict]]] = {}
            for sl, info in resolved.items():
                # один и тот же объект icon может повторяться
                key = id(info["icon"])
                grouped_by_icon.setdefault(key, []).append(
                    (sl, info))
            for icon_id, group in grouped_by_icon.items():
                if len(group) <= 1:
                    continue
                # Выбираем «лучшего»
                group.sort(key=lambda t: (t[1]["dist"], t[0]))
                winner_slot = group[0][0]
                for sl, info in group[1:]:
                    log.warning("ambiguous line attribution: slot %d "
                                "(%s) also reached the icon taken by slot "
                                "%d — treating as SURRENDER",
                                sl, info["color"], winner_slot)
                    surrendered_slots.add(sl)
                    resolved.pop(sl, None)

        # Собираем assignments: каждая иконка -> слот, который к ней привязан.
        assignments = []
        for ic in icons:
            slot_owner = None
            for slot, info in resolved.items():
                if (info["icon"]["cx"] == ic["cx"]
                        and info["icon"]["cy"] == ic["cy"]):
                    slot_owner = slot
                    break
            if slot_owner is not None:
                p = self._player_by_slot(slot_owner)
                assignments.append({
                    "kind": ic["kind"], "cx": ic["cx"], "cy": ic["cy"],
                    "score": ic["score"], "player": self.players.index(p),
                    "color_side": p.get("color"),
                })
            else:
                assignments.append({
                    "kind": ic["kind"], "cx": ic["cx"], "cy": ic["cy"],
                    "score": ic["score"], "player": None, "color_side": None,
                })

        # Слоты-«сдавшиеся» превращаем в индексы игроков (для build_result).
        surrendered_idx = [self.players.index(self._player_by_slot(s))
                           for s in surrendered_slots]
        return assignments, surrendered_idx

    def _icon_to_player_index(self, frame, icon):
        """Статичный путь: определить цвет линии у иконки -> индекс игрока."""
        cx = int(icon["cx"])
        cy = int(icon["cy"])
        res = color_analyzer.analyze_line_at_icon(
            frame, cx, cy, self.players, self._cfg,
            scale=self._cfg.scale_for(frame.shape[1], frame.shape[0]))
        return res.get("player")

    def _player_by_slot(self, slot):
        for p in self.players:
            if p.get("slot") == slot:
                return p
        return self._player_by_index(0)

    def _player_by_index(self, idx):
        return self.players[idx] if 0 <= idx < len(self.players) else self.players[0]

    # --- клики ---------------------------------------------------------
    def _click_slot(self, slot):
        """Кликнуть по слоту в «Рейтинге», чтобы подсветить его линию.

        Возвращает True, если клик был выполнен (даже если viewport == None
        — это будет видно из warnings, но без падения). Возвращает False,
        если клик НЕ МОГ быть выполнен (нет viewport/нет координат).
        """
        try:
            vp = self._viewport()
            if not vp:
                self._log_no_viewport(f"slot {slot}")
                return False
            left, top, W, H = vp
            pos = self._cfg.rating_slot_frac.get(slot)
            if not pos:
                log.warning("slot %d has no rating_slot_frac coord", slot)
                return False
            x = left + int(pos[0] * W)
            y = top + int(pos[1] * H)
            if self._click is None:
                log.warning("slot %d: no click callable", slot)
                return False
            self._click(x, y)
            time.sleep(self._cfg.slot_settle)
            log.info("clicked rating slot %d @(%d,%d)", slot, x, y)
            return True
        except Exception:  # noqa: BLE001
            log.exception("_click_slot(%d) failed", slot)
            return False

    def _click_skip(self):
        try:
            vp = self._viewport()
            if not vp:
                self._log_no_viewport("skip")
                return
            left, top, W, H = vp
            fx, fy = self._cfg.skip_button_frac
            self._click(left + int(fx * W), top + int(fy * H))
            log.info("clicked 'Пропустить'")
            time.sleep(self._cfg.tab_settle)
        except Exception:  # noqa: BLE001
            log.exception("_click_skip failed")

    def _click_score_tab(self):
        try:
            vp = self._viewport()
            if not vp:
                self._log_no_viewport("score tab")
                return
            left, top, W, H = vp
            fx0, fy0, fx1, fy1 = self._cfg.score_tab_roi
            x = left + int((fx0 + fx1) / 2 * W)
            y = top + int((fy0 + fy1) / 2 * H)
            for i in range(2):
                self._click(x, y)
                if i == 0 and self._cfg.tab_settle:
                    time.sleep(self._cfg.tab_settle)
            log.info("clicked 'Счёт' tab")
            time.sleep(self._cfg.tab_settle)
        except Exception:  # noqa: BLE001
            log.exception("_click_score_tab failed")

    def _viewport(self):
        try:
            from bridge import navigate as nav
            return nav.viewport()
        except Exception:  # noqa: BLE001
            return None

    def _log_no_viewport(self, what):
        log.warning("cannot click '%s': no viewport", what)

    def _unknown(self, error):
        return {
            "match_status": STATUS_UNKNOWN,
            "winning_team": None, "losing_team": None,
            "winners": [], "losers": [], "unmatched_players": [],
            "raw_data": {"error": error},
        }

    # --- отладка -------------------------------------------------------
    def _save_debug(self, frame, assignments, result):
        os.makedirs(self._cfg.debug_dir, exist_ok=True)
        ts = time.strftime("%Y%m%d_%H%M%S")
        path = os.path.join(self._cfg.debug_dir, f"frame_{ts}.png")
        vis = frame.copy()
        for ic in assignments:
            cx, cy = int(ic["cx"]), int(ic["cy"])
            color = (0, 255, 0) if ic["kind"] == "victory" else (0, 0, 255)
            _draw_rect(vis, cx - 20, cy - 20, cx + 20, cy + 20, color)
        icon_finder.save_png(vis, path)
        with open(path.replace(".png", ".json"), "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)


def _draw_rect(img, x0, y0, x1, y1, color, thickness=2):
    h, w = img.shape[:2]
    x0 = max(0, x0); y0 = max(0, y0)
    x1 = min(w - 1, x1); y1 = min(h - 1, y1)
    if x1 <= x0 or y1 <= y0:
        return
    c = np.asarray(color, dtype=np.uint8)
    img[y0:y0 + thickness, x0:x1 + 1] = c
    img[y1 - thickness + 1:y1 + 1, x0:x1 + 1] = c
    img[y0:y1 + 1, x0:x0 + thickness] = c
    img[y0:y1 + 1, x1 - thickness + 1:x1 + 1] = c
