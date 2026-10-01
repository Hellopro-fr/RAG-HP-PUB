#!/usr/bin/env python3
"""
Ingestion Milvus -> Typesense PAR CATEGORIE, UNE CATEGORIE A LA FOIS.

Avantages :
  - Monitoring progressif (docs/disk apres chaque categorie)
  - Peut s'arreter a n'importe quel moment si espace disque faible
  - Reprise : si on ingere les memes categories, upsert dedoublonne
  - Reprise intelligente via --skip-existing (verifie dans Typesense)

Usage :
  # Liste en ligne
  CATEGORIES='Armoire medicale,Pompe hydraulique,Batterie industrielle' \\
      python3 ingest_by_categories.py

  # Depuis un fichier (une categorie par ligne)
  CATEGORIES_FILE=mes_categories.txt python3 ingest_by_categories.py

  # Filtre etat supplementaire (par defaut : tous les etats)
  EXTRA_FILTER='etat in ["Client","Pause","Prospect"] and affichage == "Complet"' \\
      CATEGORIES_FILE=... python3 ingest_by_categories.py
"""
import json
import os
import shutil
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

CATEGORIES_FILE = os.getenv("CATEGORIES_FILE")
CATEGORIES_INLINE = os.getenv("CATEGORIES", "")

# Filtre etat/affichage optionnel (en + de la categorie)
# Laisse vide pour tout prendre. Exemples :
#   EXTRA_FILTER='etat in ["Client","Pause","Prospect"]'
#   EXTRA_FILTER='etat == "Client" or (etat == "Pause" and affichage == "Complet")'
EXTRA_FILTER = os.getenv("EXTRA_FILTER", "")

# Fetch chunk_number==1 pour avoir un produit unique, ou tous les chunks
# (1 = ne prend que le premier chunk de chaque produit)
# (None/vide = tous les chunks)
CHUNK_FILTER = os.getenv("CHUNK_FILTER", "")  # ex: "chunk_number == 1"

TS_BATCH = int(os.getenv("TS_BATCH", "1000"))
# Nombre max de categories dans un `in [...]` si on veut les grouper
CATEGORIES_PER_QUERY = int(os.getenv("CATEGORIES_PER_QUERY", "1"))

FIELDS = [
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

# Skip existing docs via upsert idempotent (Typesense le gere natif).
# Pour verifier, on peut checker la collection apres chaque categorie.
SKIP_EXISTING = os.getenv("SKIP_EXISTING", "0") == "1"


ts_client = typesense.Client({
    "api_key": TS_KEY,
    "nodes": [{"host": TS_HOST, "port": TS_PORT, "protocol": "http"}],
    "connection_timeout_seconds": 300,
})


# ========== HELPERS ==========
def disk_free_gb(path="/"):
    usage = shutil.disk_usage(path)
    return usage.free / (1024**3)


def ts_doc_count(collection):
    try:
        r = requests.get(
            f"http://{TS_HOST}:{TS_PORT}/collections/{collection}",
            headers={"X-TYPESENSE-API-KEY": TS_KEY}, timeout=5,
        )
        return r.json().get("num_documents", 0)
    except Exception:
        return 0


def ts_collection_exists(collection):
    try:
        requests.get(
            f"http://{TS_HOST}:{TS_PORT}/collections/{collection}",
            headers={"X-TYPESENSE-API-KEY": TS_KEY}, timeout=5,
        ).raise_for_status()
        return True
    except Exception:
        return False


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
    ts_client.collections.create(schema)
    print(f"[OK] Collection '{TS_COLLECTION}' creee")


def parse_price(v):
    if not v: return None
    try:
        return float(str(v).replace(",", ".").replace(" ", "").replace("\u00a0", ""))
    except (ValueError, TypeError):
        return None


def row_to_doc(row):
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
    ph = parse_price(row.get("prix_ht"))
    if ph is not None: doc["prix_ht"] = ph
    pt = parse_price(row.get("prix_ttc"))
    if pt is not None: doc["prix_ttc"] = pt
    return doc


def ts_flush(jsonl_batch):
    """
    Raw HTTP POST avec encodage UTF-8 explicite.
    Contourne un bug du client typesense-python 0.21.0 qui utilise latin-1
    et fait planter les produits contenant ', EUR, bullet, TM, oe, etc.
    """
    if not jsonl_batch:
        return 0, 0
    body = "\n".join(jsonl_batch).encode("utf-8")
    url = f"http://{TS_HOST}:{TS_PORT}/collections/{TS_COLLECTION}/documents/import?action=upsert"
    try:
        r = requests.post(
            url,
            headers={
                "X-TYPESENSE-API-KEY": TS_KEY,
                "Content-Type": "text/plain; charset=utf-8",
            },
            data=body,
            timeout=300,
        )
        r.raise_for_status()
        text = r.text
    except Exception as e:
        print(f"\n[WARN] flush error: {e}", file=sys.stderr)
        return 0, len(jsonl_batch)
    ok = text.count('"success":true')
    err = text.count('"success":false')
    return ok, err


# ========== MAIN ==========
def load_categories():
    if CATEGORIES_FILE:
        with open(CATEGORIES_FILE, "r", encoding="utf-8") as f:
            cats = [line.strip() for line in f if line.strip() and not line.startswith("#")]
    elif CATEGORIES_INLINE:
        cats = [c.strip() for c in CATEGORIES_INLINE.split(",") if c.strip()]
    else:
        print("[ERREUR] Aucune categorie fournie. Utilise CATEGORIES='...' ou CATEGORIES_FILE=...")
        sys.exit(1)
    # dedupe en preservant l'ordre
    seen = set()
    out = []
    for c in cats:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


def milvus_connect():
    if not MILVUS_HOST:
        print("[ERREUR] MILVUS_HOST manquant"); sys.exit(1)
    print(f"[INFO] Milvus {MILVUS_HOST}:{MILVUS_PORT}")
    kwargs = {"alias": "default", "host": MILVUS_HOST, "port": MILVUS_PORT}
    if MILVUS_USER:
        kwargs["user"] = MILVUS_USER
        kwargs["password"] = MILVUS_PASSWORD
    connections.connect(**kwargs)
    if not utility.has_collection(MILVUS_COLLECTION):
        print(f"[ERREUR] Collection '{MILVUS_COLLECTION}' introuvable"); sys.exit(1)
    col = Collection(MILVUS_COLLECTION)
    col.load()
    print(f"[OK] Milvus '{MILVUS_COLLECTION}' loaded ({col.num_entities} entities)")
    return col


def build_expr(categories_subset):
    """Construit l'expression Milvus pour une liste de categories."""
    cats_quoted = ",".join(f'"{c}"' for c in categories_subset)
    expr = f'categorie in [{cats_quoted}]'
    if CHUNK_FILTER:
        expr += f' and {CHUNK_FILTER}'
    if EXTRA_FILTER:
        expr += f' and ({EXTRA_FILTER})'
    return expr


def ingest_category_batch(col, categories_subset, pbar_cats):
    """
    Ingeste les produits d'un batch de categories.
    Utilise query_iterator pour paginer automatiquement.
    """
    expr = build_expr(categories_subset)
    total_chunks = 0
    total_ok = 0
    total_err = 0
    ts_buffer = []
    start = time.time()

    try:
        iterator = col.query_iterator(
            expr=expr,
            output_fields=FIELDS,
            batch_size=500,
        )
    except Exception as e:
        print(f"\n[ERREUR] query_iterator failed for expr={expr[:100]}...: {e}")
        return 0, 0, 0

    while True:
        try:
            batch = iterator.next()
        except StopIteration:
            break
        if not batch:
            break
        for row in batch:
            try:
                doc = row_to_doc(row)
            except Exception as e:
                print(f"\n[WARN] row_to_doc error: {e}")
                total_err += 1
                continue
            ts_buffer.append(json.dumps(doc, ensure_ascii=False))
            total_chunks += 1
            if len(ts_buffer) >= TS_BATCH:
                ok, err = ts_flush(ts_buffer)
                total_ok += ok
                total_err += err
                ts_buffer = []

    if ts_buffer:
        ok, err = ts_flush(ts_buffer)
        total_ok += ok
        total_err += err
    try:
        iterator.close()
    except Exception:
        pass

    elapsed = time.time() - start
    return total_chunks, total_ok, total_err


def main():
    categories = load_categories()
    print(f"[OK] {len(categories)} categories a traiter")
    print(f"[INFO] EXTRA_FILTER = {EXTRA_FILTER!r}")
    print(f"[INFO] CHUNK_FILTER = {CHUNK_FILTER!r}")

    # Typesense
    try:
        h = requests.get(f"http://{TS_HOST}:{TS_PORT}/health", timeout=5).json()
        print(f"[OK] Typesense: {h}")
    except Exception as e:
        print(f"[ERREUR] Typesense: {e}"); sys.exit(1)

    if not ts_collection_exists(TS_COLLECTION):
        ts_create_collection()
    else:
        n = ts_doc_count(TS_COLLECTION)
        print(f"[INFO] Collection '{TS_COLLECTION}' existe deja : {n} docs (upsert)")

    # Milvus
    col = milvus_connect()

    try:
        # Etat initial
        disk0 = disk_free_gb("/")
        docs0 = ts_doc_count(TS_COLLECTION)
        print(f"\n[BASELINE] Disque libre: {disk0:.1f} GB | Docs Typesense: {docs0}")
        print("="*90)

        global_start = time.time()
        global_chunks = 0
        global_ok = 0
        global_err = 0

        # On processe par groupes de CATEGORIES_PER_QUERY (default 1 pour monitoring fin)
        for i in range(0, len(categories), CATEGORIES_PER_QUERY):
            batch = categories[i:i + CATEGORIES_PER_QUERY]
            label = batch[0] if len(batch) == 1 else f"{len(batch)} categories"
            t0 = time.time()
            chunks, ok, err = ingest_category_batch(col, batch, None)
            dt = time.time() - t0

            disk_now = disk_free_gb("/")
            docs_now = ts_doc_count(TS_COLLECTION)
            delta_disk = disk0 - disk_now
            delta_docs = docs_now - docs0

            global_chunks += chunks
            global_ok += ok
            global_err += err

            print(f"[{i+1:>4}/{len(categories)}] {label[:50]:50s}  "
                  f"chunks={chunks:>5}  ok={ok:>5}  err={err:>3}  "
                  f"{dt:>5.1f}s  |  TS={docs_now:>7}(+{delta_docs:>6})  "
                  f"disk={disk_now:>5.1f}GB(-{delta_disk:>5.2f})")

            # Garde-fou : si disque < 3 GB, stop
            if disk_now < 3.0:
                print(f"\n[STOP] Disque < 3 GB (= {disk_now:.1f} GB), arret preventif.")
                break

        # Resume
        elapsed = time.time() - global_start
        disk_final = disk_free_gb("/")
        docs_final = ts_doc_count(TS_COLLECTION)
        print("\n" + "="*90)
        print(f"[DONE] {global_ok} chunks ingeres en {elapsed/60:.1f} min ({global_err} erreurs)")
        print(f"       Debit : {global_ok/max(elapsed,1):.0f} docs/s")
        print(f"       Docs Typesense : {docs0} -> {docs_final} (+{docs_final-docs0})")
        print(f"       Disque libre   : {disk0:.1f} -> {disk_final:.1f} GB (-{disk0-disk_final:.2f})")

    finally:
        col.release()
        connections.disconnect("default")


if __name__ == "__main__":
    main()
