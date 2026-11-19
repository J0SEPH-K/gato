# Decompiled with PyLingual (https://pylingual.io)
# Internal filename: 'agf.py'
# Bytecode version: 3.11a7e (3495)
# Source timestamp: 2026-07-18 01:33:54 UTC (1784338434)

import struct
import zlib
import numpy as np
HDR_TABLE_A = 20
HDR_TABLE_B = 1220
DATA_START = 2416
def _decode_rle(seg, w, h, strict=True):
    img = np.zeros((h, w, 4), dtype=np.uint8)
    total = w * h
    pos = 0
    i = 0
    n = len(seg)
    while i + 4 <= n and pos < total:
            a0, r0, g0, b0 = (seg[i], seg[i + 1], seg[i + 2], seg[i + 3])
            if a0 == 0 and b0 == 0:
                pos += r0 | g0 << 8
            else:
                y, x = divmod(pos, w)
                img[y, x] = (b0, g0, r0, a0)
                pos += 1
            i += 4
    if strict and (pos != total or i != n):
        raise ValueError(f'RLE 정합 실패: pixels {pos}/{total}, bytes {i}/{n}')
    else:
        return img
class AgfFile:
    def __init__(self, path):
        self.path = path
        self.data = open(path, 'rb').read()
        self.magic, self.canvas_w, self.canvas_h, self.nframes = struct.unpack_from('<4I', self.data, 0)
        self.table_b = struct.unpack_from('<300I', self.data, HDR_TABLE_B)
        self.rects = [struct.unpack_from('<4H', self.data, DATA_START + i * 8) for i in range(self.nframes)]
        self.blocks_base = DATA_START + self.nframes * 8
        self.block = struct.unpack_from('<12I', self.data, self.blocks_base)
        self._stream = None
    @property
    def stream(self):
        if self._stream is None:
            comp_size = self.block[11]
            s = self.blocks_base + 48
            self._stream = zlib.decompress(self.data[s:s + comp_size])
        return self._stream
    def _bounds(self, i):
        start = 0 if i == 0 else self.table_b[i - 1]
        end = len(self.stream) if i == self.nframes - 1 else self.table_b[i]
        return (start, end)
    def frame(self, i):
        x, y, w, h = self.rects[i]
        if self.nframes == 1 and len(self.stream) == w * h * 4:
            raw = np.frombuffer(self.stream, dtype=np.uint8).reshape(h, w, 4)
            return raw[:, :, [3, 2, 1, 0]].copy()
        else:
            s, e = self._bounds(i)
            return _decode_rle(self.stream[s:e], w, h)
    def frames(self):
        return [self.frame(i) for i in range(self.nframes)]
    def frame_on_canvas(self, i):
        canvas = np.zeros((self.canvas_h, self.canvas_w, 4), dtype=np.uint8)
        x, y, w, h = self.rects[i]
        canvas[y:y + h, x:x + w] = self.frame(i)
        return canvas
if __name__ == '__main__':
    import sys
    p = sys.argv[1] if len(sys.argv) > 1 else 'C:\\AKInteractive\\Gersang\\Assets\\Textures\\UI\\StatusBars\\hpbar_small.AGF'
    f = AgfFile(p)
    print(f'{p}\n  canvas={f.canvas_w}x{f.canvas_h} frames={f.nframes}')
    for i in range(f.nframes):
        try:
            img = f.frame(i)
            op = int((img[:, :, 3] > 0).sum())
            print(f'  frame{i:02d} rect={f.rects[i]} opaque_px={op}')
        except Exception as e:
            print(f'  frame{i:02d}: FAIL {e}')