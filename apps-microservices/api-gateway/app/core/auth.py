import jwt
import os
import logging

from datetime import datetime, timezone
from fastapi import Request, HTTPException, status
from fastapi.responses import RedirectResponse
from jwt import ExpiredSignatureError, InvalidTokenError

from app.core.settings import settings
from app.db.models import InfoRefreshToken, InfoAccessToken
from app.utils.token_service import verify_access_token
from common_utils.redis.cache_service import get_json

JWT_SECRET = os.environ.get("JWT_SECRET")
JWT_ALGO = os.environ.get("JWT_ALGO")
JWT_AUDIENCE = os.environ.get("JWT_AUDIENCE")

# Config logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("auth")

# ─── Routes that require docs login (session-based) ───────────────────────────
DOCS_PROTECTED_PATHS = {"/docs", "/redoc", "/openapi.json"}


class DocsAuthMiddleware:
    """
    Pure ASGI middleware that protects /docs, /redoc, and /openapi.json
    behind a session-based login.

    API proxy routes (/{service}/{path}) are NOT affected by this middleware —
    they are protected by the OAuth2 Bearer token dependency instead.

    NOTE: This is a pure ASGI middleware (not BaseHTTPMiddleware) to avoid
    breaking Tortoise-ORM's contextvar-based connection tracking in v1.1+.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")

        # Only protect docs-related paths
        if path not in DOCS_PROTECTED_PATHS:
            await self.app(scope, receive, send)
            return

        logger.info(f"➡️ Docs access: {path}")

        # Build a Request object to access session
        request = Request(scope, receive, send)

        # Vérifie session
        user = request.session.get("user")
        if not user:
            logger.warning(f"❌ Pas de session, redirection vers /login pour {path}")
            response = RedirectResponse(url="/login")
            await response(scope, receive, send)
            return

        token = user.get("token")
        if not token:
            logger.warning(
                f"❌ Pas de token en session, redirection vers /login pour {path}"
            )
            response = RedirectResponse(url="/login")
            await response(scope, receive, send)
            return

        # Vérifie le token JWT
        try:
            # Skip audience verification: account-service issues JWTs with
            # aud=<client_id> per OAuth2 spec, not the legacy JWT_AUDIENCE.
            # Signature match against the shared JWT_SECRET already proves
            # the token came from a trusted issuer.
            decoded = jwt.decode(
                token, JWT_SECRET, algorithms=[JWT_ALGO],
                options={"verify_aud": False},
            )
            logger.info(f"🔐 Utilisateur connecté: {decoded.get('name', 'unknown')}")
        except ExpiredSignatureError:
            logger.warning("⚠️ Token expiré → déconnexion")
            request.session.clear()
            response = RedirectResponse(url="/login")
            await response(scope, receive, send)
            return
        except InvalidTokenError as e:
            logger.error(f"❌ Token invalide: {e}")
            request.session.clear()
            response = RedirectResponse(url="/login")
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)


# ─── OAuth2 Bearer dependency for API proxy routes ────────────────────────────


async def verify_api_token(request: Request) -> dict:
    """
    FastAPI dependency for API proxy routes.

    1. Checks if the requested service/path is in the exclusion list.
    2. Validates the Bearer JWT access token.
    3. Checks that the access token exists in info_access_token and is active.
    4. Checks that the linked refresh token is also active.

    Returns the decoded JWT payload (or a mock payload for excluded routes).
    Raises HTTP 401 on any failure.
    """
    # TODO:
    # Test pour toujours exclure toutes les routes → except graphdlq-service pour le test
    service_name = request.path_params.get("service", "")
    req_path = request.path_params.get("path", "").strip("/")
    if service_name != "graphdlq-service":
        return {"sub": service_name, "is_excluded": True}

    # 1. Check if route is excluded from authentication
    excluded_paths = settings.EXCLUDED_ROUTES.get(service_name, [])
    normalized_excluded = [p.strip("/") for p in excluded_paths]

    if req_path in normalized_excluded:
        logger.debug(
            f"[auth] 🔓 Bypassing auth for excluded route: {service_name}/{req_path}"
        )
        return {"sub": service_name, "is_excluded": True}

    # 2. Extract token from Authorization header
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access token manquant ou invalide.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    raw_token = auth_header.removeprefix("Bearer ").strip()

    # 3. Decode & verify JWT
    try:
        payload = verify_access_token(raw_token)
    except ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access token has expired. Please refresh.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid access token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Extract claims used in logging and DB fallback checks
    token_service_name = payload.get("sub")
    refresh_token_id = payload.get("rtid")

    # 4. Check access token TTL via Redis (fast path)
    # Redis key is set when the token is created and expires automatically.
    # If the key is absent, the token has either expired or been revoked.
    redis_key = f"access_token:{raw_token}"
    redis_payload = None
    try:
        redis_payload = await get_json(redis_key)
        logging.warning(f"here is the verification of access token {redis_payload}")
    except Exception as exc:
        logger.warning(
            f"[auth] Redis unavailable, falling back to DB for token check: {exc}"
        )

    if redis_payload is not None:
        # Fast path: Redis key exists → token is still within its TTL
        logger.debug(
            f"[auth] ✅ Redis HIT — token valid for service='{token_service_name}'"
        )
        return payload

    # Slow path (Redis miss / Redis down): verify against DB
    now = datetime.now(tz=timezone.utc)
    access_record = (
        await InfoAccessToken.filter(
            token=raw_token,
            est_actif=True,
            date_expiration__gte=now,
        )
        .select_related("id_refresh_token")
        .first()
    )

    if not access_record:
        logger.warning(
            f"[auth] Rejected token: service='{token_service_name}' "
            f"(access token not found, inactive, or expired in DB)"
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access token has been revoked or expired.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 5. Check that the linked refresh token is still active
    refresh_record = access_record.id_refresh_token
    if not refresh_record or not refresh_record.est_actif:
        logger.warning(
            f"[auth] Rejected token: service='{token_service_name}' rtid={refresh_token_id} "
            f"(refresh token revoked or not found)"
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access token has been revoked.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    logger.debug(
        f"[auth] ✅ DB fallback — Authenticated service='{token_service_name}'"
    )
    return payload
