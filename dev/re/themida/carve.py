#!/usr/bin/env python3
"""Carve the unpacked PE that Themida decrypted in memory and rebuild a loadable file.

Input : full memory dump of Gersang.exe
Output: rebuilt PE with section raw data restored and ImageBase patched back
        to the file's original base so the image maps where its RVAs expect.

Usage: carve.py <dump> <pe_offset> <out>
"""
import struct
import sys


def align(v, a):
    return (v + a - 1) // a * a


def main():
    dump, off, out = sys.argv[1], int(sys.argv[2], 0), sys.argv[3]
    d = open(dump, 'rb').read()
    if d[off:off + 2] != b'MZ':
        print('no MZ at %#x' % off)
        return 1
    lf = struct.unpack_from('<I', d, off + 0x3c)[0]
    pe = off + lf
    if d[pe:pe + 4] != b'PE\0\0':
        print('no PE sig')
        return 1
    nsec = struct.unpack_from('<H', d, pe + 6)[0]
    optsz = struct.unpack_from('<H', d, pe + 20)[0]
    opt = pe + 24
    magic = struct.unpack_from('<H', d, opt)[0]
    ep = struct.unpack_from('<I', d, opt + 16)[0]
    curbase = struct.unpack_from('<Q', d, opt + 24)[0]
    sizeimg = struct.unpack_from('<I', d, opt + 56)[0]
    sa = struct.unpack_from('<I', d, opt + 32)[0]
    fa = struct.unpack_from('<I', d, opt + 36)[0]
    print('magic %#x nsec %d ep %#x imagebase %#x sizeimg %#x secalign %#x filealign %#x'
          % (magic, nsec, ep, curbase, sizeimg, sa, fa))
    so = opt + optsz

    # read the in-memory section table and the live bytes for each section
    secs = []
    for i in range(nsec):
        o = so + 40 * i
        name = d[o:o + 8].rstrip(b'\0').decode('latin1')
        vs, va, rs, rp = struct.unpack_from('<4I', d, o + 8)
        body = d[off + va:off + va + vs]
        secs.append({'name': name, 'va': va, 'vs': vs, 'chars': struct.unpack_from('<I', d, o + 36)[0],
                     'body': body})

    hdr_size = align(so + 40 * nsec, fa)
    hdr = bytearray(d[off:off + hdr_size])

    # patch the optional header: base back to the module base, drop the pointer-to-raw-data
    # of every section (they carry no raw data) and zero the checksum.
    newbase = 0
    if magic == 0x20b:
        struct.pack_into('<Q', hdr, opt - off + 24, newbase)
        struct.pack_into('<I', hdr, opt - off + 64, 0)
    else:
        struct.pack_into('<I', hdr, opt - off + 28, newbase)
        struct.pack_into('<I', hdr, opt - off + 64, 0)

    body_out = bytearray(hdr)
    ptr = hdr_size
    table = []
    for s in secs:
        raw = align(len(s['body']), fa)
        struct.pack_into('<I', body_out, (so - off) + 40 * secs.index(s) + 16, len(s['body']))
        struct.pack_into('<I', body_out, (so - off) + 40 * secs.index(s) + 20, ptr)
        table.append((s['name'], s['va'], len(s['body']), ptr))
        body_out.extend(s['body'])
        body_out.extend(b'\0' * (raw - len(s['body'])))
        ptr += raw

    struct.pack_into('<I', body_out, opt - off + 56, sizeimg)
    open(out, 'wb').write(bytes(body_out))
    for n, va, rs, rp in table:
        print('  %-10s va %#x raw %#x size %#x' % (n, va, rp, rs))
    print('wrote %s (%d bytes)' % (out, len(body_out)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
