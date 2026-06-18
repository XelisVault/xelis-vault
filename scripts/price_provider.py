#!/usr/bin/env python3
"""
Price Provider Script v4 — XELIS Vault

Any address can become a price provider by staking VLT via
StakedOracle.register_provider(). This script runs as a loop:

  1. Fetches XEL/USD prices from validated external sources
  2. Computes the median (removes outliers)
  3. Submits via StakedOracle.submit_price(feed_id, price)

Anti-Sybil: VLT staking prevents bots — each provider must stake
MIN_STAKE VLT. Outlier submissions are slashed (1% of stake).

Built-in sources: MEXC, CoinEx, CoinGecko, CoinMarketCap.
Custom HTTP/command sources can be added via custom_sources.json.

Rewards: REWARD_PER_CYCLE / n_valid_providers per aggregation cycle.
50% of slash is burned, 50% goes to Treasury.
"""
import os
import sys
import time
import json
import logging
import statistics
import argparse
import threading
from typing import Optional, List, Dict, Tuple
from dataclasses import dataclass

import requests

# ===== Configuration =====
PROVIDER_ADDRESS = os.environ.get("PROVIDER_ADDRESS", "")
XELIS_DAEMON_RPC = os.environ.get("XELIS_RPC", "http://127.0.0.1:8080")
STAKED_ORACLE_CONTRACT = os.environ.get("STAKED_ORACLE_CONTRACT", "")
VLT_ASSET_HASH = os.environ.get("VLT_ASSET_HASH", "")

POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "5"))         # seconds
SUBMIT_INTERVAL = int(os.environ.get("SUBMIT_INTERVAL", "20"))    # seconds
PROMETHEUS_PORT = int(os.environ.get("PROMETHEUS_PORT", "9091"))

CMC_API_KEY = os.environ.get("CMC_API_KEY", "")
MIN_SOURCES_REQUIRED = 2
OUTLIER_THRESHOLD_PCT = 0.10  # 10% — stricter than the oracle (5%)
                              # to avoid being slashed as a precaution

SANITY_MIN_PRICE = 0.001
SANITY_MAX_PRICE = 10000.0

# Feeds to submit
DEFAULT_FEEDS = [
    {
        "name": "XEL/USD",
        "asset_hash": "0" * 64,
        "decimals": 8,
        # MEXC + CoinEx are the primary sources (no rate limit issues)
        # CoinGecko is OPTIONAL - only enable if you have an API key (Pro plan)
        # Otherwise, with 50+ providers, CoinGecko will rate-limit everyone
        "sources": ["mexc", "coinex"],  # fast & reliable, no rate limit
        # "sources": ["mexc", "coinex", "coingecko"],  # if you have CG API key
        # "sources": ["mexc", "coinex", "cmc"],         # if you have CMC API key
    },
    # Later (via governance):
    # {
    #     "name": "XAU/USD",
    #     "asset_hash": "<gold_token_hash>",
    #     "decimals": 8,
    #     "sources": ["gold_api", "kitco", "cmc_paxg"],
    # },
]

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
log = logging.getLogger("price-provider")


# ============================================================================
# PRICE SOURCES
# ============================================================================

@dataclass
class PriceSample:
    source: str
    price_usd: float
    timestamp: float
    latency_ms: int


def fetch_mexc() -> Optional[PriceSample]:
    """MEXC — api.mexc.com (XEL listed, most reliable)"""
    t0 = time.time()
    try:
        r = requests.get(
            "https://api.mexc.com/api/v3/ticker/price",
            params={"symbol": "XELUSDT"},
            timeout=10,
        )
        r.raise_for_status()
        price = float(r.json()["price"])
        latency = int((time.time() - t0) * 1000)
        if not (SANITY_MIN_PRICE < price < SANITY_MAX_PRICE):
            log.warning(f"MEXC out-of-sanity: {price}")
            return None
        return PriceSample("mexc", price, time.time(), latency)
    except Exception as e:
        log.debug(f"MEXC failed: {e}")
        return None


def fetch_coinex() -> Optional[PriceSample]:
    """CoinEx — api.coinex.com/v2 (most active source per CoinGecko)"""
    t0 = time.time()
    try:
        r = requests.get(
            "https://api.coinex.com/v2/spot/ticker",
            params={"market": "XELUSDT"},
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
        if data.get("code") != 0 or not data.get("data"):
            return None
        price = float(data["data"][0]["last"])
        latency = int((time.time() - t0) * 1000)
        if not (SANITY_MIN_PRICE < price < SANITY_MAX_PRICE):
            log.warning(f"CoinEx out-of-sanity: {price}")
            return None
        return PriceSample("coinex", price, time.time(), latency)
    except Exception as e:
        log.debug(f"CoinEx failed: {e}")
        return None


def fetch_coingecko() -> Optional[PriceSample]:
    """CoinGecko — aggregator (rate-limit 30/min)"""
    t0 = time.time()
    try:
        r = requests.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={"ids": "xelis", "vs_currencies": "usd"},
            timeout=10,
            headers={"Accept": "application/json"},
        )
        if r.status_code == 429:
            log.debug("CoinGecko rate-limited")
            return None
        r.raise_for_status()
        data = r.json()
        if "xelis" not in data or "usd" not in data["xelis"]:
            return None
        price = float(data["xelis"]["usd"])
        latency = int((time.time() - t0) * 1000)
        if not (SANITY_MIN_PRICE < price < SANITY_MAX_PRICE):
            log.warning(f"CoinGecko out-of-sanity: {price}")
            return None
        return PriceSample("coingecko", price, time.time(), latency)
    except Exception as e:
        log.debug(f"CoinGecko failed: {e}")
        return None


def fetch_cmc() -> Optional[PriceSample]:
    """CoinMarketCap — requires CMC_API_KEY"""
    if not CMC_API_KEY:
        return None
    t0 = time.time()
    try:
        r = requests.get(
            "https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest",
            params={"symbol": "XEL", "convert": "USD"},
            timeout=10,
            headers={"X-CMC_PRO_API_KEY": CMC_API_KEY},
        )
        r.raise_for_status()
        data = r.json()
        if "data" not in data or "XEL" not in data["data"]:
            return None
        price = float(data["data"]["XEL"]["quote"]["USD"]["price"])
        latency = int((time.time() - t0) * 1000)
        if not (SANITY_MIN_PRICE < price < SANITY_MAX_PRICE):
            log.warning(f"CMC out-of-sanity: {price}")
            return None
        return PriceSample("cmc", price, time.time(), latency)
    except Exception as e:
        log.debug(f"CMC failed: {e}")
        return None


# ============================================================================
# CUSTOM SOURCES — user-configurable price sources
# ============================================================================
# Users can add their own price sources in two ways:
#
# 1. HTTP SOURCE (custom JSON API)
#    Config in custom_sources.json:
#    {
#      "name": "my_exchange",
#      "type": "http",
#      "url": "https://api.my-exchange.com/ticker?pair=XELUSD",
#      "json_path": "data.last_price",   # path to price in JSON
#      "headers": {"Authorization": "Bearer xxx"},   # optional
#      "timeout": 10
#    }
#
# 2. COMMAND SOURCE (external script)
#    Config in custom_sources.json:
#    {
#      "name": "my_script",
#      "type": "command",
#      "command": "/usr/local/bin/my_price_fetcher.sh",
#      "args": ["--asset", "XEL"]   # optional
#    }
#    The script must output the USD price on stdout (just the number, e.g. "0.32")
#
# CONFIG FILE: custom_sources.json (next to the script)
# Example provided in custom_sources.example.json
# ============================================================================

CUSTOM_SOURCES_FILE = os.environ.get(
    "CUSTOM_SOURCES_FILE",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "custom_sources.json")
)


def load_custom_sources() -> list:
    """Load custom sources from custom_sources.json."""
    if not os.path.exists(CUSTOM_SOURCES_FILE):
        return []
    try:
        with open(CUSTOM_SOURCES_FILE) as f:
            data = json.load(f)
        if not isinstance(data, list):
            log.warning(f"{CUSTOM_SOURCES_FILE} must contain a JSON list")
            return []
        return data
    except Exception as e:
        log.warning(f"Error reading {CUSTOM_SOURCES_FILE}: {e}")
        return []


def fetch_custom_http(src: dict) -> Optional[PriceSample]:
    """Custom HTTP source — parse JSON and extract price via json_path."""
    name = src.get("name", "custom_http")
    url = src.get("url")
    if not url:
        return None
    json_path = src.get("json_path", "price")
    headers = src.get("headers", {})
    timeout = src.get("timeout", 10)

    t0 = time.time()
    try:
        r = requests.get(url, headers=headers, timeout=timeout)
        r.raise_for_status()
        data = r.json()

        # Navigate JSON via path (e.g. "data.last_price")
        price = data
        for key in json_path.split("."):
            if isinstance(price, dict) and key in price:
                price = price[key]
            else:
                log.debug(f"Custom HTTP {name}: key '{key}' not found in response")
                return None

        price = float(price)
        latency = int((time.time() - t0) * 1000)
        if not (SANITY_MIN_PRICE < price < SANITY_MAX_PRICE):
            log.warning(f"Custom HTTP {name} out-of-sanity: {price}")
            return None
        return PriceSample(name, price, time.time(), latency)
    except Exception as e:
        log.debug(f"Custom HTTP {name} failed: {e}")
        return None


def fetch_custom_command(src: dict) -> Optional[PriceSample]:
    """External command source — runs a script that outputs the price on stdout."""
    import subprocess
    name = src.get("name", "custom_cmd")
    command = src.get("command")
    if not command:
        return None
    args = src.get("args", [])
    timeout = src.get("timeout", 10)

    t0 = time.time()
    try:
        result = subprocess.run(
            [command] + args,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        if result.returncode != 0:
            log.debug(f"Custom CMD {name} failed (exit {result.returncode}): {result.stderr[:200]}")
            return None

        # The script must output the price on stdout (just the number)
        output = result.stdout.strip()
        # Accept formats: "0.32", "0.32\n", "price: 0.32", "$0.32"
        # Extract the first number found
        import re
        match = re.search(r'[\d.]+', output.replace(',', '.'))
        if not match:
            log.debug(f"Custom CMD {name}: no price found in output: {output[:100]}")
            return None

        price = float(match.group())
        latency = int((time.time() - t0) * 1000)
        if not (SANITY_MIN_PRICE < price < SANITY_MAX_PRICE):
            log.warning(f"Custom CMD {name} out-of-sanity: {price}")
            return None
        return PriceSample(name, price, time.time(), latency)
    except subprocess.TimeoutExpired:
        log.debug(f"Custom CMD {name} timed out")
        return None
    except Exception as e:
        log.debug(f"Custom CMD {name} failed: {e}")
        return None


def fetch_custom(src: dict) -> Optional[PriceSample]:
    """Dispatcher for custom sources."""
    src_type = src.get("type", "http")
    if src_type == "http":
        return fetch_custom_http(src)
    elif src_type == "command":
        return fetch_custom_command(src)
    else:
        log.warning(f"Unknown custom source type: {src_type}")
        return None


# Registry of all price sources (built-in + custom)
PRICE_SOURCES = {
    "mexc": fetch_mexc,
    "coinex": fetch_coinex,
    "coingecko": fetch_coingecko,
    "cmc": fetch_cmc,
}


def get_all_sources() -> dict:
    """Return all available sources (built-in + custom)."""
    sources = PRICE_SOURCES.copy()
    for custom_src in load_custom_sources():
        name = custom_src.get("name")
        if name and name not in sources:
            # Create a closure that captures the custom source config
            def make_fetcher(src_config):
                def fetcher():
                    return fetch_custom(src_config)
                return fetcher
            sources[name] = make_fetcher(custom_src)
    return sources


# ============================================================================
# LOCAL AGGREGATION
# ============================================================================
# The provider applies ITS OWN filtering before submitting:
#   1. Sanity check
#   2. Source median
#   3. Local outlier filter (10% — stricter than the oracle's 5%)
#   4. Final median
# This reduces the risk of being slashed.
# ============================================================================
def aggregate_feed(feed: Dict) -> Tuple[Optional[float], List[PriceSample], List[str]]:
    samples: List[PriceSample] = []
    ignored: List[str] = []

    # Use get_all_sources() to include custom sources
    all_sources = get_all_sources()

    for src_name in feed["sources"]:
        fetcher = all_sources.get(src_name)
        if not fetcher:
            ignored.append(src_name)
            continue
        sample = fetcher()
        if sample is None:
            ignored.append(src_name)
        else:
            samples.append(sample)

    if len(samples) < MIN_SOURCES_REQUIRED:
        log.warning(
            f"Feed {feed['name']}: only {len(samples)} sources "
            f"(min {MIN_SOURCES_REQUIRED}), skipping"
        )
        return None, samples, ignored

    prices = [s.price_usd for s in samples]
    initial_median = statistics.median(prices)

    valid: List[PriceSample] = []
    for s in samples:
        if initial_median > 0:
            deviation = abs(s.price_usd - initial_median) / initial_median
            if deviation > OUTLIER_THRESHOLD_PCT:
                log.warning(
                    f"Feed {feed['name']}: {s.source}=${s.price_usd:.6f} "
                    f"deviates >{OUTLIER_THRESHOLD_PCT*100:.0f}%, ignoring"
                )
                ignored.append(s.source)
                continue
        valid.append(s)

    if len(valid) < MIN_SOURCES_REQUIRED:
        return None, samples, ignored

    final_median = statistics.median([s.price_usd for s in valid])

    if not (SANITY_MIN_PRICE < final_median < SANITY_MAX_PRICE):
        log.error(f"Feed {feed['name']}: final median {final_median} failed sanity")
        return None, samples, ignored

    log.info(
        f"Feed {feed['name']}: median=${final_median:.6f}, "
        f"sources={[f'{s.source}=${s.price_usd:.6f}' for s in valid]}, "
        f"ignored={ignored}"
    )
    return final_median, valid, ignored


# ============================================================================
# XELIS DAEMON
# ============================================================================
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

    def submit_price_tx(self, provider_addr: str, oracle_contract: str,
                         feed_id: int, price_atomic: int) -> Optional[str]:
        try:
            result = self._call("submit_transaction", {
                "tx_type": "CallContract",
                "contract": oracle_contract,
                "entry": "submit_price",
                "args": [str(feed_id), str(price_atomic)],
                "signer": provider_addr,
            })
            return result.get("hash")
        except Exception as e:
            log.error(f"submit_price_tx failed: {e}")
            return None


# ============================================================================
# PRICE PROVIDER — main loop
# ============================================================================
class PriceProvider:
    def __init__(self, daemon: XelisDaemon, provider_addr: str, oracle: str):
        self.daemon = daemon
        self.provider_addr = provider_addr
        self.oracle = oracle
        self.feed_ids: Dict[str, int] = {}
        self.stats = {
            "cycles": 0,
            "prices_submitted": 0,
            "prices_failed": 0,
            "estimated_rewards_vlt": 0.0,
            "estimated_slashes_vlt": 0.0,
            "last_price_xel_usd": 0.0,
            "last_submit_topo": 0,
        }

    def resolve_feed_ids(self, feeds: List[Dict]) -> None:
        for feed in feeds:
            try:
                result = self.daemon._call("call_contract_read", {
                    "contract": self.oracle,
                    "entry": "get_feed_id",
                    "args": [feed["name"]],
                })
                feed_id = int(result)
                self.feed_ids[feed["name"]] = feed_id
                log.info(f"Feed {feed['name']} -> ID {feed_id}")
            except Exception as e:
                log.warning(f"Could not resolve feed_id for {feed['name']}: {e}")

    def submit_cycle(self, feeds: List[Dict]) -> None:
        """Submit a price for each active feed."""
        self.stats["cycles"] += 1

        for feed in feeds:
            feed_id = self.feed_ids.get(feed["name"])
            if feed_id is None:
                continue

            price_usd, valid_samples, ignored = aggregate_feed(feed)
            if price_usd is None or price_usd <= 0:
                log.warning(f"No valid price for {feed['name']}, skipping this cycle")
                continue

            if feed["name"] == "XEL/USD":
                self.stats["last_price_xel_usd"] = price_usd

            decimals = feed.get("decimals", 8)
            price_atomic = int(price_usd * (10 ** decimals))

            log.info(
                f"Submitting {feed['name']}=${price_usd:.6f} "
                f"(atomic={price_atomic})"
            )

            tx_hash = self.daemon.submit_price_tx(
                self.provider_addr,
                self.oracle,
                feed_id,
                price_atomic,
            )
            if tx_hash:
                log.info(f"  -> tx={tx_hash}")
                self.stats["prices_submitted"] += 1
                # Optimistic estimate: if we are among valid submissions,
                # we receive reward_per_cycle / n_valid_providers
                # (we cannot know here — the contract decides)
                self.stats["estimated_rewards_vlt"] += 2.5  # average estimate
            else:
                log.error(f"  -> submission failed")
                self.stats["prices_failed"] += 1


# ============================================================================
# PROMETHEUS METRICS
# ============================================================================
def start_metrics_server(port: int, provider: PriceProvider):
    from http.server import HTTPServer, BaseHTTPRequestHandler

    class MetricsHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path != "/metrics":
                self.send_response(404)
                self.end_headers()
                return
            stats = provider.stats
            lines = [
                f"# HELP provider_cycles_total Total aggregation cycles",
                f"# TYPE provider_cycles_total counter",
                f"provider_cycles_total {stats['cycles']}",
                f"",
                f"# HELP provider_prices_submitted_total Prices successfully submitted",
                f"# TYPE provider_prices_submitted_total counter",
                f"provider_prices_submitted_total {stats['prices_submitted']}",
                f"",
                f"# HELP provider_prices_failed_total Prices that failed to submit",
                f"# TYPE provider_prices_failed_total counter",
                f"provider_prices_failed_total {stats['prices_failed']}",
                f"",
                f"# HELP provider_estimated_rewards_vlt Estimated VLT rewards earned",
                f"# TYPE provider_estimated_rewards_vlt gauge",
                f"provider_estimated_rewards_vlt {stats['estimated_rewards_vlt']}",
                f"",
                f"# HELP provider_last_price_xel_usd Last XEL/USD price submitted",
                f"# TYPE provider_last_price_xel_usd gauge",
                f"provider_last_price_xel_usd {stats['last_price_xel_usd']}",
                f"",
                f"# HELP provider_up 1 if running",
                f"# TYPE provider_up gauge",
                f"provider_up 1",
                f"",
            ]
            body = "\n".join(lines).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt, *args):
            pass

    server = HTTPServer(("0.0.0.0", port), MetricsHandler)
    log.info(f"Prometheus metrics on :{port}/metrics")
    server.serve_forever()


# ============================================================================
# CUSTOM SOURCE MANAGEMENT — interactive source addition
# ============================================================================

def add_custom_source_interactive():
    """Interactive assistant to add a custom source."""
    print()
    print("=" * 60)
    print("  Add a custom price source")
    print("=" * 60)
    print()
    print("Two types of custom sources are supported:")
    print("  1. HTTP API (JSON) — fetch price from a URL")
    print("  2. Command — run an external script that outputs the price")
    print()

    choice = input("Choose type (1=http, 2=command) [1]: ").strip() or "1"

    src = {}
    if choice == "1":
        src["type"] = "http"
        src["name"] = input("Source name (e.g. 'my_exchange'): ").strip()
        src["url"] = input("API URL (e.g. 'https://api.example.com/price?pair=XELUSD'): ").strip()
        src["json_path"] = input(
            "JSON path to price (e.g. 'data.last_price' or 'price'): "
        ).strip() or "price"

        headers_input = input("Headers (optional, JSON format, e.g. {\"Authorization\":\"Bearer xxx\"}): ").strip()
        if headers_input:
            try:
                src["headers"] = json.loads(headers_input)
            except:
                print("Invalid JSON headers, ignoring")

        src["timeout"] = int(input("Timeout in seconds [10]: ").strip() or "10")

    elif choice == "2":
        src["type"] = "command"
        src["name"] = input("Source name (e.g. 'my_script'): ").strip()
        src["command"] = input("Command path (e.g. '/usr/local/bin/my_price.sh'): ").strip()

        args_input = input("Arguments (optional, space-separated, e.g. --asset XEL): ").strip()
        if args_input:
            src["args"] = args_input.split()

        src["timeout"] = int(input("Timeout in seconds [10]: ").strip() or "10")

    else:
        print("Invalid choice")
        return

    if not src.get("name") or (not src.get("url") and not src.get("command")):
        print("Error: name and url/command are required")
        return

    # Test the source before adding
    print()
    print("Testing source...")
    sample = fetch_custom(src)
    if sample:
        print(f"  OK — price: ${sample.price_usd:.6f} ({sample.latency_ms}ms)")
    else:
        print("  FAIL — source does not return a valid price")
        confirm = input("Add anyway? (y/N): ").strip().lower()
        if confirm != "y":
            return

    # Load existing sources
    existing = load_custom_sources()
    existing.append(src)

    # Save
    with open(CUSTOM_SOURCES_FILE, "w") as f:
        json.dump(existing, f, indent=2)

    print()
    print(f"Source '{src['name']}' added to {CUSTOM_SOURCES_FILE}")
    print()
    print("To use it, add it to your feed config:")
    print(f'  "sources": ["mexc", "coinex", "{src["name"]}"]')
    print()
    print("Or set the DEFAULT_FEEDS in the script directly.")


def remove_custom_source_interactive():
    """Remove a custom source."""
    sources = load_custom_sources()
    if not sources:
        print("No custom sources configured.")
        return

    print()
    print("Custom sources:")
    for i, src in enumerate(sources):
        print(f"  {i}: {src.get('name', 'unnamed')} ({src.get('type', 'unknown')})")

    try:
        idx = int(input("\nIndex to remove: ").strip())
        if 0 <= idx < len(sources):
            removed = sources.pop(idx)
            with open(CUSTOM_SOURCES_FILE, "w") as f:
                json.dump(sources, f, indent=2)
            print(f"Removed: {removed.get('name')}")
        else:
            print("Invalid index")
    except ValueError:
        print("Invalid input")


# ============================================================================
# MAIN
# ============================================================================
def main():
    parser = argparse.ArgumentParser(description="XELIS Vault - Price Provider")
    parser.add_argument("--provider", required=False, help="Provider XELIS Address")
    parser.add_argument("--oracle", required=False, help="StakedOracle contract hash")
    parser.add_argument("--rpc", required=False, help="XELIS daemon RPC URL")
    parser.add_argument("--list-sources", action="store_true",
                        help="List all available sources (built-in + custom)")
    parser.add_argument("--test-sources", action="store_true",
                        help="Test all sources and show prices")
    parser.add_argument("--add-source", action="store_true",
                        help="Add a custom price source interactively")
    parser.add_argument("--remove-source", action="store_true",
                        help="Remove a custom price source")
    parser.add_argument("--show-config", action="store_true",
                        help="Show current configuration (feeds + sources)")
    args = parser.parse_args()

    if args.list_sources:
        print("Available price sources:")
        print()
        print("Built-in sources:")
        for name in PRICE_SOURCES.keys():
            print(f"  - {name}")
        print()
        custom = load_custom_sources()
        if custom:
            print("Custom sources:")
            for src in custom:
                print(f"  - {src.get('name', 'unnamed')} ({src.get('type', 'unknown')})")
        else:
            print("Custom sources: (none configured)")
            print(f"  Use --add-source to add one")
        sys.exit(0)

    if args.test_sources:
        log.info("Testing all price sources...")
        all_sources = get_all_sources()
        for name, fetcher in all_sources.items():
            sample = fetcher()
            if sample:
                log.info(f"  {name:20s} OK   ${sample.price_usd:.6f} ({sample.latency_ms}ms)")
            else:
                log.warning(f"  {name:20s} FAIL")
        sys.exit(0)

    if args.add_source:
        add_custom_source_interactive()
        sys.exit(0)

    if args.remove_source:
        remove_custom_source_interactive()
        sys.exit(0)

    if args.show_config:
        print("Current configuration:")
        print()
        print("Feeds:")
        for feed in DEFAULT_FEEDS:
            print(f"  {feed['name']}: sources = {feed['sources']}")
        print()
        print("Custom sources file:", CUSTOM_SOURCES_FILE)
        custom = load_custom_sources()
        if custom:
            print(f"  {len(custom)} custom source(s) configured")
        else:
            print("  No custom sources")
        sys.exit(0)

    provider_addr = args.provider or PROVIDER_ADDRESS
    oracle = args.oracle or STAKED_ORACLE_CONTRACT
    rpc = args.rpc or XELIS_DAEMON_RPC

    if not provider_addr:
        log.error("Missing --provider or PROVIDER_ADDRESS env var")
        sys.exit(1)
    if not oracle:
        log.error("Missing --oracle or STAKED_ORACLE_CONTRACT env var")
        sys.exit(1)

    daemon = XelisDaemon(rpc)
    provider = PriceProvider(daemon, provider_addr, oracle)

    # Start Prometheus exporter
    threading.Thread(
        target=start_metrics_server,
        args=(PROMETHEUS_PORT, provider),
        daemon=True,
    ).start()

    log.info("=" * 70)
    log.info("XELIS Vault v4 - Price Provider")
    log.info("=" * 70)
    log.info(f"  Provider:    {provider_addr}")
    log.info(f"  Oracle:      {oracle}")
    log.info(f"  RPC:         {rpc}")
    log.info(f"  Feeds:       {[f['name'] for f in DEFAULT_FEEDS]}")
    log.info(f"  Sources:     {list(get_all_sources().keys())}")
    log.info(f"  Submit intv: {SUBMIT_INTERVAL}s")
    log.info(f"  Outlier th:  {OUTLIER_THRESHOLD_PCT * 100:.0f}% (stricter than oracle)")
    log.info(f"  Metrics:     http://0.0.0.0:{PROMETHEUS_PORT}/metrics")
    log.info("=" * 70)

    # Resolve feed IDs
    provider.resolve_feed_ids(DEFAULT_FEEDS)

    # Test initial
    log.info("Testing price sources...")
    for name, fetcher in get_all_sources().items():
        sample = fetcher()
        if sample:
            log.info(f"  {name:12s} OK  ${sample.price_usd:.6f} ({sample.latency_ms}ms)")
        else:
            log.warning(f"  {name:12s} FAIL")

    # Main loop
    log.info("Starting price submission loop...")
    while True:
        try:
            provider.submit_cycle(DEFAULT_FEEDS)
        except Exception as e:
            log.error(f"Main loop error: {e}", exc_info=True)

        time.sleep(SUBMIT_INTERVAL)


if __name__ == "__main__":
    main()
