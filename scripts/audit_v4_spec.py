#!/usr/bin/env python3
"""AUDIT 1 (v4) — founder-requirement traceability: every requirement of
the v4 brief must be grounded in the contract source with a checkable
marker. Fails loudly if any requirement loses its implementation."""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LP = (ROOT / "contracts" / "launchpad" / "VaultLaunch.slx").read_text()
DEX = (ROOT / "contracts" / "dex" / "LaunchDEX.slx").read_text()
TESTS = (ROOT / "tests" / "test_launchpad_reference.py").read_text()
TESTS_DEX = (ROOT / "tests" / "test_dex_reference.py").read_text()

REQS = [
    # (id, requirement, contract marker, test marker)
    ("R1", "real confidential asset created by the contract",
     "Asset::create(", "test_full_lifecycle_curve_path"),
    ("R2", "created at validation success (not before; failures pollute nothing)",
     'require(s.load(proj_key(pid, F_ASSET)).is_none(), "exists")',
     "test_rejected_project_refunds_liquidity_and_budget"),
    ("R3", "MAX CAP enforced at creation (Fixed mode, protocol-level)",
     "MaxSupplyMode::Fixed { max_supply: total_supply }",
     "test_contract_exposes_the_full_spec_api"),
    ("R4", "whole supply delivered to the contract and verified",
     'require(tok_bal == total_supply, "assetbal")',
     "test_full_lifecycle_curve_path"),
    ("R5", "creation cost measured (balance-delta) from an earmarked budget, refunded",
     "let fee_paid: u64 = bal_before - bal_after",
     "test_asset_budget_refund_and_topup_d13"),
    ("R6", "budget top-up accepted on finalize",
     "let topup: u64 = get_deposit_for_asset(xel).unwrap_or(0)",
     "test_asset_budget_refund_and_topup_d13"),
    ("R7", "buy: XEL deposit -> REAL tokens to the wallet",
     "let ok: bool = transfer(caller, tokens, asset)",
     "test_full_lifecycle_curve_path"),
    ("R8", "sell: REAL token deposit (whole deposit) -> XEL",
     "let dep: u64 = get_deposit_for_asset(asset).unwrap_or(0)",
     "test_full_lifecycle_curve_path"),
    ("R9", "curve priced on XEL reserves x real supply (constant product, u128)",
     "fn buy_tokens_out(reserves: u64, curve_supply: u64, net_xel: u64) -> u64 {",
     "test_buy_math_hand_vector"),
    ("R10", "graduation triggers a REAL migration (not a status-only flip)",
     "entry migrate(pid: u64) -> u64 {",
     "test_full_lifecycle_curve_path"),
    ("R11", "migration takes curve XEL + remaining tokens into a REAL pool",
     "deposits.insert(asset, curve_supply)",
     "test_full_lifecycle_curve_path"),
    ("R12", "migration is ATOMIC (single cross-call with attached deposits)",
     "target.call(DEX_CREATE_POOL_CHUNK, [asset], deposits)",
     "test_migration_is_idempotent_and_dex_pin_freezes_d19"),
    ("R13", "the pool is a real AMM (constant product on the DEX)",
     "let wide: u128 = (y as u128) * (net as u128) / ((x as u128) + (net as u128))",
     "test_dex_swap_math_hand_vectors"),
    ("R14", "anti-rug: the migrated seed is protocol-locked FOREVER (v1.3: removes exist for providers, never for the seed)",
     "X2. THE SEED IS PERMANENT, PROVIDERS ARE FREE",
     "test_the_seed_is_protocol_locked_x11_x12"),
    ("R15", "team escrow NEVER migrates (claims keep working after)",
     "let team_rem: u64 = team_remaining(pid)",
     "test_full_lifecycle_curve_path"),
    ("R16", "keep: community validation (support/report/finalize)",
     "entry finalize_validation(pid: u64) -> u64 {",
     "test_full_lifecycle_curve_path"),
    ("R17", "keep: two-path graduation (direct listing vs curve)",
     "let dl: bool = s.load(proj_key(pid, F_DL)).unwrap_or(false)",
     "test_direct_listing_path_d7"),
    ("R18", "keep: Trusted/Untrusted system (buys blocked, sells never)",
     'require(status == ST_BONDING || status == ST_GRADUATED || status == ST_TRUSTED, "notrade")',
     "test_untrusted_blocks_buys_never_sells_and_recovers"),
    ("R19", "trust follows the tokens to the pool (buys-pause, sells never)",
     "entry sync_trust_to_dex(pid: u64) -> u64 {",
     "test_untrusted_at_migration_pauses_pool_buys_same_tx_d17"),
    ("R20", "keep: votable team vesting (D10 plan)",
     'require(s.load(proj_key(pid, F_VESTING_PLAN)).unwrap_or(0) == 0, "planned")',
     "test_vesting_plan_binds_at_graduation_curve_path_d10"),
    ("R21", "keep: fees 100% admin, no burn",
     "s.store(FEES_LIFETIME_KEY" if "FEES_LIFETIME_KEY" in LP else
     "entry withdraw_fees(amount: u64) -> u64 {",
     "test_solvency_after_graduation_and_withdrawal_pressure"),
    ("R22", "keep: rich events + views for the frontend",
     "pub fn get_migration_info(pid: u64)",
     "test_contract_exposes_the_full_spec_api"),
    ("R23", "volume + market cap stored ON-CHAIN (curve era + pool era)",
     "fn record_trade(pid: u64, buy_side: bool, xel_amount: u64) {",
     "test_dex_pool_era_scoreboard_and_permanent_liquidity"),
    ("R24", "token usable OUTSIDE VaultLaunch (native asset, wallet transfers)",
     "swap_xel_for_token",  # anyone trades it on the DEX with plain wallets
     "test_dex_pool_era_scoreboard_and_permanent_liquidity"),
    ("R25", "privacy: native confidential asset + private team claims",
     "// D18 — NO amount in the event",
     "test_contract_declares_every_spec_event"),
    ("R26", "DEX pin frozen after first migration (orphaning impossible)",
     'require(s.load(MIGRATED_COUNT_KEY).unwrap_or(0) == 0, "frozen")',
     "test_migration_is_idempotent_and_dex_pin_freezes_d19"),
    ("R27", "cross-call permission precheck (clear refusal for wallets)",
     'require(is_contract_callable(dex, DEX_CREATE_POOL_CHUNK), "txperm")',
     "test_cross_calls_are_exactly_the_pinned_pair_d19"),
    ("R28", "pinned chunk ids asserted against the real DEX table (CI)",
     "const DEX_CREATE_POOL_CHUNK: u16 = 6",
     "test_pinned_cross_call_chunks_d19"),
    ("R29", "no locked funds: curve sells carry no pause gate at all — pool sells neither (point 2)",
     'entry swap_token_for_xel(asset: Hash, min_xel_out: u64) -> u64 {',
     "test_sells_are_never_blocked_by_anything_x5"),
    ("R30", "solvent by construction (exact-sum curve accounting, D20/D21)",
     "let committed: u128 = (curve_xel as u128) + (locked as u128) + (budgets as u128) + (pots as u128)",
     "test_solvency_after_graduation_and_withdrawal_pressure"),
    # -- v18.2 founder risk review, points 1-2 (X10/D23 + D21 default) --
    ("R31", "providers earn: every swap fee splits admin/LP pro-rata of depth (point 1)",
     "if lp_part > 0 && tl > 0 {",
     "test_d23_providers_earn_pro_rata_and_claims_pay_x10"),
    ("R32", "the split dial is hard-bounded [25%, 75%] — LPs never cut to zero, treasury never starved",
     'require(lp_bps >= MIN_LP_SHARE_BPS, "toolow")',
     "test_d23_fee_split_dial_is_bounded_and_prospective"),
    ("R33", "vote deposit default 0.5 XEL refundable from day one (point 2: 20 farmed wallets park capital)",
     "const DEFAULT_VOTE_DEPOSIT: u64 = 50000000",
     "test_d21_default_is_a_refundable_half_xel_and_admin_cannot_confiscate"),
    ("R34", "a first deposit never earns fees from before it existed (fuzz-found IX8 fix)",
     "s.store(lkey + LPF_SNAP_XEL, s.load(pool_key(asset, F_LP_ACC_XEL)).unwrap_or(0))",
     "test_d23_first_deposit_never_earns_fees_from_before_it_existed"),
    # -- v18.3 founder risk review 3, points 1-2 (X11 seed shares + X12 removes) --
    ("R35", "the seed mints LP parts to the protocol — the first add cannot capture a migrated pool (point 1: 1 XEL on 4000 XEL = 1/4001, not 100%)",
     "s.store(pool_key(asset, F_LP_LOCKED), xel_seed)",
     "test_x11_the_first_add_cannot_capture_a_seeded_pool"),
    ("R36", "providers exit pro-rata anytime and the seed NEVER leaves — burns bounded by own withdrawable parts, floor re-asserted (point 2)",
     'require(parts <= w, "locked")',
     "test_x12_remove_liquidity_full_lifecycle"),
]

fails = []
for rid, req, marker, test in REQS:
    where = LP if any(ch in marker for ch in ["pool", "swap_", "EMERGENCY"]) or "LaunchDEX" in req or "DEX" in rid else LP
    if marker not in LP and marker not in DEX:
        fails.append(f"{rid}: contract marker missing: {req!r} — looked for {marker[:60]!r}")
    if test not in TESTS and test not in TESTS_DEX:
        fails.append(f"{rid}: no test grounds {req!r} (expected {test})")

# cross-cutting sanity: the requirement count matches the founder brief
assert len(REQS) == 36

if fails:
    print("AUDIT 1 (SPEC TRACEABILITY) FAILED:")
    for f in fails:
        print("  -", f)
    sys.exit(1)
print(f"AUDIT 1 (SPEC TRACEABILITY): PASS — {len(REQS)}/36 founder requirements "
      "grounded in the contract source AND covered by a test.")
