# Read-only memory reader for Gersang.exe.
#
# The 조철 board is decided inside client memory: five 조철희 entities exist as objects
# carrying world X/Y, and exactly one of them has the 마패 attached. Vision has to guess
# through occlusion, the fire ring and a shuffle animation; memory does not. This module
# is the 100% route.
#
# Deliberately minimal anti-cheat surface: OpenProcess(PROCESS_VM_READ |
# PROCESS_QUERY_INFORMATION) and ReadProcessMemory only. No DebugActiveProcess, no
# hardware breakpoints, no kernel driver, so XIGNCODE sees a plain external reader and
# the game does not force-close (that is the thing to verify live, and `probe()` is how).
#
# probe() is the reversing step and runs before any of this is trusted: it finds the
# 조철희 name string in the target, then dumps the bytes around every hit plus any
# float pair that looks like a world coordinate, so the entity layout is read off real
# bytes instead of guessed.
import ctypes as C
import ctypes.wintypes as W
import json
import os
import struct
import time

try:
    C.WinDLL
except AttributeError:      # macOS: only for import-time sanity in dev tests
    class _StubDLL:
        def __getattr__(self, name):
            return lambda *a, **k: 0

    class _StubLib:
        def __getattr__(self, name):
            return _StubDLL()

    C.WinDLL = lambda *a, **k: _StubLib()
    C.get_last_error = lambda: 0

k32 = C.WinDLL('kernel32', use_last_error=True)

PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010

MEM_COMMIT = 0x1000
MEM_PRIVATE = 0x20000
MEM_MAPPED = 0x40000
MEM_IMAGE = 0x1000000
PAGE_GUARD = 0x100
PAGE_NOACCESS = 0x01
_READABLE = (0x02, 0x04, 0x08, 0x20, 0x40, 0x80)

MAX_ADDR = 0x7FFFFFFFFFFF
CHUNK = 0x400000          # 4 MB per ReadProcessMemory
OVERLAP = 64
SCAN_CAP = 0xC0000000     # stop after 3 GB scanned, keeps a probe bounded

k32.OpenProcess.restype = W.HANDLE
k32.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
k32.CloseHandle.argtypes = [W.HANDLE]
k32.ReadProcessMemory.restype = W.BOOL
k32.ReadProcessMemory.argtypes = [W.HANDLE, C.c_void_p, C.c_void_p, C.c_size_t,
                                  C.POINTER(C.c_size_t)]


class MBI(C.Structure):
    _fields_ = [('BaseAddress', C.c_void_p), ('AllocationBase', C.c_void_p),
                ('AllocationProtect', W.DWORD), ('PartitionId', W.WORD),
                ('RegionSize', C.c_size_t), ('State', W.DWORD),
                ('Protect', W.DWORD), ('Type', W.DWORD)]


k32.VirtualQueryEx.restype = C.c_size_t
k32.VirtualQueryEx.argtypes = [W.HANDLE, C.c_void_p, C.POINTER(MBI), C.c_size_t]


class _PE32(C.Structure):
    _fields_ = [('dwSize', W.DWORD), ('cntUsage', W.DWORD), ('th32ProcessID', W.DWORD),
                ('th32DefaultHeapID', C.c_void_p), ('th32ModuleID', W.DWORD),
                ('cntThreads', W.DWORD), ('th32ParentProcessID', W.DWORD),
                ('pcPriClassBase', C.c_long), ('dwFlags', W.DWORD),
                ('szExeFile', C.c_char * 260)]


k32.CreateToolhelp32Snapshot.restype = W.HANDLE
k32.CreateToolhelp32Snapshot.argtypes = [W.DWORD, W.DWORD]
k32.Process32First.restype = W.BOOL
k32.Process32First.argtypes = [W.HANDLE, C.POINTER(_PE32)]
k32.Process32Next.restype = W.BOOL
k32.Process32Next.argtypes = [W.HANDLE, C.POINTER(_PE32)]


def find_pid(name='Gersang.exe'):
    """PID by exe name, case-insensitively (psutil lowercases install paths)."""
    snap = k32.CreateToolhelp32Snapshot(0x2, 0)
    if snap in (0, -1, W.HANDLE(-1).value):
        return None
    try:
        e = _PE32()
        e.dwSize = C.sizeof(_PE32)
        ok = k32.Process32First(snap, C.byref(e))
        want = name.lower()
        while ok:
            if e.szExeFile.decode('latin1').lower() == want:
                return int(e.th32ProcessID)
            ok = k32.Process32Next(snap, C.byref(e))
        return None
    finally:
        k32.CloseHandle(snap)


def open_proc(pid):
    return k32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid)


def read(h, addr, size):
    buf = C.create_string_buffer(size)
    got = C.c_size_t(0)
    if not k32.ReadProcessMemory(h, C.c_void_p(addr), buf, size, C.byref(got)):
        return b''
    return buf.raw[:got.value]


def regions(h, want_private_only=False):
    """Yield (base, size, protect, type) for committed readable regions."""
    addr = 0
    mbi = MBI()
    while addr < MAX_ADDR:
        if not k32.VirtualQueryEx(h, C.c_void_p(addr), C.byref(mbi), C.sizeof(mbi)):
            break
        base = int(mbi.BaseAddress or 0)
        size = int(mbi.RegionSize or 0)
        if not size:
            break
        ok = (mbi.State == MEM_COMMIT and mbi.Protect in _READABLE
              and not (mbi.Protect & PAGE_GUARD) and mbi.Protect != PAGE_NOACCESS)
        if ok and (not want_private_only or mbi.Type == MEM_PRIVATE):
            yield base, size, int(mbi.Protect), int(mbi.Type)
        addr = base + size


def scan(h, needles, on_hit=None, cap=SCAN_CAP, want_private_only=False):
    """Scan committed readable memory for raw byte needles. Returns [(addr, needle_index)]."""
    hits = []
    scanned = 0
    for base, size, _prot, _typ in regions(h, want_private_only):
        off = 0
        while off < size:
            n = min(CHUNK, size - off)
            blob = read(h, base + off, n)
            if blob:
                for i, nd in enumerate(needles):
                    p = blob.find(nd)
                    while p >= 0:
                        a = base + off + p
                        hits.append((a, i))
                        if on_hit:
                            on_hit(a, i)
                        p = blob.find(nd, p + 1)
            scanned += n
            if scanned >= cap:
                return hits
            if n < CHUNK:
                break
            off += CHUNK - OVERLAP
    return hits


def hexdump(blob, base):
    out = []
    for i in range(0, len(blob), 16):
        row = blob[i:i + 16]
        txt = ''.join(chr(b) if 32 <= b < 127 else '.' for b in row)
        out.append('%016x  %-47s  %s' % (base + i, ' '.join('%02x' % b for b in row), txt))
    return '\n'.join(out)


def floats_near(h, addr, back=0x80, fwd=0x180):
    """Plausible world-coordinate float pairs around a hit (entity X/Y live near the name)."""
    blob = read(h, max(0, addr - back), back + fwd)
    base = max(0, addr - back)
    out = []
    for i in range(0, max(0, len(blob) - 8), 4):
        a, b = struct.unpack_from('<ff', blob, i)
        if -20000.0 < a < 20000.0 and -20000.0 < b < 20000.0 and (abs(a) > 1.0 or abs(b) > 1.0):
            out.append({'at': base + i, 'x': round(a, 3), 'y': round(b, 3)})
    return out[:24]


def probe(outdir, name='조철희', window=0x200, max_hits=40):
    """Locate the 조철희 name in the target and dump everything around it.

    Writes <outdir>/probe_<ts>.txt and .json. Also reports whether the process
    survived the attach, which is the Cheat-Engine question.
    """
    os.makedirs(outdir, exist_ok=True)
    ts = time.strftime('%Y%m%d_%H%M%S')
    txt_p = os.path.join(outdir, 'probe_%s.txt' % ts)
    json_p = os.path.join(outdir, 'probe_%s.json' % ts)
    lines = []

    def log(s=''):
        lines.append(s)

    pid = find_pid()
    log('pid %s  target %s  ts %s' % (pid, name, ts))
    if not pid:
        log('NOTRUNNING')
        open(txt_p, 'w', encoding='utf-8').write('\n'.join(lines))
        return {'ok': False, 'why': 'not running', 'txt': txt_p}
    h = open_proc(pid)
    log('OpenProcess -> %s  err=%d' % (bool(h), C.get_last_error()))
    if not h:
        open(txt_p, 'w', encoding='utf-8').write('\n'.join(lines))
        return {'ok': False, 'why': 'open failed', 'txt': txt_p}

    needles = [(name.encode('cp949'), 'cp949'), (name.encode('utf-16-le'), 'utf16')]
    found = {'cp949': 0, 'utf16': 0}
    contexts = []

    def on_hit(a, i):
        k = needles[i][1]
        found[k] += 1
        if len(contexts) < max_hits:
            blob = read(h, max(0, a - window), window * 2)
            contexts.append({'addr': a, 'kind': k,
                             'hex': hexdump(blob, max(0, a - window)),
                             'floats': floats_near(h, a)})

    t0 = time.time()
    scan(h, [n[0] for n in needles], on_hit=on_hit)
    log('scan %.1fs  hits cp949=%d utf16=%d  kept=%d'
        % (time.time() - t0, found['cp949'], found['utf16'], len(contexts)))
    for c in contexts:
        log()
        log('=== hit %016x (%s) ===' % (c['addr'], c['kind']))
        if c['floats']:
            log('float pairs nearby: %s' % json.dumps(c['floats'][:8]))
        log(c['hex'])

    alive = bool(read(h, 0, 0x1000))
    log()
    log('alive_after_scan %s' % alive)
    k32.CloseHandle(h)
    open(txt_p, 'w', encoding='utf-8').write('\n'.join(lines))
    json.dump({'ts': ts, 'pid': pid, 'found': found, 'alive': alive,
               'contexts': contexts}, open(json_p, 'w', encoding='utf-8'), ensure_ascii=False)
    return {'ok': True, 'pid': pid, 'found': found, 'alive': alive, 'txt': txt_p, 'json': json_p}


if __name__ == '__main__':
    import sys
    d = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.getcwd(), 'debug', 'mem')
    print(json.dumps(probe(d), ensure_ascii=False))
