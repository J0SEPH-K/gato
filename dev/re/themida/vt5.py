"""Dump vtable slots (4-byte RVAs, zeros = pure virtual) for the jochel classes."""
import struct
import pe
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

d = pe.d
IB = pe.IB
md = Cs(CS_ARCH_X86, CS_MODE_64)
TEXT_LO, TEXT_HI = 0x1000, 0xa38000


def find_vt(col_rva):
    pat = struct.pack('<I', col_rva)
    out, k = [], d.find(pat)
    while k >= 0:
        if pe.o2r(k) is not None:
            out.append(k + 4)
        k = d.find(pat, k + 1)
    return out


def slots(off, limit=120):
    out = []
    for i in range(limit):
        v = struct.unpack_from('<I', d, off + 4 * i)[0]
        if v == 0:
            out.append(0)
            continue
        if not (TEXT_LO <= v < TEXT_HI):
            break
        out.append(v)
    while out and out[-1] == 0:
        out.pop()
    return out


def show(label, col_rva):
    for vto in find_vt(col_rva):
        fs = slots(vto)
        print('\n##### %s COL=0x%x vt=0x%x slots=%d' % (label, col_rva, pe.o2r(vto) or 0, len(fs)))
        for i, f in enumerate(fs):
            if not f:
                print('  [%d] pure' % i)
                continue
            fo = pe.r2o(f)
            ins = list(md.disasm(d[fo:fo + 400], IB + f))[:50]
            calls, strs, imms = [], [], []
            for x in ins:
                if x.mnemonic == 'call' and x.op_str.startswith('0x'):
                    calls.append(int(x.op_str, 16) - IB)
                if 'rip +' in x.op_str:
                    try:
                        disp = x.op_str.split('rip +')[1].split(']')[0].strip()
                        t = x.address + x.size + int(disp, 16) - IB
                        ro = pe.r2o(t)
                        s = pe.cstr(ro, 80) if ro else b''
                        if len(s) > 2 and all(32 <= c < 127 for c in s):
                            strs.append(s.decode())
                    except Exception:
                        pass
                if x.mnemonic in ('cmp', 'mov', 'add', 'lea', 'shl') and ',' in x.op_str:
                    t = x.op_str.split(',')[-1].strip()
                    if t.startswith('0x'):
                        try:
                            imms.append(int(t, 16))
                        except ValueError:
                            pass
            print('  [%d] rva=0x%x n=%d calls=%s imm=%s strs=%s'
                  % (i, f, len(ins), [hex(c) for c in calls[:10]],
                     [hex(v) for v in imms[:10]], strs[:4]))


if __name__ == '__main__':
    show('CSecretInspector_Parser', 0x1182988)
    show('CQuestionState', 0x1177740)
    show('CPrepareQuestionState', 0x11776c0)
