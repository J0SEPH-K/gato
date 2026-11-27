import struct
import pe

d = pe.d
IB = pe.IB

TARGETS = {
    'Parser': 0x11829a4,
    'Content': 0x1160aa4,
    'Question': 0x117775c,
    'PrepQ': 0x11776dc,
    'MiniGame': 0x117a14c,
}

for name, rva in TARGETS.items():
    va = IB + rva
    pk = struct.pack('<Q', va)
    hits = []
    k = d.find(pk)
    while k >= 0:
        if pe.o2r(k) is not None:
            hits.append(k)
        k = d.find(pk, k + 1)
    print(f'{name} vftable 0x{rva:x} qword refs {len(hits)}')
    for h in hits[:12]:
        print('   fileoff', hex(h), 'rva', hex(pe.o2r(h)))
