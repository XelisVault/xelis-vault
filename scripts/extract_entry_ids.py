#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
extract_entry_ids.py — Auto-generate ENTRY_IDS.md from Silex contracts.
Parses each .slx file and extracts `entry` declarations in order,
assigning sequential IDs starting at 0.
"""
import os
import re
import sys
from pathlib import Path

CONTRACTS_DIR = Path("/home/z/my-project/download/xelis-vault-v5/contracts")
OUTPUT_FILE = Path("/home/z/my-project/download/xelis-vault-v5/docs/ENTRY_IDS.md")

# Regex to match `entry function_name(...)` declarations
ENTRY_RE = re.compile(
    r"^\s*entry\s+("
    r"[A-Za-z_][A-Za-z0-9_]*"
    r")\s*\(([^)]*)\)\s*(?:->\s*([^{]+?))?\s*\{?",
    re.MULTILINE
)

def extract_entries(file_path: Path):
    """Return list of (id, name, params, return_type) tuples."""
    text = file_path.read_text(encoding="utf-8", errors="ignore")
    entries = []
    for i, m in enumerate(ENTRY_RE.finditer(text)):
        name = m.group(1)
        params = m.group(2).strip()
        ret = (m.group(3) or "u64").strip()
        entries.append((i, name, params, ret))
    return entries

def main():
    out = ["# ENTRY IDs — XELIS Vault v5.0\n"]
    out.append("Auto-generated from `contracts/` by `scripts/extract_entry_ids.py`.\n")
    out.append("Each `entry` function gets a sequential ID starting at 0 in declaration order.")
    out.append("`pub fn` and `fn` do NOT count for ID numbering — they are not callable via `Contract::call`.\n")
    out.append("")

    all_contracts = sorted(CONTRACTS_DIR.rglob("*.slx"))
    total_entries = 0
    for slx in all_contracts:
        rel = slx.relative_to(CONTRACTS_DIR)
        entries = extract_entries(slx)
        total_entries += len(entries)
        out.append(f"## `{rel}`\n")
        if not entries:
            out.append("*(no entry functions)*\n")
            continue
        out.append("| ID | Name | Parameters | Return |")
        out.append("|----|------|------------|--------|")
        for eid, name, params, ret in entries:
            # Clean up params: replace newlines, collapse whitespace
            params_clean = " ".join(params.split())
            if not params_clean:
                params_clean = "—"
            ret_clean = " ".join(ret.split())
            out.append(f"| {eid} | `{name}` | `{params_clean}` | `{ret_clean}` |")
        out.append("")

    out.insert(3, f"**Total entry functions across {len(all_contracts)} contracts:** {total_entries}\n")
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text("\n".join(out), encoding="utf-8")
    print(f"✅ Generated {OUTPUT_FILE}")
    print(f"   Contracts scanned: {len(all_contracts)}")
    print(f"   Total entry functions: {total_entries}")

if __name__ == "__main__":
    main()
