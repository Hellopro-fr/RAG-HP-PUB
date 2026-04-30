# etat_avancement.md — Migration Typesense + opti-moteur-front sur GKE

> Tableau de bord d'avancement. Mis à jour à la fin de chaque sprint ou point d'étape.
> Dernière mise à jour : **2026-04-28**

---

## 1. Synthèse globale

| Indicateur | Valeur |
|---|---|
| **Phase actuelle** | S0 + S1 + S2 terminés, prêt pour S3 (App opti-moteur-front) |
| **Avancement global** | ▓▓▓▓▓▓░░░░ 55 % |
| **Date de démarrage** | 2026-04-28 |
| **Date cible mise en prod** | À définir (T+2 semaines = ~2026-05-12) |
| **Risque global** | 🟢 Vert — pas de blocage à ce stade |

---

## 2. État par sprint

| Sprint | Objectif | Statut | Avancement | Démarré | Terminé | Owner |
|---|---|---|---|---|---|---|
| **S0** | Cadrage / docs initiales (plan, runbook, structure) | 🟢 Terminé | 100 % | 2026-04-28 | 2026-04-30 | DevSecOps |
| **S1** | Cadrage infra GKE (namespace, RBAC, NetworkPolicies) | 🟢 Terminé | 100 % | 2026-04-30 | 2026-04-30 | DevSecOps |
| **S2** | Typesense server prod (StatefulSet + PVC) | 🟢 Terminé | 100 % | 2026-04-30 | 2026-04-30 | DevSecOps |
| **S3** | App opti-moteur-front (Deployment + Service + Config) | ⚪ À faire | 0 % | — | — | DevSecOps + Lead Dev |
| **S4** | Exposition externe (Ingress + Cloud Armor + IP allowlist) | ⚪ À faire | 0 % | — | — | DevSecOps |
| **S5** | Pipeline CI/CD GitHub Actions | ⚪ À faire | 0 % | — | — | DevSecOps |
| **S6** | Validation + bascule front PHP | ⚪ À faire | 0 % | — | — | DevSecOps + Lead Dev + CP |
| **S7** | Backup + observabilité | ⚪ À faire | 0 % | — | — | DevSecOps |
| **S8** | Rapatriement VM GPU embedding `us-east4` → `europe-west1` (post-migration) | ⚪ À faire | 0 % | — | — | DevSecOps |

**Légende statut** : ⚪ À faire | 🟡 En cours | 🟢 Terminé | 🔴 Bloqué | ⏸️ En pause

---

## 3. Décisions clés prises (gel à valider avant exécution)

| # | Décision | Date | Validé par |
|---|---|---|---|
| D1 | Cluster cible : `matching-api-dev-k8s` (zone `europe-west1-b`) malgré nom `-dev` | 2026-04-28 | Utilisateur |
| D2 | Namespace : `moteur-recherche` | 2026-04-28 | Utilisateur |
| D3 | Migrer Typesense server **et** app opti-moteur-front (option b) | 2026-04-28 | Utilisateur |
| D4 | PVC SSD GCE 100 Go extensible pour Typesense | 2026-04-28 | Utilisateur |
| D5 | Embedding service reste sur VM GPU (port 8555, communication VPC déjà OK) | 2026-04-28 | Utilisateur |
| D6 | Trigger CI/CD : push sur `features/opti-moteur-front` + path `apps-microservices/opti-moteur-front/**` | 2026-04-28 | Utilisateur |
| D7 | Pattern CI/CD : nouveau (build + push Artifact Registry + `kubectl set image`) | 2026-04-28 | Utilisateur |
| D8 | Exposition : Ingress GKE + Cloud Armor + IP allowlist | 2026-04-28 | Utilisateur |
| D9 | Structure docs : sous-dossiers `sprints/` + `manifests/` séparés | 2026-04-28 | Utilisateur |
| D10 | Version Typesense : `27.1` (alignée POC) | 2026-04-28 | Utilisateur |
| D11 | NetworkPolicies scope namespace `moteur-recherche` uniquement (option B) — pas de touche au reste du cluster | 2026-04-28 | Utilisateur |
| D12 | SA dédié `opti-moteur-sa` (pod runtime, K8s simple sans WI) — création nouvelle | 2026-04-28 | Utilisateur |
| D13 | SA dédié `cicd-opti-moteur-sa` (pipeline GitHub Actions, rôles minimum) — création nouvelle | 2026-04-28 | Utilisateur |
| D14 | Réutilisation `backup gcs SA` (existant) pour CronJob backup Typesense via Workload Identity | 2026-04-28 | Utilisateur |
| D15 | Matrice d'impact obligatoire pour toute commande mutative (template figé dans runbook §5) | 2026-04-28 | Utilisateur |
| D16 | Stratégie migration index Typesense : **(b) démarrage à vide**. Re-ingestion **à la charge des devs** (hors périmètre DevSecOps). Notre rôle : livrer infra propre + fournir IP/endpoints/secrets | 2026-04-28 | Utilisateur |
| D17 | Pas de node pool dédié → cluster bridé à 60 % d'usage RAM (51 GB libres). Typesense `requests=8Gi, limits=16Gi` | 2026-04-28 | Utilisateur |
| D18 | **Exposition interne uniquement** : Service `Internal LoadBalancer` + global access. Pas d'Ingress externe, pas de TLS managé, pas de Cloud Armor. API Gateway VM GPU (`10.11.0.2`) = unique consommateur | 2026-04-28 | Utilisateur |
| D19 | API key Typesense prod = nouvelle clé forte générée (pas de contrainte de compat, Q8=b) | 2026-04-28 | Utilisateur |
| D20 | Probes : Liveness = `GET /` (light), Readiness = `GET /health` (vérifie Typesense en cascade) | 2026-04-28 | Source code |
| D21 | API Gateway `api.hellopro.eu/optimoteur-service` hébergée sur **la même VM GPU** que l'embedding (`vm-embedding-g2-std-24-use`, `10.11.0.2`, us-east4) | 2026-04-28 | Utilisateur |
| D22 | API key Typesense prod générée via `openssl rand -base64 32` (≥ 32 octets, base64). Stockage Secret K8s. Canal de remise Lead Dev : à valider en S2 | 2026-04-30 | Utilisateur |
| D23 | PVC Typesense initial 100 Go SSD, **extensible** (StorageClass à valider via `kubectl get sc`) | 2026-04-30 | Utilisateur |
| D24 | StorageClass = `premium-rwo` (CSI SSD, WaitForFirstConsumer, allowVolumeExpansion=true). ReclaimPolicy `Delete` accepté + mitigation = backups GCS S7 + procédure interdiction de `kubectl delete pvc` manuel | 2026-04-30 | DevSecOps |

---

## 4. Livrables documentaires

| Livrable | Statut | Lien |
|---|---|---|
| `plan.md` | 🟢 Terminé | [plan.md](plan.md) |
| `runbook.md` | 🟢 Terminé | [runbook.md](runbook.md) |
| `etat_avancement.md` | 🟢 Terminé (initial) | [etat_avancement.md](etat_avancement.md) |
| `sprint_001_cadrage.md` | ⚪ À faire | — |
| `sprint_002_typesense_server.md` | ⚪ À faire | — |
| `sprint_003_opti_moteur_front.md` | ⚪ À faire | — |
| `sprint_004_exposition_externe.md` | ⚪ À faire | — |
| `sprint_005_cicd.md` | ⚪ À faire | — |
| `sprint_006_validation.md` | ⚪ À faire | — |
| `sprint_007_backup_observabilite.md` | ⚪ À faire | — |
| `debug.md` | 🟢 Terminé | [debug.md](debug.md) |
| `CLAUDE.md` | 🟢 Terminé | [CLAUDE.md](CLAUDE.md) |
| `PENSE_IA.md` | 🟢 Terminé | [PENSE_IA.md](PENSE_IA.md) |

---

## 5. Points ouverts / décisions en attente

| # | Sujet | Type | Action attendue |
|---|---|---|---|
| ~~Q1~~ | ~~Endpoint exact de ré-ingestion catalogue~~ → **Hors périmètre DevSecOps (D16) — à charge des devs** | ✅ | Résolu 2026-04-28 |
| Q2 | Bucket GCS exact à réutiliser pour backups Typesense | Identification | DevSecOps à valider en S7 |
| ~~Q3~~ | ~~Nom DNS interne / IP de la VM GPU~~ → **Résolu : `10.11.0.2/32` (vm-embedding-g2-std-24-use, us-east4-c)** | ✅ | Résolu 2026-04-28 |
| Q4 | Décision GitHub Environment `production` + required reviewers | Sécurité CI/CD | À trancher avant S5 |
| Q5 | Refactor `EMBEDDING_SERVICE_URL` : `os.getenv` → Pydantic `BaseSettings` | Code drift mineur | Hors périmètre, ticket à créer |
| Q6 | API key Typesense prod (générer + stocker dans Secret K8s) | Sécurité | DevSecOps avant S2 |
| Q7 | Hardening NetPol `allow-internal-namespace` (sélecteurs `tier=app`/`tier=db` au lieu de `podSelector: {}`) | Hardening | Post-S6, à planifier après stabilisation |

---

## 6. Risques actifs

| # | Risque | Criticité | Statut | Mitigation prévue |
|---|---|---|---|---|
| R1 | Cluster `-dev` héberge prod (confusion ops) | 🟡 Moyenne | Accepté | Tracé `debug.md` § dette technique |
| R2 | Embedding VM GPU = SPOF pour la recherche | 🔴 Haute | Accepté provisoirement | Migration GKE prévue ultérieurement |
| R3 | Push direct prod depuis branche feature | 🔴 Haute | À traiter en S5 | GitHub Environment + required reviewers |
| R4 | Re-ingestion 2,24 M produits longue (1ère fois) | 🟡 Moyenne | À traiter en S6 | Job dédié hors heures pic |
| R5 | API key POC `hp_poc_2026` ne doit pas fuiter en prod | 🔴 Haute | À traiter en S2 | Génération clé forte + Secret K8s |
| R6 | `--enable-cors` Typesense ouvert (POC) | 🟡 Moyenne | À traiter en S2 | Désactivé en prod, CORS géré par app |
| R7 | **VM GPU embedding en `us-east4` ↔ GKE en `europe-west1`** : latence inter-régions ~90-100 ms RTT + coûts egress. Cause root : quota GPU L4 indisponible en `europe-west1` au moment du provisionnement | 🔴 Haute | Mitigation S6 + S8 | S6 : mesurer latence réelle. S8 : rapatriement VM en `europe-west1` une fois quota obtenu (demande quota GCP à ouvrir) |
| R8 | **NetworkPolicy enforcement non actif** sur cluster `matching-api-dev-k8s` (ni Calico legacy, ni Dataplane V2). NetPol appliquées sont **déclaratives uniquement** | 🟡 Moyenne | Accepté pour cette migration | Chantier de hardening cluster séparé : activer NetworkPolicy addon (option B) ou recréer cluster en Dataplane V2. À planifier hors S0-S8 |

---

## 7. Prochaines actions immédiates

1. ⏳ Validation utilisateur de `etat_avancement.md` (vous êtes ici)
2. ⏭️ Production de `sprint_001_cadrage.md` (livrable n°4)
3. ⏭️ Production de `debug.md`, `CLAUDE.md`, `PENSE_IA.md` (livrables n°5 à 7)
4. ⏭️ Sur validation S0 complet → démarrage S1 (création namespace + RBAC + NetworkPolicies)

---

## 8. Format de mise à jour (à respecter)

Quand un sprint avance, mettre à jour ce fichier dans cet ordre :

1. **§1 Synthèse** : barre de progression globale + phase actuelle
2. **§2 État par sprint** : statut + avancement + dates si applicable
3. **§3 Décisions** : ajouter une ligne pour chaque nouvelle décision figée
4. **§4 Livrables** : passer le statut à 🟢 quand un fichier est validé
5. **§5 Points ouverts** : retirer les points résolus, ajouter les nouveaux
6. **§6 Risques** : mettre à jour le statut, ajouter les nouveaux risques détectés
7. **§7 Prochaines actions** : actualiser
8. **§9 Historique** : ajouter une ligne au journal de bord

Mettre à jour la date "Dernière mise à jour" en tête du fichier à chaque modification.

---

## 9. Historique (journal de bord)

| Date | Action | Auteur |
|---|---|---|
| 2026-04-28 | Cadrage initial : 10 décisions figées (D1-D10), risques R1-R6 identifiés | DevSecOps |
| 2026-04-28 | Production `plan.md` (7 sprints, ~6 j/h) | DevSecOps |
| 2026-04-28 | Production `runbook.md` global (10 sections, checklists sécu + obs) | DevSecOps |
| 2026-04-28 | Production `etat_avancement.md` (état initial) | DevSecOps |
| 2026-04-28 | Décisions D11-D15 figées (NetworkPolicies option B, 3 SAs, matrice d'impact obligatoire) | Utilisateur |
| 2026-04-28 | Rétro-équipement runbook.md §5 avec matrices d'impact (5.3 / 5.4 / 5.5 / 5.6) | DevSecOps |
| 2026-04-28 | Production sprint_001 + 7 manifests YAML + démarrage exécution accompagnée | DevSecOps |
| 2026-04-28 | Incident auth `kubectl Unauthorized` → résolu par refresh ADC token (cf. runbook gke_kubectl_local.md §9.3) | Utilisateur + DevSecOps |
| 2026-04-28 | Discovery 4.1 : service Milvus = `milvus-prod` (ns milvus-prod, ports 19530/9091) confirmé | Utilisateur |
| 2026-04-28 | Discovery 4.2 : VM GPU = `vm-embedding-g2-std-24-use` (us-east4-c), IP `10.11.0.2`, port 8555 | Utilisateur |
| 2026-04-28 | **Risque R7 ouvert** : VM GPU US-East ↔ GKE EU-West, latence inter-régions impactant SLO recherche | DevSecOps |
| 2026-04-28 | Décisions D16-D21 figées : démarrage à vide, ingestion hors périmètre DevSecOps, exposition interne ILB, probes liveness/readiness | Utilisateur |
| 2026-04-28 | S4 simplifié : ILB interne au lieu d'Ingress externe + Cloud Armor → effort 1 j → 0,3 j | DevSecOps |
| 2026-04-28 | runbook §2 architecture, §5.3 ingestion, §6.1 bascule, §7 sécurité réécrits | DevSecOps |
| 2026-04-30 | **S1 Étape 1 ✅** — namespace `moteur-recherche` créé, 6 labels FinOps validés, ns vide | Utilisateur (apply) |
| 2026-04-30 | **S1 Étape 2 ✅** — SA `opti-moteur-sa` créé, labels OK, no WI (conforme D12) | Utilisateur (apply) |
| 2026-04-30 | **R8 ouvert** : NetworkPolicy enforcement non actif sur cluster — NetPol déclaratives uniquement (chantier hardening séparé) | DevSecOps |
| 2026-04-30 | **S1 Étape 3 ✅** — 5 NetPol appliquées (default-deny + allow-dns + allow-milvus + allow-vm-gpu + allow-internal) | Utilisateur (apply) |
| 2026-04-30 | **S1 TERMINÉ ✅** (100 %) — socle infra GKE prêt pour S2 (Typesense server) | DevSecOps |
| 2026-04-30 | Production `debug.md` (2 incidents + 6 dettes techniques DT001-DT006) | DevSecOps |
| 2026-04-30 | Production `CLAUDE.md` (point d'entrée IA/humain, 190 lignes, hard facts YAML) | DevSecOps |
| 2026-04-30 | Production `PENSE_IA.md` (7 patterns + 7 décisions structurantes + anti-patterns) | DevSecOps |
| 2026-04-30 | **S0 TERMINÉ ✅** (100 %) — pack documentaire complet | DevSecOps |
| 2026-04-30 | Production sprint_002 + 4 manifests YAML (Secret template, PVC ref, StatefulSet, Service) + D24 figée (StorageClass `premium-rwo`) | DevSecOps |
| 2026-04-30 | DT007 ouverte (reclaimPolicy=Delete sur SC) + DT008 ouverte (Typesense root in container) | DevSecOps |
| 2026-04-30 | **S2 Étape 6.1 ✅** — Secret `typesense-api-key` créé via one-liner openssl, 6 labels, valeur transmise hors Git | Utilisateur |
| 2026-04-30 | **S2 Étape 6.2 ✅** — Service `typesense` ClusterIP `10.0.76.33:8108` créé | Utilisateur |
| 2026-04-30 | **S2 Étape 6.3 ✅** — StatefulSet `typesense` Running 1/1 (cold start 26s), PVC 100Gi `premium-rwo` Bound | Utilisateur |
| 2026-04-30 | Incident #003 (`kubectl get pods,pvc -w` invalide) + #004 (`curl` absent dans image typesense:27.1) résolus + tracés | DevSecOps |
| 2026-04-30 | Smoketests Typesense ✅ : `/health` interne via Service, écriture `/data` (fsGroup=2000), CRUD collection `_smoketest` via API key | Utilisateur |
| 2026-04-30 | **S2 TERMINÉ ✅** (100 %) — stack Typesense opérationnelle en prod GKE | DevSecOps |
