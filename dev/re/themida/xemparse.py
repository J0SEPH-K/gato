import struct, sys

def parse(p):
    d = open(p, 'rb').read()
    pe = struct.unpack_from('<I', d, 0x3c)[0]
    nsec = struct.unpack_from('<H', d, pe + 6)[0]
    opt = struct.unpack_from('<H', d, pe + 20)[0]
    ib = struct.unpack_from('<Q', d, pe + 24 + 24)[0]
    secs = []
    for i in range(nsec):
        o = pe + 24 + opt + 40 * i
        vs, va, rs, rp = struct.unpack_from('<4I', d, o + 8)
        secs.append((va, vs, rp, rs))

    def r2o(rva):
        for va, vs, rp, rs in secs:
            if rp and va <= rva < va + rs:
                return rp + (rva - va)
        return None

    dirs = {}
    for i, nm in [(0, 'export'), (1, 'import'), (2, 'resource'), (12, 'iat'), (13, 'delay')]:
        rva, sz = struct.unpack_from('<II', d, pe + 24 + 112 + 8 * i)
        dirs[nm] = (rva, sz)
    print('==', p, 'imagebase', hex(ib), 'dirs', {k: (hex(v[0]), v[1]) for k, v in dirs.items() if v[1]})

    o = r2o(dirs['export'][0]) if dirs['export'][1] else None
    if o:
        name, base, nf, nn, af, an, ao = struct.unpack_from('<7I', d, o)
        no = r2o(name)
        print(' dllname', d[no:d.index(b"\0", no)].decode())
        print(' export count', nf)
        fo = r2o(af)
        for i in range(min(nf, 60)):
            rva = struct.unpack_from('<I', d, fo + 4 * i)[0]
            nmo = r2o(struct.unpack_from('<I', d, r2o(ao) + 4 * i)[0])
            print('   %08x %s' % (rva, d[nmo:d.index(b"\0", nmo)].decode()))

    o = r2o(dirs['import'][0]) if dirs['import'][1] else None
    if o:
        p2 = o
        n = 0
        while True:
            oft, ts, fc, nm, ft = struct.unpack_from('<5I', d, p2)
            if not nm:
                break
            no = r2o(nm)
            print(' import', d[no:d.index(b"\0", no)].decode())
            n += 1
            p2 += 20
        print(' import dll count', n)

for f in sys.argv[1:]:
    try:
        parse(f)
    except Exception as e:
        print('ERR', f, type(e).__name__, e)
