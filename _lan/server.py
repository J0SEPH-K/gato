#!/usr/bin/env python3
# LAN command queue: the Windows PC dials OUT and long-polls this server, so nothing
# has to be opened on Windows. Token in the query string. Jobs in, results out.
import base64
import json
import os
import queue
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

TOKEN = sys.argv[1] if len(sys.argv) > 1 else 'tok'
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 8791
HERE = os.path.dirname(os.path.abspath(__file__))
DL = os.path.join(HERE, 'downloads')
os.makedirs(DL, exist_ok=True)

JOBS = queue.Queue()
PENDING = {}          # id -> job
RESULTS = {}          # id -> result dict
EVENTS = {}           # id -> threading.Event
LOCK = threading.Lock()
STATE = {'last_poll': 0.0, 'polls': 0}

AGENT_PS = r'''$ErrorActionPreference = 'Continue'
$f = "$env:TEMP\gato_agent.ps1"
$src = @'
__LOOP__
'@
[IO.File]::WriteAllText($f, $src, (New-Object Text.UTF8Encoding $false))
Start-Process powershell -WindowStyle Hidden -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File',$f
"agent started detached -> $f"
'''

AGENT_LOOP = r'''$ErrorActionPreference = 'Continue'
$Mac = '__MAC__'
$T = '__TOKEN__'
[Console]::OutputEncoding = [Text.Encoding]::UTF8
Add-Type -AssemblyName System.Windows.Forms, System.Drawing
$H = @{ 'ngrok-skip-browser-warning' = '1' }
while ($true) {
  try { $j = Invoke-RestMethod -Headers $H -Uri "$Mac/poll?t=$T" -TimeoutSec 20 } catch { Start-Sleep -Milliseconds 800; continue }
  if ($null -eq $j -or $null -eq $j.id -or $j.id -eq 0) { continue }
  $id = $j.id
  $r = @{ id = $id; code = 0; out = ''; err = '' }
  try {
    if ($j.cmd -eq 'ps') {
      $s = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($j.script))
      $f = "$env:TEMP\j_$id.ps1"
      [IO.File]::WriteAllText($f, $s, (New-Object Text.UTF8Encoding $false))
      $o = & powershell -NoProfile -ExecutionPolicy Bypass -File $f 2>&1 | Out-String
      $r.out = $o
    } elseif ($j.cmd -eq 'shot') {
      $vs = [System.Windows.Forms.SystemInformation]::VirtualScreen
      $bmp = New-Object Drawing.Bitmap $vs.Width, $vs.Height
      $g = [Drawing.Graphics]::FromImage($bmp)
      $g.CopyFromScreen($vs.Left, $vs.Top, 0, 0, $bmp.Size)
      $p = "$env:TEMP\s_$id.png"
      $bmp.Save($p, [Drawing.Imaging.ImageFormat]::Png)
      $g.Dispose(); $bmp.Dispose()
      $bytes = [IO.File]::ReadAllBytes($p)
      Invoke-RestMethod -Headers $H -Uri "$Mac/file?t=$T&name=shot_$id.png" -Method Post -Body $bytes -ContentType 'application/octet-stream' -TimeoutSec 120 | Out-Null
      $r.out = "shot_$id.png"
    } elseif ($j.cmd -eq 'pull') {
      $bytes = [IO.File]::ReadAllBytes($j.path)
      $name = [IO.Path]::GetFileName($j.path)
      $chunk = 3MB
      for ($i = 0; $i -lt $bytes.Length; $i += $chunk) {
        $n = [Math]::Min($chunk, $bytes.Length - $i)
        $part = New-Object byte[] $n
        [Array]::Copy($bytes, $i, $part, 0, $n)
        Invoke-RestMethod -Headers $H -Uri "$Mac/file?t=$T&name=$name&part=$($i/$chunk)" -Method Post -Body $part -ContentType 'application/octet-stream' -TimeoutSec 120 | Out-Null
      }
      $r.out = "$name|$($bytes.Length)|$([Math]::Ceiling($bytes.Length/$chunk))"
    }
  } catch { $r.code = 1; $r.err = "$($_.Exception.Message)" }
  try { Invoke-RestMethod -Headers $H -Uri "$Mac/result?t=$T" -Method Post -Body ($r | ConvertTo-Json -Compress) -ContentType 'application/json' -TimeoutSec 60 | Out-Null } catch { }
}
'''


class H(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, *a):
        pass

    def _ok(self, obj, ctype='application/json'):
        body = obj if isinstance(obj, bytes) else json.dumps(obj).encode()
        self.send_response(200)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _auth(self, q):
        if q.get('t', [''])[0] != TOKEN:
            self._ok({'error': 'bad token'})
            return False
        return True

    def _body(self):
        n = int(self.headers.get('Content-Length') or 0)
        return self.rfile.read(n) if n else b''

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if not self._auth(q):
            return
        if u.path == '/health':
            with LOCK:
                self._ok({'ok': True, 'queued': JOBS.qsize(), 'polls': STATE['polls'],
                          'age': round(time.time() - STATE['last_poll'], 1)})
        elif u.path == '/poll':
            with LOCK:
                STATE['last_poll'] = time.time()
                STATE['polls'] += 1
            try:
                job = JOBS.get(timeout=8)
            except queue.Empty:
                self._ok({'id': 0})
                return
            self._ok(job)
        elif u.path == '/result':
            jid = q.get('id', [''])[0]
            ev = EVENTS.get(jid)
            if ev and ev.wait(120):
                self._ok(RESULTS.pop(jid, {'code': 1, 'out': '', 'err': 'gone'}))
            else:
                self._ok({'code': 1, 'out': '', 'err': 'timeout'})
        elif u.path == '/get':
            name = ''.join(c for c in q.get('name', [''])[0] if c.isalnum() or c in '._-')
            fp = os.path.join(HERE, 'blobs', name)
            if not os.path.exists(fp):
                self._ok({'error': 'missing'})
                return
            data = open(fp, 'rb').read()
            self.send_response(200)
            self.send_header('Content-Type', 'application/octet-stream')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        elif u.path == '/loop':
            host = self.headers.get('Host') or '127.0.0.1:%d' % PORT
            scheme = 'http' if host.startswith(('127.0.0.1', 'localhost')) else 'https'
            mac = scheme + '://' + host
            src = AGENT_LOOP.replace('__MAC__', mac).replace('__TOKEN__', TOKEN)
            self._ok(src.encode(), 'text/plain; charset=utf-8')
        elif u.path == '/agent':
            host = self.headers.get('Host') or '127.0.0.1:%d' % PORT
            scheme = 'http' if host.startswith(('127.0.0.1', 'localhost')) else 'https'
            mac = scheme + '://' + host
            loop = AGENT_LOOP.replace('__MAC__', mac).replace('__TOKEN__', TOKEN)
            src = AGENT_PS.replace('__LOOP__', loop)
            self._ok(src.encode(), 'text/plain; charset=utf-8')
        else:
            self._ok({'error': 'nope'})

    def do_POST(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if not self._auth(q):
            return
        raw = self._body()
        if u.path == '/job':
            job = json.loads(raw or b'{}')
            job['id'] = str(uuid.uuid4())[:8]
            jid = job['id']
            EVENTS[jid] = threading.Event()
            JOBS.put(job)
            self._ok({'id': jid})
        elif u.path == '/result':
            r = json.loads(raw.decode('utf-8', 'replace') or b'{}')
            jid = str(r.get('id'))
            RESULTS[jid] = r
            ev = EVENTS.get(jid)
            if ev:
                ev.set()
            self._ok({'ok': True})
        elif u.path == '/file':
            name = q.get('name', ['blob'])[0]
            part = q.get('part', [''])[0]
            safe = ''.join(c for c in name if c.isalnum() or c in '._-')
            p = os.path.join(DL, safe)
            with open(p, 'ab' if part else 'wb') as f:
                f.write(raw)
            self._ok({'ok': True, 'path': p, 'size': len(raw)})
        else:
            self._ok({'error': 'nope'})


if __name__ == '__main__':
    print('listening 0.0.0.0:%d token=%s' % (PORT, TOKEN), flush=True)
    ThreadingHTTPServer(('0.0.0.0', PORT), H).serve_forever()
