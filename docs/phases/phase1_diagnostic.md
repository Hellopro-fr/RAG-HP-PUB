# 📋 Phase 1 - Diagnostic & Audit : Instructions

> **Phase** : 1 - Diagnostic & Audit  
> **Durée** : 1-2 semaines  
> **Statut** : 🟡 En cours

---

## 🎯 Objectifs

1. Inventaire complet des ressources GCP déployées
2. Mapping entre code Terraform et infrastructure réelle
3. Audit sécurité et infrastructure
4. Audit code applicatif (76 microservices)
5. Recommandations FinOps

---

## 📝 Prérequis

- [ ] Accès authentifié au projet GCP `hellopro-rag-project`
- [ ] kubectl configuré pour le cluster GKE
- [ ] Terraform installé (version >= 1.0)

```bash
# Vérification accès
gcloud auth list
gcloud config set project hellopro-rag-project
gcloud container clusters get-credentials matching-api-dev --zone europe-west1-b
```

---

## 🔧 Étape 1.1 : Inventaire GCP

### Commandes à exécuter

```bash
# === Export Compute ===
gcloud compute instances list --format="table(name,zone,machineType,status,networkInterfaces[0].accessConfigs[0].natIP)" 

# === Export Réseau ===
gcloud compute networks list
gcloud compute networks subnets list --format="table(name,region,ipCidrRange)"
gcloud compute firewall-rules list --format="table(name,network,direction,sourceRanges,allowed)"

# === Export GKE ===
gcloud container clusters list
kubectl get nodes -o wide
kubectl get pods --all-namespaces

# === Export Services K8s ===
kubectl get svc --all-namespaces

# === Export IAM ===
gcloud iam service-accounts list
```

### Livrable
→ Compléter `docs/inventaire/inventaire_gcp.md`

---

## 🔧 Étape 1.2 : Mapping Terraform ↔ GCP

### Lister ressources Terraform

```bash
cd /home/anthonny/devops_projects/CLIENT/HP/RAG/infra-microservices/config-dev
terraform init
terraform state list
terraform plan -out=drift_check.tfplan
```

### Livrable
→ Compléter `docs/inventaire/mapping_tf_gcp.md`

---

## 🔧 Étape 1.3 : Audit Infrastructure

### Points de contrôle

| Composant | Critère | Check |
|-----------|---------|-------|
| GKE | Version K8s supportée | [ ] |
| GKE | Cluster privé | [ ] |
| GKE | Autoscaling configuré | [ ] |
| VPC | Segmentation appropriée | [ ] |
| VPC | Pas CIDR overlap | [ ] |
| VM | Right-sizing | [ ] |
| Stockage | Lifecycle policies | [ ] |

### Livrable
→ Compléter `docs/audit/rapport_audit_infra.md`

---

## 🔧 Étape 1.4 : Audit Sécurité

### Points de contrôle critiques

| Composant | Critère | Statut |
|-----------|---------|--------|
| Firewall | Pas de 0.0.0.0/0 | ⚠️ FAIL |
| VM | Pas d'IP publique non nécessaire | [ ] |
| IAM | Moindre privilège | [ ] |
| Secrets | Pas en clair dans code | [ ] |
| GKE | Workload Identity | [ ] |

### Livrable
→ Compléter `docs/audit/rapport_audit_securite.md`

---

## 🔧 Étape 1.5 : Audit Applicatif

### Analyse des services

```bash
# Nombre de services
ls -d /home/anthonny/devops_projects/CLIENT/HP/RAG/apps-microservices/*/ | wc -l

# Images Docker utilisées
grep -r "^FROM" /home/anthonny/devops_projects/CLIENT/HP/RAG/apps-microservices/*/Dockerfile | cut -d: -f2 | sort | uniq -c | sort -rn

# Services avec healthcheck
grep -r "healthcheck" /home/anthonny/devops_projects/CLIENT/HP/RAG/docker-compose.yml | wc -l
```

### Livrable
→ Compléter `docs/audit/rapport_audit_applicatif.md`

---

## 🔧 Étape 1.6 : Recommandations FinOps

### Analyse coûts

```bash
# Estimation via gcloud billing (si accès)
gcloud beta billing accounts list
```

### Points d'optimisation à évaluer
- [ ] Committed Use Discounts
- [ ] Spot/Preemptible VMs
- [ ] Autoscaling agressif
- [ ] Right-sizing des ressources

### Livrable
→ Compléter `docs/audit/recommendations_finops.md`

---

## ✅ Validation Phase 1

- [ ] Tous les livrables créés et remplis
- [ ] Drifts Terraform documentés
- [ ] Issues sécurité classifiées par criticité
- [ ] Revue par l'équipe effectuée

---

## 📌 Notes

> [!IMPORTANT]
> Toutes les commandes sont **read-only**. Aucune modification n'est effectuée.

> [!WARNING]
> Ne pas exécuter `terraform apply` tant que le mapping n'est pas validé.
