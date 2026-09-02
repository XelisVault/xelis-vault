# XELIS Vault — Miner Economics v10.9 (Definitive Design)

> **Date :** 13 août 2026
> **Objectif :** Système de rewards sans faille, anti-Sybil, anti-concentration, soutenable long-terme

---

## 1. Les 4 problèmes à résoudre

| # | Problème | Conséquence |
|---|----------|-------------|
| 1 | Sybil via splitting | Attaquant split son stake en N miners → manipule la médiane |
| 2 | Cap stake arbitraire | Limite artificielle (50,000 VLT) → pas de skin in the game au-delà |
| 3 | Centralisation par délégation | Tout le monde délègue aux top 3 → ils contrôlent l'oracle |
| 4 | Pas d'incitation à l'indépendance | Déléguer plus rentable que d'être son propre miner |

---

## 2. La solution : 4 mécanismes combinés

### Mécanisme 1 : Budget quotidien fixe

Le protocole distribue un **budget fixe par jour** aux miners actifs.

```
budget_quotidien = budget_annuel / 365 × budget_factor
                  = 550,000 / 365 × budget_factor
                  = 1,507 VLT/jour × budget_factor (0.5x à 2x)
```

**budget_factor** s'auto-ajuste toutes les 2 semaines :
- Si on distribue trop vite → factor baisse (0.5x min)
- Si on distribue trop lentement → factor monte (2x max)
- Garantit que le budget dure 10 ans

**Pourquoi fixe ?**
- Plus de miners → moins par miner → mais plus de sécurité (bien)
- Moins de miners → plus par miner → incite à venir (bien)
- Pas de "reward par submission" qui peut être farmé

### Mécanisme 2 : Reward = part du budget (proportionnelle au stake)

```
reward_miner = (stake_miner / stake_total) × budget_quotidien
             × reputation_multiplier
             × independence_bonus
```

**Propriétés :**
- Plus de stake = plus de rewards (linéaire, pas de cap)
- Le même APY pour tous (1,000 VLT ou 100,000 VLT = même %)
- Pas d'avantage Sybil : 100,000 en 1 miner = 100 × 1,000 = même total
- La réputation augmente le reward (1.5x Excellent, 0.5x Warning)
- L'indépendance augmente le reward (+20% si pas de délégation)

### Mécanisme 3 : Oracle pondéré par stake (CLÉ anti-Sybil)

C'est la solution fondamentale au Sybil oracle.

**Avant (médiane simple) :**
- 100 miners soumettent des prix
- Médiane = prix du 50ème miner
- Attaquant avec 51 miners (sur 100) contrôle la médiane

**Après (médiane pondérée par stake) :**
- Chaque miner a un poids = son stake
- Médiane pondérée = prix où 50% du stake total est au-dessus/dessous
- Attaquant doit avoir >50% du **stake total** pour manipuler
- Coût d'attaque = >50% de tout le VLT staked (extrêmement cher)

**Pourquoi ça marche :**
- 1 miner × 100,000 VLT = 50% du poids oracle
- 100 miners × 1,000 VLT = 50% du poids oracle (même chose)
- Splitter ne donne **aucun avantage** dans l'oracle
- L'attaquant doit acheter >50% de tout le VLT staked

### Mécanisme 4 : Anti-concentration + independence bonus

**Cap de délégation :** Un miner ne peut pas avoir plus de 20% du stake total délégué.

**Pénalité de concentration :** Si un miner dépasse 15% du stake total, ses rewards sont réduits.

**Independence bonus :** +20% de rewards si le miner n'a pas de délégation.

**Pourquoi être indépendant est toujours plus rentable :**
- Déléguer : tu paies 5-20% de commission
- Indépendant : tu gardes 100% + bonus +20% = 120% de tes rewards
- La délégation est pour ceux qui ne veulent pas faire tourner un miner

---

## 3. Scénarios économiques

### Scénario A : Bootstrapping (10 miners)

```
10 miners × 1,000 VLT each
Total stake: 10,000 VLT
Budget quotidien: 1,507 VLT (factor 2x pour attirer)

Par miner: (1,000 / 10,000) × 1,507 × 2 = 301 VLT/jour
APY: (301 × 365 / 1,000) × 100 = 10,986%

⚠ TROP ÉLEVÉ — le budget_factor doit être plus bas au début
Avec factor 0.5x: 75 VLT/jour → APY 2,738%
Avec factor 0.3x: 45 VLT/jour → APY 1,643%

Le budget_factor s'ajuste pour garder le budget sur 10 ans.
```

### Scénario B : Croissance (100 miners)

```
100 miners × 1,000 VLT each
Total stake: 100,000 VLT
Budget quotidien: 1,507 VLT (factor 1.0x)

Par miner: (1,000 / 100,000) × 1,507 = 15.1 VLT/jour
APY: (15.1 × 365 / 1,000) × 100 = 551%

Reward total: 1,507 VLT/jour × 365 = 550,000 VLT/an ✓
Budget dure: 5,500,000 / 550,000 = 10 ans ✓
```

### Scénario C : Maturité (500 miners)

```
500 miners × 1,000 VLT each
Total stake: 500,000 VLT
Budget quotidien: 1,507 VLT (factor 1.0x)

Par miner: (1,000 / 500,000) × 1,507 = 3.0 VLT/jour
APY: (3.0 × 365 / 1,000) × 100 = 110%

Reward total: 1,507 VLT/jour × 365 = 550,000 VLT/an ✓
```

### Scénario D : Saturation (1000 miners)

```
1000 miners × 1,000 VLT each
Total stake: 1,000,000 VLT
Budget quotidien: 1,507 VLT (factor 1.0x)

Par miner: (1,000 / 1,000,000) × 1,507 = 1.5 VLT/jour
APY: (1.5 × 365 / 1,000) × 100 = 55%

Reward total: 1,507 VLT/jour × 365 = 550,000 VLT/an ✓
```

---

## 4. Scénarios avec stake variable

### Un gros miner parmi des petits

```
100 miners × 1,000 VLT + 1 miner × 50,000 VLT
Total stake: 150,000 VLT
Budget quotidien: 1,507 VLT

Petit miner: (1,000 / 150,000) × 1,507 = 10.0 VLT/jour → APY 367%
Gros miner:  (50,000 / 150,000) × 1,507 = 502.3 VLT/jour → APY 367%

→ Même APY ! Le gros miner gagne plus en absolu (volume)
→ Pas d'avantage à être gros ou petit (équitable)
→ Le gros miner a plus de poids dans l'oracle (50,000 / 150,000 = 33%)
```

### Attaquant Sybil (100,000 VLT split en 100 × 1,000)

```
100 honest miners × 1,000 VLT
100 Sybil miners × 1,000 VLT (même attaquant)
Total stake: 200,000 VLT

Reward par miner: (1,000 / 200,000) × 1,507 = 7.5 VLT/jour
Attacker total: 7.5 × 100 = 750 VLT/jour
Honest total: 7.5 × 100 = 750 VLT/jour

→ L'attaquant gagne EXACTEMENT la même chose qu'en faisant 1 miner × 100,000
→ Pas d'avantage reward à splitter

ORACLE (pondéré par stake):
  Attacker stake: 100,000 VLT = 50% du poids
  Honest stake: 100,000 VLT = 50% du poids
  → L'attaquant a 50% du poids, PAS 50% des votes
  → Même situation que s'il n'avait pas splitté
  → Pour manipuler: besoin de >50% du STAKE TOTAL (cher)
```

---

## 5. Sécurité oracle : médiane pondérée par stake

### Comment ça marche

Au lieu de trier les prix et prendre le milieu (médiane simple), on pondère chaque prix par le stake du miner qui l'a soumis :

```
Prix soumis:
  Miner A (1,000 VLT):    $0.19
  Miner B (5,000 VLT):    $0.20
  Miner C (50,000 VLT):   $0.21
  Miner D (10,000 VLT):   $0.19
  Miner E (1,000 VLT):    $0.22

Stake total: 67,000 VLT

Médiane simple (par count): $0.20 (le 3ème sur 5)
Médiane pondérée (par stake):
  Cumul par prix croissant:
    $0.19: (1,000 + 10,000) / 67,000 = 16.4%
    $0.20: 16.4% + 5,000/67,000 = 23.9%
    $0.21: 23.9% + 50,000/67,000 = 98.5% ← dépasse 50% ici
    $0.22: 98.5% + 1,000/67,000 = 100%

  Médiane pondérée = $0.21 (le prix où 50% du stake est atteint)
```

### Pourquoi ça empêche le Sybil

```
Attaquant a 100,000 VLT, 100 honest miners ont 1,000 VLT chacun (100,000 total)

Médiane simple:
  100 Sybil miners + 100 honest = 200 miners
  Attacker contrôle 100/200 = 50% → peut manipuler

Médiane pondérée par stake:
  Attacker stake: 100,000 VLT = 50% du poids
  Honest stake: 100,000 VLT = 50% du poids
  → Même chose que 1 vs 1 (pas 100 vs 100)
  → Splitter ne change RIEN
```

### Coût d'attaque

Pour manipuler l'oracle, un attaquant doit contrôler >50% du **stake total** :

| Stake total protocole | Coût min attaque (50%) | Prix VLT | Coût USD |
|------------------------|------------------------|----------|----------|
| 100,000 VLT | 50,000 VLT | $0.50 | $25,000 |
| 500,000 VLT | 250,000 VLT | $0.50 | $125,000 |
| 1,000,000 VLT | 500,000 VLT | $0.50 | $250,000 |
| 5,000,000 VLT | 2,500,000 VLT | $0.50 | $1,250,000 |

Plus le protocole grossit, plus l'attaque coûte cher. C'est la sécurité par stake économique.

---

## 6. Délégation et indépendance

### Pourquoi être indépendant est plus rentable

| Configuration | APY (sur own stake) |
|---------------|---------------------|
| Miner indépendant (1,000 VLT, 0% commission) | 100% + 20% bonus = **120%** |
| Miner avec délégation (1,000 own + 4,000 delegated, 10% commission) | ~36% (sur own) + commission |
| Délégateur (1,000 VLT délégué, 10% commission) | **90%** (100% - 10%) |

**L'indépendant gagne toujours plus** (120% vs 90%). La délégation est pour ceux qui ne veulent pas faire tourner de miner.

### Anti-concentration

- **Cap 20%** : Un miner ne peut pas avoir plus de 20% du stake total délégué
- **Pénalité 15%** : Si un miner dépasse 15% du stake total, rewards réduits
- **Max 500 délégateurs** par miner

---

## 7. Implémentation

### Modifications nécessaires

**XelisVaultMiner.slx :**
- Remplacer `distribute_reward` par distribution basée sur le budget quotidien
- Ajouter `stake_weight` (stake du miner / stake total)
- Ajouter `independence_bonus` (+20% si pas de délégation)

**StakedOracle.slx :**
- Modifier `aggregate()` pour utiliser médiane pondérée par stake
- Appeler `XelisVaultMiner.get_miner_stake()` pour chaque provider
- Trier par prix, cumuler les stakes, trouver le 50%

**MinerDelegation.slx :**
- déjà implémenté (cap 20%, independence bonus)

---

## 8. Conclusion

Ce système résout les 4 problèmes :

| Problème | Solution |
|----------|----------|
| Sybil via splitting | Oracle pondéré par stake (pas par count) |
| Cap stake arbitraire | Pas de cap (linéaire, plus de stake = plus de rewards) |
| Centralisation | Cap 20% délégation + pénalité 15% + independence bonus |
| Incitation indépendance | Independence bonus +20% + pas de commission |

**Propriétés clés :**
- ✅ Plus de stake = plus de rewards (linéaire, pas de cap)
- ✅ Même APY pour tous (équitable)
- ✅ Pas d'avantage Sybil (splitting = même chose)
- ✅ Oracle sécurisé (médiane pondérée par stake)
- ✅ Budget soutenable (10 ans garanti par budget_factor)
- ✅ Incitation à l'indépendance (+20% bonus)
- ✅ Anti-concentration (cap 20% + pénalité 15%)

---

*XELIS Vault — Miner Economics v10.9 (Definitive Design)*
