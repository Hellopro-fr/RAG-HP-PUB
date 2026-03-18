# 📊 Inventaire GCP - Projet RAG HelloPro

> **Projet**: `hellopro-rag-project`  
> **Date d'extraction**: 2026-02-05 16:00 UTC+3  
> **Méthode**: Commandes gcloud (READ-ONLY)

---

## 📈 Résumé Exécutif

| Catégorie | Quantité | Notes |
|-----------|----------|-------|
| **VMs** | 7 | 4 GKE nodes + 2 GPU + 1 Manager |
| **Cluster GKE** | 1 | matching-api-dev-k8s (4 nodes) |
| **VPC** | 2 | default + hellopro-dev-vpc |
| **Subnets** | 9 (+defaults) | Multi-région |
| **Firewall Rules** | 48 | ⚠️ Plusieurs exposées 0.0.0.0/0 |
| **Load Balancers** | 22 | Mix External/Internal |
| **Service Accounts** | 4 | |
| **Artifact Registry** | 1 | hellopro (DOCKER) |
| **DNS Zones** | 1 | Private zone |
| **Buckets GCS** | 0 visible | À vérifier droits |

---

## 💻 Compute Instances (VMs)

| Nom | Zone | Type Machine | Status | IP Externe | IP Interne |
|-----|------|--------------|--------|------------|------------|
| gke-matching-api-dev-...-4954 | europe-west1-b | c2-standard-8 | RUNNING | - | 10.0.1.215 |
| gke-matching-api-dev-...-5nzj | europe-west1-b | c2-standard-8 | RUNNING | - | 10.0.1.212 |
| gke-matching-api-dev-...-ajoa | europe-west1-b | c2-standard-8 | RUNNING | - | 10.0.1.195 |
| gke-matching-api-dev-...-kf7c | europe-west1-b | c2-standard-8 | RUNNING | - | 10.0.1.194 |
| **manager-vm-dev** | europe-west1-b | e2-small | RUNNING | 34.77.187.108 | 10.0.1.2 |
| vm-embedding-g2-std-24 | europe-west1-c | g2-standard-24 | TERMINATED | 34.14.30.48 | 10.0.1.53 |
| **vm-embedding-g2-std-24-use** | us-east4-c | g2-standard-24 | RUNNING | 35.245.31.1 | 10.11.0.2 |

### ⚠️ Points d'Attention VMs
- **VM GPU active** en `us-east4-c` (hors zone TF europe-west1-b)
- **VM GPU terminée** en `europe-west1-c` (ancienne ?)
- **Manager VM** avec IP publique (bastion)

---

## ☸️ GKE Cluster

| Nom | Zone | Version | Nodes | Status |
|-----|------|---------|-------|--------|
| matching-api-dev-k8s | europe-west1-b | (voir GCP console) | 4 | RUNNING |

### Configuration
- **Machine type nodes**: c2-standard-8 (8 vCPUs, 32 GB RAM)
- **Réseau**: hellopro-dev-vpc / hellopro-subnet-dev
- **Range pods**: 10.0.128.0/17
- **Range services**: 10.0.72.0/21

---

## 🌐 VPC Networks

| Nom | Mode | Description |
|-----|------|-------------|
| default | AUTO | Default network for the project |
| hellopro-dev-vpc | CUSTOM | VPC principal projet RAG |

---

## 📍 Subnets (hellopro-dev-vpc)

| Nom | Région | CIDR | Purpose |
|-----|--------|------|---------|
| hellopro-subnet-dev | europe-west1 | 10.0.1.0/24 | PRIVATE |
| hellopro-subnet-dev-w2 | europe-west2 | 10.0.35.0/24 | PRIVATE |
| hellopro-subnet-dev-w3 | europe-west3 | 10.0.25.0/24 | PRIVATE |
| hellopro-subnet-dev-w4 | europe-west4 | 10.0.21.0/24 | PRIVATE |
| hellopro-subnet-dev-w6 | europe-west6 | 10.0.30.0/24 | PRIVATE |
| subnet-us-central1 | us-east4 | 10.11.0.0/20 | PRIVATE |
| proxy-subnet | europe-west1 | 10.0.125.0/24 | GLOBAL_MANAGED_PROXY |
| gke-matching-api-dev-k8s-...-pe-subnet | europe-west1 | 10.80.243.0/28 | PRIVATE |

> ⚠️ **Subnet us-east4** non déclaré dans Terraform original

---

## 🔥 Firewall Rules (Résumé)

### ⚠️ Règles CRITIQUES (source 0.0.0.0/0)

| Règle | Réseau | Ports | Risque |
|-------|--------|-------|--------|
| allow-public-services | default | 80,443,15672,19530 | 🔴 Élevé |
| allow-public-services-hellopro-dev-vpc | hellopro-dev-vpc | 80,443,15672,19530,8321,7474,8585,7688 | 🔴 Élevé |
| default-allow-api-ports-8509 | default | 8509 | 🔴 Élevé |
| default-allow-http | default | 80 | 🟡 Moyen |
| default-allow-https | hellopro-dev-vpc | 443 | 🟡 Moyen |
| default-allow-rdp | default | 3389 | 🔴 Élevé |
| k8s-fw-... (multiples) | hellopro-dev-vpc | Divers | 🟡 K8s managed |

### ✅ Règles Sécurisées

| Règle | Source Ranges | Ports |
|-------|---------------|-------|
| allow-ssh | 35.235.240.0/20 | 22 (IAP tunnel) |
| allow-ssh1 | IPs spécifiques | 22 |
| allow-intra-lan | RFC1918 | all |
| allow-restricted-services-hellopro | 2 IPs spécifiques | 8579,8590 |

### 🛡️ Règles de Blocage

| Règle | Direction | Description |
|-------|-----------|-------------|
| block-aws-leak | EGRESS | Blocage fuites AWS |
| block-suspect-ip | EGRESS | Blocage IPs suspectes |
| deny-crypto-mining-egress | EGRESS | Anti-cryptomining |
| deny-udp-egress | EGRESS | Blocage UDP sortant |

---

## ⚖️ Load Balancers

### External (IPs Publiques)

| IP | Type | Service |
|----|------|---------|
| 34.36.145.216 | HTTPS | portf-ingress |
| 34.117.22.97 | HTTPS | rabbitmq-i2-ingress |
| 34.8.52.188 | HTTPS | attu-cluster-ingress (Milvus UI) |
| 34.49.35.68 | HTTPS | rabbitmq-ingress |
| 34.52.142.50 | TCP | Qdrant (6333-6335) |
| 34.78.143.55 | TCP | Port 80 |
| 34.14.100.226 | TCP | Redis (6379) |
| 34.38.134.70 | TCP | Port 80 |

### Internal (IPs Privées 10.x.x.x)

| IP | Service (probable) |
|----|---------------------|
| 10.0.1.12 | cleaner-etl-dev-ilb |
| 10.0.1.13 | qualifier-llm-dev-ilb |
| 10.0.1.14 | embedding-dev-ilb |
| 10.0.1.59 | Milvus |
| 10.0.1.217 | RabbitMQ |
| 10.0.1.216 | RabbitMQ-2 |
| 10.0.1.197 | Prometheus metrics |
| 10.0.1.198 | Prometheus metrics |

---

## 🔑 Service Accounts

| Email | Display Name | Status |
|-------|--------------|--------|
| hp-sa-gcs-data-job@... | Service Account for GCS Copy-Backup Job | Active |
| 806625052144-compute@developer... | Compute Engine default SA | Active |
| terraform@hellopro-rag-project... | terraform | Active |
| milvus-backup-wi@... | (Workload Identity) | Active |

---

## 🏭 Artifact Registry

| Repository | Format | Location |
|------------|--------|----------|
| hellopro | DOCKER | (default) |

---

## 🌍 DNS Zones

| Nom | DNS Name | Visibility |
|-----|----------|------------|
| hellopro-private | hello.dev.private.com. | PRIVATE |

---

## 📝 Observations Clés

### 🔴 Risques Critiques
1. **~10 règles Firewall** exposent des ports sur 0.0.0.0/0
2. **Redis exposé** sur IP publique (34.14.100.226:6379)
3. **RDP (default-allow-rdp)** ouvert sur 0.0.0.0/0

### 🟡 Écarts avec Terraform
1. **VM GPU** `vm-embedding-g2-std-24-use` en us-east4-c (non déclarée TF)
2. **Subnet** `subnet-us-central1` en us-east4 (non déclaré TF)
3. **VM TERMINATED** `vm-embedding-g2-std-24` (ancienne version ?)

### 🟢 Bonnes Pratiques Détectées
1. SSH via IAP (35.235.240.0/20)
2. Règles anti-cryptomining
3. Blocage UDP sortant
4. Service Accounts dédiés
