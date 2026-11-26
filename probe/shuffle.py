"""Read the 조철 medallion index straight out of a port-8000 packet dump.

No vision, no confidence: the server drives the shuffle, so the swap sequence and
the answer are in the bytes. This tool only has to find them.

Frame framing is not assumed: both endiannesses of the u16 length prefix and both
interpretations of the opcode field are scored against the capture, and the one
that actually tiles the stream wins. Gersang's chat socket (4011) uses
`u16 LE length | u16 LE opcode`, so LE is the prior, but a capture decides.

  sniff   <dump>                 which framing tiles the stream
  ops     <dump> <t0> <t1>       every down frame in the window, fully decoded
  answer  <dump> <t0> <t1>       the client's own up bytes in the window
  solve   <dump> <t0> <t1> <s>   reconstruct the order from start slot s
"""
import re
import sys
from collections import Counter

LINE = re.compile(
    r'^(\d\d):(\d\d):(\d\d) dir=(up|down) sport=(\d+) dport=(\d+) len=(\d+) n=(\d+) body=([0-9a-f]*)$'
)
MAX_FRAME = 8192
PORTS = (8000,)


def load(path):
    out = []
    with open(path, 'r', encoding='ascii', errors='replace') as f:
        for ln in f:
            m = LINE.match(ln.strip())
            if not m:
                continue
            hh, mm, ss, d, sp, dp, ln_, n, body = m.groups()
            sp, dp = int(sp), int(dp)
            if not (sp in PORTS or dp in PORTS):
                continue
            out.append({'t': int(hh) * 3600 + int(mm) * 60 + int(ss),
                        'ts': f'{hh}:{mm}:{ss}', 'dir': d, 'sport': sp, 'dport': dp,
                        'len': int(ln_), 'b': bytes.fromhex(body)})
    return out


def _u16(b, endian):
    return int.from_bytes(b, endian)  # type: ignore[arg-type]


def segment(segs, endian='little', direction='down'):
    """Tile one direction with a u16 length prefix. Yields (t, ts, frame, opcode)."""
    buf = bytearray()
    marks = []
    for g in segs:
        if g['dir'] != direction:
            continue
        buf.extend(g['b'])
        marks.extend([(g['t'], g['ts'])] * len(g['b']))
    i = 0
    while i + 4 <= len(buf):
        ln = _u16(buf[i:i + 2], endian)
        if 4 <= ln <= MAX_FRAME and i + ln <= len(buf):
            op = _u16(buf[i + 2:i + 4], endian)
            yield marks[i][0], marks[i][1], bytes(buf[i:i + ln]), op
            i += ln
        else:
            i += 1


def score(segs, endian):
    n, cov, ops = 0, 0, Counter()
    for _t, _ts, fr, op in segment(segs, endian):
        n += 1
        cov += len(fr)
        ops[op] += 1
    total = sum(g['len'] for g in segs if g['dir'] == 'down')
    distinct = len(ops)
    return {'frames': n, 'bytes': cov, 'total': total,
            'cover': cov / total if total else 0.0, 'distinct_ops': distinct}


def cmd_sniff(segs):
    print(f'{len(segs)} port-8000 segments, '
          f'{sum(g["len"] for g in segs if g["dir"] == "down")}B down, '
          f'{sum(g["len"] for g in segs if g["dir"] == "up")}B up')
    for endian in ('little', 'big'):
        s = score(segs, endian)
        print(f'  {endian:6s} frames={s["frames"]:6d} cover={s["cover"] * 100:5.1f}% '
              f'opcodes={s["distinct_ops"]}')
    best = max(('little', 'big'), key=lambda e: score(segs, e)['cover'])
    print(f'best framing: {best} — pass it to ops/solve with --{best}')
    fr = list(segment(segs, best))
    if fr:
        per = Counter(t for t, _ts, _f, _o in fr)
        print('\ndown frames per second:')
        for t in sorted(per):
            hh, mm, ss = t // 3600, t // 60 % 60, t % 60
            print(f'  {hh:02d}:{mm:02d}:{ss:02d} {per[t]:4d}')
        print('\nopcode histogram:', [(hex(k), v) for k, v in Counter(o for *_x, o in fr).most_common(20)])


def window(segs, t0, t1, endian):
    return [x for x in segment(segs, endian) if t0 <= x[0] <= t1]


def decode_tail(body):
    """Every plausible reading of a short body, so one capture settles the layout."""
    parts = []
    if body:
        parts.append('u8[' + ' '.join(str(b) for b in body[:12]) + ']')
    if len(body) >= 2:
        parts.append('le16[' + ' '.join(str(int.from_bytes(body[i:i + 2], 'little'))
                                        for i in range(0, min(len(body), 12) - 1, 2)) + ']')
        parts.append('be16[' + ' '.join(str(int.from_bytes(body[i:i + 2], 'big'))
                                        for i in range(0, min(len(body), 12) - 1, 2)) + ']')
    return '  '.join(parts)


def cmd_ops(segs, t0, t1, endian):
    hit = window(segs, t0, t1, endian)
    print(f'{len(hit)} down frames in {t0}..{t1}s')
    for _t, ts, fr, op in hit:
        print(f'{ts} op=0x{op:04x} len={len(fr):4d} {decode_tail(fr[4:])}  {fr[:48].hex()}')


def cmd_answer(segs, t0, t1):
    hit = [g for g in segs if g['dir'] == 'up' and t0 <= g['t'] <= t1]
    print(f'{len(hit)} up segments in {t0}..{t1}s')
    for g in hit:
        print(f"{g['ts']} len={g['len']:4d} u8[{ ' '.join(str(b) for b in g['b'][:12])}] {g['b'][:64].hex()}")


def cmd_solve(segs, t0, t1, start, endian):
    """Apply the decoded swap pairs to the start slot and report the holder."""
    lst = [1, 2, 3, 4, 5]
    ops = []
    for _t, ts, fr, op in window(segs, t0, t1, endian):
        body = fr[4:]
        pair = None
        for cand in ([b for b in body if 1 <= b <= 5][:2],):
            if len(cand) == 2 and cand[0] != cand[1]:
                pair = tuple(cand)
        if pair:
            i, j = pair[0] - 1, pair[1] - 1
            lst[i], lst[j] = lst[j], lst[i]
            ops.append((ts, pair, list(lst)))
    for ts, pair, state in ops:
        print(f'{ts} swap {pair} -> {state}')
    print(f'{len(ops)} swaps applied from start slot {start}')
    if start not in lst:
        print('start slot fell out of the permutation — decode is wrong')
        return
    print(f'ANSWER: slot {lst.index(start) + 1}')


def hms(s):
    hh, mm, ss = (int(x) for x in s.split(':'))
    return hh * 3600 + mm * 60 + ss


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 1
    endian = 'big' if '--big' in argv else 'little'
    argv = [a for a in argv if not a.startswith('--')]
    segs = load(argv[2])
    c = argv[1]
    if c == 'sniff':
        cmd_sniff(segs)
    elif c == 'ops':
        cmd_ops(segs, hms(argv[3]), hms(argv[4]), endian)
    elif c == 'answer':
        cmd_answer(segs, hms(argv[3]), hms(argv[4]))
    elif c == 'solve':
        cmd_solve(segs, hms(argv[3]), hms(argv[4]), int(argv[5]), endian)
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
