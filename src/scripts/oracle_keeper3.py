#!/usr/bin/env python3
"""Oracle keeper: 3 provider wallets keep the XEL/USD feed alive.

Economic cadence (on-chain config: hard_stale=500, hb interval=900,
timeout=4000):
  - submit_price + poke aggregate_now every SUBMIT_EVERY blocks (~13 min)
  - heartbeats every HEARTBEAT_EVERY blocks (~45 min)
Fee 0.001 XEL/tx → total burn ≈ 0.4 XEL/day for the 3 providers.

REAL PRICE: each provider fetches the XEL/USDT median price from public
exchanges (CoinEx, MEXC) every cycle and submits it as-is.
If all sources fail → fallback to last good price
(persisted to disk) so the feed never goes stale.
Reverts ("alreadysub", nonce races) are tolerated; the loop continues.
"""
import json
import os
import signal
import statistics
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from protocol import Protocol, val_u64, _with_retries

STATE_PATH = Path(__file__).resolve().parent.parent / "docs" / "deployment_state.json"
DMAP_PATH = Path(__file__).resolve().parent.parent / "docs" / "entry_chunk_ids.json"
# Cross-platform cache/log paths (no /tmp/ on Windows)
_CACHE_DIR = Path(os.environ.get("XELIS_VAULT_DIR",
                 Path.home() / ".xelis-vault")) / "cache"
_CACHE_DIR.mkdir(parents=True, exist_ok=True)
PRICE_CACHE_PATH = _CACHE_DIR / "oracle_last_good_price.json"

PROVIDERS = [
    (os.environ.get("PROVIDER1_URL", "http://127.0.0.1:18086/json_rpc"), 1),
    (os.environ.get("PROVIDER2_URL", "http://127.0.0.1:18087/json_rpc"), 2),
    (os.environ.get("PROVIDER3_URL", "http://127.0.0.1:18088/json_rpc"), 3),
]
FEED_ID = 0
FEED_DECIMALS = 8
# Real sources listing XEL/USDT (tested 2026-08-22: coinex+mexc OK,
# bitget/gate don't list XEL but tolerated if they respond).
PRICE_SOURCES = [
    ("coinex", "https://api.coinex.com/v2/spot/ticker",
     {"market": "XELUSDT"}, ("data", 0, "last")),
    ("mexc", "https://api.mexc.com/api/v3/ticker/price",
     {"symbol": "XELUSDT"}, ("price",)),
    ("bitget", "https://api.bitget.com/api/v2/spot/market/tickers",
     {"symbol": "XELUSDT"}, ("data", 0, "lastPr")),
    ("gate", "https://api.gateio.ws/api/v4/spot/tickers",
     {"currency_pair": "XEL_USDT"}, (0, "last")),
]
SANITY_MIN = 0.001            # USD
SANITY_MAX = 10_000.0         # USD
MIN_SOURCES = 1               # resilient: 1 live source is enough
SUBMIT_EVERY = 200            # blocks (~9 min) < hard_stale 500 with margin
HEARTBEAT_EVERY = 1000        # blocks (~45 min), interval 900 / timeout 4000 (on-chain)
TX_FEE = 100_000              # 0.001 XEL/tx — burn ≈ 0.4 XEL/day for 3 providers
LOG_DIR = Path(os.environ.get("XELIS_VAULT_DIR",
              Path.home() / ".xelis-vault")) / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG = str(LOG_DIR / "oracle_keeper3.log")


def log(msg: str) -> None:
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG, "a") as f:
            f.write(line + "\n")
    except OSError:
        pass


def _load_cached_price() -> int | None:
    try:
        return int(json.loads(PRICE_CACHE_PATH.read_text())["price_atomic"])
    except Exception:
        return None


def _save_cached_price(price_atomic: int, sources: list[str]) -> None:
    try:
        PRICE_CACHE_PATH.write_text(json.dumps({
            "price_atomic": price_atomic, "sources": sources,
            "ts": int(time.time()),
        }))
    except OSError:
        pass


def fetch_real_price() -> tuple[int | None, str]:
    """Median XEL/USD across public exchanges → (atomic, description).

    Returns (None, reason) when no source yields a sane price.
    """
    vals = []
    for name, url, params, path in PRICE_SOURCES:
        try:
            r = requests.get(url, params=params, timeout=8)
            r.raise_for_status()
            d = r.json()
            for p in path:
                d = d[int(p)] if isinstance(p, int) else d[p]
            price = float(d)
            if SANITY_MIN < price < SANITY_MAX:
                vals.append((name, price))
        except Exception as e:
            log(f"  source {name}: {str(e)[:60]}")
    if len(vals) < MIN_SOURCES:
        return None, "no valid source"
    med = statistics.median([p for _, p in vals])
    used = ",".join(n for n, p in vals)
    return int(round(med * 10 ** FEED_DECIMALS)), f"median {med:.6f} USD [{used}]"


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Oracle keeper — submits prices + heartbeats")
    parser.add_argument("--wallet-url", help="Single wallet URL to use as provider (fallback)")
    parser.add_argument("--rpc", help="Daemon RPC URL (unused, kept for compatibility)")
    args = parser.parse_args()

    try:
        state = json.loads(STATE_PATH.read_text())
        dmap = json.loads(DMAP_PATH.read_text())
    except Exception as e:
        log(f"FATAL: cannot load state/dmap: {e}")
        sys.exit(1)
    miner_c = state["contracts"]["XelisVaultMiner"]
    oracle_c = state["contracts"]["StakedOracle"]

    def cid(contract: str, fn: str) -> int:
        return int(next(k for k, v in dmap[contract].items() if v["name"] == fn))

    chunk_submit = cid("StakedOracle", "submit_price")
    chunk_hb = cid("XelisVaultMiner", "submit_heartbeat")
    chunk_agg = cid("StakedOracle", "aggregate_now")

    wallets = []
    # Try the 3 dedicated provider wallets first
    for url, idx in PROVIDERS:
        try:
            pw = Protocol(wallet_url=url, wallet_auth=("wallet", "testpass"))
            addr = pw.wallet.address()
            wallets.append((idx, pw))
            log(f"provider{idx} ready ({addr[:20]}…)")
        except Exception as e:
            log(f"provider{idx} SKIP ({url}): {str(e)[:60]}")

    # Fallback: use --wallet-url as single provider if no dedicated providers found
    if not wallets and args.wallet_url:
        log(f"No dedicated providers found. Using --wallet-url as single provider...")
        try:
            pw = Protocol(wallet_url=args.wallet_url, wallet_auth=("wallet", "testpass"))
            addr = pw.wallet.address()
            wallets.append((1, pw))
            log(f"single-provider ready ({addr[:20]}…)")
        except Exception as e:
            log(f"single-provider SKIP ({args.wallet_url}): {str(e)[:60]}")

    if not wallets:
        log("FATAL: no provider wallets available")
        log("  Options:")
        log("    1. Start 3 provider wallets on ports 18086/18087/18088")
        log("    2. Or pass --wallet-url with your main wallet URL")
        sys.exit(1)

    p0 = wallets[0][1]
    last_topo = 0
    last_hb_topo = 0
    last_good_price = _load_cached_price()
    if last_good_price:
        log(f"last good price cached: {last_good_price} atomic "
            f"({last_good_price / 10**FEED_DECIMALS:.6f} USD)")

    running = [True]
    def _stop(sig, frame):
        log(f"signal {sig} received, shutting down…")
        running[0] = False
    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    def send(pw: Protocol, contract: str, chunk: int, params: list) -> bool:
        def _b():
            return pw.wallet._call("build_transaction", {
                "invoke_contract": {
                    "contract": contract, "max_gas": 3_000_000,
                    "entry_id": chunk,
                    "parameters": params,
                    "deposits": {},
                    "permission": "all"},
                "fee": {"fixed": TX_FEE}, "broadcast": True})["hash"]
        try:
            tx = _with_retries(_b)
            pw.wait(tx, timeout=120)
            rev = pw.revert_reason(tx)
            if rev is not None:
                log(f"  revert {contract[:8]}#{chunk}: {rev}")
                return False
            return True
        except Exception as e:
            msg = str(e)[:80]
            if "alreadysub" in msg or "nonce" in msg.lower():
                log(f"  soft err: {msg}")
            else:
                log(f"  err: {msg}")
            return False

    while running[0]:
        try:
            topo = p0.daemon.topoheight()
        except Exception as e:
            log(f"daemon err: {str(e)[:60]}")
            time.sleep(15)
            continue

        if topo >= last_hb_topo + HEARTBEAT_EVERY:
            for idx, pw in wallets:
                send(pw, miner_c, chunk_hb, [])
                time.sleep(4)
            last_hb_topo = topo
            log(f"heartbeats @topo {topo}")

        if topo >= last_topo + SUBMIT_EVERY:
            # Anti-deadlock v12.1: if all miners already submitted in the
            # current cycle, nobody can trigger try_aggregate
            # (the alreadysub check precedes the call). An explicit
            # aggregate_now poke opens the next cycle before submissions.
            send(wallets[0][1], oracle_c, chunk_agg, [val_u64(FEED_ID)])
            time.sleep(4)
            okc = 0
            for idx, pw in wallets:
                # REAL PRICE, fetched independently by each provider
                # (natural inter-exchange variance << max spread 500 bps).
                price, desc = fetch_real_price()
                if price is None:
                    if last_good_price is not None:
                        price = last_good_price
                        desc = f"FALLBACK last good price ({desc})"
                    else:
                        log(f"  provider{idx}: no price available ({desc}), skip")
                        continue
                okc += 1
                log(f"  provider{idx}: submit {price} atomic = "
                    f"{price / 10**FEED_DECIMALS:.6f} USD ({desc})")
                if send(pw, oracle_c, chunk_submit, [val_u64(FEED_ID), val_u64(price)]):
                    last_good_price = price
                    _save_cached_price(price, desc)
                time.sleep(4)
            # direct aggregate read
            try:
                raw = p0.daemon.read_key(oracle_c, "fg_" + str(FEED_ID))
                if isinstance(raw, dict):
                    log(f"submit x{okc} @topo {topo} | agg={raw.get('price', raw)}")
                elif raw is not None:
                    log(f"submit x{okc} @topo {topo} | fg_0={raw}")
                else:
                    log(f"submit x{okc} @topo {topo} | no aggregate yet")
            except Exception:
                log(f"submit x{okc} @topo {topo}")
            last_topo = topo

        # Sleep in small increments so we respond quickly to shutdown signals
        for _ in range(10):
            if not running[0]:
                break
            time.sleep(1)


if __name__ == "__main__":
    main()
