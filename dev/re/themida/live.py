#!/usr/bin/env python3
"""Validate the LIVE image in the dump: outer PE header, entry disasm, .themida code density."""
import struct
import sys

import capstone

d = open(sys.argv[1], 'rb').read()
N = len(d)

pe = struct.unpack_from('<I', d, 0x3c)[0]
opt = pe + 24
magic = struct.unpack_from('<H', d, opt)[0]
ep = struct.unpack_from('<I', d, opt + 16)[0]
ib = struct.unpack_from('<Q', d, opt + 24)[0]
sizeimg = struct.unpack_from('<I', d, opt + 56)[0]
ns = struct.unpack_from('<H', d, pe + 6)[0]
so = opt + struct.unpack_from('<H', d, pe + 20)[0]
print('outer: magic %#x imagebase %#x entry %#x sizeimg %#x sections %d  dump %#x' % (magic, ib, ep, sizeimg, ns, N))
secs = []
for i in range(ns):
    o = so + 40 * i
    nm = d[o:o + 8].rstrip(b'\0').decode('latin1')
    vs, va, rs, rp = struct.unpack_from('<4I', d, o + 8)
    secs.append((nm, va, vs, rp, rs))
    body = d[va:va + min(vs, 0x20000)]
    print('  %-10s va %#x vs %#x nz %d/%d' % (nm, va, vs, sum(1 for b in body if b), len(body)))

imp_rva, imp_sz = struct.unpack_from('<II', d, opt + 120)
print('import dir rva %#x size %#x' % (imp_rva, imp_sz))

md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
print('--- 14 insns at outer entry %#x (dump off %#x) ---' % (ep, ep))
for ins in list(md.disasm(d[ep:ep + 64], ib + ep))[:14]:
    print('  %#x %-16s %s %s' % (ins.address, ins.bytes.hex(), ins.mnemonic, ins.op_str))

print('--- 14 insns at .themida start %#x ---' % 0x13417000)
for ins in list(md.disasm(d[0x13417000:0x13417000 + 64], ib + 0x13417000))[:14]:
    print('  %#x %-16s %s %s' % (ins.address, ins.bytes.hex(), ins.mnemonic, ins.op_str))

print('--- ascii strings >=10 in .themida first 4MB ---')
import re
hits = re.findall(rb'[ -~]{10,}', d[0x13417000:0x13417000 + 0x400000])
print('count', len(hits))
for h in hits[:20]:
    print('   ', h[:80])
