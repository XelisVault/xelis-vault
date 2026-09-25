#!/usr/bin/env python3
"""VERIFICATION PASS 4 — cross-contract parity, machine-checked end to
end: the pinned chunk, the call signature, the deposit protocol, the
return-value convention, and the three-way ABI agreement (contract
chunk tables <-> SDK dicts <-> abi/*.json).
"""
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FACTORY = (REPO / "contracts" / "community" / "CommunityLaunch.slx").read_text()
DEX = (REPO / "contracts" / "dex" / "LaunchDEX.slx").read_text()
LAUNCHPAD = (REPO / "contracts" / "launchpad" / "VaultLaunch.slx").read_text()
sys.path.insert(0, str(REPO / "sdk" / "xvault"))

failures = []


def check(cond, msg):
    if not cond:
        failures.append(msg)
        print(f"  FAIL: {msg}")


def order(src):
    return re.findall(r"^(?:entry|pub fn|fn|hook) (\w+)", src, re.M)


print("1. the pinned chunk (both callers -> the DEX's real order)")
dex_order = order(DEX)
m = re.search(r"const DEX_CREATE_POOL_OPEN_CHUNK: u16 = (\d+)", FACTORY)
check(m is not None, "factory pin constant missing")
pin = int(m.group(1))
check(dex_order.index("create_pool_open") == pin,
      f"factory pin {pin} != real position {dex_order.index('create_pool_open')}")
m1 = re.search(r"const DEX_CREATE_POOL_CHUNK: u16 = (\d+)", LAUNCHPAD)
m2 = re.search(r"const DEX_SET_PAUSED_CHUNK: u16 = (\d+)", LAUNCHPAD)
check(m1 and m2 and dex_order.index("create_pool") == int(m1.group(1)),
      "launchpad create_pool pin drifted")
check(dex_order.index("set_pool_buys_paused") == int(m2.group(1)),
      "launchpad set_pool_buys_paused pin drifted")
print(f"  pins OK: create_pool=6, set_pool_buys_paused=7, "
      f"create_pool_open={pin}")

print("2. the call signature + deposit protocol (factory -> DEX)")
mig = re.search(r"fn migrate_coin_to_dex\(.*?\n\}", FACTORY, re.S).group(0)
check("target.call(DEX_CREATE_POOL_OPEN_CHUNK, [asset], deposits)" in mig,
      "the factory's call shape is not .call(pin, [asset], deposits)")
check("deposits.insert(xel, seed_xel)" in mig, "XEL deposit is not the SEED")
check("deposits.insert(asset, yr)" in mig, "token deposit is not the inventory")
check("let seed_xel: u64 = xr - fee" in mig,
      "the fee must be carved BEFORE building the deposits")
cpo = re.search(r"pub fn create_pool_open\(.*?\n\}", DEX, re.S).group(0)
check("get_deposit_for_asset(xel).unwrap_or(0)" in cpo,
      "the DEX reads the XEL seed from the deposits")
check("get_deposit_for_asset(asset).unwrap_or(0)" in cpo,
      "the DEX reads the token seed from the deposits")
check("pub fn create_pool_open(asset: Hash) -> u64" in DEX,
      "create_pool_open signature is not (asset: Hash) -> u64")
print("  call/deposit protocol OK (what the factory sends IS the seed)")

print("3. the return-value convention (v1.4: cross-called chunks return 0)")
check(re.findall(r"^\s*return (\w+)", cpo, re.M) == ["0"],
      "create_pool_open does not return 0")
cp = re.search(r"pub fn create_pool\(.*?\n\}", DEX, re.S).group(0)
check(re.findall(r"^\s*return (\w+)", cp, re.M) == ["0"],
      "create_pool does not return 0 (the second-migration bug)")
check('require(pool_res == 0, "poolerr")' in mig,
      "the factory does not require a zero result")
lp_mig = re.search(r"fn migrate_to_dex\(.*?\n\}", LAUNCHPAD, re.S).group(0)
check('require(pool_res == 0, "poolerr")' in lp_mig,
      "the launchpad does not require a zero result")
print("  both callers require 0; both endpoints return 0  OK")

print("4. three-way ABI agreement (contracts <-> SDK <-> abi/*.json)")
from xvault.protocol import (COMMUNITY_ENTRY_IDS, LAUNCHDEX_ENTRY_IDS,
                             LAUNCHPAD_ENTRY_IDS)  # noqa: E402
for src, ids, abi_path in (
        (FACTORY, COMMUNITY_ENTRY_IDS, "abi/CommunityLaunch.abi.json"),
        (DEX, LAUNCHDEX_ENTRY_IDS, "abi/LaunchDEX.abi.json"),
        (LAUNCHPAD, LAUNCHPAD_ENTRY_IDS, "abi/VaultLaunch.abi.json")):
    o = order(src)
    for name, eid in ids.items():
        check(o.index(name) == eid, f"{abi_path}: {name} id {eid} != real {o.index(name)}")
    abi = json.loads((REPO / abi_path).read_text())
    for e in abi["data"]:
        check(ids.get(e["name"]) == e["entry_id"],
              f"{abi_path}: {e['name']} entry_id {e['entry_id']} != SDK {ids.get(e['name'])}")
        # the param names and count match the contract's signature
        sig = re.search(rf"^(?:entry|pub fn) {e['name']}\(([^)]*)\)", src, re.M)
        params = [p.strip().split(":")[0] for p in sig.group(1).split(",")]
        abi_params = [p["name"] for p in e["params"]]
        check(params == abi_params,
              f"{abi_path}: {e['name']} params {abi_params} != contract {params}")
print("  3 contracts x (SDK dict + abi table + signature) agree  OK")

print("5. the DEX documents BOTH pins in its header")
check("chunk 33 = create_pool_open" in DEX,
      "the DEX header does not document the community pin")
check("chunk 6  = create_pool" in DEX, "the DEX header lost the launchpad pin")
print("  documented  OK")

print()
if failures:
    print(f"PASS 4 FAILED: {len(failures)} failures")
    sys.exit(1)
print("PASS 4 OK — cross-contract parity holds end to end.")
