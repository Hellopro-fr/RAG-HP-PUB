# graph-rag-api-recherche-optim-service

Copie isolee de `graph-rag-api-recherche-service` pour l'optimisation iterative du scoring produit via **agent-optim-scoring**.

> **NE PAS merger vers prod sans validation checkpoint CP4.**

## Relation avec la prod

- Code source copie de `graph-rag-api-recherche-service` (prod)
- Memes services downstream partages (database-connector, milvus, normalize-unite, llm, embedding, reranking)
- Port HTTP : **8625** (host) / 8525 (interne)
- Route gateway : `/graphoptim-service/`
- Profil docker-compose : `graph-rag-optim`

## Tech Stack
- **Language:** Python 3.10
- **Framework:** FastAPI + Uvicorn
- **gRPC:** grpcio (via shared `grpc-stubs` + `common-utils` libs)
- **LLM:** LangGraph, LangChain-core, google-genai
- **Observability:** Prometheus metrics (`common_utils.metrics`)

## Build & Run
```bash
# Via docker-compose (recommande)
docker compose --profile graph-rag-optim up -d

# Acces
curl -X POST http://localhost:8625/produits/matching
# ou via gateway
curl -X POST https://api.hellopro.eu/graphoptim-service/produits/matching
```

## Fichiers modifiables par l'agent d'optimisation

### Scoring / logique matching
| Fichier | Ce qu'il controle |
|---|---|
| `app/services/recommendation_service.py` | Moteur scoring V4 : penalites, seuils, diversite fournisseurs, Cypher Steps, scoring numerique |
| `app/services/recommendation_service_v2.py` | Scoring V2 Python : algorithmes, overlap Jaccard, seuils numeriques |
| `app/services/cypher_builder.py` | Construction Cypher, seuils recherche semantique |

### Prompts LLM
| Fichier | Ce qu'il controle |
|---|---|
| `app/services/rag_components.py` | Templates LLM : extraction entites, routing strategie, generation reponse |

### Configuration
| Fichier | Ce qu'il controle |
|---|---|
| `app/config.py` | Seuils globaux : similarite vectorielle, top_k, modele LLM |

## Fichiers a NE PAS modifier

| Fichier | Raison |
|---|---|
| `app/main.py` | Infrastructure FastAPI |
| `app/routers/*.py` | Endpoints API (routing, pas de logique scoring) |
| `app/infrastructure/*.py` | Clients gRPC/LLM (transport) |
| `app/domain/models.py` | Schemas Pydantic (sauf ajout parametre scoring) |
| `Dockerfile` | Build container |

## Folder Structure
```
app/
  main.py              # FastAPI app + router registration
  config.py            # pydantic-settings configuration
  domain/models.py     # Request/response models
  routers/             # query, recommendation, product, admin, fournisseur, nodes
  services/            # rag_service, cypher_builder, product/fournisseur/node/recommendation_service
  infrastructure/      # clients, gemini_client, hellopro_api_client, llm_service
```

## Dependencies
- **gRPC (partages avec prod):** embedding-service, milvus-service, database-connector, normalize-unite-service, spacy-service, llm-service, reranking-service
- **LLM providers:** Gemini (google-genai), LangGraph orchestration
