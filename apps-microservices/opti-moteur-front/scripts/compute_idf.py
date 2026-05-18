#!/usr/bin/env python3
"""
compute_idf.py
==============
Calcule l'IDF (Inverse Document Frequency) des tokens dans `nom_produit` pour
la collection Typesense, et serialise le dict en JSON pour usage par le
reranker (`app/services/idf_loader.py`).

Pourquoi :
  Le reranker compte historiquement les tokens query matches dans nom_produit
  avec un poids uniforme. Pour des queries combinatoires comme
  "melangeur conique", le token rare ("conique") devrait peser plus que le
  token commun ("melangeur") -- d'ou la ponderation IDF.

Usage RECOMMANDE -- dans le container Docker (deps deja la) :
  cd apps-microservices/opti-moteur-front
  docker compose exec opti-moteur-front python scripts/compute_idf.py
  docker compose restart opti-moteur-front

Usage alternatif -- depuis l'hote (besoin python3 + requirements.txt) :
  cd apps-microservices/opti-moteur-front
  python3 scripts/compute_idf.py

  # Options
  python3 scripts/compute_idf.py --collection produits_scale
  python3 scripts/compute_idf.py --limit 50000  # echantillon (test rapide)

Le fichier de sortie (`app/data/idf_nom_produit.json`) est gitignore (depend
du catalogue live). Le bind-mount docker-compose `./app/data:/app/app/data`
garantit que le fichier ecrit dans le container apparait cote hote, et vice-
versa.

Couts :
  Export ~700k docs Typesense (champ nom_produit only) : ~10-30s + ~50-200 MB RAM.
  Calcul IDF : ~5s. JSON final : ~1-5 MB (selon vocab).
"""
import argparse
import json
import logging
import math
import re
import sys
import time
import unicodedata
from collections import Counter
from pathlib import Path

# Permet de lancer le script depuis la racine du service
_SCRIPT_DIR = Path(__file__).resolve().parent
_APP_DIR = _SCRIPT_DIR.parent
sys.path.insert(0, str(_APP_DIR))

from app.core.credentials import settings  # noqa: E402
from app.core.typesense_client import typesense_client  # noqa: E402


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("compute_idf")


# ---------------------------------------------------------------------------
# Tokenizer : strict reflexion de app/utils/text.py (a maintenir aligne).
# On ne reutilise pas directement pour ne pas tirer l'app dans le script si
# l'arborescence change a l'avenir.
# ---------------------------------------------------------------------------
def normalize(s: str) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFD", s)
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower()


def tokenize(s: str):
    return set(re.findall(r"[a-z0-9]{2,}", normalize(s)))


# ---------------------------------------------------------------------------
# Export des nom_produit depuis Typesense
# ---------------------------------------------------------------------------
def iter_nom_produits(collection: str, limit: int = 0):
    """
    Streame les nom_produit via /documents/export (JSONL).

    `limit` = 0 -> export complet. Sinon : tronque (utile pour test).

    Note : Typesense renvoie 1 ligne JSON par document. Pour 700k docs c'est
    ~50-200 MB de string en RAM -- acceptable. Si on doit traiter 10M+ docs,
    refactoriser en streaming HTTP (requests.get stream=True + iter_lines).
    """
    t0 = time.time()
    logger.info("Exporting documents from Typesense collection=%s ...", collection)
    coll = typesense_client.client.collections[collection]
    raw = coll.documents.export({"include_fields": "nom_produit"})
    dt = time.time() - t0
    n_lines = raw.count("\n") + 1 if raw else 0
    logger.info("Export terminated in %.1fs (~%d lines, %.1f MB)", dt, n_lines, len(raw) / (1024 * 1024))

    n = 0
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            doc = json.loads(line)
        except json.JSONDecodeError:
            continue
        nom = doc.get("nom_produit") or ""
        if not nom:
            continue
        yield nom
        n += 1
        if limit and n >= limit:
            logger.info("Limit %d reached, stopping export", limit)
            break


# ---------------------------------------------------------------------------
# Calcul IDF lisse
# ---------------------------------------------------------------------------
def compute_idf(collection: str, limit: int = 0) -> dict:
    """
    Retourne :
      {
        "n_docs": int,
        "n_tokens": int,
        "median": float,
        "idf": {token: float, ...}
      }

    Formule : idf(t) = log((N + 1) / (df(t) + 1)) + 1
      - lisse pour eviter idf=0 ou inf
      - >= 1 pour tous les tokens (le +1 final garantit qu'un token tres
        frequent ait quand meme un poids non-nul, sinon le ratio name_match
        deviendrait degenere).
    """
    df = Counter()
    n_docs = 0
    t0 = time.time()
    last_log = t0

    for nom in iter_nom_produits(collection, limit=limit):
        n_docs += 1
        for tok in tokenize(nom):
            df[tok] += 1

        # Heartbeat toutes les 5s
        if time.time() - last_log > 5:
            logger.info("Processed %d docs, %d unique tokens so far", n_docs, len(df))
            last_log = time.time()

    if n_docs == 0:
        raise RuntimeError(f"No documents extracted from collection '{collection}' "
                           "- verifier la connectivite Typesense et le nom de la collection")

    logger.info("Tokenization done in %.1fs : %d docs, %d unique tokens",
                time.time() - t0, n_docs, len(df))

    # IDF lisse
    idf = {}
    for tok, freq in df.items():
        idf[tok] = math.log((n_docs + 1) / (freq + 1)) + 1.0

    # Mediane (utilisee comme fallback pour tokens inconnus a runtime)
    vals = sorted(idf.values())
    median = vals[len(vals) // 2] if vals else 1.0

    # Statistiques rapides (pour sanity check post-generation)
    min_idf = min(vals) if vals else 0.0
    max_idf = max(vals) if vals else 0.0
    logger.info("IDF stats : min=%.3f  median=%.3f  max=%.3f", min_idf, median, max_idf)

    return {
        "n_docs": n_docs,
        "n_tokens": len(idf),
        "median": median,
        "idf": idf,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Calcule l'IDF des tokens nom_produit pour le reranker")
    parser.add_argument(
        "--collection", default=settings.TYPESENSE_COLLECTION,
        help=f"Collection Typesense source (default: {settings.TYPESENSE_COLLECTION})",
    )
    parser.add_argument(
        "--out", default=str(_APP_DIR / "app" / "data" / "idf_nom_produit.json"),
        help="Chemin du fichier JSON de sortie",
    )
    parser.add_argument(
        "--limit", type=int, default=0,
        help="Limite le nombre de docs traites (0 = aucun). Utile pour test rapide.",
    )
    args = parser.parse_args()

    t0 = time.time()
    result = compute_idf(args.collection, limit=args.limit)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False)

    size_kb = out_path.stat().st_size / 1024
    logger.info(
        "Wrote %s (%d tokens, median=%.3f, n_docs=%d, %.1f KB) in %.1fs",
        out_path, result["n_tokens"], result["median"], result["n_docs"],
        size_kb, time.time() - t0,
    )
    logger.info(
        "Done. Pour que le reranker recharge le dict IDF en RAM, executer :\n"
        "    docker compose restart opti-moteur-front\n"
        "Puis verifier : docker compose logs --tail 30 opti-moteur-front | grep -i IDF"
    )


if __name__ == "__main__":
    main()
