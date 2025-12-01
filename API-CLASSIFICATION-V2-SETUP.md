# 🚀 API Classification V2 - Configuration Complète

## ✅ Ce qui a été fait

### 1. Copie complète du service
- ✅ Dossier `apps-microservices/api-classification-v2` créé
- ✅ Tous les fichiers copiés depuis `api-classification`

### 2. Configuration modifiée
- ✅ **Port**: 8577 → **8578**
- ✅ **Service Docker**: `api-classification-v2-service`
- ✅ **Load Balancer**: `api-classification-v2-lb`
- ✅ **Replicas**: 4 (configuré dans docker-compose.yml)
- ✅ **Version API**: v2.0.0

### 3. Fichiers modifiés

#### `Dockerfile`
- Port exposé: 8578
- Copie depuis `api-classification-v2/`

#### `main.py`
- Titre: "API Classification Produits V2"
- Version: "2.0.0"
- Message: "API Classification Produits v2.0.0 (Test)"

#### `nginx-classification-v2.conf`
- Upstream: `api_classification_v2_backend`
- Backend: `api-classification-v2-service:8578`

#### `docker-compose.yml`
```yaml
api-classification-v2-service:
  - Port interne: 8578
  - Replicas: 4
  - Environment variables configurées

api-classification-v2-lb:
  - Port externe: 8578:80
  - Nginx load balancer
```

## 🔧 Déploiement

### Prérequis
- Docker Desktop démarré
- Fichier `.env` configuré (mêmes variables que V1)

### Option 1: Script automatique (Linux/Mac/WSL)
```bash
cd apps-microservices/api-classification-v2
chmod +x deploy-v2.sh
./deploy-v2.sh
```

### Option 2: Commandes manuelles
```bash
cd c:\Users\USER\Documents\VSCode\RAG-HP-PUB

# Build
docker-compose build api-classification-v2-service api-classification-v2-lb

# Démarrer
docker-compose up -d api-classification-v2-service api-classification-v2-lb

# Vérifier les logs
docker-compose logs -f api-classification-v2-service

# Health check
curl http://localhost:8578/health
```

## 🧪 Tests

### 1. Test rapide
```bash
# Version
curl http://localhost:8578/
# Attendu: {"message": "API Classification Produits v2.0.0 (Test)"}

# Health
curl http://localhost:8578/health

# Status
curl http://localhost:8578/classification/status
```

### 2. Tests complets (Linux/Mac/WSL)
```bash
cd apps-microservices/api-classification-v2
chmod +x test-v2.sh
./test-v2.sh
```

### 3. Comparaison V1 vs V2 (Python)
```bash
cd apps-microservices/api-classification-v2
python compare-v1-v2.py
```

Ce script va :
- Tester V1 et V2 avec les mêmes produits
- Comparer les scores (Score=1 vs Score=0)
- Comparer les temps de traitement
- Générer un rapport détaillé en JSON

## 📊 Endpoints disponibles

### V1 (Production) - Port 8577
- `http://localhost:8577/classification/classify` - Classification simple
- `http://localhost:8577/classification/classify/batch` - Classification batch
- `http://localhost:8577/classification/status` - Status
- `http://localhost:8577/classification/config` - Configuration

### V2 (Test) - Port 8578
- `http://localhost:8578/classification/classify` - Classification simple
- `http://localhost:8578/classification/classify/batch` - Classification batch
- `http://localhost:8578/classification/status` - Status
- `http://localhost:8578/classification/config` - Configuration

## 🔍 Monitoring

### Logs en temps réel
```bash
docker-compose logs -f api-classification-v2-service
```

### Métriques de distribution
```bash
curl http://localhost:8578/classification/metrics/distribution | jq .
```

### État des replicas
```bash
docker-compose ps api-classification-v2-service
```

## 🛠️ Prochaines étapes (Améliorations à tester)

### Phase 1: Quick Wins (à implémenter dans V2)
1. **Reformuler le prompt** (`app/core/classifier.py:270`)
   - Supprimer la mention "liste non exhaustive"
   - Redéfinir Score=0 vs Score=1
   - Ajouter des exemples concrets

2. **Augmenter search_results_limit** (`app/core/classifier.py:41`)
   ```python
   self.search_results_limit = 50  # au lieu de 30
   ```

3. **Augmenter categories_limit** (`app/core/classifier.py:42`)
   ```python
   self.categories_limit = 15  # au lieu de 10
   ```

4. **Augmenter truncation descriptions** (`app/core/classifier.py:176`)
   ```python
   if len(desc) > 400:  # au lieu de 200
       desc = desc[:400] + "..."
   ```

### Phase 2: Optimisations avancées
- Score hybride dans `group_by_category()`
- Seuil minimum `average_score >= 0.70`
- Enrichissement des descriptions avec exemples
- Amélioration sélection des 5 exemples

## 📈 Objectifs de Performance

| Métrique | V1 Actuel | V2 Objectif | V2 Idéal |
|----------|-----------|-------------|----------|
| **Score=1** | 48% | 65-70% | 75-85% |
| **Score=0** | 52% | 30-35% | 15-25% |
| **Erreurs** | <5% | <5% | <3% |
| **Temps/produit** | ~Xs | ±20% | Optimisé |

## 🔄 Migration vers Production

Une fois les tests validés et les objectifs atteints :

```bash
# 1. Arrêter V1
docker-compose stop api-classification-service api-classification-lb

# 2. Renommer V2 en V1 dans docker-compose.yml
# 3. Changer le port de 8578 → 8577

# 4. Redéployer
docker-compose up -d api-classification-service api-classification-lb

# 5. Supprimer V2
docker-compose rm api-classification-v2-service api-classification-v2-lb
```

## 📝 Notes importantes

- ⚠️ **Ne pas modifier V1** pendant les tests de V2
- 💾 **Sauvegarder les résultats** de comparaison
- 📊 **Tester avec le même dataset** pour objectivité
- 🔍 **Documenter tous les changements** dans README_V2.md
- 🚀 **Les deux APIs peuvent tourner en parallèle** (ports différents)

## 🐛 Troubleshooting

### Le service ne démarre pas
```bash
# Vérifier les logs
docker-compose logs api-classification-v2-service

# Reconstruire l'image
docker-compose build --no-cache api-classification-v2-service
```

### Port déjà utilisé
```bash
# Vérifier quel processus utilise le port 8578
netstat -ano | findstr :8578

# Ou changer le port dans docker-compose.yml
```

### Les replicas ne démarrent pas tous
```bash
# Vérifier l'état
docker-compose ps api-classification-v2-service

# Voir les logs de tous les replicas
docker-compose logs --tail=100 api-classification-v2-service
```

## 📚 Documentation

- **README_V2.md** : Documentation détaillée de V2
- **deploy-v2.sh** : Script de déploiement automatique
- **test-v2.sh** : Script de tests automatiques
- **compare-v1-v2.py** : Script de comparaison V1 vs V2

## ✨ Résumé

✅ API Classification V2 est **prête à être déployée**
- Complètement isolée de V1
- Port dédié (8578)
- 4 replicas configurés
- Load balancer nginx
- Scripts de test et comparaison fournis

**Pour démarrer:** Une fois Docker lancé, exécutez `./deploy-v2.sh` ou les commandes manuelles ci-dessus.

**Pour tester les améliorations:** Modifiez les fichiers dans `apps-microservices/api-classification-v2/app/core/classifier.py` puis rebuild et comparez avec V1.
