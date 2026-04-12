from fastapi import APIRouter, HTTPException, Body, Request
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Set
from pymilvus import Collection, utility
from app.core.api_rest_milvus import get_loaded_collection
import asyncio
import time
import logging
from urllib.parse import urlparse

# Logger
logger = logging.getLogger(__name__)

router = APIRouter()

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
    
    ATTENTION : Cette opération scanne toute la collection (chunk_number=1). Elle peut prendre du temps sur de gros volumes.
    """
)
async def get_global_stats(http_request: Request, request: StatsRequest):
    """
    Endpoint async that wraps each Milvus batch query with the concurrency guard.
    """
    guard = http_request.app.state.concurrency_guard
    return await _run_global_analysis(guard=guard, domains_filter=request.domains)
