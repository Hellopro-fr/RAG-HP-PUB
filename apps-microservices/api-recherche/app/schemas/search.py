from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

# Ce schéma est identique à celui du notebook, comme demandé.
class SearchRequest(BaseModel):
    prompt: str
    source: Optional[List[str]] = []
    nombre_resultat: Optional[str] = "10"
    action: Optional[int] = 1
    categorie: Optional[Dict[str, str]] = {}
    fournisseur: Optional[Dict[str, str]] = {}
    etat: Optional[List[str]] = []
    affichage: Optional[List[str]] = []
    temperature: str = "0"
    template_prompt: Optional[str] = ""
    page_type: str = ""
    chat_model: str = "gpt-4.1-2025-04-14"

# Schéma de réponse détaillé pour correspondre à la sortie des fonctions de recherche
class SearchResponse(BaseModel):
    database: str
    user_query: str
    filter: Optional[Any] = None
    matches: Dict[str, List[Any]]
    context: Optional[str] = ""
    response: Optional[str] = ""
    embedding: float
    fournisseur_non_vide: Optional[bool] = None
    full_user_prompt: Optional[str] = ""
    chat_model: Optional[str] = None
    temperature: str
    vector_search: float
    total_process: float
    llm_execution: float
    import_duration: float

class LLMPipeline(BaseModel):
    llm_response: str = ""
    llm_duration: str = ""
    full_user_prompt: str = ""
    context: str = ""