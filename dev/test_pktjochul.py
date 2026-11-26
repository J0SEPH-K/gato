"""pktjochul: framing detection, swap reconstruction, and the vision-free answer.

A synthetic server stream is built the way the game frames it (u16 LE length,
u16 LE opcode, two slot ids in the body), then pushed through the recorder the
same way the sniffer does. The decoder must recover the exact permutation, must
pick LE over BE, and must abstain (not guess) on a stream it cannot tile.

Run:  python3 dev/test_pktjochul.py
"""
import os
import random
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pktjochul  # noqa: E402

fails = []


def chk(name, cond, extra: object = ''):
    print(('PASS ' if cond else 'FAIL ') + name + ('' if cond else ' -- ' + str(extra)[:160]))
    if not cond:
        fails.append(name)


def frame(op, body):
    return struct.pack('<HH', 4 + len(body), op) + body


def feed(rec, pairs, op=0x1234, junk=True, chunk=7):
    """Push a down stream made of swap frames, chopped into TCP-sized pieces."""
    stream = b''
    for a, b in pairs:
        stream += frame(op, bytes([0x01, a, b, 0x00, 0x00]))
        if junk:
            stream += frame(0x7777, bytes(16))
    for i in range(0, len(stream), chunk):
        rec.feed('down', stream[i:i + chunk])


def expected(first, pairs):
    order = [1, 2, 3, 4, 5]
    for a, b in pairs:
        order[a - 1], order[b - 1] = order[b - 1], order[a - 1]
    return order.index(first) + 1


rnd = random.Random(7)
for case in range(60):
    pairs = []
    last = None
    for _ in range(rnd.randint(5, 15)):
        while True:
            a, b = sorted(rnd.sample(range(1, 6), 2))
            if last is None or not ({a, b} & set(last)):
                break
        pairs.append((a, b))
        last = (a, b)
    first = rnd.randint(1, 5)
    rec = pktjochul.PktJochul()
    rec.begin()
    feed(rec, pairs)
    rec.end()
    got, info = rec.solve(first)
    chk(f'case {case}: {len(pairs)} swaps from {first}', got == expected(first, pairs),
        f'got={got} want={expected(first, pairs)} {info}')

# the answer is a permutation index, never out of range
rec = pktjochul.PktJochul()
rec.begin()
feed(rec, [(1, 2), (3, 4), (2, 5)])
rec.end()
got, _info = rec.solve(1)
chk('answer in 1..5', got in {1, 2, 3, 4, 5}, got)

# start slot survives a full permutation
rec = pktjochul.PktJochul()
rec.begin()
feed(rec, [(1, 2), (2, 3), (3, 4), (4, 5)])
rec.end()
got, _info = rec.solve(3)
chk('slot 3 tracked through a rotation', got == 2, got)   # [2,3,4,5,1] -> slot 3 sits at 2

# endianness: the LE stream must win over BE on the same bytes
segs = [(0.0, 'down', frame(0x1234, bytes([1, 2, 3, 0, 0])))] * 8
fr_le, cov_le = pktjochul.PktJochul._tile(segs, 'little')
fr_be, cov_be = pktjochul.PktJochul._tile(segs, 'big')
chk('LE tiles the LE stream', cov_le > 0.9 and len(fr_le) == 8, (cov_le, len(fr_le)))
chk('LE beats BE', cov_le > cov_be, (cov_le, cov_be))

# abstention
rec = pktjochul.PktJochul()
chk('empty recording abstains', rec.solve(1)[0] is None)
rec = pktjochul.PktJochul()
rec.begin()
rec.feed('down', os.urandom(400))
rec.end()
chk('noise abstains', rec.solve(1)[0] is None)
rec = pktjochul.PktJochul()
rec.begin()
feed(rec, [(1, 2)], junk=False)
rec.end()
chk('one swap is too few', rec.solve(1)[0] is None)

# up direction is ignored by the decoder
rec = pktjochul.PktJochul()
rec.begin()
feed(rec, [(1, 2), (2, 3), (3, 4), (4, 5)])
rec.feed('up', frame(0x9999, bytes([5, 5, 5, 5])))
rec.end()
chk('up bytes do not disturb the decode', rec.solve(1)[0] is not None)

# begin() clears the previous round
rec = pktjochul.PktJochul()
rec.begin()
feed(rec, [(1, 2), (2, 3), (3, 4)])
rec.end()
rec.begin()
feed(rec, [(4, 5), (1, 4), (2, 5)])
rec.end()
got, _info = rec.solve(1)
chk('begin() starts a clean round', got == expected(1, [(4, 5), (1, 4), (2, 5)]), got)

print('RESULT', 'ALL PASS' if not fails else 'FAIL %s' % fails)
sys.exit(1 if fails else 0)
