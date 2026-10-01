# Ingestion batch 2 — 7 sections restantes

Ce dossier contient les catégories à ingérer pour **compléter la couverture** du
moteur Typesense avec les 7 sections HelloPro qui manquaient après le POC
initial (Industrie + Santé, ingérés dans `produits_scale`).

## 📋 Fichiers

| Fichier | Contenu |
|---|---|
| `categories_from_roots_2.csv` | **Source** : id, nom, type, depth, parent, nb_produits — 2246 catégories feuilles |
| `categories_from_roots_2.txt` | **Input pour le script d'ingestion** : 1 nom de catégorie par ligne (déduplique les doublons de noms CSV) |

## 🎯 Couverture ajoutée

7 sections racines (niveau 1) :
- `1000005` Hydraulique-pneumatique
- `1000003` Électricité-électronique
- `1000012` Sécurité
- `1000013` Logistique
- `1000011` Génie climatique
- `9000312` Outillage et fournitures industrielles
- `1000014` Équipements d'entreprises

**Total estimé : ~317 000 produits** (6× la taille de l'ingestion POC initiale).

## 🚀 Procédure d'ingestion sur la VM

### 1. Pull le repo

```bash
cd /home/devhp/RAG-HP-PUB
git pull
```

### 2. Configurer les variables d'env (Milvus + Typesense)

Le script `vm/ingest_by_categories.py` utilise les mêmes credentials que le
POC. Charger le `.env` du microservice (ou exporter manuellement) :

```bash
cd apps-microservices/opti-moteur-front

# Charger les creds depuis le .env du service
export $(grep -E '^(ZILLIZ_|MILVUS_|TS_)' .env | xargs)

# Renommer pour matcher les noms attendus par le script d'ingestion
export MILVUS_HOST="$ZILLIZ_URI"
export MILVUS_PORT="$ZILLIZ_PORT"
export MILVUS_USER="$ZILLIZ_USER"
export MILVUS_PASSWORD="$ZILLIZ_PASSWORD"
export MILVUS_COLLECTION="produits_3"

export TS_HOST="localhost"
export TS_PORT="8108"
export TS_API_KEY="hp_poc_2026"

# CIBLE : meme collection que l'ingestion POC (= merge additif)
export TS_COLLECTION="produits_scale"
```

⚠️ **Important** : cibler la même collection `produits_scale` permet un
ingest **additif** (les anciens produits Industrie+Santé restent, on ajoute
les 7 sections par-dessus). L'upsert Typesense dédoublonne naturellement sur
`id`.

### 3. Lancer l'ingestion (détaché + log)

```bash
cd /home/devhp/RAG-HP-PUB/apps-microservices/opti-moteur-front/vm

# Chemin du fichier texte (depuis la racine du repo)
export CATEGORIES_FILE=/home/devhp/RAG-HP-PUB/rubriques/categories_from_roots_2.txt

# Lancement detache, log fichier (~70 min estimé pour 317k produits)
nohup python3 -u ingest_by_categories.py > /tmp/ingest_batch2.log 2>&1 &
echo "PID: $!"
```

### 4. Monitoring

```bash
# Suivre le log en direct
tail -f /tmp/ingest_batch2.log

# Progression Typesense (nombre total de docs)
curl -s -H "X-TYPESENSE-API-KEY: hp_poc_2026" \
  http://localhost:8108/collections/produits_scale \
  | python3 -c 'import sys,json; d=json.load(sys.stdin); print("num_documents:", d["num_documents"])'

# Temps CPU/RAM de Typesense
docker stats --no-stream typesense-opti-moteur
```

### 5. Validation post-ingest

Une fois terminé, tester quelques queries qui étaient auparavant "ABSENT" :

```bash
# Armoire de securite (section Securite = 1000012, pas dans POC initial)
curl -s -X POST http://localhost:8570/search/text \
  -H "Content-Type: application/json" \
  -d '{"query":"armoire securite","top_k":5,"candidates":500}' \
  | python3 -c 'import sys,json; d=json.load(sys.stdin); print("cat=",d.get("detected_category")," cand=",d.get("total_candidates")); [print(" -",h["nom_produit"][:60]," |",h["categorie"]) for h in d.get("results",[])[:5]]'

# Vestiaire metallique (section Equipements = 1000014)
curl -s -X POST http://localhost:8570/search/text \
  -H "Content-Type: application/json" \
  -d '{"query":"vestiaire metallique","top_k":5,"candidates":500}' \
  | python3 -c 'import sys,json; d=json.load(sys.stdin); print("cat=",d.get("detected_category")," cand=",d.get("total_candidates")); [print(" -",h["nom_produit"][:60]," |",h["categorie"]) for h in d.get("results",[])[:5]]'

# Compresseur atelier (section Outillage = 9000312)
curl -s -X POST http://localhost:8570/search/text \
  -H "Content-Type: application/json" \
  -d '{"query":"compresseur air atelier","top_k":5,"candidates":500}' \
  | python3 -c 'import sys,json; d=json.load(sys.stdin); print("cat=",d.get("detected_category")," cand=",d.get("total_candidates")); [print(" -",h["nom_produit"][:60]," |",h["categorie"]) for h in d.get("results",[])[:5]]'
```

Les résultats doivent maintenant être pertinents (catégorie détectée avec
`conf > 0.8` et produits du bon domaine).

## 🧯 Reprise en cas d'interruption

Si l'ingestion est coupée (Ctrl+C, crash, timeout VM), relance simplement le
script. L'upsert Typesense re-inscrit les mêmes produits sans effet de bord.

Pour accélérer (ignorer ce qui est déjà ingéré) :
```bash
export SKIP_EXISTING=1
# Relance la meme commande qu'avant
```
