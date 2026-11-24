# 조철 암행어사 — what the game actually does (from real footage, 2026-11-20)

Source: YouTube FG723pxOhO8 (2020, 960x720, ~11 distinct frames/s), six rounds. Start slot = slot under the gold 마패
at the start (read by the medallion-colour detector, consistent over ~15 frames per round). End slot = where the medallion
sits in the last ~4.5 s, same detector. NOT checked by eye (the image-description tool returned no text for these frames).

| round | start slot | end slot |
|---|---|---|
| 1 | 4 | 2 |
| 2 | 5 | 4 |
| 3 | 4 | 4 |
| 4 | 4 | 5 or 3 (ambiguous: 15 vs 13 votes) |
| 5 | 1 | 5 or 3 (ambiguous: 14 vs 10 votes) |
| 6 | 5 | 4 (17 of 36 votes; others scattered) |

## Mechanics
- 5 identical characters stand in a row (x = 65,145,225,305,385 in the 447x351 board crop, y~140), a counter counts 5 -> 0
  and the 마패 floats over one of them (bobbing: visible in ~40% of frames).
- At 0 the characters scatter for ~8 s: they run around, change hair/body colour, scale up and down (depth), overlap each
  other, and animals (bear, tiger, horse, wolf) run through. The scene tint changes (green / blue / orange / white).
  There are NO clean pairwise swaps.
- Then they line up again (colours still random for a moment), a 10 s answer timer starts, the player clicks one.
  The 마패 then re-appears above the real holder (green highlight) = free ground truth for every round.
- Board layout matches the macro's coordinates (CLICK_X - 287, CLICK_Y - 231) to within 4 px.

## Measured on those six rounds
- Old macro pipeline (15 fps sampling + swap-pair decoder): 0/6 against the end slots above (rounds 4-5 count either candidate wrong) (it only ever finds 10-11 "swaps").
- My all-frames swap decoder: not applicable (the game has no swaps).
- Two tracking-by-detection prototypes on the YOLO detections (Hungarian + constant velocity; min-cost flow over all
  frames): 1/6 and 0-1/6 = chance. The detector sees on average 3.8-4.2 of the 5 characters per frame in the scatter.
- Start slot by gold-medallion colour (skin independent), voted over frames: 6/6, no false votes
  (the old navy-hair pixel pattern found nothing on this footage; it is specific to one skin).

## What is needed for a real solver
Real-rate (60 fps) capture of live rounds. `brain._handle_jochul` already saves every failed round to `debug/jochul_fail`
and now also stores `start_slot` and `reveal_slot` in its meta, so each round labels itself.

## More attempts on the same six rounds (2026-11-20, later)
- Ultralytics built-in trackers (ByteTrack, BoT-SORT) on `jochul.pt`, 256/640 px: identities are reassigned 160-300 times per
  round, the start character's id never survives to the end (0/4 on the rounds with a certain end slot).
- OpenCV MOG2 (and a median background) + Norfair Kalman tracker, 32 parameter settings: best 1/4 = chance. In the scatter the
  foreground gives only ~2-4 separate blobs per frame (characters overlap each other and animals), so tracks die and are
  re-created (60-120 ids per round).
- Caveat for all of these: the clip has ~11 distinct frames/s. Live 60 fps footage may track far better; unproven.
- New skin (pink twin-tail girls, user screenshot): `jochul.pt` finds all 5 (class 0, conf 0.86-0.93) - the model already
  covers more than one skin. The gold-colour medallion rule (V >= 170, area >= 60) does NOT find the medallion in that
  screenshot (darker, smaller): the start-slot rule is validated only on the 2020 clip's rendering.

## Design note from the user (another model's advice), assessed 2026-11-20
Proposal: clean background plate (or MOG2 with learningRate 0) + top-5 blobs + constant-velocity prediction + Hungarian
matching + coasting while blobs merge + `mss` capture at 60-120 fps + key by template match.
- Already tried on the real clip (Hungarian tracker, min-cost flow, MOG2/median + Norfair): chance level at ~11 fps.
- Untested and still plausible: the same pipeline at 60+ fps live. The only thing not yet measured.
- Does not fit this game as written: no fixed clean plate (hay-bale positions differ per round), "5 largest blobs" breaks when
  animals cross, the key template must not depend on the skin.
- Next step stays: native-fps rounds with `start_slot`/`reveal_slot` labels, then replay on the Mac.

## Round recorder (shipped in 1.0.1, 2026-11-20)
Every 조철 round is now recorded in the background, every distinct frame (WGC frame counter, up to 45/s), JPEG q92 of the
board region, to `debug/jochul_rounds/round_<time>/` (`NNNNN.jpg` + `meta.json`: times, start slot, answer, marker votes,
reveal slot, effective fps, capture mode). Last 40 rounds are kept, ~30-50 MB each. Disable with `jochul_record: false`.
To tune: copy the folder to the Mac and run `python dev/tools/jochul_replay.py <folder>` (tracker vs reveal labels).
The pink-skin screenshot shows the gold-colour reveal read fails there; in that case label by eye from the last frames.

## First live round on 1.0.1 (client PC, 2026-11-20 15:37, native 44.4 fps, 1033 frames, wgc-every-frame)
- Start slot 2 (medallion rule found it on this skin: 3 votes). Macro decoded 15 swaps, clicked slot 5.
- Ground truth: slot 5 (user watched the recorded video and confirmed the macro was correct). n = 1, so this proves nothing about
  the solver: a random click is right 20% of the time.
- After the click: the clicked character turns green, the 마패 shows over it, the board closes ~1.7 s later. The macro's reveal read
  was moved from +3 s to +0.9 s because the board is already gone at +3 s. The old "popup gone = passed" check is not a
  correctness signal (the board closes either way; unverified whether a wrong click looks different).
- Detector on native-fps frames: Ultralytics `jochul.pt` finds all 5 in the row at the start/end (100%), 4.5 of 5 per frame in
  the scatter (58% of frames show all 5). Background-blob foreground: only 2.3 blobs per frame.
- Offline tracker (dev/tools/jochul_replay.py) on this round: YOLO detections + velocity Hungarian -> slot 5 in 8/9 settings at
  44 fps, 7/9 at 22 fps and at 11 fps; blob foreground -> 3/9. Agreement with the truth on ONE round only.
- Needed before changing the macro: more labelled rounds (copy `debug/jochul_rounds`, label by watching the video).

## Replaced the swap-model decoder with a velocity/Hungarian centroid tracker as the live answer (2026-11-20)
Ran the actual solver code (not an offline experiment) against the ONE real, user-confirmed-correct client
round (start slot 2, true end slot 5): BOTH swap-model decoders got it WRONG, under every tuning tried
(`periodic_decode` on the 15fps-resampled grid -> 1; `dp_decode`, time-based, period range widened up to 3 s
-> 3 or 4, never 5). The live macro's earlier "correct" click with this exact algorithm was therefore very
likely luck (n=1, 20% baseline), not the solver working, which matches the user calling the success rate
"so shit".

A much simpler method already written for offline replay - velocity-predicted Hungarian matching of the
YOLO detector's own centroids (`jochul.track_centroids`, ported from `dev/tools/jochul_replay.py`'s
`track()`, scipy replaced with a tiny brute-force 5x5-ish assignment since scipy is not bundled in the app) -
got this SAME round right in all 9 parameter combinations tried (gate in {100,150,220} x decay in
{0.6,0.8,0.95}), both with scipy and with the ported scipy-free assignment, and even on a 1-in-5 subsampled
version of the capture (207 of the 1033 frames). This is now the PRIMARY live answer
(`JochulSolver.solve_tracked`, wired into `brain._handle_jochul_inner`). `periodic_decode` is still run and
logged for comparison on every round (and a mismatch between the two triggers the same frame-dump/upload
path as before), but it no longer decides the click.

The capture feeding the solve step changed too: `jochul.record()` (old, fixed 15 fps / 13.5 s polling loop)
was replaced with `jochul.record_all()` (same all-native-frame capture the evidence recorder already used),
since the tracker needs real motion, not a coarse sample.

Caveat: n=1 confirmed round. 9/9 parameter robustness on that one case is evidence of being clearly less
fragile than the swap decoders (which were wrong AND unstable across tunings), not a proven accuracy number.
A real hit rate still needs many more labelled live rounds - every round keeps recording as before
(`debug/jochul_rounds`), and the fixture `dev/fixtures/jochul_round1` now also serves as a permanent
regression test (`dev/test_jochul_tracker.py`) so this exact real case can never silently regress.

## 2026-11-24 - the medallion is a client asset, and matching it wins

The medallion is not gold. Decoded `Assets/Textures/UI/SecretInspector/Mapae.AGF` (10 frames, 40x65,
vertical bob y2 -> y61): a cyan/turquoise pendant on a navy ribbon. The old H14-30 "gold" window in
`find_marker_slot` could only ever hit it by accident, which is why the detector scored at chance and
the whole round leaned on YOLO tracking.

The asset list is right there in the client: `assets/textures/ui/SecretInspector/` holds
inspector{Bear,Bison,Horse,Hyena,Tiger}, Board, Mapae, Songpyeon, RiceStraw and their _Outline twins,
loaded by the constructor at RVA 0x8cc279..0x8cc4d9 (`lea rdx` = asset path, `lea rcx` = the loader
string 0x12fb3e10). The puzzle object is a `CSecretInspector_Parser` singleton.

Fix: `jochul.marker_scores()` masked-matches the shipped sprite frame 4 (TM_CCORR_NORMED, alpha mask,
+/-45 px window per slot, top 130 px band) and `find_marker_slot` returns None unless the winner beats
the runner-up by MARKER_GAP. `marker_lock` needs 4 agreeing readings inside a 6-frame sliding window,
because the medallion is only on screen ~13% of the round and blinks between bobs.

REVEAL_GUARD_S = 5.0 matters: the medallion also floats over the START slot during the intro. Without
the guard the intro burst locks the start slot and the macro answers the wrong one.

Measured on `dev/fixtures/jochul_round1` (207 frames, first=2, truth=5): start slot locked at f10,
reveal slot 5 locked at t=20.08 s - both correct, answer reached before the 22 s capture window closes.
`dev/test_jochul_marker.py` pins that (7 tests), plus the "guard removed answers 2" case.

Still unverified: whether the reveal burst is always inside the capture window for a fast shuffle; the
tracker fallback stays wired for that.
