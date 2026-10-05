from typing import Annotated, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, StringConstraints


class DemandeExecution(BaseModel):
    input: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    origine: str = Field("inconnue", max_length=100)
    version: Literal["publiee", "brouillon"] = "publiee"
    id_user_bo: Optional[int] = None
    variables: Dict[str, Annotated[str, StringConstraints(max_length=2000)]] = {}  # valeurs des variables cochées dans la fiche


class Usage(BaseModel):
    tokens_entree: int
    tokens_sortie: int
    recherches: int


class ReponseExecution(BaseModel):
    output: Optional[str]
    statut: Literal["ok", "format_invalide", "erreur", "timeout"]
    erreur: Optional[str] = None
    agent: str
    version: int
    etapes: List[str]
    usage: Usage
    trace: dict = {}  # recherches, pages lues, appels MCP, sources, tokens des outils, variables
    cout_usd: Optional[float]
    duree_ms: int
    execution_id: Optional[int]
