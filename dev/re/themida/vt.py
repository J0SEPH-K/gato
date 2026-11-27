"""Extract vftables (RVA-valued slots in this dump) and disassemble them."""
import struct
import pe
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

d = pe.d
IB = pe.IB
md = Cs(CS_ARCH_X86, CS_MODE_64)
md.detail = True


def vtable(rva, limit=40):
    o = pe.r2o(rva)
    if o is None:
        return []
    out = []
    for i in range(limit):
        v = struct.unpack_from('<Q', d, o + 8 * i)[0]
        if v == 0 or v >= 0x1400000:
            break
        out.append(v)
    return out


def show(label, rva, maxfn=40, maxins=60):
    fns = vtable(rva)
    print('\n##### %s vt=0x%x slots=%d' % (label, rva, len(fns)))
    for i, f in enumerate(fns[:maxfn]):
        fo = pe.r2o(f)
        if fo is None:
            continue
        code = d[fo:fo + 400]
        ins = list(md.disasm(code, IB + f))[:maxins]
        calls, imms, strs = [], [], []
        for x in ins:
            if x.mnemonic == 'call' and x.op_str.startswith('0x'):
                calls.append(int(x.op_str, 16) - IB)
            if x.mnemonic in ('mov', 'cmp', 'add', 'sub', 'imul', 'shl', 'sar'):
                for t in x.op_str.split(','):
                    t = t.strip()
                    if t.startswith('0x'):
                        try:
                            imms.append(int(t, 16))
                        except ValueError:
                            pass
            if 'rip +' in x.op_str:
                disp = x.op_str.split('rip +')[1].split(']')[0].strip()
                try:
                    tgt = x.address + x.size + int(disp, 16) - IB
                    ro = pe.r2o(tgt)
                    s = pe.cstr(ro) if ro else b''
                    if s and all(32 <= c < 127 for c in s[:40]):
                        strs.append(s.decode())
                except Exception:
                    pass
        print('  [%d] 0x%x n=%d calls=%s' % (i, f, len(ins), [hex(c) for c in calls[:6]]))
        if strs:
            print('      strs=%s' % strs[:4])
        small = [h for h in imms if 1 <= h <= 6]
        if small:
            print('      small_imm=%s' % small[:8])
        for x in ins[:14]:
            print('      %s %s' % (x.mnemonic, x.op_str))


show('CSecretInspector_Parser', 0x11829a4)
show('CQuestionState', 0x117775c)
