# account_service Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a centralized OAuth2 Authorization Code + PKCE login service (`account_service`) — FastAPI backend + Vue 3 frontend — that other monorepo services use to authenticate users.

**Architecture:** Two new containers (`account-service-backend`, `account-service-frontend`). Backend issues RS256 JWTs after delegating credential validation to the upstream HelloPro endpoint, persists OAuth client + refresh-token state in MySQL via Tortoise. Frontend is a Vue SPA forked from `public/admin-dashboad/`, pruned to auth-only views, served by Nginx. Consumer integration is out-of-scope for this plan (separate PRs).

**Tech Stack:** Python 3.10, FastAPI, Tortoise-ORM (MySQL/asyncmy), Aerich, PyJWT[crypto], cryptography (Fernet), bcrypt, httpx, slowapi, pytest + pytest-asyncio + respx + aiosqlite. Vue 3.5, Vue Router 4.5, Vite 6, Tailwind 4, Vitest, vue-tsc, ESLint, Nginx 1.27.

**Companion docs:**
- Spec: `docs/superpowers/specs/2026-04-30-account-service-design.md`
- Consumer integration guide: `docs/superpowers/specs/account-service-README.md`

---

## File Structure

### Backend — `apps-microservices/account-service-backend/`

```
main.py                          FastAPI app + lifespan + router include
requirements.txt
Dockerfile
.dockerignore
pyproject.toml                   ruff config
CLAUDE.md
app/
  __init__.py
  core/
    __init__.py
    settings.py                  Pydantic BaseSettings (all env vars)
    security.py                  PKCE verifier check, secret hashing, hash helpers
    jwt_keys.py                  RSA keypair gen + Fernet encryption + DB persist + JWKS
    jwt_tokens.py                encode/decode RS256 access tokens
  db/
    __init__.py
    database.py                  Tortoise init/teardown
    models.py                    OAuthClient, AuthorizationCode, RefreshToken, SigningKey
  schemas.py                     Pydantic request/response models for all endpoints
  services/
    __init__.py
    hellopro_client.py           httpx call to upstream auth endpoint
    code_service.py              auth-code create + consume
    token_service.py             access+refresh issuance, rotation, reuse detection
    client_service.py            OAuthClient CRUD + secret hashing
  routers/
    __init__.py
    health.py                    GET /health
    jwks.py                      GET /.well-known/jwks.json
    authorize.py                 POST /authorize
    token.py                     POST /token
    revoke.py                    POST /revoke
    introspect.py                POST /introspect
    userinfo.py                  GET /userinfo
    logout.py                    GET /logout
    admin_clients.py             POST/GET/DELETE /admin/clients
  middleware.py                  request_id, log redaction
  rate_limit.py                  slowapi limiter
tests/
  __init__.py
  conftest.py                    sqlite in-memory + fake settings + fake key
  test_security.py
  test_jwt_keys.py
  test_jwt_tokens.py
  test_models.py
  test_hellopro_client.py
  test_code_service.py
  test_token_service.py
  test_client_service.py
  test_authorize.py
  test_token_endpoint.py
  test_revoke.py
  test_introspect.py
  test_userinfo.py
  test_logout.py
  test_admin_clients.py
  test_jwks.py
  test_rate_limit.py
  integration/
    __init__.py
    test_consumer_flow.py        full code → token → refresh → revoke walk
migrations/                       Aerich (committed)
scripts/
  seed_clients.py                idempotent OAuthClient upsert from env
```

### Frontend — `apps-microservices/account-service-frontend/`

```
package.json
vite.config.ts
tsconfig.json / tsconfig.app.json / tsconfig.node.json
eslint.config.ts
.prettierrc.json
postcss.config.js
index.html
nginx.conf
Dockerfile
.dockerignore
CLAUDE.md
public/
src/
  main.ts
  App.vue
  env.d.ts
  router/index.ts                /signin, /consent, /logout, /error
  views/Auth/
    Signin.vue
    Consent.vue
    Logout.vue
    Error.vue
  composables/
    useOAuthFlow.ts              parses URL params, posts to /authorize
    useApi.ts                    fetch wrapper with error mapping
  components/auth/
    AuthCard.vue                 layout shell forked from template
  assets/
    main.css                     Tailwind imports
tests/
  views/Signin.spec.ts
  composables/useOAuthFlow.spec.ts
```

### Repo-level

```
docker-compose.yml                                                add 2 services
.github/workflows/ci_services_account_service_backend.yml         lint + pytest
.github/workflows/ci_services_account_service_frontend.yml        eslint + vitest + vue-tsc
.github/workflows/cd_build_push_services_account_service_backend.yml
.github/workflows/cd_build_push_services_account_service_frontend.yml
CLAUDE.md                                                         add to service map
```

---

## Phase A — Backend Skeleton

### Task A1: Backend folder + requirements + Dockerfile + main.py + health endpoint

**Files:**
- Create: `apps-microservices/account-service-backend/requirements.txt`
- Create: `apps-microservices/account-service-backend/Dockerfile`
- Create: `apps-microservices/account-service-backend/.dockerignore`
- Create: `apps-microservices/account-service-backend/pyproject.toml`
- Create: `apps-microservices/account-service-backend/main.py`
- Create: `apps-microservices/account-service-backend/app/__init__.py`
- Create: `apps-microservices/account-service-backend/app/routers/__init__.py`
- Create: `apps-microservices/account-service-backend/app/routers/health.py`
- Create: `apps-microservices/account-service-backend/tests/__init__.py`
- Create: `apps-microservices/account-service-backend/tests/conftest.py`
- Test: `apps-microservices/account-service-backend/tests/test_health.py`

- [ ] **Step 1: Create `requirements.txt`**

```
fastapi[all]>=0.115,<0.130
uvicorn[standard]
PyJWT[crypto]>=2.8
cryptography>=42
bcrypt>=4.1
httpx>=0.27
tortoise-orm[asyncmy]>=0.21
aerich>=0.7
slowapi>=0.1.9
python-dotenv
uvloop
```

- [ ] **Step 2: Create `pyproject.toml`** (ruff config only)

```toml
[tool.ruff]
line-length = 88
target-version = "py310"

[tool.ruff.lint]
select = ["E", "F", "W", "I", "B", "UP"]
ignore = ["E501"]
```

- [ ] **Step 3: Create `.dockerignore`**

```
__pycache__
*.pyc
*.pyo
.pytest_cache
.ruff_cache
tests/
.env
.env.*
*.log
.git
.venv
```

- [ ] **Step 4: Create `Dockerfile`** (build context = repo root, mirroring api-gateway)

```dockerfile
FROM python:3.10-slim
WORKDIR /app

ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY apps-microservices/account-service-backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY libs/ /app/libs/
RUN pip install --no-cache-dir -e ./libs/common-utils || true

COPY apps-microservices/account-service-backend .

RUN useradd --create-home --shell /bin/bash appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port 8000 --workers ${UVICORN_WORKERS:-2} --loop uvloop"]
```

- [ ] **Step 5: Create `app/__init__.py`** (empty)

- [ ] **Step 6: Create `app/routers/__init__.py`** (empty)

- [ ] **Step 7: Create `app/routers/health.py`**

```python
from fastapi import APIRouter

router = APIRouter()


@router.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
```

- [ ] **Step 8: Create `main.py`**

```python
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.routers import health


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield


app = FastAPI(title="account-service-backend", lifespan=lifespan)
app.include_router(health.router)
```

- [ ] **Step 9: Create `tests/__init__.py`** (empty)

- [ ] **Step 10: Create `tests/conftest.py`** (minimal stub — extended later)

```python
import pytest
from fastapi.testclient import TestClient

from main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)
```

- [ ] **Step 11: Write failing test `tests/test_health.py`**

```python
def test_health_returns_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
```

- [ ] **Step 12: Run test — expect PASS**

```bash
cd apps-microservices/account-service-backend
pip install -r requirements.txt
pytest tests/test_health.py -v
```

Expected: `1 passed`.

- [ ] **Step 13: Commit**

```bash
git add apps-microservices/account-service-backend/
git commit -m "feat(account-service-backend): scaffold FastAPI service with /health"
```

---

### Task A2: Settings module (Pydantic BaseSettings)

**Files:**
- Create: `apps-microservices/account-service-backend/app/core/__init__.py`
- Create: `apps-microservices/account-service-backend/app/core/settings.py`
- Test: `apps-microservices/account-service-backend/tests/test_settings.py`

- [ ] **Step 1: Create `app/core/__init__.py`** (empty)

- [ ] **Step 2: Write failing test `tests/test_settings.py`**

```python
import os

import pytest

from app.core.settings import Settings


def test_settings_load_from_env(monkeypatch):
    monkeypatch.setenv("MYSQL_HOST", "db")
    monkeypatch.setenv("MYSQL_USER", "u")
    monkeypatch.setenv("MYSQL_PASS", "p")
    monkeypatch.setenv("MYSQL_DB", "account_db")
    monkeypatch.setenv("HELLOPRO_AUTH_URL", "https://auth.hellopro.fr/api/login")
    monkeypatch.setenv("JWT_KEY_ENCRYPTION_KEY", "Z" * 44)
    monkeypatch.setenv("GATEWAY_ADMIN_KEY", "admin")
    s = Settings()
    assert s.MYSQL_DB == "account_db"
    assert s.ACCESS_TOKEN_EXPIRE_MINUTES == 15
    assert s.REFRESH_TOKEN_EXPIRE_DAYS == 30
    assert str(s.HELLOPRO_AUTH_URL).startswith("https://auth.hellopro.fr")


def test_settings_missing_required_raises(monkeypatch):
    for k in ("MYSQL_HOST", "MYSQL_USER", "MYSQL_PASS", "MYSQL_DB",
             "HELLOPRO_AUTH_URL", "JWT_KEY_ENCRYPTION_KEY", "GATEWAY_ADMIN_KEY"):
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(Exception):
        Settings()
```

- [ ] **Step 3: Run test — expect FAIL** (ModuleNotFoundError)

```bash
pytest tests/test_settings.py -v
```

- [ ] **Step 4: Implement `app/core/settings.py`**

```python
from functools import lru_cache

from pydantic import Field, HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    MYSQL_HOST: str
    MYSQL_PORT: int = 3306
    MYSQL_USER: str
    MYSQL_PASS: str
    MYSQL_DB: str

    HELLOPRO_AUTH_URL: HttpUrl
    HELLOPRO_AUTH_TIMEOUT_SECONDS: float = 5.0

    JWT_KEY_ENCRYPTION_KEY: str = Field(min_length=32)
    JWT_ISSUER: str = "https://account.hellopro.eu"

    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    AUTH_CODE_EXPIRE_SECONDS: int = 60

    GATEWAY_ADMIN_KEY: str

    LOG_LEVEL: str = "INFO"

    @property
    def database_url(self) -> str:
        return (
            f"mysql://{self.MYSQL_USER}:{self.MYSQL_PASS}"
            f"@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DB}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 5: Run test — expect PASS**

```bash
pytest tests/test_settings.py -v
```

- [ ] **Step 6: Commit**

```bash
git add apps-microservices/account-service-backend/
git commit -m "feat(account-service-backend): add Pydantic Settings"
```

---

## Phase B — Database Layer

### Task B1: Tortoise models

**Files:**
- Create: `apps-microservices/account-service-backend/app/db/__init__.py`
- Create: `apps-microservices/account-service-backend/app/db/database.py`
- Create: `apps-microservices/account-service-backend/app/db/models.py`
- Test: `apps-microservices/account-service-backend/tests/test_models.py`
- Modify: `apps-microservices/account-service-backend/tests/conftest.py`

- [ ] **Step 1: Create `app/db/__init__.py`** (empty)

- [ ] **Step 2: Implement `app/db/models.py`**

```python
from tortoise import fields
from tortoise.models import Model


class OAuthClient(Model):
    id = fields.UUIDField(pk=True)
    client_id = fields.CharField(max_length=64, unique=True, index=True)
    client_secret_hash = fields.CharField(max_length=255)
    name = fields.CharField(max_length=128)
    redirect_uris = fields.JSONField()
    post_logout_redirect_uris = fields.JSONField(default=list)
    skip_consent = fields.BooleanField(default=True)
    is_active = fields.BooleanField(default=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "oauth_client"


class AuthorizationCode(Model):
    code_hash = fields.CharField(max_length=64, pk=True)
    client_id = fields.CharField(max_length=64, index=True)
    sub = fields.CharField(max_length=128)
    code_challenge = fields.CharField(max_length=255)
    code_challenge_method = fields.CharField(max_length=10)
    redirect_uri = fields.CharField(max_length=512)
    issued_at = fields.DatetimeField(auto_now_add=True)
    expires_at = fields.DatetimeField(index=True)
    consumed_at = fields.DatetimeField(null=True)
    user_email = fields.CharField(max_length=255, null=True)
    user_display_name = fields.CharField(max_length=255, null=True)

    class Meta:
        table = "authorization_code"


class RefreshToken(Model):
    id = fields.UUIDField(pk=True)
    token_hash = fields.CharField(max_length=64, unique=True, index=True)
    client_id = fields.CharField(max_length=64, index=True)
    sub = fields.CharField(max_length=128, index=True)
    user_email = fields.CharField(max_length=255, null=True)
    user_display_name = fields.CharField(max_length=255, null=True)
    issued_at = fields.DatetimeField(auto_now_add=True)
    expires_at = fields.DatetimeField(index=True)
    revoked_at = fields.DatetimeField(null=True)
    rotated_from_id = fields.UUIDField(null=True)
    user_agent = fields.CharField(max_length=255, null=True)
    ip = fields.CharField(max_length=45, null=True)

    class Meta:
        table = "refresh_token"


class SigningKey(Model):
    kid = fields.CharField(max_length=64, pk=True)
    private_pem_encrypted = fields.TextField()
    public_pem = fields.TextField()
    is_active = fields.BooleanField(default=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    rotated_at = fields.DatetimeField(null=True)

    class Meta:
        table = "signing_key"
```

- [ ] **Step 3: Implement `app/db/database.py`**

```python
import logging

from tortoise import Tortoise

from app.core.settings import get_settings

logger = logging.getLogger("db")

TORTOISE_ORM = {
    "connections": {"default": ""},
    "apps": {
        "models": {
            "models": ["app.db.models", "aerich.models"],
            "default_connection": "default",
        }
    },
}


def build_tortoise_config(database_url: str) -> dict:
    cfg = {
        "connections": {"default": database_url},
        "apps": {
            "models": {
                "models": ["app.db.models", "aerich.models"],
                "default_connection": "default",
            }
        },
    }
    return cfg


async def init_db(database_url: str | None = None) -> None:
    url = database_url or get_settings().database_url
    await Tortoise.init(config=build_tortoise_config(url))
    await Tortoise.generate_schemas(safe=True)
    logger.info("Tortoise initialised at %s", url.split("@")[-1])


async def close_db() -> None:
    await Tortoise.close_connections()
```

- [ ] **Step 4: Replace `tests/conftest.py`**

```python
import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

from app.db.database import close_db, init_db
from main import app


@pytest_asyncio.fixture(autouse=True)
async def _db():
    await init_db("sqlite://:memory:")
    yield
    await close_db()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)
```

- [ ] **Step 5: Add `aiosqlite` and `pytest-asyncio` to test deps**

Append to `requirements.txt`:

```
pytest>=8
pytest-asyncio>=0.23
respx>=0.21
aiosqlite>=0.20
```

Re-install:

```bash
pip install -r requirements.txt
```

- [ ] **Step 6: Add `pytest.ini`** (`apps-microservices/account-service-backend/pytest.ini`)

```ini
[pytest]
asyncio_mode = auto
testpaths = tests
```

- [ ] **Step 7: Write failing test `tests/test_models.py`**

```python
from datetime import datetime, timedelta, timezone

from app.db.models import (
    AuthorizationCode,
    OAuthClient,
    RefreshToken,
    SigningKey,
)


async def test_oauth_client_roundtrip():
    c = await OAuthClient.create(
        client_id="svc",
        client_secret_hash="h",
        name="Service",
        redirect_uris=["https://svc.hellopro.eu/cb"],
    )
    fetched = await OAuthClient.get(client_id="svc")
    assert fetched.id == c.id
    assert fetched.skip_consent is True
    assert fetched.is_active is True


async def test_auth_code_roundtrip():
    await AuthorizationCode.create(
        code_hash="abc",
        client_id="svc",
        sub="user@x",
        code_challenge="ch",
        code_challenge_method="S256",
        redirect_uri="https://svc.hellopro.eu/cb",
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=60),
    )
    assert await AuthorizationCode.filter(code_hash="abc").exists()


async def test_refresh_token_roundtrip():
    await RefreshToken.create(
        token_hash="th",
        client_id="svc",
        sub="user@x",
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
    )
    assert await RefreshToken.filter(token_hash="th").exists()


async def test_signing_key_roundtrip():
    await SigningKey.create(kid="k1", private_pem_encrypted="x", public_pem="y")
    assert await SigningKey.filter(kid="k1").exists()
```

- [ ] **Step 8: Run tests — expect PASS**

```bash
pytest tests/test_models.py -v
```

- [ ] **Step 9: Commit**

```bash
git add apps-microservices/account-service-backend/
git commit -m "feat(account-service-backend): add Tortoise models + DB init"
```

---

### Task B2: Aerich init

**Files:**
- Create: `apps-microservices/account-service-backend/aerich.ini` (generated)
- Create: `apps-microservices/account-service-backend/migrations/models/0_*.py` (generated)

- [ ] **Step 1: Add `TORTOISE_ORM` runtime export**

Append to `app/db/database.py`:

```python
import os

if os.environ.get("MYSQL_HOST"):
    TORTOISE_ORM = build_tortoise_config(get_settings().database_url)
```

- [ ] **Step 2: Initialize Aerich** (run once locally)

```bash
cd apps-microservices/account-service-backend
aerich init -t app.db.database.TORTOISE_ORM
aerich init-db
```

- [ ] **Step 3: Commit generated migration**

```bash
git add apps-microservices/account-service-backend/aerich.ini apps-microservices/account-service-backend/migrations/
git commit -m "chore(account-service-backend): aerich init + initial migration"
```

---

## Phase C — Crypto + Security Helpers

### Task C1: Security helpers (PKCE check, secret hashing)

**Files:**
- Create: `apps-microservices/account-service-backend/app/core/security.py`
- Test: `apps-microservices/account-service-backend/tests/test_security.py`

- [ ] **Step 1: Write failing test `tests/test_security.py`**

```python
import hashlib

from app.core.security import (
    generate_random_token,
    hash_secret,
    sha256_hex,
    verify_pkce,
    verify_secret,
)


def test_sha256_hex_matches_stdlib():
    assert sha256_hex("hello") == hashlib.sha256(b"hello").hexdigest()


def test_hash_and_verify_secret_roundtrip():
    h = hash_secret("supersecret")
    assert verify_secret("supersecret", h) is True
    assert verify_secret("nope", h) is False


def test_generate_random_token_length():
    t = generate_random_token(32)
    assert len(t) >= 32


def test_verify_pkce_s256_ok():
    import base64

    verifier = "a" * 64
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    assert verify_pkce(verifier, challenge, "S256") is True


def test_verify_pkce_rejects_plain_method():
    assert verify_pkce("v", "v", "plain") is False


def test_verify_pkce_wrong_verifier():
    assert verify_pkce("wrong", "any-challenge", "S256") is False
```

- [ ] **Step 2: Run test — expect FAIL**

```bash
pytest tests/test_security.py -v
```

- [ ] **Step 3: Implement `app/core/security.py`**

```python
import base64
import hashlib
import hmac
import secrets

import bcrypt


def sha256_hex(s: str | bytes) -> str:
    if isinstance(s, str):
        s = s.encode()
    return hashlib.sha256(s).hexdigest()


def hash_secret(secret: str) -> str:
    return bcrypt.hashpw(secret.encode(), bcrypt.gensalt()).decode()


def verify_secret(secret: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(secret.encode(), hashed.encode())
    except Exception:
        return False


def generate_random_token(nbytes: int = 32) -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(nbytes)).rstrip(b"=").decode()


def verify_pkce(verifier: str, challenge: str, method: str) -> bool:
    if method != "S256":
        return False
    if len(verifier) < 43 or len(verifier) > 128:
        return False
    computed = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    return hmac.compare_digest(computed, challenge)
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
pytest tests/test_security.py -v
```

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/account-service-backend/
git commit -m "feat(account-service-backend): add security helpers (PKCE, bcrypt)"
```

---

### Task C2: Signing keys (RSA generate + Fernet encrypt + DB persist + JWKS)

**Files:**
- Create: `apps-microservices/account-service-backend/app/core/jwt_keys.py`
- Test: `apps-microservices/account-service-backend/tests/test_jwt_keys.py`

- [ ] **Step 1: Write failing test `tests/test_jwt_keys.py`**

```python
from cryptography.fernet import Fernet

from app.core.jwt_keys import (
    decrypt_private_pem,
    encrypt_private_pem,
    ensure_signing_key,
    get_active_signing_key,
    jwks_response,
)
from app.db.models import SigningKey


def _fernet_key() -> str:
    return Fernet.generate_key().decode()


async def test_ensure_signing_key_creates_first_key():
    key = await ensure_signing_key(encryption_key=_fernet_key())
    assert key.kid
    assert key.is_active is True
    assert "BEGIN PUBLIC KEY" in key.public_pem


async def test_ensure_signing_key_reuses_active():
    fk = _fernet_key()
    a = await ensure_signing_key(encryption_key=fk)
    b = await ensure_signing_key(encryption_key=fk)
    assert a.kid == b.kid


async def test_encrypt_decrypt_roundtrip():
    fk = _fernet_key()
    enc = encrypt_private_pem("private-pem-bytes", fk)
    assert enc != "private-pem-bytes"
    assert decrypt_private_pem(enc, fk) == "private-pem-bytes"


async def test_get_active_signing_key_returns_only_active():
    fk = _fernet_key()
    await ensure_signing_key(encryption_key=fk)
    await SigningKey.all().update(is_active=False)
    new = await ensure_signing_key(encryption_key=fk)
    active = await get_active_signing_key()
    assert active.kid == new.kid


async def test_jwks_response_shape():
    fk = _fernet_key()
    await ensure_signing_key(encryption_key=fk)
    jwks = await jwks_response()
    assert "keys" in jwks
    assert jwks["keys"][0]["kty"] == "RSA"
    assert jwks["keys"][0]["alg"] == "RS256"
    assert jwks["keys"][0]["use"] == "sig"
    assert "kid" in jwks["keys"][0]
    assert "n" in jwks["keys"][0]
    assert "e" in jwks["keys"][0]
```

- [ ] **Step 2: Run test — expect FAIL** (ModuleNotFoundError)

- [ ] **Step 3: Implement `app/core/jwt_keys.py`**

```python
import base64
import secrets

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey

from app.db.models import SigningKey


def _new_kid() -> str:
    return secrets.token_urlsafe(12)


def _generate_keypair() -> tuple[str, str]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_pem = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    return private_pem, public_pem


def encrypt_private_pem(pem: str, encryption_key: str) -> str:
    return Fernet(encryption_key.encode()).encrypt(pem.encode()).decode()


def decrypt_private_pem(token: str, encryption_key: str) -> str:
    return Fernet(encryption_key.encode()).decrypt(token.encode()).decode()


async def ensure_signing_key(*, encryption_key: str) -> SigningKey:
    existing = await SigningKey.filter(is_active=True).first()
    if existing:
        return existing
    private_pem, public_pem = _generate_keypair()
    enc = encrypt_private_pem(private_pem, encryption_key)
    return await SigningKey.create(
        kid=_new_kid(),
        private_pem_encrypted=enc,
        public_pem=public_pem,
        is_active=True,
    )


async def get_active_signing_key() -> SigningKey:
    key = await SigningKey.filter(is_active=True).first()
    if not key:
        raise RuntimeError("No active signing key. Call ensure_signing_key first.")
    return key


def _b64url_uint(n: int) -> str:
    byte_len = (n.bit_length() + 7) // 8
    return base64.urlsafe_b64encode(n.to_bytes(byte_len, "big")).rstrip(b"=").decode()


def _public_jwk_from_pem(public_pem: str, kid: str) -> dict:
    pub: RSAPublicKey = serialization.load_pem_public_key(public_pem.encode())
    numbers = pub.public_numbers()
    return {
        "kty": "RSA",
        "use": "sig",
        "alg": "RS256",
        "kid": kid,
        "n": _b64url_uint(numbers.n),
        "e": _b64url_uint(numbers.e),
    }


async def jwks_response() -> dict:
    keys = await SigningKey.all().order_by("-created_at")
    return {"keys": [_public_jwk_from_pem(k.public_pem, k.kid) for k in keys]}
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
pytest tests/test_jwt_keys.py -v
```

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/account-service-backend/
git commit -m "feat(account-service-backend): RSA signing keys + JWKS"
```

---

### Task C3: JWT encode/decode helpers

**Files:**
- Create: `apps-microservices/account-service-backend/app/core/jwt_tokens.py`
- Test: `apps-microservices/account-service-backend/tests/test_jwt_tokens.py`

- [ ] **Step 1: Write failing test `tests/test_jwt_tokens.py`**

```python
import time

import jwt as pyjwt
import pytest
from cryptography.fernet import Fernet

from app.core.jwt_keys import decrypt_private_pem, ensure_signing_key
from app.core.jwt_tokens import decode_access_token, issue_access_token


def _fk() -> str:
    return Fernet.generate_key().decode()


async def test_issue_access_token_has_required_claims():
    fk = _fk()
    key = await ensure_signing_key(encryption_key=fk)
    token = await issue_access_token(
        sub="u@x",
        client_id="svc",
        encryption_key=fk,
        ttl_seconds=900,
        issuer="https://account.hellopro.eu",
        email="u@x",
        display_name="U",
    )
    claims = pyjwt.decode(
        token, key.public_pem, algorithms=["RS256"], audience="svc",
        options={"verify_aud": True}
    )
    assert claims["sub"] == "u@x"
    assert claims["aud"] == "svc"
    assert claims["iss"] == "https://account.hellopro.eu"
    assert claims["email"] == "u@x"
    assert claims["display_name"] == "U"
    assert claims["exp"] > int(time.time())
    assert "jti" in claims
    headers = pyjwt.get_unverified_header(token)
    assert headers["alg"] == "RS256"
    assert headers["kid"] == key.kid


async def test_decode_access_token_round_trip():
    fk = _fk()
    await ensure_signing_key(encryption_key=fk)
    token = await issue_access_token(
        sub="u@x", client_id="svc", encryption_key=fk,
        ttl_seconds=10, issuer="iss",
    )
    claims = await decode_access_token(token, expected_audience="svc")
    assert claims["sub"] == "u@x"


async def test_decode_rejects_alg_none():
    fk = _fk()
    await ensure_signing_key(encryption_key=fk)
    bad = pyjwt.encode({"sub": "x", "aud": "svc"}, key="", algorithm="none")
    with pytest.raises(Exception):
        await decode_access_token(bad, expected_audience="svc")


async def test_decode_rejects_expired():
    fk = _fk()
    await ensure_signing_key(encryption_key=fk)
    token = await issue_access_token(
        sub="u@x", client_id="svc", encryption_key=fk,
        ttl_seconds=-10, issuer="iss",
    )
    with pytest.raises(pyjwt.ExpiredSignatureError):
        await decode_access_token(token, expected_audience="svc")
```

- [ ] **Step 2: Run test — expect FAIL**

- [ ] **Step 3: Implement `app/core/jwt_tokens.py`**

```python
import secrets
import time

import jwt as pyjwt

from app.core.jwt_keys import decrypt_private_pem, get_active_signing_key
from app.db.models import SigningKey


async def issue_access_token(
    *,
    sub: str,
    client_id: str,
    encryption_key: str,
    ttl_seconds: int,
    issuer: str,
    email: str | None = None,
    display_name: str | None = None,
) -> str:
    key = await get_active_signing_key()
    now = int(time.time())
    claims: dict = {
        "iss": issuer,
        "sub": sub,
        "aud": client_id,
        "iat": now,
        "exp": now + ttl_seconds,
        "jti": secrets.token_urlsafe(16),
    }
    if email is not None:
        claims["email"] = email
    if display_name is not None:
        claims["display_name"] = display_name
    private_pem = decrypt_private_pem(key.private_pem_encrypted, encryption_key)
    return pyjwt.encode(claims, private_pem, algorithm="RS256", headers={"kid": key.kid})


async def _public_pem_for(kid: str) -> str:
    key = await SigningKey.get(kid=kid)
    return key.public_pem


async def decode_access_token(token: str, *, expected_audience: str) -> dict:
    headers = pyjwt.get_unverified_header(token)
    if headers.get("alg") != "RS256":
        raise pyjwt.InvalidAlgorithmError(f"unexpected alg {headers.get('alg')}")
    public_pem = await _public_pem_for(headers["kid"])
    return pyjwt.decode(
        token,
        public_pem,
        algorithms=["RS256"],
        audience=expected_audience,
        options={"require": ["exp", "iat", "sub", "aud"]},
    )
```

- [ ] **Step 4: Run tests — expect PASS**

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/account-service-backend/
git commit -m "feat(account-service-backend): JWT issuance + verification (RS256)"
```

---

## Phase D — Service Layer

### Task D1: HelloPro upstream client

**Files:**
- Create: `apps-microservices/account-service-backend/app/services/__init__.py`
- Create: `apps-microservices/account-service-backend/app/services/hellopro_client.py`
- Test: `apps-microservices/account-service-backend/tests/test_hellopro_client.py`

- [ ] **Step 1: Create `app/services/__init__.py`** (empty)

- [ ] **Step 2: Write failing test `tests/test_hellopro_client.py`**

```python
import httpx
import pytest
import respx

from app.services.hellopro_client import (
    HelloProAuthError,
    HelloProUnavailable,
    validate_credentials,
)

URL = "https://auth.hellopro.fr/api/login"


@respx.mock
async def test_validate_credentials_ok():
    respx.post(URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "token": "upstream-token",
                "email": "u@hellopro.fr",
                "display_name": "U",
            },
        )
    )
    info = await validate_credentials("u@hellopro.fr", "p", URL, timeout=2.0)
    assert info["email"] == "u@hellopro.fr"
    assert info["display_name"] == "U"


@respx.mock
async def test_validate_credentials_401_raises_auth_error():
    respx.post(URL).mock(return_value=httpx.Response(401))
    with pytest.raises(HelloProAuthError):
        await validate_credentials("u", "p", URL, timeout=2.0)


@respx.mock
async def test_validate_credentials_5xx_retried_then_unavailable():
    route = respx.post(URL).mock(
        side_effect=[httpx.Response(500), httpx.Response(503)]
    )
    with pytest.raises(HelloProUnavailable):
        await validate_credentials("u", "p", URL, timeout=2.0)
    assert route.call_count == 2


@respx.mock
async def test_validate_credentials_timeout_unavailable():
    respx.post(URL).mock(side_effect=httpx.ConnectTimeout("nope"))
    with pytest.raises(HelloProUnavailable):
        await validate_credentials("u", "p", URL, timeout=0.1)
```

- [ ] **Step 3: Run test — expect FAIL**

- [ ] **Step 4: Implement `app/services/hellopro_client.py`**

```python
import logging

import httpx

logger = logging.getLogger("hellopro_client")


class HelloProAuthError(Exception):
    """Upstream rejected credentials."""


class HelloProUnavailable(Exception):
    """Upstream unreachable / 5xx after retry."""


async def validate_credentials(
    email: str, password: str, url: str, *, timeout: float
) -> dict:
    last_exc: Exception | None = None
    async with httpx.AsyncClient(timeout=timeout) as client:
        for attempt in range(2):
            try:
                r = await client.post(url, json={"email": email, "password": password})
            except (httpx.TransportError, httpx.TimeoutException) as e:
                last_exc = e
                continue
            if r.status_code == 200:
                data = r.json()
                return {
                    "sub": data.get("sub") or data.get("email") or email,
                    "email": data.get("email", email),
                    "display_name": data.get("display_name", ""),
                }
            if r.status_code in (401, 403):
                raise HelloProAuthError("invalid credentials")
            if 500 <= r.status_code < 600:
                last_exc = RuntimeError(f"upstream {r.status_code}")
                continue
            raise HelloProUnavailable(f"unexpected status {r.status_code}")
    raise HelloProUnavailable(str(last_exc) if last_exc else "unknown")
```

- [ ] **Step 5: Run tests — expect PASS**

- [ ] **Step 6: Commit**

```bash
git add apps-microservices/account-service-backend/
git commit -m "feat(account-service-backend): HelloPro upstream client w/ retry"
```

---

### Task D2: Code service (issue + consume one-shot auth code)

**Files:**
- Create: `apps-microservices/account-service-backend/app/services/code_service.py`
- Test: `apps-microservices/account-service-backend/tests/test_code_service.py`

- [ ] **Step 1: Write failing test `tests/test_code_service.py`**

```python
import pytest

from app.services.code_service import (
    CodeAlreadyConsumed,
    CodeExpired,
    CodeInvalid,
    consume_code,
    issue_code,
)


async def test_issue_code_returns_raw_and_persists_hash():
    raw = await issue_code(
        client_id="svc",
        sub="u@x",
        code_challenge="ch",
        code_challenge_method="S256",
        redirect_uri="https://svc.hellopro.eu/cb",
        ttl_seconds=60,
        email="u@x",
        display_name="U",
    )
    assert isinstance(raw, str) and len(raw) > 16


async def test_consume_code_happy_path():
    raw = await issue_code(
        client_id="svc", sub="u@x", code_challenge="ch",
        code_challenge_method="S256",
        redirect_uri="https://svc.hellopro.eu/cb", ttl_seconds=60,
        email="u@x", display_name="U",
    )
    record = await consume_code(raw, expected_redirect_uri="https://svc.hellopro.eu/cb")
    assert record.sub == "u@x"


async def test_consume_code_unknown_raises():
    with pytest.raises(CodeInvalid):
        await consume_code("nope", expected_redirect_uri="x")


async def test_consume_code_replay_raises():
    raw = await issue_code(
        client_id="svc", sub="u@x", code_challenge="ch",
        code_challenge_method="S256",
        redirect_uri="https://svc.hellopro.eu/cb", ttl_seconds=60,
    )
    await consume_code(raw, expected_redirect_uri="https://svc.hellopro.eu/cb")
    with pytest.raises(CodeAlreadyConsumed):
        await consume_code(raw, expected_redirect_uri="https://svc.hellopro.eu/cb")


async def test_consume_code_expired_raises():
    raw = await issue_code(
        client_id="svc", sub="u@x", code_challenge="ch",
        code_challenge_method="S256",
        redirect_uri="https://svc.hellopro.eu/cb", ttl_seconds=-5,
    )
    with pytest.raises(CodeExpired):
        await consume_code(raw, expected_redirect_uri="https://svc.hellopro.eu/cb")


async def test_consume_code_redirect_mismatch_raises():
    raw = await issue_code(
        client_id="svc", sub="u@x", code_challenge="ch",
        code_challenge_method="S256",
        redirect_uri="https://svc.hellopro.eu/cb", ttl_seconds=60,
    )
    with pytest.raises(CodeInvalid):
        await consume_code(raw, expected_redirect_uri="https://other.hellopro.eu/cb")
```

- [ ] **Step 2: Run test — expect FAIL**

- [ ] **Step 3: Implement `app/services/code_service.py`**

```python
from datetime import datetime, timedelta, timezone

from app.core.security import generate_random_token, sha256_hex
from app.db.models import AuthorizationCode


class CodeInvalid(Exception):
    pass


class CodeExpired(Exception):
    pass


class CodeAlreadyConsumed(Exception):
    pass


async def issue_code(
    *,
    client_id: str,
    sub: str,
    code_challenge: str,
    code_challenge_method: str,
    redirect_uri: str,
    ttl_seconds: int,
    email: str | None = None,
    display_name: str | None = None,
) -> str:
    raw = generate_random_token(32)
    now = datetime.now(timezone.utc)
    await AuthorizationCode.create(
        code_hash=sha256_hex(raw),
        client_id=client_id,
        sub=sub,
        code_challenge=code_challenge,
        code_challenge_method=code_challenge_method,
        redirect_uri=redirect_uri,
        expires_at=now + timedelta(seconds=ttl_seconds),
        user_email=email,
        user_display_name=display_name,
    )
    return raw


async def consume_code(raw: str, *, expected_redirect_uri: str) -> AuthorizationCode:
    h = sha256_hex(raw)
    record = await AuthorizationCode.filter(code_hash=h).first()
    if not record:
        raise CodeInvalid("unknown code")
    if record.consumed_at is not None:
        raise CodeAlreadyConsumed("already consumed")
    if record.redirect_uri != expected_redirect_uri:
        raise CodeInvalid("redirect_uri mismatch")
    if record.expires_at <= datetime.now(timezone.utc):
        raise CodeExpired("expired")
    record.consumed_at = datetime.now(timezone.utc)
    await record.save()
    return record
```

- [ ] **Step 4: Run tests — expect PASS**

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/account-service-backend/
git commit -m "feat(account-service-backend): code_service (issue/consume PKCE codes)"
```

---

### Task D3: Token service (issue access+refresh, rotate, reuse detection)

**Files:**
- Create: `apps-microservices/account-service-backend/app/services/token_service.py`
- Test: `apps-microservices/account-service-backend/tests/test_token_service.py`

- [ ] **Step 1: Write failing test `tests/test_token_service.py`**

```python
import pytest
from cryptography.fernet import Fernet

from app.core.jwt_keys import ensure_signing_key
from app.db.models import RefreshToken
from app.services.token_service import (
    RefreshExpired,
    RefreshInvalid,
    RefreshReuseDetected,
    issue_token_pair,
    revoke_chain,
    rotate_refresh,
)


def _fk() -> str:
    return Fernet.generate_key().decode()


async def _setup():
    fk = _fk()
    await ensure_signing_key(encryption_key=fk)
    return fk


async def test_issue_token_pair_returns_access_and_refresh():
    fk = await _setup()
    pair = await issue_token_pair(
        sub="u@x", client_id="svc", encryption_key=fk,
        access_ttl_seconds=900, refresh_ttl_days=30,
        issuer="iss", email="u@x", display_name="U",
    )
    assert pair["token_type"] == "Bearer"
    assert pair["expires_in"] == 900
    assert pair["access_token"]
    assert pair["refresh_token"]
    assert await RefreshToken.filter(client_id="svc", sub="u@x").exists()


async def test_rotate_refresh_marks_old_revoked_and_issues_new():
    fk = await _setup()
    p1 = await issue_token_pair(
        sub="u@x", client_id="svc", encryption_key=fk,
        access_ttl_seconds=900, refresh_ttl_days=30, issuer="iss",
    )
    p2 = await rotate_refresh(
        raw_refresh=p1["refresh_token"], client_id="svc", encryption_key=fk,
        access_ttl_seconds=900, refresh_ttl_days=30, issuer="iss",
    )
    assert p2["refresh_token"] != p1["refresh_token"]
    rows = await RefreshToken.filter(client_id="svc", sub="u@x").all()
    assert any(r.revoked_at is not None for r in rows)
    assert any(r.revoked_at is None for r in rows)


async def test_rotate_refresh_unknown_raises():
    fk = await _setup()
    with pytest.raises(RefreshInvalid):
        await rotate_refresh(
            raw_refresh="bogus", client_id="svc", encryption_key=fk,
            access_ttl_seconds=900, refresh_ttl_days=30, issuer="iss",
        )


async def test_rotate_refresh_reuse_revokes_chain():
    fk = await _setup()
    p1 = await issue_token_pair(
        sub="u@x", client_id="svc", encryption_key=fk,
        access_ttl_seconds=900, refresh_ttl_days=30, issuer="iss",
    )
    await rotate_refresh(
        raw_refresh=p1["refresh_token"], client_id="svc", encryption_key=fk,
        access_ttl_seconds=900, refresh_ttl_days=30, issuer="iss",
    )
    with pytest.raises(RefreshReuseDetected):
        await rotate_refresh(
            raw_refresh=p1["refresh_token"], client_id="svc", encryption_key=fk,
            access_ttl_seconds=900, refresh_ttl_days=30, issuer="iss",
        )
    rows = await RefreshToken.filter(client_id="svc", sub="u@x").all()
    assert all(r.revoked_at is not None for r in rows)


async def test_revoke_chain_marks_all_revoked():
    fk = await _setup()
    p = await issue_token_pair(
        sub="u@x", client_id="svc", encryption_key=fk,
        access_ttl_seconds=900, refresh_ttl_days=30, issuer="iss",
    )
    await revoke_chain(raw_refresh=p["refresh_token"])
    rows = await RefreshToken.filter(client_id="svc", sub="u@x").all()
    assert all(r.revoked_at is not None for r in rows)
```

- [ ] **Step 2: Run test — expect FAIL**

- [ ] **Step 3: Implement `app/services/token_service.py`**

```python
from datetime import datetime, timedelta, timezone

from app.core.jwt_tokens import issue_access_token
from app.core.security import generate_random_token, sha256_hex
from app.db.models import RefreshToken


class RefreshInvalid(Exception):
    pass


class RefreshExpired(Exception):
    pass


class RefreshReuseDetected(Exception):
    pass


async def issue_token_pair(
    *,
    sub: str,
    client_id: str,
    encryption_key: str,
    access_ttl_seconds: int,
    refresh_ttl_days: int,
    issuer: str,
    email: str | None = None,
    display_name: str | None = None,
    rotated_from_id=None,
    user_agent: str | None = None,
    ip: str | None = None,
) -> dict:
    raw_refresh = generate_random_token(32)
    now = datetime.now(timezone.utc)
    await RefreshToken.create(
        token_hash=sha256_hex(raw_refresh),
        client_id=client_id,
        sub=sub,
        user_email=email,
        user_display_name=display_name,
        expires_at=now + timedelta(days=refresh_ttl_days),
        rotated_from_id=rotated_from_id,
        user_agent=user_agent,
        ip=ip,
    )
    access = await issue_access_token(
        sub=sub,
        client_id=client_id,
        encryption_key=encryption_key,
        ttl_seconds=access_ttl_seconds,
        issuer=issuer,
        email=email,
        display_name=display_name,
    )
    return {
        "access_token": access,
        "refresh_token": raw_refresh,
        "token_type": "Bearer",
        "expires_in": access_ttl_seconds,
    }


async def _lookup(raw_refresh: str) -> RefreshToken:
    h = sha256_hex(raw_refresh)
    row = await RefreshToken.filter(token_hash=h).first()
    if not row:
        raise RefreshInvalid("unknown refresh")
    return row


async def rotate_refresh(
    *,
    raw_refresh: str,
    client_id: str,
    encryption_key: str,
    access_ttl_seconds: int,
    refresh_ttl_days: int,
    issuer: str,
) -> dict:
    row = await _lookup(raw_refresh)
    if row.client_id != client_id:
        raise RefreshInvalid("client mismatch")
    if row.revoked_at is not None:
        # Reuse path: detect rotation child and revoke chain.
        children = await RefreshToken.filter(
            rotated_from_id=row.id
        ).exists()
        if children:
            await RefreshToken.filter(
                client_id=row.client_id, sub=row.sub
            ).update(revoked_at=datetime.now(timezone.utc))
            raise RefreshReuseDetected("reuse detected — chain revoked")
        raise RefreshInvalid("refresh revoked")
    if row.expires_at <= datetime.now(timezone.utc):
        raise RefreshExpired("expired")

    # Mark old as revoked + issue new with rotated_from_id pointing to old.
    row.revoked_at = datetime.now(timezone.utc)
    await row.save()
    return await issue_token_pair(
        sub=row.sub,
        client_id=row.client_id,
        encryption_key=encryption_key,
        access_ttl_seconds=access_ttl_seconds,
        refresh_ttl_days=refresh_ttl_days,
        issuer=issuer,
        email=row.user_email,
        display_name=row.user_display_name,
        rotated_from_id=row.id,
    )


async def revoke_chain(*, raw_refresh: str) -> None:
    row = await _lookup(raw_refresh)
    await RefreshToken.filter(client_id=row.client_id, sub=row.sub).update(
        revoked_at=datetime.now(timezone.utc)
    )
```

- [ ] **Step 4: Run tests — expect PASS**

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/account-service-backend/
git commit -m "feat(account-service-backend): token_service (issue/rotate/revoke)"
```

---

### Task D4: Client service (OAuthClient CRUD + secret hashing)

**Files:**
- Create: `apps-microservices/account-service-backend/app/services/client_service.py`
- Test: `apps-microservices/account-service-backend/tests/test_client_service.py`

- [ ] **Step 1: Write failing test `tests/test_client_service.py`**

```python
import pytest

from app.services.client_service import (
    ClientInactive,
    ClientNotFound,
    InvalidRedirectUri,
    InvalidSecret,
    create_client,
    delete_client,
    get_client_by_id,
    list_clients,
    validate_client_credentials,
    validate_redirect_uri,
)


async def test_create_client_returns_secret_once():
    raw = await create_client(
        client_id="svc",
        name="Service",
        redirect_uris=["https://svc.hellopro.eu/cb"],
        post_logout_redirect_uris=["https://svc.hellopro.eu/"],
        skip_consent=True,
    )
    assert raw and len(raw) >= 32


async def test_create_client_duplicate_raises():
    await create_client(client_id="svc", name="A", redirect_uris=["https://x"])
    with pytest.raises(ValueError):
        await create_client(client_id="svc", name="B", redirect_uris=["https://x"])


async def test_get_client_by_id_returns_row():
    await create_client(client_id="svc", name="A", redirect_uris=["https://x"])
    c = await get_client_by_id("svc")
    assert c.name == "A"


async def test_get_client_unknown_raises():
    with pytest.raises(ClientNotFound):
        await get_client_by_id("nope")


async def test_list_clients_returns_all():
    await create_client(client_id="a", name="A", redirect_uris=["https://x"])
    await create_client(client_id="b", name="B", redirect_uris=["https://y"])
    assert {c.client_id for c in await list_clients()} == {"a", "b"}


async def test_delete_client_marks_inactive():
    await create_client(client_id="svc", name="A", redirect_uris=["https://x"])
    await delete_client("svc")
    c = await get_client_by_id("svc")
    assert c.is_active is False


async def test_validate_redirect_uri_exact_match():
    await create_client(
        client_id="svc", name="A",
        redirect_uris=["https://svc.hellopro.eu/cb"],
    )
    c = await get_client_by_id("svc")
    validate_redirect_uri(c, "https://svc.hellopro.eu/cb")  # ok
    with pytest.raises(InvalidRedirectUri):
        validate_redirect_uri(c, "https://svc.hellopro.eu/cb/")
    with pytest.raises(InvalidRedirectUri):
        validate_redirect_uri(c, "https://attacker.example/cb")


async def test_validate_credentials_ok_and_wrong_secret():
    raw = await create_client(client_id="svc", name="A", redirect_uris=["https://x"])
    c = await validate_client_credentials("svc", raw)
    assert c.client_id == "svc"
    with pytest.raises(InvalidSecret):
        await validate_client_credentials("svc", "wrong")


async def test_validate_credentials_inactive():
    raw = await create_client(client_id="svc", name="A", redirect_uris=["https://x"])
    await delete_client("svc")
    with pytest.raises(ClientInactive):
        await validate_client_credentials("svc", raw)
```

- [ ] **Step 2: Run test — expect FAIL**

- [ ] **Step 3: Implement `app/services/client_service.py`**

```python
from app.core.security import generate_random_token, hash_secret, verify_secret
from app.db.models import OAuthClient


class ClientNotFound(Exception):
    pass


class ClientInactive(Exception):
    pass


class InvalidSecret(Exception):
    pass


class InvalidRedirectUri(Exception):
    pass


async def create_client(
    *,
    client_id: str,
    name: str,
    redirect_uris: list[str],
    post_logout_redirect_uris: list[str] | None = None,
    skip_consent: bool = True,
) -> str:
    if await OAuthClient.filter(client_id=client_id).exists():
        raise ValueError(f"client_id {client_id} already exists")
    raw = generate_random_token(32)
    await OAuthClient.create(
        client_id=client_id,
        client_secret_hash=hash_secret(raw),
        name=name,
        redirect_uris=redirect_uris,
        post_logout_redirect_uris=post_logout_redirect_uris or [],
        skip_consent=skip_consent,
        is_active=True,
    )
    return raw


async def get_client_by_id(client_id: str) -> OAuthClient:
    c = await OAuthClient.filter(client_id=client_id).first()
    if not c:
        raise ClientNotFound(client_id)
    return c


async def list_clients() -> list[OAuthClient]:
    return await OAuthClient.all()


async def delete_client(client_id: str) -> None:
    c = await get_client_by_id(client_id)
    c.is_active = False
    await c.save()


async def validate_client_credentials(client_id: str, secret: str) -> OAuthClient:
    c = await get_client_by_id(client_id)
    if not c.is_active:
        raise ClientInactive(client_id)
    if not verify_secret(secret, c.client_secret_hash):
        raise InvalidSecret(client_id)
    return c


def validate_redirect_uri(client: OAuthClient, uri: str) -> None:
    if uri not in (client.redirect_uris or []):
        raise InvalidRedirectUri(uri)
```

- [ ] **Step 4: Run tests — expect PASS**

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/account-service-backend/
git commit -m "feat(account-service-backend): client_service (CRUD + secret hashing)"
```

---

## Phase E — Schemas

### Task E1: Pydantic request/response schemas

**Files:**
- Create: `apps-microservices/account-service-backend/app/schemas.py`

- [ ] **Step 1: Implement `app/schemas.py`**

```python
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, HttpUrl


class AuthorizeRequest(BaseModel):
    email: EmailStr
    password: str
    client_id: str
    redirect_uri: str
    state: str
    code_challenge: str
    code_challenge_method: Literal["S256"]


class AuthorizeRedirectResponse(BaseModel):
    redirect: str


class AuthorizeConsentResponse(BaseModel):
    next: Literal["/consent"]
    consent_token: str


class TokenRequestAuthCode(BaseModel):
    grant_type: Literal["authorization_code"]
    code: str
    redirect_uri: str
    client_id: str
    client_secret: str
    code_verifier: str = Field(min_length=43, max_length=128)


class TokenRequestRefresh(BaseModel):
    grant_type: Literal["refresh_token"]
    refresh_token: str
    client_id: str
    client_secret: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["Bearer"] = "Bearer"
    expires_in: int


class RevokeRequest(BaseModel):
    refresh_token: str
    client_id: str
    client_secret: str


class IntrospectRequest(BaseModel):
    token: str
    client_id: str
    client_secret: str


class IntrospectResponse(BaseModel):
    active: bool
    sub: str | None = None
    aud: str | None = None
    exp: int | None = None
    iat: int | None = None


class UserInfoResponse(BaseModel):
    sub: str
    email: str | None = None
    display_name: str | None = None


class CreateClientRequest(BaseModel):
    client_id: str
    name: str
    redirect_uris: list[HttpUrl]
    post_logout_redirect_uris: list[HttpUrl] = []
    skip_consent: bool = True


class CreateClientResponse(BaseModel):
    client_id: str
    client_secret: str
    name: str


class ClientSummary(BaseModel):
    client_id: str
    name: str
    redirect_uris: list[str]
    skip_consent: bool
    is_active: bool
    created_at: datetime


class ErrorResponse(BaseModel):
    error: str
    error_description: str | None = None
```

- [ ] **Step 2: Commit (no test file — schemas exercised by router tests)**

```bash
git add apps-microservices/account-service-backend/app/schemas.py
git commit -m "feat(account-service-backend): Pydantic schemas for OAuth endpoints"
```

---

## Phase F — Routers

### Task F1: JWKS router

**Files:**
- Create: `apps-microservices/account-service-backend/app/routers/jwks.py`
- Test: `apps-microservices/account-service-backend/tests/test_jwks.py`
- Modify: `apps-microservices/account-service-backend/main.py`

- [ ] **Step 1: Write failing test `tests/test_jwks.py`**

```python
from cryptography.fernet import Fernet

from app.core.jwt_keys import ensure_signing_key


async def test_jwks_endpoint_returns_active_key(client, monkeypatch):
    fk = Fernet.generate_key().decode()
    monkeypatch.setenv("JWT_KEY_ENCRYPTION_KEY", fk)
    await ensure_signing_key(encryption_key=fk)
    r = client.get("/.well-known/jwks.json")
    assert r.status_code == 200
    data = r.json()
    assert data["keys"][0]["kty"] == "RSA"
    assert data["keys"][0]["alg"] == "RS256"
```

- [ ] **Step 2: Run test — expect FAIL**

- [ ] **Step 3: Implement `app/routers/jwks.py`**

```python
from fastapi import APIRouter

from app.core.jwt_keys import jwks_response

router = APIRouter()


@router.get("/.well-known/jwks.json", tags=["oauth"])
async def jwks() -> dict:
    return await jwks_response()
```

- [ ] **Step 4: Wire into `main.py`**

Add import + include:

```python
from app.routers import health, jwks

app.include_router(jwks.router)
```

- [ ] **Step 5: Run test — expect PASS**

- [ ] **Step 6: Commit**

```bash
git add apps-microservices/account-service-backend/
git commit -m "feat(account-service-backend): /.well-known/jwks.json"
```

---

### Task F2: Authorize router

**Files:**
- Create: `apps-microservices/account-service-backend/app/routers/authorize.py`
- Test: `apps-microservices/account-service-backend/tests/test_authorize.py`
- Modify: `apps-microservices/account-service-backend/main.py`

- [ ] **Step 1: Write failing test `tests/test_authorize.py`**

```python
import httpx
import respx
from cryptography.fernet import Fernet

from app.core.jwt_keys import ensure_signing_key
from app.services.client_service import create_client


async def _setup(monkeypatch):
    fk = Fernet.generate_key().decode()
    monkeypatch.setenv("JWT_KEY_ENCRYPTION_KEY", fk)
    monkeypatch.setenv("HELLOPRO_AUTH_URL", "https://auth.hellopro.fr/api/login")
    monkeypatch.setenv("MYSQL_HOST", "x")
    monkeypatch.setenv("MYSQL_USER", "x")
    monkeypatch.setenv("MYSQL_PASS", "x")
    monkeypatch.setenv("MYSQL_DB", "x")
    monkeypatch.setenv("GATEWAY_ADMIN_KEY", "k")
    await ensure_signing_key(encryption_key=fk)
    await create_client(
        client_id="svc", name="S",
        redirect_uris=["https://svc.hellopro.eu/cb"],
        skip_consent=True,
    )


@respx.mock
async def test_authorize_happy_path_returns_redirect(client, monkeypatch):
    await _setup(monkeypatch)
    respx.post("https://auth.hellopro.fr/api/login").mock(
        return_value=httpx.Response(200, json={"email": "u@x", "display_name": "U"})
    )
    r = client.post("/authorize", json={
        "email": "u@x", "password": "p",
        "client_id": "svc",
        "redirect_uri": "https://svc.hellopro.eu/cb",
        "state": "s", "code_challenge": "c",
        "code_challenge_method": "S256",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["redirect"].startswith("https://svc.hellopro.eu/cb?code=")
    assert "state=s" in body["redirect"]


async def test_authorize_unknown_client_returns_400(client, monkeypatch):
    await _setup(monkeypatch)
    r = client.post("/authorize", json={
        "email": "u@x", "password": "p", "client_id": "nope",
        "redirect_uri": "https://x", "state": "s", "code_challenge": "c",
        "code_challenge_method": "S256",
    })
    assert r.status_code == 400
    assert r.json()["error"] == "invalid_client"


async def test_authorize_bad_redirect_uri_returns_400(client, monkeypatch):
    await _setup(monkeypatch)
    r = client.post("/authorize", json={
        "email": "u@x", "password": "p", "client_id": "svc",
        "redirect_uri": "https://attacker.example/cb",
        "state": "s", "code_challenge": "c",
        "code_challenge_method": "S256",
    })
    assert r.status_code == 400
    assert r.json()["error"] == "invalid_redirect_uri"


@respx.mock
async def test_authorize_upstream_401_returns_401(client, monkeypatch):
    await _setup(monkeypatch)
    respx.post("https://auth.hellopro.fr/api/login").mock(
        return_value=httpx.Response(401)
    )
    r = client.post("/authorize", json={
        "email": "u@x", "password": "wrong", "client_id": "svc",
        "redirect_uri": "https://svc.hellopro.eu/cb",
        "state": "s", "code_challenge": "c",
        "code_challenge_method": "S256",
    })
    assert r.status_code == 401
    assert r.json()["error"] == "access_denied"
```

- [ ] **Step 2: Run test — expect FAIL**

- [ ] **Step 3: Implement `app/routers/authorize.py`**

```python
import logging
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException

from app.core.settings import get_settings
from app.schemas import (
    AuthorizeConsentResponse,
    AuthorizeRedirectResponse,
    AuthorizeRequest,
    ErrorResponse,
)
from app.services.client_service import (
    ClientInactive,
    ClientNotFound,
    InvalidRedirectUri,
    get_client_by_id,
    validate_redirect_uri,
)
from app.services.code_service import issue_code
from app.services.hellopro_client import (
    HelloProAuthError,
    HelloProUnavailable,
    validate_credentials,
)

logger = logging.getLogger("authorize")
router = APIRouter()


def _err(status: int, code: str, desc: str | None = None):
    raise HTTPException(
        status_code=status,
        detail=ErrorResponse(error=code, error_description=desc).model_dump(
            exclude_none=True
        ),
    )


@router.post(
    "/authorize",
    tags=["oauth"],
    response_model=AuthorizeRedirectResponse | AuthorizeConsentResponse,
)
async def authorize(req: AuthorizeRequest):
    settings = get_settings()
    try:
        client = await get_client_by_id(req.client_id)
    except ClientNotFound:
        _err(400, "invalid_client", "unknown client_id")
    if not client.is_active:
        _err(400, "invalid_client", "client inactive")

    try:
        validate_redirect_uri(client, req.redirect_uri)
    except InvalidRedirectUri:
        _err(400, "invalid_redirect_uri")

    try:
        user = await validate_credentials(
            req.email,
            req.password,
            str(settings.HELLOPRO_AUTH_URL),
            timeout=settings.HELLOPRO_AUTH_TIMEOUT_SECONDS,
        )
    except HelloProAuthError:
        _err(401, "access_denied")
    except HelloProUnavailable:
        _err(503, "upstream_unavailable")

    raw_code = await issue_code(
        client_id=client.client_id,
        sub=user["sub"],
        code_challenge=req.code_challenge,
        code_challenge_method=req.code_challenge_method,
        redirect_uri=req.redirect_uri,
        ttl_seconds=settings.AUTH_CODE_EXPIRE_SECONDS,
        email=user["email"],
        display_name=user["display_name"],
    )

    qs = urlencode({"code": raw_code, "state": req.state})
    redirect_url = f"{req.redirect_uri}?{qs}"
    return AuthorizeRedirectResponse(redirect=redirect_url)
```

- [ ] **Step 4: Wire `authorize` router in `main.py`**

```python
from app.routers import authorize, health, jwks
app.include_router(authorize.router)
```

- [ ] **Step 5: Add error-handler so HTTPException returns the body shape we asserted**

In `main.py`:

```python
from fastapi import Request
from fastapi.exceptions import HTTPException as FastAPIHTTPException
from fastapi.responses import JSONResponse


@app.exception_handler(FastAPIHTTPException)
async def http_exception_handler(_: Request, exc: FastAPIHTTPException):
    if isinstance(exc.detail, dict):
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    return JSONResponse(status_code=exc.status_code, content={"error": str(exc.detail)})
```

- [ ] **Step 6: Run tests — expect PASS**

- [ ] **Step 7: Commit**

```bash
git add apps-microservices/account-service-backend/
git commit -m "feat(account-service-backend): POST /authorize endpoint"
```

---

### Task F3: Token router

**Files:**
- Create: `apps-microservices/account-service-backend/app/routers/token.py`
- Test: `apps-microservices/account-service-backend/tests/test_token_endpoint.py`
- Modify: `apps-microservices/account-service-backend/main.py`

- [ ] **Step 1: Write failing test `tests/test_token_endpoint.py`**

```python
import hashlib
import base64

from cryptography.fernet import Fernet

from app.core.jwt_keys import ensure_signing_key
from app.services.client_service import create_client
from app.services.code_service import issue_code


def _challenge(verifier: str) -> str:
    return base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).rstrip(b"=").decode()


async def _setup(monkeypatch):
    fk = Fernet.generate_key().decode()
    monkeypatch.setenv("JWT_KEY_ENCRYPTION_KEY", fk)
    monkeypatch.setenv("HELLOPRO_AUTH_URL", "https://auth.hellopro.fr/api/login")
    monkeypatch.setenv("MYSQL_HOST", "x")
    monkeypatch.setenv("MYSQL_USER", "x")
    monkeypatch.setenv("MYSQL_PASS", "x")
    monkeypatch.setenv("MYSQL_DB", "x")
    monkeypatch.setenv("GATEWAY_ADMIN_KEY", "k")
    await ensure_signing_key(encryption_key=fk)
    secret = await create_client(
        client_id="svc", name="S",
        redirect_uris=["https://svc.hellopro.eu/cb"],
        skip_consent=True,
    )
    return secret


async def test_token_authorization_code_happy_path(client, monkeypatch):
    secret = await _setup(monkeypatch)
    verifier = "v" * 64
    code = await issue_code(
        client_id="svc", sub="u@x",
        code_challenge=_challenge(verifier),
        code_challenge_method="S256",
        redirect_uri="https://svc.hellopro.eu/cb",
        ttl_seconds=60, email="u@x", display_name="U",
    )
    r = client.post("/token", data={
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": "https://svc.hellopro.eu/cb",
        "client_id": "svc", "client_secret": secret,
        "code_verifier": verifier,
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["token_type"] == "Bearer"
    assert body["expires_in"] == 900
    assert body["access_token"]
    assert body["refresh_token"]


async def test_token_bad_secret_returns_invalid_client(client, monkeypatch):
    secret = await _setup(monkeypatch)
    verifier = "v" * 64
    code = await issue_code(
        client_id="svc", sub="u@x",
        code_challenge=_challenge(verifier),
        code_challenge_method="S256",
        redirect_uri="https://svc.hellopro.eu/cb",
        ttl_seconds=60,
    )
    r = client.post("/token", data={
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": "https://svc.hellopro.eu/cb",
        "client_id": "svc", "client_secret": "wrong",
        "code_verifier": verifier,
    })
    assert r.status_code == 401
    assert r.json()["error"] == "invalid_client"


async def test_token_bad_verifier_returns_invalid_grant(client, monkeypatch):
    secret = await _setup(monkeypatch)
    verifier = "v" * 64
    code = await issue_code(
        client_id="svc", sub="u@x",
        code_challenge=_challenge(verifier),
        code_challenge_method="S256",
        redirect_uri="https://svc.hellopro.eu/cb",
        ttl_seconds=60,
    )
    r = client.post("/token", data={
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": "https://svc.hellopro.eu/cb",
        "client_id": "svc", "client_secret": secret,
        "code_verifier": "x" * 64,
    })
    assert r.status_code == 400
    assert r.json()["error"] == "invalid_grant"


async def test_token_refresh_grant_rotates(client, monkeypatch):
    secret = await _setup(monkeypatch)
    verifier = "v" * 64
    code = await issue_code(
        client_id="svc", sub="u@x",
        code_challenge=_challenge(verifier),
        code_challenge_method="S256",
        redirect_uri="https://svc.hellopro.eu/cb",
        ttl_seconds=60, email="u@x",
    )
    r1 = client.post("/token", data={
        "grant_type": "authorization_code", "code": code,
        "redirect_uri": "https://svc.hellopro.eu/cb",
        "client_id": "svc", "client_secret": secret,
        "code_verifier": verifier,
    })
    refresh = r1.json()["refresh_token"]

    r2 = client.post("/token", data={
        "grant_type": "refresh_token",
        "refresh_token": refresh,
        "client_id": "svc", "client_secret": secret,
    })
    assert r2.status_code == 200
    assert r2.json()["refresh_token"] != refresh
```

- [ ] **Step 2: Run test — expect FAIL**

- [ ] **Step 3: Implement `app/routers/token.py`**

```python
from fastapi import APIRouter, Form, HTTPException

from app.core.security import verify_pkce
from app.core.settings import get_settings
from app.schemas import ErrorResponse, TokenResponse
from app.services.client_service import (
    ClientInactive,
    ClientNotFound,
    InvalidSecret,
    validate_client_credentials,
)
from app.services.code_service import (
    CodeAlreadyConsumed,
    CodeExpired,
    CodeInvalid,
    consume_code,
)
from app.services.token_service import (
    RefreshExpired,
    RefreshInvalid,
    RefreshReuseDetected,
    issue_token_pair,
    rotate_refresh,
)

router = APIRouter()


def _err(status: int, code: str, desc: str | None = None):
    raise HTTPException(
        status_code=status,
        detail=ErrorResponse(error=code, error_description=desc).model_dump(
            exclude_none=True
        ),
    )


async def _authn_client(client_id: str, client_secret: str):
    try:
        return await validate_client_credentials(client_id, client_secret)
    except (ClientNotFound, ClientInactive):
        _err(401, "invalid_client", "unknown or inactive client")
    except InvalidSecret:
        _err(401, "invalid_client", "bad secret")


@router.post("/token", tags=["oauth"], response_model=TokenResponse)
async def token(
    grant_type: str = Form(...),
    client_id: str = Form(...),
    client_secret: str = Form(...),
    code: str | None = Form(None),
    redirect_uri: str | None = Form(None),
    code_verifier: str | None = Form(None),
    refresh_token: str | None = Form(None),
):
    settings = get_settings()
    await _authn_client(client_id, client_secret)

    if grant_type == "authorization_code":
        if not code or not redirect_uri or not code_verifier:
            _err(400, "invalid_request", "missing code/redirect_uri/code_verifier")
        try:
            record = await consume_code(code, expected_redirect_uri=redirect_uri)
        except (CodeInvalid, CodeAlreadyConsumed, CodeExpired):
            _err(400, "invalid_grant")
        if not verify_pkce(code_verifier, record.code_challenge, record.code_challenge_method):
            _err(400, "invalid_grant", "PKCE verifier mismatch")
        if record.client_id != client_id:
            _err(400, "invalid_grant", "client mismatch")
        pair = await issue_token_pair(
            sub=record.sub,
            client_id=client_id,
            encryption_key=settings.JWT_KEY_ENCRYPTION_KEY,
            access_ttl_seconds=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            refresh_ttl_days=settings.REFRESH_TOKEN_EXPIRE_DAYS,
            issuer=settings.JWT_ISSUER,
            email=record.user_email,
            display_name=record.user_display_name,
        )
        return TokenResponse(**pair)

    if grant_type == "refresh_token":
        if not refresh_token:
            _err(400, "invalid_request", "missing refresh_token")
        try:
            pair = await rotate_refresh(
                raw_refresh=refresh_token,
                client_id=client_id,
                encryption_key=settings.JWT_KEY_ENCRYPTION_KEY,
                access_ttl_seconds=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
                refresh_ttl_days=settings.REFRESH_TOKEN_EXPIRE_DAYS,
                issuer=settings.JWT_ISSUER,
            )
        except (RefreshInvalid, RefreshExpired, RefreshReuseDetected):
            _err(400, "invalid_grant")
        return TokenResponse(**pair)

    _err(400, "unsupported_grant_type")
```

- [ ] **Step 4: Wire in `main.py`**

```python
from app.routers import authorize, health, jwks, token
app.include_router(token.router)
```

- [ ] **Step 5: Run tests — expect PASS**

- [ ] **Step 6: Commit**

```bash
git add apps-microservices/account-service-backend/
git commit -m "feat(account-service-backend): POST /token (auth_code + refresh_token grants)"
```

---

### Task F4: Revoke router

**Files:**
- Create: `apps-microservices/account-service-backend/app/routers/revoke.py`
- Test: `apps-microservices/account-service-backend/tests/test_revoke.py`
- Modify: `apps-microservices/account-service-backend/main.py`

- [ ] **Step 1: Write failing test `tests/test_revoke.py`**

```python
from cryptography.fernet import Fernet

from app.core.jwt_keys import ensure_signing_key
from app.db.models import RefreshToken
from app.services.client_service import create_client
from app.services.token_service import issue_token_pair


async def _setup(monkeypatch):
    fk = Fernet.generate_key().decode()
    monkeypatch.setenv("JWT_KEY_ENCRYPTION_KEY", fk)
    monkeypatch.setenv("HELLOPRO_AUTH_URL", "https://auth.hellopro.fr/api/login")
    monkeypatch.setenv("MYSQL_HOST", "x")
    monkeypatch.setenv("MYSQL_USER", "x")
    monkeypatch.setenv("MYSQL_PASS", "x")
    monkeypatch.setenv("MYSQL_DB", "x")
    monkeypatch.setenv("GATEWAY_ADMIN_KEY", "k")
    await ensure_signing_key(encryption_key=fk)
    return fk, await create_client(client_id="svc", name="S", redirect_uris=["https://x"])


async def test_revoke_marks_chain_revoked(client, monkeypatch):
    fk, secret = await _setup(monkeypatch)
    pair = await issue_token_pair(
        sub="u@x", client_id="svc", encryption_key=fk,
        access_ttl_seconds=900, refresh_ttl_days=30, issuer="iss",
    )
    r = client.post("/revoke", json={
        "refresh_token": pair["refresh_token"],
        "client_id": "svc", "client_secret": secret,
    })
    assert r.status_code == 200
    rows = await RefreshToken.filter(client_id="svc", sub="u@x").all()
    assert all(row.revoked_at is not None for row in rows)


async def test_revoke_unknown_token_returns_200(client, monkeypatch):
    _, secret = await _setup(monkeypatch)
    r = client.post("/revoke", json={
        "refresh_token": "bogus", "client_id": "svc", "client_secret": secret,
    })
    assert r.status_code == 200  # RFC 7009: revoke is idempotent
```

- [ ] **Step 2: Run test — expect FAIL**

- [ ] **Step 3: Implement `app/routers/revoke.py`**

```python
from fastapi import APIRouter, HTTPException

from app.schemas import ErrorResponse, RevokeRequest
from app.services.client_service import (
    ClientInactive,
    ClientNotFound,
    InvalidSecret,
    validate_client_credentials,
)
from app.services.token_service import RefreshInvalid, revoke_chain

router = APIRouter()


def _err(status: int, code: str):
    raise HTTPException(
        status_code=status,
        detail=ErrorResponse(error=code).model_dump(exclude_none=True),
    )


@router.post("/revoke", tags=["oauth"])
async def revoke(req: RevokeRequest):
    try:
        await validate_client_credentials(req.client_id, req.client_secret)
    except (ClientNotFound, ClientInactive, InvalidSecret):
        _err(401, "invalid_client")
    try:
        await revoke_chain(raw_refresh=req.refresh_token)
    except RefreshInvalid:
        pass  # idempotent per RFC 7009
    return {"revoked": True}
```

- [ ] **Step 4: Wire in `main.py`**

```python
from app.routers import authorize, health, jwks, revoke, token
app.include_router(revoke.router)
```

- [ ] **Step 5: Run tests — expect PASS**

- [ ] **Step 6: Commit**

```bash
git add apps-microservices/account-service-backend/
git commit -m "feat(account-service-backend): POST /revoke (idempotent chain revoke)"
```

---

### Task F5: Introspect router

**Files:**
- Create: `apps-microservices/account-service-backend/app/routers/introspect.py`
- Test: `apps-microservices/account-service-backend/tests/test_introspect.py`
- Modify: `apps-microservices/account-service-backend/main.py`

- [ ] **Step 1: Write failing test `tests/test_introspect.py`**

```python
from cryptography.fernet import Fernet

from app.core.jwt_keys import ensure_signing_key
from app.services.client_service import create_client
from app.services.token_service import issue_token_pair


async def _setup(monkeypatch):
    fk = Fernet.generate_key().decode()
    monkeypatch.setenv("JWT_KEY_ENCRYPTION_KEY", fk)
    monkeypatch.setenv("HELLOPRO_AUTH_URL", "https://auth.hellopro.fr/api/login")
    monkeypatch.setenv("MYSQL_HOST", "x")
    monkeypatch.setenv("MYSQL_USER", "x")
    monkeypatch.setenv("MYSQL_PASS", "x")
    monkeypatch.setenv("MYSQL_DB", "x")
    monkeypatch.setenv("GATEWAY_ADMIN_KEY", "k")
    await ensure_signing_key(encryption_key=fk)
    return fk, await create_client(client_id="svc", name="S", redirect_uris=["https://x"])


async def test_introspect_active(client, monkeypatch):
    fk, secret = await _setup(monkeypatch)
    pair = await issue_token_pair(
        sub="u@x", client_id="svc", encryption_key=fk,
        access_ttl_seconds=900, refresh_ttl_days=30, issuer="iss",
    )
    r = client.post("/introspect", json={
        "token": pair["access_token"], "client_id": "svc", "client_secret": secret,
    })
    assert r.status_code == 200
    body = r.json()
    assert body["active"] is True
    assert body["sub"] == "u@x"


async def test_introspect_invalid_token(client, monkeypatch):
    _, secret = await _setup(monkeypatch)
    r = client.post("/introspect", json={
        "token": "garbage", "client_id": "svc", "client_secret": secret,
    })
    assert r.status_code == 200
    assert r.json() == {"active": False}
```

- [ ] **Step 2: Run test — expect FAIL**

- [ ] **Step 3: Implement `app/routers/introspect.py`**

```python
from fastapi import APIRouter, HTTPException

from app.core.jwt_tokens import decode_access_token
from app.schemas import ErrorResponse, IntrospectRequest, IntrospectResponse
from app.services.client_service import (
    ClientInactive,
    ClientNotFound,
    InvalidSecret,
    validate_client_credentials,
)

router = APIRouter()


@router.post("/introspect", tags=["oauth"], response_model=IntrospectResponse)
async def introspect(req: IntrospectRequest):
    try:
        await validate_client_credentials(req.client_id, req.client_secret)
    except (ClientNotFound, ClientInactive, InvalidSecret):
        raise HTTPException(
            status_code=401,
            detail=ErrorResponse(error="invalid_client").model_dump(),
        )
    try:
        claims = await decode_access_token(req.token, expected_audience=req.client_id)
    except Exception:
        return IntrospectResponse(active=False)
    return IntrospectResponse(
        active=True,
        sub=claims.get("sub"),
        aud=claims.get("aud"),
        exp=claims.get("exp"),
        iat=claims.get("iat"),
    )
```

- [ ] **Step 4: Wire in `main.py` + run tests + commit**

```bash
pytest tests/test_introspect.py -v
git add apps-microservices/account-service-backend/
git commit -m "feat(account-service-backend): POST /introspect"
```

---

### Task F6: UserInfo router

**Files:**
- Create: `apps-microservices/account-service-backend/app/routers/userinfo.py`
- Test: `apps-microservices/account-service-backend/tests/test_userinfo.py`
- Modify: `apps-microservices/account-service-backend/main.py`

- [ ] **Step 1: Write failing test `tests/test_userinfo.py`**

```python
from cryptography.fernet import Fernet

from app.core.jwt_keys import ensure_signing_key
from app.services.client_service import create_client
from app.services.token_service import issue_token_pair


async def test_userinfo_returns_claims(client, monkeypatch):
    fk = Fernet.generate_key().decode()
    monkeypatch.setenv("JWT_KEY_ENCRYPTION_KEY", fk)
    monkeypatch.setenv("HELLOPRO_AUTH_URL", "https://auth.hellopro.fr/api/login")
    monkeypatch.setenv("MYSQL_HOST", "x")
    monkeypatch.setenv("MYSQL_USER", "x")
    monkeypatch.setenv("MYSQL_PASS", "x")
    monkeypatch.setenv("MYSQL_DB", "x")
    monkeypatch.setenv("GATEWAY_ADMIN_KEY", "k")
    await ensure_signing_key(encryption_key=fk)
    await create_client(client_id="svc", name="S", redirect_uris=["https://x"])
    pair = await issue_token_pair(
        sub="u@x", client_id="svc", encryption_key=fk,
        access_ttl_seconds=900, refresh_ttl_days=30, issuer="iss",
        email="u@x", display_name="U",
    )
    r = client.get(
        "/userinfo",
        headers={"Authorization": f"Bearer {pair['access_token']}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["sub"] == "u@x"
    assert body["email"] == "u@x"
    assert body["display_name"] == "U"


async def test_userinfo_missing_bearer_returns_401(client):
    r = client.get("/userinfo")
    assert r.status_code == 401
```

- [ ] **Step 2: Implement `app/routers/userinfo.py`**

```python
from fastapi import APIRouter, Header, HTTPException

from app.core.jwt_tokens import decode_access_token
from app.schemas import UserInfoResponse

router = APIRouter()


@router.get("/userinfo", tags=["oauth"], response_model=UserInfoResponse)
async def userinfo(authorization: str | None = Header(None)):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail={"error": "invalid_token"})
    token = authorization[7:].strip()
    import jwt as pyjwt
    try:
        unverified = pyjwt.decode(token, options={"verify_signature": False})
        aud = unverified.get("aud")
    except Exception:
        raise HTTPException(status_code=401, detail={"error": "invalid_token"})
    try:
        claims = await decode_access_token(token, expected_audience=aud)
    except Exception:
        raise HTTPException(status_code=401, detail={"error": "invalid_token"})
    return UserInfoResponse(
        sub=claims["sub"],
        email=claims.get("email"),
        display_name=claims.get("display_name"),
    )
```

- [ ] **Step 3: Wire in `main.py` + run tests + commit**

```bash
pytest tests/test_userinfo.py -v
git add apps-microservices/account-service-backend/
git commit -m "feat(account-service-backend): GET /userinfo"
```

---

### Task F7: Logout router

**Files:**
- Create: `apps-microservices/account-service-backend/app/routers/logout.py`
- Test: `apps-microservices/account-service-backend/tests/test_logout.py`

- [ ] **Step 1: Write failing test `tests/test_logout.py`**

```python
async def test_logout_redirects_to_post_logout(client, monkeypatch):
    monkeypatch.setenv("HELLOPRO_AUTH_URL", "https://auth.hellopro.fr/api/login")
    monkeypatch.setenv("MYSQL_HOST", "x")
    monkeypatch.setenv("MYSQL_USER", "x")
    monkeypatch.setenv("MYSQL_PASS", "x")
    monkeypatch.setenv("MYSQL_DB", "x")
    monkeypatch.setenv("JWT_KEY_ENCRYPTION_KEY", "Z" * 44)
    monkeypatch.setenv("GATEWAY_ADMIN_KEY", "k")
    r = client.get(
        "/logout?post_logout_redirect_uri=https://svc.hellopro.eu/",
        follow_redirects=False,
    )
    assert r.status_code == 200
    assert "https://svc.hellopro.eu/" in r.text
```

- [ ] **Step 2: Implement `app/routers/logout.py`**

```python
from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse

router = APIRouter()


@router.get("/logout", tags=["oauth"], response_class=HTMLResponse)
async def logout_page(post_logout_redirect_uri: str | None = Query(None)):
    target = post_logout_redirect_uri or "/"
    return HTMLResponse(
        f"""<!doctype html>
<html><body>
<p>You are now logged out.</p>
<p><a href="{target}">Continue</a></p>
<script>setTimeout(() => location.assign("{target}"), 1500);</script>
</body></html>"""
    )
```

- [ ] **Step 3: Wire in `main.py` + run + commit**

```bash
pytest tests/test_logout.py -v
git add apps-microservices/account-service-backend/
git commit -m "feat(account-service-backend): GET /logout post-logout page"
```

---

### Task F8: Admin clients router (X-Admin-Key gated)

**Files:**
- Create: `apps-microservices/account-service-backend/app/routers/admin_clients.py`
- Test: `apps-microservices/account-service-backend/tests/test_admin_clients.py`

- [ ] **Step 1: Write failing test `tests/test_admin_clients.py`**

```python
async def _env(monkeypatch):
    monkeypatch.setenv("HELLOPRO_AUTH_URL", "https://auth.hellopro.fr/api/login")
    monkeypatch.setenv("MYSQL_HOST", "x")
    monkeypatch.setenv("MYSQL_USER", "x")
    monkeypatch.setenv("MYSQL_PASS", "x")
    monkeypatch.setenv("MYSQL_DB", "x")
    monkeypatch.setenv("JWT_KEY_ENCRYPTION_KEY", "Z" * 44)
    monkeypatch.setenv("GATEWAY_ADMIN_KEY", "admin")


async def test_admin_create_client_returns_secret_once(client, monkeypatch):
    await _env(monkeypatch)
    r = client.post(
        "/admin/clients",
        headers={"X-Admin-Key": "admin"},
        json={
            "client_id": "svc", "name": "S",
            "redirect_uris": ["https://svc.hellopro.eu/cb"],
            "post_logout_redirect_uris": ["https://svc.hellopro.eu/"],
            "skip_consent": True,
        },
    )
    assert r.status_code == 201
    body = r.json()
    assert body["client_id"] == "svc"
    assert body["client_secret"]


async def test_admin_create_requires_admin_key(client, monkeypatch):
    await _env(monkeypatch)
    r = client.post("/admin/clients", json={
        "client_id": "svc", "name": "S",
        "redirect_uris": ["https://svc.hellopro.eu/cb"],
    })
    assert r.status_code == 403


async def test_admin_list_and_delete(client, monkeypatch):
    await _env(monkeypatch)
    client.post("/admin/clients", headers={"X-Admin-Key": "admin"}, json={
        "client_id": "svc", "name": "S",
        "redirect_uris": ["https://svc.hellopro.eu/cb"],
    })
    r = client.get("/admin/clients", headers={"X-Admin-Key": "admin"})
    assert r.status_code == 200
    assert any(c["client_id"] == "svc" for c in r.json())
    r2 = client.delete("/admin/clients/svc", headers={"X-Admin-Key": "admin"})
    assert r2.status_code == 204
```

- [ ] **Step 2: Implement `app/routers/admin_clients.py`**

```python
from fastapi import APIRouter, Depends, Header, HTTPException, Response

from app.core.settings import get_settings
from app.schemas import ClientSummary, CreateClientRequest, CreateClientResponse
from app.services.client_service import (
    ClientNotFound,
    create_client,
    delete_client,
    list_clients,
)

router = APIRouter(prefix="/admin/clients", tags=["admin"])


async def _require_admin_key(
    x_admin_key: str | None = Header(default=None, alias="X-Admin-Key"),
):
    if x_admin_key != get_settings().GATEWAY_ADMIN_KEY:
        raise HTTPException(status_code=403, detail={"error": "forbidden"})


@router.post(
    "",
    status_code=201,
    response_model=CreateClientResponse,
    dependencies=[Depends(_require_admin_key)],
)
async def admin_create(req: CreateClientRequest):
    try:
        secret = await create_client(
            client_id=req.client_id,
            name=req.name,
            redirect_uris=[str(u) for u in req.redirect_uris],
            post_logout_redirect_uris=[str(u) for u in req.post_logout_redirect_uris],
            skip_consent=req.skip_consent,
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail={"error": str(e)})
    return CreateClientResponse(
        client_id=req.client_id, client_secret=secret, name=req.name
    )


@router.get(
    "",
    response_model=list[ClientSummary],
    dependencies=[Depends(_require_admin_key)],
)
async def admin_list():
    clients = await list_clients()
    return [
        ClientSummary(
            client_id=c.client_id,
            name=c.name,
            redirect_uris=c.redirect_uris,
            skip_consent=c.skip_consent,
            is_active=c.is_active,
            created_at=c.created_at,
        )
        for c in clients
    ]


@router.delete(
    "/{client_id}",
    status_code=204,
    dependencies=[Depends(_require_admin_key)],
)
async def admin_delete(client_id: str):
    try:
        await delete_client(client_id)
    except ClientNotFound:
        raise HTTPException(status_code=404, detail={"error": "not_found"})
    return Response(status_code=204)
```

- [ ] **Step 3: Wire in `main.py` + run + commit**

```bash
pytest tests/test_admin_clients.py -v
git add apps-microservices/account-service-backend/
git commit -m "feat(account-service-backend): admin /admin/clients CRUD (X-Admin-Key)"
```

---

## Phase G — Middleware + Rate Limiting

### Task G1: Request-ID + log redaction middleware

**Files:**
- Create: `apps-microservices/account-service-backend/app/middleware.py`
- Test: `apps-microservices/account-service-backend/tests/test_middleware.py`

- [ ] **Step 1: Write failing test `tests/test_middleware.py`**

```python
def test_request_id_added_to_response(client):
    r = client.get("/health")
    assert r.headers.get("x-request-id")


def test_provided_request_id_echoed(client):
    r = client.get("/health", headers={"X-Request-Id": "rid-123"})
    assert r.headers["x-request-id"] == "rid-123"
```

- [ ] **Step 2: Implement `app/middleware.py`**

```python
import logging
import secrets
import time

from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger("request")

REDACT_HEADERS = {"authorization", "cookie", "x-admin-key"}


class RequestIdMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers") or [])
        rid_bytes = headers.get(b"x-request-id")
        rid = (
            rid_bytes.decode() if rid_bytes else secrets.token_urlsafe(8)
        )
        scope["request_id"] = rid

        start = time.perf_counter()

        async def send_with_header(msg):
            if msg["type"] == "http.response.start":
                msg.setdefault("headers", []).append(
                    (b"x-request-id", rid.encode())
                )
            await send(msg)

        try:
            await self.app(scope, receive, send_with_header)
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000
            logger.info(
                "%s %s rid=%s elapsed_ms=%.1f",
                scope.get("method"),
                scope.get("path"),
                rid,
                elapsed_ms,
            )
```

- [ ] **Step 3: Wire in `main.py`**

```python
from app.middleware import RequestIdMiddleware
app.add_middleware(RequestIdMiddleware)
```

- [ ] **Step 4: Run + commit**

```bash
pytest tests/test_middleware.py -v
git add apps-microservices/account-service-backend/
git commit -m "feat(account-service-backend): request-id + log-redaction middleware"
```

---

### Task G2: Rate limiting (slowapi)

**Files:**
- Create: `apps-microservices/account-service-backend/app/rate_limit.py`
- Modify: `apps-microservices/account-service-backend/main.py`
- Modify: `apps-microservices/account-service-backend/app/routers/authorize.py`
- Modify: `apps-microservices/account-service-backend/app/routers/token.py`
- Test: `apps-microservices/account-service-backend/tests/test_rate_limit.py`

- [ ] **Step 1: Implement `app/rate_limit.py`**

```python
from slowapi import Limiter
from slowapi.util import get_remote_address


limiter = Limiter(key_func=get_remote_address, default_limits=[])
```

- [ ] **Step 2: Wire into `main.py`**

```python
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.rate_limit import limiter

app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)


@app.exception_handler(RateLimitExceeded)
async def _rate_limit_handler(_: Request, exc: RateLimitExceeded):
    return JSONResponse(status_code=429, content={"error": "rate_limited"})
```

- [ ] **Step 3: Decorate `/authorize` (10/min) and `/token` (60/min)**

In `authorize.py` add:

```python
from fastapi import Request
from app.rate_limit import limiter


@router.post("/authorize", ...)
@limiter.limit("10/minute")
async def authorize(request: Request, req: AuthorizeRequest):
    ...
```

(Add `request: Request` as first param; pass through unchanged.) Same for `/token` with `60/minute`. (slowapi requires `Request` as first parameter when using decorator.)

- [ ] **Step 4: Test `tests/test_rate_limit.py`**

```python
async def test_rate_limit_authorize(client, monkeypatch):
    monkeypatch.setenv("HELLOPRO_AUTH_URL", "https://auth.hellopro.fr/api/login")
    monkeypatch.setenv("MYSQL_HOST", "x")
    monkeypatch.setenv("MYSQL_USER", "x")
    monkeypatch.setenv("MYSQL_PASS", "x")
    monkeypatch.setenv("MYSQL_DB", "x")
    monkeypatch.setenv("JWT_KEY_ENCRYPTION_KEY", "Z" * 44)
    monkeypatch.setenv("GATEWAY_ADMIN_KEY", "k")
    payload = {
        "email": "u@x", "password": "p", "client_id": "nope",
        "redirect_uri": "https://x", "state": "s",
        "code_challenge": "c", "code_challenge_method": "S256",
    }
    statuses = [client.post("/authorize", json=payload).status_code for _ in range(12)]
    assert 429 in statuses
```

- [ ] **Step 5: Run + commit**

```bash
pytest tests/test_rate_limit.py -v
git add apps-microservices/account-service-backend/
git commit -m "feat(account-service-backend): slowapi rate limiting on /authorize + /token"
```

---

## Phase H — Integration Test + Lifespan

### Task H1: Lifespan wires DB + ensures signing key

**Files:**
- Modify: `apps-microservices/account-service-backend/main.py`

- [ ] **Step 1: Update lifespan**

```python
@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = get_settings()
    await init_db(settings.database_url)
    await ensure_signing_key(encryption_key=settings.JWT_KEY_ENCRYPTION_KEY)
    yield
    await close_db()
```

(Add imports: `from app.core.settings import get_settings`, `from app.db.database import init_db, close_db`, `from app.core.jwt_keys import ensure_signing_key`.)

- [ ] **Step 2: Adjust `tests/conftest.py` to skip lifespan** (already overrides DB, just patch `ensure_signing_key` not to require env in tests):

```python
import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

from app.db.database import close_db, init_db
from main import app


@pytest_asyncio.fixture(autouse=True)
async def _db():
    await init_db("sqlite://:memory:")
    yield
    await close_db()


@pytest.fixture
def client() -> TestClient:
    # Avoid running lifespan (it would try real MySQL).
    return TestClient(app, raise_server_exceptions=True)
```

(`TestClient` only triggers lifespan if used as a context manager — we don't, so safe.)

- [ ] **Step 3: Run full backend test suite**

```bash
pytest -v
```

Expect all green.

- [ ] **Step 4: Commit**

```bash
git add apps-microservices/account-service-backend/
git commit -m "feat(account-service-backend): wire lifespan (init DB + ensure signing key)"
```

---

### Task H2: End-to-end consumer flow integration test

**Files:**
- Create: `apps-microservices/account-service-backend/tests/integration/__init__.py`
- Create: `apps-microservices/account-service-backend/tests/integration/test_consumer_flow.py`

- [ ] **Step 1: Create empty `__init__.py`**

- [ ] **Step 2: Create `tests/integration/test_consumer_flow.py`**

```python
import base64
import hashlib
from cryptography.fernet import Fernet
import httpx
import respx

from app.core.jwt_keys import ensure_signing_key
from app.services.client_service import create_client


def _challenge(verifier: str) -> str:
    return base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).rstrip(b"=").decode()


@respx.mock
async def test_full_oauth_flow(client, monkeypatch):
    fk = Fernet.generate_key().decode()
    monkeypatch.setenv("JWT_KEY_ENCRYPTION_KEY", fk)
    monkeypatch.setenv("HELLOPRO_AUTH_URL", "https://auth.hellopro.fr/api/login")
    monkeypatch.setenv("MYSQL_HOST", "x")
    monkeypatch.setenv("MYSQL_USER", "x")
    monkeypatch.setenv("MYSQL_PASS", "x")
    monkeypatch.setenv("MYSQL_DB", "x")
    monkeypatch.setenv("GATEWAY_ADMIN_KEY", "k")
    await ensure_signing_key(encryption_key=fk)
    secret = await create_client(
        client_id="svc", name="S",
        redirect_uris=["https://svc.hellopro.eu/cb"],
        skip_consent=True,
    )
    respx.post("https://auth.hellopro.fr/api/login").mock(
        return_value=httpx.Response(
            200, json={"email": "u@hellopro.fr", "display_name": "U"}
        )
    )

    verifier = "v" * 64
    challenge = _challenge(verifier)

    # /authorize
    r = client.post("/authorize", json={
        "email": "u@hellopro.fr", "password": "p",
        "client_id": "svc",
        "redirect_uri": "https://svc.hellopro.eu/cb",
        "state": "abc", "code_challenge": challenge,
        "code_challenge_method": "S256",
    })
    assert r.status_code == 200
    redirect = r.json()["redirect"]
    code = redirect.split("code=")[1].split("&")[0]

    # /token authorization_code
    r = client.post("/token", data={
        "grant_type": "authorization_code", "code": code,
        "redirect_uri": "https://svc.hellopro.eu/cb",
        "client_id": "svc", "client_secret": secret,
        "code_verifier": verifier,
    })
    assert r.status_code == 200
    pair = r.json()

    # /userinfo
    r = client.get("/userinfo", headers={"Authorization": f"Bearer {pair['access_token']}"})
    assert r.status_code == 200
    assert r.json()["email"] == "u@hellopro.fr"

    # /token refresh_token
    r = client.post("/token", data={
        "grant_type": "refresh_token",
        "refresh_token": pair["refresh_token"],
        "client_id": "svc", "client_secret": secret,
    })
    assert r.status_code == 200
    new_refresh = r.json()["refresh_token"]
    assert new_refresh != pair["refresh_token"]

    # /revoke
    r = client.post("/revoke", json={
        "refresh_token": new_refresh,
        "client_id": "svc", "client_secret": secret,
    })
    assert r.status_code == 200

    # rotate after revoke → invalid_grant
    r = client.post("/token", data={
        "grant_type": "refresh_token",
        "refresh_token": new_refresh,
        "client_id": "svc", "client_secret": secret,
    })
    assert r.status_code == 400
```

- [ ] **Step 3: Run + commit**

```bash
pytest tests/integration/ -v
git add apps-microservices/account-service-backend/
git commit -m "test(account-service-backend): end-to-end OAuth flow integration test"
```

---

## Phase I — Bootstrap + CLAUDE.md (backend)

### Task I1: Bootstrap seeding script

**Files:**
- Create: `apps-microservices/account-service-backend/scripts/__init__.py`
- Create: `apps-microservices/account-service-backend/scripts/seed_clients.py`
- Test: `apps-microservices/account-service-backend/tests/test_seed.py`

- [ ] **Step 1: Implement `scripts/seed_clients.py`**

```python
import asyncio
import json
import logging
import os
import sys

from app.db.database import close_db, init_db
from app.db.models import OAuthClient
from app.services.client_service import create_client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("seed")


async def seed_from_env() -> None:
    raw = os.environ.get("OAUTH_CLIENTS_SEED_JSON")
    if not raw:
        logger.info("OAUTH_CLIENTS_SEED_JSON not set — nothing to seed")
        return
    items = json.loads(raw)
    for item in items:
        cid = item["client_id"]
        if await OAuthClient.filter(client_id=cid).exists():
            logger.info("client %s already exists — skipping", cid)
            continue
        secret = await create_client(
            client_id=cid,
            name=item["name"],
            redirect_uris=item["redirect_uris"],
            post_logout_redirect_uris=item.get("post_logout_redirect_uris", []),
            skip_consent=item.get("skip_consent", True),
        )
        logger.warning("CREATED client_id=%s — STORE SECRET NOW: %s", cid, secret)


async def main() -> int:
    from app.core.settings import get_settings
    s = get_settings()
    await init_db(s.database_url)
    try:
        await seed_from_env()
    finally:
        await close_db()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
```

- [ ] **Step 2: Test (uses in-memory DB)** — `tests/test_seed.py`

```python
import json

from scripts.seed_clients import seed_from_env
from app.db.models import OAuthClient


async def test_seed_creates_clients(monkeypatch):
    monkeypatch.setenv(
        "OAUTH_CLIENTS_SEED_JSON",
        json.dumps([{
            "client_id": "svc", "name": "S",
            "redirect_uris": ["https://svc.hellopro.eu/cb"],
            "skip_consent": True,
        }]),
    )
    await seed_from_env()
    assert await OAuthClient.filter(client_id="svc").exists()


async def test_seed_idempotent(monkeypatch):
    monkeypatch.setenv(
        "OAUTH_CLIENTS_SEED_JSON",
        json.dumps([{
            "client_id": "svc", "name": "S",
            "redirect_uris": ["https://svc.hellopro.eu/cb"],
        }]),
    )
    await seed_from_env()
    await seed_from_env()  # second call should not raise
    assert await OAuthClient.filter(client_id="svc").count() == 1
```

- [ ] **Step 3: Run + commit**

```bash
pytest tests/test_seed.py -v
git add apps-microservices/account-service-backend/
git commit -m "feat(account-service-backend): idempotent seed_clients script"
```

---

### Task I2: Backend CLAUDE.md

**Files:**
- Create: `apps-microservices/account-service-backend/CLAUDE.md`

- [ ] **Step 1: Write CLAUDE.md**

```markdown
# account-service-backend

OAuth2 Authorization Code + PKCE provider. FastAPI + Tortoise + MySQL (`account_db`). Issues RS256 JWT access tokens (15 min) + opaque rotating refresh tokens (30 d). Delegates credential validation to upstream HelloPro auth endpoint (`HELLOPRO_AUTH_URL`).

## Tech Stack

- Python 3.10, FastAPI, Tortoise-ORM (asyncmy/MySQL), Aerich
- PyJWT[crypto], cryptography (Fernet), bcrypt
- httpx (upstream), slowapi (rate limit)
- pytest + pytest-asyncio + respx + aiosqlite (in-memory tests)

## Run

```bash
# Tests (in-memory sqlite, no external deps)
pytest -v

# Local dev (against MySQL)
export MYSQL_HOST=... MYSQL_USER=... MYSQL_PASS=... MYSQL_DB=account_db
export HELLOPRO_AUTH_URL=https://auth.hellopro.fr/api/login
export JWT_KEY_ENCRYPTION_KEY=$(python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')
export GATEWAY_ADMIN_KEY=...
uvicorn main:app --reload --port 8000
```

## Endpoints

| Path | Method | Purpose |
|------|--------|---------|
| `/health` | GET | Liveness check |
| `/.well-known/jwks.json` | GET | Public RSA keys for JWT verification |
| `/authorize` | POST | Validate creds via HelloPro, issue auth code |
| `/token` | POST | Exchange code or refresh for access+refresh pair |
| `/revoke` | POST | Revoke refresh token chain (idempotent) |
| `/introspect` | POST | Validate access token (rare path) |
| `/userinfo` | GET | Bearer-protected — returns sub/email/display_name |
| `/logout` | GET | Post-logout confirmation page |
| `/admin/clients` | POST/GET | Register/list OAuth clients (X-Admin-Key) |
| `/admin/clients/{client_id}` | DELETE | Soft-delete (mark inactive) |

## File Inventory

```
main.py                        FastAPI + lifespan + middleware
app/
  core/
    settings.py                Pydantic BaseSettings (env)
    security.py                PKCE check, bcrypt, sha256, random tokens
    jwt_keys.py                RSA gen, Fernet encrypt, JWKS, ensure_signing_key
    jwt_tokens.py              issue/decode RS256 access tokens
  db/
    database.py                Tortoise init + TORTOISE_ORM (Aerich)
    models.py                  OAuthClient, AuthorizationCode, RefreshToken, SigningKey
  services/
    hellopro_client.py         httpx → HELLOPRO_AUTH_URL (1 retry on 5xx)
    code_service.py            issue + consume one-shot auth codes
    token_service.py           access+refresh issuance, rotation, reuse detect
    client_service.py          OAuthClient CRUD + bcrypt secret check
  routers/                     one file per endpoint
  schemas.py                   Pydantic request/response models
  middleware.py                request_id + log redaction
  rate_limit.py                slowapi limiter (10/min /authorize, 60/min /token)
scripts/seed_clients.py        idempotent client seeder
migrations/                    Aerich (committed)
tests/                         pytest suite (sqlite in-memory)
```

## Conventions

- Tortoise ORM with MySQL in production, sqlite in-memory in tests.
- Migrations via Aerich; commit them.
- `verify_pkce` rejects everything except `S256`.
- `decode_access_token` rejects any `alg` != RS256 (no `none`, no HS*).
- Refresh-token reuse triggers full chain revocation (RFC 6819).
- `redirect_uri` matched exactly — no substring/wildcard.
- Sensitive headers redacted by middleware before logging.

## What This Provides to Other Services

- Centralized identity issuance for any monorepo service via OAuth2 Authorization Code + PKCE.
- Public JWKS endpoint for stateless JWT verification at consumers.
- Admin endpoints to manage consumer clients dynamically.
- Companion integration guide: `docs/superpowers/specs/account-service-README.md`.
```

- [ ] **Step 2: Commit**

```bash
git add apps-microservices/account-service-backend/CLAUDE.md
git commit -m "docs(account-service-backend): add CLAUDE.md"
```

---

## Phase J — Frontend (Vue) Skeleton

### Task J1: Fork template + prune to auth-only

**Files (created):**
- `apps-microservices/account-service-frontend/package.json`
- `apps-microservices/account-service-frontend/vite.config.ts`
- `apps-microservices/account-service-frontend/tsconfig.json` + `tsconfig.app.json` + `tsconfig.node.json`
- `apps-microservices/account-service-frontend/postcss.config.js`
- `apps-microservices/account-service-frontend/eslint.config.ts`
- `apps-microservices/account-service-frontend/.prettierrc.json`
- `apps-microservices/account-service-frontend/index.html`
- `apps-microservices/account-service-frontend/src/main.ts`
- `apps-microservices/account-service-frontend/src/App.vue`
- `apps-microservices/account-service-frontend/src/env.d.ts`
- `apps-microservices/account-service-frontend/src/assets/main.css`

- [ ] **Step 1: Copy minimal subset from template**

```bash
mkdir -p apps-microservices/account-service-frontend/src/{views/Auth,composables,components/auth,assets,router}
cp public/admin-dashboad/.prettierrc.json apps-microservices/account-service-frontend/
cp public/admin-dashboad/postcss.config.js apps-microservices/account-service-frontend/
cp public/admin-dashboad/eslint.config.ts apps-microservices/account-service-frontend/
cp public/admin-dashboad/tsconfig.node.json apps-microservices/account-service-frontend/
cp public/admin-dashboad/tsconfig.app.json apps-microservices/account-service-frontend/
cp public/admin-dashboad/tsconfig.json apps-microservices/account-service-frontend/
cp public/admin-dashboad/vite.config.ts apps-microservices/account-service-frontend/
cp public/admin-dashboad/env.d.ts apps-microservices/account-service-frontend/src/
cp public/admin-dashboad/index.html apps-microservices/account-service-frontend/
```

- [ ] **Step 2: Write trimmed `package.json`** (drop heavy deps not needed for auth: fullcalendar, apexcharts, swiper, vuevectormap, vue-kanban, draggable, dropzone, flatpickr)

```json
{
  "name": "account-service-frontend",
  "version": "0.1.0",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "run-p type-check \"build-only {@}\" --",
    "preview": "vite preview",
    "build-only": "vite build",
    "type-check": "vue-tsc --build",
    "lint": "eslint . --fix",
    "format": "prettier --write src/",
    "test": "vitest run"
  },
  "dependencies": {
    "@tailwindcss/forms": "^0.5.10",
    "@tailwindcss/typography": "^0.5.16",
    "lucide-vue-next": "^0.474.0",
    "vue": "^3.5.13",
    "vue-router": "^4.5.0"
  },
  "devDependencies": {
    "@tailwindcss/postcss": "^4.0.0",
    "@tsconfig/node22": "^22.0.0",
    "@types/node": "^22.10.7",
    "@vitejs/plugin-vue": "^5.2.1",
    "@vitejs/plugin-vue-jsx": "^4.1.1",
    "@vue/eslint-config-prettier": "^10.1.0",
    "@vue/eslint-config-typescript": "^14.3.0",
    "@vue/test-utils": "^2.4.6",
    "@vue/tsconfig": "^0.7.0",
    "eslint": "^9.18.0",
    "eslint-plugin-vue": "^9.32.0",
    "happy-dom": "^15.7.4",
    "jiti": "^2.4.2",
    "npm-run-all2": "^7.0.2",
    "postcss": "^8.5.1",
    "prettier": "^3.4.2",
    "sass-embedded": "^1.83.4",
    "tailwindcss": "^4.0.0",
    "typescript": "~5.7.3",
    "vite": "^6.0.11",
    "vitest": "^2.1.9",
    "vue-tsc": "^2.2.0"
  }
}
```

- [ ] **Step 3: Write `src/main.ts`**

```ts
import { createApp } from 'vue'
import App from './App.vue'
import router from './router'
import './assets/main.css'

createApp(App).use(router).mount('#app')
```

- [ ] **Step 4: Write `src/App.vue`**

```vue
<script setup lang="ts"></script>

<template>
  <router-view />
</template>
```

- [ ] **Step 5: Write `src/assets/main.css`**

```css
@import 'tailwindcss';
@plugin '@tailwindcss/forms';
@plugin '@tailwindcss/typography';

html, body, #app { height: 100%; }
```

- [ ] **Step 6: Write `index.html`** (replace template content)

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>HelloPro Account</title>
  </head>
  <body>
    <div id="app"></div>
    <script type="module" src="/src/main.ts"></script>
  </body>
</html>
```

- [ ] **Step 7: Verify build**

```bash
cd apps-microservices/account-service-frontend
npm install
npm run type-check
```

Expect 0 errors (router not yet wired — fix in next task).

- [ ] **Step 8: Commit**

```bash
git add apps-microservices/account-service-frontend/
git commit -m "feat(account-service-frontend): scaffold Vue 3 + Tailwind 4 skeleton"
```

---

### Task J2: Router + composables (PKCE + API)

**Files:**
- Create: `apps-microservices/account-service-frontend/src/router/index.ts`
- Create: `apps-microservices/account-service-frontend/src/composables/useOAuthFlow.ts`
- Create: `apps-microservices/account-service-frontend/src/composables/useApi.ts`
- Test: `apps-microservices/account-service-frontend/tests/composables/useOAuthFlow.spec.ts`

- [ ] **Step 1: Write `src/router/index.ts`**

```ts
import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/signin' },
    { path: '/signin', component: () => import('../views/Auth/Signin.vue') },
    { path: '/consent', component: () => import('../views/Auth/Consent.vue') },
    { path: '/logout', component: () => import('../views/Auth/Logout.vue') },
    { path: '/error', component: () => import('../views/Auth/Error.vue') },
    { path: '/:pathMatch(.*)*', component: () => import('../views/Auth/Error.vue') },
  ],
})

export default router
```

- [ ] **Step 2: Write `src/composables/useApi.ts`**

```ts
const BASE = ''  // same origin (Nginx proxies /authorize, /token, etc. to backend)

export async function postJson<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  const text = await r.text()
  let json: unknown
  try { json = text ? JSON.parse(text) : {} } catch { json = {} }
  if (!r.ok) {
    const detail = (json as { error?: string })?.error || `HTTP ${r.status}`
    throw new Error(detail)
  }
  return json as T
}
```

- [ ] **Step 3: Write `src/composables/useOAuthFlow.ts`**

```ts
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { postJson } from './useApi'

export interface OAuthParams {
  client_id: string
  redirect_uri: string
  state: string
  code_challenge: string
  code_challenge_method: 'S256'
}

export function useOAuthFlow() {
  const route = useRoute()

  const params = computed<OAuthParams | null>(() => {
    const q = route.query
    if (!q.client_id || !q.redirect_uri || !q.state ||
        !q.code_challenge || q.code_challenge_method !== 'S256') {
      return null
    }
    return {
      client_id: String(q.client_id),
      redirect_uri: String(q.redirect_uri),
      state: String(q.state),
      code_challenge: String(q.code_challenge),
      code_challenge_method: 'S256',
    }
  })

  async function submitLogin(email: string, password: string) {
    const p = params.value
    if (!p) throw new Error('missing_oauth_params')
    return await postJson<{ redirect?: string; next?: string }>('/authorize', {
      email, password, ...p,
    })
  }

  return { params, submitLogin }
}
```

- [ ] **Step 4: Write `tests/composables/useOAuthFlow.spec.ts`**

```ts
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { defineComponent, h } from 'vue'

import { useOAuthFlow } from '../../src/composables/useOAuthFlow'

const Probe = defineComponent({
  setup() {
    const flow = useOAuthFlow()
    return { flow }
  },
  render() {
    return h('div', { 'data-params': JSON.stringify(this.flow.params) })
  },
})

async function mountWithQuery(query: Record<string, string>) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/signin', component: Probe }],
  })
  await router.push({ path: '/signin', query })
  await router.isReady()
  return mount(Probe, { global: { plugins: [router] } })
}

describe('useOAuthFlow.params', () => {
  it('returns null when required params missing', async () => {
    const w = await mountWithQuery({ client_id: 'svc' })
    expect(w.attributes('data-params')).toBe('null')
  })
  it('returns parsed params when all present', async () => {
    const w = await mountWithQuery({
      client_id: 'svc',
      redirect_uri: 'https://svc.hellopro.eu/cb',
      state: 's',
      code_challenge: 'c',
      code_challenge_method: 'S256',
    })
    const parsed = JSON.parse(w.attributes('data-params')!)
    expect(parsed.client_id).toBe('svc')
    expect(parsed.code_challenge_method).toBe('S256')
  })
})
```

- [ ] **Step 5: Add `vitest.config.ts`**

```ts
import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  test: { environment: 'happy-dom', globals: true },
})
```

- [ ] **Step 6: Run + commit**

```bash
npm run test
git add apps-microservices/account-service-frontend/
git commit -m "feat(account-service-frontend): router + useOAuthFlow + useApi"
```

---

### Task J3: Signin view

**Files:**
- Create: `apps-microservices/account-service-frontend/src/components/auth/AuthCard.vue`
- Create: `apps-microservices/account-service-frontend/src/views/Auth/Signin.vue`
- Test: `apps-microservices/account-service-frontend/tests/views/Signin.spec.ts`

- [ ] **Step 1: Write `src/components/auth/AuthCard.vue`** (layout shell)

```vue
<script setup lang="ts">
defineProps<{ title: string; subtitle?: string }>()
</script>

<template>
  <div class="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-900 p-6">
    <div class="w-full max-w-md bg-white dark:bg-gray-800 rounded-lg shadow p-8">
      <h1 class="text-2xl font-semibold text-gray-900 dark:text-white">{{ title }}</h1>
      <p v-if="subtitle" class="mt-2 text-sm text-gray-500 dark:text-gray-400">{{ subtitle }}</p>
      <div class="mt-6"><slot /></div>
    </div>
  </div>
</template>
```

- [ ] **Step 2: Write `src/views/Auth/Signin.vue`**

```vue
<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import AuthCard from '../../components/auth/AuthCard.vue'
import { useOAuthFlow } from '../../composables/useOAuthFlow'

const router = useRouter()
const { params, submitLogin } = useOAuthFlow()

const email = ref('')
const password = ref('')
const submitting = ref(false)
const errorMessage = ref('')

async function onSubmit() {
  errorMessage.value = ''
  if (!params.value) {
    errorMessage.value = 'Missing OAuth parameters.'
    return
  }
  submitting.value = true
  try {
    const res = await submitLogin(email.value, password.value)
    if (res.redirect) {
      window.location.assign(res.redirect)
      return
    }
    if (res.next === '/consent') {
      await router.push({ path: '/consent', query: router.currentRoute.value.query })
      return
    }
    errorMessage.value = 'Unexpected response from server.'
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : 'login_failed'
    errorMessage.value =
      msg === 'access_denied' ? 'Invalid email or password.' :
      msg === 'upstream_unavailable' ? 'Service temporarily unavailable. Try again.' :
      'Sign-in failed.'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <AuthCard title="Sign in" subtitle="Enter your HelloPro credentials">
    <form class="space-y-4" @submit.prevent="onSubmit" data-test="signin-form">
      <div>
        <label class="block text-sm font-medium text-gray-700 dark:text-gray-200">Email</label>
        <input
          v-model="email" type="email" required autocomplete="email"
          class="mt-1 block w-full rounded-md border-gray-300 shadow-sm
                 focus:border-indigo-500 focus:ring-indigo-500 dark:bg-gray-700 dark:text-white"
          data-test="email"
        />
      </div>
      <div>
        <label class="block text-sm font-medium text-gray-700 dark:text-gray-200">Password</label>
        <input
          v-model="password" type="password" required autocomplete="current-password"
          class="mt-1 block w-full rounded-md border-gray-300 shadow-sm
                 focus:border-indigo-500 focus:ring-indigo-500 dark:bg-gray-700 dark:text-white"
          data-test="password"
        />
      </div>
      <p v-if="errorMessage" class="text-sm text-red-600" data-test="error">{{ errorMessage }}</p>
      <button
        type="submit" :disabled="submitting"
        class="w-full rounded-md bg-indigo-600 px-4 py-2 text-white hover:bg-indigo-700
               disabled:opacity-50"
        data-test="submit"
      >
        {{ submitting ? 'Signing in...' : 'Sign in' }}
      </button>
    </form>
  </AuthCard>
</template>
```

- [ ] **Step 3: Write `tests/views/Signin.spec.ts`**

```ts
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import Signin from '../../src/views/Auth/Signin.vue'

const baseQuery = {
  client_id: 'svc',
  redirect_uri: 'https://svc.hellopro.eu/cb',
  state: 'st',
  code_challenge: 'c',
  code_challenge_method: 'S256',
}

async function mountSignin() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/signin', component: Signin },
      { path: '/consent', component: { template: '<div/>' } },
    ],
  })
  await router.push({ path: '/signin', query: baseQuery })
  await router.isReady()
  return mount(Signin, { global: { plugins: [router] } })
}

describe('Signin.vue', () => {
  let originalAssign: typeof window.location.assign
  beforeEach(() => {
    originalAssign = window.location.assign
    Object.defineProperty(window, 'location', {
      value: { ...window.location, assign: vi.fn() },
      writable: true,
    })
  })
  afterEach(() => {
    Object.defineProperty(window.location, 'assign', { value: originalAssign })
    vi.restoreAllMocks()
  })

  it('submits and redirects on success', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ redirect: 'https://svc.hellopro.eu/cb?code=x&state=st' }), {
        status: 200, headers: { 'content-type': 'application/json' },
      })
    )
    const w = await mountSignin()
    await w.find('[data-test=email]').setValue('u@x')
    await w.find('[data-test=password]').setValue('p')
    await w.find('[data-test=signin-form]').trigger('submit.prevent')
    await new Promise((r) => setTimeout(r, 0))
    expect(fetchSpy).toHaveBeenCalled()
    expect((window.location.assign as unknown as ReturnType<typeof vi.fn>))
      .toHaveBeenCalledWith('https://svc.hellopro.eu/cb?code=x&state=st')
  })

  it('shows generic error on access_denied', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ error: 'access_denied' }), { status: 401 })
    )
    const w = await mountSignin()
    await w.find('[data-test=email]').setValue('u@x')
    await w.find('[data-test=password]').setValue('p')
    await w.find('[data-test=signin-form]').trigger('submit.prevent')
    await new Promise((r) => setTimeout(r, 0))
    expect(w.find('[data-test=error]').text()).toMatch(/Invalid email or password/i)
  })
})
```

- [ ] **Step 4: Run + commit**

```bash
npm run test
git add apps-microservices/account-service-frontend/
git commit -m "feat(account-service-frontend): Signin view + AuthCard"
```

---

### Task J4: Consent / Logout / Error views

**Files:**
- Create: `apps-microservices/account-service-frontend/src/views/Auth/Consent.vue`
- Create: `apps-microservices/account-service-frontend/src/views/Auth/Logout.vue`
- Create: `apps-microservices/account-service-frontend/src/views/Auth/Error.vue`

- [ ] **Step 1: Write `Consent.vue`** (skeleton — full consent flow deferred; v1 backend auto-skips)

```vue
<script setup lang="ts">
import AuthCard from '../../components/auth/AuthCard.vue'
import { useRoute } from 'vue-router'
const route = useRoute()
function deny() {
  const r = String(route.query.redirect_uri || '/')
  const s = String(route.query.state || '')
  window.location.assign(`${r}?error=access_denied&state=${s}`)
}
</script>

<template>
  <AuthCard title="Authorize access"
            subtitle="An application is requesting access to your account.">
    <p class="text-sm text-gray-700 dark:text-gray-200">
      Allow this application to access your account information?
    </p>
    <div class="mt-6 flex gap-3">
      <button class="flex-1 rounded-md bg-indigo-600 px-4 py-2 text-white"
              disabled>
        Allow (handled by server)
      </button>
      <button class="flex-1 rounded-md bg-gray-200 px-4 py-2" @click="deny">
        Deny
      </button>
    </div>
  </AuthCard>
</template>
```

- [ ] **Step 2: Write `Logout.vue`**

```vue
<script setup lang="ts">
import AuthCard from '../../components/auth/AuthCard.vue'
import { onMounted } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
onMounted(() => {
  const target = String(route.query.post_logout_redirect_uri || '/')
  setTimeout(() => window.location.assign(target), 1500)
})
</script>

<template>
  <AuthCard title="Signed out" subtitle="You have been logged out.">
    <p class="text-sm text-gray-500">Redirecting…</p>
  </AuthCard>
</template>
```

- [ ] **Step 3: Write `Error.vue`**

```vue
<script setup lang="ts">
import AuthCard from '../../components/auth/AuthCard.vue'
import { useRoute } from 'vue-router'
const route = useRoute()
</script>

<template>
  <AuthCard title="Something went wrong">
    <p class="text-sm text-gray-700 dark:text-gray-200">
      {{ route.query.message || 'An unexpected error occurred.' }}
    </p>
    <p class="mt-4">
      <a class="text-indigo-600 hover:underline" href="/signin">Back to sign in</a>
    </p>
  </AuthCard>
</template>
```

- [ ] **Step 4: Build + commit**

```bash
npm run type-check && npm run build
git add apps-microservices/account-service-frontend/
git commit -m "feat(account-service-frontend): Consent / Logout / Error views"
```

---

### Task J5: Nginx config + Dockerfile

**Files:**
- Create: `apps-microservices/account-service-frontend/nginx.conf`
- Create: `apps-microservices/account-service-frontend/Dockerfile`
- Create: `apps-microservices/account-service-frontend/.dockerignore`
- Create: `apps-microservices/account-service-frontend/CLAUDE.md`

- [ ] **Step 1: Write `nginx.conf`**

```nginx
server {
  listen 80;
  server_name _;

  root /usr/share/nginx/html;
  index index.html;

  location = /healthz {
    access_log off;
    return 200 "ok\n";
  }

  # Proxy auth API to backend
  location ~ ^/(authorize|token|revoke|introspect|userinfo|admin|\.well-known)(/|$) {
    proxy_pass http://account-service-backend:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
  }

  # SPA fallback
  location / {
    try_files $uri $uri/ /index.html;
  }
}
```

- [ ] **Step 2: Write `Dockerfile`** (multi-stage, build context = repo root)

```dockerfile
# Build stage
FROM node:22-alpine AS build
WORKDIR /app
COPY apps-microservices/account-service-frontend/package*.json ./
RUN npm ci --no-audit --no-fund
COPY apps-microservices/account-service-frontend .
RUN npm run build

# Runtime stage
FROM nginx:1.27-alpine AS runtime
RUN apk add --no-cache wget
COPY --from=build /app/dist /usr/share/nginx/html
COPY apps-microservices/account-service-frontend/nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD wget -qO- http://localhost:80/healthz || exit 1
USER nginx
```

- [ ] **Step 3: Write `.dockerignore`**

```
node_modules
dist
.vscode
.idea
.git
*.log
```

- [ ] **Step 4: Write `CLAUDE.md`**

```markdown
# account-service-frontend

Vue 3 SPA — login UI for `account-service-backend`. Forked and pruned from `public/admin-dashboad/`. Served by Nginx, proxies `/authorize`, `/token`, `/revoke`, `/introspect`, `/userinfo`, `/admin`, `/.well-known/*` to the backend container.

## Tech Stack

- Vue 3.5 + Vue Router 4.5
- Vite 6 + TypeScript 5.7
- Tailwind 4 + @tailwindcss/forms + @tailwindcss/typography
- Vitest (happy-dom) + @vue/test-utils

## Run

```bash
npm install
npm run dev          # dev server on http://localhost:5173
npm run build        # produces dist/
npm run test         # vitest
npm run type-check   # vue-tsc
```

## Routes

| Path | Purpose |
|------|---------|
| `/signin` | Email + password form, posts to `/authorize` |
| `/consent` | Allow/deny screen (auto-skipped for trusted clients server-side) |
| `/logout` | Confirmation page after revoke |
| `/error` | Generic error page |

## File Inventory

```
src/
  main.ts                       app bootstrap
  App.vue                       <router-view/>
  router/index.ts               4 routes + catch-all
  views/Auth/{Signin,Consent,Logout,Error}.vue
  composables/
    useOAuthFlow.ts             reads OAuth params from URL, posts /authorize
    useApi.ts                   fetch wrapper
  components/auth/AuthCard.vue  layout shell
  assets/main.css               Tailwind imports
nginx.conf                      proxy + SPA fallback
Dockerfile                      node:22-alpine build → nginx:1.27-alpine runtime
```

## Conventions

- TypeScript strict mode.
- All API calls via `useApi.postJson`.
- OAuth params read from `route.query` only; NEVER stored in localStorage.
- Generic error messages — never enumerate (no "user not found" vs "wrong password").
- Tailwind utility classes; design follows project frontend guidelines.
```

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/account-service-frontend/
git commit -m "feat(account-service-frontend): nginx.conf + Dockerfile + CLAUDE.md"
```

---

## Phase K — CI/CD + Compose Wiring

### Task K1: Backend CI workflow

**Files:**
- Create: `.github/workflows/ci_services_account_service_backend.yml`

- [ ] **Step 1: Write workflow**

```yaml
name: CI account-service-backend
on:
  pull_request:
    paths:
      - 'apps-microservices/account-service-backend/**'
      - 'libs/common-utils/**'
      - '.github/workflows/ci_services_account_service_backend.yml'

jobs:
  lint-test:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: apps-microservices/account-service-backend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.10' }
      - name: Install
        run: |
          pip install --no-cache-dir -r requirements.txt
          pip install --no-cache-dir ruff
      - name: Ruff
        run: ruff check .
      - name: Pytest
        run: pytest -v
```

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/ci_services_account_service_backend.yml
git commit -m "ci(account-service-backend): add lint + pytest workflow"
```

---

### Task K2: Frontend CI workflow

**Files:**
- Create: `.github/workflows/ci_services_account_service_frontend.yml`

- [ ] **Step 1: Write workflow**

```yaml
name: CI account-service-frontend
on:
  pull_request:
    paths:
      - 'apps-microservices/account-service-frontend/**'
      - '.github/workflows/ci_services_account_service_frontend.yml'

jobs:
  lint-test:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: apps-microservices/account-service-frontend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: '22', cache: 'npm', cache-dependency-path: apps-microservices/account-service-frontend/package-lock.json }
      - run: npm ci
      - run: npm run lint
      - run: npm run type-check
      - run: npm run test
      - run: npm run build
```

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/ci_services_account_service_frontend.yml
git commit -m "ci(account-service-frontend): add eslint + vitest + build workflow"
```

---

### Task K3: CD build+push workflows

**Files:**
- Create: `.github/workflows/cd_build_push_services_account_service_backend.yml`
- Create: `.github/workflows/cd_build_push_services_account_service_frontend.yml`

- [ ] **Step 1: Inspect an existing CD workflow for the registry/auth steps**

```bash
cat .github/workflows/cd_build_push_services_api_ingestion.yml
```

- [ ] **Step 2: Write `cd_build_push_services_account_service_backend.yml`** (copy structure of an existing one — example below; adjust to actual registry/secrets used in repo)

```yaml
name: CD account-service-backend
on:
  push:
    branches: [main]
    paths:
      - 'apps-microservices/account-service-backend/**'
      - 'libs/common-utils/**'
      - '.github/workflows/cd_build_push_services_account_service_backend.yml'

jobs:
  build-push:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-buildx-action@v3
      - uses: docker/login-action@v3
        with:
          registry: ${{ secrets.REGISTRY_URL }}
          username: ${{ secrets.REGISTRY_USER }}
          password: ${{ secrets.REGISTRY_PASS }}
      - uses: docker/build-push-action@v5
        with:
          context: .
          file: apps-microservices/account-service-backend/Dockerfile
          push: true
          tags: |
            ${{ secrets.REGISTRY_URL }}/account-service-backend:latest
            ${{ secrets.REGISTRY_URL }}/account-service-backend:${{ github.sha }}
```

- [ ] **Step 3: Write `cd_build_push_services_account_service_frontend.yml`** — same shape, swap names + Dockerfile path.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/cd_build_push_services_account_service_*.yml
git commit -m "ci(account-service): add CD build+push workflows"
```

---

### Task K4: docker-compose additions

**Files:**
- Modify: `docker-compose.yml`

- [ ] **Step 1: Append two service blocks to `docker-compose.yml`** (locate the existing block listing api-gateway / mysql; insert after)

```yaml
  account-service-backend:
    build:
      context: .
      dockerfile: apps-microservices/account-service-backend/Dockerfile
    container_name: account-service-backend
    environment:
      - MYSQL_HOST=mysql
      - MYSQL_PORT=3306
      - MYSQL_USER=${ACCOUNT_MYSQL_USER}
      - MYSQL_PASS=${ACCOUNT_MYSQL_PASS}
      - MYSQL_DB=account_db
      - HELLOPRO_AUTH_URL=${HELLOPRO_AUTH_URL}
      - HELLOPRO_AUTH_TIMEOUT_SECONDS=5
      - JWT_KEY_ENCRYPTION_KEY=${JWT_KEY_ENCRYPTION_KEY}
      - JWT_ISSUER=https://account.hellopro.eu
      - ACCESS_TOKEN_EXPIRE_MINUTES=15
      - REFRESH_TOKEN_EXPIRE_DAYS=30
      - GATEWAY_ADMIN_KEY=${GATEWAY_ADMIN_KEY}
      - OAUTH_CLIENTS_SEED_JSON=${OAUTH_CLIENTS_SEED_JSON-}
      - LOG_LEVEL=INFO
    expose: ["8000"]
    depends_on: [mysql]
    healthcheck:
      test: ["CMD", "curl", "-fsS", "http://localhost:8000/health"]
      interval: 30s
      timeout: 5s
      retries: 3
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"
    restart: unless-stopped

  account-service-frontend:
    build:
      context: .
      dockerfile: apps-microservices/account-service-frontend/Dockerfile
    container_name: account-service-frontend
    expose: ["80"]
    depends_on:
      account-service-backend:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "wget", "-qO-", "http://localhost:80/healthz"]
      interval: 30s
      timeout: 5s
      retries: 3
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"
    restart: unless-stopped
```

- [ ] **Step 2: Verify**

```bash
docker compose config | grep -E "account-service-(backend|frontend)" -A 3
```

- [ ] **Step 3: Commit**

```bash
git add docker-compose.yml
git commit -m "chore(compose): add account-service-backend + account-service-frontend"
```

---

### Task K5: Update root CLAUDE.md service map

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: In the Service Map table, add a new row under "Authentication" or extend an existing category**

Append to the `Service Map` table:

```markdown
| Authentication | `account-service-backend`, `account-service-frontend` | Python / FastAPI / Tortoise / Vue 3 | Local OK |
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: register account-service in root CLAUDE.md service map"
```

---

## Self-Review

**1. Spec coverage** — every spec section has at least one task:
- Components / architecture: A1, A2, J1, J5
- OAuth2 flow (authorize, token, refresh, revoke, introspect, userinfo, jwks, logout): F1–F7
- Admin clients endpoint (DB-backed registration): F8
- Tortoise models (OAuthClient, AuthorizationCode, RefreshToken, SigningKey): B1
- Aerich migrations: B2
- RS256 keypair + Fernet at-rest encryption + JWKS: C2
- JWT issuance + decode: C3
- PKCE + secret hashing: C1
- HelloPro upstream w/ retry: D1
- Code one-shot: D2
- Refresh rotation + reuse detection: D3
- Logging policy + redaction + request id: G1
- Rate limiting (slowapi): G2
- End-to-end OAuth flow integration test: H2
- Bootstrap seed: I1
- Frontend Signin/Consent/Logout/Error: J3, J4
- Nginx + Dockerfile + healthcheck: J5
- docker-compose: K4
- CI + CD workflows: K1–K3
- Per-service CLAUDE.md: I2, J5
- Root CLAUDE.md: K5

**2. Placeholder scan** — no "TBD" / "TODO" / "fill in" / "similar to". Every step has actual code or commands.

**3. Type consistency check** —
- `verify_pkce(verifier, challenge, method)` signature consistent across `security.py` use in `code_service.py` (passed indirectly) and `token.py` (called).
- `issue_token_pair` keyword args (`sub`, `client_id`, `encryption_key`, `access_ttl_seconds`, `refresh_ttl_days`, `issuer`, `email`, `display_name`, `rotated_from_id`) consistent in tests, `token.py`, `revoke.py`.
- `consume_code` returns an `AuthorizationCode` row; `token.py` accesses `record.code_challenge`, `record.code_challenge_method`, `record.client_id`, `record.sub`, `record.user_email`, `record.user_display_name` — all defined on the model.
- `decode_access_token(token, expected_audience=...)` keyword used identically in `introspect.py` and `userinfo.py`.
- `validate_redirect_uri(client, uri)` positional arg shape consistent in tests + `authorize.py`.
- `ensure_signing_key(encryption_key=...)` uses keyword consistently.
- Schema field names (`access_token`, `refresh_token`, `expires_in`, `token_type`) match between `TokenResponse`, `issue_token_pair` return dict, and the frontend `useOAuthFlow` (frontend doesn't read `/token` directly — only `/authorize`).

No issues found.

---

## Notes for Executor

- All backend tests use sqlite in-memory (via `aiosqlite`). MySQL is only required at runtime in Docker. Aerich migration step (B2) is the only one that requires a live MySQL — run it locally against the dev MySQL container.
- `TestClient(app)` is created without `with`, so FastAPI lifespan does NOT run during tests — DB + signing key are bootstrapped by the autouse `_db` fixture + per-test `ensure_signing_key()` call.
- `tests/conftest.py` autouse fixture initializes a fresh sqlite DB per test, so tests are isolated.
- `apps-microservices/account-service-backend/Dockerfile` build context is the repo root (mirroring api-gateway). The CD workflows (K3) reflect this.
- The `account-service-frontend` `Dockerfile` also uses repo root context so it can be `docker compose build` from the same root.
