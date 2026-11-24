"""2nd-password (2차 비밀번호) keypad solver.

Why this exists (manager, 2026-11-18): 거상's secondary-password screen is a
real anti-bot control, not a cosmetic quirk -- the digit buttons sit at 12
FIXED screen positions, but which digit is drawn at which position is
reshuffled every time the screen appears. 20 wrong entries destroy the
account's secondary-password data (per the in-game warning text), so this
module is built to refuse rather than guess whenever it isn't sure.

How it works: 12 button positions are fixed (measured live, see
KEYPAD_POS). For each position we crop a small patch and match it against
the 12 known digit templates (0-9, M=지우기/clear, X=취소/cancel) saved in
assets/pin_templates/. If every position matches a template with high
confidence AND all 12 labels are distinct (no duplicate reads, which would
mean a template is miscalibrated), we trust the mapping; otherwise we log
exactly what's ambiguous and do nothing.

The actual PIN digits never pass through here as a hardcoded value -- they
come from config.second_password(), which the user types directly into the
macro's own local settings (see config.py / prism_settings.json on this PC),
never through chat or any network call.
"""
from __future__ import annotations

import os
import time

try:
    import cv2
    import numpy as np
except Exception:
    cv2 = None
    np = None

ASSET_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets', 'pin_templates')

# The whole dialog can spawn at a DIFFERENT screen position each time (seen
# live 2026-11-18: one instance top-left at ~(17,288), another at ~(49,108)
# -- a pure translation, box width/height and every internal offset were
# pixel-identical between the two, so this is NOT a rescale, just a moving
# anchor). Everything below is defined RELATIVE to the password-display
# box's own top-left corner, which we locate fresh every time via
# find_anchor() -- no fixed absolute coordinate is trusted.
#
# Offsets measured 2026-11-18 from two real captures (both agreed exactly):
KEY_OFFSETS = {
    'r0c0': (48, 47),  'r0c1': (91, 47),  'r0c2': (134, 47),
    'r1c0': (48, 84),  'r1c1': (91, 84),  'r1c2': (134, 84),
    'r2c0': (48, 120), 'r2c1': (91, 120), 'r2c2': (134, 120),
    'r3c0': (48, 156), 'r3c1': (91, 156), 'r3c2': (134, 156),
}
CONFIRM_OFFSET = (62, 187)   # 확인
CANCEL_OFFSET = (134, 187)   # 취소
HALF_W, HALF_H = 16, 12
SEARCH_MARGIN = 3  # small tolerance only; the anchor itself should now be precise
MATCH_THRESHOLD = 0.85  # normalized correlation; below this we refuse, not guess

# Password box detection: template-matched against the box's own appearance
# (far more robust than a 1D darkness threshold, which was noisy by a few
# px between two real captures and threw off every offset downstream).
ANCHOR_TEMPLATE_PATH = os.path.join(ASSET_DIR, 'anchor_box.png')
ANCHOR_SEARCH_Y_MAX = 650
ANCHOR_MATCH_THRESHOLD = 0.9


def find_anchor(frame, log=print):
    """Returns (x, y) of the password box's top-left corner via template
    match, or None if not found confidently (ambiguous -> refuse)."""
    if cv2 is None or np is None:
        return None
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
    tmpl = cv2.imread(ANCHOR_TEMPLATE_PATH, cv2.IMREAD_GRAYSCALE)
    if tmpl is not None and tmpl.ndim == 3:   # cv2 5.0 returns (h, w, 1)
        tmpl = tmpl[:, :, 0]
    if tmpl is None:
        log('[2차비번] anchor_box.png 템플릿 없음 — 중단')
        return None
    search = gray[:ANCHOR_SEARCH_Y_MAX, :300]
    res = cv2.matchTemplate(search, tmpl, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(res)
    if max_val < ANCHOR_MATCH_THRESHOLD:
        log(f'[2차비번] 비밀번호 입력창 위치를 찾지 못함 (일치율 {max_val:.2f}) — 중단')
        return None
    return max_loc  # (x, y) of top-left corner


def _load_templates() -> dict:
    out = {}
    if cv2 is None:
        return out
    for fname in os.listdir(ASSET_DIR):
        if fname.startswith('key_') and fname.endswith('.png'):
            label = fname[len('key_'):-len('.png')]
            img = cv2.imread(os.path.join(ASSET_DIR, fname), cv2.IMREAD_GRAYSCALE)
            if img is not None and img.ndim == 3:   # cv2 5.0 returns (h, w, 1)
                img = img[:, :, 0]
            if img is not None:
                out[label] = img
    return out


def _best_match_windowed(gray, x, y, templates: dict):
    """Crops a search window larger than the template around (x,y) and lets
    matchTemplate find the best-aligned position within it, instead of
    demanding the template land pixel-perfectly at (x,y). Returns
    (label, score) for the best label across all shift positions."""
    win = gray[y - HALF_H - SEARCH_MARGIN:y + HALF_H + SEARCH_MARGIN,
               x - HALF_W - SEARCH_MARGIN:x + HALF_W + SEARCH_MARGIN]
    best_label, best_score = None, -1.0
    for label, tmpl in templates.items():
        th, tw = tmpl.shape
        if win.shape[0] < th or win.shape[1] < tw:
            continue
        res = cv2.matchTemplate(win, tmpl, cv2.TM_CCOEFF_NORMED)
        score = float(res.max())
        if score > best_score:
            best_label, best_score = label, score
    return best_label, best_score


def read_keypad(frame, log=print) -> dict | None:
    """Returns {label: (x, y)} for all 12 keys if the anchor was found and
    every position matched confidently and uniquely, else None (and logs
    exactly why)."""
    if cv2 is None or np is None:
        log('[2차비번] cv2/numpy 없음 — 이 PC에서 실행해야 함')
        return None
    anchor = find_anchor(frame, log)
    if anchor is None:
        return None
    ax, ay = anchor
    templates = _load_templates()
    if len(templates) < 12:
        log(f'[2차비번] 템플릿 {len(templates)}/12개만 로드됨 — assets/pin_templates 확인')
        return None
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
    mapping = {}
    seen_labels = {}
    for slot, (dx, dy) in KEY_OFFSETS.items():
        x, y = ax + dx, ay + dy
        label, score = _best_match_windowed(gray, x, y, templates)
        if label is None or score < MATCH_THRESHOLD:
            log(f'[2차비번] {slot} 위치 글자 인식 실패 (최고 일치율 {score:.2f}) — 중단')
            return None
        if label in seen_labels:
            log(f'[2차비번] "{label}"가 {seen_labels[label]}와 {slot} 양쪽에서 인식됨 — '
                '템플릿이 서로 구별되지 않음, 중단 (추측하지 않음)')
            return None
        seen_labels[label] = slot
        mapping[label] = (x, y)
    digits_found = sorted(k for k in mapping if k.isdigit())
    if digits_found != [str(d) for d in range(10)]:
        log(f'[2차비번] 숫자 0-9가 모두 인식되지 않음 (인식됨: {digits_found}) — 중단')
        return None
    mapping['_confirm'] = (ax + CONFIRM_OFFSET[0], ay + CONFIRM_OFFSET[1])
    mapping['_cancel'] = (ax + CANCEL_OFFSET[0], ay + CANCEL_OFFSET[1])
    return mapping


def enter_second_password(hands, frame, pin: str, log=print) -> bool:
    """pin comes from config.second_password() -- plain digits, user-entered
    locally. Never logs the pin itself."""
    if not pin or not pin.isdigit():
        log('[2차비번] 설정에 2차 비밀번호가 등록되어 있지 않음 — 직접 입력하세요')
        return False
    mapping = read_keypad(frame, log)
    if mapping is None:
        return False
    log(f'[2차비번] 키패드 인식 완료 ({len(pin)}자리 입력 시작)')
    for ch in pin:
        x, y = mapping[ch]
        hands.click(x, y)
        time.sleep(0.25)
    hands.click(*mapping['_confirm'])
    log('[2차비번] 확인 클릭 완료')
    return True
