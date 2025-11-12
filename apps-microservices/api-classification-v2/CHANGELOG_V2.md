# Changelog API Classification V2

## Version 2.0.0 - 2025-11-12

### ✨ Nouvelles fonctionnalités

#### Ajout du champ `categorie_candidates` dans les résultats
- **Description** : Retourne la liste complète des catégories candidates qui ont été envoyées au LLM pour classification
- **Format** : Liste d'objets contenant :
  - `id` : ID de la catégorie
  - `name` : Nom de la catégorie
  - `average_score` : Score moyen de similarité (arrondi à 4 décimales)
  - `total_score` : Score total de similarité (arrondi à 4 décimales)
  - `product_count` : Nombre de produits similaires dans cette catégorie

#### Exemple de réponse :

```json
{
  "id_produit": "test_001",
  "titre_produit": "Perceuse électrique Bosch 750W",
  "description_produit": "Perceuse électrique professionnelle",
  "status": "SUCCESS",
  "id_categorie": "12345",
  "nom_categorie": "Perceuses électriques",
  "score_llm": 1,
  "categorie_candidates": [
    {
      "id": "12345",
      "name": "Perceuses électriques",
      "average_score": 0.8952,
      "total_score": 13.4280,
      "product_count": 15
    },
    {
      "id": "12346",
      "name": "Outils électroportatifs",
      "average_score": 0.7234,
      "total_score": 7.2340,
      "product_count": 10
    },
    {
      "id": "12347",
      "name": "Outillage professionnel",
      "average_score": 0.6891,
      "total_score": 5.5128,
      "product_count": 8
    }
  ],
  "processing_time": 2.45,
  "llm_type": "Qwen",
  "enable_thinking": false
}
```

### 🔧 Améliorations techniques

#### Fonction helper `_format_categories_candidates()`
- Nouvelle méthode dans la classe `ProductClassifier`
- Formate les catégories pour une meilleure lisibilité dans l'API
- Limite automatiquement au nombre défini par `categories_limit`

### 📊 Utilité de ce changement

1. **Debug et analyse** : Permet de voir exactement quelles catégories étaient en compétition
2. **Validation** : Facilite la vérification si le LLM a eu accès aux bonnes catégories
3. **Amélioration continue** :
   - Identifier les cas où la bonne catégorie n'est pas dans le top 10
   - Analyser les scores des catégories pour comprendre les hésitations
   - Détecter les produits ambigus (plusieurs catégories avec des scores proches)

### 🎯 Cas d'usage

#### Analyser un produit mal classé :
```python
result = response["resultats"][0]
if result["score_llm"] == 0:
    # Voir toutes les catégories candidates
    candidates = result["categorie_candidates"]

    # Vérifier si la bonne catégorie était présente
    correct_cat = next((c for c in candidates if c["id"] == expected_id), None)

    if correct_cat:
        print(f"La bonne catégorie était présente avec un score de {correct_cat['average_score']}")
    else:
        print("La bonne catégorie n'était pas dans les candidates → Problème de recherche RAG")
```

#### Détecter les produits ambigus :
```python
candidates = result["categorie_candidates"]
top_scores = [c["average_score"] for c in candidates[:3]]

# Si les 3 premiers scores sont très proches
if max(top_scores) - min(top_scores) < 0.1:
    print("⚠️ Produit ambigu : plusieurs catégories très proches")
    print(f"Catégories: {[c['name'] for c in candidates[:3]]}")
```

### 📝 Modifications de fichiers

#### `apps-microservices/api-classification-v2/app/schemas/classification.py`
- Ajout du champ `categorie_candidates` dans `ClassificationResult`

#### `apps-microservices/api-classification-v2/app/core/classifier.py`
- Nouvelle méthode : `_format_categories_candidates()` (lignes 97-108)
- Ajout de `categorie_candidates` dans tous les retours de `classify_single()`
  - Cas de succès (ligne 639)
  - Cas d'erreur LLM (ligne 562)
  - Cas d'erreur parsing (ligne 583)
  - Cas d'erreur validation (lignes 603, 622)
  - Cas d'exception générale (ligne 656)
  - Cas sans produits similaires (ligne 518): `None`
  - Cas sans catégories (ligne 537): `None`

### 🚀 Déploiement

Pour activer ces changements :

```bash
# Rebuild de l'image
docker compose build api-classification-v2-service

# Redémarrage du service
docker compose up -d api-classification-v2-service

# Vérification
curl http://localhost:8578/classification/classify -X POST \
  -H "Content-Type: application/json" \
  -d '{
    "id_produit": "test",
    "nom_produit": "Perceuse Bosch",
    "description": "Perceuse électrique",
    "llm": "Qwen"
  }' | jq '.categorie_candidates'
```

### 📈 Prochaines étapes suggérées

1. **Analyse statistique** :
   - Moyenne des `average_score` des catégories choisies
   - Distribution des `product_count` dans les catégories candidates

2. **Amélioration du prompt** :
   - Si `average_score` < 0.7 pour toutes les catégories → Prompt trop strict
   - Si écart entre top 1 et top 2 < 0.05 → Besoin de meilleures descriptions

3. **Optimisation du RAG** :
   - Analyser les cas où bonne catégorie absente des candidates
   - Ajuster `search_results_limit` ou algorithme de groupement

---

**Date** : 2025-11-12
**Version** : 2.0.0
**Status** : ✅ Prêt pour test
