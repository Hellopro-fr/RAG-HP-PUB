from pydantic import BaseModel, Field
from typing import List, Optional, Union, Dict, Any
from datetime import datetime


class Constraint(BaseModel):
    id_caracteristique: str
    unite: Optional[str] = None
    valeurs_cibles: Optional[Union[List[str], Dict[str, Any]]] = None
    valeurs_bloquantes: Optional[Union[List[str], Dict[str, Any]]] = None


class ComplexFilterRequest(BaseModel):
    ids: Dict[str, List[Constraint]] = Field(
        ...,
        description="Map of Reponse ID to list of Constraints. Example: {'q_22_r_1': [{'id_caracteristique': '29', 'valeurs_cibles': ['3']}]}",
    )
    id_categorie: Optional[str] = Field(
        None,
        description="Optional Category ID to filter products. If provided, only products belonging to this category will be returned.",
    )
    top_k: int = 50
    v: int = 4


class ScoredProduct(BaseModel):
    id_produit: str
    nom_produit: str
    score: float
    details: List[Dict[str, Any]] = []
    info: Dict[str, Any] = {}

    class Config:
        extra = "allow"


class ResultProduct(BaseModel):
    data: List[ScoredProduct]
    info: Dict[str, Any] = {}


# --- Product Models ---


class CaracteristiqueResponse(BaseModel):
    nom: str = Field(
        ...,
        description="Formatted name of the characteristic (e.g. 'Hauteur : 1500mm')",
    )
    label: str = Field(..., description="Generic label (e.g. 'Hauteur')")
    id_caracteristique: str = Field(..., description="ID of the characteristic")
    valeur: Any = Field(..., description="Raw value (numeric or string)")
    id_valeur: str = Field(..., description="ID of the value")
    unite: Optional[str] = Field(None, description="Unit of measurement if applicable")
    type_donnee: Optional[str] = Field(
        None, description="Data type (numeric, text, etc.)"
    )
    valeur_min: Optional[float] = None
    valeur_max: Optional[float] = None


# --- Query / RAG Models ---


class QueryRequest(BaseModel):
    query: str = Field(
        ...,
        min_length=3,
        max_length=500,
        description="User's question in natural language.",
    )
    route: Optional[str] = ""
    user_id: str = "anonymous"


class QueryResponse(BaseModel):
    question: Optional[Any] = None
    retrieved_context: Optional[Any] = None
    generated_cypher: Optional[str] = None
    search_type: Optional[str] = None
    cypher_params: Optional[Dict[str, Any]] = None
    answer: Optional[str] = None


# --- Admin Models ---


class CypherQueryRequest(BaseModel):
    query: str = Field(..., description="The raw Cypher query to execute.")
    params: Optional[Dict[str, Any]] = Field(
        default_factory=dict, description="Optional parameters for the Cypher query."
    )


class CypherQueryResponse(BaseModel):
    results: List[Dict[str, Any]] = Field(
        ..., description="List of records returned by the query."
    )
    info: Optional[Dict[str, Any]] = Field(
        default_factory=dict, description="Execution metadata."
    )
