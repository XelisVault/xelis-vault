# Future Features — XELIS Vault

> Brainstorming de features innovantes à ajouter au protocole.
>
> **Status :** Toutes les features P0-P3 sont implémentées en v10.2 (13 nouveaux contrats Silex).

---

## 1. VaultChat ✅ (résolu v4.3)

**Contrat** : `VaultChat.slx` (déjà créé)

**Comment ça marche sans signer à chaque message** :
1. L'utilisateur signe UNE fois `register_session(chat_pubkey)` (1 tx, 1 gas)
2. Tous les messages suivants sont signés localement avec la private key (0 gas)
3. Un réseau de relayers vérifie les signatures et stocke les messages off-chain
4. Toutes les heures, un relayer ancre un merkle root on-chain (1 tx/h pour tout le protocole)
5. Messages chiffrés E2E (seuls sender + receiver peuvent lire)

**Avantages** : UX parfaite, gas minimal, historique vérifiable, modération possible.

---

## 2. Vault Notifications ✅ (implémenté v10.2)

**Contrat** : `contracts/notifications/NotificationCenter.slx` (14 entries)

**Comment ça marche** :
1. L'utilisateur signe `register_preferences(encrypted_push_token, encrypted_email_hash, encrypted_telegram_id, ...)` UNE fois
2. Les bots off-chain écoutent les events `Notify(recipient, type, severity)` émis par les contrats du protocole
3. Les bots déchiffrent les payloads (avec la clé privée de l'utilisateur via XSWD) et envoient les notifications via le canal préféré
4. Quiet hours respectées (l'utilisateur définit ses heures de silence)
5. Notification types : vault health, liquidation, price alert, governance, rewards, chat, P2P loan

**Privacy** :
- Aucune donnée PII stockée en clair (email hashé, push token chiffré, telegram chiffré)
- Seul l'utilisateur peut décoder son payload
- Les bots ne voient que des blobs chiffrés

---

## 3. Vault Templates ✅ (implémenté v10.2)

**Contrat** : `contracts/vault/VaultTemplates.slx` (18 entries)

**Templates disponibles** :
- **Safe Vault** : Deposit XEL, borrow 50% LTV xUSD, hold (1 tx au lieu de 2)
- **Leverage Loop** : Deposit → borrow → swap → deposit, repeat 3x (1 tx au lieu de 7-10)
- **Yield Farmer** : Deposit → borrow xUSD → deposit in SavingsRate (1 tx au lieu de 3)
- **PSM Arbitrageur** : Monitor peg deviation, auto-arbitrage (1 tx)
- **Liquidity Provider** : Deposit → borrow → provide LP on VaultSwap (1 tx au lieu de 3)

**Sécurité** :
- Slippage protection (`min_out` parameters)
- Max leverage cap (3 iterations)
- Emergency exit function (1 tx pour tout fermer)

---

## 4. Credit Score ✅ (implémenté v10.2)

**Contrat** : `contracts/credit/CreditScore.slx` (15 entries)

**Scoring (0-1000)** :
- Score initial : 500 (neutral)
- +50 par prêt remboursé à temps, +20 par prêt remboursé en avance
- -30 par prêt remboursé en retard (<7 jours), -100 si >7 jours
- -300 par default
- +1 par XEL de volume (capped +100)
- +5 par mois de durée moyenne (capped +50)
- +10 par tranche de 10% de collateral ratio au-dessus de 150% (capped +100)

**Tiers** :
| Tier | Score | Rate adj. | LTV adj. | Access |
|------|-------|-----------|----------|--------|
| Excellent | 800-1000 | -2% | +10% | Premium pools |
| Good | 650-799 | -1% | +5% | All pools |
| Fair | 450-649 | 0% | 0% | Standard |
| Poor | 250-449 | +3% | -5% | Limited |
| Very Poor | 0-249 | +5% | -10% | Locked out |

Le score est public (réputation), mais les détails sont privés.

---

## 5. Vault Insurance ✅ (implémenté v10.2)

**Contrat** : `contracts/insurance/VaultInsurance.slx` (18 entries)

**Comment ça marche** :
1. L'utilisateur paie une prime de 0.5% du borrow amount
2. Si le health factor tombe sous 120%, n'importe qui peut déclencher `trigger_auto_repay(vault_id)`
3. Le pool d'insurance rembourse la dette avec le collateral (évite la liquidation + 10% penalty)
4. Le collateral résiduel est conservé pour l'utilisateur (après 2% fee)
5. L'utilisateur peut réclamer le résiduel via `claim_residual_collateral`

**Pool d'insurance** :
- Les LPs stake du VLT pour fournir la liquidité
- 70% des primes vont aux stakers (proportionnellement)
- 20% en réserve (pour les paiements)
- 10% au treasury du protocole

---

## 6. Cross-Asset Vaults ✅ (implémenté v10.2)

**Contrat** : `contracts/vault/MultiCollateralVault.slx` (18 entries)

**Features** :
- Une vault accepte jusqu'à 10 types de collateral différents (XEL, VLT, xUSD, RWA Gold, RWA RealEstate)
- LTV par asset : XEL 75%, VLT 60%, xUSD 90%, Gold 70%, RealEstate 50%
- Health factor calculé sur la valeur totale diversifiée
- Liquidation : tous les collaterals saisis proportionnellement
- Max 10 assets par vault

**Avantage** : Si XEL chute de 30%, mais que le gold monte de 10%, le health factor ne chute que de ~20% au lieu de 30%.

---

## 7. Liquidation Bot Marketplace ✅ (implémenté v10.2)

**Contrat** : `contracts/liquidation/LiquidationMarket.slx` (17 entries)

**Mécanique** :
1. Liquidators stake min 1000 VLT pour être prioritaires
2. Plus le stake est élevé, plus la priorité est haute (score = stake × reputation)
3. Quand une vault devient liquidable, le liquidator prioritaire est notifié
4. S'il exécute la liquidation dans les 10 blocks : bonus de rapidité jusqu'à 2%
5. S'il n'agit pas, le suivant dans la queue prend le relais
6. Leaderboard public (top liquidators par exécutions + reputation)

**Anti-centralisation** :
- Max 20% du stake total par liquidator
- Min 5 liquidators actifs requis
- Inactifs perdent 50 points de réputation par missed liquidation

---

## 8. Vault Analytics ✅ (implémenté v10.2)

**Contrat** : `contracts/analytics/AnalyticsCollector.slx` (17 entries)

**Métriques collectées** :
- TVL historique (snapshots horaires, 7 jours retention)
- Volume de swap par jour (1 an retention)
- Nombre de liquidations par jour
- Distribution des health factors (11 buckets anonymisés)
- Rewards distribués (cumul + par jour)
- Utilisateurs actifs par jour
- Vaults ouverts/fermés
- PEG de xUSD (moyenne mobile)

**Privacy** : Aucune donnée individuelle. Tout est agrégé et anonymisé.

**Architecture** : Ring buffer pour TVL (168 entries = 7 jours), daily stats (365 entries = 1 an).

---

## 9. Social Trading ✅ (implémenté v10.2)

**Contrat** : `contracts/social/SocialTrading.slx` (16 entries)

**Comment ça marche** :
1. Leader call `make_vault_public(vault_id)` — opt-in volontaire
2. Follower call `follow_leader(leader, ratio_bps)` — ratio 10-100%
3. Quand le leader fait deposit/borrow/repay/withdraw/swap, le contrat émet `LeaderAction(leader, type, amount, asset)`
4. Les bots des followers écoutent ces events et exécutent les mêmes actions proportionnellement
5. Le follower peut `stop_follow` à tout moment (liquid democracy)

**Limites anti-abus** :
- Max 100 followers par leader
- Max 10 leaders par follower (diversification)
- Le leader ne peut cacher que SA propre vault
- Un follower ne peut suivre un leader qu'une fois

**Privacy** : Le leader rend SEULEMENT la vault sélectionnée publique. Les followers voient les actions mais pas l'historique complet.

---

## 10. Yield Optimizer ✅ (implémenté v10.2)

**Contrat** : `contracts/vault/YieldOptimizer.slx` (19 entries)

**Stratégies** :
- **Conservative** : 100% SavingsRate (lowest risk)
- **Balanced** : 50% SavingsRate + 50% LendingMarket (ajusté dynamiquement 40-60%)
- **Aggressive** : 100% LendingMarket (highest yield)
- **VLT Max** : 100% GovernanceVault staking

**Mécanique** :
1. User `opt_in(amount, strategy)` — délègue l'optimisation
2. Un keeper call `execute_strategy(user, savings_apr, lending_apr, gov_apr)` périodiquement
3. Le contrat recale l'allocation si le yield gain > 0.01 XEL
4. Le keeper reçoit 0.1% du yield gain (incentivisé)
5. User peut `set_strategy(new_strategy)` ou `opt_out()` à tout moment

**Réinvestissement** : Les rewards accumulés sont automatiquement réinvestis dans la stratégie via `reinvest_rewards(user, amount)`.

---

## 11. Vault NFTs ✅ (implémenté v10.2)

**Contrat** : `contracts/nft/VaultNFT.slx` (23 entries)

**Features** :
- `mint_nft(vault_id)` — wrap une vault en NFT
- `transfer_nft(nft_id, to)` — transfert direct (pas besoin de withdraw + re-deposit)
- `burn_nft(nft_id)` — unwrap pour récupérer la vault
- Marketplace intégré : `list_for_sale`, `buy_nft`, `make_offer`, `accept_offer`
- `fractionalize(nft_id, share_count)` — diviser une vault en N parts (jusqu'à 10000)
- Protocol fee : 0.5% sur les ventes

**Use cases** :
- Vendre une vault avec un bon health factor à un premium
- Utiliser une vault comme collateral dans un autre protocole
- Co-propriété de vaults (fractionalisation)
- Marché secondaire liquide

**Privacy** : Le NFT pointe vers une vault dont les montants peuvent être chiffrés (Ciphertext). Le owner est public (comme tout NFT), mais pas les détails financiers.

---

## 12. Governance Delegation ✅ (implémenté v10.2)

**Contrat** : `contracts/governance/GovernanceDelegation.slx` (18 entries)

**Liquid democracy** :
1. User `delegate(delegate_addr)` — délègue tout son voting power
2. User `undelegate()` — récupère son VP instantanément (pas de lock)
3. User `delegate_by_topic(topic, delegate)` — delegate différent par domaine
   - Topics : General, Oracle, Lending, Treasury, Governance, Upgrade
4. Délégation transitive : A→B→C, C vote avec VP_A + VP_B + VP_C
5. Le Governor call `record_vote(delegate, voted_with_majority)` pour updater la réputation

**Anti-abus** :
- Profondeur max : 5 (évite les cycles)
- Max 1000 delegators par delegate (anti-concentration)
- Pas de délégué à soi-même
- Détection de cycles avant acceptation

**Réputation** : +2 par vote, +5 bonus si vote avec majorité. Plus la réputation est haute, plus le delegate est trusted.

---

## 13. Emergency Shutdown ✅ (implémenté v10.2)

**Contrat** : `contracts/safety/EmergencyShutdown.slx` (15 entries)

**États** :
| State | Déclencheur | Opérations permises |
|-------|-------------|---------------------|
| NORMAL | - | Tout |
| SOFT_PAUSE | GuardianMultisig (3/5) | Deposit, Repay, Withdraw, Gov, Chat, Mine (pas de Borrow/Swap/Liquidate) |
| FULL_SHUTDOWN | Guardian ou Admin (via timelock 24h) | Withdraw, Repay, Governance seulement |
| RECOVERY | Guardian propose, Governor vote | Withdraw, Repay, Governance |

**Levée** : Doit passer par Governor (vote 7 jours + timelock 48h, quorum 10%, approval 60%).

**Intégration** : Tous les contrats du protocole query `is_operation_allowed(op_type)` avant d'exécuter une opération utilisateur. Si false, l'opération revert.

---

## 14. Vault Bounties ✅ (implémenté v10.2)

**Contrat** : `contracts/liquidation/VaultBounties.slx` (13 entries)

**Comment ça marche** :
1. Un watcher (n'importe qui) call `report_unhealthy_vault(vault_id, vault_owner, collateral_amount, current_health_bps)`
2. Le contrat vérifie que health < 100% (liquidable)
3. Si oui, le watcher reçoit une bounty de 0.5% du collateral (min 1 XEL, max 100 XEL)
4. Le watcher peut `claim_bounty(vault_id)` après liquidation
5. La vault est ensuite liquidée par le LiquidationMarket

**Anti-abus** :
- Un watcher ne peut pas signaler sa propre vault
- Max 10 bounties par jour par watcher
- Une vault ne peut être signalée qu'une fois
- Bounty minimum 1 XEL, maximum 100 XEL

---

## 15. Privacy Mixer ✅ (résolu v4.3)

**Contrat** : `contracts/privacy/PrivacyMixer.slx` (déjà créé)

- Deposit xUSD → receive a note (privately)
- Withdraw xUSD from a different address using the note
- Impossible de lier le deposit au withdraw
- Merkle tree de profondeur 24
- Denominations : 10 / 100 / 1000 xUSD

---

## Priorisation finale

| Priorité | Feature | Statut | Contrat | Entries |
|---|---|---|---|---|
| P0 | VaultChat | ✅ v4.3 | VaultChat.slx | 125 |
| P1 | Vault Notifications | ✅ v10.2 | NotificationCenter.slx | 14 |
| P1 | Vault Analytics | ✅ v10.2 | AnalyticsCollector.slx | 17 |
| P2 | Credit Score | ✅ v10.2 | CreditScore.slx | 15 |
| P2 | Vault Insurance | ✅ v10.2 | VaultInsurance.slx | 18 |
| P2 | Multi-Collateral Vaults | ✅ v10.2 | MultiCollateralVault.slx | 18 |
| P3 | Yield Optimizer | ✅ v10.2 | YieldOptimizer.slx | 19 |
| P3 | Social Trading | ✅ v10.2 | SocialTrading.slx | 16 |
| P3 | Vault NFTs | ✅ v10.2 | VaultNFT.slx | 23 |
| P3 | Governance Delegation | ✅ v10.2 | GovernanceDelegation.slx | 18 |
| P3 | Liquidation Marketplace | ✅ v10.2 | LiquidationMarket.slx | 17 |
| P3 | Vault Bounties | ✅ v10.2 | VaultBounties.slx | 13 |
| P3 | Emergency Shutdown | ✅ v10.2 | EmergencyShutdown.slx | 15 |
| P3 | Vault Templates | ✅ v10.2 | VaultTemplates.slx | 18 |
| P4 | Privacy Mixer | ✅ v4.3 | PrivacyMixer.slx | 20 |

**Total brainstorming v10.2** : 13 nouveaux contrats, ~4 800 lignes Silex, 225 entry functions, 30+ pub fn getters.

---

## Prochaines étapes (post-v10.2)

- **Compilation** : Tester les 46 contrats avec le compilateur Silex officiel
- **Testnet** : Déploiement ~25 août 2026
- **Audit externe** : Q4 2026 (Slixe + second auditor)
- **Mainnet** : Q1 2027

*XELIS Vault — Brainstorming Features Roadmap (v10.2 — 9 août 2026)*
