#!/usr/bin/env python3
"""
=============================================================================
run_audit.py - Harness E2E qualite moteur de recherche HelloPro
=============================================================================
But : reproduire l'audit Cowork de maniere automatisee et reproductible.

Pour chaque keyword (17 au total), le script :
  1. GET l'URL front (mode hybride : ?ajax=1&core_v2=1)
  2. Parse le HTML pour extraire les cartes produits (.card-product.list_produit)
  3. Calcule une note auto par heuristique simple :
       - tokens query normalises (NFD + lowercase + stripped accents)
       - tokens titre normalises
       - match_ratio = |intersection| / |query_tokens|
       - note 1-5 selon paliers (5=parfait, 1=hors-sujet)
  4. Calcule KPIs page par page (P1, P2, P3, P4) :
       - moyenne note /10
       - % pertinents (note >=4)
       - doublons stricts (meme id_produit + meme societe+titre>80%)
       - latence ms
  5. Sortie JSON datee dans results/

Usage :
  python3 run_audit.py [--output results/T0_baseline_2026-05-15.json]
                       [--keywords keywords.json]
                       [--workers 4]
                       [--pages 4]
                       [--verbose]

Resultats : note globale ponderee 60% P1 + 40% P2 (comme l'audit Cowork)
=============================================================================
"""

import argparse
import json
import os
import re
import sys
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError as e:
    print(f"ERREUR : modules manquants ({e}). Installer : pip install requests beautifulsoup4")
    sys.exit(1)


# =============================================================================
# CONFIG
# =============================================================================
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux x86_64) HP-SearchQualityHarness/1.0 (+rravelonarisoa@hellopro.fr)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
}
PAGE_SIZE = 40   # 40 produits par page (server-side)
TIMEOUT_SEC = 30


# =============================================================================
# NORMALISATION (alignee avec traitement_mot_mt cote PHP)
# =============================================================================
def normalize_text(s):
    """Lowercase + NFD + strip diacritiques + ponctuation -> espaces."""
    if not s:
        return ""
    s = s.lower()
    # NFD + filter diacritiques
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    # ponctuation -> espace
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(s.split())


def tokenize(s):
    """Renvoie set de tokens normalises (filtres : len >= 2, pas stopwords basiques)."""
    STOP = {"de", "du", "la", "le", "les", "un", "une", "et", "ou", "a", "au", "aux", "en", "pour", "sur", "avec", "par"}
    return {t for t in normalize_text(s).split() if len(t) >= 2 and t not in STOP}


# =============================================================================
# SCORING heuristique
# =============================================================================
def score_match(query_tokens, title_tokens):
    """
    Renvoie note 1-5 selon ratio tokens query trouves dans titre.
      5 = tous les tokens query presents (match parfait)
      4 = >=75%
      3 = >=50%
      2 = >=25%
      1 = aucun match
    """
    if not query_tokens:
        return 1
    nb_hits = len(query_tokens & title_tokens)
    ratio = nb_hits / len(query_tokens)
    if ratio >= 1.0:
        return 5
    if ratio >= 0.75:
        return 4
    if ratio >= 0.5:
        return 3
    if ratio >= 0.25:
        return 2
    return 1


def page_kpis(cards, query_tokens):
    """Calcule KPIs (note moyenne, % pertinents, doublons) pour une liste de cartes."""
    if not cards:
        return {"n": 0, "mean_score": 0.0, "pertinent_pct": 0.0, "top5_mean": 0.0, "duplicates": 0}

    scores = []
    seen_ids = set()
    seen_norm_titles = {}  # norm_title -> count
    duplicates = 0

    for card in cards:
        title_tokens = tokenize(card["title"])
        s = score_match(query_tokens, title_tokens)
        scores.append(s)

        # doublon strict : meme id_produit OU meme titre normalise + meme societe
        if card["id"] and card["id"] in seen_ids:
            duplicates += 1
        else:
            if card["id"]:
                seen_ids.add(card["id"])

        norm_t = normalize_text(card["title"])[:80]  # 80 premiers chars
        norm_key = (norm_t, card.get("societe", "").lower())
        seen_norm_titles[norm_key] = seen_norm_titles.get(norm_key, 0) + 1

    # compter les vrais doublons par titre normalise + societe
    dup_by_title = sum(v - 1 for v in seen_norm_titles.values() if v > 1)

    return {
        "n": len(cards),
        "mean_score": round(sum(scores) / len(scores), 2),
        "pertinent_pct": round(100.0 * sum(1 for s in scores if s >= 4) / len(scores), 1),
        "top5_mean": round(sum(scores[:5]) / min(5, len(scores)), 2),
        "duplicates_by_id": duplicates,
        "duplicates_by_normalized_title": dup_by_title,
    }


# =============================================================================
# PARSER HTML
# =============================================================================
def parse_cards(html):
    """
    Extrait les cartes produits du HTML.
    Cherche les elements ayant classe 'card-product list_produit'.
    Renvoie liste de dict : {id, title, societe, position}
    """
    soup = BeautifulSoup(html, "html.parser")
    cards = []

    # Selecteur principal d'apres REGLES_MOTEUR_RECHERCHE_V2.md (l.443-450)
    for idx, card in enumerate(soup.select(".card-product.list_produit"), start=1):
        # ID produit : data-id-produit ou data-produit-id ou href contenant /produit-XXX-
        pid = card.get("data-id-produit") or card.get("data-produit-id") or ""
        if not pid:
            link = card.find("a", href=True)
            if link:
                m = re.search(r"/produit-(\d+)-", link["href"])
                if m:
                    pid = m.group(1)

        # Titre : chercher dans h3 / h2 / a[title]
        title = ""
        for sel in ["h3", "h2", ".product-title", ".titre-produit", "a[title]"]:
            el = card.select_one(sel)
            if el:
                title = el.get("title", "") or el.get_text(strip=True)
                if title:
                    break

        # Fallback : tout le texte de la premiere ligne
        if not title:
            title = card.get_text(strip=True)[:120]

        # Societe : data-societe ou cherche dans un span class containing societe
        societe = card.get("data-societe", "")
        if not societe:
            for sel in [".product-vendor", ".vendeur", ".nom-societe", "[class*=societe]"]:
                el = card.select_one(sel)
                if el:
                    societe = el.get_text(strip=True)
                    if societe:
                        break

        cards.append({
            "position": idx,
            "id": pid,
            "title": title.strip(),
            "societe": societe.strip(),
        })

    return cards


def slice_pages(all_cards, pages_wanted=4):
    """Split la liste de cartes en pages de PAGE_SIZE (40).
    En mode hybride server-side, toutes les cartes sont dans le HTML."""
    pages = {}
    for p in range(1, pages_wanted + 1):
        start = (p - 1) * PAGE_SIZE
        end = start + PAGE_SIZE
        pages[f"p{p}"] = all_cards[start:end]
    return pages


# =============================================================================
# FETCH
# =============================================================================
def fetch_query(query, url_template, verbose=False):
    """Fetch une URL, retourne (status, latency_ms, html, error)."""
    url = url_template.format(query=quote_plus(query))
    t0 = time.time()
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT_SEC, allow_redirects=True)
        elapsed_ms = int((time.time() - t0) * 1000)
        if verbose:
            print(f"  [HTTP {r.status_code}] {elapsed_ms}ms  {query[:60]}", flush=True)
        return (r.status_code, elapsed_ms, r.text, None)
    except Exception as e:
        elapsed_ms = int((time.time() - t0) * 1000)
        if verbose:
            print(f"  [ERROR] {elapsed_ms}ms  {query[:60]}  : {e}", flush=True)
        return (None, elapsed_ms, "", str(e))


def audit_one_keyword(kw_obj, url_template, pages_wanted=4, verbose=False):
    """Audit complet d'un keyword."""
    query = kw_obj["query"]
    query_tokens = tokenize(query)

    status, latency_ms, html, error = fetch_query(query, url_template, verbose=verbose)
    if error or status != 200:
        return {
            "query": query,
            "audit_score": kw_obj.get("audit_score"),
            "category": kw_obj.get("category"),
            "error": error or f"HTTP {status}",
            "latency_ms": latency_ms,
        }

    all_cards = parse_cards(html)
    pages = slice_pages(all_cards, pages_wanted=pages_wanted)

    page_results = {}
    for pname, cards in pages.items():
        page_results[pname] = page_kpis(cards, query_tokens)
        # Pour debug : top5 titles
        page_results[pname]["top5_titles"] = [
            {"pos": c["position"], "title": c["title"][:80], "score": score_match(query_tokens, tokenize(c["title"]))}
            for c in cards[:5]
        ]

    # Note globale : moyenne ponderee 60% P1 + 40% P2 (comme audit)
    p1_mean = page_results["p1"]["mean_score"]
    p2_mean = page_results["p2"]["mean_score"]
    if page_results["p2"]["n"] > 0:
        global_score_5 = 0.6 * p1_mean + 0.4 * p2_mean
    else:
        global_score_5 = p1_mean
    auto_score_10 = round(global_score_5 * 2.0, 2)

    return {
        "query": query,
        "audit_score": kw_obj.get("audit_score"),
        "category": kw_obj.get("category"),
        "auto_score": auto_score_10,
        "delta_vs_audit": round(auto_score_10 - kw_obj.get("audit_score", 0), 2),
        "latency_ms": latency_ms,
        "total_cards_parsed": len(all_cards),
        "pages": page_results,
    }


# =============================================================================
# MAIN
# =============================================================================
def main():
    ap = argparse.ArgumentParser(description="Harness E2E qualite recherche HelloPro")
    ap.add_argument("--keywords", default="keywords.json", help="Path vers keywords.json")
    ap.add_argument("--output", default=None, help="Path output JSON (default: results/T<run_id>.json)")
    ap.add_argument("--workers", type=int, default=4, help="Nb threads paralleles")
    ap.add_argument("--pages", type=int, default=4, help="Nb pages a analyser")
    ap.add_argument("--verbose", action="store_true", help="Print chaque requete")
    ap.add_argument("--only-critical", action="store_true", help="Tester uniquement les 9 critiques")
    ap.add_argument("--only-canary", action="store_true", help="Tester uniquement les 8 canari")
    args = ap.parse_args()

    # Load keywords
    with open(args.keywords, encoding="utf-8") as f:
        kw_data = json.load(f)

    url_template = kw_data["url_template"]
    all_keywords = []
    if not args.only_canary:
        all_keywords.extend(("critical", k) for k in kw_data["groups"]["critical"])
    if not args.only_critical:
        all_keywords.extend(("canary", k) for k in kw_data["groups"]["canary"])

    print(f"=== Audit qualite recherche - {len(all_keywords)} keywords ===")
    print(f"URL template : {url_template}")
    print(f"Workers : {args.workers}, pages : {args.pages}")
    print()

    t_start = time.time()
    results = []

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(audit_one_keyword, kw, url_template, args.pages, args.verbose): (grp, kw) for grp, kw in all_keywords}
        for fut in as_completed(futs):
            grp, kw = futs[fut]
            try:
                res = fut.result()
                res["group"] = grp
                results.append(res)
                marker = "OK" if "error" not in res else "KO"
                score_str = f"audit={res.get('audit_score')} auto={res.get('auto_score','?')}" if "auto_score" in res else f"ERREUR {res.get('error')}"
                print(f"  [{marker}] [{grp:8s}] {res['query'][:60]:60s} | {score_str}", flush=True)
            except Exception as e:
                print(f"  [EXC] {kw['query']}: {e}", flush=True)

    # Tri stable : critical d'abord (ordre audit_score asc), puis canary
    results.sort(key=lambda r: (0 if r["group"] == "critical" else 1, r.get("audit_score", 0)))

    # Globaux
    by_group = {"critical": [], "canary": []}
    for r in results:
        if "auto_score" in r:
            by_group[r["group"]].append(r["auto_score"])
    avg_all = sum([r.get("auto_score", 0) for r in results if "auto_score" in r]) / max(1, sum(1 for r in results if "auto_score" in r))

    summary = {
        "run_id": datetime.now().strftime("%Y-%m-%d_%H-%M-%S"),
        "ts_start": datetime.now().isoformat(),
        "duration_s": round(time.time() - t_start, 1),
        "url_template": url_template,
        "nb_keywords": len(results),
        "global_avg_auto_score": round(avg_all, 2),
        "critical_avg_auto_score": round(sum(by_group["critical"]) / max(1, len(by_group["critical"])), 2),
        "canary_avg_auto_score": round(sum(by_group["canary"]) / max(1, len(by_group["canary"])), 2),
        "regression_threshold": kw_data.get("regression_threshold"),
        "keywords": results,
    }

    # Output
    if args.output:
        out_path = args.output
    else:
        run_id = summary["run_id"]
        os.makedirs("results", exist_ok=True)
        out_path = f"results/run_{run_id}.json"

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print()
    print(f"=== Termine en {summary['duration_s']}s ===")
    print(f"  Global avg auto_score : {summary['global_avg_auto_score']} /10  (audit Cowork = 6.7)")
    print(f"  Critical (9 kw) avg   : {summary['critical_avg_auto_score']} /10  (audit < 5)")
    # FIX 2026-05-15 : seuil renomme par PR #581 (canary_min_score -> canary_max_drop)
    # On gere les 2 noms pour retro-compat + on tolere l'absence du champ.
    rt = summary.get('regression_threshold') or {}
    if 'canary_max_drop' in rt:
        seuil_str = f"delta >= -{rt['canary_max_drop']} vs T0"
    elif 'canary_min_score' in rt:
        seuil_str = f"score >= {rt['canary_min_score']} (deprecated absolu)"
    else:
        seuil_str = "n/a"
    print(f"  Canary (8 kw) avg     : {summary['canary_avg_auto_score']} /10  (audit ~10)  -> seuil regression : {seuil_str}")
    print(f"  Output JSON : {out_path}")


if __name__ == "__main__":
    main()
