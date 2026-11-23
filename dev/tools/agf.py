"""Gersang .AGF sprite-sheet decoder (format from the community quickbms AGFTOTGA script, verified here by decoding
the real SecretInspector (조철) assets and eyeballing the output).

Layout (little endian):
  0x00  u32 magic 0x23, u32 max_w, u32 max_h, u32 frame_count
  0x4C0 frame_count x u32  offset of each frame inside the decompressed buffer (bytes)
  0x970 frame_count x (i16 x, i16 y, i16 w, i16 h)  placement of each frame on the max_w x max_h canvas
  0x970+8N      u32 decompressed size
  0x970+8N+16   u32 full_w, u32 full_h
  0x970+8N+0x2C u32 zlib_size, then a zlib stream
Pixels in the buffer are 4 bytes A,R,G,B. A pixel with A=0,G=0,B=0 is a run: R = number of fully transparent pixels.
"""
import struct, zlib
import numpy as np

def read(path):
    d = open(path, 'rb').read()
    magic, mw, mh, n = struct.unpack_from('<4I', d, 0)
    assert magic == 0x23, hex(magic)
    base = 0x970 + 8 * n
    usize = struct.unpack_from('<I', d, base)[0]
    fw, fh = struct.unpack_from('<2I', d, base + 16)
    zsize = struct.unpack_from('<I', d, base + 0x2C)[0]
    buf = zlib.decompress(d[base + 0x30: base + 0x30 + zsize])
    assert len(buf) == usize, (len(buf), usize)
    offs = list(struct.unpack_from('<%dI' % n, d, 0x4C0))
    offs.append(len(buf))
    frames = []
    for i in range(n):
        x, y, w, h = struct.unpack_from('<4h', d, 0x970 + 8 * i)
        a = np.frombuffer(buf[offs[i]:offs[i + 1]], np.uint8).reshape(-1, 4)  # A,R,G,B
        out = np.zeros((w * h, 4), np.uint8)   # RGBA
        pos = 0
        isrun = (a[:, 0] == 0) & (a[:, 2] == 0) & (a[:, 3] == 0)
        for k in range(len(a)):
            if pos >= w * h:
                break
            if isrun[k]:
                pos += int(a[k, 1])
            else:
                out[pos] = (a[k, 1], a[k, 2], a[k, 3], a[k, 0])
                pos += 1
        frames.append({'x': x, 'y': y, 'w': w, 'h': h, 'rgba': out.reshape(h, w, 4)})
    return {'max_w': mw, 'max_h': mh, 'frames': frames, 'full': (fw, fh)}

def canvas(sheet, i):
    """Frame i placed on the max_w x max_h canvas (RGBA)."""
    c = np.zeros((sheet['max_h'], sheet['max_w'], 4), np.uint8)
    f = sheet['frames'][i]
    y0, x0 = max(0, f['y']), max(0, f['x'])
    hh = min(f['h'], c.shape[0] - y0); ww = min(f['w'], c.shape[1] - x0)
    if hh > 0 and ww > 0:
        c[y0:y0 + hh, x0:x0 + ww] = f['rgba'][:hh, :ww]
    return c
