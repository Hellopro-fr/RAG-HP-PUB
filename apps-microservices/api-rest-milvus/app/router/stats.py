from fastapi import APIRouter, HTTPException, Body, Request
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Set
from pymilvus import Collection, utility
from app.core.api_rest_milvus import get_loaded_collection
import asyncio
import json
import time
import logging
from urllib.parse import urlparse

# Logger
logger = logging.getLogger(__name__)

router = APIRouter()

# --- CACHE CONFIGURATION (Stale-While-Revalidate) ---
CACHE_KEY = "milvus:global_stats:v1"
CACHE_LOCK_KEY = "milvus:global_stats:lock"
CACHE_FRESH_TTL = 600      # 10 min : en-dessous, on sert sans rafraîchir
CACHE_STALE_TTL = 3600     # 1h : au-delà, on refait un scan synchrone
CACHE_LOCK_TTL = 300       # 5 min : empêche les scans parallèles
CACHE_REDIS_TTL = 7200     # 2h : TTL physique Redis (> CACHE_STALE_TTL pour sécurité)

# --- CONFIGURATION (Adaptée du script) ---
# Note: Les infos de connexion (Host/Port) sont gérées par la config globale de l'app ou la connexion existante
# Mais pour rester fidèle au script, on utilise les constantes pour les noms de champs.
COLLECTION_NAME = "siteweb_2"
DOMAINE_FIELD_NAME = "domaine"
URL_FIELD_NAME = "url"
FILTER_FIELD_NAME = "page_type"
PRIMARY_KEY_FIELD_NAME = "id"
BATCH_SIZE = 16384

# --- MODÈLES PYDANTIC ---

class StatsRequest(BaseModel):
    """Modèle de requête pour l'analyse globale."""
    domains: Optional[List[str]] = Field(
        default=None,
        description="Liste optionnelle de domaines pour filtrer l'analyse. Si vide, analyse tout."
    )

class StatsResponse(BaseModel):
    """Modèle de réponse avec les statistiques."""
    execution_time_seconds: float
    total_domains: int
    domains_with_header: int
    domains_with_footer: int
    domains_no_structure: int
    unique_content_urls: int
    details: Optional[Dict] = None

# --- LOGIQUE MÉTIER ---

def _clean_domain(domain: str) -> str:
    """Nettoie un nom de domaine (enlève www., protocole, etc)."""
    if not domain:
        return ""
    parsed = urlparse(domain if '://' in domain else f'https://{domain}')
    clean = parsed.netloc or parsed.path
    return clean.replace('www.', '')

async def _run_global_analysis(guard, domains_filter: Optional[List[str]]) -> Dict:
    """Exécute l'analyse globale sur Milvus."""

    # Vérification collection
    if not utility.has_collection(COLLECTION_NAME):
        raise HTTPException(status_code=404, detail=f"La collection '{COLLECTION_NAME}' n'existe pas.")

    collection = get_loaded_collection(COLLECTION_NAME)

    # Préparation du filtre domaines
    target_domains = set()
    if domains_filter:
        for d in domains_filter:
            cleaned = _clean_domain(d)
            if cleaned:
                target_domains.add(cleaned)

    # Sets pour le comptage
    all_domains_seen = set()
    domains_with_header = set()
    domains_with_footer = set()
    unique_content_urls = set()

    base_filter_expression = "chunk_number == 1"
    last_pk = None
    total_processed = 0

    start_time = time.time()
    logger.info(f"Démarrage analyse globale. Filtre domaines: {len(target_domains) if target_domains else 'Aucun'}")

    try:
        while True:
            current_filter = base_filter_expression
            if last_pk is not None:
                current_filter += f" and {PRIMARY_KEY_FIELD_NAME} > {last_pk}"

            async with guard.slot():
                results = await asyncio.to_thread(
                    collection.query,
                    expr=current_filter,
                    offset=0,
                    limit=BATCH_SIZE,
                    output_fields=[URL_FIELD_NAME, PRIMARY_KEY_FIELD_NAME, FILTER_FIELD_NAME, DOMAINE_FIELD_NAME],
                    sorted_by_field=PRIMARY_KEY_FIELD_NAME,  # Important pour la pagination
                    asc=True
                )

            if not results:
                break

            for entity in results:
                url = entity.get(URL_FIELD_NAME)
                page_type = entity.get(FILTER_FIELD_NAME)
                url_domain = entity.get(DOMAINE_FIELD_NAME, "")

                # Nettoyage domaine entité
                if url_domain:
                    url_domain = url_domain.replace('www.', '')

                if not url_domain:
                    # On met à jour last_pk même si on saute l'entité
                    last_pk = entity[PRIMARY_KEY_FIELD_NAME]
                    continue

                # Filtrage domaine
                if target_domains:
                    is_in_filter = False
                    # Vérification exacte ou sous-domaine
                    if url_domain in target_domains:
                        is_in_filter = True
                    else:
                        # Vérification suffixe (ex: blog.site.com pour site.com)
                        for td in target_domains:
                            if url_domain.endswith('.' + td):
                                is_in_filter = True
                                break

                    if not is_in_filter:
                        last_pk = entity[PRIMARY_KEY_FIELD_NAME]
                        continue

                # Enregistrement statistiques
                all_domains_seen.add(url_domain)

                if page_type == 'header':
                    domains_with_header.add(url_domain)
                elif page_type == 'footer':
                    domains_with_footer.add(url_domain)
                else:
                    unique_content_urls.add(url)

                # Mise à jour PK pour la prochaine itération
                last_pk = entity[PRIMARY_KEY_FIELD_NAME]

            total_processed += len(results)
            # logger.info(f"Analyse en cours... {total_processed} traités")

    except Exception as e:
        logger.error(f"Erreur durant l'analyse Milvus: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur analyse Milvus: {str(e)}")

    end_time = time.time()
    execution_time = end_time - start_time

    domains_without_structure = all_domains_seen - domains_with_header - domains_with_footer

    return {
        "execution_time_seconds": round(execution_time, 2),
        "total_domains": len(all_domains_seen),
        "domains_with_header": len(domains_with_header),
        "domains_with_footer": len(domains_with_footer),
        "domains_no_structure": len(domains_without_structure),
        "unique_content_urls": len(unique_content_urls)
    }

# --- CACHE LAYER (Stale-While-Revalidate) ---

async def _background_refresh(guard, redis_client) -> None:
    """
    Recalcule les stats en arrière-plan et met à jour le cache Redis.
    Protégé par un lock Redis pour empêcher les scans parallèles.
    """
    lock_acquired = await redis_client.set(
        CACHE_LOCK_KEY, "1", nx=True, ex=CACHE_LOCK_TTL
    )
    if not lock_acquired:
        logger.debug("global-stats refresh already in progress, skipping")
        return

    try:
        logger.info("global-stats background refresh started")
        result = await _run_global_analysis(guard=guard, domains_filter=None)
        result["computed_at"] = time.time()
        await redis_client.set(CACHE_KEY, json.dumps(result), ex=CACHE_REDIS_TTL)
        logger.info(
            "global-stats background refresh done in %.1fs",
            result.get("execution_time_seconds", 0)
        )
    except Exception as e:
        logger.error("global-stats background refresh failed: %s", e)
    finally:
        await redis_client.delete(CACHE_LOCK_KEY)


async def _get_cached_or_scan(guard, redis_client) -> Dict:
    """
    Retourne les stats cachées (fresh ou stale) ou relance un scan si nécessaire.

    Cas :
      - Fresh (<600s)            → retour immédiat
      - Stale (600-3600s)        → retour immédiat + refresh async
      - Missing ou trop vieux    → scan synchrone (avec lock pour éviter concurrents)
    """
    raw = await redis_client.get(CACHE_KEY)
    if raw:
        try:
            cached = json.loads(raw)
            age = time.time() - cached.get("computed_at", 0)

            if age < CACHE_FRESH_TTL:
                logger.debug("global-stats cache hit (fresh, age=%.0fs)", age)
                return cached

            if age < CACHE_STALE_TTL:
                logger.info("global-stats cache hit (stale, age=%.0fs) — triggering async refresh", age)
                asyncio.create_task(_background_refresh(guard, redis_client))
                return cached

            logger.info("global-stats cache too old (age=%.0fs) — forcing sync rescan", age)
        except (json.JSONDecodeError, TypeError, KeyError) as e:
            logger.warning("global-stats cache parse error: %s — forcing rescan", e)

    # Cache absent ou périmé : scan synchrone, protégé par lock
    lock_acquired = await redis_client.set(
        CACHE_LOCK_KEY, "1", nx=True, ex=CACHE_LOCK_TTL
    )

    if not lock_acquired:
        # Un autre process scanne déjà : on attend sa valeur (polling 2s, max 200s)
        logger.info("global-stats scan in progress elsewhere — waiting for result")
        for _ in range(100):
            await asyncio.sleep(2)
            raw = await redis_client.get(CACHE_KEY)
            if raw:
                try:
                    cached = json.loads(raw)
                    return cached
                except json.JSONDecodeError:
                    pass
        # Timeout : on retente tout de même le scan nous-même (lock probablement stale)
        logger.warning("global-stats lock wait timed out — forcing rescan")

    try:
        result = await _run_global_analysis(guard=guard, domains_filter=None)
        result["computed_at"] = time.time()
        await redis_client.set(CACHE_KEY, json.dumps(result), ex=CACHE_REDIS_TTL)
        return result
    finally:
        await redis_client.delete(CACHE_LOCK_KEY)


async def prewarm_cache(guard, redis_client) -> None:
    """
    Déclenche un scan initial au démarrage du microservice si le cache est vide.
    Appelé depuis main.py lifespan. Fire-and-forget.
    """
    try:
        existing = await redis_client.get(CACHE_KEY)
        if existing:
            logger.info("global-stats cache already warm, skipping prewarm")
            return
        logger.info("global-stats prewarm starting (background)")
        await _background_refresh(guard, redis_client)
    except Exception as e:
        logger.warning("global-stats prewarm failed: %s", e)


# --- ENDPOINT ---

@router.post(
    "/global-stats",
    response_model=StatsResponse,
    summary="Statistiques globales des domaines dans Milvus",
    description="""
    Realise une analyse complète de la collection 'siteweb_2' pour extraire des statistiques consolidées :
    - Nombre total de domaines
    - Domaines avec Header / Footer détectés
    - Domaines sans structure détectée
    - Nombre d'URLs de contenu unique

    Cache Stale-While-Revalidate (Redis) : réponse <500ms en conditions normales, scan
    complet uniquement toutes les 10 min en arrière-plan. Le filtre `domains` (non vide)
    bypass le cache et déclenche un scan synchrone.
    """
)
async def get_global_stats(http_request: Request, request: StatsRequest):
    """
    Endpoint async that wraps each Milvus batch query with the concurrency guard.
    Sert depuis le cache Redis (SWR) si `domains` est vide, sinon scan direct.
    """
    guard = http_request.app.state.concurrency_guard
    redis_client = getattr(http_request.app.state, "redis_client", None)

    # Cas "filtre par domaines" ou Redis indisponible → comportement historique (scan direct)
    if request.domains or redis_client is None:
        return await _run_global_analysis(guard=guard, domains_filter=request.domains)

    return await _get_cached_or_scan(guard=guard, redis_client=redis_client)
