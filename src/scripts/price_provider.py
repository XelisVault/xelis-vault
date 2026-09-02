#!/usr/bin/env python3
"""
============================================================================
 XELIS Vault — Price Provider (price_provider.py)
============================================================================
Oracle price provider daemon.

Fetches the XEL/USD price from public exchanges, computes a median, and
submits it to StakedOracle.submit_price (entry chunk 16). The submitting
wallet must be a REGISTERED MINER for the oracle service (XelisVaultMiner
register_miner, service mask bit 1) with >= 1000 VLT stake.

Usage:
  python3 price_provider.py --rpc http://127.0.0.1:18084 [--feed-id 0]
                            [--interval 20] [--verbose]

Each provider runs against its own wallet process (one per miner address).

PRIVACY: never logs private keys / mnemonics / IPs. Only public on-chain
data and aggregated exchange prices.
============================================================================
"""
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
    print("ERROR: 'requests' is not installed (pip install requests)", file=sys.stderr)
    sys.exit(1)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from protocol import (Protocol, FEED_XEL_USD, FEED_DECIMALS,
                     oracle_submit_price, oracle_feed_info, get_protocol)

DEFAULT_INTERVAL = 20          # seconds between submissions
OUTLIER_PCT = 0.05             # reject sources deviating >5% from median
STALE_SECONDS = 30
MIN_SOURCES = 2
SANITY_MIN = 0.001
SANITY_MAX = 10_000.0

VAULT_DIR = Path.home() / ".xelis-vault"
LOG_DIR = VAULT_DIR / "logs"
LOG_FILE = LOG_DIR / "provider.log"


def setup_logging(verbose: bool = False) -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("provider")
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


log = logging.getLogger("provider")


class PriceSource:
    def __init__(self, name: str, url: str, params: dict, path: str,
                 timeout: int = 10):
        self.name = name
        self.url = url
        self.params = params
        self.path = path
        self.timeout = timeout

    def fetch(self) -> Optional[float]:
        try:
            r = requests.get(self.url, params=self.params, timeout=self.timeout)
            r.raise_for_status()
            data = r.json()
            for part in self.path.split("."):
                if part.isdigit():
                    data = data[int(part)]
                else:
                    data = data[part]
            price = float(data)
            if not (SANITY_MIN < price < SANITY_MAX):
                return None
            return price
        except Exception as e:
            log.debug(f"source={self.name} failed: {e}")
            return None


BUILTIN_SOURCES = {
    "coinex": lambda: PriceSource("coinex", "https://api.coinex.com/v2/spot/ticker",
                                  {"market": "XELUSDT"}, "data.0.last"),
    "mexc": lambda: PriceSource("mexc", "https://api.mexc.com/api/v3/ticker/price",
                                {"symbol": "XELUSDT"}, "price"),
    "bitget": lambda: PriceSource("bitget", "https://api.bitget.com/api/v2/spot/market/tickers",
                                  {"symbol": "XELUSDT"}, "data.0.lastPr"),
    "gate": lambda: PriceSource("gate", "https://api.gateio.ws/api/v4/spot/tickers",
                                {"currency_pair": "XEL_USDT"}, "0.last"),
}


def fetch_prices(sources: list[str]) -> list[tuple[str, float]]:
    out = []
    for key in sources:
        builder = BUILTIN_SOURCES.get(key)
        if not builder:
            continue
        price = builder().fetch()
        if price is not None:
            out.append((key, price))
            log.info(f"source={key:<8} price={price:.6f}")
    return out


def median_price(prices: list[tuple[str, float]]) -> Optional[tuple[float, list[str]]]:
    if len(prices) < MIN_SOURCES:
        return None
    vals = [p for _, p in prices]
    med = statistics.median(vals)
    valid = [name for name, p in prices if abs(p - med) / med <= OUTLIER_PCT]
    if len(valid) < MIN_SOURCES:
        return None
    valid_vals = [p for n, p in prices if n in valid]
    return statistics.median(valid_vals), valid


def main() -> None:
    parser = argparse.ArgumentParser(description="XELIS Vault Price Provider")
    parser.add_argument("--wallet-rpc", default="http://127.0.0.1:18084/json_rpc")
    parser.add_argument("--daemon-rpc", default="http://127.0.0.1:18081/json_rpc")
    parser.add_argument("--auth", default="wallet:testpass",
                        help="wallet basic auth user:pass")
    parser.add_argument("--feed-id", type=int, default=FEED_XEL_USD)
    parser.add_argument("--interval", type=int, default=DEFAULT_INTERVAL)
    parser.add_argument("--sources", default="coinex,mexc,bitget,gate",
                        help="comma-separated source keys to use")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    global log
    log = setup_logging(args.verbose)

    user, sep, pwd = args.auth.partition(":")
    p = Protocol(
        wallet_url=args.wallet_rpc,
        wallet_auth=(user, pwd),
        daemon_url=args.daemon_rpc,
    )
    source_keys = [s.strip() for s in args.sources.split(",") if s.strip()]

    log.info("=" * 60)
    log.info("XELIS Vault Price Provider")
    log.info(f"  wallet RPC:  {args.wallet_rpc}")
    log.info(f"  daemon RPC:  {args.daemon_rpc}")
    log.info(f"  feed id:     {args.feed_id}")
    log.info(f"  sources:     {source_keys}")
    log.info(f"  interval:    {args.interval}s")
    log.info("=" * 60)

    addr = p.wallet.address()
    log.info(f"provider address: {addr}")

    running = True

    def handler(signum, frame):
        nonlocal running
        running = False
    signal.signal(signal.SIGINT, handler)
    signal.signal(signal.SIGTERM, handler)

    while running:
        try:
            prices = fetch_prices(source_keys)
            result = median_price(prices)
            if result is None:
                log.warning(f"insufficient valid prices ({len(prices)} samples)")
            else:
                med, valid = result
                decimals = FEED_DECIMALS.get(args.feed_id, 8)
                price_atomic = int(round(med * 10 ** decimals))
                if args.dry_run:
                    log.info(f"[DRY-RUN] would submit feed={args.feed_id} "
                             f"price={med:.6f} ({price_atomic} atomic)")
                else:
                    try:
                        tx = oracle_submit_price(p, price_atomic, args.feed_id)
                        log.info(f"submitted feed={args.feed_id} "
                                 f"price={med:.6f} ({price_atomic}) tx={tx[:32]}")
                    except Exception as e:
                        msg = str(e).lower()
                        if "alreadysub" in msg:
                            log.debug("already submitted this cycle")
                        elif "notminer" in msg:
                            log.error("caller is not a registered oracle miner")
                            log.error("run: xvault-miner register --wallet-rpc <url>")
                            running = False
                        elif "oorange" in msg:
                            log.warning("price out of feed range")
                        elif "cbpaused" in msg:
                            log.warning("feed circuit breaker paused")
                        elif "paused" in msg:
                            log.warning("oracle paused")
                        else:
                            log.error(f"submit_price failed: {e}")
                            if hasattr(e, "__cause__"):
                                log.debug(f"cause: {e.__cause__}")
        except Exception as e:
            log.error(f"loop error: {e}")
        time.sleep(args.interval)

    log.info("provider stopped")


if __name__ == "__main__":
    main()