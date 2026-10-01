"""
Sync incremental Milvus -> Typesense.

Pour chaque appel :
  1. Upsert (insert/update) les produits Milvus modifies depuis `since`
     (champ date_maj). Couvre les NOUVEAUX et les MAJ.
  2. Supprime de Typesense les produits qui ne sont plus en Milvus
     (= orphelins, comparaison full ids).

Retourne stats pour monitoring.
"""
import json
import logging
import shutil
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

import requests
from app.core.credentials import settings
from app.core.milvus_connector import milvus
from app.core.typesense_client import typesense_client
from app.services.ingestion_service import _row_to_doc, MILVUS_OUTPUT_FIELDS

logger = logging.getLogger(__name__)


def _ts_url(path: str) -> str:
    proto = settings.TYPESENSE_PROTOCOL or "http"
    host = settings.TYPESENSE_HOST
    port = settings.TYPESENSE_PORT
    return f"{proto}://{host}:{port}{path}"


def _ts_headers() -> Dict[str, str]:
    return {
        "X-TYPESENSE-API-KEY": settings.TYPESENSE_API_KEY,
        "Content-Type": "application/json",
    }


def _ts_doc_count(collection: str) -> int:
    try:
        r = requests.get(_ts_url(f"/collections/{collection}"), headers=_ts_headers(), timeout=10)
        return r.json().get("num_documents", 0)
    except Exception:
        return 0


def _ts_flush_upsert(collection: str, jsonl_batch: List[str]) -> tuple[int, int]:
    if not jsonl_batch:
        return 0, 0
    body = "\n".join(jsonl_batch).encode("utf-8")
    url = _ts_url(f"/collections/{collection}/documents/import?action=upsert")
    try:
        r = requests.post(
            url,
            headers={
                "X-TYPESENSE-API-KEY": settings.TYPESENSE_API_KEY,
                "Content-Type": "text/plain; charset=utf-8",
            },
            data=body,
            timeout=300,
        )
        r.raise_for_status()
        text = r.text
    except Exception as e:
        logger.error(f"ts_flush_upsert error: {e}")
        return 0, len(jsonl_batch)
    ok = text.count('"success":true')
    err = text.count('"success":false')
    return ok, err


def _ts_export_ids(collection: str) -> set:
    """Export tous les `id` actuels dans Typesense."""
    url = _ts_url(f"/collections/{collection}/documents/export?include_fields=id")
    r = requests.get(
        url,
        headers={"X-TYPESENSE-API-KEY": settings.TYPESENSE_API_KEY},
        stream=True,
        timeout=600,
    )
    r.raise_for_status()
    ids = set()
    for line in r.iter_lines():
        if not line:
            continue
        try:
            d = json.loads(line.decode("utf-8"))
            if "id" in d:
                ids.add(d["id"])
        except Exception:
            continue
    return ids


def _milvus_get_ids() -> set:
    """Retourne le set des ids actuels en Milvus (id_produit_chunk)."""
    col = milvus.get_collection(settings.MILVUS_COLLECTION)
    iterator = col.query_iterator(
        expr=None,
        output_fields=["id_produit", "chunk_number"],
        batch_size=2000,
    )
    ids = set()
    while True:
        try:
            batch = iterator.next()
        except StopIteration:
            break
        if not batch:
            break
        for row in batch:
            pid = row.get("id_produit")
            ch = int(row.get("chunk_number", 0) or 0)
            if pid:
                ids.add(f"{pid}_{ch}")
    iterator.close()
    return ids


def _milvus_get_recent(since_iso: str, limit: int = 0) -> List[Dict[str, Any]]:
    """Retourne les rows Milvus avec date_maj >= since_iso."""
    col = milvus.get_collection(settings.MILVUS_COLLECTION)
    expr = f'date_maj >= "{since_iso}"'
    iterator = col.query_iterator(
        expr=expr,
        output_fields=MILVUS_OUTPUT_FIELDS,
        batch_size=500,
    )
    rows = []
    while True:
        try:
            batch = iterator.next()
        except StopIteration:
            break
        if not batch:
            break
        for row in batch:
            rows.append(row)
        if limit and len(rows) >= limit:
            break
    iterator.close()
    return rows


def sync_incremental(
    since_iso: Optional[str] = None,
    ts_collection: Optional[str] = None,
    delete_orphans: bool = True,
    batch_size: int = 1000,
) -> Dict[str, Any]:
    """
    Sync incremental Milvus -> Typesense.

    Args:
      since_iso : "2026-05-04T00:00:00" pour filtrer date_maj >= since.
                  Default : 24h ago.
      ts_collection : default = settings.TYPESENSE_COLLECTION (produits_prod)
      delete_orphans : True pour supprimer les produits plus en Milvus
      batch_size : upsert batch size

    Returns:
      {
        "ts_collection": "produits_prod",
        "since_iso": "2026-05-04T00:00:00",
        "milvus_recent_rows": 1234,
        "ts_upserted": 1230,
        "ts_upsert_errors": 4,
        "ts_orphans_deleted": 56,
        "duration_s": 123.45,
        "ts_docs_before": 2271240,
        "ts_docs_after": 2271184,
      }
    """
    if since_iso is None:
        since_iso = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")

    coll = ts_collection or settings.TYPESENSE_COLLECTION
    start = time.time()

    docs_before = _ts_doc_count(coll)
    logger.info(f"sync_incremental start | coll={coll} since={since_iso} docs={docs_before}")

    # Etape 1 : upsert les modifs recentes
    rows = _milvus_get_recent(since_iso)
    logger.info(f"  Milvus recent rows : {len(rows)}")

    ts_upserted = 0
    ts_errors = 0
    if rows:
        buffer = []
        for row in rows:
            try:
                doc = _row_to_doc(row)
                buffer.append(json.dumps(doc, ensure_ascii=False))
            except Exception as e:
                logger.warning(f"row_to_doc error: {e}")
                ts_errors += 1
                continue
            if len(buffer) >= batch_size:
                ok, err = _ts_flush_upsert(coll, buffer)
                ts_upserted += ok
                ts_errors += err
                buffer = []
        if buffer:
            ok, err = _ts_flush_upsert(coll, buffer)
            ts_upserted += ok
            ts_errors += err

    upsert_elapsed = time.time() - start
    logger.info(f"  Upsert done : {ts_upserted} ok, {ts_errors} err in {upsert_elapsed:.1f}s")

    # Etape 2 : supprimer les orphelins (en Typesense mais plus en Milvus)
    deleted = 0
    if delete_orphans:
        logger.info("  Computing orphans...")
        ts_ids = _ts_export_ids(coll)
        milvus_ids = _milvus_get_ids()
        orphans = ts_ids - milvus_ids
        logger.info(f"  TS ids: {len(ts_ids)}, Milvus ids: {len(milvus_ids)}, orphans: {len(orphans)}")

        if orphans:
            orphan_list = list(orphans)
            for i in range(0, len(orphan_list), 100):
                batch = orphan_list[i:i + 100]
                filter_expr = f"id:= [{','.join(batch)}]"
                url = _ts_url(f"/collections/{coll}/documents")
                try:
                    r = requests.delete(
                        url,
                        headers={"X-TYPESENSE-API-KEY": settings.TYPESENSE_API_KEY},
                        params={"filter_by": filter_expr, "batch_size": "100"},
                        timeout=60,
                    )
                    r.raise_for_status()
                    deleted += r.json().get("num_deleted", 0)
                except Exception as e:
                    logger.warning(f"delete batch err: {e}")

    docs_after = _ts_doc_count(coll)
    elapsed = time.time() - start
    logger.info(f"sync_incremental DONE in {elapsed:.1f}s | "
                f"upserted={ts_upserted} deleted={deleted} "
                f"docs={docs_before}->{docs_after}")

    return {
        "ts_collection": coll,
        "since_iso": since_iso,
        "milvus_recent_rows": len(rows),
        "ts_upserted": ts_upserted,
        "ts_upsert_errors": ts_errors,
        "ts_orphans_deleted": deleted,
        "duration_s": round(elapsed, 2),
        "ts_docs_before": docs_before,
        "ts_docs_after": docs_after,
    }
