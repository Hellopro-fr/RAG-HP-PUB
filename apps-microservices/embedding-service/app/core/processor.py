from common_utils.embedding.Embedding import Embedding
from common_utils.autres.CollectionName import CollectionName

def embed_input_data(input_data: dict) -> dict:
    """
    Prend un dictionnaire de produit, vectorise le donnée dans le champ embedding et prépare le message
    pour l'étape d'insertion dans la base vectorielle
    
    Retourne: Un dictionnaire prêt à être publié.
    """
    embedding_service = Embedding()
    datas = input_data.get("data", {})
    collection = input_data.get("collection", CollectionName.PRODUIT)

    result_embedding = embedding_service.embed_data_clean(datas)
    
    output_message = {
        "collection": collection,
        "data": result_embedding,
    }
    
    return output_message