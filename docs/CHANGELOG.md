## [v12R-3 testnet] — 2026-08-24

Canonical-chain redeploy after the 08-22 rollback + fast-sync realignment, with
the critical stock-VM discovery: **any entry returning non-zero has its storage
writes discarded silently** (tx still confirms). All mutating entries now follow
the `return 0` convention; values are exposed via storage keys (`lvid`, `lpc`).

- Redeployed + registry-upgraded: VaultEngineV3 `dcefbd7b…`,
  PrivacyMixer `1ade068c…`, FaucetContract `ed6e2f58…` (chunk maps unchanged).
- VaultChat v12R-2 fix (gm_/gk_ type collision) — suite 17/17.
- CLI write-path E2E (`scripts/test_cli_ops.py`): PSM, Vault Engine V3 full
  cycle, AMM swap, Savings, Mixer auto-mix, Faucet, Miner register/heartbeat —
  14/14 PASS through the exact Backend used by the TUI.
- Canon re-seeded post-fork: PSM XEL reserve, xUSD contract burn reserve,
  VaultSwap XEL/xUSD pool (+liquidity), Faucet refill, admin miner registered.
- xvault CLI: remote-node mode (reads via public node), auto wallet relaunch,
  miner start/stop over wss, registry-resolved contract hashes.

## [v12.1 testnet] — 2026-08-22

Full clean redeploy of v11.7 contracts (phases 1-8, 10-13, Phase 9 skipped).
Addresses & incidents: `docs/DEPLOYMENTS_V12_1.md`. Highlights:

- Oracle pipeline END-TO-END operational: 3 providers submit → aggregate →
  VLT rewards minted via fixed chunk-4 path; reputation rising.
- Config gaps found & fixed during bring-up (now in deploy_v12.py):
  `VLT.set_minter(Miner)`, `Miner.set_treasury(admin)`, MD wiring
  (miner/oracle `set_delegation_contract`).
- Keeper hardening (`scripts/oracle_keeper3.py`): jitter ±1% (spread must
  stay under oracle max_dev 500 bps) + periodic `aggregate_now` poke
  (fixes alreadysub deadlock when every miner submitted before the
  aggregation window opened).

## [v7.1 CLI] — 2026-08-21

### xvault-miner — Zero-config onboarding wizard

- `scripts/onboarding.py` (new): automatic first-run configuration.
  - Wallet: detect running RPC / connect existing / **download official
    xelis_wallet release binary** (Linux/Windows assets auto-matched by OS/arch;
    macOS shows build-from-source steps) / create or import non-interactively.
  - Seeds are generated locally with the exact Xelis mnemonic scheme
    (1626-word English list, 8×(3 words→u32 LE) groups, 25th word = repeat of
    word at crc32(3-char-prefixes)%24; private key reduced to a canonical
    curve25519 scalar). Validated against the official binary end-to-end.
  - Daemon: local node auto-detection, custom URL, or offline mode.
  - Contracts: loaded from new bundled `network/testnet.json` (testnet v12.1
    addresses) — users never type contract addresses again.
  - Miner address read automatically via wallet `get_address`.
- `scripts/xvault-miner.py`: `--setup` and first-run now launch the wizard;
  legacy manual prompts kept as fallback. Stale "contracts not deployed"
  screen removed.
- `scripts/xelis_wordlist_english.txt` (new): Xelis English wordlist.
- `network/testnet.json` (new): bundled contract addresses for the CLI.

## [v11.7] — 2026-08-21

### Security — Cross-contract visibility audit (CRITICAL bug class eliminated)

**Root cause discovered on testnet v12**: `Contract::call(N)` requires the target
chunk to have Access::**All** (`pub fn`). Calling an `Access::Entry` chunk
cross-contract reverts with `Chunk is not public`. Several v11.5 "fixes" had
inverted this rule (converting `pub fn` → `entry` or targeting entry chunks),
silently breaking every flow that relied on them. First symptom: every
`StakedOracle.submit_price` reverted at reward time, blocking price aggregation
and everything downstream.

New tooling:
- `scripts/audit_cross_calls.py` — compiles all contracts, resolves every
  `.call(Nu16)` receiver to its target contract and verifies the on-chain/fresh
  access kind is `all`. Result after fixes: **56 OK / 0 bugs**
  (`docs/cross_call_audit.json`). The 3 remaining sites are GuardianMultisig's
  dynamic `target.call(...)` (proposal-chosen targets — by design; proposals
  MUST reference `pub fn` chunks only).
- `scripts/gen_chunk_map.py` — recompiles the 34 core contracts + AirdropClaim,
  writes `/tmp/deploy_<Name>.hex` and regenerates `docs/entry_chunk_ids.json`
  (now 35 contracts / 1054 Entry+All entries).

#### Fixes (8 call-sites across 7 files)

- **XelisVaultMiner.distribute_reward** — `vlt.call(27)` (mint_to_entry, Entry)
  → **`vlt.call(4)`** (`pub fn mint_to`, All). This was the blocker that killed
  oracle aggregation on v12.
- **AirdropClaim.claim / emergency_withdraw_unclaimed** — same 27→4 fix (2 sites).
- **FlashCallback.on_flash_loan** — reverted the incorrect F-02 v11.5 change:
  back to `pub fn` (All), chunk id unchanged (**2**), FlashLoan-only guard kept.
- **FlashLoan.flash_loan** — `cb.call(8)` (nonexistent chunk) → **`cb.call(2)`**.
- **LendingMarket.update_pool_interest** — IRM entries 3/5 → pub fns
  **15/16** (`get_borrow_rate` / `get_supply_rate`, identical signatures).
- **FeeDistributor.is_authorized_fee_source** — `reg.call(14)` was hitting
  `request_emergency_withdraw`(!) → **`reg.call(17)`** (`pub fn try_get`,
  non-panicking, returns Hash::zero() when missing).
- **PSM** — appended `pub fn mint_cross` (**36**) / `redeem_cross` (**37**) at
  end of file (existing IDs preserved), bodies identical to entries 8/9.
- **VaultSwapV2.psm_mint / psm_redeem** — PSM entries 8/9 → **36/37**.

#### Impact on deployed testnet v12

VLTToken source unchanged → no asset migration needed in principle, but a full
clean redeploy (v12.1) is performed anyway per owner decision, following
docs/DEPLOYMENT_GUIDE.md phases (Phase 9 Insurance still skipped).

---

## [v11.5] — 2026-08-21

### Security — Re-applied 18/18 controlled-disclosure audit fixes (Silex v1.3.0 compatible)

Full audit basis: `XelisVault_v11.3_Controlled_Disclosure (1).pdf` (2026-08-17).
These fixes were originally applied in v11.4 then inadvertently reverted by the
"Silex v1.3.0 API compile fix" commit. They are now re-applied using the real
Silex v1.3.0 chunk IDs (per `docs/entry_chunk_ids.json`) — keeping the Silex
v1.3.0 compatibility work intact.

#### CRITICAL (2/2 fixed)

- **F-01** `airdrop/AirdropClaim.slx` — `emergency_withdraw_unclaimed()` now
  actually transfers the remaining VLT envelope (`TOTAL_DISTRIBUTABLE −
  total_claimed − already_withdrawn`) to `to` via `VLTToken.mint_to_entry`
  (chunk 27, not chunk 4 which is `mint_split`). Added `set_total_distributable`
  admin entry, `WITHDRAWN_KEY` tracking, and 3 read-only getters. Also fixed
  `claim()` to call chunk 27 (was 4 = mint_split / 9 = create_asset).
- **F-02** `flashloan/FlashLoan.slx` + `flashloan/FlashCallback.slx` —
  converted `on_flash_loan` from `pub fn` to `entry` so it gets a real chunk ID
  callable cross-contract (it was missing from `entry_chunk_ids.json`).
  FlashLoan now calls the new chunk ID (8) and uses `transfer_contract(callback_contract, ...)`
  for the principal (was going to the originating caller EOA). Added explicit
  `cc == flash_loan_hash` check inside `on_flash_loan`.

#### HIGH (5/5 fixed)

- **F-03** `amm/VaultSwapV2.slx` — `create_pool()` existence check now uses
  `optional<Pool>` (was `optional<Hash>`) so duplicate pools are detected.
- **F-04** `founder/RevenueShareDelegation.slx` — `only_fee_distributor()`
  now compares `get_contract_caller()` against a stored `FEE_DISTRIBUTOR_KEY`
  hash. Added `set_fee_distributor` admin entry + getter.
- **F-05** `founder/FeeDistributor.slx` — `only_protocol_contract()` now
  resolves the registry and matches the caller against an explicit list of
  10 fee-source contract names. Added `is_authorized_fee_source` helper.
- **F-07** `credit/CreditScore.slx` — `only_authorized_lender()` now resolves
  the registry and matches against the 3 authorized lender names (PeerLoan,
  SyndicatePool, LendingMarket). The stub is gone.
- **F-18r** `chat/VaultChat.slx` — VaultChat was already calling
  `miner.call(23u16, ...)` for distribute_reward (the right pub-fn All chunk ID
  per StakedOracle's own usage). No code change needed — confirmed correct.

#### MEDIUM (8/8 fixed)

- **F-06** `analytics/AnalyticsCollector.slx` — same fix as F-05, against
  an expanded list of 14 protocol contract names.
- **F-08** `amm/VaultSwapV2.slx` — `add_liquidity()` ratio check now accepts
  ±1 tolerance to absorb integer-division truncation (was exact match only).
- **F-09** `amm/VaultSwapV2.slx` — swap circuit breaker now compares
  `new_price` against the TWAP (was `last_price`, which an attacker could
  move with a single large trade).
- **F-10** `amm/VaultSwapV2.slx` — `psm_mint` / `psm_redeem` now delegate
  to `PSM.slx` entries mint/redeem (chunks 8/9) via cross-contract call
  (was reimplementing the math locally). Added `set_psm_contract` admin entry.
- **F-11** `airdrop/AirdropTracker.slx` — `finalize_distribution(start, count)`
  is now paginated/resumable (≤200 users per batch, stored cursor + running
  totals across batches). Was a single unbounded loop.
- **F-12** `airdrop/AirdropTracker.slx` — `get_leaderboard_at_rank(rank)` is
  now O(1) via a precomputed sorted index built once at finalize (was O(n²)).
- **F-13** `chat/VaultChat.slx` — `set_relayer(addr, enabled)` now requires
  the relayer to have staked `MIN_RELAYER_BOND` before enabling.
- **F-14** `founder/FounderVesting.slx` — `claim_founder_tokens()` now
  performs the transfer FIRST and `require(ok, "xferfail")` BEFORE updating
  `CLAIMED_KEY`. Uses native `transfer()` (was `vlt.call(4u16, ...)` = create_asset).

#### LOW (3/3 fixed)

- **F-15** `chat/VaultChat.slx` — explicit `require(count > 0, "underflow")`
  before decrementing the daily free-message counter in `pay_premium_message`.
- **F-16** `chat/VaultChat.slx` — `MAX_BLOB_SIZE = 16384` (16 KB) enforced
  on every message-storing entry: `store_message`, `store_group_message`,
  `store_ephemeral_message`, `send_direct_message`.
- **F-17** `faucet/FaucetContract.slx` — `distribute()` pre-checks the
  faucet's XEL and VLT balances against `addresses.len() * amount` BEFORE
  entering the loop, with `"insfaucetxel"` / `"insfaucetvlt"` errors. Per-iteration
  transfers now use native `transfer()` (was `vlt.call(4u16, ...)` = create_asset)
  and `require(ok, ...)` on the return value.

### Bug fix — PSM.slx mint/redeem (CRITICAL)

The previous PSM `mint` was calling `xusd.call(17u16, [self_hash, net_xusd], {})`
after `s.load("sh")` which **never exists** — reverting every mint. Fixed:
- `mint` now uses `mint_split` (chunk 4): mints `net_xusd + fee`, sends
  `net_xusd` to caller and `fee` to treasury. The XEL deposit stays in PSM
  as XEL reserve for the redeem path.
- `redeem` now requires a **pre-deposit** of xUSD into PSM (symmetric to
  mint's XEL pre-deposit), then burns the deposited xUSD via `burn_tokens`
  (chunk 5). Pre-deposit check + refund of excess added.

### New entries (appended, existing chunk IDs preserved)

- `proxy/ContractRegistry.slx` — `try_get_entry(name: string) -> Hash`
  (non-panicking variant of `get_entry`, returns `Hash::zero()` if missing).
  Used by F-05/F-06/F-07 access-control guards to iterate candidate names
  without reverting.
- `flashloan/FlashCallback.slx` — `on_flash_loan` converted from `pub fn`
  to `entry` (now actually callable cross-contract).
- `airdrop/AirdropClaim.slx` — `set_total_distributable(amount: u64)` admin entry.
- `founder/RevenueShareDelegation.slx` — `set_fee_distributor(fdh: Hash)` admin entry.
- `amm/VaultSwapV2.slx` — `set_psm_contract(psm: Hash)` admin entry.
- `airdrop/AirdropTracker.slx` — `get_leaderboard_count()`,
  `is_leaderboard_ready()` pub fn getters.

### Important — deployment wiring required

After redeploying the modified contracts, the admin MUST:
1. `ContractRegistry.register("VaultSwapV2", ...)`, `register("PSM", ...)`,
   `register("VaultEngineV3", ...)`, `register("FlashLoan", ...)`,
   `register("VaultChat", ...)`, `register("LendingMarket", ...)`,
   `register("PeerLoan", ...)`, `register("SyndicatePool", ...)`,
   `register("InsurancePool", ...)`, `register("SealedBidAuction", ...)`,
   `register("GovernanceVault", ...)`, `register("AirdropTracker", ...)`,
   `register("XelisVaultMiner", ...)`, `register("StakedOracle", ...)`
   — so F-05/F-06/F-07 access-control guards can resolve the protocol
   contracts by name.
2. `RevenueShareDelegation.set_fee_distributor(fdh)` (entry 23) — set the
   canonical FeeDistributor hash.
3. `VaultSwapV2.set_psm_contract(psm)` (new entry, after recompile) — set
   the canonical PSM hash so psm_mint/psm_redeem delegate correctly.
4. `AirdropClaim.set_total_distributable(amount)` (entry 16) if the default
   500 000 VLT envelope is not what you intend.
5. `FlashLoan.verify_callback(callback_contract)` for any contract intending
   to receive flash loans. The contract must implement `entry on_flash_loan`
   at the new chunk ID (8 after recompile of FlashCallback).
6. `AirdropTracker.finalize_distribution(start, count)` — call repeatedly in
   batches of ≤200 until the cursor reaches `user_count`. Then call
   `set_merkle_root(root)` with the off-chain-computed root.

### Re-generate `docs/entry_chunk_ids.json` after recompile

The new entries (on_flash_loan in FlashCallback, try_get_entry in
ContractRegistry, set_total_distributable in AirdropClaim, set_fee_distributor
in RevenueShareDelegation, set_psm_contract in VaultSwapV2, plus the
build_leaderboard_index helper in AirdropTracker) will be appended at the
end of their respective contracts, so existing chunk IDs are preserved.
Run the compile tool to refresh the chunk-id map.

---

## [v11.4] — 2026-08-17 (originally, then inadvertently reverted by v11.5-pre Silex API work)

Re-applied in v11.5 above.

---
