# Security Rules

## Secrets & URLs
- NEVER hardcode service URLs, API keys, passwords, or connection strings in source code.
- ALL service URLs MUST come from environment variables via Pydantic `BaseSettings`.
- If you find a hardcoded URL (e.g., `http://localhost:8510`), replace it with an env var in `app/core/config.py`.
- This applies to ALL connection strings: HTTP URLs, RabbitMQ (`RABBITMQ_URL`), Redis (`REDIS_URL`), Neo4j (`NEO4J_URI`), Milvus (`MILVUS_HOST`/`MILVUS_PORT`), Qdrant (`QDRANT_HOST_URL`/`QDRANT_PORT`), Elasticsearch (`ELASTICSEARCH_URL`), and gRPC service addresses.

## Known violations to fix
> **Owner:** Team lead must assign. **Deadline:** Must be resolved before next release.
- `apps-microservices/api-check-doublon-produit/app/core/credentials.py` — hardcoded `ADRESSE_VM_API_RECHERCHE`
- `apps-microservices/api-rest-milvus/app/core/credentials.py` — hardcoded localhost URL
- When a violation is fixed, remove it from this list and note the fix in the commit message.

## CORS

### Internal services (behind api-gateway, not exposed publicly)
- `allow_origins=["*"]` is acceptable.
- Add a comment: `# Internal service only — not exposed publicly`.
- Use `allow_credentials=True, allow_methods=["*"], allow_headers=["*"]`.

### Public-facing services (api-gateway, api-html-recherche)
- MUST restrict `allow_origins` to explicit domains (e.g., `["https://rag.hellopro.eu"]`).
- MUST restrict `allow_methods` to only the HTTP methods the service actually uses.
- MUST restrict `allow_headers` to only the headers the service expects.
- `allow_credentials=True` is acceptable when origins are restricted.

## JWT & Authentication
- JWT secrets MUST be set via environment variable, never use defaults like "changeme-jwt-secret".
- Sensitive headers (`authorization`, `cookie`, `x-api-key`) MUST be redacted in logs.

## Input Validation
- Use Pydantic models for ALL request validation.
- Never trust user input — validate before processing.
- Sanitize data before passing to LLM prompts (prevent prompt injection).
