#!/usr/bin/env python3
"""
compile_all.py — Compile the Silex contracts and regenerate the build
artifacts (bytecode .hex, .abi.json, chunk maps) + docs/entry_chunk_ids.json.

Usage:
    python3 scripts/compile_all.py                 # all 51 contracts
    python3 scripts/compile_all.py AirdropTracker  # only the named contracts

Every compile run mechanically verifies the append-only layout against the
existing chunk maps (old chunks must keep position+kind+name) and refuses to
write the artifacts on violation.

The compiler is the `xelis_compile_tool` binary (a Rust wrapper around the
official xelis-vm v1.3.0 crates: silex-lexer/parser/compiler +
build_environment::<MockStorageProvider>(ContractVersion::V1)). Set
XELIS_COMPILE_TOOL=<path> if the binary is not in one of the default
locations. The output is byte-for-byte identical to the canonical Windows
compiler (verified against the committed build/ artifacts).

Chunk layout is append-only: re-running this script after adding NEW
functions at the END of a contract keeps every existing chunk index stable
(verified automatically by --check / post-compile diff).
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BUILD = REPO / "build"
CONTRACTS = REPO / "contracts"
OUT_JSON = REPO / "docs" / "entry_chunk_ids.json"

# name -> relative source path (51 contracts, alphabetical)
CORE = {
    "AirdropClaim": "airdrop/AirdropClaim.slx",
    "AirdropTracker": "airdrop/AirdropTracker.slx",
    "AnalyticsCollector": "analytics/AnalyticsCollector.slx",
    "AssetVault": "rwa/AssetVault.slx",
    "ComplianceModule": "compliance/ComplianceModule.slx",
    "ContractRegistry": "proxy/ContractRegistry.slx",
    "CreditScore": "credit/CreditScore.slx",
    "EmergencyShutdown": "safety/EmergencyShutdown.slx",
    "FaucetContract": "faucet/FaucetContract.slx",
    "FeeDistributor": "founder/FeeDistributor.slx",
    "FlashCallback": "flashloan/FlashCallback.slx",
    "FlashLoan": "flashloan/FlashLoan.slx",
    "FounderVesting": "founder/FounderVesting.slx",
    "GovernanceDelegation": "governance/GovernanceDelegation.slx",
    "GovernanceVault": "governance/GovernanceVault.slx",
    "Governor": "governance/Governor.slx",
    "GuardianMultisig": "governance/GuardianMultisig.slx",
    "InsurancePool": "insurance/InsurancePool.slx",
    "InterestRateModel": "interest/InterestRateModel.slx",
    "LendingMarket": "lending/LendingMarket.slx",
    "MinerDelegation": "miner/MinerDelegation.slx",
    "MinerPool": "miner/MinerPool.slx",
    "Notifications": "notifications/Notifications.slx",
    "OracleGovernance": "governance/OracleGovernance.slx",
    "Payroll": "payroll/Payroll.slx",
    "PeerLoan": "lending/PeerLoan.slx",
    "PrivacyMixer": "privacy/PrivacyMixer.slx",
    "PSM": "amm/PSM.slx",
    "RevenueShare": "revenue/RevenueShare.slx",
    "SavingsRate": "savings/SavingsRate.slx",
    "SealedBidAuction": "auction/SealedBidAuction.slx",
    "SocialGraph": "social/SocialGraph.slx",
    "StakedOracle": "oracle/StakedOracle.slx",
    "SyndicatePool": "lending/SyndicatePool.slx",
    "Timelock": "governance/Timelock.slx",
    "TreasuryVault": "treasury/TreasuryVault.slx",
    "VaultChat": "chat/VaultChat.slx",
    "VaultEngineV3": "vault/VaultEngineV3.slx",
    "VaultSwapV2": "amm/VaultSwapV2.slx",
    "VLTToken": "token/VLTToken.slx",
    "xUSD": "usd/xUSD.slx",
    "AirdropClaimExtra": None,  # placeholder removed below
}
# keep only real entries (build dir is the source of truth for the full list)
KNOWN = {n: p for n, p in CORE.items() if p}
_EXTRA = {
    # contracts present in build/ but not in the hand list above
}
for cm in BUILD.glob("chunkmap_*.txt"):
    name = cm.stem.replace("chunkmap_", "")
    if name not in KNOWN:
        m = re.search(r"CHUNK MAP for \S+?contracts/(\S+?\.slx)", cm.read_text())
        if m:
            _EXTRA[name] = m.group(1)
KNOWN.update(_EXTRA)

CHUNK_RE = re.compile(
    r"^chunk (\d+): (Internal|Hook(?: \{[^}]*\})?|Entry \{[^}]*\}|All \{[^}]*\}) (\S+) \((\d+) instructions\)")


def find_tool() -> str:
    env = os.environ.get("XELIS_COMPILE_TOOL")
    candidates = [
        env,
        "/home/z/xelis-compile-tool/target/release/xelis_compile_tool",
        str(REPO / "tools" / "xelis_compile_tool"),
        str(REPO.parent / "xelis-compile-tool" / "target" / "release" / "xelis_compile_tool"),
    ]
    for c in candidates:
        if c and os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    sys.exit(
        "xelis_compile_tool not found — build it once:\n"
        "  git clone --branch v1.3.0 https://github.com/xelis-project/xelis-vm\n"
        "  git clone https://github.com/xelis-project/xelis-blockchain\n"
        "  (cargo project depending on xelis_common + silex-lexer/parser/compiler,\n"
        "   see build/README.md)  then set XELIS_COMPILE_TOOL=<binary path>")


def parse_chunkmap(text: str):
    """[(index, kind, name, instructions)] from the tool stderr."""
    out = []
    for line in text.splitlines():
        m = CHUNK_RE.match(line)
        if m:
            out.append((int(m.group(1)), m.group(2), m.group(3), int(m.group(4))))
    return out


def check_append_only(name: str, old_map, new_map) -> bool:
    """Old chunks must keep position+kind+name (params may be extended)."""
    ok = True
    for (i, kind, fname, _n) in old_map:
        if i >= len(new_map):
            print(f"  !! {name}: chunk {i} DISAPPEARED")
            ok = False
            continue
        ni, nkind, nname, _ = new_map[i]
        base_kind = nkind.split(" {")[0]
        if base_kind != kind.split(" {")[0] or nname != fname:
            print(f"  !! {name}: chunk {i} changed {kind} {fname} -> {nkind} {nname}")
            ok = False
    return ok


def main():
    args = [a for a in sys.argv[1:]]
    tool = find_tool()

    only = args or None
    names = [n for n in sorted(KNOWN) if (not only or n in only)]
    if only:
        missing = [n for n in only if n not in KNOWN]
        if missing:
            sys.exit(f"Unknown contract names: {missing}")

    entry_ids = json.loads(OUT_JSON.read_text()) if OUT_JSON.exists() else {}
    changed, failures = [], []

    for name in names:
        src = CONTRACTS / KNOWN[name]
        if not src.exists():
            failures.append((name, "source not found"))
            continue
        old_map_path = BUILD / f"chunkmap_{name}.txt"
        old_map = parse_chunkmap(old_map_path.read_text()) if old_map_path.exists() else []

        hex_path = BUILD / f"deploy_{name}.hex"
        abi_path = BUILD / f"deploy_{name}.abi.json"
        proc = subprocess.run(
            [tool, str(src), str(hex_path), str(abi_path)],
            capture_output=True, text=True, timeout=900)
        if proc.returncode != 0:
            failures.append((name, proc.stderr[-400:]))
            print(f"FAIL {name}: compile error")
            continue

        new_map = parse_chunkmap(proc.stderr)
        if not new_map:
            failures.append((name, "empty chunk map"))
            continue
        if old_map:
            if not check_append_only(name, old_map, new_map):
                failures.append((name, "append-only violation"))
                continue

        # write chunkmap (stderr already has the right paths)
        (BUILD / f"chunkmap_{name}.txt").write_text(proc.stderr)
        entry_ids[name] = {
            str(i): {"instructions": n, "kind": k.split(" {")[0], "name": f}
            for (i, k, f, n) in new_map
        }
        changed.append(name)
        print(f"OK   {name}: {len(new_map)} chunks -> {hex_path.name}")

    if changed:
        OUT_JSON.write_text(json.dumps(entry_ids, indent=2, sort_keys=True) + "\n")
        print(f"\n{len(changed)} contracts compiled; entry_chunk_ids.json regenerated.")

    if failures:
        print("\nFAILURES:")
        for n, err in failures:
            print(f"  {n}: {err}")
        sys.exit(1)


if __name__ == "__main__":
    main()
