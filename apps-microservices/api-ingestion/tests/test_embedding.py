# test_embed.py
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.router.embedding.embedding import router as EmbeddingRouter  # adapte ce chemin

app = FastAPI()
app.include_router(EmbeddingRouter,prefix="/embedding")  # adapte si besoin


def test_embed_endpoint():
    
    client = TestClient(app)
    
    payload = {
        "texte_brute": "Ceci est un texte pour générer des embeddings.",
        "id_unique": "abc123",
        "type_page": "fiche_produit"
    }

    response = client.post("/embedding", json=payload)
    
    assert response.status_code == 200
    json_data = response.json()

    # Vérifier que le champ embeddings est présent
    assert "embedding" in json_data['data'][0]
    embedding = json_data["data"][0]["embedding"]

    # Vérifier que c'est une liste de listes de floats
    assert isinstance(embedding, list)
    assert all(isinstance(vec, float) for vec in embedding)

    # Optionnel : vérifier les dimensions si tu sais à quoi t'attendre
    # Par exemple si c'est un seul vecteur de 384 dimensions :
    # assert len(embedding) == 1
    # assert len(embedding) <= 512
