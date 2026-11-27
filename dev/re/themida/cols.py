import struct

PATH = 'unpacked_live.exe'
d = open(PATH, 'rb').read()
pe = struct.unpack_from('<I', d, 0x3c)[0]
opt = pe + 24
ns = struct.unpack_from('<H', d, pe + 6)[0]
so = opt + struct.unpack_from('<H', d, opt + 20)[0]
IB = struct.unpack_from('<Q', d, opt + 24)[0]
SECS = []
for i in range(ns):
    o = so + 40 * i
    vs, va, rs, rp = struct.unpack_from('<4I', d, o + 8)
    SECS.append((va, vs, rp, rs))
print('imagebase', hex(IB), 'filelen', hex(len(d)))


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


base = d.find(b'.?AVCSecretInspector_Parser@@')
VT = struct.unpack_from('<Q', d, base - 16)[0]
print('typeinfo vfptr', hex(VT), 'rva', hex(VT - IB))
vto = r2o(VT - IB)
print('vfptr fileoff', hex(vto) if vto else None)
if vto:
    for i in range(8):
        v = struct.unpack_from('<Q', d, vto + 8 * i)[0]
        print('  slot', i, hex(v), 'rva', hex(v - IB) if v > IB else '')

pat = struct.pack('<Q', VT)
j = d.find(pat)
cols = []
while j >= 0:
    if d[j + 16:j + 20] == b'.?AV':
        r = o2r(j)
        if r is not None:
            cols.append((r, d[j + 16:d.find(b'\0', j + 16, j + 200)]))
    j = d.find(pat, j + 1)
print('cols', len(cols))

want = [b'SecretInspector', b'MiniGame', b'QuestionState', b'Mapae', b'FruitBasket']
for crva, nm in cols:
    if not any(w.lower() in nm.lower() for w in want):
        continue
    print('\n===', nm.decode('latin1'), 'colRVA', hex(crva))
    pk = struct.pack('<Q', IB + crva)
    k = d.find(pk)
    while k >= 0:
        rr = o2r(k)
        if rr is not None:
            print('   vftable RVA', hex(rr))
            vo = r2o(rr)
            if vo:
                for i in range(14):
                    v = struct.unpack_from('<Q', d, vo + 8 * i)[0]
                    if IB <= v < IB + len(d):
                        print('     fn', i, hex(v - IB))
        k = d.find(pk, k + 1)
