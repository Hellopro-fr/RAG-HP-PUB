# Rapport d'audit Claude Code — RAG-HP-PUB

> **Date :** 2026-03-25
> **Branche analysée :** `features/poc`
> **Projet :** RAG-HP-PUB — Plateforme RAG avec 91 microservices
> **Auditeur :** Claude Code (Opus 4.6)

---

## Table des matières

1. [État des lieux / Current State Summary](#1--état-des-lieux--current-state-summary)
2. [Agents manquants / Missing Agents](#2--agents-manquants--missing-agents)
3. [Commandes manquantes / Missing Commands](#3--commandes-manquantes--missing-commands)
4. [Règles manquantes / Missing Rules](#4--règles-manquantes--missing-rules)
5. [Skills manquants / Missing Skills](#5--skills-manquants--missing-skills)
6. [Hooks manquants / Missing Hooks](#6--hooks-manquants--missing-hooks)
7. [Problèmes dans les CLAUDE.md existants / Issues in Existing CLAUDE.md Files](#7--problèmes-dans-les-claudemd-existants--issues-in-existing-claudemd-files)
8. [Points manquants / What You're Missing](#8--points-manquants--what-youre-missing)
9. [Plan d'action priorisé / Prioritized Action Plan](#9--plan-daction-priorisé--prioritized-action-plan)
10. [Métriques de succès / Success Metrics](#10--métriques-de-succès--success-metrics)

---

## 1 — État des lieux / Current State Summary

### Tableau récapitulatif

| Catégorie | En place | Manquant | Score /10 |
|---|---|---|---|
| **Agents** | 3 (code-reviewer, debugger, doc-writer) | test-writer, security-auditor, rabbitmq-reviewer | 5/10 |
| **Commandes** | 7 (/commit-msg, /explain, /plan, /understand, /new-feature-claude-md, /new-service-claude-md, /update-claude-md) | /pre-push, /new-endpoint, /sync-proto, /troubleshoot | 6/10 |
| **Règles** | 2 (code-modification.md, commit-messages.md) | security.md, python-conventions.md, testing.md, error-handling.md, rabbitmq-patterns.md | 4/10 |
| **Skills** | 0 | fastapi-service-scaffold | 0/10 |
| **Hooks** | 0 | PostToolUse (lint), Stop (commit reminder) | 0/10 |
| **CLAUDE.md** | 97 fichiers, tous < 80 lignes, cohérents | Quelques incohérences (ports, tests, CI) | 8/10 |
| **Config personnelle** | ~/.claude/CLAUDE.md (37 lignes), primer.md prêt | — | 9/10 |
| **Guides d'équipe** | 2 guides bilingues (FR/EN) dans docs/ | — | 9/10 |
| **Tests** | 22/91 services avec répertoire pytest | 69 services sans tests, aucun jest/vitest, aucun pytest.ini | 2/10 |
| **Linters/Formatters** | Aucun | Pas de ruff, flake8, eslint, prettier, editorconfig | 0/10 |
| **Git Hooks** | Aucun | Pas de husky, pre-commit, lefthook | 0/10 |
| **CI/CD** | 41 workflows, 13/91 services couverts | 78 services sans pipeline CI | 3/10 |
| **Documentation infra** | Docker uniquement, pas de doc d'architecture | README.md vide, pas d'ADR, pas de registre de ports | 2/10 |

### Score global de maturité Claude Code

| Composant | Poids | Score | Pondéré |
|---|---|---|---|
| CLAUDE.md (couverture + qualité) | 25% | 8/10 | 20 |
| Agents | 15% | 5/10 | 7.5 |
| Commandes | 15% | 6/10 | 9 |
| Règles | 20% | 4/10 | 8 |
| Skills + Hooks | 10% | 0/10 | 0 |
| Outillage projet (tests, linters, CI) | 15% | 2/10 | 3 |

> **Score global : 47.5 / 100**
>
> La configuration Claude Code est solide sur les fondamentaux (CLAUDE.md excellents, agents de base fonctionnels, commandes utiles). Les lacunes majeures sont l'absence totale de skills/hooks, le manque de règles de sécurité, et surtout le déficit d'outillage projet (tests, linters, CI) qui limite l'efficacité de Claude Code lui-même.

---

## 2 — Agents manquants / Missing Agents

### 2.1 — test-writer — Priorité : 🔴 Critique

**Justification :** Seulement 22/91 services ont des tests. C'est le plus gros risque technique du projet. Cet agent permettra de générer des tests pytest pour les services FastAPI en suivant les patterns `conftest.py` existants.

**Fichier :** `.claude/agents/test-writer.md`

```markdown
---
name: test-writer
description: Generates pytest test suites for Python FastAPI services following existing project patterns. Use when asked to write tests, add test coverage, or create test files.
tools: Read, Write, Edit, Glob, Grep, Bash
model: sonnet
---

You are a senior QA engineer specializing in Python testing with pytest.

## Context

This is a monorepo with 91 microservices in apps-microservices/. Most are Python FastAPI services.
Only 22/91 services currently have tests. Your job is to close that gap.

## Your Process

1. **Analyze the service:** Read main.py, routers, schemas, and any existing conftest.py.
2. **Identify testable units:** List endpoints, utility functions, and business logic.
3. **Check for existing patterns:** Look for tests/ directories in similar services for conventions.
4. **Generate tests:** Create pytest files following the patterns below.

## Test Structure

```
tests/
  conftest.py          # Fixtures: test client, mock RabbitMQ, mock env vars
  test_health.py       # Health/readiness endpoints
  test_<router>.py     # One file per router
  test_<utils>.py      # Unit tests for utility functions
```

## Conventions

- Use `pytest-asyncio` for async endpoints.
- Use `httpx.AsyncClient` with `ASGITransport` for FastAPI test client.
- Mock external dependencies (RabbitMQ, gRPC, vector DBs) — never call real services.
- Use `monkeypatch.setenv` for environment variables, never modify os.environ directly.
- Follow AAA pattern: Arrange → Act → Assert.
- Test both success and error cases for each endpoint.
- Use descriptive test names: `test_<function>_<scenario>_<expected_result>`.

## Output

- Generate complete test files with all imports.
- Include a conftest.py if one doesn't exist.
- After generating, run: `python -m pytest tests/ -v --tb=short` to verify.

## Rules

- Read the actual source code before writing any test — never assume.
- Do NOT modify source code. You write tests ONLY.
- If the service has no clear testable logic (e.g., pure RabbitMQ consumer), create at minimum a health check test and a configuration validation test.
- Flag untestable code with: **"⚠️ This function is hard to test because [reason]. Consider refactoring."**
```

---

### 2.2 — security-auditor — Priorité : 🟡 Recommandé

**Justification :** Le projet expose des API publiques, gère l'authentification JWT (avec un secret par défaut `"changeme-jwt-secret"`), et le scan a révélé des URL localhost hardcodées dans `api-check-doublon-produit` et `api-rest-milvus`. Un agent dédié systématisera ces vérifications.

**Fichier :** `.claude/agents/security-auditor.md`

```markdown
---
name: security-auditor
description: Scans code for security vulnerabilities including hardcoded secrets, CORS misconfigurations, injection risks, and OWASP top 10 issues. Use when asked to audit security or before major releases.
tools: Read, Glob, Grep
model: sonnet
---

You are a senior application security engineer performing a code audit.

## Your Task

Scan the specified service(s) for security vulnerabilities across these categories:

### 1. Secrets & Credentials
- Hardcoded passwords, API keys, JWT secrets, database URLs
- Hardcoded localhost/IP addresses in credentials.py or config.py
- Default secrets (e.g., "changeme-jwt-secret", "password123")
- Secrets in Docker environment variables without .env.example documentation

### 2. CORS Configuration
- `allow_origins=["*"]` on public-facing services
- Missing CORS configuration entirely
- Inconsistent CORS policies across services

### 3. Input Validation
- Missing Pydantic model validation on request bodies
- Raw string interpolation in database queries
- Unvalidated file uploads
- Missing rate limiting on public endpoints

### 4. Authentication & Authorization
- Missing JWT validation on protected endpoints
- JWT algorithm confusion (accepting "none")
- Missing token expiration checks
- Overly permissive RBAC

### 5. Error Handling
- Stack traces exposed in API responses
- Verbose error messages leaking internal details
- `except Exception` swallowing security-relevant errors

### 6. Network Security
- `timeout=None` on outbound HTTP requests (DoS vector)
- Missing TLS verification on internal calls
- Proxy requests without timeout (found in api-gateway)

## Output Format

Group findings by severity:
- 🔴 **CRITICAL** — Exploitable now, fix immediately
- 🟡 **WARNING** — Risk that should be addressed
- 🔵 **INFO** — Best practice improvement

For each finding:
```
**[SEVERITY] Title**
- File: `path/to/file.py:line`
- Issue: Description of the vulnerability
- Impact: What an attacker could do
- Fix: Specific remediation step
```

## Rules

- Do NOT fix code. Report only.
- Reference specific files and line numbers.
- Prioritize real findings over theoretical risks.
- End with: **"Would you like me to create fix tasks for any of these findings?"**
```

---

### 2.3 — rabbitmq-reviewer — Priorité : 🔵 Nice-to-have

**Justification :** Plus de 40 services utilisent RabbitMQ avec deux patterns (aio_pika async et pika sync). Le pattern DLQ est standardisé via `common-utils/DLQPropertiesAsync.py`, mais la cohérence entre services mériterait une vérification automatisée.

**Fichier :** `.claude/agents/rabbitmq-reviewer.md`

```markdown
---
name: rabbitmq-reviewer
description: Reviews RabbitMQ consumer/publisher implementations for pattern consistency, error handling, and DLQ configuration. Use when reviewing or creating RabbitMQ-connected services.
tools: Read, Glob, Grep
model: sonnet
---

You are a messaging systems specialist with deep expertise in RabbitMQ and AMQP.

## Your Task

Review RabbitMQ implementations in the specified service(s) against project standards.

## Project Standards

### Preferred Pattern (newer services)
- **Library:** aio_pika (async)
- **Consumer:** Async consumers with proper connection recovery
- **DLQ:** Use common-utils/DLQPropertiesAsync.py for dead-letter configuration

### Legacy Pattern (older services)
- **Library:** pika (sync)
- **Note:** Flag for migration to aio_pika but don't treat as a bug

### Naming Conventions
- Exchange: `data_exchange_{collection}`
- Routing key: `new_data.{collection}`
- Queue: `{collection}_processing_queue`

### Error Handling
- **Transient errors** (network, timeout): NACK + requeue with exponential backoff
- **Permanent errors** (validation, malformed data): NACK + route to DLQ
- DLQ headers must include: original queue, error message, timestamp, retry count

## Review Checklist

1. ✅ Connection recovery configured (auto-reconnect on disconnect)
2. ✅ Proper channel prefetch_count set (not unlimited)
3. ✅ Messages acknowledged AFTER processing (not before)
4. ✅ DLQ configured for permanent failures
5. ✅ Transient vs permanent error distinction implemented
6. ✅ Naming conventions followed
7. ✅ Consumer graceful shutdown (close channel before connection)
8. ✅ No fire-and-forget publishes (confirm delivery)

## Output Format

- Group findings by severity: 🔴 Critical → 🟡 Warning → 🔵 Suggestion
- Reference specific files and functions.
- End with: **"Would you like me to implement any of these improvements?"**

## Rules

- Do NOT modify code. Review only.
- Always read the actual consumer/publisher files before commenting.
- Compare against common-utils patterns, not theoretical best practices.
```

---

## 3 — Commandes manquantes / Missing Commands

### 3.1 — /pre-push — Priorité : 🔴 Critique

**Justification :** Aucun git hook, aucun linter, aucun garde-fou avant le push. Cette commande compense l'absence totale d'outillage de qualité.

**Fichier :** `.claude/commands/pre-push.md`

```markdown
# /pre-push — Checklist avant push

Exécute une vérification complète avant de pousser du code. Parcours tous les fichiers modifiés dans la branche courante par rapport à `main`.

## Étapes

1. **Identifier les fichiers modifiés :**
   ```bash
   git diff --name-only main...HEAD
   ```

2. **Pour chaque fichier Python (.py) modifié :**
   - Vérifier la syntaxe : `python -m py_compile <file>`
   - Vérifier les imports inutilisés et doublons (lecture manuelle)
   - Vérifier qu'aucun `print()` de debug n'est resté
   - Vérifier qu'aucune URL localhost n'est hardcodée
   - Vérifier qu'aucun secret n'est en clair (patterns : password=, secret=, api_key=)

3. **Pour chaque service modifié :**
   - Si un répertoire `tests/` existe : exécuter `python -m pytest tests/ -v --tb=short`
   - Si aucun test n'existe : afficher ⚠️ "Aucun test pour ce service"

4. **Revue de code :** Appeler l'agent @code-reviewer sur les fichiers modifiés.

5. **Résumé final :**

```
## Résultat /pre-push

| Vérification       | Résultat |
|---------------------|----------|
| Syntaxe Python      | ✅ / ❌  |
| Imports propres     | ✅ / ❌  |
| Pas de debug print  | ✅ / ❌  |
| Pas de secrets      | ✅ / ❌  |
| Pas de localhost     | ✅ / ❌  |
| Tests exécutés      | ✅ / ⚠️ / ❌ |
| Revue de code       | ✅ / 🟡 / ❌ |
```

Si un ❌ est présent, afficher : **"🚫 Push déconseillé. Corrigez les problèmes ci-dessus."**
Si tout est ✅ ou ⚠️ : **"✅ Prêt à push."**
```

---

### 3.2 — /new-endpoint — Priorité : 🟡 Recommandé

**Justification :** Les 70+ services Python FastAPI suivent un pattern identique (router + schema + response envelope). Un scaffold standardisé évitera les oublis et accélérera le développement.

**Fichier :** `.claude/commands/new-endpoint.md`

```markdown
# /new-endpoint — Scaffolder un nouvel endpoint FastAPI

Crée les fichiers nécessaires pour un nouvel endpoint dans un service FastAPI existant.

## Paramètre requis

L'utilisateur doit fournir :
- **Service** : nom du service (ex: `api-ingestion`)
- **Endpoint** : chemin de l'endpoint (ex: `/api/v1/products`)
- **Méthode** : GET, POST, PUT, DELETE
- **Description** : ce que fait l'endpoint

## Étapes

1. **Lire la structure existante** du service dans `apps-microservices/<service>/`.
2. **Créer ou mettre à jour le router** dans `app/router/` en suivant le pattern existant.
3. **Créer le schéma Pydantic** dans `app/schemas/` pour le request/response body.
4. **Utiliser le format de réponse standard** :
   ```python
   {
       "code": 200,
       "status": "success",
       "message": "Description",
       "details": {
           "date": "ISO-8601",
           "uid": "uuid4"
       }
   }
   ```
5. **Créer le fichier de test** dans `tests/test_<router_name>.py` avec :
   - Test du cas nominal (happy path)
   - Test d'un cas d'erreur (validation, not found)
6. **Enregistrer le router** dans `main.py` si c'est un nouveau fichier router.

## Règles

- Lire les fichiers existants du service AVANT de générer quoi que ce soit.
- Respecter les conventions d'import et de nommage déjà en place dans le service.
- Utiliser `app/utils/response.py` pour le format de réponse si le fichier existe.
- Ne jamais écraser un fichier existant sans confirmation.
```

---

### 3.3 — /sync-proto — Priorité : 🟡 Recommandé

**Justification :** Les stubs gRPC dans `libs/grpc-stubs/` semblent générés au build Docker et non commités. La regénération manuelle est source d'erreurs. [A VERIFIER PAR L'EQUIPE : confirmer que la génération se fait bien au build time]

**Fichier :** `.claude/commands/sync-proto.md`

```markdown
# /sync-proto — Regénérer les stubs gRPC Python

Regénère les fichiers Python à partir des fichiers .proto du projet.

## Étapes

1. **Lister les fichiers .proto disponibles :**
   ```bash
   find protos/ -name "*.proto" -type f 2>/dev/null
   find libs/grpc-stubs/ -name "*.proto" -type f 2>/dev/null
   ```

2. **Pour chaque fichier .proto trouvé, générer les stubs :**
   ```bash
   python -m grpc_tools.protoc \
     -I./protos \
     --python_out=./libs/grpc-stubs/src/grpc_stubs/ \
     --grpc_python_out=./libs/grpc-stubs/src/grpc_stubs/ \
     <proto_file>
   ```

3. **Vérifier la génération :**
   - Lister les fichiers `*_pb2.py` et `*_pb2_grpc.py` générés
   - Tester l'import : `python -c "import grpc_stubs"`

4. **Résumé :**
   ```
   ## Résultat /sync-proto
   - Fichiers .proto trouvés : X
   - Stubs générés : X
   - Stubs valides : ✅ / ❌
   ```

## Pré-requis

- `grpcio-tools` doit être installé : `pip install grpcio-tools`

## Note

Si aucun fichier .proto n'est trouvé, afficher :
**"⚠️ Aucun fichier .proto trouvé. Les stubs gRPC sont probablement générés au build Docker. Voir les Dockerfile des services concernés."**
```

---

### 3.4 — /troubleshoot — Priorité : 🔵 Nice-to-have

**Justification :** Le projet utilise RabbitMQ, gRPC, Milvus/Qdrant, et des API REST interconnectées. Les problèmes de connectivité sont fréquents dans ce type d'architecture.

**Fichier :** `.claude/commands/troubleshoot.md`

```markdown
# /troubleshoot — Diagnostic guidé des problèmes courants

Guide interactif pour diagnostiquer les problèmes les plus fréquents dans le projet.

## Étape 1 — Identifier le type de problème

Demander à l'utilisateur :

**Quel type de problème rencontrez-vous ?**
1. 🐰 Connexion RabbitMQ (consumer ne reçoit pas les messages, connexion refusée)
2. 🔌 Timeout gRPC (appel inter-service qui ne répond pas)
3. 🔍 Requête Milvus/Qdrant (résultats inattendus, collection introuvable)
4. 🌐 Erreur API REST (5xx, timeout, CORS)
5. 🐳 Problème Docker (build fail, container crash)
6. 🔄 Autre

## Diagnostics par type

### 1. RabbitMQ
- Vérifier la config dans `app/core/config.py` : RABBITMQ_HOST, RABBITMQ_PORT, RABBITMQ_USER, RABBITMQ_PASSWORD
- Vérifier les noms d'exchange/queue (convention : `data_exchange_{collection}`, `{collection}_processing_queue`)
- Vérifier que le consumer ACK les messages APRES traitement
- Vérifier le DLQ : messages en dead-letter = erreurs permanentes

### 2. gRPC
- Vérifier que le service cible est démarré et écoute sur le bon port
- Vérifier la cohérence des stubs (.proto vs code généré)
- Augmenter le timeout côté client si nécessaire
- Vérifier les logs du service cible pour l'erreur réelle

### 3. Milvus/Qdrant
- Vérifier que la collection existe : lister les collections
- Vérifier la dimension des vecteurs (doit correspondre au modèle d'embedding)
- Vérifier la métrique de distance (cosine vs L2)

### 4. API REST
- Lire les logs du service : chercher le pattern `❌` dans les logs
- Vérifier la config CORS si l'erreur vient du navigateur
- Vérifier le timeout (api-gateway a `timeout=None` — risque de hang)

### 5. Docker
- Vérifier le Dockerfile : EXPOSE vs CMD port
- Vérifier les variables d'environnement dans docker-compose
- Rebuilder sans cache : `docker build --no-cache`

## Règles

- Toujours lire les logs et la config réelle du service avant de diagnostiquer.
- Appeler l'agent @debugger si le problème nécessite une analyse de code approfondie.
- Ne jamais deviner — demander les logs si non fournis.
```

---

## 4 — Règles manquantes / Missing Rules

### 4.1 — security.md — Priorité : 🔴 Critique

**Justification :** Le scan a trouvé des URL localhost hardcodées dans `api-check-doublon-produit` et `api-rest-milvus/credentials.py`, un secret JWT par défaut dans api-gateway, et des politiques CORS incohérentes. Cette règle empêchera Claude de reproduire ces anti-patterns.

**Fichier :** `.claude/rules/security.md`

```markdown
# Security Rules

> Scoped to all files. These rules MUST be followed for every code generation and modification.

## Secrets & URLs

- **NEVER** hardcode URLs (localhost, IP addresses, domain names) in source code. Use environment variables via Pydantic `BaseSettings`.
- **NEVER** hardcode passwords, API keys, JWT secrets, or tokens. Always use environment variables.
- **NEVER** use default secrets like `"changeme-jwt-secret"`, `"password"`, `"secret"`, `"admin"`. If a default is needed for local dev, use a clearly-marked placeholder and log a warning at startup.
- When creating or modifying `app/core/config.py` or `app/core/credentials.py`, ALL service URLs and credentials MUST come from environment variables.

### Known violations to fix (do not replicate)
- `apps-microservices/api-check-doublon-produit/` — hardcoded localhost URL
- `apps-microservices/api-rest-milvus/app/core/credentials.py` — hardcoded localhost URL
- `apps-microservices/api-gateway/` — JWT secret default "changeme-jwt-secret"

## CORS

- **NEVER** use `allow_origins=["*"]` on services exposed to the internet.
- For internal-only services (not exposed via api-gateway), `allow_origins=["*"]` is acceptable but must have a comment: `# Internal service only — not exposed publicly`.
- When adding CORS middleware, always specify: `allow_origins`, `allow_methods`, `allow_headers`, `allow_credentials`.

## HTTP Clients

- **ALWAYS** set a timeout on outbound HTTP requests. Never use `timeout=None`.
- Recommended: `timeout=30` for standard calls, `timeout=120` for LLM/embedding calls.

## Error Responses

- **NEVER** expose stack traces or internal paths in API error responses.
- Use the standard error envelope format from `app/utils/response.py`.
- Log the full error server-side, return a sanitized message to the client.

## Input Validation

- **ALWAYS** use Pydantic models for request body validation.
- **ALWAYS** validate and sanitize file uploads (check MIME type, size limits).
- **NEVER** use string formatting/concatenation for database queries.
```

---

### 4.2 — python-conventions.md — Priorité : 🟡 Recommandé

**Justification :** Le scan a trouvé des imports dupliqués (`api-ingestion/main.py`), des imports inutilisés (`api-chat-llm`), et aucun standard d'ordonnancement des imports. En l'absence de linter configuré, cette règle sert de filet de sécurité.

**Fichier :** `.claude/rules/python-conventions.md`

```markdown
# Python Conventions

> Scoped to `**/*.py`. Apply these rules when writing or modifying Python files.

## Import Ordering

Imports MUST follow this order, with a blank line between each group:

```python
# 1. Standard library
import os
import logging
from datetime import datetime

# 2. Third-party packages
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# 3. Local/project imports
from app.core.config import settings
from app.utils.response import success_response
```

- **NEVER** duplicate imports. If an import already exists, do not add it again.
- **NEVER** leave unused imports. Remove them when refactoring.
- Use `from X import Y` for specific symbols. Use `import X` for modules used with prefix.

## Configuration

- **ALWAYS** use Pydantic `BaseSettings` for environment-based configuration.
- Config file location: `app/core/config.py` or `app/core/credentials.py`.
- **NEVER** use `os.getenv()` directly in business logic. Access config via the settings object.

## Logging

- Use the standard `logging` module (not print, not loguru, not structlog).
- Standard format: `%(asctime)s - %(levelname)s - [WORKER_PID:%(process)d] - %(message)s`
- Use emoji prefixes for log clarity:
  - `✅` success
  - `❌` error
  - `⏳` waiting/in-progress
  - `📥` incoming request/message
  - `📤` outgoing request/message
  - `🚀` startup

## Type Hints

- Add type hints to function signatures (parameters and return type).
- Use `Optional[X]` or `X | None` for nullable types.
- Use Pydantic models for complex data structures, not raw dicts.

## Functions

- Keep functions under 30 lines. If longer, extract sub-functions.
- Use descriptive names: `process_product_data()`, not `do_stuff()`.
- Async functions (`async def`) for I/O-bound operations (HTTP calls, DB queries, message publishing).

## Exception Handling

- **NEVER** use bare `except:` or `except Exception:` without logging the error.
- Distinguish transient errors (retry) from permanent errors (log + fail).
- Re-raise or handle — never silently swallow exceptions.
```

---

### 4.3 — testing.md — Priorité : 🟡 Recommandé

**Justification :** 69/91 services n'ont aucun test. Quand Claude génère du code, il devrait aussi générer (ou rappeler de générer) les tests correspondants.

**Fichier :** `.claude/rules/testing.md`

```markdown
# Testing Rules

> Apply these rules when creating or modifying service code.

## Minimum Test Requirements

Every service SHOULD have at minimum:
1. **Health check test** — Verify `GET /health` returns 200.
2. **Configuration test** — Verify required env vars are loaded correctly.
3. **One test per endpoint** — At least the happy path.

## When to Write Tests

- When creating a new endpoint → create the test in the same PR.
- When fixing a bug → write a regression test that reproduces the bug first.
- When modifying business logic → update existing tests or add new ones.
- If a service has no tests/ directory, create one following the structure below.

## Test Structure

```
tests/
  __init__.py
  conftest.py              # Shared fixtures
  test_health.py           # Health/readiness endpoint
  test_<router_name>.py    # One per router file
  test_<utility_name>.py   # Unit tests for utils
```

## conftest.py Pattern

```python
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch

from app.main import app  # or wherever the FastAPI app is created


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
```

## Mocking Rules

- **ALWAYS** mock external services (RabbitMQ, gRPC, Milvus, Qdrant, external APIs).
- **NEVER** call real infrastructure in tests.
- Use `unittest.mock.patch` or `pytest-mock` fixtures.
- Mock at the closest boundary to the external call.

## Naming Convention

```python
def test_<function>_<scenario>_<expected_result>():
    """Example: test_create_product_with_valid_data_returns_201"""
```

## Test Commands

- Run a service's tests: `cd apps-microservices/<service> && python -m pytest tests/ -v`
- Run with coverage: `python -m pytest tests/ --cov=app --cov-report=term-missing`
```

---

### 4.4 — error-handling.md — Priorité : 🟡 Recommandé

**Justification :** Le scan montre une gestion d'erreurs modérément cohérente : un handler global pour les services HTTP, mais des `except Exception` trop larges et des erreurs silencieuses dans certains consumers RabbitMQ.

**Fichier :** `.claude/rules/error-handling.md`

```markdown
# Error Handling Rules

> Apply these rules when writing or modifying error handling code.

## HTTP Services (FastAPI)

### Standard Error Response

All API errors MUST use the standard envelope format:

```python
{
    "code": <http_status_code>,
    "status": "error",
    "message": "Human-readable error description",
    "details": {
        "date": "ISO-8601 timestamp",
        "uid": "correlation-id-if-available"
    }
}
```

Use `app/utils/response.py` if available in the service.

### Global Exception Handler

Every FastAPI service SHOULD register a global exception handler:

```python
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"❌ Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "code": 500,
            "status": "error",
            "message": "Internal server error",
            "details": {"date": datetime.utcnow().isoformat()}
        }
    )
```

### Rules

- **NEVER** return raw exception messages to clients (information leakage).
- **NEVER** use bare `except:` — always catch specific exceptions or at minimum `except Exception as e:` with logging.
- Log the full traceback server-side with `exc_info=True`.
- Use HTTP status codes correctly: 400 (bad input), 404 (not found), 409 (conflict), 422 (validation), 500 (server error).

## RabbitMQ Consumers

### Transient vs Permanent Errors

| Type | Examples | Action |
|------|----------|--------|
| **Transient** | Network timeout, service unavailable, rate limit | NACK + requeue. Implement exponential backoff. |
| **Permanent** | Validation error, malformed data, missing required field | NACK + route to DLQ. Do NOT requeue. |

### DLQ Headers

When routing to dead-letter queue, include these headers:

```python
headers = {
    "x-original-queue": queue_name,
    "x-error-message": str(error),
    "x-error-timestamp": datetime.utcnow().isoformat(),
    "x-retry-count": current_retry_count
}
```

Use `common-utils/DLQPropertiesAsync.py` for standardized DLQ configuration.

### Rules

- **ALWAYS** acknowledge messages AFTER successful processing, not before.
- **NEVER** silently swallow errors — log at ERROR level with the message body (redact PII).
- **ALWAYS** distinguish transient from permanent errors.
- Set a maximum retry count for transient errors (default: 3). After that, route to DLQ.
```

---

### 4.5 — rabbitmq-patterns.md — Priorité : 🔵 Nice-to-have

**Justification :** Plus de 40 services utilisent RabbitMQ. La cohérence est bonne mais pas documentée dans les règles Claude Code. Cette règle servira de référence pour les nouveaux services.

**Fichier :** `.claude/rules/rabbitmq-patterns.md`

```markdown
# RabbitMQ Patterns

> Apply these rules when creating or modifying RabbitMQ consumers/publishers.

## Preferred Library

- **New services:** Use `aio_pika` (async). This is the project standard.
- **Existing services with `pika`:** Do not migrate during unrelated changes. Flag for future migration if asked.

## Naming Conventions

| Element | Pattern | Example |
|---------|---------|---------|
| Exchange | `data_exchange_{collection}` | `data_exchange_fournisseurs` |
| Routing key | `new_data.{collection}` | `new_data.fournisseurs` |
| Queue | `{collection}_processing_queue` | `fournisseurs_processing_queue` |
| DLQ | `{collection}_dlq` | `fournisseurs_dlq` |

**ALWAYS** follow these naming conventions when creating new exchanges, queues, or routing keys.

## Consumer Pattern (aio_pika)

```python
import aio_pika
import logging

logger = logging.getLogger(__name__)


async def on_message(message: aio_pika.abc.AbstractIncomingMessage):
    async with message.process(requeue=False):
        try:
            body = message.body.decode()
            logger.info(f"📥 Received message: {body[:100]}...")

            # Process message here

            logger.info("✅ Message processed successfully")
        except ValidationError as e:
            # Permanent error — do not requeue
            logger.error(f"❌ Permanent error: {e}")
            # Message will be routed to DLQ via x-dead-letter-exchange
        except Exception as e:
            # Transient error — will be requeued by aio_pika
            logger.error(f"❌ Transient error, requeueing: {e}")
            raise  # aio_pika will requeue


async def start_consumer(connection_url: str, queue_name: str):
    connection = await aio_pika.connect_robust(connection_url)
    channel = await connection.channel()
    await channel.set_qos(prefetch_count=10)

    queue = await channel.declare_queue(queue_name, durable=True)
    await queue.consume(on_message)

    logger.info(f"🚀 Consumer started on queue: {queue_name}")
```

## Publisher Pattern

```python
async def publish_message(
    connection_url: str,
    exchange_name: str,
    routing_key: str,
    body: bytes
):
    connection = await aio_pika.connect_robust(connection_url)
    channel = await connection.channel()

    exchange = await channel.declare_exchange(
        exchange_name, aio_pika.ExchangeType.DIRECT, durable=True
    )

    await exchange.publish(
        aio_pika.Message(body=body, delivery_mode=aio_pika.DeliveryMode.PERSISTENT),
        routing_key=routing_key,
    )
    logger.info(f"📤 Published to {exchange_name}/{routing_key}")
    await connection.close()
```

## Rules

- **ALWAYS** use `connect_robust` (auto-reconnect) instead of `connect`.
- **ALWAYS** set `prefetch_count` — never leave it unlimited.
- **ALWAYS** use `delivery_mode=PERSISTENT` for important messages.
- **ALWAYS** declare queues as `durable=True`.
- **ALWAYS** close connections when done (or use context managers).
- Configure DLQ via exchange arguments:
  ```python
  arguments={"x-dead-letter-exchange": "", "x-dead-letter-routing-key": f"{collection}_dlq"}
  ```
```

---

## 5 — Skills manquants / Missing Skills

### 5.1 — fastapi-service-scaffold — Priorité : 🟡 Recommandé

**Justification :** Les 70+ services Python FastAPI suivent une structure identique. Un skill de scaffold éliminerait le copier-coller et garantirait la conformité dès la création.

> **Note :** Les skills Claude Code utilisent des fichiers Markdown dans `.claude/skills/`. Le skill est invoqué manuellement par l'utilisateur ou suggéré par Claude quand il détecte un besoin de scaffolding.

**Fichier :** `.claude/skills/fastapi-service-scaffold.md`

```markdown
---
name: fastapi-service-scaffold
description: Scaffold a new FastAPI microservice with the standard project structure. Use when creating a new Python microservice from scratch.
---

# Skill : Scaffold FastAPI Microservice

## Paramètre requis

L'utilisateur doit fournir :
- **Nom du service** (ex: `api-mon-nouveau-service`)
- **Description** (ce que fait le service)
- **Type** : `api` (HTTP REST) ou `processor` (RabbitMQ consumer)

## Structure à générer

```
apps-microservices/<service-name>/
  app/
    __init__.py
    main.py
    core/
      __init__.py
      config.py
    router/
      __init__.py
      health.py
    schemas/
      __init__.py
    utils/
      __init__.py
      response.py
  tests/
    __init__.py
    conftest.py
    test_health.py
  Dockerfile
  requirements.txt
  CLAUDE.md
```

## Templates

### app/main.py (type: api)
```python
import logging
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime

from app.core.config import settings
from app.router.health import router as health_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - [WORKER_PID:%(process)d] - %(message)s"
)
logger = logging.getLogger(__name__)

app = FastAPI(title=settings.SERVICE_NAME)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"❌ Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "code": 500,
            "status": "error",
            "message": "Internal server error",
            "details": {"date": datetime.utcnow().isoformat()}
        }
    )


@app.on_event("startup")
async def startup():
    logger.info(f"🚀 {settings.SERVICE_NAME} started on port {settings.PORT}")
```

### app/core/config.py
```python
from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    SERVICE_NAME: str = "<service-name>"
    PORT: int = 8080
    CORS_ORIGINS: List[str] = ["*"]  # Internal service only — restrict for public services

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
```

### app/router/health.py
```python
from fastapi import APIRouter

router = APIRouter(tags=["Health"])


@router.get("/health")
async def health_check():
    return {"status": "healthy"}
```

### app/utils/response.py
```python
from datetime import datetime
import uuid


def success_response(message: str, data: dict = None):
    return {
        "code": 200,
        "status": "success",
        "message": message,
        "details": {
            "date": datetime.utcnow().isoformat(),
            "uid": str(uuid.uuid4()),
            **(data or {})
        }
    }


def error_response(code: int, message: str):
    return {
        "code": code,
        "status": "error",
        "message": message,
        "details": {
            "date": datetime.utcnow().isoformat()
        }
    }
```

### Dockerfile
```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8080

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

### CLAUDE.md
Générer avec la commande /new-service-claude-md en suivant le pattern existant.

## Règles

- Adapter le port en vérifiant qu'il n'entre pas en conflit avec les services existants.
- Pour les services de type `processor`, remplacer le router par un consumer RabbitMQ.
- Toujours inclure le répertoire `tests/` avec au minimum `test_health.py`.
- Utiliser les mêmes versions de dépendances que les services existants (vérifier un requirements.txt voisin).
```

---

## 6 — Hooks manquants / Missing Hooks

### 6.1 — PostToolUse (Edit/Write) — Priorité : 🟡 Recommandé

**Justification :** En l'absence de linter, au minimum vérifier la syntaxe Python après chaque édition de fichier `.py`. Cela empêche Claude d'introduire des erreurs de syntaxe.

### 6.2 — Stop — Priorité : 🔵 Nice-to-have

**Justification :** Les fichiers sont souvent modifiés sans commit correspondant. Un rappel automatique inciterait à utiliser `/commit-msg`.

**Fichier :** `.claude/settings.json`

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Edit|Write",
        "hook": {
          "type": "command",
          "command": "python -m py_compile \"$CLAUDE_FILE_PATH\" 2>&1 || true",
          "condition": "{{ tool_input.file_path ends_with '.py' }}",
          "timeout": 5000,
          "description": "Vérifie la syntaxe Python après chaque édition"
        }
      }
    ],
    "Stop": [
      {
        "hook": {
          "type": "message",
          "message": "Si des fichiers ont été modifiés, pensez à exécuter /commit-msg pour générer le message de commit."
        }
      }
    ]
  }
}
```

> **[A VERIFIER PAR L'EQUIPE]** La syntaxe exacte des hooks Claude Code (notamment `condition` et `matcher`) peut varier selon la version. Valider contre la documentation officielle avant implémentation. Le format ci-dessus est basé sur les conventions documentées de Claude Code.

---

## 7 — Problèmes dans les CLAUDE.md existants / Issues in Existing CLAUDE.md Files

### Tableau des problèmes identifiés

| # | Problème | Sévérité | Détail |
|---|----------|----------|--------|
| 1 | Root CLAUDE.md à 80 lignes | 🟡 | Taille maximale atteinte. Impossible d'ajouter de nouvelles conventions sans supprimer du contenu existant. Envisager de déplacer certaines sections vers des règles dédiées dans `.claude/rules/`. |
| 2 | prix-traitement : incohérence de port | 🔴 | Le Dockerfile `EXPOSE 8595` mais le CMD utilise le port `8591`. L'un des deux est faux. Cela peut causer des échecs de déploiement ou du trafic mal routé sur Cloud Run. |
| 3 | 69/91 services sans commande de test dans CLAUDE.md | 🟡 | La plupart des CLAUDE.md documentent les commandes de build et run mais pas les commandes de test. Quand Claude travaille sur ces services, il ne sait pas comment vérifier son travail. |
| 4 | libs/grpc-stubs potentiellement trompeur | 🟡 | Le répertoire `libs/grpc-stubs/src/grpc_stubs/` ne contient qu'un `__init__.py`. Si le CLAUDE.md de ce package décrit des stubs fonctionnels, c'est trompeur. Les stubs semblent être générés au build Docker et non versionnés. [A VERIFIER PAR L'EQUIPE] |
| 5 | Couverture CI non reflétée | 🔵 | Seulement 13/91 services ont des pipelines CI/CD. Les 78 autres n'ont aucune mention de cette absence dans leur CLAUDE.md. Un avertissement `⚠️ Ce service n'a pas de pipeline CI` aiderait Claude à le signaler. |

### Actions correctives recommandées

**Pour le problème #1 (Root CLAUDE.md trop long) :**

Migrer les conventions détaillées vers des fichiers de règles dans `.claude/rules/`. Le root CLAUDE.md ne devrait contenir que :
- Présentation du projet (5 lignes)
- Structure du monorepo (10 lignes)
- Conventions clés résumées (10 lignes)
- Pointeurs vers les règles détaillées (5 lignes)

**Pour le problème #2 (port prix-traitement) :**

Vérifier le port effectivement utilisé en production (Cloud Run) et aligner Dockerfile + CMD + CLAUDE.md.

**Pour le problème #3 (pas de commande test) :**

Ajouter dans chaque CLAUDE.md de service une section :
```markdown
## Tests
- Commande : `python -m pytest tests/ -v` (ou `⚠️ Aucun test — à créer`)
```

---

## 8 — Points manquants / What You're Missing

### Infrastructure de développement

| Élément manquant | Impact | Effort |
|---|---|---|
| **Aucun .env.example** | Tout nouveau développeur doit deviner les variables d'environnement nécessaires. Frein majeur à l'onboarding. | Moyen (91 services) |
| **Aucun linter configuré** | Pas de ruff.toml, .flake8, .eslintrc, .prettierrc, .editorconfig, biome.json. Le code n'est vérifié par aucun outil automatique. | Faible (1 fichier ruff.toml à la racine) |
| **README.md vide** | Le README ne contient qu'un seul `#`. Aucune information pour un nouveau contributeur. Les guides sont dans docs/ mais pas référencés. | Faible |
| **Pas d'Architecture Decision Records (ADR)** | Les choix techniques (pourquoi Milvus vs Qdrant, pourquoi aio_pika vs pika, etc.) ne sont documentés nulle part. La connaissance est implicite. | Moyen |
| **Pas de registre de ports** | Les 91 services utilisent des ports différents, dispersés dans les Dockerfiles et configs. Pas de vue centralisée. Risque de collision. | Faible |

### Documentation technique

| Élément manquant | Impact | Effort |
|---|---|---|
| **Topologie RabbitMQ non documentée** | Les exchanges, queues et routing keys sont définis dans le code de chaque service. Aucune vue d'ensemble des flux de messages. | Moyen |
| **Pas de stratégie de mise à jour des dépendances** | Ni Renovate, ni Dependabot configuré. Les dépendances ne sont jamais mises à jour proactivement. Risque de vulnérabilités connues. | Faible |
| **CI ne couvre que 13/91 services** | 78 services n'ont aucune vérification automatisée. Les régressions passent inaperçues. | Élevé |
| **Stubs gRPC non versionnés** | Générés au build Docker, pas commités. Les développeurs ne peuvent pas vérifier localement la cohérence des interfaces sans builder le Docker. | Moyen |
| **Pas de spécifications OpenAPI stockées** | FastAPI les génère au runtime, mais elles ne sont pas exportées ni versionnées. Impossible de détecter les breaking changes sur les API. | Moyen |

---

## 9 — Plan d'action priorisé / Prioritized Action Plan

### 🔴 Semaine 1 — Critiques

> Objectif : boucher les trous de sécurité et poser les gardes-fous minimaux.

| # | Action | Fichier à créer/modifier | Temps estimé |
|---|--------|--------------------------|--------------|
| 1 | Ajouter la règle `security.md` | `.claude/rules/security.md` | 15 min |
| 2 | Ajouter la commande `/pre-push` | `.claude/commands/pre-push.md` | 15 min |
| 3 | Ajouter l'agent `test-writer` | `.claude/agents/test-writer.md` | 15 min |
| 4 | Corriger l'incohérence de port dans `prix-traitement` | `apps-microservices/prix-traitement/Dockerfile` | 10 min |
| 5 | Ajouter un contenu minimal au `README.md` | `README.md` | 15 min |

**Résultat attendu :** Les anti-patterns de sécurité connus ne seront plus reproduits. Le code peut être vérifié avant push. La génération de tests peut commencer.

---

### 🟡 Semaine 2-3 — Recommandés

> Objectif : standardiser les conventions et améliorer l'outillage Claude Code.

| # | Action | Fichier à créer/modifier | Temps estimé |
|---|--------|--------------------------|--------------|
| 1 | Ajouter la règle `python-conventions.md` | `.claude/rules/python-conventions.md` | 15 min |
| 2 | Ajouter la règle `testing.md` | `.claude/rules/testing.md` | 15 min |
| 3 | Ajouter la règle `error-handling.md` | `.claude/rules/error-handling.md` | 15 min |
| 4 | Ajouter la commande `/new-endpoint` | `.claude/commands/new-endpoint.md` | 15 min |
| 5 | Ajouter la commande `/sync-proto` | `.claude/commands/sync-proto.md` | 10 min |
| 6 | Ajouter l'agent `security-auditor` | `.claude/agents/security-auditor.md` | 15 min |
| 7 | Créer `.env.example` pour les 5 services les plus utilisés | `apps-microservices/<service>/.env.example` (x5) | 45 min |

**Résultat attendu :** Les conventions Python sont documentées et appliquées par Claude. Les nouveaux endpoints sont scaffoldés de manière cohérente. L'audit de sécurité est automatisable.

---

### 🔵 Mois 1-2 — Nice-to-have

> Objectif : atteindre une maturité complète de la configuration Claude Code.

| # | Action | Fichier à créer/modifier | Temps estimé |
|---|--------|--------------------------|--------------|
| 1 | Ajouter la règle `rabbitmq-patterns.md` | `.claude/rules/rabbitmq-patterns.md` | 15 min |
| 2 | Ajouter l'agent `rabbitmq-reviewer` | `.claude/agents/rabbitmq-reviewer.md` | 15 min |
| 3 | Ajouter le skill `fastapi-service-scaffold` | `.claude/skills/fastapi-service-scaffold.md` | 20 min |
| 4 | Configurer les hooks (settings.json) | `.claude/settings.json` | 15 min |
| 5 | Créer un registre de ports centralisé | `docs/port-registry.md` | 60 min |
| 6 | Documenter la topologie RabbitMQ | `docs/rabbitmq-topology.md` | 90 min |
| 7 | Configurer Dependabot | `.github/dependabot.yml` | 30 min |
| 8 | Étendre la CI à plus de services | `.github/workflows/ci_services_*.yml` (x17+) | 120 min+ |

**Résultat attendu :** Configuration Claude Code complète avec agents, commandes, règles, skills et hooks couvrant tous les aspects du projet. Documentation technique centralisée.

---

## 10 — Métriques de succès / Success Metrics

### Tableau de bord

| Métrique | Valeur actuelle | Cible 3 mois | Cible 6 mois | Comment mesurer |
|---|---|---|---|---|
| **Couverture de tests** (services avec tests/) | 22/91 (24%) | 50/91 (55%) | 70/91 (77%) | `find apps-microservices -name "conftest.py" \| wc -l` |
| **Problèmes de sécurité** (URLs/secrets hardcodés) | 2 connus | 0 | 0 | Exécuter l'agent @security-auditor mensuellement |
| **Couverture CI** (services avec pipeline) | 13/91 (14%) | 30/91 (33%) | 50/91 (55%) | `ls .github/workflows/ci_services_*.yml \| wc -l` |
| **Règles Claude Code actives** | 2 | 7 | 7+ | `ls .claude/rules/*.md \| wc -l` |
| **Agents Claude Code actifs** | 3 | 6 | 6 | `ls .claude/agents/*.md \| wc -l` |
| **Services avec .env.example** | 0 | 10 | 30 | `find apps-microservices -name ".env.example" \| wc -l` |

### Métriques qualitatives

| Métrique | Méthode d'évaluation | Fréquence |
|---|---|---|
| **Temps d'onboarding** | Chronomètre le temps entre le clone du repo et le premier PR soumis par un nouveau dev | A chaque nouvel arrivant |
| **Perte de contexte Claude** | Fréquence d'utilisation de `/compact` par session. Moins = mieux (Claude conserve le contexte plus longtemps) | Hebdomadaire |
| **Violations de règles** | Nombre de fois où @code-reviewer trouve des violations des règles documentées. La tendance doit baisser. | A chaque revue de code |
| **Temps de résolution de bugs** | Temps entre le report d'un bug et le fix commité. L'agent @debugger + les tests devraient réduire ce temps. | Mensuel |

### Formule de progression

```
Score de maturité = (tests/total * 25) + (ci/total * 20) + (regles * 3) + (agents * 3) + (skills * 5) + (hooks * 5) + (envexamples > 0 ? 10 : 0) + (security_issues == 0 ? 10 : 0)
```

**Aujourd'hui :** `(22/91 * 25) + (13/91 * 20) + (2 * 3) + (3 * 3) + (0 * 5) + (0 * 5) + 0 + 0` = **6.0 + 2.9 + 6 + 9 + 0 + 0 + 0 + 0 = 23.9 / 100**

**Cible 3 mois :** `(50/91 * 25) + (30/91 * 20) + (7 * 3) + (6 * 3) + (1 * 5) + (2 * 5) + 10 + 10` = **13.7 + 6.6 + 21 + 18 + 5 + 10 + 10 + 10 = 94.3 / 100**

---

> **Fin du rapport d'audit.**
>
> Ce rapport a été généré le 2026-03-25 sur la base d'un scan complet du dépôt RAG-HP-PUB (branche `features/poc`). Tous les chemins de fichiers, noms de services, et constats sont basés sur des données réelles du scan. Les recommandations marquées [A VERIFIER PAR L'EQUIPE] nécessitent une validation humaine avant implémentation.
