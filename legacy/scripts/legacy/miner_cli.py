#!/usr/bin/env python3
"""
============================================================================
 XELIS Vault — Miner CLI (miner_cli.py)
============================================================================
Register and manage XelisVaultMiner nodes (oracle/chat services) via the
protocol layer.

Commands:
  register  Register the wallet's address as a miner (service oracle).
            Requires >= 1000 VLT deposited in the invoke.
  heartbeat Send a heartbeat to stay active.
  status    Show miner + oracle feed status for this wallet.
  help      Show this help.

Usage:
  python3 miner_cli.py register --wallet-rpc http://127.0.0.1:18084/json_rpc \\
      --endpoint http://127.0.0.1:18084 --stake-vlt 1000
  python3 miner_cli.py heartbeat --wallet-rpc http://127.0.0.1:18084/json_rpc
  python3 miner_cli.py status --wallet-rpc http://127.0.0.1:18084/json_rpc
============================================================================
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from protocol import (Protocol, MIN_STAKE_VLT, VLT_ASSET, XEL_ASSET,
                     SERVICE_ORACLE, SERVICE_CHAT,
                     miner_register, miner_heartbeat, miner_active_count,
                     miner_total_staked, oracle_active_providers,
                     oracle_feed_info, FEED_XEL_USD, ADMIN)

WALLET_URL = "http://127.0.0.1:18082/json_rpc"
AUTH = ("wallet", "testpass")


def make_pubkey(addr: str) -> str:
    return hashlib.sha256(addr.encode()).hexdigest()


def cmd_register(args) -> None:
    p = Protocol(wallet_url=args.wallet_rpc,
                 wallet_auth=(args.user, args.password))
    addr = p.wallet.address()
    print(f"registering miner: {addr}")
    print(f"  endpoint:  {args.endpoint}")
    print(f"  pubkey:    {make_pubkey(addr)[:16]}...")
    print(f"  services:  oracle (bit 1) {('+ chat (bit 2)') if args.chat else ''}")
    mask = SERVICE_ORACLE | (SERVICE_CHAT if args.chat else 0)
    stake = int(args.stake_vlt * 10 ** 8)
    if stake < MIN_STAKE_VLT:
        print(f"ERROR: stake must be >= {MIN_STAKE_VLT / 10 ** 8} VLT")
        sys.exit(1)
    print(f"  stake:     {stake / 10 ** 8} VLT ({stake} atomic)")
    if args.dry_run:
        print("[DRY-RUN] would call XelisVaultMiner.register_miner")
        return
    try:
        tx = miner_register(p, args.endpoint, make_pubkey(addr), mask, stake)
        p.confirm(tx, "miner registered")
        print(f"miner registered tx={tx[:40]}...")
    except Exception as e:
        msg = str(e).lower()
        if "already" in msg:
            print("already registered")
        else:
            print(f"ERROR: {e}")
            sys.exit(1)


def cmd_heartbeat(args) -> None:
    p = Protocol(wallet_url=args.wallet_rpc,
                 wallet_auth=(args.user, args.password))
    addr = p.wallet.address()
    print(f"heartbeat for {addr}")
    if args.dry_run:
        print("[DRY-RUN] would call XelisVaultMiner.submit_heartbeat")
        return
    try:
        tx = miner_heartbeat(p)
        p.confirm(tx, "heartbeat sent")
        print(f"heartbeat tx={tx[:40]}...")
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)


def cmd_status(args) -> None:
    p = Protocol(wallet_url=args.wallet_rpc,
                 wallet_auth=(args.user, args.password))
    addr = p.wallet.address()
    print(f"wallet address:  {addr}")
    print(f"XEL balance:     {p.balance() / 10 ** 8:.4f} XEL")
    print(f"VLT balance:     {p.balance(VLT_ASSET) / 10 ** 8:.4f} VLT")
    print()
    print("--- XelisVaultMiner ---")
    print(f"  registered miners (mc):       {miner_active_count(p)}")
    print(f"  total staked VLT (ts):        {miner_total_staked(p) / 10 ** 8:.2f}")
    print(f"  active oracle providers (sm_1): {oracle_active_providers(p)}")
    try:
        me = p.read_contract(p.resolve("XelisVaultMiner"),
                             f"miner_{addr}")
        if me:
            fields = me
            print(f"  my miner record: {fields[:6]}...")
    except Exception as e:
        print(f"  (no miner record for this address)")
    print()
    print("--- StakedOracle feed 0 (XEL/USD) ---")
    try:
        info = oracle_feed_info(p, FEED_XEL_USD)
        for k, v in info.items():
            print(f"  {k}: {v}")
    except Exception as e:
        print(f"  feed read failed: {e}")
    print()
    print("--- Registry (cur_<Name> sample) ---")
    for name in ["StakedOracle", "XelisVaultMiner", "VaultEngine"]:
        print(f"  {name}: {p.resolve(name)[:24]}...")


def main() -> None:
    parser = argparse.ArgumentParser(description="XELIS Vault Miner CLI")
    sub = parser.add_subparsers(dest="cmd")

    r = sub.add_parser("register", help="register as miner")
    r.add_argument("--wallet-rpc", default=WALLET_URL)
    r.add_argument("--user", default=AUTH[0])
    r.add_argument("--password", default=AUTH[1])
    r.add_argument("--endpoint", default="http://127.0.0.1:18082")
    r.add_argument("--stake-vlt", type=float, default=1000.0)
    r.add_argument("--chat", action="store_true", help="also register chat service")
    r.add_argument("--dry-run", action="store_true")

    h = sub.add_parser("heartbeat", help="send heartbeat")
    h.add_argument("--wallet-rpc", default=WALLET_URL)
    h.add_argument("--user", default=AUTH[0])
    h.add_argument("--password", default=AUTH[1])
    h.add_argument("--dry-run", action="store_true")

    s = sub.add_parser("status", help="show status")
    s.add_argument("--wallet-rpc", default=WALLET_URL)
    s.add_argument("--user", default=AUTH[0])
    s.add_argument("--password", default=AUTH[1])

    args = parser.parse_args()
    if not args.cmd:
        parser.print_help()
        sys.exit(0)
    {"register": cmd_register, "heartbeat": cmd_heartbeat,
     "status": cmd_status}[args.cmd](args)


if __name__ == "__main__":
    main()