# Miner Guide — Configure xelis_miner + Aggregation Keeper

> Complete guide for XELIS miners who also want to support the XELIS Vault oracle.

---

## Why Miners Should Run a Keeper

XELIS miners already have:
- A synced XELIS daemon
- A wallet with their miner address
- Stable server infrastructure

By running the **aggregation keeper** alongside `xelis_miner`, you help the StakedOracle stay healthy even when few price providers are active. The keeper simply calls `aggregate_now(feed_id)` every block to ensure cycles advance on schedule.

**No VLT stake required** — keepers are public goods, anyone can run one.

---

## Option A: Run Keeper Only (No Provider Stake)

If you just want to help the network without staking VLT:

### Step 1: Install the Keeper Script

```bash
mkdir -p /opt/xelis-vault
cd /opt/xelis-vault

curl -O https://raw.githubusercontent.com/XelisVault/xelis-vault/main/scripts/aggregation_keeper.py
chmod +x aggregation_keeper.py
```

### Step 2: Configure

```bash
cat > /opt/xelis-vault/keeper.env << EOF
# StakedOracle contract hash
STAKED_ORACLE_CONTRACT=0x...

# XELIS daemon RPC URL
XELIS_RPC=http://127.0.0.1:8080

# Feeds to keep aggregated (comma-separated)
FEEDS_TO_KEEP=XEL/USD

# Poll interval (should match block time = 5s)
POLL_INTERVAL=5

# Log level
LOG_LEVEL=INFO
EOF
```

### Step 3: Run as systemd Service

```bash
sudo cat > /etc/systemd/system/xelis-vault-keeper.service << EOF
[Unit]
Description=XELIS Vault Aggregation Keeper
After=network.target xelis-daemon.service
Requires=xelis-daemon.service

[Service]
Type=simple
User=xelis
WorkingDirectory=/opt/xelis-vault
EnvironmentFile=/opt/xelis-vault/keeper.env
ExecStart=/usr/bin/python3 /opt/xelis-vault/aggregation_keeper.py
Restart=always
RestartSec=10
StandardOutput=append:/var/log/xelis-vault-keeper.log
StandardError=append:/var/log/xelis-vault-keeper.log

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable xelis-vault-keeper
sudo systemctl start xelis-vault-keeper
```

### Step 4: Verify

```bash
sudo systemctl status xelis-vault-keeper
sudo tail -f /var/log/xelis-vault-keeper.log
```

Expected output:
```
[INFO] XELIS Vault v4 - Aggregation Keeper
[INFO]   Oracle:  0x...
[INFO]   RPC:     http://127.0.0.1:8080
[INFO]   Feeds:   ['XEL/USD']
[INFO]   Feed XEL/USD -> ID 0
[INFO] Block 12345: aggregate_now called for 1 feeds
```

---

## Option B: Run Keeper + Provider (Earn VLT)

If you also want to earn VLT rewards by submitting prices:

### Step 1: Get VLT and Register as Provider

Follow the [Provider Guide](PROVIDER_GUIDE.md) — Steps 1 to 3.

### Step 2: Run Both Scripts

You can run both `price_provider.py` and `aggregation_keeper.py` on the same server. They use different ports (9091 and 9092 by default).

```bash
# Provider script (submits prices, earns rewards)
sudo systemctl start xelis-vault-provider

# Keeper script (triggers aggregation, no rewards but helps network)
sudo systemctl start xelis-vault-keeper
```

### Step 3: Monitor Both

```bash
# Provider metrics
curl http://localhost:9091/metrics | grep -E "(prices_submitted|rewards|last_price)"

# Keeper metrics
curl http://localhost:9092/metrics 2>/dev/null || echo "Keeper doesn't expose metrics (it's a public good)"
```

---

## Option C: Pool Operators

If you run a mining pool, you can integrate price submission directly into your pool software so that all your miners automatically contribute prices when they find blocks.

### Integration Approach

In your pool's block-found callback (Rust example):

```rust
// In your pool code (e.g., src/stratum/server.rs)
fn on_block_found(block_height: u64, miner_addr: Address) {
    // ... existing code: notify, distribute rewards ...
    
    // Launch price submission in async task
    let oracle = STAKED_ORACLE_CONTRACT.to_string();
    let rpc = XELIS_RPC.to_string();
    let addr = miner_addr.to_string();
    
    tokio::spawn(async move {
        let _ = Command::new("python3")
            .arg("/opt/xelis-vault/pool_price_submit.py")
            .arg("--miner").arg(&addr)
            .arg("--oracle").arg(&oracle)
            .arg("--rpc").arg(&rpc)
            .arg("--once")  // run once and exit
            .output()
            .await;
    });
}
```

The pool operator must:
1. Stake VLT as a single provider (using the pool's payout address)
2. Distribute the VLT rewards to miners proportionally (same as XEL rewards)
3. Run the keeper for redundancy

### Pool Provider Script

A `pool_price_submit.py` is provided in `scripts/` that takes `--miner <addr>` and submits prices on behalf of that miner. The pool's payout address is the registered provider.

```bash
# Pool operator setup
export POOL_PAYOUT_ADDRESS=xet1pool...
export STAKED_ORACLE_CONTRACT=0x...
export XELIS_RPC=http://127.0.0.1:8080

# Register the pool payout address as a provider (one-time)
xelis_wallet --network testnet
> call-contract <STAKED_ORACLE_HASH> register_provider \
    --signer pool-wallet \
    --deposit <VLT_ASSET_HASH> 100000000000

# Each time a miner finds a block, the pool software triggers:
python3 pool_price_submit.py --miner <miner_addr> --once
```

---

## Monitoring Your Miner + Keeper Setup

### systemd Status

```bash
sudo systemctl status xelis-daemon
sudo systemctl status xelis-miner
sudo systemctl status xelis-vault-keeper
# Optional:
sudo systemctl status xelis-vault-provider
```

### Logs

```bash
# Daemon logs
sudo journalctl -u xelis-daemon -f

# Miner logs
sudo journalctl -u xelis-miner -f

# Keeper logs
sudo tail -f /var/log/xelis-vault-keeper.log

# Provider logs (if running)
sudo tail -f /var/log/xelis-vault-provider.log
```

### Health Check Script

Create `/opt/xelis-vault/health-check.sh`:

```bash
#!/bin/bash
# Quick health check for XELIS Vault miner setup

echo "=== XELIS Daemon ==="
DAEMON_INFO=$(curl -s -X POST http://127.0.0.1:8080 \
    -H "Content-Type: application/json" \
    -d '{"method":"get_info","params":{},"jsonrpc":"2.0","id":1}')
echo "Synced: $(echo $DAEMON_INFO | jq -r '.result.synced')"
echo "Topoheight: $(echo $DAEMON_INFO | jq -r '.result.topoheight')"

echo ""
echo "=== systemd Services ==="
for svc in xelis-daemon xelis-miner xelis-vault-keeper xelis-vault-provider; do
    STATUS=$(sudo systemctl is-active $svc 2>/dev/null)
    echo "$svc: $STATUS"
done

echo ""
echo "=== Oracle Status ==="
ORACLE=${STAKED_ORACLE_CONTRACT:-"0x..."}
CYCLE=$(xelis_wallet --network testnet call-contract read $ORACLE get_cycle 0 2>/dev/null)
echo "XEL/USD feed cycle: $CYCLE"

echo ""
echo "=== Disk Space ==="
df -h / | tail -1

echo ""
echo "=== Memory ==="
free -h | head -2
```

```bash
chmod +x /opt/xelis-vault/health-check.sh
# Run it:
/opt/xelis-vault/health-check.sh
```

---

## Troubleshooting

### Keeper Not Advancing Cycles
- Verify daemon is synced
- Verify `STAKED_ORACLE_CONTRACT` is correct
- Check daemon RPC is accessible: `curl http://127.0.0.1:8080`
- Check keeper logs for errors

### Miner Not Finding Blocks
- Check daemon is synced
- Check your miner address has correct format (`xet1...` on testnet, `xel1...` on mainnet)
- Check your hashrate: `xelis_miner --stats`
- Verify mining job is being received (GetWork WebSocket)

### Provider Script Fails to Submit
- Verify daemon is synced
- Verify wallet is unlocked
- Verify `PROVIDER_ADDRESS` matches your registered provider
- Check `provider_prices_failed_total` metric

### All Services Down After Reboot
```bash
# Enable services to start on boot
sudo systemctl enable xelis-daemon
sudo systemctl enable xelis-miner
sudo systemctl enable xelis-vault-keeper
sudo systemctl enable xelis-vault-provider  # if running

# Start in order
sudo systemctl start xelis-daemon
sleep 5  # let daemon initialize
sudo systemctl start xelis-miner
sudo systemctl start xelis-vault-keeper
sudo systemctl start xelis-vault-provider  # if running
```

---

## Hardware Recommendations

### Minimal Setup (1 provider + 1 keeper)
- **CPU**: 2 cores
- **RAM**: 4 GB
- **Disk**: 100 GB SSD
- **Network**: 100 Mbps
- **Cost**: ~$10-15/month VPS

### Recommended Setup (pool operator)
- **CPU**: 4+ cores
- **RAM**: 8+ GB
- **Disk**: 500 GB NVMe SSD
- **Network**: 1 Gbps
- **Cost**: ~$40-80/month VPS

### Solo Miner + Provider
- **CPU**: 4+ cores (for mining)
- **RAM**: 8 GB
- **Disk**: 200 GB SSD
- **Network**: 100 Mbps
- **Cost**: ~$20-30/month VPS

---

## FAQ

### Do I need to run a keeper?
No, but it helps the network. If 3+ people run keepers, the oracle stays healthy. If you're the only provider on testnet, you should run a keeper.

### Can I run keeper and provider on the same machine?
Yes — they use different ports (9091 for provider, no port for keeper).

### Does running a keeper cost me anything?
Only a tiny amount of gas for the `aggregate_now` transaction (~0.0001 XEL per call). At 1 call/block, that's ~3.5 XEL/day. Negligible.

### Do keepers earn VLT rewards?
No. Keepers are a public good. Only providers (who stake VLT and submit prices) earn rewards.

### Can I run multiple keepers?
Yes, and you should! Redundancy is good. Each keeper calls `aggregate_now`, which is idempotent (calling it twice in the same cycle does nothing).

### My miner finds blocks but the keeper doesn't trigger aggregation
The keeper is independent of your miner. It runs on its own schedule (every 5 seconds by default). It doesn't need your miner to find blocks — it just calls `aggregate_now` on every block.

---

## Support

- **Discord**: [XELIS Discord](https://discord.gg/xelis) — `#mining` channel for XELIS mining, `#xelis-vault` for Vault-specific questions
- **Email**: `mining@xelisvault.io`
- **GitHub Issues**: [XelisVault/xelis-vault/issues](https://github.com/XelisVault/xelis-vault/issues)

---

## References

- [XELIS Mining Documentation](https://docs.xelis.io/features/mining)
- [XELIS Daemon Configuration](https://docs.xelis.io/getting-started/configuration/xelis_daemon)
- [XELIS Miner Configuration](https://docs.xelis.io/getting-started/configuration/xelis_miner)
- [Provider Guide](PROVIDER_GUIDE.md) — If you also want to earn VLT rewards

---

*Last updated: June 2026 — v4.2*
