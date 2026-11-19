# Source Generated with Decompyle++
# File: dpi.pyc (Python 3.11)

import ctypes

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


def apply():
    
    try:
        u = ctypes.windll.user32
        u.SetProcessDpiAwarenessContext.restype = ctypes.c_bool
        u.SetProcessDpiAwarenessContext.argtypes = [
            ctypes.c_void_p]
        if u.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
            return None
    except Exception:
        pass

    
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return None
    except Exception:
        pass

    
    try:
        ctypes.windll.user32.SetProcessDPIAware()
        return None
    except Exception:
        return None


apply()
