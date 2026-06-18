# User Guide — XELIS Vault v4.2

> Complete guide for end users of XELIS Vault (deposit, borrow, swap).

---

## Prerequisites

### Option 1: Use the Installer (recommended)

```bash
# Linux / macOS
curl -fsSL https://raw.githubusercontent.com/XelisVault/xelis-vault/main/install.py | python3

# Windows PowerShell
iwr -useb https://raw.githubusercontent.com/XelisVault/xelis-vault/main/install.py | python
```

The installer handles everything automatically.

### Option 2: Manual Setup

1. Install XELIS daemon + wallet (see https://docs.xelis.io)
2. Sync daemon on testnet: `xelis_daemon --network testnet`
3. Create wallet: `xelis_wallet --network testnet`
4. Continue with this guide

---

## Step 1: Get Testnet Funds from Faucet

The Faucet contract distributes free testnet funds to anyone:

- **100 XEL testnet** per 24h (enough for ~1000 transactions)
- **200 VLT** per 24h (enough to stake as provider)

### Claim via Wallet CLI

```bash
xelis_wallet --network testnet

# Check if faucet is configured
> call-contract <FaucetContract> get_faucet_info
# Returns: (claim_xel_amount, claim_vlt_amount, cooldown, daily_caps, ...)

# Claim both XEL and VLT in one transaction
> call-contract <FaucetContract> claim_both --signer mywallet

# Or claim separately
> call-contract <FaucetContract> claim_xel --signer mywallet
> call-contract <FaucetContract> claim_vlt --signer mywallet

# Check your claim history
> call-contract <FaucetContract> get_user_claims xet1abc...
# Returns: (last_xel_claim, last_vlt_claim, total_xel_claimed, total_vlt_claimed)
```

### Faucet Limits (Anti-Abuse)

| Limit | Value | Purpose |
|-------|-------|---------|
| Cooldown per address | 24 hours | Prevent spam claims |
| Daily cap (total) | 5000 XEL / 10000 VLT | 50 users/day max |
| Lifetime cap per address | 1000 XEL / 2000 VLT | Prevent one user draining faucet |
| Pause | Guardian can pause | Emergency stop |

If you hit a limit, the contract reverts with a clear error message:
- `"cooldown"` — wait 24h since your last claim
- `"dailycap"` — daily cap reached, wait for reset (24h)
- `"lifetimecap"` — you've claimed your lifetime max
- `"faucetempty"` — faucet needs refill (admin will refill)

---

## Step 2: Check Your Balances

```bash
xelis_wallet --network testnet

# Check XEL balance
> get-balance

# Check all asset balances (XEL, VLT, xUSD)
> get-balances
```

---

## Step 3: Deposit XEL as Collateral

To borrow xUSD, you need to deposit XEL as collateral first.

```bash
# Check current XEL price from oracle
> call-contract <StakedOracle> get_price "XEL/USD"
# Returns: 32000000 (= $0.32 in 8-decimals atomic)

# Deposit 100 XEL as collateral (100 XEL = 10,000,000,000 atomic)
> call-contract <VaultEngine> deposit \
    0x0000000000000000000000000000000000000000000000000000000000000000 \
    10000000000 \
    --signer mywallet \
    --deposit 0x0000000000000000000000000000000000000000000000000000000000000000 10000000000

# Your deposit creates a vault with ID 1 (or higher)
# You can check your vault:
> call-contract <VaultEngine> get_health_factor 1
# Returns health factor in bps (10000 = 1.0x). Should be u64::MAX (no debt yet)
```

---

## Step 4: Borrow xUSD

Once you have collateral, you can borrow xUSD up to 50% of your collateral value.

```bash
# Collateral: 100 XEL @ $0.32 = $32
# Max borrow (50% LTV): $16 = 1,600,000,000 xUSD atomic

# Borrow 10 xUSD (1,000,000,000 atomic)
> call-contract <VaultEngine> borrow 1 1000000000 --signer mywallet

# Check your health factor (should be > 20000 = 2.0x)
> call-contract <VaultEngine> get_health_factor 1

# Check your xUSD balance
> get-balances
# Should show 10 xUSD (minus 0.5% borrow fee = 9.95 xUSD)
```

### Borrowing Math

| Parameter | Value |
|-----------|-------|
| Min Collateral Ratio (MCR) | 200% (10,000 bps) |
| Max LTV | 50% (1/MCR) |
| Borrow fee | 0.5% (50 bps) — goes to treasury |
| Insurance fee | 0.1% (10 bps) — goes to insurance pool |

Example: deposit 100 XEL at $0.32 → collateral value $32 → max borrow $16 (50% LTV).

---

## Step 5: Use xUSD

xUSD is a stablecoin pegged to $1 USD. You can:

### Transfer xUSD to another user

```bash
> call-contract <xUSD> transfer_tokens xet1friend... 500000000 \
    --signer mywallet \
    --deposit <xUSD_ASSET_HASH> 500000000
# Sends 5 xUSD to your friend
```

### Swap xUSD for XEL on VaultSwap

```bash
# Swap 10 xUSD for XEL (with min 30 XEL output at $0.32)
> call-contract <VaultSwap> swap \
    <xUSD_ASSET_HASH> \
    0x0000000000000000000000000000000000000000000000000000000000000000 \
    1000000000 \
    3000000000 \
    --signer mywallet \
    --deposit <xUSD_ASSET_HASH> 1000000000
```

### Use the PSM (Peg Stability Module) for instant mint/redeem

The PSM is a **dedicated contract** (`PSM.slx`) that guarantees xUSD is always worth ~$1. It allows anyone to mint or redeem xUSD directly at the oracle price, **without needing liquidity providers**.

**How it works**:
- The PSM holds a reserve of XEL
- When you mint xUSD: you deposit XEL → PSM keeps the XEL → mints fresh xUSD to you at oracle price
- When you redeem xUSD: you deposit xUSD → PSM burns it → sends you XEL from the reserve at oracle price
- The peg is maintained by arbitrage: if xUSD > $1 on secondary markets, arbitrageurs mint and sell; if xUSD < $1, they buy and redeem

```bash
# Mint xUSD with 100 XEL (at $0.32 = 32000000 atomic price)
# You'll get ~$32 of xUSD minus 0.5% mint fee = 31.84 xUSD
> call-contract <PSM> mint 10000000000 3180000000 \
    --signer mywallet \
    --deposit 0x0000000000000000000000000000000000000000000000000000000000000000 10000000000

# Redeem xUSD for XEL
# 10 xUSD → ~31 XEL minus 0.1% redeem fee
> call-contract <PSM> redeem 1000000000 3100000000 \
    --signer mywallet \
    --deposit <xUSD_ASSET_HASH> 1000000000

# Check PSM reserves
> call-contract <PSM> get_reserves
# Returns: (xel_reserve, xusd_balance_in_psm)
```

**Why the PSM doesn't need bootstrap liquidity**:
- At launch: 0 XEL in PSM, 0 xUSD in circulation
- First user mints 100 XEL worth of xUSD → PSM has 100 XEL, 32 xUSD in circulation
- The xUSD supply grows naturally as users mint it
- The XEL reserve also grows, ensuring reddemeers always have XEL to withdraw
- Self-balancing system ✅

---

## Step 6: Repay xUSD and Withdraw Collateral

### Repay borrowed xUSD

```bash
# Repay 10 xUSD (the burn happens from the contract's balance)
> call-contract <VaultEngine> repay 1 1000000000 \
    --signer mywallet \
    --deposit <xUSD_ASSET_HASH> 1000000000

# Check health factor (should be u64::MAX now = no debt)
> call-contract <VaultEngine> get_health_factor 1
```

### Withdraw collateral

```bash
# Withdraw 50 XEL from your vault (must keep health factor healthy)
> call-contract <VaultEngine> withdraw 1 5000000000 --signer mywallet

# Verify your XEL balance
> get-balance
```

---

## Step 7: Monitor Your Position

### Check Vault Health

```bash
# Get health factor (10000 = 1.0x, 20000 = 2.0x required minimum)
> call-contract <VaultEngine> get_health_factor 1

# If health factor < 20000, you're at risk of liquidation
# Add more collateral or repay debt immediately
```

### Get Total Stats

```bash
# Total vaults created
> call-contract <VaultEngine> total_vaults

# Redemption queue size (vaults available for redemption)
> call-contract <VaultEngine> redemption_queue_size

# Oracle price for XEL/USD
> call-contract <StakedOracle> get_price "XEL/USD"

# VLT circulating supply (should decrease over time = deflation)
> call-contract <VLTToken> get_circulating_supply
> call-contract <VLTToken> get_total_burned
```

---

## Liquidation

If your health factor drops below 200% (20000 bps), your vault becomes liquidatable after a 10-block grace period (~50 seconds).

### What happens during liquidation?

1. Anyone can call `liquidate(vault_id, max_borrow_to_repay)` on your vault
2. The liquidator burns xUSD to repay your debt
3. The liquidator receives XEL collateral + 10% liquidation penalty
4. You lose part of your collateral

### How to avoid liquidation?

- **Monitor your health factor** regularly
- **Add collateral** if XEL price drops: `deposit(0x0, amount)`
- **Repay debt** to reduce borrow: `repay(vault_id, amount)`
- The 10-block grace period gives you ~50s to react

---

## Stake VLT as Price Provider (optional)

If you want to earn VLT rewards by providing price data:

```bash
# 1. Get 100 VLT (minimum stake) from faucet or VaultSwap
# 2. Register as provider
> call-contract <StakedOracle> register_provider \
    --signer mywallet \
    --deposit <VLT_ASSET_HASH> 10000000000

# 3. Run the price provider script on your server
# (See PROVIDER_GUIDE.md for full setup)
python3 scripts/price_provider.py

# 4. Monitor your rewards
> call-contract <StakedOracle> get_provider xet1abc...
# Returns: (stake, registered_at, rewards_earned, total_slashed, active)
```

---

## FAQ

### How is xUSD kept at $1?

Three mechanisms:
1. **PSM (Peg Stability Module)**: Anyone can mint/redeem xUSD at oracle price ($1 ± 0.5% fee)
2. **Overcollateralization**: Every xUSD is backed by >= $2 of XEL collateral
3. **Redemption queue**: If xUSD < $1, anyone can burn xUSD and claim XEL at face value

### Can I lose my collateral?

Only if your health factor drops below 200% for 10+ blocks. The system gives you a 50-second grace period to add collateral or repay debt. After that, your vault can be liquidated.

### Is xUSD really private?

Yes. xUSD is a XELIS Confidential Asset — balances and transfers are encrypted with Twisted ElGamal. Only you can see your xUSD balance (with your viewing key).

### Can I run multiple vaults?

Yes, each `deposit()` creates a new vault with a unique ID. You can have as many vaults as you want.

### What happens if the oracle goes down?

If no price update for 100 blocks (~500s), `get_price()` reverts. This means:
- You cannot borrow or withdraw (health factor can't be checked)
- You cannot swap on VaultSwap
- Your existing positions are safe (no automatic liquidation)

The guardian multisig can manually set a fallback price if needed.

### How do I get more testnet funds?

- Wait 24h and claim from faucet again (up to lifetime cap)
- Ask in [Discord](https://discord.gg/xelisvault) `#testnet-faucet` channel
- On mainnet: buy XEL on MEXC/CoinEx, swap for VLT/xUSD on VaultSwap

---

## Troubleshooting

### "insstake" error when registering as provider
You need to deposit at least 100 VLT (10,000,000,000 atomic) with the `register_provider` call. Make sure you have VLT in your wallet and the `--deposit` flag is set.

### "paused" error
The contract is paused (emergency). Check Discord for announcements.

### "cbpaused" error
The feed is in circuit breaker (price moved >20%). Wait for the team to reset it.

### "stale" error when getting price
The oracle hasn't updated in >100 blocks. Make sure providers are running. Check `get_cycle 0` — should increment every 25s.

### "oorange" error when submitting price
Your price is outside the [min, max] range for the feed. Check that your price sources are working: `python3 scripts/price_provider.py --test-sources`.

### Transaction not confirming
- Check daemon is synced: `curl -X POST http://127.0.0.1:8080 -d '{"method":"get_info","params":{},"jsonrpc":"2.0","id":1}'`
- Check your wallet has enough XEL for gas fees
- Check mempool: `curl -X POST http://127.0.0.1:8080 -d '{"method":"get_mempool","params":{},"jsonrpc":"2.0","id":1}'`

---

## Support

- **Discord**: [XELIS Vault Discord](https://discord.gg/xelisvault) — `#support` channel
- **Email**: `support@xelisvault.io`
- **GitHub Issues**: [XelisVault/xelis-vault/issues](https://github.com/XelisVault/xelis-vault/issues)
- **Documentation**: [docs/](../docs/)

---

*Last updated: June 2026 — v4.2*
