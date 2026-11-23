"""Relay end-to-end against `wrangler dev --local` (port 8788):  python3 relay_devtest.py"""
import hashlib, json, os, sys, urllib.request, urllib.error

B = os.environ.get('RELAY_TEST_BASE', 'http://127.0.0.1:8788')
AK, RK = 'test-admin-key-123', 'test-relay-key-456'
fails = []

def call(path, body=None, raw=None, admin=False, method=None):
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    req = urllib.request.Request(B + path, data=data, method=method or ('POST' if data is not None else 'GET'))
    req.add_header('Content-Type', 'application/octet-stream' if raw is not None else 'application/json')
    if admin:
        req.add_header('Authorization', 'Bearer ' + AK)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            b = r.read()
            return r.status, b
    except urllib.error.HTTPError as e:
        return e.code, e.read()

def jcall(*a, **k):
    st, b = call(*a, **k)
    try:
        return st, json.loads(b.decode() or '{}')
    except Exception:
        return st, {'_raw': b[:80]}

def chk(name, cond, extra=''):
    print(('PASS ' if cond else 'FAIL ') + name + (' ' + str(extra)[:140] if extra else ''))
    if not cond:
        fails.append(name)

M = 'TEST-MACHINE-1'
st, r = jcall('/agent/poll', {'machine': M, 'pc': 'T-PC', 'ver': '1.0.16', 'status': {'running': True}})
chk('poll without key -> 403', st == 403, st)
st, r = jcall('/agent/poll', {'machine': M, 'pc': 'T-PC', 'ver': '1.0.16', 'k': RK, 'status': {'running': True, 'battles': 5}})
chk('poll with relay key ok, no jobs', st == 200 and r.get('ok') and r['jobs'] == [], r)
st, r = jcall('/admin/agents')
chk('admin/agents needs key', st == 403, st)
st, r = jcall('/admin/agents', admin=True)
a = [x for x in r.get('rows', []) if x['machine'] == M]
chk('agent listed with status', a and a[0]['status'].get('battles') == 5 and a[0]['age'] < 5, r)
st, r = jcall('/admin/job', {'pc': 'T-PC', 'cmd': 'rm -rf'}, admin=True)
chk('bad cmd refused', st == 400, r)
st, r = jcall('/admin/job', {'pc': 'NOPE', 'cmd': 'log'}, admin=True)
chk('unknown pc refused', st == 404, r)
st, r = jcall('/admin/job', {'pc': 'T-PC', 'cmd': 'pull', 'arg': 'debug/jochul_rounds/round_x'}, admin=True)
job = r.get('job', '')
chk('job queued', st == 200 and job, r)
st, r = jcall('/agent/up?job=%s&seq=0&total=1' % job, raw=b'x')
chk('upload before job handed out -> refused', st == 404, r)
st, r = jcall('/agent/poll', {'machine': M, 'k': RK, 'status': {}})
chk('job delivered once', r.get('jobs') and r['jobs'][0]['id'] == job and r['jobs'][0]['cmd'] == 'pull', r)
st, r = jcall('/agent/poll', {'machine': M, 'k': RK, 'status': {}})
chk('job not delivered twice', r.get('jobs') == [], r)

# chunked upload of 2.3 MB random, out of order
blob = os.urandom(2_300_000)
CH = 700 * 1024
parts = [blob[i:i + CH] for i in range(0, len(blob), CH)]
for seq in (2, 0, 3, 1)[:len(parts)]:
    st, r = jcall('/agent/up?job=%s&seq=%d&total=%d&name=round.zip' % (job, seq, len(parts)), raw=parts[seq])
    chk('chunk %d accepted' % seq, st == 200 and r.get('ok'), r)
st, r = jcall('/admin/job?id=' + job, admin=True)
chk('job done with right size', r['job']['state'] == 'done' and r['job']['bytes'] == len(blob) and r['job']['name'] == 'round.zip', r['job'])
st, b = call('/admin/blob?job=' + job, admin=True)
chk('download sha matches', st == 200 and hashlib.sha256(b).hexdigest() == hashlib.sha256(blob).hexdigest(), (st, len(b)))
st, r = jcall('/agent/up?job=%s&seq=0&total=%d' % (job, len(parts)), raw=b'late')
chk('upload to finished job refused', st == 404, r)
st, r = jcall('/agent/up?job=%s&seq=0&total=1' % ('f' * 16), raw=b'x')
chk('upload to unknown job refused', st == 404, r)
big = os.urandom(900 * 1024 + 1)
st, r = jcall('/admin/job', {'pc': 'T-PC', 'cmd': 'log', 'arg': '1000'}, admin=True)
j2 = r['job']; jcall('/agent/poll', {'machine': M, 'k': RK, 'status': {}})
st, r = jcall('/agent/up?job=%s&seq=0&total=1' % j2, raw=big)
chk('oversize chunk refused', st == 413, r)
st, r = jcall('/agent/done', {'job': j2, 'ok': True, 'result': 'hello'})
st, r = jcall('/admin/job?id=' + j2, admin=True)
chk('done/result stored', r['job']['state'] == 'done' and r['job']['result'] == 'hello', r['job'])

# existing client auto-upload path, with a real licence bind token
st, r = jcall('/admin/issue', {'pcs': 1, 'days': 0, 'note': 'relay test'}, admin=True)
lic = r['id']
st, r = jcall('/auth', {'id': lic, 'hwid': 'HW-R', 'ver': '1.0.16'})
tok = r['token']
z = os.urandom(1_700_000)
st, r = jcall('/debug/jochul?id=%s&token=%s&reason=%s' % (lic, 'bad', 'x'), raw=z)
chk('debug upload bad token -> 403', st == 403, r)
st, r = jcall('/debug/jochul?id=%s&token=%s&reason=%s' % (lic, tok, 'reader%2Ftracker%3D4'), raw=z)
chk('debug upload ok', st == 200 and r.get('job'), r)
st, b = call('/admin/blob?job=' + r['job'], admin=True)
chk('debug blob roundtrip', hashlib.sha256(b).hexdigest() == hashlib.sha256(z).hexdigest(), len(b))
st, r = jcall('/admin/jobs', admin=True)
chk('jobs list shows autodebug', any(x['cmd'] == 'autodebug' for x in r.get('rows', [])), '')
# relay also works with a licence token (no shared key)
st, r = jcall('/agent/poll', {'machine': 'M2', 'id': lic, 'token': tok, 'status': {}})
chk('poll with licence token ok', st == 200 and r.get('ok'), r)
print('\nFAILED: %s' % fails if fails else '\nALL PASS')
sys.exit(1 if fails else 0)
