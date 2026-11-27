#!/usr/bin/env python3
"""Locate the 조철희 name (cp949 + utf16) and SecretInspector refs in the unpacked image.

Static half of the entity-struct reversal: a hit gives a file offset, and every code
reference to that address is a place where the entity's name field is compared or built.
"""
import sys

p = sys.argv[1]
d = open(p, 'rb').read()
IMG_BASE = 0x7ff779bc0000

needles = {
    'cp949': '조철희'.encode('cp949'),
    'utf16': '조철희'.encode('utf-16-le'),
    'secret': b'SecretInspector',
    'mapae': b'Mapae',
}
for k, nd in needles.items():
    offs = []
    i = d.find(nd)
    while i >= 0 and len(offs) < 40:
        offs.append(i)
        i = d.find(nd, i + 1)
    print('%-8s len=%d hits=%d %s' % (k, len(nd), len(offs),
                                     ' '.join(hex(o) for o in offs[:12])))
    for o in offs[:6]:
        s = o
        while s > 0 and 32 <= d[s - 1] < 127:
            s -= 1
        e = o
        while e < len(d) and 32 <= d[e] < 127:
            e += 1
        print('   @%#x va %#x  %r' % (o, IMG_BASE + o, d[s:min(e, s + 90)]))

# little-endian 8-byte VA refs to each cp949 hit (mov reg, imm64 / data pointer)
for k in ('cp949', 'utf16'):
    nd = needles[k]
    i = d.find(nd)
    while i >= 0:
        va = IMG_BASE + i
        pat = va.to_bytes(8, 'little')
        refs = []
        j = d.find(pat)
        while j >= 0 and len(refs) < 20:
            refs.append(j)
            j = d.find(pat, j + 1)
        if refs:
            print('%s @va %#x refs(8B): %s' % (k, va, ' '.join(hex(r) for r in refs)))
        i = d.find(nd, i + 1)
