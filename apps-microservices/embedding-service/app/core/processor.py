from common_utils.embedding.Embedding import Embedding
from common_utils.autres.CollectionName import CollectionName
import logging

async def embed_input_data(input_data: dict, **kwargs) -> dict:
    """
    Vectorise les données via le service d'embedding et prépare le message pour l'insertion.
    Lève des exceptions en cas d'échec pour être géré par le consumer.

    Returns:
        Un dictionnaire prêt à être publié.
    Raises:
        ValueError: Si les données d'entrée sont invalides ou ne contiennent aucun texte à traiter.
        Exception: Pour toute autre erreur lors du processus d'embedding (ex: gRPC indisponible).
    """
    logging.info("Début du processus d'embedding.")
    # On identifie ce service comme la source des requêtes.
    embedding_service = Embedding(source_service="embedding-service")
    datas = input_data.get("data", {})
    collection = input_data.get("collection", CollectionName.PRODUIT)

    if not datas:
        raise ValueError("Le champ 'data' est vide ou manquant dans le message.")

    try:
        result_embedding = await embedding_service.embed_data_clean(datas)
        
        if not result_embedding:
            # Ceci est une erreur de données, pas une erreur transitoire.
            # Le message ne devrait pas être réessayé.
            raise ValueError("Aucun contenu textuel valide trouvé pour l'embedding après nettoyage.")

        output_message = {
            "collection": collection,
            "data": result_embedding,
            "database": input_data.get("database", "qdrant"),
            "origin": input_data.get('origin', "")
        }
        
        logging.info(f"✓ Embedding réussi pour la collection '{collection}'. {len(result_embedding)} chunk(s) traité(s).")
        return output_message
        
    except Exception as e:
        logging.error(f"Échec du processus d'embedding: {e}", exc_info=True)
        # Propage l'exception pour que le consumer la gère (retry/DLQ)
        raise e