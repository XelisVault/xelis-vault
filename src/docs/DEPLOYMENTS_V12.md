# Testnet Deployment Record — v12 FULL REDEPLOY (v11.5 audit-fixed code)

Fresh clean redeployment of all core contracts per docs/DEPLOYMENT_GUIDE.md.
Phase 9 (Insurance) SKIPPED by owner decision. Operator: xet:czr9q8k5…
State file: docs/deployment_state.json (updated after every tx).

## Phase 1 — Infrastructure

| Step | Contract / Action | Address (tx hash) | Status |
|------|-------------------|-------------------|--------|
| 1.1 | Deploy ContractRegistry (v11.5 + try_get_entry) | `ec60bb78150add73492ac8d07c32186550b138af9c00588d59964aac5cc83194` | ✅ admin ok |
| 1.2 | Deploy ComplianceModule | `3eb327fd49856e3fe9cfdade47042b3c2177bae3eb47067053c7ae1379d369ed` | ✅ |
| 1.3 | Compliance.set_registry → REGISTRY | `b4ef01d2…` | ✅ verified reg key |

## Phase 2 — Token Layer

| Step | Contract / Action | Address / Asset | Status |
|------|-------------------|-----------------|--------|
| 2.1a | Deploy VLTToken | `0b0f5cfb9f0f0fb8db7a23c4b5170e0e69521b6941a639ed949bae9cb9839524` | ✅ |
| 2.1b | VLT.create_asset (chunk 9, +10 XEL) | **VLT asset = `daa3981df5fc070d93d6752f477d880aa0bfe6bc628a8fb1e416d5e8659f387d`** ("XELIS Vault"/VLT/8dp, cap 1e15) | ✅ |
| 2.1c | VLT.set_registry + register "VLTToken" | `e73e9834…` `4f6f84e0…` | ✅ |
| 2.2a | Deploy xUSD | `8154335a929257c4e3387cad745c846416821990ce40fb8f1333775a92c771c8` | ✅ |
| 2.2b | xUSD.create_asset (chunk 2, +10 XEL) | **xUSD asset = `0daf60ef357733a403e0ca8928b1548b0953521e318fae418c943e6abfbac85c`** ("XELIS USD"/XUSD/8dp) | ✅ |
| 2.2c | xUSD.set_registry + register "xUSD" | `c1fad5f1…` `81217290…` | ✅ |
| 2.3a | Deploy FaucetContract (v11.5 F-17) | `0baaa0c650d4378810a6584f548a9ecf57fb7b4be40503024564546937c36d5a` | ✅ |
| 2.3b | Faucet.set_registry + register | `86306737…` `4980921c…` | ✅ |

> Note opérateur: bug script extract_new_asset (substring replace) — state corrigé manuellement
> via lecture on-chain clé 'ah'. Contrats non affectés.

## Phase 3 — Mining & Oracle

| Step | Contract / Action | Address | Status |
|------|-------------------|---------|--------|
| 3.1a | Deploy XelisVaultMiner | `ba27f8e6c1fc94b679f35b758c38e64c70f92da8d92dd01b6805b830ce1af3e7` | ✅ |
| 3.1b | set_registry / set_vlt_contract / set_vlt_asset + register | ✅ | ✅ |
| 3.2a | Deploy StakedOracle | `15247c0a6ae190ad729bd2ccab675f8e292a17129474f0ff4fa234eceb4f9f27` | ✅ |
| 3.2b | set_registry / set_miner_contract + register | ✅ | ✅ |
| 3.2c | add_feed_entry("XEL/USD", XEL, 8dp, min 1, max 100 XEL) | `b37c06ea…` | ✅ |
| 3.2d | Miner.register_service(service_id=1, oracle) | `c33e994d…` | ✅ |
| 3.3a | Deploy MinerPool | `ee96c17b2dff166b61cd187d3af79c71130975b4016d094500e7ea75fbe73c35` | ✅ |
| 3.3b | set_registry / set_miner_contract / set_vlt_asset + register | ✅ | ✅ |

> Note: script rendu resumable (STATE["steps"]) après 2 crashes de paramètres
> (add_feed_entry decimals u8 ; register_service(u8, Hash) ordre corrigé).

## Phase 4 — Core Lending

| Step | Contract / Action | Address | Status |
|------|-------------------|---------|--------|
| 4.1a | Deploy InterestRateModel | `3ccdfce44461c02d33a499f088a86e51e822a30b7ab024df38ee682710bb068c` | ✅ |
| 4.1b | IRM.set_rates(50, 1000, 5000, 8000) + register | `10de44ad…` | ✅ |
| 4.2a | Deploy VaultEngineV3 | `b916b7a46d837aa4d2ee68cf161dc76baf000309337769c4e5c054b59c0a5ec9` | ✅ |
| 4.2b | set_registry/xusd_contract/xusd_asset/treasury(admin) | ✅ | ✅ |
| 4.2c | register "VaultEngine" + alias "VaultEngineV3" | ✅ | ✅ |
| 4.2d | xUSD.set_minter(VE) + set_burner(VE) | `65922812…` `139559ca…` | ✅ |
| 4.3a | Deploy SavingsRate | `4841e68886f98975e1e1a4cfaa54014ac9cfb067265f6369193dc72d8d651c88` | ✅ |
| 4.3b | set_registry/xusd_contract/xusd_asset/treasury + xUSD.set_minter(SR) + register | ✅ | ✅ |
| 4.4a | Deploy FlashCallback puis FlashLoan | CB=`8cae8f57…6bcdb4` FL=`a9d2c504693163e9be61f2c479f9453c3d4f0feecbe9ad08795d8ee9fd25e4bb` | ✅ |
| 4.4b | FL.set_registry/set_treasury + FL.verify_callback(CB) + **CB.set_flash_loan(FL)** + registers | `10bb52a7…` `1cfcce7e…` | ✅ |

> Notes: VE résout l'oracle via registry (pas de set_oracle). CB.set_flash_loan était
> absent du script — ajouté (chunk 4) sinon callback inopérant.

## Phase 5 — AMM

| Step | Contract / Action | Address | Status |
|------|-------------------|---------|--------|
| 5.1a | Deploy VaultSwapV2 | `0e5c318db4bd7feb3e0578436a96eb25e80801c7a61bebcbce831b7d46c53099` | ✅ |
| 5.1b | set_registry/xusd_contract/xusd_asset/treasury + xUSD minter+burner | ✅ | ✅ |
| 5.2a | Deploy PSM | `3376c525759a7df0e306c379cbad96cd02f92de9b1681d2edf96b7b6d9a9f9ba` | ✅ |
| 5.2b | set_registry/xusd_contract/xusd_asset/treasury + xUSD minter+burner | ✅ | ✅ |
| 5.3 | VS.set_psm_contract(PSM) (chunk 56) + registers "VaultSwapV2"/"VaultSwap"/"PSM" | `4e6e26a1…` | ✅ |

## Phase 6 — Lending Markets

| Step | Contract / Action | Address | Status |
|------|-------------------|---------|--------|
| 6.1a | Deploy LendingMarket | `01c5767015026059999b7c188b377577bfaa29abadddbe19ed76745e42d2bda2` | ✅ |
| 6.1b | set_registry/set_oracle/set_treasury + register | ✅ | ✅ |
| 6.2a | Deploy PeerLoan | `132e270dd75fb44db66109912d3d36d1ee34e3425a8e9c3aeef9a5a519050942` | ✅ |
| 6.2b | set_registry/set_oracle/set_treasury + register | ✅ | ✅ |
| 6.3a | Deploy SyndicatePool | `4a04cdc0723dbe953c0f78e03efbcd4373e236b1f8e66f0f0aa60ded366a6e1b` | ✅ |
| 6.3b | set_registry/set_oracle/set_treasury + register | ✅ | ✅ |

> ⚠️ Écart guide: LendingMarket n'a PAS de set_irm en v11.5 — l'IRM est passé
> par pool via create_pool(..., irm_hash). Le guide décrit une version antérieure.

## Phase 7 — Auctions & Privacy

| Step | Contract / Action | Address | Status |
|------|-------------------|---------|--------|
| 7.1 | Deploy SealedBidAuction + set_registry + register | `e2d2fa2ac51ee61c2b676f1d1c26d7531da7948defd49f9aec7f77cf7625ea14` | ✅ |
| 7.2 | Deploy PrivacyMixer + set_registry + register | `7f41faec283b6c722a3b289323bcce79ad6c3e23b03ed2a1589c1adba7f12985` | ✅ |

## Phase 8 — Tokenization & Treasury

| Step | Contract / Action | Address | Status |
|------|-------------------|---------|--------|
| 8.1a | Deploy AssetVault | `2f3308a10c3ad60473423f7ed785cb6ebc206793c3c1608d46c3bea7e8e723a5` | ✅ |
| 8.1b | set_registry + set_compliance(ComplianceModule) + register | `d8ce6328…` | ✅ |
| 8.2a | Deploy TreasuryVault (config ctor uniquement: admin/signer/quorum=1) | `6ef3f44b79eb12f5e85b3f6465ba5251e1e33a687ac9f415c0245e2e1ffe52d1` | ✅ |
| 8.2b | register "TreasuryVault" | ✅ | ✅ |
| 8.3a | Deploy RevenueShare | `caa6c5dc93f9a27946e79cdc924ba1e134f5067efb6556e3b3c685b8d63663c4` | ✅ |
| 8.3b | set_registry + set_share_token(VLT asset) + register | `4975dad5…` | ✅ |
| 8.4a | Deploy Payroll | `a5982d6fcf562da3d9294e4321e94e835623880ef3584dee774f2b1afe4a972c` | ✅ |
| 8.4b | set_registry + set_treasury(TreasuryVault hash) + register | `66dac05d…` | ✅ |

## Phase 9 — Insurance : ⛔ SKIPPÉE (décision owner)

## Phase 10 — Governance

| Step | Contract / Action | Address | Status |
|------|-------------------|---------|--------|
| 10.1a | Deploy GovernanceVault | `40f7b6bed62789cb3ceab6e47284c00150f4aa67ed91caf14605c4b5c8420619` | ✅ |
| 10.1b | set_registry/set_vlt_contract/set_vlt_asset + register | ✅ | ✅ |
| 10.2a | Deploy Timelock (pas de set_registry — ctor only) | `a43a00d8d4184c4e193f24acf7aca8e7e08f4c5526627c82728593fd8861a659` | ✅ |
| 10.2b | register "Timelock" | ✅ | ✅ |
| 10.3a | Deploy GuardianMultisig + set_timelock + register | `3ec3595c405430e64c9be3ff1d3837cc23814d9cf1fdceed5ef6746ecbcb6750` | ✅ |
| 10.4a | Deploy Governor + set_governance_vault/set_timelock + register | `2377145f070f29790cfbf5ffb43c03847de4f96e781abec0278d6ef9752e1582` | ✅ |
| 10.5a | Deploy OracleGovernance + set_governance_vault/set_oracle/set_timelock + register | `7ea57bf2803d514c16b13a76d6bd159a0b3126680e02185c08af3e81510a0bad` | ✅ |
| 10.6 | Cross-wiring: TL.set_governor(Gov) + TL.set_guardian_contract(GM) | `f0481161…` `4c8d9145…` | ✅ |

## Phase 11 — Chat

| Step | Contract / Action | Address | Status |
|------|-------------------|---------|--------|
| 11.1a | Deploy VaultChat **v11.6** (+entry set_vlt_asset chunk 96 — fix bond mort-né) | `0bfc1b24a02ce3e05e755f83dc8ddf2c046945e7c8badf279a8d87b3669d2097` | ✅ |
| 11.1b | Chat.set_vlt_asset(VLT) | `fc1ea3f7…` | ✅ |
| 11.1c | VLT mintés à l'admin: 1000 + 70 000 + 629 050 = **700 000 VLT** (allocation airdrop testnet, distribution manuelle owner) | `23bd1767…` `c9d6827f…` `11a4e5e7…` | ✅ |
| 11.1d | Chat.stake_relayer_bond(50 VLT) ×2 (interruption) → bond=100 VLT | `39c8ed3d…` | ✅ (cosmétique) |
| 11.1e | Chat.set_relayer(admin,true) (F-13 satisfait) | `794a6be2…` | ✅ |
| 11.1f | register "VaultChat" + Miner.register_service(svc=2, chat) | `ac5c52c1…` | ✅ |

> ⚠️ Contrat chat v11.5 orphelin abandonné: `1be87b9e…d8ce8d6` (sans set_vlt_asset).
> ⚠️ Wallet: asset VLT tracké manuellement (track_asset) pour les dépôts.

## Phase 12 — Founder & Fees

| Step | Contract / Action | Address | Status |
|------|-------------------|---------|--------|
| 12.1a | Deploy FounderVesting **4y** | `7e64b68658b6ffad46dd58dceb0f9f06b7a7ee8cda983fab1a81340fba88abec` | ✅ |
| 12.1b | set_founder(admin)/set_vlt_contract/set_vlt_asset + fund **500k VLT** ×2 + register | ⚠️ financé 2× (bug script) → **1M VLT dans le contrat**, excès 500k verrouillé (pas de sweep entry) | ✅ |
| 12.2a | Deploy FounderVesting **10y** | `b4f48448cfe3711fa79f06db33d0b8d088b37b2a1b6f8eea1f7573e80da5fd04` | ✅ |
| 12.2b | wiring + fund **500k VLT** + register | `6f4828d7…` | ✅ |
| 12.3a | Deploy FeeDistributor | `fb26448cea78a0ca0141842824ba4780fb89e4763964cc2dd6833c15c39b95df` | ✅ |
| 12.3b | set_founder/set_treasury(TreasuryVault)/set_vlt_contract/set_vlt_asset/set_registry + register | ✅ | ✅ |
| 12.4a | Deploy MinerDelegation | `1a7723fe5565e6e064ab0ca6cb087fdec2597a8692ebda5475d2bd5f55d90f6f` | ✅ |
| 12.4b | set_vlt_asset/set_miner_contract_hash/set_registry + register | ✅ | ✅ |

> ⚠️ Incidents résolus: cache deploy() avait fusionné les 2 instances (state réparé,
> registry vérifié on-chain: 4y=7e64b686, 10y=b4f48448). Boucle phase12 patchée.
> Admin: ~210k VLT stables restants après financements (+ mints en cours de stabilisation).

## Phase 13 — Airdrop

| Step | Contract / Action | Address | Status |
|------|-------------------|---------|--------|
| 13.1a | Deploy AirdropTracker **v11.6** (recorders par Hash/to_hex) | `e1f0ec8f737963a620ae7b918dbc096ea0d7c9d0f610d3b07108c6ef31aeb8d1` | ✅ |
| 13.1b | set_registry + set_vlt_contract | ✅ | ✅ |
| 13.1c | Recorders autorisés: Miner, Oracle, Chat, Governor, VaultEngineV3, VaultSwapV2, PSM | 7 × chunk 68 | ✅ |
| 13.1d | register "AirdropTracker" | `a13555c8…` | ✅ |

---

# ✅ RÉCAPITULATIF FINAL v12 — 34 contrats déployés

**Registry:** `ec60bb78150add73492ac8d07c32186550b138af9c00588d59964aac5cc83194`
**VLT asset:** `daa3981df5fc070d93d6752f477d880aa0bfe6bc628a8fb1e416d5e8659f387d`
**xUSD asset:** `0daf60ef357733a403e0ca8928b1548b0953521e318fae418c943e6abfbac85c`

Phase 9 (Insurance) skippée — InsurancePool/PrivateInsurance non déployés.
`scripts/protocol.py` CONTRACT_HASHES + assets mis à jour v12 (37 entrées avec alias).
