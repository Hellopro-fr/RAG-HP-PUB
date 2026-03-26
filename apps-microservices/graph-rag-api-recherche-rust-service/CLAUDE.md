# graph-rag-api-recherche-rust-service
Rust port of the Graph RAG search API — intelligent product search, matching, and recommendations using RAG + Cypher scoring + LLM reranking.

## Tech Stack
- **Language:** Rust 1.88 (edition 2021)
- **Framework:** Actix-web 4 with utoipa (Swagger UI at `/docs/`)
- **gRPC:** tonic 0.12 / prost 0.13 (via `rust-common-utils` shared lib)
- **Database:** Neo4j direct driver (neo4rs 0.8)
- **HTTP client:** reqwest 0.12
- **Observability:** tracing + tracing-subscriber, Prometheus metrics

## Build & Run
```bash
cargo build --release          # local build
cargo run                      # local run (needs .env)
```
- **Docker port:** 8528
- **Prometheus port:** 8566 (env `PROMETHEUS_PORT`)
- Proto compilation handled by `build.rs`

## Folder Structure
```
src/
  main.rs              # Actix-web server + OpenAPI registration
  config.rs            # Settings from env vars
  domain/models.rs     # Request/response DTOs
  routers/             # admin, fournisseur, nodes, product, query, recommendation
  services/            # rag_service, cypher_builder, product/fournisseur/node/recommendation_service
  infrastructure/      # clients, gemini_client, hellopro_api_client, llm_service
  grpc_clients/        # shared gRPC client wrappers
```

## Conventions
- Clean Architecture: routers -> services -> infrastructure
- All endpoints registered as Actix `#[get/post]` handlers with utoipa annotations
- Settings loaded once via `Lazy<Settings>` (env vars, no config file)

## API Endpoints
| Method | Path | Tag |
|--------|------|-----|
| POST | `/query` | Intelligent Search |
| POST | `/produits/filter` | Recommendation |
| POST | `/produits/filter-by-caracteristique` | Recommendation |
| POST | `/produits/score` | Recommendation |
| POST | `/produits/matching` | Recommendation |
| GET | `/produits/{id}/caracteristiques` | Produits |
| DELETE | `/produits/{id}` | Produits |
| POST | `/admin/cypher` | Admin |
| GET | `/admin/categories/count` | Admin |
| GET | `/fournisseur/{id}/couverture` | Fournisseur |
| GET | `/fournisseur/produit/{id}/couverture` | Fournisseur |
| PUT | `/nodes/{id}` | Admin |
| GET | `/nodes/schema` | Admin |
| GET | `/nodes/{id}` | Admin |
| GET | `/health` | Health |

## Dependencies
- **gRPC:** embedding-service (50052), milvus-service (50056), database-connector (50055), normalize-unite-service (50057), spacy-service (50058), llm-service (50051), reranking-service (50053)
- **Direct:** Neo4j (bolt), HelloPro external API
- **LLM providers:** Gemini, OpenAI, Anthropic (configurable)
