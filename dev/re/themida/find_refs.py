#!/usr/bin/env python3
"""Find who reads the SecretInspector data tables.

The mob name is not a literal in the image (names come from the client data
tables), so the struct cannot be found by searching '조철희'. What IS in the image
is the table name and the asset paths. Code that opens SecretInspector.txt must
know the row layout, so its references are the reversing entry point.

File offset -> RVA goes through the section map; using the raw file offset as an
RVA silently misses every reference.

For each target it looks for:
  * absolute 8-byte little-endian pointer (data tables, vtables, immediates)
  * RIP-relative disp32 (lea r64,[rip+disp] / mov reg,[rip+disp])
"""
import struct
import sys

p = sys.argv[1]
d = open(p, 'rb').read()

pe = struct.unpack_from('<I', d, 0x3c)[0]
opt = pe + 24
BASE = struct.unpack_from('<Q', d, opt + 24)[0]
ns = struct.unpack_from('<H', d, pe + 6)[0]
so = opt + struct.unpack_from('<H', d, pe + 20)[0]
SECS = []
for i in range(ns):
    o = so + 40 * i
    nm = d[o:o + 8].rstrip(b'\0').decode('latin1')
    vs, va, rs, rp = struct.unpack_from('<4I', d, o + 8)
    SECS.append((nm, va, vs, rp, rs))


def off2rva(off):
    for nm, va, vs, rp, rs in SECS:
        if rp <= off < rp + rs:
            return va + (off - rp)
    return None


TARGET_OFFS = {
    'SecretInspector.txt': 0xae5d08,
    'UI-SecretInspector.json': 0xb159ab,
    'Mapae.agf': 0xb3e493,
    'SecretInspector(asset dir)': 0xb3e32b,
}

for label, off in TARGET_OFFS.items():
    rva = off2rva(off)
    if rva is None:
        print('=== %s: off %#x not in any section' % (label, off))
        continue
    va = BASE + rva
    print('=== %s  off %#x rva %#x va %#x' % (label, off, rva, va))

    pat = struct.pack('<Q', va)
    hits = []
    i = d.find(pat)
    while i >= 0 and len(hits) < 12:
        hits.append(i)
        i = d.find(pat, i + 1)
    print('  abs8 refs: %s' % (' '.join('%#x(rva %#x)' % (h, off2rva(h) or 0) for h in hits) or '-'))

    rip = []
    key = pat[:4]
    i = 0
    n = len(d)
    while i < n - 8 and len(rip) < 20:
        i = d.find(key, i)
        if i < 0:
            break
        r = off2rva(i)
        if r is not None:
            disp = rva - (r + 4)
            if -0x80000000 <= disp < 0x80000000 and d[i:i + 4] == struct.pack('<i', disp):
                rip.append((i, r))
        i += 1
    print('  rip-rel refs: %s' % (' '.join('%#x(rva %#x)' % (o, r) for o, r in rip) or '-'))
    for o, r in rip[:6]:
        lo = max(0, o - 24)
        print('    @rva %#x  %s' % (r, d[lo:o + 12].hex()))
    print()
