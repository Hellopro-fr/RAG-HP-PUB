from common_utils.embedding.Embedding import Embedding

def embed_product_data(product_data: dict) -> dict:
    """
    Prend un dictionnaire de produit, vectorise le donnée dans le champ embedding et prépare le message
    pour l'étape d'insertion dans la base vectorielle
    
    Retourne: Un dictionnaire prêt à être publié.
    """
    embedding_service = Embedding()
    product = product_data.get("data", {})
    collection = product_data.get("collection", "produits")

    result_embedding = embedding_service.embed_data_clean(product)
    
    output_message = {
        "collection": collection,
        "data": result_embedding,
    }
    
    return output_message