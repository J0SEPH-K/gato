import pe
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

d = pe.d
IB = pe.IB
md = Cs(CS_ARCH_X86, CS_MODE_64)

rva = 0x9737d0
fo = pe.r2o(rva)
print('=== 0x%x' % rva)
ins = list(md.disasm(d[fo:fo + 1600], IB + rva))[:240]
for x in ins:
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
