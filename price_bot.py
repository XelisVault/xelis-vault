#!/usr/bin/env python3 -u
"""
Price bot: fetches XEL/USD price and updates on-chain oracle.
Runs continuously, updates every N blocks (default: 100).
"""
import json, urllib.request, base64, time, os, sys, concurrent.futures

DAEMON_RPC = os.getenv("DAEMON_RPC", "http://127.0.0.1:18081")
WALLET_RPC = os.getenv("WALLET_RPC", "http://127.0.0.1:18082")
WALLET_USER = os.getenv("WALLET_USER", "wallet")
WALLET_PASS = os.getenv("WALLET_PASS", "testpass")
ORACLE_HASH = os.getenv("ORACLE_HASH", "")
UPDATE_INTERVAL = int(os.getenv("UPDATE_INTERVAL", "100"))

def log(msg):
    print(msg, flush=True)

def wallet_rpc(method, params=None):
    body = {"jsonrpc":"2.0","id":"1","method":method}
    if params is not None:
        body["params"] = params
    req = urllib.request.Request(f"{WALLET_RPC}/json_rpc", data=json.dumps(body).encode())
    req.add_header("Authorization", f"Basic {base64.b64encode(f'{WALLET_USER}:{WALLET_PASS}'.encode()).decode()}")
    req.add_header("Content-Type","application/json")
    return json.loads(urllib.request.urlopen(req, timeout=60).read())

def daemon_rpc(method, params=None):
    body = {"jsonrpc":"2.0","id":"1","method":method}
    if params is not None:
        body["params"] = params
    req = urllib.request.Request(f"{DAEMON_RPC}/json_rpc", data=json.dumps(body).encode(), headers={"Content-Type":"application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=30).read())

def fetch_price():
    prices = []
    sources = {
        "coingecko": lambda: json.loads(urllib.request.urlopen(
            urllib.request.Request("https://api.coingecko.com/api/v3/simple/price?ids=xelis&vs_currencies=usd",
                headers={"User-Agent":"xelis-price-bot/1.0"}), timeout=15).read()).get("xelis",{}).get("usd",0),
        "mexc": lambda: float(json.loads(urllib.request.urlopen(
            urllib.request.Request("https://api.mexc.com/api/v3/ticker/price?symbol=XELUSDT",
                headers={"User-Agent":"xelis-price-bot/1.0"}), timeout=15).read()).get("price",0)),
    }
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        futures = {pool.submit(fn): name for name, fn in sources.items()}
        for f in concurrent.futures.as_completed(futures):
            try:
                p = f.result()
                if p and float(p) > 0:
                    prices.append(int(float(p) * 100000000))
                    log(f"  {futures[f]}: ${float(p):.6f}")
            except Exception as e:
                log(f"  {futures[f]} error: {e}")
    if not prices:
        return None
    prices.sort()
    return prices[len(prices) // 2]

def main():
    oracle = ORACLE_HASH or (sys.argv[1] if len(sys.argv) > 1 else None)
    if not oracle:
        log("Usage: ORACLE_HASH=<hash> python3 price_bot.py <oracle_hash>")
        sys.exit(1)

    log(f"Price bot started. Oracle: {oracle}")
    log(f"Update interval: {UPDATE_INTERVAL} blocks")
    last_top = -99999

    while True:
        try:
            info = daemon_rpc("get_info")
            if "result" not in info:
                log(f"Daemon error: {info}")
                time.sleep(30); continue
            top = info["result"]["topoheight"]
            if top < last_top + UPDATE_INTERVAL:
                time.sleep(15); continue

            price = fetch_price()
            if not price:
                log("  no price source, retrying in 60s")
                time.sleep(60); continue

            # Check pending price exists via TX result (skip if already pending)
            # Note: no read-only RPC available, always propose+execute every interval

            log(f"  proposing {price} (${price/1e8:.4f})")
            r = wallet_rpc("build_transaction", {
                "invoke_contract": {"contract":oracle,"max_gas":200000,"entry_id":2,
                    "parameters":[{"type":"primitive","value":{"type":"u64","value":str(price)}}],
                    "deposits":{},"permission":"all"},"broadcast":True})
            if "error" in r:
                log(f"  propose failed: {r['error']}"); time.sleep(30); continue
            log(f"  propose sent, waiting for timelock (3 blocks)...")

            # Wait for timelock (3 blocks). The propose needs to be mined first,
            # so we wait 5 blocks from current topo to be safe.
            start_topo = daemon_rpc("get_info")["result"]["topoheight"]
            while True:
                time.sleep(10)
                cur = daemon_rpc("get_info")["result"]["topoheight"]
                if cur >= start_topo + 5:
                    break

            log("  executing price")
            r = wallet_rpc("build_transaction", {
                "invoke_contract": {"contract":oracle,"max_gas":200000,"entry_id":3,
                    "parameters":[],"deposits":{},"permission":"all"},"broadcast":True})
            if "error" in r:
                log(f"  execute failed: {r['error']}"); time.sleep(30); continue
            log(f"  ✅ Price updated to ${price/1e8:.4f}")
            last_top = top

        except KeyboardInterrupt:
            log("\nStopping."); break
        except Exception as e:
            log(f"  error: {e}"); time.sleep(30)

if __name__ == "__main__":
    main()
