# Phase 2 - Instructions : Refactoring Terraform & Architecture Services

> **Phase** : 2 - Refactoring Terraform & Architecture  
> **Durée** : 2-3 semaines  
> **Statut** : 🔄 Planification

---

## 🎯 Objectifs

1. Réconcilier code Terraform avec infrastructure GCP réelle
2. Sécuriser les services exposés sur VM GPU
3. Séparer les environnements DEV/PROD
4. Importer les ressources non gérées par Terraform

---

## ⚠️ Contrainte Critique

> [!CAUTION]
> **AUCUNE action ne doit impacter les services en production.**
> Toutes les modifications sont validées avant exécution.

---

## 📋 Prérequis

- [ ] Accès SSH à vm-embedding-g2-std-24-use
- [ ] Terraform >= 1.0 installé
- [ ] Configuration GCP authentifiée

---

## 🔧 Étape 2.1 : Inventaire Services Exposés

### Commandes à exécuter (READ-ONLY)

```bash
# Depuis manager-vm, SSH vers VM GPU
gcloud compute ssh vm-embedding-g2-std-24-use --zone=us-east4-c \
  --command="docker ps --format 'table {{.Names}}\t{{.Ports}}' | head -50"

# Config Nginx
gcloud compute ssh vm-embedding-g2-std-24-use --zone=us-east4-c \
  --command="cat /etc/nginx/nginx.conf 2>/dev/null || echo 'Nginx non trouvé'"

# Ou via manager-vm si tunnel configuré
ssh vm-embedding-g2-std-24-use "docker ps --format 'table {{.Names}}\t{{.Ports}}'"
```

### Livrable
→ Compléter tableau classification services dans `docs/inventaire/inventaire_services.md`

---

## 🔧 Étape 2.2 : Design Architecture Sécurisée

### Architecture Recommandée

```
Internet → Cloud Armor (WAF) → HTTPS Load Balancer → NEG (VM GPU)
```

### Avantages
- Protection DDoS native
- SSL Google-managed
- Logging centralisé
- VM sans IP publique (optionnel)

### Décisions requises
1. [ ] Domaines DNS pour les APIs
2. [ ] Règles Cloud Armor (geo-blocking, rate-limit)
3. [ ] IPs partenaires à whitelister

### Livrable
→ Créer `docs/phases/phase2_architecture_cible.md`

---

## 🔧 Étape 2.3 : Restructuration Terraform

### Structure Cible

```
infra-microservices/
├── modules/
│   ├── compute_gpu_vm/   # NOUVEAU
│   ├── global_lb/        # NOUVEAU
│   ├── cloud_armor/      # NOUVEAU
│   └── ...
├── environments/
│   ├── dev/
│   └── prod/
```

### Actions
1. [ ] Créer module compute_gpu_vm
2. [ ] Ajouter subnet us-east4 au module VPC
3. [ ] Créer module global_lb pour HTTPS LB

---

## 🔧 Étape 2.4 : Import Ressources

### Ressources à importer

```bash
# VM GPU (après création module)
terraform import module.vm_gpu.google_compute_instance.main \
  projects/hellopro-rag-project/zones/us-east4-c/instances/vm-embedding-g2-std-24-use

# Subnet us-east4
terraform import module.vpc.google_compute_subnetwork.us_east4 \
  projects/hellopro-rag-project/regions/us-east4/subnetworks/subnet-us-central1
```

### Validation CRITIQUE
```bash
# TOUJOURS vérifier avant apply
terraform plan -out=phase2.tfplan

# Doit afficher : "0 to destroy"
# Si destroy détecté → STOP et analyse
```

---

## 🔧 Étape 2.5 : Déploiement Architecture

### Ordre (sans downtime)

1. Créer Load Balancer (nouveau)
2. Configurer Cloud Armor
3. Ajouter backend vers VM
4. Tester via IP du LB
5. Migrer DNS
6. (Optionnel) Retirer IP publique VM

---

## ✅ Critères de Validation

- [ ] Terraform plan sans destroy
- [ ] Tous services accessibles via LB
- [ ] Tests fonctionnels OK
- [ ] Documentation à jour
