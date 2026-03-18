# 🔍 Rapport d'Audit Infrastructure - Projet RAG HelloPro GCP

> **Date**: 2026-02-05  
> **Niveau de criticité global**: 🟡 MOYEN  
> **Auditeur**: DevSecOps / Cloud SRE Architect

---

## 📊 Résumé Exécutif

| Domaine | Score | Commentaire |
|---------|-------|-------------|
| **Compute** | 🟡 65% | VM GPU hors TF, sizing à optimiser |
| **Réseau** | 🟡 60% | VPC bien structuré mais firewall permissives |
| **GKE** | 🟢 75% | Cluster opérationnel mais améliorations possibles |
| **Stockage** | 🟡 50% | Buckets GCS non visibles, lifecycle à vérifier |
| **Monitoring** | 🟡 60% | Prometheus présent, alerting à renforcer |
| **Résilience** | 🟡 55% | Backup Milvus OK, DR à compléter |

---

## 💻 Audit Compute

### VMs Identifiées

| VM | Type | Zone | Rôle | Évaluation |
|----|------|------|------|------------|
| manager-vm-dev | e2-small | eu-west1-b | Bastion | ✅ Approprié |
| gke-matching-api-dev-* (x4) | c2-standard-8 | eu-west1-b | GKE nodes | ✅ Approprié |
| vm-embedding-g2-std-24 | g2-standard-24 | eu-west1-c | TERMINATED | ⚠️ À supprimer |
| vm-embedding-g2-std-24-use | g2-standard-24 | us-east4-c | GPU PROD | 🔴 Latence cross-région |

### ⚠️ Points d'Attention

1. **VM GPU en us-east4-c** : Latence réseau avec GKE en europe-west1-b
2. **VM Terminée** : Ressource inutilisée à nettoyer
3. **Coût GPU** : g2-standard-24 ≈ $2500/mois

### ✅ Recommandations Compute

| # | Action | Priorité | Impact |
|---|--------|----------|--------|
| C1 | Supprimer vm-embedding-g2-std-24 (TERMINATED) | 🟢 Basse | Clarté |
| C2 | Évaluer migration VM GPU vers europe | 🟡 Moyenne | Latence |
| C3 | Ajouter scheduling GPU (shutdown nuit) | 🟡 Moyenne | FinOps |

---

## 🌐 Audit Réseau

### VPC Architecture

```
hellopro-dev-vpc (CUSTOM)
├── europe-west1
│   ├── hellopro-subnet-dev (10.0.1.0/24) - GKE, VMs
│   ├── proxy-subnet (10.0.125.0/24) - Managed Proxy
│   └── gke-...-pe-subnet (10.80.243.0/28) - Private Endpoint
├── europe-west2
│   └── hellopro-subnet-dev-w2 (10.0.35.0/24) - Réservé
├── europe-west3
│   └── hellopro-subnet-dev-w3 (10.0.25.0/24) - Réservé
├── europe-west4  
│   └── hellopro-subnet-dev-w4 (10.0.21.0/24) - Réservé
├── europe-west6
│   └── hellopro-subnet-dev-w6 (10.0.30.0/24) - Réservé
└── us-east4
    └── subnet-us-central1 (10.11.0.0/20) - VM GPU
```

### ⚠️ Points d'Attention Réseau

| # | Issue | Criticité |
|---|-------|-----------|
| N1 | Subnet us-east4 non géré par TF | 🟡 Moyen |
| N2 | CIDR overlap potentiel dev/prod (10.0.1.0/24) | 🟡 Moyen |
| N3 | 5 subnets réservés non utilisés | 🟢 Bas |
| N4 | Pas de Cloud NAT détecté | 🟡 Moyen |

### ✅ Recommandations Réseau

| # | Action | Priorité | Impact |
|---|--------|----------|--------|
| N1 | Déclarer subnet us-east4 dans TF | 🔴 Haute | IaC |
| N2 | Planifier CIDR dédié pour PROD | 🟡 Moyenne | Isolation |
| N3 | Évaluer suppression subnets inutilisés | 🟢 Basse | Clarté |
| N4 | Configurer Cloud NAT | 🟡 Moyenne | Sécurité |

---

## ☸️ Audit GKE

### Configuration Cluster

| Paramètre | Valeur | Évaluation |
|-----------|--------|------------|
| **Nom** | matching-api-dev-k8s | ✅ |
| **Zone** | europe-west1-b | ⚠️ Zonal (pas regional) |
| **Nodes** | 4 | ✅ |
| **Machine Type** | c2-standard-8 | ✅ |
| **Network** | hellopro-dev-vpc | ✅ |

### ⚠️ Points d'Attention GKE

| # | Issue | Criticité |
|---|-------|-----------|
| G1 | Cluster zonal (pas regional) | 🟡 Moyen |
| G2 | Version K8s à vérifier (support) | 🟡 Moyen |
| G3 | Workload Identity à vérifier | 🟡 Moyen |
| G4 | Pas de node autoscaling détecté | 🟡 Moyen |

### ✅ Recommandations GKE

| # | Action | Priorité | Impact |
|---|--------|----------|--------|
| G1 | Évaluer migration vers cluster regional | 🟡 Moyenne | HA |
| G2 | Vérifier et mettre à jour version K8s | 🔴 Haute | Support |
| G3 | Activer Workload Identity | 🟡 Moyenne | Sécurité |
| G4 | Configurer Cluster Autoscaler | 🟡 Moyenne | FinOps |

---

## 💾 Audit Stockage

### État Actuel

| Type | Quantité | État |
|------|----------|------|
| Buckets GCS | 0 visible | ⚠️ Droits insuffisants |
| PVC K8s | Milvus data | ✅ Présent |
| Artifact Registry | 1 (hellopro) | ✅ |

### ✅ Recommandations Stockage

| # | Action | Priorité |
|---|--------|----------|
| S1 | Vérifier buckets GCS avec droits admin | 🟡 Moyenne |
| S2 | Documenter politique lifecycle GCS | 🟡 Moyenne |
| S3 | Vérifier backup PVC Milvus | 🔴 Haute |

---

## 📈 Audit Monitoring

### État Actuel

- **Prometheus** : Déployé sur GKE
- **Métriques exposées** : Milvus (9091), général (9090)
- **Alerting** : À vérifier

### ✅ Recommandations Monitoring

| # | Action | Priorité |
|---|--------|----------|
| M1 | Configurer Cloud Monitoring/Operations | 🟡 Moyenne |
| M2 | Définir alertes SLO/SLI | 🟡 Moyenne |
| M3 | Centraliser logs (Cloud Logging) | 🟡 Moyenne |

---

## 🔄 Audit Résilience

### État Actuel

| Composant | Backup | DR |
|-----------|--------|-------|
| Milvus | ✅ GCS (CronJob) | 🟡 En cours |
| VM GPU | ❌ Non configuré | ❌ |
| GKE config | ⚠️ Manifest only | ⚠️ |
| Secrets | ⚠️ À vérifier | ⚠️ |

### ✅ Recommandations Résilience

| # | Action | Priorité |
|---|--------|----------|
| R1 | Finaliser restore Milvus (Phase 3) | 🔴 Haute |
| R2 | Configurer snapshot VM GPU | 🟡 Moyenne |
| R3 | Versionner tous manifests K8s | 🟡 Moyenne |
| R4 | Documenter procédure DR | 🔴 Haute |

---

## 📋 Synthèse des Actions

### Priorité HAUTE 🔴
1. Vérifier version GKE et planifier upgrade si nécessaire
2. Finaliser restore Milvus
3. Documenter procédure DR

### Priorité MOYENNE 🟡
4. Déclarer subnet us-east4 dans Terraform
5. Configurer Cloud NAT
6. Activer Workload Identity
7. Configurer Cluster Autoscaler

### Priorité BASSE 🟢
8. Supprimer VM terminée
9. Nettoyer subnets non utilisés

---

## 🔄 Mise à Jour Audit - 2026-03-17

### Problème Architectural : Double Racine Terraform

**Criticité**: 🟡 ÉLEVÉ

Deux racines Terraform coexistent dans le projet, créant confusion et risques :

| Racine | État | VPC | Backend State |
|--------|------|-----|---------------|
| `infra-microservices/` | EN PRODUCTION | `hellopro-dev-vpc` | `hellopro-terraform-state` |
| `infra-ci-cd/terraform/` | NON APPLIQUÉ | `rag-hp-vpc` (dupliqué) | `hp-rag-terraform-state` |

**Ressources dupliquées dans `infra-ci-cd/terraform/main.tf`** :
- VPC `rag-hp-vpc` (lignes 128-132) - duplique `hellopro-dev-vpc`
- Subnet `rag-hp-subnet-europe-west1` (lignes 135-143) - duplique subnets existants
- Firewall SSH `allow-ssh-rag-hp` (lignes 150-162) - avec `ssh_allowed_ips` défaut `0.0.0.0/0`
- Firewall interne `allow-internal-rag-hp` (lignes 165-181)
- Firewall HTTP `allow-http-https-rag-hp` (lignes 184-195) - `0.0.0.0/0`

**Ressources utiles dans `infra-ci-cd/terraform/main.tf`** (à conserver) :
- Artifact Registry `rag-hp-services` (lignes 33-44)
- Service Accounts CI/CD (lignes 51-91)
- Secret Manager (lignes 98-121)
- Monitoring & Alerting (lignes 202-239)
- Budget (lignes 242-273)
- Cloud Storage build artifacts (lignes 280-304)

**Décision validée** : Fusionner les ressources utiles comme modules dans `infra-microservices/` :
- Nouveau module `modules/secret_manager/`
- Nouveau module `modules/monitoring/`
- Nouveau module `modules/service_accounts/`
- Supprimer VPC/subnet/firewall dupliqués de `infra-ci-cd/terraform/`

### State Terraform : Ressources Orphelines

24 ressources de modules commentés restent dans le state Terraform de `infra-microservices/` :
- Modules concernés : `ilb_embedding`, `ilb_qualifier`, `lb_embedding`, `lb_qualifier`, `lb_etl`
- **Action requise** : `terraform state rm` pour chaque ressource orpheline
- **Risque** : Un `terraform plan` affichera des destroy inattendus si non nettoyé

### ILB Module : Health Check Désactivé

Le module `modules/internal_lb/main.tf` a ses health checks commentés (lignes 48-55).
Cela signifie que les Internal Load Balancers ne vérifient pas la santé des backends.
**Action** : Décommenter et configurer les health checks lors de la migration des LBs.

### Monitoring : Couverture Insuffisante

`prometheus/prometheus.yml` ne scrape que ~15 services sur 48+ actifs.
Services manquants : api-gateway, api-recherche, api-chat-llm, graph-rag-*, QC-*, crawlers.
Aucun exporter tiers configuré (redis_exporter, rabbitmq_exporter).

### Recommandations Additionnelles

| # | Action | Priorité | Impact |
|---|--------|----------|--------|
| I1 | Fusionner racines Terraform | 🔴 Haute | IaC cohérent |
| I2 | Nettoyer 24 ressources orphelines state | 🔴 Haute | terraform plan fiable |
| I3 | Décommenter health checks ILB | 🟡 Moyenne | Résilience |
| I4 | Étendre couverture Prometheus à 100% services | 🟡 Moyenne | Observabilité |
| I5 | Ajouter exporters Redis/RabbitMQ | 🟡 Moyenne | Observabilité |
