# sprint_001 — Cadrage infra GKE (namespace, SA, NetworkPolicies)

> **Sprint S1** du plan de migration Typesense + opti-moteur-front sur GKE.
> Voir `../plan.md` pour le contexte global et `../runbook.md` pour les procédures.

---

## 1. Objectif

Préparer le **socle isolé** sur GKE pour héberger la stack `moteur-recherche` :
- Namespace dédié avec labels FinOps
- ServiceAccount K8s dédié pour les pods runtime
- NetworkPolicies **scope namespace** (option B, ne touche pas au reste du cluster)

À la fin du sprint, le namespace est prêt à recevoir Typesense (S2) et l'app (S3).

---

## 2. Dépendances

- ✅ Cluster GKE `matching-api-dev-k8s` accessible
- ✅ `gcloud` + `kubectl` configurés sur le poste DevSecOps
- ⏳ **Discovery requise** : nom exact du Service Milvus prod (port 19530) + IP/CIDR de la VM GPU
- ✅ Validation du `plan.md`, `runbook.md`, `etat_avancement.md`

---

## 3. Principe

| Principe | Application S1 |
|---|---|
| Zero Trust réseau | Default deny ingress+egress dans le ns + allow explicites |
| Least privilege IAM | SA K8s simple, sans Workload Identity (l'app n'appelle pas l'API GCP) |
| Tagging FinOps | Labels obligatoires sur tous les manifests (env, owner, cost-center, managed-by, app) |
| Immutable infra | Tout via manifests YAML versionnés dans `manifests/` |
| Zéro impact prod | Toutes les ressources sont créées dans un nouveau namespace, aucun service existant n'est modifié |

---

## 4. Discovery (à exécuter EN PREMIER, lecture seule)

> 📖 **Toutes les commandes ci-dessous sont en lecture seule. Aucun impact prod.**

### 4.1 Lister les services Milvus prod (pour trouver le nom exact)

```bash
kubectl get svc -n milvus-prod -o wide
```

**Attendu** : un service du type `milvus-prod-milvus` (ou similaire) sur le port `19530`.

➜ Noter le **nom exact** + le **port** dans `etat_avancement.md` Q5 et reporter dans `04-netpol-allow-egress-milvus.yaml` ci-dessous.

### 4.2 Récupérer l'IP/CIDR de la VM GPU

```bash
# Option A : si la VM est dans le même VPC, lister les VMs du projet
gcloud compute instances list --project hellopro-rag-project \
  --filter="name~'gpu' OR machineType~'g2'" \
  --format="table(name,zone,networkInterfaces[0].networkIP,networkInterfaces[0].accessConfigs[0].natIP)"

# Option B : si vous connaissez le nom de la VM
gcloud compute instances describe <NOM_VM_GPU> --zone <ZONE> \
  --project hellopro-rag-project \
  --format="value(networkInterfaces[0].networkIP)"
```

➜ Noter l'**IP interne** (pas l'IP publique) à utiliser comme `<VM_GPU_INTERNAL_IP>/32` dans `05-netpol-allow-egress-vm-gpu.yaml`.

### 4.3 Vérifier le contexte kubectl

```bash
kubectl config current-context
# Attendu : gke_hellopro-rag-project_europe-west1-b_matching-api-dev-k8s
kubectl get nodes
kubectl get ns | grep -E 'milvus-prod|moteur-recherche'
# moteur-recherche ne doit PAS encore exister
```

---

## 5. Manifests à créer

> Les fichiers seront créés dans `../manifests/` après validation de ce sprint.
> Chaque YAML est ci-dessous **inline** pour revue avant production.

### 5.1 `00-namespace.yaml` — Namespace `moteur-recherche`

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: moteur-recherche
  labels:
    app.kubernetes.io/name: opti-moteur-recherche
    app.kubernetes.io/managed-by: manifest
    environment: prod
    owner: devsecops
    cost-center: ia-rag
    app: opti-moteur-recherche
```

**Matrice d'impact** : 🆕 Création • Périmètre : cluster (nouveau ns) • Downtime : aucun • Réversible : ✅ (`kubectl delete ns moteur-recherche`) • Risque : 🟢 Faible • Validation : DevSecOps

---

### 5.2 `01-serviceaccount.yaml` — SA pod runtime

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: opti-moteur-sa
  namespace: moteur-recherche
  labels:
    app.kubernetes.io/name: opti-moteur-recherche
    app.kubernetes.io/managed-by: manifest
    environment: prod
    owner: devsecops
    cost-center: ia-rag
    app: opti-moteur-recherche
```

**Matrice d'impact** : 🆕 Création • Périmètre : namespace `moteur-recherche` • Downtime : aucun • Réversible : ✅ (`kubectl delete sa opti-moteur-sa -n moteur-recherche`) • Risque : 🟢 Faible • Validation : DevSecOps

---

### 5.3 `02-netpol-default-deny.yaml` — Default deny ingress+egress

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-all
  namespace: moteur-recherche
  labels:
    app.kubernetes.io/managed-by: manifest
    environment: prod
spec:
  podSelector: {}
  policyTypes:
    - Ingress
    - Egress
```

**Matrice d'impact** : 🆕 Création • Périmètre : namespace `moteur-recherche` (vide à ce stade) • Downtime : aucun (aucun pod dans le ns) • Réversible : ✅ (`kubectl delete netpol default-deny-all -n moteur-recherche`) • Risque : 🟢 Faible (aucun workload encore) • Validation : DevSecOps
**Pré-checks** : `kubectl get pods -n moteur-recherche` doit retourner **No resources found**

---

### 5.4 `03-netpol-allow-dns.yaml` — Allow DNS egress

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-dns
  namespace: moteur-recherche
  labels:
    app.kubernetes.io/managed-by: manifest
    environment: prod
spec:
  podSelector: {}
  policyTypes:
    - Egress
  egress:
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: kube-system
          podSelector:
            matchLabels:
              k8s-app: kube-dns
      ports:
        - protocol: UDP
          port: 53
        - protocol: TCP
          port: 53
```

**Matrice d'impact** : 🆕 Création • Périmètre : namespace `moteur-recherche` • Downtime : aucun • Réversible : ✅ • Risque : 🟢 Faible • Validation : DevSecOps

---

### 5.5 `04-netpol-allow-egress-milvus.yaml` — Allow egress vers Milvus prod

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-egress-milvus-prod
  namespace: moteur-recherche
  labels:
    app.kubernetes.io/managed-by: manifest
    environment: prod
spec:
  podSelector:
    matchLabels:
      app: opti-moteur-recherche
  policyTypes:
    - Egress
  egress:
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: milvus-prod
      ports:
        - protocol: TCP
          port: 19530   # gRPC API Milvus (à confirmer via discovery 4.1)
        - protocol: TCP
          port: 9091    # mgmt (milvus-prod-mgmt)
```

**Matrice d'impact** : 🆕 Création • Périmètre : namespace `moteur-recherche` (sélecteur `app: opti-moteur-recherche`) • Downtime : aucun • Réversible : ✅ • Risque : 🟢 Faible (n'affecte pas le namespace `milvus-prod`) • Validation : DevSecOps
**Note** : la NetPol côté `milvus-prod` n'est pas appliquée actuellement (cf. point 1 utilisateur), donc ingress vers Milvus reste ouvert. Cette policy garantit que **nos** pods n'égressent que là.

---

### 5.6 `05-netpol-allow-egress-vm-gpu.yaml` — Allow egress vers VM GPU (embedding service)

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-egress-vm-gpu-embedding
  namespace: moteur-recherche
  labels:
    app.kubernetes.io/managed-by: manifest
    environment: prod
spec:
  podSelector:
    matchLabels:
      app: opti-moteur-recherche
  policyTypes:
    - Egress
  egress:
    - to:
        - ipBlock:
            cidr: <VM_GPU_INTERNAL_IP>/32   # à renseigner via discovery 4.2
      ports:
        - protocol: TCP
          port: 8555    # api-embedding-service
```

**Matrice d'impact** : 🆕 Création • Périmètre : namespace `moteur-recherche` • Downtime : aucun • Réversible : ✅ • Risque : 🟢 Faible • Validation : DevSecOps
**⚠️ Pré-requis** : remplacer `<VM_GPU_INTERNAL_IP>/32` par la valeur exacte issue de discovery 4.2 **avant** apply.

---

### 5.7 `06-netpol-allow-internal.yaml` — Allow ingress/egress intra-namespace

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-internal-namespace
  namespace: moteur-recherche
  labels:
    app.kubernetes.io/managed-by: manifest
    environment: prod
spec:
  podSelector: {}
  policyTypes:
    - Ingress
    - Egress
  ingress:
    - from:
        - podSelector: {}
  egress:
    - to:
        - podSelector: {}
```

**Matrice d'impact** : 🆕 Création • Périmètre : namespace `moteur-recherche` • Downtime : aucun • Réversible : ✅ • Risque : 🟢 Faible • Validation : DevSecOps
**Justification** : permet à `opti-moteur-front` de joindre `typesense` (et inversement) dans le même ns.

---

## 6. Procédure d'application (par étape)

> Chaque étape suit le **pattern dry-run → diff → apply → post-vérification**.

### Étape 1 — Créer le namespace

**Pré-checks** :
```bash
kubectl get ns moteur-recherche 2>/dev/null && echo "EXISTE DEJA — STOP" || echo "OK, ns absent"
```

**Dry-run** :
```bash
kubectl apply -f manifests/00-namespace.yaml --dry-run=server -o yaml
```

**Diff** :
```bash
kubectl diff -f manifests/00-namespace.yaml
```

**Apply** :
```bash
kubectl apply -f manifests/00-namespace.yaml
```

**Post-vérif** :
```bash
kubectl get ns moteur-recherche -o jsonpath='{.metadata.labels}' | jq .
# Doit afficher tous les labels FinOps
```

---

### Étape 2 — Créer le ServiceAccount

**Pré-checks** :
```bash
kubectl get sa opti-moteur-sa -n moteur-recherche 2>/dev/null && echo "EXISTE — STOP" || echo "OK"
```

**Dry-run + diff + apply** :
```bash
kubectl apply -f manifests/01-serviceaccount.yaml --dry-run=server -o yaml
kubectl diff -f manifests/01-serviceaccount.yaml
kubectl apply -f manifests/01-serviceaccount.yaml
```

**Post-vérif** :
```bash
kubectl get sa opti-moteur-sa -n moteur-recherche
```

---

### Étape 3 — Appliquer les NetworkPolicies (dans l'ordre)

> ⚠️ **Ordre obligatoire** : default-deny en dernier serait OK aussi (ns vide), mais ce séquencement reste plus lisible.

**Pré-checks** :
```bash
# Le ns doit être vide de pods (pas de risque de couper du trafic)
kubectl get pods -n moteur-recherche
# Attendu : No resources found

# Vérifier que <VM_GPU_INTERNAL_IP> a bien été remplacé dans 05-netpol-allow-egress-vm-gpu.yaml
grep -c '<VM_GPU_INTERNAL_IP>' manifests/05-netpol-allow-egress-vm-gpu.yaml
# Attendu : 0
```

**Dry-run sur tous les NetPol d'un coup** :
```bash
for f in manifests/0{2,3,4,5,6}-netpol-*.yaml; do
  echo "=== $f ===";
  kubectl apply -f "$f" --dry-run=server -o yaml | head -10;
done
```

**Diff** :
```bash
for f in manifests/0{2,3,4,5,6}-netpol-*.yaml; do
  kubectl diff -f "$f";
done
```

**Apply** (un par un pour traçabilité) :
```bash
kubectl apply -f manifests/02-netpol-default-deny.yaml
kubectl apply -f manifests/03-netpol-allow-dns.yaml
kubectl apply -f manifests/04-netpol-allow-egress-milvus.yaml
kubectl apply -f manifests/05-netpol-allow-egress-vm-gpu.yaml
kubectl apply -f manifests/06-netpol-allow-internal.yaml
```

**Post-vérif** :
```bash
kubectl get netpol -n moteur-recherche
# Attendu : 5 policies listées

kubectl describe netpol default-deny-all -n moteur-recherche
# Vérifier : PolicyTypes Ingress + Egress, podSelector: <none>
```

---

## 7. Critères de sortie (Definition of Done)

- [ ] Namespace `moteur-recherche` créé avec tous les labels FinOps
- [ ] ServiceAccount `opti-moteur-sa` créé dans le ns
- [ ] 5 NetworkPolicies appliquées (default-deny + allow-dns + allow-milvus + allow-vm-gpu + allow-internal)
- [ ] `<VM_GPU_INTERNAL_IP>` remplacé par la valeur réelle (plus aucun placeholder)
- [ ] Nom du Service Milvus confirmé (mis à jour dans `etat_avancement.md` Q5)
- [ ] Aucun impact constaté sur les autres namespaces (`kubectl get pods --all-namespaces` stable avant/après)
- [ ] `etat_avancement.md` mis à jour : S1 = 🟢 Terminé

---

## 8. Rollback du sprint S1

> Procédure si S1 doit être annulé entièrement.

**Matrice d'impact rollback** : ❌ Destruction • Périmètre : ns `moteur-recherche` (vide) • Downtime : aucun • Réversible : non (mais ré-applicable) • Risque : 🟢 Faible • Validation : DevSecOps

```bash
# Supprime le ns + toutes ses ressources (SA + NetPols)
kubectl delete ns moteur-recherche

# Vérifier
kubectl get ns moteur-recherche 2>/dev/null && echo "ENCORE PRESENT" || echo "OK, supprimé"
```

---

## 9. Estimation effort

| Étape | Durée |
|---|---|
| Discovery (4.1 + 4.2 + 4.3) | 15 min |
| Création des 7 fichiers YAML dans `manifests/` | 10 min (action assistant) |
| Apply + post-vérifs | 30 min |
| Documentation post-sprint (etat_avancement, debug si besoin) | 15 min |
| **Total** | **~1 h 10** |

---

## 10. Suite

Une fois S1 validé :
- Mettre à jour `etat_avancement.md` (S1 → 🟢, S2 → 🟡)
- Démarrer `sprint_002_typesense_server.md` (StatefulSet Typesense + PVC + Service ClusterIP)
