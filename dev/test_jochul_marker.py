"""The 마패 medallion detector, checked against the recorded real round.

fixture meta: first=2, truth=5 (user-confirmed correct answer). The medallion is on screen only
~13% of the round and also shows during the intro over the START slot, so the two behaviours that
matter are: lock the start slot fast, and lock the REVEAL slot only after REVEAL_GUARD_S.
"""
import glob
import json
import sys

import cv2

sys.path.insert(0, '.')
import jochul


def _frames():
    return sorted(glob.glob('dev/fixtures/jochul_round1/*.jpg'))


def test_template_is_the_shipped_asset():
    tmpl = jochul._load_mapae()
    assert tmpl.shape == (65, 40), tmpl.shape
    assert int(jochul._MAPAE_MASK.sum()) // 255 == 886  # opaque pixels of the mid-bob frame


def test_detector_finds_the_medallion_on_the_start_slot():
    frames, meta = _frames(), json.load(open('dev/fixtures/jochul_round1/meta.json'))
    votes, first, polls = [], None, 0
    for polls in range(1, 46):
        if jochul.marker_lock(votes, jochul.find_marker_slot(cv2.imread(frames[polls - 1]))):
            first = votes[-1]
            break
    assert first == meta['first'] == 2
    assert polls <= 15, polls


def test_detector_locks_the_reveal_slot_after_the_guard():
    frames, meta = _frames(), json.load(open('dev/fixtures/jochul_round1/meta.json'))
    votes, answer = [], None
    for i, t in enumerate(meta['times']):
        if t < jochul.REVEAL_GUARD_S:
            continue
        if jochul.marker_lock(votes, jochul.find_marker_slot(cv2.imread(frames[i]))):
            answer = votes[-1]
            break
    assert answer == meta['truth'] == 5


def test_intro_ignored_without_the_guard():
    """Without REVEAL_GUARD_S the intro burst would answer the START slot instead of the truth."""
    frames, meta = _frames(), json.load(open('dev/fixtures/jochul_round1/meta.json'))
    votes, answer = [], None
    for i, _t in enumerate(meta['times']):
        if jochul.marker_lock(votes, jochul.find_marker_slot(cv2.imread(frames[i]))):
            answer = votes[-1]
            break
    assert answer == meta['first'] == 2
    assert answer != meta['truth']


def test_marker_lock_needs_a_burst():
    votes = []
    assert jochul.marker_lock(votes, 3) is None
    assert jochul.marker_lock(votes, None) is None
    assert jochul.marker_lock(votes, 3) == 3


def test_marker_lock_tolerates_bob_gaps():
    """The medallion blinks out between bobs; a gap must not reset an in-progress burst."""
    votes = []
    for reading in (4, None, 4, None, 4, 4):
        got = jochul.marker_lock(votes, reading)
    assert got == 4


def test_find_marker_slot_returns_none_when_absent():
    frames = _frames()
    assert jochul.find_marker_slot(cv2.imread(frames[100])) is None
