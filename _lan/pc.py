#!/usr/bin/env python3
# Mac-side client for the LAN agent: enqueue a job, wait, print.
import base64
import json
import os
import sys
import time
import urllib.request

BASE = os.environ.get('PCBASE', 'http://127.0.0.1:8791')
TOK = os.environ.get('PCTOK', 'tok')


def post(path, data, ctype='application/json'):
    req = urllib.request.Request(BASE + path, data=data, method='POST',
                                 headers={'Content-Type': ctype})
    return json.loads(urllib.request.urlopen(req, timeout=180).read() or b'{}')


def get(path):
    return json.loads(urllib.request.urlopen(BASE + path, timeout=180).read() or b'{}')


def run(job, timeout=180):
    jid = post('/job?t=' + TOK, json.dumps(job).encode())['id']
    r = get('/result?t=%s&id=%s' % (TOK, jid))
    return r


def ps(script):
    b = base64.b64encode(script.encode('utf-8')).decode()
    r = run({'cmd': 'ps', 'script': b})
    sys.stdout.write(r.get('out') or '')
    if r.get('err'):
        sys.stderr.write('\n[err] ' + r['err'] + '\n')
    return r.get('code', 0)


def main():
    a = sys.argv[1:]
    if not a:
        print('cmds: health ping ver ls ps exec shot up text'); return
    c = a[0]
    if c == 'health':
        print(json.dumps(get('/health?t=' + TOK))); return
    if c == 'ping':
        sys.exit(ps('hostname; whoami; (Get-Date).ToString("s")'))
    if c == 'ver':
        sys.exit(ps('(Get-CimInstance Win32_OperatingSystem).Caption; [Environment]::OSVersion.VersionString; $PSVersionTable.PSVersion.ToString()'))
    if c == 'ls':
        sys.exit(ps('Get-ChildItem -Force -LiteralPath %s | Select-Object Mode,Length,LastWriteTime,Name | Format-Table -AutoSize | Out-String -Width 300' % _q(a[1])))
    if c == 'text':
        sys.exit(ps('Get-Content -LiteralPath %s -TotalCount %s | Out-String' % (_q(a[1]), a[2] if len(a) > 2 else 200)))
    if c == 'ps':
        sys.exit(ps('Get-Process | Sort-Object WS -Desc | Select-Object -First 30 Id,ProcessName,WS | Format-Table -AutoSize | Out-String'))
    if c == 'exec':
        sys.exit(ps(a[1]))
    if c == 'shot':
        r = run({'cmd': 'shot'}, timeout=180)
        print(r.get('out') or r.get('err'))
        return
    if c == 'up':
        r = run({'cmd': 'pull', 'path': a[1]}, timeout=600)
        print(r.get('out') or r.get('err'))
        return
    print('unknown', c)


def _q(p):
    return "'" + p.replace("'", "''") + "'"


if __name__ == '__main__':
    main()
