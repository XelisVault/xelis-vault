#!/usr/bin/env python3
"""
============================================================================
 XELIS Vault — Miner / Oracle Operator Console (xvault-miner)
============================================================================
Live auto-refreshing dashboard + guided setup + operator handbook.

Run:  xvault-miner
      xvault-miner --setup        (guided first-time config)
      xvault-miner --rpc URL      (override daemon RPC)

Everything reads REAL on-chain state through the same cli_backend as the
xvault CLI. Keys:
      q quit   r refresh   R reset config   a auto-refresh toggle   s setup
      m actions menu       p price-provider handbook
============================================================================
"""
from __future__ import annotations

import json
import os
import platform
import signal
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import re
import requests

sys.path.insert(0, str(Path(__file__).parent))
from config import Config
from tui import (
    C, BANNER, clear, hide_cursor, show_cursor, read_key, read_key_timeout,
    menu, text_input, confirm, info_box, render_panel, render_metrics,
    render_badge, render_bar, render_ok, render_warn, render_error,
    render_status,
)
from cli_backend import Backend, DECIMALS, ZERO_HASH, load_bundle
from protocol import MIN_STAKE_VLT
from onboarding import relayer_tunnel_status

VAULT_DIR = Path.home() / ".xelis-vault"
LOG_DIR = VAULT_DIR / "logs"

REFRESH_INTERVAL = 5

_FETCH_LIVE_CACHE = {}
_FETCH_LIVE_TTL = 2.0
_FETCH_LIVE_MAX = 64
_FETCH_EXECUTOR = ThreadPoolExecutor(max_workers=4)

# Miner struct field order (XelisVaultMiner.slx `Miner`) returned for key
# `miner_<addr>`:
#   0 addr, 1 endpoint_url, 2 miner_pubkey, 3 stake, 4 services_mask,
#   5 registered_at, 6 last_heartbeat, 7 total_rewards_earned,
#   8 total_slashed, 9 reputation, 10 valid_submissions,
#   11 successful_anchors, 12 total_submissions, 13 last_infraction_topo,
#   14 active
M_ADDR, M_ENDPOINT, M_PUBKEY, M_STAKE, M_MASK, M_AT, M_HB, M_REW, \
    M_SLASH, M_REP, M_VSUB, M_ANCH, M_TSUB, M_LINF, M_ACTIVE = range(15)

SERVICE_ORACLE, SERVICE_CHAT = 1, 2

PUBLIC_TESTNET_RPC = "https://testnet-node.xelis.io/json_rpc"

# Emission / halving (site values)
INITIAL_EMISSION_VLT = 0.436       # VLT per block at launch
HALVING_INTERVAL_BLOCKS = 6_307_200  # ~1 year at 5s block time
NEW_MINER_BONUS_DAYS = 30
TIME_PROVEN_BONUS_DAYS = 15
TIME_PROVEN_BONUS_REP = 2000
REP_START = 3000
REP_BANNED = 0
REP_CRITICAL = 1000
REP_WARNING = 2000
REP_GOOD = 5000
REP_EXCELLENT = 8000
REP_MAX = 10000


def short_addr(a: str, n: int = 10) -> str:
    """Truncate an address or hash for display."""
    if not a:
        return "-"
    return f"{a[:n]}...{a[-6:]}"


def _check_balance(b: Backend, asset: str, atomic: int) -> bool:
    """True if the wallet can spend `atomic` of `asset`; shows error otherwise."""
    asset_name = {ZERO_HASH: "XEL", b.vlt_asset: "VLT", b.xusd_asset: "xUSD"}.get(asset, asset[:16])
    addr = getattr(b, "address", "(unknown)")
    balance_error = "unknown"
    try:
        avail = b.balance(asset)
    except Exception as e:
        avail = None
        balance_error = str(e)
    if avail is None:
        wallet_url = getattr(b, "cfg", {}).get("wallet_url", "(not set)") if hasattr(b, "cfg") else "(not set)"
        wallet_user = getattr(b, "cfg", {}).get("wallet_user", "(not set)") if hasattr(b, "cfg") else "(not set)"
        info_box("Balance check failed", [
            f"{C.RED}Could not read wallet balance.{C.RESET}",
            "",
            f"Wallet URL : {wallet_url}",
            f"Wallet user: {wallet_user}",
            f"Address    : {addr}",
            f"Asset      : {asset_name}",
            f"Error      : {balance_error if 'balance_error' in locals() else 'unknown'}",
            "",
            f"{C.GRAY}If you see 401, the wallet RPC user/pass is wrong.{C.RESET}",
            f"{C.GRAY}Check your config or relaunch the wallet with the expected credentials.{C.RESET}",
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


def confirm_miner_tx(b: Backend, res, action: str, expect_active: bool = False,
                     max_s: int = 120) -> tuple:
    """Wait for a miner tx to be MINED, verify it did not revert on-chain,
    and (optionally) confirm the miner profile is ACTIVE on-chain.

    This is what makes registration/heartbeat/stake/service actions
    "conforme et réel": the result box only ever says SUCCESS once the
    network actually accepted and applied the tx — never right after the
    local broadcast (which can still be rejected a few seconds later).
    Returns (ok, message).
    """
    if not res or not res.ok:
        return False, (res.reason if res else "no response")
    print(f"\n{C.DIM}⏳ {action} — broadcast sent, waiting for the block…{C.RESET}", flush=True)
    t0 = time.time()
    ok = False
    # Fast polling: 1s interval for quick block confirmation
    while time.time() - t0 < max_s:
        try:
            r = b.daemon.get_transaction(res.tx)
            if isinstance(r, dict):
                topo = (r.get("executed_in_block") or r.get("block_topoheight")
                        or r.get("topoheight"))
                if topo or r.get("blocks"):
                    ok = True
                    break
        except Exception:
            pass
        time.sleep(1)
    if not ok:
        return False, "Broadcast sent but no block confirmation after " \
                      f"{max_s}s — check the explorer later."
    # On-chain revert check (a mined tx can still be rolled back)
    revert = ""
    try:
        revert = b.verify_onchain(res.tx, timeout=10)
    except Exception:
        pass
    if revert:
        return False, f"REVERTED on-chain: {revert}"
    if expect_active:
        b.invalidate_cache()
        # Fast polling for ACTIVE status: 1s interval, 60s max
        deadline = time.time() + 60
        while time.time() < deadline:
            m = b.my_miner()
            if m and isinstance(m, list) and len(m) >= 15 and bool(m[14]):
                return True, "confirmed & profile ACTIVE on-chain"
            time.sleep(1)
            b.invalidate_cache()
        return True, ("tx confirmed but profile not yet ACTIVE on-chain. "
                      "This is normal — wait 1-2 minutes and check the dashboard. "
                      "If still inactive, your stake may be below the minimum.")
    return True, "confirmed on-chain"


def _fallback_rpc_if_needed(cfg) -> str:
    """If the configured daemon RPC is unreachable, switch to the public
    testnet node and persist the new URL so the next launch reuses it.
    Returns a hint string if a fallback occurred, else empty string."""
    url = cfg.data.get("rpc_url", "")
    if not url:
        return ""
    endpoint = url.rstrip("/")
    if endpoint and not endpoint.endswith("/json_rpc"):
        endpoint += "/json_rpc"
    try:
        r = requests.post(endpoint, json={"jsonrpc": "2.0", "id": 1,
                                     "method": "get_topoheight", "params": {}},
                           timeout=1.5)
        if r.status_code == 200:
            return ""
    except Exception:
        pass
    try:
        r2 = requests.post(PUBLIC_TESTNET_RPC,
                           json={"jsonrpc": "2.0", "id": 1,
                                 "method": "get_topoheight", "params": {}},
                           timeout=3)
        if r2.status_code == 200:
            cfg.data["rpc_url"] = PUBLIC_TESTNET_RPC
            cfg.save()
            return f"{C.YELLOW}Configured daemon unreachable, switched to public testnet node.{C.RESET}"
    except Exception:
        pass
    return ""


def bootstrap_wallet_with_seed(cfg, seed: str) -> bool:
    """Import an existing seed into a fresh xelis_wallet and wire it into the
    config, so the miner can sign registration / stake / heartbeat txs."""
    from onboarding import (find_wallet_binary, download_wallet_binary,
                           launch_wallet, wait_for_wallet, free_port,
                           WALLETS_DIR)
    binary = find_wallet_binary()
    if not binary:
        print("Downloading official XELIS wallet...")
        binary = download_wallet_binary()
    if not binary:
        print("ERROR: xelis_wallet binary not found (download failed).")
        return False
    network = "testnet"
    daemon_url = cfg.get("rpc_url") or PUBLIC_TESTNET_RPC
    password = "xvault-" + os.urandom(9).hex()
    wdir = WALLETS_DIR / f"xvault-{network}"
    rpc_port = free_port(18082)
    print(f"Lancement du wallet (reseau {network}) avec le seed fourni...")
    launch_wallet(binary, network, daemon_url, password, wdir, rpc_port,
                  seed=seed)
    url = f"http://127.0.0.1:{rpc_port}"
    addr = wait_for_wallet(url, ("wallet", "testpass"), timeout_s=120)
    if not addr:
        print("Wallet did not respond. Logs: "
              f"{VAULT_DIR / 'logs' / 'wallet.log'}")
        return False
    cfg.data.update({
        "wallet_url": url, "wallet_user": "wallet", "wallet_pass": "testpass",
        "wallet_binary": binary, "wallet_network": network,
        "wallet_password": password, "wallet_path": str(wdir),
        "wallet_rpc_port": rpc_port, "miner_address": addr,
    })
    cfg.save()
    print("Wallet ready. Verified address:", addr)
    return True


def register_miner_cli(cfg, endpoint: str, services: str, stake_vlt: float):
    """Register the configured wallet as a miner on XelisVaultMiner."""
    if not cfg.get("wallet_url"):
        print("ERROR: no wallet configured. Import your seed first "
              "(--import-seed).")
        return
    b = Backend(cfg.data)
    if not getattr(b, "address", None):
        print("ERROR: cannot read connected wallet address.")
        return
    # Check if miner binary is available (warning only, not blocking)
    from onboarding import find_miner_binary
    miner_bin = find_miner_binary()
    if not miner_bin:
        print("WARNING: xelis_miner binary not found locally.")
        print("  You can still register on-chain, but you will need to")
        print("  download the miner binary to start mining locally.")
        print("  Run with --setup or see documentation for details.")
        print()
    mask = {"both": 3, "oracle": 1, "chat": 2}.get(services or "both", 3)
    min_atomic = b.miner_stake_min() or MIN_STAKE_VLT
    try:
        stake_atomic = int(float(stake_vlt) * 10 ** DECIMALS)
    except (ValueError, TypeError):
        print("ERROR: invalid stake amount.")
        return
    if stake_atomic < min_atomic:
        stake_atomic = min_atomic
    print(f"Registering {b.address} as a miner...")
    print(f"  endpoint = {endpoint}")
    print(f"  services = {mask} ({services or 'both'})  stake = "
          f"{stake_atomic / 10 ** DECIMALS:g} VLT")
    res = b.miner_register(endpoint, mask, stake_atomic)
    ok, msg = confirm_miner_tx(b, res, "Miner registration", expect_active=True)
    if ok:
        print("OK: miner ACTIVE on-chain -> " + res.tx[:44] + "...")
        if not miner_bin:
            print("NOTE: To start mining locally, download xelis_miner and")
            print("      run 'xvault-miner --miner' or use the Actions menu.")
    else:
        print("FAILED: " + msg)


# ---------------------------------------------------------------------------
# Tier / formatting helpers
# ---------------------------------------------------------------------------

def tier_name(rep):
    if rep >= 8000: return "EXCELLENT"
    if rep >= 5000: return "GOOD"
    if rep >= 2000: return "WARNING"
    if rep >= 1000: return "CRITICAL"
    return "LOW"


def tier_color(tier):
    return {"EXCELLENT": C.GREEN, "GOOD": C.CYAN, "WARNING": C.YELLOW,
            "CRITICAL": C.RED, "LOW": C.RED + C.BOLD}.get(tier, C.GRAY)


def tier_bar(rep):
    """Reputation as a fractional bar (quiet look)."""
    return render_bar(min(rep / 10000, 1.0), 20)


def svc_badges(mask):
    out = []
    if mask & SERVICE_ORACLE:
        out.append(render_badge("Oracle", C.CYAN))
    if mask & SERVICE_CHAT:
        out.append(render_badge("Chat relay", C.MAGENTA))
    return " ".join(out) if out else f"{C.DIM}none{C.RESET}"


# ---------------------------------------------------------------------------
# Live data collection (real reads via the backend)
# ---------------------------------------------------------------------------

def fetch_live(cfg, b: Backend) -> dict:
    now = time.time()
    cache_key = id(b)
    cached = _FETCH_LIVE_CACHE.get(cache_key)
    if cached and now - cached[0] < _FETCH_LIVE_TTL:
        return cached[1]

    live = {"connected": False, "topo": 0, "balances": {},
            "miner": {}, "stats": {}, "feeds": [], "relayer": None,
            "error": "", "diag": {}}

    def _safe(fn, default=None):
        try:
            return fn(), None
        except Exception as e:
            return default, e

    try:
        topo = b.topo()
    except Exception as e:
        live["error"] = f"daemon unreachable: {e}"
        return live
    if not topo:
        _FETCH_LIVE_CACHE[cache_key] = (now, live)
        return live
    live["connected"] = True
    live["topo"] = topo

    futures = {
        "balances": _FETCH_EXECUTOR.submit(_safe, b.balances, {}),
        "miner": _FETCH_EXECUTOR.submit(_safe, b.my_miner),
        "stats": _FETCH_EXECUTOR.submit(_safe, b.miner_stats, {}),
        "price": _FETCH_EXECUTOR.submit(_safe, b.price, None),
        "tunnel": _FETCH_EXECUTOR.submit(_safe, relayer_tunnel_status, None),
        "relayer": _FETCH_EXECUTOR.submit(_safe, lambda: b.chat_relayer_status(b.address) if b.has_wallet else None, None),
    }
    results = {k: f.result() for k, f in futures.items()}

    bal, e = results["balances"]
    if e:
        live["error"] = f"balances failed: {e}"
    live["balances"] = bal or {}

    try:
        live["diag"] = {
            "address": getattr(b, "address", "(unknown)"),
            "wallet_url": getattr(b, "cfg", {}).get("wallet_url", "(not set)") if hasattr(b, "cfg") else "(not set)",
            "vlt_asset": getattr(b, "vlt_asset", "(not loaded)"),
            "xusd_asset": getattr(b, "xusd_asset", "(not loaded)"),
            "has_wallet": bool(getattr(b, "wallet", None)),
        }
    except Exception:
        pass

    m, e = results["miner"]
    if e:
        live["error"] = f"my_miner failed: {e}"
    elif isinstance(m, list) and len(m) >= 15:
        try:
            live["miner"] = {
                "endpoint": str(m[M_ENDPOINT]),
                "stake": int(m[M_STAKE]),
                "mask": int(m[M_MASK]),
                "registered_at": int(m[M_AT]),
                "hb_topo": int(m[M_HB]),
                "rewards": int(m[M_REW]),
                "slashed": int(m[M_SLASH]),
                "reputation": int(m[M_REP]),
                "valid_submissions": int(m[M_VSUB]),
                "anchors": int(m[M_ANCH]),
                "total_submissions": int(m[M_TSUB]),
                "active": bool(m[M_ACTIVE]),
            }
        except (ValueError, TypeError):
            pass

    stats, e = results["stats"]
    if e:
        live["error"] = f"miner_stats failed: {e}"
    live["stats"] = stats or {}

    price, _ = results["price"]
    if price:
        price_raw, feed_topo, stale = price
        live["feeds"].append({"name": "XEL/USD", "price_raw": price_raw,
                              "age": max(0, topo - feed_topo), "stale": stale})

    tunnel, _ = results["tunnel"]
    live["tunnel"] = tunnel

    relayer, _ = results["relayer"]
    live["relayer"] = relayer

    if len(_FETCH_LIVE_CACHE) >= _FETCH_LIVE_MAX:
        _FETCH_LIVE_CACHE.clear()
    _FETCH_LIVE_CACHE[cache_key] = (now, live)
    return live


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

def render_dashboard(cfg, live, hint=""):
    clear()
    now = datetime.now().strftime("%H:%M:%S")
    addr = cfg.get("miner_address") or cfg.get("wallet_url") and "(wallet set)" or "(not set)"

    # ── Header ──
    conn_badge = render_ok("ONLINE") if live["connected"] else render_error("OFFLINE")
    topo = f"{live['topo']:,}" if live["connected"] else "-"
    print(f"{C.CYAN}{C.BOLD}  XELIS VAULT {C.RESET}{render_badge('MINER / ORACLE OPERATOR', C.MAGENTA)}  "
          f"{C.DIM}{now}{C.RESET}")
    print(f"  {C.DIM}Operator:{C.RESET} {C.CYAN}{addr}{C.RESET}  {C.DIM}│{C.RESET}  {C.DIM}Daemon:{C.RESET} {conn_badge}  "
          f"{C.DIM}Topo:{C.RESET} {C.BOLD}{topo}{C.RESET}")

    if live.get("error"):
        print(f"  {C.RED}{C.BOLD}  ! {live['error']}{C.RESET}")

    # ── Miner status panel ──
    m = live.get("miner") or {}
    stats = live.get("stats") or {}
    if m:
        active = m.get("active", False)
        status = render_ok("ACTIVE") if active else render_warn("INACTIVE")
        rep = m.get("reputation", 3000)
        tier = tier_name(rep)
        tcolor = tier_color(tier)
        mask = m.get("mask", 0)
        hb = m.get("hb_topo", 0)
        if hb and live["connected"]:
            age = max(0, live["topo"] - hb)
            if age < 500:
                hb_txt = render_ok(f"{age} blk")
            elif age < 1000:
                hb_txt = f"{C.YELLOW}● {age} blk{C.RESET}"
            else:
                hb_txt = render_warn(f"{age} blk — needs refresh")
        else:
            hb_txt = f"{C.DIM}never{C.RESET}"
        print()
        print(f"  {status}  {render_badge(f'{tier}', tcolor)}  "
              f"{C.DIM}Rep:{C.RESET} {tier_bar(rep)} {C.BOLD}{rep}{C.RESET}{C.DIM}/10000{C.RESET}")
        # Show stake with min_stake comparison if inactive
        stake = m.get('stake', 0)
        min_stake = stats.get('min_stake') or MIN_STAKE_VLT
        if not active and stake < min_stake:
            print(f"  {C.DIM}Stake:{C.RESET}    {C.YELLOW}{bfmt(stake, 'VLT')}{C.RESET} {C.DIM}(min: {bfmt(min_stake, 'VLT')}){C.RESET}  "
                  f"{C.DIM}Rewards:{C.RESET} {bfmt(m.get('rewards'), 'VLT')}  "
                  f"{C.DIM}Slashed:{C.RESET} {bfmt(m.get('slashed'), 'VLT')}")
        else:
            print(f"  {C.DIM}Stake:{C.RESET}    {bfmt(stake, 'VLT')}  "
                  f"{C.DIM}Rewards:{C.RESET} {bfmt(m.get('rewards'), 'VLT')}  "
                  f"{C.DIM}Slashed:{C.RESET} {bfmt(m.get('slashed'), 'VLT')}")
        # Submissions with success rate
        vsub = m.get('valid_submissions', 0)
        tsub = m.get('total_submissions', 0)
        rate = f"{vsub * 100 // tsub}%" if tsub > 0 else "--"
        rate_color = C.GREEN if tsub == 0 or vsub / max(tsub, 1) > 0.9 else C.YELLOW
        print(f"  {C.DIM}Heartbeat:{C.RESET} {hb_txt}  "
              f"{C.DIM}Submissions:{C.RESET} {C.BOLD}{vsub}{C.RESET}{C.DIM}/{tsub} "
              f"({rate_color}{rate}{C.RESET})")
        # Services
        svcs = []
        if mask & 1: svcs.append(f"{C.CYAN}Oracle{C.RESET}")
        if mask & 2: svcs.append(f"{C.MAGENTA}Chat{C.RESET}")
        svc_txt = " ".join(svcs) if svcs else f"{C.DIM}none{C.RESET}"
        print(f"  {C.DIM}Services:{C.RESET}  {svc_txt}  "
              f"{C.DIM}│{C.RESET}  {C.DIM}Endpoint:{C.RESET} {m.get('endpoint') or '—'}")
        # Inactive hint
        if not active:
            print(f"  {C.YELLOW}→ Inactive: use Actions menu to increase stake or send heartbeat{C.RESET}")
    else:
        print()
        _W = 61  # interior width of the box
        def _bl(content: str) -> str:
            """Pad a box line to exactly _W visible chars (ignoring ANSI)."""
            visible = re.sub(r"\x1b\[[0-9;]*m", "", content)
            pad = max(0, _W - len(visible))
            return f"  {C.YELLOW}│{C.RESET}{content}{' ' * pad}{C.YELLOW}│{C.RESET}"
        _top = f"  {C.YELLOW}┌{'─' * _W}┐{C.RESET}"
        _bot = f"  {C.YELLOW}└{'─' * _W}┘{C.RESET}"
        print(_top)
        print(_bl(f"  {C.BOLD}{C.YELLOW}⚠ NOT REGISTERED{C.RESET}"))
        print(_bl(""))
        print(_bl(f"  {C.DIM}Register to start earning VLT rewards:{C.RESET}"))
        print(_bl(f"    {C.BOLD}1.{C.RESET} Press {C.CYAN}{C.BOLD}m{C.RESET} to open Actions menu"))
        print(_bl(f"    {C.BOLD}2.{C.RESET} Select {C.CYAN}{C.BOLD}Register as miner (guided){C.RESET}"))
        print(_bl(f"    {C.BOLD}3.{C.RESET} Follow the prompts (requires 1000 VLT stake)"))
        print(_bot)

    # ── Balances panel ──
    bal = live.get("balances") or {}
    if bal:
        bal_rows = []
        for sym, icon in [("XEL", "◆"), ("VLT", "◈"), ("xUSD", "$")]:
            v = bal.get(sym)
            color = C.GREEN if (v is not None and v > 0) else C.DIM
            bal_rows.append(f"  {icon} {C.BOLD}{sym}{C.RESET}  {color}{bfmt(v)}{C.RESET}")
        print()
        print(" ".join(bal_rows))

    # ── Protocol stats (compact) ──
    if stats:
        parts = []
        if stats.get("total_staked") is not None:
            parts.append(f"{C.DIM}Staked:{C.RESET} {bfmt(stats['total_staked'], 'VLT')}")
        if stats.get("budget") and stats.get("distributed") is not None:
            pct = stats["distributed"] * 100 // stats["budget"]
            parts.append(f"{C.DIM}Budget:{C.RESET} {pct}% {render_bar(pct / 100, 12)}")
        if stats.get("min_stake") is not None:
            parts.append(f"{C.DIM}Min:{C.RESET} {bfmt(stats['min_stake'], 'VLT')}")
        if parts:
            print(f"  {'  '.join(parts)}")

    # ── Price feeds ──
    feeds = live.get("feeds") or []
    if feeds:
        f_parts = []
        for f in feeds[:3]:
            c = C.RED if f["stale"] else C.GREEN
            price = f["price_raw"] / 10 ** DECIMALS
            if f["stale"]:
                stale = f" {C.YELLOW}(stale {f['age']}blk){C.RESET}"
            elif f["age"] < 60:
                stale = f" {C.GREEN}(fresh){C.RESET}"
            else:
                stale = f" {C.DIM}({f['age']}blk){C.RESET}"
            f_parts.append(f"{c}${price:,.2f}{C.RESET}{stale}")
        if f_parts:
            print(f"  {C.DIM}Oracle:{C.RESET} {'  '.join(f_parts)}")
    else:
        print(f"  {C.DIM}Oracle: (no data yet){C.RESET}")

    # ── Relayer + tunnel panel ──
    rl = live.get("relayer")
    tunnel = live.get("tunnel")
    if rl or tunnel:
        print()
        r_lines = []
        if rl:
            ok = rl.get("active")
            r_lines.append(f"  {C.DIM}Relayer:{C.RESET}  {render_status(bool(ok), '')}  "
                           f"{C.DIM}Bond:{C.RESET} {bfmt(rl.get('bond'), 'VLT')}")
        if tunnel:
            t_url = tunnel.get("url") or ""
            if t_url:
                r_lines.append(f"  {C.DIM}Tunnel:{C.RESET}   {C.CYAN}{t_url[:52]}{C.RESET}")
            else:
                r_lines.append(f"  {C.DIM}Tunnel:{C.RESET}   {render_warn('OFF')}")
            wd = _watchdog_state.get("last") or {}
            if wd and _watchdog_state.get("enabled"):
                healthy = wd.get("healthy")
                r_lines.append(f"  {C.DIM}Watchdog:{C.RESET}  {render_ok('OK') if healthy else render_warn('UNREACHABLE')}")
        if r_lines:
            print(render_panel("  RELAYER  &  TUNNEL", r_lines,
                               border_color=C.CYAN, width=60))

    # ── Footer ──
    print()
    print(f"{C.GRAY}{'─' * 60}{C.RESET}")
    if not cfg.get("wallet_url"):
        print(f"  {render_warn('No wallet — run setup (s)')}")
    print(f"  {C.DIM}q Quit  r Refresh  R Reset  a Auto  s Setup  m Actions  p Guide{C.RESET}")
    if hint:
        print(f"  {hint}")


def bfmt(v, suffix=""):
    """Format a possibly-None atomic balance."""
    if v is None:
        return f"{C.DIM}--{C.RESET}"
    n = v / 10 ** DECIMALS
    s = f"{n:,.4f}" if n >= 1 else f"{n:.8f}".rstrip("0").rstrip(".") or "0"
    return f"{C.GREEN}{s}{(' ' + suffix) if suffix else ''}{C.RESET}"


# ---------------------------------------------------------------------------
# Guided setup (every field explained — this was the #1 UX complaint)
# ---------------------------------------------------------------------------

def interactive_setup(cfg):
    clear()
    print(BANNER)
    print(f"\n{C.CYAN}{C.BOLD}Guided Miner Setup{C.RESET}")
    print(f"  {C.DIM}Most fields already carry a good default — press Enter to keep it.{C.RESET}\n")

    while True:
        rpc = text_input(
            "Daemon JSON-RPC URL",
            cfg.get("rpc_url"))
        if not rpc.strip():
            info_box("Invalid URL", [render_error("Daemon RPC URL cannot be empty.")], color=C.RED)
            continue
        cfg.data["rpc_url"] = rpc.strip()
        break
    print(f"{C.DIM}  → Chain node. Use {C.CYAN}https://testnet-node.xelis.io/json_rpc{C.RESET}{C.DIM} for testnet.{C.RESET}")
    time.sleep(0.4)

    wurl = text_input(
        "Wallet RPC URL  (blank = read-only mode)",
        cfg.get("wallet_url"))
    print(f"{C.DIM}  → Your wallet RPC, e.g. {C.CYAN}http://127.0.0.1:18082/json_rpc{C.RESET}{C.DIM}.\n"
          f"    Needed only for writes: heartbeat, register, stake.{C.RESET}")
    time.sleep(0.4)
    cfg.data["wallet_url"] = wurl

    while True:
        cfg.data["miner_address"] = text_input(
            "Operator address  (the wallet that becomes the miner)",
            cfg.get("miner_address"))
        addr = cfg.data.get("miner_address", "").strip()
        if not addr:
            info_box("Invalid address", [render_error("Miner address cannot be empty.")], color=C.RED)
            continue
        if not addr.startswith("xet:"):
            info_box("Invalid address", [render_error("Miner address must start with 'xet:'.")], color=C.RED)
            continue
        break
    print(f"{C.DIM}  → Must match the wallet above.{C.RESET}")
    time.sleep(0.4)

    while True:
        endp = text_input(
            "Public endpoint URL (advertised service address)",
            cfg.get("miner_endpoint"))
        if not endp.strip():
            info_box("Invalid endpoint", [render_error("Endpoint cannot be empty. It is written on-chain at registration.")], color=C.RED)
            continue
        cfg.data["miner_endpoint"] = endp.strip()
        break
    print(f"{C.DIM}  → This is where the network routes your services.{C.RESET}")
    time.sleep(0.4)

    services = menu("Which services do you support? (maximises rewards)", [
        ("Oracle only — submit prices, earn VLT", "oracle"),
        ("Chat relay only — anchor messages, earn VLT", "chat"),
        ("Both — maximize rewards (recommended)", "both"),
    ])
    if services:
        cfg.data["services"] = services

    cfg.save()
    info_box("Setup Complete", [
        render_ok("Configuration saved!"), "",
        f"Services:  {cfg.get('services')}",
        f"Address:   {cfg.get('miner_address')}",
        f"Endpoint:  {cfg.get('miner_endpoint')}", "",
        "Next: press 'm' → 'Register as miner (guided)' to register on-chain.",
        "      Then use 'Send heartbeat now' and 'Enable a service' to start earning.",
    ], color=C.GREEN)


def check_contracts(cfg):
    """Contracts come from the network bundle; only setup state matters."""
    bundle = load_bundle()
    bundle_ok = bool(bundle.get("contracts", {}).get("miner")
                     or bundle.get("contracts", {}).get("XelisVaultMiner"))
    has_wallet = bool(cfg.get("wallet_url"))
    if not bundle_ok or not has_wallet:
        clear()
        print(BANNER)
        print(f"\n{C.YELLOW}{'─' * 60}{C.RESET}")
        print(f"{render_warn('FIRST-TIME SETUP')}")
        print(f"{C.YELLOW}{'─' * 60}{C.RESET}")
        reason = "contract bundle not found" if not bundle_ok else "no wallet configured"
        print(f"\n{C.BOLD}Need to configure: {reason}.{C.RESET}")
        print(f"  The wizard guides you, explains each field, and auto-loads")
        print(f"  contract addresses from the bundled network file.\n")
        choice = menu("Start configuration?", [
            ("Yes — run the guided setup (recommended)", "setup"),
            ("Manual settings only", "manual"),
            ("View dashboard anyway (read-only demo)", "demo"),
            ("Quit", None),
        ])
        if choice == "setup":
            interactive_setup(cfg)
            return "live"
        if choice == "manual":
            interactive_setup(cfg)
            return "live"
        if choice == "demo":
            return "demo"
        return "live"
    return "live"


# ---------------------------------------------------------------------------
# Price provider handbook — the "provider guide" the user asked for
# ---------------------------------------------------------------------------

PROVIDER_GUIDE = [
    ("What is a price provider?",
     "A miner with the Oracle service enabled. Every round you submit a price",
     "for XEL/USD; the protocol aggregates honest feeds and pays VLT via the",
     "reputation system. You also earn for correct, on-time submissions."),
    ("Ready to run as a provider?",
     "1. Register as a miner with Oracle service (menu -> Register).",
     "2. Fund the wallet with a bit of XEL for tx fees.",
     "3. Launch the keeper below — it auto-submits prices + heartbeats."),
    ("How the keeper works",
     "• submit_price every round with real exchange data",
     "• poke aggregate_now to unblock the aggregation window",
     "• heartbeat every ~1000 blocks (within 900-4000 window)",
     "• small fixed fee 0.001 XEL per tx"),
    ("Health rules (StakedOracle)",
     "hard_stale = 500 blk  — feed must refresh before then",
     "hb_interval = 900      — heartbeat minimum interval",
     "hb_timeout  = 4000     — miss this and you may be slashed",
     "Keep reputation > 5000 (Good) to keep the 1.0x+ multiplier."),
    ("Tips",
     "• Never submit before the window opens (alreadysub deadlock).",
     "• Keep your node + wallet RPC online and synced.",
     "• One keeper process handles all 3 of your provider wallets."),
]


def provider_guide(cfg):
    while True:
        clear()
        print(f"{C.CYAN}{C.BOLD}  PRICE PROVIDER — HANDBOOK & LAUNCHER{C.RESET}")
        print(f"{C.GRAY}{'─' * 60}{C.RESET}\n")
        panels = []
        for title, *body in PROVIDER_GUIDE:
            panels.append(render_panel(f"  {title}", body,
                                       border_color=C.CYAN, width=58))
        print("\n\n".join(panels))

        keeper_pid = keeper_running()
        if keeper_pid:
            kline = render_ok(f"Keeper RUNNING (pid {keeper_pid})")
            launcher = [("Stop oracle keeper", "stopkeeper")]
        else:
            kline = render_warn("Oracle keeper NOT running — no live price submissions")
            launcher = [("Launch oracle keeper (auto submits prices + heartbeats)", "keeper")]

        print()
        print(render_panel("  KEEPER  STATUS", [f"  {kline}"],
                           border_color=C.MAGENTA, width=40))
        print()
        opts = launcher + [
            ("Back to dashboard", None),
        ]
        choice = menu("Provider launcher", opts)
        if choice is None:
            return
        if choice == "keeper":
            launch_keeper(cfg)
        elif choice == "stopkeeper":
            stop_keeper()


KEEPER_PID = VAULT_DIR / "keeper.pid"


def keeper_running() -> int | None:
    try:
        pid = int(KEEPER_PID.read_text().strip())
    except Exception:
        return None
    try:
        os.kill(pid, 0)
        return pid
    except OSError:
        KEEPER_PID.unlink(missing_ok=True)
        return None


def launch_keeper(cfg) -> None:
    import subprocess
    script = Path(__file__).parent / "oracle_keeper3.py"
    if not script.exists():
        info_box("Keeper", [render_error(f"oracle_keeper3.py not found at {script}")],
                 color=C.RED)
        return
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logf = open(LOG_DIR / "keeper.log", "ab")
    py = sys.executable or "python3"
    import platform as _platform
    if _platform.system() == "Windows":
        detach_kwargs = {"creationflags": subprocess.DETACHED_PROCESS
                         | subprocess.CREATE_NEW_PROCESS_GROUP,
                         "stdin": subprocess.DEVNULL}
    else:
        detach_kwargs = {"start_new_session": True, "stdin": subprocess.DEVNULL}
    proc = subprocess.Popen([py, str(script)], stdout=logf, stderr=logf,
                            **detach_kwargs)
    KEEPER_PID.write_text(str(proc.pid))
    info_box("Keeper launched", [
        render_ok(f"Oracle keeper started (pid {proc.pid})"), "",
        "It submits prices and heartbeats automatically.",
        f"Log: {LOG_DIR / 'keeper.log'}",
    ], color=C.GREEN)


def _terminate(pid: int) -> None:
    """Terminate a process, cross-platform (Windows: taskkill /F /T kills the
    whole process tree; POSIX: SIGTERM then SIGKILL after a grace period)."""
    import subprocess as _sp
    if platform.system() == "Windows":
        _sp.run(["taskkill", "/PID", str(pid), "/F", "/T"],
                capture_output=True, timeout=15)
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except (ProcessLookupError, OSError):
        return
    for _ in range(10):
        time.sleep(0.2)
        try:
            os.kill(pid, 0)
        except OSError:
            return
    try:
        os.kill(pid, signal.SIGKILL)
    except (ProcessLookupError, OSError):
        pass


def stop_keeper() -> None:
    pid = keeper_running()
    if not pid:
        info_box("Keeper", [render_warn("Keeper is not running.")])
        return
    try:
        _terminate(pid)
        KEEPER_PID.unlink(missing_ok=True)
        info_box("Keeper stopped", [render_ok(f"Stopped pid {pid}.")], color=C.GREEN)
    except OSError as e:
        info_box("Keeper", [render_error(f"Could not stop: {e}")], color=C.RED)


# ---------------------------------------------------------------------------
# Actions (real transactions)
# ---------------------------------------------------------------------------

def _wallet_unreachable_msg(cfg):
    """Return a helpful message when the wallet RPC is unreachable."""
    import platform as _plat
    url = cfg.get("wallet_url") or "(empty)"
    if _plat.system() == "Windows":
        wallet_script = f"bin{os.sep}start-wallet.bat"
        combo_script = f"bin{os.sep}start-wallet-and-keeper.bat"
    else:
        wallet_script = f"bin{os.sep}start-wallet.sh"
        combo_script = f"bin{os.sep}start-wallet-and-keeper.sh"
    return [
        render_error("Wallet RPC is configured but unreachable."),
        "",
        f"  Current URL: {C.CYAN}{url}{C.RESET}",
        "",
        "  Possible fixes:",
        f"  {C.GREEN}1.{C.RESET} Start the wallet: run {C.BOLD}{wallet_script}{C.RESET}",
        f"  {C.GREEN}2.{C.RESET} Or use {C.BOLD}{combo_script}{C.RESET}",
        f"  {C.GREEN}3.{C.RESET} Check the URL in Setup (s) — default port is {C.BOLD}18082{C.RESET}",
        f"  {C.GREEN}4.{C.RESET} Verify with: {C.DIM}curl http://127.0.0.1:18082/json_rpc{C.RESET}",
    ]


def action_registration_flow(cfg, b):
    """Guided registration with a clean explanation of service choice."""
    if not b.has_wallet:
        info_box("Register miner", [
            render_error("No wallet RPC configured."),
            "Run Setup (s) and fill 'Wallet RPC URL', e.g. http://127.0.0.1:18082/json_rpc",
        ], color=C.RED)
        return
    if not b.ping_wallet():
        info_box("Register miner", _wallet_unreachable_msg(cfg), color=C.RED)
        return
    # Check if miner binary is available (warning only, not blocking)
    from onboarding import find_miner_binary
    miner_bin = find_miner_binary()
    if not miner_bin:
        info_box("Miner binary not found", [
            render_warn("xelis_miner binary not found locally."),
            "",
            "You can still register on-chain, but you will need to",
            "download the miner binary to start mining locally.",
            "",
            f"Download from: {C.CYAN}https://github.com/xelis-project/xelis-blockchain/releases{C.RESET}",
            f"Or run with: {C.CYAN}--setup{C.RESET}",
        ], color=C.YELLOW)
        print()
    m = b.my_miner()
    if m and isinstance(m, list) and len(m) >= 15:
        if bool(m[M_ACTIVE]):
            info_box("Already registered", [
                render_ok("This address already has an active miner profile."), "",
                "Use 'Increase stake' or 'Enable service' instead.",
            ], color=C.GREEN)
        else:
            # Show diagnostic info to help the user understand why inactive
            stake = int(m[M_STAKE]) if m[M_STAKE] else 0
            rep = int(m[M_REP]) if m[M_REP] else 0
            slashed = int(m[M_SLASH]) if m[M_SLASH] else 0
            min_stake = b.miner_stake_min() or MIN_STAKE_VLT
            lines = [
                render_warn("This address has a miner profile, but it is inactive."),
                "",
                f"  Current stake: {C.BOLD}{stake / 10**DECIMALS:g} VLT{C.RESET}",
                f"  Minimum required: {C.BOLD}{min_stake / 10**DECIMALS:g} VLT{C.RESET}",
            ]
            if stake < min_stake:
                lines.append(f"  {C.YELLOW}→ Stake is below minimum — use 'Increase miner stake' to reactivate{C.RESET}")
            elif slashed > 0:
                lines.append(f"  {C.YELLOW}→ Slashed: {slashed / 10**DECIMALS:g} VLT — reputation may be too low{C.RESET}")
            elif rep < 1000:
                lines.append(f"  {C.YELLOW}→ Reputation too low ({rep}) — send heartbeats to rebuild{C.RESET}")
            else:
                lines.append(f"  {C.YELLOW}→ Use 'Increase miner stake' or send a heartbeat to reactivate{C.RESET}")
            lines.append("")
            lines.append("If you want to start fresh: deregister from xvault first.")
            info_box("Already registered (inactive)", lines, color=C.YELLOW)
        return

    endpoint = cfg.get("miner_endpoint")
    if not endpoint:
        info_box("Register miner", [
            render_error("No public endpoint configured."),
            "Set your endpoint in Setup (s) — it is advertised on-chain.",
        ], color=C.RED)
        return

    svc = cfg.get("services", "both")
    mask = {"both": SERVICE_ORACLE | SERVICE_CHAT,
            "oracle": SERVICE_ORACLE, "chat": SERVICE_CHAT}.get(svc, 3)

    min_atomic = b.miner_stake_min() or MIN_STAKE_VLT
    show_cursor()
    amt = text_input("VLT stake to deposit (minimum required by contract):",
                     default=f"{min_atomic / 10 ** DECIMALS:g}")
    hide_cursor()
    try:
        stake_atomic = int(float(amt) * 10 ** DECIMALS)
    except ValueError:
        info_box("Invalid amount", [render_error("Please enter a valid number.")],
                 color=C.RED)
        return
    if stake_atomic <= 0:
        info_box("Invalid amount", [render_error("Amount must be greater than zero.")],
                 color=C.RED)
        return
    if not _check_balance(b, b.vlt_asset, stake_atomic):
        return
    # Check XEL balance for transaction fees (need at least 0.1 XEL)
    try:
        xel_bal = b.balance(b.xel_asset)
        if xel_bal is not None and xel_bal < 10_000_000:  # 0.1 XEL in atomic
            info_box("Insufficient XEL", [
                render_error("Not enough XEL for transaction fees."),
                "",
                f"  Available: {b.fmt(xel_bal)} XEL",
                f"  Required: at least 0.1 XEL for gas + fees",
                "",
                f"  {C.DIM}Transaction fees are paid in XEL, not VLT.{C.RESET}",
            ], color=C.RED)
            return
    except Exception:
        pass  # Continue anyway, let the tx fail if no XEL

    # Show full diagnostic before registration
    try:
        xel_bal = b.balance(b.xel_asset)
        vlt_bal = b.balance(b.vlt_asset)
        xusd_bal = b.balance(b.xusd_asset)
        svc_names = []
        if mask & SERVICE_ORACLE: svc_names.append(f"{C.CYAN}Oracle{C.RESET}")
        if mask & SERVICE_CHAT: svc_names.append(f"{C.MAGENTA}Chat{C.RESET}")
        svc_txt = " + ".join(svc_names) if svc_names else "none"
        diag = [
            f"Wallet address: {b.address}",
            f"XEL balance: {b.fmt(xel_bal) if xel_bal is not None else 'unavailable'}",
            f"VLT balance: {b.fmt(vlt_bal) if vlt_bal is not None else 'unavailable'}",
            f"xUSD balance: {b.fmt(xusd_bal) if xusd_bal is not None else 'unavailable'}",
            "",
            f"Services: {svc_txt}",
            f"Endpoint: {C.CYAN}{endpoint}{C.RESET}",
            f"Stake: {C.BOLD}{amt} VLT{C.RESET} ({stake_atomic} atomic)",
        ]
        info_box("Pre-registration check", diag, color=C.CYAN)
    except Exception:
        pass

    svc_names = []
    if mask & SERVICE_ORACLE: svc_names.append("Oracle")
    if mask & SERVICE_CHAT: svc_names.append("Chat")
    svc_txt = " + ".join(svc_names) if svc_names else "none"
    print(f"{C.DIM}  Registering with: services={svc_txt}  endpoint={endpoint}  "
          f"stake={amt} VLT{C.RESET}\n")
    if not confirm(f"Register this address as a miner (services: {svc_txt}, "
                   f"endpoint: {endpoint})?"):
        return
    # Immediate feedback after confirmation
    print(f"\n{C.CYAN}{C.BOLD}  Sending registration transaction...{C.RESET}", flush=True)
    print(f"  {C.DIM}This may take 10-30 seconds depending on network congestion.{C.RESET}\n", flush=True)
    res = b.miner_register(endpoint, mask, stake_atomic)
    if not res or not res.ok:
        info_box("Registration failed", [
            render_error("Transaction could not be sent."),
            "",
            f"  Reason: {res.reason if res else 'no response'}",
            "",
            f"  {C.DIM}Check your wallet balance and network connection.{C.RESET}",
        ], color=C.RED)
        return
    ok, msg = confirm_miner_tx(b, res, "Miner registration", expect_active=True)
    if ok:
        if "ACTIVE" in msg:
            lines = [
                render_ok("Miner profile ACTIVE on-chain ✓"), "",
                f"Tx: {res.tx[:44]}…",
                "Next: enable services & send a heartbeat from the Actions menu.",
            ]
            if not miner_bin:
                lines.extend([
                    "",
                    f"{C.YELLOW}NOTE: To start mining locally, download xelis_miner from:{C.RESET}",
                    f"{C.CYAN}https://github.com/xelis-project/xelis-blockchain/releases{C.RESET}",
                ])
            info_box("Registered", lines, color=C.GREEN)
        else:
            info_box("Registration pending", [
                render_warn("Transaction confirmed, but profile not yet ACTIVE."),
                "",
                f"  {C.DIM}{msg}{C.RESET}",
                "",
                f"Tx: {res.tx[:44]}…",
                "Wait 1-2 minutes and check the dashboard.",
            ], color=C.YELLOW)
    else:
        info_box("Registration rejected", [render_error(f"Reason: {msg}")],
                 color=C.RED)


def action_heartbeat(cfg, b):
    if not b.has_wallet:
        info_box("Heartbeat failed", [
            render_error("No wallet RPC configured."),
            "Run Setup (s) and fill 'Wallet RPC URL', e.g. http://127.0.0.1:18082/json_rpc",
        ], color=C.RED)
        return
    if not b.ping_wallet():
        info_box("Heartbeat failed", _wallet_unreachable_msg(cfg), color=C.RED)
        return
    m = b.my_miner()
    if not m or not isinstance(m, list) or len(m) < 15:
        lookup_addr = (b.wallet.address() if b.wallet else b.address) or "(unknown)"
        info_box("Heartbeat failed", [
            render_error("No miner profile found on-chain for this wallet."),
            f"Lookup key: miner_{short_addr(lookup_addr)}",
            "If you just registered, wait for the block to confirm.",
            "If your wallet address changed, re-import your seed.",
        ], color=C.RED)
        return
    if not bool(m[M_ACTIVE]):
        stake = int(m[M_STAKE]) if m[M_STAKE] else 0
        min_stake = b.miner_stake_min() or MIN_STAKE_VLT
        lines = [
            render_warn("Miner profile is inactive on-chain."),
            "The contract rejects heartbeats from inactive miners.",
            "",
            f"  Current stake: {C.BOLD}{stake / 10**DECIMALS:g} VLT{C.RESET}",
            f"  Minimum required: {C.BOLD}{min_stake / 10**DECIMALS:g} VLT{C.RESET}",
        ]
        if stake < min_stake:
            lines.append(f"  {C.YELLOW}→ Use 'Increase miner stake' to reactivate{C.RESET}")
        else:
            lines.append(f"  {C.YELLOW}→ Stake is sufficient — reputation may be too low{C.RESET}")
        info_box("Heartbeat", lines, color=C.YELLOW)
        return
    res = b.miner_heartbeat()
    ok, msg = confirm_miner_tx(b, res, "Heartbeat")
    if ok:
        info_box("Heartbeat sent", [
            render_ok("Heartbeat confirmed on-chain ✓"), "",
            f"Tx: {res.tx[:40]}…",
        ], color=C.GREEN)
    else:
        info_box("Heartbeat rejected", [render_error(f"Reason: {msg}")],
                 color=C.RED)


def action_increase_stake(cfg, b):
    if not b.has_wallet:
        info_box("Increase stake", [
            render_error("No wallet RPC configured."),
            "Run Setup (s) and fill 'Wallet RPC URL'.",
        ], color=C.RED)
        return
    if not b.ping_wallet():
        info_box("Increase stake", _wallet_unreachable_msg(cfg), color=C.RED)
        return
    m = b.my_miner()
    if not m or not isinstance(m, list) or len(m) < 15:
        lookup_addr = (b.wallet.address() if b.wallet else b.address) or "(unknown)"
        info_box("Increase stake", [
            render_error("No miner profile found on-chain for this wallet."),
            f"Lookup key: miner_{short_addr(lookup_addr)}",
            "If you just registered, wait for the block to confirm.",
            "If your wallet address changed, re-import your seed.",
        ], color=C.RED)
        return
    if not bool(m[M_ACTIVE]):
        stake = int(m[M_STAKE]) if m[M_STAKE] else 0
        min_stake = b.miner_stake_min() or MIN_STAKE_VLT
        info_box("Increase stake", [
            render_warn("Miner profile is inactive on-chain."),
            "Increasing stake can reactivate it if stake was below the minimum.",
            "",
            f"  Current stake: {C.BOLD}{stake / 10**DECIMALS:g} VLT{C.RESET}",
            f"  Minimum required: {C.BOLD}{min_stake / 10**DECIMALS:g} VLT{C.RESET}",
            f"  Amount needed: {C.BOLD}{max(0, min_stake - stake) / 10**DECIMALS:g} VLT{C.RESET}",
        ], color=C.YELLOW)
    amt = text_input("VLT amount to add to miner stake:", default="100")
    try:
        atomic = int(float(amt) * 10 ** DECIMALS)
    except ValueError:
        info_box("Invalid amount", [render_error("Please enter a valid number.")],
                 color=C.RED)
        return
    if atomic <= 0:
        info_box("Invalid amount", [render_error("Amount must be greater than zero.")],
                 color=C.RED)
        return
    if not _check_balance(b, b.vlt_asset, atomic):
        return
    if confirm(f"Stake {amt} VLT more?"):
        res = b.miner_increase_stake(atomic)
        ok, msg = confirm_miner_tx(b, res, "Stake increase", expect_active=True)
        if ok:
            info_box("Stake increased", [render_ok(f"Stake confirmed on-chain ✓"),
                                         f"Tx: {res.tx[:40]}…"],
                     color=C.GREEN)
        else:
            info_box("Failed", [render_error(f"Reason: {msg}")], color=C.RED)


def action_enable_service(cfg, b):
    if not b.has_wallet:
        info_box("Enable service", [
            render_error("No wallet RPC configured."),
            "Run Setup (s) and fill 'Wallet RPC URL'.",
        ], color=C.RED)
        return
    if not b.ping_wallet():
        info_box("Enable service", _wallet_unreachable_msg(cfg), color=C.RED)
        return
    m = b.my_miner()
    if not m or not isinstance(m, list) or len(m) < 15:
        info_box("Enable service", [
            render_error("No miner profile found on-chain for this wallet."),
            f"Lookup key: miner_{short_addr(b.address)}",
            "If you just registered, wait for the block to confirm.",
            "If your wallet address changed, re-import your seed.",
        ], color=C.RED)
        return
    if not bool(m[M_ACTIVE]):
        stake = int(m[M_STAKE]) if m[M_STAKE] else 0
        min_stake = b.miner_stake_min() or MIN_STAKE_VLT
        lines = [
            render_warn("Miner profile is inactive on-chain."),
            "Reactivate it first before enabling services.",
            "",
            f"  Current stake: {C.BOLD}{stake / 10**DECIMALS:g} VLT{C.RESET}",
            f"  Minimum required: {C.BOLD}{min_stake / 10**DECIMALS:g} VLT{C.RESET}",
        ]
        if stake < min_stake:
            lines.append(f"  {C.YELLOW}→ Use 'Increase miner stake' to reactivate{C.RESET}")
        else:
            lines.append(f"  {C.YELLOW}→ Stake is sufficient — send a heartbeat to reactivate{C.RESET}")
        info_box("Enable service", lines, color=C.YELLOW)
        return
    svc = menu("Enable a service", [
        ("Oracle (submit prices, earn VLT)", SERVICE_ORACLE),
        ("Chat relay (anchor messages, earn VLT)", SERVICE_CHAT),
        ("Back", None),
    ])
    if not svc:
        return
    label = "Oracle" if svc == SERVICE_ORACLE else "Chat relay"
    if confirm(f"Enable {label} service?"):
        res = b.miner_enable_service(svc)
        ok, msg = confirm_miner_tx(b, res, f"Enable {label}")
        if ok:
            info_box("Service enabled", [render_ok(f"{label} on ✓"),
                                         f"Tx: {res.tx[:40]}…"],
                     color=C.GREEN)
        else:
            info_box("Failed", [render_error(f"Reason: {msg}")], color=C.RED)


def action_update_endpoint(cfg, b):
    """Update the miner's endpoint on-chain by deregistering and re-registering.

    WARNING: This will lose the miner's reputation and history. The stake is
    refunded, then must be re-deposited. Only use this when absolutely necessary
    (e.g. tunnel URL changed).
    """
    if not b.has_wallet:
        info_box("Update endpoint", [
            render_error("No wallet RPC configured."),
            "Run Setup (s) and fill 'Wallet RPC URL'.",
        ], color=C.RED)
        return
    if not b.ping_wallet():
        info_box("Update endpoint", _wallet_unreachable_msg(cfg), color=C.RED)
        return
    m = b.my_miner()
    if not m or not isinstance(m, list) or len(m) < 15:
        info_box("Update endpoint", [
            render_error("No miner profile found on-chain for this wallet."),
            "You must register first before updating the endpoint.",
        ], color=C.RED)
        return

    # Get current endpoint and stake
    current_endpoint = str(m[M_ENDPOINT]) if m[M_ENDPOINT] else "(unknown)"
    stake = int(m[M_STAKE]) if m[M_STAKE] else 0
    mask = int(m[M_MASK]) if m[M_MASK] else 0

    # Show current state
    info_box("Current endpoint", [
        f"  Endpoint: {C.CYAN}{current_endpoint}{C.RESET}",
        f"  Stake: {C.BOLD}{stake / 10**DECIMALS:g} VLT{C.RESET}",
        f"  Services mask: {mask}",
    ], color=C.CYAN)

    # Warn about consequences
    warn_lines = [
        render_warn("WARNING: This operation will:"),
        "",
        f"  {C.RED}• Deregister your miner (lose reputation & history){C.RESET}",
        f"  {C.YELLOW}• Refund your stake ({stake / 10**DECIMALS:g} VLT){C.RESET}",
        f"  {C.YELLOW}• Require re-registration with new endpoint{C.RESET}",
        f"  {C.YELLOW}• Require re-deposit of stake{C.RESET}",
        "",
        "This is ONLY necessary if your endpoint URL has changed",
        "(e.g. trycloudflare.com tunnel restarted with new URL).",
    ]
    info_box("Update endpoint — consequences", warn_lines, color=C.YELLOW)

    if not confirm("Proceed with endpoint update? This cannot be undone."):
        return

    # Step 1: Deregister
    print(f"\n{C.CYAN}{C.BOLD}  Step 1/2: Deregistering miner...{C.RESET}", flush=True)
    res = b.miner_deregister()
    ok, msg = confirm_miner_tx(b, res, "Miner deregistration")
    if not ok:
        info_box("Deregistration failed", [render_error(f"Reason: {msg}")], color=C.RED)
        return
    print(f"  {C.GREEN}✓ Miner deregistered. Stake refunded.{C.RESET}", flush=True)

    # Step 2: Re-register with new endpoint
    print(f"\n{C.CYAN}{C.BOLD}  Step 2/2: Re-registering with new endpoint...{C.RESET}", flush=True)
    show_cursor()
    new_endpoint = text_input("New endpoint URL:", default=current_endpoint)
    hide_cursor()
    if not new_endpoint or new_endpoint == current_endpoint:
        info_box("Cancelled", [render_warn("Endpoint unchanged. No re-registration needed.")],
                 color=C.YELLOW)
        return

    # Check XEL for fees
    try:
        xel_bal = b.balance(b.xel_asset)
        if xel_bal is not None and xel_bal < 10_000_000:
            info_box("Insufficient XEL", [
                render_error("Not enough XEL for transaction fees."),
                f"  Available: {b.fmt(xel_bal)} XEL",
                f"  Required: at least 0.1 XEL",
            ], color=C.RED)
            return
    except Exception:
        pass

    # Check VLT balance for re-stake
    if not _check_balance(b, b.vlt_asset, stake):
        return

    if not confirm(f"Re-register with endpoint: {new_endpoint}?"):
        return

    print(f"\n{C.CYAN}{C.BOLD}  Sending re-registration transaction...{C.RESET}", flush=True)
    res = b.miner_register(new_endpoint, mask, stake)
    if not res or not res.ok:
        info_box("Re-registration failed", [
            render_error("Transaction could not be sent."),
            f"  Reason: {res.reason if res else 'no response'}",
        ], color=C.RED)
        return

    ok, msg = confirm_miner_tx(b, res, "Miner re-registration", expect_active=True)
    if ok:
        if "ACTIVE" in msg:
            info_box("Endpoint updated", [
                render_ok("Miner re-registered with new endpoint ✓"),
                "",
                f"  New endpoint: {C.CYAN}{new_endpoint}{C.RESET}",
                f"  Tx: {res.tx[:44]}…",
            ], color=C.GREEN)
        else:
            info_box("Endpoint update pending", [
                render_warn("Transaction confirmed, but profile not yet ACTIVE."),
                "",
                f"  New endpoint: {C.CYAN}{new_endpoint}{C.RESET}",
                f"  {C.DIM}{msg}{C.RESET}",
            ], color=C.YELLOW)
    else:
        info_box("Re-registration failed", [render_error(f"Reason: {msg}")], color=C.RED)


def action_menu(cfg, b):
    from onboarding import miner_running, start_miner, stop_miner
    running = miner_running()
    opts = [
        ("Register as miner (guided)", "reg"),
        ("Update endpoint (deregister + re-register)", "update_ep"),
        ("Send heartbeat now", "hb"),
        ("Increase miner stake", "stake"),
        ("Enable a service", "svc"),
        ("Diagnostic: wallet / balances / assets", "diag"),
        ("MinerDelegation: delegate / profile", "delegation"),
        ("Expose relayer publicly (tunnel + endpoint update)", "public"),
        ("Toggle tunnel watchdog (auto-restart + auto-update)", "watchdog"),
        ("Price provider handbook / keeper", "prov"),
    ]
    if running:
        opts.append(("Stop built-in PoW miner", "stopminer"))
    else:
        opts.append(("Start built-in PoW miner", "startminer"))
    opts.append(("Back", None))
    choice = menu("Miner actions", opts)
    if choice == "reg":
        action_registration_flow(cfg, b)
    elif choice == "update_ep":
        action_update_endpoint(cfg, b)
    elif choice == "hb":
        action_heartbeat(cfg, b)
    elif choice == "stake":
        action_increase_stake(cfg, b)
    elif choice == "svc":
        action_enable_service(cfg, b)
    elif choice == "diag":
        _action_diagnostic(cfg, b)
    elif choice == "delegation":
        _action_delegation(cfg, b)
    elif choice == "public":
        _action_ensure_public(cfg, b)
    elif choice == "watchdog":
        _action_toggle_watchdog(cfg)
    elif choice == "prov":
        provider_guide(cfg)
    elif choice == "startminer":
        ok, msg = start_miner(cfg)
        info_box("PoW miner", [render_ok(msg) if ok else render_error(msg)],
                 color=C.GREEN if ok else C.RED)
    elif choice == "stopminer":
        ok, msg = stop_miner()
        info_box("PoW miner", [render_ok(msg) if ok else render_error(msg)],
                 color=C.GREEN if ok else C.RED)


def _action_diagnostic(cfg, b):
    lines = []
    lines.append(f"Wallet address : {b.address}")
    lines.append(f"Wallet URL     : {cfg.get('wallet_url') or '(not set)'}")
    lines.append(f"Wallet user    : {cfg.get('wallet_user') or '(not set)'}")
    lines.append(f"Wallet pass    : {'*' * len(cfg.get('wallet_pass') or '') if cfg.get('wallet_pass') else '(not set)'}")
    lines.append(f"VLT asset      : {b.vlt_asset}")
    lines.append(f"xUSD asset     : {b.xusd_asset}")
    lines.append(f"Wallet reachable: {b.ping_wallet()}")
    try:
        xel = b.balance(b.xel_asset)
        vlt = b.balance(b.vlt_asset)
        xusd = b.balance(b.xusd_asset)
        lines.append(f"XEL balance: {b.fmt(xel) if xel is not None else 'unavailable'}")
        lines.append(f"VLT balance: {b.fmt(vlt) if vlt is not None else 'unavailable'}")
        lines.append(f"xUSD balance: {b.fmt(xusd) if xusd is not None else 'unavailable'}")
    except Exception as e:
        lines.append(f"Balance error: {e}")
    try:
        m = b.my_miner()
        lines.append(f"Miner profile: {'found' if m else 'not found'}")
        if m and isinstance(m, list) and len(m) >= 15:
            lines.append(f"  active: {bool(m[14])}")
            lines.append(f"  stake: {m[3]}")
            lines.append(f"  reputation: {m[9]}")
    except Exception as e:
        lines.append(f"Miner lookup error: {e}")
    info_box("Diagnostic", lines, color=C.CYAN)


def _action_ensure_public(cfg, b):
    """Ensure the relayer daemon + cloudflare tunnel are running, then sync
    the public URL on-chain via chat_update_endpoint."""
    from onboarding import start_relayer_public
    info_box("Expose relayer publicly", [
        "Starting relayer daemon + Cloudflare tunnel...",
        "This may take up to 30 seconds.",
    ], color=C.CYAN)
    ok, msg = start_relayer_public(cfg)
    if ok:
        info_box("Relayer public", [render_ok(msg)], color=C.GREEN)
    else:
        info_box("Relayer public", [render_error(msg)], color=C.RED)


def _action_delegation(cfg, b):
    """MinerDelegation: delegate, manage profile, claim rewards."""
    md = b.C("MinerDelegation")
    if not md:
        info_box("MinerDelegation", [
            render_error("MinerDelegation contract not configured."),
            "Run the setup wizard or check Settings → Contract addresses.",
        ], color=C.RED)
        return

    while True:
        clear()
        print(BANNER)
        print(f"\n{C.CYAN}{C.BOLD}  🤝 MINER DELEGATION{C.RESET}")
        print(f"{C.GRAY}  {'─' * 56}{C.RESET}\n")

        total_del = b.delegation_total_delegated()
        miners = b.delegation_miner_count()
        print(f"  Total delegated : {C.YELLOW}{b.fmt(total_del)}{C.RESET} VLT")
        print(f"  Registered miners: {miners}\n")

        choice = menu("Delegation Menu", [
            ("📋  My delegation", "my"),
            ("🏆  Delegate to a miner", "delegate"),
            ("⏳  Undelegate (queue)", "undelegate"),
            ("✅  Execute undelegate", "exec_undel"),
            ("💎  Claim delegator rewards", "claim_del"),
            ("🔑  Register miner profile", "reg"),
            ("✏️   Update miner profile", "update"),
            ("💰  Claim miner rewards", "claim_miner"),
            ("Back", None),
        ])

        if choice is None:
            break

        if choice == "my":
            info = b.delegation_my_delegation()
            if not info:
                info_box("My delegation", [
                    render_warn("No active delegation found for this wallet."),
                ], color=C.YELLOW)
            else:
                profile = b.delegation_get_profile(info["miner"])
                lines = [
                    f"Miner      : {info['miner'][:12]}...{info['miner'][-8:]}",
                    f"Amount     : {C.YELLOW}{b.fmt(info['amount'])}{C.RESET} VLT",
                    f"Delegated  : topo {info['delegated_at']}",
                    f"Auto-comp  : {'Yes' if info['auto_compound'] else 'No'}",
                ]
                if profile:
                    lines.append(f"Miner name : {profile['name']}")
                    lines.append(f"Commission : {profile['commission_bps'] / 100:.1f}%")
                info_box("My delegation", lines, color=C.CYAN)

        elif choice == "delegate":
            miner_addr = text_input("  Miner address: ")
            if not miner_addr or len(miner_addr) < 10:
                continue
            amount_str = text_input("  VLT amount to delegate (min 10 VLT): ")
            try:
                amount_vlt = float(amount_str)
                if amount_vlt < 10:
                    info_box("Delegation", [render_error("Minimum delegation is 10 VLT.")], color=C.RED)
                    continue
            except ValueError:
                continue
            auto = menu("Auto-compound?", [
                ("Yes — reinvest rewards", "yes"),
                ("No — claim manually", "no"),
                ("Cancel", None),
            ])
            if auto is None:
                continue
            amount_atomic = int(amount_vlt * 10**8)
            if not _check_balance(b, b.vlt_asset, amount_atomic):
                continue
            print(f"\n  Delegating {C.YELLOW}{amount_vlt} VLT{C.RESET} to {miner_addr[:12]}...{miner_addr[-8:]}")
            if confirm("  Confirm?"):
                res = b.delegation_delegate(miner_addr, amount_atomic, auto == "yes")
                if res.ok:
                    info_box("Delegated", [render_ok(f"Tx: {res.tx[:40]}…")], color=C.GREEN)
                else:
                    info_box("Failed", [render_error(f"Reason: {res.reason}")], color=C.RED)

        elif choice == "undelegate":
            info = b.delegation_my_delegation()
            if not info:
                info_box("Undelegate", [render_warn("No active delegation.")], color=C.YELLOW)
                continue
            amount_str = text_input(f"  Amount to undelegate (max {b.fmt(info['amount'])} VLT): ")
            try:
                amount_vlt = float(amount_str)
                if amount_vlt <= 0:
                    raise ValueError
            except ValueError:
                continue
            amount_atomic = int(amount_vlt * 10**8)
            if amount_atomic > info["amount"]:
                info_box("Undelegate", [render_error("Amount exceeds delegated stake.")], color=C.RED)
                continue
            print(f"\n  Undelegating {C.YELLOW}{amount_vlt} VLT{C.RESET}")
            if confirm("  Confirm? (7-day delay before execution)"):
                res = b.delegation_undelegate(amount_atomic)
                if res.ok:
                    info_box("Undelegated", [render_ok(f"Request queued. Tx: {res.tx[:40]}…")], color=C.GREEN)
                else:
                    info_box("Failed", [render_error(f"Reason: {res.reason}")], color=C.RED)

        elif choice == "exec_undel":
            print(f"\n  {C.DIM}Finalize a pending undelegate request (after 7-day delay).{C.RESET}")
            if confirm("  Execute undelegate?"):
                res = b.delegation_execute_undelegate()
                if res.ok:
                    info_box("Undelegate executed", [render_ok(f"Tx: {res.tx[:40]}…")], color=C.GREEN)
                else:
                    info_box("Failed", [render_error(f"Reason: {res.reason}")], color=C.RED)

        elif choice == "claim_del":
            addr = getattr(b, "address", None)
            if not addr:
                info_box("Claim", [render_error("No wallet address configured.")], color=C.RED)
                continue
            pending = b.delegation_delegator_pending(addr)
            if pending > 0:
                print(f"\n  Pending rewards: {C.GREEN}{b.fmt(pending)}{C.RESET} VLT")
            else:
                info_box("Claim", [render_warn("No pending delegator rewards.")], color=C.YELLOW)
                continue
            if confirm("  Claim rewards?"):
                res = b.delegation_claim_delegator_rewards()
                if res.ok:
                    info_box("Claimed", [render_ok(f"Tx: {res.tx[:40]}…")], color=C.GREEN)
                else:
                    info_box("Failed", [render_error(f"Reason: {res.reason}")], color=C.RED)

        elif choice == "reg":
            name = text_input("  Miner name (3-32 chars): ")
            if not name or len(name) < 3:
                info_box("Register", [render_error("Name too short.")], color=C.RED)
                continue
            description = text_input("  Description (optional): ") or ""
            commission_str = text_input("  Commission % (0-20, e.g. 10): ")
            try:
                commission_pct = float(commission_str)
                if commission_pct < 0 or commission_pct > 20:
                    raise ValueError
                commission_bps = int(commission_pct * 100)
            except ValueError:
                info_box("Register", [render_error("Invalid commission (0-20%).")], color=C.RED)
                continue
            print(f"\n  Name: {name}")
            print(f"  Commission: {commission_pct:.1f}%")
            if confirm("  Register profile?"):
                res = b.delegation_register_profile(name, description, commission_bps)
                if res.ok:
                    info_box("Registered", [render_ok(f"Profile set. Tx: {res.tx[:40]}…")], color=C.GREEN)
                else:
                    info_box("Failed", [render_error(f"Reason: {res.reason}")], color=C.RED)

        elif choice == "update":
            name = text_input("  New name: ")
            description = text_input("  New description: ")
            commission_str = text_input("  New commission % (0-20): ")
            try:
                commission_bps = int(float(commission_str) * 100)
            except ValueError:
                continue
            if confirm("  Update profile?"):
                res = b.delegation_update_profile(name, description, commission_bps)
                if res.ok:
                    info_box("Updated", [render_ok(f"Tx: {res.tx[:40]}…")], color=C.GREEN)
                else:
                    info_box("Failed", [render_error(f"Reason: {res.reason}")], color=C.RED)

        elif choice == "claim_miner":
            addr = getattr(b, "address", None)
            if not addr:
                info_box("Claim", [render_error("No wallet address configured.")], color=C.RED)
                continue
            pending = b.delegation_miner_pending(addr)
            if pending > 0:
                print(f"\n  Pending miner rewards: {C.GREEN}{b.fmt(pending)}{C.RESET} VLT")
            else:
                info_box("Claim", [render_warn("No pending miner rewards.")], color=C.YELLOW)
                continue
            if confirm("  Claim miner rewards?"):
                res = b.delegation_claim_miner_rewards()
                if res.ok:
                    info_box("Claimed", [render_ok(f"Tx: {res.tx[:40]}…")], color=C.GREEN)
                else:
                    info_box("Failed", [render_error(f"Reason: {res.reason}")], color=C.RED)


_watchdog_state = {"enabled": False, "thread": None, "last": {}}


def _watchdog_loop(cfg, poll_interval: float = 60.0):
    """Background watchdog: ensure tunnel + relayer stay alive, update on-chain
    if public URL changes, and report health."""
    from onboarding import watchdog_tunnel
    _watchdog_state["last"] = {"ok": False, "message": "watchdog starting"}
    while _watchdog_state["enabled"]:
        try:
            status = watchdog_tunnel(cfg, poll_interval=poll_interval)
            _watchdog_state["last"] = status
        except Exception as e:
            _watchdog_state["last"] = {"ok": False, "message": f"watchdog error: {e}"}


def _action_toggle_watchdog(cfg):
    """Start/stop the tunnel watchdog."""
    if _watchdog_state["enabled"]:
        _watchdog_state["enabled"] = False
        if _watchdog_state["thread"] and _watchdog_state["thread"].is_alive():
            _watchdog_state["thread"].join(timeout=2)
        _watchdog_state["thread"] = None
        info_box("Watchdog", [render_warn("Tunnel watchdog stopped.")], color=C.YELLOW)
        return
    _watchdog_state["enabled"] = True
    t = threading.Thread(target=_watchdog_loop, args=(cfg, 60.0), daemon=True)
    t.start()
    _watchdog_state["thread"] = t
    info_box("Watchdog", [
        render_ok("Tunnel watchdog started."),
        "Checks every 60s: restarts dead tunnel, auto-updates endpoint on-chain.",
    ], color=C.GREEN)


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def main():
    import argparse
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
    parser = argparse.ArgumentParser(description="XELIS Vault — Miner / Oracle console")
    parser.add_argument("--rpc", help="Daemon RPC URL")
    parser.add_argument("--wallet-url", help="Wallet RPC URL")
    parser.add_argument("--services", choices=["oracle", "chat", "both"])
    parser.add_argument("--miner", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--setup", action="store_true")
    parser.add_argument("--run-keeper", action="store_true",
                        help="Run the oracle keeper in foreground (for batch/shell scripts)")
    parser.add_argument("--set-address", help=argparse.SUPPRESS)
    parser.add_argument("--start-mining", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--import-seed", help=argparse.SUPPRESS)
    parser.add_argument("--register", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--endpoint", help=argparse.SUPPRESS)
    parser.add_argument("--stake", type=float, help=argparse.SUPPRESS)
    args = parser.parse_args()

    cfg = Config()
    if args.rpc:
        cfg.data["rpc_url"] = args.rpc
    if args.wallet_url:
        cfg.data["wallet_url"] = args.wallet_url
    if args.services:
        cfg.data["services"] = args.services

    # Non-interactive: import an existing wallet seed into a local xelis_wallet.
    if args.import_seed:
        ok = bootstrap_wallet_with_seed(cfg, args.import_seed.strip())
        print("Import termine." if ok else "Import impossible.")
        return

    # Non-interactive: register the configured wallet as a miner.
    if args.register:
        endpoint = args.endpoint or cfg.get("miner_endpoint")
        if not endpoint:
            print("ERREUR: --endpoint (URL publique du service) requis pour "
                  "l'enregistrement.")
            return
        register_miner_cli(cfg, endpoint, args.services, args.stake or 0)
        return

    # Non-interactive: just register the miner address in the config.
    if args.set_address:
        cfg.data["miner_address"] = args.set_address
        cfg.save()
        print("Adresse mineur enregistree :", args.set_address)
        return

    # Non-interactive: launch the built-in PoW miner against your address.
    if args.miner or args.start_mining:
        from onboarding import ensure_miner_configured, start_miner
        if not cfg.get("miner_address"):
            print("ERREUR: aucune adresse mineur configuree. "
                  "Utilisez --set-address <xet:...> ou lancez --setup.")
            return
        ensure_miner_configured(cfg)
        ok, msg = start_miner(cfg)
        print(("OK: " if ok else "ERREUR: ") + msg)
        if ok:
            from pathlib import Path
            log_path = Path.home() / ".xelis-vault" / "logs" / "miner.log"
            print(f"Journal du mineur : {log_path}")
        time.sleep(2)
        return

    if args.setup:
        interactive_setup(cfg)
        return

    # Non-interactive: run the oracle keeper in foreground.
    # The batch/shell scripts background this process themselves.
    if args.run_keeper:
        keeper_script = Path(__file__).parent / "oracle_keeper3.py"
        if not keeper_script.exists():
            print(f"ERROR: oracle_keeper3.py not found at {keeper_script}")
            return
        print(f"Starting oracle keeper (foreground mode)...")
        print(f"  Keeper script: {keeper_script}")
        print(f"  Press Ctrl+C to stop.")
        print()
        try:
            # Run in foreground so the batch/shell script can manage the process
            import subprocess
            py = sys.executable or "python3"
            cmd = [py, str(keeper_script)]
            # Pass wallet-url if configured, so keeper can use it as fallback
            wallet_url = cfg.get("wallet_url")
            if wallet_url:
                cmd += ["--wallet-url", wallet_url]
            proc = subprocess.run(cmd)
        except KeyboardInterrupt:
            print("\nKeeper stopped.")
        return

    print(f"{C.DIM}  Loading dashboard...{C.RESET}", flush=True)
    hint = _fallback_rpc_if_needed(cfg)
    mode = check_contracts(cfg)

    auto_refresh = True
    running = [True]
    b = Backend(cfg.data)

    def on_signal(sig, frame):
        running[0] = False

    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGTERM, on_signal)
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, on_signal)

    hide_cursor()
    try:
        while running[0]:
            live = fetch_live(cfg, b) if mode != "demo" or b.topo() else \
                {"connected": False, "topo": 0, "balances": {}, "miner": {},
                 "stats": {}, "feeds": [], "relayer": None}
            render_dashboard(cfg, live, hint)
            hint = ""
            key = read_key_timeout(REFRESH_INTERVAL if auto_refresh else 999)
            if key is None:
                if auto_refresh:
                    hint = f"{C.DIM}Auto-refreshed at {datetime.now().strftime('%H:%M:%S')}{C.RESET}"
            elif key in ("Q", "CTRL_C", "CTRL_D"):
                break
            elif key == "s":
                show_cursor()
                interactive_setup(cfg)
                b = Backend(cfg.data)
                hide_cursor()
            elif key == "R":
                show_cursor()
                if confirm("Reset configuration to defaults? This will clear all settings."):
                    cfg.reset()
                    b = Backend(cfg.data)
                    info_box("Reset", [render_ok("Configuration reset to defaults.")], color=C.GREEN)
                hide_cursor()
            elif key == "r":
                hint = f"{C.GREEN}Manual refresh at {datetime.now().strftime('%H:%M:%S')}{C.RESET}"
            elif key == "a":
                auto_refresh = not auto_refresh
                hint = f"Auto-refresh: {'ON' if auto_refresh else 'OFF'}"
            elif key == "m":
                show_cursor()
                action_menu(cfg, b)
                hide_cursor()
            elif key == "p":
                show_cursor()
                provider_guide(cfg)
                hide_cursor()
            elif key == "h":
                show_cursor()
                action_heartbeat(cfg, b)
                time.sleep(1.2)
                hide_cursor()
    finally:
        show_cursor()
        clear()
        print(f"\n{C.CYAN}{C.BOLD}  Shutting down... Goodbye!{C.RESET}\n")


if __name__ == "__main__":
    main()
