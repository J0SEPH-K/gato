"""조철 decision chain vs every truth-labelled REAL round of the current client (2026-11-28).

Replays each recorded round through the same chain `brain._handle_jochul_inner` runs (start slot,
reveal-burst marker / settle reader over the live window, pktjochul on the round's packet log,
then the YOLO tracker ensemble) with `dev/tools/jochul_round_replay.py`, and scores it against the
game's own post-click reveal (`dev/tools/jochul_reveal_label.py`: the medallion parks over the TRUE
holder after the click - 090812 clicked 4, medallion over 2; 203347 clicked 4, medallion over 3;
044133 clicked 2, medallion over 2 and passed=True).

Rule under test (HO-10): on every real round the chain answers the reveal slot or abstains. A
confident wrong answer is a failure even if the round count is tiny.

Data is not in the repo (~45 MB a round). Default location is the HO-21 collection; override with
GATO_ROUNDS=<dir holding r044133/ r090812/ r203347/ and pkt_*.log>. Missing data or a missing
torch/ultralytics SKIPs (exit 0) with the reason, it never passes silently as tested.

    ~/Projects/diablia/workspace/_tools/cv/bin/python dev/test_jochul_real_rounds.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'tools'))
sys.path.insert(0, os.path.dirname(HERE))

DATA = os.environ.get('GATO_ROUNDS', os.path.expanduser('~/Projects/gato_data/rounds_20261128/raw'))

# (round dir, packet log, reveal label measured from the recording, slot the live build clicked)
ROUNDS = [
    ('r044133', 'pkt_20261128_044129.log', 2, 2),
    ('r090812', 'pkt_20261128_090801.log', 2, 4),
    ('r203347', 'pkt_20261128_203336.log', 3, 4),
]
# packet-only rounds (no frames): the packet decoder must abstain, it has no verified layout
PKT_ONLY = [('pkt_20261128_041924.log', 1)]

fails = []


def chk(name, cond, extra=''):
    print(('PASS ' if cond else 'FAIL ') + name + ('' if cond else ' -- ' + str(extra)[:300]))
    if not cond:
        fails.append(name)


missing = [r for r, _p, _l, _c in ROUNDS if not os.path.isdir(os.path.join(DATA, r))]
try:
    import torch  # noqa: F401
    from ultralytics import YOLO  # noqa: F401
    have_model = type(torch).__module__ != 'unittest.mock' and type(YOLO).__module__ != 'unittest.mock'
except Exception:
    have_model = False
if missing or not have_model:
    print('SKIP real-round replay: %s' % (
        'rounds not found under %s: %s' % (DATA, missing) if missing else
        'torch/ultralytics not importable (use the cv venv python, without mac_stub)'))
    sys.exit(0)

import jochul_reveal_label  # noqa: E402
import jochul_round_replay  # noqa: E402

answered = wrong = 0
for rnd, pkt, label, live in ROUNDS:
    d = os.path.join(DATA, rnd)
    lab = jochul_reveal_label.label(d)
    votes = lab['marker_votes']
    chk('%s: post-click reveal reads slot %d (unanimous, >=20 frames)' % (rnd, label),
        set(votes) == {label} and votes[label] >= 20, votes)
    r = jochul_round_replay.replay(d, os.path.join(DATA, pkt))
    chk('%s: start slot read from the frames matches the live round' % rnd,
        r['first_replayed'] == r['first_live'], (r['first_replayed'], r['first_live']))
    chk('%s: packet decoder abstains (no verified swap layout)' % rnd, r['pkt'] is None, r['pkt_info'])
    ok = r['answer'] in (None, label)
    chk('%s: chain answers the reveal slot or abstains (never confident-wrong)' % rnd, ok,
        'answer=%s label=%s %s' % (r['answer'], label, r.get('track_info')))
    print('     %s live clicked %s | replay answer %s via %s | %s' % (
        rnd, live, r['answer'], r['source'], r.get('track_info', r.get('pkt_info'))))
    for g, dcy, a, info in r.get('votes', []):
        print('       gate=%-5s decay=%-4s -> %s  %s' % (g, dcy, a, info))
    if r['answer'] is not None:
        answered += 1
        wrong += r['answer'] != label

# coverage guard: the two rounds that answer today must keep answering (a change that turns them
# into abstains is a regression too, just a safe one - it must be a deliberate decision)
r44 = jochul_round_replay.replay(os.path.join(DATA, 'r044133'), os.path.join(DATA, 'pkt_20261128_044129.log'))
r20 = jochul_round_replay.replay(os.path.join(DATA, 'r203347'), os.path.join(DATA, 'pkt_20261128_203336.log'))
chk('coverage: r044133 still answered (2)', r44['answer'] == 2, r44.get('track_info'))
chk('coverage: r203347 still answered (3)', r20['answer'] == 3, r20.get('track_info'))

for pkt, first in PKT_ONLY:
    path = os.path.join(DATA, pkt)
    if os.path.isfile(path):
        ans, info = jochul_round_replay.pkt_solve(path, first)
        chk('%s: packet decoder abstains' % pkt, ans is None, info)

n = len(ROUNDS)
print()
print('real rounds %d | answered %d | wrong %d | abstained %d | coverage %d%% | wrong-click rate %s' % (
    n, answered, wrong, n - answered, round(100.0 * answered / n),
    ('%d/%d' % (wrong, answered)) if answered else 'n/a'))
print('FAILED: %s' % fails if fails else 'all passed')
sys.exit(1 if fails else 0)
