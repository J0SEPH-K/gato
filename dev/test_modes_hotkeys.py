"""Logic tests (no keys sent to the game): auto 전투모드/거래차단 before a fight, and F3/F4/F10 hotkeys.

    .venv\\Scripts\\python dev\\test_modes_hotkeys.py

NOTE: writes battle_modes into prism_settings.json (leaves it True).
"""
import sys, types, time
import os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, ROOT)
import numpy as np
import brain, config, vision

def frame(b, t, chat=False):
    f = np.full((768, 1024, 3), 30, np.uint8)
    def put(x, y, vals):
        f[y, x] = vals
    # B region: two pixels at (849,716),(850,716)
    if b is True:  put(849, 716, (250, 250, 250)), put(850, 716, (250, 250, 250))   # 1500
    elif b is False: put(849, 716, (1, 1, 1)), put(850, 716, (1, 1, 1))              # 6
    else: put(849, 716, (90, 90, 90)), put(850, 716, (90, 90, 90))
    if t is True:  put(947, 714, (250, 250, 250)), put(948, 714, (250, 250, 250))   # 1500
    elif t is False: put(947, 714, (39, 39, 39)), put(948, 714, (38, 39, 39))        # 233
    else: put(947, 714, (90, 90, 90)), put(948, 714, (90, 90, 90))
    return f

class FH:
    def __init__(self): self.keys = []
    def press(self, k, hold=0.05, wait=False): self.keys.append(k)

def run(name, before, after=None, setting=True, chat_state='inactive'):
    s = config.load(); s['battle_modes'] = setting; config.save(s)
    logs = []
    stub = types.SimpleNamespace(hands=FH(), _log=logs.append, _grab_main=lambda: after if after is not None else before)
    stub._mode_state = lambda fr, k: brain.Brain._mode_state(stub, fr, k)
    stub._MODE_SIGS = brain.Brain._MODE_SIGS
    orig = vision.chat_hangul_state
    vision.chat_hangul_state = lambda fr: chat_state
    try:
        brain.Brain._ensure_battle_modes(stub, before)
    finally:
        vision.chat_hangul_state = orig
    print('%-34s keys=%s %s' % (name, stub.hands.keys, logs[-1] if logs else ''))
    return stub.hands.keys

ON = frame(True, True)
r = []
r.append(run('both OFF -> press a, x', frame(False, False), ON) == ['a', 'x'])
r.append(run('both ON -> nothing', ON) == [])
r.append(run('mode OFF, ban ON -> a only', frame(False, True), ON) == ['a'])
r.append(run('mode ON, ban OFF -> x only', frame(True, False), ON) == ['x'])
r.append(run('unknown sums -> nothing', frame(None, None)) == [])
r.append(run('chat has focus -> nothing', frame(False, False), ON, chat_state='korean') == [])
r.append(run('setting off -> nothing', frame(False, False), ON, setting=False) == [])
r.append(run('still OFF after press reported', frame(False, True), frame(False, True)) == ['a'])
s = config.load(); s['battle_modes'] = True; config.save(s)

# the undo reactions must be skipped when battle_modes is on
calls = []
stub = types.SimpleNamespace(hands=FH(), _log=lambda m: None, _react_at={}, monster='x')
saved = dict(brain.REACTIONS)
brain.REACTIONS['B모드'] = (lambda h: calls.append('B'), 0, 'x'); brain.REACTIONS['T밴(거래차단)'] = (lambda h: calls.append('T'), 0, 'x')
brain.Brain._do_reactions(stub, {'B모드', 'T밴(거래차단)'})
print('undo reactions with battle_modes on ->', calls); r.append(calls == [])
s['battle_modes'] = False; config.save(s)
brain.Brain._do_reactions(stub, {'B모드'})
print('undo reaction with battle_modes off ->', calls); r.append(calls == ['B'])
s['battle_modes'] = True; config.save(s)

# F3 / F4 hotkeys: synthetic key events must reach GetAsyncKeyState
import prism, ctypes
class FakeBrain: running = False
class FakeVision:
    def note(self, k, t): pass
evs = []
class FakeApi:
    brain = FakeBrain(); vision = FakeVision()
    def start(self): evs.append('start'); FakeApi.brain.running = True
    def stop(self): evs.append('stop'); FakeApi.brain.running = False
pressed = {}
class FakeUser32:
    def GetAsyncKeyState(self, vk): return 0x8000 if pressed.get(vk) else 0
class FakeWin: user32 = FakeUser32()
ctypes.windll = FakeWin()      # scripted key state: no real key is ever sent to the game
prism.start_f10_hotkey(FakeApi())
def tap(vk):
    pressed[vk] = True; time.sleep(0.12); pressed[vk] = False; time.sleep(0.5)
tap(115)   # F4 while stopped -> nothing
tap(114)   # F3 -> start
tap(114)   # F3 while running -> nothing
tap(115)   # F4 -> stop
tap(121)   # F10 -> toggle -> start
tap(121)   # F10 -> toggle -> stop
evs_f = list(evs)
print('hotkey events:', evs_f)
r.append(evs_f == ['start', 'stop', 'start', 'stop'])
print('RESULT', 'ALL PASS' if all(r) else 'FAIL %s' % r)
