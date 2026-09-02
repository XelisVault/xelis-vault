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
from datetime import datetime
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent))
from config import Config
from tui import (
    C, BANNER, clear, hide_cursor, show_cursor, read_key, read_key_timeout,
    menu, text_input, confirm, info_box, render_panel, render_metrics,
    render_badge, render_bar, render_ok, render_warn, render_error,
    render_status,
)
from cli_backend import Backend, DECIMALS, ZERO_HASH
from protocol import MIN_STAKE_VLT

VAULT_DIR = Path.home() / ".xelis-vault"
LOG_DIR = VAULT_DIR / "logs"

REFRESH_INTERVAL = 5

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
    try:
        avail = b.balance(asset)
    except Exception as e:
        avail = None
        balance_error = str(e)
    if avail is None and b.wallet:
        try:
            avail = b.wallet.balance(asset)
        except Exception as e2:
            balance_error = str(e2)
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


def _fallback_rpc_if_needed(cfg) -> str:
    """If the configured daemon RPC is unreachable, switch to the public
    testnet node and persist the new URL so the next launch reuses it.
    Returns a hint string if a fallback occurred, else empty string."""
    url = cfg.data.get("rpc_url", "")
    if not url:
        return ""
    try:
        r = requests.post(url, json={"jsonrpc": "2.0", "id": 1,
                                     "method": "get_topoheight", "params": {}},
                          timeout=3)
        if r.status_code == 200:
            return ""
    except Exception:
        pass
    try:
        r2 = requests.post(PUBLIC_TESTNET_RPC,
                           json={"jsonrpc": "2.0", "id": 1,
                                 "method": "get_topoheight", "params": {}},
                           timeout=5)
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
    if res.ok:
        print("OK: transaction submitted -> " + res.tx[:44] + "...")
        print("Check the testnet explorer for confirmation.")
    else:
        print("FAILED: " + res.reason)


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

def fetch_live(b: Backend) -> dict:
    live = {"connected": False, "topo": 0, "balances": {},
            "miner": {}, "stats": {}, "feeds": [], "relayer": None,
            "error": "", "diag": {}}
    try:
        topo = b.topo()
    except Exception as e:
        live["error"] = f"daemon unreachable: {e}"
        return live
    if not topo:
        return live
    live["connected"] = True
    live["topo"] = topo
    try:
        live["balances"] = b.balances() or {}
    except Exception as e:
        live["error"] = f"balances failed: {e}"
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

    try:
        m = b.my_miner()
        if isinstance(m, list) and len(m) >= 15:
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
    except Exception as e:
        live["error"] = f"my_miner failed: {e}"

    try:
        live["stats"] = b.miner_stats() or {}
    except Exception as e:
        live["error"] = f"miner_stats failed: {e}"
    try:
        p = b.price()
        if p:
            price_raw, feed_topo, stale = p
            live["feeds"].append({"name": "XEL/USD", "price_raw": price_raw,
                                  "age": max(0, topo - feed_topo), "stale": stale})
    except Exception:
        pass
    try:
        from onboarding import relayer_tunnel_status
        live["tunnel"] = relayer_tunnel_status(cfg)
    except Exception:
        live["tunnel"] = None
    if getattr(b, "has_wallet", False):
        try:
            live["relayer"] = b.chat_relayer_status(b.address)
        except Exception:
            live["relayer"] = None
    return live


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

def render_dashboard(cfg, live, hint=""):
    clear()
    now = datetime.now().strftime("%H:%M:%S")
    addr = cfg.get("miner_address") or cfg.get("wallet_url") and "(wallet set)" or "(not set)"

    print(f"{C.CYAN}{C.BOLD}  XELIS VAULT {C.RESET}{render_badge('MINER / ORACLE OPERATOR', C.MAGENTA)}")
    print(f"{C.DIM}  {platform.system()}/{platform.machine()}  {C.GRAY}·{C.RESET}  {render_badge('TESTNET', C.YELLOW)}")
    print(f"{C.GRAY}{'─' * 60}{C.RESET}")

    conn = render_ok("CONNECTED") if live["connected"] else \
        render_error("OFFLINE — is the daemon running?")
    topo = f"{live['topo']:,}" if live["connected"] else "-"
    print(f"  {C.DIM}{now}{C.RESET}   {C.DIM}Topoheight:{C.RESET} {C.BOLD}{topo}{C.RESET}   {conn}")
    print(f"  {C.DIM}Operator:{C.RESET} {addr}")
    if live.get("error"):
        print(f"  {C.RED}{C.BOLD}  ! {live['error']}{C.RESET}")

    # Show diagnostic info
    diag = live.get("diag", {})
    if diag:
        print()
        print(f"  {C.DIM}DIAGNOSTIC:{C.RESET}")
        print(f"    Wallet address: {diag.get('address', '(unknown)')}")
        print(f"    Wallet URL: {diag.get('wallet_url', '(not set)')}")
        print(f"    VLT asset: {diag.get('vlt_asset', '(not loaded)')[:32]}...")
        print(f"    xUSD asset: {diag.get('xusd_asset', '(not loaded)')[:32]}...")
        print(f"    Wallet reachable: {diag.get('has_wallet', False)}")

    # ── Miner status ──
    m = live.get("miner") or {}
    if m:
        active = m.get("active", False)
        status = render_ok("REGISTERED") if active else render_warn("INACTIVE")
        rep = m.get("reputation", 3000)
        tier = tier_name(rep)
        tcolor = tier_color(tier)
        mask = m.get("mask", 0)
        hb = m.get("hb_topo", 0)
        if hb and live["connected"]:
            age = max(0, live["topo"] - hb)
            hb_txt = (render_ok(f"{age} blk ago") if age < 1000
                      else render_warn(f"{age} blk ago"))
        else:
            hb_txt = f"{C.DIM}never{C.RESET}"
        m_lines = [
            f"  {status}   {render_badge(f'Reputation {rep} · {tier}', tcolor)}",
            render_metrics([
                ("Stake", bfmt(m.get("stake"), "VLT")),
                ("Rewards", f"{C.GREEN}{bfmt(m.get('rewards'), 'VLT')}{C.RESET}"),
            ], width=54),
            render_metrics([
                ("Services", svc_badges(mask)),
                ("Last heartbeat", hb_txt),
            ], width=54),
            f"  {C.DIM}Submissions:{C.RESET} {m.get('valid_submissions', 0)} valid / "
            f"{m.get('total_submissions', 0)} total   "
            f"{C.DIM}Anchors:{C.RESET} {m.get('anchors', 0)}   "
            f"{C.DIM}Slashed:{C.RESET} {C.RED}{bfmt(m.get('slashed'), 'VLT')}{C.RESET}",
            f"  {C.DIM}Endpoint:{C.RESET} {m.get('endpoint') or '—'}",
            f"  {C.DIM}Reputation:{C.RESET} {tier_bar(rep)} {rep}/10000",
        ]
        print()
        print(render_panel("  MINER  STATUS", m_lines, border_color=C.CYAN, width=58))
    else:
        print()
        print(render_panel("  MINER  STATUS", [
            render_warn("Not registered"),
            f"{C.DIM}This address has no miner profile on-chain yet.",
            f"{C.DIM}Press {C.BOLD}m{C.RESET}{C.DIM} → Register to start earning VLT.",
        ], border_color=C.CYAN, width=58))

    # ── Wallet balances ──
    bal = live.get("balances") or {}
    b_lines = []
    for sym in ("XEL", "VLT", "xUSD"):
        v = bal.get(sym)
        b_lines.append(f"  {C.BOLD}{sym:<5}{C.RESET}  {bfmt(v)}")
    print()
    print(render_panel("  WALLET  BALANCE", b_lines, border_color=C.GREEN, width=28))

    # ── Protocol stats ──
    stats = live.get("stats") or {}
    s_lines = []
    if stats.get("total_staked") is not None:
        s_lines.append(f"  Total staked:  {C.BOLD}{bfmt(stats['total_staked'], 'VLT')}{C.RESET}")
    if stats.get("budget") is not None and stats.get("distributed") is not None:
        pct = stats["distributed"] * 100 // stats["budget"]
        s_lines += [
            f"  Budget spent:  {pct}%",
            f"                 {render_bar(pct / 100, 24)}",
        ]
    if stats.get("min_stake") is not None:
        s_lines.append(f"  Min stake:     {bfmt(stats['min_stake'], 'VLT')}")
    if stats.get("budget") is not None:
        s_lines.append(f"  Reward budget: {C.BOLD}{bfmt(stats['budget'], 'VLT')}{C.RESET}")
    if not s_lines:
        s_lines.append(f"  {C.DIM}(miner contract not reachable){C.RESET}")
    print()
    print(render_panel("  PROTOCOL  STATS", s_lines, border_color=C.BLUE, width=32))

    # ── Price feeds ──
    f_lines = []
    feeds = live.get("feeds") or []
    if feeds:
        for f in feeds[:6]:
            c = C.RED if f["stale"] else C.GREEN
            icon = "●" if f["stale"] else "●"
            price = f["price_raw"] / 10 ** DECIMALS
            f_lines.append(
                f"  {c}{icon}{C.RESET} ${price:>9,.4f}  {f['name']:<9}"
                f"  {C.DIM}age {f['age']} blk{C.RESET}")
    else:
        f_lines.append(f"  {C.DIM}(no oracle data yet){C.RESET}")
    print()
    print(render_panel("  PRICE  FEEDS", f_lines, border_color=C.YELLOW, width=40))

    # ── Relayer status ──
    rl = live.get("relayer")
    if rl:
        r_lines = []
        ok = rl.get("active")
        r_lines.append(f"  {render_status(bool(ok), 'Relayer')}")
        if rl.get("bond"):
            r_lines.append(f"  Bond: {C.BOLD}{bfmt(rl['bond'], 'VLT')}{C.RESET}")
        reg = rl.get("registered")
        if reg:
            r_lines.append(f"  Endpoint: {C.CYAN}{reg.get('endpoint', '')}{C.RESET}")
            r_lines.append(f"  {C.DIM}Free: {reg.get('free_daily_limit', '')} msg/day · "
                           f"{reg.get('free_wallet_slots', '')} slots{C.RESET}")
        print()
        print(render_panel("  RELAYER  (VaultChat)", r_lines, border_color=C.MAGENTA, width=48))

    # ── Tunnel status ──
    tunnel = live.get("tunnel")
    if tunnel:
        t_lines = []
        t_url = tunnel.get("url") or ""
        if t_url:
            t_lines.append(f"  Public URL: {C.CYAN}{t_url}{C.RESET}")
        else:
            t_lines.append(f"  {render_warn('No tunnel running')}")
        tpid = tunnel.get("tunnel_pid")
        if tpid:
            t_lines.append(f"  Tunnel PID: {tpid}")
        rpid = tunnel.get("relayer_pid")
        if rpid:
            t_lines.append(f"  Relayer PID: {rpid}")
        local = tunnel.get("local_endpoint") or ""
        if local:
            t_lines.append(f"  Local endpoint: {local}")
        wd = _watchdog_state.get("last") or {}
        if wd:
            ok = wd.get("ok")
            msg = wd.get("message") or ""
            endpoint = wd.get("endpoint")
            healthy = wd.get("healthy")
            if _watchdog_state.get("enabled"):
                t_lines.append(f"  Watchdog: {render_ok('ON')} {msg}")
            else:
                t_lines.append(f"  Watchdog: {render_warn('OFF')}")
            if endpoint:
                t_lines.append(f"  Endpoint on-chain: {endpoint}")
            if healthy is not None:
                t_lines.append(f"  Public health: {render_ok('OK') if healthy else render_warn('UNREACHABLE')}")
        print()
        print(render_panel("  PUBLIC  TUNNEL", t_lines, border_color=C.BLUE, width=52))

    print()
    print(f"{C.GRAY}{'─' * 60}{C.RESET}")
    if not cfg.get("wallet_url"):
        print(f"  {render_warn('No wallet connected — run setup (s).')}")
    print(f"  {C.DIM}q Quit │ r Refresh │ R Reset │ a Auto-refresh │ s Setup │ m Actions │ p Provider guide{C.RESET}")
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
    print(f"{C.DIM}  → Your wallet RPC, e.g. {C.CYAN}http://127.0.0.1:18083/json_rpc{C.RESET}{C.DIM}.\n"
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
    bundle_ok = bool(Backend(cfg.data).C("miner"))
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
    proc = subprocess.Popen([py, str(script)], stdout=logf, stderr=logf,
                            start_new_session=True)
    KEEPER_PID.write_text(str(proc.pid))
    info_box("Keeper launched", [
        render_ok(f"Oracle keeper started (pid {proc.pid})"), "",
        "It submits prices and heartbeats automatically.",
        f"Log: {LOG_DIR / 'keeper.log'}",
    ], color=C.GREEN)


def stop_keeper() -> None:
    pid = keeper_running()
    if not pid:
        info_box("Keeper", [render_warn("Keeper is not running.")])
        return
    try:
        os.kill(pid, 15)
        KEEPER_PID.unlink(missing_ok=True)
        info_box("Keeper stopped", [render_ok(f"Stopped pid {pid}.")], color=C.GREEN)
    except OSError as e:
        info_box("Keeper", [render_error(f"Could not stop: {e}")], color=C.RED)


# ---------------------------------------------------------------------------
# Actions (real transactions)
# ---------------------------------------------------------------------------

def action_registration_flow(cfg, b):
    """Guided registration with a clean explanation of service choice."""
    if not b.has_wallet:
        info_box("Register miner", [
            render_error("No wallet RPC configured."),
            "Run Setup (s) and fill 'Wallet RPC URL', e.g. http://127.0.0.1:18083/json_rpc",
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
    if m and isinstance(m, list) and len(m) >= 15:
        if bool(m[M_ACTIVE]):
            info_box("Already registered", [
                render_ok("This address already has an active miner profile."), "",
                "Use 'Increase stake' or 'Enable service' instead.",
            ], color=C.GREEN)
        else:
            info_box("Already registered (inactive)", [
                render_warn("This address has a miner profile, but it is inactive."),
                "To reactivate: use 'Increase miner stake' to reach the minimum stake.",
                "If you want to start fresh: deregister from xvault first.",
            ], color=C.YELLOW)
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

    # Show full diagnostic before registration
    try:
        xel_bal = b.balance(b.xel_asset)
        vlt_bal = b.balance(b.vlt_asset)
        xusd_bal = b.balance(b.xusd_asset)
        diag = [
            f"Wallet address: {b.address}",
            f"XEL balance: {b.fmt(xel_bal) if xel_bal is not None else 'unavailable'}",
            f"VLT balance: {b.fmt(vlt_bal) if vlt_bal is not None else 'unavailable'}",
            f"xUSD balance: {b.fmt(xusd_bal) if xusd_bal is not None else 'unavailable'}",
            f"Requested stake: {amt} VLT ({stake_atomic} atomic)",
        ]
        info_box("Pre-registration check", diag, color=C.CYAN)
    except Exception:
        pass

    print(f"{C.DIM}  Registering with: endpoints={endpoint}  services_mask={mask}  "
          f"stake={amt} VLT{C.RESET}\n")
    if not confirm(f"Register this address as a miner (services mask {mask}, "
                   f"endpoint {endpoint})?"):
        return
    res = b.miner_register(endpoint, mask, stake_atomic)
    if res.ok:
        info_box("Registered", [
            render_ok("Miner profile created ✓"), "",
            f"Tx: {res.tx[:44]}…",
            "Next: enable services & send a heartbeat from the Actions menu.",
        ], color=C.GREEN)
    else:
        info_box("Registration rejected", [render_error(f"Reason: {res.reason}")],
                 color=C.RED)


def action_heartbeat(cfg, b):
    if not b.has_wallet:
        info_box("Heartbeat failed", [
            render_error("No wallet RPC configured."),
            "Run Setup (s) and fill 'Wallet RPC URL', e.g. http://127.0.0.1:18083/json_rpc",
        ], color=C.RED)
        return
    if not b.ping_wallet():
        info_box("Heartbeat failed", [
            render_error("Wallet RPC is configured but unreachable."),
            "Make sure the wallet is running and the URL is correct.",
            "Current URL: " + (cfg.get("wallet_url") or "(empty)"),
        ], color=C.RED)
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
        info_box("Heartbeat", [
            render_warn("Miner profile is inactive on-chain."),
            "The contract rejects heartbeats from inactive miners.",
            "If your stake fell below the minimum, use 'Increase miner stake' to reactivate.",
        ], color=C.YELLOW)
        return
    res = b.miner_heartbeat()
    if res.ok:
        info_box("Heartbeat sent", [
            render_ok("Transaction broadcast ✓"), "",
            f"Tx: {res.tx[:40]}…",
        ], color=C.GREEN)
    else:
        info_box("Heartbeat rejected", [render_error(f"Reason: {res.reason}")],
                 color=C.RED)


def action_increase_stake(cfg, b):
    if not b.has_wallet:
        info_box("Increase stake", [
            render_error("No wallet RPC configured."),
            "Run Setup (s) and fill 'Wallet RPC URL'.",
        ], color=C.RED)
        return
    if not b.ping_wallet():
        info_box("Increase stake", [
            render_error("Wallet RPC is configured but unreachable."),
            "Make sure the wallet is running and the URL is correct.",
            "Current URL: " + (cfg.get("wallet_url") or "(empty)"),
        ], color=C.RED)
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
        info_box("Increase stake", [
            render_warn("Miner profile is inactive on-chain."),
            "Increasing stake can reactivate it if stake was below the minimum.",
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
        if res.ok:
            info_box("Stake increased", [render_ok("Done ✓"), f"Tx: {res.tx[:40]}…"],
                     color=C.GREEN)
        else:
            info_box("Failed", [render_error(f"Reason: {res.reason}")], color=C.RED)


def action_enable_service(cfg, b):
    if not b.has_wallet:
        info_box("Enable service", [
            render_error("No wallet RPC configured."),
            "Run Setup (s) and fill 'Wallet RPC URL'.",
        ], color=C.RED)
        return
    if not b.ping_wallet():
        info_box("Enable service", [
            render_error("Wallet RPC is configured but unreachable."),
            "Make sure the wallet is running and the URL is correct.",
            "Current URL: " + (cfg.get("wallet_url") or "(empty)"),
        ], color=C.RED)
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
        info_box("Enable service", [
            render_warn("Miner profile is inactive on-chain."),
            "Reactivate it first by increasing your stake (Increase miner stake).",
        ], color=C.YELLOW)
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
        if res.ok:
            info_box("Service enabled", [render_ok(f"{label} on ✓"), f"Tx: {res.tx[:40]}…"],
                     color=C.GREEN)
        else:
            info_box("Failed", [render_error(f"Reason: {res.reason}")], color=C.RED)


def action_menu(cfg, b):
    from onboarding import miner_running, start_miner, stop_miner
    running = miner_running()
    opts = [
        ("Register as miner (guided)", "reg"),
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
            print("Journal du mineur : %s\\.xelis-vault\\logs\\miner.log"
                  % os.path.expanduser("~"))
        time.sleep(2)
        return

    if args.setup:
        interactive_setup(cfg)
        return

    hint = _fallback_rpc_if_needed(cfg)
    mode = check_contracts(cfg)

    auto_refresh = True
    running = [True]

    def on_signal(sig, frame):
        running[0] = False

    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGTERM, on_signal)
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, on_signal)

    hide_cursor()
    try:
        while running[0]:
            b = Backend(cfg.data)
            live = fetch_live(b) if mode != "demo" or b.topo() else \
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
                hide_cursor()
            elif key == "R":
                show_cursor()
                if confirm("Reset configuration to defaults? This will clear all settings."):
                    cfg.reset()
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
