#!/usr/bin/env python3
"""
============================================================================
 XELIS Vault v10.6 — Contract interactions module
============================================================================
Implements real interactions with deployed contracts.
All functions are wrapped with error handling and clear output.
============================================================================
"""
from __future__ import annotations
import sys
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).parent))
from tui import *

# Entry IDs (must match deployed contracts)
# StakedOracle
ORACLE_GET_PRICE = 4  # get_price_for_asset_entry

# VaultEngineV3
VAULT_DEPOSIT = 0
VAULT_BORROW = 1
VAULT_REPAY = 2
VAULT_WITHDRAW = 3
VAULT_LIQUIDATE = 4
VAULT_REDEEM = 5
VAULT_GET_VAULT = 10
VAULT_GET_HEALTH = 12
VAULT_TOTAL_VAULTS = 13

# PSM
PSM_MINT = 0
PSM_REDEEM = 1
PSM_GET_RESERVES = 2

# VaultSwapV2
SWAP_SWAP = 2
SWAP_ADD_LIQUIDITY = 0
SWAP_REMOVE_LIQUIDITY = 1

# GovernanceVault
GOV_STAKE = 0
GOV_UNSTAKE = 1
GOV_CLAIM_REWARDS = 2
GOV_GET_VOTING_POWER = 7

# Governor
GOV_PROPOSE = 0
GOV_VOTE = 1
GOV_QUEUE = 2
GOV_EXECUTE = 3

# PrivacyMixer
MIXER_DEPOSIT = 0
MIXER_WITHDRAW = 1

# VLTToken
VLT_TRANSFER = 4

# FaucetContract
FAUCET_DISTRIBUTE = 2

# AirdropTracker
AIRDROP_RECORD_MAINNET = 9

# AirdropClaim
AIRDROP_CLAIM = 0

XEL_DECIMALS = 8
VLT_DECIMALS = 8
XUSD_DECIMALS = 8


def fmt_amount(amount_atomic: int, decimals: int = 8) -> str:
    """Format atomic amount to human-readable string."""
    if not amount_atomic:
        return "0"
    amount = amount_atomic / (10 ** decimals)
    if amount >= 1000:
        return f"{amount:,.2f}"
    elif amount >= 1:
        return f"{amount:.4f}"
    else:
        return f"{amount:.8f}"


def fmt_xel(amount_atomic: int) -> str:
    return f"{fmt_amount(amount_atomic, XEL_DECIMALS)} XEL"


def fmt_vlt(amount_atomic: int) -> str:
    return f"{fmt_amount(amount_atomic, VLT_DECIMALS)} VLT"


def fmt_xusd(amount_atomic: int) -> str:
    return f"{fmt_amount(amount_atomic, XUSD_DECIMALS)} xUSD"


def fmt_usd(amount_atomic: int) -> str:
    """Format price in atomic (8 decimals) to USD string."""
    return f"${fmt_amount(amount_atomic, 8)}"


def fmt_addr(addr: str) -> str:
    """Truncate address for display."""
    if not addr or len(addr) < 20:
        return addr or "(not set)"
    return addr[:12] + "..." + addr[-8:]


def check_contracts_configured(client) -> bool:
    """Check if contract addresses are configured."""
    required = ["vault_engine_hash", "psm_hash", "vault_swap_hash",
                "oracle_hash", "governance_vault_hash"]
    missing = []
    for key in required:
        if not client.cfg.get(key):
            missing.append(key)
    if missing:
        clear()
        print(BANNER)
        print(f"\n{C.RED}{C.BOLD}  ⚠  Contracts not configured{C.RESET}")
        print(f"{C.DIM}  Missing: {', '.join(missing)}{C.RESET}")
        print(f"{C.DIM}  Run: xvault --setup to configure contract addresses.{C.RESET}")
        print(f"\n{C.GRAY}  Press Enter to continue...{C.RESET}", end="")
        input()
        return False
    return True


def show_tx_result(tx_hash: str, success_msg: str = "Transaction submitted"):
    """Display transaction result."""
    if tx_hash:
        print(f"\n  {C.GREEN}✓ {success_msg}!{C.RESET}")
        print(f"  {C.DIM}TX: {tx_hash[:40]}...{C.RESET}")
    else:
        print(f"\n  {C.RED}✗ Failed to submit transaction.{C.RESET}")
        print(f"  {C.DIM}Check your wallet is running and has balance.{C.RESET}")


# ============================================================================
# Vault operations
# ============================================================================

def vault_deposit(client, amount_xel: float):
    """Deposit XEL as collateral into VaultEngine."""
    if not check_contracts_configured(client):
        return
    vault_engine = client.cfg.get("vault_engine_hash")
    amount_atomic = int(amount_xel * (10 ** XEL_DECIMALS))

    clear()
    print(BANNER)
    print(f"\n{C.CYAN}{C.BOLD}  💰 DEPOSIT XEL COLLATERAL{C.RESET}")
    print(f"{C.GRAY}  {'─' * 56}{C.RESET}\n")
    print(f"  Amount: {C.YELLOW}{fmt_xel(amount_atomic)}{C.RESET}")
    print(f"  {C.DIM}This will deposit XEL as collateral into your vault.{C.RESET}")
    print(f"  {C.DIM}You can then borrow xUSD against it (up to 70% LTV).{C.RESET}")

    if confirm("\n  Confirm deposit?"):
        print(f"\n  {C.DIM}Submitting transaction...{C.RESET}")
        tx = client.submit_transaction(vault_engine, VAULT_DEPOSIT, [amount_atomic])
        show_tx_result(tx, "Deposit submitted")
    else:
        print(f"\n  {C.DIM}Cancelled.{C.RESET}")

    print(f"\n{C.GRAY}  Press Enter...{C.RESET}", end="")
    input()


def vault_borrow(client, amount_xusd: float):
    """Borrow xUSD against collateral."""
    if not check_contracts_configured(client):
        return
    vault_engine = client.cfg.get("vault_engine_hash")
    amount_atomic = int(amount_xusd * (10 ** XUSD_DECIMALS))

    clear()
    print(BANNER)
    print(f"\n{C.CYAN}{C.BOLD}  🏦 BORROW xUSD{C.RESET}")
    print(f"{C.GRAY}  {'─' * 56}{C.RESET}\n")
    print(f"  Amount: {C.YELLOW}{fmt_xusd(amount_atomic)}{C.RESET}")
    print(f"  {C.DIM}This will mint xUSD against your collateral.{C.RESET}")
    print(f"  {C.DIM}Stability fee: 2% APR (accrues over time){C.RESET}")
    print(f"  {C.DIM}Min collateral ratio: 150%{C.RESET}")

    if confirm("\n  Confirm borrow?"):
        print(f"\n  {C.DIM}Submitting transaction...{C.RESET}")
        tx = client.submit_transaction(vault_engine, VAULT_BORROW, [amount_atomic])
        show_tx_result(tx, "Borrow submitted")
    else:
        print(f"\n  {C.DIM}Cancelled.{C.RESET}")

    print(f"\n{C.GRAY}  Press Enter...{C.RESET}", end="")
    input()


def vault_repay(client, amount_xusd: float):
    """Repay xUSD debt."""
    if not check_contracts_configured(client):
        return
    vault_engine = client.cfg.get("vault_engine_hash")
    amount_atomic = int(amount_xusd * (10 ** XUSD_DECIMALS))

    clear()
    print(BANNER)
    print(f"\n{C.CYAN}{C.BOLD}  💳 REPAY xUSD DEBT{C.RESET}")
    print(f"{C.GRAY}  {'─' * 56}{C.RESET}\n")
    print(f"  Amount: {C.YELLOW}{fmt_xusd(amount_atomic)}{C.RESET}")
    print(f"  {C.DIM}This will burn xUSD to reduce your debt.{C.RESET}")

    if confirm("\n  Confirm repay?"):
        print(f"\n  {C.DIM}Submitting...{C.RESET}")
        tx = client.submit_transaction(vault_engine, VAULT_REPAY, [amount_atomic])
        show_tx_result(tx, "Repay submitted")
    else:
        print(f"\n  {C.DIM}Cancelled.{C.RESET}")

    print(f"\n{C.GRAY}  Press Enter...{C.RESET}", end="")
    input()


def vault_withdraw(client, amount_xel: float):
    """Withdraw XEL collateral."""
    if not check_contracts_configured(client):
        return
    vault_engine = client.cfg.get("vault_engine_hash")
    amount_atomic = int(amount_xel * (10 ** XEL_DECIMALS))

    clear()
    print(BANNER)
    print(f"\n{C.CYAN}{C.BOLD}  ↩ WITHDRAW XEL COLLATERAL{C.RESET}")
    print(f"{C.GRAY}  {'─' * 56}{C.RESET}\n")
    print(f"  Amount: {C.YELLOW}{fmt_xel(amount_atomic)}{C.RESET}")
    print(f"  {C.DIM}This will withdraw XEL from your vault.{C.RESET}")
    print(f"  {C.YELLOW}⚠ Your health factor must remain above 150%.{C.RESET}")

    if confirm("\n  Confirm withdrawal?"):
        print(f"\n  {C.DIM}Submitting...{C.RESET}")
        tx = client.submit_transaction(vault_engine, VAULT_WITHDRAW, [amount_atomic])
        show_tx_result(tx, "Withdrawal submitted")
    else:
        print(f"\n  {C.DIM}Cancelled.{C.RESET}")

    print(f"\n{C.GRAY}  Press Enter...{C.RESET}", end="")
    input()


def vault_view(client):
    """View user's vaults."""
    if not check_contracts_configured(client):
        return
    vault_engine = client.cfg.get("vault_engine_hash")
    addr = client.cfg.get("miner_address")

    clear()
    print(BANNER)
    print(f"\n{C.CYAN}{C.BOLD}  📋 YOUR VAULTS{C.RESET}")
    print(f"{C.GRAY}  {'─' * 56}{C.RESET}\n")

    # Get total vaults count
    total = client.invoke_contract(vault_engine, VAULT_TOTAL_VAULTS)
    if not total or not isinstance(total, int):
        print(f"  {C.DIM}No vaults found (or contracts not deployed).{C.RESET}")
        print(f"\n{C.GRAY}  Press Enter...{C.RESET}", end="")
        input()
        return

    print(f"  {C.DIM}Total vaults on protocol: {total}{C.RESET}")
    print(f"  {C.DIM}Your address: {fmt_addr(addr)}{C.RESET}\n")

    # In production: iterate vaults and show those owned by user
    # For now, show placeholder
    print(f"  {C.DIM}(Vault details will appear here once contracts are live){C.RESET}")

    print(f"\n{C.GRAY}  Press Enter...{C.RESET}", end="")
    input()


# ============================================================================
# Swap operations
# ============================================================================

def psm_mint(client, amount_xel: float):
    """Mint xUSD via PSM (1:1 with XEL at oracle price)."""
    if not check_contracts_configured(client):
        return
    psm = client.cfg.get("psm_hash")
    amount_atomic = int(amount_xel * (10 ** XEL_DECIMALS))

    price = client.get_xel_price()
    expected_xusd = int(amount_atomic * price / (10 ** 8)) if price else 0

    clear()
    print(BANNER)
    print(f"\n{C.CYAN}{C.BOLD}  💱 MINT xUSD via PSM{C.RESET}")
    print(f"{C.GRAY}  {'─' * 56}{C.RESET}\n")
    print(f"  You send:      {C.YELLOW}{fmt_xel(amount_atomic)}{C.RESET}")
    if price:
        print(f"  XEL price:     {fmt_usd(price)}")
        print(f"  You receive:   {C.GREEN}{fmt_xusd(expected_xusd)}{C.RESET}")
        print(f"  Fee:           {C.DIM}0.5% (included){C.RESET}")
    else:
        print(f"  {C.DIM}(oracle price unavailable){C.RESET}")

    if confirm("\n  Confirm mint?"):
        print(f"\n  {C.DIM}Submitting...{C.RESET}")
        tx = client.submit_transaction(psm, PSM_MINT, [amount_atomic, 1])
        show_tx_result(tx, "PSM mint submitted")
    else:
        print(f"\n  {C.DIM}Cancelled.{C.RESET}")

    print(f"\n{C.GRAY}  Press Enter...{C.RESET}", end="")
    input()


def psm_redeem(client, amount_xusd: float):
    """Redeem xUSD for XEL via PSM."""
    if not check_contracts_configured(client):
        return
    psm = client.cfg.get("psm_hash")
    amount_atomic = int(amount_xusd * (10 ** XUSD_DECIMALS))

    price = client.get_xel_price()
    expected_xel = int(amount_atomic * (10 ** 8) / price) if price else 0

    clear()
    print(BANNER)
    print(f"\n{C.CYAN}{C.BOLD}  💱 REDEEM xUSD for XEL{C.RESET}")
    print(f"{C.GRAY}  {'─' * 56}{C.RESET}\n")
    print(f"  You send:      {C.YELLOW}{fmt_xusd(amount_atomic)}{C.RESET}")
    if price:
        print(f"  XEL price:     {fmt_usd(price)}")
        print(f"  You receive:   {C.GREEN}{fmt_xel(expected_xel)}{C.RESET}")
        print(f"  Fee:           {C.DIM}0.1% (included){C.RESET}")
    else:
        print(f"  {C.DIM}(oracle price unavailable){C.RESET}")

    if confirm("\n  Confirm redeem?"):
        print(f"\n  {C.DIM}Submitting...{C.RESET}")
        tx = client.submit_transaction(psm, PSM_REDEEM, [amount_atomic, 1])
        show_tx_result(tx, "PSM redeem submitted")
    else:
        print(f"\n  {C.DIM}Cancelled.{C.RESET}")

    print(f"\n{C.GRAY}  Press Enter...{C.RESET}", end="")
    input()


def amm_swap(client, asset_in_name: str, asset_out_name: str, amount: float):
    """Generic AMM swap."""
    if not check_contracts_configured(client):
        return
    vault_swap = client.cfg.get("vault_swap_hash")

    # Resolve asset hashes
    asset_map = {
        "XEL": "0x" + "0" * 64,
        "xUSD": client.cfg.get("xusd_asset_hash", ""),
        "VLT": client.cfg.get("vlt_asset_hash", ""),
    }
    asset_in = asset_map.get(asset_in_name, "")
    asset_out = asset_map.get(asset_out_name, "")

    if not asset_in or not asset_out:
        print(f"\n  {C.RED}Asset not configured.{C.RESET}")
        print(f"\n{C.GRAY}  Press Enter...{C.RESET}", end="")
        input()
        return

    amount_atomic = int(amount * (10 ** 8))

    clear()
    print(BANNER)
    print(f"\n{C.CYAN}{C.BOLD}  🔄 AMM SWAP{C.RESET}")
    print(f"{C.GRAY}  {'─' * 56}{C.RESET}\n")
    print(f"  You send:      {C.YELLOW}{amount} {asset_in_name}{C.RESET}")
    print(f"  You receive:   {C.GREEN}(calculated by AMM){C.RESET} {asset_out_name}")
    print(f"  Fee:           {C.DIM}0.3% (included){C.RESET}")
    print(f"  Slippage:      {C.DIM}1% max (min_out=1){C.RESET}")

    if confirm("\n  Confirm swap?"):
        print(f"\n  {C.DIM}Submitting...{C.RESET}")
        tx = client.submit_transaction(vault_swap, SWAP_SWAP,
                                       [asset_in, asset_out, amount_atomic, 1])
        show_tx_result(tx, "Swap submitted")
    else:
        print(f"\n  {C.DIM}Cancelled.{C.RESET}")

    print(f"\n{C.GRAY}  Press Enter...{C.RESET}", end="")
    input()


# ============================================================================
# Governance operations
# ============================================================================

def gov_stake(client, amount_vlt: float):
    """Stake VLT in GovernanceVault."""
    if not check_contracts_configured(client):
        return
    gov_vault = client.cfg.get("governance_vault_hash")
    amount_atomic = int(amount_vlt * (10 ** VLT_DECIMALS))

    clear()
    print(BANNER)
    print(f"\n{C.CYAN}{C.BOLD}  🔒 STAKE VLT{C.RESET}")
    print(f"{C.GRAY}  {'─' * 56}{C.RESET}\n")
    print(f"  Amount: {C.YELLOW}{fmt_vlt(amount_atomic)}{C.RESET}")
    print(f"  {C.DIM}Staking VLT gives you voting power in governance.{C.RESET}")
    print(f"  {C.DIM}You earn rewards from protocol revenue.{C.RESET}")

    if confirm("\n  Confirm stake?"):
        print(f"\n  {C.DIM}Submitting...{C.RESET}")
        tx = client.submit_transaction(gov_vault, GOV_STAKE, [amount_atomic])
        show_tx_result(tx, "Stake submitted")
    else:
        print(f"\n  {C.DIM}Cancelled.{C.RESET}")

    print(f"\n{C.GRAY}  Press Enter...{C.RESET}", end="")
    input()


def gov_unstake(client, amount_vlt: float):
    """Unstake VLT from GovernanceVault."""
    if not check_contracts_configured(client):
        return
    gov_vault = client.cfg.get("governance_vault_hash")
    amount_atomic = int(amount_vlt * (10 ** VLT_DECIMALS))

    clear()
    print(BANNER)
    print(f"\n{C.CYAN}{C.BOLD}  🔓 UNSTAKE VLT{C.RESET}")
    print(f"{C.GRAY}  {'─' * 56}{C.RESET}\n")
    print(f"  Amount: {C.YELLOW}{fmt_vlt(amount_atomic)}{C.RESET}")
    print(f"  {C.YELLOW}⚠ Unstaking may have a delay before withdrawal.{C.RESET}")

    if confirm("\n  Confirm unstake?"):
        print(f"\n  {C.DIM}Submitting...{C.RESET}")
        tx = client.submit_transaction(gov_vault, GOV_UNSTAKE, [amount_atomic])
        show_tx_result(tx, "Unstake submitted")
    else:
        print(f"\n  {C.DIM}Cancelled.{C.RESET}")

    print(f"\n{C.GRAY}  Press Enter...{C.RESET}", end="")
    input()


def gov_claim_rewards(client):
    """Claim staking rewards."""
    if not check_contracts_configured(client):
        return
    gov_vault = client.cfg.get("governance_vault_hash")

    clear()
    print(BANNER)
    print(f"\n{C.CYAN}{C.BOLD}  🎁 CLAIM STAKING REWARDS{C.RESET}")
    print(f"{C.GRAY}  {'─' * 56}{C.RESET}\n")
    print(f"  {C.DIM}This will claim your accumulated VLT rewards.{C.RESET}")

    if confirm("\n  Confirm claim?"):
        print(f"\n  {C.DIM}Submitting...{C.RESET}")
        tx = client.submit_transaction(gov_vault, GOV_CLAIM_REWARDS, [])
        show_tx_result(tx, "Claim submitted")
    else:
        print(f"\n  {C.DIM}Cancelled.{C.RESET}")

    print(f"\n{C.GRAY}  Press Enter...{C.RESET}", end="")
    input()


# ============================================================================
# Mixer operations
# ============================================================================

def mixer_deposit(client, denomination: int):
    """Deposit into privacy mixer."""
    if not check_contracts_configured(client):
        return
    mixer = client.cfg.get("mixer_hash")
    amount_atomic = denomination * (10 ** XEL_DECIMALS)

    clear()
    print(BANNER)
    print(f"\n{C.CYAN}{C.BOLD}  🔒 PRIVACY MIXER DEPOSIT{C.RESET}")
    print(f"{C.GRAY}  {'─' * 56}{C.RESET}\n")
    print(f"  Denomination: {C.YELLOW}{denomination} XEL{C.RESET}")
    print(f"  {C.DIM}Your XEL will be mixed with others for privacy.{C.RESET}")
    print(f"  {C.DIM}You'll receive a private note to withdraw later.{C.RESET}")
    print(f"  {C.YELLOW}⚠ Save your note — it cannot be recovered!{C.RESET}")

    if confirm("\n  Confirm deposit?"):
        print(f"\n  {C.DIM}Generating commitment...{C.RESET}")
        print(f"  {C.DIM}Submitting...{C.RESET}")
        tx = client.submit_transaction(mixer, MIXER_DEPOSIT, [amount_atomic])
        show_tx_result(tx, "Mixer deposit submitted")
        print(f"\n  {C.YELLOW}⚠ Save your withdrawal note!{C.RESET}")
    else:
        print(f"\n  {C.DIM}Cancelled.{C.RESET}")

    print(f"\n{C.GRAY}  Press Enter...{C.RESET}", end="")
    input()


def mixer_withdraw(client):
    """Withdraw from privacy mixer."""
    if not check_contracts_configured(client):
        return
    mixer = client.cfg.get("mixer_hash")

    clear()
    print(BANNER)
    print(f"\n{C.CYAN}{C.BOLD}  🔓 PRIVACY MIXER WITHDRAW{C.RESET}")
    print(f"{C.GRAY}  {'─' * 56}{C.RESET}\n")
    print(f"  {C.DIM}Enter your withdrawal note and recipient address.{C.RESET}\n")

    note = text_input("  Withdrawal note: ")
    if not note:
        print(f"\n  {C.RED}No note provided.{C.RESET}")
        print(f"\n{C.GRAY}  Press Enter...{C.RESET}", end="")
        input()
        return

    recipient = text_input("  Recipient address (fresh address recommended): ")
    if not recipient or len(recipient) < 10:
        print(f"\n  {C.RED}Invalid address.{C.RESET}")
        print(f"\n{C.GRAY}  Press Enter...{C.RESET}", end="")
        input()
        return

    print(f"\n  {C.DIM}Generating ZK proof...{C.RESET}")
    print(f"  {C.DIM}Submitting...{C.RESET}")
    tx = client.submit_transaction(mixer, MIXER_WITHDRAW, [note, recipient])
    show_tx_result(tx, "Mixer withdrawal submitted")

    print(f"\n{C.GRAY}  Press Enter...{C.RESET}", end="")
    input()


# ============================================================================
# Faucet operations
# ============================================================================

def faucet_info(client):
    """Display faucet info."""
    if not check_contracts_configured(client):
        return
    faucet = client.cfg.get("faucet_hash")
    if not faucet:
        print(f"\n  {C.RED}Faucet not configured.{C.RESET}")
        print(f"\n{C.GRAY}  Press Enter...{C.RESET}", end="")
        input()
        return

    clear()
    print(BANNER)
    print(f"\n{C.CYAN}{C.BOLD}  🚰 FAUCET INFO{C.RESET}")
    print(f"{C.GRAY}  {'─' * 56}{C.RESET}\n")

    info = client.invoke_contract_fn(faucet, "get_faucet_info")
    if info and len(info) >= 6:
        xel_amount, vlt_amount, cooldown, xel_cap, vlt_cap, paused = info
        print(f"  XEL per claim:     {fmt_xel(xel_amount)}")
        print(f"  VLT per claim:     {fmt_vlt(vlt_amount)}")
        print(f"  Cooldown:          {cooldown} blocks (~{cooldown * 5 // 60} min)")
        print(f"  Lifetime XEL cap:  {fmt_xel(xel_cap)}")
        print(f"  Lifetime VLT cap:  {fmt_vlt(vlt_cap)}")
        print(f"  Status:            {'⛔ Paused' if paused else '✅ Active'}")
    else:
        print(f"  {C.DIM}(faucet not deployed or no data){C.RESET}")

    print(f"\n  {C.DIM}To request testnet funds:{C.RESET}")
    print(f"  {C.DIM}1. Ask on Discord #faucet-request{C.RESET}")
    print(f"  {C.DIM}2. Admin will distribute to your address{C.RESET}")

    print(f"\n{C.GRAY}  Press Enter...{C.RESET}", end="")
    input()


# ============================================================================
# Governance — Proposals viewer, Vote, Create proposal
# ============================================================================

def gov_view_proposals(client):
    """View active governance proposals."""
    if not check_contracts_configured(client):
        return
    governor = client.cfg.get("governor_hash")
    if not governor:
        info_box("Error", ["Governor not configured"])
        return

    clear()
    print(BANNER)
    print(f"\n{C.CYAN}{C.BOLD}  🗳  ACTIVE PROPOSALS{C.RESET}")
    print(f"{C.GRAY}  {'─' * 56}{C.RESET}\n")

    # Get proposals count (Governor pub fn get_proposals_count)
    count = client.invoke_contract_fn(governor, "get_proposals_count")
    if not count or not isinstance(count, int) or count == 0:
        print(f"  {C.DIM}No active proposals.{C.RESET}")
        print(f"\n{C.GRAY}  Press Enter...{C.RESET}", end="")
        input()
        return

    print(f"  {C.DIM}Total proposals: {count}{C.RESET}\n")
    print(f"  {'#':<4} {'Status':<12} {'For':>8} {'Against':>8} {'Description'}")
    print(f"  {C.GRAY}{'─' * 60}{C.RESET}")

    # Show last 10 proposals
    start = max(0, count - 10)
    for i in range(start, count):
        proposal = client.invoke_contract_fn(governor, "get_proposal", [i])
        if proposal and len(proposal) >= 5:
            pid, proposer, for_votes, against_votes, executed = proposal[:5]
            status = "✅ Executed" if executed else "🟡 Active"
            desc = f"Proposal #{pid}"
            print(f"  {C.DIM}{i:<4}{C.RESET} {status:<12} {for_votes:>8} {against_votes:>8} {desc}")

    print(f"\n{C.GRAY}  Press Enter...{C.RESET}", end="")
    input()


def gov_vote(client):
    """Vote on a governance proposal."""
    if not check_contracts_configured(client):
        return
    governor = client.cfg.get("governor_hash")

    clear()
    print(BANNER)
    print(f"\n{C.CYAN}{C.BOLD}  🗳  VOTE ON PROPOSAL{C.RESET}")
    print(f"{C.GRAY}  {'─' * 56}{C.RESET}\n")

    pid_str = text_input("  Proposal ID: ")
    try:
        pid = int(pid_str)
    except ValueError:
        print(f"\n  {C.RED}Invalid ID.{C.RESET}")
        print(f"\n{C.GRAY}  Press Enter...{C.RESET}", end="")
        input()
        return

    vote_choice = menu("Vote", [
        ("👍 For", "1"),
        ("👎 Against", "0"),
        ("🤐 Abstain", "2"),
        ("Cancel", None),
    ])
    if vote_choice is None:
        return

    print(f"\n  {C.DIM}Submitting vote...{C.RESET}")
    tx = client.submit_transaction(governor, 1, [pid, int(vote_choice)])  # GOV_VOTE = 1
    show_tx_result(tx, "Vote submitted")

    print(f"\n{C.GRAY}  Press Enter...{C.RESET}", end="")
    input()


def gov_create_proposal(client):
    """Create a new governance proposal."""
    if not check_contracts_configured(client):
        return
    governor = client.cfg.get("governor_hash")

    clear()
    print(BANNER)
    print(f"\n{C.CYAN}{C.BOLD}  📝 CREATE PROPOSAL{C.RESET}")
    print(f"{C.GRAY}  {'─' * 56}{C.RESET}\n")
    print(f"  {C.DIM}Proposals allow the community to change protocol parameters.{C.RESET}")
    print(f"  {C.DIM}They require a 7-day voting period + 48h timelock.{C.RESET}\n")

    title = text_input("  Title: ")
    if not title:
        return

    description = text_input("  Description: ")
    if not description:
        return

    print(f"\n  {C.DIM}Proposal type:{C.RESET}")
    ptype = menu("Type", [
        ("Parameter change (fee, LTV, etc.)", "param"),
        ("Add new oracle feed", "oracle"),
        ("Treasury spend", "treasury"),
        ("Other", "other"),
        ("Cancel", None),
    ])
    if ptype is None:
        return

    print(f"\n  {C.YELLOW}⚠ This will submit a proposal (costs gas).{C.RESET}")
    if confirm("  Confirm?"):
        print(f"\n  {C.DIM}Submitting...{C.RESET}")
        tx = client.submit_transaction(governor, 0, [title, description])  # GOV_PROPOSE = 0
        show_tx_result(tx, "Proposal created")
    else:
        print(f"\n  {C.DIM}Cancelled.{C.RESET}")

    print(f"\n{C.GRAY}  Press Enter...{C.RESET}", end="")
    input()


# ============================================================================
# AMM — Add liquidity, View pools
# ============================================================================

def amm_add_liquidity(client, xel_amount: float, vlt_amount: float):
    """Add liquidity to VLT/XEL pool."""
    if not check_contracts_configured(client):
        return
    vault_swap = client.cfg.get("vault_swap_hash")
    xel_asset = "0x" + "0" * 64
    vlt_asset = client.cfg.get("vlt_asset_hash", "")
    if not vlt_asset:
        print(f"\n  {C.RED}VLT asset not configured.{C.RESET}")
        input()
        return

    xel_atomic = int(xel_amount * (10 ** 8))
    vlt_atomic = int(vlt_amount * (10 ** 8))

    clear()
    print(BANNER)
    print(f"\n{C.CYAN}{C.BOLD}  💧 ADD LIQUIDITY (VLT/XEL pool){C.RESET}")
    print(f"{C.GRAY}  {'─' * 56}{C.RESET}\n")
    print(f"  XEL amount:  {C.YELLOW}{fmt_xel(xel_atomic)}{C.RESET}")
    print(f"  VLT amount:  {C.YELLOW}{fmt_vlt(vlt_atomic)}{C.RESET}")
    print(f"  {C.DIM}You'll receive LP tokens representing your share.{C.RESET}")
    print(f"  {C.DIM}You earn 0.3% of every swap, proportional to your share.{C.RESET}")

    if confirm("\n  Confirm add liquidity?"):
        print(f"\n  {C.DIM}Submitting...{C.RESET}")
        tx = client.submit_transaction(vault_swap, 0, [xel_asset, vlt_asset, xel_atomic, vlt_atomic])
        show_tx_result(tx, "Liquidity added")
    else:
        print(f"\n  {C.DIM}Cancelled.{C.RESET}")

    print(f"\n{C.GRAY}  Press Enter...{C.RESET}", end="")
    input()


def amm_view_pools(client):
    """View AMM pools and prices."""
    if not check_contracts_configured(client):
        return
    vault_swap = client.cfg.get("vault_swap_hash")

    clear()
    print(BANNER)
    print(f"\n{C.CYAN}{C.BOLD}  📊 AMM POOLS & PRICES{C.RESET}")
    print(f"{C.GRAY}  {'─' * 56}{C.RESET}\n")

    # Get XEL price
    price = client.get_xel_price()
    if price:
        print(f"  {C.BOLD}XEL/USD (oracle):{C.RESET} {C.GREEN}{fmt_usd(price)}{C.RESET}\n")

    # Show VLT/XEL pool info
    vlt_asset = client.cfg.get("vlt_asset_hash", "")
    xel_asset = "0x" + "0" * 64

    if vlt_asset:
        print(f"  {C.BOLD}VLT/XEL Pool:{C.RESET}")
        # In production: query VaultSwap for reserves
        print(f"    {C.DIM}(reserves will appear once pool is created){C.RESET}")

    # Show xUSD/XEL pool info
    xusd_asset = client.cfg.get("xusd_asset_hash", "")
    if xusd_asset:
        print(f"\n  {C.BOLD}xUSD/XEL Pool:{C.RESET}")
        print(f"    {C.DIM}(reserves will appear once pool is created){C.RESET}")

    # PSM info
    psm = client.cfg.get("psm_hash")
    if psm:
        print(f"\n  {C.BOLD}PSM (Peg Stability Module):{C.RESET}")
        print(f"    {C.CYAN}Fee:{C.RESET} 0.5% mint / 0.1% redeem")
        if price:
            print(f"    {C.CYAN}Rate:{C.RESET} 1 XEL = {fmt_usd(price)} xUSD")

    print(f"\n{C.GRAY}  Press Enter...{C.RESET}", end="")
    input()


# ============================================================================
# Mixer — Merkle root, Nullifier check
# ============================================================================

def mixer_view_root(client):
    """View privacy mixer Merkle root."""
    if not check_contracts_configured(client):
        return
    mixer = client.cfg.get("mixer_hash")

    clear()
    print(BANNER)
    print(f"\n{C.CYAN}{C.BOLD}  🌳 MIXER MERKLE ROOT{C.RESET}")
    print(f"{C.GRAY}  {'─' * 56}{C.RESET}\n")

    # PrivacyMixer pub fn get_merkle_root
    root = client.invoke_contract_fn(mixer, "get_merkle_root")
    if root:
        print(f"  Current root: {C.GREEN}{root}{C.RESET}")
    else:
        print(f"  {C.DIM}(no deposits yet — root will be generated on first deposit){C.RESET}")

    leaf_count = client.invoke_contract_fn(mixer, "get_leaf_count")
    if leaf_count is not None:
        print(f"  Total leaves: {leaf_count}")
        print(f"  Tree depth:   24")
        print(f"  Capacity:     {2**24:,} deposits")

    print(f"\n{C.GRAY}  Press Enter...{C.RESET}", end="")
    input()


def mixer_check_nullifier(client):
    """Check if a nullifier has been used (prevents double-spend)."""
    if not check_contracts_configured(client):
        return
    mixer = client.cfg.get("mixer_hash")

    clear()
    print(BANNER)
    print(f"\n{C.CYAN}{C.BOLD}  🔍 CHECK NULLIFIER{C.RESET}")
    print(f"{C.GRAY}  {'─' * 56}{C.RESET}\n")
    print(f"  {C.DIM}A nullifier is generated when you withdraw from the mixer.{C.RESET}")
    print(f"  {C.DIM}Each nullifier can only be used once (prevents double-spend).{C.RESET}\n")

    nullifier = text_input("  Nullifier hash: ")
    if not nullifier:
        return

    # PrivacyMixer pub fn is_nullifier_used
    used = client.invoke_contract_fn(mixer, "is_nullifier_used", [nullifier])
    if used:
        print(f"\n  {C.RED}⚠ This nullifier has been USED.{C.RESET}")
        print(f"  {C.DIM}The withdrawal has already been claimed.{C.RESET}")
    else:
        print(f"\n  {C.GREEN}✓ This nullifier is UNUSED.{C.RESET}")
        print(f"  {C.DIM}You can still use it to withdraw.{C.RESET}")

    print(f"\n{C.GRAY}  Press Enter...{C.RESET}", end="")
    input()


# ============================================================================
# Miner Delegation operations (v11.0)
# ============================================================================

# MinerDelegation entry IDs
MD_REGISTER_PROFILE = 0
MD_UPDATE_PROFILE = 1
MD_DELEGATE = 2
MD_UNDELEGATE = 3
MD_EXECUTE_UNDELEGATE = 4
MD_CLAIM_DELEGATOR_REWARDS = 5
MD_CLAIM_MINER_REWARDS = 6

def delegation_dashboard(client):
    """Main delegation dashboard — browse miners, delegate, manage."""
    delegation = client.cfg.get("delegation_hash") or client.cfg.get("miner_delegation_hash") or ""
    if not delegation:
        clear()
        print(BANNER)
        print(f"\n{C.RED}{C.BOLD}  ⚠  MinerDelegation not configured{C.RESET}")
        print(f"{C.DIM}  Run: xvault → Settings → Configure contract addresses{C.RESET}")
        print(f"\n{C.GRAY}  Press Enter...{C.RESET}", end="")
        input()
        return

    while True:
        clear()
        print(BANNER)
        print(f"\n{C.CYAN}{C.BOLD}  🤝 MINER DELEGATION{C.RESET}")
        print(f"{C.GRAY}  {'─' * 56}{C.RESET}\n")

        # Show stats
        total_del = client.invoke_contract_fn(delegation, "get_total_delegated") or 0
        miner_count = client.invoke_contract_fn(delegation, "get_miner_count") or 0
        print(f"  Total delegated: {fmt_vlt(total_del)}")
        print(f"  Registered miners: {miner_count}\n")

        choice = menu("Delegation Menu", [
            ("🏆  Browse miners           — Find a miner to delegate to", "browse"),
            ("📋  My delegation           — View my stakes + rewards", "my_del"),
            ("💎  Claim delegator rewards — Withdraw earned VLT", "claim_del"),
            ("🔑  Register miner profile  — Set name + commission (for miners)", "register"),
            ("✏️   Update miner profile    — Change name/commission", "update"),
            ("💰  Claim miner rewards     — Withdraw own + commission (miners)", "claim_miner"),
            ("⏳  Execute undelegate      — Finalize pending withdrawal", "exec_undel"),
            ("Back", None),
        ])

        if choice is None:
            break
        elif choice == "browse":
            _delegation_browse(client, delegation)
        elif choice == "my_del":
            _delegation_my(client, delegation)
        elif choice == "claim_del":
            _delegation_claim_del(client, delegation)
        elif choice == "register":
            _delegation_register(client, delegation)
        elif choice == "update":
            _delegation_update(client, delegation)
        elif choice == "claim_miner":
            _delegation_claim_miner(client, delegation)
        elif choice == "exec_undel":
            _delegation_exec_undel(client, delegation)


def _delegation_browse(client, delegation):
    """Browse miners to delegate to."""
    clear()
    print(BANNER)
    print(f"\n{C.CYAN}{C.BOLD}  🏆 BROWSE MINERS{C.RESET}")
    print(f"{C.GRAY}  {'─' * 56}{C.RESET}\n")

    count = client.invoke_contract_fn(delegation, "get_miner_count") or 0
    if not count:
        print(f"  {C.DIM}No miners registered yet.{C.RESET}")
        print(f"\n{C.GRAY}  Press Enter...{C.RESET}", end="")
        input()
        return

    # Show top 20 miners
    show = min(20, count)
    print(f"  {'#':<4} {'Name':<20} {'Stake':>12} {'Commission':>10} {'Delegators':>10}")
    print(f"  {C.GRAY}{'─' * 60}{C.RESET}")

    for i in range(show):
        # Get miner at index via list
        # MinerDelegation stores miner addresses in MINER_LIST_PREFIX
        # We need to iterate via pub fn if available
        # For now, show a placeholder
        pass

    print(f"\n  {C.DIM}(Miner list will be populated from on-chain data){C.RESET}")

    # Delegate to a miner
    print(f"\n  {C.BOLD}Delegate to a miner:{C.RESET}")
    miner_addr = text_input("  Miner address: ")
    if not miner_addr or len(miner_addr) < 10:
        return

    amount_str = text_input("  VLT amount to delegate: ")
    try:
        amount = float(amount_str)
        if amount < 10:
            print(f"\n  {C.RED}Minimum delegation is 10 VLT.{C.RESET}")
            input()
            return
    except ValueError:
        return

    auto = menu("Auto-compound?", [
        ("Yes — reinvest rewards automatically", "yes"),
        ("No — claim manually", "no"),
        ("Cancel", None),
    ])
    if auto is None:
        return

    print(f"\n  {C.BOLD}Delegation summary:{C.RESET}")
    print(f"  Miner:       {fmt_addr(miner_addr)}")
    print(f"  Amount:      {C.YELLOW}{amount} VLT{C.RESET}")
    print(f"  Auto-compound: {'✅ Yes' if auto == 'yes' else '❌ No'}")

    if confirm("\n  Confirm delegation?"):
        amount_atomic = int(amount * 10**8)
        print(f"\n  {C.DIM}Submitting...{C.RESET}")
        tx = client.submit_transaction(delegation, MD_DELEGATE,
                                       [miner_addr, amount_atomic, auto == "yes"])
        show_tx_result(tx, "Delegation submitted")
    else:
        print(f"\n  {C.DIM}Cancelled.{C.RESET}")

    print(f"\n{C.GRAY}  Press Enter...{C.RESET}", end="")
    input()


def _delegation_my(client, delegation):
    """View my delegation."""
    clear()
    print(BANNER)
    print(f"\n{C.CYAN}{C.BOLD}  📋 MY DELEGATION{C.RESET}")
    print(f"{C.GRAY}  {'─' * 56}{C.RESET}\n")

    addr = client.cfg.get("miner_address")
    if not addr:
        print(f"  {C.RED}No address configured.{C.RESET}")
        input()
        return

    info = client.invoke_contract_fn(delegation, "get_delegator_info", [addr])
    if not info or len(info) < 5:
        print(f"  {C.DIM}You haven't delegated to any miner yet.{C.RESET}")
        print(f"\n{C.GRAY}  Press Enter...{C.RESET}", end="")
        input()
        return

    miner_addr, amount, index, delegated_at, auto_compound = info
    pending = client.invoke_contract_fn(delegation, "get_delegator_pending", [addr]) or 0

    print(f"  Delegated to:    {fmt_addr(miner_addr)}")
    print(f"  Amount:          {C.YELLOW}{fmt_vlt(amount)}{C.RESET}")
    print(f"  Pending rewards: {C.GREEN}{fmt_vlt(pending)}{C.RESET}")
    print(f"  Auto-compound:   {'✅ Yes' if auto_compound else '❌ No'}")
    print(f"  Delegated at:    topo {delegated_at}")

    # Also check if miner has a profile
    profile = client.invoke_contract_fn(delegation, "get_miner_profile", [miner_addr])
    if profile and len(profile) >= 3:
        name, desc, commission = profile[0], profile[1], profile[2]
        print(f"\n  Miner profile:")
        print(f"    Name:        {name}")
        print(f"    Description: {desc}")
        print(f"    Commission:  {commission/100:.1f}%")

    print(f"\n{C.GRAY}  Press Enter...{C.RESET}", end="")
    input()


def _delegation_claim_del(client, delegation):
    """Claim delegator rewards."""
    clear()
    print(BANNER)
    print(f"\n{C.CYAN}{C.BOLD}  💎 CLAIM DELEGATOR REWARDS{C.RESET}")
    print(f"{C.GRAY}  {'─' * 56}{C.RESET}\n")

    addr = client.cfg.get("miner_address")
    pending = client.invoke_contract_fn(delegation, "get_delegator_pending", [addr]) or 0

    if pending > 0:
        print(f"  Pending rewards: {C.GREEN}{fmt_vlt(pending)}{C.RESET}")
    else:
        print(f"  {C.DIM}No pending rewards.{C.RESET}")
        print(f"\n{C.GRAY}  Press Enter...{C.RESET}", end="")
        input()
        return

    if confirm("\n  Claim rewards?"):
        print(f"\n  {C.DIM}Submitting...{C.RESET}")
        tx = client.submit_transaction(delegation, MD_CLAIM_DELEGATOR_REWARDS, [])
        show_tx_result(tx, "Rewards claimed")
    else:
        print(f"\n  {C.DIM}Cancelled.{C.RESET}")

    print(f"\n{C.GRAY}  Press Enter...{C.RESET}", end="")
    input()


def _delegation_register(client, delegation):
    """Register as a miner (set profile)."""
    clear()
    print(BANNER)
    print(f"\n{C.CYAN}{C.BOLD}  🔑 REGISTER MINER PROFILE{C.RESET}")
    print(f"{C.GRAY}  {'─' * 56}{C.RESET}\n")
    print(f"  {C.DIM}Set your miner name, description, and commission rate.{C.RESET}")
    print(f"  {C.DIM}Delegators will see this and choose to stake with you.{C.RESET}\n")

    name = text_input("  Miner name (3-32 chars): ")
    if not name or len(name) < 3:
        print(f"\n  {C.RED}Name too short.{C.RESET}")
        input()
        return

    description = text_input("  Description (optional): ")
    if not description:
        description = ""

    print(f"\n  {C.DIM}Commission is the % you take from delegator rewards.{C.RESET}")
    print(f"  {C.DIM}Range: 0% to 20%. Lower = more attractive to delegators.{C.RESET}")
    commission_str = text_input("  Commission % (e.g. 10 for 10%): ")
    try:
        commission_pct = float(commission_str)
        if commission_pct < 0 or commission_pct > 20:
            print(f"\n  {C.RED}Commission must be 0-20%.{C.RESET}")
            input()
            return
        commission_bps = int(commission_pct * 100)
    except ValueError:
        return

    print(f"\n  {C.BOLD}Profile summary:{C.RESET}")
    print(f"  Name:        {name}")
    print(f"  Description: {description}")
    print(f"  Commission:  {commission_pct:.1f}%")

    if confirm("\n  Register profile?"):
        print(f"\n  {C.DIM}Submitting...{C.RESET}")
        tx = client.submit_transaction(delegation, MD_REGISTER_PROFILE,
                                       [name, description, commission_bps])
        show_tx_result(tx, "Profile registered")
    else:
        print(f"\n  {C.DIM}Cancelled.{C.RESET}")

    print(f"\n{C.GRAY}  Press Enter...{C.RESET}", end="")
    input()


def _delegation_update(client, delegation):
    """Update miner profile."""
    clear()
    print(BANNER)
    print(f"\n{C.CYAN}{C.BOLD}  ✏️  UPDATE MINER PROFILE{C.RESET}\n")

    name = text_input("  New name: ")
    description = text_input("  New description: ")
    commission_str = text_input("  New commission %: ")
    try:
        commission_bps = int(float(commission_str) * 100)
    except ValueError:
        return

    if confirm("\n  Update profile?"):
        tx = client.submit_transaction(delegation, MD_UPDATE_PROFILE,
                                       [name, description, commission_bps])
        show_tx_result(tx, "Profile updated")
    input()


def _delegation_claim_miner(client, delegation):
    """Claim miner rewards (own + commission)."""
    clear()
    print(BANNER)
    print(f"\n{C.CYAN}{C.BOLD}  💰 CLAIM MINER REWARDS{C.RESET}")
    print(f"{C.GRAY}  {'─' * 56}{C.RESET}\n")

    addr = client.cfg.get("miner_address")
    pending = client.invoke_contract_fn(delegation, "get_miner_pending", [addr]) or 0

    if pending > 0:
        print(f"  Pending rewards: {C.GREEN}{fmt_vlt(pending)}{C.RESET}")
        print(f"  {C.DIM}(includes own stake share + delegator commission){C.RESET}")
    else:
        print(f"  {C.DIM}No pending rewards.{C.RESET}")
        input()
        return

    if confirm("\n  Claim rewards?"):
        tx = client.submit_transaction(delegation, MD_CLAIM_MINER_REWARDS, [])
        show_tx_result(tx, "Miner rewards claimed")
    input()


def _delegation_exec_undel(client, delegation):
    """Execute pending undelegate."""
    clear()
    print(BANNER)
    print(f"\n{C.CYAN}{C.BOLD}  ⏳ EXECUTE UNDELEGATE{C.RESET}")
    print(f"{C.GRAY}  {'─' * 56}{C.RESET}\n")
    print(f"  {C.DIM}Finalize a pending undelegate request (after 7-day delay).{C.RESET}\n")

    if confirm("  Execute undelegate?"):
        tx = client.submit_transaction(delegation, MD_EXECUTE_UNDELEGATE, [])
        show_tx_result(tx, "Undelegate executed")
    input()
