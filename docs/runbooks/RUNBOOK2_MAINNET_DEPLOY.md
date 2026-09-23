# RUNBOOK 2 — Déploiement MAINNET parfait (zéro perte de fonds)

> Code validé sur : **devnet local (simulateur)** + **testnet PUBLIC officiel**
> (miner réel produisant des blocs acceptés par le réseau, fenêtre de
> validation rejouée en conditions réelles) — cf.
> `RUNBOOK1_TESTNET_INTERACTIONS.md` pour toutes les commandes détaillées.
> Les hash d'exécution ci-dessous sont ceux du testnet public du 23/09/2026 ;
> sur mainnet, **tous les hash seront différents** (adresses, deploys, TX).
>
> ⚠️ Sur mainnet, TOUTES les commandes de ce runbook doivent être rejouées une
> par une en vérifiant chaque confirmation. Le comportement est validé sur le
> testnet public ; il reste à surveiller contre l'explorateur mainnet officiel
> (`https://explorer.xelis.io`).

---

## A. Faits réseau MAINNET (vérifiés dans le code v1.25.0)

| Paramètre | Mainnet | Testnet public |
|---|---|---|
| Genesis | **fixe mainnet** | fixe testnet (même préfixe `xet:`) |
| Préfixe d'adresse | `xet:` | `xet:` |
| Smart Contracts (V3) | height **3 282 150** (13/12/2025) ✅ actif | height 15 |
| V4→V7 | actifs (dernier fork majeur à height ~6 909 122) | V6 actif |
| Block time cible | **5 s** | ~11 s mesuré (average_block_time) |
| Difficulté minimum | **20 KH/s** | 10K (difficulté actuelle) |
| Récompense de minage | fixe par réseau (testnet : ~43,42 M atomic/bloc) | ~43,42 M atomic/bloc |
| Seed node | `seeds.xelis.io:2125` | `74.208.251.149:2125` (IP directe) |
| Explorateur | `https://explorer.xelis.io` | `https://testnet-explorer.xelis.io` |
| Hauteur (23/09/2026) | ~7 000 000+ (fork V7 passé) | 379 860 |

Conséquences :
- **Les Smart Contracts sont déjà actifs sur mainnet** (height actuelle ≫ forks).
- La fenêtre de validation minimale = **720 topos × 5 s = ~1 h** sur mainnet
  (sur testnet public : ~90 min à ~11 s/bloc).
- Palier de difficulté mainnet = 20 KH/s → hashrate CPU uniquement insuffisant
  ; prévoir d'utiliser les nœuds/pools officiels ou un GPU/ASIC pour miner.
  (Les tests de flux ne nécessitent PAS de miner : le réseau mainnet a déjà
  des mineurs.)

Verrous de sécurité réseau (à vérifier avant tout) :
```
1. Loin de tout : vérifier que le wallet affiche bien network=Mainnet (jamais devnet)
   → un wallet créé sur devnet/testnet est REFUSÉ sur mainnet
     ("Network mismatch for this wallet storage (stored: Devnet)!").
2. Vérifier la hauteur du nœud : get_info.network == "mainnet", pas de fork.
3. Ne JAMAIS déployer les contrats sur le mainnet avec un wallet devnet/testnet !
```

---

## B. Préparation (UNE SEULE FOIS)

### B1. Lancer le daemon mainnet (synchro complète, sans fast sync)

> **Fast sync : à n'utiliser QUE sur le testnet avec le seed officiel.**
> Sur mainnet, préférer la synchro **complète** (vérification de tout
> l'historique) — le fast sync ne vérifie pas l'historique complet
> (« Use only with trusted peers »). Si la synchro complète est trop lente,
> vous pouvez lancer en `--allow-boost-sync` (requêtes parallèles, vérifie
> toujours les blocs) — mesuré ~22,8 blocs/s sur testnet via seed IP.

```bash
# Synchro complète recommandée :
./bin/xelis_daemon --network=mainnet \
  --dir-path=./data/mainnet/ \
  --rpc-bind-address=127.0.0.1:8080 \
  --disable-interactive-mode --disable-ascii-art \
  --disable-file-logging --disable-log-color \
  >> ./logs/daemon-mainnet.log 2>&1 &
#   Variante boost sync (plus rapide, blocs vérifiés) :
#     ajouter --allow-boost-sync --max-chain-response-size 65535

# Vérifier que la chaîne est bien mainnet et synchronisée :
curl -s -X POST http://127.0.0.1:8080/json_rpc \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"get_info"}'
#   -> network: mainnet ; height ≈ hauteur officielle (explorer.xelis.io)
#   -> stable_topoheight proche de topoheight (synchro OK)
```

> DNS : sur mainnet, si les noms d'hôte ne résolvent pas depuis votre machine,
> utiliser les IP des seeds (`dig seeds.xelis.io` donne l'IP) ou
> `curl --resolve node.xelis.io:443:<IP> …`.

### B2. Créer des wallets MAINNET DÉDIÉS (jamais réutilisés)

```bash
# Admin (déploie + set) :
python3 scripts/drive_wallet_create.py wallets/wallet_mainnet_admin \
  --password '<TRES_FORT>' --name admin --network mainnet

# User (propose/migre/trade) — même clé que l'admin si on veut le même compte,
# sinon un second compte avec ses propres fonds :
python3 scripts/drive_wallet_create.py wallets/wallet_mainnet_user \
  --password '<TRES_FORT>' --name user --network mainnet

# NOTER LES ADRESSES (ex. rôle / adresse / seed) dans un coffre-fort hors-ligne.
# Le seed (12 mots) permet de RECRÉER le wallet en cas de perte du fichier.
```

### B3. Financer depuis un échange ou un autre wallet XEL

```bash
#   - Envoyer d'abord UN PETIT MONTANT (ex. 5 XEL) vers chaque adresse mainnet
#     pour tester le transfert et la synchro AVANT d'envoyer le gros.
#   - Vérifier la réception :
python3 scripts/xrpc.py --wallet-url http://127.0.0.1:8081/json_rpc --wallet-auth dev:dev balance
```

---

## C. Budget XEL nécessaire (mainnet)

Tous les montants en **atomics** (100000000 = 1 XEL) :

| Poste | Montant min | Notes |
|---|---|---|
| Fees TX + gas (deploys + ~30 invokes) | ~100-200 M | gas max 5-20 M par TX |
| propose (sub 1e6 + budget 1e8 + liq 1e8) | 201 M (déposés, exposés) | dépôt dans le contrat |
| buy (graduation) | 110 M (déposés) | devient réserves |
| add_liquidity DEX | 150 M XEL + 310e9 tokens | LP |
| swaps (tests) | 10-50 M | récupérables en partie |
| Auto-prudence | + 200 M de marge | — |
| **Total confortable admin** | **≥ 3 XEL (3e8-3e9) d'atomics de travail** | voir §K |

> Recommandation mainnet : prévoir **≥ 10 XEL (1 000 000 000 atomic)**
> répartis admin/user pour tout le flux + marge de sécurité. Le reste des
> fonds vit HORS de la chaîne (coffre-froid) jusqu'à la validation finale.
> Attention : sur testnet public, les récompenses de minage étaient
> **verrouillées temporairement** (montant « available » < solde) — sur
> mainnet, les fonds envoyés depuis un échange sont disponibles immédiatement,
> mais prévoyez la latence de stabilisation pour les réutiliser.

---

## D. Déploiement — ORDRE IMPÉRATIF (DEX d'abord, puis Vault)

```bash
XEL=0000000000000000000000000000000000000000000000000000000000000000
VAULT_SRC=./xelis-vault/out/VaultLaunch.hex
DEX_SRC=./xelis-vault/out/LaunchDEX.hex

# ===== D0. Vérifier les hash des binaires AVANT de déployer =====
shasum -a 256 "$VAULT_SRC" "$DEX_SRC"
#   Référence testnet public déployée le 23/09/2026 :
#   VaultLaunch.hex -> b6e9cb4757bae8b629b2fdbfa61f3d00281048b6354f4ef0f057b34117b9d30f
#   LaunchDEX.hex   -> 3406758971c1543cd1cb2720a38dd1227af73b25731485f54cc1996d84424fe6
#   Les hash de deploy mainnet SERONT DIFFÉRENTS (adresses sources), mais les
#   .hex doivent être identiques.

# ===== D1. Déployer LaunchDEX =====
python3 scripts/xrpc.py deploy "$DEX_SRC" --max-gas 20000000
#   -> TX_HASH: <DEX_HASH>   (le hash du contrat déployé == hash de la TX)
#   ATTENTION : recopier EXACTEMENT ce hash, il servira au Vault.

# ===== D2. Déployer VaultLaunch =====
python3 scripts/xrpc.py deploy "$VAULT_SRC" --max-gas 20000000
#   -> TX_HASH: <VAULT_HASH>

# ===== D3. Vérifier que les 2 contrats sont bien enregistrés =====
python3 scripts/xrpc.py contracts --max 20
#   réseau mainnet, les deux hash présents.
```

---

## E. Configuration (pins + params) — ordre exact

```bash
# ===== E1. Vault : lui donner l'adresse du DEX (entrée 50 = set_dex_address) =====
python3 scripts/xrpc.py invoke <VAULT_HASH> 50 \
  '[{"type":"primitive","value":{"type":"opaque","value":{"type":"Hash","value":"<DEX_HASH>"}}}]'
python3 scripts/xrpc.py wait-tx <TX> --timeout 300

# ===== E2. DEX : déclarer le launchpad autorisé à croiser create_pool =====
#   -> C'EST LE WALLET USER (celui qui migrera les projets)
python3 scripts/xrpc.py invoke <DEX_HASH> 13 \
  '[{"type":"primitive","value":{"type":"opaque","value":{"type":"Address","value":"<USER_ADDR>"}}}]'
python3 scripts/xrpc.py wait-tx <TX> --timeout 300

# ===== E3. Paramètres Vault (une commande par paramètre) =====
python3 scripts/xrpc.py invoke <VAULT_HASH> 34 '[{"type":"primitive","value":{"type":"u64","value":"1000000"}}]'   # sub  = 0.01 XEL
python3 scripts/xrpc.py invoke <VAULT_HASH> 48 '[{"type":"primitive","value":{"type":"u64","value":"100000000"}}]' # abd  = 1 XEL (budget asset)
python3 scripts/xrpc.py invoke <VAULT_HASH> 39 '[{"type":"primitive","value":{"type":"u64","value":"100000000"}}]' # mnl  = 1 XEL (liquidity)
python3 scripts/xrpc.py invoke <VAULT_HASH> 40 '[{"type":"primitive","value":{"type":"u64","value":"1"}}]'           # mnp  = 1 participant min
python3 scripts/xrpc.py invoke <VAULT_HASH> 41 '[{"type":"primitive","value":{"type":"u64","value":"8000"}}]'      # mab  = 80 % d'approbation
python3 scripts/xrpc.py invoke <VAULT_HASH> 42 '[{"type":"primitive","value":{"type":"u64","value":"720"}}]'      # vdt  = fenêtre 720 topos
python3 scripts/xrpc.py invoke <VAULT_HASH> 43 '[{"type":"primitive","value":{"type":"u64","value":"2"}}]'         # gmu  = graduation x2
python3 scripts/xrpc.py invoke <VAULT_HASH> 49 '[{"type":"primitive","value":{"type":"u64","value":"0"}}]'         # vdp  = vote gratuit 0
python3 scripts/xrpc.py invoke <VAULT_HASH> 35 '[{"type":"primitive","value":{"type":"u64","value":"50"}}]'        # tfe  = 0.5 % trading
python3 scripts/xrpc.py invoke <VAULT_HASH> 36 '[{"type":"primitive","value":{"type":"u64","value":"25"}}]'        # gfe  = 0.25 % gradué
python3 scripts/xrpc.py invoke <VAULT_HASH> 37 '[{"type":"primitive","value":{"type":"u64","value":"500"}}]'       # mgf  = 5 % migration fee

# ===== E4. Paramètres DEX =====
python3 scripts/xrpc.py invoke <DEX_HASH> 11 '[{"type":"primitive","value":{"type":"u64","value":"30"}}]'  # sfe = 0.3 %
python3 scripts/xrpc.py invoke <DEX_HASH> 29 '[{"type":"primitive","value":{"type":"u64","value":"5000"}}]' # fsl = 50/50 LP split
# (eventuels bounds: entrée 12)

# ===== E5. Contrôle final de config (storage) =====
python3 scripts/xrpc.py state <VAULT_HASH> pfe     # pending fees
python3 scripts/xrpc.py state <VAULT_HASH> pc      # project count (=0 au départ)
python3 scripts/xrpc.py state <DEX_HASH> sfe       # swap fee
```

**Verdict avant de continuer : chaque `ok` et chaque valeur de storage
doivent correspondre. Sinon, STOP — corriger avant d'engager des fonds.**

---

## F. Test le plus petit possible AVANT le vrai flux

Sur mainnet, faire d'abord une **répétition complète sur le testnet public**
(runbook 1) avec les MÊMES fichiers hex. Sur le mainnet lui-même :

```bash
# 1) Proposer un projet TEST avec strictement le minimum
#    (le dépôt proposé == 201M, récupérable seulement si rejeté — donc
#     utiliser un montant "poubelle" si la config le permet, sinon accepter
#     que ce test consomme des fonds)
python3 scripts/xrpc.py invoke <VAULT_HASH> 20 \
  '[{"type":"primitive","value":{"type":"string","value":"Test"}},
    {"type":"primitive","value":{"type":"string","value":"TST"}},
    ... (7 autres strings vides),
    {"type":"primitive","value":{"type":"u64","value":"1000000000000"}},
    {"type":"primitive","value":{"type":"u64","value":"1000"}},
    {"type":"primitive","value":{"type":"u64","value":"0"}}]' \
  --deposits "{\"$XEL\": 201000000}" --max-gas 10000000

# 2) Vérifier état p:0:st == 0, pc == 1
# 3) support(0) avec 50M
# 4) Attendre la fenêtre (720 topos × 5 s ≈ 1 h mainnet ; ~90 min testnet public)
#    puis finalize_validation
```

> En production réelle, ce projet test consomme ~350M atomic (3.5 XEL)
> irrécupérables s'il n'est pas rejeté. À faire avec un budget dédié.

---

## G. Flux complet mainnet (ordres + vérifications)

```bash
# ===== G1. propose (dépôt 201M : fee 1e6 + budget 1e8 + liq 1e8) =====
#   (voir F1 — mêmes params ; le pid retourné est 0 au premier projet)

# ===== G2. support (dépôt 50M) =====
python3 scripts/xrpc.py invoke <VAULT_HASH> 21 \
  '[{"type":"primitive","value":{"type":"u64","value":"0"}}]' \
  --deposits "{\"$XEL\": 50000000}"

# ===== G3. APRÈS la fenêtre (~1 h mainnet) : finalize SANS top-up =====
#   (le budget asset 1e8 couvre le fee de création d'asset 1e8)
python3 scripts/xrpc.py invoke <VAULT_HASH> 23 \
  '[{"type":"primitive","value":{"type":"u64","value":"0"}}]' --max-gas 10000000
#   Vérifier : p:0:st == 2, p:0:bt != 0, asset p:0:ah présent.

# ===== G4. buy (dépôt 110M) => réserves ≥ 2e8 => graduation =====
python3 scripts/xrpc.py invoke <VAULT_HASH> 24 \
  '[{"type":"primitive","value":{"type":"u64","value":"0"}}]' \
  --deposits "{\"$XEL\": 110000000}"
#   Vérifier : p:0:st == 3, p:0:gr == true.

# ===== G5. sell (du user, sur la courbe, AVANT migration) =====
#   (depôt tokens p:0:ah ; voir run_user_test.py pour le détail du paramètre
#    — le user dépose l'asset du projet, ex. 100M tokens)

# ===== G6. migrate (cross-call DEX create_pool) =====
#   DOIT être appelé par le USER (seul launchpad autorisé par set_launchpad)
python3 scripts/xrpc.py invoke <VAULT_HASH> 32 \
  '[{"type":"primitive","value":{"type":"u64","value":"0"}}]' --max-gas 20000000
#   Vérifier : p:0:mi == true, pool DEX q:<ASSET>:xr/yr > 0.

# ===== G7. sync_trust_to_dex (tolérance "insync") =====
python3 scripts/xrpc.py invoke <VAULT_HASH> 33 \
  '[{"type":"primitive","value":{"type":"u64","value":"0"}}]'

# ===== G8. add_liquidity DEX (150M XEL + 310e9 tokens) =====
python3 scripts/xrpc.py invoke <DEX_HASH> 10 \
  '[{"type":"primitive","value":{"type":"opaque","value":{"type":"Hash","value":"<ASSET>"}}}]' \
  --deposits "{\"$XEL\": 150000000, \"<ASSET>\": 310000000000}"

# ===== G9. swaps =====
python3 scripts/xrpc.py invoke <DEX_HASH> 8 \
  '[{"type":"primitive","value":{"type":"opaque","value":{"type":"Hash","value":"<ASSET>"}}},{"type":"primitive","value":{"type":"u64","value":"1"}}]' \
  --deposits "{\"$XEL\": 10000000}"
python3 scripts/xrpc.py invoke <DEX_HASH> 9 \
  '[{"type":"primitive","value":{"type":"opaque","value":{"type":"Hash","value":"<ASSET>"}}},{"type":"primitive","value":{"type":"u64","value":"1"}}]' \
  --deposits "{\"<ASSET>\": 50000000}"

# ===== G10. fees =====
python3 scripts/xrpc.py invoke <DEX_HASH> 30 \
  '[{"type":"primitive","value":{"type":"opaque","value":{"type":"Hash","value":"<ASSET>"}}}]'  # claim_lp_fees
python3 scripts/xrpc.py invoke <VAULT_HASH> 53 '[{"type":"primitive","value":{"type":"u64","value":"<pfe>"}}]'  # withdraw_fees
```

---

## H. Checklist de sécurité ZÉRO PERTE (avant, pendant, après)

**AVANT (pré-déploiement)**
- [ ] Binaires à jour (`xelis_daemon` etc. ≥ v1.24 requis par V7 mainnet).
- [ ] `get_info` → `network == "mainnet"` ET hauteur ≈ hauteur officielle.
- [ ] Wallets **créés en network=mainnet** (jamais importés du devnet/testnet).
- [ ] Seeds mots écrits hors-ligne ; wallet re-créable.
- [ ] Contrats **compilés à partir des sources finales** (`shasum -a 256` des
      `.hex` identiques au testnet public déployé).
- [ ] **Répétition complète faite sur le testnet public** juste avant (mêmes .hex).

**PENDANT**
- [ ] Un seul paramètre/hash modifié à la fois ; vérifier le storage après chaque TX.
- [ ] Ne jamais broadcaster 2 gros invokes simultanés (ordre de nonce !).
- [ ] Vérifier chaque `executed_in_block` (pas juste `in_mempool`).
- [ ] `set_launchpad` : vérifier que l'ADRESSE affichée est bien le user (erreur
      classique : pointer vers soi-même).
- [ ] `set_dex_address` : hash recopié depuis la TX de deploy, pas du fichier.

**APRÈS**
- [ ] Vérifier que `p:0:st==3` (gradué) AVANT toute opération DEX sur l'asset.
- [ ] Vérifier que les LP/fees du pool correspondent aux dépôts.
- [ ] Transfert de sortie des fees vers l'adresse de trésorerie (hors contrat).

---

## I. Erreurs classiques → cause → action (rencontrées en test)

| Erreur | Cause | Action |
|---|---|---|
| `Network mismatch for this wallet storage (stored: Devnet)!` | wallet créé sur un autre réseau | recréer sur le bon réseau (`drive_wallet_create.py --network mainnet`) |
| `Impossible to enable simulator mode except in dev network!` | `--simulator` sur testnet/mainnet | retirer `--simulator` ; c'est le miner qui produit les blocs |
| `Boost sync and fast sync can't be enabled at the same time!` | les 2 flags combinés | utiliser UN des deux (fast sync = pas d'historique complet ; boost = vérifié) |
| `notauth` | entrée admin appelée par un non-admin | utiliser le wallet admin (8081) |
| `paused` | contrat en pause (`set_paused(true)`) | ré-ouvrir avec `set_paused(false)` |
| `tiny` | swap sous le minimum défini | respecter `min_swap_xel` (entrée 12) |
| `toolow` / `toohigh` | `set_fee_split` hors bornes (2500-7500) | corriger la valeur |
| `insync` | `sync_trust_to_dex` mais déjà synchro | toléré (état désiré déjà atteint) |
| `badamt` | `withdraw_fees` > pending fees | retirer d'abord (`pfe`) puis 0 restant → refusé |
| `not enough funds in the account` | récompenses de minage verrouillées (dispo < solde) | attendre la stabilisation ; transférer par paliers |
| TX jamais confirmée (mempool) | miner absent ou hashrate < difficulté | vérifier que le miner tourne ; re-broadcast |

---

## J. Sauvegarde / récupération

```bash
# ===== Sauvegarde d'un wallet (fichier chiffré + seed) =====
#   Le fichier wallet est chiffré par le mot de passe. Le seed (12 mots)
#   est la vraie sauvegarde — il permet de réimporter partout :
#   - lancer le wallet, choix "restore from seed", network=mainnet.

# ===== État des contrats (à archiver après deploy) =====
cat > /tmp/mainnet_contracts.json <<'EOF'
{
  "network": "mainnet",
  "date": "<ISO_DATE>",
  "dex_hash": "<DEX_HASH>",
  "vault_hash": "<VAULT_HASH>",
  "admin": "<ADMIN_ADDR>",
  "user": "<USER_ADDR>",
  "pins": {"vault.set_dex_address": "<DEX_HASH>", "dex.set_launchpad": "<USER_ADDR>"},
  "params": {"sub": 1000000, "abd": 100000000, "mnl": 100000000, "mnp": 1,
             "mab": 8000, "vdt": 720, "gmu": 2, "vdp": 0}
}
EOF
cp /tmp/mainnet_contracts.json ~/xelis-vault/backups/mainnet_contracts_$(date +%Y%m%d).json
```

---

## K. Valeurs réelles du toolchain (validées sur le testnet public 23/09/2026)

Référence du déploiement testnet **public** (chaîne réelle) :
- DEX `97104c218f1627a51a380e11eb7f9ffe6e05bc809a83fbc25511c948c6f4a382`
- Vault `c546f30418490996aafcc78e0106c36e5e9ca16e6361f684214f311a890e31f7`
- admin `xet:qz5634…` ; user `xet:ugndnt7…`
- Transferts admin→user : 400M (`a16488b4…`) + 220M (`d8ef25c4…`) → user 620M
- Miner : 4 threads CPU → 642 blocs acceptés (~1 bloc/10-30 s à difficulté 10K)
- Fenêtre de validation : ~720 topos ≈ ~90 min (testnet public ~11 s/bloc)

> ⚠️ Le montant « ≥ 10 XEL de travail » (§C) est un minimum pour rejouer tout
> le flux. Sur mainnet, augmentez la marge (frais réels, gas imprévus) et
> gardez le reste des fonds hors chaîne jusqu'à la fin des tests.

---

## L. À faire absolument AVANT d'engager de gros fonds mainnet

1. **Replay intégral sur le testnet PUBLIC** des sections D→G (fait : setup
   DONE, propose/support confirmés, finalize → buy → sell → migrate → add_liq
   → swaps → claim en cours / à rejouer sur le public — voir runbook 1 §8).
2. **Vérifier les hash des .hex** compilés (identiques entre testnet et mainnet).
   - Référence déployée le 23/09/2026 (testnet public) :
     - `VaultLaunch.hex` → `b6e9cb4757bae8b629b2fdbfa61f3d00281048b6354f4ef0f057b34117b9d30f`
     - `LaunchDEX.hex` → `3406758971c1543cd1cb2720a38dd1227af73b25731485f54cc1996d84424fe6`
   - `shasum -a 256 out/VaultLaunch.hex out/LaunchDEX.hex` doit donner ces valeurs
     AVANT de déployer (les hash de deploy au §G viennent de ces fichiers).
3. **Vérifier la hauteur mainnet** sur `https://explorer.xelis.io` (le DNS peut
   être bloqué depuis votre machine : utiliser les IP des seeds via `dig`).
4. **Petits transfers de test** (0.5 XEL) avant les gros.