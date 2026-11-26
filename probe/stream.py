"""Reassemble per-direction TCP streams out of a rawdump file, then look for the
조철 minigame inside them.

rawdump lines carry no seq, but they are appended in capture order by a single
thread, so concatenating per (dir, sport, dport) in file order reproduces the
stream closely enough for offline analysis.

  frames <file> [dir] [port]   length-prefix scan of one direction
  burst  <file>                windows of unusual down-direction volume
  up     <file>                every up-direction payload on 8000, in order
  show   <file> <a> <b>        payloads between line numbers a..b
"""
import re
import sys
from collections import Counter, defaultdict

LINE = re.compile(
    r'^(\d\d):(\d\d):(\d\d) dir=(up|down) sport=(\d+) dport=(\d+) len=(\d+) n=(\d+) body=([0-9a-f]*)$'
)


def load(path):
    out = []
    with open(path, 'r', encoding='ascii', errors='replace') as f:
        for i, ln in enumerate(f):
            m = LINE.match(ln.strip())
            if not m:
                continue
            hh, mm, ss, d, sp, dp, ln_, n, body = m.groups()
            out.append({
                'i': i, 't': int(hh) * 3600 + int(mm) * 60 + int(ss),
                'ts': f'{hh}:{mm}:{ss}', 'dir': d, 'sport': int(sp),
                'dport': int(dp), 'len': int(ln_), 'b': bytes.fromhex(body),
            })
    return out


def streams(segs):
    s = defaultdict(bytearray)
    for g in segs:
        s[(g['dir'], g['sport'], g['dport'])].extend(g['b'])
    return s


def cmd_frames(segs, direction='down', port=8000):
    for (d, sp, dp), buf in streams(segs).items():
        if d != direction:
            continue
        if port and port not in (sp, dp):
            continue
        print(f'== {d} {sp}->{dp} {len(buf)}B')
        i, n, out = 0, 0, []
        while i + 2 <= len(buf) and n < 200:
            ln = int.from_bytes(buf[i:i + 2], 'big')
            if 4 <= ln <= 4096 and i + ln <= len(buf):
                out.append((i, ln, bytes(buf[i:i + ln])))
                i += ln
                n += 1
            else:
                i += 1
        print(f'   {n} plausible frames of {len(buf)}B')
        for off, ln, fr in out[:80]:
            print(f'   @{off:6d} len={ln:4d} {fr[:64].hex()}')
        print('   u16-be length histogram:', Counter(ln for _o, ln, _f in out).most_common(8))


def cmd_burst(segs):
    c = Counter()
    for g in segs:
        if g['dir'] == 'down':
            c[g['t']] += g['len']
    base = sorted(c.values())
    if not base:
        return
    med = base[len(base) // 2]
    print(f'median down bytes/sec {med}')
    for t in sorted(c):
        if c[t] > max(3 * med, med + 4000):
            hh, mm, ss = t // 3600, t // 60 % 60, t % 60
            print(f'  burst {hh:02d}:{mm:02d}:{ss:02d} {c[t]}B (x{c[t] / max(med, 1):.1f})')


def cmd_up(segs, limit=400):
    up = [g for g in segs if g['dir'] == 'up' and 8000 in (g['sport'], g['dport'])]
    print(f'{len(up)} up payloads on 8000')
    for g in up[:limit]:
        print(f"{g['ts']} len={g['len']:4d} {g['b'][:48].hex()}")


def cmd_show(segs, a, b):
    for g in segs:
        if a <= g['i'] <= b:
            print(f"{g['i']} {g['ts']} {g['dir']:4s} {g['sport']}->{g['dport']} len={g['len']} {g['b'][:96].hex()}")


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 1
    segs = load(argv[2])
    print(f'{len(segs)} segments, span {segs[0]["ts"] if segs else "-"}..{segs[-1]["ts"] if segs else "-"}')
    c = argv[1]
    if c == 'frames':
        cmd_frames(segs, argv[3] if len(argv) > 3 else 'down', int(argv[4]) if len(argv) > 4 else 8000)
    elif c == 'burst':
        cmd_burst(segs)
    elif c == 'up':
        cmd_up(segs)
    elif c == 'show':
        cmd_show(segs, int(argv[3]), int(argv[4]))
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
