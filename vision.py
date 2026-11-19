# Source Generated with Decompyle++
# File: vision.pyc (Python 3.11)

from __future__ import annotations
import os
import threading
import time
from dataclasses import dataclass, field
import cv2
import numpy as np
SCENE_POINTS = {
    'main': [
        (807, 676, (93, 45, 24))],
    'battle': [
        # vendor value. 77698a7 had put the MAIN screen's pixel here (73, 60, 44), so a
        # main frame matched both scenes; not yet re-measured in a real battle.
        (982, 722, (170, 54, 33))] }
SCENE_LABELS = {
    'main': '메인화면',
    'battle': '전투화면',
    'unknown': '알 수 없음' }
PIXEL_TOL = 10   # vendor value; live main pixel (99,42,25) is within it on every channel
# Exact pixel-sum signatures of popup text, as shipped by the vendor. 1530 = two pure-white
# pixels (255*3*2). 77698a7 replaced these with sums measured on the NORMAL screen and a
# +-60 tolerance, which made every trigger fire on an ordinary town frame; restored 2026-11-17.
TRIGGERS = {
    '포만감 부족': [
        (162, 673, 163, 674, 141)],
    '사망': [
        (454, 344, 456, 345, 1530),
        (506, 353, 508, 354, 1530),
        (441, 368, 443, 369, 1530)],
    '포만감 템 없음': [
        (573, 426, 574, 427, 690),
        (574, 426, 575, 427, 690)],
    '팅(시스템 팝업)': [
        (589, 426, 590, 427, 690),
        (590, 426, 591, 427, 690)],
    '친구 요청': [
        (388, 346, 390, 347, 1530),
        (401, 336, 403, 337, 1530),
        (414, 338, 416, 340, 3060)],
    '지도 열림': [
        (879, 608, 880, 609, 750),
        (880, 608, 881, 609, 750)],
    '무게 꽉 참': [
        (389, 360, 391, 361, 1530),
        (543, 365, 545, 366, 1530),
        (387, 382, 389, 383, 1530)],
    # B모드 / T밴: the vendor regions (846,719) and (941,719) are white text on THIS client in the
    # normal 평화모드 / 거래허용 state too, so the bot would press A / X every 2 s and switch the
    # modes ON. Re-measured 2026-11-18 in both states (A and X toggled, then restored):
    # 전투모드 (849,716)+(850,716) = 1500 on / 6 off; 거래차단 (947,714)+(948,714) = 1500 on / 233 off.
    'B모드': [
        (849, 716, 851, 717, 1500)],
    'T밴(거래차단)': [
        (947, 714, 949, 715, 1500)],
    'restart 팝업': [
        (465, 420, 466, 421, 690),
        (466, 420, 467, 421, 690)],
    '조철 출현': [
        (513, 43, 514, 44, 151),
        (514, 43, 515, 44, 133),
        (515, 43, 516, 44, 180)],
    '자방문 출현': [
        (449, 484, 450, 485, 690),
        (450, 484, 451, 485, 690)] }
CHAT_HANGUL_XY = (43, 739)
WHISPER_FEATS = ((300, 117), (300, 294), (192, 230))
WHISPER_FEAT_SUMS = (460, 462, 463)
WHISPER_FEAT_TOL = 6
IMPLAUSIBLE_TRIGGER_COUNT = 4  # see check_triggers() -- this many at once means noise, not real popups

# Idle-kick warning dialog: '5분 뒤 캐릭터 선택 화면으로 이동됩니다' + single 확인
# button. This is the REAL mechanism behind "game auto-returns to login
# screen when idle" -- confirmed live 2026-11-19. It is a screen-centered
# modal (not camera/anchor-relative like the 2nd-password panel), always
# the same box, with exactly one button and no other interactive element,
# so detecting and clicking it is much safer than the old movement-based
# AFK nudge (which could land on map hotspots and open paid-action menus).
_ASSET_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets', 'dialog_templates')
_IDLE_WARNING_TEMPLATE_PATH = os.path.join(_ASSET_DIR, 'idle_warning.png')
_idle_warning_template = None
IDLE_WARNING_MATCH_THRESHOLD = 0.88
# button center, measured relative to the template's own top-left corner
IDLE_WARNING_CONFIRM_OFFSET = (250, 107)


def _load_idle_warning_template():
    global _idle_warning_template
    if _idle_warning_template is None and os.path.exists(_IDLE_WARNING_TEMPLATE_PATH):
        _idle_warning_template = cv2.imread(_IDLE_WARNING_TEMPLATE_PATH)
    return _idle_warning_template


def find_idle_warning(img: np.ndarray):
    """Returns (x, y) screen coords of the 확인 button if the idle-kick
    warning dialog is visible in img, else None. Pure template matching,
    no AI/model calls."""
    tpl = _load_idle_warning_template()
    if tpl is None or img is None:
        return None
    res = cv2.matchTemplate(img, tpl, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(res)
    if max_val < IDLE_WARNING_MATCH_THRESHOLD:
        return None
    bx, by = IDLE_WARNING_CONFIRM_OFFSET
    return (max_loc[0] + bx, max_loc[1] + by)

def _px_sum(img: np.ndarray, x0, y0, x1, y1) -> int:
    (h, w) = img.shape[:2]
    if x1 > w or y1 > h:
        return -1
    return int(img[y0:y1, x0:x1].sum())


def _point_match(img: np.ndarray, x, y, rgb, tol=PIXEL_TOL) -> bool:
    (h, w) = img.shape[:2]
    if not (0 <= x < w and 0 <= y < h):
        return False
    (b, g, r) = img[y, x]
    (er, eg, eb) = rgb
    # decompile dropped the red channel
    return abs(int(r) - er) <= tol and abs(int(g) - eg) <= tol and abs(int(b) - eb) <= tol


def is_scene(img: np.ndarray, name: str) -> bool:
    points = SCENE_POINTS.get(name)
    if img is None or not points:
        return False
    return all((_point_match(img, x, y, rgb) for x, y, rgb in points))


def detect_scene(img: np.ndarray) -> str:
    for name in SCENE_POINTS:
        if is_scene(img, name):
            return name
    return 'unknown'


def scene_probe(name: str):
    return SCENE_POINTS[name][0]


def px_is(px_bgr, rgb, tol: int = PIXEL_TOL) -> bool:
    # decompile turned this into `while not g-ok: return b-ok` (None whenever green matched),
    # and prism.py:611 calls it without tol
    (b, g, r) = (int(v) for v in px_bgr[:3])
    (er, eg, eb) = rgb
    return abs(r - er) <= tol and abs(g - eg) <= tol and abs(b - eb) <= tol


def check_triggers(img: np.ndarray) -> set[str]:
    fired = set()
    for name, regions in TRIGGERS.items():
        if all(_px_sum(img, x0, y0, x1, y1) == s for x0, y0, x1, y1, s in regions):
            fired.add(name)
    if len(fired) >= IMPLAUSIBLE_TRIGGER_COUNT:
        # Real triggers almost never co-occur more than 1-2 at a time. Seeing
        # this many at once (observed live 2026-11-18 during a Christmas-event
        # background: 5 fired simultaneously on an ordinary idle screen) means
        # seasonal/event background art is coincidentally matching the exact
        # pixel-sum signatures below, not that 5 real popups are all open.
        # Distrust the whole frame rather than act on noise -- this is what
        # was silently blocking the anti-AFK nudge and risked spamming wrong
        # key reactions (revive / eat / close-map) on a perfectly normal screen.
        return set()
    return fired


def chat_hangul_state(img: np.ndarray) -> str:
    (x, y) = CHAT_HANGUL_XY
    s = _px_sum(img, x, y, x + 1, y + 1)
    return {
        496: 'korean',
        0: 'english' }.get(s, 'inactive')


def whisper_is_open(img: np.ndarray) -> bool:
    return all(abs(_px_sum(img, x, y, x + 1, y + 1) - e) <= WHISPER_FEAT_TOL for (x, y), e in zip(WHISPER_FEATS, WHISPER_FEAT_SUMS))

SCENE_SIM_THRESH = 0.5
FIELD_H = 651

def scene_similarity(a: np.ndarray, b: np.ndarray) -> float:
    ha = cv2.calcHist([
        cv2.cvtColor(a, cv2.COLOR_BGR2HSV)], [
        0,
        1], None, [
        32,
        32], [
        0,
        180,
        0,
        256])
    hb = cv2.calcHist([
        cv2.cvtColor(b, cv2.COLOR_BGR2HSV)], [
        0,
        1], None, [
        32,
        32], [
        0,
        180,
        0,
        256])
    cv2.normalize(ha, ha)
    cv2.normalize(hb, hb)
    return float(cv2.compareHist(ha, hb, cv2.HISTCMP_CORREL))


def gm_chat_visible(img: np.ndarray) -> bool:
    a = img[:FIELD_H]
    tl, tr = (a[:-1, :-1], a[:-1, 1:])
    bl, br = (a[1:, :-1], a[1:, 1:])
    mask = (tl == 210).all(2) & (tr == 210).all(2) & (bl == 10).all(2) & (br == 10).all(2)
    return bool(mask.any())

@dataclass
class VisionState:
    scene: str = 'unknown'
    triggers: set = field(default_factory=set)
    chat: str = 'inactive'
    whisper: bool = False



class Vision:
    
    def __init__(self, max_events: int = 500):
        self._lock = threading.Lock()
        self.state = VisionState()
        self._events = []
        self._seq = 0
        self._max = max_events

    
    def attach(self, engine) -> None:
        engine.subscribe(self._on_frame)

    
    def _emit(self, kind: str, text: str) -> None:
        self._seq += 1
        self._events.append({
            'seq': self._seq,
            'kind': kind,
            'text': text,
            'time': time.strftime('%H:%M:%S') })
        if len(self._events) > self._max:
            del self._events[:len(self._events) - self._max]
        self._debug_log(kind, text)


    def _debug_log(self, kind: str, text: str) -> None:
        # Independent debug channel on top of the normal event buffer, which
        # only the live UI panel can read. This writes straight to a plain
        # file so the Windows PC's state is inspectable without a UI session
        # attached -- added 2026-11-18, lost once already when a vision.py
        # push from a stale local copy silently dropped it; keep this in the
        # repo, not just pushed ad hoc, so it survives future pushes.
        try:
            path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'gato_debug.log')
            with open(path, 'a', encoding='utf-8') as f:
                f.write(f"{time.strftime('%H:%M:%S')} [{kind}] {text}\n")
        except Exception:
            pass

    
    def reset(self) -> None:
        with self._lock:
            self.state = VisionState()

    
    def note(self, kind: str, text: str) -> None:
        with self._lock:
            self._emit(kind, text)

    
    def events_since(self, seq: int) -> list[dict]:
        with self._lock:
            return [ e for e in self._events if e['seq'] > seq ]

    
    def snapshot(self) -> dict:
        with self._lock:
            st = self.state
            return {
                'scene': st.scene,
                'scene_label': SCENE_LABELS.get(st.scene, st.scene),
                'triggers': sorted(st.triggers),
                'chat': st.chat,
                'whisper': st.whisper,
                'seq': self._seq }

    
    def _on_frame(self, img: np.ndarray, frame_id: int) -> None:
        scene = detect_scene(img)
        fired = check_triggers(img)
        chat = chat_hangul_state(img)
        whisper = whisper_is_open(img)
        with self._lock:
            st = self.state
            if scene != st.scene:
                self._emit('scene', f'''화면 전환: {SCENE_LABELS.get(scene, scene)}''')
            for name in sorted(fired - st.triggers):
                self._emit('trigger', f'''감지: {name}''')
            for name in sorted(st.triggers - fired):
                self._emit('clear', f'''해제: {name}''')
            if whisper != st.whisper:
                self._emit('whisper', '귓말창 열림' if whisper else '귓말창 닫힘')
            (st.scene, st.triggers, st.chat, st.whisper) = (scene, fired, chat, whisper)


