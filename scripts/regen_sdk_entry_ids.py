#!/usr/bin/env python3
"""regen_sdk_entry_ids.py — regenerate LAUNCHPAD_ENTRY_IDS / _ALT (and the
LaunchDEX equivalents) in sdk/xvault/xvault/protocol.py from the REAL
declaration order of the .slx sources.

Rationale: the SDK dicts are the ABI reference real transactions build from;
hand-editing them after inserting a mid-file function is how chunk drift
starts. This tool re-emits the dicts from the contracts' own declaration
order (the same rule verify_chunk_ids.py enforces), so the SDK can never
disagree with the source. tests/test_*_reference.py still asserts the result.

Usage: python scripts/regen_sdk_entry_ids.py [--check]
  --check: verify only, exit 1 if the dicts are stale (CI-friendly).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PROTOCOL = REPO / "sdk" / "xvault" / "xvault" / "protocol.py"

TARGETS = [
    {
        "src": REPO / "contracts" / "launchpad" / "VaultLaunch.slx",
        "dict": "LAUNCHPAD_ENTRY_IDS",
        "alt": "LAUNCHPAD_ENTRY_IDS_ALT",
    },
    {
        "src": REPO / "contracts" / "dex" / "LaunchDEX.slx",
        "dict": "LAUNCHDEX_ENTRY_IDS",
        "alt": "LAUNCHDEX_ENTRY_IDS_ALT",
    },
    {
        "src": REPO / "contracts" / "community" / "CommunityLaunch.slx",
        "dict": "COMMUNITY_ENTRY_IDS",
        "alt": "COMMUNITY_ENTRY_IDS_ALT",
    },
]

DECL_RE = re.compile(r"^(?:entry|pub fn|fn|hook) (\w+)", re.M)
ENTRY_RE = re.compile(r"^entry (\w+)\(", re.M)


def emit_dict(name: str, ids: dict) -> str:
    pad = " " * 4
    body = ",\n".join(f'{pad}"{k}": {v}' for k, v in ids.items())
    return f"{name} = {{\n{body},\n}}"


def replace_dict(text: str, name: str, new_block: str) -> tuple[str, bool]:
    pat = re.compile(rf"^{name} = \{{.*?^\}}", re.S | re.M)
    m = pat.search(text)
    if not m:
        return text, False
    return text[:m.start()] + new_block + text[m.end():], m.group(0) != new_block


def main() -> int:
    check_only = "--check" in sys.argv
    text = PROTOCOL.read_text()
    stale = False
    for t in TARGETS:
        src = t["src"].read_text()
        order = DECL_RE.findall(src)
        entries = set(ENTRY_RE.findall(src))
        entry_order = [n for n in order if n in entries]
        full_ids = {n: i for i, n in enumerate(order) if n in entries}
        alt_ids = {n: i for i, n in enumerate(entry_order)}

        for dname, ids in ((t["dict"], full_ids), (t["alt"], alt_ids)):
            if f"{dname} = " not in text:
                print(f"BLOCKER: {dname} not found in protocol.py")
                return 2
            block = emit_dict(dname, ids)
            text, changed = replace_dict(text, dname, block)
            if changed:
                stale = True
                print(f"{'STALE' if check_only else 'regenerated'}: {dname}")
    if check_only:
        return 1 if stale else 0
    if stale:
        PROTOCOL.write_text(text)
        print("protocol.py updated")
    else:
        print("already in sync")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
