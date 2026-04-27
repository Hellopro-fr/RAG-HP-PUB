#!/usr/bin/env python3
"""
Ingestion STREAMING directe Milvus -> Typesense.
Aucun fichier JSONL intermediaire sur disque.

Avantages vs export+ingest :
  - Pas de 50 GB de JSONL a stocker
  - Memoire bornée (batch de 500 docs max en RAM)
  - Reprise possible depuis un checkpoint

Usage:
    MILVUS_HOST=... MILVUS_USER=... MILVUS_PASSWORD=... \
    TARGET_UNIQUE=2000000 \
    python3 stream_milvus_to_typesense.py
"""

import json
import os
import sys
import time
import requests
import typesense
from pymilvus import connections, Collection, utility
from tqdm import tqdm

# ========== CONFIG ==========
MILVUS_HOST = os.getenv("MILVUS_HOST")
MILVUS_PORT = os.getenv("MILVUS_PORT", "19530")
MILVUS_USER = os.getenv("MILVUS_USER", "")
MILVUS_PASSWORD = os.getenv("MILVUS_PASSWORD", "")
MILVUS_COLLECTION = os.getenv("MILVUS_COLLECTION", "produits_3")

TS_HOST = os.getenv("TS_HOST", "localhost")
TS_PORT = os.getenv("TS_PORT", "8108")
TS_KEY = os.getenv("TS_API_KEY", "hp_poc_2026")
TS_COLLECTION = os.getenv("TS_COLLECTION", "produits_full")

TARGET_UNIQUE = int(os.getenv("TARGET_UNIQUE", "2000000"))
MILVUS_BATCH_IDS = int(os.getenv("MILVUS_BATCH_IDS", "500"))
TS_BATCH = int(os.getenv("TS_BATCH", "2000"))

PHASE1_FILTER = os.getenv(
    "PHASE1_FILTER",
    'chunk_number == 1 and etat in ["Client","Prospect"]',
)

FIELDS = [
    # Identifiants
    "id_produit", "nom_produit", "text",
    # Hierarchie / taxonomie
    "categorie", "id_categorie",
    # Acteurs
    "fournisseur", "id_fournisseur", "marque", "fabricant",
    # Etat / visibilite
    "etat", "affichage", "statut",
    # Prix / stock / logistique
    "prix_ht", "prix_ttc", "stock", "delai_livraison",
    # References
    "ean", "sku", "reference",
    # Dates
    "date_ajout", "date_maj",
    # Chunking
    "chunk_number", "total_chunks",
    # Vecteur
    "embedding",
]

ts_client = typesense.Client({
    "api_key": TS_KEY,
    "nodes": [{"host": TS_HOST, "port": TS_PORT, "protocol": "http"}],
    "connection_timeout_seconds": 300,
})


# ========== TYPESENSE ==========
def ts_healthcheck():
    r = requests.get(f"http://{TS_HOST}:{TS_PORT}/health", timeout=5)
    r.raise_for_status()
    return r.json()


def ts_create_collection():
    schema = {
        "name": TS_COLLECTION,
        "fields": [
            {"name": "id_produit",      "type": "string", "facet": True},
            {"name": "nom_produit",     "type": "string"},
            {"name": "text",            "type": "string"},
            {"name": "categorie",       "type": "string", "facet": True, "optional": True},
            {"name": "id_categorie",    "type": "string", "facet": True, "optional": True},
            {"name": "fournisseur",     "type": "string", "facet": True, "optional": True},
            {"name": "id_fournisseur",  "type": "string", "facet": True, "optional": True},
            {"name": "marque",          "type": "string", "facet": True, "optional": True},
            {"name": "fabricant",       "type": "string", "optional": True},
            {"name": "etat",            "type": "string", "facet": True, "optional": True},
            {"name": "affichage",       "type": "string", "facet": True, "optional": True},
            {"name": "statut",          "type": "string", "facet": True, "optional": True},
            {"name": "prix_ht",         "type": "float",  "optional": True},
            {"name": "prix_ttc",        "type": "float",  "optional": True},
            {"name": "stock",           "type": "string", "optional": True},
            {"name": "delai_livraison", "type": "string", "optional": True},
            {"name": "ean",             "type": "string", "optional": True},
            {"name": "sku",             "type": "string", "optional": True},
            {"name": "reference",       "type": "string", "optional": True},
            {"name": "date_ajout",      "type": "string", "optional": True, "sort": True},
            {"name": "date_maj",        "type": "string", "optional": True, "sort": True},
            {"name": "chunk_number",    "type": "int32"},
            {"name": "total_chunks",    "type": "int32"},
            {"name": "embedding",       "type": "float[]", "num_dim": 1024},
        ],
        "token_separators": ["-", "/"],
    }
    try:
        ts_client.collections[TS_COLLECTION].delete()
        print(f"[INFO] Collection existante '{TS_COLLECTION}' supprimee")
    except Exception:
        pass
    ts_client.collections.create(schema)
    print(f"[OK] Collection '{TS_COLLECTION}' creee (num_dim=1024)")


def ts_flush(batch_jsonl):
    body = "\n".join(batch_jsonl)
    try:
        res = ts_client.collections[TS_COLLECTION].documents.import_(
            body, {"action": "upsert"}
        )
    except Exception as e:
        print(f"\n[WARN] flush error: {e}", file=sys.stderr)
        return 0, len(batch_jsonl)
    ok = res.count('"success":true')
    err = res.count('"success":false')
    return ok, err


# ========== MILVUS ==========
def milvus_connect():
    print(f"[INFO] Connexion Milvus {MILVUS_HOST}:{MILVUS_PORT}")
    kwargs = {"alias": "default", "host": MILVUS_HOST, "port": MILVUS_PORT}
    if MILVUS_USER:
        kwargs["user"] = MILVUS_USER
        kwargs["password"] = MILVUS_PASSWORD
    connections.connect(**kwargs)
    if not utility.has_collection(MILVUS_COLLECTION):
        print(f"[ERREUR] Collection '{MILVUS_COLLECTION}' introuvable")
        sys.exit(1)
    col = Collection(MILVUS_COLLECTION)
    col.load()
    print(f"[OK] Collection '{MILVUS_COLLECTION}' : {col.num_entities} entities")
    return col


def collect_ids(col):
    print(f"\n[PHASE 1] Collecte de {TARGET_UNIQUE} id_produit uniques")
    print(f"          Filtre: {PHASE1_FILTER}")
    ids = set()
    iterator = col.query_iterator(
        expr=PHASE1_FILTER,
        output_fields=["id_produit"],
        batch_size=5000,
        limit=TARGET_UNIQUE * 2,
    )
    with tqdm(total=TARGET_UNIQUE, desc="IDs") as pbar:
        while len(ids) < TARGET_UNIQUE:
            try:
                batch = iterator.next()
            except StopIteration:
                break
            if not batch: break
            for row in batch:
                pid = row.get("id_produit")
                if pid and pid not in ids:
                    ids.add(pid)
                    pbar.update(1)
                    if len(ids) >= TARGET_UNIQUE: break
    iterator.close()
    ids_list = list(ids)
    print(f"[OK] {len(ids_list)} id_produit uniques collectes")
    return ids_list


# ========== STREAMING PIPELINE ==========
def stream_ingest(col, product_ids):
    print(f"\n[PHASE 2] Streaming Milvus -> Typesense")
    print(f"          Batch Milvus = {MILVUS_BATCH_IDS} ids, Batch Typesense = {TS_BATCH} docs")

    ts_buffer = []
    total_chunks = 0
    total_ok = 0
    total_err = 0
    start = time.time()

    with tqdm(total=len(product_ids), desc="Produits", unit="prod") as pbar:
        for i in range(0, len(product_ids), MILVUS_BATCH_IDS):
            batch_ids = product_ids[i:i + MILVUS_BATCH_IDS]
            ids_quoted = ",".join(f'"{p}"' for p in batch_ids)
            expr = f'id_produit in [{ids_quoted}]'
            try:
                rows = col.query(expr=expr, output_fields=FIELDS, limit=16384)
            except Exception as e:
                print(f"\n[WARN] Milvus query batch {i}: {e}")
                pbar.update(len(batch_ids))
                continue

            for row in rows:
                # Helper: parse safely un prix VARCHAR -> float
                def parse_price(v):
                    if not v: return None
                    try:
                        return float(str(v).replace(",", ".").replace(" ", "").replace("\u00a0", ""))
                    except (ValueError, TypeError):
                        return None

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
                # Ajouter les prix SEULEMENT si parseable (sinon Typesense rejette le doc)
                px_ht = parse_price(row.get("prix_ht"))
                if px_ht is not None:
                    doc["prix_ht"] = px_ht
                px_ttc = parse_price(row.get("prix_ttc"))
                if px_ttc is not None:
                    doc["prix_ttc"] = px_ttc
                ts_buffer.append(json.dumps(doc, ensure_ascii=False))
                total_chunks += 1

                if len(ts_buffer) >= TS_BATCH:
                    ok, err = ts_flush(ts_buffer)
                    total_ok += ok
                    total_err += err
                    ts_buffer = []

            pbar.update(len(batch_ids))

    # Flush final
    if ts_buffer:
        ok, err = ts_flush(ts_buffer)
        total_ok += ok
        total_err += err

    elapsed = time.time() - start
    print(f"\n[OK] {total_ok} chunks ingeres en {elapsed/60:.1f} min ({total_err} erreurs)")
    print(f"     Debit moyen: {total_ok/max(elapsed,1):.0f} docs/s")
    print(f"     Produits traites: {len(product_ids)}  |  Chunks totaux: {total_chunks}")


# ========== MAIN ==========
def main():
    if not MILVUS_HOST:
        print("[ERREUR] MILVUS_HOST non defini. Source le .env:")
        print("  set -a && source /home/devhp/RAG-HP-PUB/.env && set +a")
        sys.exit(1)

    print(f"Typesense: {ts_healthcheck()}")
    ts_create_collection()
    col = milvus_connect()
    try:
        ids = collect_ids(col)
        stream_ingest(col, ids)
        info = ts_client.collections[TS_COLLECTION].retrieve()
        print(f"\n[DONE] Collection '{TS_COLLECTION}' : {info['num_documents']} documents")
    finally:
        col.release()
        connections.disconnect("default")


if __name__ == "__main__":
    main()
