"""Standalone window-visibility watchdog, independent of the main bot.

Why this exists: on 2026-11-18/19 the Gersang game window went invisible
twice (window alive, process responding, but IsWindowVisible()==False --
looks exactly like "the game quit" from the user's side). The main bot's
own fix for this (brain.py _ensure_window_visible) could not be confirmed
to actually be running after a restart (no log output at all from the new
process), so this script is a dead-simple, independent safety net: it does
not import brain/prism/config at all, just win32gui + win32process, so
there is nothing else that can make it silently fail to start.

Run with: py -3.11 C:/Gato/watchdog.py
Logs to: C:/Gato/watchdog.log (plain UTF-8, flushed every write)
"""
import time
import win32gui
import win32process

LOG_PATH = r"C:\Gato\watchdog.log"
PROCESS_NAME = "gersang.exe"
POLL_SEC = 5


def log(msg):
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n"
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line)
        f.flush()
    print(line, end="")


def get_process_exe(pid):
    try:
        import win32api
        import win32con
        handle = win32api.OpenProcess(win32con.PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    except Exception:
        return ""
    try:
        import win32process as wp
        return wp.GetModuleFileNameEx(handle, 0).lower()
    except Exception:
        return ""
    finally:
        handle.Close()


def find_gersang_window():
    result = []

    def cb(hwnd, _):
        if win32gui.GetWindowTextLength(hwnd) == 0:
            return
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        exe = get_process_exe(pid)
        if exe.endswith("\\" + PROCESS_NAME):
            result.append(hwnd)

    win32gui.EnumWindows(cb, None)
    if not result:
        return 0
    # Several helper windows share this process (GDI+ Window, DIEmWin) and
    # also have a non-empty title; only the one titled exactly "Gersang" is
    # the real game window with a real client rect -- observed live
    # 2026-11-19 toggling visibility on the wrong helper window repeatedly.
    exact = [h for h in result if win32gui.GetWindowText(h) == "Gersang"]
    return exact[0] if exact else result[0]


def main():
    log("watchdog started")
    last_state = None
    while True:
        try:
            hwnd = find_gersang_window()
            if not hwnd:
                if last_state != "not_found":
                    log("Gersang window not found (process may be closed)")
                    last_state = "not_found"
                time.sleep(POLL_SEC)
                continue
            visible = win32gui.IsWindowVisible(hwnd)
            if not visible:
                log(f"hwnd={hwnd} INVISIBLE -- restoring")
                import win32con
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
                time.sleep(0.3)
                fixed = win32gui.IsWindowVisible(hwnd)
                log(f"hwnd={hwnd} restore result: visible={fixed}")
                last_state = "fixed" if fixed else "failed"
            else:
                if last_state != "ok":
                    log(f"hwnd={hwnd} visible=OK")
                last_state = "ok"
        except Exception as e:
            log(f"ERROR: {type(e).__name__}: {e}")
        time.sleep(POLL_SEC)


if __name__ == "__main__":
    main()
