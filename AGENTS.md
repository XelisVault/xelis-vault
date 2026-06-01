# XELIS Vault — Agent Knowledge Base

## Silex Language Quick Reference

### Types
- `u8`, `u16`, `u32`, `u64`, `u128`, `u256` — unsigned integers
- `bool`, `string`, `null`
- `T[]` — arrays, `optional<T>` — optional, `map<K,V>` — dictionaries
- `Hash`, `Address`, `Asset`, `Contract`, `Ciphertext`
- `range<T>` — half-open range `[start, end)`
- `struct`, `enum` — user-defined types

### Function Types
- `fn` — regular function
- `entry` — externally callable (main entry point)
- `hook constructor()` — runs once on deploy
- `pub fn` — callable from other contracts (cross-contract)

### Storage API
- `Storage::new()` — read/write own contract storage
- `ReadOnlyStorage::new(contract_hash)` — read another contract's storage
- `.store(key: string, value)`, `.load(key) -> optional<T>`, `.has(key) -> bool`, `.delete(key)`

### Key Globals
- `get_caller() -> optional<Address>` — user who called
- `get_contract_caller() -> optional<Hash>` — calling contract hash
- `get_deposit_for_asset(asset_hash) -> optional<u64>` — deposit in current call
- `get_balance_for_asset(asset_hash) -> optional<u64>` — contract's balance
- `get_deposits() -> map<Hash, u64>` — all deposits in current call
- `get_current_topoheight() -> u64`
- `Block::current().timestamp()`, `.height()`, `.hash()`
- `Transaction::current().hash()`, `.source()`
- `get_contract_hash() -> Hash`

### Asset API
- `Asset::create(id, name, ticker, decimals, max_supply_mode) -> optional<Asset>`
- `Asset::get_by_id(id)`, `Asset::get_by_hash(hash)`
- `.mint(amount)`, `.burn(amount)`, `.get_supply()`, `.get_hash()`, `.get_name()`, `.get_ticker()`, `.is_mintable()`
- `MaxSupplyMode::None`, `MaxSupplyMode::Fixed { max_supply }`, `MaxSupplyMode::Mintable { max_supply }`

### Transfer Functions
- `transfer(destination: Address, amount: u64, asset: Hash) -> bool`
- `transfer_contract(contract: Hash, amount: u64, asset: Hash) -> bool`
- `burn(amount: u64, asset: Hash) -> bool`

### Cross-Contract Calls
- `Contract::new(hash).unwrap().call(entry_id: u16, args: any[], deposits: map<Hash, u64>) -> any`

### Events
- `fire_rpc_event(id: u64, data: any)` — RPC-visible event
- `emit_event(event_id: u64, data: any[])` — contract-to-contract event

### Crypto
- `Hash::blake3(bytes)`, `Hash::sha3(bytes)`, `Hash::from_hex(str)`, `Hash::zero()`
- `Address::from_string(str)`, `.to_string()`, `.to_bytes()`, `.to_point()`

## XELIS-Forge Design Patterns

### Receiver Enum Pattern
Used to support both address and contract recipients:
```
enum Receiver {
    Contract { hash: Hash },
    Address { address: Address }
}
fn safe_transfer(to: Receiver, amount: u64, asset_hash: Hash) {
    match to {
        Receiver::Contract { hash } => transfer_contract(hash, amount, asset_hash),
        Receiver::Address { address } => transfer(address, amount, asset_hash)
    }
}
```

### Balance + Charge Pattern
Track deposits with refund capability:
```
struct Balance { balance: u64, asset: Hash, source: Address }
fn (b Balance) charge(cost: u64, payable: bool) {
    require(cost <= b.balance, "balanceTooLow");
    if payable { /* pay DAO fee */ }
    b.balance -= cost;
}
fn (b Balance) refund() {
    if b.balance > 0 { transfer(b.source, b.balance, b.asset); }
}
```

### Multi-Owner Pattern
```
fn is_owner(addr: Address) -> bool {
    let owners: Address[] = Storage::new().load("owners").unwrap_or([]);
    return owners.contains(addr);
}
```

### ReadOnlyStorage Pattern
Read from other contracts without modifying:
```
let ds: ReadOnlyStorage = ReadOnlyStorage::new(dex_hash).expect("noDexStorage");
let val: optional<u64> = ds.load(some_key);
```

## Contract Architecture

### Storage Key Conventions
- `"a"` — admin address
- `"n"` — auto-increment counter
- Prefix + id — per-record storage (e.g., `"v" + id.to_string(10)`)
- `"oc"` — oracle contract hash
- `"xc"` — xUSD contract hash
- `"xa"` — xUSD asset hash
- `"vc"` — VLT contract hash
- `"va"` — VLT asset hash
- `"tr"` — treasury address

### Cross-Contract Entry ID Table

**PriceOracle (oracle)**
| ID | Entry | Description |
|----|-------|-------------|
| — | `constructor()` | Init (admin = caller), auto-runs on deploy |
| 0 | `propose_price(price)` | Propose new price (admin only) |
| 1 | `execute_price()` | Execute after timelock |
| 2 | `get_price(asset)` | Get active XEL price |
| 3 | `get_pending_price()` | Get pending price |
| 4 | `cancel_pending()` | Cancel pending price |
| 5 | `transfer_admin(new)` | Transfer admin |

**xUSD**
| ID | Entry | Description |
|----|-------|-------------|
| — | `constructor()` | Init (admin = caller), auto-runs on deploy |
| 0 | `create_asset()` | Create XUSD asset (requires 1 XEL deposit) |
| 1 | `mint_tokens(to, amount)` | Mint and transfer xUSD |
| 2 | `burn_tokens(amount)` | Burn xUSD from contract balance |
| 3 | `transfer_tokens(to, amount)` | Transfer xUSD from deposits |
| 4 | `get_asset_hash()` | Get xUSD asset hash |
| 5 | `get_asset_info()` | Get name, ticker, supply |
| 6 | `transfer_admin(new)` | Transfer admin |

**VaultEngine**
| ID | Entry | Description |
|----|-------|-------------|
| 0 | `deposit(collateral, amount)` | Create vault, returns ID |
| 1 | `borrow(vault_id, amount)` | Borrow xUSD against vault |
| 2 | `repay(vault_id, amount)` | Repay xUSD debt |
| 3 | `withdraw(vault_id, amount)` | Withdraw collateral |
| 4 | `redeem(amount)` | Redeem xUSD for XEL |
| 5 | `liquidate(vault_id)` | Liquidate underwater vault |
| 6 | `get_queue()` | Get liquidation queue |
| 7 | `set_oracle_contract(hash)` | Set oracle (admin) |
| 8 | `set_xusd_contract(hash)` | Set xUSD contract (admin) |
| 9 | `set_xusd_asset(hash)` | Set xUSD asset (admin) |
| 10 | `set_treasury(address)` | Set treasury (admin) |
| 11 | `transfer_admin(new)` | Transfer admin (admin) |
| 12 | `get_vault(id)` | Get vault snapshot |
| 13 | `get_health(id)` | Get vault health |
| 14 | `is_liquidatable(id)` | Check if liquidatable |

**VLT**
| ID | Entry | Description |
|----|-------|-------------|
| 0 | `constructor()` | Init (admin = caller) |
| 1 | `create_asset()` | Create VLT asset |
| 2 | `mint(to, amount)` | Mint VLT |
| 3 | `burn_vlt(amount)` | Burn VLT |
| 4 | `transfer_token(to, amount)` | Transfer VLT |
| 5 | `get_asset_hash()` | Get VLT asset hash |
| 6 | `get_supply()` | Get VLT total supply |
| 7 | `transfer_admin(new)` | Transfer admin |

**SavingsRate**
| ID | Entry | Description |
|----|-------|-------------|
| — | `constructor()` | Init (admin = caller, rate = 5%) |
| 0 | `set_rate(rate_bps)` | Set savings rate (admin, max 50%) |
| 1 | `set_xusd_asset(hash)` | Set xUSD asset (admin) |
| 2 | `set_xusd_contract(hash)` | Set xUSD contract (admin) |
| 3 | `deposit()` | Deposit xUSD, earn yield |
| 4 | `withdraw(amount)` | Withdraw xUSD + accrued yield |
| 5 | `get_position(addr)` | Get user position |
| 6 | `get_rate()` | Get current rate |
| 7 | `get_total_deposits()` | Get total deposited |
| 8 | `transfer_admin(new)` | Transfer admin |

**Timelock**
| ID | Entry | Description |
|----|-------|-------------|
| — | `constructor()` | Init (admin = caller, min=720, max=259200) |
| 0 | `submit_proposal(target, entry, param_value, delay)` | Submit timelocked call |
| 1 | `execute_proposal(id)` | Execute after delay |
| 2 | `cancel_proposal(id)` | Cancel (admin only) |
| 3 | `set_min_delay(delay)` | Set min delay (admin, untimelocked) |
| 4 | `set_max_delay(delay)` | Set max delay (admin, untimelocked) |
| 5 | `get_proposal(id)` | Get proposal |
| 6 | `transfer_admin(new)` | Transfer admin |

**GovernanceVault**
| ID | Entry | Description |
|----|-------|-------------|
| — | `constructor()` | Init (admin = caller) |
| 0 | `set_vlt_contract(hash)` | Set VLT contract (admin) |
| 1 | `set_vlt_asset(hash)` | Set VLT asset (admin) |
| 2 | `stake(amount, lock_days)` | Stake VLT for voting power |
| 3 | `unstake(stake_id)` | Unstake after lock period |
| 4 | `get_stake(id)` | Get stake position |
| 5 | `get_total_voting_power()` | Get total voting power |
| 6 | `get_voting_power(id)` | Get stake voting power |
| 7 | `transfer_admin(new)` | Transfer admin |

**PeerLoan**
| ID | Entry | Description |
|----|-------|-------------|
| — | `constructor()` | Init (admin = caller) |
| 0 | `create_loan(borrower, asset, principal, interest_bps, maturity_topo)` | Create peer loan |
| 1 | `repay(loan_id)` | Repay full loan |
| 2 | `default_loan(loan_id)` | Mark loan defaulted (anyone after maturity) |
| 3 | `get_loan(id)` | Get loan info |
| 4 | `transfer_admin(new)` | Transfer admin |

**SyndicatePool**
| ID | Entry | Description |
|----|-------|-------------|
| — | `constructor()` | Init (admin = caller) |
| 0 | `create_pool(name, target_asset, target_amount, min_investment, max_investors)` | Create pool (admin) |
| 1 | `invest(pool_id)` | Invest deposited amount |
| 2 | `close_pool(pool_id)` | Close when target met (manager) |
| 3 | `cancel_pool(pool_id)` | Cancel if target not met (manager) |
| 4 | `refund(pool_id)` | Refund individual investor |
| 5 | `get_pool(id)` | Get pool info |
| 6 | `transfer_admin(new)` | Transfer admin |

**PrivateInsurance**
| ID | Entry | Description |
|----|-------|-------------|
| — | `constructor()` | Init (admin = caller) |
| 0 | `create_pool(name, premium_asset, premium_amount, coverage_asset, coverage_amount, max_members)` | Create pool (admin) |
| 1 | `join_pool(pool_id)` | Join pool, pay premium |
| 2 | `claim_payout(pool_id)` | Claim coverage |
| 3 | `get_pool(id)` | Get pool |
| 4 | `transfer_admin(new)` | Transfer admin |

**InsurancePool** (staking pool)
| ID | Entry | Description |
|----|-------|-------------|
| — | `constructor()` | Init (admin = caller) |
| 0 | `stake(amount)` | Stake XEL, become member |
| 1 | `claim(position_id)` | Unstake XEL |
| 2 | `get_position(id)` | Get stake position |
| 3 | `get_total_staked()` | Get total staked |
| 4 | `is_member(addr)` | Check membership |
| 5 | `transfer_admin(new)` | Transfer admin |

**ComplianceModule**
| ID | Entry | Description |
|----|-------|-------------|
| — | `constructor()` | Init (admin = caller) |
| 0 | `register_user()` | Register (KYC pending) |
| 1 | `approve_kyc(record_id, accredited, jurisdiction, duration_blocks)` | Approve KYC (admin) |
| 2 | `reject_kyc(record_id)` | Reject KYC (admin) |
| 3 | `check_kyc(record_id)` | Check KYC validity |
| 4 | `is_accredited(record_id)` | Check accredited + KYC valid |
| 5 | `get_record(id)` | Get compliance record |
| 6 | `get_record_id_by_address(addr)` | Lookup record by address |
| 7 | `transfer_admin(new)` | Transfer admin |

## Common Pitfalls
1. Entry IDs shift when new entries are added — always recount
2. `burn()` removes from contract balance, not from arbitrary balance
3. `transfer()` returns bool — always check it
4. `get_deposit_for_asset()` only works with deposits in current call
5. Cross-contract calls: `Contract::new(hash).call(id, args, deposits)` — deposits are separate from args
6. Storage keys must be unique per contract — collisions cause bugs
7. `Asset::create(0, ...)` with id=0 works but id must be unique per contract
8. No shadowing by default — use unique variable names
9. `Hash::zero()` = XEL native asset
10. u64 multiplication/division can overflow — cast to u128/u256 for precision math

## Gas Costs (key ones)
- `Storage::store`: ~500 lex + dynamic
- `Storage::load`: ~250 lex
- `transfer()`: 500 lex
- `transfer_contract()`: 250 lex
- `burn()`: 500 lex
- `Asset::mint()`: 1000 lex
- `Asset::create()`: 5000 lex
- `Contract::call()`: 1000 lex + callee gas
- `get_balance_for_asset()`: 25 lex
- `get_deposit_for_asset()`: 5 lex

## Security Rules
1. Always `require(get_deposits().len() == N)` to validate expected deposits
2. Check return values of `transfer()` and `burn()`
3. Validate owner/caller matches in every state-changing entry
4. Check for overflow in arithmetic (use checked_* or higher bit-width casts)
5. Cross-contract calls should be permissioned or validated
6. Timelock all admin parameter changes
7. Handle `optional<T>` returns with `.expect()` or pattern matching
8. Don't use `Hash::zero()` as a valid contract hash
9. Validate deposit amounts > 0
10. Storage keys should use consistent namespace prefixes
