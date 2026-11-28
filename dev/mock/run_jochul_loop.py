"""Drives the REAL Brain._loop with a 조철 board on screen, to prove the abstain path through the
   loop and not just through _handle_jochul. Windows modules stubbed.
   python dev/mock/run_jochul_loop.py

   Two things only the loop can show:
     A) a board that STAYS up after an abstain is re-entered at once (not left to the 5 s guard) and
        the hunt ends only on the 3rd consecutive abstain, with the reason in _stop_reason.
     B) a board that CLOSES after one abstain lets hunting resume -- no retry, no stop.
"""
import os, sys, time, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import cv2
import mock_loop as m
import brain, jochul, config

config.BASE_DIR = tempfile.mkdtemp(prefix='gato_loop_')
config.JOCHUL_FAIL_DIR = os.path.join(tempfile.mkdtemp(prefix='gato_loop_fail_'), 'jochul_fail')

base = m.base
fails = []

def check(name, cond, extra=''):
    print(('PASS ' if cond else 'FAIL ') + name + ('' if cond else ' -- ' + str(extra)))
    if not cond:
        fails.append(name)

def setup(track_answer, close_on_first_answer=False):
    """Build a Brain whose screen shows the 조철 board (both trigger pixels + the first tile), with an
    unanswerable solver unless track_answer is given.

    `close_on_first_answer` makes the board vanish the moment the solver returns, i.e. while the round
    is still in flight -- the realistic "the game took the board away" case."""
    notes, t0 = [], time.time()
    state = {'closed': False}
    hands = m.FakeHands()
    hands.move_nofg = lambda *a, **k: True
    eng = m.FakeEngine(); eng.hwnd = 1
    brain.find_window = lambda: 1
    vis = m.FakeVision()
    vis.snapshot = lambda: {'scene': 'main', 'triggers': ['조철 출현']}
    vis.note = lambda *a, **k: notes.append(a[-1])
    b = brain.Brain(eng, vis, hands, note=lambda s: notes.append(s))
    b.detector = m.FakeDet([[520, 340]])
    b.detector.ready = True
    b._save_count = lambda: None
    solved = {}
    class Solver:
        ready = True
        def solve_tracked(self, frames, times, first):
            solved['calls'] = solved.get('calls', 0) + 1
            if close_on_first_answer:
                state['closed'] = True
            return track_answer, 'ok (mock tracker)'
        def _detect_missing(self, frames):
            return [None] * len(frames), [None] * len(frames)
    b.jochul_solver = Solver()
    jochul.record_all = lambda hwnd, duration=jochul.DURATION_S, stop=None, on_frame=None: (
        time.sleep(0.3), ([np.full((351, 447, 3), (40, 100, 40), np.uint8)] * 60, [i * 0.05 for i in range(60)]))[1]
    # the board: the two trigger pixels the loop and the abstain path read, plus the first tile so the
    # round reaches the tracker instead of dying at the first-tile check.
    def cap():
        f = np.full((768, 1024, 3), (40, 100, 40), np.uint8)
        for (dx, dy), c in zip(((0, 0), (1, 0), (0, 1), (1, 1)), jochul._PAT1):
            f[jochul.REGION[1] + 100 + dy, jochul.REGION[0] + 130 + dx] = c
        if not state['closed']:
            f[43, 513] = (51, 50, 50)
            f[43, 514] = (45, 44, 44)
        return f
    eng.snapshot = cap
    b._cap = cap
    brain.grab_hwnd = lambda h, normalize=True: cap()
    return b, notes, solved

def run(track_answer, seconds, close_on_first_answer=False):
    b, notes, solved = setup(track_answer, close_on_first_answer)
    b.start()
    time.sleep(seconds)
    alive = b.running
    b.stop()
    return b, notes, solved, alive

# A) board never closes, solver never answers -> abstain, retry, abstain, retry, abstain, stop.
#    Each abstain burns ~2 s of solve plus the 1.2 s board-up sleep, then _stop_bot waits its 8 s
#    STOP_GRACE, so the loop needs ~16 s before its own _shutdown_at check can fire.
b, notes, solved, alive = run(None, 26.0)
abstains = [n for n in notes if '기권' in n]
check('A: three abstains were reached', len(abstains) >= 3, len(abstains))
check('A: the board was re-entered instead of waiting the 5 s guard', solved.get('calls', 0) >= 3, solved)
check('A: the hunt actually ended (loop exited)', not alive, alive)
check('A: reason names 조철 + the 3-strike count', '조철 3회 연속 기권' in (getattr(b, '_stop_reason', None) or ''), b._stop_reason)
check('A: counter is clean for a restart', getattr(b, '_jochul_abstain_n', -1) == 0, getattr(b, '_jochul_abstain_n', -1))
check('A: no guess click was ever made', not [h for h in b.hands.log if h[0] == 'click'], b.hands.log[:3])
print('  A: %d abstains, %d solve attempts, stop_reason=%r' % (len(abstains), solved.get('calls', 0), getattr(b, '_stop_reason', None)))

# B) the board is taken away during the round -> one abstain, hunting resumes, counter stays at 1
b, notes, solved, alive = run(None, 10.0, close_on_first_answer=True)
abstains = [n for n in notes if '기권' in n]
check('B: exactly one abstain', len(abstains) == 1, abstains[:4])
check('B: hunting resumed (still running, no stop armed)', alive and getattr(b, '_shutdown_at', 'missing') is None, (alive, getattr(b, '_shutdown_at', 'missing')))
check('B: no retry was requested once the board was gone', getattr(b, '_jochul_retry', None) is False, getattr(b, '_jochul_retry', None))
check('B: counter held at 1, not advanced', getattr(b, '_jochul_abstain_n', -1) == 1, getattr(b, '_jochul_abstain_n', -1))

print('FAILED: %s' % fails if fails else 'all passed')
sys.exit(1 if fails else 0)
