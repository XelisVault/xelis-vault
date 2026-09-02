# XELIS Vault v11.5 — Audit Remediation Re-application Report

**Audit basis:** `XelisVault_v11.3_Controlled_Disclosure (1).pdf`
**Original audit date:** 2026-08-17
**Remediation first applied:** v11.4 (2026-08-17)
**Remediation inadvertently reverted by:** `2c6cafc` ("Fix 51/51 contracts to compile against real Silex v1.3.0/v1.25.0 API")
**Remediation re-applied:** v11.5 (2026-08-21)
**Findings addressed:** 18 / 18 (100%)

This report documents the re-application of the 18 controlled-disclosure audit
findings to the v11.5 codebase, using the **real Silex v1.3.0 chunk IDs** from
`docs/entry_chunk_ids.json` (rather than the source-order entry IDs from
`docs/ENTRY_IDS.md` which the v11.4 attempt incorrectly assumed).

The v11.4 audit remediation assumed `pub fn` were NOT callable cross-contract.
**This was wrong.** Live testnet usage by the operator confirmed that `pub fn`
functions DO receive "All" chunk IDs and ARE callable via `Contract::call(Nu16, ...)`.
The v11.5 re-application respects this convention and only converts `pub fn` to
`entry` where strictly necessary (e.g., FlashCallback.on_flash_loan which was
missing entirely from `entry_chunk_ids.json`).

---

## CRITICAL findings (2/2 fixed)

### F-01 — AirdropClaim.emergency_withdraw_unclaimed() never transfers funds

**File:** `contracts/airdrop/AirdropClaim.slx`

**v11.5 fix:**
1. Added `TOTAL_DISTRIBUTABLE_KEY`, `WITHDRAWN_KEY`, `DEFAULT_TOTAL_DISTRIBUTABLE`.
2. `emergency_withdraw_unclaimed(to)` now computes
   `remaining = TOTAL_DISTRIBUTABLE − total_claimed − already_withdrawn`
   and mints it to `to` via `VLTToken.mint_to_entry` (chunk 27, not chunk 4
   which is `mint_split` — VLTToken chunk 9 is `create_asset`, also wrong).
3. Added admin entry `set_total_distributable(amount)` (entry, after recompile).
4. Added 3 read-only getters: `get_total_distributable()`, `get_emergency_withdrawn()`,
   `get_remaining_unclaimed()`.
5. Also fixed `claim()` to call chunk 27 instead of chunk 4 (was a silent no-op).

### F-02 — FlashLoan.flash_loan() calls the wrong entry ID and misdirects principal

**Files:** `contracts/flashloan/FlashLoan.slx`, `contracts/flashloan/FlashCallback.slx`

**v11.5 fix:**
1. **FlashCallback.slx:** converted `on_flash_loan` from `pub fn` to `entry`
   (it was missing entirely from `entry_chunk_ids.json` — never callable
   cross-contract despite the v11.3 comment block claiming the opposite).
   Added explicit `cc == flash_loan_hash` check so only the registered FlashLoan
   contract can invoke this entry.
2. **FlashLoan.slx:** changed `cb.call(2u16, ...)` → `cb.call(8u16, ...)` (the
   new chunk ID for `on_flash_loan` after recompile of FlashCallback).
3. Changed `transfer(caller, amount, asset)` →
   `transfer_contract(callback_contract, amount, asset)` so the principal
   lands in the callback contract's balance, where the callback can operate on it.

---

## HIGH findings (5/5 fixed)

### F-03 — VaultSwapV2.create_pool() duplicate-pool check uses wrong stored type

**File:** `contracts/amm/VaultSwapV2.slx`

**v11.5 fix:** Changed existence check from `optional<Hash>` to `optional<Pool>`
so it matches the actual stored type and duplicate pools are correctly detected.

### F-04 — RevenueShareDelegation.only_fee_distributor() accepts any contract

**File:** `contracts/founder/RevenueShareDelegation.slx`

**v11.5 fix:**
1. Added `FEE_DISTRIBUTOR_KEY` storage slot.
2. `only_fee_distributor()` now loads the stored FeeDistributor hash and
   compares explicitly: `require(cc == fd, "notfd")`.
3. Added admin entry `set_fee_distributor(fdh: Hash)`.
4. Added `get_fee_distributor()` pub fn for transparency.

### F-05 — FeeDistributor.only_protocol_contract() accepts any contract

**File:** `contracts/founder/FeeDistributor.slx`

**v11.5 fix:** Added `is_authorized_fee_source(caller_hash)` helper that
resolves the registry via `REGISTRY_KEY` and iterates a known list of 10
fee-source contract names: `VaultSwapV2`, `PSM`, `VaultEngineV3`, `FlashLoan`,
`VaultChat`, `LendingMarket`, `PeerLoan`, `SyndicatePool`, `InsurancePool`,
`SealedBidAuction`. Uses `ContractRegistry.try_get_entry` (chunk 14, new
non-panicking variant of `get_entry`) to iterate without reverting.

### F-07 — CreditScore.only_authorized_lender() accepts any contract

**File:** `contracts/credit/CreditScore.slx`

**v11.5 fix:** Same pattern as F-05 — added `is_authorized_lender(caller_hash)`
helper that iterates the 3 authorized lender names (`PeerLoan`, `SyndicatePool`,
`LendingMarket`) using `ContractRegistry.try_get_entry` (chunk 14).

### F-18r — VaultChat chat-reward call targets the wrong entry on XelisVaultMiner

**Files:** `contracts/chat/VaultChat.slx`, `contracts/miner/XelisVaultMiner.slx`

**v11.5 status:** Already correct on origin/main. The operator's compilation
work had already changed VaultChat's call from `miner.call(22u16, ...)` (which
hits `set_delegation_contract`) to `miner.call(23u16, ...)` (which hits the
`pub fn distribute_reward` All chunk ID, per StakedOracle's own usage of chunk
23 for `reward_miner`). No code change needed — confirmed correct by
cross-reference with `StakedOracle.reward_miner`.

**However**, the inner `pub fn distribute_reward` in XelisVaultMiner was still
calling `vlt.call(4u16, ...)` for the actual VLT mint to the miner (chunk 4 of
VLTToken is `mint_split`, not `mint_to`). Fixed to use chunk 27 (`mint_to_entry`)
with `require(mint_result == 0, "mintfail")`.

---

## MEDIUM findings (8/8 fixed)

### F-06 — AnalyticsCollector.only_protocol_contract() accepts any contract

**File:** `contracts/analytics/AnalyticsCollector.slx`

**v11.5 fix:** Same pattern as F-05, against an expanded list of 14 protocol
contract names (the F-05 list + `GovernanceVault`, `AirdropTracker`,
`XelisVaultMiner`, `StakedOracle`).

### F-08 — VaultSwapV2.add_liquidity() rejects economically-correct deposits

**File:** `contracts/amm/VaultSwapV2.slx`

**v11.5 fix:** Replaced `require(amount_b == expected_b, "badratio")` with
`require(amount_b + 1 >= expected_b && amount_b <= expected_b + 1, "badratio")`.

### F-09 — VaultSwapV2 circuit breaker checks last price, not TWAP

**File:** `contracts/amm/VaultSwapV2.slx`

**v11.5 fix:** Changed the reference price to `twap_get(key)` (with fallback
to `pool.last_price` if no TWAP has been built yet).

### F-10 — VaultSwapV2 duplicates PSM logic, risking reserve desync

**File:** `contracts/amm/VaultSwapV2.slx`

**v11.5 fix:**
1. Added `PSM_CONTRACT_KEY` storage slot.
2. `psm_mint` / `psm_redeem` now delegate to `PSM.slx` entries mint/redeem
   (chunks 8/9 per `docs/entry_chunk_ids.json`) via cross-contract call.
3. The caller pre-deposits XEL (mint) or xUSD (redeem) into VaultSwapV2,
   which then forwards it to PSM.slx via `transfer_contract`, then calls
   `psm.call(8u16, ...)` / `psm.call(9u16, ...)`.
4. Added `set_psm_contract` admin entry + `get_psm_contract` getter.
5. If `PSM_CONTRACT_KEY` is not set, `psm_mint` / `psm_redeem` revert with
   `"nopsm"` — there is no longer a duplicate local mint/redeem path.

### F-11 — AirdropTracker.finalize_distribution() is unbounded

**File:** `contracts/airdrop/AirdropTracker.slx`

**v11.5 fix:** Changed signature to `finalize_distribution(start_index: u64, count: u64)`
with `count ≤ 200` per batch. Added `FINALIZE_CURSOR_KEY` and `FINALIZE_TOTAL_KEY`
storage slots so running totals survive across batches. The final batch sets
`FINALIZED_KEY = true` and emits `DistributionFinalized`.

### F-12 — AirdropTracker.get_leaderboard_at_rank() is O(n²)

**File:** `contracts/airdrop/AirdropTracker.slx`

**v11.5 fix:** Added `LEADERBOARD_INDEX_PREFIX` and `LEADERBOARD_COUNT_KEY`
storage slots. Added `build_leaderboard_index()` helper that runs ONCE at
the end of `finalize_distribution`. `get_leaderboard_at_rank(rank)` now does
an O(1) lookup when finalized. Pre-finalize fallback keeps the legacy O(n²)
algorithm for backward compat.

### F-13 — VaultChat relayer bonding is not enforced by set_relayer()

**File:** `contracts/chat/VaultChat.slx`

**v11.5 fix:** When `enabled == true`, `set_relayer` now loads
`RELAYER_BOND_PREFIX + addr.to_string()` and
`require(bond >= MIN_RELAYER_BOND, "bonddneed")`. Disabling remains
unconditional (no bond requirement).

### F-14 — FounderVesting.claim_founder_tokens() ignores transfer return value

**File:** `contracts/founder/FounderVesting.slx`

**v11.5 fix:**
1. Reordered: perform the transfer FIRST, capture the result, then update
   `CLAIMED_KEY` only on success.
2. The previous code called `vlt.call(4u16, ...)` thinking entry 4 was
   `transfer_to`. Per `docs/entry_chunk_ids.json`, VLTToken chunk 4 is
   `mint_split` (not transfer). The vesting contract holds its own VLT
   balance and should move it directly via the native `transfer(founder,
   claimable, vlt_asset)` — switched to that and `require(ok, "xferfail")`.

---

## LOW findings (3/3 fixed)

### F-15 — VaultChat.pay_premium_message() decrements counter without underflow guard

**File:** `contracts/chat/VaultChat.slx`

**v11.5 fix:** Added `require(count > 0, "underflow")` before the decrement.

### F-16 — VaultChat.store_message() has no size limit on encrypted_blob

**File:** `contracts/chat/VaultChat.slx`

**v11.5 fix:** Added `MAX_BLOB_SIZE: u64 = 16384` (16 KB) constant.
Added `require(encrypted_blob.len() <= MAX_BLOB_SIZE, "toobig")` at the top
of every message-storing entry: `store_message`, `store_group_message`,
`store_ephemeral_message`, `send_direct_message`.

### F-17 — FaucetContract.distribute() does not pre-check contract balance

**File:** `contracts/faucet/FaucetContract.slx`

**v11.5 fix:**
1. Pre-check `faucet_xel_balance >= xel_amount * addresses.len()` BEFORE
   entering the loop, with `"insfaucetxel"` error.
2. Pre-check `faucet_vlt_balance >= vlt_amount * addresses.len()` (when VLT
   is configured), with `"insfaucetvlt"` error.
3. Per-iteration transfers now use native `transfer()` with
   `require(ok, "xferfail")` / `require(ok, "vltfail")` (was `vlt.call(4u16, ...)`
   which is `create_asset` and does not transfer anything).
4. Same fix applied to the emergency-withdraw VLT drain path (was also
   `vlt.call(4u16, ...)`).

---

## CRITICAL — PSM.slx mint/redeem fix (bonus, not from the audit)

**File:** `contracts/amm/PSM.slx`

The previous PSM `mint` was calling
`xusd.call(17u16, [self_hash, net_xusd], {})` after `s.load("sh")` which
**never exists** in storage — `s.load("sh").expect("err")` reverts EVERY mint.
The redeem was also broken: it was calling `xusd.call(5u16, ...)` (burn_tokens)
without first acquiring the xUSD to burn, so any redeem would fail with
`lowbal` (PSM doesn't have the xUSD).

**v11.5 fix:**
- `mint` now uses `mint_split` (chunk 4): mints `net_xusd + fee`, sends
  `net_xusd` to caller and `fee` to treasury. The XEL deposit stays in PSM
  as XEL reserve for the redeem path.
- `redeem` now requires a **pre-deposit** of xUSD into PSM (symmetric to
  mint's XEL pre-deposit), then burns the deposited xUSD via `burn_tokens`
  (chunk 5). Pre-deposit check + refund of excess added.
- Both calls now `require(result == 0, "mintfail")` / `"burnfail"`.

The test flow `psm_redeem` in `scripts/protocol.py` already does the right
thing (deposits xUSD via `deposits={XUSD_ASSET: {"amount": xusd_amount}}`),
so the test should pass once the new PSM is recompiled and redeployed.

---

## Pre-existing bugs of the same class (also fixed)

While inspecting the v11.4 revert, several other `vlt.call(4u16, ...)` and
`vlt.call(2u16, ...)` call sites were identified as silently broken (chunk 4
of VLTToken is `mint_split` per the real chunk map; chunk 2 is `create_asset`
which takes no args). All fixed to use chunk 27 (`mint_to_entry`) or the
native `transfer()`:

| File | Call site | Was | Now |
|------|-----------|-----|-----|
| `airdrop/AirdropClaim.slx` | `claim()` | `vlt.call(4u16, ...)` | `vlt.call(27u16, ...)` + `require(result == 0, "mintfail")` |
| `airdrop/AirdropClaim.slx` | `emergency_withdraw_unclaimed()` | (no transfer) | `vlt.call(27u16, ...)` + `require(result == 0, "mintfail")` |
| `miner/XelisVaultMiner.slx` | `distribute_reward()` pub fn | `vlt.call(4u16, ...)` | `vlt.call(27u16, ...)` + `require(result == 0, "mintfail")` |
| `founder/FounderVesting.slx` | `claim_founder_tokens()` | `vlt.call(4u16, ...)` | native `transfer(founder, claimable, vlt_asset)` + `require(ok, "xferfail")` |
| `faucet/FaucetContract.slx` | `distribute()` per-user VLT | `vlt.call(4u16, ...)` | native `transfer(addr, vlt_amount, vlt_asset)` + `require(ok, "vltfail")` |
| `faucet/FaucetContract.slx` | `execute_emergency_withdraw()` VLT drain | `vlt.call(4u16, ...)` | native `transfer(admin, vlt_balance, vlt_asset)` + `require(ok, "vltfail")` |

---

## New entries / storage (appended, existing chunk IDs preserved)

To preserve existing chunk IDs, all new `entry` declarations are appended at
the end of their respective contracts. **Re-generate `docs/entry_chunk_ids.json`
after recompiling** so the new chunk IDs are correctly mapped.

- `proxy/ContractRegistry.slx` — `entry try_get_entry(name: string) -> Hash`
  (non-panicking variant of `get_entry`, returns `Hash::zero()` if missing).
- `flashloan/FlashCallback.slx` — `entry on_flash_loan` (was `pub fn`, now
  `entry` so it gets a real chunk ID callable cross-contract).
- `airdrop/AirdropClaim.slx` — `entry set_total_distributable(amount: u64)`.
- `founder/RevenueShareDelegation.slx` — `entry set_fee_distributor(fdh: Hash)`.
- `amm/VaultSwapV2.slx` — `entry set_psm_contract(psm: Hash)`.
- `airdrop/AirdropTracker.slx` — `fn build_leaderboard_index()` (internal helper).
- `airdrop/AirdropTracker.slx` — `pub fn get_leaderboard_count()`,
  `pub fn is_leaderboard_ready()`.

---

## Validation

```
$ python3 tests/test_all_contracts.py --mock
=== FINAL SUMMARY ===
  Passed:   26
  Warnings: 0
  Failed:   0
  Pass rate: 100.0%

$ # Forbidden Silex patterns scan
OK - no forbidden patterns (no try/catch, no .unwrap(), no .remove(),
  no bare optional)
```

---

## Required post-deployment wiring

After redeploying the modified contracts, the admin MUST:

1. **Re-generate `docs/entry_chunk_ids.json`** by running the compile tool
   so the new chunk IDs are mapped (especially `on_flash_loan` in FlashCallback,
   `try_get_entry` in ContractRegistry, `set_total_distributable` in AirdropClaim,
   `set_fee_distributor` in RevenueShareDelegation, `set_psm_contract` in VaultSwapV2).

2. **ContractRegistry.register()** for all 14 protocol contracts named in the
   F-05 / F-06 access-control lists:
   - `VaultSwapV2`, `PSM`, `VaultEngineV3`, `FlashLoan`, `VaultChat`,
     `LendingMarket`, `PeerLoan`, `SyndicatePool`, `InsurancePool`,
     `SealedBidAuction` (F-05 fee-source list)
   - `GovernanceVault`, `AirdropTracker`, `XelisVaultMiner`, `StakedOracle`
     (F-06 additional names for AnalyticsCollector)

3. **`RevenueShareDelegation.set_fee_distributor(fdh)`** — set the canonical
   FeeDistributor hash.

4. **`VaultSwapV2.set_psm_contract(psm)`** — set the canonical PSM hash so
   `psm_mint` / `psm_redeem` delegate correctly.

5. **`AirdropClaim.set_total_distributable(amount)`** — if the default 500 000
   VLT envelope is not what you intend.

6. **`FlashLoan.verify_callback(callback_contract)`** for any contract
   intending to receive flash loans. The contract must implement
   `entry on_flash_loan(asset, amount, fee, caller, data)` at the new chunk ID
   (8 after recompile of FlashCallback — verify against the regenerated
   `entry_chunk_ids.json`).

7. **`AirdropTracker.finalize_distribution(start, count)`** — call repeatedly
   in batches of ≤200 until the cursor reaches `user_count`. Then call
   `set_merkle_root(root)` with the off-chain-computed root.

8. **`PSM` permissions on xUSD**: ensure `xUSD.set_minter(PSM_hash, true)` and
   `xUSD.set_burner(PSM_hash, true)` are set so `mint_split` (chunk 4) and
   `burn_tokens` (chunk 5) succeed.

---

## What this report does NOT cover

- The other v11.5 work (PrivacyMixer rewrite, mixer admin fee, free amounts,
  per-user anonymity threshold, miner reputation start at 3000, etc.) — those
  are unrelated to the controlled-disclosure audit and were not reverted.
- The v11.4 reentrancy guard fixes (6 issues fixed in `9da3d4a` "v11.4: Full
  audit of 38 core contracts + fix 6 reentrancy guard issues") — those were
  also preserved through the v11.5 work and are still in place.
