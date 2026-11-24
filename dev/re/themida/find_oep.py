#!/usr/bin/env python3
"""Scan a dumped image for the unpacked payload.

Themida leaves the original .themida virtual range uninitialized in the file and
fills it at runtime. So: find MZ/PE pairs inside the dump, score them, and report
section entropy for the outer image.
"""
import collections
import math
import struct
import sys


def ent(b):
    if not b:
        return 0.0
    c = collections.Counter(b)
    n = len(b)
    return -sum(v / n * math.log2(v / n) for v in c.values())


def main():
    p = sys.argv[1]
    d = open(p, 'rb').read()
    n = len(d)
    print('size %d' % n)
    pe = struct.unpack_from('<I', d, 0x3c)[0]
    print('outer lfanew %#x sig %r' % (pe, d[pe:pe + 4]))
    ns = struct.unpack_from('<H', d, pe + 6)[0]
    optsz = struct.unpack_from('<H', d, pe + 20)[0]
    so = pe + 24 + optsz
    print('--- outer sections, memory content ---')
    for i in range(ns):
        o = so + 40 * i
        nm = d[o:o + 8].rstrip(b'\0').decode('latin1')
        vs, va, rs, rp = struct.unpack_from('<4I', d, o + 8)
        body = d[va:va + vs]
        nz = sum(1 for b in body if b)
        print('  %-10r va %08x vs %08x ent %5.2f nonzero %d' % (nm, va, vs, ent(body), nz))
    print('--- embedded MZ candidates ---')
    idx = 0
    hits = 0
    while hits < 40:
        i = d.find(b'MZ', idx)
        if i < 0:
            break
        idx = i + 1
        if i + 0x40 > n:
            continue
        try:
            lf = struct.unpack_from('<I', d, i + 0x3c)[0]
        except struct.error:
            continue
        if lf > 0x400 or i + lf + 4 > n:
            continue
        if d[i + lf:i + lf + 4] != b'PE\0\0':
            continue
        mach = struct.unpack_from('<H', d, i + lf + 4)[0]
        if mach not in (0x14c, 0x8664):
            continue
        magic = struct.unpack_from('<H', d, i + lf + 24)[0]
        if magic not in (0x10b, 0x20b):
            continue
        ep = struct.unpack_from('<I', d, i + lf + 24 + 16)[0]
        nsx = struct.unpack_from('<H', d, i + lf + 6)[0]
        secs = []
        o = i + lf + 24 + struct.unpack_from('<H', d, i + lf + 20)[0]
        ok = True
        for k in range(min(nsx, 16)):
            q = o + 40 * k
            if q + 40 > n:
                ok = False
                break
            nm = d[q:q + 8].rstrip(b'\0')
            vs, va, rs, rp = struct.unpack_from('<4I', d, q + 8)
            if vs > 0x2000000:
                ok = False
            secs.append((nm, va, vs))
        hits += 1
        print('  off %#x mach %#x magic %#x nsec %d ep %#x ok %s' % (i, mach, magic, nsx, ep, ok))
        for nm, va, vs in secs:
            print('      %r va %#x vs %#x' % (nm, va, vs))
    print('hits %d' % hits)


if __name__ == '__main__':
    main()
