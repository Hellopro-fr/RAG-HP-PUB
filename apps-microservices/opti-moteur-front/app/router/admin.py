"""Routes d'administration Typesense."""
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.credentials import settings
from app.core.typesense_client import typesense_client

router = APIRouter(prefix="/admin", tags=["Admin"])


class SynonymRequest(BaseModel):
    """Payload pour enregistrer un synonyme Typesense."""
    id: str = Field(..., description="Identifiant unique du synonyme", examples=["minipelle"])
    synonyms: List[str] = Field(
        ...,
        description="Liste des termes synonymes (multi-way si root=null)",
        examples=[["minipelle", "mini pelle", "mini-pelle"]],
    )
    root: Optional[str] = Field(
        None,
        description="Si defini : synonyme one-way (seul root s'expand)",
    )


class SynonymsBatchRequest(BaseModel):
    """Batch pour enregistrer plusieurs synonymes d'un coup."""
    synonyms: List[SynonymRequest]


@router.get("/collections", summary="Liste des collections Typesense")
def list_collections():
    try:
        return typesense_client.client.collections.retrieve()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/collections/{name}", summary="Stats d'une collection")
def collection_stats(name: str):
    try:
        if not typesense_client.collection_exists(name):
            raise HTTPException(status_code=404, detail=f"Collection '{name}' not found")
        return typesense_client.collection_stats(name)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/collections/{name}", summary="Creer une collection avec schema standard")
def create_collection(name: str):
    try:
        return typesense_client.create_collection_if_missing(name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/collections/{name}", summary="Supprimer une collection (danger!)")
def delete_collection(name: str, confirm: bool = False):
    if not confirm:
        raise HTTPException(
            status_code=400,
            detail="Ajouter ?confirm=true pour confirmer la suppression",
        )
    try:
        typesense_client.client.collections[name].delete()
        return {"deleted": name}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------- Synonymes ----------

@router.get("/synonyms", summary="Lister les synonymes de la collection")
def list_synonyms(collection: Optional[str] = None):
    try:
        return typesense_client.list_synonyms(collection)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/synonyms", summary="Creer ou mettre a jour UN synonyme")
def upsert_synonym(req: SynonymRequest, collection: Optional[str] = None):
    try:
        return typesense_client.upsert_synonym(
            synonym_id=req.id,
            synonyms=req.synonyms,
            root=req.root,
            collection=collection,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/synonyms/batch", summary="Creer/mettre a jour plusieurs synonymes")
def upsert_synonyms_batch(req: SynonymsBatchRequest, collection: Optional[str] = None):
    """
    Pratique pour initialiser le jeu de synonymes metier (mots composes FR B2B) :
    minipelle, tractopelle, microchargeuse, etc.
    """
    results = []
    errors = []
    for s in req.synonyms:
        try:
            res = typesense_client.upsert_synonym(
                synonym_id=s.id, synonyms=s.synonyms, root=s.root, collection=collection,
            )
            results.append({"id": s.id, "ok": True, "response": res})
        except Exception as e:
            errors.append({"id": s.id, "ok": False, "error": str(e)})
    return {"ok": len(errors) == 0, "done": len(results), "errors": errors}


@router.delete("/synonyms/{synonym_id}", summary="Supprimer un synonyme")
def delete_synonym(synonym_id: str, collection: Optional[str] = None):
    try:
        return typesense_client.delete_synonym(synonym_id, collection)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
