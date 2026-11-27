import struct
import pe

d = pe.d
IB = pe.IB
base = d.find(b'.?AVCSecretInspector_Parser@@')
VT = struct.unpack_from('<Q', d, base - 16)[0]

# occurrences of the typeinfo descriptor pointer sit at COL+16 -> COL = rva-16
pat = struct.pack('<Q', VT)
cols = []
j = d.find(pat)
while j >= 0:
    if d[j + 16:j + 20] == b'.?AV':
        r = pe.o2r(j)
        if r is not None:
            cols.append((r - 16, pe.cstr(j + 16)))
    j = d.find(pat, j + 1)
print('cols', len(cols))

want = [b'SecretInspector', b'MiniGame', b'QuestionState', b'Mapae', b'FruitBasket']
found = 0
for crva, nm in cols:
    if not any(w.lower() in nm.lower() for w in want):
        continue
    found += 1
    print('\n===', nm.decode('latin1'), 'COL RVA', hex(crva))
    pk = struct.pack('<Q', IB + crva)
    k = d.find(pk)
    hits = 0
    while k >= 0:
        rr = pe.o2r(k)
        if rr is not None:
            hits += 1
            print('   vftable RVA', hex(rr))
            vo = pe.r2o(rr)
            if vo:
                for i in range(18):
                    v = struct.unpack_from('<Q', d, vo + 8 * i)[0]
                    if IB <= v < IB + len(d):
                        print('     fn', i, hex(v - IB))
        k = d.find(pk, k + 1)
    if not hits:
        print('   (no vftable refs)')
print('matched classes', found)
