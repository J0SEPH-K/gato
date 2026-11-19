# Decompiled with PyLingual (https://pylingual.io)
# Internal filename: 'capture.py'
# Bytecode version: 3.11a7e (3495)
# Source timestamp: 2026-09-14 10:45:15 UTC (1789382715)

from __future__ import annotations
import ctypes
import ctypes.wintypes
import os
import threading
import time
from collections import deque
import cv2
import numpy as np
import win32con
import win32gui
import win32process
import wgc
PROCESS_NAME = 'gersang.exe'
REF_W, REF_H = (1024, 768)

gdi32 = ctypes.WinDLL('gdi32', use_last_error=True)
user32 = ctypes.WinDLL('user32', use_last_error=True)
kernel32 = ctypes.windll.kernel32
BI_RGB = 0
DIB_RGB_COLORS = 0
class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [('biSize', ctypes.wintypes.DWORD), ('biWidth', ctypes.wintypes.LONG), ('biHeight', ctypes.wintypes.LONG), ('biPlanes', ctypes.wintypes.WORD), ('biBitCount', ctypes.wintypes.WORD), ('biCompression', ctypes.wintypes.DWORD), ('biSizeImage', ctypes.wintypes.DWORD), ('biXPelsPerMeter', ctypes.wintypes.LONG), ('biYPelsPerMeter', ctypes.wintypes.LONG), ('biClrUsed', ctypes.wintypes.DWORD), ('biClrImportant', ctypes.wintypes.DWORD)]
class BITMAPINFO(ctypes.Structure):
    _fields_ = [('bmiHeader', BITMAPINFOHEADER), ('bmiColors', ctypes.wintypes.DWORD * 3)]
_W = ctypes.wintypes
_c_int = ctypes.c_int
gdi32.CreateCompatibleDC.argtypes = [_W.HDC]
gdi32.CreateCompatibleDC.restype = _W.HDC
gdi32.CreateCompatibleBitmap.argtypes = [_W.HDC, _c_int, _c_int]
gdi32.CreateCompatibleBitmap.restype = _W.HBITMAP
gdi32.SelectObject.argtypes = [_W.HDC, _W.HGDIOBJ]
gdi32.SelectObject.restype = _W.HGDIOBJ
gdi32.BitBlt.argtypes = [_W.HDC, _c_int, _c_int, _c_int, _c_int, _W.HDC, _c_int, _c_int, _W.DWORD]
gdi32.BitBlt.restype = _W.BOOL
gdi32.GetDIBits.argtypes = [_W.HDC, _W.HBITMAP, _W.UINT, _W.UINT, ctypes.c_void_p, ctypes.POINTER(BITMAPINFO), _W.UINT]
gdi32.GetDIBits.restype = _c_int
gdi32.DeleteObject.argtypes = [_W.HGDIOBJ]
gdi32.DeleteObject.restype = _W.BOOL
gdi32.DeleteDC.argtypes = [_W.HDC]
gdi32.DeleteDC.restype = _W.BOOL
user32.GetDC.argtypes = [_W.HWND]
user32.GetDC.restype = _W.HDC
user32.ReleaseDC.argtypes = [_W.HWND, _W.HDC]
user32.ReleaseDC.restype = _c_int
def _get_process_exe(pid: int) -> str:
    PROCESS_QUERY_LIMITED_INFORMATION = 4096
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ''
    else:
        try:
            buf = ctypes.create_unicode_buffer(ctypes.wintypes.MAX_PATH)
            size = ctypes.wintypes.DWORD(ctypes.wintypes.MAX_PATH)
            ok = kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size))
            return buf.value.lower() if ok else ''
        finally:
            kernel32.CloseHandle(handle)
def find_windows(process_name: str=PROCESS_NAME) -> list:
    """Enumerates all game windows for this process name. When GATO_TARGET_PID
    is set (one real game client per account under 다클), this restricts the
    result to that single PID's window(s) -- without it, the first multi-
    instance run would have N bot processes all race to grab whichever
    window EnumWindows happens to return first, each controlling a RANDOM
    account's client instead of its own. Each bot process for 다클 must be
    launched with its own GATO_TARGET_PID pointing at the pid it actually
    logged into.

    A single Gersang.exe process owns several windows (the real game window
    titled exactly 'Gersang', plus helper windows like 'GDI+ Window
    (Gersang.exe)' and 'DIEmWin' that also have a non-empty title and so
    also pass the old filter). Observed live 2026-11-18: right after
    launch, EnumWindows can return the helper window before the real one,
    and the helper window stays at a degenerate 1x1 client rect forever --
    callers that grab the first match get a window that will never show
    real content. Sort results so an exact title match ('Gersang') comes
    first, which is stable regardless of enumeration order.
    """
    target_pid = os.environ.get('GATO_TARGET_PID')
    target_pid = int(target_pid) if target_pid else None
    result = []
    def _enum(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return
        else:
            if win32gui.GetWindowTextLength(hwnd) == 0:
                return
            else:
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                if target_pid is not None and pid != target_pid:
                    return
                if _get_process_exe(pid).endswith('\\' + process_name):
                    result.append(hwnd)
    win32gui.EnumWindows(_enum, None)
    result.sort(key=lambda h: 0 if win32gui.GetWindowText(h) == 'Gersang' else 1)
    return result
def find_window(process_name: str=PROCESS_NAME) -> int:
    result = find_windows(process_name)
    return result[0] if result else 0
def grab_once(process_name: str=PROCESS_NAME, normalize: bool=True) -> 'np.ndarray | None':
    return grab_hwnd(find_window(process_name), normalize=normalize)
def grab_hwnd_after(hwnd: int, after: float, timeout: float=0.25, stop=None, normalize: bool=True) -> 'np.ndarray | None':
    if not hwnd or (stop is not None and stop()):
        return None
    else:
        bgr = wgc.grab_after(hwnd, after, timeout=timeout, stop=stop)
        if bgr is None:
            return
        else:
            h, w = bgr.shape[:2]
            if normalize and (w, h) != (REF_W, REF_H):
                    bgr = cv2.resize(bgr, (REF_W, REF_H), interpolation=cv2.INTER_AREA)
            return None if stop is not None and stop() else bgr
def grab_hwnd(hwnd: int, normalize: bool=True) -> 'np.ndarray | None':
    if not hwnd:
        return None
    bgr = wgc.grab(hwnd)
    if bgr is not None:
        h, w = bgr.shape[:2]
        if normalize and (w, h) != (REF_W, REF_H):
            bgr = cv2.resize(bgr, (REF_W, REF_H), interpolation=cv2.INTER_AREA)
        return bgr
    try:
        left, top, right, bottom = win32gui.GetClientRect(hwnd)
    except win32gui.error:
        return None
    w, h = (right - left, bottom - top)
    if w <= 0 or h <= 0:
        return None
    hwnd_dc = user32.GetDC(hwnd)
    if not hwnd_dc:
        return None
    mem_dc = hbmp = old = None
    try:
        mem_dc = gdi32.CreateCompatibleDC(hwnd_dc)
        hbmp = gdi32.CreateCompatibleBitmap(hwnd_dc, w, h)
        old = gdi32.SelectObject(mem_dc, hbmp)
        if not gdi32.BitBlt(mem_dc, 0, 0, w, h, hwnd_dc, 0, 0, win32con.SRCCOPY):
            return None
        buf = ctypes.create_string_buffer(w * h * 4)
        bmi = BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = w
        bmi.bmiHeader.biHeight = -h
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        bmi.bmiHeader.biCompression = BI_RGB
        gdi32.SelectObject(mem_dc, old)
        lines = gdi32.GetDIBits(mem_dc, hbmp, 0, h, buf, ctypes.byref(bmi), DIB_RGB_COLORS)
        gdi32.SelectObject(mem_dc, hbmp)
        if lines != h:
            return None
        bgra = np.frombuffer(buf, np.uint8).reshape(h, w, 4)
        bgr = np.ascontiguousarray(bgra[:, :, :3])
        if normalize and (w, h) != (REF_W, REF_H):
            bgr = cv2.resize(bgr, (REF_W, REF_H), interpolation=cv2.INTER_AREA)
        return bgr
    finally:
        if mem_dc and old:
            gdi32.SelectObject(mem_dc, old)
        if hbmp:
            gdi32.DeleteObject(hbmp)
        if mem_dc:
            gdi32.DeleteDC(mem_dc)
        user32.ReleaseDC(hwnd, hwnd_dc)


def grab_hwnd_region(hwnd: int, x0: int, y0: int, x1: int, y1: int) -> 'np.ndarray | None':
    if not hwnd:
        return None
    try:
        left, top, right, bottom = win32gui.GetClientRect(hwnd)
    except win32gui.error:
        return None
    cw, ch = (right - left, bottom - top)
    if (cw, ch) != (REF_W, REF_H):
        return None
    w, h = (x1 - x0, y1 - y0)
    if w <= 0 or h <= 0 or x1 > cw or y1 > ch:
        return None
    f = wgc.grab(hwnd)
    if f is not None:
        if f.shape[:2] != (REF_H, REF_W):
            return None
        return np.ascontiguousarray(f[y0:y1, x0:x1])
    hwnd_dc = user32.GetDC(hwnd)
    if not hwnd_dc:
        return None
    mem_dc = hbmp = old = None
    try:
        mem_dc = gdi32.CreateCompatibleDC(hwnd_dc)
        hbmp = gdi32.CreateCompatibleBitmap(hwnd_dc, w, h)
        old = gdi32.SelectObject(mem_dc, hbmp)
        if not gdi32.BitBlt(mem_dc, 0, 0, w, h, hwnd_dc, x0, y0, win32con.SRCCOPY):
            return None
        buf = ctypes.create_string_buffer(w * h * 4)
        bmi = BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = w
        bmi.bmiHeader.biHeight = -h
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        bmi.bmiHeader.biCompression = BI_RGB
        gdi32.SelectObject(mem_dc, old)
        lines = gdi32.GetDIBits(mem_dc, hbmp, 0, h, buf, ctypes.byref(bmi), DIB_RGB_COLORS)
        gdi32.SelectObject(mem_dc, hbmp)
        if lines != h:
            return None
        bgra = np.frombuffer(buf, np.uint8).reshape(h, w, 4)
        return np.ascontiguousarray(bgra[:, :, :3])
    finally:
        if mem_dc and old:
            gdi32.SelectObject(mem_dc, old)
        if hbmp:
            gdi32.DeleteObject(hbmp)
        if mem_dc:
            gdi32.DeleteDC(mem_dc)
        user32.ReleaseDC(hwnd, hwnd_dc)


class CaptureEngine:
    REFIND_INTERVAL = 1.0
    def __init__(self, fps: float=10.0, process_name: str=PROCESS_NAME):
        self.fps = fps
        self.process_name = process_name
        self._hwnd = 0
        self._pid = 0
        self._last_find = 0.0
        self._mem_dc = None
        self._hbmp = None
        self._old_bmp = None
        self._buf = None
        self._bgra = None
        self._bmi = None
        self._size = (0, 0)
        self._frame_lock = threading.Lock()
        self._bgr = None
        self._bgr_ref = None
        self._frame_out = None
        self._frame_id = 0
        self._backend = ''
        self._last_ok = 0.0
        self._times = deque(maxlen=32)
        self._cap_ms = 0.0
        self._frames = 0
        self._thread = None
        self._stop = threading.Event()
        self._subscribers = []
    def subscribe(self, fn) -> None:
        self._subscribers.append(fn)
    def start(self):
        if self._thread and self._thread.is_alive():
                return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name='prism-capture')
        self._thread.start()
    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None
        self._hwnd = 0
    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())
    @property
    def hwnd(self) -> int:
        return self._hwnd
    STALE_SEC = 1.0
    def snapshot(self) -> np.ndarray | None:
        with self._frame_lock:
            if self._frame_out is None or time.time() - self._last_ok > self.STALE_SEC:
                return
            else:
                return self._frame_out.copy()
    def jpeg(self, quality: int=70) -> bytes | None:
        with self._frame_lock:
            if self._frame_out is None:
                return
            else:
                ok, enc = cv2.imencode('.jpg', self._frame_out, [cv2.IMWRITE_JPEG_QUALITY, quality])
        return enc.tobytes() if ok else None
    def stats(self) -> dict:
        now = time.perf_counter()
        times = [t for t in self._times if now - t <= 3.0]
        fps = 0.0
        if len(times) >= 2:
            fps = (len(times) - 1) / (times[(-1)] - times[0])
        w, h = self._size
        return {'running': self.running, 'window_found': bool(self._hwnd), 'width': w, 'height': h, 'fps': round(fps, 1), 'cap_ms': round(self._cap_ms, 1), 'frames': self._frames, 'frame_id': self._frame_id, 'backend': self._backend}
    def _loop(self):
        interval = 1.0 / self.fps
        next_t = time.perf_counter()
        try:
            while not self._stop.is_set():
                t0 = time.perf_counter()
                if self._capture_once():
                    dt = (time.perf_counter() - t0) * 1000.0
                    self._cap_ms = dt if self._cap_ms == 0 else self._cap_ms * 0.9 + dt * 0.1
                    self._times.append(time.perf_counter())
                    self._frames += 1
                next_t += interval
                now = time.perf_counter()
                if next_t <= now:
                    next_t = now + interval
                self._stop.wait(next_t - now)
        finally:
            self._free_resources()

    def _ensure_hwnd(self) -> int:
        if self._hwnd and win32gui.IsWindow(self._hwnd):
            return self._hwnd
        else:
            self._hwnd = 0
            now = time.perf_counter()
            if now - self._last_find >= self.REFIND_INTERVAL:
                self._last_find = now
                self._hwnd = self._find_sticky()
            return self._hwnd
    def _find_sticky(self) -> int:
        wins = find_windows(self.process_name)
        wgc.prune(wins)
        if not wins:
            return 0
        else:
            if self._pid:
                for h in wins:
                    _, pid = win32process.GetWindowThreadProcessId(h)
                    if pid == self._pid:
                        return h
            h = wins[0]
            _, self._pid = win32process.GetWindowThreadProcessId(h)
            return h
    def _capture_once(self) -> bool:
        hwnd = self._ensure_hwnd()
        if not hwnd:
            return False
        else:
            src = wgc.grab(hwnd)
            if src is not None:
                self._backend = 'wgc'
                return self._publish(src)
            else:
                if not self._blit_gdi(hwnd):
                    return False
                else:
                    self._backend = 'gdi'
                    with self._frame_lock:
                        w, h = self._size
                        if self._bgr is None or self._bgr.shape[:2] != (h, w):
                            self._bgr = np.empty((h, w, 3), np.uint8)
                        cv2.cvtColor(self._bgra, cv2.COLOR_BGRA2BGR, dst=self._bgr)
                    return self._publish(self._bgr)
    def _blit_gdi(self, hwnd: int) -> bool:
        try:
            left, top, right, bottom = win32gui.GetClientRect(hwnd)
        except win32gui.error:
            self._hwnd = 0
            return False
        w, h = (right - left, bottom - top)
        if w <= 0 or h <= 0:
            return False
        hwnd_dc = user32.GetDC(hwnd)
        if not hwnd_dc:
            return False
        try:
            if (w, h) != self._size or self._mem_dc is None:
                self._create_resources(hwnd_dc, w, h)
            if not gdi32.BitBlt(self._mem_dc, 0, 0, w, h, hwnd_dc, 0, 0, win32con.SRCCOPY):
                return False
            gdi32.SelectObject(self._mem_dc, self._old_bmp)
            lines = gdi32.GetDIBits(self._mem_dc, self._hbmp, 0, h, self._buf, ctypes.byref(self._bmi), DIB_RGB_COLORS)
            gdi32.SelectObject(self._mem_dc, self._hbmp)
            if lines != h:
                return False
            return True
        finally:
            user32.ReleaseDC(hwnd, hwnd_dc)

    def _publish(self, bgr) -> bool:
        h, w = bgr.shape[:2]
        self._size = (w, h)
        with self._frame_lock:
            self._bgr = bgr
            if (w, h) == (REF_W, REF_H):
                self._frame_out = self._bgr
            else:
                if self._bgr_ref is None:
                    self._bgr_ref = np.empty((REF_H, REF_W, 3), np.uint8)
                cv2.resize(self._bgr, (REF_W, REF_H), dst=self._bgr_ref, interpolation=cv2.INTER_AREA)
                self._frame_out = self._bgr_ref
            self._frame_id += 1
            self._last_ok = time.time()
            frame, fid = (self._frame_out, self._frame_id)
        for fn in self._subscribers:
            try:
                fn(frame, fid)
            except Exception:
                pass
        return True
    def _create_resources(self, hwnd_dc: int, w: int, h: int):
        self._free_resources()
        self._mem_dc = gdi32.CreateCompatibleDC(hwnd_dc)
        self._hbmp = gdi32.CreateCompatibleBitmap(hwnd_dc, w, h)
        self._old_bmp = gdi32.SelectObject(self._mem_dc, self._hbmp)
        self._buf = ctypes.create_string_buffer(w * h * 4)
        self._bgra = np.frombuffer(self._buf, np.uint8).reshape(h, w, 4)
        bmi = BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = w
        bmi.bmiHeader.biHeight = -h
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        bmi.bmiHeader.biCompression = BI_RGB
        self._bmi = bmi
        self._size = (w, h)
    def _free_resources(self):
        if self._mem_dc:
            if self._old_bmp:
                gdi32.SelectObject(self._mem_dc, self._old_bmp)
            gdi32.DeleteDC(self._mem_dc)
        if self._hbmp:
            gdi32.DeleteObject(self._hbmp)
        self._mem_dc = self._hbmp = self._old_bmp = None
        self._buf = self._bgra = self._bmi = None
        self._size = (0, 0)
if __name__ == '__main__':
    eng = CaptureEngine()
    eng.start()
    time.sleep(2.0)
    print(eng.stats())
    frame = eng.snapshot()
    print('frame:', None if frame is None else frame.shape)
    eng.stop()