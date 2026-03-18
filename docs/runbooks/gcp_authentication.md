# 🔐 Procédure d'Authentification GCP pour Terraform

> **Projet** : hellopro-rag-project  
> **Erreur rencontrée** : `could not find default credentials`

---

## 🚀 Solution Rapide

### Option 1 : Application Default Credentials (Recommandé pour développement)

```bash
# Se connecter avec votre compte Google
gcloud auth application-default login

# Sélectionner le projet
gcloud config set project hellopro-rag-project

# Vérifier l'authentification
gcloud auth list
```

Après cette commande, un navigateur s'ouvrira pour vous connecter à votre compte Google.

---

### Option 2 : Service Account Key (Recommandé pour CI/CD)

```bash
# 1. Télécharger la clé du Service Account Terraform (depuis GCP Console)
# IAM & Admin → Service Accounts → terraform@hellopro-rag-project → Keys → Add Key

# 2. Définir la variable d'environnement
export GOOGLE_APPLICATION_CREDENTIALS="/chemin/vers/terraform-sa-key.json"

gcloud auth activate-service-account --key-file="C:\chemin\vers\terraform-sa-key.json"

# 3. Ou ajouter au fichier provider.tf
```

Dans `providers.tf` :
```hcl
provider "google" {
  credentials = file("/chemin/vers/terraform-sa-key.json")
  project     = "hellopro-rag-project"
  region      = "europe-west1"
}

provider "google-beta" {
  credentials = file("/chemin/vers/terraform-sa-key.json")
  project     = "hellopro-rag-project"
  region      = "europe-west1"
}
```

---

## 📋 Vérification

```bash
# Vérifier que vous êtes authentifié
gcloud auth list

# Vérifier le projet actif
gcloud config get-value project

# Tester l'accès au bucket Terraform state
gsutil ls gs://hellopro-terraform-state/

#ou

gcloud storage ls gs://hellopro-terraform-state/
```

---

## 🔧 Après Authentification

Une fois authentifié, relancer :

```bash
cd /home/anthonny/devops_projects/CLIENT/HP/RAG/infra-microservices/config-dev

# Initialiser Terraform
terraform init -upgrade

# Si succès, continuer avec les imports...
```

---

## ⚠️ Dépannage

### Erreur : "Permission denied on bucket"
```bash
# Vérifier les droits sur le bucket state
gsutil iam get gs://hellopro-terraform-state/
```

### Erreur : "Account not authorized"
```bash
# Révoquer et se reconnecter
gcloud auth application-default revoke
gcloud auth application-default login
```

### Pour utilisation en SSH (sans navigateur)
```bash
gcloud auth application-default login --no-launch-browser
# Suivre les instructions affichées (copier URL, coller code)
```
