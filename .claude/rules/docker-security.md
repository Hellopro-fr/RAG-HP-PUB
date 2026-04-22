# Docker Security Rules

> Apply when creating or modifying Dockerfiles and docker-compose files.

## Base Images

- NEVER use `latest` tag — pin to specific version (e.g., `python:3.10-slim`).
- NEVER use EOL/deprecated images. Prefer `-slim` or `-alpine` variants.

## Build Patterns (per stack)

- **Python**: `--no-cache-dir` on pip install. Copy requirements.txt first (layer caching).
- **Node.js**: Copy package.json + lock first. Use `npm ci` not `npm install`. Dockerignore node_modules.
- **Rust**: Multi-stage build. Build in `rust:*`, copy binary to `debian:*-slim` or `alpine`.
- **Go**: Multi-stage. `CGO_ENABLED=0` for static binaries. Copy to `scratch` or `alpine`.
- **All**: Multi-stage when build produces artifacts. COPY only needed files. Clean apt lists.

## Runtime Security

- NEVER run as root without justification. Add `USER nonroot`.
- NEVER pass secrets via `ENV` — use `.env` files or Docker secrets.
- NEVER hardcode credentials in Dockerfile.

## docker-compose.yml

- Every service SHOULD have `healthcheck`. Flag missing ones.
- Internal ports → `expose:` not `ports:`. Credentials → `.env` file or secrets.
- Logging: `json-file` driver with `max-size: 10m`, `max-file: 3`.

## Vulnerability Patterns

Flag: `apt-get` without `--no-install-recommends`, `chmod 777`, downloads without checksum, `ADD` instead of `COPY`, missing `.dockerignore`.
