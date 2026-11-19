"""Click-path self-test on its own window: delivery, landing error (px), latency. Does not touch the game.
Usage: .venv\\Scripts\\python dev\\selftest_click.py
"""
import sys, time, threading, ctypes, ctypes.wintypes as wt
import os
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, root_dir)
import tkinter as tk
import win32gui, capture
import input as ginput

# Own test window: verifies SendInput delivery + position + hold without touching the game.
win = tk.Tk(); win.geometry('1024x768+0+0'); win.title('Gersang')  # title irrelevant: we pass hwnd_get
win.attributes('-topmost', True)
ev = []
win.bind('<ButtonPress-3>', lambda e: ev.append(('d', time.perf_counter(), e.x_root, e.y_root)))
win.bind('<ButtonRelease-3>', lambda e: ev.append(('u', time.perf_counter(), e.x_root, e.y_root)))
win.update()
hwnd = int(win.frame(), 16)
cw = win32gui.GetClientRect(hwnd)
logs=[]
hands = ginput.Hands(hwnd_get=lambda: hwnd, log=logs.append)
hands.FG_SETTLE = 0.0
hands._foreground = lambda: hwnd   # harness: measure the click path, not window focus
pt = wt.POINT()
n_ok = 0; durs = []; errs = []
for i in range(40):
    x = 100 + (i * 83) % 800; y = 100 + (i * 61) % 560
    exp = hands._to_screen(hwnd, x, y)
    ev.clear()
    win.lift(); win.update()
    a = time.perf_counter()
    r = hands.click(x, y, 'right', wait=True)
    b = time.perf_counter()
    for _ in range(20):
        win.update(); time.sleep(0.005)
    d = [e for e in ev if e[0] == 'd']; u = [e for e in ev if e[0] == 'u']
    if not (r and d and u): print('MISS i=%d r=%s d=%d u=%d exp=%s' % (i, r, len(d), len(u), exp))
    if r and d and u:
        n_ok += 1
        errs.append(max(abs(d[0][2]-exp[0]), abs(d[0][3]-exp[1])))
        durs.append((b-a)*1000)
durs.sort()
print('clicks_delivered %d/40  max_pos_err_px %s' % (n_ok, max(errs) if errs else None))
print('click_ms p50 %.1f p90 %.1f max %.1f' % (durs[len(durs)//2], durs[int(len(durs)*.9)], durs[-1]))
print('logs', sorted(set(logs))[:6])
win.destroy()
