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
    def __init__(self, gauge=0.1, dead=(), inv_open=False, porridge=True, revive_works=True, per_item=0.075, nobar=(), empty=(), alt1=True, alt2=True):
        self.gauge, self.dead, self.inv_open = gauge, set(dead), inv_open
        self.nobar = set(nobar)
        self.empty = set(empty)
        self.alt1, self.alt2 = alt1, alt2
        self.porridge, self.revive_works, self.per_item = porridge, revive_works, per_item
        self.keys, self.clicks, self.eaten = [], [], 0
        self.portraits = np.repeat(rng.randint(40, 200, (12, 33, 74, 1)), 3, axis=3).astype(np.uint8)   # textured like a face

    def frame_alive(self):
        keep, self.dead = self.dead, set()
        try:
            return self.frame()
        finally:
            self.dead = keep

    def frame(self):
        f = np.full((768, 1024, 3), 60, np.uint8)
        f[669, 89:236] = 0
        f[670:678, 89:236] = (58, 58, 62)
        n = int(round(self.gauge * 147))
        f[670:678, 89:89 + n] = (53, 168, 108)
        f[669, 150] = 0
        f[670:678, 236] = (5, 5, 6)
        for i, y0 in enumerate(vis.MERC_BAR_ROWS):
            if (i + 1) in self.empty:
                continue                                    # no unit: field shows through, no gauges
            f[y0 - 34:y0 - 1, 6:80] = self.portraits[i]
            if (i + 1) in self.dead:
                f[y0 - 34:y0 - 1, 6:80] = (self.portraits[i] * 0.45).astype(np.uint8)
                f[y0 - 1:y0 + 11, 8:76] = (20, 20, 20)      # dark band, no HP/mana gauge
            elif (i + 1) not in self.nobar:
                f[y0:y0 + 3, 6:78] = (40, 40, 200)          # red HP gauge
                f[y0 + 6:y0 + 9, 6:78] = (170, 120, 90)     # blue mana gauge
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
        if self.w.revive_works and ((k == ('alt', '1') and self.w.alt1) or (k == ('alt', '2') and self.w.alt2)):
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


def make(world, learn=True):
    s = types.SimpleNamespace()
    s.hands, s.running, s.logs = Hands(world), True, []
    s._log = s.logs.append
    s._grab_main = world.frame
    for n in ('_merc_occupied', '_park_cursor', '_close_inventory', '_eat_to_full', '_eat_to_full_inner', '_update_merc_baseline', '_revive_dead_mercs', '_prefight', '_ensure_battle_modes', '_mode_state'):
        setattr(s, n, types.MethodType(getattr(brain.Brain, n), s))
    s._MODE_SIGS = brain.Brain._MODE_SIGS
    s._MERC_FILE = os.path.join(os.environ.get('TEMP', '/tmp'), 'gato_test_merc_slots.json')
    s._merc_occupied = types.MethodType(brain.Brain._merc_occupied, s)
    s._merc_occ = set()
    if learn:
        s._update_merc_baseline(world.frame_alive())   # what the 5 s background loop does while all are alive
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
    check('dead_mercs_v2 finds slots 3 and 8', vis.dead_mercs_v2(f) == [3, 8], vis.dead_mercs_v2(f))
    check('no dead mercs when all have gauges', vis.dead_mercs_v2(World().frame()) == [])
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
    check('eat: gauge not rising -> gives up after 2 tries', w.eaten == 2, w.eaten)

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
    check('revive: dead merc -> ONE Alt+1 only (it revives everyone)', w.keys == ['alt+1'], w.keys)
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
    check('revive: capped at 3 tries per 10 min when it keeps failing', w.keys.count('alt+1') == 3, w.keys.count('alt+1'))

    w = World(gauge=0.9, dead=(2,), revive_works=False)
    s = make(w)
    s._revive_dead_mercs(w.frame())
    s._revive_dead_mercs(w.frame())
    check('revive: 15 s cooldown between tries', w.keys.count('alt+1') == 1, w.keys)

    # ---- no false Alt presses / single press ----
    w = World(gauge=0.9, dead=(2, 3, 5))
    s = make(w)
    s._prefight(w.frame())
    check('revive: 3 dead at once -> still exactly one Alt press', w.keys == ['alt+1'], w.keys)

    w = World(gauge=0.9, dead=(2,), alt1=False)
    s = make(w)
    s._prefight(w.frame())
    check('revive: Alt+1 not enough -> Alt+2 once, never both repeated', w.keys == ['alt+1', 'alt+2'], w.keys)

    w = World(gauge=0.9, empty=(10, 11, 12))
    s = make(w)
    s._prefight(w.frame())
    check('guard: empty slots at the bottom are not dead', not any(k.startswith('alt') for k in w.keys), w.keys)

    w = World(gauge=0.9, nobar=tuple(range(1, 13)))
    s = make(w)
    s._prefight(w.frame())
    check('guard: no gauge anywhere (window/loading) -> no Alt keys', not any(k.startswith('alt') for k in w.keys), w.keys)

    w = World(gauge=0.9, dead=(12,))
    s = make(w, learn=True)          # slot 12 was seen alive while learning
    w.dead = {12}
    s._prefight(w.frame())
    check('revive: last slot dead but known occupied -> revived', w.keys == ['alt+1'], w.keys)
    w = World(gauge=0.9, dead=(12,))
    s = make(w, learn=False)
    s._merc_occ = set()
    s._prefight(w.frame())
    check('guard: last slot, never seen alive -> not guessed dead', not any(k.startswith('alt') for k in w.keys), w.keys)

    w = World(gauge=0.9)
    s = make(w)
    for _ in range(20):
        s._prefight(w.frame())
    check('guard: 20 passes with everyone alive -> zero Alt keys', not any(k.startswith('alt') for k in w.keys), w.keys)

    # ---- order: revive first, then food ----
    w = World(gauge=0.1, dead=(5,))
    s = make(w)
    first = s._prefight(w.frame())
    check('order: revive runs before eating', w.keys == ['alt+1'] and w.eaten == 0 and first, (w.keys, w.eaten))
    s._prefight(w.frame())
    check('order: next pass eats', w.eaten > 0)

    print('FAILED: %s' % fails if fails else 'all passed')
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
