# Security Rules

## Secrets & URLs
- NEVER hardcode service URLs, API keys, passwords, or connection strings in source code.
- ALL service URLs MUST come from environment variables via Pydantic `BaseSettings`.
- If you find a hardcoded URL (e.g., `http://localhost:8510`), replace it with an env var in `app/core/config.py`.

## Known violations to fix
- `apps-microservices/api-check-doublon-produit/app/core/credentials.py` — hardcoded `ADRESSE_VM_API_RECHERCHE`
- `apps-microservices/api-rest-milvus/app/core/credentials.py` — hardcoded localhost URL

## CORS
- Default CORS policy: `allow_origins=["*"]` is acceptable for internal services behind the API gateway.
- Public-facing services (api-gateway, api-html-recherche) MUST restrict origins.
- When adding CORS middleware, always include `allow_credentials=True, allow_methods=["*"], allow_headers=["*"]`.

## JWT & Authentication
- JWT secrets MUST be set via environment variable, never use defaults like "changeme-jwt-secret".
- Sensitive headers (`authorization`, `cookie`, `x-api-key`) MUST be redacted in logs.

## Input Validation
- Use Pydantic models for ALL request validation.
- Never trust user input — validate before processing.
- Sanitize data before passing to LLM prompts (prevent prompt injection).
