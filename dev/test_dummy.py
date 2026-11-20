"""DummyGuard tests (pure logic, runs anywhere):  python dev/test_dummy.py"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import detector  # noqa: E402

D = detector.DummyGuard
fails = []


def check(name, cond, extra=''):
    print(('PASS ' if cond else 'FAIL ') + name + ('' if cond else ' -- ' + str(extra)))
    if not cond:
        fails.append(name)


def run(clicks, g=None, dist=40.0, gap=0.9, t0=1000.0, xy=(500, 300)):
    g = g or D()
    out = []
    for i in range(clicks):
        out.append(g.click(xy[0], xy[1], dist, t0 + i * gap))
    return g, out


# 1. the reported case: 6 re-clicks in ~5 s must NOT stop or skip (old rule stopped here)
g, out = run(7)
check('6+ re-clicks in 6 s: no skip, no stop', set(out) <= {'ok', 'suspect'}, out)

# 2. a mob unanswered for 15+ s is skipped (not a stop), and its spot is filtered out
g, out = run(20)
check('20 s unanswered -> skip (not stop)', 'skip' in out and 'stop' not in out, out)
pts = np.array([[500, 300], [510, 305], [200, 400]], np.float32)
left = g.filter(pts, 1000 + 20 * 0.9)
check('skipped spot filtered, other mob kept', left.shape[0] == 1 and int(left[0, 0]) == 200, left)

# 3. skip expires after 45 s
check('skip expires', g.filter(pts, 1000 + 20 * 0.9 + 46).shape[0] == 3)

# 4. progress (fight / digit) clears the count
g = D()
for i in range(5):
    g.click(500, 300, 40.0, 1000 + i * 0.9)
g.progress()
_, out = run(3, g, t0=1005)
check('progress resets the suspicion count', g.clicks <= 2, g.clicks)

# 5. far mob click resets
g = D()
for i in range(5):
    g.click(500, 300, 40.0, 1000 + i * 0.9)
g.click(900, 600, 300.0, 1005)
check('far click resets', g.clicks == 0, g.clicks)

# 6. stale gap resets
g = D()
for i in range(5):
    g.click(500, 300, 40.0, 1000 + i * 0.9)
g.click(500, 300, 40.0, 1030)
check('gap > 3 s resets', g.clicks == 0, g.clicks)

# 7. three skips with no fight in between -> stop
g = D()
res = []
t = 1000.0
for rnd in range(3):
    for i in range(20):
        res.append(g.click(500 + rnd * 200, 300, 40.0, t))
        t += 0.9
check('3 skips without a fight -> stop', res.count('skip') == 2 and res.count('stop') == 1, (res.count('skip'), res.count('stop')))

# 8. fights in between keep it from stopping
g = D()
res = []
t = 1000.0
for rnd in range(6):
    for i in range(20):
        res.append(g.click(500 + rnd * 100, 300, 40.0, t))
        t += 0.9
    g.progress()
check('a fight between skips -> never stops', 'stop' not in res, res.count('stop'))

# 9. normal hunting: click, fight, click, fight - never suspect beyond 1
g = D()
res = []
t = 1000.0
for f in range(30):
    res += [g.click(500, 300, 40.0, t), g.click(500, 300, 40.0, t + 0.9)]
    g.progress()
    t += 15
check('normal hunting: no skip/stop in 30 fights', not ({'skip', 'stop'} & set(res)))

print('FAILED: %s' % fails if fails else 'all passed')
sys.exit(1 if fails else 0)
