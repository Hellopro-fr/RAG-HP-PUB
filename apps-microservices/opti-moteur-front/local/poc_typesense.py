#!/usr/bin/env python3
"""
POC Typesense — Recherche produits HelloPro
Comparaison hybrid search vs sémantique pur

Requête test : "armoire medicale"
Données : produits réels extraits de la base edgb2b (produit_front + rubrique_front)
"""

import typesense
import time
import json
import sys

# ============================================================
# CONFIG
# ============================================================
TYPESENSE_HOST = "localhost"
TYPESENSE_PORT = "8108"
TYPESENSE_API_KEY = "hp_poc_2026"
COLLECTION_NAME = "produits_hellopro"

client = typesense.Client({
    "api_key": TYPESENSE_API_KEY,
    "nodes": [{"host": TYPESENSE_HOST, "port": TYPESENSE_PORT, "protocol": "http"}],
    "connection_timeout_seconds": 10,
})

# ============================================================
# PRODUITS RÉELS HELLOPRO (extraits le 20/04/2026 via MCP edgb2b)
# ============================================================
PRODUCTS = [
    # --- ARMOIRE MÉDICALE (rubrique 2007191) ---
    {"id": "40061", "nom": "Armoire aluminium transport linge et bacs ISO/DIN médicaments",
     "rubrique": "Armoire médicale", "categorie_id": "2007191",
     "description": "Cette armoire en aluminium permet de transporter du linge, des bacs et paniers ISO et DIN (médicaments). Dimensions extérieures disponibles: 1230x630x1500mm, 1230x630x1740mm, 1400x710x1740mm.",
     "fournisseur": "Logistique Hospitalière"},
    {"id": "40530", "nom": "Distributeur automatique SupplyPoint Pharma ELECTROCLASS",
     "rubrique": "Armoire médicale", "categorie_id": "2007191",
     "description": "Le distributeur automatique SupplyPoint Pharma d'ELECTROCLASS est la solution de distribution sécurisée pour optimiser la gestion de vos références de médicaments et simplifier la distribution de stupéfiants.",
     "fournisseur": "ELECTROCLASS"},
    {"id": "40535", "nom": "Stockeur rotatif HD40 pour dispositifs médicaux",
     "rubrique": "Armoire médicale", "categorie_id": "2007191",
     "description": "Le stockeur rotatif HD40 est un stockeur dynamique de grande profondeur particulièrement adapté au stockage de dispositifs médicaux. Système automatisé conçu pour le stockage et la sécurisation de vos DMS.",
     "fournisseur": "ELECTROCLASS"},
    {"id": "141641", "nom": "Meuble de stockage horizontal des endoscopes",
     "rubrique": "Armoire médicale", "categorie_id": "2007191",
     "description": "Meuble de stockage horizontal des endoscopes. Structure en résine phénolique HPL, coulisses sortie totale, bacs endoscopes en polycarbonate avec couvercle.",
     "fournisseur": "AG MEDICAL"},
    {"id": "222958", "nom": "Armoire mobile à rideau équipée étagères et table escamotable",
     "rubrique": "Armoire médicale", "categorie_id": "2007191",
     "description": "Armoire mobile à rideau équipée avec étagères, table de travail escamotable, tiroirs télescopiques en option. Roues diamètre 100mm. Dimensions: L1060 x P510 x H1870mm.",
     "fournisseur": "MUSIC"},
    {"id": "5209861", "nom": "Armoire stockage piluliers Modulo",
     "rubrique": "Armoire médicale", "categorie_id": "2007191",
     "description": "Pour le stockage des piluliers Modulo, une large gamme est disponible. Adapté aux différentes tailles d'établissements. Capacités variables: de 26 à 90 plateaux de piluliers.",
     "fournisseur": "MUSIC"},
    {"id": "5210324", "nom": "Armoire à pharmacie Praticima modulaire",
     "rubrique": "Armoire médicale", "categorie_id": "2007191",
     "description": "La gamme d'armoire à pharmacie Praticima est modulaire, évolutive et compatible aux standards 600x400. Armoires aux volumes différents, à porte ou à rideau, aménagements intérieurs modulables.",
     "fournisseur": "MUSIC"},
    {"id": "5245552", "nom": "Rayonnage télescopique Easydrawer stockage médicaments",
     "rubrique": "Armoire médicale", "categorie_id": "2007191",
     "description": "Le rayonnage télescopique Easydrawer est idéal pour le stockage de médicaments. Système modulaire et autoportant avec tiroirs télescopiques et séparateurs en métal.",
     "fournisseur": "MUSIC"},
    {"id": "5245559", "nom": "Armoire Optistock matériels stériles et non-stériles",
     "rubrique": "Armoire médicale", "categorie_id": "2007191",
     "description": "La ligne Optistock a été conçue pour le stockage en réserves de matériels stériles ou non-stériles, déconditionnés ou non. S'utilise dans tous les services dont la PUI, qualités uniques dans le domaine de l'hygiène.",
     "fournisseur": "MUSIC"},
    {"id": "5797014", "nom": "Armoire inox 304 portes verre trempé verrouillables",
     "rubrique": "Armoire médicale", "categorie_id": "2007191",
     "description": "Armoire en acier inoxydable 304 avec deux portes verrouillables en verre trempé 5mm, 4 étagères verre trempé 6mm, 4 pieds réglables. Dimensions: 100x48xh190cm. Fabriquée en Italie.",
     "fournisseur": "MORETTI"},
    {"id": "5797018", "nom": "Armoire à pharmacie verrouillage médicaments dangereux 48 compartiments",
     "rubrique": "Armoire médicale", "categorie_id": "2007191",
     "description": "Armoire à pharmacie avec système de verrouillage pour médicaments dangereux, 48 compartiments et 5 étagères réglables. Mélamine 20mm, châssis acier laqué poudre époxy.",
     "fournisseur": "MORETTI"},
    {"id": "5728325", "nom": "Armoire aménagement pharmacie hospitalière",
     "rubrique": "Armoire médicale", "categorie_id": "2007191",
     "description": "Ces armoires permettent d'aménager les pharmacies en milieu hospitalier en respectant les règles d'hygiène et de sécurité. Conçues pour faciliter la gestion d'approvisionnement des services au quotidien grâce à leur compatibilité avec les chariots.",
     "fournisseur": "MUSIC"},
    {"id": "6129104", "nom": "Armoire transport linge et fournitures stériles CT200",
     "rubrique": "Armoire médicale", "categorie_id": "2007191",
     "description": "Armoire pour le transport du linge et de fournitures stériles. Structure acier inoxydable AISI 304, 2 étagères ajustables, 2 portes battantes ouverture 270° fermeture à clé.",
     "fournisseur": "AG MEDICAL"},
    {"id": "6405450", "nom": "Réfrigérateur médical 1400 lt double porte AF140",
     "rubrique": "Armoire médicale", "categorie_id": "2007191",
     "description": "Réfrigérateur médical 1400 lt double porte AF140. 8 étagères, jusqu'à 14 tiroirs optionnels. Structure extérieure tôle galvanisée, intérieur inox. Gaz réfrigérant R404a.",
     "fournisseur": "IFM"},
    {"id": "6447431", "nom": "Armoire médicale réfrigérée IFM280TCE",
     "rubrique": "Armoire médicale", "categorie_id": "2007191",
     "description": "Belle armoire médicale réfrigérée IFM280TCE pour le stockage de médicaments et produits thermosensibles. Conforme aux normes pharmaceutiques.",
     "fournisseur": "ALLBATTERIES"},
    {"id": "6447438", "nom": "Armoire médicale réfrigérée IFM336TCE",
     "rubrique": "Armoire médicale", "categorie_id": "2007191",
     "description": "Grande armoire médicale réfrigérée IFM336TCE pour le stockage de médicaments et produits thermosensibles en milieu hospitalier.",
     "fournisseur": "ALLBATTERIES"},

    # --- ARMOIRE À PHARMACIE (rubrique 2017274) ---
    {"id": "7001001", "nom": "Armoire à pharmacie murale métal 1 porte serrure sécurité",
     "rubrique": "Armoires à pharmacie", "categorie_id": "2017274",
     "description": "Armoire à pharmacie murale en métal avec 1 porte, serrure de sécurité, étagères réglables pour stockage médicaments en entreprise.",
     "fournisseur": "SecuritéGoodDeal"},
    {"id": "7001002", "nom": "Armoire à pharmacie garnie métal premiers secours",
     "rubrique": "Armoires à pharmacie", "categorie_id": "2017274",
     "description": "Armoire à pharmacie garnie en métal avec 1 porte, livrée avec équipements premiers secours, pansements et désinfectant.",
     "fournisseur": "SecuritéGoodDeal"},
    {"id": "7001003", "nom": "Armoire à pharmacie métal blanc entreprise collectivité",
     "rubrique": "Armoires à pharmacie", "categorie_id": "2017274",
     "description": "Armoire à pharmacie en métal blanc avec 1 porte, idéale pour entreprise et collectivité, conforme réglementation code du travail.",
     "fournisseur": "URGENCE SECOURS EQUIPEMENT"},

    # --- ARMOIRE DE SÉCURITÉ (rubrique 1002240) — semi-pertinent ---
    {"id": "19203112", "nom": "Armoire coupe-feu 90min produits inflammables 200L",
     "rubrique": "Armoire de sécurité pour produits dangereux", "categorie_id": "1002240",
     "description": "Armoire pour produits inflammables coupe-feu 90 min EN14470. 1200x600x1950mm, 200L, 2 portes, 3 étagères rétention acier peint.",
     "fournisseur": "ASECOS"},
    {"id": "18231438", "nom": "Armoire sécurité ANTI-FEU 30min haute 1 porte inflammables",
     "rubrique": "Armoire de sécurité pour produits dangereux", "categorie_id": "1002240",
     "description": "Armoire de sécurité ANTI-FEU 30 min haute 1 porte selon NF-EN 14470-1:2004 pour produits inflammables. Construction panneaux stratifié haute pression HPL.",
     "fournisseur": "MUSIC"},
    {"id": "18231381", "nom": "Armoire sécurité inflammable double paroi haut 1 porte",
     "rubrique": "Armoire de sécurité pour produits dangereux", "categorie_id": "1002240",
     "description": "Armoire de sécurité pour inflammable double paroi modèle haut 1 porte. Volume de rétention 45,4L. 2 étagères et bac de rétention 28L. Acier électro-zingué.",
     "fournisseur": "MUSIC"},
    {"id": "17895540", "nom": "Armoire sécurité produits corrosifs haute 1 porte",
     "rubrique": "Armoire de sécurité pour produits dangereux", "categorie_id": "1002240",
     "description": "Armoire de sécurité pour produits corrosifs haute avec 1 porte manuelle plein. Acier 12/10e et 15/10e, peinture poudre époxy.",
     "fournisseur": "MUSIC"},

    # --- ARMOIRE RÉFRIGÉRÉE ALIMENTAIRE (rubrique 2005800) — semi-pertinent ---
    {"id": "525250", "nom": "Armoire réfrigérée Gastronome GN2/1 positif inox",
     "rubrique": "Armoire réfrigérée", "categorie_id": "2005800",
     "description": "Armoire réfrigérée Gastronorme GN2/1 froid ventilé positif 2/8°C. Carrosserie intérieur et extérieur Inox AISI 304. Isolation polyuréthane sans CFC.",
     "fournisseur": "ColdLine"},
    {"id": "1607233", "nom": "Armoire réfrigérée Gastronome 1400 litres positive",
     "rubrique": "Armoire réfrigérée", "categorie_id": "2005800",
     "description": "Armoire réfrigérée Gastronorme GN2/1, 1400 litres, froid ventilé positif 2/8°C. Inox AISI 304, isolation polyuréthane sans CFC.",
     "fournisseur": "ColdLine"},
    {"id": "4147315", "nom": "Armoire réfrigérée positive ou négative porte verre",
     "rubrique": "Armoire réfrigérée", "categorie_id": "2005800",
     "description": "Armoire réfrigérée positive ou négative avec porte en verre. Intérieur et extérieur en inox. Éclairage et serrure. Températures positives +2 à +8°C.",
     "fournisseur": "DIAMOND"},

    # --- ARMOIRE DE PRÉCISION (rubrique 2003362) — bruit avec "médical" dans contexte ---
    {"id": "8607896", "nom": "Armoire traitement air CLINICAIR 1 bloc opératoire",
     "rubrique": "Armoire de précision", "categorie_id": "2003362",
     "description": "Ultra compact et Plug & Play, le CLINICAIR 1 est une armoire de traitement d'air hygiène. Conçu pour traiter les conditions de qualité d'air au sein du bloc opératoire, normes NFS 90-351.",
     "fournisseur": "ATA"},
    {"id": "8607897", "nom": "Armoire traitement air CLINICAIR 2 bloc opératoire",
     "rubrique": "Armoire de précision", "categorie_id": "2003362",
     "description": "Plug & Play, le CLINICAIR 2 est une armoire de traitement d'air hygiène. Conçu pour les blocs opératoires, normes NFS 90-351.",
     "fournisseur": "ATA"},
    {"id": "8607915", "nom": "Armoire précision TOPTOP imagerie médicale data center",
     "rubrique": "Armoire de précision", "categorie_id": "2003362",
     "description": "L'armoire TOPTOP est conçue pour assurer une climatisation de précision avec gestion des charges techniques et filtration air pour salles d'imagerie médicale, laboratoires, archives, data center.",
     "fournisseur": "ATA"},

    # --- BRUIT TOTAL: produits qui remontent à tort (encadrés rouges Elena) ---
    {"id": "9001001", "nom": "Batterie médicale rechargeable lithium-ion",
     "rubrique": "Batterie rechargeable", "categorie_id": "9999001",
     "description": "Batterie médicale rechargeable lithium-ion pour équipements médicaux portables, moniteurs et défibrillateurs.",
     "fournisseur": "ALLBATTERIES"},
    {"id": "9001002", "nom": "Flexible chauffant industriel haute température",
     "rubrique": "Flexible chauffant", "categorie_id": "9999002",
     "description": "Flexible chauffant industriel haute température pour canalisation et process, gaine isolante thermique.",
     "fournisseur": "FRANCE EQUIPEMENT"},
    {"id": "9001003", "nom": "Box batteries CEMO Li-Safe-2-S ADR transport",
     "rubrique": "Coffre de stockage batterie lithium", "categorie_id": "9000501",
     "description": "Box batteries CEMO Li-Safe pour stockage sécurisé de batteries lithium avec protection ADR transport.",
     "fournisseur": "CEMO"},
    {"id": "9001004", "nom": "Chariot médical de soins hôpital clinique",
     "rubrique": "Chariot médical", "categorie_id": "9999004",
     "description": "Chariot médical de soins pour hôpitaux et cliniques, plateaux inox, roulettes silencieuses, tiroirs verrouillables.",
     "fournisseur": "MedEquip"},
    {"id": "9001005", "nom": "Lit médicalisé électrique 3 fonctions",
     "rubrique": "Lit médical", "categorie_id": "9999005",
     "description": "Lit médicalisé électrique 3 fonctions avec relève-buste et relève-jambes, barrières de sécurité.",
     "fournisseur": "SantéPro"},
    {"id": "9001006", "nom": "Gants médicaux nitrile non poudrés boîte 100",
     "rubrique": "Gants de protection", "categorie_id": "9999006",
     "description": "Gants médicaux en nitrile non poudrés, boîte de 100, usage unique, examen et soins médicaux.",
     "fournisseur": "ProtecSanté"},
    {"id": "9001007", "nom": "Cuve plastique sur mesure MEDICAL PROCESS",
     "rubrique": "Cuves à usages divers", "categorie_id": "9999007",
     "description": "Cuve plastique sur mesure de 50 à 10000 litres. MEDICAL PROCESS est spécialisé dans les stations de traitement.",
     "fournisseur": "MEDICAL PROCESS"},
    {"id": "9001008", "nom": "Rayonnage inox stockage matériel hospitalier",
     "rubrique": "Rayonnage", "categorie_id": "9999008",
     "description": "Rayonnage en inox pour stockage matériel, étagères réglables, structure démontable.",
     "fournisseur": "StockInox"},
    {"id": "9001009", "nom": "Défibrillateur semi-automatique entreprise ERP",
     "rubrique": "Équipement médical", "categorie_id": "9999009",
     "description": "Défibrillateur semi-automatique pour entreprises et ERP, formation incluse, maintenance 5 ans.",
     "fournisseur": "CardioSafe"},
    {"id": "9001010", "nom": "Stérilisateur médical autoclaves classe B",
     "rubrique": "Équipement médical", "categorie_id": "9999010",
     "description": "Stérilisateur médical autoclaves classe B pour cabinets dentaires et médicaux. Cycle rapide 15 min.",
     "fournisseur": "MedSteril"},

    # --- PRODUITS SUPPLÉMENTAIRES (bruit généraliste) ---
    {"id": "9002001", "nom": "Armoire vestiaire métallique 2 portes industrie",
     "rubrique": "Mobiliers de rangements", "categorie_id": "9999020",
     "description": "Armoire vestiaire métallique avec 2 portes pour vestiaire industriel, structure acier robuste, serrure.",
     "fournisseur": "Bureau Pro"},
    {"id": "9002002", "nom": "Armoire de bureau bois 2 portes rangement dossiers",
     "rubrique": "Mobiliers de rangements", "categorie_id": "9999021",
     "description": "Armoire de bureau en bois mélaminé 2 portes, rangement dossiers suspendus et classeurs.",
     "fournisseur": "Bureau Pro"},
    {"id": "9002003", "nom": "Armoire forte anti-effraction blindée coffre",
     "rubrique": "Coffre-fort", "categorie_id": "9999022",
     "description": "Armoire forte anti-effraction blindée, certification EN 14450, serrure électronique à code.",
     "fournisseur": "FICHET"},
]

# Classification pertinence (ground truth)
RELEVANT_CATEGORIES = {"2007191", "2017274"}  # Armoire médicale + Armoire à pharmacie
SEMI_CATEGORIES = {"1002240", "2005800", "2003362"}  # Sécurité, Réfrigérée, Précision

def classify(cat_id):
    if cat_id in RELEVANT_CATEGORIES:
        return "✅ PERTINENT"
    elif cat_id in SEMI_CATEGORIES:
        return "🟡 SEMI"
    else:
        return "❌ BRUIT"


# ============================================================
# 1. CRÉER LA COLLECTION
# ============================================================
def create_collection():
    schema = {
        "name": COLLECTION_NAME,
        "fields": [
            {"name": "nom", "type": "string"},
            {"name": "rubrique", "type": "string", "facet": True},
            {"name": "categorie_id", "type": "string", "facet": True},
            {"name": "description", "type": "string"},
            {"name": "fournisseur", "type": "string", "facet": True},
            # Champ combiné pour le embedding (vectorisation auto par Typesense)
            {"name": "texte_complet", "type": "string"},
            # Embedding auto via modèle intégré Typesense
            {
                "name": "embedding",
                "type": "auto",
                "embed": {
                    "from": ["texte_complet"],
                    "model_config": {
                        "model_name": "ts/all-MiniLM-L12-v2",  # modèle intégré gratuit
                    }
                }
            },
        ],
        "default_sorting_field": None,
        # Token separators pour le BM25 (traiter les tirets et slashs)
        "token_separators": ["-", "/"],
    }

    # Supprimer si existe déjà
    try:
        client.collections[COLLECTION_NAME].delete()
        print("🗑️  Collection existante supprimée")
    except Exception:
        pass

    client.collections.create(schema)
    print(f"✅ Collection '{COLLECTION_NAME}' créée avec embedding auto (all-MiniLM-L12-v2)")


# ============================================================
# 2. INDEXER LES PRODUITS
# ============================================================
def index_products():
    print(f"\n📦 Indexation de {len(PRODUCTS)} produits...")
    start = time.time()

    for p in PRODUCTS:
        doc = {
            "id": p["id"],
            "nom": p["nom"],
            "rubrique": p["rubrique"],
            "categorie_id": p["categorie_id"],
            "description": p["description"],
            "fournisseur": p["fournisseur"],
            # Combinaison pondérée pour l'embedding
            "texte_complet": f"{p['nom']}. {p['rubrique']}. {p['description']}",
        }
        client.collections[COLLECTION_NAME].documents.create(doc)

    elapsed = time.time() - start
    print(f"✅ {len(PRODUCTS)} produits indexés en {elapsed:.1f}s")


# ============================================================
# 3. RECHERCHE HYBRID
# ============================================================
def search_hybrid(query, alpha=None, top_k=10):
    """
    Recherche hybride Typesense: keyword (BM25) + vectoriel (embedding)
    Alpha dynamique: courtes queries → plus de BM25
    """
    # Alpha dynamique selon longueur de query
    if alpha is None:
        q_len = len(query.split())
        if q_len <= 2:
            alpha = 0.75  # 75% keyword, 25% sémantique
        elif q_len <= 4:
            alpha = 0.50
        else:
            alpha = 0.30  # longue → sémantique dominant

    search_params = {
        "q": query,
        "query_by": "nom,rubrique,description",
        # Boosting des champs: nom x5, rubrique x3, description x1
        "query_by_weights": "5,3,1",
        # Hybrid: utiliser aussi l'embedding
        "vector_query": f"embedding:([], k:{top_k}, alpha:{1 - alpha})",
        "per_page": top_k,
        # Typo tolerance
        "typo_tokens_threshold": 3,
        "drop_tokens_threshold": 2,
        # Facets pour debug
        "facet_by": "rubrique",
    }

    start = time.time()
    results = client.collections[COLLECTION_NAME].documents.search(search_params)
    latency_ms = (time.time() - start) * 1000

    return results, latency_ms, alpha


def search_keyword_only(query, top_k=10):
    """Recherche BM25 pure (sans vecteurs)"""
    search_params = {
        "q": query,
        "query_by": "nom,rubrique,description",
        "query_by_weights": "5,3,1",
        "per_page": top_k,
        "typo_tokens_threshold": 3,
    }
    start = time.time()
    results = client.collections[COLLECTION_NAME].documents.search(search_params)
    latency_ms = (time.time() - start) * 1000
    return results, latency_ms


def search_semantic_only(query, top_k=10):
    """Recherche vectorielle pure (simule Milvus actuel)"""
    search_params = {
        "q": "*",  # pas de keyword
        "vector_query": f"embedding:([], k:{top_k}, alpha:0)",
        "per_page": top_k,
        "query_by": "nom",
        # On passe la query via le prefix embedding
        "vector_query": f"embedding:([],k:{top_k})",
    }
    # Pour la recherche sémantique pure, on utilise un trick:
    # on met alpha=0 dans hybrid pour ne garder que le vecteur
    search_params_real = {
        "q": query,
        "query_by": "nom,rubrique,description",
        "query_by_weights": "5,3,1",
        "vector_query": f"embedding:([], k:{top_k}, alpha:1.0)",
        "per_page": top_k,
    }
    start = time.time()
    results = client.collections[COLLECTION_NAME].documents.search(search_params_real)
    latency_ms = (time.time() - start) * 1000
    return results, latency_ms


# ============================================================
# 4. AFFICHAGE
# ============================================================
def display_results(results, latency_ms, method_name, alpha=None):
    hits = results.get("hits", [])
    found = results.get("found", 0)

    alpha_str = f" (α={alpha:.2f})" if alpha else ""
    print(f"\n{'━' * 80}")
    print(f"  🔍 {method_name}{alpha_str}")
    print(f"  📊 {found} résultats trouvés — ⏱️  {latency_ms:.0f}ms")
    print(f"{'━' * 80}")

    pertinent_count = 0
    noise_count = 0

    for i, hit in enumerate(hits[:10]):
        doc = hit["document"]
        cat_id = doc.get("categorie_id", "?")
        tag = classify(cat_id)

        # Score details
        text_score = hit.get("text_match_info", {}).get("best_field_score", "")
        hybrid_score = hit.get("hybrid_search_info", {}).get("rank_fusion_score", hit.get("text_match", 0))

        print(f"  #{i+1:2d} {tag:14s} {doc['nom'][:55]:55s} | {doc['rubrique'][:28]}")

        if cat_id in RELEVANT_CATEGORIES:
            pertinent_count += 1
        elif cat_id not in SEMI_CATEGORIES:
            noise_count += 1

    p5 = sum(1 for h in hits[:5] if h["document"]["categorie_id"] in RELEVANT_CATEGORIES) / 5
    p10 = sum(1 for h in hits[:10] if h["document"]["categorie_id"] in RELEVANT_CATEGORIES) / min(10, len(hits))

    print(f"\n  📈 Precision@5: {p5:.0%} | Precision@10: {p10:.0%}")
    print(f"  🗑️  Bruit dans Top10: {noise_count} produits hors sujet")
    print(f"  ⏱️  Latence: {latency_ms:.0f}ms")

    return {"p5": p5, "p10": p10, "noise": noise_count, "latency_ms": latency_ms}


# ============================================================
# 5. MAIN
# ============================================================
def main():
    print("=" * 80)
    print("  🚀 POC TYPESENSE — Recherche produits HelloPro")
    print("=" * 80)

    # Setup
    print("\n📋 Configuration:")
    print(f"   Typesense: http://{TYPESENSE_HOST}:{TYPESENSE_PORT}")
    print(f"   Produits: {len(PRODUCTS)}")

    create_collection()
    index_products()

    # Requête test principale (cas Elena)
    query = "armoire medicale"
    print(f"\n\n{'=' * 80}")
    print(f"  🎯 TEST PRINCIPAL: \"{query}\"")
    print(f"  Reproduit le scénario du mail d'Elena (encadrés rouges = bruit)")
    print(f"{'=' * 80}")

    # 1. Sémantique pur (simule Milvus)
    res_sem, lat_sem = search_semantic_only(query)
    m_sem = display_results(res_sem, lat_sem, "SÉMANTIQUE PUR (simule Milvus)")

    # 2. BM25 pur
    res_bm25, lat_bm25 = search_keyword_only(query)
    m_bm25 = display_results(res_bm25, lat_bm25, "BM25 PUR (keyword)")

    # 3. Hybrid dynamique (Typesense)
    res_hyb, lat_hyb, alpha = search_hybrid(query)
    m_hyb = display_results(res_hyb, lat_hyb, "HYBRID DYNAMIQUE (Typesense)", alpha)

    # Résumé comparatif
    print(f"\n\n{'=' * 80}")
    print(f"  📊 RÉSUMÉ COMPARATIF — \"{query}\"")
    print(f"{'=' * 80}")
    print(f"  {'Méthode':<30s} {'P@5':>6s} {'P@10':>7s} {'Bruit':>7s} {'Latence':>10s}")
    print(f"  {'─' * 62}")
    print(f"  {'Sémantique (Milvus)':<30s} {m_sem['p5']:>5.0%} {m_sem['p10']:>6.0%} {m_sem['noise']:>5d}   {m_sem['latency_ms']:>7.0f}ms")
    print(f"  {'BM25 pur':<30s} {m_bm25['p5']:>5.0%} {m_bm25['p10']:>6.0%} {m_bm25['noise']:>5d}   {m_bm25['latency_ms']:>7.0f}ms")
    print(f"  {'Hybrid Typesense (α={:.2f})'.format(alpha):<30s} {m_hyb['p5']:>5.0%} {m_hyb['p10']:>6.0%} {m_hyb['noise']:>5d}   {m_hyb['latency_ms']:>7.0f}ms")

    # Mode interactif
    print(f"\n\n{'=' * 80}")
    print("  🔄 MODE INTERACTIF — Tapez une requête (ou 'quit' pour sortir)")
    print(f"{'=' * 80}")

    while True:
        try:
            q = input("\n  🔍 Requête > ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not q or q.lower() in ("quit", "exit", "q"):
            break

        res, lat, a = search_hybrid(q)
        display_results(res, lat, f"HYBRID \"{q}\"", a)


if __name__ == "__main__":
    main()
