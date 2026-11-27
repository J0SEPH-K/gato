"""ContentSecretInspector slot 20 (main tick) + slot 2, and every writer of the +0x50 slot index."""
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
for idx in (20, 2, 1):
    if idx >= len(fs):
        continue
    rva = fs[idx]
    fo = pe.r2o(rva)
    print('\n===== slot %d rva=0x%x' % (idx, rva))
    for x in list(md.disasm(d[fo:fo + 1200], IB + rva))[:130]:
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

print('\n===== writers of word ptr [reg + 0x50] =====')
lo = pe.r2o(0x1277000) or 0
hi = (pe.r2o(0x13386fff) or len(d) - 1) + 1
hits = 0
for x in md.disasm(d[lo:hi], IB + 0x1277000):
    op = x.op_str
    if 'word ptr [' not in op:
        continue
    dst = op.split(',')[0]
    if '+ 0x50]' not in dst:
        continue
    hits += 1
    if hits <= 40:
        print('0x%x: %s %s' % (x.address - IB, x.mnemonic, op))
print('total', hits)
