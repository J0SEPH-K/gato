"""Logic tests for the pre-fight routines (revive dead mercs, eat to full, modes) against a fake game.

    .venv\\Scripts\\python dev\\test_prefight.py        (also runs on macOS if cv2/numpy are installed)

The fake world renders 1024x768 frames from state (gauge fill, merc HP bars, inventory window)
using the same geometry the macro reads, and records every key/click the macro sends.
"""
import os
import sys
import types

import cv2
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault('GATO_TEST', '1')
import vision as vis  # noqa: E402

try:
    import brain  # noqa: E402  (needs the Windows modules; skip the flow tests where unavailable)
except Exception as e:  # pragma: no cover
    brain = None
    BRAIN_ERR = e

rng = np.random.RandomState(7)
HDR = cv2.imread(os.path.join(ROOT, 'assets', 'ui_templates', 'inventory_header.png'))
ICO = cv2.imread(os.path.join(ROOT, 'assets', 'ui_templates', 'porridge_icon.png'))


class World:
    def __init__(self, gauge=0.1, dead=(), inv_open=False, porridge=True, revive_works=True, per_item=0.075):
        self.gauge, self.dead, self.inv_open = gauge, set(dead), inv_open
        self.porridge, self.revive_works, self.per_item = porridge, revive_works, per_item
        self.keys, self.clicks, self.eaten = [], [], 0
        self.portraits = rng.randint(40, 200, (12, 34, 74, 3)).astype(np.uint8)

    def frame(self):
        f = np.full((768, 1024, 3), 60, np.uint8)
        f[669, 89:236] = 0
        f[670:678, 89:236] = (58, 58, 62)
        n = int(round(self.gauge * 147))
        f[670:678, 89:89 + n] = (53, 168, 108)
        f[669, 150] = 0
        f[670:678, 236] = (5, 5, 6)
        for i, y0 in enumerate(vis.MERC_BAR_ROWS):
            f[y0 - 34:y0 - 1, 6:80] = self.portraits[i]
            if (i + 1) in self.dead:
                f[y0 - 34:y0 - 1, 6:80] = (self.portraits[i] * 0.45).astype(np.uint8)
            else:
                f[y0:y0 + 3, 6:78] = (40, 40, 200)
        if self.inv_open:
            x, y = vis.INV_HEADER_XY
            f[y:y + HDR.shape[0], x:x + HDR.shape[1]] = HDR
            if self.porridge:
                x, y = vis.INV_CELL_ICON_XY
                f[y:y + ICO.shape[0], x:x + ICO.shape[1]] = ICO
        return f


class Hands:
    def __init__(self, w):
        self.w = w

    def press(self, k, hold=0.05, wait=False):
        self.w.keys.append(k)
        if k == 'i':
            self.w.inv_open = not self.w.inv_open

    def combo(self, *k, **kw):
        self.w.keys.append('+'.join(k))
        if self.w.revive_works and k == ('alt', '2'):
            self.w.dead.clear()

    def click(self, x, y, button='left', **kw):
        self.w.clicks.append((x, y, button))
        if (x, y) == (730, 543) and self.w.inv_open:
            self.w.inv_open = False
        if button == 'right' and (x, y) == vis.INV_CELL_R1C2 and self.w.inv_open and self.w.porridge:
            self.w.gauge = min(1.0, self.w.gauge + self.w.per_item)
            self.w.eaten += 1

    def move(self, x, y, wait=False):
        pass


def make(world):
    s = types.SimpleNamespace()
    s.hands, s.running, s.logs = Hands(world), True, []
    s._log = s.logs.append
    s._grab_main = world.frame
    for n in ('_park_cursor', '_close_inventory', '_eat_to_full', '_revive_dead_mercs', '_prefight', '_ensure_battle_modes', '_mode_state'):
        setattr(s, n, types.MethodType(getattr(brain.Brain, n), s))
    s._MODE_SIGS = brain.Brain._MODE_SIGS
    return s


def main():
    fails = []

    def check(name, cond, extra=''):
        print(('PASS ' if cond else 'FAIL ') + name + ('' if cond else ' -- ' + str(extra)))
        if not cond:
            fails.append(name)

    # ---- vision readers on the fake frame ----
    w = World(gauge=0.1, dead=(3, 8))
    f = w.frame()
    check('food_fraction reads 10%', abs(vis.food_fraction(f) - 0.1) < 0.02, vis.food_fraction(f))
    check('dead_mercs finds slots 3 and 8', vis.dead_mercs(f) == [3, 8], vis.dead_mercs(f))
    check('no dead mercs when all have bars', vis.dead_mercs(World().frame()) == [])
    check('inventory_open false when closed', not vis.inventory_open(f))
    check('inventory_open true when open', vis.inventory_open(World(inv_open=True).frame()))
    check('food_fraction None when gauge absent', vis.food_fraction(np.full((768, 1024, 3), 90, np.uint8)) is None)
    if brain is None:
        print('SKIP flow tests (brain not importable here: %r)' % BRAIN_ERR)
        return 1 if fails else 0

    # ---- eat to full ----
    w = World(gauge=0.1)
    s = make(w)
    ok = s._eat_to_full()
    check('eat: ran', ok)
    check('eat: gauge ends >= 93%', w.gauge >= 0.93, w.gauge)
    check('eat: used only right-click on row1 col2', set(w.clicks) <= {(640, 172, 'right'), (730, 543, 'left')} and w.eaten >= 10, w.clicks[:3])
    check('eat: inventory closed again', not w.inv_open)
    check('eat: never pressed an Alt key', not any(k.startswith('alt') for k in w.keys), w.keys)

    w = World(gauge=0.1, porridge=False)
    s = make(w)
    ok = s._eat_to_full()
    check('eat: wrong item in row1 col2 -> no click on it', w.eaten == 0 and not [c for c in w.clicks if c[2] == 'right'], w.clicks)
    check('eat: wrong item -> inventory closed again', not w.inv_open)

    w = World(gauge=0.1, per_item=0.0)
    s = make(w)
    s._eat_to_full()
    check('eat: gauge not rising -> stops after 3 tries', w.eaten == 3, w.eaten)

    w = World(gauge=0.1, inv_open=True)
    s = make(w)
    s._eat_to_full()
    check('eat: inventory already open -> does not toggle it shut first', w.keys[:1] != ['i'] or w.eaten > 0, w.keys)

    # ---- prefight: threshold ----
    for g, expect in ((0.19, True), (0.21, False), (0.5, False)):
        w = World(gauge=g)
        s = make(w)
        s._prefight(w.frame())
        check('prefight: gauge %.0f%% -> eat=%s' % (g * 100, expect), (w.eaten > 0) == expect, (w.eaten, w.keys))

    # ---- revive ----
    w = World(gauge=0.9, dead=(2,))
    s = make(w)
    acted = s._prefight(w.frame())
    check('revive: dead merc -> Alt+1 then Alt+2, nothing else', w.keys == ['alt+1', 'alt+2'], w.keys)
    check('revive: reported as acted (skip stale click)', acted is True)
    check('revive: mercs alive afterwards', not w.dead)

    w = World(gauge=0.9)
    s = make(w)
    s._prefight(w.frame())
    check('revive: nobody dead -> no Alt keys', not any(k.startswith('alt') for k in w.keys), w.keys)

    w = World(gauge=0.9, dead=(2,), revive_works=False)
    s = make(w)
    for _ in range(6):
        s._revive_at = 0.0
        s._revive_dead_mercs(w.frame())
    check('revive: capped at 4 tries per 10 min when it keeps failing', w.keys.count('alt+1') == 4, w.keys.count('alt+1'))

    w = World(gauge=0.9, dead=(2,), revive_works=False)
    s = make(w)
    s._revive_dead_mercs(w.frame())
    s._revive_dead_mercs(w.frame())
    check('revive: 15 s cooldown between tries', w.keys.count('alt+1') == 1, w.keys)

    # ---- order: revive first, then food ----
    w = World(gauge=0.1, dead=(5,))
    s = make(w)
    first = s._prefight(w.frame())
    check('order: revive runs before eating', w.keys == ['alt+1', 'alt+2'] and w.eaten == 0 and first, (w.keys, w.eaten))
    s._prefight(w.frame())
    check('order: next pass eats', w.eaten > 0)

    print('FAILED: %s' % fails if fails else 'all passed')
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
