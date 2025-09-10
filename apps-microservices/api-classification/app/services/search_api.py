# app/services/search_api.py
import requests
import logging
import time
from typing import List, Dict, Any, Optional
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from ..exceptions import SearchAPIError, ProductAPIError, TimeoutError, RateLimitError
from ..handlers import ErrorHandler

logger = logging.getLogger(__name__)

class SearchAPIClient:
    """Client pour l'API de recherche centralisée avec gestion d'erreurs robuste"""
    
    def __init__(self, search_api_url: str, external_product_api_url: str, timeout: int = 30):
        self.search_api_url = search_api_url.rstrip('/')
        self.external_product_api_url = external_product_api_url.rstrip('/')
        self.timeout = timeout
        self.session = requests.Session()
        
        # Configuration de la session avec retry et timeout
        self.session.headers.update({
            'User-Agent': 'ProductClassifier/1.0',
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        })
        
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.session.close()

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((requests.exceptions.Timeout, requests.exceptions.ConnectionError))
)
def call_search_api(query: str, 
                   num_results: int = 20, 
                   use_reranker: bool = True, 
                   reranker_model: str = "BAAI/bge-reranker-v2-m3", 
                   search_api_url: str = "",
                   timeout: int = 30) -> List[Dict[str, Any]]:
    """
    Appelle l'API de recherche centralisée avec retry automatique et gestion d'erreurs.
    
    Args:
        query: Texte de recherche
        num_results: Nombre de résultats souhaités
        use_reranker: Utiliser le reranker pour améliorer les résultats
        reranker_model: Modèle de reranking à utiliser
        search_api_url: URL de l'API de recherche
        timeout: Timeout en secondes
    
    Returns:
        Liste des résultats de recherche
    
    Raises:
        SearchAPIError: Erreur lors de la recherche
        TimeoutError: Timeout de la requête
        RateLimitError: Limite de débit atteinte
    """
    if not search_api_url:
        raise SearchAPIError("URL de l'API de recherche non configurée")
    
    if not query or not query.strip():
        raise SearchAPIError("Query de recherche vide")
    
    start_time = time.time()
    
    # Préparation des données
    payload = {
        "query": query.strip(),
        "num_results": max(1, min(num_results, 200)),  # Limites raisonnables
        "use_reranker": use_reranker,
        "reranker_model": reranker_model
    }
    
    # Headers avec informations de debugging
    headers = {
        'User-Agent': 'ProductClassifier/1.0',
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        'X-Request-ID': f"search_{int(time.time())}"
    }
    
    try:
        logger.info(f"Appel API recherche: '{query[:50]}...' ({num_results} résultats)")
        logger.debug(f"URL: {search_api_url}/search, Payload: {payload}")
        
        response = requests.post(
            f"{search_api_url}/search",
            json=payload,
            headers=headers,
            timeout=timeout,
            verify=True  # Vérification SSL
        )
        
        # Métriques de performance
        response_time = time.time() - start_time
        logger.info(f"API recherche - Temps: {response_time:.2f}s, Status: {response.status_code}")
        
        # Gestion des codes de statut
        if response.status_code == 200:
            data = response.json()
            results = data.get("results", [])
            
            # Validation de la structure de réponse
            if not isinstance(results, list):
                raise SearchAPIError("Format de réponse invalide: 'results' doit être une liste")
            
            logger.info(f"Recherche réussie: {len(results)} résultats reçus")
            return results
            
        elif response.status_code == 400:
            error_data = _parse_error_response(response)
            raise SearchAPIError(f"Requête invalide: {error_data.get('message', 'Erreur inconnue')}")
            
        elif response.status_code == 401:
            raise SearchAPIError("Erreur d'authentification avec l'API de recherche")
            
        elif response.status_code == 403:
            raise SearchAPIError("Accès interdit à l'API de recherche")
            
        elif response.status_code == 404:
            raise SearchAPIError("Endpoint de recherche introuvable")
            
        elif response.status_code == 429:
            retry_after = _get_retry_after(response)
            raise RateLimitError("API de recherche", retry_after)
            
        elif response.status_code >= 500:
            error_msg = f"Erreur serveur API recherche: {response.status_code}"
            if response.text:
                error_msg += f" - {response.text[:200]}"
            raise SearchAPIError(error_msg)
            
        else:
            raise SearchAPIError(f"Erreur inattendue: {response.status_code}")
            
    except requests.exceptions.Timeout:
        logger.error(f"Timeout lors de l'appel à l'API de recherche après {timeout}s")
        raise TimeoutError("Recherche API", timeout)
        
    except requests.exceptions.ConnectionError as e:
        logger.error(f"Erreur de connexion à l'API de recherche: {e}")
        raise SearchAPIError(f"Impossible de se connecter à l'API de recherche: {str(e)}")
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Erreur lors de la requête de recherche: {e}")
        raise ErrorHandler.handle_requests_error(e, "API de recherche")
        
    except ValueError as e:
        logger.error(f"Erreur de parsing JSON de l'API recherche: {e}")
        raise SearchAPIError(f"Réponse JSON invalide: {str(e)}")
        
    except Exception as e:
        logger.exception(f"Erreur inattendue lors de l'appel API recherche: {e}")
        raise SearchAPIError(f"Erreur interne: {str(e)}")

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((requests.exceptions.Timeout, requests.exceptions.ConnectionError))
)
def get_product_details(product_ids: List[str], 
                       external_product_api_url: str,
                       timeout: int = 30) -> Optional[List[Dict[str, Any]]]:
    """
    Récupère les détails des produits via l'API externe avec retry automatique.
    
    Args:
        product_ids: Liste des IDs de produits à récupérer
        external_product_api_url: URL de l'API externe
        timeout: Timeout en secondes
    
    Returns:
        Liste des détails produits ou None en cas d'erreur
    
    Raises:
        ProductAPIError: Erreur lors de la récupération
        TimeoutError: Timeout de la requête
        RateLimitError: Limite de débit atteinte
    """
    if not external_product_api_url:
        logger.warning("URL de l'API produits externe non configurée")
        return None
    
    if not product_ids:
        logger.warning("Liste d'IDs produits vide")
        return None
    
    # Limiter le nombre d'IDs pour éviter les requêtes trop lourdes
    if len(product_ids) > 1000:
        logger.warning(f"Trop d'IDs produits ({len(product_ids)}), limitation à 1000")
        product_ids = product_ids[:1000]
    
    start_time = time.time()
    
    # Préparation des données
    payload = {
        "product_ids": list(set(product_ids))  # Déduplication
    }
    
    headers = {
        'User-Agent': 'ProductClassifier/1.0',
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        'X-Request-ID': f"products_{int(time.time())}"
    }
    
    try:
        logger.info(f"Récupération détails pour {len(payload['product_ids'])} produits")
        logger.debug(f"URL: {external_product_api_url}/products/details")
        
        response = requests.post(
            f"{external_product_api_url}/products/details",
            json=payload,
            headers=headers,
            timeout=timeout,
            verify=True
        )
        
        # Métriques de performance
        response_time = time.time() - start_time
        logger.info(f"API produits - Temps: {response_time:.2f}s, Status: {response.status_code}")
        
        # Gestion des codes de statut
        if response.status_code == 200:
            data = response.json()
            products = data.get("products", [])
            
            # Validation de la structure
            if not isinstance(products, list):
                raise ProductAPIError("Format de réponse invalide: 'products' doit être une liste")
            
            # Validation des produits individuels
            valid_products = []
            for product in products:
                if isinstance(product, dict) and 'id_produit' in product and 'nom_produit' in product:
                    valid_products.append(product)
                else:
                    logger.warning(f"Produit invalide ignoré: {product}")
            
            logger.info(f"Détails récupérés: {len(valid_products)} produits valides")
            return valid_products
            
        elif response.status_code == 400:
            error_data = _parse_error_response(response)
            raise ProductAPIError(f"Requête invalide: {error_data.get('message', 'Erreur inconnue')}")
            
        elif response.status_code == 401:
            raise ProductAPIError("Erreur d'authentification avec l'API produits")
            
        elif response.status_code == 403:
            raise ProductAPIError("Accès interdit à l'API produits")
            
        elif response.status_code == 404:
            raise ProductAPIError("Endpoint produits introuvable")
            
        elif response.status_code == 429:
            retry_after = _get_retry_after(response)
            raise RateLimitError("API produits", retry_after)
            
        elif response.status_code >= 500:
            error_msg = f"Erreur serveur API produits: {response.status_code}"
            if response.text:
                error_msg += f" - {response.text[:200]}"
            raise ProductAPIError(error_msg)
            
        else:
            raise ProductAPIError(f"Erreur inattendue: {response.status_code}")
            
    except requests.exceptions.Timeout:
        logger.error(f"Timeout lors de l'appel à l'API produits après {timeout}s")
        raise TimeoutError("API produits", timeout)
        
    except requests.exceptions.ConnectionError as e:
        logger.error(f"Erreur de connexion à l'API produits: {e}")
        raise ProductAPIError(f"Impossible de se connecter à l'API produits: {str(e)}")
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Erreur lors de la requête produits: {e}")
        raise ErrorHandler.handle_requests_error(e, "API produits")
        
    except ValueError as e:
        logger.error(f"Erreur de parsing JSON de l'API produits: {e}")
        raise ProductAPIError(f"Réponse JSON invalide: {str(e)}")
        
    except Exception as e:
        logger.exception(f"Erreur inattendue lors de l'appel API produits: {e}")
        raise ProductAPIError(f"Erreur interne: {str(e)}")

def batch_get_product_details(product_ids: List[str], 
                             external_product_api_url: str,
                             batch_size: int = 100,
                             timeout: int = 30) -> List[Dict[str, Any]]:
    """
    Récupère les détails des produits par lots pour éviter les timeouts sur de gros volumes.
    
    Args:
        product_ids: Liste des IDs de produits
        external_product_api_url: URL de l'API externe
        batch_size: Taille des lots
        timeout: Timeout par lot
    
    Returns:
        Liste consolidée des détails produits
    """
    if not product_ids:
        return []
    
    all_products = []
    failed_batches = []
    
    # Découpage en lots
    for i in range(0, len(product_ids), batch_size):
        batch_ids = product_ids[i:i + batch_size]
        batch_num = (i // batch_size) + 1
        total_batches = (len(product_ids) + batch_size - 1) // batch_size
        
        try:
            logger.info(f"Traitement lot {batch_num}/{total_batches} ({len(batch_ids)} produits)")
            
            batch_products = get_product_details(batch_ids, external_product_api_url, timeout)
            if batch_products:
                all_products.extend(batch_products)
            
            # Petite pause entre les lots pour éviter la surcharge
            if i + batch_size < len(product_ids):
                time.sleep(0.5)
                
        except Exception as e:
            logger.error(f"Erreur lot {batch_num}: {e}")
            failed_batches.append(batch_num)
            continue
    
    if failed_batches:
        logger.warning(f"Échec de {len(failed_batches)} lots: {failed_batches}")
    
    logger.info(f"Récupération par lots terminée: {len(all_products)} produits au total")
    return all_products

def health_check_apis(search_api_url: str, external_product_api_url: str, 
                     external_category_api_url: str, timeout: int = 10) -> Dict[str, Any]:
    """
    Vérifie la santé des APIs externes incluant l'API catégories.
    """
    health_status = {
        "timestamp": time.time(),
        "apis": {}
    }
    
    # Test API de recherche
    if search_api_url:
        try:
            response = requests.get(f"{search_api_url}/health", timeout=timeout)
            health_status["apis"]["search"] = {
                "status": "healthy" if response.status_code == 200 else "unhealthy",
                "response_code": response.status_code,
                "response_time_ms": response.elapsed.total_seconds() * 1000
            }
        except Exception as e:
            health_status["apis"]["search"] = {
                "status": "unhealthy",
                "error": str(e)
            }
    else:
        health_status["apis"]["search"] = {"status": "not_configured"}
    
    # Test API produits
    if external_product_api_url:
        try:
            response = requests.get(f"{external_product_api_url}/health", timeout=timeout)
            health_status["apis"]["products"] = {
                "status": "healthy" if response.status_code == 200 else "unhealthy",
                "response_code": response.status_code,
                "response_time_ms": response.elapsed.total_seconds() * 1000
            }
        except Exception as e:
            health_status["apis"]["products"] = {
                "status": "unhealthy",
                "error": str(e)
            }
    else:
        health_status["apis"]["products"] = {"status": "not_configured"}
    
    # NOUVEAU: Test API catégories
    if external_category_api_url:
        try:
            response = requests.get(f"{external_category_api_url}/health", timeout=timeout)
            health_status["apis"]["categories"] = {
                "status": "healthy" if response.status_code == 200 else "unhealthy",
                "response_code": response.status_code,
                "response_time_ms": response.elapsed.total_seconds() * 1000
            }
        except Exception as e:
            health_status["apis"]["categories"] = {
                "status": "unhealthy",
                "error": str(e)
            }
    else:
        health_status["apis"]["categories"] = {"status": "not_configured"}
    
    # Statut global
    api_statuses = [api["status"] for api in health_status["apis"].values()]
    if "unhealthy" in api_statuses:
        health_status["overall_status"] = "unhealthy"
    elif "not_configured" in api_statuses:
        health_status["overall_status"] = "degraded"
    else:
        health_status["overall_status"] = "healthy"
    
    return health_status


# Fonctions utilitaires
def _parse_error_response(response: requests.Response) -> Dict[str, Any]:
    """Parse la réponse d'erreur pour extraire les détails"""
    try:
        return response.json()
    except (ValueError, requests.exceptions.JSONDecodeError):
        return {"message": response.text[:200] if response.text else "Erreur inconnue"}

def _get_retry_after(response: requests.Response) -> Optional[int]:
    """Extrait le header Retry-After de la réponse"""
    retry_after = response.headers.get('Retry-After')
    if retry_after:
        try:
            return int(retry_after)
        except ValueError:
            pass
    return None

def validate_api_urls(search_api_url: str, external_product_api_url: str) -> Dict[str, bool]:
    """
    Valide que les URLs des APIs sont correctement formatées.
    
    Returns:
        Dict avec le statut de validation pour chaque URL
    """
    import re
    
    url_pattern = re.compile(
        r'^https?://'  # http:// ou https://
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domaine
        r'localhost|'  # localhost
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # IP
        r'(?::\d+)?'  # port optionnel
        r'(?:/?|[/?]\S+)$', re.IGNORECASE)
    
    return {
        "search_api_valid": bool(url_pattern.match(search_api_url)) if search_api_url else False,
        "product_api_valid": bool(url_pattern.match(external_product_api_url)) if external_product_api_url else False
    }

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((requests.exceptions.Timeout, requests.exceptions.ConnectionError))
)
def get_category_details(category_ids: List[str], 
                        external_category_api_url: str,
                        timeout: int = 30) -> Optional[List[Dict[str, Any]]]:
    """
    Récupère les détails des catégories via l'API externe.
    
    Args:
        category_ids: Liste des IDs de catégories à récupérer
        external_category_api_url: URL de l'API externe pour les catégories
        timeout: Timeout en secondes
    
    Returns:
        Liste des détails catégories ou None en cas d'erreur
    
    Raises:
        ProductAPIError: Erreur lors de la récupération
        TimeoutError: Timeout de la requête
        RateLimitError: Limite de débit atteinte
    """
    if not external_category_api_url:
        logger.warning("URL de l'API catégories externe non configurée")
        return None
    
    if not category_ids:
        logger.warning("Liste d'IDs catégories vide")
        return None
    
    # Limiter le nombre d'IDs
    if len(category_ids) > 500:
        logger.warning(f"Trop d'IDs catégories ({len(category_ids)}), limitation à 500")
        category_ids = category_ids[:500]
    
    start_time = time.time()
    
    # Préparation des données
    payload = {
        "category_ids": list(set(category_ids))  # Déduplication
    }
    
    headers = {
        'User-Agent': 'ProductClassifier/1.0',
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        'X-Request-ID': f"categories_{int(time.time())}"
    }
    
    try:
        logger.info(f"Récupération détails pour {len(payload['category_ids'])} catégories")
        logger.debug(f"URL: {external_category_api_url}/categories/details")
        
        response = requests.post(
            f"{external_category_api_url}/categories/details",
            json=payload,
            headers=headers,
            timeout=timeout,
            verify=True
        )
        
        # Métriques de performance
        response_time = time.time() - start_time
        logger.info(f"API catégories - Temps: {response_time:.2f}s, Status: {response.status_code}")
        
        # Gestion des codes de statut
        if response.status_code == 200:
            data = response.json()
            categories = data.get("categories", [])
            
            # Validation de la structure
            if not isinstance(categories, list):
                raise ProductAPIError("Format de réponse invalide: 'categories' doit être une liste")
            
            # Validation des catégories individuelles
            valid_categories = []
            for category in categories:
                if isinstance(category, dict) and 'id_categorie' in category:
                    # Vérifier les champs requis
                    if 'nom_categorie' not in category:
                        category['nom_categorie'] = f"Catégorie {category['id_categorie']}"
                    if 'description_categorie' not in category:
                        category['description_categorie'] = "Description non disponible"
                    
                    valid_categories.append(category)
                else:
                    logger.warning(f"Catégorie invalide ignorée: {category}")
            
            logger.info(f"Détails catégories récupérés: {len(valid_categories)} catégories valides")
            return valid_categories
            
        elif response.status_code == 400:
            error_data = _parse_error_response(response)
            raise ProductAPIError(f"Requête invalide: {error_data.get('message', 'Erreur inconnue')}")
            
        elif response.status_code == 401:
            raise ProductAPIError("Erreur d'authentification avec l'API catégories")
            
        elif response.status_code == 403:
            raise ProductAPIError("Accès interdit à l'API catégories")
            
        elif response.status_code == 404:
            raise ProductAPIError("Endpoint catégories introuvable")
            
        elif response.status_code == 429:
            retry_after = _get_retry_after(response)
            raise RateLimitError("API catégories", retry_after)
            
        elif response.status_code >= 500:
            error_msg = f"Erreur serveur API catégories: {response.status_code}"
            if response.text:
                error_msg += f" - {response.text[:200]}"
            raise ProductAPIError(error_msg)
            
        else:
            raise ProductAPIError(f"Erreur inattendue: {response.status_code}")
            
    except requests.exceptions.Timeout:
        logger.error(f"Timeout lors de l'appel à l'API catégories après {timeout}s")
        raise TimeoutError("API catégories", timeout)
        
    except requests.exceptions.ConnectionError as e:
        logger.error(f"Erreur de connexion à l'API catégories: {e}")
        raise ProductAPIError(f"Impossible de se connecter à l'API catégories: {str(e)}")
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Erreur lors de la requête catégories: {e}")
        raise ErrorHandler.handle_requests_error(e, "API catégories")
        
    except ValueError as e:
        logger.error(f"Erreur de parsing JSON de l'API catégories: {e}")
        raise ProductAPIError(f"Réponse JSON invalide: {str(e)}")
        
    except Exception as e:
        logger.exception(f"Erreur inattendue lors de l'appel API catégories: {e}")
        raise ProductAPIError(f"Erreur interne: {str(e)}")

# Fonction de test des APIs mise à jour
def health_check_apis(search_api_url: str, external_product_api_url: str, 
                     external_category_api_url: str, timeout: int = 10) -> Dict[str, Any]:
    """
    Vérifie la santé des APIs externes incluant l'API catégories.
    """
    health_status = {
        "timestamp": time.time(),
        "apis": {}
    }