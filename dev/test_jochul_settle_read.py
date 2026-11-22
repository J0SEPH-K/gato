import glob, sys
import cv2
sys.path.insert(0, '.')
import jochul


def test_fixture_window():
    fs = sorted(glob.glob('dev/fixtures/jochul_round1/*.jpg'))
    got = {i: jochul.read_settled(cv2.imread(fs[i])) for i in range(160, 207)}
    assert all(got[i] is None for i in range(160, 169)), got
    assert all(got[i] == 5 for i in range(169, 191)), got
    assert all(got[i] is None for i in range(191, 207)), got


def test_record_all_frame_callback_stops_after_lock(monkeypatch):
    import types
    import numpy as np

    capture = types.ModuleType('capture')
    source = np.zeros((768, 1024, 3), np.uint8)
    capture.grab_hwnd = lambda hwnd, normalize=False: source.copy()
    wgc = types.ModuleType('wgc')
    wgc.available = lambda: False
    monkeypatch.setitem(sys.modules, 'capture', capture)
    monkeypatch.setitem(sys.modules, 'wgc', wgc)

    calls = []
    stopped = {'value': False}

    def on_frame(i, frame, t):
        calls.append((i, frame.shape, t))
        stopped['value'] = True

    frames, times = jochul.record_all(
        1, duration=1.0, max_fps=30, on_frame=on_frame,
        stop=lambda: stopped['value']
    )
    assert len(frames) == len(times) == 1
    assert calls[0][0] == 0 and calls[0][1] == (351, 447, 3)
    assert 0 <= calls[0][2] < 1.0


def test_none_reading_resets_consecutive_votes():
    votes = []
    locked = False
    for reading in (5, 5, 5, None, 5, 5, 5):
        locked = jochul.settle_vote(votes, reading)
        assert not locked
    assert votes == [5, 5, 5]
    assert jochul.settle_vote(votes, 5)
