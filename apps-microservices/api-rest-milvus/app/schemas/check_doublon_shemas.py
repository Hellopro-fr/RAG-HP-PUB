from pydantic import BaseModel, Field
from typing import Optional, Annotated
from typing import List

class SearchRequest(BaseModel):
    id_produit : str
    nom_produit: str
    domaine    : str
    description: Optional[str] = ""
    
class SearchResponse(BaseModel):
    id_produit     : str
    is_doublon     : bool
    from_similarity: bool = False
    score          : float = 0.0
    
    
class SearchReponse(BaseModel):
    results: Annotated[SearchResponse, Field(title="Contient l'objet du RESULTAT")]
    # TODO:
    # à supprimer les données en entrées pour vérification
    post:  Annotated[SearchRequest, Field(title="Contient l'objet de la REQUETE")]

# Nouvelle réponse pour les requêtes multiples
class SearchResponseLot(BaseModel):
    results: List[SearchReponse]