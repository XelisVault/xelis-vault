# UPGRADE v12.1 — Guide de déploiement précis (testnet)

Ce document décrit **exactement** comment remplacer les contrats concernés sur
le testnet pour la version **v12.1** (auto-enregistrement airdrop + récompenses
par bloc + mixer v3 + confidentialité + correctifs de migration). À suivre
dans l'ordre, phase par phase. Toutes les commandes sont idempotentes et
reprenables — y compris après un **crash** en pleine migration (le script
reprend depuis le curseur ON-CHAIN).

> **v12.1 (correctifs de la review communautaire)** — l'ordre des phases a
> changé : la migration se fait AVANT le registry cutover, et le nouveau
> tracker démarre EN PAUSE (l'unpause est la dernière étape on-chain). Voir
> §0bis.

---

## 0. Ce qui change en v12 / v12.1 (résumé)

| Contrat | Version | Changement majeur |
|---|---|---|
| **AirdropTracker** | **v12.1** | `pub fn record_activity_cross` (chunk **77**) : les contrats autorisés enregistrent les points **automatiquement**. `import_user_state` (chunk **78**, signature étendue) + `finalize_migration` (chunk **79**, curseur interne) pour migrer l'état existant. **Démarre EN PAUSE** (constructeur), l'import n'est **plus plafonné** par le cap manuel, `set_mig_cursor` (**81**) / `get_mig_cursor` (**82**) pour la reprise crash-safe. |
| **XelisVaultMiner** | v12.1 | **Récompenses par bloc** (settle paresseux) : ~50 VLT/jour par mineur de 1000 VLT au lieu de ~0,25. Entrées ajoutées : `claim_rewards` (**91**), `set_airdrop_tracker` (**92**). Gains confidentiels par **Ciphertext** (clé `ect_<addr>`). Tous les pub fn mutants retournent 0 (bug VM). |
| **StakedOracle** | v12.0 | 1 point MINING par soumission de prix acceptée. `set_airdrop_tracker` (**60** — ⚠️ la doc v12 disait 49 par erreur, le chunk réel est 60). |
| **VaultChat** | **v12.1** | Points CHAT et RELAYER auto-enregistrés. **Correctif** : les points RELAYER (10/anchor) ne sont attribués qu'APRÈS la porte qualité (≥ 5 messages, ≥ 2 senders, cap quotidien) — avant, un spammeur pouvait farmer 500 pts/jour. |
| **Governor / GovernanceVault** | v12.0 | Points GOV (vote 50, proposal 500, stake 5). |
| **PSM / VaultSwapV2 / SavingsRate / VaultEngineV3** | v12.0 | Points LIQUIDITY (10 pts par XEL fourni) auto-enregistrés. |
| **PrivacyMixer** | **v3** | **Tornado-style** : dénominations fixes (1/10/100), nullifier atomique, **zéro montant stocké**, aucun intermédiaire. |

**Compatibilité des chunks** : toutes les fonctions existantes gardent leur
position (les nouveaux chunks sont APPEND en fin de fichier). Le CLI, le
keeper et les appels inter-contrats existants continuent de fonctionner sans
changement de leur côté.

## 0bis. Correctifs v12.1 (review communautaire — tous intégrés)

| # | Problème trouvé | Correctif |
|---|---|---|
| 1 | `upgrade_v12.py` : `SyntaxError` (`BYTECODE_DIR` utilisé avant sa déclaration `global`) | corrigé — le script s'exécute désormais (vérifié `py_compile`) |
| 2 | la migration échouait sur les utilisateurs au-dessus du cap manuel (50 000 pts) | `import_user_state` n'est plus plafonné par `MANUAL_CAP` (borne absolue 10¹² en garde-fou) |
| 3 | le nouveau tracker démarrait actif, le cutover avait lieu AVANT la migration | le tracker **démarre en pause** ; ordre : **A → C → D (migration) → B (cutover) → U (unpause, dernière étape on-chain) → E** |
| 4 | état utilisateur incompletément migré (qualified écrasé, last_active_day réinventé, structs illisibles sautées) ; reprise crash uniquement locale | la signature d'import préserve `last_active_day` + `qualified` ; structs illisibles → défauts sûrs ; **curseur de migration ON-CHAIN** (`mig`, chunks 81/82) ; `finalize_migration` à curseur interne + flag `migd` (jamais de double comptage, jamais de remise à zéro) |
| 5 | aucune vérification que l'ancien tracker n'a pas bougé pendant la migration | la phase D re-lit l'état ancien (uc/tp/ct_*) et **échoue fermé** (abort, pas de cutover) si quoi que ce soit a changé |
| 6 | crash après un unpause on-chain réussi → risque de double unpause | la phase U lit la clé on-chain `pz` — si le tracker est déjà actif, l'étape est sautée |
| 7 | mapping VaultSwap incorrect : le script n'upgradait que le nom « VaultSwap » et jamais l'artefact `VaultSwapV2` | la phase B upgrade **les deux noms** du registre (« VaultSwap » ET l'alias « VaultSwapV2 ») |
| 8 | l'appel CLI `anchor_messages` passait 3 arguments alors que le chunk compilé 11 en exige **4** (il manquait `sender_count`) | `chat_anchor(root, count, senders, msg_type)` dans `cli_backend.py` + l'UI `xvault.py` demande le nombre de senders (le relayer_server est réparé par la même correction) |
| 9 | VaultChat attribuait les points airdrop relayer AVANT la validation qualité | l'appel `record_activity_cross` est déplacé après la porte qualité (voir tableau §0) |
| 10 | chunk obsolète `set_airdrop_tracker` (49) dans cette doc | corrigé partout → **60** |

Validation : rebuild **byte-for-byte PASS** du compilateur (canonique
xelis-vm v1.3.0) sur AirdropTracker et VaultChat, layout append-only vérifié
mécaniquement, tests crash-resume migration/cutover **9/9 PASS**
(`tests/test_upgrade_v12_resume.py`), `git diff --check` PASS.

---

## 1. Pré-requis

- Le daemon + wallet admin en ligne (RPC 18081 / 18082 comme d'habitude),
  solde XEL suffisant (~1 XEL pour les fees de la centaine de tx).
- Les bytecode v12.1 sont **déjà compilés et commités** dans `build/`
  (`deploy_<Name>.hex`, régénérés par `scripts/compile_all.py`, layout
  append-only vérifié). Pour recompiler soi-même :

  ```bash
  # le toolchain (une fois) : wrapper Rust autour des crates officielles
  # xelis-vm v1.3.0 (silex-lexer/parser/compiler + build_environment).
  git clone --branch v1.3.0 https://github.com/xelis-project/xelis-vm
  git clone https://github.com/xelis-project/xelis-blockchain
  # puis builder xelis_compile_tool (voir build/README.md) et :
  export XELIS_COMPILE_TOOL=/path/to/xelis_compile_tool
  python3 scripts/compile_all.py          # 51 contrats -> build/
  python3 scripts/compile_all.py AirdropTracker VaultChat   # sélectif
  ```

  ⚠️ Le stderr imprime la **chunk map** — vérifier que `record_activity_cross`
  est bien le chunk **77** sur AirdropTracker, `claim_rewards` le **91** sur
  XelisVaultMiner et `set_mig_cursor` le **81**. Si votre tool imprime un autre
  numéro, ajuster `CH` dans `deploy/upgrade_v12.py`.

- Regénérer la map complète après compilation (optionnel mais recommandé) :
  ```bash
  python3 scripts/compile_all.py   # met à jour docs/entry_chunk_ids.json
  ```

## 2. ORDRE DES PHASES (v12.1 — CRITIQUE)

```
A (déploiement, tracker démarre EN PAUSE)
  -> C (configuration des nouveaux storages — marche pendant la pause)
  -> D (migration de l'état airdrop, tracker pas encore dans le registre,
        reprise crash-safe, échoue fermé si l'ancien tracker a bougé)
  -> B (registry cutover — les deux noms VaultSwap/VaultSwapV2)
  -> U (unpause — DERNIÈRE étape on-chain de la migration)
  -> E (fichiers runtime du repo)
```

Tout-en-un (recommandé — fenêtre minimale entre cutover et unpause) :

```bash
export TREASURY_ADDRESS=xet:<admin>
python3 deploy/upgrade_v12.py --phase all
```

Ne JAMAIS lancer `--phase b` avant que la phase D soit complète : le cutover
pointe les enregistreurs vers le nouveau tracker — il doit déjà contenir
l'état migré. Entre B et U, les enregistreurs résolvent un tracker en pause :
leurs appels `record_activity_cross` **no-op silencieux** (aucun revert,
aucun point perdu au-delà de cette courte fenêtre).

## 3. Déployer (phase A)

```bash
python3 deploy/upgrade_v12.py --phase a     # déploie les 11 contrats v12.1
```

Le constructeur du nouveau AirdropTracker v12.1 stocke **pz=true** (démarre en
pause). Le script le vérifie et, si un ancien artefact non-pausé était déployé,
le met en pause immédiatement (chunk 73).

## 4. Configurer (phase C)

```bash
export TREASURY_ADDRESS=xet:<admin>          # trésorerie temporaire = admin
python3 deploy/upgrade_v12.py --phase c
```

Cette phase configure, sur les **nouveaux** contrats (storage vierge) — tous
les setters sont admin-only et **fonctionnent pendant la pause** :

1. **AirdropTracker** : `set_authorized_recorder` (chunk 68) pour les
   **10 contrats enregistreurs** — c'est CELA qui active l'auto-enregistrement.
2. `set_airdrop_tracker` sur XelisVaultMiner (chunk 92) et StakedOracle
   (chunk **60**) — les points MINING coulent dès la prochaine soumission.
3. XelisVaultMiner : VLT contract/asset, delegation, treasury, registry,
   `register_service(oracle)`, heartbeat 900/4000.
4. StakedOracle : miner contract, registry, feed XEL/USD.
5. VaultChat : VLT asset, treasury, miner contract.
6. PSM / VaultSwap / VE3 / Savings : oracles + xUSD + registry + treasury,
   et xUSD `set_minter`/`set_burner` pour les nouveaux hash PSM/VE3/VS.
7. VLTToken : `set_minter(nouveau XelisVaultMiner)`.
8. PrivacyMixer v3 : registry + treasury (frais à 0 par défaut).

## 5. Migrer l'état airdrop (phase D)

```bash
python3 deploy/upgrade_v12.py --phase d --old-tracker ef896baa1c88d64462500b48c8a6d0fb47b92b46718d1949c79d8d0268769dca
```

Lit chaque `user_<addr>` sur l'ANCIEN tracker (encore lisible via RPC) et
l'importe dans le nouveau via `import_user_state` — **points + days_active +
last_active_day + flag qualified + adresse mainnet préservés** ; les structs
illisibles sont importées avec des défauts sûrs (enregistré, zéro point) au
lieu d'être sautées. **Aucun cap manuel** ne s'applique (les gros
contributeurs migrés sans échec). Puis `finalize_migration` recalcule `tp`,
`ct_1..7` par lots de 200 — **curseur interne on-chain + flag de complétion** :
re-lancer ne double-compte jamais et ne remet jamais les totaux à zéro.

**Crash-safe** : la relecture du curseur on-chain `mig` (mis à jour tous les
20 imports par `set_mig_cursor`) détermine où reprendre ; les ré-imports sont
des écrasements idempotents. Un crash **après** un import mais **avant** la
sauvegarde locale re-fait au plus 19 imports — sans jamais dupliquer un user.

**Échec fermé** : à la fin de la phase D, l'état de l'ancien tracker
(uc/tp/ct_*) est relu et comparé à l'instantané pris au début. Si la moindre
activité a été enregistrée sur l'ancien pendant la migration, le script
**abort** avec `FAIL CLOSED` — ne PAS lancer la phase B ; re-lancer la phase D
(les imports idempotents mettront l'état à jour) puis B+U.

Vérification :
```bash
# nouveaux uc / tp doivent égaler l'ancien (43 users / 316 220 points à date)
python3 - << 'EOF'
import json, urllib.request
def rpc(m, p):
    req = urllib.request.Request("https://testnet-node.xelis.io/json_rpc",
        data=json.dumps({"id":1,"jsonrpc":"2.0","method":m,"params":p}).encode(),
        headers={"Content-Type":"application/json","User-Agent":"check/1.0"})
    return json.loads(urllib.request.urlopen(req).read())
new = "<hash du nouveau tracker>"  # dans docs/upgrade_v12_state.json
for k in ("uc","tp","qc","migd"):
    r = rpc("get_contract_data", {"contract": new,
          "key": {"type":"primitive","value":{"type":"string","value":k}},
          "topoheight":"latest"})
    print(k, r.get("result",{}).get("data"))
EOF
# migd doit valoir true et tp l'ancien total.
```

## 6. Cutover du registre (phase B — APRÈS la migration)

```bash
python3 deploy/upgrade_v12.py --phase b
```

La phase B utilise l'entrée `upgrade` (chunk 4) du ContractRegistry et met à
jour **chaque nom** — pour le swap, **les deux** : `VaultSwap` ET l'alias
`VaultSwapV2` (tous deux présents on-chain depuis le déploiement v12R ; ne pas
mettre à jour les deux laisserait l'alias pointer sur l'ancien contrat, et
l'enregistrement airdrop des swaps resterait mort). Les anciens hash restent
accessibles en `prev_<Name>` (rollback possible via l'entrée 5). Le cooldown
de 720 blocs entre upgrades s'applique **par nom** — en cas de `cdactive`,
attendre ~1h et relancer : le script reprend où il s'était arrêté.

## 7. Réactiver le tracker (phase U — DERNIÈRE étape on-chain)

```bash
python3 deploy/upgrade_v12.py --phase u
```

Lit la clé on-chain `pz` : si le tracker est déjà actif (crash juste après un
unpause on-chain réussi), l'étape est **sautée** — jamais de double unpause.
Sinon, `unpause` (chunk 74) puis vérification que `pz=false`.

## 8. Finaliser (phase E + manuel)

```bash
python3 deploy/upgrade_v12.py --phase e     # met à jour network/testnet.json
```

Puis les étapes **manuelles** (impossibles à faire à la place des users) :

1. **Mineurs : se ré-enregistrer** (nouveau contrat = storage vierge) :
   `xvault > Miner tools > Register as miner` — le stake de 1000 VLT doit être
   re-déposé. Les 6 mineurs actuels : les providers p1/p2/p3 (admin) +
   les éventuels mineurs communautaires. Pour récupérer l'ancien stake :
   `deregister_miner` sur l'ANCIEN hash XelisVaultMiner (il reste exécutable).
2. **Relancer le keeper oracle** : `xvault-miner > p > start keeper`
   (ou `nohup python3 -u scripts/oracle_keeper3.py &`). Dès le premier cycle,
   le flux complet tourne : submit → aggregate → distribute_reward →
   settle par bloc → mint VLT → point airdrop MINING.
3. **Relancer l'indexer airdrop** (points de minage PoW uniquement, tout le
   reste est désormais auto-enregistré) :
   `nohup python3 -u scripts/airdrop_offchain_indexer.py --resume --daemon &`.
   L'injecteur `airdrop_onchain_injector.py` peut être **arrêté** (son rôle
   est repris par les contrats) sauf pour les points PoW si l'on veut les
   voir on-chain — dans ce cas ne l'arrêtez pas.
4. **Lancer le Doctor** : `xvault > Doctor — diagnose & fix my setup` —
   les sections [6/8] doivent être toutes OK (tracker + recorders autorisés).

## 9. Vérifications finales (checklist)

- [ ] `record_activity_cross` : soumettre un prix avec un provider →
      `user_<addr>` du tracker gagne +1 point MINING (chunk d'event
      `AirdropAuto` visible dans les logs du tx).
- [ ] Récompenses : après ~1 h de keeper, `dist` du nouveau XelisVaultMiner
      augmente de plusieurs VLT (vs 4,86 VLT en 2 semaines avant la v12).
- [ ] `ect_<addr>` (Ciphertext) présent sur le miner — déchiffrable par le
      wallet du mineur (`decrypt_ciphertext`).
- [ ] **Anchor de chat** : `xvault > Chat > Anchor messages` demande
      désormais le **nombre de senders uniques** (4 paramètres on-chain) —
      l'anchor ne rapporte des points RELAYER que si ≥ 5 messages ET
      ≥ 2 senders.
- [ ] Mixer v3 : dépôt 1 XEL → note `n_<asset>_1_<blake3(secret)>` ;
      withdraw vers une adresse fraîche → note consommée.
- [ ] Doctor : 8/8 sections vertes.

## 10. Rollback (si nécessaire)

Chaque nom est récupérable via le ContractRegistry :
```
ContractRegistry.rollback(entry 5) : cur_<Name> -> prev_<Name>
```
(avec son propre cooldown de 720 blocs). L'état repart de l'ancien contrat —
les points ajoutés au nouveau tracker après la migration seraient à
ré-importer. ⚠️ Upgrader de nouveau vers le tracker v12.1 après un rollback
re-démarre le flow A→C→D→B→U (le tracker redémarre en pause).

---

## Annexe A — Grille des points (v12, auto-enregistrée on-chain)

| Action | Contrat | Catégorie | Points | action_id |
|---|---|---|---|---|
| Prix accepté | StakedOracle.submit_price | MINING | 1 | 200 |
| Heartbeat | XelisVaultMiner.submit_heartbeat | MINING | 50 | 101 |
| Soumission valide (oracle/chat) | XelisVaultMiner.distribute_reward | MINING | 1 | 100 |
| Message (direct/groupe/éphémère) | VaultChat.store_* / send_direct | CHAT | 1 | 302-305 |
| Création de groupe | VaultChat.create_group | CHAT | 100 | 300 |
| Anchor de messages (≥5 msgs, ≥2 senders) | VaultChat.anchor_messages | RELAYER | 10 | 301 |
| Enregistrement relayer | VaultChat.register_as_relayer | RELAYER | 50 | 306 |
| Bond relayer | VaultChat.stake_relayer_bond | RELAYER | 5 | 307 |
| Fee relayer | VaultChat.set_relayer_fee | RELAYER | 5 | 308 |
| Vote | Governor.vote | GOVERNANCE | 50 | 501 |
| Proposition | Governor.propose | GOVERNANCE | 500 | 500 |
| Stake governance | GovernanceVault.stake | GOVERNANCE | 5 | 502 |
| Mint xUSD | PSM.mint | LIQUIDITY | 10/XEL | 400 |
| Liquidité AMM | VaultSwapV2.add_liquidity | LIQUIDITY | 10/XEL | 401 |
| Dépôt savings | SavingsRate.deposit | LIQUIDITY | 10/unit | 402 |
| Collatéral vault | VaultEngineV3.deposit | LIQUIDITY | 10/XEL | 403 |
| Dépôt mixer | PrivacyMixer.deposit | LIQUIDITY | 10/unit | 600 |

Caps quotidiennes (appliquées par le tracker) : MINING 1000/j, RELAYER 500/j,
CHAT 100/j. Le minage **PoW** (blocs) reste compté par l'indexer off-chain
(1 pt/bloc) — un contrat ne peut pas observer les headers de blocs.

## Annexe B — Chunks v12/v12.1 (VÉRIFIÉS par compilation réelle)

Tous les contrats compilent 51/51 (voir `build/chunkmap_<Name>.txt` et
`docs/entry_chunk_ids.json` régénéré). Tous les chunks existants gardent leur
position (append-only vérifié mécaniquement).

| Contrat | Fonction | Chunk | Kind |
|---|---|---|---|
| AirdropTracker | record_activity_cross (pub fn) | **77** | All |
| AirdropTracker | import_user_state (entry, 12 params v12.1) | 78 | Entry |
| AirdropTracker | finalize_migration (entry, curseur interne v12.1) | 79 | Entry |
| AirdropTracker | get_record_authority (pub fn) | 80 | All |
| AirdropTracker | **set_mig_cursor (entry, v12.1)** | **81** | Entry |
| AirdropTracker | **get_mig_cursor (pub fn, v12.1)** | **82** | All |
| XelisVaultMiner | add_confidential_earnings (fn) | 88 | Internal |
| XelisVaultMiner | settle_accrued_rewards (fn) | 89 | Internal |
| XelisVaultMiner | **settle_rewards_cross (pub fn)** | **90** | **All** |
| XelisVaultMiner | claim_rewards (entry) | 91 | Entry |
| XelisVaultMiner | set_airdrop_tracker (entry) | 92 | Entry |
| XelisVaultMiner | get_last_settle / get_airdrop_tracker | 93 / 94 | All |
| StakedOracle | set_airdrop_tracker (entry) | **60** | Entry |
| StakedOracle | get_airdrop_tracker (pub fn) | 61 | All |
| VaultChat | set_airdrop_tracker (entry) | 135 | Entry |
| Governor | set_airdrop_tracker (entry) | 23 | Entry |
| GovernanceVault | set_airdrop_tracker (entry) | 37 | Entry |
| PSM | set_airdrop_tracker (entry) | 38 | Entry |
| VaultSwapV2 | set_airdrop_tracker (entry) | 58 | Entry |
| SavingsRate | set_airdrop_tracker (entry) | 33 | Entry |
| VaultEngineV3 | set_airdrop_tracker (entry) | 76 | Entry |
| PrivacyMixer v3 | deposit (entry) | **7** | Entry |
| PrivacyMixer v3 | withdraw (entry) | **8** | Entry |
| PrivacyMixer v3 | get_denominations (pub fn) | 14 | All |
| PrivacyMixer v3 | set_airdrop_tracker (entry) | 29 | Entry |

⚠️ **PrivacyMixer v3** : deposit/withdraw passent de 6/7 à **7/8** (le helper
`class_of` est ajouté avant deposit). Le CLI est déjà mis à jour
(`scripts/cli_backend.py` CHUNKS).

Le settle des récompenses est déclenché par **appels inter-contrats par
numéro de chunk** (pas de contrainte d'ordre de déclaration en Silex) :
`StakedOracle.reward_miner` et `VaultChat.anchor_messages` appellent
`miner.settle_rewards_cross(90)` juste avant `distribute_reward(23)`.

## Annexe C — Tests crash-resume (nouveaux v12.1)

`tests/test_upgrade_v12_resume.py` (protocole entièrement mocké, 9 tests) :

1. migration complète : cap bypassé (user 60 000 pts), struct corrompue →
   défauts sûrs, `last_active_day`/`qualified` préservés, totaux recréés ;
2. le tracker est migré **pendant la pause** ;
3. crash au milieu des imports → reprise par le curseur ON-CHAIN, aucun user
   dupliqué ;
4. crash après mise à jour du curseur → les users couverts ne sont PAS
   ré-importés ;
5. `finalize_migration` re-lancé après complétion = no-op strict (aucun
   double comptage, totaux intacts) ;
6. FAIL CLOSED si l'ancien tracker a changé pendant la migration ;
7. unpause jamais doublé après un crash post-unpause on-chain ;
8. cutover des **deux** alias VaultSwap/VaultSwapV2 + idempotence ;
9. l'ordre des phases place D avant B avant U.

```bash
python3 tests/test_upgrade_v12_resume.py   # 9/9 PASS
```
