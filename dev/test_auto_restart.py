"""Brain auto-restart: the bot's OWN stop (a false no-fight timeout, a crash-like condition) must
restart itself; an explicit stop (F4/F10/panel/discord/schedule) must NOT.   python dev/test_auto_restart.py"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'mock'))
import mock_loop as m
import brain

brain.AUTO_RESTART_DELAY_SEC = 0.05
brain.AUTO_RESTART_WINDOW_SEC = 2.0
brain.AUTO_RESTART_MAX_IN_WINDOW = 3

fails = []
def check(name, cond, extra=''):
    print(('PASS ' if cond else 'FAIL ') + name + ('' if cond else ' -- ' + str(extra)))
    if not cond: fails.append(name)

def make():
    brain.find_window = lambda: 1
    eng = m.FakeEngine(); eng.hwnd = 1
    hands = m.FakeHands()
    restarts = []
    b = brain.Brain(eng, m.FakeVision(), hands, note=lambda s: None, on_auto_restart=lambda: restarts.append(time.time()))
    return b, restarts

# 1) the bot's own automatic stop (_stop_now, e.g. "window vanished") -> auto-restart fires
b, restarts = make()
b.running = True
b._stop_now('거상 창이 사라짐 (캡처 불가)')
b.running = False  # the real _loop's finally block does this; simulate it directly here
b._auto_restart_at = []
# exercise the restart branch the same way _loop's finally does
now = time.time()
b._auto_restart_at = [t for t in b._auto_restart_at if now - t < brain.AUTO_RESTART_WINDOW_SEC] + [now]
import threading
if b._auto_restart and len(b._auto_restart_at) <= brain.AUTO_RESTART_MAX_IN_WINDOW:
    threading.Thread(target=lambda: (time.sleep(brain.AUTO_RESTART_DELAY_SEC), b._on_auto_restart())).start()
time.sleep(0.3)
check('_stop_now (a crash-like condition) is eligible for auto-restart', b._auto_restart is True)
check('the restart callback actually fired', len(restarts) == 1, restarts)

# 2) an explicit user stop() must NOT be eligible
b2, restarts2 = make()
b2.running = True
b2.stop()
check('an explicit stop() clears auto_restart', b2._auto_restart is False)

# 3) a _stop_bot with user_requested=True (panel/discord) must NOT be eligible
b3, restarts3 = make()
b3.running = True
b3._stop_bot('■ 원격 정지(jungjun)', user_requested=True)
check('a user-requested _stop_bot clears auto_restart', b3._auto_restart is False)

# 4) a _stop_bot with no user_requested (e.g. "300루프 전투 미진입") IS eligible
b4, restarts4 = make()
b4.running = True
b4._stop_bot('300루프 전투 미진입 (팅 의심)')
check('an automatic _stop_bot (no user_requested) is eligible', b4._auto_restart is True)

# 5) full live loop, end to end, through the REAL internal stop path (not calling _stop_now from
# outside the loop thread, which is not how production ever calls it: _stop_now is always called
# FROM WITHIN _run_loop's own thread, immediately followed by that exact call site's `return` -
# simulate "the game window vanished" so the loop's own no-frame-timeout triggers it for real).
import numpy as np
brain.NO_FRAME_STOP_SEC = 0.2
b5, restarts5 = make()
calls = {'n': 0}
def _snap():
    calls['n'] += 1
    return None if calls['n'] > 2 else np.full((768, 1024, 3), 90, 'uint8')
b5.engine.snapshot = _snap
b5._grab_main = lambda: np.full((768, 1024, 3), 90, 'uint8')
b5.start()
t0 = time.time()
while b5.running and time.time() - t0 < 3.0:
    time.sleep(0.05)
check('the loop noticed the vanished window and stopped itself', not b5.running)
t0 = time.time()
while not restarts5 and time.time() - t0 < 3.0:
    time.sleep(0.05)
check('end-to-end: the real _loop fires the restart callback on its own stop', len(restarts5) == 1, restarts5)

# 6) crash-loop cap: repeated automatic stops within the window must eventually refuse to keep restarting
b6, restarts6 = make()
for i in range(brain.AUTO_RESTART_MAX_IN_WINDOW + 2):
    b6.running = True
    b6._stop_now('반복 테스트')
    b6.running = False
    now = time.time()
    b6._auto_restart_at = [t for t in b6._auto_restart_at if now - t < brain.AUTO_RESTART_WINDOW_SEC] + [now]
    if b6._auto_restart and len(b6._auto_restart_at) <= brain.AUTO_RESTART_MAX_IN_WINDOW:
        restarts6.append(i)
check('a crash-loop is capped, not restarted forever', len(restarts6) == brain.AUTO_RESTART_MAX_IN_WINDOW, (len(restarts6), restarts6))

print('FAILED: %s' % fails if fails else 'all passed')
sys.exit(1 if fails else 0)
