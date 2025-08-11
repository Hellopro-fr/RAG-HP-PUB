from pydantic import BaseModel
from typing import List , Dict, Any

class InsertDevisRequest(BaseModel):
    id_lead          : str
    message          : str
    message_hellopro : str
    categorie        : str
    effectif         : str
    prof_ou_part     : str
    naf2             : str
    naf5             : str
    departement      : str
    region           : str
    pays             : str
    critere          : str
    societe          : str
    date_ajout       : str
    chunk_id         : str
    embedding        : List[float]
    chunk_number     : int
    total_chunks     : int
    metadata         : Dict[str, Any] = {}