"""Runs Brain._handle_jochul against fake capture/hands/solver (Windows modules stubbed).
   python dev/mock/run_jochul_flow.py"""
import os, sys, time, types
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import mock_loop as m
import brain, jochul, config

def make(tile_after, marker_slot=None, track_answer=4):
    notes, t0 = [], time.time()
    hands = m.FakeHands()
    parks = []
    hands.move_nofg = lambda *a, **k: parks.append(a) or True
    eng = m.FakeEngine(); eng.hwnd = 1
    brain.find_window = lambda: 1
    b = brain.Brain(eng, m.FakeVision(), hands, note=lambda s: notes.append(s))
    b.running = True
    solved = {}
    class Solver:
        ready = True
        def solve_tracked(self, frames, times, first):
            solved.update(n=len(frames), first=first)
            return track_answer, 'ok (mock tracker)'
        def _detect_missing(self, frames):
            return [None] * len(frames), [None] * len(frames)
    b.jochul_solver = Solver()
    # the live code now captures with jochul.record_all (wgc/capture internals, not brain.grab_hwnd),
    # so it is stubbed directly here with a plausible native-fps frame/time series
    n_fake = 300
    def _fake_record_all(hwnd, duration=jochul.DURATION_S, stop=None):
        time.sleep(1.2)  # gives the parallel RoundRecorder a realistic window to gather frames
        return [np.zeros((4, 4, 3), np.uint8)] * n_fake, [round(i * duration / n_fake, 4) for i in range(n_fake)]
    jochul.record_all = _fake_record_all
    def cap():
        f = np.full((768, 1024, 3), (40, 100, 40), np.uint8)    # plain grass: no accidental pixel patterns
        if marker_slot and int((time.time() - t0) * 25) % 5 < 2:      # medallion bobs: visible ~40% of frames
            import cv2
            cx = jochul.CLICK_X[marker_slot] - jochul.REGION[0]
            cv2.circle(f, (jochul.REGION[0] + cx, jochul.REGION[1] + 105), 9, (40, 190, 235), -1)   # BGR gold
        if tile_after < 900 and time.time() - t0 >= tile_after:
            x, y = 130, 100          # inside REGION; pattern the real first tile has
            ox, oy = jochul.REGION[0], jochul.REGION[1]
            for (dx, dy), c in zip(((0, 0), (1, 0), (0, 1), (1, 1)), jochul._PAT1):
                f[oy + y + dy, ox + x + dx] = c
        return f
    b._cap = cap
    brain.grab_hwnd = lambda h, normalize=True: cap()    # every grab (solver + recorder) goes through the fake
    return b, hands, notes, parks, solved

fails = []
def check(name, cond, extra=''):
    print(('PASS ' if cond else 'FAIL ') + name + ('' if cond else ' -- ' + str(extra)))
    if not cond: fails.append(name)

import tempfile, json
config.BASE_DIR = tempfile.mkdtemp(prefix='gato_rounds_')
# JOCHUL_FAIL_DIR is a module-level constant computed from the ORIGINAL BASE_DIR at config.py
# import time, so reassigning config.BASE_DIR above does NOT move it - every mock round whose
# answer disagrees with the (always-naive) swap decoder was silently dumping fake frames into the
# real repo's debug/jochul_fail/ (discovered 2026-11-22: 5 "live failure" dirs there all had
# track_info == 'ok (mock tracker)', i.e. they were this script, not the real game). Redirect for
# every test case, not just case 3, so this can never contaminate real evidence again.
config.JOCHUL_FAIL_DIR = os.path.join(tempfile.mkdtemp(prefix='gato_jochul_fail_'), 'jochul_fail')
# 1) tile visible at once
b, hands, notes, parks, solved = make(0.0)
t = time.time(); b._handle_jochul(); el = time.time() - t
clicks = [h for h in hands.log if h[0] == 'click']
check('tile visible: first tile found', any('첫 마패: 2번' in n for n in notes), notes[:4])
check('parked cursor first', parks and parks[0] == jochul.PARK_XY)
check('captured with record_all (all-native-frame), ~300 fake frames', solved.get('n', 0) == 300, solved)
check('answer 4 -> two clicks at x=%d' % jochul.CLICK_X[4], len(clicks) == 2 and all(c[2] == jochul.CLICK_X[4] and c[3] == jochul.CLICK_Y for c in clicks), clicks)
check('popup-closed message logged (not called a pass)', any('조철 클릭 후 창 닫힘' in n for n in notes))
print('  flow took %.1f s' % el)
rd = os.path.join(config.BASE_DIR, 'debug', 'jochul_rounds')
dirs = sorted(os.listdir(rd)) if os.path.isdir(rd) else []
check('round recording saved', len(dirs) == 1, dirs)
if dirs:
    meta = json.load(open(os.path.join(rd, dirs[0], 'meta.json'), encoding='utf-8'))
    check('recording has frames + times + labels', meta['frames'] > 10 and len(meta['times']) == meta['frames'] and meta.get('answer') == 4 and meta.get('first') == 2, {k: meta.get(k) for k in ('frames', 'answer', 'first', 'mode', 'effective_fps', 'seconds')})
    check('frame files readable', len([f for f in os.listdir(os.path.join(rd, dirs[0])) if f.endswith('.jpg')]) == meta['frames'])

# 2) marker appears 0.7 s late -> retry finds it, no stop
b, hands, notes, parks, solved = make(0.5 + 0.7)
b._handle_jochul()
check('late marker (0.7 s) still solved, not stopped', b.running and any('첫 마패' in n for n in notes) and not any('인식 실패' in n for n in notes), notes[:5])

# 2b) other skin: no navy-hair pattern at all, only the gold medallion over slot 3
b, hands, notes, parks, solved = make(999, marker_slot=3)
b._handle_jochul()
check('medallion only (other skin): first slot 3 found', any('첫 마패: 3번' in n for n in notes) and b.running, notes[:6])

# 3) marker never appears -> stops, saves frame
b, hands, notes, parks, solved = make(999)
b._handle_jochul()
check('no marker: macro stops with a clear reason', (not b.running) and any('첫 마패 인식 실패' in n for n in notes), notes[:5])
check('no marker: frame saved for diagnosis', os.path.isdir(config.JOCHUL_FAIL_DIR) and any(f.startswith('first_tile_miss') for f in os.listdir(config.JOCHUL_FAIL_DIR)))
print('FAILED: %s' % fails if fails else 'all passed')
sys.exit(1 if fails else 0)
