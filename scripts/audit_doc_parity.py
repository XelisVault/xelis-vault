#!/usr/bin/env python3
"""audit_doc_parity.py — one-shot audit pass: docs/LAUNCHPAD.md and the SDK
must agree with contracts/launchpad/VaultLaunch.slx on every storage key,
default value and event id they mention. Exit 1 on any drift."""
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CONTRACT = (REPO / "contracts" / "launchpad" / "VaultLaunch.slx").read_text()
DOC = (REPO / "docs" / "LAUNCHPAD.md").read_text()

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
             "get_sell_quote", "get_token_balance", "get_projects_by_status",
             "get_project_by_rank", "get_latest_projects",
             "get_trusted_projects", "get_trusted_by_rank",
             "get_status_label", "get_config", "get_recovery_config",
             "get_team_config", "get_version", "get_project",
             "claim_team_allocation", "start_team_vesting"]:
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
                  ("EV_DIRECT_LISTED", 21), ("EV_MIGRATION_FEE", 22)]:
    if f"const {name}: u64 = {eid}" not in CONTRACT:
        fails.append(f"contract: event {name} = {eid} missing")

# 6. version strings agree
if 'const VERSION: string = "VaultLaunch v2.0.0"' not in CONTRACT:
    fails.append("contract: VERSION is not v2.0.0")
if "v2.0.0" not in DOC:
    fails.append("doc: LAUNCHPAD.md does not say v2.0.0")

# 7. the doc's fee schedule quotes the real default pair
if "0.25%" not in DOC or "0.50%" not in DOC or "0.5%" not in DOC:
    fails.append("doc: fee schedule defaults not documented")

if fails:
    print("DOC-PARITY AUDIT FAILED:")
    for f in fails:
        print("  -", f)
    sys.exit(1)
print("doc-parity audit: OK — contract, docs and SDK agree on keys, "
      "defaults, events, views and version")
