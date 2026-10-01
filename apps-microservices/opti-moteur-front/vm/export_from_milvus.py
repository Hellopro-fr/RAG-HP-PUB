#!/usr/bin/env python3
"""
Export 200k produits uniques (tous leurs chunks) depuis Milvus produits_3 -> JSONL
pour ingestion dans Typesense.

Phase 1: recupere 200k id_produit uniques (chunk_number == 0, actif, visible)
Phase 2: pour chaque batch de 500 id_produit, fetch TOUS les chunks (avec embedding)
         et ecrit en JSONL une ligne par chunk.

Usage:
    python3 export_from_milvus.py
    # ou
    TARGET_UNIQUE=50000 OUTPUT=data/subset.jsonl python3 export_from_milvus.py
"""

import json
import os
import sys
from pymilvus import connections, Collection, utility
from tqdm import tqdm

# =============================================================================
# CONFIG
# =============================================================================
MILVUS_HOST = os.getenv("MILVUS_HOST", "milvus-prod.hello.dev.private.com")
MILVUS_PORT = os.getenv("MILVUS_PORT", "19530")
MILVUS_USER = os.getenv("MILVUS_USER", "")
MILVUS_PASSWORD = os.getenv("MILVUS_PASSWORD", "")
MILVUS_TOKEN = os.getenv("MILVUS_TOKEN", "")
MILVUS_DB = os.getenv("MILVUS_DB", "default")
COLLECTION_NAME = os.getenv("MILVUS_COLLECTION", "produits_3")
CONNECTION_ALIAS = "default"

TARGET_UNIQUE_PRODUCTS = int(os.getenv("TARGET_UNIQUE", "200000"))
OUTPUT_FILE = os.getenv("OUTPUT", "data/products_200k.jsonl")

# Filtre Phase 1 : 1er chunk de chaque produit, vendeurs actifs (Client+Prospect)
# Les etats possibles sont: Client, Pause, Prospect
# Les affichages possibles sont: Complet, Decouverte, Restreint
PHASE1_FILTER = os.getenv(
    "PHASE1_FILTER",
    'chunk_number == 1 and etat in ["Client", "Prospect"]',
)

# Champs a recuperer en Phase 2 (avec embedding)
PHASE2_FIELDS = [
    "id_produit", "nom_produit", "text", "categorie", "id_categorie",
    "fournisseur", "id_fournisseur", "marque", "fabricant",
    "chunk_number", "total_chunks", "embedding",
]

BATCH_IDS = 500  # nombre d'id_produit par requete Milvus en Phase 2


# =============================================================================
# SCRIPT
# =============================================================================
def connect():
    print(f"[INFO] Connexion Milvus {MILVUS_HOST}:{MILVUS_PORT} (db={MILVUS_DB})")
    kwargs = {"alias": CONNECTION_ALIAS, "host": MILVUS_HOST, "port": MILVUS_PORT, "db_name": MILVUS_DB}
    if MILVUS_TOKEN:
        kwargs["token"] = MILVUS_TOKEN
        print(f"[INFO] Auth via TOKEN")
    elif MILVUS_USER:
        kwargs["user"] = MILVUS_USER
        kwargs["password"] = MILVUS_PASSWORD
        print(f"[INFO] Auth via user='{MILVUS_USER}'")
    else:
        print("[WARN] Pas d'auth fournie. Si la collection en exige, l'appel va echouer.")
    connections.connect(**kwargs)
    if not utility.has_collection(COLLECTION_NAME, using=CONNECTION_ALIAS):
        print(f"[ERREUR] Collection '{COLLECTION_NAME}' introuvable")
        sys.exit(1)
    col = Collection(COLLECTION_NAME)
    print(f"[INFO] Chargement de '{COLLECTION_NAME}' en memoire...")
    col.load()
    print(f"[OK] Collection chargee ({col.num_entities} entites totales)")
    return col


def phase1_collect_product_ids(col):
    """Phase 1 : collecte jusqu'a TARGET_UNIQUE_PRODUCTS id_produit uniques."""
    print(f"\n[PHASE 1] Collecte de {TARGET_UNIQUE_PRODUCTS} id_produit uniques")
    print(f"          Filtre: {PHASE1_FILTER}")

    ids_seen = set()
    try:
        iterator = col.query_iterator(
            expr=PHASE1_FILTER,
            output_fields=["id_produit"],
            batch_size=5000,
            limit=TARGET_UNIQUE_PRODUCTS * 2,  # marge pour doublons
        )
    except Exception as e:
        print(f"[ERREUR] query_iterator : {e}")
        print("         Essayez avec pymilvus >= 2.3")
        sys.exit(1)

    with tqdm(total=TARGET_UNIQUE_PRODUCTS, desc="IDs uniques") as pbar:
        while len(ids_seen) < TARGET_UNIQUE_PRODUCTS:
            try:
                batch = iterator.next()
            except StopIteration:
                break
            if not batch:
                break
            for row in batch:
                pid = row.get("id_produit")
                if pid and pid not in ids_seen:
                    ids_seen.add(pid)
                    pbar.update(1)
                    if len(ids_seen) >= TARGET_UNIQUE_PRODUCTS:
                        break
    try:
        iterator.close()
    except Exception:
        pass

    ids_list = list(ids_seen)
    print(f"[OK] {len(ids_list)} id_produit uniques collectes")
    return ids_list


def phase2_export_all_chunks(col, product_ids, output_path):
    """Phase 2 : export TOUS les chunks de chaque id_produit en JSONL."""
    print(f"\n[PHASE 2] Export des chunks (avec embedding) -> {output_path}")
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    total_chunks = 0
    total_batches = (len(product_ids) + BATCH_IDS - 1) // BATCH_IDS

    with open(output_path, "w", encoding="utf-8") as fout:
        with tqdm(total=len(product_ids), desc="Produits") as pbar:
            for i in range(0, len(product_ids), BATCH_IDS):
                batch_ids = product_ids[i:i + BATCH_IDS]
                # Escape any quotes in ids (shouldn't happen mais au cas ou)
                ids_quoted = ",".join(f'"{pid}"' for pid in batch_ids)
                expr = f'id_produit in [{ids_quoted}]'
                try:
                    rows = col.query(
                        expr=expr,
                        output_fields=PHASE2_FIELDS,
                        limit=16384,
                    )
                except Exception as e:
                    print(f"[WARN] Batch {i}: {e}")
                    pbar.update(len(batch_ids))
                    continue

                for row in rows:
                    doc = {
                        "id": f"{row['id_produit']}_{int(row.get('chunk_number', 0) or 0)}",
                        "id_produit": str(row.get("id_produit", "")),
                        "nom_produit": (row.get("nom_produit") or "")[:500],
                        "text": (row.get("text") or "")[:2000],
                        "categorie": row.get("categorie") or "",
                        "id_categorie": str(row.get("id_categorie") or ""),
                        "fournisseur": row.get("fournisseur") or "",
                        "marque": row.get("marque") or "",
                        "fabricant": row.get("fabricant") or "",
                        "chunk_number": int(row.get("chunk_number", 0) or 0),
                        "total_chunks": int(row.get("total_chunks", 1) or 1),
                        "embedding": list(row["embedding"]),
                    }
                    fout.write(json.dumps(doc, ensure_ascii=False) + "\n")
                    total_chunks += 1

                pbar.update(len(batch_ids))

    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    print(f"[OK] {total_chunks} chunks exportes dans {output_path} ({size_mb:.1f} MB)")
    return total_chunks


def main():
    col = connect()
    try:
        ids = phase1_collect_product_ids(col)
        if not ids:
            print("[ERREUR] Aucun id_produit collecte. Verifiez le filtre Phase 1.")
            sys.exit(1)
        phase2_export_all_chunks(col, ids, OUTPUT_FILE)
        print(f"\n[DONE] Export termine. Fichier : {OUTPUT_FILE}")
        print(f"       -> Prochaine etape : python3 ingest_typesense.py")
    finally:
        try:
            col.release()
        except Exception:
            pass
        connections.disconnect(CONNECTION_ALIAS)
        print("[INFO] Deconnecte de Milvus")


if __name__ == "__main__":
    main()
