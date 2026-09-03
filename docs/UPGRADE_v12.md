# UPGRADE v12 — Guide de déploiement précis (testnet)

Ce document décrit **exactement** comment remplacer les contrats concernés sur
le testnet pour la version **v12** (auto-enregistrement airdrop + récompenses
par bloc + mixer v3 + confidentialité). À suivre dans l'ordre, phase par
phase. Toutes les commandes sont idempotentes et reprenables.

---

## 0. Ce qui change en v12 (résumé)

| Contrat | Version | Changement majeur |
|---|---|---|
| **AirdropTracker** | v12.0 | `pub fn record_activity_cross` (chunk **77**) : les contrats autorisés enregistrent les points **automatiquement**. `import_user_state` (chunk **78**) + `finalize_migration` (chunk **79**) pour migrer l'état existant. |
| **XelisVaultMiner** | v12.1 | **Récompenses par bloc** (settle paresseux) : ~50 VLT/jour par mineur de 1000 VLT au lieu de ~0,25. Entrées ajoutées : `claim_rewards` (**91**), `set_airdrop_tracker` (**92**). Gains confidentiels par **Ciphertext** (clé `ect_<addr>`). Tous les pub fn mutants retournent 0 (bug VM). |
| **StakedOracle** | v12.0 | 1 point MINING par soumission de prix acceptée. `set_airdrop_tracker` (**49**). |
| **VaultChat** | v12.0 | Points CHAT (message 1, groupe 100) et RELAYER (anchor 10, register 50, bond 5, fee 5) auto-enregistrés. |
| **Governor / GovernanceVault** | v12.0 | Points GOV (vote 50, proposal 500, stake 5). |
| **PSM / VaultSwapV2 / SavingsRate / VaultEngineV3** | v12.0 | Points LIQUIDITY (10 pts par XEL fourni) auto-enregistrés. |
| **PrivacyMixer** | **v3** | **Tornado-style** : dénominations fixes (1/10/100), nullifier atomique, **zéro montant stocké**, aucun intermédiaire. |

**Compatibilité des chunks** : toutes les fonctions existantes gardent leur
position (les nouveaux chunks sont APPEND en fin de fichier). Le CLI, le
keeper et les appels inter-contrats existants continuent de fonctionner sans
changement de leur côté.

---

## 1. Pré-requis

- Le daemon + wallet admin en ligne (RPC 18081 / 18082 comme d'habitude),
  solde XEL suffisant (~1 XEL pour les fees de la centaine de tx).
- **Compiler les 11 contrats v12** avec le compile tool
  (`xelis_compile_tool`) — sortie dans `/tmp/deploy_<Name>.hex` :

  ```bash
  cd ~/opencode/xelis-compile-tool   # votre tool habituel
  for C in AirdropTracker XelisVaultMiner StakedOracle VaultChat Governor \
           GovernanceVault PSM VaultSwapV2 SavingsRate VaultEngineV3 PrivacyMixer; do
    ./target/release/xelis_compile_tool \
        /path/to/xelis-vault/contracts/<categorie>/$C.slx /tmp/deploy_$C.hex
  done
  # catégories: airdir=airdrop, miner, oracle, chat, governance, governance,
  # amm, amm, savings, vault, privacy
  ```

  ⚠️ Le log stderr imprime la **chunk map** — vérifier que `record_activity_cross`
  est bien le chunk **77** sur AirdropTracker et `claim_rewards` le chunk **91**
  sur XelisVaultMiner (l'ordre d'ajout du repo le garantit). Si votre tool
  imprime un autre numéro, ajuster `CH` dans `deploy/upgrade_v12.py`.

- Regénérer la map complète après compilation (optionnel mais recommandé) :
  ```bash
  python3 scripts/extract_entry_ids.py   # met à jour docs/entry_chunk_ids.json
  ```

## 2. Déployer (phases A → B)

Depuis la racine du repo, avec le wallet admin en ligne :

```bash
python3 deploy/upgrade_v12.py --phase a     # déploie les 11 nouveaux contrats
python3 deploy/upgrade_v12.py --phase b     # registry UPGRADE (entry 4) de chaque nom
```

La phase B utilise l'entrée `upgrade` (chunk 4) du ContractRegistry : les
anciens hash restent accessibles en `prev_<Name>` (rollback possible via
l'entrée 5). Le cooldown de 720 blocs entre upgrades s'applique **par nom** —
en cas de `cdactive` (cooldown), attendre ~1h et relancer : le script reprend
où il s'était arrêté.

## 3. Configurer (phase C)

```bash
export TREASURY_ADDRESS=xet:<admin>          # trésorerie temporaire = admin
python3 deploy/upgrade_v12.py --phase c
```

Cette phase configure, sur les **nouveaux** contrats (storage vierge) :

1. **AirdropTracker** : `set_authorized_recorder` (chunk 68) pour les
   **10 contrats enregistreurs** — c'est CELA qui active l'auto-enregistrement.
2. `set_airdrop_tracker` sur XelisVaultMiner (chunk 92) et StakedOracle
   (chunk 49) — les points MINING coulent dès la prochaine soumission.
3. XelisVaultMiner : VLT contract/asset, delegation, treasury, registry,
   `register_service(oracle)`, heartbeat 900/4000.
4. StakedOracle : miner contract, registry, feed XEL/USD.
5. VaultChat : VLT asset, treasury, miner contract.
6. PSM / VaultSwap / VE3 / Savings : oracles + xUSD + registry + treasury,
   et xUSD `set_minter`/`set_burner` pour les nouveaux hash PSM/VE3/VS.
7. VLTToken : `set_minter(nouveau XelisVaultMiner)`.
8. PrivacyMixer v3 : registry + treasury (frais à 0 par défaut).

## 4. Migrer l'état airdrop (phase D)

```bash
python3 deploy/upgrade_v12.py --phase d --old-tracker ef896baa1c88d64462500b48c8a6d0fb47b92b46718d1949c79d8d0268769dca
```

Lit chaque `user_<addr>` sur l'ANCIEN tracker (encore lisible via RPC) et
l'importe dans le nouveau via `import_user_state` — **points + days_active +
adresse mainnet préservés** (c'est le correctif du défaut structurel
`days_active=1` des injections manuelles). Puis `finalize_migration` par
pages de 200 users recalcule `tp`, `ct_1..7`.

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
for k in ("uc","tp","qc"):
    r = rpc("get_contract_data", {"contract": new,
          "key": {"type":"primitive","value":{"type":"string","value":k}},
          "topoheight":"latest"})
    print(k, r.get("result",{}).get("data"))
EOF
```

## 5. Finaliser (phase E + manuel)

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

## 6. Vérifications finales (checklist)

- [ ] `record_activity_cross` : soumettre un prix avec un provider →
      `user_<addr>` du tracker gagne +1 point MINING (chunk d'event
      `AirdropAuto` visible dans les logs du tx).
- [ ] Récompenses : après ~1 h de keeper, `dist` du nouveau XelisVaultMiner
      augmente de plusieurs VLT (vs 4,86 VLT en 2 semaines avant la v12).
- [ ] `ect_<addr>` (Ciphertext) présent sur le miner — déchiffrable par le
      wallet du mineur (`decrypt_ciphertext`).
- [ ] Mixer v3 : dépôt 1 XEL → note `n_<asset>_1_<blake3(secret)>` ;
      withdraw vers une adresse fraîche → note consommée.
- [ ] Doctor : 8/8 sections vertes.

## 7. Rollback (si nécessaire)

Chaque nom est récupérable via le ContractRegistry :
```
ContractRegistry.rollback(entry 5) : cur_<Name> -> prev_<Name>
```
(avec son propre cooldown de 720 blocs). L'état repart de l'ancien contrat —
les points ajoutés au nouveau tracker après la migration seraient à
ré-importer.

---

## Annexe A — Grille des points (v12, auto-enregistrée on-chain)

| Action | Contrat | Catégorie | Points | action_id |
|---|---|---|---|---|
| Prix accepté | StakedOracle.submit_price | MINING | 1 | 200 |
| Heartbeat | XelisVaultMiner.submit_heartbeat | MINING | 50 | 101 |
| Soumission valide (oracle/chat) | XelisVaultMiner.distribute_reward | MINING | 1 | 100 |
| Message (direct/groupe/éphémère) | VaultChat.store_* / send_direct | CHAT | 1 | 302-305 |
| Création de groupe | VaultChat.create_group | CHAT | 100 | 300 |
| Anchor de messages | VaultChat.anchor_messages | RELAYER | 10 | 301 |
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

## Annexe B — Nouveaux chunks v12 (VÉRIFIÉS par compilation réelle)

Tous les contrats compilent 51/51 (voir `build/chunkmap_<Name>.txt` et
`docs/entry_chunk_ids.json` régénéré). Tous les chunks existants gardent leur
position (append-only vérifié mécaniquement).

| Contrat | Fonction | Chunk | Kind |
|---|---|---|---|
| AirdropTracker | record_activity_cross (pub fn) | **77** | All |
| AirdropTracker | import_user_state (entry) | 78 | Entry |
| AirdropTracker | finalize_migration (entry) | 79 | Entry |
| AirdropTracker | get_record_authority (pub fn) | 80 | All |
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
