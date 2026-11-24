#!/usr/bin/env python3
"""Probe the dump around the carved PE to see whether section data is really there."""
import collections
import math
import struct
import sys

d = open(sys.argv[1], 'rb').read()
n = len(d)
off = int(sys.argv[2], 0)


def ent(b):
    if not b:
        return 0.0
    c = collections.Counter(b)
    k = len(b)
    return -sum(v / k * math.log2(v / k) for v in c.values())


lf = struct.unpack_from('<I', d, off + 0x3c)[0]
pe = off + lf
ns = struct.unpack_from('<H', d, pe + 6)[0]
optsz = struct.unpack_from('<H', d, pe + 20)[0]
so = pe + 24 + optsz
print('inner pe %#x nsec %d' % (pe, ns))
for i in range(ns):
    o = so + 40 * i
    nm = d[o:o + 8].rstrip(b'\0')
    vs, va, rs, rp = struct.unpack_from('<4I', d, o + 8)
    print('  %-10r va %#x vs %#x rp %#x rs %#x' % (nm, va, vs, rp, rs))

print('--- 64K window entropy / string counts 0x1000000..0x1700000 ---')
base = 0x1000000
for w in range(base, min(0x1700000, n), 0x10000):
    blk = d[w:w + 0x10000]
    nz = sum(1 for b in blk if b)
    if not nz:
        continue
    cnt = {k: blk.count(k) for k in (b'Gersang', b'xign', b'kernel32', b'IDR_')}
    print('  %#010x ent %5.2f nz %5d %s' % (w, ent(blk), nz,
                                            ' '.join('%s=%d' % (k.decode(), v) for k, v in cnt.items() if v)))

print('--- sample bytes at rdata start %#x ---' % (off + 0x233000))
print(d[off + 0x233000:off + 0x233000 + 128].hex())
print('--- ascii runs ---')
s = off + 0x233000
blk = d[s:s + 0x30000]
run = bytearray()
hits = 0
for b in blk:
    if 32 <= b < 127:
        run.append(b)
    else:
        if len(run) >= 6:
            print('   ', run.decode('latin1'))
            hits += 1
            if hits > 40:
                break
        run = bytearray()
