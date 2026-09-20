#!/usr/bin/env python3
"""Oracle keeper: 3 provider wallets keep the XEL/USD feed alive.

Cadence économique (config on-chain: hard_stale=500, hb interval=900,
timeout=4000):
  - submit_price + poke aggregate_now toutes les SUBMIT_EVERY blocks (~13 min)
  - heartbeats toutes les HEARTBEAT_EVERY blocks (~45 min)
Fee 0.001 XEL/tx → burn total ≈ 0.4 XEL/jour pour les 3 providers.

PRIX RÉEL: chaque provider récupère le prix XEL/USDT médian sur les
exchanges publiques (CoinEx, MEXC) à CHAQUE cycle et le soumet tel quel.
Si toutes les sources échouent → fallback sur le dernier bon prix
(persisté sur disque) pour ne jamais laisser le feed devenir stale.
Reverts ("alreadysub", nonce races) sont tolérés; la boucle continue.
"""
import json
import statistics
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from protocol import Protocol, val_u64, _with_retries

STATE_PATH = Path(__file__).resolve().parent.parent / "docs" / "deployment_state.json"
DMAP_PATH = Path(__file__).resolve().parent.parent / "docs" / "entry_chunk_ids.json"
PRICE_CACHE_PATH = Path("/tmp/oracle_last_good_price.json")

PROVIDERS = [
    ("http://127.0.0.1:18086/json_rpc", 1),
    ("http://127.0.0.1:18087/json_rpc", 2),
    ("http://127.0.0.1:18088/json_rpc", 3),
]
FEED_ID = 0
FEED_DECIMALS = 8
# Sources réelles listant XEL/USDT (testées 2026-08-22: coinex+mexc OK,
# bitget/gate ne référencent pas XEL mais restent tolérées si elles répondent).
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
MIN_SOURCES = 1               # resilient: 1 source vivante suffit
SUBMIT_EVERY = 200            # blocks (~9 min) < hard_stale 500 avec marge
HEARTBEAT_EVERY = 1000        # blocks (~45 min), interval 900 / timeout 4000 (on-chain)
TX_FEE = 100_000              # 0.001 XEL/tx — burn ≈ 0.4 XEL/jour pour les 3 providers
LOG = "/tmp/oracle_keeper3.log"


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
    state = json.loads(STATE_PATH.read_text())
    dmap = json.loads(DMAP_PATH.read_text())
    miner_c = state["contracts"]["XelisVaultMiner"]
    oracle_c = state["contracts"]["StakedOracle"]

    def cid(contract: str, fn: str) -> int:
        return int(next(k for k, v in dmap[contract].items() if v["name"] == fn))

    chunk_submit = cid("StakedOracle", "submit_price")
    chunk_hb = cid("XelisVaultMiner", "submit_heartbeat")
    chunk_agg = cid("StakedOracle", "aggregate_now")

    wallets = []
    for url, idx in PROVIDERS:
        pw = Protocol(wallet_url=url, wallet_auth=("wallet", "testpass"))
        wallets.append((idx, pw))
        log(f"provider{idx} prêt ({pw.wallet.address()[:20]}…)")

    p0 = wallets[0][1]
    last_topo = 0
    last_hb_topo = 0
    last_good_price = _load_cached_price()
    if last_good_price:
        log(f"dernier bon prix en cache: {last_good_price} atomic "
            f"({last_good_price / 10**FEED_DECIMALS:.6f} USD)")

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

    while True:
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
            # Anti-deadlock v12.1: si tous les miners ont déjà soumis dans le
            # cycle courant, plus personne ne peut déclencher try_aggregate
            # (le check alreadysub précède l'appel). Un poke explicite
            # aggregate_now ouvre le cycle suivant avant les soumissions.
            send(wallets[0][1], oracle_c, chunk_agg, [val_u64(FEED_ID)])
            time.sleep(4)
            okc = 0
            for idx, pw in wallets:
                # Prix RÉEL, récupéré indépendamment par chaque provider
                # (variance naturelle inter-exchanges << spread max 500 bps).
                price, desc = fetch_real_price()
                if price is None:
                    if last_good_price is not None:
                        price = last_good_price
                        desc = f"FALLBACK dernier bon prix ({desc})"
                    else:
                        log(f"  provider{idx}: aucun prix disponible ({desc}), skip")
                        continue
                okc += 1
                log(f"  provider{idx}: submit {price} atomic = "
                    f"{price / 10**FEED_DECIMALS:.6f} USD ({desc})")
                if send(pw, oracle_c, chunk_submit, [val_u64(FEED_ID), val_u64(price)]):
                    last_good_price = price
                    _save_cached_price(price, desc)
                time.sleep(4)
            # lecture directe de l'agrégat
            try:
                raw = p0.daemon.read_key(oracle_c, "fg_" + str(FEED_ID))
                if isinstance(raw, dict):
                    log(f"submit x{okc} @topo {topo} | agg={raw.get('price', raw)}")
                elif raw is not None:
                    log(f"submit x{okc} @topo {topo} | fg_0={raw}")
                else:
                    log(f"submit x{okc} @topo {topo} | pas encore d'agrégat")
            except Exception:
                log(f"submit x{okc} @topo {topo}")
            last_topo = topo

        time.sleep(10)


if __name__ == "__main__":
    main()
