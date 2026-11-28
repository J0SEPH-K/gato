"""Runs Brain._handle_jochul against fake capture/hands/solver (Windows modules stubbed).
   python dev/mock/run_jochul_flow.py"""
import os, sys, time, types
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import cv2
import mock_loop as m
import brain, jochul, config

def make(tile_after, marker_slot=None, track_answer=4, reveal_slot=None):
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
    # The marker is the game's own Mapae sprite now, so the fake screen stamps the real decoded
    # template (a plain gold circle does not match it). It bobs: visible ~40% of frames, like the
    # client, which is what marker_lock's sliding window exists for.
    tmpl = jochul._load_mapae()
    mask = jochul._MAPAE_MASK
    bgr = cv2.cvtColor(tmpl, cv2.COLOR_GRAY2BGR)

    def _stamp(img, slot, ox, oy):
        cx = ox + jochul.CLICK_X[slot] - jochul.REGION[0]
        x0, y0 = cx - bgr.shape[1] // 2, oy + 20
        sub = img[y0:y0 + bgr.shape[0], x0:x0 + bgr.shape[1]]
        m = mask[:sub.shape[0], :sub.shape[1]] > 0
        sub[m] = bgr[:sub.shape[0], :sub.shape[1]][m]

    # the live code now captures with jochul.record_all (wgc/capture internals, not brain.grab_hwnd),
    # so it is stubbed directly here with a plausible native-fps frame/time series
    n_fake = 300

    def _fake_record_all(hwnd, duration=jochul.DURATION_S, stop=None, on_frame=None):
        time.sleep(0.4)  # gives the parallel RoundRecorder a realistic window to gather frames
        frames, times = [], []
        for i in range(n_fake):
            t = round(i * duration / n_fake, 4)
            f = np.full((351, 447, 3), (40, 100, 40), np.uint8)
            if tile_after < 900 and t >= tile_after:
                for (dx, dy), c in zip(((0, 0), (1, 0), (0, 1), (1, 1)), jochul._PAT1):
                    f[100 + dy, 130 + dx] = c
            if marker_slot and t >= jochul.REVEAL_GUARD_S and i % 5 < 2:
                _stamp(f, marker_slot, 0, 0)
            frames.append(f)
            times.append(t)
            if on_frame is not None:
                on_frame(i, f, t)
            if stop is not None and stop():
                break
        return frames, times

    jochul.record_all = _fake_record_all
    # 조철 board "still on screen" flag: the abstain path reads the same two trigger pixels the live
    # loop reads, so the fake frame has to carry them exactly (sum 151 / 133 at 513,43 and 514,43).
    popup = {'on': False}
    def cap():
        f = np.full((768, 1024, 3), (40, 100, 40), np.uint8)    # plain grass: no accidental pixel patterns
        if popup['on']:
            f[43, 513] = (51, 50, 50)
            f[43, 514] = (45, 44, 44)
        if marker_slot and int((time.time() - t0) * 25) % 5 < 2:      # medallion bobs: visible ~40% of frames
            _stamp(f, marker_slot, jochul.REGION[0], jochul.REGION[1])
        _clicks = [h[1] for h in hands.log if h[0] == 'click']
        if reveal_slot and _clicks:
            # Post-click reveal cadence measured on real round_20261126_232228 (43.7 fps): the
            # medallion blinks with a 1.06 s period, 0.64 s visible / 0.42 s gone. Phase is pinned
            # to the last click so t=0.9 s (the old single cap() read) lands inside a gap.
            if ((time.time() - _clicks[-1]) % 1.06) < 0.64:
                _stamp(f, reveal_slot, jochul.REGION[0], jochul.REGION[1])
        if tile_after < 900 and time.time() - t0 >= tile_after:
            x, y = 130, 100          # inside REGION; pattern the real first tile has
            ox, oy = jochul.REGION[0], jochul.REGION[1]
            for (dx, dy), c in zip(((0, 0), (1, 0), (0, 1), (1, 1)), jochul._PAT1):
                f[oy + y + dy, ox + x + dx] = c
        return f
    b._cap = cap
    brain.grab_hwnd = lambda h, normalize=True: cap()    # every grab (solver + recorder) goes through the fake
    return b, hands, notes, parks, solved, popup

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
b, hands, notes, parks, solved, popup = make(0.0)
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
b, hands, notes, parks, solved, popup = make(0.5 + 0.7)
b._handle_jochul()
check('late marker (0.7 s) still solved, not stopped', b.running and any('첫 마패' in n for n in notes) and not any('인식 실패' in n for n in notes), notes[:5])

# 2b) other skin: no navy-hair pattern at all, only the gold medallion over slot 3
b, hands, notes, parks, solved, popup = make(999, marker_slot=3)
b._handle_jochul()
check('medallion only (other skin): first slot 3 found', any('첫 마패: 3번' in n for n in notes) and b.running, notes[:6])

# 3) first tile never appears -> ABSTAIN (board left alone, hunting resumes), frame saved
b, hands, notes, parks, solved, popup = make(999)
b._handle_jochul()
check('first tile miss: abstains instead of stopping', b.running and any('기권' in n for n in notes) and b._shutdown_at is None, notes[:5])
check('first tile miss: frame saved for diagnosis', os.path.isdir(config.JOCHUL_FAIL_DIR) and any(f.startswith('first_tile_miss') for f in os.listdir(config.JOCHUL_FAIL_DIR)))

# 4) tracker uncertain (None) -> abstain, NEVER click a guess (2026-11-22: the swap-decoder
# fallback this used to click measured 43% real-world accuracy on 7 logged failures - a wrong click
# is the expensive failure mode). The board is gone on this fake, so the loop must NOT ask for a
# re-entry and hunting must resume on the first abstain.
b, hands, notes, parks, solved, popup = make(0.0, track_answer=None)
b._handle_jochul()
clicks = [h for h in hands.log if h[0] == 'click']
check('uncertain tracker: abstains instead of stopping', b.running and any('기권' in n for n in notes), notes[:6])
check('uncertain tracker: NO click was made', len(clicks) == 0, clicks)
check('uncertain tracker: no retry when the board is already gone', getattr(b, '_jochul_retry', None) is False, getattr(b, '_jochul_retry', '<missing>'))
check('uncertain tracker: counter went to 1', getattr(b, '_jochul_abstain_n', None) == 1, getattr(b, '_jochul_abstain_n', '<missing>'))

# 4b) abstain with the board STILL UP -> retry flag set so the loop re-enters instead of idling
b, hands, notes, parks, solved, popup = make(0.0, track_answer=None)
popup['on'] = True
b._handle_jochul()
check('abstain with board still up: retry requested', getattr(b, '_jochul_retry', None) is True and b.running, (getattr(b, '_jochul_retry', '<missing>'), notes[:4]))

# 4c) 3 abstains in a row -> stop with the reason in _stop_reason; counter resets afterwards
b, hands, notes, parks, solved, popup = make(0.0, track_answer=None)
for _ in range(3):
    b._handle_jochul()
# _stop_bot arms the 8 s grace window; the loop's own _shutdown_at check ends the hunt.
check('three abstains in a row: stop armed', b._shutdown_at is not None and b.running, (b.running, b._shutdown_at))
check('three abstains in a row: reason names 조철 + the count', '조철 3회 연속 기권' in (b._stop_reason or ''), b._stop_reason)
check('three abstains in a row: counter reset for the next run', getattr(b, '_jochul_abstain_n', None) == 0, getattr(b, '_jochul_abstain_n', '<missing>'))

# 4d) an ANSWERED round resets the counter between abstains
b, hands, notes, parks, solved, popup = make(0.0, track_answer=None)
b._handle_jochul()
b._handle_jochul()
check('two abstains -> counter 2', getattr(b, '_jochul_abstain_n', None) == 2, getattr(b, '_jochul_abstain_n', '<missing>'))
b2, h2, n2, p2, s2, pop2 = make(0.0)
b._jochul_abstain_n = 2
b._jochul_solver = b2.jochul_solver
b._cap = b2._cap
b._handle_jochul()
check('answered round resets the counter to 0', getattr(b, '_jochul_abstain_n', None) == 0 and b.running, (getattr(b, '_jochul_abstain_n', '<missing>'), b.running))

# 5) post-click reveal read must survive the medallion's blink gap. One cap() at a fixed 0.9 s
# missed the reveal on two real field rounds (reveal_conf 0.8895/0.892 = the no-marker score);
# replaying the old read over every start offset of a real recorded reveal missed 111/286 times.
# The 1.1 s burst keeps the best-scoring frame, so it records the slot the game revealed (2 here,
# deliberately not the clicked 4) and sends no extra click.
b, hands, notes, parks, solved, popup = make(0.0, reveal_slot=2)
b._handle_jochul()
clicks = [h for h in hands.log if h[0] == 'click']
check('reveal burst: reveal_slot read through the blink gap', b._jochul_meta.get('reveal_slot') == 2,
      {k: b._jochul_meta.get(k) for k in ('reveal_slot', 'reveal_conf', 'clicked')})
check('reveal burst: no extra click from the reveal read', len(clicks) == 2, clicks)

print('FAILED: %s' % fails if fails else 'all passed')
sys.exit(1 if fails else 0)
