"""End-to-end check of net.AuthClient against the real deployed Worker.

Needs GATO_TEST_KEY / GATO_TEST_ADMIN in the environment.
"""
import json
import os
import sys
import urllib.request
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import net  # noqa: E402

KEY = os.environ.get('GATO_TEST_KEY', '')
ADMIN = os.environ.get('GATO_TEST_ADMIN', '')
# a key that has never been issued; KEY itself stays in the DB between runs
UNKNOWN = 'GATO-ZZZZ-' + uuid.uuid4().hex[:4].upper()
BASE = net.SERVER

fails = []


def chk(name, cond, extra=''):
    print(('PASS ' if cond else 'FAIL ') + name + ((' ' + str(extra)) if extra else ''))
    if not cond:
        fails.append(name)


def admin(path, body=None):
    data = json.dumps(body or {}).encode()
    req = urllib.request.Request(BASE + path, data=data, method='POST')
    req.add_header('Content-Type', 'application/json')
    req.add_header('User-Agent', 'GATO/test')
    req.add_header('Authorization', 'Bearer ' + ADMIN)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode() or '{}')


chk('server reachable', bool(BASE) and 'REPLACE' not in BASE, BASE)
chk('APP_VER reads VERSION', bool(net.APP_VER) and net.APP_VER[0].isdigit(), net.APP_VER)
chk('hwid is 32 chars', len(net.hwid()) == 32, net.hwid())
chk('hwid is stable', net.hwid() == net.hwid())

a = net.AuthClient('테스트몹')
chk('empty key fails clean', a.login('') is False and a.reason == '')

a.login(UNKNOWN)
chk('unknown key -> unknown', a.ok is False and a.reason == 'unknown', a.reason)

admin('/admin/issue', {'id': KEY, 'pcs': 1, 'days': 0, 'note': 'client test'})
chk('login after issue', a.login(KEY) is True and a.ok, a.label())
chk('token present', len(a.token) > 20, a.token[:12])
chk('days_left None for permanent', a.days_left is None)
chk('label says authed', '인증' in a.label(), a.label())
chk('no forced update at min_ver 0.0.0', a.must_update() is False and a.update_available() is False)

chk('heartbeat ok', a.heartbeat() is True)

admin('/admin/minver', {'ver': '99.0.0'})
chk('heartbeat reports outdated', a.heartbeat() is False and a.reason == 'outdated', a.reason)
chk('must_update true', a.must_update() is True)
chk('label shows update needed', a.label() == '업데이트 필요', a.label())
chk('login also blocked by floor', a.login(KEY) is False and a.reason == 'outdated', a.reason)

admin('/admin/minver', {'ver': '0.0.0'})
chk('recovers after floor lowered', a.login(KEY) is True, a.reason)

admin('/admin/notice', {'text': '테스트 공지'})
chk('heartbeat delivers notice', a.heartbeat() is True and a.notice == '테스트 공지', a.notice)

admin('/admin/kick', {'id': KEY})
chk('kick -> kicked', a.heartbeat() is False and a.reason == 'kicked', a.reason)
chk('relogin after kick works', a.login(KEY) is True, a.reason)

admin('/admin/revoke', {'id': KEY})
chk('revoke -> revoked', a.login(KEY) is False and a.reason == 'revoked', a.reason)

admin('/admin/notice', {'text': ''})
admin('/admin/issue', {'id': KEY, 'pcs': 1, 'days': 0, 'note': 'client test'})
chk('reissue un-revokes', a.login(KEY) is True, a.reason)

print()
print('FAILS:', fails if fails else 'none')
sys.exit(1 if fails else 0)
