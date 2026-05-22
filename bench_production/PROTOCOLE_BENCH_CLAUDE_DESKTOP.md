# Protocole bench Milvus vs Hybride — Claude Desktop + Chrome

**Contexte** : préparer la décision de bascule par défaut Solr V2 + Typesense
(PR #622). Bench à exécuter dans une session Claude Desktop avec Claude in Chrome
(extension navigateur).

**Date cible** : avant merge de PR #622 + upload Ecritel + bascule GKE.

---

## 1. Setup initial (1 minute)

1. Ouvrir Claude Desktop
2. Lancer une nouvelle conversation
3. Activer Claude in Chrome (extension)
4. Charger le CSV des mots-clés :
   ```
   C:\RIJA\CLAUDE_CODE\opti_moteur\RAG-HP-PUB\bench_production\keywords_coverage_v1.csv
   ```
5. Vérifier que Chrome a une session valide hellopro.fr (cookies OK)

## 2. URLs de référence

Pour chaque `{mot_cles}` du CSV (encodé URL) :

| Backend | URL |
|---|---|
| **Milvus** (défaut actuel) | `https://www.hellopro.fr/moteur_recherche/recherche_resultat.php?type_recherche=produit&recherche_active=1&mot_cles={mot_cles}` |
| **Hybride** (Solr V2 + Typesense) | Ajouter `&ajax=1` à la fin |

## 3. Prompt à donner à Claude Desktop

> Tu es chargé d'exécuter un bench comparatif entre 2 backends de recherche
> HelloPro (Milvus vs Hybride Solr V2 + Typesense). Le but est de mesurer si
> le nouveau backend est au moins équivalent au Milvus historique.
>
> **Entrée** : le CSV
> `C:\RIJA\CLAUDE_CODE\opti_moteur\RAG-HP-PUB\bench_production\keywords_coverage_v1.csv`
> (150 mots-clés, 5 buckets).
>
> **Procédure pour chaque mot-clé** :
> 1. Naviguer sur l'URL Milvus, attendre le rendu, extraire les 10 premiers
>    noms de produits + temps de chargement.
> 2. Naviguer sur l'URL Hybride (`&ajax=1`), attendre le rendu (y compris
>    AJAX page 1 extension), extraire les 10 premiers noms de produits.
> 3. Calculer pour ce mot-clé :
>    - **Overlap top-10** = nb produits communs / 10
>    - **Top-1 stable** = oui/non
>    - **Coverage tokens** = pour chaque top-10 H, est-ce que tous les tokens
>      du mot-clé apparaissent dans le nom (boolean) ?
>    - **Latence** = temps de chargement en ms (côté Chrome)
> 4. Sauvegarder ligne dans
>    `bench_production/bench_results/results_{timestamp}.csv` avec colonnes :
>    `keyword, bucket, milvus_top10, hybrid_top10, overlap_top10,
>    top1_stable, milvus_coverage, hybrid_coverage, milvus_ms, hybrid_ms,
>    note`
>
> **Stratégie d'exécution** :
> - Batch 1 (150 mots-clés × 2 backends = 300 navigations) en ~2-3h en
>   background. Si timeout, reprendre où tu en es via `keyword` déjà présent
>   dans le CSV results.
> - Pour les buckets `audit_history` et `zero_result`, capturer un screenshot
>   en plus pour Elena (sauvegarder dans `bench_results/screenshots/`).
>
> **Sortie finale** : générer un rapport HTML
> `bench_production/bench_report_2026-XX-XX.html` avec :
> - Tableau global par bucket : moyenne overlap, % top-1 stable, p95 latence
> - Top 20 cas où l'hybride dégrade (overlap < 50% ou top1 instable)
> - Top 20 cas où l'hybride améliore (overlap stable + coverage améliorée)
> - Annexe : tableau exhaustif des 150 mots-clés

## 4. Critères de décision (à figer avec Elena)

| Métrique | Seuil "GO bascule" | Seuil "Investigation" |
|---|---|---|
| Overlap top-10 moyen | ≥ 70 % | 50-70 % |
| Top-1 stable | ≥ 80 % | 60-80 % |
| Coverage tokens moyenne hybride | ≥ coverage Milvus | < Milvus |
| Latence p95 hybride | ≤ 1.5 × Milvus | > 1.5× |
| Cas dégradés (overlap < 50%) | < 10 % | 10-25 % |

Si **2+ métriques en "investigation"** → bloquer la bascule, retourner sur
optimisations ciblées.

## 5. Annotation Elena top-20 catégories sensibles

Une fois le rapport généré, soumettre à Elena pour annotation :
- Sélectionner les 20 mots-clés avec :
  - Bucket `audit_history` (10 mots-clés)
  - OU overlap < 60% détecté (10 nouveaux mots-clés)
- Envoyer le rapport HTML + screenshots
- Elena annote chaque cas : "Hybride meilleur" / "Milvus meilleur" / "Équivalent"
- Score final = ratio Hybride meilleur ∪ Équivalent / total

**Critère final** : si ≥ 70 % "Hybride meilleur ou équivalent" sur les 20 cas
critiques Elena → **GO bascule**.

## 6. Reprise si interruption

Le script doit être idempotent. Pour reprendre :
1. Lire `bench_results/results_*.csv` (le plus récent)
2. Sauter les mots-clés déjà présents
3. Continuer

## 7. Estimation effort

| Étape | Durée |
|---|---|
| Setup + lancement | 5 min |
| Bench batch 1 (150 × 2) | 2-3h (Claude Desktop background) |
| Génération rapport HTML | 10 min |
| Review interne avant Elena | 20 min |
| Annotation Elena | 1-2 jours |
| Décision finale | 15 min |

**Total** : ~3-4h de Claude Desktop active + 1-2 jours d'attente Elena.

## 8. Plan B si bench Claude Desktop trop lent

Fallback PowerShell direct :
```powershell
# Adapter smoke_test_bascule.ps1 pour lire le CSV 150 mots-cles
# et appeler les 2 modes (default + ?ajax=1) sans navigation Chrome.
# Output JSON brut, post-traitement par script Python pour generer
# overlap + coverage + rapport HTML.
.\bench_production\smoke_test_bascule.ps1 -Phase pre -KeywordsFile bench_production\keywords_coverage_v1.csv
```

Plus rapide (~30 min total) mais sans screenshots ni latence côté navigateur.

---

## 9. Lien

- PR bascule : https://github.com/Hellopro-fr/RAG-HP-PUB/pull/622
- Doc spec bascule : `site/moteur_recherche/BASCULE_DEFAULT_HYBRID_2026-05-22.md`
- Mots-clés : `bench_production/keywords_coverage_v1.csv`
- Smoke test post-déploiement : `bench_production/smoke_test_bascule.ps1`
