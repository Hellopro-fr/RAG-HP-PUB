from pydantic import BaseModel
from typing import List , Dict, Any

class InsertEchangeRequest(BaseModel):
    id_demande      : str
    categorie       : str
    id_categorie    : str
    produit         : str
    id_produit      : str
    fournisseur     : str
    id_fournisseur  : str
    etat            : str
    affichage       : str
    acheteur        : str
    id_acheteur     : str
    date_ajout      : str
    chunk_id        : str
    text            : str
    embedding       : List[float]
    chunk_number    : int
    total_chunks    : int
    metadata        : Dict[str, Any] = {}