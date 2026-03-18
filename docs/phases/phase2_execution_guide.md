# 🔧 Guide d'Exécution Phase 2 - Réconciliation Terraform

> **Date** : 2026-02-06  
> **Statut** : Code prêt pour validation  
> **Prérequis** : Machine avec accès GCP authentifié

---

## 📋 Résumé des Fichiers Créés/Modifiés

| Fichier | Action | Description |
|---------|--------|-------------|
| `vm_gpu_us_east4.tf` | CRÉÉ | Config VM GPU existante (à importer) |
| `firewall_gpu_vm.tf` | CRÉÉ | Règles firewall GPU ↔ GKE |
| `imports.tf` | CRÉÉ | Documentation commandes d'import |
| `terraform.tfvars` | MODIFIÉ | Ajout subnet us-east4 |

---

## 🚀 Instructions d'Exécution

### Étape 1 : Préparer l'environnement

```bash
cd /home/anthonny/devops_projects/CLIENT/HP/RAG/infra-microservices/config-dev

# S'assurer que gcloud est authentifié
gcloud auth application-default login
gcloud config set project hellopro-rag-project
```

### Étape 2 : Initialiser Terraform

```bash
terraform init -upgrade
```

### Étape 3 : Importer les ressources existantes

> ⚠️ **IMPORTANT** : Ces commandes doivent être exécutées AVANT terraform plan

```bash
# 1. Importer le subnet us-east4
terraform import 'module.vpc.google_compute_subnetwork.subnets["subnet-us-east4"]' \
  projects/hellopro-rag-project/regions/us-east4/subnetworks/subnet-us-central1

# 2. Importer la VM GPU
terraform import google_compute_instance.vm_gpu_us_east4 \
  projects/hellopro-rag-project/zones/us-east4-c/instances/vm-embedding-g2-std-24-use
```

### Étape 4 : Valider le plan

```bash
terraform plan -out=reconciliation.tfplan
```

#### ✅ Critères de succès :
- **0 ressources à détruire** (destroy)
- Modifications acceptables (labels, formatting)
- Nouvelles ressources = firewall rules uniquement

### Étape 5 : Formater le code (optionnel)

```bash
terraform fmt -recursive .
```

---

## ⚠️ Points d'Attention

### Nom du subnet incohérent
Dans GCP, le subnet est nommé `subnet-us-central1` mais il est situé en `us-east4`.
Notre code TF le renommera en `subnet-us-east4`.

**Impact** : Terraform montrera un changement de nom (acceptable).

### VM GPU - lifecycle prevent_destroy
Le fichier `vm_gpu_us_east4.tf` contient :
```hcl
lifecycle {
  prevent_destroy = true
}
```
Cela empêche toute destruction accidentelle de la VM.

### Firewall existantes
Les règles firewall dans `firewall.tf` existant ont `source_ranges = ["0.0.0.0/0"]`.
Ces règles ne sont PAS modifiées dans cette phase (remédiation = plan séparé).

---

## 📊 État Post-Import Attendu

| Ressource | État |
|-----------|------|
| VPC hellopro-dev-vpc | ✅ Géré |
| 6 Subnets (5 EU + 1 US) | ✅ Géré |
| VM manager-vm-dev | ✅ Géré |
| VM GPU us-east4 | ✅ Géré (après import) |
| GKE cluster | ✅ Géré |
| Firewall (nouvelles) | ✅ Géré |
| Firewall (existantes console) | ❌ Non géré |

---

## 📝 Prochaines Étapes (Plan Remédiation Séparé)

Une fois le plan validé, créer `plan_remediation.md` avec :

1. Sécurisation firewall (remplacer 0.0.0.0/0)  
2. Migration services vers HTTPS LB
3. Suppression IP publique VM GPU
4. Configuration Cloud Armor
5. Séparation environnements DEV/PROD
