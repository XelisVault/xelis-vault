#!/usr/bin/env python3
"""
============================================================================
 XELIS Vault — v12.1 UPGRADE SCRIPT (testnet)
============================================================================
Upgrades the 11 contracts changed in v12/v12.1 and migrates the airdrop state.

WHAT IT DOES (resumable, every step is idempotent and logged to
docs/upgrade_v12_state.json):

  PHASE A — Deploy the new bytecode (contract hash == deploy tx hash):
     AirdropTracker v12.1, XelisVaultMiner v12.1, StakedOracle v12,
     VaultChat v12.1, Governor v12, GovernanceVault v12, PSM v12,
     VaultSwapV2 v12, SavingsRate v12, VaultEngineV3 v12, PrivacyMixer v3.
     The new AirdropTracker v12.1 STARTS PAUSED (constructor) — if a
     non-paused bytecode is detected (older artifact), the script pauses it
     immediately (chunk 73).

  PHASE C — Post-deploy configuration of the FRESH contract storages
     (all setters are admin-only and work while the tracker is paused):
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

  PHASE D — Airdrop state migration (old tracker -> new tracker), WHILE THE
     NEW TRACKER IS STILL PAUSED AND NOT YET IN THE REGISTRY:
     - snapshots the old tracker state (uc, tp, ct_1..7);
     - imports every user via import_user_state (chunk 78) — points AND
       days_active AND last_active_day AND qualified flag AND mainnet address
       are preserved; users with unreadable structs are imported with safe
       defaults instead of being skipped;
     - the import loop is crash-safe: it resumes from the ON-CHAIN migration
       cursor (chunk 81 set_mig_cursor / key "mig"); re-imports are
       idempotent overwrites;
     - finalize_migration (chunk 79) recomputes the global totals — batches
       are driven by an on-chain cursor and a completion flag ("migd"), so
       re-running never double-counts and never zeroes the totals;
     - FAILS CLOSED: at the end the old tracker state is re-read and compared
       with the snapshot — if ANYTHING changed during the migration (new
       activity was recorded), the script aborts with an error and the
       registry cutover (phase B) must NOT run until phase D is re-run.

  PHASE B — Registry UPGRADE (entry 4) for each name -> new hash.
     Runs AFTER the migration: the new tracker holds the migrated state
     before any protocol contract starts resolving it.
     VaultSwapV2 is registered in the registry under TWO names (an alias
     created at v12R deploy time): BOTH "VaultSwap" AND "VaultSwapV2" are
     upgraded to the new hash.
     (ContractRegistry keeps prev_<Name> for rollback.)

  PHASE U — Unpause the new AirdropTracker (chunk 74) — THE LAST ON-CHAIN
     STEP of the migration. Crash-safe: the on-chain "pz" key is read first;
     if the tracker is already unpaused (e.g. the script crashed right after
     a successful on-chain unpause, before saving its local state), the step
     is skipped — it never unpauses twice.

  PHASE E — Update the repo runtime files:
     network/testnet.json, docs/deployment_state.json (hashes) — and prints
     the exact commands to re-register the 6 miners + restart the keeper.

CRITICAL ORDER (v12.1): A -> C -> D -> B -> U -> E.
`--phase all` runs exactly this order. When running phases manually, NEVER
run B (cutover) before D has completed, and ALWAYS run U right after B
(between them, protocol recorders resolve the new tracker which is paused —
their record_activity_cross calls silently no-op, points are not lost beyond
that short window).

USAGE (admin wallet, from the repo root):
    python3 deploy/upgrade_v12.py --phase a
    python3 deploy/upgrade_v12.py --phase c
    python3 deploy/upgrade_v12.py --phase d --old-tracker <hash>
    python3 deploy/upgrade_v12.py --phase b
    python3 deploy/upgrade_v12.py --phase u
    python3 deploy/upgrade_v12.py --phase e
    python3 deploy/upgrade_v12.py --phase all

Bytecode: compiled .hex files are read from --bytecode-dir (default: the
repo build/ directory), named deploy_<Name>.hex.
"""
from __future__ import annotations

import argparse
import json
import os
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
DEFAULT_BYTECODE_DIR = REPO / "build"

# The 11 contracts of this upgrade, in deployment order.
UPGRADE_CONTRACTS = [
    "AirdropTracker", "XelisVaultMiner", "StakedOracle", "VaultChat",
    "Governor", "GovernanceVault", "PSM", "VaultSwapV2", "SavingsRate",
    "VaultEngineV3", "PrivacyMixer",
]

# Registry/artifact name for each network key. NOTE (v12.1 fix): the swap
# artifact is VaultSwapV2 — the previous script mapped "vault_swap" to
# "VaultSwap" which (a) never matched the deployed artifact key and (b)
# upgraded only ONE of the two registry names.
KEY_TO_NAME = {
    "airdrop_tracker": "AirdropTracker",
    "miner": "XelisVaultMiner",
    "staked_oracle": "StakedOracle",
    "vault_chat": "VaultChat",
    "governor": "Governor",
    "governance_vault": "GovernanceVault",
    "psm": "PSM",
    "vault_swap": "VaultSwapV2",
    "savings_rate": "SavingsRate",
    "vault_engine": "VaultEngineV3",
    "privacy_mixer": "PrivacyMixer",
}

# Registry names to upgrade for each network key. Default: the artifact name.
# The swap is registered on-chain under BOTH names (v12R alias), so both must
# point to the new hash after the cutover.
REGISTRY_NAMES = {
    "vault_swap": ["VaultSwap", "VaultSwapV2"],
}

# Chunks (source of truth: build/chunkmap_<Name>.txt, regenerated by
# scripts/compile_all.py after every recompile — append-only layout).
CH = {
    "ContractRegistry": {"upgrade": 4, "get": 16},
    "AirdropTracker": {
        "set_authorized_recorder": 68, "set_registry": 70,
        "set_timelock": 71, "set_guardian": 72, "set_vlt_contract": 69,
        "import_user_state": 78, "finalize_migration": 79,
        "set_mig_cursor": 81, "pause": 73, "unpause": 74,
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

# Update the on-chain migration cursor every N imports (crash-safe resume:
# at most N-1 idempotent re-imports after a crash).
MIG_CURSOR_EVERY = 20

ZERO_ADDR = "xet:" + "0" * 60


def load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text())
    return {"contracts": {}, "steps": [], "migrated_users": []}


S = None
STATE = None
BYTECODE_DIR = None


def save():
    STATE_PATH.write_text(json.dumps(STATE, indent=2, sort_keys=True))


def log(msg: str):
    print(f"[upgrade_v12] {msg}", flush=True)


def _to_int(v) -> int:
    return int(v) if isinstance(v, int) else 0


def _to_bool(v) -> bool:
    return v is True


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
                f"{hexfile} not found — compile the v12.1 contracts first "
                f"(scripts/compile_all.py, see docs/UPGRADE_v12.md §2).")
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
    log("=== PHASE A: deploy the 11 v12.1 contracts ===")
    for name in UPGRADE_CONTRACTS:
        D.deploy(name)
    # Safety: the v12.1 AirdropTracker constructor stores pz=true. If an
    # older (non-paused) artifact was deployed, pause it right now.
    at = S["AirdropTracker"]
    pz = D.read(at, "pz")
    if pz is not True:
        log("WARN: tracker not paused at deploy (old bytecode?) — pausing now")
        D.invoke(at, CH["AirdropTracker"]["pause"], [],
                 label="pause tracker (safety)")
    else:
        log("New AirdropTracker is PAUSED at deploy (v12.1 default) — OK")


def phase_c(D: Deployer):
    log("=== PHASE C: post-deploy configuration (tracker still paused) ===")
    at = S["AirdropTracker"]
    reg = S.get("ContractRegistry") or _current("contract_registry")
    vlt = _current("vlt_token")
    vlt_asset = _current_vlt_asset()
    xusd = _current("xusd")
    xusd_asset = _current_xusd_asset()
    treasury = _current_treasury_addr()

    # --- AirdropTracker base config (setters are admin-only, no pause check)
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

    # --- VaultChat v12.1 ---
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

    log("PHASE C done — recorder wiring is configured. The new tracker is "
        "still PAUSED and NOT in the registry: auto-recording goes live only "
        "after phases B + U.")


def KEY_TO_NAME_inverse(hash: str) -> str:
    for k, n in KEY_TO_NAME.items():
        if S.get(n) == hash:
            return n
    return hash[:12]


def _old_snapshot(D: Deployer, old_tracker: str) -> dict:
    """Immutable reference of the old tracker state (fail-closed check)."""
    snap = {"uc": _to_int(D.read(old_tracker, "uc")),
            "tp": _to_int(D.read(old_tracker, "tp"))}
    for i in range(1, 8):
        snap[f"ct_{i}"] = _to_int(D.read(old_tracker, f"ct_{i}"))
    return snap


def phase_d(D: Deployer, old_tracker: str):
    log("=== PHASE D: airdrop state migration (new tracker still paused) ===")
    at = S["AirdropTracker"]
    old_tracker = str(old_tracker)
    log(f"old tracker: {old_tracker}")

    # 0. Snapshot the old state — the fail-closed reference.
    snap = _old_snapshot(D, old_tracker)
    stored = STATE.get("old_snapshot")
    if stored and stored != snap:
        log(f"WARN: old tracker moved since the last run "
            f"(stored={stored} now={snap}) — updating the reference; "
            f"make sure phase B has NOT run in between.")
    STATE["old_snapshot"] = snap
    save()
    user_count = snap["uc"]
    log(f"Snapshot: {user_count} users, tp={snap['tp']}")
    if user_count == 0:
        log("Old tracker empty — nothing to import, finalize anyway.")

    # 1. Import loop — resume from the ON-CHAIN migration cursor.
    cursor = _to_int(D.read(at, "mig"))
    migrated = set(STATE.get("migrated_users", []))
    imported = 0
    for i in range(cursor, user_count):
        addr = D.read(old_tracker, f"ul_{i}")
        if not addr:
            log(f"WARN: ul_{i} empty — slot skipped")
            continue
        addr = str(addr)
        up = D.read(old_tracker, f"user_{addr}")
        # struct: [mining, relayer, gov, chat, liq, bounty, comm, total_raw,
        #          total_w_bonus, days_active, last_active_day, mainnet,
        #          qualified, registered]
        if isinstance(up, list):
            n = len(up)
        else:
            n = 0
            log(f"WARN: user struct unreadable for {addr[:16]}… "
                f"— importing with safe defaults (registered, zero points)")
        mainnet = str(up[11]) if (n > 11 and up[11]) else ZERO_ADDR
        D.invoke(at, CH["AirdropTracker"]["import_user_state"],
                 [val_addr(addr),
                  val_u64(_to_int(up[0]) if n > 0 else 0),
                  val_u64(_to_int(up[1]) if n > 1 else 0),
                  val_u64(_to_int(up[2]) if n > 2 else 0),
                  val_u64(_to_int(up[3]) if n > 3 else 0),
                  val_u64(_to_int(up[4]) if n > 4 else 0),
                  val_u64(_to_int(up[5]) if n > 5 else 0),
                  val_u64(_to_int(up[6]) if n > 6 else 0),
                  val_u64(_to_int(up[9]) if n > 9 else 0),
                  val_u64(_to_int(up[10]) if n > 10 else 0),
                  val_bool(bool(up[12]) if n > 12 else False),
                  val_addr(mainnet)],
                 max_gas=15_000_000,
                 label=f"migrate[{i}] {addr[:14]}")
        migrated.add(addr)
        STATE["migrated_users"] = sorted(migrated)
        imported += 1
        # Crash-safe cursor: every MIG_CURSOR_EVERY imports (idempotent)
        if (i + 1) % MIG_CURSOR_EVERY == 0 or i + 1 == user_count:
            D.invoke(at, CH["AirdropTracker"]["set_mig_cursor"],
                     [val_u64(i + 1)], label=f"mig_cursor={i + 1}")
            STATE["migrated_users"] = sorted(migrated)
            save()
    log(f"Imported {imported} new users (cursor {cursor} -> {user_count}).")

    # 2. Finalize the global totals — on-chain cursor + completion flag.
    new_uc = _to_int(D.read(at, "uc"))
    max_batches = new_uc // 200 + 2
    for b in range(max_batches):
        if _to_bool(D.read(at, "migd")):
            log("Migration totals finalized (migd=true).")
            break
        D.invoke(at, CH["AirdropTracker"]["finalize_migration"],
                 [val_u64(200)], label=f"finalize_migration batch {b}")
    else:
        raise RuntimeError(
            "finalize_migration did not complete after "
            f"{max_batches} batches — investigate the new tracker storage")
    STATE["migration_finalized"] = True
    save()

    new_tp = _to_int(D.read(at, "tp"))
    log(f"New tracker: uc={new_uc}, tp={new_tp} (old tp={snap['tp']})")
    if new_uc and new_tp != snap["tp"]:
        log(f"WARN: tp differs (old {snap['tp']} vs new {new_tp}) — "
            f"check for manual deductions on the old tracker before cutover")

    # 3. FAIL CLOSED — the old tracker must NOT have changed during migration.
    snap2 = _old_snapshot(D, old_tracker)
    if snap2 != snap:
        raise RuntimeError(
            "FAIL CLOSED: the OLD tracker changed during the migration "
            f"({snap} -> {snap2}). New activity was recorded while the "
            "migration was running. DO NOT run phase B (cutover) yet: "
            "re-run phase D to re-import the updated state (re-imports are "
            "idempotent), then run phase B + U.")
    log("Old tracker state unchanged during migration — cutover is SAFE.")


def phase_b(D: Deployer):
    log("=== PHASE B: registry UPGRADE (entry 4) — AFTER migration ===")
    reg = S.get("ContractRegistry") or _current("contract_registry")
    if not reg:
        raise RuntimeError("ContractRegistry hash unknown")
    for key, name in KEY_TO_NAME.items():
        if name not in S:
            log(f"SKIP upgrade {name} (not deployed in this run)")
            continue
        target = S[name]
        # v12.1: upgrade EVERY registry name resolving to this contract
        # (VaultSwapV2 is registered under both "VaultSwap" and
        #  "VaultSwapV2" — the previous script upgraded only "VaultSwap").
        for reg_name in REGISTRY_NAMES.get(key, [name]):
            cur = D.read(reg, f"cur_{reg_name}")
            if str(cur) == target:
                log(f'SKIP upgrade "{reg_name}" (already current)')
                continue
            D.invoke(reg, 4, [val_str(reg_name), val_hash(target)],
                     max_gas=5_000_000, label=f'upgrade "{reg_name}"')
    log("Registry upgraded (incl. VaultSwap AND VaultSwapV2 aliases). "
        "prev_<Name> preserved for rollback (entry 5).")


def phase_u(D: Deployer):
    log("=== PHASE U: unpause the new AirdropTracker (final on-chain step) ===")
    at = S["AirdropTracker"]
    pz = D.read(at, "pz")
    if pz in (False, None):
        log("SKIP unpause — tracker already unpaused on-chain "
            "(crash-safe: never unpauses twice).")
        return
    D.invoke(at, CH["AirdropTracker"]["unpause"], [], label="unpause tracker")
    # verify
    pz = D.read(at, "pz")
    if pz not in (False, None):
        raise RuntimeError("tracker still paused after unpause — check the tx")
    STATE["unpaused"] = True
    save()
    log("Tracker is LIVE — auto-recording is now active. "
        "Verify with the CLI Doctor.")


def phase_e(D: Deployer):
    log("=== PHASE E: update repo runtime files ===")
    net = json.loads(NETWORK_PATH.read_text())
    for key, name in KEY_TO_NAME.items():
        if name in S:
            net["contracts"][key] = S[name]
    net["updated"] = time.strftime("%Y-%m-%d")
    net["version"] = "v12.1"
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


def main():
    global S, STATE, BYTECODE_DIR
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", required=True,
                    choices=["a", "b", "c", "d", "e", "u", "all"])
    ap.add_argument("--old-tracker",
                    default=_current("airdrop_tracker"),
                    help="hash of the PREVIOUS AirdropTracker (for phase d)")
    ap.add_argument("--bytecode-dir", default=str(DEFAULT_BYTECODE_DIR),
                    help="directory containing deploy_<Name>.hex "
                         "(default: repo build/)")
    args = ap.parse_args()

    BYTECODE_DIR = Path(args.bytecode_dir)

    STATE = load_state()
    S = STATE["contracts"]
    D = Deployer()

    # v12.1 CRITICAL ORDER: deploy -> configure -> migrate -> cutover ->
    # unpause -> repo files. NEVER run B before D.
    phases = (["a", "c", "d", "b", "u", "e"]
              if args.phase == "all" else [args.phase])
    for ph in phases:
        if ph == "a":
            phase_a(D)
        elif ph == "b":
            phase_b(D)
        elif ph == "c":
            phase_c(D)
        elif ph == "d":
            phase_d(D, args.old_tracker)
        elif ph == "u":
            phase_u(D)
        elif ph == "e":
            phase_e(D)
    log("DONE.")


if __name__ == "__main__":
    main()
