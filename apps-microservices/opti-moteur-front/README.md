# opti-moteur-front

Microservice FastAPI : **moteur de recherche produit front** pour HelloPro, en remplacement de Milvus (qui met 5–7 s actuellement).

- **Backend**: Typesense 27.1 (hybrid BM25 + kNN natif)
- **Embeddings**: CamemBERT-large 1024 dims (identiques à Milvus prod)
- **Pertinence**: détection catégorie + prefix-match + re-rank Python pondéré
- **Cible**: P@5 ≥ 80%, latence < 200 ms (vs 5–7 s Milvus prod)

## 📊 Résultats benchmark

26 requêtes commerciales × 34 301 produits extraits de Milvus prod :

| Moteur | P@5 | P@10 | Latence moy |
|---|---|---|---|
| Milvus prod (baseline) | — | — | ~5–7 s 🔴 |
| 🏆 **Typesense + filter_by** | **80%** | **79%** | 147 ms |
| OpenSearch Hybrid | 67% | 63% | 67 ms |

→ détail dans `reports/bench_report_final.html`

## 🏗 Architecture

```
app/
├── core/
│   ├── credentials.py        # Settings pydantic (ZILLIZ_*, TYPESENSE_*)
│   ├── milvus_connector.py   # Singleton Milvus (query async via to_thread)
│   └── typesense_client.py   # Singleton Typesense + helpers collection
├── utils/
│   └── text.py               # tokenize, normalize, is_prefix_match
├── services/
│   ├── category_detector.py  # Facet search + prefix-match filter
│   ├── reranker.py           # Formule rerank pondérée
│   ├── search_service.py     # Pipeline complet (detect + hybrid + rerank)
│   └── ingestion_service.py  # Streaming Milvus → Typesense par catégorie
├── schemas/                  # Pydantic (SearchRequest/Response, Ingest)
└── router/                   # FastAPI routes (search, ingest, admin)
```

## 🚀 Installation locale

```bash
cd apps-microservices/opti-moteur-front
./init.sh                     # crée .venv + install deps
cp .env.example .env          # éditer avec les vrais credentials ZILLIZ_*
./run.sh                      # uvicorn --reload sur :8570
```

## 🐳 Docker

```bash
docker compose up -d
curl http://localhost:8570/health
```

## 📡 API Endpoints

### `GET /` — root
```json
{"message": "Bienvenue sur l'API OPTI-MOTEUR-FRONT v1.0.0"}
```

### `GET /health`
Verifie Typesense + Milvus.
```json
{"status": "ok", "typesense": "ok", "milvus": "ok"}
```

### `POST /search`
Hybrid search avec détection catégorie + re-rank.
```json
{
  "query": "armoire medicale",
  "query_vector": [0.123, 0.456, ...],   // 1024 floats CamemBERT
  "top_k": 10,
  "apply_filter_by_category": true
}
```
Réponse :
```json
{
  "query": "armoire medicale",
  "detected_category": "Armoire médicale",
  "detection_confidence": 1.0,
  "filter_by_category": ["Armoire médicale"],
  "latency_ms": {"detect": 9, "typesense": 163, "rerank": 3, "total": 175},
  "total_candidates": 50,
  "results": [
    {
      "id_produit": "13142342",
      "nom_produit": "Armoire médicale ...",
      "categorie": "Armoire médicale",
      "score": 0.639,
      "scores_detail": {"vector": 0.34, "bm25": 0.0, "name_match": 1.0, "cat_match": 1.0, "penalty": ""}
    },
    ...
  ]
}
```

### `POST /ingest/category`
Ingère 1 catégorie depuis Milvus (blocking).
```json
{
  "categorie": "Armoire médicale",
  "extra_filter": "etat in [\"Client\",\"Prospect\"]",
  "batch_size": 1000
}
```

### `POST /ingest/categories/batch`
Ingère plusieurs catégories en série (avec garde-fou disque).

### `GET /admin/collections`
Liste des collections Typesense.

### `POST /admin/collections/{name}`
Crée une collection avec le schema standard (1024 dims, 23 fields).

### `DELETE /admin/collections/{name}?confirm=true`
Supprime une collection.

## 🔗 Dépendances

- Milvus prod (`ZILLIZ_*` envs) pour la source d'embeddings + metadata
- Typesense (standalone Docker ou Typesense Cloud)
- `api-embedding-service` pour embedder les queries au runtime (non inclus ici — à appeler avant `/search`)

## 📖 Pipeline d'ingestion complet

```
┌─────────────────────────────────────────────────────────────┐
│ 1. Build liste categories (scripts PHP sur ecrtel)          │
│    php build_categories_from_roots.php → categories.txt     │
└─────────────────────────────────────────────────────────────┘
              ↓
┌─────────────────────────────────────────────────────────────┐
│ 2. POST /ingest/categories/batch avec liste                 │
│    → streaming Milvus → Typesense                           │
│    → monitoring disque/docs par categorie                   │
└─────────────────────────────────────────────────────────────┘
              ↓
┌─────────────────────────────────────────────────────────────┐
│ 3. Queries temps reel :                                     │
│    • api-embedding-service embedd la query (1024 dims)      │
│    • POST /search avec query + vector                       │
│    • reponse en < 200ms                                     │
└─────────────────────────────────────────────────────────────┘
```

## 🧪 Tests

```bash
pytest tests/
```

## 🛠 TODO / Roadmap

- [ ] Tests unitaires sur `text.py`, `reranker.py`, `category_detector.py`
- [ ] Endpoint `/ingest/categories/batch/async` avec tâche de fond + status polling
- [ ] Intégration `common_utils.metrics.prometheus` (comme `api-rest-milvus`)
- [ ] Intégration `common_utils.concurrency.MilvusConcurrencyGuard`
- [ ] Synonymes métier B2B via Typesense `/synonyms` endpoint
- [ ] Canary A/B (feature flag) en front
