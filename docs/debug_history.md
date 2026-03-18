# 🐛 Debug History - Projet RAG HelloPro GCP

> **Objectif** : Journal chronologique des problèmes rencontrés et solutions appliquées

---

## Format des Entrées

```
### [DATE] - [TITRE DU PROBLÈME]
**Contexte** : Description du contexte
**Symptôme** : Ce qui a été observé
**Cause** : Analyse de la cause racine
**Solution** : Action corrective appliquée
**Prévention** : Mesures pour éviter la récurrence
```

---

## 📅 Journal

### 2026-02-05 - Initialisation du projet

**Contexte** : Reprise d'un projet RAG existant avec dérive IaC significative

**Symptôme** : 
- Codes Terraform ne reflètent plus l'infrastructure déployée
- VM GPU créée via Console GCP (hors Terraform)
- Services applicatifs déplacés vers VM GPU

**Cause** : 
- Évolution du projet sans mise à jour du code IaC
- Utilisation de la console pour les ajouts urgents

**Solution** :
1. Documentation de l'état actuel
2. Plan de réconciliation progressive
3. Audit complet avant toute modification

**Prévention** :
- Pipeline CI/CD pour déploiement automatisé
- Policy "Infrastructure as Code only"
- Revue périodique drift Terraform

---

## 📌 Problèmes Connus Non Résolus

| ID | Description | Impact | Priorité | ETA |
|----|-------------|--------|----------|-----|
| BUG-001 | Drift TF vs GCP | Bloquer les terraform apply | Haute | Phase 2 |
| BUG-002 | Firewall permissives | Risque sécurité | Critique | Phase 3 |
| BUG-003 | VM GPU hors IaC | Non reproductible | Moyenne | Phase 2 |

---

## ✅ Problèmes Résolus

*Aucun problème résolu pour le moment - Projet en phase d'initialisation*
