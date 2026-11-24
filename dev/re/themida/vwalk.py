#!/usr/bin/env python3
"""Walk a live process address space and locate a materialised PE image.

Scans committed regions, reads their first page, and reports any that carry an
MZ/PE header whose SizeOfImage matches a target size (or whose ImageBase matches).
Writes the matching region to <out>.img so it can be carved offline.

Usage: vwalk.py <pid> <want_sizeimage_hex> <out_prefix>
"""
import ctypes as C
import ctypes.wintypes as W
import json
import struct
import sys

k32 = C.WinDLL('kernel32', use_last_error=True)


class MEMORY_BASIC_INFORMATION(C.Structure):
    _fields_ = [('BaseAddress', C.c_void_p), ('AllocationBase', C.c_void_p),
                ('AllocationProtect', W.DWORD), ('PartitionId', W.WORD),
                ('RegionSize', C.c_size_t), ('State', W.DWORD),
                ('Protect', W.DWORD), ('Type', W.DWORD)]


k32.OpenProcess.restype = W.HANDLE
k32.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
k32.VirtualQueryEx.restype = C.c_size_t
k32.VirtualQueryEx.argtypes = [W.HANDLE, C.c_void_p, C.POINTER(MEMORY_BASIC_INFORMATION),
                               C.c_size_t]
k32.ReadProcessMemory.restype = W.BOOL
k32.ReadProcessMemory.argtypes = [W.HANDLE, C.c_void_p, C.c_void_p, C.c_size_t,
                                  C.POINTER(C.c_size_t)]

MEM_COMMIT = 0x1000
PAGE_GUARD = 0x100
PAGE_NOACCESS = 0x01


class PE32(C.Structure):
    _fields_ = [('dwSize', W.DWORD), ('cntUsage', W.DWORD), ('th32ProcessID', W.DWORD),
                ('th32DefaultHeapID', C.c_void_p), ('th32ModuleID', W.DWORD),
                ('cntThreads', W.DWORD), ('th32ParentProcessID', W.DWORD),
                ('pcPriClassBase', C.c_long), ('dwFlags', W.DWORD),
                ('szExeFile', C.c_char * 260)]


k32.CreateToolhelp32Snapshot.restype = W.HANDLE
k32.CreateToolhelp32Snapshot.argtypes = [W.DWORD, W.DWORD]
k32.Process32First.restype = W.BOOL
k32.Process32First.argtypes = [W.HANDLE, C.POINTER(PE32)]
k32.Process32Next.restype = W.BOOL
k32.Process32Next.argtypes = [W.HANDLE, C.POINTER(PE32)]


def find_pid(name):
    snap = k32.CreateToolhelp32Snapshot(0x2, 0)
    e = PE32()
    e.dwSize = C.sizeof(PE32)
    ok = k32.Process32First(snap, C.byref(e))
    while ok:
        if e.szExeFile.decode('latin1').lower() == name.lower():
            return e.th32ProcessID
        ok = k32.Process32Next(snap, C.byref(e))
    return None


def read(h, addr, size):
    buf = C.create_string_buffer(size)
    got = C.c_size_t(0)
    if not k32.ReadProcessMemory(h, C.c_void_p(addr), buf, size, C.byref(got)):
        return buf.raw[:got.value]
    return buf.raw[:got.value]


def main():
    name = sys.argv[1]
    want = int(sys.argv[2], 0)
    out = sys.argv[3]
    pid = find_pid(name) if not name.isdigit() else int(name)
    if not pid:
        print('NOTRUNNING')
        return 2
    h = k32.OpenProcess(0x0410, False, pid)
    if not h:
        print('OPENFAIL %d' % C.get_last_error())
        return 3
    addr = 0x10000
    top = 0x7fffffffffff
    mbi = MEMORY_BASIC_INFORMATION()
    hits = []
    while addr < top:
        if not k32.VirtualQueryEx(h, C.c_void_p(addr), C.byref(mbi), C.sizeof(mbi)):
            addr += 0x1000
            continue
        base = mbi.BaseAddress or 0
        size = mbi.RegionSize
        if mbi.State == MEM_COMMIT and not (mbi.Protect & PAGE_GUARD) and not (mbi.Protect & PAGE_NOACCESS):
            head = read(h, base, 0x1000)
            if head[:2] == b'MZ' and len(head) > 0x40:
                lf = struct.unpack_from('<I', head, 0x3c)[0]
                if 0x40 < lf < 0x400 and head[lf:lf + 4] == b'PE\0\0':
                    try:
                        magic = struct.unpack_from('<H', head, lf + 24)[0]
                        sizeimg = struct.unpack_from('<I', head, lf + 24 + 56)[0]
                        ib = struct.unpack_from('<Q', head, lf + 24 + 24)[0]
                        ep = struct.unpack_from('<I', head, lf + 24 + 16)[0]
                    except struct.error:
                        magic = sizeimg = ib = ep = 0
                    hits.append({'base': hex(base), 'region': hex(size), 'protect': hex(mbi.Protect),
                                 'type': mbi.Type, 'magic': hex(magic), 'sizeimage': hex(sizeimg),
                                 'imagebase': hex(ib), 'entry': hex(ep)})
                    print('HIT base %#x region %#x prot %#x type %d magic %#x sizeimg %#x ib %#x ep %#x'
                          % (base, size, mbi.Protect, mbi.Type, magic, sizeimg, ib, ep))
                    if sizeimg == want or ib in (0x180000000, 0x140000000):
                        n = min(max(size, sizeimg), 0x4000000)
                        blob = read(h, base, n)
                        fp = '%s_%x.img' % (out, base)
                        open(fp, 'wb').write(blob)
                        print('WROTE %s (%d bytes)' % (fp, len(blob)))
                        hits[-1]['file'] = fp
        addr = base + size
    json.dump(hits, open(out + '_hits.json', 'w'), indent=1)
    print('TOTAL %d' % len(hits))
    return 0


if __name__ == '__main__':
    sys.exit(main())
