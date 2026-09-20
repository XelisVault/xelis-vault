#!/usr/bin/env python3
"""
============================================================================
 XELIS Vault v10.4 — Airdrop CLI module
============================================================================
Module interactif pour interagir avec l'AirdropTracker.
Permet aux utilisateurs de :
  - Voir leurs points et distribution estimée
  - Voir le leaderboard
  - Enregistrer leur adresse mainnet
  - Voir les stats globales
  - Voir les détails par catégorie
============================================================================
"""
from __future__ import annotations
import sys
from pathlib import Path
from typing import Any, Optional

try:
    import requests
except ImportError:
    print("Please install requests: pip install requests")
    sys.exit(1)

# Import TUI library
sys.path.insert(0, str(Path(__file__).parent))
from tui import *

# AirdropTracker entry IDs (must match AirdropTracker.slx)
ENTRY_RECORD_MAINNET_ADDR = 9
ENTRY_GET_USER_POINTS = 13  # pub fn (called as entry via getter)
ENTRY_GET_USER_BREAKDOWN = 14
ENTRY_GET_TOTAL_POINTS = 15
ENTRY_GET_USER_COUNT = 16
ENTRY_GET_USER_DISTRIBUTION = 17
ENTRY_GET_MAINNET_ADDRESS = 18
ENTRY_IS_FROZEN = 19
ENTRY_IS_FINALIZED = 20
ENTRY_GET_MERKLE_ROOT = 21
ENTRY_GET_QUALIFIED_USERS = 22

# v10.4.1 dashboard getters (pub fn)
GET_USER_AT_INDEX = "get_user_at_index"
GET_USER_RANK = "get_user_rank"
GET_ESTIMATED_DISTRIBUTION = "get_estimated_distribution"
GET_USER_PERCENTAGE = "get_user_percentage"
GET_CATEGORY_TOTAL = "get_category_total"
GET_ALL_CATEGORY_TOTALS = "get_all_category_totals"
GET_TESTNET_ADDRESS = "get_testnet_address"
GET_SNAPSHOT_INFO = "get_snapshot_info"
GET_USER_ACTIVITY_SUMMARY = "get_user_activity_summary"
GET_PROTOCOL_STATS = "get_protocol_stats"
GET_LEADERBOARD_AT_RANK = "get_leaderboard_at_rank"
GET_LEADERBOARD_ENTRY = "get_leaderboard_entry"
IS_QUALIFIED = "is_qualified"
GET_TOTAL_DISTRIBUTABLE = "get_total_distributable"
GET_USER_FULL_INFO = "get_user_full_info"

CATEGORY_NAMES = {
    1: "Mining",
    2: "Relayer",
    3: "Governance",
    4: "Chat",
    5: "Liquidity",
    6: "Bounty",
    7: "Community",
}

VLT_DECIMALS = 8


class AirdropClient:
    """Client for interacting with AirdropTracker contract."""

    def __init__(self, config, xelis_client):
        self.cfg = config
        self.client = xelis_client
        self.tracker_hash = config.get("airdrop_tracker_hash") or ""

    def is_configured(self) -> bool:
        return bool(self.tracker_hash and self.tracker_hash != "0x" + "0" * 64)

    def call_entry(self, entry_id: int, params: list = None) -> Any:
        """Call an entry function on AirdropTracker (read-only via invoke)."""
        if not self.is_configured():
            return None
        try:
            r = self.client.rpc("invoke_contract", [
                self.tracker_hash,
                entry_id,
                params or [],
            ])
            return r
        except:
            return None

    def call_getter(self, fn_name: str, params: list = None) -> Any:
        """Call a pub fn on AirdropTracker (read-only via get_contract_call_result)."""
        if not self.is_configured():
            return None
        try:
            r = self.client.rpc("invoke_contract_fn", [
                self.tracker_hash,
                fn_name,
                params or [],
            ])
            return r
        except:
            return None

    def submit_tx(self, entry_id: int, params: list = None, fee: int = 100000) -> str:
        """Submit a transaction to AirdropTracker."""
        if not self.is_configured():
            return ""
        try:
            r = self.client.wallet_rpc("submit_transaction", [
                self.cfg.get("miner_address"),
                self.tracker_hash,
                {"entry_id": entry_id, "args": params or []},
                fee,
            ])
            return r or ""
        except:
            return ""

    # === Read functions ===

    def get_protocol_stats(self):
        """Returns (user_count, qualified_count, total_points, total_distributable, frozen, finalized)."""
        return self.call_getter(GET_PROTOCOL_STATS) or (0, 0, 0, 0, False, False)

    def get_user_full_info(self, user_addr: str):
        """Returns (mining, relayer, gov, chat, liq, bounty, community, total_raw, total_with_bonus, days_active, mainnet_addr, qualified, rank)."""
        return self.call_getter(GET_USER_FULL_INFO, [user_addr])

    def get_user_points(self, user_addr: str) -> int:
        return self.call_getter("get_user_points", [user_addr]) or 0

    def get_estimated_distribution(self, user_addr: str) -> int:
        return self.call_getter(GET_ESTIMATED_DISTRIBUTION, [user_addr]) or 0

    def get_user_distribution(self, user_addr: str) -> int:
        return self.call_getter("get_user_distribution", [user_addr]) or 0

    def get_user_percentage(self, user_addr: str) -> int:
        return self.call_getter(GET_USER_PERCENTAGE, [user_addr]) or 0

    def get_user_rank(self, user_addr: str) -> int:
        return self.call_getter(GET_USER_RANK, [user_addr]) or 0

    def get_user_activity_summary(self, user_addr: str):
        return self.call_getter(GET_USER_ACTIVITY_SUMMARY, [user_addr]) or (0, 0, False, False)

    def get_all_category_totals(self):
        return self.call_getter(GET_ALL_CATEGORY_TOTALS) or (0, 0, 0, 0, 0, 0, 0)

    def get_category_total(self, category: int) -> int:
        return self.call_getter(GET_CATEGORY_TOTAL, [category]) or 0

    def get_leaderboard_entry(self, rank: int):
        """Returns (testnet_addr, points, qualified, mainnet_addr, distribution)."""
        return self.call_getter(GET_LEADERBOARD_ENTRY, [rank])

    def get_user_at_index(self, index: int) -> str:
        return self.call_getter(GET_USER_AT_INDEX, [index]) or ""

    def get_snapshot_info(self):
        """Returns (deploy_topo, freeze_topo, finalize_topo, current_topo)."""
        return self.call_getter(GET_SNAPSHOT_INFO) or (0, 0, 0, 0)

    def is_frozen(self) -> bool:
        return self.call_getter("is_frozen") or False

    def is_finalized(self) -> bool:
        return self.call_getter("is_finalized") or False

    def get_total_distributable(self) -> int:
        return self.call_getter(GET_TOTAL_DISTRIBUTABLE) or 0

    def get_merkle_root(self) -> str:
        return self.call_getter("get_merkle_root") or ""

    def is_qualified(self, user_addr: str) -> bool:
        return self.call_getter(IS_QUALIFIED, [user_addr]) or False

    def get_mainnet_address(self, user_addr: str) -> str:
        return self.call_getter("get_mainnet_address", [user_addr]) or ""

    def get_testnet_address(self, mainnet_addr: str) -> str:
        return self.call_getter(GET_TESTNET_ADDRESS, [mainnet_addr]) or ""

    def get_user_count(self) -> int:
        return self.call_getter("get_user_count") or 0

    def get_qualified_users(self) -> int:
        return self.call_getter("get_qualified_users") or 0

    def get_total_points(self) -> int:
        return self.call_getter("get_total_points") or 0

    # === Write functions ===

    def record_mainnet_address(self, mainnet_addr: str) -> str:
        """Submit a transaction to record the user's mainnet address."""
        return self.submit_tx(ENTRY_RECORD_MAINNET_ADDR, [mainnet_addr])


def fmt_vlt(amount_atomic: int) -> str:
    """Format atomic VLT amount to human-readable string."""
    if not amount_atomic:
        return "0 VLT"
    vlt = amount_atomic / (10 ** VLT_DECIMALS)
    if vlt >= 1000:
        return f"{vlt:,.2f} VLT"
    return f"{vlt:.4f} VLT"


def fmt_points(points: int) -> str:
    """Format points with thousands separator."""
    if not points:
        return "0"
    return f"{points:,}"


def fmt_addr(addr: str) -> str:
    """Truncate address for display."""
    if not addr or addr == "0x" + "0" * 64:
        return "(not set)"
    if len(addr) > 20:
        return addr[:12] + "..." + addr[-8:]
    return addr


def fmt_bps(bps: int) -> str:
    """Format basis points to percentage string."""
    return f"{bps / 100:.2f}%"


def fmt_topo(topo: int) -> str:
    """Format topoheight (or 0 if not set)."""
    if not topo:
        return "—"
    return str(topo)


def fmt_days_active(days: int) -> str:
    """Format days active with qualification indicator."""
    if days >= 7:
        return f"{days} ✓"
    return f"{days} (need {7 - days} more)"


def screen_airdrop_dashboard(client: XelisClient, airdrop: AirdropClient):
    """Main airdrop dashboard screen."""
    if not airdrop.is_configured():
        clear()
        print(BANNER)
        print(f"\n{C.RED}{C.BOLD}  ⚠  AirdropTracker not configured{C.RESET}")
        print(f"{C.DIM}  Run 'xvault --setup' to configure the airdrop contract address.{C.RESET}")
        print(f"\n{C.GRAY}  Press Enter to continue...{C.RESET}", end="")
        input()
        return

    while True:
        clear()
        print(BANNER)

        user_addr = client.cfg.get("miner_address") or ""
        stats = airdrop.get_protocol_stats()
        user_count = stats[0] if stats else 0
        qualified_count = stats[1] if stats else 1
        total_points = stats[2] if stats else 2
        total_distributable = stats[3] if stats else 3
        frozen = stats[4] if stats else 4
        finalized = stats[5] if stats else 5

        print(f"\n{C.CYAN}{C.BOLD}  🪂 AIRDROP DASHBOARD{C.RESET}")
        print(f"{C.GRAY}  {'─' * 56}{C.RESET}")

        # Status badge
        if finalized:
            status = f"{C.GREEN}✓ Finalized{C.RESET}"
        elif frozen:
            status = f"{C.YELLOW}⏸ Frozen (snapshot taken){C.RESET}"
        else:
            status = f"{C.GREEN}● Active (earn points now){C.RESET}"

        print(f"  Status:           {status}")
        print(f"  Participants:     {C.BOLD}{user_count:,}{C.RESET}")
        print(f"  Qualified:        {C.GREEN}{qualified_count:,}{C.RESET}")
        print(f"  Total points:     {C.BOLD}{fmt_points(total_points)}{C.RESET}")
        print(f"  Distributable:    {C.YELLOW}{fmt_vlt(total_distributable)}{C.RESET}")

        # Snapshot timeline
        snap = airdrop.get_snapshot_info()
        if snap and snap[0]:
            print(f"\n{C.DIM}  Timeline:{C.RESET}")
            print(f"  {C.DIM}• Deploy:{C.RESET}     topo {fmt_topo(snap[0])}")
            print(f"  {C.DIM}• Frozen:{C.RESET}     topo {fmt_topo(snap[1])}")
            print(f"  {C.DIM}• Finalized:{C.RESET}  topo {fmt_topo(snap[2])}")
            print(f"  {C.DIM}• Current:{C.RESET}    topo {fmt_topo(snap[3])}")

        # My stats (if address is set)
        if user_addr:
            print(f"\n{C.CYAN}{C.BOLD}  📊 MY STATS{C.RESET}")
            print(f"{C.GRAY}  {'─' * 56}{C.RESET}")
            info = airdrop.get_user_full_info(user_addr)
            if info and len(info) >= 13:
                mining, relayer, gov, chat, liq, bounty, community = info[0:7]
                total_raw, total_with_bonus, days_active, mainnet_addr, qualified, rank = info[7:13]

                print(f"  My points:        {C.BOLD}{fmt_points(total_raw)}{C.RESET}")
                if total_with_bonus and total_with_bonus != total_raw:
                    print(f"  With bonus:       {C.GREEN}{fmt_points(total_with_bonus)}{C.RESET}")
                print(f"  My rank:          #{C.BOLD}{rank or '—'}{C.RESET} / {user_count:,}")
                pct = airdrop.get_user_percentage(user_addr)
                print(f"  My share:         {fmt_bps(pct)}")

                if frozen or finalized:
                    dist = airdrop.get_user_distribution(user_addr)
                    print(f"  My VLT:           {C.YELLOW}{fmt_vlt(dist)}{C.RESET}")
                else:
                    est = airdrop.get_estimated_distribution(user_addr)
                    print(f"  Est. VLT:         {C.YELLOW}{fmt_vlt(est)}{C.RESET}")

                print(f"  Days active:      {fmt_days_active(days_active)}")
                print(f"  Qualified:        {C.GREEN + '✓ YES' if qualified else C.RED + '✗ NO' + C.RESET}")
                print(f"  Mainnet addr:     {fmt_addr(mainnet_addr)}")
            else:
                print(f"  {C.DIM}(no activity yet — start mining, chatting, or voting!){C.RESET}")

        print(f"\n{C.GRAY}  {'─' * 56}{C.RESET}")

        choice = menu("Airdrop Menu", [
            ("🏆  Leaderboard           — Top contributors", "leaderboard"),
            ("📋  My breakdown          — Points per category", "breakdown"),
            ("🎯  Register mainnet addr  — For claim on mainnet", "register"),
            ("📈  Category stats        — Points by category", "categories"),
            ("🔍  Lookup user           — Search by address", "lookup"),
            ("ℹ️   How to earn points    — Guide", "guide"),
            ("🔐  Admin panel           — Manage airdrop (admin only)", "admin"),
            ("Back", None),
        ])

        if choice is None:
            break
        elif choice == "leaderboard":
            _airdrop_leaderboard(airdrop)
        elif choice == "breakdown":
            _airdrop_breakdown(airdrop, user_addr)
        elif choice == "register":
            _airdrop_register_mainnet(airdrop, user_addr)
        elif choice == "categories":
            _airdrop_categories(airdrop)
        elif choice == "admin":
            screen_airdrop_admin(client, airdrop)
        elif choice == "lookup":
            _airdrop_lookup(airdrop)
        elif choice == "guide":
            _airdrop_guide()


def _airdrop_leaderboard(airdrop: AirdropClient):
    """Show top contributors."""
    clear()
    print(BANNER)
    print(f"\n{C.CYAN}{C.BOLD}  🏆 LEADERBOARD — Top 20 Contributors{C.RESET}")
    print(f"{C.GRAY}  {'─' * 56}{C.RESET}\n")

    user_count = airdrop.get_user_count()
    if not user_count:
        print(f"  {C.DIM}No participants yet. Be the first!{C.RESET}")
        print(f"\n{C.GRAY}  Press Enter to continue...{C.RESET}", end="")
        input()
        return

    # Get top 20 (or all if less)
    top_n = min(20, user_count)

    print(f"  {'#':<4} {'Address':<24} {'Points':>12} {'VLT':>14} {'Status':<8}")
    print(f"  {C.GRAY}{'─' * 70}{C.RESET}")

    for rank in range(1, top_n + 1):
        entry = airdrop.get_leaderboard_entry(rank)
        if not entry or len(entry) < 5:
            continue
        addr, points, qualified, mainnet_addr, distribution = entry

        addr_str = fmt_addr(addr) if addr else "(unknown)"
        points_str = fmt_points(points) if points else "0"
        vlt_str = fmt_vlt(distribution) if distribution else "—"

        if qualified:
            status = f"{C.GREEN}✓{C.RESET}"
        else:
            status = f"{C.DIM}—{C.RESET}"

        # Highlight rank 1-3
        if rank == 1:
            rank_str = f"{C.YELLOW}🥇{C.RESET}"
        elif rank == 2:
            rank_str = f"{C.WHITE}🥈{C.RESET}"
        elif rank == 3:
            rank_str = f"{C.RED}🥉{C.RESET}"
        else:
            rank_str = f"{C.DIM}{rank:>2}{C.RESET}"

        print(f"  {rank_str:<6} {addr_str:<24} {C.BOLD}{points_str:>12}{C.RESET} {C.YELLOW}{vlt_str:>14}{C.RESET} {status}")

    if user_count > top_n:
        print(f"\n  {C.DIM}... and {user_count - top_n} more participants{C.RESET}")

    print(f"\n{C.GRAY}  Press Enter to continue...{C.RESET}", end="")
    input()


def _airdrop_breakdown(airdrop: AirdropClient, user_addr: str):
    """Show user's points breakdown by category."""
    if not user_addr:
        print(f"\n{C.RED}  No wallet address configured.{C.RESET}")
        print(f"\n{C.GRAY}  Press Enter...{C.RESET}", end="")
        input()
        return

    clear()
    print(BANNER)
    print(f"\n{C.CYAN}{C.BOLD}  📋 MY POINTS BREAKDOWN{C.RESET}")
    print(f"{C.GRAY}  {'─' * 56}{C.RESET}\n")

    info = airdrop.get_user_full_info(user_addr)
    if not info or len(info) < 13:
        print(f"  {C.DIM}No data yet. Start interacting with the protocol!{C.RESET}")
        print(f"\n{C.GRAY}  Press Enter...{C.RESET}", end="")
        input()
        return

    mining, relayer, gov, chat, liq, bounty, community = info[0:7]
    total_raw, total_with_bonus, days_active, mainnet_addr, qualified, rank = info[7:13]

    categories = [
        ("⛏  Mining", mining, "Price submissions + uptime"),
        ("📡 Relayer", relayer, "Anchoring chat messages"),
        ("🗳  Governance", gov, "Voting + proposals"),
        ("💬 Chat", chat, "Messages + groups created"),
        ("💧 Liquidity", liq, "Deposits, LP, PSM"),
        ("🐛 Bounty", bounty, "Bug reports"),
        ("👥 Community", community, "Discord help, docs"),
    ]

    print(f"  {'Category':<20} {'Points':>10}  {C.DIM}{'How to earn':<30}{C.RESET}")
    print(f"  {C.GRAY}{'─' * 64}{C.RESET}")

    for name, points, how in categories:
        points_str = fmt_points(points) if points else f"{C.DIM}0{C.RESET}"
        bar_len = min(int(points / 100), 20) if points else 0
        bar = C.CYAN + "█" * bar_len + C.RESET + C.DIM + "░" * (20 - bar_len) + C.RESET
        print(f"  {name:<20} {C.BOLD}{points_str:>10}{C.RESET}  {bar}")

    print(f"  {C.GRAY}{'─' * 64}{C.RESET}")
    print(f"  {'TOTAL':<20} {C.BOLD}{C.YELLOW}{fmt_points(total_raw):>10}{C.RESET}")

    if total_with_bonus and total_with_bonus != total_raw:
        bonus_pct = ((total_with_bonus - total_raw) * 100) / max(total_raw, 1)
        print(f"  {'With bonus':<20} {C.GREEN}{fmt_points(total_with_bonus):>10}{C.RESET} {C.DIM}(+{bonus_pct:.1f}%){C.RESET}")

    print(f"\n  {C.DIM}Rank: #{rank or '—'} / qualified: {'✓' if qualified else '✗'}{C.RESET}")
    print(f"  {C.DIM}Days active: {days_active} (need 7 to qualify){C.RESET}")

    if not qualified:
        print(f"\n  {C.YELLOW}⚠ To qualify you need:{C.RESET}")
        if total_raw < 1000:
            print(f"  {C.DIM}• {fmt_points(1000 - total_raw)} more points (min 1,000){C.RESET}")
        if days_active < 7:
            print(f"  {C.DIM}• {7 - days_active} more active days (min 7){C.RESET}")
        if not mainnet_addr or mainnet_addr == "0x" + "0" * 64:
            print(f"  {C.DIM}• Register your mainnet address{C.RESET}")

    print(f"\n{C.GRAY}  Press Enter...{C.RESET}", end="")
    input()


def _airdrop_register_mainnet(airdrop: AirdropClient, user_addr: str):
    """Register mainnet address."""
    if not user_addr:
        print(f"\n{C.RED}  No wallet address configured.{C.RESET}")
        print(f"\n{C.GRAY}  Press Enter...{C.RESET}", end="")
        input()
        return

    clear()
    print(BANNER)
    print(f"\n{C.CYAN}{C.BOLD}  🎯 REGISTER MAINNET ADDRESS{C.RESET}")
    print(f"{C.GRAY}  {'─' * 56}{C.RESET}\n")

    # Check if frozen
    if airdrop.is_frozen():
        print(f"  {C.RED}⚠ Points are frozen. You can no longer register your mainnet address.{C.RESET}")
        print(f"\n{C.GRAY}  Press Enter...{C.RESET}", end="")
        input()
        return

    # Show current address
    current = airdrop.get_mainnet_address(user_addr)
    if current and current != "0x" + "0" * 64:
        print(f"  {C.DIM}Current mainnet address:{C.RESET}")
        print(f"  {C.GREEN}{current}{C.RESET}\n")
        choice = menu("Update your mainnet address?", [
            ("Yes, change it", "yes"),
            ("No, keep it", None),
        ])
        if choice != "yes":
            return

    print(f"  {C.BOLD}Enter your XELIS MAINNET address:{C.RESET}")
    print(f"  {C.DIM}(the address where you'll receive your VLT airdrop){C.RESET}")
    print(f"  {C.DIM}(must be different from your testnet address){C.RESET}\n")

    mainnet_addr = text_input("  Mainnet address: ")

    if not mainnet_addr or len(mainnet_addr) < 10:
        print(f"\n  {C.RED}Invalid address.{C.RESET}")
        print(f"\n{C.GRAY}  Press Enter...{C.RESET}", end="")
        input()
        return

    # Check if already used
    existing_testnet = airdrop.get_testnet_address(mainnet_addr)
    if existing_testnet and existing_testnet != user_addr:
        print(f"\n  {C.RED}⚠ This mainnet address is already used by another testnet user.{C.RESET}")
        print(f"  {C.DIM}Each mainnet address can only be linked to one testnet account.{C.RESET}")
        print(f"\n{C.GRAY}  Press Enter...{C.RESET}", end="")
        input()
        return

    # Confirm
    clear()
    print(BANNER)
    print(f"\n{C.CYAN}{C.BOLD}  ⚠ CONFIRM REGISTRATION{C.RESET}")
    print(f"{C.GRAY}  {'─' * 56}{C.RESET}\n")
    print(f"  Testnet address:   {C.DIM}{user_addr}{C.RESET}")
    print(f"  Mainnet address:   {C.YELLOW}{mainnet_addr}{C.RESET}")
    print(f"\n  {C.YELLOW}This will submit a transaction (costs gas).{C.RESET}")

    if confirm("  Confirm registration?"):
        print(f"\n  {C.DIM}Submitting transaction...{C.RESET}")
        tx_hash = airdrop.record_mainnet_address(mainnet_addr)
        if tx_hash:
            print(f"\n  {C.GREEN}✓ Transaction submitted!{C.RESET}")
            print(f"  {C.DIM}TX: {tx_hash[:30]}...{C.RESET}")
        else:
            print(f"\n  {C.RED}✗ Failed to submit transaction.{C.RESET}")
            print(f"  {C.DIM}Check your wallet is running and has balance.{C.RESET}")
    else:
        print(f"\n  {C.DIM}Cancelled.{C.RESET}")

    print(f"\n{C.GRAY}  Press Enter...{C.RESET}", end="")
    input()


def _airdrop_categories(airdrop: AirdropClient):
    """Show category totals."""
    clear()
    print(BANNER)
    print(f"\n{C.CYAN}{C.BOLD}  📈 CATEGORY STATS — All Participants{C.RESET}")
    print(f"{C.GRAY}  {'─' * 56}{C.RESET}\n")

    totals = airdrop.get_all_category_totals()
    if not totals or len(totals) < 7:
        print(f"  {C.DIM}No data yet.{C.RESET}")
        print(f"\n{C.GRAY}  Press Enter...{C.RESET}", end="")
        input()
        return

    categories = [
        ("⛏  Mining", totals[0], "Price submissions + uptime", "Run xvault-miner"),
        ("📡 Relayer", totals[1], "Anchoring chat messages", "Run xvault-relayer"),
        ("🗳  Governance", totals[2], "Voting + proposals", "Stake VLT + vote"),
        ("💬 Chat", totals[3], "Messages + groups created", "Use VaultChat"),
        ("💧 Liquidity", totals[4], "Deposits, LP, PSM", "Deposit in VaultEngine"),
        ("🐛 Bounty", totals[5], "Bug reports", "Report bugs on Discord"),
        ("👥 Community", totals[6], "Discord help, docs", "Help on Discord"),
    ]

    grand_total = sum(totals)

    print(f"  {'Category':<20} {'Points':>12} {'%':>8}  {C.DIM}{'How to earn':<30}{C.RESET}")
    print(f"  {C.GRAY}{'─' * 76}{C.RESET}")

    for name, points, how, action in categories:
        pct = (points * 100 / grand_total) if grand_total else 0
        bar_len = min(int(points * 30 / max(grand_total, 1)), 30)
        bar = C.CYAN + "█" * bar_len + C.RESET + C.DIM + "░" * (30 - bar_len) + C.RESET
        print(f"  {name:<20} {C.BOLD}{fmt_points(points):>12}{C.RESET} {pct:>7.1f}% {bar}")
        print(f"  {C.DIM}{'':>20} {'':>12} {'':>8}  {how}{C.RESET}")

    print(f"  {C.GRAY}{'─' * 76}{C.RESET}")
    print(f"  {'TOTAL':<20} {C.BOLD}{C.YELLOW}{fmt_points(grand_total):>12}{C.RESET}")

    print(f"\n{C.GRAY}  Press Enter...{C.RESET}", end="")
    input()


def _airdrop_lookup(airdrop: AirdropClient):
    """Look up a user by address."""
    clear()
    print(BANNER)
    print(f"\n{C.CYAN}{C.BOLD}  🔍 LOOKUP USER{C.RESET}")
    print(f"{C.GRAY}  {'─' * 56}{C.RESET}\n")

    addr = text_input("  Enter testnet address: ")
    if not addr or len(addr) < 10:
        print(f"\n  {C.RED}Invalid address.{C.RESET}")
        print(f"\n{C.GRAY}  Press Enter...{C.RESET}", end="")
        input()
        return

    info = airdrop.get_user_full_info(addr)
    if not info or len(info) < 13:
        print(f"\n  {C.DIM}User not found or no activity.{C.RESET}")
        print(f"\n{C.GRAY}  Press Enter...{C.RESET}", end="")
        input()
        return

    mining, relayer, gov, chat, liq, bounty, community = info[0:7]
    total_raw, total_with_bonus, days_active, mainnet_addr, qualified, rank = info[7:13]

    clear()
    print(BANNER)
    print(f"\n{C.CYAN}{C.BOLD}  👤 USER PROFILE{C.RESET}")
    print(f"{C.GRAY}  {'─' * 56}{C.RESET}\n")

    print(f"  Testnet address:   {C.DIM}{addr}{C.RESET}")
    print(f"  Mainnet address:   {fmt_addr(mainnet_addr)}")
    print(f"  Rank:              #{C.BOLD}{rank or '—'}{C.RESET}")
    print(f"  Qualified:         {C.GREEN + '✓ YES' if qualified else C.RED + '✗ NO' + C.RESET}")
    print(f"  Days active:       {days_active}")

    print(f"\n  {C.CYAN}Points by category:{C.RESET}")
    categories = [
        ("Mining", mining),
        ("Relayer", relayer),
        ("Governance", gov),
        ("Chat", chat),
        ("Liquidity", liq),
        ("Bounty", bounty),
        ("Community", community),
    ]
    for name, pts in categories:
        bar_len = min(int(pts / 100), 20)
        bar = C.CYAN + "█" * bar_len + C.RESET + C.DIM + "░" * (20 - bar_len) + C.RESET
        print(f"  {name:<15} {C.BOLD}{fmt_points(pts):>10}{C.RESET} {bar}")

    print(f"\n  {C.BOLD}Total: {C.YELLOW}{fmt_points(total_raw)}{C.RESET}")
    if total_with_bonus and total_with_bonus != total_raw:
        print(f"  {C.GREEN}With bonus: {fmt_points(total_with_bonus)}{C.RESET}")

    est = airdrop.get_estimated_distribution(addr)
    if est:
        print(f"  {C.YELLOW}Estimated VLT: {fmt_vlt(est)}{C.RESET}")

    print(f"\n{C.GRAY}  Press Enter...{C.RESET}", end="")
    input()


def _airdrop_guide():
    """Show how to earn points."""
    clear()
    print(BANNER)
    print(f"\n{C.CYAN}{C.BOLD}  ℹ️  HOW TO EARN AIRDROP POINTS{C.RESET}")
    print(f"{C.GRAY}  {'─' * 56}{C.RESET}\n")

    print(f"  {C.YELLOW}🎯 Total airdrop: 500,000 VLT{C.RESET}")
    print(f"  {C.DIM}Distributed proportionally to your points vs total points.{C.RESET}\n")

    print(f"  {C.CYAN}{C.BOLD}━━━ MINING (1-1000 pts/day) ━━━{C.RESET}")
    print(f"  {C.DIM}• 1 point per valid price submission{C.RESET}")
    print(f"  {C.DIM}• 50 points per hour of miner uptime{C.RESET}")
    print(f"  {C.BOLD}→ Run: xvault-miner{C.RESET}\n")

    print(f"  {C.CYAN}{C.BOLD}━━━ RELAYER (10-500 pts/day) ━━━{C.RESET}")
    print(f"  {C.DIM}• 10 points per valid anchor (≥5 messages){C.RESET}")
    print(f"  {C.DIM}• 200 points per day of uptime{C.RESET}")
    print(f"  {C.BOLD}→ Run: xvault-relayer{C.RESET}\n")

    print(f"  {C.CYAN}{C.BOLD}━━━ GOVERNANCE (50-500 pts/action) ━━━{C.RESET}")
    print(f"  {C.DIM}• 50 points per vote{C.RESET}")
    print(f"  {C.DIM}• 500 points per proposal created{C.RESET}")
    print(f"  {C.BOLD}→ Use: xvault → Governance{C.RESET}\n")

    print(f"  {C.CYAN}{C.BOLD}━━━ CHAT (1-100 pts/day) ━━━{C.RESET}")
    print(f"  {C.DIM}• 1 point per message sent{C.RESET}")
    print(f"  {C.DIM}• 100 points per group created{C.RESET}")
    print(f"  {C.BOLD}→ Use: xvault → Chat{C.RESET}\n")

    print(f"  {C.CYAN}{C.BOLD}━━━ LIQUIDITY (10 pts/XEL) ━━━{C.RESET}")
    print(f"  {C.DIM}• 10 points per XEL deposited{C.RESET}")
    print(f"  {C.DIM}• In VaultEngine, VaultSwap, or PSM{C.RESET}")
    print(f"  {C.BOLD}→ Use: xvault → Vault or Swap{C.RESET}\n")

    print(f"  {C.CYAN}{C.BOLD}━━━ BOUNTY (200-5000 pts) ━━━{C.RESET}")
    print(f"  {C.DIM}• 5,000 points: critical bug{C.RESET}")
    print(f"  {C.DIM}• 1,000 points: high severity bug{C.RESET}")
    print(f"  {C.DIM}• 200 points: medium severity bug{C.RESET}")
    print(f"  {C.BOLD}→ Report on Discord #bug-bounty{C.RESET}\n")

    print(f"  {C.CYAN}{C.BOLD}━━━ COMMUNITY (50-200 pts) ━━━{C.RESET}")
    print(f"  {C.DIM}• 50 points: help someone on Discord{C.RESET}")
    print(f"  {C.DIM}• 200 points: write a doc or tutorial{C.RESET}")
    print(f"  {C.BOLD}→ Be active on Discord{C.RESET}\n")

    print(f"  {C.YELLOW}{C.BOLD}━━━ QUALIFICATION (REQUIRED) ━━━{C.RESET}")
    print(f"  {C.DIM}• Minimum 1,000 points total{C.RESET}")
    print(f"  {C.DIM}• Minimum 7 distinct days of activity{C.RESET}")
    print(f"  {C.DIM}• Register your mainnet address (via xvault → Airdrop){C.RESET}\n")

    print(f"  {C.GREEN}{C.BOLD}━━━ BONUS ━━━{C.RESET}")
    print(f"  {C.DIM}• +25% if active in 3+ categories (multi-role){C.RESET}\n")

    print(f"  {C.GRAY}  Press Enter...{C.RESET}", end="")
    input()


# ============================================================================
# Admin functions — for the protocol admin to manage the airdrop
# ============================================================================

# Admin entry IDs
ENTRY_RECORD_MANUAL_ATTRIBUTION = 8
ENTRY_RECORD_MANUAL_ATTRIBUTION_BATCH = 32
ENTRY_DEDUCT_POINTS = 33
ENTRY_DISQUALIFY_USER = 34
ENTRY_REVOKE_DISQUALIFICATION = 35
ENTRY_FORCE_QUALIFY_USER = 36
ENTRY_REVOKE_FORCE_QUALIFICATION = 37
ENTRY_SET_USER_BONUS_MULTIPLIER = 38
ENTRY_SET_MANUAL_ATTRIBUTION_CAP = 39

# Admin log action types
ACTION_NAMES = {
    1: "Add points",
    2: "Deduct points",
    3: "Disqualify/Revoke",
    4: "Force-qualify/Revoke",
    5: "Set multiplier",
    6: "Batch add",
}


def is_admin(airdrop: AirdropClient, user_addr: str) -> bool:
    """Check if the user is the admin (simplified — in production, query the contract)."""
    # The admin check is done on-chain by only_admin()
    # Here we just return True if user has an address
    return bool(user_addr and user_addr != "(not set)")


def screen_airdrop_admin(client: XelisClient, airdrop: AirdropClient):
    """Admin panel for managing the airdrop."""
    user_addr = client.cfg.get("miner_address") or ""

    if not is_admin(airdrop, user_addr):
        clear()
        print(BANNER)
        print(f"\n{C.RED}{C.BOLD}  ⚠  Admin access required{C.RESET}")
        print(f"{C.DIM}  Only the protocol admin can access this panel.{C.RESET}")
        print(f"\n{C.GRAY}  Press Enter to continue...{C.RESET}", end="")
        input()
        return

    while True:
        clear()
        print(BANNER)
        print(f"\n{C.RED}{C.BOLD}  🔐 AIRDROP ADMIN PANEL{C.RESET}")
        print(f"{C.GRAY}  {'─' * 56}{C.RESET}\n")

        # Show current state
        stats = airdrop.get_protocol_stats()
        if stats and len(stats) >= 6:
            frozen = stats[4]
            finalized = stats[5]
            if finalized:
                status = f"{C.GREEN}Finalized{C.RESET}"
            elif frozen:
                status = f"{C.YELLOW}Frozen{C.RESET}"
            else:
                status = f"{C.GREEN}Active{C.RESET}"
            print(f"  Status:            {status}")
            print(f"  Participants:      {stats[0]:,}")
            print(f"  Qualified:         {stats[1]:,}")
            print(f"  Total points:      {stats[2]:,}")

        cap = airdrop.call_getter("get_manual_attribution_cap") or 50000
        print(f"  Manual cap:        {cap:,} pts/call")
        log_count = airdrop.call_getter("get_admin_log_count") or 0
        print(f"  Admin actions:     {log_count:,}")
        print()

        choice = menu("Admin Menu", [
            ("➕  Add points (single user)     — Manual attribution", "add_single"),
            ("➕➕ Add points (batch)           — Multiple users at once", "add_batch"),
            ("➖  Deduct points                — Remove from user", "deduct"),
            ("🔨  Disqualify user              — Ban a cheater", "disqualify"),
            ("✅  Force-qualify user           — Override thresholds", "force_qualify"),
            ("🎁  Set bonus multiplier         — Custom bonus for user", "multiplier"),
            ("📊  View admin log               — Audit trail", "log"),
            ("⚙️  Set manual cap               — Change max per call", "set_cap"),
            ("Back", None),
        ])

        if choice is None:
            break
        elif choice == "add_single":
            _admin_add_single(airdrop, user_addr)
        elif choice == "add_batch":
            _admin_add_batch(airdrop, user_addr)
        elif choice == "deduct":
            _admin_deduct(airdrop, user_addr)
        elif choice == "disqualify":
            _admin_disqualify(airdrop, user_addr)
        elif choice == "force_qualify":
            _admin_force_qualify(airdrop, user_addr)
        elif choice == "multiplier":
            _admin_multiplier(airdrop, user_addr)
        elif choice == "log":
            _admin_view_log(airdrop)
        elif choice == "set_cap":
            _admin_set_cap(airdrop, user_addr)


def _admin_add_single(airdrop: AirdropClient, admin_addr: str):
    """Add points to a single user."""
    clear()
    print(BANNER)
    print(f"\n{C.CYAN}{C.BOLD}  ➕ ADD POINTS (SINGLE USER){C.RESET}")
    print(f"{C.GRAY}  {'─' * 56}{C.RESET}\n")

    user_addr = text_input("  User testnet address: ")
    if not user_addr or len(user_addr) < 10:
        print(f"\n  {C.RED}Invalid address.{C.RESET}")
        print(f"\n{C.GRAY}  Press Enter...{C.RESET}", end="")
        input()
        return

    # Check if disqualified
    is_disq = airdrop.call_getter("is_disqualified", [user_addr])
    if is_disq:
        print(f"\n  {C.RED}⚠ This user is disqualified. Revoke disqualification first.{C.RESET}")
        print(f"\n{C.GRAY}  Press Enter...{C.RESET}", end="")
        input()
        return

    # Select category
    cat_choice = menu("Select category", [
        ("⛏  Mining", "1"),
        ("📡 Relayer", "2"),
        ("🗳  Governance", "3"),
        ("💬 Chat", "4"),
        ("💧 Liquidity", "5"),
        ("🐛 Bounty", "6"),
        ("👥 Community", "7"),
        ("Cancel", None),
    ])
    if cat_choice is None:
        return
    category = int(cat_choice)

    # Enter points
    points_str = text_input("  Points to add: ")
    try:
        points = int(points_str)
        if points <= 0:
            raise ValueError()
    except ValueError:
        print(f"\n  {C.RED}Invalid points amount.{C.RESET}")
        print(f"\n{C.GRAY}  Press Enter...{C.RESET}", end="")
        input()
        return

    # Enter reason
    reason = text_input("  Reason (e.g. 'Discord help'): ")
    if not reason:
        reason = "Manual attribution"

    # Confirm
    clear()
    print(BANNER)
    print(f"\n{C.YELLOW}{C.BOLD}  ⚠ CONFIRM ATTRIBUTION{C.RESET}")
    print(f"{C.GRAY}  {'─' * 56}{C.RESET}\n")
    print(f"  User:     {C.DIM}{user_addr}{C.RESET}")
    print(f"  Category: {CATEGORY_NAMES.get(category, 'Unknown')}")
    print(f"  Points:   {C.BOLD}{points:,}{C.RESET}")
    print(f"  Reason:   {reason}")

    if confirm("  Confirm?"):
        print(f"\n  {C.DIM}Submitting transaction...{C.RESET}")
        tx = airdrop.submit_tx(ENTRY_RECORD_MANUAL_ATTRIBUTION, [user_addr, category, points, reason])
        if tx:
            print(f"\n  {C.GREEN}✓ Points added!{C.RESET}")
            print(f"  {C.DIM}TX: {tx[:30]}...{C.RESET}")
        else:
            print(f"\n  {C.RED}✗ Failed to submit.{C.RESET}")
    else:
        print(f"\n  {C.DIM}Cancelled.{C.RESET}")

    print(f"\n{C.GRAY}  Press Enter...{C.RESET}", end="")
    input()


def _admin_add_batch(airdrop: AirdropClient, admin_addr: str):
    """Add points to multiple users at once (max 50)."""
    clear()
    print(BANNER)
    print(f"\n{C.CYAN}{C.BOLD}  ➕➕ ADD POINTS (BATCH — up to 50 users){C.RESET}")
    print(f"{C.GRAY}  {'─' * 56}{C.RESET}\n")
    print(f"  {C.DIM}Enter one address per line. Empty line to finish.{C.RESET}\n")

    users = []
    while len(users) < 50:
        addr = text_input(f"  Address {len(users)+1} (or empty to finish): ")
        if not addr:
            break
        if len(addr) >= 10:
            users.append(addr)
        else:
            print(f"  {C.RED}Invalid address, skipped.{C.RESET}")

    if not users:
        print(f"\n  {C.DIM}No addresses entered.{C.RESET}")
        print(f"\n{C.GRAY}  Press Enter...{C.RESET}", end="")
        input()
        return

    # Select category
    cat_choice = menu(f"Select category for {len(users)} users", [
        ("⛏  Mining", "1"),
        ("📡 Relayer", "2"),
        ("🗳  Governance", "3"),
        ("💬 Chat", "4"),
        ("💧 Liquidity", "5"),
        ("🐛 Bounty", "6"),
        ("👥 Community", "7"),
        ("Cancel", None),
    ])
    if cat_choice is None:
        return
    category = int(cat_choice)

    # Enter points (same for all)
    points_str = text_input(f"  Points per user ({len(users)} users): ")
    try:
        points = int(points_str)
        if points <= 0:
            raise ValueError()
    except ValueError:
        print(f"\n  {C.RED}Invalid points.{C.RESET}")
        print(f"\n{C.GRAY}  Press Enter...{C.RESET}", end="")
        input()
        return

    total = points * len(users)
    reason = text_input("  Reason (e.g. 'Discord moderator rewards'): ")
    if not reason:
        reason = "Batch attribution"

    # Confirm
    clear()
    print(BANNER)
    print(f"\n{C.YELLOW}{C.BOLD}  ⚠ CONFIRM BATCH ATTRIBUTION{C.RESET}")
    print(f"{C.GRAY}  {'─' * 56}{C.RESET}\n")
    print(f"  Users:    {C.BOLD}{len(users)}{C.RESET}")
    print(f"  Category: {CATEGORY_NAMES.get(category, 'Unknown')}")
    print(f"  Per user: {C.BOLD}{points:,}{C.RESET}")
    print(f"  Total:    {C.YELLOW}{total:,}{C.RESET}")
    print(f"  Reason:   {reason}")
    print(f"\n  {C.DIM}Addresses:{C.RESET}")
    for u in users[:5]:
        print(f"    {C.DIM}{u[:30]}...{C.RESET}")
    if len(users) > 5:
        print(f"    {C.DIM}... and {len(users)-5} more{C.RESET}")

    if confirm("  Confirm batch?"):
        print(f"\n  {C.DIM}Submitting transaction...{C.RESET}")
        tx = airdrop.submit_tx(ENTRY_RECORD_MANUAL_ATTRIBUTION_BATCH, [users, category, points, reason])
        if tx:
            print(f"\n  {C.GREEN}✓ Batch attribution submitted!{C.RESET}")
            print(f"  {C.DIM}TX: {tx[:30]}...{C.RESET}")
        else:
            print(f"\n  {C.RED}✗ Failed to submit.{C.RESET}")
    else:
        print(f"\n  {C.DIM}Cancelled.{C.RESET}")

    print(f"\n{C.GRAY}  Press Enter...{C.RESET}", end="")
    input()


def _admin_deduct(airdrop: AirdropClient, admin_addr: str):
    """Deduct points from a user."""
    clear()
    print(BANNER)
    print(f"\n{C.CYAN}{C.BOLD}  ➖ DEDUCT POINTS{C.RESET}")
    print(f"{C.GRAY}  {'─' * 56}{C.RESET}\n")

    user_addr = text_input("  User testnet address: ")
    if not user_addr or len(user_addr) < 10:
        print(f"\n  {C.RED}Invalid address.{C.RESET}")
        print(f"\n{C.GRAY}  Press Enter...{C.RESET}", end="")
        input()
        return

    cat_choice = menu("Select category", [
        ("⛏  Mining", "1"),
        ("📡 Relayer", "2"),
        ("🗳  Governance", "3"),
        ("💬 Chat", "4"),
        ("💧 Liquidity", "5"),
        ("🐛 Bounty", "6"),
        ("👥 Community", "7"),
        ("Cancel", None),
    ])
    if cat_choice is None:
        return
    category = int(cat_choice)

    points_str = text_input("  Points to deduct: ")
    try:
        points = int(points_str)
        if points <= 0:
            raise ValueError()
    except ValueError:
        print(f"\n  {C.RED}Invalid points.{C.RESET}")
        print(f"\n{C.GRAY}  Press Enter...{C.RESET}", end="")
        input()
        return

    reason = text_input("  Reason (e.g. 'Mistake correction'): ")
    if not reason:
        reason = "Manual deduction"

    clear()
    print(BANNER)
    print(f"\n{C.RED}{C.BOLD}  ⚠ CONFIRM DEDUCTION{C.RESET}")
    print(f"{C.GRAY}  {'─' * 56}{C.RESET}\n")
    print(f"  User:     {C.DIM}{user_addr}{C.RESET}")
    print(f"  Category: {CATEGORY_NAMES.get(category, 'Unknown')}")
    print(f"  Points:   {C.RED}-{points:,}{C.RESET}")
    print(f"  Reason:   {reason}")

    if confirm("  Confirm deduction?"):
        print(f"\n  {C.DIM}Submitting...{C.RESET}")
        tx = airdrop.submit_tx(ENTRY_DEDUCT_POINTS, [user_addr, category, points, reason])
        if tx:
            print(f"\n  {C.GREEN}✓ Points deducted!{C.RESET}")
        else:
            print(f"\n  {C.RED}✗ Failed.{C.RESET}")

    print(f"\n{C.GRAY}  Press Enter...{C.RESET}", end="")
    input()


def _admin_disqualify(airdrop: AirdropClient, admin_addr: str):
    """Disqualify a user."""
    clear()
    print(BANNER)
    print(f"\n{C.RED}{C.BOLD}  🔨 DISQUALIFY USER{C.RESET}")
    print(f"{C.GRAY}  {'─' * 56}{C.RESET}\n")
    print(f"  {C.YELLOW}Banned users get 0 VLT even if they have points.{C.RESET}")
    print(f"  {C.DIM}Use for: cheaters, Sybil attackers, bot farmers.{C.RESET}\n")

    user_addr = text_input("  User testnet address: ")
    if not user_addr or len(user_addr) < 10:
        print(f"\n  {C.RED}Invalid address.{C.RESET}")
        print(f"\n{C.GRAY}  Press Enter...{C.RESET}", end="")
        input()
        return

    reason = text_input("  Reason (e.g. 'Sybil attack detected'): ")
    if not reason:
        reason = "Rule violation"

    clear()
    print(BANNER)
    print(f"\n{C.RED}{C.BOLD}  ⚠ CONFIRM DISQUALIFICATION{C.RESET}")
    print(f"{C.GRAY}  {'─' * 56}{C.RESET}\n")
    print(f"  User:   {C.DIM}{user_addr}{C.RESET}")
    print(f"  Reason: {reason}")
    print(f"\n  {C.RED}This user will receive 0 VLT even if they have points.{C.RESET}")

    if confirm("  Confirm disqualification?"):
        print(f"\n  {C.DIM}Submitting...{C.RESET}")
        tx = airdrop.submit_tx(ENTRY_DISQUALIFY_USER, [user_addr, reason])
        if tx:
            print(f"\n  {C.GREEN}✓ User disqualified!{C.RESET}")
        else:
            print(f"\n  {C.RED}✗ Failed.{C.RESET}")

    print(f"\n{C.GRAY}  Press Enter...{C.RESET}", end="")
    input()


def _admin_force_qualify(airdrop: AirdropClient, admin_addr: str):
    """Force-qualify a user."""
    clear()
    print(BANNER)
    print(f"\n{C.GREEN}{C.BOLD}  ✅ FORCE-QUALIFY USER{C.RESET}")
    print(f"{C.GRAY}  {'─' * 56}{C.RESET}\n")
    print(f"  {C.DIM}Manually qualify a user who doesn't meet standard thresholds.{C.RESET}")
    print(f"  {C.DIM}Use for: Discord mods, doc writers, valuable contributors.{C.RESET}\n")

    user_addr = text_input("  User testnet address: ")
    if not user_addr or len(user_addr) < 10:
        print(f"\n  {C.RED}Invalid address.{C.RESET}")
        print(f"\n{C.GRAY}  Press Enter...{C.RESET}", end="")
        input()
        return

    reason = text_input("  Reason (e.g. 'Discord moderator, valuable contributor'): ")
    if not reason:
        reason = "Valuable contributor"

    clear()
    print(BANNER)
    print(f"\n{C.YELLOW}{C.BOLD}  ⚠ CONFIRM FORCE-QUALIFICATION{C.RESET}")
    print(f"{C.GRAY}  {'─' * 56}{C.RESET}\n")
    print(f"  User:   {C.DIM}{user_addr}{C.RESET}")
    print(f"  Reason: {reason}")
    print(f"\n  {C.GREEN}This user will qualify even without 7 days or 1000 points.{C.RESET}")

    if confirm("  Confirm force-qualification?"):
        print(f"\n  {C.DIM}Submitting...{C.RESET}")
        tx = airdrop.submit_tx(ENTRY_FORCE_QUALIFY_USER, [user_addr, reason])
        if tx:
            print(f"\n  {C.GREEN}✓ User force-qualified!{C.RESET}")
        else:
            print(f"\n  {C.RED}✗ Failed.{C.RESET}")

    print(f"\n{C.GRAY}  Press Enter...{C.RESET}", end="")
    input()


def _admin_multiplier(airdrop: AirdropClient, admin_addr: str):
    """Set custom bonus multiplier for a user."""
    clear()
    print(BANNER)
    print(f"\n{C.CYAN}{C.BOLD}  🎁 SET BONUS MULTIPLIER{C.RESET}")
    print(f"{C.GRAY}  {'─' * 56}{C.RESET}\n")
    print(f"  {C.DIM}Give a user a custom bonus multiplier.{C.RESET}")
    print(f"  {C.DIM}10000 = 1x (no bonus), 15000 = +50%, 20000 = +100%{C.RESET}")
    print(f"  {C.DIM}0 = remove custom multiplier{C.RESET}\n")

    user_addr = text_input("  User testnet address: ")
    if not user_addr or len(user_addr) < 10:
        print(f"\n  {C.RED}Invalid address.{C.RESET}")
        print(f"\n{C.GRAY}  Press Enter...{C.RESET}", end="")
        input()
        return

    mult_choice = menu("Select multiplier", [
        ("15000  (+50%)  — Discord moderator", "15000"),
        ("20000  (+100%) — Community leader", "20000"),
        ("13000  (+30%)  — Active helper", "13000"),
        ("12500  (+25%)  — Minor contributor", "12500"),
        ("0      Remove custom multiplier", "0"),
        ("Custom value", "custom"),
        ("Cancel", None),
    ])
    if mult_choice is None:
        return
    elif mult_choice == "custom":
        mult_str = text_input("  Multiplier (in bps, e.g. 15000 for +50%): ")
        try:
            multiplier = int(mult_str)
            if multiplier < 0 or multiplier > 30000:
                raise ValueError()
        except ValueError:
            print(f"\n  {C.RED}Invalid multiplier (0-30000).{C.RESET}")
            print(f"\n{C.GRAY}  Press Enter...{C.RESET}", end="")
            input()
            return
    else:
        multiplier = int(mult_choice)

    reason = text_input("  Reason (e.g. 'Discord mod reward'): ")
    if not reason:
        reason = "Custom multiplier"

    clear()
    print(BANNER)
    print(f"\n{C.YELLOW}{C.BOLD}  ⚠ CONFIRM MULTIPLIER{C.RESET}")
    print(f"{C.GRAY}  {'─' * 56}{C.RESET}\n")
    print(f"  User:       {C.DIM}{user_addr}{C.RESET}")
    print(f"  Multiplier: {C.BOLD}{multiplier} bps{C.RESET}", end="")
    if multiplier == 0:
        print(f" {C.DIM}(removed){C.RESET}")
    elif multiplier >= 10000:
        print(f" {C.GREEN}(+{(multiplier-10000)/100:.0f}%){C.RESET}")
    else:
        print(f" {C.RED}({(multiplier-10000)/100:.0f}%){C.RESET}")
    print(f"  Reason:     {reason}")

    if confirm("  Confirm?"):
        print(f"\n  {C.DIM}Submitting...{C.RESET}")
        tx = airdrop.submit_tx(ENTRY_SET_USER_BONUS_MULTIPLIER, [user_addr, multiplier, reason])
        if tx:
            print(f"\n  {C.GREEN}✓ Multiplier set!{C.RESET}")
        else:
            print(f"\n  {C.RED}✗ Failed.{C.RESET}")

    print(f"\n{C.GRAY}  Press Enter...{C.RESET}", end="")
    input()


def _admin_view_log(airdrop: AirdropClient):
    """View admin action log (audit trail)."""
    clear()
    print(BANNER)
    print(f"\n{C.CYAN}{C.BOLD}  📊 ADMIN LOG — Audit Trail{C.RESET}")
    print(f"{C.GRAY}  {'─' * 56}{C.RESET}\n")

    count = airdrop.call_getter("get_admin_log_count") or 0
    if not count:
        print(f"  {C.DIM}No admin actions logged yet.{C.RESET}")
        print(f"\n{C.GRAY}  Press Enter...{C.RESET}", end="")
        input()
        return

    # Show last 20 actions (most recent first)
    show_count = min(20, count)
    print(f"  Showing last {show_count} of {count} total actions:\n")
    print(f"  {'#':<6} {'Action':<18} {'Target':<20} {'Amount':>10} {'Reason':<20}")
    print(f"  {C.GRAY}{'─' * 76}{C.RESET}")

    for i in range(show_count):
        # Ring buffer: most recent is at (count-1) % MAX
        idx = (count - 1 - i) % 1000
        entry = airdrop.call_getter("get_admin_log_entry", [idx])
        if not entry or len(entry) < 8:
            continue

        admin, action_type, target, category, amount, mult, reason, topo = entry

        action_name = ACTION_NAMES.get(action_type, f"Type {action_type}")
        target_str = fmt_addr(target) if target else "(batch)"
        amount_str = ""
        if amount > 0:
            amount_str = f"{amount:,}"
        elif mult > 0:
            amount_str = f"{mult} bps"

        reason_short = reason[:20] + "..." if len(reason) > 20 else reason

        print(f"  {C.DIM}{i+1:<6}{C.RESET} {action_name:<18} {target_str:<20} {C.BOLD}{amount_str:>10}{C.RESET} {C.DIM}{reason_short:<20}{C.RESET}")

    print(f"\n{C.GRAY}  Press Enter...{C.RESET}", end="")
    input()


def _admin_set_cap(airdrop: AirdropClient, admin_addr: str):
    """Set manual attribution cap."""
    clear()
    print(BANNER)
    print(f"\n{C.CYAN}{C.BOLD}  ⚙️  SET MANUAL ATTRIBUTION CAP{C.RESET}")
    print(f"{C.GRAY}  {'─' * 56}{C.RESET}\n")

    current = airdrop.call_getter("get_manual_attribution_cap") or 50000
    print(f"  Current cap: {C.BOLD}{current:,}{C.RESET} points per call")
    print(f"  {C.DIM}Range: 100 - 500,000{C.RESET}\n")

    cap_str = text_input("  New cap: ")
    try:
        new_cap = int(cap_str)
        if new_cap < 100 or new_cap > 500000:
            raise ValueError()
    except ValueError:
        print(f"\n  {C.RED}Invalid cap (100-500000).{C.RESET}")
        print(f"\n{C.GRAY}  Press Enter...{C.RESET}", end="")
        input()
        return

    if confirm(f"  Set cap to {new_cap:,}?"):
        print(f"\n  {C.DIM}Submitting...{C.RESET}")
        tx = airdrop.submit_tx(ENTRY_SET_MANUAL_ATTRIBUTION_CAP, [new_cap])
        if tx:
            print(f"\n  {C.GREEN}✓ Cap updated!{C.RESET}")
        else:
            print(f"\n  {C.RED}✗ Failed.{C.RESET}")

    print(f"\n{C.GRAY}  Press Enter...{C.RESET}", end="")
    input()
