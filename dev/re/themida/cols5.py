import struct
import pe

d = pe.d
IB = pe.IB
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

want = [b'SecretInspector', b'QuestionState', b'Mapae', b'MiniGame']
targets = [(r, o, n) for r, o, n in descs if any(w.lower() in n.lower() for w in want)]
print('targets', len(targets))

for r, o, nm in targets:
    print()
    print('===', nm.decode('latin1'), 'descRVA', hex(r))
    colr = None
    for back in range(4, 80):
        p = o - back
        if p < 0:
            break
        sig = struct.unpack_from('<I', d, p)[0]
        if sig != 1:
            continue
        ptd = struct.unpack_from('<Q', d, p + 12)[0]
        if ptd - IB == r:
            colr = pe.o2r(p)
            print('   COL base rva', hex(colr) if colr else None, 'back', back)
            break
    if colr is None:
        print('   COL not located')
        continue
    pk = struct.pack('<Q', IB + colr)
    k = d.find(pk)
    n = 0
    while k >= 0:
        rr = pe.o2r(k)
        if rr is not None:
            n += 1
            print('   vftable rva', hex(rr), 'fileoff', hex(k))
            for i in range(24):
                v = struct.unpack_from('<Q', d, k + 8 * i)[0]
                if IB <= v < IB + len(d):
                    print('      fn', i, hex(v - IB))
        k = d.find(pk, k + 1)
    if not n:
        print('   no vftable refs')
