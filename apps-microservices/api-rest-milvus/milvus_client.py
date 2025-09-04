from common_utils.database.config.settings import Configuration, settings
from common_utils.database.Utils import Utils

from pymilvus import (
    connections,
    utility,
    FieldSchema,
    CollectionSchema,
    DataType,
    Collection,
    MilvusException
)

# Connexion à Milvus
connections.connect("default", host=settings.ZILLIZ_URI, port=settings.ZILLIZ_PORT)

def execute_query(collection_name: str, query: str):
    """
    Execute une requête Milvus (ex: search) et retourne le résultat.
    query: dict ou string selon l'utilisation (ici on suppose search)
    """
    try:
        collection = Collection(collection_name)
        # Exemple générique : recherche d'un vecteur
        # query doit contenir : {"vectors": [[...]], "top_k": 5}
        vectors = query.get("vectors")
        top_k = query.get("top_k", 5)
        results = collection.search(vectors, "embedding", params={"metric_type": "L2"}, limit=top_k)
        output = []
        for result in results:
            output.append([{"id": r.id, "distance": r.distance} for r in result])
        return output
    except Exception as e:
        return {"error": str(e)}
