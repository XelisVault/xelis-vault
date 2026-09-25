# XelisVault — Community Guide (MAINNET LIVE)

> 🟢 **Deployed and verified on the XELIS mainnet on 23/09/2026.** This guide
> is written for the community: what the contracts are, where they live, how
> to launch a coin, vote, trade and provide liquidity — and how to
> **verify for yourself** that you are interacting with the right contract.

---

## 0. Official addresses (mainnet)

| Contract | Address (deployment hash) | Role |
|---|---|---|
| **VaultLaunch** (the launchpad) | `45baf014edd09f1f93a7746aa7d7c45f1dea01daa07b0bc438f2a0e80664cc54` | propose → vote → bonding curve → graduation → migration |
| **LaunchDEX v1.4.1** (the DEX) | `f3c461afe698a2bdfc7e5d941e86300876ecf16ac33ea45d8c6ddd936f7e24ef` | XEL/token pools, swaps, liquidity, LP fees |
| **CommunityLaunch v1.0.1** (the factory) | `8252cf7b7157dd05daf2d4e3bad78009c155c67bb3c908d042c61484dd7e89b9` | permissionless community coins → same DEX |
| Explorer | [`https://explorer.xelis.io`](https://explorer.xelis.io) | verify TXs, contracts, storage |

> ⚠️ **Golden rule**: never interact with any other address presented as
> "the launchpad", "the DEX" or "the factory". These three hashes are the
> only ones deployed by the official wallet
> `xel:sel92pcaegt0kenv3q35ycnzpd4xfl0md93usnkxq0rsjtha6cjsqe2xwch`.
> Always check the full hash in the explorer before sending funds.

**Independent verification** — the contracts are **pinned to each other**
at the protocol level:
- Storage `dxa` of the Vault = `f3c461af…` (the DEX): only that DEX can
  receive a project's migration.
- Storage `dxa` of CommunityLaunch = `f3c461af…` (the same DEX): that is
  where community coins migrate.
- Storage `lpx` of the DEX = `xel:sel92…` (the official wallet): only that
  wallet can create a pool via `create_pool`.

> The previous gen-1 DEX (`bce37bde…`) is **orphaned** — it exists on
> chain but never served a pool and never will (the v1.4.1 cut fixed the
> second-migration bug; UPGRADES.md §6). Never use it for trading.

Any "clone" that does not honor all three pins is a fake.

---

## 1. How it works (in 2 minutes)

**VaultLaunch** is a launchpad with **community validation**:

1. **propose** — a creator deposits **526 XEL minimum**
   (submission fee 25 XEL + asset budget 1 XEL + seed liquidity 500 XEL) and
   describes the project (name, symbol, website, socials, total supply, team
   allocation and vesting plan).
2. **support** — every community member can vote for the project
   (**no deposit required** — `vdp = 0`). Validation passes when
   `participants ≥ 1` and `≥ 80 %` approval, after a **720-topo (~1 h)**
   window.
   - ❌ Rejected project → the creator's funds are **100 % refunded**.
3. **finalize_validation** — the project enters **bonding**: a
   constant-product bonding curve opens (fee 0.5 %).
   - **Small-float** project: DEX listing when reserves reach
     `liquidity × 2` (**graduation at 1 000 XEL** of reserves for a 500 XEL
     seed).
   - Project with `≥ 2 000 XEL` liquidity at propose → **direct listing**
     right after validation (no bonding phase).
4. **migrate** — the creator migrates the curve to **LaunchDEX**: a
   permanent XEL/token pool is created, liquidity providers (LP) then earn
   **50 % of the fees** (0.30 % per swap).

**LaunchDEX** is the protocol's automated market maker: XEL↔token swaps,
adding/removing liquidity, configurable fees (0.30 % default,
50/50 LP-protocol split).

---

## 2. Launching a coin (creator)

> Minimum deposit at propose (mainnet): **526 XEL**
> (`2.5e9` sub + `1e8` budget + `5e10` seed liquidity). Anything above becomes
> extra liquidity on the curve.

| Parameter | Mainnet value |
|---|---|
| Submission fee (`sub`) | 25 XEL |
| Asset budget (`abd`) | 1 XEL |
| Minimum seed liquidity (`mnl`) | 500 XEL |
| Minimum participants (`mnp`) | 1 |
| Approval ratio (`mab`) | 80 % |
| Validation window (`vdt`) | 720 topos (~1 h) |
| Graduation multiplier (`gmu`) | ×2 (small-float → 1 000 XEL) |
| Direct-listing threshold (`dlt`) | 2 000 XEL |
| Vote deposit (`vdp`) | 0 (free) |
| Bonding / graduated / migration fee | 0.50 % / 0.25 % / 0.50 % |
| DEX swap fee / LP share | 0.30 % / 50 % |

**Tokenomics constraints** (enforced by the contract):
- `total_supply` is bounded (finite, no post-launch mint).
- `team_bps` is capped; the team vesting is **declared at propose** and
  **binding** (the community votes on the exact unlock schedule, not a
  promise).
- The team allocation is **reserved** (kept off the curve) until graduation.

---

## 3. Trading & participating

- **Buy** — during bonding on the Vault curve, then on the DEX pool after
  migration. Minimum XEL deposit 0.01 XEL per trade.
- **Sell** — free during bonding (selling is never blocked except after a
  project migrated), then on the DEX pool.
- **Provide liquidity** — `add_liquidity` on a DEX pool (XEL + tokens),
  earn **50 % of the fees** continuously, pro-rata exit at any time.
- **Claim LP fees** — `claim_lp_fees` on the pool.

> ⚠️ **Permanent liquidity floor**: the migrated seed liquidity (the 500 XEL
> minimum) is **locked in the protocol forever** (`seed locked forever`, risk
> review X11). LPs provide on top of it and earn their pro-rata share. This
> is an anti-dump guarantee: the pool can never be fully drained.

---

## 4. Interaction commands (node + wallet)

The complete command guide (propose, support, finalize, buy, sell, migrate,
swaps, add/remove liquidity, claims, data reads) is the
**[RUNBOOK 3 — Mainnet interactions](runbooks/RUNBOOK3_MAINNET_INTERACTIONS.md)**.
It includes the real deployment/config hashes and the exact XELIS RPC
parameter format.

Technical documentation of the contracts:
- [LAUNCHPAD.md](LAUNCHPAD.md) — VaultLaunch in detail (entry IDs, storage
  keys, curve, graduation, votes, vesting).
- [DEX.md](DEX.md) — LaunchDEX in detail (pools, fees, LP, trade bounds).
- [SECURITY.md](SECURITY.md) — risk model and emergency procedures.
- [ARCHITECTURE.md](ARCHITECTURE.md) — protocol overview.

**SDK integration** (`sdk/xvault`, Python):

```python
from xvault.protocol import DaemonClient
from xvault.launchpad import LaunchpadReader
from xvault.dex import DexReader

D = DaemonClient("http://127.0.0.1:8085/json_rpc")  # or your own mainnet node
VAULT = "45baf014edd09f1f93a7746aa7d7c45f1dea01daa07b0bc438f2a0e80664cc54"
DEX   = "f3c461afe698a2bdfc7e5d941e86300876ecf16ac33ea45d8c6ddd936f7e24ef"
COM   = "8252cf7b7157dd05daf2d4e3bad78009c155c67bb3c908d042c61484dd7e89b9"

lp = LaunchpadReader(D, VAULT)   # lp.count(), lp.project(0), ...
dx = DexReader(D, DEX)           # dx.pools_count(), dx.pool(asset), ...
```

---

## 5. Protocol status (25/09/2026)

| Done | Detail |
|---|---|
| Deployment (gen-1, 23/09) | VaultLaunch `45baf014…` — TX at topo 9041917 |
| **v18.4 cut (25/09)** | **DEX v1.4.1 `f3c461af…`** (topo 9073523) + **CommunityLaunch `8252cf7b…`** (topo 9073563) deployed; launchpad pin set before any pool (topo 9073612); gen-1 Vault repinned + factory pinned to the new DEX (topos 9073629/9073642) |
| Pins | `dxa` Vault → DEX ✓ , `dxa` CL → DEX ✓ , `lpx` DEX → wallet ✓ |
| Config | Vault: sub 25, abd 1, mnl 500, mnp 1, mab 80 %, vdt 720, gmu ×2, vdp 0, tfe/gfe/mgf 0.5/0.25/0.5 %, dlt 2 000 — **16/16 storage keys verified on-chain**; DEX: sfe 0.30 %, fsl 50 %, trade bounds at v1.4.1 defaults; CL: defaults = target (sub 1, abd 1, cfe/gfe/mgf 1/0.5/0.5 %, gdx 50, vxs 100) |
| Projects | `pc = 0` — nothing launched yet: **the community creates the coins** |
| Pools | `pc = 0` — no DEX pool created yet (both DEXes) |
| Module verification | .hex checksums identical to the testnet-validated / CI-gated version |

---

## 6. Quick FAQ

**Q. Why 526 XEL to propose a coin?**
25 XEL submission fee (to the protocol) + 1 XEL asset budget (covers the
asset-mint fee) + 500 XEL seed liquidity (the curve minimum; refunded if the
project is rejected, forever locked in the pool otherwise).

**Q. Does voting cost anything?**
No. `vdp = 0`: voting is free. You just need an XELIS wallet.

**Q. What guarantees I'm dealing with the right contract?**
The protocol pins `dxa`/`lpx` + explorer verification. See §0.

**Q. Can the pool liquidity be fully withdrawn?**
No. The seed (`mnl`) is locked forever; only LP contributions above the seed
can be withdrawn pro-rata.

**Q. Where are the exact commands?**
In the [mainnet RUNBOOK 3](runbooks/RUNBOOK3_MAINNET_INTERACTIONS.md)
(deployment/config TX hashes included).

---

*XelisVault v18.4 — Privacy-first DeFi on XELIS. Deployed on mainnet,
configured and verified (v1.4.1 cut on 25/09/2026: one DEX lineage for
both tracks). The rest of the protocol belongs to the community.*