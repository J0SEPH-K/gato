#!/usr/bin/env python3
"""Find the real image base of the decrypted Gersang.exe by validating the import descriptor directory at every 4K-aligned candidate base."""
import struct
import sys

d = open(sys.argv[1], 'rb').read()
N = len(d)
IMP_RVA = 0x4E5C6C
SIZEIMG = 0x590000


def cstr(o, cap=64):
    e = d.find(b'\0', o, min(o + cap, N))
    if e < 0:
        return ''
    return d[o:e].decode('latin1')


hits = []
for base in range(0x12000000, 0x16000000, 0x1000):
    o = base + IMP_RVA
    if o + 20 > N:
        continue
    oft, ts, fc, name, ft = struct.unpack_from('<IIIII', d, o)
    if not (0 < name < SIZEIMG and (oft or ft)):
        continue
    nm = cstr(base + name, 32)
    if not nm.lower().endswith(('.dll', '.drv', '.exe')) or len(nm) < 5:
        continue
    if not all(32 <= c < 127 for c in nm.encode('latin1')):
        continue
    tr = oft or ft
    if not (0 < tr < SIZEIMG):
        continue
    ok = 0
    for j in range(8):
        p = base + tr + 8 * j
        v = struct.unpack_from('<Q', d, p)[0] if p + 8 <= N else 0
        if v == 0:
            break
        if v >> 63:
            ok += 1
            continue
        r = v & 0x7FFFFFFF
        if not (0 < r < SIZEIMG):
            continue
        fn = cstr(base + r + 2, 40)
        if len(fn) > 2 and all(32 <= c < 127 for c in fn.encode('latin1')):
            ok += 1
    if ok < 2:
        continue
    hits.append((base, nm, ok))
    print('CAND base %#x  first dll %-14s valid_thunks %d' % (base, nm, ok))

print('total %d' % len(hits))
for base, nm, ok in hits[:4]:
    print('\n=== base %#x dll list ===' % base)
    k = 0
    while k < 200:
        o = base + IMP_RVA + 20 * k
        if o + 20 > N:
            break
        oft, ts, fc, name, ft = struct.unpack_from('<IIIII', d, o)
        if not (oft or name or ft):
            break
        dll = cstr(base + name, 64) if 0 < name < SIZEIMG else '?'
        cnt = 0
        tr = oft or ft
        while cnt < 4000:
            p = base + tr + 8 * cnt
            v = struct.unpack_from('<Q', d, p)[0] if p + 8 <= N else 0
            if v == 0:
                break
            cnt += 1
        print('  %-22s %d' % (dll, cnt))
        k += 1
    ep = base + 0x135EFC
    print('  entry bytes at %#x: %s' % (ep, d[ep:ep + 24].hex()))
