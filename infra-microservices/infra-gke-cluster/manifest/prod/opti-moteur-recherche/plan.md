# plan.md — Migration Typesense + opti-moteur-front sur GKE

> **Périmètre** : migrer le service de recherche produit (Typesense server + app FastAPI `opti-moteur-front`) de la VM GPU vers le cluster GKE `matching-api-dev-k8s`, avec pipeline CI/CD GitHub Actions automatisé.

---

## 1. Cadre projet

| Item | Valeur |
|---|---|
| Projet GCP | `hellopro-rag-project` |
| Région / Zone | `europe-west1` / `europe-west1-b` |
| Cluster GKE | `matching-api-dev-k8s` (héberge la prod malgré le nom — dette technique tracée) |
| Namespace cible | `moteur-recherche` |
| Branche déclencheur | `features/opti-moteur-front` |
| Path watcher CI | `apps-microservices/opti-moteur-front/**` |
| Artifact Registry | `europe-west1-docker.pkg.dev/hellopro-rag-project/hellopro/` |
| Images cibles | `opti-moteur-front:<sha>` (Typesense server : image upstream `typesense/typesense`, pas de build) |

---

## 2. Objectifs (rappel)

| # | Objectif | Critère de succès |
|---|---|---|
| O1 | Typesense server déployé sur GKE, persistant, connecté à Milvus prod | Pod Running + PVC bound + ingestion 2,24 M produits OK |
| O2 | App `opti-moteur-front` déployée sur GKE, appel embedding service VM GPU OK | `/health` 200, `/search` < 200 ms P95 |
| O3 | Exposition externe sécurisée (front PHP CDN Imperva → Ingress GKE) | TLS managé + Cloud Armor + IP allowlist actives |
| O4 | CI/CD GitHub Actions : push branch + path → build + push + rollout | Workflow vert sur PR test, image promue, pod redéployé |
| O5 | Backup + observabilité prod | Snapshot PVC hebdo + métriques Prometheus + dashboards Grafana |

---

## 3. Découpage en sprints

| Sprint | Objectif | Livrables clés | Effort | Dépendances |
|---|---|---|---|---|
| **S0** | Cadrage documentaire | `plan.md`, `runbook.md`, `etat_avancement.md`, `sprint_XXX.md`, `debug.md`, `CLAUDE.md`, `PENSE_IA.md` | 0,5 j | Validation utilisateur sur les choix d'architecture |
| **S1** | Cadrage infra GKE | namespace, RBAC, NetworkPolicies, secrets vides | 0,5 j | S0, accès `gcloud` + `kubectl` user |
| **S2** | Typesense server prod | StatefulSet + PVC SSD 100 Go + Service ClusterIP + secret API key | 1 j | S1 |
| **S3** | App opti-moteur-front | Deployment + Service + ConfigMap + Secret (Milvus, Typesense, embedding URL) | 1 j | S2, image buildée manuellement une 1ère fois |
| **S4** | Exposition interne (consommateur unique : API Gateway VM GPU) | Service `Internal LoadBalancer` + global access + NetPol ingress restreinte à `10.11.0.2/32` | 0,3 j | S3 |
| **S5** | Pipeline CI/CD | Workflow `cd_opti_moteur_front.yml` (auth WIF ou SA, build, push, rollout) | 1 j | S3 (GKE Service Account configuré) |
| **S6** | Validation + bascule | Tests bout-en-bout, ingestion prod, bascule front, smoke tests | 1 j | S4, S5 |
| **S7** | Backup + observabilité | CronJob snapshot PVC → GCS, ServiceMonitor Prometheus, dashboard Grafana | 0,5 j | S6 |
| **S8** | Rapatriement VM GPU embedding `us-east4`→`europe-west1` (post-migration) | Demande quota GPU GCP, snapshot disque, recréation VM EU, switch DNS/IP, validation latence | 1-2 j | S7 + obtention quota |

**Total estimé** : ~6,5-7,5 jours-homme (S0-S8) après simplification S4 (exposition interne au lieu d'externe). S8 dépend de l'obtention du quota GPU `europe-west1`.

---

## 4. Arbo cible des manifests

```
infra-microservices/infra-gke-cluster/manifest/prod/opti-moteur-recherche/
├── hypothese_option.md
├── plan.md
├── runbook.md
├── etat_avancement.md
├── debug.md
├── CLAUDE.md
├── PENSE_IA.md
├── sprints/
│   ├── sprint_001_cadrage.md
│   ├── sprint_002_typesense_server.md
│   ├── sprint_003_opti_moteur_front.md
│   ├── sprint_004_exposition_externe.md
│   ├── sprint_005_cicd.md
│   ├── sprint_006_validation.md
│   └── sprint_007_backup_observabilite.md
└── manifests/
    ├── 00-namespace.yaml
    ├── 01-rbac.yaml
    ├── 02-network-policies.yaml
    ├── 10-typesense-secret.yaml
    ├── 11-typesense-pvc.yaml
    ├── 12-typesense-statefulset.yaml
    ├── 13-typesense-service.yaml
    ├── 20-opti-moteur-secret.yaml
    ├── 21-opti-moteur-configmap.yaml
    ├── 22-opti-moteur-deployment.yaml
    ├── 23-opti-moteur-service.yaml
    ├── 30-managed-certificate.yaml
    ├── 31-backendconfig-cloudarmor.yaml
    ├── 32-ingress.yaml
    └── 40-backup-cronjob.yaml
```

---

## 5. Risques identifiés

| Risque | Criticité | Mitigation |
|---|---|---|
| Cluster nommé `-dev` héberge la prod (confusion ops) | Moyenne | Tracé dans `debug.md` § dette technique, à renommer à terme |
| Embedding service reste sur VM GPU (SPOF) | Haute | Documenté ; migration GKE prévue hors périmètre, latence VPC à mesurer |
| Push direct prod depuis branche feature | Haute | Ajouter GitHub Environment `production` + required reviewers (S5) |
| Re-ingestion 2,24 M produits longue (1ère ingestion) | Moyenne | Job d'ingestion dédié, hors heures pic, suivi via logs |
| Drift `EMBEDDING_SERVICE_URL` (env var hors BaseSettings) | Basse | Refactor optionnel post-migration, non bloquant |
| Coût PVC SSD 100 Go (~17 €/mois) | Basse | Tagging FinOps + revue mensuelle |

---

## 6. Validation utilisateur — points de gate

Le projet avance sprint par sprint. Validation utilisateur **obligatoire** avant de passer au sprint suivant :

1. ✅ Validation de ce `plan.md` (étape actuelle)
2. ⏳ Validation de `runbook.md` global (prochaine étape)
3. ⏳ Validation `sprint_001` puis exécution avant `sprint_002`, etc.

---

## 7. Hors périmètre (explicite)

- Migration de `api-embedding-service` vers GKE (sera traitée au S8)
- **Re-ingestion catalogue Typesense** : à la charge des devs (D16). DevSecOps livre infra + secrets + endpoints
- Refactor de l'app Python (tests unitaires, refactor `os.getenv` → BaseSettings) — séparé
- Mise en place ArgoCD / GitOps — pattern actuel = `kubectl set image` direct
- Renommage cluster GKE `-dev` → `-prod`
- Modification de l'API Gateway HelloPro `api.hellopro.eu` (upstream switch sera fait par devs au S6)
