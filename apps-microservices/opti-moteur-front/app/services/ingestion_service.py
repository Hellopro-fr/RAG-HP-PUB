"""
Service d'ingestion streaming Milvus -> Typesense, par categorie.
Pour chaque categorie :
  1. Query Milvus (filtre categorie + etat/affichage optionnel)
  2. Transforme les rows en docs Typesense
  3. Push en batch d'upsert (par defaut 1000)

Retourne stats par categorie pour monitoring.
"""
import json
import logging
import shutil
import time
from typing import Dict, List, Optional, Any, Tuple

from app.core.credentials import settings
from app.core.milvus_connector import milvus
from app.core.typesense_client import typesense_client

logger = logging.getLogger(__name__)


MILVUS_OUTPUT_FIELDS = [
    "id_produit", "nom_produit", "text",
    "categorie", "id_categorie",
    "fournisseur", "id_fournisseur", "marque", "fabricant",
    "etat", "affichage", "statut",
    "prix_ht", "prix_ttc", "stock", "delai_livraison",
    "ean", "sku", "reference",
    "date_ajout", "date_maj",
    "chunk_number", "total_chunks",
    "embedding",
]


def _parse_price(v: Any) -> Optional[float]:
    if not v:
        return None
    try:
        return float(str(v).replace(",", ".").replace(" ", "").replace("\u00a0", ""))
    except (ValueError, TypeError):
        return None


def _row_to_doc(row: Dict[str, Any]) -> Dict[str, Any]:
    doc = {
        "id": f"{row['id_produit']}_{int(row.get('chunk_number', 0) or 0)}",
        "id_produit":      str(row.get("id_produit", "")),
        "nom_produit":     (row.get("nom_produit") or "")[:500],
        "text":            (row.get("text") or "")[:2000],
        "categorie":       row.get("categorie") or "",
        "id_categorie":    str(row.get("id_categorie") or ""),
        "fournisseur":     row.get("fournisseur") or "",
        "id_fournisseur":  str(row.get("id_fournisseur") or ""),
        "marque":          row.get("marque") or "",
        "fabricant":       row.get("fabricant") or "",
        "etat":            row.get("etat") or "",
        "affichage":       row.get("affichage") or "",
        "statut":          row.get("statut") or "",
        "stock":           row.get("stock") or "",
        "delai_livraison": row.get("delai_livraison") or "",
        "ean":             row.get("ean") or "",
        "sku":             row.get("sku") or "",
        "reference":       row.get("reference") or "",
        "date_ajout":      row.get("date_ajout") or "",
        "date_maj":        row.get("date_maj") or "",
        "chunk_number":    int(row.get("chunk_number", 0) or 0),
        "total_chunks":    int(row.get("total_chunks", 1) or 1),
        "embedding":       list(row["embedding"]),
    }
    ph = _parse_price(row.get("prix_ht"))
    if ph is not None:
        doc["prix_ht"] = ph
    pt = _parse_price(row.get("prix_ttc"))
    if pt is not None:
        doc["prix_ttc"] = pt
    return doc


def _disk_free_gb(path: str = "/") -> float:
    return shutil.disk_usage(path).free / (1024 ** 3)


def _flush_to_typesense(collection: str, batch: List[str]) -> Tuple[int, int]:
    if not batch:
        return 0, 0
    body = "\n".join(batch)
    try:
        res = typesense_client.client.collections[collection].documents.import_(
            body, {"action": "upsert"}
        )
    except Exception as e:
        logger.warning("Typesense flush error: %s", e)
        return 0, len(batch)
    return res.count('"success":true'), res.count('"success":false')


async def ingest_by_category(
    categorie: str,
    ts_collection: Optional[str] = None,
    extra_filter: Optional[str] = None,
    batch_size: int = 1000,
) -> Dict[str, Any]:
    """Ingere tous les chunks Milvus d'une categorie. Retourne stats."""
    ts_collection = ts_collection or settings.TYPESENSE_COLLECTION

    # Ensure Typesense collection exists
    typesense_client.create_collection_if_missing(ts_collection)

    # Build Milvus expression
    safe_cat = categorie.replace('"', '')
    expr = f'categorie == "{safe_cat}"'
    if extra_filter:
        expr = f'({expr}) and ({extra_filter})'

    # Query Milvus (async wrap)
    t_start = time.time()
    rows = await milvus.query(
        settings.MILVUS_COLLECTION,
        expr=expr,
        output_fields=MILVUS_OUTPUT_FIELDS,
        limit=16384,
    )
    t_milvus = time.time() - t_start

    # Stream to Typesense
    t_start = time.time()
    buffer: List[str] = []
    total_chunks = 0
    total_ok = 0
    total_err = 0
    for row in rows:
        try:
            doc = _row_to_doc(row)
        except Exception as e:
            logger.warning("row_to_doc error: %s", e)
            total_err += 1
            continue
        buffer.append(json.dumps(doc, ensure_ascii=False))
        total_chunks += 1
        if len(buffer) >= batch_size:
            ok, err = _flush_to_typesense(ts_collection, buffer)
            total_ok += ok
            total_err += err
            buffer = []
    if buffer:
        ok, err = _flush_to_typesense(ts_collection, buffer)
        total_ok += ok
        total_err += err
    t_ts = time.time() - t_start

    stats = typesense_client.collection_stats(ts_collection)
    return {
        "categorie": categorie,
        "chunks_milvus":    total_chunks,
        "chunks_ok":        total_ok,
        "chunks_err":       total_err,
        "typesense_docs":   stats.get("num_documents", 0),
        "disk_free_gb":     round(_disk_free_gb("/"), 2),
        "latency_ms": {
            "milvus_query": round(t_milvus * 1000),
            "typesense_push": round(t_ts * 1000),
        },
    }


async def ingest_categories_batch(
    categories: List[str],
    ts_collection: Optional[str] = None,
    extra_filter: Optional[str] = None,
    batch_size: int = 1000,
    stop_if_disk_gb_below: float = 3.0,
) -> Dict[str, Any]:
    """Ingere une liste de categories sequentiellement, avec garde-fou disque."""
    ts_collection = ts_collection or settings.TYPESENSE_COLLECTION
    results = []
    total_chunks = 0
    total_ok = 0
    stopped_reason = None
    t_start = time.time()

    for i, cat in enumerate(categories, 1):
        logger.info("[%d/%d] Ingestion categorie '%s'", i, len(categories), cat)
        try:
            r = await ingest_by_category(cat, ts_collection, extra_filter, batch_size)
        except Exception as e:
            logger.error("Erreur categorie '%s': %s", cat, e)
            r = {"categorie": cat, "error": str(e)}
        results.append(r)
        total_chunks += r.get("chunks_milvus", 0)
        total_ok += r.get("chunks_ok", 0)

        # Garde-fou disque
        disk_free = _disk_free_gb("/")
        if disk_free < stop_if_disk_gb_below:
            stopped_reason = f"disk_free={disk_free:.2f}GB < threshold={stop_if_disk_gb_below}GB"
            logger.warning("Arret preventif : %s", stopped_reason)
            break

    return {
        "categories_processed": len(results),
        "categories_total":     len(categories),
        "total_chunks_milvus":  total_chunks,
        "total_chunks_ok":      total_ok,
        "stopped_reason":       stopped_reason,
        "elapsed_s":            round(time.time() - t_start, 1),
        "per_category":         results,
    }
