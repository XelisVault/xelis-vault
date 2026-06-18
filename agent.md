# XELIS Vault v4.2 — Agent Knowledge Base

## Project Overview
XELIS Vault is a confidential DeFi platform on the XELIS BlockDAG. 29 Silex contracts across 12 categories (token, oracle, governance, lending, AMM/P SM, savings, flash loans, auctions, RWA, treasury/insurance/compliance, testnet, infrastructure).

## Architecture Decisions

### Oracle: StakedOracle (permissionless)
- Anyone can become a price provider by staking 100 VLT (MIN_STAKE)
- Median aggregation every 5 blocks (25s), 256 submissions max per cycle
- Slashing: 1% of stake per outlier (50% burned, 50% treasury)
- Circuit breaker at 20% price deviation from previous
- Hard stale: `get_price()` reverts if no update for >100 blocks (~500s)
- Providers tracked via PROVIDER_PREFIX + address, iterable via PROVIDER_LIST_PREFIX + index
- Rewards: REWARD_PER_CYCLE = 0.48 VLT (47,564,687 atomic), 6M VLT budget over 10 years
- Feed management via OracleGovernance (add/update/remove, set params)

### VLT Token Economics
- Fixed supply: 10,000,000 VLT (1,000,000,000,000,000 atomic)
- Distribution: 60% oracle rewards, 15% team (4yr vest/1yr cliff), 12% treasury, 10% DEX liquidity, 2% airdrop, 1% bug bounty
- No investor allocation — community-driven
- Deflationary via 3 burn mechanisms: 50% protocol fees, 50% slashing, governance burn (quorum 15%)
- Projected: supply divided by 3 in 10 years (~3M VLT)
- Minter/burner pattern via `set_minter()` / `set_burner()` (contract authorization, not hardcoded keys)

### xUSD Stablecoin
- Peg mechanisms: PSM (mint/redeem at oracle price), overcollateralization (MCR 200%), redemption queue
- Unlimited max supply (backed by XEL collateral)
- Minter/burner authorization pattern (flexible, not hardcoded addresses)
- Entry IDs: create_asset=0, mint_tokens=1, mint_split=2, burn_tokens=3, transfer_tokens=4, get_asset_hash=5, get_asset_info=6, set_minter=7, set_burner=8

### Upgrade Pattern
- No delegatecall in Silex → Versioned Registry pattern via ContractRegistry
- All contracts resolve dependencies at runtime via `ContractRegistry.get(name)`
- Upgrade: deploy new → propose via Timelock (48h) → execute → `migrate_from(old_hash)`
- Rollback via `ContractRegistry.rollback(name)` (preserves previous hash)
- Cooldown 720 blocks (~1h) between same-contract upgrades

### Confidentiality (VaultEngineV3)
- Uses `Ciphertext` type (Twisted ElGamal) for encrypted collateral/debt
- Homomorphic operations: `.add()`, `.sub()` without decryption
- Grace period: 10 blocks (~50s) before liquidation
- MCR: 200%, Liquidation penalty: 10%

### VaultSwap V2 (AMM + PSM)
- Constant product AMM (x*y=k) with MEV protection
- Mandatory slippage: `min_amount_out` required
- Flash loan resistance: max 5% of pool per swap
- Per-pool circuit breaker at 10% price movement
- Dynamic fees: 0.3% normal, 1% high volatility
- PSM is a separate contract (not embedded in AMM) for isolation
- PSM mint fee: 0.5%, redeem fee: 0.1%

## Silex Language Notes
- Dynamic arrays `T[]` with `.push()`, `.len()`, index access `T[i]`
- NO fixed-size `[T; N]` or initializer syntax `[0; N]`
- Types: u8/u16/u32/u64/u128/u256/bool/string/struct/enum/optional/map/bytes
- `struct` for complex types, stored in storage via `s.store(key, value)`
- `hook constructor()` for initialization
- `entry` for callable functions, `fn` for internal, `pub fn` for read-only external
- `Contract::call(entry_id: u16, args: [], kwargs: {})` for inter-contract calls
- `optional` type with `.is_some()`, `.unwrap()`, `.unwrap_or(default)`
- `Asset::create(max_supply, name, ticker, decimals, MaxSupplyMode::None)`
- `get_caller()` returns original transaction sender (wallet), NOT calling contract
- `get_contract_caller()` returns calling contract's hash
- `Hash::zero()` for native XEL
- Must check `get_deposit_for_asset(hash)` when expecting deposits
- `asset.mint(amount)` returns bool, `burn(amount, hash)` returns bool
- `transfer(to, amount, asset_hash)` for sending assets

## Bugs Identified & Fixed (Audit)
1. Fixed-size arrays `[T; N]` → dynamic `T[]` (Silex doesn't support fixed)
2. `burn_from()` cross-account → StakedOracle handles burn directly
3. Phantom loop in `aggregate()` collecting nothing
4. Extra parenthesis in deviation calculation
5. xUSD burn entry ID mismatch (VaultEngine/VaultSwap called ID 4 instead of 3)
6. Entry ID alignment between OracleGovernance and StakedOracle
7. "MinerOracle" → "StakedOracle" in VaultEngine's get_oracle()

## Key Testnet Learnings
- Entry IDs = 0-based chunk index; hook=0, internal=1, entry chunks start at 2
- `get_caller()` always returns original tx sender (wallet), not calling contract
- `mint_tokens` returning u64 leaves stack value → VaultEngine fails with "stack not cleaned"
- Solution: xUSD mint_tokens must return void (no `return 0;`) when called via Contract::call()
- Oracle v2 uses `pub fn get_price(asset: Hash) -> u64` as chunk type "all"

## Scripts
- `price_provider.py`: sources = MEXC + CoinEx (default), custom sources via JSON
  `--list-sources`, `--test-sources`, `--add-source`, `--remove-source`, `--show-config`
- `aggregation_keeper.py`: calls `aggregate_now()` per block, 5s poll interval
- `deploy_testnet.py`: automated deployment wiring + VLT distribution
- `test_all_contracts.py`: connection, syntax, cross-contract consistency, price APIs, economics, fees

## Price Sources (June 2026)
- MEXC (api.mexc.com): ~20 req/s, 40-120ms latency
- CoinEx (api.coinex.com/v2): ~30 req/s, 80-90ms latency
- CoinGecko: 30/min rate limit (disabled by default for >50 providers)
- CoinMarketCap: requires API key (optional fallback)
- Binance/Gate.io/Kraken: XEL not listed

## Fees Structure
- PSM mint: 0.5%, redeem: 0.1%
- VaultSwap: 0.3% (0.25% LPs + 0.05% treasury), 1% high volatility
- VaultEngine borrow: 0.5% protocol + 0.1% insurance, redemption: 0.5%, liquidation: 10%
- PeerLoan: 0.1%, SyndicatePool: 0.5%, SealedBidAuction: 1%, FlashLoan: 0.09%
- 50% of treasury's fee share is burned

## Validated with XELIS-Forge (7 points)
1. Ciphertext API: encrypt/decrypt/add/sub/zero — needs confirmation
2. Asset::create signature: needs confirmation
3. Dynamic arrays (T[].push, .len, T[i]) — assumed supported
4. Contract::call(entry_id, args, kwargs) — needs mixed-type args confirmation
5. Hash::to_address() — needs confirmation
6. hash() native function — needs confirmation
7. burn(amount, asset) — native burn from contract balance

## File Organization
```
contracts/
  amm/         VaultSwapV2.slx, PSM.slx
  auction/     SealedBidAuction.slx
  compliance/  ComplianceModule.slx
  faucet/      FaucetContract.slx
  flashloan/   FlashLoan.slx, FlashCallback.slx
  governance/  OracleGovernance.slx, GovernanceVault.slx, Governor.slx, Timelock.slx, GuardianMultisig.slx
  insurance/   InsurancePool.slx, PrivateInsurance.slx
  interest/    InterestRateModel.slx
  lending/     LendingMarket.slx, PeerLoan.slx, SyndicatePool.slx
  oracle/      StakedOracle.slx
  payroll/     Payroll.slx
  proxy/       ContractRegistry.slx, Upgradeable.slx
  revenue/     RevenueShare.slx
  rwa/         AssetVault.slx
  savings/     SavingsRate.slx
  token/       VLTToken.slx
  treasury/    TreasuryVault.slx
  usd/         xUSD.slx
  vault/       VaultEngineV3.slx
scripts/       price_provider.py, aggregation_keeper.py, custom_sources.example.json
deploy/        deploy_testnet.py
tests/         test_all_contracts.py
docs/          10 markdown files (ARCHITECTURE, AUDIT, COMPATIBILITY_TABLE, MINER_GUIDE,
               PROVIDER_GUIDE, ROADMAP, TESTNET_DEPLOYMENT, UPGRADE, USER_GUIDE, WHITEPAPER)
```
