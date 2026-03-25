# graph-rag-api-recherche-service
Python FastAPI search API — intelligent product search, matching, and recommendations using RAG + Cypher scoring + LLM reranking.

## Tech Stack
- **Language:** Python 3.10
- **Framework:** FastAPI + Uvicorn
- **gRPC:** grpcio (via shared `grpc-stubs` + `common-utils` libs)
- **LLM:** LangGraph, LangChain-core, google-genai
- **Observability:** Prometheus metrics (`common_utils.metrics`)

## Build & Run
```bash
pip install -r requirements.txt    # local deps
uvicorn app.main:app --port 8525   # local run
```
- **Docker port:** 8525
- Build is Docker-only (proto compilation + shared libs install in Dockerfile)

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

## Conventions
- Clean Architecture: routers -> services -> infrastructure
- Shared libs installed as editable packages (`libs/grpc-stubs`, `libs/common-utils`)
- pydantic-settings for all config (env vars / `.env`)

## API Endpoints
| Method | Path | Tag |
|--------|------|-----|
| POST | `/query/` | Intelligent Search |
| * | `/produits/` | Recommendation + Produits |
| * | `/fournisseur/` | Fournisseur |
| * | `/nodes/` | Admin |
| * | `/admin/` | Admin |
| GET | `/health` | Health |

## Dependencies
- **gRPC:** embedding-service, milvus-service, database-connector, normalize-unite-service, spacy-service, llm-service, reranking-service
- **LLM providers:** Gemini (google-genai), LangGraph orchestration
