# 자방문 (자동방지문자 captcha) - what was verified (2026-11-20)

Offline, 47 real crops saved by the macro's previous developer (Jul-Sep 2026): text reader (`assets/models/text/best.pth`) = my own reading on
44/47, 2 more differ only by 0 vs O, 1 differs (probably my misreading). Reader confidence is below the 0.995 gate on 40/47.

Live, client PC 1.0.1, 16:51: popup appeared during hunting; macro read 3 captchas (each refresh = a NEW image, refresh budget
shown on the button "갱신(N)", 0 after two refreshes): TTV8R conf .899, PIJ7E conf .990, 85TM2 conf .940. All three reads were
correct (checked against the saved crops). It used both refreshes (gate 0.995), typed `85tm2`, clicked 확인, the dialog closed and the
game went on: correct answer, verified from the saved frames (before_confirm / after_confirm_4s). The wrong-answer pixel check
read [170, 171] (wrong dialog = [690, 690]) = not seen. The macro's "자방문 통과" is therefore backed by evidence this time.
n = 1 round, so no accuracy claim. Candidate improvement (not applied): the 0.995 gate refreshed two correct reads at conf 0.99 and 0.94.
Evidence per round: `debug/jamun_rounds/jamun_<time>/` (attempt crops + full frames, before/after confirm, meta.json).
