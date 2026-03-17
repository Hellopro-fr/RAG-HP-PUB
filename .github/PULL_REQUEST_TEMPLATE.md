## Description
<!-- Décrivez les changements apportés dans cette PR -->

## Type de changement
- [ ] 🐛 Bug fix (changement non-breaking qui corrige un problème)
- [ ] ✨ Nouvelle fonctionnalité (changement non-breaking qui ajoute une fonctionnalité)
- [ ] 💥 Breaking change (correction ou fonctionnalité qui casse la compatibilité)
- [ ] 📝 Documentation uniquement
- [ ] 🔧 Configuration / Infrastructure CI/CD

## Service(s) impacté(s)
<!-- Cochez les services concernés par cette PR -->

**Services API :**
- [ ] api-gateway
- [ ] api-html-recherche
- [ ] api-model-service
- [ ] api-recherche-service
- [ ] api-embedding-service
- [ ] api-chat-llm-service
- [ ] api-transcription-service
- [ ] api-classification
- [ ] api-classification-v2
- [ ] api-rest-milvus
- [ ] api-check-doublon-produit
- [ ] api-ingestion-service

**Services ML/AI (GPU) :**
- [ ] vllm-server
- [ ] triton-server
- [ ] ocr-service
- [ ] deepseek-ocr
- [ ] llm-service
- [ ] embedding-model-service
- [ ] reranking-model-service

**Services Processor :**
- [ ] devis-processor-service
- [ ] echange-processor-service
- [ ] website-processor-service
- [ ] product-processor-service
- [ ] categories-processor-service
- [ ] fournisseurs-processor-service
- [ ] document-echange-processor-service
- [ ] template-llm-service

**Services Database :**
- [ ] database-recherche-service
- [ ] di-database-qdrant-service
- [ ] echange-database-qdrant-service
- [ ] website-database-qdrant-service
- [ ] product-database-qdrant-service
- [ ] categories-database-qdrant-service
- [ ] fournisseurs-database-qdrant-service
- [ ] document-database-qdrant-service

**Autres services :**
- [ ] webhook-service
- [ ] optimize-service
- [ ] deepseek-metrics-collector-service
- [ ] nettoyage-bruit-ocr-service
- [ ] embedding-service

**Frontend / UI :**
- [ ] api-chatbot-service
- [ ] redis-client-frontend
- [ ] crawler-monitor-frontend
- [ ] crawler-monitor-backend

**Infrastructure / Monitoring :**
- [ ] elasticsearch
- [ ] kibana
- [ ] prometheus
- [ ] grafana
- [ ] crawler-service

**Autre :**
- [ ] Autre : _____________

## Environnement cible
<!-- Vers quelle branche / environnement cette PR sera mergée -->
- [ ] features/poc → POC
- [ ] develop → Development
- [ ] preprod → Pre-production
- [ ] prod → Production

## Checklist

**Code quality :**
- [ ] Le code respecte les standards du projet (PEP8 pour Python, etc.)
- [ ] Les fonctions complexes sont commentées
- [ ] Pas de code commenté inutile (dead code)
- [ ] Les variables et fonctions ont des noms explicites

**Tests :**
- [ ] J'ai testé localement (docker build + run)
- [ ] Les tests unitaires passent (`pytest`)
- [ ] J'ai ajouté des tests pour les nouvelles fonctionnalités
- [ ] La couverture de code est satisfaisante (>70%)

**Documentation :**
- [ ] README mis à jour si nécessaire
- [ ] Documentation API mise à jour (OpenAPI/Swagger)
- [ ] Commentaires explicatifs ajoutés pour code complexe

**Dépendances :**
- [ ] `requirements.txt` mis à jour si nouvelles dépendances
- [ ] Versions des dépendances fixées (pas de `package>=x.y`)
- [ ] Aucune dépendance avec vulnérabilités connues

**Base de données :**
- [ ] Migrations de DB incluses (si applicable)
- [ ] Scripts de migration testés
- [ ] Rollback de migration documenté

**Configuration :**
- [ ] Variables d'environnement documentées
- [ ] Valeurs par défaut définies
- [ ] Secrets gérés via Secret Manager (pas hardcodés)

**Docker :**
- [ ] Dockerfile optimisé (multi-stage si possible)
- [ ] `.dockerignore` à jour
- [ ] Image build réussit sans erreurs
- [ ] Taille de l'image raisonnable

**Sécurité :**
- [ ] Pas de secrets dans le code
- [ ] Validation des inputs utilisateur
- [ ] Pas de failles SQL injection / XSS
- [ ] Scan de sécurité passé (Semgrep, Bandit)

## Tests effectués

<!-- Décrivez les tests manuels ou automatisés que vous avez effectués -->

**Tests unitaires :**
```bash
# Commandes exécutées
pytest tests/ --cov
```

**Tests d'intégration :**
```bash
# Comment avez-vous testé ?
docker-compose up -d api-gateway
curl http://localhost:8500/health
```

**Tests de charge (si applicable) :**
```
# Résultats des tests de performance
```

## Screenshots / Logs

<!-- Si applicable, ajoutez des screenshots ou logs montrant le fonctionnement -->

<details>
<summary>Logs de test</summary>

```
Coller vos logs ici
```

</details>

## Impact sur les performances

<!-- Est-ce que cette PR impacte les performances ? -->
- [ ] Aucun impact
- [ ] Amélioration des performances
- [ ] Dégradation acceptable (justifier)
- [ ] Optimisation nécessaire (créer issue)

## Breaking changes

<!-- Si cette PR contient des breaking changes, listez-les ici -->
- [ ] Aucun breaking change
- [ ] Breaking changes (détailler ci-dessous) :

```
Lister les breaking changes et migration path
```

## Dépendances

<!-- Cette PR dépend-elle d'autres PRs ou changements ? -->
- [ ] Aucune dépendance
- [ ] Dépend de : #XXX (lien vers PR/issue)

## Rollback plan

<!-- Comment rollback si cette PR cause des problèmes en production ? -->

```bash
# Commandes de rollback
./infra-ci-cd/scripts/rollback.sh <service-name> <environment>
```

## Notes pour le reviewer

<!-- Informations supplémentaires pour faciliter la review -->

**Points d'attention :**
- 
- 

**Questions ouvertes :**
- 
-
