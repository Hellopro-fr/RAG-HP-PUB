# Phase 4 - Pipeline CI/CD DevSecOps

> **Date debut**: A planifier (apres Phase 3)
> **Duree estimee**: 2-3 semaines
> **Responsable**: DevSecOps / Lead Dev
> **Prerequis**: Phase 3 (Securisation) terminee

---

## Objectifs

1. Corriger les workflows GitHub Actions existants (bugs identifies)
2. Creer des workflows reutilisables pour eliminer la duplication (39 -> ~5 fichiers)
3. Integrer des scans de securite dans le pipeline CI
4. Automatiser le deploiement Terraform via pipeline
5. Mettre en place le deploiement automatise CloudRun + VM

---

## Etat des Lieux

### Workflows Existants (39 fichiers)
- 13 CI (test) : Pattern identique Python 3.13 + pytest
- 13 CD (build/push) : Pattern identique Docker build + push Artifact Registry + CloudRun deploy
- 13 Pipeline (orchestration) : Coordonnent CI -> CD
- 3 Terraform : dev, int, prod

### Bugs Identifies
- **Bug 1** : `${{ secret.ENV_FILE_EMBEDDING }}` manque le 's' -> `${{ secrets.ENV_FILE_EMBEDDING }}`
  - Fichiers concernes : tous les 13 CD workflows
- **Bug 2** : Tag mismatch Docker build/push (SHA suffix manquant au push)
- **Bug 3** : `--allow-unauthenticated` sur CloudRun (a evaluer par service)

### Matrice de Deploiement (service-matrix.yaml)
- **CloudRun** : 15 services (API-heavy, stateless)
- **VM GPU** : 33 services (processors, ML/AI, databases)
- **Disabled** : 5 services (outils one-off)

---

## Suivi des Taches

### 4.1 - Correction Workflows Existants

| ID | Tache | Priorite | Status | Notes |
|----|-------|----------|--------|-------|
| 4.1.1 | Corriger typo secret dans 13 CD workflows | HAUTE | ⬜ | secret -> secrets |
| 4.1.2 | Corriger tag mismatch Docker | HAUTE | ⬜ | Standardiser nommage |
| 4.1.3 | Evaluer --allow-unauthenticated | MOYENNE | ⬜ | Par service |

### 4.2 - Workflows Reutilisables

| ID | Tache | Priorite | Status | Notes |
|----|-------|----------|--------|-------|
| 4.2.1 | _reusable-ci.yml | HAUTE | ⬜ | Parametrise: service, Python/Node, tests |
| 4.2.2 | _reusable-cd-cloudrun.yml | HAUTE | ⬜ | Build, push, deploy CloudRun |
| 4.2.3 | _reusable-cd-vm.yml | HAUTE | ⬜ | Build, push, deploy VM (deploy-to-vm.sh) |
| 4.2.4 | Migration workflows existants | HAUTE | ⬜ | 39 -> appels reusable |

### 4.3 - Scans Securite

| ID | Tache | Priorite | Status | Notes |
|----|-------|----------|--------|-------|
| 4.3.1 | Trivy (images Docker) | HAUTE | ⬜ | Block CRITICAL/HIGH |
| 4.3.2 | Bandit (Python security) | HAUTE | ⬜ | Linting securite |
| 4.3.3 | gitleaks (secret detection) | HAUTE | ⬜ | Pre-commit + CI |
| 4.3.4 | Snyk integration | MOYENNE | ⬜ | Binary deja present dans repo |

### 4.4 - Pipeline Terraform

| ID | Tache | Priorite | Status | Notes |
|----|-------|----------|--------|-------|
| 4.4.1 | Workflow terraform-plan-apply.yml | HAUTE | ⬜ | Plan sur PR, Apply sur merge |
| 4.4.2 | Workload Identity Federation | HAUTE | ⬜ | Remplacer cles JSON SA |
| 4.4.3 | Plan output en commentaire PR | MOYENNE | ⬜ | Visibilite equipe |

### 4.5 - Deploiement

| ID | Tache | Priorite | Status | Notes |
|----|-------|----------|--------|-------|
| 4.5.1 | Ameliorer deploy-to-vm.sh | HAUTE | ⬜ | Health snapshot + auto-rollback |
| 4.5.2 | Ameliorer health-check.sh | HAUTE | ⬜ | Couverture tous services |
| 4.5.3 | Test rollback.sh | MOYENNE | ⬜ | Validation CloudRun + VM |

---

## Criteres de Validation Phase 4

- [ ] Tous les workflows CI/CD fonctionnels (test avec un service pilote)
- [ ] Scans securite integres et bloquants sur CRITICAL
- [ ] Pipeline Terraform automatise (plan sur PR, apply sur merge)
- [ ] Deploiement CloudRun automatise pour les 15 services
- [ ] Deploiement VM automatise pour les 33 services
- [ ] Rollback fonctionne dans les deux cibles
- [ ] Aucune cle JSON SA dans les secrets GitHub (WIF uniquement)
