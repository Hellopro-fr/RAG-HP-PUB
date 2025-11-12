#!/usr/bin/env python3
"""
Script de comparaison entre API Classification V1 et V2
"""

import requests
import json
import time
from typing import List, Dict

# URLs des APIs
API_V1_URL = "http://localhost:8577/classification/classify/batch"
API_V2_URL = "http://localhost:8578/classification/classify/batch"

# Dataset de test (à adapter avec vos vrais produits)
TEST_PRODUCTS = [
    {
        "id_produit": "test_001",
        "nom_produit": "Perceuse électrique Bosch 750W",
        "description": "Perceuse électrique professionnelle avec mandrin automatique"
    },
    {
        "id_produit": "test_002",
        "nom_produit": "Marteau piqueur pneumatique",
        "description": "Marteau piqueur 25kg pour travaux de démolition"
    },
    {
        "id_produit": "test_003",
        "nom_produit": "Scie circulaire",
        "description": "Scie circulaire 1200W avec lame carbure"
    },
    {
        "id_produit": "test_004",
        "nom_produit": "Ponceuse orbitale",
        "description": "Ponceuse électrique avec aspiration intégrée"
    },
    {
        "id_produit": "test_005",
        "nom_produit": "Meuleuse d'angle",
        "description": "Meuleuse 125mm 900W pour métaux"
    }
]

def test_api(url: str, products: List[Dict], llm: str = "Qwen") -> Dict:
    """Teste une API avec un batch de produits"""
    payload = {
        "produits": products,
        "llm": llm
    }

    start_time = time.time()
    try:
        response = requests.post(url, json=payload, timeout=300)
        response.raise_for_status()
        elapsed_time = time.time() - start_time

        result = response.json()
        result['elapsed_time'] = elapsed_time
        return result
    except Exception as e:
        return {
            "error": str(e),
            "elapsed_time": time.time() - start_time
        }

def analyze_results(results: Dict) -> Dict:
    """Analyse les résultats d'une API"""
    if "error" in results:
        return {
            "error": results["error"],
            "score_1_count": 0,
            "score_0_count": 0,
            "error_count": 0,
            "total": 0,
            "score_1_percentage": 0.0,
            "avg_time_per_product": 0.0
        }

    resultats = results.get("resultats", [])
    total = len(resultats)

    score_1_count = sum(1 for r in resultats if r.get("score_llm") == 1)
    score_0_count = sum(1 for r in resultats if r.get("score_llm") == 0)
    error_count = sum(1 for r in resultats if r.get("status") == "ERROR")

    return {
        "total": total,
        "score_1_count": score_1_count,
        "score_0_count": score_0_count,
        "error_count": error_count,
        "score_1_percentage": (score_1_count / total * 100) if total > 0 else 0.0,
        "score_0_percentage": (score_0_count / total * 100) if total > 0 else 0.0,
        "error_percentage": (error_count / total * 100) if total > 0 else 0.0,
        "total_time": results.get("elapsed_time", 0),
        "avg_time_per_product": results.get("elapsed_time", 0) / total if total > 0 else 0.0
    }

def print_comparison(v1_stats: Dict, v2_stats: Dict):
    """Affiche la comparaison entre V1 et V2"""
    print("\n" + "="*80)
    print("📊 COMPARAISON API CLASSIFICATION V1 vs V2")
    print("="*80)

    print("\n🔹 V1 (Production) - http://localhost:8577")
    print(f"  Total produits:     {v1_stats['total']}")
    print(f"  Score = 1:          {v1_stats['score_1_count']:>3} ({v1_stats['score_1_percentage']:>5.1f}%)")
    print(f"  Score = 0:          {v1_stats['score_0_count']:>3} ({v1_stats['score_0_percentage']:>5.1f}%)")
    print(f"  Erreurs:            {v1_stats['error_count']:>3} ({v1_stats['error_percentage']:>5.1f}%)")
    print(f"  Temps total:        {v1_stats['total_time']:.2f}s")
    print(f"  Temps/produit:      {v1_stats['avg_time_per_product']:.2f}s")

    print("\n🔸 V2 (Test) - http://localhost:8578")
    print(f"  Total produits:     {v2_stats['total']}")
    print(f"  Score = 1:          {v2_stats['score_1_count']:>3} ({v2_stats['score_1_percentage']:>5.1f}%)")
    print(f"  Score = 0:          {v2_stats['score_0_count']:>3} ({v2_stats['score_0_percentage']:>5.1f}%)")
    print(f"  Erreurs:            {v2_stats['error_count']:>3} ({v2_stats['error_percentage']:>5.1f}%)")
    print(f"  Temps total:        {v2_stats['total_time']:.2f}s")
    print(f"  Temps/produit:      {v2_stats['avg_time_per_product']:.2f}s")

    print("\n📈 DIFFÉRENCES")
    diff_score_1 = v2_stats['score_1_percentage'] - v1_stats['score_1_percentage']
    diff_time = v2_stats['total_time'] - v1_stats['total_time']

    emoji_score = "✅" if diff_score_1 > 0 else "⚠️" if diff_score_1 == 0 else "❌"
    emoji_time = "✅" if diff_time < 0 else "⚠️" if diff_time == 0 else "❌"

    print(f"  {emoji_score} Score = 1:       {diff_score_1:+.1f}% ({'+' if diff_score_1 >= 0 else ''}{v2_stats['score_1_count'] - v1_stats['score_1_count']} produits)")
    print(f"  {emoji_time} Temps:           {diff_time:+.2f}s ({'+' if diff_time >= 0 else ''}{(diff_time / v1_stats['total_time'] * 100) if v1_stats['total_time'] > 0 else 0:.1f}%)")

    print("\n💡 RECOMMANDATION")
    if diff_score_1 >= 5 and diff_time <= v1_stats['total_time'] * 1.2:
        print("  ✅ V2 est MEILLEURE : Score amélioré sans impact majeur sur les performances")
    elif diff_score_1 >= 5:
        print("  ⚠️  V2 améliore le score mais est plus lente : À optimiser")
    elif diff_time < v1_stats['total_time'] * 0.8:
        print("  ⚠️  V2 est plus rapide mais le score n'est pas amélioré")
    else:
        print("  ❌ V2 n'apporte pas d'amélioration significative")

    print("\n" + "="*80)

def main():
    print("🚀 Lancement de la comparaison V1 vs V2...")
    print(f"📦 {len(TEST_PRODUCTS)} produits de test\n")

    # Test V1
    print("🔹 Test de V1 en cours...")
    v1_results = test_api(API_V1_URL, TEST_PRODUCTS)
    v1_stats = analyze_results(v1_results)

    # Test V2
    print("🔸 Test de V2 en cours...")
    v2_results = test_api(API_V2_URL, TEST_PRODUCTS)
    v2_stats = analyze_results(v2_results)

    # Afficher la comparaison
    print_comparison(v1_stats, v2_stats)

    # Sauvegarder les résultats détaillés
    output = {
        "test_date": time.strftime("%Y-%m-%d %H:%M:%S"),
        "test_products_count": len(TEST_PRODUCTS),
        "v1": {
            "stats": v1_stats,
            "results": v1_results
        },
        "v2": {
            "stats": v2_stats,
            "results": v2_results
        }
    }

    output_file = f"comparison_results_{int(time.time())}.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n💾 Résultats détaillés sauvegardés dans: {output_file}")

if __name__ == "__main__":
    main()
