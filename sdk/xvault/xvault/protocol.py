"""
xvault.protocol — RPC layer for the XELIS Vault protocol (v13).

ValueCell encoding, wallet/daemon JSON-RPC clients and chunk-id tables.
Ported and hardened from the legacy v12 protocol.py; only what the mixer
needs survived. Every write goes through a LOCAL wallet RPC (xelis_wallet
--rpc-server); this SDK never touches your keys directly.
"""
from __future__ import annotations

import time
from typing import Any, Optional

import requests

# ---------------------------------------------------------------------------
# Networks
# ---------------------------------------------------------------------------
NETWORKS = {
    "mainnet": {
        "daemon": "https://node.xelis.io/json_rpc",
        "xelis_asset": "0" * 64,
        "address_prefix": "xel",
    },
    "testnet": {
        "daemon": "https://testnet-node.xelis.io/json_rpc",
        "xelis_asset": "0" * 64,
        "address_prefix": "xet",
    },
}

# Local wallet RPC (xelis_wallet --rpc-server) — defaults from the official CLI.
WALLET_URL = "http://127.0.0.1:18082/json_rpc"
WALLET_AUTH = ("wallet", "testpass")

ZERO_HASH = "0" * 64

TX_CONFIRM_TIMEOUT = 180
INVOKE_FEE = 10_000_000        # 0.1 XEL
INVOKE_GAS = 5_000_000

# ---------------------------------------------------------------------------
# PrivacyMixer V5 chunk ids (constructor = 0, then EVERY function in
# declaration order — matches the compiler's chunk maps, CI-verified).
# The MIXER_ENTRY_IDS_ALT table is the legacy "entries-only" numbering; use
# `xvault mixer probe` on testnet to confirm which one the VM expects before
# any mainnet interaction.
# ---------------------------------------------------------------------------
MIXER_CONTRACT = "PrivacyMixerV5"

MIXER_ENTRY_IDS = {
    "deposit": 13,
    "release": 14,
    "release_many": 15,
    "pause": 16,
    "unpause": 17,
    "emergency_exit": 18,
    "raise_alarm": 19,
    "set_fee_bps": 20,
    "set_bounty": 21,
    "set_fee_recipient": 22,
    "claim_fees": 23,
    "propose_owner": 24,
    "accept_owner": 25,
    "renounce_ownership": 26,
}

# Alternative numbering (entries only, 0-based) — kept ONLY for the probe.
MIXER_ENTRY_IDS_ALT = {
    "deposit": 0,
    "release": 1,
    "release_many": 2,
    "pause": 3,
    "unpause": 4,
    "emergency_exit": 5,
    "raise_alarm": 6,
    "set_fee_bps": 7,
    "set_bounty": 8,
    "set_fee_recipient": 9,
    "claim_fees": 10,
    "propose_owner": 11,
    "accept_owner": 12,
    "renounce_ownership": 13,
}

# ---------------------------------------------------------------------------
# VaultLaunch chunk ids (constructor = 0, then EVERY function in declaration
# order — matches the contract's CI-verified CHUNK TABLE).
# ---------------------------------------------------------------------------
LAUNCHPAD_CONTRACT = "VaultLaunch"

LAUNCHPAD_ENTRY_IDS = {
    "propose": 16,
    "support": 17,
    "report": 18,
    "finalize_validation": 19,
    "buy": 20,
    "sell": 21,
    "claim_refund": 22,
    "request_revalidation": 23,
    "update_project_info": 24,
    "start_team_vesting": 25,
    "claim_team_allocation": 26,
    "set_submission_fee": 27,
    "set_trading_fee": 28,
    "set_graduated_trading_fee": 29,
    "set_migration_fee": 30,
    "set_direct_listing_threshold": 31,
    "set_min_liquidity": 32,
    "set_min_participants": 33,
    "set_min_approval_ratio": 34,
    "set_validation_duration": 35,
    "set_graduation_multiplier": 36,
    "set_team_unlock_delay": 37,
    "set_vesting_bounds": 38,
    "set_recovery_fee": 39,
    "set_recovery_params": 40,
    "set_admin": 41,
    "set_paused": 42,
    "withdraw_fees": 43,
}

# Alternative numbering (entries only, 0-based) — kept ONLY for the probe.
LAUNCHPAD_ENTRY_IDS_ALT = {
    "propose": 0,
    "support": 1,
    "report": 2,
    "finalize_validation": 3,
    "buy": 4,
    "sell": 5,
    "claim_refund": 6,
    "request_revalidation": 7,
    "update_project_info": 8,
    "start_team_vesting": 9,
    "claim_team_allocation": 10,
    "set_submission_fee": 11,
    "set_trading_fee": 12,
    "set_graduated_trading_fee": 13,
    "set_migration_fee": 14,
    "set_direct_listing_threshold": 15,
    "set_min_liquidity": 16,
    "set_min_participants": 17,
    "set_min_approval_ratio": 18,
    "set_validation_duration": 19,
    "set_graduation_multiplier": 20,
    "set_team_unlock_delay": 21,
    "set_vesting_bounds": 22,
    "set_recovery_fee": 23,
    "set_recovery_params": 24,
    "set_admin": 25,
    "set_paused": 26,
    "withdraw_fees": 27,
}

# ---------------------------------------------------------------------------
# ValueCell builders (adjacently tagged JSON, mirrors the official CLI)
# ---------------------------------------------------------------------------

def _prim(t: str, v: Any) -> dict:
    return {"type": "primitive", "value": {"type": t, "value": v}}

def val_u8(n: int) -> dict:    return _prim("u8", int(n))
def val_u32(n: int) -> dict:   return _prim("u32", int(n))
def val_u64(n: int) -> dict:   return _prim("u64", str(int(n)))
def val_bool(b: bool) -> dict: return _prim("boolean", bool(b))
def val_str(s: str) -> dict:   return _prim("string", s)
def val_hash(h: str) -> dict:  return _prim("opaque", {"type": "Hash", "value": h})
def val_addr(a: str) -> dict:  return _prim("opaque", {"type": "Address", "value": a})
def val_array(cells: list) -> dict:
    return {"type": "object", "value": cells}

def parse_cell(cell: Any) -> Any:
    """Storage cell -> plain Python value (u64 as int, Hash/Address as hex str)."""
    if cell is None:
        return None
    t = cell.get("type")
    if t == "primitive":
        v = cell.get("value") or {}
        vt, val = v.get("type"), v.get("value")
        if vt in ("u8", "u16", "u32", "u64", "u128", "u256",
                  "amount", "balance", "nonce", "fee"):
            return int(val)
        if vt == "boolean":
            return bool(val)
        if vt == "string":
            return val
        if vt == "opaque":
            return val.get("value") if isinstance(val, dict) else val
        if vt == "null":
            return None
        return val
    if t == "object":
        return [parse_cell(c) for c in cell.get("value") or []]
    if t == "bytes":
        return cell.get("value")
    return cell


class RPCError(RuntimeError):
    """RPC failure."""


def _post(url: str, method: str, params: Any = None, auth: Optional[tuple] = None,
          timeout: int = 30) -> Any:
    payload = {"jsonrpc": "2.0", "id": "1", "method": method}
    if params is not None:
        payload["params"] = params
    try:
        r = requests.post(url, json=payload, auth=auth, timeout=timeout,
                          headers={"Content-Type": "application/json"})
        r.raise_for_status()
        body = r.json()
    except Exception as e:  # noqa: BLE001
        raise RPCError(f"{method}: {e}") from e
    if "error" in body:
        raise RPCError(f"{method}: {body['error']}")
    return body.get("result")


def _with_retries(fn, attempts: int = 4, delay: float = 5.0):
    last: Optional[Exception] = None
    for _ in range(attempts):
        try:
            return fn()
        except RPCError as e:
            last = e
            time.sleep(delay)
    raise last  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Daemon client (read-only, public nodes are fine)
# ---------------------------------------------------------------------------

class DaemonClient:
    def __init__(self, url: str = NETWORKS["mainnet"]["daemon"]):
        self.url = url

    def _call(self, method: str, params: Any = None) -> Any:
        return _post(self.url, method, params)

    def topoheight(self) -> int:
        return int(self._call("get_topoheight"))

    def get_info(self) -> dict:
        return self._call("get_info")

    def get_contract_data(self, contract: str, key: dict) -> Any:
        res = self._call("get_contract_data", {"contract": contract, "key": key})
        return parse_cell((res or {}).get("data")) if isinstance(res, dict) else res

    def read_key(self, contract: str, key_str: str) -> Any:
        """Read a string-keyed storage cell; None when never written."""
        try:
            return self.get_contract_data(contract, val_str(key_str))
        except RPCError as e:
            if "No data found" in str(e) or "not found" in str(e):
                return None
            raise

    def get_contract_balance(self, contract: str, asset: str) -> int:
        try:
            res = self._call("get_contract_balance",
                             {"contract": contract, "asset": asset})
            return int(res or 0)
        except RPCError:
            return 0

    def get_transaction(self, tx_hash: str) -> Optional[dict]:
        try:
            return self._call("get_transaction", {"hash": tx_hash})
        except RPCError:
            return None


# ---------------------------------------------------------------------------
# Wallet client (writes — requires a LOCAL xelis_wallet RPC)
# ---------------------------------------------------------------------------

class WalletClient:
    def __init__(self, url: str = WALLET_URL, auth: tuple = WALLET_AUTH):
        self.url = url
        self.auth = auth

    def _call(self, method: str, params: Any = None) -> Any:
        return _post(self.url, method, params, auth=self.auth)

    def address(self) -> str:
        return self._call("get_address")

    def nonce(self) -> int:
        return int(self._call("get_nonce"))

    def invoke(self, contract: str, entry_id: int, params: Optional[list] = None,
               deposits: Optional[dict] = None, max_gas: int = INVOKE_GAS,
               fee: int = INVOKE_FEE, broadcast: bool = True) -> str:
        """Build + broadcast an invoke_contract transaction. Returns tx hash."""
        def _build() -> str:
            payload = {
                "invoke_contract": {
                    "contract": contract,
                    "max_gas": max_gas,
                    "entry_id": entry_id,
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

        return _with_retries(_build)

    def wait_nonce_advance(self, before: int, timeout: int = TX_CONFIRM_TIMEOUT) -> int:
        t0 = time.time()
        while time.time() - t0 < timeout:
            try:
                now = self.nonce()
                if now > before:
                    return now
            except RPCError:
                pass
            time.sleep(3.0)
        raise RPCError(f"tx not confirmed after {timeout}s (nonce stuck at {before})")
