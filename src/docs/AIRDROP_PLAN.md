# XELIS Vault — Airdrop Plan v10.4

> **Date :** 9 août 2026
> **Allocation totale :** 700 000 VLT (7% de la supply)
>   - 500 000 VLT pour les contributeurs testnet (5%)
>   - 200 000 VLT pour le launch mainnet (2%, first-come-first-served)

---

## 1. Vue d'ensemble du processus

```
TESTNET (phase de test)                    MAINNET (after launch)
┌─────────────────────────────────┐        ┌────────────────────────────┐
│                                 │        │                            │
│  Users interagissent avec le    │        │  AirdropClaim.slx          │
│  protocole (mine, chat, vote)   │        │  - Merkle root stocké      │
│         │                       │        │  - claim(proof, amount)    │
│         ▼                       │        │                            │
│  Contrats core émettent events  │        │  User appelle claim()      │
│         │                       │        │  avec son proof            │
│         ▼                       │        │         │                  │
│  AirdropTracker.slx             │        │         ▼                  │
│  - Accumule points par user     │        │  Vérification Merkle       │
│  - Caps quotidiens anti-bot     │        │  Mint VLT → mainnet_addr   │
│                                 │        │                            │
│  1. record_*() (events)         │        └────────────────────────────┘
│  2. record_mainnet_address()    │                  ▲
│  3. freeze_points()             │                  │
│  4. finalize_distribution()     │ ─────────────────┘
│     → calcule VLT par user      │
│     → Merkle root off-chain     │  Merkle root published
│  5. set_merkle_root()           │
│                                 │
└─────────────────────────────────┘
```

---

## 2. Contrats impliqués

### AirdropTracker.slx (sur TESTNET)

**Fichier :** `contracts/airdrop/AirdropTracker.slx` (32 entries)

**Rôle :** Accumule les points de contribution de chaque utilisateur testnet.

**Fonctions principales :**
- `record_mining_activity(miner, valid_submissions, runtime_blocks)` — appelé par XelisVaultMiner
- `record_relayer_activity(relayer, valid_anchors, uptime_blocks)` — appelé par VaultChat
- `record_governance_vote(voter, proposal_id)` — appelé par Governor
- `record_chat_message(sender)` — appelé par VaultChat
- `record_liquidity_provided(user, xel_amount)` — appelé par VaultEngine/VaultSwap/PSM
- `record_bug_bounty(reporter, severity)` — admin only
- `record_mainnet_address(mainnet_addr)` — user enregistre son adresse mainnet
- `freeze_points()` — admin arrête la collecte
- `finalize_distribution()` — admin calcule la distribution (bonus inclus)
- `set_merkle_root(root)` — admin stocke le Merkle root final

**Getters publics :**
- `get_user_points(user)` — points totaux (avec bonus si finalisé)
- `get_user_breakdown(user)` — détail par catégorie
- `get_user_distribution(user)` — VLT à recevoir
- `get_total_points()` — somme totale (pour vérification)
- `get_qualified_users()` — nombre d'utilisateurs qualifiés

### AirdropClaim.slx (sur MAINNET)

**Fichier :** `contracts/airdrop/AirdropClaim.slx` (16 entries)

**Rôle :** Distribue les VLT aux utilisateurs qualifiés via Merkle proofs.

**Fonction principale :**
```silex
entry claim(
    testnet_addr: Address,    // adresse testnet de l'utilisateur
    mainnet_addr: Address,    // adresse mainnet (où recevoir les VLT)
    amount: u64,              // montant en VLT atomic
    proof: Hash[]             // Merkle proof
) -> u64
```

**Vérifications :**
1. `caller == mainnet_addr` (prouve ownership de l'adresse mainnet)
2. `amount > 0`
3. Merkle root est set
4. User n'a pas déjà claim (anti double-claim)
5. `verify_merkle_proof(proof, leaf, root)` (leaf = hash(testnet||mainnet||amount))

**Si tout OK :** Mint `amount` VLT à `mainnet_addr`.

---

## 3. Système de points

### Catégories et actions

| Catégorie | Action | Points | Cap quotidien |
|-----------|--------|--------|---------------|
| **MINING** | 1 prix valide soumis | 1 pt | 1000 pts/jour |
| | 1 heure de runtime | 50 pts | — |
| **RELAYER** | 1 anchor valide (≥5 msgs) | 10 pts | 500 pts/jour |
| | 1 jour d'uptime | 200 pts | — |
| **GOVERNANCE** | 1 vote | 50 pts | — |
| | 1 proposition créée | 500 pts | — |
| **CHAT** | 1 message envoyé | 1 pt | 100 pts/jour |
| | 1 groupe créé | 100 pts | — |
| **LIQUIDITY** | 1 XEL déposé (LP, vault, PSM) | 10 pts | — |
| **BOUNTY** | Bug critique | 5 000 pts | — |
| | Bug high | 1 000 pts | — |
| | Bug medium | 200 pts | — |
| **COMMUNITY** | Aide Discord (manuel) | 50 pts | — |
| | Doc/tutorial écrit | 200 pts | — |

### Bonus (appliqués au finalize)

| Bonus | Condition | Multiplicateur |
|-------|-----------|----------------|
| Multi-role | 3+ catégories actives | +25% sur le total |
| Early miner | Top 100 miners par stake | +50% mining (TODO: requires integration) |
| High reputation | Reputation > 9000 sur tout le testnet | +30% total (TODO: requires integration) |

> Les bonus "Early miner" et "High reputation" nécessitent une intégration plus poussée avec XelisVaultMiner. Pour la v10.4 initiale, seul le bonus Multi-role est appliqué automatiquement. Les autres peuvent être ajoutés via `record_manual_attribution`.

### Conditions de qualification

Pour qualifier pour l'airdrop, un utilisateur doit :
1. **Min 1 000 points cumulés** (filtre les bots occasionnels)
2. **Min 7 jours distincts d'activité** (pas 7 jours consécutifs, mais 7 jours différents)
3. **Avoir enregistré son adresse mainnet** via `record_mainnet_address()`

---

## 4. Distribution

### Formule

```
user_vlt = (user_total_points × 500 000 VLT) / sum(all_qualified_users_total_points)
```

### Exemple

| User | Points (avec bonus) | % du total | VLT reçus |
|------|---------------------|------------|-----------|
| Alice | 50 000 | 2% | 10 000 VLT |
| Bob | 5 000 | 0.2% | 1 000 VLT |
| Charlie | 500 000 | 20% | 100 000 VLT |
| ... | ... | ... | ... |
| **Total** | **2 500 000** | **100%** | **500 000 VLT** |

---

## 5. Processus de snapshot et claim

### Étape 1 — Annonce (T-7 jours)

- Annoncer publiquement la date de snapshot
- Rappeler aux users d'enregistrer leur adresse mainnet via `record_mainnet_address()`
- Dernière chance de gagner des points

### Étape 2 — Freeze (T=0)

1. Admin appelle `freeze_points()` sur AirdropTracker
2. Aucun nouveau point n'est accepté
3. Les users ne peuvent plus enregistrer d'adresse mainnet

### Étape 3 — Finalize (T+1 jour)

1. Admin appelle `finalize_distribution()` sur AirdropTracker
2. Le contrat :
   - Itère tous les users
   - Vérifie la qualification (min points + min jours + mainnet addr)
   - Applique les bonus
   - Calcule `total_with_bonus` par user
   - Calcule `user_distribution = (total_with_bonus × 500 000 VLT) / total_all`

### Étape 4 — Génération du Merkle tree (off-chain)

1. Lancer `scripts/generate_airdrop_merkle.py` :
   ```bash
   python3 scripts/generate_airdrop_merkle.py \
       --rpc http://testnet-rpc.xelis.io \
       --tracker <airdrop_tracker_hash> \
       --output airdrop_distribution.json
   ```
2. Le script :
   - Fetch tous les users qualifiés depuis AirdropTracker
   - Build les leaves : `keccak256(testnet_addr || mainnet_addr || amount)`
   - Build le Merkle tree
   - Génère `airdrop_distribution.json` avec :
     - `merkle_root`
     - Pour chaque user : `testnet_addr`, `mainnet_addr`, `amount`, `proof`

### Étape 5 — Publication

1. Publier `airdrop_distribution.json` sur IPFS + GitHub
2. Vérification indépendante : la communauté peut vérifier que son allocation est correcte
3. Merkle root publié publiquement

### Étape 6 — Déploiement AirdropClaim (mainnet)

1. Déployer `AirdropClaim.slx` sur mainnet
2. Appeler `set_merkle_root(<root>)`
3. Appeler `set_vlt_contract(<VLT_token_hash>)`
4. Transférer 500 000 VLT au contrat AirdropClaim

### Étape 7 — Claim (6 mois)

1. Users appellent `claim(testnet_addr, mainnet_addr, amount, proof)` sur mainnet
2. Le contrat vérifie et mint les VLT
3. Après 6 mois, les fonds non réclamés vont au treasury via `emergency_withdraw_unclaimed()`

---

## 6. Anti-Sybil (anti-bot)

### Mesures on-chain

1. **Caps quotidiens** : max 1000 pts/jour en mining, 500 en relayer, 100 en chat
2. **Min 7 jours distincts** : un bot qui mine 24/7 pendant 1 jour ne qualify pas
3. **Min 1 000 points** : filtre les bots occasionnels
4. **Adresse mainnet obligatoire** : prouve que l'user a une intention long-terme

### Mesures off-chain (indexer)

1. **Détection de patterns** : 5 addresses qui soumettent toujours le même prix à la même seconde → suspect
2. **Analyse d'IP** (relayer-side) : pas 2 addresses avec la même IP relayer
3. **Validation manuelle** : pour les cas litigieux, governance vote

### Mesures de governance

1. **`record_manual_attribution`** : admin peut ajouter des points pour contributions off-chain (Discord, docs)
2. **`record_bug_bounty`** : bugs signalés via process séparé (Immunefi-style)
3. **Dispute mechanism** : un user peut contester son score via governance proposal

---

## 7. Intégration avec les contrats core

### Option A : Appel direct (recommandé pour 4 contrats critiques)

Les contrats suivants appellent directement AirdropTracker via cross-contract call :
- `XelisVaultMiner.slx` — appelle `record_mining_activity` après `submit_price`
- `StakedOracle.slx` — appelle `record_mining_activity` après `submit_price`
- `VaultChat.slx` — appelle `record_relayer_activity` après `anchor_messages` + `record_chat_message` après `store_message`
- `Governor.slx` — appelle `record_governance_vote` après `vote` + `record_governance_proposal` après `propose`

**Pattern :**
```silex
// In XelisVaultMiner, after submit_price:
let tracker_opt: optional<Hash> = s.load(AIRDROP_TRACKER_KEY)
if tracker_opt.is_some() {
    let tracker_hash: Hash = tracker_opt.expect("err")
    if tracker_hash != Hash::zero() {
        let tracker: Contract = Contract::new(tracker_hash).expect("err")
        let _ = tracker.call(0u16, [caller, 1u64, 0u64], {})  // record_mining_activity
    }
}
```

### Option B : Indexer bot (pour les autres contrats)

Pour les contrats qui n'appellent pas directement AirdropTracker :
- `VaultEngineV3` (deposit) → indexer lit l'event `Deposit`
- `VaultSwapV2` (add_liquidity) → indexer lit l'event `LiquidityAdded`
- `PSM` (mint) → indexer lit l'event `PSMMint`
- `LiquidationMarket` → indexer lit l'event `LiquidationExecuted`
- `VaultBounties` → indexer lit l'event `BountyClaimed`

Le bot `scripts/airdrop_indexer.py` écoute ces events et appelle `record_*` sur AirdropTracker.

---

## 8. Launch airdrop (200 000 VLT)

Séparé du testnet airdrop, pour le lancement mainnet :

- **First-come-first-served** pour les 1000 premiers users mainnet
- 200 VLT par user
- **Condition :** min 1 transaction sur le protocole (déposit, swap, ou chat)
- **Objectif :** bootstrapper l'activité mainnet

Implémentation : simple contrat `LaunchAirdrop.slx` (à créer si besoin) qui distribute 200 VLT aux 1000 premiers addresses qui font une transaction.

---

## 9. Checklist de déploiement

### Avant le testnet

- [ ] Déployer `AirdropTracker.slx` sur testnet
- [ ] Appeler `set_authorized_recorder(XelisVaultMiner_addr, true)`
- [ ] Appeler `set_authorized_recorder(StakedOracle_addr, true)`
- [ ] Appeler `set_authorized_recorder(VaultChat_addr, true)`
- [ ] Appeler `set_authorized_recorder(Governor_addr, true)`
- [ ] Appeler `set_authorized_recorder(indexer_wallet_addr, true)` pour le bot
- [ ] Lancer `airdrop_indexer.py` pour les contrats sans appel direct
- [ ] Annoncer le programme d'airdrop à la communauté

### Pendant le testnet

- [ ] Monitorer les points accumulés via `get_total_points()`
- [ ] Vérifier que les caps quotidiens fonctionnent
- [ ] Détecter les patterns suspects (bot farms)
- [ ] Ajouter des points manuels pour contributions community (Discord, docs)

### À la fin du testnet

- [ ] Annoncer la date de snapshot (T-7 jours)
- [ ] Rappeler aux users d'enregistrer leur adresse mainnet
- [ ] À T=0 : appeler `freeze_points()`
- [ ] À T+1 jour : appeler `finalize_distribution()`
- [ ] Lancer `generate_airdrop_merkle.py` pour générer le Merkle tree
- [ ] Publier `airdrop_distribution.json` sur IPFS + GitHub
- [ ] Vérification indépendante par la communauté

### Sur mainnet

- [ ] Déployer `AirdropClaim.slx`
- [ ] Appeler `set_merkle_root(<root>)`
- [ ] Appeler `set_vlt_contract(<VLT_hash>)`
- [ ] Transférer 500 000 VLT au contrat AirdropClaim
- [ ] Ouvrir le claim pendant 6 mois
- [ ] Après 6 mois : `emergency_withdraw_unclaimed()` pour les fonds non réclamés

---

## 10. Getters pour le site web (dashboard)

Le contrat `AirdropTracker` expose **25 pub fn** pour permettre à un site web d'afficher toutes les infos en temps réel.

### Stats globales (page d'accueil)

| Fonction | Retourne | Usage |
|----------|----------|-------|
| `get_protocol_stats()` | `(user_count, qualified_count, total_points, total_distributable, frozen, finalized)` | Header stats bar |
| `get_total_points()` | `u64` | Total points accumulés |
| `get_user_count()` | `u64` | Nombre de participants |
| `get_qualified_users()` | `u64` | Nombre d'utilisateurs qualifiés |
| `get_total_distributable()` | `u64` | 500 000 VLT (constant) |
| `get_all_category_totals()` | `(mining, relayer, gov, chat, liq, bounty, community)` | Pie chart par catégorie |
| `get_category_total(cat)` | `u64` | Total pour une catégorie |
| `is_frozen()` | `bool` | État de la collecte |
| `is_finalized()` | `bool` | État de la distribution |
| `get_snapshot_info()` | `(deploy_topo, freeze_topo, finalize_topo, current_topo)` | Timeline |

### Profil utilisateur (page user)

| Fonction | Retourne | Usage |
|----------|----------|-------|
| `get_user_full_info(user)` | `(mining, relayer, gov, chat, liq, bounty, community, total_raw, total_with_bonus, days_active, mainnet_addr, qualified, rank)` | Profil complet |
| `get_user_points(user)` | `u64` | Points totaux |
| `get_user_breakdown(user)` | `(mining, relayer, gov, chat, liq, bounty, community, total_raw, total_with_bonus, qualified, registered)` | Bar chart par catégorie |
| `get_user_distribution(user)` | `u64` | VLT à recevoir (après finalize) |
| `get_estimated_distribution(user)` | `u64` | VLT estimé (avant finalize) |
| `get_user_percentage(user)` | `u64` | % du total (en bps) |
| `get_user_rank(user)` | `u64` | Position dans le classement (1-indexed) |
| `get_user_activity_summary(user)` | `(days_active, last_active_day, qualified, has_mainnet)` | Stats d'activité |
| `get_mainnet_address(user)` | `Address` | Adresse mainnet enregistrée |
| `is_qualified(user)` | `bool` | Si l'utilisateur est qualifié |

### Leaderboard (page classement)

| Fonction | Retourne | Usage |
|----------|----------|-------|
| `get_leaderboard_at_rank(rank)` | `Address` | Adresse à la position `rank` |
| `get_leaderboard_entry(rank)` | `(addr, points, qualified, mainnet_addr, distribution)` | Entrée complète à la position `rank` |
| `get_user_at_index(index)` | `Address` | N-ième user (pour itération) |

### Reverse lookup (recherche)

| Fonction | Retourne | Usage |
|----------|----------|-------|
| `get_testnet_address(mainnet_addr)` | `Address` | Trouve le user testnet depuis son addr mainnet |

### Merkle & claim (page mainnet)

| Fonction | Retourne | Usage |
|----------|----------|-------|
| `get_merkle_root()` | `Hash` | Root publié pour vérification |

### Exemple d'intégration site web

```javascript
// Page d'accueil — stats bar
const stats = await tracker.call("get_protocol_stats", []);
// stats = [userCount, qualifiedCount, totalPoints, totalDistributable, frozen, finalized]

// Pie chart — répartition par catégorie
const totals = await tracker.call("get_all_category_totals", []);
// totals = [mining, relayer, governance, chat, liquidity, bounty, community]

// Profil user — toutes les infos en 1 call
const userInfo = await tracker.call("get_user_full_info", [userAddr]);
// userInfo = [mining, relayer, gov, chat, liq, bounty, community,
//             totalRaw, totalWithBonus, daysActive, mainnetAddr, qualified, rank]

// Leaderboard top 10
for (let rank = 1; rank <= 10; rank++) {
    const entry = await tracker.call("get_leaderboard_entry", [rank]);
    // entry = [testnetAddr, points, qualified, mainnetAddr, distribution]
}

// Distribution estimée (avant finalize)
const estAmount = await tracker.call("get_estimated_distribution", [userAddr]);
```

---

## 11. Scripts fournis

| Script | Rôle |
|--------|------|
| `scripts/airdrop_indexer.py` | Bot qui écoute les events on-chain et appelle `record_*` sur AirdropTracker |
| `scripts/generate_airdrop_merkle.py` | Génère le Merkle tree + proofs depuis AirdropTracker (après finalize) |

---

## 12. Estimations

### Scenario 1 : Testnet modeste (100 users actifs)

- 50 miners × 10 000 pts = 500 000 pts
- 20 relayers × 5 000 pts = 100 000 pts
- 30 governance voters × 1 000 pts = 30 000 pts
- 80 chat users × 2 000 pts = 160 000 pts
- Total : ~790 000 pts

Average distribution : 500 000 / 100 = 5 000 VLT par user (= $2 500 au prix de $0.50)

### Scenario 2 : Testnet réussi (1000 users actifs)

- 300 miners × 20 000 pts = 6 000 000 pts
- 50 relayers × 8 000 pts = 400 000 pts
- 200 governance voters × 1 500 pts = 300 000 pts
- 500 chat users × 3 000 pts = 1 500 000 pts
- Total : ~8 200 000 pts

Average distribution : 500 000 / 1000 = 500 VLT par user (= $250)

---

*XELIS Vault — Airdrop Plan v10.4 (9 août 2026)*
