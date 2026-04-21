# POC Typesense 200k — Déploiement VM Linux

Déploiement sur `/home/devhp/rvl/` avec accès direct Milvus prod.

## Prérequis VM

- Docker + Docker Compose installés
- Python 3.8+
- ~12 GB RAM libres (Typesense + index)
- ~15 GB disque libres (JSONL export + Typesense data)
- Accès réseau à `milvus-prod.hello.dev.private.com:19530`

## Installation

```bash
cd /home/devhp/rvl/
pip3 install -r requirements.txt
```

Copier le fichier des requêtes pré-embeddées depuis le POC Windows :
```bash
# Depuis ta machine Windows vers la VM
scp C:\RIJA\CLAUDE_CODE\poc_typesense\data\query_embeddings.json \
    devhp@VM:/home/devhp/rvl/data/
```

Lancer Typesense :
```bash
docker compose up -d
curl http://localhost:8108/health   # doit retourner {"ok":true}
```

## Pipeline en 3 étapes

### 1. Export Milvus → JSONL (~15-25 min)

```bash
python3 export_from_milvus.py
```

Output : `data/products_200k.jsonl` (~2-3 GB, 400k-600k chunks)

Options via env vars :
```bash
# Subset plus petit pour tester d'abord
TARGET_UNIQUE=20000 OUTPUT=data/subset_20k.jsonl python3 export_from_milvus.py

# Filtre Phase 1 custom (ex. sans filtre etat)
PHASE1_FILTER='chunk_number == 0' python3 export_from_milvus.py
```

### 2. Ingestion Typesense (~5-10 min)

```bash
python3 ingest_typesense.py
```

Output : collection `produits_200k` avec ~500k documents (1024-dim vectors).

Options :
```bash
INPUT=data/subset_20k.jsonl TS_COLLECTION=produits_20k python3 ingest_typesense.py
BATCH=5000 python3 ingest_typesense.py   # plus rapide si RAM OK
```

### 3. Benchmark

```bash
python3 search.py                       # 4 requetes par defaut
python3 search.py "armoire medicale"   # une requete specifique
```

La 1ère recherche vectorielle déclenche la construction HNSW (~30s-2min),
les suivantes sont en 30-100ms.

## Interprétation des résultats

Le script affiche 4 blocs par requête :
1. **TS Semantique pur** — simule exactement Milvus (vecteur seul)
2. **TS BM25 pur** — keyword seul
3. **TS Hybrid** — BM25 + vecteur avec `query_by_weights` dynamique
4. **Milvus baseline** — pour vérifier la latence réelle prod

Comparer :
- **Latence** : gain Typesense vs Milvus (cible < 200ms)
- **Pertinence** : les 10 premiers produits remontés sont-ils cohérents ?
- **Bruit** : Milvus semantique fait-il remonter `Batterie médicale` / `Flexible chauffant` sur la requête `armoire medicale` comme dans le screenshot d'Elena ?

## Requêtes pré-embeddées disponibles

Dans `data/query_embeddings.json` :
- `armoire medicale`
- `armoire médicale`
- `armoire pharmacie`
- `armoire pour médicaments hospitaliers`
- `meuble stockage médical`
- `pompe hydraulique`
- `chariot élévateur électrique`
- `armoire réfrigérée pour vaccins`
- `batterie lithium`
- `armoire sécurité inflammables`
- `extincteur`

Pour en ajouter : demander à embedder via MCP `rag_embed_text` puis merger dans `query_embeddings.json`.

## Sizing & monitoring

```bash
docker stats typesense-200k              # RAM + CPU en temps reel
docker exec typesense-200k df -h /data   # disque
curl -s http://localhost:8108/stats.json -H "X-TYPESENSE-API-KEY: hp_poc_2026" | jq
```

## Cleanup

```bash
docker compose down -v          # supprime le container + volume
rm -rf data/                    # supprime les JSONL exportes
```

## Troubleshooting

**Milvus timeout** : augmenter le timeout pymilvus dans `export_from_milvus.py` (connect `timeout=` param)

**Typesense OOM** : baisser `TARGET_UNIQUE` à 100k ou 50k

**Collection Milvus introuvable** : vérifier avec
```bash
python3 -c "from pymilvus import connections, utility; connections.connect(host='milvus-prod.hello.dev.private.com', port='19530'); print(utility.list_collections())"
```

**Ingestion lente** : monter `BATCH=5000` (nécessite ~2 GB RAM de marge)
