import struct

PATH = 'unpacked_live.exe'
d = open(PATH, 'rb').read()
pe = struct.unpack_from('<I', d, 0x3c)[0]
ns = struct.unpack_from('<H', d, pe + 6)[0]
soh = struct.unpack_from('<H', d, pe + 20)[0]
opt = pe + 24
so = opt + soh
IB = struct.unpack_from('<Q', d, opt + 24)[0]
SECS = []
for i in range(ns):
    o = so + 40 * i
    vs, va, rs, rp = struct.unpack_from('<4I', d, o + 8)
    SECS.append((va, vs, rp, rs))


def o2r(off):
    for va, vs, rp, rs in SECS:
        if rp <= off < rp + rs:
            return va + off - rp
    return None


def r2o(rva):
    for va, vs, rp, rs in SECS:
        if va <= rva < va + rs:
            return rp + rva - va
    return None


def cstr(off, lim=200):
    e = d.find(b'\0', off, off + lim)
    return d[off:e] if e > 0 else b''


base = d.find(b'.?AVCSecretInspector_Parser@@')
VT = struct.unpack_from('<Q', d, base - 16)[0]
pat = struct.pack('<Q', VT)
desc = []
j = d.find(pat)
while j >= 0:
    r = o2r(j)
    if r is not None:
        nm = cstr(j + 16)
        if nm.startswith(b'.?AV'):
            desc.append((r, j, nm))
    j = d.find(pat, j + 1)
print('descriptors', len(desc))

for r, j, nm in desc:
    va = IB + r
    pk = struct.pack('<Q', va)
    hits = []
    k = d.find(pk)
    while k >= 0:
        rr = o2r(k)
        if rr is not None:
            hits.append(rr)
        k = d.find(pk, k + 1)
    print(nm.decode('latin1'), 'COLrefs', [hex(h) for h in hits[:10]])
    for cr in hits[:10]:
        o = r2o(cr - 16)
        if o is None:
            print('   col outside file', hex(cr - 16))
            continue
        sig, off, cd = struct.unpack_from('<3I', d, o)
        print('   COL', hex(cr - 16), 'sig', sig, 'off', off, 'cd', cd)
        for v in range(10):
            vp = struct.unpack_from('<Q', d, cr - 16 + 24 + 8 * v)[0]
            if IB <= vp < IB + 0x13e33000:
                print('     vfn', v, hex(vp - IB))
