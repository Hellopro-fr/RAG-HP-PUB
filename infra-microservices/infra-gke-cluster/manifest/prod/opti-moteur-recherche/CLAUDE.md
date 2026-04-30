# CLAUDE.md — Migration `opti-moteur-recherche` sur GKE

> **Si tu es un agent IA** : lis ce fichier en entier **avant toute action**. Il contient les invariants à respecter et l'état actuel du chantier.
> **Si tu es un humain** : c'est ton point d'entrée. 5 min de lecture pour être opérationnel.

---

## TL;DR (en 5 lignes)

Migration de la stack `Typesense + opti-moteur-front` (moteur de recherche produit B2B) de la VM GPU `us-east4` vers le cluster GKE `matching-api-dev-k8s` (`europe-west1`), ns `moteur-recherche`. Pipeline CI/CD GitHub Actions à mettre en place. **L'ingestion catalogue est hors périmètre DevSecOps** (à charge des devs). Avancement actuel : **30 % (S1 terminé)**. Prochaine étape : **S2 — Typesense server (StatefulSet + PVC + Secret)**.

---

## Où chercher quoi (index)

| Tu cherches… | Va lire |
|---|---|
| Le plan global et le découpage en sprints | `plan.md` |
| Les procédures opérationnelles + matrices d'impact | `runbook.md` |
| L'état actuel, décisions figées, risques actifs, journal | `etat_avancement.md` ⭐ **toujours commencer par là** |
| L'historique des incidents + dette technique | `debug.md` |
| Le raisonnement / hypothèses derrière les choix | `PENSE_IA.md` |
| Le détail opérationnel d'un sprint donné | `sprints/sprint_00X_*.md` |
| Les manifests YAML à appliquer | `manifests/*.yaml` |
| La doc benchmark moteurs (existant — Solr/Typesense/OpenSearch) | `hypothese_option.md` |

---

## Hard facts (à utiliser sans inventer)

```yaml
projet_gcp:        hellopro-rag-project
region:            europe-west1
zone:              europe-west1-b
cluster_gke:       matching-api-dev-k8s   # NB : nommé "-dev" mais héberge la prod (DT001)
namespace:         moteur-recherche
artifact_registry: europe-west1-docker.pkg.dev/hellopro-rag-project/hellopro/

milvus_prod:
  namespace: milvus-prod
  service:   milvus-prod                  # gRPC API
  ports:     19530 (gRPC), 9091 (mgmt)
  service_dns: milvus-prod.milvus-prod.svc.cluster.local

vm_gpu_embedding:
  name:      vm-embedding-g2-std-24-use
  zone:      us-east4-c                   # ⚠️ inter-régions vs cluster GKE EU (R7/DT003)
  ip:        10.11.0.2
  port:      8555
  hosts:
    - api-embedding-service (port 8555)
    - api.hellopro.eu/optimoteur-service  # API Gateway HelloPro = consommateur unique du service GKE

typesense_image:    typesense/typesense:27.1
typesense_port:     8108
opti_moteur_port:   8570

# Annotations Service obligatoires
typesense_service:
  type: ClusterIP                              # intra-cluster uniquement
opti_moteur_front_service:                     # à appliquer en S3
  type: LoadBalancer
  annotations:
    networking.gke.io/load-balancer-type: "Internal"
    networking.gke.io/internal-load-balancer-allow-global-access: "true"   # CROSS-REGION, VM us-east4 → GKE europe-west1
opti_moteur_probes:
  liveness:  GET /        # léger, pas de cascade
  readiness: GET /health  # vérifie Typesense en cascade

service_accounts:
  opti-moteur-sa:        # ✅ créé S1 — pod runtime, K8s simple, pas de WI
  cicd-opti-moteur-sa:   # ⏳ à créer S5 — GitHub Actions (artifactregistry.writer + container.developer)
  backup gcs SA:         # ♻️ existant — à réutiliser S7 pour backup Typesense
```

---

## Architecture cible (résumée)

```
PHP front  →  CDN Imperva  →  API Gateway HelloPro (api.hellopro.eu, sur VM GPU us-east4, IP 10.11.0.2)
                                       ↓ HTTP via VPC inter-région
                            ┌─────── GKE matching-api-dev-k8s (europe-west1) ───────┐
                            │ ns moteur-recherche                                  │
                            │ Service opti-moteur-front (Internal LB, port 8570)   │
                            │   ↓                                                  │
                            │ Deployment opti-moteur-front (2 replicas)            │
                            │   ├──→ Service typesense (ClusterIP 8108) → PVC SSD 100Go│
                            │   ├──→ Milvus prod (ns milvus-prod:19530)            │
                            │   └──→ Embedding VM GPU (10.11.0.2:8555, us-east4)   │
                            └──────────────────────────────────────────────────────┘
```

**Pas d'Ingress externe, pas de TLS public, pas de Cloud Armor** : la sécurité repose sur Internal LoadBalancer + NetworkPolicy ingress allowlist `10.11.0.2/32` (VM API Gateway = unique consommateur).

---

## État actuel du chantier (snapshot 2026-04-30)

| Sprint | Statut | Avancement |
|---|---|---|
| **S0 cadrage docs** | **🟢 terminé** | **100 %** |
| **S1 socle infra GKE** | **🟢 terminé** | **100 %** |
| **S2 Typesense server** | **🟢 terminé** | **100 %** |
| S3 opti-moteur-front | ⚪ à faire | 0 % |
| S4 exposition interne (ILB) | ⚪ à faire | 0 % |
| S5 CI/CD GitHub Actions | ⚪ à faire | 0 % |
| S6 validation + bascule | ⚪ à faire | 0 % |
| S7 backup + observabilité | ⚪ à faire | 0 % |
| S8 rapatriement VM GPU EU | ⚪ à faire | 0 % (dépend quota GPU) |

**Avancement global : 55 %**

Ressources créées sur le cluster :

**S1 ✅** :
- Namespace `moteur-recherche` (labels FinOps OK)
- ServiceAccount `opti-moteur-sa` (K8s simple, sans WI)
- 5 NetworkPolicies : default-deny + allow-dns + allow-egress-milvus + allow-egress-vm-gpu (10.11.0.2:8555) + allow-internal

**S2 ✅** :
- Secret `typesense-api-key` (Opaque, 44 bytes, jamais en Git)
- Service `typesense` (ClusterIP `10.0.76.33:8108`)
- StatefulSet `typesense` (1 réplique Running, image `27.1`, requests=8Gi/2 CPU, limits=16Gi/4 CPU, fsGroup 2000)
- PVC `typesense-data-typesense-0` (100Gi `premium-rwo` SSD, Bound)

---

## Règles strictes (à NE JAMAIS violer)

### Workflow
1. **Une action mutative = une matrice d'impact obligatoire** (`🆕/✏️/❌ • Périmètre • Downtime • Réversible • Risque • Validation`). Pas d'exception.
2. **Pattern dry-run → diff → apply → post-vérif** sur chaque commande mutative.
3. **L'utilisateur exécute lui-même les commandes**. L'agent fournit + accompagne + analyse les retours.
4. **Une étape à la fois**, validation utilisateur entre chaque.
5. **Mettre à jour `etat_avancement.md`** après chaque étape (statut sprint + journal de bord).

### Décisions figées (ne pas remettre en cause sans validation)
- D11 : NetworkPolicies scope ns `moteur-recherche` uniquement (option B)
- D16 : Re-ingestion catalogue = **hors périmètre DevSecOps** (devs s'en chargent)
- D18 : Exposition interne uniquement (Internal LB), **pas** d'Ingress externe / Cloud Armor / TLS public
- D19 : API key Typesense prod = **nouvelle clé forte** (jamais réutiliser `hp_poc_2026` du POC)
- D20 : Liveness `GET /`, Readiness `GET /health`

### Sécurité
- Aucun secret en clair dans Git (utiliser `kubectl create secret` ou ExternalSecrets ; jamais commit `.env` ni manifest avec valeur en dur)
- Image Typesense pinnée `27.1` (pas `:latest`)
- `--enable-cors` Typesense **désactivé en prod** (cf. DT006)
- ClusterIP par défaut, Internal LB pour l'unique exposition

### FinOps
- Labels obligatoires sur toute ressource : `environment=prod`, `owner=devsecops`, `cost-center=ia-rag`, `managed-by=manifest`, `app.kubernetes.io/name=opti-moteur-recherche`
- `requests` ET `limits` toujours définis sur les pods
- Cluster bridé à 60 % d'usage RAM (51 GB libres sur 128) — Typesense `requests=8Gi, limits=16Gi` par défaut

---

## Risques actifs majeurs (résumé)

| # | Risque | Sévérité | Impact opérationnel |
|---|---|---|---|
| R7 | VM GPU `us-east4` ↔ GKE `europe-west1` (latence ~100 ms RTT) | 🔴 | SLO `< 200 ms P95` à la limite. Mitigé S6 (mesure) + S8 (rapatriement EU) |
| R8 | NetworkPolicy enforcement non actif sur le cluster | 🟡 | NetPol déclaratives uniquement. Sécurité réelle via Internal LB |
| R3 | Push prod depuis branche feature | 🔴 | À mitiger S5 via GitHub Environment + required reviewers |
| R5 | API key POC `hp_poc_2026` ne doit pas fuiter | 🔴 | À traiter S2 (clé forte + Secret K8s) |

> Liste complète : `etat_avancement.md` §6.

---

## Stack outils côté DevSecOps (poste local)

- Windows + Git Bash MINGW64
- `gcloud` SDK (configurations `default` + `kubectl-local`)
- `kubectl` ≥ 1.28
- Pas de `jq` disponible → utiliser `kubectl describe` / `-o yaml`
- Tunnel SSH vers bastion `manager-vm-dev` (`ubuntu@34.44.178.81`) avant tout `kubectl`
- Auth via ADC user (token ~1 h) — alias `gke-refresh` recommandé (cf. `debug.md` §3)

Référence runbook critique : `docs/runbooks/gke_kubectl_local.md`

---

## Prochaine action attendue

**S2 — Typesense server** (StatefulSet + PVC SSD 100 Go + Secret API key + Service ClusterIP).

Le sprint demande :
1. Génération nouvelle API key forte (256 bits)
2. Manifests à créer dans `manifests/` :
   - `10-typesense-secret.yaml` (API key, généré localement, **ne pas committer la valeur**)
   - `11-typesense-pvc.yaml` (SSD 100 Go, StorageClass à choisir — `standard-rwo` ou `premium-rwo`)
   - `12-typesense-statefulset.yaml` (image `27.1`, command sans `--enable-cors`, requests=8Gi/limits=16Gi)
   - `13-typesense-service.yaml` (ClusterIP port 8108)
3. `sprint_002_typesense_server.md` : doc opérationnelle avec matrices d'impact

**Avant de démarrer S2** :
- Confirmer la StorageClass à utiliser sur le cluster (`kubectl get sc`)
- Confirmer la taille réelle estimée de l'index (à demander aux devs ou estimer 2,24 M produits × ~10-20 Ko = ~25-50 Go → 100 Go avec marge)
- Convenir de la procédure de génération + remise sécurisée de l'API key au Lead Dev

---

## Glossaire interne

- **opti-moteur-front** : nom de l'app FastAPI Python. Code source : `apps-microservices/opti-moteur-front/`
- **opti-moteur-recherche** : nom de la stack/namespace/projet de migration (= Typesense + opti-moteur-front + infra)
- **API Gateway HelloPro** : routeur applicatif sur VM GPU à `api.hellopro.eu`, **pas** une API Gateway managée GCP/Apigee/Kong
- **POC** : la stack qui tourne actuellement sur la VM GPU en mode dev/test (référence `docker-compose.yaml`)
- **Migration** : ce chantier (S0-S8) — passage POC VM → prod GKE

---

## Mise à jour de ce CLAUDE.md

Ce fichier doit refléter l'**état figé/structurant** du chantier. À mettre à jour :
- Quand une décision majeure est figée (ajouter dans "Décisions figées")
- Quand un sprint passe à 🟢 (mettre à jour le snapshot)
- Quand une nouvelle convention émerge (ajouter dans "Règles strictes")
- **Pas** à chaque commande exécutée → ça, c'est `etat_avancement.md`
