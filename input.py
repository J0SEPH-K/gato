# Decompiled with PyLingual (https://pylingual.io)
# Internal filename: 'input.py'
# Bytecode version: 3.11a7e (3495)
# Source timestamp: 2026-07-28 09:03:05 UTC (1785229385)

from __future__ import annotations
import ctypes
import ctypes.wintypes
import os
import queue
import random
import sys
import threading
import time
import win32api
import win32con
import win32gui
import win32process
from capture import find_window, REF_W, REF_H

user32 = ctypes.windll.user32
try:
    ctypes.windll.winmm.timeBeginPeriod(1)   # 1 ms timer: 60 Hz loops and 4 ms cursor checks need it
except Exception:
    pass
def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False
def ensure_admin() -> bool:
    if is_admin():
        return True
    else:
        if os.environ.get('PRISM_NO_ELEVATE') == '1':
            return False
        else:
            script = os.path.abspath(sys.argv[0])
            pyw = os.path.join(os.path.dirname(sys.executable), 'pythonw.exe')
            launcher = pyw if os.path.exists(pyw) else sys.executable
            ret = ctypes.windll.shell32.ShellExecuteW(None, 'runas', launcher, f'\"{script}\"', None, 1)
            if ret > 32:
                sys.exit(0)
            return False
_ULONG_PTR = ctypes.wintypes.WPARAM
class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [('wVk', ctypes.c_ushort), ('wScan', ctypes.c_ushort), ('dwFlags', ctypes.c_ulong), ('time', ctypes.c_ulong), ('dwExtraInfo', _ULONG_PTR)]
class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [('dx', ctypes.c_long), ('dy', ctypes.c_long), ('mouseData', ctypes.c_ulong), ('dwFlags', ctypes.c_ulong), ('time', ctypes.c_ulong), ('dwExtraInfo', _ULONG_PTR)]
class _INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [('ki', _KEYBDINPUT), ('mi', _MOUSEINPUT)]
    _anonymous_ = ('u',)
    _fields_ = [('type', ctypes.c_ulong), ('u', _U)]
_INPUT_MOUSE = 0
_INPUT_KEYBOARD = 1
_KEYUP = 2
_SCANCODE = 8
_EXTENDED = 1
_M_LEFTDOWN, _M_LEFTUP = (2, 4)
_M_RIGHTDOWN, _M_RIGHTUP = (8, 16)
_M_MOVE = 1
_M_ABSOLUTE = 32768
_M_VIRTUALDESK = 16384
# Input humanisation. XIGNCODE does not care that SendInput is used (a real mouse
# goes through the same call), but a click that lands on the exact same integer
# pixel every round with a fixed 80 ms hold is the cheapest thing to fingerprint.
JITTER_PX = 2

def _jit(v, amp=JITTER_PX):
    """Gaussian jitter, clamped to +/-amp so a click never leaves its cell."""
    return int(round(v + max(-amp, min(amp, random.gauss(0, amp / 2.0)))))
def _send(inp: _INPUT) -> None:
    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(_INPUT))
def _abs_xy(sx: int, sy: int):
    vx = user32.GetSystemMetrics(76)
    vy = user32.GetSystemMetrics(77)
    vw = user32.GetSystemMetrics(78)
    vh = user32.GetSystemMetrics(79)
    nx = int((sx - vx) * 65535 / max(1, vw - 1))
    ny = int((sy - vy) * 65535 / max(1, vh - 1))
    return (nx, ny)
def _key_event(scan: int, flags: int) -> None:
    inp = _INPUT(type=_INPUT_KEYBOARD)
    inp.ki = _KEYBDINPUT(0, scan, flags, 0, 0)
    _send(inp)
def _vk_event(vk: int, flags: int) -> None:
    inp = _INPUT(type=_INPUT_KEYBOARD)
    inp.ki = _KEYBDINPUT(vk, 0, flags, 0, 0)
    _send(inp)
def _mouse_event(flags: int, dx: int=0, dy: int=0) -> None:
    inp = _INPUT(type=_INPUT_MOUSE)
    inp.mi = _MOUSEINPUT(dx, dy, 0, flags, 0, 0)
    _send(inp)
VK = {'enter': 13, 'esc': 27, 'space': 32, 'tab': 9, 'backspace': 8, 'shift': 16, 'ctrl': 17, 'alt': 18, 'up': 38, 'down': 40, 'left': 37, 'right': 39, 'insert': 45, 'delete': 46, 'home': 36, 'end': 35, 'pageup': 33, 'pagedown': 34}
for _i in range(1, 13):
    VK[f'f{_i}'] = 112 + _i - 1
for _c in '0123456789':
    VK[_c] = ord(_c)
for _c in 'abcdefghijklmnopqrstuvwxyz':
    VK[_c] = ord(_c.upper())
_EXT_KEYS = {'left', 'up', 'pageup', 'pagedown', 'insert', 'end', 'down', 'delete', 'home', 'right'}
VK_HANGUL = 21
class Hands:
    FG_SETTLE = 0.3
    def __init__(self, hwnd_get=None, log=None):
        self._hwnd_get = hwnd_get or (lambda: 0)
        self._log = log or (lambda s: None)
        self._q = queue.Queue()
        self._mouse_held = None
        self._fg_at = 0.0
        self._pin = None             # (screen_x, screen_y, expires_monotonic): where the cursor must stay
        self.guard_enabled = False   # set by Brain while the macro runs
        self.guard_fixes = 0         # times the guard pulled a drifting cursor back
        self._thread = threading.Thread(target=self._worker, daemon=True, name='prism-hands')
        self._thread.start()
        self._guard_thread = threading.Thread(target=self._guard_loop, daemon=True, name='prism-cursor-guard')
        self._guard_thread.start()
    def _worker(self):
        # ***<module>.Hands._worker: Failure: Different control flow
        while True:
            try:
                fn, done, box = self._q.get()
                try:
                    box[0] = fn()
                except Exception as e:
                    box[0] = False
                    self._log(f'입력 오류: {type(e).__name__}: {e}')
            finally:
                if done is not None:
                    done.set()
    PIN_TTL = 2.5

    def _set_pin(self, sx: int, sy: int) -> None:
        self._pin = (sx, sy, time.monotonic() + self.PIN_TTL)

    def _touch_pin(self) -> None:
        pin = self._pin
        if pin is not None:
            self._pin = (pin[0], pin[1], time.monotonic() + self.PIN_TTL)

    def _guard_loop(self) -> None:
        """Keeps the cursor on the last commanded point while the macro is acting. If the real
        mouse (or anything else) moves it, it is put back within ~5 ms, so a cast or click never
        lands where the cursor drifted to."""
        pt = ctypes.wintypes.POINT()
        while True:
            time.sleep(0.004)
            pin = self._pin
            if pin is None or not self.guard_enabled:
                continue
            if time.monotonic() > pin[2]:
                self._pin = None
                continue
            user32.GetCursorPos(ctypes.byref(pt))
            if pt.x != pin[0] or pt.y != pin[1]:
                user32.SetCursorPos(pin[0], pin[1])
                self.guard_fixes += 1

    def _do(self, fn, wait: bool):
        if not wait:
            self._q.put((fn, None, [None]))
            return
        else:
            done = threading.Event()
            box = [None]
            self._q.put((fn, done, box))
            done.wait(timeout=10.0)
            return box[0]
    def _hwnd(self) -> int:
        hwnd = self._hwnd_get()
        if hwnd and win32gui.IsWindow(hwnd):
            return hwnd
        else:
            return find_window()
    def _foreground(self) -> int:
        hwnd = self._hwnd()
        if not hwnd:
            self._log('입력 스킵 — 거상 창 없음')
            return 0
        else:
            if win32gui.GetForegroundWindow() != hwnd:
                cur_tid = win32api.GetCurrentThreadId()
                fg = win32gui.GetForegroundWindow()
                fg_tid = win32process.GetWindowThreadProcessId(fg)[0] if fg else 0
                attached = False
                if fg_tid and fg_tid != cur_tid:
                        attached = bool(user32.AttachThreadInput(cur_tid, fg_tid, True))
                try:
                    win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
                    try:
                        win32gui.SetForegroundWindow(hwnd)
                    except Exception:
                        pass
                finally:
                    if attached:
                        user32.AttachThreadInput(cur_tid, fg_tid, False)
                self._fg_at = time.monotonic()
                time.sleep(0.15)
                if win32gui.GetForegroundWindow() != hwnd:
                    self._log('입력 스킵 — 거상 창 전면 전환 실패')
                    return 0
                else:
                    self._log('전면 전환')
            if self._fg_at:
                remain = self.FG_SETTLE - (time.monotonic() - self._fg_at)
                if remain > 0:
                    time.sleep(remain)
            return hwnd
    def focus_game(self) -> bool:
        try:
            return bool(self._foreground())
        except Exception as e:
            self._log(f'전면 전환 오류: {e}')
            return False
    @staticmethod
    def _to_screen(hwnd: int, x: int, y: int):
        try:
            _, _, cw, ch = win32gui.GetClientRect(hwnd)
            if cw and ch and ((cw, ch) != (REF_W, REF_H)):
                        x = x * cw / REF_W
                        y = y * ch / REF_H
        except Exception:
            pass
        return win32gui.ClientToScreen(hwnd, (int(round(x)), int(round(y))))
    @staticmethod
    def _press_key(name: str, hold: float):
        name = name.lower()
        scan = user32.MapVirtualKeyW(VK[name], 0)
        flags = _SCANCODE | (_EXTENDED if name in _EXT_KEYS else 0)
        _key_event(scan, flags)
        time.sleep(hold)
        _key_event(scan, flags | _KEYUP)
    def move(self, x, y, wait=False):
        def _fn():
            hwnd = self._foreground()
            if not hwnd:
                return False
            else:
                sx, sy = self._to_screen(hwnd, x, y)
                self._pin = None
                ok = self._land(sx, sy)
                if ok:
                    self._set_pin(sx, sy)
                return ok
        return self._do(_fn, wait)
    def move_nofg(self, x, y, wait=False):
        def _fn():
            hwnd = self._hwnd()
            if not hwnd:
                return False
            else:
                self._pin = None     # explicit park: the cursor guard must not drag it back to the last click point
                try:
                    user32.SetCursorPos(*self._to_screen(hwnd, x, y))
                except Exception:
                    return False
                return True
        return self._do(_fn, wait)
    @staticmethod
    def _land(sx: int, sy: int) -> bool:
        """SetCursorPos, then read the cursor back; retry so a click never fires off-target."""
        pt = ctypes.wintypes.POINT()
        for _ in range(4):
            user32.SetCursorPos(sx, sy)
            user32.GetCursorPos(ctypes.byref(pt))
            if pt.x == sx and pt.y == sy:
                return True
            time.sleep(0.004)
        return False
    def click(self, x, y, button='left', down_ms=0.08, wait=False):
        def _fn():
            hwnd = self._foreground()
            if not hwnd:
                return False
            else:
                sx, sy = self._to_screen(hwnd, _jit(x), _jit(y))
                nx, ny = _abs_xy(sx, sy)
                absf = _M_ABSOLUTE | _M_VIRTUALDESK
                down_ms = max(0.02, down_ms * random.uniform(0.7, 1.35))
                self._pin = None
                if not self._land(sx, sy):
                    self._log(f'클릭 스킵 — 커서 안착 실패 ({sx},{sy})')
                    return False
                self._set_pin(sx, sy)            # guard holds the cursor here through the click
                _mouse_event(_M_MOVE | absf, nx, ny)
                time.sleep(random.uniform(0.008, 0.026))
                if not self._land(sx, sy):
                    self._log(f'클릭 스킵 — 커서 이탈 ({sx},{sy})')
                    return False
                d, u = (_M_LEFTDOWN, _M_LEFTUP) if button == 'left' else (_M_RIGHTDOWN, _M_RIGHTUP)
                try:
                    _mouse_event(d | absf, nx, ny)
                    time.sleep(down_ms)
                finally:
                    _mouse_event(u | absf, nx, ny)
                return True
        return self._do(_fn, wait)
    def mouse_hold(self, x, y, button='right', wait=False):
        def _fn():
            hwnd = self._foreground()
            if not hwnd:
                return False
            else:
                sx, sy = self._to_screen(hwnd, x, y)
                nx, ny = _abs_xy(sx, sy)
                absf = _M_ABSOLUTE | _M_VIRTUALDESK
                if not self._land(sx, sy):
                    self._log(f'홀드 스킵 — 커서 안착 실패 ({sx},{sy})')
                    return False
                _mouse_event(_M_MOVE | absf, nx, ny)
                time.sleep(0.012)
                _mouse_event((_M_LEFTDOWN if button == 'left' else _M_RIGHTDOWN) | absf, nx, ny)
                self._mouse_held = button
                return True
        return self._do(_fn, wait)
    def mouse_release(self, button=None, wait=False):
        def _fn():
            b = button or self._mouse_held
            if b:
                _mouse_event(_M_LEFTUP if b == 'left' else _M_RIGHTUP)
                self._mouse_held = None
            return True
        return self._do(_fn, wait)
    def press(self, key, hold=0.05, wait=False):
        def _fn():
            self._touch_pin()
            if not self._foreground():
                return False
            else:
                self._press_key(key, hold)
                return True
        return self._do(_fn, wait)
    def key_hold(self, key, wait=False):
        def _fn():
            self._touch_pin()
            if not self._foreground():
                return False
            else:
                n = key.lower()
                flags = _SCANCODE | (_EXTENDED if n in _EXT_KEYS else 0)
                _key_event(user32.MapVirtualKeyW(VK[n], 0), flags)
                return True
        return self._do(_fn, wait)
    def key_release(self, key, wait=False):
        def _fn():
            n = key.lower()
            flags = _SCANCODE | (_EXTENDED if n in _EXT_KEYS else 0) | _KEYUP
            _key_event(user32.MapVirtualKeyW(VK[n], 0), flags)
            return True
        return self._do(_fn, wait)
    def combo(self, *keys, hold=0.05, wait=False):
        def _fn():
            if not self._foreground():
                return False
            else:
                mods = [k.lower() for k in keys[:(-1)]]
                for m in mods:
                    _key_event(user32.MapVirtualKeyW(VK[m], 0), _SCANCODE)
                time.sleep(0.02)
                self._press_key(keys[(-1)], hold)
                for m in reversed(mods):
                    _key_event(user32.MapVirtualKeyW(VK[m], 0), _SCANCODE | _KEYUP)
                return True
        return self._do(_fn, wait)
    def keys_together(self, *keys, hold=0.05, wait=False):
        def _fn():
            if not self._foreground():
                return False
            else:
                names = [k.lower() for k in keys]
                for n in names:
                    flags = _SCANCODE | (_EXTENDED if n in _EXT_KEYS else 0)
                    _key_event(user32.MapVirtualKeyW(VK[n], 0), flags)
                time.sleep(hold)
                for n in reversed(names):
                    flags = _SCANCODE | (_EXTENDED if n in _EXT_KEYS else 0)
                    _key_event(user32.MapVirtualKeyW(VK[n], 0), flags | _KEYUP)
                return True
        return self._do(_fn, wait)
    def press_vk(self, vk, shift=False, wait=False):
        def _fn():
            if not self._foreground():
                return False
            else:
                if shift:
                    _key_event(user32.MapVirtualKeyW(VK['shift'], 0), _SCANCODE)
                _vk_event(int(vk), 0)
                time.sleep(0.03)
                _vk_event(int(vk), _KEYUP)
                if shift:
                    _key_event(user32.MapVirtualKeyW(VK['shift'], 0), _SCANCODE | _KEYUP)
                return True
        return self._do(_fn, wait)
    def toggle_hangul(self, wait=False):
        def _fn():
            if not self._foreground():
                return False
            else:
                _vk_event(VK_HANGUL, 0)
                time.sleep(0.03)
                _vk_event(VK_HANGUL, _KEYUP)
                return True
        return self._do(_fn, wait)
    def clear_pending(self):
        try:
            while True:
                fn, done, box = self._q.get_nowait()
                box[0] = False
                if done is not None:
                    done.set()
        except queue.Empty:
            return None
    def release_all(self):
        self._pin = None
        self.clear_pending()
        if self._mouse_held:
            self.mouse_release(wait=True)