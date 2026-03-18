# Phase 3 - Securisation Infrastructure & Applications

> **Date debut**: 2026-03-17
> **Derniere MAJ**: 2026-03-18
> **Duree estimee**: 3-4 semaines
> **Responsable**: DevSecOps / Cloud SRE
> **Prerequis**: Phase 2 (Terraform Refactoring) terminee
> **Rapport remediation**: `docs/rapports/rapport_remediation_securite_20260318.md`

---

## Objectifs

1. Eliminer toutes les vulnerabilites critiques (score securite 35% -> 80%+)
2. Consolider l'infrastructure Terraform en une seule racine
3. Migrer tous les services exposes vers Internal Load Balancers
4. Implementer IAM least privilege et Secret Manager
5. Securiser les applications (CORS, healthchecks, validation)

---

## Suivi des Taches

### 3.0 - Pre-requis : Urgences & Consolidation

| ID | Tache | Priorite | Status | Date | Notes |
|----|-------|----------|--------|------|-------|
| 3.0.1 | Runbook urgences securite | CRITIQUE | ✅ Fait | 2026-03-17 | `docs/runbooks/security_remediation.md` |
| 3.0.2 | Execution urgences (SEC-1,2,3,10) | CRITIQUE | ✅ Fait | 2026-03-18 | Rapport: `docs/rapports/rapport_remediation_securite_20260318.md` |
| 3.0.3 | Fusion racines Terraform | HAUTE | ✅ Code | 2026-03-17 | 4 modules crees et commentes dans main.tf |
| 3.0.4 | Correction ssh_allowed_ips | HAUTE | ✅ Fait | 2026-03-17 | 0.0.0.0/0 -> 35.235.240.0/20 |
| 3.0.5 | Nettoyage state TF orphelin | HAUTE | ⬜ | - | 24 ressources a supprimer |

### 3.1 - Securisation Reseau

| ID | Tache | Priorite | Status | Date | Notes |
|----|-------|----------|--------|------|-------|
| 3.1.1 | Module Cloud NAT | HAUTE | ⬜ | - | Nouveau module TF |
| 3.1.2 | Retrait IP publique VM GPU | HAUTE | ⬜ | - | Apres Cloud NAT actif |
| 3.1.3 | Migration Redis -> ILB | HAUTE | ✅ Deja fait | 2026-03-18 | ILB `10.0.1.220` + AUTH active + FW supprimee |
| 3.1.4 | Migration Qdrant -> ILB | HAUTE | 🔄 Partiel | 2026-03-18 | PROD OK. DEV a verifier (`34.52.142.50`) |
| 3.1.5 | Migration RabbitMQ -> ILB | HAUTE | ✅ Deja fait | 2026-03-18 | 1 instance v3 sur ILB `10.0.1.216`. Port 34.78.143.55 ferme |
| 3.1.6 | Health checks ILB | MOYENNE | ⬜ | - | Decommenter lignes 48-55 |
| 3.1.7 | K8s Network Policies | MOYENNE | ⬜ | - | Redis, RabbitMQ, Milvus, Qdrant |

### 3.2 - IAM & Secrets

| ID | Tache | Priorite | Status | Date | Notes |
|----|-------|----------|--------|------|-------|
| 3.2.1 | Workload Identity GKE | HAUTE | ⬜ | - | modules/gke_cluster/ |
| 3.2.2 | Module Secret Manager | HAUTE | ⬜ | - | rabbitmq, redis, jwt, milvus |
| 3.2.3 | External Secrets Operator | MOYENNE | ⬜ | - | Installation sur GKE |
| 3.2.4 | SA dedies par service | MOYENNE | ⬜ | - | Remplacer SA default compute@ |
| 3.2.5 | Rotation credentials | HAUTE | ✅ Fait | 2026-03-18 | JWT renforce (hex 64), ADMIN_KEY deja OK, RabbitMQ non-defaut |

### 3.3 - Securisation Applicative

| ID | Tache | Priorite | Status | Date | Notes |
|----|-------|----------|--------|------|-------|
| 3.3.1 | CORS restrictif | MOYENNE | ⬜ | - | allow_origins=["*"] -> specifique |
| 3.3.2 | Healthchecks 71 services | MOYENNE | ⬜ | - | Ajouter /health + Docker HEALTHCHECK |
| 3.3.3 | Validation gRPC | BASSE | ⬜ | - | Pydantic + proto validation |

---

## Criteres de Validation Phase 3

- [ ] Aucune regle firewall avec source 0.0.0.0/0 (sauf HTTP/HTTPS API Gateway)
- [ ] Redis, Qdrant, RabbitMQ uniquement accessibles en interne
- [ ] VM GPU sans IP publique (acces IAP uniquement)
- [ ] Cloud NAT fonctionnel (VM peut acceder Internet)
- [ ] Workload Identity actif sur GKE
- [ ] Secrets dans Secret Manager (pas dans .env)
- [ ] Score securite audit > 70%
- [ ] `terraform plan` = 0 unexpected changes
- [ ] Matrice de connectivite validee (script test_connectivity.sh)

---

## Risques et Mitigations

| Risque | Probabilite | Impact | Mitigation |
|--------|------------|--------|------------|
| Coupure services apres changement firewall | HAUTE | CRITIQUE | Matrice de test, fenetre maintenance, rollback pret |
| terraform apply revert fixes manuels | HAUTE | HAUTE | terraform plan obligatoire, import ressources |
| Perte messages RabbitMQ pendant migration | MOYENNE | HAUTE | Drainer les queues avant migration |
| Workload Identity casse auth pods | MOYENNE | MOYENNE | Rollout progressif, fallback ancien SA |
