#!/usr/bin/env python3
"""Parse the import table of the decrypted inner image straight out of the process dump."""
import struct
import sys

D = open(sys.argv[1], 'rb')
d = D.read()
BASE = int(sys.argv[2], 16) if len(sys.argv) > 2 else 0x105e790

pe = BASE + struct.unpack_from('<I', d, BASE + 0x3c)[0]
opt = pe + 24
magic = struct.unpack_from('<H', d, opt)[0]
ns = struct.unpack_from('<H', d, pe + 6)[0]
so = opt + struct.unpack_from('<H', d, pe + 20)[0]
secs = []
for i in range(ns):
    o = so + 40 * i
    vs, va, rs, rp = struct.unpack_from('<4I', d, o + 8)
    secs.append((va, max(vs, rs)))


def inmap(rva):
    return any(va <= rva < va + vs for va, vs in secs)


def rd(rva, n):
    return d[BASE + rva:BASE + rva + n]


def cstr(rva, cap=256):
    out = bytearray()
    p = BASE + rva
    while len(out) < cap:
        b = d[p]
        if not b:
            break
        out.append(b)
        p += 1
    return out.decode('latin1')


imp_rva, imp_sz = struct.unpack_from('<II', d, opt + (120 if magic == 0x20b else 104))
print('magic %#x  import dir rva %#x size %#x  mappable %s' % (magic, imp_rva, imp_sz, inmap(imp_rva)))

k = 0
total = 0
dlls = []
while k < 300:
    rva = imp_rva + 20 * k
    oft, ts, fc, name, ft = struct.unpack('<IIIII', rd(rva, 20))
    if not (oft or name or ft):
        break
    dll = cstr(name) if inmap(name) else '<%#x>' % name
    thunk_rva = oft or ft
    funcs = []
    j = 0
    while j < 5000 and inmap(thunk_rva + 8 * j):
        v = struct.unpack('<Q', rd(thunk_rva + 8 * j, 8))[0]
        if v == 0:
            break
        if v & (1 << 63):
            funcs.append('#%d' % (v & 0xffff))
        else:
            funcs.append(cstr((v & 0x7fffffff) + 2) if inmap(v & 0x7fffffff) else '<%#x>' % v)
        j += 1
    total += len(funcs)
    dlls.append((dll, funcs))
    print('\n%s  (%d)' % (dll, len(funcs)))
    print('   ' + ', '.join(funcs[:25]) + (' ...' if len(funcs) > 25 else ''))
    k += 1

print('\nDLLs %d  funcs %d' % (len(dlls), total))
