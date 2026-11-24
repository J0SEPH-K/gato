"""cv2 5.0 hands back (h, w, 1) for IMREAD_GRAYSCALE, which made every
revive-popup score 0.0 on the client PC while macOS cv2 5.1 returned (h, w)
and every offline test passed. The loader must normalise both."""
import numpy as np
import pytest

import vision


@pytest.fixture(autouse=True)
def _reset(monkeypatch, tmp_path):
    mask = np.zeros((52, 260), np.uint8)
    mask[5:20, 5:60] = 255
    p = tmp_path / 'revive_text_mask.png'
    p.write_bytes(b'')
    monkeypatch.setattr(vision, '_REVIVE_MASK_PATH', str(p))
    monkeypatch.setattr(vision, '_revive_mask', None)
    return mask


def _patch_imread(monkeypatch, arr):
    monkeypatch.setattr(vision.cv2, 'imread', lambda *a, **k: arr.copy())


def test_two_d_imread_is_accepted(monkeypatch, _reset):
    _patch_imread(monkeypatch, _reset)
    m = vision._load_revive_mask()
    assert m is not None and m.shape == (52, 260)


def test_three_d_imread_is_squeezed(monkeypatch, _reset):
    _patch_imread(monkeypatch, _reset[:, :, None])
    m = vision._load_revive_mask()
    assert m is not None and m.shape == (52, 260)


def test_squeezed_mask_scores_above_floor(monkeypatch, _reset):
    _patch_imread(monkeypatch, _reset[:, :, None])
    frame = np.zeros((768, 1024, 3), np.uint8)
    warm = np.array([120, 140, 160], np.uint8)   # BGR inside the _warm_fill window
    for box in (vision.REVIVE_OK_BOX, vision.REVIVE_CANCEL_BOX):
        bx0, by0, bx1, by1 = box
        frame[by0:by1, bx0:bx1] = warm
    x0, y0, x1, y1 = vision.REVIVE_TEXT_BOX
    assert (y1 - y0, x1 - x0) == (52, 260)
    frame[y0:y1, x0:x1][5:20, 5:60] = 255
    tpl = vision._load_revive_mask()
    assert tpl.shape == (52, 260)
    assert vision.find_revive_popup(frame)[0] == 'ok'
