# XELIS Vault — Guide de Déploiement Complet

> **Version :** v10.5
> **Date :** 9 août 2026
> **Objectif :** Déployer le protocole dans le bon ordre, avec la bonne configuration
>
> Ce guide est conçu pour être suivi **étape par étape**. Chaque étape doit être
> complétée avant de passer à la suivante. Ne sautez aucune étape.

---

## 📋 Pré-requis

Avant de commencer, vous devez avoir :

1. **Le compilateur Silex officiel** (xelis-vm) installé
2. **Un wallet XELIS** (Genesix ou CLI) avec assez de XEL pour les gas
3. **Le code source** : `git clone https://github.com/XelisVault/xelis-vault.git`
4. **Le script de déploiement** : `python3 deploy/deploy_testnet.py --help`
5. **14 adresses prêtes** : admin, founder, guardian×5 (multisig), emergency, treasury, etc.

---

## 🎯 Vue d'ensemble

```
37 contrats core à déployer dans cet ordre :

Phase 1 : Infrastructure (2 contrats)
  1. ContractRegistry
  2. ComplianceModule

Phase 2 : Token Layer (3 contrats)
  3. VLTToken
  4. xUSD
  5. FaucetContract (testnet only)

Phase 3 : Mining & Oracle (3 contrats)
  6. XelisVaultMiner
  7. StakedOracle
  8. MinerPool

Phase 4 : Core Lending (5 contrats)
  9. InterestRateModel
  10. VaultEngineV3
  11. SavingsRate
  12. FlashLoan
  13. FlashCallback

Phase 5 : AMM (2 contrats)
  14. VaultSwapV2
  15. PSM

Phase 6 : Lending Markets (3 contrats)
  16. LendingMarket
  17. PeerLoan
  18. SyndicatePool

Phase 7 : Auctions & Privacy (2 contrats)
  19. SealedBidAuction
  20. PrivacyMixer

Phase 8 : Tokenization & Treasury (4 contrats)
  21. AssetVault
  22. TreasuryVault
  23. RevenueShare
  24. Payroll

Phase 9 : Insurance (2 contrats)
  25. InsurancePool
  26. PrivateInsurance

Phase 10 : Governance (4 contrats)
  27. GovernanceVault
  28. Governor
  29. Timelock
  30. GuardianMultisig
  31. OracleGovernance

Phase 11 : Chat (1 contract)
  32. VaultChat

Phase 12 : Founder & Fees (3 contrats)
  33. FounderVesting (instance 1 : 4 ans)
  34. FounderVesting (instance 2 : 10 ans)
  35. FeeDistributor
  36. MinerDelegation

Phase 13 : Airdrop (2 contrats)
  37. AirdropTracker (TESTNET)
  38. AirdropClaim (MAINNET, déployé plus tard)

TOTAL : 38 contrats core (37 sur testnet + 1 sur mainnet)
```

---

## 🚀 PHASE 1 : Infrastructure

### Étape 1.1 — Déployer ContractRegistry

```bash
# Compiler
xelis-compile contracts/proxy/ContractRegistry.slx

# Déployer (le caller devient admin)
xelis-deploy ContractRegistry.bytecode
# → Sauvegarder le hash retourné : REGISTRY_HASH
```

**Configuration immédiate :**
```bash
# Aucune config requise (admin = caller par défaut)
# Vérifier :
xelis-call REGISTRY_HASH get_version_str
# → Doit retourner "ContractRegistry v5.0"
```

### Étape 1.2 — Déployer ComplianceModule

```bash
xelis-compile contracts/compliance/ComplianceModule.slx
xelis-deploy ComplianceModule.bytecode
# → Sauvegarder : COMPLIANCE_HASH
```

**Configuration :**
```bash
# set_registry (entry)
xelis-call COMPLIANCE_HASH set_registry [REGISTRY_HASH]
# set_timelock (entry) — sera configuré après le déploiement de Timelock
# set_guardian (entry) — sera configuré après le déploiement de GuardianMultisig
```

---

## 🪙 PHASE 2 : Token Layer

### Étape 2.1 — Déployer VLTToken

```bash
xelis-compile contracts/token/VLTToken.slx
xelis-deploy VLTToken.bytecode
# → Sauvegarder : VLT_CONTRACT_HASH, VLT_ASSET_HASH (retourné par create_asset)
```

**Configuration :**
```bash
# set_registry (entry 6)
xelis-call VLT_CONTRACT_HASH set_registry [REGISTRY_HASH]

# Enregistrer dans le registry
xelis-call REGISTRY_HASH register ["VLTToken", VLT_CONTRACT_HASH]
```

### Étape 2.2 — Déployer xUSD

```bash
xelis-compile contracts/usd/xUSD.slx
xelis-deploy xUSD.bytecode
# → Sauvegarder : XUSD_CONTRACT_HASH, XUSD_ASSET_HASH
```

**Configuration :**
```bash
# set_registry (entry)
xelis-call XUSD_CONTRACT_HASH set_registry [REGISTRY_HASH]

# Enregistrer dans le registry
xelis-call REGISTRY_HASH register ["xUSD", XUSD_CONTRACT_HASH]
```

### Étape 2.3 — Déployer FaucetContract (testnet only)

```bash
xelis-compile contracts/faucet/FaucetContract.slx
xelis-deploy FaucetContract.bytecode
# → Sauvegarder : FAUCET_HASH
```

**Configuration :**
```bash
xelis-call FAUCET_HASH set_registry [REGISTRY_HASH]
# Refill le faucet plus tard (après mint des VLT)
```

---

## ⛏️ PHASE 3 : Mining & Oracle

### Étape 3.1 — Déployer XelisVaultMiner

```bash
xelis-compile contracts/miner/XelisVaultMiner.slx
xelis-deploy XelisVaultMiner.bytecode
# → Sauvegarder : MINER_CONTRACT_HASH
```

**Configuration :**
```bash
# set_registry (entry)
xelis-call MINER_CONTRACT_HASH set_registry [REGISTRY_HASH]

# set_vlt_contract (entry) — pour mint les rewards
xelis-call MINER_CONTRACT_HASH set_vlt_contract [VLT_CONTRACT_HASH]

# set_vlt_asset (entry) — pour les transferts
xelis-call MINER_CONTRACT_HASH set_vlt_asset [VLT_ASSET_HASH]

# Enregistrer dans le registry
xelis-call REGISTRY_HASH register ["XelisVaultMiner", MINER_CONTRACT_HASH]
```

### Étape 3.2 — Déployer StakedOracle

```bash
xelis-compile contracts/oracle/StakedOracle.slx
xelis-deploy StakedOracle.bytecode
# → Sauvegarder : ORACLE_HASH
```

**Configuration (ORDRE IMPORTANT) :**
```bash
# 1. set_registry
xelis-call ORACLE_HASH set_registry [REGISTRY_HASH]

# 2. set_miner_contract (entry 9) — CRITIQUE, l'oracle a besoin du miner
xelis-call ORACLE_HASH set_miner_contract [MINER_CONTRACT_HASH]

# 3. add_feed (pub fn) — ajouter le feed XEL/USD
#    Paramètres : name="XEL/USD", asset=Hash::zero() (XEL), decimals=8, min_price=1, max_price=100000000000
xelis-call ORACLE_HASH add_feed ["XEL/USD", "0x0000...0000", 8, 1, 100000000000]

# Enregistrer dans le registry
xelis-call REGISTRY_HASH register ["StakedOracle", ORACLE_HASH]

# 4. Autoriser StakedOracle comme service sur XelisVaultMiner
#    register_service sur le miner (entry)
xelis-call MINER_CONTRACT_HASH set_authorized_service [ORACLE_HASH, 1]
#    (service_id=1 pour oracle)
```

### Étape 3.3 — Déployer MinerPool

```bash
xelis-compile contracts/miner/MinerPool.slx
xelis-deploy MinerPool.bytecode
# → Sauvegarder : MINERPOOL_HASH
```

**Configuration :**
```bash
xelis-call MINERPOOL_HASH set_registry [REGISTRY_HASH]
# set_miner_contract (entry) — pour interagir avec XelisVaultMiner
xelis-call MINERPOOL_HASH set_miner_contract [MINER_CONTRACT_HASH]
xelis-call MINERPOOL_HASH set_vlt_asset [VLT_ASSET_HASH]

xelis-call REGISTRY_HASH register ["MinerPool", MINERPOOL_HASH]
```

---

## 🏦 PHASE 4 : Core Lending

### Étape 4.1 — Déployer InterestRateModel

```bash
xelis-compile contracts/interest/InterestRateModel.slx
xelis-deploy InterestRateModel.bytecode
# → Sauvegarder : IRM_HASH
```

**Configuration :**
```bash
# set_rates (entry 4) — configurer les taux
# Paramètres : base=50, multiplier=1000, jump=5000, kink=8000
xelis-call IRM_HASH set_rates [50, 1000, 5000, 8000]

xelis-call REGISTRY_HASH register ["InterestRateModel", IRM_HASH]
```

### Étape 4.2 — Déployer VaultEngineV3

```bash
xelis-compile contracts/vault/VaultEngineV3.slx
xelis-deploy VaultEngineV3.bytecode
# → Sauvegarder : VAULTENGINE_HASH
```

**Configuration (ORDRE CRITIQUE) :**
```bash
# 1. set_registry
xelis-call VAULTENGINE_HASH set_registry [REGISTRY_HASH]

# 2. set_oracle (entry) — pour lire les prix XEL
xelis-call VAULTENGINE_HASH set_oracle [ORACLE_HASH]

# 3. set_xusd_contract (entry) — pour mint/burn xUSD
xelis-call VAULTENGINE_HASH set_xusd_contract [XUSD_CONTRACT_HASH]

# 4. set_xusd_asset (entry) — asset hash pour transferts
xelis-call VAULTENGINE_HASH set_xusd_asset [XUSD_ASSET_HASH]

# 5. set_treasury (entry) — adresse du treasury (sera TreasuryVault plus tard)
#    Pour l'instant, utiliser une adresse temporaire
xelis-call VAULTENGINE_HASH set_treasury [TREASURY_TEMP_ADDR]

# Enregistrer
xelis-call REGISTRY_HASH register ["VaultEngine", VAULTENGINE_HASH]

# 6. Autoriser VaultEngine comme minter sur xUSD (CRITIQUE)
#    xUSD entry = set_minter
xelis-call XUSD_CONTRACT_HASH set_minter [VAULTENGINE_HASH, true]

# 7. Autoriser VaultEngine comme burner sur xUSD
xelis-call XUSD_CONTRACT_HASH set_burner [VAULTENGINE_HASH, true]
```

### Étape 4.3 — Déployer SavingsRate

```bash
xelis-compile contracts/savings/SavingsRate.slx
xelis-deploy SavingsRate.bytecode
# → Sauvegarder : SAVINGS_HASH
```

**Configuration :**
```bash
xelis-call SAVINGS_HASH set_registry [REGISTRY_HASH]
xelis-call SAVINGS_HASH set_xusd_contract [XUSD_CONTRACT_HASH]
xelis-call SAVINGS_HASH set_xusd_asset [XUSD_ASSET_HASH]
xelis-call SAVINGS_HASH set_treasury [TREASURY_TEMP_ADDR]

# Autoriser SavingsRate comme minter sur xUSD
xelis-call XUSD_CONTRACT_HASH set_minter [SAVINGS_HASH, true]

xelis-call REGISTRY_HASH register ["SavingsRate", SAVINGS_HASH]
```

### Étape 4.4 — Déployer FlashLoan + FlashCallback

```bash
xelis-compile contracts/flashloan/FlashCallback.slx
xelis-deploy FlashCallback.bytecode
# → Sauvegarder : CALLBACK_HASH

xelis-compile contracts/flashloan/FlashLoan.slx
xelis-deploy FlashLoan.bytecode
# → Sauvegarder : FLASHLOAN_HASH
```

**Configuration :**
```bash
xelis-call FLASHLOAN_HASH set_registry [REGISTRY_HASH]
xelis-call FLASHLOAN_HASH set_treasury [TREASURY_TEMP_ADDR]

# Whitelister les callback contracts autorisés
xelis-call FLASHLOAN_HASH verify_callback [CALLBACK_HASH]

xelis-call REGISTRY_HASH register ["FlashLoan", FLASHLOAN_HASH]
xelis-call REGISTRY_HASH register ["FlashCallback", CALLBACK_HASH]
```

---

## 🔄 PHASE 5 : AMM

### Étape 5.1 — Déployer VaultSwapV2

```bash
xelis-compile contracts/amm/VaultSwapV2.slx
xelis-deploy VaultSwapV2.bytecode
# → Sauvegarder : VAULTSWAP_HASH
```

**Configuration :**
```bash
xelis-call VAULTSWAP_HASH set_registry [REGISTRY_HASH]
xelis-call VAULTSWAP_HASH set_oracle [ORACLE_HASH]
xelis-call VAULTSWAP_HASH set_xusd_contract [XUSD_CONTRACT_HASH]
xelis-call VAULTSWAP_HASH set_xusd_asset [XUSD_ASSET_HASH]
xelis-call VAULTSWAP_HASH set_treasury [TREASURY_TEMP_ADDR]

# Autoriser comme minter/burner sur xUSD
xelis-call XUSD_CONTRACT_HASH set_minter [VAULTSWAP_HASH, true]
xelis-call XUSD_CONTRACT_HASH set_burner [VAULTSWAP_HASH, true]

xelis-call REGISTRY_HASH register ["VaultSwap", VAULTSWAP_HASH]
```

### Étape 5.2 — Déployer PSM

```bash
xelis-compile contracts/amm/PSM.slx
xelis-deploy PSM.bytecode
# → Sauvegarder : PSM_HASH
```

**Configuration :**
```bash
xelis-call PSM_HASH set_registry [REGISTRY_HASH]
xelis-call PSM_HASH set_oracle [ORACLE_HASH]
xelis-call PSM_HASH set_xusd_contract [XUSD_CONTRACT_HASH]
xelis-call PSM_HASH set_xusd_asset [XUSD_ASSET_HASH]
xelis-call PSM_HASH set_treasury [TREASURY_TEMP_ADDR]

# Autoriser comme minter/burner sur xUSD
xelis-call XUSD_CONTRACT_HASH set_minter [PSM_HASH, true]
xelis-call XUSD_CONTRACT_HASH set_burner [PSM_HASH, true]

xelis-call REGISTRY_HASH register ["PSM", PSM_HASH]
```

---

## 💰 PHASE 6 : Lending Markets

### Étape 6.1 — Déployer LendingMarket

```bash
xelis-compile contracts/lending/LendingMarket.slx
xelis-deploy LendingMarket.bytecode
# → Sauvegarder : LENDINGMARKET_HASH
```

**Configuration :**
```bash
xelis-call LENDINGMARKET_HASH set_registry [REGISTRY_HASH]
xelis-call LENDINGMARKET_HASH set_oracle [ORACLE_HASH]
xelis-call LENDINGMARKET_HASH set_irm [IRM_HASH]
xelis-call LENDINGMARKET_HASH set_treasury [TREASURY_TEMP_ADDR]

xelis-call REGISTRY_HASH register ["LendingMarket", LENDINGMARKET_HASH]
```

### Étape 6.2 — Déployer PeerLoan

```bash
xelis-compile contracts/lending/PeerLoan.slx
xelis-deploy PeerLoan.bytecode
# → Sauvegarder : PEERLOAN_HASH
```

**Configuration :**
```bash
xelis-call PEERLOAN_HASH set_registry [REGISTRY_HASH]
xelis-call PEERLOAN_HASH set_oracle [ORACLE_HASH]
xelis-call PEERLOAN_HASH set_treasury [TREASURY_TEMP_ADDR]

xelis-call REGISTRY_HASH register ["PeerLoan", PEERLOAN_HASH]
```

### Étape 6.3 — Déployer SyndicatePool

```bash
xelis-compile contracts/lending/SyndicatePool.slx
xelis-deploy SyndicatePool.bytecode
# → Sauvegarder : SYNDICATE_HASH
```

**Configuration :**
```bash
xelis-call SYNDICATE_HASH set_registry [REGISTRY_HASH]
xelis-call SYNDICATE_HASH set_oracle [ORACLE_HASH]
xelis-call SYNDICATE_HASH set_treasury [TREASURY_TEMP_ADDR]

xelis-call REGISTRY_HASH register ["SyndicatePool", SYNDICATE_HASH]
```

---

## 🔒 PHASE 7 : Auctions & Privacy

### Étape 7.1 — Déployer SealedBidAuction

```bash
xelis-compile contracts/auction/SealedBidAuction.slx
xelis-deploy SealedBidAuction.bytecode
# → Sauvegarder : AUCTION_HASH
```

**Configuration :**
```bash
xelis-call AUCTION_HASH set_registry [REGISTRY_HASH]
xelis-call REGISTRY_HASH register ["SealedBidAuction", AUCTION_HASH]
```

### Étape 7.2 — Déployer PrivacyMixer

```bash
xelis-compile contracts/privacy/PrivacyMixer.slx
xelis-deploy PrivacyMixer.bytecode
# → Sauvegarder : MIXER_HASH
```

**Configuration :**
```bash
xelis-call MIXER_HASH set_registry [REGISTRY_HASH]
xelis-call REGISTRY_HASH register ["PrivacyMixer", MIXER_HASH]
```

---

## 🏛️ PHASE 8 : Tokenization & Treasury

### Étape 8.1 — Déployer AssetVault

```bash
xelis-compile contracts/rwa/AssetVault.slx
xelis-deploy AssetVault.bytecode
# → Sauvegarder : ASSETVAULT_HASH
```

**Configuration :**
```bash
xelis-call ASSETVAULT_HASH set_registry [REGISTRY_HASH]
xelis-call ASSETVAULT_HASH set_compliance [COMPLIANCE_HASH]

xelis-call REGISTRY_HASH register ["AssetVault", ASSETVAULT_HASH]
```

### Étape 8.2 — Déployer TreasuryVault

```bash
xelis-compile contracts/treasury/TreasuryVault.slx
xelis-deploy TreasuryVault.bytecode
# → Sauvegarder : TREASURY_HASH
```

**Configuration :**
```bash
xelis-call TREASURY_HASH set_registry [REGISTRY_HASH]
xelis-call REGISTRY_HASH register ["TreasuryVault", TREASURY_HASH]

# CRITIQUE : Maintenant que TreasuryVault est déployé, mettre à jour
# tous les contrats qui utilisaient TREASURY_TEMP_ADDR
# set_treasury sur : VaultEngine, SavingsRate, FlashLoan, VaultSwap, PSM, LendingMarket, PeerLoan, SyndicatePool
xelis-call VAULTENGINE_HASH set_treasury [TREASURY_HASH]
xelis-call SAVINGS_HASH set_treasury [TREASURY_HASH]
xelis-call FLASHLOAN_HASH set_treasury [TREASURY_HASH]
xelis-call VAULTSWAP_HASH set_treasury [TREASURY_HASH]
xelis-call PSM_HASH set_treasury [TREASURY_HASH]
xelis-call LENDINGMARKET_HASH set_treasury [TREASURY_HASH]
xelis-call PEERLOAN_HASH set_treasury [TREASURY_HASH]
xelis-call SYNDICATE_HASH set_treasury [TREASURY_HASH]
```

### Étape 8.3 — Déployer RevenueShare

```bash
xelis-compile contracts/revenue/RevenueShare.slx
xelis-deploy RevenueShare.bytecode
# → Sauvegarder : REVENUE_HASH
```

**Configuration :**
```bash
xelis-call REVENUE_HASH set_registry [REGISTRY_HASH]
xelis-call REVENUE_HASH set_vlt_asset [VLT_ASSET_HASH]
xelis-call REGISTRY_HASH register ["RevenueShare", REVENUE_HASH]
```

### Étape 8.4 — Déployer Payroll

```bash
xelis-compile contracts/payroll/Payroll.slx
xelis-deploy Payroll.bytecode
# → Sauvegarder : PAYROLL_HASH
```

**Configuration :**
```bash
xelis-call PAYROLL_HASH set_registry [REGISTRY_HASH]
xelis-call PAYROLL_HASH set_treasury [TREASURY_HASH]
xelis-call REGISTRY_HASH register ["Payroll", PAYROLL_HASH]
```

---

## 🛡️ PHASE 9 : Insurance

### Étape 9.1 — Déployer InsurancePool

```bash
xelis-compile contracts/insurance/InsurancePool.slx
xelis-deploy InsurancePool.bytecode
# → Sauvegarder : INSURANCE_HASH
```

**Configuration :**
```bash
xelis-call INSURANCE_HASH set_registry [REGISTRY_HASH]
xelis-call INSURANCE_HASH set_treasury [TREASURY_HASH]
xelis-call REGISTRY_HASH register ["InsurancePool", INSURANCE_HASH]
```

### Étape 9.2 — Déployer PrivateInsurance

```bash
xelis-compile contracts/insurance/PrivateInsurance.slx
xelis-deploy PrivateInsurance.bytecode
# → Sauvegarder : PRIVINSURANCE_HASH
```

**Configuration :**
```bash
xelis-call PRIVINSURANCE_HASH set_registry [REGISTRY_HASH]
xelis-call PRIVINSURANCE_HASH set_treasury [TREASURY_HASH]
xelis-call REGISTRY_HASH register ["PrivateInsurance", PRIVINSURANCE_HASH]
```

---

## 🏛️ PHASE 10 : Governance

### Étape 10.1 — Déployer GovernanceVault

```bash
xelis-compile contracts/governance/GovernanceVault.slx
xelis-deploy GovernanceVault.bytecode
# → Sauvegarder : GOVVAULT_HASH
```

**Configuration :**
```bash
xelis-call GOVVAULT_HASH set_registry [REGISTRY_HASH]
xelis-call GOVVAULT_HASH set_vlt_contract [VLT_CONTRACT_HASH]
xelis-call GOVVAULT_HASH set_vlt_asset [VLT_ASSET_HASH]
xelis-call REGISTRY_HASH register ["GovernanceVault", GOVVAULT_HASH]
```

### Étape 10.2 — Déployer Timelock

```bash
xelis-compile contracts/governance/Timelock.slx
xelis-deploy Timelock.bytecode
# → Sauvegarder : TIMELOCK_HASH
```

**Configuration :**
```bash
xelis-call TIMELOCK_HASH set_registry [REGISTRY_HASH]
xelis-call REGISTRY_HASH register ["Timelock", TIMELOCK_HASH]
```

### Étape 10.3 — Déployer GuardianMultisig

```bash
xelis-compile contracts/governance/GuardianMultisig.slx
xelis-deploy GuardianMultisig.bytecode
# → Sauvegarder : GUARDIAN_HASH
```

**Configuration :**
```bash
xelis-call GUARDIAN_HASH set_registry [REGISTRY_HASH]
xelis-call GUARDIAN_HASH set_timelock [TIMELOCK_HASH]

# Ajouter les 5 guardians (entry add_signer)
# Puis set_quorum à 3 (sur 5)
xelis-call GUARDIAN_HASH set_quorum [3]

xelis-call REGISTRY_HASH register ["GuardianMultisig", GUARDIAN_HASH]
```

### Étape 10.4 — Déployer Governor

```bash
xelis-compile contracts/governance/Governor.slx
xelis-deploy Governor.bytecode
# → Sauvegarder : GOVERNOR_HASH
```

**Configuration (ORDRE CRITIQUE) :**
```bash
# 1. set_registry
xelis-call GOVERNOR_HASH set_registry [REGISTRY_HASH]

# 2. set_governance_vault (entry) — pour lire le voting power
xelis-call GOVERNOR_HASH set_governance_vault [GOVVAULT_HASH]

# 3. set_timelock (entry) — pour soumettre les proposals au timelock
xelis-call GOVERNOR_HASH set_timelock [TIMELOCK_HASH]

xelis-call REGISTRY_HASH register ["Governor", GOVERNOR_HASH]
```

### Étape 10.5 — Déployer OracleGovernance

```bash
xelis-compile contracts/governance/OracleGovernance.slx
xelis-deploy OracleGovernance.bytecode
# → Sauvegarder : ORACLEGOV_HASH
```

**Configuration :**
```bash
xelis-call ORACLEGOV_HASH set_registry [REGISTRY_HASH]
xelis-call ORACLEGOV_HASH set_governance_vault [GOVVAULT_HASH]
xelis-call ORACLEGOV_HASH set_oracle [ORACLE_HASH]
xelis-call REGISTRY_HASH register ["OracleGovernance", ORACLEGOV_HASH]
```

---

## 💬 PHASE 11 : Chat

### Étape 11.1 — Déployer VaultChat

```bash
xelis-compile contracts/chat/VaultChat.slx
xelis-deploy VaultChat.bytecode
# → Sauvegarder : CHAT_HASH
```

**Configuration (ORDRE CRITIQUE) :**
```bash
# 1. set_registry
xelis-call CHAT_HASH set_registry [REGISTRY_HASH]

# 2. set_miner_contract (entry) — pour les rewards relayer
xelis-call CHAT_HASH set_miner_contract [MINER_CONTRACT_HASH]

# 3. Autoriser VaultChat comme service sur XelisVaultMiner
#    service_id=2 pour chat
xelis-call MINER_CONTRACT_HASH set_authorized_service [CHAT_HASH, 2]

xelis-call REGISTRY_HASH register ["VaultChat", CHAT_HASH]
```

---

## 💰 PHASE 12 : Founder & Fees

### Étape 12.1 — Déployer FounderVesting (Instance 1 : 4 ans)

```bash
xelis-compile contracts/founder/FounderVesting.slx
xelis-deploy FounderVesting.bytecode
# → Sauvegarder : FOUNDER_VESTING_1_HASH
```

**Configuration :**
```bash
# set_founder (entry 4) — ton adresse
xelis-call FOUNDER_VESTING_1_HASH set_founder [FOUNDER_ADDR]

# set_vlt_contract (entry 5)
xelis-call FOUNDER_VESTING_1_HASH set_vlt_contract [VLT_CONTRACT_HASH]

# set_vlt_asset (entry 6)
xelis-call FOUNDER_VESTING_1_HASH set_vlt_asset [VLT_ASSET_HASH]

# Mint 500,000 VLT au contrat de vesting
# VLTToken entry = mint_to
xelis-call VLT_CONTRACT_HASH mint_to [FOUNDER_VESTING_1_HASH, 50000000000000]

xelis-call REGISTRY_HASH register ["FounderVesting4y", FOUNDER_VESTING_1_HASH]
```

### Étape 12.2 — Déployer FounderVesting (Instance 2 : 10 ans)

```bash
xelis-deploy FounderVesting.bytecode
# → Sauvegarder : FOUNDER_VESTING_2_HASH
```

**Configuration :**
```bash
xelis-call FOUNDER_VESTING_2_HASH set_founder [FOUNDER_ADDR]
xelis-call FOUNDER_VESTING_2_HASH set_vlt_contract [VLT_CONTRACT_HASH]
xelis-call FOUNDER_VESTING_2_HASH set_vlt_asset [VLT_ASSET_HASH]

# IMPORTANT : Changer les paramètres de vesting pour 10 ans
# (modifier TOTAL_AMOUNT, CLIFF, VESTING via storage ou re-déployer avec params différents)
# En production, on déploie une version modifiée avec :
#   CLIFF = 1 year (6307200 blocks)
#   VESTING = 9 years (56764800 blocks)
#   TOTAL = 500,000 VLT

# Mint 500,000 VLT au contrat
xelis-call VLT_CONTRACT_HASH mint_to [FOUNDER_VESTING_2_HASH, 50000000000000]

xelis-call REGISTRY_HASH register ["FounderVesting10y", FOUNDER_VESTING_2_HASH]
```

### Étape 12.3 — Déployer FeeDistributor

```bash
xelis-compile contracts/founder/FeeDistributor.slx
xelis-deploy FeeDistributor.bytecode
# → Sauvegarder : FEEDIST_HASH
```

**Configuration :**
```bash
# set_founder (entry 8) — ton adresse
xelis-call FEEDIST_HASH set_founder [FOUNDER_ADDR]

# set_treasury (entry 9) — le TreasuryVault
xelis-call FEEDIST_HASH set_treasury [TREASURY_HASH]

# set_vlt_contract (entry 10) — pour burn
xelis-call FEEDIST_HASH set_vlt_contract [VLT_CONTRACT_HASH]

xelis-call REGISTRY_HASH register ["FeeDistributor", FEEDIST_HASH]

# CRITIQUE : Maintenant, configurer TOUS les contrats qui génèrent des fees
# pour qu'ils envoient les fees au FeeDistributor au lieu du treasury direct
# (à faire via governance ou admin calls sur chaque contrat)
```

### Étape 12.4 — Déployer MinerDelegation

```bash
xelis-compile contracts/miner/MinerDelegation.slx
xelis-deploy MinerDelegation.bytecode
# → Sauvegarder : DELEGATION_HASH
```

**Configuration (ORDRE CRITIQUE) :**
```bash
# 1. Set VLT asset (pour les transferts natifs)
xelis-call DELEGATION_HASH set_vlt_asset [VLT_ASSET_HASH]

# 2. Set miner contract hash (pour only_miner_contract verification)
xelis-call DELEGATION_HASH set_miner_contract_hash [MINER_CONTRACT_HASH]

# 3. Set registry
xelis-call DELEGATION_HASH set_registry [REGISTRY_HASH]

# Enregistrer dans le registry
xelis-call REGISTRY_HASH register ["MinerDelegation", DELEGATION_HASH]

# 4. CRITIQUE : Configurer XelisVaultMiner pour pousser own_stake vers MinerDelegation
xelis-call MINER_CONTRACT_HASH set_delegation_contract [DELEGATION_HASH]

# 5. CRITIQUE : Configurer StakedOracle pour lire le total stake depuis MinerDelegation
xelis-call ORACLE_HASH set_delegation_contract [DELEGATION_HASH]

# 6. Set cap stake (anti-concentration, default 500,000 VLT)
# Optionnel — le default est déjà 500,000 VLT
# xelis-call DELEGATION_HASH set_cap_stake [50000000000000]
```

**Points critiques :**
- `set_delegation_contract` sur XelisVaultMiner permet de pousser les mises à jour de own_stake
- `set_delegation_contract` sur StakedOracle permet de lire le total stake (own + delegated) pour la médiane pondérée
- Sans ces 2 configurations, la délégation n'affecte pas le poids oracle

---

## 🪂 PHASE 13 : Airdrop

### Étape 13.1 — Déployer AirdropTracker (TESTNET)

```bash
xelis-compile contracts/airdrop/AirdropTracker.slx
xelis-deploy AirdropTracker.bytecode
# → Sauvegarder : AIRDROP_TRACKER_HASH
```

**Configuration :**
```bash
xelis-call AIRDROP_TRACKER_HASH set_registry [REGISTRY_HASH]
xelis-call AIRDROP_TRACKER_HASH set_vlt_contract [VLT_CONTRACT_HASH]

# Autoriser les contrats à enregistrer les points
# (entry 23 : set_authorized_recorder)
xelis-call AIRDROP_TRACKER_HASH set_authorized_recorder [MINER_CONTRACT_HASH, true]
xelis-call AIRDROP_TRACKER_HASH set_authorized_recorder [ORACLE_HASH, true]
xelis-call AIRDROP_TRACKER_HASH set_authorized_recorder [CHAT_HASH, true]
xelis-call AIRDROP_TRACKER_HASH set_authorized_recorder [GOVERNOR_HASH, true]
xelis-call AIRDROP_TRACKER_HASH set_authorized_recorder [VAULTENGINE_HASH, true]
xelis-call AIRDROP_TRACKER_HASH set_authorized_recorder [VAULTSWAP_HASH, true]
xelis-call AIRDROP_TRACKER_HASH set_authorized_recorder [PSM_HASH, true]

# Mint 500,000 VLT au AirdropTracker pour la distribution future
# (sera transféré à AirdropClaim sur mainnet)
xelis-call VLT_CONTRACT_HASH mint_to [TREASURY_HASH, 50000000000000]
# (Les VLT restent au treasury, seront transférés à AirdropClaim au lancement mainnet)

xelis-call REGISTRY_HASH register ["AirdropTracker", AIRDROP_TRACKER_HASH]
```

### Étape 13.2 — AirdropClaim (MAINNET, plus tard)

Ce contrat est déployé sur MAINNET au lancement, pas sur testnet.

```bash
# Sur MAINNET :
xelis-compile contracts/airdrop/AirdropClaim.slx
xelis-deploy AirdropClaim.bytecode
# → Sauvegarder : AIRDROP_CLAIM_HASH

# Configuration :
xelis-call AIRDROP_CLAIM_HASH set_vlt_contract [VLT_CONTRACT_HASH_MAINNET]
xelis-call AIRDROP_CLAIM_HASH set_merkle_root [MERKLE_ROOT]
# (MERKLE_ROOT est calculé par scripts/generate_airdrop_merkle.py après finalize)

# Transférer 500,000 VLT au AirdropClaim
xelis-call VLT_CONTRACT_HASH transfer_to [AIRDROP_CLAIM_HASH, 50000000000000]
```

---

## 🎁 ÉTAPE FINALE : Distribution des VLT

Après le déploiement de tous les contrats, distribuer les 10M VLT :

```bash
# Total : 10,000,000 VLT (10,000,000,000,000,000 atomic)

# 1. Oracle rewards (5,500,000 VLT) → XelisVaultMiner budget
xelis-call VLT_CONTRACT_HASH mint_to [MINER_CONTRACT_HASH, 5500000000000000]

# 2. Chat rewards (1,000,000 VLT) → XelisVaultMiner budget (service_id=2)
# (déjà inclus dans le budget ci-dessus, sera distribué via distribute_reward)

# 3. DEX liquidity (1,000,000 VLT) → TreasuryVault (pour seed les pools plus tard)
xelis-call VLT_CONTRACT_HASH mint_to [TREASURY_HASH, 1000000000000000]

# 4. Founder vesting 4y (500,000 VLT) → déjà minté à l'étape 12.1
# 5. Founder vesting 10y (500,000 VLT) → déjà minté à l'étape 12.2

# 6. Treasury (500,000 VLT) → TreasuryVault
xelis-call VLT_CONTRACT_HASH mint_to [TREASURY_HASH, 50000000000000]

# 7. Community airdrop (500,000 VLT) → TreasuryVault (sera distribué)
xelis-call VLT_CONTRACT_HASH mint_to [TREASURY_HASH, 50000000000000]

# 8. Launch airdrop (200,000 VLT) → TreasuryVault
xelis-call VLT_CONTRACT_HASH mint_to [TREASURY_HASH, 20000000000000]

# 9. Bug bounty (100,000 VLT) → TreasuryVault
xelis-call VLT_CONTRACT_HASH mint_to [TREASURY_HASH, 10000000000000]

# 10. Protocol reserve (200,000 VLT) → TreasuryVault
xelis-call VLT_CONTRACT_HASH mint_to [TREASURY_HASH, 20000000000000]

# Total minté : 5,500,000 + 1,000,000 + 500,000 + 500,000 + 500,000 + 500,000
#             + 200,000 + 100,000 + 200,000 + 1,000,000 (chat)
# = 10,000,000 VLT ✅
```

---

## ✅ Vérification finale

```bash
# 1. Vérifier le nombre de contrats enregistrés
xelis-call REGISTRY_HASH list_names_entry
# → Doit retourner 37 noms

# 2. Vérifier le supply VLT
xelis-call VLT_CONTRACT_HASH get_asset_info_entry
# → Total supply = 10,000,000 VLT

# 3. Vérifier l'oracle
xelis-call ORACLE_HASH get_feed ["XEL/USD"]
# → Doit retourner le feed avec active=true

# 4. Tester un petit deposit
# (via le CLI : xvault → Vault → Deposit)

# 5. Lancer le validateur
python3 scripts/validate_chunk_ids.py
# → Doit afficher "73/73 OK"

# 6. Lancer les tests
python3 tests/test_all_contracts.py --rpc http://testnet-rpc.xelis.io --tracker AIRDROP_TRACKER_HASH
```

---

## 🚨 Points critiques à ne PAS oublier

1. **L'ordre compte** : ne pas déployer VaultEngine avant StakedOracle
2. **set_miner_contract sur StakedOracle** : sinon l'oracle ne peut pas vérifier les miners
3. **Autoriser les minters/burners sur xUSD** : sinon VaultEngine/PSM/VaultSwap ne peuvent pas mint
4. **set_treasury avec TreasuryVault** : pas une adresse EOA, le contrat TreasuryVault
5. **Whitelist les callbacks FlashLoan** : sinon flash_loan revert
6. **Authorized recorders sur AirdropTracker** : sinon les points ne s'enregistrent pas
7. **Mint des VLT aux FounderVesting** : sinon tu ne peux pas claim
8. **Vérifier le validateur** avant d'annoncer le déploiement

---

## 📊 Récapitulatif des hashes à sauvegarder

Garde ce fichier dans un endroit sécurisé (pas sur GitHub) :

```
# Infrastructure
REGISTRY_HASH = 0x...
COMPLIANCE_HASH = 0x...

# Tokens
VLT_CONTRACT_HASH = 0x...
VLT_ASSET_HASH = 0x...
XUSD_CONTRACT_HASH = 0x...
XUSD_ASSET_HASH = 0x...
FAUCET_HASH = 0x...

# Mining & Oracle
MINER_CONTRACT_HASH = 0x...
ORACLE_HASH = 0x...
MINERPOOL_HASH = 0x...

# Core Lending
IRM_HASH = 0x...
VAULTENGINE_HASH = 0x...
SAVINGS_HASH = 0x...
FLASHLOAN_HASH = 0x...
CALLBACK_HASH = 0x...

# AMM
VAULTSWAP_HASH = 0x...
PSM_HASH = 0x...

# Lending Markets
LENDINGMARKET_HASH = 0x...
PEERLOAN_HASH = 0x...
SYNDICATE_HASH = 0x...

# Auctions & Privacy
AUCTION_HASH = 0x...
MIXER_HASH = 0x...

# Tokenization & Treasury
ASSETVAULT_HASH = 0x...
TREASURY_HASH = 0x...
REVENUE_HASH = 0x...
PAYROLL_HASH = 0x...

# Insurance
INSURANCE_HASH = 0x...
PRIVINSURANCE_HASH = 0x...

# Governance
GOVVAULT_HASH = 0x...
TIMELOCK_HASH = 0x...
GUARDIAN_HASH = 0x...
GOVERNOR_HASH = 0x...
ORACLEGOV_HASH = 0x...

# Chat
CHAT_HASH = 0x...

# Founder & Fees
FOUNDER_VESTING_1_HASH = 0x...
FOUNDER_VESTING_2_HASH = 0x...
FEEDIST_HASH = 0x...
DELEGATION_HASH = 0x...

# Airdrop
AIRDROP_TRACKER_HASH = 0x...
# AIRDROP_CLAIM_HASH = (déployé sur mainnet plus tard)

# Adresses importantes
FOUNDER_ADDR = xel1...
ADMIN_ADDR = xel1...
TREASURY_TEMP_ADDR = xel1... (temporaire, remplacé par TREASURY_HASH)
```

---

*XELIS Vault — Guide de Déploiement Complet v10.5*
