"""
Entrypoint du service de normalisation dynamique.

- Charge le référentiel depuis le BO v2 au démarrage (fail-fast avec quelques retries :
  un référentiel vide ne normaliserait rien).
- Construit le normalizer rechargeable + use_case.
- Démarre le serveur gRPC (contrat historique) dans un thread démon.
- Démarre les métriques Prometheus.
- Lance l'API REST (FastAPI/uvicorn) en principal ; le refresh TTL tourne dans son lifespan.
"""

import asyncio
import logging
import threading
import time

import uvicorn

from common_utils.metrics.prometheus import start_metrics_server_in_thread

from app.config import settings
from application.normalization_use_case import NormalizationUseCase
from infrastructure.grpc_server import serve
from infrastructure.referentiel_loader import Referentiel, fetch_referentiel_from_bo
from infrastructure.rest_api import create_app
from infrastructure.unit_normalization_service import UnitNormalizationService

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

_STARTUP_MAX_RETRIES = 5
_STARTUP_RETRY_DELAY_SECONDS = 5


def _load_referentiel_with_retry() -> Referentiel:
    """Charge le référentiel au démarrage avec quelques retries (BO peut booter en parallèle)."""
    last_exc: Exception | None = None
    for attempt in range(1, _STARTUP_MAX_RETRIES + 1):
        try:
            return asyncio.run(fetch_referentiel_from_bo())
        except Exception as exc:
            last_exc = exc
            logger.warning(
                "Chargement référentiel échoué (tentative %s/%s): %s",
                attempt, _STARTUP_MAX_RETRIES, exc,
            )
            if attempt < _STARTUP_MAX_RETRIES:
                time.sleep(_STARTUP_RETRY_DELAY_SECONDS)
    raise RuntimeError(f"Impossible de charger le référentiel au démarrage: {last_exc}")


def main():
    start_metrics_server_in_thread(port=settings.PROMETHEUS_PORT)

    referentiel = _load_referentiel_with_retry()
    logger.info("Référentiel initial chargé: %s", referentiel.counts())

    normalizer = UnitNormalizationService(referentiel)
    use_case = NormalizationUseCase(normalizer)

    async def reload_fn():
        ref = await fetch_referentiel_from_bo()
        return normalizer.reload(ref)

    # Serveur gRPC (contrat inchangé) dans un thread démon, partage le normalizer.
    threading.Thread(target=serve, args=(use_case,), daemon=True, name="grpc-server").start()

    app = create_app(use_case, reload_fn)

    logger.info("Démarrage API REST sur le port %s...", settings.REST_PORT)
    uvicorn.run(app, host="0.0.0.0", port=settings.REST_PORT)


if __name__ == "__main__":
    main()
