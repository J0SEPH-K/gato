# Selling GATO — feasibility, cost, price, demand (2026-11-21)

No subscription. One-time license per PC. Three things have to exist before the first sale:
source protection, a license server, and a trustworthy update channel. The update machinery
already exists; the other two do not.

## 1. Can it be done — verdict per requirement

| Requirement | State | Work |
|---|---|---|
| Source not readable by the buyer | PyInstaller ships `.pyc`, decompiles in minutes with `uncompyle`/PyLingual (net.py in this repo is literally a PyLingual decompile) | **Build change**: Nuitka compile + PyArmor Pro on the crown-jewel modules |
| Always auto-updates | Already built (`update.py`): checks GitHub, SHA256 + size verified, waits for idle, silent install, relaunch | Move off GitHub (see 4) |
| In-app update notice like Vivaldi | Not built — it updates silently today | Panel banner + changelog line + "지금 업데이트" button |
| Can't be copied to another PC | Nothing | HWID-bound license + heartbeat |
| Buyers trust the installer | Unsigned — SmartScreen "알 수 없는 게시자" | OV code signing certificate |

All four are ordinary work. None is research.

## 2. Source protection

PyInstaller is packaging, not protection. Confirmed in the literature: PyInstaller bytecode is
extractable and decompilable with original names; Nuitka emits native code and the Python logic
is gone.

Layer it, don't pick one:

1. `jochul.py`, `detector.py`, `combat.py`, `brain.py` — the actual edge — through **PyArmor Pro**
   (`--enable-rft --enable-bcc`), then through **Nuitka** (`--nofollow-import-to=...` for the rest).
   Obfuscate-then-compile is the combination that keeps even string literals out.
2. Everything else stays plain Nuitka-compiled. `ultralytics` stays a normal package.
3. Assets (`assets/models`, 132 MB of `.pt`) ship as data. They are already the bulk of the 410 MB
   installer and are not source.

What survives anyway: function/class names and string literals in the binary, and a determined
buyer with Ghidra. That is the ceiling for any Python product; nobody reverse-engineers a 거상
macro that far. Ship it.

Cost: PyArmor Pro **$89 one-time, perpetual**. Nuitka commercial (constant protection, traceback
encryption) is **€250/yr** — optional, buy it only if the free tier proves too thin.

**Build risk:** Nuitka on Windows is a real CI change — compile times go from ~2 min to ~15-25 min
and ultralytics needs `--include-package` work. Do it once on a branch and prove the selftest still
passes before the first sale, not after.

## 3. License server

`net.py` already speaks the entire protocol to `https://public2-production.up.railway.app`:
`/auth`, `/heartbeat` (20 s), `/cmd`, `/shot`, `/stats`, `/error`, `/nlp/*`. It is switched off by
one line — `LOCAL = os.environ.get('GATO_LOCAL', '1') != '0'`. Point `SERVER` at our own box, flip
`LOCAL` to 0, and the client side is done.

Server (FastAPI + SQLite, ~600 lines):

- `POST /auth` — license key + HWID → signed token, seat enforced (1 key = 1 PC), `expired`/`revoked`
  reasons already handled by the client
- `POST /heartbeat` — token + HWID re-check, returns `min_version`, `notice`
- admin CLI — issue / revoke / re-issue / extend, seat count, per-key HWID history
- **offline grace 72 h** — the client already tolerates `MAX_NET_FAILS`; a network blip must never
  stop a running bot, and the client PCs' links are not reliable
- re-activation limit: 2 per 6 months, by Discord/카톡 request (stops one key on ten PCs, still
  friendly to someone who reinstalls Windows)

Hosting, real prices: 카페24 가상서버 비즈니스 2 GB **16,000원/월** (VAT incl., domestic IDC), or
퓨쳐인프라 Small **14,000원/월**. The auth load is trivial — a few hundred requests an hour at 50
users. **Don't** use Railway again (the current URL's host); a flat domestic VPS is cheaper and
doesn't meter.

## 4. Update channel and the notice

Today `update.py` pulls from the **public** `J0SEPH-K/gato-setup` repo. Two changes:

- Host the installer + a signed `latest.json` on the VPS behind the license check, so the release
  repo can stay private and a non-customer can't pull the binary.
- Verify the **Authenticode signature** of the downloaded installer before running it, on top of the
  existing SHA256 + size check.

In-app notice, Vivaldi-style: panel banner `새 버전 v1.0.14 나왔습니다 — [지금 업데이트] [나중에]`,
one-line changelog, and it never interrupts a running bot (already true). Plus a **forced floor**:
the server returns `min_version`, and a client below it refuses to start with "필수 업데이트" and a
single button. That floor is the only way to guarantee everyone is current when 거상 patches — and
거상 patches are exactly when every copy breaks at once, so this is the single most important piece
of the whole commercial build.

## 5. Cost

| Item | First year | Recurring |
|---|---|---|
| VPS (카페24 비즈니스 16,000원/월) | 192,000원 | 192,000원/yr |
| OV code signing, SSL.com $129 | ~190,000원 | same |
| PyArmor Pro $89 (one-time) | ~130,000원 | — |
| Domain | ~15,000원 | ~15,000원/yr |
| Hardware token for the cert (YubiKey FIPS $379) | ~550,000원 | — |
| **Total** | **~1,077,000원** | **~207,000원/yr** |

Without the hardware token (SSL.com eSigner cloud signing instead, $20/mo) the first year is about
**820,000원** but recurring rises to ~500,000원/yr. Token is cheaper after year two.

Cheaper signing route worth checking first: **Azure Artifact Signing $9.99/mo** — but individuals
are only eligible in the US and Canada, so as a Korean individual it is likely closed. If a 사업자
등록 exists under FineVT or his own name, that opens both Azure and the cheaper OV tiers.

Marginal cost per sale: **≈ 0원**. Server, cert and build all amortise. Break-even on the whole
first year is **5-6 sales at 20만원**.

## 6. Price

Market, from actual listings (not guesses):

- 지존오토 resale 8-10만원; 3클라 오토 초기 25만원 (광말구, YouTube)
- 작업장 세팅 30만원 + 자리당 월 10만원 (강철비, YouTube)
- 린클매니저 (리니지클래식) 1PC 1클라 **월 45,000원**, 2클라 81,000원 — subscription
- 해외 one-time comparables: OpenMacro $19.99 lifetime, GrindHero $149/yr-249 lifetime, dracaryS £220
- 크몽 제작 의뢰 5,000원~330,000원 (일반 업무 매크로, 게임 오토 아님)

거상 buyers expect 20-30만원 **initial** for a working setup. Since this is one-time with no
subscription, price under the market's initial cost, not at it:

| Tier | Price | Contents |
|---|---|---|
| 1 PC | **150,000원** | 1 key, 1 PC, 업데이트 12개월 |
| 2 PC | **250,000원** | |
| 3 PC | **350,000원** | + 우선 지원 |
| 업데이트 갱신 (12개월 후) | 50,000원/yr | optional — bot keeps working without it |

150,000원 for lifetime on one PC undercuts a 25만원 3클라 setup and lands near 지존오토 resale,
while the 3-PC tier is the one 작업장 buyers take. No subscription means no churn and no billing
infrastructure — but also no recurring revenue, so the 12-month update window and its renewal fee
matter: 거상 will patch and the macro will break, and free forever is not affordable.

Refund: 7 days, minus nothing — with a "거상 패치로 인한 중단은 환불 사유 아님, 업데이트로 대응"
clause written on the landing page before purchase.

## 7. Where the buyers are

Ranked by conversion, cheapest first:

1. **유튜브 데모** — a 60-90 s clip of the bot clearing a real 사냥터, plus one showing 조철 solved.
   This is how the category sells (광말구, 땡겨, 강철비 are all macro-review channels); a review
   from one of them is worth more than any ad. Post to 거상 갤러리 and 거상 유튜브 댓글.
2. **거리니닷컴 / 다음 카페 거상투** — the two places 거상 users actually read. A 후기 thread with
   the demo video and the price list.
3. **디스코드 서버** — buyers need support and updates; a channel per release is also how they get
   told to update.
4. **크몽** — slow, 4.5% fee, but it is the trust layer for a first-time buyer who won't send money
   to a stranger. List at 250,000원 there to cover the fee.
5. **중고나라** — the resale/지존오토 crowd. Post once a week, they search it.

Do **not** lead with Discord-only sales; a stranger won't join a server to see a price.

## 8. Order of work

1. Nuitka + PyArmor branch, selftest green, installer builds from it
2. License server + admin CLI on the VPS, `LOCAL=0`, HWID, offline grace
3. Update hosting on the VPS + signature verify + forced `min_version` floor
4. Update banner UI
5. OV certificate, sign the installer and the exe
6. Landing page: demo video, price table, refund clause, 거상 ToS disclaimer
7. First 3 sales at a discount in exchange for a public 후기

## 9. Honest risks

- **거상 patches break the bot.** Everyone's copy dies the same day. The forced-update floor plus a
  fast release is the answer, but expect one bad patch to cost a wave of refunds.
- **Detection/ban.** 거상's own policy escalates macro detection 20일 → 영구정지. Sell it as
  "탐지 시 계정 정지는 감수" — the landing page must say it, or the first ban wave becomes a
  refund fight.
- **Nuitka can break ultralytics at runtime.** Prove the selftest on a built artifact, not in dev.
- **Support load is real.** Every buyer is a non-technical Windows user. Budget a few hours a week
  or the 3-PC tier's "우선 지원" becomes a job.
