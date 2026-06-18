#!/usr/bin/env python3
"""
XELIS Vault v4.2 — Complete Test Suite

Exhaustive test script for all XELIS Vault contracts on testnet.
Cannot sign transactions (requires xelis_wallet), but performs:

    1. Testnet connection (public RPC)
    2. Network verification (sync, topoheight, version)
    3. Syntax analysis of all .slx contracts
    4. Inter-contract consistency checks (entry IDs)
    5. External API verification (MEXC, CoinEx, CoinGecko)
    6. Economic calculation simulation (rewards, slashing)
    7. Detailed test report generation

USAGE: python3 test_all_contracts.py
"""
import os
import sys
import json
import time
import requests
from pathlib import Path
from datetime import datetime

TESTNET_RPC = "https://testnet-node.xelis.io/json_rpc"
REPO_DIR = Path(__file__).parent.parent
CONTRACTS_DIR = REPO_DIR / "contracts"
REPORT_FILE = REPO_DIR / "test_report.md"

class C:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    END = '\033[0m'

def ok(msg):    print(f"  {C.GREEN}OK{C.END} {msg}")
def warn(msg):  print(f"  {C.YELLOW}!!{C.END} {msg}")
def err(msg):   print(f"  {C.RED}XX{C.END} {msg}")
def info(msg):  print(f"  {C.BLUE}..{C.END} {msg}")

results = {"start_time": datetime.now().isoformat(), "tests": [], "summary": {"pass": 0, "warn": 0, "fail": 0}}

def record(name, status, detail=""):
    results["tests"].append({"name": name, "status": status, "detail": detail})
    if status == "PASS": results["summary"]["pass"] += 1
    elif status == "WARN": results["summary"]["warn"] += 1
    else: results["summary"]["fail"] += 1


def test_testnet_connection():
    print(f"\n{C.HEADER}{C.BOLD}=== 1. TESTNET CONNECTION ==={C.END}")
    try:
        r = requests.post(TESTNET_RPC, json={"method": "get_info", "jsonrpc": "2.0", "id": 1}, timeout=15)
        r.raise_for_status()
        data = r.json()
        if "result" not in data:
            err(f"Response: {data}")
            record("testnet_connection", "FAIL", str(data))
            return None
        info_node = data["result"]
        ok(f"Connected to XELIS testnet")
        info(f"Network: {info_node.get('network')}")
        info(f"Topoheight: {info_node.get('topoheight')}")
        info(f"Height: {info_node.get('height')}")
        info(f"Version: {info_node.get('version')}")
        info(f"Block time: {info_node.get('block_time_target')}ms")
        info(f"Circulating supply: {info_node.get('circulating_supply')}")
        if info_node.get("network") != "testnet":
            err("WRONG NETWORK - must be testnet!")
            record("testnet_network", "FAIL", f"network={info_node.get('network')}")
        else:
            record("testnet_connection", "PASS")
            record("testnet_network", "PASS")
        bt = info_node.get("block_time_target", 0)
        if 4000 <= bt <= 6000:
            ok(f"Block time confirmed: {bt}ms (~5s)")
            record("block_time", "PASS", f"{bt}ms")
        else:
            warn(f"Unexpected block time: {bt}ms")
            record("block_time", "WARN", f"{bt}ms")
        return info_node
    except Exception as e:
        err(f"Connection failed: {e}")
        record("testnet_connection", "FAIL", str(e))
        return None


def test_contracts_syntax():
    print(f"\n{C.HEADER}{C.BOLD}=== 2. CONTRACT SYNTAX ANALYSIS ==={C.END}")
    if not CONTRACTS_DIR.exists():
        err(f"Contracts dir not found: {CONTRACTS_DIR}")
        record("contracts_dir", "FAIL", str(CONTRACTS_DIR))
        return
    contracts = sorted(CONTRACTS_DIR.rglob("*.slx"))
    info(f"Found {len(contracts)} .slx contracts")
    if len(contracts) != 31:
        warn(f"Expected 31 contracts, found {len(contracts)}")
        record("contracts_count", "WARN", f"{len(contracts)}")
    else:
        ok(f"31 contracts present")
        record("contracts_count", "PASS")
    for contract in contracts:
        name = contract.stem
        try:
            content = contract.read_text()
            open_paren = content.count('(')
            close_paren = content.count(')')
            if open_paren != close_paren:
                err(f"{name}: unbalanced parens ({open_paren} vs {close_paren})")
                record(f"syntax_{name}", "FAIL", "parentheses")
                continue
            open_brace = content.count('{')
            close_brace = content.count('}')
            if open_brace != close_brace:
                err(f"{name}: unbalanced braces ({open_brace} vs {close_brace})")
                record(f"syntax_{name}", "FAIL", "braces")
                continue
            if 'hook constructor' not in content:
                warn(f"{name}: no constructor")
                record(f"syntax_{name}", "WARN", "no_constructor")
                continue
            ok(f"{name}")
            record(f"syntax_{name}", "PASS")
        except Exception as e:
            err(f"{name}: {e}")
            record(f"syntax_{name}", "FAIL", str(e))


def test_inter_contract_consistency():
    print(f"\n{C.HEADER}{C.BOLD}=== 3. INTER-CONTRACT CONSISTENCY ==={C.END}")
    contracts_to_check = [
        ("VaultEngineV3", "contracts/vault/VaultEngineV3.slx"),
        ("PSM", "contracts/amm/PSM.slx"),
        ("VaultSwapV2", "contracts/amm/VaultSwapV2.slx"),
    ]
    for name, rel_path in contracts_to_check:
        path = REPO_DIR / rel_path
        if not path.exists():
            err(f"{name}: file not found")
            record(f"inter_contract_{name}", "FAIL", "file not found")
            continue
        content = path.read_text()
        mint_split_calls = content.count("xusd.call(2u16")
        burn_calls = content.count("xusd.call(3u16")
        bad_burn_calls = content.count("xusd.call(4u16")
        if bad_burn_calls > 0:
            err(f"{name}: {bad_burn_calls} xUSD calls with entry ID 4 (should be 3)")
            record(f"inter_contract_{name}", "FAIL", f"bad entry ID: {bad_burn_calls}")
        elif mint_split_calls > 0 or burn_calls > 0:
            ok(f"{name}: mint_split={mint_split_calls}, burn={burn_calls} - consistent")
            record(f"inter_contract_{name}", "PASS", f"mint_split={mint_split_calls}, burn={burn_calls}")
        else:
            ok(f"{name}: no xUSD calls (OK)")
            record(f"inter_contract_{name}", "PASS", "no xUSD calls")


def test_price_sources():
    print(f"\n{C.HEADER}{C.BOLD}=== 4. PRICE API TEST ==={C.END}")
    sources = {
        "MEXC": {
            "url": "https://api.mexc.com/api/v3/ticker/price",
            "params": {"symbol": "XELUSDT"},
            "extract": lambda d: float(d["price"]),
        },
        "CoinEx": {
            "url": "https://api.coinex.com/v2/spot/ticker",
            "params": {"market": "XELUSDT"},
            "extract": lambda d: float(d["data"][0]["last"]),
        },
        "CoinGecko": {
            "url": "https://api.coingecko.com/api/v3/simple/price",
            "params": {"ids": "xelis", "vs_currencies": "usd"},
            "extract": lambda d: float(d["xelis"]["usd"]),
        },
    }
    prices = {}
    for name, cfg in sources.items():
        try:
            r = requests.get(cfg["url"], params=cfg["params"], timeout=10)
            if r.status_code == 429:
                warn(f"{name}: rate limited (429)")
                record(f"price_source_{name}", "WARN", "rate limited")
                continue
            r.raise_for_status()
            price = cfg["extract"](r.json())
            if 0.001 < price < 10000:
                ok(f"{name}: ${price:.6f}")
                prices[name] = price
                record(f"price_source_{name}", "PASS", f"${price:.6f}")
            else:
                err(f"{name}: non-sane price ${price}")
                record(f"price_source_{name}", "FAIL", f"price={price}")
        except Exception as e:
            err(f"{name}: {e}")
            record(f"price_source_{name}", "FAIL", str(e))
    if len(prices) >= 2:
        price_list = list(prices.values())
        min_p = min(price_list)
        max_p = max(price_list)
        median = sorted(price_list)[len(price_list) // 2]
        spread_pct = ((max_p - min_p) / median) * 100
        if spread_pct < 5:
            ok(f"Consistency: spread {spread_pct:.2f}% (< 5%)")
            record("price_consistency", "PASS", f"spread={spread_pct:.2f}%")
        else:
            warn(f"High spread: {spread_pct:.2f}%")
            record("price_consistency", "WARN", f"spread={spread_pct:.2f}%")
        info(f"Median price: ${median:.6f}")
        info(f"Spread: {spread_pct:.2f}%")
    else:
        warn("Not enough sources to check consistency")
        record("price_consistency", "WARN", "insufficient sources")


def test_economic_calculations():
    print(f"\n{C.HEADER}{C.BOLD}=== 5. ECONOMIC SIMULATION ==={C.END}")
    VLT_SUPPLY = 10_000_000
    VLT_REWARDS_POOL = 6_000_000
    YEARS = 10
    BLOCK_TIME = 5
    BLOCKS_PER_YEAR = 31536000 // BLOCK_TIME
    CYCLES_PER_YEAR = BLOCKS_PER_YEAR // 5
    vlt_per_year = VLT_REWARDS_POOL / YEARS
    vlt_per_day = vlt_per_year / 365
    cycles_per_day = (86400 / BLOCK_TIME) / 5
    reward_per_cycle = vlt_per_day / cycles_per_day
    info(f"VLT supply total: {VLT_SUPPLY:,}")
    info(f"VLT rewards pool: {VLT_REWARDS_POOL:,} (60%)")
    info(f"Annual budget: {vlt_per_year:,} VLT/year")
    info(f"Daily budget: {vlt_per_day:.0f} VLT/day")
    info(f"Cycles/day: {cycles_per_day:.0f}")
    info(f"REWARD_PER_CYCLE: {reward_per_cycle:.4f} VLT")
    expected_atomic = 47_564_687
    actual_atomic = int(reward_per_cycle * 1e8)
    diff_pct = abs(actual_atomic - expected_atomic) / expected_atomic * 100
    if diff_pct < 1:
        ok(f"REWARD_PER_CYCLE consistent (diff {diff_pct:.2f}%)")
        record("economic_reward_per_cycle", "PASS", f"expected={expected_atomic}, actual={actual_atomic}")
    else:
        err(f"REWARD_PER_CYCLE inconsistent (diff {diff_pct:.2f}%)")
        record("economic_reward_per_cycle", "FAIL", f"expected={expected_atomic}, actual={actual_atomic}")
    print()
    info("ROI per provider count (stake 100 VLT):")
    for n in [10, 25, 50, 100, 200, 500, 1000]:
        reward_each = reward_per_cycle / n
        per_day = reward_each * cycles_per_day
        roi_days = 100 / per_day if per_day > 0 else 999999
        print(f"    {n:4d} providers -> {per_day:6.2f} VLT/day each (ROI: {roi_days:5.0f} days)")
    print()
    info("Slashing test:")
    MIN_STAKE = 100
    SLASH_BPS = 100
    slash_per_outlier = MIN_STAKE * SLASH_BPS / 10000
    info(f"  MIN_STAKE: {MIN_STAKE} VLT")
    info(f"  Slash per outlier: {slash_per_outlier} VLT (1%)")
    info(f"  50% burned: {slash_per_outlier / 2} VLT")
    info(f"  50% treasury: {slash_per_outlier / 2} VLT")
    outliers_to_disable = MIN_STAKE / slash_per_outlier
    info(f"  Provider disabled after {outliers_to_disable:.0f} outliers (stake < MIN_STAKE)")
    if outliers_to_disable == 100:
        ok(f"Slashing consistent: 100 outliers = full stake slashed")
        record("economic_slashing", "PASS", f"{outliers_to_disable:.0f} outliers")
    else:
        warn(f"Unexpected slashing: {outliers_to_disable:.0f} outliers")
        record("economic_slashing", "WARN", f"{outliers_to_disable:.0f} outliers")


def test_fees():
    print(f"\n{C.HEADER}{C.BOLD}=== 6. FEE VERIFICATION ==={C.END}")
    fees_expected = {
        "PSM mint fee": (50, "contracts/amm/PSM.slx", "DEFAULT_MINT_FEE_BPS"),
        "PSM redeem fee": (10, "contracts/amm/PSM.slx", "DEFAULT_REDEEM_FEE_BPS"),
        "VaultSwap swap fee": (30, "contracts/amm/VaultSwapV2.slx", "DEFAULT_BASE_FEE"),
        "VaultSwap treasury fee": (5, "contracts/amm/VaultSwapV2.slx", "DEFAULT_TREASURY_FEE"),
        "VaultEngine borrow fee": (50, "contracts/vault/VaultEngineV3.slx", "DEFAULT_PROTOCOL_FEE"),
        "VaultEngine insurance fee": (10, "contracts/vault/VaultEngineV3.slx", "DEFAULT_INSURANCE_FEE"),
        "VaultEngine redemption fee": (50, "contracts/vault/VaultEngineV3.slx", "DEFAULT_REDEMPTION_FEE"),
        "VaultEngine liquidation penalty": (1000, "contracts/vault/VaultEngineV3.slx", "DEFAULT_LIQ_PENALTY"),
        "StakedOracle slash bps": (100, "contracts/oracle/StakedOracle.slx", "DEFAULT_SLASH_BPS"),
        "FlashLoan fee": (9, "contracts/flashloan/FlashLoan.slx", "DEFAULT_FEE_BPS"),
    }
    import re
    for fee_name, (expected, rel_path, const_name) in fees_expected.items():
        path = REPO_DIR / rel_path
        if not path.exists():
            err(f"{fee_name}: contract not found")
            record(f"fee_{fee_name}", "FAIL", "file not found")
            continue
        content = path.read_text()
        patterns = re.findall(r'(\w+).*?:\s*u64\s*=\s*(\d+)', content)
        found = False
        for var_name, value in patterns:
            if var_name == const_name:
                value = int(value)
                if value == expected:
                    ok(f"{fee_name}: {value/100:.2f}% (expected {expected/100:.2f}%)")
                    record(f"fee_{fee_name}", "PASS", f"{value}")
                else:
                    err(f"{fee_name}: {value} (expected {expected})")
                    record(f"fee_{fee_name}", "FAIL", f"{value} != {expected}")
                found = True
                break
        if not found:
            warn(f"{fee_name}: constant {const_name} not found")
            record(f"fee_{fee_name}", "WARN", f"{const_name} not found")


def generate_report():
    print(f"\n{C.HEADER}{C.BOLD}=== REPORT GENERATION ==={C.END}")
    report = []
    report.append("# XELIS Vault v4.2 - Test Report")
    report.append("")
    report.append(f"**Generated**: {results['start_time']}")
    report.append(f"**Testnet**: https://testnet-node.xelis.io")
    report.append("")
    report.append("## Summary")
    report.append("")
    report.append(f"- **Passed**: {results['summary']['pass']}")
    report.append(f"- **Warnings**: {results['summary']['warn']}")
    report.append(f"- **Failed**: {results['summary']['fail']}")
    report.append(f"- **Total**: {sum(results['summary'].values())}")
    report.append("")
    pass_rate = results['summary']['pass'] / max(1, sum(results['summary'].values())) * 100
    report.append(f"**Pass rate**: {pass_rate:.1f}%")
    report.append("")
    report.append("## Detailed Results")
    report.append("")
    report.append("| Test | Status | Detail |")
    report.append("|------|--------|--------|")
    for test in results["tests"]:
        status_icon = {"PASS": "PASS", "WARN": "WARN", "FAIL": "FAIL"}[test["status"]]
        report.append(f"| {test['name']} | {status_icon} | {test['detail']} |")
    report.append("")
    report.append("## Notes")
    report.append("")
    report.append("- This script cannot sign transactions (requires xelis_wallet)")
    report.append("- To actually deploy, see `docs/TESTNET_DEPLOYMENT.md`")
    report.append("- Contracts must be compiled with silex-compiler before deployment")
    report.append("- 4 Silex APIs remain to validate with XELIS-Forge team (see `docs/COMPATIBILITY_TABLE.md`)")
    REPORT_FILE.write_text("\n".join(report))
    ok(f"Report saved: {REPORT_FILE}")
    print(f"\n{C.HEADER}{C.BOLD}=== FINAL SUMMARY ==={C.END}")
    print(f"  {C.GREEN}Passed: {results['summary']['pass']}{C.END}")
    print(f"  {C.YELLOW}Warnings: {results['summary']['warn']}{C.END}")
    print(f"  {C.RED}Failed: {results['summary']['fail']}{C.END}")
    print(f"  Pass rate: {pass_rate:.1f}%")
    print()


def main():
    print(f"\n{C.HEADER}{C.BOLD}")
    print("=" * 70)
    print("  XELIS Vault v4.2 - Complete Test Suite")
    print("=" * 70)
    print(f"{C.END}")
    print(f"Repo: {REPO_DIR}")
    print(f"Testnet RPC: {TESTNET_RPC}")
    print()
    test_testnet_connection()
    test_contracts_syntax()
    test_inter_contract_consistency()
    test_price_sources()
    test_economic_calculations()
    test_fees()
    generate_report()
    if results['summary']['fail'] > 0:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(1)
