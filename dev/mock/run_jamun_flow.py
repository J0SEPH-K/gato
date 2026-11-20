"""Runs Brain._handle_jamun (자동방지문자) against fake capture/hands/reader and checks the typed keys, the clicks and
the evidence record.   python dev/mock/run_jamun_flow.py"""
import json, os, sys, tempfile, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import mock_loop as m
import brain, config

config.BASE_DIR = tempfile.mkdtemp(prefix='gato_jamun_')
config.JAMUN_DIR = os.path.join(config.BASE_DIR, 'debug', 'jamun')
fails = []
def check(name, cond, extra=''):
    print(('PASS ' if cond else 'FAIL ') + name + ('' if cond else ' -- ' + str(extra)))
    if not cond: fails.append(name)

def make(reads, wrong_dialog=False):
    eng = m.FakeEngine(); eng.hwnd = 0
    brain.find_window = lambda: 0
    hands = m.FakeHands()
    b = brain.Brain(eng, m.FakeVision(), hands, note=lambda s: None)
    b.running = True
    class Reader:
        ready = True; last_step_conf = 0.0
        def __init__(self): self.i = 0
        def read(self, crop):
            t, c = reads[min(self.i, len(reads) - 1)]; self.i += 1; self.last_step_conf = c; return t, c
    b.text_reader = Reader()
    def frame():
        f = np.full((768, 1024, 3), (210, 215, 220), np.uint8)
        if wrong_dialog:
            f[426, 589] = (230, 230, 230); f[426, 590] = (230, 230, 230)
        return f
    b._cap = frame; b._cap_native = frame
    b._stop_now = lambda why='': setattr(b, 'running', False) or b.__dict__.setdefault('stops', []).append(why)
    return b, hands

# 1) first read confident -> typed once, confirm clicked, record saved, passed
b, hands = make([('AB3D9', 0.9992)])
b._handle_jamun()
keys = [h[2][0] for h in hands.log if h[0] == 'press']
clicks = [(h[2], h[3]) for h in hands.log if h[0] == 'click']
check('typed the read text lower-case, in order', keys == ['a', 'b', '3', 'd', '9'], keys)
check('clicked the input box then confirm', (500, 425) in clicks and clicks[-1] == (446, 478), clicks)
check('no refresh click when confident', (578, 478) not in clicks, clicks)
check('not stopped', b.running)
rd = os.path.join(config.BASE_DIR, 'debug', 'jamun_rounds'); dirs = sorted(os.listdir(rd)) if os.path.isdir(rd) else []
check('evidence record saved', len(dirs) == 1, dirs)
if dirs:
    meta = json.load(open(os.path.join(rd, dirs[0], 'meta.json'), encoding='utf-8'))
    files = os.listdir(os.path.join(rd, dirs[0]))
    check('record has attempt, text, verdict and frames', meta['attempts'][0]['text'] == 'AB3D9' and meta['submitted_text'] == 'AB3D9' and meta['wrong_dialog_seen'] is False and {'attempt1_crop.png', 'before_confirm.png', 'after_confirm_4s.png'} <= set(files), (meta, files))

# 2) low confidence -> refresh, read again, then confident
b, hands = make([('QWERT', 0.93), ('Z9X8C', 0.9991)])
b._handle_jamun()
clicks = [(h[2], h[3]) for h in hands.log if h[0] == 'click']
keys = ''.join(h[2][0] for h in hands.log if h[0] == 'press')
check('low confidence -> one refresh click, types the SECOND read', (578, 478) in clicks and keys == 'z9x8c', (clicks, keys))

# 3) wrong-answer dialog visible -> macro stops
b, hands = make([('AAAAA', 0.9999)], wrong_dialog=True)
b._handle_jamun()
check('wrong-answer dialog -> macro stops', (not b.running) and b.__dict__.get('stops'), b.__dict__.get('stops'))
print('FAILED: %s' % fails if fails else 'all passed')
sys.exit(1 if fails else 0)
