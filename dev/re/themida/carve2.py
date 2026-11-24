#!/usr/bin/env python3
"""Rebuild a loadable-shaped PE from the live flat image dump.

Dump offset == RVA, dump length == SizeOfImage. Header comes from the dump,
ImageBase is kept at the real runtime base, every section gets real raw data
carved out of the dump (the on-disk .themida had raw size 0).

Usage: carve2.py <dump> <out.exe>
"""
import math
import struct
import sys

FA = 0x200
SA = 0x1000


def align(v, a):
    return (v + a - 1) // a * a


def ent(b):
    if not b:
        return 0.0
    c = [0] * 256
    for x in b:
        c[x] += 1
    return -sum((v / len(b)) * math.log2(v / len(b)) for v in c if v)


def main():
    dump, out = sys.argv[1], sys.argv[2]
    d = open(dump, 'rb').read()
    assert d[:2] == b'MZ', 'dump not an image'
    lf = struct.unpack_from('<I', d, 0x3c)[0]
    assert d[lf:lf + 4] == b'PE\0\0', 'bad PE sig'
    nsec = struct.unpack_from('<H', d, lf + 6)[0]
    soh = struct.unpack_from('<H', d, lf + 20)[0]
    opt = lf + 24
    magic = struct.unpack_from('<H', d, opt)[0]
    assert magic == 0x20b, 'not PE32+'
    ib = struct.unpack_from('<Q', d, opt + 24)[0]
    entry = struct.unpack_from('<I', d, opt + 16)[0]
    sizeimg = struct.unpack_from('<I', d, opt + 56)[0]
    assert sizeimg <= len(d), 'dump shorter than SizeOfImage'
    st = opt + soh
    secs = []
    for k in range(nsec):
        o = st + 40 * k
        nm = d[o:o + 8]
        vs, va, rs, rp = struct.unpack_from('<IIII', d, o + 8)
        secs.append({'o': o, 'name': nm.rstrip(b'\0').decode('latin1', 'replace'),
                     'vs': vs, 'va': va})
    hdr_end = max(FA, align(st + 40 * nsec, FA))
    buf = bytearray(d[:hdr_end])
    off = hdr_end
    for s in secs:
        body = d[s['va']:s['va'] + s['vs']] if s['vs'] else b''
        rs = align(len(body), FA)
        struct.pack_into('<II', buf, s['o'] + 16, rs, off if rs else 0)
        buf += body + b'\0' * (rs - len(body))
        s['rs'] = rs
        off += rs
    struct.pack_into('<Q', buf, opt + 24, ib)
    struct.pack_into('<I', buf, opt + 16, entry)
    open(out, 'wb').write(bytes(buf))
    print('wrote %s %d bytes  imagebase %#x entry %#x sizeimg %#x' % (out, len(buf), ib, entry, sizeimg))
    for s in secs:
        body = d[s['va']:s['va'] + s['vs']] if s['vs'] else b''
        print('  %-9s va %#010x vs %#08x rs %#08x ent %.2f' % (s['name'], s['va'], s['vs'], s['rs'], ent(body[:0x100000])))


main()
