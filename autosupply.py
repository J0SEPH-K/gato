"""Auto-restock: teach-and-replay travel + food/weight management.

Why this file exists (manager, 2026-11-18): the live client has no pathfinding
and no map data, and 거상 has hundreds of hand-walked maps -- there is no
general "click anywhere, go anywhere" solution without either decompiling the
whole map graph or watching a human do it. The pattern this game's own
community actually uses for cross-map travel is NOT free-form walking: it is
(a) a paid instant teleport to one of two fixed hubs via a right-click field
menu (육의전 cost = level*2000, 무투장 cost = level*1000), (b) a location
scroll item bought from an NPC for some destinations, or (c) walking a route
the player already knows. This module automates exactly that shape:

  - WaypointRecorder: press a hotkey to start/stop; every real left-click
    the user makes on the game client while recording is appended as
    (x, y, wait_before_s) in REFERENCE (1024x768) coordinates. This is how
    you "teach" the bot a route once (field menu clicks, portal clicks,
    shop clicks) instead of guessing pixel positions.
  - replay_waypoints(): clicks the same sequence back with the same
    relative timing.
  - run_restock(): the orchestrator called when weight is full or food is
    out. SAFE BY DEFAULT: if `common.auto_restock_enabled` is False, or the
    current monster has no recorded `travel_waypoints`, it does nothing but
    log a clear reason -- it never guesses a screen position on a live
    account. Calibrating it is a one-time teach session per monster.

Nothing here runs unless config.auto_restock_enabled() is True AND the
current monster profile has non-empty travel_waypoints. Both are off by
default.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes
import json
import os
import threading
import time

VK_LBUTTON = 0x01
WAYPOINTS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "waypoints.json")


def _load_all() -> dict:
    if not os.path.exists(WAYPOINTS_PATH):
        return {}
    try:
        with open(WAYPOINTS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_all(data: dict) -> None:
    tmp = WAYPOINTS_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, WAYPOINTS_PATH)


def load_route(name: str) -> list:
    """Return the recorded [{'x','y','wait'}] list for a named route, or []."""
    return _load_all().get(name, [])


def save_route(name: str, clicks: list) -> None:
    data = _load_all()
    data[name] = clicks
    _save_all(data)


def delete_route(name: str) -> None:
    data = _load_all()
    data.pop(name, None)
    _save_all(data)


def list_routes() -> list:
    return sorted(_load_all().keys())


class WaypointRecorder:
    """Polls the real mouse button (GetAsyncKeyState) the same way the F10
    start/stop hotkey already works in prism.py -- consistent with this
    codebase's existing pattern, and it means recording works no matter
    which window has input focus, exactly like F10 does."""

    POLL_S = 0.02

    def __init__(self, to_client_xy):
        # to_client_xy(screen_x, screen_y) -> (ref_x, ref_y) | None, supplied
        # by the caller so this module never has to import capture/win32gui
        # itself (keeps it testable off-Windows too).
        self._to_client_xy = to_client_xy
        self._thread = None
        self._stop = threading.Event()
        self._clicks = []
        self._last_t = None
        self.recording = False

    def start(self) -> None:
        if self.recording:
            return
        self._clicks = []
        self._last_t = time.monotonic()
        self._stop.clear()
        self.recording = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> list:
        self._stop.set()
        self.recording = False
        if self._thread:
            self._thread.join(timeout=1.0)
        return list(self._clicks)

    def _loop(self) -> None:
        user32 = ctypes.windll.user32
        prev_down = False
        while not self._stop.is_set():
            down = bool(user32.GetAsyncKeyState(VK_LBUTTON) & 0x8000)
            if down and not prev_down:
                pt = ctypes.wintypes.POINT()
                user32.GetCursorPos(ctypes.byref(pt))
                ref = self._to_client_xy(pt.x, pt.y)
                if ref is not None:
                    now = time.monotonic()
                    wait = round(now - (self._last_t or now), 2)
                    self._last_t = now
                    self._clicks.append({"x": int(ref[0]), "y": int(ref[1]), "wait": wait})
            prev_down = down
            time.sleep(self.POLL_S)


def replay_waypoints(hands, clicks: list, log=print) -> bool:
    """Replay a recorded route. `hands` is the bot's own Hands instance (or
    RemoteHands), so this goes through the same click() path as everything
    else -- no new input primitive, no new risk surface."""
    if not clicks:
        log("[자동보충] 경로가 비어 있음 — 재생할 것이 없습니다")
        return False
    for i, step in enumerate(clicks):
        wait = step.get("wait", 0.0)
        if wait > 0:
            time.sleep(min(wait, 5.0))  # clamp: a bad recording should not stall minutes
        hands.click(int(step["x"]), int(step["y"]))
        log(f"경로 {i + 1}/{len(clicks)} 클릭 ({step['x']},{step['y']})")
    return True


def run_restock(brain, reason: str) -> None:
    """Called from brain.py when weight is full or food is out. `brain` is
    the live Brain instance itself (has .hands, .monster, ._log) -- does
    nothing destructive by default; every branch that would click something
    unverified logs why it refused instead of guessing."""
    log = lambda s: brain._log(f"[자동보충] {s}")
    try:
        import config
    except Exception as e:
        log(f"설정을 불러오지 못함 ({e}) — 중단")
        return

    if not config.auto_restock_enabled():
        log(f"{reason} — 자동 보충이 꺼져 있습니다 (설정 → 자동 보충 → 사용). 수동으로 처리하세요.")
        return

    monster = getattr(brain, "monster", None) or ""
    go_route = load_route(f"{monster}:to_town")
    back_route = load_route(f"{monster}:to_hunt")
    if not go_route or not back_route:
        log(
            f"{reason} — '{monster}' 몬스터의 이동 경로가 기록되지 않았습니다. "
            "설정 → 자동 보충 → 경로 기록으로 마을 이동(to_town)과 사냥터 복귀(to_hunt)를 "
            "한 번씩 직접 걸어가며 기록하세요. 기록 전까지는 자동으로 움직이지 않습니다."
        )
        return

    log(f"{reason} — 마을로 이동 시작")
    if not replay_waypoints(brain.hands, go_route, log):
        return
    food_item = config.food_item()
    food_qty = config.food_buy_qty()
    buy_route = load_route(f"{monster}:buy_food")
    if buy_route:
        log(f"{food_item} {food_qty}개 구매 시도")
        replay_waypoints(brain.hands, buy_route, log)
    else:
        log(f"구매 경로(buy_food)가 기록되지 않아 {food_item} 구매를 건너뜁니다 — 직접 구매하세요")
    sell_items = config.cleanup_sell_items()
    sell_route = load_route(f"{monster}:sell_items")
    if sell_items and sell_route:
        log(f"무게 정리: {sell_items} 판매 시도")
        replay_waypoints(brain.hands, sell_route, log)
    elif sell_items:
        log("판매 경로(sell_items)가 기록되지 않아 무게 정리를 건너뜁니다 — 직접 정리하세요")
    log("사냥터로 복귀 시작")
    replay_waypoints(brain.hands, back_route, log)
    log("자동 보충 완료 — 사냥 재시작하세요")
