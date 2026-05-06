#!/usr/bin/env python3
"""
delete_orphans.py
==================
Supprime les produits qui sont dans Typesense `produits_prod` mais qui
ne sont PLUS dans Milvus (= produits supprimés/désactivés depuis la
dernière ingestion).

Le script `ingest_full_milvus.py` ne fait que UPSERT, il n'efface jamais.
Sans ce script, Typesense accumule des "orphelins" au fil du temps.

Stratégie :
  1. Liste tous les `id` (= "{id_produit}_{chunk_number}") dans Milvus
  2. Liste tous les `id` dans Typesense
  3. Diff : Typesense - Milvus = orphelins à supprimer
  4. Suppression batch via Typesense API delete_by_filter

Usage :
    cd /home/devhp/RAG-HP-PUB/apps-microservices/opti-moteur-front
    export $(grep -E '^(ZILLIZ_|MILVUS_|TYPESENSE_)' .env | xargs)
    export MILVUS_HOST="$ZILLIZ_URI"
    export MILVUS_PORT="$ZILLIZ_PORT"
    export MILVUS_USER="$ZILLIZ_USER"
    export MILVUS_PASSWORD="$ZILLIZ_PASSWORD"
    export TS_HOST="localhost"
    export TS_PORT="8108"
    export TS_API_KEY="hp_poc_2026"
    export TS_COLLECTION="produits_prod"

    cd vm
    python3 delete_orphans.py

Mode dry-run (compte sans supprimer) :
    DRY_RUN=1 python3 delete_orphans.py
"""
import os
import sys
import time
import requests
from pymilvus import connections, Collection, utility

# ========== CONFIG ==========
MILVUS_HOST       = os.getenv("MILVUS_HOST")
MILVUS_PORT       = os.getenv("MILVUS_PORT", "19530")
MILVUS_USER       = os.getenv("MILVUS_USER", "")
MILVUS_PASSWORD   = os.getenv("MILVUS_PASSWORD", "")
MILVUS_COLLECTION = os.getenv("MILVUS_COLLECTION", "produits_3")

TS_HOST       = os.getenv("TS_HOST", "localhost")
TS_PORT       = os.getenv("TS_PORT", "8108")
TS_KEY        = os.getenv("TS_API_KEY", "hp_poc_2026")
TS_COLLECTION = os.getenv("TS_COLLECTION", "produits_prod")

DRY_RUN = os.getenv("DRY_RUN", "0") == "1"
DELETE_BATCH_SIZE = int(os.getenv("DELETE_BATCH_SIZE", "100"))


def get_milvus_ids():
    """Retourne le set des `id_produit_chunk` actuels en Milvus."""
    print(f"[INFO] Connexion Milvus {MILVUS_HOST}:{MILVUS_PORT}...")
    kwargs = {"alias": "default", "host": MILVUS_HOST, "port": MILVUS_PORT}
    if MILVUS_USER:
        kwargs["user"] = MILVUS_USER
        kwargs["password"] = MILVUS_PASSWORD
    connections.connect(**kwargs)

    if not utility.has_collection(MILVUS_COLLECTION):
        print(f"[ERREUR] Collection Milvus '{MILVUS_COLLECTION}' introuvable")
        sys.exit(1)

    col = Collection(MILVUS_COLLECTION)
    col.load()
    print(f"[OK] Milvus '{MILVUS_COLLECTION}' charge : {col.num_entities} entities")

    ids = set()
    iterator = col.query_iterator(
        expr=None,
        output_fields=["id_produit", "chunk_number"],
        batch_size=1000,
    )
    n = 0
    start = time.time()
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
            n += 1
        if n % 10000 == 0:
            elapsed = time.time() - start
            print(f"  ... {n} ids chargés ({elapsed:.0f}s)")

    iterator.close()
    col.release()
    connections.disconnect("default")
    print(f"[OK] {len(ids)} ids distincts dans Milvus")
    return ids


def get_typesense_ids():
    """Retourne le set des `id` actuels dans Typesense produits_prod."""
    print(f"[INFO] Export Typesense {TS_HOST}:{TS_PORT}/{TS_COLLECTION}...")
    url = f"http://{TS_HOST}:{TS_PORT}/collections/{TS_COLLECTION}/documents/export?include_fields=id"
    r = requests.get(
        url,
        headers={"X-TYPESENSE-API-KEY": TS_KEY},
        stream=True,
        timeout=600,
    )
    r.raise_for_status()

    ids = set()
    n = 0
    start = time.time()
    for line in r.iter_lines():
        if not line:
            continue
        try:
            import json
            d = json.loads(line.decode("utf-8"))
            if "id" in d:
                ids.add(d["id"])
                n += 1
                if n % 50000 == 0:
                    elapsed = time.time() - start
                    print(f"  ... {n} ids chargés ({elapsed:.0f}s)")
        except Exception:
            continue
    print(f"[OK] {len(ids)} ids distincts dans Typesense")
    return ids


def delete_orphans(orphan_ids):
    """Supprime les ids orphelins par batch (Typesense delete_by_filter par id IN ...)."""
    if not orphan_ids:
        print("[OK] Aucun orphelin a supprimer")
        return 0, 0

    print(f"[INFO] Suppression de {len(orphan_ids)} orphelins...")
    if DRY_RUN:
        print("[DRY-RUN] Pas de suppression effective.")
        # Afficher quelques exemples
        sample = list(orphan_ids)[:10]
        print(f"  Exemples : {sample}")
        return 0, len(orphan_ids)

    deleted = 0
    errors = 0
    orphan_list = list(orphan_ids)
    for i in range(0, len(orphan_list), DELETE_BATCH_SIZE):
        batch = orphan_list[i:i + DELETE_BATCH_SIZE]
        # Typesense delete_by_filter : `id:= [id1,id2,id3]`
        filter_expr = f"id:= [{','.join(batch)}]"
        url = f"http://{TS_HOST}:{TS_PORT}/collections/{TS_COLLECTION}/documents"
        try:
            r = requests.delete(
                url,
                headers={"X-TYPESENSE-API-KEY": TS_KEY},
                params={"filter_by": filter_expr, "batch_size": str(DELETE_BATCH_SIZE)},
                timeout=60,
            )
            r.raise_for_status()
            res = r.json()
            deleted += res.get("num_deleted", 0)
            if (i // DELETE_BATCH_SIZE) % 50 == 0:
                print(f"  ... {deleted}/{len(orphan_ids)} supprimes")
        except Exception as e:
            print(f"[WARN] delete batch error: {e}")
            errors += len(batch)

    return deleted, errors


def main():
    if not MILVUS_HOST:
        print("[ERREUR] MILVUS_HOST manquant"); sys.exit(1)

    print(f"=== Suppression d'orphelins Typesense ===")
    print(f"Source Milvus : {MILVUS_COLLECTION}")
    print(f"Cible Typesense : {TS_COLLECTION}")
    print(f"DRY_RUN : {DRY_RUN}")
    print()

    milvus_ids = get_milvus_ids()
    typesense_ids = get_typesense_ids()

    orphans = typesense_ids - milvus_ids
    only_in_milvus = milvus_ids - typesense_ids

    print()
    print(f"=== Diff ===")
    print(f"  Dans Milvus uniquement     : {len(only_in_milvus)} (= a ingerer via ingest_full_milvus.py)")
    print(f"  Dans Typesense uniquement  : {len(orphans)} (= orphelins a supprimer)")
    print(f"  Dans les deux              : {len(milvus_ids & typesense_ids)}")
    print()

    if orphans:
        deleted, errors = delete_orphans(orphans)
        print(f"[DONE] {deleted} orphelins supprimes, {errors} erreurs")
    else:
        print("[OK] Pas d'orphelins, Typesense est synchronise.")


if __name__ == "__main__":
    main()
