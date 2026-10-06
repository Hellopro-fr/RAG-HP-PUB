"""
API REST (FastAPI) du service de normalisation dynamique.

Exposée pour les consommateurs HTTP (matching_prix.php, scripts externes) en plus
du contrat gRPC historique. Toutes les routes lisent l'état courant du normalizer
(rechargeable à chaud) ; aucune logique métier dupliquée — délégation au use_case.

Endpoints :
  POST /normalize/quantity   — normalise une valeur+unité
  POST /normalize/range      — normalise un intervalle min/max
  POST /normalize/batch      — lot de quantités
  POST /normalize/compare    — compare 2 quantités après normalisation (matching prix)
  POST /admin/reload         — recharge le référentiel (auth token optionnel)
  GET  /health               — liveness
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any, Awaitable, Callable, Dict, List, Optional

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from application.normalization_use_case import NormalizationUseCase
from app.config import settings

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Schémas
# --------------------------------------------------------------------------- #
class QuantityRequest(BaseModel):
    label: str = ""
    unit: Optional[str] = None
    value: Any
    data_type: str = "numeric"


class QuantityResponse(BaseModel):
    success: bool
    valeur_canonique: Optional[float] = None
    unite_canonique: Optional[str] = None
    error_message: str = ""


class RangeRequest(BaseModel):
    label: str = ""
    unit: Optional[str] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None


class RangeResponse(BaseModel):
    success: bool
    valeur_min_canonique: Optional[float] = None
    valeur_max_canonique: Optional[float] = None
    unite_canonique: Optional[str] = None
    error_message: str = ""


class BatchRequest(BaseModel):
    items: List[QuantityRequest]


class CompareRequest(BaseModel):
    """
    Compare une quantité produit (a) à une contrainte de référence (b) après
    normalisation canonique. Utilisé par le Matching prix quand les unités diffèrent.
    operator :
      - "gte" : match si value_a >= value_b   (ex. contrainte « ≥ »)
      - "lte" : match si value_a <= value_b   (ex. contrainte « ≤ »)
      - "eq"  : match si |value_a - value_b| <= tolerance * |value_b|
    """
    label: str = ""
    value_a: float
    unit_a: Optional[str] = None
    value_b: float
    unit_b: Optional[str] = None
    operator: str = "eq"
    tolerance: float = 0.01  # ±1 % par défaut pour "eq"


class CompareResponse(BaseModel):
    match: bool
    comparable: bool  # False si une normalisation a échoué ou dimensions incompatibles
    canonical_a: Optional[float] = None
    canonical_b: Optional[float] = None
    unite_canonique: Optional[str] = None
    raison: str = ""


class ReloadResponse(BaseModel):
    success: bool
    counts: Dict[str, Any] = {}
    error_message: str = ""


class ValidateRequest(BaseModel):
    """Gate 1 du learner : valide des lignes proposées contre le VRAI moteur.
    `proposed` est au format sections (definitions/unite_dimension/label_dimension/
    dimension_canonique/reecriture/preprocessing) fusionné au référentiel courant.
    `values` : toutes les valeurs à valider (min ET max d'une plage) en UN appel.
    `value` est accepté en rétro-compat (équivaut à values=[value])."""
    proposed: Dict[str, Any] = {}
    label: str = ""
    unit: Optional[str] = None
    values: Optional[List[Any]] = None
    value: Any = None


class ValidateResponse(BaseModel):
    ok: bool                      # True si la proposition rend TOUTES les valeurs normalisables
    valeur_canonique: Optional[float] = None
    unite_canonique: Optional[str] = None


def create_app(
    use_case: NormalizationUseCase,
    reload_fn: Callable[[], Awaitable[Dict[str, Any]]],
) -> FastAPI:
    """
    Construit l'app FastAPI.
    `reload_fn` : coroutine qui re-fetch le référentiel BO v2 puis swap l'état,
    retourne les compteurs. Injectée par main.py (qui détient le loader + normalizer).
    """

    async def _refresh_loop() -> None:
        """Rafraîchit périodiquement le référentiel (cache TTL). Ne crashe jamais."""
        interval = settings.REFERENTIEL_TTL_SECONDS
        while True:
            await asyncio.sleep(interval)
            try:
                counts = await reload_fn()
                logger.info("Refresh TTL référentiel OK: %s", counts)
            except Exception as exc:
                logger.warning("Refresh TTL référentiel échoué (on garde l'état courant): %s", exc)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        task: Optional[asyncio.Task] = None
        if settings.REFERENTIEL_TTL_SECONDS > 0:
            task = asyncio.create_task(_refresh_loop())
        yield
        if task is not None:
            task.cancel()

    app = FastAPI(
        title="graph-rag-normalize-unite-service-dynamique",
        lifespan=lifespan,
    )

    @app.get("/health")
    async def health() -> Dict[str, str]:
        return {"status": "ok"}

    @app.post("/normalize/quantity", response_model=QuantityResponse)
    async def normalize_quantity(req: QuantityRequest) -> QuantityResponse:
        result = use_case.normalize_quantity(req.label, req.unit, req.value, req.data_type)
        if result:
            return QuantityResponse(
                success=True,
                valeur_canonique=result.get("valeur_canonique"),
                unite_canonique=result.get("unite_canonique"),
            )
        return QuantityResponse(
            success=False,
            error_message=f"Could not normalize value for label '{req.label}'",
        )

    @app.post("/normalize/range", response_model=RangeResponse)
    async def normalize_range(req: RangeRequest) -> RangeResponse:
        result = use_case.normalize_range(req.label, req.unit, req.min_value, req.max_value)
        if result:
            return RangeResponse(
                success=True,
                valeur_min_canonique=result.get("valeur_min_canonique"),
                valeur_max_canonique=result.get("valeur_max_canonique"),
                unite_canonique=result.get("unite_canonique"),
            )
        return RangeResponse(
            success=False,
            error_message=f"Could not normalize range for label '{req.label}'",
        )

    @app.post("/normalize/batch", response_model=List[QuantityResponse])
    async def normalize_batch(req: BatchRequest) -> List[QuantityResponse]:
        responses: List[QuantityResponse] = []
        for item in req.items:
            result = use_case.normalize_quantity(
                item.label, item.unit, item.value, item.data_type
            )
            if result:
                responses.append(
                    QuantityResponse(
                        success=True,
                        valeur_canonique=result.get("valeur_canonique"),
                        unite_canonique=result.get("unite_canonique"),
                    )
                )
            else:
                responses.append(
                    QuantityResponse(
                        success=False,
                        error_message=f"Could not normalize value for label '{item.label}'",
                    )
                )
        return responses

    @app.post("/normalize/compare", response_model=CompareResponse)
    async def normalize_compare(req: CompareRequest) -> CompareResponse:
        norm_a = use_case.normalize_quantity(req.label, req.unit_a, req.value_a, "numeric")
        norm_b = use_case.normalize_quantity(req.label, req.unit_b, req.value_b, "numeric")

        if not norm_a or not norm_b:
            return CompareResponse(
                match=False,
                comparable=False,
                raison="normalisation impossible d'un des deux côtés",
            )

        unite_a = norm_a.get("unite_canonique")
        unite_b = norm_b.get("unite_canonique")
        if unite_a != unite_b:
            return CompareResponse(
                match=False,
                comparable=False,
                canonical_a=norm_a.get("valeur_canonique"),
                canonical_b=norm_b.get("valeur_canonique"),
                raison=f"dimensions incompatibles ({unite_a} vs {unite_b})",
            )

        a = norm_a["valeur_canonique"]
        b = norm_b["valeur_canonique"]
        op = req.operator.lower()
        if op == "gte":
            match = a >= b
        elif op == "lte":
            match = a <= b
        elif op == "eq":
            match = abs(a - b) <= req.tolerance * abs(b) if b != 0 else a == 0
        else:
            return CompareResponse(
                match=False, comparable=False, raison=f"opérateur inconnu '{req.operator}'"
            )

        return CompareResponse(
            match=match,
            comparable=True,
            canonical_a=a,
            canonical_b=b,
            unite_canonique=unite_a,
        )

    @app.post("/admin/validate", response_model=ValidateResponse)
    async def admin_validate(req: ValidateRequest) -> ValidateResponse:
        values = req.values if req.values is not None else ([req.value] if req.value is not None else [])
        result = use_case.normalizer.validate_proposed(req.proposed, req.label, req.unit, values)
        return ValidateResponse(
            ok=bool(result.get("ok")),
            valeur_canonique=result.get("valeur_canonique"),
            unite_canonique=result.get("unite_canonique"),
        )

    @app.post("/admin/reload", response_model=ReloadResponse)
    async def admin_reload(x_reload_token: str = Header(default="")) -> ReloadResponse:
        if settings.RELOAD_AUTH_TOKEN and x_reload_token != settings.RELOAD_AUTH_TOKEN:
            raise HTTPException(status_code=401, detail="invalid reload token")
        try:
            counts = await reload_fn()
            return ReloadResponse(success=True, counts=counts)
        except Exception as exc:
            logger.error("Reload échoué: %s", exc, exc_info=True)
            return ReloadResponse(success=False, error_message=str(exc))

    return app
