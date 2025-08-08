from common_utils.embedding.Embedding import Embedding

def test_embed_function():
    
    embedding_service = Embedding()

    produit = {
        "id_produit": "12345",
        "nom_produit": "Produit Test",
        "embedding": "Ceci est un texte pour générer des embeddings.",
        "type_page": "fiche_produit"
    }

    result = embedding_service.embed_data_clean(produit)
    
    # Vérifier que le champ embeddings est présent
    assert "embedding" in result[0]
    embedding = result[0]["embedding"]

    # Vérifier que c'est une liste de listes de floats
    assert isinstance(embedding, list)
    assert all(isinstance(vec, float) for vec in embedding)

    # Optionnel : vérifier les dimensions si tu sais à quoi t'attendre
    assert len(embedding) <= 1024
