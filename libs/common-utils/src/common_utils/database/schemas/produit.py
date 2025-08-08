from pydantic import BaseModel
from typing import List , Dict, Any

class InsertProduitRequest(BaseModel):
    chunk_id       : str
    embedding      : List[float]
    id_produit     : str
    nom_produit    : str
    id_categorie   : str
    categorie      : str
    id_fournisseur : str
    fournisseur    : str
    domaine        : str
    description    : str
    chunk_number   : int
    total_chunks   : int
    metadata       : Dict[str, Any] = {}