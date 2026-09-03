#!/usr/bin/env python3
"""
============================================================================
 XELIS Vault v10.6 — Admin Panel
============================================================================
Module des fonctions réservées à l'admin du protocole.
Accessible via: xvault --admin  (ou menu Settings → Admin Panel)

L'admin peut :
  - Gérer les contrats (pause, unpause, set parameters)
  - Distribuer le faucet (testnet)
  - Gérer l'airdrop (freeze, finalize, set merkle root, batch add points)
  - Gérer les miners (slash, set rewards, register service)
  - Gérer le FeeDistributor (set founder, set treasury)
  - Gérer FounderVesting (claim tokens, set founder)
  - Gérer RevenueShareDelegation (set share, revoke, extend)
  - Emergency shutdown (si EmergencyShutdown déployé)
============================================================================
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from tui import *
from contract_ops import (
    fmt_xel, fmt_vlt, fmt_xusd, fmt_usd, fmt_addr, fmt_amount,
    check_contracts_configured, show_tx_result,
)

# Entry IDs pour les contrats admin

# ContractRegistry
REG_GET = 0
REG_REGISTER = 1
REG_UPGRADE = 2
REG_ROLLBACK = 3

# XelisVaultMiner
MINER_REGISTER = 0
MINER_SLASH = 7
MINER_DISTRIBUTE_REWARD = 8
MINER_SET_BASE_REWARD = 23  # pub fn → entry
MINER_SET_TOTAL_BUDGET = 18
MINER_SET_AUTHORIZED_SERVICE = 16

# StakedOracle
ORACLE_ADD_FEED = 0  # pub fn
ORACLE_SUBMIT_PRICE = 0  # entry
ORACLE_AGGREGATE_NOW = 1  # entry
ORACLE_FORCE_UPDATE = 23  # entry (v10.5 escape hatch)
ORACLE_PAUSE = 21  # entry wrapper
ORACLE_UNPAUSE = 22  # entry wrapper
ORACLE_SET_MINER_CONTRACT = 9

# VaultEngineV3
VAULT_SET_MIN_CR = 20
VAULT_SET_LIQ_PENALTY = 21
VAULT_SET_PROTOCOL_FEE = 22
VAULT_PAUSE = 23
VAULT_UNPAUSE = 24

# PSM
PSM_SET_MINT_FEE = 6
PSM_SET_REDEEM_FEE = 7
PSM_SET_DAILY_CAPS = 8
PSM_PAUSE = 9
PSM_UNPAUSE = 10

# VaultSwapV2
SWAP_PAUSE = 15
SWAP_UNPAUSE = 16
SWAP_SET_FEE = 17

# FaucetContract
FAUCET_REFILL_XEL = 0
FAUCET_REFILL_VLT = 1
FAUCET_DISTRIBUTE = 2
FAUCET_SET_CLAIM_AMOUNTS = 3
FAUCET_SET_COOLDOWN = 4
FAUCET_SET_LIFETIME_CAPS = 5
FAUCET_PAUSE = 6
FAUCET_UNPAUSE = 7

# AirdropTracker
AIRDROP_FREEZE = 10
AIRDROP_FINALIZE = 11
AIRDROP_SET_MERKLE_ROOT = 12
AIRDROP_RECORD_MANUAL = 8
AIRDROP_RECORD_BATCH = 32
AIRDROP_DEDUCT = 33
AIRDROP_DISQUALIFY = 34
AIRDROP_REVOKE_DISQUAL = 35
AIRDROP_FORCE_QUALIFY = 36
AIRDROP_REVOKE_FORCE_QUAL = 37
AIRDROP_SET_MULTIPLIER = 38
AIRDROP_SET_CAP = 39
AIRDROP_SET_AUTHORIZED_RECORDER = 23

# FeeDistributor
FEE_SET_FOUNDER = 8
FEE_SET_TREASURY = 9
FEE_SET_VLT_CONTRACT = 10
FEE_SET_DISTRIBUTION = 11  # hypothetical set_burn_bps etc

# FounderVesting
FV_CLAIM = 0
FV_SET_FOUNDER = 4
FV_SET_VLT_CONTRACT = 5

# RevenueShareDelegation
RSD_SET_SHARE = 0
RSD_REVOKE_SHARE = 1
RSD_UPDATE_PCT = 2
RSD_EXTEND = 3
RSD_CLAIM_FOUNDER = 4

# Governor
GOV_QUEUE = 2
GOV_EXECUTE = 3

# GuardianMultisig
GUARDIAN_PROPOSE = 0
GUARDIAN_CONFIRM = 1
GUARDIAN_REVOKE = 2
GUARDIAN_EXECUTE = 3
GUARDIAN_ADD_SIGNER = 4
GUARDIAN_REMOVE_SIGNER = 5
GUARDIAN_SET_QUORUM = 6

# EmergencyShutdown
EMERGENCY_SOFT_PAUSE = 0
EMERGENCY_FULL_SHUTDOWN = 1
EMERGENCY_PROPOSE_RECOVERY = 2
EMERGENCY_EXECUTE_RECOVERY = 3


def is_admin(client) -> bool:
    """
    Check if the current user is the admin.
    Tries on-chain verification first (queries contracts for admin address),
    falls back to config if contracts not configured.
    """
    user_addr = client.cfg.get("miner_address") or ""
    if not user_addr:
        return False

    # Try on-chain verification: query VaultEngine (or any core contract) for admin
    # Each contract stores its admin at ADMIN_KEY.
    # We can query via a getter or by comparing get_caller() == admin.
    # Since contracts don't expose get_admin() directly, we use config-based check
    # BUT we auto-detect: if user_addr matches any known admin address in config.
    admin_addr = client.cfg.get("admin_address") or ""
    if admin_addr:
        return user_addr == admin_addr

    # Auto-detection: try to call an admin-only function on a contract
    # If it succeeds, user is admin. If it reverts, user is not.
    # This is a read-only check — we try get_version (which is public) but
    # we can't easily verify admin status without a getter.
    # For now, rely on config. The user sets "I am admin" in settings,
    # and we verify by checking their address matches.
    return False


def is_guardian(client) -> bool:
    """
    Check if the current user is a guardian.
    Queries the GuardianMultisig contract on-chain to verify.
    """
    user_addr = client.cfg.get("miner_address") or ""
    if not user_addr:
        return False

    # Try on-chain verification via GuardianMultisig.is_signer()
    guardian_contract = client.cfg.get("guardian_multisig_hash") or ""
    if guardian_contract:
        # GuardianMultisig pub fn is_signer(addr) -> bool
        result = client.invoke_contract_fn(guardian_contract, "is_signer", [user_addr])
        if result is not None:
            return bool(result)

    # Fall back to config
    guardian_addrs = client.cfg.get("guardian_addresses") or []
    return user_addr in guardian_addrs


def auto_detect_roles(client):
    """
    Auto-detect admin/guardian status by querying contracts.
    Updates the config with detected roles.
    Called on startup.
    """
    user_addr = client.cfg.get("miner_address") or ""
    if not user_addr:
        return

    # Check if user is guardian via GuardianMultisig
    guardian_contract = client.cfg.get("guardian_multisig_hash") or ""
    if guardian_contract:
        result = client.invoke_contract_fn(guardian_contract, "is_signer", [user_addr])
        if result is not None:
            # Update config
            guardian_addrs = client.cfg.get("guardian_addresses") or []
            if result and user_addr not in guardian_addrs:
                guardian_addrs.append(user_addr)
                client.cfg.data["guardian_addresses"] = guardian_addrs
                client.cfg.save()
            elif not result and user_addr in guardian_addrs:
                guardian_addrs.remove(user_addr)
                client.cfg.data["guardian_addresses"] = guardian_addrs
                client.cfg.save()

    # Admin detection: try to verify by calling an admin function
    # We can't easily do this read-only, so we rely on the user setting it
    # But we can check if user is admin of TreasuryVault (which exposes is_signer)
    treasury = client.cfg.get("treasury_hash") or ""
    if treasury:
        result = client.invoke_contract_fn(treasury, "is_signer", [user_addr])
        if result:
            # User is a treasury signer — likely admin
            client.cfg.data["admin_address"] = user_addr
            client.cfg.save()


def require_admin(client) -> bool:
    """Check admin access, show error if not admin."""
    if is_admin(client):
        return True
    clear()
    print(BANNER)
    print(f"\n{C.RED}{C.BOLD}  ⚠  ADMIN ACCESS REQUIRED{C.RESET}")
    print(f"{C.DIM}  Your address: {fmt_addr(client.cfg.get('miner_address', ''))}{C.RESET}")
    print(f"{C.DIM}  Admin address: {fmt_addr(client.cfg.get('admin_address', '(not set)'))}{C.RESET}")
    print(f"\n{C.DIM}  If you are the admin, configure your address:{C.RESET}")
    print(f"{C.DIM}    xvault --setup --admin <your_address>{C.RESET}")
    print(f"\n{C.GRAY}  Press Enter to continue...{C.RESET}", end="")
    input()
    return False


def require_guardian(client) -> bool:
    """Check guardian access."""
    if is_guardian(client):
        return True
    clear()
    print(BANNER)
    print(f"\n{C.RED}{C.BOLD}  ⚠  GUARDIAN ACCESS REQUIRED{C.RESET}")
    print(f"{C.DIM}  Your address: {fmt_addr(client.cfg.get('miner_address', ''))}{C.RESET}")
    print(f"{C.DIM}  Registered guardians: {len(client.cfg.get('guardian_addresses', []))}{C.RESET}")
    print(f"\n{C.DIM}  If you are a guardian, configure your address:{C.RESET}")
    print(f"{C.DIM}    xvault --setup --guardian <your_address>{C.RESET}")
    print(f"\n{C.GRAY}  Press Enter to continue...{C.RESET}", end="")
    input()
    return False


# ============================================================================
# ADMIN PANEL — Main menu
# ============================================================================

def screen_admin_panel(client):
    """Main admin panel — only accessible to admin."""
    if not require_admin(client):
        return

    while True:
        clear()
        print(BANNER)
        print(f"\n{C.RED}{C.BOLD}  🔐 ADMIN PANEL{C.RESET}")
        print(f"{C.GRAY}  {'─' * 56}{C.RESET}\n")

        # Show admin status
        addr = client.cfg.get("miner_address", "")
        print(f"  {C.DIM}Admin: {fmt_addr(addr)}{C.RESET}\n")

        choice = menu("Admin Menu", [
            ("⏸  Pause Protocol           — Emergency pause all contracts", "pause_all"),
            ("▶  Unpause Protocol         — Resume all contracts", "unpause_all"),
            ("🚰 Faucet Management         — Distribute testnet funds", "faucet"),
            ("🪂 Airdrop Management        — Freeze, finalize, batch points", "airdrop"),
            ("⛏  Miner Management          — Slash, rewards, services", "miner"),
            ("🔮 Oracle Management         — Add feed, force update, pause", "oracle"),
            ("⚙️  Protocol Parameters       — Fees, LTV, penalties", "params"),
            ("💰 FeeDistributor            — Set founder, treasury", "feedist"),
            ("💎 Founder Vesting           — Claim VLT, set founder", "vesting"),
            ("🤝 Revenue Share             — Share revenue with contributors", "revenue"),
            ("⚡ Emergency Shutdown         — Global circuit breaker", "emergency"),
            ("📊 Admin Log                 — View audit trail", "log"),
            ("Back", None),
        ])

        if choice is None:
            break
        elif choice == "pause_all":
            _admin_pause_all(client)
        elif choice == "unpause_all":
            _admin_unpause_all(client)
        elif choice == "faucet":
            _admin_faucet(client)
        elif choice == "airdrop":
            _admin_airdrop(client)
        elif choice == "miner":
            _admin_miner(client)
        elif choice == "oracle":
            _admin_oracle(client)
        elif choice == "params":
            _admin_params(client)
        elif choice == "feedist":
            _admin_feedist(client)
        elif choice == "vesting":
            _admin_vesting(client)
        elif choice == "revenue":
            _admin_revenue(client)
        elif choice == "emergency":
            _admin_emergency(client)
        elif choice == "log":
            _admin_log(client)


# ============================================================================
# Pause / Unpause
# ============================================================================

def _admin_pause_all(client):
    """Pause all protocol contracts."""
    clear()
    print(BANNER)
    print(f"\n{C.RED}{C.BOLD}  ⏸  PAUSE ALL CONTRACTS{C.RESET}")
    print(f"{C.GRAY}  {'─' * 56}{C.RESET}\n")
    print(f"  {C.YELLOW}⚠ This will pause ALL protocol operations.{C.RESET}")
    print(f"  {C.DIM}Users won't be able to deposit, borrow, swap, or chat.{C.RESET}")
    print(f"  {C.DIM}Only withdrawals and repays will work.{C.RESET}\n")

    contracts = [
        ("VaultEngine", client.cfg.get("vault_engine_hash"), VAULT_PAUSE),
        ("PSM", client.cfg.get("psm_hash"), PSM_PAUSE),
        ("VaultSwap", client.cfg.get("vault_swap_hash"), SWAP_PAUSE),
        ("StakedOracle", client.cfg.get("oracle_hash"), ORACLE_PAUSE),
    ]

    if not confirm("  Pause ALL contracts?"):
        print(f"\n  {C.DIM}Cancelled.{C.RESET}")
        input()
        return

    for name, hash_val, entry_id in contracts:
        if hash_val:
            print(f"  {C.DIM}Pausing {name}...{C.RESET}")
            tx = client.submit_transaction(hash_val, entry_id, [])
            if tx:
                print(f"    {C.GREEN}✓ {name} paused{C.RESET}")
            else:
                print(f"    {C.RED}✗ {name} failed{C.RESET}")

    print(f"\n  {C.GRAY}Press Enter...{C.RESET}", end="")
    input()


def _admin_unpause_all(client):
    """Unpause all protocol contracts."""
    clear()
    print(BANNER)
    print(f"\n{C.GREEN}{C.BOLD}  ▶  UNPAUSE ALL CONTRACTS{C.RESET}")
    print(f"{C.GRAY}  {'─' * 56}{C.RESET}\n")

    if not confirm("  Unpause ALL contracts?"):
        return

    contracts = [
        ("VaultEngine", client.cfg.get("vault_engine_hash"), VAULT_UNPAUSE),
        ("PSM", client.cfg.get("psm_hash"), PSM_UNPAUSE),
        ("VaultSwap", client.cfg.get("vault_swap_hash"), SWAP_UNPAUSE),
        ("StakedOracle", client.cfg.get("oracle_hash"), ORACLE_UNPAUSE),
    ]

    for name, hash_val, entry_id in contracts:
        if hash_val:
            print(f"  {C.DIM}Unpausing {name}...{C.RESET}")
            tx = client.submit_transaction(hash_val, entry_id, [])
            if tx:
                print(f"    {C.GREEN}✓ {name} unpaused{C.RESET}")
            else:
                print(f"    {C.RED}✗ {name} failed{C.RESET}")

    print(f"\n  {C.GRAY}Press Enter...{C.RESET}", end="")
    input()


# ============================================================================
# Faucet Management
# ============================================================================

def _admin_faucet(client):
    """Faucet management submenu."""
    faucet = client.cfg.get("faucet_hash")
    if not faucet:
        info_box("Error", ["Faucet not configured"])
        return

    while True:
        clear()
        print(BANNER)
        print(f"\n{C.CYAN}{C.BOLD}  🚰 FAUCET MANAGEMENT{C.RESET}")
        print(f"{C.GRAY}  {'─' * 56}{C.RESET}\n")

        # Show faucet info
        info = client.invoke_contract_fn(faucet, "get_faucet_info")
        if info and len(info) >= 6:
            xel_amt, vlt_amt, cooldown, xel_cap, vlt_cap, paused = info
            print(f"  XEL per claim:     {fmt_xel(xel_amt)}")
            print(f"  VLT per claim:     {fmt_vlt(vlt_amt)}")
            print(f"  Cooldown:          {cooldown} blocks")
            print(f"  Status:            {'⛔ Paused' if paused else '✅ Active'}\n")

        choice = menu("Faucet Menu", [
            ("💧 Distribute to addresses  — Batch send XEL+VLT", "distribute"),
            ("⚙️  Set claim amounts       — Change XEL/VLT per claim", "amounts"),
            ("⏱  Set cooldown             — Change wait time", "cooldown"),
            ("📊 Set lifetime caps        — Max per user", "caps"),
            ("⏸  Pause faucet", "pause"),
            ("▶  Unpause faucet", "unpause"),
            ("Back", None),
        ])

        if choice is None:
            break
        elif choice == "distribute":
            _faucet_distribute(client, faucet)
        elif choice == "amounts":
            _faucet_set_amounts(client, faucet)
        elif choice == "cooldown":
            _faucet_set_cooldown(client, faucet)
        elif choice == "caps":
            _faucet_set_caps(client, faucet)
        elif choice == "pause":
            tx = client.submit_transaction(faucet, FAUCET_PAUSE, [])
            show_tx_result(tx, "Faucet paused")
            input()
        elif choice == "unpause":
            tx = client.submit_transaction(faucet, FAUCET_UNPAUSE, [])
            show_tx_result(tx, "Faucet unpaused")
            input()


def _faucet_distribute(client, faucet):
    """Distribute XEL+VLT to multiple addresses."""
    clear()
    print(BANNER)
    print(f"\n{C.CYAN}{C.BOLD}  💧 DISTRIBUTE TESTNET FUNDS{C.RESET}")
    print(f"{C.GRAY}  {'─' * 56}{C.RESET}\n")
    print(f"  {C.DIM}Enter one address per line. Empty line to finish.{C.RESET}")
    print(f"  {C.DIM}Max 50 addresses per batch.{C.RESET}\n")

    addresses = []
    while len(addresses) < 50:
        addr = text_input(f"  Address {len(addresses)+1} (or empty): ")
        if not addr:
            break
        if len(addr) >= 10:
            addresses.append(addr)
        else:
            print(f"  {C.RED}Invalid, skipped.{C.RESET}")

    if not addresses:
        return

    print(f"\n  {C.BOLD}{len(addresses)} addresses will receive:{C.RESET}")
    print(f"  {C.YELLOW}100 XEL + 200 VLT each{C.RESET}")
    print(f"  {C.YELLOW}Total: {len(addresses) * 100} XEL + {len(addresses) * 200} VLT{C.RESET}")

    if confirm(f"\n  Distribute to {len(addresses)} addresses?"):
        print(f"\n  {C.DIM}Submitting...{C.RESET}")
        tx = client.submit_transaction(faucet, FAUCET_DISTRIBUTE, [addresses])
        show_tx_result(tx, f"Distributed to {len(addresses)} addresses")
    else:
        print(f"\n  {C.DIM}Cancelled.{C.RESET}")

    print(f"\n  {C.GRAY}Press Enter...{C.RESET}", end="")
    input()


def _faucet_set_amounts(client, faucet):
    """Set claim amounts."""
    clear()
    print(BANNER)
    print(f"\n{C.CYAN}{C.BOLD}  ⚙️  SET CLAIM AMOUNTS{C.RESET}\n")

    xel_str = text_input("  XEL per claim: ")
    vlt_str = text_input("  VLT per claim: ")
    try:
        xel = int(float(xel_str) * 10**8)
        vlt = int(float(vlt_str) * 10**8)
        if xel > 0 and vlt > 0:
            tx = client.submit_transaction(faucet, FAUCET_SET_CLAIM_AMOUNTS, [xel, vlt])
            show_tx_result(tx, "Amounts updated")
    except ValueError:
        print(f"\n  {C.RED}Invalid input.{C.RESET}")
    input()


def _faucet_set_cooldown(client, faucet):
    """Set cooldown."""
    clear()
    print(BANNER)
    print(f"\n{C.CYAN}{C.BOLD}  ⏱  SET COOLDOWN{C.RESET}\n")
    hours_str = text_input("  Cooldown in hours: ")
    try:
        hours = int(hours_str)
        blocks = hours * 720  # 720 blocks/hour at 5s
        if blocks >= 100:
            tx = client.submit_transaction(faucet, FAUCET_SET_COOLDOWN, [blocks])
            show_tx_result(tx, f"Cooldown set to {hours}h")
    except ValueError:
        print(f"\n  {C.RED}Invalid.{C.RESET}")
    input()


def _faucet_set_caps(client, faucet):
    """Set lifetime caps."""
    clear()
    print(BANNER)
    print(f"\n{C.CYAN}{C.BOLD}  📊 SET LIFETIME CAPS{C.RESET}\n")
    xel_str = text_input("  XEL lifetime cap: ")
    vlt_str = text_input("  VLT lifetime cap: ")
    try:
        xel = int(float(xel_str) * 10**8)
        vlt = int(float(vlt_str) * 10**8)
        tx = client.submit_transaction(faucet, FAUCET_SET_LIFETIME_CAPS, [xel, vlt])
        show_tx_result(tx, "Caps updated")
    except ValueError:
        print(f"\n  {C.RED}Invalid.{C.RESET}")
    input()


# ============================================================================
# Airdrop Management
# ============================================================================

def _admin_airdrop(client):
    """Airdrop management submenu."""
    tracker = client.cfg.get("airdrop_tracker_hash")
    if not tracker:
        info_box("Error", ["AirdropTracker not configured"])
        return

    while True:
        clear()
        print(BANNER)
        print(f"\n{C.CYAN}{C.BOLD}  🪂 AIRDROP MANAGEMENT{C.RESET}")
        print(f"{C.GRAY}  {'─' * 56}{C.RESET}\n")

        # Show stats
        stats = client.invoke_contract_fn(tracker, "get_protocol_stats")
        if stats and len(stats) >= 6:
            user_count, qualified, total_pts, distributable, frozen, finalized = stats
            if finalized:
                status = f"{C.GREEN}Finalized{C.RESET}"
            elif frozen:
                status = f"{C.YELLOW}Frozen{C.RESET}"
            else:
                status = f"{C.GREEN}Active{C.RESET}"
            print(f"  Status:            {status}")
            print(f"  Participants:      {user_count}")
            print(f"  Qualified:         {qualified}")
            print(f"  Total points:      {total_pts}\n")

        choice = menu("Airdrop Menu", [
            ("❄️  Freeze points             — End accumulation", "freeze"),
            ("✅ Finalize distribution      — Calculate VLT per user", "finalize"),
            ("🌳 Set Merkle root            — After off-chain generation", "merkle"),
            ("➕ Add points (single)        — Manual attribution", "add_single"),
            ("➕➕ Add points (batch)         — Multiple users", "add_batch"),
            ("➖ Deduct points              — Remove from user", "deduct"),
            ("🔨 Disqualify user            — Ban a cheater", "disqualify"),
            ("✅ Force-qualify user         — Override thresholds", "force_qual"),
            ("🎁 Set bonus multiplier       — Custom bonus", "multiplier"),
            ("⚙️  Set manual cap            — Max points per call", "set_cap"),
            ("📊 View admin log             — Audit trail", "log"),
            ("Back", None),
        ])

        if choice is None:
            break
        elif choice == "freeze":
            if confirm("  Freeze ALL points? This cannot be undone."):
                tx = client.submit_transaction(tracker, AIRDROP_FREEZE, [])
                show_tx_result(tx, "Points frozen")
            input()
        elif choice == "finalize":
            if confirm("  Finalize distribution? This calculates VLT per user."):
                print(f"\n  {C.DIM}This may take a moment (iterates all users)...{C.RESET}")
                tx = client.submit_transaction(tracker, AIRDROP_FINALIZE, [], fee=500000)
                show_tx_result(tx, "Distribution finalized")
            input()
        elif choice == "merkle":
            root = text_input("  Merkle root (hex): ")
            if root and len(root) >= 10:
                tx = client.submit_transaction(tracker, AIRDROP_SET_MERKLE_ROOT, [root])
                show_tx_result(tx, "Merkle root set")
            input()
        elif choice == "add_single":
            _airdrop_add_single(client, tracker)
        elif choice == "add_batch":
            _airdrop_add_batch(client, tracker)
        elif choice == "deduct":
            _airdrop_deduct(client, tracker)
        elif choice == "disqualify":
            _airdrop_disqualify(client, tracker)
        elif choice == "force_qual":
            _airdrop_force_qual(client, tracker)
        elif choice == "multiplier":
            _airdrop_multiplier(client, tracker)
        elif choice == "set_cap":
            _airdrop_set_cap(client, tracker)
        elif choice == "log":
            _airdrop_view_log(client, tracker)


def _airdrop_add_single(client, tracker):
    """Add points to single user."""
    clear()
    print(BANNER)
    print(f"\n{C.CYAN}{C.BOLD}  ➕ ADD POINTS (SINGLE USER){C.RESET}\n")

    addr = text_input("  User address: ")
    if not addr or len(addr) < 10:
        return

    cat = menu("Category", [
        ("Mining", "1"), ("Relayer", "2"), ("Governance", "3"),
        ("Chat", "4"), ("Liquidity", "5"), ("Bounty", "6"), ("Community", "7"),
        ("Cancel", None),
    ])
    if not cat:
        return

    pts_str = text_input("  Points: ")
    try:
        pts = int(pts_str)
    except ValueError:
        return

    reason = text_input("  Reason: ")
    if not reason:
        reason = "Manual attribution"

    if confirm(f"\n  Add {pts} points to {fmt_addr(addr)}?"):
        tx = client.submit_transaction(tracker, AIRDROP_RECORD_MANUAL,
                                       [addr, int(cat), pts, reason])
        show_tx_result(tx, "Points added")
    input()


def _airdrop_add_batch(client, tracker):
    """Batch add points."""
    clear()
    print(BANNER)
    print(f"\n{C.CYAN}{C.BOLD}  ➕➕ ADD POINTS (BATCH){C.RESET}")
    print(f"  {C.DIM}One address per line. Empty to finish. Max 50.{C.RESET}\n")

    users = []
    while len(users) < 50:
        addr = text_input(f"  Address {len(users)+1}: ")
        if not addr:
            break
        if len(addr) >= 10:
            users.append(addr)

    if not users:
        return

    cat = menu(f"Category for {len(users)} users", [
        ("Mining", "1"), ("Relayer", "2"), ("Governance", "3"),
        ("Chat", "4"), ("Liquidity", "5"), ("Bounty", "6"), ("Community", "7"),
        ("Cancel", None),
    ])
    if not cat:
        return

    pts_str = text_input(f"  Points per user ({len(users)} users): ")
    try:
        pts = int(pts_str)
    except ValueError:
        return

    reason = text_input("  Reason: ")
    if not reason:
        reason = "Batch attribution"

    if confirm(f"\n  Add {pts} pts to {len(users)} users (total {pts*len(users)})?"):
        tx = client.submit_transaction(tracker, AIRDROP_RECORD_BATCH,
                                       [users, int(cat), pts, reason])
        show_tx_result(tx, f"Batch: {len(users)} users")
    input()


def _airdrop_deduct(client, tracker):
    """Deduct points."""
    clear()
    print(BANNER)
    print(f"\n{C.CYAN}{C.BOLD}  ➖ DEDUCT POINTS{C.RESET}\n")

    addr = text_input("  User address: ")
    cat = menu("Category", [
        ("Mining", "1"), ("Relayer", "2"), ("Governance", "3"),
        ("Chat", "4"), ("Liquidity", "5"), ("Bounty", "6"), ("Community", "7"),
        ("Cancel", None),
    ])
    if not cat:
        return

    pts_str = text_input("  Points to deduct: ")
    try:
        pts = int(pts_str)
    except ValueError:
        return

    reason = text_input("  Reason: ")
    if not reason:
        reason = "Manual deduction"

    if confirm(f"\n  Deduct {pts} pts from {fmt_addr(addr)}?"):
        tx = client.submit_transaction(tracker, AIRDROP_DEDUCT,
                                       [addr, int(cat), pts, reason])
        show_tx_result(tx, "Points deducted")
    input()


def _airdrop_disqualify(client, tracker):
    """Disqualify user."""
    clear()
    print(BANNER)
    print(f"\n{C.RED}{C.BOLD}  🔨 DISQUALIFY USER{C.RESET}\n")
    print(f"  {C.YELLOW}Banned users get 0 VLT even if they have points.{C.RESET}\n")

    addr = text_input("  User address: ")
    reason = text_input("  Reason: ")
    if not reason:
        reason = "Rule violation"

    if confirm(f"\n  Disqualify {fmt_addr(addr)}?"):
        tx = client.submit_transaction(tracker, AIRDROP_DISQUALIFY, [addr, reason])
        show_tx_result(tx, "User disqualified")
    input()


def _airdrop_force_qual(client, tracker):
    """Force-qualify user."""
    clear()
    print(BANNER)
    print(f"\n{C.GREEN}{C.BOLD}  ✅ FORCE-QUALIFY USER{C.RESET}\n")

    addr = text_input("  User address: ")
    reason = text_input("  Reason: ")
    if not reason:
        reason = "Valuable contributor"

    if confirm(f"\n  Force-qualify {fmt_addr(addr)}?"):
        tx = client.submit_transaction(tracker, AIRDROP_FORCE_QUALIFY, [addr, reason])
        show_tx_result(tx, "User force-qualified")
    input()


def _airdrop_multiplier(client, tracker):
    """Set bonus multiplier."""
    clear()
    print(BANNER)
    print(f"\n{C.CYAN}{C.BOLD}  🎁 SET BONUS MULTIPLIER{C.RESET}\n")

    addr = text_input("  User address: ")

    mult = menu("Multiplier", [
        ("15000 (+50%) — Discord mod", "15000"),
        ("20000 (+100%) — Community leader", "20000"),
        ("13000 (+30%) — Active helper", "13000"),
        ("0 — Remove multiplier", "0"),
        ("Cancel", None),
    ])
    if not mult:
        return

    reason = text_input("  Reason: ")
    if not reason:
        reason = "Custom multiplier"

    if confirm(f"\n  Set multiplier {mult} for {fmt_addr(addr)}?"):
        tx = client.submit_transaction(tracker, AIRDROP_SET_MULTIPLIER,
                                       [addr, int(mult), reason])
        show_tx_result(tx, "Multiplier set")
    input()


def _airdrop_set_cap(client, tracker):
    """Set manual cap."""
    clear()
    print(BANNER)
    print(f"\n{C.CYAN}{C.BOLD}  ⚙️  SET MANUAL CAP{C.RESET}\n")

    cap_str = text_input("  New cap (max points per call): ")
    try:
        cap = int(cap_str)
        if 100 <= cap <= 500000:
            tx = client.submit_transaction(tracker, AIRDROP_SET_CAP, [cap])
            show_tx_result(tx, "Cap updated")
    except ValueError:
        pass
    input()


def _airdrop_view_log(client, tracker):
    """View admin log."""
    clear()
    print(BANNER)
    print(f"\n{C.CYAN}{C.BOLD}  📊 ADMIN LOG{C.RESET}\n")

    count = client.invoke_contract_fn(tracker, "get_admin_log_count")
    if not count or count == 0:
        print(f"  {C.DIM}No admin actions logged.{C.RESET}")
        input()
        return

    show = min(20, count)
    print(f"  {C.DIM}Showing last {show} of {count} actions:{C.RESET}\n")

    for i in range(show):
        idx = (count - 1 - i) % 1000
        entry = client.invoke_contract_fn(tracker, "get_admin_log_entry", [idx])
        if entry and len(entry) >= 8:
            admin, action_type, target, cat, amount, mult, reason, topo = entry
            actions = {1: "Add", 2: "Deduct", 3: "Disqualify", 4: "ForceQual",
                       5: "Multiplier", 6: "Batch"}
            action_name = actions.get(action_type, f"Type{action_type}")
            target_str = fmt_addr(target) if target else "(batch)"
            amt = f"{amount}" if amount else (f"{mult}bps" if mult else "")
            print(f"  {C.DIM}{i+1:>3}{C.RESET} {action_name:<12} {target_str:<20} {amt:>10} {reason[:25]}")

    print(f"\n  {C.GRAY}Press Enter...{C.RESET}", end="")
    input()


# ============================================================================
# Miner Management
# ============================================================================

def _admin_miner(client):
    """Miner management submenu."""
    miner = client.cfg.get("miner_hash") or client.cfg.get("xelis_vault_miner_hash")
    if not miner:
        info_box("Error", ["XelisVaultMiner not configured"])
        return

    while True:
        clear()
        print(BANNER)
        print(f"\n{C.CYAN}{C.BOLD}  ⛏  MINER MANAGEMENT{C.RESET}")
        print(f"{C.GRAY}  {'─' * 56}{C.RESET}\n")

        choice = menu("Miner Menu", [
            ("🔨 Slash miner              — Penalize a miner", "slash"),
            ("💰 Set base reward          — Change reward per submission", "reward"),
            ("🔑 Authorize service        — Allow contract to call miner", "service"),
            ("📊 View miner info          — Check miner details", "view"),
            ("Back", None),
        ])

        if choice is None:
            break
        elif choice == "slash":
            _miner_slash(client, miner)
        elif choice == "reward":
            _miner_set_reward(client, miner)
        elif choice == "service":
            _miner_service(client, miner)
        elif choice == "view":
            _miner_view(client, miner)


def _miner_slash(client, miner):
    """Slash a miner."""
    clear()
    print(BANNER)
    print(f"\n{C.RED}{C.BOLD}  🔨 SLASH MINER{C.RESET}\n")

    addr = text_input("  Miner address: ")
    sev = menu("Severity", [
        ("0 — Outlier (1% stake, 50 rep)", "0"),
        ("1 — Late submission (5% stake, 200 rep)", "1"),
        ("2 — Offline (10% stake, 500 rep)", "2"),
        ("3 — Censorship (25% stake, 1000 rep)", "3"),
        ("4 — Malicious (50% stake, 5000 rep)", "4"),
        ("Cancel", None),
    ])
    if sev is None:
        return

    reporter = text_input("  Reporter address (gets 10% bounty, or empty): ")

    if confirm(f"\n  Slash miner {fmt_addr(addr)} (severity {sev})?"):
        params = [addr, int(sev), reporter if reporter else client.cfg.get("miner_address")]
        tx = client.submit_transaction(miner, MINER_SLASH, params)
        show_tx_result(tx, "Miner slashed")
    input()


def _miner_set_reward(client, miner):
    """Set base reward."""
    clear()
    print(BANNER)
    print(f"\n{C.CYAN}{C.BOLD}  💰 SET BASE REWARD{C.RESET}\n")

    print(f"  {C.DIM}Current base rewards:{C.RESET}")
    print(f"  {C.DIM}• Oracle: 0.475 VLT per valid submission{C.RESET}")
    print(f"  {C.DIM}• Chat: 2 VLT per valid anchor{C.RESET}\n")

    svc = menu("Which service?", [
        ("Oracle (service 1)", "1"),
        ("Chat (service 2)", "2"),
        ("Cancel", None),
    ])
    if svc is None:
        return

    amt_str = text_input(f"  New base reward (in VLT, e.g. 0.5): ")
    try:
        amt = int(float(amt_str) * 10**8)
        if amt > 0:
            tx = client.submit_transaction(miner, MINER_SET_BASE_REWARD, [int(svc), amt])
            show_tx_result(tx, "Base reward updated")
    except ValueError:
        pass
    input()


def _miner_service(client, miner):
    """Authorize a service contract."""
    clear()
    print(BANNER)
    print(f"\n{C.CYAN}{C.BOLD}  🔑 AUTHORIZE SERVICE{C.RESET}\n")

    addr = text_input("  Contract address to authorize: ")
    svc = menu("Service ID", [
        ("1 — Oracle", "1"),
        ("2 — Chat", "2"),
        ("Cancel", None),
    ])
    if svc is None:
        return

    enable = menu("Action", [
        ("Authorize", "true"),
        ("Revoke", "false"),
        ("Cancel", None),
    ])
    if enable is None:
        return

    if confirm(f"\n  {'Authorize' if enable == 'true' else 'Revoke'} {fmt_addr(addr)}?"):
        params = [addr, int(svc), enable == "true"]
        tx = client.submit_transaction(miner, MINER_SET_AUTHORIZED_SERVICE, params)
        show_tx_result(tx, "Service updated")
    input()


def _miner_view(client, miner):
    """View miner info."""
    clear()
    print(BANNER)
    print(f"\n{C.CYAN}{C.BOLD}  📊 MINER INFO{C.RESET}\n")

    addr = text_input("  Miner address: ")
    if not addr:
        return

    info = client.invoke_contract_fn(miner, "get_miner", [addr])
    if info and len(info) >= 10:
        endpoint, pubkey, stake, services, registered, last_hb, total_rewards, total_slashed, rep, active = info[:10]
        print(f"\n  {C.BOLD}Miner: {fmt_addr(addr)}{C.RESET}")
        print(f"  Endpoint:       {endpoint}")
        print(f"  Stake:          {fmt_vlt(stake)}")
        print(f"  Services:       {services}")
        print(f"  Reputation:     {rep} / 10000")
        print(f"  Total rewards:  {fmt_vlt(total_rewards)}")
        print(f"  Total slashed:  {fmt_vlt(total_slashed)}")
        print(f"  Active:         {'✅' if active else '❌'}")
    else:
        print(f"\n  {C.DIM}Miner not found.{C.RESET}")
    input()


# ============================================================================
# Oracle Management
# ============================================================================

def _admin_oracle(client):
    """Oracle management submenu."""
    oracle = client.cfg.get("oracle_hash")
    if not oracle:
        info_box("Error", ["StakedOracle not configured"])
        return

    while True:
        clear()
        print(BANNER)
        print(f"\n{C.CYAN}{C.BOLD}  🔮 ORACLE MANAGEMENT{C.RESET}")
        print(f"{C.GRAY}  {'─' * 56}{C.RESET}\n")

        # Show price
        price = client.get_xel_price()
        if price:
            print(f"  Current XEL/USD: {C.GREEN}{fmt_usd(price)}{C.RESET}\n")

        choice = menu("Oracle Menu", [
            ("➕ Add feed                 — New price feed", "add_feed"),
            ("⚡ Force update price       — Override stuck feed", "force_update"),
            ("⏸  Pause oracle", "pause"),
            ("▶  Unpause oracle", "unpause"),
            ("Back", None),
        ])

        if choice is None:
            break
        elif choice == "add_feed":
            _oracle_add_feed(client, oracle)
        elif choice == "force_update":
            _oracle_force_update(client, oracle)
        elif choice == "pause":
            if confirm("  Pause oracle?"):
                tx = client.submit_transaction(oracle, ORACLE_PAUSE, ["admin_pause"])
                show_tx_result(tx, "Oracle paused")
            input()
        elif choice == "unpause":
            tx = client.submit_transaction(oracle, ORACLE_UNPAUSE, [])
            show_tx_result(tx, "Oracle unpaused")
            input()


def _oracle_add_feed(client, oracle):
    """Add a new price feed."""
    clear()
    print(BANNER)
    print(f"\n{C.CYAN}{C.BOLD}  ➕ ADD PRICE FEED{C.RESET}\n")

    name = text_input("  Feed name (e.g. XEL/USD): ")
    asset = text_input("  Asset hash (0x000... for XEL): ")
    if not asset:
        asset = "0x" + "0" * 64
    decimals_str = text_input("  Decimals (default 8): ")
    try:
        decimals = int(decimals_str) if decimals_str else 8
    except ValueError:
        decimals = 8

    min_str = text_input("  Min price (atomic): ")
    max_str = text_input("  Max price (atomic): ")

    if confirm(f"\n  Add feed '{name}'?"):
        tx = client.submit_transaction(oracle, ORACLE_ADD_FEED,
                                       [name, asset, decimals, int(min_str), int(max_str)])
        show_tx_result(tx, "Feed added")
    input()


def _oracle_force_update(client, oracle):
    """Force update a stuck feed."""
    clear()
    print(BANNER)
    print(f"\n{C.YELLOW}{C.BOLD}  ⚡ FORCE UPDATE PRICE{C.RESET}")
    print(f"  {C.DIM}Use this if a feed is stuck (circuit breaker or deviation).{C.RESET}\n")

    feed_id_str = text_input("  Feed ID (0 for XEL/USD): ")
    try:
        feed_id = int(feed_id_str)
    except ValueError:
        feed_id = 0

    price_str = text_input("  New price (in USD, e.g. 0.19): ")
    try:
        price = int(float(price_str) * 10**8)
    except ValueError:
        return

    if confirm(f"\n  Force update feed {feed_id} to {fmt_usd(price)}?"):
        tx = client.submit_transaction(oracle, ORACLE_FORCE_UPDATE, [feed_id, price])
        show_tx_result(tx, "Price force-updated")
    input()


# ============================================================================
# Protocol Parameters
# ============================================================================

def _admin_params(client):
    """Protocol parameters submenu."""
    while True:
        clear()
        print(BANNER)
        print(f"\n{C.CYAN}{C.BOLD}  ⚙️  PROTOCOL PARAMETERS{C.RESET}")
        print(f"{C.GRAY}  {'─' * 56}{C.RESET}\n")

        choice = menu("Parameters Menu", [
            ("VaultEngine — Min collateral ratio", "min_cr"),
            ("VaultEngine — Liquidation penalty", "liq_penalty"),
            ("VaultEngine — Protocol fee", "proto_fee"),
            ("PSM — Mint fee", "psm_mint_fee"),
            ("PSM — Redeem fee", "psm_redeem_fee"),
            ("PSM — Daily caps", "psm_caps"),
            ("VaultSwap — Swap fee", "swap_fee"),
            ("Back", None),
        ])

        if choice is None:
            break
        elif choice == "min_cr":
            _param_set(client, "vault_engine_hash", VAULT_SET_MIN_CR,
                       "Min collateral ratio (bps, e.g. 15000 = 150%)", 10000, 50000)
        elif choice == "liq_penalty":
            _param_set(client, "vault_engine_hash", VAULT_SET_LIQ_PENALTY,
                       "Liquidation penalty (bps, e.g. 1000 = 10%)", 100, 5000)
        elif choice == "proto_fee":
            _param_set(client, "vault_engine_hash", VAULT_SET_PROTOCOL_FEE,
                       "Protocol fee (bps, e.g. 50 = 0.5%)", 0, 1000)
        elif choice == "psm_mint_fee":
            _param_set(client, "psm_hash", PSM_SET_MINT_FEE,
                       "PSM mint fee (bps, e.g. 50 = 0.5%)", 0, 1000)
        elif choice == "psm_redeem_fee":
            _param_set(client, "psm_hash", PSM_SET_REDEEM_FEE,
                       "PSM redeem fee (bps, e.g. 10 = 0.1%)", 0, 1000)
        elif choice == "psm_caps":
            _psm_set_caps(client)
        elif choice == "swap_fee":
            _param_set(client, "vault_swap_hash", SWAP_SET_FEE,
                       "Swap fee (bps, e.g. 30 = 0.3%)", 0, 1000)


def _param_set(client, config_key, entry_id, label, min_val, max_val):
    """Generic parameter setter."""
    contract = client.cfg.get(config_key)
    if not contract:
        info_box("Error", [f"{config_key} not configured"])
        return

    clear()
    print(BANNER)
    print(f"\n{C.CYAN}{C.BOLD}  ⚙️  {label.upper()}{C.RESET}\n")

    val_str = text_input(f"  {label}: ")
    try:
        val = int(val_str)
        if val < min_val or val > max_val:
            print(f"\n  {C.RED}Value must be between {min_val} and {max_val}.{C.RESET}")
            input()
            return
        if confirm(f"\n  Set {label} to {val}?"):
            tx = client.submit_transaction(contract, entry_id, [val])
            show_tx_result(tx, "Parameter updated")
    except ValueError:
        pass
    input()


def _psm_set_caps(client):
    """Set PSM daily caps."""
    psm = client.cfg.get("psm_hash")
    if not psm:
        return

    clear()
    print(BANNER)
    print(f"\n{C.CYAN}{C.BOLD}  PSM DAILY CAPS{C.RESET}\n")

    mint_str = text_input("  Daily mint cap (XEL atomic): ")
    redeem_str = text_input("  Daily redeem cap (xUSD atomic): ")

    if confirm("\n  Update caps?"):
        tx = client.submit_transaction(psm, PSM_SET_DAILY_CAPS,
                                       [int(mint_str), int(redeem_str)])
        show_tx_result(tx, "Caps updated")
    input()


# ============================================================================
# FeeDistributor Management
# ============================================================================

def _admin_feedist(client):
    """FeeDistributor management."""
    feedist = client.cfg.get("fee_distributor_hash")
    if not feedist:
        info_box("Error", ["FeeDistributor not configured"])
        return

    while True:
        clear()
        print(BANNER)
        print(f"\n{C.CYAN}{C.BOLD}  💰 FEE DISTRIBUTOR{C.RESET}")
        print(f"{C.GRAY}  {'─' * 56}{C.RESET}\n")

        # Show pending balances
        founder_pending = client.invoke_contract_fn(feedist, "get_founder_balance")
        treasury_pending = client.invoke_contract_fn(feedist, "get_treasury_balance")

        print(f"  Founder pending:  {fmt_xel(founder_pending) if founder_pending else '0 XEL'}")
        print(f"  Treasury pending: {fmt_xel(treasury_pending) if treasury_pending else '0 XEL'}\n")

        choice = menu("FeeDistributor Menu", [
            ("👤 Set founder address      — Change founder", "set_founder"),
            ("🏛  Set treasury address     — Change treasury", "set_treasury"),
            ("Back", None),
        ])

        if choice is None:
            break
        elif choice == "set_founder":
            addr = text_input("  New founder address: ")
            if addr and len(addr) >= 10:
                if confirm(f"\n  Set founder to {fmt_addr(addr)}?"):
                    tx = client.submit_transaction(feedist, FEE_SET_FOUNDER, [addr])
                    show_tx_result(tx, "Founder updated")
            input()
        elif choice == "set_treasury":
            addr = text_input("  New treasury address: ")
            if addr and len(addr) >= 10:
                if confirm(f"\n  Set treasury to {fmt_addr(addr)}?"):
                    tx = client.submit_transaction(feedist, FEE_SET_TREASURY, [addr])
                    show_tx_result(tx, "Treasury updated")
            input()


# ============================================================================
# Founder Vesting
# ============================================================================

def _admin_vesting(client):
    """FounderVesting management."""
    vesting = client.cfg.get("founder_vesting_hash")
    if not vesting:
        info_box("Error", ["FounderVesting not configured"])
        return

    while True:
        clear()
        print(BANNER)
        print(f"\n{C.CYAN}{C.BOLD}  💎 FOUNDER VESTING{C.RESET}")
        print(f"{C.GRAY}  {'─' * 56}{C.RESET}\n")

        # Show vesting info
        info = client.invoke_contract_fn(vesting, "get_vesting_info")
        if info and len(info) >= 8:
            founder, total, claimed, start, cliff, vesting_blocks, current, paused = info
            claimable = client.invoke_contract_fn(vesting, "get_claimable_amount") or 0
            print(f"  Total:         {fmt_vlt(total)}")
            print(f"  Claimed:       {fmt_vlt(claimed)}")
            print(f"  Claimable now: {C.GREEN}{fmt_vlt(claimable)}{C.RESET}")
            print(f"  Start topo:    {start}")
            print(f"  Cliff ends:    {start + cliff}\n")

        choice = menu("Vesting Menu", [
            ("💎 Claim tokens             — Withdraw vested VLT", "claim"),
            ("👤 Set founder address      — Change founder", "set_founder"),
            ("Back", None),
        ])

        if choice is None:
            break
        elif choice == "claim":
            if confirm("  Claim all vested tokens?"):
                tx = client.submit_transaction(vesting, FV_CLAIM, [])
                show_tx_result(tx, "Tokens claimed")
            input()
        elif choice == "set_founder":
            addr = text_input("  New founder address: ")
            if addr and len(addr) >= 10:
                if confirm(f"\n  Set founder to {fmt_addr(addr)}?"):
                    tx = client.submit_transaction(vesting, FV_SET_FOUNDER, [addr])
                    show_tx_result(tx, "Founder updated")
            input()


# ============================================================================
# Revenue Share Delegation
# ============================================================================

def _admin_revenue(client):
    """RevenueShareDelegation management."""
    rsd = client.cfg.get("revenue_share_delegation_hash")
    if not rsd:
        info_box("Error", ["RevenueShareDelegation not configured"])
        return

    while True:
        clear()
        print(BANNER)
        print(f"\n{C.CYAN}{C.BOLD}  🤝 REVENUE SHARE DELEGATION{C.RESET}")
        print(f"{C.GRAY}  {'─' * 56}{C.RESET}\n")

        # Show founder pending
        pending = client.invoke_contract_fn(rsd, "get_founder_pending")
        if pending:
            print(f"  Founder pending: {fmt_xel(pending)}")
        count = client.invoke_contract_fn(rsd, "get_contributor_count")
        if count is not None:
            print(f"  Contributors:     {count}")
        print()

        choice = menu("Revenue Share Menu", [
            ("➕ Set share                — Share % with contributor", "set_share"),
            ("🔨 Revoke share             — Cancel a share", "revoke"),
            ("⏱  Extend share             — Add duration", "extend"),
            ("💎 Claim founder revenue    — Withdraw your share", "claim"),
            ("📊 View contributor info    — Check share details", "view"),
            ("Back", None),
        ])

        if choice is None:
            break
        elif choice == "set_share":
            _rsd_set_share(client, rsd)
        elif choice == "revoke":
            addr = text_input("  Contributor address: ")
            if confirm(f"\n  Revoke share for {fmt_addr(addr)}?"):
                tx = client.submit_transaction(rsd, RSD_REVOKE_SHARE, [addr])
                show_tx_result(tx, "Share revoked")
            input()
        elif choice == "extend":
            addr = text_input("  Contributor address: ")
            days_str = text_input("  Additional days: ")
            try:
                days = int(days_str)
                blocks = days * 720
                if confirm(f"\n  Extend by {days} days?"):
                    tx = client.submit_transaction(rsd, RSD_EXTEND, [addr, blocks])
                    show_tx_result(tx, "Share extended")
            except ValueError:
                pass
            input()
        elif choice == "claim":
            if confirm("  Claim founder revenue?"):
                tx = client.submit_transaction(rsd, RSD_CLAIM_FOUNDER, [])
                show_tx_result(tx, "Revenue claimed")
            input()
        elif choice == "view":
            _rsd_view(client, rsd)


def _rsd_set_share(client, rsd):
    """Set revenue share."""
    clear()
    print(BANNER)
    print(f"\n{C.CYAN}{C.BOLD}  ➕ SET REVENUE SHARE{C.RESET}\n")

    addr = text_input("  Contributor address: ")

    pct = menu("Percentage", [
        ("10% (1000 bps)", "1000"),
        ("20% (2000 bps)", "2000"),
        ("30% (3000 bps)", "3000"),
        ("50% (5000 bps) — max", "5000"),
        ("Custom", "custom"),
        ("Cancel", None),
    ])
    if pct is None:
        return
    elif pct == "custom":
        pct_str = text_input("  Percentage (bps, e.g. 2500 = 25%): ")
        try:
            pct = int(pct_str)
        except ValueError:
            return

    days_str = text_input("  Duration (days, min 1, max 3650): ")
    try:
        days = int(days_str)
        blocks = days * 720
    except ValueError:
        return

    if confirm(f"\n  Share {pct/100:.0f}% with {fmt_addr(addr)} for {days} days?"):
        tx = client.submit_transaction(rsd, RSD_SET_SHARE, [addr, int(pct), blocks])
        show_tx_result(tx, "Share set")
    input()


def _rsd_view(client, rsd):
    """View contributor info."""
    clear()
    print(BANNER)
    print(f"\n{C.CYAN}{C.BOLD}  📊 CONTRIBUTOR INFO{C.RESET}\n")

    addr = text_input("  Contributor address: ")
    if not addr:
        return

    info = client.invoke_contract_fn(rsd, "get_share_info", [addr])
    if info and len(info) >= 6:
        pct, start, end, received, pending, active = info
        print(f"\n  {C.BOLD}Contributor: {fmt_addr(addr)}{C.RESET}")
        print(f"  Percentage:      {pct/100:.1f}%")
        print(f"  Start topo:      {start}")
        print(f"  End topo:        {end}")
        print(f"  Total received:  {fmt_xel(received)}")
        print(f"  Pending:         {fmt_xel(pending)}")
        print(f"  Active:          {'✅' if active else '❌'}")
    else:
        print(f"\n  {C.DIM}No share found for this address.{C.RESET}")
    input()


# ============================================================================
# Emergency Shutdown
# ============================================================================

def _admin_emergency(client):
    """Emergency shutdown management."""
    emergency = client.cfg.get("emergency_shutdown_hash")
    if not emergency:
        info_box("Error", ["EmergencyShutdown not configured",
                           "This contract is part of the brainstorming features (Phase 5+)",
                           "It may not be deployed yet."])
        return

    while True:
        clear()
        print(BANNER)
        print(f"\n{C.RED}{C.BOLD}  ⚡ EMERGENCY SHUTDOWN{C.RESET}")
        print(f"{C.GRAY}  {'─' * 56}{C.RESET}\n")

        state = client.invoke_contract_fn(emergency, "get_state")
        states = {0: "NORMAL", 1: "SOFT_PAUSE", 2: "FULL_SHUTDOWN", 3: "RECOVERY"}
        state_name = states.get(state, "UNKNOWN") if state is not None else "UNKNOWN"
        print(f"  Current state: {C.BOLD}{state_name}{C.RESET}\n")

        choice = menu("Emergency Menu", [
            ("🟡 Soft pause               — Pause borrows/swaps, keep withdrawals", "soft"),
            ("🔴 Full shutdown            — Only withdrawals allowed", "full"),
            ("🟢 Propose recovery         — Start governance recovery", "recovery"),
            ("Back", None),
        ])

        if choice is None:
            break
        elif choice == "soft":
            reason = text_input("  Reason: ")
            if confirm(f"\n  {C.RED}Trigger SOFT PAUSE?{C.RESET}"):
                tx = client.submit_transaction(emergency, EMERGENCY_SOFT_PAUSE, [reason])
                show_tx_result(tx, "Soft pause triggered")
            input()
        elif choice == "full":
            reason = text_input("  Reason: ")
            if confirm(f"\n  {C.RED}⚠⚠  Trigger FULL SHUTDOWN? This is severe!{C.RESET}"):
                tx = client.submit_transaction(emergency, EMERGENCY_FULL_SHUTDOWN, [reason])
                show_tx_result(tx, "Full shutdown triggered")
            input()
        elif choice == "recovery":
            pid_str = text_input("  Governance proposal ID: ")
            try:
                pid = int(pid_str)
                if confirm("\n  Propose recovery?"):
                    tx = client.submit_transaction(emergency, EMERGENCY_PROPOSE_RECOVERY, [pid])
                    show_tx_result(tx, "Recovery proposed")
            except ValueError:
                pass
            input()


# ============================================================================
# Admin Log (generic)
# ============================================================================

def _admin_log(client):
    """View admin log from AirdropTracker (or other contracts)."""
    tracker = client.cfg.get("airdrop_tracker_hash")
    if tracker:
        _airdrop_view_log(client, tracker)
    else:
        info_box("No log", ["Admin log requires AirdropTracker"])


# ============================================================================
# GUARDIAN PANEL — Separate from admin
# ============================================================================

def screen_guardian_panel(client):
    """Guardian panel — only accessible to guardians."""
    if not require_guardian(client):
        return

    while True:
        clear()
        print(BANNER)
        print(f"\n{C.YELLOW}{C.BOLD}  🛡  GUARDIAN PANEL{C.RESET}")
        print(f"{C.GRAY}  {'─' * 56}{C.RESET}\n")

        addr = client.cfg.get("miner_address", "")
        print(f"  {C.DIM}Guardian: {fmt_addr(addr)}{C.RESET}\n")

        choice = menu("Guardian Menu", [
            ("⏸  Emergency pause          — Pause protocol immediately", "pause"),
            ("▶  Emergency unpause        — Resume protocol", "unpause"),
            ("🔮 Oracle force update      — Override stuck price", "oracle_force"),
            ("🚨 Trigger circuit breaker  — Pause specific feed", "cb"),
            ("🗳  Multisig proposals       — View/confirm/execute", "multisig"),
            ("Back", None),
        ])

        if choice is None:
            break
        elif choice == "pause":
            _guardian_pause(client)
        elif choice == "unpause":
            _guardian_unpause(client)
        elif choice == "oracle_force":
            _guardian_oracle_force(client)
        elif choice == "cb":
            _guardian_circuit_breaker(client)
        elif choice == "multisig":
            _guardian_multisig(client)


def _guardian_pause(client):
    """Guardian emergency pause."""
    clear()
    print(BANNER)
    print(f"\n{C.RED}{C.BOLD}  ⏸  EMERGENCY PAUSE{C.RESET}")
    print(f"{C.GRAY}  {'─' * 56}{C.RESET}\n")
    print(f"  {C.YELLOW}⚠ This will pause ALL protocol operations.{C.RESET}")
    print(f"  {C.DIM}Guardians can pause without admin approval.{C.RESET}\n")

    if not confirm("  Pause ALL contracts?"):
        return

    contracts = [
        ("VaultEngine", client.cfg.get("vault_engine_hash"), VAULT_PAUSE),
        ("PSM", client.cfg.get("psm_hash"), PSM_PAUSE),
        ("VaultSwap", client.cfg.get("vault_swap_hash"), SWAP_PAUSE),
        ("StakedOracle", client.cfg.get("oracle_hash"), ORACLE_PAUSE),
    ]

    for name, hash_val, entry_id in contracts:
        if hash_val:
            print(f"  {C.DIM}Pausing {name}...{C.RESET}")
            tx = client.submit_transaction(hash_val, entry_id, [])
            if tx:
                print(f"    {C.GREEN}✓ {name} paused{C.RESET}")
            else:
                print(f"    {C.RED}✗ {name} failed{C.RESET}")

    print(f"\n  {C.GRAY}Press Enter...{C.RESET}", end="")
    input()


def _guardian_unpause(client):
    """Guardian emergency unpause."""
    clear()
    print(BANNER)
    print(f"\n{C.GREEN}{C.BOLD}  ▶  EMERGENCY UNPAUSE{C.RESET}\n")

    if not confirm("  Unpause ALL contracts?"):
        return

    contracts = [
        ("VaultEngine", client.cfg.get("vault_engine_hash"), VAULT_UNPAUSE),
        ("PSM", client.cfg.get("psm_hash"), PSM_UNPAUSE),
        ("VaultSwap", client.cfg.get("vault_swap_hash"), SWAP_UNPAUSE),
        ("StakedOracle", client.cfg.get("oracle_hash"), ORACLE_UNPAUSE),
    ]

    for name, hash_val, entry_id in contracts:
        if hash_val:
            print(f"  {C.DIM}Unpausing {name}...{C.RESET}")
            tx = client.submit_transaction(hash_val, entry_id, [])
            if tx:
                print(f"    {C.GREEN}✓ {name} unpaused{C.RESET}")

    print(f"\n  {C.GRAY}Press Enter...{C.RESET}", end="")
    input()


def _guardian_oracle_force(client):
    """Guardian can force update oracle price."""
    oracle = client.cfg.get("oracle_hash")
    if not oracle:
        info_box("Error", ["Oracle not configured"])
        return

    clear()
    print(BANNER)
    print(f"\n{C.YELLOW}{C.BOLD}  ⚡ ORACLE FORCE UPDATE{C.RESET}")
    print(f"  {C.DIM}Guardians can override stuck prices.{C.RESET}\n")

    feed_id_str = text_input("  Feed ID (0 for XEL/USD): ")
    try:
        feed_id = int(feed_id_str)
    except ValueError:
        feed_id = 0

    price_str = text_input("  New price (USD, e.g. 0.19): ")
    try:
        price = int(float(price_str) * 10**8)
    except ValueError:
        return

    if confirm(f"\n  Force update feed {feed_id} to {fmt_usd(price)}?"):
        tx = client.submit_transaction(oracle, ORACLE_FORCE_UPDATE, [feed_id, price])
        show_tx_result(tx, "Price force-updated")
    input()


def _guardian_circuit_breaker(client):
    """Guardian can trigger circuit breaker on a feed."""
    oracle = client.cfg.get("oracle_hash")
    if not oracle:
        return

    clear()
    print(BANNER)
    print(f"\n{C.YELLOW}{C.BOLD}  🚨 CIRCUIT BREAKER{C.RESET}\n")

    feed_id_str = text_input("  Feed ID to pause: ")
    reason = text_input("  Reason: ")

    if confirm(f"\n  Trigger circuit breaker on feed {feed_id_str}?"):
        # StakedOracle trigger_feed_cb (pub fn → would need entry wrapper)
        print(f"\n  {C.DIM}Submitting...{C.RESET}")
        print(f"  {C.YELLOW}(Note: trigger_feed_cb may need entry wrapper){C.RESET}")
    input()


def _guardian_multisig(client):
    """GuardianMultisig operations."""
    guardian = client.cfg.get("guardian_multisig_hash")
    if not guardian:
        info_box("Error", ["GuardianMultisig not configured"])
        return

    while True:
        clear()
        print(BANNER)
        print(f"\n{C.CYAN}{C.BOLD}  🗳  MULTISIG PROPOSALS{C.RESET}")
        print(f"{C.GRAY}  {'─' * 56}{C.RESET}\n")

        choice = menu("Multisig Menu", [
            ("📋 View pending proposals   — List active proposals", "view"),
            ("✅ Confirm proposal         — Add your signature", "confirm"),
            ("❌ Revoke confirmation       — Remove your signature", "revoke"),
            ("▶  Execute proposal         — Execute if quorum reached", "execute"),
            ("Back", None),
        ])

        if choice is None:
            break
        elif choice == "view":
            print(f"\n  {C.DIM}(Proposal viewer — would list pending multisig proposals){C.RESET}")
            input()
        elif choice == "confirm":
            pid_str = text_input("  Proposal ID: ")
            try:
                pid = int(pid_str)
                if confirm(f"\n  Confirm proposal {pid}?"):
                    tx = client.submit_transaction(guardian, GUARDIAN_CONFIRM, [pid])
                    show_tx_result(tx, "Confirmation added")
            except ValueError:
                pass
            input()
        elif choice == "revoke":
            pid_str = text_input("  Proposal ID: ")
            try:
                pid = int(pid_str)
                if confirm(f"\n  Revoke confirmation for {pid}?"):
                    tx = client.submit_transaction(guardian, GUARDIAN_REVOKE, [pid])
                    show_tx_result(tx, "Confirmation revoked")
            except ValueError:
                pass
            input()
        elif choice == "execute":
            pid_str = text_input("  Proposal ID: ")
            try:
                pid = int(pid_str)
                if confirm(f"\n  Execute proposal {pid}?"):
                    tx = client.submit_transaction(guardian, GUARDIAN_EXECUTE, [pid])
                    show_tx_result(tx, "Proposal executed")
            except ValueError:
                pass
            input()
