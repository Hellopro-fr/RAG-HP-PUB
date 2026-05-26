# sprint_003 — App `opti-moteur-front` (Build Cloud Build + Deployment + Service ClusterIP)

> **Sprint S3** du plan de migration. Voir `../plan.md`, `../runbook.md`, `../CLAUDE.md` pour le contexte.

---

## 1. Objectif

Déployer l'application FastAPI `opti-moteur-front` en production sur GKE :
1. **Builder l'image Docker** via **Cloud Build** (1ʳᵉ fois manuellement, le pipeline CI/CD GitHub Actions sera S5)
2. **Push vers Artifact Registry** : tag `v1.0.0-prod`
3. Créer **Secret** Milvus (creds), **ConfigMap** (params non-sensibles), **Deployment** (2 replicas), **Service ClusterIP** (port 8570)
4. Tests bout-en-bout intra-cluster : app ↔ Typesense ↔ Milvus ↔ embedding VM GPU

**Hors périmètre** :
- Exposition externe (S4 — Internal LoadBalancer + annotation global access)
- Pipeline GitHub Actions (S5)
- Re-ingestion catalogue (D16, à charge des devs)

---

## 2. Dépendances

- ✅ S1 + S2 terminés (namespace, SA, NetPol, Typesense, Service `typesense:8108`)
- ✅ Image base Python 3.10-slim disponible publiquement
- ⏳ User Milvus prod existant + son mot de passe (à fournir au moment de l'apply Secret)
- ⏳ Auth `gcloud` configurée (ADC user) avec `roles/cloudbuild.builds.editor` + `roles/artifactregistry.writer`

---

## 3. Principe

| Principe | Application S3 |
|---|---|
| Build dans GCP, pas en local | Cloud Build : pas de pull image massif sur poste, build dans le VPC, push direct Artifact Registry |
| Stateless = HA simple | 2 replicas, Service ClusterIP round-robin natif. Pas de session sticky requise |
| Probes split (D20) | Liveness `GET /` (light, redémarre seulement si l'app Python crash). Readiness `GET /health` (vérifie Typesense + Milvus en cascade — pod retiré du Service si dépendance KO sans restart) |
| Secrets jamais en clair | Secret `opti-moteur-milvus-creds` créé via `read -s` + `kubectl create --dry-run \| apply`. Secret `typesense-api-key` (S2) réutilisé tel quel |
| ConfigMap pour params non-sensibles | `TYPESENSE_HOST`, `TYPESENSE_PORT`, `MILVUS_COLLECTION`, `EMBEDDING_SERVICE_URL`, etc. |
| FinOps | Resources `requests=200m/512Mi`, `limits=1000m/1Gi` (D16 confirmé Q16) |
| Tagging | Image tag `v1.0.0-prod` (D figée Q14, sémantique pour 1ʳᵉ release prod) |

---

## 4. Discovery (lecture seule)

> 📖 **Aucun impact prod.**

```bash
# 4.1 Vérifier que les ressources S1 + S2 sont OK
kubectl get all,secret -n moteur-recherche

# 4.2 Vérifier l'auth Cloud Build / Artifact Registry
gcloud auth list
gcloud config get-value project   # doit être hellopro-rag-project (ou explicit override avec --project)
gcloud artifacts repositories list --location=europe-west1 --project=hellopro-rag-project
# Attendu : repo "hellopro" présent

# 4.3 Vérifier que le Dockerfile et le build context sont OK
ls -la ../../../../../../apps-microservices/opti-moteur-front/Dockerfile
# (depuis le dossier opti-moteur-recherche/, le Dockerfile est à 6 niveaux au-dessus)
# OU utiliser le chemin absolu depuis la racine du repo
```

---

## 5. Build image Docker via Cloud Build

### 5.1 Pré-requis : créer `cloudbuild.yaml` dans le service

Le Dockerfile a besoin du **repo root comme build context** (cf. ligne `COPY apps-microservices/opti-moteur-front/...` dans le Dockerfile). On utilise un fichier `cloudbuild.yaml` qui configure explicitement le build avec le bon contexte.

**Fichier à créer** : `apps-microservices/opti-moteur-front/cloudbuild.yaml`

```yaml
# cloudbuild.yaml — Build de l'image opti-moteur-front avec context=repo root
# Usage :
#   gcloud builds submit . \
#     --config=apps-microservices/opti-moteur-front/cloudbuild.yaml \
#     --project=hellopro-rag-project \
#     --region=europe-west1 \
#     --substitutions=_TAG=v1.0.0-prod
substitutions:
  _IMAGE: europe-west1-docker.pkg.dev/hellopro-rag-project/hellopro/opti-moteur-front
  _TAG: v1.0.0-prod
options:
  logging: CLOUD_LOGGING_ONLY
steps:
  - name: gcr.io/cloud-builders/docker
    args:
      - build
      - --tag=${_IMAGE}:${_TAG}
      - --file=apps-microservices/opti-moteur-front/Dockerfile
      - .
  - name: gcr.io/cloud-builders/docker
    args:
      - push
      - ${_IMAGE}:${_TAG}
images:
  - ${_IMAGE}:${_TAG}
```

**Matrice d'impact (création du fichier `cloudbuild.yaml`)** : 🆕 Création • Périmètre : repo Git (fichier source) • Downtime : aucun • Réversible : ✅ • Risque : 🟢 Faible • Validation : Aucune (fichier de build, pas de modif de l'app)

---

### 5.2 Commande Cloud Build

> 🆕 **Matrice d'impact** : Création image Docker dans Artifact Registry • Périmètre : projet GCP `hellopro-rag-project` • Downtime : aucun (build dans GCP) • Réversible : ✅ (`gcloud artifacts docker images delete <image>:<tag>`) • Risque : 🟢 Faible (image taguée, autres tags non touchés) • Validation : DevSecOps
> Coût : Cloud Build = ~5-10 min × 0,003 $/min = ~0,03 $ par build. Stockage Artifact Registry = ~0,1 $/Go/mois.

**Pré-checks** :
```bash
# Auth GCP active
gcloud auth list | grep "(active)"

# Le projet est bien hellopro-rag-project
gcloud config set project hellopro-rag-project

# L'image n'existe pas déjà avec ce tag (sinon écrasement)
gcloud artifacts docker images list \
  europe-west1-docker.pkg.dev/hellopro-rag-project/hellopro \
  --filter="package=opti-moteur-front" \
  --include-tags
# Attendu : aucun résultat avec tag v1.0.0-prod
```

**Lancer le build** depuis **`RAG-HP-PUB/`** (build context aligné sur les chemins du Dockerfile) :
```bash
cd /h/Works/Hellopro/account-pro/RAG-HP-PUB

gcloud builds submit . \
  --config=apps-microservices/opti-moteur-front/cloudbuild.yaml \
  --project=hellopro-rag-project \
  --region=europe-west1 \
  --substitutions=_TAG=v1.0.0-prod
```

> ⚠️ **Important** : le build context **doit** être `RAG-HP-PUB/` (pas `account-pro/`).
> Le Dockerfile fait `COPY apps-microservices/opti-moteur-front/...`, ce chemin n'existe que depuis `RAG-HP-PUB/`. Cf. incident `debug.md #005`.
>
> Un fichier `.gcloudignore` à la racine de `RAG-HP-PUB/` réduit l'upload (~quelques Mo au lieu de ~975 Mo).

> Durée typique : 3-8 min (pull base image + pip install + push image).
> Suivi : URL Cloud Build affichée au début, ou via console GCP → Cloud Build → History.

**Post-vérif** :
```bash
# L'image est dans Artifact Registry avec le bon tag
gcloud artifacts docker images list \
  europe-west1-docker.pkg.dev/hellopro-rag-project/hellopro/opti-moteur-front \
  --include-tags
# Attendu : 1 ligne avec tag v1.0.0-prod, digest sha256:..., create time récent
```

⚠️ **Attention** : si le build échoue avec "Permission denied" pendant le push → vérifier que le SA de Cloud Build (`<PROJECT_NUMBER>@cloudbuild.gserviceaccount.com`) a le rôle `roles/artifactregistry.writer` sur le repo `hellopro`.

---

## 6. Manifests à créer

### 6.1 `20-opti-moteur-secret-milvus.yaml` — Secret Milvus (TEMPLATE doc)

> ⚠️ **Template documentaire — NE PAS APPLIQUER VIA `kubectl apply -f`.** Réelle création via one-liner étape 7.1.

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: opti-moteur-milvus-creds
  namespace: moteur-recherche
  labels:
    app.kubernetes.io/name: opti-moteur-front
    app.kubernetes.io/managed-by: manifest
    environment: prod
    owner: devsecops
    cost-center: ia-rag
    app: opti-moteur-recherche
type: Opaque
stringData:
  zilliz-user: "<MILVUS_USER>"          # user dédié, fourni à l'apply
  zilliz-password: "<MILVUS_PASSWORD>"  # mot de passe, JAMAIS commit
```

**Matrice d'impact** : 🆕 Création Secret • Périmètre : ns `moteur-recherche` • Downtime : aucun • Réversible : ✅ • Risque : 🟢 (creds jamais sur disque persistant) • Validation : DevSecOps

---

### 6.2 `21-opti-moteur-configmap.yaml` — ConfigMap params non-sensibles

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: opti-moteur-config
  namespace: moteur-recherche
  labels:
    app.kubernetes.io/name: opti-moteur-front
    app.kubernetes.io/managed-by: manifest
    environment: prod
    owner: devsecops
    cost-center: ia-rag
    app: opti-moteur-recherche
data:
  # --- Milvus connection (creds dans Secret opti-moteur-milvus-creds) ---
  ZILLIZ_URI: "milvus-prod.milvus-prod.svc.cluster.local"
  ZILLIZ_PORT: "19530"
  MILVUS_COLLECTION: "produits_3"

  # --- Typesense connection (API key dans Secret typesense-api-key, créé S2) ---
  TYPESENSE_HOST: "typesense"
  TYPESENSE_PORT: "8108"
  TYPESENSE_PROTOCOL: "http"
  TYPESENSE_COLLECTION: "produits_prod"
  TYPESENSE_CONNECTION_TIMEOUT: "60"

  # --- Embedding service (VM GPU us-east4 via VPC) ---
  EMBEDDING_SERVICE_URL: "http://10.11.0.2:8555"
  EMBEDDING_TIMEOUT: "10"
  EMBEDDING_DIMENSION: "1024"

  # --- Recherche (params métier, alignés défauts credentials.py POC) ---
  HNSW_EF_SEARCH: "128"
  RERANK_W_VECTOR: "0.55"
  RERANK_W_BM25: "0.10"
  RERANK_W_NAME: "0.25"
  RERANK_W_CAT: "0.10"
  CAT_FILTER_THRESHOLD: "0.30"
  CAT_FILTER_TOP_N: "3"
  CAT_PREFIX_LOOKAHEAD: "2"
  CANDIDATES_TOP_K: "50"
  DEFAULT_TOP_K: "10"

  # --- Service ---
  SERVICE_PORT: "8570"
```

**Matrice d'impact** : 🆕 Création ConfigMap • Périmètre : ns `moteur-recherche` • Downtime : aucun • Réversible : ✅ • Risque : 🟢 (aucune valeur sensible) • Validation : DevSecOps

---

### 6.3 `22-opti-moteur-deployment.yaml` — Deployment 2 replicas

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: opti-moteur-front
  namespace: moteur-recherche
  labels:
    app.kubernetes.io/name: opti-moteur-front
    app.kubernetes.io/managed-by: manifest
    environment: prod
    owner: devsecops
    cost-center: ia-rag
    app: opti-moteur-recherche
spec:
  replicas: 2
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0   # zero-downtime sur deploy CI/CD (S5)
  selector:
    matchLabels:
      app.kubernetes.io/name: opti-moteur-front
      app: opti-moteur-recherche
  template:
    metadata:
      labels:
        app.kubernetes.io/name: opti-moteur-front
        app: opti-moteur-recherche
        environment: prod
    spec:
      serviceAccountName: opti-moteur-sa
      terminationGracePeriodSeconds: 30
      containers:
        - name: opti-moteur-front
          image: europe-west1-docker.pkg.dev/hellopro-rag-project/hellopro/opti-moteur-front:v1.0.0-prod
          imagePullPolicy: IfNotPresent
          ports:
            - containerPort: 8570
              name: http
              protocol: TCP
          envFrom:
            - configMapRef:
                name: opti-moteur-config
          env:
            # --- Milvus credentials depuis Secret ---
            - name: ZILLIZ_USER
              valueFrom:
                secretKeyRef:
                  name: opti-moteur-milvus-creds
                  key: zilliz-user
            - name: ZILLIZ_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: opti-moteur-milvus-creds
                  key: zilliz-password
            # --- Typesense API key depuis Secret S2 ---
            - name: TYPESENSE_API_KEY
              valueFrom:
                secretKeyRef:
                  name: typesense-api-key
                  key: api-key
          resources:
            requests:
              cpu: "200m"
              memory: "512Mi"
            limits:
              cpu: "1000m"
              memory: "1Gi"
          livenessProbe:
            httpGet:
              path: /
              port: 8570
            initialDelaySeconds: 20
            periodSeconds: 30
            timeoutSeconds: 5
            failureThreshold: 3
          readinessProbe:
            httpGet:
              path: /health
              port: 8570
            initialDelaySeconds: 10
            periodSeconds: 10
            timeoutSeconds: 5
            failureThreshold: 3
```

**Matrice d'impact** : 🆕 Création Deployment 2 replicas • Périmètre : ns `moteur-recherche` • Downtime : aucun (rien en prod) • Réversible : ✅ (`kubectl delete deploy opti-moteur-front -n moteur-recherche`) • Risque : 🟡 Moyen (image jamais utilisée auparavant, premier démarrage prod) • Validation : DevSecOps
**Pré-requis** : Secret `opti-moteur-milvus-creds` + Secret `typesense-api-key` + ConfigMap `opti-moteur-config` doivent exister + image présente dans Artifact Registry.

---

### 6.4 `23-opti-moteur-service.yaml` — Service ClusterIP

> Note : à S3 c'est un ClusterIP pour tests intra-cluster. À S4 on le transformera en `Internal LoadBalancer` avec annotations global access.

```yaml
apiVersion: v1
kind: Service
metadata:
  name: opti-moteur-front
  namespace: moteur-recherche
  labels:
    app.kubernetes.io/name: opti-moteur-front
    app.kubernetes.io/managed-by: manifest
    environment: prod
    owner: devsecops
    cost-center: ia-rag
    app: opti-moteur-recherche
spec:
  type: ClusterIP
  selector:
    app.kubernetes.io/name: opti-moteur-front
    app: opti-moteur-recherche
  ports:
    - name: http
      port: 8570
      targetPort: 8570
      protocol: TCP
```

**Matrice d'impact** : 🆕 Création Service ClusterIP • Périmètre : ns `moteur-recherche` • Downtime : aucun • Réversible : ✅ • Risque : 🟢 Faible • Validation : DevSecOps
**DNS résultant** : `opti-moteur-front.moteur-recherche.svc.cluster.local:8570`

---

## 7. Procédure d'application (étape par étape)

### 7.1 — Créer le Secret `opti-moteur-milvus-creds`

> 🆕 **Matrice d'impact** : Création Secret • Périmètre : ns `moteur-recherche` • Downtime : aucun • Réversible : ✅ • Risque : 🟢 (mot de passe via `read -s`, jamais dans l'historique bash) • Validation : DevSecOps

**Pré-checks** :
```bash
kubectl get secret opti-moteur-milvus-creds -n moteur-recherche 2>/dev/null && echo "EXISTE — STOP" || echo "OK"
```

**Création (one-liner sécurisé, password masqué à la saisie)** :
```bash
read -p "Username Milvus prod : " ZILLIZ_USER
read -s -p "Password Milvus prod : " ZILLIZ_PASSWORD; echo ""
kubectl create secret generic opti-moteur-milvus-creds \
  --namespace=moteur-recherche \
  --from-literal=zilliz-user="$ZILLIZ_USER" \
  --from-literal=zilliz-password="$ZILLIZ_PASSWORD" \
  --dry-run=client -o yaml | kubectl apply -f -
unset ZILLIZ_USER ZILLIZ_PASSWORD
```

**Ajouter labels** :
```bash
kubectl label secret opti-moteur-milvus-creds -n moteur-recherche \
  app.kubernetes.io/name=opti-moteur-front \
  app.kubernetes.io/managed-by=manifest \
  environment=prod \
  owner=devsecops \
  cost-center=ia-rag \
  app=opti-moteur-recherche
```

**Post-vérif** :
```bash
kubectl describe secret opti-moteur-milvus-creds -n moteur-recherche
# Attendu : Type Opaque, Data zilliz-user (X bytes) + zilliz-password (Y bytes), labels OK
```

---

### 7.2 — Apply ConfigMap

```bash
kubectl apply -f manifests/21-opti-moteur-configmap.yaml --dry-run=server -o yaml | head -30
kubectl diff -f manifests/21-opti-moteur-configmap.yaml
kubectl apply -f manifests/21-opti-moteur-configmap.yaml
kubectl describe cm opti-moteur-config -n moteur-recherche
```

---

### 7.3 — Build + push image (cf. §5)

Si pas déjà fait : créer `cloudbuild.yaml` puis lancer `gcloud builds submit`.

---

### 7.4 — Apply Service ClusterIP (avant Deployment pour DNS prêt)

```bash
kubectl apply -f manifests/23-opti-moteur-service.yaml --dry-run=server -o yaml | head -25
kubectl diff -f manifests/23-opti-moteur-service.yaml
kubectl apply -f manifests/23-opti-moteur-service.yaml
kubectl get svc opti-moteur-front -n moteur-recherche
```

---

### 7.5 — Apply Deployment

> 🆕 **Matrice d'impact** : Création Deployment 2 replicas • Périmètre : ns `moteur-recherche` • Downtime : aucun • Réversible : ✅ • Risque : 🟡 (premier démarrage app prod, peut révéler erreurs config Milvus/Typesense/Embedding) • Validation : DevSecOps

**Pré-checks** :
```bash
# (a) Tous les pré-requis présents
kubectl get secret opti-moteur-milvus-creds typesense-api-key -n moteur-recherche
kubectl get cm opti-moteur-config -n moteur-recherche
kubectl get svc opti-moteur-front -n moteur-recherche

# (b) L'image est dans Artifact Registry
gcloud artifacts docker images describe \
  europe-west1-docker.pkg.dev/hellopro-rag-project/hellopro/opti-moteur-front:v1.0.0-prod
```

**Dry-run + diff** :
```bash
kubectl apply -f manifests/22-opti-moteur-deployment.yaml --dry-run=server -o yaml | head -60
kubectl diff -f manifests/22-opti-moteur-deployment.yaml
```

**Apply + suivi** :
```bash
kubectl apply -f manifests/22-opti-moteur-deployment.yaml

# Suivi du rollout (attend que les 2 replicas soient ready)
kubectl rollout status deployment/opti-moteur-front -n moteur-recherche --timeout=5m
```

**Post-vérif** :
```bash
kubectl get pods -n moteur-recherche -l app.kubernetes.io/name=opti-moteur-front
# Attendu : 2 pods Running 1/1

# Logs au démarrage des 2 pods
kubectl logs -n moteur-recherche -l app.kubernetes.io/name=opti-moteur-front --tail=20

# Vérifier les Endpoints du Service
kubectl get endpoints opti-moteur-front -n moteur-recherche
# Attendu : 2 IPs (les 2 pods)
```

---

### 7.6 — Smoketests bout-en-bout (depuis pod éphémère curl)

```bash
# 1. /  -> liveness, doit retourner {"message":"Bienvenue..."}
kubectl run -n moteur-recherche --rm -i --restart=Never \
  --image=curlimages/curl tmp-test-1 -- \
  curl -sS http://opti-moteur-front:8570/

# 2. /health -> readiness, doit retourner status combiné
kubectl run -n moteur-recherche --rm -i --restart=Never \
  --image=curlimages/curl tmp-test-2 -- \
  curl -sS http://opti-moteur-front:8570/health
# Attendu : {"status":"ok","typesense":"ok","milvus":"ok"}
# Si typesense:"ok" mais milvus:"ko" → vérifier creds Milvus dans Secret
```

---

## 8. Critères de sortie (Definition of Done)

- [ ] Fichier `cloudbuild.yaml` créé dans `apps-microservices/opti-moteur-front/`
- [ ] Image `opti-moteur-front:v1.0.0-prod` présente dans Artifact Registry
- [ ] Secret `opti-moteur-milvus-creds` créé (creds jamais committés)
- [ ] ConfigMap `opti-moteur-config` créée avec toutes les valeurs validées
- [ ] Service ClusterIP `opti-moteur-front` accessible sur 8570 dans le ns
- [ ] Deployment 2 replicas Running 1/1, ready
- [ ] `GET /` retourne 200 avec message d'accueil
- [ ] `GET /health` retourne `{"status":"ok","typesense":"ok","milvus":"ok"}`
- [ ] 2 pods listés dans Endpoints du Service
- [ ] `etat_avancement.md` mis à jour : S3 = 🟢 Terminé

---

## 9. Rollback du sprint S3

> Index Typesense vide à ce stade (D16) → rollback safe, pas de perte de données métier.

**Matrice d'impact rollback** : ❌ Destruction Deployment + Service + ConfigMap + Secret • Périmètre : ns `moteur-recherche` (Typesense préservé) • Downtime : aucun • Réversible : ré-applicable • Risque : 🟢 Faible • Validation : DevSecOps

```bash
kubectl delete deploy opti-moteur-front -n moteur-recherche
kubectl delete svc opti-moteur-front -n moteur-recherche
kubectl delete cm opti-moteur-config -n moteur-recherche
kubectl delete secret opti-moteur-milvus-creds -n moteur-recherche

# Optionnel : supprimer l'image en cas de problème de build
gcloud artifacts docker images delete \
  europe-west1-docker.pkg.dev/hellopro-rag-project/hellopro/opti-moteur-front:v1.0.0-prod \
  --quiet
```

---

## 10. Estimation effort

| Étape | Durée |
|---|---|
| Discovery (4.1 à 4.3) | 5 min |
| Création `cloudbuild.yaml` (5.1) | 5 min |
| Build + push Cloud Build (5.2) | 10 min (3-8 min build + vérif) |
| Création Secret Milvus (7.1) | 5 min |
| Apply ConfigMap (7.2) | 5 min |
| Apply Service (7.4) | 5 min |
| Apply Deployment + suivi rollout (7.5) | 10 min |
| Smoketests (7.6) | 10 min |
| Documentation post-sprint | 10 min |
| **Total** | **~1 h 05** |

---

## 11. Suite

Une fois S3 validé :
- Mettre à jour `etat_avancement.md` (S3 → 🟢, S4 → 🟡)
- Démarrer `sprint_004_exposition_interne.md` :
  - Convertir le Service `opti-moteur-front` en `LoadBalancer` interne (annotation `networking.gke.io/load-balancer-type: "Internal"` + `internal-load-balancer-allow-global-access: "true"`)
  - Créer NetPol ingress restreinte à `10.11.0.2/32` (API Gateway VM GPU)
  - Tester depuis la VM GPU (us-east4) → service GKE (europe-west1) — confirmation cross-region
