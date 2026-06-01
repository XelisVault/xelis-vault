#!/usr/bin/env python3
"""Batch deploy all 20 contracts to devnet and extract addresses."""

import json, os, time, re, base64, urllib.request

RPC = "http://localhost:18082/json_rpc"
AUTH = base64.b64encode(b":testpassword").decode()
BUILD = "/Users/adrien/opencode/xelis-vault/build"

# Contracts with or without constructor
WITH_CTOR = {
    "PriceOracle": True, "xUSD": True, "InterestRateModel": False,
    "VaultEngine": True, "FlashLoan": True, "InsurancePool": True,
    "PrivateInsurance": True, "LendingMarket": True, "PeerLoan": True,
    "SyndicatePool": True, "SealedBidAuction": True, "AssetVault": True,
    "TreasuryVault": True, "RevenueShare": True, "Payroll": True,
    "ComplianceModule": True, "VLT": True, "GovernanceVault": True,
    "Timelock": True,
    "SavingsRate": True,
}

CONTRACTS = list(WITH_CTOR.keys())

def rpc(method, params, timeout=600):
    payload = json.dumps({"jsonrpc":"2.0","id":"1","method":method,"params":params}).encode()
    req = urllib.request.Request(RPC, data=payload, headers={"Content-Type":"application/json"})
    req.add_header("Authorization", f"Basic {AUTH}")
    resp = urllib.request.urlopen(req, timeout=timeout)
    return json.loads(resp.read())

# Pre-load hexes
hexes = {}
for c in CONTRACTS:
    with open(os.path.join(BUILD, f"{c}.hex")) as f:
        hexes[c] = f.read().strip()

# Check wallet
try:
    balance = rpc("get_balance", {}, timeout=10).get("result", "?")
    print(f"Wallet balance: {balance}", flush=True)
except Exception as e:
    print(f"Wallet not responding: {e}", flush=True)
    exit(1)

# Deploy remaining contracts (skip already deployed)
already = {"PriceOracle", "xUSD", "InterestRateModel"}
results = {}

# Check daemon log for already-deployed contracts
try:
    with open("/Users/adrien/opencode/xelis-vault/data/daemon.log") as f:
        log = f.read()
    # Find which contracts are on-chain
    matches = set(re.findall(r'Invoke contract ([0-9a-f]{64}) from \1', log))
    # Also find contracts deployed without constructor
    # Those won't have "Invoke contract from itself" lines, so just skip
    # PriceOracle and xUSD are known deployed
except:
    matches = set()

print(f"Skipping already known deployments: PriceOracle, xUSD, InterestRateModel", flush=True)

for c in CONTRACTS:
    if c in already:
        print(f"\n=== {c} = SKIP (already deployed) ===", flush=True)
        results[c] = {"status": "skip"}
        continue

    print(f"\n=== {c} ===", flush=True)
    deploy_params = {"module": hexes[c]}
    if WITH_CTOR[c]:
        deploy_params["invoke"] = {"max_gas": 1000000}

    try:
        result = rpc("build_transaction", {
            "deploy_contract": deploy_params,
            "broadcast": True
        }, timeout=600)
        if "result" in result:
            print(f"  OK - tx: {result['result'].get('hash','?')}", flush=True)
            results[c] = {"status": "ok", "tx": result["result"].get("hash")}
        else:
            print(f"  FAIL: {result.get('error',{}).get('message', result)}", flush=True)
            results[c] = {"status": "error", "error": result.get("error")}
    except Exception as e:
        print(f"  TIMEOUT: {e}", flush=True)
        results[c] = {"status": "timeout", "error": str(e)}

print(f"\n{'='*60}", flush=True)
ok = sum(1 for v in results.values() if v['status'] == 'ok')
skip = sum(1 for v in results.values() if v['status'] == 'skip')
fail = sum(1 for v in results.values() if v['status'] != 'ok' and v['status'] != 'skip')
print(f"OK: {ok}, SKIP: {skip}, FAIL: {fail}, TOTAL: {len(CONTRACTS)}", flush=True)

# Wait for mining
print("\nWaiting 60s for mining...", flush=True)
time.sleep(60)

# Extract ALL addresses from daemon log
print("\n=== Contract Addresses ===")
try:
    with open("/Users/adrien/opencode/xelis-vault/data/daemon.log") as f:
        log = f.read()
    # All Invoke contract lines (constructor calls)
    all_matches = re.findall(r'Invoke contract ([0-9a-f]{64}) from \1', log)
    print(f"Found {len(all_matches)} constructor deploy events in log", flush=True)
    # Also check for contracts deployed without constructor (InterestRateModel)
    # These don't have Invoke contract lines, so we can't detect them this way
    
    # Build registry from chronological matching
    registry = {}
    deployed_chrono = [c for c in CONTRACTS if results.get(c, {}).get('status') in ('ok', 'skip')]
    recent = all_matches[-len(deployed_chrono):] if len(all_matches) >= len(deployed_chrono) else all_matches
    for i, c in enumerate(deployed_chrono):
        if i < len(recent):
            registry[c] = recent[i]
            print(f"  {c}: {recent[i]}", flush=True)
        else:
            print(f"  {c}: address not found in log", flush=True)
    
    # Save
    with open(os.path.join(BUILD, "registry.json"), "w") as f:
        json.dump(registry, f, indent=2)
    print(f"\nRegistry saved to {BUILD}/registry.json", flush=True)
except Exception as e:
    print(f"Error: {e}", flush=True)
