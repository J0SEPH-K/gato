import struct
import pe
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

d = pe.d
IB = pe.IB
md = Cs(CS_ARCH_X86, CS_MODE_64)
TEXT_END = 0xa38000


def find_vt(col_rva):
    """vftable[-1] holds the COL RVA; vftable starts 4 bytes after that slot."""
    pat = struct.pack('<I', col_rva)
    out = []
    k = d.find(pat)
    while k >= 0:
        if pe.o2r(k) is not None:
            out.append(k + 4)
        k = d.find(pat, k + 1)
    return out


def slots(off, limit=60):
    out = []
    for i in range(limit):
        v = struct.unpack_from('<I', d, off + 4 * i)[0]
        if v == 0 or v >= TEXT_END:
            break
        out.append(v)
    return out


def show(label, col_rva):
    vts = find_vt(col_rva)
    print('\n##### %s COL=0x%x vftables=%s' % (label, col_rva, [hex(pe.o2r(v) or 0) for v in vts]))
    for vto in vts:
        fs = slots(vto)
        print('  vt fileoff=0x%x slots=%d' % (vto, len(fs)))
        for i, f in enumerate(fs):
            fo = pe.r2o(f)
            if fo is None:
                print('    [%d] 0x%x OUTSIDE' % (i, f)); continue
            ins = list(md.disasm(d[fo:fo + 240], IB + f))[:28]
            calls, strs, imms = [], [], []
            for x in ins:
                if x.mnemonic == 'call' and x.op_str.startswith('0x'):
                    calls.append(int(x.op_str, 16) - IB)
                if 'rip +' in x.op_str:
                    try:
                        disp = x.op_str.split('rip +')[1].split(']')[0].strip()
                        t = x.address + x.size + int(disp, 16) - IB
                        ro = pe.r2o(t)
                        s = pe.cstr(ro, 64) if ro else b''
                        if len(s) > 2 and all(32 <= c < 127 for c in s):
                            strs.append(s.decode())
                    except Exception:
                        pass
                if x.mnemonic in ('cmp', 'mov') and ',' in x.op_str:
                    t = x.op_str.split(',')[-1].strip()
                    if t.startswith('0x'):
                        try:
                            imms.append(int(t, 16))
                        except ValueError:
                            pass
            print('    [%d] rva=0x%x n=%d calls=%s imm=%s strs=%s' % (i, f, len(ins), [hex(c) for c in calls[:8]], [hex(v) for v in imms[:8]], strs[:3]))
            for x in ins[:10]:
                print('        %s %s' % (x.mnemonic, x.op_str))


show('CSecretInspector_Parser', 0x1182988)
show('CQuestionState', 0x1177740)
