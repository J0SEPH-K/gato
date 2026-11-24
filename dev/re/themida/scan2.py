#!/usr/bin/env python3
"""Scan the runtime .themida region of the dump for the decrypted image."""
import collections
import math
import struct
import sys

d = open(sys.argv[1], 'rb').read()
n = len(d)
LO, HI = 0x13417000, 0x13a89000

print('dump %d bytes, region %#x..%#x (%d bytes)' % (n, LO, HI, HI - LO))
print('--- MZ occurrences inside region ---')
i = LO
hits = 0
while True:
    i = d.find(b'MZ', i, HI)
    if i < 0:
        break
    lf = struct.unpack_from('<I', d, i + 0x3c)[0] if i + 0x40 < n else 0
    sig = d[i + lf:i + lf + 4] if 0x40 < lf < 0x400 else b''
    print('  %#x lfanew %#x sig %r' % (i, lf, sig))
    hits += 1
    i += 1
print('  total %d' % hits)

print('--- 64K window: entropy + prologue-byte density ---')
for w in range(LO, HI, 0x10000):
    blk = d[w:w + 0x10000]
    if not blk:
        break
    c = collections.Counter(blk)
    e = -sum(v / len(blk) * math.log2(v / len(blk)) for v in c.values())
    nz = sum(1 for b in blk if b)
    pro = (blk.count(b'\x48\x89') + blk.count(b'\x48\x8b') + blk.count(b'\x55\x48')
           + blk.count(b'\xe8') + blk.count(b'\xcc'))
    if nz == 0:
        continue
    print('  %#010x ent %5.2f nz %5d pro %4d' % (w, e, nz, pro))
