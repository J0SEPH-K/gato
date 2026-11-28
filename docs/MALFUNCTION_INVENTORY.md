# Malfunction inventory — fleet logs, 2026-11-28 (HO-25)

Read-only. Source: relay `log` jobs (`relay_cli.py log <pc> 3000000`), saved to
`~/Projects/gato_data/logs_20261128/` (not in the repo). Code locations are pinned to
`d0dda84` (= VERSION 1.0.45, the build the fleet runs; repo HEAD is 1.0.47, so HO-5/8/9 fixes are source-only, not deployed).
Every claim is labelled MEASURED (counted from the logs by script), HYPOTHESIS (code-reading, not reproduced) or UNVERIFIED.

## Coverage of the data

| PC | VERSION | Buffer (log lines carry HH:MM:SS only, no date; newest line is 2026-11-28 23:47) | Used |
|---|---|---|---|
| DESKTOP-7GHL129 | 1.0.45 | 07:41:55 → 23:47:36 (16.09 h, 3 MB cap clipped the earlier part) | yes |
| qwer | 1.0.45 | 09:29:00 → 23:48:10 (14.32 h, clipped) | yes |
| WIN-64I6UT8GMMP | 1.0.45 | agents row age 41,465 s (~11.5 h offline); `log` job queued, no answer in 240 s. The only copy on disk is a 2026-11-24 pull (14:47–15:53, older build) — not used | **MISSING** |
| finevt-7 | 1.0.19 / 1.0.22 | last poll 348,067 s ago (~4 d, app closed); not queried | **MISSING** |
| deploy-check, diag-mac, probe | 1.0.16–1.0.18 / vt | dev/test rows, 4–5 days stale | n/a |

All Korean text decoded as UTF-8; control counts: `전투 진입` = 1038 (D) / 1057 (qwer), so the decoder is sound.
Both live PCs are the same day only, so "per day" below = Nov 28. No midnight wrap in either buffer (checked).

## Headline numbers (MEASURED)

| | DESKTOP-7GHL129 | qwer |
|---|---|---|
| battles entered / attacks | 1038 / 2085 | 1057 / 2168 |
| `구동 시작` / `구동 정지` | 30 / 30 | 16 / 16 |
| `정지 — 사유:` lines | 25 (all `300루프`) | 11 (all `300루프`) |
| stops with NO reason line in the preceding 40 lines | **0** | **0** |
| `자동 재시작 중단` (5 stops in 600 s) | 3 | 2 |
| time stopped after an abort, until a human restarted | 32,830 + 404 + 161 = 33,395 s (9.28 h) | 23,761 + 3,355 = 27,116 s (7.53 h) |
| …as share of buffer | **57.6 %** | **52.6 %** |
| Python tracebacks | 0 | 0 |
| food refills (`[포만감]`) filled / confirmed | 76 / 76 | 80 / 80 |
| mercenary revives | 55 | 49 |

Caveat on "time stopped": measured as gap between the abort and the next `구동 시작`. Whether the PC would have hunted for that whole gap
(game state, nobody present) is UNVERIFIED; it is an upper bound on lost run-time. **Aborts are the dominant loss by two orders of magnitude;
ordinary `300루프` stops cost ~2,160 s in total (36 stops × ≈60 s).**

## Ranked failure classes (frequency × run-time lost)

| # | Class | Count (D / qwer) | Run-time lost (MEASURED) | Status |
|---|---|---|---|---|
| 1 | 조철 wrong answer → trigger still true after restart → zero-battle restarts → abort | 2 rounds (09:08, 20:33) / 0 | 32,830 s + 161 s | COVERED HO-5, HO-10 (decoder), HO-8 (abstain + lingering board) — all fixed in source only, undeployed |
| 2 | 자방문 wrong → `팅(시스템 팝업)` still true → 4 restarts in 31 s → abort | 0 / 1 (11:40) | 23,761 s | **UNCOVERED** (A) |
| 3 | Zero-battle `300루프` restart chain with NO popup/조철 → abort | 1 chain (18:42–18:46) / 1 chain (20:43–20:45, plus 20:40) | 404 s + 3,355 s (+ ~9 stops of budget) | **UNCOVERED** (B) |
| 4 | F4 (user stop) → false `거상 창이 사라짐` `_stop_now` + competing auto-restart | 4 F4 presses → 4 false window-lost stops / 0 | 161 s (it supplied the 5th stop of the 20:37 abort) | **UNCOVERED** (C) |
| 5 | Ordinary `300루프 전투 미진입` stop after a ~42 s lull, then auto-restart | 25 / 11 | ≈ 60 s each (42 s idle + 8 s grace + 10 s delay) = ~2,160 s | **UNCOVERED** (D) — low |
| 6 | 자방문 captcha solved wrong (1 of 5), 2 of 5 submitted after the refresh budget with conf 0.87–0.93 | 0 / 1 of 5 | feeds class 2 | **UNCOVERED** (E) |
| 7 | Foreground steal fails ~continuously (`전면 전환 실패 N회`) | counter rate 3.9/s (07:42–09:10, process 1) and 3.5/s (18:19–23:47, process 2; counter reset at the 18:19 relaunch) / 1.7/s | unmeasured: clicks still land (2,085 attacks); each failure costs ~0.45 s dead time per skill | **UNCOVERED** (F) |
| 8 | Chat sniffer reassembly error `'NoneType' object has no attribute 'syn_seq'` | 5 / 9 | none measured; chat/packet path | **UNCOVERED** (G) |
| 9 | `[고트] 전투 분석 시작 실패` on every start | 33 / 16 | none (noise) | **UNCOVERED** (H) — low |
| 10 | 조철 — 5-in-600 auto-restart budget also spent by real stops (`AUTO_RESTART_MAX_IN_WINDOW=4`) | n/a | see 1–4 | folded into A–C |
| 11 | Duplicate instances | 0 duplicate-second `전투 진입` events in either log | 0 | COVERED HO-9 (source only); not observed in this window |
| 12 | Dummy-mob suspicion (504 / 335 lines), skips (13 / 3 `더미몹 판정`) | 13 skips × ≥15 s ≈ 195 s / ≈45 s | ~240 s | COVERED (DummyGuard, shipped); not a fault |
| 13 | `색적 결과 폐기` (target moved before click) | 963 / 624 | 1 loop each | expected behaviour, not a fault |
| 14 | Scene `unknown` | 7 lines (22:19:52–58) / 48 lines | 0 | explained: all inside 자방문 windows (D 22:19; qwer 10:07, 11:40, 19:57, 22:38). Not a fault |
| 15 | Food / revive triggers | 76/76, 80/80 confirmed | 0 | healthy |

### Class detail

**1 — 조철 → abort.** D 09:08:02 clicked slot 4 (`조철 패킷 해독 → 4 (… off=4,7 …)`, `reveal=2 (0.968)` = truth 2); 20:33:37 clicked 4 again
(`reveal=None`). Packet decoder produced answer 4 on both rounds with different first markers (5, 1) — the constant-column signature. After each wrong
answer `조철 출현` was re-detected on every restart: 09:09:01, 10:07, 10:54, 11:42 (4 restarts, 0 battles, 37–56 s each) → `자동 재시작 중단` 09:12:37; again 20:34:52, 35:56, 36:59 then `거상 창 사라짐` → abort 20:37:31.
Code: `brain.py:1926 _stop_now('조철 오답')`, `brain.py:2149` abort, `AUTO_RESTART_MAX_IN_WINDOW=4` (`brain.py:169`). Fixed in source by fe4b122/0f4d307, not in the 1.0.45 fleet build.

**2 — 자방문 → 팅 popup → abort (A).** qwer 11:40:10 자방문 appears; refresh budget (2) consumed, third read `GZ1L4` submitted with margin 0.866; 11:40:27 `자방문 오답 — 즉시 종료`; the game then shows a system popup:
`[확인중] 팅(시스템 팝업)` → `팅(시스템 팝업) — 즉시 종료` at 11:40:28, then again at the first frame of every restart (11:40:38, :48, :58, 11:41:08/09: `[trigger] 감지: 팅(시스템 팝업)` already true on the first frame) → `자동 재시작 중단` 11:41:09.
Macro stayed down until the human restart at 18:17:10 = 23,761 s. Same structure as class 1: the auto-restart restarts into a screen state that is still the stop condition.
Code: `brain.py:2053 _stop_now('자방문 오답')`, `brain.py:164 STOP_NOW_TRIGGERS={'팅(시스템 팝업)'}`, trigger confirm at `brain.py:2173`, restart at `brain.py:2147–2160`.

**3 — zero-battle chain without popup (B).** D 18:41:59 (stop after a 23-min healthy run), restarts 18:42:17, 18:43:21, 18:44:25, 18:45:29: each logged `구동 시작`, `[게이트] 전부 통과` loops, 12–19 `더미몹 의심` lines, **0** `전투 진입`, `300루프` stop after 54 s; abort 18:46:22; human restart 18:53:06 (404 s). No 조철/자방문/팅 trigger on those frames (only the routine `B모드`/`T밴` — the same two triggers are present at successful restarts, e.g. 19:14:10, 21:17:28, so they are not the cause).
qwer 20:42:56 → restarts 20:43:07, 20:44:11, 20:44:59 (0 battles, 17/12/3 dummy lines) → abort 20:45:36; human restart 21:41:31 (3,355 s).
ROOT CAUSE UNKNOWN. HYPOTHESIS (≈50 %): character stands on a depleted/unreachable spot (consistent with `더미몹 판정`, `색적 결과 폐기` ×N and the skill's "hunts in place, never roams" rule) and every restart re-runs the same fruitless loop. UNVERIFIED: no frame exists for these minutes — the logs carry no screen state, and Field Ops may not send `shot` jobs while a PC is mid-hunt. The actionable defect regardless of cause: the stop line carries no evidence (no saved frame, no scene/trigger snapshot) and recovery is "retry identically".
Code: `brain.py:2263–2269` (`_no_battle_count`/`NO_BATTLE_LIMIT=300` → `_stop_bot`), `brain.py:2147–2160`.

**4 — F4 → false window-lost (C).** D: `[F4] 전투 종료` at 18:53:11, 20:37:12, 22:40:07, 22:40:26 — each is followed 3–7 s later by `캡처 실패 — 거상 창 확인 중` → `거상 창이 사라짐 (캡처 불가) — 즉시 종료` (18:53:17, 20:37:18, 22:40:14, 22:40:32): 4/4. The window never left (hwnd stays 197188 across 18:53; 394574 across 22:40). Manual `[F3] 전투 시작` follows at 18:53:18 and 22:40:36, and an `[자동재시작]` still fires on its 10 s timer (18:53:27, 22:40:42) — a restart racing the user's own start.
At 20:37 the false window-lost stops (20:37:18, 20:37:31) were the 4th/5th stops of the window → `자동 재시작 중단`.
HYPOTHESIS (≈70 %): the F4 handler tears down capture (WGC) while the brain loop is still running; the loop reads capture failure as window loss. Code: `brain.py:2194 _stop_now('거상 창이 사라짐 (캡처 불가)')`; F3/F4 handlers in `input.py`/`prism.py` (not read in this pass).

**5 — normal `300루프` stop (D).** 36 stops; seconds since the last `전투 진입` when the 300-loop clock fired: D 41,45,52,42,42,49,49,43,42,41,42,42 (healthy runs) and 80–336 s (stops inside restart chains or after a long fight-free stretch). The threshold is loop-count, not seconds (`_no_battle_count += units`, `brain.py:2266`), so the real timeout is ≈42 s of no fight.
Healthy runs end this way every 4–80 min; each is recovered by the 10 s auto-restart. The cost is small but it spends the 5-in-600 budget (A–C chains are exactly what happens when 2–3 of these cluster).

**6 — 자방문 accuracy (E).** 5 events on qwer + 1 on D: 5 passed (D 22:19 first try; qwer 10:07 try 3, 19:57 try 3, 22:38 try 1), 1 wrong (qwer 11:40 try 3). Reads at 0.87–0.93 after two refreshes are submitted anyway (`갱신 2회 소진 — … 로 그냥 제출`). Records saved as `jamun_20261128_{100727,114027,195804,223905,222002}` on the PCs (relay `ls`/`pull` can fetch them; not pulled in this pass).

**7 — foreground (F).** `전면 전환 실패 N회 - 좌표 클릭으로 계속` logged every 100: D 898 lines, qwer 896. Code `input.py:326`. The 1.0.41 ladder is deployed; failures persist at 1.7–3.9 /s (MEASURED from consecutive counter lines). Whether this affects reaction time cannot be derived from the log (UNVERIFIED).

**8 — sniffer (G).** `채팅 재조립 오류 — 해당 연결 초기화: 'NoneType' object has no attribute 'syn_seq'` ×14 and `채팅 프레임 해석 지연` ×50 (12 / 38).
`sniffer.py:463` reads `if stream or stream.syn_seq != seq:` — a decompiled-boolean inversion (should be `not stream or …`): with `stream is None` it dereferences `None.syn_seq`, which is exactly the logged error, and a live stream is torn down on every SYN. HYPOTHESIS ≈85 %; confirm with `dev/tools/bytecode_compare.py` against the original `.pyc` per the skill before editing. `wpcap=False` is also logged on every start (D 18:19:27), i.e. the chat sniffer runs on the fallback.

**9 — 고트 (H).** `전투 분석 시작 실패: 고트 본 창을 찾을 수 없습니다 (최소화됐거나 구조 변경)` on every start (`prism.py:452`), 33 / 16. Hunts proceed (`[용병] 고트 기록상 사망` lines appear 28 / 17 times, so a 고트 record path exists), so this is noise, not a stopper — but it means the log cannot distinguish a real 고트 failure.

## UNCOVERED issue specs (for the GATO President to create as stage-3 children)

**A. Auto-restart must not restart into a still-true stop condition (자방문/팅 popup).**
Owner: GATO Engineering. Files: `brain.py` (`_loop` finally block ~2147; `STOP_NOW_TRIGGERS`; `_handle_jamun` stop at ~2053), `prism.py` (`_auto_restart` ~576).
Fix idea: on `_stop_now` for 자방문/조철/팅, record `_stop_cause`; the auto-restart worker re-checks the cause's trigger on a fresh frame before starting and, while it is still true, waits (bounded, e.g. 5 × 10 s) without counting toward the 5-in-600 budget; after the bound, abort with the cause in the reason. No clicking on the popup (anti-cheat risk; popup dismissal needs a verified template per the skill).
Test: dev/mock scenario — `팅` trigger stays true for N frames after a 자방문 wrong: (a) current code produces 5 stops in <40 s and `자동 재시작 중단` (assert it FAILS on d0dda84 logic), (b) fixed code produces 0 extra stops and a single abort-or-resume decision; (c) trigger clears after 2 checks → run resumes. Run with the change stashed to prove the scenario fails.

**B. Zero-battle restart chains: capture evidence and stop thrashing.**
Owner: GATO Engineering. Files: `brain.py` (no-battle stop ~2263; abort ~2147), `debug.py`/capture helper.
Fix idea: on each `300루프` stop write `debug/stuck_<ts>/frame.jpg + state.json` (scene, active triggers, last 5 `몹 클릭` coords, dummy-blacklist size, `전면 전환 실패` count); on the 2nd consecutive zero-battle restart, log a distinct line `연속 무전투 재시작 N` and do not auto-restart a 3rd time inside the same window. Goal: the next occurrence is diagnosable (this inventory could not root-cause it).
Test: mock — scenario with a main-scene frame and a detector that never produces a battle: assert evidence files are written once per stop, the log line appears, and the chain stops after 2 with a reason; scenario where the 2nd restart enters a battle resets the counter.

**C. F4 (user stop) must not become `거상 창 사라짐`, and a manual F3/F4 cancels the pending auto-restart.**
Owner: GATO Engineering. Files: `prism.py` (hotkey handlers, `_auto_restart` timer), `brain.py:2194`.
Fix idea: F4 sets `user_requested=True` before tearing down capture; capture failure in the next 10 s while `user_requested` is set logs `사용자 정지` and exits without `_stop_now` and without incrementing `_auto_restart_at`; a pending auto-restart timer is cancelled when F3 or F4 arrives.
Test: unit/mock — simulate F4 then a failing `grab`: assert stop reason is `사용자 정지`, `_auto_restart_at` unchanged, no restart scheduled; assert FAILS on d0dda84 logic (reason `거상 창이 사라짐`, restart scheduled). F3 within the 10 s timer cancels the timer (single `구동 시작`).

**D. 300-loop no-battle stop: time-based, scene-aware, and logged with the last-seen mob count.**
Owner: GATO Engineering. Files: `brain.py` (~2263–2269, `NO_BATTLE_LIMIT`), `config.py`.
Fix idea: keep the safety stop but measure it in seconds (current effective ≈42 s), add the last detector count and dummy-blacklist size to the stop reason, and make the limit a documented config value. Do NOT lengthen it blindly: it is the guard for the disconnect case (팅 의심).
Test: mock — lull of 30 s then battle ⇒ no stop; lull of 60 s ⇒ stop with the new reason string; confirm `dev/test_auto_restart.py` still passes.

**E. 자방문 low-confidence submits: measure, then gate.**
Owner: GATO Engineering (vision worker). Files: `brain.py` jamun block ~2000–2060, jamun reader, `docs/JAMUN_FINDINGS.md`.
Fix idea: pull the 5 saved `jamun_20261128_*` records via relay `pull` (read-only), score the reader on them and any earlier records; report margin vs correctness; if wrong reads cluster below a margin, spend the refresh budget (not a guess) until margin ≥ threshold, and stop with `자방문 신뢰도 부족` rather than submitting 0.87.
Test: replay on the labelled records: 0 confident-wrong (margin ≥ threshold) and report abstention rate; the 11:40 record must abstain or be right.

**F. Foreground-steal failure rate.**
Owner: GATO Engineering. Files: `input.py` (~326 steal ladder, `_fg_fail`), `capture.py`.
Fix idea: log, throttled, WHICH window holds the foreground and what the ladder step that failed was (class name + title of `GetForegroundWindow()`), plus ms spent in the failed steal per click, so the failure can be attributed (own panel? RDP? second GATO instance?). Measure before changing the ladder.
Test: unit with a fake win32 layer asserting the new diagnostic fields and that the click is still issued on failure (no regression to 1.0.41 behaviour).

**G. sniffer.py:463 inverted condition.**
Owner: GATO Engineering (Solver squad consulted: pktjochul depends on this stream). Files: `sniffer.py:463`.
Fix idea: run `dev/tools/bytecode_compare.py` against the original `.pyc`; if the original is `if not stream or stream.syn_seq != seq:`, fix and add a regression test feeding a SYN for an unseen key.
Test: unit — `_segment(key, seq, b'', flags=2)` on an empty `_streams` must create a synced stream and not raise; assert it FAILS today with `'NoneType' object has no attribute 'syn_seq'`.

**H. 고트 start-failure noise.**
Owner: GATO Engineering. Files: `prism.py:452`.
Fix idea: log once per process (or once per `구동 시작` with a counter) and record `고트=off` in the status line; keep failing open. Test: mock with 고트 unavailable: exactly one line per start, hunt unaffected.

## "Works without malfunction" — canary soak bar (for HO-26)

Run the release candidate on ONE real PC, human-started, no operator touching F3/F4 or the game for the whole period. Judge from the PC's `gato_debug.log` pulled via relay (pull every ≤ 2 h so the 3 MB tail cap does not clip the start — the buffer at 3.5 battles/min holds ≈15 h).

| # | Requirement | Pass threshold | Fleet baseline today (1.0.45) |
|---|---|---|---|
| 1 | Duration | ≥ 8 h continuous wall-clock, includes ≥ 1 full `300루프`-lull cycle | — |
| 2 | Hunting availability = (time in runs with ≥ 1 battle) / wall-clock | ≥ 95 % | ≈ 42 % D / ≈ 47 % qwer |
| 3 | `자동 재시작 중단` | 0 | 3 / 2 |
| 4 | Consecutive zero-battle restarts | ≤ 1 | 4 |
| 5 | Unexplained stops = a `구동 정지` with no reason line (`정지 — 사유`/`즉시 종료`) in the preceding 40 lines, or a reason outside {포만감 템 없음, 무게 꽉 참, 사용자 정지} | 0 | 0 reasonless, but 9 stops had false or avoidable reasons (4 F4 window-lost, 5 lingering `팅` popup on qwer) |
| 6 | Every stop has a logged reason and, for stops other than the three above, a `debug/stuck_*` evidence dir (spec B) | 100 % | reason 100 %, evidence 0 % |
| 7 | 조철: confident-wrong clicks | 0 (every round answered right or abstained) | 2 of 2 answered rounds wrong |
| 8 | 조철 evidence gate (rounds are ~2/day, so the soak alone cannot prove accuracy): the HO-10 replay over all labelled rounds | 0 confident-wrong, abstain rate reported | open (HO-10 in progress) |
| 9 | 자방문: wrong submits | 0 | 1 of 6 |
| 10 | Tracebacks / `오류:` lines excluding the chat sniffer | 0; chat sniffer `syn_seq` 0 after spec G | 0 / 14 |
| 11 | Battles per hunting hour | ≥ 60 (baseline D 64/h, qwer 74/h over the whole buffer, aborts included) | 64 / 74 |
| 12 | Duplicate instances (`COUNT` of Gato processes at start/end, same-second duplicate events) | 1 / 0 | 0 duplicate events observed |
| 13 | Run still alive at the end (`running=True`, agents `age` < 60 s, `uptime_s` increasing) | yes | — |

FAIL on any of 3, 5, 7, 9; the rest are reported with the number and judged by the President. Each hour: battles, attacks, stops with reasons, 조철 rounds (right / wrong / abstained), 자방문 (passed / wrong), restarts.
