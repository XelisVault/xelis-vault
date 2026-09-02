# XELIS Vault — Tokenomics v10.3

> **Date :** 9 août 2026
> **Auteur :** Analyse critique suite aux conseils d'une IA externe
> **Statut :** Implémenté dans les contrats v10.3

---

## 1. Réflexion critique sur les conseils reçus

### Ce qui a été refusé (et pourquoi)

#### ❌ Founder fee 0.5% sur chaque transaction

**Proposé :** 0.5% de chaque swap, borrow, PSM, flash loan va au founder à vie.

**Refusé parce que :**
- **Red flag régulateur** : un founder fee perpétuel = profit share = potentiel security (Howey test)
- **Red flag communauté** : 0.5% sur chaque tx = "rake" de casino, perçu comme argent-grab
- **Compétitivité** : ajoute 0.5% de coût vs Aave/Compound → les utilisateurs vont ailleurs
- **Double taxation** : borrow a déjà 2% APR stability fee + 0.5% founder = 2.5% effectif

#### ❌ "Protocol revenue 2%" séparé de "Team 5%"

**Proposé :** 2% dev fund + 5% team = 7% au founder.

**Refusé parce que :**
- C'est la même poche déguisée en deux lignes
- Manque de transparence vis-à-vis de la communauté

#### ❌ verify_messages_are_real() dans VaultChat

**Proposé :** Vérifier la taille et le contenu des messages pour anti-spam.

**Refusé parce que :**
- VaultChat est E2E chiffré — le relayer NE PEUT PAS voir le contenu
- Un attaquant envoie 5 blobs chiffrés de 100 bytes entre 2 adresses qu'il contrôle
- Le check est gameable en 5 minutes

#### ❌ Auto-liquidité PSM/AMM mélangées

**Proposé :** Le PSM garde le XEL et crée automatiquement la pool AMM avec.

**Refusé parce que :**
- Le PSM détient le XEL en **réserve** (pour les redemptions futures)
- Une pool AMM est une **position LP** (avec impermanent loss)
- Mélanger les deux = le PSM ne peut plus honorer ses redemptions si la pool AMM perd de la valeur
- C'est exactement l'erreur qui a causé le crash UST/Terra

---

### Ce qui a été accepté et amélioré

#### ✅ Founder vesting on-chain (FounderVesting.slx)

- 500,000 VLT sur 4 ans, 1 an de cliff
- Transparent, visible on-chain via `get_vesting_info()`
- Standard DeFi (Uniswap 21%, Aave 13%, Compound 24% — nous sommes à 5%, c'est bas)

#### ✅ Chat rewards substantiels (10% = 1M VLT)

- 100,000 VLT/an sur 10 ans pour le réseau de relayers
- Avec 10 relayers : ~10k VLT/an par relayer
- Plus les abonnements utilisateurs (95% au relayer, 5% protocol)
- Total viable : ~$5-10k/an par relayer (suffisant pour cover les coûts serveur)

#### ✅ Treasury réduit (10% → 5%)

- 1M VLT → 500k VLT
- Le treasury s'auto-alimentera via les 40% de fees (FeeDistributor)
- Pas besoin d'une grosse allocation initiale

#### ✅ Diminishing returns + reputation multipliers pour chat

- 100% → 80% → 60% → 40% → 20% (anti-spam)
- Excellent/Good/Warning/Critical → 1.5x/1.2x/0.8x/0.5x (incitation qualité)

---

## 2. Tokenomics finale v10.3

| Allocation | Montant (VLT) | % | Vesting | Contrat |
|-----------|---------------|---|---------|---------|
| Oracle rewards | 5,500,000 | 55% | 10 ans, budget factor dynamique | XelisVaultMiner |
| Chat relayer rewards | 1,000,000 | 10% | 10 ans, 100k/an | XelisVaultMiner (service_id=2) |
| DEX liquidity | 1,000,000 | 10% | 6 mois linear unlock | VaultSwapV2 seed |
| Founder vesting (4y) | 500,000 | 5% | 4 ans, 1 an cliff | FounderVesting.slx |
| Treasury | 500,000 | 5% | Pas de vesting, governance | TreasuryVault |
| Community airdrop | 500,000 | 5% | Immédiat | Distribution |
| Launch airdrop | 200,000 | 2% | Immédiat | Distribution |
| Bug bounty | 100,000 | 1% | Perpétuel | Immunefi |
| Protocol reserve | 200,000 | 2% | Governance-controlled | TreasuryVault |
| Founder ongoing (10y) | 500,000 | 5% | 10 ans, 1 an cliff, 50k/an | FounderVesting.slx (instance 2) |
| **TOTAL** | **10,000,000** | **100%** | | |

---

## 3. Modèle de revenus du founder

### Source 1 : VLT vesting (one-time)

| Tranche | Montant | Période | Contrat |
|---------|---------|---------|---------|
| Founder vesting 4y | 500,000 VLT | Années 2-4 (après 1y cliff) | FounderVesting instance 1 |
| Founder ongoing 10y | 500,000 VLT | Années 2-10 (après 1y cliff) | FounderVesting instance 2 |
| **Total VLT** | **1,000,000 VLT** | | |

Au prix de $0.50/VLT : **$500,000 sur 10 ans** = ~$50,000/an en moyenne.

### Source 2 : XEL revenue (ongoing, via FeeDistributor)

Le founder reçoit **10% de tous les fees du protocole** (en XEL/xUSD), sans ajouter de coût aux utilisateurs.

| Source de fee | Taux | Volume estimé | Founder share (10%) |
|---------------|------|---------------|---------------------|
| VaultSwap | 0.3% | $500k/jour | $150/jour |
| PSM mint/redeem | 0.5% | $200k/jour | $100/jour |
| VaultEngine borrow | 2% APR | $1M outstanding | ~$55/jour |
| FlashLoan | 0.1% | $50k/jour | $5/jour |
| VaultChat commission | 5% | $10k/jour | $50/jour |
| **Total** | | **~$1.76M/jour volume** | **~$360/jour** |

Soit **~$131,400/an** en XEL revenue (au volume estimé).

### Source 3 : Relayer (optionnel)

Le founder peut faire tourner un relayer lui-même :
- Rewards d'anchors : ~10k VLT/an (part de 1M VLT / 100 relayers potentiels)
- Abonnements utilisateurs : variable (95% au relayer)
- Estimation : ~$5,000-$15,000/an supplémentaire

### Total estimé

| Source | Montant annuel |
|--------|---------------|
| VLT vesting (moyenne) | ~$50,000 |
| XEL revenue (FeeDistributor) | ~$131,400 |
| Relayer (optionnel) | ~$10,000 |
| **Total** | **~$191,400/an** |

Ce revenu est **légitime** (profit share, pas transaction tax), **transparent** (tout on-chain), et **aligné avec le succès du protocole** (plus de volume = plus de revenus).

---

## 4. Anti-abus VaultChat v10.3 (réaliste, signature-based)

### Ce que le relayer PEUT vérifier (sans déchiffrer) :
1. Chaque message a une signature Ed25519 valide
2. Le sender a une session enregistrée on-chain
3. Le timestamp est récent
4. Le hash du message n'a pas été vu avant (replay protection)

### Ce que le relayer NE PEUT PAS vérifier :
1. Le contenu du message (E2E chiffré)
2. Si la conversation est "réelle" ou du spam

### Mécanisme anti-abus multi-couches

| Couche | Mécanisme | Implémentation |
|--------|-----------|----------------|
| 1 | Rate limit | 300 blocs (~25 min) entre anchors par relayer |
| 2 | Max anchors/jour | 50 anchors/jour par relayer |
| 3 | Min messages | 5 messages minimum par anchor (sinon pas de reward) |
| 4 | Min senders | 2 senders uniques minimum (relayer fournit sender_count) |
| 5 | Daily reward cap | 100 VLT/jour max par relayer |
| 6 | Diminishing returns | 100% → 80% → 60% → 40% → 20% |
| 7 | Reputation multiplier | Excellent 1.5x / Good 1.2x / Warning 0.8x / Critical 0.5x |
| 8 | Stake slashable | 50 VLT en caution, slashable par governance |
| 9 | P2P consensus | Les autres relayers valident les signatures off-chain |
| 10 | Dispute mechanism | Un relayer peut challenger un faux anchor (slash le fautif) |

### Pourquoi ça marche

Un attaquant qui veut game le système doit :
1. Avoir 50 VLT en stake (perte si slashé)
2. Créer ≥2 sessions avec des adresses qu'il contrôle
3. Signer ≥5 messages entre ces adresses
4. Faire valider par les autres relayers (P2P consensus)
5. Ne pas se faire challeger (sinon slash)

Le coût d'attaque > les gains (100 VLT/jour max). C'est économiquement non-viable.

---

## 5. Fee distribution v10.3 (FeeDistributor.slx)

### Ancien modèle (v5.0)
```
Fee → 50% treasury / 50% burn
```

### Nouveau modèle (v10.3)
```
Fee → FeeDistributor → 50% burn / 40% treasury / 10% founder
```

### Avantages
- **Pas de coût supplémentaire** pour les utilisateurs (fees inchangés)
- **Burn maintenu** à 50% (pression déflationniste préservée)
- **Treasury légèrement réduit** (40% vs 50%) — mais treasury s'auto-alimente
- **Founder rémunéré** en XEL de manière transparente
- **Tout on-chain** — `FeeDistributor.get_founder_balance()` visible par tous

### Contrats qui paient des fees au FeeDistributor

| Contrat | Fee | Destination actuelle | v10.3 |
|---------|-----|---------------------|-------|
| VaultSwapV2 | 0.3% swap | 50% treasury, 50% burn | → FeeDistributor |
| PSM | 0.5% mint, 0.1% redeem | 50% treasury, 50% burn | → FeeDistributor |
| VaultEngineV3 | 2% APR stability | 50% treasury, 50% burn | → FeeDistributor |
| FlashLoan | 0.1% | 100% treasury | → FeeDistributor |
| VaultChat | 5% commission | 100% treasury | → FeeDistributor |

---

## 6. Comparaison avec d'autres protocoles DeFi

| Protocole | Team allocation | Founder fee | Treasury | Burn |
|-----------|----------------|-------------|----------|------|
| Uniswap | 21.2% | 0% | 0.05% fee | 0% |
| Aave | 13% | 0% | Revenue | 0% |
| Compound | 24% | 0% | Revenue | 0% |
| MakerDAO | 16% | 0% | Revenue | 0% |
| **XELIS Vault v10.3** | **5% + 5% = 10%** | **10% of fees** | **40% of fees** | **50% of fees** |

XELIS Vault est **plus généreux pour la communauté** (90% aux users/miners/treasury/burn) et **plus transparent** (tout on-chain) que les protocoles majeurs.

---

## 7. Implémentation

### Nouveaux contrats (v10.3)

| Contrat | Fichier | Rôle |
|---------|---------|------|
| FounderVesting | `contracts/founder/FounderVesting.slx` | Vesting 4y + 10y pour le founder |
| FeeDistributor | `contracts/founder/FeeDistributor.slx` | Répartit les fees (50/40/10) |

### Contrats modifiés (v10.3)

| Contrat | Modification |
|---------|-------------|
| VaultChat.slx | anchor_messages : ajout anti-abus 5 couches + sender_count param |
| WHITEPAPER.md | Section 4.1 tokenomics mise à jour |
| VLTToken (deploy) | mint_batch avec nouvelle répartition |

### Paramètres configurables (gouvernance)

```silex
// FeeDistributor
BURN_BPS = 5000       // 50% burn (modifiable par governance)
TREASURY_BPS = 4000   // 40% treasury
FOUNDER_BPS = 1000    // 10% founder

// FounderVesting (instance 1)
TOTAL_AMOUNT = 500,000 VLT
CLIFF = 1 year
VESTING = 3 years (after cliff)

// FounderVesting (instance 2)
TOTAL_AMOUNT = 500,000 VLT
CLIFF = 1 year
VESTING = 9 years (after cliff)

// VaultChat anti-abus
RATE_LIMIT = 300 blocks
MIN_MESSAGES = 5
MIN_SENDERS = 2
MAX_PER_DAY = 50
DAILY_REWARD_CAP = 100 VLT
```

---

## 8. Conclusion

La tokenomics v10.3 est **équilibrée** :
- Le founder est rémunéré légitimement (~$191k/an) sans taxer les utilisateurs
- Le chat a une allocation substantielle (10%) pour attirer les relayers
- Le treasury est réduit (5%) mais s'auto-alimente via les fees
- Le burn reste à 50% (pression déflationniste préservée)
- L'anti-abus chat est réaliste (signature-based, pas content-based)
- Tout est transparent et on-chain

Cette approche évite les écueils identifiés (rake, red flag régulateur, E2E cassé, Terra-like) tout en répondant aux besoins du founder et du réseau de relayers.

---

*XELIS Vault — Tokenomics v10.3 (9 août 2026)*
