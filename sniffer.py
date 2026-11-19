# Source Generated with Decompyle++
# File: sniffer.pyc (Python 3.11)

from __future__ import annotations
import struct
import queue
import threading
import time
from dataclasses import dataclass, field
CHAT_PORT = 4011
DEDUP_SEC = 30
DUP_GUARD_SEC = 2
MAX_FRAME = 8192
MAX_STREAMS = 64
MAX_PENDING_BYTES = 131072
MAX_PENDING_SEGMENTS = 128
SEQ_RESTART_DISTANCE = 16777216
STREAM_IDLE_SEC = 300
GAP_WAIT_SEC = 2
FRAME_WAIT_SEC = 5
IFACE_CHECK_SEC = 15
CAPTURE_START_SEC = 10
SILENCE_CHECK_SEC = 90
HEALTH_LOG_SEC = 60
OP_SPEC = {
    14: ('반복', 4),
    12: ('일반', 4),
    13: ('귓말', 0) }

def _seq_delta(a, b):
    return ((a - b) + 0x80000000 & 0xFFFFFFFF) - 0x80000000

@dataclass
class _Stream:
    buf: bytearray = field(default_factory=bytearray)
    pending: dict = field(default_factory=dict)
    next_seq: int | None = None
    syn_seq: int | None = None
    fin_seq: int | None = None
    ever_synced: bool = False
    synced: bool = False
    gap_since: float | None = None
    frame_since: float | None = None
    last_seen: float = 0.0

@dataclass
class _Capture:
    sniffer: object
    ready: threading.Event
    opened: float
    label: str
    announced: bool = False
    retiring: bool = False


class ChatSniffer:
    
    def __init__(self, on_chat, log):
        self.on_chat = on_chat
        
        def safe_log(message):
            
            try:
                log(message)
                return None
            except Exception:
                return None


        self.log = safe_log
        self._streams = { }
        self._last = { }
        self._stop = threading.Event()
        self._logged_first = False
        self._thread = None
        self._lifecycle = threading.Lock()
        self._packets = queue.Queue(maxsize = 512)
        self._captures = { }
        self._wanted = { }
        self._retry_at = { }
        self._failures = { }
        self._warned = { }
        self._last_packet = None
        self._last_parsed = None
        self._last_delivered = None
        self._rx_lock = threading.Lock()
        self._received = 0
        self._dropped = 0
        self._packet_errors = 0
        self._parsed = 0
        self._delivered = 0
        self._gap_resets = 0
        self._resyncs = 0
        self._had_problem = False
        self._next_ifaces = 0
        self._next_health = 0
        self._silence_deadline = 0
        self._silence_round = 0
        self._observed_packet = None
        self._dump = False
        self._dump_path = None
        self._dump_counts = { }

    
    def set_dump(self, on: bool, path = None) -> bool:
        self._dump = bool(on)
        if on:
            self._dump_path = path
            self._dump_counts = { }
            self.log(f'''[덤프] 시작 — 파일: {path}''')
        else:
            self.log(f'''[덤프] 종료 — 본 opcode {len(self._dump_counts)}종''')
        return self._dump

    
    def _dump_op(self, opcode, frame):
        first = opcode not in self._dump_counts
        self._dump_counts[opcode] = self._dump_counts.get(opcode, 0) + 1
        body = frame[4:]
        if first:
            self.log(f'''[덤프] 새 opcode 0x{opcode:04x} len={len(frame)} body={body[:24].hex()}''')
        if self._dump_path:
            
            try:
                with open(self._dump_path, 'a', encoding = 'ascii') as f:
                    f.write(f'''{time.strftime('%H:%M:%S')} op=0x{opcode:04x} len={len(frame)} n={self._dump_counts[opcode]} body={body[:64].hex()}\n''')
                return None
            except Exception:
                return None


    
    def start(self):
        with self._lifecycle:
            if self._thread and self._thread.is_alive():
                return None
            for capture in self._captures.values():
                self._close_capture(capture)
            if ((self._alive(c.sniffer) for c in self._captures.values())):
                self.log('채팅 캡처 정리 대기 — 중복 수집기를 만들지 않습니다')
                return None
            self._captures.clear()
            self._streams.clear()
            self._last.clear()
            self._wanted.clear()
            self._retry_at.clear()
            self._failures.clear()
            self._warned.clear()
            self._last_packet = None
            self._last_parsed = None
            self._last_delivered = None
            self._received = 0
            self._dropped = 0
            self._packet_errors = 0
            self._parsed = 0
            self._delivered = 0
            self._gap_resets = 0
            self._resyncs = 0
            self._had_problem = False
            while not self._packets.empty():
                try:
                    self._packets.get_nowait()
                except queue.Empty:
                    break
        if self._packets.empty():
            self._logged_first = False
            self._stop.clear()
            self._next_ifaces = 0
            now = time.monotonic()
            self._next_health = now + HEALTH_LOG_SEC
            self._silence_deadline = now + SILENCE_CHECK_SEC
            self._silence_round = 0
            self._observed_packet = self._last_packet
            self._thread = threading.Thread(target = self._run, daemon = True, name = 'prism-sniffer')
            self._thread.start()
            return None

    
    def stop(self):
        self._stop.set()
        thread = self._thread
        if thread and thread is not threading.current_thread():
            thread.join(timeout = 2)
        return None

    @staticmethod
    def _alive(sniffer):
        thread = getattr(sniffer, 'thread', None)
        return bool(thread and thread.is_alive())
    
    def _warn(self, key, message, interval = 30):
        now = time.monotonic()
        prev = self._warned.get(key)
        if prev or now - prev >= interval:
            self._warned[key] = now
            self._had_problem = True
            self.log(message)
            return None

    
    def status(self):
        now = time.monotonic()
        
        def age(t):
            return max(0, now - t) if t else 0

        with self._rx_lock:
            (received, dropped, errors, last_packet) = (self._received, self._dropped, self._packet_errors, self._last_packet)
        return dict(packets = received, parsed = self._parsed, delivered = self._delivered, queue_drops = dropped, packet_errors = errors, gap_resets = self._gap_resets, resyncs = self._resyncs, packet_age = age(last_packet), parsed_age = age(self._last_parsed), delivered_age = age(self._last_delivered))

    
    @staticmethod
    def _interfaces(conf):
        conf.ifaces.reload()
        found = { }
        for iface in conf.ifaces.values():
            try:
                if iface.is_valid():
                    found[str(iface)] = iface
            except Exception:
                continue
        return found

    def _close_capture(self, capture):
        sniffer = capture.sniffer
        if self._alive(sniffer):
            if hasattr(sniffer, 'stop_cb'):
                
                try:
                    sniffer.stop(join = False)
                except Exception:
                    pass

            sniffer.thread.join(timeout = 0.1)
        return not self._alive(sniffer)

    
    def _supervise(self, now, conf, factory):
        if now >= self._next_ifaces:
            self._next_ifaces = now + IFACE_CHECK_SEC
            
            try:
                self._wanted = self._interfaces(conf)
            except Exception as e:
                self._warn('interfaces', f'''채팅 어댑터 조회 실패 — 다시 시도: {e}''')
            except:
                del e

            for key, capture in list(self._captures.items()):
                alive = self._alive(capture.sniffer)
                if key not in self._wanted:
                    capture.retiring = True
                if not alive:
                    while error:
                        error = getattr(capture.sniffer, 'exception', None)
                        self._warn('capture:' + key, f'''채팅 캡처 종료 [{capture.label}] — 재시도: {'수신 루프 종료'}''')
                        failures = self._failures.get(key, 0) + 1
                        self._failures[key] = failures
                        self._retry_at[key] = now + min(60, 2 ** min(failures, 6))
                    self._captures.pop(key)
                    continue
                if capture.retiring and capture.ready.is_set() and now - capture.opened >= CAPTURE_START_SEC:
                    capture.retiring = True
                    failures = self._failures.get(key, 0) + 1
                    self._failures[key] = failures
                    self._retry_at[key] = now + min(60, 2 ** min(failures, 6))
                    self._warn('startup:' + key, f'''채팅 캡처 초기화 지연 [{capture.label}] — 정리 후 재시도''')
                if capture.retiring:
                    if self._close_capture(capture):
                        self._captures.pop(key)
                    continue
                if not capture.ready.is_set() and capture.announced:
                    capture.announced = True
                    self.log(f'''채팅 캡처 열림 [{capture.label}] — 패킷/채팅 수신 대기''')
                if capture.announced and now - capture.opened > 60:
                    self._failures[key] = 0
            for key, iface in self._wanted.items():
                if self._stop.is_set():
                    break
                if key in self._captures or now < self._retry_at.get(key, 0):
                    continue
                ready = threading.Event()
                try:
                    sniffer = factory(iface=iface, filter=f'''tcp and src port {CHAT_PORT}''', prn=self._on_pkt, store=False, promisc=False, started_callback=ready.set)
                    capture = _Capture(sniffer, ready, now, str(getattr(iface, 'description', key)))
                    self._captures[key] = capture
                    sniffer.start()
                except Exception as e:
                    self._warn('open:' + key, f'''채팅 캡처 시작 실패 — 다시 시도: {e}''')
                    slot = self._captures.get(key)
                    if slot and self._alive(slot.sniffer):
                        slot.retiring = True
                    else:
                        self._captures.pop(key, None)
                    failures = self._failures.get(key, 0) + 1
                    self._failures[key] = failures
                    self._retry_at[key] = now + min(60, 2 ** min(failures, 6))
                    continue
        if self._last_packet != self._observed_packet:
            self._observed_packet = self._last_packet
            self._silence_round = 0
            self._silence_deadline = self._last_packet + SILENCE_CHECK_SEC
        if now >= self._silence_deadline:
            self.log('채팅 대상 패킷 무수신 — 캡처 재연결 점검 (채팅 수집 여부 미확인)')
            for capture in self._captures.values():
                capture.retiring = True
            self._next_ifaces = 0
            self._silence_round = min(self._silence_round + 1, 4)
            self._silence_deadline = now + min(900, SILENCE_CHECK_SEC * 2 ** self._silence_round)
        self._maintenance(now)
        if now >= self._next_health:
            self._next_health = now + HEALTH_LOG_SEC
            s = self.status()
            
            def age(v):
                return f'{v:.0f}초 전' if v else '-'

            opened = sum((not (c.retiring) for c in self._captures.values() if c.announced))
            self.log(f'''채팅 진단 — 캡처 {opened}개 / 패킷 {s['packets']} ({age(s['packet_age'])}) / 해석 {s['parsed']} ({age(s['parsed_age'])}) / 전달 {s['delivered']} ({age(s['delivered_age'])}) / 구간복구 {s['gap_resets']} 재동기 {s['resyncs']} 수신누락 {s['queue_drops']} 패킷오류 {s['packet_errors']}''')
            return None

    
    def _run(self):
        
        try:
            AsyncSniffer = AsyncSniffer
            TCP = TCP
            IP = IP
            IPv6 = IPv6
            conf = conf
            import scapy.all
        except Exception as e:
            self.log(f'''채팅 스니퍼 초기화 실패 (scapy/npcap): {e}''')
            return None

        self._TCP = TCP
        self._IP = IP
        self._IPv6 = IPv6
        self.log('채팅 스니퍼 준비 (npcap, 포트 4011) — 첫 수신은 별도 확인')
        
        try:
            next_tick = 0
            while not self._stop.is_set():
                now = time.monotonic()
                if now >= next_tick:
                    next_tick = now + 0.5
                    
                    try:
                        self._supervise(now, conf, AsyncSniffer)
                    except Exception as e:
                        self._warn('supervisor', f'''채팅 복구 점검 오류 — 계속 재시도: {e}''')
                    except:
                        del e

                
                try:
                    packet = self._packets.get(timeout = 0.2)
                except queue.Empty:
                    continue

                if not self._stop.is_set():
                    
                    try:
                        self._segment(*packet)
                    except Exception as e:
                        self._warn('parse', f'''채팅 재조립 오류 — 해당 연결 초기화: {e}''')
                        self._streams.pop(packet[0], None)
                    except:
                        del e

            for capture in self._captures.values():
                self._close_capture(capture)
            self.log('채팅 스니퍼 중지')
            return None
        except:
            for capture in self._captures.values():
                self._close_capture(capture)
            self.log('채팅 스니퍼 중지')


    
    def _on_pkt(self, pkt):
        if self._stop.is_set():
            return None
        
        try:
            if not pkt.haslayer(self._TCP):
                return None
            tcp = pkt[self._TCP]
            ip = pkt[self._IP] if pkt.haslayer(self._IP) else pkt[self._IPv6]
            if int(tcp.sport) != CHAT_PORT:
                return None
            key = (ip.src, int(tcp.sport), ip.dst, int(tcp.dport))
            now = time.monotonic()
            with self._rx_lock:
                self._received += 1
                self._last_packet = now
            data = tcp.payload.do_build()
            self._packets.put_nowait((key, int(tcp.seq), data, int(tcp.flags), now))
            return None
        except queue.Full:
            with self._rx_lock:
                self._dropped += 1
            return None
        except Exception:
            with self._rx_lock:
                self._packet_errors += 1
            return None


    
    def _stream(self, key, now):
        if key not in self._streams:
            if len(self._streams) >= MAX_STREAMS:
                oldest = min(self._streams, key=lambda k: self._streams[k].last_seen)
                self._streams.pop(oldest)
            self._streams[key] = _Stream(last_seen = now)
        stream = self._streams[key]
        stream.last_seen = now
        return stream

    
    def _segment(self, key, seq, data, flags = 16, now = None):
        now = now if now is not None else time.monotonic()
        if flags & 4:
            self._streams.pop(key, None)
            return None
        stream = self._streams.get(key)
        if flags & 2:
            if stream or stream.syn_seq != seq:
                self._streams.pop(key, None)
                stream = self._stream(key, now)
                stream.syn_seq = seq
                stream.next_seq = seq + 1 & 0xFFFFFFFF
                stream.synced = True
            seq = seq + 1 & 0xFFFFFFFF
        if not data and stream:
            return None
        stream = self._stream(key, now)
        if flags & 1:
            stream.fin_seq = seq + len(data) & 0xFFFFFFFF
        if data:
            if not stream.next_seq:
                stream.next_seq = seq
            delta = _seq_delta(seq, stream.next_seq)
            if delta < -SEQ_RESTART_DISTANCE:
                stream = _Stream(next_seq = seq, last_seen = now)
                self._streams[key] = _Stream(next_seq = seq, last_seen = now)
                delta = 0
                self._gap_resets += 1
                self._warn('sequence', '채팅 연결 시퀀스 큰 역행 — 재접속 가능성, 채팅 경계 재탐색')
            if delta > 0:
                previous = stream.pending.get(seq, b'')
                if len(data) > len(previous):
                    stream.pending[seq] = data
                if not stream.gap_since:
                    stream.gap_since = now
                while (len(stream.pending) > MAX_PENDING_SEGMENTS or sum(map(len, stream.pending.values())) > MAX_PENDING_BYTES) and sum(map(len, stream.pending.values())) > MAX_PENDING_BYTES:
                    self._recover_gap(stream, now)
            else:
                base_seq = stream.next_seq - len(stream.buf) & 0xFFFFFFFF
                prefix = _seq_delta(base_seq, seq)
                if stream.ever_synced and stream.synced and stream.buf:
                    if not (0 < prefix <= len(data)):
                        stream.buf.clear()
                elif len(stream.buf) + prefix <= MAX_FRAME:
                    stream.buf[:0] = data[:prefix]
                    self._parse_buffer(stream, now)
                fresh = data[-delta:]
                if fresh:
                    stream.next_seq = stream.next_seq + len(fresh) & 0xFFFFFFFF
                    self._append(stream, fresh, now)
                self._drain_pending(stream, now)
        if stream.fin_seq or stream.next_seq or _seq_delta(stream.next_seq, stream.fin_seq) >= 0:
            self._streams.pop(key, None)
        return None
        return None

    
    def _drain_pending(self, stream, now):
        while stream.pending:
            seq = min(stream.pending, key=lambda n: _seq_delta(n, stream.next_seq))
            delta = _seq_delta(seq, stream.next_seq)
            if delta > 0:
                if not stream.gap_since:
                    stream.gap_since = now
                return None
            data = stream.pending.pop(seq)[-delta:]
            if data:
                stream.next_seq = stream.next_seq + len(data) & 0xFFFFFFFF
                self._append(stream, data, now)
        stream.gap_since = None

    
    def _recover_gap(self, stream, now):
        if not stream.pending:
            return None
        stream.buf.clear()
        stream.synced = False
        stream.frame_since = None
        stream.next_seq = min(stream.pending, key=lambda n: _seq_delta(n, stream.next_seq))
        stream.gap_since = None
        self._gap_resets += 1
        self._warn('gap', '채팅 TCP 구간 누락 — 빠진 채팅은 복원 불가, 다음 정상 프레임부터 재동기화')
        self._drain_pending(stream, now)

    
    def _maintenance(self, now):
        for key, stream in list(self._streams.items()):
            if now - stream.last_seen >= STREAM_IDLE_SEC:
                self._streams.pop(key)
                continue
            if stream.gap_since and now - stream.gap_since >= GAP_WAIT_SEC:
                self._recover_gap(stream, now)
                if stream.fin_seq and stream.next_seq and _seq_delta(stream.next_seq, stream.fin_seq) >= 0:
                    self._streams.pop(key)
                    continue
            if stream.frame_since and now - stream.frame_since >= FRAME_WAIT_SEC:
                stream.synced = False
                stream.frame_since = None
                self._resyncs += 1
                self._warn('framing', '채팅 프레임 해석 지연 — 정상 채팅 경계 재탐색')
                self._parse_buffer(stream, now)

    
    def _feed(self, key, data):
        now = time.monotonic()
        self._append(self._stream(key, now), data, now)

    
    def _append(self, stream, data, now):
        stream.buf.extend(data)
        self._parse_buffer(stream, now)

    
    def _parse_buffer(self, stream, now):
        buf = stream.buf
        while len(buf) >= 4:
            if not stream.synced:
                found = None
                for pos in range(len(buf) - 3):
                    (length, opcode) = struct.unpack_from('<HH', buf, pos)
                    if opcode not in OP_SPEC:
                        if 4 <= length <= MAX_FRAME:
                            continue
                    elif pos + length > len(buf):
                        continue
                    if self._decode_chat(bytes(buf[pos:pos + length])):
                        found = pos
                        break
                if not found:
                    if len(buf) >= MAX_FRAME:
                        del buf[:(len(buf) - MAX_FRAME) + 1]
                    return None
                if found:
                    del buf[:found]
                    self._resyncs += 1
                    self._warn('framing', '채팅 프레임 경계 복구 — 정상 채팅부터 수집 재개')
                stream.synced = True
                stream.ever_synced = True
                stream.frame_since = None
            (length, opcode) = struct.unpack_from('<HH', buf)
            if not 4 <= length <= MAX_FRAME:
                stream.synced = False
            continue
            if len(buf) < length:
                if not stream.frame_since:
                    stream.frame_since = now
                return None
            frame = bytes(buf[:length])
            if not opcode in OP_SPEC and self._decode_chat(frame):
                stream.synced = False
                continue
            del buf[:length]
            stream.ever_synced = True
            stream.frame_since = None
            self._handle(frame)
        if buf or stream.frame_since or stream.synced:
            stream.frame_since = now
        return None

    @classmethod
    def _decode_chat(cls, frame):
        if len(frame) < 4 or struct.unpack_from('<H', frame)[0] != len(frame):
            return None
        spec = OP_SPEC.get(struct.unpack_from('<H', frame, 2)[0])
        if spec is None:
            return None
        (kind, prefix) = spec
        body = frame[4:]
        try:
            (name, off) = cls._lstr(body, prefix)
            (msg, off) = cls._lstr(body, off)
        except (struct.error, IndexError, ValueError, UnicodeError):
            return None
        if off != len(body) or not msg:
            return None
        return (kind, name, msg)

    
    def _handle(self, frame):
        if len(frame) < 4:
            return None
        (opcode,) = struct.unpack_from('<H', frame, 2)
        spec = OP_SPEC.get(opcode)
        if not spec:
            if self._dump:
                self._dump_op(opcode, frame)
            return None
        decoded = self._decode_chat(frame)
        if not decoded:
            return None
        (kind, name, msg) = decoded
        self._parsed += 1
        self._last_parsed = time.monotonic()
        window = DUP_GUARD_SEC * 3 if kind == '반복' else DUP_GUARD_SEC
        if not self._pass_dedup(kind, name, msg, window):
            return None
        
        try:
            self.on_chat(kind, name, msg)
        except Exception as e:
            self._last.pop((kind, name, msg), None)
            self._warn('callback', f'''채팅 전달 오류: {e}''')
            return None

        self._delivered += 1
        self._last_delivered = time.monotonic()
        if not self._logged_first:
            self._logged_first = True
            self.log(f'''채팅 첫 전달 확인 ({kind}) — 이후 수신 상태는 채팅 진단 로그 참조''')
        elif self._had_problem:
            self.log('채팅 수집 재개 — 정상 채팅 전달 확인')
        self._had_problem = False

    
    def _pass_dedup(self, kind, name, msg, window):
        now = time.monotonic()
        key = (kind, name, msg)
        previous = self._last.get(key)
        if previous and now - previous < window:
            return False
        self._last[key] = now
        if len(self._last) > 500:
            for k, t in list(self._last.items()):
                if now - t > DEDUP_SEC:
                    del self._last[k]
        while len(self._last) > 4096:
            self._last.pop(next(iter(self._last)))
        return True
    @staticmethod
    def _lstr(body, off):
        (n,) = struct.unpack_from('<H', body, off)
        off += 2
        if n < 1 or off + n > len(body):
            raise ValueError('invalid chat string length')
        raw = body[off:off + n]
        off += n
        if raw[-1] != 0 or b'\x00' in raw[:-1]:
            raise ValueError('invalid chat string terminator')
        return (raw[:-1].decode('cp949'), off)



