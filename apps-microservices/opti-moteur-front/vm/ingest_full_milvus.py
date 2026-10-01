#!/usr/bin/env python3
"""
ingest_full_milvus.py
======================
Ingestion COMPLÈTE de tous les produits Milvus -> Typesense `produits_prod`.

Différence vs ingest_by_categories.py :
  - Pas besoin de fournir la liste de catégories
  - Itère sur TOUS les produits Milvus sans filtre catégorie
  - Cible produits_prod par défaut (collection prod)

Usage :
    cd /home/devhp/RAG-HP-PUB/apps-microservices/opti-moteur-front

    # Charger les creds depuis le .env du service
    export $(grep -E '^(ZILLIZ_|MILVUS_|TYPESENSE_)' .env | xargs)

    # Renommer pour matcher les noms attendus
    export MILVUS_HOST="$ZILLIZ_URI"
    export MILVUS_PORT="$ZILLIZ_PORT"
    export MILVUS_USER="$ZILLIZ_USER"
    export MILVUS_PASSWORD="$ZILLIZ_PASSWORD"
    export MILVUS_COLLECTION="produits_3"
    export TS_HOST="localhost"
    export TS_PORT="8108"
    export TS_API_KEY="hp_poc_2026"
    export TS_COLLECTION="produits_prod"   # IMPORTANT : cibler la collection prod

    # Lancer (estimation : 2-4h selon volume Milvus, ~2.6M chunks)
    cd vm
    nohup python3 -u ingest_full_milvus.py > /tmp/ingest_full.log 2>&1 &
    echo "PID: $!"

    # Monitoring
    tail -f /tmp/ingest_full.log
    curl -s -H "X-TYPESENSE-API-KEY: hp_poc_2026" \\
      http://localhost:8108/collections/produits_prod \\
      | python3 -c 'import sys,json; print("docs:", json.load(sys.stdin)["num_documents"])'

Reprise après interruption :
    Re-lancer la même commande. L'upsert dédoublonne sur `id`.
"""
import json
import os
import shutil
import sys
import time
import requests
import typesense
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
TS_COLLECTION = os.getenv("TS_COLLECTION", "produits_prod")  # PROD par défaut

TS_BATCH = int(os.getenv("TS_BATCH", "1000"))
DISK_THRESHOLD_GB = float(os.getenv("DISK_THRESHOLD_GB", "3.0"))

# Filtre optionnel (laisse vide pour tout prendre)
EXTRA_FILTER = os.getenv("EXTRA_FILTER", "")

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


# ========== HELPERS ==========
def disk_free_gb(path="/"):
    return shutil.disk_usage(path).free / (1024**3)


def ts_doc_count(collection):
    try:
        r = requests.get(
            f"http://{TS_HOST}:{TS_PORT}/collections/{collection}",
            headers={"X-TYPESENSE-API-KEY": TS_KEY}, timeout=5,
        )
        return r.json().get("num_documents", 0)
    except Exception:
        return 0


def parse_price(v):
    if not v: return None
    try:
        return float(str(v).replace(",", ".").replace(" ", "").replace(" ", ""))
    except (ValueError, TypeError):
        return None


def row_to_doc(row):
    doc = {
        "id":              f"{row['id_produit']}_{int(row.get('chunk_number', 0) or 0)}",
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
def main():
    if not MILVUS_HOST:
        print("[ERREUR] MILVUS_HOST manquant"); sys.exit(1)

    print(f"[INFO] Milvus      : {MILVUS_HOST}:{MILVUS_PORT}")
    print(f"[INFO] Source      : {MILVUS_COLLECTION}")
    print(f"[INFO] Typesense   : {TS_HOST}:{TS_PORT}")
    print(f"[INFO] Cible coll. : {TS_COLLECTION}")
    print(f"[INFO] EXTRA_FILTER: {EXTRA_FILTER!r}")

    # Health checks
    try:
        h = requests.get(f"http://{TS_HOST}:{TS_PORT}/health", timeout=5).json()
        print(f"[OK] Typesense health: {h}")
    except Exception as e:
        print(f"[ERREUR] Typesense unreachable: {e}"); sys.exit(1)

    docs0 = ts_doc_count(TS_COLLECTION)
    if docs0 == 0:
        print(f"[WARN] Collection '{TS_COLLECTION}' vide ou inexistante. La creer d'abord ?")
        print(f"       Voir scripts/ingest_by_categories.py qui cree la collection si absente.")
        ans = input("Continuer quand meme ? (o/N) ").strip().lower()
        if ans not in ("o", "oui", "y", "yes"):
            sys.exit(1)

    # Connexion Milvus
    print(f"[INFO] Connexion Milvus...")
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
    n_total = col.num_entities
    print(f"[OK] Milvus '{MILVUS_COLLECTION}' chargee : {n_total} entities")

    try:
        disk0 = disk_free_gb("/")
        print(f"[BASELINE] Disque libre: {disk0:.1f} GB | Docs Typesense: {docs0}")
        print("=" * 90)

        global_start = time.time()
        global_chunks = 0
        global_ok = 0
        global_err = 0

        # Iteration TOUT Milvus (avec filter optionnel)
        # Le query_iterator pagine automatiquement par batch de 500
        expr = EXTRA_FILTER if EXTRA_FILTER else ""

        try:
            iterator = col.query_iterator(
                expr=expr if expr else None,
                output_fields=FIELDS,
                batch_size=500,
            )
        except Exception as e:
            print(f"[ERREUR] query_iterator failed: {e}")
            sys.exit(1)

        ts_buffer = []
        last_print = time.time()

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
                    global_err += 1
                    continue
                ts_buffer.append(json.dumps(doc, ensure_ascii=False))
                global_chunks += 1
                if len(ts_buffer) >= TS_BATCH:
                    ok, err = ts_flush(ts_buffer)
                    global_ok += ok
                    global_err += err
                    ts_buffer = []

            # Print progress every 30s
            now = time.time()
            if now - last_print > 30:
                last_print = now
                disk_now = disk_free_gb("/")
                docs_now = ts_doc_count(TS_COLLECTION)
                elapsed = now - global_start
                rate = global_ok / max(elapsed, 1)
                eta_min = (n_total - global_chunks) / max(rate, 1) / 60
                print(f"  [{elapsed/60:5.1f}min] chunks={global_chunks:>7} "
                      f"ok={global_ok:>7} err={global_err:>4} "
                      f"rate={rate:>4.0f} docs/s | TS={docs_now:>7} "
                      f"disk={disk_now:>5.1f}GB | ETA {eta_min:.0f}min")

                # Garde-fou disque
                if disk_now < DISK_THRESHOLD_GB:
                    print(f"\n[STOP] Disque < {DISK_THRESHOLD_GB} GB, arret preventif.")
                    break

        # Flush final
        if ts_buffer:
            ok, err = ts_flush(ts_buffer)
            global_ok += ok
            global_err += err

        try:
            iterator.close()
        except Exception:
            pass

        # Resume
        elapsed = time.time() - global_start
        disk_final = disk_free_gb("/")
        docs_final = ts_doc_count(TS_COLLECTION)
        print("\n" + "=" * 90)
        print(f"[DONE] {global_ok} chunks ingeres en {elapsed/60:.1f} min ({global_err} erreurs)")
        print(f"       Debit  : {global_ok/max(elapsed,1):.0f} docs/s")
        print(f"       Docs TS: {docs0} -> {docs_final} (+{docs_final-docs0})")
        print(f"       Disque : {disk0:.1f} -> {disk_final:.1f} GB (-{disk0-disk_final:.2f})")

    finally:
        col.release()
        connections.disconnect("default")


if __name__ == "__main__":
    main()
