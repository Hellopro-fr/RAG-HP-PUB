from pydantic import BaseModel, Field
from typing import Optional, Annotated
from typing import List

class SearchRequest(BaseModel):
    nom_produit: str
    domaine    : str
    description: Optional[str] = ""
    id_produit : str
    
class SearchResponse(BaseModel):
    etat           : str
    is_doublon     : bool
    from_similarity: bool = False
    score          : float = 0.0
    error          : Optional[str] = None
    id_produit     : str
    
    
class SearchReponse(BaseModel):
    result : Annotated[SearchResponse, Field(title="Contient l'objet du RESULTAT")]
    # # TODO:
    # à supprimer les données en entrées pour vérification
    # post:  Annotated[SearchRequest, Field(title="Contient l'objet de la REQUETE")]

# Nouvelle réponse pour les requêtes multiples
class SearchResponseLot(BaseModel):
    results: List[SearchResponse]