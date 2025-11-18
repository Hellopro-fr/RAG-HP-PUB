import requests
import httpx
import json
import logging
import asyncio
from typing import Any, Optional, List, Dict

# Imports depuis api-recherche (modules copiés dans le conteneur Docker via Dockerfile)
# Le Dockerfile copie les modules de l'API recherche dans /app/api_recherche_lib
# Ces imports utilisent le namespace "api_recherche_lib" au lieu de "app" pour éviter les conflits
from api_recherche_lib.core.recherche import search_in_milvus
from api_recherche_lib.schemas.search import SearchRequestWs, SourcesFiltre, RerankerOptions

logger = logging.getLogger(__name__)

# --- CONFIGURATION ---
EXTERNAL_PRODUCT_API_URL = "https://www.hellopro.fr/partenaires_externes/info_produit/get_info_produit.php"
EXTERNAL_CATEGORY_API_URL = "https://www.hellopro.fr/partenaires_externes/info_produit/get_info_categorie_classification.php"
EXTERNAL_PROMPT_API_URL = "https://www.hellopro.fr/partenaires_externes/info_produit/get_info_prompt.php"

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
            top_k=30,
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
        # logger.info(f"[INTERNAL] Recherche interne avec prompt='{prompt}', num_results={num_results}")

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

        # logger.info(f"[INTERNAL] Requête créée: {request}")

        # Appel direct à la fonction de recherche
        results_data = await search_in_milvus(request)

        # logger.info(f"[INTERNAL] Résultat brut de search_in_milvus: {type(results_data)}")
        # logger.info(f"[INTERNAL] Clés du résultat: {results_data.keys() if results_data else 'None'}")

        # Extraire les correspondances de produits
        product_matches = results_data.get('matches', {}).get('produits_3', [])
        # logger.info(f"[INTERNAL] Récupéré {len(product_matches)} correspondances de la recherche interne")

        # Log seulement si aucun résultat (pour débogage)
        if not product_matches:
            logger.warning(f"[INTERNAL] Aucun résultat pour prompt='{prompt[:50]}...'")

        return product_matches

    except Exception as e:
        logger.error(f"[INTERNAL] Erreur recherche: {type(e).__name__} - {str(e)}")
        # import traceback
        # logger.error(f"[INTERNAL] Traceback: {traceback.format_exc()}")
        return None


async def get_category_details_async(category_ids: List[str], url: str) -> Optional[List[Dict[str, Any]]]:
    """
    Version asynchrone de get_category_details pour parallélisation.
    Utilise httpx pour des appels HTTP non-bloquants.
    """
    headers = {
        'Content-Type': 'application/json',
        'User-Agent': 'Mozilla/5.0 (compatible; ClassificationService/2.0)'
    }
    payload = {'category_ids': category_ids}
    print(f"Payload get_category_details_async: {payload}")

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
                            'description_categorie': str(item.get('description_categorie', '')),
                            'fil_ariane': str(item.get('fil_ariane', '')),
                            'top_5_produit': str(item.get('top_5_produit', ''))
                        })
                logger.info(f"[ASYNC] {len(category_details)} descriptions de catégories enrichies récupérées")
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


async def get_prompt_details_async(prompt_id: int, url: str) -> Optional[Dict[str, Any]]:
    """
    Version asynchrone pour récupérer un template de prompt depuis l'API externe.
    Utilise httpx pour des appels HTTP non-bloquants.

    Args:
        prompt_id: ID du prompt à récupérer (ex: 94)
        url: URL de l'API externe

    Returns:
        Un dictionnaire avec le contenu du prompt et la température:
        {
            'prompt': 'contenu du prompt avec placeholders',
            'temperature': 0.4
        }
        ou None en cas d'erreur
    """
    headers = {'Content-Type': 'application/json'}
    payload = {'id_prompt': prompt_id}

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

            # On s'attend à recevoir un objet avec 'prompt' et 'temperature'
            if isinstance(data, dict) and 'prompt' in data:
                prompt_content = str(data.get('prompt', ''))
                temperature = float(data.get('temperature', 0.0))  # Température par défaut: 0.0

                logger.info(f"[ASYNC] Prompt ID {prompt_id} récupéré avec succès (temperature: {temperature})")

                return {
                    'prompt': prompt_content,
                    'temperature': temperature
                }
            else:
                logger.error(f"[ASYNC] Format de réponse inattendu pour get_prompt_details: {data}")
                return None

    except httpx.TimeoutException as e:
        logger.error(f"[ASYNC] Timeout lors de get_prompt_details (30s): {str(e)}")
        return None
    except httpx.ConnectError as e:
        logger.error(f"[ASYNC] Erreur de connexion pour get_prompt_details ({url}): {str(e)}")
        return None
    except httpx.HTTPStatusError as e:
        logger.error(f"[ASYNC] Erreur HTTP {e.response.status_code} pour get_prompt_details: {str(e)}")
        return None
    except httpx.HTTPError as e:
        logger.error(f"[ASYNC] Erreur HTTP dans get_prompt_details: {str(e)}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"[ASYNC] Erreur lors du décodage JSON dans get_prompt_details: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"[ASYNC] Erreur inattendue dans get_prompt_details: {type(e).__name__} - {str(e)}")
        return None