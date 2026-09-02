#!/usr/bin/env python3
"""
============================================================================
 XELIS Vault — CLI chain backend (live on-chain layer)
 ============================================================================
 Real interactions with the deployed contracts, built on the same proven
 primitives used by the deployment/test tooling (protocol.py):

   - wallet ops  : build_transaction / invoke_contract (ValueCell params)
   - daemon reads: get_contract_data (string keys), get_contract_balance

 Contract hashes & asset hashes come from the network bundle
 (network/testnet.json) so the CLI always targets the current deployment.
 Entry ids are the COMPILED chunk indices (verified on-chain).

 Only flows verified end-to-end on-chain are exposed as transactions.
 Everything else is shown as "coming soon" by the CLI.
 ============================================================================
"""
from __future__ import annotations

import json
import secrets
import sys
import time
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).parent))
from protocol import (
    WalletClient, DaemonClient, RPCError,
    val_u64, val_u128, val_u8, val_u16, val_str, val_hash, val_addr, val_bytes,
    parse_cell,
)

ZERO_HASH = "0" * 64

MIN_AUCTION_DURATION_BLOCKS = 1440

# ---------------------------------------------------------------------------
# Network bundle loading (contracts + assets)
# ---------------------------------------------------------------------------

def _bundle_candidates() -> list:
    here = Path(__file__).parent
    return [
        here.parent / "network" / "testnet.json",      # installed layout
        here.parent.parent / "network" / "testnet.json",
        here / "network_testnet.json",
    ]


def load_bundle() -> dict:
    for c in _bundle_candidates():
        if c.exists():
            try:
                return json.loads(c.read_text())
            except Exception:
                pass
    return {}


# Fallbacks (current testnet deployment) if the bundle file is missing.
# Registry `cur_<Name>` is always preferred over these static tables.
_FALLBACK = {
    "contracts": {
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
    },
    "vlt_asset": "3f1f9a3c0a90a0a548670a069e8edad5c0c20914b20b289426b2857c6715f58f",
    "xusd_asset": "be39794c4a32f231d410c8be3a4d9e80455c667d902c5edf8527dea52533356e",
}

# ContractRegistry names for live resolution (registry is authoritative).
_REGISTRY_NAMES = {
    "staked_oracle": "StakedOracle",
    "miner": "XelisVaultMiner",
    "vlt_token": "VLTToken",
    "xusd": "xUSD",
    "vault_engine": "VaultEngineV3",
    "vault_swap": "VaultSwap",
    "psm": "PSM",
    "savings_rate": "SavingsRate",
    "mixer": "PrivacyMixer",
    "treasury_vault": "TreasuryVault",
    "asset_vault": "AssetVault",
    "faucet": "FaucetContract",
    "airdrop": "AirdropTracker",
}
# ---------------------------------------------------------------------------
# Compiled entry-chunk ids (source of truth: docs/entry_chunk_ids.json)
# ---------------------------------------------------------------------------

CHUNKS = {
    "PSM":            {"mint": 8, "redeem": 9},
    "VaultEngineV3":  {"deposit": 17, "borrow": 18, "repay": 19, "withdraw": 20},
    "VaultSwapV2":    {"create_pool": 16, "add_liquidity": 17, "swap": 18},
    "SavingsRate":    {"deposit": 8, "withdraw": 9, "claim_interest": 10},
    "PrivacyMixer":   {"deposit": 6, "withdraw": 7},
    "TreasuryVault":  {"propose": 9, "confirm": 10, "revoke": 11, "execute": 12, "deposit": 16},
    "AssetVault":     {"mint": 5, "transfer_asset": 6, "create_asset": 4,
                        "set_registry": 10},
    "StakedOracle":   {"submit_price": 16, "aggregate_now": 17},
    "XelisVaultMiner": {"register_miner": 15, "enable_service": 16, "increase_stake": 18,
                        "submit_heartbeat": 21},
    "GovernanceVault": {"stake": 4, "unstake": 5, "claim_rewards": 6,
                         "get_total_staked": 9, "get_user_staked": 10,
                         "notify_reward_amount": 12, "set_reward_distributor": 13},
    "Governor":        {"propose": 3, "vote": 4, "queue": 5, "cancel": 6,
                         "get_proposal_count": 7},
    "FlashLoan":       {"flash_loan": 6, "get_fee_bps": 7, "get_total_earned": 8,
                         "get_available_liquidity": 9, "set_fee_bps": 10,
                         "verify_callback": 23},
    "FlashCallback":   {"on_flash_loan": 2, "set_flash_loan": 4, "claim_profit": 5},
    "PeerLoan":        {"create_offer": 6, "cancel_offer": 7, "accept_offer": 8,
                         "repay": 9, "claim_collateral": 10, "get_offer": 11,
                         "get_offers_count": 12},
    "SyndicatePool":   {"create_pool": 8, "supply": 9, "withdraw_supply": 10,
                         "activate_pool": 11, "repay": 12, "claim": 13,
                         "get_pool": 14, "get_lender_position": 15,
                         "get_pools_count": 16},
    "SealedBidAuction": {"create_auction": 13, "commit": 14, "reveal": 15,
                          "settle": 16, "declare_winner": 17, "refund_bid": 18,
                          "claim_asset": 19, "claim_proceeds": 20,
                          "get_auction": 21, "get_auctions_count": 22},
    "Timelock":         {"execute_proposal": 6, "cancel_proposal": 7,
                          "set_min_delay": 9, "set_governor": 11},
    "VaultChat":        {"register_session": 7, "create_group": 8,
                           "add_group_member": 9, "anchor_messages": 11,
                           "store_message": 38, "store_group_message": 48,
                           "set_relayer": 20, "set_relayer_fee": 51,
                           "claim_relayer_fees": 56, "stake_relayer_bond": 121,
                           "register_as_relayer": 66,
                           "update_relayer_endpoint": 119,
                           "send_direct_message": 113, "get_session": 13,
                           "get_group": 14, "is_active": 16,
                           "get_last_anchor": 17, "get_groups_count": 18},
    "MinerDelegation":  {"register_miner_profile": 5, "update_miner_profile": 6,
                         "delegate": 7, "undelegate": 8, "execute_undelegate": 9,
                         "claim_delegator_rewards": 10, "claim_miner_rewards": 11},
    "AirdropTracker":  {"record_mainnet_address": 22},
}

# Airdrop categories (AirdropTracker.slx consts).
AIRDROP_CATEGORIES = {
    1: "Mining",
    2: "Relayer",
    3: "Governance",
    4: "Chat",
    5: "Liquidity",
    6: "Bounty",
    7: "Community",
}

# AirdropTracker.storage string keys (source: contracts/airdrop/AirdropTracker.slx)
_AIR_USER_PREFIX = "user_"
_AIR_LIST_PREFIX = "ul_"
_AIR_LB_PREFIX = "lb_"
_AIR_CAT_PREFIX = "ct_"

DECIMALS = 8


class OpResult:
    """Outcome of a transaction op."""
    def __init__(self, ok: bool, tx: str = "", reason: str = "",
                 contract: str = "", entry: str = ""):
        self.ok = ok
        self.tx = tx
        self.reason = reason
        self.contract = contract
        self.entry = entry

    def __bool__(self):
        return self.ok


# ---------------------------------------------------------------------------
# Backend
# ---------------------------------------------------------------------------

class Backend:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        bundle = load_bundle() or _FALLBACK
        contracts = dict(_FALLBACK["contracts"])
        contracts.update({k: v for k, v in bundle.get("contracts", {}).items() if v})
        # accept both naming styles from older bundles
        alias = {"oracle": "staked_oracle", "vault_engine_v3": "vault_engine",
                 "psm_contract": "psm"}
        for a, b in alias.items():
            if a in contracts and b not in contracts:
                contracts[b] = contracts[a]
        self.contracts = contracts
        self.vlt_asset = bundle.get("vlt_asset") or _FALLBACK["vlt_asset"]
        self.xusd_asset = bundle.get("xusd_asset") or _FALLBACK["xusd_asset"]
        self.xel_asset = ZERO_HASH
        self.feed_id = int(bundle.get("oracle_feed_id", 0))

        daemon_url = cfg.get("rpc_url") or "http://127.0.0.1:18081"
        wallet_url = cfg.get("wallet_url") or ""
        if daemon_url and not daemon_url.endswith("/json_rpc"):
            daemon_url += "/json_rpc"
        if wallet_url and not wallet_url.endswith("/json_rpc"):
            wallet_url += "/json_rpc"
        self.daemon = DaemonClient(daemon_url)
        auth = (cfg.get("wallet_user") or "wallet", cfg.get("wallet_pass") or "testpass")
        self.wallet = WalletClient(wallet_url, auth) if wallet_url else None
        self._resolve_via_registry()
        self._ensure_tracked_assets()

    def _resolve_via_registry(self):
        """ContractRegistry cur_<Name> overrides static tables (authoritative)."""
        reg = (self.contracts.get("registry")
               or self.contracts.get("ContractRegistry")
               or self.contracts.get("contract_registry"))
        if not reg:
            return
        resolved = {}
        for key, name in _REGISTRY_NAMES.items():
            try:
                h = self.daemon.read_key(reg, f"cur_{name}")
            except Exception:
                continue
            if h and isinstance(h, str) and len(h) == 64:
                resolved[key] = h                # snake_case alias
                resolved[name] = h               # canonical CamelCase key
        self.contracts.update(resolved)

    def _ensure_tracked_assets(self):
        """Make sure the wallet knows about VLT and xUSD before balance checks."""
        if not self.wallet:
            return
        try:
            for asset in (self.vlt_asset, self.xusd_asset):
                if asset and asset != ZERO_HASH:
                    self.wallet.track_asset(asset)
        except Exception:
            pass

    # -- helpers ----------------------------------------------------------

    @property
    def address(self) -> str:
        addr = self.cfg.get("miner_address") or ""
        if addr:
            return addr
        try:
            return self.wallet.address() or ""
        except Exception:
            return ""

    @property
    def has_wallet(self) -> bool:
        return bool(self.wallet)

    def ping_wallet(self) -> bool:
        if not self.wallet:
            return False
        try:
            self.wallet.address()
            return True
        except Exception:
            return False

    def C(self, key: str) -> str:
        return self.contracts.get(key, "")

    def topo(self) -> int:
        try:
            return self.daemon.topoheight()
        except Exception:
            return 0

    def balance(self, asset: str = ZERO_HASH) -> Optional[int]:
        if not self.wallet:
            return None
        try:
            if asset and asset != ZERO_HASH:
                try:
                    self.wallet.track_asset(asset)
                except Exception:
                    pass
            return self.wallet.balance(asset)
        except Exception as e:
            try:
                return self.wallet.balance(asset)
            except Exception:
                return None

    def balances(self) -> dict:
        out = {}
        for name, asset in (("XEL", self.xel_asset), ("VLT", self.vlt_asset),
                            ("xUSD", self.xusd_asset)):
            b = self.balance(asset)
            out[name] = b
        return out

    def fmt(self, amount: Optional[int], suffix: str = "") -> str:
        if amount is None:
            return "--"
        v = amount / (10 ** DECIMALS)
        s = f"{v:,.4f}" if v >= 1 else f"{v:.8f}".rstrip("0").rstrip(".") or "0"
        return f"{s}{(' ' + suffix) if suffix else ''}"

    def price(self):
        """(price_raw, feed_topo, stale) from StakedOracle storage."""
        so = self.C("staked_oracle")
        if not so:
            return None
        fg = self.daemon.read_key(so, f"fg_{self.feed_id}")
        if isinstance(fg, list) and len(fg) >= 2:
            price, feed_topo = int(fg[0]), int(fg[1])
            hsb = self.daemon.read_key(so, "hsb")
            hard_stale = int(hsb) if isinstance(hsb, int) else 500
            stale = (self.topo() - feed_topo) > hard_stale
            return price, feed_topo, stale
        return None

    def price_usd(self) -> Optional[float]:
        p = self.price()
        return (p[0] / 10 ** DECIMALS) if p else None

    # -- protocol stats -----------------------------------------------------

    def miner_stats(self) -> dict:
        mn = self.C("miner")
        out = {}
        if not mn:
            return out
        ts = self.daemon.read_key(mn, "ts")
        tb = self.daemon.read_key(mn, "tb")
        dist = self.daemon.read_key(mn, "dist")
        ms = self.daemon.read_key(mn, "ms")
        if isinstance(ts, int): out["total_staked"] = ts
        if isinstance(tb, int): out["budget"] = tb
        if isinstance(dist, int): out["distributed"] = dist
        if isinstance(ms, int): out["min_stake"] = ms
        return out

    def my_miner(self) -> Optional[list]:
        mn = self.C("miner")
        addr = None
        if self.wallet:
            try:
                addr = self.wallet.address()
            except Exception:
                pass
        if not addr:
            addr = self.address
        if not mn or not addr:
            return None
        m = self.daemon.read_key(mn, f"miner_{addr}")
        return m if isinstance(m, list) else None

    def psm_reserves(self) -> dict:
        psm = self.C("psm")
        out = {}
        if not psm:
            return out
        try:
            out["xel"] = self.daemon.get_contract_balance(psm, self.xel_asset)
        except Exception:
            pass
        try:
            out["xusd"] = self.daemon.get_contract_balance(psm, self.xusd_asset)
        except Exception:
            pass
        return out

    def amm_pools(self) -> list:
        vs = self.C("vault_swap")
        if not vs:
            return []
        count = self.daemon.read_key(vs, "pc")
        pools = []
        n = int(count) if isinstance(count, int) else 0
        pairs = [(self.xel_asset, self.xusd_asset), (self.xel_asset, self.vlt_asset),
                 (self.vlt_asset, self.xusd_asset)]
        for a, b in pairs:
            lo, hi = (a, b) if a < b else (b, a)
            pool = self.daemon.read_key(vs, f"p_{lo}_{hi}")
            if isinstance(pool, list) and len(pool) >= 6:
                pools.append({"a": str(pool[0]), "b": str(pool[1]),
                              "reserve_a": int(pool[2]), "reserve_b": int(pool[3])})
        return pools

    def my_vaults(self) -> list:
        ve = self.C("vault_engine")
        addr = self.address
        if not ve or not addr:
            return []
        n = self.daemon.read_key(ve, "n")
        total = int(n) if isinstance(n, int) else 0
        vaults = []
        for i in range(1, min(total, 200) + 1):
            snap = self.daemon.read_key(ve, f"v{i}")
            if isinstance(snap, list) and len(snap) >= 10:
                owner = str(snap[0])
                if owner == addr:
                    vaults.append({
                        "id": i,
                        "collateral_asset": str(snap[1]),
                        "collateral": int(snap[2]),
                        "borrow_amount": int(snap[4]),
                        "last_update_topo": int(snap[6]),
                        "liquidated": bool(snap[7]),
                    })
        return vaults

    def health_factor(self, v: dict) -> Optional[float]:
        """Approximate HF: collateral value / debt value (xUSD ≈ $1)."""
        price = self.price_usd()
        if not price or not v:
            return None
        col_val = v["collateral"] / 10 ** DECIMALS * price
        debt_val = v["borrow_amount"] / 10 ** DECIMALS
        if debt_val == 0:
            return float("inf")
        return col_val / debt_val

    MIN_CR = 2.0  # 200% minimum collateral ratio

    def savings_stats(self) -> dict:
        sr = self.C("savings_rate")
        out = {}
        if not sr:
            return out
        td = self.daemon.read_key(sr, "td")
        ab = self.daemon.read_key(sr, "ab")
        if isinstance(td, int):
            out["total_deposits"] = td
        if isinstance(ab, int):
            out["apy_bps"] = ab
        try:
            out["contract_xusd"] = self.daemon.get_contract_balance(sr, self.xusd_asset)
        except Exception:
            pass
        return out

    def mixer_stats(self) -> dict:
        mx = self.C("mixer")
        out = {}
        if not mx:
            return out
        tmc = self.daemon.read_key(mx, "tmc")
        tm = self.daemon.read_key(mx, f"tm_{self.xel_asset}")
        if isinstance(tmc, int): out["total_mixes"] = tmc
        if isinstance(tm, int): out["total_mixed"] = tm
        return out

    def treasury_info(self) -> dict:
        tv = self.C("treasury_vault")
        out = {}
        if not tv:
            return out
        sc = self.daemon.read_key(tv, "sc")
        q = self.daemon.read_key(tv, "q")
        pc = self.daemon.read_key(tv, "pc")
        if isinstance(sc, int): out["signers"] = sc
        if isinstance(q, int): out["quorum"] = q
        if isinstance(pc, int): out["proposals"] = pc
        try:
            out["xel"] = self.daemon.get_contract_balance(tv, self.xel_asset)
            out["xusd"] = self.daemon.get_contract_balance(tv, self.xusd_asset)
        except Exception:
            pass
        return out

    def rwa_asset_info(self) -> dict:
        av = self.C("asset_vault")
        out = {}
        if not av:
            return out
        ah = self.daemon.read_key(av, "ah")
        if ah:
            out["asset_hash"] = str(ah)
            info = self.daemon.read_key(av, "ai")
            if isinstance(info, list):
                out["info"] = info
            try:
                out["supply"] = None  # native asset supply needs asset read
            except Exception:
                pass
        return out

    # -- faucet --------------------------------------------------------------

    def faucet_info(self) -> dict:
        fa = self.C("faucet")
        out = {}
        if not fa:
            return out
        xa = self.daemon.read_key(fa, "xa")
        va = self.daemon.read_key(fa, "va2")
        cd = self.daemon.read_key(fa, "cd")
        if isinstance(xa, int): out["xel_per_claim"] = xa
        if isinstance(va, int): out["vlt_per_claim"] = va
        if isinstance(cd, int): out["cooldown"] = cd
        try:
            out["xel_pool"] = self.daemon.get_contract_balance(fa, self.xel_asset)
            out["vlt_pool"] = self.daemon.get_contract_balance(fa, self.vlt_asset)
        except Exception:
            pass
        last = self.daemon.read_key(fa, f"ulc_{self.address}") if self.address else None
        if isinstance(last, int):
            out["my_last_claim_topo"] = last
        return out

    # =========================================================================
    # Transaction ops — only flows verified end-to-end on-chain
    # =========================================================================

    def _invoke(self, contract_key: str, fn: str, params=None, deposits=None,
                max_gas: int = 10_000_000) -> OpResult:
        contract = self.C(contract_key)
        chunk = CHUNKS.get(contract_key, {}).get(fn)
        if not contract or chunk is None:
            return OpResult(False, reason=f"{contract_key}.{fn} unavailable")
        if not self.wallet:
            return OpResult(False, reason="No wallet connected (read-only mode)")
        try:
            tx = self.wallet.invoke(contract, chunk, params=params,
                                    deposits=deposits or {}, max_gas=max_gas)
        except RPCError as e:
            msg = str(e)
            if "Module error: " in msg:
                msg = msg.split("Module error: ", 1)[1].split(":")[0].strip()
            elif "Server returned error: [" in msg:
                msg = msg.split("Server returned error: ", 1)[1][:160]
            return OpResult(False, reason=msg[:200])
        except Exception as e:
            return OpResult(False, reason=str(e)[:200])
        return OpResult(True, tx=tx, contract=contract_key, entry=fn)

    # --- PSM ---------------------------------------------------------------

    def psm_mint(self, xel_amount_atomic: int, min_xusd_out: int = 1) -> OpResult:
        expected = int(xel_amount_atomic * (self.price_usd() or 1.0))
        min_out = max(min_xusd_out, int(expected * 0.95))  # 5% slippage guard
        return self._invoke("PSM", "mint",
                            [val_u64(xel_amount_atomic), val_u64(min_out)],
                            deposits={self.xel_asset: {"amount": xel_amount_atomic}},
                            max_gas=15_000_000)

    def psm_redeem(self, xusd_amount_atomic: int, min_xel_out: int = 1) -> OpResult:
        usd = self.price_usd() or 1.0
        expected_xel = int(xusd_amount_atomic / usd)
        min_out = max(min_xel_out, int(expected_xel * 0.90))  # 10% slippage guard
        return self._invoke("PSM", "redeem",
                            [val_u64(xusd_amount_atomic), val_u64(min_out)],
                            deposits={self.xusd_asset: {"amount": xusd_amount_atomic}},
                            max_gas=15_000_000)

    # --- VaultEngine V3 ------------------------------------------------------

    def vault_deposit(self, xel_amount_atomic: int) -> OpResult:
        salt = secrets.token_hex(32)
        return self._invoke("VaultEngineV3", "deposit",
                            [val_hash(self.xel_asset), val_u64(xel_amount_atomic),
                             val_hash(salt)],
                            deposits={self.xel_asset: {"amount": xel_amount_atomic}},
                            max_gas=20_000_000)

    def vault_borrow(self, vault_id: int, xusd_amount_atomic: int) -> OpResult:
        return self._invoke("VaultEngineV3", "borrow",
                            [val_u64(vault_id), val_u64(xusd_amount_atomic)],
                            max_gas=25_000_000)

    def vault_repay(self, vault_id: int, xusd_amount_atomic: int) -> OpResult:
        return self._invoke("VaultEngineV3", "repay",
                            [val_u64(vault_id), val_u64(xusd_amount_atomic)],
                            deposits={self.xusd_asset: {"amount": xusd_amount_atomic}},
                            max_gas=25_000_000)

    def vault_withdraw(self, vault_id: int, xel_amount_atomic: int) -> OpResult:
        return self._invoke("VaultEngineV3", "withdraw",
                            [val_u64(vault_id), val_u64(xel_amount_atomic)],
                            max_gas=20_000_000)

    def vault_get(self, vault_id: int) -> Optional[dict]:
        """Full snapshot of one vault (storage key v<id>)."""
        ve = self.C("vault_engine")
        if not ve:
            return None
        snap = self.daemon.read_key(ve, f"v{vault_id}")
        if not (isinstance(snap, list) and len(snap) >= 10):
            return None
        return {
            "id": vault_id,
            "owner": str(snap[0]),
            "collateral_asset": str(snap[1]),
            "collateral": int(snap[2]),
            "borrow_asset": str(snap[3]),
            "borrow_amount": int(snap[4]),
            "last_update_topo": int(snap[6]),
            "liquidated": bool(snap[7]),
        }

    def vault_max_borrow(self, vault_id: int) -> int:
        """Max xUSD borrowable (atomic): collateral value / MIN_CR (200%).

        Integer arithmetic only — float division would truncate small vaults
        (e.g. 0.9 xUSD -> int(0.9039) = 0). Priced in USD atomic (1e8).
        Returns 0 if the oracle feed is stale (vault would revert `stale`).
        """
        v = self.vault_get(vault_id)
        if not v or v["liquidated"]:
            return 0
        p = self.price()
        if not p or p[2]:
            return 0
        price_raw = int(p[0])
        col_value_usd = v["collateral"] * price_raw // 10 ** DECIMALS
        max_total = int(col_value_usd / self.MIN_CR)
        return max(0, max_total - v["borrow_amount"])

    def verify_onchain(self, tx: str, timeout: float = 12.0) -> str:
        """Return '' if the tx committed cleanly, else the on-chain revert reason.
        Polls the contract logs (written async after mining) for an exit_error."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                logs = self.daemon.get_contract_logs(tx)
            except Exception:
                logs = []
            if isinstance(logs, list) and logs:
                for entry in logs:
                    if not isinstance(entry, dict):
                        continue
                    if entry.get("type") == "exit_error":
                        v = entry.get("value") or {}
                        err = v.get("err") if isinstance(v, dict) else str(v)
                        if isinstance(err, dict):
                            return err.get("message") or str(err)
                        return str(err)
                    if entry.get("exit_error"):
                        return str(entry["exit_error"])
                return ""  # clean exit (no error logged)
            time.sleep(1.5)
        return ""  # could not observe — treat as success (builds already confirmed)

    # --- AMM -----------------------------------------------------------------

    def amm_swap(self, asset_in: str, asset_out: str,
                 amount_in_atomic: int, min_out_atomic: int = 1) -> OpResult:
        reserves = self._pool_reserves(asset_in, asset_out)
        if reserves:
            r_in, r_out = reserves
            if r_in > 0:
                out_est = amount_in_atomic * r_out // (r_in + amount_in_atomic)
                min_out_atomic = max(min_out_atomic, int(out_est * 0.90))
        return self._invoke("VaultSwapV2", "swap",
                            [val_hash(asset_in), val_hash(asset_out),
                             val_u64(amount_in_atomic), val_u64(min_out_atomic)],
                            deposits={asset_in: {"amount": amount_in_atomic}},
                            max_gas=25_000_000)

    def amm_add_liquidity(self, asset_a: str, amount_a_atomic: int,
                          asset_b: str, amount_b_atomic: int) -> OpResult:
        lo, hi = (asset_a, asset_b) if asset_a < asset_b else (asset_b, asset_a)
        lo_amt = amount_a_atomic if lo == asset_a else amount_b_atomic
        hi_amt = amount_b_atomic if lo == asset_a else amount_a_atomic
        return self._invoke("VaultSwapV2", "add_liquidity",
                            [val_hash(lo), val_hash(hi), val_u64(lo_amt), val_u64(hi_amt)],
                            deposits={lo: {"amount": lo_amt}, hi: {"amount": hi_amt}},
                            max_gas=30_000_000)

    def _pool_reserves(self, a: str, b: str):
        vs = self.C("vault_swap")
        if not vs:
            return None
        lo, hi = (a, b) if a < b else (b, a)
        pool = self.daemon.read_key(vs, f"p_{lo}_{hi}")
        if isinstance(pool, list) and len(pool) >= 6:
            ra, rb = int(pool[2]), int(pool[3])
            return (ra, rb) if lo == a else (rb, ra)
        return None

    # --- Savings -------------------------------------------------------------

    def savings_deposit(self, xusd_amount_atomic: int) -> OpResult:
        return self._invoke("SavingsRate", "deposit",
                            [val_u64(xusd_amount_atomic)],
                            deposits={self.xusd_asset: {"amount": xusd_amount_atomic}},
                            max_gas=15_000_000)

    def savings_withdraw(self, xusd_amount_atomic: int) -> OpResult:
        return self._invoke("SavingsRate", "withdraw",
                            [val_u64(xusd_amount_atomic)], max_gas=15_000_000)

    def savings_claim_interest(self) -> OpResult:
        return self._invoke("SavingsRate", "claim_interest", [], max_gas=15_000_000)

    # --- Privacy Mixer (private note + shared pool; no sender/recipient link)

    def mixer_deposit(self, asset: str, amount_atomic: int, secret: str) -> OpResult:
        """Deposit into the shared pool, creating a private note blake3(secret).
        The contract stores NO sender identity. Keep `secret` (64 hex) to withdraw."""
        return self._invoke("PrivacyMixer", "deposit",
                            [val_hash(asset), val_hash(secret)],
                            deposits={asset: {"amount": amount_atomic}},
                            max_gas=20_000_000)

    def mixer_withdraw(self, recipient: str, asset: str,
                       amount_atomic: int, secret: str) -> OpResult:
        """Present secret to destroy the note and pull `amount` from the shared
        pool to `recipient` (any address). No on-chain sender link."""
        return self._invoke("PrivacyMixer", "withdraw",
                            [val_addr(recipient), val_hash(asset),
                             val_u64(amount_atomic), val_hash(secret)],
                            max_gas=20_000_000)

    def mixer_note_balance(self, asset: str, secret: str) -> int | None:
        """Remaining amount drainable for a secret (blake3(secret)); 0 if absent."""
        mx = self.C("mixer")
        if not mx or not self.daemon:
            return None
        try:
            import blake3 as _b3
            commitment = _b3.blake3(bytes.fromhex(secret)).hexdigest()
        except Exception:
            return None
        v = self.daemon.read_key(mx, f"n_{asset}_" + commitment)
        return int(v) if isinstance(v, int) else None

    # --- Treasury Vault (multisig) --------------------------------------------

    def treasury_deposit(self, asset: str, amount_atomic: int) -> OpResult:
        return self._invoke("TreasuryVault", "deposit",
                            [val_hash(asset), val_u64(amount_atomic)],
                            deposits={asset: {"amount": amount_atomic}},
                            max_gas=10_000_000)

    def treasury_propose(self, asset: str, to: str, amount_atomic: int,
                         data_hex: str = "") -> OpResult:
        return self._invoke("TreasuryVault", "propose",
                            [val_hash(asset), val_addr(to),
                             val_u64(amount_atomic), val_bytes(data_hex)],
                            max_gas=10_000_000)

    def treasury_confirm(self, proposal_id: int) -> OpResult:
        return self._invoke("TreasuryVault", "confirm", [val_u64(proposal_id)])

    def treasury_revoke(self, proposal_id: int) -> OpResult:
        return self._invoke("TreasuryVault", "revoke", [val_u64(proposal_id)])

    def treasury_execute(self, proposal_id: int) -> OpResult:
        return self._invoke("TreasuryVault", "execute", [val_u64(proposal_id)],
                            max_gas=15_000_000)

    # --- RWA / AssetVault (issuer) ---------------------------------------------

    def rwa_mint(self, to: str, amount_atomic: int) -> OpResult:
        return self._invoke("AssetVault", "mint", [val_addr(to), val_u64(amount_atomic)],
                            max_gas=15_000_000)

    def rwa_transfer(self, to: str, amount_atomic: int) -> OpResult:
        av = self.C("asset_vault")
        ah = self.daemon.read_key(av, "ah") if av else None
        if not ah:
            return OpResult(False, reason="No RWA asset created yet")
        ah = str(ah)
        try:
            self.wallet.track_asset(ah)
        except Exception:
            pass  # already tracked
        return self._invoke("AssetVault", "transfer_asset",
                            [val_addr(to), val_u64(amount_atomic)],
                            deposits={ah: {"amount": amount_atomic}},
                            max_gas=15_000_000)

    # --- Miner actions -----------------------------------------------------------

    def miner_heartbeat(self) -> OpResult:
        return self._invoke("XelisVaultMiner", "submit_heartbeat", [])

    def miner_increase_stake(self, vlt_amount_atomic: int) -> OpResult:
        return self._invoke("XelisVaultMiner", "increase_stake",
                            [val_u64(vlt_amount_atomic)],
                            deposits={self.vlt_asset: {"amount": vlt_amount_atomic}})

    def miner_register(self, endpoint_url: str, services_mask: int,
                       stake_atomic: int) -> OpResult:
        """Register this wallet as a miner with the XelisVaultMiner contract.

        `miner_pubkey` is a random 32-byte hash identifying this miner's service
        key on-chain (contract requires it non-zero on register). `stake_atomic`
        is attached as the VLT deposit — the contract requires `>= MIN_STAKE`
        and refunds any excess above the minimum.
        """
        import os
        pubkey = os.urandom(32).hex()
        dep = {self.vlt_asset: {"amount": stake_atomic}} if stake_atomic > 0 else {}
        return self._invoke(
            "XelisVaultMiner", "register_miner",
            [val_str(endpoint_url), val_hash(pubkey), val_u8(services_mask & 0xFF)],
            deposits=dep, max_gas=25_000_000)

    def miner_stake_min(self) -> int | None:
        """The contract's MIN_STAKE (atomic) — used as the registration default."""
        mn = self.C("miner")
        if not mn:
            return None
        v = self.daemon.read_key(mn, "ms")
        return int(v) if isinstance(v, int) else None

    def miner_enable_service(self, service_id: int) -> OpResult:
        return self._invoke("XelisVaultMiner", "enable_service",
                            [val_u8(service_id)], max_gas=15_000_000)

    # --- Faucet -------------------------------------------------------------------

    def faucet_distribute(self, addresses: list) -> OpResult:
        fa = self.C("faucet")
        chunk = 6  # distribute(Address[])
        if not fa or not self.wallet:
            return OpResult(False, reason="Faucet unavailable")
        try:
            tx = self.wallet.invoke(fa, chunk,
                                    [{"type": "object", "value": [val_addr(a) for a in addresses]}],
                                    deposits={}, max_gas=10_000_000)
        except RPCError as e:
            msg = str(e)
            if "Module error: " in msg:
                msg = msg.split("Module error: ", 1)[1].split(":")[0].strip()
            return OpResult(False, reason=msg[:200])
        except Exception as e:
            return OpResult(False, reason=str(e)[:200])
        return OpResult(True, tx=tx)

    # --- Governance ----------------------------------------------------------

    def gov_stake(self, vlt_atomic: int, lock_days: int = 7) -> OpResult:
        return self._invoke("GovernanceVault", "stake",
                            [val_u64(vlt_atomic), val_u64(lock_days)],
                            deposits={self.vlt_asset: {"amount": vlt_atomic}},
                            max_gas=20_000_000)

    def gov_unstake(self, stake_id: int) -> OpResult:
        return self._invoke("GovernanceVault", "unstake",
                            [val_u64(stake_id)], max_gas=15_000_000)

    def gov_claim_rewards(self) -> OpResult:
        return self._invoke("GovernanceVault", "claim_rewards",
                            [], max_gas=20_000_000)

    def gov_total_staked(self) -> int | None:
        v = self._storage_read("GovernanceVault", "ts")
        return int(v) if v is not None else None

    def gov_user_staked(self) -> int | None:
        v = self._storage_read("GovernanceVault", "us_" + self._my_addr())
        return int(v) if v is not None else None

    def gov_stakes_count(self) -> int | None:
        v = self._storage_read("GovernanceVault", "sc")
        return int(v) if v is not None else None

    # --- Governor (on-chain governance) --------------------------------------

    def gov_propose(self, target: str, entry_id: int,
                    params_hex: str, description: str) -> OpResult:
        return self._invoke("Governor", "propose",
                            [val_hash(target), val_u16(entry_id),
                             val_bytes(params_hex), val_str(description)],
                            max_gas=30_000_000)

    def gov_vote(self, proposal_id: int, support: int) -> OpResult:
        return self._invoke("Governor", "vote",
                            [val_u64(proposal_id), val_u8(support)],
                            max_gas=20_000_000)

    def gov_queue(self, proposal_id: int) -> OpResult:
        return self._invoke("Governor", "queue",
                            [val_u64(proposal_id)], max_gas=30_000_000)

    def gov_count(self) -> int | None:
        v = self._storage_read("Governor", "pc")
        return int(v) if v is not None else None

    def gov_proposal_list(self, limit: int = 20) -> list:
        """Return proposals as parsed dicts (Proposal struct read from storage)."""
        gov = self.C("Governor")
        if not gov or not self.daemon:
            return []
        count = self.gov_count() or 0
        out = []
        for i in range(min(count, limit)):
            try:
                p = self.daemon.read_key(gov, f"p_{i}")
            except Exception:
                continue
            if not isinstance(p, list):
                continue
            def _g(idx, cast=int):
                try:
                    return cast(p[idx])
                except (IndexError, ValueError):
                    return None
            out.append({
                "id": _g(0),
                "proposer": _g(1, str),
                "target": (_g(2, str) or "")[:16],
                "entry_id": _g(3),
                "description": str(_g(5) or "")[:40],
                "start_topo": _g(6),
                "end_topo": _g(7),
                "yes": _g(8), "no": _g(9), "abstain": _g(10),
                "queued": bool(_g(11)), "cancelled": bool(_g(12)),
                "executed": bool(_g(13)),
            })
        out.sort(key=lambda x: (x["id"] or 0))
        return out

    def gov_voting_period(self) -> int | None:
        v = self._storage_read("Governor", "vp")
        return int(v) if v is not None else None

    # --- FlashLoan -----------------------------------------------------------

    def flashloan_borrow(self, asset: str, amount_atomic: int,
                         cb_hash: str, data: str = "") -> OpResult:
        return self._invoke("FlashLoan", "flash_loan",
                            [val_hash(asset), val_u64(amount_atomic),
                             val_hash(cb_hash), val_bytes(data)],
                            max_gas=30_000_000)

    def flashloan_fund(self, asset: str, amount_atomic: int) -> OpResult:
        """Fund FlashLoan liquidity via set_fee_bps (admin entry + deposit)."""
        return self._invoke("FlashLoan", "set_fee_bps",
                            [val_u64(9)],
                            deposits={asset: {"amount": amount_atomic}},
                            max_gas=10_000_000)

    def flashloan_verify_cb(self, cb_hash: str) -> OpResult:
        return self._invoke("FlashLoan", "verify_callback",
                            [val_hash(cb_hash)], max_gas=10_000_000)

    def flashloan_liquidity(self, asset: str) -> int | None:
        fl = self.C("FlashLoan")
        if not fl:
            return None
        try:
            return int(self.daemon.get_contract_balance(fl, asset) or 0)
        except Exception:
            return None

    def flashloan_earned(self) -> int | None:
        v = self._storage_read("FlashLoan", "te")
        return int(v) if v is not None else None

    def flashloan_fee_bps(self) -> int | None:
        """FlashLoan fee in basis points (storage key `fb`)."""
        v = self._storage_read("FlashLoan", "fb")
        return int(v) if v is not None else None

    # --- FlashCallback -------------------------------------------------------

    def flashcb_fund(self, asset: str, amount_atomic: int) -> OpResult:
        """Fund FlashCallback via set_flash_loan (sets FL ref + deposits)."""
        cb = self.C("FlashCallback")
        fl = self.C("FlashLoan")
        if not cb or not fl:
            return OpResult(False, reason="FlashCallback/FlashLoan unavailable")
        return self._invoke_raw(cb, CHUNKS["FlashCallback"]["set_flash_loan"],
                                [val_hash(fl)],
                                deposits={asset: {"amount": amount_atomic}},
                                max_gas=10_000_000)

    def flashcb_profit(self, asset: str) -> OpResult:
        cb = self.C("FlashCallback")
        chunk = CHUNKS["FlashCallback"]["claim_profit"]
        return self._invoke_raw(cb, chunk, [val_hash(asset)],
                                max_gas=10_000_000)

    def _invoke_raw(self, contract: str, chunk: int, params,
                    deposits=None, max_gas=10_000_000) -> OpResult:
        if not contract or not self.wallet:
            return OpResult(False, reason="Contract unavailable")
        try:
            tx = self.wallet.invoke(contract, chunk, params,
                                    deposits=deposits or {},
                                    max_gas=max_gas)
        except RPCError as e:
            msg = str(e)
            if "Module error: " in msg:
                msg = msg.split("Module error: ", 1)[1].split(":")[0].strip()
            return OpResult(False, reason=msg[:200])
        except Exception as e:
            return OpResult(False, reason=str(e)[:200])
        return OpResult(True, tx=tx)

    # --- PeerLoan ------------------------------------------------------------

    def pl_create_offer(self, asset_lent: str, amount_atomic: int,
                        interest_bps: int, duration_blocks: int,
                        collateral_asset: str,
                        collateral_amount: int) -> OpResult:
        return self._invoke("PeerLoan", "create_offer",
                            [val_hash(asset_lent), val_u64(amount_atomic),
                             val_u64(interest_bps), val_u64(duration_blocks),
                             val_hash(collateral_asset),
                             val_u64(collateral_amount)],
                            deposits={asset_lent: {"amount": amount_atomic}},
                            max_gas=25_000_000)

    def pl_cancel_offer(self, offer_id: int) -> OpResult:
        return self._invoke("PeerLoan", "cancel_offer",
                            [val_u64(offer_id)], max_gas=15_000_000)

    def pl_accept_offer(self, offer_id: int,
                        collateral_asset: str,
                        collateral_amount: int) -> OpResult:
        return self._invoke("PeerLoan", "accept_offer",
                            [val_u64(offer_id)],
                            deposits={collateral_asset:
                                      {"amount": collateral_amount}},
                            max_gas=25_000_000)

    def pl_repay(self, offer_id: int, total_repay: int) -> OpResult:
        return self._invoke("PeerLoan", "repay",
                            [val_u64(offer_id)],
                            deposits={self.xel_asset: {"amount": total_repay}},
                            max_gas=25_000_000)

    def pl_count(self) -> int | None:
        v = self._storage_read("PeerLoan", "oc")
        return int(v) if v is not None else None

    # --- SyndicatePool -------------------------------------------------------

    def sp_create_pool(self, asset_lent: str, total_amount: int,
                       interest_bps: int, duration_blocks: int,
                       collateral_asset: str,
                       collateral_amount: int) -> OpResult:
        return self._invoke("SyndicatePool", "create_pool",
                            [val_hash(asset_lent), val_u64(total_amount),
                             val_u64(interest_bps), val_u64(duration_blocks),
                             val_hash(collateral_asset),
                             val_u64(collateral_amount)],
                            max_gas=25_000_000)

    def sp_supply(self, pool_id: int, amount_atomic: int,
                  asset: str = None) -> OpResult:
        asset = asset or self.xel_asset
        return self._invoke("SyndicatePool", "supply",
                            [val_u64(pool_id), val_u64(amount_atomic)],
                            deposits={asset: {"amount": amount_atomic}},
                            max_gas=20_000_000)

    def sp_activate(self, pool_id: int) -> OpResult:
        return self._invoke("SyndicatePool", "activate_pool",
                            [val_u64(pool_id)], max_gas=25_000_000)

    def sp_repay(self, pool_id: int, amount_atomic: int,
                 asset: str = None) -> OpResult:
        asset = asset or self.xel_asset
        return self._invoke("SyndicatePool", "repay",
                            [val_u64(pool_id), val_u64(amount_atomic)],
                            deposits={asset: {"amount": amount_atomic}},
                            max_gas=25_000_000)

    def sp_claim(self, pool_id: int) -> OpResult:
        return self._invoke("SyndicatePool", "claim",
                            [val_u64(pool_id)], max_gas=20_000_000)

    def sp_count(self) -> int | None:
        v = self._storage_read("SyndicatePool", "pc")
        return int(v) if v is not None else None

    # --- SealedBidAuction ----------------------------------------------------

    def au_create(self, asset: str, amount_atomic: int, bid_asset: str,
                  min_bid: int, cdur: int = MIN_AUCTION_DURATION_BLOCKS,
                  rdur: int = MIN_AUCTION_DURATION_BLOCKS) -> OpResult:
        return self._invoke("SealedBidAuction", "create_auction",
                            [val_hash(asset), val_u64(amount_atomic),
                             val_hash(bid_asset), val_u64(min_bid),
                             val_u64(cdur), val_u64(rdur)],
                            deposits={asset: {"amount": amount_atomic}},
                            max_gas=25_000_000)

    def au_commit(self, auction_id: int, bid_hash: str) -> OpResult:
        return self._invoke("SealedBidAuction", "commit",
                            [val_u64(auction_id), val_hash(bid_hash)],
                            max_gas=15_000_000)

    def au_reveal(self, auction_id: int, amount: int, nonce: int) -> OpResult:
        return self._invoke("SealedBidAuction", "reveal",
                            [val_u64(auction_id), val_u64(amount),
                             val_u64(nonce)],
                            max_gas=25_000_000)

    def au_settle(self, auction_id: int) -> OpResult:
        return self._invoke("SealedBidAuction", "settle",
                            [val_u64(auction_id)], max_gas=15_000_000)

    def au_declare_winner(self, auction_id: int, winner_addr: str,
                          amount: int) -> OpResult:
        return self._invoke("SealedBidAuction", "declare_winner",
                            [val_u64(auction_id), val_addr(winner_addr),
                             val_u64(amount)],
                            max_gas=20_000_000)

    def au_claim_asset(self, auction_id: int) -> OpResult:
        return self._invoke("SealedBidAuction", "claim_asset",
                            [val_u64(auction_id)], max_gas=15_000_000)

    def au_claim_proceeds(self, auction_id: int) -> OpResult:
        return self._invoke("SealedBidAuction", "claim_proceeds",
                            [val_u64(auction_id)], max_gas=15_000_000)

    def au_count(self) -> int | None:
        v = self._storage_read("SealedBidAuction", "ac")
        return int(v) if v is not None else None

    # --- Timelock ------------------------------------------------------------

    def tl_execute(self, proposal_id: int) -> OpResult:
        return self._invoke("Timelock", "execute_proposal",
                            [val_u64(proposal_id)], max_gas=30_000_000)

    def tl_cancel(self, proposal_id: int) -> OpResult:
        return self._invoke("Timelock", "cancel_proposal",
                            [val_u64(proposal_id)], max_gas=15_000_000)

    # --- VaultChat -----------------------------------------------------------

    def chat_register(self, enc_key: str) -> OpResult:
        k = self._hash32(enc_key)
        return self._invoke("VaultChat", "register_session",
                            [val_hash(k)], max_gas=15_000_000)

    @staticmethod
    def _hash32(s: str) -> str:
        """Return a 64-hex (32-byte) hash string for any input key/message."""
        import hashlib
        return hashlib.sha256(s.encode("utf-8")).hexdigest()

    def chat_send_dm(self, to: str, msg_hex: str, ttl: int = 0) -> OpResult:
        return self._invoke("VaultChat", "send_direct_message",
                            [val_addr(to), val_bytes(msg_hex), val_u64(ttl)],
                            max_gas=20_000_000)

    def chat_store_message(self, to: str, msg_hex: str, ttl: int = 0) -> OpResult:
        return self._invoke("VaultChat", "store_message",
                            [val_addr(to), val_bytes(msg_hex), val_u64(ttl)],
                            max_gas=20_000_000)

    def chat_create_group(self, enc_key: str) -> OpResult:
        return self._invoke("VaultChat", "create_group",
                            [val_hash(enc_key)], max_gas=15_000_000)

    def chat_add_member(self, group_id: int, addr: str, enc_key: str) -> OpResult:
        return self._invoke("VaultChat", "add_group_member",
                            [val_u64(group_id), val_addr(addr), val_bytes(enc_key)],
                            max_gas=15_000_000)

    def chat_group_msg(self, group_id: int, msg_hex: str, ttl: int = 0) -> OpResult:
        return self._invoke("VaultChat", "store_group_message",
                            [val_u64(group_id), val_bytes(msg_hex), val_u64(ttl)],
                            max_gas=20_000_000)

    def chat_anchor(self, root: str, count: int, msg_type: int = 0) -> OpResult:
        return self._invoke("VaultChat", "anchor_messages",
                            [val_hash(root), val_u64(count), val_u8(msg_type)],
                            max_gas=20_000_000)

    def chat_stake_bond(self, vlt_atomic: int) -> OpResult:
        return self._invoke("VaultChat", "stake_relayer_bond",
                            [val_u64(vlt_atomic)],
                            deposits={self.vlt_asset: {"amount": vlt_atomic}},
                            max_gas=20_000_000)

    def chat_set_relayer(self, addr: str, enabled: bool = True) -> OpResult:
        return self._invoke("VaultChat", "set_relayer",
                            [val_addr(addr), val_bool(enabled)],
                            max_gas=15_000_000)

    def chat_register_relayer(self, endpoint: str, max_fee: int,
                              max_msgs: int) -> OpResult:
        return self._invoke("VaultChat", "register_as_relayer",
                            [val_str(endpoint), val_u64(max_fee), val_u64(max_msgs)],
                            max_gas=20_000_000)

    def chat_update_endpoint(self, endpoint: str) -> OpResult:
        """Change the relayer's registered public endpoint (chunk 119)."""
        return self._invoke("VaultChat", "update_relayer_endpoint",
                            [val_str(endpoint)], max_gas=15_000_000)

    def chat_set_fee(self, token: int, fee: int) -> OpResult:
        return self._invoke("VaultChat", "set_relayer_fee",
                            [val_u64(fee), val_u8(token)],
                            max_gas=15_000_000)

    def chat_claim_fees(self) -> OpResult:
        return self._invoke("VaultChat", "claim_relayer_fees",
                            [], max_gas=20_000_000)

    def chat_groups_count(self) -> int | None:
        v = self._storage_read("VaultChat", "gc")
        return int(v) if v is not None else None

    def chat_inbox(self, addr: str = "") -> list:
        """Read my on-chain direct (+relayed) inbox from storage.
        Returns list of dicts {kind:'direct'|'relayed', sender, ts, blob}."""
        addr = addr or self.address
        if not addr:
            return []
        chat = self.C("VaultChat")
        if not chat:
            return []
        out = []
        dc = self.daemon.read_key(chat, f"dmsgc_{addr}")
        n_dm = int(dc) if isinstance(dc, int) else 0
        for i in range(min(n_dm, 50)):
            raw = self.daemon.read_key(chat, f"dmsg_{addr}_{i}")
            if not raw:
                continue
            parts = str(raw).split("|")
            out.append({"kind": "direct", "blob": parts[0],
                        "sender": parts[1] if len(parts) > 1 else "",
                        "ts": parts[2] if len(parts) > 2 else "",
                        "slot": i})
        mc = self.daemon.read_key(chat, f"msgc_{addr}")
        n_m = int(mc) if isinstance(mc, int) else 0
        for i in range(min(n_m, 50)):
            raw = self.daemon.read_key(chat, f"msg_{addr}_{i}")
            if not raw:
                continue
            parts = str(raw).split("|")
            out.append({"kind": "relayed", "blob": parts[0],
                        "sender": parts[1] if len(parts) > 1 else "",
                        "ts": parts[2] if len(parts) > 2 else "",
                        "slot": i})
        return out

    @staticmethod
    def chat_decode(msg: str) -> str:
        """Best-effort decode of a message the user typed (hex or plain)."""
        s = msg.strip()
        try:
            if all(c in "0123456789abcdefABCDEF" for c in s) and len(s) % 2 == 0:
                return bytes.fromhex(s).decode("utf-8", "replace")
        except Exception:
            pass
        return s

    @staticmethod
    def chat_encode(msg: str) -> str:
        """Encode a user plaintext message into hex for on-chain storage."""
        try:
            _ = bytes.fromhex(msg.strip())  # already hex?
            if all(c in "0123456789abcdef" for c in msg.strip()):
                return msg.strip()
        except Exception:
            pass
        return msg.encode("utf-8").hex()

    # --- Funding helpers (deposit XEL to any contract) ----------------------

    def fund_contract(self, contract_key: str, asset: str,
                      amount_atomic: int, params: list = None) -> OpResult:
        """Deposit assets to any contract by invoking its deposit entry."""
        deposit_chunk = CHUNKS.get(contract_key, {}).get("deposit")
        if deposit_chunk is None:
            return OpResult(False, reason=f"{contract_key} has no deposit entry")
        p = params if params is not None else [val_hash(asset), val_u64(amount_atomic)]
        return self._invoke(contract_key, "deposit", p,
                            deposits={asset: {"amount": amount_atomic}},
                            max_gas=10_000_000)

    def fund_any(self, contract_key: str, entry_fn: str,
                 params: list, asset: str, amount_atomic: int) -> OpResult:
        """Deposit assets to any contract via any entry (entry persists deposits at tx level)."""
        return self._invoke(contract_key, entry_fn, params,
                            deposits={asset: {"amount": amount_atomic}},
                            max_gas=10_000_000)

    # --- RWA (admin asset registration) --------------------------------------

    def rwa_register(self, name: str, symbol: str,
                     decimals: int, supply: int) -> OpResult:
        return self._invoke("AssetVault", "create_asset",
                            [val_str(name), val_str(symbol),
                             val_u8(decimals), val_u64(supply)],
                            max_gas=20_000_000)

    # --- AirdropTracker (points / leaderboard / qualification) --------------

    def airdrop_record_mainnet(self, mainnet_addr: str) -> OpResult:
        """Submit the user's mainnet address to finalize airdrop eligibility."""
        return self._invoke("AirdropTracker", "record_mainnet_address",
                            [val_addr(mainnet_addr)], max_gas=5_000_000)

    def _air_read(self, key: str):
        return self._storage_read("AirdropTracker", key)

    def _air_int(self, key: str, default: int = 0) -> int:
        v = self._air_read(key)
        return int(v) if isinstance(v, int) else default

    def airdrop_user_points(self, addr: str = "") -> Optional[dict]:
        """Full UserPoints snapshot for an address."""
        addr = addr or self.address
        raw = self._air_read(_AIR_USER_PREFIX + addr)
        if not (isinstance(raw, list) and len(raw) >= 15):
            return None
        return {
            "mining": int(raw[0]), "relayer": int(raw[1]),
            "governance": int(raw[2]), "chat": int(raw[3]),
            "liquidity": int(raw[4]), "bounty": int(raw[5]),
            "community": int(raw[6]),
            "total_raw": int(raw[7]), "total_with_bonus": int(raw[8]),
            "days_active": int(raw[9]), "last_active_day": int(raw[10]),
            "mainnet_address": str(raw[11]),
            "qualified": bool(raw[12]), "registered": bool(raw[13]),
        }

    def airdrop_snapshot(self) -> dict:
        """Global snapshot: user_count, total_points, qualified, finalized."""
        return {
            "user_count": self._air_int("uc"),
            "total_points": self._air_int("tp"),
            "qualified_count": self._air_int("qc"),
            "leaderboard_count": self._air_int("lbc"),
            "frozen": bool(self._air_read("fz")),
            "finalized": bool(self._air_read("fn")),
            "start_topo": self._air_int("stt"),
            "freeze_topo": self._air_int("fzt"),
            "finalize_topo": self._air_int("flt"),
            "manual_cap": self._air_int("mcap"),
            "merkle_root": str(self._air_read("mr") or "")[:24],
        }

    def airdrop_category_totals(self) -> dict:
        out = {}
        for cat, name in AIRDROP_CATEGORIES.items():
            v = self._air_read(_AIR_CAT_PREFIX + str(cat))
            out[name] = int(v) if isinstance(v, int) else 0
        return out

    def airdrop_leaderboard(self, limit: int = 15) -> list:
        """Top-N users pre-finalize. Reads the user list + points from storage
        and sorts locally (the chain's O(n^2) rank getter is avoided)."""
        count = self._air_int("uc")
        rows = []
        for i in range(min(count, 400)):
            addr_raw = self._air_read(_AIR_LIST_PREFIX + str(i))
            if not isinstance(addr_raw, str):
                continue
            up = self._air_read(_AIR_USER_PREFIX + addr_raw)
            if isinstance(up, list) and len(up) >= 9:
                rows.append({
                    "addr": addr_raw, "points": int(up[7]),
                    "qualified": bool(up[12]) if len(up) > 12 else False,
                    "mainnet": str(up[11]),
                    "with_bonus": int(up[8]),
                })
        rows.sort(key=lambda r: r["points"], reverse=True)
        return rows[:limit]

    def airdrop_rank(self, addr: str = "", limit_up: int = 400) -> tuple:
        """Return (rank, total_users) for an address (1-based; 0 if unknown)."""
        addr = addr or self.address
        up = self.airdrop_user_points(addr)
        if not up:
            return 0, self._air_int("uc")
        my_points = up["total_raw"]
        count = self._air_int("uc")
        higher = 0
        for i in range(min(count, limit_up)):
            addr2 = self._air_read(_AIR_LIST_PREFIX + str(i))
            if not isinstance(addr2, str) or addr2 == addr:
                continue
            o = self._air_read(_AIR_USER_PREFIX + addr2)
            if isinstance(o, list) and len(o) >= 8 and int(o[7]) > my_points:
                higher += 1
        return higher + 1, count

    # --- VaultChat relayer --------------------

    def chat_relayer_status(self, addr: str = "") -> dict:
        """Read a relayer's on-chain profile from VaultChat storage."""
        addr = addr or self.address
        vc = self.C("VaultChat")
        if not vc or not self.daemon:
            return {}
        def r(key):
            try:
                return self.daemon.read_key(vc, key)
            except Exception:
                return None
        active = r("relayer_" + addr)
        bond = r("rbond_" + addr)
        fee = r("rfee_" + addr)
        token = r("rtok_" + addr)
        reg = r("rlreg_" + addr)
        out = {
            "active": (active is True) or (isinstance(active, list) and bool(active)),
            "bond": int(bond) if isinstance(bond, int) else (int(bond[0]) if isinstance(bond, list) and bond else 0),
            "fee": int(fee) if isinstance(fee, int) else (int(fee[0]) if isinstance(fee, list) and fee else 1000000),
            "token": int(token) if isinstance(token, int) else (int(token[0]) if isinstance(token, list) and token else 0),
            "registered": None,
        }
        # rlreg_<addr> is "endpoint|free_daily_limit|free_wallet_slots" (string)
        if isinstance(reg, str) and "|" in reg:
            parts = reg.split("|")
            out["registered"] = {
                "endpoint": parts[0],
                "free_daily_limit": parts[1] if len(parts) > 1 else "",
                "free_wallet_slots": parts[2] if len(parts) > 2 else "",
            }
        return out

    def chat_relayers_list(self) -> list:
        """Enumerate all registered relayers on-chain.

        The contract keeps a registry: rlregc = count, rlreg_idx_<i> = the
        relayer's address, rlreg_<addr> = "endpoint|free_daily_limit|free_wallet_slots".
        Returns a list of dicts, newest first.
        """
        vc = self.C("VaultChat")
        if not vc or not self.daemon:
            return []
        def r(key):
            try:
                return self.daemon.read_key(vc, key)
            except Exception:
                return None
        count = int(r("rlregc")) if isinstance(r("rlregc"), int) else 0
        out = []
        for i in range(count):
            addr = r(f"rlreg_idx_{i}")
            if not addr or not isinstance(addr, str):
                continue
            reg = r("rlreg_" + addr)
            details = {"addr": addr, "endpoint": "", "free_daily_limit": 0,
                       "free_wallet_slots": 0,
                       "bond": 0, "fee": 0, "token": 0}
            if isinstance(reg, str) and "|" in reg:
                p = reg.split("|")
                details["endpoint"] = p[0]
                details["free_daily_limit"] = int(p[1]) if p[1].isdigit() else p[1]
                details["free_wallet_slots"] = int(p[2]) if len(p) > 2 and p[2].isdigit() else (p[2] if len(p) > 2 else 0)
            bnd = r("rbond_" + addr)
            fee = r("rfee_" + addr)
            tok = r("rtok_" + addr)
            details["bond"] = int(bnd) if isinstance(bnd, int) else (int(bnd[0]) if isinstance(bnd, list) and bnd else 0)
            details["fee"] = int(fee) if isinstance(fee, int) else (int(fee[0]) if isinstance(fee, list) and fee else 0)
            details["token"] = int(tok) if isinstance(tok, int) else (int(tok[0]) if isinstance(tok, list) and tok else 0)
            out.append(details)
        # newest first (registry is append-only, last index = newest)
        out.reverse()
        return out

    def _air_read_relay(self, vc: str, key: str):
        try:
            return self.daemon.read_key(vc, key)
        except Exception:
            return None

    # --- MinerDelegation ------------------------------------------------------

    def delegation_register_profile(self, name: str, description: str,
                                    commission_bps: int) -> OpResult:
        """Register/update miner profile for delegation."""
        return self._invoke("MinerDelegation", "register_miner_profile",
                            [val_str(name), val_str(description), val_u64(commission_bps)],
                            max_gas=10_000_000)

    def delegation_delegate(self, miner_addr: str, amount_vlt: int,
                            auto_compound: bool = False) -> OpResult:
        """Delegate VLT to a miner."""
        return self._invoke("MinerDelegation", "delegate",
                            [val_addr(miner_addr), val_u64(amount_vlt),
                             val_bool(auto_compound)],
                            deposits={self.vlt_asset: {"amount": amount_vlt}},
                            max_gas=15_000_000)

    def delegation_undelegate(self, amount_vlt: int) -> OpResult:
        """Queue undelegation of VLT from current miner."""
        return self._invoke("MinerDelegation", "undelegate",
                            [val_u64(amount_vlt)],
                            max_gas=10_000_000)

    def delegation_execute_undelegate(self) -> OpResult:
        """Execute pending undelegation after delay."""
        return self._invoke("MinerDelegation", "execute_undelegate",
                            [], max_gas=10_000_000)

    def delegation_get_profile(self, miner_addr: str) -> dict | None:
        """Get miner's delegation profile: (name, description, commission_bps)."""
        md = self.C("MinerDelegation")
        if not md or not self.daemon:
            return None
        try:
            raw = self.daemon.read_key(md, f"mp_{miner_addr}")
            if isinstance(raw, list) and len(raw) >= 3:
                return {
                    "name": str(raw[0]),
                    "description": str(raw[1]),
                    "commission_bps": int(raw[2]),
                }
        except Exception:
            pass
        return None

    def delegation_my_delegation(self) -> dict | None:
        """Get my current delegation info."""
        md = self.C("MinerDelegation")
        if not md or not self.daemon or not self.address:
            return None
        try:
            raw = self.daemon.read_key(md, f"del_{self.address}")
            if isinstance(raw, list) and len(raw) >= 5:
                return {
                    "miner": str(raw[0]),
                    "amount": int(raw[1]),
                    "index": int(raw[2]),
                    "delegated_at": int(raw[3]),
                    "auto_compound": bool(raw[4]) if len(raw) > 4 else False,
                }
        except Exception:
            pass
        return None

    def delegation_miner_stake(self, miner_addr: str) -> int:
        """Get total stake of a miner (own + delegated)."""
        md = self.C("MinerDelegation")
        if not md or not self.daemon:
            return 0
        try:
            raw = self.daemon.read_key(md, f"mp_{miner_addr}")
            if isinstance(raw, list) and len(raw) >= 7:
                return int(raw[6])
        except Exception:
            pass
        return 0

    def delegation_update_profile(self, name: str, description: str,
                                  commission_bps: int) -> OpResult:
        """Update miner profile for delegation."""
        return self._invoke("MinerDelegation", "update_miner_profile",
                            [val_str(name), val_str(description), val_u64(commission_bps)],
                            max_gas=10_000_000)

    def delegation_claim_delegator_rewards(self) -> OpResult:
        """Claim delegator rewards."""
        return self._invoke("MinerDelegation", "claim_delegator_rewards",
                            [], max_gas=10_000_000)

    def delegation_claim_miner_rewards(self) -> OpResult:
        """Claim miner rewards (own + commission)."""
        return self._invoke("MinerDelegation", "claim_miner_rewards",
                            [], max_gas=10_000_000)

    def delegation_total_delegated(self) -> int:
        """Total delegated VLT across all miners."""
        md = self.C("MinerDelegation")
        if not md or not self.daemon:
            return 0
        try:
            raw = self.daemon.read_key(md, "td")
            return int(raw) if isinstance(raw, int) else 0
        except Exception:
            return 0

    def delegation_miner_count(self) -> int:
        """Number of registered miners."""
        md = self.C("MinerDelegation")
        if not md or not self.daemon:
            return 0
        try:
            raw = self.daemon.read_key(md, "mc")
            return int(raw) if isinstance(raw, int) else 0
        except Exception:
            return 0

    def delegation_miner_pending(self, miner_addr: str) -> int:
        """Pending rewards for a miner."""
        md = self.C("MinerDelegation")
        if not md or not self.daemon:
            return 0
        try:
            raw = self.daemon.read_key(md, f"mpr_{miner_addr}")
            return int(raw) if isinstance(raw, int) else 0
        except Exception:
            return 0

    def delegation_delegator_pending(self, delegator_addr: str) -> int:
        """Pending rewards for a delegator (computed from index + extra)."""
        md = self.C("MinerDelegation")
        if not md or not self.daemon or not delegator_addr:
            return 0
        try:
            del_raw = self.daemon.read_key(md, f"del_{delegator_addr}")
            if not isinstance(del_raw, list) or len(del_raw) < 5:
                return 0
            miner_addr = str(del_raw[0])
            amount = int(del_raw[1])
            index_snapshot = int(del_raw[2])
            profile_raw = self.daemon.read_key(md, f"mp_{miner_addr}")
            if not isinstance(profile_raw, list) or len(profile_raw) < 8:
                return 0
            reward_index = int(profile_raw[7])
            index_diff = reward_index - index_snapshot
            if index_diff <= 0:
                return 0
            pending = (amount * index_diff) // 10**18
            extra_raw = self.daemon.read_key(md, f"dpr_{delegator_addr}")
            extra = int(extra_raw) if isinstance(extra_raw, int) else 0
            return pending + extra
        except Exception:
            return 0

    # --- Generic int reader --------------------------------------------------

    def _storage_read(self, contract_key: str, key_str: str):
        """Read a string-keyed storage cell from a contract."""
        contract = self.C(contract_key)
        if not contract or not self.daemon:
            return None
        try:
            return self.daemon.read_key(contract, key_str)
        except Exception:
            return None

    def _my_addr(self) -> str:
        return self.address
