import struct
import pe

d = pe.d
IB = pe.IB
base = d.find(b'.?AVCSecretInspector_Parser@@')
VT = struct.unpack_from('<Q', d, base - 16)[0]
print('typeinfo vfptr', hex(VT))

# x64 COL layout: sig(4) off(4) cd(4) pTypeDescriptor(8) pCHD(8)  -> type_info.name at COL+12+16
pat = struct.pack('<Q', VT)
cols = []
j = d.find(pat)
while j >= 0:
    if d[j + 16:j + 20] == b'.?AV':
        r = pe.o2r(j)
        if r is not None:
            cols.append((r - 12, pe.cstr(j + 16)))
    j = d.find(pat, j + 1)
print('cols', len(cols))

want = [b'SecretInspector', b'QuestionState', b'Mapae']
for crva, nm in cols:
    if not any(w.lower() in nm.lower() for w in want):
        continue
    print('\n===', nm.decode('latin1'), 'COL', hex(crva))
    co = pe.r2o(crva)
    if co is not None:
        sig, off, cd = struct.unpack_from('<3I', d, co)
        print('   sig', sig, 'off', off, 'cd', cd)
    pk = struct.pack('<Q', IB + crva)
    k = d.find(pk)
    n = 0
    while k >= 0:
        rr = pe.o2r(k)
        if rr is not None:
            n += 1
            print('   vftable at', hex(rr), 'fileoff', hex(k))
            vo = k
            for i in range(20):
                v = struct.unpack_from('<Q', d, vo + 8 * i)[0]
                if IB <= v < IB + len(d):
                    print('      fn', i, hex(v - IB))
        k = d.find(pk, k + 1)
    if not n:
        print('   no vftable refs')
