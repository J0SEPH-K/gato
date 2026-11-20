# Decompiled with PyLingual (https://pylingual.io)
# Internal filename: 'jochul.py'
# Bytecode version: 3.11a7e (3495)
# Source timestamp: 2026-08-17 09:30:58 UTC (1786959058)

import threading
import time
from collections import Counter
import numpy as np
REGION = (287, 231, 734, 582)
PARK_XY = (292, 167)
CLICK_Y = 373
CLICK_X = {1: 352, 2: 432, 3: 512, 4: 592, 5: 672}
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
def find_marker_slot(region_img):
    """Slot (1-5) under the floating gold 마패 medallion, or None. Skin-independent: it looks for the
    medallion's colour, not for the character sprite (the pixel pattern in find_first_tile is the
    navy hair of one skin). The medallion bobs, so call it on several frames and vote (see vote_marker)."""
    import cv2
    hsv = cv2.cvtColor(np.ascontiguousarray(region_img), cv2.COLOR_BGR2HSV)
    m = ((hsv[..., 0] >= 14) & (hsv[..., 0] <= 30) & (hsv[..., 1] >= 140) & (hsv[..., 2] >= 170)).astype(np.uint8)
    n, _, st, cen = cv2.connectedComponentsWithStats(m, 8)
    best = None
    for i in range(1, n):
        a = int(st[i, 4])
        if 60 <= a <= 900 and (best is None or a > best[0]):
            best = (a, float(cen[i][0]))
    if best is None:
        return None
    xs = [CLICK_X[k] - REGION[0] for k in (1, 2, 3, 4, 5)]
    return 1 + int(np.argmin([abs(best[1] - x) for x in xs]))


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

    def solve_tracked(self, frames, times, first_slot, conf=0.20, gate=150.0, decay=0.8):
        """Primary live answer (see the note above TRACK_SLOT_X): velocity-predicted Hungarian
        tracking of the YOLO detector's own centroids through the whole scatter."""
        dets = self.detect_centroids(frames, conf=conf)
        return track_centroids(times, dets, first_slot, gate=gate, decay=decay)
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


def record_all(hwnd, duration=DURATION_S, stop=None, max_fps=MAX_REC_FPS):
    """Keep EVERY distinct game frame for `duration` seconds (not a fixed 15 Hz sample).
    Returns (crops, times); times are seconds since the first poll. Needs the WGC capture session
    (it counts frames); falls back to ~30 Hz polling of the normal grab if WGC is unavailable."""
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


def _in_row(pts):
    return len(pts) >= 5 and np.std([p[1] for p in pts]) < 14 and abs(np.median([p[1] for p in pts]) - TRACK_ROW_Y) < 40


def track_centroids(times, dets, start_slot, gate=150.0, decay=0.8):
    """dets: per-frame list of (x, y) character centroids (from the YOLO detector, not background
    blobs). Returns (final slot 1-5 of the character that started at start_slot, info string), or
    (None, reason) if no usable start/end row was found."""
    s = next((i for i, d in enumerate(dets) if _in_row(d)), None)
    e = next((i for i in range(len(dets) - 1, -1, -1) if _in_row(dets[i])), None)
    if s is None or e is None or e <= s:
        return None, 'no start/end row found'
    pos = np.array(sorted(dets[s], key=lambda p: p[0])[:5] if len(dets[s]) == 5
                   else sorted(dets[s], key=lambda p: abs(p[1] - TRACK_ROW_Y))[:5])
    pos = pos[np.argsort(pos[:, 0])]
    vel = np.zeros((5, 2))
    last = times[s]
    coast = 0
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
        else:
            pos = pred
            vel *= decay
            coast += 5
    fin = np.array(sorted(dets[e], key=lambda p: abs(p[1] - TRACK_ROW_Y))[:5])
    fin = fin[np.argsort(fin[:, 0])]
    C = np.linalg.norm(pos[:, None, :] - fin[None, :, :], axis=2)
    r, c = _assign_optimal(C)
    m = {int(a): int(b) + 1 for a, b in zip(r, c)}
    return m.get(start_slot - 1), 'ok (coasted %d track-frames)' % coast


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
