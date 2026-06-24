#!/usr/bin/env python3
"""
============================================================================
 XELIS Vault v5.0 — Price Provider (price_provider.py)
============================================================================

Long-running daemon that:

  1. Loads sources from ~/.xelis-vault/config/custom_sources.json
  2. Polls each enabled source every 5 seconds (configurable per-source)
  3. For each enabled feed (XEL/USD, XEL/BTC, ...):
       a. Collects prices from all sources
       b. Rejects prices >5 % from the median (outlier)
       c. Rejects prices older than 30 s (stale)
       d. Computes the median of remaining valid prices
       e. Calls StakedOracle.submit_price(feed_id, price) (entry ID 5)
          via XELIS RPC

PRIVACY:
  - NEVER logs source API keys. Only source name + price + timestamp.
  - NEVER logs the wallet private key or mnemonic.
  - NEVER logs the IP addresses of other miners.
  - DOES log block heights, topoheights, price submission confirmations,
    reward amounts (public on-chain), error messages (without sensitive
    context).

CLI:
  python3 price_provider.py --config ~/.xelis-vault/config/custom_sources.json \\
      --feed-id 0 \\
      [--dry-run] [--verbose]
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import statistics
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

try:
    import requests
except ImportError:
    print("ERROR: 'requests' is not installed. Run install.py first:",
          file=sys.stderr)
    sys.exit(1)

# ============================================================================
# CONSTANTS — v5.0 entry IDs (canonical, see docs/ENTRY_IDS.md)
# ============================================================================
# StakedOracle entry IDs
ORACLE_ADD_FEED                = 0
ORACLE_UPDATE_FEED             = 1
ORACLE_SET_FEED_ACTIVE         = 2
ORACLE_TRIGGER_FEED_CB         = 3
ORACLE_RESET_FEED_CB           = 4
ORACLE_SUBMIT_PRICE            = 5   # (feed_id, price)   ← used here
ORACLE_AGGREGATE_NOW           = 6   # (feed_id)          ← used by keeper
ORACLE_GET_PRICE_BY_FEED       = 7
ORACLE_GET_PRICE               = 8   # (name) -> u64
ORACLE_GET_PRICE_FOR_ASSET     = 9   # (asset) -> u64
ORACLE_GET_FEED_ID             = 10  # (name) -> u64
ORACLE_PAUSE                   = 11
ORACLE_UNPAUSE                 = 12
ORACLE_SET_MAX_DEVIATION_BPS   = 13
ORACLE_SET_CB_THRESHOLD_BPS    = 14
ORACLE_SET_AGGREGATION_BLOCKS  = 15
ORACLE_SET_MAX_STALE_BLOCKS    = 16
ORACLE_SET_HARD_STALE_BLOCKS   = 17
ORACLE_DISABLE_BOOTSTRAP       = 18
ORACLE_SET_BOOTSTRAP_MIN_PROVIDERS = 19
ORACLE_SET_MIN_PROVIDERS       = 20
ORACLE_SET_MINER_CONTRACT      = 21
ORACLE_SET_REGISTRY            = 22
ORACLE_SET_TIMELOCK            = 23
ORACLE_SET_GUARDIAN            = 24
ORACLE_SET_EMERGENCY           = 25
ORACLE_TRANSFER_ADMIN          = 26
ORACLE_GET_VERSION             = 27

# Defaults
VAULT_DIR     = Path.home() / ".xelis-vault"
DEFAULT_CONFIG = VAULT_DIR / "config" / "custom_sources.json"
DEFAULT_RPC    = "http://127.0.0.1:8080"
LOG_DIR        = VAULT_DIR / "logs"
LOG_FILE       = LOG_DIR / "provider.log"

POLL_INTERVAL_DEFAULT = 5          # seconds
SUBMIT_INTERVAL_DEFAULT = 20       # seconds — must be < 25 s (1 cycle)
OUTLIER_THRESHOLD_PCT = 0.05       # 5 % — match on-chain oracle
STALE_THRESHOLD_SECONDS = 30       # reject prices older than 30 s
SANITY_MIN_PRICE = 0.001           # USD
SANITY_MAX_PRICE = 10_000.0        # USD
MIN_SOURCES_REQUIRED = 2
MAX_WORKERS_DEFAULT = 8

# ============================================================================
# LOGGING
# ============================================================================
def setup_logging(verbose: bool = False) -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("provider")
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    logger.propagate = False
    if logger.handlers:
        return logger
    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    try:
        from logging.handlers import RotatingFileHandler
        fh = RotatingFileHandler(
            LOG_FILE, maxBytes=100 * 1024 * 1024, backupCount=5
        )
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    except Exception:
        pass
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(sh)
    return logger


log = logging.getLogger("provider")


# ============================================================================
# DATA STRUCTURES
# ============================================================================
@dataclass
class PriceSample:
    source: str
    price: float
    timestamp: float        # epoch seconds
    latency_ms: int


@dataclass
class Feed:
    feed_id: int
    name: str
    asset_hash: str
    decimals: int = 8


# ============================================================================
# PRICE SOURCE INTERFACES
# ============================================================================
class PriceSource:
    """Base class — each source implements fetch_price(symbol) -> PriceSample."""

    def __init__(self, name: str, cfg: dict) -> None:
        self.name = name
        self.cfg = cfg
        self.poll_interval = int(cfg.get("poll_interval_seconds",
                                         POLL_INTERVAL_DEFAULT))
        self.last_fetch: float = 0.0
        self.last_sample: Optional[PriceSample] = None

    def fetch_price(self, symbol: str) -> Optional[PriceSample]:
        raise NotImplementedError

    def maybe_fetch(self, symbol: str) -> Optional[PriceSample]:
        now = time.time()
        if now - self.last_fetch < self.poll_interval:
            return self.last_sample
        self.last_fetch = now
        try:
            sample = self.fetch_price(symbol)
        except Exception as e:
            log.debug(f"source={self.name} fetch failed: {e}")
            sample = None
        self.last_sample = sample
        return sample


class HttpPriceSource(PriceSource):
    """Generic HTTP source: GET url → walk json_path → float."""

    def __init__(self, name: str, cfg: dict) -> None:
        super().__init__(name, cfg)
        self.url = cfg["url"]
        self.params = cfg.get("params", {})
        self.headers = cfg.get("headers", {})
        self.json_path = cfg.get("json_path", "price")
        self.timeout = int(cfg.get("timeout", 10))

    def fetch_price(self, symbol: str) -> Optional[PriceSample]:
        t0 = time.time()
        r = requests.get(
            self.url,
            params=self.params,
            headers=self.headers,
            timeout=self.timeout,
        )
        r.raise_for_status()
        data = r.json()
        # Walk the dot-separated json_path
        price = data
        for part in self.json_path.split("."):
            if part.isdigit():
                price = price[int(part)]
            else:
                price = price[part]
        price = float(price)
        latency_ms = int((time.time() - t0) * 1000)
        if not (SANITY_MIN_PRICE < price < SANITY_MAX_PRICE):
            log.warning(f"source={self.name} out-of-sanity price={price}")
            return None
        return PriceSample(
            source=self.name,
            price=price,
            timestamp=time.time(),
            latency_ms=latency_ms,
        )


class CoinExSource(HttpPriceSource):
    """Built-in CoinEx source."""

    def __init__(self, name: str, cfg: dict) -> None:
        merged = {
            "url": "https://api.coinex.com/v2/spot/ticker",
            "params": {"market": "XELUSDT"},
            "json_path": "data.0.last",
            "timeout": 10,
            **cfg,
        }
        super().__init__(name, merged)


class MEXCSource(HttpPriceSource):
    """Built-in MEXC source."""

    def __init__(self, name: str, cfg: dict) -> None:
        merged = {
            "url": "https://api.mexc.com/api/v3/ticker/price",
            "params": {"symbol": "XELUSDT"},
            "json_path": "price",
            "timeout": 10,
            **cfg,
        }
        super().__init__(name, merged)


class DaemonSource(PriceSource):
    """Reads the implied XEL/USD price from the local XELIS daemon."""

    def __init__(self, name: str, cfg: dict) -> None:
        super().__init__(name, cfg)
        self.rpc_url = cfg.get("rpc_url", DEFAULT_RPC)

    def fetch_price(self, symbol: str) -> Optional[PriceSample]:
        # The daemon doesn't expose a direct USD price — this source is a
        # placeholder for users who want to derive one from the on-chain
        # DEX pool (XEL/xUSD). In production, replace this with a real
        # derivation.
        t0 = time.time()
        try:
            payload = {
                "method": "get_info",
                "params": {},
                "jsonrpc": "2.0",
                "id": 1,
            }
            r = requests.post(self.rpc_url, json=payload, timeout=10)
            r.raise_for_status()
            info = r.json().get("result", {})
            # Placeholder: in a real deployment you would query a XEL/xUSD
            # pool on VaultSwap and compute the implied price.
            # For now we just return None to indicate "no native price".
            log.debug(f"source=daemon fetched info, topoheight="
                      f"{info.get('topoheight')}")
            latency_ms = int((time.time() - t0) * 1000)
            # NOTE: To enable, implement the pool-price derivation here and
            # return a real PriceSample.
            _ = latency_ms
            return None
        except Exception as e:
            log.debug(f"source=daemon fetch failed: {e}")
            return None


class CommandSource(PriceSource):
    """Runs an external command and parses stdout as JSON with a `price`."""

    def __init__(self, name: str, cfg: dict) -> None:
        super().__init__(name, cfg)
        self.command = cfg["command"]
        self.args = cfg.get("args", [])
        self.timeout = int(cfg.get("timeout", 15))

    def fetch_price(self, symbol: str) -> Optional[PriceSample]:
        t0 = time.time()
        try:
            result = subprocess.run(
                [self.command, *self.args],
                capture_output=True,
                timeout=self.timeout,
                text=True,
            )
            if result.returncode != 0:
                log.debug(f"source={self.name} command exited "
                          f"{result.returncode}: {result.stderr[:200]}")
                return None
            data = json.loads(result.stdout)
            price = float(data["price"])
            latency_ms = int((time.time() - t0) * 1000)
            if not (SANITY_MIN_PRICE < price < SANITY_MAX_PRICE):
                log.warning(f"source={self.name} out-of-sanity price={price}")
                return None
            return PriceSample(
                source=self.name,
                price=price,
                timestamp=time.time(),
                latency_ms=latency_ms,
            )
        except Exception as e:
            log.debug(f"source={self.name} fetch failed: {e}")
            return None


# ============================================================================
# SOURCE FACTORY
# ============================================================================
def build_source(cfg: dict) -> Optional[PriceSource]:
    """Build a PriceSource from a config dict, or None if disabled."""
    if not cfg.get("enabled", True):
        return None
    name = cfg.get("name", "unknown")
    stype = cfg.get("type", "http").lower()
    if stype == "coinex":
        return CoinExSource(name, cfg)
    if stype == "mexc":
        return MEXCSource(name, cfg)
    if stype == "http":
        return HttpPriceSource(name, cfg)
    if stype == "daemon":
        return DaemonSource(name, cfg)
    if stype == "command":
        return CommandSource(name, cfg)
    log.warning(f"Unknown source type={stype} for source={name} — skipping")
    return None


def load_sources(path: Path) -> list[PriceSource]:
    if not path.exists():
        log.error(f"Config file not found: {path}")
        log.error("Run install.py first, or pass --config /path/to/file")
        sys.exit(1)
    try:
        raw = json.loads(path.read_text())
    except Exception as e:
        log.error(f"Could not parse {path}: {e}")
        sys.exit(1)
    # The file may be either {"sources": [...]} or a top-level list.
    sources_list = raw.get("sources", raw) if isinstance(raw, dict) else raw
    sources: list[PriceSource] = []
    for entry in sources_list:
        try:
            src = build_source(entry)
            if src is not None:
                sources.append(src)
                log.debug(f"Loaded source: {src.name} "
                          f"(type={entry.get('type')}, "
                          f"interval={src.poll_interval}s)")
        except Exception as e:
            # Don't log the full entry — may contain API keys
            log.warning(f"Failed to build source={entry.get('name')}: {e}")
    return sources


# ============================================================================
# AGGREGATION
# ============================================================================
def aggregate(
    samples: list[PriceSample],
    outlier_pct: float = OUTLIER_THRESHOLD_PCT,
    stale_seconds: float = STALE_THRESHOLD_SECONDS,
) -> tuple[Optional[float], list[str], list[str]]:
    """Returns (median, valid_sources, rejected_sources)."""
    now = time.time()
    # Stale check
    fresh = [s for s in samples if now - s.timestamp <= stale_seconds]
    stale_names = [s.source for s in samples if now - s.timestamp > stale_seconds]
    if len(fresh) < MIN_SOURCES_REQUIRED:
        return None, [], [s.source for s in samples]
    # Compute median of fresh samples
    prices = [s.price for s in fresh]
    median = statistics.median(prices)
    # Outlier check
    valid: list[str] = []
    rejected: list[str] = list(stale_names)
    for s in fresh:
        if median > 0:
            deviation = abs(s.price - median) / median
            if deviation > outlier_pct:
                rejected.append(s.source)
                log.debug(f"source={s.source} price={s.price} rejected "
                          f"(deviation={deviation:.2%} > {outlier_pct:.2%})")
                continue
        valid.append(s.source)
    if len(valid) < MIN_SOURCES_REQUIRED:
        return None, [], rejected
    # Recompute median of valid samples only
    valid_samples = [s for s in fresh if s.source in valid]
    median = statistics.median([s.price for s in valid_samples])
    return median, valid, rejected


# ============================================================================
# XELIS CLIENT (subset needed for submit_price)
# ============================================================================
class XelisClient:
    def __init__(self, rpc_url: str) -> None:
        self.rpc_url = rpc_url
        self._id = 0

    def _call(self, method: str, params: Optional[dict] = None) -> Any:
        self._id += 1
        payload = {
            "method": method,
            "params": params or {},
            "jsonrpc": "2.0",
            "id": self._id,
        }
        r = requests.post(self.rpc_url, json=payload, timeout=30)
        r.raise_for_status()
        data = r.json()
        if "error" in data and data["error"]:
            raise RuntimeError(f"RPC error: {data['error']}")
        return data.get("result", {})

    def get_topoheight(self) -> int:
        return int(self._call("get_topoheight"))

    def submit_price(self, oracle_contract: str, feed_id: int,
                     price_atomic: int, signer: str = "default") -> str:
        """Call StakedOracle.submit_price(feed_id, price) — entry ID 5."""
        result = self._call("submit_transaction", {
            "tx_type": "CallContract",
            "contract": oracle_contract,
            "entry_id": ORACLE_SUBMIT_PRICE,
            "args": [str(feed_id), str(price_atomic)],
            "signer": signer,
        })
        tx_hash = result.get("hash") if isinstance(result, dict) else None
        if not tx_hash:
            raise RuntimeError(f"submit_price returned no hash: {result}")
        return tx_hash

    def get_feed_id(self, oracle_contract: str, name: str) -> int:
        try:
            result = self._call("call_contract_read", {
                "contract": oracle_contract,
                "entry_id": ORACLE_GET_FEED_ID,
                "args": [name],
            })
            return int(result)
        except Exception as e:
            log.debug(f"Could not resolve feed_id for {name}: {e}")
            return -1


# ============================================================================
# PROVIDER DAEMON
# ============================================================================
class ProviderDaemon:
    def __init__(
        self,
        sources: list[PriceSource],
        client: XelisClient,
        oracle_contract: str,
        feed: Feed,
        submit_interval: int = SUBMIT_INTERVAL_DEFAULT,
        dry_run: bool = False,
        max_workers: int = MAX_WORKERS_DEFAULT,
    ) -> None:
        self.sources = sources
        self.client = client
        self.oracle_contract = oracle_contract
        self.feed = feed
        self.submit_interval = submit_interval
        self.dry_run = dry_run
        self.max_workers = max_workers
        self.running = True
        self._register_signals()

    def _register_signals(self) -> None:
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                signal.signal(sig, self._handle_signal)
            except (ValueError, OSError):
                pass

    def _handle_signal(self, signum, frame) -> None:
        log.info(f"Received signal {signum} — shutting down")
        self.running = False

    def collect_samples(self, symbol: str) -> list[PriceSample]:
        samples: list[PriceSample] = []
        for src in self.sources:
            sample = src.maybe_fetch(symbol)
            if sample is not None:
                log.info(f"source={src.name:<15} price={sample.price:.6f} "
                         f"latency={sample.latency_ms}ms")
                samples.append(sample)
            else:
                log.debug(f"source={src.name:<15} no sample")
        return samples

    def submit(self, price_usd: float, valid: list[str],
               rejected: list[str]) -> None:
        # Convert to atomic (8 decimals for XEL/USD feed)
        price_atomic = int(round(price_usd * 10 ** self.feed.decimals))
        topo = 0
        try:
            topo = self.client.get_topoheight()
        except Exception:
            pass
        log.info(
            f"median={price_usd:.6f}  valid={valid}  rejected={rejected}  "
            f"topo={topo}"
        )
        if self.dry_run:
            log.info(f"[DRY-RUN] would call submit_price(feed_id="
                     f"{self.feed.feed_id}, price_atomic={price_atomic})")
            return
        try:
            tx = self.client.submit_price(
                self.oracle_contract, self.feed.feed_id, price_atomic
            )
            log.info(f"submit_price feed_id={self.feed.feed_id} "
                     f"price_atomic={price_atomic}  tx={tx}")
        except Exception as e:
            msg = str(e).lower()
            if "alreadysub" in msg:
                log.debug("Already submitted this cycle — skipping")
            elif "notreg" in msg:
                log.error("Wallet not registered as miner — call "
                          "XelisVaultMiner.register_miner (entry ID 0) first")
                self.running = False
            elif "oorange" in msg:
                log.warning(f"submit_price rejected: price out of feed range. "
                            f"Check sources: {valid}")
            elif "paused" in msg:
                log.warning("StakedOracle is paused — skipping submission")
            else:
                log.error(f"submit_price failed: {e}")

    def run(self) -> None:
        log.info("=" * 60)
        log.info("XELIS Vault v5.0 Price Provider")
        log.info("=" * 60)
        log.info(f"  Oracle contract: {self.oracle_contract}")
        log.info(f"  Feed:            {self.feed.name} (id={self.feed.feed_id}, "
                 f"decimals={self.feed.decimals})")
        log.info(f"  RPC URL:         {self.client.rpc_url}")
        log.info(f"  Submit interval: {self.submit_interval}s")
        log.info(f"  Sources:         {[s.name for s in self.sources]}")
        log.info(f"  Dry run:         {self.dry_run}")
        log.info("=" * 60)
        last_submit = 0.0
        while self.running:
            try:
                samples = self.collect_samples(self.feed.name)
                if len(samples) < MIN_SOURCES_REQUIRED:
                    log.warning(f"Only {len(samples)} source(s) responded — "
                                f"need >= {MIN_SOURCES_REQUIRED}, skipping "
                                f"this cycle")
                else:
                    median, valid, rejected = aggregate(samples)
                    now = time.time()
                    if median is None:
                        log.warning(f"No valid median after filtering — "
                                    f"rejected={rejected}")
                    elif now - last_submit >= self.submit_interval:
                        self.submit(median, valid, rejected)
                        last_submit = now
                time.sleep(1)  # tight poll — sources throttle themselves
            except KeyboardInterrupt:
                break
            except Exception as e:
                log.error(f"Main loop error: {e}")
                time.sleep(5)
        log.info("Price provider stopped — goodbye")


# ============================================================================
# CLI
# ============================================================================
def main() -> None:
    parser = argparse.ArgumentParser(
        description="XELIS Vault v5.0 Price Provider"
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG,
                        help=f"Sources config (default: {DEFAULT_CONFIG})")
    parser.add_argument("--rpc", default=DEFAULT_RPC,
                        help=f"XELIS daemon JSON-RPC URL (default: {DEFAULT_RPC})")
    parser.add_argument("--oracle", default=os.environ.get("STAKED_ORACLE_CONTRACT", ""),
                        help="StakedOracle contract hash "
                             "(or env STAKED_ORACLE_CONTRACT)")
    parser.add_argument("--feed-id", type=int, default=0,
                        help="Feed ID to submit prices for (default: 0)")
    parser.add_argument("--feed-name", default="XEL/USD",
                        help="Feed name (for logging)")
    parser.add_argument("--feed-asset", default="0" * 64,
                        help="Feed asset hash (default: zero = native XEL)")
    parser.add_argument("--feed-decimals", type=int, default=8,
                        help="Feed decimals (default: 8)")
    parser.add_argument("--submit-interval", type=int,
                        default=SUBMIT_INTERVAL_DEFAULT,
                        help=f"Submit interval in seconds "
                             f"(default: {SUBMIT_INTERVAL_DEFAULT})")
    parser.add_argument("--max-workers", type=int, default=MAX_WORKERS_DEFAULT,
                        help=f"Thread pool size for source polling "
                             f"(default: {MAX_WORKERS_DEFAULT})")
    parser.add_argument("--dry-run", action="store_true",
                        help="Don't submit txs, just log what would happen")
    parser.add_argument("--verbose", action="store_true",
                        help="DEBUG-level logging")
    args = parser.parse_args()

    global log
    log = setup_logging(verbose=args.verbose)

    sources = load_sources(args.config)
    if not sources:
        log.error("No enabled sources in config — nothing to do")
        sys.exit(1)
    log.info(f"Loaded {len(sources)} enabled source(s)")

    if not args.oracle:
        log.error("StakedOracle contract hash required "
                  "(--oracle or STAKED_ORACLE_CONTRACT env var)")
        sys.exit(1)

    client = XelisClient(args.rpc)
    feed = Feed(
        feed_id=args.feed_id,
        name=args.feed_name,
        asset_hash=args.feed_asset,
        decimals=args.feed_decimals,
    )
    daemon = ProviderDaemon(
        sources=sources,
        client=client,
        oracle_contract=args.oracle,
        feed=feed,
        submit_interval=args.submit_interval,
        dry_run=args.dry_run,
        max_workers=args.max_workers,
    )
    daemon.run()


if __name__ == "__main__":
    main()
