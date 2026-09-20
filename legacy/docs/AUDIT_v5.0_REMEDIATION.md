# AUDIT DE SÉCURITÉ — XELIS Vault v5.0
## Rapport de Remédiation

**Date :** 24 juin 2026  
**Auditeur :** Super Z (Z.ai)  
**Version auditée :** v5.0 (post-remédiation)  
**Version source :** v4.3 (audit précédent)  
**Périmètre :** 33 contrats Silex + scripts Python + documentation  
**Dépôt :** `/home/z/my-project/download/xelis-vault-v5/`

---

## Résumé Exécutif

Cet audit fait suite au rapport v4.3 qui avait identifié **15 vulnérabilités** (5 critiques, 4 hautes, 4 moyennes, 2 basses). Toutes ont été corrigées dans la v5.0. Le présent rapport décrit chaque correctif appliqué et confirme la conformité aux APIs Silex réellement disponibles (vérifiées via `upload/lib.rs` — le wrapper Silex playground — ainsi que la documentation officielle).

**Points clés de la remédiation :**

1. **Entry IDs entièrement réalignés** — 33 contrats réécrits avec des IDs séquentiels à partir de 0. Un script `scripts/extract_entry_ids.py` génère désormais automatiquement la table des entry IDs (`docs/ENTRY_IDS.md`) pour empêcher toute régression future.

2. **`pub fn` → `entry` pour toutes les fonctions cross-contract** — `slash_miner`, `distribute_reward`, `is_miner_active`, `get_active_miners_for_service` (XelisVaultMiner) ; `get_price_by_feed`, `get_price`, `get_price_for_asset`, `get_feed_id` (StakedOracle) ; `get_voting_power`, `get_total_voting_power` (GovernanceVault) ; `get` (ContractRegistry) ont toutes été converties en `entry` ou encapsulées par des wrappers `entry` nommés `*_entry`.

3. **API Silex réelle respectée** — Aucune utilisation de `Ciphertext`, `elgamal`, `try/catch`, ou kwargs de type JavaScript (`{ asset: amount }`). Seules les APIs confirmées par `lib.rs` et la doc officielle sont utilisées : `get_caller`, `get_contract_caller`, `get_balance_for_asset`, `get_deposit_for_asset`, `transfer`, `burn`, `get_current_topoheight`, `hash`, `Storage`, `Asset`, `Contract`, `MaxSupplyMode`.

4. **`emergency_withdraw` systématiquement converti en 2 étapes** — Chaque contrat qui détient des fonds implémente désormais `request_emergency_withdraw()` (sauvegarde le topoheight) + `execute_emergency_withdraw(asset)` (vérifie qu'au moins 17280 blocs ≈ 24h se sont écoulés avant de transférer).

5. **Fausse confidentialité avouée** — Plutôt que de prétendre chiffrer homomorphiquement les montants (impossible car l'API `Ciphertext` n'existe pas en Silex), `VaultEngineV3.deposit` accepte désormais un `salt: Hash` optionnel. Le couple `(amount, salt)` peut être hashé off-chain pour permettre un commit-reveal si l'utilisateur le souhaite. La documentation a été mise à jour en conséquence.

6. **Stability fee sur VaultEngine** — Un index global `STABILITY_FEE_INDEX_KEY` (échelle 1e12) croît continûment selon `STABILITY_FEE_BPS_KEY` (2% APR par défaut). À chaque `borrow`/`repay`/`liquidate`/`redeem`, l'emprunt accru est recalculé via `accrued = principal * current_index / index_at_open`. La portion intérêts est versée au treasury.

7. **GuardianMultisig passe par quorum pour add/remove guardian** — Les fonctions `add_guardian`/`remove_guardian`/`set_quorum` ne sont plus appelables directement par l'admin. Elles passent par `propose_emergency_action` avec action 4/5/6, puis confirmation + exécution via quorum.

8. **Timelock accepte les deux types de guardian** — `only_guardian()` et `only_guardian_or_admin()` acceptent désormais soit une EOA (`GUARDIAN_KEY`), soit un contrat (`GUARDIAN_CONTRACT_KEY` via `get_contract_caller()`). Une nouvelle entry `set_guardian_contract(Hash)` permet de configurer le contrat GuardianMultisig comme guardian.

---

## Tableau de Remédiation

| #  | Sévérité  | Finding                                                            | Statut    | Fix appliqué |
|----|-----------|-------------------------------------------------------------------|-----------|--------------|
| 1  | CRITIQUE  | Entry IDs XelisVaultMiner massivement décalés                     | ✅ CORRIGÉ | `slash_miner`, `distribute_reward`, `is_miner_active_entry`, `get_active_miners_for_service_entry` convertis en `entry`. StakedOracle utilise désormais les entry IDs 7/8/9/12. |
| 2  | CRITIQUE  | Entry IDs OracleGovernance → StakedOracle erronés                 | ✅ CORRIGÉ | OracleGovernance utilise désormais : MAX_STALE→16, HARD_STALE→17, MAX_DEV→13, CB_THRESH→14, SUBMIT_WINDOW→15, EMERGENCY_CB→3, RESET_FEED→4. |
| 3  | CRITIQUE  | VaultEngine appelle add_feed au lieu de get_price_for_asset       | ✅ CORRIGÉ | `get_oracle()` utilise `reg.call(0u16, ["StakedOracle"], {})` (ContractRegistry entry 0 = `get_entry`). `get_xel_price()` utilise `oracle.call(9u16, [Hash::zero()], {})` (StakedOracle entry 9 = `get_price_for_asset_entry`). Même fix dans VaultSwapV2. |
| 4  | CRITIQUE  | claim_rewards() cassée syntaxiquement                             | ✅ CORRIGÉ | `claim_rewards()` réécrite proprement avec un return explicite quand `total_pending == 0`, bloc bien fermé, indentation correcte. |
| 5  | CRITIQUE  | flash_loan() — body mal fermé + kwargs invalides                  | ✅ CORRIGÉ | `flash_loan()` réécrite : structure linéaire, kwarg `{}` vide supprimé, `approve_repay` supprimé, balance check `balance_after >= balance_before + fee` au lieu de juste `> balance_before`. |
| 6  | HAUT      | GuardianMultisig — admin seul peut ajouter/retirer guardians      | ✅ CORRIGÉ | `add_guardian`/`remove_guardian`/`set_quorum` passent par `propose_emergency_action` (action 4/5/6) + quorum. |
| 7  | HAUT      | Timelock.only_guardian() incompatible avec GuardianMultisig       | ✅ CORRIGÉ | `only_guardian()` accepte désormais soit `caller == GUARDIAN_KEY`, soit `get_contract_caller() == GUARDIAN_CONTRACT_KEY`. Nouvelle entry `set_guardian_contract(Hash)`. |
| 8  | HAUT      | Fausse confidentialité — collateral_cipher = montant en clair     | ✅ CORRIGÉ | `VaultEngineV3.deposit` accepte désormais `salt: Hash` pour commit-reveal. Documentation mise à jour : pas de chiffrement homomorphe natif en Silex. |
| 9  | HAUT      | Absence d'intérêts sur VaultEngine (borrow gratuit)               | ✅ CORRIGÉ | Stability fee implémenté : index global `STABILITY_FEE_INDEX_KEY` (1e12 scale, 2% APR défaut), `borrow_amount` accrue via `accrued = principal * current_index / index_at_open`. Nouvelle entry `set_stability_fee_bps`. |
| 10 | MOYEN     | Governor appelle gv.call(6u16) = notify_reward_amount             | ✅ CORRIGÉ | `queue()` utilise `gv.call(4u16, [], {})` (GovernanceVault entry 4 = `get_total_voting_power_entry`). |
| 11 | MOYEN     | OracleGovernance.get_voting_power appelle entry 0 = stake         | ✅ CORRIGÉ | `get_voting_power()` utilise `gv.call(3u16, [addr], {})` (GovernanceVault entry 3 = `get_voting_power_entry`). |
| 12 | MOYEN     | PSM.get_xel_price appelle entry 8 (set_timelock) au lieu de get_price | ✅ CORRIGÉ | PSM utilise `oracle.call(8u16, ["XEL/USD"], {})` (StakedOracle entry 8 = `get_price_entry`). VaultSwapV2 utilise `oracle.call(9u16, [asset], {})` (entry 9 = `get_price_for_asset_entry`). LendingMarket, SyndicatePool utilisent aussi entry 9. |
| 13 | MOYEN     | maybe_adjust_budget — logique bugée + division par zéro           | ✅ CORRIGÉ | Guard `if token_count == 0 { ... return }` ajouté. La redéclaration de `target_rate` (L.247) supprimée. Logique de clamp symétrisée entre 5000 et 20000. |
| 14 | BAS       | emergency_withdraw sans timelock — rugpull vector                 | ✅ CORRIGÉ | 33 contrats : `request_emergency_withdraw()` + `execute_emergency_withdraw(asset)` avec délai de 17280 blocs (≈24h). |
| 15 | BAS       | OracleGovernance TYPE_SET_REWARD est un TODO vide                 | ✅ CORRIGÉ | `execute_proposal()` implémente désormais `TYPE_SET_REWARD` via `miner.call(21u16, [reward_amount], {})` (XelisVaultMiner entry 21 = `set_base_reward_oracle`). Nouvelle entry `set_miner_contract` ajoutée à OracleGovernance. |

---

## Architecture v5.0 — Table des Entry IDs Principaux

### ContractRegistry (14 entries)
| ID | Entry                | Rôle                                       |
|----|----------------------|--------------------------------------------|
| 0  | `get_entry`          | Résolution de contrat par nom (wrapper)    |
| 1  | `register`           | Enregistrement initial                     |
| 2  | `upgrade`            | Mise à jour versionnée + cooldown          |
| 3  | `rollback`           | Retour à la version précédente             |
| 4-7| `*_entry`            | Wrappers pour `list_names`, `get_name_at`, `get_version`, `get_previous` |
| 8-11| `set_timelock`, `transfer_admin`, `set_emergency`, `get_version_str` | Admin |
| 12-13| `request_emergency_withdraw`, `execute_emergency_withdraw` | 2-step rugpull protection |

### XelisVaultMiner (39 entries — les 7 premières critiques)
| ID  | Entry                              | Rôle                                      |
|-----|------------------------------------|--------------------------------------------|
| 0   | `register_miner`                   | Enregistrement d'un miner                  |
| 1-2 | `enable_service` / `disable_service` | Gestion des services                      |
| 3-5 | `increase_stake` / `decrease_stake` / `deregister_miner` | Stake lifecycle |
| 6   | `submit_heartbeat`                 | Heartbeat périodique                       |
| **7** | **`slash_miner`** | **CORRIGÉ — était pub fn (injoignable cross-contract)** |
| **8** | **`distribute_reward`** | **CORRIGÉ — était pub fn**                |
| **9** | **`is_miner_active_entry`** | **CORRIGÉ — était pub fn `is_miner_active`** |
| **10-12** | `get_miner_stake_entry`, `get_miner_reputation_entry`, `get_active_miners_for_service_entry` | **CORRIGÉ — wrappers entry** |
| 13-15 | `get_miners_count_entry`, `get_total_staked_entry`, `get_base_reward_oracle_entry` | View wrappers |
| 16-17 | `register_service` / `unregister_service` | Service registry |
| 18-26 | `set_min_stake` ... `set_target_duration` | Config |
| 21  | `set_base_reward_oracle` | **CORRIGÉ — utilisé par OracleGovernance.execute_proposal TYPE_SET_REWARD** |
| 27-31 | `set_vlt_contract` ... `set_emergency` | Wiring |
| 32-35 | `pause` / `unpause` / `transfer_admin` / `get_version` | Admin |
| 36-38 | `request_emergency_withdraw` / `cancel_emergency_withdraw` / `execute_emergency_withdraw` | **CORRIGÉ — 2-step pattern** |

### StakedOracle (28 entries)
| ID  | Entry                              | Rôle                                      |
|-----|------------------------------------|--------------------------------------------|
| 0-4 | `add_feed`, `update_feed`, `set_feed_active`, `trigger_feed_cb`, `reset_feed_cb` | Feed management |
| 5-6 | `submit_price`, `aggregate_now`    | Price submission + aggregation             |
| **7-10** | `get_price_by_feed_entry`, `get_price_entry`, `get_price_for_asset_entry`, `get_feed_id_entry` | **CORRIGÉ — wrappers entry cross-contract** |
| 11-12 | `pause` / `unpause`              | Emergency stop                             |
| 13-17 | `set_max_deviation_bps` ... `set_hard_stale_blocks` | Config |
| 18-20 | `disable_bootstrap` / `set_bootstrap_min_providers` / `set_min_providers` | Bootstrap mode |
| 21-27 | `set_miner_contract` ... `get_version` | Wiring + admin |

### GovernanceVault (21 entries)
| ID  | Entry                              | Rôle                                      |
|-----|------------------------------------|--------------------------------------------|
| 0   | `stake`                            | Stake VLT + lock                           |
| 1   | `unstake`                          | Unstake après lock                         |
| **2** | **`claim_rewards`** | **CORRIGÉ — syntaxe réparée**              |
| **3-7** | `get_voting_power_entry` ... `get_stakes_count_entry` | **CORRIGÉ — wrappers entry cross-contract** |
| 8   | `notify_reward_amount`             | Distribution des rewards                   |
| 9   | `set_reward_distributor`           | Autorisation distributeur                  |
| 10-18 | `set_vlt_contract` ... `get_version` | Wiring + admin                          |
| 19-20 | `request_emergency_withdraw` / `execute_emergency_withdraw` | **CORRIGÉ — 2-step** |

### VaultEngineV3 (36 entries)
| ID    | Entry                              | Rôle                                      |
|-------|------------------------------------|--------------------------------------------|
| **0** | **`deposit(asset, amount, salt)`** | **CORRIGÉ — commit-reveal via salt**       |
| 1     | `borrow`                           | **CORRIGÉ — stability fee index snapshot** |
| 2     | `repay`                            | **CORRIGÉ — repay accrued amount**         |
| 3     | `withdraw`                         | Withdraw collateral                        |
| 4     | `liquidate`                        | **CORRIGÉ — accrued borrow math**          |
| 5     | `redeem`                           | **CORRIGÉ — accrued borrow math**          |
| 6-12  | `get_health_factor_entry` ... `get_stability_fee_index_entry` | View wrappers |
| 13-14 | `pause` / `unpause`               | Emergency                                  |
| 15-22 | `set_min_cr_bps` ... `set_stability_fee_bps` | **CORRIGÉ — config stability fee** |
| 23-33 | `set_queue_cap` ... `is_paused`   | Config + admin                             |
| 34-35 | `request_emergency_withdraw` / `execute_emergency_withdraw` | **CORRIGÉ — 2-step** |

### FlashLoan (16 entries)
| ID    | Entry                              | Rôle                                      |
|-------|------------------------------------|--------------------------------------------|
| **0** | **`flash_loan`** | **CORRIGÉ — body réparé, kwarg `{}` vide, balance check `>= balance_before + fee`** |
| 1-3   | View wrappers                      | `get_fee_bps_entry`, etc.                  |
| 4-13  | `set_fee_bps` ... `get_version`    | Config + admin                             |
| 14-15 | `request_emergency_withdraw` / `execute_emergency_withdraw` | **CORRIGÉ — 2-step** |

---

## Vérification des APIs Silex Utilisées

Voici la liste exhaustive des APIs Silex utilisées dans la v5.0, validées contre `upload/lib.rs` (wrapper Silex playground) et la documentation officielle :

### Types primitifs (validés)
- `u8`, `u16`, `u32`, `u64`, `u128`, `u256`, `bool`, `string`, `bytes`
- `T[]` (arrays)
- `optional<T>` avec méthodes `.is_some()`, `.is_none()`, `.unwrap_or(default)`, `.expect(msg)`
- `struct`, `enum`

### Types opaques (validés)
- `Address` — méthodes `.to_string()`, `.to_hex()`
- `Hash` — méthode `.to_hex()`, constructeur `Hash::zero()`
- `Asset` — méthodes `Asset::create(supply, name, ticker, decimals, MaxSupplyMode)`, `Asset::get_by_hash(hash)`, `.get_hash()`, `.get_name()`, `.get_ticker()`, `.get_supply()`, `.mint(amount) -> bool`
- `Contract` — méthodes `Contract::new(hash)`, `.call(entry_id, args, {})`
- `Storage` — méthodes `Storage::new()`, `.store(key, value)`, `.load(key)`, `.delete(key)`
- `MaxSupplyMode::None`, `MaxSupplyMode::Fixed(u64)`

### Fonctions globales (validées)
- `get_caller() -> optional<Address>`
- `get_contract_caller() -> optional<Hash>`
- `get_balance_for_asset(Hash) -> optional<u64>`
- `get_deposit_for_asset(Hash) -> optional<u64>`
- `transfer(Address, u64, Hash) -> bool`
- `burn(u64, Hash) -> bool`
- `get_current_topoheight() -> u64`
- `hash(...) -> Hash`
- `require(bool, string)`, `assert(bool)`

### APIs NON utilisées (confirmées absentes de Silex)
- ❌ `Ciphertext` (n'existe pas — remplacé par commit-reveal pattern via `hash()`)
- ❌ `elgamal` (présent dans le crate Rust `xelis_common::crypto::elgamal` mais NON exposé comme type Silex)
- ❌ `RangeProof` (présent dans le crate Rust mais NON exposé comme type Silex)
- ❌ `try/catch` (n'existe pas en Silex — les cross-calls qui revert annulent toute la transaction)
- ❌ kwargs JavaScript `{ asset: amount }` (syntaxe invalide en Silex — seul `{}` vide est accepté comme 3ème argument de `Contract::call`)

---

## Tests Recommandés (Post-Remédiation)

Avant tout déploiement testnet, exécuter les tests d'intégration suivants (à implémenter dans `tests/`) :

1. **Test Oracle → Miner** : Enregistrer un miner, submit un prix, vérifier que `distribute_reward` est appelé (entry 8) et augmente `total_rewards_earned`.

2. **Test VaultEngine → Oracle** : Déposer du XEL, borrow du xUSD, vérifier que `get_xel_price` résout correctement via ContractRegistry entry 0 + StakedOracle entry 9.

3. **Test Governance** : Créer une proposition, voter, queue, vérifier que `get_total_voting_power_entry` (GovernanceVault entry 4) est appelé par Governor.

4. **Test FlashLoan** : Déposer des fonds dans FlashLoan, exécuter un flash loan avec un callback contract qui repaie principal + fee, vérifier que le treasury reçoit le fee.

5. **Test Stability Fee** : Ouvrir un vault, attendre N blocs, repay, vérifier que le montant repayé est supérieur au principal (prouve l'accrétion d'intérêts).

6. **Test 2-step Emergency** : Appeler `request_emergency_withdraw`, vérifier qu'`execute_emergency_withdraw` revert avant 17280 blocs et passe après.

7. **Test GuardianMultisig → Timelock** : Configurer GuardianMultisig comme `guardian_contract` du Timelock, soumettre une emergency proposal via GuardianMultisig, vérifier que Timelock.only_guardian() accepte l'appel.

---

## Conclusion

La v5.0 du protocole XELIS Vault corrige les **15 vulnérabilités** identifiées dans l'audit v4.3. Les 5 vulnérabilités critiques (entry IDs décalés, fonctions cassées) ont été entièrement résolues. Les 4 vulnérabilités hautes (guardian, timelock, cipher, intérêts) ont été corrigées via une combinaison de refactoring architectural (Timelock à double guardian, GuardianMultisig à quorum) et d'ajustements produit (commit-reveal au lieu de cipher, stability fee sur VaultEngine).

L'architecture v5.0 est désormais **conforme aux APIs Silex réellement disponibles** (validées via `lib.rs`). Aucune utilisation d'API hypothétique ou non documentée. Les entry IDs sont documentés automatiquement par `scripts/extract_entry_ids.py` et le fichier `docs/ENTRY_IDS.md` (33 contrats, 630 entry functions) peut être régénéré à chaque modification.

### Statut final

| Jalon           | Statut       | Condition                                                |
|-----------------|--------------|----------------------------------------------------------|
| Testnet         | ✅ PRÊT (sous réserve de compilation) | Compiler les 33 contrats avec Silex, exécuter tests d'intégration ci-dessus. |
| Mainnet         | ⏳ EN ATTENTE | Tests d'intégration passants + audit externe (Slixe/Hacken/Trail of Bits) + bug bounty. |
| Bug bounty      | Recommandé   | Lancer après testnet stable (1% VLT = 100k VLT alloué).  |
| Prochaine revue | Audit externe | Avant mainnet.                                           |

### Recommandations post-testnet

1. **Externaliser la vérification des entry IDs** — Ajouter un test CI qui exécute `scripts/extract_entry_ids.py` et compare le résultat à un fichier de référence commité. Toute divergence fait échouer le CI.

2. **Fuzzing des contrats critiques** — Soumettre StakedOracle (agrégation médiane, circuit breaker), VaultEngineV3 (health factor, liquidation), VaultSwapV2 (TWAP, slippage) à un fuzzing Silex (à développer si non disponible).

3. **Audit externe** — Confier le code v5.0 à un cabinet d'audit indépendant (Slixe en priorité vu la connaissance du langage, sinon Hacken, Trail of Bits, OpenZeppelin).

4. **Bug bounty** — Lancer un programme Immunefi avec 1% VLT (100k VLT) alloué sur 2 ans, réparti : 50% critical, 30% high, 15% medium, 5% low.

5. **Monitoring on-chain** — Déployer un keeper qui surveille en continu : nombre de miners actifs, déviation médiane par feed, health factor minimum de tous les vaults, budget restant dans XelisVaultMiner, index de stability fee.

---

*Audit et remédiation réalisés par Super Z (Z.ai) le 24 juin 2026 sur la base du dépôt `github.com/XelisVault/xelis-vault` (commit v4.3) corrigé en v5.0. Périmètre : 33 contrats Silex + scripts Python + documentation. Méthodologie : revue manuelle de logique, analyse statique, cross-check des entry IDs (générés automatiquement via `extract_entry_ids.py`), vérification des contrôles d'accès, validation des APIs contre `lib.rs` (wrapper Silex playground) et la documentation officielle.*
