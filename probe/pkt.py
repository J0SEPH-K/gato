"""Offline analyser for the port-8000 raw dump (sniffer._raw_dump).

Dump line format (ascii, one line per TCP segment):
    HH:MM:SS dir=up|down sport=N dport=N len=N n=N body=<hex, <=512B>

Subcommands:
  ops  <file>                 opcode histogram (first 2 bytes, big endian) split by direction
  diff <file> <t0> <t1> <t2>  set-diff control window [t0,t1) against window [t1,t2)
  seg  <file> <opcode> [from] print segments carrying that opcode, in capture order
  hex  <file> <ts> <n>        print n segments starting at HH:MM:SS ts

The point of `diff` is to isolate the 조철 shuffle opcode without knowing it in
advance: the control window is ordinary field traffic, the second window is the
shuffle. Keys that appear in the second window and not the first are candidates.
Keys are (dir, len, body[8:12]) so the per-segment sequence field at offset 4 is
ignored and duplicates collapse.
"""
import re
import sys
from collections import Counter

LINE = re.compile(
    r'^(\d\d):(\d\d):(\d\d) dir=(up|down) sport=(\d+) dport=(\d+) len=(\d+) n=(\d+) body=([0-9a-f]*)$'
)


def load(path):
    out = []
    with open(path, 'r', encoding='ascii', errors='replace') as f:
        for ln in f:
            m = LINE.match(ln.strip())
            if not m:
                continue
            hh, mm, ss, d, sp, dp, ln_, n, body = m.groups()
            out.append({
                't': int(hh) * 3600 + int(mm) * 60 + int(ss),
                'ts': f'{hh}:{mm}:{ss}',
                'dir': d,
                'sport': int(sp),
                'dport': int(dp),
                'len': int(ln_),
                'n': int(n),
                'b': bytes.fromhex(body),
            })
    return out


def opcode(b):
    return int.from_bytes(b[:2], 'big') if len(b) >= 2 else -1


def cmd_ops(segs):
    up, down = Counter(), Counter()
    for s in segs:
        (up if s['dir'] == 'up' else down)[opcode(s['b'])] += 1
    print(f'{len(segs)} segments  up={sum(up.values())} down={sum(down.values())}')
    print('-- down (server -> client) opcodes, count desc --')
    for op, c in down.most_common(60):
        lens = sorted({s['len'] for s in segs if s['dir'] == 'down' and opcode(s['b']) == op})
        print(f'  0x{op:04x} {c:6d}  lens={lens[:6]}')
    print('-- up (client -> server) opcodes --')
    for op, c in up.most_common(40):
        lens = sorted({s['len'] for s in segs if s['dir'] == 'up' and opcode(s['b']) == op})
        print(f'  0x{op:04x} {c:6d}  lens={lens[:6]}')


def key(s):
    return (s['dir'], s['len'], s['b'][8:12].hex())


def cmd_diff(segs, t0, t1, t2):
    ctrl = [s for s in segs if t0 <= s['t'] < t1]
    win = [s for s in segs if t1 <= s['t'] < t2]
    ck = Counter(key(s) for s in ctrl)
    wk = Counter(key(s) for s in win)
    print(f'control {len(ctrl)} segs in {t0}-{t1}s, window {len(win)} segs in {t1}-{t2}s')
    novel = [(k, c) for k, c in wk.items() if k not in ck]
    novel.sort(key=lambda kv: -kv[1])
    print(f'{len(novel)} novel keys in window (present in window, absent from control)')
    for (d, ln, h), c in novel[:80]:
        ops = Counter(opcode(s['b']) for s in win if key(s) == (d, ln, h))
        print(f'  {d:4s} len={ln:5d} body8:12={h:8s} x{c:3d}  opcodes={[hex(o) for o in ops]}')
    lost = [(k, c) for k, c in ck.items() if k not in wk]
    print(f'-- {len(lost)} keys lost in window --')
    for (d, ln, h), c in sorted(lost, key=lambda kv: -kv[1])[:20]:
        print(f'  {d:4s} len={ln:5d} body8:12={h:8s} x{c}')


def cmd_seg(segs, op, start=0):
    hit = [s for s in segs if opcode(s['b']) == op]
    print(f'{len(hit)} segments with opcode 0x{op:04x}')
    for s in hit[:400]:
        if s['t'] < start:
            continue
        print(f"{s['ts']} {s['dir']:4s} len={s['len']:5d} {s['b'][:96].hex()}")


def cmd_hex(segs, ts, n):
    hh, mm, ss = (int(x) for x in ts.split(':'))
    t = hh * 3600 + mm * 60 + ss
    hit = [s for s in segs if s['t'] >= t][:n]
    for s in hit:
        print(f"{s['ts']} {s['dir']:4s} sp={s['sport']} dp={s['dport']} len={s['len']:5d} {s['b'][:128].hex()}")


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 1
    segs = load(argv[2])
    c = argv[1]
    if c == 'ops':
        cmd_ops(segs)
    elif c == 'diff':
        cmd_diff(segs, int(argv[3]), int(argv[4]), int(argv[5]))
    elif c == 'seg':
        cmd_seg(segs, int(argv[3], 0), int(argv[4]) if len(argv) > 4 else 0)
    elif c == 'hex':
        cmd_hex(segs, argv[3], int(argv[4]))
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
