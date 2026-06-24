#!/usr/bin/env python3
"""
============================================================================
 XELIS Vault v5.0 — Aggregation Keeper (aggregation_keeper.py)
============================================================================

Long-running daemon that calls StakedOracle.aggregate_now(feed_id)
(entry ID 6) for each configured feed every 25 seconds.

Why?  Aggregation is triggered inside submit_price() IF the cycle has
elapsed. But if no provider submits for N blocks, aggregation never
runs and the on-chain price becomes stale. This keeper guarantees
timely aggregation — anyone can run it, no VLT stake needed.

PRIVACY:
  - Only logs public on-chain data (topoheight, cycle number, submission
    counts).
  - NEVER logs wallet private keys, mnemonics, balances, or IP addresses.

CLI:
  python3 aggregation_keeper.py --feed-ids 0,1,2 --interval 25 \\
      --rpc http://localhost:8080 [--dry-run] [--verbose]
"""
from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import time
from pathlib import Path
from typing import Any, Optional

try:
    import requests
except ImportError:
    print("ERROR: 'requests' is not installed. Run install.py first:",
          file=sys.stderr)
    sys.exit(1)

# ============================================================================
# CONSTANTS — v5.0 entry IDs
# ============================================================================
# StakedOracle entry IDs (only the ones we use)
ORACLE_SUBMIT_PRICE            = 5
ORACLE_AGGREGATE_NOW           = 6   # (feed_id)   ← used here
ORACLE_GET_PRICE_BY_FEED       = 7   # (feed_id) -> u64

# Defaults
DEFAULT_RPC = "http://127.0.0.1:8080"
DEFAULT_INTERVAL = 25           # seconds (~5 blocks)
DEFAULT_FEED_IDS = "0"
STUCK_CYCLE_THRESHOLD_SEC = 300 # 5 minutes — alert if cycle doesn't advance
VAULT_DIR = Path.home() / ".xelis-vault"
LOG_DIR   = VAULT_DIR / "logs"
LOG_FILE  = LOG_DIR / "keeper.log"

# ============================================================================
# LOGGING
# ============================================================================
def setup_logging(verbose: bool = False) -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("keeper")
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


log = logging.getLogger("keeper")

# ============================================================================
# XELIS CLIENT
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

    def is_synced(self) -> bool:
        info = self._call("get_info")
        return bool(info.get("synced", False))

    def aggregate_now(self, oracle_contract: str, feed_id: int,
                      signer: str = "default") -> str:
        """Call StakedOracle.aggregate_now(feed_id) — entry ID 6."""
        result = self._call("submit_transaction", {
            "tx_type": "CallContract",
            "contract": oracle_contract,
            "entry_id": ORACLE_AGGREGATE_NOW,
            "args": [str(feed_id)],
            "signer": signer,
        })
        tx_hash = result.get("hash") if isinstance(result, dict) else None
        if not tx_hash:
            raise RuntimeError(f"aggregate_now returned no hash: {result}")
        return tx_hash

    def read_price(self, oracle_contract: str, feed_id: int) -> int:
        """Call StakedOracle.get_price_by_feed_entry(feed_id) — entry ID 7."""
        try:
            result = self._call("call_contract_read", {
                "contract": oracle_contract,
                "entry_id": ORACLE_GET_PRICE_BY_FEED,
                "args": [str(feed_id)],
            })
            return int(result) if result else 0
        except Exception as e:
            log.debug(f"read_price failed for feed {feed_id}: {e}")
            return 0

    def get_cycle(self, oracle_contract: str, feed_id: int) -> int:
        """Best-effort read of the current cycle. Falls back to 0 on error."""
        try:
            # The cycle isn't exposed as an entry ID in v5.0 (it's a pub fn);
            # we approximate progress by tracking the on-chain price changes.
            # If your daemon supports the named call, this returns the cycle.
            result = self._call("call_contract_read", {
                "contract": oracle_contract,
                "entry": "get_cycle",
                "args": [str(feed_id)],
            })
            return int(result) if result else 0
        except Exception:
            return 0


# ============================================================================
# KEEPER
# ============================================================================
class AggregationKeeper:
    def __init__(
        self,
        client: XelisClient,
        oracle_contract: str,
        feed_ids: list[int],
        interval: int = DEFAULT_INTERVAL,
        dry_run: bool = False,
    ) -> None:
        self.client = client
        self.oracle_contract = oracle_contract
        self.feed_ids = feed_ids
        self.interval = interval
        self.dry_run = dry_run
        self.running = True
        # Per-feed stuck-cycle tracking
        self.last_cycle: dict[int, int] = {fid: 0 for fid in feed_ids}
        self.last_cycle_change: dict[int, float] = {fid: 0.0 for fid in feed_ids}
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

    def aggregate_one(self, feed_id: int) -> None:
        """Trigger aggregation for a single feed and log progress."""
        topo = 0
        try:
            topo = self.client.get_topoheight()
        except Exception:
            pass
        if self.dry_run:
            log.info(f"[DRY-RUN] would call aggregate_now(feed_id={feed_id}) "
                     f"at topo={topo}")
            return
        try:
            tx = self.client.aggregate_now(self.oracle_contract, feed_id)
            # Read the current on-chain price for context (public data only)
            price_atomic = self.client.read_price(self.oracle_contract, feed_id)
            price = price_atomic / 1e8 if price_atomic else 0.0
            log.info(
                f"Aggregated feed {feed_id} at topo {topo}  "
                f"price={price:.6f}  tx={tx}"
            )
        except Exception as e:
            msg = str(e).lower()
            if "alreadyaggreg" in msg or "toosoon" in msg:
                log.debug(f"aggregate_now({feed_id}) already done this cycle")
            elif "paused" in msg:
                log.warning(f"StakedOracle paused — skipping feed {feed_id}")
            else:
                log.error(f"aggregate_now({feed_id}) failed: {e}")

    def check_stuck_cycles(self) -> None:
        """Alert if any feed's cycle hasn't advanced in 5 minutes."""
        now = time.time()
        for fid in self.feed_ids:
            cycle = self.client.get_cycle(self.oracle_contract, fid)
            if cycle != self.last_cycle[fid]:
                self.last_cycle[fid] = cycle
                self.last_cycle_change[fid] = now
                continue
            # Cycle hasn't changed
            last_change = self.last_cycle_change[fid]
            if last_change == 0:
                self.last_cycle_change[fid] = now
                continue
            stuck_for = now - last_change
            if stuck_for > STUCK_CYCLE_THRESHOLD_SEC:
                log.warning(
                    f"Feed {fid} cycle stuck at {cycle} for "
                    f"{int(stuck_for)}s — check providers"
                )

    def run(self) -> None:
        log.info("=" * 60)
        log.info("XELIS Vault v5.0 Aggregation Keeper")
        log.info("=" * 60)
        log.info(f"  Oracle contract: {self.oracle_contract}")
        log.info(f"  RPC URL:         {self.client.rpc_url}")
        log.info(f"  Feed IDs:        {self.feed_ids}")
        log.info(f"  Interval:        {self.interval}s")
        log.info(f"  Dry run:         {self.dry_run}")
        log.info("=" * 60)

        if not self.client.is_synced():
            log.warning("Daemon not synced — continuing anyway")

        while self.running:
            try:
                topo = self.client.get_topoheight()
                log.debug(f"Topoheight={topo}")
                for fid in self.feed_ids:
                    self.aggregate_one(fid)
                self.check_stuck_cycles()
            except KeyboardInterrupt:
                break
            except Exception as e:
                log.error(f"Main loop error: {e}")
            # Sleep in small increments so SIGINT is responsive
            slept = 0
            while slept < self.interval and self.running:
                time.sleep(1)
                slept += 1

        log.info("Aggregation keeper stopped — goodbye")


# ============================================================================
# CLI
# ============================================================================
def parse_feed_ids(s: str) -> list[int]:
    ids: list[int] = []
    for part in s.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ids.append(int(part))
        except ValueError:
            log.error(f"Invalid feed ID: {part!r}")
            sys.exit(1)
    if not ids:
        log.error("No feed IDs provided")
        sys.exit(1)
    return ids


def main() -> None:
    parser = argparse.ArgumentParser(
        description="XELIS Vault v5.0 Aggregation Keeper"
    )
    parser.add_argument("--feed-ids", default=DEFAULT_FEED_IDS,
                        help=f"Comma-separated feed IDs (default: "
                             f"{DEFAULT_FEED_IDS})")
    parser.add_argument("--interval", type=int, default=DEFAULT_INTERVAL,
                        help=f"Seconds between aggregate calls (default: "
                             f"{DEFAULT_INTERVAL})")
    parser.add_argument("--rpc", default=DEFAULT_RPC,
                        help=f"XELIS daemon JSON-RPC URL (default: "
                             f"{DEFAULT_RPC})")
    parser.add_argument("--oracle", default=os.environ.get(
                            "STAKED_ORACLE_CONTRACT", ""),
                        help="StakedOracle contract hash "
                             "(or env STAKED_ORACLE_CONTRACT)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Don't submit txs, just log what would happen")
    parser.add_argument("--verbose", action="store_true",
                        help="DEBUG-level logging")
    args = parser.parse_args()

    global log
    log = setup_logging(verbose=args.verbose)

    feed_ids = parse_feed_ids(args.feed_ids)
    if not args.oracle:
        log.error("StakedOracle contract hash required "
                  "(--oracle or STAKED_ORACLE_CONTRACT env var)")
        sys.exit(1)

    client = XelisClient(args.rpc)
    keeper = AggregationKeeper(
        client=client,
        oracle_contract=args.oracle,
        feed_ids=feed_ids,
        interval=args.interval,
        dry_run=args.dry_run,
    )
    keeper.run()


if __name__ == "__main__":
    main()
