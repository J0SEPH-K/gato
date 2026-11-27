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
        return None

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
        per = {}
        for op, frame in frames:
            hit, total, pairs = per.get(op, (0, 0, []))
            pair = PktJochul._pair(frame)
            per[op] = (hit + (1 if pair else 0), total + 1, pairs + ([pair] if pair else []))
        cand = {op: v for op, v in per.items()
                if v[1] >= MIN_SWAPS and v[0] / v[1] >= MIN_PAIR_RATE}
        if not cand:
            top = sorted(per.items(), key=lambda kv: -kv[1][1])[:4]
            return None, 'no opcode carries pairs (' + ', '.join(
                f'{op:#06x}:{h}/{t}' for op, (h, t, _p) in top) + ')'
        if len(cand) > 1:
            # A real swap opcode moves DIFFERENT characters round after round, so its
            # decoded pairs are varied. A noise opcode that happens to carry in-range
            # bytes repeats the same pair every time. Rank on that, and abstain when
            # the top two are equally varied (mixing them would corrupt the order).
            ranked = sorted(cand.items(), key=lambda kv: -len(set(kv[1][2])))
            first_n = len(set(ranked[0][1][2]))
            if first_n > len(set(ranked[1][1][2])):
                op = ranked[0][0]
                return op, f'op={op:#06x} {cand[op][0]}/{cand[op][1]} distinct={first_n}'
            return None, 'ambiguous opcodes ' + ', '.join(
                f'{op:#06x}:{h}/{t}' for op, (h, t, _p) in sorted(cand.items()))
        op = next(iter(cand))
        return op, f'op={op:#06x} {cand[op][0]}/{cand[op][1]}'

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
        op, op_info = self.swap_opcode(frames)
        if op is None:
            return None, f'{len(frames)}f {cover * 100:.0f}% {endian} — {op_info}'
        pairs = [p for o, frame in frames if o == op for p in [self._pair(frame)] if p]
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
