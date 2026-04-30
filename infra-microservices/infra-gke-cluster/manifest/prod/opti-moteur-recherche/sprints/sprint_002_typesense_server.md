# sprint_002 — Typesense server (StatefulSet + PVC + Secret + Service)

> **Sprint S2** du plan de migration. Voir `../plan.md`, `../runbook.md`, `../CLAUDE.md` pour le contexte.

---

## 1. Objectif

Déployer Typesense `27.1` en production sur GKE :
- **StatefulSet** 1 réplique avec PVC SSD 100 Go persistant
- **Secret** K8s pour l'API key (générée à la volée, jamais committée en clair)
- **Service ClusterIP** interne (port 8108)
- Démarrage **à vide** (D16) — l'ingestion sera faite par les devs (S6)

Aucun manifest de l'app `opti-moteur-front` n'est posé ici (c'est S3).

---

## 2. Dépendances

- ✅ S1 terminé : namespace `moteur-recherche`, SA `opti-moteur-sa`, 5 NetworkPolicies appliquées
- ✅ StorageClass `premium-rwo` validée (D24)
- ✅ Image Typesense `27.1` confirmée (alignée POC)
- ⏳ **Génération API key prod** à faire pendant le sprint (`openssl rand -base64 32`)

---

## 3. Principe

| Principe | Application S2 |
|---|---|
| Démarrage à vide | StatefulSet créé avec collection vide. L'ingestion catalogue est hors périmètre (D16) |
| Secret jamais en clair | API key générée localement + `kubectl create secret --from-literal --dry-run=client \| kubectl apply -f -`. Pas de fichier YAML committé avec la valeur |
| FinOps | `requests=8Gi RAM/2 CPU`, `limits=16Gi RAM/4 CPU` (cluster bridé à 60 % d'usage = ~51 GB libres, marge confortable) |
| Sécurité | `--enable-cors` désactivé (DT006), API key forte (D19), Service ClusterIP (jamais exposé hors cluster) |
| Observabilité | Liveness + Readiness sur `/health` Typesense (port 8108) |
| Persistance | PVC `premium-rwo` 100 Go, `allowVolumeExpansion=true` |

---

## 4. Discovery (lecture seule)

> 📖 **Aucun impact prod.**

```bash
# 4.1 Vérifier que les ressources S1 sont toujours en place
kubectl get ns,sa,netpol -n moteur-recherche

# 4.2 Vérifier la StorageClass premium-rwo
kubectl describe sc premium-rwo
# Attendu : Provisioner pd.csi.storage.gke.io, ReclaimPolicy Delete,
#           VolumeBindingMode WaitForFirstConsumer, AllowVolumeExpansion True

# 4.3 Capacité disque/quota (zone du cluster)
gcloud compute project-info describe --project hellopro-rag-project \
  --format="value(quotas.metric,quotas.usage,quotas.limit)" 2>/dev/null \
  | grep -i SSD || echo "(quota check optionnel)"
```

---

## 5. Manifests à créer

### 5.1 `10-typesense-secret.yaml` — Secret API key (TEMPLATE, ne pas committer la valeur)

> ⚠️ **Ce fichier est un template documentaire.** L'application réelle se fait via la commande `kubectl create secret` ci-dessous (étape 6.1), pas via `kubectl apply -f`. La valeur n'est **jamais** committée dans Git.

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: typesense-api-key
  namespace: moteur-recherche
  labels:
    app.kubernetes.io/name: typesense
    app.kubernetes.io/managed-by: manifest
    environment: prod
    owner: devsecops
    cost-center: ia-rag
    app: opti-moteur-recherche
type: Opaque
stringData:
  api-key: "<GENERATED_VIA_OPENSSL_RAND>"   # ⚠️ généré à la volée, jamais committé en clair
```

**Matrice d'impact** : 🆕 Création • Périmètre : ns `moteur-recherche` • Downtime : aucun • Réversible : ✅ (`kubectl delete secret typesense-api-key -n moteur-recherche`) • Risque : 🟢 Faible • Validation : DevSecOps
**⚠️ Critique** : la **valeur** ne doit JAMAIS apparaître dans Git, ni dans un log.

---

### 5.2 `11-typesense-pvc.yaml` — PVC SSD 100 Go

> ⚠️ Ce manifest est documentaire. En pratique, le PVC sera **créé automatiquement** par le `volumeClaimTemplates` du StatefulSet (étape 5.3). On ne l'applique **pas** séparément.

```yaml
# Référence — ce PVC sera matérialisé via le StatefulSet (volumeClaimTemplates)
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: typesense-data-typesense-0   # nom auto-généré : <vct-name>-<sts-name>-<ordinal>
  namespace: moteur-recherche
  labels:
    app.kubernetes.io/name: typesense
    app.kubernetes.io/managed-by: manifest
    environment: prod
    owner: devsecops
    cost-center: ia-rag
    app: opti-moteur-recherche
spec:
  accessModes: ["ReadWriteOnce"]
  storageClassName: premium-rwo
  resources:
    requests:
      storage: 100Gi
```

**Note** : ne pas appliquer ce fichier directement. Le StatefulSet le crée via son `volumeClaimTemplates`.

---

### 5.3 `12-typesense-statefulset.yaml` — StatefulSet Typesense

```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: typesense
  namespace: moteur-recherche
  labels:
    app.kubernetes.io/name: typesense
    app.kubernetes.io/managed-by: manifest
    environment: prod
    owner: devsecops
    cost-center: ia-rag
    app: opti-moteur-recherche
spec:
  serviceName: typesense
  replicas: 1
  selector:
    matchLabels:
      app.kubernetes.io/name: typesense
      app: opti-moteur-recherche
  template:
    metadata:
      labels:
        app.kubernetes.io/name: typesense
        app: opti-moteur-recherche
        environment: prod
    spec:
      serviceAccountName: opti-moteur-sa
      terminationGracePeriodSeconds: 60
      securityContext:
        fsGroup: 2000   # accessible par groupe non-root pour /data
      containers:
        - name: typesense
          image: typesense/typesense:27.1
          imagePullPolicy: IfNotPresent
          args:
            - "--data-dir=/data"
            - "--api-key=$(TYPESENSE_API_KEY)"
            - "--listen-port=8108"
            # NB : pas de --enable-cors (DT006). CORS géré par opti-moteur-front en S3.
          env:
            - name: TYPESENSE_API_KEY
              valueFrom:
                secretKeyRef:
                  name: typesense-api-key
                  key: api-key
          ports:
            - containerPort: 8108
              name: http
              protocol: TCP
          resources:
            requests:
              cpu: "1"
              memory: "8Gi"
            limits:
              cpu: "4"
              memory: "16Gi"
          volumeMounts:
            - name: typesense-data
              mountPath: /data
          livenessProbe:
            httpGet:
              path: /health
              port: 8108
            initialDelaySeconds: 30
            periodSeconds: 30
            timeoutSeconds: 5
            failureThreshold: 3
          readinessProbe:
            httpGet:
              path: /health
              port: 8108
            initialDelaySeconds: 10
            periodSeconds: 10
            timeoutSeconds: 5
            failureThreshold: 3
  volumeClaimTemplates:
    - metadata:
        name: typesense-data
        labels:
          app.kubernetes.io/name: typesense
          app.kubernetes.io/managed-by: manifest
          environment: prod
          owner: devsecops
          cost-center: ia-rag
          app: opti-moteur-recherche
      spec:
        accessModes: ["ReadWriteOnce"]
        storageClassName: premium-rwo
        resources:
          requests:
            storage: 100Gi
```

**Matrice d'impact** : 🆕 Création • Périmètre : ns `moteur-recherche` • Downtime : aucun (rien n'existe encore) • Réversible : ✅ (`kubectl delete sts typesense -n moteur-recherche` — **mais NE supprime PAS le PVC** par défaut, c'est voulu) • Risque : 🟡 Moyen (PVC SSD 100 Go provisionné = ~17 €/mois immédiat, à monitorer) • Validation : DevSecOps
**Pré-requis** : Secret `typesense-api-key` doit exister AVANT cet apply (sinon pod en CrashLoop).
**Pré-checks** : `kubectl get secret typesense-api-key -n moteur-recherche` doit retourner la ressource.

---

### 5.4 `13-typesense-service.yaml` — Service ClusterIP

```yaml
apiVersion: v1
kind: Service
metadata:
  name: typesense
  namespace: moteur-recherche
  labels:
    app.kubernetes.io/name: typesense
    app.kubernetes.io/managed-by: manifest
    environment: prod
    owner: devsecops
    cost-center: ia-rag
    app: opti-moteur-recherche
spec:
  type: ClusterIP
  selector:
    app.kubernetes.io/name: typesense
    app: opti-moteur-recherche
  ports:
    - name: http
      port: 8108
      targetPort: 8108
      protocol: TCP
```

**Matrice d'impact** : 🆕 Création • Périmètre : ns `moteur-recherche` • Downtime : aucun • Réversible : ✅ (`kubectl delete svc typesense -n moteur-recherche`) • Risque : 🟢 Faible • Validation : DevSecOps
**DNS résultant** : `typesense.moteur-recherche.svc.cluster.local:8108` (utilisé par opti-moteur-front au S3)

---

## 6. Procédure d'application (étape par étape)

### Étape 6.1 — Générer + créer le Secret API key

> 🆕 **Matrice d'impact** : Création Secret • Périmètre : ns `moteur-recherche` • Downtime : aucun • Réversible : ✅ • Risque : 🟢 (clé jamais sur disque/Git en clair) • Validation : DevSecOps

**Pré-checks** :
```bash
kubectl get secret typesense-api-key -n moteur-recherche 2>/dev/null && echo "EXISTE — STOP" || echo "OK"
```

**Génération + création (one-liner, valeur jamais sur disque persistant)** :
```bash
TYPESENSE_API_KEY=$(openssl rand -base64 32) && \
kubectl create secret generic typesense-api-key \
  --namespace=moteur-recherche \
  --from-literal=api-key="$TYPESENSE_API_KEY" \
  --dry-run=client -o yaml | kubectl apply -f -

# Garder la valeur disponible dans le terminal pour la transmettre au Lead Dev
echo "API key générée : $TYPESENSE_API_KEY"
echo "⚠️ Transmettre via canal sécurisé (1Password / Bitwarden / Keybase). NE PAS coller dans Slack/email/Git."
```

**Ajouter labels** (après création, le `create secret` ne les pose pas par défaut) :
```bash
kubectl label secret typesense-api-key -n moteur-recherche \
  app.kubernetes.io/name=typesense \
  app.kubernetes.io/managed-by=manifest \
  environment=prod \
  owner=devsecops \
  cost-center=ia-rag \
  app=opti-moteur-recherche
```

**Post-vérif** :
```bash
kubectl describe secret typesense-api-key -n moteur-recherche
# Attendu : Type Opaque, Data api-key (44 bytes = 32 octets random base64), labels OK
# La valeur reste masquée dans describe
```

---

### Étape 6.2 — Apply Service ClusterIP (avant StatefulSet pour DNS prêt)

> 🆕 **Matrice d'impact** : Création Service • Périmètre : ns `moteur-recherche` • Downtime : aucun • Réversible : ✅ • Risque : 🟢 • Validation : DevSecOps

```bash
# Pré-check
kubectl get svc typesense -n moteur-recherche 2>/dev/null && echo "EXISTE" || echo "OK"

# Dry-run + diff + apply
kubectl apply -f manifests/13-typesense-service.yaml --dry-run=server -o yaml | head -20
kubectl diff -f manifests/13-typesense-service.yaml
kubectl apply -f manifests/13-typesense-service.yaml

# Post-vérif
kubectl get svc typesense -n moteur-recherche
# Attendu : ClusterIP attribué, port 8108, sélecteur app.kubernetes.io/name=typesense
```

---

### Étape 6.3 — Apply StatefulSet (Typesense + PVC auto)

> 🆕 **Matrice d'impact** : Création StatefulSet + PVC SSD 100 Go • Périmètre : ns `moteur-recherche` • Downtime : aucun • Réversible : ✅ (sts), ⚠️ PVC reste après suppression sts (DT007) • Risque : 🟡 (provisionnement PVC ~17 €/mois immédiat) • Validation : DevSecOps

**Pré-checks** :
```bash
# Le Secret existe (essentiel)
kubectl get secret typesense-api-key -n moteur-recherche

# Aucun StatefulSet déjà
kubectl get sts -n moteur-recherche

# Capacité du cluster
kubectl top nodes
# Vérifier qu'on a au moins 16 Gi de RAM libre sur un node (limit Typesense)
```

**Dry-run + diff** :
```bash
kubectl apply -f manifests/12-typesense-statefulset.yaml --dry-run=server -o yaml | head -40
kubectl diff -f manifests/12-typesense-statefulset.yaml
```

**Apply** :
```bash
kubectl apply -f manifests/12-typesense-statefulset.yaml
```

**Suivi du démarrage** (peut prendre 1-3 min : pull image + provisionnement PVC + boot Typesense) :
```bash
# NB : kubectl ne supporte pas -w sur plusieurs types (cf. debug #003).
# Lancer les 2 watches dans 2 terminaux OU vérifier séquentiellement après quelques secondes.
kubectl get pods -n moteur-recherche -w   # Ctrl+C dès typesense-0 Running 1/1
kubectl get pvc -n moteur-recherche       # vérification ponctuelle, doit être Bound
```

**Post-vérif** :
```bash
# Pod Running
kubectl get pods -n moteur-recherche -l app.kubernetes.io/name=typesense

# PVC bound
kubectl get pvc -n moteur-recherche

# Logs du démarrage Typesense
kubectl logs typesense-0 -n moteur-recherche --tail=30
# Attendu : "Started Typesense API server on port 8108" ou similaire

# Healthcheck Typesense interne (depuis le pod lui-même)
kubectl exec typesense-0 -n moteur-recherche -- \
  curl -sS http://localhost:8108/health
# Attendu : {"ok":true}

# Healthcheck via le Service (ClusterIP)
kubectl run -n moteur-recherche --rm -i --restart=Never \
  --image=curlimages/curl tmp-health -- \
  curl -sS http://typesense:8108/health
# Attendu : {"ok":true}
```

**Test écriture sur /data (vérification fsGroup=2000)** :
```bash
# Tester que Typesense peut écrire dans /data
kubectl exec typesense-0 -n moteur-recherche -- \
  sh -c 'touch /data/.write_test && ls -la /data/.write_test && rm /data/.write_test && echo "OK write/delete /data"'
# Attendu : "OK write/delete /data"
# Si erreur "Permission denied" → fsGroup à ajuster (test UID/GID réel via : kubectl exec ... id)
```

**Test API key (avec la valeur générée à 6.1, ne pas la logguer)** :
```bash
# Créer une collection de test
kubectl exec typesense-0 -n moteur-recherche -- \
  curl -sS -X POST "http://localhost:8108/collections" \
  -H "X-TYPESENSE-API-KEY: $TYPESENSE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"name":"_smoketest","fields":[{"name":"id","type":"string"}]}'

# Lister les collections
kubectl exec typesense-0 -n moteur-recherche -- \
  curl -sS "http://localhost:8108/collections" \
  -H "X-TYPESENSE-API-KEY: $TYPESENSE_API_KEY"

# Supprimer la collection de test
kubectl exec typesense-0 -n moteur-recherche -- \
  curl -sS -X DELETE "http://localhost:8108/collections/_smoketest" \
  -H "X-TYPESENSE-API-KEY: $TYPESENSE_API_KEY"
```

---

## 7. Critères de sortie (Definition of Done)

- [ ] Secret `typesense-api-key` créé (valeur jamais en clair dans Git/log)
- [ ] Service ClusterIP `typesense` accessible sur port 8108
- [ ] StatefulSet `typesense` Running 1/1, ready
- [ ] PVC `typesense-data-typesense-0` Bound (100 Gi, premium-rwo)
- [ ] `curl http://typesense:8108/health` depuis un pod du ns retourne `{"ok":true}`
- [ ] Smoketest API key OK (création + suppression collection `_smoketest`)
- [ ] Logs Typesense propres (aucune erreur au démarrage)
- [ ] API key communiquée au Lead Dev par canal sécurisé
- [ ] `etat_avancement.md` mis à jour : S2 = 🟢 Terminé

---

## 8. Rollback du sprint S2

> ⚠️ **Suppression du PVC = perte de l'index Typesense** (DT007). En S2 l'index est vide, donc rollback OK. À la prod (post-ingestion), backup GCS obligatoire avant tout rollback.

**Matrice d'impact rollback** : ❌ Destruction StatefulSet + PVC • Périmètre : ns `moteur-recherche` • Downtime : aucun (rien en prod) • Réversible : ré-applicable mais index vide à nouveau • Risque : 🟢 Faible (S2 = pas encore d'ingestion) • Validation : DevSecOps

```bash
# 1. Supprimer le StatefulSet (le pod est arrêté gracieusement)
kubectl delete sts typesense -n moteur-recherche

# 2. Supprimer le PVC (DT007 : reclaimPolicy=Delete → disque détruit, OK car index vide)
kubectl delete pvc typesense-data-typesense-0 -n moteur-recherche

# 3. Supprimer le Service
kubectl delete svc typesense -n moteur-recherche

# 4. Supprimer le Secret
kubectl delete secret typesense-api-key -n moteur-recherche

# 5. Vérifier
kubectl get all,pvc,secret -n moteur-recherche
```

---

## 9. Estimation effort

| Étape | Durée |
|---|---|
| Discovery (4.1 + 4.2 + 4.3) | 5 min |
| Génération + apply Secret (6.1) | 10 min (incl. transmission Lead Dev) |
| Apply Service (6.2) | 5 min |
| Apply StatefulSet + suivi démarrage (6.3) | 15 min (PVC provisioning ~1-2 min, image pull ~30 s, boot ~30 s) |
| Smoketests + post-vérifs | 15 min |
| Documentation post-sprint (`etat_avancement.md`, `debug.md` si besoin) | 10 min |
| **Total** | **~1 h** |

---

## 10. Suite

Une fois S2 validé :
- Mettre à jour `etat_avancement.md` (S2 → 🟢, S3 → 🟡)
- Démarrer `sprint_003_opti_moteur_front.md` :
  - Generate / fournir le `.env` prod (Milvus creds, embedding URL, Typesense URL+key)
  - Manifests : ConfigMap (params non-secrets), Secret (creds Milvus), Deployment app, Service ClusterIP
  - Probes split (liveness `/`, readiness `/health`)
  - Build image Docker (manuelle 1ʳᵉ fois) + push Artifact Registry
  - Apply Deployment + tests bout-en-bout app↔Typesense↔Milvus↔embedding
