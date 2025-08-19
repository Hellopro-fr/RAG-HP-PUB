from pydantic import BaseModel
from typing import List , Dict, Any

class InsertWebsiteRequest(BaseModel):
    url             : str
    categorie       : str
    id_categorie    : str
    page_type       : str
    domaine         : str
    fournisseur     : str
    id_fournisseur  : str
    etat            : str
    affichage       : str
    date_ajout      : str
    chunk_id        : str
    text            : str
    embedding       : List[float]
    chunk_number    : int
    total_chunks    : int
    metadata        : Dict[str, Any] = {}