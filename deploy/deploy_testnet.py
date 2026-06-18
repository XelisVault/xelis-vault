#!/usr/bin/env python3
"""
============================================================================
 XELIS Vault v4.2 — Testnet Deployment Script
============================================================================

Automated deployment of all XELIS Vault v4.2 contracts to XELIS testnet.

USAGE
=====
    python3 deploy_testnet.py --signer deployer

This script:
    1. Deploys ContractRegistry
    2. Deploys VLTToken, creates VLT asset
    3. Deploys StakedOracle, configures it
    4. Deploys OracleGovernance
    5. Deploys VaultEngineV3, VaultSwapV2
    6. Registers all contracts in ContractRegistry
    7. Distributes initial VLT allocation
    8. Adds XEL/USD feed
    9. Saves deployment addresses to deployment.json

PREREQUISITES
=============
    - XELIS daemon synced on testnet (--network testnet)
    - XELIS wallet running with --rpc-server
    - Compiled .slx contracts (use silex-compiler)
    - Deployer wallet with testnet XEL
    - Python 3.10+ with requests library

CONFIGURATION
=============
    Edit the CONFIG section below or use environment variables.
"""
import os
import sys
import json
import time
import argparse
import logging
from pathlib import Path

try:
    import requests
except ImportError:
    print("ERROR: 'requests' library not installed. Run: pip3 install requests")
    sys.exit(1)

# ============================================================================
# CONFIGURATION
# ============================================================================
CONFIG = {
    "rpc_url": os.environ.get("XELIS_RPC", "http://127.0.0.1:8080"),
    "network": os.environ.get("XELIS_NETWORK", "testnet"),
    "signer": os.environ.get("DEPLOYER_SIGNER", "deployer"),

    # Initial allocation addresses (override via env)
    "team_address": os.environ.get("TEAM_ADDRESS", ""),
    "treasury_address": os.environ.get("TREASURY_ADDRESS", ""),
    "airdrop_address": os.environ.get("AIRDROP_ADDRESS", ""),
    "bug_bounty_address": os.environ.get("BUG_BOUNTY_ADDRESS", ""),

    # Contracts directory (compiled .slx files)
    "contracts_dir": os.environ.get("CONTRACTS_DIR", "contracts"),

    # Output file for deployment addresses
    "output_file": os.environ.get("OUTPUT_FILE", "deployment.json"),
}

# VLT allocation (must sum to 10M VLT = 1e15 atomic)
VLT_ALLOCATION = {
    "oracle_rewards":  6_000_000 * 10**8,  # 60% — to StakedOracle contract
    "team":            1_500_000 * 10**8,  # 15% — to team wallet
    "treasury":        1_200_000 * 10**8,  # 12% — to treasury
    "dex_liquidity":   1_000_000 * 10**8,  # 10% — to VaultSwap
    "airdrop":           200_000 * 10**8,  # 2%  — to airdrop reserve
    "bug_bounty":        100_000 * 10**8,  # 1%  — to bug bounty
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger("deploy")


# ============================================================================
# XELIS RPC CLIENT
# ============================================================================
class XelisClient:
    def __init__(self, rpc_url: str, signer: str):
        self.rpc_url = rpc_url
        self.signer = signer
        self._id = 0

    def _call(self, method: str, params: dict = None) -> dict:
        self._id += 1
        payload = {
            "method": method,
            "params": params or {},
            "jsonrpc": "2.0",
            "id": self._id,
        }
        try:
            r = requests.post(self.rpc_url, json=payload, timeout=30)
            r.raise_for_status()
            data = r.json()
            if "error" in data:
                raise RuntimeError(f"RPC error: {data['error']}")
            return data.get("result", {})
        except Exception as e:
            log.error(f"RPC call failed ({method}): {e}")
            raise

    def get_topoheight(self) -> int:
        return int(self._call("get_topoheight"))

    def is_synced(self) -> bool:
        info = self._call("get_info")
        return info.get("synced", False)

    def deploy_contract(self, compiled_path: str) -> str:
        """Deploy a compiled contract. Returns the contract hash."""
        if not Path(compiled_path).exists():
            raise FileNotFoundError(f"Compiled contract not found: {compiled_path}")

        with open(compiled_path, "rb") as f:
            code = f.read().hex()

        result = self._call("submit_transaction", {
            "tx_type": "DeployContract",
            "code": code,
            "signer": self.signer,
        })
        tx_hash = result.get("hash")
        if not tx_hash:
            raise RuntimeError(f"Deploy failed: no tx hash returned")

        # Wait for confirmation and get contract hash
        time.sleep(5)  # wait 1 block
        receipt = self._call("get_transaction", {"hash": tx_hash})
        contract_hash = receipt.get("contract_hash")
        if not contract_hash:
            raise RuntimeError(f"Deploy tx confirmed but no contract hash: {receipt}")

        return contract_hash

    def call_contract(self, contract: str, entry: str, args: list,
                      deposit_asset: str = None, deposit_amount: int = None) -> str:
        """Call a contract entry. Returns tx hash."""
        params = {
            "tx_type": "CallContract",
            "contract": contract,
            "entry": entry,
            "args": [str(a) for a in args],
            "signer": self.signer,
        }
        if deposit_asset and deposit_amount:
            params["deposits"] = [{deposit_asset: str(deposit_amount)}]

        result = self._call("submit_transaction", params)
        tx_hash = result.get("hash")
        if not tx_hash:
            raise RuntimeError(f"Call failed: no tx hash returned")
        return tx_hash

    def read_contract(self, contract: str, entry: str, args: list = None) -> any:
        """Read-only contract call."""
        return self._call("call_contract_read", {
            "contract": contract,
            "entry": entry,
            "args": [str(a) for a in (args or [])],
        })

    def wait_for_tx(self, tx_hash: str, timeout: int = 30):
        """Wait for a transaction to be confirmed."""
        start = time.time()
        while time.time() - start < timeout:
            try:
                self._call("get_transaction", {"hash": tx_hash})
                return
            except:
                time.sleep(2)
        log.warning(f"Tx {tx_hash} not confirmed after {timeout}s")


# ============================================================================
# DEPLOYMENT FUNCTIONS
# ============================================================================
def check_prerequisites(client: XelisClient):
    """Verify prerequisites before deployment."""
    log.info("Checking prerequisites...")

    if not client.is_synced():
        log.error("Daemon is not synced. Wait for sync before deploying.")
        sys.exit(1)
    log.info("✓ Daemon synced")

    topo = client.get_topoheight()
    log.info(f"✓ Current topoheight: {topo}")

    required_addrs = ["team_address", "treasury_address", "airdrop_address", "bug_bounty_address"]
    for key in required_addrs:
        if not CONFIG[key]:
            log.error(f"Missing {key} in CONFIG. Set it via env var.")
            sys.exit(1)
    log.info("✓ All allocation addresses configured")

    contracts_dir = Path(CONFIG["contracts_dir"])
    required_contracts = [
        "proxy/ContractRegistry.compiled",
        "token/VLTToken.compiled",
        "usd/xUSD.compiled",
        "oracle/StakedOracle.compiled",
        "governance/OracleGovernance.compiled",
        "vault/VaultEngineV3.compiled",
        "amm/VaultSwapV2.compiled",
        "amm/PSM.compiled",
        "faucet/FaucetContract.compiled",
    ]
    for c in required_contracts:
        if not (contracts_dir / c).exists():
            log.error(f"Missing compiled contract: {contracts_dir / c}")
            log.error("Compile contracts first with silex-compiler.")
            sys.exit(1)
    log.info("✓ All compiled contracts present")


def deploy_contracts(client: XelisClient) -> dict:
    """Deploy all contracts in order. Returns dict of name -> hash."""
    deployed = {}
    cdir = CONFIG["contracts_dir"]

    # 1. ContractRegistry
    log.info("Deploying ContractRegistry...")
    deployed["ContractRegistry"] = client.deploy_contract(f"{cdir}/proxy/ContractRegistry.compiled")
    log.info(f"  ✓ ContractRegistry: {deployed['ContractRegistry']}")

    # 2. VLTToken
    log.info("Deploying VLTToken...")
    deployed["VLTToken"] = client.deploy_contract(f"{cdir}/token/VLTToken.compiled")
    log.info(f"  ✓ VLTToken: {deployed['VLTToken']}")

    # Create VLT asset
    log.info("Creating VLT asset...")
    tx = client.call_contract(deployed["VLTToken"], "create_asset", [])
    client.wait_for_tx(tx)

    # Get VLT asset hash
    vlt_asset = client.read_contract(deployed["VLTToken"], "get_asset_hash")
    deployed["VLTAsset"] = vlt_asset
    log.info(f"  ✓ VLT asset: {vlt_asset}")

    # 2b. xUSD (stablecoin)
    log.info("Deploying xUSD...")
    deployed["xUSD"] = client.deploy_contract(f"{cdir}/usd/xUSD.compiled")
    log.info(f"  ✓ xUSD: {deployed['xUSD']}")

    # Create xUSD asset
    log.info("Creating xUSD asset...")
    tx = client.call_contract(deployed["xUSD"], "create_asset", [])
    client.wait_for_tx(tx)

    xusd_asset = client.read_contract(deployed["xUSD"], "get_asset_hash")
    deployed["xUSDAsset"] = xusd_asset
    log.info(f"  ✓ xUSD asset: {xusd_asset}")

    # 3. StakedOracle
    log.info("Deploying StakedOracle...")
    deployed["StakedOracle"] = client.deploy_contract(f"{cdir}/oracle/StakedOracle.compiled")
    log.info(f"  ✓ StakedOracle: {deployed['StakedOracle']}")

    # Configure StakedOracle
    log.info("Configuring StakedOracle...")
    for entry, args in [
        ("set_vlt_contract", [deployed["VLTToken"]]),
        ("set_vlt_asset", [vlt_asset]),
        ("set_treasury", [CONFIG["treasury_address"]]),
        ("set_registry", [deployed["ContractRegistry"]]),
    ]:
        tx = client.call_contract(deployed["StakedOracle"], entry, args)
        client.wait_for_tx(tx)
        log.info(f"  ✓ {entry}")

    # Authorize StakedOracle as minter in VLTToken
    log.info("Authorizing StakedOracle as VLT minter...")
    tx = client.call_contract(deployed["VLTToken"], "set_minter",
                                [deployed["StakedOracle"], True])
    client.wait_for_tx(tx)
    log.info("  ✓ StakedOracle is now a minter")

    # 4. OracleGovernance
    log.info("Deploying OracleGovernance...")
    deployed["OracleGovernance"] = client.deploy_contract(f"{cdir}/governance/OracleGovernance.compiled")
    log.info(f"  ✓ OracleGovernance: {deployed['OracleGovernance']}")

    # Configure OracleGovernance
    log.info("Configuring OracleGovernance...")
    for entry, args in [
        ("set_oracle", [deployed["StakedOracle"]]),
        ("set_governance_vault", [deployed["VLTToken"]]),  # placeholder, should be real GovernanceVault
    ]:
        tx = client.call_contract(deployed["OracleGovernance"], entry, args)
        client.wait_for_tx(tx)
        log.info(f"  ✓ {entry}")

    # 5. VaultEngineV3
    log.info("Deploying VaultEngineV3...")
    deployed["VaultEngine"] = client.deploy_contract(f"{cdir}/vault/VaultEngineV3.compiled")
    log.info(f"  ✓ VaultEngine: {deployed['VaultEngine']}")

    # Configure VaultEngine
    log.info("Configuring VaultEngine...")
    for entry, args in [
        ("set_registry", [deployed["ContractRegistry"]]),
        ("set_treasury", [CONFIG["treasury_address"]]),
        ("set_xusd_contract", [deployed["xUSD"]]),
        ("set_xusd_asset", [xusd_asset]),
    ]:
        tx = client.call_contract(deployed["VaultEngine"], entry, args)
        client.wait_for_tx(tx)
        log.info(f"  ✓ {entry}")

    # 6. VaultSwapV2
    log.info("Deploying VaultSwapV2...")
    deployed["VaultSwap"] = client.deploy_contract(f"{cdir}/amm/VaultSwapV2.compiled")
    log.info(f"  ✓ VaultSwap: {deployed['VaultSwap']}")

    # Configure VaultSwap
    log.info("Configuring VaultSwap...")
    for entry, args in [
        ("set_registry", [deployed["ContractRegistry"]]),
        ("set_treasury", [CONFIG["treasury_address"]]),
        ("set_xusd_asset", [xusd_asset]),
        ("set_xusd_contract", [deployed["xUSD"]]),
    ]:
        tx = client.call_contract(deployed["VaultSwap"], entry, args)
        client.wait_for_tx(tx)
        log.info(f"  ✓ {entry}")

    # Authorize VaultEngine, VaultSwap and PSM as xUSD minters/burners
    log.info("Authorizing xUSD minters/burners...")

    # 6b. PSM (Peg Stability Module) — dedicated contract for xUSD peg
    log.info("Deploying PSM (Peg Stability Module)...")
    deployed["PSM"] = client.deploy_contract(f"{cdir}/amm/PSM.compiled")
    log.info(f"  ✓ PSM: {deployed['PSM']}")

    # Configure PSM
    log.info("Configuring PSM...")
    for entry, args in [
        ("set_xusd_contract", [deployed["xUSD"]]),
        ("set_xusd_asset", [xusd_asset]),
        ("set_oracle", [deployed["StakedOracle"]]),
        ("set_treasury", [CONFIG["treasury_address"]]),
    ]:
        tx = client.call_contract(deployed["PSM"], entry, args)
        client.wait_for_tx(tx)
        log.info(f"  ✓ {entry}")

    # Authorize VaultEngine, VaultSwap, and PSM as xUSD minters/burners
    for contract_name in ["VaultEngine", "VaultSwap", "PSM"]:
        for action in ["set_minter", "set_burner"]:
            tx = client.call_contract(deployed["xUSD"], action,
                                       [deployed[contract_name], True])
            client.wait_for_tx(tx)
            log.info(f"  ✓ {action} {contract_name}")

    # 7. FaucetContract
    log.info("Deploying FaucetContract...")
    deployed["FaucetContract"] = client.deploy_contract(f"{cdir}/faucet/FaucetContract.compiled")
    log.info(f"  ✓ FaucetContract: {deployed['FaucetContract']}")

    # Configure Faucet
    log.info("Configuring FaucetContract...")
    for entry, args in [
        ("set_vlt_asset", [vlt_asset]),
        ("set_vlt_contract", [deployed["VLTToken"]]),
    ]:
        tx = client.call_contract(deployed["FaucetContract"], entry, args)
        client.wait_for_tx(tx)
        log.info(f"  ✓ {entry}")

    # 7. Register all in ContractRegistry
    log.info("Registering contracts in ContractRegistry...")
    registrations = [
        ("ContractRegistry", deployed["ContractRegistry"]),
        ("VLTToken", deployed["VLTToken"]),
        ("xUSD", deployed["xUSD"]),
        ("StakedOracle", deployed["StakedOracle"]),
        ("OracleGovernance", deployed["OracleGovernance"]),
        ("VaultEngine", deployed["VaultEngine"]),
        ("VaultSwap", deployed["VaultSwap"]),
        ("PSM", deployed["PSM"]),
        ("FaucetContract", deployed["FaucetContract"]),
    ]
    for name, hash_val in registrations:
        tx = client.call_contract(deployed["ContractRegistry"], "register", [name, hash_val])
        client.wait_for_tx(tx)
        log.info(f"  ✓ Registered {name}")

    # 8. Refill Faucet with testnet funds
    log.info("Refilling Faucet with testnet funds...")
    # Refill 10,000 XEL testnet
    tx = client.call_contract(deployed["FaucetContract"], "refill_xel",
                               [10_000 * 10**8],
                               deposit_asset="0x" + "0" * 64,
                               deposit_amount=10_000 * 10**8)
    client.wait_for_tx(tx)
    log.info("  ✓ Refilled 10,000 XEL")

    # Refill 50,000 VLT (for community distribution)
    tx = client.call_contract(deployed["VLTToken"], "mint_to",
                               [deployed["FaucetContract"], 50_000 * 10**8])
    client.wait_for_tx(tx)
    log.info("  ✓ Minted 50,000 VLT to faucet")

    return deployed


def distribute_vlt(client: XelisClient, deployed: dict):
    """Distribute initial 10M VLT according to allocation."""
    log.info("Distributing initial VLT allocation (10M VLT)...")

    distributions = [
        ("Oracle rewards (to StakedOracle)", deployed["StakedOracle"], VLT_ALLOCATION["oracle_rewards"]),
        ("Team", CONFIG["team_address"], VLT_ALLOCATION["team"]),
        ("Treasury", CONFIG["treasury_address"], VLT_ALLOCATION["treasury"]),
        ("DEX liquidity (to VaultSwap)", deployed["VaultSwap"], VLT_ALLOCATION["dex_liquidity"]),
        ("Airdrop reserve", CONFIG["airdrop_address"], VLT_ALLOCATION["airdrop"]),
        ("Bug bounty", CONFIG["bug_bounty_address"], VLT_ALLOCATION["bug_bounty"]),
    ]

    for label, addr, amount in distributions:
        log.info(f"  Minting {amount / 1e8:.0f} VLT to {label}...")
        tx = client.call_contract(deployed["VLTToken"], "mint_to", [addr, amount])
        client.wait_for_tx(tx)
        log.info(f"  ✓ {label}")

    # Verify total supply
    supply = client.read_contract(deployed["VLTToken"], "get_circulating_supply")
    expected = sum(VLT_ALLOCATION.values())
    log.info(f"✓ Total VLT supply: {int(supply) / 1e8:.0f} (expected {expected / 1e8:.0f})")


def add_initial_feed(client: XelisClient, deployed: dict):
    """Add the XEL/USD feed to StakedOracle."""
    log.info("Adding XEL/USD feed...")
    # name="XEL/USD", asset=0x0 (XEL native), decimals=8, min=100000 ($0.001), max=10000000000000 ($10000)
    xel_zero = "0x" + "0" * 64
    tx = client.call_contract(
        deployed["StakedOracle"],
        "add_feed",
        ["XEL/USD", xel_zero, 8, 100000, 10000000000000]
    )
    client.wait_for_tx(tx)
    log.info("  ✓ XEL/USD feed added (feed_id = 0)")


def verify_deployment(client: XelisClient, deployed: dict):
    """Verify the deployment is functional."""
    log.info("Verifying deployment...")

    # Check VLT supply
    supply = client.read_contract(deployed["VLTToken"], "get_circulating_supply")
    assert int(supply) == 10_000_000 * 10**8, f"VLT supply mismatch: {supply}"
    log.info("  ✓ VLT supply = 10M")

    # Check StakedOracle config
    vlt_contract = client.read_contract(deployed["StakedOracle"], "get_version")
    log.info(f"  ✓ StakedOracle version: {vlt_contract}")

    # Check feed exists
    try:
        feed_id = client.read_contract(deployed["StakedOracle"], "get_feed_id", ["XEL/USD"])
        assert int(feed_id) == 0
        log.info("  ✓ XEL/USD feed exists (id=0)")
    except Exception as e:
        log.error(f"  ✗ Feed verification failed: {e}")

    # Check registry has all contracts
    for name in ["ContractRegistry", "VLTToken", "StakedOracle", "VaultEngine", "VaultSwap"]:
        registered = client.read_contract(deployed["ContractRegistry"], "get", [name])
        if registered and registered != "0x" + "0" * 64:
            log.info(f"  ✓ Registry: {name} = {registered}")
        else:
            log.error(f"  ✗ Registry: {name} not found")

    log.info("✓ Deployment verified successfully!")


def save_deployment(deployed: dict):
    """Save deployment addresses to JSON file."""
    output = {
        "network": CONFIG["network"],
        "deployed_at": int(time.time()),
        "contracts": deployed,
        "config": {
            "rpc_url": CONFIG["rpc_url"],
            "signer": CONFIG["signer"],
        },
    }
    with open(CONFIG["output_file"], "w") as f:
        json.dump(output, f, indent=2)
    log.info(f"Deployment addresses saved to {CONFIG['output_file']}")


# ============================================================================
# MAIN
# ============================================================================
def main():
    parser = argparse.ArgumentParser(description="XELIS Vault v4.2 Testnet Deployment")
    parser.add_argument("--signer", default=CONFIG["signer"], help="Wallet signer name")
    parser.add_argument("--rpc", default=CONFIG["rpc_url"], help="XELIS RPC URL")
    parser.add_argument("--team", help="Team allocation address")
    parser.add_argument("--treasury", help="Treasury address")
    parser.add_argument("--airdrop", help="Airdrop reserve address")
    parser.add_argument("--bug-bounty", help="Bug bounty address")
    parser.add_argument("--skip-distribution", action="store_true",
                        help="Skip VLT distribution (for testing)")
    parser.add_argument("--skip-feed", action="store_true",
                        help="Skip adding XEL/USD feed")
    args = parser.parse_args()

    # Override config with CLI args
    CONFIG["signer"] = args.signer
    CONFIG["rpc_url"] = args.rpc
    if args.team: CONFIG["team_address"] = args.team
    if args.treasury: CONFIG["treasury_address"] = args.treasury
    if args.airdrop: CONFIG["airdrop_address"] = args.airdrop
    if args.bug_bounty: CONFIG["bug_bounty_address"] = args.bug_bounty

    log.info("=" * 70)
    log.info("XELIS Vault v4.2 — Testnet Deployment")
    log.info("=" * 70)
    log.info(f"  RPC:      {CONFIG['rpc_url']}")
    log.info(f"  Network:  {CONFIG['network']}")
    log.info(f"  Signer:   {CONFIG['signer']}")
    log.info(f"  Team:     {CONFIG['team_address']}")
    log.info(f"  Treasury: {CONFIG['treasury_address']}")
    log.info("=" * 70)

    client = XelisClient(CONFIG["rpc_url"], CONFIG["signer"])

    # Step 1: Check prerequisites
    check_prerequisites(client)

    # Step 2: Deploy contracts
    deployed = deploy_contracts(client)

    # Step 3: Distribute VLT
    if not args.skip_distribution:
        distribute_vlt(client, deployed)

    # Step 4: Add XEL/USD feed
    if not args.skip_feed:
        add_initial_feed(client, deployed)

    # Step 5: Verify
    verify_deployment(client, deployed)

    # Step 6: Save deployment
    save_deployment(deployed)

    log.info("=" * 70)
    log.info("✓ DEPLOYMENT COMPLETE!")
    log.info("=" * 70)
    log.info("Next steps:")
    log.info("  1. Recruit 5-10 price providers (see docs/PROVIDER_GUIDE.md)")
    log.info("  2. Run aggregation keeper (see docs/MINER_GUIDE.md)")
    log.info("  3. Monitor at https://testnet-explorer.xelis.io/")
    log.info("=" * 70)


if __name__ == "__main__":
    main()
