# runbook.md — Migration Typesense + opti-moteur-front sur GKE

> Runbook **global** d'exploitation de la migration. Les commandes détaillées par sprint sont dans `sprints/sprint_XXX.md`.

---

## 1. Objectif opérationnel

Faire tourner en production sur GKE la stack `Typesense server + opti-moteur-front`, exposée au front PHP legacy (CDN Imperva) et aux services internes VM GPU, avec déploiement automatisé sur push sur la branche `features/opti-moteur-front`.

---

## 2. Architecture cible

```
┌─────────────────────────────────────────────────────────────────┐
│ Internet                                                        │
│   ↓                                                             │
│ CDN Imperva → site PHP CentOS (legacy)                          │
│   ↓                                                             │
│ API Gateway HelloPro (api.hellopro.eu/optimoteur-service)       │
│   = hébergée sur la VM GPU `vm-embedding-g2-std-24-use`         │
│     (10.11.0.2, us-east4) — voir R7                             │
│   ↓ HTTP via VPC interne (cross-region us-east4 → europe-west1) │
│ ┌──────────────── GKE matching-api-dev-k8s (europe-west1) ──┐   │
│ │ Namespace : moteur-recherche                              │   │
│ │                                                           │   │
│ │ Service opti-moteur-front (Internal LB, port 8570)        │   │
│ │   + global access activé (annotation GKE)                 │   │
│ │   + NetPol ingress allowlist : 10.11.0.2/32 only          │   │
│ │   ↓                                                       │   │
│ │ Deployment opti-moteur-front (2 replicas)                 │   │
│ │   ├──→ Service typesense (8108, ClusterIP interne)        │   │
│ │   │     ↓                                                 │   │
│ │   │   StatefulSet typesense-0 (PVC SSD 100 Go)            │   │
│ │   │   • démarre vide en prod (D16)                        │   │
│ │   │                                                       │   │
│ │   ├──→ Milvus prod (svc milvus-prod, ns milvus-prod)      │   │
│ │   │                                                       │   │
│ │   └──→ Embedding service (10.11.0.2:8555, même VM GPU)    │   │
│ └────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

> **Pas d'Ingress externe, pas de TLS public, pas de Cloud Armor** :
> le service GKE est consommé uniquement par l'API Gateway HelloPro qui parle au cluster via VPC interne.

---

## 3. Dépendances

### Externes (hors périmètre, doivent être disponibles)
- Cluster GKE `matching-api-dev-k8s` accessible via `kubectl`
- Milvus prod (collection `produits_3`) opérationnel dans le cluster
- VM GPU joignable depuis les nodes GKE sur le port `8555` (api-embedding-service) — **communication GKE ↔ VM GPU déjà fonctionnelle, à re-tester depuis le pod opti-moteur-front au S3**
- Artifact Registry `europe-west1-docker.pkg.dev/hellopro-rag-project/hellopro/`
- Service Account GitHub Actions avec rôles `roles/artifactregistry.writer` + `roles/container.developer` — **à créer (S5)**
- Bucket GCS pour backups — **réutiliser bucket existant** (à identifier au S7, candidat `gs://hellopro-backups/` si dispo)

### Internes (créées par cette migration)
- Namespace `moteur-recherche`
- ServiceAccount `opti-moteur-sa` (Workload Identity vers SA GCP)
- Secret `typesense-api-key`, `opti-moteur-secrets` (Milvus credentials)
- ConfigMap `opti-moteur-config`
- ManagedCertificate `opti-moteur-cert`
- BackendConfig `opti-moteur-backend` (Cloud Armor)

---

## 4. Principes directeurs

| Principe | Application |
|---|---|
| **Zero Trust réseau** | NetworkPolicies deny-all par défaut, ouverture explicite vers Milvus, Typesense, embedding service VM |
| **Least privilege IAM** | SA dédié, rôles minimum, Workload Identity (pas de clés JSON) |
| **Immutable infra** | Aucune modification manuelle prod ; tout via manifests versionnés ou pipeline CI/CD |
| **Observabilité d'abord** | Pas de mise en prod sans métriques `/metrics` + logs structurés + healthcheck |
| **FinOps** | Tags obligatoires, requests/limits définis, PVC dimensionné juste, image multi-stage |
| **Progressive delivery** | Validation staging → canary → prod, pas de big-bang |

---

## 5. Procédures opérationnelles

> **Convention matrice d'impact** : chaque commande mutative ci-dessous porte une matrice d'impact compacte au format
> `🆕/✏️/❌ • Périmètre : X • Downtime : Y • Réversible : ✅/❌ • Risque : 🟢/🟡/🔴 • Validation : Z`
>
> Les commandes en **lecture seule** sont marquées `📖 Aucun impact prod`. Les matrices détaillées par étape sont dans `sprints/sprint_XXX.md`.

### 5.1 Déploiement initial (one-shot)

Voir `sprints/sprint_001` à `sprint_004`. Ordre strict :
1. Namespace + RBAC + NetworkPolicies
2. Typesense server (StatefulSet + PVC + Service)
3. opti-moteur-front (Deployment + Service)
4. Ingress + ManagedCertificate + Cloud Armor

### 5.2 Déploiement continu (post-migration, automatique)

Trigger : push sur `features/opti-moteur-front` modifiant `apps-microservices/opti-moteur-front/**`.

Pipeline :
1. Build image Docker → tag `<sha>`
2. Push vers Artifact Registry
3. `gcloud container clusters get-credentials matching-api-dev-k8s --zone europe-west1-b`
4. `kubectl set image deployment/opti-moteur-front opti-moteur-front=<image>:<sha> -n moteur-recherche`
5. `kubectl rollout status deployment/opti-moteur-front -n moteur-recherche --timeout=5m`
6. Si échec → `kubectl rollout undo` automatique

### 5.3 Re-ingestion catalogue — **HORS PÉRIMÈTRE DEVSECOPS (D16)**

> 📌 **Ingestion à la charge des devs**. Le rôle DevSecOps se limite à fournir aux devs :
> - URL interne du service `opti-moteur-front.moteur-recherche.svc.cluster.local:8570`
> - URL interne Typesense `typesense.moteur-recherche.svc.cluster.local:8108`
> - Secret `TYPESENSE_API_KEY` (via Secret K8s, valeur fournie au Lead Dev de manière sécurisée)
> - Credentials Milvus (déjà existants)
> - IP / endpoint embedding service (`10.11.0.2:8555`)
>
> Pour exécuter l'ingestion, les devs accèdent au pod via `kubectl exec` ou via Job K8s qu'ils déploient. Pattern générique pour référence :

```bash
# Pattern générique — endpoint exact à valider côté code
kubectl exec -n moteur-recherche deploy/opti-moteur-front -- \
  curl -X POST http://localhost:8570/<endpoint-ingestion> \
  -H "Content-Type: application/json" \
  -d '{"collection": "produits_3", "batch_size": 1000}'
```

**Matrice d'impact** : 🆕 Création • Périmètre : Typesense (collection prod) + lecture Milvus prod • Downtime : aucun (collection neuve, ancien moteur non touché) • Réversible : ✅ (`DELETE` collection Typesense) • Risque : 🟡 (charge I/O Milvus prod 30-60 min) • Validation : DevSecOps + Lead Dev • Pré-checks : ingestion en heure creuse, monitoring Milvus actif

Durée estimée : 30-60 min selon I/O Milvus. Suivre les logs.

### 5.4 Rollback global

| Cas | Action | Matrice d'impact |
|---|---|---|
| Mauvaise image déployée | `kubectl rollout undo deployment/opti-moteur-front -n moteur-recherche` | ✏️ • Périmètre : Deployment app • Downtime : ~30 s (rolling) • Réversible : ✅ (re-rollout) • Risque : 🟢 • Validation : DevSecOps |
| Corruption index Typesense | Recréer collection + ré-ingestion (cf. 5.3) | ❌+🆕 • Périmètre : index Typesense • Downtime : recherche dégradée 30-60 min (front bascule sur Solr) • Réversible : ❌ une fois `DELETE` lancé • Risque : 🔴 • Validation : CTO + DevSecOps |
| PVC corrompu | Restaurer snapshot GCS (cf. 5.6) | ✏️ • Périmètre : PVC typesense-data • Downtime : 5-15 min • Réversible : ✅ (snapshot précédent) • Risque : 🟡 • Validation : DevSecOps |
| Migration entière à annuler | Bascule front PHP vers ancien endpoint VM GPU + `kubectl scale deploy opti-moteur-front --replicas=0` | ✏️ • Périmètre : routage front + scale GKE • Downtime : aucun si DNS/config front à jour • Réversible : ✅ (re-bascule) • Risque : 🟡 (config front à valider) • Validation : CTO + Lead Dev |

### 5.5 Troubleshooting rapide

> 📖 **Toutes les commandes ci-dessous sont en lecture seule. Aucun impact prod.**


```bash
# Statut global
kubectl get all -n moteur-recherche

# Logs app
kubectl logs -n moteur-recherche -l app=opti-moteur-front --tail=100 -f

# Logs Typesense
kubectl logs -n moteur-recherche typesense-0 --tail=100

# Test connectivité depuis le pod app
kubectl exec -n moteur-recherche deploy/opti-moteur-front -- \
  curl -sS http://typesense:8108/health

# Test embedding service VM GPU
kubectl exec -n moteur-recherche deploy/opti-moteur-front -- \
  curl -sS http://<IP_VM_GPU>:8555/health

# Events récents (erreurs scheduling, OOM, etc.)
kubectl get events -n moteur-recherche --sort-by='.lastTimestamp' | tail -20
```

### 5.6 Backup / Restore Typesense

**Backup** (CronJob hebdo) :
```bash
kubectl exec -n moteur-recherche typesense-0 -- \
  curl -X POST "http://localhost:8108/operations/snapshot?snapshot_path=/data/snapshot" \
  -H "X-TYPESENSE-API-KEY: $API_KEY"
# puis upload vers gs://hellopro-backups/typesense/
```
**Matrice d'impact** : 🆕 Création (snapshot disque) • Périmètre : pod typesense-0 + bucket GCS • Downtime : aucun (snapshot live) • Réversible : ✅ (snapshot supprimable) • Risque : 🟢 • Validation : Aucune (CronJob automatisé)

**Restore** :
```bash
# 1. Scale down
kubectl scale statefulset typesense -n moteur-recherche --replicas=0
# 2. Récupérer snapshot depuis GCS dans le PVC (job dédié)
# 3. Scale up
kubectl scale statefulset typesense -n moteur-recherche --replicas=1
```
**Matrice d'impact** : ✏️ Modification • Périmètre : Typesense + PVC • Downtime : 5-15 min (recherche bascule sur Solr) • Réversible : ✅ (snapshot précédent) • Risque : 🟡 (perte de données entre dernier snapshot et incident) • Validation : CTO + DevSecOps

---

## 6. Impact

### 6.1 Sur les utilisateurs
- **Pendant migration** : aucun (l'ancien moteur reste en service jusqu'à la bascule)
- **Bascule** : pas de modif du front PHP. C'est l'**API Gateway** sur la VM GPU qui change son **upstream** : ancien backend (POC interne VM) → nouveau Service GKE (`opti-moteur-front.moteur-recherche.svc.cluster.local:8570` ou IP du LB interne). Action **à charge des devs** au S6.

### 6.2 Sur les équipes
- **Lead Dev métier** : modif config front PHP pour pointer vers nouvel Ingress GKE
- **DevSecOps** : ajout cluster + namespace à monitorer (Prometheus, Grafana, alerts)
- **CTO** : revue + validation avant bascule prod

### 6.3 Sur l'infra
- **GKE** : +2 pods app (~500 mCPU, 1 Gi RAM) + 1 pod Typesense (~1 CPU, 2 Gi RAM, 100 Gi disque SSD)
- **Coût additionnel estimé** : ~30-40 €/mois (PVC SSD 100 Go + LB Ingress + trafic)
- **VM GPU** : libère ressources Typesense + opti-moteur-front (récupération ~2 Gi RAM)

---

## 7. Sécurité — checklist mise en prod

- [ ] Service `typesense` en `ClusterIP` uniquement (jamais exposé hors cluster)
- [ ] Service `opti-moteur-front` en `Internal LoadBalancer` (avec annotation `networking.gke.io/load-balancer-type: "Internal"` + `networking.gke.io/internal-load-balancer-allow-global-access: "true"`)
- [ ] NetPol ingress restreinte à `10.11.0.2/32` (API Gateway VM GPU) — aucune autre source autorisée
- [ ] Secrets gérés via Kubernetes Secret + chiffrement KMS au repos (à vérifier sur le cluster)
- [ ] Aucun secret en clair dans les manifests Git (utiliser `kubectl create secret` ou ExternalSecrets)
- [ ] NetworkPolicies actives (default deny + allow explicites)
- [ ] Image opti-moteur-front scannée Trivy (CI step)
- [ ] Image Typesense pinnée par version (pas `:latest`) — version cible : `typesense/typesense:27.1` (alignée sur le `docker-compose.yaml` du POC)
- [ ] **API key Typesense prod ≠ clé POC** (`hp_poc_2026` interdite en prod) — générer une clé forte, stockée dans Secret K8s
- [ ] `--enable-cors` désactivé sur Typesense en prod (CORS géré par opti-moteur-front uniquement)
- [ ] PodSecurityContext : `runAsNonRoot: true`, `readOnlyRootFilesystem: true` quand possible
- [ ] Healthchecks (liveness + readiness) configurés sur tous les pods
- [ ] Resources `requests` ET `limits` définies

---

## 8. Observabilité — checklist

- [ ] Endpoint `/metrics` Prometheus exposé sur opti-moteur-front
- [ ] ServiceMonitor déployé pour scrape automatique
- [ ] Dashboard Grafana : latence P50/P95/P99, taux d'erreur, hit rate cache, ingestion lag
- [ ] Alertes : pod down, latence > 500 ms, taux erreur > 1 %, PVC > 80 %
- [ ] Logs structurés JSON envoyés vers Cloud Logging (default GKE)

---

## 9. Contacts / Escalade

| Rôle | Responsabilité |
|---|---|
| CTO | Go/no-go bascule prod, arbitrage incidents SEV1 |
| DevSecOps | Owner infra GKE + pipeline CI/CD |
| Lead Dev métier | Owner code applicatif `opti-moteur-front` |
| Chef produit | Validation comportement métier (P@5, qualité résultats) |

**SEV1** (impact prod recherche) : rollback immédiat (5.4) puis postmortem blameless dans les 48 h.

---

## 10. Documents associés

- `plan.md` — planning global et sprints
- `etat_avancement.md` — état au jour le jour
- `debug.md` — historique bugs / fix / leçons
- `sprints/sprint_XXX.md` — détails opérationnels par sprint
- `PENSE_IA.md` — décisions et hypothèses
- `CLAUDE.md` — synthèse pour reprise par autre agent
- `hypothese_option.md` — synthèse benchmark moteurs (existant)
