---
name: docker-expert
description: Docker troubleshooting, optimization, and security best practices for the RAG-HP-PUB monorepo (90+ Dockerfiles, docker-compose with 108 services)
argument-hint: <service-name-or-topic>
---

# Docker Expert

Analyze, troubleshoot, or optimize Docker configurations for the RAG-HP-PUB project.

## What You Can Do

1. **Troubleshoot** — Diagnose Dockerfile build failures, container crashes, networking issues, volume problems.
2. **Optimize** — Reduce image sizes, improve build times (layer caching), fix security issues.
3. **Review** — Audit a service's Dockerfile against `.claude/rules/docker-security.md`.
4. **Compare** — Compare a service's Docker setup against project best practices.
5. **Compose** — Analyze `docker-compose.yml` for port conflicts, missing healthchecks, environment issues.

## Context

- **90+ Dockerfiles** across `apps-microservices/`
- **docker-compose.yml**: 108 services, 2187 lines
- **Standard Python base**: `python:3.10-slim`
- **Shared libs**: Installed via `pip install -e /app/libs/common-utils`
- **Proto compilation**: At build time via `grpc_tools.protoc`
- **Profiles**: `app`, `tools`, `disabled`
- **Logging**: `json-file` driver, 10m max-size, 3 max-file

## Process

### If troubleshooting:
1. Read the service's Dockerfile.
2. Read the docker-compose.yml entry for the service.
3. Identify the issue (build error, runtime error, config mismatch).
4. Propose a fix with trade-offs (per `.claude/rules/impact-awareness.md`).

### If optimizing:
1. Read the Dockerfile.
2. Check image size contributors (base image, unnecessary packages, cache invalidation).
3. Propose optimizations with expected size reduction.

### If reviewing:
1. Apply every check from `.claude/rules/docker-security.md`.
2. Report findings grouped by severity.

## Rules

- Detect the service's stack per `.claude/rules/stack-detection.md` before applying stack-specific Docker patterns.
- Apply `.claude/rules/docker-security.md` for all reviews.
- Apply `.claude/rules/impact-awareness.md` for changes to shared Docker configs.
- Never modify `docker-compose.yml` without listing all affected services first.
