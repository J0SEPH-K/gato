# 조철 암행어사 — what the game actually does (from real footage, 2026-11-20)

Source: YouTube FG723pxOhO8 (2020, 960x720, ~11 distinct frames/s), six rounds. Start slot = slot under the gold 마패
at the start, end slot = slot of the green highlighted character with the 마패 after the answer (frame-checked by eye).

| round | start slot | end slot |
|---|---|---|
| 1 | 4 | 2 |
| 2 | 5 | 4 |
| 3 | 4 | 4 |
| 4 | 4 | 5 |
| 5 | 1 | 5 |
| 6 | 5 | 4 |

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
- Old macro pipeline (15 fps sampling + swap-pair decoder): 0/6 (it only ever finds 10-11 "swaps").
- My all-frames swap decoder: not applicable (the game has no swaps).
- Two tracking-by-detection prototypes on the YOLO detections (Hungarian + constant velocity; min-cost flow over all
  frames): 1/6 and 0-1/6 = chance. The detector sees on average 3.8-4.2 of the 5 characters per frame in the scatter.
- Start slot by gold-medallion colour (skin independent), voted over frames: 6/6, no false votes
  (the old navy-hair pixel pattern found nothing on this footage; it is specific to one skin).

## What is needed for a real solver
Real-rate (60 fps) capture of live rounds. `brain._handle_jochul` already saves every failed round to `debug/jochul_fail`
and now also stores `start_slot` and `reveal_slot` in its meta, so each round labels itself.
