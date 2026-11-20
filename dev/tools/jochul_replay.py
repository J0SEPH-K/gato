"""Replay recorded 조철 rounds (debug/jochul_rounds/round_*/ : NNNNN.jpg + meta.json) through an offline tracker and
score the answer against the labels the macro stored (start_slot / reveal_slot / first / answer).

    python dev/tools/jochul_replay.py path/to/jochul_rounds            (all rounds)
    python dev/tools/jochul_replay.py path/to/jochul_rounds/round_X     (one round)

Pipeline: background from the scatter phase (median) -> foreground blobs (any colour) -> velocity-predicted
Hungarian matching with coasting while blobs merge -> where the track that started on the marked slot ends.
Needs numpy, opencv, scipy. Pure analysis: never touches the game.
"""
import json
import os
import sys

import cv2
import numpy as np
from scipy.optimize import linear_sum_assignment

SLOT_X = np.array([65, 145, 225, 305, 385], float)      # board-crop coordinates of the 5 slots
ROW_Y = 140.0


def load_round(d):
    meta = json.load(open(os.path.join(d, 'meta.json'), encoding='utf-8'))
    frames = [cv2.imread(os.path.join(d, '%05d.jpg' % i)) for i in range(meta['frames'])]
    return meta, np.array(meta['times'], float), frames


def blobs(mask, amin=350, amax=5200):
    m = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    n, _, st, cen = cv2.connectedComponentsWithStats(m, 8)
    return [np.array(cen[i], float) for i in range(1, n) if amin <= st[i, 4] <= amax and st[i, 2] < 110 and st[i, 3] < 110]


def foreground(frames, times, bg_from=0.35, bg_to=0.80, thr=34):
    T = times[-1]
    idx = [i for i, t in enumerate(times) if bg_from * T <= t <= bg_to * T] or list(range(len(frames)))
    med = np.median(np.stack([frames[i] for i in idx]), axis=0).astype(np.int16)
    return [(np.abs(f.astype(np.int16) - med).max(axis=2) > thr).astype(np.uint8) * 255 for f in frames]


def in_row(pts):
    return len(pts) >= 5 and np.std([p[1] for p in pts]) < 14 and abs(np.median([p[1] for p in pts]) - ROW_Y) < 40


def track(times, dets, start_slot, gate=150.0, decay=0.8):
    """dets: per frame list of (x, y). Returns (final slot of the tracked character, info)."""
    s = next((i for i, d in enumerate(dets) if in_row(d)), None)
    e = next((i for i in range(len(dets) - 1, -1, -1) if in_row(dets[i])), None)
    if s is None or e is None or e <= s:
        return None, 'no start/end row found'
    pos = np.array(sorted(dets[s], key=lambda p: p[0])[:5] if len(dets[s]) == 5 else sorted(dets[s], key=lambda p: abs(p[1] - ROW_Y))[:5])
    pos = pos[np.argsort(pos[:, 0])]
    vel = np.zeros((5, 2))
    last = times[s]
    coast = 0
    for i in range(s + 1, e + 1):
        dt = max(1e-3, times[i] - last)
        last = times[i]
        pred = pos + vel * min(dt, 0.25)
        D = np.array(dets[i]).reshape(-1, 2)
        if len(D):
            C = np.linalg.norm(pred[:, None, :] - D[None, :, :], axis=2)
            C = np.where(C > gate, 1e4, C)
            r, c = linear_sum_assignment(C)
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
    fin = np.array(sorted(dets[e], key=lambda p: abs(p[1] - ROW_Y))[:5])
    fin = fin[np.argsort(fin[:, 0])]
    C = np.linalg.norm(pos[:, None, :] - fin[None, :, :], axis=2)
    r, c = linear_sum_assignment(C)
    m = {int(a): int(b) + 1 for a, b in zip(r, c)}
    return m.get(start_slot - 1), 'ok (coasted %d track-frames)' % coast


def solve_round(d):
    meta, times, frames = load_round(d)
    masks = foreground(frames, times)
    dets = [blobs(m) for m in masks]
    start = meta.get('start_slot') or meta.get('first')
    ans, info = track(times, dets, int(start)) if start else (None, 'no start label')
    return meta, ans, info


def main(path):
    dirs = [path] if os.path.exists(os.path.join(path, 'meta.json')) else sorted(os.path.join(path, x) for x in os.listdir(path) if x.startswith('round_'))
    ok = tot = 0
    for d in dirs:
        meta, ans, info = solve_round(d)
        truth = meta.get('reveal_slot') or meta.get('truth')
        mark = ''
        if truth:
            tot += 1
            ok += (ans == truth)
            mark = 'OK' if ans == truth else 'WRONG'
        print('%s: %s fps, start=%s, macro answered=%s, tracker=%s, reveal=%s %s [%s]' % (
            os.path.basename(d), meta.get('effective_fps'), meta.get('start_slot') or meta.get('first'), meta.get('answer'), ans, truth, mark, info))
    if tot:
        print('tracker %d/%d against reveal labels' % (ok, tot))


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else '.')
