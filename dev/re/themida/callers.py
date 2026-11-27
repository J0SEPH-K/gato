"""Find direct call sites of the parser's 0x110-stride vector helpers."""
import pe
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

d = pe.d
IB = pe.IB
md = Cs(CS_ARCH_X86, CS_MODE_64)

TARGETS = {0x973760: 'at_index', 0x9737a0: 'count', 0x973720: 'ctor', 0x9736e0: 'dtor'}

text_lo = pe.r2o(0x1000) or 0
text_hi = (pe.r2o(0xa38000 - 1) or len(d) - 1) + 1
code = d[text_lo:text_hi]

hits = {k: [] for k in TARGETS}
for ins in md.disasm(code, IB + 0x1000):
    if ins.mnemonic != 'call' or not ins.op_str.startswith('0x'):
        continue
    t = int(ins.op_str, 16) - IB
    if t in TARGETS:
        hits[t].append(ins.address - IB)

for t, name in TARGETS.items():
    print('%s 0x%x callers %d: %s' % (name, t, len(hits[t]), [hex(x) for x in hits[t][:20]]))
