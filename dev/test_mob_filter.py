"""Mobs with a fire ring at their feet (already engaged by someone else) must never be picked.

    python dev/test_mob_filter.py
"""
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import detector  # noqa: E402


class FakeMatcher:
    def __init__(self, boxes):
        self.boxes = boxes

    def detect(self, frame):
        return [(x, y, 102, 165, 1.0, 'master_gui_n:1', 0.9) for x, y in self.boxes]


def run(boxes, burning_x, fire_rect, fire_roi=(0.5, 0.8, 28), lowf_intact=True):
    d = detector.SpriteDetector([])
    d.ready = True
    d.matcher = FakeMatcher(boxes)
    d.has_fire = lambda f, box, tag, roi=None, rect=None: box[0] in burning_x
    frame = np.zeros((768, 1024, 3), np.uint8)
    out = d.detect(frame, fire_roi=fire_roi, fire_rect=fire_rect)
    return sorted(int(c[0] - 51) for c in out)   # back to the box x (center = x + 51)


def main():
    fails = []

    def check(name, got, want):
        ok = got == want
        print(('PASS ' if ok else 'FAIL ') + name + ('' if ok else f' -- got {got}, want {want}'))
        if not ok:
            fails.append(name)

    boxes = [(664, 243), (343, 300), (216, 148), (184, 195)]
    check('tuned rect: all 3 ringed mobs dropped, the free one kept', run(boxes, {664, 216, 184}, (0.19, 0.76, 0.81, 0.98)), [343])
    check('tuned rect: nothing burning -> all kept', run(boxes, set(), (0.19, 0.76, 0.81, 0.98)), [184, 216, 343, 664])
    check('tuned rect: all burning -> none picked', run(boxes, {664, 343, 216, 184}, (0.19, 0.76, 0.81, 0.98)), [])
    check('fire filter off (roi None) -> untouched', run(boxes, {664}, None, fire_roi=None), [184, 216, 343, 664])

    import config
    missing = [m for m in config.MOB_CATALOG if config.mob_fire_roi(m) is None]
    check('every catalog mob has the fire filter on', missing, [])
    print('FAILED: %s' % fails if fails else 'all passed')
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
