#!/usr/bin/env python3
"""Analyze a memory dump: section entropy, PE sanity, unpack evidence."""
import collections, json, math, struct, sys


def ent(b):
    if not b:
        return 0.0
    c = collections.Counter(b)
    n = len(b)
    return -sum(v / n * math.log2(v / n) for v in c.values())


def main():
    man = json.load(open(sys.argv[1]))
    for m in man['modules']:
        p = m['file']
        d = open(p, 'rb').read()
        pe = struct.unpack_from('<I', d, 0x3c)[0]
        ok = d[pe:pe + 4] == b'PE\0\0'
        print('== %s size %d pe_ok %s' % (m['name'], len(d), ok))
        if not ok:
            continue
        ns = struct.unpack_from('<H', d, pe + 6)[0]
        optsz = struct.unpack_from('<H', d, pe + 20)[0]
        opt = pe + 24
        magic = struct.unpack_from('<H', d, opt)[0]
        ep = struct.unpack_from('<I', d, opt + 16)[0]
        ib = struct.unpack_from('<Q', d, opt + 24)[0] if magic == 0x20b else struct.unpack_from('<I', d, opt + 28)[0]
        print('   magic %#x nsec %d entry %#x imagebase %#x' % (magic, ns, ep, ib))
        so = pe + 24 + optsz
        for i in range(ns):
            o = so + 40 * i
            name = d[o:o + 8].rstrip(b'\0').decode('latin1')
            vs, va, rs, rp = struct.unpack_from('<4I', d, o + 8)
            body = d[va:va + vs]
            print('   %-10s va %08x vs %08x ent %5.2f' % (name, va, vs, ent(body)))
        print('   entry bytes: %s' % d[ep:ep + 24].hex())
        for kw in [b'xigncode', b'XIGNCODE', b'x3.xem', b'xcorona', b'xmag', b'xnina',
                   b'Gersang', b'AKInteractive', b'.text', b'Themida']:
            cnt = d.count(kw)
            if cnt:
                print('   str %-14r count %d first %#x' % (kw, cnt, d.find(kw)))
        print('   nonzero bytes %d / %d' % (sum(1 for b in d if b), len(d)))
        print()


if __name__ == '__main__':
    main()
