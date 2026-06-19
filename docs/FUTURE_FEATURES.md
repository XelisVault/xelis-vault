# Future Features — XELIS Vault

> Brainstorming de features innovantes à ajouter au protocole.

---

## 1. VaultChat ✅ (résolu)

**Contrat** : `VaultChatAnchor.slx` (déjà créé)

**Comment ça marche sans signer à chaque message** :
1. L'utilisateur signe UNE fois `register_session(chat_pubkey)` (1 tx, 1 gas)
2. Tous les messages suivants sont signés localement avec la private key (0 gas)
3. Un réseau de relayers vérifie les signatures et stocke les messages off-chain
4. Toutes les heures, un relayer ancre un merkle root on-chain (1 tx/h pour tout le protocole)
5. Messages chiffrés E2E (seuls sender + receiver peuvent lire)

**Avantages** : UX parfaite, gas minimal, historique vérifiable, modération possible.

---

## 2. Vault Notifications (alertes automatiques)

**Problème** : Les utilisateurs doivent vérifier manuellement leur health factor.

**Solution** : Système de notifications on-chain + off-chain.

- **On-chain** : `NotificationCenter.slx` — les utilisateurs enregistrent leur préférence (push, email hash, telegram chat_id chiffré)
- **Off-chain** : Un bot surveille les events on-chain et envoie des notifications :
  - "Your vault health factor dropped below 150%"
  - "Your vault is now liquidatable"
  - "Price moved 10% in 5 minutes"
  - "Your governance proposal was executed"
  - "You received VLT rewards"

**UX** : L'utilisateur signe une fois pour activer les notifications, puis tout est automatique.

---

## 3. Vault Templates (one-click strategies)

**Idée** : Des templates pré-configurés pour des stratégies courantes.

- **"Safe Vault"** : MCR 250%, conservative borrowing
- **"Leverage Loop"** : Borrow xUSD → swap for XEL → deposit → borrow more (auto-compound)
- **"Yield Farmer"** : Borrow xUSD → deposit in SavingsRate → earn yield spread
- **"PSM Arbitrageur"** : Monitor peg deviation → auto-arbitrage between PSM and VaultSwap

**Contrat** : `VaultTemplate.slx` — chaque template est un script qui exécute plusieurs transactions en une seule (batch).

---

## 4. Credit Score (réputation on-chain)

**Idée** : Système de réputation pour les emprunteurs P2P (PeerLoan, SyndicatePool).

- Chaque utilisateur a un credit score (0-1000) basé sur :
  - Historique de repayment (punctual vs late vs default)
  - Volume total emprunté/remboursé
  - Duration moyenne des prêts
  - Collateral ratio moyen

- Le score affecte :
  - Taux d'intérêt (meilleur score = taux plus bas)
  - LTV max (meilleur score = LTV plus élevé)
  - Accès aux pools premium

**Contrat** : `CreditScore.slx` — calcule et stocke le score de chaque utilisateur.

---

## 5. Vault Insurance (auto-insurance)

**Idée** : Les vaults peuvent s'auto-assurer contre la liquidation.

- L'utilisateur paie une petite prime (0.5% du borrow amount)
- Si le health factor tombe sous 120%, l'insurance rembourse automatiquement la dette avec le collateral (évite la liquidation et la penalty de 10%)
- Les primes sont accumulées dans un pool qui gagne des intérêts

**Contrat** : `VaultInsurance.slx` — extension du VaultEngine.

---

## 6. Cross-Asset Vaults (multi-collateral)

**Idée** : Une vault qui accepte plusieurs types de collateral simultanément.

- Deposit XEL + VLT + RWA Gold dans la même vault
- Le health factor est calculé sur la valeur totale
- Diversification du risque (si XEL chute, le gold peut compenser)

**Contrat** : `MultiCollateralVault.slx` — extension du VaultEngine.

---

## 7. Liquidation Bot Marketplace

**Idée** : Marketplace pour les liquidation bots.

- Les liquidateurs peuvent "stake" du capital pour être prioritaires
- Le protocole récompense les liquidateurs les plus rapides
- Système de classement (leaderboard)
- API publique pour les liquidation bots

**Contrat** : `LiquidationMarket.slx` — gère les stakes et priorités des liquidateurs.

---

## 8. Vault Analytics (on-chain metrics)

**Idée** : Contrat qui stocke des métriques agrégées pour le dashboard.

- TVL historique (snapshot toutes les heures)
- Volume de swap par jour
- Nombre de liquidations par jour
- Distribution des health factors
- Provider rewards distribués

**Contrat** : `AnalyticsCollector.slx` — collecte et stocke les métriques (appelé par les autres contrats via hooks).

---

## 9. Social Trading (copy trading)

**Idée** : Suivre et copier automatiquement les stratégies d'autres utilisateurs.

- Un utilisateur "suivi" rend sa vault publique (volontairement)
- Les followers peuvent auto-répliquer ses actions (deposit, borrow, swap)
- Le suivi est proportionnel (si le leader emprunte 10% de son collateral, le follower aussi)

**Contrat** : `SocialTrading.slx` — gère les relations leader/follower.

---

## 10. Yield Optimizer (auto-compounding)

**Idée** : Bot qui optimise automatiquement le yield.

- Surveille les taux d'intérêt sur LendingMarket vs SavingsRate
- Déplace automatiquement les fonds vers le rendement le plus élevé
- Réinvestit les rewards automatiquement
- L'utilisateur signe une fois pour autoriser, puis tout est automatique

**Contrat** : `YieldOptimizer.slx` — gère les stratégies d'optimisation.

---

## 11. Vault NFTs (position tokenization)

**Idée** : Tokeniser les positions de vault en NFTs.

- Chaque vault devient un NFT (ERC-721 equivalent)
- L'utilisateur peut transférer, vendre, ou utiliser son vault comme collateral
- Marché secondaire pour les vaults (vend une vault avec un bon health factor à un premium)
- Fractionalisation : diviser une vault en plusieurs parts

**Contrat** : `VaultNFT.slx` — wrap le VaultEngine pour tokeniser les positions.

---

## 12. Governance Delegation (liquid democracy)

**Idée** : Déléguer son voting power à un expert, avec retrait à tout moment.

- Un utilisateur peut déléguer son voting power à un "delegate"
- Le delegate vote avec son propre VP + celui de tous ses delegators
- Les delegators peuvent reprendre leur VP à tout moment (liquid democracy)
- Système de réputation pour les delegates

**Contrat** : `GovernanceDelegation.slx` — gère les délégations.

---

## 13. Emergency Shutdown (circuit breaker global)

**Idée** : Pause globale de tout le protocole en cas d'attaque.

- Un guardian peut déclencher un shutdown global
- Tous les contrats sont pausés simultanément
- Les utilisateurs peuvent uniquement withdraw (pas borrow, pas swap)
- Le shutdown nécessite un vote de governance pour être levé

**Contrat** : `EmergencyShutdown.slx` — gère le shutdown global.

---

## 14. Vault Bounties (récompenses pour debug)

**Idée** : Récompenser les utilisateurs qui trouvent des vaults unhealthy.

- Si un utilisateur trouve une vault avec health factor < 100%, il reçoit une bounty
- La bounty est payée par la penalty de liquidation
- Incite les liquidateurs à surveiller activement le protocole

---

## 15. Privacy Mixer (confidential transactions)

**Idée** : Mixer pour anonymiser complètement les flux de fonds.

- Deposit xUSD → receive a note (privately)
- Withdraw xUSD from a different address using the note
- Impossible de lier le deposit au withdraw
- Utilise des preuves ZK (comme Tornado Cash mais sur XELIS)

**Contrat** : `PrivacyMixer.slx` — utilise les ZK proofs natives d'XELIS.

---

## Priorisation recommandée

| Priorité | Feature | Effort | Impact |
|---|---|---|---|
| P0 | VaultChat | Moyen | Communauté |
| P1 | Vault Notifications | Faible | Rétention |
| P1 | Vault Analytics | Faible | Dashboard |
| P2 | Credit Score | Moyen | P2P lending |
| P2 | Vault Insurance | Moyen | Sécurité |
| P2 | Multi-Collateral Vaults | Élevé | Flexibilité |
| P3 | Yield Optimizer | Élevé | Yield |
| P3 | Social Trading | Élevé | Communauté |
| P3 | Vault NFTs | Moyen | Liquidity |
| P3 | Governance Delegation | Faible | Governance |
| P4 | Privacy Mixer | Très élevé | Privacy |
| P4 | Emergency Shutdown | Faible | Sécurité |

---

*XELIS Vault — Future Features Roadmap*
