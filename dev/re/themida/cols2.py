import struct
import pe

d = pe.d
IB = pe.IB
base = d.find(b'.?AVCSecretInspector_Parser@@')
VT = struct.unpack_from('<Q', d, base - 16)[0]
print('typeinfo vfptr', hex(VT), 'rva', hex(VT - IB))
vto = pe.r2o(VT - IB)
print('vfptr fileoff', hex(vto) if vto else None)

pat = struct.pack('<Q', VT)
cols = []
j = d.find(pat)
while j >= 0:
    if d[j + 16:j + 20] == b'.?AV':
        r = pe.o2r(j)
        if r is not None:
            cols.append((r, pe.cstr(j + 16)))
    j = d.find(pat, j + 1)
print('cols', len(cols))

want = [b'SecretInspector', b'MiniGame', b'QuestionState', b'Mapae', b'FruitBasket', b'Content']
for crva, nm in cols:
    if not any(w.lower() in nm.lower() for w in want):
        continue
    print('\n===', nm.decode('latin1'), 'colRVA', hex(crva))
    pk = struct.pack('<Q', IB + crva)
    k = d.find(pk)
    while k >= 0:
        rr = pe.o2r(k)
        if rr is not None:
            print('   vftable RVA', hex(rr))
            vo = pe.r2o(rr)
            if vo:
                for i in range(16):
                    v = struct.unpack_from('<Q', d, vo + 8 * i)[0]
                    if IB <= v < IB + len(d):
                        print('     fn', i, hex(v - IB))
        k = d.find(pk, k + 1)
