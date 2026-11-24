"""jochul.track_centroids / solve_tracked: regression test against a REAL, user-confirmed-correct
client round (dev/fixtures/jochul_round1), plus synthetic edge cases for _assign_optimal.
Needs ultralytics+torch (the real model), so it's skipped (not failed) where those aren't installed.
   python dev/test_jochul_tracker.py"""
import json
import os
import sys

import numpy as np
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import jochul

fails = []


def check(name, cond, extra=''):
    print(('PASS ' if cond else 'FAIL ') + name + ('' if cond else ' -- ' + str(extra)))
    if not cond:
        fails.append(name)


# --- _assign_optimal: must match brute-force-obvious answers, including RECTANGULAR matrices
# (fewer detections than tracked points, or more) ---
sq = np.array([[1.0, 9, 9], [9, 1.0, 9], [9, 9, 1.0]])
r, c = jochul._assign_optimal(sq)
check('square matrix: picks the diagonal (cheapest)', list(zip(r.tolist(), c.tolist())) == [(0, 0), (1, 1), (2, 2)], (r, c))

fewer_cols = np.array([[0.0, 9, 9], [9, 0.0, 9], [9, 9, 9], [9, 9, 9]])  # 4 rows, 3 cols
r, c = jochul._assign_optimal(fewer_cols)
check('fewer detections than tracked points: assigns exactly 3 (not 4)', len(r) == 3 and len(c) == 3, (r, c))
check('fewer-cols case still finds the two free cheap matches', set(zip(r.tolist(), c.tolist())) >= {(0, 0), (1, 1)}, (r, c))

fewer_rows = np.array([[0.0, 9, 9, 9], [9, 0.0, 9, 9], [9, 9, 9, 9]])  # 3 rows, 4 cols
r, c = jochul._assign_optimal(fewer_rows)
check('more detections than tracked points: assigns exactly 3', len(r) == 3 and len(c) == 3, (r, c))

# --- track_centroids: synthetic case, 5 points where slot 1 and slot 2 gradually swap places
# (real characters RUN between positions over several frames; a one-frame teleport is not a fair
# test of a velocity tracker - two positions that are simply occupied, with no motion in between,
# are genuinely indistinguishable from "nobody moved", which is correct, not a bug) ---
start_row = [(65, 140), (145, 140), (225, 140), (305, 140), (385, 140)]
end_row = [(145, 140), (65, 140), (225, 140), (305, 140), (385, 140)]  # 1 and 2 swapped
times = np.linspace(0.0, 1.0, 12)
dets = []
for t in times:
    f = min(1.0, t / 0.8)
    dets.append([(65 + f * 80, 140), (145 - f * 80, 140), (225, 140), (305, 140), (385, 140)])
ans, info = jochul.track_centroids(times, dets, start_slot=1)
check('synthetic swap (gradual motion): the slot-1 character is tracked to its new slot (2)', ans == 2, (ans, info))

# a start/end row that's never found (always scattered) returns None, not a crash or a guess
scattered = [[(100, 300)], [(120, 310)]]
ans, info = jochul.track_centroids(np.array([0.0, 0.5]), scattered, start_slot=1)
check('no usable row -> None, not a silent wrong guess', ans is None, (ans, info))

# --- row fit: the anchor row must be the board's five SLOTS, not just five flat points ---
# A sixth stray detection used to be handled by `sorted(...)[:5]`, which drops whichever point sorts
# last - shifting every slot index by one and making the tracker follow the wrong character while all
# five ensemble settings agreed (5/5) on two real customer rounds, both WRONG.
stray = [(65, 140), (145, 140), (225, 140), (305, 140), (385, 140), (700, 141)]
fit = jochul._row_fit(stray)
check('a stray 6th detection is excluded, not sorted in and shifting the slots',
      fit is not None and [round(x) for x in fit[1][:, 0]] == [65, 145, 225, 305, 385], fit)

# five flat points that are NOT on the slot grid are not an anchor
check('five flat but off-grid points are rejected as an anchor',
      jochul._row_fit([(100, 140), (180, 140), (260, 140), (340, 140), (420, 140)]) is None)

# a genuine settled row with a few px of detector jitter must still fit
check('a real row with a few px of detector jitter still fits',
      jochul._row_fit([(71, 140), (140, 141), (225, 139), (309, 140), (378, 142)]) is not None)

# extrapolated end, tracked character stopped, but the row is scattered off-grid -> None
sc = [[(65, 140), (145, 140), (225, 140), (305, 140), (385, 140)]]
sc += [[(100, 300), (200, 310), (300, 320), (400, 330), (500, 340)] for _ in range(3)]
ans, info = jochul.track_centroids(np.arange(4) * 0.1, sc, start_slot=1)
check('extrapolated end on scattered points -> None (not a confident wrong grid guess)',
      ans is None, (ans, info))

# --- real labelled round: the one actual client capture confirmed correct by the user ---
# This needs the REAL torch/ultralytics, not a stub: dev/mock/mac_stub.py does
# sys.modules.setdefault('torch', MagicMock()) (and the same for ultralytics) for OTHER tests
# that only need win32 calls faked. If mac_stub is imported before this file (as the harness
# pattern `python3 -c "import mac_stub, runpy; ..."` does for every other dev/test_*.py), that
# setdefault wins the race and `import torch` below silently returns the MagicMock - no
# exception, so the old `except Exception: HAVE_MODEL=False` never caught it. The real model
# then never runs: predict() returns a MagicMock, `for bi, res in enumerate(results)` iterates
# zero times (MagicMock's default __iter__), every frame gets zero detections, and the test
# fails with "no start/end row found" - which looks exactly like a tracker regression but is a
# harness bug. Run this file directly (`python3 dev/test_jochul_tracker.py`, no mac_stub) or
# import this module before mac_stub in any combined run. Guard here so a future accidental
# mac_stub-first invocation SKIPs with a clear reason instead of reporting a fake FAIL.
try:
    import torch  # noqa: F401
    from ultralytics import YOLO  # noqa: F401
    HAVE_MODEL = (type(torch).__module__ != 'unittest.mock'
                  and type(YOLO).__module__ != 'unittest.mock')
except Exception:
    HAVE_MODEL = False

if not HAVE_MODEL:
    print('SKIP real-round test (torch/ultralytics not installed, or mac_stub.py pre-mocked '
          'them in sys.modules - run this file directly, without importing mac_stub first)')
else:
    import cv2
    fdir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixtures', 'jochul_round1')
    meta = json.load(open(os.path.join(fdir, 'meta.json'), encoding='utf-8'))
    frames = [cv2.imread(os.path.join(fdir, '%05d.jpg' % i)) for i in range(meta['frames'])]
    rtimes = np.array(meta['times'])
    model_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               'assets', 'models', 'jochul', 'jochul.pt')
    solver = jochul.JochulSolver(model_path)
    solver.preload()
    ans, info = solver.solve_tracked(frames, rtimes, meta['first'])
    check('real client round: tracker reaches the user-confirmed correct slot',
          ans == meta['truth'], (ans, meta['truth'], info))

    t0 = __import__('time').perf_counter()
    ens_ans, ens_info = solver.solve_tracked(frames, rtimes, meta['first'])
    ens_dt = __import__('time').perf_counter() - t0
    check('ensemble vote also reaches the correct slot, well inside the 10 s answer timer',
          ens_ans == meta['truth'] and ens_dt < 9.0, (ens_ans, ens_dt, ens_info))

    # a case with no usable row at all in ANY setting must come back as "uncertain" (None), not a guess
    no_data = [[] for _ in frames]
    solver.detect_centroids = lambda frames, conf=0.20: no_data
    ans2, info2 = solver.solve_tracked(frames, rtimes, meta['first'])
    check('no usable detections anywhere -> uncertain (None), not a silent guess', ans2 is None, (ans2, info2))
    # the swap-model decoders are kept only as a secondary signal - documenting here that they
    # got this SAME round wrong, so a future change must not quietly swap back to trusting them alone
    per_std, per_sens = solver._detect_missing(frames)
    old_ops = jochul.periodic_decode(jochul._resample_uniform(per_std, rtimes.tolist()),
                                      per_frame_sens=jochul._resample_uniform(per_sens, rtimes.tolist()))
    old_order = jochul.apply_swaps(old_ops)
    old_ans = old_order.index(meta['first']) + 1 if meta['first'] in old_order else None
    print('(for reference) periodic_decode on this same round answers %s (wrong) - not used for the click' % old_ans)

print('FAILED: %s' % fails if fails else 'all passed')
sys.exit(1 if fails else 0)
