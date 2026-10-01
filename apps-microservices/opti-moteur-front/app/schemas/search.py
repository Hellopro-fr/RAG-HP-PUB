"""Schemas pydantic pour l'API search."""
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    query: str = Field(..., description="Requete textuelle du commercial", examples=["armoire medicale"])
    query_vector: List[float] = Field(..., description="Vecteur CamemBERT 1024 dims de la query")
    collection: Optional[str] = Field(None, description="Collection Typesense (override settings)")
    top_k: Optional[int] = Field(10, ge=1, le=100, description="Nombre de resultats a retourner")
    candidates: Optional[int] = Field(50, ge=10, le=200, description="Candidats pour re-rank")
    apply_filter_by_category: bool = Field(True, description="Applique filter_by si categorie detectee")


class ScoreDetail(BaseModel):
    vector: float
    bm25: float
    name_match: float
    cat_match: float
    penalty: str = ""


class Hit(BaseModel):
    id_produit: str
    nom_produit: str
    categorie: str
    # id_categorie : requis cote front PHP pour reconstruire l'URL fiche produit
    # (pattern /<slug>-<id_categorie>-<id_produit>-produit.html). Sans ce champ,
    # PHP filtre et rejette les hits -> 0 resultat affiche malgre 30 hits API.
    id_categorie: str = ""
    fournisseur: str = ""
    id_fournisseur: str = ""
    marque: str = ""
    # etat / affichage : utilises par PHP pour le boost des societes clientes
    # (logique moteur_solr : etat='Client' OU etat='Pause'+affichage='Complet').
    etat: str = ""
    affichage: str = ""
    prix_ht: Optional[float] = None
    score: float
    scores_detail: ScoreDetail


class Latency(BaseModel):
    detect: int
    typesense: int
    rerank: int
    total: int


class SearchResponse(BaseModel):
    query: str
    detected_category: Optional[str]
    detection_confidence: float
    filter_by_category: Optional[List[str]]
    latency_ms: Latency
    total_candidates: int
    results: List[Hit]
