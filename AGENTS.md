# XELIS Vault — Operator Notes (AGENTS.md)

## 🚨 FORK + ROLLBACK (2026-08-22) — chaîne canonique rétablie, redéploiement v12R

### ⚠️ FAUX MYSTÈRE "wallet cache corrompu" — résolu : c'était un revert silencieux
- **Symptôme** : soldes VLT gelés après des mints "confirmés" ; warnings
  `DAG reorg detected … deleting changes` à chaque bloc dans le log wallet.
- **Vraie cause** : un mint manuel de `2e15` atomiques (= **20M VLT**) dépassait la
  MAX_SUPPLY 10M → contrat reverté `supmax`. La tx se CONFIRME quand même (nonce
  consommé) mais ne crédite rien ; `WalletClient.invoke` brut NE vérifie PAS le
  revert (seul `Deployer.invoke` le fait via `revert_reason`). Le wallet affichait
  donc correctement 951 VLT.
- Les warnings `DAG reorg detected` sont du BRUIT NORMAL en DAG miné localement
  (coinbase admin à chaque bloc + réordonnancement topo de blocs frères) — présents
  aussi bien avant le rollback. Ne pas les prendre pour un fork.
- **Reconstruction wallet** (faite pendant le debug, utile à savoir) :
  seed récupérable via CLI interactif (`./xelis_wallet --wallet-path … --password …`
  puis commande `seed`, mot de passe redemandé). Recréation: stopper wallet,
  déplacer `db`, relancer avec `--seed "<25 mots>"`, puis RE-TRACKER les assets
  (`track_asset` VLT/xUSD) — le tracking est stocké dans le db, pas dans les keys.
  Backups: `/Users/adrien/xelis/wallet_v125/db.bak_frozen_0215`.



**Ce qui s'est passé** :
- Le nœud officiel `testnet-node.xelis.io` était **stalled à topo 155,716** ; notre daemon
  a miné une branche privée jusqu'à 174,941 (~19k blocs orphelins). Ancêtres communs
  vérifiés identiques aux topos 100k/140k/150k/155k.
- **TOUTES les déploiements v11 ET v12 sont morts** sur la chaîne canonique (audit:
  `get_contract_module` → `no contract module available` pour les 36 hash de
  deployment_state.json ET les hash v12 originaux).
- L'admin garde son historique ancien : **nonce canonique 4688**, solde **57,334 XEL**
  (vs 63,737 sur la branche forkée — la diff = récompenses minières perdues).

**Rollback exécuté** :
- Keeper tué, LaunchAgents stack+daemon déchargés, miner tué.
- Backup data dir → `/Users/adrien/xelis/data_forked_backup_*` (137 Mo).
- Resync from scratch: `./xelis_daemon ... --allow-fast-sync`
  ⚠️ **fast-sync et boost-sync sont MUTUELLEMENT EXCLUSIFS** (sinon erreur `Invalid config sync mode`).
  Fast-sync terminé en 1m37s, bootstrap metadata de 711 contrats externes.
- Daemon tourne via **nohup** (`launchctl bootstrap com.xelisvault.daemon` →
  `Input/output error`, agent à réparer). Log: `/tmp/xelis_daemon_fresh.log`.
- Miner relancé (plist `.disabled`, nohup PID ~69659): **blocs acceptés par le réseau** ✓,
  alignement vérifié local=officiel=155,746 avec hash identiques @155,744. Pas de re-fork.
  Version officielle: `1.25.0-a6ae4cd9` vs notre build patché `1.25.0-a39e295` — compatible.
- Wallet admin **redémarré obligatoirement** après rollback: il croyait nonce=0 alors que
  la chaîne attendait 4688 → `Invalid TX nonce`. Après restart, get_nonce renvoie 4688 ✓.

**Redéploiement complet "v12R" en cours** (orchestrateur deploy/deploy_v12.py) :
- État reset: docs/deployment_state.json vierge ; backup ancien état →
  docs/deployment_state_forked_0822.json.
- Fix bug deploy_v12.py phase3: `admin_addr` indéfini → remplacé par `ADMIN` import.
- Les hash v12R sont consignés au fil des phases dans docs/deployment_state.json +
  section « v12R REDEPLOY » ci-dessous.

## 🔧 FIX v12R — VLT max supply visible protocole (2026-08-22)

L'asset VLT du premier passage v12R a été créé avec `MaxSupplyMode::None` → l'explorer
affichait "no max supply" (le cap 10M n'existait qu'au niveau logique contrat, clé `ms`).

**Fix**: `contracts/token/VLTToken.slx` create_asset →
`MaxSupplyMode::Mintable { max_supply: MAX_SUPPLY }` (=10_000_000 VLT @8dp).
⚠️ Syntaxe Silex: variante avec payload = style STRUCT `Mintable { max_supply: X }`,
PAS `Mintable(X)` (erreur `unexpected type 'MaxSupplyMode'`).
Bytecode recompilé → /tmp/deploy_VLTToken.hex ; entry chunks 4–27 inchangés.
Redéploiement complet relancé depuis la phase 1 (registry neuf ⇒ noms libres).
Ancien état partiel archivé: docs/deployment_state_v12R_partial_maxsupply0.json.
xUSD reste volontairement en MaxSupplyMode::None (stable adossé au collatéral).

## ✅ Tests E2E v12R (2026-08-23, passe complète)

| Flow | Résultat | Notes |
|---|---|---|
| PSM.mint / redeem | ✅ | redeem exige le **contrat xUSD financé en xUSD** (burn depuis SA balance, pattern v12.1 confirmé). Refill: invoke idempotent `xUSD.set_registry`(13) + dépôt attaché |
| VE3 deposit→borrow→repay→withdraw | ✅ cycle complet x2 | health checks validés (2 `unhealthy` correctement levés). COUNTER "n" démarre à 1 → vault#1 = premier |
| SavingsRate deposit/withdraw/claim | ✅ | |
| VaultSwap create_pool/add_liq/swap | ✅ | `cbtrip` = circuit breaker TWAP (max_vol 1000bps) → pour 1er swap sur pool neuf: set_max_volatility_bps(32) temporaire |
| PrivacyMixer deposit ×3 + auto-mix | ✅ | mix auto au 3e dépôt (threshold=3). refund impossible en test: timeout min 17280 blocs (1j) |
| Faucet.distribute | ✅ | **chunk 6** (16=set_guardian!). Arrays RPC: `{"type":"object","value":[val,…]}` |
| GovernanceVault stake/unstake | ✅ | stake ids démarrent à 0; unstake avant lock → "locked" (correct) |
| FounderVesting claim | ✅ | "cliffnotpassed" (correct) |
| MinerDelegation.register_profile | ✅ | `(name:str, description:str, commission_bps:u64)` |
| VaultChat.register_session | ✅ | |
| Oracle prix réel + heartbeats providers | ✅ | $0.2165, rewards protocole XEL reçus par providers (+45 XEL chacun) |

### 🔧 Fixes appliqués pendant la passe
1. **PSM.set_oracle(23) + VS.set_oracle(37) manquaient** → ajoutés à deploy_v12.py
   phase5. Sans eux: PSM.mint revert `err`, swap sans prix.
2. Encodage JSON-RPC des arrays (Silex): variante **`object`** avec value=list de
   ValueCells (`{"type":"object","value":[…]}`); variantes RPC acceptées:
   primitive/bytes/object/map UNIQUEMENT.
3. Maturité balances chiffrées ~60 blocs APRÈS chaque mint — les attaches de
   dépôts échouent (`lowbal`/proof error) si on réutilise des fonds tout frais.

## ✅ Reconfiguration post-v12R (2026-08-23, complète)

| Élément | État |
|---|---|
| Config oracle/miner | hsb=500 (chunk 56), hi=900 (34), ht=4000 (35) ✓ |
| Faucet | VLT wiring (12/13), claims 100XEL+100VLT (7), financé **40k XEL + 500k VLT** ✓ |
| Providers p1/p2/p3 | fund 1100 VLT + 5 XEL chacun → `register_miner` (15) stake 1000 VLT mask=1 ✓ |
| PSM réserve XEL | **100 XEL** via invoke get_reserves_entry(10)+deposit ✓ |
| protocol.py | VLT/XUSD assets + 36 CONTRACT_HASHES v12R ✓ |
| cli_backend.py | _FALLBACK régénéré depuis deployment_state.json ✓ |
| Keeper oracle | nohup `scripts/oracle_keeper3.py`, **prix réel** CoinEx+MEXC médiane $0.2107, submit x3 OK, feed `fg_0=[21070000,…]` ✓ |

⚠️ Pièges rencontrés (NE PAS REFAIRE):
- `Faucet.refill_vlt` (chunk 5) prend **1 param u64** ET le transfert se fait en attachant
  le dépôt au même invoke (l'entry ne fait qu'émettre l'event).
- Pour créditer un contrat en XEL/VLT: invoquer n'importe quelle entry **sans param**
  du contrat cible (ex chunk 10 get_reserves_entry pour PSM) avec `deposits={…}`.
- Les warnings wallet `DAG reorg detected … deleting changes` sont normaux en DAG
  miné localement — voir section « FAUX MYSTÈRE » ci-dessus.

## ✅ v12R REDEPLOY — hash définitifs (2026-08-22, après fix max supply)

| ContractRegistry | `19161543b9e5aef00c5a3e226058b946d847c78941f0c89e9b996c6332204970` |
| ComplianceModule | `1c0f143207c24d3b3e7fd04000cd1425e498505171de45ca980238e9f71c7f4a` |
| VLTToken | `020f228fbd61e3a6cd2d570083e14c02f7073f293c79ee4059359b896e217d84` |
| xUSD | `4836190ca2f2278cfc3e8ad8c7e05bbd0070de253c64615f6eea2c19885063a1` |
| FaucetContract | `0169707c19522269e8126edf36066e2c83c384e8c31f8072667f7cfad06631ec` |
| XelisVaultMiner | `6c70647e233dd634aa05cd6bdca06b521947c4c682d7decac0700d8a79d4b024` |
| StakedOracle | `e89bc25043c320fdac9c2030bc99e4b5bd94c9e0043132d10f66cd93576fa515` |
| MinerPool | `de744e0ccf45252070eb8fe83d0d16d36736ab7af1014a69405f358fb63c439b` |
| InterestRateModel | `e9f716b07628fb8793adf3e20142348082a5021d671f316dad1e02cfb70f9c6d` |
| VaultEngineV3 | `844cab735a8156f55c3055c2ff56a6824ad6d55b32f7dfb866655bde2bfa2054` |
| SavingsRate | `139caff55ca74911eb0c2631e5aab623a53ee56c7b24143328ecef3a610a9738` |
| FlashCallback | `a84fc6d305b4ed1a6e15c310461799172272ec1cabf209316e724c3ede420f40` |
| FlashLoan | `f8505eb95c5bb070e4f2a7f2d80826e13d140d2ee03b6bfdfaf1b7772c4be9f4` |
| VaultSwapV2 | `5defc37154200f1cabb5b5fa43510565ab791e34b20f2cf4132ec7d9ac4e2041` |
| PSM | `977ddf73305dd21c29ffbe69dc2bdb29a12a62f4ff8bbc3140cafd4b51d5c2e1` |
| LendingMarket | `cb8f489382368b2f1b27bffcba346ede50aa180ebefac89ac444995bc95255bc` |
| PeerLoan | `ec1ed4f280fef7cd7b13cb0231be12cfb53ddc57b38eaa822e00497221d82d36` |
| SyndicatePool | `5980cbd860081e613d32fd86d1c474fd798c8a7da262177078ad2eeb8dcb5cb0` |
| SealedBidAuction | `ac0c5a4e22a8348d3e98ff6183fdab23117f06f4a154098c1d7c84b24c3097f5` |
| PrivacyMixer | `d54cc19be3d16a86a3849be4389e44a9c123ebb0042a88e94f4e91893f940ab8` |
| AssetVault | `d16f7671f3e5399e1da826f9c4743f6fd5161e54048c945da6bea25d1032ff64` |
| TreasuryVault | `01d3851249e13354465766306e65be15497a9a9df6f46e35fe417879c4a5ab84` |
| RevenueShare | `49c363dae4d32473d6d3c26ce0482cf735f7d656c665094002c1d21a6978c94b` |
| Payroll | `44ce12fb3d143f360c84664fe4849f01fb31ce5b45aebda38b037c70b4079b30` |
| GovernanceVault | `52cb2f100984319c7f41bbec03fb3e7679279eafdd4abb44ff5d8fdd7631cf97` |
| Timelock | `b925d8e30ccd7bcffdc1376a6aecd8daaaa71603a3d0a4c9413d9e4a8ed11082` |
| GuardianMultisig | `9792a5894877a5982c9efdfb91f94c1536fe5f21c017a56c59691776413e4929` |
| Governor | `608eec92282bcba466e88d7e70d616be5653e9a120997866d738838e783862c3` |
| OracleGovernance | `bab86ca4a01c3250ce90b5c5d569b87ab221a212321848e104eb89500c28c953` |
| VLT asset | `3f1f9a3c0a90a0a548670a069e8edad5c0c20914b20b289426b2857c6715f58f` |
| XUSD asset | `be39794c4a32f231d410c8be3a4d9e80455c667d902c5edf8527dea52533356e` |



## ⚠️ LEÇON N°1 — get_deposit_for_asset est TRANSITOIRE (par-tx) — v12.1

Découverte clé du 2026-08-22 (validée par contrats probe déployés) :

- `get_deposit_for_asset(asset)` ne voit que les deposits passés **dans le MÊME tx**
  que l'entry exécutée. Retourne `None` sinon → `.expect("err")` panique `"err"`.
- Un « pré-dépôt » fait dans un tx SÉPARÉ crédite la **balance du contrat**
  (`get_contract_balance` l'affiche) mais **PAS le tracker per-caller**.
- `transfer_contract(A→B)` ne crédite PAS non plus le tracker du caller chez B :
  tout pattern « forward puis re-lecture du dépôt » cross-contract est **impossible**.

### Patterns qui FONCTIONNENT (validés on-chain)
```python
# PSM.mint (chunk 8) — deposit intégré au MÊME invoke :
p.wallet.invoke(PSM, 8, [val_u64(xel_amt), val_u64(min_out)],
                deposits={"0"*64: {"amount": xel_amt}})
# PSM.redeem (chunk 9) — idem avec l'asset xUSD en deposit
```
✅ mint 0.0595 xUSD + redeem 800k raw testés OK sur v12.1 (admin).

### Patterns CASSÉS en v12.1 (fix code requis en v12.2)
- `VaultSwapV2.psm_mint/psm_redeem` → `PSM.mint_cross/redeem_cross` : mint_cross
  relit `get_deposit_for_asset` alors que les fonds arrivent par `transfer_contract`
  → panic `"err"` systématique. Fix: lire `get_balance_for_asset` dans *_cross,
  ou faire porter le dépôt par le tx d'origine et ne plus relire.
- `PSM.redeem` : `burn_tokens` (chunk 5) brûle depuis la balance du **contrat xUSD**
  (pas du dépôt PSM). Workaround testnet: financer le contrat xUSD en xUSD
  (invoke entry quelconque + deposits). Fix propre: `transfer_contract(xusd_hash, …)`
  avant `call(5)` dans redeem.
- Dépôts orphelins: les pré-dépôts ratés ont laissé ~8 XEL de réserve dans PSM
  (utile pour les redeems, comptabilisé comme réserve).

## 🔧 Config oracle/miner ajustée on-chain (2026-08-22, admin)

| Clé | Contrat | Ancien | Nouveau | Entry |
|---|---|---|---|---|
| `hsb` hard_stale | StakedOracle | 100 blocs | **500** (~22 min) | chunk 56 |
| `hi` hb_interval | Miner | 100 | **900** | chunk 34 |
| `ht` hb_timeout | Miner | 300 | **4000** | chunk 35 |

Keeper (`scripts/oracle_keeper3.py`) recalibré économie:
- submit_price + poke `aggregate_now` toutes les **300 blocs** (~13.5 min < hsb)
- heartbeats toutes les **1000 blocs** (~45 min, entre interval 900 et timeout 4000)
- fee fixe **0.001 XEL/tx** (wallet accepte jusqu'à 0.0001; marge ×10)
- burn total ≈ **0.4 XEL/jour pour les 3 providers** (avant: ~8 XEL/h !)
- jitter ±1% (spread < max_dev 500bps), top-up providers: 50 XEL chacun le 08-22

## 🐛 Deadlock alreadysub (design oracle)

Si TOUS les miners soumettent avant l'ouverture de la fenêtre d'agrégation,
personne ne peut re-déclencher `try_aggregate` (le check `alreadysub` précède)
→ cycle bloqué indéfiniment (`sc_N=3`, cy figé). Le keeper poke donc
`aggregate_now` (chunk 17, sans access-control) AVANT chaque round de soumissions.
Fix contrat possible: déplacer try_aggregate avant le check, ou entry publique dédiée.

## 🧪 Résultats tests flux v12.1 (2026-08-22, admin wallet)

| Flux | Statut | Notes |
|---|---|---|
| Oracle E2E (submit→agg→rewards VLT) | ✅ | fg_0 frais chaque cycle keeper |
| PSM.mint XEL→xUSD | ✅ | 0.0595 puis +10.0485 xUSD (deposit même tx OBLIGATOIRE) |
| PSM.redeem xUSD→XEL | ✅ | nécessite xUSD contract financé (voir bug burn) |
| VE3 deposit/borrow/repay/withdraw | ✅ | CYCLE COMPLET vault#1: 2 XEL collatéral, borrow 0.03, repay full, withdraw OK |
| VaultSwap create_pool / add_liquidity / swap | ✅ | pool XEL/xUSD 0.4:1.98 @ prix oracle; swap 0.002 XEL OK |
| VaultSwap.psm_mint / psm_redeem | ❌ | bug forward+re-read → v12.2 |
| SavingsRate deposit/withdraw | ✅ | 0.015 déposé, 0.01 retiré |
| Faucet refill/set_claim_amounts/distribute | ✅ | claim réduit à 1 XEL + 5 VLT/user (default 100 XEL trop gros) |

### Pièges rencontrés pendant les tests (NE PAS REFAIRE)
- **Unités prix**: oracle 4,950,000 raw = 0.0495 $/XEL → 203 XEL ≈ 10 xUSD
  (PAS 2 !). min_out en RAW xUSD 8dp.
- **VaultSwap CB**: `toobig` = swap > max_swap_pct du pool; `cbtrip` = écart
  prix exécution vs TWAP > max_volatility_bps (default 1000). Sur un mini-pool,
  même 5% du pool trip le CB → swiper ≤1% du pool ou élargir la config (entry 32).
- **Address[] en paramètre RPC**: format tableau ValueCell =
  `{"type":"object","value":[val_addr(x), …]}` (ValueCell::Object(CellArray),
  xelis-vm/types/src/values/cell/mod.rs; Map = paires clé/valeur, PAS un tableau).
- **Lire une valeur retournée par un contrat**: la faire `return` depuis une
  entry probe → visible dans get_contract_logs champ `exit_code`.
- **Maturité UTXO ~60+ blocs**: après chaque mint/gros crédit, attendre ~4 min
  avant de re-déposer ("not enough funds … available: X" au BUILD).
- **VE3**: COUNTER_KEY="n" démarre à 1 → premier vault = v_1; repay brûle
  depuis le solde du contrat xUSD (comme PSM.redeem) → financer xUSD contract
  avant gros repay; treasury=admin ⇒ fees récupérées par l'admin au borrow.
- **Faucet**: refill_xel=4, distribute=6 (Address[] format object);
  defaults claim 100 XEL/user → set_claim_amounts(7) recommandé.

## 🛠️ Techniques de debug contract (éprouvées)

- `get_contract_logs {caller: <tx>}` montre `exit_error` mais **sans localisation**.
- **Contrats probe** = meilleur bissecteur : déployer un mini-.slx qui appelle
  directement le chunk suspecté (ex: `/tmp/probe_minter.slx` a validé xUSD chunk 4).
  - Compile: `xelis_compile_tool <in.slx> <out.hex>` (chunk map sur stderr)
  - Deploy: build_transaction `deploy_contract` fee 1e8, hash = tx hash
  - `set_minter(Hash, bool)` prend **2 params** (hash + enabled)
- Balance asset wallet: RPC wallet `get_balance` avec `params: {"asset": <hash>}`
  (sans params = XEL total).
- **Maturité UTXO**: xUSD fraîchement minté non spendable pendant ~60+ blocs
  → attendre ou tester des montants réduits.
- Daemon n'expose pas le revert reason via get_transaction; passer par logs/probe.

## Live Environment

- **Network**: testnet (block_version 6 → allows V0|V1; V7 will allow V1 only). Daemon v1.25.0 (`1.25.0-a39e295`, built from local `~/opencode/xelis-blockchain`).
- **Daemon RPC**: `http://127.0.0.1:18081/json_rpc` (no auth)
- **Wallet RPC**: `http://127.0.0.1:18082/json_rpc`, basic auth `wallet:testpass`
- **Admin**: `xet:czr9q8k5xlzqdptq7n2vapyjfduldts6tw3e6apl99vknzvmu4zsq8z9j8v`
- **Processes (post-rollback 2026-08-22)**: daemon `./xelis_daemon --network testnet --dir-path /Users/adrien/xelis/data/ --rpc-bind-address 127.0.0.1:18081 --allow-fast-sync` via **nohup** (LaunchAgent `.daemon` cassé: `Input/output error`). Miner 8 threads via nohup (blocs acceptés par le réseau officiel ✓). Wallets admin 18082 + providers 18086/18087/18088 tournent en continu et se reconnectent au daemon. LaunchAgents: `com.xelisvault.daemon`, `.stack`, `.keeper`, `.miner.plist.disabled`, `.provider18082/18084/18085`. **Unloaded the keeper+providers on 2026-08-20 (they spammed StakedOracle entry 16 submit_price → `alreadysub` every block, flooding the mempool and blocking admin txs from confirming). Restart only after fixing the subscribe-once logic.**
- **Wallet nonce**: after a daemon restart or chain rollback the wallet's stored nonce lags (ou diverge) ; restart le wallet puis vérifier `get_nonce` == nonce attendu par la chaîne avant tout build. Pendant les déploiements, poll `get_nonce` entre txs.
- **Deployment helper**: `/tmp/deploy_ops.py` (`deploy()`, `invoke()`, `get_data()`, `val_*` value builders).
- **Block time**: ~2.7s. Wait 5–12s between sequential TXs (proof-verification race → `Proof verification error`); nonce race → `Invalid TX ... nonce, got X expected Y` — both fixed by sleeping and retrying once. "Contract not found" right after deploy → wrong hash or too soon; cross-check with `cur_<Name>` in the registry.
- **Registry (ContractRegistry `840b81...`)**: register (entry 3) is ONE-WAY per name (`exists` revert); upgrade (entry 4, admin) enforces 720-block cooldown (`UPGRADE_TOPO_PREFIX`, unlock = register topo + 720). Upgrades preserve `prev_<Name>` for rollback. Names registered (count 33): ContractRegistry, ComplianceModule, VLTToken, xUSD, FaucetContract, XelisVaultMiner, StakedOracle, MinerPool, InterestRateModel, VaultEngine, SavingsRate, FlashLoan, FlashCallback, **VaultSwap** (not "VaultSwapV2"), PSM, LendingMarket, PeerLoan, SyndicatePool, SealedBidAuction, PrivacyMixer, AssetVault, TreasuryVault, RevenueShare, Payroll, InsurancePool, PrivateInsurance, GovernanceVault, Timelock, Governor, GuardianMultisig, OracleGovernance, VaultChat, FounderVesting4y, FounderVesting10y, FeeDistributor, MinerDelegation.
- **Current `cur_<Name>` hashes (registry authoritative, 2026-08-21)**:
  - VaultEngine: `4c10cf5f37b77c31a099819cf13bde43fe45e374fcf13c5c5f7578978ef969c9`
  - PSM: `3456fc47707447403b2bff56d8052e706575665d79fcf121c930d068ba1e6d11` (mint works; redeem fixed in source - `burn_tokens` called directly)
  - VaultSwap: `dbff590caeb56d7d287279772a322ef62170616abfafa24f7a0bf2d2262a02c7`
  - PrivacyMixer: `534c86a90ee1acac2da96b786fe00311d2e176608488668220c8bef9e96825bb`
  - SavingsRate: `5839e0158fb0965030b7a8575b4db38c22b6d69a3f0bb6262f322db9a07f55b0` (reentrancy fixed: `release_reentrancy()` added)
  - GovernanceVault: `65138ab138ff0f3a73852b54767e23b84c20a110bc62f59ca09b678eaef71d56`
  - InsurancePool: `bc74bae34e763895ed5795ba540ba1e60926777782b84b9d815707835962b8da` (newly deployed 2026-08-21, ADMIN_KEY=`adm`, configured & registered)
  - xUSD: `87242c12262bf4d7144842a06e91d96af53e5ce5b786e10ccb5c687be4658ae8`
  - xUSD asset: `a04b10a46698c97f3e465882dee5827e62360c30060f33f3604179769bc65100`
  - StakedOracle v3: `159594c8a5a856c9bc1063271ce8930500f1cab6fcc0e2bf604c78561ec09605`
  - Registry: `840b810c32f24b516ba5d65accef8cb706355e076a2c41ea98f2afce009f1a14`
- **VaultEngineV3 config**: set_registry=40, set_xusd_contract=41, set_xusd_asset=42, set_treasury=43 (Address). **xUSD perms (chunks 18=set_minter, 19=set_burner; set_minter also sets bu_)**: registered True for VaultEngine `4c10cf5f...`, PSM `3456fc47...`, VaultSwap `dbff590c...` (2026-08-20). Without burner → `notburner` on repay/redeem; without minter → `notminter` on mint_split (skip only if caller == xUSD admin).
- **StakedOracle (v3) config**: set_registry=46, set_miner_contract=44, add_feed_entry=10, pause=34 (All, not 33). Miner `register_service` entry 31 takes service_id **1..=8** (`0` → `badservice`); stored key `svc_<contract_hash.to_hex()>` = service id. Oracle holders set_oracle: VaultSwap=37, PSM=23, LendingMarket=29, PeerLoan=15, SyndicatePool=19 (all point to v3).
- **Treasury notes**: all `set_treasury` setters take an **Address** (temp = admin) EXCEPT FeeDistributor (Hash → TreasuryVault). TreasuryVault is a contract (hash) → cannot be set via Address-typed setters; fees accrue to admin wallet until a future fix. TreasuryVault has NO set_registry (guide stale); constructor sets admin+1 signer+quorum 1. RevenueShare `set_vlt_asset` is actually `set_share_token` (entry 8).
- **Contract funding**: mint paths (VLTToken.mint_to_entry=27, xUSD) take Address — to fund a CONTRACT, invoke any of its entries with `deposits: {"<asset_hash>": {"amount": N}}` (ContractDepositBuilder shape; plain int is rejected). Verified on FounderVesting (500k VLT each).
- **VaultChat**: `set_miner_contract`/`set_registry` are pub-fns (All chunks) — NOT externally invokable; miner reward wiring needs the Governor/Timelock proposal path (Timelock.submit_proposal/execute can cross-contract-call All chunks). No registry reference exists in VaultChat.
- **MinerDelegation** (entry set_miner_own_stake=14) is only_miner_contract — configurable only from miner flow. Miner register_service (31) ids: 1=oracle, 2=chat (CHAT_SERVICE_ID), 0 → `badservice`; key `svc_<contract_hash>`.
- **VM patch (CRITICAL)**: `ExitValue::is_success()` in `xelis_common/src/contract/vm.rs` returns `true` for all `ExitCode` (not just 0). Non-zero returns from entry points are **values** (ids, amounts), never errors. Errors use `require()` → `ExitError`. Applied 2026-08-20, daemon rebuilt & restarted.
- **PSM fix (2026-08-21)**: `redeem` now calls `burn_tokens` (chunk 5) directly instead of `transfer_contract` + `call(5)` — the caller's deposit is already in PSM balance. Redeem works for small amounts (< PSM XEL reserve).
- **InsurancePool (new 2026-08-21)**: deployed `bc74bae3...`, ADMIN_KEY=`adm` (was `a` conflicting with ASSET_KEY), set_asset=xUSD, set_registry=REG, registered as cur_InsurancePool. Stake/unstake work.
- **SavingsRate fix**: `release_reentrancy()` added before `return 0` in deposit/withdraw (reentrancy guard was stuck on `RG_ENTERED`).
- **FaucetContract fix**: `distribute` entry is chunk 16 (not 6), takes `Address[]` via sequence ValueCell.
- **VM nonce sync**: `WalletClient.invoke` waits for wallet nonce to catch up to daemon nonce before building, then waits for nonce advance after confirm.
- **xUSD UTXO maturity**: freshly minted xUSD not spendable immediately (~60+ blocks / ~3 min). Tests use 180s waits and partial amounts.

## Compilation

- Tool: `/Users/adrien/opencode/xelis-compile-tool` (`cargo build --release`, binary `./target/release/xelis_compile_tool`).
- Output hex now = **complete ContractModule** (version byte `01` + module serialized with V1 writer context). Do NOT prepend bytes — deploy as-is.
- Compile env = `build_environment::<DummyProvider>(ContractVersion::V1)`.
- Compile log (stderr) prints `chunk N: <Access>` list → source of truth for entry chunk indices.

## CRITICAL: entry_id = compiled chunk index

`entry_id` in wallet invokes is the **chunk index in the compiled module**, NOT the
source-order counter in `docs/ENTRY_IDS.md`. Chunk layout: hook 0 first, then internal/helper
chunks, then Entry chunks, then All chunks. Indexes differ per contract — always read the
compile log or `docs/entry_chunk_ids.json` (auto-generated map, all 51 contracts, 959 entries).

Example: ComplianceModule `set_registry` = chunk **14** (source order 9). Calling chunk 9
hit `update_merkle_root` → reverted with `notverifier`.

## Wallet RPC (v1.25.0) — build_transaction

Flattened `TransactionTypeBuilder`, **snake_case** keys at top level of params:

```json
{
  "deploy_contract": { "contract": "<hex>", "invoke": { "max_gas": 1000000 } },
  "fee": { "fixed": 100000000 },
  "broadcast": true
}
```

- If the module has a constructor (hook 0), `invoke` is **required** (else `INVALID_CONSTRUCTOR_INVOKE`). No constructor → omit `invoke`.
- Constructor params are NOT supported by DeployContractInvokeBuilder (only max_gas + deposits) — constructors must be param-less.
- Contract hash = deploy transaction hash (confirmed via `ContractDeployEvent`).
- Invoke: `"invoke_contract": { "contract": "<hex>", "max_gas": N, "entry_id": <chunk index>, "parameters": [...], "deposits": {}, "permission": "all" }`.
- Fee guidance: deploy `{"fixed": 100000000}`, invoke `{"fixed": 10000000}`. Gas: 1M for stores, 5M+ for cross-contract / heavy.
- Old (v1.22.2) wallet: enum key `"DeployContract"` + object `{"version","module"}` — obsolete, do not use.

## ValueCell JSON (adjacently tagged)

- u64/u128: `{"type":"primitive","value":{"type":"u64","value":"<decimal string>"}}`
- u8/u16/u32: `{"type":"primitive","value":{"type":"u8","value":1}}` (number)
- bool: `{"type":"primitive","value":{"type":"boolean","value":true}}`
- string: `{"type":"primitive","value":{"type":"string","value":"..."}}`
- Hash: `{"type":"primitive","value":{"type":"opaque","value":{"type":"Hash","value":"<hex>"}}}`
- Address: `{"type":"primitive","value":{"type":"opaque","value":{"type":"Address","value":"xet:..."}}}`
- bytes: `{"type":"bytes","value":"<hex>"}`
- Same shape for `get_contract_data` keys (daemon).

## Daemon RPC reads

- `get_contract_data` `{contract: <hash>, key: <ValueCell>}` → `{data: <ValueCell>, topoheight, previous_topoheight}`; `No data found with requested key` = key never set.
- `get_contract_logs` `{caller: <tx hash>}` → `exit_error` entries reveal reverts (e.g. `notverifier`). Sometimes transient "Data not found on disk" right after execution — retry after a few seconds.
- `get_contract_module`, `get_contract_balance` available. NO simulation/invoke dry-run method on daemon RPC.

## Deployment guide

- Order + config steps: `docs/DEPLOYMENT_GUIDE.md` (13 phases, 37 core contracts; +14 brainstorming contracts exist in repo, 51 total).
- After EACH deployment/config: update `docs/DEPLOYMENTS.md`, commit to GitHub.
- Record tx hashes as contract addresses. Verify state via `get_contract_data` after each config step.

# v11.5 BUILD LOG (Super Z audit fixes applied + compile fixes)

## Compilation status — 34/34 core contracts OK (commit adb13f0 + local fixes)

Fixes applied on top of adb13f0 (Silex requires fn/const defined BEFORE use; len() returns u32):

1. **AirdropTracker.slx**: moved `fn build_leaderboard_index` before `entry finalize_distribution`
   (was called at line 623, defined at 721 → "No matching function found").
   Also: `require(!s.load(K).unwrap_or(false))` split into typed let + require;
   `emit_event(... s.load(QUALIFIED_COUNT_KEY).unwrap_or(0).to_string(...))` split into typed let.
2. **FeeDistributor.slx**: moved `fn is_authorized_fee_source` before `fn only_protocol_contract`;
   loop var `let i: u64` → `u32` (names.len() is u32).
3. **VaultChat.slx**: moved `const RELAYER_BOND_PREFIX` + `const MIN_RELAYER_BOND` from line ~2229
   to top constants section (used at line 521 by set_relayer F-13 fix).
4. **FaucetContract.slx**: `xel_amount * addresses.len()` → `* (addresses.len() as u64)` (2 sites).

AnalyticsCollector NOT in the 38-core deploy list (DO NOT DEPLOY YET) — left untouched.

## Next: regenerate docs/entry_chunk_ids.json for the 34 core contracts, then deploy
## per docs/DEPLOYMENT_GUIDE.md phases 1–8,10–13 (Phase 9 Insurance SKIPPED per owner).

## ✅ Chunk map régénéré (docs/entry_chunk_ids.json)
34 contrats core, 1031 chunks Entry/All mappés depuis le compile tool (sortie sur STDERR,
pas stdout — piège subprocess). Bytecodes dans /tmp/deploy_<Name>.hex et /tmp/chunkmap_<Name>.hex.

## PROCHAINE ÉTAPE: déploiement phases 1-8, 10-13 (Phase 9 Insurance SKIPPED)

# v12 FULL REDEPLOY (v11.5 code) — en cours
Orchestrateur: deploy/deploy_v12.py (--phase N), état: docs/deployment_state.json.
AirdropTracker patché v11.6: set_authorized_recorder(Hash,bool) + only_authorized_recorder
via get_contract_caller()/to_hex() (l'ancien check Address ne pouvait jamais matcher un contrat).
PHASE 1 ✅ ContractRegistry=ec60bb78…83194 | ComplianceModule=3eb327fd…69ed (+set_registry ok)
PHASE 2 ✅ VLTToken=0b0f5cfb…9524 VLT_ASSET=daa3981d…f387d | xUSD=8154335a…771c8 XUSD_ASSET=0daf60ef…ac85c | Faucet=0baaa0c6…36d5a
⚠️ Bug substring dans deploy_v12.py extract_new_asset — state XUSD corrigé à la main. NE PAS réutiliser tel quel.
PHASE 3 ✅ Miner=ba27f8e6…af3e7 Oracle=15247c0a…9f27 (+feed XEL/USD svc1) MinerPool=ee96c17b…73c35
deploy_v12.py: invoke() resumable via STATE["steps"] (label@contract12). Fixes: val_u8 decimals, register_service(u8,hash).
PHASE 4 ✅ IRM=3ccdfce4…068c(rates 50/1000/5000/8000) VE=b916b7a4…5ec9(minter+burner xUSD) Savings=4841e688…1c88(minter) FL=a9d2c504…e4bb CB=8cae8f57…bcdb4(+set_flash_loan chunk4 ajouté au script)
VE: oracle résolu via registry "StakedOracle" — pas de set_oracle.
PHASE 6 ✅ LendingMarket=01c57670…bda2 PeerLoan=132e270d…0942 SyndicatePool=4a04cdc0…6e1b
⚠️ Pas de set_irm sur LM v11.5 (IRM par pool dans create_pool) — écart vs guide documenté.
PHASE 11 ✅ VaultChat v11.6=0bfc1b24…2097 (nouveau chunk set_vlt_asset=96; ancien 1be87b9e… abandonné)
Admin wallet: 700 000 VLT (airdrop testnet, distribution manuelle). Relayer bond 100 VLT (double stake cosmétique).
VLTToken.mint_to_entry=27 ; wallet doit tracker l'asset avant tout dépôt VLT.
PHASE 12 ✅ FV4y=7e64b686…abec(⚠️1M VLT, excès 500k verrouillé) FV10y=b4f48448…fd04(500k) FeeDistributor=fb26448c…95df MinerDelegation=1a7723fe…90f6f
phase12 patchée: instances par hash explicite (cache deploy() fusionnait les 2 vestings).
PHASE 13 ✅ AirdropTracker v11.6=e1f0ec8f…eb8d1 + 7 recorders (Hash) — DÉPLOIEMENT COMPLET
protocol.py: VLT/XUSD assets + 37 CONTRACT_HASHES v12. docs/DEPLOYMENTS_V12.md complet.

# INCIDENT 2026-08-23 ~09:30-10:40 — "fork" testnet: nœud officiel GELÉ, pas nous
Symptôme: explorer/officiel figé à topo 170999 (37a286a7) pendant que notre daemon avançait (171962+).
Diagnostic: dernier bloc commun = 170999 EXACTEMENT (get_block_at_topoheight, PAS get_block qui n'existe pas).
Le nœud officiel refuse TOUT depuis 171000: blocs vides ET transactions (mempool=0 malgré 31MB envoyés).
Bloc 171000 = bloc vide sans tx → rien d'empoisonné, leur node est gelé/buggé en interne.
Le testnet dépend de notre hashrate: sans nos blocs la chaîne publique est à l'arrêt total.
Décision: rester sur NOTRE branche (plus lourde), miner+keeper relancés dessus.
Dès que le node officiel débloquera, le DAG convergera vers la branche la plus lourde = la nôtre.
Vérif convergence: comparer hash get_block_at_topoheight(171000) local (d76f76c1…) vs officiel.
État critique safe des deux côtés: tous les déploiements v12R + config sont ≤170999.
Seules les txs post-170999 seraient à rejouer si un jour on abandonnait notre branche (non prévu).
RPC daemon utile: p2p_status (best/median/our_topoheight), get_peers (bytes_recv/sent).
Miner PID nohup /tmp/miner.log; keeper nohup /tmp/oracle_keeper.log (plist .keeper obsolète, ne pas utiliser).

# RÉSOLUTION SYNC 2026-08-24 — daemon aligné via fast-sync + monitor auto-reset
Cause racine du blocage genesis-resync: txs historiques testnet à preuves ZK invalides selon code actuel
(bloc 42865 tx e50b4d30… nonce 324, puis nonce-drift be4eeec1… @47k). Aucun full-resync possible.
Solution finale (choix owner): daemon compilé depuis commit EXACT a6ae4cd9 (branche dev = leur build 1.25.0,
master est resté étiqueté 1.24.0!) + DB vierge + --allow-fast-sync vers 74.208.251.149 → aligné instantané.
⚠️ Le n° de version du binaire DOIT matcher le node officiel (get_info.version).
Monitor permanent: scripts/sync_monitor.py (nohup, log /tmp/sync_monitor.log) — compare local↔officiel
chaque minute; fork/stall persistant → wipe data/testnet + re-fastsync auto (cooldown 20 min).
Superviseur PTY dispo si commandes prompt nécessaires: /tmp/daemon_pty.py + echo cmd > /tmp/dcmd.
Miner/keeper/wallets: relancer SEULEMENT une fois le node officiel dégelé et stable.

# ✅ VaultChat E2E + RELAYERS — 17/17 PASS (2026-08-24) + BUG FIX v12R-2

## Bug critique trouvé par les tests → corrigé et redéployé
- `add_group_member` stockait la clé chiffrée à `gm_<gid>_<addr>` alors que
  `store_group_message` charge un BOOL au même préfixe → toute publication membre
  = VM type error "Expected a value of type Bool". Le getter `get_group_member_key*`
  chargait en plus un `Hash` (3e type sur la même clé).
- **Fix v12R-2**: nouveau const `GROUP_KEY_PREFIX="gk_"` pour les clés chiffrées;
  `gm_` = bool membership strict. Getters retournent `string` (hex, "" si absent).
  Chunk map INCHANGÉE (vérifiée: 7/8/9/11/15/20/48/51/56/66/95/96/121 identiques).
- **Nouveau hash VaultChat**: `73f7b78bef94c20a5115f8fdc9ed2cd8d8792cdb398f01a7f254163b30958e24`
  (deploy tx). Registry UPGRADE entry 4 utilisé pour la 1re fois: cur_VaultChat→nouveau,
  prev_ préservé ✓ (cooldown ne s'appliquait pas: jamais upgradé avant).
- Config nouvelle instance: set_vlt_asset(96)=VLT ✓, set_treasury(95)=admin ✓.
  ⚠️ claim_relayer_fees revert "notset" tant que treasury non configuré!

## Suite scripts/test_chat.py (17 assertions)
Sessions admin+p1 (+read-back) | create_group id0 + gc=1 | add_group_member p1
(+gm_=true) | store_group_message par le MEMBRE ✅(grâce au fix) | anchor_messages
admin (merkle/count/senders/type u8) | Relayer p2: stake_relayer_bond 50 VLT
(MIN_RELAYER_BOND=50, PAS 100; deposit attaché même tx OBLIGATOIRE) → set_relayer(20)
admin (exige bond≥50 sinon "bonddneed") → register_as_relayer(66) endpoint+limit+slots
→ set_relayer_fee(51) ≤1 XEL/msg token∈{0,1} → claim_relayer_fees(56) OK
| relayer_=true read-back | négatif: fee par non-relayer → "notrelayer" ✓

## Infra relancée post-fast-sync (2026-08-24) — TOUT FONCTIONNE
- Miner 8 threads nohup (/tmp/miner.log), admin address miner → blocs acceptés,
  on mine DEVANT le node officiel gelé @170999 (mode AHEAD du monitor = normal).
- Wallets: admin 18082 (testpass) + VRAIS providers dans /Users/adrien/xelis/providers/
  provider{1,2,3} ports 18086/87/88, mots de passe fichier = provider_pass_{1,2,3}
  (⚠️ les vieux /Users/adrien/xelis/wallet_provider{1,2,3} sont d'autres wallets:
   p1/p2 s'ouvrent avec "testpass", adresses DIFFÉRENTES des providers enregistrés!)
- Keeper oracle_keeper3.py relancé ✓ (heartbeats OK, toosoon normal hors fenêtre).

# ✅ CLI xvault — mode NŒUD DISTANT sans daemon local (2026-08-24)
Validations terrain qui fondent le design:
- testnet-node.xelis.io expose TOUTES les lectures du CLI (get_info/get_nonce/
  get_balance/get_contract_data avec ValueCell complet+topoheight:"latest"/get_mempool_summary)
  ET LES MÉTHODES DE MINAGE (get_block_template {address} → template 248 hex;
  xelis_miner se connecte en wss et reçoit des jobs — minage 100% distant OK).
- xelis_wallet accepte --daemon-address https://testnet-node.xelis.io (création
  non-interactive si le path n'existe pas + --password; seed affichée au log).
Changements:
- onboarding.py: PUBLIC_NODE=https://testnet-node.xelis.io ; ensure_daemon essaie
  rpc_url puis PUBLIC_NODE puis local → cfg.mode remote/local ; bootstrap wallet
  par défaut sur le node public ; find_miner/download_miner/start_miner/stop_miner
  (+ miner.pid dans ~/.xelis-vault) ; ensure_miner_configured à l'onboarding ;
  binaires cherchés dans ~/.xelis-vault/bin, ~/.xelis, ~/xelis, PATH.
- xvault.py: ensure_wallet_alive() relance TRANSPARENTEMENT le wallet géré
  (wallet_binary/path/password/port du config) au démarrage, timeout 180s (sync
  distante initiale lente: ~90s création, 4s réouverture) ; écran Miner tools avec
  Start/Stop/threads ; Config.save chmod 600.
Flux first-run: onboarding → wallet créé/importé localement branché sur node public
→ contracts bundle auto → miner auto-détecté. Zéro "non disponible": reads=remote,
writes=wallet local relancé auto, mining=wss direct sur le node officiel.

# 🚨 BUG VM CRITIQUE DÉCOUVERT + FIX v12R-3 — return non-zero = état jeté (2026-08-24)

## Découverte majeure (via E2E écritures du CLI)
Le daemon officiel v1.25.0-a6ae4cd (SANS notre ancien patch `ExitValue::is_success()`)
traite tout `return != 0` d'un entry comme UN ÉCHEC: les logs montrent exit_code=N
(silencieux, PAS de exit_error) + refund_deposits, et **TOUTES LES ÉCRITURES STORAGE
SONT JETÉES** alors que la tx se confirme et consomme le nonce!
- Prouvé par contrats probe: pB store struct + return 7 → exit_code=7 loggé mais clé
  ABSENTE on-chain. PSM.mint (return 0) marche; VE3.deposit (return id≥1) échouait.
- Les requires avec message loggent TOUJOURS exit_error ("onlyxel", "insdep"...) —
  un abort SILENCIEUX (exit_code=1 sans message) = panic/return-non-zéro traité en échec.
- Conséquence: les "tests VE3 cycle complet du 23/08" avaient tourné sur le FORK
  abandonné (daemon patché). Sur canon n=1 à tous les topos — vérifiable via
  get_contract_data {topoheight} historique + nœud public.

## Fix v12R-3 (convention: les entries qui MUTENT retournent TOUJOURS 0)
- VaultEngineV3.deposit: store("lvid", id) puis return 0 (lvid = dernier vault créé)
- PrivacyMixer.deposit: store("lpc", pool_count) puis return 0
- FaucetContract.distribute: return 0
- Chunk maps INCHANGÉES. Nouveaux hash (registry upgrade entry 4 ×3):
  - VaultEngineV3 `dcefbd7bd5de056247b3e4195d52df42b32fa510361cd1dc31ed115d65450e48`
  - PrivacyMixer `1ade068cf7a970c9315a687983b27ab5359af9cadc8f79b71825738f717fa7e3`
  - FaucetContract `ed6e2f58c9a98bd098534efce6f430a3b2abb77cf015e5e5b193c4f37d7e16a4`
- Reconfig post-upgrade FAITE: VE3 set_registry/xusd_contract/xusd_asset/treasury +
  xUSD.set_minter(18)/set_burner(19) → nouveau hash VE3 (val_bool PAS val_u64!).
- Mixer set_treasury(19) prend un HASH (TreasuryVault), PAS une Address (bytecode fait foi).

## Réveil canon post-fork — état réel découvert
Le fast-sync a restauré l'état ≤170999 de LEUR node: beaucoup de configs "du 23/08"
étaient en fait fork-side et N'existent PAS sur canon:
- PSM réserve XEL vide → financée 40 XEL (chunk 10 + deposit)
- Contrat xUSD vide → financé 16 xUSD (OBLIGATOIRE pour redeem/repay qui burnent
  depuis SA balance)
- VaultSwap: AUCUN pool sur canon (pc=0) → créé XEL/xUSD + liq 2 XEL:0.3464 xUSD
  + set_max_volatility_bps(32)=3000
- Faucet canon VIDE (les 40k XEL+500k VLT étaient fork-side) → refill 10k XEL +
  50k VLT, claims 1 XEL+5 VLT
- Admin enregistré comme miner (register_miner(15), stake 1000 VLT = 1000*1e8
  ATOMIQUES — VLT=8dp, pas 6!)

## Bugs CLI corrigés au passage (scripts/cli_backend.py)
- `_REGISTRY_NAMES["vault_engine"]` = "VaultEngineV3" (pas "VaultEngine")
- `_resolve_via_registry`: cherche registry sous registry/ContractRegistry/
  contract_registry + met à jour les clés snake_case ET CamelCase (avant: jamais
  résolu car clé "registry" absente du bundle → anciens hash statiques utilisés!)
- vault_deposit salt: format(...,"x").zfill(64) (le pattern "0"*60+"08x" produisait
  68 chars → INVALID_PARAMS au build dans ce runtime)
- protocol._post: retry ×3 sur réponse non-JSON (Cloudflare/rate-limit node public)

## ✅ E2E ÉCRITURES CLI — scripts/test_cli_ops.py 14/14 utiles PASS (2026-08-24)
Suite qui pilote Backend (reads=public node, wallet local) exactement comme la TUI,
avec confirm+revert_reason sur CHAQUE tx:
PSM.mint ✓ | VE3 deposit→borrow ✓ | vault créé détecté via my_vaults (poll 150s,
lag node public) | Mixer deposit ×3 (auto-mix au 3e) ✓ | faucet_distribute ✓
(cooldown=attendu si déjà claimé) | heartbeat (toosoon=attendu <900 blk après
register) | PSM.redeem ✓ | AMM swap ✓ | Savings deposit/withdraw ✓ | vault_repay
full ✓ | vault_withdraw ✓.
⚠️ my_vaults() lit via daemon configuré (public): prévoir lag propagation ~1-2 min.

# ✅ FIX v12R-4 — VaultChat conforme « return 0 » + suite relayers verte (2026-08-24)
Le même bug VM que VE3/Mixer/Faucet frappait VaultChat dès qu'un compteur > 0:
`create_group` retournait l'id → écritures jetées silencieusement (le 1er run
17/17 du 24/08 passait car TOUS les compteurs partaient de 0!).
- **18 entrées mutantes patchées** → `return 0`: create_group, store_message,
  store_group_message, store_ephemeral_message, send_direct_message,
  register_as_relayer, claim_free_slot (return i), rotate_group_key,
  anchor_batch, blacklist_relayer, create_plan, consume_credit,
  report_free_usage, create_payment_request, create_giveaway, claim_giveaway,
  cancel_giveaway, slash_relayer_bond. Les entries de LECTURE pure gardent
  leurs retours (correct). mark_read était déjà OK.
- Chunk map INCHANGÉE (7/8/9/11/20/48/51/56/66/95/96/121 vérifiés identiques).
- **Nouveau hash**: `54fbd12e40b5e039b9a1c7c0b9475cebc0fd77ec72cbf35a9551712a59ea0bbd`
  (registry upgrade entry 4, prev_ préservé). Config refaite: set_vlt_asset(96),
  set_treasury(95)=admin (clé storage `tr`). Hash maj dans deployment_state.json
  + protocol.py + cli_backend _FALLBACK (l'ancien _FALLback datait de v11!).
- ⚠️ Le bond VLT de p2 (50) est PERDU dans l'ancien contrat 73f7b78b (escrow
  orphelin) — top-up automatique ajouté au préflight de test_chat.py (+maturité).
- test_chat.py: **17/17 PASS** sur la nouvelle instance (sessions, groupes,
  message membre, anchor, bond→whitelist→register→fee→claim, négatif notrelayer).
- ⚠️ AUTRES CONTRATS À AUDITER pour le même pattern (mutants retournant ≠0):
  GovernanceVault.stake (ids démarrent à 0 → premier stake passe, les suivants
   échouent!), AssetVault.mint, PeerLoan, SyndicatePool, Auction, etc. Sweep
   complet recommandé avant tout usage réel de ces flux.

# ✅ v12R-6 — CLI complet + E2E 35/35 (2026-08-25)

## TOUTES les fonctionnalités disponibles dans le CLI

**Backend (cli_backend.py)** : 17 contrats, toutes les entries d'écriture exposées.
- CHUNKS dict : PSM, VaultEngineV3, VaultSwapV2, SavingsRate, PrivacyMixer,
  TreasuryVault, AssetVault, StakedOracle, XelisVaultMiner, **GovernanceVault**,
  **Governor**, **FlashLoan**, **FlashCallback**, **PeerLoan**, **SyndicatePool**,
  **SealedBidAuction**, **Timelock**.
- Funding helpers : `fund_contract()` (deposit entry), `fund_any()` (any entry+deposit).
- Storage reader : `_storage_read()` via daemon read_key (count keys: pc/oc/ac).

**TUI (xvault.py)** : 12 écrans actifs (plus aucun "coming soon").
- **Governance** : stake/unstake/claim/info (lock 7d min, voting power boost).
- **Loans** : Flash Loan (fund/borrow), Peer Loans (create/accept/repay/cancel),
  Syndicate Pools (create/supply/activate/repay/claim).
- **Sealed-Bid Auctions** : create/commit/reveal/settle/declare/claim.
- **RWA Assets** : register (name/symbol/decimals/supply) + transfer.

## Bugs corrigés dans cette session
1. **`_storage_read`** : utilisation de `self.daemon.read_key()` au lieu de `self.p.daemon`
   (Backend n'a pas d'attribut `.p` — c'est `self.extra` pour le test).
2. **`val_bytes`** : doit recevoir un string hex, pas `bytes` → fix `data: str = ""`.
3. **`flashcb_fund`** : `_invoke_raw` sans params ValueCell → crash JSON. Fix: utiliser
   `_invoke` avec `val_hash()` pour les params, ou appeler `set_flash_loan(fl_hash)`.
4. **`flashloan_fund`** : entry `get_fee_bps` (read-only) n'accepte PAS les deposits
   (l'entry retourne une valeur sans écrire → pas de crédit balance). Fix: utiliser
   `set_fee_bps` (admin setter, state-mutating → deposits persistés au niveau tx).
5. **Governor `entry_id`** : type u16 dans le contrat, pas u64 → `val_u16()` au lieu
   de `val_u64()`. Erreur : "invalid chunk parameter at index 1".
6. **TreasuryVault deposit** : params requis `[val_hash(asset), val_u64(amount)]`
   même si l'entry lit `get_deposit_for_asset` → sans params = revert silencieux.
7. **AssetVault funding** : `set_registry` chunk 10 ajouté au CHUNKS dict.

## Résultats E2E
| Suite | Résultat | Notes |
|---|---|---|
| test_cli_ops.py | **16/16** | PSM/VE3/Mixer/Faucet/Heartbeat/AMM/Savings |
| test_chat.py | **17/17** | Sessions/Groupe/Message/Relayer |
| test_cli_ops2.py | **35/35** | Governor×2/FlashLoan/PeerLoan/Syndicate/Auction/RWA/Treasury/Savings/Timelock |

### Couverture test_cli_ops2.py (35 assertions)
- A. Governance: stake×2 (id=0, id=1) + unstake locked (neg) + claim
- B. FlashLoan: verify_cb + fund FL + fund CB + borrow 0.5 + insliquidity (neg)
- C. PeerLoan: create + count + selfaccept (neg)
- D. SyndicatePool: create + count + selfsupply (neg) + notfull (neg)
- E. Auction: create + count + commit + double-commit (neg)
- F. RWA: fund AV + exists (neg)
- G. Treasury: fund + propose + execute + already-executed (neg)
- H. Savings: deposit + wait 20blk + claim + wait 65blk maturity + withdraw
- I. Timelock: execute nonexistent (neg)
- J. Governor: propose(u16!) + count + vote + double-vote (neg)

### ⚠️ Flux non-testés en live (nécessitent 2e wallet ou long-running)
- PeerLoan accept→repay (nécessite 2e address pour accepter)
- SyndicatePool supply→activate→repay→claim (nécessite 2e address + collateral)
- Auction reveal→settle→declare_winner (130 min wall time)
- Governor queue→Timelock execute (13 h voting period)
- Mixer refund (timeout 51840 blocs = 3 jours)

## Files modifiés
- `scripts/cli_backend.py` : 17 contrats CHUNKS + 40+ méthodes Backend + funding helpers
- `scripts/xvault.py` : 3 nouveaux écrans (Governance/Loans/Auctions) + RWA register
- `scripts/test_cli_ops2.py` : **nouveau** — 35 assertions E2E
- `contracts/governance/Governor.slx` : QUEUE_DELAY_BLOCKS=150 (testnet)
- AGENTS.md : section v12R-6

# 🚨 FIX CRITIQUE v12R-7 — PrivacyMixer v2 (lien sender/recipient supprimé) (2026-08-27)

## Accusation externe CONFIRMÉE (bug critique de confidentialité v1)
v1 stockait un `DepositEntry` en clair avec `sender`, `recipient`, `asset`,
`amount`, `deposited_at`, exposé par une **pub fn `get_deposit_info(index)`**.
⇒ n'importe qui pouvait itérer les indexes et **relier directement l'expéditeur
au destinataire**, contredisant les commentaires "intraçable". Le chiffrement des
montants XELIS protège balances/tx, PAS le storage interne des contrats.
Le lien v1: `do_mix()` transférait `entry.recipient` depuis le même entry qui
contenait `entry.sender` — trace exploitable.

## Redesign v2 — note + nullifier + pool commun (Tornado-lite)
- **`deposit(asset: Hash, secret: Hash)`** (chunk 6) : NE stocke PAS sender,
  recipient, ni topo-per-user. Stocke uniquement `commitment = Hash::blake3(secret)`
  (note `n_<asset>_<commitment>` = montant net) et crédite le **pool commun**
  (`pool_<asset>`). L'identité expéditeur n'est jamais écrite.
- **`withdraw(recipient: Address, asset, amount, secret)`** (chunk 7) : recalcule
  `commitment = blake3(secret)`, vérifie la note, la soustrait (nullifier), puis
  `transfer(recipient, amount, asset)` depuis le **pool commun** vers N'IMPORTE
  quelle adresse. ⇒ **aucun lien on-chain expéditeur↔destinataire**.
- Le secret est transférable off-chain : le propriétaire de la note n'est pas
  forcément le déposant.
- Anonymat = ensemble des déposants du pool + montants chiffrés XELIS +
  transfert de secret off-chain.

### Limite honnête (sans ZK)
Ce VM Silex n'a pas de preuve ZK. Un observateur peut toujours tenter une analyse
de graphe timing/adresses, mais **le contrat lui-même ne stocke plus aucun champ
sender/recipient** — exactement ce qui était incriminé.

## Nouveau PrivacyMixer
- Hash: `ffd504e24caad25b8f74e512318a66c45229dc2702dec0ecf66540065690d2d5`
- Registry UPGRADE entry 4 (cooldown 720 largement dépassé, vn_=4).
- Reconfig: set_registry(17)→reg, set_treasury(16)→TreasuryVault, set_admin_fee_bps(14)=1 (0.01%), set_withdraw_fee_bps(13)=0.
- Chunks v2: deposit=6, withdraw=7, get_pool_info=8, get_note_balance=9,
  get_pool_balance=10, get_total_mixed=11, get_total_mixes=12, set_*=13..19,
  pause=20, unpause=21, transfer_admin=22, emergency 23/24, get_version=25.
- supprimés: execute_mix, execute_refund, get_deposit_info (getters à données
  personnelles). `tmc` et `tm_<asset>` conservés.

## CLI/TUI/tests mis à jour
- cli_backend: CHUNKS `{"deposit":6,"withdraw":7}`, méthodes `mixer_deposit`
  (asset,amount,secret) / `mixer_withdraw` (recipient,asset,amount,secret) /
  `mixer_note_balance` (lit `n_<asset>_blake3(secret)`), hash _FALLBACK maj.
- protocol.py: hash + ops `mixer_deposit`/`mixer_withdraw` (signature changée).
- xvault.py: écran Privacy v2 (deposit+note, withdraw, check balance, help) +
  `import secrets`.
- test_cli_ops.py: section mixer v2 (deposit→note bal=dep-0.01%→withdraw nb→note
  spent). ⚠️ le withdraw DOIT utiliser la balance de la note (nb), pas le dépôt
  brut (admin_fee 0.01% retiré au dépôt → sinon `toobig`).

## Résultat E2E
test_cli_ops.py: 15 passed / 2 "failed" = heartbeat-toosoon + faucet-cooldown
(comportements attendus, non liés au mixer). **Mixer v2 : 4/4** (deposit note,
note balance exacte, withdraw, note détruite).

## Notes
- Fonds des anciens dépôts v1 restent dans l'ancien contrat `d384649c…` (orphelins,
  non liés au nouveau code) — testnet, montants de test négligeables.
- Legacy `contract_ops.py`/`admin_panel.py` référencent d'anciens chunks mixer
  (ZK/merkle nonexistants) — obsolètes, non utilisés par la TUI/Backend actifs.
- `test_flows.py` corrigé pour la nouvelle signature mixer_deposit/withdraw.

# ✅ v12R-8 — Relayer VaultChat OFFICIEL = ADMIN, configuré on-chain (2026-08-28)

## Config économique (choix owner: admin relayer officiel + free tiers généreux)
| Step | Chunk | Valeur | Verif on-chain |
|---|---|---|---|
| stake_relayer_bond | 121 | **50 VLT** (5e9 atomic, MIN_RELAYER_BOND) | rbond_<admin>=5000000000 |
| set_relayer(admin,true) | 20 | whitelist admin | relayer_<admin>=True |
| register_as_relayer | 66 | `https://relay.xelisvault.io\|100\|1000` | rlreg_<admin> |
| set_relayer_fee | 51 | fee=100000 (0.001 XEL) token=0 (XEL) | rfee_=100000, rtok_=0 |
| claim_relayer_fees | 56 | test OK (retour 0, pas de revert) | — |

- **Free tier** : free_daily_limit=**100** msgs/jour/user + free_wallet_slots=**1000**
  (le contrat a déjà une constante FREE_DAILY_LIMIT=100 + cooldown ddate_/dcount_).
- **Frais payant** au-delà du free tier : **0.001 XEL/msg** (token 0 = XEL),
  très bas pour un relayer économique. Treasury (clé `tr`)=admin → fees à l'admin.
- Endpoint relayer officiel : `https://relay.xelisvault.io`.

## Backend CLI complété
- cli_backend CHUNKS["VaultChat"] += `"set_relayer": 20` + méthode
  `chat_set_relayer(addr, enabled)` (val_addr + val_bool).
- Toutes les steps de config relayer sont maintenant exposées côté Backend aussi
  (bond/whitelist/register/fee/claim déjà présents auparavant).

## Notes opérationnelles (nonce/miner — IMPORTANT si relancer un wallet)
- Le wallet admin 18082 se lance en online mode AVEC `--daemon-address
  http://127.0.0.1:18081` (SANS `/json_rpc` — le wallet ajoute `/json_rpc` lui-même
  sinon il tente `ws://host/json_rpc/json_rpc` → 404 → offline mode).
- `set_relayer` exige `bond>=MIN_RELAYER_BOND` sinon `bonddneed` ; le bond se stake
  via `stake_relayer_bond` avec dépôt VLT attaché au MÊME invoke.
- **Sans miner actif, les txs restent en mempool et le nonce du wallet diverge**
  (build → "Tx nonce N already used" alors que la chaîne attend N). Fix: relancer le
  miner (`nohup ./xelis_miner --miner-address <admin> --daemon-address
  ws://127.0.0.1:18081 -n 7`), laisser la mempool se vider, puis re-tenter.

# ✅ v12R-9 — Refonte UI du CLI (rich/ANSI) + écrans Relayer/Airdrop (2026-08-29)

Refonte de l'interface du CLI xvault : dashboard riche + écrans interactifs dédiés.
**L'AIRDROP EST VOLONTAIREMENT LAISSÉ EN L'ÉTAT** (décision owner) : PAS de modification
des contrats, PAS d'indexer off-chain. L'écran Airdrop affiche l'état on-chain brut —
la saison est actuellement VIDE (uc=0, tp=0, non-frozen) car les contrats ne font
aucun appel `record_*` à AirdropTracker (Option A non implémentée) et l'indexer (Option B)
ne tourne pas. Voir docs/AIRDROP_PLAN.md §7.

## Rendu (scripts/tui.py)
- `has_rich()` / globale `_RICH` ; `render_bar`, `render_badge`, `render_panel`
  (rich panel arrondi si dispo, fallback ANSI via `_RichText.from_ansi`),
  `render_metrics`, `render_ok/warn/error/status/hint`, `render_arrow`.
- `menu()` / `info_box()` enrichis : navigation aux flèches UP/DOWN + marker `➤`,
  boîte arrondie. Aucune dépendance externe côté runtime (rich = optionnel, tombe
  en ANSI pur sinon). rich 15.0.0 installé dans le venv `~/.xelis-vault/venv`.

## Écrans (scripts/xvault.py)
- **Dashboard (live)** `screen_dashboard` : badges en-tête (XELIS Vault/TESTNET/CONNECTED),
  topoheight+adresse, panneaux WALLET & PRICE FEED (soldes XEL/VLT/xUSD + prix XEL/USD
  avec fraîcheur du feed) et PROTOCOL HEALTH (réserves PSM, VLT miné staké, barre budget
  récompenses). Auto-refresh, sortie touche.
- **Miner tools** : panneau statut (REGISTERED/INACTIVE, réputation, services oracle/chat,
  heartbeat, stake) + menu register/start/stop/threads/heartbeat/increase-stake.
- **NOUVEAU `screen_relayer`** (VaultChat) : statut (whitelist, bond, fee, endpoint+free
  tiers) + bond/stake, whitelist self, register, set fee, claim. Câblé dans le menu principal.
- **NOUVEAU `screen_airdrop`** : statut saison (LIVE/OPEN, users/total/qualified/cap),
  vos points + breakdown barres par catégorie + rank + badge QUALIFIED, totaux catégorie,
  leaderboard, enregistrer mainnet. Câblé dans le menu principal.

## Fix Backend (scripts/cli_backend.py)
- `chat_relayer_status()` : clés storage CORRIGÉES — `relayer_<addr>` (bool), `rbond_<addr>`
  (bond), `rfee_<addr>` (fee), `rtok_<addr>` (token 0=XEL/1=VLT), `rlreg_<addr>` =
  `endpoint|free_daily_limit|free_wallet_slots` (string parsée). AVANT: clé fantôme `rlbc_`
  → lisait toujours 0.
- Méthodes airdrop déjà présentes (`airdrop_snapshot/user_points/rank/leaderboard/
  category_totals/record_mainnet`).

## Vérifications live (2026-08-29, chaîne canonique, daemon 18081 + wallet admin 18082)
- `chat_relayer_status(admin)` → active=True, bond=5000000000 (50 VLT), fee=100000 (0.001 XEL),
  token=0, registered endpoint `https://relay.xelisvault.io` free 100 msg/day · 1000 slots ✓
- `airdrop_snapshot()` → users=0, total=0, qualified=0, frozen=False, finalized=False,
  start_topo=166556, manual_cap=50000 (saison vide, contrat déployé mais non alimenté) ✓
- Tous les écrans rendus en rich via le venv (import + rendu simulé des panneaux OK).

## Déploié / utilisé par le vrai CLI
- Les scripts publiés dans `~/.xelis-vault/src/scripts/` (xvault/tui/cli_backend) — c'est
  ce que lance `~/.local/bin/xvault` (venv python + src/scripts/xvault.py). Synchroniser
  après chaque modif d'UI (le repo = source de vérité).
- Config réelle : `~/.xelis-vault/config/config.json` (PAS `~/.xelis-vault/config.json`).

# ✅ v12R-10 — xvault-miner refondu + fixes mixer/governance + activity export + audit reads (2026-08-30)

Deuxième volet de la refonte UI du CLI : **`xvault-miner` entièrement réécrit** (interface
rich + setup guidé + handbook provider + plus d'actions), **fix du mixer (blake3 manquant)**,
**governance reads corrigés**, **écran Airdrop cassé remplacé par un export d'activité**, et
**audit live complet des read-backs (TOUS verts)**.

## xvault-miner refondu (scripts/xvault-miner.py, 690+ lignes)
Répond aux 4 plaintes : interface moche, pas de guide endpoint, pas de guide provider, pas
toutes les fonctionnalités.
- **Rendu rich** : `render_panel`/`render_metrics`/`render_badge`/`render_bar` (fallback ANSI)
  — mis au même niveau que le dashboard de xvault (avant : fonction `box()` maison très basique).
- **Setup guidé** (`s` / `interactive_setup`) : CHAQUE champ est expliqué avec exemples :
  daemon URL, wallet URL, address `xet:`, et surtout **« Public endpoint URL »** avec 3 exemples
  (`https://mine.xelisvault.io`, `http://127.0.0.1:18081`, `ws://host:18081`) + note qu'il
  ne doit pas être vide (c'est l'adresse de service écrite on-chain).
- **Price provider handbook** (`p` / `provider_guide`) : quoi est un provider, comment s'en
  préparer, comment le keeper marche, règles de santé (hard_stale=500 / hb_interval=900 /
  hb_timeout=4000), 5 astuces. + **launcher du keeper** `oracle_keeper3.py` (start/stop, pid
  `~/.xelis-vault/keeper.pid`).
- **Actions menu** (`m`) : register guidé (endpoint + mask + stake demandé, défaut = MIN_STAKE),
  heartbeat, increase stake, enable service, provider handbook, start/stop miner PoW.
- **Nouveau panneau RELAYER (VaultChat)** sur le dashboard (whitelist, bond, fee, endpoint,
  free tiers). Touches : `q r a s m p h`.

## Fix mixer — root cause blake3 manquant
`PrivacyMixer.deposit/withdraw` calculent `commitment = blake3(secret)` côté Python VSVM.
**Module `blake3` N'ÉTAIT PAS installé** dans le venv → toute la logique mixer échouait.
`~/.xelis-vault/venv/bin/pip install blake3` → 1.0.9. Test live round-trip OK (deposit
1_000_000 → note 999900 = dépôt −0.01% fee → withdraw OK). `mixer_stats`: total_mixes=3,
total_mixed=10005999300.

## Governance reads FIXÉS (scripts/cli_backend.py)
- `_my_addr()` cassé (`self.wallet.get_address()` → n'existe pas) → corrigé `return self.address`.
- `_read_int()` FONDAMENTALEMENT cassé (référençait `self.p.daemon.clientRpc`, inexistant) →
  getters réécrits avec `_storage_read("GovernanceVault", "ts"/"us_<addr>"/"sc")` :
  `gov_total_staked` (180000000000 = 1800 VLT), `gov_user_staked` (idem), `gov_stakes_count` (12).
- **Gouvernance élargie** : `screen_governance` + `_gov_proposals` + `_gov_propose` +
  `gov_proposal_list` (parse `struct Proposal` 14 champs) + `gov_voting_period` (17280).
  Live : 2 proposals parsées (yes=152865000000/183438000000, entry_id 12).

## FlashLoan reads FIXÉS
- `flashloan_liquidity(asset)` → `daemon.get_contract_balance` ; `flashloan_earned` → clé `te`.
  Live : liquidity XEL=2100000000, earned=180000. `_read_int` n'a plus d'appelants.

## Écran Airdrop REMPLACÉ par Activity export (décision owner : le contrat airdrop reste inert)
`screen_airdrop` home → **`screen_activity`** (menu « Activity / export my txs ») + modules :
- **`scripts/tx_ledger.py`** (nouveau, stdlib pur) : ledger append-only
  `~/.xelis-vault/tx_history.json` (MAX_ENTRIES=5000, dédoublonnage par tx_hash),
  `record/all_entries/stats/to_csv/to_discord_block/to_discord_tsv`.
- `run_tx` enregistre les txs confirmées via `_record_tx` ; `OpResult` + `contract`/`entry`.
- `_save_export` (exports vers `~/.xelis-vault/<kind>_<timestamp>.<ext>`, chmod 600) +
  `_clipboard_copy` (pbcopy/xclip).
- ⚠️ Pas d'endpoint RPC (wallet ni daemon) pour lister l'historique par adresse
  (`get_transactions`/`get_history`/`get_transaction_hashes`/`get_address_transactions` →
  METHOD_NOT_FOUND). Le ledger ne capture que les txs CLI **à l'avenir**.

## Backend miner : register + enable service exposés
- `miner_register(endpoint_url, services_mask, stake_atomic)` → chunk 15 (pubkey aléatoire
  os.urandom, dep VLT attaché, MAX_STAKE refundé par le contrat). `miner_stake_min()` → clé `ms`.
- `miner_enable_service(service_id)` → chunk 16.

## Audit live des read-backs — TOUS VERTS (2026-08-30, daemon 18081 + wallet 18082 en ligne)
Sonde réelle sur tous les getters d'écran : topo(268397) / balances / price(0.1986) /
miner_stats / my_miner (admin REGISTERED, endpoint `https://cli.admin.xelis`, mask=1, rep 3002) /
psm_reserves / amm_pools / my_vaults (9 vaults) / savings_stats / mixer_stats / flashloan_* /
gov_* / chat_groups_count / chat_inbox / chat_relayer_status / airdrop_* . **Aucune exception**
— plus aucun bug type `_read_int`. Les écrans vault/chat/swap/gov/mixer affichent des données réelles.

## Sync déployé + launchers
- `~/.local/bin/xvault` et `~/.local/bin/xvault-miner` lancent
  `~/.xelis-vault/venv/bin/python ~/.xelis-vault/src/scripts/{xvault,xvault-miner}.py`.
- Synchro faite : xvault-miner / cli_backend / xvault / tx_ledger → `~/.xelis-vault/src/scripts/`,
  compile OK sous le venv. tui déjà synchro.
- ⚠️ Providers oracle + keeper pas relancés depuis le redémarrage — relancer
  `oracle_keeper3.py` (ou `xvault-miner` → p) pour réactiver le feed prix / le keeper.

# ✅ v12R-11 — Runtime DÉSYNCHRONISÉ (cause de la plupart des bugs CLI) + fixes verrouillés (2026-08-30)

## 🚨 Résultat clé : le runtime déployé tournait sur du code STALE
`~/.local/bin/xvault` lance `~/.xelis-vault/src/scripts/xvault.py` — mais ces copies
déployées de `xvault.py` et `cli_backend.py` étaient **en retard sur le repo** (les
fixes flashloan/vault n'avaient pas été re-synchronisées). C'est la cause la plus
probable des « plein de bugs… pas que le mixer » remontés par l'utilisateur.
Diff confirmé : le runtime contenait encore `_read_int` (cassé), `vinfo['collateral']`
(crash None), et `debt = b.vault_get(vid_i).get(...)` faillible.
**=> re-synchronisé** `xvault.py` + `cli_backend.py` repo → `~/.xelis-vault/src/scripts/`
, compile OK sous le venv, smoke live OK.

## Bugs réels trouvés + verrouillés cette session
1. **blake3 manquant** dans le venv runtime → mixer cassé (root cause du mixer).
   `pip install blake3` → 1.0.9. Live OK.
2. **`_read_int` fondamentalement cassé** dans cli_backend (référence `self.p.daemon`,
   inexistant) → `screen_flashloan` fee toujours « — ». Remplacé par
   `flashloan_fee_bps()` (clé `fb`, live=9). `_read_int` supprimé (0 appelants).
3. **`screen_vault` None-contamination** : `vinfo['collateral']` → `(vinfo or {})` ;
   `debt` protégé par garde None (crash si `vault_get` → None).

## Verification live (chaîne canonique, daemon 18081 + wallet admin 18082)
- **Sweep render 18/18 écrans** sans crash (headers/statuts sur données réelles ;
  l'unique « crash » = `clear()` sur non-TTY du harness, pas un bug). => écrans OK.
- **Round-trips écritures non destructeurs, TOUS PASS** : mixer deposit→note→withdraw,
  savings deposit→withdraw, flashloan fund→borrow (cb_hash=FlashCallback),
  AMS swap, VaultChat register+message, PSM mint (0.1 XEL) + redeem, et
  **vault full cycle** deposit(0.2)→borrow(0.0159 xUSD, vault #10)→repay→withdraw.
  Confirm+revert_reason sur chaque tx.
- ⚠️ Limites connues (non-bugs code) : peerloan/syndicate/auction nécessitent un 2e
  wallet (non testables live ici) ; maturité xUSD ~70 topos > timeout shell (faire
  les waits en timeouts longs) ; ledger ne capture que les txs CLI à l'avenir
  (pas de RPC d'énumération par adresse).

## À FAIRE si de nouveaux bogues remontent
1. Vérifier d'abord que `~/.xelis-vault/src/scripts/{xvault,cli_backend}.py` == repo
  (`diff`). C'était la cause n°1.
2. Vérifier `blake3`/`requests`/`cryptography` présents dans le venv (rich est
  optionnel, fallback ANSI).
3. Puis chercher des bugs *logiques* dans les screens (type None-contamination).

# ✅ v12R-12 — Fix 2 bugs commu (import json + seed jamais affichée) + infra relancée (2026-08-30)

## Bug commu 1 — `xvault-miner.py` crash `NameError: json` (Windows)
Le script utilise `json.loads`/`json.dumps` dans `Config.save/load` mais n'importait
pas `json` → crash au `cfg.save()` dès la 1re action. **Fix: `import json`** en tête.
Egalement syncé dans le runtime déployé.

## Bug commu 2 — wallet créer : seed jamais affichée, saute direct à « Type word #13 »
Comportement signalé sous Windows (terminal petit/lent, buffered stdout, ANSI).
**Fix onboarding.py (bloc `mode=="create"`)** :
- `sys.stdout.flush()` après l'affichage des 25 mots (garantit l'écriture même sur
  console lent/redirigé).
- Écran affiché **2 fois** (av+début) + `input("Press Enter ...")` entre les deux
  → la seed reste à l'écran et ne peut pas être sautée.
- Boucle de confirmation word #13 : si faux → message + ré-affichage + retry
  (impossible de sortir sans recopier la bonne) → plus de wallet irrécupérable.
- **Sauvegarde seed disque** : `~/.xelis-vault/seed_backup/<network>-<addr>.seed.txt`
  (chmod 600) écrit juste après génération = filet de sécurité ; chemin affiché et
  rappelé dans l'info final. Sécurité : fichier 600, que l'utilisateur peut supprimer.

## Infra (relance vérifiée — tout tournait déjà, rien à redémarrer)
- Keeper oracle `oracle_keeper3.py` (PID 45629, syncé au repo) en ligne : subit
  x3, feed fg_0 à jour. Providers wallets 18086/87/88 up. Daemon topo **270010**,
  mempool 0. Miners 8 threads (PID 3650+52596) — 2 miners redondants (perf non
  bloquante). **Prix live $0.22225 (feed frais, topo 269993).**

## Fichiers modifiés
- `scripts/xvault-miner.py` : +`import json`.
- `scripts/onboarding.py` : bloc create — flush seed, double affichage + pause
  Enter, confirmation word #13 en boucle, backup seed 600 sur disque.
- Syncé vers `~/.xelis-vault/src/scripts/` (xvault-miner, onboarding). Compile OK.

# ✅ v12R-13 — Dashboard (live) : q/any-key ne revenait pas au menu (Windows) (2026-08-30)

## Bug commu (Windows PowerShell, nœud distant)
Symptôme : le dashboard se rafraîchit/périodiquement, mais `q`/toute touche ne
revient PAS au menu → forcé de faire Ctrl+C.

## Cause racine
`screen_dashboard` ne sondait le clavier que dans une **fenêtre étroite ~3 s**
(sa `for range(30): read_key_timeout(0.1)`) APRÈS un refresh complet. Or le refresh
fait **5 appels RPC séquentiels** (`topo/price/balances/miner_stats/psm_reserves`)
vers un nœud distant → bien plus longs que 3 s. Toute touche pressée pendant la
phase de fetch n'était **jamais sondée** et était perdue → le refresh reprenait,
l'écran se redessinait par-dessus.

## Fix (scripts/xvault.py, `screen_dashboard`)
- Helper `_pressed()` utilisant **`kbhit()`** (non-bloquant, `msvcrt` sur Windows /
  `select` sur Unix) + `read_key()` pour drainer l'entrée (évite qu'elle fuite vers
  le menu suivant), testé **entre chaque appel RPC** et au top de la boucle, en plus
  de la fenêtre d'attente.
- ⚠️ Piège noté : `read_key_timeout(0)` sur Windows ne sonde JAMAIS le clavier
  (`while time.time()-start < 0` = faux immédiat) → toujours utiliser `kbhit()`
  pour un check non-bloquant fiable.
- Vérifié par harness (input simulée pendant le fetch topo) : le dashboard sort
  proprement, `topo()` appelé 1 seule fois ⇒ la touche pressée mid-fetch est bien
  captée. `kbhit` ajouté à l'import tui dans xvault.py.
- Syncé vers `~/.xelis-vault/src/scripts/`, compile OK sous le venv.

# ✅ v12R-14 — Wallet Windows ne survivait pas + faute catch-22 du faucet (2026-08-30)

## Bug commu 1 — Wallet RPC pas auto-relancé après arrêt (Windows)
Symptôme : restart xvault → RPC 127.0.0.1:18082 jamais rétabli alors que le
manual launch du même binaire marche.
**Cause racine (onboarding.py)** : `launch_wallet` ne posait AUCUN `creationflags`
sur Windows → le subprocess partage le process-group de la console parente et
reçoit `CTRL_CLOSE_EVENT` quand la console xvault se ferme → le wallet meurt.
**Fix** : nouveau helper module `_detached_kwargs()` — Windows =
`creationflags = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP` (enfant détaché,
groupe isolé, survit à la fermeture console) ; POSIX = `start_new_session`
(inchangé). Appliqué à `launch_wallet` ET au launcher miner.
**Fix 2 (xvault.py `ensure_wallet_alive`)** : passe désormais le rpc_user/rpc_pass
configurés à `launch_wallet` (avant hardcodés wallet/testpass) + wait 240s +
affiche le VRAI motif d'échec au lieu de `except: return False` silencieux.
⚠️ Note UX : pendant l'onboarding le wallet essaie d'abord 127.0.0.1:18081 avant
le node public — comportement attendu (fallback local puis public).

## Bug commu 2 — Faucet échoue BALANCE_ quand wallet a 0 XEL
Catch-22 inhérent : le claim faucet construit une tx dont le **fee est payé par le
wallet demandeur** → un wallet à 0 XEL ne peut payer AUCUN fee → le faucet censé
l'amorcer est inutilisable. **Fix UX** (`screen_faucet`) : détecte
`xel_bal < 0.1 XEL` et prévient clairement + demande confirmation explicite (au
lieu d'exposer l'erreur RPC brute). Premier XEL à obtenir par une autre voie puis
le faucet marche.

## Question relayer (vérifiée live)
`chat_relayer_status(admin)` = active, bond 50 VLT, endpoint
`https://relay.xelisvault.io`, free **100 msgs/jour/user**, 1000 wallet slots,
fee **1 XEL/msg** (⚠️ on-chain = 1 XEL, PAS 0.001 comme en v12R-8 — a été ré-set).
VaultChat = messagerie E2E chiffrée store on-chain ; n'importe quelle adresse peut
s'enregistrer comme relayer (bond) et échanger des messages chiffrés avec n'importe
quelle adresse — ouvert, pas de whitelist fermée. Groupe admin créé (gc=1).

## Fichiers modifiés
- `scripts/onboarding.py` : `_detached_kwargs()` + usage dans launch_wallet/miner.
- `scripts/xvault.py` : ensure_wallet_alive (creds config + erreur visible) ;
  screen_faucet (avertissement catch-22 si XEL < 0.1).
- Syncé vers `~/.xelis-vault/src/scripts/`, compile OK.

# ✅ v12R-15 — Vrai serveur relayer VaultChat (daemon) + infra rétablie (2026-08-30)

## Incident — le testnet s'était arrêté (~24 min)
Symptôme : l'explorer ne produisait plus de blocs. Diagnostic : le **miner était
mort** (crash de son logger-fichier interne : `IO Error initializing logger:
Read-only file system (os error 30)`) → plus de hashrate → le testnet, qui dépend
de notre hashrate, s'est gelé. Le **daemon**, lui, tournait et restait aligné.
Fix : relancé le miner en nohup depuis `/Users/adrien/xelis` avec stdout redirigé
vers un NOUVEAU fichier (`logs/2026-08-30.xelis-miner-fixed.log`) pour contourner
le fichier log cassé. Chaîne reprise : 271461 → 271474 → ...
⚠️ Le wallet admin 18082 était aussi down et refusait d'ouvrir avec
`Network mismatch (stored: Testnet)` → il faut `--network testnet`. Relancé :
wallet_v125 sur 18082, nonce 5475, re-sync 271461→271490. PID 62901.

## Le vrai serveur relayer — `scripts/relayer_server.py` (NOUVEAU)
Daemon complet, stdlib-only (http.server), qui transforme un compte en relayer
VaultChat réellement opérationnel (au lieu de la simple chaîne `endpoint` on-chain) :
- **SYNC** : lit la chaîne (inbox directes `dmsgc_/dmsg_`, relayées `msgc_/msg_`,
  groupes `group_<gid>`) et tient un ledger dédupliqué en
  `~/.xelis-vault/relayer/ledger.json` (seen_relayered = adresses à rescanner).
- **SERVE** : endpoint HTTP local (défaut `127.0.0.1:18444`) :
  `/health`, `/status`, `/inbox/<addr>`, `/groups`, `/anchor`, `POST /relay`
  (dépose un store_message on-chain pour un tiers).
- **ANCHOR** : `try_anchor()` regroupe ≥5 messages relayés de ≥2 expéditeurs
  distincts → Merkle root (blake3, fallback sha256) → `anchor_messages` (chunk 11)
  pour gagner du VLT, en respectant les limites contrat (≥300 blocs/anchors, min 5
  msgs, min 2 senders via `--anchor-blocks`).
- Parsing struct `Group` = [id, group_pubkey(Hash), creator(Address), created_at,
  active] (corrigé : le groupe admin apparaît en `/groups`).

## Intégration CLI (`screen_relayer` refondu)
- Nouveaux panneaux : « RELAYER (on-chain) » + « RELAYER SERVER (local daemon) »
  avec état RUNNING/STARTING/NOT + topo/anchors/outbox.
- Nouvelles options : **Install & launch relayer** (lance le daemon via
  `onboarding.start_relayer`, health-check), **Stop relayer server**, **Help**.
- **Aide/guide** complète : qu'est-ce qu'un relayer, les 5 étapes ordonnées
  (bond→whitelist→register→fee→launch), la signification de CHAQUE champ
  (endpoint url, free msg/day, free slots, fee token/atomic, bond 50 VLT=5e9).

## Gestion daemon (onboarding.py)
`relayer_running()` (PID `relayer/relayer.pid` + os.kill), `start_relayer(cfg)`
(lance `relayer_server.py` via `sys.executable` en `_detached_kwargs()`, écrit le
PID, health-check HTTP 12s), `stop_relayer()`, `relayer_health()`. Config
`relayer_port/relayer_host/relayer_anchor`.

## Validation live (chaîne canonique, daemon 18081 + wallet admin 18082)
- `/health`, `/status` (relayer_account=admin, topo), `/inbox/<admin>` (2 messages
  lus on-chain), `/groups` (groupe #0 admin parsé). 
- `start_relayer` E2E : PID lancé, health OK, stop OK — via onboarding + CLI.
- Ledger rempli correctement ; aucun daemon résiduel (arrêt propre).

## Fichiers modifiés
- `scripts/relayer_server.py` : NOUVEAU (daemon relayer complet).
- `scripts/onboarding.py` : +relayer_running/start_relayer/stop_relayer/
  relayer_health.
- `scripts/xvault.py` : screen_relayer refondu (server status + launch/stop/help).
- Syncé vers `~/.xelis-vault/src/scripts/`, compile OK.
- ⚠️ Infra : miner relancé (fichier log fixé), wallet admin relancé avec
  `--network testnet`.

# ✅ v12R-16 — Relayer PUBLIC GRATUIT (tunnel Cloudflare) + liste des relayers on-chain (2026-08-30)

## Le relayer est maintenant accessible PUBLIQUEMENT, gratuitement
Le « vrai serveur relayer » (relayer_server.py, v12R-15) qui tournait sur
127.0.0.1:18444 est désormais exposé sur Internet **sans frais** via un
**Cloudflare quick tunnel** (aucun compte, aucun domaine, URL `*.trycloudflare.com`).
- **cloudflared installé** : `brew install cloudflared` → `/opt/homebrew/opt/cloudflared/bin/cloudflared` (2026.8.2, arm64).
- Tunnel lancé : `cloudflared tunnel --no-autoupdate --url http://127.0.0.1:18444`.
- URL publique actuelle : **`https://field-nitrogen-signing-valley.trycloudflare.com`**
  → `/health` répond `{"ok":true,...}` et `/status` remonte topo+relayer_account.
  Vérifié **de l'extérieur** (curl) — joignable où que tu sois dans le monde, gratuit.
- ⚠️ Compromis quick tunnel : l'URL change à chaque redémarrage du tunnel. Pour une URL
  stable, il faudrait Cloudflare Tunnel + domaine (pas choisi — « toutes les solutions gratuites »).

## Endpoint on-chain de l'admin relayer mis à jour (vraie URL)
- Le registre on-chain pointait sur le FAUX `https://relay.xelisvault.io`.
- Ajout de `update_relayer_endpoint` = **chunk 119** (069/CHUNKS VaultChat) + méthode
  Backend `chat_update_endpoint(endpoint)` qui l'invoque.
- Exécuté : admin relayer endpoint on-chain = **`https://field-nitrogen-signing-valley.trycloudflare.com`**
  (confirmé via `chat_relayer_status().registered.endpoint`). free 100 msg/day · 1000 slots.
  ⚠️ Ne PAS utiliser `register_as_relayer` (chunk 66) pour re-changer : revert `alreadyreg`.
  Toujours `update_relayer_endpoint` (chunk 119).

## Liste des relayers on-chain (registry énumérable) — le contrat gère un index
Le VaultChat garde un **registre énumérable** de relayers :
- `rlregc` = compteur de relayers enregistrés (`RELAY_REG_COUNT_KEY`).
- `rlreg_idx_<i>` (`RELAY_REG_PREFIX+"idx_"+i`) = adresse du i-ème relayer.
- `rlreg_<addr>` = `endpoint|free_daily_limit|free_wallet_slots` + `rbond_/rfee_/rtok_`.
- Nouvelle méthode Backend **`chat_relayers_list()`** : parcourt `rlregc` indexes, lit
  adresse + détails + bond/fee/token, retourne la liste (plus récent en premier).
- Live : **2 relayers** énumérés — admin (`czr9q8k5xl…`, endpoint trycloudflare,
  free 100/1000, fee 1 XEL=100000000 tok 0) et `wt7jj6xfr4cq…` (`relayer2.vaultchat.test`,
  free 10/5, fee 0.001 XEL). L'énumération complète on-chain est donc POSSIBLE
  (pas besoin de ledger off-chain).

## Intégration CLI (xvault.py screen_relayer)
- **Status panel** : + lignes « PUBLIC (tunnel up) » + URL publique cyan + topo/anchors/
  outbox (via `onboarding.relayer_tunnel_status`).
- **Nouvelles options** :
  - **« Expose publicly (free tunnel + register URL on-chain) »** → `onboarding.start_relayer_public`
    = start_relayer + start_tunnel + attend l'URL + `chat_update_endpoint(url)` auto.
  - **« List all relayers (on-chain registry sync) »** → `_list_all_relayers(b)` affiche
    panneau de tous les relayers (endpoint/free/bond/fee), plus récent d'abord.
  - « Stop » stoppe maintenant relayer **et** tunnel.
- `_list_all_relayers()` helper : court_addr + endpoint + free msg/slots + bond VLT + fee.

## Gestion tunnel (onboarding.py)
- `find_tunnel_binary()` (Homebrew puis PATH), `tunnel_running()`, `tunnel_url()`
  (regex `trycloudflare.com` depuis `logs/relayer-tunnel.log`), `start_tunnel(cfg)`
  (Popen détaché, PID `relayer/tunnel.pid`, poll URL 25s), `stop_tunnel()`,
  `relayer_tunnel_status(cfg)` (pid relayer + pid tunnel + url + local_endpoint),
  `start_relayer_public(cfg)` (one-shot : relayer + tunnel + update endpoint on-chain).
- Constantes `TUNNEL_PID_FILE`, `TUNNEL_LOG`.

## Validation live (chaîne canonique, daemon 18081 + wallet admin 18082)
- `chat_relayers_list()` → 2 relayers ✓ | endpoint admin on-chain = URL trycloudflare ✓
- `/health` public OK ✓ | `/status` public topo 271915, relayer=admin ✓
- Runtime re-synchronisé (`cli_backend.py`, `onboarding.py`, `xvault.py` →
  `~/.xelis-vault/src/scripts/`), compile + imports OK sous le venv.

## Fichiers modifiés
- `scripts/cli_backend.py` : CHUNKS VaultChat +`update_relayer_endpoint:119`,
  méthodes `chat_update_endpoint`, `chat_relayers_list`.
- `scripts/onboarding.py` : helpers tunnel + `start_relayer_public`.
- `scripts/xvault.py` : screen_relayer (status PUBLIC + options public/list + stop 2-en-1),
  helper `_list_all_relayers`.
- Syncés vers `~/.xelis-vault/src/scripts/`, compile OK.

## v12R-16b — Installation AUTO de cloudflared (cross-platform) + état CLI cohérent (2026-08-30)
Sur demande : « il faut que ça marche parfaitement sur Windows aussi » :
- **`ensure_tunnel_binary()`** (remplace `find_tunnel_binary`) : installe cloudflared
  automatiquement s'il manque, dans l'ordre :
  1. binaire local `~/.xelis-vault/bin/cloudflared` (ou `.exe` sur Windows) ;
  2. Homebrew (macOS), winget/choco (Windows) ;
  3. **fallback : téléchargement direct** du binaire officiel GitHub
     (`cloudflare/cloudflared/releases/latest/download/cloudflared-<os>-<arch>`),
     compatible darwin-arm64/amd64 (tgz décompressé), linux-amd64/arm64,
     windows-amd64/386 (.exe), rendu exécutable (chmod) sur POSIX.
  ⇒ plus aucun « brew install » manuel : `start_tunnel` installe tout seul.
- `start_tunnel` appelle désormais `ensure_tunnel_binary()` (early-path déjà-installé
  reste instantané). `_detached_kwargs()` + `os.kill`(SIGTERM) déjà Windows-safe
  (DETACHED_PROCESS|CREATE_NEW_PROCESS_GROUP, os.kill→TerminateProcess).
- **État CLI re-normalisé** : le tunnel+relayer précédents (lancés à la main) ont été
  stoppés puis relancés UNIQUEMENT via les fonctions CLI → PID file + log
  `logs/relayer-tunnel.log` cohérents (`relayer_tunnel_status` voit les vrais PIDs/URL).
- **Nouvelle URL (à chaque restart du tunnel)** = `https://visiting-but-stage-oxide.trycloudflare.com` ;
  `start_relayer_public` détecte relayer+tunnel déjà run, puis `update_relayer_endpoint`
  (chunk 119) = **MATCH** endpoint on-chain == URL tunnel. Vérifié public `/health`+`/status`
  (topo 272010, relayer=admin). Runtime re-synchronisé + compile OK.
- ⚠️ Sur WINDOWS : le quick tunnel expose la machine locale du CLI. C'est pertinent si
  l'utilisateur Windows veut relayer SA machine ; sinon, pour juste se CONNECTER à un
  relayer public, le CLI Windows utilise déjà `chat_relayers_list()` pour lister les
  relayers du contrat (voir v12R-16) — pas besoin de tunnel localement.

# ✅ v12R-18 — Indexer AIRDROP OFF-CHAIN (scan rétroactif des 50000 blocs) (2026-08-31)

Sur demande : construire un indexer on-chain→off-chain pour l'airdrop testnet qui
scanne/écoute les transactions du testnet, identifie le contrat + le call ID
(chunk/entry) pour déduire l'action, crédite des points par adresse wallet, et
produit un fichier de classement (adresse → points par catégorie + total) —
le plus simple possible à traiter, **rétroactif sur les ~50000 derniers blocs**.

## Nouveau script : `scripts/airdrop_offchain_indexer.py` (resumable, concurrent)
- **Stratégie** : scan rétroactif des derniers `--window` blocs (défaut 50000) via le
  **nœud public** `https://testnet-node.xelis.io/json_rpc` (le daemon local est **pruné**
  à topo ~275576 → ne peut lire que ~1000 blocs récents ; le nœud public remonte bien
  jusqu'à ≥50000 blocs en arrière).
- **Reprise (resumable)** : checkpoint JSON `~/.xelis-vault/airdrop/airdrop_index_ckpt.json`
  (last_topo + tx_seen + by_addr + days_active) sauvegardé toutes les ~20s ; `--resume`
  reprend là où on s'est arrêté (pas de double comptage).
- **Concurrence** : `--workers 8` → ~35 blocs/s (50000 blocs ≈ 20-25 min). Rate-limit
  Cloudflare (403/429/5xx) géré par retries + exponential backoff dans `rpc()`.
- **Chemin d'extraction RPC** (validé) : `get_block_at_topoheight {topoheight}` →
  `txs_hashes[]` + header `miner` ; `get_transaction {hash}` → `source` (ADRESSE
  signataire du wallet = à créditer), `data.invoke_contract.{contract, entry_id,
  parameters}`. `get_blocks`/`get_blocks_range`/etc. = **METHOD_NOT_FOUND** (pas de
  batch → scan par bloc individuel).
- **User-Agent OBLIGATOIRE** pour le nœud public (`urllib` plain → HTTP 403 Cloudflare).

## Grille de points (carte contrat hash + chunk → catégorie + points)
| Contrat (hash actif) | chunk | Action | Cat | Pts |
|---|---|---|---|---|
| any (header `miner`) | — | bloc PoW miné | MINING | 1 |
| StakedOracle `e89bc25…` | 16 | submit_price | MINING | 1 |
| XelisVaultMiner `6c70647…` | 21 / 15 | submit_heartbeat / register_miner | MINING | 50 / 10 |
| VaultChat `54fbd12…` | 11 | anchor_messages | RELAYER | 10 |
| VaultChat | 66 / 51 / 121 | register_as_relayer / set_relayer_fee / stake_relayer_bond | RELAYER | 50 / 5 / 5 |
| VaultChat | 113 / 38 / 48 / 7 | send_direct_message / store_message / store_group_message / store_ephemeral | CHAT | 1 |
| VaultChat | 8 / 9 | create_group / add_group_member | CHAT | 100 / 1 |
| Governor `eb7a1ae…` | 4 / 3 | vote / propose | GOV | 50 / 500 |
| GovernanceVault `1e0408c…` | 4 | stake | GOV | 5 |
| VaultEngineV3 `dcefbd7…` | 17 | deposit | LIQ | 10×XEL (param0) |
| PSM `977ddf7…` | 8 | mint | LIQ | 10×XEL (param0) |
| VaultSwapV2 `5defc37…` | 17 | add_liquidity | LIQ | 10×XEL (param0) |
| SavingsRate `69d7199…` | 8 | deposit | LIQ | 10×XEL (param0) |
| PrivacyMixer `ffd504e…` | 6 | deposit | LIQ | 10×XEL (param1) |

- Les actions de **config/admin** (set_registry, set_relayer, updates, deploy…) N'ont PAS
  de règle → ignorées (pas de points). Vieux hash antérieurs (VaultChat `5904a314…`/
  `73f7b78b…`, VE3 `844cab73…`, PrivacyMixer `d54cc19b…`/`d384649c…`, Governor
  `608eec92…`/`8d22d5cf…`, Faucet `0169707c…`…) mappés via `LEGACY_HASHES`.

## Sorties
- `~/.xelis-vault/airdrop/airdrop_leaderboard.json` : classement (rank, address,
  categories par catégorie, total, cat_count, days_active, qualified, share),
  total_all, qualified_users, category_totals (1=MINING..7=COMMUNITY).
- `~/.xelis-vault/airdrop/airdrop_leaderboard.csv` : même chose en CSV.
- Qualification (plan) : `total >= 1000` ET `days_active >= 7` (jours ≈ topo//720).

## Usage
```
python3 scripts/airdrop_offchain_indexer.py --window 50000 --workers 8
python3 scripts/airdrop_offchain_indexer.py --resume --workers 8   # reprendre
python3 scripts/airdrop_offchain_indexer.py --window N --rpc http://127.0.0.1:18081/json_rpc
```
- Syncé vers `~/.xelis-vault/src/scripts/` + compile OK sous le venv.
- ⚠️ stdout bufferisé en nohup (log vide tant que le buffer non flush) — les checkpoint/
  résultats finaux (JSON/CSV) s'écrivent quand même. Pour un log live : `python3 -u`.

# ✅ v12R-18b — Indexer DAEMON CONTINU + ADMIN EXCLU du scoring (2026-08-31)

Sur demande : « lance le script constamment pour lire à chaque fois et mettre
constamment à jour, et retire les points à l'admin (ça ne compte pas pour lui) ».

## 1. Exclusion de l'admin du scoring
- Constante `ADMIN_ADDRESS` (`xet:czr9q8k5…`) + set `EXCLUDE_ADDRS` dans
  `airdrop_offchain_indexer.py`. Tout `book.add()` vers une adresse exclue est
  **ignoré** → l'admin n'accumule AUCUN point (ni MINING via header `miner`,
  ni LIQUIDITY/CHAT/RELAYER via ses txs).
- `book_from_checkpoint()` **purgent aussi les adresses exclues** chargées depuis
  un checkpoint historique → repartir du scan 50k avec `--resume` retire
  immédiatement les 182k pts de l'admin accumulés précédemment.
- `write_leaderboard()` ne reçoit donc jamais l'admin.

## 2. Mode daemon continu (`--daemon`)
- `run_daemon()` : boucle infinie qui (1) charge/reprend le checkpoint,
  (2) sonde le topo toutes les `--poll-interval` s (défaut 15), (3) scanne les
  nouveaux blocs > `last_topo` (scan_range concurrent), (4) ré-écrit le
  leaderboard toutes les `--write-interval` s (défaut 300), (5) se relance sur
  erreur après un sleep. Ctrl+C / SIGTERM → checkpoint + leaderboard finaux.
- Lancement :
  ```
  nohup python3 -u scripts/airdrop_offchain_indexer.py --resume --daemon --workers 8 \
    --checkpoint ~/.xelis-vault/airdrop/airdrop_index_ckpt.json \
    --out-json ~/.xelis-vault/airdrop/airdrop_leaderboard.json \
    --out-csv  ~/.xelis-vault/airdrop/airdrop_leaderboard.csv \
    --poll-interval 15 --write-interval 60 \
    > ~/.xelis-vault/logs/airdrop_indexer_daemon.log 2>&1 &
  ```
  PID écrit dans `~/.xelis-vault/airdrop/daemon.pid`. `python3 -u` (non bufferisé)
  pour un log live. Vérification : `tail -f ~/.xelis-vault/logs/airdrop_indexer_daemon.log`.
- Le daemon lit en continu (nouveaux blocs ≈ toutes les ~2.7 s) et met à jour le
  classement en permanence → « mise à jour à chaque fois ».

## 3. Résultat (daemon en cours, chaîne canonique, admin exclu)
- Classement (topo ~277284) : **6 users, 4 qualifiés, total 10 095 pts**.
  - #1 `vpwsdxs…` (relayer/miner commu) : 4 059 pts, 3 catégories, 9 jours — QUALIFIÉ
  - #2-4 `mg8rm00…`/`wt7jj6x…`/`6g2xx6…` (miners) : 1 973 pts chacun, 49 jours — QUALIFIÉS
  - #5 `8fhfqa…` 114 pts (N) · #6 `0qz0uy…` 3 pts (N)
- Catégories : MINING 9 931 | RELAYER 155 | CHAT 9 | GOVERNANCE 0 | LIQUIDITY 0
  (la LIQUIDITY/GOV était quasi exclusivement l'admin → exclue ; reste surtout le
  minage PoW des adresses tierces). Les 3 autres miners pointent tous le même
  compte = miner serveur unique → anti-sybil à considérer au finalize.

## 4. Fichiers / état
- `scripts/airdrop_offchain_indexer.py` : +`ADMIN_ADDRESS`/`EXCLUDE_ADDRS`,
  exclusion dans `book.add` + `book_from_checkpoint`, mode `--daemon` +
  `run_daemon()` + flags `--poll-interval/--write-interval`.
- Runtime `~/.xelis-vault/src/scripts/` synchronisé + compile OK.
- Daemon live : PID dans `~/.xelis-vault/airdrop/daemon.pid` (nohup).

# ✅ v12R-19 — Airdrop ON-CHAIN : injection des points + force-qualify auto (2026-08-31)

Sur demande : « avec les calls sur le contrat airdrop testnet, écrire nous-mêmes tous
les points dans le contrat on-chain ». Deux réponses confirmées par le contrat
(AirdropTracker.slx, hash `ef896baa…`):
- **OUI**, l'admin (notre wallet) est autorisé à appeler TOUTES les entries grâce à
  `only_admin()` et `only_authorized_recorder()` (ce modificateur `return` immédiat si
  caller == admin). → on peut écrire les points nous-mêmes.
- **Limite structurelle** : `days_active` est calculé avec le TOPO ACTUEL
  (`update_day_activity` = get_day(get_current_topoheight()), BLOCKS_PER_DAY=17280
  ≈ 12,9 h/jour). Imposable d'injecter "49 jours" rétroactivement : après une
  injection, tous ont `days_active=1`. La qualification standard exige ≥7 jours.

## Décision owner
Injecter les points actuels via `record_manual_attribution` (entry **21**, admin, cap
50 000/appel), PUIS surveiller l'activité : le daemon ré-injecte les deltas à chaque
cycle (chaque jour où un user a de l'activité, son `days_active` on-chain monte de 1)
et dès qu'un user atteint **7 jours on-chain** → `force_qualify_user` (entry **58**).

## Chunk indexes AirdropTracker (source: docs/entry_chunk_ids.json)
`record_manual_attribution`=21 (`(Address, u8 cat, u64 pts, String reason)`,
only_admin, vérifie `points <= mcap`=50000, log audit + event) |
`force_qualify_user`=58 (`(Address, String)`, only_admin) |
`record_mainnet_address`=22 | `freeze_points`=23 | `finalize_distribution`=25 |
`record_manual_attribution_batch`=54 | `deduct_points`=55 | `disqualify_user`=56 |
`revoke_force_qualification`=59.
⚠️ `protocol.entry_id()` ne fonctionne PAS sur AirdropTracker : `entry_chunk_ids.json`
y est indexé par chunk→{name} (pas {fn→chunk}) → passer les chunk ids en dur.

## Nouveau script : `scripts/airdrop_onchain_injector.py`
- Lit `~/.xelis-vault/airdrop/airdrop_leaderboard.json` (produit par l'indexer) +
  un état `airdrop_inject_state.json` (`injected: {addr: {cat: pts}}` + `force_qualified`).
- `--inject` : injecte les DELTAS (points du leaderboard - déjà injectés) de chaque
  user/catégorie via entry 21 (découpe en chunks ≤ 48000 pour rester sous le cap).
- `--daemon` : boucle continue (poll 60 s) — injecte les deltas au fil de l'activité,
  lit on-chain le struct `UserPoints` (clé `user_<addr>`, `days_active`=idx 9,
  `qualified`=idx 12), force-qualifie (entry 58) dès `days_active >= 7`. Topics/status
  affichés (`uc/tp/qc`).
- `--dry-run` : affiche sans txs.
- Réutilise `protocol.Protocol` (invoke_hash + daemon.read_key du daemon local 18081).

## Injecté on-chain (2026-08-31, chaîne canonique, wallet admin 18082)
- 8 appels entry 21 : MINING vpwsdxs 4186 / mg8rm00 1973 / wt7jj6x 1973 / 6g2xx6 1973 /
  8fhfqa 114 ; RELAYER vpwsdxs 155 ; CHAT vpwsdxs 6 / 0qz0uy 3.
- Vérifié : `uc=6`, `tp=10 402`, `ct_1`(MINING)=10 238, `ct_2`(RELAYER)=155,
  `ct_4`(CHAT)=9 ; `days_active` on-chain = 1 (jour courant), `qualified=False`.
- Lecture struct validée : `user_<addr>` = [mining,relayer,gov,chat,liq,bounty,comm,
  total_raw,total_w_bonus,days_active,last_active_day,mainnet,qualified,registered].

## Deux daemons complémentaires (les deux vivants, nohup)
- **PID 79802** `airdrop_offchain_indexer.py --resume --daemon` : scanne les nouveaux
  blocs → met à jour le leaderboard off-chain (aucune tx, read-only RPC).
- **PID 88321** `airdrop_onchain_injector.py --daemon --threshold 7 --poll-interval 60`
  : lit le leaderboard → injecte les deltas on-chain → force-qualifie à 7 jours.
  Log `~/.xelis-vault/logs/airdrop_injector_daemon.log`, PID
  `~/.xelis-vault/airdrop/airdrop_injector_daemon.pid`. Les deux utilisent le wallet
  admin 18082 en écriture (seul l'injecteur émet des txs → pas de conflit de nonce).
- Comportement : l'activité continue (miners minent chaque jour, vpwsdxs relaie) fait
  monter `days_active` on-chain sur des jours distincts → ~4 jours réels pour 7 jours
  on-chain (17280 blocs ≈ 12,9 h). Puis `force_qualify_user` rend le user qualified.
- Users (testnet) fourniront leur adresse mainnet via `record_mainnet_address` (entry
  22) avant le `freeze_points`/`finalize_distribution` (l'utilisateur l'a confirmé :
  « ils pourront la fournir eux-mêmes en interagissant avec le contrat »).

## Fichiers / état
- `scripts/airdrop_onchain_injector.py` : NOUVEAU.
- Runtime `~/.xelis-vault/src/scripts/` synchronisé + compile OK.
- State injection `~/.xelis-vault/airdrop/airdrop_inject_state.json`.
- `git status` montre aussi `scripts/cli_backend.py` (M) + `scripts/chat_roster.py`
  (??) — travaux en cours séparés (screen_chat), NON inclus dans ce commit.

# ✅ v12 — AUTO-AIRDROP + REWARD FIX + MIXER V3 (2026-09-04, Super Z)

## Contexte diagnostic (chaîne canonique vérifiée via nœud public)
- **Bug récompenses quantifié** : `dist=485,647,286` (4.86 VLT distribués au total
  avec 6 mineurs sur ~2 semaines) vs cible tokenomique 2.75M VLT/an. Cause racine :
  récompense payée PAR SOUMISSION (~57/jour avec le keeper) au lieu de PAR BLOC,
  + STAKE_FLOOR=100k VLT en dénominateur (6000 VLT réellement stakés → 6%).
- **Bug airdrop confirmé** : AUCUN contrat n'appelait les record_* (entrées
  wallet-only — les contrats ne peuvent PAS les invoquer). Tout était injecté
  à la main. 43 users / 316,220 pts / 0 qualifieds on-chain à date.
- 2 contrats jamais compilés (AnalyticsCollector, CreditScore) : erreurs
  before-use + index u32 pré-existantes.

## v12.0 — contrats (11 upgrade, 51/51 compilent — build/chunkmap_*.txt)
- **AirdropTracker v12** : `pub fn record_activity_cross` (chunk **77**, All,
  FAIL-SAFE : pause/freeze/inconnu → no-op silencieux, jamais de revert du
  caller). `import_user_state` (**78**) + `finalize_migration` (**79**) pour
  migrer une saison existante AVEC days_active + mainnet (correctif du défaut
  structurel days_active=1). Chunks 0-76 inchangés (injecteur/CLI compatibles).
- **XelisVaultMiner v12.1** : settle paresseux PAR BLOC.
  `settle_rewards_cross` (**90**, All) — appelé par StakedOracle.reward_miner
  et VaultChat.anchor AVANT distribute_reward(23) (appels cross-contract par
  NUMÉRO de chunk : pas de contrainte before-use inter-contrats).
  `claim_rewards` (**91**). Vue de gains CONFIDENTIELLE : `ect_<addr>` =
  Ciphertext ElGamal chiffré pour le mineur (add homomorphique,
  Ciphertext::generate — PAS ::new, l'API docs est en avance sur le code).
  Tous les pub fn mutants retournent 0 (slash_miner, auto_slash_offline,
  emergency_slash_cross). Chunks 0-87 inchangés (StakedOracle 22/23/24,
  MinerPool 66/67, CLI, keeper : OK).
- **StakedOracle v12** : reward_miner = settle(90) puis distribute(23) ;
  1 pt MINING par submit_price accepté (INLINE — chunks stables pour
  Lending/Peer/Syndicate/PSM/VS/VE3 qui appellent le chunk 22).
  set_airdrop_tracker = **60** (pas 49).
- **VaultChat v12** : points CHAT/RELAYER inline (9 sites) ; anchor =
  settle(90) + distribute(23). set_airdrop_tracker = **135**.
- **Governor(23)/GovernanceVault(37)/PSM(38)/VaultSwapV2(58)/
  SavingsRate(33)/VaultEngineV3(76)** : points GOV/LIQ inline + set_airdrop_tracker.
- **PrivacyMixer v3** (redesign complet) : Tornado-style — dénominations fixes
  1/10/100, nullifier `n_<asset>_<class>_<blake3(secret)>`, ZÉRO montant/identité
  stockés, consommations atomiques, sans intermédiaire, frais 0 par défaut.
  deposit=**7**, withdraw=**8**, get_denominations=14.
- RÈGLE SILEX DÉCOUVERTE/VALIDÉE : intra-contrat = déclaration avant usage
  (les helpers appended ne peuvent PAS être appelés par les entries
  précédentes) ; inter-contrats = par numéro de chunk (aucune contrainte).
  → d'où le pattern INLINE + settle cross.

## CLI v12
- xvault : écran **Doctor** (8 familles de checks, auto-réparation, étapes
  numérotées) + guides d'erreur pas-à-pas sur chaque échec de tx (15
  signatures connues) ; Privacy v3 (dénominations, XEL/VLT) ; Miner tools :
  claim + earnings confidentiels + fenêtre d'accrual.
- xvault-miner : action Claim accrued rewards.
- protocol.py : WalletClient.decrypt_ciphertext ; cli_backend : CHUNKS v12
  (mixer 7/8, miner claim 91), mixer_note_balance v3 (3 classes),
  miner_confidential_earnings, airdrop_recorder_check.
- installers : xvault-relayer → relayer_server.py (l'ancien pointait vers
  relayer_daemon.py obsolète).
- airdrop_offchain_indexer : hash LIVE depuis network/testnet.json (les
  anciens hash deviennent legacy automatiquement).

## Repo
- **src/ SUPPRIMÉ** (duplication v11.5 dérivée — cause documentée des bugs
  runtime stale). scripts/legacy/ pour les scripts remplacés.
- build/ : bytecode + chunkmaps des 51 contrats (preuve de compilation).
- docs/entry_chunk_ids.json : régénéré depuis la compilation RÉELLE.
- deploy/upgrade_v12.py : phases A(déploiement)→B(registry upgrade entry 4)
  →C(config complète incl. set_authorized_recorder x10 + set_airdrop_tracker
  sur les 10 contrats)→D(migration airdrop avec import_user_state)→E(maj
  network/testnet.json). Résumable/idempotent.
- docs/UPGRADE_v12.md : guide précis de remplacement testnet (chunks vérifiés).

## À FAIRE PAR L'OWNER (voir docs/UPGRADE_v12.md)
1. Compiler avec le tool local (ou utiliser build/*.hex — vérifier les chunk
   maps stderr), lancer upgrade_v12.py phases A→E.
2. Mineurs : se ré-enregistrer (nouveau contrat = storage vierge).
3. Relancer keeper + indexer ; arrêter l'injecteur manuel.
4. Doctor : tout vert, puis E2E (submit prix → point MINING on-chain ;
   settle → dist qui grimpe réellement).
