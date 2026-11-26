# Decompiled with PyLingual (https://pylingual.io)
# Internal filename: 'jochul.py'
# Bytecode version: 3.11a7e (3495)
# Source timestamp: 2026-08-17 09:30:58 UTC (1786959058)

import os
import sys
import threading
import time
from collections import Counter
import cv2
import numpy as np

# Absolute floor for a medallion match. The gap test alone let a weak 0.889 background score win
# when the medallion was only half-visible, which is how a stray first frame could vote a wrong
# start slot. Real sightings score >= 0.96, clean background sits at 0.887-0.891.
MARKER_ABS = 0.93
MARKER_GAP = 0.03
MARKER_NEED = 2
MARKER_WIN = 5
REGION = (287, 231, 734, 582)
MARKER_BAND_Y1 = 130
MARKER_WIN_X = 45
PARK_XY = (292, 167)
CLICK_Y = 373
CLICK_X = {1: 354, 2: 431, 3: 518, 4: 598, 5: 678}
FIRST_TILE_DELAY = 0.5
SHUFFLE_DELAY = 2.5
FPS = 15
DURATION_S = 13.5
PERIOD = 13
N_OPS = 15
EXT_K = 6
CONF = 0.3
CONF_SENS = 0.15
IMG_SIZE = 256
BATCH = 8
Y_TOL_NORM = 0.05714285714285714
CLASS_RANGES_NORM = {1: (0.0, 0.227), 2: (0.227, 0.409), 3: (0.409, 0.591), 4: (0.591, 0.773), 5: (0.773, 1.0)}
ALL_SLOTS = {1, 2, 3, 4, 5}
_PAT1 = ((10, 17, 69), (10, 17, 69), (8, 14, 61), (10, 16, 79))
_PAT2 = ((17, 28, 111), (17, 28, 111), (13, 22, 94), (17, 26, 127))
_PAT_TOL = 3
_FIRST_TILE_LIMITS = ((1, 105), (2, 185), (3, 265), (4, 345))
def crop_region(frame):
    x0, y0, x1, y1 = REGION
    return frame[y0:y1, x0:x1]
def _find_pattern(img, pat, tol=_PAT_TOL):
    # ***<module>._find_pattern: Failure: Different bytecode
    tl, tr, bl, br = pat
    a = img.astype(np.int16)
    m = (np.abs(a[:(-1), :(-1)] - np.asarray(tl, np.int16)) <= tol).all(2) & (np.abs(a[:(-1), 1:] - np.asarray(tr, np.int16)) <= tol).all(2) & (np.abs(a[1:, :(-1)] - np.asarray(bl, np.int16)) <= tol).all(2) & (np.abs(a[1:, 1:] - np.asarray(br, np.int16)) <= tol).all(2)
    ys, xs = np.where(m)
    return list(zip(xs.tolist(), ys.tolist()))
def find_first_tile(region_img):
    pts = _find_pattern(region_img, _PAT1) or _find_pattern(region_img, _PAT2)
    if not pts:
        return
    else:
        x = pts[0][0]
        for slot, limit in _FIRST_TILE_LIMITS:
            if x <= limit:
                return slot
        return 5
_MAPAE_TMPL = None
_MAPAE_MASK = None


def _decode_agf(path):
    """Minimal .AGF decoder -> (frames as RGBA arrays, per-frame rects, canvas size).

    Inlined instead of importing agf.py so there is no import-order ambiguity between the repo-root
    copy and dev/tools, and nothing extra to add to the PyInstaller spec. Format: u32 magic 0x23,
    u32 max_w, u32 max_h, u32 frame_count; frame offsets at 0x4C0; i16 x/y/w/h rects at 0x970; then
    per-frame blocks, each with the zlib size at +0x2C and the stream at +0x30. Pixels are A,R,G,B
    with (A=0,R=n,G=0,B=0) encoding a run of n transparent pixels.
    """
    import struct
    import zlib
    data = open(path, 'rb').read()
    magic, max_w, max_h, n = struct.unpack_from('<4I', data, 0)
    if magic != 0x23:
        raise ValueError('not an AGF: %#x' % magic)
    base = 0x970 + 8 * n
    usize = struct.unpack_from('<I', data, base)[0]
    zsize = struct.unpack_from('<I', data, base + 0x2C)[0]
    buf = zlib.decompress(data[base + 0x30: base + 0x30 + zsize])
    if len(buf) != usize:
        raise ValueError('AGF size mismatch %d/%d' % (len(buf), usize))
    offs = list(struct.unpack_from('<%dI' % n, data, 0x4C0)) + [len(buf)]
    frames, rects = [], []
    for i in range(n):
        x, y, w, h = struct.unpack_from('<4h', data, 0x970 + 8 * i)
        a = np.frombuffer(buf[offs[i]:offs[i + 1]], np.uint8).reshape(-1, 4)
        out = np.zeros((w * h, 4), np.uint8)
        pos = 0
        run = (a[:, 0] == 0) & (a[:, 2] == 0) & (a[:, 3] == 0)
        for k in range(len(a)):
            if pos >= w * h:
                break
            if run[k]:
                pos += int(a[k, 1])
            else:
                out[pos] = (a[k, 1], a[k, 2], a[k, 3], a[k, 0])
                pos += 1
        frames.append(out.reshape(h, w, 4))
        rects.append((x, y, w, h))
    return frames, rects, (max_w, max_h)


def _load_mapae():
    """Lazy-load the shipped Mapae.AGF medallion sprite as a masked grey template.

    The medallion is a client asset, not something we drew: assets/textures/ui/SecretInspector/Mapae.agf
    ships in the install and the repo copy is byte-identical. The middle frame is the settled bob pose,
    which is the pose that shows on the reveal, and template matching it is skin-independent (no gold
    HSV window, so a pink-haired or dark-armoured character cannot break it).
    """
    global _MAPAE_TMPL, _MAPAE_MASK
    if _MAPAE_TMPL is not None:
        return _MAPAE_TMPL
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets', 'medallion', 'Mapae.AGF')
    frames, rects, (max_w, max_h) = _decode_agf(path)
    i = min(4, len(frames) - 1)
    canvas = np.zeros((max_h, max_w, 4), np.uint8)
    x, y, w, h = rects[i]
    canvas[y:y + h, x:x + w] = frames[i]
    _MAPAE_TMPL = cv2.cvtColor(np.ascontiguousarray(canvas[..., :3]), cv2.COLOR_BGR2GRAY)
    _MAPAE_MASK = (canvas[..., 3] > 128).astype(np.uint8) * 255
    return _MAPAE_TMPL


def marker_scores(region_img):
    """Per-slot medallion correlation (1..5) over the bob band above the row."""
    tmpl = _load_mapae()
    grey = cv2.cvtColor(np.ascontiguousarray(region_img), cv2.COLOR_BGR2GRAY)
    band = grey[:min(grey.shape[0], MARKER_BAND_Y1)]
    out = {}
    for slot in (1, 2, 3, 4, 5):
        cx = CLICK_X[slot] - REGION[0]
        lo, hi = max(0, cx - MARKER_WIN_X), min(band.shape[1], cx + MARKER_WIN_X)
        sub = band[:, lo:hi]
        if sub.shape[0] < tmpl.shape[0] or sub.shape[1] < tmpl.shape[1]:
            out[slot] = -1.0
            continue
        res = cv2.matchTemplate(sub, tmpl, cv2.TM_CCORR_NORMED, mask=_MAPAE_MASK)
        out[slot] = float(res.max())
    return out


def find_marker_slot(region_img):
    """Slot (1-5) under the floating medallion, or None when it is not on screen.

    Returns None unless the best slot beats the runner-up by MARKER_GAP, so frames where the
    medallion is between bobs (or hidden) score as absent instead of guessing. Call it on several
    frames and vote (see vote_marker)."""
    scores = marker_scores(region_img)
    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    if not ranked or ranked[0][1] < MARKER_ABS:
        return None
    if ranked[0][1] - ranked[1][1] < MARKER_GAP:
        return None
    return ranked[0][0]


def marker_lock(votes, reading):
    """Return the agreed slot once MARKER_NEED of the last MARKER_WIN readings agree, else None.

    The medallion bobs in and out (it is on screen only ~13% of a round), so a plain run-length
    vote never fires; a short sliding window tolerates the gaps but still needs a real burst, so a
    single stray frame cannot lock the wrong slot.
    """
    votes.append(reading)
    seen = [v for v in votes[-MARKER_WIN:] if v]
    if len(seen) < MARKER_NEED:
        return None
    slot, n = Counter(seen).most_common(1)[0]
    return slot if n >= MARKER_NEED else None


def vote_marker(slots):
    """Most common slot among the frames where the medallion was seen (None if never seen)."""
    seen = [x for x in slots if x]
    return Counter(seen).most_common(1)[0][0] if seen else None


def record(capture_fn, fps=FPS, duration=DURATION_S):
    interval = 1.0 / fps
    total = int(fps * duration)
    frames, times = ([], [])
    t0 = time.perf_counter()
    next_t = t0
    for _ in range(total):
        now = time.perf_counter()
        if now < next_t:
            time.sleep(next_t - now)
        next_t += interval
        f = capture_fn()
        if f is not None:
            frames.append(np.ascontiguousarray(crop_region(f)))
            times.append(time.perf_counter() - t0)
    return (frames, times)
def _resample_uniform(per_frame, times, fps=FPS):
    if not times:
        return list(per_frame)
    n_grid = max(1, int(round(times[-1] * fps)) + 1)
    grid = [None] * n_grid
    for det, t in zip(per_frame, times):
        k = int(round(t * fps))
        if 0 <= k < n_grid and (grid[k] is None or det is not None):
            grid[k] = det
    return grid
def _horizontal_groups(pts, y_tol):
    if pts.shape[0] == 0:
        return []
    order = np.argsort(pts[:, 1])
    ys = pts[order, 1]
    out, i, n = ([], 0, len(ys))
    while i < n:
        j = i
        while j < n and ys[j] - ys[i] <= y_tol:
            j += 1
        idxs = order[i:j].tolist()
        out.append((idxs, j - i, float(ys[i:j].mean())))
        i = j
    return out


def _slot_from_x(x, w):
    for slot, (lo, hi) in CLASS_RANGES_NORM.items():
        if lo * w <= x < hi * w:
                return slot
def _missing_from_pts(pts, w, h):
    if len(pts) == 0:
        return
    else:
        pts = np.asarray(pts, dtype=float)
        groups = _horizontal_groups(pts, Y_TOL_NORM * h)
        sizes = sorted((g[1] for g in groups))
        if len(groups) == 3 and sizes == [1, 2, 2]:
                return
        cand = [(g, s) for g, s, ym in groups if s == 3 or (s == 2 and 110 <= ym <= 170)]
        if not cand:
            return
        else:
            idxs, s = cand[0]
            seen = set()
            for i in idxs:
                slot = _slot_from_x(pts[i][0], w)
                if slot is None:
                    return
                else:
                    seen.add(slot)
            if len(seen) < 2:
                return
            else:
                missing = tuple(sorted(ALL_SLOTS - seen))
                if s == 3 and len(missing) == 2 or (s == 2 and len(missing) == 3):
                    return missing
                else:
                    return None
def _vote_block(items):
    pairs = [t for t in items if len(t) == 2]
    triples = [t for t in items if len(t) == 3]
    if pairs:
        top = Counter(pairs).most_common(2)
        if len(top) > 1 and top[0][1] == top[1][1]:
                return
        return top[0][0]
    else:
        if triples:
            inter = set(triples[0])
            for t in triples[1:]:
                inter &= set(t)
            if len(inter) == 2:
                return tuple(sorted(inter))
            else:
                return Counter(triples).most_common(1)[0][0]
def _resolve_pairs(votes, block_items, sens_items=None, ext_items=None):
    n = len(votes)
    resolved = [tuple(sorted(v)) if v and len(v) == 2 else None for v in votes]
    def _cooc(items, allowed):
        pair_cnt = Counter()
        cnt = Counter()
        for t in items:
            s = sorted((x for x in t if allowed is None or x in allowed))
            for x in s:
                cnt[x] += 1
            for a in range(len(s)):
                for b in range(a + 1, len(s)):
                    pair_cnt[s[a], s[b]] += 1
        return (pair_cnt, cnt)
    def _freq_top2(i, allowed):
        pair_cnt, cnt = _cooc(block_items[i], allowed)
        ext_pair = Counter() if ext_items is None else _cooc(ext_items[i], allowed)[0]
        sens_pair = Counter() if sens_items is None else _cooc(sens_items[i], allowed)[0]
        if pair_cnt:
            return sorted(pair_cnt.items(), key=lambda kv: (-kv[1], -ext_pair[kv[0]], -sens_pair[kv[0]], kv[0]))[0][0]
        else:
            if len(cnt) < 2:
                return
            else:
                ext_cnt = Counter() if ext_items is None else _cooc(ext_items[i], allowed)[1]
                sens_cnt = Counter() if sens_items is None else _cooc(sens_items[i], allowed)[1]
                top = sorted(cnt.items(), key=lambda kv: (-kv[1], -ext_cnt[kv[0]], -sens_cnt[kv[0]], kv[0]))[:2]
                return tuple(sorted((s for s, _ in top)))
    for _ in range(n + 2):
        changed = False
        for i in range(n):
            if resolved[i] is not None:
                continue
            else:
                forbid = set()
                if i - 1 >= 0 and resolved[i - 1]:
                        forbid |= set(resolved[i - 1])
                if i + 1 < n and resolved[i + 1]:
                        forbid |= set(resolved[i + 1])
                allowed = ALL_SLOTS - forbid
                pick = tuple(sorted(allowed)) if len(allowed) == 2 else _freq_top2(i, allowed)
                if pick and len(pick) == 2:
                        resolved[i] = pick
                        changed = True
        if not changed:
            break
    for i in range(n):
        if resolved[i] is None:
            resolved[i] = _freq_top2(i, None)
    return [r for r in resolved if r is not None]
def periodic_decode(per_frame, period=PERIOD, n_ops=N_OPS, per_frame_sens=None):
    # ***<module>.periodic_decode: Failure: Different control flow
    n = len(per_frame)
    if n == 0:
        return []
    else:
        if n_ops is None:
            n_ops = max(1, round(n / period))
        search = int(period) // 2 + 1
        cands = sorted((period + 0.25 * k for k in range((-4), 3)), key=lambda p: abs(p - period))
        best = None
        for p in cands:
            # p 후보별 최적 phi 를 찾는다
            for phi in range(-search, search + 1):
                ops, block_items, compat, bnd_none = ([], [], 0, 0)
                for i in range(1, n_ops):
                    b = int(round(phi + p * i))
                    if 0 <= b < n and per_frame[b] is None:
                                bnd_none += 1
                for i in range(n_ops):
                    lo = int(round(phi + p * i))
                    hi = int(round(phi + p * (i + 1)))
                    items = [per_frame[f] for f in range(max(0, lo), min(n, hi)) if per_frame[f] is not None]
                    v = _vote_block(items)
                    ops.append(v)
                    block_items.append(items)
                    if v and len(v) == 2:
                            ps = set(v)
                            compat += sum((1 for t in items if ps.issubset(set(t))))
                # Only two valid swaps that share a tile count as a violation (a tile cannot be in two
                # consecutive swaps). An undecided block (None) is NOT a violation: the decompiled
                # source had `not a or not b or ...` here, which the original bytecode does not do.
                viol = sum((1 for a, b in zip(ops, ops[1:]) if a and b and len(a) == 2 and (len(b) == 2) and set(a) & set(b)))
                key = (-viol, bnd_none, compat)
                if best is None or key > best[0]:
                    best = (key, ops, block_items, p, phi)
        _, _, _, p, phi = best
        ext_items = []
        sens_items = [] if per_frame_sens is not None else None
        for i in range(n_ops):
            lo = int(round(phi + p * i))
            hi = int(round(phi + p * (i + 1)))
            ext_items.append([per_frame[f] for f in range(max(0, lo - EXT_K), min(n, hi + EXT_K)) if per_frame[f] is not None])
            if sens_items is not None:
                sens_items.append([per_frame_sens[f] for f in range(max(0, lo), min(n, hi)) if per_frame_sens[f] is not None])
        return _resolve_pairs(best[1], best[2], sens_items, ext_items)

def _viol_count(ops):
    return sum((1 for a, b in zip(ops, ops[1:]) if set(a) & set(b)))
def apply_swaps(ops, init=(1, 2, 3, 4, 5)):
    lst = list(init)
    for op in ops:
        if op and len(op) == 2:
                i, j = (op[0] - 1, op[1] - 1)
                lst[i], lst[j] = (lst[j], lst[i])
    return lst
class JochulSolver:
    def __init__(self, model_path):
        self.model_path = model_path
        self.model = None
        self.ready = False
    def preload(self):
        import torch
        from ultralytics import YOLO
        self.model = YOLO(self.model_path)
        if torch.cuda.is_available():
            self.model.fuse()
        dummy = np.zeros((351, 447, 3), np.uint8)
        self.model.predict(source=dummy, imgsz=IMG_SIZE, conf=CONF, verbose=False)
        self.ready = True
    def solve(self, frames, times, first_slot):
        per_std, per_sens = self._detect_missing(frames)
        ops = periodic_decode(_resample_uniform(per_std, times), per_frame_sens=_resample_uniform(per_sens, times))
        order = apply_swaps(ops)
        if first_slot not in order:
            return (None, ops)
        else:
            return (order.index(first_slot) + 1, ops)

    def detect_centroids(self, frames, conf=0.20):
        """Per-frame list of (x, y) character centroids from the YOLO detector (not the missing-tile
        logic): the input `track_centroids` needs."""
        import torch
        use_cuda = torch.cuda.is_available()
        out = [[] for _ in frames]
        for s in range(0, len(frames), BATCH):
            batch = frames[s:s + BATCH]
            results = self.model.predict(source=batch, conf=conf, imgsz=IMG_SIZE,
                                          device=0 if use_cuda else 'cpu', max_det=10, iou=0.45, verbose=False)
            for bi, res in enumerate(results):
                b = res.boxes
                if b is None or len(b) == 0:
                    continue
                xyxy = b.xyxy.cpu().numpy()
                out[s + bi] = [((x[0] + x[2]) / 2, (x[1] + x[3]) / 2) for x in xyxy]
        return out

    ENSEMBLE_SETTINGS = [(100.0, 0.6), (100.0, 0.95), (150.0, 0.8), (220.0, 0.6), (220.0, 0.95)]
    # A simple majority (3/5) is too weak for a costly wrong click: it lets two settings
    # disagree and still auto-click. The only labelled clean real round we have currently
    # produces 4/5 votes for the confirmed answer, so require at least 4/5 and abstain otherwise.
    MIN_ENSEMBLE_VOTES = 4

    def solve_tracked(self, frames, times, first_slot, conf=0.20, settings=None):
        """Primary live answer (see the note above TRACK_SLOT_X): velocity-predicted Hungarian
        tracking of the YOLO detector's own centroids through the whole scatter.

        Detection (the slow ~5 s part) runs ONCE; the tracker then runs over several (gate, decay)
        settings on that same detection set (cheap - this adds well under 1 s) and votes. Confirmed
        9/9 agreement on the one real labelled round at the single default setting; voting across
        settings makes a FUTURE round that is less clean say 'uncertain' instead of confidently
        picking whichever setting happened to run, which is the harder failure mode to catch.
        Returns (answer_or_None, info_string). answer is None when there is no majority.
        """
        dets = self.detect_centroids(frames, conf=conf)
        votes = []
        for gate, decay in (settings or self.ENSEMBLE_SETTINGS):
            ans, _ = track_centroids(times, dets, first_slot, gate=gate, decay=decay)
            votes.append(ans)
        counts = Counter(v for v in votes if v is not None)
        if not counts:
            return None, f'no setting found a usable start/end row (votes={votes})'
        top, n_top = counts.most_common(1)[0]
        info = f'ensemble {dict(counts)} of {len(votes)}'
        if n_top < self.MIN_ENSEMBLE_VOTES or n_top * 2 <= len(votes):
            return None, f'insufficient agreement (<{self.MIN_ENSEMBLE_VOTES}/5) - {info}'
        return top, info
    def _detect_missing(self, frames):
        import torch
        use_cuda = torch.cuda.is_available()
        std = [None] * len(frames)
        sens = [None] * len(frames)
        for s in range(0, len(frames), BATCH):
            batch = frames[s:s + BATCH]
            results = self.model.predict(source=batch, conf=CONF_SENS, imgsz=IMG_SIZE, device=0 if use_cuda else 'cpu', max_det=10, iou=0.45, verbose=False)
            for bi, res in enumerate(results):
                h, w = batch[bi].shape[:2]
                b = res.boxes
                if b is None or len(b) == 0:
                    continue
                else:
                    xyxy = b.xyxy.cpu().numpy()
                    cf = b.conf.cpu().numpy()
                    pts = np.column_stack(((xyxy[:, 0] + xyxy[:, 2]) / 2, (xyxy[:, 1] + xyxy[:, 3]) / 2))
                    std[s + bi] = _missing_from_pts(pts[cf >= CONF], w, h)
                    sens[s + bi] = _missing_from_pts(pts, w, h)
        return (std, sens)

# ---------------------------------------------------------------------------------------------
# EXPERIMENTAL, NOT WIRED IN: all-frames recording and global swap decoding (2026-11-20)
#
# The original pipeline sampled the screen 15 times a second and trusted one fixed swap period
# (13 samples). Here every distinct frame the game delivers is kept with its arrival time, and the
# swap sequence is found by one global search over (period, phase, 15 swaps) that maximises the
# agreement between the per-frame detections and the swaps, with a penalty when two consecutive
# swaps share a tile (the game never does that). The period is estimated from the data (0.70 s to
# 1.10 s), so a different shuffle speed no longer breaks it.
# ---------------------------------------------------------------------------------------------
REF_W, REF_H = 1024, 768
MAX_REC_FPS = 45.0
PERIOD_S_NOMINAL = PERIOD / float(FPS)            # 0.8667 s per swap
PERIOD_S_RANGE = (0.70, 1.10)
PAIRS = [(a, b) for a in range(1, 6) for b in range(a + 1, 6)]
_PAIR_INDEX = {p: i for i, p in enumerate(PAIRS)}


def record_all(hwnd, duration=DURATION_S, stop=None, max_fps=MAX_REC_FPS, on_frame=None):
    """Keep EVERY distinct game frame for `duration` seconds (not a fixed 15 Hz sample).
    Returns (crops, times); times are seconds since the first poll. Needs the WGC capture session
    (it counts frames); falls back to ~30 Hz polling of the normal grab if WGC is unavailable.
    `on_frame`, when provided, receives each appended crop as (index, frame, elapsed_seconds)."""
    import cv2
    import capture
    import wgc
    sess = wgc._session(hwnd) if wgc.available() else None
    frames, times = [], []
    t0 = time.perf_counter()
    last_seq, last_t = -1, -1.0
    next_poll = t0
    min_gap = 1.0 / max_fps
    while True:
        now = time.perf_counter()
        if now - t0 >= duration or (stop is not None and stop()):
            break
        f = None
        if sess is not None:
            seq = sess.frames
            if seq != last_seq and now - t0 - last_t >= min_gap * 0.9:
                info = sess.client_frame_info()
                if info is not None:
                    f, last_seq = info[0], info[2]
                else:
                    last_seq = seq
                now = time.perf_counter()
            else:
                time.sleep(0.001)
                continue
        else:
            if now < next_poll:
                time.sleep(0.001)
                continue
            next_poll = now + 1.0 / 30.0
            f = capture.grab_hwnd(hwnd, normalize=False)
        if f is None:
            continue
        if (f.shape[1], f.shape[0]) != (REF_W, REF_H):
            f = cv2.resize(f, (REF_W, REF_H), interpolation=cv2.INTER_AREA)
        frames.append(np.ascontiguousarray(crop_region(f)))
        last_t = now - t0
        times.append(last_t)
        if on_frame is not None:
            on_frame(len(frames) - 1, frames[-1], last_t)
    return frames, times


def _obs_matrix(per_std, per_sens, w_std=1.0, w_sens=0.35):
    """Per-frame evidence for each of the 10 possible swaps: shape (n, 10).
    A detected missing PAIR supports exactly that swap (+), contradicts a swap sharing one tile
    a little and a disjoint swap more. A missing TRIPLE (one false slot) supports the 3 pairs inside it."""
    n = len(per_std)
    m = np.zeros((n, len(PAIRS)), np.float32)
    for src, w in ((per_std, w_std), (per_sens, w_sens)):
        if src is None:
            continue
        for i, v in enumerate(src):
            if not v:
                continue
            sv = set(v)
            if len(v) == 2:
                for k, p in enumerate(PAIRS):
                    inter = len(sv & set(p))
                    m[i, k] += w * (1.0 if inter == 2 else (-0.25 if inter == 1 else -0.6))
            elif len(v) == 3:
                for k, p in enumerate(PAIRS):
                    m[i, k] += w * (0.45 if set(p) <= sv else -0.35)
    return m


_OVERLAP = np.array([[1.0 if set(p) & set(q) else 0.0 for q in PAIRS] for p in PAIRS], np.float32)


def dp_decode(per_std, times, per_sens=None, n_ops=N_OPS, overlap_penalty=4.0, period_range=PERIOD_S_RANGE,
              t_step=0.005, phase_step=0.02, return_info=False):
    """Global decode. per_std/per_sens: per-frame missing tuple or None at the frame arrival `times`
    (seconds). Returns the list of swaps (n_ops pairs)."""
    n = len(per_std)
    if n == 0:
        return ([], {}) if return_info else []
    times = np.asarray(times, np.float64)
    m = _obs_matrix(per_std, per_sens)
    cum = np.vstack([np.zeros((1, m.shape[1]), np.float32), np.cumsum(m, axis=0)])
    best = None
    for T in np.arange(period_range[0], period_range[1] + 1e-9, t_step):
        # prefer the nominal speed slightly when evidence is equal
        prior = -0.15 * abs(T - PERIOD_S_NOMINAL) / 0.05
        for phi in np.arange(-0.5 * T, 0.5 * T + 1e-9, phase_step):
            edges = phi + T * np.arange(n_ops + 1)
            idx = np.searchsorted(times, edges)
            idx = np.clip(idx, 0, n)
            block = cum[idx[1:]] - cum[idx[:-1]]               # (n_ops, 10)
            # DP over blocks with a soft "no shared tile with the previous swap" rule
            score = block[0].copy()
            back = np.zeros((n_ops, len(PAIRS)), np.int8)
            for k in range(1, n_ops):
                trans = score[:, None] - overlap_penalty * _OVERLAP      # (prev, cur)
                back[k] = np.argmax(trans, axis=0)
                score = trans[back[k], np.arange(len(PAIRS))] + block[k]
            end = int(np.argmax(score))
            total = float(score[end]) + prior
            if best is None or total > best[0]:
                best = (total, T, phi, end, back.copy())
    total, T, phi, end, back = best
    seq = [end]
    for k in range(n_ops - 1, 0, -1):
        seq.append(int(back[k, seq[-1]]))
    seq.reverse()
    ops = [PAIRS[i] for i in seq]
    if return_info:
        viol = sum(1 for a, b in zip(ops, ops[1:]) if set(a) & set(b))
        return ops, {'score': total, 'period_s': float(T), 'phase_s': float(phi), 'violations': viol, 'frames': n}
    return ops


def resample_vote(per_frame, times, fps=FPS):
    """Aggregate many irregular samples into the fixed-rate grid the original decoder expects: each cell
    takes the most common detection in it (a cell with only misses stays None)."""
    if not times:
        return list(per_frame)
    n_grid = max(1, int(round(times[-1] * fps)) + 1)
    cells = [[] for _ in range(n_grid)]
    for det, t in zip(per_frame, times):
        k = int(round(t * fps))
        if 0 <= k < n_grid and det is not None:
            cells[k].append(det)
    return [Counter(c).most_common(1)[0][0] if c else None for c in cells]


# ---------------------------------------------------------------------------------------------
# LIVE TRACKER-BASED SOLVER (2026-11-20): the swap-model decoders above (periodic_decode, dp_decode)
# both got the one real, user-confirmed round WRONG (start 2, true end 5) no matter how they were
# tuned. A simple velocity-predicted Hungarian-matching tracker on the YOLO detector's own centroids
# (not background-subtraction blobs, which score much worse) got that SAME round right in all 9
# parameter combinations tried. This is therefore the primary live answer; periodic_decode/dp_decode
# are kept only as a secondary signal recorded for comparison, not used to choose the click.
# n=1 confirmed round: this is evidence of being less wrong, not a proven accuracy number. Every
# future round must still be recorded and labelled so the real hit rate can be measured.
# ---------------------------------------------------------------------------------------------
TRACK_SLOT_X = np.array([65, 145, 225, 305, 385], float)  # board-crop coords of the 5 slots
TRACK_ROW_Y = 140.0
MAX_SETTLE_SPEED = 100.0  # px/s; above this the tracked character is still visibly sliding, not
                          # settled - see the extrapolated-end guard in track_centroids(). Real
                          # settled speeds measured so far: ~0-59 px/s; a real still-moving case
                          # measured 233 px/s. Comfortably between the two, not yet validated
                          # against more real data.


def _assign_optimal(cost):
    """Optimal assignment for a small, possibly RECTANGULAR cost matrix (5 tracked points x however
    many detections this frame has, which is often not exactly 5) by brute force over permutations
    of the larger side, so the live app does not need to bundle scipy for this 5-ish x 5-ish problem."""
    import itertools
    n_r, n_c = cost.shape
    best_cost, best_rows, best_cols = None, None, None
    if n_r <= n_c:
        for cols in itertools.permutations(range(n_c), n_r):
            c = sum(cost[i, cols[i]] for i in range(n_r))
            if best_cost is None or c < best_cost:
                best_cost, best_rows, best_cols = c, tuple(range(n_r)), cols
    else:
        for rows in itertools.permutations(range(n_r), n_c):
            c = sum(cost[rows[j], j] for j in range(n_c))
            if best_cost is None or c < best_cost:
                best_cost, best_rows, best_cols = c, rows, tuple(range(n_c))
    return np.array(best_rows), np.array(best_cols)


ROW_FIT_PX = 34.0  # max |x - slot x| any point of a row may have and still count as on-grid
RECENT_WIN = 12    # frames of match history inspected at the extrapolated end
RECENT_NEED = 3    # matches that history must contain for the final positions to count as measured


def _fit_row(pts):
    """(max_dx, points sorted left to right) for the 5-subset of pts that best matches the slot grid."""
    import itertools
    arr = np.asarray(pts, float).reshape(-1, 2)
    best = None
    for sub in itertools.combinations(range(len(arr)), 5):
        cand = arr[list(sub)]
        cand = cand[np.argsort(cand[:, 0])]
        dx = float(np.max(np.abs(cand[:, 0] - TRACK_SLOT_X)))
        if best is None or dx < best[0]:
            best = (dx, cand)
    return best


def _row_fit(pts):
    """Five settled characters standing ON the slot grid -> (max_dx, points left to right), else None.

    The old test (`_in_row`) only required five points with a flat y and never looked at x, so a row
    that had nothing to do with the board's five slots still counted as an anchor. Worse, when more
    than five points were detected it took `sorted(...)[:5]`, which silently drops whichever point
    sorts last - one stray detection shifts every slot index by one, and the tracker then confidently
    follows the wrong character (5/5 unanimous on two real customer rounds, both wrong). So: choose
    the subset by fit to the real slot grid, and treat a row that does not fit as no anchor at all.
    """
    pts = np.asarray(pts, float).reshape(-1, 2)
    if len(pts) < 5:
        return None
    best = _fit_row(pts)
    if best is None or best[0] > ROW_FIT_PX:
        return None
    cand = best[1]
    if np.std(cand[:, 1]) >= 14 or abs(float(np.median(cand[:, 1])) - TRACK_ROW_Y) >= 40:
        return None
    return best


def track_centroids(times, dets, start_slot, gate=150.0, decay=0.8):
    """dets: per-frame list of (x, y) character centroids (from the YOLO detector, not background
    blobs). Returns (final slot 1-5 of the character that started at start_slot, info string), or
    (None, reason) if no usable start row was found.

    BUG (found 2026-11-22 from a real customer's logged failure, not the dev fixture): this used to
    always require a clean 5-point row near the END too, found by scanning backward for the last
    _in_row() frame. On a real round that end anchor can simply not exist - one character was
    undetected (occlusion/overlap) through the ENTIRE 1.4 s settle window right before reveal,
    something the one clean dev-fixture round never exercised (its tail is instead a few frames of
    reveal-popup visual noise AFTER a perfectly clean settled row, which the old code correctly
    anchored on). When no late clean row exists, the backward scan used to fall through all the way
    to whatever row it last saw - in the logged failure, frames 0-3 (the first 0.06 s, before the
    shuffle even started) - so both anchors ended up inside that 0.06 s window and the 'track'
    covered none of the actual 13.4 s shuffle. Every ensemble setting agreed (5/5, looked maximally
    confident) because they were all measuring the same zero-motion no-op, not because the answer
    was right - the game's own reveal proved it wrong.
    Fix: keep the original fast path (anchor on a genuine LATE clean row, matching tracked
    positions against that real frame) whenever one exists in roughly the back half of the
    recording - this is what makes the dev fixture work and is more precise than the fallback
    when the data allows it. Only when no such late anchor exists (the real-failure case) fall
    back to tracking continuously, frame by frame, all the way to the actual last frame via the
    existing velocity/Hungarian matching (already tolerant of missing/extra detections per frame),
    then read the final slot off the fixed slot grid (TRACK_SLOT_X/TRACK_ROW_Y) instead of a
    frame that doesn't exist.

    (Tried 2026-11-22: also assuming a canonical-grid start when no clean start row exists at
    all, by the same reasoning as the end-anchor fix. Reverted - tested against a real logged
    failure with no start row (20261121_011754), it turned an honest 'no usable row' into a
    confident WRONG answer (said slot 2; the game's reveal says slot 1). 'uncertain' is the
    correct, safe output when the data genuinely doesn't support a claim - this function must
    not trade an honest None for a false-confidence wrong guess, which is the exact bug fixed
    above. Only the END anchor has evidence (two real rounds) justifying the grid-assumption
    fallback; the START anchor still requires a real clean row.)
    """
    n = len(dets)
    s = next((i for i, d in enumerate(dets) if _row_fit(d)), None)
    if s is None:
        return None, 'no start row on the slot grid'
    e_clean = next((i for i in range(n - 1, -1, -1) if _row_fit(dets[i])), None)
    use_clean_end = e_clean is not None and e_clean > s and e_clean >= s + (n - s) * 0.5
    e = e_clean if use_clean_end else n - 1
    if e <= s:
        return None, 'start row too close to end of recording'
    start_fit = _row_fit(dets[s])
    assert start_fit is not None  # guaranteed by the `s is None` check above
    pos = start_fit[1]
    vel = np.zeros((5, 2))
    last = times[s]
    coast = 0
    recent = []  # matched-detection count per frame, last RECENT_WIN frames only
    for i in range(s + 1, e + 1):
        dt = max(1e-3, times[i] - last)
        last = times[i]
        pred = pos + vel * min(dt, 0.25)
        D = np.array(dets[i]).reshape(-1, 2) if len(dets[i]) else np.zeros((0, 2))
        if len(D):
            C = np.linalg.norm(pred[:, None, :] - D[None, :, :], axis=2)
            C = np.where(C > gate, 1e4, C)
            r, c = _assign_optimal(C)
            matched = set()
            for a, b in zip(r, c):
                if C[a, b] < 1e4:
                    vel[a] = 0.35 * vel[a] + 0.65 * np.clip((D[b] - pos[a]) / dt, -400, 400)
                    pos[a] = D[b]
                    matched.add(a)
            for a in range(5):
                if a not in matched:
                    pos[a] = pred[a]
                    vel[a] *= decay
                    coast += 1
            recent = (recent + [len(matched)])[-RECENT_WIN:]
        else:
            pos = pred
            vel *= decay
            coast += 5
            recent = (recent + [0])[-RECENT_WIN:]
    if use_clean_end:
        end_fit = _row_fit(dets[e])
        assert end_fit is not None  # use_clean_end means e is an e_clean frame
        fin = end_fit[1]
    else:
        # Extrapolated-end case: the assumed-settled canonical grid is only trustworthy if the
        # tracked character has actually STOPPED moving by the last captured frame. Found
        # 2026-11-22 from a third real failure (different PC): the recording can end while 2+
        # characters are still visibly sliding into place (the settle animation outlasted the
        # capture window) - bucketing a still-moving point against the fixed grid is a guess, not
        # a measurement, and was confidently wrong (said 4; the game's reveal says 1). The tracked
        # character's own final speed was 233 px/s there, vs 0-59 px/s on the two real rounds
        # where this same fallback path is already known to behave safely (one of them already
        # returns 'no majority' from disagreement; the other is the dev fixture, settled, ~0-2
        # px/s) - well separated, so gate on it instead of guessing.
        tracked_speed = float(np.linalg.norm(vel[start_slot - 1]))
        if tracked_speed > MAX_SETTLE_SPEED:
            return None, 'tracked character still moving at capture end (%.0f px/s)' % tracked_speed
        # The tracked character stopping is not enough on its own: the whole row has to have landed
        # on the slots. Bucketing scattered points against the fixed grid is a guess that all five
        # ensemble settings make identically, so it votes 5/5 and looks certain while being wrong.
        # ...and the positions have to be actual measurements, not extrapolation. If nothing matched
        # near the end, `pos` is just the decaying prediction from the START row, so fitting it to the
        # grid returns the start slot - the zero-motion no-op that reads as maximal confidence.
        if sum(recent) < RECENT_NEED:
            return None, 'almost nothing detected near the capture end (%d matches in the last %d frames)' % (sum(recent), len(recent))
        fit = _row_fit(pos)
        if fit is None:
            return None, 'tracked positions not settled on the slot grid at capture end'
        fin = fit[1]
    C = np.linalg.norm(pos[:, None, :] - fin[None, :, :], axis=2)
    r, c = _assign_optimal(C)
    m = {int(a): int(b) + 1 for a, b in zip(r, c)}
    span = e - s
    mode = 'clean-end' if use_clean_end else 'extrapolated-end'
    return m.get(start_slot - 1), 'ok (%s, coasted %d/%d track-frames)' % (mode, coast, span)


class RoundRecorder:
    """Records every distinct game frame of the board for a whole 조철 round (start to reveal), in the
    background, JPEG-encoded as it goes (~40 KB a frame), then saves them with times and labels.
    Purpose: native-fps, self-labelled footage of the CURRENT game for offline tuning on a Mac.
    Never blocks or alters the solver; every failure is swallowed."""
    KEEP_ROUNDS = 40

    def __init__(self, hwnd, grab_fn=None, max_fps=MAX_REC_FPS, quality=92, max_seconds=45.0):
        self.hwnd, self.grab_fn, self.max_fps, self.quality, self.max_seconds = hwnd, grab_fn, max_fps, quality, max_seconds
        self.frames, self.times = [], []
        self._stop = threading.Event()
        self._thread = None
        self.t0 = None
        self.mode = None

    def start(self):
        self.t0 = time.perf_counter()
        self._thread = threading.Thread(target=self._run, daemon=True, name='jochul-recorder')
        self._thread.start()
        return self

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3.0)

    def _run(self):
        try:
            import cv2
            sess = None
            try:
                import wgc
                if wgc.available():
                    s = wgc._session(self.hwnd)
                    if s is not None and isinstance(getattr(s, 'frames', None), int):
                        sess = s
            except Exception:
                sess = None
            self.mode = 'wgc-every-frame' if sess is not None else 'poll-30hz'
            last_seq, last_t, next_poll = -1, -1.0, time.perf_counter()
            min_gap = 1.0 / self.max_fps
            while not self._stop.is_set():
                now = time.perf_counter()
                if now - self.t0 > self.max_seconds:
                    break
                f = None
                if sess is not None:
                    if sess.frames == last_seq or now - self.t0 - last_t < min_gap * 0.9:
                        time.sleep(0.001)
                        continue
                    info = sess.client_frame_info()
                    last_seq = sess.frames if info is None else info[2]
                    f = info[0] if info is not None else None
                else:
                    if now < next_poll:
                        time.sleep(0.002)
                        continue
                    next_poll = now + 1.0 / 30.0
                    f = self.grab_fn() if self.grab_fn else None
                if f is None:
                    continue
                if (f.shape[1], f.shape[0]) != (REF_W, REF_H):
                    f = cv2.resize(f, (REF_W, REF_H), interpolation=cv2.INTER_AREA)
                ok, buf = cv2.imencode('.jpg', crop_region(f), [cv2.IMWRITE_JPEG_QUALITY, self.quality])
                if ok:
                    last_t = time.perf_counter() - self.t0
                    self.frames.append(buf.tobytes())
                    self.times.append(round(last_t, 4))
        except Exception:
            pass

    def save(self, base_dir, meta):
        import json
        import os
        import shutil
        try:
            if not self.frames:
                return None
            os.makedirs(base_dir, exist_ok=True)
            d = os.path.join(base_dir, time.strftime('round_%Y%m%d_%H%M%S'))
            os.makedirs(d, exist_ok=True)
            for i, b in enumerate(self.frames):
                with open(os.path.join(d, '%05d.jpg' % i), 'wb') as fh:
                    fh.write(b)
            m = dict(meta)
            m.update({'times': self.times, 'frames': len(self.frames), 'mode': self.mode, 'region': list(REGION),
                      'seconds': round(self.times[-1], 2) if self.times else 0,
                      'effective_fps': round(len(self.frames) / max(0.1, self.times[-1]), 1) if self.times else 0})
            with open(os.path.join(d, 'meta.json'), 'w', encoding='utf-8') as fh:
                json.dump(m, fh, ensure_ascii=False, default=str)
            dirs = sorted(x for x in os.listdir(base_dir) if x.startswith('round_'))
            for old in dirs[:-self.KEEP_ROUNDS]:
                shutil.rmtree(os.path.join(base_dir, old), ignore_errors=True)
            return d
        except Exception:
            return None


SETTLE_SLOTS = [67, 144, 231, 311, 391]
SETTLE_Y = 160
SETTLE_MARGIN = 20
SETTLE_GOLD_MIN = 40
SETTLE_NEED = 4
READ_CAP_S = 19.5
# The medallion also shows during the intro (before the shuffle starts), so medallion votes are
# only trusted once this many seconds of the recording have elapsed; otherwise the intro burst
# would lock the START slot and we would answer the wrong one.
REVEAL_GUARD_S = 5.0
ROW_BAND = (slice(100, 225), slice(40, 410))


def settle_vote(votes, reading):
    """Accumulate consecutive valid settled readings; None breaks the voting streak."""
    if reading is None:
        votes.clear()
        return False
    votes.append(reading)
    tail = votes[-SETTLE_NEED:]
    return len(tail) == SETTLE_NEED and len(set(tail)) == 1


def read_settled(f):
    hsv = cv2.cvtColor(f, cv2.COLOR_BGR2HSV)
    H, S, V = (hsv[..., i].astype(int) for i in range(3))
    sats, golds = [], []
    for x in SETTLE_SLOTS:
        b = (slice(SETTLE_Y - 45, SETTLE_Y + 45), slice(x - 22, x + 22))
        u = (slice(SETTLE_Y - 80, SETTLE_Y - 40), slice(x - 32, x + 32))
        sats.append(float(np.median(S[b])))
        golds.append(int(((H[u] >= 15) & (H[u] <= 38) & (S[u] >= 130) & (V[u] >= 150)).sum()))
    o = sorted(range(5), key=lambda k: -(sats[k] + golds[k] / 300.0))
    if (sats[o[0]] - sats[o[1]]) < SETTLE_MARGIN or golds[o[0]] < SETTLE_GOLD_MIN:
        return None
    return o[0] + 1


def row_band(f):
    return cv2.cvtColor(f[ROW_BAND], cv2.COLOR_BGR2GRAY)
