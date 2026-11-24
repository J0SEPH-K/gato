#!/usr/bin/env python3
"""Emit analysis-side labels for the resolved Themida IAT thunks.

Produces iat_named.tsv, imports_by_dll.txt, unpacked_live.idc, unpacked_live.ghidra.py

Usage: gen_labels.py <thunks_json> <imagebase_hex>
"""
import json
import sys
from collections import defaultdict

src, ib = sys.argv[1], int(sys.argv[2], 0)
rows = [r for r in json.load(open(src)) if r.get("name")]
rows.sort(key=lambda r: r["i"])
print("named slots: %d" % len(rows))

with open("iat_named.tsv", "w") as f:
    f.write("slot\tslot_rva\tthunk_rva\tdll\tfunction\n")
    for r in rows:
        f.write("%d\t%#x\t%#x\t%s\t%s\n"
                % (r["i"], r["slot_rva"], r["thunk"], r["mod"].lower(), r["name"]))

by = defaultdict(list)
for r in rows:
    by[r["mod"].lower()].append((r["i"], r["thunk"], r["name"]))
with open("imports_by_dll.txt", "w") as f:
    for dll in sorted(by):
        f.write("# %s  (%d)\n" % (dll, len(by[dll])))
        for i, t, n in by[dll]:
            f.write("  slot %-5d thunk %#x  %s\n" % (i, t, n))
        f.write("\n")

with open("unpacked_live.idc", "w") as f:
    f.write("// auto-generated: name Themida IAT thunks\n")
    f.write("// thunk VA = 0x%x + thunk_rva\n" % ib)
    f.write("#include <idc.idc>\nstatic main() {\n")
    for r in rows:
        safe = r["name"].replace("?", "_").replace("@", "_")
        f.write('  MakeName(0x%x, "%s_%s_%d");\n'
                % (ib + r["thunk"], r["mod"].split(".")[0].lower(), safe, r["i"]))
        f.write('  MakeComm(0x%x, "%s!%s");\n'
                % (ib + r["thunk"], r["mod"].lower(), r["name"]))
    f.write("}\n")

with open("unpacked_live.ghidra.py", "w") as f:
    f.write("# auto-generated: name Themida IAT thunks (Ghidra Jython)\n")
    f.write("from ghidra.program.model.symbol import SourceType\n")
    f.write("st = currentProgram.getSymbolTable()\n")
    f.write("af = currentProgram.getAddressFactory().getDefaultAddressSpace()\n")
    for r in rows:
        safe = r["name"].replace("?", "_").replace("@", "_")
        label = "%s_%s_%d" % (r["mod"].split(".")[0].lower(), safe, r["i"])
        f.write("try:\n")
        f.write("    st.createLabel(af.getAddress(0x%x), '%s', SourceType.USER_DEFINED)\n"
                % (ib + r["thunk"], label))
        f.write("except Exception:\n    pass\n")
    f.write("print('labelled %d thunks')\n" % len(rows))

print("dlls: %d" % len(by))
for dll in sorted(by):
    print("  %-18s %d" % (dll, len(by[dll])))
