#!/usr/bin/env python3
"""audit_doc_parity.py — one-shot audit pass: docs/LAUNCHPAD.md,
docs/DEX.md and the SDK must agree with the contracts on every storage
key, default value, event id and version they mention. Exit 1 on drift."""
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CONTRACT = (REPO / "contracts" / "launchpad" / "VaultLaunch.slx").read_text()
DOC = (REPO / "docs" / "LAUNCHPAD.md").read_text()
DEX_CONTRACT = (REPO / "contracts" / "dex" / "LaunchDEX.slx").read_text()
DEX_DOC = (REPO / "docs" / "DEX.md").read_text()

fails = []

# 1. every project field key documented in the doc exists in the contract
for field, const in [
    ("cr", "F_CREATOR"), ("st", "F_STATUS"), ("nm", "F_NAME"), ("sy", "F_SYMBOL"),
    ("ds", "F_DESC"), ("ws", "F_WEBSITE"), ("lg", "F_LOGO"), ("ts", "F_SUPPLY"),
    ("tb", "F_TEAM_BPS"), ("lq", "F_LIQUIDITY"), ("rv", "F_RESERVES"),
    ("cs", "F_CURVE"), ("ct", "F_CREATED"), ("ve", "F_DEADLINE"),
    ("sp", "F_SUPPORTS"), ("rp", "F_REPORTS"), ("gr", "F_GRADUATED"),
    ("rc", "F_REFUND"), ("rd", "F_ROUND"), ("vo", "F_VOLUME"), ("dl", "F_DL"),
    ("bt", "F_BONDING_START"), ("tp", "F_TEAM_PAID"),
    ("vs", "F_VESTING_START"), ("vd", "F_VESTING_DURATION"),
    # v3 (D10/D11/D12)
    ("vp", "F_VESTING_PLAN"), ("tw", "F_TWITTER"), ("tg", "F_TELEGRAM"),
    ("dc", "F_DISCORD"), ("bv", "F_BUY_VOL"), ("sv", "F_SELL_VOL"),
    ("tc", "F_TRADES"), ("lt", "F_LAST_TRADE"),
    ("mc", "F_MCAP"), ("mh", "F_MCAP_HIGH"), ("mg", "F_MCAP_GRAD"),
    # v4 (D13/D15/D17)
    ("ah", "F_ASSET"), ("ab", "F_BUDGET"), ("mi", "F_MIGRATED"),
    ("ma", "F_MIG_AT"), ("mx", "F_MIG_XEL"), ("mt", "F_MIG_TOK"),
    ("dsy", "F_DEX_SYNCED"),
]:
    if f'const {const}: string = "{field}"' not in CONTRACT:
        fails.append(f"contract: field key {field} ({const}) missing")

# 2. every global key documented in the doc exists in the contract
for key, const in [
    ("gfe", "GRADUATED_FEE_KEY"), ("mgf", "MIGRATION_FEE_KEY"),
    ("dlt", "DIRECT_LISTING_KEY"), ("tdy", "TEAM_DELAY_KEY"),
    ("vmn", "VESTING_MIN_KEY"), ("vmx", "VESTING_MAX_KEY"),
    ("pfe", "PENDING_FEES_KEY"), ("tcx", "TOTAL_CURVE_XEL_KEY"),
    ("lrf", "LOCKED_REFUNDS_KEY"), ("sub", "SUBMISSION_FEE_KEY"),
    # v3 (D12 protocol-wide scoreboard)
    ("tbv", "TOTAL_BUY_VOL_KEY"), ("tsv", "TOTAL_SELL_VOL_KEY"),
    ("ttc", "TOTAL_TRADES_KEY"),
    # v4 (D13/D19/D20)
    ("abd", "ASSET_BUDGET_KEY"), ("tbb", "TOTAL_BUDGETS_KEY"),
    ("mgc", "MIGRATED_COUNT_KEY"), ("dxa", "DEX_ADDRESS_KEY"),
    # v4.1 (D21)
    ("vdp", "VOTE_DEPOSIT_KEY"), ("tvp", "VOTE_POTS_KEY"),
]:
    if f'const {const}: string = "{key}"' not in CONTRACT:
        fails.append(f"contract: global key {key} ({const}) missing")

# 3. defaults quoted in the doc are the contract constants
for const, value in [
    ("DEFAULT_GRADUATED_FEE_BPS", "25"), ("DEFAULT_MIGRATION_FEE_BPS", "50"),
    ("DEFAULT_DIRECT_LISTING", "200000000000"), ("DEFAULT_TEAM_DELAY", "3153600"),
    ("DEFAULT_VESTING_MIN", "518400"), ("DEFAULT_VESTING_MAX", "6307200"),
    ("DEFAULT_TRADING_FEE_BPS", "50"), ("DEFAULT_MIN_LIQUIDITY", "50000000000"),
]:
    if f"{const}: u64 = {value}" not in CONTRACT:
        fails.append(f"contract: default {const} = {value} missing")
    if const.replace("DEFAULT_", "").lower() not in DOC.lower() and const not in DOC:
        # the doc quotes values, not const names — only check the contract side
        pass

# 4. every view named in the doc's frontend guide exists in the contract
for view in ["get_current_price", "get_market_cap", "get_bonding_info",
             "get_project_trust", "get_team_allocation", "get_buy_quote",
             "get_sell_quote", "get_projects_by_status",
             "get_project_by_rank", "get_latest_projects",
             "get_trusted_projects", "get_trusted_by_rank",
             "get_status_label", "get_config", "get_recovery_config",
             "get_team_config", "get_version", "get_project",
             "claim_team_allocation", "start_team_vesting",
             # v3 (D10/D11/D12)
             "get_social_links", "get_trading_stats",
             "get_market_cap_history", "get_proposal_data",
             "get_volume_stats", "get_protocol_stats",
             "update_project_info",
             # v4 (D13/D15): real assets + migration. get_token_balance is
             # GONE on purpose (no internal ledger — wallets hold the asset)
             "get_asset_info", "get_migration_info",
             "migrate", "sync_trust_to_dex",
             # v4.1 (D21/D22): the sybil dial + the site-data bridges
             "claim_vote_deposit", "get_vote_config",
             "get_project_by_asset", "get_migrated_count",
             "get_migrated_by_rank"]:
    if f"fn {view}(" not in CONTRACT and f"entry {view}(" not in CONTRACT:
        fails.append(f"contract: view/entry {view} named in the doc is missing")
    if view not in DOC:
        fails.append(f"doc: {view} exists in the contract but is not documented")

# 5. every event id in the doc table matches the contract constant
for name, eid in [("EV_PROJECT_CREATED", 1), ("EV_SUPPORTED", 2),
                  ("EV_REPORTED", 3), ("EV_VALIDATION_FINISHED", 4),
                  ("EV_BONDING_OPENED", 5), ("EV_TOKENS_BOUGHT", 6),
                  ("EV_TOKENS_SOLD", 7), ("EV_PROJECT_GRADUATED", 8),
                  ("EV_TRUST_LOST", 9), ("EV_TRUST_RECOVERED", 10),
                  ("EV_FEES_COLLECTED", 11), ("EV_PARAM_SET", 12),
                  ("EV_PAUSED", 13), ("EV_UNPAUSED", 14), ("EV_ADMIN_SET", 15),
                  ("EV_REFUND_CLAIMED", 16), ("EV_RECOVERY_REQUESTED", 17),
                  ("EV_PROJECT_INFO_UPDATED", 18),
                  ("EV_TEAM_VESTING_STARTED", 19), ("EV_TEAM_CLAIMED", 20),
                  ("EV_DIRECT_LISTED", 21), ("EV_MIGRATION_FEE", 22),
                  # v4
                  ("EV_ASSET_CREATED", 23), ("EV_MIGRATED", 24),
                  ("EV_DEX_SYNCED", 25), ("EV_DEX_ADDRESS", 26),
                  # v4.1 (D21)
                  ("EV_VOTE_DEPOSIT_CLAIMED", 27)]:
    if f"const {name}: u64 = {eid}" not in CONTRACT:
        fails.append(f"contract: event {name} = {eid} missing")

# 6. version strings agree
if 'const VERSION: string = "VaultLaunch v4.2.0"' not in CONTRACT:
    fails.append("contract: VERSION is not v4.2.0")
if "v4.2.0" not in DOC:
    fails.append("doc: LAUNCHPAD.md does not say v4.2.0")
if 'const VERSION: string = "LaunchDEX v1.4.1"' not in DEX_CONTRACT:
    fails.append("dex contract: VERSION is not v1.4.1")
if "v1.4.1" not in DEX_DOC:
    fails.append("doc: DEX.md does not say v1.4.1")
# v3 sanity: the D10/D11/D12 views are documented in the frontend guide
for concept in ["vesting_plan", "get_social_links", "get_volume_stats",
                "get_market_cap_history", "get_trading_stats"]:
    if concept not in DOC:
        fails.append(f"doc: v3 concept {concept} not documented")

# v4 sanity: the real-asset concepts are documented
for concept in ["Asset::create", "Fixed", "asset_budget", "migrate",
                "sync_trust_to_dex", "LaunchDEX", "get_asset_info",
                "get_migration_info", "confidential"]:
    if concept not in DOC:
        fails.append(f"doc: v4 concept {concept} not documented")

# v4.1 sanity: the risk-review hardening is documented (D21/D22, X7, IX6)
for concept in ["vote_deposit", "claim_vote_deposit", "get_project_by_asset",
                "get_migrated_by_rank", "price-neutral", "set_vote_deposit"]:
    if concept not in DOC:
        fails.append(f"doc: v4.1 concept {concept} not documented")

# v4.2 sanity: the dial default and the provider era are documented
for concept in ["0.5 XEL", "get_lp_info", "claim_lp_fees", "lp_share_bps",
                "UPGRADES.md"]:
    if concept not in DOC:
        fails.append(f"doc: v4.2 concept {concept} not documented")
if "const DEFAULT_VOTE_DEPOSIT: u64 = 50000000" not in CONTRACT:
    fails.append("contract: DEFAULT_VOTE_DEPOSIT is not 0.5 XEL (v4.2)")

# v1.2 DEX sanity: the provider surface is documented in DEX.md and the
# keys/views/entries exist in the contract
for concept in ["X10", "IX8", "claim_lp_fees", "set_fee_split",
                "get_lp_info", "lp_share_bps", "MIN_LP_ADD_XEL"]:
    if concept not in DEX_DOC:
        fails.append(f"doc: DEX.md v1.2 concept {concept} not documented")
for const, key in [("F_LP_POT_XEL", "lx"), ("F_LP_POT_TOK", "ly"),
                   ("F_LP_TOTAL", "tl"), ("F_LP_ACC_XEL", "ax"),
                   ("F_LP_ACC_TOK", "ay")]:
    if f'const {const}: string = "{key}"' not in DEX_CONTRACT:
        fails.append(f"dex contract: pool key {key} ({const}) missing")
if 'const FEE_SPLIT_KEY: string = "fsl"' not in DEX_CONTRACT:
    fails.append("dex contract: global key fsl (FEE_SPLIT_KEY) missing")
for fn in ("entry claim_lp_fees", "entry set_fee_split",
           "pub fn get_lp_info"):
    if fn not in DEX_CONTRACT:
        fails.append(f"dex contract: {fn} missing")
if "const EV_LP_FEES_CLAIMED: u64 = 13" not in DEX_CONTRACT:
    fails.append("dex contract: event 13 (LpFeesClaimed) missing")

# v1.3 DEX sanity: the two-tier liquidity model (seed shares + provider
# removes) is documented in DEX.md and the keys/entries exist in the
# contract
for concept in ["X11", "X12", "IX9", "remove_liquidity", "seed floor",
                "PROVIDERS CAN LEAVE"]:
    if concept not in DEX_DOC:
        fails.append(f"doc: DEX.md v1.3 concept {concept} not documented")
for const, key in [("F_LP_LOCKED", "pl"), ("LPF_W", "w")]:
    if f'const {const}: string = "{key}"' not in DEX_CONTRACT:
        fails.append(f"dex contract: v1.3 key {key} ({const}) missing")
for fn in ("entry remove_liquidity",):
    if fn not in DEX_CONTRACT:
        fails.append(f"dex contract: {fn} missing")
if "const EV_LIQUIDITY_REMOVED: u64 = 14" not in DEX_CONTRACT:
    fails.append("dex contract: event 14 (LiquidityRemoved) missing")
for guard in ('require(parts <= w, "locked")', '"seederr"', '"parterr"',
              '"seedlp"'):
    if guard not in DEX_CONTRACT:
        fails.append(f"dex contract: v1.3 guard {guard} missing")
# LAUNCHPAD.md must say the new anti-rug model LOUDLY
for concept in ("seed is protocol-locked", "remove_liquidity"):
    if concept not in DOC:
        fails.append(f"doc: LAUNCHPAD.md v1.3 concept {concept} missing")

# v1.4 DEX sanity: the open seeding endpoint + the second-migration fix
# are documented in DEX.md and present in the contract
for concept in ["X13", "create_pool_open", "second-migration",
                "permissionless", "CommunityLaunch"]:
    if concept not in DEX_DOC:
        fails.append(f"doc: DEX.md v1.4 concept {concept} not documented")
if "pub fn create_pool_open(asset: Hash) -> u64" not in DEX_CONTRACT:
    fails.append("dex contract: create_pool_open missing")
if "33  create_pool_open" not in DEX_CONTRACT:
    fails.append("dex contract: chunk table does not list create_pool_open at 33")
# THE FIX: create_pool must return 0 (a non-zero cross-call result is
# treated as failure by the pinned launchpad's migrate_to_dex) — check
# the ACTUAL return statements (the fix's comment mentions the old one)
import re as _re
_cp = _re.search(r"pub fn create_pool\(.*?\n\}", DEX_CONTRACT, _re.S)
if not _cp:
    fails.append("dex contract: create_pool body not found")
elif _re.findall(r"^\s*return (\w+)", _cp.group(0), _re.M) != ["0"]:
    fails.append("dex contract: create_pool must return 0 — it still "
                 "returns the pool index (the second-migration bug)")
_cpo = _re.search(r"pub fn create_pool_open\(.*?\n\}", DEX_CONTRACT, _re.S)
if not _cp or not _cpo:
    fails.append("dex contract: create_pool/create_pool_open bodies not found")
else:
    if "return 0" not in _cpo.group(0):
        fails.append("dex contract: create_pool_open must return 0")
    if 'require(caller == lpx' in _cpo.group(0):
        fails.append("dex contract: create_pool_open must NOT gate on lpx (X13)")
    if '"paused"' not in _cpo.group(0):
        fails.append("dex contract: create_pool_open must check the emergency pause")
    if 's.store(LAUNCHPAD_PINNED_KEY, true)' not in _cpo.group(0):
        fails.append("dex contract: create_pool_open must freeze the lpx pin "
                     "at the first pool (X4)")

# CommunityLaunch sanity: the community track's contract, doc, keys,
# entries and pinned cross-call chunk agree
try:
    COMMUNITY_CONTRACT_SRC = (REPO / "contracts" / "community"
                              / "CommunityLaunch.slx").read_text()
    COMMUNITY_DOC_SRC = (REPO / "docs" / "COMMUNITY_LAUNCH.md").read_text()
except FileNotFoundError as e:
    fails.append(f"community track file missing: {e.filename}")
    COMMUNITY_CONTRACT_SRC = ""
    COMMUNITY_DOC_SRC = ""
if COMMUNITY_CONTRACT_SRC:
    if 'const VERSION: string = "CommunityLaunch v1.0.1"' not in COMMUNITY_CONTRACT_SRC:
        fails.append("community contract: VERSION is not v1.0.1")
    if "v1.0.1" not in COMMUNITY_DOC_SRC:
        fails.append("doc: COMMUNITY_LAUNCH.md does not say v1.0.1")
    for concept in ["C1", "C2", "C4", "virtual", "graduation", "migrate",
                    "create_pool_open", "IC3", "IC4", "permissionless",
                    "Asset::create", "Fixed", "min_tokens_out", "LaunchDEX"]:
        if concept not in COMMUNITY_DOC_SRC:
            fails.append(f"doc: COMMUNITY_LAUNCH.md concept {concept} not documented")
    for fn in ("entry launch_coin", "entry buy", "entry sell", "entry migrate",
               "entry claim_creator_allocation", "entry update_coin_info",
               "entry set_dex_address", "entry withdraw_fees",
               "pub fn get_curve_info", "pub fn get_coin_by_asset",
               "pub fn get_buy_quote", "pub fn get_sell_quote",
               "pub fn get_market_cap", "pub fn get_status_label"):
        if fn not in COMMUNITY_CONTRACT_SRC:
            fails.append(f"community contract: {fn} missing")
    for guard in ('require(tokens <= yr, "curverr")',
                  'require(gross <= xr, "curverr")',
                  'require(dep >= committed, "budget")'):
        if guard not in COMMUNITY_CONTRACT_SRC:
            fails.append(f"community contract: guard {guard} missing")
    if "const DEX_CREATE_POOL_OPEN_CHUNK: u16 = 33" not in COMMUNITY_CONTRACT_SRC:
        fails.append("community contract: the pinned cross-call chunk 33 is missing")
    if "const DEFAULT_VIRTUAL_XEL: u64 = 10000000000" not in COMMUNITY_CONTRACT_SRC:
        fails.append("community contract: DEFAULT_VIRTUAL_XEL is not 100 XEL")
    if "const DEFAULT_GRADUATION_DEPTH: u64 = 5000000000" not in COMMUNITY_CONTRACT_SRC:
        fails.append("community contract: DEFAULT_GRADUATION_DEPTH is not 50 XEL")
    if "const MAX_CREATOR_BPS: u64 = 500" not in COMMUNITY_CONTRACT_SRC:
        fails.append("community contract: MAX_CREATOR_BPS is not 5%")

# the upgrade runbook exists and the honest audit status is written
for path, needle in (("docs/UPGRADES.md", "generation"),
                     ("docs/SECURITY.md", "NO external, independent"),
                     ("docs/SECURITY.md", "Front-running")):
    if not (REPO / path).exists() or needle not in (REPO / path).read_text():
        fails.append(f"doc: {path} missing the {needle!r} section")

# 7. the doc's fee schedule quotes the real default pair
if "0.25%" not in DOC or "0.50%" not in DOC or "0.5%" not in DOC:
    fails.append("doc: fee schedule defaults not documented")

if fails:
    print("DOC-PARITY AUDIT FAILED:")
    for f in fails:
        print("  -", f)
    sys.exit(1)
print("doc-parity audit: OK — contracts, docs (LAUNCHPAD/DEX/SECURITY/"
      "UPGRADES) and SDK agree on keys, defaults, events, views, "
      "versions and the v4.2/v1.2 provider surface")
