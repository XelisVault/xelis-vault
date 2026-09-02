#!/usr/bin/env python3
"""gen_chunk_map.py — Recompiles all core contracts and regenerates
docs/entry_chunk_ids.json + /tmp/deploy_<Name>.hex.

The map associates compiled chunk_id -> {name, kind, params}. Names come from
source declaration order (1:1 with compiled chunk order), kinds
and params from the compile tool stderr.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CONTRACTS = REPO / "contracts"
TOOL = "/Users/adrien/opencode/xelis-compile-tool/target/release/xelis_compile_tool"
OUT = REPO / "docs" / "entry_chunk_ids.json"
HEXDIR = Path("/tmp")

# (Name, relative path) — 34 core + AirdropClaim (mainnet, compiled for map)
CORE = [
    ("ContractRegistry", "proxy/ContractRegistry.slx"),
    ("ComplianceModule", "compliance/ComplianceModule.slx"),
    ("VLTToken", "token/VLTToken.slx"),
    ("xUSD", "usd/xUSD.slx"),
    ("FaucetContract", "faucet/FaucetContract.slx"),
    ("XelisVaultMiner", "miner/XelisVaultMiner.slx"),
    ("StakedOracle", "oracle/StakedOracle.slx"),
    ("MinerPool", "miner/MinerPool.slx"),
    ("InterestRateModel", "interest/InterestRateModel.slx"),
    ("VaultEngineV3", "vault/VaultEngineV3.slx"),
    ("SavingsRate", "savings/SavingsRate.slx"),
    ("FlashLoan", "flashloan/FlashLoan.slx"),
    ("FlashCallback", "flashloan/FlashCallback.slx"),
    ("VaultSwapV2", "amm/VaultSwapV2.slx"),
    ("PSM", "amm/PSM.slx"),
    ("LendingMarket", "lending/LendingMarket.slx"),
    ("PeerLoan", "lending/PeerLoan.slx"),
    ("SyndicatePool", "lending/SyndicatePool.slx"),
    ("SealedBidAuction", "auction/SealedBidAuction.slx"),
    ("PrivacyMixer", "privacy/PrivacyMixer.slx"),
    ("AssetVault", "rwa/AssetVault.slx"),
    ("TreasuryVault", "treasury/TreasuryVault.slx"),
    ("RevenueShare", "revenue/RevenueShare.slx"),
    ("Payroll", "payroll/Payroll.slx"),
    ("GovernanceVault", "governance/GovernanceVault.slx"),
    ("Timelock", "governance/Timelock.slx"),
    ("GuardianMultisig", "governance/GuardianMultisig.slx"),
    ("Governor", "governance/Governor.slx"),
    ("OracleGovernance", "governance/OracleGovernance.slx"),
    ("VaultChat", "chat/VaultChat.slx"),
    ("FounderVesting", "founder/FounderVesting.slx"),
    ("FeeDistributor", "founder/FeeDistributor.slx"),
    ("MinerDelegation", "miner/MinerDelegation.slx"),
    ("AirdropTracker", "airdrop/AirdropTracker.slx"),
    ("AirdropClaim", "airdrop/AirdropClaim.slx"),
]


def strip_comments(src: str) -> str:
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.DOTALL)
    return re.sub(r"//.*", "", src)


def main():
    only = sys.argv[1:] or None
    result = {}
    failures = []
    for name, rel in CORE:
        if only and name not in only:
            continue
        src_path = CONTRACTS / rel
        hex_path = HEXDIR / f"deploy_{name}.hex"
        proc = subprocess.run([TOOL, str(src_path), str(hex_path)],
                              capture_output=True, text=True, timeout=600)
        if proc.returncode != 0:
            failures.append((name, proc.stderr[-300:]))
            print(f"❌ {name}: COMPILE KO")
            continue

        # noms dans l'ordre source
        clean = strip_comments(src_path.read_text())
        names = [m.group(1) for m in re.finditer(
            r"^(?:entry|pub fn|fn|hook)\s+(\w+)\s*[\(<]", clean, re.MULTILINE)]

        # compiled chunks (stderr)
        chunks = [(int(m.group(1)), m.group(2), m.group(3).strip())
                  for m in re.finditer(
                      r"chunk (\d+): ([A-Za-z]+)(?: \{ parameters: (.*) \} \()? ", "")
                  ]
        # parsing robuste ligne par ligne
        chunks = []
        for line in proc.stderr.splitlines():
            m = re.match(r"\s*chunk (\d+): (\w+)(.*)", line)
            if not m:
                continue
            cid, kind, rest = int(m.group(1)), m.group(2), m.group(3)
            pm = re.search(r"parameters: (.*)\)", rest)
            chunks.append((cid, kind, pm.group(1).strip() if pm else None))

        entry = {}
        for i, name_i in enumerate(names):
            if i >= len(chunks):
                break
            cid, kind, params = chunks[i]
            if kind in ("Entry", "All"):
                entry[str(cid)] = {"name": name_i, "kind": kind,
                                   "params": f"{'Some' if params else 'None'}({params or ''})"}
        result[name] = entry
        print(f"✅ {name}: {len(chunks)} chunks, {len(entry)} Entry/All")

    if failures:
        print("\nÉCHECS:")
        for n, e in failures:
            print(f"  {n}: {e}")
        sys.exit(1)

    OUT.write_text(json.dumps(result, indent=1, sort_keys=True))
    total = sum(len(v) for v in result.values())
    print(f"\n{OUT} written: {len(result)} contracts, {total} Entry/All entries")


if __name__ == "__main__":
    main()
