#!/usr/bin/env python3
"""Gato remote link (M1): hub relay client + pairing CLI + selftest.

Nothing here imports prism. The Api instance is passed in by install().
websockets is imported lazily so the CLI still runs without it.

M1 scope: link/sender/exec/state threads, challenge-response auth, cmd/ack,
state relay, read-only rpc whitelist. No FrameStreamer, no remote_input.

=====================================================================
prism.py — apply these 3 lines verbatim, nothing else changes.

1) At the end of Api.__init__, after `self.start_cmd_poller()` (prism.py:78):

        import remote_link
        self.remote = remote_link.install(self)   # None when remote.json is absent or invalid

2) In main()._on_closed (prism.py:986):

        if getattr(api, 'remote', None): api.remote.close()

=====================================================================
"""

import argparse
import base64
import hashlib
import hmac
import json
import os
import queue
import random
import re
import secrets
import socket
import sys
import threading
import time
import urllib.error
import urllib.request

REMOTE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'remote.json')

INPUT_CMDS = {'click_l', 'click_r', 'key_f', 'key_m', 'key_i', 'key_b', 'key_enter'}
PRIORITY = {'stop', 'sched_stop', 'live_stop'}
LEASED = INPUT_CMDS | {'start', 'sched_start', 'chat_normal', 'chat_sangdan', 'whisper',
                       'gato_login', 'gato_launch', 'game_close', 'key'}

SECRET_KEYS = {'discord_token', 'discord_webhook', 'ntfy_url', 'auth_id'}
SECRET_RE = re.compile(r'(token|secret|webhook|pass)', re.I)


class RemoteCfgError(Exception):
    pass


def _b32(n=10):
    return base64.b32encode(secrets.token_bytes(8)).decode().lower().rstrip('=')[:n]


def _b64u(b):
    return base64.urlsafe_b64encode(b).decode().rstrip('=')


def _machine():
    """MachineGuid on Windows; a stable per-host string elsewhere (selftest only)."""
    if sys.platform == 'win32':
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\Microsoft\Cryptography') as k:
                return str(winreg.QueryValueEx(k, 'MachineGuid')[0])
        except Exception:
            return 'win-unknown'
    return 'mac-' + socket.gethostname()


def _atomic_write(path, obj):
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def load_remote_cfg():
    if not os.path.exists(REMOTE_PATH):
        return None
    try:
        with open(REMOTE_PATH, encoding='utf-8') as f:
            cfg = json.load(f)
        if cfg.get('v') != 1 or not cfg.get('hub') or not cfg.get('pc') or not cfg.get('secret'):
            raise RemoteCfgError('remote.json 형식 오류 — 다시 페어링하세요')
    except RemoteCfgError:
        raise
    except Exception as e:
        raise RemoteCfgError(f'remote.json 읽기 실패 — {e}')
    if cfg.get('machine') != _machine():
        try:
            os.replace(REMOTE_PATH, REMOTE_PATH + '.copied')
        except OSError:
            pass
        raise RemoteCfgError('다른 PC에서 복사된 remote.json — 이 PC에서 다시 페어링하세요')
    return cfg


def redact(obj):
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k in SECRET_KEYS or (isinstance(k, str) and SECRET_RE.search(k)):
                out[k] = {'set': bool(v)}
            else:
                out[k] = redact(v)
        return out
    if isinstance(obj, list):
        return [redact(v) for v in obj]
    return obj


def strip_secret_keys(d):
    return {k: v for k, v in d.items() if not (k in SECRET_KEYS or (isinstance(k, str) and SECRET_RE.search(k)))}


class RemoteLink:
    PING_S = 20
    STATE_FAST_S = 2.0
    STATE_SLOW_S = 30.0
    CMD_TIMEOUT_S = 15.0
    BACKOFF = (1, 2, 4, 8, 16, 32, 60)

    def __init__(self, api, cfg, run_remote_orig, lock):
        self.api = api
        self.cfg = cfg
        self._orig = run_remote_orig
        self._lock = lock
        self._stop = threading.Event()
        self._ws = None
        self._ws_lock = threading.Lock()
        self._q = queue.Queue(maxsize=1000)
        self._exec_q = queue.Queue()
        self._seen = []
        self._seen_set = set()
        self._offset = 0
        self._authed = False
        self._dead_code = None
        self._threads = []
        self._ev_seq = 0
        self._chat_seq = 0
        self._last_hash = None
        self._last_sent = 0.0

    # ---------- lifecycle ----------
    def start(self):
        for fn in (self._link_loop, self._sender_loop, self._exec_loop, self._state_loop):
            t = threading.Thread(target=fn, daemon=True, name='remote-' + fn.__name__)
            t.start()
            self._threads.append(t)

    def close(self):
        self._stop.set()
        with self._ws_lock:
            ws = self._ws
        if ws is not None:
            try:
                ws.close()
            except Exception:
                pass

    def _hub_now(self):
        return int(time.time() * 1000) + self._offset

    # ---------- link ----------
    def _link_loop(self):
        import websockets.sync.client as wsc
        hub = self.cfg['hub'].rstrip('/')
        ws_url = hub.replace('https://', 'wss://').replace('http://', 'ws://') + '/ws/agent?pc=' + self.cfg['pc']
        attempt = 0
        while not self._stop.is_set():
            if self._dead_code == 4003:
                # Hub no longer knows this pc (forgotten, or paired before a schema change).
                # Do not die: a re-pair from the phone makes the same pc id work again.
                self._note('이 PC는 허브에 없음 — 휴대폰에서 다시 페어링하세요 (60초마다 재시도)')
                self._stop.wait(60.0)
                continue
            self._authed = False
            try:
                with wsc.connect(ws_url, open_timeout=10, ping_interval=20, ping_timeout=20,
                                 max_size=2 ** 20, user_agent_header='gato-remote/1') as ws:
                    with self._ws_lock:
                        self._ws = ws
                    self._recv(ws)
            except Exception as e:
                if self._stop.is_set():
                    return
                self._note(f'[원격링크] 연결 끊김 — {type(e).__name__}')
            finally:
                with self._ws_lock:
                    self._ws = None
            if self._dead_code == 4003:
                continue
            base = self.BACKOFF[min(attempt, len(self.BACKOFF) - 1)]
            attempt = attempt + 1 if not self._authed else 0
            if self._authed:
                base = self.BACKOFF[0]
            self._stop.wait(base * random.uniform(0.7, 1.3))

    def _recv(self, ws):
        ping_at = 0.0
        for raw in ws:
            if self._stop.is_set():
                return
            now = time.monotonic()
            if now - ping_at >= self.PING_S:
                ping_at = now
                self._send({'t': 'ping'})
            if isinstance(raw, (bytes, bytearray)):
                continue  # M1: no frames
            try:
                m = json.loads(raw)
            except Exception:
                continue
            self._on_msg(m)

    def _on_msg(self, m):
        t = m.get('t')
        if t == 'challenge':
            self._offset = int(m.get('now', 0)) - int(time.time() * 1000)
            n = m.get('n', '')
            sig = hmac.new(self.cfg['secret'].encode(), f"agent|{self.cfg['pc']}|{n}".encode(), hashlib.sha256).hexdigest()
            self._send({'t': 'auth', 'pc': self.cfg['pc'], 'sig': sig})
        elif t == 'welcome':
            self._offset = int(m.get('now', 0)) - int(time.time() * 1000)
            self._authed = True
            self._note(f"[원격링크] 연결됨 — {m.get('name', '')}")
            self._state_once()
        elif t == 'cmd':
            self._enqueue_exec(m)
        elif t == 'rpc':
            self._exec_q.put(('rpc', m))
        elif t in ('view', 'credit', 'still'):
            pass  # M2

    def _enqueue_exec(self, m):
        if m.get('cmd') in PRIORITY:
            threading.Thread(target=self._run_one, args=('cmd', m), daemon=True).start()
        else:
            self._exec_q.put(('cmd', m))

    # ---------- sender ----------
    def _send(self, obj):
        try:
            self._q.put_nowait(obj)
        except queue.Full:
            pass

    def _sender_loop(self):
        while not self._stop.is_set():
            try:
                obj = self._q.get(timeout=1.0)
            except queue.Empty:
                continue
            with self._ws_lock:
                ws = self._ws
            if ws is None:
                continue
            try:
                ws.send(json.dumps(obj, ensure_ascii=False))
            except Exception:
                pass

    # ---------- exec ----------
    def _exec_loop(self):
        while not self._stop.is_set():
            try:
                kind, m = self._exec_q.get(timeout=1.0)
            except queue.Empty:
                continue
            box = {}
            th = threading.Thread(target=self._run_one, args=(kind, m, box), daemon=True)
            th.start()
            th.join(self.CMD_TIMEOUT_S)
            if th.is_alive():
                self._send({'t': 'ack', 'id': m.get('id'), 'ok': False, 'res': 'timeout', 'note': 'timeout'})
                self._note('[원격] 명령 시간 초과')

    def _run_one(self, kind, m, box=None):
        mid = m.get('id')
        exp = int(m.get('exp') or 0)
        if exp and exp < self._hub_now():
            self._send({'t': 'ack', 'id': mid, 'ok': False, 'res': 'expired', 'note': 'expired'})
            return
        if mid:
            if mid in self._seen_set:
                return
            self._seen.append(mid)
            self._seen_set.add(mid)
            if len(self._seen) > 512:
                old = self._seen.pop(0)
                self._seen_set.discard(old)
        try:
            if kind == 'rpc':
                self._on_rpc(m)
            else:
                self._on_cmd(m)
        except Exception as e:
            self._send({'t': 'ack', 'id': mid, 'ok': False, 'res': 'error', 'note': f'{type(e).__name__}: {e}'})

    def _on_cmd(self, m):
        cmd = str(m.get('cmd') or '')
        arg = m.get('arg') or ''
        before = getattr(self.api, '_last_note', None)
        with self._lock:
            self._orig(cmd, arg)
        note = getattr(self.api, '_last_note', '')
        note = note if note != before else ''
        self._send({'t': 'ack', 'id': m.get('id'), 'ok': True, 'res': 'ok', 'note': note})
        self._state_once()

    def _on_rpc(self, m):
        name = str(m.get('m') or '')
        a = m.get('a') or []
        api = self.api
        fns = {
            'tick': lambda: api.tick(int(a[0]), int(a[1])),
            'status': lambda: api.status(),
            'get_config': lambda: redact(api.get_config()),
            'set_monster': lambda: redact(api.set_monster(str(a[0]))),
            'save_monster_cfg': lambda: redact(api.save_monster_cfg(str(a[0]), dict(a[1]), a[2] if len(a) > 2 else None)),
            'save_common': lambda: redact(api.save_common(strip_secret_keys(dict(a[0])), a[1] if len(a) > 1 else None)),
            'kill_rank': lambda: api.kill_rank(),
            'appear_records': lambda: api.appear_records(),
            'reset_count': lambda: api.reset_count(),
            'portrait': lambda: api.portrait(str(a[0])),
        }
        fn = fns.get(name)
        if fn is None:
            self._send({'t': 'rpc_res', 'id': m.get('id'), 'ok': False, 'result': {'err': 'denied'}})
            return
        try:
            res = fn()
            self._send({'t': 'rpc_res', 'id': m.get('id'), 'ok': True, 'result': res})
        except Exception as e:
            self._send({'t': 'rpc_res', 'id': m.get('id'), 'ok': False, 'result': {'err': f'{type(e).__name__}: {e}'}})

    # ---------- state ----------
    def _state_loop(self):
        while not self._stop.wait(self.STATE_FAST_S if self._authed else self.STATE_SLOW_S):
            if not self._authed:
                continue
            try:
                s = self.api.tick(self._ev_seq, self._chat_seq)
            except Exception:
                continue
            ev = s.pop('ev', [])
            chat = s.pop('chat', [])
            h = hashlib.sha256(json.dumps(s, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()
            if h == self._last_hash and time.monotonic() - self._last_sent < self.STATE_SLOW_S:
                continue
            self._last_hash = h
            self._last_sent = time.monotonic()
            self._send({'t': 'state', 'seq': s.get('seq', 0), 'ts': self._hub_now(), 's': s, 'ev': ev[-50:], 'chat': chat[-50:]})

    def _state_once(self):
        """Send a state immediately (after welcome, after every ack) so the phone never waits 2 s."""
        try:
            s = self.api.tick(self._ev_seq, self._chat_seq)
        except Exception:
            return
        ev = s.pop('ev', [])
        chat = s.pop('chat', [])
        self._last_hash = hashlib.sha256(json.dumps(s, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()
        self._last_sent = time.monotonic()
        self._send({'t': 'state', 'seq': s.get('seq', 0), 'ts': self._hub_now(), 's': s, 'ev': ev[-50:], 'chat': chat[-50:]})

    def _note(self, text):
        try:
            self.api.vision.note('input', text)
        except Exception:
            pass


def install(api):
    try:
        cfg = load_remote_cfg()
        if cfg is None:
            return None
        import websockets.sync.client  # noqa: F401
    except RemoteCfgError as e:
        try:
            api.vision.note('input', f'[원격링크] {e}')
        except Exception:
            pass
        return None
    except ImportError:
        try:
            api.vision.note('input', '[원격링크] websockets 미설치 — pip install websockets==15.0.1')
        except Exception:
            pass
        return None
    orig = api._run_remote
    lock = threading.RLock()

    def _locked(cmd, arg=''):
        with lock:
            return orig(cmd, arg)

    api._run_remote = _locked
    link = RemoteLink(api, cfg, orig, lock)
    link.start()
    return link


# ---------------- pairing CLI ----------------

def _post(hub, path, obj, timeout=10):
    data = json.dumps(obj).encode()
    req = urllib.request.Request(hub.rstrip('/') + path, data=data,
                                 headers={'content-type': 'application/json', 'user-agent': 'gato-remote/1'}, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode() or '{}')
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or '{}')
        except Exception:
            return e.code, {}


def cmd_pair(args):
    pc = 'pc_' + _b32()
    secret = _b64u(secrets.token_bytes(32))
    name = (args.name or 'PC')[:24]
    st, body = _post(args.hub, '/api/agent/pair/start', {'pc': pc, 'name': name, 'secret': secret})
    if st != 200 or not body.get('ok'):
        print(f'[페어링] 시작 실패: {st} {body}')
        return 1
    code = body['code']
    print('[페어링] 휴대폰에서 \'설정 → PC 추가\'를 누르고')
    print(f'         이 코드를 입력하세요:  {code[:3]} {code[3:]}')
    print(f'         (이름: {name}, 10분 유효)')
    deadline = time.time() + 600
    while time.time() < deadline:
        sig = hmac.new(secret.encode(), f'poll|{pc}|{code}'.encode(), hashlib.sha256).hexdigest()
        st, body = _post(args.hub, '/api/agent/pair/poll', {'pc': pc, 'sig': sig, 'code': code})
        state = body.get('state')
        if state == 'approved':
            cfg = {'v': 1, 'hub': args.hub.rstrip('/'), 'pc': pc, 'name': body.get('name', name),
                   'secret': secret, 'machine': _machine(),
                   'paired_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                   'input_mode': {'key': 'borrow', 'mouse': 'borrow'}}
            _atomic_write(REMOTE_PATH, cfg)
            print('[페어링] 승인됨 — 매크로를 다시 시작하면 연결됩니다')
            return 0
        if state == 'expired':
            print('코드 만료 — 다시 실행하세요')
            return 2
        if state == 'rejected':
            print('[페어링] 거부됨')
            return 1
        time.sleep(3)
    print('시간 초과')
    return 2


def cmd_set_hub(args):
    cfg = load_remote_cfg()
    if cfg is None:
        print('remote.json 없음 — 먼저 pair')
        return 1
    cfg['hub'] = args.url.rstrip('/')
    _atomic_write(REMOTE_PATH, cfg)
    print('허브 URL 변경됨:', cfg['hub'])
    return 0


def cmd_unpair(_args):
    if not os.path.exists(REMOTE_PATH):
        print('remote.json 없음')
        return 1
    if input('remote.json을 삭제할까요? [y/N] ').strip().lower() != 'y':
        print('취소')
        return 1
    os.remove(REMOTE_PATH)
    print('삭제됨')
    return 0


# ---------------- FakeApi + selftest ----------------

class FakeVision:
    def __init__(self):
        self.notes = []

    def note(self, kind, text):
        self.notes.append(text)
        print('[note]', text, flush=True)


class FakeApi:
    def __init__(self, name='PC'):
        self.vision = FakeVision()
        self.running = False
        self.battles = 143
        self.name = name
        self._last_note = ''

    def _run_remote(self, cmd, arg=''):
        if cmd == 'start':
            self.running = True
            self._last_note = '▶ 패널 시작'
        elif cmd == 'stop':
            self.running = False
            self._last_note = '■ 정지'
        elif cmd == 'sched_start':
            self._last_note = f'스케쥴 {arg}'
        else:
            self._last_note = f'{cmd} {arg}'.strip()
        print(f'[exec] {cmd} {arg}', flush=True)

    def tick(self, ev_seq, chat_seq):
        return {
            'seq': 1, 'running': self.running, 'battle_count': self.battles,
            'monster': '주작', 'schedule': {'active': False, 'cycle': 0, 'cycles': 0, 'battles': 0, 'target': 10, 'resting': False, 'rest_left': 0},
            'auth': {'ok': True, 'label': '인증 · D-12'}, 'window_count': 0, 'clients': [],
            'last_note': self._last_note, 'gato': False, 'admin': True, 'locked': False,
            'busy': None, 'ver': 'selftest', 'input_mode': {'key': 'borrow', 'mouse': 'borrow'},
            'ev': [], 'chat': [],
        }

    def status(self):
        return {'ok': True, 'running': self.running, 'battles': self.battles}

    def get_config(self):
        return {'common': {'discord_token': 'abc', 'nick': 'x'}, 'monsters': []}

    def set_monster(self, name):
        return {'ok': True, 'monster': name}

    def save_monster_cfg(self, name, cfg, stamp=None):
        return {'ok': True}

    def save_common(self, cfg, stamp=None):
        return {'ok': True, 'got': sorted(cfg.keys())}

    def kill_rank(self):
        return {'ok': True}

    def appear_records(self):
        return []

    def reset_count(self):
        self.battles = 0
        return {'ok': True}

    def portrait(self, name):
        return {'ok': True, 'name': name}


def cmd_selftest(args):
    import tempfile
    global REMOTE_PATH
    hub = args.hub.rstrip('/')
    name = args.name or 'selftest'
    print(f'[selftest] hub={hub} name={name}', flush=True)
    if args.fake_pair:
        old = REMOTE_PATH
        REMOTE_PATH = os.path.join(tempfile.mkdtemp(prefix='gato-remote-'), 'remote.json')
        pc = 'pc_' + _b32()
        secret = _b64u(secrets.token_bytes(32))
        st, body = _post(hub, '/api/agent/pair/start', {'pc': pc, 'name': name, 'secret': secret})
        if st != 200 or not body.get('ok'):
            print(f'[selftest] pair/start 실패: {st} {body}', flush=True)
            return 1
        code = body['code']
        print(f'CODE {code}', flush=True)
        # approve with OWNER_PASS over HTTP
        st2, dev = _post(hub, '/api/login', {'pass': os.environ.get('OWNER_PASS', 'test-pass-1234'), 'device_name': 'selftest'})
        if st2 != 200:
            print(f'[selftest] login 실패: {st2} {dev}', flush=True)
            return 1
        # cookie login via urllib cookie header
        req = urllib.request.Request(hub + '/api/login', data=json.dumps({'pass': os.environ.get('OWNER_PASS', 'test-pass-1234'), 'device_name': 'selftest'}).encode(), headers={'content-type': 'application/json', 'user-agent': 'gato-remote/1'}, method='POST')
        with urllib.request.urlopen(req, timeout=10) as r:
            ck = r.headers.get('set-cookie', '').split(';')[0]
        req = urllib.request.Request(hub + '/api/pair/approve', data=json.dumps({'code': code, 'name': name}).encode(), headers={'content-type': 'application/json', 'cookie': ck, 'user-agent': 'gato-remote/1'}, method='POST')
        with urllib.request.urlopen(req, timeout=10) as r:
            appr = json.loads(r.read().decode())
        if not appr.get('ok'):
            print('[selftest] approve 실패', appr, flush=True)
            return 1
        cfg = {'v': 1, 'hub': hub, 'pc': pc, 'name': name, 'secret': secret,
               'machine': _machine(), 'paired_at': 'now', 'input_mode': {'key': 'borrow', 'mouse': 'borrow'}}
        _atomic_write(REMOTE_PATH, cfg)
        print(f'PAIRED {pc}', flush=True)
        REMOTE_PATH = old
    else:
        cfg = load_remote_cfg()
        if cfg is None:
            print('[selftest] remote.json 없음 — --fake-pair 또는 pair 를 쓰세요')
            return 1
    api = FakeApi(name)
    link = RemoteLink(api, cfg, api._run_remote, threading.RLock())
    link.start()
    print('[selftest] 링크 시작 — Ctrl-C 종료', flush=True)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        link.close()
        return 0


def main():
    ap = argparse.ArgumentParser(prog='remote_link.py')
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('pair')
    p.add_argument('--hub', required=True)
    p.add_argument('--name')
    p.set_defaults(fn=cmd_pair)
    p = sub.add_parser('set-hub')
    p.add_argument('url')
    p.set_defaults(fn=cmd_set_hub)
    p = sub.add_parser('unpair')
    p.set_defaults(fn=cmd_unpair)
    p = sub.add_parser('selftest')
    p.add_argument('--hub', required=True)
    p.add_argument('--fake-pair', action='store_true')
    p.add_argument('--fake-agent', action='store_true')
    p.add_argument('--name')
    p.set_defaults(fn=cmd_selftest)
    args = ap.parse_args()
    sys.exit(args.fn(args))


if __name__ == '__main__':
    main()
