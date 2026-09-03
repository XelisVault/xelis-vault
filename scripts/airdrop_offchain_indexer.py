#!/usr/bin/env python3
"""
airdrop_offchain_indexer.py — Indexer off-chain rétroactif pour l'airdrop testnet.

Scanne les blocs du testnet XELIS, identifie les transactions `invoke_contract`
vers les contrats du protocole, déduit l'action (via le hash du contrat + l'entry_id
= chunk compilé), crédite des points par adresse wallet, et écrit un fichier de
classement (adresse -> points par catégorie + total).

Stratégie :
  - Rétroactif : scanne les derniers `--window` blocs (défaut 50000) jusqu'au topo actuel.
  - Reprise (resumable) : un checkpoint (JSON) enregistre `last_topo_scanned` + les
    txs déjà traitées ; relancer reprend là où on s'est arrêté (pas de double comptage).
  - Source : nœud public `testnet-node.xelis.io` (User-Agent requis, rate-limit Cloudflare
    géré par retries/exponential backoff + petites rafales concurrency). Le daemon local
    non pruné peut servir la partie récente via `--rpc http://127.0.0.1:18081/json_rpc`.

Points (docs/AIRDROP_PLAN.md v10.4) :
  - MINING       : 1 pt prix valide soumis (StakedOracle.submit_price=16) ;
                   1 bloc PoW miné -> 1 pt au miner (header `miner`) ; heartbeat 50 pts.
  - RELAYER      : 10 pts/anchor (VaultChat.anchor_messages=11) ; 50 pts enregistrement relayer.
  - CHAT         : 1 pt/message (send_direct_message=113, store_message=38,
                   store_group_message=48, store_ephemeral_message) cap 100/jour ;
                   100 pts/groupe créé (create_group=8).
  - GOVERNANCE   : 50 pts/vote (Governor.vote=4) ; 500 pts/proposition (Governor.propose=3).
  - LIQUIDITY    : 10 pts par XEL déposé (VaultEngineV3.deposit=17, PSM.mint=8,
                   VaultSwap.add_liquidity=17, SavingsRate.deposit=8, PrivacyMixer.deposit=6).

Usage :
    python3 scripts/airdrop_offchain_indexer.py --window 50000
    python3 scripts/airdrop_offchain_indexer.py --resume --out /tmp/airdrop.csv
"""
import argparse
import concurrent.futures
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

PUBLIC_NODE = "https://testnet-node.xelis.io/json_rpc"
LOCAL_NODE = "http://127.0.0.1:18081/json_rpc"

XEL_DECIMALS = 8

# Adresses EXCLUES du scoring (n'accumulent AUCUN point airdrop).
# L'admin (déployeur/opérateur) ne compte pas : "ça ne compte pas pour lui".
ADMIN_ADDRESS = "xet:czr9q8k5xlzqdptq7n2vapyjfduldts6tw3e6apl99vknzvmu4zsq8z9j8v"
EXCLUDE_ADDRS = {ADMIN_ADDRESS}

# ---------------------------------------------------------------------------
# Contrats du protocole -> hash actif (deployment_state.json / protocol.py)
# ---------------------------------------------------------------------------
CONTRACT_HASHES = {
    "AirdropTracker": "ef896baa1c88d64462500b48c8a6d0fb47b92b46718d1949c79d8d0268769dca",
    "AssetVault": "e65d593b5818af605caffbc5c56dbf2ee966b8b7baad18e165a6012b7f7343df",
    "ComplianceModule": "1c0f143207c24d3b3e7fd04000cd1425e498505171de45ca980238e9f71c7f4a",
    "ContractRegistry": "19161543b9e5aef00c5a3e226058b946d847c78941f0c89e9b996c6332204970",
    "FaucetContract": "ed6e2f58c9a98bd098534efce6f430a3b2abb77cf015e5e5b193c4f37d7e16a4",
    "FeeDistributor": "c7e23f4cbe34ecb411811e7edbdbd55e428f2884b36d067be94ca4ca425491f7",
    "FlashCallback": "a84fc6d305b4ed1a6e15c310461799172272ec1cabf209316e724c3ede420f40",
    "FlashLoan": "3e3ae983175a1f97013963803d977dd39a3b525c1778cb4cd4e3c4858e2b5ef8",
    "GovernanceVault": "1e0408c02b99eeca65399033d16330e0af936525dd41fd860980e214f59d5da5",
    "Governor": "eb7a1aea5518ddeff6ab7379d9abe854969b690928124314ba378e5073c154b9",
    "GuardianMultisig": "9792a5894877a5982c9efdfb91f94c1536fe5f21c017a56c59691776413e4929",
    "LendingMarket": "cb8f489382368b2f1b27bffcba346ede50aa180ebefac89ac444995bc95255bc",
    "MinerPool": "de744e0ccf45252070eb8fe83d0d16d36736ab7af1014a69405f358fb63c439b",
    "OracleGovernance": "bab86ca4a01c3250ce90b5c5d569b87ab221a212321848e104eb89500c28c953",
    "PSM": "977ddf73305dd21c29ffbe69dc2bdb29a12a62f4ff8bbc3140cafd4b51d5c2e1",
    "Payroll": "44ce12fb3d143f360c84664fe4849f01fb31ce5b45aebda38b037c70b4079b30",
    "PeerLoan": "ee27ecae9d8bb9b600026e883506eac39d81e5c908cca9dfeb6d96b529117568",
    "PrivacyMixer": "ffd504e24caad25b8f74e512318a66c45229dc2702dec0ecf66540065690d2d5",
    "RevenueShare": "49c363dae4d32473d6d3c26ce0482cf735f7d656c665094002c1d21a6978c94b",
    "SavingsRate": "69d719949fd8f25fc33c8d4e8d9da6d8cb30f63a0163e39e1c9de79129d86f27",
    "SealedBidAuction": "105bb6ccdb14f8cd34da78b85ed36790b29b2625d168297aa4294d3a557c46eb",
    "StakedOracle": "e89bc25043c320fdac9c2030bc99e4b5bd94c9e0043132d10f66cd93576fa515",
    "SyndicatePool": "e1622bb0c1dace2c0b008a8448f2ade7df7eeb898410aa7f3355bf57bb48a0ae",
    "Timelock": "b925d8e30ccd7bcffdc1376a6aecd8daaaa71603a3d0a4c9413d9e4a8ed11082",
    "TreasuryVault": "c50042aa59703bb1c73ffa0ffcb01f23b8ae8419d1e23b2892b9dcf9dde0a886",
    "VLTToken": "020f228fbd61e3a6cd2d570083e14c02f7073f293c79ee4059359b896e217d84",
    "VaultChat": "54fbd12e40b5e039b9a1c7c0b9475cebc0fd77ec72cbf35a9551712a59ea0bbd",
    "VaultEngineV3": "dcefbd7bd5de056247b3e4195d52df42b32fa510361cd1dc31ed115d65450e48",
    "VaultSwapV2": "5defc37154200f1cabb5b5fa43510565ab791e34b20f2cf4132ec7d9ac4e2041",
    "XelisVaultMiner": "6c70647e233dd634aa05cd6bdca06b521947c4c682d7decac0700d8a79d4b024",
    "xUSD": "4836190ca2f2278cfc3e8ad8c7e05bbd0070de253c64615f6eea2c19885063a1",
}

# Vieilles instances (hash antérieurs encore présents dans certains blocs) -> contract
LEGACY_HASHES = {
    "844cab735a8156f55c3055c2ff56a6824ad6d55b32f7dfb866655bde2bfa2054": "VaultEngineV3",
    "52cb2f100984319c7f41bbec03fb3e7679279eafdd4abb44ff5d8fdd7631cf97": "GovernanceVault",
    "608eec92282bcba466e88d7e70d616be5653e9a120997866d738838e783862c3": "Governor",
    "8d22d5cf83f411fc34846d0f36e86ffd2a0e19aca4fc65c5209647f53bf3b862": "Governor",
    "d384649c8f8f52116a198d2125bd1b6c3dff9bfda55643979c85a28631a6261d": "PrivacyMixer",
    "d54cc19be3d16a86a3849be4389e44a9c123ebb0042a88e94f4e91893f940ab8": "PrivacyMixer",
    "dcefbd7bd5de056247b3e4195d52df42b32fa510361cd1dc31ed115d65450e48": "VaultEngineV3",
    "5904a314ec3dfda55654647ea03c8b6d149102505f076006bc1cd36f7cc3e80b": "VaultChat",
    "73f7b78bef94c20a5115f8fdc9ed2cd8d8792cdb398f01a7f254163b30958e24": "VaultChat",
    "0169707c19522269e8126edf36066e2c83c384e8c31f8072667f7cfad06631ec": "FaucetContract",
    "1e0408c02b99eeca65399033d16330e0af936525dd41fd860980e214f59d5da5": "GovernanceVault",
}

_HASH_TO_NAME = {v: k for k, v in CONTRACT_HASHES.items()}
_HASH_TO_NAME.update(LEGACY_HASHES)

# v12: prefer the LIVE hashes from network/testnet.json (auto-adapts after
# a registry upgrade — old hashes move to LEGACY_HASHES below at runtime).
try:
    import json as _json
    from pathlib import Path as _Path
    _net = _json.loads((_Path(__file__).resolve().parent.parent
                        / "network" / "testnet.json").read_text())
    _KEY_TO_NAME = {
        "airdrop_tracker": "AirdropTracker", "asset_vault": "AssetVault",
        "compliance_module": "ComplianceModule",
        "contract_registry": "ContractRegistry", "faucet": "FaucetContract",
        "fee_distributor": "FeeDistributor", "flash_callback": "FlashCallback",
        "flash_loan": "FlashLoan", "governance_vault": "GovernanceVault",
        "governor": "Governor", "guardian_multisig": "GuardianMultisig",
        "lending_market": "LendingMarket", "miner_pool": "MinerPool",
        "oracle_governance": "OracleGovernance", "psm": "PSM",
        "payroll": "Payroll", "peer_loan": "PeerLoan",
        "privacy_mixer": "PrivacyMixer", "revenue_share": "RevenueShare",
        "savings_rate": "SavingsRate",
        "sealed_bid_auction": "SealedBidAuction",
        "staked_oracle": "StakedOracle", "syndicate_pool": "SyndicatePool",
        "timelock": "Timelock", "treasury_vault": "TreasuryVault",
        "vlt_token": "VLTToken", "vault_chat": "VaultChat",
        "vault_engine": "VaultEngineV3", "vault_swap": "VaultSwapV2",
        "miner": "XelisVaultMiner", "xusd": "xUSD",
    }
    for _k, _name in _KEY_TO_NAME.items():
        _h = _net.get("contracts", {}).get(_k)
        if _h:
            # any hash that differs from the table above is historical:
            # keep it mapped (LEGACY) and register the live one.
            if CONTRACT_HASHES.get(_name) and CONTRACT_HASHES[_name] != _h:
                LEGACY_HASHES[CONTRACT_HASHES[_name]] = _name
            CONTRACT_HASHES[_name] = _h
    _HASH_TO_NAME = {v: k for k, v in CONTRACT_HASHES.items()}
    _HASH_TO_NAME.update(LEGACY_HASHES)
except Exception as _e:  # network file missing — fall back to the table
    pass


# ---------------------------------------------------------------------------
# Grille de points : (catégorie, points, description, mode)
#   mode: "fixed" -> points fixes ; "xel" -> pointeurs calculés à partir d'un param
# ---------------------------------------------------------------------------
CATS = {
    "MINING":   {"id": 1},
    "RELAYER":  {"id": 2},
    "GOVERNANCE": {"id": 3},
    "CHAT":     {"id": 4},
    "LIQUIDITY": {"id": 5},
    "BOUNTY":   {"id": 6},
    "COMMUNITY": {"id": 7},
}

# Actions reconnues : hash contrat -> { entry_id(chunk) : (cat, pts, desc, extract_amount_index?) }
SCORE_MAP = {
    "VaultChat": {
        113: ("CHAT", 1, "send_direct_message"),
        38:  ("CHAT", 1, "store_message"),
        48:  ("CHAT", 1, "store_group_message"),
        7:   ("CHAT", 1, "store_ephemeral_message"),
        8:   ("CHAT", 100, "create_group"),
        9:   ("CHAT", 1, "add_group_member"),
        11:  ("RELAYER", 10, "anchor_messages"),
        66:  ("RELAYER", 50, "register_as_relayer"),
        51:  ("RELAYER", 5, "set_relayer_fee"),
        121: ("RELAYER", 5, "stake_relayer_bond"),
    },
    "Governor": {
        4:  ("GOVERNANCE", 50, "vote"),
        3:  ("GOVERNANCE", 500, "propose"),
    },
    "GovernanceVault": {
        4: ("GOVERNANCE", 5, "stake"),
    },
    "StakedOracle": {
        16: ("MINING", 1, "submit_price"),
    },
    "XelisVaultMiner": {
        21: ("MINING", 50, "submit_heartbeat"),
        15: ("MINING", 10, "register_miner"),
    },
    "VaultEngineV3": {
        # param[0] = montant XEL déposé (deposit prend l'adresse + amount)
        17: ("LIQUIDITY", "xel_param0", "deposit"),
        18: ("LIQUIDITY", 0, "borrow"),   # borrow = pas de nouveau XEL provisionné
    },
    "PSM": {
        # param[0] = montant XEL -> xUSD
        8: ("LIQUIDITY", "xel_param0", "mint"),
    },
    "VaultSwapV2": {
        17: ("LIQUIDITY", "xel_param0", "add_liquidity"),
    },
    "SavingsRate": {
        8: ("LIQUIDITY", "xel_param0", "deposit"),
    },
    "PrivacyMixer": {
        6: ("LIQUIDITY", "xel_param1", "deposit"),  # deposit(asset, amount) -> amount en param[1]
    },
}


# ---------------------------------------------------------------------------
# RPC
# ---------------------------------------------------------------------------
class RpcError(Exception):
    pass


def rpc(url: str, method: str, params, max_retries: int = 6) -> dict:
    body = json.dumps({"jsonrpc": "2.0", "method": method, "params": params, "id": 1}).encode()
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    }
    delay = 1.0
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url, data=body, headers=headers)
            with urllib.request.urlopen(req, timeout=40) as resp:
                data = json.load(resp)
            if "error" in data:
                raise RpcError(str(data["error"]))
            return data.get("result")
        except urllib.error.HTTPError as e:
            # 429/403/5xx -> backoff
            if e.code in (429, 403, 500, 502, 503, 504):
                time.sleep(delay)
                delay = min(delay * 2, 20)
                continue
            raise
        except (urllib.error.URLError, RpcError, TimeoutError, OSError, json.JSONDecodeError) as e:
            if attempt == max_retries - 1:
                raise
            time.sleep(delay)
            delay = min(delay * 2, 20)
    raise RpcError(f"failed after {max_retries} retries")


def get_topoheight(url: str) -> int:
    info = rpc(url, "get_info", None)
    return info["topoheight"]


def get_block(url: str, topo: int) -> dict:
    return rpc(url, "get_block_at_topoheight", {"topoheight": topo})


def get_tx(url: str, tx_hash: str) -> dict:
    return rpc(url, "get_transaction", {"hash": tx_hash})


def parse_param(cell) -> object:
    """Extrait une valeur simple d'un param ValueCell (best effort)."""
    if not isinstance(cell, dict):
        return cell
    if cell.get("type") == "primitive":
        v = cell.get("value", {})
        vv = v.get("value")
        if isinstance(vv, dict):
            return vv.get("value", vv)
        return vv
    return None


# ---------------------------------------------------------------------------
# Points par adresse
# ---------------------------------------------------------------------------
class PointsBook:
    def __init__(self):
        # addr -> { cat -> points }, et objets de suivi pour la reprise
        self.by_addr = defaultdict(lambda: defaultdict(int))
        self.days_active = defaultdict(set)
        self.activity = []          # list of dicts (détail, pour audit)
        self.tx_seen = set()        # hash de tx déjà traitées (reprise)
        self.last_topo = 0

    def add(self, addr: str, cat: str, pts: float, desc: str, topo: int, tx: str):
        if pts <= 0:
            return
        if addr in EXCLUDE_ADDRS or not addr:
            return
        self.by_addr[addr][cat] += pts
        day = topo // 720  # ~1 jour en blocs (≈2.7s * 720)
        self.days_active[addr].add(day)
        if len(self.activity) < 200000:
            self.activity.append({
                "addr": addr, "cat": cat, "pts": pts,
                "desc": desc, "topo": topo, "tx": tx[:16],
            })

    def total(self, addr: str) -> float:
        return sum(self.by_addr[addr].values())

    def category_count(self, addr: str) -> int:
        return sum(1 for v in self.by_addr[addr].values() if v > 0)


def format_addr(addr: str) -> str:
    return addr if addr else ""


# ---------------------------------------------------------------------------
# Scan d'un bloc
# ---------------------------------------------------------------------------
def score_block(book: PointsBook, url: str, block: dict, _tmp_tx_cache: dict = None):
    txs = block.get("txs_hashes") or []
    miner = block.get("miner")
    topo = block.get("topoheight")
    # MINING : bloc PoW miné -> le miner gagne 1 pt
    if miner:
        book.add(miner, "MINING", 1, "block_mined", topo, block.get("hash", "")[:16])
    # fetch les txs (concurrent si on passe un thread pool via le cache en mode batch)
    for tx_hash in txs:
        if tx_hash in book.tx_seen:
            continue
        book.tx_seen.add(tx_hash)
        if _tmp_tx_cache is not None and tx_hash in _tmp_tx_cache:
            tx = _tmp_tx_cache[tx_hash]
        else:
            try:
                tx = get_tx(url, tx_hash)
            except Exception:
                continue
        _score_tx(book, tx, topo, tx_hash)


def _score_tx(book: PointsBook, tx: dict, topo: int, tx_hash: str):
    if not tx:
        return
    data = tx.get("data", {})
    ic = data.get("invoke_contract")
    if not ic:
        return
    contract = ic.get("contract")
    entry_id = ic.get("entry_id")
    source = tx.get("source")
    name = _HASH_TO_NAME.get(contract)
    if not name:
        return
    rule = SCORE_MAP.get(name)
    if not rule:
        return
    action = rule.get(entry_id)
    if not action:
        return
    cat, pts, desc = action
    result_pts = pts
    if isinstance(pts, str) and pts.startswith("xel_param"):
        idx = int(pts.replace("xel_param", ""))
        params = ic.get("parameters") or []
        val = parse_param(params[idx]) if idx < len(params) else None
        try:
            result_pts = float(val) / (10 ** XEL_DECIMALS) * 10.0
        except (TypeError, ValueError):
            result_pts = 0.0
    book.add(source or "", cat, result_pts, desc, topo, tx_hash)


def scan_range(book: PointsBook, url: str, start: int, end: int,
               workers: int = 8, sleep: float = 0.0,
               on_progress=None):
    """Scanne [start..end] de façon concurrente pour les blocs, batchant les txs."""
    done = start - 1
    total = end - start + 1
    t0 = time.time()

    def fetch_block(t):
        # retries avec backoff gérés par rpc(); sur échec définitif on retourne un marker
        try:
            return t, get_block(url, t)
        except Exception:
            return t, None

    # on traite par lots pour garder un progress lisible et un checkpoint régulier
    BATCH = workers * 4
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        for batch_start in range(start, end + 1, BATCH):
            batch_end = min(end + 1, batch_start + BATCH)
            futures = {ex.submit(fetch_block, t): t for t in range(batch_start, batch_end)}
            batch_blocks = []
            for fut in concurrent.futures.as_completed(futures):
                try:
                    batch_blocks.append(fut.result())
                except Exception:
                    batch_blocks.append((futures[fut], None))
            # réessayer les blocs échoués en séquentiel (pause si rate-limit)
            failed = [t for t, b in batch_blocks if b is None]
            for t in failed:
                for attempt in range(4):
                    try:
                        blk = get_block(url, t)
                        if blk:
                            batch_blocks.append((t, blk))
                            break
                    except Exception:
                        time.sleep(5 * (attempt + 1))
                if not any(bb for bb in batch_blocks if bb[0] == t and bb[1] is not None):
                    print(f"[warn] topo {t} injoignable après retries — ignoré")
            batch_blocks = [bb for bb in batch_blocks if bb[0] not in failed or
                            (bb[0] in failed and bb[1] is not None)]
            # collecter toutes les txs du lot pour les fetch en concurrence
            new_tx = {}
            present = {t: b for t, b in batch_blocks if b is not None}
            for t, blk in present.items():
                for th in (blk.get("txs_hashes") or []):
                    if th not in book.tx_seen:
                        new_tx[th] = None
            missing = [th for th, v in new_tx.items() if v is None]
            if missing:
                with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as tex:
                    results = list(tex.map(lambda h: (h, get_tx(url, h)), missing))
                for h, tx in results:
                    new_tx[h] = tx
            # score
            for t, blk in sorted(present.items()):
                cache = {h: new_tx[h] for h in (blk.get("txs_hashes") or []) if h in new_tx}
                try:
                    score_block(book, url, blk, _tmp_tx_cache=cache or None)
                except Exception as e:
                    print(f"[err] score topo {t}: {e}")
                book.last_topo = t
                done += 1
                if on_progress:
                    on_progress(done, total, t, time.time() - t0)
            if sleep:
                time.sleep(sleep)


# ---------------------------------------------------------------------------
# Checkpoint
# ---------------------------------------------------------------------------
def load_checkpoint(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            pass
    return {
        "last_topo": 0,
        "tx_seen": [],
        "by_addr": {},       # {"addr": {cat: pts}}
        "days_active": {},   # {"addr": [day,...]}
    }


def save_checkpoint(path: Path, book: PointsBook):
    ck = {
        "last_topo": book.last_topo,
        "tx_seen": list(book.tx_seen),
        "by_addr": {a: dict(c) for a, c in book.by_addr.items()},
        "days_active": {a: list(d) for a, d in book.days_active.items()},
    }
    path.write_text(json.dumps(ck))


def book_from_checkpoint(ck: dict) -> PointsBook:
    book = PointsBook()
    book.last_topo = ck.get("last_topo", 0)
    book.tx_seen = set(ck.get("tx_seen") or [])
    for a, cats in (ck.get("by_addr") or {}).items():
        if a in EXCLUDE_ADDRS or not a:
            continue
        for cat, pts in cats.items():
            book.by_addr[a][cat] = pts
    for a, days in (ck.get("days_active") or {}).items():
        if a in EXCLUDE_ADDRS or not a:
            continue
        book.days_active[a] = set(days)
    return book


# ---------------------------------------------------------------------------
# Sorties
# ---------------------------------------------------------------------------
def write_leaderboard(book: PointsBook, out_json: Path, out_csv: Path):
    rows = []
    for addr, cats in book.by_addr.items():
        if not addr:
            continue
        row = {"address": addr, "categories": dict(cats),
               "total": round(book.total(addr), 4),
               "cat_count": book.category_count(addr),
               "days_active": len(book.days_active[addr])}
        rows.append(row)
    rows.sort(key=lambda r: -r["total"])
    # classement + total général
    total_all = round(sum(r["total"] for r in rows), 4)
    # qualification (plan) : >=1000 pts & >=7 jours actifs
    for i, r in enumerate(rows, 1):
        r["rank"] = i
        r["qualified"] = bool(r["total"] >= 1000 and r["days_active"] >= 7)
        r["share"] = round(r["total"] / total_all, 6) if total_all > 0 else 0.0
    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "window_topos_scanned": book.last_topo,
        "total_points_all_users": total_all,
        "qualified_users": sum(1 for r in rows if r["qualified"]),
        "users": len(rows),
        "leaderboard": rows,
        "category_totals": {
            cat: round(sum(r["categories"].get(cat, 0) for r in rows), 4)
            for cat in CATS
        },
    }
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(output, indent=2))
    if out_csv:
        with open(out_csv, "w") as f:
            f.write("rank,address,total,cat_count,days_active,qualified,share,"
                    "mining,relayer,governance,chat,liquidity\n")
            for r in rows:
                c = r["categories"]
                f.write("{},{},{},{},{},{},{},{},{},{},{},{}\n".format(
                    r["rank"], r["address"], r["total"], r["cat_count"],
                    r["days_active"], int(r["qualified"]), r["share"],
                    c.get("MINING", 0), c.get("RELAYER", 0),
                    c.get("GOVERNANCE", 0), c.get("CHAT", 0), c.get("LIQUIDITY", 0)))
    return output


# ---------------------------------------------------------------------------
# Daemon continu (lit en permanence les nouveaux blocs)
# ---------------------------------------------------------------------------
def run_daemon(book: PointsBook, args, ck_path: Path, out_json: Path, out_csv):
    """Boucle infinie : scanne les nouveaux blocs en continu, ré-écrit
    régulièrement le leaderboard (admin exclu), checkpoint après chaque scan."""
    print(f"[daemon] démarre (workers={args.workers}, poll={args.poll_interval}s)")
    print(f"[daemon] adresses exclues du scoring: {sorted(EXCLUDE_ADDRS)}")
    last_write = 0.0
    while True:
        try:
            topo = get_topoheight(args.rpc)
            if topo > book.last_topo:
                start = book.last_topo + 1
                print(f"[daemon] nouveaux blocs: scan {start}..{topo} "
                      f"({topo - start + 1} blocs)")
                def on_progress(done, total, t, elapsed):
                    nonlocal last_write
                    if time.time() - last_write > 20:
                        save_checkpoint(ck_path, book)
                    if done % 500 == 0 or done == total:
                        print(f"[daemon] {t}/{topo} · {len(book.by_addr)} adresses, "
                              f"{len(book.tx_seen)} txs")
                scan_range(book, args.rpc, start, topo, workers=args.workers,
                           sleep=args.sleep, on_progress=on_progress)
            # ré-écrire le leaderboard périodiquement (même sans nouveaux blocs)
            if time.time() - last_write > args.write_interval or topo <= book.last_topo:
                save_checkpoint(ck_path, book)
                out = write_leaderboard(book, out_json, out_csv)
                print(f"[daemon] leaderboard écrit: {out['users']} users, "
                      f"{out['qualified_users']} qualifiés, "
                      f"total={out['total_points_all_users']} (topo {book.last_topo})")
                last_write = time.time()
        except KeyboardInterrupt:
            save_checkpoint(ck_path, book)
            write_leaderboard(book, out_json, out_csv)
            print("[daemon] arrêt")
            break
        except Exception as e:
            print(f"[daemon] erreur: {e}; retry dans {args.poll_interval}s")
        time.sleep(args.poll_interval)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Indexer airdrop off-chain (scan rétroactif)")
    ap.add_argument("--rpc", default=PUBLIC_NODE,
                    help="Endpoint JSON-RPC du daemon (défaut: nœud public)")
    ap.add_argument("--window", type=int, default=50000,
                    help="Nombre de blocs rétroactifs à scanner (défaut 50000)")
    ap.add_argument("--checkpoint", default=str(
        Path.home() / ".xelis-vault" / "airdrop_index_ckpt.json"))
    ap.add_argument("--out-json", default=str(
        Path.home() / ".xelis-vault" / "airdrop_leaderboard.json"))
    ap.add_argument("--out-csv", default="")
    ap.add_argument("--resume", action="store_true",
                    help="Reprendre depuis le checkpoint (sinon repart de zéro)")
    ap.add_argument("--sleep", type=float, default=0.0,
                    help="Pause secondes entre lots (anti rate-limit)")
    ap.add_argument("--workers", type=int, default=8,
                    help="Concurrence pour les requêtes RPC (défaut 8)")
    ap.add_argument("--daemon", action="store_true",
                    help="Mode continu : lit en boucle les nouveaux blocs (s'arrête jamais)")
    ap.add_argument("--poll-interval", type=float, default=15.0,
                    help="Poll des nouveaux blocs en secondes (mode daemon, défaut 15)")
    ap.add_argument("--write-interval", type=float, default=300.0,
                    help="Ré-écrire le leaderboard toutes les N secondes (mode daemon, défaut 300)")
    args = ap.parse_args()

    ck_path = Path(args.checkpoint)
    if args.resume and ck_path.exists():
        ck = load_checkpoint(ck_path)
        book = book_from_checkpoint(ck)
        print(f"[resume] repris au topo {book.last_topo} ({len(book.tx_seen)} txs déjà vues)")
    else:
        book = PointsBook()
        print("[fresh] nouveau scan")

    if args.daemon:
        run_daemon(book, args, ck_path, Path(args.out_json), args.out_csv)
        return

    topo = get_topoheight(args.rpc)
    start = max(1, topo - args.window)
    if book.last_topo < start:
        book.last_topo = start - 1  # on va scanner à partir de start

    print(f"topo actuel: {topo} | fenêtre: {args.window} | scan {start}..{topo} "
          f"(workers={args.workers})")
    last_save = time.time()

    def on_progress(done, total, t, elapsed):
        nonlocal last_save
        if time.time() - last_save > 20:
            save_checkpoint(ck_path, book)
            last_save = time.time()
        if done % 200 == 0 or done == total:
            rate = done / elapsed if elapsed > 0 else 0
            eta = (total - done) / rate / 3600 if rate > 0 else 0
            print(f"[{t}/{topo}] {done}/{total} blocs, "
                  f"{len(book.by_addr)} adresses, {len(book.tx_seen)} txs, "
                  f"{rate:.1f} blk/s, ETA {eta:.1f}h")

    scan_range(book, args.rpc, start, topo, workers=args.workers,
               sleep=args.sleep, on_progress=on_progress)

    save_checkpoint(ck_path, book)
    out = write_leaderboard(book, Path(args.out_json), args.out_csv)
    print("\n=== RÉSULTAT ===")
    print(f"users: {out['users']} | total points: {out['total_points_all_users']} | "
          f"qualifiés: {out['qualified_users']}")
    print(f"catégories: {out['category_totals']}")
    print(f"JSON: {args.out_json}")
    if args.out_csv:
        print(f"CSV : {args.out_csv}")
    print("\nTop 10:")
    for r in out["leaderboard"][:10]:
        print(f"  #{r['rank']:>3} {r['address']}  total={r['total']:>10}  "
              f"cats={r['cat_count']}  days={r['days_active']}  q={'Y' if r['qualified'] else 'N'}")


if __name__ == "__main__":
    main()
