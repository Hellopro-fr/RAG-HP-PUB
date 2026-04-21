"""Routes de recherche."""
from fastapi import APIRouter, HTTPException

from app.schemas.search import SearchRequest, SearchResponse
from app.services.search_service import search as do_search

router = APIRouter(prefix="/search", tags=["Search"])


@router.post("", response_model=SearchResponse, summary="Recherche hybride produit")
def search_products(req: SearchRequest):
    """
    Execute une recherche hybride Typesense :
      1. Detection categorie via facet + prefix-match filter
      2. Hybrid search (BM25 sur nom/categorie/text + vector kNN)
      3. Re-rank Python pondere sur top-50 candidats

    Necessite un `query_vector` pre-calcule (CamemBERT 1024 dims).
    Pour embedder la query depuis le texte, appeler d'abord
    `api-embedding-service` / `rag_embed_text`.
    """
    try:
        return do_search(
            query=req.query,
            query_vector=req.query_vector,
            collection=req.collection,
            top_k=req.top_k,
            candidates=req.candidates,
            apply_filter_by_category=req.apply_filter_by_category,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
