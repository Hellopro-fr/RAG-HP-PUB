# 📦 Rapport d'Audit Applicatif - Projet RAG HelloPro

> **Date**: 2026-02-05  
> **Nombre de services**: 76 microservices  
> **Stack principale**: Python + Node.js

---

## 📊 Résumé Exécutif

| Métrique | Valeur | Évaluation |
|----------|--------|------------|
| **Total Dockerfiles** | 76 | - |
| **Services Python** | ~65 | 85% |
| **Services Node.js** | ~9 | 12% |
| **Healthchecks définis** | 5 | 🔴 6.5% seulement |
| **Services avec replicas** | 34 | 🟡 45% |
| **Multi-stage builds** | À vérifier | - |

---

## 🐍 Stack Technique

### Images de Base Utilisées

| Image | Quantité | % | Évaluation |
|-------|----------|---|------------|
| python:3.10-slim | 62 | 82% | ✅ Standard |
| python:3.11-slim | 7 | 9% | ✅ Récent |
| node:20-alpine | 5 | 7% | ✅ LTS |
| node:18-alpine | 2 | 3% | ⚠️ EOL proche |
| vllm/vllm-openai | 2 | 3% | ✅ ML optimisé |
| golang:1.24-alpine | 1 | 1% | ✅ |
| playwright | 1 | 1% | ✅ Testing |

### ⚠️ Points d'Attention Images

| Issue | Impact | Action |
|-------|--------|--------|
| node:18-alpine | EOL Avril 2025 | 🔴 Migrer vers node:20 |
| python:3.10 | Support jusqu'à Oct 2026 | 🟡 Planifier migration |
| Versions non pindées | Reproductibilité | 🟡 Pinder les versions |

---

## 🏥 Healthchecks

### État Actuel

- **Healthchecks définis** : 5 sur 76 services (6.5%)
- **Services sans healthcheck** : 71

### Services avec Healthcheck

| Service | Type |
|---------|------|
| vllm-server | HTTP /health |
| triton-server | HTTP /v2/health/ready |
| elasticsearch | HTTP /_cluster/health |
| deepseek-ocr | HTTP /health |
| (1 autre) | - |

### ✅ Recommandations Healthcheck

1. **Ajouter healthcheck à TOUS les services**
2. Modèle type pour services Python:
```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8xxx/health"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 60s
```

---

## 📈 Scalabilité (Replicas)

### Distribution

| Replicas | Services | Exemples |
|----------|----------|----------|
| 10 | 2 | image-download-service, api-classification |
| 7 | 1 | website-processor-service |
| 5 | 1 | nettoyage-bruit-ocr-service |
| 4 | 8 | devis-processor, classifications, template-llm |
| 2 | 2 | document-echange-processor |
| 1 (default) | 42 | Autres services |

### ⚠️ Points d'Attention Scaling

| Issue | Impact |
|-------|--------|
| 42 services sans replicas explicites | SPOF potentiel |
| Pas de HPA K8s détecté | Scaling manuel |

---

## 🔧 Configuration Services

### Patterns Identifiés

| Pattern | Services | Commentaire |
|---------|----------|-------------|
| gRPC interne | llm-service, embedding-model-service | Ports 5005x |
| REST HTTP | api-*, services web | Ports 8xxx |
| Queue consumers | *-processor-service | RabbitMQ |
| Database connectors | database-*-service | Qdrant/Milvus |

### Variables d'Environnement Communes

- `RABBITMQ_URL` - Message queue
- `REDIS_URL` - Cache/State
- `LLM_SERVICE_URL` - Service LLM interne
- `EMBEDDING_SERVICE_URL` - Embeddings
- `MILVUS_HOST` / `QDRANT_HOST` - Bases vectorielles

---

## 🔒 Sécurité Applicative

### Évaluation

| Critère | État | Action |
|---------|------|--------|
| USER non-root | À vérifier | Auditer Dockerfiles |
| Secrets en .env | Probable | Migrer Secret Manager |
| Volumes montés RW | Présents | Évaluer read-only |
| Network isolation | Partielle | Implémenter NetworkPolicies |

### ⚠️ Points Critiques

1. **Volumes en mode RW** dans plusieurs services de développement
2. **Secrets** probablement en ConfigMaps/env
3. **Pas de scan de vulnérabilités** détecté dans CI

---

## 📋 Services par Catégorie

### APIs REST (15 services)
- api-ingestion-service
- api-recherche-service
- api-chat-llm-service
- api-classification-service (v1 & v2)
- api-embedding-service
- api-gateway-service
- api-transcription-service
- api-html-recherche-service
- api-rest-milvus
- api-check-doublon-produit
- api-question-caracteristique
- graph-rag-api-recherche-service

### Processors/Workers (20+ services)
- devis-processor-service
- echange-processor-service
- website-processor-service
- product-processor-service
- categories-processor-service
- fournisseurs-processor-service
- graph-rag-*-processor (10+ services)
- document-echange-processor-service
- nettoyage-bruit-ocr-service

### ML/AI Services (10 services)
- vllm-server (LLM)
- triton-server (Inference)
- embedding-model-service
- reranking-model-service
- llm-service
- ocr-service
- deepseek-ocr

### Database Connectors (8 services)
- database-recherche-service
- di-database-qdrant-service
- echange-database-qdrant-service
- product-database-qdrant-service
- categories-database-qdrant-service
- fournisseurs-database-qdrant-service
- document-database-qdrant-service
- website-database-qdrant-service

### Frontend/UI (3 services)
- nextjs-formulaire-hp
- redis-client-frontend
- crawler-monitor-frontend

### Infra (5 services)
- dlq-manager-service
- graph-rag-dlq-manager
- crawler-service / crawler-service-python
- webhook-service
- image-download-service

---

## ✅ Plan d'Amélioration

### Priorité HAUTE 🔴
| # | Action |
|---|--------|
| APP-1 | Ajouter healthchecks à tous les services |
| APP-2 | Migrer node:18 → node:20 |
| APP-3 | Scanner vulnérabilités images (Trivy) |

### Priorité MOYENNE 🟡
| # | Action |
|---|--------|
| APP-4 | Pinder toutes les versions d'images |
| APP-5 | Vérifier USER non-root |
| APP-6 | Implémenter liveness/readiness probes K8s |

### Priorité BASSE 🟢
| # | Action |
|---|--------|
| APP-7 | Optimiser images avec multi-stage builds |
| APP-8 | Documenter chaque service (README) |
| APP-9 | Standardiser structure Dockerfile |
