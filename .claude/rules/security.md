# Security Rules

## Secrets & URLs

- NEVER hardcode service URLs, API keys, passwords, or connection strings.
- ALL service URLs MUST come from environment variables via Pydantic `BaseSettings`.
- Hardcoded URL found → replace with env var in `app/core/config.py`.
- Applies to: HTTP URLs, RabbitMQ, Redis, Neo4j, Milvus, Qdrant, Elasticsearch, gRPC addresses.

## CORS

- **Internal services** (behind api-gateway): `allow_origins=["*"]` acceptable with comment `# Internal only`.
- **Public-facing** (api-gateway, api-html-recherche): MUST restrict origins, methods, headers explicitly.

## JWT & Auth

- JWT secrets via environment variable only — never defaults like "changeme-jwt-secret".
- Redact sensitive headers (`authorization`, `cookie`, `x-api-key`) in logs.

## Input Validation

- Pydantic models for ALL request validation. Never trust user input.
- Sanitize data before LLM prompts (prevent prompt injection).
