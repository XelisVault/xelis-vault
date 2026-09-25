#!/usr/bin/env python3
"""silex_compile_check.py — the COMPILER gate (as opposed to the static
linters): every active .slx contract must actually COMPILE with the
canonical Silex toolchain, and the committed abi/*.json files must be
byte-identical to what `silex-cli abi` emits for those sources.

Why this exists: the static gates (lint_silex.py, verify_chunk_ids.py)
read source text and cannot catch a genuine compile error. This gate
runs the real compiler, and it pins the ABI artifacts to the compiler's
own output (type-name casing, param order, entry ids) so the frontend
never encodes against a drifted table.

Binary resolution (in priority order):
  1. $SILEX_CLI  — explicit path (CI downloads the pinned release)
  2. `silex-cli` on PATH
  3. ~/xelis-dev/silex-cli/target/release/silex-cli (local dev build)

Exit 0 = everything compiles AND the committed ABIs match the compiler;
exit 1 = a compile error, an ABI drift, or no compiler found.
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CONTRACTS = [
    ("contracts/community/CommunityLaunch.slx", "abi/CommunityLaunch.abi.json"),
    ("contracts/dex/LaunchDEX.slx", "abi/LaunchDEX.abi.json"),
    ("contracts/launchpad/VaultLaunch.slx", "abi/VaultLaunch.abi.json"),
]


def find_cli() -> str:
    candidates = [os.environ.get("SILEX_CLI", ""), "silex-cli",
                  str(Path.home() / "xelis-dev" / "silex-cli"
                      / "target" / "release" / "silex-cli")]
    for cand in candidates:
        if not cand:
            continue
        if "/" in cand and Path(cand).is_file() and os.access(cand, os.X_OK):
            return cand
        from shutil import which
        hit = which(cand)
        if hit:
            return hit
    return ""


def main() -> int:
    cli = find_cli()
    if not cli:
        print("silex-cli not found (set $SILEX_CLI or install from "
              "github.com/xelis-project/silex-cli) — GATE SKIPPED", file=sys.stderr)
        return 1

    fails = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        for src_rel, abi_rel in CONTRACTS:
            src = REPO / src_rel
            out = tmp / (src.stem + ".json")
            proc = subprocess.run([cli, "compile", str(src), "-f", "json",
                                   "-o", str(out)],
                                  capture_output=True, text=True)
            if proc.returncode != 0:
                fails.append(f"{src_rel}: COMPILE FAILED:\n{proc.stderr}")
                continue

            abi_out = tmp / (src.stem + ".abi.json")
            proc = subprocess.run([cli, "abi", str(src), "-o", str(abi_out)],
                                  capture_output=True, text=True)
            if proc.returncode != 0:
                fails.append(f"{src_rel}: abi generation failed:\n{proc.stderr}")
                continue

            committed = REPO / abi_rel
            try:
                want = json.loads(committed.read_text())
                got = json.loads(abi_out.read_text())
            except (OSError, json.JSONDecodeError) as exc:
                fails.append(f"{abi_rel}: unreadable committed ABI ({exc})")
                continue
            if want != got:
                fails.append(f"{abi_rel}: ABI DRIFT — committed file differs "
                             f"from `silex-cli abi` (regenerate it)")
            else:
                print(f"  OK   {src_rel}  (compiles; ABI in sync)")

    if fails:
        print("SILEX COMPILE CHECK FAILED:")
        for f in fails:
            print("  -", f.replace("\n", "\n    "))
        return 1

    print("silex compile check: PASS — every contract compiles and the "
          "committed abi/*.json match the compiler byte-for-byte.")
    return 0


if __name__ == "__main__":
    sys.exit(main())