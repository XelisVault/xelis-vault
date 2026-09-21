#!/usr/bin/env python3
"""AUDIT 4 (v4) — SDK parity for the real-asset era: signatures, entry-ids
(BOTH contracts), deposits (budget + whole-deposit sell), the pinned
cross-call chunks, DEFAULTS parity and the v4 reader surface."""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sdk" / "xvault"))

LP_SRC = (ROOT / "contracts" / "launchpad" / "VaultLaunch.slx").read_text()
DEX_SRC = (ROOT / "contracts" / "dex" / "LaunchDEX.slx").read_text()

from xvault import dex as dx          # noqa: E402
from xvault import launchpad as lp    # noqa: E402
from xvault.protocol import LAUNCHDEX_ENTRY_IDS, LAUNCHPAD_ENTRY_IDS  # noqa: E402

fails = []


def check(cond, msg):
    if not cond:
        fails.append(msg)


# 1. propose: the 11 parameters in the SAME order contract <-> SDK
m = re.search(r"entry propose\(([^)]*)\)", LP_SRC)
check(m, "propose signature not found")
contract_params = [p.strip().split(":")[0] for p in m.group(1).split(",")]
sdk_params = ["name", "symbol", "description", "website", "logo", "twitter",
              "telegram", "discord", "total_supply", "team_bps",
              "vesting_duration"]
check(contract_params == sdk_params,
      f"propose params diverge: contract={contract_params} sdk={sdk_params}")

# 2. sell: v4 signature is sell(pid) — the whole deposit (no amount param)
m = re.search(r"entry sell\(([^)]*)\)", LP_SRC)
check(m and m.group(1).strip() == "pid: u64",
      f"sell signature must be (pid) in v4, got: {m.group(1) if m else None!r}")
check("sell_deposits" in dir(lp), "SDK: sell_deposits builder missing")

# 3. entry ids: every SDK id == the real declaration position (both files)
for src, ids, label in ((LP_SRC, LAUNCHPAD_ENTRY_IDS, "VaultLaunch"),
                        (DEX_SRC, LAUNCHDEX_ENTRY_IDS, "LaunchDEX")):
    order = re.findall(r"^(?:entry|pub fn|fn|hook) (\w+)", src, re.M)
    for fn_name, eid in ids.items():
        check(order.index(fn_name) == eid,
              f"{label}: chunk {eid} for {fn_name} != real {order.index(fn_name)}")

# 4. the pinned cross-call chunks (D19) match the DEX's real table
m1 = re.search(r"const DEX_CREATE_POOL_CHUNK: u16 = (\d+)", LP_SRC)
m2 = re.search(r"const DEX_SET_PAUSED_CHUNK: u16 = (\d+)", LP_SRC)
dorder = re.findall(r"^(?:entry|pub fn|fn|hook) (\w+)", DEX_SRC, re.M)
check(m1 and dorder.index("create_pool") == int(m1.group(1)),
      "pinned create_pool chunk drifted")
check(m2 and dorder.index("set_pool_buys_paused") == int(m2.group(1)),
      "pinned set_pool_buys_paused chunk drifted")

# 5. DEFAULTS parity: SDK numbers == contract constants (both files)
for const, val in (("DEFAULT_ASSET_BUDGET", lp.DEFAULTS["asset_budget"]),
                   ("DEFAULT_SUBMISSION_FEE", lp.DEFAULTS["submission_fee"]),
                   ("DEFAULT_TRADING_FEE_BPS", lp.DEFAULTS["trading_fee_bps"]),
                   ("DEFAULT_GRADUATED_FEE_BPS", lp.DEFAULTS["graduated_fee_bps"]),
                   ("DEFAULT_MIGRATION_FEE_BPS", lp.DEFAULTS["migration_fee_bps"])):
    check(f"const {const}: u64 = {val}" in LP_SRC, f"contract default {const} drifted")
check(f"const DEFAULT_SWAP_FEE_BPS: u64 = {dx.DEFAULTS['swap_fee_bps']}" in DEX_SRC,
      "DEX default swap fee drifted")

# 6. propose deposits include the asset budget (D13)
src = open(ROOT / "sdk" / "xvault" / "xvault" / "launchpad.py").read()
check("submission_fee + asset_budget + liquidity" in src,
      "SDK propose_deposits must sum fee + budget + liquidity")

# 7. the v4 reader surface: asset + migration fields, dex module
reader_attrs = ["asset_info", "migration_info", "dex_address", "migrated_count"]
for attr in reader_attrs:
    check(f"def {attr}(" in src, f"LaunchpadReader.{attr} missing")
dex_src = open(ROOT / "sdk" / "xvault" / "xvault" / "dex.py").read()
for piece in ("class DexReader", "def xel_to_tokens_out", "def tokens_to_xel_out",
              "def spot_price", "def swap_xel_params", "def swap_token_params",
              "def add_liquidity_deposits", "def create_pool_params",
              "def pool_key"):
    check(piece in dex_src, f"xvault.dex missing {piece}")

# 8. the math mirrors: SDK formula == contract formula (spot check on the
# DEX buy path, the most formula-dense line)
check("(y as u128) * (net as u128) / ((x as u128) + (net as u128))" in DEX_SRC,
      "DEX buy formula changed — update xvault.dex")
check("token_reserve * net // (xel_reserve + net)" in dex_src,
      "SDK DEX buy formula drifted from the contract")

# 9. the v4.1 surface: D21 builders/readers + the X7 fit mirror
for piece in ("def vote_deposits", "def claim_vote_deposit_params",
              "def set_vote_deposit_params", "def vote_config",
              "def project_by_asset", "def migrated_by_rank",
              "def migrated_list", "def asset_lookup_key",
              "def migrated_index_key"):
    check(piece in src, f"xvault.launchpad missing {piece} (v4.1)")
check("def liquidity_fit" in dex_src, "xvault.dex missing liquidity_fit (X7)")
check('y * xel_in // x' in dex_src and 'x * tok_in // y' in dex_src,
      "SDK liquidity_fit formula drifted from the contract (X7)")
# the contract's fit and the SDK's fit agree on the branch logic
check("need_tok" in DEX_SRC and '"fiterr"' in DEX_SRC,
      "contract add_liquidity no longer carries the X7 fit guards")
# get_launchpad exposure on the DEX (upgrade-runbook bridge, point 3)
check("pub fn get_launchpad() -> (string, bool)" in DEX_SRC,
      "DEX get_launchpad view missing (v4.1)")

# 10. the v1.2 surface (X10/D23): builders, math mirrors, reader, defaults
for piece in ("def set_fee_split_params", "def claim_lp_fees_params",
              "def fee_split", "def lp_earnings", "def accrual_increment",
              "def lp_key", "def lp_info"):
    check(piece in dex_src, f"xvault.dex missing {piece} (v1.2/X10)")
# the split math mirrors the contract exactly (floor on the LP side)
check("lp_part = fee * lp_bps // 10_000" in dex_src and
      "return fee - lp_part, lp_part" in dex_src,
      "SDK fee_split formula drifted from the contract (X10)")
# the accrual mirror: lp_part * ACC_SCALE / total_depth, floored
check("lp_part * ACC_SCALE // total_depth" in dex_src,
      "SDK accrual_increment drifted from the contract (X10)")
check("(accrued - snapshot) * parts // ACC_SCALE" in dex_src,
      "SDK lp_earnings drifted from the contract (X10)")
# DEFAULTS + bounds parity: SDK == contract constants
check(f"const DEFAULT_LP_SHARE_BPS: u64 = {dx.DEFAULTS['lp_share_bps']}" in DEX_SRC,
      "DEX default LP share drifted")
check(f"const MIN_LP_SHARE_BPS: u64 = {dx.MIN_LP_SHARE_BPS}" in DEX_SRC,
      "DEX min LP share bound drifted")
check(f"const MAX_LP_SHARE_BPS: u64 = {dx.MAX_LP_SHARE_BPS}" in DEX_SRC,
      "DEX max LP share bound drifted")
check(f"const MIN_LP_ADD_XEL: u64 = {dx.MIN_LP_ADD_XEL}" in DEX_SRC,
      "DEX LP-entry floor drifted")
check(f"const ACC_SCALE: u64 = {dx.ACC_SCALE}" in DEX_SRC,
      "DEX accrual scale drifted")
# the v4.2 default: the D21 dial is 0.5 XEL refundable
check(f"const DEFAULT_VOTE_DEPOSIT: u64 = {lp.DEFAULTS['vote_deposit']}" in LP_SRC,
      "VaultLaunch default vote deposit drifted (v4.2)")
# the reader carries the LP pots/depth + the provider position
for piece in ('"lp_pot_xel", F_LP_POT_XEL', '"lp_pot_tokens", F_LP_POT_TOK',
              '"lp_total_depth", F_LP_TOTAL', '"fee_split_bps": "fsl"'):
    check(piece in dex_src, f"DexReader missing the X10 field {piece}")
# CLI surfaces the new entries
cli_src = open(ROOT / "sdk" / "xvault" / "xvault" / "cli.py").read()
for piece in ("claim-lp-fees", "set-fee-split", "def cmd_dex_lp",
              "LAUNCHDEX_ENTRY_IDS[\"claim_lp_fees\"]",
              "LAUNCHDEX_ENTRY_IDS[\"set_fee_split\"]"):
    check(piece in cli_src, f"CLI missing {piece} (v1.2/X10)")

# 11. the v1.3 surface (X11/X12): seed shares, removes, the floor views
for piece in ("def remove_liquidity_params", "def remove_outs",
              "LPF_W", "F_LP_LOCKED"):
    check(piece in dex_src, f"xvault.dex missing {piece} (v1.3/X11-X12)")
check("remove_liquidity_params" in dir(dx), "SDK remove builder not importable")
# the remove math mirrors the contract exactly (floored pro-rata, both sides)
check("parts * xel_reserve // total_depth" in dex_src and
      "parts * token_reserve // total_depth" in dex_src,
      "SDK remove_outs formula drifted from the contract (X12)")
# the contract's guards and the SDK's refusals agree
check('require(parts <= w, "locked")' in DEX_SRC and
      '"poolerr"' in DEX_SRC and '"seederr"' in DEX_SRC,
      "contract remove_liquidity no longer carries the X12 guards")
check('ValueError("poolerr")' in dex_src and
      'ValueError("dust")' in dex_src,
      "SDK remove_outs refusals drifted from the contract (X12)")
# the seed mint + the fees-only guarantee in the contract
check("s.store(pool_key(asset, F_LP_LOCKED), xel_seed)" in DEX_SRC,
      "contract create_pool no longer mints the seed floor (X11)")
check("s.store(seed_lkey + LPF_XEL, xel_seed)" in DEX_SRC and
      "s.store(seed_lkey + LPF_W" not in DEX_SRC,
      "the seed position must mint parts but NEVER withdrawable parts (X11)")
# the reader carries the seed floor + the withdrawable balance
for piece in ('"lp_locked_depth", F_LP_LOCKED', '"withdrawable": w'):
    check(piece in dex_src, f"DexReader missing the v1.3 field {piece}")
# CLI surfaces the remove
for piece in ("remove-liquidity", "def cmd_dex_remove_liquidity",
              "LAUNCHDEX_ENTRY_IDS[\"remove_liquidity\"]"):
    check(piece in cli_src, f"CLI missing {piece} (v1.3/X12)")

if fails:
    print("AUDIT 4 (SDK PARITY) FAILED:")
    for f in fails:
        print("  -", f)
    sys.exit(1)
print("AUDIT 4 (SDK PARITY): PASS — signatures (incl. whole-deposit sell), "
      "entry-ids on BOTH contracts, pinned cross-call chunks, defaults, "
      "budget deposits, the v4 reader surface, the dex math mirror, the "
      "v4.1 hardening surface (D21/D22/X7), the v1.2 LP revenue\n"
      "surface (X10/D23: split, accrual, claims, bounds) and the v1.3\n"
      "two-tier surface (X11 seed shares, X12 removes, the floor views)\n"
      "all agree with the contracts.")
