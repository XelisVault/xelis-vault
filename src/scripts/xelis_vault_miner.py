#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Optional

try:
    import requests
except ImportError:
    print("ERROR: 'requests' not installed. Run:  pip install requests")
    sys.exit(1)

# ── testnet defaults (2026-07-28) ──────────────────────────────────────
# StakedOracle hash — UPDATE after deployment
STAKED_ORACLE_HASH = ""
MINER_HASH        = "21ed1297c7ed4001a4a7c9a4bb89b10da0b0f3ad0312545a5af4a761200af207"
VLT_HASH          = "7275c55d711789b1b746cd4695b04c0e393a0db74ecf72360c5544b73368cfab"
VLT_ASSET         = "2de72ed3ea2d8ff30e6df57ba3a4d993dedfa8636d207d43d09e33615bfde2c6"

# entry IDs (chunk index = entry_id)
ENTRY_SUBMIT_PRICE     = 15  # StakedOracle chunk 15 = submit_price
ENTRY_AGGREGATE_NOW    = 16  # StakedOracle chunk 16 = aggregate_now
ENTRY_GET_PRICE        = 21  # StakedOracle chunk 21 = get_price_for_asset

ENTRY_REGISTER_MINER   = 10
ENTRY_SUBMIT_HEARTBEAT = 16
ENTRY_MINER_ACTIVE     = 19
ENTRY_MINER_REPUTATION = 21

SERVICE_ORACLE     = 1
MIN_STAKE_VLT      = 100_000_000_000  # 1000 VLT (8 decimals, v10.7 anti-Sybil)
HEARTBEAT_INTERVAL = 100
PRICE_UPDATE_INT   = 100
ORACLE_TIMELOCK    = 3
SANITY_MIN         = 0.001
SANITY_MAX         = 10_000.0
MIN_SOURCES        = 2
REP_GOOD           = 5000

VAULT_DIR   = Path.home() / ".xelis-vault"
CONFIG_PATH = VAULT_DIR / "config" / "config.json"
LOG_DIR     = VAULT_DIR / "logs"
LOG_FILE    = LOG_DIR / "miner.log"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("xvm")

# ── helpers ────────────────────────────────────────────────────────────

def mask(s: Optional[str], keep: int = 4) -> str:
    if not s or len(s) <= keep * 2: return "*" * len(s or "")
    return f"{s[:keep]}{'*'*(len(s)-keep*2)}{s[-keep:]}"


def prompt(default: str, label: str, secret: bool = False) -> str:
    v = os.environ.get(label.upper().replace(" ", "_"))
    if v: return v
    d = f" [{default}]" if default else ""
    try:
        return input(f"  {label}{d}: ").strip() or default
    except (EOFError, KeyboardInterrupt):
        return default


# ── config ─────────────────────────────────────────────────────────────

class Config:
    def __init__(self) -> None:
        self.rpc_url: str = "http://127.0.0.1:18081"
        self.wallet_url: str = "http://127.0.0.1:18082"
        self.wallet_user: str = "wallet"
        self.wallet_pass: str = "testpass"
        self.miner_address: str = ""
        self.endpoint_url: str = ""
        self.services_mask: int = SERVICE_ORACLE
        self.enable_miner: bool = False
        self.enable_oracle: bool = True
        self.price_update_interval: int = PRICE_UPDATE_INT
        self.oracle_timelock: int = ORACLE_TIMELOCK
        self.heartbeat_interval: int = HEARTBEAT_INTERVAL

    @classmethod
    def load_or_interactive(cls, path: Path, args: argparse.Namespace) -> Config:
        cfg = cls()
        if path.exists():
            try:
                raw = json.loads(path.read_text())
                for k, v in raw.items():
                    if hasattr(cfg, k): setattr(cfg, k, v)
            except Exception:
                pass
        if args.rpc:            cfg.rpc_url = args.rpc
        if args.wallet_url:     cfg.wallet_url = args.wallet_url
        if args.endpoint:       cfg.endpoint_url = args.endpoint
        if args.miner:          cfg.enable_miner = True
        if args.no_oracle:      cfg.enable_oracle = False
        if args.wallet_user:    cfg.wallet_user = args.wallet_user
        if args.wallet_pass:    cfg.wallet_pass = args.wallet_pass

        if not args.yes:
            print(f"\n  ── XELIS Vault Miner — Setup ──")
            print(f"  Config: {path}")
            cfg.rpc_url = prompt(cfg.rpc_url, "Daemon RPC URL")
            cfg.wallet_url = prompt(cfg.wallet_url, "Wallet RPC URL")
            cfg.wallet_user = prompt(cfg.wallet_user, "Wallet username")
            cfg.wallet_pass = prompt(cfg.wallet_pass, "Wallet password", secret=True)
            if not cfg.miner_address or not cfg.enable_miner:
                m = prompt("", "Miner address (or enter to skip miner mode)")
                if m:
                    cfg.miner_address = m
                    cfg.enable_miner = True
                    cfg.endpoint_url = prompt(cfg.endpoint_url, "Public endpoint URL")
            print("")

        cfg.save(path)
        return cfg

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.__dict__, indent=2))


# ── RPC clients ────────────────────────────────────────────────────────

class DaemonClient:
    def __init__(self, url: str) -> None:
        self.url = url.rstrip("/") + "/json_rpc"
        self._id = 0

    def call(self, method: str, params: dict | None = None) -> Any:
        self._id += 1
        body = {"method": method, "jsonrpc": "2.0", "id": self._id}
        if params is not None:
            body["params"] = params
        r = requests.post(self.url, json=body, timeout=30)
        r.raise_for_status()
        data = r.json()
        if data.get("error"):
            raise RuntimeError(f"daemon RPC error: {data['error']}")
        return data.get("result", {})

    def topoheight(self) -> int:
        return int(self.call("get_topoheight"))

    def is_synced(self) -> bool:
        return bool(self.call("get_info").get("synced", False))

    def read_contract_data(self, contract: str, key: dict) -> Any:
        return self.call("get_contract_data", {"contract": contract, "key": key})


class WalletClient:
    def __init__(self, base_url: str, user: str, password: str) -> None:
        self.url = base_url.rstrip("/") + "/json_rpc"
        self.auth = (user, password)
        self._id = 0

    def call(self, method: str, params: dict | None = None) -> Any:
        self._id += 1
        body = {"jsonrpc": "2.0", "method": method, "id": self._id}
        if params is not None:
            body["params"] = params
        r = requests.post(self.url, json=body, auth=self.auth, timeout=60)
        r.raise_for_status()
        data = r.json()
        if data.get("error"):
            raise RuntimeError(f"wallet RPC error: {data['error']}")
        return data.get("result", {})

    def nonce(self) -> int:
        return int(self.call("get_nonce"))

    def invoke(self, contract: str, entry_id: int, params: list,
               deposits: dict | None = None, max_gas: int = 500_000) -> Optional[str]:
        invoke = {
            "contract": contract, "entry_id": entry_id,
            "parameters": params, "deposits": deposits or {},
            "max_gas": max_gas, "permission": "all",
        }
        tx_params: dict = {"invoke_contract": invoke, "fee": {"fixed": 10_000_000}, "broadcast": True}
        for attempt in range(2):
            try:
                result = self.call("build_transaction", tx_params)
                return result.get("hash") or None
            except Exception as e:
                msg = str(e)
                if attempt == 0 and "nonce" in msg.lower():
                    import re
                    m = re.search(r'(?:expected|range:\s*\[)(\d+)', msg)
                    if m:
                        tx_params["nonce"] = int(m.group(1))
                        log.warning(f"  retrying with nonce {tx_params['nonce']} ...")
                        continue
                    m = re.search(r'nonce\s+(\d+)\s+already\s+used', msg, re.I)
                    if m:
                        tx_params["nonce"] = int(m.group(1)) + 1
                        log.warning(f"  retrying with nonce {tx_params['nonce']} ...")
                        continue
                    log.warning(f"  nonce error, retrying once ...")
                    continue
                log.error(f"  TX failed (entry {entry_id}): {e}")
                return None


# ── price fetching ─────────────────────────────────────────────────────

def fetch_coingecko() -> Optional[float]:
    try:
        r = requests.get("https://api.coingecko.com/api/v3/simple/price",
                         params={"ids": "xelis", "vs_currencies": "usd"}, timeout=10)
        r.raise_for_status()
        return float(r.json()["xelis"]["usd"])
    except Exception:
        return None


def fetch_mexc() -> Optional[float]:
    try:
        r = requests.get("https://api.mexc.com/api/v3/ticker/price",
                         params={"symbol": "XELUSDT"}, timeout=10)
        r.raise_for_status()
        return float(r.json()["price"])
    except Exception:
        return None


def fetch_price() -> Optional[float]:
    prices: list[tuple[str, float]] = []
    for src in (("coingecko", fetch_coingecko), ("mexc", fetch_mexc)):
        v = src[1]()
        if v is not None:
            prices.append((src[0], v))
    if len(prices) < MIN_SOURCES:
        log.warning(f"  Price: only {len(prices)} source(s)")
        return None
    med = statistics.median(p for _, p in prices)
    if not (SANITY_MIN < med < SANITY_MAX):
        log.warning(f"  Price ${med:.6f} out of range")
        return None
    log.info(f"  XEL/USD: ${med:.6f} ({'+'.join(s for s,_ in prices)})")
    return med


def usd_to_atomic(p: float, dec: int = 8) -> int:
    return int(round(p * 10 ** dec))


# ── price oracle daemon ────────────────────────────────────────────────

class PriceDaemon:
    def __init__(self, cfg: Config, daemon: DaemonClient, wallet: WalletClient, dry: bool) -> None:
        self.cfg = cfg
        self.d = daemon
        self.w = wallet
        self.dry = dry
        self.running = True
        self.last_topo: int = 0
        self.pending_topo: int = 0
        for sig in (signal.SIGINT, signal.SIGTERM):
            try: signal.signal(sig, lambda *_: setattr(self, "running", False))
            except Exception: pass

    def _read_price(self) -> Optional[int]:
        try:
            r = self.d.read_contract_data(STAKED_ORACLE_HASH, {
                "type": "primitive", "value": {"type": "string", "value": "p"}
            })
            if r.get("data"):
                return int(r["data"]["value"]["value"])
            return None
        except Exception: return None

    def _read_pending(self) -> int:
        try:
            r = self.d.read_contract_data(STAKED_ORACLE_HASH, {
                "type": "primitive", "value": {"type": "string", "value": "pp"}
            })
            if r.get("data"):
                return int(r["data"]["value"]["value"])
            return 0
        except Exception: return 0

    def _read_pending_topo(self) -> int:
        try:
            r = self.d.read_contract_data(STAKED_ORACLE_HASH, {
                "type": "primitive", "value": {"type": "string", "value": "pt"}
            })
            if r.get("data"):
                return int(r["data"]["value"]["value"])
            return 0
        except Exception: return 0

    def _propose(self, p: int) -> bool:
        if self.dry: return True
        return bool(self.w.invoke(STAKED_ORACLE_HASH, ENTRY_SUBMIT_PRICE,
                     [{"type":"primitive","value":{"type":"u64","value":str(p)}}]))

    def _execute(self) -> bool:
        if self.dry: return True
        return bool(self.w.invoke(STAKED_ORACLE_HASH, ENTRY_AGGREGATE_NOW, []))

    def run(self, topo: int) -> None:
        if self.last_topo == 0:
            self.last_topo = topo
            cur = self._read_price()
            log.info(f"  On-chain price: ${cur/1e8:.6f}" if cur else "  No on-chain price yet")
            return

        # Check if there is a pending proposal to execute
        pending_pp = self._read_pending()
        pending_pt = self._read_pending_topo()
        if pending_pp and pending_pt:
            if topo >= pending_pt + self.cfg.oracle_timelock:
                log.info("  Executing pending proposal ...")
                if self._execute():
                    self.last_topo = topo
            return

        if topo - self.last_topo < self.cfg.price_update_interval:
            return

        log.info(f"── oracle update (topo {topo}) ──")
        price = fetch_price()
        if price is None: return

        atomic = usd_to_atomic(price)
        cur = self._read_price()
        if cur:
            chg = abs(atomic - cur) / max(cur, 1) * 100
            log.info(f"  Change: {chg:.2f}%")
            if chg < 1.0:
                log.info("  ─ skipped (<1%)")
                self.last_topo = topo
                return
        log.info("  Proposing price ...")
        if self._propose(atomic):
            self.last_topo = topo


# ── miner daemon ───────────────────────────────────────────────────────

class MinerDaemon:
    def __init__(self, cfg: Config, daemon: DaemonClient, wallet: WalletClient, dry: bool) -> None:
        self.cfg = cfg
        self.d = daemon
        self.w = wallet
        self.dry = dry
        self.last_hb: int = 0

    def _is_registered(self) -> bool:
        try:
            r = self.d.read_contract_data(MINER_HASH, {
                "type": "primitive", "value": {"type": "string", "value": f"miner_{self.cfg.miner_address}"}
            })
            return bool(r.get("data"))
        except Exception: return False

    def register(self) -> bool:
        if self.dry: return True
        params = [
            {"type":"primitive","value":{"type":"string","value":self.cfg.endpoint_url}},
            {"type":"primitive","value":{"type":"opaque","value":{"type":"Hash","value":"0"*64}}},
            {"type":"primitive","value":{"type":"u8","value":self.cfg.services_mask}},
        ]
        deposits = {VLT_ASSET: {"amount": MIN_STAKE_VLT}}
        tx = self.w.invoke(MINER_HASH, ENTRY_REGISTER_MINER, params, deposits=deposits,
                          max_gas=5_000_000)
        if tx: log.info(f"  registered → {tx[:16]}..."); return True
        return False

    def heartbeat(self) -> bool:
        if self.dry: return True
        tx = self.w.invoke(MINER_HASH, ENTRY_SUBMIT_HEARTBEAT, [])
        if tx: log.info(f"  heartbeat → {tx[:16]}..."); return True
        return False

    def reputation(self) -> int:
        try:
            r = self.d.read_contract_data(MINER_HASH, {
                "type": "primitive", "value": {"type": "string", "value": f"rep_{self.cfg.miner_address}"}
            })
            if r.get("data"):
                return int(r["data"]["value"]["value"])
            return 0
        except Exception: return 0

    def run(self, topo: int) -> None:
        if not self.cfg.enable_miner: return
        if not self._is_registered():
            if not self.cfg.miner_address or not self.cfg.endpoint_url:
                return
            log.info("  registering ...")
            self.register()
            return
        if topo - self.last_hb >= self.cfg.heartbeat_interval:
            self.heartbeat()
            self.last_hb = topo
        rep = self.reputation()
        if rep and rep < REP_GOOD:
            log.warning(f"  reputation {rep} — below Good")


# ── interactive actions ────────────────────────────────────────────────

def cmd_register(cfg: Config, d: DaemonClient, w: WalletClient) -> None:
    print("\n  Registering as miner on XelisVaultMiner ...")
    if not cfg.miner_address:
        cfg.miner_address = input("  Your miner address (xet:...): ").strip()
        cfg.save(CONFIG_PATH)
    if not cfg.endpoint_url:
        cfg.endpoint_url = input("  Your public endpoint URL: ").strip()
        cfg.save(CONFIG_PATH)
    miner = MinerDaemon(cfg, d, w, dry=False)
    if miner.register():
        print("  Registered successfully!")
    else:
        print("  Registration failed.")


def cmd_balance(cfg: Config, w: WalletClient) -> None:
    print("\n  Checking balances ...")
    try:
        r = w.call("get_balance")
        print(f"  XEL:    {int(r.get('balance',0))/1e8:.4f}")
    except Exception as e:
        print(f"  XEL:    error ({e})")


def cmd_wizard(cfg: Config) -> None:
    print("\n  ── Interactive Setup Wizard ──")
    cfg.rpc_url = prompt(cfg.rpc_url, "Daemon RPC URL")
    cfg.wallet_url = prompt(cfg.wallet_url, "Wallet RPC URL")
    cfg.wallet_user = prompt(cfg.wallet_user, "Wallet username")
    cfg.wallet_pass = prompt(cfg.wallet_pass, "Wallet password", secret=True)
    m = prompt(cfg.miner_address, "Miner address (skip to skip miner mode)")
    if m:
        cfg.miner_address = m
        cfg.enable_miner = True
        cfg.endpoint_url = prompt(cfg.endpoint_url, "Public endpoint URL")
    cfg.save(CONFIG_PATH)
    print("  Config saved.\n")


def cmd_interactive(cfg: Config, d: DaemonClient, w: WalletClient) -> None:
    print(f"\n  Interactive mode — XELIS Vault Miner")
    print(f"  Daemon: {cfg.rpc_url}  |  Wallet: {cfg.wallet_url}")
    print(f"  Commands: register, balances, oracle, start, quit")
    while True:
        try:
            cmd = input("\n  > ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            break
        if cmd == "register":
            cmd_register(cfg, d, w)
        elif cmd == "balances":
            cmd_balance(cfg, w)
        elif cmd == "oracle":
            cfg.enable_oracle = True
            cfg.enable_miner = False
            cmd_daemon(cfg, d, w)
        elif cmd == "start":
            cmd_daemon(cfg, d, w)
        elif cmd in ("quit", "exit"):
            break
        else:
            print(f"  Unknown: {cmd}")


def cmd_daemon(cfg: Config, d: DaemonClient, w: WalletClient, dry: bool = False) -> None:
    log.info("╔══════════════════════════════════════════╗")
    log.info("║     XELIS Vault v5.1 — Daemon            ║")
    log.info("╚══════════════════════════════════════════╝")
    log.info(f"  RPC:          {cfg.rpc_url}")
    log.info(f"  Wallet:       {cfg.wallet_url}")
    log.info(f"  Oracle:       {'ON' if cfg.enable_oracle else 'OFF'}")
    log.info(f"  Miner:        {cfg.miner_address or 'OFF'}")
    log.info(f"  Dry run:      {dry}")
    log.info("")

    oracle = PriceDaemon(cfg, d, w, dry)
    miner = MinerDaemon(cfg, d, w, dry)

    last_topo = 0
    while oracle.running:
        try:
            topo = d.topoheight()
            if topo == last_topo:
                time.sleep(5); continue
            last_topo = topo
            if cfg.enable_oracle:
                oracle.run(topo)
            if cfg.enable_miner:
                miner.run(topo)
            time.sleep(5)
        except KeyboardInterrupt:
            break
        except Exception as e:
            log.error(f"  loop: {e}")
            time.sleep(10)
    log.info("  stopped.")


# ── main ──────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="XELIS Vault — All-in-One Miner & Price Oracle Daemon")
    parser.add_argument("--rpc", help="Daemon RPC URL")
    parser.add_argument("--wallet-url", help="Wallet RPC URL")
    parser.add_argument("--wallet-user", help="Wallet username", default="wallet")
    parser.add_argument("--wallet-pass", help="Wallet password", default="testpass")
    parser.add_argument("--endpoint", help="Public endpoint URL (miner mode)")
    parser.add_argument("--config", type=Path, default=CONFIG_PATH, help=f"Config path (default: {CONFIG_PATH})")
    parser.add_argument("--miner", action="store_true", help="Enable miner mode")
    parser.add_argument("--no-oracle", action="store_true", help="Disable oracle updates")
    parser.add_argument("--dry-run", action="store_true", help="Log only, no TX")
    parser.add_argument("--yes", "-y", action="store_true", help="Skip interactive prompts (use saved/CLI config)")
    parser.add_argument("--interactive", "-i", action="store_true", help="Interactive shell mode")
    args = parser.parse_args()

    cfg = Config.load_or_interactive(args.config, args)
    d = DaemonClient(cfg.rpc_url)
    w = WalletClient(cfg.wallet_url, cfg.wallet_user, cfg.wallet_pass)

    if args.interactive:
        cmd_interactive(cfg, d, w)
        return

    if not cfg.enable_miner and not cfg.enable_oracle:
        print("Nothing to do (miner off, oracle off). Use --miner or remove --no-oracle")
        return

    cmd_daemon(cfg, d, w, dry=args.dry_run)


if __name__ == "__main__":
    main()
