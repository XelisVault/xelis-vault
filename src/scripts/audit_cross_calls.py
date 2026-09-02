#!/usr/bin/env python3
"""audit_cross_calls.py — Detects cross-contract calls to non-'all' chunks.

VM rule: Contract::call(N) requires Access::All (pub fn). A call to an Entry
or Internal chunk produces the runtime revert "Chunk is not public".

Method:
  1. Compile each .slx with xelis_compile_tool, parse stderr -> access by chunk.
  2. Find each site `VAR.call(Nu16, ...)`.
  3. Resolve VAR -> target contract (local bindings, getters get_*_contract,
     semantic alias on storage keys).
  4. Report any site whose resolved target is not 'all' at chunk N.
"""
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CONTRACTS = REPO / "contracts"
TOOL = Path("/Users/adrien/opencode/xelis-compile-tool/target/release/xelis_compile_tool")

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

# semantic alias -> contract name (applied on variable names / keys)
ALIASES = [
    (r"miner_delegation|delegation", "MinerDelegation"),
    (r"miner_pool", "MinerPool"),
    (r"miner|mc\b", "XelisVaultMiner"),
    (r"vlt", "VLTToken"),
    (r"xusd", "xUSD"),
    (r"registry|reg\b", "ContractRegistry"),
    (r"oracle", "StakedOracle"),
    (r"psm", "PSM"),
    (r"flash_callback|callback_contract|cb_contract", "FlashCallback"),
    (r"flash_loan|fl\b", "FlashLoan"),
    (r"timelock|tl\b", "Timelock"),
    (r"governance_vault|gvault|gov_vault", "GovernanceVault"),
    (r"governor", "Governor"),
    (r"guardian", "GuardianMultisig"),
    (r"compliance", "ComplianceModule"),
    (r"irm|interest_rate", "InterestRateModel"),
    (r"treasury", "TreasuryVault"),
    (r"chat", "VaultChat"),
    (r"auction", "SealedBidAuction"),
    (r"mixer", "PrivacyMixer"),
    (r"savings", "SavingsRate"),
    (r"lending_market|market", "LendingMarket"),
    (r"peer_loan|peer", "PeerLoan"),
    (r"syndicate", "SyndicatePool"),
    (r"revenue", "RevenueShare"),
    (r"payroll", "Payroll"),
    (r"insurance", "InsurancePool"),
    (r"tracker|airdrop", "AirdropTracker"),
]

DYNAMIC_RECEIVERS = {"target", "callback_target"}  # dynamic resolution (multisig)


def compile_and_parse(rel_path: str):
    """Compile un .slx et retourne ({chunk_id: 'all'|'entry'|'internal'|'hook'}, hex)."""
    src = CONTRACTS / rel_path
    out_hex = Path("/tmp/audit_tmp.hex")
    proc = subprocess.run(
        [str(TOOL), str(src), str(out_hex)],
        capture_output=True, text=True, timeout=300)
    if proc.returncode != 0:
        raise RuntimeError(f"compile KO {rel_path}: {proc.stderr[-400:]}")
    access = {}
    for m in re.finditer(r"chunk (\d+): (\w+)", proc.stderr):
        cid, kind = int(m.group(1)), m.group(2).lower()
        access[cid] = kind  # hook/all/entry/internal
    return access, out_hex.read_text().strip()


def strip_comments(src: str) -> str:
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.DOTALL)
    return re.sub(r"//.*", "", src)


def resolve_receiver(var: str, func_src: str, file_src: str):
    """Finds the contract targeted by a receiver variable."""
    if var in DYNAMIC_RECEIVERS:
        return None
    # 1. binding local: let VAR_hash = s.load(KEY) / get_miner_contract()
    pat_local = rf"(?:let\s+)?{re.escape(var)}\w*\s*(?::[^=]+)?=\s*([^;\n]+)"
    for m in reversed(list(re.finditer(pat_local, func_src))):
        rhs = m.group(1)
        mm = re.search(r"s\.load\((\w+)\)", rhs)
        if mm:
            hit = alias_lookup(mm.group(1))
            if hit:
                return hit
        mm = re.search(r"get_(\w+)\(", rhs)
        if mm:
            hit = alias_lookup(mm.group(1))
            if hit:
                return hit
        hit = alias_lookup(rhs)
        if hit:
            return hit
    # 2. getter defined in file: fn get_VAR...() -> Contract { s.load(KEY) }
    gm = re.search(rf"fn\s+get_{re.escape(var)}\w*\s*\(", file_src)
    if gm:
        tail = file_src[gm.start():gm.start() + 500]
        mm = re.search(r"s\.load\((\w+)\)", tail)
        if mm:
            hit = alias_lookup(mm.group(1))
            if hit:
                return hit
    return alias_lookup(var)


def alias_lookup(text: str):
    low = text.lower()
    for pat, name in ALIASES:
        if re.search(pat, low):
            return name
    return None


def split_functions(src: str):
    """Roughly splits the file into named blocks (fn/entry/hook)."""
    marks = [(m.start(), m.group(1)) for m in
             re.finditer(r"^(?:entry|pub fn|fn|hook)\s+(\w+)", src, re.MULTILINE)]
    blocks = []
    for i, (pos, name) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else len(src)
        blocks.append((name, src[pos:end]))
    return blocks


def main():
    print("== Compile and map accesses ==")
    access_maps = {}
    for name, rel in CORE:
        try:
            access_maps[name], _ = compile_and_parse(rel)
            kinds = {}
            for k in access_maps[name].values():
                kinds[k] = kinds.get(k, 0) + 1
            print(f"  {name:20} {len(access_maps[name]):3} chunks {kinds}")
        except Exception as e:
            print(f"  {name:20} ERROR: {str(e)[:80]}")

    print("\n== Audit call sites ==")
    bugs, unknown, ok = [], [], 0
    for name, rel in CORE:
        path = CONTRACTS / rel
        raw = path.read_text()
        src = strip_comments(raw)
        blocks = split_functions(src)
        for fname, body in blocks:
            for m in re.finditer(r"(\w+)\.call\((\d+)u16", body):
                var, cid = m.group(1), int(m.group(2))
                line_no = src[:src.find(body) + m.start()].count("\n") + 1
                if var in DYNAMIC_RECEIVERS:
                    unknown.append((rel, line_no, fname, var, cid, "dynamique"))
                    continue
                target = resolve_receiver(var, body, src)
                if target is None or target not in access_maps:
                    unknown.append((rel, line_no, fname, var, cid,
                                    f"cible={target}"))
                    continue
                acc = access_maps[target].get(cid)
                if acc == "all":
                    ok += 1
                elif acc is None:
                     bugs.append((rel, line_no, fname, var, cid, target,
                                  f"chunk {cid} MISSING in {target}"))
                else:
                    bugs.append((rel, line_no, fname, var, cid, target,
                                 f"access='{acc}' (requires 'all')"))

    print(f"\nOK: {ok} | BUGS: {len(bugs)} | UNRESOLVED: {len(unknown)}")
    if bugs:
        print("\n--- BUGS (cross-contract call to non-'all' chunk) ---")
        for b in bugs:
            print(f"  {b[0]}:{b[1]} [{b[2]}] {b[3]}.call({b[4]}) -> {b[5]} : {b[6]}")
    if unknown:
        print("\n--- Needs manual review ---")
        for u in unknown:
            print(f"  {u[0]}:{u[1]} [{u[2]}] {u[3]}.call({u[4]}) : {u[5]}")

    # export for later fix
    import json
    (REPO / "docs" / "cross_call_audit.json").write_text(json.dumps(
        {"bugs": bugs, "unknown": unknown, "ok": ok}, indent=1))
    print("\nresults -> docs/cross_call_audit.json")


if __name__ == "__main__":
    main()
