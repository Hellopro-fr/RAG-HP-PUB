# 🔒 Rapport d'Audit Sécurité - Projet RAG HelloPro GCP

> **Date**: 2026-02-05  
> **Niveau de criticité global**: 🔴 ÉLEVÉ  
> **Classification**: CONFIDENTIEL  
> **Auditeur**: DevSecOps / Cloud SRE Architect

---

## 📊 Résumé Exécutif

| Domaine | Score | Vulnérabilités |
|---------|-------|----------------|
| **Firewall** | 🔴 35% | 10+ règles exposées 0.0.0.0/0 |
| **Exposition Réseau** | 🔴 40% | Redis public, ports critiques exposés |
| **IAM** | 🟡 60% | SA par défaut utilisé, à auditer |
| **Secrets** | 🟡 55% | À migrer vers Secret Manager |
| **GKE** | 🟡 65% | Workload Identity à activer |
| **Chiffrement** | 🟢 80% | Encryption at rest par défaut |

---

## 🔥 Vulnérabilités Critiques

### VULN-001: Firewall Rules Exposées sur 0.0.0.0/0

**Criticité**: 🔴 CRITIQUE  
**Impact**: Exposition directe sur Internet

| Règle | Réseau | Ports | Risque |
|-------|--------|-------|--------|
| allow-public-services | default | 80,443,15672,19530 | Management RabbitMQ, Milvus exposés |
| allow-public-services-hellopro-dev-vpc | hellopro-dev-vpc | 80,443,15672,19530,8321,7474,8585,7688 | Neo4j, services internes |
| default-allow-api-ports-8509 | default | 8509 | API ingestion |
| default-allow-rdp | default | 3389 | RDP Windows (inutilisé ?) |
| k8s-fw-a3a81e73236e843ddb15347e6ce6a59d | hellopro-dev-vpc | 6379 | **REDIS** |

**Recommandation Immédiate**:
```
# Restreindre redis à IPs autorisées uniquement
# Supprimer allow-rdp si Windows non utilisé
# Restreindre services management (15672, 19530)
```

### VULN-002: Redis Exposé sur Internet

**Criticité**: 🔴 CRITIQUE  
**IP**: 34.14.100.226:6379

```
Service: Redis
Port: 6379
Exposition: PUBLIQUE
Protection: Firewall 0.0.0.0/0
```

**Risques**:
- Accès non authentifié possible
- Data breach
- Injection de commandes

**Recommandation**:
1. Migrer vers Internal Load Balancer IMMÉDIATEMENT
2. Activer AUTH Redis
3. Restreindre firewall aux IPs sources

### VULN-003: RabbitMQ Management Exposé

**Criticité**: 🟡 ÉLEVÉ  
**Ports**: 15672 (Web UI), 5672 (AMQP)

```
Services: 2x RabbitMQ
Port Management: 15672 exposé 0.0.0.0/0
```

**Recommandation**:
- Restreindre 15672 à IPs ops uniquement
- Utiliser Ingress avec authentification

---

## 🔍 Analyse Détaillée par Domaine

### 1. Firewall Rules

#### ⚠️ Règles À Risque

| Règle | Analyse | Action |
|-------|---------|--------|
| allow-ssh (TF) | Source 0.0.0.0/0, ports 22,19530,80,15672 | 🔴 Modifier source → IAP |
| allow-intra-lan (TF) | Source 0.0.0.0/0 | 🔴 Modifier → RFC1918 |
| k8s-fw-*a3a81e* | Redis 6379 public | 🔴 Supprimer/migrer ILB |
| default-allow-rdp | RDP 3389 public | 🔴 Supprimer |

#### ✅ Règles Sécurisées (Bonnes pratiques détectées)

| Règle | Commentaire |
|-------|-------------|
| allow-ssh1 | IPs spécifiques uniquement ✅ |
| allow-restricted-services-hellopro | 2 IPs autorisées ✅ |
| block-aws-leak | Blocage egress AWS ✅ |
| deny-crypto-mining-egress | Anti-cryptomining ✅ |
| deny-udp-egress | Blocage UDP sortant ✅ |

### 2. Exposition Réseau

#### IPs Publiques Identifiées

| Ressource | IP Publique | Justification | Action |
|-----------|-------------|---------------|--------|
| manager-vm-dev | 34.77.187.108 | Bastion | ✅ OK via IAP |
| vm-embedding-g2-std-24-use | 35.245.31.1 | Services ML | ⚠️ Évaluer Cloud NAT |
| Redis LB | 34.14.100.226 | Base données | 🔴 Migrer ILB |
| Qdrant LB | 34.52.142.50 | Base vectorielle | 🔴 Migrer ILB |
| RabbitMQ LB | 34.78.143.55 | Message Queue | 🔴 Migrer ILB |

### 3. IAM & Service Accounts

| Service Account | Usage | Évaluation |
|-----------------|-------|------------|
| 806625052144-compute@developer... | Default Compute | ⚠️ Trop permissif |
| terraform@hellopro-rag-project... | IaC | ✅ Dédié |
| hp-sa-gcs-data-job@... | Backup GCS | ✅ Dédié |
| milvus-backup-wi@... | Workload Identity | ✅ Dédié |

**Recommandations IAM**:
1. Éviter SA Compute par défaut
2. Créer SA dédiés par service
3. Activer Workload Identity partout

### 4. Secrets Management

**État actuel**:
- Secrets probablement en .env ou ConfigMaps
- Secret Manager non détecté comme source

**Recommandations**:
1. Migrer vers GCP Secret Manager
2. Utiliser External Secrets Operator pour K8s
3. Rotation automatique des credentials

### 5. GKE Security

| Contrôle | État | Action |
|----------|------|--------|
| Cluster privé | À vérifier | Activer si non privé |
| Workload Identity | Inconnu | Activer |
| Pod Security Standards | Inconnu | Configurer |
| Network Policies | Inconnu | Implémenter |
| Binary Authorization | Non actif | Évaluer |

---

## 📋 Plan de Remédiation

### Semaine 1 (URGENT) 🔴

| # | Action | Responsable | Validation |
|---|--------|-------------|------------|
| SEC-1 | Migrer Redis vers Internal LB | Infra | Test connectivité |
| SEC-2 | Supprimer default-allow-rdp | Infra | N/A |
| SEC-3 | Restreindre firewall allow-ssh | Infra | Test SSH via IAP |

### Semaine 2 (HIGH) 🟡

| # | Action | Responsable | Validation |
|---|--------|-------------|------------|
| SEC-4 | Migrer Qdrant/RabbitMQ vers ILB | Infra | Test services |
| SEC-5 | Corriger allow-intra-lan → RFC1918 | Infra | Test réseau |
| SEC-6 | Activer Workload Identity GKE | Infra | Test pods |

### Semaine 3-4 (MEDIUM) 🟢

| # | Action | Responsable | Validation |
|---|--------|-------------|------------|
| SEC-7 | Migrer secrets vers Secret Manager | DevOps | Test déploiement |
| SEC-8 | Configurer Cloud NAT | Infra | Test egress |
| SEC-9 | Implémenter Network Policies K8s | DevOps | Test isolation |

---

## 📊 Métriques de Sécurité

| Métrique | Actuel | Cible |
|----------|--------|-------|
| Règles FW 0.0.0.0/0 | ~10 | 0 |
| Services publics critiques | 3 | 0 |
| SA par défaut utilisés | 1 | 0 |
| Secrets en Secret Manager | ? | 100% |
| Workload Identity | Non | Oui |

---

---

## 🔄 Mise à Jour Audit - 2026-03-17

### Nouvelles Vulnérabilités Identifiées

#### VULN-004: Duplication Terraform avec Faille Sécurité

**Criticité**: 🟡 ÉLEVÉ
**Fichier**: `infra-ci-cd/terraform/variables.tf` ligne 44

```hcl
variable "ssh_allowed_ips" {
  default = ["0.0.0.0/0"]  # ⚠️ TODO: Restreindre en production
}
```

**Analyse** : Le dossier `infra-ci-cd/terraform/` contient une racine Terraform séparée qui :
- Crée un VPC dupliqué `rag-hp-vpc` (vs `hellopro-dev-vpc` en production)
- Définit des règles firewall SSH ouvertes à `0.0.0.0/0` par défaut
- N'a jamais été appliqué (heureusement)
- Duplique partiellement les ressources de `infra-microservices/`

**Risque** : Si appliqué en l'état, ouvrirait SSH au monde entier sur un VPC séparé.

**Décision** : Fusionner les ressources utiles (Secret Manager, Monitoring, Service Accounts, Budget) dans `infra-microservices/` et supprimer les ressources dupliquées (VPC, subnet, firewall) de `infra-ci-cd/terraform/`.

#### VULN-005: Credentials par Défaut en Production

**Criticité**: 🔴 CRITIQUE
**Fichiers**: `apps-microservices/api-gateway/app/core/settings.py`

| Credential | Valeur par défaut | Risque |
|------------|-------------------|--------|
| JWT_SECRET | "changeme-jwt-secret" | Bypass authentification |
| GATEWAY_ADMIN_KEY | "changeme-admin-key" | Accès admin non autorisé |
| MySQL credentials | gateway_user / gateway_pass | Accès base de données |

**Recommandation** : Rotation immédiate + migration vers Secret Manager.

#### VULN-006: gRPC sans TLS

**Criticité**: 🟡 ÉLEVÉ
**Fichiers**: Tous les `*_client.py` dans `libs/common-utils/grpc_clients/`

Tous les clients gRPC utilisent `grpc.insecure_channel()` sans TLS/SSL.
Impact : Vulnérabilité Man-in-the-Middle sur la communication inter-services.

#### VULN-007: CORS Permissif

**Criticité**: 🟡 MOYEN
**Fichiers**: Multiples services FastAPI (`api-ingestion`, `api-embedding-service`, etc.)

`allow_origins=["*"]` permet des requêtes cross-origin depuis n'importe quel domaine.

#### VULN-008: Healthchecks Absents (71/76 services)

**Criticité**: 🟡 MOYEN
Seulement 5 services sur 76 disposent d'un endpoint `/health`.
Impact : Impossibilité de détecter automatiquement les pannes de service.

### État des Remédiations

| # | Action | Statut | Date | Validation |
|---|--------|--------|------|------------|
| SEC-1 | Migrer Redis vers Internal LB | ✅ Deja en ILB | 2026-03-18 | ILB `10.0.1.220`, namespace `default` |
| SEC-2 | Supprimer default-allow-rdp | ✅ Supprimee | 2026-03-18 | `gcloud firewall-rules list` = 0 items |
| SEC-3 | Restreindre firewall allow-ssh | ✅ Corrigé dans TF | 2026-02-06 | IAP 35.235.240.0/20 |
| SEC-4 | Migrer Qdrant/RabbitMQ vers ILB | ✅ RabbitMQ OK / ⬜ Qdrant DEV a verifier | 2026-03-18 | RabbitMQ v3 sur `10.0.1.216`, port 34.78.143.55 ferme |
| SEC-5 | Corriger allow-intra-lan → RFC1918 | ✅ Corrigé dans TF | 2026-02-06 | Ranges RFC1918 |
| SEC-6 | Activer Workload Identity GKE | ⬜ Planifié Phase 3 | - | - |
| SEC-7 | Migrer secrets vers Secret Manager | ⬜ Planifié Phase 3 | - | - |
| SEC-8 | Configurer Cloud NAT | ⬜ Planifié Phase 3 | - | - |
| SEC-9 | Implémenter Network Policies K8s | ⬜ Planifié Phase 3 | - | - |
| SEC-10 | Rotation credentials par défaut | ✅ Effectuee | 2026-03-18 | JWT_SECRET renforce (hex 64 chars), GATEWAY_ADMIN_KEY deja forte |
| SEC-11 | Fusion racine TF infra-ci-cd | ⬜ Planifié Phase 3 | - | - |

### Corrections Audit - Ecarts Constates (2026-03-18)

L'execution terrain a revele des ecarts significatifs entre l'audit initial et la realite :

| Element | Audit initial | Realite constatee |
|---------|--------------|-------------------|
| Regle `default-allow-rdp` | Source `0.0.0.0/0`, active | **Desactivee** + restreinte a 3 IPs bureau |
| JWT_SECRET | `changeme-jwt-secret` | Deja change en `SecretPassJWT2626` (faible mais pas defaut) |
| GATEWAY_ADMIN_KEY | `changeme-admin-key` | Deja une cle forte 64+ chars |
| RabbitMQ instances | 3 (V2, prod, v3) | **1 seule** instance `rabbitmq-v3` |
| RabbitMQ acces | IP publique `34.78.143.55` | **ILB interne** `10.0.1.216`, port public ferme |
| Redis acces | IP publique `34.14.100.226` | **ILB interne** `10.0.1.220`, namespace `default` |
| Redis namespace | `cache` (dans manifests) | `default` (en realite) |

> **Conclusion** : L'equipe avait deja initie des remediations non documentees. Le niveau de risque reel est significativement plus bas que l'evaluation initiale.

### Métriques Mises à Jour

| Métrique | Initial (02/05) | Audit code (03/17) | Reel terrain (03/18) | Cible |
|----------|-----------------|--------------------|--------------------|-------|
| Règles FW 0.0.0.0/0 | ~10 | ~8 | ~7 (RDP supprimee) | 0 |
| Services publics critiques | 3 | 3 | **0-1** (Redis+RabbitMQ deja ILB, Qdrant a verifier) | 0 |
| SA par défaut utilisés | 1 | 1 | 1 | 0 |
| Secrets en Secret Manager | 0% | 0% | 0% | 100% |
| Workload Identity | Non | Non | Non | Oui |
| Credentials par defaut | 3 | 3 | **0** (tous rotates/renforces) | 0 |
| Services avec healthcheck | 5/76 (6.5%) | 5/76 (6.5%) | 5/76 (6.5%) | 76/76 (100%) |

---

## ⚠️ Avertissement

> [!CAUTION]
> **Ne pas appliquer les changements firewall sans test préalable**.
> Risque de coupure des services en production.
> **Ne pas exécuter `terraform apply` sur `infra-ci-cd/terraform/`** - créerait un VPC dupliqué.

> [!IMPORTANT]
> Verifier l'exposition Qdrant DEV (port 6333 sur 34.52.142.50) - potentiellement le dernier service expose.
> Runbook de remédiation disponible : `docs/runbooks/security_remediation.md`
