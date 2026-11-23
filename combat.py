# Source Generated with Decompyle++
# File: combat.pyc (Python 3.11)

import glob
import os
import time
import cv2
import numpy as np
import config as _config
import detector as _det
import vision
(MAP_X0, MAP_Y0) = (36, 670)
(MAP_W, MAP_H) = (180, 90)
MAP_CENTER = (MAP_W / 2.0, MAP_H / 2.0)
(BOX_W, BOX_H) = (66, 46)
FIELD_CENTER = (512, 373)
SUMMON_BOUNDS = (40, 40, 984, 614)
PAN_VY = 67.5
PAN_VX = 135.0
PAN_BASE = 0.4
PAN_RATIO = 0.7
PAN_SCREEN_VX = 2140.0
PAN_SCREEN_VY = 1080.0
PAN_SCREEN_MIN_HOLD = 0.04
MINIMAL_AIM_BOUNDS = (120.0, 100.0, 904.0, 550.0)
MINIMAL_PAN_INSET = 32.0
MINIMAL_BASE_TOLERANCE_PX = 12.0
ALLY_REF_UV = (0.44, 0.45)
LINK_DILATE = 5
MIN_SQUAD_PX = 12
ENTRY_SETTLE_POLLS = 12      # extra captures while the battle minimap fills in
ENTRY_SETTLE_GAP_S = 0.15
DEFAULT_OPTS = {
    'squad_counts': [
        2,
        2,
        2,
        2,
        2,
        2],
    'use_summon': False,
    'summon_mode': None,
    'center_move_delay': 1.0,
    'lead_px': 40.0,
    'aim_y4': None,
    'multi_retreat': False,
    'noejeonju': False,
    'attack_keys': None,
    'aim_y': 40.0,
    'pan_dist': 0.4,
    'pan_ratio': PAN_RATIO }

def _noejeonju(io, o):
    if not o.get('noejeonju'):
        return None
    for k in ('0', 'r'):
        io.press(k)
        time.sleep(0.025)


def _squad_cycles(counts, idx):
    if not counts:
        return 2.0
    return float(counts[idx]) if idx < len(counts) else float(counts[-1])

BATTLE_PIXEL_XY = (986, 704)
BATTLE_PIXEL_SUM = 222
BATTLE_PIXEL_TOL = 20

def is_battle(frame):
    (x, y) = BATTLE_PIXEL_XY
    if frame is None or y >= frame.shape[0] or x >= frame.shape[1]:
        return False
    return abs(int(frame[y, x].sum()) - BATTLE_PIXEL_SUM) <= BATTLE_PIXEL_TOL


def minimap_center_black(mm):
    (cy, cx) = (MAP_H // 2, MAP_W // 2)
    block = mm[cy - 1:cy + 2, cx - 1:cx + 2]
    return bool((block == 0).all(axis = 2).any())


def is_main(frame):
    return vision.is_scene(frame, 'main')


# A battle that already had its attack commands issued needs ~25 s to resolve before the main screen
# returns (measured on finevt-7 2026-11-23: attack 15:49:18, main again 15:49:38); the old 100 x 0.1 s
# wait gave up after 10 s, called _stop_now and left the run dead. 600 x 0.1 s = 60 s.
RETREAT_WAIT_FRAMES = 600

def wait_for_main(io, log, max_frames = RETREAT_WAIT_FRAMES, stop = None):
    for _ in range(max_frames):
        if stop and stop():
            return False
        if is_main(io.capture()):
            return True
        time.sleep(0.1)
    log(f'퇴각실패 ({max_frames}루프 내 메인 복귀 실패)')
    return False


def crop_minimap(frame):
    return frame[MAP_Y0:MAP_Y0 + MAP_H, MAP_X0:MAP_X0 + MAP_W]

BOX_WHITE_MIN = 170
BOX_WHITE_SPREAD = 12

def _box_mask(mm):
    v = mm.astype(np.int16)
    return (v.min(axis = 2) >= BOX_WHITE_MIN) & (v.max(axis = 2) - v.min(axis = 2) <= BOX_WHITE_SPREAD)


def detect_box(mm):
    white = _box_mask(mm)
    if white.sum() < 8:
        return None
    (ys, xs) = np.where(white)
    (x0, x1, y0, y1) = (int(xs.min()), int(xs.max()), int(ys.min()), int(ys.max()))
    (clip_l, clip_r) = (x0 <= 0, x1 >= MAP_W - 1)
    (clip_t, clip_b) = (y0 <= 0, y1 >= MAP_H - 1)
    if clip_l and not clip_r:
        x0 = x1 - (BOX_W - 1)
    elif clip_r and not clip_l:
        x1 = x0 + (BOX_W - 1)
    if clip_t and not clip_b:
        y0 = y1 - (BOX_H - 1)
    elif clip_b and not clip_t:
        y1 = y0 + (BOX_H - 1)
    return {
        'x0': x0,
        'y0': y0,
        'x1': x1,
        'y1': y1,
        'cx': (x0 + x1) / 2.0,
        'cy': (y0 + y1) / 2.0,
        'w': max(1, x1 - x0),
        'h': max(1, y1 - y0) }


def _dot_mask(mm):
    black = (mm.sum(axis = 2) == 0).astype(np.uint8)
    solid = cv2.morphologyEx(black, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    interior = cv2.erode(solid, np.ones((7, 7), np.uint8))
    hsv = cv2.cvtColor(mm, cv2.COLOR_BGR2HSV)
    (s, v) = (hsv[(..., 1)], hsv[(..., 2)])
    return (s > 20) & (v > 45) & (interior > 0) & (black == 0)


def detect_squads(mm, min_px = MIN_SQUAD_PX, colors = None):
    mask = _dot_mask(mm)
    if colors is not None:
        known = np.zeros(mask.shape, dtype = bool)
        for color in colors:
            known |= (mm == color).all(axis = 2)
        mask &= known
    if not mask.any():
        return []
    pts = mm[mask]
    colors = np.unique(pts, axis = 0)
    assign = { tuple(c): i for i, c in enumerate(colors) }
    label = np.full(mm.shape[:2], -1, np.int32)
    (ys, xs) = np.where(mask)
    label[ys, xs] = [ assign[tuple(mm[y, x])] for y, x in zip(ys, xs) ]
    squads = []
    kernel = np.ones((LINK_DILATE, LINK_DILATE), np.uint8)
    for pi, rep in enumerate(colors):
        cmask = (label == pi).astype(np.uint8)
        (n, lab, _stats, _cent) = cv2.connectedComponentsWithStats(cv2.dilate(cmask, kernel), 8)
        for i in range(1, n):
            comp = (lab == i) & (cmask > 0)
            px = int(comp.sum())
            if px < min_px:
                continue
            (yy, xx) = np.nonzero(comp)
            (x0, y0, x1, y1) = (int(xx.min()), int(yy.min()), int(xx.max()), int(yy.max()))
            squads.append({
                'color': tuple((int(v) for v in rep)),
                'cx': (x0 + x1) / 2.0,
                'cy': (y0 + y1) / 2.0,
                'px': px,
                'bounds': (x0, y0, x1, y1) })
    return squads


def analyze(mm):
    box = detect_box(mm)
    squads = detect_squads(mm)
    (ally, enemies) = (None, list(squads))
    if box and squads:
        best = None
        for s in squads:
            u = (s['cx'] - box['x0']) / box['w']
            v = (s['cy'] - box['y0']) / box['h']
            if 0.0 <= u <= 1.0 and 0.0 <= v <= 1.0:
                d = (u - ALLY_REF_UV[0]) ** 2 + (v - ALLY_REF_UV[1]) ** 2
                if best is None or d < best:
                    (best, ally) = (d, s)
        if ally is not None:
            enemies = [ s for s in squads if s is not ally ]
    return {
        'box': box,
        'ally': ally,
        'enemies': enemies }

CENTER_PING_XY = {
    'left': (984, 384),
    'right': (40, 384),
    'up': (512, 624),
    'down': (512, 40) }

def _dir_side(dx, dy):
    dx *= 0.5
    if abs(dx) >= abs(dy):
        return 'right' if dx > 0 else 'left'
    return 'down' if dy > 0 else 'up'


def _ally_side(ally):
    return _dir_side(ally['cx'] - MAP_CENTER[0], ally['cy'] - MAP_CENTER[1])


def mm_dist_sq(dx, dy):
    dx *= 0.5
    return dx * dx + dy * dy


def formation_center(squads):
    if len(squads) < 3:
        return None
    cx0 = sum((s['cx'] for s in squads)) / len(squads)
    cy0 = sum((s['cy'] for s in squads)) / len(squads)
    g = {
        'up': [],
        'down': [],
        'left': [],
        'right': [] }
    for s in squads:
        g[_dir_side(s['cx'] - cx0, s['cy'] - cy0)].append(s)
    xs = [ s['cx'] for s in g['up'] + g['down'] ]
    ys = [ s['cy'] for s in g['left'] + g['right'] ]
    if g['left'] and g['right']:
        xs.append((sum((s['cx'] for s in g['left'])) / len(g['left']) + sum((s['cx'] for s in g['right'])) / len(g['right'])) / 2)
    if g['up'] and g['down']:
        ys.append((sum((s['cy'] for s in g['up'])) / len(g['up']) + sum((s['cy'] for s in g['down'])) / len(g['down'])) / 2)
    if not xs or not ys:
        return None
    return (sum(xs) / len(xs), sum(ys) / len(ys))


def _pan(io, dx, dy, scale = 1.0, *, min_delta = 1.0, min_hold = 0.0):
    steps = []
    if abs(dx) >= min_delta:
        steps.append(('right' if dx > 0 else 'left', max(min_hold, (abs(dx) / PAN_VX) * scale)))
    if abs(dy) >= min_delta:
        steps.append(('down' if dy > 0 else 'up', max(min_hold, (abs(dy) / PAN_VY) * scale)))
    if not steps:
        return {}
    steps.sort(key=lambda s: s[1])
    held = { k: t for k, t in steps }
    for k, _ in steps:
        io.hold(k)
    elapsed = 0.0
    
    try:
        for k, t in steps:
            time.sleep(max(0.0, t - elapsed))
            io.release(k)
            elapsed = t
        return held
    except Exception:
        for k, _ in steps:
            io.release(k)
        raise 



def _pan_screen(io, dx, dy):
    return _pan(io, dx * PAN_VX / PAN_SCREEN_VX, dy * PAN_VY / PAN_SCREEN_VY, min_delta = 1e-06, min_hold = PAN_SCREEN_MIN_HOLD)

PAN_SETTLE_TIMEOUT = 0.25
PAN_STABLE_FRAMES = 3
PAN_STABLE_SPAN = 0.035
PAN_STABLE_EPS = 0.5

def _valid_pan_box(mm, box):
    if not box or box['w'] < 8 or box['h'] < 8:
        return False
    white = _box_mask(mm)
    (h, w) = white.shape
    (x0, x1, y0, y1) = (int(box[k]) for k in ('x0', 'x1', 'y0', 'y1'))
    (xl, xr, yt, yb) = (max(0, x0), min(w - 1, x1), max(0, y0), min(h - 1, y1))
    if xl >= xr or yt >= yb:
        return False
    horizontal = [ white[y, xl:xr + 1].mean() for y in (y0, y1) if 0 <= y < h ]
    vertical = [ white[yt:yb + 1, x].mean() for x in (x0, x1) if 0 <= x < w ]
    return bool(horizontal and vertical and min(horizontal + vertical) >= 0.5)


def _precision_note(message):
    if not _pan_log_path:
        return None
    
    try:
        with open(_pan_log_path, 'a', encoding = 'utf-8') as f:
            f.write(f'''[{time.strftime('%H:%M:%S')}] 정밀조준 {message}\n''')
            return None
    except OSError:
        return None



def _settled_pan_frame(io, stop, diagnostics = None):
    details = diagnostics if diagnostics is not None else { }
    details.clear()
    details.update(received = 0, missing = 0, invalid = 0, changed = 0, stable = 0, elapsed_ms = 0, reason = '')
    fresh = getattr(io, 'capture_after', None)
    if not callable(fresh):
        frame = io.capture()
        return (frame, detect_box(crop_minimap(frame)) if frame is not None else None)
    started = after = time.monotonic()
    deadline = started + PAN_SETTLE_TIMEOUT
    samples = []
    while not stop():
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        after = time.monotonic()
        frame = fresh(after, timeout = min(remaining, 0.05), stop = stop)
        after = time.monotonic()
        details['missing' if frame is None else 'received'] += 1
        if frame is not None:
            details['_last_frame'] = frame
        if stop() or after > deadline:
            break
        if frame is None:
            time.sleep(min(0.005, max(0.0, deadline - after)))
            continue
        mm = crop_minimap(frame)
        box = detect_box(mm)
        if not _valid_pan_box(mm, box):
            details['invalid'] += 1
            samples.clear()
            continue
        details['_last_valid_frame'] = frame
        details['_last_valid_box'] = dict(box)
        samples.append((after, box))
        count_before = len(samples)
        while any((max((s[1][k] for s in samples)) - min((s[1][k] for s in samples)) > PAN_STABLE_EPS for k in ('cx', 'cy', 'w', 'h'))):
            samples.pop(0)
        if len(samples) < count_before:
            details['changed'] += 1
        if len(samples) >= PAN_STABLE_FRAMES and after - samples[0][0] >= PAN_STABLE_SPAN:
            details.update(stable = len(samples), elapsed_ms = (after - started) * 1000)
            _precision_note(f'''안정 프레임 {len(samples)}장, {(after - started) * 1000:.0f}ms''')
            return (frame, box)
    details.update(stable = len(samples), elapsed_ms = (time.monotonic() - started) * 1000)
    if stop():
        reason = '정지 요청'
    elif details['received'] == 0:
        reason = '새 프레임 미수신'
    elif details['invalid'] == details['received']:
        reason = '흰박스 검출 실패'
    elif details['changed']:
        reason = '박스 위치·크기 변동'
    elif details['invalid']:
        reason = '흰박스 검출 불안정'
    elif len(samples) < PAN_STABLE_FRAMES:
        reason = '새 프레임 부족'
    else:
        reason = '안정 관측 시간 부족'
    details['reason'] = reason
    _precision_note(f'''카메라 안정 프레임 확보 실패: {reason}, 수신 {details['received']}장, 미수신 {details['missing']}회, 박스 무효 {details['invalid']}장, 변동 {details['changed']}회, 안정 {len(samples)}/{PAN_STABLE_FRAMES}장, {details['elapsed_ms']:.0f}ms''')
    return (None, None)


def _pan_settle_failure_detail(details):
    if not details or not details.get('reason'):
        return ''
    return f''' [{details['reason']}, 안정 관측 {details.get('stable', 0)}/{PAN_STABLE_FRAMES}장]'''


def _entry_pan_frame(io, stop):
    details = { }
    (frame, box) = _settled_pan_frame(io, stop, diagnostics = details)
    if stop():
        details['reason'] = '정지 요청'
        return (None, None, details)
    latest = details.get('_last_frame')
    if latest is None:
        latest = frame if frame is not None else io.capture()
    if isinstance(latest, np.ndarray) and is_main(latest):
        details['reason'] = '메인화면 복귀'
        return (None, None, details)
    if stop():
        details['reason'] = '정지 요청'
        return (None, None, details)
    if box is not None:
        return (frame, box, details)
    last_frame = details.get('_last_valid_frame')
    last_box = details.get('_last_valid_box')
    if details.get('reason') in ('새 프레임 부족', '안정 관측 시간 부족') and not details.get('invalid') and not details.get('changed') and last_frame is not None and latest is last_frame and last_box is not None:
        reason = f'''{details['reason']} · 이번 팬 뒤 정상 프레임 사용'''
        return (last_frame, dict(last_box, _entry_fallback = reason), details)
    return (None, None, details)


def _predict_pan_camera(cur, held, vx, vy):
    if not isinstance(held, dict):
        return None
    durations = [ held.get(k, 0.0) for k in ('right', 'left', 'down', 'up') ]
    if not all((np.isfinite(v) and v >= 0 for v in durations)) or not all((np.isfinite(v) and v > 0 for v in (vx, vy))):
        return None
    result = [
        cur[0] + (held.get('right', 0.0) - held.get('left', 0.0)) * vx,
        cur[1] + (held.get('down', 0.0) - held.get('up', 0.0)) * vy]
    return result if all((np.isfinite(v) for v in result)) else None


def _attack_pan_frame(io, stop, cur, predicted = None):
    details = { }
    (frame, box) = _settled_pan_frame(io, stop, diagnostics = details)
    if stop():
        details['reason'] = '정지 요청'
        return (None, None, details)
    latest = details.get('_last_frame')
    if latest is None:
        latest = frame if frame is not None else io.capture()
    if isinstance(latest, np.ndarray) and is_main(latest):
        details['reason'] = '메인화면 복귀'
        return (None, None, details)
    if stop():
        details['reason'] = '정지 요청'
        return (None, None, details)
    if box is not None:
        return (frame, box, details)
    reason = details.get('reason') or '카메라 확인 부족'
    last_box = details.get('_last_valid_box')
    if last_box is not None:
        box = dict(last_box, _aim_fallback = f'''{reason} · 마지막 박스 사용''')
        return (details.get('_last_valid_frame'), box, details)
    center = predicted if predicted is not None else cur
    if not (all((np.isfinite(v) for v in center)) and -BOX_W <= center[0] <= MAP_W + BOX_W and -BOX_H <= center[1] <= MAP_H + BOX_H):
        details['reason'] = '카메라 추정 기준 없음'
        return (None, None, details)
    source = 'pan 이동량 추정' if predicted is not None else '직전 카메라 사용'
    box = dict(cx = center[0], cy = center[1], w = BOX_W - 1, h = BOX_H - 1, _camera_estimated = True, _aim_fallback = f'''{reason} · {source}''')
    return (None, box, details)


def _fourway_projection_profile(box, ally, enemies):
    if not box or not ally or not isinstance(enemies, (list, tuple)) or len(enemies) not in (2, 3) or box.get('w') != BOX_W - 1 or box.get('h') != BOX_H - 1:
        return None
    if any(('cx0' in e or 'cy0' in e for e in enemies)):
        return None
    
    try:
        raw = [(float(s['cx']), float(s['cy'])) for s in [ally, *enemies]]
    except (KeyError, TypeError, ValueError):
        return None

    if any((not np.isfinite(x) or not np.isfinite(y) or not (0 <= x < MAP_W and 0 <= y < MAP_H) for x, y in raw)):
        return None
    points = sorted(((x * 0.5, y) for x, y in raw))
    if len(set(points)) != len(points):
        return None
    pairs = [ (sum(((a[k] - b[k]) ** 2 for k in (0, 1))), a, b) for i, a in enumerate(points) for b in points[i + 1:] ]
    (distance2, a, b) = max(pairs)
    diameter = distance2 ** 0.5
    profiles = ((38.0, 43.0, 26.7, 26.1, '궁형'), (54.0, 61.0, 17.04, 16.97, '도사형'))
    chosen = next((p for p in profiles if p[0] <= diameter <= p[1]), None)
    if chosen is None:
        return None
    transverse_tolerance = 2.0
    radial_tolerance = 2.5
    if min(abs(a[0] - b[0]), abs(a[1] - b[1])) > transverse_tolerance:
        return None
    (cx, cy) = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    radius = diameter / 2
    slots = { }
    for x, y in points:
        (dx, dy) = (x - cx, y - cy)
        horizontal = abs(dx) >= abs(dy)
        (radial, transverse) = (abs(dx), abs(dy)) if horizontal else (abs(dy), abs(dx))
        if abs(radial - radius) > radial_tolerance or transverse > transverse_tolerance:
            return None
        slot = ('right' if dx > 0 else 'left') if horizontal else 'down' if dy > 0 else 'up'
        if slot in slots:
            return None
        slots[slot] = (x, y)
    for first, second in (('left', 'right'), ('up', 'down')):
        if first in slots and second in slots:
            (p, q) = (slots[first], slots[second])
            observed = sum(((p[k] - q[k]) ** 2 for k in (0, 1))) ** 0.5
            if not chosen[0] <= observed <= chosen[1]:
                return None
    return (chosen[2], chosen[3], f'''{chosen[4]} 초기간격 {diameter:.2f}px''')


def _projection_scale(o, box):
    scale = o.get('projection_scale')
    measured_zoom = box['w'] == BOX_W - 1 and box['h'] == BOX_H - 1
    if isinstance(scale, (list, tuple)) and len(scale) == 2 and measured_zoom:
        
        try:
            (x, y) = map(float, scale)
            if np.isfinite(x) and np.isfinite(y) and 1 <= x <= 100 and 1 <= y <= 100:
                return (x, y)
        except (ValueError, TypeError):
            pass

    return (FIELD_CENTER[0] * 2 / BOX_W, FIELD_CENTER[1] * 2 / BOX_H)

KEY_HOLD_S = 0.03
KEY_GAP_S = 0.03
MOVE_SETTLE_S = 0.05
HOLD_REPEAT_S = 0.05
RELEASE_GAP_S = 0.05
HOLD_AS_WAIT = False
ATTACK_KEYS_ALL = ('3', '4', '5', '6', '7', '8', '9')
ATTACK_KEYS_DEFAULT = ('3', '4', '5', '6')
ATTACK_TAIL = '2'
ATTACK_FINISH = 'e'

def normalize_attack_keys(raw) -> list:
    if raw is None:
        return list(ATTACK_KEYS_DEFAULT)
    
    try:
        want = { str(k).strip() for k in raw }
    except TypeError:
        return list(ATTACK_KEYS_DEFAULT)

    return [ k for k in ATTACK_KEYS_ALL if k in want ]


def _attack(io, x, y, hold_sec, stop = None, keys = None):
    seq = list(keys if keys is not None else ATTACK_KEYS_DEFAULT) + [
        ATTACK_TAIL]
    io.move(x, y)
    time.sleep(MOVE_SETTLE_S)
    io.move(x, y)   # land + verify again right before the casts (the guard also pins it)
    for k in seq:
        io.press('r', KEY_HOLD_S)
        time.sleep(KEY_GAP_S)
        io.press(k, KEY_HOLD_S)
        time.sleep(KEY_GAP_S)
    io.press(ATTACK_FINISH, KEY_HOLD_S)
    time.sleep(KEY_GAP_S)
    io.move(x, y)
    if HOLD_AS_WAIT:
        end = time.time() + max(0.0, float(hold_sec))
        while time.time() < end:
            if stop and stop():
                return None
            time.sleep(HOLD_REPEAT_S)
    else:
        
        try:
            io.hold('r')
            end = time.time() + max(0.0, float(hold_sec))
            while time.time() < end:
                if stop and stop():
                    return None
                io.hold('r')
                time.sleep(HOLD_REPEAT_S)
        finally:
            time.sleep(RELEASE_GAP_S)
            io.release('r')
    time.sleep(KEY_GAP_S)
    io.press(ATTACK_FINISH, KEY_HOLD_S)
    return None



def run_battle(io, opts = None, log = print, detect = None, should_stop = None, pre_retreat = None):
    o = {
        **DEFAULT_OPTS, **(opts or {}) }
    o['summon_mode'] = _config.summon_mode(o)
    o['use_summon'] = o['summon_mode'] != 'none'
    o['attack_keys'] = normalize_attack_keys(o.get('attack_keys'))
    _pan_log_begin(o)
    stop = should_stop or (lambda: False)

    
    def retreat():
        if pre_retreat:
            
            try:
                pre_retreat(io.capture())
            except Exception:
                pass

        _retreat(io)

    frame = io.capture()
    if frame is None:
        return 'no-frame'
    st = analyze(crop_minimap(frame))
    (box, ally, enemies) = (st['box'], st['ally'], st['enemies'])
    # The minimap is still fading in on the first frames of a battle: 12 of 58 saved skip frames
    # on finevt-7 had no dots at all and the rest showed partial/dim dots, so a single early frame
    # sent the run into an instant retreat (measured 2 attacks in 57 battle entries). Poll for the
    # minimap to settle before giving up.
    polls = 0
    while (not box or not ally or not enemies) and polls < ENTRY_SETTLE_POLLS and not stop():
        time.sleep(ENTRY_SETTLE_GAP_S)
        fr = io.capture()
        if fr is None:
            continue
        polls += 1
        if not is_battle(fr):
            break
        frame = fr
        st = analyze(crop_minimap(frame))
        (box, ally, enemies) = (st['box'], st['ally'], st['enemies'])
    if polls and box and ally and enemies:
        log(f'전투: 미니맵 안정화 대기 {polls}회 후 검출 성공 (적 {len(enemies)}부대)')
    if not box or not ally or not enemies:
        log(f'''전투: 검출 부족 — 퇴각·집계 (박스 {'O' if box else 'X'} / 아군 {'O' if ally else 'X'} / 적 {len(enemies)}부대)''')
        _save_skip_frame(o, frame, box, ally, enemies)
        retreat()
        if not wait_for_main(io, log, stop = stop):
            return 'stopped' if stop() else 'retreat-fail'
        return 'ok'
    _pan_log_entry(frame, box, ally, enemies)
    log(f'''전투 진입 — 적 {len(enemies)}부대''')
    _lock_ally_origin(ally)
    if o.get('multi_retreat') and len(enemies) >= 4:
        log(f'''다부대 즉시 퇴각 (적 {len(enemies)}부대)''')
        retreat()
        if not wait_for_main(io, log, stop = stop):
            return 'stopped' if stop() else 'retreat-fail'
        return 'ok'
    pan_scale = max(0.5, min(2.0, 65.0 / box['w']))
    pan_scale *= o['pan_dist'] / PAN_BASE
    u_ref = 0.5 + (ally['cx'] - box['cx']) / BOX_W
    v_ref = 0.5 + (ally['cy'] - box['cy']) / BOX_H
    multi = len(enemies) >= 4
    _enable_fragment_tracking(ally, enemies, multi)
    (kx, ky) = _projection_scale(o, box)
    profile = None if multi else _fourway_projection_profile(box, ally, enemies)
    o['_minimal_pan'] = profile is not None
    if profile:
        (kx, ky, profile_name) = profile
        log(f'''4방향 자동 팬 — {profile_name}, 타격영역 진입 / 추가 추격 최대 1회''')
        _precision_note(f'''자동 프로필 {profile_name}, 공통 화면속도 {PAN_SCREEN_VX:.0f}/{PAN_SCREEN_VY:.0f}px/s''')
    elif not multi:
        _precision_note('진입 배치 프로필 미확정 — 기존 몹별 팬/배율 유지')
    _precision_note(f'''v1 배율 x={kx:.3f} y={ky:.3f} 초기기준({ally['cx'] - box['cx']:.2f},{ally['cy'] - box['cy']:.2f})''')
    
    def unstable_entry(details):
        if stop() or details.get('reason') == '정지 요청':
            return 'stopped'
        if details.get('reason') == '메인화면 복귀':
            log('진입 확인 중 메인화면 복귀 — 전투 종료')
            return 'ok'
        log(f'''진입 팬 안정화 실패{_pan_settle_failure_detail(details)} — 소환/공격 없이 퇴각''')
        retreat()
        if not wait_for_main(io, log, stop = stop):
            return 'stopped' if stop() else 'retreat-fail'
        return 'stopped' if stop() else 'ok'

    
    def note_entry_frame(settled_box, details):
        if settled_box.get('_entry_fallback'):
            message = f'''진입 화면 확인 보완{_pan_settle_failure_detail(details)} — 확보한 정상 프레임으로 계속'''
            log(message)
            _precision_note(message)
            return None

    summon_tgt = None
    ping_at = time.time()
    if multi:
        _noejeonju(io, o)
        _pan(io, MAP_CENTER[0] - ally['cx'], MAP_CENTER[1] - ally['cy'], pan_scale)
        if callable(getattr(io, 'capture_after', None)):
            (_, settled_box, settle_details) = _entry_pan_frame(io, stop)
            if settled_box is None:
                return unstable_entry(settle_details)
            note_entry_frame(settled_box, settle_details)
        io.move(*FIELD_CENTER)
        time.sleep(0.05)
        for k in '1mq2w' if o['use_summon'] else '1mq2':
            io.press(k)
            time.sleep(0.025)
    else:
        _noejeonju(io, o)
        io.move(*CENTER_PING_XY[_ally_side(ally)])
        time.sleep(0.05)
        for k in '1mq2':
            io.press(k)
            time.sleep(0.025)
        if o['use_summon']:
            center_summon = bool(o.get('summon_center'))
            summon_tgt = None if center_summon else max(enemies, key=lambda e: mm_dist_sq(e['cx'] - MAP_CENTER[0], e['cy'] - MAP_CENTER[1]))
            if o['_minimal_pan']:
                _pan_screen(io, (MAP_CENTER[0] - ally['cx']) * kx, (MAP_CENTER[1] - ally['cy']) * ky)
            else:
                _pan(io, MAP_CENTER[0] - ally['cx'], MAP_CENTER[1] - ally['cy'], pan_scale)
            sx = sy = None
            (frame2, settled_box, settle_details) = _entry_pan_frame(io, stop)
            if settled_box is None and (callable(getattr(io, 'capture_after', None)) or settle_details.get('reason') in ('정지 요청', '메인화면 복귀')):
                return unstable_entry(settle_details)
            if settled_box is not None:
                note_entry_frame(settled_box, settle_details)
            if frame2 is not None:
                mm2 = crop_minimap(frame2)
                box2 = settled_box
                if box2:
                    fc = formation_center(detect_squads(mm2))
                    (tx, ty) = fc if fc else MAP_CENTER
                    log('소환 기준 — ' + ('부대 십자 중앙' if fc else '부대<3, 맵중앙 폴백'))
                    sx = FIELD_CENTER[0] + (tx - box2['cx'] - (u_ref - 0.5) * BOX_W) * kx
                    sy = FIELD_CENTER[1] + (ty - box2['cy'] - (v_ref - 0.5) * BOX_H) * ky
            if sx is None:
                (sx, sy) = FIELD_CENTER
            if not center_summon:
                side = _dir_side(summon_tgt['cx'] - MAP_CENTER[0], summon_tgt['cy'] - MAP_CENTER[1])
                if side == 'left':
                    sx -= 400
                elif side == 'right':
                    sx += 400
                elif side == 'up':
                    sy -= 200
                else:
                    sy += 200
            sx = min(SUMMON_BOUNDS[2], max(SUMMON_BOUNDS[0], sx))
            sy = min(SUMMON_BOUNDS[3], max(SUMMON_BOUNDS[1], sy))
            io.move(int(round(sx)), int(round(sy)))
            time.sleep(0.05)
            io.press('w')
    time.sleep(max(0.0, o['center_move_delay'] - (time.time() - ping_at)))
    current_box = _rescan(io, list(enemies), ally)
    for e in enemies:
        (e['cx0'], e['cy0']) = (e['cx'], e['cy'])
    if multi:
        order = sorted(enemies, key=lambda e: mm_dist_sq(e['cx'] - ally['cx'], e['cy'] - ally['cy']))
        if summon_tgt is not None:
            s_side = _dir_side(summon_tgt['cx'] - MAP_CENTER[0], summon_tgt['cy'] - MAP_CENTER[1])
            rest = [ e for e in order if e is not summon_tgt ]
            other_side = [ e for e in rest if _dir_side(e['cx'] - MAP_CENTER[0], e['cy'] - MAP_CENTER[1]) != s_side ]
            same_side = [ e for e in rest if e not in other_side ]
            order = other_side + same_side + [
                summon_tgt]
        (remaining, greedy) = (order, False)
    else:
        remaining = [ e for e in enemies if e is not summon_tgt ]
        greedy = True
    ref = (ally['cx'], ally['cy'])
    cur = [
        current_box['cx'],
        current_box['cy']] if current_box else [
        MAP_CENTER[0],
        MAP_CENTER[1]]
    o['_camera_estimated'] = not bool(current_box)
    total = len(enemies)
    order_idx = 0
    while order_idx < total:
        if stop():
            log('정지 명령 — 즉시 퇴각')
            retreat()
            return 'stopped'
        if order_idx > 0:
            pending = list(remaining)
            if greedy and summon_tgt is not None:
                pending.append(summon_tgt)
            current_box = _rescan(io, pending, ally)
            if current_box:
                cur = [
                    current_box['cx'],
                    current_box['cy']]
                o['_camera_estimated'] = False
        if remaining:
            if greedy:
                enemy = min(remaining, key=lambda e: mm_dist_sq(e['cx'] - ref[0], e['cy'] - ref[1]))
                remaining.remove(enemy)
            else:
                enemy = remaining.pop(0)
        else:
            enemy = summon_tgt
        cycles = _squad_cycles(o['squad_counts'], order_idx)
        lead_mult = 0.0 if enemy is summon_tgt and o['summon_mode'] == 'taunt' else 1.0
        cur = _aim_minimap(io, enemy, ally, u_ref, v_ref, pan_scale, kx, ky, o, cycles, log, order_idx, lead_mult, stop, cur, multi, detect)
        if o.get('_battle_main_seen') and not stop():
            return 'ok'
        ref = (enemy['cx'], enemy['cy'])
        order_idx += 1
    retreat()
    if stop():
        return 'stopped'
    if not wait_for_main(io, log, stop = stop):
        return 'stopped' if stop() else 'retreat-fail'
    return 'ok'

CROSS_DIST = 35.0
CROSS_RATIO = 0.9

def _approach(io, enemy, u_ref, v_ref, pan_scale, kx, ky, log, idx, ratio = PAN_RATIO):
    frame = io.capture()
    box = detect_box(crop_minimap(frame)) if frame is not None else None
    if not box:
        log(f'''{idx + 1}부대: 흰박스 미검출 — 팬 생략''')
        return (FIELD_CENTER, None)
    goal_x = enemy['cx'] - (u_ref - 0.5) * BOX_W
    goal_y = enemy['cy'] - (v_ref - 0.5) * BOX_H
    (dx, dy) = (goal_x - box['cx'], goal_y - box['cy'])
    if ratio < 1.0 and max(abs(dx) * 0.5, abs(dy)) >= CROSS_DIST:
        ratio = CROSS_RATIO
    _pan(io, ratio * dx, ratio * dy, pan_scale)
    ex = FIELD_CENTER[0] + (1.0 - ratio) * dx * kx
    ey = FIELD_CENTER[1] + (1.0 - ratio) * dy * ky
    moved = dict(box)
    moved['cx'] = box['cx'] + ratio * dx
    moved['cy'] = box['cy'] + ratio * dy
    return ((ex, ey), moved)

AIM_Y_OFFSET = 40.0
AIM_BOUNDS = (20.0, 20.0, 1004.0, 630.0)
ATTACK_AIM_OFFSET = (20.0, -10.0)
ALLY_SCREEN_R = 150.0
AIM_ROI_FRAC = 0.75
AIM_DIR_EPS = 40.0
MOB_CHASE_ATTEMPTS = 2
CHASE_JUMP_R = 12.0
BOSS_GATE_X = 360.0
BOSS_GATE_Y = 180.0
AIM_LEAD_XFRAC = 2.0

def _clamp_aim(x, y):
    (x0, y0, x1, y1) = AIM_BOUNDS
    return (min(x1, max(x0, x)), min(y1, max(y0, y)))


def _adjust_attack_aim(x, y):
    (dx, dy) = ATTACK_AIM_OFFSET
    return _clamp_aim(x + dx, y + dy)

DEBUG_KEEP = 600
SKIP_KEEP = 60

def _save_skip_frame(o, frame, box, ally, enemies):
    d = o.get('skip_debug_dir')
    if not d or frame is None:
        return None
    try:
        os.makedirs(d, exist_ok = True)
        tag = f'''b{1 if box else 0}a{1 if ally else 0}e{len(enemies)}'''
        cv2.imwrite(os.path.join(d, time.strftime(f'''skip_%Y%m%d_%H%M%S_{tag}.png''')), frame)
        prune_dir(d, SKIP_KEEP, 'skip_*.png')
        return None
    except Exception:
        return None



def prune_dir(d, keep, pattern = '*.png'):
    
    try:
        files = sorted(glob.glob(os.path.join(d, pattern)))
        for f in files[:-keep] if len(files) > keep else []:
            os.remove(f)
        return None
    except Exception:
        return None


AIM_DEBUG_KEEP = 50

def _save_aim_debug(o, frame, idx, ax, ay, base, raw = None, chosen = None, ally_xy = None, avoid_xy = None, mode = '', info = ''):
    d = o.get('aim_debug_dir')
    if not d or frame is None:
        return None
    
    try:
        os.makedirs(d, exist_ok = True)
        vis = frame.copy()
        if o.get('_minimal_pan'):
            (x0, y0, x1, y1) = map(int, MINIMAL_AIM_BOUNDS)
            cv2.rectangle(vis, (x0, y0), (x1, y1), (255, 200, 0), 1)
        if ally_xy is not None:
            cv2.circle(vis, (int(ally_xy[0]), int(ally_xy[1])), int(ALLY_SCREEN_R), (0, 255, 255), 1)
        if avoid_xy is not None:
            cv2.circle(vis, (int(avoid_xy[0]), int(avoid_xy[1])), int(ALLY_SCREEN_R), (0, 165, 255), 1)
        for (x, y), cf in raw or []:
            cv2.circle(vis, (int(x), int(y)), 7, (0, 255, 0), 2)
            cv2.putText(vis, f'''{cf:.2f}''', (int(x) + 8, int(y) - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0), 1)
        if chosen is not None:
            cv2.circle(vis, (int(chosen[0]), int(chosen[1])), 12, (255, 255, 0), 2)
            cv2.line(vis, (int(chosen[0]), int(chosen[1])), (int(ax), int(ay)), (0, 0, 255), 1)
        cv2.drawMarker(vis, (int(base[0]), int(base[1])), (160, 160, 160), cv2.MARKER_CROSS, 18, 2)
        cv2.drawMarker(vis, (int(ax), int(ay)), (0, 0, 255), cv2.MARKER_CROSS, 26, 2)
        info = ''.join((ch for ch in info if ord(ch) < 128)).strip()
        txt = f'''sq{idx + 1} [{mode}] {info}'''[:110]
        cv2.putText(vis, txt, (8, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 3, cv2.LINE_AA)
        cv2.putText(vis, txt, (8, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 255), 1, cv2.LINE_AA)
        cv2.imwrite(os.path.join(d, time.strftime(f'''aim_%Y%m%d_%H%M%S_sq{idx + 1}_{mode}.png''')), vis)
        prune_dir(d, AIM_DEBUG_KEEP)
        return None
    except Exception:
        return None



def _save_debug(o, frame, idx, ax, ay, tag = ''):
    dbg = o.get('debug_dir')
    if not dbg or frame is None:
        return None
    
    try:
        os.makedirs(dbg, exist_ok = True)
        name = time.strftime(f'''atk_%Y%m%d_%H%M%S_sq{idx + 1}_x{int(ax)}y{int(ay)}{tag}.png''')
        cv2.imwrite(os.path.join(dbg, name), frame)
        prune_dir(dbg, o.get('debug_keep', DEBUG_KEEP))
        return None
    except Exception:
        return None



def _attack_target(io, enemy, ally, kx, ky, o, cycles, log, idx, detect = None, stop = None, base = None, fallback = True, lead_mult = 1.0, avoid = None, box_hint = None, multi = False):
    (bx, by) = base if base is not None else FIELD_CENTER
    (ax, ay) = (bx, by)
    frame = io.capture()
    note = ''
    found = detect is None
    raw_dets = []
    ally_xy = avoid_xy = chosen = None
    if detect is not None and frame is not None:
        
        try:
            (coords, confs) = detect(frame)
        except Exception:
            coords = confs = None
        n_raw = 0 if coords is None else len(coords)
        if n_raw:
            raw_dets = [ ((float(x), float(y)), float(c)) for (x, y), c in zip(coords.tolist(), confs.tolist()) ]
        if coords is not None and len(coords):
            box2 = detect_box(crop_minimap(frame)) or box_hint
            if box2 is not None:
                asx = FIELD_CENTER[0] + (ally['cx'] - box2['cx']) * kx
                asy = FIELD_CENTER[1] + (ally['cy'] - box2['cy']) * ky
                ally_xy = (asx, asy)
                da = (coords[:, 0] - asx) ** 2 + (coords[:, 1] - asy) ** 2
                keep = da > ALLY_SCREEN_R ** 2
                (coords, confs) = (coords[keep], confs[keep])
                if avoid is not None and len(coords):
                    vx = FIELD_CENTER[0] + (avoid['cx'] - box2['cx']) * kx
                    vy = FIELD_CENTER[1] + (avoid['cy'] - box2['cy']) * ky
                    avoid_xy = (vx, vy)
                    dv = (coords[:, 0] - vx) ** 2 + (coords[:, 1] - vy) ** 2
                    keep = dv > ALLY_SCREEN_R ** 2
                    (coords, confs) = (coords[keep], confs[keep])
            else:
                coords = coords[:0]
                note = ' — 흰박스 미검출로 아군 판별 불가, 보류'
        if coords is not None and len(coords):
            keep = (coords[:, 0] >= _det.GATE_X[0]) & (coords[:, 0] <= _det.GATE_X[1]) & (coords[:, 1] >= _det.GATE_Y[0]) & (coords[:, 1] <= _det.GATE_Y[1])
            (coords, confs) = (coords[keep], confs[keep])
            if not len(coords):
                note = ' — 검출 전부 조준 게이트 밖, 기대점 폴백'
        if coords is not None and len(coords):
            (gx0, gx1) = _det.GATE_X
            (gy0, gy1) = _det.GATE_Y
            (bw, bh) = (AIM_ROI_FRAC * (gx1 - gx0), AIM_ROI_FRAC * (gy1 - gy0))
            if multi:
                (cxg, cyg) = ((gx0 + gx1) / 2.0, (gy0 + gy1) / 2.0)
                (rx0, rx1) = (cxg - bw / 2, cxg + bw / 2)
                (ry0, ry1) = (cyg - bh / 2, cyg + bh / 2)
            else:
                (cx, cy) = FIELD_CENTER
                (rx0, rx1) = (gx0, gx0 + bw) if bx < cx - AIM_DIR_EPS else (gx1 - bw, gx1) if bx > cx + AIM_DIR_EPS else (gx0, gx1)
                (ry0, ry1) = (gy0, gy0 + bh) if by < cy - AIM_DIR_EPS else (gy1 - bh, gy1) if by > cy + AIM_DIR_EPS else (gy0, gy1)
            inb = (coords[:, 0] >= rx0) & (coords[:, 0] <= rx1) & (coords[:, 1] >= ry0) & (coords[:, 1] <= ry1)
            if inb.any():
                (coords, confs) = (coords[inb], confs[inb])
        if coords is not None and len(coords):
            i = int(np.argmax(confs))
            (ax, ay) = (float(coords[i, 0]), float(coords[i, 1]))
            chosen = (ax, ay)
            note = f''' — YOLO 부대 조준 (conf {float(confs[i]):.2f}, {len(coords)}건 중 최고)'''
            found = True
        elif n_raw:
            if not note:
                note = f''' — 검출 {n_raw}건 전부 아군 판정, 기대점 폴백'''
        else:
            note = ' — YOLO 미검출, 기대점 폴백'
    if not found and not fallback:
        _save_debug(o, frame, idx, bx, by, tag = '_miss')
        _save_aim_debug(o, frame, idx, bx, by, (bx, by), raw = raw_dets, ally_xy = ally_xy, avoid_xy = avoid_xy, mode = 'MISS', info = note.strip(' —'))
        return False
    side = _dir_side(enemy.get('cx0', enemy['cx']) - MAP_CENTER[0], enemy.get('cy0', enemy['cy']) - MAP_CENTER[1])
    a4 = o.get('aim_y4')
    if a4 and not multi:
        ay += {
            'up': a4[0],
            'down': a4[1],
            'left': a4[2],
            'right': a4[3] }[side]
    else:
        ay += o.get('aim_y', AIM_Y_OFFSET)
    lead = o['lead_px'] * lead_mult
    if lead > 0:
        if multi or not o.get('use_summon'):
            dx = (ally['cx'] - enemy.get('cx0', enemy['cx'])) * kx
            dy = (ally['cy'] - enemy.get('cy0', enemy['cy'])) * ky
            (wx, wy) = (dx * 2.0, dy * 1.0)
            n = (wx * wx + wy * wy) ** 0.5
            if n > 1e-06:
                ax += lead * wx / n
                ay += lead * wy / n
        else:
            (ox, oy) = {
                'up': (0, 1),
                'down': (0, -1),
                'right': (-2, 0),
                'left': (2, 0) }[side]
            ax += lead * ox
            ay += lead * oy
    (ax, ay) = _adjust_attack_aim(ax, ay)
    log(f'''{idx + 1}부대 공격{note}''')
    _attack(io, int(round(ax)), int(round(ay)), cycles, stop, o.get('attack_keys'))
    _save_debug(o, frame, idx, ax, ay)
    mode = 'YOLO' if chosen is not None else 'EXPECT'
    dy = ay - (chosen[1] if chosen is not None else by)
    _save_aim_debug(o, frame, idx, ax, ay, (bx, by), raw = raw_dets, chosen = chosen, ally_xy = ally_xy, avoid_xy = avoid_xy, mode = mode, info = f'''{side} dy{dy:+.0f}{note}''')
    return True

RESCAN_ALLY_R = 8.0
ALLY_ORIGIN_PAD = 2.0
ALLY_TRACK_JUMP_R = 12.0
FRAGMENT_TRACK_R = 12.0
FRAGMENT_LINK_R = 4.0

def _enable_fragment_tracking(ally, enemies, multi = False):
    colors = [ tuple(e['color']) for e in enemies ]
    ally_color = tuple(ally['color'])
    for enemy, color in zip(enemies, colors):
        enemy['_merge_fragments'] = not multi and color != ally_color and colors.count(color) == 1


def _update_enemy_track(enemy, observed):
    for key in ('cx', 'cy', 'bounds', 'px'):
        if key in observed:
            enemy[key] = observed[key]


def _merge_enemy_fragments(squads, targets):
    result = list(squads)
    target_colors = [ tuple(e['color']) for e in targets ]
    for enemy in targets:
        color = tuple(enemy['color'])
        if not enemy.get('_merge_fragments') or target_colors.count(color) != 1:
            continue
        near = [ i for i, s in enumerate(result) if tuple(s['color']) == color
            and mm_dist_sq(s['cx'] - enemy['cx'], s['cy'] - enemy['cy']) <= FRAGMENT_TRACK_R ** 2 ]
        if len(near) < 2:
            continue
        seed = min(near, key=lambda i: mm_dist_sq(result[i]['cx'] - enemy['cx'], result[i]['cy'] - enemy['cy']))
        
        def bounds(s):
            return s.get('bounds', (s['cx'], s['cy'], s['cx'], s['cy']))

        (x0, y0, x1, y1) = bounds(result[seed])
        joined = []
        for i in near:
            (a0, b0, a1, b1) = bounds(result[i])
            gap_x = max(0.0, x0 - a1, a0 - x1)
            gap_y = max(0.0, y0 - b1, b0 - y1)
            if mm_dist_sq(gap_x, gap_y) <= FRAGMENT_LINK_R ** 2:
                joined.append(i)
        if len(joined) < 2:
            continue
        boxes = [ bounds(result[i]) for i in joined ]
        extent = (min((b[0] for b in boxes)), min((b[1] for b in boxes)), max((b[2] for b in boxes)), max((b[3] for b in boxes)))
        merged = dict(result[seed], bounds = extent, cx = (extent[0] + extent[2]) / 2.0, cy = (extent[1] + extent[3]) / 2.0, px = sum((result[i]['px'] for i in joined)), _fragment_seed = (result[seed]['cx'], result[seed]['cy']))
        _precision_note(f'''부대 조각 {len(joined)}개 재결합 색={color} 점={merged['px']} 중점({merged['cx']:.1f},{merged['cy']:.1f})''')
        result = [merged if i == seed else s for i, s in enumerate(result) if i == seed or i not in joined]
    return result


def _match(squads, color, x, y, tol = 0):
    (best, bestd) = (None, 1e+18)
    for s in squads:
        if sum((abs(a - b) for a, b in zip(s['color'], color))) > tol:
            continue
        (sx, sy) = s.get('_fragment_seed', (s['cx'], s['cy']))
        d = mm_dist_sq(sx - x, sy - y)
        if d < bestd:
            (bestd, best) = (d, s)
    return best


def _lock_ally_origin(ally):
    if '_origin' not in ally:
        (x, y) = (ally['cx'], ally['cy'])
        ally['_origin'] = (x, y, tuple(ally['color']), tuple(ally.get('bounds', (x, y, x, y))))
        ally['_tracked_points'] = [
            (x, y)]
    return ally['_origin']


def _enemy_candidates(mm, ally, targets):
    (ox, oy, ally_color, bounds) = _lock_ally_origin(ally)
    colors = { tuple(e['color']) for e in targets } | {
        ally_color}
    squads = detect_squads(mm, min_px = 1, colors = colors)
    (x0, y0, x1, y1) = bounds
    
    def at_origin(s):
        return (s['cx'] - ox) ** 2 + (s['cy'] - oy) ** 2 <= RESCAN_ALLY_R ** 2 or (x0 - ALLY_ORIGIN_PAD <= s['cx'] <= x1 + ALLY_ORIGIN_PAD and y0 - ALLY_ORIGIN_PAD <= s['cy'] <= y1 + ALLY_ORIGIN_PAD)

    previous = ally['_tracked_points']
    allied = []
    for s in squads:
        if s['color'] != ally_color:
            continue
        d = min(mm_dist_sq(s['cx'] - ax, s['cy'] - ay) for ax, ay in previous)
        if at_origin(s) or d <= ALLY_TRACK_JUMP_R ** 2 and all((d < mm_dist_sq(s['cx'] - e['cx'], s['cy'] - e['cy']) for e in targets if tuple(e['color']) == ally_color)):
            allied.append(s)
    if allied:
        ally['_tracked_points'] = [ (s['cx'], s['cy']) for s in allied ]
    candidates = [ s for s in squads if not (s['color'] == ally_color and (at_origin(s) or any(((s['cx'] - ax) ** 2 + (s['cy'] - ay) ** 2 <= RESCAN_ALLY_R ** 2 for ax, ay in ally['_tracked_points'])))) ]
    return _merge_enemy_fragments(candidates, targets)


def _rescan(io, remaining, ally):
    frame = io.capture()
    if frame is None:
        return None
    mm = crop_minimap(frame)
    box = detect_box(mm)
    cands = _enemy_candidates(mm, ally, remaining)
    for enemy in remaining:
        m = _match(cands, enemy['color'], enemy['cx'], enemy['cy'])
        if m:
            _update_enemy_track(enemy, m)
            cands.remove(m)
    return box

PAN_KEEP = 20
_pan_log_path = None

def _log_aim(idx, base_ax, base_ay, after_aimy, after_lead, final, lead, mode):
    if not _pan_log_path:
        return None
    
    try:
        with open(_pan_log_path, 'a', encoding = 'utf-8') as f:
            f.write(f'''[{time.strftime('%H:%M:%S')}] {idx + 1}부대 타격점  매핑({base_ax:6.1f},{base_ay:6.1f}) -> aim_y({after_aimy[0]:6.1f},{after_aimy[1]:6.1f}) -> lead {mode} {lead:.0f}px ({after_lead[0] - after_aimy[0]:+6.1f},{after_lead[1] - after_aimy[1]:+6.1f}) -> 최종({final[0]:6.1f},{final[1]:6.1f})\n''')
            return None
    except Exception:
        return None



def _pan_log_entry(frame, box, ally, enemies):
    if not _pan_log_path:
        return None
    
    try:
        a = f'''({ally['cx']:.0f},{ally['cy']:.0f})''' if ally else 'X'
        es = '  '.join((f'''적{i + 1}({e['cx']:.0f},{e['cy']:.0f})px{e['px']}''' for i, e in enumerate(enemies)))
        with open(_pan_log_path, 'a', encoding = 'utf-8') as f:
            f.write(f'''[{time.strftime('%H:%M:%S')}] 진입  박스cx={box['cx']:.0f},cy={box['cy']:.0f} w={box['w']}  아군{a}  {es}\n''')
        if frame is not None:
            cv2.imwrite(_pan_log_path[:-4] + '_entry.png', crop_minimap(frame))
            return None
        return None
    except Exception:
        return None



def _pan_log_begin(o):
    global _pan_log_path, _pan_log_path, _pan_log_path
    _pan_log_path = None
    d = o.get('pan_debug_dir')
    if not d:
        return None
    
    try:
        os.makedirs(d, exist_ok = True)
        _pan_log_path = os.path.join(d, time.strftime('pan_%Y%m%d_%H%M%S.txt'))
        prune_dir(d, PAN_KEEP, 'pan_*.txt')
        prune_dir(d, PAN_KEEP, 'pan_*_entry.png')
        return None
    except Exception:
        _pan_log_path = None
        return None



def _log_pan(o, log, idx, want_dx, want_dy, got_dx, got_dy, held, scale, target = None, cam_before = None, cam_after = None):
    if not isinstance(held, dict) or not _pan_log_path:
        return None
    parts = []
    for ax, want, got, key_pair in (('x', want_dx, got_dx, ('left', 'right')), ('y', want_dy, got_dy, ('up', 'down'))):
        t = held.get(key_pair[0], 0.0) or held.get(key_pair[1], 0.0)
        if t <= 0:
            continue
        v = abs(got) / t
        r = abs(got) / abs(want) if abs(want) >= 1 else float('nan')
        parts.append(f'''{ax}: 요청{want:+7.1f} 실제{got:+7.1f} ({r:4.2f}배) 홀드{t:5.2f}s -> {v:6.1f}px/s''')
    if not parts:
        return None
    where = ''
    if target and cam_before and cam_after:
        where = f'''  [목표({target[0]:.0f},{target[1]:.0f}) 카메라({cam_before[0]:.0f},{cam_before[1]:.0f})->({cam_after[0]:.0f},{cam_after[1]:.0f})]'''
    
    try:
        with open(_pan_log_path, 'a', encoding = 'utf-8') as f:
            f.write(f'''[{time.strftime('%H:%M:%S')}] {idx + 1}부대 scale{scale:4.2f}  ''' + '  |  '.join(parts) + where + '\n')
            return None
    except Exception:
        return None



def _minimal_pan_delta(base, final):
    if not all((np.isfinite(v) for v in (*base, *final))):
        return None
    result = []
    for axis, lo, hi in ((0, MINIMAL_AIM_BOUNDS[0], MINIMAL_AIM_BOUNDS[2]), (1, MINIMAL_AIM_BOUNDS[1], MINIMAL_AIM_BOUNDS[3])):
        if lo <= final[axis] <= hi:
            if lo - MINIMAL_BASE_TOLERANCE_PX <= base[axis] <= hi + MINIMAL_BASE_TOLERANCE_PX:
                result.append(0.0)
                continue
        (low, high) = sorted((base[axis], final[axis]))
        (min_delta, max_delta) = (high - hi, low - lo)
        if min_delta > max_delta:
            return None
        if min_delta <= 0 <= max_delta:
            delta = 0.0
        elif min_delta > 0:
            delta = min(max_delta, min_delta + MINIMAL_PAN_INSET)
        else:
            delta = max(min_delta, max_delta - MINIMAL_PAN_INSET)
        result.append(delta)
    return tuple(result)


def _nearest_attack_point(x, y):
    if not all((np.isfinite(v) for v in (x, y))):
        return None
    (x0, y0, x1, y1) = MINIMAL_AIM_BOUNDS
    return (min(x1, max(x0, x)), min(y1, max(y0, y)))


def _note_boundary_attack(log, idx, raw, final):
    if final != raw:
        log(f'''{idx + 1}부대 추격 후 범위 보정 — ({raw[0]:.1f},{raw[1]:.1f}) → ({final[0]:.1f},{final[1]:.1f})''')
        _precision_note(f'''{idx + 1}부대 경계 조준 원래 클릭({raw[0]:.1f},{raw[1]:.1f}) 최종({final[0]:.1f},{final[1]:.1f}) 영역={MINIMAL_AIM_BOUNDS}''')
        return None


def _select_boss_aim(frame, detect, expected, ally_xy):
    
    try:
        coords = detect(frame) if frame is not None and detect is not None else None
    except Exception:
        coords = None
    if coords is None or not len(coords):
        return None
    (ax, ay) = expected
    (asx, asy) = ally_xy
    candidates = [ (float(c[0]), float(c[1])) for c in coords if (float(c[0]) - asx) ** 2 + (float(c[1]) - asy) ** 2 > ALLY_SCREEN_R ** 2
        and abs(float(c[0]) - ax) <= BOSS_GATE_X
        and abs(float(c[1]) - ay) <= BOSS_GATE_Y ]
    return min(candidates, key=lambda p: (p[0] - ax) ** 2 + (p[1] - ay) ** 2) if candidates else None


def _position_for_attack(io, enemy, ally, u_ref, v_ref, kx, ky, o, log, idx, lead_mult, stop, cur, detect = None):
    pans = 0
    hold_total = 0.0
    pending = None
    predicted = None
    while not stop():
        (frame, box, settle_details) = _attack_pan_frame(io, stop, cur, predicted)
        if box is None:
            if settle_details.get('reason') == '메인화면 복귀':
                o['_battle_main_seen'] = True
            log(f'''{idx + 1}부대 조준 중단{_pan_settle_failure_detail(settle_details)} — 이번 부대 공격 생략''')
            return (cur, None, None)
        predicted = None
        cur = [
            box['cx'],
            box['cy']]
        o['_camera_estimated'] = bool(box.get('_camera_estimated'))
        if pending is not None:
            (dx, dy, held, before, target, before_observed) = pending
            if before_observed and not box.get('_camera_estimated'):
                _log_pan(o, log, idx, dx / kx, dy / ky, cur[0] - before[0], cur[1] - before[1], held, 1.0, target = target, cam_before = before, cam_after = cur)
            pending = None
        if stop():
            return (cur, None, None)
        if box['w'] != BOX_W - 1 or box['h'] != BOX_H - 1:
            log(f'''{idx + 1}부대 카메라 줌 변경 — 이번 부대 공격 생략''')
            return (cur, None, None)
        (tx, ty) = (enemy['cx'], enemy['cy'])
        candidates = _enemy_candidates(crop_minimap(frame), ally, [
            enemy]) if frame is not None else []
        target = _match(candidates, enemy.get('color'), tx, ty)
        if not target or mm_dist_sq(target['cx'] - tx, target['cy'] - ty) > CHASE_JUMP_R ** 2:
            why = '적 재검출 없음' if not target else '적 위치 급변 후보 제외'
            box = dict(box, _aim_fallback = ' · '.join(filter(None, (box.get('_aim_fallback'), f'''{why}, 마지막 적 좌표 사용'''))))
        else:
            _update_enemy_track(enemy, target)
        base = (FIELD_CENTER[0] + (enemy['cx'] - cur[0] - (u_ref - 0.5) * BOX_W) * kx, FIELD_CENTER[1] + (enemy['cy'] - cur[1] - (v_ref - 0.5) * BOX_H) * ky)
        boss_aim = None
        if frame is not None and o.get('boss') and detect is not None:
            ally_xy = (FIELD_CENTER[0] + (ally['cx'] - cur[0] - (u_ref - 0.5) * BOX_W) * kx, FIELD_CENTER[1] + (ally['cy'] - cur[1] - (v_ref - 0.5) * BOX_H) * ky)
            boss_aim = _select_boss_aim(frame, detect, base, ally_xy)
            if stop():
                return (cur, None, None)
        if boss_aim is not None:
            after_lead = boss_aim
        else:
            (base, _, after_lead, _, _) = _attack_mapping(enemy, ally, cur, u_ref, v_ref, kx, ky, o, lead_mult, False)
        final = (after_lead[0] + ATTACK_AIM_OFFSET[0], after_lead[1] + ATTACK_AIM_OFFSET[1])
        delta = _minimal_pan_delta(base, final)
        if pans >= MOB_CHASE_ATTEMPTS and delta != (0.0, 0.0) and all((np.isfinite(v) for v in (*base, *final))):
            return (cur, frame, dict(box, _boss_aim = boss_aim, _boundary_aim = True))
        if delta is None:
            log(f'''{idx + 1}부대 조준 보정이 타격영역 초과 — 이번 부대 공격 생략''')
            return (cur, None, None)
        if delta == (0.0, 0.0):
            detail = '팬 없음' if pans == 0 else f'''팬 {pans}회, 홀드 {hold_total:.3f}s'''
            log(f'''{idx + 1}부대 타격영역 확보 — {detail}''')
            _precision_note(f'''{idx + 1}부대 최소팬 완료 {detail} 적({base[0]:.1f},{base[1]:.1f}) 클릭({final[0]:.1f},{final[1]:.1f}) 영역={MINIMAL_AIM_BOUNDS} 중점여유={MINIMAL_BASE_TOLERANCE_PX:.0f}px''')
            return (cur, frame, dict(box, _boss_aim = boss_aim))
        if stop():
            return (cur, None, None)
        held = _pan_screen(io, *delta)
        pans += 1
        hold_total += max(held.values(), default = 0.0)
        predicted = _predict_pan_camera(cur, held, PAN_SCREEN_VX / kx, PAN_SCREEN_VY / ky)
        pending = (*delta, held, list(cur), (enemy['cx'], enemy['cy']), not box.get('_camera_estimated'))
        _precision_note(f'''{idx + 1}부대 {'첫 팬' if pans == 1 else '추가 추격 1/1'} 화면px({delta[0]:.1f},{delta[1]:.1f}) 홀드={held}''')
    return (cur, None, None)


def _attack_mapping(enemy, ally, cur, u_ref, v_ref, kx, ky, o, lead_mult, multi):
    (tx, ty) = (enemy['cx'], enemy['cy'])
    ax = FIELD_CENTER[0] + (tx - cur[0] - (u_ref - 0.5) * BOX_W) * kx
    ay = FIELD_CENTER[1] + (ty - cur[1] - (v_ref - 0.5) * BOX_H) * ky
    side = _dir_side(enemy.get('cx0', tx) - MAP_CENTER[0], enemy.get('cy0', ty) - MAP_CENTER[1])
    a4 = o.get('aim_y4')
    (base_ax, base_ay) = (ax, ay)
    ay += a4[{
        'up': 0,
        'down': 1,
        'left': 2,
        'right': 3 }[side]] if a4 and not multi else o.get('aim_y', AIM_Y_OFFSET)
    after_aimy = (ax, ay)
    center_holds = o.get('summon_center') and _config.summon_mode(o) != 'non_taunt'
    lead = 0.0 if center_holds else o['lead_px'] * lead_mult
    lead_mode = '없음'
    if lead > 0:
        if multi or o.get('lead_angle') or not o.get('use_summon'):
            lead_mode = '각도'
            dx = (ally['cx'] - enemy.get('cx0', tx)) * kx
            dy = (ally['cy'] - enemy.get('cy0', ty)) * ky
            (wx, wy) = (dx * AIM_LEAD_XFRAC, dy * 1.0)
            n = (wx * wx + wy * wy) ** 0.5
            if n > 1e-06:
                ax += lead * wx / n
                ay += lead * wy / n
            else:
                lead_mode = '각도(방향0 — 미적용)'
        else:
            lead_mode = f'''카디널({side})'''
            (ox, oy) = {
                'up': (0, 1),
                'down': (0, -1),
                'right': (-2, 0),
                'left': (2, 0) }[side]
            ax += lead * ox
            ay += lead * oy
    elif lead_mult == 0.0:
        lead_mode = '없음(소환 대상)'
    elif center_holds:
        lead_mode = '없음(중앙소환 몹)'
    after_lead = (ax, ay)
    return ((base_ax, base_ay), after_aimy, after_lead, lead, lead_mode)


def _aim_minimap(io, enemy, ally, u_ref, v_ref, pan_scale, kx, ky, o, cycles, log, idx, lead_mult, stop, cur, multi, detect = None):
    (tx, ty, color) = (enemy['cx'], enemy['cy'], enemy.get('color'))
    target_seen = False
    frame2 = None
    boundary_aim = False
    if o.get('_minimal_pan') and not multi:
        (cur, frame2, box2) = _position_for_attack(io, enemy, ally, u_ref, v_ref, kx, ky, o, log, idx, lead_mult, stop, cur, detect = detect)
        if box2 is None:
            return cur
        boundary_aim = bool(box2.get('_boundary_aim'))
        (tx, ty) = (enemy['cx'], enemy['cy'])
        target_seen = True
    else:
        camera_estimated = bool(o.get('_camera_estimated'))
        for attempt in range(MOB_CHASE_ATTEMPTS):
            if stop():
                return cur
            goal_cx = tx - (u_ref - 0.5) * BOX_W
            goal_cy = ty - (v_ref - 0.5) * BOX_H
            (dxp, dyp) = (goal_cx - cur[0], goal_cy - cur[1])
            base = o.get('pan_ratio') or PAN_RATIO
            if multi:
                ratio = 1.0
            elif max(abs(dxp) * 0.5, abs(dyp)) >= CROSS_DIST:
                ratio = max(base, CROSS_RATIO)
            else:
                ratio = base
            (want_dx, want_dy) = (ratio * dxp, ratio * dyp)
            before = list(cur)
            held = _pan(io, want_dx, want_dy, pan_scale)
            predicted = _predict_pan_camera(cur, held, PAN_VX / pan_scale, PAN_VY / pan_scale) if pan_scale > 0 else None
            (frame2, box2, settle_details) = _attack_pan_frame(io, stop, cur, predicted)
            if box2 is None:
                if settle_details.get('reason') == '메인화면 복귀':
                    o['_battle_main_seen'] = True
                log(f'''{idx + 1}부대 조준 중단{_pan_settle_failure_detail(settle_details)} — 이번 부대 공격 생략''')
                return cur
            cur = [
                box2['cx'],
                box2['cy']]
            if not camera_estimated and not box2.get('_camera_estimated'):
                _log_pan(o, log, idx, want_dx, want_dy, cur[0] - before[0], cur[1] - before[1], held, pan_scale, target = (tx, ty), cam_before = before, cam_after = cur)
            camera_estimated = bool(box2.get('_camera_estimated'))
            o['_camera_estimated'] = camera_estimated
            boundary_aim = attempt + 1 >= MOB_CHASE_ATTEMPTS
            cands = _enemy_candidates(crop_minimap(frame2), ally, [
                dict(enemy, cx = tx, cy = ty)]) if frame2 is not None else []
            tgt = _match(cands, color, tx, ty)
            target_seen = bool(tgt and mm_dist_sq(tgt['cx'] - tx, tgt['cy'] - ty) <= CHASE_JUMP_R ** 2)
            if target_seen:
                (tx, ty) = (tgt['cx'], tgt['cy'])
                _update_enemy_track(enemy, tgt)
            else:
                why = '적 재검출 없음' if not tgt else '적 위치 급변 후보 제외'
                box2 = dict(box2, _aim_fallback = ' · '.join(filter(None, (box2.get('_aim_fallback'), f'''{why}, 마지막 적 좌표 사용'''))))
                target_seen = True
            goal_cx = tx - (u_ref - 0.5) * BOX_W
            goal_cy = ty - (v_ref - 0.5) * BOX_H
            if not box2 or abs(goal_cx - cur[0]) <= 1.5 and abs(goal_cy - cur[1]) <= 1.5:
                break
    (enemy['cx'], enemy['cy']) = (tx, ty)
    if not target_seen or not box2 or stop():
        log(f'''{idx + 1}부대 현재 적 위치 미확인/정지 — 이번 부대 공격 생략''')
        return cur
    ax = FIELD_CENTER[0] + (tx - cur[0] - (u_ref - 0.5) * BOX_W) * kx
    ay = FIELD_CENTER[1] + (ty - cur[1] - (v_ref - 0.5) * BOX_H) * ky
    fallback = box2.get('_aim_fallback', '')
    quality = 'estimated' if fallback else 'stable'
    if frame2 is not None and o.get('boss') and detect is not None:
        fb = frame2
        if o.get('_minimal_pan') and not multi:
            boss_aim = box2.get('_boss_aim')
        else:
            asx = FIELD_CENTER[0] + (ally['cx'] - cur[0] - (u_ref - 0.5) * BOX_W) * kx
            asy = FIELD_CENTER[1] + (ally['cy'] - cur[1] - (v_ref - 0.5) * BOX_H) * ky
            boss_aim = _select_boss_aim(fb, detect, (ax, ay), (asx, asy))
        if boss_aim is not None:
            if stop():
                return cur
            raw = (boss_aim[0] + ATTACK_AIM_OFFSET[0], boss_aim[1] + ATTACK_AIM_OFFSET[1])
            nearest = _nearest_attack_point(*raw)
            if nearest is None:
                log(f'''{idx + 1}부대 비정상 타격 좌표 — 공격 생략''')
                return cur
            boundary_aim = boundary_aim or bool(fallback and _minimal_pan_delta((ax, ay), raw) != (0.0, 0.0))
            (bx, by) = nearest if boundary_aim else _adjust_attack_aim(*boss_aim)
            if boundary_aim:
                _note_boundary_attack(log, idx, raw, (bx, by))
                quality += ' boundary'
            note = f''' · {fallback}''' if fallback else ''
            log(f'''{idx + 1}부대 공격 (boss 조준 ✓{note})''')
            _attack(io, int(round(bx)), int(round(by)), cycles, stop, o.get('attack_keys'))
            _save_aim_debug(o, fb, idx, bx, by, (ax, ay), chosen = (bx, by), mode = 'BOSS', info = f'''k={kx:.2f},{ky:.2f} {quality}''')
            _save_debug(o, io.capture(), idx, bx, by, tag = 'boss')
            return cur
    (base_point, after_aimy, after_lead, lead, lead_mode) = _attack_mapping(enemy, ally, cur, u_ref, v_ref, kx, ky, o, lead_mult, multi)
    (base_ax, base_ay) = base_point
    (ax, ay) = after_lead
    final_unclamped = (ax + ATTACK_AIM_OFFSET[0], ay + ATTACK_AIM_OFFSET[1])
    nearest = _nearest_attack_point(*final_unclamped)
    if nearest is None:
        log(f'''{idx + 1}부대 비정상 타격 좌표 — 공격 생략''')
        return cur
    boundary_aim = boundary_aim or bool(fallback and _minimal_pan_delta(base_point, final_unclamped) != (0.0, 0.0))
    if stop():
        return cur
    (ax, ay) = nearest if boundary_aim else _adjust_attack_aim(ax, ay)
    if boundary_aim:
        _note_boundary_attack(log, idx, final_unclamped, (ax, ay))
        quality += ' boundary'
    _log_aim(idx, base_ax, base_ay, after_aimy, after_lead, (ax, ay), lead, lead_mode)
    note = f'''추정 조준 · {fallback}''' if fallback else '미니맵 조준'
    log(f'''{idx + 1}부대 공격 ({note})''')
    if fallback:
        _precision_note(f'''{idx + 1}부대 추정 공격: {fallback}, 카메라={cur}, 적=({tx},{ty}), 클릭=({ax:.1f},{ay:.1f})''')
    _attack(io, int(round(ax)), int(round(ay)), cycles, stop, o.get('attack_keys'))
    _save_aim_debug(o, frame2, idx, ax, ay, (base_ax, base_ay), mode = 'MINIMAP', info = f'''k={kx:.2f},{ky:.2f} {quality}''')
    _save_debug(o, io.capture(), idx, ax, ay, tag = 'mm')
    return cur


def _retreat(io):
    for _ in range(3):
        time.sleep(0.05)
        io.press('esc')

BANJA_WAIT_SEC = 600.0

def run_battle_banja(io, opts = None, log = print, should_stop = None, sub_entry = None):
    stop = should_stop or (lambda: False)
    frame = io.capture()
    if frame is None:
        return 'no-frame'
    ally = analyze(crop_minimap(frame)).get('ally')
    (x, y) = CENTER_PING_XY[_ally_side(ally)] if ally else FIELD_CENTER
    io.move(x, y)
    time.sleep(0.05)
    for k in 'qwe':
        io.press(k)
        time.sleep(0.025)
    if sub_entry is not None:
        
        try:
            sub_entry()
        except Exception as e:
            log(f'''반자사 서브 진입 오류: {e}''')

    log('반자사 — Q·W·E 후 자연 종료 대기')
    end = time.time() + BANJA_WAIT_SEC
    while time.time() < end:
        if stop():
            _retreat(io)
            return 'stopped'
        f = io.capture()
        if f is not None and is_main(f):
            return 'ok'
        time.sleep(0.5)
    log('반자사 — 대기 초과, 퇴각 시도')
    _retreat(io)
    if not wait_for_main(io, log, stop = stop):
        return 'stopped' if stop() else 'retreat-fail'
    return 'ok'

