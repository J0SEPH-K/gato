"""Server relay: lets the owner see this PC and pull its debug files with NO tunnel.

Every ~30 s the app POSTs its status to the licence Worker (outbound https only) and receives any jobs the
owner queued. A job asks for a log tail, a screenshot, a directory listing, or a zip of a debug folder; the
app uploads the result back to the Worker in <=700 KB chunks. Nothing listens on the PC, so NAT, a home IP
shared by several PCs, Cloudflare quick-tunnel 429s and the ngrok agent cap cannot cut it off.

Safety: only paths under BASE_DIR/debug and the three log files can be read; settings/keys are never
readable; there is no command that starts the bot or runs code. Everything here is best effort - any failure
is swallowed and the bot keeps hunting.
"""
from __future__ import annotations

import io
import json
import os
import threading
import time
import zipfile

import config

POLL_SEC = 30.0          # idle cadence
FAST_SEC = 3.0           # while a job was just handed out
FAST_FOR_SEC = 120.0
CHUNK = 700 * 1024
MAX_PULL_BYTES = 150 * 1024 * 1024
DEFAULT_RELAY_KEY = 'gato-relay-3f9c1d7a52e84b06a8d1c4f7'   # replaced by the server secret at deploy; see server/README.md
ALLOWED_TOP = ('debug', 'gato_debug.log', 'gato_traceback.log', 'prism_crash.log')
DENY_PARTS = ('settings', 'token', 'secret', 'license', 'password', '.key')


def _cfg(key, default):
    try:
        return config.load().get(key, default)
    except Exception:
        return default


def resolve(rel: str) -> str:
    """Absolute path for a read request, or raise ValueError. Pure function (unit tested)."""
    rel = (rel or '').replace('\\', '/').strip().lstrip('/')
    if not rel or '..' in rel.split('/'):
        raise ValueError('bad path')
    base = os.path.realpath(config.BASE_DIR)
    full = os.path.realpath(os.path.join(base, rel))
    if full != base and not full.startswith(base + os.sep):
        raise ValueError('outside')
    top = os.path.relpath(full, base).replace('\\', '/').split('/')[0]
    if top not in ALLOWED_TOP:
        raise ValueError('not allowed')
    low = full.lower()
    if any(p in os.path.basename(low) for p in DENY_PARTS):
        raise ValueError('denied')
    return full


def tail_lines(path: str, n: int = 20, max_bytes: int = 6000) -> str:
    try:
        size = os.path.getsize(path)
        with open(path, 'rb') as f:
            f.seek(max(0, size - max_bytes))
            raw = f.read()
        lines = raw.decode('utf-8', 'replace').splitlines()
        lines = [x for x in lines if '[게이트]' not in x]
        return '\n'.join(lines[-n:])
    except Exception:
        return ''


def parse_pull_arg(arg: str):
    """'debug/jochul_rounds/round_x|every=5|mb=80' -> (path, every, max_bytes)."""
    parts = [p.strip() for p in (arg or '').split('|')]
    path, every, mb = parts[0], 1, MAX_PULL_BYTES // (1024 * 1024)
    for p in parts[1:]:
        if p.startswith('every='):
            every = max(1, int(p[6:] or 1))
        elif p.startswith('mb='):
            mb = max(1, min(MAX_PULL_BYTES // (1024 * 1024), int(p[3:] or 1)))
    return path, every, mb * 1024 * 1024


def build_zip(full: str, every: int = 1, max_bytes: int = MAX_PULL_BYTES) -> bytes:
    """Zip a file or a directory. `every`=N keeps every Nth frame_XXXX image (other files always kept)."""
    buf = io.BytesIO()
    base = os.path.dirname(full) if os.path.isfile(full) else full
    files = []
    if os.path.isfile(full):
        files = [full]
    else:
        for root, _d, names in os.walk(full):
            for nm in sorted(names):
                files.append(os.path.join(root, nm))
    files.sort()
    total = 0
    idx = 0
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        for p in files:
            nm = os.path.basename(p)
            low = nm.lower()
            if any(d in low for d in DENY_PARTS):
                continue
            if every > 1 and nm.startswith('frame_'):
                idx += 1
                if (idx - 1) % every:
                    continue
            try:
                sz = os.path.getsize(p)
            except OSError:
                continue
            if total + sz > max_bytes:
                # A single file bigger than the budget (a 550 MB pktmon .etl) must still
                # contribute its head, otherwise the pull returns an empty zip.
                room = max_bytes - total
                if room > 0:
                    try:
                        with open(p, 'rb') as fh:
                            head = fh.read(room)
                    except OSError:
                        head = b''
                    if head:
                        z.writestr(os.path.relpath(p, base).replace('\\', '/'), head, compress_type=zipfile.ZIP_STORED)
                        total += len(head)
                z.writestr('_TRUNCATED.txt', f'stopped at {total} bytes (limit {max_bytes}); head of {os.path.basename(p)} kept')
                break
            comp = zipfile.ZIP_STORED if low.endswith(('.png', '.jpg', '.jpeg', '.zip')) else zipfile.ZIP_DEFLATED
            z.write(p, os.path.relpath(p, base).replace('\\', '/'), compress_type=comp)
            total += sz
    return buf.getvalue()


class Relay:
    def __init__(self, api):
        self.api = api
        self._stop = threading.Event()
        self._thread = None
        self._fast_until = 0.0
        self._t0 = time.time()
        self._fails = 0
        self._busy = threading.Lock()

    # ---- plumbing ----
    def _key(self):
        return str(_cfg('relay_key', '') or DEFAULT_RELAY_KEY)

    def _auth_fields(self):
        o = {'k': self._key()}
        try:
            a = self.api.auth
            if a.ok and a.token and a.token != 'local':
                o.update({'id': a.auth_id, 'token': a.token})
        except Exception:
            pass
        return o

    def _post_json(self, path, obj, timeout=20):
        import net
        return net._post(path, obj, timeout=timeout)

    def _post_raw(self, path, data: bytes, timeout=120):
        import net
        if getattr(net, '_SESSION', None) is not None:
            r = net._SESSION.post(net.SERVER + path, data=data, headers={'Content-Type': 'application/octet-stream'}, timeout=timeout)
            r.raise_for_status()
            return r.json()
        import urllib.request
        req = urllib.request.Request(net.SERVER + path, data=data, method='POST',
                                     headers={'Content-Type': 'application/octet-stream', 'User-Agent': f'GATO/{net.CLIENT_VER}'})
        with urllib.request.urlopen(req, timeout=timeout, context=net._SSL_CTX) as r:
            return json.loads(r.read().decode('utf-8'))

    def status(self) -> dict:
        import net
        out = {'ver': net.APP_VER, 'uptime_s': int(time.time() - self._t0), 'running': False, 'battles': 0,
               'scene': '', 'monster': '', 'stop_reason': '', 'auth': '', 'jochul_mode': _cfg('jochul_mode', 'alert')}
        try:
            b = self.api.brain
            out['running'] = bool(getattr(b, 'running', False))
            out['battles'] = int(getattr(b, 'battle_count', 0) or 0)
            out['stop_reason'] = str(getattr(b, '_stop_reason', '') or '')[:80]
        except Exception as e:
            out['err'] = f'brain: {type(e).__name__}'
        try:
            out['scene'] = (self.api.vision.snapshot() or {}).get('scene', '') or ''
        except Exception:
            pass
        try:
            out['monster'] = str(_cfg('current_monster', '') or '')
            out['auth'] = self.api.auth.label()
        except Exception:
            pass
        try:
            out['tail'] = tail_lines(os.path.join(config.BASE_DIR, 'gato_debug.log'), 20)
        except Exception:
            pass
        return out

    # ---- jobs ----
    def _upload(self, job, data: bytes, name: str):
        n = max(1, (len(data) + CHUNK - 1) // CHUNK)
        for i in range(n):
            part = data[i * CHUNK:(i + 1) * CHUNK] or b'\0'
            q = f'/agent/up?job={job}&seq={i}&total={n}&name={name}'
            for attempt in range(4):
                try:
                    self._post_raw(q, part)
                    break
                except Exception:
                    if attempt == 3:
                        raise
                    time.sleep(2 + attempt * 3)
            time.sleep(0.05)   # keep the hunt responsive

    def _done(self, job, ok, result=''):
        try:
            self._post_json('/agent/done', {'job': job, 'ok': ok, 'result': str(result)[:3900]})
        except Exception:
            pass

    def run_job(self, job):
        jid, cmd, arg = job.get('id', ''), job.get('cmd', ''), job.get('arg', '')
        try:
            with self._busy:
                if cmd == 'log':
                    n = max(1000, min(3_000_000, int(arg or 300000)))
                    p = os.path.join(config.BASE_DIR, 'gato_debug.log')
                    with open(p, 'rb') as f:
                        size = os.path.getsize(p)
                        f.seek(max(0, size - n))
                        data = f.read()
                    self._upload(jid, data, 'gato_debug.tail.log')
                elif cmd == 'shot':
                    import cv2
                    img = self.api.brain._grab_main()
                    if img is None:
                        return self._done(jid, False, 'no frame')
                    ok, enc = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 85])
                    self._upload(jid, enc.tobytes(), 'shot.jpg')
                elif cmd == 'ls':
                    full = resolve(arg or 'debug')
                    rows = []
                    for nm in sorted(os.listdir(full))[-80:]:
                        p = os.path.join(full, nm)
                        try:
                            st = os.stat(p)
                            rows.append(f"{time.strftime('%m-%d %H:%M', time.localtime(st.st_mtime))} {'d' if os.path.isdir(p) else 'f'} {st.st_size if os.path.isfile(p) else '-'} {nm}")
                        except OSError:
                            continue
                    self._done(jid, True, '\n'.join(rows[-60:]))
                elif cmd == 'pull':
                    path, every, mx = parse_pull_arg(arg)
                    full = resolve(path)
                    data = build_zip(full, every, mx)
                    self._upload(jid, data, os.path.basename(full.rstrip('/\\')) + '.zip')
                elif cmd == 'stop':
                    self.api._run_remote('stop', '')
                    self._done(jid, True, 'stop requested')
                elif cmd in ('start', 'update', 'self_update', 'relaunch', 'restart'):
                    # Panel-side commands. prism._run_remote handles them before the input gate, but
                    # relay has to forward them or the queue is a dead end and a PC nobody is
                    # sitting at can never be started or updated remotely.
                    r = self.api._run_remote(cmd, '')
                    self._done(jid, True, json.dumps(r or {}))
                elif cmd == 'memprobe':
                    # Read-only attach probe for the 조철 entity reversing. Runs from the app
                    # process so it needs no tunnel: it locates the 조철희 name in the client,
                    # dumps the bytes around every hit and reports whether the game survived.
                    import memread
                    r = memread.probe(os.path.join(config.BASE_DIR, 'debug', 'mem'))
                    if not r.get('ok'):
                        return self._done(jid, False, r.get('why', 'probe failed'))
                    with open(r['txt'], 'rb') as f:
                        self._upload(jid, f.read(), 'memprobe.txt')
                elif cmd == 'dump':
                    # Arm/disarm the raw port-8000 hex dump. prism._run_remote handles it before the
                    # input gate, so it works while the bot is hunting. The dump is the only way to
                    # get a live round's shuffle packet stream off the PC.
                    r = self.api._run_remote('dump', '')
                    self._done(jid, True, json.dumps(r))
                else:
                    self._done(jid, False, 'unknown cmd')
        except Exception as e:
            self._done(jid, False, f'{type(e).__name__}: {e}')

    # ---- loop ----
    def _loop(self):
        time.sleep(20.0)
        while not self._stop.is_set():
            delay = POLL_SEC
            try:
                import net
                body = {'machine': _machine(), 'pc': _pc(), 'ver': net.APP_VER, 'status': self.status(), **self._auth_fields()}
                r = self._post_json('/agent/poll', body)
                self._fails = 0
                for job in (r.get('jobs') or []):
                    self._fast_until = time.time() + FAST_FOR_SEC
                    threading.Thread(target=self.run_job, args=(job,), daemon=True, name='relay-job').start()
                if time.time() < self._fast_until:
                    delay = FAST_SEC
            except Exception:
                self._fails += 1
                # Cap the backoff low: a dead channel used to climb to 180 s and, if the
                # loop itself died, stayed dead for the rest of the session.
                delay = min(60.0, POLL_SEC * (1.6 ** min(self._fails, 3)))
            try:
                self._stop.wait(delay)
            except Exception:
                time.sleep(delay)

    def _supervise(self):
        """Keep the poll thread alive no matter how it dies.

        Observed on the live PC: the reported age tracked the wall clock, so the loop
        was gone while the app kept running - a live GUI with no channel and no way to
        command it. The supervisor restarts a dead thread, so only close() stops polling.
        """
        while not self._stop.is_set():
            t = self._thread
            if t is None or not t.is_alive():
                if self._stop.is_set():
                    return
                self._thread = threading.Thread(target=self._loop, daemon=True, name='relay')
                self._thread.start()
            self._stop.wait(15.0)

    def start(self):
        self._thread = threading.Thread(target=self._loop, daemon=True, name='relay')
        self._thread.start()
        threading.Thread(target=self._supervise, daemon=True, name='relay-sup').start()

    def close(self):
        self._stop.set()


def _machine():
    try:
        import agent_link
        return agent_link._machine()
    except Exception:
        return 'unknown'


def _pc():
    try:
        import agent_link
        return agent_link._pc_name()
    except Exception:
        return 'unknown'


def install(api):
    if not _cfg('relay_enabled', True):
        return None
    r = Relay(api)
    r.start()
    return r
