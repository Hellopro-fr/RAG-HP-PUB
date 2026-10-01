"""
POC Typesense — Ingestion avec embeddings CamemBERT 1024 (identique Milvus prod)

Charge les 42 produits HelloPro + leurs embeddings CamemBERT pre-calcules via MCP,
cree la collection Typesense avec num_dim=1024, et ingeste en batch.
"""

import json
import os
import sys
import time
import requests
import typesense
from poc_typesense import PRODUCTS  # 42 produits metadata

# ============================================================
# CONFIG
# ============================================================
TYPESENSE_HOST = "localhost"
TYPESENSE_PORT = "8108"
TYPESENSE_API_KEY = "hp_poc_2026"
COLLECTION_NAME = "produits_hellopro_cam"
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

client = typesense.Client({
    "api_key": TYPESENSE_API_KEY,
    "nodes": [{"host": TYPESENSE_HOST, "port": TYPESENSE_PORT, "protocol": "http"}],
    "connection_timeout_seconds": 10,
})


def load_embeddings():
    """Charge les 3 batches d'embeddings dans l'ordre."""
    all_emb = []
    for fname in ("embeddings_batch1.json", "embeddings_batch2.json", "embeddings_batch3.json"):
        fpath = os.path.join(DATA_DIR, fname)
        with open(fpath, "r", encoding="utf-8") as f:
            batch = json.load(f)
        all_emb.extend(batch)
        print(f"  [OK] {fname}: {len(batch)} embeddings charges")
    return all_emb


def create_collection():
    """Schema Typesense avec vecteur 1024 pre-calcule (pas d'auto-embedding)."""
    schema = {
        "name": COLLECTION_NAME,
        "fields": [
            {"name": "nom", "type": "string"},
            {"name": "rubrique", "type": "string", "facet": True},
            {"name": "categorie_id", "type": "string", "facet": True},
            {"name": "description", "type": "string"},
            {"name": "fournisseur", "type": "string", "facet": True, "optional": True},
            {"name": "texte_complet", "type": "string"},
            # Vecteur 1024 dimensions pre-calcule (CamemBERT-large)
            {"name": "embedding", "type": "float[]", "num_dim": 1024},
        ],
        "token_separators": ["-", "/"],
    }

    try:
        client.collections[COLLECTION_NAME].delete()
        print(f"[INFO] Collection existante '{COLLECTION_NAME}' supprimee")
    except Exception:
        pass

    client.collections.create(schema)
    print(f"[OK] Collection '{COLLECTION_NAME}' creee (num_dim=1024, CamemBERT)")


def ingest():
    embeddings = load_embeddings()

    if len(embeddings) != len(PRODUCTS):
        print(f"[ERREUR] Mismatch: {len(PRODUCTS)} produits vs {len(embeddings)} embeddings")
        print(f"         PRODUCTS attend 42 produits (16 armoire med + 3 pharma + 4 secu + 3 refrig + 3 precision + 13 bruit)")
        sys.exit(1)

    docs = []
    for i, (prod, emb) in enumerate(zip(PRODUCTS, embeddings)):
        texte = f"{prod['nom']}. {prod['rubrique']}. {prod['description']}"
        # Verif optionnelle: le text envoye au MCP doit correspondre
        if emb["text"][:50] != texte[:50]:
            print(f"  [WARN] #{i} text mismatch: '{emb['text'][:50]}' vs '{texte[:50]}'")
        docs.append({
            "id": prod["id"],
            "nom": prod["nom"],
            "rubrique": prod["rubrique"],
            "categorie_id": prod["categorie_id"],
            "description": prod["description"],
            "fournisseur": prod.get("fournisseur") or "",
            "texte_complet": texte,
            "embedding": emb["vector"],
        })

    print(f"\n[INFO] Ingestion de {len(docs)} produits...")
    start = time.time()
    jsonl = "\n".join(json.dumps(d, ensure_ascii=False) for d in docs)
    result = client.collections[COLLECTION_NAME].documents.import_(jsonl, {"action": "upsert"})
    elapsed = time.time() - start

    # Check result
    n_ok = result.count("\"success\":true")
    n_err = result.count("\"success\":false")
    print(f"[OK] {n_ok} ingeres en {elapsed:.2f}s ({n_err} erreurs)")
    if n_err:
        print("     Premieres erreurs:")
        for line in result.split("\n")[:3]:
            if "false" in line:
                print(f"     {line}")


def main():
    print("=" * 70)
    print("  POC Typesense - Ingestion CamemBERT 1024")
    print("=" * 70)

    # Healthcheck (HTTP direct, compatible client 0.21)
    try:
        r = requests.get(f"http://{TYPESENSE_HOST}:{TYPESENSE_PORT}/health", timeout=3)
        r.raise_for_status()
        print(f"[OK] Typesense healthy: {r.json()}")
    except Exception as e:
        print(f"[ERREUR] Typesense injoignable sur http://{TYPESENSE_HOST}:{TYPESENSE_PORT}")
        print(f"        {e}")
        print("        Lance: docker compose up -d")
        sys.exit(1)

    create_collection()
    ingest()

    count = client.collections[COLLECTION_NAME].retrieve()["num_documents"]
    print(f"\n[OK] Collection prete: {count} documents indexes")
    print(f"     -> python search_camembert.py pour lancer le benchmark")


if __name__ == "__main__":
    main()
