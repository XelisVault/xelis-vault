"""
xvault.launchpad — VaultLaunch reference implementation & RPC reader.

Python mirror of contracts/launchpad/VaultLaunch.slx. Every formula here
MUST stay byte-identical to the contract (CI cross-checks the core math in
tests/test_launchpad_reference.py — if you change one, change both in the
same commit).

v4 — REAL ASSETS: every validated project's token is a native XELIS
confidential asset created by the contract (MaxSupplyMode::Fixed — the
whole supply exists from birth and can never be minted past its cap).
Buyers hold REAL tokens in their own wallets; the curve trades actual
deposits; graduation migrates the reserves + inventory into a permanent
LaunchDEX pool (see xvault.dex). There is NO internal ledger anymore:
this module reads the contract's string-keyed bookkeeping (curve state,
trust, vesting, scoreboard) via the daemon RPC, while wallet balances
live on-chain in the wallets themselves.

Units: XEL and token amounts are atomic integers with 8 decimals
(1 XEL = 1 token = 100_000_000).
"""
from __future__ import annotations

from typing import Any, Dict, Optional

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
    "asset_budget": 1_000_000_000,            # 10 XEL earmarked for Asset::create (D13)
    "min_liquidity": 50_000_000_000,          # 500 XEL
    "trading_fee_bps": 50,                    # 0.5% while bonding
    "graduated_fee_bps": 25,                  # 0.25% curve trades between graduation and migration (D8)
    "migration_fee_bps": 50,                  # 0.5% once at graduation (D9)
    "direct_listing_threshold": 200_000_000_000,  # 2000 XEL skips bonding (D7)
    "min_participants": 20,
    "min_approval_ratio_bps": 8_000,          # 80%
    "validation_duration": 51_840,            # ~3 days at ~5s topoheights
    "graduation_multiplier": 4,
    "recovery_fee": 25_000_000_000,           # 250 XEL
    "recovery_min_participants": 40,
    "recovery_min_ratio_bps": 9_000,          # 90%
    "team_unlock_delay": 3_153_600,           # ~6 months of bonding (D3)
    "vesting_min": 518_400,                   # ~1 month
    "vesting_max": 6_307_200,                 # ~1 year
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


def current_fee_bps(graduated: bool, trading_fee_bps: int, graduated_fee_bps: int) -> int:
    """Effective trading fee of a project (D8): the graduated rate once it
    has graduated, clamped <= the bonding rate — exactly the contract's
    current_fee_bps() helper (defence in depth on top of cross-checked
    setters)."""
    if not graduated:
        return trading_fee_bps
    return min(graduated_fee_bps, trading_fee_bps)


def team_unlocked(team_alloc: int, graduated: bool,
                  vesting_start: int, vesting_duration: int,
                  status: int, bonding_start: int, team_unlock_delay: int,
                  topo: int) -> int:
    """How much of the allocation the creator may claim RIGHT NOW (D3) —
    mirrors the contract's team_unlocked() exactly (the gross unlocked
    amount; claimable = unlocked - team_paid, floored at 0).

    vesting active -> linear stream team * elapsed / duration (floored)
    graduated (no vesting) -> full allocation
    bonding/Untrusted/Recovery past team_unlock_delay -> full allocation
    otherwise -> 0
    """
    if team_alloc == 0:
        return 0
    if vesting_start > 0:
        if vesting_duration == 0:
            return team_alloc
        if topo <= vesting_start:
            return 0
        elapsed = topo - vesting_start
        return min(team_alloc * elapsed // vesting_duration, team_alloc)
    if graduated:
        return team_alloc
    if status in (ST_BONDING, ST_UNTRUSTED, ST_RECOVERY) and bonding_start > 0:
        if topo >= bonding_start + team_unlock_delay:
            return team_alloc
    return 0


def team_remaining(team_alloc: int, team_paid: int) -> int:
    """Allocation still owed to the creator (never negative) — the I1 term.

    v4: this is ALSO the token escrow the launchpad retains after
    migration (I10) — claimable at any time via claim_team_allocation."""
    return max(team_alloc - team_paid, 0)


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
    """Spot price: XEL (scaled by 1e8) per 1 whole token.

    CURVE-ERA price: 0 once migrated (the live price is LaunchDEX's
    get_spot_price — compose both eras for the frontend)."""
    if curve_supply == 0:
        return 0
    return min(reserves * scale // curve_supply, 2**64 - 1)


def market_cap(reserves: int, curve_supply: int, total_supply: int,
               team_bps: int, graduated: bool, team_paid: int = 0) -> int:
    """mc = R * circulating / C in atomic XEL (saturating at u64 max).

    circulating excludes the team allocation NOT YET PAID to the creator.
    CURVE-ERA cap: 0 once migrated (post-migration the live cap is the
    DEX pool's price x circulating — see xvault.dex.pool_market_cap).
    """
    if curve_supply == 0:
        return 0
    team_rem = team_remaining(team_alloc_of(total_supply, team_bps), team_paid)
    circulating = total_supply - curve_supply - team_rem
    if circulating <= 0:
        return 0
    return min(reserves * circulating // curve_supply, 2**64 - 1)


def dex_pool_market_cap(xel_reserve: int, token_reserve: int,
                        total_supply: int, team_remaining_amt: int) -> int:
    """Post-migration market cap: (x / y) * circulating, where circulating
    excludes the pool's own tokens and the unpaid team escrow. Atomic XEL,
    saturating at u64 max. Mirrors nothing on-chain (the DEX keeps reserves;
    the composition is the SDK's job, by design D12/D15)."""
    if token_reserve == 0:
        return 0
    circulating = total_supply - token_reserve - team_remaining_amt
    if circulating <= 0:
        return 0
    return min(xel_reserve * circulating // token_reserve, 2**64 - 1)


# ---------------------------------------------------------------------------
# Storage keys — must match the contract's key builders exactly
# ---------------------------------------------------------------------------

def proj_key(pid: int, field: str) -> str:
    return f"p:{pid}:{field}"


def vote_key(pid: int, round_no: int, voter: str) -> str:
    return f"v:{pid}:{round_no}:{voter}"


def ticker_key(symbol: str) -> str:
    """Ticker reservation registry (D11): one launchpad project per symbol."""
    return f"t:{symbol}"


F_CREATOR, F_STATUS, F_NAME, F_SYMBOL = "cr", "st", "nm", "sy"
F_DESC, F_WEBSITE, F_LOGO = "ds", "ws", "lg"
F_TWITTER, F_TELEGRAM, F_DISCORD = "tw", "tg", "dc"
F_SUPPLY, F_TEAM_BPS, F_LIQUIDITY = "ts", "tb", "lq"
F_RESERVES, F_CURVE, F_CREATED, F_DEADLINE = "rv", "cs", "ct", "ve"
F_SUPPORTS, F_REPORTS, F_GRADUATED = "sp", "rp", "gr"
F_REFUND, F_ROUND, F_VOLUME = "rc", "rd", "vo"
F_DL, F_BONDING_START = "dl", "bt"
F_TEAM_PAID, F_VESTING_START, F_VESTING_DURATION = "tp", "vs", "vd"
F_VESTING_PLAN = "vp"
F_BUY_VOL, F_SELL_VOL, F_TRADES, F_LAST_TRADE = "bv", "sv", "tc", "lt"
F_MCAP, F_MCAP_HIGH, F_MCAP_GRAD = "mc", "mh", "mg"
F_ASSET, F_BUDGET = "ah", "ab"
F_MIGRATED, F_MIG_AT, F_MIG_XEL, F_MIG_TOK = "mi", "ma", "mx", "mt"
F_DEX_SYNCED = "ds"

GLOBAL_KEYS = {
    "admin": "adm", "count": "pc", "submission_fee": "sub",
    "asset_budget": "abd",
    "min_liquidity": "mnl", "trading_fee_bps": "tfe",
    "graduated_fee_bps": "gfe", "migration_fee_bps": "mgf",
    "direct_listing_threshold": "dlt",
    "min_participants": "mnp", "min_approval_ratio_bps": "mab",
    "validation_duration": "vdt", "graduation_multiplier": "gmu",
    "team_unlock_delay": "tdy", "vesting_min": "vmn", "vesting_max": "vmx",
    "recovery_fee": "rfe", "recovery_min_participants": "rmp",
    "recovery_min_ratio_bps": "rmr", "pending_fees": "pfe",
    "fees_collected_lifetime": "fcl", "total_volume": "tvl",
    "total_buy_volume": "tbv", "total_sell_volume": "tsv",
    "total_trades": "ttc",
    "total_curve_xel": "tcx", "locked_refunds": "lrf",
    "total_budgets": "tbb", "migrated_count": "mgc", "dex_address": "dxa",
    "paused": "pz",
}


# ---------------------------------------------------------------------------
# Invoke parameter builders (ValueCell) — positional, chunk-id addressed
# ---------------------------------------------------------------------------

def propose_params(name: str, symbol: str, description: str, website: str,
                   logo: str, twitter: str, telegram: str, discord: str,
                   total_supply: int, team_bps: int, vesting_duration: int) -> list:
    """v3: social links (D11) + the vesting plan (D10, 0 = claim at
    graduation, otherwise within [vesting_min, vesting_max] snapshotted at
    propose time). v4: total_supply becomes the asset's FIXED max_supply
    at creation (D13)."""
    return [val_str(name), val_str(symbol), val_str(description),
            val_str(website), val_str(logo), val_str(twitter),
            val_str(telegram), val_str(discord), val_u64(total_supply),
            val_u64(team_bps), val_u64(vesting_duration)]


def propose_deposits(submission_fee: int, asset_budget: int, liquidity: int,
                     xel_asset: str = "0" * 64) -> dict:
    """Attached deposit: EXACTLY submission_fee + asset_budget + liquidity
    XEL (v4: the budget covers the chain's Asset::create cost; unused part
    refunded to the creator at creation — D13)."""
    return {xel_asset: submission_fee + asset_budget + liquidity}


def buy_deposits(xel_amount: int, xel_asset: str = "0" * 64) -> dict:
    return {xel_asset: xel_amount}


def sell_deposits(token_amount: int, asset: str) -> dict:
    """v4 sell: attach the tokens you want to sell — the WHOLE deposit is
    sold (whole-deposit semantics, D14). `asset` is the project's asset
    hash (see LaunchpadReader.asset_info)."""
    return {asset: token_amount}


def finalize_topup_deposits(xel_amount: int, xel_asset: str = "0" * 64) -> dict:
    """Optional top-up on finalize_validation when the chain's asset
    creation cost rose above the earmarked budget (D13); the unused part
    of budget + top-up is refunded to the creator in the same transaction."""
    return {xel_asset: xel_amount}


def update_info_params(description: str, website: str, logo: str,
                       twitter: str, telegram: str, discord: str) -> list:
    """v3: social links ride along (D11) — updatable at any time."""
    return [val_str(description), val_str(website), val_str(logo),
            val_str(twitter), val_str(telegram), val_str(discord)]


def set_recovery_params_params(participants: int, ratio_bps: int) -> list:
    return [val_u64(participants), val_u64(ratio_bps)]


def set_vesting_bounds_params(min_topos: int, max_topos: int) -> list:
    return [val_u64(min_topos), val_u64(max_topos)]


def start_team_vesting_params(pid: int, duration: int) -> list:
    return [val_u64(pid), val_u64(duration)]


def set_dex_address_params(dex_hash: str) -> list:
    """Pin the LaunchDEX contract (D19) — must be a 64-hex-char string.
    Callable only while migrated_count == 0 (frozen forever after)."""
    from .protocol import val_hash
    return [val_hash(dex_hash)]


def pid_params(pid: int) -> list:
    return [val_u64(pid)]


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

    def dex_address(self) -> Optional[str]:
        """The pinned LaunchDEX contract (D19) — None while unset."""
        return self._key(GLOBAL_KEYS["dex_address"])

    def migrated_count(self) -> int:
        return self._key(GLOBAL_KEYS["migrated_count"], 0)

    def config(self) -> Dict[str, int]:
        return {name: self._key(key, DEFAULTS.get(name, 0))
                for name, key in GLOBAL_KEYS.items()
                if name in DEFAULTS}

    def admin(self) -> Optional[str]:
        return self._key(GLOBAL_KEYS["admin"])

    def stats(self) -> Dict[str, Any]:
        names = ("count", "pending_fees", "fees_collected_lifetime",
                 "total_volume", "total_curve_xel", "locked_refunds",
                 "total_buy_volume", "total_sell_volume", "total_trades",
                 "total_budgets", "migrated_count")
        out: Dict[str, Any] = {n: self._key(GLOBAL_KEYS[n], 0) for n in names}
        out["paused"] = self.paused()
        out["dex_address"] = self.dex_address()
        return out

    def volume_stats(self) -> Dict[str, int]:
        """Protocol-wide curve-era scoreboard (D12, mirrors get_volume_stats).
        Pool-era volumes live on LaunchDEX (xvault.dex.DexReader)."""
        names = ("total_volume", "total_buy_volume", "total_sell_volume",
                 "total_trades")
        return {n: self._key(GLOBAL_KEYS[n], 0) for n in names}

    def project(self, pid: int) -> Dict[str, Any]:
        """Everything the frontend needs for one project card."""
        out: Dict[str, Any] = {"id": pid}
        for attr, field in (("creator", F_CREATOR), ("status", F_STATUS),
                            ("name", F_NAME), ("symbol", F_SYMBOL),
                            ("description", F_DESC), ("website", F_WEBSITE),
                            ("logo", F_LOGO),
                            ("twitter", F_TWITTER), ("telegram", F_TELEGRAM),
                            ("discord", F_DISCORD),
                            ("total_supply", F_SUPPLY),
                            ("team_bps", F_TEAM_BPS),
                            ("liquidity", F_LIQUIDITY),
                            ("reserves", F_RESERVES), ("curve", F_CURVE),
                            ("created_topo", F_CREATED),
                            ("deadline", F_DEADLINE),
                            ("supports", F_SUPPORTS), ("reports", F_REPORTS),
                            ("graduated", F_GRADUATED), ("round", F_ROUND),
                            ("volume", F_VOLUME),
                            ("direct_listing", F_DL),
                            ("bonding_start", F_BONDING_START),
                            ("team_paid", F_TEAM_PAID),
                            ("vesting_start", F_VESTING_START),
                            ("vesting_duration", F_VESTING_DURATION),
                            ("vesting_plan", F_VESTING_PLAN),
                            ("buy_volume", F_BUY_VOL),
                            ("sell_volume", F_SELL_VOL),
                            ("trades", F_TRADES),
                            ("last_trade_topo", F_LAST_TRADE),
                            ("market_cap", F_MCAP),
                            ("market_cap_high", F_MCAP_HIGH),
                            ("market_cap_grad", F_MCAP_GRAD),
                            ("asset", F_ASSET), ("asset_budget", F_BUDGET),
                            ("migrated", F_MIGRATED),
                            ("migrated_at", F_MIG_AT),
                            ("migrated_xel", F_MIG_XEL),
                            ("migrated_tokens", F_MIG_TOK),
                            ("dex_synced", F_DEX_SYNCED)):
            out[attr] = self._key(proj_key(pid, field))
        status = out.get("status") or 0
        out["status_label"] = STATUS_LABELS.get(status, "unknown")
        return out

    def social_links(self, pid: int) -> Dict[str, str]:
        """(D11) — empty string means no link."""
        p = self.project(pid)
        return {"twitter": p["twitter"] or "",
                "telegram": p["telegram"] or "",
                "discord": p["discord"] or ""}

    def trading_stats(self, pid: int) -> Dict[str, int]:
        """Per-project curve-era scoreboard (D12, mirrors get_trading_stats).
        Post-migration this freezes — pool-era stats live on LaunchDEX."""
        p = self.project(pid)
        return {"buy_volume": p["buy_volume"] or 0,
                "sell_volume": p["sell_volume"] or 0,
                "total_volume": p["volume"] or 0,
                "trades": p["trades"] or 0,
                "last_trade_topo": p["last_trade_topo"] or 0}

    def market_cap_history(self, pid: int) -> Dict[str, int]:
        """Stored market-cap series (D12, mirrors get_market_cap_history)."""
        p = self.project(pid)
        return {"current": p["market_cap"] or 0,
                "all_time_high": p["market_cap_high"] or 0,
                "at_graduation": p["market_cap_grad"] or 0}

    def asset_info(self, pid: int) -> Dict[str, Any]:
        """The real token's identity (D13, mirrors get_asset_info):
        created / hash / budget earmark. `mintable`/`max_supply` come from
        the chain's asset registry itself (get_asset in the daemon RPC),
        not from launchpad storage — the whole point of the Fixed cap."""
        p = self.project(pid)
        return {"created": p["asset"] is not None,
                "asset": p["asset"],
                "budget": p["asset_budget"] or 0}

    def migration_info(self, pid: int) -> Dict[str, Any]:
        """The pool-era bridge (D15/D19, mirrors get_migration_info)."""
        p = self.project(pid)
        return {"migrated": bool(p["migrated"]),
                "migrated_at": p["migrated_at"] or 0,
                "xel_sent": p["migrated_xel"] or 0,
                "tokens_sent": p["migrated_tokens"] or 0,
                "dex_address": self.dex_address(),
                "dex_trust_synced": bool(p["dex_synced"])}

    def proposal_data(self, pid: int) -> Dict[str, Any]:
        """The one-call voting card (D10/D7/D13, mirrors get_proposal_data):
        what is being sold, what the team takes, the vesting plan, which
        graduation path, when the window closes, and the earmarked asset
        budget."""
        p = self.project(pid)
        return {"liquidity": p["liquidity"] or 0,
                "total_supply": p["total_supply"] or 0,
                "team_bps": p["team_bps"] or 0,
                "vesting_plan": p["vesting_plan"] or 0,
                "direct_listed": bool(p["direct_listing"]),
                "created_topo": p["created_topo"] or 0,
                "validation_end": p["deadline"] or 0,
                "asset_budget": p["asset_budget"] or 0}

    def team_allocation(self, pid: int, topo: int = 0) -> Dict[str, int]:
        """Team allocation panel (D3): alloc, paid, vesting, claimable_now.

        `topo` is the reference topoheight for the vesting stream (the
        daemon's current topoheight in production; tests pass explicit
        values). Mirrors the contract's get_team_allocation view. The
        CLAIMED amounts are the creator's private data (D18) — payouts were
        confidential transfers.
        """
        p = self.project(pid)
        team = team_alloc_of(p["total_supply"] or 0, p["team_bps"] or 0)
        paid = p["team_paid"] or 0
        unlocked = team_unlocked(
            team, bool(p["graduated"]),
            p["vesting_start"] or 0, p["vesting_duration"] or 0,
            p["status"] or 0, p["bonding_start"] or 0,
            self._key(GLOBAL_KEYS["team_unlock_delay"],
                      DEFAULTS["team_unlock_delay"]),
            topo)
        return {
            "team_alloc": team,
            "team_paid": paid,
            "team_remaining": team_remaining(team, paid),
            "vesting_start": p["vesting_start"] or 0,
            "vesting_duration": p["vesting_duration"] or 0,
            "claimable_now": max(unlocked - paid, 0),
            "vesting_plan": p["vesting_plan"] or 0,
        }

    def has_voted(self, pid: int, round_no: int, voter: str) -> bool:
        return bool(self._key(vote_key(pid, round_no, voter), False))

    def quotes(self, pid: int, fee_bps: Optional[int] = None) -> Dict[str, int]:
        p = self.project(pid)
        reserves, curve = p["reserves"] or 0, p["curve"] or 0
        graduated = bool(p["graduated"])
        if fee_bps is None:
            # the project's EFFECTIVE fee (D8), exactly like the contract
            fee_bps = current_fee_bps(
                graduated,
                self._key(GLOBAL_KEYS["trading_fee_bps"],
                          DEFAULTS["trading_fee_bps"]),
                self._key(GLOBAL_KEYS["graduated_fee_bps"],
                          DEFAULTS["graduated_fee_bps"]))
        return {
            "reserves": reserves,
            "curve": curve,
            "price": current_price(reserves, curve),
            "market_cap": market_cap(reserves, curve, p["total_supply"] or 0,
                                     p["team_bps"] or 0, graduated,
                                     p["team_paid"] or 0),
            "fee_bps": fee_bps,
            "graduated": graduated,
        }
