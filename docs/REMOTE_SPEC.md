# Gato 원격 — remote control plane spec (phone → hub → N PCs)

Status: design, ready for GABRIEL. Author: DEMIURGE, 2026-11-16.
Scope: agent side in `workspace/gato_src/`, hub + phone UI in a new
`diablia/mobile-macro/`. Nothing in `brain.py`, `combat.py`, `net.py`,
`capture.py`, `input.py` changes. `prism.py` gets 3 added lines.

---

## 0. Report

### What it is
A small Cloudflare Worker with one Durable Object ("hub") that every macro PC
dials out to over a WebSocket. The phone opens the same Worker URL and sees a
list of PCs. For each PC it shows online state, bot state, a live thumbnail of
the game window and one full-rate viewer, and it has the existing controls:
start/stop, schedule, monster config, chat, the F/M/I/B/Enter keys, and
left/right click. Each PC keeps running the existing `_run_remote` command
vocabulary unchanged. The new agent module only adds a second transport into it.
Input reaches a chosen game window by briefly borrowing focus. It waits until
the user is idle, then restores the user's window and cursor. If the background
`PostMessage` path is shown to work on this game, it uses that instead.

### Why it's new (and where it isn't)
Searches run on 2026-11-16 (web): `게임 매크로 모바일 원격 제어 여러 PC 동시 화면 보기 프로그램`,
`MeshCentral agent outbound websocket relay NAT remote desktop multiple devices web`,
`Cloudflare Durable Objects free plan limits … hibernation`, `ngrok free plan data transfer limit`.

Closest prior art. The topology and the thumbnail wall are **not new**:
- **리모아PC원격제어** (https://remoapc.com/) gives 5 PCs free, a thumbnail
  wall, an Android app, an outbound-only relay, and WGC capture of fullscreen
  games. It already covers "see 3 PCs from the phone and click on them".
- **MeshCentral** (https://docs.meshcentral.com/design/): agents dial out to the
  server over WebSocket and the server relays them to the browser. Its desktop
  multiplexor already aggregates quality and frame rate across viewers.
- **RemoteMV** (MHsoft) and **RemoteT** do multi-PC game remote control. RemoteMV
  bypasses game security with a driver; we refuse to do that.

Honest call: if Jungjun only needed pixels and clicks, installing RemoaPC and
clicking the pywebview window remotely would cover about 80% of this with no
code. The delta this design delivers, which none of the above does:
1. **Bot-native control.** You can start, stop, or schedule all three bots and
   read their state (`running`, `battle_count`, schedule cycle, last note)
   without streaming video at all. Video is optional, not the control path.
2. **Game-window-only capture.** The hub only ever sees the 거상 client area.
   The rest of the user's desktop never leaves the PC. Remote-desktop tools
   send the whole desktop.
3. **The user's desktop isn't taken over.** Input is gated on user idle, the
   foreground window and cursor are restored afterwards, and calibration checks
   whether `PostMessage` is enough (section 5). Remote desktop tools move the
   real cursor while a session is open.
4. **$0, no installer, no third-party agent** running as admin on the PCs.

The two engineering pieces with some originality are not patent-grade
novelty, and I'm not claiming that:
- **Vision-verified input-path calibration.** The bot's own capture diffs the
  frame before and after a probe keystroke (`M` opens and closes the map) to
  decide per PC whether background `PostMessage` input works or focus must be
  borrowed. Screenshot-verified automation in general is old (Sikuli). What's
  new here is using it to choose the transport per PC at runtime.
- **End-to-end credit flow through a hibernating Durable Object.** A
  self-healing credit watchdog lets a lost credit cost 3 s, not a stall.

### Why it works (what was run)
- **Free-tier fit (fact, from docs, fetched 2026-11-16).** Durable Objects on
  Workers Free: 100,000 requests/day and 13,000 GB-s/day. Incoming WebSocket
  messages bill 20:1. Outgoing messages and protocol pings are free.
  `setWebSocketAutoResponse` replies cost no duration
  (https://developers.cloudflare.com/durable-objects/platform/pricing/).
  Messages routed through a Worker don't count as Worker requests
  (https://developers.cloudflare.com/workers/platform/pricing/).
  Calculation (§4.6): 24 h/day of 1 full + 2 thumbs comes to about 43.4k billed
  requests/day (43% of the cap). Duration worst case, one DO awake 24 h:
  0.125 GB × 86,400 s = 10,800 GB-s (83% of the cap).
- **Why not a tunnel (fact).** ngrok Free has 1 GB/month data out
  (https://ngrok.com/docs/pricing-limits/free-plan-limits). One hour of full
  view uses about 190–600 MB (below), so a tunnel dies in 2–5 hours of
  viewing. Cloudflare doesn't bill Worker egress.
- **Frame sizes (measured).** I used a real 1024×768 거상 base screen
  (gogolap.com guide image `01_기본_화면.webp`, 1024×768 source), resized with
  PIL BOX and encoded as baseline JPEG. PIL and OpenCV use the same IJG quality
  scale, so sizes should be within about 10%, but that's a hypothesis checked in
  M2.

  | size | q | KB/frame |
  |---|---|---|
  | 1024×768 | 70 | 200.1 |
  | 640×480 | 50 | 59.5 |
  | 640×480 | 40 | 51.5 |
  | 480×360 | 35 | 26.7 |
  | 320×240 | 35 | 12.0 |
  | 320×240 | 30 | 10.8 |
- **Code facts verified by reading the source:**
  - `capture.py:19` sets `REF_W, REF_H = (1024, 768)`. The reference frame is
    **1024×768, not 1920×1080** as the brief said, and all click args are in
    that space (`prism.py:233`).
  - `prism.py:286` calls `self.auth.upload_live(jpg)`, but `net.AuthClient`
    has no `upload_live` (only `live_uploader`, `net.py:269`). The
    `except Exception: pass` swallows the `AttributeError`, so **the vendor
    live view uploads nothing today**. That's out of scope: this spec does not
    touch the vendor path. A one-line fix (`self.auth.upload_shot(jpg)`) is
    noted in §10 for Jungjun to decide.
  - `config.save()` settings are pushed to the vendor server
    (`_push_settings`, `prism.py:685`). So **pairing secrets must never go
    into `prism_settings.json`**. They live in a separate `remote.json`.
  - `config._validate` merges `base` before `raw` (`config.py:1784-1787`).
    Dropping secret keys from a phone-sent `common` dict therefore keeps the
    stored values.
  - `_run_remote` already refuses input commands while `brain.running`
    (`prism.py:118`). Remote input is therefore only ever live while the bot is
    stopped, and the focus borrow never competes with the bot's own `Hands`.

### What's unproven (hypotheses + the experiment that settles each)
| # | Hypothesis | Experiment | Cost |
|---|---|---|---|
| H1 | 거상 ignores `PostMessage` keys (scancode `SendInput` in `input.py` suggests DirectInput/raw input) but may accept `PostMessage` mouse | `py -3.11 remote_input.py probe` on one PC (§5.4) | 5 min |
| H2 | `GetLastInputInfo` is also updated by our own injected input, so the "own injection" discount (§5.2) is needed | `remote_input.py selftest` prints idle before/after one injection | 2 min |
| H3 | OpenCV JPEG sizes on live game frames are within ±15% of the PIL proxy above | `remote_link.py bench-frames --seconds 60` on a PC (M2) | 2 min |
| H4 | The DO stays within free duration while one phone views 24 h | Cloudflare dashboard → DO metrics after a 24 h M2 soak | 1 day passive |
| H5 | A 0.12 s settle after `SendInput` is enough for the game to consume the input before focus is restored | selftest frame-diff on a key that opens a window (`I`) with settle 0.05/0.12/0.25 | 5 min |
| H6 | iOS Safari keeps the `SameSite=Strict` HttpOnly cookie for a home-screen web app across launches | Add to Home Screen, kill the app, reopen after 1 day | 1 day passive |
| H7 | `websockets.sync` `send()` is safe across threads | Not relied on: the spec funnels all sends through one sender thread | 0 |

---

## 1. Topology and rendezvous: Cloudflare Worker + one Durable Object

```
 phone (browser)  ──wss /ws/phone──┐
                                   ▼
                     Worker "gato-hub"  ──► DO "Fleet" (idFromName("fleet"))
                                   ▲          SQLite: pcs, devices, pending, meta, audit
 PC1 RemoteLink ──wss /ws/agent────┤
 PC2 RemoteLink ──wss /ws/agent────┤          (all outbound from PCs; no port forward)
 PC3 RemoteLink ──wss /ws/agent────┘
 PC* also keep: vendor /cmd long-poll (unchanged), Discord BotPoller (unchanged)
```

**Choice: (b) our own relay on a Cloudflare Worker + a single SQLite-backed
Durable Object using the WebSocket Hibernation API.**

Why the other options were killed:
- **(a) Vendor `/cmd` + `/shot`, killed.** We can't change the server or see its
  phone protocol. `/shot` keeps only the latest frame per auth_id over HTTP
  POST base64 (about 33% overhead and one request per frame). There's no
  multi-PC view, and our screens and commands would pass through a third party.
  Keep it untouched as a fallback channel.
- **(c) Tailscale mesh, killed.** It needs a system install on 3 PCs plus the
  phone, and holds the phone's single VPN slot on iOS. The page would have to
  talk to 3 `http://100.x` origins: mixed content from an https page, plus CORS
  on 3 listeners. Each PC would have to open a listening port. It does solve NAT
  and bandwidth, but it fails "no installer" and adds an inbound surface on
  every PC.
- **Fly/Railway/Render, killed.** Railway and Fly have no free tier for new
  accounts, and Render free sleeps after 15 min idle and kills WebSockets.
- **ngrok to the Mac cockpit, killed.** 1 GB/month of egress (above), and the
  Mac must be on.

Why one DO: all three PCs and the phones share one object, so routing is a map
lookup and not a cross-object RPC. That keeps the request count and duration to
one object (the 83% worst case above). Load is 3 agents plus 1–2 phones, far
below the DO's ~1,000 req/s soft limit.

**PC offline.** The agent socket closes (`webSocketClose`/`webSocketError`), or
its last auto-response timestamp is more than 50 s old. The hub then marks it
`online:false` and pushes `{"t":"pc", ...}` to every phone. Commands to an
offline PC are **rejected immediately** with `err code:"offline"`. They're
never queued, because a click aimed at a stale screen is dangerous. The phone
learns about it within 50 s worst case (half-open TCP), or instantly on a clean
close.

---

## 2. Agent side: `remote_link.py` (new) + 3 lines in `prism.py`

### 2.1 Files
```
workspace/gato_src/
  remote_link.py    # RemoteLink, FrameStreamer, pairing CLI, selftest, bench-frames
  remote_input.py   # RemoteHands(Hands), idle gate, focus borrow/restore, PostMessage path, probe
  remote.json       # generated by pairing; never in prism_settings.json; never copied between PCs
  requirements.txt  # + websockets==15.0.1   (verify the wheel for py3.11 win_amd64; pure-python fallback is fine)
```
`remote_link.py` must import **nothing from `prism`**. It receives the `Api`
instance. It imports `capture`, `input`, `cv2`, `win32*` lazily inside
functions, so `python3 remote_link.py selftest` runs on macOS with a `FakeApi`.

### 2.2 The 3-line `prism.py` edit
At the end of `Api.__init__` (after `self.start_cmd_poller()`, `prism.py:78`):
```python
        import remote_link
        self.remote = remote_link.install(self)   # None when remote.json is absent or invalid
```
In `main()._on_closed` (`prism.py:986`):
```python
        if getattr(api, 'remote', None): api.remote.close()
```
That's all. When `remote.json` is missing, `install()` returns `None`, starts
no thread and patches nothing, so the vendor channel behaves exactly as today.

### 2.3 `install(api) -> RemoteLink | None`
```python
REMOTE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'remote.json')  # not cwd: ensure_admin relaunches

def install(api) -> 'RemoteLink | None':
    try:
        cfg = load_remote_cfg()            # None if missing; raises RemoteCfgError on bad/copied file
        if cfg is None: return None
        import websockets.sync.client      # noqa: F401  (fail fast, clear note)
    except RemoteCfgError as e:
        api.vision.note('input', f'[원격링크] {e}'); return None
    except ImportError:
        api.vision.note('input', '[원격링크] websockets 미설치 — pip install websockets==15.0.1'); return None
    orig = api._run_remote
    lock = threading.RLock()
    def _locked(cmd, arg=''):
        with lock:
            return orig(cmd, arg)
    api._run_remote = _locked              # instance attr shadows the method; the vendor poller now shares the lock
    link = RemoteLink(api, cfg, orig, lock)
    link.start()
    return link
```
Every exception inside `install` is caught, so a broken relay never stops the
bot from starting.

### 2.4 `remote.json`
```json
{
  "v": 1,
  "hub": "https://gato-hub.<account>.workers.dev",
  "pc": "pc_k3x9q2m7ab",
  "name": "PC1-거실",
  "secret": "<base64url, 32 random bytes>",
  "machine": "<HKLM\\SOFTWARE\\Microsoft\\Cryptography\\MachineGuid>",
  "paired_at": "2026-11-16T12:00:00Z",
  "input_mode": {"key": "borrow", "mouse": "borrow"}
}
```
`load_remote_cfg()` checks that `machine` equals the current MachineGuid. If it
doesn't, it renames the file to `remote.json.copied` and raises
`RemoteCfgError('다른 PC에서 복사된 remote.json — 이 PC에서 다시 페어링하세요')`.
This matters because `RUN.md` tells people to copy the whole folder between
PCs, which would otherwise make PC2 impersonate PC1.

### 2.5 `class RemoteLink`
```python
class RemoteLink:
    PING_S = 20            # app-level {"t":"ping"} → DO auto-response (no wake, no duration)
    STATE_FAST_S = 2.0     # while any viewer lease is active
    STATE_SLOW_S = 30.0    # otherwise (and on change)
    CMD_TIMEOUT_S = 15.0
    BACKOFF = (1, 2, 4, 8, 16, 32, 60)   # ±30% jitter, reset after 'welcome'

    def __init__(self, api, cfg: dict, run_remote_orig, lock: threading.RLock): ...
    def start(self) -> None          # starts threads: link, sender, exec, state
    def close(self) -> None          # sets _stop, closes ws, stops streamer
    # internals
    def _link_loop(self) -> None     # connect → challenge/auth → recv loop → reconnect
    def _sender_loop(self) -> None   # sole writer: JSON queue first, then the latest frame slot
    def _exec_loop(self) -> None     # FIFO command worker with watchdog
    def _state_loop(self) -> None
    def _on_msg(self, m: dict) -> None
    def _on_cmd(self, m: dict) -> None
    def _on_rpc(self, m: dict) -> None
    def _send(self, obj: dict) -> None          # enqueue JSON
    def _hub_now(self) -> int                   # local ms + offset learned from 'challenge'/'welcome'/'view'.now
```

Connection: `websockets.sync.client.connect(hub_ws + '/ws/agent?pc=' + pc,
open_timeout=10, ping_interval=20, ping_timeout=20, max_size=2**20,
user_agent_header='gato-remote/1')`. The protocol pings let the agent detect a
dead hub within about 40 s. The hub's liveness check uses the app-level ping
timestamps.

Command dispatch (`_on_cmd`, run on the exec thread):
```python
INPUT_CMDS = {'click_l','click_r','key_f','key_m','key_i','key_b','key_enter'}
PRIORITY   = {'stop','sched_stop','live_stop'}          # bypass the FIFO; run on a short-lived thread
LEASED     = INPUT_CMDS | {'start','sched_start','chat_normal','chat_sangdan','whisper',
                           'gato_login','gato_launch','game_close','key'}   # hub enforces the control lease

def _dispatch(self, cmd, arg, win):
    before = self.api._last_note
    if cmd == 'key':                                    # new, stage 3: wider key pad
        return self._run_key(arg, win)
    if cmd in INPUT_CMDS:
        with self._lock:                                # same RLock the vendor poller uses
            saved = self.api.hands
            self.api.hands = self.rhands
            self.rhands.set_target(win)                 # pid or None (= engine.hwnd / find_window)
            try:     self._orig(cmd, arg)               # verbatim _run_remote: same checks, same notes
            finally: self.api.hands = saved
        res = self.rhands.barrier(timeout=5.0)          # 'ok' | 'user_busy' | 'no_window' | 'fg_fail' | 'blocked'
    else:
        self._orig(cmd, arg)                            # start, stop, shot, chat_*, gato_*, sched_*, settings_reload, game_close
        res = 'ok'
    note = self.api._last_note if self.api._last_note != before else ''
    return res, note
```
- The `'shot'` command keeps its vendor meaning (upload to the vendor server).
  The relay has its own `still` view (§4) and never calls `shot`.
- `live_start`/`live_stop` are passed through verbatim for compatibility but
  are no-ops for the relay.
- `key` (stage 3) takes `arg` from the whitelist `esc enter space tab up down
  left right f1..f12 a..z 0..9`. It is refused while `brain.running`, with the
  same note as `_run_remote`.

Replay and expiry: drop any `cmd`/`rpc` whose `exp < self._hub_now()`, and
send `ack ok:false note:'expired'`. Keep an `OrderedDict` LRU of the last 512
`id`s. A duplicate is dropped silently, which is safe after a reconnect resend.

Watchdog: `_exec_loop` runs each command on a worker thread and joins with
`CMD_TIMEOUT_S`. On timeout it sends `ack ok:false note:'timeout'`, abandons
that (daemon) worker, and spawns a fresh one. Every state message carries
`busy:{cmd, for_s}`. If two commands are hung at once, input/leased commands
are refused with `note:'PC 응답 없음 — 매크로 재시작 필요'`; `stop` still runs
through the priority path.

RPC whitelist (`_on_rpc`). Anything else gets `ok:false err:'denied'`:
```python
RPC = {
  'tick':             lambda a: api.tick(int(a[0]), int(a[1])),
  'status':           lambda a: api.status(),
  'get_config':       lambda a: redact(api.get_config()),
  'set_monster':      lambda a: redact(api.set_monster(str(a[0]))),
  'save_monster_cfg': lambda a: redact(api.save_monster_cfg(str(a[0]), dict(a[1]), a[2] if len(a) > 2 else None)),
  'save_common':      lambda a: redact(api.save_common(strip_secret_keys(dict(a[0])), a[1] if len(a) > 1 else None)),
  'kill_rank':        lambda a: api.kill_rank(),
  'appear_records':   lambda a: api.appear_records(),
  'reset_count':      lambda a: api.reset_count(),
  'portrait':         lambda a: api.portrait(str(a[0])),
  'input_probe':      lambda a: self.rhands.probe(api),          # stage 3, §5.4
  'set_input_mode':   lambda a: self._set_input_mode(dict(a[0])),  # writes remote.json only
}
SECRET_KEYS = {'discord_token','discord_webhook','ntfy_url','auth_id'}
SECRET_RE   = re.compile(r'(token|secret|webhook|pass)', re.I)   # catch-all for future keys
# redact(): replace each matching value v with {'set': bool(v)}; strip_secret_keys(): drop them from incoming dicts
```
Deliberately excluded from remote access: `login`, `logout`, `self_update`,
`toggle_dump`, `test_webhook`, `test_ntfy`, every `win_*`. `start`, `stop` and
schedules go through `cmd` only, so there is one path for each action.

State message (`_state_loop`), built from `api.tick(ev_seq, chat_seq)`
(`prism.py:519`) so nothing is re-implemented:
```json
{"t":"state","seq":812,"ts":1763295000123,
 "s":{"running":false,"battle_count":143,"monster":"주작",
      "schedule":{"active":true,"cycle":2,"cycles":3,"battles":4,"target":10,"resting":false,"rest_left":0},
      "auth":{"ok":true,"label":"인증 · D-12"},
      "window_count":2,"clients":[{"role":"메인","state":"메인화면"},{"role":"서브1","state":"전투"}],
      "last_note":"▶ 패널 시작","gato":false,"admin":true,"locked":false,
      "busy":null,"ver":"<net.CODE_VER>","input_mode":{"key":"borrow","mouse":"borrow"}},
 "ev":[ /* vision.events_since(ev_seq), last 50 max */ ],
 "chat":[ /* api.chat(chat_seq), last 50 max */ ]}
```
`locked` is true when `OpenInputDesktop` fails (session locked or on the secure
desktop). In that case input and capture can't work, and the phone shows
`PC 잠김`. A state message is sent when the content hash changes or the slow
interval passes.

Windows list (sent on change, checked every 2 s via `api._find_windows_cached()`):
```json
{"t":"wins","list":[{"pid":4120,"hwnd":328744,"role":"메인"},{"pid":6612,"hwnd":590112,"role":"서브1"}]}
```

### 2.6 Pairing CLI (same file)
```
py -3.11 remote_link.py pair --hub https://gato-hub.<account>.workers.dev --name "PC1-거실"
py -3.11 remote_link.py set-hub <url>        # same pc/secret, new URL (only valid if the same Worker/DO namespace)
py -3.11 remote_link.py unpair               # deletes remote.json after confirmation
py -3.11 remote_link.py selftest --hub URL   # FakeApi, runs on macOS too
py -3.11 remote_link.py bench-frames --seconds 60   # Windows: real KB/frame, fps, encode ms per mode
```
Uses stdlib `urllib` only; `requests` is not required.

---

## 3. Multi-PC identity and pairing

Identity:
- `pc`: `"pc_" + 10 chars base32` (lowercase, no padding), generated on the
  agent by `secrets.token_bytes`.
- `name`: free text, max 24 chars, editable from the phone.
- `secret`: 32 bytes from `secrets.token_bytes`, generated on the agent and sent
  **once** over TLS at `pair/start`. The hub stores it because it must compute
  HMACs; it is never sent again.

End-to-end flow. The 6-digit code appears **only on the PC console**, never on
the phone. That makes it the out-of-band proof: someone who calls `pair/start`
can create a pending entry but can't approve it.

```
PC console                               Hub (DO)                               Phone (logged in)
──────────                               ────────                               ─────────────────
pair --hub U --name "PC1-거실"
 gen pc, secret, machine
 POST /api/agent/pair/start  ─────────►  pending[pc] = {name, secret, code=6 digits,
   {"pc","name","secret"}                 exp=now+600s}; max 5 pending; 10/h per IP
 ◄─ {"ok":true,"code":"482913","exp_s":600}
 prints:
 [페어링] 휴대폰에서 '설정 → PC 추가'를 누르고
         이 코드를 입력하세요:  482 913
         (이름: PC1-거실, 10분 유효)
 loop every 3 s:
 POST /api/agent/pair/poll  ──────────►  state of pending/pcs
   {"pc","sig":hex(HMAC(secret,"poll|"+pc+"|"+code))}
                                                                    ⚙ → PC 추가 → shows "대기 중: PC1-거실 (3분 전)"
                                                                    user types 482913 → [승인]
                                         ◄──────────── POST /api/pair/approve {"code":"482913","name":"PC1-거실"}
                                         5 wrong codes / 10 min → 10 min lock on approve
                                         pcs[pc] = {name, secret, created, input_mode}
                                         delete pending[pc]; push {"t":"pc",...} to phones
 ◄─ {"state":"approved","name":"PC1-거실"}
 write remote.json (atomic: .tmp + os.replace)
 [페어링] 승인됨 — 매크로를 다시 시작하면 연결됩니다
```
`pair/poll` states: `pending | approved | expired | rejected`. On `expired` the
CLI prints `코드 만료 — 다시 실행하세요` and exits 2.

The QR option was killed: the PC side has no camera, and printing a QR needs a
new dependency. A 6-digit code typed on the phone is the same proof with zero
dependencies.

---

## 4. Screen streaming

### 4.1 Modes (agent `FrameStreamer`)
| mode | size | JPEG q | max fps | change gate (mean absdiff on downscaled frame) | forced resend ("keyframe") | KB/frame (measured proxy) | worst-case rate |
|---|---|---|---|---|---|---|---|
| `thumb` | 320×240 | 30 | 0.5 | ≥ 0.8 | every 10 s | 10.8 | 5.4 KB/s |
| `full` | 640×480 | 45 | 3 | ≥ 0.4 (`LIVE_MIN_DIFF`) | every 5 s (`LIVE_KEYFRAME_SEC`) | ~55 (between q40 = 51.5 and q50 = 59.5) | 165 KB/s ≈ 1.3 Mbps ≈ 590 MB/h |
| `full` + `q:"save"` | 480×360 | 35 | 2 | ≥ 0.6 | every 5 s | 26.7 | 53 KB/s ≈ 0.43 Mbps ≈ 190 MB/h |
| `still` (one-shot) | 1024×768 | 70 | 1 frame | n/a | n/a | 200.1 | one-off |

A "keyframe" here means a forced resend of an unchanged frame. MJPEG has no
inter frames, so this is purely for recovering from a lost frame or a newly
joined viewer. The agent also sends one frame **immediately** on every mode
change. The rates in the table assume every frame changes. 거상 has animated
water and sprites, so assume it mostly does until `bench-frames` (H3) says
otherwise.

Default on the phone: `q:"save"` when `navigator.connection?.saveData` is set
or `navigator.connection?.type === 'cellular'`, otherwise `auto`. A `데이터 절약`
toggle overrides it. iOS has no `navigator.connection`, so the default there is
`save`, and the user can turn it off.

### 4.2 Capture path (reuses `_live_loop`'s path, not its uploader)
```python
def _grab(self, pid):
    api = self.api
    if pid is None or pid == self._main_pid():
        if api.engine.running:                    # bot already capturing at 10 fps: no second WGC grab
            img = api.engine.snapshot()           # VERIFY returns the 1024×768-normalised BGR; else fall through
            if img is not None: return img
        return api.brain._grab_main()             # identical to _live_loop / 'shot'
    hwnd = self._hwnd_for_pid(pid)                # from find_windows(); None if gone
    return capture.grab_hwnd(hwnd, normalize=True) if hwnd else None
```
After that it does the same as `_live_loop`: `cv2.resize(INTER_AREA)`, then the
`absdiff().mean()` gate, then `cv2.imencode('.jpg', IMWRITE_JPEG_QUALITY)`, then
a size-1 latest slot, which `_sender_loop` drains. Five consecutive capture
failures stop the streamer and set `note` to `_capture_fail_reason()`, the same
text the vendor path uses.

### 4.3 Binary frame format
Agent → hub, little-endian, 20-byte header followed by the JPEG bytes:
```python
HDR = struct.Struct('<2sBBIIQ')   # magic b'GF', ver=1, kind(0 thumb,1 full,2 still), seq u32, win_pid u32 (0 = main), cap_ms u64 (agent clock; informational only)
```
Hub → phone: `[u8 pc_len][pc ascii][u64 hub_rx_ms LE]` followed by the agent
payload unchanged. The phone computes age as
`phone_now + phone_offset − hub_rx_ms`. It never uses agent clocks.

### 4.4 Leases (view) and renewals
- Phone → hub every 8 s, on any change, and when the page becomes visible:
  `{"t":"view","leases":{"pc_a":"full","pc_b":"thumb","pc_c":"thumb"},"q":"auto","win":{"pc_a":4120}}`.
- On `visibilitychange → hidden` the phone sends `{"t":"view","leases":{}}`
  immediately, so a backgrounded tab costs no data.
- The hub keeps `views[dev] = {leases, q, win, at}` in memory. Per PC it takes
  `mode = max(off < thumb < full)` over devices with `now − at < 20 s`. `q` is
  `"save"` if any full viewer asked for save, `win` comes from the
  most-recently-updated full viewer.
- Hub → agent: `{"t":"view","mode":"full","q":"auto","win":4120,"lease_s":20,"now":<hub ms>}`.
  It's sent whenever the aggregate changes and as a renewal whenever any phone
  renews, at most once per 4 s per PC.
- The agent drops to `off` when `lease_s` passes with no renewal, and stops the
  streamer thread, so CPU use is zero.
- `still`: phone → hub `{"t":"still","pc":"pc_a"}` → agent
  `{"t":"still","win":pid}`, which sends one kind-2 frame. It doesn't use credit
  and is rate-limited to 1 per 3 s per PC by the agent.

### 4.5 Backpressure: end-to-end credits with a self-healing watchdog
- **Agent.** `credits = 2` for full, `1` for thumb. They reset on every `view`
  that changes the mode. Each frame sent uses one credit. At zero the agent
  **doesn't encode** (no CPU). When the hub sends
  `{"t":"credit","seq":n}`, the agent adds one credit, up to the cap. If no
  credit has arrived for 3 s, the agent refills to the cap. That covers a credit
  lost in hub hibernation or a phone that dropped.
- **Hub, per phone and per PC.** `credit[dev][pc]` starts at 2. On a frame from
  a PC, for each phone leasing that PC: if it has credit, send the frame and
  decrement. Otherwise store the frame in `pending[dev][pc]`, overwriting what's
  there (latest-only, so older frames are dropped). On a phone message
  `{"t":"credit","pc":"pc_a","seq":n}`, increment the phone's credit, flush the
  pending frame, and forward `credit` to the agent if `n > lastCredited[pc]`, so
  the first viewer's ack drives the agent.
- **Phone.** It sends `credit` in the `<img>`'s `onload`, after decode. Back
  pressure is therefore measured at the screen, not at the socket.
- **Adaptive quality** (agent, `q:"auto"` only). RTT is the time from frame
  send to the credit for that `seq`, measured on the agent clock only, so clock
  skew doesn't matter. If the median of the last 5 RTTs is over 1,200 ms, step
  down to the `save` parameters. Step back up after 15 s of median RTT under
  400 ms.
- The hub caches the last frame per PC and kind in memory. A phone that starts
  leasing gets it immediately. That cache is lost on hibernation, but the agent
  sends a fresh frame on every mode change, so nothing breaks.

### 4.6 Free-tier budget (calculation from the numbers above)
Viewing 1 full + 2 thumbs, incoming messages/s: agent frames 3 + thumbs 1 +
phone credits 4 + agent state 1.5 + phone view renewals 0.125 + agent pings 0.15
≈ **9.8 msg/s**. That bills as 0.49 req/s, which is 1,764 req per viewing hour.
Idle (no viewer): about 0.25 msg/s, or roughly 1,080 req/day.
**24 h of viewing comes to about 43.4k billed requests/day** against the
100k cap.

Guard: the hub counts incoming messages per UTC day and persists the count every
60 s (1,440 row writes/day). At 80% of 2,000,000 incoming messages (≈ 80k billed
requests) it forces every lease to `thumb`. It pushes
`{"t":"budget","pct":80}` and the phone shows `오늘 무료 한도 80% — 썸네일만`.
At 95% it forces `off`, and commands still work.

---

## 5. Input routing: `remote_input.py`

### 5.1 `class RemoteHands(Hands)`
It's a separate instance with its own worker thread. The bot's `Hands` is never
touched (Brain holds its own reference, `prism.py:59`).
```python
class RemoteHands(Hands):
    IDLE_GATE_MS = 1500     # user must be idle this long
    IDLE_WAIT_S  = 3.0      # wait up to this long for idle, else 'user_busy'
    SETTLE_S     = 0.12     # H5: let the game consume input before restoring
    def __init__(self, api, log, mode: dict): ...
    def set_target(self, pid: int | None) -> None      # captured at enqueue time
    def barrier(self, timeout: float) -> str           # _do(lambda: self._last, wait=True)
    def click(self, x, y, button='left', down_ms=0.05, wait=False)   # override: 'post' → _post_click, else super()
    def press(self, key, hold=0.05, wait=False)                     # override: 'post' → _post_key,  else super()
    def _do(self, fn, wait)                            # override: wrap fn in _borrowed(fn, pid) when mode is borrow
    def _hwnd(self) -> int                             # override: hwnd for self._cur_pid among find_windows(), else engine.hwnd/find_window()
    def probe(self, api) -> dict                       # §5.4
```
Only `click` and `press` are overridden, because those are the only `Hands`
calls `_run_remote` makes (`prism.py:199, 240`). The command args keep their
format: `click_l|click_r` take `"x,y"` in 1024×768 reference space, and
`key_*` take no arg. Targeting a window is an **envelope field** `win` (a pid),
never inside `arg`. With no `win`, the target is the same window as today.

### 5.2 Focus borrow (SendInput path, default)
```python
def _borrowed(self, fn, pid):
    self._cur_pid = pid
    if not self._wait_idle():                       # GetLastInputInfo; discounts our own injections (H2)
        self._last = 'user_busy'; self._log('[원격] 사용자 입력 중 — 원격 입력 보류'); return False
    prev_fg  = win32gui.GetForegroundWindow()
    prev_pos = win32api.GetCursorPos()
    game = self._hwnd()
    try:
        ok = fn()                                   # unchanged Hands body: _foreground() → SendInput (scancodes)
        self._inj_tick = kernel32.GetTickCount()
        time.sleep(self.SETTLE_S)
        self._last = 'ok' if ok else ('no_window' if not game else 'fg_fail')
        return ok
    finally:
        if prev_fg and prev_fg != game and win32gui.IsWindow(prev_fg) and not _is_game(prev_fg):
            _fg_to(prev_fg)                         # same AttachThreadInput/SetForegroundWindow dance as Hands._foreground
        win32api.SetCursorPos(prev_pos)

def _wait_idle(self) -> bool:
    end = time.monotonic() + self.IDLE_WAIT_S
    while True:
        li = _last_input_tick(); now = kernel32.GetTickCount()
        ours = self._inj_tick and (li - self._inj_tick) & 0xFFFFFFFF <= 50   # last input == our own injection
        if ours or ((now - li) & 0xFFFFFFFF) >= self.IDLE_GATE_MS: return True
        if time.monotonic() >= end: return False
        time.sleep(0.1)
```
Each command borrows focus for about 0.5 s (`Hands._foreground` sleeps 0.15 s
plus `FG_SETTLE` 0.3 s, then `SETTLE_S` 0.12 s). The cursor goes back to the
exact pixel it came from. `BlockInput` is deliberately not used: it would freeze
the user's keyboard. The idle gate makes a collision require the user to start
typing within the 0.5 s window, and if that happens the stray keys land in the
game window, never in the user's document.

### 5.3 Background path (`PostMessage`, opt-in per channel after a successful probe)
```python
def _post_click(self, x, y, button, down_ms):
    hwnd = self._hwnd();  cw, ch = client size;  cx, cy = round(x*cw/REF_W), round(y*ch/REF_H)
    lp = (cy << 16) | (cx & 0xFFFF)
    PostMessage(hwnd, WM_MOUSEMOVE, 0, lp)
    PostMessage(hwnd, WM_LBUTTONDOWN|WM_RBUTTONDOWN, MK_LBUTTON|MK_RBUTTON, lp); sleep(down_ms)
    PostMessage(hwnd, WM_LBUTTONUP|WM_RBUTTONUP, 0, lp)
def _post_key(self, name):
    vk = VK[name]; sc = MapVirtualKeyW(vk, 0); ext = name in _EXT_KEYS
    lp = 1 | (sc << 16) | (ext << 24)
    PostMessage(hwnd, WM_KEYDOWN, vk, lp); sleep(0.05); PostMessage(hwnd, WM_KEYUP, vk, lp | (1 << 30) | (1 << 31))
```
There's no focus change and no cursor movement. It's used only for channels
where `input_mode[channel] == "post"`.

### 5.4 Calibration probe (`rpc input_probe`, or `py -3.11 remote_input.py probe`)
Preconditions: the bot is stopped and the scene is `main` (`vision_detect_scene`),
otherwise it returns `{"ok":false,"why":"봇 정지 + 메인화면에서만"}`.
1. A = grab; `_post_key('m')`; wait 0.6 s; B = grab; `_post_key('m')`; wait
   0.6 s; C = grab.
2. `d_open = absdiff(A,B).mean()`, `d_close = absdiff(A,C).mean()`. The key
   path counts as working if `d_open ≥ 6.0` and `d_close ≤ 2.0`.
   **Thresholds are hypotheses**: log the raw numbers and tune them on the
   first run.
3. If the post path failed, repeat with the borrow path to prove the scene can
   change at all. If both fail, the probe is invalid (`why:"화면 변화 없음"`).
4. Mouse: no automatic probe, because there's no safe known coordinate. The
   phone offers `테스트 클릭`: post a left click at a coordinate the user taps,
   then show before/after frames side by side, and the user confirms.

Result:
`{"ok":true,"key":{"post":false,"borrow":true,"d_open":0.3,"d_close":0.2},"mouse":null}`.
The phone then offers to set the mode, which calls `set_input_mode`, which
writes `remote.json`.

### 5.5 Safety rules enforced in the agent, regardless of what the hub sends
- The target hwnd must come from `find_windows()` (the game process). Input is
  never sent to any other window.
- `0 ≤ x < 1024` and `0 ≤ y < 768`, already checked by `_run_click`.
- Refused while `brain.running` (existing rule).
- Chat (`chat_*`, `whisper`) runs through `brain.type_chat` with the bot's own
  `Hands`. It steals focus without restoring it, the same as Discord chat today.
  That's a known limitation and isn't changed here.

---

## 6. Auth and safety

| Link | Mechanism |
|---|---|
| Phone → hub login | `POST /api/login {"pass","device_name"}`. Compare `SHA-256(pass)` to `SHA-256(env.OWNER_PASS)` with `crypto.subtle.timingSafeEqual`. `OWNER_PASS` is set by `wrangler secret put OWNER_PASS` (≥ 12 chars). Throttle: 5 failures per IP per 15 min, then a 15-min lock for that IP; 30 failures per hour globally, then a 1 h global lock. |
| Phone session | Device token: 32 random bytes, base64url. The hub stores `sha256(token)` in `devices`. Cookie `gm_dev=<token>; HttpOnly; Secure; SameSite=Strict; Path=/; Max-Age=7776000`, refreshed when older than 30 days. |
| Phone WebSocket | `/ws/phone` upgrade requires the cookie and `Origin === new URL(request.url).origin`, otherwise 403. Commands travel inside this authenticated WSS, so replaying them requires the socket. |
| Hub → agent | Challenge–response on every connect: hub `{"t":"challenge","n":<16B b64>,"now":ms}`, agent `{"t":"auth","pc","sig":hex(HMAC-SHA256(secret,"agent|"+pc+"|"+n))}`. The nonce is single-use, so a captured auth can't be replayed. No auth within 10 s, or a bad sig, closes with 4001. An unknown or forgotten pc closes with 4003, and the agent then stops retrying and notes `이 PC는 허브에서 삭제됨 — 다시 페어링`. |
| Command freshness | The hub stamps `exp = now + 10 s`. The agent drops anything past `exp` using the hub-clock offset, and dedups on an LRU of 512 ids. |
| Vendor login | Untouched. RemoteLink never reads or sends `auth_id`/`token`, never calls `login`/`logout`, and doesn't relay `/auth`. `Api.start()` still requires `auth.ok` (`prism.py:371`). The hub has its own identity, so there's no double authentication: two independent systems, and a PC can be relay-online while vendor-unauthed (the phone shows `auth.label`). |
| Audit | The DO appends `{ts, dev, pc, cmd}` for every leased command and keeps the last 500. **No args are stored** (chat text, OTP). Visible in `설정 → 기록`. |

What a **compromised phone or stolen device token can** do: everything the UI
does. That includes start/stop, editing monster config, typing in-game chat as
the user, and clicking inside the game window while the bot is stopped. Clicks
in 거상 can move items or trade, so **in-game asset damage is possible**. This
is the real risk; revoke fast.

What it **cannot** do:
- read or change the Discord token/webhook, the ntfy URL, or the vendor auth_id
  (redacted and stripped)
- call vendor login/logout or self-update
- send input to any non-game window
- run code, touch files, or read `remote.json`
- learn PC secrets
- pair a PC without the code shown on that PC's console

Revocation:
- `설정 → 기기 → 해제` revokes one device.
- `POST /api/devices/revoke_all {"pass"}` works from any browser with the
  passphrase.
- If the passphrase leaks: `wrangler secret put OWNER_PASS`, then `revoke_all`.
- If a PC secret leaks: `설정 → PC → 삭제`, then re-pair that PC.

---

## 7. Hub API (Worker + DO)

### 7.1 Files
```
mobile-macro/
  hub/
    wrangler.toml
    package.json            # devDependencies: wrangler only
    src/worker.js           # routing; forwards /api/* and /ws/* to the DO; assets otherwise
    src/fleet.js            # export class Fleet (DurableObject): storage, sockets, routing, leases, credits
    test/e2e.mjs            # node 22: drives wrangler dev with a fake agent + fake phone
  web/
    index.html  app.js  app.css   # served by Workers static assets
  README.md                 # deploy: npx wrangler login; npx wrangler secret put OWNER_PASS; npx wrangler deploy
```
`mobile-macro/` sits outside `cockpit/` on purpose. The cockpit is the DIABLIA
TUI shell, a different product. Copy the visual tokens and the key-pad markup
from `cockpit/mobile/mobile.css` and `app_index.html`. The textual-bundle
capture code doesn't apply here and isn't copied.

`wrangler.toml`:
```toml
name = "gato-hub"
main = "src/worker.js"
compatibility_date = "2026-11-01"
[assets]
directory = "../web"
binding = "ASSETS"
[[durable_objects.bindings]]
name = "FLEET"
class_name = "Fleet"
[[migrations]]
tag = "v1"
new_sqlite_classes = ["Fleet"]
```

### 7.2 HTTP
| Method & path | Auth | Body → Response |
|---|---|---|
| `POST /api/login` | none (throttled) | `{"pass","device_name"}` → `200 {"ok":true,"device":{"id":"d_x","name"}}` + cookie; `401 {"ok":false,"err":"bad_pass","wait_s":0}`; `429 {"ok":false,"err":"locked","wait_s":840}` |
| `POST /api/logout` | cookie | → `{"ok":true}`, revokes this device |
| `GET /api/session` | cookie | → `{"ok":true,"device":{...}}` or `401` |
| `GET /api/devices` | cookie | → `{"devices":[{"id","name","created","last_seen","me":bool}]}` |
| `POST /api/devices/revoke` | cookie | `{"id"}` → `{"ok":true}` |
| `POST /api/devices/revoke_all` | **pass** | `{"pass"}` → `{"ok":true,"revoked":n}` |
| `POST /api/pair/approve` | cookie | `{"code","name"?}` → `{"ok":true,"pc":PcRow}` / `{"ok":false,"err":"bad_code"|"locked"}` |
| `GET /api/pair/pending` | cookie | → `{"pending":[{"name","age_s"}]}` (no codes) |
| `POST /api/pcs/:pc/rename` | cookie | `{"name"}` → `{"ok":true}` |
| `POST /api/pcs/:pc/forget` | cookie | → `{"ok":true}`; closes the agent socket with 4003 |
| `GET /api/audit` | cookie | → `{"items":[{"ts","dev","pc","cmd"}]}` |
| `POST /api/agent/pair/start` | none (10/h/IP, ≤5 pending) | `{"pc","name","secret"}` → `{"ok":true,"code","exp_s":600}` |
| `POST /api/agent/pair/poll` | HMAC | `{"pc","sig"}` → `{"state":"pending"|"approved"|"expired"|"rejected","name"?}` |
| `GET /ws/agent?pc=` | challenge–response | WebSocket |
| `GET /ws/phone` | cookie + Origin | WebSocket |

### 7.3 DO storage (SQLite via `ctx.storage.sql`)
```sql
CREATE TABLE IF NOT EXISTS pcs     (pc TEXT PRIMARY KEY, name TEXT, secret TEXT, created INT, last_seen INT, input_mode TEXT);
CREATE TABLE IF NOT EXISTS devices (id TEXT PRIMARY KEY, name TEXT, token_hash TEXT UNIQUE, created INT, last_seen INT);
CREATE TABLE IF NOT EXISTS pending (pc TEXT PRIMARY KEY, name TEXT, secret TEXT, code TEXT, exp INT, ip TEXT);
CREATE TABLE IF NOT EXISTS meta    (k TEXT PRIMARY KEY, v TEXT);     -- msg_day, msg_count, ctl:<pc>, throttle state
CREATE TABLE IF NOT EXISTS audit   (ts INT, dev TEXT, pc TEXT, cmd TEXT);
```
`last_seen` is written at most once per 5 min per PC, to protect the
100k rows/day write budget.

### 7.4 WebSocket wiring (Hibernation API)
- `ctx.acceptWebSocket(server, ['agent:'+pc])` or `['phone:'+dev]`, plus
  `ws.serializeAttachment({role, pc|dev, authed, since})`.
- In the constructor:
  `ctx.setWebSocketAutoResponse(new WebSocketRequestResponsePair('{"t":"ping"}','{"t":"pong"}'))`.
  Agent online means a socket exists and
  `now − (ctx.getWebSocketAutoResponseTimestamp(ws) ?? since) < 50 s`.
- An alarm every 10 s **only while any phone socket exists**. It recomputes
  online flags and pushes `pc` diffs. With no phone attached, no alarm runs and
  the DO hibernates.
- If a new agent socket arrives for a pc that already has one, the old one is
  closed with 4009 `replaced`. If that happens 3 times in 10 min, the hub sets
  `dup:true` on the PcRow, the phone shows `같은 PC ID가 두 곳에서 접속 중`, and
  the agent backs off to 60 s on 4009.

### 7.5 Message shapes
Phone → hub:
```json
{"t":"hello","v":1}
{"t":"view","leases":{"pc_a":"full","pc_b":"thumb"},"q":"auto","win":{"pc_a":4120}}
{"t":"credit","pc":"pc_a","seq":1234}
{"t":"still","pc":"pc_a"}
{"t":"cmd","id":"01JD…","pc":"pc_a","cmd":"click_l","arg":"512,384","win":4120}
{"t":"rpc","id":"01JD…","pc":"pc_a","m":"get_config","a":[]}
{"t":"take","pc":"pc_a"}
```
Hub → phone:
```json
{"t":"snapshot","now":1763295000000,"me":{"dev":"d_ab12","name":"아이폰"},"pcs":[PcRow,…],"budget":{"pct":12}}
{"t":"pc", …PcRow}
{"t":"state","pc":"pc_a","rx":1763295000456,"s":{…},"ev":[…],"chat":[…]}
{"t":"wins","pc":"pc_a","list":[…]}
{"t":"ack","pc":"pc_a","id":"01JD…","ok":true,"res":"ok","note":"▶ 패널 시작"}
{"t":"rpc_res","pc":"pc_a","id":"01JD…","ok":true,"result":{…}}
{"t":"err","id":"01JD…","code":"offline"|"busy"|"denied"|"budget","msg":"…","holder":"아이패드"}
{"t":"budget","pct":80}
binary: [u8 len][pc][u64 hub_rx_ms][GF header][jpeg]
```
`PcRow`:
```json
{"pc":"pc_a","name":"PC1-거실","online":true,"since":1763290000000,"last_seen":1763295000000,
 "running":false,"battles":143,"sched":{"active":true,"cycle":2,"cycles":3},
 "frame_rx":1763295000400,"ctl":"d_ab12","dup":false,"input_mode":{"key":"borrow","mouse":"borrow"}}
```
The hub fills `running`, `battles` and `sched` from the latest agent `state`.

Hub → agent: `challenge`, `welcome {"name","now"}`, `view`, `credit`, `still`,
`cmd {"id","cmd","arg","win","exp","by"}`, `rpc {"id","m","a","exp","by"}`.
Agent → hub: `auth`, `ping`, `state`, `wins`, `ack`, `rpc_res`, binary frames.

### 7.6 Control lease (double control)
Leased commands (`LEASED` in §2.5) need `ctl[pc] ∈ {null, dev, expired}`. The
first leased command takes the lease for 60 s, and each command renews it. A
second device gets `err code:"busy" holder:<name>`, and its UI shows
`아이패드에서 제어 중 — [제어 가져오기]`. That button sends `take`, which moves
the lease and pushes `pc` to both phones. `stop`, `sched_stop`, `view`,
`still` and every read RPC are **never leased**: any device can always stop any
PC. The lease is written to `meta` only when it changes hands.

---

## 8. Phone UI (`mobile-macro/web/`)

One page, portrait first, Korean labels. Viewport meta copied from
`cockpit/mobile/app_index.html` (`interactive-widget=resizes-content`,
`viewport-fit=cover`).

```
┌ #bar ─────────────────────────────────────────────────┐
│ Gato 원격            ● 3/3 온라인      [데이터 절약] [⚙] │
├ #strip (3 tiles, horizontal) ─────────────────────────┤
│ [thumb] PC1-거실 ● 가동 · 전투 143 · 2초                │
│ [thumb] PC2-방   ● 정지 · 15초                          │
│ [thumb] PC3      ○ 오프라인 · 마지막 3분 전              │
├ #viewer (4:3, selected PC) ───────────────────────────┤
│  overlay: PC1-거실 · 3fps · 지연 240ms · 메인/서브1 ▾    │
│  tap = 좌클릭, long-press 600 ms = 우클릭 (클릭 모드 ON)  │
│  [선명하게] [전체 보기] [클릭 모드]                      │
├ #ctl ─────────────────────────────────────────────────┤
│ [▶ 시작] [■ 정지] [스케쥴] [설정]                        │
├ #pad ─────────────────────────────────────────────────┤
│ F  M  I  B  ⏎ 엔터   [⌨ 더보기 → ESC SPACE TAB ▲◀▼▶ F1–F12] │
├ #chat ────────────────────────────────────────────────┤
│ [일반|상단|귓말1–9] [입력…                ] [보내기]      │
├ #log (drawer) 이벤트 / 채팅 ───────────────────────────┤
└───────────────────────────────────────────────────────┘
```

Behaviour:
- **Login screen.** It reuses the cockpit `#boot` overlay pattern: mark,
  message, one button. Fields: `암호`, `기기 이름`, then `로그인`.
- **Selecting a PC** (tap a strip tile) sets its lease to `full` and the others
  to `thumb`. `전체 보기` shows a 2×2 grid of the three thumbs and leases all
  three as `thumb`.
- **Click mapping.**
  `x = clamp(floor((e.clientX − r.left) / r.width * 1024), 0, 1023)`, and `y`
  the same way with 768. A ripple is drawn at the tap. While `running`, the
  overlay is greyed with `가동 중 입력 차단`. `클릭 모드` starts OFF so a scroll
  can't click.
- **Frames.** `URL.createObjectURL(new Blob([jpeg],{type:'image/jpeg'}))` into
  the tile's `<img>`. The previous URL is revoked on `onload`, then `credit` is
  sent.
- **Dot colours.** Green: online and state < 10 s old. Amber: online but state
  older (`응답 지연`). Grey: offline. Red ring: `dup` or `locked` (`PC 잠김`).
- **Confirm dialogs** for `game_close` (`게임을 종료할까요?`), `gato_login` (it
  carries an OTP) and `reset_count`.
- **Settings** (`설정`) has tabs:
  - `몬스터`: `get_config` / `set_monster` / `save_monster_cfg`, with stamp
    conflict text passed through verbatim.
  - `공통`: secret fields shown as `설정됨` / `없음`, read-only.
  - `스케쥴`: cycles, battles, rest → `cmd sched_start "c,b,r"`.
  - `PC`: rename, forget, `입력 방식 테스트`.
  - `기기`.
  - `기록` (audit).
  - `PC 추가`: pending list plus a 6-digit code field.

Label table (UI ↔ command):

| Label | Sends |
|---|---|
| ▶ 시작 | `cmd start` |
| ■ 정지 | `cmd stop` |
| 스케쥴 시작 | `cmd sched_start "c,b,r"` |
| 스케쥴 정지 | `cmd sched_stop` |
| F / M / I / B / ⏎ 엔터 | `cmd key_f/key_m/key_i/key_b/key_enter` |
| 더보기 keys | `cmd key "<name>"` (stage 3) |
| 좌클릭 / 우클릭 | `cmd click_l/click_r "x,y"` |
| 일반 / 상단 / 귓말N 보내기 | `cmd chat_normal "<text>"` / `chat_sangdan "<text>"` / `whisper "N|<text>"` |
| 고트 로그인 / 고트 실행 | `cmd gato_login "slot,otp"` / `gato_launch "slot"` |
| 게임 종료 | `cmd game_close` |
| 설정 다시 불러오기 | `cmd settings_reload` |
| 선명하게 | `still` |

Serving: the Worker serves `web/` as static assets at
`https://gato-hub.<account>.workers.dev/`. The URL is stable, so no tunnel, no
`COCKPIT_PUBLIC_URL` and no Mac is needed. For local dev, `npx wrangler dev`
serves it at `http://127.0.0.1:8787`.

---

## 9. Failure modes (one line each)

| Failure | Behaviour |
|---|---|
| Hub down / Cloudflare outage | Bots keep running. Agents reconnect with backoff 1→60 s ±30%. The phone shows `허브 연결 끊김 — 재시도 중`. Vendor `/cmd` and the Discord `BotPoller` still work as out-of-band control. |
| PC offline (crash, reboot, network) | Socket close or 50 s ping silence → `online:false` pushed to phones. Commands are rejected `offline`, never queued. The row shows `마지막 접속 N분 전`. |
| Phone offline / app backgrounded | Leases expire in ≤ 20 s → agents stop encoding. The control lease lapses in 60 s. The bot is unaffected. |
| Tunnel URL change | Doesn't apply: `workers.dev` is stable. If the Worker is renamed, the DO namespace is new, so run `remote_link.py pair` again on each PC (`set-hub` is only for a same-namespace custom domain). |
| Device token leak | `설정 → 기기 → 해제`, or `revoke_all` with the passphrase from any browser. The audit log shows what was sent. |
| Passphrase leak | `wrangler secret put OWNER_PASS` + `revoke_all`. Login throttle limits guessing. |
| PC secret leak / folder copied to another PC | MachineGuid check refuses the copied `remote.json`. For a real leak: `PC 삭제` (4003) → re-pair. |
| Two phones controlling one PC | Control lease. The second phone gets `busy` with the holder's name and an explicit `제어 가져오기`. `stop` is always allowed. |
| Clock skew (agent or phone) | All freshness uses hub time: offsets come from `challenge`/`welcome`/`view.now` and `snapshot.now`. Agent auth is nonce-based, so it never depends on time. |
| PC hangs mid-command | Watchdog acks `timeout` after 15 s, the state shows `busy`, a fresh exec worker takes over, and `stop` uses the priority path. If the whole process wedges, pings stop and the PC goes offline in ≤ 50 s. |
| User typing at the PC when remote input arrives | Idle gate waits up to 3 s, then acks `user_busy` (`사용자 사용 중`). Nothing is injected. |
| Game window gone / minimised | `_run_remote`'s existing notes (`거상 창 없음`), and the streamer shows `_capture_fail_reason()`. |
| Session locked | `locked:true` → phone `PC 잠김`. Input and capture are disabled until unlock. |
| Free-tier budget near cap | 80%: thumbs only. 95%: no video. Commands keep working. Resets at 00:00 UTC (09:00 KST). |
| Same pc id on two machines | 4009 replace loop → `dup:true` on the row, and the agent backs off to 60 s. |
| Relay not configured / websockets missing | `install()` returns `None`, one note in the log, and the vendor path is unchanged. |

---

## 10. Milestones

### M1: Fleet status and start/stop (no video, no input)
Useful alone: see all three bots and start, stop or schedule them from the phone.

Files:
- `workspace/gato_src/remote_link.py`: `install`, `RemoteLink` without
  streamer or input, pairing CLI, `selftest` with `FakeApi`.
- `workspace/gato_src/prism.py`: the 3 lines in §2.2.
- `workspace/gato_src/requirements.txt`: `+websockets==15.0.1`.
- `mobile-macro/hub/{wrangler.toml,package.json,src/worker.js,src/fleet.js,test/e2e.mjs}`:
  login/devices/pair/pcs, agent and phone sockets, `cmd`/`ack`, `state`,
  read-only `rpc`, control lease, audit.
- `mobile-macro/web/{index.html,app.js,app.css}`: login, strip without images,
  `시작`/`정지`/`스케쥴`, log drawer.
- `.gitignore`: add `mobile-macro/hub/.wrangler/` and
  `mobile-macro/hub/node_modules/`.

Verify (macOS):
```bash
cd mobile-macro/hub && npm i && (OWNER_PASS=test-pass-1234 npx wrangler dev --port 8787 &) && sleep 5 && \
node test/e2e.mjs http://127.0.0.1:8787 --agents 3
# e2e: login → 3 fake agents pair (python3 ../../workspace/gato_src/remote_link.py selftest --hub … --fake-pair)
#      → phone sees 3 online → cmd start to pc #2 → ack ok + state.running true → kill agent #3 → pc #3 offline ≤ 50 s
#      → second phone gets err busy → stop from second phone succeeds → exits 0
```
Verify (Windows, one PC): `py -3.11 remote_link.py pair --hub <url> --name PC1`,
then `py -3.11 run_gato.py`. The phone shows PC1 online with the correct
`battle_count`, and `▶ 시작` starts the bot.

### M2: Screens (thumb wall + one full viewer + still)
Files:
- `remote_link.py`: `FrameStreamer`, credits, adaptive quality,
  `bench-frames`.
- `fleet.js`: view aggregation, credit routing, frame cache, budget guard.
- `web/app.js`, `app.css`: viewer, thumbs, grid, `데이터 절약`, age and fps
  overlay.

Verify:
```bash
node test/e2e.mjs http://127.0.0.1:8787 --agents 3 --stream 60
# asserts over 60 s: thumb fps ≤ 0.55 per PC; full fps ≤ 3.1; with phone acks paused,
# agent sends ≤ 2 frames then resumes ≤ 3.5 s later (watchdog); first frame to a new viewer ≤ 1 s; budget counter increments
```
```
py -3.11 remote_link.py bench-frames --seconds 60   # Windows: prints per-mode mean/p95 KB, fps, encode ms → replaces the PIL proxy (H3)
```

### M3: Input, chat and config from the phone
Files:
- `workspace/gato_src/remote_input.py`: `RemoteHands`, idle gate,
  borrow/restore, PostMessage path, `probe`, `selftest`.
- `remote_link.py`: input dispatch with the hands swap, `key` cmd, config RPCs
  with redaction and stripping, `input_probe`/`set_input_mode`.
- `fleet.js`: lease coverage for the new commands.
- `web/`: click overlay, pad, chat bar, settings tabs, probe UI.

Verify (Windows, with the game open and the bot stopped):
```
py -3.11 remote_input.py selftest
# opens Notepad as the "user" window; RemoteHands.press('i') via borrow;
# asserts: game frame diff > 6 (inventory opened), foreground == Notepad within 1.0 s,
# cursor back to the exact original pixel; prints GetLastInputInfo before/after (H2);
# repeats with SETTLE_S 0.05/0.12/0.25 (H5); presses 'i' again to close.
py -3.11 remote_input.py probe       # H1: prints d_open/d_close for post and borrow paths
```
Then from the phone: tap the minimap on PC2's full view, and PC2's game reacts
while the user's browser on PC2 keeps focus.

### Next three build steps (for GABRIEL, in order)
1. `mobile-macro/hub/src/fleet.js` + `worker.js` + `test/e2e.mjs`, with the
   pure-protocol parts of the fake agent in `remote_link.py selftest`. M1 must
   pass on macOS before any Windows work starts.
2. `remote_link.py` real Windows path + the `prism.py` 3 lines. Pair one PC,
   check `▶ 시작`/`■ 정지` from the phone.
3. `FrameStreamer` + `bench-frames`. Run it on a PC and paste the numbers into
   §4.1, replacing the proxy column.

### Open decisions for Jungjun (one line each)
- Fix the vendor live view bug (`prism.py:286`
  `upload_live` → `upload_shot`)? It's outside this spec and changes vendor
  traffic, so it's yours to decide.
- The PCs are paired to `gato-hub.<account>.workers.dev` on the Cloudflare
  account that `workspace/aatrox` already uses with wrangler. Confirm that
  account, or name another.
- Ground rules: automating 거상 likely breaches its terms of service, and this
  code is a decompile of a third-party bot. This spec adds no anti-cheat
  evasion (no drivers, no hooks, no injection into the game process). Account
  risk and licence risk stay as they were before this spec.
