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
    nm = d[o:o + 8].rstrip(b'\0').decode('latin1', 'replace')
    vs, va, rs, rp = struct.unpack_from('<4I', d, o + 8)
    SECS.append((nm, va, vs, rp, rs))


def o2r(off):
    for nm, va, vs, rp, rs in SECS:
        if rp <= off < rp + rs:
            return va + off - rp
    return None


def r2o(rva):
    for nm, va, vs, rp, rs in SECS:
        if va <= rva < va + rs:
            return rp + rva - va
    return None


def q(off):
    return struct.unpack_from('<Q', d, off)[0]


def cstr(off, lim=200):
    e = d.find(b'\0', off, off + lim)
    return d[off:e] if e > 0 else b''


base = d.find(b'.?AVCSecretInspector_Parser@@')
VT = q(base - 16)
print('typeinfo vfptr', hex(VT), 'imagebase', hex(IB))
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
print('descriptors found', len(desc))

KW = [b'SecretInspector', b'Mapae', b'Jochul', b'Reta', b'Leta', b'Amhaeng',
      b'Inspector', b'MiniGame', b'Mini', b'Puzzle', b'Question']


def refs(va, limit=20):
    p = struct.pack('<Q', IB + va)
    out = []
    j = d.find(p)
    while j >= 0 and len(out) < limit:
        r = o2r(j)
        if r is not None:
            out.append(r)
        j = d.find(p, j + 1)
    return out


names = [nm for _r, _j, nm in desc]
print('\nall descriptor names matching keywords:')
for nm in names:
    if any(k.lower() in nm.lower() for k in KW):
        print('  ', nm.decode('latin1'))

for r, j, nm in desc:
    if not any(k.lower() in nm.lower() for k in KW):
        continue
    print('\n===', nm.decode('latin1'), 'descRVA', hex(r))
    for cr in refs(r):
        o = r2o(cr - 16)
        if o is None:
            continue
        sig, off, cd = struct.unpack_from('<3I', d, o)
        if sig != 1:
            continue
        col = cr - 16
        print('  COL', hex(col), 'offset', off, 'cdOffset', cd)
        for vr in refs(col):
            print('    vftable', hex(vr))
            for rr in refs(vr, 6):
                print('      vtref', hex(rr))
