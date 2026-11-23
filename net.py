# Decompiled with PyLingual (https://pylingual.io)
# Internal filename: 'net.py'
# Bytecode version: 3.11a7e (3495)
# Source timestamp: 2026-08-10 04:23:54 UTC (1786335834)

from __future__ import annotations
import base64
import hashlib
import json
import os
import threading
import time
import ssl
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
try:
    import certifi
    _SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except Exception:
    _SSL_CTX = ssl.create_default_context()
# License backend (Cloudflare Worker, see server/). Override with GATO_SERVER for
# a local wrangler dev run.
LICENSE_SERVER = 'https://gato-license.gigan.workers.dev'
SERVER = os.environ.get('GATO_SERVER', '').strip() or LICENSE_SERVER
CLIENT_VER = '1.0'

def _app_ver():
    try:
        import config as _config
        with open(os.path.join(_config.RES_DIR, 'VERSION'), encoding='utf-8') as f:
            return f.read().strip()
    except Exception:
        return CLIENT_VER

APP_VER = _app_ver()

_HWID_PATH = None

def hwid() -> str:
    """Stable per-machine id: MachineGuid + volume serial + node, hashed. Cached."""
    global _HWID_PATH
    try:
        import config as _config
        if _HWID_PATH is None:
            _HWID_PATH = os.path.join(_config.BASE_DIR, 'hwid.txt')
        with open(_HWID_PATH, encoding='utf-8') as f:
            cached = f.read().strip()
        if len(cached) == 32:
            return cached
    except Exception:
        pass
    parts = []
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\Microsoft\Cryptography') as k:
            parts.append(str(winreg.QueryValueEx(k, 'MachineGuid')[0]))
    except Exception:
        pass
    try:
        import ctypes
        serial = ctypes.c_ulong(0)
        ctypes.windll.kernel32.GetVolumeInformationW('C:\\', None, 0, ctypes.byref(serial), None, None, None, 0)
        parts.append(str(serial.value))
    except Exception:
        pass
    try:
        import uuid
        parts.append(str(uuid.getnode()))
    except Exception:
        pass
    parts.append(os.environ.get('COMPUTERNAME', '') or 'unknown')
    value = hashlib.sha256('|'.join(parts).encode('utf-8')).hexdigest()[:32]
    try:
        with open(_HWID_PATH, 'w', encoding='utf-8') as f:
            f.write(value)
    except Exception:
        pass
    return value
# The original launcher exported this from the signed manifest. Running from source
# there is no launcher, so fall back to the version the local cache manifest carries
# (4.56) or the vendor blocks the client as outdated (min_code_version 4.54).
def _default_code_ver():
    try:
        import json as _json
        _here = os.path.dirname(os.path.abspath(__file__))
        for _p in (os.path.join(_here, 'gato_cache', 'manifest_local.json'),
                   os.path.join(os.path.dirname(_here), 'gato_cache', 'manifest_local.json')):
            with open(_p, encoding='utf-8') as f:
                return str(_json.load(f).get('version') or '')
    except Exception:
        return ''

CODE_VER = os.environ.get('GATOSUPER_CODE_VERSION', '') or _default_code_ver()

# No vendor subscription: auth never gates the bot. Set GATO_LOCAL=0 to use the
# vendor server again.
LOCAL = os.environ.get('GATO_LOCAL', '0') == '1'
HEARTBEAT_SEC = 60
TIMEOUT = 6.0
MAX_NET_FAILS = 3
REASON_LABELS = {'denied': '미등록 키', 'unknown': '없는 라이선스 키', 'bad_request': '요청 오류', 'revoked': '키 차단됨', 'blocked': '임시차단됨', 'kicked': '다른 곳에서 로그인됨', 'expired': '사용 기한 만료', 'depleted': '사용 횟수 소진', 'outdated': '업데이트 필요', 'limit': 'PC 대수 초과', 'network': '서버 연결 실패'}
def _new_session():
    try:
        import certifi as _certifi
        import requests as _requests
        from requests.adapters import HTTPAdapter
    except Exception:
        return None
    try:
        s = _requests.Session()
        s.verify = _certifi.where()
        # Cloudflare's bot filter answers 403 / error 1010 to the default
        # python-requests UA, so every client has to announce itself.
        s.headers.update({'User-Agent': f'GATO/{CLIENT_VER}', 'Accept': 'application/json'})
        ad = HTTPAdapter(pool_connections=4, pool_maxsize=8, max_retries=0)
        s.mount('https://', ad)
        s.mount('http://', ad)
        return s
    except Exception:
        return None
_SESSION = _new_session()
def _post(path: str, payload: dict, timeout: float=None) -> dict:
    if _SESSION is not None:
        r = _SESSION.post(SERVER + path, json=payload, timeout=timeout or TIMEOUT)
        r.raise_for_status()
        return r.json()
    else:
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(SERVER + path, data=data, headers={'Content-Type': 'application/json', 'User-Agent': f'GATO/{CLIENT_VER}', 'Accept': 'application/json'})
        with urllib.request.urlopen(req, timeout=timeout or TIMEOUT, context=_SSL_CTX) as r:
            return json.loads(r.read().decode('utf-8'))
CMD_TIMEOUT = 40
def _ver_key(v):
    out = []
    for p in str(v or '').lstrip('vV').replace('-', '.').split('.'):
        out.append(int(p) if p.isdigit() else 0)
    while len(out) < 3:
        out.append(0)
    return tuple(out[:3])


def _err_detail(e) -> str:
    resp = getattr(e, 'response', None)
    if resp is not None and getattr(resp, 'status_code', None):
        return f'HTTP {resp.status_code}'
    else:
        _n = type(e).__name__
        if _n in ['ReadTimeout', 'ConnectTimeout', 'Timeout']:
            return 'timeout'
        else:
            if _n in ['ConnectionError', 'ProxyError', 'SSLError', 'ChunkedEncodingError']:
                return _n
            else:
                if isinstance(e, urllib.error.HTTPError):
                    return f'HTTP {e.code}'
                else:
                    if isinstance(e, urllib.error.URLError):
                        r = getattr(e, 'reason', None)
                        if isinstance(r, Exception):
                            return f'{type(r).__name__}: {r}'
                        else:
                            return f'URLError: {r or e}'
                    else:
                        return f'{type(e).__name__}: {e}'
class AuthClient:
    def __init__(self, mob: str=''):
        self.auth_id = ''
        self.token = ''
        self.mob = mob
        self.ok = False
        self.reason = ''
        self.days_left = None
        self.expiry = ''
        self.credits = None
        self.banja = False
        self.no_battle_limit = 0
        self.notice = ''
        self.latest_patch = ''
        self.min_ver = ''
        self.hwid = hwid()
        self._net_fails = 0
        self.state = {}
        self.net_err = ''
        self.grace = False
    def label(self) -> str:
        if LOCAL:
            return '로컬 모드'
        if self.ok:
            if self.grace:
                return '인증 · 서버 연결 대기(임시 유지)'
            if self.credits is not None:
                return f'인증 · 잔여 {self.credits}회'
            else:
                if self.days_left is not None:
                    return f'인증 · D-{max(0, self.days_left)}'
                else:
                    return '인증 OK'
        else:
            if self.reason == 'network' and self.net_err:
                return f'서버 연결 실패 · {self.net_err}'
            else:
                return REASON_LABELS.get(self.reason, '미인증')
    def login(self, auth_id: str) -> bool:
        self.auth_id = (auth_id or '').strip()
        self.ok = False
        self.token = ''
        if LOCAL:
            self.ok = True
            self.reason = ''
            self.days_left = None
            self.credits = None
            self.token = 'local'
            return True
        if not self.auth_id:
            self.reason = ''
            return False
        else:
            r = None
            for attempt in range(3):   # one flaky request must not show '로그인 필요'
                try:
                    r = _post('/auth', {'id': self.auth_id, 'hwid': self.hwid, 'mob': self.mob, 'ver': APP_VER, 'code_ver': CODE_VER})
                    break
                except Exception as e:
                    self.net_err = _err_detail(e)
                    if attempt < 2:
                        time.sleep(1.5 * (attempt + 1))
            if r is None:
                self.reason = 'network'
                if self._grace_ok():
                    return True
                return False
            self._absorb(r)
            if not r.get('ok'):
                self.reason = r.get('reason', 'denied')
                return False
            else:
                if r.get('expired'):
                    self.reason = 'expired'
                    return False
                else:
                    if r.get('depleted'):
                        self.reason = 'depleted'
                        return False
                    else:
                        self.token = r.get('token', '')
                        self.expiry = r.get('expiry', '') or ''
                        self.days_left = r.get('days_left', self._calc_days())
                        self.ok = True
                        self.reason = ''
                        self._net_fails = 0
                        self.grace = False
                        self._remember_ok()
                        return True
    GRACE_SEC = 12 * 3600
    def _grace_path(self) -> str:
        import config as _config
        return os.path.join(_config.BASE_DIR, 'auth_grace.json')
    def _remember_ok(self) -> None:
        """Remember that THIS key logged in on THIS PC just now (no secret beyond what the user typed)."""
        try:
            with open(self._grace_path(), 'w', encoding='utf-8') as f:
                json.dump({'id': self.auth_id, 'hwid': self.hwid, 'token': self.token, 'ts': time.time(),
                           'expiry': self.expiry, 'credits': self.credits}, f)
        except Exception:
            pass
    def _grace_ok(self) -> bool:
        """Server unreachable: keep an already-verified PC running for 12 h instead of blocking start."""
        try:
            with open(self._grace_path(), encoding='utf-8') as f:
                g = json.load(f)
            if g.get('id') != self.auth_id or g.get('hwid') != self.hwid or not g.get('token'):
                return False
            if time.time() - float(g.get('ts', 0)) > self.GRACE_SEC:
                return False
            self.token = g['token']
            self.expiry = g.get('expiry', '') or ''
            self.ok = True
            self.reason = ''
            self.grace = True
            return True
        except Exception:
            return False
    def heartbeat(self) -> bool:
        if LOCAL:
            return self.ok
        if not self.token:
            return self.ok
        else:
            try:
                r = _post('/heartbeat', {'id': self.auth_id, 'token': self.token, 'hwid': self.hwid, 'mob': self.mob, 'ver': APP_VER, 'code_ver': CODE_VER, **(self.state or {})})
            except Exception as e:
                self._net_fails += 1
                self.net_err = _err_detail(e)
                if self._net_fails >= MAX_NET_FAILS:
                    self.ok = False
                    self.reason = 'network'
                    return False
                else:
                    return self.ok
            self._net_fails = 0
            self._absorb(r)
            if not r.get('ok'):
                self.ok = False
                self.reason = r.get('reason', 'revoked')
                self.days_left = r.get('days_left', self._calc_days())
                return False
            else:
                self.days_left = r.get('days_left', self._calc_days())
                self.ok = True
                return True
    def _absorb(self, r: dict) -> None:
        """Common fields the server returns on both /auth and /heartbeat."""
        if isinstance(r.get('notice'), str):
            self.notice = r.get('notice') or ''
        mv = str(r.get('min_ver') or '')
        if mv:
            self.min_ver = mv
        self.latest_patch = str(r.get('patch', self.latest_patch) or '')
    def update_available(self) -> bool:
        """True when the server's floor is above this build."""
        if not self.min_ver or not APP_VER:
            return bool(CODE_VER and self.latest_patch and (self.latest_patch != CODE_VER))
        return _ver_key(APP_VER) < _ver_key(self.min_ver)

    def must_update(self) -> bool:
        """Server refuses this build - the bot may not start until it updates."""
        return self.reason == 'outdated'
    def _calc_days(self):
        if not self.expiry:
            return
        else:
            try:
                deadline = datetime.strptime(self.expiry, '%Y-%m-%d') + timedelta(days=1)
                return (deadline - datetime.now()).days
            except Exception:
                return None
    def _fire(self, path: str, payload: dict) -> None:
        if LOCAL:
            return None
        def _run():
            try:
                _post(path, payload)
            except Exception:
                return None
        threading.Thread(target=_run, daemon=True).start()
    def report_battle(self) -> None:
        if self.token:
            self._fire('/battle', {'id': self.auth_id, 'token': self.token})
    def report_appear(self, kind: str, wrong: bool=False) -> None:
        if self.token:
            self._fire('/appear', {'id': self.auth_id, 'token': self.token, 'kind': kind, 'wrong': wrong})
    def upload_jamun_debug(self, png_bytes: bytes, text: str, conf: float) -> None:
        if not self.token or not png_bytes or len(png_bytes) > 250000:
            return None
        else:
            self._fire('/debug/jamun', {'id': self.auth_id, 'token': self.token, 'png_b64': base64.b64encode(png_bytes).decode('ascii'), 'text': str(text)[:8], 'conf': float(conf)})
    def report_jamun_wrong(self) -> None:
        if self.token:
            self._fire('/debug/jamun_wrong', {'id': self.auth_id, 'token': self.token})
    def upload_jochul_debug(self, zip_bytes: bytes, reason: str) -> None:
        if not self.token or not zip_bytes or len(zip_bytes) > 39000000:
            return None
        else:
            def _run():
                url = f'{SERVER}/debug/jochul?id={urllib.parse.quote(self.auth_id)}&token={self.token}&reason={urllib.parse.quote(str(reason)[:80])}'
                for attempt in range(4):   # a single dropped request used to lose the whole round
                    try:
                        req = urllib.request.Request(url, data=zip_bytes, headers={'Content-Type': 'application/zip'}, method='POST')
                        urllib.request.urlopen(req, timeout=180, context=_SSL_CTX)
                        return None
                    except Exception:
                        time.sleep(5 * (attempt + 1))
                return None
            threading.Thread(target=_run, daemon=True).start()
    def report_error(self, kind: str, text: str, wait: bool=False) -> None:
        if not self.token:
            return
        else:
            payload = {'id': self.auth_id, 'token': self.token, 'kind': kind[:40], 'text': text[:4000], 'ver': CODE_VER}
            if not wait:
                self._fire('/error', payload)
                return
            else:
                try:
                    _post('/error', payload, timeout=4.0)
                except Exception:
                    return None
    def get_settings(self):
        if LOCAL or not self.token:
            return False
        else:
            try:
                url = f'{SERVER}/settings?id={urllib.parse.quote(self.auth_id)}&token={self.token}'
                with urllib.request.urlopen(url, timeout=TIMEOUT, context=_SSL_CTX) as r:
                    d = json.loads(r.read().decode('utf-8'))
                return d.get('settings') if d.get('ok') else False
            except Exception:
                return False
    def put_settings(self, settings: dict) -> None:
        if LOCAL:
            return None
        if self.token:
            self._fire('/settings', {'id': self.auth_id, 'token': self.token, 'settings': settings})
    def poll_cmd(self):
        if LOCAL or not self.token:
            return []
        else:
            try:
                r = _post('/cmd', {'id': self.auth_id, 'token': self.token}, timeout=CMD_TIMEOUT)
            except Exception:
                return []
            return r.get('cmds') or [] if r.get('ok') else []
    def upload_shot(self, jpg_bytes: bytes) -> bool:
        if not self.token or not jpg_bytes:
            return False
        else:
            try:
                r = _post('/shot', {'id': self.auth_id, 'token': self.token, 'jpg_b64': base64.b64encode(jpg_bytes).decode('ascii')})
                return bool(r.get('ok'))
            except Exception:
                return False
    def live_uploader(self):
        try:
            import certifi as _certifi
            import requests as _requests
            s = _requests.Session()
            s.verify = _certifi.where()
            def _up(jpg_bytes: bytes) -> bool:
                if not self.token or not jpg_bytes:
                    return False
                else:
                    try:
                        r = s.post(f'{SERVER}/shot', json={'id': self.auth_id, 'token': self.token, 'jpg_b64': base64.b64encode(jpg_bytes).decode('ascii')}, timeout=TIMEOUT)
                        return bool(r.json().get('ok'))
                    except Exception:
                        return False
            return _up
        except Exception:
            return self.upload_shot
    def upload_stats(self, state: str, stats: dict) -> bool:
        if not self.token:
            return False
        else:
            try:
                r = _post('/stats', {'id': self.auth_id, 'token': self.token, 'state': state, 'stats': stats})
                return bool(r.get('ok'))
            except Exception:
                return False
    def nlp_parse(self, text: str):
        if not self.token:
            return
        else:
            try:
                r = _post('/nlp/parse', {'id': self.auth_id, 'token': self.token, 'text': text})
                return r if r.get('ok') else None
            except Exception:
                return None
    def nlp_chat(self, text: str):
        if not self.token:
            return
        else:
            try:
                r = _post('/nlp/chat', {'id': self.auth_id, 'token': self.token, 'text': text})
                return r.get('answer') if r.get('ok') else None
            except Exception:
                return None