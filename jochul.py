# Decompiled with PyLingual (https://pylingual.io)
# Internal filename: 'jochul.py'
# Bytecode version: 3.11a7e (3495)
# Source timestamp: 2026-08-17 09:30:58 UTC (1786959058)

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