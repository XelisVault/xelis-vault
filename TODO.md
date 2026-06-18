# TODO — XELIS Vault v4.2

> List of tasks to complete BEFORE and AFTER mainnet deployment.

---

## 🔴 BEFORE Mainnet — MANDATORY

### Compilation et tests
- [ ] Compiler les 31 contrats `.slx` avec le silex-compiler officiel XELIS
- [ ] Fix compilation errors (allow for iterations)
- [ ] Validate the 7 points listed in `docs/COMPATIBILITY_TABLE.md` with the XELIS-Forge team
- [ ] Write unit tests for each contract (target: 90% coverage)
- [ ] Write integration tests (complete flows: deposit → borrow → swap → repay)
- [ ] Fuzzing tests on critical contracts (StakedOracle, VaultEngine, PSM)
- [ ] Tests de stress (1000 providers, 10000 vaults, etc.)

### Audit
- [ ] Final internal audit (complete code review)
- [ ] Audit externe par Trail of Bits OU OpenZeppelin OU Hacken
- [ ] Fix all audit findings
- [ ] Re-audit if major changes

### Testnet
- [ ] Deploy on testnet with `deploy_testnet.py`
- [ ] Test all user flows (faucet → stake → submit_price → rewards)
- [ ] Test all lending flows (deposit → borrow → repay → withdraw)
- [ ] Tester tous les swaps (PSM mint/redeem, AMM swap)
- [ ] Tester la gouvernance (propose → vote → queue → execute)
- [ ] Tester les cas d'urgence (pause, circuit breaker, slashing)
- [ ] Recruit 20+ price providers for testnet
- [ ] Run for 4+ weeks without critical incident

### Bug Bounty
- [ ] Lancer un programme bug bounty sur Immunefi
- [ ] Allocation : 100,000 VLT (1% de la supply)
- [ ] Coverage: all v4.2 contracts
- [ ] Duration: minimum 3 months before mainnet

### Documentation
- [ ] Finalize whitepaper v3 (external review)
- [ ] Create the web dashboard (React)
- [ ] Create the TypeScript SDK
- [ ] Create a CLI tool to interact with contracts
- [ ] Translate documentation into Chinese and Spanish

---

## 🟡 AFTER Mainnet — Important

### Surveillance (mois 1-3)
- [ ] Monitoring 24/7 des contrats critiques
- [ ] Telegram/Discord alerts for any abnormal event
- [ ] Check daily:
  - [ ] Oracle cycle increments
  - [ ] Aggregated price reasonable (no drift)
  - [ ] VLT supply decreases (burn active)
  - [ ] No provider is mass-slashed
  - [ ] TVL in VaultEngine reasonable
- [ ] Weekly community report

### Expansion (months 3-12)
- [ ] First governance vote to add XAU/USD (when RWA gold ready)
- [ ] Launch AssetVault for physical gold
- [ ] Integrate ComplianceModule (when KYC verifier ready)
- [ ] Launch InsurancePool
- [ ] Launch LendingMarket (multi-collateral)
- [ ] Launch PeerLoan and SyndicatePool
- [ ] Launch SealedBidAuction

### Optimizations
- [ ] Optimize gas for critical functions
- [ ] Add events for better indexing
- [ ] Implement subgraphs for the dashboard
- [ ] Optimize price_provider script (cache, retry logic)

---

## 🟢 Long Term (year 2+)

### Future Features
- [ ] Reputation system for providers (v5)
- [ ] Multi-asset collateral in VaultEngine
- [ ] Cross-chain bridges (xUSD → Ethereum, Solana)
- [ ] Mobile wallet app
- [ ] L2 scaling (if necessary)
- [ ] Governance v2 (quadratic voting, delegation)
- [ ] Full ZK compliance (ZK verifier on-chain)

### Ecosystem
- [ ] Partnership with other XELIS projects
- [ ] Integration with XELIS Forge (forge-xelis-vault bridge)
- [ ] Documentation for third-party developers
- [ ] Hackathons and grants for builders

---

## 📊 Target Metrics

### End of 2026 (3 months post-mainnet)
- [ ] 50+ active price providers
- [ ] $100k+ TVL in VaultEngine
- [ ] $500k+ daily volume on VaultSwap + PSM
- [ ] VLT circulating supply: ~9.5M (5% burned)
- [ ] 1000+ unique wallet addresses interacted

### End of 2027
- [ ] 200+ active price providers
- [ ] $5M+ TVL
- [ ] $2M+ daily volume
- [ ] 3+ active price feeds (XEL/USD, XAU/USD, EUR/USD)
- [ ] VLT circulating supply: ~7M (30% burned)

### End of 2028
- [ ] 500+ active price providers
- [ ] $50M+ TVL
- [ ] $10M+ daily volume
- [ ] 10+ active price feeds
- [ ] VLT circulating supply: ~5M (50% burned)

---

## ⚠️ Known Risks

### Technical Risks
1. **Unconfirmed Ciphertext API** — If the Silex API for homomorphic encryption differs, VaultEngineV3 must be adapted
2. **Compilation errors** — Allow 1-2 weeks of debugging after first compilation
3. **Gas costs** — Complex contracts (LendingMarket, SealedBidAuction) can be expensive to execute
4. **Storage growth** — StakedOracle stores a lot of data, plan for pruning

### Economic Risks
1. **Provider shortage** — If <10 providers at launch, the oracle may be slow
2. **VLT price volatility** — May affect staking attractiveness
3. **PSM drain** — If XEL price drops sharply, the PSM can be drained
4. **Governance attacks** — A whale could buy enough VLT to control governance

### Regulatory Risks
1. **xUSD classification** — May be considered a regulated stablecoin
2. **RWA compliance** — AssetVault must comply with local laws
3. **Privacy regulations** — Confidentiality may be problematic in certain jurisdictions

---

## 🆘 Useful Contacts

- **XELIS Forge team** : https://github.com/XELIS-Forge (Silex technical questions)
- **XELIS project** : https://github.com/xelis-project (daemon, wallet, miner)
- **XELIS Discord** : https://discord.gg/xelis
- **Trail of Bits** : https://www.trailofbits.com/ (audit externe)
- **OpenZeppelin** : https://www.openzeppelin.com/ (audit externe)
- **Immunefi** : https://www.immunefi.com/ (bug bounty)

---

*Last updated: June 2026 — v4.2*
