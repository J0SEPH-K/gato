"""Answer 조철 from the port-8000 byte stream instead of from vision.

The server runs the shuffle, so the swap sequence and the final holder are in
the packets. This module records the main-socket frames of one round and
reconstructs the permutation from them; the answer is then a list index, not a
model score.

Framing is not assumed: chat on 4011 uses `u16 LE length | u16 LE opcode`, and
the main socket is expected to match, but both endiannesses are scored and the
one that actually tiles the stream wins. A wrong endianness scores ~0% coverage
because random u16 values almost never chain.

Opcode gating (1.0.43): the body layout is still undocumented, so treating every
frame as a possible swap lets unrelated opcodes inject phantom swaps and shift
the permutation to a confidently wrong answer. Instead the round's opcode
histogram is built and the ONE opcode whose frames reliably carry a swap pair is
used; zero or several candidates abstain rather than guess.

`solve` returns None (never a guess) when the stream did not decode into a
permutation that still contains the start slot.
"""
from __future__ import annotations

import os
import threading
import time
from collections import Counter

MAX_FRAME = 8192
MIN_FRAME = 4
RING_SEC = 40.0
DUP_MIN_BYTES = 24   # only payloads this big are checked for retransmission
ENDIANS = ('little', 'big')
MIN_PAIR_RATE = 0.80  # share of one opcode's frames that must decode to a pair
MIN_SWAPS = 3


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

    def dump(self, path: str) -> int:
        """Write the recorded segments to disk, one line per TCP payload.

        This is the ground truth for tuning the real frame layout: the decode is
        only as good as the bytes, and a round that abstains has to be replayable
        afterwards instead of guessed at. Returns bytes written.
        """
        segs = self.snapshot()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        n = 0
        with open(path, 'w', encoding='ascii') as f:
            for t, direction, payload in segs:
                f.write(f'{t:.3f} {direction} {len(payload)} {payload.hex()}\n')
                n += len(payload)
        return n

    def snapshot(self):
        with self._lock:
            return list(self._segs)

    # ---- decode side --------------------------------------------------
    @staticmethod
    def _tile(segs, endian, want='down'):
        buf = bytearray()
        for _t, direction, payload in segs:
            if direction == want:
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
    def _pair_at(frame, a, b):
        """Bytes at two fixed frame offsets read as a slot pair, or None."""
        if len(frame) <= b:
            return None
        x, y = frame[a], frame[b]
        if 1 <= x <= 5 and 1 <= y <= 5 and x != y:
            return (x, y)
        return None

    @staticmethod
    def _pair(frame):
        """The swap pair using the default layout, or None.

        The body layout is not documented. Live capture of the real server stream
        (1.0.46) shows the pair at frame offsets 8 and 11, i.e. body offsets 4 and 7:
        `len|sub|op|00 00|count|slotA .. slotB .. 00`. `_layout` re-derives the
        offsets from each round anyway; this is only the fallback.
        """
        return PktJochul._pair_at(frame, *PktJochul.DEFAULT_OFF)

    DEFAULT_OFF = (8, 11)
    MAX_OFF = 24
    MIN_LAYOUT_FRAMES = 3
    MIN_LAYOUT_RATE = 0.60

    @staticmethod
    def _layout(frames):
        """Best (opcode, offset_a, offset_b) for this round, or (None, why).

        Fixed offsets break the moment the server reorders a body, and the old
        "first two in-range bytes" reading happily matched a frame counter and
        answered the identity permutation. So scan every offset pair and keep the
        one that behaves like a swap column: present in most of that opcode's
        frames AND varied (a real column moves different characters round after
        round, a counter repeats). Two columns that score the same abstain.
        """
        per = {}
        for op, frame in frames:
            per.setdefault(op, []).append(frame)
        cand = []
        for op, group in per.items():
            if len(group) < PktJochul.MIN_LAYOUT_FRAMES:
                continue
            limit = min(PktJochul.MAX_OFF, min(len(f) for f in group))
            for a in range(4, limit):
                for b in range(a + 1, limit):
                    pairs = [p for p in (PktJochul._pair_at(f, a, b) for f in group) if p]
                    if len(pairs) < PktJochul.MIN_LAYOUT_FRAMES:
                        continue
                    if len(pairs) < PktJochul.MIN_LAYOUT_RATE * len(group):
                        continue
                    variety = len(set(pairs))
                    if variety < 3:
                        continue
                    # Byte "a" being in 1..5 is not proof it is a slot field — a fixed
                    # subtype/tag byte that happens to sit in that range reads as a
                    # constant "slot" on every frame. Checked against two independent
                    # field captures (2026-11-28, opcode 0xee00 off=4,7): offset 4 was
                    # the literal value 3 on all 155 combined swaps across BOTH a round
                    # that passed and one that didn't — the "varying" end (offset 7) was
                    # real, offset 4 never was. A real swap column must vary on both ends
                    # independently; requiring that here would abstain on both of those
                    # rounds, including the passed one, which is the correct call: a
                    # confident answer built on a constant byte is a coincidence, not a
                    # decode, even on the one round it happened to agree with the result.
                    # Replay of all three captured real rounds (BXBO-5): every surviving
                    # 0xee00 column had one side pinned to a single value - off 4 is the
                    # subtype (3 on 223/223 frames) and off 7 is the record count (frame
                    # length grows ~6 B per unit of it), so (4,7) and (7,10) were never swap
                    # data. A genuine column of only 3-4 swaps cannot always show 3 values on
                    # each side (e.g. (4,5),(1,4),(2,5)), so short columns need 2; the
                    # constant-side columns above have 1 and stay rejected either way.
                    need = 3 if len(pairs) >= 5 else 2
                    if len({p[0] for p in pairs}) < need or len({p[1] for p in pairs}) < need:
                        continue
                    cand.append(((variety, len(pairs), a, b), op, a, b, pairs, len(group)))
        if not cand:
            return None, 'no frame column carries a varying slot pair'
        # Deepest column wins a tie: the pair sits behind the count field, so a constant
        # byte early in the body (subtype/count) would otherwise shadow the real column.
        cand.sort(reverse=True)
        _key, op, a, b, pairs, total = cand[0]
        info = f'op={op:#06x} off={a},{b} {len(pairs)}/{total}'
        if len(cand) > 1 and cand[1][0][:2] == cand[0][0][:2] and cand[1][1] != op:
            other = cand[1]
            return None, info + f' — ambiguous with op={other[1]:#06x} off={other[2]},{other[3]}'
        return (op, a, b), info

    @staticmethod
    def _best_tiling(segs, want='down'):
        best = None
        for endian in ENDIANS:
            frames, cover = PktJochul._tile(segs, endian, want)
            key = (cover, len(frames))
            if best is None or key > best[0]:
                best = (key, endian, frames, cover)
        if best is None:
            return None, [], 0.0
        _key, endian, frames, cover = best
        return endian, frames, cover

    @staticmethod
    def swap_opcode(frames):
        """The single opcode that carries swap pairs, or (None, why).

        The real swap opcode is undocumented, so it is identified from the round
        itself: it must appear at least MIN_SWAPS times and MIN_PAIR_RATE of its
        frames must decode to a pair. Exactly one survivor is required - two
        plausible opcodes means the layout is ambiguous and mixing them would
        corrupt the permutation.
        """
        layout, info = PktJochul._layout(frames)
        if layout is None:
            return None, info
        return layout[0], info

    @staticmethod
    def _replay(pairs):
        order = [1, 2, 3, 4, 5]
        for a, b in pairs:
            if a not in order or b not in order:
                continue
            ia, ib = order.index(a), order.index(b)
            order[ia], order[ib] = order[ib], order[ia]
        return order

    def client_pick(self):
        """The slot the client itself sent up, when the up stream decodes one.

        Cross-check / log line only: the up direction also carries movement and
        chat, so this is the last single-byte 1..5 frame body found.
        """
        segs = self.snapshot()
        if not segs:
            return None
        _endian, frames, _cover = self._best_tiling(segs, 'up')
        pick = None
        for _op, frame in frames:
            tail = frame[4:]
            if len(tail) == 1 and 1 <= tail[0] <= 5:
                pick = tail[0]
        return pick

    def _decode(self):
        """(order, info) or (None, why) for the recorded round."""
        segs = self.snapshot()
        if not segs:
            return None, 'no main-port traffic recorded'
        endian, frames, cover = self._best_tiling(segs)
        if not frames:
            return None, 'no framing candidate'
        if cover < 0.30:
            return None, f'framing never tiled ({cover * 100:.0f}% {endian})'
        layout, op_info = self._layout(frames)
        if layout is None:
            return None, f'{len(frames)}f {cover * 100:.0f}% {endian} — {op_info}'
        op, a, b = layout
        pairs = [p for o, frame in frames if o == op for p in [self._pair_at(frame, a, b)] if p]
        info = (f'{len(frames)}f {cover * 100:.0f}% {endian} ops='
                f'{len(Counter(o for o, _f in frames))} {op_info} swaps={len(pairs)}')
        if len(pairs) < MIN_SWAPS:
            return None, info + ' — too few swaps'
        return self._replay(pairs), info

    def permutation(self):
        """(order, info) for the recorded round - the shuffle result itself."""
        return self._decode()

    def solve(self, first_slot: int):
        """Apply the recorded swap sequence to the start slot. (answer, info)."""
        order, info = self._decode()
        if order is None:
            return None, info
        if first_slot not in order:
            return None, info + f' — start slot {first_slot} left the permutation'
        return order.index(first_slot) + 1, info
