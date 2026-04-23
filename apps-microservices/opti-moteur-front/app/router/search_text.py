"""
Route POST /search/text : recherche hybride qui prend du TEXTE en entree
(pas de vecteur), embed via api-embedding-service, puis lance le pipeline
/search standard.

Fichier independant - ne modifie pas /app/router/search.py ni ses schemas.
"""
import logging

from fastapi import APIRouter, HTTPException

from app.schemas.search_text import SearchTextRequest
from app.schemas.search import SearchResponse  # re-use du schema de reponse existant
from app.services.embedding_client import embed_text
from app.services.search_service import search as do_search

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/search", tags=["Search Text"])


@router.post(
    "/text",
    response_model=SearchResponse,
    summary="Recherche hybride par texte (embed + search en un seul appel)",
)
def search_by_text(req: SearchTextRequest):
    """
    Endpoint simplifie pour les clients qui ne gerent pas les embeddings
    (ex: PHP front www.hellopro.fr).

    Pipeline :
      1. Si `use_vector=True` (defaut) : appelle api-embedding-service pour
         obtenir le vecteur CamemBERT 1024 et delegue au pipeline hybride.
      2. Si `use_vector=False` : skip l'embedding, pipeline pur BM25 +
         name_match + cat_match (plus rapide, utile pour A/B test).

    Retourne la meme structure que /search (SearchResponse).
    """
    vector = None
    if req.use_vector:
        # 1. Embed
        try:
            vector = embed_text(req.query)
        except Exception as e:
            logger.error("Embedding failed for query=%r: %s", req.query, e)
            raise HTTPException(
                status_code=503,
                detail=f"Embedding service unavailable: {e}",
            )

    # 2. Search (reutilise le service existant, vector=None si use_vector=False)
    try:
        return do_search(
            query=req.query,
            query_vector=vector,
            collection=req.collection,
            top_k=req.top_k,
            candidates=req.candidates,
            apply_filter_by_category=req.apply_filter_by_category,
        )
    except Exception as e:
        logger.error("Search failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
