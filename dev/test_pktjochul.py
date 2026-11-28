"""pktjochul: framing, opcode gating, swap reconstruction, abstention.

A synthetic server stream is built the way the game frames it (u16 LE length,
u16 LE opcode, two slot ids in the body), with a large volume of UNRELATED
opcodes mixed in that also carry in-range bytes - that is the real failure mode,
because those would otherwise inject phantom swaps and shift the answer.

The decoder must recover the exact permutation, must pick LE over BE, must
identify the swap opcode on its own, and must abstain (not guess) on a stream it
cannot tile or on a stream with two equally plausible swap opcodes.

Run:  python3 dev/test_pktjochul.py
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pktjochul  # noqa: E402

fails = []
SWAP_OP = 0x1234
NOISE_OPS = (0x7777, 0x0031, 0x0042)


def chk(name, cond, extra: object = ''):
    print(('PASS ' if cond else 'FAIL ') + name + ('' if cond else ' -- ' + str(extra)[:200]))
    if not cond:
        fails.append(name)


def frame(op, body, endian='little'):
    return struct.pack('<HH' if endian == 'little' else '>HH', 4 + len(body), op) + body


def stream(pairs, endian='little', noise=True, noise_per_swap=2):
    """A down stream: swap frames plus unrelated frames that also look slot-ish."""
    out = b''
    for a, b in pairs:
        out += frame(SWAP_OP, bytes([0x01, a, b, 0x00, 0x00]), endian)
        if noise:
            for _ in range(noise_per_swap):
                out += frame(NOISE_OPS[_ % len(NOISE_OPS)], bytes([0x01, 1, 2, 9, 9]), endian)
    return out


def feed(rec, data, chunk=7):
    for i in range(0, len(data), chunk):
        rec.feed('down', data[i:i + chunk])


def rec_for(pairs, **kw):
    rec = pktjochul.PktJochul()
    rec.begin()
    feed(rec, stream(pairs, **kw))
    return rec


# 1. exact reconstruction from a start slot
pairs = [(1, 3), (3, 5), (2, 4), (1, 2), (4, 5)]
rec = rec_for(pairs)
ans, info = rec.solve(1)
order = pktjochul.PktJochul._replay(pairs)
chk('reconstructs the permutation', order == [4, 5, 2, 1, 3], order)
chk('answers from the start slot', ans == order.index(1) + 1, f'ans={ans} {info}')
chk('identifies the swap opcode only', 'op=0x1234' in info, info)

# 2. noise frames must not enter the permutation
clean = rec_for(pairs, noise=False)
chk('noise does not change the answer', clean.solve(1)[0] == ans)

# 3. a big-endian stream tiles as big-endian and still answers
be = rec_for(pairs, endian='big')
be_ans, be_info = be.solve(1)
chk('tiles a BE stream as BE', 'big' in be_info, be_info)
chk('answers on a BE stream', be_ans == ans, f'{be_ans} {be_info}')

# 4. abstains on an untilable stream
rec = pktjochul.PktJochul()
rec.begin()
feed(rec, bytes(400))
chk('abstains when nothing tiles', rec.solve(1)[0] is None, rec.solve(1)[1])

# 5. abstains when the start slot is unknown
chk('abstains on a bad start slot', rec_for(pairs).solve(9)[0] is None)

# 6. abstains when two opcodes both look like swaps
rec = pktjochul.PktJochul()
rec.begin()
both = b''
for a, b in pairs:
    both += frame(SWAP_OP, bytes([0x01, a, b, 0, 0]))
    both += frame(0x2000, bytes([0x01, b, a, 0, 0]))
feed(rec, both)
ans6, info6 = rec.solve(1)
chk('abstains on two plausible opcodes', ans6 is None and 'ambiguous' in info6, info6)

# 7. abstains when too few swaps
chk('abstains under MIN_SWAPS', rec_for([(1, 2), (2, 3)]).solve(1)[0] is None)

# 8. retransmitted segment is not double counted
rec = pktjochul.PktJochul()
rec.begin()
one = (frame(SWAP_OP, bytes([0x01, 1, 3, 0, 0]))
       + frame(SWAP_OP, bytes([0x01, 3, 4, 0, 0]))
       + frame(SWAP_OP, bytes([0x01, 4, 5, 0, 0])))
rec.feed('down', one)
rec.feed('down', one)
chk('dedupes a retransmit', rec.solve(1)[1].count('swaps=3') == 1, rec.solve(1)[1])

# 9. client pick cross-check
rec = pktjochul.PktJochul()
rec.begin()
feed(rec, stream(pairs))
rec.feed('up', frame(0x9001, bytes([4])))
chk('reads the client pick', rec.client_pick() == 4, rec.client_pick())

# 10. begin() clears the previous round
rec = pktjochul.PktJochul()
rec.begin()
feed(rec, stream([(1, 2), (2, 3), (3, 4)]))
rec.begin()
feed(rec, stream([(4, 5), (1, 4), (2, 5)]))
chk('begin() starts a clean round',
    rec.solve(1)[0] == pktjochul.PktJochul._replay([(4, 5), (1, 4), (2, 5)]).index(1) + 1)

# 11. the real 0xee00 position-broadcast shape must abstain, not answer.
# Layout read off three captured real rounds (BXBO-5 replay): `len|op|03 00 00 count|records`,
# each record `id(2) 02 y x(2) 00`. Offset 4 is the subtype (3 on every frame) and offset 7 the
# record count, so (4,7) reads as a "swap pair" (3,count) on most frames and (7,10) as (count,2).
# The pre-BXBO-5 gate (pair-tuple variety only) answered from exactly these columns on two real
# rounds; a column with one side pinned to a single value is not swap data.
import random  # noqa: E402
rng = random.Random(7)
ee = b''
for count in [1, 2, 1, 4, 1, 2, 2, 1, 4, 1, 2, 1, 1, 2, 4, 1, 3, 1, 2, 1] * 3:
    body = bytes([3, 0, 0, count])
    for _ in range(count):
        body += bytes([rng.randrange(256), rng.randrange(256), 2, rng.randrange(256),
                       rng.randrange(256), rng.randrange(1, 3), 0])
    ee += frame(0xee00, body)
rec = pktjochul.PktJochul()
rec.begin()
feed(rec, ee)
ans11, info11 = rec.solve(1)
chk('abstains on the real 0xee00 subtype/count shape', ans11 is None and 'no frame column' in info11,
    f'ans={ans11} {info11}')

print()
if fails:
    print(f'{len(fails)} FAILED: ' + ', '.join(fails))
    sys.exit(1)
print('ALL PASS')
