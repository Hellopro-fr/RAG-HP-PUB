from os import error
from pydantic import BaseModel, Field
from typing import Annotated, List, Optional, Dict, Any, Union


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
    reranker_model: Optional[str] = ("BAAI/bge-reranker-v2-m3",)
    get_n_chunks_pj: bool = (False,)


class SourcesFiltre(BaseModel):
    source: str
    filtre: Dict[str, Any] = {}


class LLMOptions(BaseModel):
    chat_model: str = "gpt-4.1-2025-04-14"
    temperature: float = 0.0
    template_prompt: Optional[str] = ""
    provider: str = ""
    thinking_level: str = "high"


class RerankerOptions(BaseModel):
    use_reranker: bool = True
    reranker_model: str = "BAAI/bge-reranker-v2-m3"
    rrf: bool = False
    ponderation: float = 1.1


class HybridSearchOptions(BaseModel):
    """Paramètres d'exploration pour la recherche hybride (dense + BM25)."""

    ef: Optional[int] = (
        None  # HNSW search breadth (None = auto ~300, 2000+ = meilleur rappel)
    )
    radius: Optional[float] = None  # Seuil de similarité minimum (COSINE: 0.0 à 1.0)
    range_filter: Optional[float] = None  # Seuil de similarité maximum
    drop_ratio_search: float = (
        0.0  # BM25: proportion des termes faibles à ignorer (0.0 = max précision)
    )
    dense_limit_multiplier: int = (
        1  # Facteur de sur-récupération (3+ = plus de candidats pour fusion)
    )
    ranker_type: str = "rrf"  # "weighted" ou "rrf" (Reciprocal Rank Fusion)
    rrf_k: int = 60  # Constante de lissage RRF (10-100)


class SearchRequestWs(BaseModel):
    prompt: str
    source: Optional[List[SourcesFiltre]] = [
        SourcesFiltre(source="produits_3", filtre={})
    ]
    action: Optional[int] = 1
    top_k: Optional[int] = 10
    filtre: Optional[Dict[str, Any]] = {}
    fields: Optional[List[str]] = []
    llm: Optional[LLMOptions] = LLMOptions(
        chat_model="gpt-4.1-2025-04-14", temperature=0.0
    )
    options: Optional[RerankerOptions] = RerankerOptions()
    type: int = 1
    cache: bool = (True,)
    get_n_chunks_pj: bool = (False,)
    hybrid: bool = False
    hybrid_options: Optional[HybridSearchOptions] = HybridSearchOptions()


# Schéma de réponse détaillé
class SearchResponse(BaseModel):
    database: str
    user_query: str
    filter: Optional[Any] = None
    matches: Dict[str, List[Any]]
    context: Optional[str] = ""
    response: Optional[str] = ""
    embedding: Union[float, str]
    fournisseur_non_vide: Optional[bool] = None
    full_user_prompt: Optional[str] = ""
    chat_model: Optional[str] = None
    temperature: float = 0.0

    vector_search: Union[float, str]
    total_process: Union[float, str]
    llm_execution: Union[float, str]
    import_duration: Union[float, str]
    llm_reponse: Optional[dict] = {}


class LLMPipeline(BaseModel):
    llm_response: str = ""
    llm_duration: Union[float, str] = 0
    full_user_prompt: str = ""
    context: str = ""
    response: dict = {}
    error: Optional[bool] = False


class SearchReponse(BaseModel):
    results: Annotated[
        SearchResponse,
        Field(title="Contient l'objet du résultat depuis les recherches"),
    ]
    # TODO:
    # à supprimer les données en entrées pour vérification
    post: Annotated[
        SearchRequestWs,
        Field(title="Contient l'objet de la requête depuis les recherches"),
    ]
