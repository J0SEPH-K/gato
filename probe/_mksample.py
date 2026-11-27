import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pktjochul  # noqa: E402
import struct  # noqa: E402

OUT = '/tmp/replay_sample.log'


def frame(op, body, endian='little'):
    return struct.pack('<HH' if endian == 'little' else '>HH', 4 + len(body), op) + body


pairs = [(1, 3), (3, 5), (2, 4), (1, 2), (4, 5)]
rec = pktjochul.PktJochul()
rec.begin()
for a, b in pairs:
    rec.feed('down', frame(0x1234, bytes([0x01, a, b, 0, 0])))
    rec.feed('down', frame(0x7777, bytes([0x01, 1, 2, 9, 9])))
rec.feed('up', frame(0x9001, bytes([4])))
n = rec.dump(OUT)
print('wrote', n, 'bytes to', OUT)
print('solve ->', rec.solve(1))
