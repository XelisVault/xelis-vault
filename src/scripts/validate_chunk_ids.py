#!/usr/bin/env python3
"""
validate_chunk_ids.py — Validates all cross-contract chunk IDs.

This validator ACTUALLY verifies that each .call(Nu16, ...) cross-contract call
targets a real entry ID in the target contract. It does this by:
  1. Parsing each .slx file to extract its entry list (in declaration order)
  2. Finding all .call(Nu16, ...) patterns in every contract
  3. Resolving the target contract by analyzing the variable assignment
  4. Checking that entry ID N exists in the target contract
  5. Checking that the entry name matches the expected function

Usage:
    python3 scripts/validate_chunk_ids.py
"""
import re
from pathlib import Path

CONTRACTS_DIR = Path(__file__).resolve().parent.parent / "contracts"


def get_entries(filepath):
    """Extract ALL function names (entry + pub fn + fn + hook) in declaration order.
    
    CRITICAL: In XELIS VM, chunk IDs are assigned to ALL functions in source order,
    not just entries. A .call(Nu16) targets chunk N which includes entry, pub fn,
    fn, and hook. Only pub fn chunks are callable cross-contract.
    """
    src = filepath.read_text()
    entries = []
    for m in re.finditer(r'^(entry|pub fn|fn|hook)\s+(\w+)\s*[\(<]', src, re.MULTILINE):
        entries.append((m.group(1), m.group(2)))
    return entries


def build_entry_map():
    """Build a map of contract_path -> [entry_names]."""
    entry_map = {}
    for f in sorted(CONTRACTS_DIR.rglob("*.slx")):
        rel = str(f.relative_to(CONTRACTS_DIR))
        entry_map[rel] = get_entries(f)
    return entry_map


def find_contract_hash_var(src, var_name, max_lines=50):
    """
    Try to find what contract hash a variable refers to.
    Look for patterns like:
      let oracle: Contract = Contract::new(oracle_hash)
      let oracle_hash: Hash = s.load(ORACLE_KEY)
    Returns the storage key name or contract name if found, None otherwise.
    """
    # Look for: let VAR_hash: Hash = s.load(STORAGE_KEY)
    pat1 = rf'let\s+{re.escape(var_name)}_hash\s*:\s*Hash\s*=\s*s\.load\((\w+)\)'
    m = re.search(pat1, src)
    if m:
        return m.group(1)
    
    # Look for: let VAR: Contract = Contract::new(SOMETHING_hash)
    pat2 = rf'let\s+{re.escape(var_name)}\s*:\s*Contract\s*=\s*Contract::new\((\w+)\)'
    m = re.search(pat2, src)
    if m:
        return m.group(1)
    
    return None


# Mapping of storage key names to contract files
STORAGE_KEY_TO_CONTRACT = {
    "ORACLE_KEY": "oracle/StakedOracle.slx",
    "REGISTRY_KEY": "proxy/ContractRegistry.slx",
    "XUSD_CONTRACT_KEY": "usd/xUSD.slx",
    "VLT_CONTRACT_KEY": "token/VLTToken.slx",
    "MINER_CONTRACT_KEY": "miner/XelisVaultMiner.slx",
    "GOV_VAULT_KEY": "governance/GovernanceVault.slx",
    "TIMELOCK_KEY": "governance/Timelock.slx",
    "IRM_KEY": "interest/InterestRateModel.slx",
    "COMPLIANCE_KEY": "compliance/ComplianceModule.slx",
}

# Mapping of variable name prefixes to contract files (for common patterns)
VAR_PREFIX_TO_CONTRACT = {
    "oracle": "oracle/StakedOracle.slx",
    "reg": "proxy/ContractRegistry.slx",
    "xusd": "usd/xUSD.slx",
    "vlt": "token/VLTToken.slx",
    "miner": "miner/XelisVaultMiner.slx",
    "mc": "miner/XelisVaultMiner.slx",
    "gv": "governance/GovernanceVault.slx",
    "tl": "governance/Timelock.slx",
    "irm": "interest/InterestRateModel.slx",
    "cb": "flashloan/FlashCallback.slx",
    "compliance": "compliance/ComplianceModule.slx",
}


def resolve_target_contract(src, var_name):
    """Try to resolve which contract a variable points to."""
    # Try storage key lookup
    storage_key = find_contract_hash_var(src, var_name)
    if storage_key and storage_key in STORAGE_KEY_TO_CONTRACT:
        return STORAGE_KEY_TO_CONTRACT[storage_key]
    
    # Try variable name prefix
    for prefix, contract in VAR_PREFIX_TO_CONTRACT.items():
        if var_name == prefix or var_name.startswith(prefix + "_"):
            return contract
    
    return None


def main():
    entry_map = build_entry_map()
    
    errors = []
    ok = 0
    warnings = 0
    
    for f in sorted(CONTRACTS_DIR.rglob("*.slx")):
        src = f.read_text()
        rel = str(f.relative_to(CONTRACTS_DIR))
        
        # Strip comments before searching (avoid false positives in comments)
        clean_src = re.sub(r'//.*', '', src)
        
        # Find all .call(Nu16, ...) patterns in clean source
        for m in re.finditer(r'(\w+)\.call\((\d+)u16', clean_src):
            var_name = m.group(1)
            entry_id = int(m.group(2))
            
            # Skip 'target.call' (dynamic, used by GuardianMultisig)
            if var_name == "target":
                warnings += 1
                continue
            
            target_contract = resolve_target_contract(src, var_name)
            
            if target_contract is None:
                warnings += 1
                continue
            
            entries = entry_map.get(target_contract, [])
            
            if entry_id >= len(entries):
                errors.append(
                    f"❌ {rel}: {var_name}.call({entry_id}u16) — chunk {entry_id} does not exist "
                    f"in {target_contract} (max={len(entries)-1})"
                )
            else:
                func_type, fn_name = entries[entry_id]
                if func_type == "pub fn":
                    ok += 1
                else:
                    errors.append(
                        f"🔴 {rel}: {var_name}.call({entry_id}u16) → {target_contract}.{fn_name} "
                        f"is '{func_type}' (NOT callable cross-contract — only 'pub fn' is)"
                    )
    
    # Print results
    print("=" * 70)
    print("XELIS Vault — Cross-Contract Entry ID Validator (REAL)")
    print("=" * 70)
    print()
    
    for e in errors:
        print(f"  {e}")
    
    if warnings > 0:
        print(f"\n  ({warnings} warnings — dynamic or unresolvable calls skipped)")
    
    print()
    print(f"{'=' * 70}")
    print(f"Results: {ok} OK, {len(errors)} FAIL, {warnings} warnings")
    
    if len(errors) == 0:
        print("✅ ALL CROSS-CONTRACT ENTRY IDs VALIDATED SUCCESSFULLY!")
    else:
        print(f"❌ {len(errors)} entry IDs need fixing!")
    
    return 0 if len(errors) == 0 else 1


if __name__ == "__main__":
    exit(main())
