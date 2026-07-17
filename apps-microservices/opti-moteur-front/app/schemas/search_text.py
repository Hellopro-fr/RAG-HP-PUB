"""
Schemas pydantic pour l'endpoint /search/text.
Distincts de search.py pour ne PAS toucher aux schemas existants.
"""
from typing import Optional
from pydantic import BaseModel, Field


class SearchTextRequest(BaseModel):
    """
    Variante de SearchRequest qui n'exige PAS le vecteur en entree.
    Le vecteur sera calcule en interne via api-embedding-service.

    Cible : integration depuis PHP front ou tout client qui ne gere pas
    les embeddings.
    """
    query: str = Field(..., description="Requete textuelle", examples=["armoire medicale"])
    collection: Optional[str] = Field(None, description="Collection Typesense (override settings)")
    top_k: Optional[int] = Field(10, ge=1, le=2000, description="Nombre de resultats a retourner")
    candidates: Optional[int] = Field(50, ge=10, le=2000, description="Candidats pour re-rank")
    offset: Optional[int] = Field(
        0,
        ge=0,
        le=2000,
        description=(
            "Decalage dans les resultats re-ranked, pour la pagination AJAX. "
            "Ex: offset=40 top_k=40 -> page 2 (produits 41-80)."
        ),
    )
    apply_filter_by_category: bool = Field(True, description="Applique filter_by si categorie detectee")
    use_vector: bool = Field(
        True,
        description=(
            "Si True (defaut) : pipeline hybride (BM25 + kNN vecteur CamemBERT + rerank). "
            "Si False : pur BM25 + name_match + cat_match (pas d'appel a api-embedding-service, "
            "plus rapide d'environ 300-500 ms, perd la remontee semantique de synonymes)."
        ),
    )
