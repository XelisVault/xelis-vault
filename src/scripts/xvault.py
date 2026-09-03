#!/usr/bin/env python3
"""
============================================================================
 XELIS Vault — Community CLI (xvault)
============================================================================
Interactive CLI with arrow-key navigation. No typing numbers.
Works on Linux, macOS, and Windows.

Live on-chain data & verified contract flows via cli_backend.
Features not yet enabled are clearly marked "coming soon".
============================================================================
"""
from __future__ import annotations

import json
import os
import platform
import re
import secrets
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from config import Config, CONFIG_PATH
from tui import (
    C, clear, hide_cursor, show_cursor, read_key, read_key_timeout, kbhit,
    menu, text_input, confirm, info_box, progress_bar, BANNER, _RICH,
    has_rich, render_panel, render_metrics, render_bar, render_badge,
    render_ok, render_warn, render_error, render_status, render_hint,
)
from cli_backend import (
    Backend, DECIMALS, OpResult, AIRDROP_CATEGORIES, ZERO_HASH,
)
from protocol import SERVICE_ORACLE, SERVICE_CHAT, MIN_STAKE_VLT
import onboarding

VAULT_DIR = Path.home() / ".xelis-vault"

MIN_LEND_DURATION_BLOCKS = 1440
MAX_INTEREST_BPS = 5000
MIN_AUCTION_DURATION_BLOCKS = 1440
RELAYER_MAX_FREE_MESSAGES_PER_DAY = 1000
RELAYER_MAX_FREE_WALLET_SLOTS = 10000
RELAYER_DEFAULT_FEE_ATOMIC = 1_000_000  # 0.01 XEL/VLT per message
MINER_HEARTBEAT_WARN_BLOCKS = 1000
MIN_RELAYER_BOND_VLT = 50

_WALLET_ALIVE_CACHE = {}
_WALLET_ALIVE_TTL = 15.0  # seconds before re-checking wallet status
_WALLET_RELAUNCHING: set = set()   # urls currently being relaunched in the background


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def short_addr(a: str, n: int = 10) -> str:
    if not a:
        return "-"
    return f"{a[:n]}...{a[-6:]}"


def parse_amount(text: str) -> int | None:
    """Human amount → atomic (1e8). Returns None on invalid input."""
    text = text.strip().replace(",", "").replace("_", "")
    try:
        v = float(text)
    except ValueError:
        return None
    if v <= 0:
        return None
    return int(round(v * 10 ** DECIMALS))


def show_result(res, action: str):
    if res.ok:
        info_box("Transaction sent", [
            f"{C.GREEN}{action} successful{C.RESET}",
            "",
            f"Tx hash:",
            f"{C.DIM}{res.tx[:62]}{C.RESET}",
            *(            f"{C.DIM}{res.tx[i:i+62]}{C.RESET}" for i in range(62, len(res.tx), 62)),
             *(["",
                f"{C.GREEN}✔ Confirmed on-chain"
                + (f" — block {str(getattr(res, 'topo'))[:12]}…" if getattr(res, 'topo') else "")
                + f" in {getattr(res, 'secs', 0):.0f} s{C.RESET}"]
               if getattr(res, "confirmed", None) else
               ["", f"{C.YELLOW}⏳ Not yet visible in a block after "
                    f"{getattr(res, 'secs', 0):.0f} s — check via 'History'.{C.RESET}"]),
        ], color=C.GREEN)
    else:
        friendly = _friendly_error(res.reason or "")
        if friendly:
            info_box("Insufficient balance", [
                f"{C.RED}{action}: {friendly}{C.RESET}",
                "",
                f"{C.GRAY}Tip: mint xUSD first (Swap > Mint) or lower the amount."
                f"{C.RESET}",
            ], color=C.RED)
        else:
            info_box("Transaction failed", [
                f"{C.RED}{action} was rejected by the chain{C.RESET}",
                "",
                f"Reason: {res.reason}",
            ], color=C.RED)


def ask_amount(b: Backend, asset: str, prompt_text: str, default: str = "1"):
    """text_input with the live balance always visible in the prompt."""
    try:
        bal = b.balance(asset)
        if bal is not None:
            bal_s = b.fmt(bal)
        else:
            bal_s = "?"
    except Exception:
        bal_s = "?"
    addr = getattr(b, "address", "(unknown)")
    asset_name = {ZERO_HASH: "XEL", b.vlt_asset: "VLT", b.xusd_asset: "xUSD"}.get(asset, asset[:16])
    return text_input(f"{prompt_text}  [wallet: {short_addr(addr)} | {asset_name}: {bal_s}]", default=default)


def wait_confirm(b: Backend, tx: str, max_s: int = 90):
    """Poll the daemon until the tx lands in a block. Returns (ok, topo)."""
    t0 = time.time()
    while time.time() - t0 < max_s:
        r = b.daemon.get_transaction(tx)
        if isinstance(r, dict):
            topo = (r.get("executed_in_block") or r.get("block_topoheight")
                    or r.get("topoheight"))
            if topo or r.get("blocks"):
                return True, topo
        time.sleep(3)
    return False, None


def run_tx(b: Backend, fn, action: str):
    """Pending indicator + confirmation feedback around a write op.
    Builds + broadcasts, waits for the block, then VERIFIES on-chain that the
    transaction actually committed (a revert means the storage was rolled back)."""
    print(f"\n{C.DIM}⏳ Transaction in progress — sign → broadcast → wait for block (~5-15 s)…{C.RESET}", flush=True)
    t0 = time.time()
    try:
        res = fn()
    except Exception as e:
        sys.stdout.write("\r\x1b[K"); sys.stdout.flush()
        show_result(OpResult(False, reason=str(e)[:200]), action)
        return None
    if not res.ok:
        sys.stdout.write("\r\x1b[K"); sys.stdout.flush()
        show_result(res, action)
        return None
    ok, topo = wait_confirm(b, res.tx)
    secs = time.time() - t0
    # On-chain verification — a built+broadcast tx can still REVERT on the chain
    revert = ""
    if ok:
        revert = b.verify_onchain(res.tx) if hasattr(b, "verify_onchain") else ""
    sys.stdout.write("\r\x1b[K"); sys.stdout.flush()
    if revert:
        info_box("Transaction reverted by the chain", [
            f"{C.RED}{action} was REJECTED on-chain — nothing was applied.{C.RESET}",
            "",
            f"Reason: {C.BOLD}{revert}{C.RESET}",
            "",
            f"{C.GRAY}Tx hash:{C.RESET} {res.tx[:40]}…",
        ], color=C.RED)
        res.ok = False
        res.reason = revert
        return res
    res.confirmed = ok
    res.topo = topo
    res.secs = secs
    _record_tx(b, res, action)
    show_result(res, action)
    return res


def _record_tx(b: Backend, res, action: str):
    """Persist a confirmed, non-reverted tx to the local activity ledger."""
    try:
        import tx_ledger
        tx_ledger.record(
            b.address, res.tx,
            screen="(CLI)",
            action=action[:120],
            description=action[:200],
            topo=res.topo if getattr(res, "topo", None) else None,
            contract=getattr(res, "contract", "") or "",
            entry=getattr(res, "entry", "") or "",
        )
    except Exception:
        pass


def _friendly_error(msg: str):
    """Translate raw wallet/protocol errors into human text."""
    low = msg.lower()
    if "not enough funds" in low or "insufficient balance" in low:
        m = re.search(r"required:\s*(\d+)[,\s]+available:\s*(\d+)", low)
        if m:
            req, av = int(m.group(1)), int(m.group(2))
            return (f"available {av / 10**DECIMALS:.6g}, "
                    f"required {req / 10**DECIMALS:.6g}")
        return "not enough funds for amount + fee"
    if "stale" in low:
        return "oracle price is stale — wait for refresh or check node sync"
    if "revert" in low or "rejected" in low:
        return "transaction reverted on-chain"
    if "not found" in low and "contract" in low:
        return "contract not found on this node — try a different RPC"
    return None


def _check_balance(b: Backend, asset: str, atomic: int) -> bool:
    """True if the wallet can spend `atomic` of `asset`; offers max otherwise."""
    asset_name = {ZERO_HASH: "XEL", b.vlt_asset: "VLT", b.xusd_asset: "xUSD"}.get(asset, asset[:16])
    addr = getattr(b, "address", "(unknown)")
    e = None
    try:
        avail = b.balance(asset)
    except Exception as e:
        avail = None
    if avail is None:
        info_box("Balance check failed", [
            f"{C.RED}Could not read wallet balance.{C.RESET}",
            "",
            f"Wallet: {addr}",
            f"Asset: {asset_name} ({asset[:16]}...)",
            f"Error: {str(e)[:80]}" if e else "",
            "",
            f"{C.GRAY}Check that the wallet is running and the RPC is reachable.{C.RESET}",
        ], color=C.RED)
        return False
    if atomic <= avail:
        return True
    info_box("Insufficient balance", [
        f"{C.RED}Not enough funds in this wallet.{C.RESET}",
        "",
        f"Wallet: {addr}",
        f"Asset: {asset_name}",
        f"Available: {C.BOLD}{b.fmt(avail)}{C.RESET}",
        f"Requested: {b.fmt(atomic)}",
        "",
        f"{C.GRAY}Lower the amount or top up your wallet.{C.RESET}",
    ], color=C.RED)
    return False


def coming_soon(name: str, desc: str):
    info_box(f"{name} — Coming soon", [
        f"{C.BOLD}{name}{C.RESET} is not enabled yet.",
        "",
        *desc,
        "",
        f"{C.GRAY}Follow the project for release updates.{C.RESET}",
    ], color=C.YELLOW)


# ---------------------------------------------------------------------------
# Screens
# ---------------------------------------------------------------------------

def screen_dashboard(b: Backend):
    """Live professional dashboard — auto-refreshes in real time until a key
    is pressed.

    A background thread continuously fetches on-chain data via
    `Backend.dashboard_snapshot()` (itself parallelized + short-TTL cached)
    and stores the latest snapshot in a lock-protected shared state. The
    render loop below never makes a network call itself, so it can never
    freeze waiting on a remote RPC round-trip — key presses are picked up
    within ~50ms regardless of network conditions.
    """
    hide_cursor()
    state = {"snap": None, "err": None, "refresh_count": 0}
    lock = threading.Lock()
    stop = threading.Event()
    start_time = time.time()

    def _worker():
        count = 0
        while not stop.is_set():
            try:
                snap = b.dashboard_snapshot()
                count += 1
                with lock:
                    state["snap"], state["err"], state["refresh_count"] = snap, None, count
            except Exception as e:
                with lock:
                    state["err"] = str(e)[:200]
            stop.wait(1.0)

    t = threading.Thread(target=_worker, daemon=True, name="dashboard-refresh")
    t.start()

    def _pressed():
        # True non-blocking check (works on Windows via msvcrt and on Unix).
        if kbhit():
            read_key()  # drain the input so it doesn't leak into the next menu
            return True
        return False

    try:
        while True:
            with lock:
                snap, err = state["snap"], state["err"]
                refresh_n = state["refresh_count"]

            if snap is None:
                # First frame not ready yet — show a lightweight loading state
                # instead of a blank/frozen screen while the background
                # thread completes its first fetch.
                if _pressed():
                    return
                clear()
                print(render_badge(' XELIS Vault ', 'cyan', filled=True))
                print()
                print(f"{C.RED}{err}{C.RESET}" if err else
                      f"{C.DIM}Connecting to the network…{C.RESET}")
                if read_key_timeout(0.2) is not None or _pressed():
                    return
                continue

            if _pressed():
                return
            clear()
            topo = snap["topo"]
            price_info = snap["price"]
            bal = snap["balances"]
            ms = snap["miner_stats"]
            psm = snap["psm"]
            xel, vlt, xusd = bal.get("XEL"), bal.get("VLT"), bal.get("xUSD")
            now_str = datetime.now().strftime("%H:%M:%S")
            uptime_s = int(time.time() - start_time)
            uptime_str = f"{uptime_s // 3600}h{(uptime_s % 3600) // 60:02d}m"

            # ── Header / connection strip ───────────────────────────────
            net_ok = bool(topo) and err is None
            conn_badge = render_badge(' ONLINE ', 'green', filled=True) if net_ok \
                else render_badge(' OFFLINE ', 'red', filled=True)
            hdr_lines = [
                f"  {render_badge(' XELIS VAULT ', 'cyan', filled=True)}"
                f"  {render_badge(' TESTNET ', 'magenta', filled=True)}"
                f"  {conn_badge}"
                f"  {C.DIM}{now_str}{C.RESET}"
                f"  {C.DIM}uptime {uptime_str}{C.RESET}"
                f"  {C.DIM}refresh #{refresh_n}{C.RESET}",
                "",
                f"  {C.DIM}Topoheight{C.RESET}  {C.BOLD}{topo:,}{C.RESET}"
                f"    {C.DIM}Address{C.RESET}  {C.CYAN}{short_addr(b.address)}{C.RESET}",
            ]
            print("\n".join(hdr_lines))

            # ── Wallet balances panel ───────────────────────────────────
            wal_rows = []
            for sym, val, icon in [("XEL", xel, "◆"), ("VLT", vlt, "◈"), ("xUSD", xusd, "$")]:
                formatted = b.fmt(val)
                color = C.GREEN if (val is not None and val > 0) else C.DIM
                wal_rows.append((f"  {icon} {sym}", f"{color}{C.BOLD}{formatted}{C.RESET}  {C.DIM}{sym}{C.RESET}"))

            # Total USD value estimate
            if price_info and xel is not None:
                raw_price = price_info[0] / 10**DECIMALS
                usd_val = (xel / 10**DECIMALS) * raw_price
                wal_rows.append((f"  ≈ USD", f"{C.BOLD}${usd_val:,.2f}{C.RESET}  {C.DIM}(XEL only){C.RESET}"))

            if price_info:
                raw, ftopo, stale = price_info
                age = max(0, topo - ftopo)
                if stale:
                    price_badge = f"{C.RED}● STALE ({age} blk){C.RESET}"
                elif age < 60:
                    price_badge = f"{C.GREEN}● fresh ({age} blk){C.RESET}"
                else:
                    price_badge = f"{C.YELLOW}● aging ({age} blk){C.RESET}"
                wal_rows.append(("  XEL/USD", f"{C.BOLD}${raw / 10**DECIMALS:,.4f}{C.RESET}  {price_badge}"))

            print()
            print(render_metrics(wal_rows, title="  WALLET  &  PRICE  FEED",
                                 border_color=C.CYAN))

            # ── Protocol panel ──────────────────────────────────────────
            pro_rows = []
            if psm and psm.get("xel") is not None:
                psm_xel = psm.get("xel", 0)
                psm_xusd = psm.get("xusd", 0)
                pro_rows.append(("PSM XEL reserve",
                                 f"{C.BOLD}{b.fmt(psm_xel)}{C.RESET}  {C.DIM}XEL{C.RESET}"))
                pro_rows.append(("PSM xUSD reserve",
                                 f"{C.BOLD}{b.fmt(psm_xusd)}{C.RESET}  {C.DIM}xUSD{C.RESET}"))
            if ms.get("total_staked") is not None:
                pro_rows.append(("Miner total staked",
                                 f"{C.BOLD}{b.fmt(ms['total_staked'])}{C.RESET}  {C.DIM}VLT{C.RESET}"))
            if ms.get("budget") is not None and ms.get("distributed") is not None:
                budget, dist = ms["budget"], ms["distributed"]
                pct = dist / budget if budget else 0
                pct_int = int(pct * 100)
                bar = render_bar(pct, 20)
                color = C.GREEN if pct < 0.5 else C.YELLOW if pct < 0.85 else C.RED
                pro_rows.append(("Rewards distributed",
                                 f"{bar}  {color}{pct_int}%{C.RESET}  "
                                 f"{C.DIM}{dist//10**DECIMALS:g}/{budget//10**DECIMALS:g} VLT{C.RESET}"))
            if ms.get("min_stake") is not None:
                pro_rows.append(("Min miner stake",
                                 f"{C.BOLD}{b.fmt(ms['min_stake'])}{C.RESET}  {C.DIM}VLT{C.RESET}"))
            if pro_rows:
                print()
                print(render_metrics(pro_rows, title="  PROTOCOL  HEALTH",
                                     border_color=C.MAGENTA))

            # ── Footer ──────────────────────────────────────────────────
            print()
            print(f"{C.DIM}{'─' * 62}{C.RESET}")
            print(f"  {C.DIM}Live auto-refresh (1s) — press any key to go back{C.RESET}")
            # Data refreshes in the background every ~1s; key presses are
            # picked up within ~50-200ms regardless (never blocked by RPC).
            if read_key_timeout(1.0) is not None or _pressed():
                return
    finally:
        stop.set()
        show_cursor()


def screen_vault(b: Backend):
    while True:
        vaults = b.my_vaults()
        opts = [("View my vaults", "view"),
                ("Open / top-up a vault (deposit XEL collateral)", "deposit")]
        if vaults:
            opts += [("Borrow xUSD", "borrow"),
                     ("Repay debt", "repay"),
                     ("Withdraw collateral", "withdraw")]
        opts.append(("Back", None))
        choice = menu("Vault — collateralized xUSD", opts,
                      subtitle="Deposit XEL, borrow xUSD at 200% minimum ratio")
        if choice is None:
            return
        if choice == "view":
            lines = []
            if not vaults:
                lines.append(f"{C.DIM}No vault yet. Deposit XEL to open one.{C.RESET}")
            for v in vaults:
                hf = b.health_factor(v)
                if hf is None:
                    hf_s = "--"
                elif hf == float("inf"):
                    hf_s = f"{C.GREEN}no debt{C.RESET}"
                elif hf < 1.05:
                    hf_s = f"{C.RED}⚠ {hf:.2f}{C.RESET}"
                elif hf < 1.5:
                    hf_s = f"{C.YELLOW}{hf:.2f}{C.RESET}"
                else:
                    hf_s = f"{C.GREEN}{hf:.2f}{C.RESET}"
                state = f"{C.RED}LIQUIDATED{C.RESET}" if v["liquidated"] else "active"
                lines.append(
                    f"Vault #{v['id']}  {state}")
                lines.append(
                    f"   Collateral: {b.fmt(v['collateral'], 'XEL')}   "
                    f"Debt: {b.fmt(v['borrow_amount'], 'xUSD')}   HF: {hf_s}")
            info_box("My vaults", lines or ["empty"], color=C.CYAN)
        elif choice == "deposit":
            amt = ask_amount(b, b.xel_asset, "XEL amount to deposit as collateral:")
            atomic = parse_amount(amt)
            if atomic is None:
                continue
            if not _check_balance(b, b.xel_asset, atomic):
                continue
            if confirm(f"Deposit {amt} XEL into the Vault?"):
                run_tx(b, lambda: b.vault_deposit(atomic), "Vault deposit")
        elif choice == "borrow":
            vid = text_input("Vault id:", default=str(vaults[0]["id"]))
            try:
                vid_i = int(vid)
            except ValueError:
                continue
            maxb = b.vault_max_borrow(vid_i) if hasattr(b, "vault_max_borrow") else 0
            vinfo = b.vault_get(vid_i) if hasattr(b, "vault_get") else None
            default = "10"
            if maxb and maxb > 0:
                default = f"{maxb / 10**DECIMALS:.6f}".rstrip("0").rstrip(".")
            amt = text_input(f"xUSD amount to borrow (max {b.fmt(maxb, 'xUSD')}):",
                             default=default)
            atomic = parse_amount(amt)
            if atomic is None:
                continue
            if vinfo and vinfo.get("liquidated"):
                info_box("Vault liquidated", ["This vault is liquidated and cannot borrow."],
                         color=C.RED)
                continue
            if maxb and atomic > maxb:
                info_box("Cannot borrow that much", [
                    f"{C.RED}Max borrowable is {b.fmt(maxb, 'xUSD')}{C.RESET}",
                    "",
                    f"Collateral {b.fmt((vinfo or {}).get('collateral'), 'XEL')} at "
                    f"${b.price_usd():,.4f} → 200% min ratio allows "
                    f"{b.fmt(maxb, 'xUSD')} of total debt.",
                ], color=C.RED)
                continue
            if confirm(f"Borrow {amt} xUSD against vault #{vid_i}?"):
                run_tx(b, lambda: b.vault_borrow(vid_i, atomic), "Borrow")
        elif choice == "repay":
            vid = text_input("Vault id:", default=str(vaults[0]["id"]))
            try:
                vid_i = int(vid)
            except ValueError:
                continue
            vinfo = b.vault_get(vid_i) if hasattr(b, "vault_get") else None
            debt = (vinfo or {}).get("borrow_amount") or 0
            default = f"{debt / 10**DECIMALS:.6f}".rstrip("0").rstrip(".") if debt else "10"
            amt = text_input(f"xUSD amount to repay (current debt {b.fmt(debt, 'xUSD')}):",
                             default=default)
            atomic = parse_amount(amt)
            if atomic is None:
                continue
            if debt and atomic > debt:
                info_box("Over-repayment", [
                    f"{C.RED}Your debt is only {b.fmt(debt, 'xUSD')}.{C.RESET}",
                    "Repaying more than the debt is rejected by the chain.",
                ], color=C.RED)
                continue
            if confirm(f"Repay {amt} xUSD on vault #{vid_i}?"):
                run_tx(b, lambda: b.vault_repay(vid_i, atomic), "Repay")
        elif choice == "withdraw":
            vid = text_input("Vault id:", default=str(vaults[0]["id"]))
            try:
                vid_i = int(vid)
            except ValueError:
                continue
            vinfo = b.vault_get(vid_i) if hasattr(b, "vault_get") else None
            coll = (vinfo or {}).get("collateral") or 0
            default = f"{coll / 10**DECIMALS:.6f}".rstrip("0").rstrip(".") if coll else "1"
            amt = text_input(f"XEL amount to withdraw (collateral {b.fmt(coll, 'XEL')}):",
                             default=default)
            atomic = parse_amount(amt)
            if atomic is None:
                continue
            if coll and atomic > coll:
                info_box("Cannot withdraw that much", [
                    f"{C.RED}You only have {b.fmt(coll, 'XEL')} collateral.{C.RESET}",
                    "Also, withdrawing too much breaks the 200% collateral ratio.",
                ], color=C.RED)
                continue
            if confirm(f"Withdraw {amt} XEL from vault #{vid_i}?"):
                run_tx(b, lambda: b.vault_withdraw(vid_i, atomic), "Withdraw")


def screen_swap(b: Backend):
    while True:
        usd = b.price_usd()
        pools = b.amm_pools()
        psm = b.psm_reserves()
        sub = (f"XEL/USD ${usd:,.4f}   PSM reserves: "
               f"{b.fmt(psm.get('xel'))} XEL / {b.fmt(psm.get('xusd'))} xUSD"
               ) if usd else "Oracle price unavailable"
        choice = menu("Swap", [
            ("Mint xUSD from XEL (PSM)", "mint"),
            ("Redeem XEL from xUSD (PSM)", "redeem"),
            ("Swap via AMM pool", "swap"),
            ("View AMM pools", "pools"),
            ("Add liquidity to AMM pool", "liquidity"),
            ("Back", None),
        ], subtitle=sub)
        if choice is None:
            return
        if choice == "mint":
            amt = ask_amount(b, b.xel_asset, "XEL amount to convert to xUSD:")
            atomic = parse_amount(amt)
            if atomic is None:
                continue
            if not _check_balance(b, b.xel_asset, atomic):
                continue
            est = atomic / 10 ** DECIMALS * (usd or 1)
            if confirm(f"Mint {amt} XEL → ≈{est:.4f} xUSD ?"):
                run_tx(b, lambda: b.psm_mint(atomic), "Mint xUSD")
        elif choice == "redeem":
            avail = 0
            try:
                avail = b.balance(b.xusd_asset) or 0
            except Exception:
                pass
            default = "1" if avail >= 10**DECIMALS else f"{avail / 10**DECIMALS:.6f}".rstrip("0").rstrip(".")
            amt = text_input(f"xUSD amount to redeem for XEL (you hold {b.fmt(avail)}):",
                             default=default or "0.5")
            atomic = parse_amount(amt)
            if atomic is None:
                continue
            if not _check_balance(b, b.xusd_asset, atomic):
                continue
            est = atomic / 10 ** DECIMALS / (usd or 1) if usd else 0
            if confirm(f"Redeem {amt} xUSD → ≈{est:.4f} XEL ?"):
                run_tx(b, lambda: b.psm_redeem(atomic), "Redeem xUSD")
        elif choice == "swap":
            pick = menu("Select direction", [
                ("XEL → xUSD", (b.xel_asset, b.xusd_asset)),
                ("xUSD → XEL", (b.xusd_asset, b.xel_asset)),
                ("XEL → VLT", (b.xel_asset, b.vlt_asset)),
                ("VLT → XEL", (b.vlt_asset, b.xel_asset)),
                ("xUSD → VLT", (b.xusd_asset, b.vlt_asset)),
                ("VLT → xUSD", (b.vlt_asset, b.xusd_asset)),
                ("Back", None)])
            if not pick:
                continue
            ain, aout = pick
            sym_in = "XEL" if ain == b.xel_asset else ("xUSD" if ain == b.xusd_asset else "VLT")
            amt = ask_amount(b, ain, f"{sym_in} amount to swap:")
            atomic = parse_amount(amt)
            if atomic is None:
                continue
            if not _check_balance(b, ain, atomic):
                continue
            if confirm(f"Swap {amt} {sym_in} via AMM?"):
                run_tx(b, lambda: b.amm_swap(ain, aout, atomic), "AMM swap")
        elif choice == "pools":
            lines = []
            if not pools:
                lines.append(f"{C.DIM}No AMM pools yet.{C.RESET}")
            for p in pools:
                def sym(h):
                    return "XEL" if h == b.xel_asset else ("VLT" if h == b.vlt_asset else "xUSD")
                lines.append(f"{sym(p['a'])}/{sym(p['b'])}:  "
                             f"{b.fmt(p['reserve_a'], sym(p['a']))}  |  "
                             f"{b.fmt(p['reserve_b'], sym(p['b']))}")
            info_box("AMM pools", lines or ["empty"], color=C.CYAN)
        elif choice == "liquidity":
            coming_soon("Add liquidity", [
                "Liquidity provision UI requires LP token accounting",
                "which is being finalized.",
                "",
                "You can still swap through existing pools today."])


def screen_savings(b: Backend):
    while True:
        st = b.savings_stats()
        td = st.get("total_deposits")
        cx = st.get("contract_xusd")
        sub = (f"Total deposits: {b.fmt(td)} xUSD   |   Contract balance: "
               f"{b.fmt(cx)} xUSD") if td is not None else "Loading..."
        choice = menu("Savings (xUSD interest-bearing deposits)", [
            ("Deposit xUSD", "dep"),
            ("Withdraw xUSD", "wd"),
            ("Claim accrued interest", "claim"),
            ("Back", None),
        ], subtitle=sub)
        if choice is None:
            return
        if choice == "dep":
            amt = ask_amount(b, b.xusd_asset, "xUSD amount to deposit:", "10")
            atomic = parse_amount(amt)
            if atomic is None:
                continue
            if not _check_balance(b, b.xusd_asset, atomic):
                continue
            if confirm(f"Deposit {amt} xUSD into Savings?"):
                run_tx(b, lambda: b.savings_deposit(atomic), "Savings deposit")
        elif choice == "wd":
            amt = ask_amount(b, b.xusd_asset, "xUSD amount to withdraw:", "10")
            atomic = parse_amount(amt)
            if atomic is None:
                continue
            if confirm(f"Withdraw {amt} xUSD from Savings?"):
                run_tx(b, lambda: b.savings_withdraw(atomic), "Savings withdraw")
        elif choice == "claim":
            if confirm("Claim all accrued savings interest?"):
                run_tx(b, lambda: b.savings_claim_interest(), "Interest claim")


def _gen_secret() -> str:
    return secrets.token_bytes(32).hex()


def screen_privacy(b: Backend):
    while True:
        st = b.mixer_stats()
        sub = (f"mixes executed: {st.get('total_mixes', '-')}   "
               f"total pooled: {b.fmt(st.get('total_mixed'))} XEL") if st else "Loading..."
        choice = menu("Privacy Mixer — private pool (no sender link)", [
            ("Deposit + create note", "dep"),
            ("Withdraw from pool", "wd"),
            ("Check my note balance", "bal"),
            ("How it works", "help"),
            ("Back", None),
        ], subtitle=sub)
        if choice is None:
            return
        if choice == "dep":
            asset = "XEL"
            amt = ask_amount(b, b.xel_asset, "XEL amount to deposit privately:", "0.1")
            atomic = parse_amount(amt)
            if atomic is None:
                continue
            if not _check_balance(b, b.xel_asset, atomic):
                continue
            secret = _gen_secret()
            if confirm(f"Deposit {amt} XEL and create a private note?\n"
                       f"Keep {C.YELLOW}this secret{C.RESET} to withdraw later:\n{C.BRIGHT}{secret}{C.RESET}"):
                run_tx(b, lambda a=atomic, s=secret: b.mixer_deposit(b.xel_asset, a, s),
                       "Private note deposit")
                info_box("Note secret (SAVE THIS)", [
                    "To withdraw you must present this secret.",
                    "It can be handed to any address off-chain,",
                    "so other people can withdraw for you.",
                    "",
                    f"{C.YELLOW}{secret}{C.RESET}",
                ], color=C.MAGENTA)
        elif choice == "wd":
            dest = text_input("Withdraw TO address (xet:...):").strip()
            if not dest.startswith("xet:") or len(dest) < 20:
                info_box("Invalid address", ["Please enter a full xet: address."],
                         color=C.RED)
                continue
            amt = ask_amount(b, b.xel_asset, "XEL amount to withdraw:", "0.1")
            atomic = parse_amount(amt)
            if atomic is None:
                continue
            secret = text_input("Your note secret (64 hex):").strip().lower()
            if len(secret) != 64:
                info_box("Invalid secret", ["Need a 64-char hex secret."], color=C.RED)
                continue
            if confirm(f"Withdraw {amt} XEL to {short_addr(dest)}?\n"
                       f"Funds come from the shared pool — no sender link."):
                run_tx(b, lambda d=dest, a=atomic, s=secret:
                       b.mixer_withdraw(d, b.xel_asset, a, s),
                       "Private note withdraw")
        elif choice == "bal":
            secret = text_input("Your note secret (64 hex):").strip().lower()
            if len(secret) != 64:
                info_box("Invalid secret", ["Need a 64-char hex secret."], color=C.RED)
                continue
            nb = b.mixer_note_balance(b.xel_asset, secret)
            info_box("Note balance",
                     [f"{b.fmt(nb) if nb is not None else '—'} XEL available",
                      "0 or 'not found' means the note is spent or unknown."],
                     color=C.CYAN)
        elif choice == "help":
            info_box("How the mixer works (v2)", [
                "1. Deposit XEL with a random secret → the",
                "   contract stores a note = blake3(secret).",
                "2. NO sender or recipient is stored on-chain.",
                "3. Withdraw by presenting the secret, to ANY",
                "   recipient, pulling from the shared pool.",
                "",
                "Anonymity = all depositors of the pool + XELIS",
                "encrypted amounts + off-chain secret handoff.",
                "",
                f"{C.YELLOW}Keep your secret safe — it is the only way",
                f"to recover the note.{C.RESET}",
            ], color=C.MAGENTA)


def screen_treasury(b: Backend):
    while True:
        t = b.treasury_info()
        sub = (f"{t.get('signers', '?')} signers · quorum {t.get('quorum', '?')} · "
               f"{t.get('proposals', '?')} proposals · treasury "
               f"{b.fmt(t.get('xel'))} XEL") if t else "Loading..."
        choice = menu("Treasury Vault (multisig)", [
            ("Fund the treasury (deposit)", "fund"),
            ("Create spending proposal (signer)", "propose"),
            ("Confirm proposal (signer)", "confirm"),
            ("Execute confirmed proposal (signer)", "execute"),
            ("Back", None),
        ], subtitle=sub)
        if choice is None:
            return
        if choice == "fund":
            amt = ask_amount(b, b.xel_asset, "XEL amount to deposit into treasury:")
            atomic = parse_amount(amt)
            if atomic is None:
                continue
            if confirm(f"Deposit {amt} XEL into the Treasury?"):
                run_tx(b, lambda: b.treasury_deposit(b.xel_asset, atomic), "Treasury deposit")
        elif choice == "propose":
            dest = text_input("Destination address (xet:...):").strip()
            if not dest.startswith("xet:"):
                continue
            amt = ask_amount(b, b.xel_asset, "XEL amount to propose spending:")
            atomic = parse_amount(amt)
            if atomic is None:
                continue
            if confirm(f"Propose spending {amt} XEL to {short_addr(dest)}?"):
                run_tx(b, lambda: b.treasury_propose(b.xel_asset, dest, atomic), "Proposal")
        elif choice in ("confirm", "execute"):
            pid = text_input("Proposal id:")
            try:
                pid_i = int(pid.strip())
            except ValueError:
                continue
            verb = "Confirm" if choice == "confirm" else "Execute"
            fn = b.treasury_confirm if choice == "confirm" else b.treasury_execute
            if confirm(f"{verb} proposal #{pid_i}?"):
                run_tx(b, lambda: fn(pid_i), f"Proposal {verb}")


def screen_rwa(b: Backend):
    av = b.C("asset_vault")
    ah = b.daemon.read_key(av, "ah") if av else None
    issuer = b.daemon.read_key(av, "i") if av else None
    while True:
        sub = (f"Issuer: {issuer[:18]}…" if issuer else "No RWA asset registered yet")
        opts = []
        if ah:
            opts.append(("Transfer RWA tokens", "transfer"))
        opts += [("Register new asset & mint (admin)", "create"),
                 ("Back", None)]
        choice = menu("RWA Assets (real-world assets)", opts, subtitle=sub)
        if choice is None:
            return
        if choice == "transfer":
            dest = text_input("Recipient address (xet:...):").strip()
            if not dest.startswith("xet:"):
                continue
            amt = ask_amount(b, ah, "Token amount to transfer:", "1")
            atomic = parse_amount(amt)
            if atomic is None:
                continue
            if confirm(f"Transfer {amt} RWA tokens to {short_addr(dest)}?"):
                run_tx(b, lambda: b.rwa_transfer(dest, atomic), "RWA transfer")
        elif choice == "create":
            name = text_input("Asset name (e.g. 'My Token'):")
            if not name:
                continue
            sym = text_input("Symbol (e.g. 'MTK'):")
            if not sym:
                continue
            dec = text_input("Decimals (default 8):").strip() or "8"
            sup = text_input("Initial supply (human-readable, e.g. 1000):")
            if not sup:
                continue
            try:
                dec_i, sup_i = int(dec), int(float(sup) * 10 ** int(dec))
            except ValueError:
                info_box("Invalid input", ["Bad decimals or supply."], color=C.RED)
                continue
            if confirm(f"Register '{name}' ({sym}) supply={sup} dec={dec_i}?"):
                run_tx(b, lambda: b.rwa_register(name, sym, dec_i, sup_i),
                       "Register RWA asset")


def screen_faucet(b: Backend):
    while True:
        f = b.faucet_info()
        sub = (f"Gives {b.fmt(f.get('xel_per_claim'))} XEL + "
               f"{b.fmt(f.get('vlt_per_claim'))} VLT per distribution · pool "
               f"{b.fmt(f.get('xel_pool'))} XEL") if f else "Loading..."
        choice = menu("Testnet Faucet", [
            ("Distribute to my address", "me"),
            ("View faucet details", "info"),
            ("Back", None),
        ], subtitle=sub)
        if choice is None:
            return
        if choice == "me":
            if not b.address:
                info_box("No address", ["Configure your wallet first."], color=C.RED)
                continue
            # Catch-22: a wallet with no XEL can't pay the network tx fee, so the
            # faucet (which credits XEL) can't be claimed the very first time.
            try:
                xel_bal = b.balance(b.xel_asset) or 0
                fee_need = 10_000_000  # 0.1 XEL INVOKE_FEE
                if xel_bal < fee_need:
                    if not confirm(
                        "Your wallet has almost no XEL, but claiming the faucet "
                        "pays a small network fee from your own balance.\n"
                        "You need a tiny amount of XEL to pay the first fee.\n\n"
                        "Proceed anyway and let the chain report the fee error?"):
                        continue
            except Exception:
                pass
            if confirm(f"Distribute faucet funds to {short_addr(b.address)}?"):
                run_tx(b, lambda: b.faucet_distribute([b.address]), "Faucet distribution")
        elif choice == "info":
            lines = [
                f"XEL per claim:  {b.fmt(f.get('xel_per_claim'), 'XEL')}",
                f"VLT per claim:  {b.fmt(f.get('vlt_per_claim'), 'VLT')}",
                f"Cooldown:       {f.get('cooldown', '-')} blocks",
                f"Pool balances:  {b.fmt(f.get('xel_pool'))} XEL · "
                f"{b.fmt(f.get('vlt_pool'))} VLT",
            ]
            if f.get("my_last_claim_topo"):
                lines.append(f"Your last claim: topo {f['my_last_claim_topo']:,}")
            info_box("Faucet details", lines, color=C.CYAN)


# --- Governance screen ------------------------------------------------------

def screen_governance(b: Backend):
    """Staking (GovernanceVault) + on-chain protocol governance (Governor)."""
    while True:
        total = b.gov_total_staked()
        user  = b.gov_user_staked()
        count = b.gov_stakes_count()
        nprop = b.gov_count()
        sub = (f"Staked: {b.fmt(total, 'VLT') if total else '—'}  ·  "
               f"You: {b.fmt(user, 'VLT') if user else '—'}  ·  "
               f"Positions: {count if count is not None else '—'}  ·  "
               f"Proposals: {nprop if nprop is not None else '—'}")
        opts = [("Stake VLT (voting power)", "stake"),
                ("Unstake a position", "unstake"),
                ("Claim staking rewards", "claim"),
                ("Proposals (Governor) →", "gov_list"),
                ("Propose an action (Governor)", "gov_propose"),
                ("Info", "info"),
                ("Back", None)]
        choice = menu("Governance", opts, subtitle=sub)
        if choice is None:
            return
        if choice == "stake":
            amt = ask_amount(b, b.vlt_asset, "VLT amount to stake:", "100")
            atomic = parse_amount(amt)
            if atomic is None:
                continue
            days = text_input("Lock period in days (default 7):").strip() or "7"
            if not days.isdigit() or int(days) <= 0:
                info_box("Invalid input", [render_error("Lock period must be a positive number.")], color=C.RED)
                continue
            if confirm(f"Stake {amt} VLT for {days} days?"):
                run_tx(b, lambda a=atomic, d=int(days): b.gov_stake(a, d),
                       "Governance stake")
        elif choice == "unstake":
            sid = text_input("Stake ID to unstake (number):").strip()
            if not sid:
                continue
            if confirm(f"Unstake position #{sid}? (reverts if still locked)"):
                run_tx(b, lambda i=int(sid): b.gov_unstake(i),
                       "Governance unstake")
        elif choice == "claim":
            if confirm("Claim governance rewards?"):
                run_tx(b, b.gov_claim_rewards, "Claim governance rewards")
        elif choice == "gov_list":
            _gov_proposals(b)
        elif choice == "gov_propose":
            _gov_propose(b)
        elif choice == "info":
            info_box("Governance", [
                f"Total staked:  {b.fmt(total, 'VLT') if total else '—'}",
                f"Your stake:    {b.fmt(user, 'VLT') if user else '—'}",
                f"Stake count:   {count if count is not None else '—'}",
                f"Proposals:     {nprop if nprop is not None else '—'}",
                "",
                "Vault: min lock 7 days; voting power = stake × (1 + lock boost).",
                "Governor: any holder with ≥ proposal-threshold voting power",
                "can propose; quorum + approval window shown per proposal.",
            ], color=C.CYAN)


def _gov_proposals(b: Backend):
    """Browse on-chain proposals and act (vote / queue)."""
    while True:
        props = b.gov_proposal_list()
        topo = b.topo()
        lines = []
        if not props:
            lines.append(f"{C.DIM}No proposals on-chain yet.{C.RESET}")
        for p in props:
            status = f"{C.GREEN}ACTIVE{C.RESET}" if p.get("end_topo") and topo < p["end_topo"] \
                     else (f"{C.YELLOW}QUEUED{C.RESET}" if p.get("queued") else
                           f"{C.RED}ENDED{C.RESET}")
            if p.get("executed"):
                status = f"{C.DIM}EXECUTED{C.RESET}"
            if p.get("cancelled"):
                status = f"{C.RED}CANCELLED{C.RESET}"
            left = max(0, (p["end_topo"] - topo)) if p.get("end_topo") else 0
            lines.append(
                f"  #{p['id']}  {status}  "
                f"target {p.get('target','')}·{p.get('entry_id','')}"
                f"{'  ' + p['description'] if p.get('description') else ''}"
                f"\n      yes {b.fmt(p.get('yes',0),'VLT')}  ·  "
                f"no {b.fmt(p.get('no',0),'VLT')}  ·  "
                f"abstain {b.fmt(p.get('abstain',0),'VLT')}"
                f"  ({left} bks left)")
        body = lines or [f"{C.DIM}Loading...{C.RESET}"]
        print()
        print(render_panel("  PROTOCOL  PROPOSALS", body,
                           border_color=C.CYAN, width=66))
        print()
        sel = menu("Proposals", [
            ("Vote on a proposal", "vote"),
            ("Queue an ended proposal", "queue"),
            ("Refresh", "refresh"),
            ("Back", None),
        ])
        if sel is None or sel == "refresh":
            if sel is None:
                return
            continue
        if sel == "vote":
            sid = text_input("Proposal ID:").strip()
            if not sid:
                continue
            sup = text_input("Support (1=yes, 0=no, 2=abstain):").strip() or "1"
            try:
                sid, sup = int(sid), int(sup)
            except ValueError:
                info_box("Input", [f"{C.RED}Invalid numbers.{C.RESET}"], color=C.RED)
                continue
            if confirm(f"Vote {'yes' if sup==1 else 'no' if sup==0 else 'abstain'} "
                       f"on proposal #{sid}?"):
                run_tx(b, lambda s=sid, v=sup: b.gov_vote(s, v), "Governor vote")
        elif sel == "queue":
            sid = text_input("Proposal ID to queue:").strip()
            if not sid or not confirm(f"Queue proposal #{sid}?"):
                continue
            run_tx(b, lambda i=int(sid): b.gov_queue(i), "Governor queue")


def _gov_propose(b: Backend):
    """Create a new on-chain proposal targeting a contract entry."""
    target = text_input("Target contract hash (hex):").strip().lower()
    if len(target) != 64:
        info_box("Input", [
            f"{C.RED}Need a 64-char contract hash hex.{C.RESET}",
            "Tip: see the dashboard / registry for contract hashes.",
        ], color=C.RED)
        return
    eid = text_input("Entry (chunk) ID to call:").strip()
    if not eid.isdigit():
        info_box("Input", [f"{C.RED}Entry ID must be a number.{C.RESET}"], color=C.RED)
        return
    params = text_input("Call params hex (bytes, optional):").strip() or ""
    desc = text_input("Short description:").strip()
    if confirm(f"Propose calling entry {eid} on {target[:16]}… {desc!r}?"):
        run_tx(b, lambda t=target, e=int(eid), p=params, d=desc:
               b.gov_propose(t, e, p, d), "Governor propose")


# --- Loans screen (FlashLoan / PeerLoan / Syndicate) -----------------------

def screen_loans(b: Backend):
    while True:
        choice = menu("Loans", [
            ("Flash Loan", "flash"),
            ("Peer Loans", "peer"),
            ("Syndicate Pools", "syn"),
            ("Back", None),
        ])
        if choice is None:
            return
        if choice == "flash":
            screen_flashloan(b)
        elif choice == "peer":
            screen_peerloan(b)
        elif choice == "syn":
            screen_syndicate(b)


def screen_flashloan(b: Backend):
    while True:
        liq = b.flashloan_liquidity(b.xel_asset)
        earned = b.flashloan_earned()
        fee = b.flashloan_fee_bps()
        sub = (f"Liquidity: {b.fmt(liq, 'XEL') if liq else '—'}  ·  "
               f"Earned: {b.fmt(earned, 'XEL') if earned else '—'}  ·  "
               f"Fee: {fee or '—'} bps")
        opts = [("Borrow (flash loan)", "borrow"),
                ("Fund liquidity", "fund"),
                ("Back", None)]
        choice = menu("Flash Loan", opts, subtitle=sub)
        if choice is None:
            return
        if choice == "borrow":
            amt = ask_amount(b, b.xel_asset, "Amount to borrow (XEL):", "1")
            atomic = parse_amount(amt)
            if atomic is None:
                continue
            cb = text_input("Callback contract hash (64 hex):").strip()
            if not cb or len(cb) != 64:
                info_box("Invalid", ["Need a 64-char hex callback hash."], color=C.RED)
                continue
            if confirm(f"Borrow {amt} XEL via FlashLoan?"):
                run_tx(b, lambda a=atomic, c=cb: b.flashloan_borrow(b.xel_asset, a, c),
                       "Flash loan borrow")
        elif choice == "fund":
            amt = ask_amount(b, b.xel_asset, "XEL amount to fund:", "5")
            atomic = parse_amount(amt)
            if atomic is None:
                continue
            if confirm(f"Fund FlashLoan with {amt} XEL?"):
                run_tx(b, lambda a=atomic: b.flashloan_fund(b.xel_asset, a),
                       "Fund FlashLoan")


def screen_peerloan(b: Backend):
    while True:
        count = b.pl_count()
        sub = f"Offers: {count if count is not None else '—'}"
        opts = [("Create offer (lend)", "create"),
                ("Accept offer (borrow)", "accept"),
                ("Repay a loan", "repay"),
                ("Cancel offer", "cancel"),
                ("Back", None)]
        choice = menu("Peer Loans", opts, subtitle=sub)
        if choice is None:
            return
        if choice == "create":
            amt = ask_amount(b, b.xel_asset, "Amount to lend (XEL):", "1")
            atomic = parse_amount(amt)
            if atomic is None:
                continue
            ibps = text_input(f"Interest bps (max {MAX_INTEREST_BPS}, e.g. 500 = 5%):").strip() or "500"
            dur = text_input(f"Duration in blocks (min {MIN_LEND_DURATION_BLOCKS}):").strip() or f"{MIN_LEND_DURATION_BLOCKS}"
            if not ibps.isdigit() or not dur.isdigit():
                info_box("Invalid input", [render_error("Interest bps and duration must be numbers.")], color=C.RED)
                continue
            ibps_i, dur_i = int(ibps), int(dur)
            if not (0 < ibps_i <= MAX_INTEREST_BPS):
                info_box("Invalid input", [render_error(f"Interest bps must be between 1 and {MAX_INTEREST_BPS}.")], color=C.RED)
                continue
            if dur_i < MIN_LEND_DURATION_BLOCKS:
                info_box("Invalid input", [render_error(f"Duration must be at least {MIN_LEND_DURATION_BLOCKS} blocks.")], color=C.RED)
                continue
            coll_amt = ask_amount(b, b.vlt_asset, "Collateral required (VLT):", "100")
            catom = parse_amount(coll_amt)
            if catom is None:
                continue
            if confirm(f"Lend {amt} XEL @ {ibps}bps for {dur} blocks?"):
                run_tx(b, lambda a=atomic, i=ibps_i, d=dur_i, ca=catom:
                       b.pl_create_offer(b.xel_asset, a, i, d, b.vlt_asset, ca),
                       "Create loan offer")
        elif choice == "accept":
            oid = text_input("Offer ID to accept:").strip()
            if not oid:
                continue
            coll = ask_amount(b, b.vlt_asset, "Collateral VLT to attach:", "100")
            catom = parse_amount(coll)
            if catom is None:
                continue
            if confirm(f"Accept offer #{oid} with {coll} VLT collateral?"):
                run_tx(b, lambda i=int(oid), c=catom:
                       b.pl_accept_offer(i, b.vlt_asset, c),
                       "Accept loan offer")
        elif choice == "repay":
            oid = text_input("Offer ID to repay:").strip()
            if not oid:
                continue
            amt = ask_amount(b, b.xel_asset, "Repay amount (XEL, include interest):", "1.1")
            atomic = parse_amount(amt)
            if atomic is None:
                continue
            if confirm(f"Repay offer #{oid} with {amt} XEL?"):
                run_tx(b, lambda i=int(oid), a=atomic: b.pl_repay(i, a),
                       "Repay loan")
        elif choice == "cancel":
            oid = text_input("Offer ID to cancel:").strip()
            if not oid:
                continue
            if confirm(f"Cancel offer #{oid}?"):
                run_tx(b, lambda i=int(oid): b.pl_cancel_offer(i),
                       "Cancel loan offer")


def screen_syndicate(b: Backend):
    while True:
        count = b.sp_count()
        sub = f"Pools: {count if count is not None else '—'}"
        opts = [("Create pool", "create"),
                ("Supply to pool", "supply"),
                ("Activate pool (borrower)", "activate"),
                ("Repay pool", "repay"),
                ("Claim from pool", "claim"),
                ("Back", None)]
        choice = menu("Syndicate Pools", opts, subtitle=sub)
        if choice is None:
            return
        if choice == "create":
            amt = ask_amount(b, b.xel_asset, "Total pool size (XEL):", "1")
            atomic = parse_amount(amt)
            if atomic is None:
                continue
            ibps = text_input(f"Interest bps (max {MAX_INTEREST_BPS}):").strip() or "500"
            dur = text_input(f"Duration in blocks (min {MIN_LEND_DURATION_BLOCKS}):").strip() or f"{MIN_LEND_DURATION_BLOCKS}"
            if not ibps.isdigit() or not dur.isdigit():
                info_box("Invalid input", [render_error("Interest bps and duration must be numbers.")], color=C.RED)
                continue
            ibps_i, dur_i = int(ibps), int(dur)
            if not (0 < ibps_i <= MAX_INTEREST_BPS):
                info_box("Invalid input", [render_error(f"Interest bps must be between 1 and {MAX_INTEREST_BPS}.")], color=C.RED)
                continue
            if dur_i < MIN_LEND_DURATION_BLOCKS:
                info_box("Invalid input", [render_error(f"Duration must be at least {MIN_LEND_DURATION_BLOCKS} blocks.")], color=C.RED)
                continue
            coll = ask_amount(b, b.vlt_asset, "Collateral required (VLT):", "100")
            catom = parse_amount(coll)
            if catom is None:
                continue
            if confirm(f"Create syndicate pool: {amt} XEL @ {ibps}bps, {coll} VLT collateral?"):
                run_tx(b, lambda a=atomic, i=ibps_i, d=dur_i, ca=catom:
                       b.sp_create_pool(b.xel_asset, a, i, d, b.vlt_asset, ca),
                       "Create syndicate pool")
        elif choice == "supply":
            pid = text_input("Pool ID to supply to:").strip()
            if not pid:
                continue
            amt = ask_amount(b, b.xel_asset, "XEL to supply:", "0.5")
            atomic = parse_amount(amt)
            if atomic is None:
                continue
            if confirm(f"Supply {amt} XEL to pool #{pid}?"):
                run_tx(b, lambda i=int(pid), a=atomic: b.sp_supply(i, a),
                       "Supply to pool")
        elif choice == "activate":
            pid = text_input("Pool ID to activate:").strip()
            if not pid:
                continue
            if confirm(f"Activate pool #{pid}? (requires full funding + collateral attached)"):
                run_tx(b, lambda i=int(pid): b.sp_activate(i),
                       "Activate pool")
        elif choice == "repay":
            pid = text_input("Pool ID to repay:").strip()
            if not pid:
                continue
            amt = ask_amount(b, b.xel_asset, "XEL to repay:", "1")
            atomic = parse_amount(amt)
            if atomic is None:
                continue
            if confirm(f"Repay {amt} XEL to pool #{pid}?"):
                run_tx(b, lambda i=int(pid), a=atomic: b.sp_repay(i, a),
                       "Repay pool")
        elif choice == "claim":
            pid = text_input("Pool ID to claim from:").strip()
            if not pid:
                continue
            if confirm(f"Claim from pool #{pid}?"):
                run_tx(b, lambda i=int(pid): b.sp_claim(i),
                       "Claim from pool")


# --- Auctions screen --------------------------------------------------------

def screen_auctions(b: Backend):
    while True:
        count = b.au_count()
        sub = f"Auctions: {count if count is not None else '—'}"
        opts = [("Create auction (seller)", "create"),
                ("Commit bid (buyer)", "commit"),
                ("Reveal bid (buyer)", "reveal"),
                ("Settle / declare winner", "settle"),
                ("Claim asset / proceeds", "claim"),
                ("Back", None)]
        choice = menu("Sealed-Bid Auctions", opts, subtitle=sub)
        if choice is None:
            return
        if choice == "create":
            amt = ask_amount(b, b.vlt_asset, "VLT amount to auction:", "10")
            atomic = parse_amount(amt)
            if atomic is None:
                continue
            minb = ask_amount(b, b.xel_asset, "Minimum bid (XEL):", "0.1")
            minb_atomic = parse_amount(minb)
            if minb_atomic is None:
                continue
            cdur = text_input(f"Commit duration blocks (min {MIN_AUCTION_DURATION_BLOCKS}):").strip() or f"{MIN_AUCTION_DURATION_BLOCKS}"
            rdur = text_input(f"Reveal duration blocks (min {MIN_AUCTION_DURATION_BLOCKS}):").strip() or f"{MIN_AUCTION_DURATION_BLOCKS}"
            if not cdur.isdigit() or not rdur.isdigit():
                info_box("Invalid input", [render_error("Durations must be numbers.")], color=C.RED)
                continue
            cdur_i, rdur_i = int(cdur), int(rdur)
            if cdur_i < MIN_AUCTION_DURATION_BLOCKS or rdur_i < MIN_AUCTION_DURATION_BLOCKS:
                info_box("Invalid input", [render_error(f"Durations must be at least {MIN_AUCTION_DURATION_BLOCKS} blocks.")], color=C.RED)
                continue
            if confirm(f"Auction {amt} VLT, min bid {minb} XEL?"):
                run_tx(b, lambda a=atomic, m=minb_atomic, c=cdur_i, r=rdur_i:
                       b.au_create(b.vlt_asset, a, b.xel_asset, m, c, r),
                       "Create auction")
        elif choice == "commit":
            aid = text_input("Auction ID:").strip()
            if not aid:
                continue
            bh = text_input("Bid hash (64 hex, blake3 of 'amount|nonce|addr'):").strip()
            if not bh or len(bh) != 64:
                info_box("Invalid", ["Need 64-char hex hash."], color=C.RED)
                continue
            if confirm(f"Commit bid on auction #{aid}?"):
                run_tx(b, lambda i=int(aid), h=bh: b.au_commit(i, h),
                       "Commit bid")
        elif choice == "reveal":
            aid = text_input("Auction ID:").strip()
            if not aid:
                continue
            amt = ask_amount(b, b.xel_asset, "Bid amount (XEL):", "1")
            atomic = parse_amount(amt)
            if atomic is None:
                continue
            nonce = text_input("Nonce (integer used in hash):").strip() or "0"
            if not nonce.isdigit():
                info_box("Invalid input", [render_error("Nonce must be a number.")], color=C.RED)
                continue
            if confirm(f"Reveal bid {amt} XEL on auction #{aid}?"):
                run_tx(b, lambda i=int(aid), a=atomic, n=int(nonce):
                       b.au_reveal(i, a, n),
                       "Reveal bid")
        elif choice == "settle":
            aid = text_input("Auction ID:").strip()
            if not aid:
                continue
            if confirm(f"Settle auction #{aid}?"):
                run_tx(b, lambda i=int(aid): b.au_settle(i),
                       "Settle auction")
        elif choice == "claim":
            aid = text_input("Auction ID:").strip()
            if not aid:
                continue
            c = text_input("Claim what? (asset/proceeds):").strip().lower()
            if c not in ("asset", "proceeds"):
                info_box("Invalid choice", [render_error("Type 'asset' or 'proceeds'.")], color=C.RED)
                continue
            if c == "asset":
                run_tx(b, lambda i=int(aid): b.au_claim_asset(i),
                       "Claim auction asset")
            elif c == "proceeds":
                run_tx(b, lambda i=int(aid): b.au_claim_proceeds(i),
                       "Claim auction proceeds")


# --- VaultChat screen -------------------------------------------------------

def screen_chat(b: Backend):
    while True:
        gc = b.chat_groups_count()
        inbox = b.chat_inbox() if hasattr(b, "chat_inbox") else []
        unread = len(inbox)
        sub = (f"Groups: {gc if gc is not None else '—'}  ·  "
               f"Inbox: {unread} message(s)")
        opts = [("Inbox / read messages", "inbox"),
                ("Register session", "register"),
                ("Send direct message (on-chain, guaranteed)", "dm"),
                ("Send via relayer (store_message)", "relay_msg"),
                ("Create group", "cgrp"),
                ("Add group member", "amem"),
                ("Send group message", "gmsg"),
                ("Anchor messages", "anchor"),
                ("Relayer: bond + register", "relayer"),
                ("Relayer: set fee", "fee"),
                ("Relayer: claim fees", "claim"),
                ("Expose publicly (tunnel + endpoint update)", "public"),
                ("Back", None)]
        choice = menu("Encrypted Chat (VaultChat)", opts, subtitle=sub)
        if choice is None:
            return
        if choice == "inbox":
            msgs = b.chat_inbox() if hasattr(b, "chat_inbox") else []
            lines = []
            if not msgs:
                lines.append(f"{C.DIM}No messages yet.{C.RESET}")
            for m in msgs:
                tag = "DM" if m["kind"] == "direct" else "via relay"
                sender = short_addr(m["sender"])
                dec = b.chat_decode(m["blob"]) if hasattr(b, "chat_decode") else m["blob"]
                lines.append(f"[{tag}] {C.BOLD}{sender}{C.RESET}: {dec}")
            info_box("Chat inbox (on-chain)", lines, color=C.CYAN)
        elif choice == "register":
            ek = text_input("Encrypted session key (64 hex or any string):").strip()
            if not ek:
                continue
            k = ek if len(ek) == 64 else ek.encode().hex()[:64]
            if confirm("Register chat session?"):
                run_tx(b, lambda k=k: b.chat_register(k), "Register session")
        elif choice == "dm":
            dest = text_input("Recipient address (xet:...):").strip()
            if not dest.startswith("xet:"):
                continue
            prompt = "Message to send (encrypted before sending):"
            msg = text_input(prompt)
            if not msg:
                continue
            hexmsg = b.chat_encode(msg) if hasattr(b, "chat_encode") else msg
            if confirm(f"Send direct message to {short_addr(dest)}? "
                       f"(on-chain, guaranteed persistence)"):
                run_tx(b, lambda d=dest, m=hexmsg: b.chat_send_dm(d, m),
                       "Send DM")
        elif choice == "relay_msg":
            dest = text_input("Recipient address (xet:...):").strip()
            if not dest.startswith("xet:"):
                continue
            msg = text_input("Message to encrypt & relay:")
            if not msg:
                continue
            hexmsg = b.chat_encode(msg) if hasattr(b, "chat_encode") else msg
            if confirm(f"Send {short_addr(dest)} a message via relayer "
                       "(store_message)?"):
                run_tx(b, lambda d=dest, m=hexmsg: b.chat_store_message(d, m),
                       "Store message")
        elif choice == "cgrp":
            ek = text_input("Group encrypted key (64 hex):").strip()
            if not ek or len(ek) != 64:
                info_box("Invalid", ["Need 64-char hex key."], color=C.RED)
                continue
            if confirm("Create group chat?"):
                run_tx(b, lambda k=ek: b.chat_create_group(k), "Create group")
        elif choice == "amem":
            gid = text_input("Group ID:").strip()
            if not gid:
                continue
            addr = text_input("Member address (xet:...):").strip()
            if not addr.startswith("xet:"):
                continue
            ek = text_input("Encrypted key for member (64 hex or any string):").strip()
            if not ek:
                info_box("Invalid", ["Need an encrypted key."], color=C.RED)
                continue
            if not ek or len(ek) != 64:
                ek = ek.encode().hex()[:64]
            if confirm(f"Add {short_addr(addr)} to group #{gid}?"):
                run_tx(b, lambda g=int(gid), a=addr, k=ek:
                       b.chat_add_member(g, a, k),
                       "Add group member")
        elif choice == "gmsg":
            gid = text_input("Group ID:").strip()
            if not gid:
                continue
            msg = text_input("Message to send to group:").strip()
            if not msg:
                continue
            hexmsg = b.chat_encode(msg) if hasattr(b, "chat_encode") else msg
            if confirm(f"Send message to group #{gid}?"):
                run_tx(b, lambda g=int(gid), m=hexmsg: b.chat_group_msg(g, m),
                       "Send group message")
        elif choice == "anchor":
            root = text_input("Merkle root (64 hex):").strip()
            if not root or len(root) != 64:
                info_box("Invalid", ["Need 64-char hex root."], color=C.RED)
                continue
            count = text_input("Message count:").strip() or "1"
            if not count.isdigit():
                info_box("Invalid input", [render_error("Message count must be a number.")], color=C.RED)
                continue
            if confirm(f"Anchor {count} messages?"):
                run_tx(b, lambda r=root, c=int(count): b.chat_anchor(r, c),
                       "Anchor messages")
        elif choice == "relayer":
            amt = ask_amount(b, b.vlt_asset, f"VLT bond (min {MIN_RELAYER_BOND_VLT}):", str(MIN_RELAYER_BOND_VLT))
            atomic = parse_amount(amt)
            if atomic is None:
                continue
            ep = text_input("Relayer endpoint (url):").strip() or "http://localhost"
            if confirm(f"Bond {amt} VLT + register as relayer?"):
                res = run_tx(b, lambda a=atomic: b.chat_stake_bond(a), "Stake bond")
                if res is not None and res.ok:
                    # Wait for the bond tx to be confirmed on-chain, then
                    # register. No blind sleep: run_tx already waits for the
                    # block, so the second tx can follow immediately.
                    run_tx(b, lambda: b.chat_register_relayer(ep, RELAYER_DEFAULT_FEE_ATOMIC, 100),
                           "Register relayer")
                else:
                    info_box("Bond failed", [
                        render_error("The bond transaction was not confirmed — "
                                     "relayer registration skipped."),
                    ], color=C.RED)
        elif choice == "fee":
            tok = text_input("Token (0=XEL, 1=VLT):").strip() or "0"
            if tok not in ("0", "1"):
                info_box("Invalid input", [render_error("Token must be 0 (XEL) or 1 (VLT).")], color=C.RED)
                continue
            fee = text_input("Fee in atomic units (e.g. 1000000 = 0.01):").strip()
            if not fee:
                continue
            if not fee.isdigit():
                info_box("Invalid input", [render_error("Fee must be a number.")], color=C.RED)
                continue
            if confirm(f"Set relayer fee: {fee} for token {tok}?"):
                run_tx(b, lambda t=int(tok), f=int(fee): b.chat_set_fee(t, f),
                       "Set relayer fee")
        elif choice == "claim":
            if confirm("Claim relayer fees?"):
                run_tx(b, b.chat_claim_fees, "Claim relayer fees")


# --- Miner tools screen -----------------------------------------------------

def _relayer_server_status(cfg) -> list:
    """Returns render lines for the local relayer daemon + tunnel running state."""
    import onboarding
    st = onboarding.relayer_tunnel_status(cfg.data)
    lines = []
    if st["relayer_pid"]:
        health = onboarding.relayer_health(cfg.data)
        badge = render_ok("RUNNING") if health else render_warn("STARTING")
        lines.append(f"  {badge}  relayer (pid {st['relayer_pid']}) · "
                     f"{st['local_endpoint']}")
    else:
        lines.append(f"  {render_warn('NOT RUNNING')}  {C.DIM}(use 'Install & launch relayer' below){C.RESET}")
    if st["tunnel_pid"]:
        badge = render_ok("PUBLIC") if st["url"] else render_warn("STARTING")
        lines.append(f"  {badge}  tunnel (pid {st['tunnel_pid']})")
        if st["url"]:
            lines.append(f"  {C.CYAN}https://{st['url'].split('//')[1]}{C.RESET}  {C.DIM}(public — reachable worldwide){C.RESET}")
    else:
        lines.append(f"  {render_hint('local only')}  {C.DIM}tunnel off — use 'Expose publicly'{C.RESET}")
    if st["relayer_pid"] and health:
        try:
            import json as _json
            import urllib.request
            with urllib.request.urlopen(f"http://{st['local_endpoint']}/status", timeout=2) as resp:
                s = _json.loads(resp.read())
            lines.append(f"  {C.DIM}topo {s.get('topo')} · anchors {s.get('anchors_submitted')} "
                         f"· outbox {len(s.get('outbox_new', []) or [])}{C.RESET}")
        except Exception:
            pass
    return lines


def _relayer_guide():
    info_box("Relayer — guide (read me)", [
        f"{C.BOLD}What is a VaultChat relayer?{C.RESET}",
        "An account (with a 50 VLT bond) authorized to relay encrypted messages",
        "and anchor batches on-chain to earn VLT. It also exposes a server that",
        "clients query (inbox/groups).",
        "",
        f"{C.BOLD}Steps to become a relayer (in order) :{C.RESET}",
        f"  1. {C.CYAN}Stake relayer bond{C.RESET}  — deposit min 50 VLT as collateral.",
        f"  2. {C.CYAN}Whitelist self{C.RESET}     — admin marks your address as relayer.",
        f"  3. {C.CYAN}Register relayer{C.RESET}   — announce endpoint + free quotas.",
        f"  4. {C.CYAN}Set relayer fee{C.RESET}    — fees beyond the free tier.",
        f"  5. {C.CYAN}Install & launch relayer{C.RESET} — start the real local server.",
        "",
        f"{C.BOLD}'Register relayer' fields :{C.RESET}",
        "  Endpoint url  — the public address of your relay server. For a",
        "                 local server: http://127.0.0.1:18444 (what this CLI",
        "                 launches). A real domain if you expose it.",
        "  Free msg/day  — free messages per day per user (<={RELAYER_MAX_FREE_MESSAGES_PER_DAY}).",
        "  Free slots    — number of wallets served free (<={RELAYER_MAX_FREE_WALLET_SLOTS}).",
        f"  Fee token     — 0 = XEL, 1 = VLT.",
        f"  Fee (atomic)  — fee per message beyond free tier. Ex: 100000="
        f"{C.DIM}0.001{C.RESET}, 100000000=1.",
        f"Bond {MIN_RELAYER_BOND_VLT} VLT = {MIN_RELAYER_BOND_VLT * 10 ** DECIMALS} atomic (VLT has {DECIMALS} decimals).",
        "",
        f"{C.GRAY}The relayer daemon (relayer_server.py) handles on-chain sync,",
        f"responds on the HTTP endpoint and anchors message batches to earn",
        f"rewards. PID/logs: ~/.xelis-vault/relayer/ + logs/relayer.log.{C.RESET}",
    ], color=C.CYAN)


def _list_all_relayers(b: Backend):
    """Enumerate every registered relayer on-chain and print them (registry sync)."""
    rls = b.chat_relayers_list()
    if not rls:
        info_box("Relayers (on-chain)", ["No registered relayers found on-chain."],
                 color=C.YELLOW)
        return
    lines = [f"{C.BOLD}{len(rls)} relayer(s) registered on-chain, newest first :{C.RESET}", ""]
    for i, r in enumerate(rls, 1):
        ep = r.get("endpoint") or "—"
        lines.append(f"{C.CYAN}{i}.{C.RESET} {short_addr(r.get('addr', ''))}")
        lines.append(f"   endpoint  {C.DIM}{ep}{C.RESET}")
        lines.append(f"   free      {r.get('free_daily_limit')} msg/day · "
                     f"{r.get('free_wallet_slots')} slots")
        tokname = "XEL" if int(r.get("token") or 0) == 0 else "VLT"
        fee = int(r.get("fee") or 0)
        fee_txt = f"{fee/10**DECIMALS:g} {tokname}/msg" if fee else "0 (no fee)"
        lines.append(f"   bond {b.fmt(r.get('bond', 0), 'VLT')} · fee {fee_txt}")
        lines.append("")
    print()
    print(render_panel("  RELAYERS  ON-CHAIN  (registry)", lines,
                       border_color=C.MAGENTA, width=64))
    host = short_addr(b.address)
    print(f"  {C.DIM}Your address {host} — use 'Expose publicly' to keep the registry "
          f"endpoint pointing at a live server.{C.RESET}")
    print()


def screen_relayer(b: Backend):
    """Interactive Relayer manager: on-chain ops + local daemon + help."""
    import onboarding
    cfg = Config()
    r = b.chat_relayer_status()
    if not r:
        r = {}
    token_name = {0: "XEL", 1: "VLT"}.get(r.get("token"), "XEL")
    status = render_ok("Whitelisted") if r.get("active") else render_warn("Not whitelisted")
    reg_txt = f"{C.DIM}not registered{C.RESET}"
    if r.get("registered"):
        d = r["registered"]
        reg_txt = (f"{render_badge(d.get('endpoint', ''), C.CYAN)}"
                   f" {C.DIM}free {d.get('free_daily_limit','0')} msg/day · {d.get('free_wallet_slots','0')} slots{C.RESET}")
    lines = [
        f"{status}",
        f"{render_metrics([('Bond', b.fmt(r.get('bond', 0), 'VLT')),
                            ('Fee', f"{r.get('fee', RELAYER_DEFAULT_FEE_ATOMIC)/10**DECIMALS:g} {token_name}/msg")])}",
        f"  {C.DIM}Registration:{C.RESET}  {reg_txt}",
    ]
    print()
    print(render_panel("  RELAYER  (VaultChat)  ·  on-chain", lines, border_color=C.MAGENTA, width=64))
    print(render_panel("  RELAYER SERVER  (local daemon)", _relayer_server_status(cfg),
                       border_color=C.MAGENTA, width=64))
    print(f"  {C.DIM}Fee flow: messages over the free tier pay the relayer fee. The local daemon is"
          f" what a real endpoint points to — 'Install & launch' runs it.{C.RESET}")
    print()

    opts = [
        ("Install & launch relayer (run relayer_server.py)", "launch"),
        ("Expose publicly (free tunnel + register URL on-chain)", "public"),
        ("List all relayers (on-chain registry sync)", "list"),
        ("Stop relayer server", "stop"),
        ("Stake relayer bond (min 50 VLT)", "bond"),
        ("Whitelist self (admin: set_relayer)", "whitelist"),
        ("Register relayer (endpoint + free limits)", "register"),
        ("Set relayer fee", "fee"),
        ("Claim accumulated fees", "claim"),
        ("Help / how to be a relayer", "help"),
        ("Back", None),
    ]
    choice = menu("Relayer tools", opts)
    if choice == "launch":
        ok, msg = onboarding.start_relayer(cfg.data)
        info_box("Relayer server", [("✅ " if ok else "⚠️ ") + msg], color=(C.GREEN if ok else C.YELLOW))
    elif choice == "public":
        if confirm("Start the free Cloudflare tunnel and register the "
                   "public URL on-chain (quick * .trycloudflare.com — changes on each restart)?"):
            ok, msg = onboarding.start_relayer_public(cfg.data)
            info_box("Public relayer", [("✅ " if ok else "⚠️ ") + msg],
                     color=(C.GREEN if ok else C.YELLOW))
    elif choice == "list":
        _list_all_relayers(b)
    elif choice == "stop":
        ok, msg = onboarding.stop_relayer()
        if ok or "not running" in msg:
            ok2, msg2 = onboarding.stop_tunnel()
            info_box("Relayer server", [msg, msg2], color=(C.GREEN if ok or "not running" in msg else C.YELLOW))
        else:
            info_box("Relayer server", [msg], color=(C.YELLOW))
    elif choice == "help":
        _relayer_guide()
    elif choice == "bond":
        amt = ask_amount(b, b.vlt_asset, "VLT bond to stake (min 50):", "50")
        atomic = parse_amount(amt)
        if atomic is None:
            return
        if not _check_balance(b, b.vlt_asset, atomic):
            return
        if confirm(f"Stake {amt} VLT as relayer bond (min {MIN_RELAYER_BOND_VLT} = {MIN_RELAYER_BOND_VLT * 10 ** DECIMALS} atomic)?"):
            run_tx(b, lambda a=atomic: b.chat_stake_bond(a), "Stake relayer bond")
    elif choice == "whitelist":
        if confirm("Whitelist this address as a relayer (requires admin)?"):
            run_tx(b, lambda: b.chat_set_relayer(b.address, True),
                   "Whitelist relayer")
    elif choice == "register":
        ep = text_input("Relayer endpoint url (public address of your relay "
                        "server; local example: http://127.0.0.1:18444):").strip() or "http://127.0.0.1:18444"
        lim = text_input(f"Free messages / day / user (1-{RELAYER_MAX_FREE_MESSAGES_PER_DAY}):").strip() or "100"
        slots = text_input(f"Free wallet slots (1-{RELAYER_MAX_FREE_WALLET_SLOTS}):").strip() or "1000"
        try:
            lim, slots = int(lim), int(slots)
        except ValueError:
            info_box("Input", [f"{C.RED}Limits must be integers.{C.RESET}"], color=C.RED)
            return
        if confirm(f"Register relayer at {ep} (free {lim} msg/day, {slots} slots)?"):
            run_tx(b, lambda e=ep, l=lim, s=slots: b.chat_register_relayer(e, l, s),
                   "Register relayer")
    elif choice == "fee":
        tok = text_input("Fee token (0=XEL, 1=VLT):").strip() or "0"
        fee = text_input("Fee in atomic units (e.g. 100000 = 0.001 XEL, "
                         "100000000 = 1 XEL):").strip()
        if not fee:
            return
        try:
            tok, fee = int(tok), int(fee)
        except ValueError:
            info_box("Input", [f"{C.RED}Invalid number.{C.RESET}"], color=C.RED)
            return
        if confirm(f"Set relayer fee = {fee/10**DECIMALS:g} "
                   f"{'XEL' if tok == 0 else 'VLT'} per message?"):
            run_tx(b, lambda t=tok, f=fee: b.chat_set_fee(t, f), "Set relayer fee")
    elif choice == "claim":
        if confirm("Claim accumulated relayer fees to this wallet?"):
            run_tx(b, b.chat_claim_fees, "Claim relayer fees")


# --- Activity screen (transaction export for manual analysis) ----------------

def screen_activity(b: Backend):
    """View the local, structured transaction history and export it for
    manual analysis (Discord/sheet). The on-chain airdrop tracker is unused,
    so the CLI keeps its own ledger of every tx you perform."""
    import tx_ledger
    st = tx_ledger.stats()
    topo = b.topo()

    # ── Header / status ────────────────────────────────────────────────
    count = st.get("count", 0)
    lines = [
        f"  Wallet:  {short_addr(b.address) if b.address else st.get('wallet','—')}",
        f"  {render_metrics([('Recorded txs', count),
                            ('First', st.get('first_ts') or '—'),
                            ('Last', st.get('last_ts') or '—')])}",
        "  " + (f"{C.DIM}Every transaction you execute from this CLI is logged here "
                f"automatically.{C.RESET}"),
    ]
    print()
    print(render_panel("  YOUR  ACTIVITY  (local ledger)", lines,
                       border_color=C.CYAN, width=66))

    # ── Latest entries ─────────────────────────────────────────────────
    ents = tx_ledger.all_entries(limit=8)
    if ents:
        print()
        body = []
        for e in reversed(ents):
            ce = (f"{e.get('contract','')}.{e.get('entry','')}").strip(".")
            body.append(
                f"  #{e.get('seq')}  {C.DIM}{e.get('ts_utc','')}{C.RESET}  "
                f"{e.get('tx_hash','')[:12]}…  "
                f"{render_badge(ce or e.get('action',''), C.MAGENTA)}")
        print(render_panel(f"  LATEST  ({min(count,8)} shown of {count})", body,
                           border_color=C.CYAN, width=66))
    else:
        print()
        body = [f"  {render_warn('No transactions recorded yet.')}",
                f"  {C.DIM}They appear here automatically as you use the other "
                f"screens (swap, vault, chat…).{C.RESET}"]
        print(render_panel("  LATEST", body, border_color=C.CYAN, width=66))

    # ── Export actions ─────────────────────────────────────────────────
    print()
    opts = [
        ("Copy export block for Discord (all tx hashes)", "discord"),
        ("Save full JSON to file", "json"),
        ("Save CSV to file", "csv"),
        ("Copy raw list of tx hashes (one per line)", "raw"),
        ("Where do you send this?", "help"),
        ("Back", None),
    ]
    choice = menu("Export activity", opts)
    if choice is None:
        return
    if choice == "discord":
        block = tx_ledger.to_discord_block(b.address)
        if _clipboard_copy(block):
            info_box("Copied to clipboard", [
                "Paste it directly in the Discord channel. It contains one",
                "row per transaction: seq, timestamp, full tx hash, contract.entry",
                "action and block height.",
                "",
                f"{C.DIM}{block[:400]}{C.RESET}",
            ], color=C.GREEN)
        else:
            info_box("Discord export block", block.splitlines(),
                     color=C.GREEN)
    elif choice == "json":
        path = _save_export("activity", "json", tx_ledger.dump_json(b.address))
        info_box("Saved", [f"{C.GREEN}Ledger JSON written to:{C.RESET}", str(path)],
                 color=C.GREEN)
    elif choice == "csv":
        path = _save_export("activity", "csv", tx_ledger.to_csv(b.address))
        info_box("Saved", [f"{C.GREEN}CSV written to:{C.RESET}", str(path)],
                 color=C.GREEN)
    elif choice == "raw":
        raw = "\n".join(e.get("tx_hash", "") for e in tx_ledger.all_entries(b.address))
        if _clipboard_copy(raw):
            info_box("Copied to clipboard", [
                f"Copied {len(raw.splitlines())} transaction hash(es).",
                "Paste them in Discord — the team will look each one up on-chain.",
            ], color=C.GREEN)
        else:
            info_box("Tx hash list", [raw or "(none yet)"], color=C.GREEN)
    elif choice == "help":
        info_box("How this works", [
            "The on-chain airdrop tracker is not populated (the contracts do",
            "not credit it), so this CLI keeps its OWN history of every",
            "transaction you perform here.",
            "",
            "• Run your activity (swap, vault, mixer, chat, governance…).",
            "• Come back here and export 'for Discord' or copy the raw hashes.",
            "• Send it in the Discord channel; we'll analyse each tx on-chain",
            "  (block explorer hash lookup) and tally your participation.",
            "",
            f"{C.YELLOW}Tip: use this wallet consistently so your whole testnet",
            f"journey is attributable to one address.{C.RESET}",
        ], color=C.CYAN)


def _save_export(kind: str, ext: str, content: str):
    """Write an export file next to the ledger and return its path."""
    import tx_ledger
    import time as _t
    fname = f"{kind}_{_t.strftime('%Y%m%d_%H%M%S')}.{ext}"
    path = tx_ledger.LEDGER_DIR / fname
    tx_ledger.LEDGER_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    try:
        os.chmod(path, 0o600)
    except Exception:
        pass
    return path


def _clipboard_copy(text: str) -> bool:
    """Copy text to the system clipboard. Returns False if unavailable."""
    try:
        import shutil
        if shutil.which("pbcopy"):          # macOS
            p = subprocess.run(["pbcopy"], input=text.encode(),
                               capture_output=True, timeout=5)
            return p.returncode == 0
        if shutil.which("xclip"):           # Linux
            p = subprocess.run(["xclip", "-selection", "clipboard"],
                               input=text.encode(), capture_output=True,
                               timeout=5)
            return p.returncode == 0
        if os.name == "nt":                 # Windows
            p = subprocess.run(["powershell", "-Command",
                                "Set-Clipboard", "-Value", text],
                               capture_output=True, timeout=5)
            return p.returncode == 0
    except Exception:
        pass
    return False


# --- Miner tools screen -----------------------------------------------------

def screen_miner_tools(b: Backend):
    cfg = _load_cfg()
    while True:
        m = b.my_miner()
        stats = b.miner_stats()
        topo = b.topo()

        # ── Miner status panel ───────────────────────────────────────────
        if m and isinstance(m, list) and len(m) >= 15:
            stake = m[3]
            mask = m[4]
            hb_topo = m[6]
            rewards = m[7]
            rep = m[9]
            active = bool(m[14])
            age = max(0, topo - hb_topo) if hb_topo else -1
            srvc = []
            if mask & 1:
                srvc.append(render_badge("Oracle", C.CYAN))
            if (mask >> 1) & 1:
                srvc.append(render_badge("Chat relay", C.MAGENTA))
            svc_txt = " ".join(srvc) if srvc else f"{C.DIM}none{C.RESET}"
            status = render_ok("REGISTERED") if active else render_warn("INACTIVE")
            hb_txt = (f"{render_ok(f'{age} blocks ago')}" if age >= 0 and age < MINER_HEARTBEAT_WARN_BLOCKS
                      else (render_warn(f"{age} blocks ago") if age >= 0
                            else f"{C.DIM}never{C.RESET}"))
            lines = [
                f"{status}   {render_badge(f'Reputation {rep}', C.YELLOW)}",
                f"{render_metrics([('Stake', b.fmt(stake, 'VLT')),
                                   ('Rewards earned', b.fmt(rewards, 'VLT'))])}",
                f"{render_metrics([('Services', svc_txt),
                                   ('Last heartbeat', hb_txt)])}",
            ]
        else:
            lines = [
                f"{render_warn('Not registered')}",
                f"{C.DIM}No miner profile on-chain for {short_addr(b.address)}.{C.RESET}",
                f"{C.DIM}Use the options below to register & start earning.{C.RESET}",
            ]
        if stats.get("total_staked") is not None:
            lines.append(f"  {C.DIM}Network total staked:{C.RESET} "
                         f"{b.fmt(stats['total_staked'], 'VLT')}")
        print()
        print(render_panel("  MINER  STATUS", lines, border_color=C.CYAN, width=64))

        # ── Actions ──────────────────────────────────────────────────────
        import onboarding
        miner_pid = onboarding.miner_running()
        mopts = []
        if miner_pid:
            mopts.append((f"Stop built-in miner (pid {miner_pid})", "stop"))
        else:
            if not (m and isinstance(m, list) and len(m) >= 15 and bool(m[14])):
                mopts.append(("Register miner on-chain", "reg"))
            mopts.append(("Start built-in PoW miner", "start"))
            threads = cfg_miner_threads()
            mopts.append((f"Set thread count (currently {threads})", "threads"))
        mopts += [
            ("Send heartbeat now", "hb"),
            ("Increase miner stake", "stake"),
            ("Back", None),
        ]
        choice = menu("Miner tools", mopts)
        if choice is None:
            return
        if choice == "hb":
            if not b.has_wallet:
                info_box("Heartbeat failed", [
                    render_error("No wallet RPC configured."),
                    "Run setup first, or set wallet_url in config.",
                ], color=C.RED)
            elif not b.ping_wallet():
                info_box("Heartbeat failed", [
                    render_error("Wallet RPC is configured but unreachable."),
                    "Make sure the wallet is running and the URL is correct.",
                    "Current URL: " + (cfg.get("wallet_url") or "(empty)"),
                ], color=C.RED)
            else:
                run_tx(b, lambda: b.miner_heartbeat(), "Heartbeat")
        elif choice == "stake":
            if not b.has_wallet:
                info_box("Increase stake", [
                    render_error("No wallet RPC configured."),
                    "Run setup first, or set wallet_url in config.",
                ], color=C.RED)
            elif not b.ping_wallet():
                info_box("Increase stake", [
                    render_error("Wallet RPC is configured but unreachable."),
                    "Make sure the wallet is running and the URL is correct.",
                    "Current URL: " + (cfg.get("wallet_url") or "(empty)"),
                ], color=C.RED)
            else:
                amt = ask_amount(b, b.vlt_asset, "VLT amount to add to miner stake:", "100")
                atomic = parse_amount(amt)
                if atomic is None:
                    continue
                if not _check_balance(b, b.vlt_asset, atomic):
                    continue
                if confirm(f"Stake {amt} VLT more?"):
                    run_tx(b, lambda: b.miner_increase_stake(atomic), "Stake increase")
        elif choice == "reg":
            action_register_miner(b, cfg)
        elif choice == "start":
            cfg_obj = _load_cfg()
            ok, msg = onboarding.start_miner(cfg_obj)
            info_box("Miner", [msg], color=C.GREEN if ok else C.RED)
        elif choice == "stop":
            ok, msg = onboarding.stop_miner()
            info_box("Miner", [msg], color=C.GREEN if ok else C.RED)
        elif choice == "threads":
            cfg_obj = _load_cfg()
            t = text_input("Number of mining threads:",
                           default=str(cfg_obj.get("miner_threads") or 4))
            if t.isdigit() and 1 <= int(t) <= 64:
                cfg_obj.data["miner_threads"] = t
                cfg_obj.save()
                info_box("Saved", [f"{t} thread(s) — applies at next start."],
                         color=C.GREEN)


def _load_cfg():
    """Fresh Config instance (screens receive only the Backend)."""
    return Config()


def cfg_miner_threads() -> str:
    try:
        return str(json.loads(CONFIG_PATH.read_text()).get(
            "miner_threads") or (max(1, (__import__("os").cpu_count() or 2) - 1)))
    except Exception:
        return "?"


def action_register_miner(b: Backend, cfg: Config):
    """Register the configured wallet as a miner on-chain via XelisVaultMiner."""
    addr = cfg.get("miner_address")
    if not addr:
        info_box("Register miner", [
            render_error("No wallet address configured."),
            "Run setup first, or use 'xvault' to configure one.",
        ], color=C.RED)
        return
    if not b.has_wallet:
        info_box("Register miner", [
            render_error("No wallet RPC configured."),
            "Set wallet_url in config or run setup.",
        ], color=C.RED)
        return
    if not b.ping_wallet():
        info_box("Register miner", [
            render_error("Wallet RPC is configured but unreachable."),
            "Make sure the wallet is running and the URL is correct.",
            "Current URL: " + (cfg.get("wallet_url") or "(empty)"),
        ], color=C.RED)
        return
    m = b.my_miner()
    if m and isinstance(m, list) and len(m) >= 15 and bool(m[14]):
        info_box("Already registered", [
            render_ok("This address already has a miner profile."), "",
            "Use 'Increase miner stake' or 'Send heartbeat now' instead.",
        ], color=C.GREEN)
        return

    endpoint = cfg.get("miner_endpoint")
    if not endpoint:
        info_box("Register miner", [
            render_error("No public endpoint configured."),
            "Set your endpoint in Settings — it is advertised on-chain.",
        ], color=C.RED)
        return

    svc = cfg.get("services", "both")
    mask = {"both": SERVICE_ORACLE | SERVICE_CHAT,
            "oracle": SERVICE_ORACLE, "chat": SERVICE_CHAT}.get(svc, 3)

    min_atomic = b.miner_stake_min() or MIN_STAKE_VLT
    amt = ask_amount(b, b.vlt_asset,
                     "VLT stake to deposit (minimum required by contract):",
                     default=f"{min_atomic / 10 ** DECIMALS:g}")
    atomic = parse_amount(amt)
    if atomic is None:
        info_box("Invalid amount", [render_error("Please enter a valid number.")],
                 color=C.RED)
        return
    if atomic <= 0:
        info_box("Invalid amount", [render_error("Amount must be greater than zero.")],
                 color=C.RED)
        return
    if not _check_balance(b, b.vlt_asset, atomic):
        return

    if not confirm(f"Register this address as a miner (services mask {mask}, "
                   f"endpoint {endpoint}, stake {amt} VLT)?"):
        return

    res = run_tx(b, lambda: b.miner_register(endpoint, mask, atomic),
                 "Miner registration")
    if res is None or not res.ok:
        return
    # Verify the profile is ACTIVE on-chain (the tx is confirmed, but the
    # contract applies the registration at the next block — confirm reality).
    b.invalidate_cache()
    deadline = time.time() + 60
    active = False
    while time.time() < deadline:
        m = b.my_miner()
        if m and isinstance(m, list) and len(m) >= 15 and bool(m[14]):
            active = True
            break
        time.sleep(2)
        b.invalidate_cache()
    if active:
        info_box("Registered", [
            render_ok("Miner profile ACTIVE on-chain ✓"), "",
            f"Tx: {res.tx[:62]}…",
            "Next: enable services & send a heartbeat from the Miner tools menu.",
        ], color=C.GREEN)
    else:
        info_box("Registered", [
            render_ok("Transaction confirmed ✓"), "",
            "Profile still syncing on-chain — it will appear shortly.",
            f"Tx: {res.tx[:62]}…",
        ], color=C.GREEN)


# ---------------------------------------------------------------------------
# Settings / wallet setup
# ---------------------------------------------------------------------------

def run_onboarding(cfg: Config) -> bool:
    """Delegate to the shared onboarding wizard (English, seed-safe)."""
    import onboarding
    ok = onboarding.run_onboarding(cfg)
    cfg.load()
    return ok


def screen_settings(b: Backend, cfg: Config):
    while True:
        bundle_path = None
        for cand in (Path(__file__).parent.parent / "network" / "testnet.json",):
            if cand.exists():
                bundle_path = cand
                break
        ver = "?"
        n_contracts = "?"
        if bundle_path:
            try:
                d = json.loads(bundle_path.read_text())
                ver = d.get("version", "?")
                n_contracts = len(d.get("contracts", {}))
            except Exception:
                pass
        choice = menu("Settings", [
            ("Edit RPC endpoints", "rpc"),
            ("Reset local configuration", "reset"),
            ("Back", None),
        ], subtitle=f"Contract bundle v{ver} ({n_contracts} contracts)")
        if choice is None:
            return
        if choice == "rpc":
            rpc = text_input("Daemon JSON-RPC URL:", default=cfg.get("rpc_url")).strip()
            wal = text_input("Wallet JSON-RPC URL:", default=cfg.get("wallet_url")).strip()
            cfg.data["rpc_url"] = rpc
            cfg.data["wallet_url"] = wal
            cfg.save()
            info_box("Saved", ["RPC endpoints updated."], color=C.GREEN)
        elif choice == "reset":
            if confirm("Delete local configuration? (wallet files are kept)",
                       default_yes=False):
                CONFIG_PATH.unlink(missing_ok=True)
                cfg.__init__()
                info_box("Done", ["Configuration reset."], color=C.GREEN)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _auto_detect_wallet_config(cfg: Config) -> dict:
    """Auto-detect wallet binary, path, and password when not explicitly configured.

    Scans known locations and uses coherent defaults so the wallet can be
    auto-launched even after a minimal setup (e.g. xvault-miner setup that
    only sets wallet_url). Works on Windows, Linux, and macOS.
    Returns a dict of detected values.
    """
    detected = {}
    # ── Binary ──
    binary = cfg.get("wallet_binary")
    if not binary or not Path(binary).exists():
        found = onboarding.find_wallet_binary()
        if found:
            detected["wallet_binary"] = found
            binary = found
    # ── Wallet path ──
    # Cross-platform: same candidates on all OS (Path handles separators)
    wpath = cfg.get("wallet_path")
    if not wpath or not Path(wpath).exists():
        candidates = [
            VAULT_DIR / "wallets" / "xvault-user",
            VAULT_DIR / "wallets" / "xvault-testnet",
            VAULT_DIR / "wallets" / "xvault-mainnet",
            # Legacy / alternative locations
            Path.home() / ".xelis" / "wallet" / "testnet",
            Path.home() / ".xelis" / "wallet",
        ]
        for c in candidates:
            if c.exists() and any(c.iterdir()):
                detected["wallet_path"] = str(c)
                wpath = str(c)
                break
    # ── Password ──
    password = cfg.get("wallet_password")
    if not password:
        # The default password used by start-wallet.bat/.sh and onboarding
        detected["wallet_password"] = "testpass"
    # ── Network ──
    if not cfg.get("wallet_network"):
        detected["wallet_network"] = "testnet"
    # ── Seed (for --seed flag, optional) ──
    # Look for seed backup files to enable auto-launch with the right wallet
    seed_dir = VAULT_DIR / "seed_backup"
    if seed_dir.exists():
        seeds = list(seed_dir.glob("*.seed.txt"))
        if seeds:
            try:
                words = []
                for line in seeds[0].read_text().splitlines():
                    parts = line.strip().split(". ", 1)
                    if len(parts) == 2:
                        words.append(parts[1])
                if words:
                    detected["_wallet_seed"] = " ".join(words)
            except Exception:
                pass
    return detected


def _relaunch_wallet_bg(cfg: Config, url: str, cache_key: tuple) -> None:
    """Background relaunch of the managed wallet RPC (never blocks the UI).

    Called from ensure_wallet_alive when the wallet is configured but down.
    Runs in a daemon thread: launch the process, wait (up to 60 s) for the
    JSON-RPC to answer, then update the alive-cache so the main loop notices.
    """
    import socket
    try:
        network = cfg.get("wallet_network", "testnet")
        daemon = cfg.get("rpc_url") or onboarding.PUBLIC_NODE
        user = cfg.get("wallet_user", "wallet")
        pwd = cfg.get("wallet_pass", "testpass")
        binary = cfg.get("wallet_binary")
        wpath = cfg.get("wallet_path")
        password = cfg.get("wallet_password")
        seed = cfg.data.get("_wallet_seed")
        port = int(cfg.get("wallet_rpc_port") or 18082)

        # Auto-detect missing config
        if not binary or not wpath or not password:
            detected = _auto_detect_wallet_config(cfg)
            binary = binary or detected.get("wallet_binary")
            wpath = wpath or detected.get("wallet_path")
            password = password or detected.get("wallet_password")
            seed = seed or detected.get("_wallet_seed")
            # Persist detected values so next launch is faster
            for k, v in detected.items():
                if not k.startswith("_") and not cfg.get(k):
                    cfg.data[k] = v
            cfg.save()

        if not binary or not Path(binary).exists():
            raise FileNotFoundError("Wallet binary not found — run Setup first")
        if not wpath:
            raise FileNotFoundError("Wallet path not found — run Setup first")

        # Check if port is already in use (wallet may be starting by another process)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        try:
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                # Port is open — wallet may already be running, just wait for RPC
                try:
                    print(f"  {C.DIM}Wallet port {port} already in use, waiting for RPC...{C.RESET}")
                except Exception:
                    pass
                addr = onboarding.wait_for_wallet(url, (user, pwd), timeout_s=30)
                _WALLET_ALIVE_CACHE[cache_key] = (time.time(), bool(addr))
                return
        finally:
            sock.close()

        try:
            print(f"  {C.DIM}Auto-launching wallet on port {port}...{C.RESET}")
        except Exception:
            pass

        onboarding.launch_wallet(binary, network, daemon, password,
                                 Path(wpath), port, seed=seed,
                                 rpc_user=user, rpc_pass=pwd)
        addr = onboarding.wait_for_wallet(url, (user, pwd), timeout_s=60)
        _WALLET_ALIVE_CACHE[cache_key] = (time.time(), bool(addr))
        if addr:
            try:
                print(f"  {C.GREEN}Wallet auto-relaunched and ready on {url}{C.RESET}")
            except Exception:
                pass
    except Exception as e:
        _WALLET_ALIVE_CACHE[cache_key] = (time.time(), False)
        try:
            print(f"  {C.RED}Auto-relaunch of wallet failed: {e}{C.RESET}")
        except Exception:
            pass
    finally:
        _WALLET_RELAUNCHING.discard(cache_key)


def ensure_wallet_alive(cfg: Config) -> bool:
    """Auto-relaunch the managed wallet RPC when it is configured but down.

    This is what makes remote-node mode 'zero unavailable': the chain data
    comes from the public node and the local wallet process is (re)started
    transparently in the background. The relaunch itself runs in a worker
    thread so the menu never freezes for up to 4 minutes.

    Works even when wallet_binary/wallet_path/wallet_password are not
    explicitly configured — it auto-detects them from known defaults.
    """
    wallet_url = cfg.get("wallet_url")
    if not wallet_url:
        return False
    port = int(cfg.get("wallet_rpc_port") or 18082)
    url = f"http://127.0.0.1:{port}"
    cache_key = (url, cfg.get("wallet_user", "wallet"))
    now = time.time()
    cached = _WALLET_ALIVE_CACHE.get(cache_key)
    if cached and now - cached[0] < _WALLET_ALIVE_TTL:
        return cached[1]
    try:
        onboarding.rpc_call(url, "get_address",
                            auth=(cfg.get("wallet_user", "wallet"),
                                  cfg.get("wallet_pass", "testpass")), timeout=1.5)
        _WALLET_ALIVE_CACHE[cache_key] = (now, True)
        return True  # already up
    except Exception:
        pass
    # Wallet is down — check if we CAN relaunch (binary exists or detectable)
    binary = cfg.get("wallet_binary")
    if not binary or not Path(binary).exists():
        detected = _auto_detect_wallet_config(cfg)
        binary = detected.get("wallet_binary")
        if not binary:
            return False  # no binary available, can't relaunch
    # Relaunch in a background thread, never block the UI.
    if cache_key in _WALLET_RELAUNCHING:
        return False  # a relaunch is already in flight
    _WALLET_RELAUNCHING.add(cache_key)
    threading.Thread(target=_relaunch_wallet_bg, args=(cfg, url, cache_key),
                     daemon=True).start()
    return False


def main():
    cfg = Config()
    first_run = not CONFIG_PATH.exists()
    b = None
    cfg_version = None

    # Auto-detect and persist wallet config on first launch or if missing
    if cfg.get("wallet_url"):
        detected = _auto_detect_wallet_config(cfg)
        changed = False
        for k, v in detected.items():
            if not k.startswith("_") and not cfg.get(k):
                cfg.data[k] = v
                changed = True
        if changed:
            cfg.save()

    # Pre-flight: trigger wallet auto-relaunch early so it starts in parallel
    # with the first dashboard render. This makes the wallet appear ready
    # faster when it was already running or needs a quick relaunch.
    if cfg.get("wallet_url"):
        ensure_wallet_alive(cfg)

    while True:
        if not first_run and cfg.get("wallet_url"):
            ensure_wallet_alive(cfg)

        current_version = cfg._version
        if b is None or current_version != cfg_version:
            b = Backend(cfg.data)
            cfg_version = current_version

        online = b.topo() > 0
        wallet_ok = bool(b.wallet)
        if wallet_ok:
            try:
                b.balance()
            except Exception:
                wallet_ok = False

        # Check if wallet auto-relaunch is in progress
        wallet_relaunching = False
        wallet_port_listening = False
        if not wallet_ok and cfg.get("wallet_url"):
            port = int(cfg.get("wallet_rpc_port") or 18082)
            url = f"http://127.0.0.1:{port}"
            cache_key = (url, cfg.get("wallet_user", "wallet"))
            wallet_relaunching = cache_key in _WALLET_RELAUNCHING
            # Check if port is already listening (wallet process starting up)
            if not wallet_relaunching:
                import socket as _sock
                _s = _sock.socket(_sock.AF_INET, _sock.SOCK_STREAM)
                _s.settimeout(0.5)
                try:
                    if _s.connect_ex(("127.0.0.1", port)) == 0:
                        wallet_port_listening = True
                finally:
                    _s.close()

        title_lines = [BANNER]
        clear()
        print(BANNER)
        print(f"{C.GRAY}{'─' * 66}{C.RESET}")
        net = f"{C.GREEN}● daemon online{C.RESET}" if online else \
              f"{C.RED}○ daemon offline{C.RESET}"
        if wallet_ok:
            wal = f"{C.GREEN}● wallet ready{C.RESET}"
        elif wallet_relaunching:
            wal = f"{C.YELLOW}◌ wallet starting…{C.RESET}"
        elif wallet_port_listening:
            wal = f"{C.YELLOW}◌ wallet syncing…{C.RESET}"
        elif cfg.get("wallet_url"):
            wal = f"{C.RED}○ wallet unreachable{C.RESET}"
        else:
            wal = f"{C.YELLOW}○ no wallet configured{C.RESET}"
        addr = short_addr(cfg.get("miner_address")) if cfg.get("miner_address") else short_addr(b.address)
        print(f"  {net}   {wal}   Address: {addr}")
        if wallet_relaunching:
            print(f"  {C.DIM}  ↳ Auto-launching wallet in background…{C.RESET}")
        print()

        opts = [
            ("Dashboard (live)", lambda: screen_dashboard(b)),
            ("Vault — collateralized xUSD", lambda: screen_vault(b)),
            ("Swap (xUSD / AMM)", lambda: screen_swap(b)),
            ("Savings", lambda: screen_savings(b)),
            ("Privacy Mixer", lambda: screen_privacy(b)),
            ("Governance", lambda: screen_governance(b)),
            ("Loans (Flash / Peer / Syndicate)", lambda: screen_loans(b)),
            ("Sealed-Bid Auctions", lambda: screen_auctions(b)),
            ("Encrypted Chat", lambda: screen_chat(b)),
            ("Relayer (bond / fee / claim)", lambda: screen_relayer(b)),
            ("Activity / export my txs", lambda: screen_activity(b)),
            ("Treasury (multisig)", lambda: screen_treasury(b)),
            ("RWA Assets", lambda: screen_rwa(b)),
            ("Miner tools", lambda: screen_miner_tools(b)),
            ("Faucet", lambda: screen_faucet(b)),
        ]
        opts.append(("Settings", ("settings",)))
        if first_run or not wallet_ok:
            opts.insert(0, ("Set up wallet / node", ("setup",)))
        opts.append(("Quit", ("quit",)))

        choice = menu("", opts)
        if choice is None or choice == ("quit",):
            clear()
            return
        if choice == ("setup",):
            first_run = not run_onboarding(cfg)
            continue
        if choice == ("settings",):
            screen_settings(b, cfg)
            continue
        # normal screens
        try:
            choice()
        except Exception as e:
            info_box("Error", [str(e)[:200]], color=C.RED)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        clear()
