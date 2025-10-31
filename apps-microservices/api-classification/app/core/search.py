import requests
import httpx
import json
import logging
import asyncio
from typing import Any, Optional, List, Dict

# Imports depuis api-recherche (modules copiés dans le conteneur Docker via Dockerfile)
# Le Dockerfile copie les modules dans /app/shared_modules/api_recherche et ajoute ce chemin au PYTHONPATH
# Ces imports fonctionnent car le PYTHONPATH contient /app/shared_modules/api_recherche
from app.core.recherche import search_in_milvus
from app.schemas.search import SearchRequestWs, SourcesFiltre, RerankerOptions

logger = logging.getLogger(__name__)

# --- CONFIGURATION ---
EXTERNAL_PRODUCT_API_URL = "https://www.hellopro.fr/partenaires_externes/info_produit/get_info_produit.php"
EXTERNAL_CATEGORY_API_URL = "https://www.hellopro.fr/partenaires_externes/info_produit/get_info_categorie.php"

def get_product_details(product_ids: List[str], url: str) -> Optional[List[Dict[str, Any]]]:
    """
    Envoie un tableau d'ID de produits à un lien externe via une requête POST
    et retourne un tableau de détails de produits.
    """
    headers = {'Content-Type': 'application/json'}
    payload = {'id_produits': product_ids}

    try:
        response = requests.post(url, headers=headers, data=json.dumps(payload))
        response.raise_for_status()
        data = response.json()

        product_details = []
        if isinstance(data, dict):
            for product_id, product_name in data.items():
                product_details.append({
                    'id_produit': str(product_id),
                    'nom_produit': str(product_name)
                })
        else:
            logger.error(f"Format de réponse inattendu pour get_product_details: {data}")
            return None
        return product_details

    except requests.exceptions.RequestException as e:
        logger.error(f"Erreur dans get_product_details: {e}")
        return None
    except json.JSONDecodeError:
        logger.error("Erreur lors du décodage JSON dans get_product_details")
        return None

def get_category_details(category_ids: List[str], url: str) -> Optional[List[Dict[str, Any]]]:
    """
    Envoie un tableau d'ID de catégories à un lien externe via une requête POST
    et retourne un tableau de détails de catégories.
    """
    headers = {'Content-Type': 'application/json'}
    payload = {'category_ids': category_ids}

    try:
        response = requests.post(url, headers=headers, data=json.dumps(payload))
        response.raise_for_status()
        data = response.json()

        if isinstance(data, list):
            category_details = []
            for item in data:
                if isinstance(item, dict):
                    category_details.append({
                        'id_categorie': item.get('id_categorie'),
                        'nom_categorie': item.get('nom_categorie', 'N/A'),
                        'description_categorie': item.get('description_categorie', 'Description non disponible')
                    })
                else:
                    logger.warning(f"Élément inattendu dans get_category_details: {item}")
            return category_details
        else:
            logger.error(f"Format de réponse inattendu pour get_category_details: {data}")
            return None

    except requests.exceptions.RequestException as e:
        logger.error(f"Erreur dans get_category_details: {e}")
        return None
    except json.JSONDecodeError:
        logger.error("Erreur lors du décodage JSON dans get_category_details")
        return None

# Fonction conservée pour compatibilité descendante mais utilise maintenant la version async
def call_search_api(prompt: str, num_results: int, use_reranker: bool = True, reranker_model: str = "BAAI/bge-reranker-v2-m3") -> Optional[List[Dict[str, Any]]]:
    """
    Appelle l'API de recherche de manière synchrone (wrapper autour de la version async).
    DEPRECATED: Utilisez call_search_api_async directement pour de meilleures performances.
    """
    return asyncio.run(call_search_api_async(prompt, num_results, use_reranker, reranker_model))

def test_search_api_connection() -> bool:
    """Test de connexion à l'API de recherche interne"""
    try:
        # Test avec un appel direct à search_in_milvus
        return asyncio.run(_test_search_internal())
    except Exception as e:
        logger.error(f"Erreur test connexion API recherche: {e}")
        return False

async def _test_search_internal() -> bool:
    """Test interne asynchrone"""
    try:
        request = SearchRequestWs(
            prompt="test",
            source=[SourcesFiltre(source="produits_3", filtre={})],
            action=1,
            top_k=1,
            options=RerankerOptions(use_reranker=False, rrf=False)
        )
        result = await search_in_milvus(request)
        return result is not None
    except Exception as e:
        logger.error(f"Erreur test interne: {e}")
        return False


# ============================================================================
# VERSIONS ASYNCHRONES (OPTIMISÉES) - Pour pipeline parallèle
# ============================================================================

async def call_search_api_async(prompt: str, num_results: int, use_reranker: bool = True, reranker_model: str = "BAAI/bge-reranker-v2-m3") -> Optional[List[Dict[str, Any]]]:
    """
    Version asynchrone de call_search_api pour parallélisation.
    Utilise maintenant l'API de recherche en interne (search_in_milvus) au lieu d'un appel HTTP.
    """
    try:
        logger.info(f"[INTERNAL] Recherche interne avec prompt='{prompt}', num_results={num_results}")

        # Créer la requête pour l'API de recherche interne
        request = SearchRequestWs(
            prompt=prompt,
            source=[SourcesFiltre(source="produits_3", filtre={})],
            action=1,
            top_k=num_results,
            options=RerankerOptions(
                use_reranker=use_reranker,
                reranker_model=reranker_model,
                rrf=False
            )
        )

        # Appel direct à la fonction de recherche
        results_data = await search_in_milvus(request)

        # Extraire les correspondances de produits
        product_matches = results_data.get('matches', {}).get('produits_3', [])
        logger.info(f"[INTERNAL] Récupéré {len(product_matches)} correspondances de la recherche interne")

        return product_matches

    except Exception as e:
        logger.error(f"[INTERNAL] Erreur lors de la recherche interne: {type(e).__name__} - {str(e)}")
        return None


async def get_category_details_async(category_ids: List[str], url: str) -> Optional[List[Dict[str, Any]]]:
    """
    Version asynchrone de get_category_details pour parallélisation.
    Utilise httpx pour des appels HTTP non-bloquants.
    """
    headers = {'Content-Type': 'application/json'}
    payload = {'category_ids': category_ids}

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

            if isinstance(data, list):
                category_details = []
                for item in data:
                    if isinstance(item, dict):
                        category_details.append({
                            'id_categorie': str(item.get('id_categorie', '')),
                            'nom_categorie': str(item.get('nom_categorie', '')),
                            'description_categorie': str(item.get('description_categorie', ''))
                        })
                logger.info(f"[ASYNC] {len(category_details)} descriptions de catégories récupérées")
                return category_details
            else:
                logger.error(f"[ASYNC] Format de réponse inattendu pour get_category_details: {data}")
                return None

    except httpx.TimeoutException as e:
        logger.error(f"[ASYNC] Timeout lors de get_category_details (30s): {str(e)}")
        return None
    except httpx.ConnectError as e:
        logger.error(f"[ASYNC] Erreur de connexion pour get_category_details ({url}): {str(e)}")
        return None
    except httpx.HTTPStatusError as e:
        logger.error(f"[ASYNC] Erreur HTTP {e.response.status_code} pour get_category_details: {str(e)}")
        return None
    except httpx.HTTPError as e:
        logger.error(f"[ASYNC] Erreur HTTP dans get_category_details: {str(e)}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"[ASYNC] Erreur lors du décodage JSON dans get_category_details: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"[ASYNC] Erreur inattendue dans get_category_details: {type(e).__name__} - {str(e)}")
        return None