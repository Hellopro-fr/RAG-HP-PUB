# Harness E2E qualite moteur de recherche HelloPro

## But

Reproduire l'audit Cowork de maniere automatisee, sans dependance externe,
pour pouvoir mesurer **avant/apres** chaque modif (LOW cert, dedup, etc.)
et **detecter les regressions** sur les keywords canari.

## Fichiers

| Fichier | Role |
|---|---|
| `keywords.json` | 17 keywords baseline (9 critiques + 8 canari) issus de l'audit du 13/05 |
| `run_audit.py` | Script principal : fetch URL front + parse HTML + scoring auto + KPIs |
| `compare.py` | Diff entre 2 runs : detecte gains, regressions, calcule verdict |
| `results/` | Output JSON de chaque run + .md du compare |

## Prerequis (sur la VM)

```bash
# Installer les deps Python (1 fois)
pip3 install --user requests beautifulsoup4
```

## Workflow type pour un test avant/apres

```bash
# 1. Aller dans le dossier
cd /home/devhp/RAG-HP-PUB/tests/search_quality_harness

# 2. Capturer baseline avant modif
python3 run_audit.py --output results/T0_baseline_2026-05-15.json --verbose

# 3. Appliquer la modif PHP (ex: deployer fonctions_annuaire_hp.php avec flag penalize_low_cert)
#    + activer le flag : URL ?ajax=1&core_v2=1&penalize_low_cert=1 dans run_audit.py

# 4. Capturer apres modif
python3 run_audit.py --output results/T1_after_low_cert.json --verbose

# 5. Comparer
python3 compare.py results/T0_baseline_2026-05-15.json results/T1_after_low_cert.json --md results/diff_T0_T1.md

# 6. Lire le verdict
cat results/diff_T0_T1.md
```

Le verdict du compare.py est (seuils RELATIFS au baseline T0, override via CLI) :
- **VALIDE** : critical avg progresse d'au moins `critical_min_gain` (default 0.3) ET aucun canary n'a chute de plus de `canary_max_drop` (default 0.5) vs T0 -> on garde la modif
- **SANS EFFET** : critical avg pas de progression suffisante -> on revert la modif
- **ROLLBACK OBLIGATOIRE** : au moins un canary a chute de plus de `canary_max_drop` vs T0 -> rollback immediat

> **Note 2026-05-15** : seuil canari devenu RELATIF (delta vs T0) au lieu d'absolu.
> L'ancien seuil `canary_min_score=9.5` etait trop strict : en baseline T0 du 15/05,
> 5/8 canaris etaient deja sous 9.5 (calibration auto-score plus strict que humain Cowork).
> Le seuil relatif detecte une vraie regression introduite par la modif, pas la valeur absolue.

## Options run_audit.py

```
--keywords PATH      Path vers keywords.json (default: keywords.json)
--output PATH        Path output JSON (default: results/run_<timestamp>.json)
--workers N          Nb threads paralleles (default: 4)
--pages N            Nb pages a analyser (default: 4, soit P1+P2+P3+P4)
--verbose            Print chaque requete + latence
--only-critical      Tester uniquement les 9 critiques (rapide ~30s)
--only-canary        Tester uniquement les 8 canari (rapide ~30s)
```

## Calibration

Apres le tout premier run (T0 baseline), comparer le `global_avg_auto_score`
avec la note Cowork de l'audit du 13/05 (= 6.7/10).

- Si la note auto est entre **5.5 et 7.5** -> calibration OK, on peut commencer les actions.
- Si la note auto est < 5 ou > 8 -> l'heuristique de scoring est trop laxiste ou trop stricte.
  Ajuster les paliers dans `score_match()` ou la tokenisation dans `tokenize()`.

## Heuristique de scoring (note 1-5 par produit)

```
nb_hits = |tokens_query intersection tokens_titre|  (apres normalisation NFD + lowercase + sans accent)
ratio = nb_hits / |tokens_query|

  ratio >= 1.0  -> 5  (parfait)
  ratio >= 0.75 -> 4  (bon)
  ratio >= 0.5  -> 3  (moyen)
  ratio >= 0.25 -> 2  (faible)
  ratio <  0.25 -> 1  (hors-sujet)
```

C'est une heuristique simple : la note Cowork humaine est plus nuancee
(elle tient compte du contexte, des marques, etc.). Mais cette heuristique
est **reproductible** et **rapide**, donc parfaite pour mesurer un delta
entre 2 runs.

## Note globale ponderee

```
note_finale_10 = (0.6 * mean_score_p1 + 0.4 * mean_score_p2) * 2
```

Meme ponderation que l'audit Cowork (60% P1, 40% P2).
Si P2 est vide (single page), on prend juste mean_score_p1 * 2.

## Limites connues

1. Le parser HTML s'appuie sur la classe `.card-product.list_produit`.
   Si HelloPro change le markup, le parser cassera silencieusement.
2. La detection de l'ID produit cherche `data-id-produit`, `data-produit-id`,
   puis fallback regex `/produit-(\d+)-` dans le href. A adapter si le
   markup change.
3. La detection societe cherche plusieurs selecteurs (`.product-vendor`,
   `.vendeur`, etc.). Si aucun ne matche, la dedup par societe ne marchera pas
   correctement. A verifier sur le HTML reel.
4. En mode hybride server-side, TOUTES les cartes sont dans le HTML
   (jusqu'a ~200). On slice par lots de 40 pour reconstruire P1/P2/P3/P4.
   Si le slice server-side change (cf fix P0 du 30/04), il faudra adapter.
