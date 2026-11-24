#!/usr/bin/env python3
"""Owner CLI for the server relay (no tunnel needed).

  relay_cli.py agents                       every PC that polled, age in seconds, running/battles/scene, last log lines
  relay_cli.py log  <pc> [bytes]            tail of gato_debug.log  -> /tmp/relay/<pc>_log.txt
  relay_cli.py shot <pc>                    current game frame      -> /tmp/relay/<pc>_shot.jpg
  relay_cli.py ls   <pc> [debug/...]        directory listing under debug/
  relay_cli.py pull <pc> <path> [every=N] [mb=N]   zip of a debug folder (e.g. debug/jochul_rounds/round_x)
  relay_cli.py jobs                         recent jobs incl. automatic wrong-round uploads (cmd autodebug)
  relay_cli.py get  <jobid>                 download a finished job's file
  relay_cli.py stop <pc>                    stop the macro on that PC
  relay_cli.py watch <pc> [secs] [rounds]   live-tail that PC's log forever (Ctrl-C to stop)

A customer only has to be running the app: the relay key is baked in, so a PC is watchable from
the moment it starts, with no tunnel and no setup on their side. The PC must run >= 1.0.16 (that
is when relay.py first shipped).

Admin key: $GATO_ADMIN_KEY, else server/.secrets.txt (ADMIN_KEY).
"""
import json, os, re, sys, time, urllib.request, urllib.error, urllib.parse

B = os.environ.get('GATO_SERVER', 'https://gato-license.gigan.workers.dev')
OUT = '/tmp/relay'

def _key():
    k = os.environ.get('GATO_ADMIN_KEY', '')
    if k:
        return k
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'server', '.secrets.txt')
    for line in open(p, encoding='utf-8', errors='replace'):
        m = re.match(r'\s*ADMIN_KEY\s*[:=]\s*(\S+)', line)
        if m:
            return m.group(1)
    sys.exit('no admin key')

def req(path, body=None, raw=False, timeout=60):
    r = urllib.request.Request(B + path, data=json.dumps(body).encode() if body is not None else None,
                               headers={'Authorization': 'Bearer ' + _key(), 'Content-Type': 'application/json', 'User-Agent': 'gato-owner'})
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        d = resp.read()
        return (d, resp.headers) if raw else json.loads(d.decode())

def agents():
    rows = req('/admin/agents')['rows']
    for a in rows:
        s = a['status']
        print(f"{a['pc']:<22} v{a['ver']:<7} {a['age']:>5}s ago  running={s.get('running')} battles={s.get('battles')} scene={s.get('scene')} mob={s.get('monster')} auth={s.get('auth')} stop='{s.get('stop_reason','')}'")
    return rows

def job(pc, cmd, arg='', wait=240):
    r = req('/admin/job', {'pc': pc, 'cmd': cmd, 'arg': arg})
    if not r.get('ok'):
        sys.exit(f'job refused: {r}')
    jid = r['job']
    t0 = time.time()
    while time.time() - t0 < wait:
        j = req('/admin/job?id=' + jid)['job']
        if j['state'] in ('done', 'error'):
            return j
        time.sleep(3)
    sys.exit(f'timeout: PC did not answer within {wait}s (job {jid}). It polls every 30 s while the app is open.')

def watch(pc, every=20.0, rounds=None):
    """Live-tail a PC's gato_debug.log by re-issuing a `log` job, printing only new lines.

    Each poll pulls a 400 KB tail and diffs it against what has already been printed, so a round
    shows up in the terminal a few seconds after the PC writes it. Ctrl-C to stop.
    """
    seen = []
    n = 0
    print(f'watching {pc} every {every:.0f}s (Ctrl-C to stop)')
    try:
        while rounds is None or n < rounds:
            n += 1
            try:
                j = job(pc, 'log', '400000', wait=90)
                if j['state'] == 'error':
                    print(f'[{time.strftime("%H:%M:%S")}] job error: {j["result"][:200]}')
                else:
                    p, _ = get(j['id'], f'{pc}_watch_{j["id"]}.log')
                    lines = open(p, encoding='utf-8', errors='replace').read().splitlines()
                    # Re-anchor on the previous tail's last lines so a re-fetch overlaps, then print
                    # only what is genuinely after it.
                    if seen:
                        k = 0
                        for i in range(len(lines)):
                            if lines[i:i + len(seen)] == seen:
                                k = i + len(seen)
                                break
                        new = lines[k:]
                    else:
                        new = lines
                    for ln in new:
                        print(f'[{time.strftime("%H:%M:%S")}] {ln}')
                    if lines:
                        seen = lines[-40:]
            except Exception as e:
                print(f'[{time.strftime("%H:%M:%S")}] {type(e).__name__}: {e}')
            time.sleep(every)
    except KeyboardInterrupt:
        print('stopped')


def get(jid, name=None):
    d, h = req('/admin/blob?job=' + jid, raw=True, timeout=300)
    os.makedirs(OUT, exist_ok=True)
    nm = name or urllib.parse.unquote(h.get('x-name') or jid)
    p = os.path.join(OUT, nm)
    open(p, 'wb').write(d)
    return p, len(d)

def main(a):
    if not a or a[0] in ('-h', '--help'):
        print(__doc__); return
    c = a[0]
    if c == 'agents': agents()
    elif c == 'jobs':
        for j in req('/admin/jobs')['rows']:
            print(time.strftime('%m-%d %H:%M', time.localtime(j['created'])), j['id'], j['cmd'], j['state'], j['bytes'], j['name'], (j['arg'] or '')[:60])
    elif c == 'get': print('%s (%d bytes)' % get(a[1]))
    elif c == 'log':
        j = job(a[1], 'log', a[2] if len(a) > 2 else '400000')
        print(j['state'], j['result'][:200]) if j['state'] == 'error' else print('%s (%d bytes)' % get(j['id'], f'{a[1]}_log.txt'))
    elif c == 'shot':
        j = job(a[1], 'shot')
        print(j['state'], j['result'][:200]) if j['state'] == 'error' else print('%s (%d bytes)' % get(j['id'], f'{a[1]}_shot.jpg'))
    elif c == 'ls':
        j = job(a[1], 'ls', a[2] if len(a) > 2 else 'debug'); print(j['result'])
    elif c == 'pull':
        j = job(a[1], 'pull', '|'.join(a[2:]), wait=900)
        print(j['state'], j['result'][:200]) if j['state'] == 'error' else print('%s (%d bytes)' % get(j['id']))
    elif c == 'stop':
        print(job(a[1], 'stop')['result'])
    elif c == 'watch':
        watch(a[1], every=float(a[2]) if len(a) > 2 else 20.0)
    else:
        sys.exit('unknown command')

if __name__ == '__main__':
    main(sys.argv[1:])
