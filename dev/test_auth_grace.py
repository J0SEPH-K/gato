"""AuthClient.login: retry on a flaky request, 12 h grace when the server is down, no grace for a wrong key."""
import os, sys, tempfile, json, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'mock')); import mac_stub  # noqa
except Exception:
    pass
import config, net
config.BASE_DIR = tempfile.mkdtemp(prefix='gato_auth_')
net.LOCAL = False
fails = []
def chk(n, c, e=''):
    print(('PASS ' if c else 'FAIL ') + n + (' ' + str(e)[:90] if e else ''))
    if not c: fails.append(n)
time.sleep = lambda s: None
calls = {'n': 0}
def flaky(path, body, timeout=20):
    calls['n'] += 1
    if calls['n'] < 3: raise OSError('boom')
    return {'ok': True, 'token': 'TOK', 'days_left': 5}
net._post = flaky
a = net.AuthClient()
chk('login survives 2 dropped requests', a.login('GATO-AAAA') and calls['n'] == 3 and not a.grace, calls)
net._post = lambda *x, **k: (_ for _ in ()).throw(OSError('down'))
b = net.AuthClient()
chk('server down + verified within 12 h -> grace', b.login('GATO-AAAA') and b.grace and b.token == 'TOK' and '임시' in b.label(), b.label())
c = net.AuthClient()
chk('different key gets no grace', not c.login('GATO-BBBB') and c.reason == 'network')
g = json.load(open(os.path.join(config.BASE_DIR, 'auth_grace.json'))); g['ts'] = time.time() - 13 * 3600
json.dump(g, open(os.path.join(config.BASE_DIR, 'auth_grace.json'), 'w'))
d = net.AuthClient()
chk('grace expires after 12 h', not d.login('GATO-AAAA'))
net._post = lambda *x, **k: {'ok': False, 'reason': 'revoked'}
e = net.AuthClient()
chk('revoked key never graced', not e.login('GATO-AAAA') and e.reason == 'revoked')
print('FAILED %s' % fails if fails else 'ALL PASS'); sys.exit(1 if fails else 0)
