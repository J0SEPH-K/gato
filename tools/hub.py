#!/usr/bin/env python3
"""Mac side of the GATO link: list every PC that is up, and talk to each one.

PCs announce themselves to a fixed ntfy topic (agent_link.py on the PC). This tool
reads that topic, keeps the newest URL per machine, drops anything that has not
announced for STALE_SEC, then talks to each PC directly through its own tunnel.

    python3 tools/hub.py list                     # who is up
    python3 tools/hub.py log   <pc> [-n 80]       # tail of that PC's log
    python3 tools/hub.py shot  <pc> [out.jpg]     # screenshot
    python3 tools/hub.py cmd   <pc> stop|start    # remote command
    python3 tools/hub.py watch                    # poll, print ups and downs
"""
import json
import os
import sys
import time
import urllib.request

TOPIC = os.environ.get('GATO_TOPIC') or 'gato-hub-un6q3wm4tu'
TOKEN = os.environ.get('GATO_TOKEN') or 'mt4hjwtg3bj5pc4npa3o3w5rfgu4tk2c'
STALE_SEC = 150.0
STATE = os.path.expanduser('~/.gato_hub/state.json')
UA = {'user-agent': 'gato-hub/1', 'ngrok-skip-browser-warning': '1'}


def _state():
    try:
        with open(STATE, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def _save(s):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    tmp = STATE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(s, f, ensure_ascii=False, indent=1)
    os.replace(tmp, STATE)


def poll():
    try:
        req = urllib.request.Request(f'https://ntfy.sh/{TOPIC}/json?poll=1&since=30m', headers=UA)
        raw = urllib.request.urlopen(req, timeout=25).read().decode('utf-8', 'replace')
    except Exception as e:
        print(f'# rendezvous unreachable: {type(e).__name__}: {e}', file=sys.stderr)
        raw = ''
    st = _state()
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            m = json.loads(line)
            d = json.loads(m.get('message') or '{}')
        except Exception:
            continue
        if not d.get('machine') or not d.get('url'):
            continue
        st[d['machine']] = {'pc': d.get('pc', '?'), 'url': d['url'], 'ver': d.get('ver', '?'),
                            'seen': float(m.get('time') or time.time())}
    now = time.time()
    live = {k: v for k, v in st.items() if now - v['seen'] < STALE_SEC}
    _save(live)
    return live


def _pick(name, live):
    if name.lower() in live:
        return live[name.lower()]
    for k, v in live.items():
        if name.lower() in v['pc'].lower() or v['pc'].lower().startswith(name.lower()):
            return v
    raise SystemExit(f'no live PC matching {name!r} (see: hub.py list)')


def get(v, path, timeout=30, tries=3):
    """Quick tunnels are sometimes slow on the first request after an idle period, so a timeout
    or 5xx is retried. A 401 is not: that is a real token mismatch."""
    last = None
    for i in range(tries):
        req = urllib.request.Request(v['url'] + path, headers={**UA, 'x-gato-token': TOKEN})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            body = ''
            try:
                body = e.read().decode('utf-8', 'replace')[:200]
            except Exception:
                pass
            last = f'HTTP {e.code} {body}'.strip()
            if e.code < 500:
                raise SystemExit(f'{v["pc"]}: {last}')
        except Exception as e:
            last = f'{type(e).__name__}: {e}'
        if i < tries - 1:
            time.sleep(4 * (i + 1))
    raise RuntimeError(f'{v["pc"]}: {last}')


def post(v, path, obj, timeout=30):
    req = urllib.request.Request(v['url'] + path, data=json.dumps(obj).encode(), method='POST',
                                 headers={**UA, 'x-gato-token': TOKEN, 'content-type': 'application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode() or '{}')


def main(argv):
    cmd = argv[1] if len(argv) > 1 else 'list'
    live = poll()
    if cmd == 'list':
        if not live:
            print('no PC is up (nothing announced in the last %d s)' % STALE_SEC)
            return 0
        for k, v in sorted(live.items(), key=lambda x: x[1]['pc']):
            try:
                s = json.loads(get(v, '/status', 10))
                state = ('running, %d battles' % s['battles']) if s['running'] else 'stopped'
                print(f"{v['pc']:<20} v{v['ver']:<6} {state:<22} {s['monster']}  {int(time.time()-v['seen'])}s ago")
            except Exception as e:
                print(f"{v['pc']:<20} v{v['ver']:<6} unreachable: {type(e).__name__}: {e}")
        return 0
    if cmd == 'watch':
        seen = set()
        while True:
            live = poll()
            cur = {(v['pc'], v['url']) for v in live.values()}
            for k, v in live.items():
                key = (v['pc'], v['url'])
                if key not in seen:
                    seen.add(key)
                    try:
                        s = json.loads(get(v, '/status', 10))
                        print(f"{time.strftime('%H:%M:%S')} UP {v['pc']} v{v['ver']} running={s['running']} battles={s['battles']} scene={s['scene']}", flush=True)
                    except Exception as e:
                        print(f"{time.strftime('%H:%M:%S')} UP {v['pc']} (status failed: {type(e).__name__})", flush=True)
            for key in list(seen - cur):
                print(f"{time.strftime('%H:%M:%S')} DOWN {key[0]}", flush=True)
                seen.discard(key)
            time.sleep(20)
    if len(argv) < 3:
        raise SystemExit('usage: hub.py {list|watch|log|shot|cmd} [pc] [arg]')
    v = _pick(argv[2], live)
    if cmd == 'log':
        n = int(argv[4]) if len(argv) > 4 else 80
        body = get(v, '/log?since=0', 40).decode('utf-8', 'replace').splitlines()
        print('\n'.join(body[-n:]))
    elif cmd == 'shot':
        out = argv[3] if len(argv) > 3 else '/tmp/gato_shot.jpg'
        open(out, 'wb').write(get(v, '/shot', 40))
        print(out)
    elif cmd == 'cmd':
        print(json.dumps(post(v, '/cmd', {'cmd': argv[3], 'arg': argv[4] if len(argv) > 4 else ''}), ensure_ascii=False)[:400])
    else:
        raise SystemExit('unknown command ' + cmd)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
