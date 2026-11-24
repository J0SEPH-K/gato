# Gersang.exe Themida unpack + XIGNCODE survey — result

Client: C:\Users\Administrator\AKInteractive\Gersang\Gersang.exe
SHA-256 02edcd63c227577477db5cb2451716722c12b08f6ecc5a9219d21fbf8fa303d3
PID 21024, runtime base 0x7ff779bc0000, SizeOfImage 0x13e33000

## DONE — Themida is off

Themida decrypts in memory only (.themida raw size 0 on disk), so the plaintext image was
taken from the live process, not the file.

1. dump_remote.py — ReadProcessMemory over the whole image; dump length == SizeOfImage,
   dump offset == RVA.
2. carve2.py — rebuilds a PE from that dump: headers from the dump, real raw data for every
   section (.themida raw 0x672000), ImageBase left at the true runtime base.
   Output unpacked_live.exe 333637120 B.
3. loadtest2.py — VirtualAlloc at the preferred base 0x7ff779bc0000 succeeds, every section
   memmoved and byte-compared: 13/13 sections 100.0% match, entry bytes
   e88201000041524989e24152498b7210 (the .boot decompressor prologue) land correctly.

Decryption evidence, not just header sanity:
- .text 163/163 64K windows at entropy < 7.0 (on-disk .text is 7.95 = packed).
- .text starts with a real sub rsp,0x28; mov rax, gs:[0x58] prologue, 86.7% linear-sweep
  disassembly validity across random offsets, 319k prologue-class instructions.
- .rdata yields 437 game data-table names (Armor.txt, AbyssMonsterSetInfo.txt, Sooryun.txt,
  MazeMap.txt, ...), 210 Korean UI strings ([사인검 속성:, [공격력:, <진형효과>), 10.5k ASCII strings.
- .themida itself is decoded Themida/WinLicense runtime (entropy 5.22, 207 diagnostic strings,
  CheckIN/TP_IN//dumpstatus).

## DONE — imports recovered (was the blocker)

The 23-descriptor table at RVA 0x13411280 is only Themida's own stub table (one API per DLL).
The real, loader-populated IAT is at RVA 0x136e0c78, 1630 slots, every slot a 5-byte
Themida jmp into a VM handler.

resolve_thunks3.py walked each thunk into its handler, scanned +/-0x3000 for a pointer (direct
or via rip-relative slot) belonging to a loaded module, and named it from that module's export
directory: 834/1630 resolved — kernel32 612, advapi32 126, ntdll 35, user32 20, shell32 16,
shlwapi 14, gdi32 11. Spot-check 10/10: the qword at each resolved site equals the named export.

Generated: iat_named.tsv, imports_by_dll.txt, unpacked_live.idc (IDA), unpacked_live.ghidra.py.
Load unpacked_live.exe at 0x7ff779bc0000, run the label script, and 834 API thunks are named.

## XIGNCODE — mapped, not devirtualised

- XIGNCODE runs out-of-process: no x*.xem module is mapped in Gersang.exe, and no
  xign/xmag/xcorona/BlackCipher process or service exists while the game is running.
- x3_x64.xem and xcorona_x64.xem are PE32 with a .vlizer section at entropy 8.00 (VMProtect,
  ~0x42000 virtual each) — packed.
- xmag_x64.xem / xnina_x64.xem have no MZ, tag Pust at 0xc, entropy 7.95 — container blobs.
- Loaded Gersang modules are stock system DLLs only, so the game itself does not host the
  anti-cheat body.

Consequence: nothing in the macro path needs XIGNCODE internals. The game's own code and data
are plaintext in unpacked_live.exe.

## Artifacts

unpacked_live.exe, unpacked_live.idc, unpacked_live.ghidra.py, iat_named.tsv,
imports_by_dll.txt, game_data_tables.txt, korean.txt, thunks3.json, carve2.py, dump_remote.py,
resolve_thunks3.py, loadtest2.py
Remote: C:\re\unpacked_live.exe, C:\re\dumps\Gersang.exe.dump
