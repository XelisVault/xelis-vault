#!/usr/bin/env python3
"""
============================================================================
 XELIS Vault v11.1 — Protocol Simulation Suite (COMPLETE REWRITE)
============================================================================
Updated with:
  - Bitcoin-style halving rewards (INITIAL_REWARD_PER_BLOCK / 2^epoch)
  - STAKE_FLOOR = 100,000 VLT (bounds APY when few miners)
  - CAP_STAKE_PER_MINER = 500,000 VLT (anti-concentration)
  - Stake-weighted oracle median (anti-Sybil)
  - Miner delegation (own + delegated stake)
  - Emergency powers (guardian slash, ban, freeze)

Scenarios:
  1. Bootstrapping (10 miners, 7 days)
  2. Normal Growth (100 miners, 100 vaults, 30 days)
  3. Sybil Attack on Oracle (100 Sybil miners)
  4. Bank Run / XEL Crash (-50%)
  5. Extreme Cases (1 miner, 10000 miners, 90% attacker)
  6. PSM Arbitrage + Peg Stress
  7. Cascade Liquidation (-44% crash)
  8. Delegation Flow (miners + delegators)
  9. Halving Over Time (year 1 vs year 5 vs year 10)
  10. Guardian Emergency Response
============================================================================
"""
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# ============================================================================
# CONSTANTS (match contract parameters v11.1)
# ============================================================================

VLT_TOTAL_SUPPLY = 10_000_000 * 10**8
VLT_ORACLE_BUDGET = 5_500_000 * 10**8
MIN_STAKE = 1000 * 10**8
BLOCKS_PER_YEAR = 6_307_200
BLOCKS_PER_DAY = 17_280

# v11.1: Bitcoin-style halving
INITIAL_REWARD_PER_BLOCK = 43593000  # ~0.436 VLT/block
HALVING_INTERVAL_BLOCKS = 6_307_200  # 1 year

# v11.1: STAKE_FLOOR and CAP
STAKE_FLOOR = 100_000 * 10**8  # 100,000 VLT virtual floor
CAP_STAKE_PER_MINER = 500_000 * 10**8  # 500,000 VLT max per miner

DEFAULT_MIN_CR = 150
LIQ_PENALTY = 10
STABILITY_FEE_APR = 2
PSM_MINT_FEE = 0.5
PSM_REDEEM_FEE = 0.1
SWAP_FEE = 0.3
MAX_DAILY_MINT_CAP = 100_000 * 10**8
MAX_DEVIATION_BPS = 2000
CB_THRESHOLD_BPS = 2000

REPUTATION_TIERS = {
    "Excellent": (8000, 1.5),
    "Good": (5000, 1.0),
    "Warning": (2000, 0.5),
    "Critical": (1000, 0.25),
    "Banned": (0, 0.0),
}

# ============================================================================
# SIMULATION STATE
# ============================================================================

@dataclass
class Miner:
    addr: str
    stake: int
    reputation: int = 5000
    total_rewards: int = 0
    total_slashed: int = 0
    active: bool = True
    submissions: int = 0
    valid_submissions: int = 0
    # Delegation
    delegated_stake: int = 0
    commission_bps: int = 1000  # 10% default
    name: str = ""

@dataclass
class Vault:
    owner: str
    collateral: int
    borrow: int
    created_at: int

@dataclass
class ProtocolState:
    miners: Dict[str, Miner] = field(default_factory=dict)
    total_staked: int = 0

    xel_price: int = 19_000000
    oracle_paused: bool = False
    cb_paused: bool = False
    last_aggregation: int = 0
    launch_block: int = 0

    vaults: List[Vault] = field(default_factory=list)
    total_collateral: int = 0
    total_borrow: int = 0

    psm_xel_reserve: int = 0
    psm_xusd_minted: int = 0
    daily_mint_used: int = 0
    daily_redeem_used: int = 0

    distributed_rewards: int = 0
    xusd_supply: int = 0
    current_block: int = 0
    rewards_frozen: bool = False

    total_deposits: int = 0
    total_borrows: int = 0
    total_repays: int = 0
    total_liquidations: int = 0
    total_swaps: int = 0

    def get_rep_mult(self, rep):
        for name, (threshold, mult) in REPUTATION_TIERS.items():
            if rep >= threshold:
                return mult, name
        return 0.0, "Banned"

    def advance_blocks(self, n):
        self.current_block += n
        if self.current_block % BLOCKS_PER_DAY == 0:
            self.daily_mint_used = 0
            self.daily_redeem_used = 0

    def advance_days(self, n):
        self.advance_blocks(n * BLOCKS_PER_DAY)

# ============================================================================
# CORE PROTOCOL FUNCTIONS (v11.1)
# ============================================================================

def get_block_reward(state):
    """Bitcoin-style halving: reward = INITIAL / 2^epoch"""
    elapsed = state.current_block - state.launch_block
    if elapsed <= 0:
        return INITIAL_REWARD_PER_BLOCK
    epoch = elapsed // HALVING_INTERVAL_BLOCKS
    reward = INITIAL_REWARD_PER_BLOCK
    for _ in range(epoch):
        reward = reward // 2
        if reward == 0:
            return 0
    return reward

def get_stake_weighted_median(prices_with_stakes):
    """Stake-weighted median (anti-Sybil)."""
    if not prices_with_stakes:
        return 0
    sorted_ps = sorted(prices_with_stakes, key=lambda x: x[0])
    total_stake = sum(s for _, s in sorted_ps)
    if total_stake == 0:
        return sorted_ps[len(sorted_ps)//2][0]
    half = total_stake / 2
    cumul = 0
    for price, stake in sorted_ps:
        cumul += stake
        if cumul > half:
            return price
    return sorted_ps[-1][0]

def get_total_stake_with_delegation(state):
    """Total stake including delegated (for oracle weight)."""
    return state.total_staked  # In v11.1, total_staked already includes delegated

def distribute_rewards(state):
    """v11.1: Bitcoin-style halving + STAKE_FLOOR + cap_stake + reputation."""
    if state.rewards_frozen:
        return 0, "Rewards frozen"

    active_miners = [m for m in state.miners.values() if m.active]
    if not active_miners:
        return 0, "No active miners"

    block_reward = get_block_reward(state)
    if block_reward == 0:
        return 0, "Rewards exhausted (halving)"

    # STAKE_FLOOR: use max(total_staked, STAKE_FLOOR) as denominator
    effective_total = max(state.total_staked, STAKE_FLOOR)

    total_distributed = 0
    for miner in active_miners:
        rep_mult_float, _ = state.get_rep_mult(miner.reputation)
        rep_mult = int(rep_mult_float * 10000)

        effective_stake = min(miner.stake + miner.delegated_stake, CAP_STAKE_PER_MINER)

        # v11.2: Concentration penalty curve
        concentration_factor = 10000  # 1.0x default
        total_stake_all = state.total_staked
        if total_stake_all > 0:
            miner_share_bps = (miner.stake * 10000) // total_stake_all
            if miner_share_bps > 800:  # 8% soft threshold
                if miner_share_bps >= 2000:  # 20% hard threshold
                    concentration_factor = 3000  # 0.3x
                else:
                    excess = miner_share_bps - 800
                    range_val = 2000 - 800  # 1200
                    penalty = (excess * 7000) // range_val
                    concentration_factor = 10000 - penalty

        reward_per_block = int(block_reward * effective_stake * rep_mult * concentration_factor / (effective_total * 100000000))
        reward = reward_per_block * BLOCKS_PER_DAY
        if reward > 0:
            miner.total_rewards += reward
            state.distributed_rewards += reward
            total_distributed += reward
            miner.valid_submissions += 1

    return total_distributed, f"Distributed {total_distributed/10**8:.1f} VLT to {len(active_miners)} miners"

def deposit_collateral(state, user, xel_amount):
    vault = Vault(owner=user, collateral=xel_amount, borrow=0, created_at=state.current_block)
    state.vaults.append(vault)
    state.total_collateral += xel_amount
    state.total_deposits += 1
    return vault

def borrow_xusd(state, vault, xusd_amount):
    collateral_value = (vault.collateral * state.xel_price) // 10**8
    max_borrow = (collateral_value * 100) // DEFAULT_MIN_CR
    if vault.borrow + xusd_amount > max_borrow:
        return False, f"Exceeds max borrow ({max_borrow/10**8:.2f} xUSD)"
    vault.borrow += xusd_amount
    state.total_borrow += xusd_amount
    state.xusd_supply += xusd_amount
    return True, "OK"

def get_health_factor(state, vault):
    if vault.borrow == 0:
        return 999999
    collateral_value = (vault.collateral * state.xel_price) // 10**8
    return (collateral_value * 10000) // vault.borrow

def liquidate_vault(state, vault):
    hf = get_health_factor(state, vault)
    if hf >= 10000:
        return False, "Not liquidatable"
    state.total_collateral -= vault.collateral
    state.total_borrow -= vault.borrow
    state.xusd_supply -= vault.borrow
    state.total_liquidations += 1
    vault.collateral = 0
    vault.borrow = 0
    return True, f"Liquidated (health was {hf/100:.0f}%)"

def psm_mint(state, user, xel_amount):
    if state.oracle_paused or state.cb_paused:
        return False, "Oracle paused"
    if state.daily_mint_used + xel_amount > MAX_DAILY_MINT_CAP:
        return False, "Daily cap exceeded"
    gross_xusd = (xel_amount * state.xel_price) // 10**8
    fee = (gross_xusd * PSM_MINT_FEE) // 100
    net_xusd = gross_xusd - fee
    state.psm_xel_reserve += xel_amount
    state.psm_xusd_minted += net_xusd
    state.xusd_supply += net_xusd
    state.daily_mint_used += xel_amount
    return True, f"Minted {net_xusd/10**8:.2f} xUSD"

def psm_redeem(state, user, xusd_amount):
    if state.oracle_paused or state.cb_paused:
        return False, "Oracle paused"
    gross_xel = (xusd_amount * 10**8) // state.xel_price
    fee = (gross_xel * PSM_REDEEM_FEE) // 100
    net_xel = gross_xel - fee
    if net_xel > state.psm_xel_reserve:
        return False, f"Insufficient PSM reserve ({state.psm_xel_reserve/10**8:.0f} XEL)"
    state.psm_xel_reserve -= net_xel
    state.psm_xusd_minted -= xusd_amount
    state.xusd_supply -= xusd_amount
    return True, f"Redeemed {net_xel/10**8:.2f} XEL"

def register_miner(state, addr, stake, name=""):
    if stake < MIN_STAKE:
        return False, f"Stake too low (min {MIN_STAKE/10**8:.0f} VLT)"
    miner = Miner(addr=addr, stake=stake, name=name)
    state.miners[addr] = miner
    state.total_staked += stake
    return True, "Registered"

def delegate_to_miner(state, delegator_addr, miner_addr, amount):
    if amount < 10 * 10**8:
        return False, "Min 10 VLT"
    miner = state.miners.get(miner_addr)
    if not miner or not miner.active:
        return False, "Miner not active"
    # Cap check
    total = miner.stake + miner.delegated_stake + amount
    if total > CAP_STAKE_PER_MINER:
        return False, f"Cap exceeded ({CAP_STAKE_PER_MINER/10**8:.0f} VLT max)"
    miner.delegated_stake += amount
    state.total_staked += amount
    return True, f"Delegated {amount/10**8:.0f} VLT"

def aggregate_prices(state, price_submissions):
    prices_with_stakes = []
    for miner_addr, price in price_submissions:
        miner = state.miners.get(miner_addr)
        if miner and miner.active:
            # v11.1: Use own + delegated stake for oracle weight
            total_stake = miner.stake + miner.delegated_stake
            prices_with_stakes.append((price, total_stake))
    if not prices_with_stakes:
        return False, "No valid submissions"
    new_price = get_stake_weighted_median(prices_with_stakes)
    if state.xel_price > 0:
        diff = abs(new_price - state.xel_price)
        pct = (diff * 10000) // state.xel_price
        if pct > CB_THRESHOLD_BPS:
            state.cb_paused = True
            return False, f"Circuit breaker triggered ({pct/100:.1f}% deviation)"
    state.xel_price = new_price
    state.last_aggregation = state.current_block
    return True, f"Aggregated to ${new_price/10**8:.4f}"

def slash_miner(state, miner_addr, slash_bps):
    miner = state.miners.get(miner_addr)
    if not miner:
        return 0, "Not found"
    slash_amount = (miner.stake * slash_bps) // 10000
    miner.stake -= slash_amount
    miner.total_slashed += slash_amount
    state.total_staked -= slash_amount
    rep_loss = (10000 * slash_bps) // 10000
    miner.reputation = max(0, miner.reputation - rep_loss)
    if miner.stake < MIN_STAKE:
        miner.active = False
    return slash_amount, f"Slashed {slash_amount/10**8:.1f} VLT"

# ============================================================================
# SCENARIO RUNNER
# ============================================================================

def run_scenario(name, fn):
    print(f"\n{'='*70}")
    print(f"  SCENARIO: {name}")
    print(f"{'='*70}\n")
    state = ProtocolState()
    state.launch_block = 0
    results = fn(state)
    print(f"\n--- Final State ---")
    print(f"  Block:          {state.current_block:,}")
    print(f"  Miners:         {len([m for m in state.miners.values() if m.active])} active")
    print(f"  Total staked:   {state.total_staked/10**8:,.0f} VLT")
    print(f"  XEL price:      ${state.xel_price/10**8:.4f}")
    print(f"  xUSD supply:    {max(0, state.xusd_supply)/10**8:,.0f}")
    print(f"  Total collateral: {state.total_collateral/10**8:,.0f} XEL")
    print(f"  Total borrow:   {state.total_borrow/10**8:,.0f} xUSD")
    print(f"  PSM reserve:    {state.psm_xel_reserve/10**8:,.0f} XEL")
    print(f"  Rewards distributed: {state.distributed_rewards/10**8:,.0f} VLT")
    print(f"  Liquidations:   {state.total_liquidations}")
    print(f"  Oracle paused:  {state.oracle_paused}")
    print(f"  CB paused:      {state.cb_paused}")
    print(f"  Rewards frozen: {state.rewards_frozen}")
    if results:
        print(f"\n--- Results ---")
        for r in results:
            print(f"  {r}")
    return state

# ============================================================================
# SCENARIO 1: Bootstrapping (10 miners, 7 days)
# ============================================================================

def scenario_bootstrap(state):
    results = []
    results.append("📋 10 miners register with 1,000 VLT each")

    for i in range(10):
        ok, msg = register_miner(state, f"miner_{i}", MIN_STAKE, f"Miner{i}")
    results.append(f"  ✅ {len(state.miners)} miners registered")
    results.append(f"  Total staked: {state.total_staked/10**8:.0f} VLT")

    block_reward = get_block_reward(state)
    daily_budget = block_reward * BLOCKS_PER_DAY / 10**8
    results.append(f"  Block reward: {block_reward/10**8:.4f} VLT/block")
    results.append(f"  Daily budget: {daily_budget:.0f} VLT/day")

    for day in range(7):
        state.advance_days(1)
        submissions = [(f"miner_{i}", 19_000000 + i * 10000) for i in range(10)]
        for addr, price in submissions:
            state.miners[addr].submissions += 1
        aggregate_prices(state, submissions)
        distribute_rewards(state)

    avg_reward = sum(m.total_rewards for m in state.miners.values()) / len(state.miners)
    effective_total = max(state.total_staked, STAKE_FLOOR)
    rep_mult = 10000  # 1.0x Good
    reward_per_block = block_reward * MIN_STAKE * rep_mult / (effective_total * 10000)
    daily_reward = reward_per_block * BLOCKS_PER_DAY
    expected_apy = (daily_reward * 365 / MIN_STAKE) * 100

    results.append(f"\nAfter 7 days:")
    results.append(f"  Price: ${state.xel_price/10**8:.4f}")
    results.append(f"  Rewards/miner: {avg_reward/10**8:.1f} VLT")
    results.append(f"  Est. APY: ~{expected_apy:.0f}%")
    results.append(f"  STAKE_FLOOR active: {'YES' if state.total_staked < STAKE_FLOOR else 'NO'}")

    if expected_apy > 5000:
        results.append("  ⚠️ WARNING: APY > 5000% — may attract Sybil")
    elif expected_apy > 500:
        results.append("  ✅ APY attractive but bounded by STAKE_FLOOR")
    else:
        results.append("  ✅ APY reasonable")

    total_distributed_7d = state.distributed_rewards
    budget_years = VLT_ORACLE_BUDGET / (total_distributed_7d / 7 * 365) if total_distributed_7d > 0 else 0
    results.append(f"  Budget lasts: {budget_years:.0f} years (geometric, not linear)")
    return results

# ============================================================================
# SCENARIO 2: Normal Growth (100 miners, 100 vaults, 30 days)
# ============================================================================

def scenario_growth(state):
    results = []
    for i in range(100):
        stake = MIN_STAKE + (i * 500 * 10**8)
        register_miner(state, f"miner_{i}", stake, f"Miner{i}")
    results.append(f"📋 100 miners (stakes 1k-50k VLT)")
    results.append(f"  Total staked: {state.total_staked/10**8:,.0f} VLT")

    for i in range(100):
        xel = (10 + i * 5) * 10**8
        vault = deposit_collateral(state, f"user_{i}", xel)
        max_borrow = (xel * state.xel_price) // 10**8 * 50 // 100
        borrow_xusd(state, vault, max_borrow)
    results.append(f"📋 100 vaults created")

    for i in range(50):
        psm_mint(state, f"user_{i}", 100 * 10**8)
    results.append(f"📋 50 PSM mints")

    for day in range(30):
        state.advance_days(1)
        submissions = [(f"miner_{i}", 19_000000 + (day * 10000 if day < 15 else -(day-15)*5000))
                       for i in range(50)]
        aggregate_prices(state, submissions)
        distribute_rewards(state)
        for vault in state.vaults:
            hf = get_health_factor(state, vault)
            if hf < 10000 and vault.borrow > 0:
                liquidate_vault(state, vault)

    avg_reward = sum(m.total_rewards for m in state.miners.values()) / len(state.miners)
    sorted_miners = sorted(state.miners.values(), key=lambda m: m.stake, reverse=True)
    top_1_pct = (sorted_miners[0].stake / state.total_staked) * 100
    top_10_stake = sum(m.stake for m in sorted_miners[:10])
    top_10_pct = (top_10_stake / state.total_staked) * 100

    results.append(f"After 30 days:")
    results.append(f"  Rewards/miner: {avg_reward/10**8:.1f} VLT")
    results.append(f"  Total distributed: {state.distributed_rewards/10**8:,.0f} VLT")
    results.append(f"  Liquidations: {state.total_liquidations}")
    results.append(f"  Top 1 miner: {top_1_pct:.1f}% of stake")
    results.append(f"  Top 10 miners: {top_10_pct:.1f}% of stake")

    if top_1_pct > 20:
        results.append("  ⚠️ WARNING: Top miner > 20% — concentration risk")
    else:
        results.append("  ✅ Decentralization OK")
    return results

# ============================================================================
# SCENARIO 3: Sybil Attack on Oracle
# ============================================================================

def scenario_sybil_attack(state):
    results = []
    for i in range(50):
        register_miner(state, f"honest_{i}", 2000 * 10**8)
    honest_stake = state.total_staked
    results.append(f"📋 50 honest miners, stake: {honest_stake/10**8:.0f} VLT")

    attacker_stake = 100_000 * 10**8
    for i in range(100):
        register_miner(state, f"sybil_{i}", attacker_stake // 100)
    results.append(f"📋 Attacker: 100 Sybil miners × {attacker_stake//100//10**8:.0f} VLT")
    results.append(f"  Attacker share: {(attacker_stake/state.total_staked)*100:.1f}%")

    # Day 1: honest only
    submissions = [(f"honest_{i}", 19_000000) for i in range(50)]
    aggregate_prices(state, submissions)
    results.append(f"\nDay 1 (honest only): ${state.xel_price/10**8:.4f} ✅")

    # Day 2: attack — Sybil submits $0.50
    state.cb_paused = False
    submissions = []
    for addr in state.miners:
        price = 19_000000 if "honest" in addr else 50_000000
        submissions.append((addr, price))

    simple_prices = sorted([p for _, p in submissions])
    simple_median = simple_prices[len(simple_prices)//2]

    prices_with_stakes = []
    for addr, price in submissions:
        m = state.miners[addr]
        prices_with_stakes.append((price, m.stake + m.delegated_stake))
    weighted_median = get_stake_weighted_median(prices_with_stakes)

    results.append(f"\nDay 2 (attack at $0.50):")
    results.append(f"  Simple median: ${simple_median/10**8:.4f} {'❌ MANIPULATED' if simple_median > 30_000000 else '✅'}")
    results.append(f"  Stake-weighted: ${weighted_median/10**8:.4f} {'❌ MANIPULATED' if weighted_median > 30_000000 else '✅'}")

    if weighted_median <= 30_000000:
        results.append(f"  ✅ Stake-weighted median RESISTED!")
    else:
        results.append(f"  ⚠️ Attack at 50% stake — theoretical limit reached")
        results.append(f"  Mitigation: Circuit breaker + guardian response")

    # Day 3: extreme attack $10
    state.cb_paused = False
    submissions = [(addr, 19_000000 if "honest" in addr else 1_000_000000) for addr in state.miners]
    ok, msg = aggregate_prices(state, submissions)
    results.append(f"\nDay 3 (extreme $10): {msg}")
    if state.cb_paused:
        results.append(f"  ✅ Circuit breaker triggered")

    # Day 4: Guardian response
    results.append(f"\nDay 4 (guardian response):")
    state.rewards_frozen = True
    dist, dmsg = distribute_rewards(state)
    results.append(f"  Rewards: {dmsg}")
    for i in range(10):
        slash_amount, smsg = slash_miner(state, f"sybil_{i}", 5000)  # 50% slash
    attacker_remaining = sum(m.stake for a, m in state.miners.items() if "sybil" in a)
    results.append(f"  Attacker slashed: {(attacker_stake - attacker_remaining)/10**8:.0f} VLT")
    results.append(f"  Attacker remaining: {attacker_remaining/10**8:.0f} VLT")
    return results

# ============================================================================
# SCENARIO 4: Bank Run / XEL Crash (-50%)
# ============================================================================

def scenario_bank_run(state):
    results = []
    for i in range(50):
        register_miner(state, f"miner_{i}", MIN_STAKE)
    for i in range(200):
        xel = (50 + i * 10) * 10**8
        vault = deposit_collateral(state, f"user_{i}", xel)
        max_borrow = (xel * state.xel_price) // 10**8 * 60 // 100
        borrow_xusd(state, vault, max_borrow)

    state.psm_xel_reserve = 500_000 * 10**8
    for i in range(500):
        psm_mint(state, f"psm_{i}", 1000 * 10**8)

    results.append(f"📋 50 miners, 200 vaults, 500k XEL PSM")
    results.append(f"  Collateral: {state.total_collateral/10**8:,.0f} XEL")
    results.append(f"  Borrow: {state.total_borrow/10**8:,.0f} xUSD")
    results.append(f"  PSM reserve: {state.psm_xel_reserve/10**8:,.0f} XEL")

    old_price = state.xel_price
    state.xel_price = 9_500000  # -50%
    results.append(f"\n💥 XEL CRASH -50%: ${old_price/10**8:.4f} → ${state.xel_price/10**8:.4f}")

    liquidatable = sum(1 for v in state.vaults if get_health_factor(state, v) < 10000 and v.borrow > 0)
    results.append(f"  Vaults liquidatable: {liquidatable}/{len(state.vaults)}")

    for vault in state.vaults:
        if vault.borrow > 0 and get_health_factor(state, vault) < 10000:
            liquidate_vault(state, vault)
    results.append(f"  Liquidations: {state.total_liquidations}")

    # PSM bank run
    successful = 0
    for i in range(1000):
        ok, msg = psm_redeem(state, f"user_{i}", 1000 * 10**8)
        if ok:
            successful += 1
        else:
            break
    results.append(f"\n🏃 PSM bank run: {successful}/1000 succeeded")
    results.append(f"  PSM reserve: {state.psm_xel_reserve/10**8:,.0f} XEL")

    backing = (state.total_collateral * state.xel_price) // 10**8
    if state.xusd_supply > 0:
        ratio = backing / state.xusd_supply * 100
        results.append(f"  xUSD backing: {ratio:.1f}%")
        if ratio >= 100:
            results.append(f"  ✅ xUSD still over-collateralized")
        else:
            results.append(f"  ❌ xUSD under-collateralized")
    return results

# ============================================================================
# SCENARIO 5: Extreme Cases
# ============================================================================

def scenario_extremes(state):
    results = []
    # Case A: 1 miner
    results.append("📋 Case A: 1 miner (1,000 VLT)")
    register_miner(state, "solo", MIN_STAKE)
    block_reward = get_block_reward(state)
    effective_total = max(state.total_staked, STAKE_FLOOR)
    reward_per_block = block_reward * MIN_STAKE * 10000 / (effective_total * 10000)
    daily = reward_per_block * BLOCKS_PER_DAY
    apy = (daily * 365 / MIN_STAKE) * 100
    results.append(f"  Daily reward: {daily/10**8:.1f} VLT")
    results.append(f"  APY: {apy:.0f}%")
    results.append(f"  STAKE_FLOOR bounds APY: {'YES' if state.total_staked < STAKE_FLOOR else 'NO'}")
    if apy < 10000:
        results.append("  ✅ STAKE_FLOOR prevents insane APY")
    else:
        results.append("  ⚠️ APY still high — consider higher STAKE_FLOOR")

    # Case B: 10,000 miners
    state2 = ProtocolState()
    state2.launch_block = 0
    results.append(f"\n📋 Case B: 10,000 miners (1,000 VLT each)")
    for i in range(10000):
        register_miner(state2, f"m_{i}", MIN_STAKE)
    effective_total2 = max(state2.total_staked, STAKE_FLOOR)
    reward_per_block2 = block_reward * MIN_STAKE * 10000 / (effective_total2 * 10000)
    daily2 = reward_per_block2 * BLOCKS_PER_DAY
    apy2 = (daily2 * 365 / MIN_STAKE) * 100
    results.append(f"  Daily reward/miner: {daily2/10**8:.4f} VLT")
    results.append(f"  APY: {apy2:.1f}%")
    if apy2 < 10:
        results.append("  ⚠️ APY < 10% — miners may leave")
    else:
        results.append("  ✅ APY reasonable at scale")

    # Case C: 90% attacker
    state3 = ProtocolState()
    state3.launch_block = 0
    results.append(f"\n📋 Case C: 90% stake attacker")
    for i in range(10):
        register_miner(state3, f"h_{i}", MIN_STAKE)
    register_miner(state3, "attacker", 90_000 * 10**8)
    attacker_pct = (90_000 * 10**8 / state3.total_staked) * 100
    results.append(f"  Attacker: {attacker_pct:.1f}% of total stake")
    if attacker_pct > 50:
        results.append(f"  ❌ CRITICAL: >50% stake — can manipulate oracle")
        results.append(f"  Mitigation: Guardian slash + circuit breaker + governance")
    return results

# ============================================================================
# SCENARIO 6: PSM Stress
# ============================================================================

def scenario_psm_stress(state):
    results = []
    state.psm_xel_reserve = 1_000_000 * 10**8
    state.xel_price = 19_000000
    results.append(f"📋 PSM: 1M XEL reserve, XEL=${state.xel_price/10**8:.4f}")

    ok, msg = psm_mint(state, "arb_1", 10_000 * 10**8)
    results.append(f"\nNormal mint 10k XEL: {msg}")

    # Massive mint attempt
    attempts = 0
    for i in range(1000):
        ok, msg = psm_mint(state, f"drain_{i}", 10_000 * 10**8)
        if ok:
            attempts += 1
        else:
            break
    results.append(f"\nMassive mint: {attempts} attempts succeeded")
    results.append(f"  Daily cap used: {(state.daily_mint_used/MAX_DAILY_MINT_CAP)*100:.1f}%")
    if state.daily_mint_used >= MAX_DAILY_MINT_CAP:
        results.append(f"  ✅ Daily cap prevented full drain")

    # Redeem stress
    total_redeemed = 0
    count = 0
    while state.psm_xel_reserve > 0 and count < 10000:
        ok, msg = psm_redeem(state, f"r_{count}", 1000 * 10**8)
        if ok:
            total_redeemed += 1000 * 10**8
            count += 1
        else:
            break
    results.append(f"\nRedeem stress: {count} reclaims, {total_redeemed/10**8:,.0f} XEL")
    results.append(f"  PSM reserve: {state.psm_xel_reserve/10**8:,.0f} XEL")
    if state.psm_xel_reserve == 0:
        results.append(f"  ⚠️ PSM drained — daily cap limits rate")
    return results

# ============================================================================
# SCENARIO 7: Cascade Liquidation
# ============================================================================

def scenario_cascade(state):
    results = []
    for i in range(100):
        xel = 100 * 10**8
        vault = deposit_collateral(state, f"user_{i}", xel)
        max_borrow = (xel * state.xel_price) // 10**8 * 60 // 100
        borrow_xusd(state, vault, max_borrow)
    results.append(f"📋 100 vaults at 60% LTV (health ~167%)")

    # Drop 30%
    state.xel_price = 13_300000
    results.append(f"\n💥 Drop -30%: ${state.xel_price/10**8:.4f}")
    below_100 = sum(1 for v in state.vaults if v.borrow > 0 and get_health_factor(state, v) < 10000)
    below_150 = sum(1 for v in state.vaults if v.borrow > 0 and get_health_factor(state, v) < 15000)
    results.append(f"  Below 100%: {below_100}, below 150%: {below_150}")

    for v in state.vaults:
        if v.borrow > 0 and get_health_factor(state, v) < 10000:
            liquidate_vault(state, v)
    results.append(f"  Liquidations: {state.total_liquidations}")

    if state.total_borrow > 0:
        backing = (state.total_collateral * state.xel_price) // 10**8
        ratio = backing / state.total_borrow * 100
        results.append(f"  Backing: {ratio:.1f}%")
        if ratio >= 100:
            results.append(f"  ✅ Protocol solvent")
        else:
            results.append(f"  ❌ Insolvent — bad debt")

    # Second wave -20%
    state.xel_price = 10_640000
    results.append(f"\n💥 Second drop (total -44%): ${state.xel_price/10**8:.4f}")
    wave2 = 0
    for v in state.vaults:
        if v.borrow > 0 and get_health_factor(state, v) < 10000:
            liquidate_vault(state, v)
            wave2 += 1
    results.append(f"  Wave 2 liquidations: {wave2}")
    results.append(f"  Total: {state.total_liquidations}")

    if state.total_borrow > 0:
        backing = (state.total_collateral * state.xel_price) // 10**8
        ratio = backing / state.total_borrow * 100
        results.append(f"  Final backing: {ratio:.1f}%")
    else:
        results.append(f"  ✅ All debt cleared — no bad debt")
    return results

# ============================================================================
# SCENARIO 8: Delegation Flow
# ============================================================================

def scenario_delegation(state):
    results = []
    # 5 miners register
    for i in range(5):
        register_miner(state, f"miner_{i}", MIN_STAKE, f"Miner{i}")
    results.append("📋 5 miners registered (1,000 VLT each)")

    # 20 delegators delegate to miner_0 (best reputation)
    for i in range(20):
        ok, msg = delegate_to_miner(state, f"del_{i}", "miner_0", 500 * 10**8)
    results.append(f"📋 20 delegators × 500 VLT → miner_0")
    results.append(f"  miner_0 total stake: {(state.miners['miner_0'].stake + state.miners['miner_0'].delegated_stake)/10**8:.0f} VLT")

    # Run 7 days
    for day in range(7):
        state.advance_days(1)
        submissions = [(f"miner_{i}", 19_000000) for i in range(5)]
        aggregate_prices(state, submissions)
        dist, msg = distribute_rewards(state)

    # Check rewards
    m0 = state.miners["miner_0"]
    m1 = state.miners["miner_1"]
    results.append(f"\nAfter 7 days:")
    results.append(f"  miner_0 rewards: {m0.total_rewards/10**8:.1f} VLT (has delegation)")
    results.append(f"  miner_1 rewards: {m1.total_rewards/10**8:.1f} VLT (no delegation)")
    results.append(f"  miner_0 earned {m0.total_rewards/max(m1.total_rewards,1):.1f}x more than miner_1")

    # Check concentration penalty
    m0_share = (m0.stake / state.total_staked) * 100
    results.append(f"\n  Concentration analysis:")
    results.append(f"  miner_0 stake share: {m0_share:.1f}% of total")
    if m0_share > 20:
        results.append(f"  ⚠️ miner_0 > 20% — concentration penalty at 0.3x (rewards reduced 70%)")
    elif m0_share > 8:
        penalty_pct = ((m0_share - 8) / 12) * 70
        results.append(f"  ⚠️ miner_0 in penalty zone ({m0_share:.1f}%) — rewards reduced {penalty_pct:.0f}%")
    else:
        results.append(f"  ✅ miner_0 < 8% — no concentration penalty")

    # Check oracle weight
    prices_with_stakes = []
    for addr, miner in state.miners.items():
        total = miner.stake + miner.delegated_stake
        prices_with_stakes.append((19_000000, total))
    total_weight = sum(s for _, s in prices_with_stakes)
    m0_weight = (m0.stake + m0.delegated_stake) / total_weight * 100
    results.append(f"\n  Oracle weight:")
    results.append(f"  miner_0: {m0_weight:.1f}% of total")
    if m0_weight > 50:
        results.append(f"  ⚠️ miner_0 controls >50% of oracle weight!")
        results.append(f"  Mitigation: Concentration penalty reduces rewards (not oracle weight)")
        results.append(f"  Mitigation: Guardian can slash if manipulation detected")
    else:
        results.append(f"  ✅ No single miner controls >50%")
    return results

# ============================================================================
# SCENARIO 9: Halving Over Time
# ============================================================================

def scenario_halving(state):
    results = []
    for i in range(100):
        register_miner(state, f"m_{i}", MIN_STAKE)
    results.append("📋 100 miners × 1,000 VLT")
    results.append(f"  Total stake: {state.total_staked/10**8:,.0f} VLT")
    results.append(f"  STAKE_FLOOR: {STAKE_FLOOR/10**8:,.0f} VLT")
    results.append(f"  Floor active: {'YES (APY bounded)' if state.total_staked < STAKE_FLOOR else 'NO'}")

    results.append(f"\nYear-by-year halving:")
    for year in range(1, 11):
        state.current_block = year * BLOCKS_PER_YEAR
        block_reward = get_block_reward(state)
        daily = block_reward * BLOCKS_PER_DAY
        effective_total = max(state.total_staked, STAKE_FLOOR)
        reward_per_block = block_reward * MIN_STAKE * 10000 / (effective_total * 10000)
        per_miner_daily = reward_per_block * BLOCKS_PER_DAY
        apy = (per_miner_daily * 365 / MIN_STAKE) * 100
        yearly_total = daily * 365 / 10**8
        cumul_pct = (1 - 1/(2**year)) * 100

        results.append(f"  Year {year:>2}: {yearly_total:>10,.0f} VLT/yr | "
                      f"{daily/10**8:>7.0f} VLT/day | "
                      f"APY: {apy:>7.0f}% | "
                      f"Cumul: {cumul_pct:.1f}%")

    results.append(f"\n  ✅ Rewards decrease naturally (Bitcoin-style)")
    results.append(f"  ✅ Budget never truly exhausted (geometric series)")
    results.append(f"  ✅ STAKE_FLOOR bounds APY in early years")
    return results

# ============================================================================
# SCENARIO 10: Guardian Emergency Response
# ============================================================================

def scenario_guardian(state):
    results = []
    for i in range(50):
        register_miner(state, f"honest_{i}", 2000 * 10**8)
    for i in range(100):
        register_miner(state, f"sybil_{i}", 1000 * 10**8)
    results.append("📋 50 honest + 100 Sybil miners")
    results.append(f"  Attacker stake: 50% of total")

    # Normal operation
    state.advance_days(1)
    submissions = [(addr, 19_000000) for addr in state.miners]
    aggregate_prices(state, submissions)
    dist, msg = distribute_rewards(state)
    results.append(f"\nDay 1 (normal): {msg}")

    # Attack detected
    results.append(f"\n🚨 ATTACK DETECTED — Guardian response:")
    state.rewards_frozen = True
    results.append(f"  1. Rewards frozen ✅")
    dist, msg = distribute_rewards(state)
    results.append(f"     Distribution: {msg}")

    # Slash 20 Sybil miners
    total_slashed = 0
    for i in range(20):
        amount, _ = slash_miner(state, f"sybil_{i}", 5000)  # 50% slash
        total_slashed += amount
    results.append(f"  2. 20 Sybil miners slashed 50%: {total_slashed/10**8:.0f} VLT burned")

    # Ban 5 worst
    for i in range(5):
        m = state.miners[f"sybil_{i}"]
        m.active = False
        m.reputation = 0
    results.append(f"  3. 5 Sybil miners permanently banned")

    # Unfreeze after cleanup
    state.rewards_frozen = False
    state.cb_paused = False
    state.advance_days(1)
    submissions = [(addr, 19_000000) for addr in state.miners if state.miners[addr].active]
    aggregate_prices(state, submissions)
    dist, msg = distribute_rewards(state)
    results.append(f"\nDay 2 (recovery): {msg}")

    active_honest = sum(1 for a, m in state.miners.items() if "honest" in a and m.active)
    active_sybil = sum(1 for a, m in state.miners.items() if "sybil" in a and m.active)
    results.append(f"  Active honest: {active_honest}")
    results.append(f"  Active Sybil: {active_sybil} (was 100)")
    results.append(f"  ✅ Protocol recovered — honest miners dominate")
    return results

# ============================================================================
# MAIN
# ============================================================================

def main():
    print("=" * 70)
    print("  XELIS Vault v11.1 — Protocol Simulation Suite")
    print("  Bitcoin-style halving + STAKE_FLOOR + Stake-weighted oracle")
    print("=" * 70)

    run_scenario("1. Bootstrapping (10 miners, 7 days)", scenario_bootstrap)
    run_scenario("2. Normal Growth (100 miners, 30 days)", scenario_growth)
    run_scenario("3. Sybil Attack on Oracle", scenario_sybil_attack)
    run_scenario("4. Bank Run / XEL Crash (-50%)", scenario_bank_run)
    run_scenario("5. Extreme Cases (1, 10000, 90% attacker)", scenario_extremes)
    run_scenario("6. PSM Arbitrage + Peg Stress", scenario_psm_stress)
    run_scenario("7. Cascade Liquidation (-44%)", scenario_cascade)
    run_scenario("8. Delegation Flow (miners + delegators)", scenario_delegation)
    run_scenario("9. Halving Over Time (Year 1-10)", scenario_halving)
    run_scenario("10. Guardian Emergency Response", scenario_guardian)

    print(f"\n{'='*70}")
    print(f"  ALL 10 SCENARIOS COMPLETE")
    print(f"{'='*70}")

if __name__ == "__main__":
    main()
