"""Unit test for vision.find_revive_popup on synthetic 1024x768 frames (no game needed).

    python dev/test_revive_popup.py
"""
import os
import sys

import cv2
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import vision  # noqa: E402

WARM = (128, 148, 161)  # BGR of the flat button face


def frame(buttons=True, text=True, only_ok=False, shift=(0, 0)):
    f = np.full((768, 1024, 3), 40, np.uint8)
    f[300:470, 350:680] = (14, 16, 18)  # dialog body
    if buttons:
        x0, y0, x1, y1 = vision.REVIVE_OK_BOX
        f[y0:y1, x0:x1] = WARM
        if not only_ok:
            x0, y0, x1, y1 = vision.REVIVE_CANCEL_BOX
            f[y0:y1, x0:x1] = WARM
    if text:
        m = vision._load_revive_mask()
        x0, y0, x1, y1 = vision.REVIVE_TEXT_BOX
        reg = f[y0 + shift[1]:y1 + shift[1], x0 + shift[0]:x1 + shift[0]]
        reg[m > 0] = (235, 235, 235)
    return f


def main():
    fails = []

    def check(name, got, want):
        ok = got == want
        print(('PASS ' if ok else 'FAIL ') + name + ('' if ok else f' -- got {got!r}, want {want!r}'))
        if not ok:
            fails.append(name)

    check('popup present -> click 확인', vision.find_revive_popup(frame()), ('ok', vision.REVIVE_CLICK_XY))
    check('text shifted 2px still ok', vision.find_revive_popup(frame(shift=(2, 1))), ('ok', vision.REVIVE_CLICK_XY))
    check('buttons but different text -> unknown, no click', vision.find_revive_popup(frame(text=False)), ('unknown', None))
    check('only one button (idle-warning style) -> none', vision.find_revive_popup(frame(only_ok=True)), None)
    check('no buttons -> none', vision.find_revive_popup(frame(buttons=False)), None)
    check('plain field -> none', vision.find_revive_popup(np.full((768, 1024, 3), 90, np.uint8)), None)
    check('missing frame -> none', vision.find_revive_popup(None), None)
    print('FAILED: %s' % fails if fails else 'all passed')
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
