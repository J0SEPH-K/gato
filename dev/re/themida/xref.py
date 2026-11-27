"""Find code that references the SecretInspector strings/assets and disassemble around it."""
import struct
import pe
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

d = pe.d
IB = pe.IB
md = Cs(CS_ARCH_X86, CS_MODE_64)
TEXT_LO, TEXT_HI = 0x1000, 0xa38000

TARGETS = {
    'json': 0xb16f80 + (0xae5d08 - 0xae5cf0) + 0,   # placeholder, fixed below
}
# resolve real RVAs from known file offsets
for key, off in [('inspector_json', 0xb15980), ('assets', 0xb3e2f0), ('mapae', 0xb3e493),
                 ('secretfile', 0xae5cf0)]:
    TARGETS[key] = pe.o2r(off)
print('targets', {k: hex(v) for k, v in TARGETS.items()})

# scan .text for rip-relative lea/mov whose target is one of the strings
text_lo_off = pe.r2o(TEXT_LO) or 0
text_hi_off = (pe.r2o(TEXT_HI - 1) or len(d) - 1) + 1
code = d[text_lo_off:text_hi_off]
hits = []
for ins in md.disasm(code, IB + TEXT_LO):
    if 'rip +' not in ins.op_str:
        continue
    try:
        disp = ins.op_str.split('rip +')[1].split(']')[0].strip()
        tgt = ins.address + ins.size + int(disp, 16) - IB
    except Exception:
        continue
    for k, v in TARGETS.items():
        if v is not None and 0 <= v - tgt < 0x40:
            hits.append((k, ins.address - IB, tgt))
print('hits', len(hits))
for k, rva, tgt in hits[:40]:
    print('  %s at rva 0x%x -> 0x%x' % (k, rva, tgt))
