import struct
import pe

d = pe.d
IB = pe.IB

# x64 COL: sig(4) off(4) cd(4) pTypeDescriptor(RVA,4) pClassDescriptor(RVA,4)
# vftable[-1] (8 bytes before vftable) holds COL RVA.
base = d.find(b'.?AVCSecretInspector_Parser@@')
VT = struct.unpack_from('<Q', d, base - 16)[0]
pat = struct.pack('<Q', VT)
descs = []
j = d.find(pat)
while j >= 0:
    if d[j + 16:j + 20] == b'.?AV':
        r = pe.o2r(j)
        if r is not None:
            descs.append((r, j, pe.cstr(j + 16)))
    j = d.find(pat, j + 1)

want = [b'SecretInspector', b'QuestionState', b'Mapae', b'MiniGame', b'FruitBasket']
targets = [(r, o, n) for r, o, n in descs if any(w.lower() in n.lower() for w in want)]
print('targets', len(targets))

for r, o, nm in targets:
    print()
    print('===', nm.decode('latin1'), 'descRVA', hex(r))
    rp = struct.pack('<I', r)
    cols = []
    k = d.find(rp)
    while k >= 0:
        p = k - 12
        if p >= 0 and struct.unpack_from('<I', d, p)[0] == 1:
            cr = pe.o2r(p)
            if cr is not None:
                cols.append((cr, p))
        k = d.find(rp, k + 1)
    print('   COLs', [hex(c) for c, _ in cols])
    for cr, co in cols:
        off, cd = struct.unpack_from('<2I', d, co + 4)
        print('   COL', hex(cr), 'offset', off, 'cdOffset', cd)
        cp = struct.pack('<I', cr)
        v = d.find(cp)
        while v >= 0:
            vt = v + 8
            vr = pe.o2r(vt)
            if vr is not None:
                print('      vftable rva', hex(vr), 'fileoff', hex(vt))
                for i in range(28):
                    fv = struct.unpack_from('<Q', d, vt + 8 * i)[0]
                    if IB <= fv < IB + len(d):
                        print('        fn', i, hex(fv - IB))
            v = d.find(cp, v + 1)
