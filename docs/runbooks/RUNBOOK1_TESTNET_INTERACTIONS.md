# RUNBOOK 1 — Interactions complètes avec les contrats (réseau TESTNET PUBLIC)

> Réseau : **testnet public officiel XELIS** (`testnet-explorer.xelis.io`),
> chaîne réelle minée par la communauté (height ~380 000, topo ~384 000 le
> 23/09/2026, block version 6, hard forks Smart Contracts dès height 15).
> Le daemon local est **synchronisé sur ce réseau** (fast sync via seed IP
> `74.208.251.149:2125`) et le **miner CPU produit des blocs réels acceptés
> par le réseau** (642 blocs « accepted by network » à la date du runbook).
>
> Ce fichier liste **toutes les commandes** utilisées pour interagir avec
> chaque fonction de `VaultLaunch` (le launchpad) et `LaunchDEX` (le DEX)
> sur le testnet public. Les hash/adresses ci-dessous sont ceux du
> déploiement public du 23/09/2026 — ils changent à chaque nouveau
> déploiement.

---

## 0. Matériel (env actuel — testnet public)

| Élément | Valeur |
|---|---|
| Explorateur réseau | `https://testnet-explorer.xelis.io` |
| Daemon RPC (local, public) | `http://127.0.0.1:8080/json_rpc` (network=testnet) |
| Wallet admin (RPC) | `http://127.0.0.1:8081/json_rpc` — `dev`/`dev` |
| Wallet user (RPC) | `http://127.0.0.1:8082/json_rpc` — `user`/`user` |
| Miner | 4 threads vers admin — blocs acceptés par le réseau |
| Block time moyen réseau | ~11,2 s (get_info.average_block_time) |
| Récompense de minage | ~43,42 M atomic / bloc (0,4342 XEL) |
| Admin address | `xet:qz5634ew8xpmqne5vs67k063ak9tgsdxpm3zx7zv4tfryxpg5v0sqnmmzeg` |
| User address | `xet:ugndnt7qrauv7yqnad48ssp6y4aay45785ex5sxtdlkcm9ukzahsqc0zs57` |
| **VaultLaunch (Vault)** | `c546f30418490996aafcc78e0106c36e5e9ca16e6361f684214f311a890e31f7` |
| **LaunchDEX (DEX)** | `97104c218f1627a51a380e11eb7f9ffe6e05bc809a83fbc25511c948c6f4a382` |
| Asset XEL | `0000000000000000000000000000000000000000000000000000000000000000` |

Helper utilisé : `python3 scripts/xrpc.py` (daemon 8080 + wallet admin 8081).
Tous les invokes du **user** (8082) passent par `build_transaction` direct
(voir section 6).

Format des paramètres XELIS (types typés JSON) :
- `u64(v)`      → `{"type":"primitive","value":{"type":"u64","value":"v"}}`
- `string(v)`   → `{"type":"primitive","value":{"type":"string","value":v}}`
- `hash(h)`     → `{"type":"primitive","value":{"type":"opaque","value":{"type":"Hash","value":h}}}`
- `address(a)`  → `{"type":"primitive","value":{"type":"opaque","value":{"type":"Address","value":a}}}`
- `bool(b)`     → `{"type":"primitive","value":{"type":"boolean","value":b}}`

Deposit (joindre des fonds à un invoke) :
`--deposits '{"<asset_hex>": <montant_atomic>}'` (100000000 atomic = 1 XEL).

---

## 1. Démarrage de l'environnement (daemon public + wallets + miner)

### 1.1 Synchroniser le daemon sur le testnet PUBLIC (fast sync)

> ⚠️ **DNS bloqué depuis cette machine** : `dig`/`nslookup` résolvent mais la
> libc (curl/Python) échoue pour les noms d'hôte **applicatifs**
> (`testnet-node.xelis.io`). Le **P2P n'a pas besoin du DNS** : le seed
> testnet est une IP directe `74.208.251.149:2125`.

```bash
# daemon full (synchro depuis le début) :
./bin/xelis_daemon --network=testnet \
  --dir-path=./data/public-testnet/ \
  --rpc-bind-address=127.0.0.1:8080 \
  --disable-interactive-mode --disable-ascii-art \
  --disable-file-logging --disable-log-color \
  >> ./logs/daemon-public-testnet.log 2>&1 &

# OU fast sync (recommandé pour rattraper ~380k blocs vite) :
#   --allow-fast-sync : récupère un état bootstrappé du seed, ne stocke pas
#                       tout l'historique (ne vérifie pas toute l'histoire)
./bin/xelis_daemon --network=testnet \
  --dir-path=./data/public-testnet/ \
  --rpc-bind-address=127.0.0.1:8080 \
  --allow-fast-sync \
  --disable-interactive-mode --disable-ascii-art \
  --disable-file-logging --disable-log-color \
  >> ./logs/daemon-public-testnet.log 2>&1 &
#   Mesuré le 23/09/2026 : fast sync ~90 s au lieu de ~275 min en full sync.
#   (boost sync 22,8 blocs/s ; fast sync ~6 270 blocs/s — et ne PAS combiner
#    --allow-fast-sync ET --allow-boost-sync : « Boost sync and fast sync
#    can't be enabled at the same time! »)
```

Vérifier la synchro (le réseau public reste branché pendant le fast sync) :

```bash
curl -s -X POST http://127.0.0.1:8080/json_rpc \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"get_info"}'
#   network: testnet ; height ≈ 379800+ ; stable_topoheight ≈ topoheight
```

### 1.2 Lancer les wallets (testnet, seed IP direct)

```bash
# wallet admin (8081) — storage testnet
./bin/xelis_wallet --network=testnet \
  --wallet-path=./wallets/wallet_testnet --password=dev \
  --daemon-address=http://127.0.0.1:8080 \
  --rpc-bind-address=127.0.0.1:8081 --rpc-username=dev --rpc-password=dev \
  --disable-interactive-mode --disable-ascii-art \
  --disable-file-logging --disable-log-color \
  >> ./logs/wallet-testnet.log 2>&1 &

# wallet user (8082)
./bin/xelis_wallet --network=testnet \
  --wallet-path=./wallets/wallet_user_testnet --password=dev \
  --daemon-address=http://127.0.0.1:8080 \
  --rpc-bind-address=127.0.0.1:8082 --rpc-username=user --rpc-password=user \
  --disable-interactive-mode --disable-ascii-art \
  --disable-file-logging --disable-log-color \
  >> ./logs/wallet-user-testnet.log 2>&1 &
```

> 💡 Redémarrer les wallets après un changement de chaîne : ils gardent un
> cache de synchro basé sur l'ancienne chaîne et peuvent rester bloqués
> (« EventReceiver lagged behind » / WebSocket reset). Le restart les
> resynchronise proprement sur la chaîne publique.

### 1.3 Lancer le miner (4 threads → admin)

```bash
./bin/xelis_miner --network=testnet \
  --daemon-address=http://127.0.0.1:8080 \
  --thread-count=4 \
  --address=xet:qz5634ew8xpmqne5vs67k063ak9tgsdxpm3zx7zv4tfryxpg5v0sqnmmzeg \
  >> ./logs/miner-testnet.log 2>&1 &
```

Confirmation que le minage est bien sur le réseau **public** (log miner) :

```
INFO xelis_miner > New job received: difficulty 10K at height 379761
INFO xelis_miner > Thread #0: block b3c0539134… found at height 379761 with difficulty 25.1K
INFO xelis_miner > submitting new block found...
INFO xelis_miner > Block submitted has been accepted by network !
```

> « Block submitted has been accepted by network » = le bloc a été propagé et
> accepté par les autres nœuds du testnet public — on est bien sur la chaîne
> réelle. 642 blocs acceptés à la date du runbook.

---

## 2. Déploiement des contrats (testnet public)

```bash
# Déployer le DEX d'abord (Vault y cross-appellera create_pool)
python3 scripts/xrpc.py deploy out/LaunchDEX.hex --max-gas 20000000
#   TX_HASH: 97104c218f1627a51a380e11eb7f9ffe6e05bc809a83fbc25511c948c6f4a382
#   (le hash du module déployé == hash de la TX de deploy)
python3 scripts/xrpc.py wait-tx 97104c218f1627a51a380e11eb7f9ffe6e05bc809a83fbc25511c948c6f4a382 --timeout 300

# Déployer VaultLaunch ensuite
python3 scripts/xrpc.py deploy out/VaultLaunch.hex --max-gas 20000000
#   TX_HASH: c546f30418490996aafcc78e0106c36e5e9ca16e6361f684214f311a890e31f7
python3 scripts/xrpc.py wait-tx c546f30418490996aafcc78e0106c36e5e9ca16e6361f684214f311a890e31f7 --timeout 300
```

---

## 3. Config initiale (VaultLaunch) — fait sur le testnet public

| Entrée | Nom | Paramètres utilisés | Effet |
|---|---|---|---|
| **50** | `set_dex_address` | `hash(DEX)` | le Vault connaît le DEX (pour la migration `create_pool`) |
| **13** (DEX) | `set_launchpad` | `address(USER)` | seul le wallet USER peut cross-appeler `create_pool` (celui qui migre) |
| **34** | `set_submission_fee` | `u64(1_000_000)` | 0.01 XEL par propose |
| **48** | `set_asset_budget` | `u64(100_000_000)` | budget 1 XEL : couvre le fee de création d'asset (1e8) sans top-up |
| **39** | `set_min_liquidity` | `u64(100_000_000)` | liquidité minimale 1 XEL (floor 1e8) |
| **40** | `set_min_participants` | `u64(1)` | 1 seul wallet suffit (test) |
| **49** | `set_vote_deposit` | `u64(0)` | votes gratuits (0 = fallback 50M si non stocké) |
| **42** | `set_validation_duration` | `u64(720)` | fenêtre de validation minimale = 720 topos |
| **43** | `set_graduation_multiplier` | `u64(2)` | graduation quand réserves ≥ 2× liquidité |
| **37** | `set_migration_fee` | `u64(500)` | fee de migration 5 % (prise UNE fois à la graduation) — aligné mainnet (§ runbook 2) |

Commandes réelles :

```bash
# Vault : set_dex_address(DEX)
python3 scripts/xrpc.py invoke c546f30418490996aafcc78e0106c36e5e9ca16e6361f684214f311a890e31f7 50 \
  '[{"type":"primitive","value":{"type":"opaque","value":{"type":"Hash","value":"97104c218f1627a51a380e11eb7f9ffe6e05bc809a83fbc25511c948c6f4a382"}}}]'

# DEX : set_launchpad(USER)
python3 scripts/xrpc.py invoke 97104c218f1627a51a380e11eb7f9ffe6e05bc809a83fbc25511c948c6f4a382 13 \
  '[{"type":"primitive","value":{"type":"opaque","value":{"type":"Address","value":"xet:ugndnt7qrauv7yqnad48ssp6y4aay45785ex5sxtdlkcm9ukzahsqc0zs57"}}}]'

# Params admin (un par un)
python3 scripts/xrpc.py invoke c546f30418490996aafcc78e0106c36e5e9ca16e6361f684214f311a890e31f7 34 '[{"type":"primitive","value":{"type":"u64","value":"1000000"}}]'
python3 scripts/xrpc.py invoke c546f30418490996aafcc78e0106c36e5e9ca16e6361f684214f311a890e31f7 48 '[{"type":"primitive","value":{"type":"u64","value":"100000000"}}]'
python3 scripts/xrpc.py invoke c546f30418490996aafcc78e0106c36e5e9ca16e6361f684214f311a890e31f7 39 '[{"type":"primitive","value":{"type":"u64","value":"100000000"}}]'
python3 scripts/xrpc.py invoke c546f30418490996aafcc78e0106c36e5e9ca16e6361f684214f311a890e31f7 40 '[{"type":"primitive","value":{"type":"u64","value":"1"}}]'
python3 scripts/xrpc.py invoke c546f30418490996aafcc78e0106c36e5e9ca16e6361f684214f311a890e31f7 49 '[{"type":"primitive","value":{"type":"u64","value":"0"}}]'
python3 scripts/xrpc.py invoke c546f30418490996aafcc78e0106c36e5e9ca16e6361f684214f311a890e31f7 42 '[{"type":"primitive","value":{"type":"u64","value":"720"}}]'
python3 scripts/xrpc.py invoke c546f30418490996aafcc78e0106c36e5e9ca16e6361f684214f311a890e31f7 43 '[{"type":"primitive","value":{"type":"u64","value":"2"}}]'
python3 scripts/xrpc.py invoke c546f30418490996aafcc78e0106c36e5e9ca16e6361f684214f311a890e31f7 37 '[{"type":"primitive","value":{"type":"u64","value":"500"}}]'  # mgf = 5 % (TX bfb9e784…, bloc 725deb56…)
```

Vérifier un paramètre stocké :

```bash
python3 scripts/xrpc.py state c546f30418490996aafcc78e0106c36e5e9ca16e6361f684214f311a890e31f7 pfe   # pending fees
python3 scripts/xrpc.py state c546f30418490996aafcc78e0106c36e5e9ca16e6361f684214f311a890e31f7 pc    # project count
```

---

## 4. VaultLaunch — toutes les entrées (selon ABI)

Vault = `c546f30418490996aafcc78e0106c36e5e9ca16e6361f684214f311a890e31f7`
(prefixe `python3 scripts/xrpc.py invoke <VAULT> <id> '<params>'`)

### 4.1 Flux utilisateur (créateur)

| ID | Fonction | Paramètres | Notes / commande testée |
|---|---|---|---|
| **20** | `propose(name, symbol, description, website, logo, twitter, telegram, discord, total_supply, team_bps, vesting_duration)` | 8 strings + 3 u64 | dépôt XEL 201000000 (= fee 1e6 + budget 1e8 + liq 1e8). Retourne le pid. **Fait** : `pc 0→1`, `p:0:st=0`. |
| **21** | `support(pid)` | `u64(pid)` | dépôt XEL 50000000 (locké/refundé selon vdp). **Fait** : `sp=1`, slot vote enregistré. |
| **23** | `finalize_validation(pid)` | `u64(pid)` | après `ve` dépassé. SANS top-up grâce au budget 1e8 (couvre fee d'asset 1e8). → st=2 bonding, asset minté. **REJOUER après la fenêtre**. |
| **24** | `buy(pid)` | `u64(pid)` | dépôt XEL 110M → réserves ≥2e8 → graduation (st=3). |
| **25** | `sell(pid)` | `u64(pid)` | dépôt tokens (ex. 100M) → vend sur la courbe. Refusé si migré (`migrated`). |
| **26** | `claim_refund(pid)` | `u64(pid)` | refund des dépôts si projet rejeté. Erreur sinon (`badstate`). |
| **27** | `claim_vote_deposit(pid, round)` | `u64(pid), u64(round)` | récupère le vote deposit locké. |
| **28** | `request_revalidation(pid)` | `u64(pid)` | rejeté si déjà gradué (`badstate`). |
| **29** | `update_project_info(pid, description, website, logo, twitter, telegram, discord)` | `u64` + 6 strings | réservé au créateur (`notauth` pour l'admin). |
| **30** | `start_team_vesting(pid, duration)` | `u64(pid), u64(duration)` | créateur uniquement (`notauth` admin). |
| **31** | `claim_team_allocation(pid)` | `u64(pid)` | créateur uniquement (`notauth` admin). |
| **32** | `migrate(pid)` | `u64(pid)` | cross-call DEX `create_pool` (uniquement si DEX pinné sur cet appelant). |
| **33** | `sync_trust_to_dex(pid)` | `u64(pid)` | sync flag de confiance DEX ; `insync` toléré (déjà dans l'état désiré). |

### 4.2 Setter admin (Vault)

| ID | Fonction | Paramètres | Storage key |
|---|---|---|---|
| **34** | `set_submission_fee` | `u64(fee)` | `sub` |
| **35** | `set_trading_fee` | `u64(bps)` | `tfe` |
| **36** | `set_graduated_trading_fee` | `u64(bps)` | `gfe` |
| **37** | `set_migration_fee` | `u64(bps)` | `mgf` |
| **38** | `set_direct_listing_threshold` | `u64(amount)` | `dlt` |
| **39** | `set_min_liquidity` | `u64(amount)` | `mnl` |
| **40** | `set_min_participants` | `u64(count)` | `mnp` |
| **41** | `set_min_approval_ratio` | `u64(bps)` | `mab` |
| **42** | `set_validation_duration` | `u64(topos)` | `vdt` |
| **43** | `set_graduation_multiplier` | `u64(multiplier)` | `gmu` |
| **44** | `set_team_unlock_delay` | `u64(topos)` | `tdy` |
| **45** | `set_vesting_bounds` | `u64(min_topos), u64(max_topos)` | `vmn`, `vmx` |
| **46** | `set_recovery_fee` | `u64(fee)` | `rfe` |
| **47** | `set_recovery_params` | `u64(participants), u64(ratio_bps)` | `rmp`, `rmr` |
| **48** | `set_asset_budget` | `u64(amount)` | `abd` |
| **49** | `set_vote_deposit` | `u64(amount)` | `vdp` |
| **50** | `set_dex_address` | `hash(addr)` | `dax` |
| **51** | `set_admin` | `address(new_admin)` | — |
| **52** | `set_paused` | `bool(flag)` | `pz` (bloque buy/support…) |
| **53** | `withdraw_fees` | `u64(amount)` | vide `pfe` ; erreur `badamt` si vide |

Exemple de séquence read → set → verify → restore (faite par
`run_admin_test.py`, ADMIN = wallet 8081) :

```bash
# — set_submission_fee 2M puis restore 1M
python3 scripts/xrpc.py invoke <VAULT> 34 '[{"type":"primitive","value":{"type":"u64","value":"2000000"}}]'
python3 scripts/xrpc.py state <VAULT> sub            # -> 2000000
python3 scripts/xrpc.py invoke <VAULT> 34 '[{"type":"primitive","value":{"type":"u64","value":"1000000"}}]'
python3 scripts/xrpc.py state <VAULT> sub            # -> 1000000
```

---

## 5. LaunchDEX — toutes les entrées (selon ABI)

DEX = `97104c218f1627a51a380e11eb7f9ffe6e05bc809a83fbc25511c948c6f4a382`

| ID | Fonction | Paramètres | Notes |
|---|---|---|---|
| **8** | `swap_xel_for_token` | `hash(asset), u64(min_tokens_out)` | dépôt XEL ; fee split LP. Refusé si `<` min swap (`tiny`). |
| **9** | `swap_token_for_xel` | `hash(asset), u64(min_xel_out)` | dépôt tokens. |
| **10** | `add_liquidity` | `hash(asset)` | dépôt XEL + tokens (excedent refundé). Skip si LP déjà présent. |
| **11** | `set_swap_fee` | `u64(bps)` | key `sfe` |
| **12** | `set_trade_bounds` | `u64(min_seed_xel), u64(min_seed_tokens), u64(min_swap_xel), u64(max_swap_xel), u64(min_swap_tokens), u64(max_swap_tokens)` | keys `mnx,lnt,mnt,tsw,mst,mxs` |
| **13** | `set_launchpad` | `address(addr)` | seul ce wallet peut `create_pool` |
| **14** | `set_admin` | `address(new_admin)` | — |
| **15** | `set_paused` | `bool(flag)` | `xpa` (bloque les swaps) |
| **16** | `withdraw_fees` | `hash(asset), u64(xel_amount), u64(token_amount)` | vide les pots `xf`/`yf` du pool |
| **29** | `set_fee_split` | `u64(lp_bps)` | 2500 ≤ lp ≤ 7500 (`toolow`/`toohigh` sinon) ; key `fsl` |
| **30** | `claim_lp_fees` | `hash(asset)` | crystallise la part LP accrue (event 13) |

Exemples (fait dans `run_admin_test.py`) :

```bash
# set_swap_fee(100) puis verify puis restore(30)
python3 scripts/xrpc.py invoke <DEX> 11 '[{"type":"primitive","value":{"type":"u64","value":"100"}}]'
python3 scripts/xrpc.py state <DEX> sfe             # -> 100

# split 25 % LP : swap 10M -> fee 30K -> LP 7500
python3 scripts/xrpc.py invoke <DEX> 29 '[{"type":"primitive","value":{"type":"u64","value":"2500"}}]'
python3 scripts/xrpc.py invoke <DEX> 8 '[{"type":"primitive","value":{"type":"opaque","value":{"type":"Hash","value":"<ASSET>"}}},{"type":"primitive","value":{"type":"u64","value":"1"}}]' --deposits '{"0000000000000000000000000000000000000000000000000000000000000000":10000000}'
python3 scripts/xrpc.py state <DEX> "q:<ASSET>:xf"   # fees treasury
python3 scripts/xrpc.py state <DEX> "q:<ASSET>:lx"   # LP fee pot
```

---

## 6. Wallet USER (8082) — invokes via build_transaction (comme le user ne passe pas par xrpc.py)

Scripts `run_user_test.py` (user = créateur/proposer) et `run_admin_test.py`
(admin = setters) exécutent tout ceci. Exemple minimal de build+broadcast :

```python
import base64, json, urllib.request
USER = "http://127.0.0.1:8082/json_rpc"
AUTH = "Basic " + base64.b64encode(b"user:user").decode()
def rpc(m, params=None, timeout=120):
    body = {"jsonrpc": "2.0", "id": 1, "method": m}
    if params: body["params"] = params
    req = urllib.request.Request(USER, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Authorization": AUTH})
    r = json.loads(urllib.request.urlopen(req, timeout=timeout).read())
    if "error" in r: raise SystemExit(json.dumps(r["error"]))
    return r.get("result")

def u64(v): return {"type":"primitive","value":{"type":"u64","value":str(v)}}
XEL = "0"*64
tx = rpc("build_transaction", {
    "invoke_contract": {"contract": "c546f30418490996aafcc78e0106c36e5e9ca16e6361f684214f311a890e31f7",
                        "entry_id": 20, "parameters": [...],
                        "max_gas": 10_000_000, "permission": "all",
                        "deposits": {XEL: {"amount": 201_000_000}}},
    "broadcast": True}, timeout=120)
print("tx:", tx["hash"])
```

---

## 7. Commandes de transfert de fonds (admin → user)

```python
# wallet admin 8081 : build_transaction avec transfers
tx = rpc(8081, "dev", "dev", "build_transaction", {
    "transfers": [{"asset": "0"*64, "amount": 400_000_000,
                   "destination": "xet:ugndnt7qrauv7yqnad48ssp6y4aay45785ex5sxtdlkcm9ukzahsqc0zs57"}],
    "broadcast": True})
# tx: a16488b4b1915c56103559867f499f81e36dd128f0c7ae99399ae4ea32f1faa0 (testnet public)
```
> ⚠️ Les récompenses de minage sont **verrouillées temporairement** (montant
> « available » < solde affiché) : il faut attendre la stabilisation des blocs
> avant de pouvoir re-transférer. Transférer par paliers en vérifiant le solde
> spendable. Exemple réel : transferts successifs 400M (`a16488b4…`) puis
> 220M (`d8ef25c4…`) pour amener le user à 620M.

---

## 7ter. Reprise automatique du flux après la fenêtre (`run_user_test.py`)

`run_user_test.py` (user, 8082) : propose → support → finalize → buy → sell
→ migrate → sync → add_liq → swaps → claim_lp_fees. Le wait de fenêtre a été
porté à **1500 × 5 s = 125 min** (720 topos × ~8-11 s/bloc ≈ ~90 min sur le
testnet public).

```bash
cd /Users/adrien/xelis-dev/scripts
python3 run_user_test.py           # flux complet, attend la fenêtre de validation
python3 run_admin_test.py          # après : tests admin + post-migration
```

---

## 7bis. Smoke test SDK live (xvault — LaunchpadReader / DexReader)

Le SDK `sdk/xvault` (Python ≥ 3.10, deps `requests`, `blake3`) lit l'état
des contrats via un `DaemonClient` pointé sur le réseau voulu. Sur le testnet
public, on pointe le daemon local synchronisé (8080) :

```python
from xvault.protocol import DaemonClient
from xvault.launchpad import LaunchpadReader
from xvault.dex import DexReader

D = DaemonClient("http://127.0.0.1:8080/json_rpc")
VAULT = "c546f30418490996aafcc78e0106c36e5e9ca16e6361f684214f311a890e31f7"
DEX   = "97104c218f1627a51a380e11eb7f9ffe6e05bc809a83fbc25511c948c6f4a382"

lp = LaunchpadReader(D, VAULT)   # vsl.paused() / count() / dex_address() / project(0)
dx = DexReader(D, DEX)           # pools_count() / config() / pool(asset)
```

---

## 8. Résumé chronologique réel (testnet PUBLIC, 23/09/2026)

1. **Passage au testnet public** : daemon local chaîne locale arrêtée, data dir
   public propre, daemon relancé `--network=testnet` (seed IP `74.208.251.149:2125`).
2. **Fast sync** (`--allow-fast-sync`) : ~90 s pour rattraper ~380k blocs
   (height 379 759, topo 383 959, stable 383 935) — au lieu de ~275 min en
   full/boost sync.
3. **Miner relancé** (4 threads → admin) : « Block submitted has been accepted
   by network » à height 379 761 (difficulté 25,1K), puis en continu. **642
   blocs acceptés** à 19:39.
4. **Wallets redémarrés** (étaient bloqués sur l'ancienne chaîne) : admin
   resynchronisé → solde 7,8 XEL en montant (récompenses), puis croissance
   (~10,4 XEL à 19:24, ~30,9 XEL à 19:38).
5. **Transfets admin→user** : 400M (`a16488b4…`) + 220M (`d8ef25c4…`) →
   user = 620M (récompenses verrouillées → transferts par paliers).
6. `run_flow.py setup` (adapté : WALLET/USER=adresses testnet) :
   - Deploy DEX → `97104c21…` ; Deploy Vault → `c546f304…` (TX confirmées en
     blocs réels : `79ce2e98…`, `f90a456e…`)
   - `set_dex_address(50)`, `set_launchpad(13)` vers USER
   - Params 34/48/39/40/49/42/43 + **37 `set_migration_fee(500)`** (voir §3) —
     `mgf=500` confirmé en bloc réel `725deb56…`
7. USER propose (entry 20) + support (entry 21) — en cours d'exécution via
   `run_user_test.py` (PID 20304, lancé 19:36) ; **en attente de la fenêtre**
   `ve` (720 topos ≈ ~90 min).
8. Après la fenêtre : finalize → buy → sell → migrate → sync → add_liq →
   swaps → claim (résultats à reporter ici).

> Le testnet **public** a des temps réels : ~11-13 s/bloc, fenêtre 720 topos
> ≈ ~90 min — contre ~1 h (5 s/bloc) sur mainnet.