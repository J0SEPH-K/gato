"""Logic tests: HUD click exclusion, time-based loop counters, stray-window guard.

    python dev/test_accuracy.py
"""
import os
import sys
import types

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import detector  # noqa: E402
import vision as vis  # noqa: E402

try:
    import brain  # noqa: E402
except Exception as e:  # pragma: no cover
    brain, BRAIN_ERR = None, e


def main():
    fails = []

    def check(name, cond, extra=''):
        print(('PASS ' if cond else 'FAIL ') + name + ('' if cond else ' -- ' + str(extra)))
        if not cond:
            fails.append(name)

    # HUD exclusion: portraits, toolbar, minimap, quick slots, right buttons are never ground
    for name, (x, y) in {'portrait slot 2': (45, 80), 'portrait slot 9': (60, 380), 'top toolbar': (300, 30),
                         'minimap': (900, 120), 'quick slot': (100, 600), 'right buttons': (990, 450),
                         'bottom HUD': (500, 700)}.items():
        check('blocked: ' + name, detector.ui_blocked(x, y))
    for name, (x, y) in {'field center': (512, 340), 'field left': (150, 300), 'field right': (800, 400)}.items():
        check('free: ' + name, not detector.ui_blocked(x, y))
    coords = np.array([[45, 120], [60, 300], [400, 330]], np.float32)
    pick = detector.nearest_in_gate(coords, 1.0, center=detector.CENTER)
    check('pick skips HUD points, takes the real mob', pick is not None and int(pick[0]) == 400, pick)
    check('only HUD points -> no pick', detector.nearest_in_gate(np.array([[45, 120], [60, 300]], np.float32), 1.0, center=detector.CENTER) is None)

    # time-based search window
    w = detector.SearchWindow()
    for _ in range(10):
        w.advance(0.1)          # ten 10 ms ticks at 100 Hz = 0.1 old-loop unit each
    check('search window grows by wall-clock units, not per call', abs(w.age - 1.0) < 1e-6, w.age)
    check('search window caps at 10 units', (lambda: [w.advance(50.0), w.age][1])() == detector.SEARCH_EXPAND_FRAMES)

    if brain is None:
        print('SKIP brain tests: %r' % BRAIN_ERR)
        return 1 if fails else 0

    # stray window guard
    HDR = __import__('cv2').imread(os.path.join(ROOT, 'assets', 'ui_templates', 'inventory_header.png'))

    def frame(inv):
        f = np.full((768, 1024, 3), 60, np.uint8)
        if inv:
            x, y = vis.INV_HEADER_XY
            f[y:y + HDR.shape[0], x:x + HDR.shape[1]] = HDR
        return f

    class H:
        def __init__(self):
            self.keys, self.clicks = [], []

        def press(self, k, hold=0.05, wait=False):
            self.keys.append(k)

        def click(self, x, y, b='left', **kw):
            self.clicks.append((x, y))

    def mk():
        s = types.SimpleNamespace(hands=H(), _battle_running=False, _sub_solving=False, _log=lambda m: None)
        s._close_stray_window = types.MethodType(brain.Brain._close_stray_window, s)
        return s

    s = mk()
    check('stray window open -> Esc pressed', s._close_stray_window(frame(True), 'unknown', set()) is True and s.hands.keys == ['esc'], s.hands.keys)
    s = mk()
    check('no window, scene main -> nothing', s._close_stray_window(frame(False), 'main', set()) is False and not s.hands.keys)
    s = mk()
    s._macro_inv = True
    check('window opened by the macro itself -> left alone', s._close_stray_window(frame(True), 'unknown', set()) is False and not s.hands.keys)
    s = mk()
    s._battle_running = True
    check('during a battle -> left alone', s._close_stray_window(frame(True), 'unknown', set()) is False and not s.hands.keys)
    s = mk()
    import time as _t
    r = [s._close_stray_window(frame(True), 'unknown', set()) for _ in range(3)]
    check('rate limit: 3 immediate calls -> 1 Esc', s.hands.keys == ['esc'] and all(r), (s.hands.keys, r))
    s = mk()
    s._unk_since = _t.time() - 4.0
    check('unknown scene > 3 s with no known popup -> Esc', s._close_stray_window(frame(False), 'unknown', set()) is True and s.hands.keys == ['esc'], s.hands.keys)
    s = mk()
    s._unk_since = _t.time() - 4.0
    check('unknown scene but a known trigger is up -> leave it', s._close_stray_window(frame(False), 'unknown', {'사망'}) is False and not s.hands.keys)

    print('FAILED: %s' % fails if fails else 'all passed')
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
