# ==============================================================================
# ENDPOINT DE VÉRIFICATION D'URLS DANS MILVUS
# Reproduit la logique du script 2_check_urls_in_milvus.py
# ==============================================================================

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Set
from pymilvus import Collection, utility
from app.core.api_rest_milvus import get_loaded_collection

from common_utils.database.config.settings import Configuration

import asyncio
import logging
import time

logger = logging.getLogger(__name__)

router = APIRouter()

# --- CONFIGURATION ---
COLLECTION_NAME = "siteweb_2"
URL_FIELD_NAME = "url"
FILTER_FIELD_NAME = "page_type"
CHUNK_SIZE = 500  # Taille des batchs pour la clause IN


# --- SCHEMAS PYDANTIC ---

class CheckUrlsRequest(BaseModel):
    """Modèle de requête pour la vérification d'URLs."""
    urls_by_domain: Dict[str, List[str]] = Field(
        ...,
        description="Dictionnaire avec les domaines comme clés et les listes d'URLs comme valeurs",
        json_schema_extra={
            "example": {
                "example.com": [
                    "https://example.com/page1",
                    "https://example.com/page2"
                ],
                "autre-domaine.fr": [
                    "https://autre-domaine.fr/produit/123"
                ]
            }
        }
    )
    report_header_footer: bool = Field(
        default=False,
        description="Inclure un rapport détaillé sur les header/footer par domaine"
    )
    collection_name: Optional[str] = Field(
        default=COLLECTION_NAME,
        description=f"Nom de la collection Milvus (défaut: {COLLECTION_NAME})"
    )


class HeaderFooterStatus(BaseModel):
    """Statut header/footer pour un domaine."""
    has_header: bool
    has_footer: bool


class HeaderFooterSummary(BaseModel):
    """Résumé du rapport header/footer."""
    total_domains: int
    missing_header: int
    missing_footer: int
    missing_both: int


class HeaderFooterReport(BaseModel):
    """Rapport complet header/footer."""
    summary: HeaderFooterSummary
    by_domain: Dict[str, HeaderFooterStatus]


class FoundUrlEntry(BaseModel):
    """Entrée d'URL trouvée avec son page_type."""
    url: str
    page_type: str


class CheckUrlsResponse(BaseModel):
    """Modèle de réponse pour la vérification d'URLs."""
    status: str = "success"
    missing_urls: Dict[str, List[str]] = Field(
        ...,
        description="Dictionnaire des URLs manquantes par domaine"
    )
    header_footer_report: Optional[HeaderFooterReport] = Field(
        default=None,
        description="Rapport header/footer (si demandé)"
    )
    statistics: Dict = Field(
        default_factory=dict,
        description="Statistiques de la vérification"
    )
    found_urls_by_domain: Optional[Dict[str, List[FoundUrlEntry]]] = Field(
        default=None,
        description="URLs trouvées par domaine avec leur page_type (hors header/footer)"
    )


# --- FONCTIONS UTILITAIRES ---

def _generate_url_variants(url: str) -> List[str]:
    """
    Génère les variantes d'une URL pour une recherche tolérante dans Milvus.

    Variantes générées (dédupliquées) :
      - L'URL brute
      - Avec/sans slash final

    Nécessaire car Milvus stocke les URLs selon le format exact envoyé à
    l'ingestion, mais les consommateurs (scripts BO, healing) peuvent envoyer
    une forme normalisée (trailing slash retiré). Sans cette tolérance, des
    URLs pourtant présentes dans Milvus sont déclarées "missing".

    NOTE : la tolérance www/non-www a été retirée volontairement car elle
    doublait le volume de variantes sans bénéfice réel (le crawler stocke
    les URLs de façon cohérente sur www) et saturait le concurrency_guard
    Milvus (MILVUS_GLOBAL_MAX_CONCURRENT=30). Si un mismatch www apparaît,
    il se verra dans le reporting et on pourra réévaluer.
    """
    variants = {url}
    if url.endswith('/'):
        variants.add(url.rstrip('/'))
    else:
        variants.add(url + '/')
    return list(variants)


async def _check_urls_batch(guard, collection: Collection, urls_to_check: List[str]) -> Dict:
    """
    Vérifie une liste d'URLs dans Milvus avec tolérance de normalisation.

    Chaque URL est étendue en plusieurs variantes (slash/www) pour retrouver
    les entrées présentes sous une forme légèrement différente.

    Retourne:
    - found_urls: Set[str] - URLs originales trouvées (hors header/footer)
    - found_urls_page_type: Dict[str, str] - mapping URL originale → page_type
    - has_header: bool
    - has_footer: bool
    """
    found_urls: Set[str] = set()
    found_urls_page_type: Dict[str, str] = {}
    found_urls_exact: Dict[str, bool] = {}
    has_header = False
    has_footer = False

    # Mapping variante → URLs originales qui ont généré cette variante
    variant_to_originals: Dict[str, Set[str]] = {}
    all_variants: Set[str] = set()

    for url in urls_to_check:
        for variant in _generate_url_variants(url):
            variant_to_originals.setdefault(variant, set()).add(url)
            all_variants.add(variant)

    all_variants_list = list(all_variants)
    total = len(all_variants_list)

    for i in range(0, total, CHUNK_SIZE):
        batch = all_variants_list[i:i + CHUNK_SIZE]

        # Echapper les backslashes PUIS les guillemets simples dans les URLs
        # Important: échapper \ d'abord, sinon on double-échappe les \' qu'on vient d'ajouter
        batch_escaped = [u.replace("\\", "\\\\").replace("'", "\\'") for u in batch]
        urls_str = ", ".join([f"'{u}'" for u in batch_escaped])

        # Filtre chunk_number == 1 pour éviter les doublons
        expr = f"{URL_FIELD_NAME} in [{urls_str}] and chunk_number == 1"

        try:
            async with guard.slot():
                results = await asyncio.to_thread(
                    collection.query,
                    expr=expr,
                    output_fields=[URL_FIELD_NAME, FILTER_FIELD_NAME],
                    consistency_level="Strong"
                )

            for entity in results:
                url_found = entity[URL_FIELD_NAME]
                page_type = entity.get(FILTER_FIELD_NAME, "")

                if page_type == 'header':
                    has_header = True
                elif page_type == 'footer':
                    has_footer = True

                # On considère trouvé si ce n'est pas header/footer.
                # L'URL trouvée peut être une variante : on marque comme trouvées
                # toutes les URLs originales qui ont généré cette variante.
                if page_type not in ['header', 'footer']:
                    originals = variant_to_originals.get(url_found, set())
                    found_urls.update(originals)
                    for orig in originals:
                        is_exact = (url_found == orig)
                        current = found_urls_page_type.get(orig, "")
                        current_exact = found_urls_exact.get(orig, False)
                        # Priorite : le page_type d'un match EXACT (url_found == url demandee)
                        # prime sur celui d'une variante (ex. /x/=fiche_produit doit gagner
                        # sur /x=article). On (re)affecte si rien trouve, ou si on obtient un
                        # match exact alors que la valeur courante venait d'une variante.
                        if current == "" or (is_exact and not current_exact):
                            found_urls_page_type[orig] = page_type
                            found_urls_exact[orig] = is_exact

        except Exception as e:
            logger.error(f"Erreur lors de la requête Milvus: {e}")
            raise

    return {
        "found_urls": found_urls,
        "found_urls_page_type": found_urls_page_type,
        "has_header": has_header,
        "has_footer": has_footer
    }


# --- ENDPOINT ---

@router.post(
    "/check-urls-existence",
    response_model=CheckUrlsResponse,
    summary="Vérifie l'existence d'URLs dans Milvus",
    description="""
Vérifie si les URLs fournies existent dans la collection Milvus (hors header/footer).

**Fonctionnalités:**
- Vérification par batch optimisée (chunks de 500 URLs)
- Exclusion automatique des pages header/footer du comptage
- Rapport optionnel sur la présence de header/footer par domaine
- Support de plusieurs domaines en une seule requête

**Performance:**
- Utilise la connexion directe pymilvus
- Optimisé pour de grandes listes d'URLs

**Cas d'usage:**
- Détecter les URLs manquantes avant réingestion
- Vérifier la complétude de l'indexation d'un site
"""
)
async def check_urls_existence(http_request: Request, request: CheckUrlsRequest):
    """
    Vérifie l'existence des URLs dans Milvus.

    Reproduit la logique du script 2_check_urls_in_milvus.py pour être appelé
    depuis le Back Office sans connexion directe à Milvus.
    """
    start_time = time.time()

    collection_name = request.collection_name or COLLECTION_NAME

    # Vérifier si la collection existe
    if not utility.has_collection(collection_name):
        raise HTTPException(
            status_code=404,
            detail=f"Collection '{collection_name}' introuvable dans Milvus."
        )

    try:
        collection = get_loaded_collection(collection_name)
    except Exception as e:
        logger.error(f"Erreur lors du chargement de la collection: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Erreur lors du chargement de la collection: {str(e)}"
        )

    guard = http_request.app.state.concurrency_guard

    missing_urls_by_domain: Dict[str, List[str]] = {}
    header_footer_status: Dict[str, HeaderFooterStatus] = {}
    found_urls_by_domain: Dict[str, List[FoundUrlEntry]] = {}

    total_urls_count = sum(len(urls) for urls in request.urls_by_domain.values())
    total_domains = len(request.urls_by_domain)
    processed_urls = 0
    total_found = 0
    total_missing = 0

    logger.info(f"Démarrage vérification: {total_urls_count} URLs dans {total_domains} domaines")

    for domain, urls in request.urls_by_domain.items():
        if not urls:
            missing_urls_by_domain[domain] = []
            if request.report_header_footer:
                header_footer_status[domain] = HeaderFooterStatus(
                    has_header=False,
                    has_footer=False
                )
            continue

        # Dédupliquer les URLs
        urls_unique = list(set(urls))

        try:
            # Vérification dans Milvus
            result = await _check_urls_batch(guard, collection, urls_unique)

            found_urls = result["found_urls"]
            missing = set(urls_unique) - found_urls

            if missing:
                missing_urls_by_domain[domain] = sorted(list(missing))
                total_missing += len(missing)

            total_found += len(found_urls)

            if request.report_header_footer:
                header_footer_status[domain] = HeaderFooterStatus(
                    has_header=result["has_header"],
                    has_footer=result["has_footer"]
                )

            # Agréger found_urls_page_type par domaine
            fpt = result["found_urls_page_type"]
            if fpt:
                found_urls_by_domain[domain] = [
                    FoundUrlEntry(url=u, page_type=pt) for u, pt in fpt.items()
                ]

            processed_urls += len(urls)

        except Exception as e:
            logger.error(f"Erreur pour le domaine {domain}: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Erreur lors de la vérification du domaine '{domain}': {str(e)}"
            )
    
    elapsed_time = time.time() - start_time
    
    # Construire la réponse
    response_data = {
        "status": "success",
        "missing_urls": missing_urls_by_domain,
        "statistics": {
            "total_domains": total_domains,
            "total_urls_checked": total_urls_count,
            "total_found": total_found,
            "total_missing": total_missing,
            "domains_with_missing_urls": len(missing_urls_by_domain),
            "processing_time_seconds": round(elapsed_time, 2)
        }
    }
    
    # Ajouter le rapport header/footer si demandé
    if request.report_header_footer:
        missing_header = sum(1 for v in header_footer_status.values() if not v.has_header)
        missing_footer = sum(1 for v in header_footer_status.values() if not v.has_footer)
        missing_both = sum(1 for v in header_footer_status.values() if not v.has_header and not v.has_footer)
        
        response_data["header_footer_report"] = HeaderFooterReport(
            summary=HeaderFooterSummary(
                total_domains=total_domains,
                missing_header=missing_header,
                missing_footer=missing_footer,
                missing_both=missing_both
            ),
            by_domain=header_footer_status
        )
    
    # Ajouter found_urls_by_domain si des URLs ont été trouvées
    if found_urls_by_domain:
        response_data["found_urls_by_domain"] = found_urls_by_domain

    logger.info(f"Vérification terminée en {elapsed_time:.2f}s - {total_found} trouvées, {total_missing} manquantes")

    return CheckUrlsResponse(**response_data)


# --- SCHEMA POUR ENDPOINT SIMPLE ---

class CheckUrlsSimpleRequest(BaseModel):
    """Modèle de requête pour la vérification simple d'URLs."""
    urls: List[str] = Field(
        ...,
        description="Liste des URLs à vérifier",
        json_schema_extra={
            "example": [
                "https://example.com/page1",
                "https://example.com/page2"
            ]
        }
    )
    collection_name: Optional[str] = Field(
        default=COLLECTION_NAME,
        description=f"Nom de la collection Milvus (défaut: {COLLECTION_NAME})"
    )


@router.post(
    "/check-urls-existence/simple",
    summary="Vérification simple d'une liste d'URLs",
    description="Version simplifiée pour vérifier une liste d'URLs sans groupement par domaine."
)
async def check_urls_simple(http_request: Request, request: CheckUrlsSimpleRequest):
    """
    Version simplifiée pour vérifier une liste d'URLs directement.
    Retourne uniquement les URLs trouvées et manquantes.
    """
    if not request.urls:
        return {
            "status": "success",
            "found_urls": [],
            "missing_urls": [],
            "count": {"found": 0, "missing": 0, "total": 0}
        }

    collection_name = request.collection_name or COLLECTION_NAME

    if not utility.has_collection(collection_name):
        raise HTTPException(
            status_code=404,
            detail=f"Collection '{collection_name}' introuvable."
        )

    try:
        collection = get_loaded_collection(collection_name)
        guard = http_request.app.state.concurrency_guard

        urls_unique = list(set(request.urls))
        result = await _check_urls_batch(guard, collection, urls_unique)

        found_urls = sorted(list(result["found_urls"]))
        missing_urls = sorted(list(set(urls_unique) - result["found_urls"]))

        return {
            "status": "success",
            "found_urls": found_urls,
            "missing_urls": missing_urls,
            "count": {
                "found": len(found_urls),
                "missing": len(missing_urls),
                "total": len(urls_unique)
            }
        }

    except Exception as e:
        logger.error(f"Erreur lors de la vérification: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Erreur: {str(e)}"
        )

