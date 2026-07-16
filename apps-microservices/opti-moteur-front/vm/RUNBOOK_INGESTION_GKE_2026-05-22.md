# Runbook : Ingestion Milvus → Typesense GKE (v2, via service Python)

**Date** : 2026-05-22 (v2)
**Statut** : Architecture clarifiée — tout passe par les routes HTTP du service
Python GKE, plus besoin d'accéder directement à Typesense interne.

**Source** : Milvus prod (`produits_3`), accessible **depuis le pod GKE** (vérifié
via `/sync/health` qui renvoie `"milvus":"ok"`).
**Cible** : Typesense GKE, **collection `produits_prod`**, atteint via
`POST /ingest/...` au service Python GKE `http://10.0.1.240:8570`.

**Durée totale estimée** : 4-8 h (selon volume catalogue Milvus).

---

## Architecture (clarifiée)

```
   [VM GCP devhp]                  [GCP private network]              [GKE cluster]
   ──────────────                  ─────────────────────              ─────────────
                                                                   ┌─────────────────────┐
   migrate_to_gke.sh ───── HTTP ──> http://10.0.1.240:8570 ──────> │ opti-moteur-front   │
   (curl + checkpoints)            (ingress GKE)                   │  /ingest/...        │
                                                                   │  /sync/...          │
                                                                   │  /admin/...         │
                                                                   └─┬─────────────────┬─┘
                                                                     │                 │
                                                                     ▼                 ▼
                                                          ┌──────────────┐  ┌──────────────┐
                                                          │ Milvus prod  │  │ Typesense    │
                                                          │  produits_3  │  │ GKE pod      │
                                                          └──────────────┘  └──────────────┘
```

⚠️ **Ce que `10.0.1.240:8570` N'EST PAS** : ce n'est pas le Typesense GKE direct.
C'est le **microservice Python `opti-moteur-front`** qui sert d'orchestrateur.
On l'a confirmé via `curl /health` qui retourne :
```json
{"status":"ok","typesense":"ok","milvus":"ok"}
```
(format service Python, pas Typesense pur qui répondrait `{"ok":true}`).

---

## Pré-requis (3 min)

### A. Connectivité depuis la VM

```bash
curl -s http://10.0.1.240:8570/sync/health | jq .
# Attendu :
# {
#   "status": "ok",
#   "milvus": "ok (XXXXXXX entities, collection=produits_3)",
#   "typesense": "ok (NNNNNNN docs, collection=produits_prod)"
# }
```

Si timeout → joindre Tafita (firewall VPC GCP).

### B. SYNC_TOKEN

Le token est défini dans l'env du pod GKE. Par défaut : `hp_sync_2026_04_30_xZ7q`.
À vérifier avec Tafita s'il a été changé en prod.

```bash
# Si different, exporter avant de lancer le script
export SYNC_TOKEN="<valeur reelle>"
```

### C. Liste catalogue Milvus

Le script utilise par défaut `rubriques/categories_from_roots.txt` comme source
de vérité (committé dans le repo). À refresh si manquant :

```bash
cd ~/RAG-HP-PUB/apps-microservices/opti-moteur-front/vm
export $(grep -E '^(ZILLIZ_|MILVUS_)' ../.env | xargs)
export MILVUS_HOST="$ZILLIZ_URI" MILVUS_PORT="$ZILLIZ_PORT"
export MILVUS_USER="$ZILLIZ_USER" MILVUS_PASSWORD="$ZILLIZ_PASSWORD"
python3 list_missing_categories.py
# Genere rubriques/categories_missing.txt
```

---

## Procédure en 1 commande

```bash
cd ~/RAG-HP-PUB
git pull origin features/poc
bash apps-microservices/opti-moteur-front/vm/migrate_to_gke.sh
```

Le script gère 5 étapes interactives (Y/N à chaque palier), avec checkpoints
dans `/tmp/migrate_gke_checkpoints/` pour reprise.

### Étapes orchestrées

| # | Action | Route HTTP | Durée |
|---|---|---|---|
| 1 | Créer collection si absente | `POST /admin/collections/produits_prod` | < 1 s |
| 2 | Préparer liste catégories | (lecture fichier) | < 1 s |
| 3 | Ingestion chunked (CHUNK_SIZE catégories à la fois) | `POST /ingest/categories/batch` | ~4-8 h |
| 4 | Sync delta + orphelins | `POST /sync/incremental` (token) | 5-30 min |
| 5 | Régénération IDF | **manuel** (kubectl exec sur pod) | 1-5 min |

### Options

```bash
# Run non-interactif (CI / nohup)
AUTO=1 bash apps-microservices/opti-moteur-front/vm/migrate_to_gke.sh

# Lancer en background avec log
nohup bash apps-microservices/opti-moteur-front/vm/migrate_to_gke.sh \
    > /tmp/migrate_gke_$(date +%Y%m%d).log 2>&1 &
tail -f /tmp/migrate_gke_*.log

# Custom catalogue source
CATEGORIES_FILE=~/RAG-HP-PUB/rubriques/categories_missing.txt \
    bash apps-microservices/opti-moteur-front/vm/migrate_to_gke.sh

# Chunk plus petit (si timeout HTTP sur l'API)
CHUNK_SIZE=10 bash apps-microservices/opti-moteur-front/vm/migrate_to_gke.sh
```

---

## Monitoring (autre terminal)

```bash
# Compteur docs Typesense GKE
watch -n 60 'curl -s http://10.0.1.240:8570/admin/collections/produits_prod \
              | jq ".num_documents"'

# Logs detailles par chunk
ls -lt /tmp/migrate_gke_logs/ | head -20
tail -f /tmp/migrate_gke_logs/step3_chunk_*.json | jq .

# Etat des checkpoints
ls -lh /tmp/migrate_gke_checkpoints/
cat /tmp/migrate_gke_checkpoints/step3_progress.txt  # ligne actuelle dans le CSV
```

---

## Reprise après interruption

Le script est **idempotent** (upsert Typesense) et **resumable** (checkpoints).

```bash
# Reprendre où on s'est arreté
bash apps-microservices/opti-moteur-front/vm/migrate_to_gke.sh

# Force reset complet (refaire from scratch)
rm -rf /tmp/migrate_gke_checkpoints
bash apps-microservices/opti-moteur-front/vm/migrate_to_gke.sh
```

---

## Étape 5 — IDF (action manuelle Tafita)

Le service ne pousse PAS encore d'endpoint admin `/admin/compute-idf` (TODO
future). Pour régénérer :

```bash
# Sur la machine qui a kubectl/GKE acces (Tafita ou toi via gcloud auth)
POD=$(kubectl get pod -l app=opti-moteur-front -o jsonpath='{.items[0].metadata.name}')
kubectl exec -it $POD -- python scripts/compute_idf.py
kubectl rollout restart deployment opti-moteur-front
sleep 30
kubectl logs --tail=30 -l app=opti-moteur-front | grep -i "IDF"
# Attendu : "IDF loaded from idf_nom_produit.json : NNNNNN tokens, ..."
```

⚠️ **Persistance critique** : `app/data/idf_nom_produit.json` doit être sur un
**PVC** (PersistentVolumeClaim) Kubernetes, sinon il sera perdu au prochain
redéploiement. À vérifier avec Tafita. Sinon prévoir un `initContainer` qui
regénère l'IDF au démarrage.

**Alerte 22/05** : le fichier était absent du `app/data/` de la VM, signe que
la persistance n'était peut-être déjà pas assurée côté VM. À reproduire sur
GKE : `kubectl describe pod opti-moteur-front | grep -A5 Volumes`.

---

## Smoke test post-ingestion (depuis Windows)

Une fois les 5 étapes vertes :

```powershell
cd C:\RIJA\CLAUDE_CODE\opti_moteur\RAG-HP-PUB
.\bench_production\smoke_test_bascule.ps1 -Phase post
```

Critère : tous les `armoire medicale`, `ritmo`, `urinoir delabie`, `e-crane`,
`lockers bagagerie` retournent leurs top-1 attendus (cf audits Elena).

---

## Bascule par défaut (PR #622 déjà mergée)

Côté Ecritel, vérifier que `moteur_recherche.php` contient bien la ligne :
```php
if (!defined('HP_USE_HYBRID_SEARCH')) define('HP_USE_HYBRID_SEARCH', true);
```

Test final :
```bash
# URL default doit retourner mode hybride (marker HP_QUALITY_P1)
curl -s "https://www.hellopro.fr/moteur_recherche/recherche_resultat.php?type_recherche=produit&recherche_active=1&mot_cles=ritmo" \
  | grep -o 'HP_QUALITY_P1:\s*regime=\w*'
```

---

## Plan de rollback

| Niveau | Action | Délai |
|---|---|---|
| URL | `?legacy=1` sur l'URL de test | 0 s |
| Front | `HP_USE_HYBRID_SEARCH=false` + redéploy Ecritel | 5 min |
| Infra | Tafita repointe gateway sur ancien backend Milvus | 10 min |

---

## Monitoring J+1

| Métrique | Source | Seuil alerte |
|---|---|---|
| `num_documents` Typesense GKE | `GET /admin/collections/produits_prod` | < 95 % target |
| Latence p95 `/search/text` | logs opti-moteur-front | > 1.5 s |
| Taux 5xx | gateway api.hellopro.eu | > 1 % |
| Plaintes Elena | Slack #moteur-recherche | 0 attendu |

---

## Liens

- Script wrapper : [`migrate_to_gke.sh`](./migrate_to_gke.sh)
- API ingestion : `app/router/ingest.py` (`POST /ingest/categories/batch`)
- API sync : `app/router/sync.py` (`POST /sync/incremental`)
- API admin : `app/router/admin.py`
- Doc bascule par défaut : [`../../../site/moteur_recherche/BASCULE_DEFAULT_HYBRID_2026-05-22.md`](../../../site/moteur_recherche/BASCULE_DEFAULT_HYBRID_2026-05-22.md)
- PR bascule (mergée) : https://github.com/Hellopro-fr/RAG-HP-PUB/pull/622
- PR ce runbook : https://github.com/Hellopro-fr/RAG-HP-PUB/pull/623
