from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Union, Dict, Any
from datetime import datetime
import re


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
    blocked_val: int | float = -2
    different_val: int | float = -0.3


class BaseNormalizer(BaseModel):
    @field_validator("*", mode="before")
    def normalize_whitespace(cls, v):
        if isinstance(v, str):
            return re.sub(r"\s+", " ", v).strip()
        return v


class ProduitPayload(BaseNormalizer):
    url: Optional[str] = Field(None, description="URL de la page du produit")
    nom_produit: str = Field(..., description="Nom commercial du produit")
    domaine: Optional[str] = Field(None, description="Domaine du site web source")
    fournisseur: Optional[str] = Field(
        None, description="Nom du fournisseur proposant le produit"
    )
    id_fournisseur: str = Field(..., description="ID numérique du fournisseur")
    categorie: Optional[str] = Field(
        None, description="Nom de la catégorie principale du produit"
    )
    id_categorie: str = Field(..., description="ID numérique de la catégorie")
    source: Optional[str] = Field(
        None, description="Origine de la donnée (ex: produits_bo)"
    )
    fichier_source: Optional[str] = Field(
        None, description="Nom du fichier d'où provient la donnée"
    )
    date_ajout: Optional[datetime] = Field(
        None, description="Date d'ajout du produit dans le système"
    )
    id_produit: str = Field(..., description="ID alphanumérique original du produit")
    sku: Optional[str] = Field(None, description="SKU (Stock Keeping Unit) du produit")
    ean: Optional[str] = Field(
        None, description="Code EAN (European Article Number) du produit"
    )
    url_image: Optional[str] = Field(None, description="URL vers les images du produit")
    reference: Optional[str] = Field(None, description="Référence fabricant du produit")
    prix_ttc: Optional[float] = Field(None, description="Prix Toutes Taxes Comprises")
    statut: Optional[str] = Field(
        None, description="Statut de disponibilité du produit (ex: En stock)"
    )
    description: Optional[str] = Field(
        None, description="Description technique ou commerciale du produit"
    )

    def get_graph_id(self) -> str:
        return f"id_produit_{self.id_produit}"


class ScoredProduct(ProduitPayload):
    score: float
    details: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="DEBUG: Detailed score breakdown per response.",
    )
    info: Dict[str, Any] = Field(
        default_factory=dict,
        description="DEBUG: List of information about the product.",
    )


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
