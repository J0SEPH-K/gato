# Decompiled with PyLingual (https://pylingual.io)
# Internal filename: 'wgc.py'
# Bytecode version: 3.11a7e (3495)
# Source timestamp: 2026-09-14 10:45:15 UTC (1789382715)

from __future__ import annotations
import ctypes
import ctypes.wintypes
import ctypes.wintypes as wt
import threading
import time
import numpy as np

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

user32 = ctypes.windll.user32
dwmapi = ctypes.windll.dwmapi
DWMWA_EXTENDED_FRAME_BOUNDS = 9
_import_err: str | None = None
try:
    from windows_capture import WindowsCapture
except Exception as e:
    WindowsCapture = None
    _import_err = f'{type(e).__name__}: {e}'
def available() -> bool:
    return WindowsCapture is not None
def import_error() -> str | None:
    return _import_err
# The WGC buffer is the whole window (extended frame bounds), so the client area sits at
# ClientToScreen(0,0) - ef.left/top inside it. The (-1,-1) nudge is what the whole TRIGGERS
# table was calibrated against -- keep it unless every trigger region is re-measured too.
RENDER_SHIFT = ((-1), (-1))
def _client_box(hwnd: int):
    rc = wt.RECT()
    if not user32.GetClientRect(hwnd, ctypes.byref(rc)):
        return
    else:
        w, h = (rc.right - rc.left, rc.bottom - rc.top)
        if w <= 0 or h <= 0:
            return None
        else:
            org = wt.POINT(0, 0)
            if not user32.ClientToScreen(hwnd, ctypes.byref(org)):
                return
            else:
                ef = wt.RECT()
                if dwmapi.DwmGetWindowAttribute(wt.HWND(hwnd), DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(ef), ctypes.sizeof(ef)) != 0:
                    return
                else:
                    return (org.x - ef.left, org.y - ef.top, w, h)
class _Session:
    def __init__(self, hwnd: int):
        self.hwnd = hwnd
        self.lock = threading.Lock()
        self.frame = None
        self.frame_at = 0.0
        self.frame_mono = 0.0
        self.frames = 0
        self.started_at = time.time()
        self.error = None
        self.alive = True
        self._want_stop = False
        self.thread = threading.Thread(target=self._run, daemon=True, name=f'wgc-{hwnd}')
        self.thread.start()
    def _run(self):
        try:
            cap = WindowsCapture(cursor_capture=False, window_hwnd=self.hwnd)
            @cap.event
            def on_frame_arrived(frame, ctl):
                received_at = time.monotonic()
                if self._want_stop:
                    ctl.stop()
                    return
                else:
                    buf = getattr(frame, 'frame_buffer', None)
                    if buf is None:
                        return
                    else:
                        bgr = np.array(buf[:, :, :3])
                        with self.lock:
                            self.frame = bgr
                            self.frame_at = time.time()
                            self.frame_mono = received_at
                            self.frames += 1
            @cap.event
            def on_closed():
                self.alive = False
            cap.start()
        except Exception as e:
            self.error = f'{type(e).__name__}: {e}'
        finally:
            self.alive = False
    def stop(self):
        self._want_stop = True
    def client_frame(self) -> np.ndarray | None:
        sample = self.client_frame_info()
        return sample[0] if sample is not None else None
    def client_frame_info(self):
        box = _client_box(self.hwnd)
        if box is None:
            return
        else:
            ox, oy, w, h = box
            ox = max(0, ox + RENDER_SHIFT[0])
            oy = max(0, oy + RENDER_SHIFT[1])
            with self.lock:
                f = self.frame
                received_at, seq = (self.frame_mono, self.frames)
            if f is None or oy + h > f.shape[0] or ox + w > f.shape[1] or (ox < 0) or (oy < 0):
                return None
            else:
                return (np.ascontiguousarray(f[oy:oy + h, ox:ox + w]), received_at, seq)
_sessions: dict[int, _Session] = {}
_reg_lock = threading.Lock()
FIRST_FRAME_WAIT = 1.5
def _session(hwnd: int) -> _Session | None:
    if not available() or not hwnd or (not user32.IsWindow(hwnd)):
        _drop(hwnd)
        return
    else:
        with _reg_lock:
            s = _sessions.get(hwnd)
            if s is not None and (s.alive or s.thread.is_alive()):
                return s
            else:
                if s is not None:
                    _sessions.pop(hwnd, None)
                s = _Session(hwnd)
                _sessions[hwnd] = s
                return s
def _drop(hwnd: int):
    with _reg_lock:
        s = _sessions.pop(hwnd, None)
    if s is not None:
        s.stop()
def grab(hwnd: int) -> np.ndarray | None:
    # ***<module>.grab: Failure detected at line number 138 and instruction offset 76: Different bytecode
    s = _session(hwnd)
    if s is None:
        return
    else:
        f = s.client_frame()
        if f is None and s.frames == 0 and (time.time() - s.started_at < FIRST_FRAME_WAIT):
                    deadline = s.started_at + FIRST_FRAME_WAIT
                    while time.time() < deadline and s.frames == 0 and (s.error is None):
                        f = s.client_frame()
                    else:
                        time.sleep(0.01)
        if f is None and s.error:
                _drop(hwnd)
        return f
def grab_after(hwnd: int, after: float, timeout: float=0.25, stop=None):
    deadline = time.monotonic() + max(0.0, float(timeout))
    if stop is not None and stop() or time.monotonic() >= deadline:
        return None
    s = _session(hwnd)
    if s is None:
        return
    while time.monotonic() < deadline:
        if stop is not None and stop():
                return
        if not s.alive or s.error or (not user32.IsWindow(hwnd)):
            return None
        sample = s.client_frame_info()
        if sample is not None:
            frame, received_at, seq = sample
            if seq > 0 and received_at > after:
                if (stop is None or not stop()) and time.monotonic() < deadline:
                    return frame
                else:
                    return None
        remaining = deadline - time.monotonic()
        if remaining > 0:
            time.sleep(min(0.01, remaining))
    return None
def stop_all():
    with _reg_lock:
        sessions = list(_sessions.values())
        _sessions.clear()
    for s in sessions:
        s.stop()
def prune(live_hwnds) -> None:
    keep = set(live_hwnds)
    with _reg_lock:
        dead = [h for h in _sessions if h not in keep or not user32.IsWindow(h)]
    for h in dead:
        _drop(h)
def stats() -> list[dict]:
    with _reg_lock:
        items = list(_sessions.items())
    now = time.time()
    return [{'hwnd': h, 'frames': s.frames, 'alive': s.alive, 'age_ms': round((now - s.frame_at) * 1000) if s.frame_at else None, 'error': s.error} for h, s in items]