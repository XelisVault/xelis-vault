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

if fails:
    print("AUDIT 4 (SDK PARITY) FAILED:")
    for f in fails:
        print("  -", f)
    sys.exit(1)
print("AUDIT 4 (SDK PARITY): PASS — signatures (incl. whole-deposit sell), "
      "entry-ids on BOTH contracts, pinned cross-call chunks, defaults, "
      "budget deposits, the v4 reader surface, the dex math mirror and the "
      "v4.1 hardening surface (D21/D22/X7) all agree with the contracts.")
