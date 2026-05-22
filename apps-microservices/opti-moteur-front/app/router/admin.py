"""Routes d'administration Typesense."""
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException
from pydantic import BaseModel, Field

from app.core.credentials import settings
from app.core.typesense_client import typesense_client
from app.services.synonyms_service import auto_generate_synonyms
from app.services import idf_service

router = APIRouter(prefix="/admin", tags=["Admin"])


def _check_admin_token(x_admin_token: Optional[str]) -> None:
    """Verifie le header X-Admin-Token. Raise 403 si invalide."""
    if not x_admin_token or x_admin_token != settings.ADMIN_TOKEN:
        raise HTTPException(
            status_code=403,
            detail="Missing or invalid X-Admin-Token header",
        )


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


# ---------- IDF (regeneration en background) ----------

@router.post(
    "/compute-idf",
    summary="Regenerer le dict IDF en background (compute_idf.py + reload)",
)
def admin_compute_idf(
    background_tasks: BackgroundTasks,
    collection: Optional[str] = None,
    x_admin_token: Optional[str] = Header(None, description="Token jetable"),
):
    """
    Lance `scripts/compute_idf.py` en background pour regenerer
    `app/data/idf_nom_produit.json` puis recharger le cache IDF en RAM.

    Securite : header `X-Admin-Token` requis.
    Duree typique : 2-5 min sur 2M docs.
    Pour suivre l'avancement : `GET /admin/compute-idf/status`.

    A appeler :
      - Manuellement apres une ingestion massive (cf migrate_to_gke.sh)
      - Automatiquement chaque semaine via cron PHP `compute_idf_weekly.php`
    """
    _check_admin_token(x_admin_token)

    if idf_service.is_running():
        raise HTTPException(
            status_code=429,
            detail="A regeneration is already running. See GET /admin/compute-idf/status",
        )

    background_tasks.add_task(idf_service.regenerate_idf_background, collection)
    return {
        "status": "started",
        "collection": collection or settings.TYPESENSE_COLLECTION,
        "note": "Run in background, ~2-5 min. Poll GET /admin/compute-idf/status",
    }


@router.get(
    "/compute-idf/status",
    summary="Statut de la derniere regeneration IDF",
)
def admin_compute_idf_status():
    """Retourne l'etat de la derniere regeneration : never_run/running/ok/error."""
    return idf_service.get_state()


# ---------- Synonymes auto-generation ----------

@router.post(
    "/synonyms/auto-generate",
    summary="Auto-generer les synonymes depuis TOUTES les categories de la collection",
)
def synonyms_auto_generate(
    collection: Optional[str] = None,
    dry_run: bool = False,
):
    """
    Scan toutes les categories ingerees dans Typesense, et pour chaque
    categorie multi-tokens (ex: 'Mini-pelles (moins de 10 tonnes)') genere
    automatiquement les variantes orthographiques equivalentes
    (minipelles / mini pelles / mini-pelles) comme synonyme multi-way.

    A appeler apres chaque ingestion de nouvelles categories. Sans liste
    metier manuelle : la source de verite est le catalogue Typesense.

    Parametres query :
      - collection (optional) : override settings.TYPESENSE_COLLECTION
      - dry_run (default false) : si true, calcule mais ne push rien
        (utile pour revue avant activation).
    """
    try:
        return auto_generate_synonyms(collection=collection, dry_run=dry_run)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
