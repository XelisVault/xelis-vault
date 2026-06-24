# Provider Guide — XELIS Vault v5.0

> Earn VLT rewards by providing accurate price data to the XELIS Vault oracle.
> Aimed at technical operators running `price_provider.py` and
> `aggregation_keeper.py`.

---

## 1. Overview

### 1.1 What is a price provider?

A price provider is anyone who runs the `price_provider.py` script, fetches
XEL prices from external exchanges, computes a median locally, and submits
it on-chain via `StakedOracle.submit_price(feed_id, price)` (entry ID **5**).

### 1.2 Provider vs miner

In v5.0 the terminology is:

- **Miner** — registered on `XelisVaultMiner` (entry ID 0), locks 100 VLT
  stake, sends heartbeats (entry ID 6), can be slashed (entry ID 7). Earns
  rewards through `distribute_reward` (entry ID 8) which is called by the
  oracle / chat contracts.
- **Provider** — runs `price_provider.py`. The provider's wallet address
  **must** be a registered miner (otherwise `submit_price` reverts with
  `notreg`). The provider is the **source of price data**, the miner is the
  **on-chain identity** that earns the reward.

In practice: a miner runs the daemon (`xelis_vault_miner.py`) for
heartbeats + reputation, **and** runs `price_provider.py` to actually submit
prices. The two scripts share the same wallet.

### 1.3 Why this matters

Every swap, loan, liquidation and PSM mint reads the price from
`StakedOracle.get_price_for_asset_entry(asset)` (entry ID 9). A wrong price
moves money incorrectly. The more providers, the harder it is to push a bad
median — the oracle rejects any submission >5 % from the median of the
current cycle.

---

## 2. Supported price sources

Built into `price_provider.py`:

| Source       | URL                                       | Auth needed? | Symbols supported |
|--------------|-------------------------------------------|--------------|-------------------|
| **CoinEx**   | `https://api.coinex.com/v2/spot/ticker`   | API key/secret (optional, raises rate limit) | `XEL/USDT`, `XEL/BTC` |
| **MEXC**     | `https://api.mexc.com/api/v3/ticker/price`| API key/secret (optional) | `XEL/USDT` |
| **XELIS daemon** | `http://127.0.0.1:8080` (your local node) | None — uses `get_info` + DEX pool price | Native XEL/USDT implied price |
| **Custom HTTP** | Any URL returning JSON                | Bearer token, headers, etc. | Any |
| **Custom command** | Any local executable returning JSON  | None | Any |

See [`scripts/custom_sources.example.json`](../scripts/custom_sources.example.json)
for a fully-commented example with all source types.

---

## 3. Custom source format

The config file is `~/.xelis-vault/config/custom_sources.json`. It is a JSON
object with a single `sources` array. Each entry is one of:

### 3.1 Schema

```json
{
  "sources": [
    {
      "name": "coinex",
      "type": "http",
      "enabled": true,
      "api_key": "YOUR_API_KEY",
      "api_secret": "YOUR_API_SECRET",
      "symbols": ["XEL/USDT", "XEL/BTC"],
      "poll_interval_seconds": 5,
      "url": "https://api.coinex.com/v2/spot/ticker",
      "params": { "market": "XELUSDT" },
      "json_path": "data.0.last",
      "headers": { "X-CoinEx-Key": "YOUR_API_KEY" },
      "timeout": 10
    },
    {
      "name": "mexc",
      "type": "http",
      "enabled": true,
      "api_key": "YOUR_MEXC_API_KEY",
      "api_secret": "YOUR_MEXC_API_SECRET",
      "symbols": ["XEL/USDT"],
      "poll_interval_seconds": 5,
      "url": "https://api.mexc.com/api/v3/ticker/price",
      "params": { "symbol": "XELUSDT" },
      "json_path": "price",
      "timeout": 10
    },
    {
      "name": "xelis_daemon",
      "type": "daemon",
      "enabled": true,
      "rpc_url": "http://127.0.0.1:8080",
      "poll_interval_seconds": 5
    },
    {
      "name": "custom_api",
      "type": "http",
      "enabled": false,
      "url": "https://api.my-price.com/xel",
      "json_path": "price",
      "headers": { "Authorization": "Bearer YOUR_TOKEN" },
      "timeout": 10
    },
    {
      "name": "my_script",
      "type": "command",
      "enabled": false,
      "command": "/usr/local/bin/fetch_xel_price.sh",
      "args": ["--json"],
      "timeout": 15
    }
  ]
}
```

### 3.2 Fields

| Field                   | Required | Description                                              |
|-------------------------|----------|----------------------------------------------------------|
| `name`                  | yes      | Unique identifier used in logs (never logs API key)      |
| `type`                  | yes      | `http` / `daemon` / `command`                            |
| `enabled`               | yes      | If `false`, source is skipped                            |
| `url`                   | http     | URL to fetch                                             |
| `params`                | http     | Query-string params                                      |
| `json_path`             | http     | Dot-separated path into the JSON (e.g. `data.0.last`)    |
| `headers`               | http     | Extra HTTP headers (e.g. `Authorization: Bearer ...`)    |
| `timeout`               | http/cmd | Seconds before the fetch is aborted                     |
| `api_key` / `api_secret`| http     | Optional, used by built-in CoinEx/MEXC helpers          |
| `symbols`               | http     | List of trading-pair symbols this source can fetch       |
| `poll_interval_seconds` | all      | Per-source polling interval                              |
| `rpc_url`               | daemon   | XELIS daemon JSON-RPC URL                                |
| `command` + `args`      | command  | External command; stdout must be JSON with a `price` field |

---

## 4. Price aggregation

On each cycle (default every 5 seconds per source, then a 20-second submit
window), `price_provider.py`:

1. **Polls each enabled source** for the configured symbol(s).
2. **Sanity-checks** each price: must be within `0.001 < price < 10,000` USD
   (configurable in the script).
3. **Outlier rejection**: any price >5 % from the median of all collected
   prices is discarded (and logged).
4. **Staleness check**: any price older than 30 seconds is discarded (and
   logged).
5. **Median compute**: takes the median of remaining valid prices.
6. **Submit** if there are ≥ 2 valid sources.

### 4.1 Why median not mean?

Median is robust to a single bad source. With 5 sources, even if 2 are
completely wrong (e.g. an exchange glitch), the median of the 3 good ones is
still correct.

### 4.2 Why >5 % rejection?

The on-chain oracle itself rejects submissions >5 % from the on-chain median
(severity 0 slash, -50 reputation). We pre-filter locally to avoid being
flagged.

### 4.3 Why >30 s staleness?

A price from 60 s ago can be drastically different from now in volatile
markets. 30 s gives us a strict freshness bound without being too aggressive.

---

## 5. Submission flow

```
                  ┌──────────────────────┐
                  │  CoinEx  MEXC  Daemon │   (custom sources)
                  └──────────┬───────────┘
                             │ fetch every 5s
                             ▼
                  ┌──────────────────────┐
                  │  price_provider.py   │
                  │   - sanity check     │
                  │   - outlier reject   │
                  │   - staleness reject │
                  │   - compute median   │
                  └──────────┬───────────┘
                             │ every ~20 s
                             ▼
                  ┌──────────────────────┐
                  │ StakedOracle         │
                  │ .submit_price(       │   ← entry ID 5
                  │   feed_id, price)    │
                  └──────────┬───────────┘
                             │ on cycle boundary (5 blocks)
                             ▼
                  ┌──────────────────────┐
                  │ StakedOracle         │
                  │ .aggregate_now(fid)  │   ← entry ID 6 (called by keeper)
                  └──────────┬───────────┘
                             │
                             ▼
                  ┌──────────────────────┐
                  │ XelisVaultMiner      │
                  │ .distribute_reward(  │   ← entry ID 8 (called by oracle)
                  │   miner, svc, true)  │
                  └──────────────────────┘
```

The `submit_price` (entry ID 5) call is signed by your wallet — this is what
links the price to your miner address. The on-chain oracle verifies you are
registered (entry ID 9 must return 1) and not paused.

---

## 6. Privacy considerations

### 6.1 What is public on-chain

- Your **wallet address** (signs every `submit_price` transaction).
- Your **submitted price** (visible in the tx payload).
- The **timestamp / block height** of your submission.
- Your **reputation** (entry ID 11 — readable by anyone).
- Your **stake and rewards** (entries 10 and 11 of `XelisVaultMiner`).

### 6.2 What is NOT logged on-chain

- Your **IP address** (the daemon submits via JSON-RPC; the network only sees
  the wallet's signed transaction).
- Your **API keys** (CoinEx, MEXC, etc.) — these never leave your server.
- Your **other wallet holdings** — only the stake is locked in the contract.
- Other miners' IPs — the script never logs them either.

### 6.3 Best practice: use a dedicated mining wallet

Set up a fresh XELIS wallet **just for mining**. Send it exactly 100 VLT +
a small XEL balance for gas. This way:

- Your main holdings aren't linked to your miner identity.
- If the miner server is compromised, only the mining wallet (small balance)
  is at risk.
- Your on-chain history as a miner doesn't leak your main wallet's
  transaction graph.

### 6.4 What `price_provider.py` logs

```
2026-07-15 14:32:11 INFO  source=coinex        price=0.4821  latency=80ms
2026-07-15 14:32:11 INFO  source=mexc          price=0.4819  latency=150ms
2026-07-15 14:32:11 INFO  source=xelis_daemon  price=0.4820  latency=12ms
2026-07-15 14:32:11 INFO  median=0.4820  valid_sources=3  rejected=0
2026-07-15 14:32:31 INFO  submit_price feed_id=0 price=48200000 atomic  tx=0x9f3a...c1
```

Note: API keys are **never** in the log. Source name + price + timestamp
only. Wallet balances are masked with `****`.

---

## 7. Setting up the aggregation keeper

The `aggregation_keeper.py` script triggers `StakedOracle.aggregate_now
(feed_id)` (entry ID **6**) every 25 seconds. This is needed because
aggregation only auto-triggers inside `submit_price` if the cycle has
elapsed — but if no provider submits in a given window, aggregation never
runs and the price goes stale.

### 7.1 Install & run

```bash
python3 scripts/aggregation_keeper.py \
    --feed-ids 0,1,2 \
    --interval 25 \
    --rpc http://localhost:8080
```

### 7.2 Run as a service

```bash
sudo tee /etc/systemd/system/xelis-vault-keeper.service <<EOF
[Unit]
Description=XELIS Vault Aggregation Keeper v5.0
After=network.target xelis-daemon.service

[Service]
Type=simple
User=$(whoami)
ExecStart=/home/$(whoami)/.xelis-vault/venv/bin/python3 \
    /home/$(whoami)/xelis-vault-v5/scripts/aggregation_keeper.py \
    --feed-ids 0 --interval 25
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now xelis-vault-keeper
```

> Anyone can run a keeper — no VLT stake needed. The community is encouraged
> to run ≥ 3 keepers for redundancy.

### 7.3 CLI flags

| Flag          | Default                  | Description                          |
|---------------|--------------------------|--------------------------------------|
| `--feed-ids`  | `0`                      | Comma-separated feed IDs to keep     |
| `--interval`  | `25`                     | Seconds between aggregate calls      |
| `--rpc`       | `http://localhost:8080`  | XELIS daemon JSON-RPC URL            |
| `--dry-run`   | off                      | Log but don't submit                 |

---

## 8. Monitoring

### 8.1 Log files

| Process              | Log file                                |
|----------------------|-----------------------------------------|
| `xelis_vault_miner.py` | `~/.xelis-vault/logs/miner.log`       |
| `price_provider.py`    | `~/.xelis-vault/logs/provider.log`    |
| `aggregation_keeper.py`| `~/.xelis-vault/logs/keeper.log`      |

All logs rotate at 100 MB and keep 5 archives.

### 8.2 Live tail

```bash
tail -f ~/.xelis-vault/logs/provider.log
```

### 8.3 Grafana dashboard

A ready-to-import Grafana JSON ships at `scripts/grafana_dashboard.json`
(create it from the template below if it doesn't exist yet). It exposes:

- `provider_prices_submitted_total` (counter)
- `provider_last_price_xel_usd` (gauge)
- `provider_estimated_rewards_vlt` (gauge)
- `provider_sources_healthy` (gauge — number of sources returning valid data)
- `keeper_aggregations_total` (counter)
- `keeper_last_aggregation_topo` (gauge)

To enable Prometheus, set `PROMETHEUS_PORT=9091` in
`~/.xelis-vault/config/.env` and scrape it from your Prometheus instance.

### 8.4 On-chain checks

```bash
# Current aggregated price for XEL/USD (entry ID 8)
xelis_wallet call-contract <StakedOracle> get_price_entry "XEL/USD"

# Current cycle for feed 0 (pub fn)
xelis_wallet call-contract <StakedOracle> get_cycle 0

# Number of submissions in the current cycle (pub fn)
xelis_wallet call-contract <StakedOracle> get_cycle_submissions 0
```

---

## 9. Performance tuning

### 9.1 Poll interval

Default is 5 s per source. Lowering to 2 s gives fresher data but increases
API rate-limit risk. Recommended:

- **CoinEx / MEXC** with API key: 2–3 s
- **CoinEx / MEXC** without API key: 5 s
- **CoinGecko**: 60 s (rate limit 30/min)
- **Custom HTTP**: depends on the upstream — start at 5 s

### 9.2 Max sources

More sources = better median, but diminishing returns past 5. The script
cap is 10 concurrent sources.

### 9.3 Retry policy

Each source has a built-in 3-retry with exponential backoff (1 s, 2 s, 4 s).
After 3 failures the source is marked unhealthy for 60 s and skipped. The
script logs every retry at DEBUG level.

### 9.4 Submit interval

Default: 20 s. The on-chain cycle is 5 blocks ≈ 25 s. Submitting every 20 s
ensures you have a fresh submission in every cycle without being flagged for
spam (`alreadysub` revert if you submit twice in the same cycle).

### 9.5 Parallelism

`price_provider.py` polls all sources concurrently using a thread pool
(default 8 workers). If you have many sources, raise the pool size:

```bash
python3 scripts/price_provider.py --max-workers 16
```

---

## 10. Disaster recovery

### 10.1 If your provider goes down

- The on-chain oracle keeps working as long as **other** providers are
  submitting — your absence just means you don't earn rewards.
- No reputation penalty for being offline **as a provider** (the reputation
  penalty for being offline applies to **miners**, triggered by missed
  heartbeats — see [Miner Guide](MINER_GUIDE.md) §11.3).
- When you come back, you simply resume submitting.

### 10.2 Redundancy

Run two provider instances in different data centres, both signed by the
**same** wallet. The second instance is a hot standby — it submits only if
the primary hasn't submitted in the current cycle (use the `--standby` flag).

### 10.3 Failover sources

If your primary source goes down, the script automatically falls back to
the next enabled source. Keep at least **3 sources** enabled so a single
outage doesn't drop you below the 2-source minimum.

### 10.4 Backup config

Back up `~/.xelis-vault/config/` regularly to a secure location (encrypted
off-site). It contains your API keys.

### 10.5 Wallet backup

Back up your wallet's mnemonic offline (paper / hardware). If your server
dies, you can restore the wallet on a new server and keep the same miner
identity (reputation, stake, registration all persist on-chain).

---

## 11. FAQ

### Q1. Can I run provider without being a miner?
No. `submit_price` reverts with `notreg` if your address isn't registered on
`XelisVaultMiner`. Register first (see [Miner Guide](MINER_GUIDE.md) §7),
then run `price_provider.py` with the same wallet.

### Q2. Do I get slashed for being offline?
Only miners get slashed (via missed heartbeats). The provider script not
running means no rewards, but no penalty.

### Q3. Can I run the provider and the miner daemon on different machines?
Yes, as long as both share the same wallet (same XELIS address). Use
`xelis_wallet`'s remote RPC mode to share a single wallet across machines.

### Q4. What's the minimum stake to be a provider?
100 VLT (the miner minimum). There is no separate provider stake — your
miner stake covers it.

### Q5. How are rewards credited?
`StakedOracle.aggregate_now` (entry ID 6) is called by the keeper every 25 s.
If your submission was within 5 % of the median, `distribute_reward` (entry
ID 8 on `XelisVaultMiner`) mints VLT to your wallet. The amount is
`BASE_REWARD_ORACLE × reputation_mult × budget_factor`.

### Q6. Can I submit for multiple feeds?
Yes. Add multiple `--feed-id` flags or list them in the config. Each feed
earns its own reward per cycle.

### Q7. Why is my provider log showing `oorange` errors?
Your submitted price is outside the `[min_price, max_price]` range set when
the feed was created (entry ID 0 on `StakedOracle`). Check your sources and
the feed config. For XEL/USD the default range is `[0.001 USD, 10,000 USD]`.

### Q8. Where do I get help?
- Discord: https://discord.gg/UHpYAWbG — `#providers` channel
- Email: `providers@xelisvault.io`
- GitHub Issues: https://github.com/XelisVault/xelis-vault/issues

---

## 12. References

- [Miner Guide](MINER_GUIDE.md) — register as a miner, manage stake/reputation
- [Reward System](REWARD_SYSTEM.md) — full reward math
- [Entry IDs v5.0](ENTRY_IDS.md) — canonical entry ID list
- [`scripts/custom_sources.example.json`](../scripts/custom_sources.example.json)
  — fully-commented config example

---

*Last updated: July 2026 — v5.0*
