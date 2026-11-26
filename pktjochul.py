"""Answer 조철 from the port-8000 byte stream instead of from vision.

The server runs the shuffle, so the swap sequence and the final holder are in
the packets. This module records the main-socket frames of one round and
reconstructs the permutation from them; the answer is then a list index, not a
model score.

Framing is not assumed: chat on 4011 uses `u16 LE length | u16 LE opcode`, and
the main socket is expected to match, but both endiannesses are scored and the
one that actually tiles the stream wins. A wrong endianness scores ~0% coverage
because random u16 values almost never chain.

`solve` returns None (never a guess) when the stream did not decode into a
permutation that still contains the start slot.
"""
from __future__ import annotations

import threading
import time
from collections import Counter

MAX_FRAME = 8192
MIN_FRAME = 4
RING_SEC = 40.0
DUP_MIN_BYTES = 24   # only payloads this big are checked for retransmission
ENDIANS = ('little', 'big')


class PktJochul:
    """Rolling recorder for main-port traffic plus the shuffle decoder."""

    def __init__(self, log=lambda m: None):
        self.log = log
        self._lock = threading.Lock()
        self._segs: list[tuple[float, str, bytes]] = []
        self._on = False

    # ---- capture side -------------------------------------------------
    def begin(self):
        with self._lock:
            self._segs.clear()
            self._on = True

    def end(self):
        with self._lock:
            self._on = False

    @property
    def active(self) -> bool:
        return self._on

    def feed(self, direction: str, payload: bytes):
        """One TCP payload on the main socket. Called from the sniffer thread.

        A retransmitted segment carries the same bytes again; without this guard
        the swap frame would be counted twice and the permutation would flip to a
        confidently wrong answer. Only near-MSS payloads are compared, because a
        short payload can legitimately repeat back to back.
        """
        if not self._on or not payload:
            return
        now = time.monotonic()
        with self._lock:
            if len(payload) >= DUP_MIN_BYTES and self._segs:
                _t, prev_dir, prev = self._segs[-1]
                if prev_dir == direction and prev == payload and now - _t < 3.0:
                    return
            self._segs.append((now, direction, payload))
            if len(self._segs) > 20000:
                cutoff = now - RING_SEC
                self._segs = [s for s in self._segs if s[0] >= cutoff]

    def snapshot(self):
        with self._lock:
            return list(self._segs)

    # ---- decode side --------------------------------------------------
    @staticmethod
    def _tile(segs, endian):
        buf = bytearray()
        for _t, direction, payload in segs:
            if direction == 'down':
                buf.extend(payload)
        i, out = 0, []
        while i + MIN_FRAME <= len(buf):
            ln = int.from_bytes(buf[i:i + 2], endian)
            if MIN_FRAME <= ln <= MAX_FRAME and i + ln <= len(buf):
                op = int.from_bytes(buf[i + 2:i + 4], endian)
                out.append((op, bytes(buf[i:i + ln])))
                i += ln
            else:
                i += 1
        down = sum(len(p) for _t, d, p in segs if d == 'down')
        cover = sum(len(f) for _o, f in out) / down if down else 0.0
        return out, cover

    @staticmethod
    def _pair(frame):
        """The swap pair in one frame, or None.

        The exact body layout is not documented, so readings are tried in order
        and the first that yields exactly two distinct slot ids wins. The
        leading byte is skipped first because it is usually a frame subtype
        (0x01) and would otherwise read as slot 1.
        """
        tail = frame[4:]
        if len(tail) < 2:
            return None
        for cand in (tail[1:], tail):
            slots = [b for b in cand if 1 <= b <= 5]
            if len(slots) == 2 and slots[0] != slots[1]:
                return (slots[0], slots[1])
        a, b = tail[0], tail[1]
        if a != b and 1 <= a <= 5 and 1 <= b <= 5:
            return (a, b)
        return None

    @classmethod
    def _pairs(cls, frames):
        """Swap pairs in frame order."""
        out = []
        for _op, frame in frames:
            pair = cls._pair(frame)
            if pair:
                out.append(pair)
        return out

    def solve(self, first_slot: int):
        """Apply the recorded swap sequence to the start slot. (answer, info)."""
        segs = self.snapshot()
        if not segs:
            return None, 'no main-port traffic recorded'
        best = None
        for endian in ENDIANS:
            frames, cover = self._tile(segs, endian)
            key = (cover, len(frames))
            if best is None or key > best[0]:
                best = (key, endian, frames, cover)
        if best is None:
            return None, 'no framing candidate'
        _key, endian, frames, cover = best
        if cover < 0.30:
            return None, f'framing never tiled ({cover * 100:.0f}% {endian})'
        ops = Counter(op for op, _f in frames)
        pairs = self._pairs(frames)
        order = [1, 2, 3, 4, 5]
        for a, b in pairs:
            order[a - 1], order[b - 1] = order[b - 1], order[a - 1]
        info = (f'{len(frames)}f {cover * 100:.0f}% {endian} ops={len(ops)} '
                f'swaps={len(pairs)} seq={pairs[:20]}')
        if len(pairs) < 3:
            return None, info + ' — too few swaps'
        if first_slot not in order:
            return None, info + f' — start slot {first_slot} left the permutation'
        return order.index(first_slot) + 1, info
