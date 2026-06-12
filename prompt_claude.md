# Prompt pour Claude — Compléter et perfectionner XELIS Vault

Tu es ingénieur smart contracts senior spécialisé XELIS/Silex. Tu vas réviser, compléter et perfectionner l'intégralité du projet XELIS Vault pour le rendre parfait et prêt pour le mainnet.

## Contexte

XELIS Vault est une plateforme financière confidentielle sur XELIS BlockDAG. Tous les contrats sont en **Silex** (langage smart contract XELIS). Le projet a 23 contrats, certains déployés sur testnet.

Repo : `https://github.com/XelisVault/xelis-vault`

## Étape 1 : Apprendre Silex

Lis ces ressources :
- https://docs.xelis.io/features/smart-contracts/silex
- Tous les fichiers `.slx` dans `contracts/`
- Le fichier `AGENTS.md` dans le repo (référence Silex complète)

Concepts clés Silex :
- `fn` = interne, `entry` = appelable de l'extérieur, `pub fn` = cross-contract via `Contract::call()`
- `hook constructor()` = init au déploiement
- Entry retour **non-zero → rollback** de tous les storage writes !
- `Hash::zero()` = asset XEL natif
- `get_caller()` = wallet source original (même cross-contract)
- `get_contract_caller()` = contrat appelant immédiat
- `transfer()` retourne bool — toujours vérifier
- `transfer_contract()` pour envoyer à un contrat
- `Contract::new(hash).call(entry_id, args, deposits)` pour cross-contract
- Entry IDs = positions 0-indexed dans l'ordre du fichier source
- Pas de `mut` — utiliser early return ou pattern fonctionnel
- Cross-contract nécessite `pub fn` (Access::All), pas `entry`

## Étape 2 : Tout réviser pour la perfection

Pour CHAQUE contrat dans `contracts/`, vérifie :

### Règles d'or
- Toute multiplication / division utilise u128 ou u256 pour éviter les overflow
- `transfer()` retourne bool — toujours checker
- `get_deposit_for_asset()` utilisé avant de consommer un dépôt
- `get_deposits().len()` pour valider le nombre de dépôts
- Ordre check-effects-interact (pas de reentrancy)
- Toute entry state-changing retourne 0 (jamais non-zero)
- Les `pub fn` cross-contract sont protégées (admin check)
- `only_admin()` check à la fois `get_caller()` ET `get_contract_caller()` (timelock)
- Storage keys uniques sans collisions
- Validation des entrées (montants > 0, addresses non-zero)
- `optional<T>` bien unwrapé avec `.expect()` ou pattern match
- `emergency_withdraw()` protégé par `EMERGENCY_KEY` (pattern emergency address)

### Contrats spécifiques

**VaultEngine.slx** — Core lending
- `redeem()` vérifie dépôt xUSD avant d'envoyer XEL
- `deposit()` whiteliste XEL uniquement comme collatéral
- `sweep()` ne draine pas XEL ni xUSD
- Queue de liquidation FIFO correcte (sentinel value)
- Health check après chaque opération

**VaultSwap.slx** — AMM + PSM
- PSM : réserves mises à jour après mint/redeem
- PSM : prix oracle utilisé correctement
- PSM : frais envoyés à trésorerie avant mint/burn
- AMM : x*y=k avec frais (0.3%) correct
- `calc_swap_out` retourne 3 valeurs (after_fee, amount_out, fee)
- `calc_optimal` retourne surplus au caller
- `mint_lp` brûle MIN_LIQUIDITY (1000) sur premier mint
- `do_remove_liquidity` proportion correcte
- `get_pool_key`/`get_pair_key` sans collisions
- `store_pair`/`load_pair` tokens triés

**xUSD.slx** — Stablecoin
- `mint_tokens` protégé (only_minter)
- `burn_tokens` vérifie transfer avant burn
- `create_asset` une seule fois

**Timelock.slx** — Governance
- submit/execute avec délai minimum
- Pub fn wrappers appellent les bonnes entry IDs

**Governor.slx** — Proposals
- Seuil proposition (1%) correct
- Quorum (4%) vérifié au queue
- `queue` appelle Timelock.submit_proposal_tl (entry 10)
- `execute` appelle Timelock.execute_proposal_tl (entry 13 v4)

**GovernanceVault.slx** — Staking
- Voting power avec lock multiplier correct
- Rewards : standard StakingRewards (reward_per_token)
- Unstaking : rewards claimés avant déstack
- Pub fn get_voter_power_tl / get_total_voting_power_tl correctes

**PriceOracle.slx** — Oracle
- propose/execute avec timelock
- `get_price` retourne u64

**VLT.slx** — Token
- create_asset mint 10M
- mint échoue après (Fixed supply)

**SavingsRate.slx** — Yield
- `calc_yield` : principal * rate * blocks / 10000
- Rate max 5000 bps enforce

**LendingMarket.slx** — Marketplace
- Calcul intérêts correct
- Collatéral suffisant vérifié au borrow
- Positions trackées par borrower

**Autres contrats** (PeerLoan, InsurancePool, PrivateInsurance, ComplianceModule, SyndicatePool, SealedBidAuction, AssetVault, TreasuryVault, RevenueShare, Payroll, FlashLoan, FlashCallback)
- Mêmes vérifications générales
- Logique métier correcte

## Étape 3 : Implémenter tout ce qui manque

### 3.1 Vrai système de compliance ZK (remplacer ComplianceModule.slx)
Le whitepaper décrit un vrai système ZK où un vérificateur émet une preuve on-chain. Implémente ça proprement avec les primitives Silex (Signature::verify, hash commitments).

### 3.2 GuardianMultisig.slx
Multi-signature pour N guardians avec seuil M :
- Voter power basé sur stake VLT ou weight configurable
- Actions : veto timelock, pause, remplacement guardians
- Bypass timelock en urgence (M signatures)

### 3.3 Pause mechanism (VaultEngine + LendingMarket)
- Flag `paused: bool`, protection `only_guardians()`
- `pause()` : stop emprunts, dépôts, liquidations
- Les retraits et remboursements toujours possibles

### 3.4 VLTDistributor.slx
Contrat de distribution avec vesting schedule complet :
- 40% LP → farmé 4 ans
- 20% Team → 2 ans linear vesting (cliff 6 mois)
- 15% Treasury → governance
- 10% Ecosystem → grants
- 10% Airdrop → claim TGE
- 5% Security → bug bounties

### 3.5 RevenueDistributor.slx
Split automatique des frais :
- 50% → buyback/burn VLT (achète VLT sur VaultSwap + burn)
- 30% → dev fund
- 10% → insurance pool
- 10% → ecosystem partnerships
- Appelable manuellement ou via Scheduled Execution

### 3.6 Primes d'assurance automatiques
Modifier VaultEngine pour prélever 0.1% sur chaque borrow → InsurancePool.
InsurancePool distribue aux stakers.

### 3.7 Redemption : FIFO → meilleur design
Le whitepaper dit "lowest health factor". Décide si FIFO ou lowest health est meilleur et implémente le bon.

## Étape 4 : VaultChat — Design parfait sans TX par message

### Le problème
Chaque TX coûte ~0.01 XEL. Si chaque message = 1 TX, c'est inutilisable.

### Solution recommandée : Off-chain + ancrage on-chain

**Messagerie temps réel (0 TX)** :
- Connexion P2P directe entre clients via WebSocket/WebRTC
- Messages E2E encryptés, transmis sans passer par la blockchain
- Typing indicators, statut lecture, présence → tout off-chain
- Fonctionne comme Signal mais décentralisé

**Ancrage on-chain par batch** :
- Périodiquement (1x par heure/jour), le hash Merkle de la conversation est commité
- 1 seule TX pour tout l'historique
- Garantit intégrité et non-répudiation

**Pour les groupes/DAO** :
- Les messages sont soumis à un relayer off-chain
- Le relayer batch tout et soumet 1 TX via Scheduled Execution
- Les frais partagés entre membres

**Stockage des messages** :
- Les messages récents stockés localement (client)
- Option : sauvegarde décentralisée sur IPFS/Arweave (encrypté)
- L'on-chain stocke seulement les hashs d'intégrité

**Burn-after-reading** :
- Le message est détruit localement côté destinataire
- L'on-chain prouve que le message a été livré et détruit
- Pas besoin de TX supplémentaire

**Pièces jointes** :
- Upload sur IPFS/Arweave (encrypté)
- Le hash + clé de déchiffrement partagés dans le message P2P

**Intégration Vault** :
- Bouton "Envoyer un paiement" dans la conversation
- Utilise `Contract::call()` pour déclencher vault deposit/repay
- Le paiement est sa propre TX (inévitable), mais le message l'accompagnant est gratuit

### Livrables VaultChat
- Fichier `docs/VAULTCHAT_ARCHITECTURE.md` avec design complet
- Protocole off-chain détaillé
- Modèle de frais
- Schéma de sécurité (encryption, forward secrecy, intégrité)

## Étape 5 : Finalisation

1. Tous les bugs de logique corrigés
2. Tous les contrats manquants créés et prêts à compiler
3. Contrats existants modifiés (pause, insurance premiums)
4. Tous les contrats syntaxiquement valides Silex
5. Entry IDs cohérents entre contrats (cross-contract)
6. AGENTS.md mis à jour (nouveaux contrats + entry IDs)
7. README.md et ROADMAP.md mis à jour
8. Tout commité et pushé sur GitHub

## Règles impératives

- **NE PAS** supprimer ou modifier `emergency_withdraw()` — le pattern doit rester dans tous les contrats
- **NE PAS** ajouter de commentaires dans le code
- Conserver la compatibilité avec les entry IDs des contrats déjà déployés si possible
- Pas de `mut` en Silex — utiliser early return
- Cross-contract = `pub fn`, pas `entry`
- Tester mentalement chaque contrat (pas de compilateur dispo)
- Se concentrer sur la qualité et la justesse du code, pas sur les aspects théoriques

---

Le repo est à https://github.com/XelisVault/xelis-vault

Clone, lis tout le code, puis exécute les étapes 1 à 5.
