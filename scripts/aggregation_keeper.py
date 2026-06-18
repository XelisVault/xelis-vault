#!/usr/bin/env python3
"""
Aggregation Keeper — XELIS Vault v4

Bot that calls StakedOracle.aggregate_now(feed_id) on every block to
ensure aggregation triggers even if no one submits a price in the
current window.

Why? Aggregation is triggered inside submit_price() IF the cycle has
elapsed. But if no provider submits for N blocks, aggregation never
runs and the price becomes stale. This keeper guarantees timely
aggregation.

Run on any server (ideally the team + 1-2 community members for
redundancy). No VLT stake needed — anyone can call aggregate_now().

    python3 aggregation_keeper.py
"""
import os
import sys
import time
import logging
import requests

XELIS_DAEMON_RPC = os.environ.get("XELIS_RPC", "http://127.0.0.1:8080")
STAKED_ORACLE_CONTRACT = os.environ.get("STAKED_ORACLE_CONTRACT", "")
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "5"))  # 5s = 1 block
FEEDS_TO_KEEP = os.environ.get("FEEDS_TO_KEEP", "XEL/USD").split(",")

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
log = logging.getLogger("aggregation-keeper")


class XelisDaemon:
    def __init__(self, rpc: str):
        self.rpc = rpc
        self._id = 0

    def _call(self, method: str, params: dict = None) -> dict:
        self._id += 1
        payload = {
            "method": method,
            "params": params or {},
            "jsonrpc": "2.0",
            "id": self._id,
        }
        r = requests.post(self.rpc, json=payload, timeout=15)
        r.raise_for_status()
        data = r.json()
        if "error" in data:
            raise RuntimeError(f"XELIS RPC error: {data['error']}")
        return data.get("result", {})

    def get_topoheight(self) -> int:
        return int(self._call("get_topoheight"))

    def resolve_feed_id(self, oracle_contract: str, feed_name: str) -> int:
        """Resolve a feed's numeric ID from its name."""
        try:
            result = self._call("call_contract_read", {
                "contract": oracle_contract,
                "entry": "get_feed_id",
                "args": [feed_name],
            })
            return int(result)
        except Exception as e:
            log.error(f"Could not resolve feed_id for {feed_name}: {e}")
            return -1

    def aggregate_now(self, oracle_contract: str, feed_id: int) -> bool:
        """Call StakedOracle.aggregate_now(feed_id)."""
        try:
            self._call("submit_transaction", {
                "tx_type": "CallContract",
                "contract": oracle_contract,
                "entry": "aggregate_now",
                "args": [str(feed_id)],
            })
            return True
        except Exception as e:
            log.debug(f"aggregate_now({feed_id}) failed: {e}")
            return False


def main():
    if not STAKED_ORACLE_CONTRACT:
        log.error("Missing STAKED_ORACLE_CONTRACT env var")
        sys.exit(1)

    daemon = XelisDaemon(XELIS_DAEMON_RPC)

    log.info("=" * 60)
    log.info("XELIS Vault v4 - Aggregation Keeper")
    log.info("=" * 60)
    log.info(f"  Oracle:  {STAKED_ORACLE_CONTRACT}")
    log.info(f"  RPC:     {XELIS_DAEMON_RPC}")
    log.info(f"  Feeds:   {FEEDS_TO_KEEP}")
    log.info(f"  Interval: {POLL_INTERVAL}s")
    log.info("=" * 60)

    # Resolve feed IDs on startup
    feed_ids = []
    for name in FEEDS_TO_KEEP:
        fid = daemon.resolve_feed_id(STAKED_ORACLE_CONTRACT, name.strip())
        if fid >= 0:
            feed_ids.append((name.strip(), fid))
            log.info(f"  Feed {name.strip()} -> ID {fid}")

    if not feed_ids:
        log.error("No feeds resolved, exiting")
        sys.exit(1)

    last_topo = 0
    while True:
        try:
            current_topo = daemon.get_topoheight()
            if current_topo == last_topo:
                time.sleep(POLL_INTERVAL)
                continue
            last_topo = current_topo

            # Call aggregate_now for each feed on every block
            for name, fid in feed_ids:
                daemon.aggregate_now(STAKED_ORACLE_CONTRACT, fid)
            log.debug(f"Block {current_topo}: aggregate_now called for {len(feed_ids)} feeds")
        except Exception as e:
            log.error(f"Main loop error: {e}", exc_info=True)

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
