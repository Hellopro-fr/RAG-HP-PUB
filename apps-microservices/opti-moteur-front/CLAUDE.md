# CLAUDE.md — opti-moteur-front

## Contexte metier

Remplacement du moteur de recherche produit front (www.hellopro.fr) actuellement
base sur Milvus qui prend 5-7 secondes et renvoie des resultats peu pertinents
sur les requetes commerciales courtes (1-3 mots). Cible : **< 200 ms, P@5 >= 80%**.

## Decisions d'architecture

### 1. Backend Typesense (et non Milvus direct)
- Milvus est performant pour le RAG (long context, batch) mais lent et bruyant
  sur les requetes courtes.
- Typesense fait du hybrid BM25 + kNN nativement, avec latence 20-200 ms.
- OpenSearch est une alternative credible (testee dans reports/) mais plus
  d'overhead ops (JVM, Dashboards).

### 2. Embeddings CamemBERT-large identiques a Milvus prod
- Meme modele pour eviter la re-vectorisation de 2,24 M produits.
- Les embeddings sont pulles directement depuis Milvus (`produits_3`).
- Le service d'embedding `api-embedding-service` fournit la meme fonction pour
  les queries au runtime.

### 3. Pipeline de pertinence specifique HelloPro
La formule de ranking est metier-specifique :
```
final_score = 0.55 * cosine_vector
            + 0.10 * bm25_normalise
            + 0.25 * tokens_match_nom_produit
            + 0.10 * tokens_match_categorie
```
Penalite x0.3 si (vec < 0.20 AND name_match < 0.50) : elimine les faux positifs
BM25 sur des tokens fortuits (ex: "18V" qui matche des batteries pour requete
"perceuse 18V").

### 4. Detection categorie avec "prefix-match tolerant"
- Recherche de la categorie dominante via facet Typesense.
- Ne garde la categorie pour filter_by que si les tokens de la query
  apparaissent dans les premiers mots du nom (avec tolerance sg/pl).
- Exemples :
  - query="batterie lithium" vs cat="Armoire de stockage batterie lithium"
    -> REJETE (batterie en position 4, pas un prefix match)
  - query="signalisation securite" vs cat="Signalisations securite travail"
    -> ACCEPTE (signalisation ~ signalisations via startswith bilateral)

## Conventions alignees avec le repo

- Settings via `pydantic_settings.BaseSettings` et `.env` file.
- Env vars Milvus : `ZILLIZ_URI`, `ZILLIZ_PORT`, `ZILLIZ_USER`, `ZILLIZ_PASSWORD`
  (meme que `api-rest-milvus`, `database-recherche-service`, etc).
- Singleton pattern pour les connecteurs (comme `milvus_connector` dans
  graph-rag-milvus-service).
- Async I/O via `asyncio.to_thread` pour wrap le pymilvus sync.
- FastAPI avec `lifespan` async pour warm-up, router par feature, monitoring
  `/health`.

## Workflow type (POC validation)

1. Extraire la hierarchie categories cibles (ecrtel PHP).
2. `POST /admin/collections/produits_poc` -> cree la collection Typesense.
3. `POST /ingest/categories/batch` avec la liste des categories feuilles.
4. Embedder quelques queries test via `api-embedding-service`.
5. `POST /search` -> valider P@5 + latence.
6. Pousser en canary sur une fraction du traffic front.

## Ce qu'il reste a faire

Voir la roadmap du README. En priorite :
1. Tests unitaires text.py + reranker.py (logique pure, faciles a tester).
2. Async batch ingestion avec suivi de status.
3. Integration Prometheus pour suivi SLO (P@5, P@95 latence) en prod.

## Structure code

Respecter `app/{core,services,router,schemas,utils}/` :
- `core/` : connecteurs infra (Milvus, Typesense)
- `utils/` : fonctions pures stateless (tokenize, normalize)
- `services/` : logique metier (detection, rerank, ingestion)
- `schemas/` : contrats API pydantic
- `router/` : routes FastAPI thin, deleguent aux services
