# Configuration du Service de Recherche Vectorielle

## 1. Configuration Milvus/Zilliz
- Connection: ZILLIZ_URI, ZILLIZ_PORT (défaut 19530)
- Métrique: COSINE
- ef_search: 300 ou top_k * 2 (dynamique)
- M_PARAMS: 32, EF_PARAMS: 300

## 2. Top-K et Reranking
- Top-K par défaut: 10
- Top-K retrieval (avec reranker): top_k * 1.1 (10% marge)
- Top-K retrieval (sans reranker): top_k
- Reranker: BAAI/bge-reranker-v2-m3 (activé par défaut)

## 3. Embeddings
- Modèle: dangvantuan/sentence-camembert-large (1024 dims)
- Batch size: 64
- Chunk size: 500 caractères
- Chunk overlap: 100 caractères
- Service: embedding-model-service:50052 (gRPC)

## 4. Reranking
- Modèle: BAAI/bge-reranker-v2-m3 (multilingual)
- Service: reranking-model-service:50053 (gRPC)
- Output: Scores de pertinence (0-1)

## 5. Flux de Recherche
Query -> Embedding -> Milvus Search -> [Reranking] -> Results -> [LLM]

## 6. Fichiers Clés
- recherche.py: SearchOrchestrator (orchestration)
- search.py: Schémas de requête
- credentials.py: Configuration output fields
- Embedding.py: Chunking et embedding
- milvus_client.py: Client Milvus (search, parametres)
- embedding_client.py: Client gRPC embedding
- reranking_client.py: Client gRPC reranking

## 7. Collections Milvus
- produits_3, siteweb_2, devis, echanges
- Tous avec embedding 1024 dims

## 8. Services gRPC
- embedding-model-service: 50052
- reranking-model-service: 50053
- database-recherche-service: 50054
- api-recherche-service: 8510 (REST + WebSocket)
