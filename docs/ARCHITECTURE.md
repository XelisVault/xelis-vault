# XELIS Vault — Architecture

## Directory Structure

```
xelis-vault/
├── contracts/                      # Smart contracts (Silex)
│   ├── vault/
│   │   └── VaultEngine.slx        # Core lending logic
│   ├── oracle/
│   │   └── PriceOracle.slx        # Price feed with timelock
│   ├── interest/
│   │   └── InterestRateModel.slx  # Dynamic interest rates
│   ├── xusd/
│   │   └── xUSD.slx               # Confidential stablecoin
│   ├── insurance/
│   │   └── InsurancePool.slx      # Community insurance
│   ├── flashloan/
│   │   ├── FlashLoan.slx          # Confidential flash loans
│   │   └── FlashCallback.slx      # Reusable flash loan callback
│   ├── governance/
│   │   ├── VLT.slx                # Governance token
│   │   ├── GovernanceVault.slx    # Staking & voting
│   │   ├── Governor.slx           # Proposal & voting engine
│   │   └── Timelock.slx           # Configurable execution delay
│   ├── pools/
│   │   ├── VaultSwap.slx          # Custom AMM + Peg Stability Module
│   │   └── SyndicatePool.slx      # Syndicated credit pools
│   ├── lending/
│   │   ├── LendingMarket.slx      # Multi-pool lending
│   │   └── PeerLoan.slx           # P2P bilateral loans
│   ├── auction/
│   │   └── SealedBidAuction.slx   # Confidential auctions
│   ├── rwa/
│   │   ├── AssetVault.slx         # RWA tokenization standard
│   │   └── TreasuryVault.slx      # Multi-sig treasury
│   ├── compliance/
│   │   └── ComplianceModule.slx   # ZK KYC/AML layer
│   ├── payroll/
│   │   ├── RevenueShare.slx       # Revenue distribution
│   │   └── Payroll.slx            # Recurring payments
│   ├── treasury/
│   │   ├── RevenueShare.slx       # Revenue distribution
│   │   └── TreasuryVault.slx      # Multi-sig treasury
│   ├── savings/
│   │   └── SavingsRate.slx       # xUSD yield savings account
│   └── token/
│       └── VLT.slx                # Governance token
├── sdk/
│   └── src/
│       ├── index.ts               # Main SDK entry
│       ├── vault.ts               # VaultEngine client
│       ├── market.ts              # Marketplace client
│       ├── governance.ts          # Governance client
│       ├── compliance.ts          # Compliance client
│       └── utils.ts               # Utilities
├── dashboard/
│   └── src/
│       ├── App.tsx                # Main React app
│       ├── pages/
│       │   ├── VaultDashboard.tsx  # Vault management
│       │   ├── Marketplace.tsx     # Lending marketplace
│       │   ├── Treasury.tsx        # Treasury management
│       │   ├── Governance.tsx      # Voting & proposals
│       │   ├── Compliance.tsx      # KYC/AML portal
│       │   └── Auctions.tsx        # Auction house
│       ├── components/             # Shared UI components
│       ├── hooks/                  # React hooks
│       └── utils/                  # Utilities
├── cli/
│   └── src/
│       ├── index.ts               # CLI entry point
│       ├── commands/
│       │   ├── vault.ts            # xvault commands
│       │   ├── market.ts           # market commands
│       │   ├── governance.ts       # governance commands
│       │   ├── treasury.ts         # treasury commands
│       │   └── compliance.ts       # compliance commands
│       └── utils.ts
├── bot/
│   └── src/
│       ├── index.ts               # Liquidation keeper bot
│       ├── liquidator.ts           # Core liquidation logic
│       └── scheduled.ts            # Scheduled Executions client
├── scripts/
│   ├── setup-devnet.sh            # Devnet environment setup
│   ├── deploy.sh                  # Core contract deployment
│   └── deploy-full.sh             # Full ecosystem deployment
├── docs/
│   ├── WHITEPAPER.md              # Technical whitepaper
│   ├── ARCHITECTURE.md            # This file
│   └── ROADMAP.md                 # Development roadmap
├── test/
│   ├── vault.test.ts
│   ├── market.test.ts
│   ├── governance.test.ts
│   └── integration.test.ts
├── README.md                      # Project overview
└── package.json                   # Root package
```

## Smart Contract Dependencies

```
VaultSwap
    ├── depends on → PriceOracle (XEL price for PSM)
    ├── depends on → xUSD (mint/burn for PSM)
    ├── manages → xUSD/XEL pool (PSM-enabled)
    └── manages → VLT/XEL pool (standard AMM)

VaultEngine
    ├── depends on → PriceOracle (XEL price data)
    ├── depends on → xUSD (mint/burn)
    ├── depends on → InterestRateModel (rate calculation)
    └── called by → LiquidationBot

LendingMarket
    ├── depends on → PriceOracle
    ├── depends on → xUSD
    ├── depends on → InterestRateModel
    ├── depends on → AssetVault (collateral tokens)
    └── depends on → ComplianceModule (institutional checks)

PeerLoan
    ├── depends on → PriceOracle
    ├── depends on → ComplianceModule (optional)
    └── depends on → Timelock (dispute resolution)

SyndicatePool
    ├── depends on → PriceOracle
    ├── depends on → ComplianceModule
    └── depends on → TreasuryVault (payout routing)

SealedBidAuction
    ├── depends on → AssetVault (any token type)
    └── depends on → ComplianceModule (optional)

AssetVault (standalone template)
    └── can optionally integrate → ComplianceModule

TreasuryVault
    └── depends on → ComplianceModule (signer verification)

GovernanceVault
    ├── depends on → VLT (staking token)
    ├── depends on → Timelock (execution delay)
    └── manages → all protocol parameters

ComplianceModule
    └── called by → any contract requiring KYC/AML checks

InsurancePool
    ├── depends on → VaultEngine (verify vault status)
    └── depends on → xUSD (payouts)

FlashLoan
    └── depends on → liquidity sources
```

## Data Flow

### VaultSwap — AMM with PSM

VaultSwap is a custom AMM (constant product x*y=k) with integrated Peg Stability Module:

```
1. ADD LIQUIDITY
   User → deposit token_a + token_b (or XEL for new pool)
   VaultSwap → create pool (first time) or add to existing
   VaultSwap → mint LP tokens (e.g., "xUSD-XEL VLP")
   Return: LP tokens to user

2. SWAP
   User → deposit token_in
   VaultSwap → 0.3% fee (0.25% to LP, 0.05% to protocol treasury)
   VaultSwap → x*y=k swap
   User ← token_out

3. PSM MINT (xUSD/XEL pool only)
   User → deposit XEL
   VaultSwap → fetch XEL price from PriceOracle
   VaultSwap → 0.5% mint fee to treasury
   VaultSwap → call xUSD.mint_tokens(user, amount) at oracle price
   User ← xUSD at oracle peg

4. PSM REDEEM (xUSD/XEL pool only)
   User → deposit xUSD
   VaultSwap → fetch XEL price from PriceOracle
   VaultSwap → 0.1% redeem fee to treasury
   VaultSwap → call xUSD.burn_tokens(amount)
   VaultSwap → transfer XEL from pool reserves to user
   User ← XEL at oracle peg
```

### Redemption Flow (Peg Support)

```
1. xUSD trades below $1 on Forge DEX
2. Arbitrageur buys xUSD cheap on Forge
3. Calls redeem(amount) on VaultEngine
4. Contract targets vault with lowest CR (≥150%)
5. Redeemer receives XEL collateral at face value
6. Vault owner's debt reduced proportionally
7. xUSD burned → supply decreases → price recovers
```

### Core Lending (VaultEngine)

```
1. DEPOSIT
   User → [XEL] → VaultEngine
   VaultEngine → store encrypted collateral
   VaultEngine → create VaultSnapshot
   Return: vault_id

2. BORROW
   User → call borrow(vault_id, amount)
   VaultEngine → check health (collateral ≥ debt × 1.5)
   VaultEngine → mint xUSD (amount - 0.5% fee)
   VaultEngine → collect 0.5% fee to treasury
   VaultEngine → update encrypted debt
   Return: total_debt

3. REPAY
   User → [xUSD] → VaultEngine
   VaultEngine → burn xUSD
   VaultEngine → update encrypted debt
   Return: remaining_debt

4. WITHDRAW
   User → call withdraw(vault_id, amount)
   VaultEngine → check health (post-withdrawal)
   VaultEngine → [XEL] → User
   VaultEngine → update encrypted collateral
   Return: remaining_collateral
```

### Lending Marketplace

```
1. SUPPLY
   User → [token] → LendingMarket pool
   Position encrypted
   Earn interest based on pool utilization

2. BORROW
   User → borrow from pool against collateral
   Dynamic rate based on pool utilization
   Position encrypted

3. LIQUIDATE
   Keeper → liquidate underwater position
   Collateral transferred at discount
   No identity revealed
```

### Governance

```
1. PROPOSE
   VLT holder → submit parameter change
   → enters Timelock (48h queue)

2. VOTE
   VLT stakers → vote on proposal
   Weighted by stake duration

3. EXECUTE
   After timelock expires → parameter applied
   Guardians can veto during timelock
```

## Privacy Model

| Data | On-Chain | Visibility |
|------|----------|------------|
| Vault owner | Public (Address) | Everyone |
| Collateral amount | Encrypted (Ciphertext) | Owner only |
| Borrow amount | Encrypted (Ciphertext) | Owner only |
| Health factor | Computed (plaintext for VM) | ZK verifiable |
| Peer loan terms | Encrypted | Participants only |
| Syndicate contributions | Encrypted | Participant-only |
| Treasury balances | Encrypted | Authorized signers |
| Auction bids | Encrypted | Bidder only |
| Revenue shares | Encrypted | Recipient only |
| Compliance status | ZK proof | Verifier only |
| Insurance policy | Encrypted | Counterparties only |
| xUSD balance | Encrypted (native) | Owner only |
| Liquidations | Public (event) | Everyone |
| Governance votes | Public | Everyone |

## Integrated Development Environment

### Devnet (Current)

| Component | Address |
|-----------|---------|
| Daemon RPC | `http://127.0.0.1:18081` |
| Wallet RPC | `http://127.0.0.1:18082` |
| Wallet Auth | Basic auth, password: `testpassword` |
| Network | `devnet` |

### Testnet

| Component | Address |
|-----------|---------|
| Daemon RPC | `http://127.0.0.1:18083` |
| Wallet RPC | `http://127.0.0.1:18084` |
| Wallet Auth | Basic auth |
| Network | `testnet` |
| Miner Address | `xet:gtk5tu8ydlh5yr5dcam559mgeuvkg48rllvhhs0tvgrycm7ahytsqd4f27d` |

---

## Deployment Addresses

*To be filled after mainnet deployment*
