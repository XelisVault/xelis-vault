#!/usr/bin/env python3
"""
============================================================================
 XELIS Vault — Protocol Client (protocol.py)
============================================================================
Canonical on-chain interaction layer for the deployed XELIS Vault protocol.

- Wallet RPC (build_transaction / invoke_contract + deposits) for writes
- Daemon RPC (get_contract_data, get_asset, get_contract_logs) for reads
- Registry resolution (cur_<Name>) with fallback to deployed-hash table
- Entry chunk-id map (docs/entry_chunk_ids.json) — entry_id = compiled chunk
- Op wrappers for every externally-invokable protocol flow

Live environment (testnet):
  daemon  http://127.0.0.1:18081/json_rpc
  wallet  http://127.0.0.1:18082/json_rpc  (basic auth wallet:testpass)
============================================================================
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any, Optional

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS = REPO_ROOT / "docs"

# ---------------------------------------------------------------------------
# Live environment
# ---------------------------------------------------------------------------
DAEMON_URL = "http://127.0.0.1:18081/json_rpc"
WALLET_URL = "http://127.0.0.1:18082/json_rpc"
WALLET_AUTH = ("wallet", "testpass")

ZERO_HASH = "0" * 64

ADMIN = "xet:czr9q8k5xlzqdptq7n2vapyjfduldts6tw3e6apl99vknzvmu4zsq8z9j8v"

# Canonical asset hashes (verified on-chain)
XEL_ASSET = ZERO_HASH                      # native XELIS (8 decimals)
VLT_ASSET = "3f1f9a3c0a90a0a548670a069e8edad5c0c20914b20b289426b2857c6715f58f"
XUSD_ASSET = "be39794c4a32f231d410c8be3a4d9e80455c667d902c5edf8527dea52533356e"

ASSET_NAMES = {
    XEL_ASSET: "XEL",
    VLT_ASSET: "VLT",
    XUSD_ASSET: "xUSD",
}

DECIMALS = {XEL_ASSET: 8, VLT_ASSET: 8, XUSD_ASSET: 8}

# Registered contract hashes (deploy log — registry cur_<Name> is authoritative)
CONTRACT_HASHES = {
    "AirdropTracker": "ef896baa1c88d64462500b48c8a6d0fb47b92b46718d1949c79d8d0268769dca",
    "AssetVault": "e65d593b5818af605caffbc5c56dbf2ee966b8b7baad18e165a6012b7f7343df",
    "ComplianceModule": "1c0f143207c24d3b3e7fd04000cd1425e498505171de45ca980238e9f71c7f4a",
    "ContractRegistry": "19161543b9e5aef00c5a3e226058b946d847c78941f0c89e9b996c6332204970",
    "FaucetContract": "ed6e2f58c9a98bd098534efce6f430a3b2abb77cf015e5e5b193c4f37d7e16a4",
    "FeeDistributor": "c7e23f4cbe34ecb411811e7edbdbd55e428f2884b36d067be94ca4ca425491f7",
    "FlashCallback": "a84fc6d305b4ed1a6e15c310461799172272ec1cabf209316e724c3ede420f40",
    "FlashLoan": "3e3ae983175a1f97013963803d977dd39a3b525c1778cb4cd4e3c4858e2b5ef8",
    "FounderVesting": "fa07e6f5b5273c6d48994e846a05363099366661c4128f76b1fe41d15d1055a4",
    "FounderVesting10y": "fa07e6f5b5273c6d48994e846a05363099366661c4128f76b1fe41d15d1055a4",
    "FounderVesting4y": "fa07e6f5b5273c6d48994e846a05363099366661c4128f76b1fe41d15d1055a4",
    "GovernanceVault": "1e0408c02b99eeca65399033d16330e0af936525dd41fd860980e214f59d5da5",
    "Governor": "eb7a1aea5518ddeff6ab7379d9abe854969b690928124314ba378e5073c154b9",
    "GuardianMultisig": "9792a5894877a5982c9efdfb91f94c1536fe5f21c017a56c59691776413e4929",
    "InterestRateModel": "e9f716b07628fb8793adf3e20142348082a5021d671f316dad1e02cfb70f9c6d",
    "LendingMarket": "cb8f489382368b2f1b27bffcba346ede50aa180ebefac89ac444995bc95255bc",
    "MinerDelegation": "5eb34079fd84ee3626e410c0e9cbf5d568c76cabeaf36c0d00b5e21693033685",
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

# Oracle feed ids
FEED_XEL_USD = 0
FEED_IDS = {FEED_XEL_USD: "XEL/USD"}
FEED_ASSETS = {FEED_XEL_USD: XEL_ASSET}
FEED_DECIMALS = {FEED_XEL_USD: 8}

# Miner service ids (XelisVaultMiner.register_service)
SERVICE_ORACLE = 1
SERVICE_CHAT = 2

MIN_STAKE_VLT = 100_000_000_000  # 1000 VLT (v10.7 anti-Sybil)

TX_CONFIRM_TIMEOUT = 120
INVOKE_FEE = 10_000_000        # 0.1 XEL
DEPLOY_FEE = 100_000_000       # 1 XEL
INVOKE_GAS = 5_000_000
HEAVY_GAS = 10_000_000


# ---------------------------------------------------------------------------
# ValueCell builders (adjacently tagged)
# ---------------------------------------------------------------------------
def _prim(t: str, v: Any) -> dict:
    return {"type": "primitive", "value": {"type": t, "value": v}}


def val_u64(n: int) -> dict:
    return _prim("u64", str(n))


def val_u128(n: int) -> dict:
    return _prim("u128", str(n))


def val_u8(n: int) -> dict:
    return _prim("u8", int(n))


def val_u16(n: int) -> dict:
    return _prim("u16", int(n))


def val_bool(b: bool) -> dict:
    return _prim("boolean", bool(b))


def val_str(s: str) -> dict:
    return _prim("string", s)


def val_hash(hexstr: str) -> dict:
    return _prim("opaque", {"type": "Hash", "value": hexstr})


def val_addr(addr: str) -> dict:
    return _prim("opaque", {"type": "Address", "value": addr})


def val_bytes(hexstr: str) -> dict:
    return {"type": "bytes", "value": hexstr}


def parse_cell(cell: dict) -> Any:
    """Parse a ValueCell into a python value (best effort)."""
    if not isinstance(cell, dict):
        return cell
    t = cell.get("type")
    if t == "primitive":
        v = cell.get("value", {})
        vt = v.get("type")
        val = v.get("value")
        if vt in ("u8", "u16", "u32"):
            return int(val)
        if vt in ("u64", "u128", "amount", "balance", "nonce", "fee"):
            try:
                return int(val)
            except (TypeError, ValueError):
                return val
        if vt == "boolean":
            return bool(val)
        if vt == "string":
            return val
        if vt == "opaque":
            # nested type: Hash / Address / PublicKey / ...
            if isinstance(val, dict):
                return val.get("value", val)
            return val
        return val
    if t == "bytes":
        return cell.get("value")
    if t == "object":
        # custom struct — return list of parsed field values
        items = cell.get("value") or []
        return [parse_cell(i) for i in items]
    return cell


# ---------------------------------------------------------------------------
# Entry chunk-id map
# ---------------------------------------------------------------------------
_ENTRY_MAP: Optional[dict] = None

# Registry names -> entry-chunk map keys (registry name != source module name
# for some contracts: the registry keeps deploy names, the chunk map is keyed
# by the compiled module's source name).
_ENTRY_ALIASES = {
    "VaultEngine": "VaultEngineV3",
    "VaultSwap": "VaultSwapV2",
    "FounderVesting4y": "FounderVesting",
    "FounderVesting10y": "FounderVesting",
}


def _entry_key(name: str) -> str:
    return _ENTRY_ALIASES.get(name, name)


def entry_map() -> dict:
    global _ENTRY_MAP
    if _ENTRY_MAP is None:
        path = DOCS / "entry_chunk_ids.json"
        if not path.exists():
            raise RuntimeError(f"entry chunk map not found: {path}")
        try:
            _ENTRY_MAP = json.loads(path.read_text())
        except Exception as e:
            raise RuntimeError(f"invalid entry chunk map {path}: {e}")
    return _ENTRY_MAP


def entry_id(contract_name: str, fn: str) -> int:
    m = entry_map().get(_entry_key(contract_name))
    if not m:
        raise RuntimeError(f"no entry map for contract {contract_name}")
    if fn not in m:
        raise RuntimeError(f"{contract_name}.{fn} is not an Entry chunk "
                          f"(All/pub-fn chunks are not wallet-invokable)")
    return m[fn]


def list_entries(contract_name: str) -> dict:
    return entry_map().get(contract_name, {})


# ---------------------------------------------------------------------------
# RPC clients
# ---------------------------------------------------------------------------
class RPCError(RuntimeError):
    """RPC failure. transient=True when a retry after a short sleep can fix it
    (nonce race, proof-verification race, temporary storage miss)."""

    def __init__(self, msg: str, transient: bool = False):
        super().__init__(msg)
        self.transient = transient


def _is_transient(method: str, err: dict) -> bool:
    msg = str(err.get("message", "")).lower()
    if "nonce" in msg and ("already used" in msg or "expected" in msg):
        return True
    if "proof verification error" in msg:
        return True
    if "not enough funds" in msg:
        return False  # permanent — funding required, retrying won't help
    if method == "get_transaction" and "not found" in msg:
        return False
    # v12.1: a contract was just deployed -> the wallet may not know it
    # yet before the block stabilizes. Retry after a few seconds.
    if "contract not found" in msg:
        return True
    return False


def _post(url: str, method: str, params: Any, auth: Optional[tuple] = None,
          timeout: int = 8) -> Any:
    payload: dict = {"jsonrpc": "2.0", "method": method, "id": 1}
    if params is not None:
        payload["params"] = params
    last_exc: Optional[Exception] = None
    for attempt in range(3):        # public nodes may answer HTML (rate limit / CF)
        try:
            r = requests.post(url, auth=auth, json=payload, timeout=timeout)
            if r.status_code == 401:
                raise RPCError(f"{method}: 401 Unauthorized from {url} — check wallet RPC username/password",
                               transient=False)
            data = r.json()
            if data.get("error"):
                err = data["error"]
                raise RPCError(f"{method}: {err}",
                               transient=_is_transient(method, err))
            return data.get("result")
        except ValueError as e:     # non-JSON body — retry after a pause
            last_exc = e
            time.sleep(2 * (attempt + 1))
    raise RPCError(f"{method}: non-JSON response from {url}",
                   transient=True) from last_exc


def _with_retries(fn, attempts: int = 4, delay: float = 8.0):
    """Run fn(); retry on transient RPC errors (nonce / proof races)."""
    last: Optional[Exception] = None
    for i in range(attempts):
        try:
            return fn()
        except RPCError as e:
            if not e.transient:
                raise
            last = e
            time.sleep(delay)
        except requests.RequestException as e:
            last = e
            time.sleep(delay)
    raise last


class WalletClient:
    """xelis_wallet v1.25 — build_transaction (flattened TransactionTypeBuilder)."""

    def __init__(self, url: str = WALLET_URL, auth: tuple = WALLET_AUTH):
        self.url = url
        self.auth = auth

    def _call(self, method: str, params: Any = None) -> Any:
        return _post(self.url, method, params, auth=self.auth)

    def address(self) -> str:
        return self._call("get_address")

    def balance(self, asset: str = XEL_ASSET) -> int:
        return int(self._call("get_balance", {"asset": asset}))

    def track_asset(self, asset: str) -> None:
        self._call("track_asset", {"asset": asset})

    def invoke(self, contract: str, entry: int, params: Optional[list] = None,
               deposits: Optional[dict] = None, max_gas: int = INVOKE_GAS,
               fee: int = INVOKE_FEE, broadcast: bool = True) -> str:
        """Build + broadcast an invoke_contract transaction. Returns tx hash.

        Waits for the wallet's stored nonce to catch up with the daemon
        (the wallet syncs its nonce lazily), then retries on nonce /
        proof-verification races."""
        self._wait_nonce_catchup()

        def _build() -> str:
            payload = {
                "invoke_contract": {
                    "contract": contract,
                    "max_gas": max_gas,
                    "entry_id": entry,
                    "parameters": params or [],
                    "deposits": deposits or {},
                    "permission": "all",
                },
                "fee": {"fixed": fee},
                "broadcast": broadcast,
            }
            result = self._call("build_transaction", payload)
            tx_hash = result.get("hash") if isinstance(result, dict) else None
            if not tx_hash:
                raise RPCError(f"build_transaction returned no hash: {result}")
            return tx_hash
        tx = _with_retries(_build)
        # wait for wallet nonce to advance (confirms tx was processed)
        self.wait_nonce_advance(int(self._call("get_nonce")), timeout=180)
        return tx

    def wait_nonce_advance(self, before: int, timeout: int = 120) -> int:
        """Wait until the wallet's stored nonce advances past `before`."""
        t0 = time.time()
        while time.time() - t0 < timeout:
            n = int(self._call("get_nonce"))
            if n > before:
                return n
            time.sleep(5)
        return int(self._call("get_nonce"))

    def _wait_nonce_catchup(self, timeout: int = 120) -> None:
        """Wait until the wallet's stored nonce >= the daemon's account nonce."""
        addr = self.address()
        t0 = time.time()
        while time.time() - t0 < timeout:
            try:
                w = int(self._call("get_nonce"))
                d = int(_post(DAEMON_URL, "get_nonce",
                              {"address": addr}).get("nonce", 0))
                if w >= d:
                    return
            except Exception:
                pass
            time.sleep(5)

    def transfer(self, to: str, amount: int, asset: str = XEL_ASSET,
                 fee: int = INVOKE_FEE) -> str:
        self._wait_nonce_catchup()

        def _build() -> str:
            payload = {
                "transfers": [{"destination": to, "amount": amount,
                               "asset": asset}],
                "fee": {"fixed": fee},
                "broadcast": True,
            }
            result = self._call("build_transaction", payload)
            tx_hash = result.get("hash") if isinstance(result, dict) else None
            if not tx_hash:
                raise RPCError(f"transfer returned no hash: {result}")
            return tx_hash
        return _with_retries(_build)


class DaemonClient:
    def __init__(self, url: str = DAEMON_URL):
        self.url = url

    def _call(self, method: str, params: Any = None) -> Any:
        return _post(self.url, method, params)

    def topoheight(self) -> int:
        return int(self._call("get_topoheight"))

    def get_contract_data(self, contract: str, key: dict) -> Any:
        """Raw get_contract_data. Raises RPCError when key never set."""
        return self._call("get_contract_data",
                          {"contract": contract, "key": key})

    def read_key(self, contract: str, key_str: str) -> Any:
        """Read a string-keyed storage cell; returns parsed value or None."""
        try:
            res = self.get_contract_data(contract, val_str(key_str))
        except RPCError:
            return None
        data = res.get("data") if isinstance(res, dict) else None
        if data is None:
            return None
        return parse_cell(data)

    def read_hash_key(self, contract: str, key: dict) -> Any:
        try:
            res = self.get_contract_data(contract, key)
        except RPCError:
            return None
        data = res.get("data") if isinstance(res, dict) else None
        if data is None:
            return None
        return parse_cell(data)

    def get_asset(self, asset: str) -> Optional[dict]:
        try:
            return self._call("get_asset", {"asset": asset})
        except RPCError:
            return None

    def get_contract_balance(self, contract: str, asset: str) -> int:
        try:
            res = self._call("get_contract_balance",
                             {"contract": contract, "asset": asset})
        except RPCError:
            return 0
        if isinstance(res, dict):
            return int(res.get("data", 0))
        return int(res) if res else 0

    def get_transaction(self, tx_hash: str) -> Optional[dict]:
        try:
            return self._call("get_transaction", {"hash": tx_hash})
        except RPCError:
            return None

    def get_contract_logs(self, caller: str) -> list:
        try:
            res = self._call("get_contract_logs", {"caller": caller})
            return res if isinstance(res, list) else []
        except RPCError:
            return []


# ---------------------------------------------------------------------------
# Protocol facade
# ---------------------------------------------------------------------------
class Protocol:
    def __init__(self, wallet: Optional[WalletClient] = None,
                 daemon: Optional[DaemonClient] = None,
                 wallet_url: str = WALLET_URL,
                 wallet_auth: tuple = WALLET_AUTH,
                 daemon_url: str = DAEMON_URL):
        if wallet is None:
            wallet = WalletClient(url=wallet_url, auth=wallet_auth)
        if daemon is None:
            daemon = DaemonClient(url=daemon_url)
        self.wallet = wallet
        self.daemon = daemon
        self._registry_cache: dict[str, str] = {}

    # --- resolution --------------------------------------------------------
    def resolve(self, name: str) -> str:
        """Registry cur_<Name> first, then static deploy table."""
        name = name.replace("VaultEngineV3", "VaultEngine")
        if name in self._registry_cache:
            return self._registry_cache[name]
        h = self.daemon.read_key(CONTRACT_HASHES["ContractRegistry"],
                                 f"cur_{name}")
        if h:
            self._registry_cache[name] = h
            return h
        if name in CONTRACT_HASHES:
            return CONTRACT_HASHES[name]
        raise RuntimeError(f"cannot resolve contract {name}")

    def hash_of(self, name: str) -> str:
        return self.resolve(name)

    def entry(self, name: str, fn: str) -> int:
        return entry_id(name, fn)

    # --- reads -------------------------------------------------------------
    def read(self, name: str, key_str: str) -> Any:
        return self.daemon.read_key(self.resolve(name), key_str)

    def read_contract(self, contract_hash: str, key_str: str) -> Any:
        return self.daemon.read_key(contract_hash, key_str)

    def topoheight(self) -> int:
        return self.daemon.topoheight()

    def price(self, asset: str = XEL_ASSET) -> Optional[int]:
        """Aggregated XEL/USD price (fg_<feed_id> struct) — needs 3+ active miners."""
        oracle = self.resolve("StakedOracle")
        fid = FEED_XEL_USD
        agg = self.read_contract(oracle, f"fg_{fid}")
        if agg and isinstance(agg, list) and len(agg) >= 1:
            return int(agg[0])
        return None

    # --- writes ------------------------------------------------------------
    def invoke(self, name: str, fn: str, params: Optional[list] = None,
               deposits: Optional[dict] = None, max_gas: int = INVOKE_GAS,
               fee: int = INVOKE_FEE) -> str:
        contract = self.resolve(name)
        eid = self.entry(name, fn)
        return self.wallet.invoke(contract, eid, params, deposits,
                                  max_gas=max_gas, fee=fee)

    def invoke_hash(self, contract_hash: str, eid: int,
                    params: Optional[list] = None,
                    deposits: Optional[dict] = None,
                    max_gas: int = INVOKE_GAS, fee: int = INVOKE_FEE) -> str:
        return self.wallet.invoke(contract_hash, eid, params, deposits,
                                  max_gas=max_gas, fee=fee)

    def wait(self, tx_hash: str, timeout: int = TX_CONFIRM_TIMEOUT) -> dict:
        start = time.time()
        while time.time() - start < timeout:
            res = self.daemon.get_transaction(tx_hash)
            if res:
                return res
            time.sleep(3)
        raise TimeoutError(f"tx {tx_hash} not confirmed in {timeout}s")

    def confirm(self, tx_hash: str, label: str = "") -> str:
        self.wait(tx_hash)
        if label:
            print(f"[ok] {label}: {tx_hash[:16]}...")
        return tx_hash

    def revert_reason(self, tx_hash: str, timeout: float = 8.0) -> Optional[str]:
        """Return the contract revert message, or None on success/unknown.

        Logs are written asynchronously by the daemon after mining — poll
        until the exit entry appears (empty logs would otherwise be read as
        success)."""
        deadline = time.time() + timeout
        while True:
            try:
                logs = self.daemon.get_contract_logs(tx_hash)
            except RPCError:
                logs = []
            if isinstance(logs, list) and logs:
                for entry in logs:
                    if not isinstance(entry, dict):
                        continue
                    if entry.get("type") == "exit_error":
                        v = entry.get("value") or {}
                        err = v.get("err") if isinstance(v, dict) else None
                        if isinstance(err, dict):
                            return err.get("message") or str(err)
                        return str(err)
                    if entry.get("exit_error"):
                        return str(entry["exit_error"])
                return None
            if time.time() >= deadline:
                return None
            time.sleep(1.5)

    # --- balance helpers ----------------------------------------------------
    def balance(self, asset: str = XEL_ASSET) -> int:
        return self.wallet.balance(asset)

    def contract_balance(self, name: str, asset: str) -> int:
        return self.daemon.get_contract_balance(self.resolve(name), asset)

    def send(self, to: str, amount: int, asset: str = XEL_ASSET) -> str:
        return self.wallet.transfer(to, amount, asset)


# ---------------------------------------------------------------------------
# Op wrappers — Oracle
# ---------------------------------------------------------------------------
def oracle_submit_price(p: Protocol, price_atomic: int, feed_id: int = FEED_XEL_USD,
                        max_gas: int = 500_000, fee: int = 1_000_000) -> str:
    """StakedOracle.submit_price — caller must be an active miner (svc 1).
    Low fee/gas by default: submit_price uses very little gas."""
    return p.invoke("StakedOracle", "submit_price",
                    [val_u64(feed_id), val_u64(price_atomic)],
                    max_gas=max_gas, fee=fee)


def oracle_aggregate_now(p: Protocol, feed_id: int = FEED_XEL_USD) -> str:
    return p.invoke("StakedOracle", "aggregate_now", [val_u64(feed_id)])


def oracle_feed_info(p: Protocol, feed_id: int = FEED_XEL_USD) -> dict:
    """Read feed struct (fd_<id> object), activeness (fa_<id>),
    aggregated price (fg_<id>), last aggregation (la_<id>), cycle (cy_<id>)."""
    oracle = p.resolve("StakedOracle")
    info: dict[str, Any] = {}
    feed = p.read_contract(oracle, f"fd_{feed_id}")
    if feed and isinstance(feed, list) and len(feed) >= 7:
        info["id"] = feed[0]
        info["name"] = feed[1]
        info["asset"] = feed[2]
        info["decimals"] = feed[3]
        info["min_price"] = feed[4]
        info["max_price"] = feed[5]
        info["created_at"] = feed[6]
    info["active"] = p.read_contract(oracle, f"fa_{feed_id}")
    agg = p.read_contract(oracle, f"fg_{feed_id}")
    if agg and isinstance(agg, list) and len(agg) >= 5:
        info["agg_price"] = agg[0]
        info["agg_topo"] = agg[1]
        info["agg_deviation_bps"] = agg[2]
        info["agg_sources"] = agg[3]
        info["agg_cycle"] = agg[4]
    info["last_agg"] = p.read_contract(oracle, f"la_{feed_id}")
    info["cycle"] = p.read_contract(oracle, f"cy_{feed_id}")
    return info


def oracle_active_providers(p: Protocol) -> int:
    """Active miners registered for oracle service (sm_<service>)."""
    v = p.read_contract(p.resolve("XelisVaultMiner"), f"sm_{SERVICE_ORACLE}")
    return int(v) if v else 0


# ---------------------------------------------------------------------------
# Op wrappers — Miner
# ---------------------------------------------------------------------------
def miner_register(p: Protocol, endpoint_url: str, miner_pubkey: str,
                   services_mask: int = SERVICE_ORACLE,
                   stake_vlt: int = MIN_STAKE_VLT) -> str:
    """XelisVaultMiner.register_miner — deposits stake_vlt VLT (min 1000)."""
    return p.invoke("XelisVaultMiner", "register_miner",
                    [val_str(endpoint_url), val_hash(miner_pubkey),
                     val_u8(services_mask)],
                    deposits={VLT_ASSET: {"amount": stake_vlt}},
                    max_gas=HEAVY_GAS)


def miner_heartbeat(p: Protocol) -> str:
    return p.invoke("XelisVaultMiner", "submit_heartbeat", [])


def miner_active_count(p: Protocol) -> int:
    """Total registered miners (MINERS_COUNT_KEY = mc)."""
    v = p.read_contract(p.resolve("XelisVaultMiner"), "mc")
    return int(v) if v else 0


def miner_total_staked(p: Protocol) -> int:
    v = p.read_contract(p.resolve("XelisVaultMiner"), "ts")
    return int(v) if v else 0


# ---------------------------------------------------------------------------
# Op wrappers — VaultEngine (XEL collateral → xUSD debt)
# ---------------------------------------------------------------------------
def vault_deposit(p: Protocol, amount_xel: int, salt: str = "0" * 64) -> str:
    """deposit(collateral_asset, collateral_amount, salt) — deposits XEL."""
    return p.invoke("VaultEngine", "deposit",
                    [val_hash(XEL_ASSET), val_u64(amount_xel), val_hash(salt)],
                    deposits={XEL_ASSET: {"amount": amount_xel}},
                    max_gas=HEAVY_GAS)


def vault_borrow(p: Protocol, vault_id: int, amount_xusd: int) -> str:
    return p.invoke("VaultEngine", "borrow",
                    [val_u64(vault_id), val_u64(amount_xusd)])


def vault_repay(p: Protocol, vault_id: int, amount_xusd: int) -> str:
    return p.invoke("VaultEngine", "repay",
                    [val_u64(vault_id), val_u64(amount_xusd)],
                    deposits={XUSD_ASSET: {"amount": amount_xusd}})


def vault_withdraw(p: Protocol, vault_id: int, amount_xel: int) -> str:
    return p.invoke("VaultEngine", "withdraw",
                    [val_u64(vault_id), val_u64(amount_xel)])


def vault_liquidate(p: Protocol, vault_id: int,
                    max_borrow_to_repay: int) -> str:
    return p.invoke("VaultEngine", "liquidate",
                    [val_u64(vault_id), val_u64(max_borrow_to_repay)])


def vault_redeem(p: Protocol, amount_xusd: int) -> str:
    return p.invoke("VaultEngine", "redeem", [val_u64(amount_xusd)])


def vault_total(p: Protocol) -> int:
    """Vault id counter (COUNTER_KEY = n)."""
    v = p.read_contract(p.resolve("VaultEngine"), "n")
    return int(v) if v else 0


# ---------------------------------------------------------------------------
# Op wrappers — PSM (1:1 XEL <-> xUSD at oracle price)
# ---------------------------------------------------------------------------
def psm_mint(p: Protocol, xel_amount: int, min_xusd_out: int) -> str:
    if min_xusd_out <= 0:
        raise ValueError("psm_mint: min_xusd_out must be > 0 (contract rejects 0)")
    return p.invoke("PSM", "mint",
                    [val_u64(xel_amount), val_u64(min_xusd_out)],
                    deposits={XEL_ASSET: {"amount": xel_amount}})


def psm_redeem(p: Protocol, xusd_amount: int, min_xel_out: int) -> str:
    if min_xel_out <= 0:
        raise ValueError("psm_redeem: min_xel_out must be > 0 (contract rejects 0)")
    return p.invoke("PSM", "redeem",
                    [val_u64(xusd_amount), val_u64(min_xel_out)],
                    deposits={XUSD_ASSET: {"amount": xusd_amount}})


# ---------------------------------------------------------------------------
# Op wrappers — VaultSwap AMM
# ---------------------------------------------------------------------------
def swap_create_pool(p: Protocol, asset_a: str, asset_b: str,
                     is_psm: bool = False) -> str:
    return p.invoke("VaultSwap", "create_pool",
                    [val_hash(asset_a), val_hash(asset_b), val_bool(is_psm)])


def swap_add_liquidity(p: Protocol, asset_a: str, asset_b: str,
                       amount_a: int, amount_b: int) -> str:
    return p.invoke("VaultSwap", "add_liquidity",
                    [val_hash(asset_a), val_hash(asset_b),
                     val_u64(amount_a), val_u64(amount_b)],
                    deposits={asset_a: {"amount": amount_a},
                              asset_b: {"amount": amount_b}},
                    max_gas=HEAVY_GAS)


def swap_swap(p: Protocol, asset_in: str, asset_out: str, amount_in: int,
              min_amount_out: int = 1) -> str:
    return p.invoke("VaultSwap", "swap",
                    [val_hash(asset_in), val_hash(asset_out),
                     val_u64(amount_in), val_u64(min_amount_out)],
                    deposits={asset_in: {"amount": amount_in}})


def swap_psm_mint(p: Protocol, xel_amount: int, min_xusd_out: int) -> str:
    if min_xusd_out <= 0:
        raise ValueError("swap_psm_mint: min_xusd_out must be > 0")
    return p.invoke("VaultSwap", "psm_mint",
                    [val_u64(xel_amount), val_u64(min_xusd_out)],
                    deposits={XEL_ASSET: {"amount": xel_amount}})


def swap_psm_redeem(p: Protocol, xusd_amount: int, min_xel_out: int) -> str:
    if min_xel_out <= 0:
        raise ValueError("swap_psm_redeem: min_xel_out must be > 0")
    return p.invoke("VaultSwap", "psm_redeem",
                    [val_u64(xusd_amount), val_u64(min_xel_out)],
                    deposits={XUSD_ASSET: {"amount": xusd_amount}})


def swap_pools_count(p: Protocol) -> int:
    v = p.read_contract(p.resolve("VaultSwap"), "pc")
    return int(v) if v else 0


# ---------------------------------------------------------------------------
# Op wrappers — Governance
# ---------------------------------------------------------------------------
def gov_stake(p: Protocol, amount_vlt: int, lock_days: int = 0) -> str:
    return p.invoke("GovernanceVault", "stake",
                    [val_u64(amount_vlt), val_u64(lock_days)],
                    deposits={VLT_ASSET: {"amount": amount_vlt}})


def gov_unstake(p: Protocol, stake_id: int) -> str:
    return p.invoke("GovernanceVault", "unstake", [val_u64(stake_id)])


def gov_claim_rewards(p: Protocol) -> str:
    return p.invoke("GovernanceVault", "claim_rewards", [])


def gov_total_staked(p: Protocol) -> int:
    v = p.read_contract(p.resolve("GovernanceVault"), "ts")
    return int(v) if v else 0


def gov_stakes_count(p: Protocol) -> int:
    v = p.read_contract(p.resolve("GovernanceVault"), "sc")
    return int(v) if v else 0


# ---------------------------------------------------------------------------
# Op wrappers — PrivacyMixer v2 (note + shared pool; no sender/recipient link)
# ---------------------------------------------------------------------------
def mixer_deposit(p: Protocol, asset: str, amount_atomic: int, secret: str) -> str:
    return p.invoke("PrivacyMixer", "deposit",
                    [val_hash(asset), val_hash(secret)],
                    deposits={asset: {"amount": amount_atomic}}, max_gas=HEAVY_GAS)


def mixer_withdraw(p: Protocol, recipient: str, asset: str,
                   amount_atomic: int, secret: str) -> str:
    return p.invoke("PrivacyMixer", "withdraw",
                    [val_addr(recipient), val_hash(asset), val_u64(amount_atomic),
                     val_hash(secret)],
                    max_gas=HEAVY_GAS)


# ---------------------------------------------------------------------------
# Op wrappers — Insurance
# ---------------------------------------------------------------------------
def insurance_stake(p: Protocol, amount: int) -> str:
    return p.invoke("InsurancePool", "stake", [val_u64(amount)],
                    deposits={XUSD_ASSET: {"amount": amount}})


def insurance_unstake(p: Protocol, amount: int) -> str:
    return p.invoke("InsurancePool", "unstake", [val_u64(amount)])


def insurance_claim_premium(p: Protocol) -> str:
    return p.invoke("InsurancePool", "claim_premium", [])


# ---------------------------------------------------------------------------
# Op wrappers — Vesting / Delegation / Savings / Faucet / Chat
# ---------------------------------------------------------------------------
def vesting_claim(p: Protocol, name: str = "FounderVesting4y") -> str:
    return p.invoke(name, "claim_founder_tokens", [])


def delegation_register_profile(p: Protocol, name: str, description: str,
                                commission_bps: int) -> str:
    return p.invoke("MinerDelegation", "register_miner_profile",
                    [val_str(name), val_str(description), val_u64(commission_bps)])


def delegation_delegate(p: Protocol, miner_addr: str, amount_vlt: int,
                        auto_compound: bool = False) -> str:
    return p.invoke("MinerDelegation", "delegate",
                    [val_addr(miner_addr), val_u64(amount_vlt),
                     val_bool(auto_compound)],
                    deposits={VLT_ASSET: {"amount": amount_vlt}})


def delegation_undelegate(p: Protocol, amount_vlt: int) -> str:
    return p.invoke("MinerDelegation", "undelegate", [val_u64(amount_vlt)])


def savings_deposit(p: Protocol, amount_xusd: int) -> str:
    return p.invoke("SavingsRate", "deposit", [val_u64(amount_xusd)],
                    deposits={XUSD_ASSET: {"amount": amount_xusd}})


def savings_withdraw(p: Protocol, amount_xusd: int) -> str:
    return p.invoke("SavingsRate", "withdraw", [val_u64(amount_xusd)])


def faucet_distribute(p: Protocol, addresses: list) -> str:
    return p.invoke("FaucetContract", "distribute",
                    [val_addr(a) for a in addresses])


def chat_register_session(p: Protocol, chat_pubkey: str) -> str:
    return p.invoke("VaultChat", "register_session", [val_hash(chat_pubkey)])


def chat_anchor_messages(p: Protocol, merkle_root: str, message_count: int,
                         sender_count: int, msg_type: int = 0) -> str:
    return p.invoke("VaultChat", "anchor_messages",
                    [val_hash(merkle_root), val_u64(message_count),
                     val_u64(sender_count), val_u8(msg_type)])


# ---------------------------------------------------------------------------
# Bootstrap defaults
# ---------------------------------------------------------------------------
_default: Optional[Protocol] = None


def get_protocol() -> Protocol:
    global _default
    if _default is None:
        _default = Protocol()
    return _default


def set_protocol(p: Protocol) -> None:
    global _default
    _default = p


if __name__ == "__main__":
    p = get_protocol()
    if len(sys.argv) > 1 and sys.argv[1] == "check":
        print("wallet address:", p.wallet.address())
        print("topoheight:", p.topoheight())
        for name in ["StakedOracle", "XelisVaultMiner", "VaultEngine", "PSM"]:
            print(f"{name}: {p.resolve(name)[:16]}...")
        print("VLT balance:", p.balance(VLT_ASSET))
        print("xUSD balance:", p.balance(XUSD_ASSET))
        print("XEL balance:", p.balance())