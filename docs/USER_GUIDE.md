# User Guide — XELIS Vault v5.0

> Complete guide for end users of XELIS Vault: lending, swap, governance,
> mixer, chat, flash loans, auctions, savings, insurance.

---

## 1. Introduction

XELIS Vault is a decentralized financial protocol built on the XELIS
BlockDAG. It is composed of 33 Silex contracts that together provide:

- **Lending** (over-collateralized CDP + multi-asset pools)
- **Swap** (constant-product AMM + Peg Stability Module)
- **Governance** (VLT staking with lock boost + timelocked proposals)
- **PrivacyMixer** (ZK-backed anonymity for XEL / VLT / xUSD)
- **VaultChat** (end-to-end-encrypted on-chain anchored chat)
- **FlashLoan** (uncollateralized 1-tx loans, 9 bps fee)
- **SealedBidAuction** (commit/reveal auction for RWA sales)
- **SavingsRate** (xUSD savings, 4 % APR)
- **InsurancePool** (XEL-staked coverage, earns premiums)

All on XELIS — a privacy-first BlockDAG with sub-second finality.

### Privacy on XELIS

XELIS uses Twisted ElGamal confidential transactions. Your **balances** and
**transfer amounts** are encrypted on-chain; only you (with your viewing
key) can decrypt them. The protocol layer (XELIS Vault) inherits this
privacy for VLT, xUSD and all assets minted through the protocol.

---

## 2. Wallet setup

### 2.1 XELIS wallet (CLI)

Recommended for power users and miners.

```bash
# Build from source
git clone https://github.com/xelis-project/xelis-blockchain.git
cd xelis-blockchain && cargo build --release --bin xelis_wallet
sudo cp target/release/xelis_wallet /usr/local/bin/

# Or download a release: https://github.com/xelis-project/xelis-blockchain/releases

# Start with RPC server (needed for the miner / provider scripts)
xelis_wallet --network testnet --rpc-server &

# Attach and create a wallet
xelis_wallet --network testnet
> create-wallet mywallet
> get-address   # → xet1abc...
```

### 2.2 Genesix wallet (GUI)

Recommended for end users. Available for Windows, macOS, Linux at
https://genesix.app. Full XELIS Vault integration (deposit, borrow, swap,
governance, mixer UI) is included.

### 2.3 Hardware wallet

XELIS supports Ledger Nano S/X and Trezor Safe 5 via the
`xelis_wallet --hardware` flag. Use this for large holdings — your mnemonic
never touches a general-purpose computer.

---

## 3. Getting VLT

### Testnet faucet

```bash
xelis_wallet call-contract <FaucetContract> claim_both --signer mywallet
# → 100 XEL (testnet gas) + 200 VLT (more than enough to start)
```

Limits: 24 h cooldown per address, 1,000 XEL / 2,000 VLT lifetime cap.

### Mainnet DEX (VaultSwap)

```bash
# Swap 100 XEL → VLT on VaultSwapV2
xelis_wallet call-contract <VaultSwapV2> swap \
    0x0000000000000000000000000000000000000000000000000000000000000000 \  # XEL
    <VLT_ASSET_HASH> \                                                    # VLT
    10000000000 \                                                         # 100 XEL in
    1000000000 \                                                          # min 10 VLT out
    --signer mywallet \
    --deposit 0x0000...0000 10000000000
```

### OTC

For large amounts, contact the team at `otc@xelisvault.io` for an
over-the-counter trade.

---

## 4. Lending — VaultEngine

`VaultEngineV3` is the over-collateralized CDP engine. Deposit XEL, borrow
xUSD, repay, withdraw.

### 4.1 Deposit XEL collateral

```bash
# Deposit 100 XEL (= 10,000,000,000 atomic) as collateral
xelis_wallet call-contract <VaultEngineV3> deposit \
    0x0000000000000000000000000000000000000000000000000000000000000000 \
    10000000000 \
    --signer mywallet \
    --deposit 0x0000...0000 10000000000
# → creates vault ID 1
```

### 4.2 Borrow xUSD

Max LTV is 50 % (collateral ratio 200 %). At XEL = $0.32, 100 XEL gives
$32 collateral → max borrow $16 xUSD.

```bash
xelis_wallet call-contract <VaultEngineV3> borrow 1 1000000000 --signer mywallet
# Borrow 10 xUSD (minus 0.5 % borrow fee = 9.95 xUSD received)
```

### 4.3 Repay

```bash
xelis_wallet call-contract <VaultEngineV3> repay 1 1000000000 \
    --signer mywallet \
    --deposit <xUSD_ASSET_HASH> 1000000000
# Burns 10 xUSD to clear your debt (plus accrued stability fee)
```

### 4.4 Withdraw collateral

```bash
xelis_wallet call-contract <VaultEngineV3> withdraw 1 5000000000 --signer mywallet
# Withdraw 50 XEL — must keep health factor > 200 %
```

### 4.5 Liquidation

If your health factor drops below 200 % (20,000 bps) for 10 blocks (~50 s),
anyone can call:

```bash
xelis_wallet call-contract <VaultEngineV3> liquidate 1 1000000000 \
    --signer liquidator \
    --deposit <xUSD_ASSET_HASH> 1000000000
# Liquidator repays your debt, receives XEL collateral + 10 % liquidation penalty
```

### 4.6 Stability fee

A per-vault stability fee accrues on every borrow (variable rate set by
governance, default 2 % APR). The fee is charged in xUSD when you repay or
when the vault is liquidated. Check the current rate via the
`VaultEngineV3.get_stability_fee_index` pub fn.

---

## 5. Lending — LendingMarket

`LendingMarket` is a multi-asset interest-rate pool: supply any asset to
earn interest, or borrow against your supplied assets. Uses an
`InterestRateModel` (utilization-based curve).

### 5.1 Supply

```bash
# Supply 1,000 VLT to the VLT pool
xelis_wallet call-contract <LendingMarket> supply \
    <VLT_ASSET_HASH> 100000000000 \
    --signer mywallet \
    --deposit <VLT_ASSET_HASH> 100000000000
# → you receive cVLT (collateral token) representing your share
```

### 5.2 Borrow against collateral

```bash
# Borrow 100 xUSD against your supplied VLT (must keep health factor > 150 %)
xelis_wallet call-contract <LendingMarket> borrow \
    <xUSD_ASSET_HASH> 10000000000 \
    --signer mywallet
```

### 5.3 Repay & withdraw

```bash
# Repay 50 xUSD
xelis_wallet call-contract <LendingMarket> repay \
    <xUSD_ASSET_HASH> 5000000000 \
    --signer mywallet \
    --deposit <xUSD_ASSET_HASH> 5000000000

# Withdraw 500 VLT
xelis_wallet call-contract <LendingMarket> withdraw \
    <VLT_ASSET_HASH> 50000000000 \
    --signer mywallet
```

---

## 6. PSM (Peg Stability Module)

`PSM` is a dedicated contract that mints/redeems xUSD 1:1 at the oracle
XEL/USD price, with a small fee.

### 6.1 Mint xUSD with XEL

```bash
# At XEL = $0.32 (atomic price 32000000):
# 100 XEL → $32 → 31.84 xUSD (after 0.5 % mint fee)
xelis_wallet call-contract <PSM> mint 10000000000 3180000000 \
    --signer mywallet \
    --deposit 0x0000...0000 10000000000
```

### 6.2 Redeem xUSD for XEL

```bash
# 10 xUSD → ~31 XEL (after 0.1 % redeem fee)
xelis_wallet call-contract <PSM> redeem 1000000000 3100000000 \
    --signer mywallet \
    --deposit <xUSD_ASSET_HASH> 1000000000
```

### 6.3 Daily caps

The PSM enforces daily mint/redeem caps (default 1,000,000 xUSD/day each)
to limit oracle attack surface. Check via the `get_daily_usage_entry` (entry
ID 5 on `PSM`).

| Fee                | Default |
|--------------------|---------|
| Mint fee           | 0.5 %   (50 bps) |
| Redeem fee         | 0.1 %   (10 bps) |
| Daily mint cap     | 1,000,000 xUSD |
| Daily redeem cap   | 1,000,000 xUSD |

---

## 7. VaultSwap

`VaultSwapV2` is a constant-product AMM with TWAP-based fees and an
integrated PSM route for xUSD/XEL.

### 7.1 Swap

```bash
# Swap 100 XEL → VLT (min 200 VLT out)
xelis_wallet call-contract <VaultSwapV2> swap \
    0x0000...0000 \
    <VLT_ASSET_HASH> \
    10000000000 \
    20000000000 \
    --signer mywallet \
    --deposit 0x0000...0000 10000000000
```

### 7.2 Add liquidity

```bash
# Create a new pool (XEL/VLT) — first time only
xelis_wallet call-contract <VaultSwapV2> create_pool \
    0x0000...0000 \
    <VLT_ASSET_HASH> \
    false \    # is_psm = false (regular AMM pool)
    --signer mywallet

# Add 100 XEL + 200 VLT as liquidity
xelis_wallet call-contract <VaultSwapV2> add_liquidity \
    0x0000...0000 <VLT_ASSET_HASH> 10000000000 20000000000 0 \
    --signer mywallet \
    --deposit 0x0000...0000 10000000000 \
    --deposit <VLT_ASSET_HASH> 20000000000
```

### 7.3 Fees

- Swap fee: **0.30 %** (30 bps), of which 5 bps goes to the treasury.
- TWAP-based: the fee can be raised during high volatility (governance
  control).

---

## 8. Governance

`GovernanceVault` lets you stake VLT to receive voting power (with a lock
boost up to 2×) and earn staking rewards (Synthetix-style RPT).

### 8.1 Stake VLT

```bash
# Stake 1,000 VLT for 1 year (lock boost = 1.5×)
xelis_wallet call-contract <GovernanceVault> stake 100000000000 31536000 \
    --signer mywallet \
    --deposit <VLT_ASSET_HASH> 100000000000
```

### 8.2 Voting power boost

| Lock duration | Boost |
|---------------|-------|
| 0 (no lock)   | 1.0×  |
| 3 months      | 1.125×|
| 1 year        | 1.5×  |
| 4 years (max) | 2.0×  |

### 8.3 Vote on proposals

`Governor` is the proposal engine. Anyone with ≥ 1 % of voting power can
propose.

```bash
# Vote YES on proposal 7
xelis_wallet call-contract <Governor> vote 7 1 --signer mywallet
# vote_value: 0=against, 1=for, 2=abstain
```

### 8.4 Queue & execute

If a proposal passes, it enters a **timelock** (default 48 h) before
execution.

```bash
# Queue (after vote succeeds)
xelis_wallet call-contract <Governor> queue 7 --signer mywallet

# Execute (after timelock elapses)
xelis_wallet call-contract <Governor> execute 7 --signer mywallet
```

### 8.5 Unstake & claim rewards

```bash
# Unstake (after lock expires)
xelis_wallet call-contract <GovernanceVault> unstake --signer mywallet

# Claim accrued staking rewards
xelis_wallet call-contract <GovernanceVault> claim_rewards --signer mywallet
```

---

## 9. PrivacyMixer

`PrivacyMixer` lets you deposit XEL / VLT / xUSD and later withdraw to a
fresh address using a ZK proof, breaking the on-chain link.

### 9.1 Deposit

```bash
# Deposit 100 XEL into the XEL mixer (denomination = 100 XEL)
xelis_wallet call-contract <PrivacyMixer> deposit \
    0x0000...0000 \         # asset
    10000000000 \           # amount
    <commitment_hash> \     # hash of your secret + nullifier
    --signer mywallet \
    --deposit 0x0000...0000 10000000000
```

`commitment_hash = H(secret, nullifier)`. Generate the secret + nullifier
locally with a cryptographically secure RNG — save them offline.

### 9.2 Withdraw

```bash
# Generate a ZK proof off-chain (use xelis-zk CLI)
xelis-zk prove-withdraw \
    --asset 0x0000...0000 \
    --amount 10000000000 \
    --secret <your_secret> \
    --nullifier <your_nullifier> \
    --recipient xet1fresh... \
    --output proof.json

# Submit the proof on-chain
xelis_wallet call-contract <PrivacyMixer> withdraw \
    0x0000...0000 \
    10000000000 \
    xet1fresh... \
    <merkle_root> \
    <nullifier_hash> \
    <proof_bytes> \
    --signer fresh_wallet
```

The recipient address must be a fresh wallet with no prior history, to
maintain anonymity.

### 9.3 Denominations

The mixer supports fixed denominations per asset (e.g. 1, 10, 100, 1000
XEL). Larger denominations have larger anonymity sets but take longer to
confirm.

---

## 10. VaultChat

`VaultChat` is an end-to-end-encrypted chat with Merkle-root anchoring
on-chain every hour.

### 10.1 Register your chat pubkey

```bash
xelis_wallet call-contract <VaultChat> register_session \
    <your_x25519_pubkey> \
    --signer mywallet
```

### 10.2 Create a group

```bash
xelis_wallet call-contract <VaultChat> create_group \
    "My private group" \
    <merkle_root_of_initial_member_set> \
    --signer mywallet
```

### 10.3 Anchor messages

Messages are stored off-chain by relayers (miners running service ID 2).
Every hour the relayer computes a Merkle root of all messages received and
anchors it on-chain:

```bash
xelis_wallet call-contract <VaultChat> anchor_messages \
    <group_id> \
    <merkle_root> \
    <first_msg_id> \
    <last_msg_id> \
    --signer relayer_wallet
```

The anchor earns the relayer a chat reward (BASE_REWARD_CHAT × reputation ×
budget_factor).

---

## 11. FlashLoan

`FlashLoan` lets you borrow any asset without collateral, as long as you
repay (plus 9 bps fee) **within the same transaction**.

### 11.1 Borrow + repay in one tx

Implement a `FlashCallback` contract that receives the funds, does your
arbitrage / liquidation, and repays. Then:

```bash
xelis_wallet call-contract <FlashLoan> flash_loan \
    <asset> \
    <amount> \
    <your_callback_contract> \
    <callback_data> \
    --signer mywallet
```

The fee is **9 bps** (0.09 %). If your callback doesn't repay in full, the
whole transaction reverts.

---

## 12. SealedBidAuction

`SealedBidAuction` is a commit/reveal auction used for RWA (real-world
asset) sales.

### 12.1 Create auction (seller)

```bash
xelis_wallet call-contract <SealedBidAuction> create_auction \
    <asset> <amount> <min_bid> <commit_phase_end> <reveal_phase_end> \
    --signer seller
```

### 12.2 Commit a bid (bidder)

```bash
# hash(bid_amount, salt) — keep salt secret until reveal
xelis_wallet call-contract <SealedBidAuction> commit_bid \
    <auction_id> <commitment_hash> \
    --signer bidder \
    --deposit <asset> <min_bid>
```

### 12.3 Reveal (bidder)

```bash
xelis_wallet call-contract <SealedBidAuction> reveal_bid \
    <auction_id> <bid_amount> <salt> \
    --signer bidder \
    --deposit <asset> <bid_amount>
```

### 12.4 Settle & claim

After the reveal phase, anyone calls `settle_auction`. The winner receives
the asset; losers get their deposit back.

```bash
xelis_wallet call-contract <SealedBidAuction> settle_auction <auction_id> --signer anyone
xelis_wallet call-contract <SealedBidAuction> claim_asset <auction_id> --signer winner
xelis_wallet call-contract <SealedBidAuction> refund_bid <auction_id> --signer loser
```

---

## 13. SavingsRate

`SavingsRate` pays xUSD holders a fixed 4 % APR, sourced from PSM fees and
VaultEngine stability fees.

### 13.1 Deposit xUSD

```bash
xelis_wallet call-contract <SavingsRate> deposit 100000000000 \
    --signer mywallet \
    --deposit <xUSD_ASSET_HASH> 100000000000
# → 100 xUSD deposited, accrues interest continuously
```

### 13.2 Withdraw

```bash
xelis_wallet call-contract <SavingsRate> withdraw 100000000000 \
    --signer mywallet
# Withdraws your principal + accrued interest
```

The 4 % rate is set by governance via `set_rate` and can be changed
through a Governor proposal.

---

## 14. InsurancePool

`InsurancePool` lets you stake XEL to backstop the protocol against hacks
and bugs. In return you earn premiums (paid in VLT).

### 14.1 Stake

```bash
xelis_wallet call-contract <InsurancePool> stake 10000000000 \
    --signer mywallet \
    --deposit 0x0000...0000 10000000000
# Stake 100 XEL into the insurance pool
```

### 14.2 Earn premiums

Premiums are funded by a portion of VaultEngine liquidation penalties (10
bps per liquidation) and PSM fees. They are distributed pro-rata to stakers
every 2,016 blocks (~1 week).

### 14.3 Unstake

```bash
xelis_wallet call-contract <InsurancePool> unstake 10000000000 --signer mywallet
# Subject to a 7-day withdrawal delay (in case of active payouts)
```

### 14.4 Risk

If a hack is proven (via Governor vote + GuardianMultisig execution), up
to 30 % of the pool can be slashed to compensate victims. Understand this
risk before staking.

---

## 15. FAQ

### Q1. Is my data private on XELIS Vault?
Yes. XELIS uses Twisted ElGamal confidential transactions — your balances
and transfer amounts are encrypted. Only the protocol events (deposits,
borrows, votes) are visible on-chain, and even those are tied to your
address, not your identity. Use PrivacyMixer to break the address link.

### Q2. How is xUSD kept at $1?
Three mechanisms:
1. **PSM** — anyone can mint/redeem xUSD at oracle price ±0.5 % fee.
2. **Over-collateralization** — every xUSD is backed by ≥ $2 of XEL.
3. **Redemption queue** — if xUSD < $1, anyone can burn xUSD and claim
   XEL at face value from `VaultEngineV3`.

### Q3. Can I lose my collateral?
Only if your health factor drops below 200 % for 10+ blocks (~50 s grace
period). Add collateral or repay debt to stay safe.

### Q4. What happens if the oracle goes down?
After 100 blocks (~500 s) without a price update, `get_price` reverts.
Borrowing, withdrawing, and swapping are paused. Existing positions are
safe (no automatic liquidation). The guardian multisig can set a fallback
price.

### Q5. Can I run multiple vaults?
Yes — each `deposit` creates a new vault with a unique ID.

### Q6. How do I get testnet funds?
Claim from the FaucetContract (see §3). Wait 24 h between claims.

### Q7. What's the difference between VaultEngine and LendingMarket?
- **VaultEngine** — CDP: you deposit XEL only, borrow xUSD only.
- **LendingMarket** — multi-asset: supply any asset, borrow any asset
  against your supplied portfolio.

### Q8. Are there gas fees?
Yes — every transaction pays a small XEL fee to the BlockDAG miners. On
testnet this is free (faucet-funded). On mainnet expect ~0.001 XEL per
tx.

### Q9. Can I use a hardware wallet?
Yes — see §2.3.

### Q10. How are rewards taxed?
XELIS Vault is a protocol, not a tax authority. Track your own rewards
(see `get_miner` for miners, or `claim_rewards` history for stakers) and
consult a tax professional.

### Q11. Where do I get help?
- Discord: https://discord.gg/UHpYAWbG — `#support` channel
- Email: `support@xelisvault.io`
- GitHub Issues: https://github.com/XelisVault/xelis-vault/issues
- Documentation: [docs/](.)

---

## 16. References

- [Whitepaper v5.0](WHITEPAPER.md)
- [Architecture / README](../README.md)
- [Entry IDs v5.0](ENTRY_IDS.md) — canonical entry ID list (630 entries)
- [Miner Guide](MINER_GUIDE.md) — if you want to become a miner
- [Provider Guide](PROVIDER_GUIDE.md) — if you want to run a price provider
- [Reward System](REWARD_SYSTEM.md) — full reward math
- [Roadmap](ROADMAP.md)

---

*Last updated: July 2026 — v5.0*
