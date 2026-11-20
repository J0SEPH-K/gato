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
