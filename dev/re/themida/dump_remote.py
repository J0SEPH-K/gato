#!/usr/bin/env python3
"""Dump a live 64-bit process image from a Windows box via ReadProcessMemory.

Runs ON the target. Writes <name>.dump plus a per-module manifest so the image can
be rebuilt offline (PE headers + section map from the on-disk file, bytes from memory).

Usage:  python dump_remote.py Gersang.exe  [outdir]
"""
import ctypes as C
import ctypes.wintypes as W
import json
import os
import struct
import sys
import time

k32 = C.WinDLL('kernel32', use_last_error=True)

PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010
TH32CS_SNAPMODULE = 0x00000008
TH32CS_SNAPMODULE32 = 0x00000010
MAX_PATH = 260


class MODULEENTRY32(C.Structure):
    _fields_ = [('dwSize', W.DWORD), ('th32ModuleID', W.DWORD),
                ('th32ProcessID', W.DWORD), ('GlblcntUsage', W.DWORD),
                ('ProccntUsage', W.DWORD), ('modBaseAddr', C.c_void_p),
                ('modBaseSize', W.DWORD), ('hModule', W.HMODULE),
                ('szModule', C.c_char * 256), ('szExePath', C.c_char * MAX_PATH)]


k32.OpenProcess.restype = W.HANDLE
k32.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
k32.ReadProcessMemory.restype = W.BOOL
k32.ReadProcessMemory.argtypes = [W.HANDLE, C.c_void_p, C.c_void_p, C.c_size_t,
                                  C.POINTER(C.c_size_t)]
k32.CreateToolhelp32Snapshot.restype = W.HANDLE
k32.CreateToolhelp32Snapshot.argtypes = [W.DWORD, W.DWORD]
k32.Module32First.restype = W.BOOL
k32.Module32First.argtypes = [W.HANDLE, C.POINTER(MODULEENTRY32)]
k32.Module32Next.restype = W.BOOL
k32.Module32Next.argtypes = [W.HANDLE, C.POINTER(MODULEENTRY32)]


def find_pid(name):
    k32.CreateToolhelp32Snapshot.restype = W.HANDLE
    snap = k32.CreateToolhelp32Snapshot(0x2, 0)  # TH32CS_SNAPPROCESS
    if snap in (0, -1, W.HANDLE(-1).value):
        return None
    class PE32(C.Structure):
        _fields_ = [('dwSize', W.DWORD), ('cntUsage', W.DWORD), ('th32ProcessID', W.DWORD),
                    ('th32DefaultHeapID', C.c_void_p), ('th32ModuleID', W.DWORD),
                    ('cntThreads', W.DWORD), ('th32ParentProcessID', W.DWORD),
                    ('pcPriClassBase', C.c_long), ('dwFlags', W.DWORD),
                    ('szExeFile', C.c_char * MAX_PATH)]
    k32.Process32First.restype = W.BOOL
    k32.Process32First.argtypes = [W.HANDLE, C.POINTER(PE32)]
    k32.Process32Next.restype = W.BOOL
    k32.Process32Next.argtypes = [W.HANDLE, C.POINTER(PE32)]
    e = PE32(); e.dwSize = C.sizeof(PE32)
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


def modules(pid):
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPMODULE | TH32CS_SNAPMODULE32, pid)
    out = []
    if snap in (0, -1, W.HANDLE(-1).value):
        return out
    m = MODULEENTRY32(); m.dwSize = C.sizeof(MODULEENTRY32)
    ok = k32.Module32First(snap, C.byref(m))
    while ok:
        out.append({'base': m.modBaseAddr or 0, 'size': m.modBaseSize,
                    'name': m.szModule.decode('latin1'),
                    'path': m.szExePath.decode('latin1')})
        ok = k32.Module32Next(snap, C.byref(m))
    return out


def pe_layout(path):
    """Return (image_size, [(va, vsize, rawptr, rawsize, name)]) from the file."""
    d = open(path, 'rb').read()
    pe = struct.unpack_from('<I', d, 0x3c)[0]
    if d[pe:pe + 4] != b'PE\0\0':
        return None, []
    nsec = struct.unpack_from('<H', d, pe + 6)[0]
    optsz = struct.unpack_from('<H', d, pe + 20)[0]
    opt = pe + 24
    magic = struct.unpack_from('<H', d, opt)[0]
    sizeimg = struct.unpack_from('<I', d, opt + 56)[0]
    so = pe + 24 + optsz
    secs = []
    for i in range(nsec):
        o = so + 40 * i
        name = d[o:o + 8].rstrip(b'\0').decode('latin1')
        vs, va, rs, rp = struct.unpack_from('<4I', d, o + 8)
        secs.append((va, vs, rp, rs, name))
    return (sizeimg, secs, magic)


def main():
    if len(sys.argv) < 2:
        print('usage: dump_remote.py <process.exe> [outdir]')
        return 1
    target = sys.argv[1]
    outdir = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.getcwd(), 'dumps')
    os.makedirs(outdir, exist_ok=True)
    pid = find_pid(target)
    if not pid:
        print('NOTRUNNING %s' % target)
        return 2
    h = k32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid)
    if not h:
        print('OPENFAIL err=%d' % C.get_last_error())
        return 3
    print('PID %d' % pid)
    mods = modules(pid)
    man = []
    for m in mods:
        nm = m['name']
        if not (nm.lower().endswith('.exe') or nm.lower().endswith('.xem')
                or nm.lower().endswith('.dll') and ('xign' in nm.lower() or 'x3' in nm.lower()
                                                    or 'xmag' in nm.lower() or 'xnina' in nm.lower()
                                                    or 'xcorona' in nm.lower())):
            continue
        layout = pe_layout(m['path']) if os.path.exists(m['path']) else (None, [], 0)
        sizeimg, secs, magic = layout
        # header bytes straight from memory (covers PE + sections table)
        hdr = read(h, m['base'], 0x1000)
        rec = {'name': nm, 'path': m['path'], 'base': hex(m['base']), 'size': m['size'],
               'magic': hex(magic) if magic else None, 'sections': [], 'file': None}
        blob = bytearray(hdr.ljust(min(m['size'], 0x1000), b'\0'))
        for va, vs, rp, rs, sname in secs:
            data = read(h, m['base'] + va, vs)
            rec['sections'].append({'name': sname, 'va': hex(va), 'vsize': hex(vs),
                                    'got': len(data)})
            end = va + vs
            if end > len(blob):
                blob.extend(b'\0' * (end - len(blob)))
            blob[va:va + len(data)] = data
        fp = os.path.join(outdir, nm + '.dump')
        open(fp, 'wb').write(bytes(blob))
        rec['file'] = fp
        rec['dumped'] = len(blob)
        man.append(rec)
        print('DUMPED %s base=%#x size=%d -> %d bytes' % (nm, m['base'], m['size'], len(blob)))
    json.dump({'pid': pid, 'target': target, 'modules': man},
              open(os.path.join(outdir, 'manifest.json'), 'w'), indent=1)
    print('MANIFEST %s' % os.path.join(outdir, 'manifest.json'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
