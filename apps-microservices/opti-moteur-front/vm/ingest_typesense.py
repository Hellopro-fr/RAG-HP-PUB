#!/usr/bin/env python3
"""
Ingestion du JSONL (export Milvus) vers Typesense collection produits_200k.
Streaming : lit le fichier ligne par ligne, batch d'import de 2000 docs.

Usage:
    python3 ingest_typesense.py
    # ou
    INPUT=data/subset.jsonl BATCH=5000 python3 ingest_typesense.py
"""

import json
import os
import sys
import time
import requests
import typesense
from tqdm import tqdm

# =============================================================================
# CONFIG
# =============================================================================
TS_HOST = os.getenv("TS_HOST", "localhost")
TS_PORT = os.getenv("TS_PORT", "8108")
TS_KEY = os.getenv("TS_API_KEY", "hp_poc_2026")
COLLECTION = os.getenv("TS_COLLECTION", "produits_200k")
INPUT_FILE = os.getenv("INPUT", "data/products_200k.jsonl")
BATCH_SIZE = int(os.getenv("BATCH", "2000"))

client = typesense.Client({
    "api_key": TS_KEY,
    "nodes": [{"host": TS_HOST, "port": TS_PORT, "protocol": "http"}],
    "connection_timeout_seconds": 300,
})


def healthcheck():
    try:
        r = requests.get(f"http://{TS_HOST}:{TS_PORT}/health", timeout=5)
        r.raise_for_status()
        print(f"[OK] Typesense healthy: {r.json()}")
    except Exception as e:
        print(f"[ERREUR] Typesense injoignable sur http://{TS_HOST}:{TS_PORT}: {e}")
        print("        Lance: docker compose up -d")
        sys.exit(1)


def create_collection():
    schema = {
        "name": COLLECTION,
        "fields": [
            {"name": "id_produit",   "type": "string", "facet": True},
            {"name": "nom_produit",  "type": "string"},
            {"name": "text",         "type": "string"},
            {"name": "categorie",    "type": "string", "facet": True, "optional": True},
            {"name": "id_categorie", "type": "string", "facet": True, "optional": True},
            {"name": "fournisseur",  "type": "string", "facet": True, "optional": True},
            {"name": "marque",       "type": "string", "facet": True, "optional": True},
            {"name": "fabricant",    "type": "string", "optional": True},
            {"name": "chunk_number", "type": "int32"},
            {"name": "total_chunks", "type": "int32"},
            {"name": "embedding",    "type": "float[]", "num_dim": 1024},
        ],
        "token_separators": ["-", "/"],
    }
    try:
        client.collections[COLLECTION].delete()
        print(f"[INFO] Collection '{COLLECTION}' existante supprimee")
    except Exception:
        pass
    client.collections.create(schema)
    print(f"[OK] Collection '{COLLECTION}' creee (num_dim=1024, CamemBERT)")


def count_lines(path):
    n = 0
    with open(path, "rb") as f:
        for _ in f:
            n += 1
    return n


def flush(batch):
    body = "\n".join(batch)
    try:
        res = client.collections[COLLECTION].documents.import_(body, {"action": "upsert"})
    except Exception as e:
        print(f"[WARN] flush error: {e}")
        return 0, len(batch)
    ok = res.count('"success":true')
    err = res.count('"success":false')
    return ok, err


def ingest():
    if not os.path.exists(INPUT_FILE):
        print(f"[ERREUR] Fichier introuvable : {INPUT_FILE}")
        print(f"        Lance d'abord : python3 export_from_milvus.py")
        sys.exit(1)

    print(f"[INFO] Comptage des lignes de {INPUT_FILE}...")
    n_total = count_lines(INPUT_FILE)
    print(f"[INFO] {n_total} documents a ingerer (batch={BATCH_SIZE})")

    start = time.time()
    batch = []
    ok_total = err_total = 0

    with open(INPUT_FILE, "r", encoding="utf-8") as f, \
         tqdm(total=n_total, desc="Ingest", unit="doc") as pbar:
        for line in f:
            line = line.rstrip("\n")
            if not line:
                continue
            batch.append(line)
            if len(batch) >= BATCH_SIZE:
                ok, err = flush(batch)
                ok_total += ok
                err_total += err
                pbar.update(len(batch))
                batch = []
        if batch:
            ok, err = flush(batch)
            ok_total += ok
            err_total += err
            pbar.update(len(batch))

    elapsed = time.time() - start
    print(f"\n[OK] {ok_total} ingeres en {elapsed:.1f}s ({err_total} erreurs)")
    print(f"     Debit: {ok_total / max(elapsed,1):.0f} docs/s")


def main():
    healthcheck()
    create_collection()
    ingest()

    info = client.collections[COLLECTION].retrieve()
    print(f"\n[DONE] Collection '{COLLECTION}' prete : {info['num_documents']} documents")
    print(f"       -> Prochaine etape : python3 search.py")


if __name__ == "__main__":
    main()
