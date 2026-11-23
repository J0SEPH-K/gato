"""relay.py: path safety, zip building, and a full job round-trip against `wrangler dev --local` (port 8788).
Run:  python3 dev/test_relay.py   (the Worker round-trip part is skipped when nothing listens on 8788)"""
import hashlib, io, json, os, shutil, sys, tempfile, threading, time, urllib.request, zipfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'mock')); sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    import mac_stub  # noqa: F401
except Exception:
    pass
import config, relay

base = tempfile.mkdtemp(prefix='gato_relay_')
config.BASE_DIR = base
os.makedirs(os.path.join(base, 'debug', 'jochul_rounds', 'round_1'))
for i in range(1, 11):
    open(os.path.join(base, 'debug', 'jochul_rounds', 'round_1', 'frame_%04d.jpg' % i), 'wb').write(os.urandom(2000))
open(os.path.join(base, 'debug', 'jochul_rounds', 'round_1', 'meta.json'), 'w').write('{"answer":3}')
open(os.path.join(base, 'gato_debug.log'), 'w', encoding='utf-8').write('\n'.join('12:00:%02d [brain] line %d' % (i % 60, i) for i in range(400)))
open(os.path.join(base, 'prism_settings.json'), 'w').write('{"auth_id":"SECRET"}')
os.makedirs(os.path.join(base, 'debug', 'x'))
open(os.path.join(base, 'debug', 'x', 'license_token.txt'), 'w').write('SECRET')
fails = []
def chk(n, c, e=''):
    print(('PASS ' if c else 'FAIL ') + n + (' ' + str(e)[:100] if e else ''))
    if not c: fails.append(n)

def refused(p):
    try:
        relay.resolve(p); return False
    except ValueError:
        return True

chk('debug dir ok', not refused('debug/jochul_rounds/round_1'))
chk('log ok', not refused('gato_debug.log'))
chk('settings refused', refused('prism_settings.json'))
chk('parent escape refused', refused('debug/../prism_settings.json') and refused('../etc'))
chk('absolute path refused', refused('C:/Windows/system32') and refused('/etc/passwd'))
chk('secret-named file refused', refused('debug/x/license_token.txt'))
chk('empty refused', refused('') and refused('   '))
chk('arg parse', relay.parse_pull_arg('debug/a|every=5|mb=80') == ('debug/a', 5, 80 * 1024 * 1024))
z = relay.build_zip(relay.resolve('debug/jochul_rounds/round_1'), every=1)
names = zipfile.ZipFile(io.BytesIO(z)).namelist()
chk('zip has all 10 frames + meta', len(names) == 11, len(names))
z = relay.build_zip(relay.resolve('debug/jochul_rounds/round_1'), every=5)
fr = [n for n in zipfile.ZipFile(io.BytesIO(z)).namelist() if n.startswith('frame_')]
chk('every=5 keeps 2 of 10 frames', len(fr) == 2, fr)
z = relay.build_zip(relay.resolve('debug'), every=1)
chk('zip of debug never includes secret-named file', not any('license' in n for n in zipfile.ZipFile(io.BytesIO(z)).namelist()))
z = relay.build_zip(relay.resolve('debug/jochul_rounds/round_1'), every=1, max_bytes=5000)
chk('size cap truncates', '_TRUNCATED.txt' in zipfile.ZipFile(io.BytesIO(z)).namelist())
chk('tail hides gate spam', '[게이트]' not in relay.tail_lines(os.path.join(base, 'gato_debug.log')))

# ---- worker round trip ----
B = os.environ.get('RELAY_TEST_BASE', 'http://127.0.0.1:8788')
try:
    urllib.request.urlopen(B + '/health', timeout=3)
except Exception:
    print('SKIP worker round-trip (no wrangler dev on 8788)'); shutil.rmtree(base, ignore_errors=True)
    print('FAILED %s' % fails if fails else 'ALL PASS (unit part)'); sys.exit(1 if fails else 0)
import net
net.SERVER = B
net._SESSION = None          # plain urllib path
relay.DEFAULT_RELAY_KEY = 'test-relay-key-456'
relay.POLL_SEC = 0.5

class Brain:
    running = True; battle_count = 7; _stop_reason = ''
    def _grab_main(self):
        try:
            import numpy as np
            return np.zeros((768, 1024, 3), 'uint8')
        except Exception:
            return None
class Vision:
    def snapshot(self): return {'scene': 'main'}
class Auth:
    ok = False; token = ''; auth_id = ''
    def label(self): return '미인증'
stops = []
class Api:
    brain, vision, auth = Brain(), Vision(), Auth()
    def _run_remote(self, c, a): stops.append(c)
r = relay.Relay(Api())
def admin(path, body=None):
    req = urllib.request.Request(B + path, data=json.dumps(body).encode() if body is not None else None, headers={'Authorization': 'Bearer test-admin-key-123', 'Content-Type': 'application/json'})
    return urllib.request.urlopen(req, timeout=30).read()
st = r.status()
chk('status has battles/tail/auth', st['battles'] == 7 and 'line 399' in st['tail'] and st['auth'] == '미인증', st)
relay._machine = lambda: 'RELAY-TEST-PC'; relay._pc = lambda: 'RELAY-TEST'
# one poll registers the PC
body = {'machine': 'RELAY-TEST-PC', 'pc': 'RELAY-TEST', 'ver': '1.0.16', 'status': st, **r._auth_fields()}
r._post_json('/agent/poll', body)
agents = json.loads(admin('/admin/agents'))['rows']
chk('PC visible to owner with its log tail', any(a['pc'] == 'RELAY-TEST' and 'line 399' in a['status'].get('tail', '') for a in agents))
def job(cmd, arg=''):
    j = json.loads(admin('/admin/job', {'pc': 'RELAY-TEST', 'cmd': cmd, 'arg': arg}))['job']
    resp = r._post_json('/agent/poll', body)
    for x in resp['jobs']: r.run_job(x)
    return json.loads(admin('/admin/job?id=' + j))['job'], j
jb, jid = job('pull', 'debug/jochul_rounds/round_1|every=5')
data = urllib.request.urlopen(urllib.request.Request(B + '/admin/blob?job=' + jid, headers={'Authorization': 'Bearer test-admin-key-123'})).read()
chk('pull -> zip with 2 frames arrives intact', jb['state'] == 'done' and len([n for n in zipfile.ZipFile(io.BytesIO(data)).namelist() if n.startswith('frame_')]) == 2, jb)
jb, jid = job('log', '2000')
data = urllib.request.urlopen(urllib.request.Request(B + '/admin/blob?job=' + jid, headers={'Authorization': 'Bearer test-admin-key-123'})).read()
chk('log tail arrives', jb['state'] == 'done' and len(data) == 2000 and data.endswith(b'line 399'), len(data))
jb, jid = job('ls', 'debug')
chk('ls result', jb['state'] == 'done' and 'jochul_rounds' in jb['result'], jb['result'])
jb, jid = job('pull', 'prism_settings.json')
chk('pull of settings refused on the PC', jb['state'] == 'error', jb['result'])
jb, jid = job('pull', 'debug/../prism_settings.json')
chk('traversal refused on the PC', jb['state'] == 'error', jb['result'])
jb, jid = job('stop')
chk('stop works', jb['state'] == 'done' and stops == ['stop'])
shutil.rmtree(base, ignore_errors=True)
print('FAILED %s' % fails if fails else 'ALL PASS')
sys.exit(1 if fails else 0)
