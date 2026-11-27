"""Correct PE section map for unpacked_live.exe (names are blanked to spaces)."""
import struct

PATH = 'unpacked_live.exe'
_d = open(PATH, 'rb').read()
_pe = struct.unpack_from('<I', _d, 0x3c)[0]
_ns = struct.unpack_from('<H', _d, _pe + 6)[0]
_soh = struct.unpack_from('<H', _d, _pe + 20)[0]
_opt = _pe + 24
IB = struct.unpack_from('<Q', _d, _opt + 24)[0]
_st = _opt + _soh

SECS = []
for _i in range(_ns):
    _o = _st + 40 * _i
    _vs, _va, _rs, _rp = struct.unpack_from('<4I', _d, _o + 8)
    _ch = struct.unpack_from('<I', _d, _o + 36)[0]
    SECS.append((_va, _vs, _rp, _rs, _ch))

d = _d


def o2r(off):
    for va, vs, rp, rs, ch in SECS:
        if rp and rp <= off < rp + rs:
            return va + off - rp
    return None


def r2o(rva):
    for va, vs, rp, rs, ch in SECS:
        if va <= rva < va + max(vs, rs):
            return rp + rva - va
    return None


def q(off):
    return struct.unpack_from('<Q', d, off)[0]


def cstr(off, lim=256):
    e = d.find(b'\0', off, off + lim)
    return d[off:e] if e > 0 else b''


def dump_sections():
    for i, (va, vs, rp, rs, ch) in enumerate(SECS):
        print(f'{i:2d} va=0x{va:08x} vs=0x{vs:08x} rp=0x{rp:08x} rs=0x{rs:08x} ch=0x{ch:08x}')
