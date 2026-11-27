"""Disassemble the full-VA vftables of the jochel classes."""
import struct
import pe
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

d = pe.d
IB = pe.IB
md = Cs(CS_ARCH_X86, CS_MODE_64)

SITES = {
    'CSecretInspector_Parser': 0xb63808,
    'CQuestionState': 0xb32e80,
    'CPrepareQuestionState': 0xb32e50,
    'ContentSecretInspector': 0xb16ef8,
}


def info(fn_rva, maxins=45):
    fo = pe.r2o(fn_rva)
    if fo is None:
        return None
    ins = list(md.disasm(d[fo:fo + 500], IB + fn_rva))[:maxins]
    calls, strs, imms = [], [], []
    for x in ins:
        if x.mnemonic == 'call' and x.op_str.startswith('0x'):
            calls.append(int(x.op_str, 16) - IB)
        if 'rip +' in x.op_str:
            try:
                disp = x.op_str.split('rip +')[1].split(']')[0].strip()
                t = x.address + x.size + int(disp, 16) - IB
                ro = pe.r2o(t)
                s = pe.cstr(ro, 90) if ro else b''
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
    return len(ins), calls, imms, strs


for label, site in SITES.items():
    o = pe.r2o(site)
    print('\n##### %s site=0x%x' % (label, site))
    for i in range(1, 30):
        va = struct.unpack_from('<Q', d, o + 8 * i)[0]
        if not (IB <= va < IB + 0x1400000):
            print('  [%d] non-code 0x%x' % (i - 1, va))
            break
        r = va - IB
        got = info(r)
        if got is None:
            print('  [%d] rva=0x%x OUTSIDE' % (i - 1, r))
            continue
        n, calls, imms, strs = got
        print('  [%d] rva=0x%x n=%d calls=%s imm=%s strs=%s'
              % (i - 1, r, n, [hex(c) for c in calls[:8]],
                 [hex(v) for v in imms[:8]], strs[:3]))
