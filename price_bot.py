#!/usr/bin/env python3
"""
Price bot: fetches XEL/USD price and pushes to on-chain oracle.
Runs continuously, updates every N blocks (default: 100).
*/
import json, urllib.request, base64, time, os, sys

# Config
DAEMON_RPC = os.getenv("DAEMON_RPC", "http://127.0.0.1:18081")
WALLET_RPC = os.getenv("WALLET_RPC", "http://127.0.0.1:18082")
WALLET_USER = os.getenv("WALLET_USER", "wallet")
WALLET_PASS = os.getenv("WALLET_PASS", "testpass")
ORACLE_HASH = os.getenv("ORACLE_HASH", "")  # set via env or arg
UPDATE_INTERVAL = int(os.getenv("UPDATE_INTERVAL", "100"))  # blocks

# Price sources (all fetched simultaneously, median used)
PRICE_SOURCES = [
    "coingecko",
    "mexc",
    "bitmart",
]

CHANGE_THRESHOLD = float(os.getenv("CHANGE_THRESHOLD", "0.02"))  # 2% min change to update

def wallet_rpc(method, params):
    req = urllib.request.Request(f"{WALLET_RPC}/json_rpc",
        data=json.dumps({"jsonrpc":"2.0","id":"1","method":method,"params":params}).encode(),
        headers={"Content-Type":"application/json"})
    req.add_header("Authorization", f"Basic {base64.b64encode(f'{WALLET_USER}:{WALLET_PASS}'.encode()).decode()}")
    return json.loads(urllib.request.urlopen(req, timeout=30).read())

def daemon_rpc(method, params):
    req = urllib.request.Request(f"{DAEMON_RPC}/json_rpc",
        data=json.dumps({"jsonrpc":"2.0","id":"1","method":method,"params":params}).encode(),
        headers={"Content-Type":"application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=30).read())

def fetch_coingecko():
    url = "https://api.coingecko.com/api/v3/simple/price?ids=xelis&vs_currencies=usd"
    req = urllib.request.Request(url, headers={"User-Agent": "xelis-price-bot/1.0"})
    data = json.loads(urllib.request.urlopen(req, timeout=15).read())
    price = data.get("xelis", {}).get("usd")
    if price:
        print(f"  coingecko: ${price}")
        return int(price * 100000000)
    return None

def fetch_mexc():
    url = "https://api.mexc.com/api/v3/ticker/price?symbol=XELUSDT"
    req = urllib.request.Request(url, headers={"User-Agent": "xelis-price-bot/1.0"})
    data = json.loads(urllib.request.urlopen(req, timeout=15).read())
    if "error" not in data:
        price = float(data["price"])
        print(f"  mexc: ${price}")
        return int(price * 100000000)
    return None

def fetch_bitmart():
    url = "https://api-cloud.bitmart.com/spot/v1/ticker?symbol=XEL_USDT"
    req = urllib.request.Request(url, headers={"User-Agent": "xelis-price-bot/1.0"})
    data = json.loads(urllib.request.urlopen(req, timeout=15).read())
    ticker = data.get("data", {}).get("ticker", [{}])[0] if isinstance(data.get("data", {}).get("ticker"), list) else data.get("data", {}).get("ticker", {})
    price = float(ticker.get("last_price", 0))
    if price > 0:
        print(f"  bitmart: ${price}")
        return int(price * 100000000)
    return None

def fetch_price():
    """Fetch from all sources in parallel, return median."""
    import concurrent.futures
    prices = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(PRICE_SOURCES)) as pool:
        futures = {pool.submit(globals()[f"fetch_{s}"]): s for s in PRICE_SOURCES}
        for f in concurrent.futures.as_completed(futures):
            try:
                p = f.result()
                if p and p > 0:
                    prices.append(p)
                    print(f"  got {futures[f]}: {p / 1e8}")
            except Exception as e:
                print(f"  {futures[f]} error: {e}")
    if not prices:
        return None, None
    # Median (no single source can dominate)
    prices.sort()
    median = prices[len(prices) // 2]
    print(f"  median: ${median / 1e8} (from {len(prices)} sources)")
    return median, f"median_of_{len(prices)}"

def main():
    oracle = ORACLE_HASH
    if not oracle:
        print("Usage: ORACLE_HASH=<hash> python3 price_bot.py")
        print("  or: python3 price_bot.py <oracle_hash>")
        if len(sys.argv) > 1:
            oracle = sys.argv[1]
        else:
            sys.exit(1)

    print(f"Price bot started. Oracle: {oracle}")
    print(f"Update interval: {UPDATE_INTERVAL} blocks")
    print("Press Ctrl+C to stop.\n")

    last_top = 0

    while True:
        try:
            # Get current chain info
            info = daemon_rpc("get_info", {})
            if "result" not in info:
                print(f"Daemon error: {info}")
                time.sleep(30)
                continue

            top = info["result"]["topoheight"]
            mempool = info["result"]["mempool_size"]

            # Check if it's time to update
            if top < last_top + UPDATE_INTERVAL and mempool > 0:
                time.sleep(15)
                continue

            # Fetch price
            price, source = fetch_price()
            if not price:
                print("  no price source available, retrying in 60s")
                time.sleep(60)
                continue

            # Get current on-chain price for comparison
            try:
                current_req = urllib.request.Request(
                    f"{DAEMON_RPC}/json_rpc",
                    data=json.dumps({"jsonrpc":"2.0","id":"1","method":"contract_call",
                        "params": {"contract": oracle, "entry_id": 4, "parameters": [{"type":"primitive","value":{"type":"opaque","value":{"type":"Hash","value":"0000000000000000000000000000000000000000000000000000000000000000"}}}]}}).encode(),
                    headers={"Content-Type":"application/json"})
                current = json.loads(urllib.request.urlopen(current_req, timeout=15).read())
                old_price = current.get("result", {}).get("result", 0)
                print(f"  current on-chain: {old_price} base units")
            except Exception as e:
                print(f"  could not fetch current price: {e}")
                old_price = 0

            # Only update if price changed significantly (>1%)
            if old_price and abs(price - old_price) / max(old_price, 1) < 0.01:
                print(f"  price unchanged ({price}), skipping update")
                last_top = top
                time.sleep(60)
                continue

            print(f"  proposing new price: {price} base units (${price / 1e8:.4f}) from {source}")

            # Propose price
            u64_param = lambda v: {"type":"primitive","value":{"type":"u64","value":str(v)}}
            result = wallet_rpc("build_transaction", {
                "invoke_contract": {
                    "contract": oracle, "max_gas": 100000, "entry_id": 2,
                    "parameters": [u64_param(price)],
                    "deposits": {}, "permission": "all"
                }, "broadcast": True
            })
            if "error" in result:
                print(f"  propose failed: {result['error']}")
                time.sleep(30)
                continue
            print(f"  propose tx: {result['result']['hash'][:20]}...")

            # Wait for mempool to clear
            time.sleep(10)
            while True:
                info = daemon_rpc("get_info", {})
                if info.get("result", {}).get("mempool_size", 0) == 0:
                    break
                time.sleep(3)

            # Execute price
            result = wallet_rpc("build_transaction", {
                "invoke_contract": {
                    "contract": oracle, "max_gas": 100000, "entry_id": 3,
                    "parameters": [], "deposits": {}, "permission": "all"
                }, "broadcast": True
            })
            if "error" in result:
                print(f"  execute failed: {result['error']}")
                time.sleep(30)
                continue
            print(f"  execute tx: {result['result']['hash'][:20]}...")
            print(f"  ✅ Price updated to ${price / 1e8:.4f}")

            last_top = top

        except KeyboardInterrupt:
            print("\nStopping.")
            break
        except Exception as e:
            print(f"  error: {e}")
            time.sleep(30)

if __name__ == "__main__":
    main()
