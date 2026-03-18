# 🔄 Mapping Terraform ↔ GCP - Analyse des Drifts

> **Projet**: `hellopro-rag-project`  
> **Date**: 2026-02-05  
> **État TF**: bucket `hellopro-terraform-state/dev/state`

---

## 📊 Synthèse des Drifts

| Catégorie | Dans TF | Dans GCP | Drift |
|-----------|---------|----------|-------|
| VPC | 1 | 2 | ⚠️ default VPC non géré |
| Subnets | 5 | 9 | 🔴 4 non déclarés |
| VMs | 1 | 7 | 🔴 6 non déclarées (dont GKE nodes) |
| GKE Cluster | 1 | 1 | ✅ OK |
| Firewall Rules | 2 | 48 | 🔴 46 non déclarées |
| DNS Zone | 1 | 1 | ✅ OK |
| DNS Records | 8 | ? | ⚠️ À vérifier |
| Load Balancers | 4+ | 22 | 🔴 Majeur drift |

---

## 📁 Structure Terraform Actuelle

```
infra-microservices/
├── modules/                    # 12 modules réutilisables
│   ├── vpc/
│   ├── gke_cluster/
│   ├── compute_instance/
│   ├── compute_instance_gpu/
│   ├── compute_standalone_gpu/
│   ├── dns/
│   ├── artifact_registry/
│   ├── loadbalancer/
│   ├── loadbalancer_rabbit/
│   ├── internal_lb/
│   ├── dlvm_mig/
│   └── access_connector/
├── config-dev/                 # Configuration DEV
│   ├── backend.tf              # GCS backend
│   ├── vpc.tf                  # 1 VPC + 5 subnets
│   ├── gke.tf                  # 1 cluster
│   ├── vm.tf                   # 1 VM manager
│   ├── vm_gpu_standalone.tf    # ❌ COMMENTÉ
│   ├── firewall.tf             # 2 règles
│   ├── dns.tf                  # 1 zone + 8 records
│   ├── lb.tf                   # Load balancers
│   └── ...
└── config-prod/                # Configuration PROD (similaire)
```

---

## 🔍 Analyse Détaillée par Ressource

### VPC Networks

| TF Resource | TF Name | GCP Name | Status |
|-------------|---------|----------|--------|
| module.vpc | hellopro-dev-vpc | hellopro-dev-vpc | ✅ Sync |
| - | - | default | ⚠️ Non géré par TF |

### Subnets (TF vs GCP)

| TF Déclaré | GCP Présent | CIDR | Status |
|------------|-------------|------|--------|
| hellopro-subnet-dev | ✅ Oui | 10.0.1.0/24 | ✅ Sync |
| hellopro-subnet-dev-w2 | ✅ Oui | 10.0.35.0/24 | ✅ Sync |
| hellopro-subnet-dev-w3 | ✅ Oui | 10.0.25.0/24 | ✅ Sync |
| hellopro-subnet-dev-w4 | ✅ Oui | 10.0.21.0/24 | ✅ Sync |
| hellopro-subnet-dev-w6 | ✅ Oui | 10.0.30.0/24 | ✅ Sync |
| - | subnet-us-central1 (us-east4) | 10.11.0.0/20 | 🔴 Non déclaré |
| - | proxy-subnet | 10.0.125.0/24 | ⚠️ Géré automatiquement |
| - | gke-matching-api-dev-...-pe-subnet | 10.80.243.0/28 | ⚠️ Géré par GKE |

### Compute Instances (VMs)

| TF Déclaré | GCP Présent | Zone | Type | Status |
|------------|-------------|------|------|--------|
| module.vm (manager-vm-dev) | ✅ manager-vm-dev | eu-west1-b | e2-small | ✅ Sync |
| - | gke-matching-api-dev-...-4954 | eu-west1-b | c2-standard-8 | ⚠️ GKE managed |
| - | gke-matching-api-dev-...-5nzj | eu-west1-b | c2-standard-8 | ⚠️ GKE managed |
| - | gke-matching-api-dev-...-ajoa | eu-west1-b | c2-standard-8 | ⚠️ GKE managed |
| - | gke-matching-api-dev-...-kf7c | eu-west1-b | c2-standard-8 | ⚠️ GKE managed |
| ❌ COMMENTÉ | vm-embedding-g2-std-24 | eu-west1-c | g2-standard-24 | 🔴 TERMINATED |
| ❌ Non déclaré | **vm-embedding-g2-std-24-use** | **us-east4-c** | g2-standard-24 | 🔴 **DRIFT CRITIQUE** |

### GKE Cluster

| TF Déclaré | GCP Présent | Status |
|------------|-------------|--------|
| module.gke_cluster (matching-api-dev) | matching-api-dev-k8s | ⚠️ Nom légèrement différent |

### Firewall Rules (DRIFT MAJEUR)

**Dans Terraform (config-dev/firewall.tf)** :
| Rule | Source | Ports |
|------|--------|-------|
| allow-ssh | 0.0.0.0/0 | 22,19530,80,15672 |
| allow-intra-lan | 0.0.0.0/0 | all |

**Dans GCP (48 règles)** - Non déclarées en TF :
- `allow-public-services-hellopro-dev-vpc`
- `allow-ssh1` (IPs spécifiques)
- `allow-restricted-services-hellopro`
- `allow-us-to-gke-internal`
- `allow-useast4-to-gke-internal`
- `allow-vm-to-rabbitmq-ilb-5672`
- `allow-vm-to-redis-ilb-6379`
- `default-allow-https`
- `block-aws-leak`
- `block-suspect-ip`
- `deny-crypto-mining-*`
- `deny-udp-egress`
- ~20 règles k8s-fw-* (managed by K8s)
- ... et autres

### Load Balancers (DRIFT MAJEUR)

**Dans Terraform** :
- cleaner-etl-dev-ilb
- embedding-dev-ilb  
- qualifier-llm-dev-ilb
- (autres via modules lb)

**Dans GCP (22 forwarding rules)** :
- Nombreux LB créés par Kubernetes/Ingress
- ILB créés via console

---

## 🔴 Drifts Critiques à Résoudre

### 1. VM GPU en us-east4-c (NON déclarée TF)
```
Ressource: vm-embedding-g2-std-24-use
Zone: us-east4-c (au lieu de europe-west1-b)
Type: g2-standard-24 (2xL4 GPU)
Status: RUNNING
IP: 35.245.31.1 (publique)
```

**Action recommandée** :
- Option A: Import dans Terraform
- Option B: Documenter comme ressource "hors IaC"

### 2. Subnet us-east4 (NON déclaré TF)
```
Nom: subnet-us-central1
Région: us-east4
CIDR: 10.11.0.0/20
```

**Action recommandée** : Ajouter au tfvars et vpc.tf

### 3. Firewall permissives (source 0.0.0.0/0)
```
allow-ssh: devrait être restreint à IAP uniquement
allow-intra-lan: source devrait être RFC1918 uniquement
```

**Action recommandée** : Modifier firewall.tf progressivement

---

## 🟡 Drifts Modérés

### 4. CIDR overlap dev/prod
Les deux environnements utilisent `10.0.1.0/24` pour le subnet principal.

**Action recommandée** : Prévoir migration CIDR pour PROD

### 5. Firewall créées via Console
~15 règles non déclarées en TF mais nécessaires pour le fonctionnement.

**Action recommandée** : Import ou création dans firewall.tf

---

## 🟢 Éléments Synchronisés

| Ressource | Status |
|-----------|--------|
| VPC hellopro-dev-vpc | ✅ |
| 5 Subnets principaux | ✅ |
| GKE Cluster | ✅ (à vérifier config) |
| VM Manager | ✅ |
| DNS Zone | ✅ |
| Artifact Registry | ✅ |

---

## 📋 Plan de Réconciliation

### Phase 2.1 - Import Ressources
```bash
# À exécuter APRÈS validation (READ uniquement ici)
# terraform import module.vpc.google_compute_subnetwork.subnet_us_east4 ...
# terraform import google_compute_instance.vm_gpu_use ...
# etc.
```

### Phase 2.2 - Refactoring Modules
1. Ajouter module pour VM GPU
2. Étendre module VPC pour subnets multi-région
3. Centraliser firewall rules

### Phase 2.3 - Séparation Environnements
1. workspace Terraform OU
2. Dossiers séparés avec tfvars différents

---

## ⚠️ Avertissement

> [!CAUTION]
> **NE PAS exécuter `terraform apply`** tant que les imports et le mapping ne sont pas validés.
> Un apply sans préparation pourrait détruire des ressources en production.
