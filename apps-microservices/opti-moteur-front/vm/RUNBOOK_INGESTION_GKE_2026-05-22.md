# Runbook : Ingestion Milvus → Typesense GKE (toutes catégories + delta)

**Date** : 2026-05-22
**Contexte** : Migration définitive du moteur de recherche front. Le Typesense
GKE a déjà reçu une 1ère ingestion partielle. On finalise en (a) couvrant
toutes les catégories Milvus restantes, (b) supprimant les orphelins, (c)
régénérant l'IDF.

**Source** : Milvus prod (collection `produits_3`) accessible depuis la VM GCP
`vm-embedding-g2-std-24-use`.
**Cible** : Typesense GKE `http://10.0.1.240:8570`, collection `produits_prod`.

**Durée totale estimée** : 6-10 h (dont 5-8 h en background pour l'ingestion).

---

## Pré-requis sur la VM (à valider AVANT)

### A. `.env` à jour
Le `.env` de la VM doit contenir (au-delà des Milvus et embedding existants) :

```bash
# Cible Typesense GKE (NEW 2026-05-22)
TYPESENSE_HOST=10.0.1.240
TYPESENSE_PORT=8570
TYPESENSE_API_KEY=P8SRQOLdgrsq0gYZ1ZkbrJ8yRtY+l/A50MAo3OlnDMU=
TYPESENSE_COLLECTION=produits_prod
```

⚠️ La sortie `grep -E "TYPESENSE|EMBEDDING" .env` du 22/05 ne montrait que :
```
EMBEDDING_API_URL="https://api.hellopro.eu/embedding-service/embedding"
EMBEDDING_API_KEY="your_optional_embedding_api_key"
```
→ **Action** : ajouter le bloc TYPESENSE_* ci-dessus.

### B. Connectivité réseau

```bash
# Health Typesense GKE depuis la VM
curl -sf "http://10.0.1.240:8570/health" \
  -H "X-TYPESENSE-API-KEY: P8SRQOLdgrsq0gYZ1ZkbrJ8yRtY+l/A50MAo3OlnDMU=" | jq .
# Attendu : {"ok":true}
```

Si timeout → contacter Tafita pour vérifier le firewall GCP (VPC privé).

### C. Inventaire actuel Typesense GKE

```bash
# Total docs
curl -s "http://10.0.1.240:8570/collections/produits_prod" \
  -H "X-TYPESENSE-API-KEY: P8SRQOLdgrsq0gYZ1ZkbrJ8yRtY+l/A50MAo3OlnDMU=" | jq '.num_documents'

# Nb catégories distinctes (facet)
curl -s "http://10.0.1.240:8570/collections/produits_prod/documents/search?q=*&facet_by=categorie&per_page=0&max_facet_values=2000" \
  -H "X-TYPESENSE-API-KEY: P8SRQOLdgrsq0gYZ1ZkbrJ8yRtY+l/A50MAo3OlnDMU=" \
  | jq '.facet_counts[0].counts | length'
```

Noter les chiffres → comparaison avant/après.

---

## Étape 1 — Diff catégories Milvus vs Typesense (5 min)

```bash
cd ~/RAG-HP-PUB/apps-microservices/opti-moteur-front/vm

# Charger les credentials Milvus
export $(grep -E '^(ZILLIZ_|MILVUS_)' ../.env | xargs)
export MILVUS_HOST="$ZILLIZ_URI" MILVUS_PORT="$ZILLIZ_PORT"
export MILVUS_USER="$ZILLIZ_USER" MILVUS_PASSWORD="$ZILLIZ_PASSWORD"

# Lister catégories absentes du Typesense GKE
# NOTE : list_missing_categories.py compare avec rubriques/categories_from_roots*.txt
# Pour comparer dynamiquement avec Typesense GKE, voir migrate_to_gke.sh ci-dessous
python3 list_missing_categories.py

# Output :
#   ../../../rubriques/categories_missing.txt          (1 ligne / catégorie)
#   ../../../rubriques/categories_missing_chunks_NN.txt (lots de 100)

wc -l ../../../rubriques/categories_missing.txt
```

---

## Étape 2 — Ingestion (5-8 h en background)

```bash
# 1. Pointer Typesense GKE
export TS_HOST=10.0.1.240
export TS_PORT=8570
export TS_API_KEY='P8SRQOLdgrsq0gYZ1ZkbrJ8yRtY+l/A50MAo3OlnDMU='
export TS_COLLECTION=produits_prod

# 2. (Optionnel) filtre etat pour ne prendre que produits actifs
export EXTRA_FILTER='etat in ["Client","Pause","Prospect"]'

# 3. Lancer en nohup, log timestampé
LOG=/tmp/ingest_gke_$(date +%Y%m%d_%H%M).log
nohup python3 ingest_by_categories.py \
  CATEGORIES_FILE=../../../rubriques/categories_missing.txt \
  > $LOG 2>&1 &
echo "PID : $!"
echo "Log : $LOG"
```

### Monitoring en parallèle

```bash
# Suivre les logs
tail -f /tmp/ingest_gke_*.log

# Compteur Typesense GKE (toutes les 5 min)
watch -n 300 'curl -s "http://10.0.1.240:8570/collections/produits_prod" \
  -H "X-TYPESENSE-API-KEY: P8SRQOLdgrsq0gYZ1ZkbrJ8yRtY+l/A50MAo3OlnDMU=" \
  | jq ".num_documents"'

# RAM/CPU
docker stats opti-moteur-front 2>/dev/null
```

### Reprise après interruption

`ingest_by_categories.py` est idempotent (upsert + SKIP_EXISTING optionnel) :

```bash
SKIP_EXISTING=1 nohup python3 ingest_by_categories.py \
  CATEGORIES_FILE=../../../rubriques/categories_missing.txt \
  > /tmp/ingest_gke_resume_$(date +%Y%m%d_%H%M).log 2>&1 &
```

---

## Étape 3 — Cleanup orphelins (30 min)

```bash
cd ~/RAG-HP-PUB/apps-microservices/opti-moteur-front/vm

export $(grep -E '^(ZILLIZ_|MILVUS_)' ../.env | xargs)
export MILVUS_HOST="$ZILLIZ_URI" MILVUS_PORT="$ZILLIZ_PORT"
export MILVUS_USER="$ZILLIZ_USER" MILVUS_PASSWORD="$ZILLIZ_PASSWORD"
export TS_HOST=10.0.1.240 TS_PORT=8570
export TS_API_KEY='P8SRQOLdgrsq0gYZ1ZkbrJ8yRtY+l/A50MAo3OlnDMU='
export TS_COLLECTION=produits_prod

# DRY-RUN d'abord (compte sans supprimer)
DRY_RUN=1 python3 delete_orphans.py
# Doit afficher : "X orphelins detectes (dry-run, aucune suppression)"

# Si le X est raisonnable (< 5 % du total), supprimer pour de vrai
python3 delete_orphans.py
```

⚠️ Si X > 10 % du total → STOP, analyser pourquoi avant suppression.
Cas connus : filtre EXTRA_FILTER différent entre runs successifs.

---

## Étape 4 — Régénérer IDF (1-5 min)

Le fichier `app/data/idf_nom_produit.json` est **actuellement absent** sur la
VM (vérifié 22/05). Le reranker tourne donc en mode strict (perte de la
qualité A4 IDF). Régénération obligatoire après l'ingestion :

```bash
cd ~/RAG-HP-PUB/apps-microservices/opti-moteur-front

# 1. Pointer le script sur le Typesense GKE (sinon il pointe par défaut sur
#    le Typesense de la VM legacy)
export TYPESENSE_HOST=10.0.1.240
export TYPESENSE_PORT=8570
export TYPESENSE_API_KEY='P8SRQOLdgrsq0gYZ1ZkbrJ8yRtY+l/A50MAo3OlnDMU='

# 2. Génération via le container (toutes les deps déjà là)
docker compose exec opti-moteur-front python scripts/compute_idf.py

# 3. Vérifier que le fichier est apparu côté hôte (bind-mount)
ls -lh app/data/idf_nom_produit.json
# Attendu : ~20 MB, fraîchement créé

# 4. Recharger le service pour reprise du nouveau dict
docker compose restart opti-moteur-front
docker compose logs --tail 30 opti-moteur-front | grep -i "IDF"
# Attendu : "IDF loaded from idf_nom_produit.json : NNNN tokens, ..."
```

---

## Étape 5 — Sync synonymes GKE (5 min)

Vérifier que les synonymes sont bien sur le Typesense GKE :

```bash
curl -s "http://10.0.1.240:8570/collections/produits_prod/synonyms" \
  -H "X-TYPESENSE-API-KEY: P8SRQOLdgrsq0gYZ1ZkbrJ8yRtY+l/A50MAo3OlnDMU=" \
  | jq '.synonyms | length'
# Attendu : ~2000 clusters (1993 + synonymes manuels)
```

Si 0 ou très faible → lancer le script PHP de sync (côté hellopro.fr) :
```bash
# Sur le serveur hellopro.fr
php site/script/typesense/sync_synonyms_daily.php
```

---

## Étape 6 — Smoke test (10 min, depuis Windows)

Une fois tout déployé, vérifier que ça fonctionne via :

```powershell
cd C:\RIJA\CLAUDE_CODE\opti_moteur\RAG-HP-PUB
.\bench_production\smoke_test_bascule.ps1 -Phase post
```

Critère succès : tous les `armoire medicale`, `ritmo`, `urinoir delabie`,
`e-crane`, `lockers bagagerie` retournent leurs top-1 attendus.

---

## Étape 7 — Bascule par défaut (PR #622)

Une fois les étapes 1-6 vertes :

```bash
# Sur le serveur Ecritel
# 1. Vérifier le flag dans le PHP (doit être true post-merge PR #622)
grep "HP_USE_HYBRID_SEARCH" /var/www/.../hellopro_fr/moteur_recherche.php
# Attendu : if (!defined('HP_USE_HYBRID_SEARCH')) define('HP_USE_HYBRID_SEARCH', true);

# 2. Test URL legacy (rollback fonctionne)
curl -s "https://www.hellopro.fr/moteur_recherche/recherche_resultat.php?type_recherche=produit&recherche_active=1&mot_cles=ritmo&legacy=1" \
  | grep -i "HP_QUALITY_P1"

# 3. Test URL default (doit utiliser hybride)
curl -s "https://www.hellopro.fr/moteur_recherche/recherche_resultat.php?type_recherche=produit&recherche_active=1&mot_cles=ritmo" \
  | grep -i "HP_QUALITY_P1"
# Attendu : présence du marker HP_QUALITY_P1
```

---

## Monitoring J+1 post-ingestion

| Métrique | Source | Seuil alerte |
|---|---|---|
| `num_documents` Typesense GKE | `/collections/produits_prod` | < 95 % du target |
| Latence p95 `/search` | logs opti-moteur-front | > 1.5 s |
| Taux 5xx | gateway api.hellopro.eu | > 1 % |
| Plaintes Elena | Slack #moteur-recherche | 0 attendu |

---

## Plan de rollback (urgence)

Si dégradation détectée :

1. **Quick** (URL niveau) : passer toutes les URLs en `?legacy=1` côté front
2. **Medium** (5 min) : passer `HP_USE_HYBRID_SEARCH=false` + redéploy PHP
3. **Heavy** (10 min) : Tafita repointe la gateway sur l'ancien backend Milvus

---

## Fichiers liés

- Script wrapper : [`migrate_to_gke.sh`](./migrate_to_gke.sh) — orchestration auto
- Scripts d'ingestion existants : `ingest_by_categories.py`, `delete_orphans.py`,
  `list_missing_categories.py`, `compute_idf.py`
- Doc bascule : [`../../../site/moteur_recherche/BASCULE_DEFAULT_HYBRID_2026-05-22.md`](../../../site/moteur_recherche/BASCULE_DEFAULT_HYBRID_2026-05-22.md)
- PR #622 : https://github.com/Hellopro-fr/RAG-HP-PUB/pull/622
