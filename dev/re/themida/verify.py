#!/usr/bin/env python3
"""Validate a carved image: disassemble entry, dump import descriptors, string density."""
import struct
import sys

import capstone

d = open(sys.argv[1], 'rb').read()
pe = struct.unpack_from('<I', d, 0x3c)[0]
opt = pe + 24
magic = struct.unpack_from('<H', d, opt)[0]
ep = struct.unpack_from('<I', d, opt + 16)[0]
ib = struct.unpack_from('<Q', d, opt + 24)[0] if magic == 0x20b else struct.unpack_from('<I', d, opt + 28)[0]
ns = struct.unpack_from('<H', d, pe + 6)[0]
so = opt + struct.unpack_from('<H', d, pe + 20)[0]
secs = []
for i in range(ns):
    o = so + 40 * i
    vs, va, rs, rp = struct.unpack_from('<4I', d, o + 8)
    secs.append((va, max(vs, rs), rp, rs, d[o:o + 8].rstrip(b'\0').decode('latin1')))


def off(rva):
    for va, vs, rp, rs, nm in secs:
        if va <= rva < va + vs:
            return rp + (rva - va)
    return None


print('imagebase %#x entry %#x' % (ib, ep))
print('--- 24 instructions at entry ---')
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
md.detail = False
p = off(ep)
for n, ins in enumerate(md.disasm(d[p:p + 96], ib + ep)):
    print('  %#x  %-8s %s' % (ins.address, ins.bytes.hex(), ins.mnemonic + ' ' + ins.op_str))
    if n > 22:
        break

imp_rva, imp_sz = struct.unpack_from('<II', d, opt + (120 if magic == 0x20b else 104))
print('--- import dir rva %#x size %#x ---' % (imp_rva, imp_sz))
o = off(imp_rva) if imp_rva else None
if o:
    print('  raw bytes:', d[o:o + 80].hex())
    k = 0
    while k < 40:
        dsc = d[o + 20 * k:o + 20 * k + 20]
        if len(dsc) < 20 or not any(dsc):
            break
        oft, ts, fc, name, ft = struct.unpack('<IIIII', dsc)
        np = off(name) if name else None
        dll = d[np:d.find(b'\0', np)].decode('latin1') if np else '?'
        print('  dsc%d oft %#x name %#x -> %r' % (k, oft, name, dll))
        k += 1
else:
    print('  (import dir not mappable)')

print('--- ascii string runs >= 8 in each section ---')
for va, vs, rp, rs, nm in secs:
    body = d[rp:rp + rs]
    runs, cur, tot = [], bytearray(), 0
    for b in body:
        if 32 <= b < 127:
            cur.append(b)
        else:
            if len(cur) >= 8:
                tot += 1
                if len(runs) < 6:
                    runs.append(cur.decode('latin1'))
            cur = bytearray()
    print('  %-10s runs>=8: %d  %s' % (nm, tot, runs))
