"""ContentSecretInspector round state machine: slots 3 (timers) and 20 (main)."""
import struct
import pe
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

d = pe.d
IB = pe.IB
md = Cs(CS_ARCH_X86, CS_MODE_64)

SITE = 0xb16ef8


def slots(n=30):
    o = pe.r2o(SITE)
    out = []
    for i in range(1, n):
        v = struct.unpack_from('<Q', d, o + 8 * i)[0]
        if not (IB <= v < IB + 0x1400000):
            break
        out.append(v - IB)
    return out


fs = slots()
print('slots', len(fs), [hex(x) for x in fs])

for idx in (3, 20, 2):
    if idx >= len(fs):
        continue
    rva = fs[idx]
    fo = pe.r2o(rva)
    print('\n===== slot %d rva=0x%x' % (idx, rva))
    for x in list(md.disasm(d[fo:fo + 900], IB + rva))[:110]:
        line = '0x%x: %s %s' % (x.address - IB, x.mnemonic, x.op_str)
        if 'rip +' in x.op_str:
            try:
                disp = x.op_str.split('rip +')[1].split(']')[0].strip()
                t = x.address + x.size + int(disp, 16) - IB
                ro = pe.r2o(t)
                s = pe.cstr(ro, 90) if ro else b''
                if len(s) > 2 and all(32 <= c < 127 for c in s):
                    line += '   ; "%s"' % s.decode()
                else:
                    line += '   ; 0x%x' % t
            except Exception:
                pass
        print(line)
