# 🚀 Classification Batch Distribuée

## Vue d'ensemble

L'endpoint `/classification/classify/batch/distributed` permet de classifier un grand nombre de produits en exploitant **tous les replicas** du service de classification, offrant ainsi une accélération significative du traitement.

---

## 📊 Comparaison des performances

| Méthode | Endpoint | Utilisation des replicas | Vitesse relative |
|---------|----------|-------------------------|------------------|
| **Standard** | `/classify/batch` | 1 seul replica | 1x (baseline) |
| **Distribuée** | `/classify/batch/distributed` | 20 replicas | ~20x plus rapide |

### Exemple concret

**Traitement de 100 produits :**
- Méthode standard : ~200 secondes (tous sur 1 replica)
- Méthode distribuée : ~10 secondes (5 produits par replica × 20 replicas)

---

## 🎯 Comment ça fonctionne

### Architecture

```
Client
  ↓
  Envoie 100 produits → /classify/batch/distributed
  ↓
  Service divise automatiquement
  ├→ Sous-batch 1 (5 produits) → Replica 1
  ├→ Sous-batch 2 (5 produits) → Replica 2
  ├→ Sous-batch 3 (5 produits) → Replica 3
  ├→ ...
  └→ Sous-batch 20 (5 produits) → Replica 20
  ↓
  Tous les replicas traitent en PARALLÈLE
  ↓
  Agrégation des résultats
  ↓
  Retour au client avec résultats complets
```

### Logique de division

Le service divise intelligemment selon le nombre de produits :

```python
nombre_replicas_utilises = min(CLASSIFICATION_NUM_REPLICAS, nombre_produits)
taille_sous_batch = ceil(nombre_produits / nombre_replicas_utilises)
```

**Exemples :**
- **100 produits** → 20 sous-batches de 5 produits
- **50 produits** → 20 sous-batches de 3 produits (10 replicas avec 2 produits)
- **10 produits** → 10 sous-batches de 1 produit (10 replicas utilisés)
- **2 produits** → 2 sous-batches de 1 produit (2 replicas utilisés)

---

## 🔌 Utilisation de l'API

### Endpoint

```
POST /classification/classify/batch/distributed
```

### Format de requête

**Identique à `/classify/batch` standard :**

```json
{
  "produits": [
    {
      "id_produit": "12345",
      "nom_produit": "Perceuse électrique Bosch",
      "description": "Perceuse électrique professionnelle 750W avec mandrin automatique",
      "id_categorie_attendue": "cat_123"
    },
    {
      "id_produit": "12346",
      "nom_produit": "Marteau-piqueur pneumatique",
      "description": "Marteau-piqueur industriel 25kg pour travaux de démolition"
    }
    // ... jusqu'à 100 produits
  ],
  "llm": "Qwen",
  "enable_thinking": false
}
```

### Format de réponse

```json
{
  "total_produits": 100,
  "success_count": 98,
  "error_count": 2,
  "resultats": [
    {
      "id_produit": "12345",
      "titre_produit": "Perceuse électrique Bosch",
      "description_produit": "Perceuse électrique professionnelle 750W...",
      "status": "SUCCESS",
      "id_categorie": "cat_456",
      "nom_categorie": "Outils Électriques",
      "score_llm": 1,
      "processing_time": 2.34,
      "llm_type": "Qwen",
      "enable_thinking": false,
      "llm_response": [...]
    },
    // ... 99 autres résultats
  ],
  "llm_type": "Qwen",
  "processing_time_total": 12.45
}
```

---

## ⚙️ Configuration

### Variables d'environnement

Configurées dans [docker-compose.yml](../../docker-compose.yml#L346-L350) :

```yaml
environment:
  - CLASSIFICATION_SERVICE_NAME=api-classification-service
  - CLASSIFICATION_SERVICE_PORT=8577
  - CLASSIFICATION_NUM_REPLICAS=20
```

| Variable | Valeur par défaut | Description |
|----------|-------------------|-------------|
| `CLASSIFICATION_SERVICE_NAME` | `api-classification-service` | Nom du service Docker |
| `CLASSIFICATION_SERVICE_PORT` | `8577` | Port du service |
| `CLASSIFICATION_NUM_REPLICAS` | `20` | Nombre de replicas disponibles |

### Nombre de replicas

Le nombre de replicas est défini dans [docker-compose.yml](../../docker-compose.yml#L356) :

```yaml
deploy:
  replicas: 20
```

**Pour modifier le nombre de replicas :**

1. Modifier `replicas: 20` dans docker-compose.yml
2. Mettre à jour `CLASSIFICATION_NUM_REPLICAS=20` pour correspondre
3. Redéployer : `docker-compose up -d --scale api-classification-service=20`

---

## 🧪 Exemples de code

### Python avec requests

```python
import requests

products = [
    {
        "id_produit": f"prod_{i}",
        "nom_produit": f"Produit {i}",
        "description": f"Description du produit {i}"
    }
    for i in range(100)
]

response = requests.post(
    "http://localhost:8577/classification/classify/batch/distributed",
    json={
        "produits": products,
        "llm": "Qwen",
        "enable_thinking": False
    },
    timeout=300  # 5 minutes max
)

result = response.json()
print(f"✅ {result['success_count']} produits classifiés en {result['processing_time_total']:.2f}s")
print(f"❌ {result['error_count']} erreurs")
```

### Python avec httpx (async)

```python
import httpx
import asyncio

async def classify_batch():
    products = [...]  # Liste de 100 produits

    async with httpx.AsyncClient(timeout=300) as client:
        response = await client.post(
            "http://localhost:8577/classification/classify/batch/distributed",
            json={"produits": products, "llm": "Qwen"}
        )
        return response.json()

result = asyncio.run(classify_batch())
```

### Curl

```bash
curl -X POST "http://localhost:8577/classification/classify/batch/distributed" \
  -H "Content-Type: application/json" \
  -d '{
    "produits": [
      {
        "id_produit": "12345",
        "nom_produit": "Perceuse électrique",
        "description": "Perceuse 750W"
      }
    ],
    "llm": "Qwen",
    "enable_thinking": false
  }'
```

---

## 📈 Logs et monitoring

### Logs de distribution

Le service affiche des logs détaillés pour chaque distribution :

```
INFO - 📦 Distribution de 100 produits sur 20 replicas (5 produits/replica)
INFO -   → Envoi du sous-batch 1/20 (5 produits) à http://api-classification-service:8577/classification/classify/batch
INFO -   → Envoi du sous-batch 2/20 (5 produits) à http://api-classification-service:8577/classification/classify/batch
...
INFO -   ✅ Sous-batch 1 terminé : 5 succès, 0 erreurs
INFO -   ✅ Sous-batch 2 terminé : 4 succès, 1 erreurs
...
INFO - ✅ Distribution terminée en 12.45s : 98 succès, 2 erreurs
```

### Visualiser les logs

```bash
# Logs d'un replica spécifique
docker logs rag-hp-pub-api-classification-service-1

# Logs de tous les replicas en temps réel
docker-compose logs -f api-classification-service

# Filtrer les logs de distribution
docker-compose logs api-classification-service | grep "Distribution"
```

---

## 🔧 Dépannage

### Problème : Timeout

**Symptôme :** `HTTPError: Request timeout`

**Solution :**
- Augmenter le timeout dans le code client (défaut: 300s)
- Vérifier que tous les replicas sont actifs : `docker-compose ps api-classification-service`

### Problème : Certains sous-batches échouent

**Symptôme :** `error_count > 0` dans la réponse

**Solution :**
- Vérifier les logs : `docker-compose logs api-classification-service | grep "❌"`
- Vérifier la disponibilité du LLM service
- Réessayer avec un batch plus petit

### Problème : Pas de distribution (1 seul replica utilisé)

**Symptôme :** Performance identique à `/classify/batch`

**Solution :**
1. Vérifier le nombre de replicas actifs :
   ```bash
   docker-compose ps api-classification-service
   ```
2. Vérifier les variables d'environnement :
   ```bash
   docker exec rag-hp-pub-api-classification-service-1 env | grep CLASSIFICATION
   ```

---

## 🎛️ Quand utiliser quelle méthode ?

| Cas d'usage | Endpoint recommandé | Raison |
|-------------|---------------------|--------|
| **1-10 produits** | `/classify/batch` | Overhead de distribution non nécessaire |
| **10-100 produits** | `/classify/batch/distributed` | Gain de performance significatif |
| **Plusieurs batches** | `/classify/batch/distributed` | Meilleure utilisation des ressources |
| **Latence critique** | `/classify/batch/distributed` | Temps de réponse minimal |

---

## 💡 Optimisations futures

Possibilités d'amélioration :

1. **Load balancing intelligent**
   - Tenir compte de la charge actuelle de chaque replica
   - Distribuer en fonction des capacités GPU disponibles

2. **Retry automatique**
   - Réessayer automatiquement les sous-batches en échec
   - Redistribuer sur d'autres replicas en cas d'erreur

3. **Cache partagé**
   - Mettre en cache les résultats de recherche similaire
   - Partager le cache entre replicas via Redis

4. **Streaming des résultats**
   - Retourner les résultats au fur et à mesure
   - Via WebSocket ou Server-Sent Events

---

## 📚 Références

- Code source : [classification.py](app/router/classification.py#L343-L505)
- Configuration Docker : [docker-compose.yml](../../docker-compose.yml#L333-L363)
- Documentation API standard : [README.md](README.md)

---

**Date de création :** 2025-01-31
**Version :** 1.0
**Auteur :** Claude Assistant
