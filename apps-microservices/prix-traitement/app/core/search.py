"""
Module de recherche RAG dans Milvus pour le service prix-traitement.
Basé sur prix-extraction-siteweb/app/core/search.py avec support du filtre id_categorie.
"""
import logging
import asyncio
from typing import Any, Optional, List, Dict

# Imports depuis api-recherche (modules copiés dans le conteneur Docker via Dockerfile)
# Le Dockerfile copie les modules de l'API recherche dans /app/api_recherche_lib
# Ces imports utilisent le namespace "api_recherche_lib" au lieu de "app" pour éviter les conflits
from api_recherche_lib.core.recherche import search_in_milvus
from api_recherche_lib.schemas.search import SearchRequestWs, SourcesFiltre, RerankerOptions

logger = logging.getLogger(__name__)


async def call_search_api_async(
    prompt: str, 
    num_results: int = 30, 
    source: str = "prix",
    filtre: Optional[Dict[str, Any]] = None,
    use_reranker: bool = False, 
    reranker_model: str = "BAAI/bge-reranker-v2-m3"
) -> Optional[List[Dict[str, Any]]]:
    """
    Recherche asynchrone dans Milvus via l'API de recherche interne (search_in_milvus).
    
    Args:
        prompt: Le texte de recherche
        num_results: Nombre de résultats à retourner (défaut: 30)
        source: La collection source dans Milvus (défaut: "prix")
        filtre: Dictionnaire de filtres (ex: {"id_categorie": "1234"})
        use_reranker: Utiliser le reranker
        reranker_model: Modèle de reranking
        
    Returns:
        Liste de correspondances ou None en cas d'erreur
    """
    if filtre is None:
        filtre = {}
    
    try:
        # Créer la requête pour l'API de recherche interne
        request = SearchRequestWs(
            prompt=prompt,
            source=[SourcesFiltre(source=source, filtre=filtre)],
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

        # Extraire les correspondances depuis la source configurée
        product_matches = results_data.get('matches', {}).get(source, [])

        # Log seulement si aucun résultat (pour débogage)
        if not product_matches:
            logger.warning(f"[INTERNAL] Aucun résultat pour prompt='{prompt[:50]}...' dans source='{source}'")
        else:
            logger.info(f"[INTERNAL] {len(product_matches)} résultats trouvés dans source='{source}'")

        return product_matches

    except Exception as e:
        logger.error(f"[INTERNAL] Erreur recherche Milvus: {type(e).__name__} - {str(e)}")
        return None
