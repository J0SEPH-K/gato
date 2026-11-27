"""Decide a recorded 조철 round offline, from its bytes only.

The live decoder (pktjochul) has to abstain inside the 20 s answer timer, so it
cannot afford to be curious. This tool is the opposite: run it afterwards on a
saved dump and print everything needed to fix the decoder when a round
abstained - framing coverage per endianness, the full opcode histogram, and the
pair rate of every opcode.

Dump formats accepted:
  * pktjochul.dump()     "<monotonic> <up|down> <len> <hex>"
  * sniffer raw dump     "HH:MM:SS dir=.. sport=.. dport=.. len=.. n=.. body=.."

  scan   <dump>              framing + opcode histogram + pair rates
  frames <dump> <opcode>     every frame of that opcode, body decoded
  solve  <dump> <start>      the answer the stream implies, or why not
"""
import re
import sys

sys.path.insert(0, __file__.rsplit('/', 2)[0])
import pktjochul  # noqa: E402

RAW = re.compile(
    r'^\d\d:\d\d:\d\d dir=(up|down) sport=\d+ dport=\d+ len=\d+ n=\d+ body=([0-9a-f]*)$'
)


def load(path):
    """[(direction, payload)] in capture order, from either dump format."""
    out = []
    with open(path, 'r', encoding='ascii', errors='replace') as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            m = RAW.match(ln)
            if m:
                out.append((m.group(1), bytes.fromhex(m.group(2))))
                continue
            parts = ln.split(' ', 3)
            if len(parts) == 4 and parts[1] in ('up', 'down'):
                try:
                    out.append((parts[1], bytes.fromhex(parts[3])))
                except ValueError:
                    pass
    return out


def rec_of(segs):
    rec = pktjochul.PktJochul()
    rec.begin()
    for direction, payload in segs:
        rec.feed(direction, payload)
    return rec


def cmd_scan(path):
    segs = load(path)
    up = sum(len(p) for d, p in segs if d == 'up')
    down = sum(len(p) for d, p in segs if d == 'down')
    print(f'segments {len(segs)}  down {down}B  up {up}B')
    rec = rec_of(segs)
    endian, frames, cover = pktjochul.PktJochul._best_tiling(rec.snapshot())
    print(f'best framing {endian} cover {cover * 100:.1f}% frames {len(frames)}')
    per = {}
    for op, frame in frames:
        hit, total = per.get(op, (0, 0))
        per[op] = (hit + (1 if pktjochul.PktJochul._pair(frame) else 0), total + 1)
    print('opcode  frames  pairs  rate  body-sample')
    for op, (hit, total) in sorted(per.items(), key=lambda kv: -kv[1][1]):
        rate = hit / total if total else 0.0
        sample = next((f[4:12].hex() for o, f in frames if o == op), '')
        print(f'0x{op:04x}  {total:6d}  {hit:5d}  {rate * 100:5.1f}%  {sample}')
    op, why = pktjochul.PktJochul.swap_opcode(frames)
    print(f'swap opcode -> {op if op is None else hex(op)}  ({why})')


def cmd_frames(path, op_want):
    segs = load(path)
    rec = rec_of(segs)
    endian, frames, _cover = pktjochul.PktJochul._best_tiling(rec.snapshot())
    print(f'framing {endian}, {len(frames)} frames')
    for op, frame in frames:
        if op != op_want:
            continue
        tail = frame[4:]
        pair = pktjochul.PktJochul._pair(frame)
        print(f'len={len(frame)} pair={pair} u8={list(tail)}')


def cmd_solve(path, first):
    segs = load(path)
    rec = rec_of(segs)
    ans, info = rec.solve(first)
    order, _info = rec.permutation()
    print(f'start slot {first} -> answer {ans}')
    print(f'info {info}')
    if order:
        print(f'permutation {order}')
    print(f'client pick {rec.client_pick()}')


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    cmd, path = sys.argv[1], sys.argv[2]
    if cmd == 'scan':
        cmd_scan(path)
    elif cmd == 'frames':
        cmd_frames(path, int(sys.argv[3], 0))
    elif cmd == 'solve':
        cmd_solve(path, int(sys.argv[3]))
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
