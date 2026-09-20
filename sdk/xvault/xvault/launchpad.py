"""
xvault.launchpad — VaultLaunch reference implementation & RPC reader.

Python mirror of contracts/launchpad/VaultLaunch.slx. Every formula here
MUST stay byte-identical to the contract (CI cross-checks the core math in
tests/test_launchpad_reference.py — if you change one, change both in the
same commit).

The launched tokens are an INTERNAL LEDGER of the VaultLaunch contract (no
inter-contract calls on XELIS): balances and curve state live in the
contract's string-keyed storage, which this module reads via the daemon RPC
(get_contract_data with plain string keys).

Units: XEL and token amounts are atomic integers with 8 decimals
(1 XEL = 1 token = 100_000_000).
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from . import protocol
from .protocol import DaemonClient, val_addr, val_str, val_u64

# ---------------------------------------------------------------------------
# Status codes (contract LIFECYCLE section)
# ---------------------------------------------------------------------------
ST_VALIDATION = 0
ST_REJECTED = 1
ST_BONDING = 2
ST_GRADUATED = 3
ST_TRUSTED = 4
ST_UNTRUSTED = 5
ST_RECOVERY = 6

STATUS_LABELS = {
    ST_VALIDATION: "validation",
    ST_REJECTED: "rejected",
    ST_BONDING: "bonding",
    ST_GRADUATED: "graduated",
    ST_TRUSTED: "trusted",
    ST_UNTRUSTED: "untrusted",
    ST_RECOVERY: "recovery",
}

# Buy allowed only in these states (Untrusted / windows block NEW buys).
BUYABLE = (ST_BONDING, ST_GRADUATED, ST_TRUSTED)
# Sell is NEVER blockable once trading opened.
SELLABLE = (ST_BONDING, ST_GRADUATED, ST_TRUSTED, ST_UNTRUSTED, ST_RECOVERY)

# ---------------------------------------------------------------------------
# Defaults (must match the contract constants exactly)
# ---------------------------------------------------------------------------
DEFAULTS = {
    "submission_fee": 1_000_000_000,          # 10 XEL
    "min_liquidity": 50_000_000_000,          # 500 XEL
    "trading_fee_bps": 50,                    # 0.5%
    "min_participants": 20,
    "min_approval_ratio_bps": 8_000,          # 80%
    "validation_duration": 51_840,            # ~3 days at ~5s topoheights
    "graduation_multiplier": 4,
    "recovery_fee": 25_000_000_000,           # 250 XEL
    "recovery_min_participants": 40,
    "recovery_min_ratio_bps": 9_000,          # 90%
}

# ---------------------------------------------------------------------------
# Curve math — the contract's exact integer formulas (u128-safe)
# ---------------------------------------------------------------------------

def fmt_token(atomic: int) -> str:
    """Format a launched-token amount (8 decimals, same scale as XEL)."""
    return f"{atomic / 1e8:,.8f}".rstrip("0").rstrip(".")


def fee_take(amount: int, bps: int) -> int:
    """Trading fee on `amount`, floored in favour of the contract."""
    return amount * bps // 10_000


def buy_tokens_out(reserves: int, curve_supply: int, net_xel: int) -> int:
    """tokens_out = C * net / (R + net), floored."""
    return curve_supply * net_xel // (reserves + net_xel)


def sell_xel_out(reserves: int, curve_supply: int, tokens: int) -> int:
    """gross = R * T / (C + T), floored (before fee)."""
    return reserves * tokens // (curve_supply + tokens)


def team_alloc_of(total_supply: int, team_bps: int) -> int:
    return total_supply * team_bps // 10_000


def buy_quote(reserves: int, curve_supply: int, xel_amount: int,
              fee_bps: int) -> int:
    """Tokens received for an attached XEL amount (fee included)."""
    net = xel_amount - fee_take(xel_amount, fee_bps)
    return buy_tokens_out(reserves, curve_supply, net)


def sell_quote(reserves: int, curve_supply: int, tokens: int,
               fee_bps: int) -> int:
    """XEL received (net of fee) for selling tokens."""
    gross = sell_xel_out(reserves, curve_supply, tokens)
    return gross - fee_take(gross, fee_bps)


def current_price(reserves: int, curve_supply: int,
                  scale: int = 100_000_000) -> int:
    """Spot price: XEL (scaled by 1e8) per 1 whole token."""
    if curve_supply == 0:
        return 0
    return min(reserves * scale // curve_supply, 2**64 - 1)


def market_cap(reserves: int, curve_supply: int, total_supply: int,
               team_bps: int, graduated: bool) -> int:
    """mc = R * circulating / C in atomic XEL (saturating at u64 max)."""
    if curve_supply == 0:
        return 0
    team = 0 if graduated else team_alloc_of(total_supply, team_bps)
    circulating = total_supply - curve_supply - team
    if circulating <= 0:
        return 0
    return min(reserves * circulating // curve_supply, 2**64 - 1)


# ---------------------------------------------------------------------------
# Storage keys — must match the contract's key builders exactly
# ---------------------------------------------------------------------------

def proj_key(pid: int, field: str) -> str:
    return f"p:{pid}:{field}"


def vote_key(pid: int, round_no: int, voter: str) -> str:
    return f"v:{pid}:{round_no}:{voter}"


def bal_key(pid: int, owner: str) -> str:
    return f"b:{pid}:{owner}"


F_CREATOR, F_STATUS, F_NAME, F_SYMBOL = "cr", "st", "nm", "sy"
F_DESC, F_WEBSITE, F_LOGO = "ds", "ws", "lg"
F_SUPPLY, F_TEAM_BPS, F_LIQUIDITY = "ts", "tb", "lq"
F_RESERVES, F_CURVE, F_CREATED, F_DEADLINE = "rv", "cs", "ct", "ve"
F_SUPPORTS, F_REPORTS, F_GRADUATED = "sp", "rp", "gr"
F_REFUND, F_ROUND, F_VOLUME = "rc", "rd", "vo"

GLOBAL_KEYS = {
    "admin": "adm", "count": "pc", "submission_fee": "sub",
    "min_liquidity": "mnl", "trading_fee_bps": "tfe",
    "min_participants": "mnp", "min_approval_ratio_bps": "mab",
    "validation_duration": "vdt", "graduation_multiplier": "gmu",
    "recovery_fee": "rfe", "recovery_min_participants": "rmp",
    "recovery_min_ratio_bps": "rmr", "pending_fees": "pfe",
    "fees_collected_lifetime": "fcl", "total_volume": "tvl",
    "total_curve_xel": "tcx", "locked_refunds": "lrf",
    "paused": "pz",
}


# ---------------------------------------------------------------------------
# Invoke parameter builders (ValueCell) — positional, chunk-id addressed
# ---------------------------------------------------------------------------

def propose_params(name: str, symbol: str, description: str, website: str,
                   logo: str, total_supply: int, team_bps: int) -> list:
    return [val_str(name), val_str(symbol), val_str(description),
            val_str(website), val_str(logo), val_u64(total_supply),
            val_u64(team_bps)]


def propose_deposits(submission_fee: int, liquidity: int,
                     xel_asset: str = "0" * 64) -> dict:
    """Attached deposit: EXACTLY submission_fee + liquidity XEL."""
    return {xel_asset: submission_fee + liquidity}


def buy_deposits(xel_amount: int, xel_asset: str = "0" * 64) -> dict:
    return {xel_asset: xel_amount}


def update_info_params(description: str, website: str, logo: str) -> list:
    return [val_str(description), val_str(website), val_str(logo)]


def set_recovery_params_params(participants: int, ratio_bps: int) -> list:
    return [val_u64(participants), val_u64(ratio_bps)]


def pid_params(pid: int) -> list:
    return [val_u64(pid)]


def sell_params(pid: int, token_amount: int) -> list:
    return [val_u64(pid), val_u64(token_amount)]


# ---------------------------------------------------------------------------
# RPC reader (public nodes are fine — read-only)
# ---------------------------------------------------------------------------

class LaunchpadReader:
    def __init__(self, daemon: DaemonClient, contract: str):
        self.d = daemon
        self.contract = contract

    def _key(self, key: str, default: Any = None) -> Any:
        v = self.d.read_key(self.contract, key)
        return default if v is None else v

    def count(self) -> int:
        return self._key(GLOBAL_KEYS["count"], 0)

    def paused(self) -> bool:
        return bool(self._key(GLOBAL_KEYS["paused"], False))

    def config(self) -> Dict[str, int]:
        return {name: self._key(key, DEFAULTS.get(name, 0))
                for name, key in GLOBAL_KEYS.items()
                if name in DEFAULTS}

    def admin(self) -> Optional[str]:
        return self._key(GLOBAL_KEYS["admin"])

    def stats(self) -> Dict[str, Any]:
        names = ("count", "pending_fees", "fees_collected_lifetime",
                 "total_volume", "total_curve_xel", "locked_refunds")
        out: Dict[str, Any] = {n: self._key(GLOBAL_KEYS[n], 0) for n in names}
        out["paused"] = self.paused()
        return out

    def project(self, pid: int) -> Dict[str, Any]:
        """Everything the frontend needs for one project card."""
        out: Dict[str, Any] = {"id": pid}
        for attr, field in (("creator", F_CREATOR), ("status", F_STATUS),
                            ("name", F_NAME), ("symbol", F_SYMBOL),
                            ("description", F_DESC), ("website", F_WEBSITE),
                            ("logo", F_LOGO), ("total_supply", F_SUPPLY),
                            ("team_bps", F_TEAM_BPS),
                            ("liquidity", F_LIQUIDITY),
                            ("reserves", F_RESERVES), ("curve", F_CURVE),
                            ("created_topo", F_CREATED),
                            ("deadline", F_DEADLINE),
                            ("supports", F_SUPPORTS), ("reports", F_REPORTS),
                            ("graduated", F_GRADUATED), ("round", F_ROUND),
                            ("volume", F_VOLUME)):
            out[attr] = self._key(proj_key(pid, field))
        status = out.get("status") or 0
        out["status_label"] = STATUS_LABELS.get(status, "unknown")
        return out

    def token_balance(self, pid: int, owner: str) -> int:
        return self._key(bal_key(pid, owner), 0) or 0

    def has_voted(self, pid: int, round_no: int, voter: str) -> bool:
        return bool(self._key(vote_key(pid, round_no, voter), False))

    def quotes(self, pid: int, fee_bps: Optional[int] = None) -> Dict[str, int]:
        p = self.project(pid)
        reserves, curve = p["reserves"] or 0, p["curve"] or 0
        if fee_bps is None:
            fee_bps = self._key(GLOBAL_KEYS["trading_fee_bps"],
                                DEFAULTS["trading_fee_bps"])
        return {
            "reserves": reserves,
            "curve": curve,
            "price": current_price(reserves, curve),
            "market_cap": market_cap(reserves, curve, p["total_supply"] or 0,
                                     p["team_bps"] or 0,
                                     bool(p["graduated"])),
            "fee_bps": fee_bps,
        }
