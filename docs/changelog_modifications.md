# Journal des Modifications - Projet RAG HelloPro GCP

> **Objectif** : Tracer chaque modification effectuee, son contexte, et son impact production.
> **Convention** : Chaque modification est numerotee (MOD-XXX) et liee a une phase du plan.

---

## MOD-001 : Correction numerotation phases - etat_avancement.md

| Champ | Detail |
|-------|--------|
| **Date** | 2026-03-17 |
| **Fichier** | `docs/etat_avancement.md` |
| **Phase du plan** | Etape 0 - Mise a jour documentation |
| **Modification** | Alignement de la numerotation des phases avec `plan.md` (Phase 3=Securisation, Phase 4=CI/CD, Phase 5=Documentation). Mise a jour de la date, ajout des nouvelles sections "Points d'Attention" et "Prochaines Etapes" detaillees. |
| **Pourquoi** | L'ancien fichier avait un decalage de numerotation (Phase 4=Securisation) par rapport au plan de reference (`plan.md` Phase 3=Securisation). Cela creait de la confusion. |
| **Impact prod** | ZERO - Documentation uniquement |

---

## MOD-002 : Mise a jour plan.md avec sous-taches Phase 3/4/5

| Champ | Detail |
|-------|--------|
| **Date** | 2026-03-17 |
| **Fichier** | `docs/plan.md` |
| **Phase du plan** | Etape 0 - Mise a jour documentation |
| **Modification** | Version 1.1 -> 1.2. Ajout de sous-taches detaillees pour Phase 3 (3.0.x, 3.1.x, 3.2.x, 3.3.x), Phase 4 (4.1 a 4.5) et Phase 5 (5.1 a 5.8). Mise a jour de la structure documentaire. |
| **Pourquoi** | Le plan original n'avait que 6 taches par phase sans granularite suffisante pour le suivi. |
| **Impact prod** | ZERO - Documentation uniquement |

---

## MOD-003 : Enrichissement rapport audit securite

| Champ | Detail |
|-------|--------|
| **Date** | 2026-03-17 |
| **Fichier** | `docs/audit/rapport_audit_securite.md` |
| **Phase du plan** | Etape 0 - Mise a jour documentation |
| **Modification** | Ajout section "Mise a Jour Audit - 2026-03-17" avec : VULN-004 (duplication TF avec faille SSH), VULN-005 (credentials par defaut), VULN-006 (gRPC sans TLS), VULN-007 (CORS permissif), VULN-008 (healthchecks absents). Ajout tableau etat remediations et metriques mises a jour. |
| **Pourquoi** | L'audit initial (02/05) ne couvrait pas les vulnerabilites applicatives decouvertes lors de l'analyse du code source. |
| **Impact prod** | ZERO - Documentation uniquement |

---

## MOD-004 : Enrichissement rapport audit infrastructure

| Champ | Detail |
|-------|--------|
| **Date** | 2026-03-17 |
| **Fichier** | `docs/audit/rapport_audit_infra.md` |
| **Phase du plan** | Etape 0 - Mise a jour documentation |
| **Modification** | Ajout section "Mise a Jour Audit - 2026-03-17" avec : probleme double racine Terraform, 24 ressources orphelines dans state, health checks ILB desactives, couverture Prometheus insuffisante, recommandations I1 a I5. |
| **Pourquoi** | L'analyse du code Terraform a revele des problemes architecturaux non couverts par l'audit initial. |
| **Impact prod** | ZERO - Documentation uniquement |

---

## MOD-005 : Creation runbook remediation securite

| Champ | Detail |
|-------|--------|
| **Date** | 2026-03-17 |
| **Fichier** | `docs/runbooks/security_remediation.md` (NOUVEAU) |
| **Phase du plan** | Etape 1 - Tache 3.0.1 |
| **Modification** | Creation du runbook complet avec commandes gcloud/kubectl pour : SEC-1 (Redis ILB), SEC-2 (suppression RDP), SEC-3 (RabbitMQ ILB), SEC-4 (Qdrant ILB), SEC-10 (rotation credentials). Inclut diagnostics, rollbacks, matrice de tests et script de validation. |
| **Pourquoi** | L'equipe doit pouvoir valider et executer les remediations securite de maniere autonome et tracable. |
| **Impact prod** | ZERO - Document de procedures, pas d'execution |

---

## MOD-006 : Creation suivi Phase 3

| Champ | Detail |
|-------|--------|
| **Date** | 2026-03-17 |
| **Fichier** | `docs/phases/phase3_securisation.md` (NOUVEAU) |
| **Phase du plan** | Etape 0 - Documentation |
| **Modification** | Creation du fichier de suivi detaille Phase 3 avec tableaux de taches, criteres de validation et risques. |
| **Pourquoi** | Chaque phase doit avoir son fichier de suivi dedie pour le tracking granulaire. |
| **Impact prod** | ZERO - Documentation uniquement |

---

## MOD-007 : Creation suivi Phase 4

| Champ | Detail |
|-------|--------|
| **Date** | 2026-03-17 |
| **Fichier** | `docs/phases/phase4_cicd.md` (NOUVEAU) |
| **Phase du plan** | Etape 0 - Documentation |
| **Modification** | Creation du fichier de suivi detaille Phase 4 CI/CD avec etat des lieux workflows existants, bugs identifies et taches. |
| **Pourquoi** | Preparation du suivi Phase 4 avec inventaire des problemes existants dans les workflows GH Actions. |
| **Impact prod** | ZERO - Documentation uniquement |

---

## MOD-008 : Correction ssh_allowed_ips (infra-ci-cd)

| Champ | Detail |
|-------|--------|
| **Date** | 2026-03-17 |
| **Fichier** | `infra-ci-cd/terraform/variables.tf` (ligne 44) |
| **Phase du plan** | Etape 2 - Tache 3.0.4 |
| **Modification** | `default = ["0.0.0.0/0"]` remplace par `default = ["35.235.240.0/20"]` (plage IAP Google) |
| **Pourquoi** | Variable par defaut dangereuse : si `infra-ci-cd/terraform/` est applique sans surcharger cette variable, SSH serait ouvert au monde entier. |
| **Impact prod** | ZERO - `infra-ci-cd/terraform/` n'a jamais ete applique sur GCP. Correction preventive. |

---

## MOD-009 : Creation module Cloud NAT

| Champ | Detail |
|-------|--------|
| **Date** | 2026-03-17 |
| **Fichiers** | `infra-microservices/modules/cloud_nat/main.tf`, `variables.tf`, `outputs.tf` (NOUVEAUX) |
| **Phase du plan** | Etape 3 - Tache 3.1.1 |
| **Modification** | Creation du module Terraform Cloud NAT (Cloud Router + NAT config avec logs). |
| **Pourquoi** | Prerequis pour retirer l'IP publique de la VM GPU. Permet acces Internet sortant sans IP publique. |
| **Impact prod** | ZERO - Module commente dans main.tf. Ne sera actif qu'apres decommenter + terraform apply. |

---

## MOD-010 : Creation module Secret Manager

| Champ | Detail |
|-------|--------|
| **Date** | 2026-03-17 |
| **Fichiers** | `infra-microservices/modules/secret_manager/main.tf`, `variables.tf`, `outputs.tf` (NOUVEAUX) |
| **Phase du plan** | Etape 4 - Tache 3.2.2 |
| **Modification** | Creation du module Terraform Secret Manager avec support for_each pour creer N secrets. |
| **Pourquoi** | Centraliser la gestion des secrets (actuellement en .env / variables d'environnement). Migre depuis infra-ci-cd/terraform/main.tf. |
| **Impact prod** | ZERO - Module commente dans main.tf. Ne sera actif qu'apres decommenter + terraform apply. |

---

## MOD-011 : Creation module Monitoring

| Champ | Detail |
|-------|--------|
| **Date** | 2026-03-17 |
| **Fichiers** | `infra-microservices/modules/monitoring/main.tf`, `variables.tf`, `outputs.tf` (NOUVEAUX) |
| **Phase du plan** | Etape 7 - Tache 5.3 |
| **Modification** | Creation du module Terraform Monitoring avec alertes CloudRun, GKE CPU, disk usage et budget. |
| **Pourquoi** | Alerting centralise et reproductible via IaC. Migre et enrichi depuis infra-ci-cd/terraform/main.tf. |
| **Impact prod** | ZERO - Module commente dans main.tf. Ne sera actif qu'apres decommenter + terraform apply. |

---

## MOD-012 : Creation module Service Accounts

| Champ | Detail |
|-------|--------|
| **Date** | 2026-03-17 |
| **Fichiers** | `infra-microservices/modules/service_accounts/main.tf`, `variables.tf`, `outputs.tf` (NOUVEAUX) |
| **Phase du plan** | Etape 4 - Tache 3.2.4 |
| **Modification** | Creation du module Terraform pour Service Accounts CI/CD et dedies (cloud-build-deployer, cloudrun-services, milvus-reader, etc.). |
| **Pourquoi** | Remplacer le SA par defaut compute@ par des SA dedies avec moindre privilege. Migre depuis infra-ci-cd/terraform/main.tf. |
| **Impact prod** | ZERO - Module commente dans main.tf. Ne sera actif qu'apres decommenter + terraform apply. |

---

## MOD-013 : Ajout appels modules dans main.tf (COMMENTES)

| Champ | Detail |
|-------|--------|
| **Date** | 2026-03-17 |
| **Fichier** | `infra-microservices/main.tf` (lignes 213-295) |
| **Phase du plan** | Etape 2 - Consolidation Terraform |
| **Modification** | Ajout des appels aux 4 nouveaux modules (cloud_nat, secret_manager, service_accounts, monitoring). **Les 4 sont COMMENTES** - aucun n'est actif. |
| **Pourquoi** | Preparer le code pour activation progressive. Chaque module sera decommente un par un apres validation. |
| **Impact prod** | ZERO - Tout est commente. Un `terraform plan` ne montrera aucun changement lie a ces modules. |

---

## MOD-014 : Execution SEC-2 - Suppression regle firewall RDP

| Champ | Detail |
|-------|--------|
| **Date** | 2026-03-18 |
| **Fichier** | Regle GCP `default-allow-rdp` (pas de fichier local) |
| **Phase du plan** | Phase 3 - SEC-2 |
| **Modification** | Suppression de la regle firewall `default-allow-rdp` via `gcloud compute firewall-rules delete`. Backup JSON sauvegarde avant suppression. |
| **Pourquoi** | Regle inutile : aucun workload Windows. Elimination de surface d'attaque. |
| **Constat reel vs audit** | L'audit indiquait source `0.0.0.0/0`. En realite : regle **desactivee** et restreinte a 3 IPs bureau. Risque reel quasi nul mais suppression reste la bonne pratique. |
| **Impact prod** | ZERO - Aucun service n'utilise RDP/3389 |

---

## MOD-015 : Execution SEC-10 - Rotation JWT_SECRET

| Champ | Detail |
|-------|--------|
| **Date** | 2026-03-18 |
| **Fichier** | `.env` sur VM GPU `vm-embedding-g2-std-24-use` |
| **Phase du plan** | Phase 3 - SEC-10 |
| **Modification** | Remplacement de `JWT_SECRET=SecretPassJWT2626` par un secret fort genere via `openssl rand -hex 32`. Redemarrage api-gateway-service. |
| **Pourquoi** | L'ancien secret etait court et a pattern previsible. Le nouveau est un hex 64 chars cryptographiquement aleatoire. |
| **Constat reel vs audit** | L'audit indiquait `changeme-jwt-secret`. En realite c'etait deja change en `SecretPassJWT2626` (faible mais pas defaut). GATEWAY_ADMIN_KEY etait deja une cle forte 64+ chars. |
| **Impact prod** | FAIBLE - Invalidation des tokens JWT existants, reconnexion necessaire |

---

## MOD-016 : Corrections audit - Ecarts constates vs realite terrain

| Champ | Detail |
|-------|--------|
| **Date** | 2026-03-18 |
| **Fichiers** | `docs/audit/rapport_audit_securite.md`, `docs/runbooks/security_remediation.md` |
| **Phase du plan** | Phase 3 - Mise a jour documentation |
| **Modification** | Mise a jour des statuts SEC et correction des ecarts entre audit et realite : (1) RDP etait deja desactive+restreint, (2) JWT/ADMIN_KEY deja changes, (3) RabbitMQ consolide en 1 instance sur ILB interne, (4) Redis migre sur ILB interne `10.0.1.220` |
| **Pourquoi** | L'equipe avait deja initie des remediations non documentees. Les rapports doivent refleter l'etat reel. |
| **Impact prod** | ZERO - Documentation uniquement |

---

## MOD-017 : Creation rapport de remediation securite

| Champ | Detail |
|-------|--------|
| **Date** | 2026-03-18 |
| **Fichier** | `docs/rapports/rapport_remediation_securite_20260318.md` (NOUVEAU) |
| **Phase du plan** | Phase 3 - SEC-1,2,3,10 |
| **Modification** | Rapport complet de toutes les remediations executees le 2026-03-18 : SEC-2 (RDP supprime), SEC-10 (JWT renforce), SEC-1 (Redis deja ILB), SEC-3 (RabbitMQ deja ILB). Inclut ecarts audit vs realite, metriques avant/apres, actions restantes. |
| **Pourquoi** | Documenter chaque action de remediation avec constat reel vs audit pour tracabilite et suivi. |
| **Impact prod** | ZERO - Documentation |

---

## MOD-018 : Mise a jour docs post-remediation (etat_avancement, plan, phase3)

| Champ | Detail |
|-------|--------|
| **Date** | 2026-03-18 |
| **Fichiers** | `docs/etat_avancement.md`, `docs/plan.md` (v1.3), `docs/phases/phase3_securisation.md` |
| **Phase du plan** | Phase 3 - Documentation |
| **Modification** | Mise a jour des statuts de toutes les taches SEC traitees (3.0.1, 3.0.2, 3.0.3, 3.0.4, 3.1.3, 3.1.5, 3.2.5). Correction des informations erronees (2x RabbitMQ -> 1x, score securite 35% -> 55-60%). Progression Phase 3 : 5% -> 25%. |
| **Pourquoi** | Les documents doivent refleter l'etat reel post-remediation. |
| **Impact prod** | ZERO - Documentation |
