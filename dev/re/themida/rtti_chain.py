import struct
import sys

PATH = sys.argv[1] if len(sys.argv) > 1 else 'unpacked_live.exe'
NAMES = sys.argv[2:] or ['CSecretInspector@@', 'CSecretInspectorMgr@@', 'CMapaeMgr@@', 'CMapae@@', 'CUnitMgr@@', 'CUnit@@']

d = open(PATH, 'rb').read()
pe = struct.unpack_from('<I', d, 0x3C)[0]
opt = pe + 24
IB = struct.unpack_from('<Q', d, opt + 24)[0]
ns = struct.unpack_from('<H', d, pe + 6)[0]
so = opt + struct.unpack_from('<H', d, opt + 20)[0]
SECS = []
for i in range(ns):
    o = so + 40 * i
    vs, va, rs, rp = struct.unpack_from('<4I', d, o + 8)
    nm = d[o:o + 8].rstrip(b'\x00').decode('latin1')
    SECS.append((va, vs, rp, rs, nm))
print('imagebase', hex(IB), 'sections', len(SECS))


def r2o(rva):
    for va, vs, rp, rs, nm in SECS:
        if rp and va <= rva < va + max(vs, rs):
            off = rva - va + rp
            if 0 <= off < len(d):
                return off
    return None


def o2r(off):
    for va, vs, rp, rs, nm in SECS:
        if rp <= off < rp + rs:
            return va + off - rp
    return None


def secname(off):
    for va, vs, rp, rs, nm in SECS:
        if rp <= off < rp + rs:
            return nm
    return '?'


def find_refs(va, limit=8):
    pat = struct.pack('<Q', va)
    out, j = [], d.find(pat)
    while j >= 0 and len(out) < limit:
        r = o2r(j)
        if r is not None:
            out.append((j, r, secname(j)))
        j = d.find(pat, j + 1)
    return out


for t in NAMES:
    # the stored name literally begins with ".?AV", so match on that, not on a NUL prefix
    i = d.find(('.?AV' + t).encode())
    if i < 0:
        print('\n===', t, 'NOT FOUND')
        continue
    rva = o2r(i)
    print('\n=== .?AV' + t, 'file', hex(i), 'rva', hex(rva) if rva else None)
    if rva is None:
        continue
    desc_rva = o2r(i - 16)
    if desc_rva is None:
        print('  descriptor start not mapped (pad/cross-boundary)')
        continue
    print('  type_info vftable ptr', hex(struct.unpack_from('<Q', d, i - 16)[0]))
    td_va = IB + desc_rva
    cols = find_refs(td_va)
    print('  COL refs:', [(hex(a), hex(b), c) for a, b, c in cols])
    for coff, crva, sec in cols:
        col_va = IB + crva
        vt = find_refs(col_va)
        print('    COL', hex(col_va), 'in', sec, '-> vtable refs:', [(hex(a), hex(b), c) for a, b, c in vt])
        for voff, vrva, vsec in vt:
            vt_va = IB + vrva
            code = find_refs(vt_va, limit=6)
            print('      vtable', hex(vt_va), 'in', vsec, '-> code refs:', [(hex(a), hex(b), c) for a, b, c in code])
