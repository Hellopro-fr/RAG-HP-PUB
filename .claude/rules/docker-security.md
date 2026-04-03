# Docker Security Rules

> Scoped to `**/Dockerfile*` and `**/docker-compose*.yml`. Apply when creating or modifying Docker files.

## Base Images

- NEVER use `latest` tag — always pin to a specific version (e.g., `python:3.10-slim`, not `python:latest`).
- NEVER use EOL or deprecated base images (e.g., `python:3.7`, `node:14`, `debian:stretch`).
- Prefer `-slim` or `-alpine` variants to reduce attack surface.
- When updating a base image version, check all services using the same image for consistency.

## Build Best Practices

Detect the service's stack per `.claude/rules/stack-detection.md`, then apply the appropriate build patterns:

**Python:**
- ALWAYS use `--no-cache-dir` on `pip install` to reduce image size.
- Copy `requirements.txt` first, install, then copy source (layer caching).

**Node.js:**
- Copy `package.json` and lock file first, install, then copy source.
- Use `npm ci` (not `npm install`) for deterministic builds.
- Add `node_modules/` to `.dockerignore`.

**Rust:**
- Use multi-stage builds: build in a `rust:*` image, copy binary to a minimal runtime image (`debian:*-slim` or `alpine`).
- Cache cargo registry and build artifacts between builds if possible.

**Go:**
- Use multi-stage builds: build with `golang:*`, copy binary to `scratch` or `alpine`.
- Use `CGO_ENABLED=0` for static binaries when possible.

**All stacks:**
- ALWAYS use multi-stage builds when the build step produces artifacts (e.g., ONNX export, proto compilation, compiled binaries).
- COPY only what is needed — avoid `COPY . .` at the root level.
- Remove build-time dependencies after use (`apt-get purge`, `rm -rf /var/lib/apt/lists/*`).

**Unknown stack:** Apply the generic rules above. If the stack has specific Dockerfile patterns, flag: "Consider updating `.claude/rules/docker-security.md` with patterns for this stack."

## Runtime Security

- NEVER run as root in production without justification. Add `USER nonroot` or equivalent.
- If root is required (e.g., for port binding), add a comment: `# Requires root: <reason>`.
- NEVER pass secrets via `ENV` in Dockerfile — use `.env` files, Docker secrets, or runtime environment injection.
- NEVER hardcode passwords, API keys, or connection strings in Dockerfile.

## docker-compose.yml

- EVERY service SHOULD have a `healthcheck` section. Flag services without one.
- Exposed ports: verify that ports meant for internal-only communication are NOT exposed to the host (use `expose:` not `ports:`).
- Environment variables with credentials MUST reference `.env` file or Docker secrets, not inline values.
- Logging config: verify `json-file` driver with `max-size` and `max-file` limits (project standard: 10m / 3 files).

## Vulnerability Patterns to Flag

- `apt-get install` without `--no-install-recommends` (pulls unnecessary packages).
- `chmod 777` or overly permissive file permissions.
- Downloading binaries from URLs without checksum verification.
- Using `ADD` instead of `COPY` (ADD auto-extracts tarballs and supports URLs — unexpected behavior).
- Missing `.dockerignore` in service directory (risk of copying `.env`, `.git`, `node_modules`).
