from os import error
from pydantic import BaseModel, Field
from typing import Annotated, List, Optional, Dict, Any

# Ce schéma est identique à celui du notebook, comme demandé.
class SearchRequest(BaseModel):
    prompt: str
    source: Optional[List[str]] = ["produits"]
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
    params: Optional[Dict[str, Any]] = {}
    use_reranker: Optional[bool] = True
    reranker_model: Optional[str] = "BAAI/bge-reranker-v2-m3"

class SourcesFiltre(BaseModel):
    source: str
    filtre: Dict[str, Any] = {}
    
class LLMOptions(BaseModel):
    chat_model: str = "gpt-4.1-2025-04-14"
    temperature: float = 0.0
    template_prompt: Optional[str] = ""

class RerankerOptions(BaseModel):
    use_reranker: bool = True
    reranker_model: str = "BAAI/bge-reranker-v2-m3"
    rrf: bool = False

class SearchRequestWs(BaseModel):
    prompt: str
    source: Optional[List[SourcesFiltre]] = [SourcesFiltre(source="produits", filtre={})]
    action: Optional[int] = 1
    top_k: Optional[int] = 10
    filtre: Optional[Dict[str, Any]] = {}
    filtre_source: Optional[Dict[str, List[str]]] = {}
    llm: Optional[LLMOptions] = LLMOptions(chat_model="gpt-4.1-2025-04-14", temperature=0.0)
    options: Optional[RerankerOptions] = RerankerOptions()
    type: int = 1

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
    temperature: float = ""
    vector_search: float
    total_process: float
    llm_execution: float
    import_duration: float
    llm_reponse: Optional[dict] = {}

class LLMPipeline(BaseModel):
    llm_response: str = ""
    llm_duration: float = ""
    full_user_prompt: str = ""
    context: str = ""
    response: dict = {}
    error: Optional[bool] = False
    
class SearchReponse(BaseModel):
    results: Annotated[SearchResponse, Field(title="Contient l'objet du résultat depuis les recherches")]
    # TODO:
    # à supprimer les données en entrées pour vérification
    post:  Annotated[SearchRequestWs, Field(title="Contient l'objet de la requête depuis les recherches")]