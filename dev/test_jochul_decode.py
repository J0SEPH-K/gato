"""조철 swap-sequence decoder: regression test against simulated shuffles.

The decompiled source counted an undecided block (None) as a rule violation, which the original
bytecode does not. With dropped detections that picked the wrong timing phase and produced wrong
swaps. These cases failed before the fix.   python dev/test_jochul_decode.py
"""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import jochul  # noqa: E402


def sim(rnd, noise, drop, period=13.0, n_ops=15):
    ops, last = [], None
    for _ in range(n_ops):
        while True:
            a, b = sorted(rnd.sample(range(1, 6), 2))
            if last is None or not ({a, b} & set(last)):
                break
        ops.append((a, b))
        last = (a, b)
    n = int(period * n_ops) + 4
    pf = [None] * n
    for i, (a, b) in enumerate(ops):
        for f in range(int(round(period * i + 1)), min(n, int(round(period * (i + 1))))):
            u = rnd.random()
            if u < drop:
                continue
            pf[f] = tuple(sorted(rnd.sample(range(1, 6), 2))) if u < drop + noise else (a, b)
    return ops, pf


fails = []


def check(name, cond, extra=''):
    print(('PASS ' if cond else 'FAIL ') + name + ('' if cond else ' -- ' + str(extra)))
    if not cond:
        fails.append(name)


rnd = random.Random(1)
cases = []
for t in range(500):
    noise, drop = rnd.choice([0, .05, .15]), rnd.choice([0, .2, .4])
    cases.append((t, noise, drop) + sim(rnd, noise, drop))
byid = {c[0]: c for c in cases}
for t in (30, 473):   # decoded wrongly by the decompiled version
    _, _, _, ops, pf = byid[t]
    check('case %d decodes to the true swaps' % t, jochul.periodic_decode(pf) == ops)

ok = sum(jochul.periodic_decode(pf) == ops for _, _, _, ops, pf in cases)
check('exact decode >= 99%% of 500 simulated shuffles (%d)' % ok, ok >= 495, ok)
ok_hard = [jochul.periodic_decode(pf) == ops for _, n, d, ops, pf in cases if d >= .4 or n >= .15]
check('hard cases (40%% frames lost / 15%% wrong) >= 98%% (%d/%d)' % (sum(ok_hard), len(ok_hard)), sum(ok_hard) >= 0.98 * len(ok_hard))
check('empty input -> []', jochul.periodic_decode([]) == [])
print('FAILED: %s' % fails if fails else 'all passed')
sys.exit(1 if fails else 0)
