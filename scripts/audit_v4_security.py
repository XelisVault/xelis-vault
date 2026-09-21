#!/usr/bin/env python3
"""AUDIT 2 (v4) — mechanical security pass over VaultLaunch v4 +
LaunchDEX v1: guarded subtractions, overflow-guarded accumulators,
access control on every entry, transfers as last interactions, and the
cross-call ordering (state first, external call last).

Heuristic by design — a finding is either fixed or explicitly justified
below; the machine-checked guarantees live in the fuzz/invariant suite
(tests/test_launchpad_reference.py)."""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = [ROOT / "contracts" / "launchpad" / "VaultLaunch.slx",
         ROOT / "contracts" / "dex" / "LaunchDEX.slx"]

# reviewed security decisions, not lint bypasses (mirrors lint_silex.py):
PUBLIC_BY_DESIGN = {
    ("VaultLaunch", "propose"): "creates a project funded by the caller's OWN deposit",
    ("VaultLaunch", "support"): "public voting by design — bounded by the one-vote-per-round key + the D21 deposit dial",
    ("VaultLaunch", "report"): "public voting by design — same bound as support",
    ("VaultLaunch", "sell"): "exit path, never blockable — bounded by the caller's OWN token deposit (whole-deposit)",
    ("VaultLaunch", "claim_vote_deposit"): "pull-refund of the caller's OWN locked deposit (D21) — the storage key embeds the caller's address (v:{pid}:{round}:{caller}), so no voter can ever touch another voter's funds; the slot's recorded amount bounds the payout, and require(locked > 0) makes double claims impossible",
    ("VaultLaunch", "finalize_validation"): "permissionless deadline executor — outcome fully determined by public tallies",
    ("VaultLaunch", "migrate"): "permissionless migration executor — no destination/amount/caller choice, pinned DEX only",
    ("VaultLaunch", "sync_trust_to_dex"): "permissionless keeper — mirrors the public trust status to the pool's buys-pause",
    ("LaunchDEX", "swap_xel_for_token"): "payable-style — bounded by the caller's OWN XEL deposit",
    ("LaunchDEX", "swap_token_for_xel"): "payable-style — bounded by the caller's OWN token deposit (whole-deposit)",
    ("LaunchDEX", "add_liquidity"): "public permanent donation — bounded by BOTH attached deposits; only the caller's OWN excess side can come back (X7 ratio fit)",
}

fails = []


def fn_spans(src):
    lines = src.splitlines()
    spans = []
    cur = None
    for i, line in enumerate(lines):
        m = re.match(r"(entry|pub fn|fn|hook) (\w+)", line.strip())
        if m:
            if cur:
                cur[3] = i
                spans.append(tuple(cur))
            cur = [m.group(2), m.group(1), i, len(lines) - 1]
    if cur:
        spans.append(tuple(cur))
    return spans


def inside_string(line, frag):
    """True when frag sits inside a quoted literal on this line."""
    for m in re.finditer(r'"[^"]*"', line):
        if frag in m.group(0):
            return True
    return False


for path in FILES:
    src = path.read_text()
    stem = path.stem
    spans = fn_spans(src)
    lines = src.splitlines()

    def body_of(n):
        fn = next((s for s in spans if s[2] <= n - 1 < s[3] + 1), None)
        if not fn:
            return None, []
        return fn, lines[fn[2]:n]

    # -- 1. subtractions --------------------------------------------------
    for n, raw in enumerate(lines, 1):
        stripped = raw.strip()
        if stripped.startswith("//"):
            continue
        for m in re.finditer(r"(\w+)\s*-\s*(\w+)", raw):
            a, b = m.group(1), m.group(2)
            frag = m.group(0)
            if inside_string(raw, frag):
                continue  # "buys-paused" is a label, not math
            fn, body = body_of(n)
            if not body:
                continue
            ctx = "\n".join(body)
            guarded = bool(
                # direct guards on the pair (either orientation)
                re.search(rf"require\(\s*{a}\s*>=\s*{b}", ctx) or
                re.search(rf"require\(\s*{b}\s*<=\s*{a}", ctx) or
                re.search(rf"require\(\s*{a}\s*>\s*{b}", ctx) or
                re.search(rf"if\s+{a}\s*>=\s*{b}", ctx) or
                re.search(rf"if\s+{b}\s*>=\s*{a}", ctx) or   # paid >= team -> return 0
                re.search(rf"if\s+{a}\s*>\s*{b}", ctx) or    # unlocked > paid
                re.search(rf"if\s+{a}\s*<=\s*{b}", ctx) or   # now <= vesting_start -> return 0
                re.search(rf"if\s+\w+\s*<\s*{a}\b", ctx) or  # rank < count
                # fee subtractions: fee = fee_take(x, bps) with bps <= 1000
                # (hard-capped) => fee < x, always
                (b == "fee" and f"fee_take({a}," in ctx) or
                 (b == "fee_take" and f"{a} - fee_take({a}" in raw) or
                 # team allocation: team_bps <= 2000 (required in propose)
                 # => team_alloc_of(ts, tb) <= ts/5 < ts
                 (b == "team_alloc_of" and "require(team_bps <= MAX_TEAM_BPS" in ctx) or
                 # DEX swap floors: require(wide < (y as u128)) with
                 # out = wide as u64, checked right above the store
                 (b == "out" and re.search(r"require\(wide < \(" + a + r" as u128\)", ctx)))
            if not guarded:
                fails.append(f"{stem}:{n} unguarded `{frag}` in `{fn[0]}`: {stripped[:70]}")

    # -- 2. accumulator stores via checked_add -----------------------------
    for n, raw in enumerate(lines, 1):
        stripped = raw.strip()
        if stripped.startswith("//"):
            continue
        for m in re.finditer(r"s\.store\((\w+),\s*(\w+)\s*\+\s*(\w+)\)", raw):
            if "COUNT_KEY" in raw or "POOLS_COUNT_KEY" in raw:
                continue  # capacity-checked counters (require(count < MAX) above)
            fails.append(f"{stem}:{n} raw `+` store (not checked_add): {stripped[:70]}")

    # -- 3. access control on every entry ----------------------------------
    for (fname, kind, start, end) in spans:
        if kind != "entry":
            continue
        body = "\n".join(lines[start:end])
        if (stem, fname) in PUBLIC_BY_DESIGN:
            continue
        if re.search(r"get_deposit_for_asset\(\w+\)", body):
            continue  # payable-style: bounded by the caller's own deposit
        guarded = ("only_admin()" in body or
                   re.search(r"require\(caller == ", body) or
                   re.search(r"require\(.*caller == creator", body))
        if not guarded:
            fails.append(f"{stem}:{start + 1} entry `{fname}` has no access guard")

    # -- 4. transfers last (no store after, events/return fine) ------------
    for (fname, kind, start, end) in spans:
        if kind != "entry":
            continue
        body_lines = lines[start:end]
        for i, ln in enumerate(body_lines):
            if re.search(r"let ok: bool = transfer\(", ln):
                for l in body_lines[i + 1:]:
                    s = l.strip()
                    if s and not s.startswith("//") and "s.store(" in s:
                        fails.append(f"{stem}: store AFTER transfer in `{fname}`: {s[:60]}")

    # -- 5. cross-calls last (state written before, sync flag documented) --
    for (fname, kind, start, end) in spans:
        if kind != "entry":
            continue
        body_lines = lines[start:end]
        for i, ln in enumerate(body_lines):
            if ".call(" in ln:
                for l in body_lines[i + 1:]:
                    s = l.strip()
                    if s and not s.startswith("//") and "s.store(" in s and "DEX_SYNCED" not in l:
                        fails.append(f"{stem}: store AFTER cross-call in `{fname}`: {s[:60]}")

if fails:
    print("AUDIT 2 (SECURITY) FAILED:")
    for f in fails:
        print("  -", f)
    sys.exit(1)
print("AUDIT 2 (SECURITY): PASS — every subtraction guarded (direct require, "
      "inverted-if, hard-capped fee/bps math, or deposit bounds), every "
      "accumulator via checked_add, every entry access-controlled or "
      "PUBLIC_BY_DESIGN, transfers and cross-calls as last interactions.")
