from contextlib import asynccontextmanager
import asyncio
import json
import logging
import os
import time
from typing import Any, Dict

import httpx
import websockets
from fastapi import (
    FastAPI,
    Request,
    WebSocket,
    WebSocketDisconnect,
    Depends,
    HTTPException,
    status,
)
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.openapi.utils import get_openapi
from fastapi.responses import Response
from starlette.middleware.sessions import SessionMiddleware

from app.core.settings import settings, SERVICE_MAP
from app.core.auth import DocsAuthMiddleware, verify_api_token
from app.db.database import TORTOISE_ORM, bootstrap_refresh_tokens
from app.db.models import ApiCallHistory
from app.routers.auth_account import router as auth_account_router
from app.routers.login import router as login_router
from app.routers.tokens import router as tokens_router
from common_utils.redis.cache_service import init_redis_pool, close_redis_pool

from tortoise.contrib.fastapi import register_tortoise


# ─── Lifespan ────────────────────────────────────────────────────────────────
# register_tortoise merges this lifespan with its own ORM lifespan.
# Our lifespan runs INSIDE the TortoiseContext created by register_tortoise,
# so DB operations work here.
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Bootstrap runs after Tortoise has initialised (via register_tortoise merge)
    await bootstrap_refresh_tokens()
    # Initialise Redis connection pool for access-token TTL checks
    await init_redis_pool()
    yield
    # Graceful Redis shutdown
    await close_redis_pool()


app = FastAPI(
    title="API Gateway",
    docs_url=None,  # disable default docs
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan,
)

# ─── Middleware stack ─────────────────────────────────────────────────────────
# DocsAuthMiddleware is a pure ASGI middleware (not BaseHTTPMiddleware) to avoid
# breaking Tortoise-ORM's contextvar tracking in v1.1+.
# In Starlette, the LAST add_middleware call is the OUTERMOST middleware.
# SessionMiddleware must be outermost so it populates request.session before
# DocsAuthMiddleware reads it.
app.add_middleware(DocsAuthMiddleware)
app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ.get("JWT_SECRET", "changeme-session-secret"),
)

# ─── Tortoise-ORM (creates TortoiseContext via RegisterTortoise) ─────────────
register_tortoise(
    app,
    config=TORTOISE_ORM,
    generate_schemas=True,
    add_exception_handlers=True,
)

# ─── Include routers ───────────────────────────────────────────────────────────
app.include_router(login_router)
app.include_router(tokens_router)
app.include_router(auth_account_router)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

EXCLUDED_HEADERS = {"host", "content-length", "transfer-encoding", "connection"}

# ─── History logging constants ────────────────────────────────────────────────
# Services whose calls should never be persisted in the history table
EXCLUDED_SERVICES = {
    "crawling-service",
    "image_comparator-service",
    "graphadmin-service",
}

# Headers whose values must be redacted before storage (lowercase, case-insensitive)
SENSITIVE_HEADERS = {"authorization", "cookie", "x-api-key", "set-cookie"}


# ─── Fire-and-forget history logging ──────────────────────────────────────────


def _sanitize_headers(headers: Dict[str, Any]) -> Dict[str, Any]:
    """Creates a copy of headers with sensitive values redacted."""
    clean_headers = {}
    for k, v in headers.items():
        if k.lower() in SENSITIVE_HEADERS:
            clean_headers[k] = "[REDACTED]"
        else:
            clean_headers[k] = v
    return clean_headers


async def _log_history(
    service_name: str,
    method: str,
    path: str,
    status_code: int,
    client_ip: str,
    request_headers: dict,
    duration_ms: int,
) -> None:
    """Persist an API call history record; errors are swallowed to not affect clients."""

    # Fast exit if service is excluded
    if service_name in EXCLUDED_SERVICES:
        return

    try:
        # Sanitize headers before serializing
        safe_headers = _sanitize_headers(request_headers)

        # Optimize JSON: If available, use 'orjson.dumps' for faster serialization
        headers_json = json.dumps(safe_headers, default=str)

        await ApiCallHistory.create(
            service_name=service_name,
            method=method,
            path=path,
            status_code=status_code,
            client_ip=client_ip,
            request_headers=headers_json,
            duration_ms=duration_ms,
        )
    except Exception as exc:
        # Include context in the error log for debugging
        logger.warning(
            f"[history] Failed to log API call for {service_name} {path}: {exc}",
            exc_info=True,
        )


# ─── Proxy route ──────────────────────────────────────────────────────────────


@app.api_route(
    "/{service}/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    include_in_schema=False,
)
async def proxy(
    service: str,
    path: str,
    request: Request,
    token_payload: dict = Depends(verify_api_token),
):
    base_url = SERVICE_MAP.get(f"/{service}")
    if not base_url:
        return JSONResponse(status_code=404, content={"detail": "Service not found"})

    # 1. Construire l'URL de destination en conservant les query parameters
    target_url = f"{base_url}/{path}"
    if request.query_params:
        target_url += "?" + str(request.query_params)

    # 2. Propager les headers du client, en excluant ceux qui sont spécifiques à la connexion
    headers = {
        name: value
        for name, value in request.headers.items()
        if name.lower() not in EXCLUDED_HEADERS
    }

    # 3. Lire le corps de la requête
    body = await request.body()

    # 4. Per-service timeout: detection=180s, others=None (existing behavior)
    service_key = f"{service}-service" if not service.endswith("-service") else service
    timeout_s = settings.DOWNSTREAM_TIMEOUTS_S.get(service_key)
    timeout = httpx.Timeout(timeout_s, connect=10.0) if timeout_s else None

    start_time = time.monotonic()
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            response = await client.request(
                request.method,
                target_url,
                headers=headers,
                content=body,
            )
        except httpx.TimeoutException as e:
            logger.warning(f"Timeout calling {service} after {timeout_s}s: {e}")
            return JSONResponse(
                status_code=504,
                content={"detail": f"Le service '{service}' a depasse son timeout ({timeout_s}s)."},
            )
        except httpx.RequestError as e:
            logger.error(f"Impossible de contacter le service {service}: {e}")
            return JSONResponse(
                status_code=503,
                content={"detail": f"Le service '{service}' est indisponible."},
            )

    if response.status_code == 503:
        logger.warning(
            f"Service {service} returned 503 (retry-after={response.headers.get('retry-after', 'n/a')})"
        )

    duration_ms = int((time.monotonic() - start_time) * 1000)

    # 5. Enregistrer l'appel dans l'historique (fire-and-forget)
    client_ip = request.client.host if request.client else "unknown"
    service_name_from_token = token_payload.get("sub", service)
    asyncio.create_task(
        _log_history(
            service_name=service_name_from_token,
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            client_ip=client_ip,
            request_headers=dict(request.headers),
            duration_ms=duration_ms,
        )
    )

    # 6. Renvoyer la réponse du service au client
    # On propage également les headers de la réponse du service
    response_headers = {
        name: value
        for name, value in response.headers.items()
        if name.lower() not in EXCLUDED_HEADERS
    }

    response_headers["X-Content-Type-Options"] = "nosniff"
    response_headers["X-Frame-Options"] = "DENY"
    response_headers["Strict-Transport-Security"] = (
        "max-age=31536000; includeSubDomains"
    )

    return Response(
        content=response.content,
        status_code=response.status_code,
        headers=response_headers,
        media_type=response.headers.get("content-type"),
    )


@app.websocket("/{service}/{path:path}")
async def websocket_proxy(service: str, path: str, websocket: WebSocket):
    base_url = SERVICE_MAP.get(f"/{service}")
    if not base_url:
        logger.warning(f"[GW] Service '{service}' non trouvé. Fermeture WS.")
        await websocket.close(code=1008)
        return

    ws_url = base_url.replace("http://", "ws://").replace("https://", "wss://")
    target_url = f"{ws_url}/{path}"

    if websocket.url.query:
        target_url += "?" + websocket.url.query

    logger.info(f"[GW] Connexion client acceptée pour {websocket.url.path}")
    await websocket.accept()

    EXCLUDED_WS_HEADERS = {
        "connection",
        "upgrade",
        "host",
        "sec-websocket-key",
        "sec-websocket-version",
        "sec-websocket-protocol",
        "sec-websocket-extensions",
    }

    try:
        logger.info(f"[GW] Tentative de connexion au backend : {target_url}")

        forwarded_headers = [
            (name, value)
            for name, value in websocket.headers.items()
            if name.lower() not in EXCLUDED_WS_HEADERS
        ]

        async with websockets.connect(
            target_url, extra_headers=forwarded_headers
        ) as backend_ws:
            logger.info("[GW] Connexion au backend réussie. Démarrage du relais.")

            async def forward_to_backend():
                try:
                    while True:
                        data = await websocket.receive_text()
                        # logger.info(f"[GW] Client -> Backend: {data[:200]}...")
                        await backend_ws.send(data)
                except WebSocketDisconnect:
                    logger.info("[GW] Le client s'est déconnecté.")

            async def forward_to_client():
                try:
                    while True:
                        data = await backend_ws.recv()
                        # logger.info(f"[GW] Backend -> Client: {data[:200]}...")
                        await websocket.send_text(data)
                except websockets.exceptions.ConnectionClosed:
                    logger.info("[GW] Le backend a fermé la connexion.")

            client_task = asyncio.create_task(forward_to_backend())
            backend_task = asyncio.create_task(forward_to_client())
            done, pending = await asyncio.wait(
                [client_task, backend_task], return_when=asyncio.FIRST_COMPLETED
            )
            for task in pending:
                task.cancel()

    except websockets.exceptions.InvalidStatusCode as e:
        logger.error(
            f"[GW] ERREUR: Le backend a refusé la connexion WebSocket avec le statut {e.status_code}"
        )
    except Exception as e:
        logger.error(
            f"[GW] ERREUR inattendue dans le proxy WebSocket : {e}", exc_info=True
        )
    finally:
        # Laisser le framework gérer la fermeture de la connexion client.
        # Le `async with` gère déjà la fermeture de la connexion backend.
        logger.info("[GW] Nettoyage et fin du proxy pour cette connexion.")
        # --- LIGNE SUPPRIMÉE ---
        # await websocket.close()


# Combine all OpenAPI schemas
@app.get("/openapi.json", include_in_schema=False)
async def custom_openapi():
    # ── Description publique (visible par tous les utilisateurs) ──────────────
    _PUBLIC_DESCRIPTION = """
> ⚠️ **Note importante — Authentification désactivée temporairement**
>
> Le contrôle d'accès par **Bearer Token** (`access_token`) n'est **pas encore actif**.
> Vous pouvez appeler tous les endpoints **sans fournir de token** pour le moment.
> Cette restriction sera activée prochainement.

---

## 🔐 Authentification — Comment accéder aux services

Tous les appels aux microservices transitent par cette gateway et doivent être authentifiés
via un **Bearer Token** (JWT à durée de vie limitée).

### Étape 1 — Récupérer votre refresh token

> 💡 Le **refresh token** de votre service est automatiquement généré au démarrage de la gateway.
> Vous n'avez pas besoin de le créer manuellement.

Exécutez l'endpoint suivant en renseignant le nom de votre service :

`GET /auth/token/refresh-tokens?service_name=<nom-de-votre-service>`

La réponse contient votre `refresh_token`. Conservez-le, il est permanent tant que le service est actif.

### Étape 2 — Générer un access token

Échangez votre `refresh_token` contre un **access token** avec une durée de vie de 24h via `POST /auth/token/refresh` :

```json
{
  "service_name": "<nom-de-votre-service>",
  "refresh_token": "<votre-refresh-token>"
}
```

La réponse contient un `access_token` valable pour une durée de 24h.

### Étape 3 — Appeler les services

### 🖥️ Utilisation dans Swagger UI

1. Exécutez `GET /auth/token/refresh-tokens` pour obtenir votre `refresh_token`.
2. Exécutez `POST /auth/token/refresh` — pour obtenir l'`access_token`.
3. Cliquez sur **🔒 Authorize**, collez l'access token dans le champ **Bearer Token**, puis validez.

### ⚙️ Pour les requêtes APIs

Ajoutez l'access token dans l'en-tête `Authorization` de chaque requête :

```
Authorization: Bearer <votre-access-token>
```

### Étape 4 — Renouveler l'access token

Lorsque l'access token expire, répétez l'**Étape 2** pour en obtenir un nouveau à partir du même refresh token.

"""

    openapi = get_openapi(
        title="Hellopro APIs",
        version="1.0.0",
        description=_PUBLIC_DESCRIPTION,
        routes=app.routes,
    )

    # ── Bearer token authorization ─────────────────────────────────────────────
    # Adds the 🔒 Authorize button in Swagger UI so tokens can be set globally.
    # The key name IS the label shown in the Swagger UI Authorize dialog.
    openapi.setdefault("components", {}).setdefault("securitySchemes", {})[
        "Bearer Token"
    ] = {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT",
        "description": "Coller l'access token généré depuis **POST /auth/token/generate** or **POST /auth/token/refresh**.",
    }
    # Apply the scheme globally (all paths inherit it unless they override)
    openapi["security"] = [{"Bearer Token": []}]
    # ────────────────────────────────────────────────────────────────────────────

    # ── Admin clé (X-Admin-Key header) — defined server-side ─────────────────
    # This scheme must be in the server-side spec so Swagger UI knows to send
    # the X-Admin-Key header for endpoints that declare this security scheme.
    # Non-admin users see the field but it stays empty (key is never exposed).
    # Admin users get it pre-filled via the JS injection in /docs.
    openapi["components"]["securitySchemes"]["AdminCle"] = {
        "type": "apiKey",
        "in": "header",
        "name": "X-Admin-Key",
        "description": "Clé Admin (variable env `GATEWAY_ADMIN_KEY`) — gestion des historiques et refresh tokens.",
    }
    # ────────────────────────────────────────────────────────────────────────────

    # ── Description complémentaire réservée aux admins ────────────────────────
    _ADMIN_DESCRIPTION_EXTRA = """
<!-- ADMIN_SECTION -->

---

## 🛡️ Section Administration *(visible uniquement par les administrateurs)*

Les endpoints ci-dessous sont protégés par l'en-tête `X-Admin-Key`.
La valeur attendue correspond à la variable d'environnement **`GATEWAY_ADMIN_KEY`**.
Elle est automatiquement injectée dans vos requêtes Swagger UI.

> ⚠️ **Avant d'utiliser un endpoint admin** : cliquez sur le bouton **🔒 Authorize** en haut de la page,
> puis validez le champ **AdminCle** (il est déjà pré-rempli automatiquement).
> Sans cette étape, vos requêtes seront rejetées avec une erreur `403 Forbidden`.

| Endpoint | Rôle |
|----------|------|
| `POST /auth/token/generate` | Crée (ou réutilise) le refresh token d'un service et émet un access token initial. |
| `POST /auth/token/revoke` | Désactive le refresh token d'un service et invalide tous ses access tokens (DB + Redis). |
| `GET /auth/logs` | Journal d'audit paginé de tous les appels proxysés : méthode, chemin, service, statut, IP, durée. |
| `GET /auth/token/all-refresh-tokens` | Liste les refresh tokens de **tous** les services. Filtre optionnel `active_only` (`true` / `false` / absent = tous). |
"""
    openapi["info"]["description"] = (
        openapi["info"].get("description", "") + _ADMIN_DESCRIPTION_EXTRA
    )
    # ────────────────────────────────────────────────────────────────────────────

    # Tracker pour détecter les collisions de schémas
    schema_tracker = {}  # {schema_name: [service_prefix1, service_prefix2, ...]}

    async with httpx.AsyncClient() as client:
        # Premier passage : détecter les collisions
        service_schemas = {}  # {prefix: sub_openapi}
        for prefix, url in SERVICE_MAP.items():
            try:
                r = await client.get(f"{url}/openapi.json")
                r.raise_for_status()
                sub_openapi = r.json()
                service_schemas[prefix] = sub_openapi

                # Tracker les schémas de ce service
                if (
                    "components" in sub_openapi
                    and "schemas" in sub_openapi["components"]
                ):
                    for schema_name in sub_openapi["components"]["schemas"].keys():
                        if schema_name not in schema_tracker:
                            schema_tracker[schema_name] = []
                        schema_tracker[schema_name].append(prefix)

            except Exception as e:
                print(f"Failed to fetch schema from {url}: {e}")

        # Identifier les schémas en collision (présents dans plusieurs services)
        conflicting_schemas = {
            name for name, prefixes in schema_tracker.items() if len(prefixes) > 1
        }

        # Deuxième passage : merger avec préfixe seulement si collision
        for prefix, sub_openapi in service_schemas.items():
            # Créer un préfixe unique pour les schémas basé sur le service
            # Ex: /classification-service -> Classification, /classification-v2-service -> ClassificationV2
            schema_prefix = (
                prefix.strip("/")
                .replace("-service", "")
                .replace("-", "_")
                .title()
                .replace("_", "")
            )

            # Fonction pour remplacer les références de schémas
            def prefix_refs(obj, prefix_to_use, schemas_to_prefix):
                """Préfixe récursivement les références $ref uniquement pour les schémas en collision"""
                if isinstance(obj, dict):
                    new_obj = {}
                    for k, v in obj.items():
                        if (
                            k == "$ref"
                            and isinstance(v, str)
                            and "#/components/schemas/" in v
                        ):
                            schema_name = v.split("/")[-1]
                            # Préfixer seulement si ce schéma est en collision
                            if schema_name in schemas_to_prefix:
                                new_obj[k] = (
                                    f"#/components/schemas/{prefix_to_use}{schema_name}"
                                )
                            else:
                                new_obj[k] = v
                        else:
                            new_obj[k] = prefix_refs(
                                v, prefix_to_use, schemas_to_prefix
                            )
                    return new_obj
                elif isinstance(obj, list):
                    return [
                        prefix_refs(item, prefix_to_use, schemas_to_prefix)
                        for item in obj
                    ]
                else:
                    return obj

            # Préfixer les références dans les paths (seulement pour schémas en collision)
            prefixed_paths = prefix_refs(
                sub_openapi.get("paths", {}), schema_prefix, conflicting_schemas
            )

            # Merge paths with prefix
            for path, path_data in prefixed_paths.items():
                # Préfixer les operationId pour éviter les collisions dans Swagger UI
                for method in [
                    "get",
                    "post",
                    "put",
                    "delete",
                    "patch",
                    "options",
                    "head",
                    "trace",
                ]:
                    if method in path_data and "operationId" in path_data[method]:
                        original_operation_id = path_data[method]["operationId"]
                        # Ajouter le préfixe du service à l'operationId
                        # Ex: classify_single_product -> classification_v2_classify_single_product
                        service_name = (
                            prefix.strip("/").replace("-service", "").replace("-", "_")
                        )
                        path_data[method][
                            "operationId"
                        ] = f"{service_name}_{original_operation_id}"

                # Pas besoin de définir un server spécifique par path car le path complet
                # inclut déjà le préfixe du service (/classification-v2-service/...)
                # Swagger UI utilisera le serveur racine "/" par défaut
                openapi["paths"][f"{prefix}{path}"] = path_data

            # Merge components (schemas, responses, parameters, etc.)
            if "components" in sub_openapi:
                if "components" not in openapi:
                    openapi["components"] = {}

                for comp_type, comp_dict in sub_openapi["components"].items():
                    if comp_type not in openapi["components"]:
                        openapi["components"][comp_type] = {}

                    for key, val in comp_dict.items():
                        # Préfixer seulement si ce schéma est en collision
                        if comp_type == "schemas" and key in conflicting_schemas:
                            prefixed_key = f"{schema_prefix}{key}"
                            prefixed_val = prefix_refs(
                                val, schema_prefix, conflicting_schemas
                            )
                            openapi["components"][comp_type][
                                prefixed_key
                            ] = prefixed_val
                        else:
                            # Pas de collision, garder le nom original
                            if key not in openapi["components"][comp_type]:
                                openapi["components"][comp_type][key] = val

    return JSONResponse(content=openapi)


# ─── GET /openapi-public.json — filtered spec for non-admin users ──────────────


def _build_public_openapi(full_spec: dict) -> dict:
    """
    Return a copy of the full OpenAPI spec with all admin-only endpoints removed.

    An endpoint is considered admin-only when its `security` array contains
    the {"AdminCle": []} entry (the X-Admin-Key scheme).
    The AdminCle securityScheme definition is also removed from components.
    """
    import copy

    public = copy.deepcopy(full_spec)

    # 1. Filter paths: drop operations (or entire paths) that require AdminCle
    paths_to_keep = {}
    for path, path_item in public.get("paths", {}).items():
        public_methods = {}
        for method, operation in path_item.items():
            if not isinstance(operation, dict):
                # path-level fields such as 'parameters', 'summary', etc.
                public_methods[method] = operation
                continue
            # Check if this operation's security list contains AdminCle
            security = operation.get("security", [])
            is_admin_only = any(
                isinstance(s, dict) and "AdminCle" in s for s in security
            )
            if not is_admin_only:
                public_methods[method] = operation

        # Only keep the path if at least one HTTP method remains
        http_methods = {
            "get",
            "post",
            "put",
            "delete",
            "patch",
            "options",
            "head",
            "trace",
        }
        if any(m in public_methods for m in http_methods):
            paths_to_keep[path] = public_methods

    public["paths"] = paths_to_keep

    # 2. Remove AdminCle from securitySchemes so it doesn't appear in Authorize
    try:
        del public["components"]["securitySchemes"]["AdminCle"]
    except KeyError:
        pass

    # 3. Strip the admin-only section from the description
    desc = public.get("info", {}).get("description", "")
    _admin_sentinel = "\n<!-- ADMIN_SECTION -->"
    if _admin_sentinel in desc:
        public["info"]["description"] = desc.split(_admin_sentinel)[0]

    return public


@app.get("/openapi-public.json", include_in_schema=False)
async def public_openapi(request: Request):
    """Filtered OpenAPI spec — admin-only endpoints are hidden."""
    from fastapi.responses import JSONResponse as _JSONResponse

    # Reuse the full spec built by the custom_openapi endpoint
    full_response = await custom_openapi()
    full_spec = json.loads(full_response.body)
    public_spec = _build_public_openapi(full_spec)
    return _JSONResponse(content=public_spec)


# Custom docs and redoc
from fastapi.openapi.docs import (
    get_swagger_ui_html,
    get_redoc_html,
)


@app.get("/docs", include_in_schema=False)
async def custom_docs(request: Request):
    # ── Determine if the logged-in user is an admin ──────────────────────────────
    user = request.session.get("user", {})
    user_email = user.get("email", "").strip().lower()

    admin_emails_raw = os.environ.get("GATEWAY_DOCS_ADMIN_EMAILS", "")
    admin_emails = {e.strip().lower() for e in admin_emails_raw.split(",") if e.strip()}

    is_admin = bool(user_email and user_email in admin_emails)

    logger.info(
        f"[docs] user_email={user_email!r} | "
        f"GATEWAY_DOCS_ADMIN_EMAILS={admin_emails_raw!r} | "
        f"is_admin={is_admin}"
    )
    # ────────────────────────────────────────────────────────────────────────────

    # Non-admin users get a filtered spec that hides admin-only endpoints
    openapi_url = "/openapi.json" if is_admin else "/openapi-public.json"

    swagger_response = get_swagger_ui_html(
        openapi_url=openapi_url, title="API Gateway Docs"
    )

    html_content = swagger_response.body.decode("utf-8")

    # ── Common JS (all users): auto-authorize Bearer Token from generate/refresh ──
    common_js = """
<script>
(function () {
  var BEARER_SCHEME = 'Bearer Token';

  function applyBearerToken(token) {
    // Try the Swagger UI built-in API first (most reliable, same as admin key)
    var ui = window.__swaggerUi;
    if (ui && typeof ui.preauthorizeHttpAuth === 'function') {
      ui.preauthorizeHttpAuth(BEARER_SCHEME, token);
      return;
    }

    // UI not ready yet — retry up to 10 times every 200 ms
    var attempts = 0;
    var interval = setInterval(function () {
      attempts++;
      var ui2 = window.__swaggerUi;
      if (ui2 && typeof ui2.preauthorizeHttpAuth === 'function') {
        clearInterval(interval);
        ui2.preauthorizeHttpAuth(BEARER_SCHEME, token);
        return;
      }
      if (attempts >= 10) {
        clearInterval(interval);
        // Last-resort fallback: fill Authorize dialog via DOM
        _fillBearerViaDOM(token);
      }
    }, 200);
  }

  function _fillBearerViaDOM(token) {
    var dialog = document.querySelector('.dialog-ux');
    if (!dialog || dialog.style.display === 'none') {
      var mainBtn = document.querySelector('.auth-btn-wrapper .authorize, button.btn.authorize');
      if (mainBtn) mainBtn.click();
    }
    setTimeout(function () {
      var sections = document.querySelectorAll('.auth-container');
      sections.forEach(function (section) {
        var heading = section.querySelector('h4, h3, h2');
        if (!heading || heading.textContent.indexOf(BEARER_SCHEME) === -1) return;

        var inp = section.querySelector('input[type="text"], input[type="password"], input');
        if (inp) {
          var nativeSetter = Object.getOwnPropertyDescriptor(
            window.HTMLInputElement.prototype, 'value'
          ).set;
          nativeSetter.call(inp, token);
          inp.dispatchEvent(new Event('input', { bubbles: true }));
        }

        var buttons = section.querySelectorAll('button');
        for (var i = 0; i < buttons.length; i++) {
          if (buttons[i].textContent.trim() === 'Authorize') {
            buttons[i].click();
            break;
          }
        }
      });
      setTimeout(function () {
        var closeBtn = document.querySelector('button.btn-done, button[aria-label="Close"]');
        if (closeBtn) closeBtn.click();
      }, 250);
    }, 350);
  }

  // Wrap SwaggerUIBundle to add responseInterceptor + persistAuthorization
  var _orig = window.SwaggerUIBundle;
  window.SwaggerUIBundle = function (config) {
    config.persistAuthorization = true;
    config.deepLinking = true;

    var _prevResp = config.responseInterceptor;
    config.responseInterceptor = function (response) {
      var result = _prevResp ? _prevResp(response) : response;
      try {
        var url = response.url || '';
        // Match /auth/token/generate and /auth/token/refresh exactly
        // (exclude /auth/token/refresh-tokens and similar)
        var isTokenEndpoint = /\/auth\/token\/generate(\?|$)/.test(url)
                           || /\/auth\/token\/refresh(\?|$|#)/.test(url);
        if (isTokenEndpoint && response.status === 200) {
          var body = response.obj
            || JSON.parse(response.text || response.body || '{}');
          var token = body && body.access_token;
          if (token) applyBearerToken(token);
        }
      } catch (_) {}
      return result || response;
    };

    var ui = _orig(config);
    window.__swaggerUi = ui;
    return ui;
  };
  Object.assign(window.SwaggerUIBundle, _orig);
})();
</script>"""
    html_content = html_content.replace("</head>", common_js + "\n</head>")

    if not is_admin:
        return HTMLResponse(content=html_content)

    # ── Admin-only JS: pre-fill AdminCle + auto-send X-Admin-Key header ─────────
    admin_key = os.environ.get("GATEWAY_ADMIN_KEY", "changeme-admin-key")

    admin_js = f"""
<script>
(function () {{
  var ADMIN_KEY = '{admin_key}';
  var SCHEME_NAME = 'AdminCle';

  // ── 1. MutationObserver: fill AdminCle input when the dialog opens ────────
  function tryFillAdminInput(root) {{
    var containers = root.querySelectorAll ? root.querySelectorAll('.auth-container') : [];
    for (var i = 0; i < containers.length; i++) {{
      var heading = containers[i].querySelector('h4, h3, h2');
      if (heading && heading.textContent.indexOf(SCHEME_NAME) !== -1) {{
        var inp = containers[i].querySelector('input[type="text"]');
        if (inp && inp.value !== ADMIN_KEY) {{
          var nativeSetter = Object.getOwnPropertyDescriptor(
            window.HTMLInputElement.prototype, 'value'
          ).set;
          nativeSetter.call(inp, ADMIN_KEY);
          inp.dispatchEvent(new Event('input', {{ bubbles: true }}));
        }}
      }}
    }}
  }}
  var adminObserver = new MutationObserver(function (mutations) {{
    mutations.forEach(function (m) {{
      m.addedNodes.forEach(function (node) {{
        if (node.nodeType === 1) tryFillAdminInput(node);
      }});
    }});
  }});
  function startAdminObserver() {{
    adminObserver.observe(document.body, {{ childList: true, subtree: true }});
  }}
  if (document.readyState !== 'loading') {{
    startAdminObserver();
  }} else {{
    document.addEventListener('DOMContentLoaded', startAdminObserver);
  }}

  // ── 2. requestInterceptor: always inject X-Admin-Key header ───────────────
  var _orig2 = window.SwaggerUIBundle;
  window.SwaggerUIBundle = function (config) {{
    var _prev = config.requestInterceptor;
    config.requestInterceptor = function (request) {{
      if (_prev) request = _prev(request);
      request.headers['X-Admin-Key'] = ADMIN_KEY;
      return request;
    }};
    return _orig2(config);
  }};
  Object.assign(window.SwaggerUIBundle, _orig2);
}})();
</script>"""
    html_content = html_content.replace("</head>", admin_js + "\n</head>")
    return HTMLResponse(content=html_content)
    # ────────────────────────────────────────────────────────────────────────────


@app.get("/redoc", include_in_schema=False)
async def custom_redoc():
    from fastapi.responses import RedirectResponse

    return RedirectResponse(url="/docs", status_code=301)
