"""Checks agent_link's HTTP API (status/log/shot/cmd, token gate) and the hub's rendezvous bookkeeping,
without ngrok or the internet.   python dev/mock/run_link_test.py"""
import json, os, sys, time, urllib.request, urllib.error
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'tools'))
import numpy as np
import mock_loop as m
import config
config.BASE_DIR = tempfile_dir = __import__('tempfile').mkdtemp(prefix='gato_link_')
config.RES_DIR = config.BASE_DIR
import agent_link, hub

fails = []
def check(name, cond, extra=''):
    print(('PASS ' if cond else 'FAIL ') + name + ('' if cond else ' -- ' + str(extra)))
    if not cond: fails.append(name)

eng = m.FakeEngine(); eng.hwnd = 0
brain_mod = __import__('brain')
brain_mod.find_window = lambda: 0
hands = m.FakeHands()
b = brain_mod.Brain(eng, m.FakeVision(), hands, note=lambda s: None)
b.running = True; b.battle_count = 7
class Api:
    brain = b; vision = b.vision; monster = '테스트몹'
    def __init__(self): self.cmds = []
    def _run_remote(self, cmd, arg=''):
        self.cmds.append((cmd, arg)); return {'did': cmd}
api = Api()
b._grab_main = lambda: np.full((768, 1024, 3), 120, np.uint8)
with open(os.path.join(config.BASE_DIR, 'gato_debug.log'), 'w') as f:
    for i in range(200): f.write('line %d\n' % i)
link = agent_link.Link(api, 'topic-x', 'tok-x', 'ngrok-x')
link.pc = 'PC-TEST'; link.machine = 'MACH-TEST'; link.url = 'https://fake.ngrok-free.app'
link._start_tunnel = lambda: None
link.start(); time.sleep(0.6)

def req(path, tok='tok-x', data=None, timeout=10):
    r = urllib.request.Request('http://127.0.0.1:%d%s' % (agent_link.LINK_PORT, path), data=data,
                               headers={'x-gato-token': tok} if tok else {})
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        return resp.status, resp.read()

try:
    req('/status', tok='bad'); check('wrong token -> 401', False, 'got 200')
except urllib.error.HTTPError as e:
    check('wrong token -> 401', e.code == 401, e.code)
s, body = req('/status')
d = json.loads(body)
check('/status reports pc, version, running, battles', d['pc'] == 'PC-TEST' and d['running'] and d['battles'] == 7 and 'ver' in d, d)
check('/log returns the log tail', b'line 199' in req('/log?since=0')[1])
check('/log with a too-large offset falls back to the whole file', b'line 0' in req('/log?since=999999999')[1])
s, body = req('/shot')
check('/shot returns a JPEG', body[:2] == b'\xff\xd8' and len(body) > 500, body[:4])
s, body = req('/cmd', data=json.dumps({'cmd': 'stop'}).encode())
check('/cmd reaches the bot', json.loads(body)['ok'] and api.cmds == [('stop', '')], api.cmds)
check('/ping', req('/ping')[0] == 200)

seen = [json.dumps({'pc': 'A', 'machine': 'm1', 'url': 'https://a.ngrok-free.app', 'ver': '1.0.3'}, ensure_ascii=False),
        json.dumps({'pc': 'B', 'machine': 'm2', 'url': 'https://b.ngrok-free.app', 'ver': '1.0.3'})]
class R:
    def __init__(self, raw): self.raw = raw
    def read(self): return self.raw.encode()
def fake_poll(now, ages):
    raw = '\n'.join(json.dumps({'message': s, 'time': now - ages[i]}) for i, s in enumerate(seen))
    hub.urllib.request.urlopen = lambda req, timeout=0: R(raw)
    return hub.poll()
hub.STATE = os.path.join(config.BASE_DIR, 'hub_state.json')
live = fake_poll(time.time(), [0, 0])
check('hub sees both PCs at once', len(live) == 2 and {v['pc'] for v in live.values()} == {'A', 'B'}, live)
live = fake_poll(time.time(), [0, hub.STALE_SEC + 60])
check('a silent PC drops out after STALE_SEC', len(live) == 1 and list(live.values())[0]['pc'] == 'A', live)
live = fake_poll(time.time(), [0, 0])
check('picking by machine id and by name both work', hub._pick('m2', live)['pc'] == 'B' and hub._pick('a', live)['pc'] == 'A')
# status() must never raise: a half-initialised Api (no monster, brain without counters) is normal
class Raising:
    def __getattr__(self, k): raise RuntimeError('brain not built')
class Bare:
    class vision:
        @staticmethod
        def snapshot(): raise RuntimeError('no vision')
    brain = Raising()
link2 = agent_link.Link(Bare(), 't', 'k', 'n')
link2.pc = 'PC-BARE'
st = link2.status()
check('status survives a half-built Api', st['pc'] == 'PC-BARE' and st['running'] is False and st['battles'] == 0, st)
check('status names the brain problem instead of raising', 'err' in st and 'brain' in st['err'], st)
class NoBrain:
    pass
check('status survives a missing brain entirely', agent_link.Link(NoBrain(), 't', 'k', 'n').status()['battles'] == 0)

ver = os.path.join(config.BASE_DIR, 'VERSION')
open(ver, 'w').write('9.9.9\n')
check('_ver reads VERSION from the writable dir too', agent_link._ver() == '9.9.9', agent_link._ver())
os.remove(ver)
check('_ver never raises when VERSION is missing', agent_link._ver() in ('?', ''), agent_link._ver())

calls = {'n': 0}
class Boom:
    def read(self): return b'{"error":"x"}'
def flaky(req, timeout=0):
    calls['n'] += 1
    if calls['n'] < 3:
        raise urllib.error.HTTPError(req.full_url, 500, 'boom', {}, Boom())
    return type('R', (), {'read': lambda self: b'ok', '__enter__': lambda self: self, '__exit__': lambda *a: False})()
hub.urllib.request.urlopen = flaky
check('hub.get retries a 500 then succeeds', hub.get({'pc': 'P', 'url': 'https://x'}, '/status', timeout=1) == b'ok' and calls['n'] == 3, calls)
link.close()
link2.close()
print('FAILED: %s' % fails if fails else 'all passed')
sys.exit(1 if fails else 0)
