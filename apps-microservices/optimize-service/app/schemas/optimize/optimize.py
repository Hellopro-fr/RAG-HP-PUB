from pydantic import BaseModel
from typing import List, Dict, Any, Optional

class OptimRequest(BaseModel):
    id_produit_scrapping: str
    nom_produit: str
    description_produit: str
    categorie_produit : Optional[str] = None

class OptimResponse(BaseModel):
    data: List[Dict[str, Any]]