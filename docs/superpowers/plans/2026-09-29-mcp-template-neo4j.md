# Neo4j MCP Template Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an admin create named Neo4j MCP instances (own URI / user / password / database / read-only flag) from the gateway Templates page, hosted by a new `mcp-template-neo4j-service` runner and exposed through `mcp-gateway-service` like the GA4 / GSC template instances.

**Architecture:** A new Python runner (same admin API contract as `mcp-google-templates-runner`) spawns one `mcp-proxy -- mcp-neo4j-cypher` subprocess per instance, with the credentials injected as environment variables (no secret file). The gateway gains a `templates.runner` column and a runner registry so every runner call (spawn / kill / restart / list / sync) goes to the runner that owns the template; Neo4j credentials arrive as form fields and are stored in the existing encrypted `EncryptedCredentials` column. The Vue admin form renders connection fields + a "Lecture seule" checkbox for Neo4j templates.

**Tech Stack:** Python 3.11 / FastAPI / asyncio / `mcp-proxy` / `mcp-neo4j-cypher>=0.6.0` / `neo4j` driver; Go 1.24 / GORM / net/http; Vue 3 + TypeScript + Vitest.

**Spec:** `docs/superpowers/specs/2026-09-29-mcp-template-neo4j-design.md`

## Global Constraints

- Ports follow the Google runner (admin 8595, pool 15000–15099) with the next free slots: runner admin port **8598** (8596 = Zoho, 8597 = HelloData), instance pool **15100–15199**.
- Runner name values: `google` (default for every existing row) and `neo4j`. Column: `templates.runner varchar(16) NOT NULL DEFAULT 'google'`.
- Neo4j credentials JSON shape (encrypted at rest, sent to the runner as `credentials_json`): `{"uri":…,"username":…,"password":…,"database":…}`; `database` defaults to `neo4j`.
- URI schemes accepted: `bolt`, `bolt+s`, `bolt+ssc`, `neo4j`, `neo4j+s`, `neo4j+ssc`; database name `^[A-Za-z0-9._-]{1,63}$`.
- Neo4j `extra_env` accepts only `NEO4J_READ_ONLY` = `"true"` | `"false"`; the template default is `"true"`.
- `mcp-neo4j-cypher>=0.6.0` (verified in 0.6.0: reads `NEO4J_URI/USERNAME/PASSWORD/DATABASE/READ_ONLY`; `NEO4J_URL` wins over `NEO4J_URI`; read-only mode registers `write_neo4j_cypher` with `enabled=False`).
- The password is never logged, never echoed in an error, never returned by the API, never pre-filled in the UI.
- The static `mcp-neo4j-service` (port 8587) is not touched.
- Commits: Conventional Commits, bilingual EN/FR body. Stage only the task's files (`apps-microservices/mcp-gateway-service/internal/gateway/scoped_gateway.go` has an unrelated local edit — never stage it).
- Test commands (the dev box has no Go / pytest — use Docker; run from the repo root):
  - Runner: `docker run --rm -v "$PWD/apps-microservices/mcp-template-neo4j-service":/src -w /src python:3.11-slim sh -c "pip install -q -r requirements.txt pytest pytest-asyncio && python -m pytest -q -p no:cacheprovider tests"`
  - Gateway test command: `docker run --rm -v "$PWD/apps-microservices/mcp-gateway-service":/src -v gomodcache:/go/pkg/mod -w /src golang:1.24-alpine go test ./internal/...` (used to see the expected compile errors / failures).
  - Gateway baseline — the Alpine image builds with `CGO_ENABLED=0`, so **86 pre-existing tests always fail** (`open sqlite: … go-sqlite3 requires cgo`: `internal/api/bdd_handlers_test.go`, `internal/repository/{bdd_used_repo,token_repo,oauth2_repo}_test.go`, `internal/authserver/authorize_test.go` use `gorm.io/driver/sqlite`). Record them once, before Task 4:
    `docker run --rm -v "$PWD/apps-microservices/mcp-gateway-service":/src -v gomodcache:/go/pkg/mod -w /src golang:1.24-alpine sh -c "go test ./internal/... 2>&1 | grep -E '^\s*--- FAIL' | sed 's/ (.*//;s/^ *//' | sort" > /tmp/gw-baseline.fails`
  - **Gateway check** (after each gateway task): the same pipeline into `/tmp/gw-after.fails`, then `diff /tmp/gw-baseline.fails /tmp/gw-after.fails` must print nothing; `go vet ./internal/...` (same image) must be clean; and the task's new tests must PASS: `docker run … go test ./internal/<pkg>/ -run '<TestNames>' -v`.
  - `gofmt` runs in the same image (`docker run --rm -v …:/src -w /src golang:1.24-alpine gofmt -l ./internal ./cmd`). About 40 files are already listed at baseline, so the rule is: no file you **created**, and no file that was gofmt-clean before your edit, may appear in it. Never `gofmt -w` a file that was not clean at baseline (it would reformat unrelated lines).
  - If go stops with `checksum mismatch … SECURITY ERROR`, the `gomodcache` volume holds truncated downloads: clean it once with `docker run --rm -v gomodcache:/m golang:1.24-alpine sh -c "find /m/cache/download -name '*.mod' -size 0 -delete; find /m/cache/download -name '*.lock' -delete"`, or use a fresh volume (`-v gomodcache-neo4j:/go/pkg/mod`, network needed on the first run).
  - Frontend: `cd apps-microservices/mcp-gateway-frontend && npx vitest run <spec files>`

## Review Focus

1. **Template env overriding the connection** — an admin (or a stale template row) setting `NEO4J_URL`, `NEO4J_TRANSPORT` or `NEO4J_MCP_SERVER_*` must not redirect the instance to another database or take it off stdio — nor may the template's `stdio_args` (`--db-url`, `--password`, … win over env vars). Pinned by `test_env_template_cannot_override_connection`, `test_stdio_args_cannot_override_connection` (Task 1), `test_stdio_args_rejected_before_port` (Task 3) and `TestValidateRunnerExtraEnv` / `TestHandleCreateInstance_Neo4jForbiddenExtraEnv_Returns400` (Task 7).
2. **Rotate with a wrong password** — a rejected rotate must leave the instance running on its previous credentials, and the next reconcile must not respawn it with the rejected ones. Pinned by `TestHandleRotateCredentials_Neo4jPrecheckFailure_KeepsOldCredentials` (Task 7: the Neo4j rotate persists only after the runner accepted the new credentials) and the runner validating before `sup.spawn` (Task 3 `test_spawn_precheck_failure_422`).
3. **One runner receiving the other's instances** — the runner sync endpoint must return only the caller's instances, and identical Google/Neo4j tokens must not make routing ambiguous. Pinned by `TestHandleRunnerSync_FiltersByRunner` (Task 8) and the equal-token guard in `app.go` (Task 6).
4. **Password leaking through the stderr tail** shown in the instance detail view — pinned by `test_stderr_redacts_password` (Task 3).
5. **Neo4j down when the runner (re)boots** — reconcile must still spawn instances (pre-check only on admin create/rotate), otherwise a Neo4j blip would orphan every instance. Pinned by `test_reconcile_endpoint_skips_precheck` (Task 3).

---

## File Structure

**New service `apps-microservices/mcp-template-neo4j-service/`**

| File | Responsibility |
|---|---|
| `app/config.py` | Settings (env vars, port 8598, pool 15100–15199, pre-check timeout) |
| `app/auth.py` | `X-Admin-Token` dependency (copy of the Google runner) |
| `app/models.py` | Admin API Pydantic models (copy of the Google runner) |
| `app/port_pool.py` | Port pool (copy of the Google runner) |
| `app/neo4j_env.py` | Parse `credentials_json`, build the child env, strip reserved keys |
| `app/precheck.py` | One-shot Neo4j connectivity check → `PrecheckError(code, message)` |
| `app/supervisor.py` | Spawn / supervise / kill `mcp-proxy -- mcp-neo4j-cypher` with env credentials, stderr redaction |
| `app/gateway_sync.py` | Boot + periodic reconcile against the gateway (copy of the Google runner) |
| `app/api/admin.py` | Admin API; pre-check on `POST /admin/instances` only |
| `app/main.py` | FastAPI app + lifespan |
| `Dockerfile`, `entrypoint.sh`, `requirements.txt`, `CLAUDE.md` | Packaging + docs |
| `tests/*` | pytest suite |

**Gateway `apps-microservices/mcp-gateway-service/`**

| File | Change |
|---|---|
| `internal/db/models.go` | `Template.Runner` |
| `internal/api/runners.go` (new) | Runner names, `RunnerEndpoint`, `runnerEndpoint/ForTemplate/ForInstance/NameForToken`, `runnerHost`, `runnerPrecheckMessage`, not-configured error |
| `internal/api/template_credentials.go` (new) | `credentialsFromRequest`, `validateRunnerExtraEnv` |
| `internal/validation/neo4j.go` (new) | `ValidateNeo4jCredentials` |
| `internal/runnerclient/client.go` | Typed `StatusError` + `Detail()` |
| `internal/api/template_handlers.go` | Route every runner call through the registry; per-runner credentials; pre-check mapping; rotate rollback |
| `internal/api/internal_handlers.go` | Sync filtered by caller runner |
| `internal/api/server_handlers.go` | `Handler.runners` field; delete cascade via the registry |
| `internal/api/google_handlers.go` | Sheet import restricted to the Google runner |
| `internal/api/template_dto.go` | `runner` in the response + export row |
| `internal/repository/template_repo.go` | Upsert `runner`; `InstanceRepo.UpdateExtraEnv` |
| `internal/config/config.go`, `internal/app/app.go` | `NEO4J_TEMPLATES_RUNNER_*` + wiring |
| `init-db/init-mcp-gateway-db.sql` | `neo4j` seed row |
| `CLAUDE.md` | Docs |

**Frontend `apps-microservices/mcp-gateway-frontend/`**

| File | Change |
|---|---|
| `src/components/templates/neo4jConnection.ts` (new) | Pure helpers: detect, validate, FormData fields, read-only env |
| `src/types/templates.ts` | `runner`, optional `credentials`, `neo4j` params, `RotateNeo4jParams` |
| `src/api/templates.ts`, `src/stores/templates.ts` | Neo4j fields on create / rotate |
| `src/views/TemplateInstanceFormView.vue` | Neo4j connection block + "Lecture seule" |
| `src/components/templates/RotateCredentialsModal.vue`, `src/views/TemplateDetailView.vue` | Neo4j rotate |

**Root:** `docker-compose.yml` (new service + gateway env).

---

### Task 1: Runner scaffold + credentials/env builder

**Files:**
- Create: `apps-microservices/mcp-template-neo4j-service/requirements.txt`
- Create: `apps-microservices/mcp-template-neo4j-service/app/__init__.py`, `app/api/__init__.py`, `tests/__init__.py` (empty)
- Create: `apps-microservices/mcp-template-neo4j-service/app/config.py`
- Create (copy): `app/auth.py`, `app/models.py`, `app/port_pool.py`, `tests/test_port_pool.py`
- Create: `apps-microservices/mcp-template-neo4j-service/app/neo4j_env.py`
- Test: `apps-microservices/mcp-template-neo4j-service/tests/conftest.py`, `tests/test_neo4j_env.py`

**Interfaces:**
- Produces: `app.config.settings` (fields below); `app.neo4j_env.Neo4jCredentials(uri, username, password, database)`, `parse_credentials(raw: str) -> Neo4jCredentials`, `InvalidCredentials(ValueError)`, `check_stdio_args(args: list[str]) -> None` (raises `InvalidCredentials`), `build_process_env(base: Mapping[str,str], template_env: Mapping[str,str], creds: Neo4jCredentials) -> dict[str,str]`; `app.port_pool.PortPool` (unchanged copy); `app.models.SpawnRequest`, `SpawnResponse`, `InstanceStatus`, `InstanceListResponse`, `ReconcileRequest` (unchanged copy); `app.auth.require_admin_token` (unchanged copy).

- [ ] **Step 1: Create the package skeleton and the copies**

```bash
S=apps-microservices/mcp-template-neo4j-service
G=apps-microservices/mcp-google-templates-runner
mkdir -p $S/app/api $S/tests
touch $S/app/__init__.py $S/app/api/__init__.py $S/tests/__init__.py
cp $G/app/auth.py $G/app/models.py $G/app/port_pool.py $S/app/
cp $G/tests/test_port_pool.py $S/tests/
```

`$S/requirements.txt`:

```
fastapi
uvicorn[standard]
pydantic
pydantic-settings
httpx
mcp-proxy>=0.11.0
mcp-neo4j-cypher>=0.6.0
neo4j>=5.26,<7
```

`$S/app/config.py`:

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # env vars are already named in full (no prefix stripping)
    model_config = SettingsConfigDict(env_prefix="")

    mcp_gateway_url: str
    mcp_gateway_admin_token: str
    runner_admin_token: str
    # 8595 = mcp-google-templates-runner, 8596 = mcp-zoho-service,
    # 8597 = mcp-hellodata-service: 8598 is the next free MCP port.
    runner_port: int = 8598
    # The Google runner owns 15000-15099; this runner takes the next block.
    runner_instance_port_start: int = 15100
    runner_instance_port_end: int = 15199
    runner_host: str = "0.0.0.0"
    runner_reconcile_interval_sec: int = 300
    runner_reconcile_retry_sec: int = 15
    # Connectivity check run before an admin-requested spawn (create/rotate).
    neo4j_precheck_timeout_sec: float = 5.0


settings = Settings()
```

`$S/tests/conftest.py` (Settings is instantiated at import time, so the required env vars must exist before any `app.*` import):

```python
import os

os.environ.setdefault("MCP_GATEWAY_URL", "http://gateway.invalid")
os.environ.setdefault("MCP_GATEWAY_ADMIN_TOKEN", "gw-token")
os.environ.setdefault("RUNNER_ADMIN_TOKEN", "runner-token")
```

- [ ] **Step 2: Write the failing tests**

`$S/tests/test_neo4j_env.py`:

```python
import pytest

from app.neo4j_env import (
    InvalidCredentials,
    Neo4jCredentials,
    build_process_env,
    check_stdio_args,
    parse_credentials,
)

VALID = '{"uri":"bolt://neo4j:7687","username":"reader","password":"s3cret","database":"graph"}'


def test_parse_valid():
    assert parse_credentials(VALID) == Neo4jCredentials(
        uri="bolt://neo4j:7687", username="reader", password="s3cret", database="graph"
    )


def test_parse_defaults_database():
    creds = parse_credentials('{"uri":"bolt://h:7687","username":"u","password":"p"}')
    assert creds.database == "neo4j"


def test_parse_blank_database_defaults():
    creds = parse_credentials('{"uri":"bolt://h:7687","username":"u","password":"p","database":"  "}')
    assert creds.database == "neo4j"


@pytest.mark.parametrize(
    "raw,msg",
    [
        ("not json", "not valid JSON"),
        ("[]", "JSON object"),
        ('{"username":"u","password":"p"}', "uri"),
        ('{"uri":"bolt://h","password":"p"}', "username"),
        ('{"uri":"bolt://h","username":"u","password":"  "}', "password"),
        ('{"uri":"bolt://h","username":"u","password":"p","database":5}', "database"),
    ],
)
def test_parse_rejects(raw, msg):
    with pytest.raises(InvalidCredentials, match=msg):
        parse_credentials(raw)


def test_repr_hides_password():
    assert "s3cret" not in repr(parse_credentials(VALID))


def test_env_credentials_and_read_only():
    env = build_process_env(
        {"PATH": "/bin", "HOME": "/home/runner", "LANG": "C.UTF-8", "RUNNER_ADMIN_TOKEN": "leak"},
        {"NEO4J_READ_ONLY": "true"},
        parse_credentials(VALID),
    )
    assert env == {
        "PATH": "/bin",
        "HOME": "/home/runner",
        "LANG": "C.UTF-8",
        "NEO4J_READ_ONLY": "true",
        "NEO4J_URI": "bolt://neo4j:7687",
        "NEO4J_USERNAME": "reader",
        "NEO4J_PASSWORD": "s3cret",
        "NEO4J_DATABASE": "graph",
    }


def test_env_template_cannot_override_connection():
    env = build_process_env(
        {},
        {
            "NEO4J_URL": "bolt://evil:7687",
            "NEO4J_URI": "bolt://evil:7687",
            "NEO4J_PASSWORD": "x",
            "NEO4J_TRANSPORT": "http",
            "NEO4J_MCP_SERVER_PORT": "9999",
            "NEO4J_READ_ONLY": "false",
        },
        parse_credentials(VALID),
    )
    assert env["NEO4J_URI"] == "bolt://neo4j:7687"
    assert env["NEO4J_PASSWORD"] == "s3cret"
    assert env["NEO4J_READ_ONLY"] == "false"
    for key in ("NEO4J_URL", "NEO4J_TRANSPORT", "NEO4J_MCP_SERVER_PORT"):
        assert key not in env
    assert env["PATH"]  # default PATH when the base env has none


@pytest.mark.parametrize(
    "args",
    [
        ["--db-url", "bolt://evil:7687"],
        ["--password=x"],
        ["--username", "admin"],
        ["--database", "other"],
        ["--transport", "http"],
        ["--server-port", "9999"],
        ["--allow-origins", "*"],
        ["--allowed-hosts", "*"],
        # argparse abbreviations (allow_abbrev=True upstream)
        ["--db", "bolt://evil:7687"],
        ["--pass", "x"],
        ["--user", "admin"],
        ["--data", "other"],
        ["--trans", "http"],
        ["--serv", "9999"],
    ],
)
def test_stdio_args_cannot_override_connection(args):
    # mcp-neo4j-cypher reads CLI flags BEFORE env vars (utils.process_config).
    with pytest.raises(InvalidCredentials, match="stdio_args may not set"):
        check_stdio_args(args)


def test_stdio_args_other_flags_allowed():
    check_stdio_args([])
    check_stdio_args(["--read-timeout", "30"])
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: the runner test command from Global Constraints.
Expected: a collection error `ModuleNotFoundError: No module named 'app.neo4j_env'` in `tests/test_neo4j_env.py` and `Interrupted: 1 error during collection` (pytest runs no test while a module fails to import).

- [ ] **Step 4: Implement `app/neo4j_env.py`**

```python
"""Neo4j credentials parsing and child-process environment for one instance.

The gateway sends the decrypted credentials as a JSON string
({"uri","username","password","database"}). Nothing is written to disk:
the values go straight into the mcp-neo4j-cypher subprocess environment.
"""
from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field

DEFAULT_PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

# mcp-neo4j-cypher reads NEO4J_URL *before* NEO4J_URI, and NEO4J_TRANSPORT /
# NEO4J_MCP_SERVER_* would switch it off stdio (mcp-proxy needs stdio). The
# connection variables are owned by the runner, never by the template env.
_RESERVED_KEYS = frozenset(
    {
        "NEO4J_URL",
        "NEO4J_URI",
        "NEO4J_USERNAME",
        "NEO4J_PASSWORD",
        "NEO4J_DATABASE",
        "NEO4J_TRANSPORT",
    }
)
_RESERVED_PREFIXES = ("NEO4J_MCP_SERVER_",)


class InvalidCredentials(ValueError):
    """credentials_json does not describe a usable Neo4j connection."""


@dataclass(frozen=True)
class Neo4jCredentials:
    uri: str
    username: str
    password: str = field(repr=False)
    database: str = "neo4j"


def parse_credentials(raw: str) -> Neo4jCredentials:
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError) as e:
        raise InvalidCredentials("credentials_json is not valid JSON") from e
    if not isinstance(data, dict):
        raise InvalidCredentials("credentials_json must be a JSON object")
    values: dict[str, str] = {}
    for key in ("uri", "username", "password"):
        value = data.get(key)
        if not isinstance(value, str) or not value.strip():
            raise InvalidCredentials(f"credentials_json.{key} is required")
        values[key] = value
    database = data.get("database") or "neo4j"
    if not isinstance(database, str):
        raise InvalidCredentials("credentials_json.database must be a string")
    return Neo4jCredentials(
        uri=values["uri"].strip(),
        username=values["username"],
        password=values["password"],
        database=database.strip() or "neo4j",
    )


def _is_reserved(key: str) -> bool:
    return key in _RESERVED_KEYS or key.startswith(_RESERVED_PREFIXES)


# mcp-neo4j-cypher CLI flags win over env vars, so the template's stdio_args
# must not carry any connection/transport flag either ("--password" on argv
# would also be visible in `ps`). Its parser is a plain argparse.ArgumentParser
# (allow_abbrev=True): "--pass" IS "--password", so any long option that is a
# prefix of a reserved flag is rejected too.
_RESERVED_FLAGS = (
    "--db-url",
    "--username",
    "--password",
    "--database",
    "--transport",
    "--server-path",
    "--server-host",
    "--server-port",
    "--allow-origins",
    "--allowed-hosts",
)


def check_stdio_args(args: list[str]) -> None:
    for arg in args:
        name = arg.split("=", 1)[0]
        if len(name) > 2 and name.startswith("--") and any(f.startswith(name) for f in _RESERVED_FLAGS):
            raise InvalidCredentials(f"stdio_args may not set {name}: the runner owns the connection")


def build_process_env(
    base: Mapping[str, str],
    template_env: Mapping[str, str],
    creds: Neo4jCredentials,
) -> dict[str, str]:
    """Minimal child env: PATH/HOME/LANG from the runner (execvp needs PATH),
    then the template env minus reserved keys, then the connection variables
    last so nothing upstream can override them. The runner's own secrets
    (RUNNER_ADMIN_TOKEN, ...) are never inherited."""
    env = {
        "PATH": base.get("PATH", DEFAULT_PATH),
        "HOME": base.get("HOME", "/tmp"),
        "LANG": base.get("LANG", "C.UTF-8"),
    }
    env.update({k: v for k, v in template_env.items() if not _is_reserved(k)})
    env.update(
        {
            "NEO4J_URI": creds.uri,
            "NEO4J_USERNAME": creds.username,
            "NEO4J_PASSWORD": creds.password,
            "NEO4J_DATABASE": creds.database,
        }
    )
    return env
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: the runner test command.
Expected: all tests in `test_neo4j_env.py` and `test_port_pool.py` PASS.

- [ ] **Step 6: Commit**

```bash
git add apps-microservices/mcp-template-neo4j-service
git commit -m "feat(mcp-template-neo4j-service): scaffold runner and Neo4j env builder

Credentials JSON is parsed and injected into the child environment only;
template env cannot override the connection (NEO4J_URL wins over
NEO4J_URI in mcp-neo4j-cypher, so it is stripped).

Squelette du runner et construction de l'environnement Neo4j : les
identifiants ne sont jamais ecrits sur disque et l'env du template ne
peut pas rediriger la connexion."
```

---

### Task 2: Connectivity pre-check

**Files:**
- Create: `apps-microservices/mcp-template-neo4j-service/app/precheck.py`
- Test: `apps-microservices/mcp-template-neo4j-service/tests/test_precheck.py`

**Interfaces:**
- Consumes: `Neo4jCredentials` (Task 1).
- Produces: `app.precheck.verify_connection(creds: Neo4jCredentials, timeout: float) -> None` (async), `app.precheck.PrecheckError(code: str, message: str)` with `.code` / `.message`. Codes: `neo4j_invalid_uri`, `neo4j_auth_failed`, `neo4j_database_not_found`, `neo4j_unreachable`, `neo4j_error`.

- [ ] **Step 1: Write the failing tests**

`tests/test_precheck.py`:

```python
import asyncio

import pytest
from neo4j.exceptions import AuthError, ClientError, ConfigurationError, ServiceUnavailable

import app.precheck as precheck
from app.neo4j_env import Neo4jCredentials
from app.precheck import PrecheckError, verify_connection

CANARY = "canary-7f3a91"  # synthetic value; must never appear in messages
CREDS = Neo4jCredentials(uri="bolt://neo4j:7687", username="u", password=CANARY, database="graph")


class FakeResult:
    async def consume(self):
        return None


class FakeSession:
    def __init__(self, driver):
        self._driver = driver

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def run(self, query):
        self._driver.queries.append(query)
        if self._driver.hang:
            await asyncio.sleep(10)
        if self._driver.exc is not None:
            raise self._driver.exc
        return FakeResult()


class FakeDriver:
    def __init__(self, exc=None, hang=False):
        self.exc = exc
        self.hang = hang
        self.closed = False
        self.database = None
        self.queries = []

    def session(self, database=None):
        self.database = database
        return FakeSession(self)

    async def close(self):
        self.closed = True


def _install(monkeypatch, driver=None, ctor_exc=None):
    calls = {}

    def fake_driver(uri, auth=None, **kwargs):
        calls["uri"], calls["auth"], calls["kwargs"] = uri, auth, kwargs
        if ctor_exc is not None:
            raise ctor_exc
        return driver

    monkeypatch.setattr(precheck.AsyncGraphDatabase, "driver", fake_driver)
    return calls


@pytest.mark.asyncio
async def test_success_pings_the_configured_database(monkeypatch):
    drv = FakeDriver()
    calls = _install(monkeypatch, drv)
    await verify_connection(CREDS, timeout=1.0)
    assert calls["uri"] == "bolt://neo4j:7687"
    assert calls["auth"] == ("u", CANARY)
    assert drv.database == "graph"
    assert drv.queries == ["RETURN 1"]
    assert drv.closed


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "exc,code",
    [
        (AuthError("bad credentials"), "neo4j_auth_failed"),
        (ServiceUnavailable("down"), "neo4j_unreachable"),
        (OSError("connection refused"), "neo4j_unreachable"),
    ],
)
async def test_errors_are_classified(monkeypatch, exc, code):
    drv = FakeDriver(exc=exc)
    _install(monkeypatch, drv)
    with pytest.raises(PrecheckError) as info:
        await verify_connection(CREDS, timeout=1.0)
    assert info.value.code == code
    assert CANARY not in info.value.message
    assert drv.closed


@pytest.mark.asyncio
async def test_database_not_found(monkeypatch):
    exc = ClientError("missing db")
    exc._neo4j_code = "Neo.ClientError.Database.DatabaseNotFound"
    _install(monkeypatch, FakeDriver(exc=exc))
    with pytest.raises(PrecheckError) as info:
        await verify_connection(CREDS, timeout=1.0)
    assert info.value.code == "neo4j_database_not_found"
    assert "graph" in info.value.message


@pytest.mark.asyncio
async def test_other_client_error(monkeypatch):
    exc = ClientError("forbidden")
    exc._neo4j_code = "Neo.ClientError.Security.Forbidden"
    _install(monkeypatch, FakeDriver(exc=exc))
    with pytest.raises(PrecheckError) as info:
        await verify_connection(CREDS, timeout=1.0)
    assert info.value.code == "neo4j_error"


@pytest.mark.asyncio
async def test_timeout_is_unreachable(monkeypatch):
    drv = FakeDriver(hang=True)
    _install(monkeypatch, drv)
    with pytest.raises(PrecheckError) as info:
        await verify_connection(CREDS, timeout=0.05)
    assert info.value.code == "neo4j_unreachable"
    assert drv.closed


@pytest.mark.asyncio
async def test_invalid_uri(monkeypatch):
    _install(monkeypatch, ctor_exc=ConfigurationError("URI scheme 'http' is not supported"))
    with pytest.raises(PrecheckError) as info:
        await verify_connection(CREDS, timeout=1.0)
    assert info.value.code == "neo4j_invalid_uri"
    assert CANARY not in info.value.message
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: the runner test command.
Expected: `ModuleNotFoundError: No module named 'app.precheck'`.

- [ ] **Step 3: Implement `app/precheck.py`**

```python
"""One-shot Neo4j connectivity check, run before an admin-requested spawn.

Only the admin API (create / rotate) calls this: the boot and periodic
reconcile paths spawn without it, so a Neo4j blip while the runner restarts
never orphans instances (mcp-neo4j-cypher reconnects on its own).
"""
from __future__ import annotations

import asyncio

from neo4j import AsyncGraphDatabase
from neo4j.exceptions import (
    AuthError,
    ClientError,
    ConfigurationError,
    DriverError,
    Neo4jError,
    ServiceUnavailable,
)

from app.neo4j_env import Neo4jCredentials

_DATABASE_NOT_FOUND = "Neo.ClientError.Database.DatabaseNotFound"


class PrecheckError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


async def _ping(driver, database: str) -> None:
    async with driver.session(database=database) as session:
        result = await session.run("RETURN 1")
        await result.consume()


async def verify_connection(creds: Neo4jCredentials, timeout: float) -> None:
    """Raise PrecheckError unless the credentials open a session on the
    configured database. Error messages never include the password."""
    try:
        driver = AsyncGraphDatabase.driver(
            creds.uri,
            auth=(creds.username, creds.password),
            connection_timeout=timeout,
        )
    except (ConfigurationError, ValueError) as e:
        raise PrecheckError("neo4j_invalid_uri", f"invalid Neo4j URI {creds.uri!r}") from e
    try:
        await asyncio.wait_for(_ping(driver, creds.database), timeout=timeout)
    except AuthError as e:  # subclass of ClientError: must come first
        raise PrecheckError("neo4j_auth_failed", "Neo4j rejected the username or password") from e
    except ClientError as e:
        if e.code == _DATABASE_NOT_FOUND:
            raise PrecheckError(
                "neo4j_database_not_found", f"database {creds.database!r} does not exist"
            ) from e
        raise PrecheckError("neo4j_error", f"Neo4j refused the connection check ({e.code})") from e
    except (ServiceUnavailable, OSError, asyncio.TimeoutError) as e:
        raise PrecheckError("neo4j_unreachable", f"Neo4j unreachable at {creds.uri}") from e
    except (Neo4jError, DriverError) as e:
        raise PrecheckError("neo4j_error", f"Neo4j connection check failed ({type(e).__name__})") from e
    finally:
        await driver.close()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: the runner test command. Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/mcp-template-neo4j-service/app/precheck.py apps-microservices/mcp-template-neo4j-service/tests/test_precheck.py
git commit -m "feat(mcp-template-neo4j-service): add Neo4j connectivity pre-check

Classifies auth, unreachable, missing database and invalid URI failures
into stable codes the gateway surfaces as HTTP 422.

Verification de connexion Neo4j avant creation : codes d'erreur stables
remontes par le gateway en 422."
```

---

### Task 3: Supervisor, admin API, sync, app, Docker packaging

**Files:**
- Create: `apps-microservices/mcp-template-neo4j-service/app/supervisor.py`
- Create: `apps-microservices/mcp-template-neo4j-service/app/api/admin.py`
- Create (copy): `app/gateway_sync.py`, `tests/test_gateway_sync.py`
- Create: `app/main.py`, `Dockerfile`, `entrypoint.sh`, `CLAUDE.md`
- Test: `tests/test_supervisor.py`, `tests/test_admin.py`

**Interfaces:**
- Consumes: `parse_credentials`, `build_process_env`, `InvalidCredentials` (Task 1); `verify_connection`, `PrecheckError` (Task 2); `PortPool`, `SpawnRequest`, `SpawnResponse`, `InstanceStatus`, `InstanceListResponse`, `ReconcileRequest`, `settings`, `require_admin_token`.
- Produces: HTTP contract identical to the Google runner (`GET /admin/health`, `GET|POST /admin/instances`, `DELETE /admin/instances/{id}`, `POST /admin/instances/{id}/restart`, `POST /admin/reconcile`), plus `POST /admin/instances` → **422** `{"detail":{"code":…,"message":…}}` on invalid credentials or a failed pre-check. `Supervisor(pool)`, `SpawnSpec` (same fields as the Google runner), `Supervisor.spawn(spec, bypass_mcp_proxy=False)`, `.kill`, `.restart`, `.list`, `.get`, `.shutdown`.

- [ ] **Step 1: Copy the unchanged sync module and its tests**

```bash
S=apps-microservices/mcp-template-neo4j-service
G=apps-microservices/mcp-google-templates-runner
cp $G/app/gateway_sync.py $S/app/gateway_sync.py
cp $G/tests/test_gateway_sync.py $S/tests/test_gateway_sync.py
```

`gateway_sync.py` only uses `settings.mcp_gateway_url`, `settings.mcp_gateway_admin_token`, the two reconcile intervals, `SpawnSpec` and `Supervisor.spawn/kill/list` — all present with the same names in this runner.

- [ ] **Step 2: Write the failing supervisor tests**

`tests/test_supervisor.py`:

```python
import asyncio

import pytest
import pytest_asyncio

from app.neo4j_env import InvalidCredentials
from app.port_pool import PortPool
from app.supervisor import SpawnSpec, Supervisor

CREDS = '{"uri":"bolt://neo4j:7687","username":"reader","password":"s3cret","database":"graph"}'


def _spec(instance_id, args, creds=CREDS, env=None):
    return SpawnSpec(
        instance_id=instance_id,
        template_slug="neo4j",
        stdio_command="sh",
        stdio_args=["-c", args],
        env=env if env is not None else {"NEO4J_READ_ONLY": "true"},
        credentials_json=creds,
        credentials_hash="h",
    )


@pytest_asyncio.fixture
async def supervisor():
    pool = PortPool(21000, 21009)
    sup = Supervisor(pool=pool)
    yield sup
    await sup.shutdown()


@pytest.mark.asyncio
async def test_child_receives_neo4j_env(supervisor):
    inst = await supervisor.spawn(
        _spec("n1", 'echo "$NEO4J_URI $NEO4J_USERNAME $NEO4J_DATABASE $NEO4J_READ_ONLY" >&2; sleep 3600'),
        bypass_mcp_proxy=True,
    )
    await asyncio.sleep(0.5)
    assert inst.port in range(21000, 21010)
    assert "bolt://neo4j:7687 reader graph true" in list(inst.stderr_ring)


@pytest.mark.asyncio
async def test_stderr_redacts_password(supervisor):
    inst = await supervisor.spawn(
        _spec("n2", 'echo "password is $NEO4J_PASSWORD" >&2; sleep 3600'),
        bypass_mcp_proxy=True,
    )
    await asyncio.sleep(0.5)
    lines = list(inst.stderr_ring)
    assert "password is ***" in lines
    assert not any("s3cret" in line for line in lines)


@pytest.mark.asyncio
async def test_runner_secrets_not_inherited(supervisor, monkeypatch):
    monkeypatch.setenv("RUNNER_ADMIN_TOKEN", "runner-secret")
    inst = await supervisor.spawn(
        _spec("n3", 'echo "token=[$RUNNER_ADMIN_TOKEN]" >&2; sleep 3600'),
        bypass_mcp_proxy=True,
    )
    await asyncio.sleep(0.5)
    assert "token=[]" in list(inst.stderr_ring)


@pytest.mark.asyncio
async def test_invalid_credentials_consume_no_port(supervisor):
    with pytest.raises(InvalidCredentials):
        await supervisor.spawn(_spec("bad", "sleep 1", creds="{}"), bypass_mcp_proxy=True)
    assert supervisor.get("bad") is None
    assert supervisor._pool.used() == []


@pytest.mark.asyncio
async def test_stdio_args_rejected_before_port(supervisor):
    spec = _spec("argv", "sleep 1")
    spec.stdio_args = ["--db-url", "bolt://evil:7687"]
    with pytest.raises(InvalidCredentials):
        await supervisor.spawn(spec, bypass_mcp_proxy=True)
    assert supervisor.get("argv") is None
    assert supervisor._pool.used() == []


@pytest.mark.asyncio
async def test_kill_releases_port(supervisor):
    await supervisor.spawn(_spec("n4", "sleep 3600"), bypass_mcp_proxy=True)
    await supervisor.kill("n4")
    assert supervisor.get("n4") is None
    assert supervisor._pool.used() == []


@pytest.mark.asyncio
async def test_crashing_child_is_respawned(supervisor):
    inst = await supervisor.spawn(_spec("n5", "sleep 0.5; exit 1"), bypass_mcp_proxy=True)
    first_pid = inst.pid
    await asyncio.sleep(2.0)
    assert supervisor.get("n5").pid != first_pid


@pytest.mark.asyncio
async def test_mcp_proxy_argv(supervisor, monkeypatch):
    seen = {}

    async def fake_exec(*argv, **kwargs):
        seen["argv"] = argv
        seen["env"] = kwargs["env"]
        raise FileNotFoundError("mcp-proxy")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    await supervisor.spawn(_spec("n6", "unused"))
    await asyncio.sleep(0.2)
    port = seen["argv"][2]
    assert list(seen["argv"]) == [
        "mcp-proxy", "--port", port, "--host", "0.0.0.0",
        "--pass-environment", "--stateless", "--", "sh", "-c", "unused",
    ]
    assert seen["env"]["NEO4J_PASSWORD"] == "s3cret"
    # The failed spawn released its port.
    assert supervisor._pool.used() == []
```

- [ ] **Step 3: Run them to verify they fail**

Run: the runner test command.
Expected: `ModuleNotFoundError: No module named 'app.supervisor'`.

- [ ] **Step 4: Implement `app/supervisor.py`**

Adapted from `mcp-google-templates-runner/app/supervisor.py`: no `CredentialsStore`, no secret file, the env is built once per spawn, and stderr is redacted.

```python
from __future__ import annotations

import asyncio
import collections
import dataclasses
import logging
import os
import signal
import time
from typing import Optional

from app.neo4j_env import build_process_env, check_stdio_args, parse_credentials
from app.port_pool import PortPool

logger = logging.getLogger("supervisor")

_REDACTED = "***"


@dataclasses.dataclass
class SpawnSpec:
    instance_id: str
    template_slug: str
    stdio_command: str
    stdio_args: list[str]
    env: dict[str, str]
    credentials_json: str
    credentials_hash: str
    # Last-known port the gateway wants us to reuse (see PortPool.allocate).
    runner_port: Optional[int] = None


@dataclasses.dataclass
class RunningInstance:
    instance_id: str
    template_slug: str
    port: int
    pid: int
    credentials_hash: str
    spec: SpawnSpec = dataclasses.field(repr=False)
    # Full child env, credentials included. Held in memory only.
    proc_env: dict[str, str] = dataclasses.field(repr=False, default_factory=dict)
    # Scrubbed from every stderr line before it reaches stderr_ring (the ring
    # is served to the gateway's instance detail view).
    secret: str = dataclasses.field(repr=False, default="")
    desired_state: str = "running"  # "running" | "stopped"
    status: str = "pending"         # "pending" | "running" | "failed" | "stopped"
    last_error: str = ""
    stderr_ring: collections.deque = dataclasses.field(default_factory=collections.deque)
    exit_count: int = 0
    started_at: float = 0.0
    supervisor_task: Optional[asyncio.Task] = None
    process: Optional[asyncio.subprocess.Process] = None


class Supervisor:
    FLAPPING_THRESHOLD = 5
    FLAPPING_WINDOW_SEC = 10.0
    BACKOFF_INITIAL = 1.0
    BACKOFF_MAX = 60.0
    HEALTHY_RESET_SEC = 60.0
    STDERR_RING_SIZE = 200

    def __init__(self, pool: PortPool):
        self._pool = pool
        self._instances: dict[str, RunningInstance] = {}
        self._lock = asyncio.Lock()

    def get(self, instance_id: str) -> Optional[RunningInstance]:
        return self._instances.get(instance_id)

    def list(self) -> list[RunningInstance]:
        return list(self._instances.values())

    async def spawn(self, spec: SpawnSpec, bypass_mcp_proxy: bool = False) -> RunningInstance:
        # Parse before touching state: invalid credentials (or connection flags
        # in stdio_args) must neither consume a port nor kill a running
        # instance. Raises InvalidCredentials.
        check_stdio_args(spec.stdio_args)
        creds = parse_credentials(spec.credentials_json)
        proc_env = build_process_env(os.environ, spec.env, creds)
        async with self._lock:
            if spec.instance_id in self._instances:
                # Spawn-on-existing = restart-with-possibly-new-spec
                await self._kill_locked(spec.instance_id, release_port=False)
            port = self._pool.allocate(preferred=spec.runner_port)
            inst = RunningInstance(
                instance_id=spec.instance_id,
                template_slug=spec.template_slug,
                port=port,
                pid=0,
                credentials_hash=spec.credentials_hash,
                spec=spec,
                proc_env=proc_env,
                secret=creds.password,
                stderr_ring=collections.deque(maxlen=self.STDERR_RING_SIZE),
                started_at=time.monotonic(),
            )
            self._instances[spec.instance_id] = inst
            inst.supervisor_task = asyncio.create_task(
                self._supervise(inst, bypass_mcp_proxy=bypass_mcp_proxy)
            )
        # Give the supervisor a moment to launch
        await asyncio.sleep(0.1)
        return inst

    async def _release_failed(self, instance_id: str) -> None:
        """Pop a failed instance (binary missing, flapping) and release its port."""
        async with self._lock:
            inst = self._instances.pop(instance_id, None)
            if inst:
                self._pool.release(inst.port)

    async def kill(self, instance_id: str) -> None:
        async with self._lock:
            await self._kill_locked(instance_id, release_port=True)

    async def _kill_locked(self, instance_id: str, release_port: bool) -> None:
        inst = self._instances.pop(instance_id, None)
        if not inst:
            return
        inst.desired_state = "stopped"
        if inst.process and inst.process.returncode is None:
            try:
                inst.process.send_signal(signal.SIGTERM)
                try:
                    await asyncio.wait_for(inst.process.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    inst.process.kill()
                    await inst.process.wait()
            except ProcessLookupError:
                pass
        if inst.supervisor_task and not inst.supervisor_task.done():
            inst.supervisor_task.cancel()
        if release_port:
            self._pool.release(inst.port)

    async def restart(self, instance_id: str) -> None:
        inst = self._instances.get(instance_id)
        if not inst:
            raise KeyError(instance_id)
        # The supervise loop respawns after the child exits.
        if inst.process and inst.process.returncode is None:
            inst.process.send_signal(signal.SIGTERM)

    async def shutdown(self) -> None:
        async with self._lock:
            for iid in list(self._instances.keys()):
                await self._kill_locked(iid, release_port=True)

    async def _supervise(self, inst: RunningInstance, bypass_mcp_proxy: bool) -> None:
        backoff = self.BACKOFF_INITIAL
        while inst.desired_state == "running":
            if bypass_mcp_proxy:
                argv = [inst.spec.stdio_command, *inst.spec.stdio_args]
            else:
                argv = [
                    "mcp-proxy",
                    "--port", str(inst.port),
                    "--host", "0.0.0.0",
                    "--pass-environment",
                    "--stateless",
                    "--", inst.spec.stdio_command, *inst.spec.stdio_args,
                ]
            try:
                proc = await asyncio.create_subprocess_exec(
                    *argv,
                    env=inst.proc_env,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.PIPE,
                    stdin=asyncio.subprocess.DEVNULL,
                )
            except FileNotFoundError as e:
                inst.last_error = f"spawn failed: {e}"
                inst.status = "failed"
                logger.error("instance %s: %s", inst.instance_id, inst.last_error)
                await self._release_failed(inst.instance_id)
                return

            inst.process = proc
            inst.pid = proc.pid
            inst.status = "running"
            inst.started_at = time.monotonic()
            logger.info("instance %s: started pid=%d port=%d", inst.instance_id, proc.pid, inst.port)

            drain_task = asyncio.create_task(self._drain_stderr(inst))
            try:
                exit_code = await proc.wait()
            finally:
                drain_task.cancel()

            if inst.desired_state != "running":
                inst.status = "stopped"
                return

            inst.exit_count += 1
            tail = "\n".join(list(inst.stderr_ring)[-10:])
            inst.last_error = f"exit {exit_code}; stderr tail:\n{tail}"
            logger.warning("instance %s exited: %s", inst.instance_id, inst.last_error)

            uptime = time.monotonic() - inst.started_at
            if uptime < self.FLAPPING_WINDOW_SEC and inst.exit_count >= self.FLAPPING_THRESHOLD:
                inst.status = "failed"
                inst.desired_state = "stopped"
                await self._release_failed(inst.instance_id)
                return

            if uptime > self.HEALTHY_RESET_SEC:
                backoff = self.BACKOFF_INITIAL
                inst.exit_count = 0

            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, self.BACKOFF_MAX)

        inst.status = "stopped"

    async def _drain_stderr(self, inst: RunningInstance) -> None:
        assert inst.process and inst.process.stderr
        try:
            while True:
                line = await inst.process.stderr.readline()
                if not line:
                    return
                text = line.decode("utf-8", errors="replace").rstrip()
                if inst.secret:
                    text = text.replace(inst.secret, _REDACTED)
                inst.stderr_ring.append(text)
        except asyncio.CancelledError:
            return
```

- [ ] **Step 5: Run the supervisor tests**

Run: the runner test command. Expected: `test_supervisor.py` and `test_gateway_sync.py` PASS (the latter imports only `app.config`, `app.gateway_sync` and `app.supervisor`).

- [ ] **Step 6: Write the failing admin API tests**

`tests/test_admin.py`:

```python
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

import app.api.admin as admin
import app.main as main
from app.precheck import PrecheckError

TOKEN = {"X-Admin-Token": "runner-token"}
CREDS = '{"uri":"bolt://neo4j:7687","username":"reader","password":"s3cret","database":"neo4j"}'


def _body(creds=CREDS):
    return {
        "instance_id": "i1",
        "template_slug": "neo4j",
        "stdio_command": "mcp-neo4j-cypher",
        "stdio_args": [],
        "env": {"NEO4J_READ_ONLY": "true"},
        "credentials_json": creds,
        "credentials_hash": "h",
    }


@pytest.fixture
def fake_sup():
    sup = MagicMock()
    sup.list.return_value = []
    sup.spawn = AsyncMock(return_value=MagicMock(port=15100, pid=42))
    sup.kill = AsyncMock()
    return sup


@pytest.fixture
def client(fake_sup):
    main.app.dependency_overrides[admin.get_supervisor] = lambda: fake_sup
    with TestClient(main.app) as c:
        yield c
    main.app.dependency_overrides.clear()


def test_health_no_auth(client):
    r = client.get("/admin/health")
    assert r.status_code == 200 and r.json() == {"status": "ok"}


def test_list_requires_token(client):
    assert client.get("/admin/instances").status_code == 401


def test_spawn_invalid_credentials_422(client, fake_sup):
    r = client.post("/admin/instances", json=_body(creds="{}"), headers=TOKEN)
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "neo4j_invalid_credentials"
    fake_sup.spawn.assert_not_called()


def test_spawn_connection_flag_in_args_422(client, fake_sup):
    body = _body()
    body["stdio_args"] = ["--password", "x"]
    r = client.post("/admin/instances", json=body, headers=TOKEN)
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "neo4j_invalid_credentials"
    fake_sup.spawn.assert_not_called()


def test_spawn_precheck_failure_422(client, fake_sup, monkeypatch):
    async def failing(creds, timeout):
        raise PrecheckError("neo4j_auth_failed", "Neo4j rejected the username or password")

    monkeypatch.setattr(admin, "verify_connection", failing)
    r = client.post("/admin/instances", json=_body(), headers=TOKEN)
    assert r.status_code == 422
    assert r.json()["detail"] == {
        "code": "neo4j_auth_failed",
        "message": "Neo4j rejected the username or password",
    }
    assert "s3cret" not in r.text
    # The running instance (if any) is untouched: spawn() never ran.
    fake_sup.spawn.assert_not_called()


def test_spawn_success(client, fake_sup, monkeypatch):
    monkeypatch.setattr(admin, "verify_connection", AsyncMock(return_value=None))
    r = client.post("/admin/instances", json=_body(), headers=TOKEN)
    assert r.status_code == 200
    assert r.json() == {"port": 15100, "pid": 42}
    fake_sup.spawn.assert_awaited_once()


def test_reconcile_endpoint_skips_precheck(client, fake_sup, monkeypatch):
    check = AsyncMock(side_effect=AssertionError("pre-check must not run on reconcile"))
    monkeypatch.setattr(admin, "verify_connection", check)
    r = client.post("/admin/reconcile", json={"desired_instances": [_body()]}, headers=TOKEN)
    assert r.status_code == 202
    assert r.json() == {"spawned": 1}
    check.assert_not_called()
```

- [ ] **Step 7: Run them to verify they fail**

Run: the runner test command.
Expected: `ModuleNotFoundError: No module named 'app.api.admin'` (then `app.main`).

- [ ] **Step 8: Implement `app/api/admin.py`**

```python
from __future__ import annotations

import asyncio
import logging
import time

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth import require_admin_token
from app.config import settings
from app.models import (
    InstanceListResponse,
    InstanceStatus,
    ReconcileRequest,
    SpawnRequest,
    SpawnResponse,
)
from app.neo4j_env import InvalidCredentials, check_stdio_args, parse_credentials
from app.precheck import PrecheckError, verify_connection
from app.supervisor import SpawnSpec, Supervisor

logger = logging.getLogger("runner.admin")

router = APIRouter(prefix="/admin", dependencies=[Depends(require_admin_token)])


def get_supervisor() -> Supervisor:
    # set by main.py at startup
    from app import main

    if main.supervisor is None:
        raise HTTPException(status_code=503, detail="supervisor not ready")
    return main.supervisor


def _unprocessable(code: str, message: str) -> HTTPException:
    # The gateway reads detail.code / detail.message (runnerclient.StatusError.Detail).
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={"code": code, "message": message},
    )


@router.get("/instances", response_model=InstanceListResponse)
async def list_instances(sup: Supervisor = Depends(get_supervisor)):
    items = []
    for inst in sup.list():
        items.append(
            InstanceStatus(
                id=inst.instance_id,
                port=inst.port,
                pid=inst.pid,
                status=inst.status,
                uptime_s=int(time.monotonic() - inst.started_at) if inst.status == "running" else 0,
                last_error=inst.last_error or None,
                stderr_tail="\n".join(list(inst.stderr_ring)) or None,
            )
        )
    return InstanceListResponse(instances=items)


@router.post("/instances", response_model=SpawnResponse)
async def spawn_instance(req: SpawnRequest, sup: Supervisor = Depends(get_supervisor)):
    # Admin-requested spawn (create / rotate): validate and pre-check BEFORE the
    # supervisor kills any running process for this id, so a rejected rotate
    # leaves the previous instance serving.
    try:
        check_stdio_args(req.stdio_args)
        creds = parse_credentials(req.credentials_json)
    except InvalidCredentials as e:
        raise _unprocessable("neo4j_invalid_credentials", str(e))
    try:
        await verify_connection(creds, settings.neo4j_precheck_timeout_sec)
    except PrecheckError as e:
        logger.warning("pre-check failed for instance %s: %s", req.instance_id, e.code)
        raise _unprocessable(e.code, e.message)
    spec = SpawnSpec(**req.model_dump())
    try:
        inst = await sup.spawn(spec)
    except Exception:
        logger.exception("spawn failed for instance %s", req.instance_id)
        raise HTTPException(status_code=500, detail="spawn failed — see server logs")
    return SpawnResponse(port=inst.port, pid=inst.pid)


@router.delete("/instances/{instance_id}", status_code=status.HTTP_204_NO_CONTENT)
async def kill_instance(instance_id: str, sup: Supervisor = Depends(get_supervisor)):
    try:
        await sup.kill(instance_id)
    except Exception:
        logger.exception("kill failed for instance %s", instance_id)
        raise HTTPException(status_code=500, detail="kill failed — see server logs")
    return None


@router.post("/instances/{instance_id}/restart", status_code=status.HTTP_202_ACCEPTED)
async def restart_instance(instance_id: str, sup: Supervisor = Depends(get_supervisor)):
    try:
        await sup.restart(instance_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="instance not found")
    return {"status": "restarting"}


@router.post("/reconcile", status_code=status.HTTP_202_ACCEPTED)
async def reconcile(req: ReconcileRequest, sup: Supervisor = Depends(get_supervisor)):
    # No pre-check here: reconcile restores desired state, and must not drop
    # instances because Neo4j is briefly unavailable.
    desired = {r.instance_id: r for r in req.desired_instances}
    local = {inst.instance_id: inst for inst in sup.list()}

    for iid in list(local.keys()):
        if iid not in desired:
            await sup.kill(iid)

    sem = asyncio.Semaphore(5)

    async def _spawn_one(r: SpawnRequest):
        async with sem:
            try:
                await sup.spawn(SpawnSpec(**r.model_dump()))
            except Exception:
                logger.exception("reconcile: spawn failed for %s", r.instance_id)

    to_spawn = []
    for iid, r in desired.items():
        if iid not in local:
            to_spawn.append(r)
        elif local[iid].credentials_hash != r.credentials_hash:
            to_spawn.append(r)

    await asyncio.gather(*[_spawn_one(r) for r in to_spawn], return_exceptions=True)
    return {"spawned": len(to_spawn)}
```

- [ ] **Step 9: Implement `app/main.py`**

```python
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.admin import router as admin_router
from app.config import settings
from app.gateway_sync import reconcile_loop
from app.port_pool import PortPool
from app.supervisor import Supervisor

logger = logging.getLogger("runner")
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)

supervisor: Supervisor | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global supervisor
    pool = PortPool(settings.runner_instance_port_start, settings.runner_instance_port_end)
    supervisor = Supervisor(pool=pool)
    logger.info(
        "runner started; gateway=%s ports=%d-%d",
        settings.mcp_gateway_url,
        settings.runner_instance_port_start,
        settings.runner_instance_port_end,
    )
    # Fire-and-forget reconcile loop (boot + periodic), same as the Google
    # runner: a gateway unreachable at boot is retried on the short interval.
    app.state.sync_task = asyncio.create_task(reconcile_loop(supervisor))
    yield
    app.state.sync_task.cancel()
    await asyncio.gather(app.state.sync_task, return_exceptions=True)
    if supervisor:
        await supervisor.shutdown()
    logger.info("runner shut down")


app = FastAPI(title="mcp-template-neo4j-service", lifespan=lifespan)
app.include_router(admin_router)


@app.get("/admin/health")
async def health():
    return {"status": "ok"}
```

- [ ] **Step 10: Packaging files**

`entrypoint.sh`:

```bash
#!/bin/bash
set -e
exec "$@"
```

`Dockerfile`:

```dockerfile
FROM python:3.11-slim

# curl is used by the Docker healthcheck.
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY apps-microservices/mcp-template-neo4j-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY apps-microservices/mcp-template-neo4j-service/app /app/app
COPY apps-microservices/mcp-template-neo4j-service/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Non-root
RUN useradd -u 1000 -m runner
USER runner

EXPOSE 8598
# Dynamic instance ports (15100-15199) are exposed via docker-compose `expose:`.
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8598"]
```

`CLAUDE.md`:

```markdown
# mcp-template-neo4j-service

Python sidecar that hosts the Neo4j template instances spawned by the gateway's Templates feature. One `mcp-proxy -- mcp-neo4j-cypher` subprocess per instance, each on a dynamic port in the 15100–15199 pool, supervised per-instance. Same admin API contract as `mcp-google-templates-runner`.

## Tech Stack

- Python 3.11, FastAPI, Uvicorn, asyncio
- `mcp-proxy` wraps the stdio MCP server into SSE/HTTP
- Upstream package: `mcp-neo4j-cypher>=0.6.0`; `neo4j` driver for the pre-check

## Credentials

The gateway sends `credentials_json` = `{"uri","username","password","database"}` (decrypted from `template_instances.encrypted_credentials`). The runner never writes it to disk: it becomes `NEO4J_URI/USERNAME/PASSWORD/DATABASE` in the child env, set after the template env so nothing can override them. `NEO4J_URL`, `NEO4J_TRANSPORT` and `NEO4J_MCP_SERVER_*` are stripped from the template env (`NEO4J_URL` wins over `NEO4J_URI` upstream), and connection/transport CLI flags (`--db-url`, `--password`, `--transport`, `--server-*`, …, including argparse abbreviations such as `--pass`) in `stdio_args` are rejected with `neo4j_invalid_credentials` (CLI flags win over env vars upstream). The password is replaced by `***` in the stderr tail. `NEO4J_READ_ONLY` comes from the instance `extra_env`; `true` removes `write_neo4j_cypher` from `tools/list`.

## Pre-check

`POST /admin/instances` (gateway create / rotate) first opens a session on the configured database (`RETURN 1`, timeout `NEO4J_PRECHECK_TIMEOUT_SEC`, default 5 s). Failure → 422 `{"detail":{"code","message"}}` with code `neo4j_invalid_credentials`, `neo4j_invalid_uri`, `neo4j_auth_failed`, `neo4j_database_not_found`, `neo4j_unreachable` or `neo4j_error`; nothing is spawned and a running instance with the same id keeps serving. `/admin/reconcile` and the boot/periodic sync skip the pre-check so a Neo4j blip never orphans instances.

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `MCP_GATEWAY_URL` | — | Base URL of mcp-gateway-service for sync |
| `MCP_GATEWAY_ADMIN_TOKEN` | — | Sent as `X-Admin-Token` to the gateway; must equal the gateway's `NEO4J_TEMPLATES_RUNNER_ADMIN_TOKEN` (the gateway uses it to pick this runner's instances) |
| `RUNNER_ADMIN_TOKEN` | — | Required `X-Admin-Token` on incoming `/admin/*` requests |
| `RUNNER_PORT` | `8598` | Admin API port (8595 Google runner, 8596 Zoho, 8597 HelloData) |
| `RUNNER_INSTANCE_PORT_START` / `_END` | `15100` / `15199` | Dynamic pool (the Google runner owns 15000–15099) |
| `NEO4J_PRECHECK_TIMEOUT_SEC` | `5` | Pre-check timeout |

## Admin API (X-Admin-Token)

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/admin/health` | Liveness (no auth) |
| `GET` | `/admin/instances` | List running instances |
| `POST` | `/admin/instances` | Pre-check + spawn instance |
| `DELETE` | `/admin/instances/{id}` | Kill instance |
| `POST` | `/admin/instances/{id}/restart` | Restart in place |
| `POST` | `/admin/reconcile` | Full state reconcile (no pre-check) |

## Tests

    docker run --rm -v "$PWD/apps-microservices/mcp-template-neo4j-service":/src -w /src python:3.11-slim \
      sh -c "pip install -q -r requirements.txt pytest pytest-asyncio && python -m pytest -q -p no:cacheprovider tests"

See `docs/superpowers/specs/2026-09-29-mcp-template-neo4j-design.md`.
```

- [ ] **Step 11: Run the whole runner suite**

Run: the runner test command.
Expected: all tests PASS (`test_neo4j_env`, `test_port_pool`, `test_precheck`, `test_supervisor`, `test_gateway_sync`, `test_admin`).

- [ ] **Step 12: Build the image**

Run: `docker build -f apps-microservices/mcp-template-neo4j-service/Dockerfile -t mcp-template-neo4j-service:dev .`
Expected: the build succeeds, and `docker run --rm --entrypoint mcp-neo4j-cypher mcp-template-neo4j-service:dev --help` prints the CLI usage (binary on PATH).

- [ ] **Step 13: Commit**

First classify the new directory for graphify (the `graphify-coverage-check` CI fails on an unclassified service): in `graphify-out/services-policy.yml`, under `not_graphed:`, right after the `mcp-google-templates-runner` entry, add

```yaml
  - path: apps-microservices/mcp-template-neo4j-service
    reason: templated_wrapper
```

```bash
git add graphify-out/services-policy.yml
git add apps-microservices/mcp-template-neo4j-service
git commit -m "feat(mcp-template-neo4j-service): supervise mcp-neo4j-cypher instances

Admin API mirrors mcp-google-templates-runner; POST /admin/instances
pre-checks the connection (422 on failure, running instance untouched),
reconcile does not. Password redacted from the stderr tail.

Supervision des instances mcp-neo4j-cypher : pre-verification a la
creation uniquement, mot de passe masque dans les logs remontes."
```

---

### Task 4: Gateway — `templates.runner` column, DTOs, export/import, seed

**Files:**
- Modify: `apps-microservices/mcp-gateway-service/internal/db/models.go` (struct `Template`, ~line 500)
- Create: `apps-microservices/mcp-gateway-service/internal/api/runners.go`
- Modify: `internal/api/template_dto.go` (`TemplateResponse`, `TemplateExportRow`)
- Modify: `internal/api/template_handlers.go` (`toTemplateResponse`, `toTemplateExportRow`, `fromTemplateExportRow`)
- Modify: `internal/repository/template_repo.go` (`Upsert`)
- Modify: `internal/repository/template_repo_test.go` (DDL in `newTemplateTestDB`)
- Modify: `init-db/init-mcp-gateway-db.sql`
- Test: `internal/api/runners_test.go`, `internal/repository/template_repo_test.go`

(All gateway paths below are relative to `apps-microservices/mcp-gateway-service/`.)

**Interfaces:**
- Produces: `db.Template.Runner string`; `api.RunnerGoogle = "google"`, `api.RunnerNeo4j = "neo4j"`, `api.knownRunners map[string]bool`, `api.templateRunnerName(tpl *db.Template) string` (nil or "" → `"google"`); JSON field `runner` on `TemplateResponse` and `TemplateExportRow`.

- [ ] **Step 1: Write the failing tests**

`internal/api/runners_test.go`:

```go
package api

import (
	"strings"
	"testing"

	"mcp-gateway/internal/db"
)

func TestTemplateRunnerName(t *testing.T) {
	cases := []struct {
		name string
		tpl  *db.Template
		want string
	}{
		{"nil template", nil, RunnerGoogle},
		{"empty runner", &db.Template{Slug: "ga"}, RunnerGoogle},
		{"neo4j", &db.Template{Slug: "neo4j", Runner: RunnerNeo4j}, RunnerNeo4j},
	}
	for _, c := range cases {
		if got := templateRunnerName(c.tpl); got != c.want {
			t.Errorf("%s: got %q, want %q", c.name, got, c.want)
		}
	}
}

func TestToTemplateResponse_Runner(t *testing.T) {
	if got := toTemplateResponse(db.Template{Slug: "ga"}, 0).Runner; got != RunnerGoogle {
		t.Errorf("legacy row: runner = %q, want google", got)
	}
	if got := toTemplateResponse(db.Template{Slug: "neo4j", Runner: RunnerNeo4j}, 0).Runner; got != RunnerNeo4j {
		t.Errorf("neo4j row: runner = %q", got)
	}
}

func TestTemplateExportRow_RunnerRoundTrip(t *testing.T) {
	row := toTemplateExportRow(db.Template{Slug: "neo4j", Name: "Neo4j", StdioCommand: "mcp-neo4j-cypher", Runner: RunnerNeo4j})
	if row.Runner != RunnerNeo4j {
		t.Fatalf("export runner = %q", row.Runner)
	}
	back, err := fromTemplateExportRow(row)
	if err != nil || back.Runner != RunnerNeo4j {
		t.Fatalf("import: runner=%q err=%v", back.Runner, err)
	}
}

func TestFromTemplateExportRow_RunnerDefaultsAndValidation(t *testing.T) {
	tpl, err := fromTemplateExportRow(TemplateExportRow{Slug: "ga", Name: "GA", StdioCommand: "analytics-mcp"})
	if err != nil || tpl.Runner != RunnerGoogle {
		t.Fatalf("missing runner: got %q err=%v, want google", tpl.Runner, err)
	}
	_, err = fromTemplateExportRow(TemplateExportRow{Slug: "x", Name: "X", StdioCommand: "x", Runner: "docker"})
	if err == nil || !strings.Contains(err.Error(), `unknown runner "docker"`) {
		t.Fatalf("unknown runner: err = %v", err)
	}
}
```

Append to `internal/repository/template_repo_test.go`:

```go
func TestTemplateRepo_UpsertPersistsRunner(t *testing.T) {
	gdb := newTemplateTestDB(t)
	repo := NewTemplateRepo(gdb)
	if err := repo.Upsert([]db.Template{{Slug: "neo4j", Name: "Neo4j", StdioCommand: "mcp-neo4j-cypher", Runner: "neo4j", IsActive: true}}); err != nil {
		t.Fatalf("upsert: %v", err)
	}
	got, err := repo.GetBySlug("neo4j")
	if err != nil || got.Runner != "neo4j" {
		t.Fatalf("runner = %v err=%v", got, err)
	}
	// The repository updates the column on re-import (DoUpdates list);
	// handleImportTemplates refuses the change while instances exist (Task 7).
	if err := repo.Upsert([]db.Template{{Slug: "neo4j", Name: "Neo4j", StdioCommand: "mcp-neo4j-cypher", Runner: "google", IsActive: true}}); err != nil {
		t.Fatalf("re-upsert: %v", err)
	}
	got, _ = repo.GetBySlug("neo4j")
	if got.Runner != "google" {
		t.Fatalf("runner after re-upsert = %q, want google", got.Runner)
	}
}
```

- [ ] **Step 2: Run to verify failure**

Run: the gateway test command.
Expected: compile errors — `undefined: RunnerGoogle`, `undefined: templateRunnerName`, `unknown field Runner in struct literal of type db.Template`.

- [ ] **Step 3: Add the model field**

In `internal/db/models.go`, inside `type Template struct`, directly after the `Kind` field:

```go
	// Runner selects which template runner hosts this template's instances:
	//   "google" — mcp-google-templates-runner (ga, gsc, ...)
	//   "neo4j"  — mcp-template-neo4j-service
	// Every pre-existing row gets "google" from the column default.
	Runner    string    `gorm:"type:varchar(16);not null;default:'google'" json:"runner"`
```

Then `gofmt -w internal/db/models.go` (gofmt-clean at baseline, so only the `Template` struct's alignment moves).

In `newTemplateTestDB` (`internal/repository/template_repo_test.go`), add to the `CREATE TABLE templates` DDL, after the `kind` line:

```sql
			runner              TEXT NOT NULL DEFAULT 'google',
```

- [ ] **Step 4: Create `internal/api/runners.go`**

```go
package api

import "mcp-gateway/internal/db"

// Template runner names (templates.runner). Each runner is a sidecar that
// spawns one mcp-proxy subprocess per template instance.
const (
	RunnerGoogle = "google" // mcp-google-templates-runner
	RunnerNeo4j  = "neo4j"  // mcp-template-neo4j-service
)

var knownRunners = map[string]bool{RunnerGoogle: true, RunnerNeo4j: true}

// templateRunnerName returns the runner owning tpl. Rows created before the
// column existed (and a missing template) belong to the Google runner.
func templateRunnerName(tpl *db.Template) string {
	if tpl == nil || tpl.Runner == "" {
		return RunnerGoogle
	}
	return tpl.Runner
}
```

- [ ] **Step 5: DTOs and export/import**

`internal/api/template_dto.go` — in `TemplateResponse`, after the `Kind` field:

```go
	Runner           string          `json:"runner"`
```

and in `TemplateExportRow`, after `Kind`:

```go
	Runner           string                   `json:"runner"`
```

`internal/api/template_handlers.go`:
- in `toTemplateResponse`, after `Kind: t.Kind,` add `Runner: templateRunnerName(&t),`
- in `toTemplateExportRow`, after `Kind: t.Kind,` add `Runner: t.Runner,`
- in `fromTemplateExportRow`, after the `kind` defaulting block add:

```go
	// Dumps created before templates.runner existed carry no runner: they are
	// Google templates.
	runner := row.Runner
	if runner == "" {
		runner = RunnerGoogle
	}
	if !knownRunners[runner] {
		return db.Template{}, fmt.Errorf("template %s: unknown runner %q", row.Slug, runner)
	}
```

  and add `Runner: runner,` to the `db.Template{...}` literal after `Kind: kind,`.

`internal/repository/template_repo.go` — in `TemplateRepo.Upsert`, add `"runner",` to the `AssignmentColumns` list after `"kind",`.

- [ ] **Step 6: Seed row**

Append to `init-db/init-mcp-gateway-db.sql`, after the existing templates `INSERT … ON DUPLICATE KEY UPDATE …;` statement:

```sql

-- Neo4j template (runner = mcp-template-neo4j-service). Separate statement
-- because only this row sets `runner`; the rows above get 'google' from the
-- column default. NEO4J_READ_ONLY defaults to "true" and is overridden per
-- instance from the "Lecture seule" checkbox. tool_prefix is empty on purpose:
-- each instance must choose its own (the static mcp-neo4j-service owns "neo4j"),
-- which handleCreateInstance enforces.
INSERT INTO templates
  (slug, name, description, icon, stdio_command, stdio_args, default_env, required_extra_env, tool_prefix, tags, kind, runner, is_active, created_at, updated_at)
VALUES
  ('neo4j',
   'Neo4j',
   'MCP wrapper exposing Cypher queries and schema inspection on one Neo4j database (read-only by default).',
   '/images/servers/neo4j.svg',
   'mcp-neo4j-cypher',
   '[]',
   '{"NEO4J_READ_ONLY": "true"}',
   '[{"key":"NEO4J_READ_ONLY","label":"Lecture seule","required":false}]',
   '',
   '["database","neo4j","graph"]',
   'stdio',
   'neo4j',
   1,
   NOW(3), NOW(3))
ON DUPLICATE KEY UPDATE
  name=VALUES(name),
  description=VALUES(description),
  icon=VALUES(icon),
  stdio_command=VALUES(stdio_command),
  stdio_args=VALUES(stdio_args),
  default_env=VALUES(default_env),
  required_extra_env=VALUES(required_extra_env),
  tool_prefix=VALUES(tool_prefix),
  tags=VALUES(tags),
  kind=VALUES(kind),
  runner=VALUES(runner),
  updated_at=NOW(3);
```

(`/images/servers/neo4j.svg` is the icon already used for the static Neo4j server in `mcp-gateway-frontend/src/data/servers.ts`.)

- [ ] **Step 7: Run to verify pass**

Run: the gateway check. Expected: no new failure versus the baseline; `TestTemplateRunnerName`, `TestToTemplateResponse_Runner`, `TestTemplateExportRow_RunnerRoundTrip`, `TestFromTemplateExportRow_RunnerDefaultsAndValidation` (`./internal/api/`) and `TestTemplateRepo_UpsertPersistsRunner` (`./internal/repository/`) PASS.

- [ ] **Step 8: Commit**

```bash
cd apps-microservices/mcp-gateway-service
git add internal/db/models.go internal/api/runners.go internal/api/runners_test.go \
  internal/api/template_dto.go internal/api/template_handlers.go \
  internal/repository/template_repo.go internal/repository/template_repo_test.go \
  init-db/init-mcp-gateway-db.sql
git commit -m "feat(mcp-gateway-service): add templates.runner and the neo4j template

Existing rows default to the google runner; export/import carry the
column and reject unknown runners.

Colonne templates.runner (google par defaut) et template neo4j dans le
seed ; l'export/import transporte la colonne."
cd -
```

---

### Task 5: Gateway — typed runner HTTP errors

**Files:**
- Modify: `internal/runnerclient/client.go` (`do`)
- Test: `internal/runnerclient/client_test.go` (append)

**Interfaces:**
- Produces: `runnerclient.StatusError{Method, Path string; StatusCode int; Body map[string]any}` with `Error()` (same text as before: `runner <METHOD> <path>: status <code>: <body>`) and `Detail() (code, message string)` reading `{"detail":{"code","message"}}`.

- [ ] **Step 1: Write the failing test** — append to `client_test.go` (add `"context"`, `"errors"`, `"net/http"`, `"net/http/httptest"`, `"strings"` to its imports if missing):

```go
func TestSpawn_UnprocessableReturnsStatusErrorWithDetail(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusUnprocessableEntity)
		_, _ = w.Write([]byte(`{"detail":{"code":"neo4j_auth_failed","message":"Neo4j rejected the username or password"}}`))
	}))
	defer srv.Close()

	_, err := New(srv.URL, "tok").Spawn(context.Background(), SpawnRequest{InstanceID: "i1"})
	var se *StatusError
	if !errors.As(err, &se) {
		t.Fatalf("want *StatusError, got %T %v", err, err)
	}
	if se.StatusCode != http.StatusUnprocessableEntity {
		t.Errorf("status = %d", se.StatusCode)
	}
	code, msg := se.Detail()
	if code != "neo4j_auth_failed" || msg != "Neo4j rejected the username or password" {
		t.Errorf("detail = %q / %q", code, msg)
	}
	if !strings.Contains(err.Error(), "runner POST /admin/instances: status 422") {
		t.Errorf("error text changed: %v", err)
	}
}

func TestStatusError_DetailIgnoresNonObjectDetail(t *testing.T) {
	// FastAPI request-validation 422s carry a list in "detail".
	se := &StatusError{StatusCode: 422, Body: map[string]any{"detail": []any{"x"}}}
	if code, msg := se.Detail(); code != "" || msg != "" {
		t.Errorf("got %q / %q, want empty", code, msg)
	}
}
```

- [ ] **Step 2: Run to verify failure**

Run: `docker run --rm -v "$PWD/apps-microservices/mcp-gateway-service":/src -v gomodcache:/go/pkg/mod -w /src golang:1.24-alpine go test ./internal/runnerclient/`
Expected: `undefined: StatusError`.

- [ ] **Step 3: Implement** — in `client.go`, add below the `Client` struct:

```go
// StatusError is returned for any runner response with status >= 400. The
// Error() text is unchanged from the untyped error it replaces.
type StatusError struct {
	Method     string
	Path       string
	StatusCode int
	Body       map[string]any
}

func (e *StatusError) Error() string {
	return fmt.Sprintf("runner %s %s: status %d: %v", e.Method, e.Path, e.StatusCode, e.Body)
}

// Detail returns detail.code / detail.message from a runner body shaped
// {"detail":{"code":…,"message":…}} (the Neo4j runner's pre-check 422).
// Both are empty for any other body.
func (e *StatusError) Detail() (code, message string) {
	d, ok := e.Body["detail"].(map[string]any)
	if !ok {
		return "", ""
	}
	code, _ = d["code"].(string)
	message, _ = d["message"].(string)
	return code, message
}
```

and replace the `>= 400` branch of `do`:

```go
	if resp.StatusCode >= 400 {
		var errBody map[string]any
		_ = json.NewDecoder(io.LimitReader(resp.Body, 4096)).Decode(&errBody)
		return &StatusError{Method: method, Path: path, StatusCode: resp.StatusCode, Body: errBody}
	}
```

- [ ] **Step 4: Run to verify pass** — the gateway check. Expected: no new failure versus the baseline; `TestSpawn_UnprocessableReturnsStatusErrorWithDetail` and `TestStatusError_DetailIgnoresNonObjectDetail` PASS, and so do the existing `./internal/runnerclient/` tests.

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/mcp-gateway-service/internal/runnerclient/client.go apps-microservices/mcp-gateway-service/internal/runnerclient/client_test.go
git commit -m "feat(mcp-gateway-service): type runner HTTP errors

StatusError keeps the previous message and exposes detail.code/message
so the pre-check reason can reach the admin.

Erreurs runner typees : le motif de la pre-verification Neo4j peut
remonter jusqu'a l'admin."
```

---

### Task 6: Gateway — runner registry and routing of every runner call

**Files:**
- Modify: `internal/api/runners.go` (extend)
- Modify: `internal/api/server_handlers.go` (`Handler` struct: new field; delete cascade ~line 610)
- Modify: `internal/api/template_handlers.go` (`handleGetInstance`, `handleCreateInstance`, `createInstanceFromSpec`, `classifyCreateInstanceError`, `handleRestartInstance`, `handleRotateCredentials`, `handleDeleteInstance`)
- Modify: `internal/config/config.go`, `internal/app/app.go`
- Test: `internal/api/runners_test.go` (append), `internal/api/template_api_helpers_test.go` (new), `internal/api/template_routing_test.go` (new)

**Interfaces:**
- Consumes: `templateRunnerName`, `RunnerGoogle`, `RunnerNeo4j` (Task 4); `runnerclient.StatusError` (Task 5).
- Produces:
  - `type RunnerEndpoint struct { Client *runnerclient.Client; URL string; AdminToken string }`
  - `func (h *Handler) SetRunners(runners map[string]RunnerEndpoint)`
  - `func (h *Handler) runnerEndpoint(name string) (RunnerEndpoint, error)` — Google falls back to `h.runner` + `h.config.GoogleTemplatesRunner*`
  - `func (h *Handler) runnerForTemplate(tpl *db.Template) (RunnerEndpoint, error)`
  - `func (h *Handler) runnerForInstance(inst *db.TemplateInstance) (RunnerEndpoint, error)`
  - `func (h *Handler) runnerNameForToken(token string) (string, bool)`
  - `type runnerNotConfiguredError struct{ name string }` (message `runner <name> not configured`), `func isRunnerNotConfigured(err error) bool`
  - `func runnerHost(baseURL string) string`
  - `func runnerPrecheckMessage(err error) (string, bool)` — `"<code>: <message>"` for a runner 422 carrying a detail code
  - new `createInstanceErrorKind` values `createInstanceErrRunnerMissing` (→ 503) and `createInstanceErrPrecheck` (→ 422)
  - test helpers `newTemplateAPITestHandler(t) (*Handler, *gorm.DB)`, `seedTemplate(t, gdb, slug, runner)`, `fakeRunner(t, status, body) *httptest.Server`, `multipartRequest(t, target, fields) *http.Request`
  - config fields `Neo4jTemplatesRunnerURL`, `Neo4jTemplatesRunnerAdminToken`

- [ ] **Step 1: Test helpers** — create `internal/api/template_api_helpers_test.go`:

```go
package api

import (
	"bytes"
	"encoding/json"
	"mime/multipart"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/glebarez/sqlite"
	"gorm.io/gorm"

	"mcp-gateway/internal/config"
	"mcp-gateway/internal/crypto"
	"mcp-gateway/internal/db"
	"mcp-gateway/internal/repository"
	"mcp-gateway/internal/runnerclient"
)

// Same hand-rolled DDL as internal/repository/template_repo_test.go
// (newTemplateTestDB), including the runner column.
const templateAPITestDDL = `
	CREATE TABLE templates (
		slug                TEXT PRIMARY KEY,
		name                TEXT NOT NULL,
		description         TEXT,
		icon                TEXT NOT NULL DEFAULT '',
		stdio_command       TEXT NOT NULL,
		stdio_args          TEXT,
		default_env         TEXT,
		required_extra_env  TEXT,
		tool_prefix         TEXT NOT NULL DEFAULT '',
		tags                TEXT,
		is_active           INTEGER NOT NULL DEFAULT 1,
		kind                TEXT NOT NULL DEFAULT 'stdio',
		runner              TEXT NOT NULL DEFAULT 'google',
		created_at          datetime,
		updated_at          datetime
	);
	CREATE TABLE mcp_servers (
		id                   TEXT PRIMARY KEY,
		name                 TEXT NOT NULL DEFAULT '',
		url                  TEXT NOT NULL DEFAULT '',
		transport_preference TEXT NOT NULL DEFAULT 'auto',
		connect_timeout_ms   INTEGER NOT NULL DEFAULT 10000,
		mcp_transport        TEXT NOT NULL DEFAULT 'http',
		tool_prefix          TEXT NOT NULL DEFAULT '',
		icon                 TEXT NOT NULL DEFAULT '',
		template_slug        TEXT NOT NULL DEFAULT '',
		doc_slug             TEXT,
		is_active            INTEGER NOT NULL DEFAULT 1,
		health_status        TEXT NOT NULL DEFAULT 'unknown',
		created_by           TEXT NOT NULL DEFAULT '',
		created_at           datetime,
		updated_at           datetime
	);
	CREATE TABLE template_instances (
		id                    TEXT PRIMARY KEY,
		template_slug         TEXT NOT NULL,
		name                  TEXT NOT NULL,
		encrypted_credentials BLOB NOT NULL,
		credentials_hash      TEXT NOT NULL,
		extra_env             TEXT,
		runner_port           INTEGER,
		runner_status         TEXT NOT NULL DEFAULT 'pending',
		runner_last_error     TEXT,
		mcp_server_id         TEXT NOT NULL,
		created_by            TEXT NOT NULL DEFAULT '',
		created_at            datetime,
		updated_at            datetime
	);`

const testEncryptionKey = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"

func newTemplateAPITestHandler(t *testing.T) (*Handler, *gorm.DB) {
	t.Helper()
	gdb, err := gorm.Open(sqlite.Open(":memory:"), &gorm.Config{})
	if err != nil {
		t.Fatalf("open sqlite: %v", err)
	}
	if err := gdb.Exec(templateAPITestDDL).Error; err != nil {
		t.Fatalf("ddl: %v", err)
	}
	enc, err := crypto.NewEncryptor(testEncryptionKey)
	if err != nil {
		t.Fatalf("encryptor: %v", err)
	}
	h := &Handler{
		templateRepo: repository.NewTemplateRepo(gdb),
		instanceRepo: repository.NewInstanceRepo(gdb, enc),
		repo:         repository.NewServerRepo(gdb, enc),
		config:       &config.Config{GoogleTemplatesRunnerAdminToken: "google-tok"},
	}
	return h, gdb
}

func seedTemplate(t *testing.T, gdb *gorm.DB, slug, runner string) {
	t.Helper()
	defaultEnv := `{}`
	if runner == RunnerNeo4j {
		defaultEnv = `{"NEO4J_READ_ONLY":"true"}`
	}
	// gdb.Create, not a raw INSERT: GORM binds json.RawMessage as a BLOB; a
	// SQL string literal is stored as TEXT, which the glebarez driver cannot
	// scan back into json.RawMessage (GetBySlug would then fail).
	if err := gdb.Create(&db.Template{
		Slug: slug, Name: slug, StdioCommand: "cmd-" + slug,
		StdioArgs: json.RawMessage(`[]`), DefaultEnv: json.RawMessage(defaultEnv),
		RequiredExtraEnv: json.RawMessage(`[]`), ToolPrefix: slug, Tags: json.RawMessage(`[]`),
		Kind: "stdio", Runner: runner, IsActive: true,
	}).Error; err != nil {
		t.Fatalf("seed template %s: %v", slug, err)
	}
}

func withNeo4jRunner(h *Handler, url string) {
	h.SetRunners(map[string]RunnerEndpoint{RunnerNeo4j: {Client: runnerclient.New(url, "neo-tok"), URL: url, AdminToken: "neo-tok"}})
}

// fakeRunner answers every request with status/body.
func fakeRunner(t *testing.T, status int, body string) *httptest.Server {
	t.Helper()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(status)
		_, _ = w.Write([]byte(body))
	}))
	t.Cleanup(srv.Close)
	return srv
}

func multipartRequest(t *testing.T, target string, fields map[string]string) *http.Request {
	t.Helper()
	var buf bytes.Buffer
	mw := multipart.NewWriter(&buf)
	for k, v := range fields {
		if err := mw.WriteField(k, v); err != nil {
			t.Fatalf("write field: %v", err)
		}
	}
	if err := mw.Close(); err != nil {
		t.Fatalf("close multipart: %v", err)
	}
	req := httptest.NewRequest(http.MethodPost, target, &buf)
	req.Header.Set("Content-Type", mw.FormDataContentType())
	return req
}
```

- [ ] **Step 2: Write the failing tests**

Append to `internal/api/runners_test.go` and extend its import block to:

```go
import (
	"errors"
	"fmt"
	"net/http"
	"strings"
	"testing"

	"mcp-gateway/internal/config"
	"mcp-gateway/internal/db"
	"mcp-gateway/internal/runnerclient"
)
```

```go
func TestRunnerEndpoint_Resolution(t *testing.T) {
	google := runnerclient.New("http://mcp-google-templates-runner:8595", "google-tok")
	neo := runnerclient.New("http://mcp-template-neo4j-service:8598", "neo-tok")
	h := &Handler{
		runner: google,
		config: &config.Config{GoogleTemplatesRunnerURL: "http://mcp-google-templates-runner:8595", GoogleTemplatesRunnerAdminToken: "google-tok"},
	}
	h.SetRunners(map[string]RunnerEndpoint{RunnerNeo4j: {Client: neo, URL: "http://mcp-template-neo4j-service:8598", AdminToken: "neo-tok"}})

	ep, err := h.runnerEndpoint(RunnerGoogle)
	if err != nil || ep.Client != google || ep.URL != "http://mcp-google-templates-runner:8595" {
		t.Fatalf("google: %+v err=%v", ep, err)
	}
	ep, err = h.runnerForTemplate(&db.Template{Slug: "neo4j", Runner: RunnerNeo4j})
	if err != nil || ep.Client != neo {
		t.Fatalf("neo4j: %+v err=%v", ep, err)
	}

	bare := &Handler{}
	_, err = bare.runnerEndpoint(RunnerNeo4j)
	if !isRunnerNotConfigured(err) || err.Error() != "runner neo4j not configured" {
		t.Fatalf("missing neo4j: err=%v", err)
	}
	if _, err := bare.runnerEndpoint(RunnerGoogle); !isRunnerNotConfigured(err) {
		t.Fatalf("missing google: err=%v", err)
	}
}

func TestRunnerNameForToken(t *testing.T) {
	h := &Handler{config: &config.Config{GoogleTemplatesRunnerAdminToken: "google-tok"}}
	h.SetRunners(map[string]RunnerEndpoint{RunnerNeo4j: {Client: runnerclient.New("http://x:8598", "neo-tok"), URL: "http://x:8598", AdminToken: "neo-tok"}})
	cases := []struct {
		token string
		want  string
		ok    bool
	}{
		{"google-tok", RunnerGoogle, true}, // accepted even without a Google client (previous behaviour)
		{"neo-tok", RunnerNeo4j, true},
		{"wrong", "", false},
		{"", "", false},
	}
	for _, c := range cases {
		got, ok := h.runnerNameForToken(c.token)
		if got != c.want || ok != c.ok {
			t.Errorf("token %q: got (%q,%v), want (%q,%v)", c.token, got, ok, c.want, c.ok)
		}
	}

	// Equal tokens: nobody can be identified, so nobody gets instances.
	same := &Handler{config: &config.Config{GoogleTemplatesRunnerAdminToken: "same", Neo4jTemplatesRunnerAdminToken: "same"}}
	if got, ok := same.runnerNameForToken("same"); ok || got != "" {
		t.Errorf("equal tokens: got (%q,%v), want refusal", got, ok)
	}
}

func TestRunnerHost(t *testing.T) {
	cases := map[string]string{
		"http://mcp-template-neo4j-service:8598":    "mcp-template-neo4j-service",
		"https://mcp-google-templates-runner:8595/": "mcp-google-templates-runner",
		"http://runner":                             "runner",
		"runner:8598":                               "runner",
	}
	for in, want := range cases {
		if got := runnerHost(in); got != want {
			t.Errorf("runnerHost(%q) = %q, want %q", in, got, want)
		}
	}
}

func TestRunnerPrecheckMessage(t *testing.T) {
	pre := &runnerclient.StatusError{StatusCode: http.StatusUnprocessableEntity, Body: map[string]any{
		"detail": map[string]any{"code": "neo4j_auth_failed", "message": "Neo4j rejected the username or password"},
	}}
	if msg, ok := runnerPrecheckMessage(fmt.Errorf("wrapped: %w", pre)); !ok || msg != "neo4j_auth_failed: Neo4j rejected the username or password" {
		t.Errorf("got %q %v", msg, ok)
	}
	if _, ok := runnerPrecheckMessage(&runnerclient.StatusError{StatusCode: http.StatusBadGateway}); ok {
		t.Error("502 must not be a pre-check failure")
	}
	if _, ok := runnerPrecheckMessage(errors.New("dial tcp: refused")); ok {
		t.Error("transport error must not be a pre-check failure")
	}
}

func TestClassifyCreateInstanceError_NewKinds(t *testing.T) {
	status, msg := classifyCreateInstanceError(&createInstanceError{Kind: createInstanceErrRunnerMissing, Err: runnerNotConfiguredError{name: RunnerNeo4j}})
	if status != http.StatusServiceUnavailable || msg != "runner neo4j not configured" {
		t.Errorf("runner missing: %d %q", status, msg)
	}
	pre := &runnerclient.StatusError{StatusCode: 422, Body: map[string]any{"detail": map[string]any{"code": "neo4j_unreachable", "message": "Neo4j unreachable at bolt://x:7687"}}}
	status, msg = classifyCreateInstanceError(&createInstanceError{Kind: createInstanceErrPrecheck, Err: pre})
	if status != http.StatusUnprocessableEntity || msg != "neo4j_unreachable: Neo4j unreachable at bolt://x:7687" {
		t.Errorf("precheck: %d %q", status, msg)
	}
}
```

`internal/api/template_routing_test.go`:

```go
package api

import (
	"context"
	"errors"
	"fmt"
	"net"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

// The instance URL must be built from the selected runner's host: the Neo4j
// runner answers on 127.0.0.1 (a live listener), the Google URL is
// unresolvable. Dialing the Google host would end in createInstanceErrUnhealthy.
func TestCreateInstanceFromSpec_UsesSelectedRunnerHost(t *testing.T) {
	h, gdb := newTemplateAPITestHandler(t)
	seedTemplate(t, gdb, "neo4j", RunnerNeo4j)
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("listen: %v", err)
	}
	defer ln.Close()
	port := ln.Addr().(*net.TCPAddr).Port
	srv := fakeRunner(t, http.StatusOK, fmt.Sprintf(`{"port":%d,"pid":1}`, port))
	h.config.GoogleTemplatesRunnerURL = "http://google-host.invalid:8595"
	withNeo4jRunner(h, srv.URL)
	tpl, err := h.templateRepo.GetBySlug("neo4j")
	if err != nil {
		t.Fatalf("template: %v", err)
	}

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	creds := []byte(`{"uri":"bolt://h:7687","username":"u","password":"p","database":"neo4j"}`)
	_, url, err := h.createInstanceFromSpec(ctx, tpl, "prod", creds, nil, nil, "", "neo4jprod", false, "")
	var cerr *createInstanceError
	if errors.As(err, &cerr) && cerr.Kind == createInstanceErrUnhealthy {
		t.Fatalf("dialed the wrong runner host: %v", err)
	}
	// With the hand-rolled mcp_servers DDL the insert may fail after the TCP
	// check (createInstanceErrMCPServerInsert); the host has been proven either way.
	if err == nil && url != fmt.Sprintf("http://127.0.0.1:%d", port) {
		t.Fatalf("url = %s", url)
	}
}

func TestHandleCreateInstance_Neo4jRunnerNotConfigured_Returns503(t *testing.T) {
	h, gdb := newTemplateAPITestHandler(t)
	seedTemplate(t, gdb, "neo4j", RunnerNeo4j)
	req := multipartRequest(t, "/api/v1/template-instances", map[string]string{
		"template_slug": "neo4j",
		"name":          "prod",
	})
	rec := httptest.NewRecorder()
	h.handleCreateInstance(rec, req)
	if rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("got %d body=%s, want 503", rec.Code, rec.Body.String())
	}
	if !strings.Contains(rec.Body.String(), "runner neo4j not configured") {
		t.Errorf("body = %s", rec.Body.String())
	}
}
```

Run `gofmt -w internal/api/runners_test.go internal/api/template_api_helpers_test.go internal/api/template_routing_test.go` (new files must be gofmt-clean).

- [ ] **Step 3: Run to verify failure**

Run: the gateway test command.
Expected: compile errors — `h.SetRunners undefined`, `undefined: RunnerEndpoint`, `undefined: runnerHost`, `undefined: createInstanceErrRunnerMissing`, …

- [ ] **Step 4: Extend `internal/api/runners.go`** — replace its import line with:

```go
import (
	"crypto/subtle"
	"errors"
	"net/http"
	"net/url"
	"strings"

	"mcp-gateway/internal/db"
	"mcp-gateway/internal/runnerclient"
)
```

and append:

```go
// RunnerEndpoint is one configured template runner. The same AdminToken is
// used in both directions: the gateway sends it to the runner, and the runner
// sends it back on /api/v1/internal/runner/sync, which is how the gateway
// knows which runner is asking.
type RunnerEndpoint struct {
	Client     *runnerclient.Client
	URL        string // in-cluster base URL, e.g. http://mcp-template-neo4j-service:8598
	AdminToken string
}

type runnerNotConfiguredError struct{ name string }

func (e runnerNotConfiguredError) Error() string { return "runner " + e.name + " not configured" }

func isRunnerNotConfigured(err error) bool {
	var e runnerNotConfiguredError
	return errors.As(err, &e)
}

// SetRunners wires the non-Google template runners, keyed by runner name.
// The Google runner passed to NewHandler stays the source for "google".
func (h *Handler) SetRunners(runners map[string]RunnerEndpoint) {
	h.runners = runners
}

func (h *Handler) runnerEndpoint(name string) (RunnerEndpoint, error) {
	if ep, ok := h.runners[name]; ok && ep.Client != nil {
		return ep, nil
	}
	if name == RunnerGoogle && h.runner != nil {
		ep := RunnerEndpoint{Client: h.runner}
		if h.config != nil {
			ep.URL = h.config.GoogleTemplatesRunnerURL
			ep.AdminToken = h.config.GoogleTemplatesRunnerAdminToken
		}
		return ep, nil
	}
	return RunnerEndpoint{}, runnerNotConfiguredError{name: name}
}

func (h *Handler) runnerForTemplate(tpl *db.Template) (RunnerEndpoint, error) {
	return h.runnerEndpoint(templateRunnerName(tpl))
}

// runnerForInstance resolves the runner through the instance's template. A
// missing template row (the FK is RESTRICT, so only in tests or a corrupted
// DB) falls back to the Google runner, the only runner that existed before
// templates.runner.
func (h *Handler) runnerForInstance(inst *db.TemplateInstance) (RunnerEndpoint, error) {
	var tpl *db.Template
	if h.templateRepo != nil && inst != nil {
		if t, err := h.templateRepo.GetBySlug(inst.TemplateSlug); err == nil {
			tpl = t
		}
	}
	return h.runnerForTemplate(tpl)
}

// runnerNameForToken identifies the runner calling the internal sync
// endpoint. Every candidate is compared in constant time. The Google token
// is read from config, not from the client, so the Google runner sync keeps
// working exactly as before when only GOOGLE_TEMPLATES_RUNNER_ADMIN_TOKEN is set.
func (h *Handler) runnerNameForToken(token string) (string, bool) {
	if token == "" {
		return "", false
	}
	candidates := map[string]string{}
	if h.config != nil && h.config.GoogleTemplatesRunnerAdminToken != "" {
		candidates[RunnerGoogle] = h.config.GoogleTemplatesRunnerAdminToken
	}
	for name, ep := range h.runners {
		if ep.AdminToken != "" {
			candidates[name] = ep.AdminToken
		}
	}
	// A Neo4j token equal to the Google one (app.go then disables the Neo4j
	// runner) means the caller cannot be identified: refuse rather than hand
	// the Google service-account keys to whichever runner asks.
	if h.config != nil && h.config.Neo4jTemplatesRunnerAdminToken != "" &&
		h.config.Neo4jTemplatesRunnerAdminToken == h.config.GoogleTemplatesRunnerAdminToken {
		return "", false
	}
	matched := ""
	for name, expected := range candidates {
		if subtle.ConstantTimeCompare([]byte(token), []byte(expected)) == 1 {
			matched = name
		}
	}
	return matched, matched != ""
}

// runnerHost extracts the host the gateway dials for an instance port. The
// gateway and the runners share a Docker network, so instance URLs are
// http://<runner host>:<instance port>.
func runnerHost(baseURL string) string {
	if u, err := url.Parse(baseURL); err == nil && u.Hostname() != "" {
		return u.Hostname()
	}
	host := strings.TrimPrefix(strings.TrimPrefix(baseURL, "http://"), "https://")
	return strings.SplitN(host, ":", 2)[0]
}

// runnerPrecheckMessage reports whether err is a runner 422 carrying a
// {"detail":{"code","message"}} body (the Neo4j runner's pre-check), and
// returns "<code>: <message>" for the admin.
func runnerPrecheckMessage(err error) (string, bool) {
	var se *runnerclient.StatusError
	if !errors.As(err, &se) || se.StatusCode != http.StatusUnprocessableEntity {
		return "", false
	}
	code, message := se.Detail()
	if code == "" {
		return "", false
	}
	if message == "" {
		return code, true
	}
	return code + ": " + message, true
}
```

Note: for `runnerHost("runner:8598")`, `url.Parse` either fails (the port-like opaque part) or yields an empty hostname; both reach the fallback branch, which returns `runner`.

- [ ] **Step 5: Handler field** — in `internal/api/server_handlers.go`, in the `Handler` struct, right after `runner       *runnerclient.Client`, add:

```go
	// runners holds the non-Google template runners (see SetRunners); the
	// Google runner is `runner` above.
	runners map[string]RunnerEndpoint
```

Then `gofmt -w internal/api/server_handlers.go` (gofmt-clean at baseline, so only the `Handler` struct's alignment moves).

- [ ] **Step 6: Route every runner call** — edits in `internal/api/template_handlers.go`:

(a) `handleGetInstance`: replace the `// Best-effort: fetch live stderr tail from runner.` block (through its closing `}`) with:

```go
	// Best-effort: fetch live stderr tail from the instance's runner.
	tail := ""
	if ep, rerr := h.runnerForInstance(inst); rerr == nil {
		if statuses, lerr := ep.Client.List(r.Context()); lerr == nil {
			for _, s := range statuses {
				if s.ID == id {
					tail = s.StderrTail
					break
				}
			}
		}
	}
```

(b) `handleCreateInstance`: remove `h.runner == nil || ` from the first guard, and right after the `tpl.Kind` check block add:

```go
	if _, err := h.runnerForTemplate(tpl); err != nil {
		writeJSON(w, http.StatusServiceUnavailable, ErrorResponse{Error: err.Error()})
		return
	}
```

(c) Error kinds — extend the `const` block after `createInstanceErrMCPServerInsert`:

```go
	createInstanceErrRunnerMissing
	createInstanceErrPrecheck
```

and add to the `switch cerr.Kind` in `classifyCreateInstanceError`:

```go
		case createInstanceErrRunnerMissing:
			return http.StatusServiceUnavailable, cerr.Err.Error()
		case createInstanceErrPrecheck:
			msg, _ := runnerPrecheckMessage(cerr.Err)
			return http.StatusUnprocessableEntity, msg
```

(d) `createInstanceFromSpec`: at the very top of the body (before `instanceID := uuid.New().String()`):

```go
	ep, err := h.runnerForTemplate(tpl)
	if err != nil {
		return nil, "", &createInstanceError{Kind: createInstanceErrRunnerMissing, Err: err}
	}
```

then change `resp, err := h.runner.Spawn(` to `resp, err := ep.Client.Spawn(`; in the spawn-error branch replace `return nil, "", &createInstanceError{Kind: createInstanceErrSpawn, Err: err}` with:

```go
		kind := createInstanceErrSpawn
		if _, ok := runnerPrecheckMessage(err); ok {
			kind = createInstanceErrPrecheck
		}
		return nil, "", &createInstanceError{Kind: kind, Err: err}
```

replace the four lines from `runnerHost := strings.TrimPrefix(...)` through `hostPort := fmt.Sprintf(...)` with:

```go
	host := runnerHost(ep.URL)
	instanceURL := fmt.Sprintf("http://%s:%d", host, resp.Port)
	hostPort := fmt.Sprintf("%s:%d", host, resp.Port)
```

and replace both remaining `h.runner.Kill(ctx, instanceID)` with `ep.Client.Kill(ctx, instanceID)`. In the doc comment, change the precondition "credentialsJSON already passed validation.ValidateServiceAccountJSON" to "credentialsJSON already validated for the template's runner (credentialsFromRequest)". (`resp, err := …` and the later `freshInst, err := …` still compile: each declares a new variable on the left.)

(e) `handleRestartInstance`: the guard becomes `if h.instanceRepo == nil {`; replace `if _, err := h.instanceRepo.GetByID(id); err != nil {` with

```go
	inst, err := h.instanceRepo.GetByID(id)
	if err != nil {
```

(keep the block body), then, before `h.runner.Restart`, add

```go
	ep, err := h.runnerForInstance(inst)
	if err != nil {
		writeJSON(w, http.StatusServiceUnavailable, ErrorResponse{Error: err.Error()})
		return
	}
```

and change `h.runner.Restart(` to `ep.Client.Restart(`.

(f) `handleRotateCredentials`: the guard becomes `if h.templateRepo == nil || h.instanceRepo == nil {`; after the `tpl, err := h.templateRepo.GetBySlug(...)` block add

```go
	ep, err := h.runnerForTemplate(tpl)
	if err != nil {
		writeJSON(w, http.StatusServiceUnavailable, ErrorResponse{Error: err.Error()})
		return
	}
```

and change `h.runner.Spawn(` to `ep.Client.Spawn(`. (Task 7 rewrites this handler's body.)

(g) `handleDeleteInstance`: the guard becomes `if h.instanceRepo == nil {`; replace `if _, err := h.instanceRepo.GetByID(id); err != nil {` with `inst, err := h.instanceRepo.GetByID(id)` + `if err != nil {`; replace step 1 (the `h.runner.Kill` block and its comment) with:

```go
	// 1) Kill the runner subprocess first (idempotent on the runner side). An
	//    unconfigured runner cannot be reached anyway; its reconcile loop drops
	//    the instance once the row is gone.
	if ep, rerr := h.runnerForInstance(inst); rerr != nil {
		log.Printf("[templates][WARN] %v — skipping kill for %s (continuing with DB delete)", rerr, id)
	} else if err := ep.Client.Kill(r.Context(), id); err != nil {
		log.Printf("[templates][WARN] runner kill failed for %s: %v (continuing with DB delete)", id, err)
	}
```

(h) `internal/api/server_handlers.go`, template-aware delete cascade: replace

```go
			if h.runner != nil {
				if kerr := h.runner.Kill(r.Context(), inst.ID); kerr != nil {
```

with

```go
			if ep, rerr := h.runnerForInstance(inst); rerr == nil {
				if kerr := ep.Client.Kill(r.Context(), inst.ID); kerr != nil {
```

(the closing braces are unchanged).

`internal/api/google_handlers.go` keeps its `h.runner == nil` guard: the sheet import is Google-only (Task 7 enforces it).

- [ ] **Step 7: Config + wiring**

`internal/config/config.go` — after the `GoogleTemplatesRunnerAdminToken` struct field:

```go
	Neo4jTemplatesRunnerURL         string // NEO4J_TEMPLATES_RUNNER_URL
	Neo4jTemplatesRunnerAdminToken  string // NEO4J_TEMPLATES_RUNNER_ADMIN_TOKEN
```

and in the loader, after `GoogleTemplatesRunnerAdminToken: os.Getenv("GOOGLE_TEMPLATES_RUNNER_ADMIN_TOKEN"),`:

```go
		Neo4jTemplatesRunnerURL:         os.Getenv("NEO4J_TEMPLATES_RUNNER_URL"),
		Neo4jTemplatesRunnerAdminToken:  os.Getenv("NEO4J_TEMPLATES_RUNNER_ADMIN_TOKEN"),
```

(Do **not** run `gofmt -w` on `config.go`: it is not gofmt-clean at baseline and would reformat the whole `Config` literal. Align the two new lines by hand with the Google lines above them.)

`internal/app/app.go` — right after the `apiHandler := api.NewHandler(...)` line:

```go
	// Non-Google template runners. The runner token doubles as the runner's
	// identity on /api/v1/internal/runner/sync, so it must differ from the
	// Google one or the gateway could hand one runner the other's instances.
	runners := map[string]api.RunnerEndpoint{}
	switch {
	case cfg.Neo4jTemplatesRunnerURL == "" || cfg.Neo4jTemplatesRunnerAdminToken == "":
		log.Println("[main] neo4j-templates runner: DISABLED (env vars not set)")
	case cfg.Neo4jTemplatesRunnerAdminToken == cfg.GoogleTemplatesRunnerAdminToken:
		log.Println("[main][ERROR] neo4j-templates runner: DISABLED and runner sync refused for BOTH runners (NEO4J_TEMPLATES_RUNNER_ADMIN_TOKEN must differ from GOOGLE_TEMPLATES_RUNNER_ADMIN_TOKEN)")
	default:
		runners[api.RunnerNeo4j] = api.RunnerEndpoint{
			Client:     runnerclient.New(cfg.Neo4jTemplatesRunnerURL, cfg.Neo4jTemplatesRunnerAdminToken),
			URL:        cfg.Neo4jTemplatesRunnerURL,
			AdminToken: cfg.Neo4jTemplatesRunnerAdminToken,
		}
		log.Printf("[main] neo4j-templates runner: %s", cfg.Neo4jTemplatesRunnerURL)
	}
	apiHandler.SetRunners(runners)
```

- [ ] **Step 8: Run to verify pass**

Run: the gateway check.
Expected: no new failure versus the baseline (the pre-existing `…_NilDeps_Returns503` tests still get 503 from their nil repos); `TestRunnerEndpoint_Resolution`, `TestRunnerNameForToken`, `TestRunnerHost`, `TestRunnerPrecheckMessage`, `TestClassifyCreateInstanceError_NewKinds`, `TestHandleCreateInstance_Neo4jRunnerNotConfigured_Returns503` and `TestCreateInstanceFromSpec_UsesSelectedRunnerHost` PASS.

- [ ] **Step 9: Commit**

```bash
cd apps-microservices/mcp-gateway-service
git add internal/api/runners.go internal/api/runners_test.go \
  internal/api/template_api_helpers_test.go internal/api/template_routing_test.go \
  internal/api/template_handlers.go internal/api/server_handlers.go \
  internal/config/config.go internal/app/app.go
git commit -m "feat(mcp-gateway-service): route template instances to their runner

Every spawn/kill/restart/list goes to the runner named by
templates.runner; instance URLs use that runner's host. A runner 422
pre-check failure surfaces as 422 with its reason.

Chaque instance de template est routee vers son runner ; l'URL de
l'instance utilise l'hote de ce runner."
cd -
```

---

### Task 7: Gateway — Neo4j credentials, extra_env rules, rotate rollback

**Files:**
- Create: `internal/validation/neo4j.go`
- Create: `internal/api/template_credentials.go`
- Modify: `internal/api/template_handlers.go` (`handleCreateInstance`, `handleRotateCredentials`)
- Modify: `internal/api/google_handlers.go` (`handleImportInstancesFromSheet`, after the `tpl.Kind` check ~line 402)
- Modify: `internal/repository/template_repo.go` (`InstanceRepo.UpdateExtraEnv`)
- Test: `internal/validation/neo4j_test.go`, `internal/api/template_credentials_test.go`, `internal/api/template_routing_test.go` (append), `internal/repository/template_repo_test.go` (append)

**Interfaces:**
- Consumes: Task 6 helpers and registry; `runnerPrecheckMessage`.
- Produces:
  - `validation.Neo4jCredentials{URI, Username, Password, Database string}` (JSON `uri`, `username`, `password`, `database`), `validation.ValidateNeo4jCredentials(in Neo4jCredentials) (Neo4jCredentials, error)`, `validation.MaxNeo4jFieldLength = 1024`
  - `credentialsFromRequest(r *http.Request, runnerName string) ([]byte, error)` — multipart fields `neo4j_uri`, `neo4j_username`, `neo4j_password`, `neo4j_database` for Neo4j; file `credentials` for Google
  - `validateRunnerExtraEnv(runnerName string, extra map[string]string) error`
  - `(*repository.InstanceRepo).UpdateExtraEnv(id string, extraEnv json.RawMessage) error`

- [ ] **Step 1: Write the failing tests**

`internal/validation/neo4j_test.go`:

```go
package validation

import (
	"strings"
	"testing"
)

func TestValidateNeo4jCredentials_OK(t *testing.T) {
	got, err := ValidateNeo4jCredentials(Neo4jCredentials{
		URI: "  bolt://neo4j:7687 ", Username: " reader ", Password: " p w ", Database: "",
	})
	if err != nil {
		t.Fatalf("err = %v", err)
	}
	want := Neo4jCredentials{URI: "bolt://neo4j:7687", Username: "reader", Password: " p w ", Database: "neo4j"}
	if got != want {
		t.Errorf("got %+v, want %+v", got, want)
	}
	for _, uri := range []string{"bolt+s://h:7687", "bolt+ssc://h", "neo4j://h:7687", "neo4j+s://h.example.com", "neo4j+ssc://10.0.0.1:7687", "NEO4J://h", "neo4j://h:7687?policy=eu", "bolt://h:7687/"} {
		if _, err := ValidateNeo4jCredentials(Neo4jCredentials{URI: uri, Username: "u", Password: "p"}); err != nil {
			t.Errorf("%s: unexpected err %v", uri, err)
		}
	}
}

func TestValidateNeo4jCredentials_Errors(t *testing.T) {
	long := strings.Repeat("a", MaxNeo4jFieldLength+1)
	cases := []struct {
		name   string
		in     Neo4jCredentials
		errSub string
	}{
		{"empty uri", Neo4jCredentials{Username: "u", Password: "hunter2"}, "uri is required"},
		{"http scheme", Neo4jCredentials{URI: "http://h:7474", Username: "u", Password: "hunter2"}, "uri scheme must be one of"},
		{"no host", Neo4jCredentials{URI: "bolt://", Username: "u", Password: "hunter2"}, "uri must include a host"},
		{"userinfo", Neo4jCredentials{URI: "bolt://neo4j:hunter2@h:7687", Username: "u", Password: "hunter2"}, "must not embed credentials"},
		{"path", Neo4jCredentials{URI: "bolt://h:7687/db", Username: "u", Password: "hunter2"}, "must not contain a path"},
		{"no username", Neo4jCredentials{URI: "bolt://h", Password: "hunter2"}, "username is required"},
		{"blank password", Neo4jCredentials{URI: "bolt://h", Username: "u", Password: "   "}, "password is required"},
		{"bad database", Neo4jCredentials{URI: "bolt://h", Username: "u", Password: "hunter2", Database: "a b"}, "database must match"},
		{"too long", Neo4jCredentials{URI: "bolt://h", Username: long, Password: "hunter2"}, "too long"},
	}
	for _, c := range cases {
		_, err := ValidateNeo4jCredentials(c.in)
		if err == nil || !strings.Contains(err.Error(), c.errSub) {
			t.Errorf("%s: err = %v, want containing %q", c.name, err, c.errSub)
			continue
		}
		if strings.Contains(err.Error(), "hunter2") {
			t.Errorf("%s: error echoes the password: %v", c.name, err)
		}
	}
}
```

`internal/api/template_credentials_test.go`:

```go
package api

import (
	"strings"
	"testing"
)

func TestCredentialsFromRequest_Neo4jFieldsSerialized(t *testing.T) {
	req := multipartRequest(t, "/x", map[string]string{
		"neo4j_uri": "bolt://neo4j:7687", "neo4j_username": "reader", "neo4j_password": "p w", "neo4j_database": "",
	})
	got, err := credentialsFromRequest(req, RunnerNeo4j)
	if err != nil {
		t.Fatalf("err = %v", err)
	}
	want := `{"uri":"bolt://neo4j:7687","username":"reader","password":"p w","database":"neo4j"}`
	if string(got) != want {
		t.Errorf("got %s, want %s", got, want)
	}
}

func TestCredentialsFromRequest_Neo4jInvalid(t *testing.T) {
	req := multipartRequest(t, "/x", map[string]string{"neo4j_uri": "http://h", "neo4j_username": "u", "neo4j_password": "hunter2"})
	_, err := credentialsFromRequest(req, RunnerNeo4j)
	if err == nil || !strings.HasPrefix(err.Error(), "invalid credentials: uri scheme") {
		t.Fatalf("err = %v", err)
	}
	if strings.Contains(err.Error(), "hunter2") {
		t.Error("error echoes the password")
	}
}

func TestCredentialsFromRequest_GoogleStillRequiresFile(t *testing.T) {
	req := multipartRequest(t, "/x", map[string]string{"neo4j_uri": "bolt://h", "neo4j_username": "u", "neo4j_password": "p"})
	_, err := credentialsFromRequest(req, RunnerGoogle)
	if err == nil || err.Error() != "missing credentials file" {
		t.Fatalf("err = %v, want missing credentials file", err)
	}
}

func TestValidateRunnerExtraEnv(t *testing.T) {
	for _, env := range []map[string]string{nil, {}, {"NEO4J_READ_ONLY": "true"}, {"NEO4J_READ_ONLY": "false"}} {
		if err := validateRunnerExtraEnv(RunnerNeo4j, env); err != nil {
			t.Errorf("%v: unexpected %v", env, err)
		}
	}
	bad := map[string]map[string]string{
		"NEO4J_URL":       {"NEO4J_URL": "bolt://evil"},
		"NEO4J_TRANSPORT": {"NEO4J_TRANSPORT": "http"},
		"NEO4J_READ_ONLY": {"NEO4J_READ_ONLY": "yes"},
	}
	for want, env := range bad {
		err := validateRunnerExtraEnv(RunnerNeo4j, env)
		if err == nil || !strings.Contains(err.Error(), want) {
			t.Errorf("%v: err = %v", env, err)
		}
	}
	if err := validateRunnerExtraEnv(RunnerGoogle, map[string]string{"GOOGLE_PROJECT_ID": "x"}); err != nil {
		t.Errorf("google must be unrestricted here: %v", err)
	}
}
```

Append to `internal/api/template_routing_test.go`, and extend its imports to:

```go
import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"net"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"mcp-gateway/internal/db"
)
```

```go
const precheckAuthFailed = `{"detail":{"code":"neo4j_auth_failed","message":"Neo4j rejected the username or password"}}`

func TestHandleCreateInstance_Neo4jPrecheckFailure_Returns422AndRollsBack(t *testing.T) {
	h, gdb := newTemplateAPITestHandler(t)
	seedTemplate(t, gdb, "neo4j", RunnerNeo4j)
	withNeo4jRunner(h, fakeRunner(t, http.StatusUnprocessableEntity, precheckAuthFailed).URL)

	req := multipartRequest(t, "/api/v1/template-instances", map[string]string{
		"template_slug": "neo4j", "name": "prod", "extra_env": `{"NEO4J_READ_ONLY":"true"}`, "tool_prefix": "neo4jprod",
		"neo4j_uri": "bolt://neo4j:7687", "neo4j_username": "reader", "neo4j_password": "wrong",
	})
	rec := httptest.NewRecorder()
	h.handleCreateInstance(rec, req)
	if rec.Code != http.StatusUnprocessableEntity {
		t.Fatalf("got %d body=%s, want 422", rec.Code, rec.Body.String())
	}
	if !strings.Contains(rec.Body.String(), "neo4j_auth_failed: Neo4j rejected the username or password") {
		t.Errorf("body = %s", rec.Body.String())
	}
	var count int64
	gdb.Table("template_instances").Count(&count)
	if count != 0 {
		t.Errorf("template_instances rows = %d, want 0 (rolled back)", count)
	}
}

func TestHandleCreateInstance_Neo4jForbiddenExtraEnv_Returns400(t *testing.T) {
	h, gdb := newTemplateAPITestHandler(t)
	seedTemplate(t, gdb, "neo4j", RunnerNeo4j)
	withNeo4jRunner(h, fakeRunner(t, http.StatusOK, `{"port":1,"pid":1}`).URL)
	req := multipartRequest(t, "/api/v1/template-instances", map[string]string{
		"template_slug": "neo4j", "name": "prod", "extra_env": `{"NEO4J_URL":"bolt://evil:7687"}`, "tool_prefix": "neo4jprod",
		"neo4j_uri": "bolt://neo4j:7687", "neo4j_username": "reader", "neo4j_password": "p",
	})
	rec := httptest.NewRecorder()
	h.handleCreateInstance(rec, req)
	if rec.Code != http.StatusBadRequest || !strings.Contains(rec.Body.String(), "NEO4J_URL") {
		t.Fatalf("got %d body=%s, want 400 naming NEO4J_URL", rec.Code, rec.Body.String())
	}
}

func TestHandleCreateInstance_Neo4jRequiresOwnToolPrefix(t *testing.T) {
	h, gdb := newTemplateAPITestHandler(t)
	seedTemplate(t, gdb, "neo4j", RunnerNeo4j)
	withNeo4jRunner(h, fakeRunner(t, http.StatusOK, `{"port":1,"pid":1}`).URL)
	for _, prefix := range []string{"", "neo4j", "Neo4j"} {
		req := multipartRequest(t, "/api/v1/template-instances", map[string]string{
			"template_slug": "neo4j", "name": "prod", "tool_prefix": prefix,
			"neo4j_uri": "bolt://neo4j:7687", "neo4j_username": "reader", "neo4j_password": "p",
		})
		rec := httptest.NewRecorder()
		h.handleCreateInstance(rec, req)
		if rec.Code != http.StatusBadRequest || !strings.Contains(rec.Body.String(), "tool_prefix") {
			t.Errorf("prefix %q: got %d body=%s, want 400 about tool_prefix", prefix, rec.Code, rec.Body.String())
		}
	}
}

func TestHandleImportTemplates_RunnerChangeWithInstances_Returns409(t *testing.T) {
	h, gdb := newTemplateAPITestHandler(t)
	seedTemplate(t, gdb, "neo4j", RunnerNeo4j)
	if err := h.instanceRepo.Create(&db.TemplateInstance{ID: "i1", TemplateSlug: "neo4j", Name: "n", CredentialsHash: "h", RunnerStatus: "running", MCPServerID: "i1"}, []byte(`{}`)); err != nil {
		t.Fatalf("seed instance: %v", err)
	}
	// No "runner" in the row: fromTemplateExportRow defaults it to google.
	body := `{"version":1,"templates":[{"slug":"neo4j","name":"Neo4j","stdio_command":"mcp-neo4j-cypher","kind":"stdio","is_active":true}]}`
	req := httptest.NewRequest(http.MethodPost, "/api/v1/templates/import", strings.NewReader(body))
	rec := httptest.NewRecorder()
	h.handleImportTemplates(rec, req)
	// Decode first: writeJSON's encoder HTML-escapes '>' as \u003e.
	var errBody ErrorResponse
	_ = json.Unmarshal(rec.Body.Bytes(), &errBody)
	if rec.Code != http.StatusConflict || !strings.Contains(errBody.Error, "cannot change runner neo4j -> google") {
		t.Fatalf("got %d body=%s, want 409", rec.Code, rec.Body.String())
	}
	got, _ := h.templateRepo.GetBySlug("neo4j")
	if got.Runner != RunnerNeo4j {
		t.Errorf("runner changed to %q despite the 409", got.Runner)
	}
}

func TestHandleRotateCredentials_Neo4jPrecheckFailure_KeepsOldCredentials(t *testing.T) {
	h, gdb := newTemplateAPITestHandler(t)
	seedTemplate(t, gdb, "neo4j", RunnerNeo4j)
	withNeo4jRunner(h, fakeRunner(t, http.StatusUnprocessableEntity, precheckAuthFailed).URL)

	oldCreds := []byte(`{"uri":"bolt://neo4j:7687","username":"reader","password":"good","database":"neo4j"}`)
	sum := sha256.Sum256(oldCreds)
	oldHash := hex.EncodeToString(sum[:])
	oldEnv := json.RawMessage(`{"NEO4J_READ_ONLY":"true"}`)
	inst := &db.TemplateInstance{ID: "inst-1", TemplateSlug: "neo4j", Name: "prod", CredentialsHash: oldHash, ExtraEnv: oldEnv, RunnerStatus: "running", MCPServerID: "inst-1"}
	if err := h.instanceRepo.Create(inst, oldCreds); err != nil {
		t.Fatalf("seed instance: %v", err)
	}

	req := multipartRequest(t, "/api/v1/template-instances/inst-1/rotate-credentials", map[string]string{
		"neo4j_uri": "bolt://neo4j:7687", "neo4j_username": "reader", "neo4j_password": "wrong",
		"extra_env": `{"NEO4J_READ_ONLY":"false"}`,
	})
	rec := httptest.NewRecorder()
	h.handleRotateCredentials(rec, req)
	if rec.Code != http.StatusUnprocessableEntity {
		t.Fatalf("got %d body=%s, want 422", rec.Code, rec.Body.String())
	}
	got, plain, err := h.instanceRepo.GetByIDWithCredentials("inst-1")
	if err != nil {
		t.Fatalf("reload: %v", err)
	}
	if string(plain) != string(oldCreds) || got.CredentialsHash != oldHash {
		t.Errorf("rejected credentials were persisted: %s / %s", plain, got.CredentialsHash)
	}
	if string(got.ExtraEnv) != string(oldEnv) {
		t.Errorf("rejected extra_env was persisted: %s", got.ExtraEnv)
	}
}
```

Append to `internal/repository/template_repo_test.go`:

```go
func TestInstanceRepo_UpdateExtraEnv(t *testing.T) {
	gdb := newTemplateTestDB(t)
	repo := NewInstanceRepo(gdb, newTestEncryptor(t))
	inst := &db.TemplateInstance{ID: "i1", TemplateSlug: "neo4j", Name: "n", CredentialsHash: "h", MCPServerID: "s1", RunnerStatus: "running", ExtraEnv: []byte(`{"NEO4J_READ_ONLY":"true"}`)}
	if err := repo.Create(inst, []byte(`{}`)); err != nil {
		t.Fatalf("create: %v", err)
	}
	if err := repo.UpdateExtraEnv("i1", []byte(`{"NEO4J_READ_ONLY":"false"}`)); err != nil {
		t.Fatalf("update: %v", err)
	}
	got, err := repo.GetByID("i1")
	if err != nil || string(got.ExtraEnv) != `{"NEO4J_READ_ONLY":"false"}` {
		t.Fatalf("extra_env = %s err=%v", got.ExtraEnv, err)
	}
	// Writing the same value again must not error (MySQL reports 0 affected rows).
	if err := repo.UpdateExtraEnv("i1", []byte(`{"NEO4J_READ_ONLY":"false"}`)); err != nil {
		t.Fatalf("idempotent update: %v", err)
	}
}
```

- [ ] **Step 2: Run to verify failure**

Run: the gateway test command.
Expected: compile errors — `undefined: ValidateNeo4jCredentials`, `undefined: credentialsFromRequest`, `repo.UpdateExtraEnv undefined`.

- [ ] **Step 3: `internal/validation/neo4j.go`**

```go
package validation

import (
	"fmt"
	"net/url"
	"regexp"
	"strings"
)

// MaxNeo4jFieldLength caps each connection field; real values are < 200 chars.
const MaxNeo4jFieldLength = 1024

// Neo4jCredentials is the connection a Neo4j template instance uses. It is
// JSON-encoded, encrypted into template_instances.encrypted_credentials, and
// sent to mcp-template-neo4j-service as credentials_json.
type Neo4jCredentials struct {
	URI      string `json:"uri"`
	Username string `json:"username"`
	Password string `json:"password"`
	Database string `json:"database"`
}

var neo4jSchemes = map[string]bool{
	"bolt": true, "bolt+s": true, "bolt+ssc": true,
	"neo4j": true, "neo4j+s": true, "neo4j+ssc": true,
}

var neo4jDatabaseRe = regexp.MustCompile(`^[A-Za-z0-9._-]{1,63}$`)

// ValidateNeo4jCredentials trims the admin-entered fields (never the password)
// and returns the normalized value to encrypt. Error messages never include
// the password, nor the URI (which may embed one).
func ValidateNeo4jCredentials(in Neo4jCredentials) (Neo4jCredentials, error) {
	out := Neo4jCredentials{
		URI:      strings.TrimSpace(in.URI),
		Username: strings.TrimSpace(in.Username),
		Password: in.Password,
		Database: strings.TrimSpace(in.Database),
	}
	for _, v := range []string{out.URI, out.Username, out.Password, out.Database} {
		if len(v) > MaxNeo4jFieldLength {
			return out, fmt.Errorf("field too long (max %d characters)", MaxNeo4jFieldLength)
		}
	}
	if out.URI == "" {
		return out, fmt.Errorf("uri is required")
	}
	u, err := url.Parse(out.URI)
	if err != nil {
		return out, fmt.Errorf("uri is not a valid URL")
	}
	if !neo4jSchemes[strings.ToLower(u.Scheme)] {
		return out, fmt.Errorf("uri scheme must be one of bolt, bolt+s, bolt+ssc, neo4j, neo4j+s, neo4j+ssc")
	}
	if u.User != nil {
		return out, fmt.Errorf("uri must not embed credentials; use the username and password fields")
	}
	if u.Hostname() == "" {
		return out, fmt.Errorf("uri must include a host")
	}
	if u.Path != "" && u.Path != "/" {
		return out, fmt.Errorf("uri must not contain a path; set the database field instead")
	}
	if out.Username == "" {
		return out, fmt.Errorf("username is required")
	}
	if strings.TrimSpace(out.Password) == "" {
		return out, fmt.Errorf("password is required")
	}
	if out.Database == "" {
		out.Database = "neo4j"
	}
	if !neo4jDatabaseRe.MatchString(out.Database) {
		return out, fmt.Errorf("database must match [A-Za-z0-9._-]{1,63}")
	}
	return out, nil
}
```

(`url.Parse` keeps the scheme's case, so `strings.ToLower` is what accepts `NEO4J://`, as the driver does.)

- [ ] **Step 4: `internal/api/template_credentials.go`**

```go
package api

import (
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"

	"mcp-gateway/internal/validation"
)

// credentialsFromRequest reads the instance credentials from the multipart
// form, per runner. Google templates upload a service-account JSON file
// ("credentials"); Neo4j templates send connection fields (neo4j_uri,
// neo4j_username, neo4j_password, neo4j_database), serialized here to the
// JSON the Neo4j runner expects. Every error is a client error (400) and
// never contains the password.
func credentialsFromRequest(r *http.Request, runnerName string) ([]byte, error) {
	if runnerName == RunnerNeo4j {
		creds, err := validation.ValidateNeo4jCredentials(validation.Neo4jCredentials{
			URI:      r.FormValue("neo4j_uri"),
			Username: r.FormValue("neo4j_username"),
			Password: r.FormValue("neo4j_password"),
			Database: r.FormValue("neo4j_database"),
		})
		if err != nil {
			return nil, fmt.Errorf("invalid credentials: %w", err)
		}
		return json.Marshal(creds)
	}
	file, hdr, err := r.FormFile("credentials")
	if err != nil {
		return nil, errors.New("missing credentials file")
	}
	defer file.Close()
	if hdr.Size > int64(validation.MaxSAJSONSize) {
		return nil, errors.New("credentials file too large")
	}
	credBytes, err := io.ReadAll(io.LimitReader(file, int64(validation.MaxSAJSONSize)+1))
	if err != nil {
		return nil, errors.New("read credentials: " + err.Error())
	}
	if _, err := validation.ValidateServiceAccountJSON(credBytes); err != nil {
		return nil, errors.New("invalid credentials: " + err.Error())
	}
	return credBytes, nil
}

// validateRunnerExtraEnv enforces runner-specific extra_env rules on top of
// the template's required_extra_env schema. Neo4j instances accept only
// NEO4J_READ_ONLY = "true" | "false": any other NEO4J_* key could redirect the
// connection (NEO4J_URL wins over NEO4J_URI in mcp-neo4j-cypher) or take the
// server off stdio.
func validateRunnerExtraEnv(runnerName string, extra map[string]string) error {
	if runnerName != RunnerNeo4j {
		return nil
	}
	for k, v := range extra {
		if k != "NEO4J_READ_ONLY" {
			return fmt.Errorf("extra_env: %q is not allowed for Neo4j templates (only NEO4J_READ_ONLY)", k)
		}
		if v != "true" && v != "false" {
			return errors.New(`extra_env: NEO4J_READ_ONLY must be "true" or "false"`)
		}
	}
	return nil
}
```

- [ ] **Step 5: `handleCreateInstance`** (in `template_handlers.go`)

- Replace the Task 6 runner check with:

```go
	runnerName := templateRunnerName(tpl)
	if _, err := h.runnerEndpoint(runnerName); err != nil {
		writeJSON(w, http.StatusServiceUnavailable, ErrorResponse{Error: err.Error()})
		return
	}
```

- right after the existing `validateExtraEnv(...)` block add:

```go
	if err := validateRunnerExtraEnv(runnerName, extraEnv); err != nil {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: err.Error()})
		return
	}
```

- replace the whole `// Read credentials file` block (from `file, hdr, err := r.FormFile("credentials")` through the closing `}` of the `ValidateServiceAccountJSON` check) with:

```go
	credBytes, err := credentialsFromRequest(r, runnerName)
	if err != nil {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: err.Error()})
		return
	}
```

- right after the existing `tool_prefix` alphanumeric check block (the one returning "tool_prefix must contain only alphanumeric characters…"), add:

```go
	// The static mcp-neo4j-service already owns the "neo4j" prefix and the
	// gateway has no tool-name collision check: every Neo4j instance must
	// carry its own prefix (the seed leaves the template prefix empty).
	if runnerName == RunnerNeo4j {
		if p := firstNonEmpty(toolPrefixOverride, tpl.ToolPrefix); p == "" || strings.EqualFold(p, "neo4j") {
			writeJSON(w, http.StatusBadRequest, ErrorResponse{
				Error: `tool_prefix is required for Neo4j instances and must not be "neo4j" (used by the static Neo4j server), e.g. neo4jprod`,
			})
			return
		}
	}
```

- change the multipart comment above `ParseMultipartForm` to: `// Multipart: "template_slug", "name", "extra_env" (JSON string), plus either file "credentials" (Google runner) or neo4j_* fields (Neo4j runner).`

- [ ] **Step 6: `handleRotateCredentials`** — keep the guard, the `id` extraction and the `ParseMultipartForm` block; replace everything after them (from `file, hdr, err := r.FormFile("credentials")` to the end of the function) with:

```go
	inst, err := h.instanceRepo.GetByID(id)
	if err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			writeJSON(w, http.StatusNotFound, ErrorResponse{Error: "instance not found"})
			return
		}
		log.Printf("[templates] rotate: lookup %s failed: %v", id, err)
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: "instance lookup failed"})
		return
	}
	tpl, err := h.templateRepo.GetBySlug(inst.TemplateSlug)
	if err != nil {
		log.Printf("[templates] rotate: template lookup for slug %q failed: %v", inst.TemplateSlug, err)
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: "template lookup failed"})
		return
	}
	runnerName := templateRunnerName(tpl)
	ep, err := h.runnerEndpoint(runnerName)
	if err != nil {
		writeJSON(w, http.StatusServiceUnavailable, ErrorResponse{Error: err.Error()})
		return
	}
	credBytes, err := credentialsFromRequest(r, runnerName)
	if err != nil {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: err.Error()})
		return
	}
	hash := sha256.Sum256(credBytes)
	hashHex := hex.EncodeToString(hash[:])

	var extraEnv map[string]string
	if len(inst.ExtraEnv) > 0 {
		_ = json.Unmarshal(inst.ExtraEnv, &extraEnv)
	}
	// A Neo4j rotate may also change NEO4J_READ_ONLY (the "Lecture seule"
	// checkbox lives in the same dialog). A Google rotate keeps extra_env.
	newExtraEnvJSON := inst.ExtraEnv
	if runnerName == RunnerNeo4j {
		if raw := r.FormValue("extra_env"); raw != "" {
			var parsed map[string]string
			if err := json.Unmarshal([]byte(raw), &parsed); err != nil {
				writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "extra_env: invalid JSON"})
				return
			}
			if err := validateExtraEnv(tpl.RequiredExtraEnv, parsed); err != nil {
				writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: err.Error()})
				return
			}
			if err := validateRunnerExtraEnv(runnerName, parsed); err != nil {
				writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: err.Error()})
				return
			}
			extraEnv = parsed
			newExtraEnvJSON, _ = json.Marshal(parsed)
		}
	}
	extraEnvChanged := string(newExtraEnvJSON) != string(inst.ExtraEnv)

	// persist writes the new credentials (encrypted blob + hash) and settings.
	persist := func() error {
		if err := h.instanceRepo.UpdateCredentials(id, credBytes, hashHex); err != nil {
			return err
		}
		if extraEnvChanged {
			return h.instanceRepo.UpdateExtraEnv(id, newExtraEnvJSON)
		}
		return nil
	}
	// Google: DB first — the runner respawn below re-reads from us on reconcile.
	// Neo4j: the runner pre-checks the new credentials, so they are persisted
	// only once it accepted them. A rejected rotate never touches the DB, and a
	// reconcile racing with the pre-check keeps using the stored (previous)
	// credentials.
	persistAfterSpawn := runnerName == RunnerNeo4j
	if !persistAfterSpawn {
		if err := persist(); err != nil {
			log.Printf("[templates] rotate credentials DB update failed (id=%s): %v", id, err)
			writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: "could not persist new credentials"})
			return
		}
	}

	// Respawn with the new credentials. See handleCreateInstance for why the
	// slice is initialised to empty rather than left nil.
	stdioArgs := []string{}
	if len(tpl.StdioArgs) > 0 {
		_ = json.Unmarshal(tpl.StdioArgs, &stdioArgs)
		if stdioArgs == nil {
			stdioArgs = []string{}
		}
	}
	env := renderEnv(tpl.DefaultEnv, extraEnv, id)
	if _, err := ep.Client.Spawn(r.Context(), runnerclient.SpawnRequest{
		InstanceID:      id,
		TemplateSlug:    inst.TemplateSlug,
		StdioCommand:    tpl.StdioCommand,
		StdioArgs:       stdioArgs,
		Env:             env,
		CredentialsJSON: string(credBytes),
		CredentialsHash: hashHex,
		RunnerPort:      inst.RunnerPort,
	}); err != nil {
		if msg, ok := runnerPrecheckMessage(err); ok {
			// Nothing was persisted and the runner left the running process alone.
			writeJSON(w, http.StatusUnprocessableEntity, ErrorResponse{Error: msg})
			return
		}
		log.Printf("[templates] runner respawn after rotate failed (id=%s): %v", id, err)
		if uErr := h.instanceRepo.UpdateStatus(id, "failed", "rotate: "+err.Error(), nil); uErr != nil {
			log.Printf("[templates][WARN] could not persist failed status after rotate (id=%s): %v", id, uErr)
		}
		writeJSON(w, http.StatusBadGateway, ErrorResponse{Error: "runner unavailable — see server logs"})
		return
	}
	if persistAfterSpawn {
		if err := persist(); err != nil {
			// The runner already serves the new credentials; the next reconcile
			// reverts it to the stored (previous) ones, the safe direction.
			log.Printf("[templates] rotate credentials DB update failed after respawn (id=%s): %v", id, err)
			writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: "could not persist new credentials"})
			return
		}
	}
	writeJSON(w, http.StatusAccepted, map[string]string{"status": "rotating"})
}
```

This supersedes the Task 6 edit (f). Three deliberate differences from the previous body: for Neo4j the credentials are persisted only after the runner accepted them (Google keeps DB-first); the instance/template lookups now come before reading the credentials (the runner decides which fields to read), and `RunnerPort: inst.RunnerPort` is passed so the respawn keeps the port stored in `mcp_servers.url`. `io` stays imported in `template_handlers.go` (still used by `handleImportTemplates`).

- [ ] **Step 7: `InstanceRepo.UpdateExtraEnv`** — append to `internal/repository/template_repo.go`, after `UpdateCredentials`:

```go
// UpdateExtraEnv replaces the admin-supplied extra_env JSON (non-secret,
// stored in clear). No RowsAffected check: MySQL reports 0 affected rows when
// the value is unchanged, which is not an error here.
func (r *InstanceRepo) UpdateExtraEnv(id string, extraEnv json.RawMessage) error {
	return r.db.Model(&db.TemplateInstance{}).Where("id = ?", id).Update("extra_env", extraEnv).Error
}
```

(add `"encoding/json"` to the file's imports if absent.)

- [ ] **Step 8: Sheet import is Google-only** — in `internal/api/google_handlers.go`, `handleImportInstancesFromSheet`, directly after the `tpl.Kind` check block:

```go
	// Sheet rows carry a service-account JSON cell: only Google-runner
	// templates can be imported this way.
	if runner := templateRunnerName(tpl); runner != RunnerGoogle {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{
			Error: fmt.Sprintf("template %s does not support Google Sheets import (runner=%s)", tpl.Slug, runner),
		})
		return
	}
```

- [ ] **Step 9: Catalog import cannot move a template with instances to another runner** — in `handleImportTemplates` (`template_handlers.go`), right before `if err := h.templateRepo.Upsert(rows); err != nil {`, add:

```go
	// Changing templates.runner while instances exist would hand their
	// credentials to the other runner on its next sync (and kill them on the
	// old one). The repository allows it; the import refuses it.
	if h.instanceRepo != nil {
		counts, err := h.instanceRepo.CountsByTemplate()
		if err != nil {
			log.Printf("[templates] import: count instances failed: %v", err)
			writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: "import failed"})
			return
		}
		// ListAll, not GetBySlug: GetBySlug only returns active templates, and an
		// inactive template can still have instances.
		current, err := h.templateRepo.ListAll()
		if err != nil {
			log.Printf("[templates] import: list templates failed: %v", err)
			writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: "import failed"})
			return
		}
		bySlug := make(map[string]db.Template, len(current))
		for _, c := range current {
			bySlug[c.Slug] = c
		}
		for _, t := range rows {
			cur, ok := bySlug[t.Slug]
			if !ok || counts[t.Slug] == 0 {
				continue
			}
			if from, to := templateRunnerName(&cur), templateRunnerName(&t); from != to {
				writeJSON(w, http.StatusConflict, ErrorResponse{
					Error: fmt.Sprintf("template %s: cannot change runner %s -> %s while it has %d instance(s)", t.Slug, from, to, counts[t.Slug]),
				})
				return
			}
		}
	}
```

(`t` and `cur` are per-iteration copies, so taking their address is safe; `db` and `fmt` are already imported in `template_handlers.go`.)

- [ ] **Step 10: Run to verify pass**

Run: the gateway check. Expected: no new failure versus the baseline; `TestValidateNeo4jCredentials_OK` and `TestValidateNeo4jCredentials_Errors` (`./internal/validation/`), `TestCredentialsFromRequest_Neo4jFieldsSerialized`, `TestCredentialsFromRequest_Neo4jInvalid`, `TestCredentialsFromRequest_GoogleStillRequiresFile`, `TestValidateRunnerExtraEnv`, `TestHandleCreateInstance_Neo4jPrecheckFailure_Returns422AndRollsBack`, `TestHandleCreateInstance_Neo4jForbiddenExtraEnv_Returns400`, `TestHandleCreateInstance_Neo4jRequiresOwnToolPrefix`, `TestHandleImportTemplates_RunnerChangeWithInstances_Returns409`, `TestHandleRotateCredentials_Neo4jPrecheckFailure_KeepsOldCredentials` (`./internal/api/`) and `TestInstanceRepo_UpdateExtraEnv` (`./internal/repository/`) PASS.

- [ ] **Step 11: Commit**

```bash
cd apps-microservices/mcp-gateway-service
git add internal/validation/neo4j.go internal/validation/neo4j_test.go \
  internal/api/template_credentials.go internal/api/template_credentials_test.go \
  internal/api/template_routing_test.go internal/api/template_handlers.go \
  internal/api/google_handlers.go \
  internal/repository/template_repo.go internal/repository/template_repo_test.go
git commit -m "feat(mcp-gateway-service): accept Neo4j connection fields for template instances

Neo4j credentials are validated and encrypted like SA JSON; extra_env is
limited to NEO4J_READ_ONLY and a Neo4j instance needs its own tool
prefix; a Neo4j rotate is persisted only once the runner pre-check
accepted it; catalog import cannot move a template with instances to
another runner.

Identifiants Neo4j saisis dans le formulaire et chiffres ; extra_env
limite a NEO4J_READ_ONLY ; une rotation Neo4j n'est enregistree
qu'apres acceptation par le runner ; l'import ne peut pas changer le
runner d'un template qui a des instances."
cd -
```

---

### Task 8: Gateway — runner sync isolation

**Files:**
- Modify: `internal/api/internal_handlers.go` (`handleRunnerSync`)
- Test: `internal/api/runner_sync_test.go` (new)

**Interfaces:**
- Consumes: `runnerNameForToken`, `templateRunnerName`, the Task 6 test helpers.
- Produces: `POST /api/v1/internal/runner/sync` returns only the instances whose template's runner matches the caller's token; unknown/empty token → 401.

- [ ] **Step 1: Write the failing test** — `internal/api/runner_sync_test.go`:

```go
package api

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"mcp-gateway/internal/db"
	"mcp-gateway/internal/runnerclient"
)

func seedInstance(t *testing.T, h *Handler, id, slug string) {
	t.Helper()
	inst := &db.TemplateInstance{ID: id, TemplateSlug: slug, Name: id, CredentialsHash: "h-" + id, RunnerStatus: "running", MCPServerID: id}
	if err := h.instanceRepo.Create(inst, []byte(`{"id":"`+id+`"}`)); err != nil {
		t.Fatalf("seed %s: %v", id, err)
	}
}

func postRunnerSync(h *Handler, token string) *httptest.ResponseRecorder {
	req := httptest.NewRequest(http.MethodPost, "/api/v1/internal/runner/sync", nil)
	if token != "" {
		req.Header.Set("X-Admin-Token", token)
	}
	rec := httptest.NewRecorder()
	h.handleRunnerSync(rec, req)
	return rec
}

func TestHandleRunnerSync_FiltersByRunner(t *testing.T) {
	h, gdb := newTemplateAPITestHandler(t) // Google token: google-tok
	h.SetRunners(map[string]RunnerEndpoint{RunnerNeo4j: {Client: runnerclient.New("http://neo:8598", "neo-tok"), URL: "http://neo:8598", AdminToken: "neo-tok"}})
	seedTemplate(t, gdb, "ga", RunnerGoogle)
	seedTemplate(t, gdb, "neo4j", RunnerNeo4j)
	seedInstance(t, h, "ga-1", "ga")
	seedInstance(t, h, "neo-1", "neo4j")

	for token, wantID := range map[string]string{"google-tok": "ga-1", "neo-tok": "neo-1"} {
		rec := postRunnerSync(h, token)
		if rec.Code != http.StatusOK {
			t.Fatalf("%s: got %d body=%s", token, rec.Code, rec.Body.String())
		}
		var out struct {
			DesiredInstances []runnerclient.SpawnRequest `json:"desired_instances"`
		}
		if err := json.Unmarshal(rec.Body.Bytes(), &out); err != nil {
			t.Fatalf("decode: %v", err)
		}
		if len(out.DesiredInstances) != 1 || out.DesiredInstances[0].InstanceID != wantID {
			t.Fatalf("%s: got %+v, want only %s", token, out.DesiredInstances, wantID)
		}
		if out.DesiredInstances[0].CredentialsJSON != `{"id":"`+wantID+`"}` {
			t.Errorf("%s: credentials = %s", token, out.DesiredInstances[0].CredentialsJSON)
		}
	}
	for _, token := range []string{"", "wrong"} {
		if rec := postRunnerSync(h, token); rec.Code != http.StatusUnauthorized {
			t.Errorf("token %q: got %d, want 401", token, rec.Code)
		}
	}
}
```

- [ ] **Step 2: Run to verify failure**

Run: the gateway test command.
Expected: FAIL — `neo-tok` gets 401, and `google-tok` receives both instances.

- [ ] **Step 3: Implement** — in `handleRunnerSync` replace the token check

```go
	expected := h.config.GoogleTemplatesRunnerAdminToken
	got := r.Header.Get("X-Admin-Token")
	if expected == "" || subtle.ConstantTimeCompare([]byte(got), []byte(expected)) != 1 {
		http.Error(w, `{"error":"unauthorized"}`, http.StatusUnauthorized)
		return
	}
```

with

```go
	// Each runner authenticates with its own token, which also tells us which
	// runner is asking: it must only receive its own instances, or its
	// reconcile would spawn (and fail to run) the other runner's.
	runnerName, ok := h.runnerNameForToken(r.Header.Get("X-Admin-Token"))
	if !ok {
		http.Error(w, `{"error":"unauthorized"}`, http.StatusUnauthorized)
		return
	}
```

and, in the `for _, inst := range instances` loop, move the template lookup before the decryption and filter on the runner — the loop now starts:

```go
	for _, inst := range instances {
		tpl, err := h.templateRepo.GetBySlug(inst.TemplateSlug)
		if err != nil {
			log.Printf("[templates][WARN] runner/sync: template %s missing for instance %s", inst.TemplateSlug, inst.ID)
			continue
		}
		if templateRunnerName(tpl) != runnerName {
			continue
		}
		_, plain, err := h.instanceRepo.GetByIDWithCredentials(inst.ID)
		if err != nil {
			log.Printf("[templates][WARN] runner/sync: decrypt failed for %s: %v", inst.ID, err)
			continue
		}
```

(the rest of the loop body — `stdioArgs`, `extraEnv`, the `append` — is unchanged; delete the original `GetByIDWithCredentials` and `GetBySlug` blocks it replaces). Remove the `crypto/subtle` import from `internal_handlers.go` only if the compiler reports it unused (the user-sync handler may still use it).

- [ ] **Step 4: Run to verify pass** — the gateway check. Expected: no new failure versus the baseline; `TestHandleRunnerSync_FiltersByRunner` PASS.

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/mcp-gateway-service/internal/api/internal_handlers.go apps-microservices/mcp-gateway-service/internal/api/runner_sync_test.go
git commit -m "fix(mcp-gateway-service): give each template runner only its own instances

The runner sync endpoint identifies the caller by its admin token and
filters by templates.runner; credentials of other runners' instances are
no longer decrypted for it.

La synchro runner ne renvoie plus que les instances du runner appelant."
```

---

### Task 9: Frontend — Neo4j form and rotate dialog

**Files** (relative to `apps-microservices/mcp-gateway-frontend/`):
- Create: `src/components/templates/neo4jConnection.ts`
- Modify: `src/types/templates.ts`, `src/api/templates.ts`, `src/stores/templates.ts`
- Modify: `src/views/TemplateInstanceFormView.vue`
- Modify: `src/components/templates/RotateCredentialsModal.vue`, `src/views/TemplateDetailView.vue`
- Test: `src/components/templates/neo4jConnection.spec.ts`, `src/api/templates.neo4j.spec.ts`, `src/views/TemplateInstanceFormView.neo4j.spec.ts`

**Interfaces:**
- Consumes: the gateway contract from Tasks 4–7 (`runner` on templates; multipart `neo4j_uri`, `neo4j_username`, `neo4j_password`, `neo4j_database`; `extra_env` `{"NEO4J_READ_ONLY":"true"|"false"}`; rotate accepts the same fields).
- Produces: `Neo4jConnectionInput`, `isNeo4jTemplate`, `emptyNeo4jConnection`, `validateNeo4jConnection`, `appendNeo4jFields`, `readOnlyExtraEnv`, `isReadOnly`; `RotateNeo4jParams`; `templatesApi.rotate(id, File | RotateNeo4jParams)`; `store.rotateCredentials(id, File | RotateNeo4jParams)`.

- [ ] **Step 1: Write the failing tests**

`src/components/templates/neo4jConnection.spec.ts`:

```ts
import { describe, it, expect } from 'vitest'
import {
  appendNeo4jFields,
  emptyNeo4jConnection,
  isNeo4jTemplate,
  isReadOnly,
  readOnlyExtraEnv,
  validateNeo4jConnection
} from './neo4jConnection'

const ok = { uri: 'bolt://neo4j:7687', username: 'reader', password: 's3cret', database: 'neo4j' }

describe('neo4jConnection', () => {
  it('detects Neo4j templates by runner', () => {
    expect(isNeo4jTemplate({ runner: 'neo4j' })).toBe(true)
    expect(isNeo4jTemplate({ runner: 'google' })).toBe(false)
    expect(isNeo4jTemplate({})).toBe(false)
    expect(isNeo4jTemplate(null)).toBe(false)
  })

  it('starts empty with the default database', () => {
    expect(emptyNeo4jConnection()).toEqual({ uri: '', username: '', password: '', database: 'neo4j' })
  })

  it('accepts every supported scheme', () => {
    for (const uri of ['bolt://h:7687', 'bolt+s://h', 'bolt+ssc://h', 'neo4j://h', 'neo4j+s://h.example.com', 'neo4j+ssc://10.0.0.1:7687']) {
      expect(validateNeo4jConnection({ ...ok, uri })).toBeNull()
    }
  })

  it('rejects invalid input with a French message', () => {
    expect(validateNeo4jConnection({ ...ok, uri: '' })).toBe("L'URI est obligatoire")
    expect(validateNeo4jConnection({ ...ok, uri: 'http://h:7474' })).toMatch(/^Schéma attendu/)
    expect(validateNeo4jConnection({ ...ok, uri: 'bolt://neo4j:pw@h' })).toBe("Ne mettez pas d'identifiants dans l'URI")
    expect(validateNeo4jConnection({ ...ok, uri: 'pas une uri' })).toBe('URI invalide')
    expect(validateNeo4jConnection({ ...ok, username: ' ' })).toBe("L'utilisateur est obligatoire")
    expect(validateNeo4jConnection({ ...ok, password: '  ' })).toBe('Le mot de passe est obligatoire')
    expect(validateNeo4jConnection({ ...ok, database: 'a b' })).toMatch(/^Nom de base invalide/)
    expect(validateNeo4jConnection({ ...ok, database: '' })).toBeNull()
  })

  it('writes the multipart fields the gateway reads', () => {
    const fd = new FormData()
    appendNeo4jFields(fd, { uri: ' bolt://neo4j:7687 ', username: ' reader ', password: ' p w ', database: '' })
    expect(fd.get('neo4j_uri')).toBe('bolt://neo4j:7687')
    expect(fd.get('neo4j_username')).toBe('reader')
    expect(fd.get('neo4j_password')).toBe(' p w ')
    expect(fd.get('neo4j_database')).toBe('neo4j')
  })

  it('maps the read-only checkbox to extra_env and back', () => {
    expect(readOnlyExtraEnv(true)).toEqual({ NEO4J_READ_ONLY: 'true' })
    expect(readOnlyExtraEnv(false)).toEqual({ NEO4J_READ_ONLY: 'false' })
    expect(isReadOnly({ NEO4J_READ_ONLY: 'false' })).toBe(false)
    expect(isReadOnly({ NEO4J_READ_ONLY: 'true' })).toBe(true)
    expect(isReadOnly(undefined)).toBe(true) // template default is read-only
  })
})
```

`src/api/templates.neo4j.spec.ts`:

```ts
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('./client', () => ({
  api: { postMultipart: vi.fn().mockResolvedValue({}) }
}))

import { api } from './client'
import { templatesApi } from './templates'

const postMultipart = api.postMultipart as unknown as ReturnType<typeof vi.fn>
const conn = { uri: 'bolt://neo4j:7687', username: 'reader', password: 's3cret', database: 'graph' }

describe('templatesApi Neo4j payloads', () => {
  beforeEach(() => postMultipart.mockClear())

  it('createInstance sends neo4j fields and no credentials file', async () => {
    await templatesApi.createInstance({
      template_slug: 'neo4j',
      name: 'prod',
      extra_env: { NEO4J_READ_ONLY: 'true' },
      neo4j: conn
    })
    const [url, fd] = postMultipart.mock.calls[0] as [string, FormData]
    expect(url).toBe('/api/v1/template-instances')
    expect(fd.get('neo4j_uri')).toBe('bolt://neo4j:7687')
    expect(fd.get('neo4j_database')).toBe('graph')
    expect(fd.get('credentials')).toBeNull()
    expect(fd.get('extra_env')).toBe('{"NEO4J_READ_ONLY":"true"}')
  })

  it('rotate sends neo4j fields and extra_env', async () => {
    await templatesApi.rotate('inst-1', { neo4j: conn, extra_env: { NEO4J_READ_ONLY: 'false' } })
    const [url, fd] = postMultipart.mock.calls[0] as [string, FormData]
    expect(url).toBe('/api/v1/template-instances/inst-1/rotate-credentials')
    expect(fd.get('neo4j_password')).toBe('s3cret')
    expect(fd.get('extra_env')).toBe('{"NEO4J_READ_ONLY":"false"}')
    expect(fd.get('credentials')).toBeNull()
  })

  it('rotate with a File keeps the Google upload', async () => {
    const file = new File(['{}'], 'sa.json', { type: 'application/json' })
    await templatesApi.rotate('inst-2', file)
    const [, fd] = postMultipart.mock.calls[0] as [string, FormData]
    expect(fd.get('credentials')).toBeInstanceOf(File)
    expect(fd.get('neo4j_uri')).toBeNull()
  })
})
```

`src/views/TemplateInstanceFormView.neo4j.spec.ts` (mounts the real view; the `@/api/client` mock is required — without it `IconPicker` → `@/api/servers` → `client.ts` → `@/router` calls `createRouter` on the mocked `vue-router`; `jsdom` and `@vue/test-utils` are already devDependencies):

```ts
// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const getTemplate = vi.fn()
vi.mock('@/api/templates', () => ({ templatesApi: { get: (...a: unknown[]) => getTemplate(...a) } }))
vi.mock('@/stores/templates', () => ({ useTemplatesStore: () => ({ createInstance: vi.fn() }) }))
vi.mock('@/stores/servers', () => ({ useServersStore: () => ({ tags: [], fetchTags: vi.fn() }) }))
vi.mock('@/composables/useToast', () => ({ useToast: () => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }) }))
vi.mock('@/api/client', () => ({ api: {} }))
vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }) }))

import TemplateInstanceFormView from './TemplateInstanceFormView.vue'

const base = {
  slug: 'x', name: 'X', description: '', icon: '', stdio_command: 'cmd', stdio_args: [],
  required_extra_env: [{ key: 'NEO4J_READ_ONLY', label: 'Lecture seule', required: false }],
  tool_prefix: '', tags: [], kind: 'stdio', instance_count: 0
}

async function render(runner?: 'google' | 'neo4j') {
  getTemplate.mockResolvedValue({ ...base, runner })
  const w = mount(TemplateInstanceFormView, {
    props: { slug: 'x' },
    global: { stubs: { StepTabs: true, IconPicker: true, 'router-link': true } }
  })
  await flushPromises()
  return w
}

describe('TemplateInstanceFormView runner branching', () => {
  beforeEach(() => getTemplate.mockReset())

  it('Neo4j template shows the connection fields and read-only checkbox, not the file upload', async () => {
    const w = await render('neo4j')
    for (const id of ['neo4j-uri', 'neo4j-username', 'neo4j-password', 'neo4j-database']) {
      expect(w.find(`#${id}`).exists()).toBe(true)
    }
    expect(w.find('#neo4j-password').attributes('type')).toBe('password')
    expect((w.find('#neo4j-read-only').element as HTMLInputElement).checked).toBe(true)
    expect(w.find('#instance-credentials').exists()).toBe(false)
    expect(w.find('#env-NEO4J_READ_ONLY').exists()).toBe(false)
  })

  it('Google template is unchanged', async () => {
    const w = await render('google')
    expect(w.find('#instance-credentials').exists()).toBe(true)
    expect(w.find('#neo4j-uri').exists()).toBe(false)
  })
})
```

- [ ] **Step 2: Run to verify failure**

Run: `cd apps-microservices/mcp-gateway-frontend && npx vitest run src/components/templates/neo4jConnection.spec.ts src/api/templates.neo4j.spec.ts src/views/TemplateInstanceFormView.neo4j.spec.ts`
Expected: FAIL — `Failed to resolve import "./neo4jConnection"`; the api spec fails on `neo4j_uri` being `null`; the view spec fails on the `#neo4j-uri` assertions.

- [ ] **Step 3: `src/components/templates/neo4jConnection.ts`**

```ts
// Neo4j template helpers (runner = 'neo4j'). The gateway validates again
// (validation.ValidateNeo4jCredentials) and stays the source of truth; this
// only gives the admin immediate feedback.

export interface Neo4jConnectionInput {
  uri: string
  username: string
  password: string
  database: string
}

const SCHEMES = ['bolt:', 'bolt+s:', 'bolt+ssc:', 'neo4j:', 'neo4j+s:', 'neo4j+ssc:']
const DATABASE_RE = /^[A-Za-z0-9._-]{1,63}$/

export function isNeo4jTemplate(t: { runner?: string } | null | undefined): boolean {
  return t?.runner === 'neo4j'
}

export function emptyNeo4jConnection(): Neo4jConnectionInput {
  return { uri: '', username: '', password: '', database: 'neo4j' }
}

export function validateNeo4jConnection(c: Neo4jConnectionInput): string | null {
  const uri = c.uri.trim()
  if (!uri) return "L'URI est obligatoire"
  let parsed: URL
  try {
    parsed = new URL(uri)
  } catch {
    return 'URI invalide'
  }
  if (!SCHEMES.includes(parsed.protocol.toLowerCase())) {
    return 'Schéma attendu : bolt, bolt+s, bolt+ssc, neo4j, neo4j+s ou neo4j+ssc'
  }
  if (parsed.username || parsed.password) return "Ne mettez pas d'identifiants dans l'URI"
  if (!parsed.hostname) return "L'URI doit contenir un hôte"
  if (!c.username.trim()) return "L'utilisateur est obligatoire"
  if (!c.password.trim()) return 'Le mot de passe est obligatoire'
  const database = c.database.trim() || 'neo4j'
  if (!DATABASE_RE.test(database)) return 'Nom de base invalide (lettres, chiffres, . _ -)'
  return null
}

// Multipart field names read by the gateway's credentialsFromRequest.
// The password is sent as typed (never trimmed).
export function appendNeo4jFields(fd: FormData, c: Neo4jConnectionInput): void {
  fd.append('neo4j_uri', c.uri.trim())
  fd.append('neo4j_username', c.username.trim())
  fd.append('neo4j_password', c.password)
  fd.append('neo4j_database', c.database.trim() || 'neo4j')
}

export function readOnlyExtraEnv(readOnly: boolean): Record<string, string> {
  return { NEO4J_READ_ONLY: readOnly ? 'true' : 'false' }
}

// Missing value = template default, which is read-only.
export function isReadOnly(extraEnv: Record<string, string> | null | undefined): boolean {
  return extraEnv?.NEO4J_READ_ONLY !== 'false'
}
```

- [ ] **Step 4: Types, API, store**

`src/types/templates.ts`:
- add at the top: `import type { Neo4jConnectionInput } from '@/components/templates/neo4jConnection'`
- in `interface Template`, after `kind: 'stdio' | 'http_batch'` add:

```ts
  // Runner hosting the instances: 'google' (mcp-google-templates-runner) or
  // 'neo4j' (mcp-template-neo4j-service). Absent on older gateways = 'google'.
  runner?: 'google' | 'neo4j'
```

- in `interface CreateInstanceParams`, replace `credentials: File` with:

```ts
  // Google templates: service-account JSON file.
  credentials?: File
  // Neo4j templates: connection fields (sent instead of `credentials`).
  neo4j?: Neo4jConnectionInput
```

- add at the bottom:

```ts
export interface RotateNeo4jParams {
  neo4j: Neo4jConnectionInput
  extra_env?: Record<string, string>
}
```

`src/api/templates.ts`:
- add `RotateNeo4jParams` to the `import type { … } from '@/types/templates'` list and `import { appendNeo4jFields } from '@/components/templates/neo4jConnection'`
- in `createInstance`, replace `formData.append('credentials', params.credentials)` with:

```ts
    if (params.neo4j) {
      appendNeo4jFields(formData, params.neo4j)
    } else if (params.credentials) {
      formData.append('credentials', params.credentials)
    }
```

- in `importCatalog`, replace `} catch (e) {` with `} catch {` — the binding is unused and is the one (pre-existing) error the Step 8 eslint run would otherwise report.
- replace `rotate`:

```ts
  rotate(id: string, payload: File | RotateNeo4jParams): Promise<void> {
    const formData = new FormData()
    if (payload instanceof File) {
      formData.append('credentials', payload)
    } else {
      appendNeo4jFields(formData, payload.neo4j)
      if (payload.extra_env) {
        formData.append('extra_env', JSON.stringify(payload.extra_env))
      }
    }
    return api.postMultipart<void>(`${BASE}/template-instances/${id}/rotate-credentials`, formData)
  },
```

`src/stores/templates.ts` — change `async function rotateCredentials(id: string, credentials: File): Promise<void> { await templatesApi.rotate(id, credentials) }` to take `payload: File | RotateNeo4jParams` and pass it through; add `RotateNeo4jParams` to the store's `@/types/templates` type import.

- [ ] **Step 5: Run the unit tests** — `npx vitest run src/components/templates/neo4jConnection.spec.ts src/api/templates.neo4j.spec.ts`. Expected: PASS (the view spec still fails until Step 6).

- [ ] **Step 6: `TemplateInstanceFormView.vue`**

Script (`<script setup>`):
- add the imports:

```ts
import {
  emptyNeo4jConnection,
  isNeo4jTemplate,
  readOnlyExtraEnv,
  validateNeo4jConnection
} from '@/components/templates/neo4jConnection'
import type { Neo4jConnectionInput } from '@/components/templates/neo4jConnection'
```

- extend the `form` reactive type with `neo4j: Neo4jConnectionInput` and `read_only: boolean`, and its initial value with `neo4j: emptyNeo4jConnection(),` and `read_only: true,`.
- replace `const isStep1Valid = computed(() => toolPrefixValid.value)` with (the gateway enforces the same rule):

```ts
const neo4jPrefixError = computed(() => {
  if (!isNeo4j.value) return null
  const p = form.tool_prefix.trim()
  if (!p) return 'Préfixe obligatoire pour une instance Neo4j (ex. neo4jprod)'
  if (p.toLowerCase() === 'neo4j') return 'Préfixe déjà utilisé par le serveur Neo4j statique : choisissez-en un autre'
  return null
})

const isStep1Valid = computed(() => toolPrefixValid.value && !neo4jPrefixError.value)
```

  and in the template, right after `<p class="text-xs text-gray-400 dark:text-gray-500 mt-1">Alphanumérique uniquement</p>`, add `<p v-if="neo4jPrefixError" class="text-xs text-error-600 dark:text-error-400 mt-1">{{ neo4jPrefixError }}</p>`.
- after `const template = ref<Template | null>(null)` add (a `const` must be declared before any code that runs it; `computed` getters are lazy, so `neo4jPrefixError` may be declared above `isNeo4j`):

```ts
const isNeo4j = computed(() => isNeo4jTemplate(template.value))
const neo4jError = computed(() => (isNeo4j.value ? validateNeo4jConnection(form.neo4j) : null))
// Show the validation message only once the admin has started typing.
const neo4jTouched = computed(
  () => !!(form.neo4j.uri || form.neo4j.username || form.neo4j.password)
)
```

- in `isStep0Valid`, replace the two lines `if (!form.file) return false` / `if (fileError.value) return false` with:

```ts
  if (isNeo4j.value) {
    if (neo4jError.value) return false
  } else {
    if (!form.file) return false
    if (fileError.value) return false
  }
```

  and change `if (template.value?.required_extra_env) {` to `if (!isNeo4j.value && template.value?.required_extra_env) {`.
- in `handleSubmit`, replace `if (!form.file || !template.value) return` with:

```ts
  if (!template.value) return
  if (!isNeo4j.value && !form.file) return
```

  and replace the `await store.createInstance({ … })` call with:

```ts
    const extraEnv = isNeo4j.value ? readOnlyExtraEnv(form.read_only) : extraEnvCleaned
    await store.createInstance({
      template_slug: template.value.slug,
      name: form.name,
      extra_env: Object.keys(extraEnv).length ? extraEnv : undefined,
      credentials: isNeo4j.value ? undefined : form.file ?? undefined,
      neo4j: isNeo4j.value ? { ...form.neo4j } : undefined,
      tags: form.tags.length ? form.tags : undefined,
      icon: form.icon || undefined,
      tool_prefix: form.tool_prefix || undefined,
      auto_discover: form.auto_discover
    })
```

Template:
- step 0 "Required extra env" block: change its `v-if` to `v-if="!isNeo4j && template.required_extra_env && template.required_extra_env.length > 0"`.
- add `v-if="!isNeo4j"` to the `<div>` that wraps the "Service account JSON file" block, and insert right after that `</div>`:

```vue
            <!-- Neo4j connection (runner = neo4j) -->
            <div
              v-else
              class="space-y-3 border border-gray-200 dark:border-gray-800 rounded-md p-4"
            >
              <p class="text-xs font-semibold text-gray-700 dark:text-gray-300">
                Connexion Neo4j
              </p>
              <div>
                <label for="neo4j-uri" class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  URI <span class="text-red-500">*</span>
                </label>
                <input
                  id="neo4j-uri"
                  v-model="form.neo4j.uri"
                  type="text"
                  autocomplete="off"
                  placeholder="bolt://neo4j:7687"
                  class="h-11 w-full rounded-lg border border-gray-300 bg-transparent px-4 py-2.5 text-sm text-gray-800 shadow-theme-xs placeholder:text-gray-400 focus:border-brand-300 focus:outline-hidden focus:ring-3 focus:ring-brand-500/10 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90 dark:placeholder:text-white/30"
                />
              </div>
              <div>
                <label for="neo4j-username" class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Utilisateur <span class="text-red-500">*</span>
                </label>
                <input
                  id="neo4j-username"
                  v-model="form.neo4j.username"
                  type="text"
                  autocomplete="off"
                  class="h-11 w-full rounded-lg border border-gray-300 bg-transparent px-4 py-2.5 text-sm text-gray-800 shadow-theme-xs placeholder:text-gray-400 focus:border-brand-300 focus:outline-hidden focus:ring-3 focus:ring-brand-500/10 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90 dark:placeholder:text-white/30"
                />
              </div>
              <div>
                <label for="neo4j-password" class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Mot de passe <span class="text-red-500">*</span>
                </label>
                <input
                  id="neo4j-password"
                  v-model="form.neo4j.password"
                  type="password"
                  autocomplete="new-password"
                  class="h-11 w-full rounded-lg border border-gray-300 bg-transparent px-4 py-2.5 text-sm text-gray-800 shadow-theme-xs placeholder:text-gray-400 focus:border-brand-300 focus:outline-hidden focus:ring-3 focus:ring-brand-500/10 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90 dark:placeholder:text-white/30"
                />
              </div>
              <div>
                <label for="neo4j-database" class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Base de données
                </label>
                <input
                  id="neo4j-database"
                  v-model="form.neo4j.database"
                  type="text"
                  autocomplete="off"
                  placeholder="neo4j"
                  class="h-11 w-full rounded-lg border border-gray-300 bg-transparent px-4 py-2.5 text-sm text-gray-800 shadow-theme-xs placeholder:text-gray-400 focus:border-brand-300 focus:outline-hidden focus:ring-3 focus:ring-brand-500/10 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90 dark:placeholder:text-white/30"
                />
              </div>
              <label class="flex items-start gap-2 text-sm text-gray-700 dark:text-gray-300">
                <input id="neo4j-read-only" v-model="form.read_only" type="checkbox" class="mt-0.5" />
                <span>
                  Lecture seule
                  <span class="block text-xs text-gray-500 dark:text-gray-400">
                    Masque l'outil <code class="font-mono">write_neo4j_cypher</code> pour tous les utilisateurs de cette instance.
                  </span>
                </span>
              </label>
              <p
                v-if="neo4jTouched && neo4jError"
                class="text-xs text-error-600 dark:text-error-400 flex items-center gap-1"
              >
                <i class="pi pi-exclamation-triangle text-[11px]" />
                {{ neo4jError }}
              </p>
              <p class="text-[11px] text-gray-500 dark:text-gray-400">
                La connexion est vérifiée à la création. Le mot de passe est chiffré et ne sera plus affiché.
              </p>
            </div>
```

- step 2 (Vérification) "Extra env" `<div>`: prefix its `v-if` with `!isNeo4j && `, and insert right after it:

```vue
              <!-- Neo4j connection recap (password never shown) -->
              <div v-if="isNeo4j" class="py-2 grid grid-cols-3 gap-4">
                <dt class="text-sm font-medium text-gray-500 dark:text-gray-400">Connexion Neo4j</dt>
                <dd class="text-sm text-gray-900 dark:text-white col-span-2 font-mono text-xs space-y-0.5">
                  <div>{{ form.neo4j.uri }}</div>
                  <div>{{ form.neo4j.username }} @ {{ form.neo4j.database || 'neo4j' }}</div>
                  <div class="font-sans">{{ form.read_only ? 'Lecture seule' : 'Lecture et écriture' }}</div>
                </dd>
              </div>
```

- if a step-2 recap row displays the SA file (search the template for `form.file` or `fileInfo`), add `v-if="!isNeo4j"` to that row.

- [ ] **Step 7: Rotate dialog**

`src/views/TemplateDetailView.vue` — on `<RotateCredentialsModal …>` add `:runner="template?.runner"`; and on the `<router-link :to="{ name: 'template-instance-sheet-import', … }">` ("Import depuis Sheets", inside the `v-if="!isZohoTemplate"` block) add `v-if="template?.runner !== 'neo4j'"` — the gateway rejects sheet import for non-Google runners (Task 7 Step 8).

`src/components/templates/RotateCredentialsModal.vue`, script:
- add the import:

```ts
import {
  emptyNeo4jConnection,
  isReadOnly,
  readOnlyExtraEnv,
  validateNeo4jConnection
} from './neo4jConnection'
```

- `defineProps`: add `runner?: string`
- after `const submitting = ref(false)` add:

```ts
const isNeo4j = computed(() => props.runner === 'neo4j')
const neo4j = ref(emptyNeo4jConnection())
const readOnly = ref(true)
const neo4jError = computed(() => (isNeo4j.value ? validateNeo4jConnection(neo4j.value) : null))
```

- replace `canSubmit` with:

```ts
const canSubmit = computed(() => {
  if (submitting.value || !props.instance) return false
  if (isNeo4j.value) return !neo4jError.value
  return !!file.value && !fileError.value
})
```

- in `resetForm()` add `neo4j.value = emptyNeo4jConnection()` and `readOnly.value = isReadOnly(props.instance?.extra_env)`
- replace the `watch(() => props.open, …)` with a reset on every open/close (so `readOnly` is initialised from the instance when the dialog opens; the password is never pre-filled):

```ts
watch(
  () => props.open,
  () => resetForm()
)
```

- in `submit()`, replace `if (!file.value || !props.instance) return` and the `await store.rotateCredentials(props.instance.id, file.value)` line with:

```ts
  if (!props.instance) return
  if (!isNeo4j.value && !file.value) return
```

```ts
    if (isNeo4j.value) {
      await store.rotateCredentials(props.instance.id, {
        neo4j: { ...neo4j.value },
        extra_env: readOnlyExtraEnv(readOnly.value)
      })
    } else {
      await store.rotateCredentials(props.instance.id, file.value as File)
    }
```

Template:
- `DialogTitle`: replace `Renouveler la clé` with `{{ isNeo4j ? 'Modifier la connexion' : 'Renouveler la clé' }}`.
- `DialogDescription`: wrap the current text in `<template v-if="!isNeo4j">…</template>` and add `<template v-else>Saisissez les identifiants Neo4j (le mot de passe est obligatoire à chaque modification). La connexion est vérifiée avant de redémarrer l'instance ; en cas d'échec, l'instance continue avec les anciens identifiants.</template>`.
- add `v-if="!isNeo4j"` on the "Service account JSON file" `<div>` and insert right after it:

```vue
          <!-- Neo4j connection -->
          <div v-else class="space-y-3">
            <div>
              <label for="rotate-neo4j-uri" class="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
                URI <span class="text-error-500">*</span>
              </label>
              <input
                id="rotate-neo4j-uri"
                v-model="neo4j.uri"
                type="text"
                autocomplete="off"
                placeholder="bolt://neo4j:7687"
                class="h-10 w-full rounded-lg border border-gray-300 bg-transparent px-3 text-sm text-gray-800 dark:border-gray-700 dark:text-white/90"
              />
            </div>
            <div>
              <label for="rotate-neo4j-username" class="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
                Utilisateur <span class="text-error-500">*</span>
              </label>
              <input
                id="rotate-neo4j-username"
                v-model="neo4j.username"
                type="text"
                autocomplete="off"
                class="h-10 w-full rounded-lg border border-gray-300 bg-transparent px-3 text-sm text-gray-800 dark:border-gray-700 dark:text-white/90"
              />
            </div>
            <div>
              <label for="rotate-neo4j-password" class="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
                Mot de passe <span class="text-error-500">*</span>
              </label>
              <input
                id="rotate-neo4j-password"
                v-model="neo4j.password"
                type="password"
                autocomplete="new-password"
                class="h-10 w-full rounded-lg border border-gray-300 bg-transparent px-3 text-sm text-gray-800 dark:border-gray-700 dark:text-white/90"
              />
            </div>
            <div>
              <label for="rotate-neo4j-database" class="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
                Base de données
              </label>
              <input
                id="rotate-neo4j-database"
                v-model="neo4j.database"
                type="text"
                autocomplete="off"
                placeholder="neo4j"
                class="h-10 w-full rounded-lg border border-gray-300 bg-transparent px-3 text-sm text-gray-800 dark:border-gray-700 dark:text-white/90"
              />
            </div>
            <label class="flex items-start gap-2 text-sm text-gray-700 dark:text-gray-300">
              <input id="rotate-neo4j-read-only" v-model="readOnly" type="checkbox" class="mt-0.5" />
              <span>
                Lecture seule
                <span class="block text-xs text-gray-500 dark:text-gray-400">
                  Masque l'outil <code class="font-mono">write_neo4j_cypher</code> pour tous les utilisateurs de cette instance.
                </span>
              </span>
            </label>
            <p
              v-if="neo4jError && (neo4j.uri || neo4j.username || neo4j.password)"
              class="text-xs text-error-600 dark:text-error-400"
            >
              {{ neo4jError }}
            </p>
          </div>
```

- submit button label: `{{ submitting ? 'Rotation…' : (isNeo4j ? 'Enregistrer' : 'Renouveler') }}`.

- [ ] **Step 8: Type-check, lint, tests**

Run:

```bash
cd apps-microservices/mcp-gateway-frontend
npx vue-tsc -b
npx eslint src/components/templates src/api/templates.ts src/stores/templates.ts src/types/templates.ts src/views/TemplateInstanceFormView.vue src/views/TemplateDetailView.vue --ext .ts,.vue
npx vitest run src/components/templates/neo4jConnection.spec.ts src/api/templates.neo4j.spec.ts src/views/TemplateInstanceFormView.neo4j.spec.ts
```

Expected: no type errors, no lint errors (after the `catch {` fix in Step 4), all 3 spec files PASS. The pre-existing `vue/attributes-order` warning in `TemplateInstanceFormView.vue` is a warning, not an error.

- [ ] **Step 9: Commit**

```bash
git add apps-microservices/mcp-gateway-frontend/src/components/templates/neo4jConnection.ts \
  apps-microservices/mcp-gateway-frontend/src/components/templates/neo4jConnection.spec.ts \
  apps-microservices/mcp-gateway-frontend/src/api/templates.neo4j.spec.ts \
  apps-microservices/mcp-gateway-frontend/src/views/TemplateInstanceFormView.neo4j.spec.ts \
  apps-microservices/mcp-gateway-frontend/src/types/templates.ts \
  apps-microservices/mcp-gateway-frontend/src/api/templates.ts \
  apps-microservices/mcp-gateway-frontend/src/stores/templates.ts \
  apps-microservices/mcp-gateway-frontend/src/views/TemplateInstanceFormView.vue \
  apps-microservices/mcp-gateway-frontend/src/views/TemplateDetailView.vue \
  apps-microservices/mcp-gateway-frontend/src/components/templates/RotateCredentialsModal.vue
git commit -m "feat(mcp-gateway-frontend): Neo4j connection form for template instances

Neo4j templates (runner=neo4j) show URI/user/password/database and a
read-only checkbox instead of the SA JSON upload, in both the create
form and the rotate dialog.

Formulaire de connexion Neo4j (URI, utilisateur, mot de passe, base,
lecture seule) a la place du fichier JSON, en creation et en rotation."
```

---

### Task 10: Compose, docs, end-to-end check

**Files:**
- Modify: `docker-compose.yml` (after the `mcp-google-templates-runner` service; `mcp-gateway-service` `environment`)
- Modify: `apps-microservices/mcp-gateway-service/CLAUDE.md`
- Modify: `apps-microservices/mcp-gateway-frontend/CLAUDE.md`
- Modify: `CLAUDE.md` (root Service Map)

- [ ] **Step 1: Compose service** — insert after the `mcp-google-templates-runner` block (before the next service):

```yaml
  mcp-template-neo4j-service:
    build:
      context: .
      dockerfile: ./apps-microservices/mcp-template-neo4j-service/Dockerfile
    container_name: mcp-template-neo4j-service
    profiles: [ "mcp" ]
    restart: unless-stopped
    expose:
      - "8598"
      - "15100-15199"
    environment:
      - MCP_GATEWAY_URL=http://mcp-gateway-service:8592
      - MCP_GATEWAY_ADMIN_TOKEN=${NEO4J_TEMPLATES_RUNNER_ADMIN_TOKEN}
      - RUNNER_ADMIN_TOKEN=${NEO4J_TEMPLATES_RUNNER_ADMIN_TOKEN}
      - RUNNER_PORT=8598
      - RUNNER_INSTANCE_PORT_START=15100
      - RUNNER_INSTANCE_PORT_END=15199
    healthcheck:
      test: [ "CMD", "curl", "-f", "http://localhost:8598/admin/health" ]
      interval: 30s
      timeout: 5s
      retries: 3
    depends_on:
      - mcp-gateway-service
    networks:
      - services-net
    logging: *logging_defaults
```

and in the `mcp-gateway-service` `environment:` list, right after `- GOOGLE_TEMPLATES_RUNNER_ADMIN_TOKEN=${GOOGLE_TEMPLATES_RUNNER_ADMIN_TOKEN}`:

```yaml
      # Neo4j template runner (token must differ from the Google runner's)
      - NEO4J_TEMPLATES_RUNNER_URL=http://mcp-template-neo4j-service:8598
      - NEO4J_TEMPLATES_RUNNER_ADMIN_TOKEN=${NEO4J_TEMPLATES_RUNNER_ADMIN_TOKEN}
```

Run: `docker compose --profile mcp config --quiet && echo COMPOSE_OK`
Expected: `COMPOSE_OK` (a warning that `NEO4J_TEMPLATES_RUNNER_ADMIN_TOKEN` is unset is fine locally).

- [ ] **Step 2: Gateway CLAUDE.md**

- Template Catalog: `(seeded: GA4, GSC)` → `(seeded: GA4, GSC, Neo4j)`; `POST is multipart: template_slug, name, extra_env JSON, credentials file` → `POST is multipart: template_slug, name, extra_env JSON, plus a credentials file (Google runner) or neo4j_uri / neo4j_username / neo4j_password / neo4j_database fields (Neo4j runner)`; the rotate line → `POST /template-instances/{id}/rotate-credentials — replacement credentials (SA JSON, or Neo4j fields + optional extra_env) + respawn; a Neo4j rotate is persisted only after the runner pre-check accepted it (422 otherwise, DB and running instance untouched)`.
- Internal Sync: `runner's boot-time pull of desired instances (returns decrypted credentials)` → `a runner's pull of its desired instances — the X-Admin-Token identifies the runner (Google or Neo4j) and only that runner's instances are returned (decrypted credentials)`.
- Environment table: the `GOOGLE_TEMPLATES_RUNNER_URL` description "Required to spawn template instances." → "Required to spawn Google-runner template instances (ga, gsc)."; then, after the two `GOOGLE_TEMPLATES_RUNNER_*` rows:

```markdown
| `NEO4J_TEMPLATES_RUNNER_URL` | — | In-cluster URL of mcp-template-neo4j-service (e.g. `http://mcp-template-neo4j-service:8598`). Required to spawn Neo4j template instances. |
| `NEO4J_TEMPLATES_RUNNER_ADMIN_TOKEN` | — | Shared secret for the Neo4j runner (both directions). **Must differ** from `GOOGLE_TEMPLATES_RUNNER_ADMIN_TOKEN` — the sync endpoint uses it to tell the runners apart; equal tokens disable the Neo4j runner at boot. |
```

- Database table: `templates` row → `Template catalog (seed: ga GA4, gsc GSC, neo4j Neo4j) — stdio_command, default_env with {instance_id} placeholder, required_extra_env schema, and runner (google | neo4j)`; `template_instances` row → `One row per template instance — encrypted credentials (SA JSON or Neo4j connection JSON), credentials_hash, runner_port/status, FK to mcp_servers.id`.

- [ ] **Step 3: Root CLAUDE.md + frontend CLAUDE.md** — in the root `CLAUDE.md` Service Map, replace the row `| MCP Template Runner | \`mcp-google-templates-runner\` | Python / FastAPI / asyncio | Local OK |` with `| MCP Template Runners | \`mcp-google-templates-runner\`, \`mcp-template-neo4j-service\` | Python / FastAPI / asyncio | Local OK |`. In the frontend `CLAUDE.md`, in the `views/` part of the File Inventory, add:

```
    TemplateInstanceFormView.vue  # template instance wizard; Neo4j templates (runner=neo4j) get connection fields + "Lecture seule" instead of the SA JSON upload
```

and under `components/`: `templates/neo4jConnection.ts  # Neo4j field validation + FormData helpers (mirrors the gateway's ValidateNeo4jCredentials)`.

- [ ] **Step 4: Spec** — nothing to edit: the design doc was updated together with this plan (pre-check codes, empty seed prefix, rotate ordering, stdio_args guard, runner-change guard). Only check it still matches what was built.

- [ ] **Step 5: Full test sweep**

Run the runner test command, the gateway check and the frontend spec files from Global Constraints.
Expected: runner and frontend all PASS; gateway: no new failure versus the baseline.

- [ ] **Step 6: Commit**

```bash
git add docker-compose.yml CLAUDE.md apps-microservices/mcp-gateway-service/CLAUDE.md \
  apps-microservices/mcp-gateway-frontend/CLAUDE.md
git commit -m "chore(mcp-template-neo4j-service): wire the runner in compose and document it

New service in the mcp profile (8598, pool 15100-15199) and gateway
docs updated for the Neo4j runner.

Nouveau service dans le profil mcp (8598, pool 15100-15199) et
documentation du gateway mise a jour."
```

- [ ] **Step 7: Deployment + manual verification (remote server — not runnable locally)**

1. Add `NEO4J_TEMPLATES_RUNNER_ADMIN_TOKEN=<random, different from the Google one>` to the server `.env`.
2. `docker compose --profile mcp up -d --build mcp-gateway-service mcp-template-neo4j-service mcp-gateway-frontend` (the gateway's AutoMigrate adds `templates.runner`).
3. Re-apply the seed so the `neo4j` row exists: `docker compose exec mysql mysql -u root -p<pw> gateway_db < apps-microservices/mcp-gateway-service/init-db/init-mcp-gateway-db.sql`.
4. The gateway log shows `[main] neo4j-templates runner: http://mcp-template-neo4j-service:8598`; the runner log shows `reconcile: 0 desired`.
5. Admin UI → Templates → Neo4j: create instance `prod` with **tool prefix `neo4jprod`** (read-only checked) and instance `staging` with **tool prefix `neo4jstaging`** (unchecked), on the same database. The prefix `neo4j` (static server) and an empty prefix must be refused. A wrong password must fail with `neo4j_auth_failed: …` and create nothing.
6. Through the gateway `tools/list`: `neo4jprod_*` exposes only `read_neo4j_cypher` and `get_neo4j_schema`; `neo4jstaging_*` also exposes `write_neo4j_cypher`.
7. `MATCH (p:Produit) RETURN count(p) AS n` through `neo4jprod_read_neo4j_cypher` returns the same count as the static `neo4j_read_neo4j_cypher` (34 089 on 2026-09-29).
8. Rotate `neo4jprod` with a wrong password → 422, and the instance still answers step 7.
9. Restart the runner container → both instances come back on the same ports (runner log `reconcile: 2 desired, 2 spawned`), and the GA/GSC instances are untouched.
10. Graph: run `python scripts/graphify_plan_update.py` and follow `/graphify-refresh` only for the areas it reports (never a bare `--update`, per the root CLAUDE.md).
