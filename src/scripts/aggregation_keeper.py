#!/usr/bin/env python3
"""
============================================================================
 XELIS Vault — Aggregation Keeper (aggregation_keeper.py)
============================================================================
Calls StakedOracle.aggregate_now (entry chunk 17) every interval so prices
are aggregated even if no provider submits. Anyone can run this.

Usage:
  python3 aggregation_keeper.py --wallet-rpc http://127.0.0.1:18082/json_rpc
                                --feed-ids 0 [--interval 25] [--verbose]
============================================================================
"""
from __future__ import annotations

import argparse
import json
import logging
import signal
import sys
import time
from pathlib import Path
from typing import Optional

try:
    import requests
except ImportError:
    print("ERROR: 'requests' is not installed (pip install requests)", file=sys.stderr)
    sys.exit(1)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from protocol import (Protocol, oracle_aggregate_now, oracle_feed_info,
                     FEED_XEL_USD)

DEFAULT_INTERVAL = 25
DEFAULT_FEED_IDS = "0"
VAULT_DIR = Path.home() / ".xelis-vault"
LOG_DIR = VAULT_DIR / "logs"
LOG_FILE = LOG_DIR / "keeper.log"


def setup_logging(verbose: bool = False) -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("keeper")
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    logger.propagate = False
    if logger.handlers:
        return logger
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s",
                            datefmt="%Y-%m-%d %H:%M:%S")
    try:
        from logging.handlers import RotatingFileHandler
        fh = RotatingFileHandler(LOG_FILE, maxBytes=50 * 1024 * 1024, backupCount=3)
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    except Exception:
        pass
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(sh)
    return logger


log = logging.getLogger("keeper")


def main() -> None:
    parser = argparse.ArgumentParser(description="XELIS Vault Aggregation Keeper")
    parser.add_argument("--wallet-rpc", default="http://127.0.0.1:18082/json_rpc")
    parser.add_argument("--daemon-rpc", default="http://127.0.0.1:18081/json_rpc")
    parser.add_argument("--auth", default="wallet:testpass")
    parser.add_argument("--feed-ids", default=DEFAULT_FEED_IDS)
    parser.add_argument("--interval", type=int, default=DEFAULT_INTERVAL)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    global log
    log = setup_logging(args.verbose)

    user, _, pwd = args.auth.partition(":")
    p = Protocol(wallet_url=args.wallet_rpc, wallet_auth=(user, pwd),
                 daemon_url=args.daemon_rpc)
    feed_ids = [int(x) for x in args.feed_ids.split(",") if x.strip()]

    log.info("=" * 60)
    log.info("XELIS Vault Aggregation Keeper")
    log.info(f"  wallet RPC: {args.wallet_rpc}")
    log.info(f"  feed ids:   {feed_ids}")
    log.info(f"  interval:   {args.interval}s")
    log.info("=" * 60)

    running = True
    def handler(signum, frame):
        nonlocal running
        running = False
    signal.signal(signal.SIGINT, handler)
    signal.signal(signal.SIGTERM, handler)

    while running:
        try:
            topo = p.topoheight()
            for fid in feed_ids:
                try:
                    tx = oracle_aggregate_now(p, fid)
                    info = oracle_feed_info(p, fid)
                    log.info(f"aggregated feed={fid} topo={topo} tx={tx[:32]} "
                             f"price={info.get('agg_price')} "
                             f"sources={info.get('agg_sources')} "
                             f"cycle={info.get('cycle')}")
                except Exception as e:
                    msg = str(e).lower()
                    if "toosoon" in msg or "already" in msg:
                        log.debug(f"feed={fid} not ready yet")
                    else:
                        log.error(f"aggregate feed={fid} failed: {e}")
        except Exception as e:
            log.error(f"loop error: {e}")
        slept = 0
        while slept < args.interval and running:
            time.sleep(1)
            slept += 1

    log.info("keeper stopped")


if __name__ == "__main__":
    main()