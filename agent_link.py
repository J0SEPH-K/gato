"""Always-on link from an installed GATO to Jungjun's Mac.

Every install, on every launch:
  1. opens a tiny HTTP API on 127.0.0.1:LINK_PORT (status, log tail, screenshot, commands),
  2. exposes it with a downloaded ngrok tunnel,
  3. announces {machine, pc, url} to a fixed rendezvous topic on ntfy.sh,
  4. keeps announcing so the Mac always has the current URL.

The Mac polls the rendezvous (`tools/hub.py`), sees every PC that is up, and talks to each one
directly through its tunnel. Nothing needs to be configured on the PC, no port forwarding, and
several PCs work at the same time (each has its own tunnel).

All of it is optional at runtime: no ngrok, no internet, no topic -> the bot hunts as before.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import config

LINK_PORT = 8787
# cloudflared quick tunnels first: free, no account, and no limit on how many PCs run at once
# (the free ngrok account allows only 3 simultaneous agents, which is why it is only the fallback).
CF_URL_RE = re.compile(r'https://[a-z0-9-]+\.trycloudflare\.com')
def _cf_asset():
    """(release asset, local name) for this machine. sys.platform, not os.name: macOS is also 'posix'."""
    if sys.platform == 'win32':
        return 'cloudflared-windows-amd64.exe', 'cloudflared.exe'
    if sys.platform == 'darwin':
        import platform
        arch = 'arm64' if platform.machine() in ('arm64', 'aarch64') else 'amd64'
        return f'cloudflared-darwin-{arch}.tgz', 'cloudflared'
    return 'cloudflared-linux-amd64', 'cloudflared'
CF_DL = 'https://github.com/cloudflare/cloudflared/releases/latest/download/'
NGROK_URL_RE = re.compile(r'url=(https://[a-z0-9.\-]+\.ngrok[a-z0-9.\-]*)')
NGROK_DL = 'https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-windows-amd64.zip'
# ntfy.sh's free anonymous tier allows only 250 messages per IP per DAY (not per PC - if several of
# his PCs share one office/home IP they share that quota too). Announcing every 25 s burned through
# it in under 2 hours; after that every post 429s until the daily reset, which looked like the link
# going dead. A real-time status no longer needs frequent announces at all: the hub can just ask the
# PC's last known URL directly (see tools/hub.py). So this only has to announce rarely, plus whenever
# the URL actually changes (new tunnel) - instant on the one event that matters.
ANNOUNCE_SEC = 600.0
MAX_LOG_BYTES = 4 * 1024 * 1024

DEFAULT_TOPIC = 'gato-hub-un6q3wm4tu'
DEFAULT_TOKEN = 'mt4hjwtg3bj5pc4npa3o3w5rfgu4tk2c'
DEFAULT_NGROK_TOKEN = '32QPEAkVjUqwutfuSgN6rWElMDJ_6evGDtiJvWDsg2BzLKYnq'


def _load_cfg():
    try:
        c = config.load()
    except Exception:
        c = {}
    return (str(c.get('link_topic') or DEFAULT_TOPIC).strip(),
            str(c.get('link_token') or DEFAULT_TOKEN).strip(),
            str(c.get('ngrok_authtoken') or DEFAULT_NGROK_TOKEN).strip(),
            bool(c.get('link_enabled', True)))


def _bin_dir():
    d = os.path.join(config.BASE_DIR, 'bin')
    os.makedirs(d, exist_ok=True)
    return d


def _pc_name():
    try:
        import socket
        return socket.gethostname()
    except Exception:
        return 'unknown'


def _machine():
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\Microsoft\Cryptography') as k:
            return str(winreg.QueryValueEx(k, 'MachineGuid')[0])
    except Exception:
        return _pc_name()


def _ver():
    """The app version. VERSION ships next to the exe, but older installs predate that, so fall
    back to the version baked into the build: a '?' on every PC makes the hub useless."""
    for path in (os.path.join(config.RES_DIR, 'VERSION'), os.path.join(config.BASE_DIR, 'VERSION')):
        try:
            with open(path, encoding='utf-8') as f:
                v = f.read().strip()
            if v:
                return v
        except Exception:
            pass
    try:
        import net
        return str(net.CODE_VER or '') or '?'
    except Exception:
        return '?'


class Link:
    def __init__(self, api, topic, token, ngrok_token):
        self.api = api
        self.topic = topic
        self.token = token
        self.ngrok_token = ngrok_token
        self.pc = _pc_name()
        self.machine = _machine()
        self.url = ''
        self.tunnel = None
        self.tunnel_kind = ''
        self.port = LINK_PORT
        self.httpd = None
        self._stop = threading.Event()
        self.log = lambda m: api.vision.note('input', f'[링크] {m}')

    def _handler(self):
        link = self

        class H(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'

            def log_message(self, *a):
                pass

            def _send(self, code, body=b'', ctype='application/json'):
                self.send_response(code)
                self.send_header('content-type', ctype)
                self.send_header('content-length', str(len(body)))
                self.send_header('ngrok-skip-browser-warning', '1')
                self.end_headers()
                if body:
                    self.wfile.write(body)

            def _auth(self):
                if self.headers.get('x-gato-token', '') != link.token:
                    self._send(401, b'{"error":"token"}')
                    return False
                return True

            def do_GET(self):
                if not self._auth():
                    return
                p = self.path.split('?')[0]
                try:
                    if p == '/status':
                        return self._send(200, json.dumps(link.status()).encode())
                    if p == '/log':
                        since = 0
                        q = self.path.split('since=')
                        if len(q) > 1:
                            since = int(q[1].split('&')[0] or 0)
                        return self._send(200, link.log_since(since))
                    if p == '/shot':
                        img = link.api.brain._grab_main()
                        if img is None:
                            return self._send(503, b'{"error":"no frame"}')
                        import cv2
                        ok, buf = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 80])
                        return self._send(200, buf.tobytes(), 'image/jpeg')
                    if p == '/ping':
                        return self._send(200, b'{"ok":true}')
                    return self._send(404, b'{"error":"path"}')
                except Exception as e:
                    return self._send(500, json.dumps({'error': f'{type(e).__name__}: {e}'}).encode())

            def do_POST(self):
                if not self._auth():
                    return
                if self.path.split('?')[0] != '/cmd':
                    return self._send(404, b'{"error":"path"}')
                try:
                    n = int(self.headers.get('content-length') or 0)
                    body = json.loads(self.rfile.read(n) or b'{}')
                    res = link.api._run_remote(str(body.get('cmd') or ''), str(body.get('arg') or ''))
                    return self._send(200, json.dumps({'ok': True, 'res': res}, default=str).encode())
                except Exception as e:
                    return self._send(500, json.dumps({'error': f'{type(e).__name__}: {e}'}).encode())

        return H

    def status(self):
        """Never raises: the hub prints whatever came back, so one missing attribute must not
        turn the whole PC into a 500."""
        out = {'pc': self.pc, 'machine': self.machine, 'ver': _ver(), 'url': self.url,
               'tunnel': self.tunnel_kind, 'ts': time.time(), 'running': False, 'battles': 0,
               'scene': '', 'monster': ''}
        try:
            b = self.api.brain
            out['running'] = bool(getattr(b, 'running', False))
            out['battles'] = int(getattr(b, 'battle_count', 0) or 0)
        except Exception as e:
            out['err'] = f'brain: {type(e).__name__}: {e}'
        try:
            out['scene'] = (self.api.vision.snapshot() or {}).get('scene', '') or ''
        except Exception:
            pass
        try:
            out['monster'] = str(getattr(self.api, 'monster', '') or config.load().get('current_monster', '') or '')
        except Exception:
            pass
        return out

    def log_since(self, since):
        p = os.path.join(config.BASE_DIR, 'gato_debug.log')
        if not os.path.exists(p):
            return b''
        size = os.path.getsize(p)
        if since > size:
            since = 0
        with open(p, 'rb') as f:
            f.seek(max(0, since))
            return f.read(MAX_LOG_BYTES)

    def _download(self, url, dest):
        self.log(f'{os.path.basename(dest)} 내려받는 중')
        tmp = dest + '.part'
        urllib.request.urlretrieve(url, tmp)
        os.replace(tmp, dest)
        return dest

    def _cf_exe(self):
        """The cloudflared binary for this OS, downloaded once. Verified with --version so a
        wrong-architecture or partial download falls back instead of hanging forever."""
        asset, name = _cf_asset()
        exe = os.path.join(_bin_dir(), name)
        if not os.path.exists(exe):
            tmp = self._download(CF_DL + asset, os.path.join(_bin_dir(), asset))
            if asset.endswith('.tgz'):
                import tarfile
                with tarfile.open(tmp) as tf:
                    for mem in tf.getmembers():
                        if mem.name.endswith('cloudflared'):
                            with tf.extractfile(mem) as src, open(exe, 'wb') as dst:
                                dst.write(src.read())
                            break
                os.remove(tmp)
            else:
                os.replace(tmp, exe)
            if not os.path.exists(exe):
                raise RuntimeError('cloudflared 없음')
            os.chmod(exe, 0o755)
            subprocess.run([exe, '--version'], capture_output=True, timeout=90, check=True)
        return exe

    def _ngrok_exe(self):
        exe = os.path.join(_bin_dir(), 'ngrok.exe')
        if os.path.exists(exe):
            return exe
        z = self._download(NGROK_DL, exe + '.zip')
        import zipfile
        with zipfile.ZipFile(z) as zf:
            for n in zf.namelist():
                if n.lower().endswith('ngrok.exe'):
                    with zf.open(n) as src, open(exe, 'wb') as dst:
                        dst.write(src.read())
                    break
        os.remove(z)
        if not os.path.exists(exe):
            raise RuntimeError('ngrok.exe 없음')
        return exe

    def _start_tunnel(self):
        """cloudflared; if that fails, ngrok. Whichever wins sets self.url and announces it."""
        try:
            exe = self._cf_exe()
            self.tunnel_kind = 'cloudflared'
            cmd = [exe, 'tunnel', '--url', f'http://127.0.0.1:{self.port}', '--no-autoupdate']
        except Exception as e:
            self.log(f'cloudflared 준비 실패 ({type(e).__name__}) — ngrok 로 대체')
            exe = self._ngrok_exe()
            self.tunnel_kind = 'ngrok'
            cmd = [exe, 'http', str(self.port), '--log=stdout', '--authtoken', self.ngrok_token]
        flags = 0x08000000 if os.name == 'nt' else 0
        self.tunnel = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                       creationflags=flags, text=True, encoding='utf-8', errors='replace')

        def _reader():
            for line in self.tunnel.stdout:
                m = (CF_URL_RE if self.tunnel_kind == 'cloudflared' else NGROK_URL_RE).search(line)
                if m:
                    url = m.group(0 if self.tunnel_kind == 'cloudflared' else 1)
                    if url != self.url:
                        self.url = url
                        self.log(f'터널({self.tunnel_kind}) {url}')
                        threading.Thread(target=self._announce_verified, daemon=True).start()
                if 'ERR_NGROK' in line or 'failed to' in line.lower():
                    self.log(line.strip()[:160])
        threading.Thread(target=_reader, daemon=True).start()

    def _announce_verified(self, tries=8):
        """Hold the announcement until the tunnel answers from outside, so the hub never gets a
        URL that is not usable yet."""
        for _ in range(tries):
            if self._stop.is_set() or not self.url:
                return
            if self._public_ok():
                self._announce()
                return
            time.sleep(3.0)
        self._announce()

    def _announce(self):
        if not self.url:
            return
        body = json.dumps({'pc': self.pc, 'machine': self.machine, 'url': self.url,
                           'ver': _ver(), 'ts': time.time()}).encode()
        req = urllib.request.Request(f'https://ntfy.sh/{self.topic}', data=body, method='POST',
                                     headers={'content-type': 'application/json',
                                              'user-agent': 'gato-link/1'})
        try:
            urllib.request.urlopen(req, timeout=15).read()
            self._announce_fails = 0
        except urllib.error.HTTPError as e:
            self._announce_fails = getattr(self, '_announce_fails', 0) + 1
            if self._announce_fails in (1, 5) or self._announce_fails % 50 == 0:
                detail = ''
                try:
                    detail = e.read().decode('utf-8', 'replace')[:120]
                except Exception:
                    pass
                self.log(f'알림 실패 {self._announce_fails}회: HTTP {e.code} {detail}'
                         + (' — 공개 ntfy.sh 하루 할당량(IP당 250건) 소진 추정' if e.code == 429 else ''))
        except Exception as e:
            self._announce_fails = getattr(self, '_announce_fails', 0) + 1
            if self._announce_fails in (1, 5) or self._announce_fails % 50 == 0:
                self.log(f'알림 실패 {self._announce_fails}회: {type(e).__name__}: {e}')

    def start(self):
        """Bind a local port (LINK_PORT, or the next free one if two instances share a PC) and go."""
        self.httpd = None
        for port in range(LINK_PORT, LINK_PORT + 20):
            try:
                self.httpd = ThreadingHTTPServer(('127.0.0.1', port), self._handler())
                self.port = port
                break
            except OSError:
                continue
        if self.httpd is None:
            self.log(f'로컬 포트 {LINK_PORT}~ 사용 불가 — 링크 없이 계속')
            return
        self.httpd.daemon_threads = True
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        threading.Thread(target=self._loop, daemon=True).start()
        self.log(f'링크 시작 (포트 {self.port})')

    def _local_ok(self):
        """Is our own HTTP server answering? A tunnel over a dead origin just returns 502."""
        try:
            req = urllib.request.Request(f'http://127.0.0.1:{self.port}/ping',
                                         headers={'x-gato-token': self.token})
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status == 200
        except Exception:
            return False

    def _public_ok(self):
        """Does the tunnel actually reach us from outside? Only a real request proves it:
        cloudflared prints its URL before the route is ready, and a half-open tunnel keeps
        announcing while every request 502s."""
        if not self.url:
            return False
        try:
            req = urllib.request.Request(self.url + '/ping',
                                         headers={'user-agent': 'gato-link/1',
                                                  'ngrok-skip-browser-warning': '1',
                                                  'x-gato-token': self.token})
            with urllib.request.urlopen(req, timeout=15) as r:
                return r.status == 200
        except Exception:
            return False

    def _rebind(self):
        try:
            if self.httpd is not None:
                self.httpd.shutdown()
                self.httpd.server_close()
        except Exception:
            pass
        self.httpd = None
        for port in range(LINK_PORT, LINK_PORT + 20):
            try:
                self.httpd = ThreadingHTTPServer(('127.0.0.1', port), self._handler())
                self.httpd.daemon_threads = True
                self.port = port
                threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
                return True
            except OSError:
                continue
        return False

    def _loop(self):
        bad_local = 0
        bad_public = 0
        while not self._stop.wait(ANNOUNCE_SEC if self.url else 5.0):
            try:
                if not self._local_ok():
                    bad_local += 1
                    if bad_local >= 2:
                        self.log('로컬 서버 무응답 — 다시 엶')
                        if not self._rebind():
                            self.log(f'포트 {LINK_PORT}~ 사용 불가')
                        bad_local = 0
                else:
                    bad_local = 0
                if self.tunnel is None or self.tunnel.poll() is not None:
                    if self.tunnel is not None:
                        self.log('터널 종료 — 재시작')
                    self.url = ''
                    self._start_tunnel()
                    bad_public = 0
                elif self.url:
                    if self._public_ok():
                        bad_public = 0
                    else:
                        bad_public += 1
                        if bad_public >= 2:
                            self.log(f'터널 무응답 {bad_public}회 — 새 터널')
                            try:
                                self.tunnel.terminate()
                            except Exception:
                                pass
                            self.url = ''
                            bad_public = 0
                self._announce()
            except Exception as e:
                self.log(f'{type(e).__name__}: {e}')

    def close(self):
        self._stop.set()
        for fn in (lambda: self.tunnel and self.tunnel.poll() is None and self.tunnel.terminate(),
                   lambda: self.httpd and self.httpd.shutdown()):
            try:
                fn()
            except Exception:
                pass


def install(api):
    topic, token, ngrok_token, enabled = _load_cfg()
    if not enabled:
        return None
    link = Link(api, topic, token, ngrok_token)
    link.start()
    return link
