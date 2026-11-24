# Plan: fully autonomous, accurate 조철 solver (no human in the loop)

## Goal
A 조철 solver that decides and clicks with zero human involvement, and whose hit rate is measured by the game itself instead of by eye.

## The correction that drives everything
The previous draft put a human on the labelling step ("B4 eye-check"). Wrong, because **the game reveals the answer on every single round**. After the click the clicked character turns green and the 마패 parks over it for ~1.7 s — `brain.py:1715` says exactly that, and `brain.py:1720` already grabs that frame into `meta['reveal_slot']`.

The reveal is also already machine-readable. `read_settled` (jochul.py:777) scores each slot by median saturation in the character band — the green overlay spikes precisely that — plus gold-marker pixel count, and `settle_vote` (jochul.py:767) only accepts a reading when 4 consecutive frames agree. `dev/test_jochul_settle_read.py` pins it on the real round: frames 160-168 -> None, 169-190 -> 5, 191-206 -> None. Deterministic, cheap, already tested.

So ground truth is free and self-generated. The macro labels its own rounds, the tracker gets scored against the game's reveal, and the corpus grows every time the macro runs.

## Current context (verified today)
- `jochul.py`: `read_settled` + `settle_vote` = the oracle. `solve_tracked`/`track_centroids` = fallback (velocity-predicted Hungarian on YOLO centroids, `MIN_ENSEMBLE_VOTES = 4` of 5, abstains above `MAX_SETTLE_SPEED = 100.0` px/s). `periodic_decode`/`dp_decode` = diagnostic only, 0/6 on the real clip.
- `brain.py:_handle_jochul` already runs the oracle first (1605-1607), locks before the capture cap, and only falls back to the tracker if nothing locked (1618-1622). On total uncertainty it **stops the whole macro** (1688).
- Evidence: one confirmed round, `dev/fixtures/jochul_round1` (207 frames, first 2, truth 5). `docs/JOCHUL_FINDINGS.md`: every older approach 0/6, tracker 1/6, gold rule 6/6 on the 2020 clip, fails on pink-skin characters.
- Full stack only at `/Users/jungjunkim/Projects/diablia/workspace/_tools/cv/bin/python` (3.11, torch, ultralytics, cv2 5.0). System python3 has no torch.
- No game client, no remote shell. Cold start must come from public video; live confirmation waits on the client.

## Architecture
Three layers, all self-checking. (1) **Oracle**: `read_settled` + `settle_vote`, unchanged semantics — it decides and clicks. (2) **Self-labelling**: the same oracle plus `find_marker_slot` read on the post-click reveal frame. A round is admitted to the corpus only when both readers agree on the same slot; disagreement self-rejects. That is what replaces the eye-check with a machine check. (3) **Fallback + training signal**: `solve_tracked` answers rounds the oracle cannot converge on, and every admitted round scores both readers so improvement is a number, not a feeling.

## Step-by-step

### A. Skill (remove the human)
**A1.** Rewrite `~/.hermes/skills/research/gersang-game-research/SKILL.md`: drop the eye-check section, add *Self-label* (run `read_settled` over the 5 s after the click, run `find_marker_slot` on the reveal frame, admit only on agreement, else reject with the reason). Add a *Never* line: never label a round by looking at it.

### B. Cold-start corpus, machine-labelled
**B1.** `mkdir -p dev/corpus/{raw,rounds,rejected}`; download 8 clips with `yt-dlp -f 'bestvideo[height<=720]+bestaudio/best'`. Expect `ls dev/corpus/raw | wc -l` -> 8.
**B2.** Write `dev/tools/jochul_extract.py`. Per clip: ffmpeg to 1024x768, 2 fps scan with `find_marker_slot` on the crop, group hits within 20 s into segments, then per segment write `NNNNN.jpg` (q92) at source fps up to 20 s. Label `first` = majority marker slot in the first 3 s; `truth` = oracle-locked slot in the last 5 s; `truth_marker` = majority `find_marker_slot` over the same 5 s. Admit only if `truth == truth_marker` and both non-None, else `mv` to `dev/corpus/rejected/` with the reason. Expect >=1 admitted round from one clip with `truth` set.
**B3.** Run over the rest; target >= 15 admitted (`ls -d dev/corpus/rounds/* | wc -l`). Under 10 admitted -> raise the scan to 4 fps before adding clips.

### C. Scoreboard, TDD
**C1.** `dev/test_jochul_corpus.py`, red first: assert `solve_tracked` returns 5 for `jochul_round1`; assert `None` for the first 30 frames (nothing guards short input today). Run -> one failure.
**C2.** Minimal fix in `track_centroids`: `if len(dets) < 20: return None, 'recording too short'`. Re-run -> green.
**C3.** `dev/tools/jochul_score.py`: replay each round through `solve_tracked` **and** through the oracle, write `ok_oracle`/`ok_tracker` into `meta.json`, print `truth / oracle / tracker` per round then `oracle N/M`, `tracker N/M`, `abstained K`.
**C4.** Commit.

### D. Make the fallback earn its place
**D1.** Branch on the numbers, rule fixed in advance: oracle >= 0.95 -> oracle stays primary and the work becomes converging faster (lower `SETTLE_NEED` with a stricter margin). Oracle < 0.95 -> tune the oracle bands against the corpus, one variable per commit, re-score. Tracker >= 0.80 -> promote to co-primary so rounds the oracle misses still get answered instead of stopping.
**D2.** Every commit carries the delta: `jochul: settle margin 20->28 (oracle 18/20 -> 20/20)`.

### E. Autonomy hardening (the actual "fully autonomous")
**E1.** Replace the abort at `brain.py:1688`. On uncertainty: don't click, wait up to 3 s for the board to close itself, then resume the round loop. Stop only after 3 consecutive unanswerable rounds.
**E2.** `dev/tools/jochul_ingest.py` folds live rounds (already saved under `debug/jochul_rounds`) into `dev/corpus/rounds` under the same dual-reader rule — self-growing corpus, no manual step.
**E3.** `dev/test_jochul_autonomy.py`: oracle-locked round clicks exactly once; non-converging round neither clicks nor stops; three misses in a row does stop.

### F. Ship
**F1.** `VERSION` -> 1.0.16, full `dev/test_jochul_*.py` green, prerelease.

## Validation
No accuracy claim without a printed `oracle N/M` / `tracker N/M` line in `docs/JOCHUL_FINDINGS.md`. Acceptance: hit rate on admitted rounds, reported per fps band, plus E3 green.

## Risks
- Video fps: everything collapsed at ~11 fps vs 44 fps live. Record `effective_fps`, report split by band, never pool the two.
- `read_settled` may not converge on re-encoded video; that shows up as low admitted yield, fixed with more clips — not with a human.
- Pink-skin characters break the gold rule, so those rounds self-reject instead of mislabelling. Coverage degrades, correctness does not.
- The client still will not start, so live confirmation is deferred; nothing in A-D needs it.
