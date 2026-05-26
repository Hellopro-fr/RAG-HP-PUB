# update_image.md — Procédure manuelle de mise à jour de l'image `opti-moteur-front`

> **Objectif** : mettre à jour l'image Docker de l'app `opti-moteur-front` en production GKE après modification du code.
> **Cible utilisateur** : DevSecOps + Lead Dev métier.
> **Quand utiliser ce fichier** :
> - **Aujourd'hui** : process manuel obligatoire (le pipeline CI/CD GitHub Actions sera mis en place au sprint S5)
> - **Après S5** : ce fichier reste utile pour les rollback manuels et les déploiements hors-pipeline (hotfix, urgence, environnement de test)

---

## 1. Vue d'ensemble du workflow

```
┌─────────────────────────────────────────────────────────────────┐
│ Code modifié dans apps-microservices/opti-moteur-front/         │
└─────────────────────────────────────────────────────────────────┘
                            │
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ 1. Choisir un nouveau tag (jamais réutiliser un tag existant)   │
│    Convention : v<MAJOR>.<MINOR>.<PATCH>-prod (semver)          │
└─────────────────────────────────────────────────────────────────┘
                            │
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ 2. Cloud Build : build + push vers Artifact Registry            │
│    europe-west1-docker.pkg.dev/.../opti-moteur-front:<tag>      │
└─────────────────────────────────────────────────────────────────┘
                            │
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ 3. Mettre à jour le Deployment GKE                              │
│    Option A : kubectl set image (rapide, sans Git)              │
│    Option B : modifier YAML + kubectl apply (tracé dans Git)    │
└─────────────────────────────────────────────────────────────────┘
                            │
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ 4. Suivre le rollout (RollingUpdate, maxUnavailable=0)          │
│    → zero-downtime sur les 2 replicas                           │
└─────────────────────────────────────────────────────────────────┘
                            │
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ 5. Smoketests + post-vérif                                      │
│    Si KO → rollback (cf. §6)                                    │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. Pré-requis et setup

Le setup se découpe en **3 niveaux** selon la fréquence d'exécution :

| Niveau | Quand | Effort | Qui |
|---|---|---|---|
| 🔧 **§2.1 Setup projet GCP** | **UNE SEULE FOIS** par projet GCP | ~10 min | Admin GCP |
| 🔁 **§2.2 Setup poste opérateur** | **UNE SEULE FOIS** par DevSecOps | ~5 min | Chaque DevSecOps |
| 🔄 **§2.3 Activation session** | **À chaque session de build** | ~5 sec | Opérateur |

**Pré-requis universels (chaque session)** :
- ✅ Auth `kubectl` valide (token ADC < 1 h, sinon refresh — cf. `runbook.md` §5 ou `docs/runbooks/gke_kubectl_local.md`)
- ✅ Tunnel SSH vers `manager-vm-dev` actif (si poste local DevSecOps)
- ✅ Code modifié + commité dans la branche cible
- ✅ `cloudbuild.yaml` à jour : `apps-microservices/opti-moteur-front/cloudbuild.yaml`
- ✅ `.gcloudignore` à la racine de `RAG-HP-PUB/`

---

### 🔧 2.1 Setup projet GCP — UNE SEULE FOIS par projet (Admin GCP)

> 🆕 **Matrice d'impact** : Création SA + 4 bindings projet + 1 binding bucket + 1 binding SA Compute + bucket GCS • Périmètre : projet GCP `hellopro-rag-project` • Downtime : aucun • Réversible : ✅ • Risque : 🟢 Faible (rôles minimaux conditionnés) • Validation : DevSecOps + Admin GCP

> **Statut sur `hellopro-rag-project` (2026-05-22)** : ✅ Réalisé. Cette section sert de référence pour réplication sur futurs projets / nouveaux SAs.

**Justification du choix SA dédié + impersonation** (vs clé JSON ou usage direct du SA Compute) :
- Pas de clé JSON exportée (zéro risque de fuite par commit accidentel)
- Audit logs tracent `user → SA` (vs juste `SA` avec clé) → meilleure compliance SOC
- Pas de rotation manuelle de clé tous les 90 jours
- Même SA réutilisable pour la CI/CD GitHub Actions (S5) via Workload Identity Federation
- Alignement avec les bonnes pratiques GCP modernes

#### 2.1.A — Bucket Cloud Build

> ⚠️ Cloud Build utilise un bucket GCS pour stocker le tarball source. Le bucket `gs://<PROJECT>_cloudbuild` est généralement auto-créé par un build précédent, **mais pas toujours en région attendue**.

**Vérifier l'existence** :
```bash
gcloud storage buckets describe gs://hellopro-rag-project_cloudbuild \
  --format="value(name,location)"
```

**Si vide → créer en `europe-west1`** (région du build) :
```bash
gcloud storage buckets create gs://hellopro-rag-project_cloudbuild \
  --project=hellopro-rag-project \
  --location=europe-west1 \
  --uniform-bucket-level-access \
  --default-storage-class=STANDARD
```

> 📝 **Cas réel rencontré le 2026-05-22** : le bucket existait déjà en multi-région `us` (créé par un build précédent hors région). On s'y est appuyé via `--gcs-source-staging-dir` (cf. §4 Étape 1). Pour un nouveau projet, préférer une création explicite en `europe-west1`.

#### 2.1.B — Création du SA + 4 rôles PROJET

```bash
export PROJECT_ID=hellopro-rag-project
export PROJECT_NUMBER=806625052144   # ⚠️ adapter via : gcloud projects describe $PROJECT_ID --format='value(projectNumber)'
export SA_NAME=cicd-opti-moteur-sa
export SA_EMAIL=${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com

# 1. Créer le SA
gcloud iam service-accounts create $SA_NAME \
  --project=$PROJECT_ID \
  --display-name="CI/CD opti-moteur-front (Cloud Build manuel + GitHub Actions WIF)" \
  --description="SA dédié au build/push opti-moteur-front. Impersonation pour manuel, WIF pour CI/CD."

# 2. Rôles PROJET (4 bindings)

# 2.B.1 Lancer/voir les builds Cloud Build
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$SA_EMAIL" \
  --role="roles/cloudbuild.builds.editor"

# 2.B.2 Push image vers Artifact Registry (repo "hellopro")
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$SA_EMAIL" \
  --role="roles/artifactregistry.writer"

# 2.B.3 Upload objects dans le bucket Cloud Build (conditionné au bucket)
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$SA_EMAIL" \
  --role="roles/storage.objectAdmin" \
  --condition='expression=resource.name.startsWith("projects/_/buckets/hellopro-rag-project_cloudbuild"),title=cloudbuild_bucket_only'

# 2.B.4 Appeler les APIs GCP (Cloud Build, Storage, etc.)
# ⚠️ Sans ce rôle, erreur trompeuse : "user is forbidden from accessing the bucket"
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$SA_EMAIL" \
  --role="roles/serviceusage.serviceUsageConsumer"
```

#### 2.1.C — Rôle BUCKET-level (pas project-level)

> ⚠️ **Piège connu** : `roles/storage.legacyBucketReader` ne se grant **pas** au niveau projet (erreur `Role X is not supported for this resource`). Il doit être posé **directement sur le bucket**. Sinon, Cloud Build échoue à `storage.buckets.get` (permission absente d'`objectAdmin`) — même message trompeur "forbidden from accessing the bucket".

```bash
gcloud storage buckets add-iam-policy-binding gs://hellopro-rag-project_cloudbuild \
  --member="serviceAccount:$SA_EMAIL" \
  --role="roles/storage.legacyBucketReader"
```

#### 2.1.D — `actAs` sur le SA Compute Engine (steps Cloud Build)

> ⚠️ **Piège connu** : Cloud Build en mode régional (`--region=europe-west1`) exécute ses steps sous l'identité du **Compute Engine default SA** (`<PROJECT_NUMBER>-compute@developer.gserviceaccount.com`). Le SA submitter doit pouvoir "act as" ce SA, sinon erreur `caller does not have permission to act as service account projects/.../serviceAccounts/<UNIQUE_ID>`.

```bash
gcloud iam service-accounts add-iam-policy-binding \
  ${PROJECT_NUMBER}-compute@developer.gserviceaccount.com \
  --member="serviceAccount:$SA_EMAIL" \
  --role="roles/iam.serviceAccountUser" \
  --project=$PROJECT_ID
```

#### 2.1.E — Vérification finale du setup projet

```bash
# 1. Bindings PROJET du SA (attendu : 4 rôles)
gcloud projects get-iam-policy $PROJECT_ID --format=yaml | grep -B 2 -A 5 cicd-opti-moteur-sa
# Attendu :
#   - artifactregistry.writer
#   - cloudbuild.builds.editor
#   - serviceusage.serviceUsageConsumer
#   - storage.objectAdmin (avec condition cloudbuild_bucket_only)

# 2. Binding BUCKET-level (attendu : legacyBucketReader)
gcloud storage buckets get-iam-policy gs://hellopro-rag-project_cloudbuild --format=yaml \
  | grep -B 1 -A 3 cicd-opti-moteur-sa

# 3. Binding SA Compute-level (attendu : serviceAccountUser)
gcloud iam service-accounts get-iam-policy \
  ${PROJECT_NUMBER}-compute@developer.gserviceaccount.com \
  --project=$PROJECT_ID
```

---

### 🔁 2.2 Setup poste opérateur — UNE SEULE FOIS par DevSecOps

> 🆕 **Matrice d'impact** : Configuration gcloud locale + 1 binding IAM `tokenCreator` sur le SA • Périmètre : poste local + SA `cicd-opti-moteur-sa` • Downtime : aucun • Réversible : ✅ • Risque : 🟢 Faible

#### 2.2.A — Côté admin GCP (1 ligne par nouvel opérateur DevSecOps)

```bash
export SA_EMAIL=cicd-opti-moteur-sa@hellopro-rag-project.iam.gserviceaccount.com
export YOUR_USER=aandrianirina@hellopro.fr   # ⚠️ adapter à l'opérateur ajouté

gcloud iam service-accounts add-iam-policy-binding $SA_EMAIL \
  --project=hellopro-rag-project \
  --member="user:$YOUR_USER" \
  --role="roles/iam.serviceAccountTokenCreator"
```

#### 2.2.B — Côté poste opérateur (config gcloud dédiée)

Le poste DevSecOps a typiquement plusieurs identités gcloud. **On NE bascule PAS le compte `active`** → on crée une **config gcloud dédiée** qui pose l'impersonation, et on l'active à chaque session de build.

```bash
# 1. Créer une config gcloud nommée "cloudbuild-cicd"
gcloud config configurations create cloudbuild-cicd

# 2. L'activer
gcloud config configurations activate cloudbuild-cicd

# 3. Configurer l'identité user (acteur de l'impersonation)
gcloud config set account aandrianirina@hellopro.fr   # ⚠️ adapter
gcloud config set project hellopro-rag-project

# 4. Configurer l'impersonation du SA cicd-opti-moteur-sa
gcloud config set auth/impersonate_service_account \
  cicd-opti-moteur-sa@hellopro-rag-project.iam.gserviceaccount.com

# 5. Si pas déjà fait : auth user (navigateur)
gcloud auth login

# 6. Vérifier la config
gcloud config list
# Doit afficher :
#   [auth]
#   impersonate_service_account = cicd-opti-moteur-sa@hellopro-rag-project.iam.gserviceaccount.com
#   [core]
#   account = aandrianirina@hellopro.fr
#   project = hellopro-rag-project
```

---

### 🔄 2.3 Activation session — À chaque session de build (5 sec)

#### ========================================================== ####
#### =================ON COMMENCE ICI POUR UN BUILD ============ ####
#### ========================================================== ####

```bash
# 1. Activer la config dédiée (impersonation sticky)
gcloud config configurations activate cloudbuild-cicd

# 2. (Optionnel) Vérifier que l'identité réelle des appels API est le SA
TOKEN=$(gcloud auth print-access-token)
curl -s "https://www.googleapis.com/oauth2/v3/tokeninfo?access_token=$TOKEN" | grep '"email"'
# Attendu : "email": "cicd-opti-moteur-sa@hellopro-rag-project.iam.gserviceaccount.com"
```

> ✅ Le token retourné est celui du SA `cicd-opti-moteur-sa`, **émis pour le compte du user** (le user a permission via `tokenCreator`). Toutes les commandes `gcloud` qui suivent s'exécutent **sous l'identité du SA**.

**Après le build — revenir à la config par défaut** :
```bash
gcloud config configurations activate default
```

---

### 2.4 Alternative déconseillée — Clé JSON exportée

> ⚠️ **À NE PAS UTILISER sauf cas exceptionnel** (ex: VM Manager sans accès interactif `gcloud auth login`).
>
> Inconvénients : clé sur disque (fuite possible si commit accidentel), rotation manuelle tous les 90 jours, audit logs ne tracent que le SA (pas le user qui a déclenché).

Si vraiment nécessaire (validé par DevSecOps + admin) :

```bash
# 1. Admin GCP génère une clé JSON (1 fois par poste)
gcloud iam service-accounts keys create ~/cicd-opti-moteur-sa-key.json \
  --iam-account=cicd-opti-moteur-sa@hellopro-rag-project.iam.gserviceaccount.com \
  --project=hellopro-rag-project

# 2. Restreindre les permissions du fichier sur le poste
chmod 600 ~/cicd-opti-moteur-sa-key.json

# 3. À chaque session, activer le SA via la clé
gcloud auth activate-service-account \
  --key-file=$HOME/cicd-opti-moteur-sa-key.json

# 4. Lancer le build (commande §4 inchangée)

# 5. Après le build, désactiver le SA (préserver l'identité par défaut)
gcloud auth revoke cicd-opti-moteur-sa@hellopro-rag-project.iam.gserviceaccount.com
```

> ⚠️ **NE JAMAIS** committer `cicd-opti-moteur-sa-key.json` dans Git. À ajouter au `.gitignore` global du poste.
> Procédure de **rotation tous les 90 jours** obligatoire : `gcloud iam service-accounts keys delete <KEY_ID>` + recréation.

---

### 2.5 Migration vers WIF en S5 (CI/CD GitHub Actions)

Le sprint S5 réutilise **le même SA** `cicd-opti-moteur-sa` avec tous ses rôles, mais l'authentification GitHub Actions → SA passe par **Workload Identity Federation** (WIF) :
- Le runner GitHub Actions est autorisé à impersoner le SA via un Workload Identity Pool GCP
- Aucune clé JSON exportée dans GitHub Secrets
- Audit logs tracent `GitHub Actions run → SA`

Seul ajout à faire en S5 : configuration du Workload Identity Pool + provider OIDC GitHub. Tous les rôles SA sont déjà en place (§2.1).

---

### 2.6 Récap rôles IAM (post-setup complet)

| Identité | Rôle | Scope | Justification |
|---|---|---|---|
| `aandrianirina@hellopro.fr` (user) | `iam.serviceAccountTokenCreator` | SA `cicd-opti-moteur-sa` | Acteur de l'impersonation (§2.2.A) |
| `cicd-opti-moteur-sa` (SA) | `cloudbuild.builds.editor` | Projet | Lancer/voir les builds (§2.1.B.1) |
| `cicd-opti-moteur-sa` (SA) | `artifactregistry.writer` | Projet | Push image (§2.1.B.2) |
| `cicd-opti-moteur-sa` (SA) | `storage.objectAdmin` (conditionné) | Projet → bucket cloudbuild | Upload tarball source (§2.1.B.3) |
| `cicd-opti-moteur-sa` (SA) | `serviceusage.serviceUsageConsumer` | Projet | Appeler les APIs GCP (§2.1.B.4) |
| `cicd-opti-moteur-sa` (SA) | `storage.legacyBucketReader` | Bucket `_cloudbuild` | `storage.buckets.get` manquant dans `objectAdmin` (§2.1.C) |
| `cicd-opti-moteur-sa` (SA) | `iam.serviceAccountUser` | SA `<PROJECT_NUMBER>-compute@developer` | `actAs` SA Compute (steps Cloud Build régionaux, §2.1.D) |
| `hp-sa-gcs-data-job@...` (SA backup) | `storage.objectAdmin` (autres buckets) | Buckets backup | **Hors scope Cloud Build** — réservé aux backups GCS |

---

## 3. Stratégie de tag

> ⚠️ **Règle d'or** : ne **JAMAIS** réutiliser un tag existant. Kubernetes a `imagePullPolicy: IfNotPresent` → si le tag est identique, le nœud GKE garde l'ancienne image en cache et ne pull pas la nouvelle. Le rollout passe sans rien changer.

### Convention recommandée — Semver `vMAJOR.MINOR.PATCH-prod`

| Type de changement | Tag | Exemple |
|---|---|---|
| Hotfix / fix critique | bump PATCH | `v1.0.0-prod` → `v1.0.1-prod` |
| Nouvelle feature compatible | bump MINOR | `v1.0.1-prod` → `v1.1.0-prod` |
| Breaking change | bump MAJOR | `v1.1.0-prod` → `v2.0.0-prod` |
| Test / preview | suffixe spécial | `v1.0.0-rc1`, `v1.0.0-test` |

### Alternative — SHA Git court (pour CI/CD futur)

Pour le pipeline GitHub Actions S5, on utilisera plutôt `<sha-7-chars>` (`a1b2c3d`). Pour le manuel, le semver est plus lisible.

### Lister les tags existants avant de choisir

```bash
gcloud artifacts docker images list \
  europe-west1-docker.pkg.dev/hellopro-rag-project/hellopro/opti-moteur-front \
  --include-tags
```

---

#### ========================================================== ####
#### ======================== OU ICI ========================= ####
#### ========================================================== ####

## 4. Procédure étape par étape

### Étape 1 — Build + push de la nouvelle image

> 🆕 **Matrice d'impact** : Création image dans Artifact Registry • Périmètre : projet GCP `hellopro-rag-project` • Downtime : aucun (build dans GCP, l'ancienne image reste active sur GKE) • Réversible : ✅ (`gcloud artifacts docker images delete <image>:<tag>`) • Risque : 🟢 Faible (anciennes images intactes, juste un nouveau tag) • Validation : DevSecOps

**Pré-checks** (recommandé : impersonation via config dédiée, cf. §2.3) :
```bash
# 1. Activer la config Cloud Build (impersonation SA cicd-opti-moteur-sa)
gcloud config configurations activate cloudbuild-cicd

# 2. (Optionnel) Vérifier que l'identité réelle des appels API est le SA
TOKEN=$(gcloud auth print-access-token)
curl -s "https://www.googleapis.com/oauth2/v3/tokeninfo?access_token=$TOKEN" | grep '"email"'
# Attendu : "email": "cicd-opti-moteur-sa@hellopro-rag-project.iam.gserviceaccount.com"

# 3. Vérifier que le tag à utiliser n'existe pas déjà
NEW_TAG="v1.0.1-prod"   # ⚠️ adapter (cf. §3 convention semver, ex: v1.0.1-220526-prod avec date)
gcloud artifacts docker images list \
  europe-west1-docker.pkg.dev/hellopro-rag-project/hellopro/opti-moteur-front \
  --include-tags \
  --filter="tags=$NEW_TAG"
# Attendu : aucun résultat. Sinon → choisir un autre tag (la réutilisation ne push pas, cf. §7 FAQ)

# 4. Projet actif
gcloud config get-value project   # doit être hellopro-rag-project
```

**Lancer le build** depuis **`RAG-HP-PUB/`** :
```bash
cd /h/Works/Hellopro/account-pro/RAG-HP-PUB

NEW_TAG="v1.0.1-prod"   # ⚠️ adapter (cf. §3 convention semver)

gcloud builds submit . \
  --config=apps-microservices/opti-moteur-front/cloudbuild.yaml \
  --project=hellopro-rag-project \
  --region=europe-west1 \
  --gcs-source-staging-dir=gs://hellopro-rag-project_cloudbuild/source \
  --substitutions=_TAG=$NEW_TAG
```

> ⚠️ **Flag `--gcs-source-staging-dir` obligatoire si le bucket existant n'est pas en `europe-west1`**. Sans lui, gcloud tente une auto-création régionale qui peut échouer avec un message trompeur (`forbidden from accessing the bucket`). Avec lui, on force l'usage du bucket existant + sous-dossier `source/`.
>
> Durée typique : **1-3 min** (tarball + pull base + pip install + push image).

**Post-vérif** :
```bash
gcloud artifacts docker images list \
  europe-west1-docker.pkg.dev/hellopro-rag-project/hellopro/opti-moteur-front \
  --include-tags \
  --filter="tags=$NEW_TAG"
# Attendu : 1 ligne avec le tag, digest sha256:..., create time récent.
```

---

### Étape 2 — Mettre à jour l'image dans le Deployment GKE

#### Option A — `kubectl set image` (rapide, sans modif Git)

> ✏️ **Matrice d'impact** : Modification image Deployment + déclenchement RollingUpdate • Périmètre : ns `moteur-recherche` • Downtime : aucun (maxUnavailable=0, rolling sur 2 replicas) • Réversible : ✅ (`kubectl rollout undo`) • Risque : 🟡 Moyen (nouveau code en prod, peut révéler bugs) • Validation : DevSecOps + Lead Dev

```bash
NEW_TAG="v1.0.1-prod"   # ⚠️ adapter, identique au build

kubectl set image deployment/opti-moteur-front \
  opti-moteur-front=europe-west1-docker.pkg.dev/hellopro-rag-project/hellopro/opti-moteur-front:$NEW_TAG \
  -n moteur-recherche
```
> Attendu : `deployment.apps/opti-moteur-front image updated`

**Avantage** : rapide (1 commande, pas de modif Git).
**Inconvénient** : drift entre l'état réel et le manifest `manifests/22-opti-moteur-deployment.yaml` versionné. À corriger ensuite via Option B (apply le manifest mis à jour) pour garder Git source of truth.

---

#### Option B — Modifier le YAML + `kubectl apply` (tracé Git)

> ✏️ **Matrice d'impact** : identique à l'Option A.

1. **Modifier** `manifests/22-opti-moteur-deployment.yaml`, ligne `image:` :
   ```diff
   -          image: europe-west1-docker.pkg.dev/hellopro-rag-project/hellopro/opti-moteur-front:v1.0.0-prod
   +          image: europe-west1-docker.pkg.dev/hellopro-rag-project/hellopro/opti-moteur-front:v1.0.1-prod
   ```

2. **Commit Git** (toujours, pour traçabilité) :
   ```bash
   git add manifests/22-opti-moteur-deployment.yaml
   git commit -m "chore(opti-moteur-front): bump image to v1.0.1-prod"
   ```

3. **Apply** :
   ```bash
   kubectl diff -f manifests/22-opti-moteur-deployment.yaml
   kubectl apply -f manifests/22-opti-moteur-deployment.yaml
   ```

**Avantage** : Git = source of truth. Le manifest reflète l'état réel.
**Inconvénient** : 2-3 étapes au lieu de 1.

> **Recommandation** : Option B pour les changements importants. Option A pour hotfix d'urgence (commit le manifest plus tard).

---

### Étape 3 — Suivre le rollout

```bash
kubectl rollout status deployment/opti-moteur-front -n moteur-recherche --timeout=5m
```
> Attendus (séquence ~30-90s) :
> - `Waiting for deployment "opti-moteur-front" rollout to finish: 1 out of 2 new replicas have been updated...`
> - `Waiting for deployment "opti-moteur-front" rollout to finish: 1 of 2 updated replicas are available...`
> - `deployment "opti-moteur-front" successfully rolled out`

**Comportement RollingUpdate** (avec `maxSurge: 1`, `maxUnavailable: 0`) :
1. K8s crée 1 nouveau pod avec la nouvelle image (3 pods total temporairement)
2. Quand le nouveau pod est `Ready` → K8s supprime 1 ancien pod
3. K8s crée un 2ᵉ nouveau pod (3 pods total)
4. Quand le 2ᵉ nouveau pod est `Ready` → K8s supprime le dernier ancien pod
5. → `deployment successfully rolled out`

**Vérifier les pods** :
```bash
kubectl get pods -n moteur-recherche -l app.kubernetes.io/name=opti-moteur-front
# Attendu : 2 pods Running 1/1, AGE récent

kubectl get rs -n moteur-recherche
# Attendu : 2 ReplicaSet — l'ancien (DESIRED 0), le nouveau (DESIRED 2)
```

---

### Étape 4 — Smoketests post-rollout

```bash
# 1. /  -> liveness
kubectl run -n moteur-recherche --rm -i --restart=Never \
  --image=curlimages/curl tmp-root -- \
  curl -sS http://opti-moteur-front:8570/

# 2. /health -> readiness, cascade Typesense + Milvus
kubectl run -n moteur-recherche --rm -i --restart=Never \
  --image=curlimages/curl tmp-health -- \
  curl -sS http://opti-moteur-front:8570/health
# Attendu : {"status":"ok","typesense":"ok","milvus":"ok"}

# 3. Logs récents pour vérifier qu'il n'y a pas d'erreur
kubectl logs -n moteur-recherche -l app.kubernetes.io/name=opti-moteur-front --tail=30 --all-containers
```

---

## 5. Vérification que l'image utilisée correspond bien au nouveau tag

Pour s'assurer que les pods utilisent bien la nouvelle image (et pas une cache d'ancien tag) :

```bash
# Image utilisée dans la config Deployment
kubectl get deployment opti-moteur-front -n moteur-recherche \
  -o jsonpath='{.spec.template.spec.containers[0].image}'
echo ""

# Image réellement utilisée par les pods Running
kubectl get pods -n moteur-recherche -l app.kubernetes.io/name=opti-moteur-front \
  -o jsonpath='{.items[*].spec.containers[0].image}'
echo ""
```
> Les 2 commandes doivent retourner exactement la même valeur, contenant le `NEW_TAG`.

---

## 6. Rollback en cas de problème

> ❌ **Matrice d'impact rollback** : Modification image Deployment vers version précédente • Périmètre : ns `moteur-recherche` • Downtime : aucun (RollingUpdate inversé) • Réversible : ✅ (re-rollout vers nouveau tag) • Risque : 🟡 Moyen (urgence) • Validation : DevSecOps

### Cas 1 — Le rollout est en cours et échoue

```bash
# Annuler le rollout en cours (revient à l'image précédente)
kubectl rollout undo deployment/opti-moteur-front -n moteur-recherche

# Vérifier
kubectl rollout status deployment/opti-moteur-front -n moteur-recherche
```

### Cas 2 — Le rollout a réussi mais le nouveau code a un bug

```bash
# Voir l'historique des rollouts
kubectl rollout history deployment/opti-moteur-front -n moteur-recherche

# Revenir à la révision précédente
kubectl rollout undo deployment/opti-moteur-front -n moteur-recherche

# Ou revenir à une révision spécifique
kubectl rollout undo deployment/opti-moteur-front -n moteur-recherche --to-revision=<N>
```

### Cas 3 — Image cassée à supprimer d'Artifact Registry

> ⚠️ Ne **JAMAIS** supprimer une image utilisée par un Deployment Running. Vérifier d'abord avec la commande §5.

```bash
gcloud artifacts docker images delete \
  europe-west1-docker.pkg.dev/hellopro-rag-project/hellopro/opti-moteur-front:<bad-tag> \
  --quiet
```

---

## 7. Edge cases et FAQ

### Q : J'ai pushé une image avec le même tag, le rollout ne change rien

**Cause** : `imagePullPolicy: IfNotPresent` (default sur tag non `:latest`). Les nodes ont l'ancienne image en cache.

**Solution recommandée** : utiliser un nouveau tag (ne jamais réutiliser).

**Solution d'urgence** (déconseillée mais possible) :
```bash
# Forcer le redémarrage des pods (pull se fera car kubelet revérifie)
kubectl rollout restart deployment/opti-moteur-front -n moteur-recherche
```

### Q : Le rollout échoue avec `ImagePullBackOff`

**Causes possibles** :
1. Tag inexistant dans Artifact Registry → vérifier orthographe + `gcloud artifacts docker images list ... --include-tags`
2. SA des nodes GKE n'a pas `roles/artifactregistry.reader` sur le repo `hellopro` → ajouter le rôle au SA des nodes
3. Repo Artifact Registry incorrect → vérifier l'URL complète

```bash
# Diagnostic
kubectl describe pods -n moteur-recherche -l app.kubernetes.io/name=opti-moteur-front | grep -A 5 -i pull
```

### Q : Le rollout dure trop longtemps (timeout 5m)

**Cause probable** : `readinessProbe` ne passe pas (l'app ne répond pas à `/health` dans le délai).

**Diagnostic** :
```bash
kubectl describe pods -n moteur-recherche -l app.kubernetes.io/name=opti-moteur-front | tail -20
kubectl logs -n moteur-recherche -l app.kubernetes.io/name=opti-moteur-front --tail=50
```

Vérifier :
- Que Typesense est joignable (`kubectl exec ... wget http://typesense:8108/health`)
- Que Milvus est joignable (creds bons)
- Que la nouvelle version du code n'a pas cassé `/health`

### Q : Comment voir l'historique des images déployées ?

```bash
kubectl rollout history deployment/opti-moteur-front -n moteur-recherche

# Détail d'une révision
kubectl rollout history deployment/opti-moteur-front -n moteur-recherche --revision=2
```

### Q : Peut-on faire un canary deploy (1 seul replica avec la nouvelle image) ?

Oui, mais ce n'est pas géré nativement par Deployment standard. Options :
- Dupliquer le Deployment avec un Deployment-canary (1 replica, même Service)
- Utiliser ArgoCD + Argo Rollouts (à envisager post-S5 pour les changements critiques)

---

## 8. Commandes one-liner mémo (à garder dans le terminal)

```bash
# Variables
export PROJECT=hellopro-rag-project
export REGION=europe-west1
export REPO=hellopro
export IMAGE=opti-moteur-front
export NS=moteur-recherche
export NEW_TAG=v1.0.1-prod   # ⚠️ adapter

# Auth via impersonation SA cicd-opti-moteur-sa
gcloud config configurations activate cloudbuild-cicd

# Build + push (sous l'identité du SA via impersonation)
cd /h/Works/Hellopro/account-pro/RAG-HP-PUB && \
gcloud builds submit . \
  --config=apps-microservices/${IMAGE}/cloudbuild.yaml \
  --project=${PROJECT} --region=${REGION} \
  --gcs-source-staging-dir=gs://${PROJECT}_cloudbuild/source \
  --substitutions=_TAG=${NEW_TAG}

# Apres le build, revenir a la config par defaut
gcloud config configurations activate default

# Update + suivre rollout (option A : kubectl set image)
kubectl set image deployment/${IMAGE} \
  ${IMAGE}=${REGION}-docker.pkg.dev/${PROJECT}/${REPO}/${IMAGE}:${NEW_TAG} \
  -n ${NS} && \
kubectl rollout status deployment/${IMAGE} -n ${NS} --timeout=5m

# Vérif image utilisée
kubectl get pods -n ${NS} -l app.kubernetes.io/name=${IMAGE} \
  -o jsonpath='{.items[*].spec.containers[0].image}' && echo ""

# Smoketest
kubectl run -n ${NS} --rm -i --restart=Never \
  --image=curlimages/curl tmp-test -- \
  curl -sS http://${IMAGE}:8570/health

# Rollback urgence
kubectl rollout undo deployment/${IMAGE} -n ${NS}
```

---

## 9. Procédure résumée (cheat sheet)

| Étape | Commande clé | Durée |
|---|---|---|
| 0. Activer config | `gcloud config configurations activate cloudbuild-cicd` | 1 s |
| 1. Build + push | `gcloud builds submit . --config=... --region=europe-west1 --gcs-source-staging-dir=gs://hellopro-rag-project_cloudbuild/source --substitutions=_TAG=<NEW_TAG>` | 1-3 min |
| 2. Retour config | `gcloud config configurations activate default` | 1 s |
| 3. Update Deployment | `kubectl set image deployment/opti-moteur-front opti-moteur-front=<image>:<NEW_TAG> -n moteur-recherche` | 1 s |
| 4. Suivre rollout | `kubectl rollout status deployment/opti-moteur-front -n moteur-recherche` | 30-90 s |
| 5. Smoketest | `kubectl run --rm ...curlimages/curl... -- curl -sS http://opti-moteur-front:8570/health` | 5 s |
| 6. (si KO) Rollback | `kubectl rollout undo deployment/opti-moteur-front -n moteur-recherche` | 30 s |

**Total typique** : ~5 min pour une mise à jour propre.

---

## 10. Documents associés

- `runbook.md` — runbook global d'exploitation (procédures macro)
- `sprints/sprint_003_opti_moteur_front.md` — détails du déploiement initial
- `sprints/sprint_005_cicd.md` — *(à venir)* pipeline CI/CD GitHub Actions automatisant ces étapes
- `debug.md` — historique incidents (consulter avant un build pour éviter les pièges connus)
- `apps-microservices/opti-moteur-front/cloudbuild.yaml` — config du build Cloud Build
- `RAG-HP-PUB/.gcloudignore` — limite l'upload Cloud Build

---

## 11. Historique des leçons apprises

### 2026-05-22 — Premier build CI/CD via SA dédié `cicd-opti-moteur-sa`

Premier build manuel via le SA dédié (au lieu du SA admin). Plusieurs pièges rencontrés et résolus, à appliquer en setup initial pour les prochains projets :

| Symptôme erreur | Cause root | Fix |
|---|---|---|
| `forbidden from accessing the bucket [..._cloudbuild]. Please check ... serviceusage.services.use` | SA manque `roles/serviceusage.serviceUsageConsumer` (appel API GCP) | §2.1.B.4 — binding projet |
| `Role roles/storage.legacyBucketReader is not supported for this resource` | Rôle bucket-level granté par erreur au niveau projet | §2.1.C — binding directement sur le bucket |
| `forbidden from accessing the bucket` (persistant après serviceUsageConsumer) | `storage.objectAdmin` n'inclut **pas** `storage.buckets.get` | §2.1.C — `roles/storage.legacyBucketReader` sur le bucket |
| `PERMISSION_DENIED: caller does not have permission to act as service account projects/.../<UNIQUE_ID>` | SA manque `actAs` sur le SA Compute Engine (utilisé par Cloud Build régional) | §2.1.D — `roles/iam.serviceAccountUser` sur SA Compute |
| `gcloud builds submit` tente une auto-création régionale qui échoue silencieusement | Bucket existant en multi-région `us`, build en `europe-west1` | §4 Étape 1 — flag `--gcs-source-staging-dir` obligatoire |

**Build réussi** : `opti-moteur-front:v1.0.1-220526-prod` en 1m18s.

**Rôles finaux du SA `cicd-opti-moteur-sa`** : cf. tableau §2.6.
