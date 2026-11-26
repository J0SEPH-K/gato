"""Find the 조철 shuffle in a raw port-8000 dump and read the medallion index
straight out of the bytes.

The raw dump (sniffer._raw_dump) is one line per TCP segment, in capture order:

    HH:MM:SS dir=down sport=8000 dport=<client> len=N n=<k> body=<hex>

Server->client frames on the main socket are length-prefixed with a u16 BE
length that equals the whole frame length. So the down stream can be cut into
frames without any guessing: read u16, take that many bytes, repeat, resync one
byte at a time when the length does not fit.

Pipeline:
  1. segment the down stream into frames
  2. find the shuffle window = the burst of small, regular frames that ends in
     the reveal (the client sends its answer right after)
  3. inside the window, print every frame with its tail decoded as u8/u16 so the
     slot permutation is visible by eye on the first capture and by code after

  scan   <dump>              frame histogram + candidate shuffle windows
  window <dump> <t0> <t1>    every frame in that time window, fully decoded
  up     <dump> <t0> <t1>    the client's own bytes in the window (its answer)
"""
import re
import sys
from collections import Counter

LINE = re.compile(
    r'^(\d\d):(\d\d):(\d\d) dir=(up|down) sport=(\d+) dport=(\d+) len=(\d+) n=(\d+) body=([0-9a-f]*)$'
)
MAX_FRAME = 8192


def load(path):
    out = []
    with open(path, 'r', encoding='ascii', errors='replace') as f:
        for ln in f:
            m = LINE.match(ln.strip())
            if not m:
                continue
            hh, mm, ss, d, sp, dp, ln_, n, body = m.groups()
            sp, dp = int(sp), int(dp)
            if 8000 not in (sp, dp):
                continue
            out.append({
                't': int(hh) * 3600 + int(mm) * 60 + int(ss),
                'ts': f'{hh}:{mm}:{ss}', 'dir': d, 'sport': sp, 'dport': dp,
                'len': int(ln_), 'b': bytes.fromhex(body),
            })
    return out


def segment(segs, direction='down'):
    """Length-prefixed framing of one direction. Yields (t, ts, frame_bytes)."""
    buf = bytearray()
    marks = []
    for g in segs:
        if g['dir'] != direction:
            continue
        buf.extend(g['b'])
        marks.extend([(g['t'], g['ts'])] * len(g['b']))
    i = 0
    while i + 2 <= len(buf):
        ln = int.from_bytes(buf[i:i + 2], 'big')
        if 4 <= ln <= MAX_FRAME and i + ln <= len(buf):
            yield marks[i][0], marks[i][1], bytes(buf[i:i + ln])
            i += ln
        else:
            i += 1


def frames(segs, direction='down'):
    return list(segment(segs, direction))


def cmd_scan(segs):
    fr = frames(segs)
    print(f'{len(fr)} down frames on 8000')
    if not fr:
        print('no frames — was the dump armed while the bot was hunting?')
        return
    ops = Counter(int.from_bytes(f[2][2:4], 'big') for f in fr)
    print('opcode histogram (frame[2:4]):')
    for op, c in ops.most_common(25):
        lens = sorted({len(f[2]) for f in fr if int.from_bytes(f[2][2:4], 'big') == op})
        print(f'  0x{op:04x} x{c:5d} lens={lens[:8]}')
    per = Counter(t for t, _ts, _f in fr)
    base = sorted(per.values())
    med = base[len(base) // 2] if base else 1
    print(f'\nmedian {med} frames/s; windows above 4x:')
    for t in sorted(per):
        if per[t] >= max(4 * med, 8):
            hh, mm, ss = t // 3600, t // 60 % 60, t % 60
            print(f'  {hh:02d}:{mm:02d}:{ss:02d} {per[t]} frames')


def _dump_frame(ts, fr):
    op = int.from_bytes(fr[2:4], 'big')
    tail = fr[4:]
    as_u8 = ' '.join(str(x) for x in tail[:16])
    print(f'{ts} op=0x{op:04x} len={len(fr):4d} u8[{as_u8}] {fr[:72].hex()}')


def cmd_window(segs, t0, t1):
    hit = [f for f in frames(segs) if t0 <= f[0] <= t1]
    print(f'{len(hit)} frames in {t0}..{t1}s')
    for _t, ts, fr in hit:
        _dump_frame(ts, fr)


def cmd_up(segs, t0, t1):
    hit = [g for g in segs if g['dir'] == 'up' and t0 <= g['t'] <= t1]
    print(f'{len(hit)} up segments in window')
    for g in hit:
        print(f"{g['ts']} len={g['len']:4d} {g['b'][:64].hex()}")


def hms(s):
    hh, mm, ss = (int(x) for x in s.split(':'))
    return hh * 3600 + mm * 60 + ss


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 1
    segs = load(argv[2])
    c = argv[1]
    if c == 'scan':
        cmd_scan(segs)
    elif c == 'window':
        cmd_window(segs, hms(argv[3]), hms(argv[4]))
    elif c == 'up':
        cmd_up(segs, hms(argv[3]), hms(argv[4]))
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
