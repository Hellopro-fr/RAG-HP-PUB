# sprint_004 — Exposition interne (Internal LoadBalancer + firewall + NetPol ingress)

> **Sprint S4** du plan de migration. Voir `../plan.md`, `../runbook.md`, `../CLAUDE.md` pour le contexte.

---

## 1. Objectif

Exposer le service `opti-moteur-front` aux **consommateurs autorisés** (API Gateway VM GPU `10.11.0.2`) en **cross-region** (us-east4 → europe-west1) via :
1. **Internal LoadBalancer GCP** + global access activé (sur le Service GKE)
2. **Firewall rule GCP** restreignant `10.11.0.2/32` → port 8570 (couche réelle de filtrage car R8 dit que NetPol K8s n'est pas enforced)
3. **NetworkPolicy K8s** déclarative (couche doc, prête à enforcer si Dataplane V2 activé un jour)

**Hors périmètre** :
- Exposition publique Internet (architecture interne)
- Pipeline CI/CD (S5)
- Cloud Armor (D18)

---

## 2. Dépendances

- ✅ S1 + S2 + S3 terminés (app `opti-moteur-front` Running 2/2, Service ClusterIP `10.0.78.78:8570`)
- ✅ VPC partagé entre `europe-west1` (cluster GKE) et `us-east4` (VM GPU) (déjà fonctionnel cf. R7)
- ⏳ Auth `gcloud` avec `roles/compute.securityAdmin` (pour créer firewall rules)

---

## 3. Principe

| Principe | Application S4 |
|---|---|
| Defense in depth | Firewall GCP (couche L3/L4 réelle) **+** NetPol K8s (couche déclarative) **+** Internal LB (jamais exposé Internet) |
| Cross-region transparent | `internal-load-balancer-allow-global-access: "true"` sur l'annotation Service |
| Alignement repo | Annotations identiques à `manifest/prod/milvus-prod/milvus-prod-mgmt-svc.yaml` |
| Trace via Git | Modif `23-opti-moteur-service.yaml` versionnée, firewall rule créée via commande tracée |
| Mode test isolé | Procédures documentées (port-forward, firewall temporaire) pour ne jamais ouvrir en prod par accident |

---

## 4. Discovery (lecture seule)

```bash
# 4.1 Le Service ClusterIP actuel est OK
kubectl get svc opti-moteur-front -n moteur-recherche -o yaml | head -25

# 4.2 Lister les firewall rules existantes pour s'inspirer du pattern
gcloud compute firewall-rules list \
  --project=hellopro-rag-project \
  --filter="name~'gke-' OR name~'allow-internal'" \
  --format="table(name,direction,priority,sourceRanges.list():label=SRC_RANGES,allowed[].map().firewall_rule().list():label=ALLOW,targetTags.list():label=TGT_TAGS)" \
  | head -20

# 4.3 Récupérer le réseau VPC du cluster
gcloud container clusters describe matching-api-dev-k8s \
  --zone=europe-west1-b \
  --project=hellopro-rag-project \
  --format="value(network,subnetwork)"

# 4.4 Récupérer le tag réseau des nodes GKE (pour cibler la firewall rule)
gcloud compute instances list \
  --project=hellopro-rag-project \
  --filter="name~'gke-matching-api-dev'" \
  --format="value(name,tags.items.list():label=TAGS)" \
  --limit=1
# Note : les nodes GKE ont un tag "gke-<cluster-name>-<random>-node" auto-généré
```

---

## 5. Manifests à modifier / créer

### 5.1 Modifier `manifests/23-opti-moteur-service.yaml`

> ✏️ **Matrice d'impact** : Modification Service ClusterIP → Internal LoadBalancer • Périmètre : ns `moteur-recherche` + ressource GCP (création LB Internal) • Downtime : 30-60s (le ClusterIP existant est remplacé par un LB Internal, brève coupure intra-cluster pendant la transition) • Réversible : ✅ (revenir à `type: ClusterIP`) • Risque : 🟡 Moyen (provisionnement LB GCP ~+18 €/mois, mais sans expo Internet) • Validation : DevSecOps

Modifications à apporter :
- `type: ClusterIP` → `type: LoadBalancer`
- Ajout des **annotations**

```yaml
apiVersion: v1
kind: Service
metadata:
  name: opti-moteur-front
  namespace: moteur-recherche
  annotations:
    networking.gke.io/load-balancer-type: "Internal"
    networking.gke.io/internal-load-balancer-allow-global-access: "true"
  labels:
    app.kubernetes.io/name: opti-moteur-front
    app.kubernetes.io/managed-by: manifest
    environment: prod
    owner: devsecops
    cost-center: ia-rag
    app: opti-moteur-recherche
spec:
  type: LoadBalancer            # ← changé de ClusterIP
  selector:
    app.kubernetes.io/name: opti-moteur-front
    app: opti-moteur-recherche
  ports:
    - name: http
      port: 8570
      targetPort: 8570
      protocol: TCP
```

---

### 5.2 Créer `manifests/30-netpol-allow-ingress-from-vm-gpu.yaml`

> 🆕 **Matrice d'impact** : Création NetworkPolicy ingress • Périmètre : ns `moteur-recherche` • Downtime : aucun (NetPol déclarative cf. R8) • Réversible : ✅ • Risque : 🟢 Faible • Validation : DevSecOps

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-ingress-from-vm-gpu-api-gateway
  namespace: moteur-recherche
  labels:
    app.kubernetes.io/managed-by: manifest
    environment: prod
spec:
  podSelector:
    matchLabels:
      app.kubernetes.io/name: opti-moteur-front
  policyTypes:
    - Ingress
  ingress:
    - from:
        - ipBlock:
            cidr: 10.11.0.2/32   # vm-embedding-g2-std-24-use (us-east4-c, API Gateway)
      ports:
        - protocol: TCP
          port: 8570
```

> Cette policy est **déclarative** (R8). La vraie sécurité réseau vient de la firewall rule GCP §6.

---

## 6. Firewall rule GCP

> 🆕 **Matrice d'impact** : Création Firewall Rule GCP (couche L3/L4 réelle) • Périmètre : projet GCP `hellopro-rag-project` • Downtime : aucun • Réversible : ✅ (`gcloud compute firewall-rules delete`) • Risque : 🟡 Moyen (mauvaise règle peut couper du trafic légitime — d'où le `priority` haut et le `sourceRanges` strict) • Validation : DevSecOps

### 6.1 Créer la règle prod

```bash
# Variables (à adapter si discovery 4.3/4.4 donne d'autres valeurs)
NETWORK="default"   # ⚠️ confirmer via discovery 4.3 — peut être un VPC custom

gcloud compute firewall-rules create allow-vm-gpu-to-opti-moteur-front \
  --project=hellopro-rag-project \
  --network=$NETWORK \
  --direction=INGRESS \
  --action=ALLOW \
  --priority=1000 \
  --source-ranges=10.11.0.2/32 \
  --rules=tcp:8570 \
  --target-tags=$(gcloud container clusters describe matching-api-dev-k8s \
                    --zone=europe-west1-b \
                    --project=hellopro-rag-project \
                    --format="value(nodePools[0].config.tags[0])") \
  --description="ALLOW VM GPU API Gateway (10.11.0.2) -> opti-moteur-front:8570 (cross-region us-east4 -> europe-west1)"
```

> Le `--target-tags` cible les nodes GKE (le LB Internal forwarde vers les nodes). La discovery 4.4 récupère le tag.

### 6.2 Vérifier la règle créée

```bash
gcloud compute firewall-rules describe allow-vm-gpu-to-opti-moteur-front \
  --project=hellopro-rag-project
```
> Attendu : `direction: INGRESS`, `sourceRanges: [10.11.0.2/32]`, `allowed: [{IPProtocol: tcp, ports: [8570]}]`.

---

## 7. Procédure d'application étape par étape

### Étape 7.1 — Apply NetworkPolicy ingress

> Avant de modifier le Service, on pose la NetPol (déclarative, zéro impact mais cohérent avec la sécu).

```bash
# Pré-check
kubectl get netpol allow-ingress-from-vm-gpu-api-gateway -n moteur-recherche 2>/dev/null && echo "EXISTE" || echo "OK"

# Dry-run + diff + apply
kubectl apply -f manifests/30-netpol-allow-ingress-from-vm-gpu.yaml --dry-run=server -o yaml | head -20
kubectl diff -f manifests/30-netpol-allow-ingress-from-vm-gpu.yaml
kubectl apply -f manifests/30-netpol-allow-ingress-from-vm-gpu.yaml

# Post-vérif
kubectl describe netpol allow-ingress-from-vm-gpu-api-gateway -n moteur-recherche
```

---

### Étape 7.2 — Créer la firewall rule GCP

```bash
# Pré-check : la règle n'existe pas déjà
gcloud compute firewall-rules describe allow-vm-gpu-to-opti-moteur-front \
  --project=hellopro-rag-project 2>/dev/null && echo "EXISTE — STOP" || echo "OK"

# Récupérer le tag des nodes GKE
NODE_TAG=$(gcloud container clusters describe matching-api-dev-k8s \
  --zone=europe-west1-b \
  --project=hellopro-rag-project \
  --format="value(nodePools[0].config.tags[0])")
echo "Node tag : $NODE_TAG"

# Récupérer le network
NETWORK=$(gcloud container clusters describe matching-api-dev-k8s \
  --zone=europe-west1-b \
  --project=hellopro-rag-project \
  --format="value(network)")
echo "Network : $NETWORK"

# Création
gcloud compute firewall-rules create allow-vm-gpu-to-opti-moteur-front \
  --project=hellopro-rag-project \
  --network=$NETWORK \
  --direction=INGRESS \
  --action=ALLOW \
  --priority=1000 \
  --source-ranges=10.11.0.2/32 \
  --rules=tcp:8570 \
  --target-tags=$NODE_TAG \
  --description="ALLOW VM GPU API Gateway (10.11.0.2) -> opti-moteur-front:8570"

# Post-vérif
gcloud compute firewall-rules describe allow-vm-gpu-to-opti-moteur-front \
  --project=hellopro-rag-project
```

---

### Étape 7.3 — Modifier le Service (ClusterIP → Internal LB)

> ✏️ **Attention** : à ce stade le Service va être **temporairement remplacé**. Le `kubectl apply` modifie le type. K8s recrée la ressource Service côté GKE et provisionne le Internal LB GCP. Petite coupure intra-cluster ~30-60s.

**Pré-checks** :
```bash
# Pods toujours OK
kubectl get pods -n moteur-recherche -l app.kubernetes.io/name=opti-moteur-front

# Service actuel ClusterIP
kubectl get svc opti-moteur-front -n moteur-recherche
```

**Dry-run + diff** :
```bash
kubectl apply -f manifests/23-opti-moteur-service.yaml --dry-run=server -o yaml | head -30
kubectl diff -f manifests/23-opti-moteur-service.yaml
```
> Attendu dans le diff :
> - `type: ClusterIP` → `type: LoadBalancer`
> - Ajout des 2 annotations `networking.gke.io/...`

**Apply** :
```bash
kubectl apply -f manifests/23-opti-moteur-service.yaml
```
> Attendu : `service/opti-moteur-front configured`

**Suivi du provisionnement Internal LB** (~1-3 min) :
```bash
kubectl get svc opti-moteur-front -n moteur-recherche -w
# Ctrl+C dès que la colonne EXTERNAL-IP affiche une IP RFC1918 (10.x.x.x ou 172.16.x.x)
```
> ⚠️ Le terme **EXTERNAL-IP** est trompeur ici : pour un Internal LB GCP, c'est une IP **privée RFC1918**, joignable uniquement depuis le VPC.

**Post-vérif** :
```bash
kubectl describe svc opti-moteur-front -n moteur-recherche
# Vérifier :
# - Type: LoadBalancer
# - LoadBalancer Ingress: <IP RFC1918>
# - Annotations: networking.gke.io/load-balancer-type=Internal
#                networking.gke.io/internal-load-balancer-allow-global-access=true
# - Port: 8570
# - Endpoints: 2 IPs des pods

# Recuperer l'IP du LB Internal pour les tests
INTERNAL_LB_IP=$(kubectl get svc opti-moteur-front -n moteur-recherche \
  -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
echo "Internal LB IP: $INTERNAL_LB_IP"
```

---

## 8. Smoketests (4 chemins distincts)

### 8.1 — Intra-cluster (DNS K8s, doit toujours marcher)

```bash
kubectl run -n moteur-recherche --rm -i --restart=Never \
  --image=curlimages/curl tmp-test-intra -- \
  curl -sS http://opti-moteur-front:8570/health
# Attendu : {"status":"ok","typesense":"ok","milvus":"ok"}
```

---

### 8.2 — Depuis la VM GPU (`vm-embedding-g2-std-24-use`, us-east4)

> 📖 **Matrice d'impact** : Lecture seule (curl). Aucun impact prod.

**Pré-requis** : SSH actif vers la VM GPU.

```bash
# SSH sur la VM GPU
gcloud compute ssh vm-embedding-g2-std-24-use \
  --zone=us-east4-c \
  --project=hellopro-rag-project

# Une fois sur la VM, depuis le shell de la VM :
INTERNAL_LB_IP="<l'IP retournée à 7.3>"   # ⚠️ adapter

curl -sS -m 5 http://$INTERNAL_LB_IP:8570/health
# Attendu : {"status":"ok","typesense":"ok","milvus":"ok"} en quelques centaines de ms

# Mesurer la latence cross-region (R7)
time curl -sS -o /dev/null -w "%{http_code} - %{time_total}s\n" \
  http://$INTERNAL_LB_IP:8570/health
# Attendu : ~100-150ms (RTT us-east4 ↔ europe-west1)
```

---

### 8.3 — Test rapide depuis votre poste DevSecOps via `kubectl port-forward`

> 📖 **Matrice d'impact** : Lecture seule (tunnel temporaire local). Aucun impact prod.

```bash
# Dans un terminal :
kubectl port-forward -n moteur-recherche svc/opti-moteur-front 18570:8570

# Dans un autre terminal :
curl -sS http://localhost:18570/health
curl -sS http://localhost:18570/

# Ctrl+C dans le 1er terminal pour fermer le tunnel
```

> **Avantage** : zero modif infra, zero risque exposition. **À privilégier pour les tests dev.**

---

### 8.4 — Test depuis Internet (mode test temporaire, exception)

> ⚠️ **À utiliser uniquement pour des tests fonctionnels ponctuels, jamais pour du trafic régulier.**

> ✏️ **Matrice d'impact** : Modification firewall GCP — temporaire — • Périmètre : projet GCP • Downtime : aucun • Réversible : ✅ • Risque : 🟡 Moyen (exposition partielle Internet pendant la fenêtre) • Validation : DevSecOps + horodatage strict

**Étape 1 — Récupérer votre IP publique**
```bash
MY_PUBLIC_IP=$(curl -s https://api.ipify.org)
echo "Mon IP publique : $MY_PUBLIC_IP"
```

**Étape 2 — Créer une firewall rule TEMPORAIRE**
```bash
gcloud compute firewall-rules create temp-allow-test-opti-moteur-front-$(date +%Y%m%d-%H%M) \
  --project=hellopro-rag-project \
  --network=$NETWORK \
  --direction=INGRESS \
  --action=ALLOW \
  --priority=1000 \
  --source-ranges=$MY_PUBLIC_IP/32 \
  --rules=tcp:8570 \
  --target-tags=$NODE_TAG \
  --description="TEMPORARY test access for $(whoami) — TO DELETE within 1h"
```

> ⚠️ **MAIS** : un Internal LB GCP n'est **pas joignable depuis Internet**, même avec firewall ouverte. L'IP du LB est RFC1918. Donc cette procédure ne suffit **PAS** pour un test depuis Internet.

**Pour vraiment tester depuis Internet**, 2 options :
- **Option I** : ouvrir un **2ᵉ Service** de type `LoadBalancer` **External** (avec annotation Cloud Armor IP allowlist) — chantier complet, à NE PAS faire pour un test ponctuel
- **Option II (recommandée)** : utiliser `kubectl port-forward` (cf. 8.3) ou SSH sur une VM du VPC + curl

> **Conclusion** : préférer §8.3 (`kubectl port-forward`) pour les tests rapides depuis poste local. Les tests "depuis Internet" via Internal LB ne sont pas possibles sans changement architectural.

**Étape 3 — Cleanup obligatoire** (si firewall temporaire créée)
```bash
gcloud compute firewall-rules delete temp-allow-test-opti-moteur-front-<timestamp> \
  --project=hellopro-rag-project --quiet

# Lister toutes les firewall rules temporaires pour ne rien oublier
gcloud compute firewall-rules list \
  --project=hellopro-rag-project \
  --filter="name~'^temp-'" \
  --format="table(name,creationTimestamp)"
```

---

## 9. Critères de sortie (Definition of Done)

- [ ] NetPol `allow-ingress-from-vm-gpu-api-gateway` appliquée
- [ ] Firewall rule GCP `allow-vm-gpu-to-opti-moteur-front` créée et validée (priority=1000, source=10.11.0.2/32, port=8570, target-tags=GKE nodes)
- [ ] Service `opti-moteur-front` modifié en `type: LoadBalancer` avec annotations Internal + global access
- [ ] Internal LB IP attribuée (RFC1918) et stable
- [ ] Smoketest 8.1 (intra-cluster) ✅
- [ ] Smoketest 8.2 (VM GPU cross-region) ✅ avec latence < 200 ms
- [ ] Smoketest 8.3 (port-forward local) ✅
- [ ] Aucune firewall rule temporaire restante (cleanup vérifié)
- [ ] `etat_avancement.md` mis à jour : S4 = 🟢 Terminé
- [ ] CLAUDE.md hard facts mis à jour avec `INTERNAL_LB_IP`

---

## 10. Rollback du sprint S4

> Si problème détecté après l'apply : retour à l'état S3 (Service ClusterIP).

```bash
# 1. Revenir au type ClusterIP
# Modifier 23-opti-moteur-service.yaml : type LoadBalancer -> ClusterIP, retirer les annotations
# Puis kubectl apply

# Ou plus rapide via patch :
kubectl patch svc opti-moteur-front -n moteur-recherche \
  --type=merge \
  -p '{"spec":{"type":"ClusterIP"},"metadata":{"annotations":null}}'

# 2. Supprimer la firewall rule
gcloud compute firewall-rules delete allow-vm-gpu-to-opti-moteur-front \
  --project=hellopro-rag-project --quiet

# 3. Supprimer la NetPol ingress (optionnel, sans effet réel)
kubectl delete netpol allow-ingress-from-vm-gpu-api-gateway -n moteur-recherche
```

---

## 11. Estimation effort

| Étape | Durée |
|---|---|
| Discovery (4.1 à 4.4) | 5 min |
| Apply NetPol ingress (7.1) | 5 min |
| Création firewall rule GCP (7.2) | 10 min |
| Modification Service (7.3) + provisionnement LB | 5 min |
| Smoketests (8.1, 8.2, 8.3) | 15 min |
| Documentation post-sprint | 10 min |
| **Total** | **~50 min** |

---

## 12. Suite

Une fois S4 validé :
- Mettre à jour `etat_avancement.md` (S4 → 🟢, S5 → 🟡)
- Mettre à jour `CLAUDE.md` Hard facts avec `INTERNAL_LB_IP`
- Communiquer l'`INTERNAL_LB_IP:8570` au Lead Dev pour qu'il puisse modifier l'upstream de l'API Gateway HelloPro (au S6)
- Démarrer `sprint_005_cicd.md` :
  - Création SA `cicd-opti-moteur-sa` (rôles min : `roles/artifactregistry.writer` + `roles/container.developer` scope ns)
  - Workflow GitHub Actions `cd_opti_moteur_front.yml` : trigger sur push branche `features/opti-moteur-front` + path `apps-microservices/opti-moteur-front/**`
  - GitHub Environment `production` avec required reviewers (mitigation R3)
