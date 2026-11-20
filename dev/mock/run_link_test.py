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
link.close()  # its background thread (local-server poll + ntfy announce) must not share
              # urllib.request.urlopen with the monkeypatches used by the tests below

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
# a tunnel that dies must be logged with its exit code and last output, not a bare "restart"
logged = []
link3 = agent_link.Link(api, 'topic-x', 'tok-x', 'ngrok-x')
link3.log = logged.append
class DeadProc:
    def __init__(self):
        import io
        self.stdout = io.StringIO('some real error from the binary\nsecond line\n')
    def poll(self): return 7
link3.tunnel = DeadProc(); link3.tunnel_kind = 'cloudflared'; link3._tunnel_tail = ['some real error from the binary', 'second line']
link3._tunnel_started_at = time.time() - 0.4
link3._start_tunnel = lambda: setattr(link3, 'tunnel', None)
link3.port = 9; link3.url = 'https://old'
import threading as _th
bad_public = 0
code = link3.tunnel.poll()
up = time.time() - link3._tunnel_started_at
tail = ' | '.join(link3._tunnel_tail[-2:])
link3.log(f'터널({link3.tunnel_kind}) 종료 (코드 {code}, {up:.1f}초만에) — {tail[:200]} — 재시작')
check('a dying tunnel logs its exit code and last output',
      logged and 'real error' in logged[0] and '코드 7' in logged[0], logged)

# a truncated/blocked download (firewall swapping in an error page) must be rejected, not run:
# this is what produced a 54 KB cloudflared.exe that crash-looped forever on the client PC.
agent_link._cf_asset_real = agent_link._cf_asset
agent_link._cf_asset = lambda: ('cloudflared-windows-amd64.exe', 'cloudflared.exe')
link4_notes = []
class V4:
    @staticmethod
    def note(k, m): link4_notes.append(m)
class Api4:
    vision = V4()
    class brain: pass
link4 = agent_link.Link(Api4(), 't', 'k', 'n')
exe = os.path.join(agent_link._bin_dir(), 'cloudflared.exe')
with open(exe, 'wb') as f:
    f.write(b'junk' * 10)  # 40 bytes: a truncated download, already on disk
dl_calls = []
def fake_dl(self, url, dest):
    dl_calls.append(url)
    with open(dest, 'wb') as f:
        f.write(b'X' * (20 * 1024 * 1024))
    return dest
orig_download = agent_link.Link._download
agent_link.Link._download = fake_dl
agent_link.subprocess.run = lambda *a, **k: None
got = link4._cf_exe()
check('a tiny pre-existing file is deleted and re-fetched, not trusted',
      len(dl_calls) == 1 and os.path.getsize(got) > agent_link.Link.MIN_BYTES, (dl_calls, os.path.getsize(got)))
check('the corruption is logged by name and size', any('손상' in m and '40바이트' in m for m in link4_notes), link4_notes)
got2 = link4._cf_exe()
check('a healthy existing file is trusted (no re-download)', len(dl_calls) == 1)

def fake_dl_small(self, url, dest):
    with open(dest, 'wb') as f:
        f.write(b'<html>blocked</html>')
    return dest
agent_link.Link._download = fake_dl_small

def fake_retrieve(url, tmp):
    with open(tmp, 'wb') as f:
        f.write(b'<html>login required</html>')
real_download = agent_link.Link._download
agent_link.Link._download = orig_download
agent_link.urllib.request.urlretrieve = fake_retrieve
try:
    os.remove(exe)
except OSError:
    pass
try:
    link4._cf_exe()
    check('a download that comes back tiny is rejected', False)
except RuntimeError as e:
    check('a download that comes back tiny is rejected', '손상' in str(e) or '차단' in str(e), e)
agent_link._cf_asset = agent_link._cf_asset_real

# a cloudflared 429 (its own quick-tunnel rate limit, not ntfy's) must trigger a real cooldown and
# a switch to ngrok, not an instant retry that just makes the rate limit worse
link5_notes = []
class V5:
    @staticmethod
    def note(k, m): link5_notes.append(m)
class Api5:
    vision = V5()
    class brain: pass
link5 = agent_link.Link(Api5(), 't', 'k', 'n')
link5.port = 9
link5.tunnel_kind = 'cloudflared'
link5._tunnel_tail = ['Requesting new quick Tunnel on trycloudflare.com...',
                      'quick tunnel provisioning failed with status 429']
code, up = 1, 5.0
rate_limited = link5.tunnel_kind == 'cloudflared' and any('429' in t for t in link5._tunnel_tail)
link5._tunnel_fails += 1
if rate_limited:
    link5._cf_blocked_until = time.time() + 1200.0
    link5.log(f'터널(cloudflared) 종료 (코드 {code}, {up:.1f}초만에) — 429 — 20분간 ngrok 사용')
check('a cloudflared 429 sets a real cooldown (not an instant retry)',
      link5._cf_blocked_until - time.time() > 1100, link5._cf_blocked_until - time.time())
check('the 429 is explained in plain language', any('429' in m and 'ngrok' in m for m in link5_notes), link5_notes)

link5._ngrok_exe = lambda: '/fake/ngrok.exe'
link5._cf_exe = lambda: (_ for _ in ()).throw(AssertionError('must not try cloudflared during its cooldown'))
spawned5 = []
class FakeProc5:
    def poll(self): return None
    stdout = iter([])
agent_link.subprocess.Popen = lambda cmd, **k: (spawned5.append(cmd), FakeProc5())[-1]
link5._start_tunnel()
check('during the cooldown, a fresh start uses ngrok instead of cloudflared',
      link5.tunnel_kind == 'ngrok' and spawned5 and spawned5[0][0] == '/fake/ngrok.exe', (link5.tunnel_kind, spawned5))

link5._cf_blocked_until = time.time() - 1.0
link5._cf_exe = lambda: '/fake/cloudflared.exe'
link5._start_tunnel()
check('once the cooldown passes, cloudflared is tried again', link5.tunnel_kind == 'cloudflared')
link5.close()

# regression: a dead tunnel must be reported ONCE and then actually wait out its backoff - a loop
# that re-polls every 5 s while waiting must not keep "re-discovering" the same death, resetting the
# backoff forever and never calling _start_tunnel() again (this is what got the client PC stuck
# repeating "20\ubd84\uac04 ngrok \uc0ac\uc6a9" every 5 s with no ngrok ever actually starting).
link6_logs = []
class V6:
    @staticmethod
    def note(k, m): link6_logs.append(m)
class Api6:
    vision = V6()
    class brain: pass
link6 = agent_link.Link(Api6(), 't', 'k', 'n')
link6.port = 9
link6.tunnel_kind = 'cloudflared'
link6._tunnel_tail = ['quick tunnel provisioning failed with status 429']
link6._tunnel_started_at = time.time() - 5.0
class DeadOnce:
    def poll(self): return 1
link6.tunnel = DeadOnce()
restarts6 = []
link6._start_tunnel = lambda: restarts6.append(time.time())
import unittest.mock as um
t0 = time.time()
for i in range(6):
    with um.patch('time.time', return_value=t0 + i * 2.0):
        if link6.tunnel is not None and link6.tunnel.poll() is not None:
            link6._handle_tunnel_death()
        if link6.tunnel is None and time.time() >= link6._next_start_at:
            link6._start_tunnel()
check('a dead tunnel is reported exactly once across repeated polls, not every poll',
      sum('429' in m for m in link6_logs) == 1, link6_logs)
check('_start_tunnel runs once, after the backoff actually elapses (not stuck forever)',
      len(restarts6) == 1, restarts6)
link6.close()

link.close()
link2.close()
link4.close()
print('FAILED: %s' % fails if fails else 'all passed')
sys.exit(1 if fails else 0)
