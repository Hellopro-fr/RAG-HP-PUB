#!/usr/bin/env python3
"""
list_missing_categories.py
===========================
Liste les categories de Milvus qui n'ont PAS encore ete ingerees dans Typesense
(= toutes les categories Milvus MOINS celles deja dans batch 1 + batch 2).

Outputs :
  - categories_missing.txt          : 1 categorie par ligne (input pour ingest_by_categories.py)
  - categories_missing_chunks_NN.txt : split en lots de N categories (default 100)

Usage :
    cd /home/devhp/RAG-HP-PUB/apps-microservices/opti-moteur-front
    export $(grep -E '^(ZILLIZ_|MILVUS_)' .env | xargs)
    export MILVUS_HOST="$ZILLIZ_URI" MILVUS_PORT="$ZILLIZ_PORT"
    export MILVUS_USER="$ZILLIZ_USER" MILVUS_PASSWORD="$ZILLIZ_PASSWORD"
    export MILVUS_COLLECTION="produits_3"

    cd vm
    python3 list_missing_categories.py

    # Avec taille de chunk personnalisee
    CHUNK_SIZE=50 python3 list_missing_categories.py
"""
import os
import sys
import time
from pymilvus import connections, Collection, utility


MILVUS_HOST       = os.getenv("MILVUS_HOST")
MILVUS_PORT       = os.getenv("MILVUS_PORT", "19530")
MILVUS_USER       = os.getenv("MILVUS_USER", "")
MILVUS_PASSWORD   = os.getenv("MILVUS_PASSWORD", "")
MILVUS_COLLECTION = os.getenv("MILVUS_COLLECTION", "produits_3")

# Repo root (parent de apps-microservices)
REPO_ROOT = os.path.abspath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "..", ".."
))
RUBRIQUES_DIR = os.path.join(REPO_ROOT, "rubriques")

# Fichiers existants des batches deja ingeres
EXISTING_FILES = [
    os.path.join(RUBRIQUES_DIR, "categories_from_roots.txt"),     # Batch 1
    os.path.join(RUBRIQUES_DIR, "categories_from_roots_2.txt"),   # Batch 2
]

OUTPUT_FILE = os.path.join(RUBRIQUES_DIR, "categories_missing.txt")
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "100"))


def load_existing_categories():
    """Charge les categories deja ingerees (batch 1 + 2)."""
    existing = set()
    for path in EXISTING_FILES:
        if not os.path.exists(path):
            print(f"[WARN] {path} introuvable, on continue sans")
            continue
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    existing.add(line)
        print(f"[OK] {path} : {len(existing)} categories cumulees")
    return existing


def get_all_milvus_categories():
    """Retourne le set des categories distinctes presentes en Milvus."""
    if not MILVUS_HOST:
        print("[ERREUR] MILVUS_HOST manquant"); sys.exit(1)

    print(f"[INFO] Connexion Milvus {MILVUS_HOST}:{MILVUS_PORT}...")
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
    print(f"[OK] Milvus '{MILVUS_COLLECTION}' charge : {col.num_entities} entities")

    print(f"[INFO] Itère sur tous les produits pour collecter les categories distinctes...")
    cats = set()
    iterator = col.query_iterator(
        expr="categorie != ''",
        output_fields=["categorie"],
        batch_size=2000,
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
            c = row.get("categorie")
            if c:
                cats.add(c.strip())
            n += 1
        if n % 50000 == 0:
            print(f"  ... {n} rows iteres, {len(cats)} categories distinctes")

    iterator.close()
    col.release()
    connections.disconnect("default")

    elapsed = time.time() - start
    print(f"[OK] {len(cats)} categories distinctes en Milvus (en {elapsed:.0f}s)")
    return cats


def split_into_chunks(items, chunk_size):
    """Decoupe une liste en chunks de taille chunk_size."""
    items = sorted(items)
    chunks = []
    for i in range(0, len(items), chunk_size):
        chunks.append(items[i:i + chunk_size])
    return chunks


def main():
    print("=== List missing categories (Milvus -> Typesense) ===\n")

    # 1. Categories deja ingerees
    existing = load_existing_categories()
    print(f"[OK] Total categories deja ingerees (batch 1 + 2) : {len(existing)}\n")

    # 2. Toutes categories Milvus
    all_milvus = get_all_milvus_categories()
    print()

    # 3. Diff
    missing = all_milvus - existing
    extra = existing - all_milvus  # categories ingerees qui n'existent plus en Milvus

    print(f"=== Diff ===")
    print(f"  Categories Milvus           : {len(all_milvus)}")
    print(f"  Categories deja ingerees    : {len(existing)}")
    print(f"  Categories communes         : {len(all_milvus & existing)}")
    print(f"  MANQUANTES (a ingerer)      : {len(missing)}")
    print(f"  Plus en Milvus (deprecated) : {len(extra)}")
    print()

    if not missing:
        print("[OK] Toutes les categories Milvus sont deja ingerees. Rien a faire.")
        return

    # 4. Ecriture du fichier global
    os.makedirs(RUBRIQUES_DIR, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(f"# Categories manquantes a ingerer (Milvus - batch1 - batch2)\n")
        f.write(f"# Genere : {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"# Total : {len(missing)} categories\n\n")
        for c in sorted(missing):
            f.write(c + "\n")
    print(f"[OK] Fichier ecrit : {OUTPUT_FILE}")

    # 5. Split en chunks
    chunks = split_into_chunks(missing, CHUNK_SIZE)
    print(f"\n[INFO] Decoupage en {len(chunks)} chunks de {CHUNK_SIZE} categories")

    for i, chunk in enumerate(chunks, 1):
        chunk_file = os.path.join(
            RUBRIQUES_DIR,
            f"categories_missing_chunk_{i:03d}_of_{len(chunks):03d}.txt"
        )
        with open(chunk_file, "w", encoding="utf-8") as f:
            f.write(f"# Chunk {i}/{len(chunks)} - {len(chunk)} categories\n\n")
            for c in chunk:
                f.write(c + "\n")
        print(f"  - {chunk_file} ({len(chunk)} cat.)")

    print(f"\n[NEXT STEPS]")
    print(f"  Lancer un chunk a la fois avec ingest_by_categories.py :")
    print(f"")
    print(f"  export CATEGORIES_FILE={RUBRIQUES_DIR}/categories_missing_chunk_001_of_{len(chunks):03d}.txt")
    print(f"  export TS_COLLECTION=produits_prod   # collection prod")
    print(f"  python3 ingest_by_categories.py")
    print(f"")
    print(f"  Une fois le chunk 001 termine, passer au 002, etc.")


if __name__ == "__main__":
    main()
