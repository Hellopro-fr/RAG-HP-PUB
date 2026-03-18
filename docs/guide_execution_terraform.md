# 📘 Guide d'Exécution Terraform - Architecture Centralisée

Ce projet utilise une architecture Terraform centralisée :
- **Code unique (DRY)** : Le code racine (`/infra-microservices/`) est utilisé pour tous les environnements.
- **Environnements isolés** : Les configurations spécifiques (variables, backend) sont dans `environments/<env>/`.

---

## 🚀 Commandes Principales

Toutes les commandes doivent être exécutées depuis la **racine du code Terraform** :
`/home/anthonny/devops_projects/CLIENT/HP/RAG/infra-microservices`

### 1. Initialisation (terraform init)

Vous devez spécifier le fichier de configuration backend correspondant à l'environnement cible via l'option `-backend-config`.

**Pour DEV :**
```bash
# S'assurer d'avoir les credentials
export GOOGLE_APPLICATION_CREDENTIALS="local/votre-cle.json"

# Init avec le prefix DEV
terraform init \
  -backend-config="prefix=dev/state" \
  -reconfigure
```

**Pour PROD (Futur) :**
```bash
terraform init \
  -backend-config="prefix=prod/state" \
  -reconfigure
```

> **Note** : L'option `-reconfigure` est impérative lorsque vous basculez d'un environnement à l'autre pour recharger la configuration du backend correcte.

### 2. Planification (terraform plan)

Utilisez le fichier de variables (`tfvars`) spécifique à l'environnement.

**Pour DEV :**
```bash
terraform plan \
  -var-file=environments/dev/terraform.tfvars \
  -out=dev.tfplan
```

### 3. Application (terraform apply)

Appliquez le plan généré.

**Pour DEV :**
```bash
terraform apply "dev.tfplan"
```

---

## 📂 Structure des Fichiers

```
infra-microservices/
├── main.tf              # Code Infrastructure (Appels Modules)
├── variables.tf         # Déclarations des variables (interface)
├── providers.tf         # Configuration Providers (Google)
├── outputs.tf           # Valeurs retournées
├── backend.tf           # Config Backend GCS (sans prefix)
│
└── environments/
    └── dev/
        └── terraform.tfvars  # Valeurs spécifiques DEV
```

## ❓ FAQ / Troubleshooting

### Erreur IDE : "Unexpected attribute environment" dans terraform.tfvars
**Symptôme** : Votre éditeur souligne la variable `environment` (ou d'autres) en rouge dans `environments/dev/terraform.tfvars`.

**Cause** : L'éditeur analyse le fichier `terraform.tfvars` par rapport au répertoire courant (`environments/dev/`), où il ne trouve aucun fichier `.tf` déclarant ces variables. Or, dans notre architecture centralisée, les variables sont déclarées à la racine (`../../variables.tf`).

**Solution** : C'est une erreur de contexte de l'IDE, sans impact sur le fonctionnement.
- Si vous exécutez `terraform plan` depuis la racine comme indiqué, Terraform charge correctement `variables.tf` et les valeurs du fichier `tfvars`.
- **Action** : Vous pouvez ignorer cet avertissement.

### Erreur Backend "Prefix" ou "State lock"
**Symptôme** : Terraform tente d'accéder au mauvais state ou reste bloqué.
**Solution** : Vérifiez que vous avez bien relancé `terraform init` avec le bon `-backend-config="prefix=..."`.
