# 📊 Rapport d'Analyse Terraform Plan - Drifts et Corrections

> **Date** : 2026-02-06  
> **Projet** : hellopro-rag-project  
> **Statut** : Plan initial : 8 add, 6 change, 24 destroy → **À corriger**

---

## 🔴 Problèmes Critiques Identifiés

### 1. VM GPU Force Replace (CORRIGÉ ✅)

La VM `vm-embedding-g2-std-24-use` était marquée pour remplacement à cause de :
- `key_revocation_action_type` différent
- `boot_disk.initialize_params.image` différent  
- `boot_disk.initialize_params.size` (100 → 500)

**Solution appliquée** : Ajout de `ignore_changes` dans le lifecycle pour préserver la VM de production.

---

### 2. Subnet Rename → Replace (CORRIGÉ ✅)

Le subnet `subnet-us-central1` en région us-east4 aurait été recréé si on essayait de le renommer en `subnet-us-east4`.

**Solution appliquée** : Conserver le nom original `subnet-us-central1` dans terraform.tfvars.

---

### 3. Modules Orphelins dans le State (24 ressources) ⚠️

Ces modules ont été **commentés** dans le code mais leurs ressources restent dans le state Terraform :

| Module | Ressources dans State | Action Requise |
|--------|----------------------|----------------|
| `module.ilb_embedding` | 5 ressources | `terraform state rm` |
| `module.ilb_qualifier` | 5 ressources | `terraform state rm` |
| `module.lb_embedding` | 6 ressources | `terraform state rm` |
| `module.lb_qualifier` | 6 ressources | `terraform state rm` |
| `module.lb_etl` | 6 ressources | `terraform state rm` |

**⚠️ Ces ressources existent toujours dans GCP et continueront à fonctionner.**  
Terraform ne les gérera tout simplement plus.

---

### 4. Firewall Rules Revertées ⚠️

Les règles firewall ont été remédiées directement dans GCP Console (source_ranges restreints) mais le code TF contient toujours `0.0.0.0/0`.

| Règle | État GCP | État TF Code | Impact |
|-------|----------|--------------|--------|
| `allow-ssh` | `35.235.240.0/20` (IAP) | `0.0.0.0/0` | Revert sécurité ! |
| `allow-intra-lan` | Ranges internes | `0.0.0.0/0` | Revert sécurité ! |

**Solution recommandée** : Mettre à jour le code firewall.tf pour correspondre à l'état sécurisé dans GCP.

---

## 🔧 Commandes de Nettoyage du State

Exécuter ces commandes pour retirer les modules orphelins du state :

```bash
# 1. Sauvegarder le state actuel
terraform state pull > state_backup_$(date +%Y%m%d_%H%M%S).json

# 2. Retirer les modules orphelins du state (ILB)
terraform state rm 'module.ilb_embedding'
terraform state rm 'module.ilb_qualifier'

# 3. Retirer les modules orphelins du state (LB externes)
terraform state rm 'module.lb_embedding'
terraform state rm 'module.lb_qualifier'
terraform state rm 'module.lb_etl'

# 4. Vérifier le state nettoyé
terraform state list | grep -E "(ilb_embedding|ilb_qualifier|lb_embedding|lb_qualifier|lb_etl)"
# Doit retourner vide
```

---

## 📋 Plan d'Action Recommandé

### Étape 1 : Nettoyage du State (MAINTENANT)
```bash
# Exécuter les commandes terraform state rm ci-dessus
```

### Étape 2 : Re-planifier
```bash
terraform plan -out=clean.tfplan 2>&1 | tee clean_plan.log
```

### Étape 3 : Vérifier le Nouveau Plan
Le plan devrait maintenant montrer :
- ✅ **0 destroy** (plus de modules orphelins)
- ✅ VM GPU : aucun changement (ignore_changes)
- ⚠️ Firewall : update pour revenir à 0.0.0.0/0 (à décider si on applique)

### Étape 4 : Décision sur Firewall
**Option A** : Mettre à jour firewall.tf pour matcher GCP (recommandé)
**Option B** : Ajouter `ignore_changes` sur les firewall rules

---

## 📏 État Attendu Après Corrections

| Catégorie | add | change | destroy |
|-----------|-----|--------|---------|
| Avant corrections | 8 | 6 | 24 |
| Après state rm | 3 | 3-4 | 1-2 max |
| Après ajustement FW | 3 | 1-2 | 0 |

---

## ⚠️ Ressources Non Gérées par Terraform (Volontairement)

Ces ressources existent dans GCP mais ne sont/seront pas gérées par Terraform :

1. **Load Balancers externes** (ilb_embedding, lb_qualifier, etc.) → Retirés du state
2. **Firewall K8s** (k8s-fw-*) → Gérées automatiquement par GKE
3. **Certaines firewall rules manuelles** → Créées via Console pour besoins ponctuels
