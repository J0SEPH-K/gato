"""Deep-dive the CSecretInspector_Parser vtable entry (0x973720) and its callees."""
import struct
import pe
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

d = pe.d
IB = pe.IB
md = Cs(CS_ARCH_X86, CS_MODE_64)


seen = set()


def dis(rva, n=90, depth=0, tag=''):
    if rva in seen or depth > 2:
        return
    seen.add(rva)
    fo = pe.r2o(rva)
    if fo is None:
        print('%s 0x%x OUTSIDE' % ('  ' * depth, rva))
        return
    print('\n%s=== %s 0x%x (depth %d)' % ('  ' * depth, tag, rva, depth))
    ins = list(md.disasm(d[fo:fo + 700], IB + rva))[:n]
    calls = []
    for x in ins:
        line = '  %s 0x%x: %s %s' % ('  ' * depth, x.address - IB, x.mnemonic, x.op_str)
        if 'rip +' in x.op_str:
            try:
                disp = x.op_str.split('rip +')[1].split(']')[0].strip()
                t = x.address + x.size + int(disp, 16) - IB
                ro = pe.r2o(t)
                s = pe.cstr(ro, 90) if ro else b''
                if len(s) > 2 and all(32 <= c < 127 for c in s):
                    line += '   ; "%s"' % s.decode()
                else:
                    line += '   ; data 0x%x' % t
            except Exception:
                pass
        print(line)
        if x.mnemonic == 'call' and x.op_str.startswith('0x'):
            calls.append(int(x.op_str, 16) - IB)
    for c in calls:
        dis(c, 60, depth + 1, 'call')


dis(0x973720, 90, 0, 'Parser::slot0')
