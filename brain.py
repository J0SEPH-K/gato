# Decompiled with PyLingual (https://pylingual.io)
# Internal filename: 'brain.py'
# Bytecode version: 3.11a7e (3495)
# Source timestamp: 2026-09-21 14:09:33 UTC (1789999773)

from __future__ import annotations
import ctypes
import ctypes.wintypes
import glob
import json
import os
import platform
import random
import re
import sys
import threading
import time
import traceback
from datetime import datetime
import cv2
import numpy as np
import win32con
import win32gui
import captcha
import chat
import combat
import config
import detector
import jochul
import vision as vis
from capture import grab_once, grab_hwnd, grab_hwnd_after, grab_hwnd_region, find_window, find_windows, _get_process_exe
from input import Hands

_GATO_EXE = 'gersang-traders.exe'
_gato_cache = {'files': None}
def _pid_by_exe(name_lower: str):
    TH32CS_SNAPPROCESS = 2
    k = ctypes.windll.kernel32
    class PE32(ctypes.Structure):
        _fields_ = [('dwSize', ctypes.wintypes.DWORD), ('cntUsage', ctypes.wintypes.DWORD), ('th32ProcessID', ctypes.wintypes.DWORD), ('th32DefaultHeapID', ctypes.c_void_p), ('th32ModuleID', ctypes.wintypes.DWORD), ('cntThreads', ctypes.wintypes.DWORD), ('th32ParentProcessID', ctypes.wintypes.DWORD), ('pcPriClassBase', ctypes.wintypes.LONG), ('dwFlags', ctypes.wintypes.DWORD), ('szExeFile', ctypes.c_char * 260)]
    snap = k.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    pe = PE32()
    pe.dwSize = ctypes.sizeof(PE32)
    pid = None
    try:
        if k.Process32First(snap, ctypes.byref(pe)):
            while True:
                if pe.szExeFile.decode('cp949', 'replace').lower() == name_lower:
                    pid = pe.th32ProcessID
                    break
                if not k.Process32Next(snap, ctypes.byref(pe)):
                    break
    finally:
        k.CloseHandle(snap)
    return pid
def _gato_files():
    cached = _gato_cache['files']
    if cached and os.path.exists(cached[1]):
        return cached
    else:
        found = None
        try:
            pid = _pid_by_exe(_GATO_EXE)
            if pid:
                exe = _get_process_exe(pid)
                if exe:
                    d = os.path.join(os.path.dirname(exe), 'battle_sessions')
                    a = os.path.join(d, '_autosave.json')
                    if os.path.exists(a):
                        found = (os.path.join(d, '_autosave.journal.jsonl'), a)
        except Exception:
            pass
        if found is None:
            for base in [os.environ.get('ProgramFiles', 'C:\\Program Files'), os.environ.get('ProgramFiles(x86)', 'C:\\Program Files (x86)'), os.environ.get('LOCALAPPDATA', '')]:
                if not base:
                    continue
                else:
                    hits = glob.glob(os.path.join(base, '*', 'battle_sessions', '_autosave.json')) or glob.glob(os.path.join(base, '*', '*', 'battle_sessions', '_autosave.json'))
                    if hits:
                        d = os.path.dirname(hits[0])
                        found = (os.path.join(d, '_autosave.journal.jsonl'), hits[0])
                        break
        _gato_cache['files'] = found
        return found if found else (None, None)
def _read_last_json_line(path, tail_bytes=131072):
    try:
        with open(path, 'rb') as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(size - tail_bytes if size > tail_bytes else 0)
            chunk = f.read()
    except OSError:
        return None
    for part in reversed(chunk.decode('utf-8', 'replace').split('\n')):
        if part.strip():
            try:
                return json.loads(part)
            except ValueError:
                pass
def _gato_read_client():
    journal, _ = _gato_files()
    if journal is None:
        return
    else:
        obj = _read_last_json_line(journal)
        if not obj:
            return
        else:
            try:
                return obj['clients'][0]
            except (KeyError, IndexError, TypeError):
                return None
                return None
def _gato_read_deaths():
    c = _gato_read_client()
    if c is None:
        return
    else:
        bc = c.get('session', {}).get('battle_count', 0)
        cv = c.get('battle_history_compact_v2')
        deaths = cv.get('deaths') if isinstance(cv, dict) else None
        return (bc, deaths if deaths is not None else [])
def _gato_read_exp():
    # irreducible cflow, using cdg fallback
    # ***<module>._gato_read_exp: Failure: Compilation Error
    c = _gato_read_client()
    if c is None:
        return
    bc = c.get('session', {}).get('battle_count', 0)
    cv = c.get('battle_history_compact_v2')
    if not isinstance(cv, dict):
        return
    try:
        rows = cv.get('character_exp_rows')
        chars = cv.get('characters')
        if not rows or not chars:
            return None
        exp_row = rows[(-1)]
        names = [r[1] if isinstance(r, (list, tuple)) and len(r) > 1 else str(i) for i, r in enumerate(chars)]
        codes = [r[2] if isinstance(r, (list, tuple)) and len(r) > 2 else str(i) for i, r in enumerate(chars)]
        return (bc, exp_row, names, codes)
    except Exception:
        return None
def _r_death(h):
    h.click(557, 440)
def _r_friend(h):
    h.click(632, 426)
def _r_map(h):
    time.sleep(0.2)
    h.press('m')
def _r_bmode(h):
    time.sleep(0.2)
    h.press('a')
def _r_tban(h):
    time.sleep(0.2)
    h.press('x')
def _r_restart(h):
    h.click(466, 420)
REACTIONS = {'사망': (_r_death, 5.0, '부활 확인 클릭'), '친구 요청': (_r_friend, 3.0, '거절 클릭'), '지도 열림': (_r_map, 2.0, '지도 닫기 (M)'), 'B모드': (_r_bmode, 2.0, '전투모드 해제 (A)'), 'T밴(거래차단)': (_r_tban, 2.0, '거래차단 해제 (X)'), 'restart 팝업': (_r_restart, 2.0, '팝업 클릭')}
STOP_TRIGGERS = {'포만감 템 없음', '무게 꽉 참'}
NOTIFY_TRIGGERS = {'친구 요청'}
POPUP_CROP = (348, 322, 764, 452)
STOP_NOW_TRIGGERS = {'팅(시스템 팝업)'}
DIGIT_GUARD_SEC = 10.0
STOP_GRACE = 8.0
NO_BATTLE_LIMIT = 300
NO_FRAME_STOP_SEC = 3.0
JAMUN_INPUT_XY = (500, 425)
JAMUN_INPUT_ERROR_IDS = frozenset({'ttatta12', 'ttatta13'})
JAMUN_INPUT_CHARS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
def _jamun_submission_text(text: str, auth_id: str) -> str:
    if auth_id not in JAMUN_INPUT_ERROR_IDS or len(text) != 5 or any((ch not in JAMUN_INPUT_CHARS for ch in text)):
        return text
    else:
        if random.randrange(200) >= 6:
            return text
        else:
            pos = random.randrange(len(text))
            choices = JAMUN_INPUT_CHARS.replace(text[pos], '')
            return text[:pos] + random.choice(choices) + text[pos + 1:]
class BattleIO:
    def __init__(self, engine, hands):
        self._engine = engine
        self._hands = hands
    def capture(self):
        h = self._engine.hwnd
        frame = grab_hwnd(h) if h else grab_once()
        return frame if frame is not None else self._engine.snapshot()
    def capture_after(self, after, timeout=0.25, stop=None):
        h = self._engine.hwnd
        if not h:
            return
        else:
            return grab_hwnd_after(h, after, timeout=timeout, stop=stop)
    def press(self, name, hold=0.05):
        self._hands.press(name, hold, wait=True)
    def hold(self, name):
        self._hands.key_hold(name, wait=True)
    def release(self, name):
        self._hands.key_release(name, wait=True)
    def click(self, x, y, button='left'):
        self._hands.click(int(x), int(y), button, wait=True)
    def move(self, x, y):
        self._hands.move(int(x), int(y), wait=True)
class Brain:
    INTERVAL = 1.0 / 60.0   # loop pacing target; the loop actually waits for each NEW captured frame
    TICK_UNITS = 0.1        # old 10 Hz loop period: loop-count constants are kept in these units
    def __init__(self, engine, vision, hands, note=print, notify=None, notify_img=None, report_battle=None, report_appear=None, on_stopped=None, banja_ok=None, no_battle_limit=None, debug_jochul=None, debug_jamun=None, debug_jamun_wrong=None, auth_id=None):
        self.engine = engine
        self.vision = vision
        self.hands = hands
        self.note = note
        self._notify_push = notify or (lambda msg: None)
        self._notify_img = notify_img or (lambda msg, img: None)
        self._on_stopped = on_stopped or (lambda: None)
        self._report_battle = report_battle or (lambda: None)
        self._report_appear = report_appear or (lambda kind, wrong=False: None)
        self._banja_ok = banja_ok or (lambda: False)
        self._nb_limit = no_battle_limit or (lambda: 0)
        self._debug_jochul = debug_jochul
        self._debug_jamun = debug_jamun
        self._debug_jamun_wrong = debug_jamun_wrong or (lambda: None)
        self._auth_id = auth_id or (lambda: '')
        self.running = False
        self._thread = None
        self.monster = config.load().get('current_monster', config.DEFAULT_MONSTER)
        self.detector = None
        self.battle_detector = None
        self.aim_y = 30.0
        self.fire_roi = None
        self.trust_avoid = None
        self._react_at = {}
        self._battle_running = False
        self._battle_at = 0.0
        self._battle_click = 0
        self._digit_at = 0.0
        self._tab_at = 0.0
        self._battle_thread = None
        self._shutdown_at = None
        self._no_battle_count = 0
        self._sub_hands = {}
        self._sub_list = []
        self._sub_list_at = 0.0
        self._sub_sniff_prev = {}
        self._sub_solving = False
        self.rest_mode = False
        self.sched_target = None
        self._io = BattleIO(engine, hands)
        self.battle_count = self._load_count()
        self._prev_fired = set()
        self.jochul_solver = jochul.JochulSolver(config.JOCHUL_MODEL)
        self.text_reader = captcha.TextReader(config.TEXT_MODEL)
        self.solver_errors = {}
        self._solvers_loading = True
        self._jochul_at = 0.0
        self._jamun_at = 0.0
        self._solve_thread = None
        self._prev_main = None
        self._gm_at = 0.0
        self._kill_rank = []
        self._build_detectors()
        self._preload_async()
        self._preload_solvers()
        self._moved_at = time.time()
        self._afk_thread = None
        self.start_afk()
    # Anti-AFK (NATAS 2026-11-18, not vendor): 거상 drops to the menu after ~5 min without the
    # character moving; key presses don't count. Walk one step out with a right-click (the same
    # button the bot attacks with) and walk back. Runs whether or not the bot is started.
    AFK_SEC = 120.0
    AFK_STEP = 48
    def start_afk(self):
        if self._afk_thread and self._afk_thread.is_alive():
            return
        self._afk_thread = threading.Thread(target=self._afk_loop, daemon=True, name='prism-afk')
        self._afk_thread.start()
    def _afk_busy(self) -> bool:
        return bool(self._battle_running or self._sub_solving or (self._solve_thread and self._solve_thread.is_alive()))
    def _afk_loop(self):
        while True:
            time.sleep(5.0)
            try:
                self._ensure_window_visible()
                self._check_idle_warning()
                self._check_revive_popup()
                self._learn_mercs()
                if False and time.time() - max(self._moved_at, self._battle_at) >= self.AFK_SEC and not self._afk_busy():
                    # DISABLED (manager, 2026-11-19): confirmed live, twice,
                    # that this nudge's right-click reliably lands on a map
                    # hotspot at 초보자군영 that opens a REAL paid-travel
                    # confirmation ('무투장으로 이동하시겠습니까? 수수료는
                    # 10,000냥입니다.') instead of just walking. It did not
                    # self-confirm either time, but it reappears every AFK
                    # cycle and the risk of it ever being accidentally
                    # confirmed is not acceptable unattended. Do not
                    # re-enable until it uses a movement method proven not
                    # to open any dialog (e.g. keyboard-direction movement,
                    # or a per-call screenshot check that recognizes and
                    # safely cancels ANY dialog it causes) -- see also the
                    # reverted dismiss-click attempt earlier this session,
                    # which made the same dialog worse, not better.
                    self._afk_nudge()
            except Exception as e:
                self._log(f'[AFK] 오류: {type(e).__name__}: {e}')
                self._moved_at = time.time()
    def _ensure_window_visible(self):
        # Observed live 2026-11-18: after a Windows lock/unlock cycle the game
        # window can end up with WS_VISIBLE cleared even though the process
        # is alive and responding -- looks exactly like "the game quit" from
        # the user's side, but nothing crashed. Self-heal it here so an
        # unattended run doesn't sit invisible for hours.
        hwnd = find_window()
        if not hwnd:
            return
        if not win32gui.IsWindowVisible(hwnd):
            self._log('[AFK] 게임 창이 숨겨짐 감지 — 복구 시도')
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
            self._log('[AFK] 게임 창 복구 완료' if win32gui.IsWindowVisible(hwnd) else '[AFK] 게임 창 복구 실패 — 수동 확인 필요')
    def _check_idle_warning(self):
        # The real mechanism behind "game auto-returns to login screen when
        # idle" (confirmed live 2026-11-19): a '5분 뒤 캐릭터 선택 화면으로
        # 이동됩니다' dialog with a single 확인 button. Detecting and
        # clicking it is a left-click on one known, single-purpose button --
        # no movement, no risk of landing on a map hotspot or opening any
        # other menu, unlike the old right-click nudge.
        frame = self._grab_main()
        if frame is None:
            return
        pt = vis.find_idle_warning(frame)
        if pt is None:
            return
        self.hands.click(pt[0], pt[1], 'left', wait=True)
        time.sleep(0.5)
        self._moved_at = time.time()
        self._log('[AFK] 유휴 경고창 감지 — 확인 클릭')
    def _afk_nudge(self):
        before = self._grab_main()
        if before is None or vis.detect_scene(before) != 'main' or vis.check_triggers(before):
            return
        cx, cy = int(detector.CENTER[0]), int(detector.CENTER[1])
        self.hands.click(cx + self.AFK_STEP, cy, 'right', wait=True)
        time.sleep(1.5)
        after = self._grab_main()
        dx = dy = 0.0
        if after is not None:
            a = cv2.cvtColor(before[:vis.FIELD_H], cv2.COLOR_BGR2GRAY).astype(np.float32)
            b = cv2.cvtColor(after[:vis.FIELD_H], cv2.COLOR_BGR2GRAY).astype(np.float32)
            (dx, dy), _ = cv2.phaseCorrelate(a, b)
            lim = 2 * self.AFK_STEP
            dx = max(-lim, min(lim, dx))
            dy = max(-lim, min(lim, dy))
        # camera shift dx,dy: the spot we started on is now at center + shift (center if the camera is fixed)
        self.hands.click(int(round(cx + dx)), int(round(cy + dy)), 'right', wait=True)
        time.sleep(1.5)
        final = self._grab_main()
        if final is not None:
            self._prev_main = final[:vis.FIELD_H].copy()
        self._moved_at = time.time()
        self._log(f'[AFK] 캐릭터 이동 (화면 이동 {dx:+.0f},{dy:+.0f})')
        # NOTE (manager, 2026-11-19): tried adding an automatic "dismiss any
        # accidental menu" click here (left-click on own position) after a
        # right-click landed on a building and opened a context menu once.
        # Reverted immediately: that dismiss click itself triggered a SECOND
        # unintended menu (a paid 무투장 fast-travel confirmation, 10,000냥)
        # on a live run. A stray menu sitting open is a cosmetic/vision
        # annoyance; blindly clicking to "dismiss" risks confirming a real
        # paid action. Do not re-add this without a reliable way to
        # recognize and cancel the SPECIFIC dialog that appeared, not a
        # blind click-and-hope.
    def _log(self, msg: str):
        try:
            self.note(msg)
        except Exception:
            return None
    def _grab_main(self, normalize: bool=True):
        h = self.engine.hwnd
        if h and (not win32gui.IsWindow(h)):
                h = 0
        if h:
            return grab_hwnd(h, normalize=normalize)
        else:
            return grab_once(normalize=normalize)
    def _notify(self, msg: str):
        self._log(msg)
        try:
            self._notify_push(msg)
        except Exception:
            return None
    def _notify_popup(self, name: str):
        self._log(f'감지: {name}')
        img = self._grab_main()
        if img is not None:
            x0, y0, x1, y1 = POPUP_CROP
            h, w = img.shape[:2]
            if x1 <= w and y1 <= h:
                try:
                    self._notify_img(f'🔔 {name}', img[y0:y1, x0:x1])
                    return
                except Exception:
                    pass
        self._notify(f'🔔 {name}')
        return
    def _chat_state(self) -> str:
        f = self._grab_main()
        return vis.chat_hangul_state(f) if f is not None else 'inactive'
    def _type_tokens(self, text: str, gap: float=0.2):
        for shift, key in chat.to_tokens(text):
            if isinstance(key, int):
                self.hands.press_vk(key, shift=shift, wait=True)
            else:
                if shift:
                    self.hands.combo('shift', key, wait=True)
                else:
                    self.hands.press(key, wait=True)
            time.sleep(gap)
    def type_chat(self, text: str, pre_click=None):
        text = chat.filter_text(text)
        if not text:
            return
        else:
            if pre_click is not None:
                self.hands.click(*pre_click, wait=True)
                time.sleep(0.2)
            state = self._chat_state()
            for _ in range(2):
                if state != 'inactive':
                    break
                else:
                    self.hands.press('enter', wait=True)
                    time.sleep(0.25)
                    state = self._chat_state()
            if state == 'inactive':
                self._log('채팅창 활성화 실패 — 전송 취소')
            else:
                if state == 'english':
                    self.hands.toggle_hangul(wait=True)
                    time.sleep(0.2)
                self._type_tokens(text)
                self.hands.press('enter', wait=True)
                time.sleep(0.2)
                for _ in range(2):
                    if self._chat_state() == 'inactive':
                        return
                    else:
                        self.hands.press('enter', wait=True)
                        time.sleep(0.25)
    W_MEMO = (227, 693)
    W_TAB1 = (155, 126)
    W_TAB_DY = 18
    W_INPUT = (322, 284)
    W_BOX = (119, 95, 462, 297)
    def _whisper_open_now(self) -> bool:
        img = self._grab_main()
        return img is not None and vis.whisper_is_open(img)
    def _whisper_crop(self):
        img = self._grab_main()
        if img is None:
            return
        else:
            x1, y1, x2, y2 = self.W_BOX
            return img[y1:y2, x1:x2].copy()
    def _whisper_close(self):
        for _ in range(2):
            if not self._whisper_open_now():
                return
            else:
                self.hands.click(*self.W_MEMO, wait=True)
                time.sleep(0.3)
        if self._whisper_open_now():
            self._log('⚠ 귓말창 닫힘 확인 실패')
            self._notify('귓말창이 닫히지 않았습니다 — 화면 확인 필요')
    def send_whisper(self, slot: int, msg: str):
        msg = chat.filter_text(msg)
        if not msg:
            return
        if not self._whisper_open_now():
            self.hands.click(*self.W_MEMO, wait=True)
            time.sleep(0.8)
            if not self._whisper_open_now():
                self._notify_img('귓말창 열기 실패 — 현재 화면 첨부', self._grab_main())
                self._whisper_close()
                return
        self.hands.click(self.W_TAB1[0], self.W_TAB1[1] + (slot - 1) * self.W_TAB_DY, wait=True)
        time.sleep(0.15)
        self.hands.click(*self.W_INPUT, wait=True)
        time.sleep(0.15)
        state = self._chat_state()
        if state == 'inactive':
            crop = self._whisper_crop()
            self._whisper_close()
            self._notify_img(f'귓말{slot} 대상이 없습니다', crop)
        else:
            if state == 'english':
                self.hands.toggle_hangul(wait=True)
                time.sleep(0.2)
            self._type_tokens(msg, gap=0.05)
            self.hands.press('enter', wait=True)
            time.sleep(0.15)
            crop = self._whisper_crop()
            for _ in range(2):
                if self._chat_state() == 'inactive':
                    break
                else:
                    self.hands.press('enter', wait=True)
                    time.sleep(0.2)
            self._whisper_close()
            self._notify_img(f'📨 귓말{slot} 전송: {msg}', crop)
    def _check_scene_change(self):
        frame = self._grab_main()
        if frame is None:
            return
        else:
            field = frame[:vis.FIELD_H].copy()
            if self._prev_main is not None:
                sim = vis.scene_similarity(self._prev_main, field)
                if sim < vis.SCENE_SIM_THRESH:
                    stop = not self.ignore_teleport
                    msg = f'⚠ 배경 급변 (유사도 {sim:.2f}) — 맵 이동/영자 소환 의심' + ('' if stop else ' (이동 잦은 몹 — 정지 안 함)')
                    self._log(msg)
                    self._notify_img(msg, frame)
                    if stop and self._shutdown_at is None:
                            self._shutdown_at = time.time() + STOP_GRACE
                else:
                    self._log(f'배경 유사도 {sim:.2f}')
            self._prev_main = field
    SUB_TRIGGERS = {'사망', '포만감 템 없음'}
    SUB_MAIN_WAIT = 120.0
    def _sub_hands_for(self, hwnd: int, tag: str) -> Hands:
        self._sub_hands = {h: v for h, v in self._sub_hands.items() if win32gui.IsWindow(h)}
        if not hasattr(self, '_sub_tag'):
            self._sub_tag = {}
        self._sub_tag[hwnd] = tag
        hands = self._sub_hands.get(hwnd)
        if hands is None:
            hands = Hands(hwnd_get=lambda h=hwnd: h, log=lambda s, h_=hwnd: self._log(f"[{self._sub_tag.get(h_, '서브창')}] {s}"))
            self._sub_hands[hwnd] = hands
        return hands
    def _check_sub_windows(self):
        try:
            main = self.engine.hwnd
            subs = [h for h in find_windows() if h != main][:2]
        except Exception:
            return None
        if len(subs) != getattr(self, '_sub_n', (-1)):
            self._sub_n = len(subs)
            if subs:
                self._log(f'서브 거상 창 {len(subs)}개 점검 대상')
        if not subs:
            return
        else:
            for i, hwnd in enumerate(subs, 1):
                if win32gui.IsIconic(hwnd):
                    self._log(f'[서브창{i}] 최소화 상태 → 복원 (포커스 안 뺏음)')
                    try:
                        win32gui.ShowWindow(hwnd, win32con.SW_SHOWNOACTIVATE)
                    except Exception:
                        pass
                    time.sleep(0.3)
            deadline = time.time() + self.SUB_MAIN_WAIT
            waiting = list(subs)
            logged = False
            while waiting and self.running and (time.time() < deadline):
                        waiting = [h for h in waiting if win32gui.IsWindow(h) and (not combat.is_main(grab_hwnd(h)))]
                        if waiting:
                            if not logged:
                                logged = True
                                self._log(f'서브창 {len(waiting)}개 메인 복귀 대기…')
                            time.sleep(0.2)
            for h in waiting:
                self._log(f'[서브창{subs.index(h) + 1}] {self.SUB_MAIN_WAIT:.0f}초 내 메인 미복귀 — 그냥 진행')
            for i, hwnd in enumerate(subs, 1):
                try:
                    l, t, r_, b = win32gui.GetClientRect(hwnd)
                    if (r_ - l, b - t) != (1024, 768) and hwnd not in getattr(self, '_sub_res_warned', set()):
                            self._sub_res_warned = getattr(self, '_sub_res_warned', set())
                            self._sub_res_warned.add(hwnd)
                            self._notify(f'⚠️ 서브창{i} 해상도 {r_ - l}×{b - t} — 기준 1024×768이 아니라 포만감/사망 판정 불가')
                except Exception:
                    pass
                img = grab_hwnd(hwnd)
                if img is None:
                    self._log(f'[서브창{i}] 캡처 실패 — 점검 스킵')
                    continue
                else:
                    fired = vis.check_triggers(img)
                    tag = f'서브창{i}'
                    if fired & self.SUB_TRIGGERS:
                        hands = self._sub_hands_for(hwnd, tag)
                        if '사망' in fired:
                            self._log(f'[{tag}] 사망 감지 → 부활 + 불사신부')
                            hands.move(557, 440, wait=True)
                            time.sleep(0.3)
                            hands.click(557, 440, wait=True)
                    if self._sub_solving:
                        continue
                    else:
                        if '조철 출현' in fired:
                            self._handle_jochul(hands=self._sub_hands_for(hwnd, tag), hwnd=hwnd, tag=tag, park=False)
                        else:
                            if '자방문 출현' in fired:
                                self._handle_jamun(hands=self._sub_hands_for(hwnd, tag), hwnd=hwnd, tag=tag)
            if subs:
                self._focus_main()
    def _focus_main(self):
        try:
            self.hands.move(*combat.FIELD_CENTER, wait=True)
        except Exception:
            return None
    def _retreat_subs(self):
        try:
            main = self.engine.hwnd
            subs = [h for h in find_windows() if h != main][:2]
        except Exception:
            return None
        for i, hwnd in enumerate(subs, 1):
            img = grab_hwnd(hwnd)
            if img is None or not combat.is_battle(img):
                continue
            else:
                tag = f'서브창{i}'
                self._log(f'[{tag}] 전투화면 → 퇴각')
                hands = self._sub_hands_for(hwnd, tag)
                hands.move(*combat.FIELD_CENTER, wait=True)
                time.sleep(0.3)
                for _ in range(3):
                    hands.press('esc', wait=True)
                    time.sleep(0.05)
    def _banja_sub_entry(self):
        try:
            main = self.engine.hwnd
            subs = [h for h in find_windows() if h != main][:2]
        except Exception:
            return None
        pressed = False
        for i, hwnd in enumerate(subs, 1):
            tag = f'서브창{i}'
            deadline = time.time() + self.BANJA_SUB_BATTLE_WAIT
            in_battle = False
            while time.time() < deadline and self.running:
                    img = grab_hwnd(hwnd)
                    if img is not None and combat.is_battle(img):
                            in_battle = True
                            break
                    time.sleep(0.3)
            if not in_battle:
                self._log(f'[{tag}] 전투화면 아님 — E 스킵')
                continue
            else:
                self._log(f'[{tag}] 전투화면 확인 → E')
                hands = self._sub_hands_for(hwnd, tag)
                hands.move(*combat.FIELD_CENTER, wait=True)
                time.sleep(0.3)
                hands.press('e', wait=True)
                pressed = True
        if pressed:
            self._focus_main()
    SUB_SNIFF_REFRESH = 3.0
    _SNIFF_TRIGGERS = ('조철 출현', '자방문 출현')
    def _sniff_subs(self):
        now = time.time()
        if now - self._sub_list_at >= self.SUB_SNIFF_REFRESH:
            self._sub_list_at = now
            try:
                main = self.engine.hwnd
                self._sub_list = [h for h in find_windows() if h != main][:2]
            except Exception:
                self._sub_list = []
        if not self._sub_list:
            return
        else:
            cur = {}
            for i, hwnd in enumerate(self._sub_list, 1):
                fired = set()
                for name in self._SNIFF_TRIGGERS:
                    regions = vis.TRIGGERS[name]
                    bx0 = min((r[0] for r in regions))
                    by0 = min((r[1] for r in regions))
                    bx1 = max((r[2] for r in regions))
                    by1 = max((r[3] for r in regions))
                    patch = grab_hwnd_region(hwnd, bx0, by0, bx1, by1)
                    if patch is None:
                        break
                    else:
                        if all((int(patch[y0 - by0:y1 - by0, x0 - bx0:x1 - bx0].sum()) == s for x0, y0, x1, y1, s in regions)):
                            fired.add(name)
                new = fired - self._sub_sniff_prev.get(hwnd, set())
                held = set()
                for trig, kind in [('조철 출현', 'jochul'), ('자방문 출현', 'jamun')]:
                    if trig in new and (not self._start_sub_solve(hwnd, i, kind)):
                            held.add(trig)
                cur[hwnd] = fired - held
            self._sub_sniff_prev = cur
    def _start_sub_solve(self, hwnd: int, idx: int, kind: str) -> bool:
        if self._sub_solving or self._shutdown_at is not None or self._battle_running:
            return False
        else:
            tag = f'서브창{idx}'
            self._sub_solving = True
            self._log(f"[{tag}] {('조철' if kind == 'jochul' else '자방문')} 출현 감지")
            def _worker():
                try:
                    hands = self._sub_hands_for(hwnd, tag)
                    if kind == 'jochul':
                        self._handle_jochul(hands=hands, hwnd=hwnd, tag=tag, park=False)
                    else:
                        self._handle_jamun(hands=hands, hwnd=hwnd, tag=tag)
                except Exception as e:
                    self._log(f'[{tag}] 풀이 오류: {e}')
                finally:
                    self._focus_main()
                    self._sub_solving = False
            threading.Thread(target=_worker, daemon=True).start()
            return True
    def gato_detected(self) -> bool:
        now = time.time()
        if now - getattr(self, '_gato_pid_at', 0.0) < 3.0:
            return getattr(self, '_gato_pid_cached', False)
        else:
            self._gato_pid_at = now
            try:
                self._gato_pid_cached = _pid_by_exe(_GATO_EXE) is not None
            except Exception:
                self._gato_pid_cached = False
            return self._gato_pid_cached
    def _check_revive_popup(self) -> bool:
        """Click 확인 on the 불사신부 popup (a merc or the character died). Never clicks an
        unrecognised confirm dialog; saves it to debug/dialog_unknown instead."""
        frame = self._grab_main()
        if frame is None:
            return False
        found = vis.find_revive_popup(frame)
        if found is None:
            return False
        kind, pt = found
        if kind == 'unknown':
            if time.time() - getattr(self, '_unk_dlg_at', 0.0) >= 60.0:
                self._unk_dlg_at = time.time()
                try:
                    d = os.path.join(config.BASE_DIR, 'debug', 'dialog_unknown')
                    os.makedirs(d, exist_ok=True)
                    if len(os.listdir(d)) < 20:
                        cv2.imwrite(os.path.join(d, time.strftime('%H%M%S') + '.png'), frame)
                except Exception:
                    pass
                self._log('[팝업] 확인/취소 팝업 문구 불일치 — 클릭 안 함 (debug/dialog_unknown 저장)')
            return False
        clicks = [t for t in getattr(self, '_revive_clicks', []) if time.time() - t < 10.0]
        if len(clicks) >= 3:
            return False
        clicks.append(time.time())
        self._revive_clicks = clicks
        self.hands.click(pt[0], pt[1], 'left', wait=True)
        time.sleep(0.6)
        self._moved_at = time.time()
        self._log('[부활] 불사신부 사용 팝업 — 확인 클릭')
        return True
    def _delayed_merc_check(self):
        time.sleep(1.0)
        self._check_revive_popup()
        ui_ok = self._check_merc_deaths_ui()
        prev_bc = getattr(self, '_gato_bc', None)
        deadline = time.time() + 30.0
        advanced_at = None
        while time.time() < deadline:
            snap = _gato_read_deaths()
            if snap is not None and (prev_bc is None or snap[0] != prev_bc):
                    self._gato_bc = snap[0]
                    if advanced_at is None:
                        advanced_at = time.time()
                    if not ui_ok:
                        self._check_merc_deaths()
                    self._check_merc_exp()
                    if time.time() - advanced_at >= 2.0:
                        return
            time.sleep(0.3)
        if not ui_ok:
            self._check_merc_deaths()
        self._check_merc_exp()
    def _check_merc_deaths(self):
        snap = _gato_read_deaths()
        if snap is None:
            self._gato_fail = getattr(self, '_gato_fail', 0) + 1
            if self._gato_fail == 3 and (not getattr(self, '_gato_warned', False)):
                    self._gato_warned = True
                    self._log('[용병감시] 고트(고상 트레이더스) 미실행 — 사망 자동부활 비활성')
            return None
        else:
            self._gato_fail = 0
            self._gato_warned = False
            bc, deaths = snap
            key = (deaths[(-1)][0], tuple(deaths[(-1)][1])) if deaths else None
            prev = getattr(self, '_gato_death_key', '__UNSET__')
            if prev == '__UNSET__':
                self._gato_death_key = key
                return
            else:
                if key == prev:
                    return
                else:
                    self._gato_death_key = key
                    if key is None:
                        return
                    else:
                        frame = self._grab_main()
                        if frame is None or not combat.is_main(frame):
                            self._gato_death_key = prev
                            return
                        else:
                            self._log(f'[용병] 고트 기록상 사망 전투#{key[0]} — 화면에서 확인 후에만 부활')
                            self._revive_dead_mercs(frame)
    def _check_merc_deaths_ui(self) -> bool:
        try:
            import traders_ctl
            dead = traders_ctl.dead_characters()
        except Exception:
            return False
        if dead is None:
            return False
        else:
            if not dead:
                return True
            else:
                frame = self._grab_main()
                if frame is None or not combat.is_main(frame):
                    return True
                else:
                    self._log(f"[용병] 고트 UI상 사망 {', '.join(sorted(dead))} — 화면에서 확인 후에만 부활")
                    self._revive_dead_mercs(frame)
                    return True
    _EXP_TIERS_OFF = (20, 30, 35, 40, 45, 50, 55)
    _EXP_TIERS_ON = (23, 33, 38, 43, 48, 53, 58)
    _EXP_TIER_TOL = 0.4
    def _check_merc_exp(self) -> None:
        snap = _gato_read_exp()
        if snap is None:
            return
        bc, exp_row, names, codes = snap
        prev = getattr(self, '_exp_bc', None)
        if prev is not None:
            if bc == prev:
                return
            if bc < prev:
                self._exp_stats = {}
                self._exp_bc = bc
                self._push_kill_rank()
                return
        vals = [v for v in exp_row if isinstance(v, (int, float)) and v > 0]
        if not vals:
            self._exp_bc = bc
            return
        else:
            mode = max(set(vals), key=vals.count)
            if mode <= 0:
                self._exp_bc = bc
                return
            else:
                base_pct = None
                for base in [self._EXP_TIERS_ON, self._EXP_TIERS_OFF]:
                    unit = mode / base[0]
                    hits = sum((1 for g in vals if min((abs(g / unit - t) for t in base)) <= self._EXP_TIER_TOL))
                    if base_pct is None or hits > base_pct[0]:
                        base_pct = (hits, base[0])
                base_pct = base_pct[1]
                stats = getattr(self, '_exp_stats', None)
                if stats is None:
                    stats = self._exp_stats = {}
                for i, gained in enumerate(exp_row):
                    if not isinstance(gained, (int, float)) or gained <= 0:
                        continue
                    else:
                        code = codes[i] if i < len(codes) else str(i)
                        nm = names[i] if i < len(names) else str(i)
                        extra = max(0.0, gained - mode)
                        st = stats.setdefault(code, {'name': nm, 'extra': 0.0, 'battles': 0, 'tier': base_pct})
                        st['name'] = nm
                        st['tier'] = base_pct
                        st['extra'] += extra
                        st['battles'] += 1
                self._exp_bc = bc
                self._push_kill_rank()
    def _push_kill_rank(self) -> None:
        stats = getattr(self, '_exp_stats', None) or {}
        total = sum((st['extra'] for st in stats.values()))
        rows = []
        for code, st in stats.items():
            share = st['extra'] / total * 100 if total > 0 else 0.0
            rows.append({'name': st['name'], 'share': round(share, 2), 'extra': round(st['extra']), 'battles': st['battles'], 'tier': round(st.get('tier', 0))})
        rows.sort(key=lambda r: r['share'], reverse=True)
        self._kill_rank = rows
    def get_kill_rank(self) -> list:
        return getattr(self, '_kill_rank', [])
    def _stop_bot(self, reason: str=''):
        if self._shutdown_at is not None:
            return
        else:
            self._shutdown_at = time.time() + STOP_GRACE
            if reason:
                self._notify(f'{reason} — {STOP_GRACE:.0f}초 후 정지')
    def _stop_now(self, reason: str=''):
        self._shutdown_at = None
        self.running = False
        if reason:
            self._notify(f'{reason} — 즉시 종료')
    _restock_in_progress = False
    def _try_autorestock(self, stop_hit: set) -> bool:
        """Returns True if a restock attempt was launched (caller should NOT
        also stop the bot), False if autosupply is disabled/uncalibrated
        (caller falls back to the existing stop-the-bot behavior unchanged).
        Runs in its own thread so travel/shop clicks (which take real
        seconds) don't block the vision loop that keeps checking for the
        instant-kill trigger (팅) while restock plays out."""
        import config
        import autosupply
        if not config.auto_restock_enabled() or self._restock_in_progress:
            return False
        if not autosupply.load_route(f'{self.monster}:to_town') or not autosupply.load_route(f'{self.monster}:to_hunt'):
            return False
        reason = ', '.join(sorted(stop_hit))
        self._restock_in_progress = True
        self._notify(f'{reason} — 자동 보충 시작')
        def _run():
            try:
                autosupply.run_restock(self, reason)
            except Exception as e:
                self._log(f'[자동보충] 오류: {e} — 수동으로 확인하세요')
                self._notify(f'자동 보충 실패: {e}')
            finally:
                self._restock_in_progress = False
        threading.Thread(target=_run, daemon=True).start()
        return True
    @staticmethod
    def _load_count() -> int:
        # irreducible cflow, using cdg fallback
        # ***<module>.Brain._load_count: Failure: Compilation Error
        try:
            with open(config.BATTLE_COUNT_PATH, encoding='ascii') as f:
                return max(0, int(f.read().strip()))
        except Exception:
            return 0
    def _save_count(self) -> None:
        # irreducible cflow, using cdg fallback
        # ***<module>.Brain._save_count: Failure: Compilation Error
        try:
            with open(config.BATTLE_COUNT_PATH, 'w', encoding='ascii') as f:
                f.write(str(self.battle_count))
        except Exception:
            return None
    def reset_count(self) -> None:
        self.battle_count = 0
        self._save_count()
        try:
            if os.path.exists(config.APPEAR_PATH):
                os.remove(config.APPEAR_PATH)
        except Exception:
            pass
        self._exp_stats = {}
        self._exp_bc = None
        self._push_kill_rank()
        self._log('전투 횟수 · 출현 기록 초기화')
    def _record_appear(self, kind: str) -> None:
        line = f'{datetime.now():%Y-%m-%d %H:%M:%S} {kind} — 전투 {self.battle_count}회'
        try:
            with open(config.APPEAR_PATH, 'a', encoding='utf-8') as f:
                f.write(line + '\n')
        except Exception:
            pass
        self._report_appear({'조철': 'jochul', '자방문': 'jamun'}.get(kind, kind))
        self._log(f'{kind} 출현 — 전투 {self.battle_count}회 (기록)')
    def get_appear_records(self) -> list:
        out = []
        try:
            with open(config.APPEAR_PATH, encoding='utf-8') as f:
                for line in f:
                    m = re.match('(\\S+ \\S+) (\\S+) — 전투 (\\d+)회', line.strip())
                    if m:
                        out.append({'time': m.group(1), 'kind': m.group(2), 'count': int(m.group(3))})
        except Exception:
            pass
        return out
    def start(self):
        if self.running:
            return
        else:
            self.running = False
            self.hands.clear_pending()
            if self._thread and self._thread.is_alive():
                    self._thread.join(timeout=2.0)
            if self._battle_thread and self._battle_thread.is_alive():
                    self._battle_thread.join(timeout=5.0)
            if self._solve_thread and self._solve_thread.is_alive():
                    self._solve_thread.join(timeout=16.0)
            self._battle_thread = None
            self._solve_thread = None
            self._battle_running = False
            self.hands.release_all()
            new_monster = config.load().get('current_monster', config.DEFAULT_MONSTER)
            if new_monster != self.monster:
                self.monster = new_monster
                self._build_detectors()
                self._preload_async()
            self._battle_click = 1
            self._battle_at = 0.0
            self._digit_at = 0.0
            self._shutdown_at = None
            self._no_battle_count = 0
            self.rest_mode = False
            self.sched_target = None
            f0 = self._grab_main()
            self._prev_main = f0[:vis.FIELD_H].copy() if f0 is not None else None
            self.hands.guard_enabled = True
            self.running = True
            self._thread = threading.Thread(target=self._loop, daemon=True, name='prism-brain')
            self._thread.start()
    def stop(self):
        self.running = False
        self.hands.guard_enabled = False
        self.rest_mode = False
        self.sched_target = None
        self.hands.clear_pending()
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None
        if self._battle_thread:
            self._battle_thread.join(timeout=5.0)
            self._battle_thread = None
        if self._solve_thread:
            self._solve_thread.join(timeout=16.0)
            self._solve_thread = None
        self._battle_running = False
        self.hands.release_all()
    def _build_detectors(self):
        # ***<module>.Brain._build_detectors: Failure: Different control flow
        mp = config.mob_model_path(self.monster)
        self.aim_y = config.mob_aim_y(self.monster)
        self.fire_roi = config.mob_fire_roi(self.monster)
        self.fire_rect = config.mob_fire_rect(self.monster)
        self.trust_avoid = config.mob_trust_avoid(self.monster)
        self.ignore_dummy = config.mob_ignore_dummy(self.monster)
        self.box_click = config.mob_box_click(self.monster)
        self.ignore_teleport = config.mob_ignore_teleport(self.monster)
        self._stop_triggers = STOP_TRIGGERS - {'무게 꽉 참'} if config.mob_ignore_weight(self.monster) else STOP_TRIGGERS
        sprite = config.mob_sprite(self.monster)
        if sprite:
            self.detector = detector.SpriteDetector(sprite)
        else:
            self.detector = detector.MobDetector(mp, conf=config.mob_conf(self.monster), classes=('mob',), avoid_conf=config.mob_avoid_conf(self.monster)) if mp else None
        self.battle_detector = None
        self.boss_detector = None
        if config.mob_boss(self.monster) and mp:   # decompile had `not boss or mp`
                self.boss_detector = detector.MobDetector(mp, conf=config.mob_boss_conf(self.monster), classes=('mob', 'avoid'))
    def _model_env(self, path: str='') -> str:
        out = []
        try:
            out.append(f'win={platform.win32_ver()[0]}/{platform.win32_ver()[1]}')
            out.append(f'py={platform.python_version()}')
        except Exception:
            pass
        try:
            import torch
            out.append(f'torch={torch.__version__}')
        except Exception as e:
            out.append(f'torch=X({type(e).__name__})')
        if path:
            try:
                out.append(f'file={os.path.basename(path)}:' + (str(os.path.getsize(path)) if os.path.exists(path) else '없음'))
            except Exception:
                pass
        try:
            class _MS(ctypes.Structure):
                _fields_ = [('dwLength', ctypes.c_ulong), ('dwMemoryLoad', ctypes.c_ulong), ('ullTotalPhys', ctypes.c_ulonglong), ('ullAvailPhys', ctypes.c_ulonglong), ('ullTotalPageFile', ctypes.c_ulonglong), ('ullAvailPageFile', ctypes.c_ulonglong), ('ullTotalVirtual', ctypes.c_ulonglong), ('ullAvailVirtual', ctypes.c_ulonglong), ('ullAvailExtendedVirtual', ctypes.c_ulonglong)]
            ms = _MS()
            ms.dwLength = ctypes.sizeof(_MS)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(ms))
            out.append(f'ram={ms.ullAvailPhys // 1048576}/{ms.ullTotalPhys // 1048576}MB')
        except Exception:
            pass
        return ' · '.join(out)
    def _model_fail(self, tag: str, path: str=''):
        e = sys.exc_info()[1]
        self._log(f'❌ {tag} 모델 로드 실패: {type(e).__name__}: {e}')
        self._log(f'   환경 — {self._model_env(path)}')
    def _preload_async(self):
        det, bdet = (self.detector, self.boss_detector)
        def _preload():
            for d, tag in [(det, '색적'), (bdet, 'boss')]:
                if d is None:
                    self._log(f'{tag} 모델 미지정 — 스킵')
                else:
                    try:
                        d.preload()
                        self._log(f'[{self.monster}] {tag} 모델 로드 완료')
                    except Exception:
                        self._model_fail(tag, getattr(d, 'model_path', ''))
        threading.Thread(target=_preload, daemon=True).start()
    def _preload_solvers(self):
        def _load():
            try:
                for s, tag in self._solvers():
                    try:
                        s.preload()
                        self._log(f'{tag} 모델 로드 완료')
                    except Exception as e:
                        self.solver_errors[tag] = f'{type(e).__name__}: {e}'
                        self._model_fail(tag, getattr(s, 'model_path', '') or getattr(s, 'ckpt_path', ''))
            finally:
                self._solvers_loading = False
        self._solvers_loading = True
        self.solver_errors = {}
        threading.Thread(target=_load, daemon=True).start()
    def _solvers(self):
        return ((self.jochul_solver, '조철'), (self.text_reader, '자방문'))
    def start_block_reason(self) -> str:
        pending = [tag for s, tag in self._solvers() if not getattr(s, 'ready', False)]
        if not pending:
            return ''
        else:
            failed = [f'{t}({self.solver_errors[t]})' for t in pending if t in self.solver_errors]
            if failed:
                return '모델 로드 실패 — ' + ', '.join(failed)
            else:
                if self._solvers_loading:
                    return f"{'·'.join(pending)} 모델 로딩 중 — 잠시 후 다시 시도하세요"
                else:
                    return f"{'·'.join(pending)} 모델 미로드"
    def _restart_relic_map(self):
        # ***<module>.Brain._restart_relic_map: Failure: Different control flow
        target = {'유물지도': (432, 444), '유물지도(정예)': (432, 324)}[self.monster]
        if not self.hands.click(466, 420, wait=True):
            return
        else:
            time.sleep(0.8)
            if self.running and self._shutdown_at is not None:
                return None
            else:
                if self.hands.click(*target, button='left', wait=True):
                    self._log(f'{self.monster}: 다시하기 후 이동 {target}')
    def _close_stray_window(self, img, scene, fired) -> bool:
        """A window the macro did not open (the 용병 가방/status window from a portrait click)
        hides the main HUD, the scene reads 'unknown' and nothing works. Close it with Esc
        (then the 창닫기 button). True = a window is up, skip everything else this pass."""
        if self._battle_running or self._sub_solving or getattr(self, '_macro_inv', False):
            self._unk_since = 0.0
            return False
        now = time.time()
        stray = vis.inventory_open(img)
        if not stray:
            if scene == 'unknown' and not fired:
                if not getattr(self, '_unk_since', 0.0):
                    self._unk_since = now
                stray = now - self._unk_since >= 3.0
            else:
                self._unk_since = 0.0
        if not stray:
            self._stray_tries = 0
            return False
        if now - getattr(self, '_esc_at', 0.0) < 0.9:
            return True
        self._esc_at = now
        self._stray_tries = getattr(self, '_stray_tries', 0) + 1
        if self._stray_tries > 6:
            if self._stray_tries == 7:
                self._log('[창] 닫히지 않는 창 — 수동 확인 필요')
            return True
        if self._stray_tries % 3 == 0 and vis.inventory_open(img):
            self._log('[창] 창닫기 클릭')
            self.hands.click(730, 543, 'left', wait=True)
        else:
            self._log('[창] 예상치 못한 창 열림 — Esc로 닫음')
            self.hands.press('esc', hold=0.08, wait=True)
        return True
    def _park_cursor(self):
        self.hands.move(730, 580, wait=True)   # below the 가방 window: hover only, no tooltip over the cells
        time.sleep(0.35)
    def _close_inventory(self) -> bool:
        for attempt in range(3):
            f = self._grab_main()
            if f is not None and not vis.inventory_open(f):
                return True
            if attempt == 0:
                self.hands.press('i', hold=0.12, wait=True)
            else:
                self.hands.click(730, 543, 'left', wait=True)   # 창닫기
            time.sleep(0.7)
        f = self._grab_main()
        ok = f is not None and not vis.inventory_open(f)
        if not ok:
            self._log('[포만감] 가방 창 닫기 실패 — 수동 확인 필요')
        return ok
    def _eat_to_full(self) -> bool:
        """Open 가방, right-click row 1 / column 2 (궁중 타락죽) until the gauge is full, close 가방."""
        self._macro_inv = True
        try:
            return self._eat_to_full_inner()
        finally:
            self._macro_inv = False
    def _eat_to_full_inner(self) -> bool:
        f = self._grab_main()
        if f is None or vis.chat_hangul_state(f) != 'inactive':
            return False
        start = vis.food_fraction(f)
        if start is None:
            return False
        if not vis.inventory_open(f):
            for _ in range(2):
                self.hands.press('i', hold=0.12, wait=True)
                time.sleep(0.8)
                f = self._grab_main()
                if f is not None and vis.inventory_open(f):
                    break
            else:
                self._log('[포만감] 가방 열기 실패 — 먹지 않음')
                return False
        self._park_cursor()
        f = self._grab_main()
        if f is None or not vis.porridge_in_r1c2(f):
            self._log('[포만감] 가방 1행 2열이 궁중 타락죽이 아님 — 아무것도 누르지 않음')
            self._close_inventory()
            return False
        prev, stalls, eaten = start, 0, 0
        why = '최대'
        for _ in range(16):
            if not self.running:
                why = '정지'
                break
            self.hands.click(vis.INV_CELL_R1C2[0], vis.INV_CELL_R1C2[1], 'right', wait=True)
            eaten += 1
            time.sleep(0.5)
            self._park_cursor()
            f = self._grab_main()
            frac = vis.food_fraction(f) if f is not None else None
            if frac is None:
                why = '게이지 확인불가'
                break
            if frac >= 0.93:
                break
            if not vis.porridge_in_r1c2(f):
                why = '궁중 타락죽 소진'
                break
            if frac <= prev + 0.01:
                stalls += 1
                if stalls >= 2:
                    why = '게이지가 늘지 않음'
                    break
            else:
                stalls = 0
            prev = frac
        self._close_inventory()
        end = vis.food_fraction(self._grab_main())
        fmt = lambda v: 'n/a' if v is None else f'{v * 100:.0f}%'
        self._log(f'[포만감] 궁중 타락죽 {eaten}개 사용: {fmt(start)} → {fmt(end)} ({why})')
        return True
    _MERC_FILE = os.path.join(config.BASE_DIR, 'merc_slots.json')
    def _merc_occupied(self) -> set:
        occ = self.__dict__.get('_merc_occ')
        if occ is None:
            try:
                with open(self._MERC_FILE, encoding='utf-8') as f:
                    occ = {int(x) for x in json.load(f)}
            except Exception:
                occ = set()
            self._merc_occ = occ
        return occ
    def _learn_mercs(self) -> None:
        if self._battle_running or getattr(self, '_macro_inv', False):
            return
        f = self._grab_main()
        if f is not None and vis.detect_scene(f) == 'main' and not vis.inventory_open(f):
            self._update_merc_baseline(f)
    def _update_merc_baseline(self, frame) -> None:
        """Remember which portrait slots held a live unit (persisted, so a restart with a dead
        merc already on screen still knows that slot is occupied)."""
        occ = self._merc_occupied()
        new = set(vis.merc_alive_slots(frame)) - occ
        if new:
            occ |= new
            try:
                with open(self._MERC_FILE, 'w', encoding='utf-8') as f:
                    json.dump(sorted(occ), f)
            except Exception:
                pass
    def _revive_dead_mercs(self, frame) -> bool:
        """A 용병 is dead when its portrait shows neither an HP nor a mana gauge. One Alt+1 revives
        every dead unit at once; Alt+2 is pressed (once) only if one is still dead afterwards.
        Confirmed on two frames 0.4 s apart; every press is logged and a frame saved."""
        if frame is None:
            return False
        occ = self._merc_occupied()
        dead = vis.dead_mercs_v2(frame, occ)
        if not dead:
            return False
        now = time.time()
        if now - getattr(self, '_revive_at', 0.0) < 6.0:
            return False
        time.sleep(0.4)
        fresh = self._grab_main()
        again = vis.dead_mercs_v2(fresh, occ) if fresh is not None else []
        dead = [d for d in dead if d in again]
        if not dead:
            return False
        if getattr(self, '_revive_fail', 0) >= 3 and now - getattr(self, '_revive_at', 0.0) < 300.0:
            if now - getattr(self, '_revive_cap_log', 0.0) > 120.0:
                self._revive_cap_log = now
                self._log(f'[용병] 죽은 용병 {dead} — Alt 부활이 3회 연속 실패, 5분 쉼 (반계탕 확인)')
            return False
        self._revive_at = now
        self._log(f'[용병] 죽은 용병 슬롯 {dead} — Alt+1 한 번으로 전원 부활 시도')
        try:
            d = os.path.join(config.BASE_DIR, 'debug', 'revive')
            os.makedirs(d, exist_ok=True)
            if len(os.listdir(d)) < 30:
                cv2.imwrite(os.path.join(d, time.strftime('%H%M%S') + '.png'), fresh)
        except Exception:
            pass
        self.hands.combo('alt', '1', wait=True)
        time.sleep(1.5)
        left = vis.dead_mercs_v2(self._grab_main(), occ)
        if left:
            self._log(f'[용병] Alt+1 후에도 사망 슬롯 {left} — Alt+2 한 번')
            self.hands.combo('alt', '2', wait=True)
            time.sleep(1.5)
            left = vis.dead_mercs_v2(self._grab_main(), occ)
        self._revive_fail = (getattr(self, '_revive_fail', 0) + 1) if left else 0
        self._log('[용병] 부활 후 남은 사망 슬롯: ' + (str(left) if left else '없음'))
        return True
    def _prefight(self, frame) -> bool:
        """Everything that must be true right before a fight. True = a long action ran, so the
        caller should re-detect the mob instead of clicking a stale position."""
        cfg = config.load()
        if frame is None:
            return False
        self._update_merc_baseline(frame)
        if cfg.get('prefight_revive', True) and self._revive_dead_mercs(frame):
            return True
        if cfg.get('prefight_food', True):
            frac = vis.food_fraction(frame)
            if frac is not None and frac < vis.FOOD_LOW_FRAC and time.time() - getattr(self, '_eat_at', 0.0) > 30.0:
                self._eat_at = time.time()
                self._log(f'[포만감] {frac * 100:.0f}% (1/5 미만) — 궁중 타락죽으로 채움')
                if self._eat_to_full():
                    return True
        self._ensure_battle_modes(frame)
        return False
    # 전투모드 (hotkey A) and 거래차단 (hotkey X) indicator signatures, measured live on a native
    # 1024x768 frame (see vision.TRIGGERS comment): (box, on_sum, off_sum). Any other sum = unknown,
    # and unknown is never toggled.
    _MODE_SIGS = {'a': ('전투모드', (849, 716, 851, 717), 1500, 6), 'x': ('거래차단', (947, 714, 949, 715), 1500, 233)}
    def _mode_state(self, frame, key):
        _name, box, on, off = self._MODE_SIGS[key]
        s = vis._px_sum(frame, *box)
        return True if s == on else (False if s == off else None)
    def _ensure_battle_modes(self, frame) -> None:
        """Right before a fight starts: make sure 전투모드 and 거래차단 are ON (toggle keys A / X)."""
        if frame is None or not config.load().get('battle_modes', True):
            return
        if time.time() - getattr(self, '_modes_at', 0.0) < 3.0:
            return
        if vis.chat_hangul_state(frame) != 'inactive':
            return   # chat box has focus: a letter key would be typed, not toggled
        todo = []
        for key in ('a', 'x'):
            st = self._mode_state(frame, key)
            if st is False:
                todo.append(key)
            elif st is None and time.time() - getattr(self, '_modes_unk_at', 0.0) >= 60.0:
                self._modes_unk_at = time.time()
                self._log(f'[모드] {self._MODE_SIGS[key][0]} 상태 인식 불가 — 건드리지 않음')
        if not todo:
            return
        self._modes_at = time.time()
        for key in todo:
            self.hands.press(key, wait=True)
            time.sleep(0.3)
        time.sleep(0.4)
        after = self._grab_main()
        res = []
        for key in todo:
            st = self._mode_state(after, key) if after is not None else None
            res.append(f"{self._MODE_SIGS[key][0]} {'ON' if st else ('여전히 OFF' if st is False else '확인불가')}")
        self._log('[모드] 전투 시작 전 자동 설정: ' + ', '.join(res))
    def _do_reactions(self, fired: set[str]):
        now = time.time()
        for name in sorted(fired):
            entry = REACTIONS.get(name)
            if entry is None:
                continue
            if name in ('B모드', 'T밴(거래차단)') and config.load().get('battle_modes', True):
                continue   # these reactions switch the modes OFF; battle_modes wants them ON
            else:
                fn, cooldown, desc = entry
                if now - self._react_at.get(name, 0.0) < cooldown:
                    continue
                else:
                    self._react_at[name] = now
                    self._log(f'반응: {name} → {desc}')
                    try:
                        if name == 'restart 팝업' and self.monster in ('유물지도', '유물지도(정예)'):
                            self._restart_relic_map()
                            return True
                        else:
                            fn(self.hands)
                    except Exception as e:
                        self._log(f'반응 실패 ({name}): {e}')
    def _start_battle(self):
        self._battle_running = True
        self._battle_at = time.time()
        def _worker():
            # ***<module>.Brain._start_battle._worker: Failure: Different bytecode
            try:
                detect = None
                if config.mob_boss(self.monster):
                    bd = self.boss_detector
                    if bd is not None and bd.ready:
                        detect = lambda f: bd.detect(f)
                    else:
                        if self.detector and getattr(self.detector, 'matcher', None) and self.detector.ready:
                                    detect = lambda f: self.detector.detect(f)
                gm_frame = [None]
                def _pre_retreat(frame):
                    if frame is not None and gm_frame[0] is None and vis.gm_chat_visible(frame):
                                gm_frame[0] = frame
                                self._gm_at = time.time()
                                self._log('⚠ 영자(운영자) 채팅 감지 (퇴각 직전)')
                                self._notify_img('⚠ 영자(운영자) 채팅 감지', frame)
                cfg_all = config.load()
                if bool(cfg_all.get('banja_mode')) and self._banja_ok():
                    result = combat.run_battle_banja(self._io, opts={'pan_dist': config.mob_pan_dist(self.monster)}, log=self._log, should_stop=lambda: not self.running, sub_entry=self._banja_sub_entry)
                else:
                    s = cfg_all.get('monsters', {}).get(self.monster, {})
                    result = combat.run_battle(self._io, opts={'squad_counts': config.parse_squad_counts(s.get('squad_counts')), 'center_move_delay': float(s.get('center_move_delay', 1.0)), 'lead_px': float(s.get('lead_px', 40.0)), 'aim_y4': config.mob_aim_y4(self.monster), 'use_summon': bool(s.get('use_summon', False)), 'summon_mode': config.summon_mode(s), 'summon_center': config.mob_summon_center(self.monster), 'multi_retreat': bool(s.get('multi_retreat', False)), 'noejeonju': bool(s.get('noejeonju', False)), 'attack_keys': s.get('attack_keys'), 'aim_y': self.aim_y, 'pan_dist': config.mob_pan_dist(self.monster), 'pan_ratio': config.mob_pan_ratio(self.monster), 'projection_scale': config.mob_projection_scale(self.monster), 'lead_angle': config.mob_lead_angle(self.monster), 'boss': config.mob_boss(self.monster), 'debug_dir': config.BATTLE_DEBUG_DIR, **{'debug_keep': 50, 'aim_debug_dir': config.AIM_DEBUG_DIR, 'skip_debug_dir': config.BATTLE_SKIP_DIR, 'pan_debug_dir': config.PAN_DEBUG_DIR}}, log=self._log, detect=detect, should_stop=lambda: not self.running, pre_retreat=_pre_retreat)
                if result in ['ok', 'stopped']:
                    self.battle_count += 1
                    self._save_count()
                    self._report_battle()
                    self._log(f'전투 {self.battle_count}회')
                    if result == 'ok':
                        threading.Thread(target=self._delayed_merc_check, daemon=True).start()
                        self._check_scene_change()
                        self._check_sub_windows()
                        if gm_frame[0] is not None:
                            msg = config.load().get('gm_chat_msg', '')
                            if msg:
                                time.sleep(2.0)
                                self.type_chat(msg)
                            self._stop_bot('영자 대응 완료')
                else:
                    if result == 'retreat-fail':
                        self._stop_now('전투 후 메인 복귀 실패')
                    else:
                        self._log(f'전투 종료: {result}')
            except Exception as e:
                tb = traceback.extract_tb(e.__traceback__)[(-1)]
                self._log(f'전투 오류: {type(e).__name__}: {e} ({tb.filename.split(chr(92))[(-1)]}:{tb.lineno})')
            finally:
                self._battle_running = False
                self._battle_at = time.time()
                self._battle_click = 1
        self._battle_thread = threading.Thread(target=_worker, daemon=True)
        self._battle_thread.start()
    def _cap(self):
        return self._grab_main()
    def retreat_if_battle(self, stop=None) -> bool:
        img = self._grab_main()
        if img is None or not combat.is_battle(img):
            return False
        else:
            self._log('전투 감지 → 퇴각 (휴식 중)')
            combat._retreat(self._io)
            combat.wait_for_main(self._io, self._log, stop=stop)
            return True
    def _cap_native(self):
        return self._grab_main(normalize=False)
    def _start_jochul(self):
        self._battle_running = True
        self._jochul_at = time.time()
        def _worker():
            try:
                self._handle_jochul()
            except Exception as e:
                self._log(f'조철 오류: {e}')
            finally:
                self._battle_running = False
                self._jochul_at = time.time()
                self._battle_click = 1
        self._solve_thread = threading.Thread(target=_worker, daemon=True)
        self._solve_thread.start()
    SOLVER_WAIT_SEC = 6.0
    def _await_solver(self, solver, label: str) -> bool:
        if getattr(solver, 'ready', False):
            return True
        else:
            self._log(f'{label} — 해독 모델 로드 대기')
            end = time.time() + self.SOLVER_WAIT_SEC
            while time.time() < end:
                if not self.running:
                    return False
                if getattr(solver, 'ready', False):
                    return True
                time.sleep(0.2)
            self._notify(f'⚠️ {label} 감지했으나 해독 모델 미로드 — 정지')
            self._stop_now(f'{label} 솔버 미준비')
            return False
    def _handle_jochul(self, hands=None, hwnd=0, tag='', park=True):
        """Solve one 조철 round; in the background also record EVERY frame of the round with labels
        (start slot, our answer, where the 마패 reappears) into debug/jochul_rounds for offline tuning."""
        rec = None
        self._jochul_meta = {}
        try:
            _rh = hwnd or self.engine.hwnd or find_window()
            if _rh and config.load().get('jochul_record', True):
                rec = jochul.RoundRecorder(_rh, grab_fn=(lambda: grab_hwnd(_rh))).start()
        except Exception:
            rec = None
        try:
            return self._handle_jochul_inner(hands, hwnd, tag, park)
        finally:
            if rec is not None:
                try:
                    time.sleep(0.4)
                    rec.stop()
                    d = rec.save(os.path.join(config.BASE_DIR, 'debug', 'jochul_rounds'), self._jochul_meta)
                    if d:
                        self._log(f'조철 라운드 녹화 저장 — {len(rec.frames)}프레임 ({rec.mode}) {d}')
                except Exception:
                    pass
    def _handle_jochul_inner(self, hands=None, hwnd=0, tag='', park=True):
        hands = hands or self.hands
        cap = (lambda: grab_hwnd(hwnd)) if hwnd else self._cap
        p = f'[{tag}] ' if tag else ''
        if not self._await_solver(self.jochul_solver, f'{p}조철'):
            return
        else:
            self._log(f'{p}조철 감지 — 풀이 시작')
            if park:
                hands.move_nofg(*jochul.PARK_XY, wait=True)
            time.sleep(jochul.FIRST_TILE_DELAY)
            # The first-tile marker can take a few frames to appear; look for up to ~1 s instead of
            # giving up (and stopping) on the first miss. The shuffle clock below is kept aligned.
            _t_ref = time.time()
            frame, first = None, None
            _marker_seen, _pattern_seen = [], []
            for _try in range(45):
                frame = cap()
                if frame is not None:
                    _reg = jochul.crop_region(frame)
                    _pattern_seen.append(jochul.find_first_tile(_reg))
                    # skin-independent: the gold 마패 medallion floating over the marked character
                    _marker_seen.append(jochul.find_marker_slot(_reg))
                    _mv = jochul.vote_marker(_marker_seen)
                    if _mv and _marker_seen.count(_mv) >= 3:
                        break
                if time.time() - _t_ref > 1.6:
                    break
                time.sleep(0.04)
            _mv, _pv = jochul.vote_marker(_marker_seen), jochul.vote_marker(_pattern_seen)
            first = _mv or _pv
            if _mv and _pv and _mv != _pv:
                self._log(f'{p}조철 첫 마패: 메달 {_mv}번 / 색상패턴 {_pv}번 불일치 — 메달 우선')
            if frame is None:
                self._log(f'{p}조철: 캡처 실패')
                return
            else:
                if first is None:
                    try:
                        os.makedirs(config.JOCHUL_FAIL_DIR, exist_ok=True)
                        cv2.imwrite(os.path.join(config.JOCHUL_FAIL_DIR, time.strftime('first_tile_miss_%H%M%S.png')), frame)
                    except Exception:
                        pass
                    self._stop_now(f'{p}조철 첫 마패 인식 실패')
                    return
                else:
                    self._log(f'{p}조철 첫 마패: {first}번')
                    time.sleep(max(0.0, jochul.SHUFFLE_DELAY - (time.time() - _t_ref)))
                    rec_hwnd = hwnd or self.engine.hwnd or find_window()
                    rec_cap = (lambda: grab_hwnd(rec_hwnd)) if rec_hwnd else self._cap
                    frames, times = jochul.record(rec_cap)
                    if not self.running:
                        return
                    else:
                        _t0 = time.perf_counter()
                        answer, ops = self.jochul_solver.solve(frames, times, first)
                        solve_s = time.perf_counter() - _t0
                        n_ops = len(ops)
                        self._log(f'{p}조철 연산 {n_ops}개(15 기대) → 정답: {answer} (해석 {solve_s:.1f}s)')
                        import net
                        meta = {'ver': net.CODE_VER, 'first': first, 'n_ops': n_ops, 'ops': [list(o) for o in ops], 'order': jochul.apply_swaps(ops), 'answer': answer, 'attempts': [], 'passed': None, 'solve_s': round(solve_s, 2)}
                        self._jochul_meta = meta
                        meta['marker_votes'] = {str(k): _marker_seen.count(k) for k in set(_marker_seen) if k}
                        dump = None
                        if n_ops != 15 or answer is None:
                            dump = self._save_frames(config.JOCHUL_FAIL_DIR, frames, times, meta=meta, extra={'first_tile': frame})
                            self._upload_jochul_debug(frames, times, f'n_ops={n_ops}', meta=dict(meta), first_img=frame)
                        if answer is None:
                            answer = 3
                            self._log(f'{p}조철 해독 불확실 → 중앙({answer}) 클릭')
                        meta['clicked'] = answer
                        x = jochul.CLICK_X[answer]
                        time.sleep(1.0)
                        def _popup_present():
                            f = cap()
                            return f is not None and vis._px_sum(f, 513, 43, 514, 44) == 151 and (vis._px_sum(f, 514, 43, 515, 44) == 133)
                        def _fg_info():
                            fg = win32gui.GetForegroundWindow()
                            try:
                                title = win32gui.GetWindowText(fg)[:40]
                            except Exception:
                                title = '?'
                            return {'is_target': fg == rec_hwnd, 'title': title}
                        hands.move(x, jochul.CLICK_Y, wait=True)
                        time.sleep(0.3)
                        meta['fg_before'] = _fg_info()
                        hands.click(x, jochul.CLICK_Y, down_ms=0.15, wait=True)
                        time.sleep(0.3)
                        hands.click(x, jochul.CLICK_Y, down_ms=0.15, wait=True)
                        meta['fg_after'] = _fg_info()
                        self._log(f'{p}조철 정답 더블클릭 ({answer}번 x={x})')
                        time.sleep(0.9)
                        try:
                            # after the click the clicked character turns green and the 마패 shows over it for ~1.7 s,
                            # then the board closes (real round, 44 fps). Read it NOW, not 3 s later. Recorded as evidence
                            # only: the game closes the board for right and wrong clicks alike, so this is NOT a pass signal.
                            _rf = cap()
                            if _rf is not None:
                                meta['reveal_slot'] = jochul.find_marker_slot(jochul.crop_region(_rf))
                                meta['start_slot'] = first
                        except Exception:
                            pass
                        time.sleep(2.1)
                        present = _popup_present()
                        meta['attempts'].append(bool(present))
                        passed = not present
                        meta['passed'] = passed
                        if passed:
                            self._log(f'{p}조철 클릭 후 창 닫힘 (정답 여부는 게임이 알려주지 않음 — 확인 불가)')
                            if dump:
                                self._write_meta(dump, meta)
                        else:
                            if dump:
                                self._write_meta(dump, meta)
                            else:
                                self._save_frames(config.JOCHUL_FAIL_DIR, frames, times, meta=meta, extra={'first_tile': frame})
                            self._upload_jochul_debug(frames, times, f'{p}오답 (answer={answer})', meta=dict(meta), first_img=frame)
                            if not hwnd:
                                self._report_appear('jochul', wrong=True)
                            self._stop_now(f'{p}조철 오답')
    def _start_jamun(self):
        self._battle_running = True
        self._jamun_at = time.time()
        def _worker():
            try:
                self._handle_jamun()
            except Exception as e:
                self._log(f'자방문 오류: {e}')
            finally:
                self._battle_running = False
                self._jamun_at = time.time()
                self._battle_click = 1
        self._solve_thread = threading.Thread(target=_worker, daemon=True)
        self._solve_thread.start()
    def _handle_jamun(self, hands=None, hwnd=0, tag=''):
        """Solve one 자방문 captcha and keep the evidence (full frames before typing / before confirm / 4 s after,
        every attempt's crop, read text and confidence, what was typed, the verdict pixels) in
        debug/jamun_rounds/ so a live run can be audited offline."""
        self._jamun_rec = {'attempts': [], 'frames': {}}
        try:
            return self._handle_jamun_inner(hands, hwnd, tag)
        finally:
            try:
                self._jamun_save(hwnd)
            except Exception:
                pass
    def _jamun_note_frame(self, key, img):
        try:
            if img is not None:
                self._jamun_rec['frames'][key] = img.copy()
        except Exception:
            pass
    def _jamun_save(self, hwnd):
        rec = getattr(self, '_jamun_rec', None)
        if not rec or not rec.get('attempts'):
            return
        base = os.path.join(config.BASE_DIR, 'debug', 'jamun_rounds')
        d = os.path.join(base, time.strftime('jamun_%Y%m%d_%H%M%S'))
        os.makedirs(d, exist_ok=True)
        for k, img in rec['frames'].items():
            cv2.imwrite(os.path.join(d, k + '.png'), img)
        meta = {k: v for k, v in rec.items() if k != 'frames'}
        with open(os.path.join(d, 'meta.json'), 'w', encoding='utf-8') as f:
            json.dump(meta, f, ensure_ascii=False, default=str)
        dirs = sorted(x for x in os.listdir(base) if x.startswith('jamun_'))
        for old in dirs[:-60]:
            __import__('shutil').rmtree(os.path.join(base, old), ignore_errors=True)
        self._log(f'자방문 기록 저장 — {os.path.basename(d)} (시도 {len(rec["attempts"])}회)')
    def _handle_jamun_inner(self, hands=None, hwnd=0, tag=''):
        hands = hands or self.hands
        cap = (lambda: grab_hwnd(hwnd)) if hwnd else self._cap
        cap_native = (lambda: grab_hwnd(hwnd, normalize=False)) if hwnd else self._cap_native
        p = f'[{tag}] ' if tag else ''
        if not self._await_solver(self.text_reader, f'{p}자방문'):
            return
        else:
            self._log(f'{p}자방문 감지 — 풀이 시작')
            hands.move(292, 167, wait=True)
            time.sleep(1.0)
            text = ''
            prev_text = None
            for attempt in range(3):
                if not self.running:
                    return
                else:
                    frame = cap_native()
                    if frame is None:
                        self._log(f'{p}자방문: 캡처 실패')
                        return
                    else:
                        crop = captcha.crop_text(frame)
                        self._save_crop(config.JAMUN_DIR, crop)
                        text, conf = self.text_reader.read(crop)
                        self._log(f'{p}자방문 인식: {text} (margin {conf:.3f} / 스텝 {self.text_reader.last_step_conf:.3f})')
                        try:
                            self._jamun_rec['attempts'].append({'text': text, 'conf': round(float(conf), 4), 'step_conf': round(float(self.text_reader.last_step_conf), 4), 't': time.strftime('%H:%M:%S')})
                            self._jamun_note_frame('attempt%d_full' % (attempt + 1), frame)
                            self._jamun_note_frame('attempt%d_crop' % (attempt + 1), crop)
                        except Exception:
                            pass
                        if prev_text is not None and text == prev_text:
                                self._log(f'{p}자방문 갱신 미반영 의심 — 직전과 동일 문자({text})')
                        if self._debug_jamun is not None:
                            try:
                                ok_png, enc = cv2.imencode('.png', crop)
                                if ok_png:
                                    self._debug_jamun(enc.tobytes(), text, float(conf))
                            except Exception:
                                pass
                        if len(text) == 5 and conf >= 0.995:
                                break
                        if attempt >= 2:
                            self._log(f'{p}자방문 갱신 2회 소진 — {text}로 그냥 제출')
                            break
                        else:
                            self._log(f'{p}자방문 {len(text)}자/conf{conf:.2f} — 갱신 후 재판별 ({attempt + 1}/2)')
                            if attempt == 1:
                                time.sleep(3.0)
                            hands.click(578, 478, wait=True)
                            time.sleep(1.5)
                            prev_text = text
            hands.move(*JAMUN_INPUT_XY, wait=True)
            time.sleep(0.3)
            hands.click(*JAMUN_INPUT_XY, wait=True)
            time.sleep(0.2)
            submitted_text = _jamun_submission_text(text, self._auth_id())
            self._jamun_rec['read_text'] = text
            self._jamun_rec['submitted_text'] = submitted_text
            for ch in submitted_text:
                hands.press(ch.lower(), wait=True)
                time.sleep(0.5)
            time.sleep(2.0)
            self._jamun_note_frame('before_confirm', cap())
            hands.click(446, 478, wait=True)
            time.sleep(4.0)
            frame = cap()
            self._jamun_note_frame('after_confirm_4s', frame)
            try:
                self._jamun_rec['wrong_dialog_pixels'] = [vis._px_sum(frame, 589, 426, 590, 427), vis._px_sum(frame, 590, 426, 591, 427)] if frame is not None else None
                self._jamun_rec['wrong_dialog_seen'] = bool(frame is not None and self._jamun_rec['wrong_dialog_pixels'] == [690, 690])
            except Exception:
                pass
            if frame is not None and vis._px_sum(frame, 589, 426, 590, 427) == 690 and (vis._px_sum(frame, 590, 426, 591, 427) == 690):
                self._debug_jamun_wrong()
                if not hwnd:
                    self._report_appear('jamun', wrong=True)
                self._stop_now(f'{p}자방문 오답')
            else:
                self._log(f'{p}자방문 통과')
    def _upload_jochul_debug(self, frames, times, reason: str, meta=None, first_img=None) -> None:
        up = self._debug_jochul
        if up is None:
            return
        else:
            def _worker():
                try:
                    import io
                    import zipfile
                    buf = io.BytesIO()
                    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_STORED) as z:
                        if meta is not None:
                            z.writestr('meta.json', json.dumps(meta, ensure_ascii=False))
                        if first_img is not None:
                            ok, enc = cv2.imencode('.jpg', first_img, [cv2.IMWRITE_JPEG_QUALITY, 80])
                            if ok:
                                z.writestr('first_tile.jpg', enc.tobytes())
                        for i, f in enumerate(frames, 1):
                            ok, enc = cv2.imencode('.jpg', f, [cv2.IMWRITE_JPEG_QUALITY, 60])
                            if ok:
                                z.writestr(f'frame_{i:04d}.jpg', enc.tobytes())
                            if buf.tell() > 34000000:
                                break
                        if times is not None:
                            z.writestr('times.json', json.dumps([round(t, 4) for t in times]))
                    up(buf.getvalue(), reason)
                    self._log(f'조철 실패 회차 서버 수집 ({buf.tell() // 1048576}MB)')
                except Exception:
                    return None
            threading.Thread(target=_worker, daemon=True, name='jochul-debug').start()
    @staticmethod
    def _save_frames(d, frames, times=None, meta=None, extra=None):
        try:
            os.makedirs(d, exist_ok=True)
            sub = os.path.join(d, time.strftime('%Y%m%d_%H%M%S'))
            os.makedirs(sub, exist_ok=True)
            for i, f in enumerate(frames, 1):
                cv2.imwrite(os.path.join(sub, f'frame_{i:04d}.png'), f)
            if times is not None:
                with open(os.path.join(sub, 'times.json'), 'w', encoding='ascii') as f:
                    json.dump([round(t, 4) for t in times], f)
            for name, img in (extra or {}).items():
                if img is not None:
                    cv2.imwrite(os.path.join(sub, f'{name}.png'), img)
            if meta is not None:
                Brain._write_meta(sub, meta)
            dirs = sorted((g for g in __import__('glob').glob(os.path.join(d, '*')) if os.path.isdir(g)))
            for old in dirs[:(-5)]:
                __import__('shutil').rmtree(old, ignore_errors=True)
            return sub
        except Exception:
            return None
    @staticmethod
    def _write_meta(sub, meta):
        # irreducible cflow, using cdg fallback
        # ***<module>.Brain._write_meta: Failure: Compilation Error
        try:
            with open(os.path.join(sub, 'meta.json'), 'w', encoding='utf-8') as f:
                json.dump(meta, f, ensure_ascii=False, indent=1)
        except Exception:
            return None
    @staticmethod
    def _save_crop(d, crop):
        try:
            os.makedirs(d, exist_ok=True)
            cv2.imwrite(os.path.join(d, time.strftime('jamun_%Y%m%d_%H%M%S.png')), crop)
            files = sorted(__import__('glob').glob(os.path.join(d, '*.png')))
            for old in files[:(-200)]:
                os.remove(old)
        except Exception:
            return None
    def _loop(self):
        try:
            self._run_loop()
        finally:
            self.running = False
            try:
                self.hands.release_all()
            except Exception as e:
                self._log(f'입력 정리 오류: {e}')
            try:
                self._retreat_subs()
            except Exception:
                pass
            self._log('구동 정지')
            try:
                self._on_stopped()
            except Exception:
                pass

    def _run_loop(self):
        # ***<module>.Brain._run_loop: Failure: Different control flow
        self._log('구동 시작')
        _first = True
        prev_busy = False
        search_window = detector.SearchWindow()
        main_since = None
        loop_n = 0
        last_click_n = None
        dummy_guard = detector.DummyGuard()
        no_frame_at = 0.0
        # NATAS/manager (2026-11-18): STOP_NOW_TRIGGERS fired on a single bad frame
        # (measured: '팅(시스템 팝업)' region read 216/220 vs the real threshold
        # 308/388 moments later on a clean re-capture -- a one-frame false positive,
        # not a miscalibrated region). Require the same kill trigger on 2 consecutive
        # loop iterations before trusting it; a real system popup stays up far longer
        # than one frame, so this costs nothing real and kills the false stop.
        _pending_kill = None
        while self.running:
            while True:
                t0 = time.time()
                units = min(5.0, (t0 - getattr(self, '_prev_loop_t', t0)) / self.TICK_UNITS)
                self._prev_loop_t = t0
                loop_n += units
                _fid = self.engine._frame_id
                img = self.engine.snapshot()
                if img is None:
                    main_since = None
                    if no_frame_at == 0.0:
                        no_frame_at = time.time()
                        self._log('캡처 실패 — 거상 창 확인 중')
                    else:
                        if time.time() - no_frame_at >= NO_FRAME_STOP_SEC:
                            self._stop_now('거상 창이 사라짐 (캡처 불가)')
                            return
                    time.sleep(0.2)
                else:
                    no_frame_at = 0.0
                    snap = self.vision.snapshot()
                    if _first:
                        _first = False
                        self._log(f'첫 프레임 {img.shape} 씬={snap.get("scene")} hwnd={self.engine.hwnd}')
                    fired = set(snap.get('triggers', []))
                    scene = snap.get('scene', 'unknown')
                    if scene != 'main':
                        main_since = None
                    else:
                        if main_since is None:
                            main_since = time.monotonic()
                    try:
                        self._sniff_subs()
                    except Exception:
                        pass
                    if self._shutdown_at is not None and time.time() >= self._shutdown_at:
                        self._log('정지')
                        self.running = False
                        return
                    else:
                        kill = fired & STOP_NOW_TRIGGERS
                        if kill and (not self._battle_running):
                            if _pending_kill == kill:
                                self._stop_now(', '.join(sorted(kill)))
                                return
                            else:
                                _pending_kill = kill
                                self._log(f'[확인중] {", ".join(sorted(kill))} — 다음 프레임에서 재확인')
                        else:
                            _pending_kill = None
                        if True:
                            stop_hit = fired & self._stop_triggers
                            if stop_hit and (not self._battle_running) and (self._shutdown_at is None):
                                        restock_eligible = stop_hit <= {'무게 꽉 참', '포만감 템 없음'}
                                        if restock_eligible and self._try_autorestock(stop_hit):
                                            pass
                                        else:
                                            self._stop_bot(', '.join(sorted(stop_hit)))
                            if scene == 'main' and (not self._battle_running):
                                    for name in sorted(fired - self._prev_fired & NOTIFY_TRIGGERS):
                                        self._notify_popup(name)
                            if not self._battle_running and self._shutdown_at is None:
                                    new_fired = fired - self._prev_fired
                                    now = time.time()
                                    if '조철 출현' in new_fired:
                                        self._record_appear('조철')
                                        if now - self._jochul_at > 5.0:
                                            self._start_jochul()
                                    else:
                                        if '자방문 출현' in new_fired:
                                            self._record_appear('자방문')
                                            if now - self._jamun_at > 5.0:
                                                self._start_jamun()
                            self._prev_fired = fired
                            if fired and (not self._battle_running) and (self._shutdown_at is None) and (not self._sub_solving) and self._do_reactions(fired):
                                                continue
                            if not self._battle_running and scene == 'battle' and combat.is_battle(img) and (time.time() - self._battle_at > 0.3):
                                            if combat.minimap_center_black(combat.crop_minimap(img)):
                                                self._start_battle()
                                            else:
                                                if time.time() - self._tab_at > 0.5:
                                                    self.hands.press('tab')
                                                    self._tab_at = time.time()
                            if self._battle_running or scene == 'battle' or self._sub_solving or self.rest_mode:
                                self._no_battle_count = 0
                            else:
                                if self._shutdown_at is None:
                                    self._no_battle_count += units
                                    limit = self._nb_limit() or NO_BATTLE_LIMIT
                                    if self._no_battle_count >= limit:
                                        self._stop_bot(f'{limit}루프 전투 미진입 (팅 의심)')
                            if scene == 'main' and (not self._battle_running) and (time.time() - self._digit_at >= DIGIT_GUARD_SEC):
                                        num = detector.read_top_number(img, dump_dir=config.DIGIT_DEBUG_DIR)
                                        if num is not None:
                                            self._digit_at = time.time()
                                            dummy_guard.progress()
                                            self._log('전투 대기중')
                            if prev_busy and (not self._battle_running):
                                    last_click_n = None
                                    dummy_guard.progress()
                            if self._battle_running:
                                dummy_guard.progress()
                            prev_busy = self._battle_running
                            search_window.update(scene == 'main' and (not self._battle_running))
                            fixed_sc = config.mob_gate_scale(self.monster)
                            gate_sc = fixed_sc if fixed_sc is not None else 1.0
                            mob_gate_sc = gate_sc * search_window.scale
                            if self._close_stray_window(img, scene, fired):
                                self.engine.wait_new(_fid, 0.05)
                                continue
                            if scene == 'main' and (not self._battle_running) and self._shutdown_at is None and time.time() - getattr(self, '_dead_chk_at', 0.0) >= 0.5:
                                self._dead_chk_at = time.time()
                                self._update_merc_baseline(img)
                                if config.load().get('prefight_revive', True) and self._revive_dead_mercs(img):
                                    continue
                            # NATAS gate probe (2026-11-17): once a second, name every click gate that is False, so a
                            # Start that never clicks says why instead of being guessed at. Remove once the bot fights.
                            if time.time() - getattr(self, '_gate_log_at', 0.0) >= 1.0:
                                self._gate_log_at = time.time()
                                _g = {'detector': bool(self.detector), 'ready': bool(self.detector and self.detector.ready),
                                      'not_battle': not self._battle_running, 'not_shutdown': self._shutdown_at is None,
                                      'scene_main': scene == 'main', 'not_sub_solving': not self._sub_solving,
                                      'not_rest': not self.rest_mode,
                                      'sched_ok': self.sched_target is None or self.battle_count < self.sched_target,
                                      'battle_click': self._battle_click >= 1,
                                      'digit_guard': time.time() - self._digit_at >= DIGIT_GUARD_SEC}
                                _bad = [k for k, v in _g.items() if not v]
                                self._log('[게이트] ' + ('전부 통과 — 색적 실행' if not _bad else '막힘: ' + ', '.join(_bad)) + f' (scene={scene})')
                            if self.detector and self.detector.ready and (not self._battle_running) and (self._shutdown_at is None) and (scene == 'main') and (not self._sub_solving) and (not self.rest_mode) and (self.sched_target is None or self.battle_count < self.sched_target) and (self._battle_click >= 1) and (time.time() - self._digit_at >= DIGIT_GUARD_SEC):
                                                                    sprite_opts = {}
                                                                    if isinstance(self.detector, detector.SpriteDetector):
                                                                        sprite_opts['allow_avoid2'] = main_since is not None and time.monotonic() - main_since >= detector.SPRITE_AVOID2_DELAY_SEC
                                                                    coords = dummy_guard.filter(self.detector.detect(img, fire_roi=self.fire_roi, trust_avoid=self.trust_avoid, fire_rect=self.fire_rect, **sprite_opts), time.time())
                                                                    pick = detector.nearest_in_gate(coords, mob_gate_sc, center=detector.CENTER)
                                                                    search_window.advance(units)
                                                                    if pick:
                                                                        # Re-detect on the NEWEST frame and click where the mob is NOW:
                                                                        # mobs walk, and the frame the pick came from is already old.
                                                                        fresh = self.engine.snapshot()
                                                                        if fresh is None or not combat.is_main(fresh):
                                                                            self._log('색적 결과 폐기 — 클릭 직전 화면 변경(연산 지연)')
                                                                            pick = None
                                                                        else:
                                                                            c2 = dummy_guard.filter(detector.drop_ui_points(self.detector.detect(fresh, fire_roi=self.fire_roi, trust_avoid=self.trust_avoid, fire_rect=self.fire_rect, **sprite_opts)), time.time())
                                                                            near = None
                                                                            if c2 is not None and c2.shape[0]:
                                                                                dd = np.hypot(c2[:, 0] - pick[0], c2[:, 1] - pick[1])
                                                                                j = int(np.argmin(dd))
                                                                                if dd[j] <= 26.0:
                                                                                    near = c2[j]
                                                                            if near is None:
                                                                                self._log('색적 결과 폐기 — 클릭 직전 재확인에서 대상 사라짐/이동')
                                                                                pick = None
                                                                            else:
                                                                                pick = (float(near[0]), float(near[1]), float(detector.corrected_dist(near[None, :])[0]))
                                                                                img = fresh
                                                                    if pick:
                                                                        x, y, dist = pick
                                                                        if self._prefight(img):
                                                                            continue
                                                                        self.hands.click(int(x), int(y), 'right')
                                                                        try:
                                                                            _d = os.path.join(config.BASE_DIR, 'debug', 'clicks')
                                                                            os.makedirs(_d, exist_ok=True)
                                                                            if len(os.listdir(_d)) < 80:
                                                                                _im = img.copy()
                                                                                cv2.circle(_im, (int(x), int(y)), 16, (0, 255, 0), 2)
                                                                                cv2.imwrite(os.path.join(_d, time.strftime('%H%M%S') + '.jpg'), _im, [cv2.IMWRITE_JPEG_QUALITY, 80])
                                                                        except Exception:
                                                                            pass
                                                                        self._moved_at = time.time()
                                                                        self._battle_click = -detector.click_cooldown(dist)
                                                                        search_window.reset()
                                                                        self._log('몹 클릭')
                                                                        if not self.ignore_dummy:
                                                                            verdict = dummy_guard.click(x, y, dist, time.time())
                                                                            if verdict == 'suspect':
                                                                                self._log(f'더미몹 의심 — 재클릭 {dummy_guard.clicks}회, 응답 없음 {time.time() - (dummy_guard.first_t or time.time()):.0f}초 ({detector.DummyGuard.MIN_SECONDS:.0f}초 넘으면 건너뜀)')
                                                                            elif verdict == 'skip':
                                                                                self._log('더미몹 판정 — 이 자리를 45초간 건너뛰고 계속 사냥')
                                                                                # we were actively clicking for 15 s: that is not a disconnect, so the
                                                                                # 30 s "no fight = 팅 의심" clock must not run through this
                                                                                self._no_battle_count = 0
                                                                            elif verdict == 'stop':
                                                                                self._stop_bot('더미몹 반복 (건너뛰어도 전투 미진입)')
                                                                        last_click_n = loop_n
                            if self.box_click and (not self._battle_running) and (self._shutdown_at is None) and (scene == 'main') and (not self._sub_solving) and (not self.rest_mode) and (self._battle_click >= 1):
                                                        pick = detector.nearest_in_gate(detector.find_boxes(img), gate_sc)
                                                        if pick:
                                                            fresh = self.engine.snapshot()
                                                            if fresh is None or not combat.is_main(fresh):
                                                                self._log('상자 결과 폐기 — 클릭 직전 화면 변경')
                                                                pick = None
                                                        if pick:
                                                            x, y, dist = pick
                                                            self.hands.click(int(x), int(y), 'left')
                                                            self._battle_click = -detector.COOLDOWN_LOOPS
                                                            self._log('상자 클릭')
                            self._battle_click += units
                            self.engine.wait_new(_fid, 0.03)