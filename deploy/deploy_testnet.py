#!/usr/bin/env python3
"""
============================================================================
 XELIS Vault v5.0 — Testnet Deployment Script
============================================================================

Automated deployment of all 33 XELIS Vault v5.0 contracts to the XELIS
testnet, in canonical dependency order:

    1.  ContractRegistry        (proxy/proxy)
    2.  VLTToken                (token — mints VLT asset via entry 5)
    3.  XelisVaultMiner         (miner — needs VLT asset)
    4.  StakedOracle            (oracle — needs Miner + VLT)
    5.  xUSD                    (stablecoin)
    6.  VaultEngineV3           (CDP — needs Oracle + xUSD)
    7.  PSM                     (peg stability — needs Oracle + xUSD)
    8.  VaultSwapV2             (AMM — needs Oracle + xUSD)
    9.  GovernanceVault         (VLT staking with lock boost)
    10. Governor                (proposal engine)
    11. Timelock                (governance delay)
    12. GuardianMultisig        (emergency control)
    13. OracleGovernance        (oracle governance)
    14. FlashLoan               (uncollateralized 1-tx loans)
    15. FlashCallback           (flash callback iface)
    16. SealedBidAuction        (RWA commit/reveal auction)
    17. PrivacyMixer            (ZK anonymity)
    18. VaultChat               (encrypted chat)
    19. SavingsRate             (xUSD savings)
    20. InsurancePool           (XEL-staked coverage)
    21. PrivateInsurance        (insurance variant)
    22. InterestRateModel       (utilization curve for LendingMarket)
    23. LendingMarket           (multi-asset pool)
    24. PeerLoan                (P2P lending)
    25. SyndicatePool           (syndicated loans)
    26. RevenueShare            (VLT revenue split)
    27. FaucetContract          (testnet faucet)
    28. TreasuryVault           (protocol treasury)
    29. Payroll                 (recurring payments)
    30. AssetVault              (RWA vault)
    31. ComplianceModule        (compliance layer)
    32. MinerPool               (miner pool composable)
    33. Upgradeable             (proxy pattern helper)

After deploying, this script:
  - Wires each contract: set_registry, set_vlt_contract, set_vlt_asset,
    set_treasury, set_miner_contract, set_oracle, set_governance_vault,
    set_timelock, set_guardian, set_guardian_contract, set_minter,
    set_burner, register_service, etc.
  - Registers all contracts in ContractRegistry via entry ID 1 (register)
  - Authorizes StakedOracle, VaultEngine, PSM, VaultSwap, etc. as
    VLTToken / xUSD minters/burners via VLTToken entry 3 (set_minter)
    and entry 4 (set_burner)
  - Initializes first oracle feed: add_feed("XEL/USD", Hash::zero(),
    8, 100000, 10000000000000) — StakedOracle entry ID 0
  - Distributes initial VLT via VLTToken entry 2 (mint_batch)
  - Prints a deployment summary
  - Saves everything to ~/.xelis-vault/config/deployment.json

PRIVACY:
  - NEVER logs private keys or mnemonics. Only contract hashes + addresses.
  - The signer name is logged (e.g. "deployer"), not the wallet's private
    key.

USAGE:
    python3 deploy_testnet.py --signer deployer \\
        --team xet1TEAM --treasury xet1TREAS \\
        --airdrop xet1AIRDROP --bug-bounty xet1BUGS
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Optional

try:
    import requests
except ImportError:
    print("ERROR: 'requests' library not installed. Run: pip3 install requests",
          file=sys.stderr)
    sys.exit(1)

# ============================================================================
# CONFIGURATION
# ============================================================================
CONFIG = {
    "rpc_url":         os.environ.get("XELIS_RPC", "http://127.0.0.1:8080"),
    "network":         os.environ.get("XELIS_NETWORK", "testnet"),
    "signer":          os.environ.get("DEPLOYER_SIGNER", "deployer"),
    "team_address":    os.environ.get("TEAM_ADDRESS", ""),
    "treasury_address":os.environ.get("TREASURY_ADDRESS", ""),
    "airdrop_address": os.environ.get("AIRDROP_ADDRESS", ""),
    "bug_bounty_address": os.environ.get("BUG_BOUNTY_ADDRESS", ""),
    "dex_address":     os.environ.get("DEX_LIQUIDITY_ADDRESS", ""),
    "contracts_dir":   os.environ.get("CONTRACTS_DIR",
                                      str(Path(__file__).resolve().parent.parent
                                          / "contracts")),
    "output_file":     os.environ.get("OUTPUT_FILE", ""),
}

# VLT allocation — must sum to 10,000,000 VLT (1e15 atomic @ 8 decimals)
VLT_ALLOCATION = {
    "oracle_rewards":  6_000_000 * 10**8,  # 60% to StakedOracle
    "team":            1_500_000 * 10**8,  # 15% to team
    "treasury":        1_200_000 * 10**8,  # 12% to treasury
    "dex_liquidity":   1_000_000 * 10**8,  # 10% to DEX
    "airdrop":           200_000 * 10**8,  # 2%  to airdrop
    "bug_bounty":        100_000 * 10**8,  # 1%  to bug bounty
}

XEL_ZERO_HASH = "0x" + "0" * 64

# Canonical list of 33 contracts in deployment order.
# (logical_name, subdir, filename_stem)
CONTRACTS_IN_ORDER = [
    ("ContractRegistry",  "proxy",       "ContractRegistry"),
    ("VLTToken",          "token",       "VLTToken"),
    ("XelisVaultMiner",   "miner",       "XelisVaultMiner"),
    ("StakedOracle",      "oracle",      "StakedOracle"),
    ("xUSD",              "usd",         "xUSD"),
    ("VaultEngine",       "vault",       "VaultEngineV3"),
    ("PSM",               "amm",         "PSM"),
    ("VaultSwap",         "amm",         "VaultSwapV2"),
    ("GovernanceVault",   "governance",  "GovernanceVault"),
    ("Governor",          "governance",  "Governor"),
    ("Timelock",          "governance",  "Timelock"),
    ("GuardianMultisig",  "governance",  "GuardianMultisig"),
    ("OracleGovernance",  "governance",  "OracleGovernance"),
    ("FlashLoan",         "flashloan",   "FlashLoan"),
    ("FlashCallback",     "flashloan",   "FlashCallback"),
    ("SealedBidAuction",  "auction",     "SealedBidAuction"),
    ("PrivacyMixer",      "privacy",     "PrivacyMixer"),
    ("VaultChat",         "chat",        "VaultChat"),
    ("SavingsRate",       "savings",     "SavingsRate"),
    ("InsurancePool",     "insurance",   "InsurancePool"),
    ("PrivateInsurance",  "insurance",   "PrivateInsurance"),
    ("InterestRateModel", "interest",    "InterestRateModel"),
    ("LendingMarket",     "lending",     "LendingMarket"),
    ("PeerLoan",          "lending",     "PeerLoan"),
    ("SyndicatePool",     "lending",     "SyndicatePool"),
    ("RevenueShare",      "revenue",     "RevenueShare"),
    ("FaucetContract",    "faucet",      "FaucetContract"),
    ("TreasuryVault",     "treasury",    "TreasuryVault"),
    ("Payroll",           "payroll",     "Payroll"),
    ("AssetVault",        "rwa",         "AssetVault"),
    ("ComplianceModule",  "compliance",  "ComplianceModule"),
    ("MinerPool",         "miner",       "MinerPool"),
    ("Upgradeable",       "proxy",       "Upgradeable"),
]

# ============================================================================
# v5.0 ENTRY IDs (canonical)
# ============================================================================
# ContractRegistry (entry IDs)
CR_GET             = 0   # (name) -> Hash
CR_REGISTER        = 1   # (name, contract_hash)
CR_UPGRADE         = 2   # (name, new_hash)
CR_ROLLBACK        = 3   # (name)
# 4-7: list_names_entry, get_name_at_entry, get_version_entry, get_previous_entry
# 8-11: set_timelock, transfer_admin, set_emergency, get_version_str
# 12-13: request_emergency_withdraw, execute_emergency_withdraw

# VLTToken (entry IDs)
VLT_MINT_TO            = 0   # (to, amount)
VLT_BURN_OWN           = 1   # (amount)
VLT_MINT_BATCH         = 2   # (recipients, amounts)
VLT_SET_MINTER         = 3   # (contract_hash, enabled)
VLT_SET_BURNER         = 4   # (contract_hash, enabled)
VLT_CREATE_ASSET       = 5   # ()
# 6-10: set_registry, set_timelock, transfer_admin, set_emergency, get_version
VLT_GET_ASSET_HASH     = 11  # () -> Hash
VLT_GET_MAX_SUPPLY     = 12
VLT_GET_TOTAL_BURNED   = 13
VLT_GET_CIRC_SUPPLY    = 14

# XelisVaultMiner (entry IDs — see scripts/xelis_vault_miner.py for full list)
XVM_REGISTER_MINER            = 0
XVM_REGISTER_SERVICE          = 16
XVM_SET_VLT_CONTRACT          = 25
XVM_SET_VLT_ASSET             = 26
XVM_SET_TREASURY              = 27
XVM_SET_REGISTRY              = 28
XVM_SET_TIMELOCK              = 29
XVM_SET_GUARDIAN              = 30
XVM_SET_EMERGENCY             = 31

# StakedOracle (entry IDs — see scripts/price_provider.py for full list)
ORACLE_ADD_FEED                = 0   # (name, asset, decimals, min, max)
ORACLE_SET_MINER_CONTRACT      = 21
ORACLE_SET_REGISTRY            = 22
ORACLE_SET_TIMELOCK            = 23
ORACLE_SET_GUARDIAN            = 24
ORACLE_SET_EMERGENCY           = 25

# ============================================================================
# LOGGING
# ============================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("deploy")


# ============================================================================
# XELIS RPC CLIENT
# ============================================================================
class XelisClient:
    def __init__(self, rpc_url: str, signer: str) -> None:
        self.rpc_url = rpc_url
        self.signer = signer
        self._id = 0

    def _call(self, method: str, params: Optional[dict] = None) -> Any:
        self._id += 1
        payload = {
            "method": method,
            "params": params or {},
            "jsonrpc": "2.0",
            "id": self._id,
        }
        try:
            r = requests.post(self.rpc_url, json=payload, timeout=60)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            log.error(f"RPC call failed ({method}): {e}")
            raise
        if "error" in data and data["error"]:
            raise RuntimeError(f"RPC error: {data['error']}")
        return data.get("result", {})

    def get_topoheight(self) -> int:
        return int(self._call("get_topoheight"))

    def is_synced(self) -> bool:
        return bool(self._call("get_info").get("synced", False))

    # ---- deployment helpers ----
    def deploy_contract(self, compiled_path: str) -> str:
        """Deploy a compiled contract. Returns the new contract hash."""
        if not Path(compiled_path).exists():
            # Try .slx as fallback
            slx_path = compiled_path.replace(".compiled", ".slx")
            if Path(slx_path).exists():
                compiled_path = slx_path
            else:
                raise FileNotFoundError(
                    f"Compiled contract not found: {compiled_path}"
                )
        with open(compiled_path, "rb") as f:
            code = f.read().hex()
        result = self._call("submit_transaction", {
            "tx_type": "DeployContract",
            "code": code,
            "signer": self.signer,
        })
        tx_hash = result.get("hash") if isinstance(result, dict) else None
        if not tx_hash:
            raise RuntimeError(f"Deploy returned no tx hash: {result}")
        # Wait for confirmation
        time.sleep(6)
        receipt = self._call("get_transaction", {"hash": tx_hash})
        contract_hash = receipt.get("contract_hash")
        if not contract_hash:
            raise RuntimeError(f"Deploy tx confirmed but no contract hash: "
                               f"{receipt}")
        return contract_hash

    def call_entry(
        self,
        contract: str,
        entry_id: int,
        args: list[Any],
        deposits: Optional[list[dict]] = None,
    ) -> str:
        """Call a contract entry by numeric ID. Returns tx hash."""
        params: dict[str, Any] = {
            "tx_type": "CallContract",
            "contract": contract,
            "entry_id": entry_id,
            "args": [str(a) for a in args],
            "signer": self.signer,
        }
        if deposits:
            params["deposits"] = deposits
        result = self._call("submit_transaction", params)
        tx_hash = result.get("hash") if isinstance(result, dict) else None
        if not tx_hash:
            raise RuntimeError(f"Call returned no hash: {result}")
        return tx_hash

    def call_named(
        self,
        contract: str,
        entry: str,
        args: list[Any],
        deposits: Optional[list[dict]] = None,
    ) -> str:
        """Call a contract entry by name (used as fallback for older daemons)."""
        params: dict[str, Any] = {
            "tx_type": "CallContract",
            "contract": contract,
            "entry": entry,
            "args": [str(a) for a in args],
            "signer": self.signer,
        }
        if deposits:
            params["deposits"] = deposits
        result = self._call("submit_transaction", params)
        tx_hash = result.get("hash") if isinstance(result, dict) else None
        if not tx_hash:
            raise RuntimeError(f"Call returned no hash: {result}")
        return tx_hash

    def read_entry(self, contract: str, entry_id: int,
                   args: Optional[list[Any]] = None) -> Any:
        return self._call("call_contract_read", {
            "contract": contract,
            "entry_id": entry_id,
            "args": [str(a) for a in (args or [])],
        })

    def read_named(self, contract: str, entry: str,
                   args: Optional[list[Any]] = None) -> Any:
        return self._call("call_contract_read", {
            "contract": contract,
            "entry": entry,
            "args": [str(a) for a in (args or [])],
        })

    def wait_for_tx(self, tx_hash: str, timeout: int = 60) -> bool:
        start = time.time()
        while time.time() - start < timeout:
            try:
                self._call("get_transaction", {"hash": tx_hash})
                return True
            except Exception:
                time.sleep(2)
        log.warning(f"Tx {tx_hash} not confirmed after {timeout}s")
        return False


# ============================================================================
# DEPLOYMENT STEPS
# ============================================================================
def check_prerequisites(client: XelisClient) -> None:
    log.info("Checking prerequisites...")
    if not client.is_synced():
        log.error("Daemon is not synced. Wait for sync before deploying.")
        sys.exit(1)
    log.info(f"✓ Daemon synced (topoheight={client.get_topoheight()})")
    required = ["team_address", "treasury_address", "airdrop_address",
                "bug_bounty_address", "dex_address"]
    for key in required:
        if not CONFIG[key]:
            log.error(f"Missing {key} (env var or --flag required)")
            sys.exit(1)
    log.info("✓ All allocation addresses configured")
    cdir = Path(CONFIG["contracts_dir"])
    if not cdir.exists():
        log.error(f"Contracts dir not found: {cdir}")
        sys.exit(1)
    log.info(f"✓ Contracts dir: {cdir}")


def deploy_all_contracts(client: XelisClient) -> dict[str, str]:
    """Deploy all 33 contracts in canonical order. Returns {name: hash}."""
    deployed: dict[str, str] = {}
    cdir = Path(CONFIG["contracts_dir"])
    log.info(f"Deploying {len(CONTRACTS_IN_ORDER)} contracts in order...")
    for name, subdir, stem in CONTRACTS_IN_ORDER:
        # Try .compiled first, fall back to .slx
        compiled = cdir / subdir / f"{stem}.compiled"
        if not compiled.exists():
            compiled = cdir / subdir / f"{stem}.slx"
        if not compiled.exists():
            log.error(f"Missing: {compiled}")
            sys.exit(1)
        try:
            contract_hash = client.deploy_contract(str(compiled))
            deployed[name] = contract_hash
            log.info(f"  ✓ {name:<22} → {contract_hash}")
        except Exception as e:
            log.error(f"  ✗ Failed to deploy {name}: {e}")
            sys.exit(1)
    return deployed


def create_assets(client: XelisClient, deployed: dict[str, str]) -> dict[str, str]:
    """Create VLT and xUSD assets; return {logical_name: asset_hash}."""
    assets: dict[str, str] = {}
    # VLT asset (VLTToken entry ID 5: create_asset)
    log.info("Creating VLT asset (VLTToken.create_asset)...")
    tx = client.call_entry(deployed["VLTToken"], VLT_CREATE_ASSET, [])
    client.wait_for_tx(tx)
    vlt_asset = client.read_entry(deployed["VLTToken"], VLT_GET_ASSET_HASH)
    assets["VLT"] = vlt_asset
    log.info(f"  ✓ VLT asset: {vlt_asset}")
    # xUSD asset — assume same entry ID 5 for create_asset (matches v5.0
    # token pattern). Adjust if xUSD's entry IDs differ.
    log.info("Creating xUSD asset (xUSD.create_asset)...")
    try:
        tx = client.call_entry(deployed["xUSD"], VLT_CREATE_ASSET, [])
        client.wait_for_tx(tx)
        xusd_asset = client.read_entry(deployed["xUSD"], VLT_GET_ASSET_HASH)
        assets["xUSD"] = xusd_asset
        log.info(f"  ✓ xUSD asset: {xusd_asset}")
    except Exception as e:
        log.warning(f"Could not create xUSD asset (entry 5): {e}")
        log.warning("You may need to create it manually with the correct entry ID.")
    return assets


def wire_contracts(
    client: XelisClient,
    deployed: dict[str, str],
    assets: dict[str, str],
) -> None:
    """Wire all contracts together via their set_* entry IDs."""
    log.info("Wiring contracts together...")
    vlt_contract = deployed["VLTToken"]
    vlt_asset    = assets["VLT"]
    xusd_contract = deployed["xUSD"]
    xusd_asset    = assets.get("xUSD", "")
    treasury     = CONFIG["treasury_address"]
    miner_contract = deployed["XelisVaultMiner"]
    oracle       = deployed["StakedOracle"]
    registry     = deployed["ContractRegistry"]
    timelock     = deployed["Timelock"]
    guardian     = deployed["GuardianMultisig"]
    gov_vault    = deployed["GovernanceVault"]
    governor     = deployed["Governor"]
    vault_engine = deployed["VaultEngine"]
    psm          = deployed["PSM"]
    vault_swap   = deployed["VaultSwap"]

    def call(contract: str, entry_id: int, args: list[Any]) -> None:
        try:
            tx = client.call_entry(contract, entry_id, args)
            client.wait_for_tx(tx)
            log.info(f"  ✓ {contract[:10]}... entry {entry_id} -> ok")
        except Exception as e:
            log.warning(f"  ! {contract[:10]}... entry {entry_id}: {e}")

    # ContractRegistry self-register
    call(registry, CR_REGISTER, ["ContractRegistry", registry])

    # VLTToken: set_registry
    # (VLTToken entry 6 = set_registry in v5.0 — see ENTRY_IDS.md)
    call(vlt_contract, 6, [registry])

    # XelisVaultMiner wiring (entry IDs from canonical table)
    call(miner_contract, XVM_SET_VLT_CONTRACT, [vlt_contract])
    call(miner_contract, XVM_SET_VLT_ASSET,    [vlt_asset])
    call(miner_contract, XVM_SET_TREASURY,     [treasury])
    call(miner_contract, XVM_SET_REGISTRY,     [registry])
    call(miner_contract, XVM_SET_TIMELOCK,     [timelock])
    call(miner_contract, XVM_SET_GUARDIAN,     [guardian])
    call(miner_contract, XVM_SET_EMERGENCY,    [guardian])
    # Authorize oracle + chat as service contracts (register_service, entry 16)
    call(miner_contract, XVM_REGISTER_SERVICE, [1, oracle])
    if "VaultChat" in deployed:
        call(miner_contract, XVM_REGISTER_SERVICE, [2, deployed["VaultChat"]])

    # StakedOracle wiring
    call(oracle, ORACLE_SET_MINER_CONTRACT, [miner_contract])
    call(oracle, ORACLE_SET_REGISTRY,       [registry])
    call(oracle, ORACLE_SET_TIMELOCK,       [timelock])
    call(oracle, ORACLE_SET_GUARDIAN,       [guardian])
    call(oracle, ORACLE_SET_EMERGENCY,      [guardian])

    # Authorize StakedOracle as VLT minter (VLTToken entry 3: set_minter)
    call(vlt_contract, VLT_SET_MINTER, [oracle, True])
    # Authorize XelisVaultMiner as VLT minter too (it mints chat rewards)
    call(vlt_contract, VLT_SET_MINTER, [miner_contract, True])

    # xUSD: set_minter / set_burner for VaultEngine, PSM, VaultSwap
    if xusd_asset:
        for c in [vault_engine, psm, vault_swap]:
            call(xusd_contract, VLT_SET_MINTER, [c, True])
            call(xusd_contract, VLT_SET_BURNER, [c, True])

    # VaultEngine wiring — uses named entries (set by contract author)
    for entry, args in [
        ("set_registry",    [registry]),
        ("set_treasury",    [treasury]),
        ("set_xusd_contract", [xusd_contract]),
        ("set_xusd_asset",  [xusd_asset]),
        ("set_oracle",      [oracle]),
    ]:
        try:
            tx = client.call_named(vault_engine, entry, args)
            client.wait_for_tx(tx)
            log.info(f"  ✓ VaultEngine.{entry} -> ok")
        except Exception as e:
            log.warning(f"  ! VaultEngine.{entry}: {e}")

    # PSM wiring
    for entry, args in [
        ("set_xusd_contract", [xusd_contract]),
        ("set_xusd_asset",    [xusd_asset]),
        ("set_oracle",        [oracle]),
        ("set_treasury",      [treasury]),
        ("set_registry",      [registry]),
    ]:
        try:
            tx = client.call_named(psm, entry, args)
            client.wait_for_tx(tx)
            log.info(f"  ✓ PSM.{entry} -> ok")
        except Exception as e:
            log.warning(f"  ! PSM.{entry}: {e}")

    # VaultSwap wiring
    for entry, args in [
        ("set_registry",    [registry]),
        ("set_treasury",    [treasury]),
        ("set_xusd_asset",  [xusd_asset]),
        ("set_xusd_contract", [xusd_contract]),
        ("set_oracle",      [oracle]),
    ]:
        try:
            tx = client.call_named(vault_swap, entry, args)
            client.wait_for_tx(tx)
            log.info(f"  ✓ VaultSwap.{entry} -> ok")
        except Exception as e:
            log.warning(f"  ! VaultSwap.{entry}: {e}")

    # GovernanceVault wiring
    for entry, args in [
        ("set_vlt_contract", [vlt_contract]),
        ("set_vlt_asset",    [vlt_asset]),
        ("set_registry",     [registry]),
        ("set_timelock",     [timelock]),
        ("set_governor",     [governor]),
    ]:
        try:
            tx = client.call_named(gov_vault, entry, args)
            client.wait_for_tx(tx)
            log.info(f"  ✓ GovernanceVault.{entry} -> ok")
        except Exception as e:
            log.warning(f"  ! GovernanceVault.{entry}: {e}")

    # Governor wiring
    for entry, args in [
        ("set_governance_vault", [gov_vault]),
        ("set_timelock",         [timelock]),
        ("set_guardian",         [guardian]),
        ("set_registry",         [registry]),
    ]:
        try:
            tx = client.call_named(governor, entry, args)
            client.wait_for_tx(tx)
            log.info(f"  ✓ Governor.{entry} -> ok")
        except Exception as e:
            log.warning(f"  ! Governor.{entry}: {e}")

    # Timelock wiring
    for entry, args in [
        ("set_guardian_contract", [guardian]),
        ("set_governor",          [governor]),
        ("set_registry",          [registry]),
    ]:
        try:
            tx = client.call_named(timelock, entry, args)
            client.wait_for_tx(tx)
            log.info(f"  ✓ Timelock.{entry} -> ok")
        except Exception as e:
            log.warning(f"  ! Timelock.{entry}: {e}")

    # GuardianMultisig wiring
    for entry, args in [
        ("set_timelock",  [timelock]),
        ("set_registry",  [registry]),
    ]:
        try:
            tx = client.call_named(guardian, entry, args)
            client.wait_for_tx(tx)
            log.info(f"  ✓ GuardianMultisig.{entry} -> ok")
        except Exception as e:
            log.warning(f"  ! GuardianMultisig.{entry}: {e}")

    # OracleGovernance wiring
    for entry, args in [
        ("set_oracle",         [oracle]),
        ("set_governance_vault", [gov_vault]),
        ("set_registry",       [registry]),
    ]:
        try:
            tx = client.call_named(deployed["OracleGovernance"], entry, args)
            client.wait_for_tx(tx)
            log.info(f"  ✓ OracleGovernance.{entry} -> ok")
        except Exception as e:
            log.warning(f"  ! OracleGovernance.{entry}: {e}")

    # FaucetContract wiring
    for entry, args in [
        ("set_vlt_asset",    [vlt_asset]),
        ("set_vlt_contract", [vlt_contract]),
    ]:
        try:
            tx = client.call_named(deployed["FaucetContract"], entry, args)
            client.wait_for_tx(tx)
            log.info(f"  ✓ FaucetContract.{entry} -> ok")
        except Exception as e:
            log.warning(f"  ! FaucetContract.{entry}: {e}")

    log.info("✓ Contract wiring complete")


def register_all_in_registry(
    client: XelisClient,
    deployed: dict[str, str],
) -> None:
    """Register every deployed contract in ContractRegistry (entry ID 1)."""
    log.info(f"Registering {len(deployed)} contracts in ContractRegistry...")
    registry = deployed["ContractRegistry"]
    for name, hash_val in deployed.items():
        if name == "ContractRegistry":
            continue  # already self-registered
        try:
            tx = client.call_entry(registry, CR_REGISTER, [name, hash_val])
            client.wait_for_tx(tx)
            log.info(f"  ✓ Registered {name}")
        except Exception as e:
            log.warning(f"  ! Could not register {name}: {e}")


def add_initial_feed(client: XelisClient, deployed: dict[str, str]) -> None:
    """Add XEL/USD feed: add_feed(name, asset, decimals, min, max)."""
    log.info("Adding XEL/USD feed (StakedOracle.add_feed, entry ID 0)...")
    oracle = deployed["StakedOracle"]
    # name="XEL/USD", asset=zero (native XEL), decimals=8,
    # min=100000 ($0.001), max=10000000000000 ($100,000)
    try:
        tx = client.call_entry(oracle, ORACLE_ADD_FEED,
                               ["XEL/USD", XEL_ZERO_HASH, 8, 100000, 10000000000000])
        client.wait_for_tx(tx)
        log.info("  ✓ XEL/USD feed added (feed_id = 0)")
    except Exception as e:
        log.warning(f"  ! Could not add XEL/USD feed: {e}")


def distribute_vlt(
    client: XelisClient,
    deployed: dict[str, str],
    assets: dict[str, str],
) -> None:
    """Distribute initial 10M VLT via VLTToken.mint_batch (entry ID 2)."""
    log.info("Distributing initial 10M VLT via VLTToken.mint_batch...")
    vlt_contract = deployed["VLTToken"]
    recipients = [
        deployed["StakedOracle"],          # oracle rewards (60%)
        CONFIG["team_address"],            # team (15%)
        CONFIG["treasury_address"],        # treasury (12%)
        CONFIG["dex_address"],             # DEX liquidity (10%)
        CONFIG["airdrop_address"],         # airdrop (2%)
        CONFIG["bug_bounty_address"],      # bug bounty (1%)
    ]
    amounts = [
        VLT_ALLOCATION["oracle_rewards"],
        VLT_ALLOCATION["team"],
        VLT_ALLOCATION["treasury"],
        VLT_ALLOCATION["dex_liquidity"],
        VLT_ALLOCATION["airdrop"],
        VLT_ALLOCATION["bug_bounty"],
    ]
    try:
        tx = client.call_entry(vlt_contract, VLT_MINT_BATCH,
                               [recipients, amounts])
        client.wait_for_tx(tx)
        log.info("  ✓ mint_batch complete")
        # Verify total supply
        supply = client.read_entry(vlt_contract, VLT_GET_CIRC_SUPPLY)
        expected = sum(VLT_ALLOCATION.values())
        actual = int(supply) if supply else 0
        log.info(f"  ✓ VLT circulating supply: {actual / 1e8:.0f} VLT "
                 f"(expected {expected / 1e8:.0f})")
    except Exception as e:
        log.error(f"  ✗ mint_batch failed: {e}")
        log.error("Falling back to individual mint_to (entry 0) calls...")
        for label, addr, amount in zip(
            ["oracle_rewards", "team", "treasury", "dex", "airdrop", "bug_bounty"],
            recipients, amounts,
        ):
            try:
                tx = client.call_entry(vlt_contract, VLT_MINT_TO,
                                       [addr, amount])
                client.wait_for_tx(tx)
                log.info(f"  ✓ mint_to {label}: {amount / 1e8:.0f} VLT")
            except Exception as e2:
                log.error(f"  ✗ mint_to {label} failed: {e2}")


def refill_faucet(
    client: XelisClient,
    deployed: dict[str, str],
) -> None:
    """Refill the testnet faucet with XEL and VLT."""
    log.info("Refilling FaucetContract for testnet use...")
    faucet = deployed["FaucetContract"]
    # 10,000 XEL testnet to faucet
    try:
        tx = client.call_named(faucet, "refill_xel", [10_000 * 10**8],
            deposits=[{XEL_ZERO_HASH: str(10_000 * 10**8)}])
        client.wait_for_tx(tx)
        log.info("  ✓ Refilled 10,000 XEL to faucet")
    except Exception as e:
        log.warning(f"  ! Could not refill XEL: {e}")
    # 50,000 VLT to faucet
    try:
        tx = client.call_entry(deployed["VLTToken"], VLT_MINT_TO,
                               [faucet, 50_000 * 10**8])
        client.wait_for_tx(tx)
        log.info("  ✓ Minted 50,000 VLT to faucet")
    except Exception as e:
        log.warning(f"  ! Could not mint VLT to faucet: {e}")


def verify_deployment(
    client: XelisClient,
    deployed: dict[str, str],
    assets: dict[str, str],
) -> None:
    log.info("Verifying deployment...")
    # VLT supply
    supply = client.read_entry(deployed["VLTToken"], VLT_GET_CIRC_SUPPLY)
    actual = int(supply) if supply else 0
    if actual == sum(VLT_ALLOCATION.values()):
        log.info(f"  ✓ VLT supply correct ({actual / 1e8:.0f} VLT)")
    else:
        log.warning(f"  ! VLT supply mismatch: got {actual / 1e8:.0f}, "
                    f"expected {sum(VLT_ALLOCATION.values()) / 1e8:.0f}")
    # StakedOracle version
    try:
        version = client.read_entry(deployed["StakedOracle"], 27)  # get_version
        log.info(f"  ✓ StakedOracle version: {version}")
    except Exception:
        pass
    # Feed exists
    try:
        feed_id = client.read_entry(deployed["StakedOracle"], 10,  # get_feed_id_entry
                                    ["XEL/USD"])
        if int(feed_id) == 0:
            log.info("  ✓ XEL/USD feed registered (id=0)")
        else:
            log.warning(f"  ! XEL/USD feed_id={feed_id} (expected 0)")
    except Exception as e:
        log.warning(f"  ! Could not verify feed: {e}")
    # Registry spot checks
    for name in ["VLTToken", "StakedOracle", "VaultEngine", "PSM", "VaultSwap",
                 "GovernanceVault", "Governor", "Timelock", "GuardianMultisig"]:
        try:
            registered = client.read_entry(deployed["ContractRegistry"],
                                           CR_GET, [name])
            if registered and registered != XEL_ZERO_HASH:
                log.info(f"  ✓ Registry: {name}")
            else:
                log.warning(f"  ! Registry: {name} not found")
        except Exception:
            log.warning(f"  ! Could not check registry entry for {name}")
    log.info("✓ Deployment verification complete")


def save_deployment(deployed: dict[str, str], assets: dict[str, str]) -> None:
    out_path = Path(CONFIG["output_file"]) if CONFIG["output_file"] else (
        Path.home() / ".xelis-vault" / "config" / "deployment.json"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "network": CONFIG["network"],
        "deployed_at": int(time.time()),
        "contracts": deployed,
        "assets": assets,
        "config": {
            "rpc_url": CONFIG["rpc_url"],
            "signer": CONFIG["signer"],
            "team_address": CONFIG["team_address"],
            "treasury_address": CONFIG["treasury_address"],
            "airdrop_address": CONFIG["airdrop_address"],
            "bug_bounty_address": CONFIG["bug_bounty_address"],
            "dex_address": CONFIG["dex_address"],
        },
        "vlt_allocation": {k: v for k, v in VLT_ALLOCATION.items()},
    }
    out_path.write_text(json.dumps(payload, indent=2))
    log.info(f"Deployment info saved to {out_path}")


def print_summary(deployed: dict[str, str], assets: dict[str, str]) -> None:
    print()
    print("=" * 70)
    print("  XELIS Vault v5.0 — Deployment Summary")
    print("=" * 70)
    print(f"  Network:      {CONFIG['network']}")
    print(f"  Signer:       {CONFIG['signer']}  (private key never logged)")
    print(f"  RPC:          {CONFIG['rpc_url']}")
    print()
    print("  Contracts:")
    for name, hash_val in deployed.items():
        print(f"    {name:<22} {hash_val}")
    print()
    print("  Assets:")
    for name, hash_val in assets.items():
        print(f"    {name:<22} {hash_val}")
    print()
    print("=" * 70)
    print("  Next steps:")
    print("    1. Recruit 5-10 price providers (see docs/PROVIDER_GUIDE.md)")
    print("    2. Run aggregation keeper (see docs/MINER_GUIDE.md)")
    print("    3. Monitor at https://testnet-explorer.xelis.io/")
    print("=" * 70)


# ============================================================================
# MAIN
# ============================================================================
def main() -> None:
    parser = argparse.ArgumentParser(
        description="XELIS Vault v5.0 Testnet Deployment"
    )
    parser.add_argument("--signer", default=CONFIG["signer"])
    parser.add_argument("--rpc", default=CONFIG["rpc_url"])
    parser.add_argument("--team", help="Team allocation address")
    parser.add_argument("--treasury", help="Treasury address")
    parser.add_argument("--airdrop", help="Airdrop reserve address")
    parser.add_argument("--bug-bounty", help="Bug bounty address")
    parser.add_argument("--dex", help="DEX liquidity address")
    parser.add_argument("--skip-distribution", action="store_true",
                        help="Skip VLT distribution (for testing)")
    parser.add_argument("--skip-feed", action="store_true",
                        help="Skip adding XEL/USD feed")
    parser.add_argument("--skip-faucet", action="store_true",
                        help="Skip refilling the faucet")
    args = parser.parse_args()

    CONFIG["signer"] = args.signer
    CONFIG["rpc_url"] = args.rpc
    if args.team:        CONFIG["team_address"]        = args.team
    if args.treasury:    CONFIG["treasury_address"]    = args.treasury
    if args.airdrop:     CONFIG["airdrop_address"]     = args.airdrop
    if args.bug_bounty:  CONFIG["bug_bounty_address"]  = args.bug_bounty
    if args.dex:         CONFIG["dex_address"]         = args.dex

    log.info("=" * 70)
    log.info("XELIS Vault v5.0 — Testnet Deployment")
    log.info("=" * 70)
    log.info(f"  RPC:       {CONFIG['rpc_url']}")
    log.info(f"  Network:   {CONFIG['network']}")
    log.info(f"  Signer:    {CONFIG['signer']}  (private key never logged)")
    log.info(f"  Team:      {CONFIG['team_address']}")
    log.info(f"  Treasury:  {CONFIG['treasury_address']}")
    log.info(f"  Airdrop:   {CONFIG['airdrop_address']}")
    log.info(f"  Bug bounty:{CONFIG['bug_bounty_address']}")
    log.info(f"  DEX:       {CONFIG['dex_address']}")
    log.info("=" * 70)

    client = XelisClient(CONFIG["rpc_url"], CONFIG["signer"])

    check_prerequisites(client)
    deployed = deploy_all_contracts(client)
    assets = create_assets(client, deployed)
    wire_contracts(client, deployed, assets)
    register_all_in_registry(client, deployed)
    if not args.skip_feed:
        add_initial_feed(client, deployed)
    if not args.skip_distribution:
        distribute_vlt(client, deployed, assets)
    if not args.skip_faucet:
        refill_faucet(client, deployed)
    verify_deployment(client, deployed, assets)
    save_deployment(deployed, assets)
    print_summary(deployed, assets)

    log.info("=" * 70)
    log.info("✓ DEPLOYMENT COMPLETE!")
    log.info("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted by user")
        sys.exit(1)
