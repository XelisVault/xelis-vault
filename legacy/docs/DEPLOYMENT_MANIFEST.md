# Deployment Manifest — XELIS Vault

> **Dernière mise à jour :** 9 août 2026 — v10.2
>
> Ce document liste TOUS les contrats du protocole, classés par priorité de déploiement.
> Les outils de déploiement automatiques (Miya ou autres) DOIVENT respecter cet ordre.

---

## 🚨 RÈGLE D'OR

```
┌──────────────────────────────────────────────────────────────────┐
│  NE DÉPLOYER QUE LES CONTRATS DE PHASE 1 (CORE v5.0)             │
│  AU DÉMARRAGE DU TESTNET.                                        │
│                                                                  │
│  LES CONTRATS DE PHASE 5+ (v10.2 BRAINSTORMING) NE SONT PAS      │
│  PRIORITAIRES — NE PAS LES DÉPLOYER TANT QUE :                   │
│    1. Les 37 contrats core ne sont pas déployés                  │
│    2. Le testnet n'est pas stable                                │
│    3. L'audit externe n'est pas fait                             │
│    4. Il reste du temps à la toute fin                           │
└──────────────────────────────────────────────────────────────────┘
```

---

## ✅ Phase 1 — CORE (37 contrats, à déployer en premier)

Ces 37 contrats sont le cœur du protocole. **Ils doivent être déployés dans l'ordre ci-dessous** (voir `deploy/deploy_testnet.py`).

### 1. Infrastructure (2 contrats)
| # | Contract | File | Notes |
|---|----------|------|-------|
| 1 | ContractRegistry | `contracts/proxy/ContractRegistry.slx` | Doit être déployé en premier |
| 2 | ComplianceModule | `contracts/compliance/ComplianceModule.slx` | KYC/AML ZK |

### 2. Token Layer (3 contrats)
| # | Contract | File | Notes |
|---|----------|------|-------|
| 4 | VLTToken | `contracts/token/VLTToken.slx` | 10M supply, deflationary |
| 5 | xUSD | `contracts/usd/xUSD.slx` | Stablecoin, elastic supply |
| 6 | FaucetContract | `contracts/faucet/FaucetContract.slx` | Testnet only |

### 3. Mining & Oracle (3 contrats)
| # | Contract | File | Notes |
|---|----------|------|-------|
| 7 | XelisVaultMiner | `contracts/miner/XelisVaultMiner.slx` | Stake 100 VLT, reputation, slashing |
| 8 | StakedOracle | `contracts/oracle/StakedOracle.slx` | Decentralized median oracle |
| 9 | MinerPool | `contracts/miner/MinerPool.slx` | Optional pool for miners |

### 4. Core Lending (4 contrats)
| # | Contract | File | Notes |
|---|----------|------|-------|
| 10 | VaultEngineV3 | `contracts/vault/VaultEngineV3.slx` | CDP, deposit/borrow/repay/liquidate |
| 11 | InterestRateModel | `contracts/interest/InterestRateModel.slx` | Kinked rates |
| 12 | SavingsRate | `contracts/savings/SavingsRate.slx` | xUSD yield |
| 13 | FlashLoan | `contracts/flashloan/FlashLoan.slx` | Uncollateralized flash loans |
| 14 | FlashCallback | `contracts/flashloan/FlashCallback.slx` | Flash loan callback interface |

### 5. AMM (2 contrats)
| # | Contract | File | Notes |
|---|----------|------|-------|
| 15 | VaultSwapV2 | `contracts/amm/VaultSwapV2.slx` | Custom AMM + TWAP |
| 16 | PSM | `contracts/amm/PSM.slx` | Peg Stability Module xUSD↔XEL |

### 6. Lending Markets (3 contrats)
| # | Contract | File | Notes |
|---|----------|------|-------|
| 17 | LendingMarket | `contracts/lending/LendingMarket.slx` | Multi-pool P2P lending |
| 18 | PeerLoan | `contracts/lending/PeerLoan.slx` | Bilateral P2P loans |
| 19 | SyndicatePool | `contracts/lending/SyndicatePool.slx` | Multi-lender syndicated loans |

### 7. Auctions & Privacy (2 contrats)
| # | Contract | File | Notes |
|---|----------|------|-------|
| 20 | SealedBidAuction | `contracts/auction/SealedBidAuction.slx` | Confidential sealed-bid auctions |
| 21 | PrivacyMixer | `contracts/privacy/PrivacyMixer.slx` | ZK anonymity mixer |

### 8. Tokenization & Treasury (4 contracts)
| # | Contract | File | Notes |
|---|----------|------|-------|
| 22 | AssetVault | `contracts/rwa/AssetVault.slx` | RWA tokenization standard |
| 23 | TreasuryVault | `contracts/treasury/TreasuryVault.slx` | Multi-sig treasury |
| 24 | RevenueShare | `contracts/revenue/RevenueShare.slx` | Confidential revenue distribution |
| 25 | Payroll | `contracts/payroll/Payroll.slx` | Private recurring payments |

### 9. Insurance (2 contrats)
| # | Contract | File | Notes |
|---|----------|------|-------|
| 26 | InsurancePool | `contracts/insurance/InsurancePool.slx` | Community-backed insurance |
| 27 | PrivateInsurance | `contracts/insurance/PrivateInsurance.slx` | P2P insurance & derivatives |

### 10. Governance (4 contrats)
| # | Contract | File | Notes |
|---|----------|------|-------|
| 28 | GovernanceVault | `contracts/governance/GovernanceVault.slx` | VLT staking + voting |
| 29 | Governor | `contracts/governance/Governor.slx` | Proposal lifecycle |
| 30 | Timelock | `contracts/governance/Timelock.slx` | 48h timelock on param changes |
| 31 | GuardianMultisig | `contracts/governance/GuardianMultisig.slx` | Emergency multisig |
| 32 | OracleGovernance | `contracts/governance/OracleGovernance.slx` | Oracle feed management |

### 11. Chat (1 contract)
| # | Contract | File | Notes |
|---|----------|------|-------|
| 33 | VaultChat | `contracts/chat/VaultChat.slx` | E2E encrypted messaging (125 functions) |

### 12. Founder & Fee Distribution (3 contrats, v10.3-v10.4.3)
| # | Contract | File | Notes |
|---|----------|------|-------|
| 34 | FounderVesting | `contracts/founder/FounderVesting.slx` | Vesting 4y + 10y pour le founder |
| 35 | FeeDistributor | `contracts/founder/FeeDistributor.slx` | Répartit fees : 50% burn, 40% treasury, 10% founder |
| 36 | RevenueShareDelegation | `contracts/founder/RevenueShareDelegation.slx` | Partage revenus founder avec contributeurs (durée + %) |

### 13. Airdrop (2 contrats, v10.4)
| # | Contract | File | Notes |
|---|----------|------|-------|
| 37 | AirdropTracker | `contracts/airdrop/AirdropTracker.slx` | TESTNET — accumule points contribution |
| 38 | AirdropClaim | `contracts/airdrop/AirdropClaim.slx` | MAINNET — distribution Merkle proof |

---

## ⛔ Phase 5+ — BRAINSTORMING (13 contrats, NE PAS DÉPLOYER MAINTENANT)

Ces 13 contrats sont des **features brainstorming v10.2**. Ils sont marqués `⚠️ DEPLOYMENT STATUS: PENDING` dans leur en-tête.

**Conditions de déploiement (toutes doivent être vraies) :**
1. ✅ Les 37 contrats core sont déployés et fonctionnels
2. ✅ Le testnet est stable depuis ≥ 4 semaines
3. ✅ L'audit externe est terminé
4. ✅ La governance a voté pour activer la feature
5. ✅ Il reste du temps à la toute fin

| # | Contract | File | Feature | Priority |
|---|----------|------|---------|----------|
| 40 | NotificationCenter | `contracts/notifications/NotificationCenter.slx` | Encrypted notifications | P5 |
| 41 | CreditScore | `contracts/credit/CreditScore.slx` | On-chain credit reputation | P5 |
| 42 | EmergencyShutdown | `contracts/safety/EmergencyShutdown.slx` | Global circuit breaker | P5 |
| 43 | GovernanceDelegation | `contracts/governance/GovernanceDelegation.slx` | Liquid democracy | P5 |
| 44 | VaultInsurance | `contracts/insurance/VaultInsurance.slx` | Auto-insurance vs liquidation | P5 |
| 45 | AnalyticsCollector | `contracts/analytics/AnalyticsCollector.slx` | On-chain metrics | P5 |
| 46 | LiquidationMarket | `contracts/liquidation/LiquidationMarket.slx` | Liquidator marketplace | P5 |
| 47 | VaultBounties | `contracts/liquidation/VaultBounties.slx` | Watcher bounties | P5 |
| 48 | SocialTrading | `contracts/social/SocialTrading.slx` | Copy trading | P5 |
| 49 | YieldOptimizer | `contracts/vault/YieldOptimizer.slx` | Auto yield optimization | P5 |
| 50 | VaultTemplates | `contracts/vault/VaultTemplates.slx` | One-click strategies | P5 |
| 51 | MultiCollateralVault | `contracts/vault/MultiCollateralVault.slx` | Multi-asset collateral | P5 |
| 52 | VaultNFT | `contracts/nft/VaultNFT.slx` | Tokenized positions | P5 |

---

## 📋 Checklist de déploiement pour outils automatiques (Miya, etc.)

```
□ ÉTAPE 1 : Déployer ContractRegistry (entry point de tout)
□ ÉTAPE 2 : Déployer VLTToken + xUSD
□ ÉTAPE 3 : Déployer XelisVaultMiner + StakedOracle
□ ÉTAPE 4 : Déployer VaultEngineV3 + InterestRateModel + SavingsRate
□ ÉTAPE 5 : Déployer FlashLoan + FlashCallback
□ ÉTAPE 6 : Déployer VaultSwapV2 + PSM
□ ÉTAPE 7 : Déployer LendingMarket + PeerLoan + SyndicatePool
□ ÉTAPE 8 : Déployer SealedBidAuction + PrivacyMixer
□ ÉTAPE 9 : Déployer AssetVault + TreasuryVault + RevenueShare + Payroll
□ ÉTAPE 10 : Déployer InsurancePool + PrivateInsurance
□ ÉTAPE 11 : Déployer GovernanceVault + Governor + Timelock + GuardianMultisig + OracleGovernance
□ ÉTAPE 12 : Déployer VaultChat
□ ÉTAPE 13 : Déployer FaucetContract (testnet only)
□ ÉTAPE 14 : Déployer ComplianceModule
□ ÉTAPE 15 : Wire tous les contrats (set_registry, set_oracle, etc.)
□ ÉTAPE 16 : Vérifier les 23 chunk IDs cross-contract (validate_chunk_ids.py)
□ ÉTAPE 17 : Lancer les tests (tests/test_all_contracts.py --live)

⛔ NE PAS DÉPLOYER LES 13 CONTRATS BRAINSTORMING — PHASE 5+ ONLY
```

---

## 🔍 Comment identifier un contrat brainstorming

Tous les contrats brainstorming v10.2 ont dans leur en-tête :

```
// ⚠️  DEPLOYMENT STATUS: PENDING — DO NOT DEPLOY YET
```

Si un outil de déploiement voit ce marqueur, il doit SKIP le contrat.

---

*XELIS Vault — Deployment Manifest v10.2*
