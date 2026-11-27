"""Disassemble the real vftable of the jochel classes (vftable starts at the COL anchor)."""
import struct
import pe
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

d = pe.d
IB = pe.IB
md = Cs(CS_ARCH_X86, CS_MODE_64)
CODE_LO, CODE_HI = 0x1277000, 0x13387000


def show(label, anchor):
    o = pe.r2o(anchor)
    print('\n##### %s anchor=0x%x' % (label, anchor))
    for i in range(40):
        v = struct.unpack_from('<I', d, o + 4 * i)[0]
        if not (CODE_LO <= v < CODE_HI):
            print('  [%d] 0x%x (non-code)' % (i, v))
            continue
        fo = pe.r2o(v)
        ins = list(md.disasm(d[fo:fo + 400], IB + v))[:45]
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
            if x.mnemonic in ('cmp', 'mov', 'add', 'shl', 'imul') and ',' in x.op_str:
                t = x.op_str.split(',')[-1].strip()
                if t.startswith('0x'):
                    try:
                        imms.append(int(t, 16))
                    except ValueError:
                        pass
        print('  [%d] rva=0x%x n=%d calls=%s imm=%s strs=%s'
              % (i, v, len(ins), [hex(c) for c in calls[:10]],
                 [hex(x) for x in imms[:10]], strs[:4]))


show('CSecretInspector_Parser', 0x1182988)
show('CQuestionState', 0x1177740)
show('CPrepareQuestionState', 0x11776c0)
