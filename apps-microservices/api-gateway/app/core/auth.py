import jwt
import os
import logging

from fastapi import Request
from fastapi.responses import RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware
from jwt import ExpiredSignatureError, InvalidTokenError

JWT_SECRET = os.environ.get("JWT_SECRET")
JWT_ALGO = os.environ.get("JWT_ALGO")
JWT_AUDIENCE = os.environ.get("JWT_AUDIENCE")

# Config logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("auth")

# ─── Routes that require docs login (session-based) ───────────────────────────
DOCS_PROTECTED_PATHS = {"/docs", "/redoc", "/openapi.json"}


class DocsAuthMiddleware(BaseHTTPMiddleware):
    """
    Middleware that protects /docs, /redoc, and /openapi.json behind a session-based login.
    API proxy routes (/{service}/{path}) are NOT affected by this middleware —
    they are protected by the OAuth2 Bearer token dependency instead.
    """

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Only protect docs-related paths
        if path not in DOCS_PROTECTED_PATHS:
            return await call_next(request)

        logger.info(f"➡️ Docs access: {path}")

        # Vérifie session
        user = request.session.get("user")
        if not user:
            logger.warning(f"❌ Pas de session, redirection vers /login pour {path}")
            return RedirectResponse(url="/login")

        token = user.get("token")
        if not token:
            logger.warning(
                f"❌ Pas de token en session, redirection vers /login pour {path}"
            )
            return RedirectResponse(url="/login")

        # Vérifie le token JWT
        try:
            decoded = jwt.decode(
                token, JWT_SECRET, algorithms=[JWT_ALGO], audience=JWT_AUDIENCE
            )
            logger.info(f"🔐 Utilisateur connecté: {decoded.get('name', 'unknown')}")
        except ExpiredSignatureError:
            logger.warning("⚠️ Token expiré → déconnexion")
            request.session.clear()
            return RedirectResponse(url="/login")
        except InvalidTokenError as e:
            logger.error(f"❌ Token invalide: {e}")
            request.session.clear()
            return RedirectResponse(url="/login")

        return await call_next(request)
