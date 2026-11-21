import json, urllib.request, urllib.error

B = 'http://127.0.0.1:8787'
AK = 'test-admin-key-123'

def call(path, body=None, admin=False, token=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(B + path, data=data, method='POST' if data else 'GET')
    req.add_header('Content-Type', 'application/json')
    if admin:
        req.add_header('Authorization', 'Bearer ' + AK)
    if token:
        req.add_header('Authorization', 'Bearer ' + token)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.loads(r.read().decode() or '{}')
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or '{}')

fails = []
def chk(name, cond, extra=''):
    print(('PASS ' if cond else 'FAIL ') + name + (' ' + extra if extra else ''))
    if not cond:
        fails.append(name)

# 1 admin auth required
st, r = call('/admin/list')
chk('admin/list needs key', st == 403, f'got {st}')

# 2 issue 2pc license
st, r = call('/admin/issue', {'pcs': 2, 'days': 0, 'note': 'test'}, admin=True)
chk('issue ok', st == 200 and r.get('ok') and r.get('id'), json.dumps(r)[:160])
lic = r.get('id', '')

# 3 auth with wrong hwid set -> first bind ok
st, r = call('/auth', {'id': lic, 'hwid': 'HW-A', 'ver': '1.0.13'})
chk('auth binds pc1', st == 200 and r.get('ok') and r.get('token'), json.dumps(r)[:160])
tok = r.get('token', '')
chk('auth returns min_ver field', 'min_ver' in r)

# 4 second pc
st, r = call('/auth', {'id': lic, 'hwid': 'HW-B', 'ver': '1.0.13'})
chk('auth binds pc2', st == 200 and r.get('ok'), json.dumps(r)[:120])

# 5 third pc exceeds
st, r = call('/auth', {'id': lic, 'hwid': 'HW-C', 'ver': '1.0.13'})
chk('auth 3rd pc -> limit', st == 200 and r.get('ok') is False and r.get('reason') == 'limit', json.dumps(r)[:120])

# 6 heartbeat with valid token
st, r = call('/heartbeat', {'id': lic, 'token': tok, 'hwid': 'HW-A', 'ver': '1.0.13'})
chk('heartbeat ok', st == 200 and r.get('ok'), json.dumps(r)[:120])

# 7 heartbeat bad token
st, r = call('/heartbeat', {'id': lic, 'token': 'garbage', 'hwid': 'HW-A', 'ver': '1.0.13'})
chk('heartbeat bad token -> denied', r.get('ok') is False, json.dumps(r)[:120])

# 8 minver above build -> outdated
call('/admin/minver', {'ver': '9.9.9'}, admin=True)
st, r = call('/heartbeat', {'id': lic, 'token': tok, 'hwid': 'HW-A', 'ver': '1.0.13'})
chk('minver forces outdated', r.get('reason') == 'outdated', json.dumps(r)[:160])
st, r = call('/auth', {'id': lic, 'hwid': 'HW-A', 'ver': '1.0.13'})
chk('auth reports outdated too', r.get('reason') == 'outdated', json.dumps(r)[:160])
call('/admin/minver', {'ver': '0.0.0'}, admin=True)
st, r = call('/auth', {'id': lic, 'hwid': 'HW-A', 'ver': '1.0.13'})
chk('auth ok after minver lowered', r.get('ok'), json.dumps(r)[:120])
tok = r.get('token', '')

# 9 notice broadcast
call('/admin/notice', {'text': '점검 안내'}, admin=True)
st, r = call('/heartbeat', {'id': lic, 'token': tok, 'hwid': 'HW-A', 'ver': '1.0.13'})
chk('notice delivered', r.get('notice') == '점검 안내', json.dumps(r)[:120])

# 10 kick invalidates old token
call('/admin/kick', {'id': lic}, admin=True)
st, r = call('/heartbeat', {'id': lic, 'token': tok, 'hwid': 'HW-A', 'ver': '1.0.13'})
chk('kick kills old token', r.get('ok') is False, json.dumps(r)[:120])

# 11 unbind frees a slot
call('/admin/unbind', {'id': lic, 'hwid': 'HW-B'}, admin=True)
st, r = call('/auth', {'id': lic, 'hwid': 'HW-C', 'ver': '1.0.13'})
chk('after unbind HW-C can bind', r.get('ok'), json.dumps(r)[:120])
tok = r.get('token', '')

# 12 revoke
call('/admin/revoke', {'id': lic}, admin=True)
st, r = call('/auth', {'id': lic, 'hwid': 'HW-A', 'ver': '1.0.13'})
chk('revoked denies', r.get('ok') is False and r.get('reason') == 'revoked', json.dumps(r)[:120])

# 13 unknown license
st, r = call('/auth', {'id': 'NOPE-XXXX', 'hwid': 'HW-Z', 'ver': '1.0.13'})
chk('unknown id denied', r.get('ok') is False and r.get('reason') == 'unknown', json.dumps(r)[:120])

# 14 expiry in the past -> expired
st, r = call('/admin/issue', {'pcs': 1, 'days': -1, 'note': 'expired'}, admin=True)
exp = r.get('id', '')
st, r = call('/auth', {'id': exp, 'hwid': 'HW-E', 'ver': '1.0.13'})
chk('expired license denies', r.get('ok') is False and r.get('reason') == 'expired', json.dumps(r)[:120])

# 15 list shows both
st, r = call('/admin/list', None, admin=True)
chk('list returns rows', st == 200 and len(r.get('rows') or []) >= 2)

print()
print('FAILS:', fails if fails else 'none')
