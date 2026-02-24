"""
Points d'accès de gestion des tokens pour l'API Gateway.

Endpoints (tous sous /auth) :
    POST /auth/token/generate   — Créer un refresh token + access token pour un service
    POST /auth/token/refresh    — Échanger un refresh token contre un nouvel access token
    POST /auth/token/revoke     — Désactiver le refresh token d'un service
    GET  /auth/history          — Journal d'audit paginé de tous les appels proxysés

Les endpoints admin (generate / revoke / history) sont protégés par l'en-tête
X-Admin-Key, validé par rapport à la variable d'env GATEWAY_ADMIN_KEY.
"""

import os
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Header, Query, Request, status

from app.db.models import ApiCallHistory, InfoRefreshToken, InfoAccessToken
from app.db.schemas import (
    ApiCallHistoryEntry,
    ApiCallHistoryList,
    TokenGenerateRequest,
    TokenGenerateResponse,
    TokenRefreshRequest,
    TokenRefreshResponse,
    TokenRevokeRequest,
    TokenRevokeResponse,
    RefreshTokenEntry,
    RefreshTokenList,
)

# from libs.token_lib import generate_access_token, generate_refresh_token
# from libs.token_lib import TokenService
from app.utils.token_service import generate_access_token, generate_refresh_token
from app.utils.token_service import TokenService
from common_utils.redis.cache_service import set_json, delete_key, scan_keys_by_prefix

logger = logging.getLogger("tokens")

router = APIRouter(prefix="/auth", tags=["Token Management"])

# ─── Admin key (env-based) ─────────────────────────────────────────────────────
GATEWAY_ADMIN_KEY: str = os.environ.get("GATEWAY_ADMIN_KEY", "changeme-admin-key")
ACCESS_TOKEN_EXPIRE_MINUTES: int = int(
    os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", "15")
)

# Maximum number of active, non-expired access tokens kept per refresh token
MAX_ACTIVE_ACCESS_TOKENS = 10


# ─── Admin key dependency ──────────────────────────────────────────────────────


async def require_admin_key(
    x_admin_key: str = Header(..., alias="X-Admin-Key", include_in_schema=False),
) -> None:
    """FastAPI dependency that verifies the X-Admin-Key header."""
    if x_admin_key != GATEWAY_ADMIN_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing admin key.",
        )


# ─── Helper: prune old active access tokens ───────────────────────────────────


async def _prune_access_tokens(refresh_token_id: int) -> None:
    """
    Keep only the MAX_ACTIVE_ACCESS_TOKENS most recently created, non-expired
    access tokens active for a given refresh token. Deactivate all others.
    """
    now = datetime.now(tz=timezone.utc)

    # Fetch all active, non-expired access tokens for this refresh token
    # ordered by date_creation DESC (most recent first)
    active_tokens = (
        await InfoAccessToken.filter(
            id_refresh_token_id=refresh_token_id,
            est_actif=True,
            date_expiration__gte=now,
        )
        .order_by("-date_creation")
        .all()
    )

    if len(active_tokens) > MAX_ACTIVE_ACCESS_TOKENS:
        # IDs of tokens to deactivate (everything beyond the first 10)
        ids_to_deactivate = [t.id for t in active_tokens[MAX_ACTIVE_ACCESS_TOKENS:]]
        await InfoAccessToken.filter(id__in=ids_to_deactivate).update(est_actif=False)
        logger.info(
            f"[tokens] Pruned {len(ids_to_deactivate)} excess access tokens "
            f"for refresh_token_id={refresh_token_id}"
        )

    # Also deactivate any expired tokens that are still marked active
    expired_count = await InfoAccessToken.filter(
        id_refresh_token_id=refresh_token_id,
        est_actif=True,
        date_expiration__lt=now,
    ).update(est_actif=False)

    if expired_count:
        logger.info(
            f"[tokens] Deactivated {expired_count} expired access tokens "
            f"for refresh_token_id={refresh_token_id}"
        )


# ─── POST /auth/token/generate ────────────────────────────────────────────────


@router.post(
    "/token/generate",
    response_model=TokenGenerateResponse,
    summary="Générer un refresh token + access token pour un service (admin uniquement)",
    openapi_extra={"security": [{"AdminCle": []}]},
)
async def generate_token(
    body: TokenGenerateRequest,
    request: Request,
    _: None = Depends(require_admin_key),
) -> TokenGenerateResponse:
    """
    Crée (ou réutilise s'il existe déjà) le refresh token d'un microservice
    et émet un nouvel access token à courte durée de vie.

    - Si un refresh token actif existe déjà → réutilisation.
    - Sinon → création d'un nouveau refresh token.
    """
    # 1. Check for existing active refresh token
    refresh_record = await InfoRefreshToken.filter(
        nom_service=body.service_name,
        est_actif=True,
    ).first()

    if refresh_record:
        logger.info(
            f"[tokens] Active refresh token already exists for "
            f"service='{body.service_name}' (id={refresh_record.id}) — reusing."
        )
    else:
        # Create new refresh token
        refresh_token_value = generate_refresh_token(body.service_name)
        client_ip = request.client.host if request.client else "unknown"
        refresh_record = await InfoRefreshToken.create(
            nom_service=body.service_name,
            token=refresh_token_value,
            ip_creation=client_ip,
            est_actif=True,
        )
        logger.info(f"[tokens] Refresh token created for service='{body.service_name}'")

    # 2. Generate a new access token (JWT)
    now = datetime.now(tz=timezone.utc)
    expiration = now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    access_token_value = generate_access_token(
        service_name=body.service_name,
        refresh_token_id=refresh_record.id,
    )

    # 3. Store access token in DB
    access_record = await InfoAccessToken.create(
        id_refresh_token=refresh_record,
        token=access_token_value,
        date_expiration=expiration,
        est_actif=True,
    )

    # 3b. Mirror access token in Redis with the same TTL
    ttl_seconds = ACCESS_TOKEN_EXPIRE_MINUTES * 60
    redis_key = f"access_token:{access_token_value}"
    try:
        await set_json(
            redis_key,
            {"service": body.service_name, "rtid": refresh_record.id},
            ttl=ttl_seconds,
        )
        logger.info(
            f"[tokens] Access token stored in Redis (ttl={ttl_seconds}s) "
            f"for service='{body.service_name}'"
        )
    except Exception as exc:
        logger.warning(f"[tokens] Could not store access token in Redis: {exc}")

    # 4. Prune old access tokens
    await _prune_access_tokens(refresh_record.id)

    return TokenGenerateResponse(
        service_name=body.service_name,
        refresh_token=refresh_record.token,
        access_token=access_token_value,
        access_token_expires_minutes=ACCESS_TOKEN_EXPIRE_MINUTES,
        access_token_expires_at=expiration,
        created_at=refresh_record.date_creation,
    )


# ─── POST /auth/token/refresh ─────────────────────────────────────────────────


@router.post(
    "/token/refresh",
    response_model=TokenRefreshResponse,
    summary="Échanger un refresh token contre un nouvel access token",
)
async def refresh_token(body: TokenRefreshRequest) -> TokenRefreshResponse:
    """
    Émet un nouvel access token à courte durée de vie à partir d'un refresh token valide et actif.

    **Utilisation dans Swagger UI :**
    1. Exécutez cet endpoint pour obtenir un `access_token`.
    2. Copiez la valeur de `access_token` dans la réponse.
    3. Cliquez sur **🔒 Authorize** (en haut de la page), collez le token dans le champ **Bearer Token**, puis cliquez sur **Authorize**.
    """
    record = await InfoRefreshToken.filter(
        nom_service=body.service_name,
        token=body.refresh_token,
        est_actif=True,
    ).first()

    if not record:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or revoked refresh token.",
        )

    # Generate new access token
    now = datetime.now(tz=timezone.utc)
    expiration = now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    access_token_value = generate_access_token(
        service_name=body.service_name,
        refresh_token_id=record.id,
    )

    # Store access token in DB
    await InfoAccessToken.create(
        id_refresh_token=record,
        token=access_token_value,
        date_expiration=expiration,
        est_actif=True,
    )

    # Mirror access token in Redis with the same TTL
    ttl_seconds = ACCESS_TOKEN_EXPIRE_MINUTES * 60
    redis_key = f"access_token:{access_token_value}"
    try:
        await set_json(
            redis_key,
            {"service": body.service_name, "rtid": record.id},
            ttl=ttl_seconds,
        )
        logger.info(
            f"[tokens] Access token stored in Redis (ttl={ttl_seconds}s) "
            f"for service='{body.service_name}'"
        )
    except Exception as exc:
        logger.warning(f"[tokens] Could not store access token in Redis: {exc}")

    # Prune old access tokens
    await _prune_access_tokens(record.id)

    logger.info(f"[tokens] Access token refreshed for service='{body.service_name}'")

    return TokenRefreshResponse(
        service_name=body.service_name,
        access_token=access_token_value,
        access_token_expires_minutes=ACCESS_TOKEN_EXPIRE_MINUTES,
        access_token_expires_at=expiration,
    )


# ─── POST /auth/token/revoke ──────────────────────────────────────────────────


@router.post(
    "/token/revoke",
    response_model=TokenRevokeResponse,
    summary="Révoquer le refresh token d'un service (admin uniquement)",
    openapi_extra={"security": [{"AdminCle": []}]},
)
async def revoke_token(
    body: TokenRevokeRequest,
    _: None = Depends(require_admin_key),
) -> TokenRevokeResponse:
    """
    Marque le refresh token d'un service comme inactif.
    Désactive également tous les access tokens associés et les supprime du cache Redis.
    """
    # 1. Deactivate refresh token(s) for this service
    refresh_records = await InfoRefreshToken.filter(
        nom_service=body.service_name, est_actif=True
    ).all()

    if not refresh_records:
        return TokenRevokeResponse(
            service_name=body.service_name,
            revoked=False,
            message="No active token found for this service.",
        )

    refresh_ids = [r.id for r in refresh_records]

    # Deactivate all refresh tokens
    await InfoRefreshToken.filter(id__in=refresh_ids).update(est_actif=False)

    # 2. Deactivate all linked access tokens
    deactivated_access = await InfoAccessToken.filter(
        id_refresh_token_id__in=refresh_ids, est_actif=True
    ).update(est_actif=False)

    # 2b. Remove all linked access tokens from Redis
    access_records = await InfoAccessToken.filter(
        id_refresh_token_id__in=refresh_ids
    ).all()
    for acc in access_records:
        redis_key = f"access_token:{acc.token}"
        try:
            await delete_key(redis_key)
        except Exception as exc:
            logger.warning(f"[tokens] Could not delete Redis key '{redis_key}': {exc}")
    logger.info(
        f"[tokens] Removed {len(access_records)} access token(s) from Redis "
        f"for service='{body.service_name}'"
    )

    logger.info(
        f"[tokens] Refresh token revoked for service='{body.service_name}' "
        f"({len(refresh_ids)} refresh, {deactivated_access} access tokens deactivated)"
    )

    return TokenRevokeResponse(
        service_name=body.service_name,
        revoked=True,
        message=(
            f"Refresh token for '{body.service_name}' has been revoked. "
            f"{deactivated_access} access token(s) deactivated."
        ),
    )


# ─── GET /auth/history ────────────────────────────────────────────────────────


@router.get(
    "/logs",
    response_model=ApiCallHistoryList,
    summary="Journal d'audit paginé des appels API (admin uniquement)",
    openapi_extra={"security": [{"AdminCle": []}]},
)
async def get_history(
    _: None = Depends(require_admin_key),
    page: int = Query(1, ge=1, description="Numéro de page (commence à 1)"),
    page_size: int = Query(50, ge=1, le=500, description="Nombre d'éléments par page"),
    service_name: str | None = Query(None, description="Filtrer par nom de service"),
) -> ApiCallHistoryList:
    """
    Retourne un journal d'audit paginé, du plus récent au plus ancien,
    de tous les appels API ayant transité par la gateway.
    """
    qs = ApiCallHistory.all()

    if service_name:
        qs = qs.filter(service_name=service_name)

    total = await qs.count()
    items = (
        await qs.order_by("-called_at").offset((page - 1) * page_size).limit(page_size)
    )

    return ApiCallHistoryList(
        total=total,
        page=page,
        page_size=page_size,
        items=[ApiCallHistoryEntry.model_validate(item) for item in items],
    )


# ─── GET /auth/token/refresh-tokens ──────────────────────────────────────────


@router.get(
    "/token/refresh-tokens",
    response_model=RefreshTokenList,
    response_model_exclude_none=True,
    summary="Lister les refresh tokens d'un service",
)
async def list_refresh_tokens(
    request: Request,
    service_name: str = Query(
        ..., description="Nom du service dont on veut lister les refresh tokens."
    ),
    active_only: bool = Query(
        True, description="Si true, retourne uniquement les tokens actifs."
    ),
) -> RefreshTokenList:
    """
    Retourne les refresh tokens enregistrés pour le service indiqué.

    **Champ `refresh` (corps prêt à l'emploi pour `/auth/token/refresh`) :**
    - ✅ **Inclus** uniquement lorsque l'appelant est connecté via la session de documentation (navigateur).
    - ❌ **Absent** pour les appels programmatiques (aucune session active).

    Ce champ peut être copié-collé directement dans `POST /auth/token/refresh`
    pour obtenir un nouvel access token sans avoir à ressaisir manuellement les valeurs.
    """
    qs = InfoRefreshToken.all().filter(nom_service=service_name)

    if active_only:
        qs = qs.filter(est_actif=True)

    records = await qs.order_by("nom_service").all()

    # Only expose the ready-to-use refresh body when the caller is logged in
    # via the docs session (browser user). Programmatic API callers don't get it.
    is_docs_user = bool(request.session.get("user"))

    return RefreshTokenList(
        total=len(records),
        items=[
            RefreshTokenEntry(
                id=r.id,
                service_name=r.nom_service,
                token=r.token,
                date_creation=r.date_creation,
                ip_creation=r.ip_creation,
                est_actif=r.est_actif,
                refresh=(
                    TokenRefreshRequest(
                        service_name=r.nom_service,
                        refresh_token=r.token,
                    )
                    if is_docs_user
                    else None
                ),
            )
            for r in records
        ],
    )


# ─── GET /auth/token/all-refresh-tokens (admin) ───────────────────────────────


@router.get(
    "/token/all-refresh-tokens",
    response_model=RefreshTokenList,
    summary="Lister tous les refresh tokens — tous services (admin uniquement)",
    openapi_extra={"security": [{"AdminCle": []}]},
)
async def list_all_refresh_tokens(
    _: None = Depends(require_admin_key),
    active_only: bool = Query(
        None,
        description=(
            "Filtrer par statut. "
            "`true` = actifs uniquement, `false` = inactifs uniquement, "
            "absent = tous les tokens."
        ),
    ),
) -> RefreshTokenList:
    """
    Retourne les refresh tokens de **tous** les services enregistrés.

    - Le filtre `active_only` est **optionnel** : s'il est absent, tous les tokens
      sont retournés (actifs et inactifs).
    - Résultats triés par nom de service puis par date de création décroissante.
    """
    qs = InfoRefreshToken.all()

    if active_only is not None:
        qs = qs.filter(est_actif=active_only)

    records = await qs.order_by("nom_service", "-date_creation").all()

    return RefreshTokenList(
        total=len(records),
        items=[
            RefreshTokenEntry(
                id=r.id,
                service_name=r.nom_service,
                token=r.token,
                date_creation=r.date_creation,
                ip_creation=r.ip_creation,
                est_actif=r.est_actif,
            )
            for r in records
        ],
    )
