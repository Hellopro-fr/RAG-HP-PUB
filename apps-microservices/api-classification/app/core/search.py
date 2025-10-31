import requests
import httpx
import json
import logging
import asyncio
from typing import Any, Optional, List, Dict

logger = logging.getLogger(__name__)

# --- CONFIGURATION ---
SEARCH_API_URL = "http://34.34.166.5:8510/search"
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

def call_search_api(prompt: str, num_results: int, use_reranker: bool = True, reranker_model: str = "BAAI/bge-reranker-v2-m3") -> Optional[List[Dict[str, Any]]]:
    """
    Appelle l'API de recherche centralisée avec le prompt donné.
    """
    search_payload = {
        'prompt': prompt,
        'source': [
            {
                'source': 'produits_3',
                'filtre': {}
            }
        ],
        'action': 1,
        'top_k': str(num_results),
        'options': {
            'use_reranker': use_reranker,
            'reranker_model': reranker_model,
            'rrf': False
        }
    }

    search_headers = {'Content-Type': 'application/json'}

    try:
        logger.info(f"Envoi requête à l'API de recherche: {SEARCH_API_URL} avec prompt='{prompt}'")
        response = requests.post(SEARCH_API_URL, headers=search_headers, data=json.dumps(search_payload), timeout=30)
        response.raise_for_status()

        results_data = response.json()
        product_matches = results_data.get('results', {}).get('matches', {}).get('produits_3', [])
        logger.info(f"Récupéré {len(product_matches)} correspondances de l'API de recherche")
        return product_matches

    except requests.exceptions.RequestException as e:
        logger.error(f"Erreur lors de l'appel à l'API de recherche: {e}")
        return None
    except json.JSONDecodeError:
        logger.error("Erreur lors du décodage JSON de l'API de recherche")
        return None

def test_search_api_connection() -> bool:
    """Test de connexion à l'API de recherche"""
    try:
        test_payload = {
            'prompt': 'test',
            'source': [{'source': 'produits_3', 'filtre': {}}],
            'action': 1,
            'top_k': '1',
            'options': {'use_reranker': False, 'rrf': False}
        }
        response = requests.post(
            SEARCH_API_URL,
            headers={'Content-Type': 'application/json'},
            data=json.dumps(test_payload),
            timeout=30
        )
        return response.status_code == 200
    except Exception as e:
        logger.error(f"Erreur test connexion API recherche: {e}")
        return False


# ============================================================================
# VERSIONS ASYNCHRONES (OPTIMISÉES) - Pour pipeline parallèle
# ============================================================================

async def call_search_api_async(prompt: str, num_results: int, use_reranker: bool = True, reranker_model: str = "BAAI/bge-reranker-v2-m3") -> Optional[List[Dict[str, Any]]]:
    """
    Version asynchrone de call_search_api pour parallélisation.
    Utilise httpx pour des appels HTTP non-bloquants.
    """
    search_payload = {
        'prompt': prompt,
        'source': [
            {
                'source': 'produits_3',
                'filtre': {}
            }
        ],
        'action': 1,
        'top_k': str(num_results),
        'options': {
            'use_reranker': use_reranker,
            'reranker_model': reranker_model,
            'rrf': False
        }
    }

    search_headers = {'Content-Type': 'application/json'}

    try:
        logger.info(f"[ASYNC] Envoi requête à l'API de recherche: {SEARCH_API_URL} avec prompt='{prompt}'")
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(SEARCH_API_URL, headers=search_headers, json=search_payload)
            response.raise_for_status()

            results_data = response.json()
            product_matches = results_data.get('results', {}).get('matches', {}).get('produits_3', [])
            logger.info(f"[ASYNC] Récupéré {len(product_matches)} correspondances de l'API de recherche")
            return product_matches

    except httpx.TimeoutException as e:
        logger.error(f"[ASYNC] Timeout lors de l'appel à l'API de recherche (30s): {str(e)}")
        return None
    except httpx.ConnectError as e:
        logger.error(f"[ASYNC] Erreur de connexion à l'API de recherche ({SEARCH_API_URL}): {str(e)}")
        return None
    except httpx.HTTPStatusError as e:
        logger.error(f"[ASYNC] Erreur HTTP {e.response.status_code} de l'API de recherche: {str(e)}")
        return None
    except httpx.HTTPError as e:
        logger.error(f"[ASYNC] Erreur HTTP lors de l'appel à l'API de recherche: {str(e)}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"[ASYNC] Erreur lors du décodage JSON de l'API de recherche: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"[ASYNC] Erreur inattendue lors de l'appel à l'API de recherche: {type(e).__name__} - {str(e)}")
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