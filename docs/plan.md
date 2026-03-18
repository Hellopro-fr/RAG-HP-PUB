# 📋 Plan de Travail Global - Projet RAG HelloPro GCP

> **Version**: 1.3 (Post-remediation urgences securite)
> **Date**: 2026-03-18
> **Auteur**: DevSecOps / Cloud SRE Architect
> **Statut Global**: Phase 3 En Cours (40%)

---

## 🎯 Objectif Global

Mettre en conformité et fiabiliser l'infrastructure GCP du projet RAG HelloPro avec :
- Architecture résiliente sur 2 environnements (DEV / PROD) + futur PREPROD
- Pipeline CI/CD DevSecOps complet
- Documentation exhaustive et exploitable
- Optimisation FinOps

---

## 📊 Vue Synthétique du Projet

| Élément | État Actuel |
|---------|-------------|
| **Cluster GKE** | 4 nodes c2-standard-8 (32GB RAM) |
| **Services K8s** | Milvus, Qdrant, 1x RabbitMQ (v3), Redis, Prometheus |
| **VM GPU** | g2-standard-24 (2xL4, 96GB) - via Console |
| **VM Manager** | Bastion/Manager |
| **Microservices** | ~76 services (docker-compose) |
| **Terraform** | ✅ Centralisé, Modulaire, State PROD prêt |
| **Securite** | 🔄 Score ~55-60%. Redis/RabbitMQ securises. Reste: Qdrant DEV, Cloud NAT, IAM, Secrets |

---

## 🗂️ Structure Documentaire

```
docs/
├── plan.md                          # Ce fichier - Plan global
├── etat_avancement.md               # Suivi quotidien des tâches
├── guide_execution_terraform.md     # Guide des opérations TF
├── inventaire/
│   ├── inventaire_gcp.md            # Inventaire ressources GCP
│   ├── mapping_tf_gcp.md            # Correspondance Terraform <-> GCP
├── audit/
│   ├── rapport_audit_infra.md       # Audit infrastructure (65%)
│   ├── rapport_audit_securite.md    # Audit sécurité (35% CRITIQUE)
│   ├── rapport_audit_applicatif.md  # Audit applicatif (76 services)
│   ├── recommendations_finops.md    # Recommandations FinOps
├── phases/
│   ├── phase1_diagnostic.md         # Phase 1 - Analyse & Diagnostic
│   ├── phase2_terraform.md          # Phase 2 - Refactoring Terraform
│   ├── phase3_securisation.md       # Phase 3 - Sécurisation
│   ├── phase4_cicd.md               # Phase 4 - CI/CD DevSecOps
├── runbooks/
│   ├── gcp_authentication.md        # Authentification GCP
│   ├── security_remediation.md      # Remédiation sécurité urgences
│   ├── deployment.md                # Procédure de déploiement
│   ├── gpu_vm_scheduling.md         # Gestion start/stop GPU VM
│   ├── incident_response.md         # Playbook incidents sécurité
```

---

## 📅 Phases du Projet

### 🔍 Phase 1 : Diagnostic & Audit (Semaine 1-2)

| ID | Étape | Livrable | Priorité | Status |
|----|-------|----------|----------|--------|
| 1.1 | Inventaire ressources GCP | `inventaire_gcp.md` | 🔴 Haute | ✅ Fait |
| 1.2 | Mapping Terraform ↔ GCP | `mapping_tf_gcp.md` | 🔴 Haute | ✅ Fait |
| 1.3 | Audit infrastructure | `rapport_audit_infra.md` | 🔴 Haute | ✅ Fait |
| 1.4 | Audit sécurité | `rapport_audit_securite.md` | 🔴 Haute | ✅ Fait |
| 1.5 | Audit code applicatif | `rapport_audit_applicatif.md` | 🟡 Moyenne | ✅ Fait |
| 1.6 | Recommandations FinOps | `recommendations_finops.md` | 🟡 Moyenne | ✅ Fait |

### 🔧 Phase 2 : Refactoring Terraform (Semaine 3-4)

| ID | Étape | Description | Priorité | Status |
|----|-------|-------------|----------|--------|
| 2.1 | Restructuration modules Terraform | Centralisation root + modules | 🔴 Haute | ✅ Fait |
| 2.2 | Import ressources existantes | Migration State DEV | 🔴 Haute | ✅ Fait |
| 2.3 | Séparation environnements | Estruct. `environments/dev & prod` | 🔴 Haute | ✅ Fait |
| 2.4 | Standardisation naming | Variables dynamiques (env) | 🟡 Moyenne | ✅ Fait |
| 2.5 | Documentation modules | `guide_execution_terraform.md` | 🟡 Moyenne | ✅ Fait |

### 🔒 Phase 3 : Sécurisation (Semaine 5-8)

> **Détails** : `docs/phases/phase3_securisation.md`

#### 3.0 - Pré-requis : Urgences & Consolidation Terraform

| ID | Étape | Description | Priorité | Status |
|----|-------|-------------|----------|--------|
| 3.0.1 | Runbook urgences securite | Redis, RabbitMQ, RDP, credentials | 🔴 Critique | ✅ Fait |
| 3.0.2 | Execution urgences securite | SEC-1,2,3,10 executes + rapport | 🔴 Critique | ✅ Fait (03/18) |
| 3.0.3 | Consolidation racines Terraform | Modules crees et commentes dans main.tf | 🔴 Haute | ✅ Fait (code) |
| 3.0.4 | Correction ssh_allowed_ips | infra-ci-cd/terraform/variables.tf -> IAP | 🔴 Haute | ✅ Fait |
| 3.0.5 | Nettoyage state orphelin | terraform state rm x 24 ressources | 🔴 Haute | ⬜ A faire |

#### 3.1 - Sécurisation Réseau

| ID | Étape | Description | Priorité | Status |
|----|-------|-------------|----------|--------|
| 3.1.1 | Module Cloud NAT | `modules/cloud_nat/` sur hellopro-dev-vpc | 🔴 Haute | ⬜ À faire |
| 3.1.2 | Suppression IP publique VM GPU | Retirer IP externe, accès IAP uniquement | 🔴 Haute | ⬜ À faire |
| 3.1.3 | Migration Redis vers ILB | Deja fait : ILB `10.0.1.220` + AUTH active | 🔴 Haute | ✅ Deja fait |
| 3.1.4 | Migration Qdrant vers ILB | PROD OK (ILB). DEV a verifier (`34.52.142.50`) | 🔴 Haute | 🔄 En cours |
| 3.1.5 | Migration RabbitMQ vers ILB | Deja fait : 1 instance `rabbitmq-v3` ILB `10.0.1.216` | 🔴 Haute | ✅ Deja fait |
| 3.1.6 | Health checks ILB | Décommenter lignes 48-55 modules/internal_lb | 🟡 Moyenne | ⬜ À faire |
| 3.1.7 | K8s Network Policies | Isoler Redis, RabbitMQ, Milvus, Qdrant | 🟡 Moyenne | ⬜ À faire |

#### 3.2 - IAM & Secrets

| ID | Étape | Description | Priorité | Status |
|----|-------|-------------|----------|--------|
| 3.2.1 | Workload Identity GKE | Modifier modules/gke_cluster + K8s SA | 🔴 Haute | ⬜ À faire |
| 3.2.2 | Module Secret Manager | rabbitmq, redis, jwt, milvus credentials | 🔴 Haute | ⬜ À faire |
| 3.2.3 | External Secrets Operator | Installation sur GKE | 🟡 Moyenne | ⬜ À faire |
| 3.2.4 | SA dédiés par service | Remplacer SA par défaut compute@ | 🟡 Moyenne | ⬜ À faire |
| 3.2.5 | Rotation credentials par defaut | JWT renforce, ADMIN_KEY deja OK, RabbitMQ OK | 🔴 Haute | ✅ Fait (03/18) |

#### 3.3 - Sécurisation Applicative

| ID | Étape | Description | Priorité | Status |
|----|-------|-------------|----------|--------|
| 3.3.1 | CORS restrictif | Remplacer allow_origins=["*"] | 🟡 Moyenne | ⬜ À faire |
| 3.3.2 | Healthchecks (71 services) | Ajouter /health + HEALTHCHECK Docker | 🟡 Moyenne | ⬜ À faire |
| 3.3.3 | Validation gRPC | Pydantic + proto validation | 🟢 Basse | ⬜ À faire |

### 🚀 Phase 4 : Pipeline DevSecOps (Semaine 9-11)

> **Détails** : `docs/phases/phase4_cicd.md`

| ID | Étape | Description | Priorité | Status |
|----|-------|-------------|----------|--------|
| 4.1 | Corriger workflows GH Actions existants | Bug secret typo, tag mismatch × 13 CD | 🔴 Haute | ⬜ À faire |
| 4.2 | Workflows réutilisables | _reusable-ci.yml, _reusable-cd-cloudrun.yml, _reusable-cd-vm.yml | 🔴 Haute | ⬜ À faire |
| 4.3 | Scans sécurité CI | Trivy, Bandit, gitleaks, Snyk | 🔴 Haute | ⬜ À faire |
| 4.4 | Pipeline Terraform | Plan sur PR, Apply sur merge, WIF auth | 🔴 Haute | ⬜ À faire |
| 4.5 | Pipeline déploiement | CloudRun + VM (deploy-to-vm.sh amélioré) | 🔴 Haute | ⬜ À faire |
| 4.6 | Environnement PREPROD | Parité avec PROD | 🟢 Basse | ⬜ À faire |

### 📊 Phase 5 : Observabilité, FinOps & Documentation (Semaine 11-13)

| ID | Étape | Description | Priorité | Status |
|----|-------|-------------|----------|--------|
| 5.1 | Prometheus couverture complète | Étendre de 15 à 48+ services + exporters | 🔴 Haute | ⬜ À faire |
| 5.2 | Grafana dashboards | System overview, RabbitMQ, Vector DB, GPU, FinOps | 🔴 Haute | ⬜ À faire |
| 5.3 | Alerting | GKE CPU, RabbitMQ queue, healthcheck, disk | 🔴 Haute | ⬜ À faire |
| 5.4 | GPU VM scheduling | Auto stop/start pour économie ~$1,000/mois | 🟡 Moyenne | ⬜ À faire |
| 5.5 | Cleanup ressources | VM terminée, IPs orphelines, state TF | 🟡 Moyenne | ⬜ À faire |
| 5.6 | Runbooks opérationnels | Déploiement, GPU, incidents, sécurité | 🔴 Haute | 🔄 En cours |
| 5.7 | Documentation architecture | Schémas réseau post-sécurisation | 🔴 Haute | ⬜ À faire |
| 5.8 | Formation équipe | Transfert de compétences | 🟡 Moyenne | ⬜ À faire |

---

## 🚦 Légende Status
- ✅ Fait : Terminé et validé
- 🔄 En Cours : Démarré
- ⬜ À faire : Pas encore démarré
