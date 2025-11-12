# API Classification V2 - Version de Test

## 🎯 Objectif

Cette version V2 est une copie complète de `api-classification` pour tester les améliorations de performance sans impacter l'API en production.

## 🔧 Configuration

### Ports
- **API V1 (production)** : `http://localhost:8577`
- **API V2 (test)** : `http://localhost:8578`

### Services Docker
- `api-classification-v2-service` : Service principal (4 replicas)
- `api-classification-v2-lb` : Load balancer nginx

## 🚀 Déploiement

### 1. Build et démarrage
```bash
# Build seulement api-classification-v2
docker-compose build api-classification-v2-service api-classification-v2-lb

# Démarrer uniquement V2
docker-compose up -d api-classification-v2-service api-classification-v2-lb

# Vérifier les logs
docker-compose logs -f api-classification-v2-service
```

### 2. Vérifier le déploiement
```bash
# Health check
curl http://localhost:8578/health

# Status de l'API
curl http://localhost:8578/classification/status

# Version
curl http://localhost:8578/
# Devrait retourner: {"message": "API Classification Produits v2.0.0 (Test)"}
```

## 📊 Tests de Performance

### Test simple (1 produit)
```bash
curl -X POST "http://localhost:8578/classification/classify" \
  -H "Content-Type: application/json" \
  -d '{
    "id_produit": "test_001",
    "nom_produit": "Perceuse électrique Bosch 750W",
    "description": "Perceuse électrique professionnelle avec mandrin automatique",
    "llm": "Qwen"
  }'
```

### Test batch
```bash
curl -X POST "http://localhost:8578/classification/classify/batch" \
  -H "Content-Type: application/json" \
  -d '{
    "produits": [
      {
        "id_produit": "001",
        "nom_produit": "Perceuse électrique",
        "description": "Perceuse 750W"
      },
      {
        "id_produit": "002",
        "nom_produit": "Marteau piqueur",
        "description": "Marteau pneumatique 25kg"
      }
    ],
    "llm": "Qwen"
  }'
```

## 🔬 Comparaison V1 vs V2

### Métriques à surveiller
1. **Taux de Score=1** : Objectif 75%+ (vs 48% actuellement)
2. **Temps de traitement** : À comparer avec V1
3. **Taux d'erreur** : Doit rester stable

### Script de comparaison
```python
import requests
import json

# Test sur les mêmes produits
products = [...]  # Votre dataset de test

# Test V1
response_v1 = requests.post(
    "http://localhost:8577/classification/classify/batch",
    json={"produits": products, "llm": "Qwen"}
)

# Test V2
response_v2 = requests.post(
    "http://localhost:8578/classification/classify/batch",
    json={"produits": products, "llm": "Qwen"}
)

# Comparaison
v1_score1 = sum(1 for r in response_v1.json()["resultats"] if r["score_llm"] == 1)
v2_score1 = sum(1 for r in response_v2.json()["resultats"] if r["score_llm"] == 1)

print(f"V1 Score=1: {v1_score1}/{len(products)} ({v1_score1/len(products)*100:.1f}%)")
print(f"V2 Score=1: {v2_score1}/{len(products)} ({v2_score1/len(products)*100:.1f}%)")
```

## 🛠️ Modifications Apportées (à venir)

### Phase 1 - Quick Wins
- [ ] Reformulation du prompt (classifier.py:270)
- [ ] `search_results_limit`: 30 → 50
- [ ] `categories_limit`: 10 → 15
- [ ] Truncation descriptions: 200 → 400 caractères

### Phase 2 - Optimisations
- [ ] Score hybride dans `group_by_category()`
- [ ] Seuil minimum `average_score >= 0.70`
- [ ] Enrichissement des descriptions
- [ ] Amélioration sélection des exemples

## 📝 Logs et Monitoring

### Voir les logs en temps réel
```bash
docker-compose logs -f api-classification-v2-service
```

### Métriques de distribution
```bash
curl http://localhost:8578/classification/metrics/distribution
```

## 🔄 Migration vers Production

Une fois les tests validés :
1. Arrêter V1 : `docker-compose stop api-classification-service api-classification-lb`
2. Renommer V2 en V1 dans le docker-compose.yml
3. Redéployer sur le port 8577

## ⚠️ Notes Importantes

- **Ne pas modifier V1** pendant les tests de V2
- **Sauvegarder les résultats** de V1 pour comparaison
- **Documenter tous les changements** dans ce fichier
- **Tester avec le même dataset** pour comparaison objective
