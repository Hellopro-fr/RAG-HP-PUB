# Suivi de la bascule par lots — état chaîne par chaîne

> **Le tableau qui dit qui est où.** Pendant la coexistence VM / GKE, c'est la seule source de vérité sur l'état de chaque service.
> Tenu par le DevSecOps, **mis à jour à chaque geste**, pas en fin de journée. Un service = une ligne.
> ⚠️ L1…L7 = lots d'exécution (priorités P1-P3 de l'inventaire uniquement).

## Légende

| Colonne | Valeurs |
|---|---|
| Jumeau VM | `UP` (sert la prod) · `STOPPED` (arrêté mais présent — c'est le filet de rollback) · `N/A` (L7 : reste up par conception) |
| GKE | `shadow` (broker dev, sans trafic) · `PROD` (données de production) · `0` (scalé à zéro après un rollback) |
| Validé | initiales + date. Deux validations : DSO (technique) et LEAD/dev (fonctionnel) |

## État des lots

| Lot | Date proposée | Statut | Bascule | Obs. 24 h | Décision J+1 |
|:--:|---|---|---|---|---|
| **L1** | **sam 19/09** (anticipé) | ✅ **basculé** — L1-a 06:44 UTC · L1-b 10:29 UTC | L1-a 3 min (rollback réel 62 s, rebascule 1'50) · L1-b **2 min 05** | 🟡 en cours → lun 21 | **lun 21/09 9h30** (1er message réel + décision L2) |
| **L2** | **lun 21/09 14h Paris** (avancé) | 🟡 **prêt** (emptyDir ✅, re-scan ✅ VEX-01, gel ✅, réponses pré-contrôle LEAD ✅) | | | **mar 22/09 9h30** |
| **L3** | mer 23/09 | ⬜ à venir | | | |
| **L4** | jeu 24/09 | ⬜ à venir | | | |
| **L5** | lun 28/09 | ⬜ à venir | | | |
| **L6** | mar 29/09 | ⬜ à venir | | | |
| **L7** | mer 30/09 | ⬜ à venir | | | |

## État des services

| Lot | Service VM | Déploiement GKE | Jumeau VM | GKE | Réplicas | Date bascule | Validé DSO | Validé LEAD/dev | Obs. 24 h | Notes |
|:--:|---|---|:--:|:--:|:--:|---|---|---|:--:|---|
| L1 | `deepseek-metrics-collector-service` | `deepseek-metrics-collector-service` | **STOPPED** | **PROD** | 1 | 2026-09-19 09:52 | DSO 19/09 | ⬜ 1er msg réel lun | ⬜ | rollback réel joué (62 s) ; SIGTERM ignoré (Exited 137) ; [rapport](rapports/deepseek-metrics-collector-service.md) |
| L1 | `nettoyage-bruit-ocr-service` | `nettoyage-bruit-ocr-service` | **STOPPED** ×5 | **PROD** | **3** | 2026-09-19 10:29 UTC | DSO 19/09 | ⬜ 1er msg réel lun | ⬜ | plage tarifaire 06-10h/01-04h UTC = `consumers=0` nominal ; code bind-mount sur VM (ne pas `git pull` la VM pendant 7 j) ; [rapport](rapports/nettoyage-bruit-ocr-service.md) |
| L2 | `qc-caracterisation` | `qc-caracterisation` | UP | shadow | 1 | | | | ⬜ | |
| L2 | `qc-enrichissement` | `qc-enrichissement` | UP | shadow | 1 | | | | ⬜ | |
| L2 | `qc-equivalence` | `qc-equivalence` | UP | shadow | 1 | | | | ⬜ | |
| L2 | `qc-generation-caracteristiques` | `qc-generation-caracteristiques` | UP | shadow | 1 | | | | ⬜ | |
| L2 | `qc-generation-question1` | `qc-generation-question1` | UP | shadow | 1 | | | | ⬜ | |
| L2 | `qc-generation-question2an` | `qc-generation-question2an` | UP | shadow | 1 | | | | ⬜ | |
| L2 | `qc-generation-valeurs` | `qc-generation-valeurs` | UP | shadow | 1 | | | | ⬜ | |
| L3 | `prix-extraction-produits` | `prix-extraction-produits` | UP | shadow | 1 | | | | ⬜ | |
| L3 | `prix-extraction-message` | `prix-extraction-message` | UP | shadow | 1 | | | | ⬜ | |
| L3 | `prix-extraction-devis` | `prix-extraction-devis` | UP | shadow | 1 | | | | ⬜ | |
| L3 | `prix-caracterisation` | `prix-caracterisation` | UP | shadow | 1 | | | | ⬜ | |
| L3 | `prix-milvus-processor-service` | `prix-milvus-processor` | UP | shadow | 1 | | | | ⬜ | |
| L4 | `website-processor-service` | `website-processor-service` | UP | shadow | 1 | | | | ⬜ | |
| L4 | `product-processor-service` | `product-processor-service` | UP | shadow | 1 | | | | ⬜ | |
| L4 | `echange-processor-service` | `echange-processor-service` | UP | shadow | 1 | | | | ⬜ | |
| L4 | `devis-processor-service` | `devis-processor-service` | UP | shadow | 1 | | | | ⬜ | |
| L4 | `website-database-qdrant-service` | `website-database-qdrant-service` | UP | shadow | 1 | | | | ⬜ | |
| L4 | `product-database-qdrant-service` | `product-database-qdrant-service` | UP | shadow | 1 | | | | ⬜ | |
| L4 | `echange-database-qdrant-service` | `echange-database-qdrant-service` | UP | shadow | 1 | | | | ⬜ | |
| L4 | `document-database-qdrant-service` | `document-database-qdrant-service` | UP | shadow | 1 | | | | ⬜ | |
| L4 | `di-database-qdrant-service` | `di-database-qdrant-service` | UP | shadow | 1 | | | | ⬜ | |
| L5 | `graph-rag-produit-processor` | `graph-rag-produit-processor` | UP | shadow | 1 | | | | ⬜ | |
| L5 | `graph-rag-etl-processor` | `graph-rag-etl-processor` | UP | shadow | 1 | | | | ⬜ | |
| L5 | `graph-rag-fournisseur-processor` | `graph-rag-fournisseur-processor` | UP | shadow | 1 | | | | ⬜ | |
| L5 | `graph-rag-categorie-processor` | `graph-rag-categorie-processor` | UP | shadow | 1 | | | | ⬜ | |
| L5 | `graph-rag-llm-extractor-processor` | `graph-rag-llm-extractor-processor` | UP | shadow | 1 | | | | ⬜ | |
| L5 | `graph-rag-normalize-unite-processor` | `graph-rag-normalize-unite-processor` | UP | shadow | 1 | | | | ⬜ | |
| L5 | `graph-rag-normalize-unite-retry-processor` | `graph-rag-normalize-unite-retry-processor` | UP | shadow | 1 | | | | ⬜ | |
| L5 | `graph-rag-semantique-vigil-processor` | `graph-rag-semantique-vigil-processor` | UP | shadow | 1 | | | | ⬜ | |
| L6 | `embedding-service` | `embedding-service` | UP | shadow | 1 | | | | ⬜ | |
| L6 | `template-llm-service` | `template-llm-service` | UP | shadow | 1 | | | | ⬜ | |
| L6 | `webhook-service` | `webhook-service` | UP | shadow | 1 | | | | ⬜ | |
| L7 | `api-gateway-go-service` | `api-gateway-go` | N/A | shadow | 1 | | | | ⬜ | |
| L7 | `mcp-gateway-service` | `mcp-gateway-service` | N/A | shadow | 1 | | | | ⬜ | |
| L7 | `mcp-zoho-service` | `mcp-zoho-service` | N/A | shadow | 1 | | | | ⬜ | |
| L7 | `mcp-google-templates-runner` | `mcp-google-templates-runner` | N/A | shadow | 1 | | | | ⬜ | |
| L7 | `graph-rag-api-admin-service` | `graph-rag-api-admin-service` | N/A | shadow | 1 | | | | ⬜ | |
| L7 | `graph-rag-dlq-manager-service` | `graph-rag-dlq-manager` | N/A | shadow | 1 | | | | ⬜ | |
| L7 | `dlq-manager-service` | `dlq-manager-service` | UP | shadow | 1 | | | | ⬜ | |

## Rollbacks

| Date | Lot | Service(s) | Cause | Durée | Analyse | Reprise |
|---|---|---|---|---|---|---|
| | | | | | | |

## Règle d'arrêt de la série

- **1 rollback** → pause d'un jour ouvré, analyse de cause écrite, correction de la procédure, puis reprise.
- **2 rollbacks** (même lot ou lots différents) → **série suspendue**, comité CTO / LEAD / DSO avant toute reprise.
- Un lot ne démarre jamais un **vendredi** ni la veille d'un jour férié : l'observation de 24 h doit tomber un jour ouvré.
