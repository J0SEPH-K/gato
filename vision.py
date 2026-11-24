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
# Offset of the confirm button inside idle_warning.png. Re-measured live 2026-11-23 on
# a real popup: template re-cropped to (380,360)-(660,500), button centre at client
# (612,473) = +232/+113. The old template scored only 0.75 against the real dialog
# (below the 0.88 gate) so the bot never clicked it and got kicked to login instead.
IDLE_WARNING_CONFIRM_OFFSET = (232, 113)


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
    if '포만감 템 없음' in fired:
        # The two exact-sum pixels sit at screen centre, i.e. on the player's own sprite: a white
        # pixel pair there matched on a perfectly normal frame (measured live on finevt-7 2026-11-23:
        # (230,230,230) x2 at (573,426) with the gauge at 97%) and stopped every run. A real
        # "no food" popup only matters when the gauge is low, so a readable, healthy gauge vetoes it.
        frac = food_fraction(img)
        if frac is not None and frac >= FOOD_LOW_FRAC:
            fired.discard('포만감 템 없음')
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
            path = os.path.join(__import__('config').BASE_DIR, 'gato_debug.log')
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




# ---- 불사신부 사용 확인 팝업 (용병/캐릭터 사망 시) -------------------------------------
# '불사신부 사용시 의원으로 가지 않고 그 자리에서 부활할 수 있습니다. 사용하시겠습니까?' + 확인/취소.
# Geometry measured 2026-11-19 from a client screenshot (1024x768 reference). Several other
# dialogs (e.g. paid travel) share the same two-button layout, so the BUTTONS alone are never
# enough to click: the message text must also match the stored text mask.
REVIVE_OK_BOX = (532, 434, 586, 449)
REVIVE_CANCEL_BOX = (604, 434, 658, 449)
REVIVE_GAP_BOX = (588, 434, 602, 449)
REVIVE_CLICK_XY = (558, 441)
REVIVE_TEXT_BOX = (380, 340, 640, 392)
REVIVE_TEXT_MIN = 0.6
_REVIVE_MASK_PATH = os.path.join(_ASSET_DIR, 'revive_text_mask.png')
_revive_mask = None


def _warm_fill(img: np.ndarray, box) -> float:
    x0, y0, x1, y1 = box
    reg = img[y0:y1, x0:x1].astype(np.int16)
    if reg.size == 0:
        return 0.0
    b, g, r = reg[..., 0], reg[..., 1], reg[..., 2]
    m = (r > 120) & (r < 190) & (g > 110) & (g < 170) & (b > 95) & (b < 150) & (r - b > 15) & (r - b < 60)
    return float(m.mean())


def _load_revive_mask():
    global _revive_mask
    if _revive_mask is None and os.path.exists(_REVIVE_MASK_PATH):
        m = cv2.imread(_REVIVE_MASK_PATH, cv2.IMREAD_GRAYSCALE)
        if m is not None:
            if m.ndim == 3:          # cv2 5.0 returns (h, w, 1) for IMREAD_GRAYSCALE
                m = m[:, :, 0]
            _revive_mask = (m > 127).astype(np.uint8)
    return _revive_mask


def find_revive_popup(img: np.ndarray):
    """Returns ('ok', (x, y)) when the 불사신부 popup is visible (click (x, y) = 확인),
    ('unknown', None) when a 확인/취소 dialog is at that spot but the message text does not
    match (never click), or None when no such dialog is there."""
    tpl = _load_revive_mask()
    if tpl is None or img is None or img.shape[0] < 768 or img.shape[1] < 1024:
        return None
    if _warm_fill(img, REVIVE_OK_BOX) < 0.55 or _warm_fill(img, REVIVE_CANCEL_BOX) < 0.55:
        return None
    if _warm_fill(img, REVIVE_GAP_BOX) > 0.15:
        return None
    k3 = np.ones((3, 3), np.uint8)
    k5 = np.ones((5, 5), np.uint8)
    t_d = cv2.dilate(tpl, k3)
    x0, y0, x1, y1 = REVIVE_TEXT_BOX
    best = (0.0, 0.0)
    for dy in (-2, -1, 0, 1, 2):
        for dx in (-2, -1, 0, 1, 2):
            reg = img[y0 + dy:y1 + dy, x0 + dx:x1 + dx]
            if reg.shape[:2] != tpl.shape:
                continue
            c = (cv2.cvtColor(reg, cv2.COLOR_BGR2GRAY) > 140).astype(np.uint8)
            n = int(c.sum())
            if n == 0:
                continue
            recall = float(np.logical_and(tpl, cv2.dilate(c, k5)).sum()) / max(1, int(tpl.sum()))
            prec = float(np.logical_and(c, t_d).sum()) / n
            if min(recall, prec) > min(best):
                best = (recall, prec)
    if min(best) >= REVIVE_TEXT_MIN:
        return ('ok', REVIVE_CLICK_XY)
    return ('unknown', None)


# ---- 포만감 gauge, 용병 portraits, inventory (measured 2026-11-19 on a native 1024x768 client) ----
_UI_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets', 'ui_templates')
FOOD_BAR_X = (89, 235)          # first/last pixel column of the gauge
FOOD_BAR_Y = 673                # a row through the fill (fill is y 670..677)
FOOD_LOW_FRAC = 0.2


def food_fraction(img: np.ndarray):
    """포만감 fill 0.0..1.0, or None if the gauge is not on screen (battle scene, covered...)."""
    if img is None or img.shape[0] < 768 or img.shape[1] < 1024:
        return None
    # frame of the gauge: black line above the fill and the dark right border
    if int(img[669, 150].sum()) > 40 or int(img[FOOD_BAR_Y, FOOD_BAR_X[1] + 1].sum()) > 60:
        return None
    n = 0
    for x in range(FOOD_BAR_X[0], FOOD_BAR_X[1] + 1):
        b, g, r = (int(v) for v in img[FOOD_BAR_Y, x])
        if g > r + 25 and g > b + 25 and g > 70:
            n += 1
        else:
            break
    return n / float(FOOD_BAR_X[1] - FOOD_BAR_X[0] + 1)


MERC_BAR_ROWS = tuple(35 + 41 * i for i in range(12))   # red HP bar rows of the 12 portrait slots
MERC_BAR_X = (4, 84)


def _merc_has_bar(img: np.ndarray, y0: int) -> bool:
    """Red HP bar present in the slot's bar row: 2 of 3 consecutive rows with >= 4 red pixels
    (searched +-9 px because the selection frame shifts one slot). Any HP above ~5% shows, a dead
    merc shows none, and portrait art rarely produces a 3-row red streak."""
    for y in range(y0 - 9, y0 + 12):
        band = img[y:y + 3, 6:88].astype(np.int16)
        red = (band[..., 2] > 140) & (band[..., 1] < 70) & (band[..., 0] < 70)
        if int((red.sum(axis=1) >= 4).sum()) >= 2:
            return True
    return False


def dead_mercs(img: np.ndarray) -> list:
    """1-based portrait slots whose portrait is shown but whose red HP bar is gone (= dead)."""
    if img is None or img.shape[0] < 768 or img.shape[1] < 1024:
        return []
    dead = []
    for i, y0 in enumerate(MERC_BAR_ROWS):
        if _merc_has_bar(img, y0):
            continue          # alive
        port = img[max(0, y0 - 34):y0 - 1, 6:80]
        gray = cv2.cvtColor(port, cv2.COLOR_BGR2GRAY)
        if gray.mean() >= 30 and gray.std() >= 15:     # a portrait is there (not an empty panel)
            dead.append(i + 1)
    return dead


INV_HEADER_XY = (690, 100)
INV_CELL_R1C2 = (640, 172)       # 궁중 타락죽 (row 1, column 2 of the 가방 tab)
INV_CELL_ICON_XY = (622, 154)
INV_MATCH_MIN = 0.85
_tpl_cache = {}


def _tpl(name):
    if name not in _tpl_cache:
        _tpl_cache[name] = cv2.imread(os.path.join(_UI_DIR, name))
    return _tpl_cache[name]


def _match_at(img, tpl, xy, pad=6):
    if tpl is None or img is None or img.shape[0] < 768 or img.shape[1] < 1024:
        return 0.0
    x, y = xy
    h, w = tpl.shape[:2]
    reg = img[max(0, y - pad):y + h + pad, max(0, x - pad):x + w + pad]
    if reg.shape[0] < h or reg.shape[1] < w:
        return 0.0
    return float(cv2.matchTemplate(reg, tpl, cv2.TM_CCOEFF_NORMED).max())


def inventory_open(img: np.ndarray) -> bool:
    """The 가방 window is open at its default position."""
    return _match_at(img, _tpl('inventory_header.png'), INV_HEADER_XY) >= INV_MATCH_MIN


def porridge_in_r1c2(img: np.ndarray) -> bool:
    """Row 1, column 2 of the open inventory shows the 궁중 타락죽 icon."""
    return _match_at(img, _tpl('porridge_icon.png'), INV_CELL_ICON_XY) >= INV_MATCH_MIN


def merc_slots(img: np.ndarray) -> list:
    """[(slot 1..12, has_hp_bar, portrait_mean_gray)] for the 용병 portrait column."""
    if img is None or img.shape[0] < 768 or img.shape[1] < 1024:
        return []
    out = []
    for i, y0 in enumerate(MERC_BAR_ROWS):
        port = img[max(0, y0 - 34):y0 - 1, 6:80]
        out.append((i + 1, _merc_has_bar(img, y0), float(cv2.cvtColor(port, cv2.COLOR_BGR2GRAY).mean())))
    return out


def merc_gauge(img: np.ndarray, y0: int):
    """(red_px, blue_px) of the HP and mana gauges in the slot's bar band (searched +-9 rows,
    the selection frame shifts the lower slots by a few pixels)."""
    best = (0, 0)
    for y in range(y0 - 9, y0 + 12):
        band = img[y:y + 12, 8:76].astype(np.int16)
        b, g, r = band[..., 0], band[..., 1], band[..., 2]
        red = int(((r > 140) & (g < 70) & (b < 70)).sum())
        blue = int(((b > 120) & (r < 130) & (b - r > 25)).sum())
        if red + blue > best[0] + best[1]:
            best = (red, blue)
    return best


MERC_GAUGE_MIN = 20     # alive units show >= ~200 red and ~200 blue px; a dead one shows 0 of both


def merc_alive_slots(img: np.ndarray) -> list:
    """Slots that show an HP or mana gauge (= a live unit)."""
    if img is None or img.shape[0] < 768 or img.shape[1] < 1024:
        return []
    out = []
    for i, y0 in enumerate(MERC_BAR_ROWS):
        red, blue = merc_gauge(img, y0)
        if red >= MERC_GAUGE_MIN or blue >= MERC_GAUGE_MIN:
            out.append(i + 1)
    return out


def dead_mercs_v2(img: np.ndarray, occupied=()) -> list:
    """Dead 용병 = a slot with NO HP gauge and NO mana gauge that still holds a unit.
    Held = a live unit sits in a lower slot (units fill the column from the top, so a gap above a
    live one is a dead one), or the slot was seen alive earlier (`occupied`, persisted)."""
    alive = merc_alive_slots(img)
    if not alive:
        return []          # no gauge anywhere: window covered, loading, or the wrong screen
    last_alive = max(alive)
    out = []
    for slot in range(1, 13):
        if slot in alive:
            continue
        if slot < last_alive or slot in occupied:
            out.append(slot)
    return out

# --- slot occupancy -------------------------------------------------------------------
# Empty portrait panels are dark blue-grey placeholder art (mean ~33-70, almost no bright
# pixels); a portrait - alive or dead - is bright grey art (>= ~245 px above 180 in the band,
# dead ones desaturated).  The 150 threshold sits in the middle of a 69 -> 245 gap, so it does
# not depend on the skin or on the HP colour.
MERC_OCC_BRIGHT_MIN = 150


def merc_occupied_slot(img: np.ndarray, y0: int) -> bool:
    """True when the portrait slot holds art at all (alive or dead), False for an empty panel."""
    band = img[max(0, y0 - 38):max(1, y0 - 2), 4:86]
    g = cv2.cvtColor(band, cv2.COLOR_BGR2GRAY)
    return int((g > 180).sum()) >= MERC_OCC_BRIGHT_MIN


def merc_occupied(img: np.ndarray) -> list:
    """1-based slots that currently show portrait art."""
    if img is None or img.shape[0] < 768 or img.shape[1] < 1024:
        return []
    return [i + 1 for i, y0 in enumerate(MERC_BAR_ROWS) if merc_occupied_slot(img, y0)]


def dead_mercs_v3(img: np.ndarray) -> list:
    """Dead unit = a slot that shows portrait art but neither an HP nor a mana gauge.

    Empty panels are dark placeholder art and carry no portrait, so they are never reported -
    the stale occupied list that used to flag them is gone. Units fill the column top-down,
    so a gauge-less slot above the last live one is dead even if its portrait is blanked."""
    if img is None or img.shape[0] < 768 or img.shape[1] < 1024:
        return []
    alive = set(merc_alive_slots(img))
    if not alive:
        return []
    last_alive = max(alive)
    return [s for s in range(1, 13)
            if s not in alive
            and (s < last_alive or merc_occupied_slot(img, MERC_BAR_ROWS[s - 1]))]
