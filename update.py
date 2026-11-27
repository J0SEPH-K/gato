"""Auto-update from the public release repo.

The release repo is public, so no token is needed. On launch and every few hours the app asks
GitHub for the newest release, compares the tag with VERSION, and — when the bot is idle — installs
it silently and comes back up. Everything here is optional: no internet or a private repo just means
"no update", never a broken start.

Only a frozen (installed) build updates itself; a source checkout is left to git.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import threading
import time
import urllib.request

import config

REPO = 'J0SEPH-K/gato-setup'
API = f'https://api.github.com/repos/{REPO}/releases/latest'
ASSET_NAME = 'GatoSetup.exe'
CHECK_FIRST_SEC = 90.0
CHECK_FAST_SEC = 45.0   # cadence while the server floor blocks this build
CHECK_EVERY_SEC = 6 * 3600.0
UA = {'user-agent': 'gato-updater/1', 'accept': 'application/vnd.github+json'}
MAX_BYTES = 900 * 1024 * 1024


def current_version():
    return config.read_version()


def _tag_key(tag):
    parts = []
    for p in tag.lstrip('vV').replace('-', '.').split('.'):
        parts.append(int(p) if p.isdigit() else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


def check(timeout=20):
    """{'tag','url','size','sha256'} for a newer release, else None."""
    try:
        req = urllib.request.Request(API, headers=UA)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            rel = json.loads(r.read().decode() or '{}')
    except Exception:
        return None
    tag = str(rel.get('tag_name') or '')
    cur = current_version()
    if not tag or not cur or _tag_key(tag) <= _tag_key(cur):
        return None
    for a in rel.get('assets') or []:
        if a.get('name') == ASSET_NAME and a.get('state') == 'uploaded':
            digest = str(a.get('digest') or '')
            return {'tag': tag, 'url': a.get('browser_download_url') or a.get('url'),
                    'size': int(a.get('size') or 0),
                    'sha256': digest.split(':', 1)[1] if digest.startswith('sha256:') else ''}
    return None


def download(info, log=lambda m: None):
    dest = os.path.join(config.BASE_DIR, 'update', f'GatoSetup-{info["tag"]}.exe')
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    tmp = dest + '.part'
    h = hashlib.sha256()
    got = 0
    req = urllib.request.Request(info['url'], headers={**UA, 'accept': 'application/octet-stream'})
    with urllib.request.urlopen(req, timeout=60) as r, open(tmp, 'wb') as f:
        while True:
            chunk = r.read(256 * 1024)
            if not chunk:
                break
            got += len(chunk)
            if got > MAX_BYTES:
                raise RuntimeError('설치 파일이 너무 큼')
            h.update(chunk)
            f.write(chunk)
    if info.get('size') and got != info['size']:
        os.remove(tmp)
        raise RuntimeError(f'크기 불일치 {got}/{info["size"]}')
    if info.get('sha256') and h.hexdigest().lower() != info['sha256'].lower():
        os.remove(tmp)
        raise RuntimeError('SHA256 불일치')
    os.replace(tmp, dest)
    log(f'내려받기 완료 {got // (1024 * 1024)}MB')
    return dest


def apply(installer, log=lambda m: None):
    """Hand over to the installer from a detached .cmd so this process can exit cleanly."""
    exe = os.path.abspath(sys.executable)
    cmd = os.path.join(config.BASE_DIR, 'update', 'apply.cmd')
    os.makedirs(os.path.dirname(cmd), exist_ok=True)
    with open(cmd, 'w', encoding='utf-8') as f:
        f.write('@echo off\r\n')
        f.write('ping -n 3 127.0.0.1 >nul\r\n')
        f.write(f'"{installer}" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /CLOSEAPPLICATIONS\r\n')
        f.write('ping -n 3 127.0.0.1 >nul\r\n')
        f.write(f'start "" "{exe}"\r\n')
        f.write('del "%~f0"\r\n')
    kwargs = {'close_fds': True}
    if os.name == 'nt':
        # CREATE_NO_WINDOW | DETACHED_PROCESS: keeps running after this process exits
        kwargs['creationflags'] = 0x08000000 | 0x00000008
    subprocess.Popen(['cmd', '/c', cmd], **kwargs)
    log('설치 프로그램 실행 — 앱을 다시 시작합니다')


def install(api):
    """Background checker. Returns the thread, or None when this is not a frozen build."""
    if not getattr(sys, 'frozen', False):
        return None
    log = lambda m: api.vision.note('input', f'[업데이트] {m}')

    def _loop():
        time.sleep(CHECK_FIRST_SEC)
        while True:
            try:
                info = check()
                if info:
                    log(f'{info["tag"]} 발견 (현재 {current_version()}) — 내려받는 중')
                    path = download(info, log)
                    waited = 0.0
                    # A forced update (server floor above this build) must land
                    # quickly, so it only gives the bot a couple of minutes.
                    limit = 150.0 if api.auth.must_update() else 1800.0
                    while api.brain.running and waited < limit:
                        time.sleep(5.0)
                        waited += 5.0
                    api._update_ready = {'tag': info['tag'], 'path': path}
                    apply(path, log)
                    time.sleep(6.0)
                    try:
                        api.brain.stop()
                        api.engine.stop()
                    except Exception:
                        pass
                    os._exit(0)
            except Exception as e:
                log(f'실패 {type(e).__name__}: {e}')
            # A raised server floor is the one case where the next check cannot wait hours:
            # the bot refuses to start until the build is replaced, so poll fast and land it.
            # must_update() can flip *while* we sleep (the floor is raised from the server), so
            # sleep in slices and re-read it — a flat 6 h sleep ignored the floor for hours.
            nap = CHECK_FAST_SEC if api.auth.must_update() else CHECK_EVERY_SEC
            while nap > 0:
                time.sleep(min(15.0, nap))
                nap -= 15.0
                if api.auth.must_update() and nap > CHECK_FAST_SEC:
                    nap = CHECK_FAST_SEC

    t = threading.Thread(target=_loop, daemon=True)
    t.start()
    return t
