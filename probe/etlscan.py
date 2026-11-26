"""Heuristic port-8000 frame extractor for a pktmon .etl blob.

pktmon ETL is not pcap and nothing on macOS parses it, but the records are
mostly 0xff padding with the captured bytes in scattered runs. Gersang frames
are little-endian u16 length + u16 opcode (same shape sniffer._parse_buffer
uses on 4011), so a chain of consecutive well-formed frames is a strong
signal. No chain is trusted below MIN_CHAIN frames.
"""
import struct
import sys
import collections

MINF = 4
MAXF = 8192
MAXOP = 0x800


def chains(d, min_chain=4):
    n = len(d)
    out = []
    i = 0
    while i < n - 4:
        j = i
        fr = []
        while j < n - 4:
            ln, op = struct.unpack_from('<HH', d, j)
            if not (MINF <= ln <= MAXF) or op == 0 or op > MAXOP:
                break
            if j + ln > n:
                break
            fr.append((j, ln, op, bytes(d[j:j + ln])))
            j += ln
        if len(fr) >= min_chain:
            out.append(fr)
            i = j
        else:
            i += 1
    return out


def main():
    path = sys.argv[1]
    min_chain = int(sys.argv[2]) if len(sys.argv) > 2 else 4
    d = open(path, 'rb').read()
    print('bytes', len(d))
    cs = chains(d, min_chain)
    print('chains', len(cs), 'frames', sum(len(c) for c in cs))
    hist = collections.Counter()
    for c in cs:
        for _o, _l, op, _b in c:
            hist[op] += 1
    print('opcodes', [(hex(k), v) for k, v in hist.most_common(25)])
    for c in cs[:12]:
        print('--- chain at', hex(c[0][0]), 'frames', len(c))
        for off, ln, op, body in c[:10]:
            print('   ', hex(off), 'op=0x%04x' % op, 'len', ln, body[:48].hex())


if __name__ == '__main__':
    main()
