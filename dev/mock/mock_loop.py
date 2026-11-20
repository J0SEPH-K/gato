"""Runs the real Brain loop on a Mac/Linux with fake capture, hands and detector (Windows modules stubbed).
   python dev/mock/run_dummy_scenarios.py"""
import sys, time, threading, types
import os
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
import mac_stub
import numpy as np, cv2
import brain, config, detector, vision
base = cv2.imread(os.path.join(HERE, 'main_scene.png'))
assert base is not None and base.shape[:2] == (768, 1024)

class FakeEngine:
    hwnd = 1; _frame_id = 0
    def __init__(self): self.mode = 'main'
    def snapshot(self):
        FakeEngine._frame_id += 1
        return base.copy()
    def wait_new(self, last, timeout=0.03): time.sleep(0.016); return self._frame_id
class FakeHands:
    guard_enabled = False
    def __init__(self): self.log = []
    def click(self, x, y, button='left', **k): self.log.append(('click', time.time(), x, y, button)); return True
    def press(self, *a, **k): self.log.append(('press', time.time(), a)); return True
    def combo(self, *a, **k): self.log.append(('combo', time.time(), a)); return True
    def move(self, *a, **k): return True
    def __getattr__(self, n): return lambda *a, **k: True
class FakeDet:
    ready = True
    def __init__(self, pts): self.pts = pts
    def detect(self, img, **k): return np.array(self.pts, np.float32).reshape(-1, 2)

class FakeVision:
    """Scene always 'main', no triggers: the field before the click is answered."""
    def snapshot(self): return {'scene': 'main', 'triggers': []}
    def note(self, *a, **k): pass
    def reset(self): pass

def make(pts):
    b = brain.Brain.__new__(brain.Brain)
    brain.Brain._build_detectors = lambda self: None
    brain.Brain._preload_async = lambda self: None
    return b

def run_scenario(title, seconds, pts, scene_fn=None):
    def _bd(self):
        self.fire_roi = config.mob_fire_roi(self.monster); self.fire_rect = config.mob_fire_rect(self.monster)
        self.trust_avoid = config.mob_trust_avoid(self.monster); self.ignore_dummy = config.mob_ignore_dummy(self.monster)
        self._stop_triggers = brain.STOP_TRIGGERS; self.detector = None; self.box_click = False
    brain.Brain._build_detectors = _bd
    brain.Brain._preload_async = lambda self: None
    notes = []
    eng, hands, vis = FakeEngine(), FakeHands(), FakeVision()
    if scene_fn: vis.snapshot = scene_fn
    vis.note = lambda *a, **k: notes.append((time.time(), a[-1]))
    b = brain.Brain(eng, vis, hands, note=lambda m: notes.append((time.time(), m)))
    b.detector = FakeDet(pts)
    b.detector.ready = True
    b._save_count = lambda: None
    b._grab_main = lambda normalize=True: base.copy()
    b.start()
    time.sleep(seconds)
    alive = b.running
    b.stop()
    return b, hands, notes, alive
