from pydantic import BaseModel, Field
from typing import Optional, Annotated

class SearchRequest(BaseModel):
    nom_produit: str
    domaine    : str
    description: Optional[str] = ""
    
class SearchResponse(BaseModel):
    is_doublon     : bool
    from_similarity: bool = False
    score          : float = 0.0
    
    
class SearchReponse(BaseModel):
    results: Annotated[SearchResponse, Field(title="Contient l'objet du RESULTAT")]
    # TODO:
    # à supprimer les données en entrées pour vérification
    post:  Annotated[SearchRequest, Field(title="Contient l'objet de la REQUETE")]