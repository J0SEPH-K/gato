import struct
import pe
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

d = pe.d
IB = pe.IB
md = Cs(CS_ARCH_X86, CS_MODE_64)
md.detail = True

TEXT_END = 0xa38000


def slots(vt_rva, limit=60):
    o = pe.r2o(vt_rva)
    out = []
    for i in range(limit):
        v = struct.unpack_from('<I', d, o + 4 * i)[0]
        if v == 0 or v >= TEXT_END:
            break
        out.append(v)
    return out


def show(label, vt_rva):
    fs = slots(vt_rva)
    print('\n##### %s vt=0x%x slots=%d' % (label, vt_rva, len(fs)))
    for i, f in enumerate(fs):
        fo = pe.r2o(f)
        if fo is None:
            print('  [%d] 0x%x OUTSIDE' % (i, f))
            continue
        ins = list(md.disasm(d[fo:fo + 300], IB + f))[:40]
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
                    if s and len(s) > 2 and all(32 <= c < 127 for c in s):
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
        print('  [%d] rva=0x%x ins=%d calls=%s strs=%s imm=%s'
              % (i, f, len(ins), [hex(c) for c in calls[:8]], strs[:3], [hex(v) for v in imms[:6]]))


show('Parser', 0x11829b0)
show('Question', 0x1177768)
show('PrepQ', 0x11776e8)
