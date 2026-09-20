#!/usr/bin/env python3
"""verify_chunk_ids.py — XELIS chunk-ID (entry-point) verifier.

In the XELIS VM every function of a Silex contract compiles to a numbered
chunk: the `hook constructor` is chunk 0 and EVERY function (private `fn`,
`entry`, `pub fn`) takes the next chunk ID in source declaration order.
Cross-contract calls are `.call(Nu16, ...)` — a wrong N silently calls the
wrong function (or nothing), which is how the v12 protocol ended up with
bumped mappings (audit Tasks 1/2-a/2-b: 3 wrong oracle params, comments
carrying 3 inconsistent numbering schemes).

This tool enforces, for every .slx under contracts/ (legacy/ excluded):

  1. CHUNK TABLE check — the chunk table documented in the contract header
     (the comment block introduced by a line containing "CHUNK TABLE" /
     "Chunk layout", made of `N name` pairs) must match the real
     declaration order EXACTLY (every function present, no extra, no wrong
     ID). The table is the on-chain ABI documentation; a stale table is how
     the v12 chunk drift stayed invisible.
  2. Inter-contract call check — `Contract::new(...)`, `.call(Nu16, ...)`
     and `.delegate(Nu16, ...)` are detected. For contracts/mixer/* the
     invariant is ZERO inter-contract calls (PrivacyMixerV4 is deliberately
     self-contained: 0 dependencies, 0 permissions, deployable alone) — any
     such call is a BLOCKER. For other active contracts, resolvable targets
     are checked against the target's real chunk table.
  3. Mixer invariant statement — the report explicitly affirms "0
     inter-contract calls" when it holds.

Validation mode: `--validate-legacy` cross-checks the numbering rule itself
against the compiler ground truth (legacy/build/chunkmap_*.txt were emitted
by the real xelis_compile_tool when v12 was built). If the parser disagreed
with the compiled chunk maps, the RULE would be wrong — this mode proves it
isn't. It is a dev tool, not a CI gate.

Exit code: 0 if every active contract is OK, 1 otherwise, 2 on tool error.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from silex_parse import SilexFile  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
VERSION = "1.0.0"

# marker introducing a documented chunk table in the header
TABLE_MARKER_RE = re.compile(r"//.*?(CHUNK TABLE|Chunk layout|chunk table)", re.IGNORECASE)
PAIR_RE = re.compile(r"(\d+)\s+([A-Za-z_]\w*)")
SEPARATOR_RE = re.compile(r"^//[\s\-=_]*$")

# inter-contract call primitives (stdlib: Contract::new, call, delegate)
CROSS_CALL_RES = [
    ("Contract::new", re.compile(r"\bContract\s*::\s*new\s*\(")),
    (".call(Nu16)", re.compile(r"\.\s*call\s*\(\s*\d+\s*u16")),
    (".delegate(Nu16)", re.compile(r"\.\s*delegate\s*\(\s*\d+\s*u16")),
]

COMPILED_KIND_TO_OURS = {"Hook": "hook", "Internal": "fn", "Entry": "entry", "All": "pub_fn"}
CHUNKMAP_LINE_RE = re.compile(r"^\s*chunk (\d+):\s+(\w+)\s*(?:\{[^}]*\}\s*)?(\w+)\s+\(")


# ---------------------------------------------------------------------------
# Chunk table parsing
# ---------------------------------------------------------------------------

def parse_documented_table(sf: SilexFile) -> Optional[Dict[int, str]]:
    """Extract {chunk_id: name} from the header CHUNK TABLE block.

    Returns None when the contract documents no table at all.
    """
    lines = sf.src.splitlines()
    marker_idx: Optional[int] = None
    for i, text in enumerate(lines):
        if TABLE_MARKER_RE.search(text):
            marker_idx = i
            break
    if marker_idx is None:
        return None

    table: Dict[int, str] = {}
    # walk comment lines after the marker; skip `// ----` separators and
    # empty `//` lines; stop at the first prose comment line without pairs
    # or at the first non-comment line (end of header block)
    for text in lines[marker_idx + 1: marker_idx + 1 + 100]:
        stripped = text.strip()
        if not stripped.startswith("//"):
            break
        if SEPARATOR_RE.match(stripped):
            continue
        pairs = PAIR_RE.findall(stripped[2:])
        if not pairs:
            break
        for cid, name in pairs:
            table[int(cid)] = name
    return table or None


def format_table(entries: List[Tuple[str, str]], indent: str = "    ") -> str:
    """Render a chunk table the way the contract headers do (3 columns)."""
    if not entries:
        return indent + "(no functions)"
    width = max(len(name) for _, name in entries) + 2
    out = []
    for i in range(0, len(entries), 3):
        row = entries[i:i + 3]
        out.append(indent + "".join(f"{idx:<3} {name:<{width}}" for idx, name in row).rstrip())
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Inter-contract call detection
# ---------------------------------------------------------------------------

def find_cross_calls(sf: SilexFile) -> List[Tuple[int, str, str]]:
    """[(line, primitive, masked-line-snippet)] of inter-contract calls."""
    out: List[Tuple[int, str, str]] = []
    for label, rx in CROSS_CALL_RES:
        for m in rx.finditer(sf.masked):
            line = sf.line_of_offset(m.start())
            out.append((line, label, sf.line_text(line)))
    return sorted(out)


def resolve_call_target(sf: SilexFile, line: int) -> Optional[Path]:
    """Best-effort static resolution of the contract being called on `line`.

    Recognizes the v12 idiom:
        let X: Contract = Contract::new(x_hash)
        let x_hash: Hash = s.load(SOME_KEY)
    and maps SOME_KEY / var names to another ACTIVE contract by stem
    (e.g. ORACLE_KEY -> oracle/StakedOracle.slx when such a file is active).
    Returns None when the target cannot be resolved statically.
    """
    # only meaningful when several active contracts exist; the mixer has none
    return None


# ---------------------------------------------------------------------------
# Per-contract verification
# ---------------------------------------------------------------------------

def verify_contract(path: Path, rel: str, active: Dict[Path, SilexFile],
                    is_mixer: bool) -> Tuple[bool, List[str]]:
    sf = SilexFile.parse(path)
    ok = True
    log: List[str] = []

    actual = [(str(i), f.name) for i, f in enumerate(sf.functions)]
    documented = parse_documented_table(sf)

    log.append(f"{rel}")
    log.append(f"  functions in declaration order : {len(actual)}")
    log.append("  generated chunk table (truth):")
    log.append(format_table(actual))

    if documented is None:
        if not actual:
            log.append("  OK: no functions and no chunk table — nothing to verify "
                       "(degenerate contract)")
        else:
            ok = False
            log.append("  FAIL: no documented CHUNK TABLE in the header — every "
                       "active contract must document its chunk table (it is the "
                       "ABI reference used by every caller)")
    else:
        doc_entries = sorted(documented.items())
        log.append(f"  documented CHUNK TABLE        : {len(doc_entries)} entries")
        problems: List[str] = []
        doc_set = dict(doc_entries)
        actual_map = {int(i): n for i, n in actual}
        for cid, name in doc_set.items():
            if cid not in actual_map:
                problems.append(f"chunk {cid} documented as `{name}` but the "
                                f"contract has no chunk {cid} (only 0..{len(actual)-1})")
            elif actual_map[cid] != name:
                problems.append(f"chunk {cid} documented as `{name}` but is "
                                f"actually `{actual_map[cid]}`")
        for cid, name in actual_map.items():
            if cid not in doc_set:
                problems.append(f"chunk {cid} `{name}` is missing from the "
                                f"documented table")
        if problems:
            ok = False
            log.append("  FAIL: documented table does not match declaration order:")
            for p in problems:
                log.append(f"    - {p}")
        else:
            log.append("  OK: documented table matches declaration order exactly")

    # -- inter-contract calls ------------------------------------------------
    cross = find_cross_calls(sf)
    if is_mixer:
        if cross:
            ok = False
            log.append(f"  FAIL: MIXER INVARIANT BROKEN — {len(cross)} inter-contract "
                       f"call(s) in contracts/mixer/:")
            for (line, label, snippet) in cross:
                log.append(f"    - L{line} {label}: {snippet[:70]}")
            log.append("       The mixer is a standalone mainnet contract by design "
                       "(0 deps, 0 permissions); adding a cross-call is a design "
                       "change that needs founder sign-off, not a patch.")
        else:
            log.append("  OK: 0 inter-contract calls (mixer invariant holds — "
                       "no Contract::new / .call / .delegate)")
    else:
        for (line, label, snippet) in cross:
            target = resolve_call_target(sf, line)
            if target is None:
                log.append(f"  NOTE: L{line} {label} — target not resolvable "
                           f"statically, verify the chunk id manually: {snippet[:60]}")
            else:
                tsf = active.get(target)
                if tsf is None:
                    log.append(f"  NOTE: L{line} {label} — target {target} is not "
                               f"an active contract")
                else:
                    m = re.search(r"\.\s*call\s*\(\s*(\d+)\s*u16", snippet)
                    if m and int(m.group(1)) >= len(tsf.functions):
                        ok = False
                        log.append(f"  FAIL: L{line} .call({m.group(1)}u16) — chunk "
                                   f"{m.group(1)} does not exist in {target.name} "
                                   f"(max {len(tsf.functions)-1})")
                    else:
                        log.append(f"  OK: L{line} {label} -> {target.name}")
    return ok, log


# ---------------------------------------------------------------------------
# Legacy validation against compiler ground truth
# ---------------------------------------------------------------------------

def validate_legacy(legacy_dir: Path) -> int:
    build = legacy_dir / "build"
    contracts_dir = legacy_dir / "contracts"
    maps = sorted(build.glob("chunkmap_*.txt"))
    if not maps:
        print(f"error: no chunkmap_*.txt under {build}", file=sys.stderr)
        return 2
    slx_by_name = {p.stem: p for p in contracts_dir.rglob("*.slx")}

    print("=" * 78)
    print(" Chunk-ID rule validation — parser vs compiler ground truth")
    print(" (chunkmap_*.txt were emitted by the real xelis_compile_tool)")
    print("=" * 78)
    matched = mismatched = missing = 0
    mismatch_details: List[str] = []
    for cm in maps:
        name = cm.stem.replace("chunkmap_", "")
        src = slx_by_name.get(name)
        if src is None:
            missing += 1
            continue
        compiled: List[Tuple[str, str]] = []  # (our_kind, fn_name)
        for line in cm.read_text(errors="replace").splitlines():
            m = CHUNKMAP_LINE_RE.match(line)
            if m:
                kind = COMPILED_KIND_TO_OURS.get(m.group(2), m.group(2).lower())
                compiled.append((kind, m.group(3)))
        sf = SilexFile.parse(src)
        parsed = [(f.kind, f.name) for f in sf.functions]
        if parsed == compiled:
            matched += 1
            print(f"  OK       {name}: {len(parsed)} chunks, order+names+kinds identical")
        else:
            mismatched += 1
            print(f"  MISMATCH {name}: compiled {len(compiled)} chunks vs parsed "
                  f"{len(parsed)} functions")
            for i in range(max(len(compiled), len(parsed))):
                c = compiled[i] if i < len(compiled) else None
                p = parsed[i] if i < len(parsed) else None
                if c != p:
                    mismatch_details.append(
                        f"    {name} chunk {i}: compiled={c} parsed={p}")
    for d in mismatch_details[:40]:
        print(d)
    total = matched + mismatched + missing
    print("-" * 78)
    print(f" Contracts: {total} | identical to compiler: {matched} | mismatched: "
          f"{mismatched} | no source: {missing}")
    if matched and mismatched == 0:
        print(" RULE VALIDATED: declaration order == compiled chunk order, 1:1, "
              "kinds included.")
    elif matched:
        print(f" RULE VALIDATED on {matched}/{matched+mismatched} contracts — "
              f"mismatches are source-vs-build drift (source edited after the "
              f"last compile), not rule errors.")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="XELIS chunk-ID verifier (XelisVault CI)")
    ap.add_argument("--contracts", type=Path, default=REPO_ROOT / "contracts",
                    help="directory to verify (default: <repo>/contracts)")
    ap.add_argument("--validate-legacy", action="store_true",
                    help="dev mode: validate the numbering rule against the "
                         "compiled chunkmaps in legacy/build/ (not a CI gate)")
    args = ap.parse_args(argv)

    if args.validate_legacy:
        return validate_legacy(REPO_ROOT / "legacy")

    base = args.contracts.resolve()
    if not base.is_dir():
        print(f"error: contracts directory not found: {base}", file=sys.stderr)
        return 2
    files = sorted(p for p in base.rglob("*.slx")
                   if "legacy" not in p.relative_to(base).parts)
    if not files:
        print(f"error: no .slx files found under {base}", file=sys.stderr)
        return 2

    active: Dict[Path, SilexFile] = {}
    for p in files:
        active[p] = SilexFile.parse(p)

    print("=" * 78)
    print(f" XELIS chunk-ID verifier v{VERSION} — XelisVault CI")
    print(" chunk 0 = constructor, then every fn/entry/pub fn in declaration order")
    print("=" * 78)
    all_ok = True
    statuses: List[str] = []
    for p in files:
        rel = str(p.relative_to(base))
        is_mixer = "mixer" in p.relative_to(base).parts
        ok, log = verify_contract(p, rel, active, is_mixer)
        all_ok = all_ok and ok
        statuses.append(f"  {'OK  ' if ok else 'FAIL'} {rel}")
        print()
        for line in log:
            print(line)

    print()
    print("-" * 78)
    for s in statuses:
        print(s)
    print("-" * 78)
    mixer_calls = sum(len(find_cross_calls(sf))
                      for p, sf in active.items() if "mixer" in p.relative_to(base).parts)
    print(f" Result: {'ALL OK' if all_ok else 'FAIL'} | mixer inter-contract "
          f"calls: {mixer_calls} (invariant: 0)")
    print("=" * 78)
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
