# Decompiled with PyLingual (https://pylingual.io)
# Internal filename: 'prism.py'
# Bytecode version: 3.11a7e (3495)
# Source timestamp: 2026-09-21 13:50:40 UTC (1789998640)

from __future__ import annotations
global _API
import dpi
import ctypes
import ctypes.wintypes
import os
import re
import subprocess
import sys
import threading
import time
import cv2
import webview
import win32con
import win32gui
import win32process
import config
APP_TITLE = 'Gato_super'
from brain import Brain
from capture import CaptureEngine, REF_H, REF_W, find_window, find_windows, grab_hwnd_region
import combat
import net
from input import Hands, ensure_admin, is_admin
from notify import BotPoller, Notifier
from sniffer import ChatSniffer
from vision import Vision, detect_scene as vision_detect_scene, px_is as vision_px_is, scene_probe as vision_scene_probe

try:
    ctypes.windll
    ctypes.WinDLL
except AttributeError:
    class _StubDLL:
        def __getattr__(self, name):
            return lambda *a, **k: 0
    class _StubLib:
        def __getattr__(self, name):
            return _StubDLL()
    ctypes.windll = _StubLib()
    ctypes.WinDLL = lambda *a, **k: _StubDLL()

UI_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ui')
# Desktop-sized window. The 425x850 phone-portrait shape was a vendor
# leftover; this is a PC app with a real monitor behind it.
WIN_MIN_W, WIN_MIN_H = (720, 560)
WIN_DEF_W, WIN_DEF_H = (960, 660)
class Api:
    def __init__(self):
        # ***<module>.Api.__init__: Failure: Different bytecode
        self.engine = CaptureEngine(fps=60.0)
        self.vision = Vision()
        self.vision.attach(self.engine)
        self.hands = Hands(hwnd_get=lambda: self.engine.hwnd, log=lambda s: self.vision.note('input', s))
        self.notifier = Notifier(get_discord=lambda: config.load().get('discord_webhook', ''), get_ntfy=lambda: config.load().get('ntfy_url', ''), get_tag=lambda: getattr(self, 'auth_id', '') or 'Gato_super', log=lambda s: self.vision.note('input', s))
        self.auth = net.AuthClient()
        self.auth_id = os.environ.get('GATOSUPER_AUTH_ID', '').strip() or config.load().get('auth_id', '')
        self.brain = Brain(self.engine, self.vision, self.hands, note=lambda m: self.vision.note('brain', m), notify=lambda s: self.vision.note('input', s), notify_img=self.notifier.text, report_battle=self.auth.report_battle, report_appear=self.auth.report_appear, on_stopped=self._on_brain_stopped, banja_ok=lambda: self.auth.banja, no_battle_limit=lambda: self.auth.no_battle_limit, debug_jochul=self.auth.upload_jochul_debug, debug_jamun=self.auth.upload_jamun_debug, debug_jamun_wrong=self.auth.report_jamun_wrong, auth_id=lambda: self.auth.auth_id if self.auth.ok else '', on_auto_restart=self._auto_restart_bot)
        self._start_auth()
        self.bot_poller = BotPoller(get_token=lambda: config.load().get('discord_token', ''), get_channel=lambda: config.load().get('discord_channel', ''), on_message=self._on_discord_command, log=lambda s: self.vision.note('input', s), poll=2.0)
        self.bot_poller.start()
        self._chat_lock = threading.Lock()
        self._chat_log = []
        self._chat_seq = 0
        self.sniffer = ChatSniffer(on_chat=self._on_chat, log=lambda s: self.vision.note('input', s))
        self.sniffer.start()
        self._sched_thread = None
        self._sched_stop = threading.Event()
        self._sched = {'active': False, 'cycle': 0, 'cycles': 0, 'battles': 0, 'target': 0, 'resting': False, 'rest_left': 0}
        self._run_since = 0.0
        self._last_note = ''
        self._wins = []
        self._wins_at = 0.0
        self._live_until = 0.0
        self._live_thread = None
        self._live_lock = threading.Lock()
        self.start_cmd_poller()
        try:
            import remote_link
            self.remote = remote_link.install(self)   # None when remote.json is absent or invalid
        except Exception as _e:
            self.remote = None
            self.vision.note('input', f'[원격링크] 설치 실패 — {type(_e).__name__}: {_e}')
        try:
            import agent_link
            self.link = agent_link.install(self)   # always-on link to the Mac; None when disabled
        except Exception as _e:
            self.link = None
            self.vision.note('input', f'[링크] 설치 실패 — {type(_e).__name__}: {_e}')
        try:
            import update
            self.updater = update.install(self)   # frozen builds only; None in a source checkout
        except Exception as _e:
            self.updater = None
            self.vision.note('input', f'[업데이트] 설치 실패 — {type(_e).__name__}: {_e}')
    _CHAT_NOTIFY_KEY = {'귓말': 'notify_whisper', '일반': 'notify_normal', '반복': 'notify_repeat'}
    def _on_chat(self, kind: str, name: str, msg: str) -> None:
        # ***<module>.Api._on_chat: Failure: Different control flow
        with self._chat_lock:
            self._chat_seq += 1
            self._chat_log.append({'seq': self._chat_seq, 'kind': kind, 'name': name, 'msg': msg, 'time': time.strftime('%H:%M:%S')})
            if len(self._chat_log) > 400:
                del self._chat_log[:len(self._chat_log) - 400]
        key = self._CHAT_NOTIFY_KEY.get(kind)
        if not key or config.load().get(key, False):
                self.notifier.text(f'{kind} {name}: {msg}')
    _REMOTE_KEYS = {'key_f': 'f', 'key_m': 'm', 'key_i': 'i', 'key_b': 'b', 'key_enter': 'enter'}
    _INPUT_CMDS = frozenset(_REMOTE_KEYS) | {'click_l', 'click_r'}
    def start_cmd_poller(self):
        def _loop():
            while True:
                if not self.auth.token:
                    time.sleep(3.0)
                    continue
                else:
                    try:
                        cmds = self.auth.poll_cmd()
                    except Exception:
                        cmds = []
                    if not cmds:
                        time.sleep(0.5)
                        continue
                    else:
                        for c in cmds:
                            try:
                                self._run_remote(c.get('cmd', ''), c.get('arg', ''))
                            except Exception as e:
                                self.vision.note('input', f'[원격] 명령 오류: {e}')
        threading.Thread(target=_loop, daemon=True).start()
    def _note(self, msg: str):
        self._last_note = msg[:200]
        self.vision.note('input', msg)
        self.notifier.text(msg)
    def _run_remote(self, cmd: str, arg: str=''):
        if cmd in self._INPUT_CMDS and self.brain.running:
            self._note('가동 중에는 입력이 차단됩니다 — 봇을 정지한 뒤 다시 시도하세요')
        else:
            if cmd == 'start':
                self.start()
                self._note('▶ 패널 시작' if self.brain.running else f'⚠️ 시작 불가 — {self.brain.start_block_reason() or self.auth.label()}')
            else:
                if cmd == 'stop':
                    if not self.brain.running:
                        self._note('이미 정지 상태')
                    else:
                        if self.brain._shutdown_at is not None:
                            self._note('이미 정지 예약됨')
                        else:
                            self.stop_grace('패널')
                    return None
                else:
                    if cmd == 'shot':
                        img = self.brain._grab_main()
                        if img is None:
                            self._note(f'[원격] 캡처 실패 — {self._capture_fail_reason()}')
                            return
                        else:
                            ok, enc = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 70])
                            self.vision.note('input', '[원격] 화면 캡처 전송' if ok and self.auth.upload_shot(enc.tobytes()) else '[원격] 캡처 업로드 실패')
                    else:
                        if cmd == 'live_start':
                            self._live_extend()
                        else:
                            if cmd == 'live_stop':
                                self._live_until = 0.0
                            else:
                                if cmd == 'game_close':
                                    self._close_game()
                                else:
                                    if cmd in ['chat_normal', 'chat_sangdan', 'whisper']:
                                        self._run_chat(cmd, arg)
                                    else:
                                        if cmd in ['gato_login', 'gato_launch']:
                                            self._run_gato(cmd, arg)
                                        else:
                                            if cmd == 'gato_stats':
                                                self._run_gato_stats()
                                            else:
                                                if cmd in ['click_l', 'click_r']:
                                                    self._run_click(cmd, arg)
                                                else:
                                                    if cmd == 'settings_reload':
                                                        threading.Thread(target=self._pull_settings, daemon=True).start()
                                                        self.vision.note('input', '[원격] 설정 다시 불러오기')
                                                    else:
                                                        if cmd == 'sched_start':
                                                            try:
                                                                c, b, r = (int(x) for x in (arg or '').split(',')[:3])
                                                            except (ValueError, TypeError):
                                                                self._note('스케쥴 시작 실패 — 값 오류')
                                                                return None
                                                            result = self.schedule_start(c, b, r)['schedule_result']
                                                            if result['ok']:
                                                                self._note(f"스케쥴 시작 — {result['cycles']}사이클 × {result['battles']}전투, 휴식 {result['rest_sec']}초")
                                                            else:
                                                                self._note(f"스케쥴 시작 실패 — {result['reason']}")
                                                            return None
                                                        else:
                                                            if cmd == 'sched_stop':
                                                                if not self._sched.get('active'):
                                                                    self._note('스케쥴이 실행 중이 아닙니다')
                                                                else:
                                                                    self.schedule_stop()
                                                                    self._note('스케쥴 정지')
                                                                return None
                                                            else:
                                                                key = self._REMOTE_KEYS.get(cmd)
                                                                if key is None:
                                                                    self.vision.note('input', f'[원격] 알 수 없는 명령: {cmd}')
                                                                    return
                                                                else:
                                                                    if not self.engine.hwnd and (not find_window()):
                                                                        self._note(f'[원격] {key.upper()} 입력 실패 — 거상 창 없음')
                                                                        return
                                                                    else:
                                                                        self.hands.press(key)
                                                                        self.vision.note('input', f'[원격] {key.upper()} 입력')
    def _restore_game_focus(self):
        # ***<module>.Api._restore_game_focus: Failure: Different control flow
        if not self.brain.running or not self.hands.focus_game():
                self.vision.note('input', '⚠ 고트 조작 후 거상 창 전면 복귀 실패')
    def _run_gato_stats(self):
        def _worker():
            note = lambda s: self.vision.note('input', s)
            try:
                import traders_ctl
            except Exception as e:
                note(f'[고트] 지표 읽기 불가: {type(e).__name__}: {e}')
                return None
            try:
                traders_ctl.ensure_battle_analysis(log=note)
                d = traders_ctl.battle_stats(log=note)
                ok = self.auth.upload_stats(d['state'], d['stats'])
                note(f"[고트] 지표 {len(d['stats'])}건 {('전송' if ok else '전송 실패')} (state={d['state']})")
            except traders_ctl.TradersError as e:
                note(f'[고트] 지표 읽기 실패: {e}')
                self.auth.upload_stats('error', {'오류': str(e)[:80]})
            except Exception as e:
                note(f'[고트] 지표 오류: {type(e).__name__}: {e}')
            finally:
                self._restore_game_focus()
        threading.Thread(target=_worker, daemon=True).start()
    def _run_click(self, cmd: str, arg: str):
        try:
            (xs, _, ys) = (arg or '').partition(',')
            (x, y) = (int(xs), int(ys))
        except ValueError:
            self.vision.note('input', f'[원격] 클릭 좌표 오류: {arg!r}')
            return None
        if not (0 <= x < REF_W and 0 <= y < REF_H):
            self.vision.note('input', f'[원격] 클릭 좌표 범위 밖: ({x}, {y})')
            return None
        if not self.engine.hwnd and not find_window():
            self._note('[원격] 클릭 실패 — 거상 창 없음')
            return None
        button = 'right' if cmd == 'click_r' else 'left'
        self.hands.click(x, y, button)
        word = '우' if button == 'right' else '좌'
        self.vision.note('input', f'[원격] {word}클릭 ({x}, {y})')
    def _run_gato(self, cmd: str, arg: str):
        parts = (arg or '').split(',')
        try:
            slot = max(1, min(3, int(parts[0] or 1)))
        except ValueError:
            slot = 1
        otp = parts[1].strip() if len(parts) > 1 else ''
        def _worker():
            try:
                import traders_ctl
            except Exception as e:
                self._note(f'고트 기능 사용 불가: {type(e).__name__}: {e}')
                return None
            try:
                msg = traders_ctl.login_slot(slot, otp, log=lambda s: self.vision.note('input', s)) if cmd == 'gato_login' else traders_ctl.launch_game(slot, log=lambda s: self.vision.note('input', s))
                self._note(f'고트: {msg}')
            except traders_ctl.TradersError as e:
                self._note(f'고트 실패: {e}')
            except Exception as e:
                self._note(f'고트 오류: {type(e).__name__}: {e}')
        threading.Thread(target=_worker, daemon=True).start()
    LIVE_LEASE_SEC = 25.0
    LIVE_INTERVAL = 0.35
    LIVE_SIZE = (640, 480)
    LIVE_Q = 50
    LIVE_MIN_DIFF = 0.4
    LIVE_KEYFRAME_SEC = 5.0
    def _live_extend(self):
        with self._live_lock:
            fresh = self._live_until < time.time()
            self._live_until = time.time() + self.LIVE_LEASE_SEC
            if self._live_thread is None or not self._live_thread.is_alive():
                self._live_thread = threading.Thread(target=self._live_loop, daemon=True, name='live-view')
                self._live_thread.start()
        if fresh:
            self.vision.note('input', '[원격] 라이브 보기 시작 (~1fps)')
    def _live_loop(self):
        cv_ = threading.Condition()
        done = threading.Event()
        slot = {'jpg': None}

        def upload(jpg):
            try:
                self.auth.upload_live(jpg)
            except Exception:
                pass

        def _sender():
            while not done.is_set():
                with cv_:
                    while not slot['jpg'] and not done.is_set():
                        cv_.wait(0.5)
                    jpg = slot['jpg']
                    slot['jpg'] = None
                if jpg:
                    upload(jpg)

        threading.Thread(target=_sender, daemon=True, name='live-send').start()
        fails = 0
        prev = None
        last_q = 0.0
        try:
            while time.time() < self._live_until:
                t0 = time.time()
                img = self.brain._grab_main()
                if img is None:
                    fails += 1
                    if fails >= 5:
                        self.vision.note('input', f'[원격] 라이브 중단 — {self._capture_fail_reason()}')
                        self._live_until = 0.0
                        break
                else:
                    fails = 0
                    small = cv2.resize(img, self.LIVE_SIZE, interpolation=cv2.INTER_AREA)
                    changed = prev is None or cv2.absdiff(small, prev).mean() >= self.LIVE_MIN_DIFF
                    if changed or time.time() - last_q >= self.LIVE_KEYFRAME_SEC:
                        (ok, enc) = cv2.imencode('.jpg', small, [cv2.IMWRITE_JPEG_QUALITY, self.LIVE_Q])
                        if ok:
                            with cv_:
                                slot['jpg'] = enc.tobytes()
                                cv_.notify()
                            prev = small
                            last_q = time.time()
                time.sleep(max(0.0, self.LIVE_INTERVAL - (time.time() - t0)))
        finally:
            done.set()
            with cv_:
                cv_.notify()
        self.vision.note('input', '[원격] 라이브 보기 종료')

    def _capture_fail_reason(self) -> str:
        hwnd = find_window()
        if not hwnd:
            return '거상 창이 없습니다 (게임 종료됨)'
        try:
            (left, top, right, bottom) = win32gui.GetClientRect(hwnd)
            if right - left <= 0 or bottom - top <= 0:
                return '거상 창이 최소화되어 있습니다 (복원 후 다시 시도)'
        except Exception:
            return '거상 창을 읽을 수 없습니다'
        return '캡처에 실패했습니다 (일시적 오류일 수 있음)'
    def _close_game(self):
        hwnd = self.engine.hwnd or find_window()
        if not hwnd:
            self._note('게임 종료 — 거상 창이 이미 없습니다')
            return
        else:
            if self.brain.running:
                self.stop()
                time.sleep(0.3)
            win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
            self._note('게임 종료 요청 (창 닫기)')
    def _run_chat(self, cmd: str, arg: str):
        def _worker():
            try:
                if cmd == 'whisper':
                    slot_s, _, text = (arg or '').partition('|')
                    try:
                        slot = max(1, min(9, int(slot_s)))
                    except ValueError:
                        slot = 1
                    self._discord_whisper(slot, text)
                else:
                    self._discord_chat(arg, 'sangdan' if cmd == 'chat_sangdan' else 'normal')
            except Exception as e:
                self.vision.note('input', f'[패널] 채팅 오류: {type(e).__name__}: {e}')
        threading.Thread(target=_worker, daemon=True).start()
    def start(self):
        if net.LOCAL and not self.auth.ok:
            self.auth.login(self.auth_id)
        if not self.auth.ok:
            self.vision.note('input', f'시작 차단 — {self.auth.label()} (로그인 필요)')
            return self.status()
        else:
            block = self.brain.start_block_reason()
            if block:
                self.vision.note('input', f'시작 차단 — {block}')
                return self.status()
            else:
                self.vision.reset()
                if not self.hands.focus_game():
                    self.vision.note('input', '⚠ 거상 창을 전면으로 올리지 못했습니다 — 캡처/입력이 실패할 수 있습니다')
                self.engine.start()
                self.brain.start()
                self._run_since = time.time()
                self._ensure_gato_analysis()
                return self.status()
    def _ensure_gato_analysis(self):
        def _worker():
            note = lambda s: self.vision.note('input', s)
            try:
                import traders_ctl
            except Exception as e:
                note(f'[고트] 전투 분석 확인 불가: {type(e).__name__}: {e}')
                return None
            try:
                note(f'[고트] {traders_ctl.ensure_battle_analysis(log=note)}')
            except traders_ctl.TradersError as e:
                note(f'[고트] 전투 분석 시작 실패: {e}')
            except Exception as e:
                note(f'[고트] 전투 분석 오류: {type(e).__name__}: {e}')
            finally:
                self._restore_game_focus()
        threading.Thread(target=_worker, daemon=True).start()
    def stop(self):
        self._sched_stop.set()
        self._sched['active'] = False
        self._sched['resting'] = False
        self._stop_bot()
        return self.status()
    def _stop_bot(self):
        self.brain.stop()
        self.engine.stop()
        self.hands.release_all()
    def stop_grace(self, author='', reason='', user_requested=True):
        self._sched_stop.set()
        self._sched['active'] = False
        self._sched['resting'] = False
        self.brain._stop_bot(reason or (f'■ 원격 정지({author})' if author else '■ 원격 정지'), user_requested=user_requested)
    def schedule_start(self, cycles, battles, rest_sec):
        def _result(ok, reason=''):
            status = self.status()
            result = {'ok': ok, 'reason': reason}
            if ok:
                result.update(cycles=cycles, battles=battles, rest_sec=rest_sec)
            status['schedule_result'] = result
            return status
        self._sched_stop.set()
        t = self._sched_thread
        if t and t.is_alive() and (t is not threading.current_thread()):
                    t.join(timeout=2.0)
        try:
            cycles = max(1, int(float(cycles)))
            battles = max(1, int(float(battles)))
            rest_sec = max(0, int(float(rest_sec)))
        except (TypeError, ValueError):
            self.vision.note('input', '스케쥴 값 오류 — 숫자로 입력')
            return _result(False, '값 오류 — 숫자로 입력')
        if net.LOCAL and not self.auth.ok:
            self.auth.login(self.auth_id)
        if not self.auth.ok:
            self.vision.note('input', f'스케쥴 차단 — {self.auth.label()} (로그인 필요)')
            return _result(False, f'{self.auth.label()} (로그인 필요)')
        else:
            block = self.brain.start_block_reason()
            if block:
                self.vision.note('input', f'스케쥴 차단 — {block}')
                return _result(False, block)
            else:
                s = config.load()
                s['sched_cycles'], s['sched_battles'], s['sched_rest_sec'] = (cycles, battles, rest_sec)
                if not config.save(s):
                    self.vision.note('input', '스케쥴 차단 — 설정 저장 실패')
                    return _result(False, '설정 저장 실패')
                else:
                    self._sched_stop.clear()
                    self._sched = {'active': True, 'cycle': 0, 'cycles': cycles, 'battles': 0, 'target': battles, 'resting': False, 'rest_left': 0}
                    self._sched_thread = threading.Thread(target=self._sched_loop, args=(cycles, battles, rest_sec), daemon=True)
                    self._sched_thread.start()
                    return _result(True)
    def schedule_stop(self):
        return self.stop()
    def _sched_loop(self, cycles, battles, rest_sec):
        start_total = self.brain.battle_count
        for c in range(1, cycles + 1):
            if self._sched_stop.is_set():
                break
            self._sched.update(cycle=c, battles=0, resting=False)
            base = self.brain.battle_count
            self.vision.note('input', f'[스케쥴] 사이클 {c}/{cycles} 시작 (목표 {battles}전투)')
            if not self.brain.running:
                self.start()
            self.brain.sched_target = base + battles
            while not self._sched_stop.is_set():
                done = self.brain.battle_count - base
                self._sched['battles'] = done
                if done >= battles:
                    break
                if not self.brain.running:
                    self.vision.note('input', '[스케쥴] 봇이 멈춰 스케쥴 중단')
                    self.notifier.text(f'⚠️ 스케쥴 중단 — 봇 정지 (사이클 {c}/{cycles}, 총 {self.brain.battle_count - start_total}전투)')
                    break
                time.sleep(1.0)
            if self._sched_stop.is_set():
                break
            if c < cycles and rest_sec > 0:
                self.vision.note('input', f'[스케쥴] 사이클 {c} 완료 — {rest_sec}초 휴식 (색적만 정지)')
                self._sched.update(resting=True, rest_left=rest_sec)
                self.brain.rest_mode = True
                end = time.time() + rest_sec
                try:
                    while not self._sched_stop.is_set():
                        left = int(round(end - time.time()))
                        if left <= 0:
                            break
                        self._sched['rest_left'] = left
                        if not self.brain.running:
                            self.vision.note('input', '[스케쥴] 휴식 중 봇 정지 — 스케쥴 중단')
                            self.notifier.text(f'⚠️ 스케쥴 중단 — 휴식 중 봇 정지 (사이클 {c}/{cycles})')
                            break
                        time.sleep(1.0)
                finally:
                    self.brain.rest_mode = False
                    self._sched['resting'] = False
        if not self._sched_stop.is_set():
            self.vision.note('input', '[스케쥴] 전체 완료')
            self.notifier.text(f'🏁 스케쥴 완료 — {cycles}사이클 · 총 {self.brain.battle_count - start_total}전투')
            self._stop_bot()
        self._sched.update(active=False, resting=False)
        self.brain.sched_target = None
    def _on_brain_stopped(self):
        self.engine.stop()
        self.hands.release_all()
    def _auto_restart_bot(self):
        """The bot stopped itself (a false no-fight timeout, a transient capture glitch, etc. - never
        a user/schedule stop, see Brain._auto_restart). Run the SAME sequence F3/the panel start button
        does, not just brain.start(): the engine was already stopped by _on_brain_stopped above, and
        the game window needs re-focusing."""
        self.vision.note('input', '[자동재시작] 재시작 시도')
        try:
            res = self.start()
            if not self.brain.running:
                self.vision.note('input', f'[자동재시작] 실패 — {self.brain.start_block_reason() or self.auth.label()}')
        except Exception as e:
            self.vision.note('input', f'[자동재시작] 오류: {type(e).__name__}: {e}')
    _WINS_TTL = 2.0
    def _find_windows_cached(self):
        now = time.time()
        if now - self._wins_at > self._WINS_TTL:
            self._wins = find_windows()
            self._wins_at = now
        return self._wins
    def tick(self, since_seq: int=0, chat_seq: int=0):
        return {'status': self.status(), 'events': self.vision.events_since(int(since_seq)), 'chat': self.chat(chat_seq)}
    def win_minimize(self):
        if webview.windows:
            webview.windows[0].minimize()
    def win_close(self):
        if webview.windows:
            webview.windows[0].destroy()
    @staticmethod
    def _clamp_size(w, h):
        try:
            w, h = (int(w), int(h))
        except (TypeError, ValueError):
            return None
        try:
            u = ctypes.windll.user32
            max_w, max_h = (u.GetSystemMetrics(0), u.GetSystemMetrics(1))
        except Exception:
            max_w, max_h = (3840, 2160)
        return (max(WIN_MIN_W, min(w, max_w)), max(WIN_MIN_H, min(h, max_h)))
    def win_resize(self, w, h):
        size = self._clamp_size(w, h)
        if size and webview.windows:
                webview.windows[0].resize(*size)
    def win_size_save(self, w, h):
        size = self._clamp_size(w, h)
        if not size:
            return
        else:
            s = config.load()
            s['win_w'], s['win_h'] = size
            config.save(s)
    def self_update(self):
        if os.environ.get('GATOSUPER_LAUNCHED') != '1':
            return {'ok': False, 'msg': '런처 실행이 아니라 자동 업데이트 불가'}
        else:
            if self.brain.running:
                self.stop()
            exe = sys.executable
            try:
                subprocess.Popen([exe, '--auto'], cwd=os.path.dirname(exe) or None)
            except Exception as e:
                return {'ok': False, 'msg': f'런처 재실행 실패: {type(e).__name__}: {e}'}
            def _exit_soon():
                time.sleep(0.8)
                try:
                    self._stop_bot()
                except Exception:
                    pass
                os._exit(0)
            threading.Thread(target=_exit_soon, daemon=True).start()
            return {'ok': True}
    def status(self):
        s = self.engine.stats()
        s['vision'] = self.vision.snapshot()
        s['admin'] = is_admin()
        s['battle_count'] = self.brain.battle_count
        s['auth'] = self.auth_status()
        s['schedule'] = dict(self._sched)
        s['monster'] = config.load().get('current_monster', '')
        s['update'] = {'available': self.auth.update_available(), 'current': net.CODE_VER, 'latest': self.auth.latest_patch}
        wins = self._find_windows_cached()
        s['window_found'] = bool(self.engine.hwnd) if s['running'] else bool(wins)
        s['window_count'] = len(wins)
        s['clients'] = self._client_states(wins) if len(wins) >= 2 else []
        s['gato'] = self.brain.gato_detected()
        return s
    def _client_states(self, wins):
        out = []
        main = self.engine.hwnd
        sub_i = 0
        for h in wins:
            if h == main:
                role = '메인'
            else:
                sub_i += 1
                role = f'서브{sub_i}'
            mx, my, mrgb = vision_scene_probe('main')
            pm = grab_hwnd_region(h, mx, my, mx + 1, my + 1)
            if pm is None:
                state = '판독불가'
            else:
                if vision_px_is(pm[0, 0], mrgb):
                    state = '메인화면'
                else:
                    pb = grab_hwnd_region(h, *combat.BATTLE_PIXEL_XY, combat.BATTLE_PIXEL_XY[0] + 1, combat.BATTLE_PIXEL_XY[1] + 1)
                    state = '전투' if pb is not None and int(pb.sum()) == combat.BATTLE_PIXEL_SUM else '기타'
            out.append({'role': role, 'state': state})
        return out
    def appear_records(self):
        return self.brain.get_appear_records()
    def kill_rank(self):
        return self.brain.get_kill_rank()
    def reset_count(self):
        self.brain.reset_count()
        return {'battle_count': self.brain.battle_count}
    def toggle_dump(self):
        on = not self.sniffer._dump
        path = None
        if on:
            os.makedirs(config.PACKET_DUMP_DIR, exist_ok=True)
            path = os.path.join(config.PACKET_DUMP_DIR, time.strftime('dump_%Y%m%d_%H%M%S.log'))
        self.sniffer.set_dump(on, path)
        return {'dump': on, 'path': path or ''}
    def _start_auth(self):
        def _loop():
            while True:
                self.auth.mob = config.load().get('current_monster', '')
                if self.auth_id:
                    if self.auth.login(self.auth_id):
                        self.vision.note('input', f'인증: {self.auth.label()}')
                        self._pull_settings()
                    else:
                        self.vision.note('input', f'인증 실패 — {self.auth.label()}')
                time.sleep(net.HEARTBEAT_SEC)
                if not self.auth.token:
                    continue
                cfg = config.load()
                self.auth.mob = cfg.get('current_monster', '') or self.brain.monster
                self.auth.state = {'running': bool(self.brain.running), 'battles': int(self.brain.battle_count), 'scene': (self.vision.snapshot() or {}).get('scene', '') or '', 'uptime': self._last_note, 'err': bool(find_window()), 'game': {**self._sched, 'cfg_cycles': int(cfg.get('sched_cycles', 3)), 'cfg_battles': int(cfg.get('sched_battles', 10)), 'cfg_rest': int(cfg.get('sched_rest_sec', 600))}}
                was_ok = self.auth.ok
                if not self.auth.heartbeat() and was_ok:
                    if self.brain.running:
                        self.stop_grace(reason=f'인증 끊김 — {self.auth.label()}', user_requested=False)
                    else:
                        self.vision.note('input', f'인증 끊김 — {self.auth.label()} → 정지')
                        self.stop()
                time.sleep(net.HEARTBEAT_SEC)

        threading.Thread(target=_loop, daemon=True).start()
    def login(self, auth_id):
        self.auth_id = str(auth_id or '').strip()
        s = config.load()
        s['auth_id'] = self.auth_id
        config.save(s)
        self.auth.mob = s.get('current_monster', '')
        if self.auth.login(self.auth_id):
            self.vision.note('input', f'인증: {self.auth.label()}')
            self._pull_settings()
        else:
            self.vision.note('input', f'인증 실패 — {self.auth.label()}')
        return self.auth_status()
    def logout(self):
        if self.brain.running:
            self.stop()
        self.auth.ok = False
        self.auth.token = ''
        self.auth.reason = ''
        self.vision.note('input', '로그아웃')
        return self.auth_status()
    def auth_status(self):
        a = self.auth
        return {'ok': a.ok, 'label': a.label(), 'reason': a.reason, 'days_left': a.days_left, 'credits': a.credits, 'banja': a.banja, 'notice': a.notice, 'auth_id': self.auth_id}
    def _pull_settings(self):
        remote = self.auth.get_settings()
        if remote is False:
            return
        else:
            if not (isinstance(remote, dict) and 'monsters' in remote):
                self._push_settings()
                return
            else:
                local = config.load()
                remote['auth_id'] = local.get('auth_id', self.auth_id)
                config.save(remote)
                self.vision.note('input', f'[{self.auth_id}] 서버 설정 불러옴')
    def _push_settings(self):
        s = config.load()
        s.pop('auth_id', None)
        self.auth.put_settings(s)
    def test_webhook(self, url=''):
        url = (url or config.load().get('discord_webhook', '')).strip()
        if not url:
            return '웹훅 URL이 비어 있습니다'
        else:
            self.notifier._send_discord(url, '[Gato_super] ✅ 웹훅 테스트')
            return '디스코드 테스트 전송'
    def test_ntfy(self, url=''):
        url = (url or config.load().get('ntfy_url', '')).strip()
        if not url:
            return 'ntfy URL이 비어 있습니다'
        else:
            self.notifier._send_ntfy(url, '[Gato_super] ✅ ntfy 테스트')
            return 'ntfy 테스트 전송'
    _CMD_START = {'run', 'on', 'go', 'start', '시작', '켜'}
    _CMD_STOP = {'꺼', 'quit', '종료', '정지', 'off', 'stop'}
    _CMD_STATUS = {'stat', '?', 'status', '상태'}
    _CHAT_CLICK = {'sangdan': (651, 648)}
    def _on_discord_command(self, content: str, author: str):
        c = content.strip().lstrip('!/ ')
        if not c:
            return
        else:
            if c.startswith('(상단)'):
                self._discord_chat(c[len('(상단)'):], 'sangdan')
                return
            else:
                if c.startswith('(일반)'):
                    self._discord_chat(c[len('(일반)'):], 'normal')
                    return
                else:
                    if c.startswith('(귓말'):
                        m = re.match('^\\(귓말([1-9]?)\\)(.*)$', c, re.S)
                        if m:
                            self._discord_whisper(int(m.group(1) or '1'), m.group(2))
                        else:
                            self.notifier.text('형식: (귓말) 메시지 / (귓말N) 메시지 (N=1~9)')
                        return None
                    else:
                        cl = c.lower()
                        if cl in self._CMD_START:
                            if self.brain.running:
                                self.notifier.text(f'이미 가동 중 ({author})')
                                return
                            else:
                                self.start()
                                if self.brain.running:
                                    self.notifier.text(f'▶ 원격 시작 ({author})')
                                else:
                                    self.notifier.text(f'⚠️ 시작 불가 ({author}) — {self.brain.start_block_reason() or self.auth.label()}')
                        else:
                            if cl in self._CMD_STOP:
                                if not self.brain.running:
                                    self.notifier.text(f'이미 정지 상태 ({author})')
                                else:
                                    if self.brain._shutdown_at is not None:
                                        self.notifier.text(f'이미 정지 예약됨 ({author})')
                                    else:
                                        self.stop_grace(author)
                            else:
                                if cl in self._CMD_STATUS:
                                    self._reply_status()
                                else:
                                    if cl in ['덤프', 'dump']:
                                        r = self.toggle_dump()
                                        self.notifier.text(f"🧪 패킷 덤프 {('ON' if r['dump'] else 'OFF')}" + (f"\n{r['path']}" if r['path'] else ''))
                                    else:
                                        threading.Thread(target=self._nlp_dispatch, args=(c, author), daemon=True).start()
    def _nlp_dispatch(self, text: str, author: str):
        p = self.auth.nlp_parse(text)
        intent = (p or {}).get('intent')
        if intent == 'start':
            self._on_discord_command('시작', author)
            return
        else:
            if intent == 'quit':
                self._on_discord_command('정지', author)
                return
            else:
                if intent == 'status':
                    self._reply_status()
                    return
                else:
                    if intent == 'whisper':
                        self.notifier.text('귓말은 `(귓말)내용` 형식으로 보내주세요')
                        return
                    else:
                        ans = self.auth.nlp_chat(text)
                        if ans:
                            self.notifier.text(ans)
    def _discord_chat(self, text: str, kind: str):
        if self.brain.running:
            self.notifier.text('봇 가동 중 — 정지 후 채팅 가능')
            return
        else:
            if not find_window():
                self.notifier.text('거상 창을 찾을 수 없습니다')
                return
            else:
                msg = text.strip()
                if not msg:
                    return
                else:
                    label = {'sangdan': '상단', 'normal': '일반'}.get(kind, kind)
                    self.vision.note('input', f'[디코→{label}] {msg}')
                    self.brain.type_chat(text, pre_click=self._CHAT_CLICK.get(kind))
    def _discord_whisper(self, slot: int, text: str):
        if self.brain.running:
            self.notifier.text('봇 가동 중 — 정지 후 귓말 가능')
            return
        else:
            if not find_window():
                self.notifier.text('거상 창을 찾을 수 없습니다')
                return
            else:
                if not text.strip():
                    return
                else:
                    self.vision.note('input', f'[디코→귓말{slot}] {text.strip()}')
                    try:
                        self.brain.send_whisper(slot, text)
                    except Exception as e:
                        self.vision.note('input', f'귓말 실패: {e}')
                        self.notifier.text(f'귓말 처리 오류: {e}')
    def _reply_status(self):
        img = self.brain._grab_main()
        st = '가동 중' if self.brain.running else '정지'
        scene = vision_detect_scene(img) if img is not None else 'unknown'
        label = {'main': '메인화면', 'battle': '전투화면'}.get(scene, '알 수 없음')
        self.notifier.image(f"📊 {st} · 화면 {label} · 몹 {self.brain.monster} · 전투 {self.brain.battle_count}회 · 거상창 {('감지' if img is not None else '없음')}", img)
    def events(self, since_seq: int=0):
        return self.vision.events_since(int(since_seq))
    def chat(self, since_seq: int=0):
        with self._chat_lock:
            return [c for c in self._chat_log if c['seq'] > int(since_seq)]
    def get_config(self):
        s = config.load()
        s['stamp'] = config.settings_stamp(s)
        s['catalog'] = sorted(config.MOB_CATALOG.keys())
        s['categories'] = config.MOB_CATEGORIES
        s['mob_category'] = {n: m.get('category') or '기타' for n, m in config.MOB_CATALOG.items()}
        return s
    def set_monster(self, name):
        s = config.load()
        if name in config.MOB_CATALOG:
            s['current_monster'] = name
            config.save(s)
        return self.get_config()
    def _cfg_error(self, msg):
        self.vision.note('input', f'설정 저장 실패 — {msg}')
        out = self.get_config()
        out['error'] = msg
        return out
    def _stamp_conflict(self, s, stamp):
        if not stamp or str(stamp) == config.settings_stamp(s):
            return None
        else:
            out = self.get_config()
            out['conflict'] = True
            out['error'] = '그 사이 설정이 다른 곳에서 바뀌었습니다 — 한 번 더 누르면 덮어씁니다'
            self.vision.note('input', '설정 저장 보류 — 그 사이 설정이 바뀜 (재시도하면 덮어씀)')
            return out
    def save_monster_cfg(self, name, cfg, stamp=None):
        s = config.load()
        if name not in config.MOB_CATALOG:
            return self._cfg_error(f'알 수 없는 몹입니다: {name}')
        else:
            conflict = self._stamp_conflict(s, stamp)
            if conflict:
                return conflict
            else:
                try:
                    clean = config.validate_monster_cfg(cfg, s['monsters'].get(name))
                except config.SettingsError as e:
                    return self._cfg_error(str(e))
                s['monsters'][name] = clean
                s['current_monster'] = name
                if not config.save(s):
                    return self._cfg_error('설정 파일을 쓸 수 없습니다')
                else:
                    self._push_settings()
                    return self.get_config()
    def save_common(self, common, stamp=None):
        s = config.load()
        conflict = self._stamp_conflict(s, stamp)
        if conflict:
            return conflict
        else:
            try:
                s.update(config.validate_common(common, s))
            except config.SettingsError as e:
                return self._cfg_error(str(e))
            if not config.save(s):
                return self._cfg_error('설정 파일을 쓸 수 없습니다')
            else:
                self._push_settings()
                return self.get_config()
    def portrait(self, name):
        path = config.portrait_path(name)
        if not path or not os.path.exists(path):
            return ''
        else:
            try:
                import base64
                with open(path, 'rb') as f:
                    b64 = base64.b64encode(f.read()).decode('ascii')
                return 'data:image/png;base64,' + b64
            except Exception:
                return ''
def _proc_exe(pid: int) -> str:
    _k = ctypes.windll.kernel32
    _k.OpenProcess.argtypes = [ctypes.wintypes.DWORD, ctypes.wintypes.BOOL, ctypes.wintypes.DWORD]
    _k.OpenProcess.restype = ctypes.wintypes.HANDLE
    _k.CloseHandle.argtypes = [ctypes.wintypes.HANDLE]
    _k.QueryFullProcessImageNameW.argtypes = [ctypes.wintypes.HANDLE, ctypes.wintypes.DWORD, ctypes.wintypes.LPWSTR, ctypes.POINTER(ctypes.wintypes.DWORD)]
    h = _k.OpenProcess(4096, False, pid)
    if not h:
        return ''
    else:
        try:
            buf = ctypes.create_unicode_buffer(ctypes.wintypes.MAX_PATH)
            sz = ctypes.wintypes.DWORD(ctypes.wintypes.MAX_PATH)
            ok = ctypes.windll.kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(sz))
            return buf.value.lower() if ok else ''
        finally:
            ctypes.windll.kernel32.CloseHandle(h)
def close_previous_instances():
    my_pid = os.getpid()
    titles = {APP_TITLE, 'Prism'}
    def _collect(hwnd, acc):
        if not (win32gui.IsWindowVisible(hwnd) and win32gui.GetWindowText(hwnd) in titles):
            return None
        else:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            if pid == my_pid:
                return
            else:
                exe = os.path.basename(_proc_exe(pid))
                if exe.startswith('python') or exe.startswith('gato_super'):
                    acc.append(hwnd)
    for _ in range(5):
        found = []
        win32gui.EnumWindows(_collect, found)
        if not found:
            return
        else:
            for h in found:
                win32gui.PostMessage(h, win32con.WM_CLOSE, 0, 0)
            time.sleep(0.6)
def install_error_hooks(api):
    import traceback
    def _report(kind, exc_type, exc, tb):
        txt = ''.join(traceback.format_exception(exc_type, exc, tb))
        try:
            api.vision.note('input', f'⚠ 내부 오류({kind}): {exc_type.__name__}: {exc}')
        except Exception:
            pass
        try:
            with open(os.path.join(config.BASE_DIR, 'gato_traceback.log'), 'a', encoding='utf-8') as _f:
                _f.write('--- ' + kind + ' ---\n' + txt + '\n')
        except Exception:
            pass
        try:
            api.auth.report_error(kind, txt)
        except Exception:
            return None
    _orig_sys_hook = sys.excepthook
    def _sys_hook(exc_type, exc, tb):
        _report('crash', exc_type, exc, tb)
        _orig_sys_hook(exc_type, exc, tb)
    sys.excepthook = _sys_hook
    def _thread_hook(args):
        if args.exc_type is SystemExit:
            return
        else:
            name = args.thread.name if args.thread else '?'
            _report(f'thread:{name}', args.exc_type, args.exc_value, args.exc_traceback)
    threading.excepthook = _thread_hook
def start_f10_hotkey(api):
    """Global hotkeys (polled, so they work while the game has focus):
    F3 = 전투 시작, F4 = 전투 종료, F10 = toggle (kept from the original)."""
    def _loop():
        user32 = ctypes.windll.user32
        VK_F3, VK_F4, VK_F10 = 114, 115, 121
        prev = {VK_F3: False, VK_F4: False, VK_F10: False}
        last = {VK_F3: 0.0, VK_F4: 0.0, VK_F10: 0.0}
        while True:
            now = time.time()
            for vk in (VK_F3, VK_F4, VK_F10):
                down = bool(user32.GetAsyncKeyState(vk) & 32768)
                if down and (not prev[vk]) and (now - last[vk] > 0.3):
                    last[vk] = now
                    try:
                        running = api.brain.running
                        if vk == VK_F3 and not running:
                            api.vision.note('input', '[F3] 전투 시작')
                            api.start()
                        elif vk == VK_F4 and running:
                            api.vision.note('input', '[F4] 전투 종료')
                            api.stop()
                        elif vk == VK_F10:
                            api.stop() if running else api.start()
                    except Exception:
                        pass
                prev[vk] = down
            time.sleep(0.015)
    threading.Thread(target=_loop, daemon=True).start()
def main():
    global _API
    ensure_admin()
    close_previous_instances()
    api = Api()
    _API = api
    install_error_hooks(api)
    start_f10_hotkey(api)
    def _on_closed():
        api.brain.stop()
        api.engine.stop()
        api.sniffer.stop()
        api.bot_poller.stop()
        if getattr(api, 'remote', None):
            api.remote.close()
        if getattr(api, 'link', None):
            api.link.close()
    cfg0 = config.load()
    win_w, win_h = Api._clamp_size(cfg0.get('win_w', WIN_DEF_W), cfg0.get('win_h', WIN_DEF_H)) or (WIN_DEF_W, WIN_DEF_H)
    try:
        screen_h = ctypes.windll.user32.GetSystemMetrics(1)
    except Exception:
        screen_h = 1080
    win_y = max(0, (screen_h - win_h) // 2)
    window = webview.create_window(APP_TITLE, os.path.join(UI_DIR, 'index.html'), js_api=api, x=10, y=win_y, width=win_w, height=win_h, min_size=(WIN_MIN_W, WIN_MIN_H), background_color='#0d0f14', frameless=True, easy_drag=False)
    window.events.closed += _on_closed
    webview.start()
    os._exit(0)
_API = None
if __name__ == '__main__':
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        import traceback
        txt = traceback.format_exc()
        with open(os.path.join(config.BASE_DIR, 'prism_crash.log'), 'w', encoding='utf-8') as f:
            f.write(txt)
        if _API is not None:
            try:
                _API.auth.report_error('crash', txt, wait=True)
            except Exception:
                pass
        raise