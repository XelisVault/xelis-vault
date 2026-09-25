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
    "devnet": {
        "daemon": "http://127.0.0.1:8080/json_rpc",
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
    "propose": 20,
    "support": 21,
    "report": 22,
    "finalize_validation": 23,
    "buy": 24,
    "sell": 25,
    "claim_refund": 26,
    "claim_vote_deposit": 27,
    "request_revalidation": 28,
    "update_project_info": 29,
    "start_team_vesting": 30,
    "claim_team_allocation": 31,
    "migrate": 32,
    "sync_trust_to_dex": 33,
    "set_submission_fee": 34,
    "set_trading_fee": 35,
    "set_graduated_trading_fee": 36,
    "set_migration_fee": 37,
    "set_direct_listing_threshold": 38,
    "set_min_liquidity": 39,
    "set_min_participants": 40,
    "set_min_approval_ratio": 41,
    "set_validation_duration": 42,
    "set_graduation_multiplier": 43,
    "set_team_unlock_delay": 44,
    "set_vesting_bounds": 45,
    "set_recovery_fee": 46,
    "set_recovery_params": 47,
    "set_asset_budget": 48,
    "set_vote_deposit": 49,
    "set_dex_address": 50,
    "set_admin": 51,
    "set_paused": 52,
    "withdraw_fees": 53,
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
    "claim_vote_deposit": 7,
    "request_revalidation": 8,
    "update_project_info": 9,
    "start_team_vesting": 10,
    "claim_team_allocation": 11,
    "migrate": 12,
    "sync_trust_to_dex": 13,
    "set_submission_fee": 14,
    "set_trading_fee": 15,
    "set_graduated_trading_fee": 16,
    "set_migration_fee": 17,
    "set_direct_listing_threshold": 18,
    "set_min_liquidity": 19,
    "set_min_participants": 20,
    "set_min_approval_ratio": 21,
    "set_validation_duration": 22,
    "set_graduation_multiplier": 23,
    "set_team_unlock_delay": 24,
    "set_vesting_bounds": 25,
    "set_recovery_fee": 26,
    "set_recovery_params": 27,
    "set_asset_budget": 28,
    "set_vote_deposit": 29,
    "set_dex_address": 30,
    "set_admin": 31,
    "set_paused": 32,
    "withdraw_fees": 33,
}

# ---------------------------------------------------------------------------
# LaunchDEX chunk ids (same rule: every function in declaration order).
# NOTE (devnet toolchain): VaultLaunch cross-calls create_pool and
# set_pool_buys_paused, which are declared `pub fn` — NOT `entry` — because
# this devnet VM refuses cross-contract calls into `entry` chunks ("Chunk is
# not public"). They keep their real chunk ids (create_pool = 6,
# set_pool_buys_paused = 7) since chunk numbering follows declaration order
# for every function (hook/fn/pub fn/entry alike). Being `pub fn`, they are
# absent from this transaction-facing entry table; the D19 pin (VaultLaunch's
# DEX_CREATE_POOL_CHUNK / DEX_SET_PAUSED_CHUNK) is asserted against the real
# declaration order by tests/test_dex_reference.py and
# tests/test_launchpad_reference.py.
# ---------------------------------------------------------------------------
DEX_CONTRACT = "LaunchDEX"

LAUNCHDEX_ENTRY_IDS = {
    "swap_xel_for_token": 8,
    "swap_token_for_xel": 9,
    "add_liquidity": 10,
    "set_swap_fee": 11,
    "set_trade_bounds": 12,
    "set_launchpad": 13,
    "set_admin": 14,
    "set_paused": 15,
    "withdraw_fees": 16,
    "set_fee_split": 29,
    "claim_lp_fees": 30,
    "remove_liquidity": 32,
}

LAUNCHDEX_ENTRY_IDS_ALT = {
    "swap_xel_for_token": 0,
    "swap_token_for_xel": 1,
    "add_liquidity": 2,
    "set_swap_fee": 3,
    "set_trade_bounds": 4,
    "set_launchpad": 5,
    "set_admin": 6,
    "set_paused": 7,
    "withdraw_fees": 8,
    "set_fee_split": 9,
    "claim_lp_fees": 10,
    "remove_liquidity": 11,
}

# ---------------------------------------------------------------------------
# CommunityLaunch chunk ids (same rule: every function in declaration
# order — the factory of the permissionless community track, v1.0).
# The cross-called DEX chunk (create_pool_open, LaunchDEX v1.4 chunk 33)
# is pinned as CommunityLaunch's DEX_CREATE_POOL_OPEN_CHUNK constant and
# asserted against the DEX's real declaration order by
# tests/test_community_reference.py.
# ---------------------------------------------------------------------------
COMMUNITY_CONTRACT = "CommunityLaunch"

COMMUNITY_ENTRY_IDS = {
    "launch_coin": 15,
    "buy": 16,
    "sell": 17,
    "migrate": 18,
    "claim_creator_allocation": 19,
    "update_coin_info": 20,
    "set_submission_fee": 21,
    "set_asset_budget": 22,
    "set_curve_fee": 23,
    "set_graduated_fee": 24,
    "set_migration_fee": 25,
    "set_graduation_depth": 26,
    "set_virtual_xel": 27,
    "set_dex_address": 28,
    "set_admin": 29,
    "set_paused": 30,
    "withdraw_fees": 31,
}

COMMUNITY_ENTRY_IDS_ALT = {
    "launch_coin": 0,
    "buy": 1,
    "sell": 2,
    "migrate": 3,
    "claim_creator_allocation": 4,
    "update_coin_info": 5,
    "set_submission_fee": 6,
    "set_asset_budget": 7,
    "set_curve_fee": 8,
    "set_graduated_fee": 9,
    "set_migration_fee": 10,
    "set_graduation_depth": 11,
    "set_virtual_xel": 12,
    "set_dex_address": 13,
    "set_admin": 14,
    "set_paused": 15,
    "withdraw_fees": 16,
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
