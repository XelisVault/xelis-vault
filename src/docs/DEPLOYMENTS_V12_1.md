# Déploiement Testnet v12.1 — 2026-08-21/22

Redeploy complet suite au fix **v11.7 « cross-contract visibility »**
(`Contract::call` exige `Access::All` ; 8 call-sites corrigés dans 7 fichiers).
Phase 9 Insurance toujours SKIPPED (décision owner). Orchestrateur:
`deploy/deploy_v12.py --phase N` (resumable, état: `docs/deployment_state.json`).

## Adresses v12.1 (registry: `66c7df95…8dcf3e`)

| Contrat | Hash |
|---|---|
| ContractRegistry | `66c7df95bf05e59eabf211d047f2183c3ada8e8dcf3e6862ddd9d3ce2bbbb820` |
| ComplianceModule | `8048f087585acde69ad2dc5aa466288a78b0a96ed9cfa690025b6e19ee82ca1e` |
| VLTToken | `0cc358d3851cfce1a1858605b7b4811a0166709d43df2376c91baa208ffb6091` |
| **VLT asset** | `12f72fc47984070c82f88eba1d5868a808f43a76d31c055c9798b33881af5749` |
| xUSD | `d8195e0af207814d6cfaac965fe746d9c217ad53abded72e7a431fbe078a1d07` |
| **xUSD asset** | `f610dfb8d140bf353cd27abcfe018164cb2c7d9c68a65d351b7a67796551c5bd` |
| FaucetContract | `7d68c47bc1e33df7f8a73c6af3908beda0a700264472697bb6bdfbdf5944f5d6` |
| XelisVaultMiner | `d6e8bb5608f860b75f1ae2248c728fa18cb007f265c4b11650b3476b26bca866` |
| StakedOracle | `3ae1c54de26db4dc6e8d884df1c7271979150c397835fedab99ebc7a9c1725ad` |
| MinerPool | `651d4c40…(voir state)` |
| InterestRateModel | (state) |
| VaultEngineV3 | (state) |
| SavingsRate | (state) |
| FlashLoan / FlashCallback | (state) — CB vérifié via `vcb_<hash>` |
| VaultSwapV2 | (state) → PSM `d9bfc818…60ce6b` |
| LendingMarket / PeerLoan / SyndicatePool | (state) |
| SealedBidAuction / PrivacyMixer | (state) |
| AssetVault / TreasuryVault / RevenueShare / Payroll | (state) |
| GovernanceVault / Timelock / GuardianMultisig / Governor / OracleGovernance | (state) |
| VaultChat | `6f75ed06…21fb963b0` (relayer bond 50 VLT, admin relayer) |
| FounderVesting4y / FounderVesting10y | (state) — 500k VLT chacun |
| FeeDistributor / MinerDelegation | MD=`1b267364…ea5e8ee664` |
| AirdropTracker | (state) + 7 recorders |

Hashes complets: `docs/deployment_state.json` (source de vérité).

## Wiring vérifié on-chain

- Oracle: `mc`→Miner ✓, `dc`→MD ✓, `reg` ✓, feed `fd_0` XEL/USD (8dp,
  min 1, max 100 VLT) ✓
- Miner: `reg`, `vc`, `va`, `dck`→MD ✓, **`tr`=admin (treasury)** ✓
- FlashLoan `vcb_<CB>` = true ✓ ; VaultSwapV2 `psm` ✓ ; PSM `xc` ✓
- xUSD: minters VE/Savings/VS/PSM + burners VE/VS/PSM ✓
- **VLT.set_minter(XelisVaultMiner)** ✓ (ajouté v12.1 — voir incident #1)

## Providers oracle (testnet)

Wallets ports 18086/18087/18088 (`wallet:testpass`), inscrits miners
(chunk 15, stake 1000 VLT, services_mask=1):

| Provider | Adresse |
|---|---|
| p1 | `xet:mg8rm00m89cr46kkq8yy3clp3gp0q0swe2ntm6829huj0kjd4q7qqtf6tzc` |
| p2 | `xet:wt7jj6xfr4cqauh3v8zdtwhryft8yn4zrfys7juchuujtt0j49lqqf2dxy6` |
| p3 | `xet:6g2xx6d2jyazjcl9jkn3qdp6862g9y7h75tswehtwnd7pzn6h36qqfy53wv` |

Keeper: `scripts/oracle_keeper3.py` (nohup, log `/tmp/oracle_keeper3.log`),
submit_price toutes les ~5 blocs + aggregate_now anti-deadlock + heartbeats.
Résultat: `fg_0` rafraîchi chaque cycle (~13s), récompenses distribuées,
réputation en hausse.

## Incidents & résolutions (à ne pas refaire)

1. **`notminter` sur submit_price** : distribute_reward mint via
   VLT.mint_to (chunk 4) → le MINER doit être minter VLT.
   Fix config + ajouté en phase3 du script.
2. **Panic `err` sur submit_price** : jitter keeper ±4% → spread 800 bps >
   max_dev 500 bps → branche slash-all → `TREASURY_KEY("tr")` absent sur le
   Miner → expect("err"). Fixes: `Miner.set_treasury(admin)` + jitter ±1% +
   set_treasury ajouté en phase3.
3. **Deadlock alreadysub** : si tous les miners soumettent avant l'ouverture
   de la fenêtre d'agrégation, plus personne ne peut déclencher
   try_aggregate (check alreadysub AVANT l'appel). Le cycle reste ouvert
   indéfiniment (sc_N=3, cy bloqué). Fix keeper: poke `aggregate_now`
   (chunk 17, sans access-control) avant chaque round de soumissions.
   NOTE design contrat: envisager de déplacer try_aggregate avant le check
   provided_key ou entry publique dédiée.
4. **Providers à court de XEL** après ~3h (2400 tx × 0.01): top-up 20 XEL.
   Burn rate ≈ 24 XEL/jour pour 3 providers @5 blocs/cycle.
5. **ASSET_NOT_TRACKED**: les wallets providers doivent `track_asset` du
   nouveau VLT avant tout dépôt.
6. **Lag post-deploy**: invoke juste après deploy → `-32004 Contract not
   found` (stabilité). `_is_transient` le traite désormais (retry).

## CLI v7.1 (même commit)

Onboarding zero-config `scripts/onboarding.py`: wallet (détection/download
binaire officiel/création seed locale validée contre le binaire/import),
daemon auto-detect, contrats chargés depuis `network/testnet.json`.
Schéma mnémonique Xelis implémenté (1626 mots, 24+checksum=copie du mot
crc32%24, scalaire curve25519 canonique).
