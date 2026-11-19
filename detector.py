# Source Generated with Decompyle++
# File: detector.pyc (Python 3.11)

import glob
import json
import os
import threading
import time
import cv2
import numpy as np
AGF_TOOLS_DIR = os.path.expanduser(os.path.join('~', 'AGF'))
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SPRITE_ASSIGN_DIRS = (os.path.join(AGF_TOOLS_DIR, 'assignments'), os.path.join(BASE_DIR, 'assets', 'sprite'))
FIELD_H = 651
CENTER = np.array([
    512,
    340], dtype = np.float32)
X_SCALE = 0.75
GATE_X = (40, 984)
GATE_Y = (40, 614)
CLICK_FRAMES = 10
COOLDOWN_LOOPS = CLICK_FRAMES - 1
SEARCH_EXPAND_FRAMES = 10
SPRITE_AVOID2_DELAY_SEC = 8.0

class SearchWindow:
    
    def __init__(self):
        self.age = 0
        self.was_main = False

    
    def update(self, is_main):
        if not is_main or not self.was_main:
            self.reset()
        self.was_main = is_main

    
    def advance(self, n=1.0):
        # n = elapsed time in 0.1 s units, so the search window grows at the same wall-clock
        # speed whatever the loop rate is (it was 1 per loop when the loop ran at 10 Hz)
        self.age = min(SEARCH_EXPAND_FRAMES, self.age + n)

    
    def reset(self):
        self.age = 0

    
    def scale(self):
        return 0.5 + 0.5 * self.age / SEARCH_EXPAND_FRAMES

    scale = property(scale)

AVOID_OVERLAP = 0.8
(FIRE_R_MIN, FIRE_RB_DIFF, FIRE_G_MIN) = (200, 90, 80)
(FIRE_SEED_R, FIRE_SEED_G, FIRE_SEED_B_MAX) = (245, 200, 190)
FIRE_ROI_DEFAULT = (0.5, 0.8, 28)
FIRE_BLOB_MIN = 40
FIRE_LOW_INTACT = 0.45

def fire_ambient(frame_bgr, box):
    (H, W) = frame_bgr.shape[:2]
    (x1, y1, x2, y2) = (int(v) for v in box)
    (w, h) = (x2 - x1, y2 - y1)
    patches = ((x1, y1 - int(h * 1.2), x2, y1 - int(h * 0.85)), (x1, y2 + int(h * 0.15), x2, y2 + int(h * 0.5)), (x1 - int(w * 1.0), y1 + h // 4, x1 - int(w * 0.2), y2), (x2 + int(w * 0.2), y1 + h // 4, x2 + int(w * 1.0), y2))
    fiery = valid = 0
    for px0, py0, px1, py1 in patches:
        (px0, py0) = (max(0, px0), max(0, py0))
        (px1, py1) = (min(W, px1), min(H, py1))
        if px1 - px0 < 8 or py1 - py0 < 6:
            continue
        valid += 1
        if fire_pixels(frame_bgr[py0:py1, px0:px1]) >= 16:
            fiery += 1
    return valid > 0 and fiery >= -(-valid * 3 // 4)

FIRE_REGION_TOP = 0.4
FIRE_REGION_PAD_X = 6
FIRE_REGION_PAD_B = 8

def fire_region(box, rect = None):
    (x1, y1, x2, y2) = (int(v) for v in box)
    if rect is None:
        return (max(0, x1 - FIRE_REGION_PAD_X), y1 + int((y2 - y1) * FIRE_REGION_TOP), x2 + FIRE_REGION_PAD_X, y2 + FIRE_REGION_PAD_B)
    (w, h) = (x2 - x1, y2 - y1)
    (rx0, ry0, rx1, ry1) = rect
    return (x1 + int(w * rx0), y1 + int(h * ry0), x1 + int(w * rx1), y1 + int(h * ry1))


def fire_pixels(roi_bgr):
    if roi_bgr.size == 0:
        return 0
    b = roi_bgr[:, :, 0].astype(np.int16)
    g = roi_bgr[:, :, 1].astype(np.int16)
    r = roi_bgr[:, :, 2].astype(np.int16)
    orange = (r > FIRE_R_MIN) & (r - b > FIRE_RB_DIFF) & (g > FIRE_G_MIN)
    core = (r > FIRE_SEED_R) & (g > FIRE_SEED_G) & (b < FIRE_SEED_B_MAX)
    if not core.any():
        return 0
    m8 = cv2.morphologyEx((orange | core).astype(np.uint8), cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    (n, lab) = cv2.connectedComponents(m8)
    if n <= 1:
        return 0
    valid = np.unique(lab[core])
    valid = valid[valid > 0]
    if len(valid) == 0:
        return 0
    return int(np.bincount(lab.ravel())[valid].max())


def roi_in_box(frame_bgr, box, roi = None, rect = None):
    (x0, y0, x1, y1) = fire_region(box, rect)
    return frame_bgr[max(0, y0):max(0, y1), max(0, x0):max(0, x1)]


def _subtract_sprite_alpha(observed, reference):
    obs = observed.astype(np.float32)
    src = reference[:, :, :3].astype(np.float32)
    alpha = reference[:, :, 3:4].astype(np.float32) / 255.0
    remaining = np.maximum(1.0 - alpha, 0.00392156862745098)
    blended = (alpha[:, :, 0] > 0) & (alpha[:, :, 0] < 1) & np.all((obs >= alpha * src - 3) & (obs <= alpha * src + 255 * (1 - alpha) + 3), axis = 2)
    low = (obs - alpha * src - 3) / remaining
    high = ((obs - alpha * src) + 3) / remaining
    background = np.stack((high[:, :, 0], low[:, :, 1], low[:, :, 2]), axis = 2)
    filtered = observed.copy()
    filtered[blended] = np.clip(background, 0, 255).astype(np.uint8)[blended]
    same = (alpha[:, :, 0] > 0) & (np.abs(obs - src).max(axis = 2) <= 3)
    filtered[same] = 0
    return filtered


def _fire_roi_without_sprite(frame_bgr, box, rect, sprite_bgra, sprite_alpha = False):
    crop = roi_in_box(frame_bgr, box, rect = rect)
    (bx0, by0, bx1, by1) = (int(v) for v in box)
    if crop.size == 0 or sprite_bgra.shape != (by1 - by0, bx1 - bx0, 4):
        return crop
    (rx0, ry0, _rx1, _ry1) = fire_region(box, rect)
    (rx0, ry0) = (max(0, rx0), max(0, ry0))
    (x0, y0) = (max(rx0, bx0), max(ry0, by0))
    x1 = min(rx0 + crop.shape[1], bx1)
    y1 = min(ry0 + crop.shape[0], by1)
    if x1 <= x0 or y1 <= y0:
        return crop
    reference = sprite_bgra[y0 - by0:y1 - by0, x0 - bx0:x1 - bx0]
    observed = crop[y0 - ry0:y1 - ry0, x0 - rx0:x1 - rx0]
    if sprite_alpha:
        filtered = crop.copy()
        filtered[y0 - ry0:y1 - ry0, x0 - rx0:x1 - rx0] = _subtract_sprite_alpha(observed, reference)
        return filtered
    same = (reference[:, :, 3] > 200) & (np.abs(observed.astype(np.int16) - reference[:, :, :3].astype(np.int16)).max(axis = 2) <= 3)
    if not same.any():
        return crop
    filtered = crop.copy()
    filtered[y0 - ry0:y1 - ry0, x0 - rx0:x1 - rx0][same] = 0
    return filtered


def box_has_fire(frame_bgr, box, roi = None, rect = None, sprite_bgra = None, sprite_alpha = False):
    crop = roi_in_box(frame_bgr, box, rect = rect) if sprite_bgra is None else _fire_roi_without_sprite(frame_bgr, box, rect, sprite_bgra, sprite_alpha)
    return fire_pixels(crop) >= FIRE_BLOB_MIN

DIGIT_ROI = (490, 225, 560, 335)
DIGIT_MATCH_MIN = 0.6
DUMMY_NEAR_DIST = 90.0
DUMMY_STACK_STOP = 6
DUMMY_RESET_LOOPS = 20
DIGIT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets', 'digits')
_digit_tpl = None
_digit_dump_at = 0.0
DIGIT_DUMP_KEEP = 200
_digit_prune_busy = False

def _remove_files(paths):
    global _digit_prune_busy
    for f in paths:
        try:
            os.remove(f)
        except Exception:
            continue
    _digit_prune_busy = False


def _prune_digit_dumps(d):
    global _digit_prune_busy
    if _digit_prune_busy:
        return None
    
    try:
        files = sorted(glob.glob(os.path.join(d, 'd_*.png')))
    except Exception:
        return None

    old = files[:-DIGIT_DUMP_KEEP] if len(files) > DIGIT_DUMP_KEEP else []
    if not old:
        return None
    if len(old) > 50:
        _digit_prune_busy = True
        threading.Thread(target = _remove_files, args = (old,), daemon = True).start()
        return None
    _remove_files(old)


def _digit_mask(roi_bgr):
    b = roi_bgr[:, :, 0].astype(np.int16)
    g = roi_bgr[:, :, 1].astype(np.int16)
    r = roi_bgr[:, :, 2].astype(np.int16)
    return ((r >= 190) & (g >= 90) & (g <= 210) & (b <= 130)).astype(np.uint8)


def _digit_templates():
    global _digit_tpl
    if _digit_tpl is None:
        _digit_tpl = { }
        for p in glob.glob(os.path.join(DIGIT_DIR, '*.png')):
            name = os.path.splitext(os.path.basename(p))[0]
            img = cv2.imread(p, cv2.IMREAD_GRAYSCALE)
            if img is not None and len(name) == 1 and name.isdigit():
                _digit_tpl[name] = (img > 127).astype(np.float32)
    return _digit_tpl


def read_top_number(frame_bgr, dump_dir = None):
    global _digit_dump_at
    tpl = _digit_templates()
    if not tpl:
        return None
    (x0, y0, x1, y1) = DIGIT_ROI
    if frame_bgr.shape[0] < y1 or frame_bgr.shape[1] < x1:
        return None
    roi = frame_bgr[y0:y1, x0:x1]
    mask = _digit_mask(roi)
    (n, lab, stats, _) = cv2.connectedComponentsWithStats(mask, 8)
    keep = np.zeros_like(mask)
    for i in range(1, n):
        a = int(stats[i, cv2.CC_STAT_AREA])
        h = int(stats[i, cv2.CC_STAT_HEIGHT])
        if 25 <= a <= 500 and h <= 50:
            keep[lab == i] = 1
    if int(keep.sum()) < 60:
        return None
    m = keep.astype(np.float32)
    (best, score) = (None, 0.0)
    for name, t in tpl.items():
        s = float(cv2.matchTemplate(m, t, cv2.TM_CCOEFF_NORMED).max())
        if s > score:
            (best, score) = (name, s)
    if score >= DIGIT_MATCH_MIN:
        return best
    if dump_dir and time.time() - _digit_dump_at >= 5.0:
        _digit_dump_at = time.time()
        
        try:
            os.makedirs(dump_dir, exist_ok = True)
            cv2.imwrite(os.path.join(dump_dir, time.strftime('d_%Y%m%d_%H%M%S.png')), roi)
            _prune_digit_dumps(dump_dir)
        except Exception:
            pass
    return None


BOX_TL_BGR = (89, 193, 216)
BOX_TR_BGR = (84, 191, 215)
BOX_BL_BGR = (83, 193, 219)
BOX_BR_BGR = (86, 193, 215)
BOX_TOL = 10
MOB_PIXEL_BGR = (255, 255, 88)
MOB_PIXEL_TOL = 20

def _find_corner_pattern(frame_bgr, tl, tr, bl, br, tol):
    img = frame_bgr[:FIELD_H].astype(np.int16)
    (TL, TR) = (img[:-1, :-1], img[:-1, 1:])
    (BL, BR) = (img[1:, :-1], img[1:, 1:])
    mask = (np.abs(TL - tl) <= tol).all(2) & (np.abs(TR - tr) <= tol).all(2) & (np.abs(BL - bl) <= tol).all(2) & (np.abs(BR - br) <= tol).all(2)
    (ys, xs) = np.nonzero(mask)
    if xs.size == 0:
        return np.empty((0, 2), dtype = np.float32)
    return np.stack([
        xs,
        ys], axis = 1).astype(np.float32)


def find_boxes(frame_bgr):
    return _find_corner_pattern(frame_bgr, BOX_TL_BGR, BOX_TR_BGR, BOX_BL_BGR, BOX_BR_BGR, BOX_TOL)


def find_pixel_mobs(frame_bgr):
    return _find_corner_pattern(frame_bgr, MOB_PIXEL_BGR, MOB_PIXEL_BGR, MOB_PIXEL_BGR, MOB_PIXEL_BGR, MOB_PIXEL_TOL)


def _overlap_frac(mob, avoids):
    (mx1, my1, mx2, my2) = mob
    area = max(1.0, (mx2 - mx1) * (my2 - my1))
    best = 0.0
    for ax1, ay1, ax2, ay2 in avoids:
        iw = min(mx2, ax2) - max(mx1, ax1)
        ih = min(my2, ay2) - max(my1, ay1)
        if iw > 0 and ih > 0:
            best = max(best, iw * ih / area)
    return best


class MobDetector:
    
    def __init__(self, model_path, conf = 0.8, classes = ('mob',), imgsz = None, avoid_conf = None):
        self.model_path = model_path
        self.conf = conf
        self.avoid_conf = conf if avoid_conf is None else avoid_conf
        self.classes = set(classes)
        self.imgsz = imgsz
        self.model = None
        self.names = None
        self.ready = False

    
    def preload(self):
        from ultralytics import YOLO
        self.model = YOLO(self.model_path)
        self.names = self.model.names
        if self.imgsz is None:
            
            try:
                self.imgsz = int(self.model.ckpt['train_args']['imgsz'])
            except Exception:
                self.imgsz = 512

        dummy = np.zeros((self.imgsz, self.imgsz, 3), dtype = np.uint8)
        self.model.predict(source = dummy, imgsz = self.imgsz, conf = self.conf, verbose = False)
        self.ready = True

    
    def detect(self, frame_bgr, conf = None, fire_roi = None, with_conf = False, trust_avoid = None, fire_rect = None):
        empty = np.empty((0, 2), dtype = np.float32)
        empty_cf = np.empty((0,), dtype = np.float32)
        if not self.ready:
            return (empty, empty_cf) if with_conf else empty
        trust = fire_roi is None if trust_avoid is None else bool(trust_avoid)
        mob_th = self.conf if conf is None else conf
        avoid_th = self.avoid_conf if conf is None else conf
        rgb = cv2.cvtColor(frame_bgr[:FIELD_H], cv2.COLOR_BGR2RGB)
        r = self.model.predict(source = rgb, imgsz = self.imgsz, conf = min(mob_th, avoid_th), verbose = False)[0]
        (cands, avoids, avoid2s) = ([], [], [])
        for box, cls, cf in zip(r.boxes.xyxy, r.boxes.cls, r.boxes.conf):
            name = self.names[int(cls)]
            xy = box.tolist()
            if name in self.classes:
                if float(cf) >= mob_th:
                    cands.append((xy, float(cf)))
                continue
            if name == 'avoid2':
                if float(cf) >= avoid_th:
                    avoid2s.append(xy)
                continue
            if name.startswith('avoid') and float(cf) >= avoid_th:
                if trust:
                    avoids.append(xy)
                    continue
                cands.append((xy, float(cf)))
        excl = avoid2s + avoids
        (out, out_cf) = ([], [])
        for box, cf in cands:
            (x1, y1, x2, y2) = box
            if excl and _overlap_frac((x1, y1, x2, y2), excl) >= AVOID_OVERLAP:
                continue
            (cx, cy) = ((x1 + x2) / 2.0, (y1 + y2) / 2.0)
            if fire_roi is not None and box_has_fire(frame_bgr, box, fire_roi, rect = fire_rect):
                continue
            out.append([
                cx,
                cy])
            out_cf.append(cf)
        coords = np.array(out, dtype=np.float32) if out else empty
        if with_conf:
            return (coords, np.array(out_cf, dtype=np.float32) if out_cf else empty_cf)
        return coords



class SpriteDetector:
    _FIRE_SPRITE_EXCLUDE = frozenset({
        'ghostjy_m',
        'ghostjy_n',
        'ghostpm_m',
        'ghostpm_n',
        'jiphaeng_m',
        'jiphaeng_n',
        'master_pil_m',
        'master_pil_n',
        'lord_kumchun_m',
        'lord_kumchun_n',
        'lord_shinnong_m',
        'lord_shinnong_n'})
    _FIRE_ALPHA_EXCLUDE = frozenset({
        'jiphaeng_n',
        'jiphaeng_m'})
    
    def __init__(self, agf_names):
        self.agf_names = list(agf_names)
        self.matcher = None
        self.frame_cls = { }
        self.names = {
            0: 'mob' }
        self.ready = False
        self._fire_sprites = { }

    
    @staticmethod
    def _load_assign(stem):
        for d in SPRITE_ASSIGN_DIRS:
            try:
                with open(os.path.join(d, stem + '.json'), encoding='utf-8') as fp:
                    return json.load(fp)['classes']
            except Exception:
                continue
        return None

    
    def preload(self):
        import sprite_match
        paths = sprite_match.resolve_agf_paths(self.agf_names)
        fire_sprites = { }
        skip = set()
        for p in paths:
            stem = os.path.splitext(os.path.basename(p))[0]
            cls = self._load_assign(stem)
            if cls is None:
                continue
            self.frame_cls[stem] = { i: c for i, c in enumerate(cls) if c != 'mob' }
            skip |= { (stem, i) for i, c in enumerate(cls) if c in ('other', 'skip') }
        bg_dir = os.path.join(BASE_DIR, 'snapshots')
        bg_counts = None
        if not glob.glob(os.path.join(bg_dir, '*.png')):
            bg_dir = None
            hist = os.path.join(BASE_DIR, 'assets', 'sprite', 'bg_hist.npz')
            
            try:
                import numpy as _np
                z = _np.load(hist)
                bg_counts = dict(zip(z['colors'].tolist(), z['counts'].tolist()))
            except Exception:
                pass

        self.matcher = sprite_match.SpriteMatcher(paths, bg_dir=bg_dir, bg_counts=bg_counts, skip_frames=skip, log=lambda *a, **k: None)
        for p in paths:
            stem = os.path.splitext(os.path.basename(p))[0]
            if stem not in self._FIRE_SPRITE_EXCLUDE:
                continue
            source = sprite_match.AgfFile(p)
            for i in range(source.nframes):
                if (stem, i) not in skip:
                    fire_sprites[stem, i] = sprite_match._trim(source.frame(i))
        self._fire_sprites = fire_sprites
        self.ready = True

    
    def fire_reference(self, tag):
        (stem, fr) = tag.rsplit(':', 1)
        mirror = fr.endswith('M')
        idx = int(fr[:-1]) if mirror else int(fr)
        reference = self._fire_sprites.get((stem, idx))
        return reference[:, ::-1] if reference is not None and mirror else reference

    
    def has_fire(self, frame_bgr, box, tag, roi = None, rect = None):
        return box_has_fire(frame_bgr, box, roi, rect = rect, sprite_bgra = self.fire_reference(tag), sprite_alpha = tag.rsplit(':', 1)[0] in self._FIRE_ALPHA_EXCLUDE)

    
    def detect(self, frame_bgr, conf = None, fire_roi = None, with_conf = False, trust_avoid = None, fire_rect = None, *, allow_avoid2 = False):
        empty = np.empty((0, 2), dtype = np.float32)
        empty_cf = np.empty((0,), dtype = np.float32)
        if not self.ready:
            return (empty, empty_cf) if with_conf else empty
        (cands, excl) = ([], [])
        for x, y, w, h, sc, tag, lowf in self.matcher.detect(frame_bgr):
            (stem, fr) = tag.rsplit(':', 1)
            mirror = fr.endswith('M')
            idx = int(fr[:-1]) if mirror else int(fr)
            cls = self.frame_cls.get(stem, { }).get(idx)
            box = (x, y, x + w, y + h)
            if cls == 'avoid2' and mirror and allow_avoid2:
                excl.append(box)
                continue
            if cls in ('other', 'skip'):
                continue
            cands.append((box, sc, lowf, tag))
        (out, out_cf) = ([], [])
        for box, cf, lowf, tag in cands:
            if excl and _overlap_frac(box, excl) >= AVOID_OVERLAP:
                continue
            if fire_roi is not None and self.has_fire(frame_bgr, box, tag, fire_roi, rect = fire_rect):
                # Fire ring at the mob's feet = another player/party is already fighting it.
                # With a tuned fire_rect that is decisive. (The decompiled condition used to
                # skip such a mob only when the fire was 'ambient', so engaged mobs were kept:
                # live 2026-11-19, 3 of 3 ringed 도사_귀 flagged, 2 of them still clicked.)
                if fire_rect or lowf < FIRE_LOW_INTACT or fire_ambient(frame_bgr, box):
                    continue
            out.append([
                (box[0] + box[2]) / 2.0,
                (box[1] + box[3]) / 2.0])
            out_cf.append(cf)
        coords = np.array(out, dtype=np.float32) if out else empty
        if with_conf:
            return (coords, np.array(out_cf, dtype=np.float32) if out_cf else empty_cf)
        return coords



def corrected_dist(coords):
    dx = (coords[:, 0] - CENTER[0]) * X_SCALE
    dy = coords[:, 1] - CENTER[1]
    return np.sqrt(dx * dx + dy * dy)


# Screen areas that are HUD, never ground: a click there opens a window or presses a button
# (the 용병 portrait column opens that merc's 가방/status window, which freezes the macro).
UI_BLOCK_RECTS = (
    (0, 0, 100, 525),        # 용병 portraits + their HP bars
    (0, 0, 350, 90),         # top-left stat box (shown on hover) and portrait 1
    (100, 0, 665, 52),       # top toolbar icons
    (820, 0, 1024, 205),     # minimap
    (955, 355, 1024, 650),   # right-hand button column
    (0, 555, 335, 700),      # Alt+1 / Alt+2 quick slots
    (0, 640, 1024, 768),     # bottom HUD
)


def ui_blocked(x, y) -> bool:
    return any(x0 <= x < x1 and y0 <= y < y1 for x0, y0, x1, y1 in UI_BLOCK_RECTS)


def drop_ui_points(coords):
    """Remove detections that sit on the HUD so the next-nearest real mob is picked instead."""
    if coords is None or coords.shape[0] == 0:
        return coords
    keep = np.array([not ui_blocked(float(c[0]), float(c[1])) for c in coords], dtype=bool)
    return coords[keep]


def nearest_in_gate(coords, scale = 1.0, center = None):
    coords = drop_ui_points(coords)
    if coords is None or coords.shape[0] == 0:
        return None
    gx = (GATE_X[0] + GATE_X[1]) / 2.0
    gy = (GATE_Y[0] + GATE_Y[1]) / 2.0
    if center is not None and scale < 1.0:
        (gx, gy) = center
    hx = ((GATE_X[1] - GATE_X[0]) / 2.0) * scale
    hy = ((GATE_Y[1] - GATE_Y[0]) / 2.0) * scale
    mask = (coords[:, 0] >= max(GATE_X[0], gx - hx)) & (coords[:, 0] <= min(GATE_X[1], gx + hx)) & (coords[:, 1] >= max(GATE_Y[0], gy - hy)) & (coords[:, 1] <= min(GATE_Y[1], gy + hy))
    if not mask.any():
        return None
    d = corrected_dist(coords)
    real = np.flatnonzero(mask)[np.argmin(d[mask])]
    return (float(coords[real, 0]), float(coords[real, 1]), float(d[real]))


def click_cooldown(dist):
    return COOLDOWN_LOOPS

