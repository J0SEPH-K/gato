# Selling GATO — zero-cost plan (2026-11-21)

No 사업자등록, no subscription, no monthly bill. One-time license per PC. Every piece below is free
tier or funded out of the first sales.

## 0. What "free" changes

| Piece | Paid plan | Free plan | Verdict |
|---|---|---|---|
| License server | 카페24 VPS 16,000원/월 | Cloudflare Workers + D1 free tier | **Free works** — fits ~70 users |
| Hosting the update file | VPS storage | GitHub Releases (already live, already free) | **Free, already built** |
| Domain | 15,000원/yr | `*.workers.dev` subdomain | **Free** |
| Source protection | PyArmor Pro $89 | Nuitka (Apache-2.0) | **Free works** — kills the .pyc |
| Installer signing | Certum Individual $99/yr | unsigned + SmartScreen warning | **Start free, buy from revenue** |
| Payments | PG (needs 사업자) | 크몽 개인 전문가 / 계좌이체 | **Free, no 사업자등록** |
| **Total** | ~1,077,000원 first year | **0원** | |

One real ceiling: Cloudflare free is 100,000 requests/day. At a 20 s heartbeat that is only ~23
users. So the licensed client heartbeats **every 60 s** (~69 users), and the server writes to D1 only
on state change, not on every beat. Past ~70 users the $5/mo Workers plan is the first money spent —
by then that is one sale's worth.

## 1. Source protection, free

PyInstaller ships `.pyc`, and this repo's own `net.py` is a PyLingual decompile — that is what a buyer
gets in five minutes.

**Nuitka** compiles to C, then to a native binary. Python bytecode is gone; the logic is machine
code. That is the whole win, and it is free (Apache 2.0).

- `--nofollow-import-to=` for stdlib and ultralytics, compile the app to a native binary.
- Optional extra later: PyArmor free trial on `jochul.py`/`detector.py` before Nuitka. The free tier is
  limited (file count/size, no RFT/BCC) — if it fights the build, skip it. Nuitka alone is enough.
- `assets/models/*` (132 MB of `.pt`) ship as data. Not source.

What still leaks: function names, string literals in the binary, and Ghidra for someone determined.
That is the ceiling for any Python product and no 거상 buyer goes that far.

Build risk is real: Nuitka on Windows takes CI from ~2 min to ~15-25 min and ultralytics needs
`--include-package` work. Do it on a branch and prove the selftest passes on the built artifact
before the first sale.

## 2. License server, free, on Cloudflare

`net.py` already speaks the whole protocol — `/auth`, `/heartbeat`, `/cmd`, `/shot`, `/stats`,
`/error` — and it is switched off by one line (`LOCAL`). Point `SERVER` at the Worker and the client
side is done.

One Worker + one D1 table:

- `POST /auth` — license key + HWID → HMAC token, 1 key = 1 seat, `expired`/`revoked` reasons the
  client already handles
- `POST /heartbeat` — token + HWID recheck; returns `min_version` and `notice`
- admin endpoint behind a secret — issue / revoke / re-issue
- **72 h offline grace** — the client already tolerates `MAX_NET_FAILS`; a network blip must never
  stop a running bot
- reactivation limit 2 per 6 months, by Discord request

Free tier is enough: 5 M D1 reads/day, 100 k writes/day, 5 GB storage, 10 ms CPU per invocation
(enough — one indexed query and an HMAC). Signup needs no card. Keep it to ~150 lines so the CPU
budget is never close.

## 3. Updates, free, already built

`update.py` pulls from public `J0SEPH-K/gato-setup`: SHA256 + size verified, waits for idle, silent
install, relaunch. Source stays in the private repo; only the built binary is public, and an
installer without a key does nothing. **No VPS needed.**

Add:

- **`min_version` floor** — heartbeat returns it; a client below it refuses to start with
  `필수 업데이트` and one button. This is the most important line in the build: when 거상 patches,
  every copy breaks the same hour and this is the only way to force everyone onto the fix.
- **Vivaldi-style notice** — panel banner `새 버전 vX 나왔습니다 — [지금 업데이트] [나중에]` plus a
  one-line changelog. Never interrupts a running bot (already true).

## 4. Cost: 0원

Nothing to buy to launch. First optional spend, paid out of revenue:

| When | Item | Cost |
|---|---|---|
| after ~10 sales | Certum Individual code signing, cloud, no USB token | $99/yr (~13만원) |
| past ~70 users | Cloudflare Workers paid | $5/mo |

Unsigned until then means SmartScreen `알 수 없는 게시자` → `추가 정보` → `실행`. Put that on the
landing page with a screenshot so it is not a surprise, and sign as soon as the cert is affordable —
unsigned costs conversion, not legality.

## 5. Getting paid with no 사업자등록

- **크몽 개인 전문가** — allowed with no business registration and no approval step, just 본인인증 +
  a 계좌 in your own name. Fee is 16.4% under 700,000원, so list at **190,000원** there and net
  ~158,000원. It is also the trust layer for a stranger who won't wire money to an individual.
- **계좌이체 direct** — 0% fee, for people arriving from 유튜브/Discord who already trust the demo.
  Cheaper for both sides; use 크몽 only for cold buyers.
- 크몽 does not withhold 3.3% — report the income in the May 종합소득세 filing yourself and keep the
  fee invoices as expenses. Repeated sales technically make you 사업자등록 대상; register once volume
  is steady, not before.

## 6. Price

From real listings: 지존오토 resale 8-10만원, 3클라 오토 초기 25만원, 작업장 세팅 30만원 + 자리당 월
10만원, 린클매니저 월 45,000원/PC, OpenMacro $19.99 lifetime, GrindHero $249 lifetime.

| Tier | Direct | 크몽 | Contents |
|---|---|---|---|
| 1 PC | **150,000원** | 190,000원 | 1 key, 1 PC, 업데이트 12개월 |
| 2 PC | **250,000원** | 300,000원 | |
| 3 PC | **350,000원** | 420,000원 | + 우선 지원 |
| 갱신 (12개월 후) | 50,000원/yr | — | optional, bot runs without it |

No subscription, so the 12-month update window is what keeps the thing affordable against 거상's
patch cadence. State it plainly at purchase.

Refund: 7 days, plus a written clause — `거상 패치로 인한 중단은 환불 사유 아님, 업데이트로 대응`.

## 7. Demand, zero budget

1. **유튜브 60-90 s demo** — a real 사냥터 clear, and one clip of 조철 being solved. This category
   sells on video (광말구, 땡겨, 강철비 are all macro-review channels); one review beats any ad.
2. **거리니닷컴 / 다음 카페 거상투** — where 거상 users actually read. 후기 thread with the video and
   the price list.
3. **디스코드** — support + update pushes, one channel per release.
4. **크몽** — cold-buyer trust layer, 190,000원.
5. **중고나라 / 당근** — the 지존오토 resale crowd, weekly.

First 3 sales at a discount in exchange for a public 후기. Don't sell Discord-only; a stranger won't
join a server to see a price.

## 8. Order of work

1. Nuitka branch, selftest green on the built artifact, installer builds from it
2. Worker + D1 license server, `LOCAL=0`, HWID, 72 h grace, 60 s heartbeat
3. `min_version` floor on the existing SHA256 update path
4. Update banner UI
5. Landing page (video, price, refund clause, 거상 ToS + ban disclaimer, SmartScreen screenshot)
6. First sales → cert → sign

## 9. Honest risks

- **거상 patches kill every copy at once.** The `min_version` floor plus a fast release is the
  answer; expect one bad patch to cost a wave of refunds.
- **Bans.** 거상 escalates 20일 → 영구정지. `탐지 시 계정 정지는 감수` must be on the page.
- **Cloudflare free ceiling** is ~70 users at 60 s beats. Fine for launch, $5/mo after.
- **Nuitka can break ultralytics at runtime.** Prove it on a built artifact, not in dev.
- **Unsigned installer** loses some cold buyers until the cert exists.
- **Support load is real** — every buyer is a non-technical Windows user.
