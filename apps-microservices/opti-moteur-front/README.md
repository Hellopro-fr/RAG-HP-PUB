# Opti Moteur Front — POC Typesense / OpenSearch vs Milvus

POC de remplacement du moteur de recherche produit front (actuellement Milvus)
par **Typesense** et **OpenSearch** pour atteindre **< 2s de latence** avec une
pertinence P@5 ≥ 80% sur les requêtes commerciales courtes (1–3 mots).

## 🎯 Contexte

Les commerciaux se plaignent que la recherche produit Milvus renvoie des
résultats peu pertinents sur des requêtes courtes type « armoire médicale »
(les produits attendus remontent en 20e position au lieu du top 5), avec une
latence de **5–7 s**. Objectif : **< 2 s, top-5 pertinent**.

## 📊 Résultats clés

Benchmark sur **26 requêtes commerciales** × dataset **34 301 produits**
(extraits de Milvus prod, embeddings CamemBERT-large 1024 dims identiques).

| Méthode | P@5 | P@10 | Latence moy |
|---|---|---|---|
| Milvus prod (baseline) | ~? | ~? | **5000–7000 ms** 🔴 |
| 🥇 **Typesense Hybrid + filter_by** | **80%** | **79%** | **147 ms** ⚡ |
| Typesense Sémantique pur (≈Milvus) | 69% | 62% | 31 ms |
| Typesense BM25 pur | 62% | 58% | 32 ms |
| OpenSearch BM25 | 66% | 62% | 59 ms |
| OpenSearch kNN pur | 69% | 62% | 73 ms |
| OpenSearch Hybrid | 67% | 63% | 67 ms |
| OpenSearch Hybrid v2 (filter) | 67% | 64% | 69 ms |

→ voir [`reports/bench_report_final.html`](reports/bench_report_final.html)
pour le détail visuel par requête.

## 🧩 Innovations du moteur Typesense (`search_v2.py`)

1. **Détection automatique de catégorie** via facet search sur `categorie`
2. **Prefix-match tolérant sg/pl** : query « signalisation securite » matche
   catégorie « Signalisations sécurité travail »
3. **Hard filter par catégorie** quand confiance ≥ 80% et prefix-match OK
4. **Re-rank Python pondéré** sur top 50 candidats :
   `final = 0.55·vecteur + 0.10·BM25 + 0.25·match_nom + 0.10·match_categorie`
5. **Pénalité** sur les hits « BM25-only » (vec < 0.20 AND name_match < 50%)

## 📁 Structure

```
opti-moteur-front/
├── README.md                          ← vous êtes ici
├── .gitignore
│
├── local/                             Scripts pour poste de dev (Windows/macOS/Linux)
│   ├── docker-compose.yml             Typesense 27.1 single node
│   ├── requirements.txt
│   ├── search_v2.py                   ⭐ Moteur principal (detection cat + re-rank)
│   ├── search_local.py                Benchmark simple
│   ├── benchmark_panel.py             Panel 26 queries → bench_results.json
│   ├── benchmark_opensearch.py        Bench OpenSearch (BM25 / kNN / Hybrid)
│   ├── benchmark_opensearch_v2.py     Bench OS avec filter_by categorie
│   ├── compute_metrics.py             Calcul P@5 / P@10 vs ground truth
│   ├── generate_report_final.py       Rapport HTML 5-way + color-coded
│   ├── ingest_typesense.py            Ingestion d'un JSONL dans Typesense
│   ├── ingest_camembert.py            Ingestion POC initial (42 produits)
│   ├── inspect_categories.py          Debug distribution catégories
│   ├── merge_queries.py               Merge embeddings de queries
│   ├── synonyms.json                  Exemple synonymes métier B2B
│   └── data/
│       ├── query_embeddings.json      26 requêtes pré-embeddées CamemBERT
│       └── ground_truth.json          Catégories attendues par requête
│
├── vm/                                Scripts pour VM Linux (accès Milvus direct)
│   ├── README_VM.md
│   ├── docker-compose.yml             Typesense avec volume persist
│   ├── docker-compose-full.yml        Typesense cap RAM 32 GB (prod-scale)
│   ├── requirements.txt               pymilvus + typesense + tqdm
│   ├── export_from_milvus.py          Export JSONL depuis Milvus (2 phases)
│   ├── stream_milvus_to_typesense.py  Ingestion streaming directe (pas de JSONL)
│   ├── ingest_by_categories.py        Ingestion par liste de catégories
│   ├── ingest_typesense.py            Variante simple
│   ├── search.py                      Benchmark sur VM avec baseline Milvus
│   ├── debug_milvus.py                Debug connexion / filtres Milvus
│   └── find_categories.sql            SQL recursif (alternative aux scripts PHP)
│
├── ecrtel/                            Scripts PHP pour l'hébergeur prod
│   ├── build_categories_list.php      Par keywords → niveau_1 → leaves
│   └── build_categories_from_roots.php Par rubriques racines → BFS descendants
│
└── reports/                           Rapports HTML (pour présentation)
    ├── bench_report.html              Première version
    ├── bench_report_3way.html         OpenSearch vs Typesense
    └── bench_report_final.html        ⭐ Version finale avec P@5/P@10 color-coded
```

## 🚀 Quickstart local

```bash
cd local

# 1. Lancer Typesense
docker compose up -d
curl http://localhost:8108/health    # attendu {"ok":true}

# 2. Dépendances Python
pip install -r requirements.txt

# 3. Ingérer un JSONL (extrait depuis Milvus via vm/export_from_milvus.py)
INPUT=data/merged_30k.jsonl TS_COLLECTION=produits_30k \
  python3 ingest_typesense.py

# 4. Benchmark complet
TS_COLLECTION=produits_30k python3 benchmark_panel.py
python3 compute_metrics.py
python3 generate_report_final.py
# → ouvrir bench_report_final.html
```

## 🏭 Déploiement VM

Voir [`vm/README_VM.md`](vm/README_VM.md).

Pipeline typique :
1. **ecrtel/build_categories_from_roots.php** → `categories_from_roots.txt`
   (liste des rubriques leaves sous Fabrication & Santé par exemple)
2. Transfert du `.txt` sur la VM
3. **vm/ingest_by_categories.py** → streaming Milvus → Typesense, par catégorie

```bash
# Sur la VM, après sourcing du .env RAG-HP-PUB
MILVUS_HOST=$ZILLIZ_URI MILVUS_PORT=$ZILLIZ_PORT \
MILVUS_USER=$ZILLIZ_USER MILVUS_PASSWORD=$ZILLIZ_PASSWORD \
CATEGORIES_FILE=categories_from_roots.txt \
TS_COLLECTION=produits_prod \
EXTRA_FILTER='etat in ["Client","Prospect"] or (etat == "Pause" and affichage == "Complet")' \
python3 ingest_by_categories.py | tee ingestion.log
```

Le script affiche après chaque catégorie : `chunks_ingérés`, `docs_total_typesense`, `disque_libre_restant`.

## 📐 Sizing prod (2,24 M chunks Milvus)

| Ressource | Besoin | Notes |
|---|---|---|
| RAM Typesense | 25–30 GB | `mem_limit: 32g` dans docker-compose-full.yml |
| Disque Typesense data | 30–40 GB | |
| Ingestion | ~1–2 h streaming | 500–2000 docs/s selon CPU/réseau |
| 1ère query (cold HNSW) | 30 s – 2 min | |
| Queries suivantes | 50–200 ms | |

## 🗺️ Roadmap

- [x] POC local 42 produits (42 dims fictifs) — CamemBERT 1024
- [x] Benchmark 34k produits réels
- [x] Comparaison OpenSearch vs Typesense
- [x] Métriques P@5 / P@10 sur ground truth
- [x] Prefix-match catégorie + re-rank Python
- [ ] Scale-test VM 2,24 M chunks
- [ ] Collecte queries réelles commerciaux
- [ ] Dual-write Milvus + Typesense à `api-embedding-service`
- [ ] Canary 10% traffic en prod
- [ ] Déploiement GA

## 🔗 Références

- [Typesense hybrid search](https://typesense.org/docs/27.1/api/vector-search.html#hybrid-search)
- [OpenSearch kNN](https://opensearch.org/docs/latest/search-plugins/knn/index/)
- Structure catégories HelloPro : `rubrique_front` avec racine virtuelle `1000000`, sections = direct children, niveau_1 = grandchildren
