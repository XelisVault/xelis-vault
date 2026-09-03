#!/usr/bin/env python3
"""
============================================================================
 XELIS Vault — v12 UPGRADE SCRIPT (testnet)
============================================================================
Upgrades the 11 contracts changed in v12 and migrates the airdrop state.

WHAT IT DOES (resumable, every step is idempotent and logged to
docs/upgrade_v12_state.json):

  PHASE A — Deploy the new bytecode (contract hash == deploy tx hash):
     AirdropTracker v12, XelisVaultMiner v12.1, StakedOracle v12,
     VaultChat v12, Governor v12, GovernanceVault v12, PSM v12,
     VaultSwapV2 v12, SavingsRate v12, VaultEngineV3 v12, PrivacyMixer v3.

  PHASE B — Registry UPGRADE (entry 4) for each name -> new hash.
     (ContractRegistry keeps prev_<Name> for rollback. Register entry 3 is
      one-way; UPGRADE is the correct path for existing names.)

  PHASE C — Post-upgrade configuration of the FRESH contract storages:
     - AirdropTracker: set_authorized_recorder for every recorder contract
       (chunk 68, Hash param) — this is what ACTIVATES auto-recording.
     - Each wired contract: set_airdrop_tracker(new tracker hash).
     - XelisVaultMiner: vlt contract/asset, delegation, treasury, registry,
       timelock, guardian, register_service(StakedOracle), hb interval/timeout.
     - StakedOracle: set_miner_contract, set_registry, add feed XEL/USD.
     - VaultChat: set_vlt_asset, set_treasury, set_miner_contract.
     - PSM / VaultSwapV2 / VaultEngineV3 / SavingsRate: oracle / xusd /
       registry / treasury setters (same config as the previous instance).
     - PrivacyMixer v3: set_registry, set_treasury, fees 0.

  PHASE D — Airdrop state migration (old tracker -> new tracker):
     reads user_<addr> structs on the OLD tracker via RPC, then
     import_user_state (chunk 78) for each user — points AND days_active AND
     mainnet address are preserved — then finalize_migration (chunk 79, 200
     users per call) recomputes the global totals.

  PHASE E — Update the repo runtime files:
     network/testnet.json, docs/deployment_state.json (hashes) — and prints
     the exact commands to re-register the 6 miners + restart the keeper.

USAGE (admin wallet, from the repo root):
    python3 deploy/upgrade_v12.py --phase a
    python3 deploy/upgrade_v12.py --phase b
    python3 deploy/upgrade_v12.py --phase c
    python3 deploy/upgrade_v12.py --phase d --old-tracker <hash>
    python3 deploy/upgrade_v12.py --phase e
    python3 deploy/upgrade_v12.py --phase all

Bytecode: compiled .hex files are read from --bytecode-dir (default /tmp),
named deploy_<Name>.hex — same convention as the v12R redeploy.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from protocol import (  # noqa: E402
    Protocol, WalletClient, DaemonClient, RPCError,
    val_str, val_hash, val_addr, val_u64, val_u8, val_bool,
)

STATE_PATH = REPO / "docs" / "upgrade_v12_state.json"
NETWORK_PATH = REPO / "network" / "testnet.json"
BYTECODE_DIR = Path("/tmp")

# The 11 contracts of this upgrade, in deployment order.
UPGRADE_CONTRACTS = [
    "AirdropTracker", "XelisVaultMiner", "StakedOracle", "VaultChat",
    "Governor", "GovernanceVault", "PSM", "VaultSwapV2", "SavingsRate",
    "VaultEngineV3", "PrivacyMixer",
]

# Registry name for each contract key (source: network/testnet.json keys).
KEY_TO_NAME = {
    "airdrop_tracker": "AirdropTracker",
    "miner": "XelisVaultMiner",
    "staked_oracle": "StakedOracle",
    "vault_chat": "VaultChat",
    "governor": "Governor",
    "governance_vault": "GovernanceVault",
    "psm": "PSM",
    "vault_swap": "VaultSwap",
    "savings_rate": "SavingsRate",
    "vault_engine": "VaultEngineV3",
    "privacy_mixer": "PrivacyMixer",
}

# Chunks (source of truth: docs/entry_chunk_ids.json REGENERATED after compile)
CH = {
    "ContractRegistry": {"upgrade": 4, "get": 16},
    "AirdropTracker": {
        "set_authorized_recorder": 68, "set_registry": 70,
        "set_timelock": 71, "set_guardian": 72, "set_vlt_contract": 69,
        "import_user_state": 78, "finalize_migration": 79,
    },
    "XelisVaultMiner": {
        "set_vlt_contract": 40, "set_vlt_asset": 41,
        "set_delegation_contract": 42, "set_treasury": 43,
        "set_registry": 44, "set_timelock": 45, "set_guardian": 46,
        "register_service": 31, "set_heartbeat_interval": 34,
        "set_heartbeat_timeout": 35, "set_min_stake": 33,
        "set_airdrop_tracker": 92, "set_base_reward_oracle": 36,
    },
    "StakedOracle": {
        "set_miner_contract": 44, "set_registry": 46,
        "add_feed_entry": 10, "set_airdrop_tracker": 60,
        "set_max_stale": 56, "set_hard_stale": 57,
    },
    "VaultChat": {
        "set_vlt_asset": 96, "set_treasury": 95,
        "set_miner_contract": 36, "set_airdrop_tracker": 135,
    },
    "Governor": {"set_governance_vault": 10, "set_timelock": 11,
                 "set_airdrop_tracker": 23},
    "GovernanceVault": {"set_airdrop_tracker": 37},
    "PSM": {
        "set_xusd_contract": 13, "set_xusd_asset": 14, "set_oracle": 23,
        "set_treasury": 16, "set_registry": 17, "set_airdrop_tracker": 38,
    },
    "VaultSwapV2": {"set_oracle": 37, "set_registry": 18,
                    "set_airdrop_tracker": 58},
    "SavingsRate": {"set_registry": 15, "set_xusd_asset": 13,
                    "set_airdrop_tracker": 33},
    "VaultEngineV3": {
        "set_registry": 40, "set_xusd_contract": 41,
        "set_xusd_asset": 42, "set_treasury": 43,
        "set_airdrop_tracker": 76,
    },
    "PrivacyMixer": {"set_registry": 19, "set_treasury": 18,
                     "set_airdrop_tracker": 29},
}

# Airdrop recorders to authorize (registry keys).
RECORDERS = [
    "miner", "staked_oracle", "vault_chat", "governor", "governance_vault",
    "psm", "vault_swap", "savings_rate", "vault_engine", "privacy_mixer",
]


def load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text())
    return {"contracts": {}, "steps": [], "migrated_users": []}


S = None
STATE = None


def save():
    STATE_PATH.write_text(json.dumps(STATE, indent=2, sort_keys=True))


def log(msg: str):
    print(f"[upgrade_v12] {msg}", flush=True)


class Deployer:
    def __init__(self):
        self.p = Protocol()
        self.w: WalletClient = self.p.wallet
        self.d: DaemonClient = self.p.daemon

    def deploy(self, name: str, max_gas: int = 2_000_000) -> str:
        if name in S:
            log(f"SKIP deploy {name} (already at {S[name][:16]}...)")
            return S[name]
        hexfile = BYTECODE_DIR / f"deploy_{name}.hex"
        if not hexfile.exists():
            raise FileNotFoundError(
                f"{hexfile} not found — compile the v12 contracts first "
                f"(see docs/UPGRADE_v12.md §2).")
        module = hexfile.read_text().strip()
        self.w._wait_nonce_catchup()

        def _build():
            payload = {
                "deploy_contract": {"contract": module,
                                    "invoke": {"max_gas": max_gas}},
                "fee": {"fixed": 100_000_000},
                "broadcast": True,
            }
            r = self.w._call("build_transaction", payload)
            h = r.get("hash") if isinstance(r, dict) else None
            if not h:
                raise RPCError(f"deploy {name}: no hash: {r}")
            return h
        from protocol import _with_retries
        tx = _with_retries(_build)
        self.p.wait(tx, timeout=180)
        rev = self.p.revert_reason(tx)
        if rev:
            raise RuntimeError(f"deploy {name} REVERTED: {rev}")
        S[name] = tx
        STATE["contracts"][name] = tx
        save()
        log(f"DEPLOY {name} -> {tx}")
        return tx

    def invoke(self, contract: str, entry: int, params=None, deposits=None,
               max_gas=10_000_000, label=""):
        if entry is None:
            log(f"SKIP {label} (chunk id unknown — update CH map)")
            return None
        key = f"{label}@{contract[:12]}"
        if key in STATE.get("steps", []):
            log(f"SKIP {label} (already done)")
            return None
        tx = self.w.invoke(contract, entry, params or [], deposits or {},
                           max_gas=max_gas)
        self.p.wait(tx, timeout=180)
        rev = self.p.revert_reason(tx)
        if rev:
            raise RuntimeError(f"{label or entry} REVERTED: {rev}")
        log(f"OK {label} (chunk {entry})")
        STATE.setdefault("steps", []).append(key)
        save()
        return tx

    def read(self, contract: str, key: str):
        return self.d.read_key(contract, key)


# ---------------------------------------------------------------------------
def phase_a(D: Deployer):
    log("=== PHASE A: deploy the 11 v12 contracts ===")
    for name in UPGRADE_CONTRACTS:
        D.deploy(name)


def phase_b(D: Deployer):
    log("=== PHASE B: registry UPGRADE (entry 4) ===")
    reg = S.get("ContractRegistry") or _current("contract_registry")
    if not reg:
        raise RuntimeError("ContractRegistry hash unknown")
    for key, name in KEY_TO_NAME.items():
        if name not in S:
            log(f"SKIP upgrade {name} (not deployed in this run)")
            continue
        target = S[name]
        cur = D.read(reg, f"cur_{name}")
        if str(cur) == target:
            log(f'SKIP upgrade "{name}" (already current)')
            continue
        D.invoke(reg, 4, [val_str(name), val_hash(target)],
                 max_gas=5_000_000, label=f'upgrade "{name}"')
    log("Registry upgraded. prev_<Name> preserved for rollback (entry 5).")


def phase_c(D: Deployer):
    log("=== PHASE C: post-upgrade configuration ===")
    at = S["AirdropTracker"]
    reg = S.get("ContractRegistry") or _current("contract_registry")
    vlt = _current("vlt_token")
    vlt_asset = _current_vlt_asset()
    xusd = _current("xusd")
    xusd_asset = _current_xusd_asset()
    treasury = _current_treasury_addr()

    # --- AirdropTracker base config ---
    D.invoke(at, CH["AirdropTracker"]["set_registry"], [val_hash(reg)],
             label="Tracker.set_registry")
    # --- Authorize every recorder contract (activates auto-recording) ---
    for key in RECORDERS:
        ch = _current(key)
        if not ch:
            log(f"WARN: no current hash for recorder {key} — skipped")
            continue
        D.invoke(at, CH["AirdropTracker"]["set_authorized_recorder"],
                 [val_hash(ch), val_bool(True)],
                 label=f"Tracker.authorize {KEY_TO_NAME.get(key, key)}")

    # --- XelisVaultMiner v12.1 ---
    mn = S["XelisVaultMiner"]
    D.invoke(mn, CH["XelisVaultMiner"]["set_vlt_contract"], [val_hash(vlt)],
             label="Miner.set_vlt_contract")
    D.invoke(mn, CH["XelisVaultMiner"]["set_vlt_asset"], [val_hash(vlt_asset)],
             label="Miner.set_vlt_asset")
    dele = _current("miner_delegation")
    if dele:
        D.invoke(mn, CH["XelisVaultMiner"]["set_delegation_contract"],
                 [val_hash(dele)], label="Miner.set_delegation")
    D.invoke(mn, CH["XelisVaultMiner"]["set_treasury"], [val_addr(treasury)],
             label="Miner.set_treasury")
    D.invoke(mn, CH["XelisVaultMiner"]["set_registry"], [val_hash(reg)],
             label="Miner.set_registry")
    D.invoke(mn, CH["XelisVaultMiner"]["register_service"],
             [val_u8(1), val_hash(S["StakedOracle"])],
             label="Miner.register_service(oracle)")
    D.invoke(mn, CH["XelisVaultMiner"]["set_heartbeat_interval"], [val_u64(900)],
             label="Miner.set_hb_interval(900)")
    D.invoke(mn, CH["XelisVaultMiner"]["set_heartbeat_timeout"], [val_u64(4000)],
             label="Miner.set_hb_timeout(4000)")
    D.invoke(mn, CH["XelisVaultMiner"]["set_airdrop_tracker"], [val_hash(at)],
             label="Miner.set_airdrop_tracker")

    # --- StakedOracle v12 ---
    so = S["StakedOracle"]
    D.invoke(so, CH["StakedOracle"]["set_miner_contract"], [val_hash(mn)],
             label="Oracle.set_miner_contract")
    D.invoke(so, CH["StakedOracle"]["set_registry"], [val_hash(reg)],
             label="Oracle.set_registry")
    D.invoke(so, CH["StakedOracle"]["add_feed_entry"],
             [val_str("XEL/USD"), val_hash("0" * 64), val_u8(8),
              val_u64(100000), val_u64(10000000000000)],
             max_gas=15_000_000, label="Oracle.add_feed XEL/USD")
    D.invoke(so, CH["StakedOracle"]["set_airdrop_tracker"], [val_hash(at)],
             label="Oracle.set_airdrop_tracker")

    # --- VaultChat v12 ---
    vc = S["VaultChat"]
    D.invoke(vc, CH["VaultChat"]["set_vlt_asset"], [val_hash(vlt_asset)],
             label="Chat.set_vlt_asset")
    D.invoke(vc, CH["VaultChat"]["set_treasury"], [val_addr(treasury)],
             label="Chat.set_treasury")
    D.invoke(vc, CH["VaultChat"]["set_miner_contract"], [val_hash(mn)],
             label="Chat.set_miner_contract")

    # --- Governor / GovernanceVault ---
    D.invoke(S["Governor"], CH["Governor"]["set_governance_vault"],
             [val_hash(S["GovernanceVault"])], label="Governor.set_gov_vault")
    D.invoke(S["Governor"], CH["Governor"]["set_timelock"],
             [val_hash(_current("timelock"))], label="Governor.set_timelock")

    # --- DeFi layer (PSM / VaultSwap / VE3 / Savings) ---
    psm = S["PSM"]
    D.invoke(psm, CH["PSM"]["set_xusd_contract"], [val_hash(xusd)],
             label="PSM.set_xusd")
    D.invoke(psm, CH["PSM"]["set_xusd_asset"], [val_hash(xusd_asset)],
             label="PSM.set_xusd_asset")
    D.invoke(psm, CH["PSM"]["set_oracle"], [val_hash(so)], label="PSM.set_oracle")
    D.invoke(psm, CH["PSM"]["set_treasury"], [val_addr(treasury)],
             label="PSM.set_treasury")

    vs = S["VaultSwapV2"]
    D.invoke(vs, CH["VaultSwapV2"]["set_oracle"], [val_hash(so)],
             label="VaultSwap.set_oracle")
    D.invoke(vs, CH["VaultSwapV2"]["set_registry"], [val_hash(reg)],
             label="VaultSwap.set_registry")

    ve3 = S["VaultEngineV3"]
    D.invoke(ve3, CH["VaultEngineV3"]["set_registry"], [val_hash(reg)],
             label="VE3.set_registry")
    D.invoke(ve3, CH["VaultEngineV3"]["set_xusd_contract"], [val_hash(xusd)],
             label="VE3.set_xusd")
    D.invoke(ve3, CH["VaultEngineV3"]["set_xusd_asset"], [val_hash(xusd_asset)],
             label="VE3.set_xusd_asset")
    D.invoke(ve3, CH["VaultEngineV3"]["set_treasury"], [val_addr(treasury)],
             label="VE3.set_treasury")

    sr = S["SavingsRate"]
    D.invoke(sr, CH["SavingsRate"]["set_registry"], [val_hash(reg)],
             label="Savings.set_registry")
    D.invoke(sr, CH["SavingsRate"]["set_xusd_asset"], [val_hash(xusd_asset)],
             label="Savings.set_xusd_asset")

    # xUSD minters/burners for the new PSM / VE3 / VaultSwap hashes
    xusd_c = _current("xusd")
    for who, role in [(psm, "minter"), (psm, "burner"),
                      (ve3, "minter"), (ve3, "burner"),
                      (vs, "minter"), (vs, "burner")]:
        entry = 18 if role == "minter" else 19
        D.invoke(xusd_c, entry, [val_hash(who), val_bool(True)],
                 label=f"xUSD.{role}({KEY_TO_NAME_inverse(who)})")
    # VLTToken: keep the miner as minter
    D.invoke(vlt, 7, [val_hash(mn), val_bool(True)], label="VLT.set_minter(miner)")

    # --- PrivacyMixer v3 ---
    pm = S["PrivacyMixer"]
    D.invoke(pm, CH["PrivacyMixer"]["set_registry"], [val_hash(reg)],
             label="Mixer.set_registry")
    D.invoke(pm, CH["PrivacyMixer"]["set_treasury"],
             [val_hash(_current("treasury_vault"))], label="Mixer.set_treasury")

    # --- Activate the airdrop wiring on EVERY upgraded contract ---
    for name, key in [("VaultChat", "vault_chat"), ("Governor", "governor"),
                      ("GovernanceVault", "governance_vault"),
                      ("PSM", "psm"), ("VaultSwapV2", "vault_swap"),
                      ("SavingsRate", "savings_rate"),
                      ("VaultEngineV3", "vault_engine"),
                      ("PrivacyMixer", "privacy_mixer")]:
        D.invoke(S[name], CH[name]["set_airdrop_tracker"], [val_hash(at)],
                 label=f"{name}.set_airdrop_tracker")

    log("PHASE C done — auto-recording is LIVE (verify with the Doctor).")


def KEY_TO_NAME_inverse(hash: str) -> str:
    for k, n in KEY_TO_NAME.items():
        if S.get(n) == hash:
            return n
    return hash[:12]


def phase_d(D: Deployer, old_tracker: str):
    log("=== PHASE D: airdrop state migration ===")
    at = S["AirdropTracker"]
    # 1. read the old tracker user list
    user_count = D.read(old_tracker, "uc")
    if not isinstance(user_count, int):
        log("Old tracker empty (uc not set) — nothing to migrate.")
        return
    log(f"Old tracker has {user_count} users")
    ZERO_ADDR = "xet:" + "0" * 60
    migrated = set(STATE.get("migrated_users", []))
    imported = 0
    for i in range(user_count):
        addr = D.read(old_tracker, f"ul_{i}")
        if not addr or str(addr) in migrated:
            continue
        addr = str(addr)
        up = D.read(old_tracker, f"user_{addr}")
        if not isinstance(up, list) or len(up) < 13:
            log(f"WARN: user struct unreadable for {addr[:16]}… — skipped")
            continue
        # struct: [mining, relayer, gov, chat, liq, bounty, comm, total_raw,
        #          total_w_bonus, days_active, last_active_day, mainnet,
        #          qualified, registered]
        def _u(x):
            return int(x) if isinstance(x, int) else 0
        mainnet = str(up[11]) if up[11] else ZERO_ADDR
        D.invoke(at, CH["AirdropTracker"]["import_user_state"],
                 [val_addr(addr), val_u64(_u(up[0])), val_u64(_u(up[1])),
                  val_u64(_u(up[2])), val_u64(_u(up[3])), val_u64(_u(up[4])),
                  val_u64(_u(up[5])), val_u64(_u(up[6])), val_u64(_u(up[9])),
                  val_addr(mainnet)],
                 max_gas=15_000_000,
                 label=f"migrate {addr[:14]}")
        migrated.add(addr)
        STATE["migrated_users"] = sorted(migrated)
        save()
        imported += 1
        time.sleep(1)
    log(f"Imported {imported} users.")

    # 2. finalize: recompute global totals (200 users per call)
    start = 0
    while True:
        r = D.invoke(at, CH["AirdropTracker"]["finalize_migration"],
                     [val_u64(start), val_u64(200)],
                     label=f"finalize_migration({start})")
        if r is None:
            # step already done — stop
            break
        start += 200
        if start >= user_count:
            break
    log("Migration complete. Verify: uc/tp/ct_* on the new tracker.")


def phase_e(D: Deployer):
    log("=== PHASE E: update repo runtime files ===")
    net = json.loads(NETWORK_PATH.read_text())
    for key, name in KEY_TO_NAME.items():
        if name in S:
            net["contracts"][key] = S[name]
    net["updated"] = time.strftime("%Y-%m-%d")
    net["version"] = "v12"
    NETWORK_PATH.write_text(json.dumps(net, indent=2) + "\n")
    log(f"network/testnet.json updated ({len(S)} new hashes).")
    log("NEXT STEPS (manual, see docs/UPGRADE_v12.md):")
    log("  1. Miners re-register: xvault > Miner tools > Register (6 users).")
    log("     (a new contract hash = fresh storage; stakes are refunded by")
    log("      deregister_miner on the OLD contract first if desired)")
    log("  2. Restart the oracle keeper: xvault-miner > p > start keeper.")
    log("  3. Restart the airdrop indexer daemon (PoW points continue to")
    log("     be injected by the admin injector; contract activity is now")
    log("     auto-recorded and no longer needs manual injection).")
    log("  4. Run the CLI Doctor to verify the wiring end-to-end.")


# ---------------------------------------------------------------------------
def _current(key: str):
    """Current hash for a network key from network/testnet.json."""
    try:
        net = json.loads(NETWORK_PATH.read_text())
        return net.get("contracts", {}).get(key)
    except Exception:
        return None


def _current_vlt_asset():
    try:
        return json.loads(NETWORK_PATH.read_text()).get("vlt_asset")
    except Exception:
        return None


def _current_xusd_asset():
    try:
        return json.loads(NETWORK_PATH.read_text()).get("xusd_asset")
    except Exception:
        return None


def _current_treasury_addr():
    """Admin address as treasury placeholder (same as the v12R config)."""
    env = os.environ.get("TREASURY_ADDRESS")
    if env:
        return env
    try:
        return Protocol().wallet.address()
    except Exception:
        raise RuntimeError(
            "Set TREASURY_ADDRESS env var (admin wallet address) "
            "or run with the wallet online.")


import os  # noqa: E402


def main():
    global S, STATE
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", required=True,
                    choices=["a", "b", "c", "d", "e", "all"])
    ap.add_argument("--old-tracker",
                    default=_current("airdrop_tracker"),
                    help="hash of the PREVIOUS AirdropTracker (for phase d)")
    ap.add_argument("--bytecode-dir", default=str(BYTECODE_DIR))
    args = ap.parse_args()

    global BYTECODE_DIR  # noqa: PLW0603
    BYTECODE_DIR = Path(args.bytecode_dir)

    STATE = load_state()
    S = STATE["contracts"]
    D = Deployer()

    phases = ["a", "b", "c", "d", "e"] if args.phase == "all" else [args.phase]
    for ph in phases:
        if ph == "a":
            phase_a(D)
        elif ph == "b":
            phase_b(D)
        elif ph == "c":
            phase_c(D)
        elif ph == "d":
            phase_d(D, args.old_tracker)
        elif ph == "e":
            phase_e(D)
    log("DONE.")


if __name__ == "__main__":
    main()
