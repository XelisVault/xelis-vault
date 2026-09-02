# Guide XELIS Vault — Mineur & Oracle

> Guide complet en français pour installer le logiciel, devenir mineur,
> fournir des prix à l'oracle, et gagner des VLT.

---

## Table des matières

1. [Installation](#1-installation)
2. [Démarrage rapide](#2-démarrage-rapide)
3. [Devenir mineur](#3-devenir-mineur)
4. [Fournisseur de prix (oracle)](#4-fournisseur-de-prix-oracle)
5. [Architecture des récompenses](#5-architecture-des-récompenses)
6. [Dépannage](#6-dépannage)
7. [Mise à jour & désinstallation](#7-mise-à-jour--désinstallation)

---

## 1. Installation

### Prérequis

| Logiciel | Version minimum |
|----------|----------------|
| Python   | 3.10+ |
| git      | n'importe |
| curl     | n'importe |

### Installation en une ligne

```bash
curl -fsSL https://xelisvault.github.io/xelis-vault/install | bash
```

L'installateur :
1. Vérifie Python ≥ 3.10, git, curl
2. Clone le dépôt dans `~/.xelis-vault/src/`
3. Crée un environnement virtuel Python (`~/.xelis-vault/venv/`)
4. Installe les dépendances (`requests`, `python-dotenv`)
5. Génère `~/.xelis-vault/config/config.json` avec les adresses des contrats
6. Génère `~/.xelis-vault/config/.env`
7. Installe le lanceur `xvault` dans `~/.local/bin/`
8. Propose de configurer un service auto-démarrage (systemd/launchd)

### Installation non-interactive

```bash
curl -fsSL https://xelisvault.github.io/xelis-vault/install | bash -s -- -y
```

### Contrats déployés (testnet)

Ces adresses sont intégrées dans l'installateur — aucune configuration manuelle nécessaire :

| Contrat | Adresse (64 hex) | Rôle |
|---------|------------------|------|
| PriceOracle v2.1 | `764ad585...` | Prix XEL/USD avec propose → timelock → execute |
| XelisVaultMiner v2.1 | `21ed1297...` | Enregistrement mineur, heartbeat, récompenses |
| VLTToken v5.1 | `7275c55d...` | Token VLT (10M supply fixe) |
| VLT Asset | `2de72ed3...` | Identifiant on-chain du VLT |
| VaultSwapV2 | `1b669939...` | AMM — échange XEL/VLT |
| PSM v5.1 | `9f266744...` | Échange XEL ↔ xUSD au prix oracle |
| xUSD | `909576c1...` | Stablecoin |
| VaultEngine | `667b165c...` | CDP — dépôt XEL, emprunt xUSD |
| StakedOracle v5.0 | `57a34396...` | Oracle décentralisé (réservé) |

---

## 2. Démarrage rapide

### Lancer le daemon XELIS

```bash
# Si vous avez les binaires installés :
xelis_daemon --network testnet \
  --dir-path ~/.xelis-vault/data \
  --rpc-bind-address 127.0.0.1:18081 \
  --enable-contracts-logging
```

### Lancer le wallet

```bash
xvault --wallet
```

Ou manuellement :
```bash
xelis_wallet --seed "VOTRE_PHRASE_DE_RECUPERATION" \
  --password testpass --wallet-path /tmp/vault.db \
  --daemon-address http://127.0.0.1:18081 --network testnet \
  --rpc-bind-address 127.0.0.1:18082 --rpc-username wallet \
  --rpc-password testpass
```

### Vérifier le statut

```bash
# Hauteur du daemon
curl -s http://127.0.0.1:18081/json_rpc \
  -H 'Content-Type: application/json' \
  -d '{"method":"get_info","id":1}' | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['result']['topoheight'])"

# Balance XEL
curl -s http://127.0.0.1:18082/json_rpc \
  -u wallet:testpass \
  -H 'Content-Type: application/json' \
  -d '{"method":"get_balance","params":{"asset":"0000000000000000000000000000000000000000000000000000000000000000"},"id":1}'
```

### Lancer le mineur + oracle (tout-en-un)

```bash
xvault --miner
```

Ceci démarre `scripts/xelis_vault_miner.py` qui gère à la fois :
- La récupération du prix XEL/USD (CoinGecko + MEXC)
- La proposition/execution du prix sur PriceOracle
- L'enregistrement mineur (si pas encore fait)
- Les heartbeats toutes les 100 blocks

---

## 3. Devenir mineur

### Qu'est-ce qu'un mineur XELIS Vault ?

Un mineur XELIS Vault n'est PAS un mineur de blocs XELIS (ceux qui produisent des blocs et gagnent du XEL). Un mineur Vault **exécute des services protocolaires** (oracle de prix) et gagne des **VLT** en récompense.

### Conditions requises

| Condition | Détail |
|-----------|--------|
| Stake minimum | **1000 VLT** (100000000000 en unités atomiques, 8 décimales) |
| Endpoint public | URL publique où le mineur est joignable (peut être un placeholder) |
| Wallet synchronisé | Connecté au daemon, avec assez de XEL pour les frais |
| Services mask | 1 = oracle uniquement |

### Comment obtenir 1000 VLT ?

**Méthode A — Swap XEL → VLT sur VaultSwapV2 :**
Une pool XEL/VLT existe déjà avec liquidité (~140 XEL = 1 VLT).
Utilisez la fonction `swap` (entry 18) de VaultSwapV2.

**Méthode B — Miner le bloc XELIS :**
Le mineur de blocs XELIS (`xelis_miner`) produit des blocks toutes les ~5s
sur testnet (difficulty=10000). Les XEL gagnés peuvent être swappés pour VLT.

**Méthode C — Récompenses oracle :**
Le PriceOracle distribue ~0.71 VLT à chaque execution de prix.
  Les récompenses s'accumulent jusqu'à atteindre 1000 VLT.

### Enregistrement

Le `xelis_vault_miner.py` gère l'enregistrement automatiquement. Pour le
faire manuellement via le wallet RPC :

```json
{
  "method": "build_transaction",
  "params": {
    "invoke_contract": {
      "contract": "21ed1297c7ed4001a4a7c9a4bb89b10da0b0f3ad0312545a5af4a761200af207",
      "entry_id": 10,
      "parameters": [
        {"type": "primitive", "value": {"type": "string", "value": "https://mon-endpoint.com"}},
        {"type": "primitive", "value": {"type": "opaque", "value": {"type": "Hash", "value": "0101010101010101010101010101010101010101010101010101010101010101"}}},
        {"type": "primitive", "value": {"type": "u8", "value": 1}}
      ],
      "deposits": {
        "2de72ed3ea2d8ff30e6df57ba3a4d993dedfa8636d207d43d09e33615bfde2c6": {"amount": 10000000000}
      },
      "max_gas": 5000000,
      "permission": "all"
    },
    "broadcast": true,
    "fee": {"fixed": 1000000}
  }
}
```

**Paramètres :**
- `entry_id = 10` : `register_miner(endpoint, pubkey, services)`
- `endpoint` : URL publique (string)
- `pubkey` : clé publique de 32 bytes (Hash non-zero, peut être `01...01`)
- `services = 1` : oracle uniquement
- **Deposit** : 1000 VLT (100000000000 atomic) sur l'asset VLT

### Heartbeat

Le heartbeat doit être soumis toutes les 100 blocks pour rester actif.

```json
{
  "method": "build_transaction",
  "params": {
    "invoke_contract": {
      "contract": "21ed1297...",
      "entry_id": 16,
      "parameters": [],
      "deposits": {},
      "max_gas": 500000,
      "permission": "none"
    },
    "broadcast": true,
    "fee": {"fixed": 1000000}
  }
}
```

### Vérifier son statut

```bash
# Vérifier si le mineur est actif (entry 19)
python3 -c "
import requests, json
r = requests.post('http://127.0.0.1:18081/json_rpc',
  json={'method':'get_contract_data','params':{
    'contract':'21ed1297c7ed4001a4a7c9a4bb89b10da0b0f3ad0312545a5af4a761200af207',
    'key':{'type':'primitive','value':{'type':'string','value':'ts'}}
  },'id':1})
print(json.dumps(r.json(), indent=2))
"

# Voir la réputation (entry 21) — key miner_{addr}
```

---

## 4. Fournisseur de prix (oracle)

### Architecture

```
CoinGecko ─┐
            ├──► xelis_vault_miner.py ──► PriceOracle v2.1
   MEXC ───┘         │                       ├── propose_price (entry 2)
                     │                       └── execute_price (entry 3)
                     │                              │
                     │                              ▼
                     │                    XelisVaultMiner.distribute_reward
                     │                              │
                     │                              ▼
                     │                    VLTToken.mint_to (entry 4, pub fn)
                     │                              │
                     │                              ▼
                     │                    VLT minées → wallet du mineur
                     │
                     └── Heartbeat toutes les 100 blocks (entry 16)
```

### Cycle de prix

1. `xelis_vault_miner.py` récupère le prix XEL/USD depuis CoinGecko et MEXC
2. Calcule la médiane des sources valides
3. Appelle `propose_price` (entry 2) sur PriceOracle avec le prix en atomic (8 décimales)
4. Attend 3 blocks (timelock de sécurité)
5. Appelle `execute_price` (entry 3)
6. PriceOracle appelle `distribute_reward` sur XelisVaultMiner
7. Des VLT sont minées et envoyées au wallet du mineur

### Détails de l'appel propose_price

```json
{
  "invoke_contract": {
    "contract": "764ad585c2f484e54ea9dd06a7fb8b81397ba2487d37298f27edce3747d836dd",
    "entry_id": 2,
    "parameters": [
      {"type": "primitive", "value": {"type": "u64", "value": "31176300"}}
    ],
    "deposits": {},
    "max_gas": 500000,
    "permission": "none"
  },
  "broadcast": true,
  "fee": {"fixed": 1000000}
}
```

Le prix est en unités atomiques avec 8 décimales : `31176300 = $0.311763`.

### Sources de prix supportées

| Source | API | Limite |
|--------|-----|--------|
| CoinGecko | `api.coingecko.com/api/v3/simple/price` | 10-30 req/min |
| MEXC | `api.mexc.com/api/v3/ticker/price` | 10 req/s sans API key |

Le script nécessite au moins **2 sources valides** pour soumettre un prix.
Si une source échoue, le script continue avec l'autre et log un avertissement.

### Vérifier le prix oracle actuel

```bash
python3 -c "
import requests, json
r = requests.post('http://127.0.0.1:18081/json_rpc',
  json={'method':'get_contract_data','params':{
    'contract':'764ad585c2f484e54ea9dd06a7fb8b81397ba2487d37298f27edce3747d836dd',
    'key':{'type':'primitive','value':{'type':'string','value':'p'}}
  },'id':1})
d = r.json()
if d.get('result',{}).get('data'):
    price = int(d['result']['data']['value']['value'])
    print(f'Prix XEL: \${price/100_000_000:.6f}')
else:
    print('Pas de prix stocké')
"
```

---

## 5. Architecture des récompenses

### Formule de récompense

```
reward = BASE_REWARD_ORACLE × reputation_multiplier × budget_factor / 10000
```

| Variable | Défaut | Description |
|----------|--------|-------------|
| `BASE_REWARD_ORACLE` | 0.4756 VLT | Récompense de base par soumission valide |
| `reputation_multiplier` | 1.0×–1.5× | Dépend du niveau de réputation |
| `budget_factor` | 5000–20000 | S'ajuste toutes les 2 semaines |

### Niveaux de réputation

| Niveau | Score min | Multiplicateur |
|--------|-----------|----------------|
| New | 0 | 0.25× |
| Bronze | 1000 | 0.5× |
| Silver | 2500 | 0.75× |
| Gold | 5000 | 1.0× |
| Elite | 10000 | 1.5× |

La réputation augmente à chaque heartbeat valide et diminue en cas
d'absence prolongée ou de comportement abusif.

### Récompense estimée

| Mineurs actifs | VLT/jour estimé (Elite) | ROI stake 1000 VLT |
|----------------|------------------------|-------------------|
| 10 | ~55 VLT | < 2 jours |
| 50 | ~11 VLT | ~9 jours |
| 100 | ~5.5 VLT | ~18 jours |

*Basé sur budget_factor = 1.0×, heartbeat toutes les 100 blocks (~8 min),
prix proposé toutes les 100 blocks.*

---

## 6. Dépannage

### Le daemon ne répond pas

**Symptôme :** `curl: (7) Failed to connect`

```
Vérifiez que le daemon tourne :
  ps aux | grep xelis_daemon

Redémarrez-le :
  xvault --daemon
  # ou :
  /Users/adrien/xelis/xelis_daemon --network testnet \
    --dir-path /Users/adrien/xelis/data/ \
    --rpc-bind-address 127.0.0.1:18081 \
    --enable-contracts-logging
```

### Le wallet ne répond pas

**Symptôme :** `Wallet not responding`

```
ps aux | grep xelis_wallet
xvault --wallet
```

Le wallet peut prendre 1-2 minutes pour synchroniser la première fois.

### "Unexpected parameters for this method"

**Symptôme :** Erreur `UNEXPECTED_PARAMS` sur `get_info`

**Cause :** La méthode `get_info` ne prend PAS de paramètres.

```
CORRECT :
  {"method":"get_info","id":1}

INCORRECT :
  {"method":"get_info","params":{},"id":1}
```

Certaines versions du daemon acceptent `params: {}`, d'autres non.
Toujours utiliser `get_info` sans params.

### "no stable balance found"

**Symptôme :** Impossible d'utiliser des VLT/xUSD en deposit

**Cause :** Le wallet XELIS nécessite 24 blocks de confirmation (~2 min)
avant de considérer un asset personnalisé comme "stable".

**Solution :** Attendre ~3 min après avoir reçu des VLT/xUSD avant de
les utiliser dans une transaction.

### Transaction minée mais état non changé

**Symptôme :** La TX est dans un block (visible sur l'explorateur) mais
le contrat n'a pas changé d'état.

**Cause :** `max_gas` trop bas → tous les changements d'état sont annulés
silencieusement. Ou `permission` manquant → les appels cross-contract
sont bloqués.

**Solutions :**
- Vérifier `max_gas` : 500000 pour une opération simple, 5000000+
  pour un `Asset::create()`, 10M+ pour un appel cross-contract
- Ajouter `"permission": "all"` si l'entry fait des appels cross-contract
- Ajouter `"permission": "none"` si l'entry est simple

### Erreur "Chunk is not public"

**Cause :** Vous appelez un `entry` via `Contract::call()`. Les appels
cross-contract nécessitent `pub fn` (Access::All).

**Solution :** Le contrat appelé doit utiliser `pub fn` au lieu de `entry`
pour la fonction cible.

### Erreur "lowbal" sur PSM ou VaultSwap

**Cause :** `get_balance_for_asset(xusd_asset)` dans xUSD.burn_tokens
retourne le solde du contrat xUSD, pas le dépôt de l'appelant.

**Solution :** Toujours faire `transfer_contract(xusd_contract, amount, xusd_asset)`
AVANT d'appeler `burn_tokens` via cross-contract call.

### Le prix oracle ne s'execute pas

**Symptôme :** `propose_price` réussit mais `execute_price` ne fait rien

**Causes possibles :**
1. Moins de 3 blocks se sont écoulés depuis la proposition
2. Le mineur n'est pas enregistré (distribute_reward échoue silencieusement)
3. `max_gas` insuffisant pour `execute_price` (nécessite ~10M+ à cause
   des appels cross-contract)

### CoinGecko rate-limit

**Symptôme :** `429 Too Many Requests` de CoinGecko

**Solution :** Le script bascule automatiquement sur MEXC. Si les deux
sources échouent, le prix n'est pas soumis et le script réessaye
au block suivant.

### Port déjà utilisé

**Symptôme :** `Address already in use` au démarrage du daemon/wallet

```bash
# Trouver ce qui écoute sur le port
lsof -i :18081
lsof -i :18082

# Tueur le processus
kill -9 <PID>
```

---

## 7. Mise à jour & désinstallation

### Mise à jour

```bash
curl -fsSL https://xelisvault.github.io/xelis-vault/install | bash
```

L'installateur détecte l'installation existante et fait un `git pull`.
La config existante est préservée.

### Désinstallation

```bash
curl -fsSL https://xelisvault.github.io/xelis-vault/install | bash -s -- --uninstall
```

Ceci supprime :
- `~/.xelis-vault/` (config, logs, wallet, venv)
- `~/.local/bin/xvault`
- Les liens symboliques des binaires XELIS

**Note :** Votre wallet on-chain et votre enregistrement mineur ne sont
pas affectés. Pour désenregistrer votre mineur :
```bash
# Appeler deregister_miner (entry 15) sur XelisVaultMiner
```

---

## Références

| Ressource | Lien |
|-----------|------|
| Discord | https://discord.gg/vyXTVRNSyu |
| GitHub | https://github.com/XelisVault/xelis-vault |
| Explorateur testnet | https://testnet-explorer.xelis.io/ |
| XELIS Blockchain | https://xelis.io |

---

*Documentation générée le 29 juillet 2026 — XELIS Vault v5.2*
