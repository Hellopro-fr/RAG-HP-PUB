# Livrer une fonctionnalité sur un service migré

> **Pour qui** : toutes les équipes qui développent sur `RAG-HP-PUB`.
> **Depuis quand** : 14/10/2026. Ce guide remplace l'habitude « je pousse sur `features/poc`, c'est en production ».
> **Contact** : l'équipe DevSecOps.

## La règle en une phrase

**Un service migré se livre par une PR vers `prod`. Le merge déploie tout seul.** Un service resté sur la VM se livre comme avant, par `features/poc`.

Pousser sur `features/poc` le code d'un service migré **ne le met plus en production** : la VM ne le sert plus.

## Comment livrer sur un service migré

1. Créez votre branche **depuis `prod`** (pas depuis `features/poc`) : `git fetch origin && git switch -c feat/<sujet> origin/prod`.
2. Faites vos changements dans le dossier du service (`apps-microservices/<service>/`).
3. Ouvrez une PR **de votre branche vers `prod`**. Les contrôles (gate) doivent être verts.
4. Après revue, **mergez**. Le CD du service se déclenche seul :
   - **Cloud Run** : construction de l'image, déploiement d'une nouvelle révision, test de santé, retour arrière automatique s'il échoue ;
   - **GKE** : construction de l'image, `kubectl set image`, attente du rollout, retour arrière automatique (`rollout undo`) s'il échoue.
5. Suivez le déploiement dans l'onglet *Actions* de GitHub : le job du service affiche son statut et un résumé en bas de page. **En cas d'échec, GitHub envoie un email à la personne qui a mergé la PR** (réglage par défaut de chaque compte : *Settings → Notifications → Actions*, « Only notify for failed workflows »). Des alertes dans Teams viendront plus tard.

Le déploiement ne se déclenche que si votre PR touche le dossier du service (ou son fichier `.github/workflows/deploy-…yml`). Une modification d'une bibliothèque partagée (`libs/`) ne redéploie pas les services : prévenez-nous, on lance les déploiements concernés (bouton *Run workflow* du CD).

## Services migrés : livraison par PR vers `prod`

### Cloud Run (API HTTP et serveurs MCP)

| Service | Dossier | CD |
|---|---|---|
| api-comparaison-texte | `apps-microservices/api-comparaison-texte` | `deploy-api-comparaison-texte.yml` |
| optimize-service | `apps-microservices/optimize-service` | `deploy-optimize-service.yml` |
| api-detection-langue-fr | `apps-microservices/api-detection-langue-fr` | `deploy-api-detection-langue-fr.yml` |
| content-extractor-api-service | `apps-microservices/content-extractor-api-service` | `deploy-content-extractor-api-service.yml` |
| api-chat-llm | `apps-microservices/api-chat-llm` | `deploy-api-chat-llm.yml` |
| api-embedding-service | `apps-microservices/api-embedding-service` | `deploy-api-embedding-service.yml` |
| graph-rag-api-recherche-service | `apps-microservices/graph-rag-api-recherche-service` | `deploy-graph-rag-api-recherche-service.yml` |
| graph-rag-api-recherche-optim-service | `apps-microservices/graph-rag-api-recherche-optim-service` | `deploy-graph-rag-api-recherche-optim-service.yml` |
| graph-rag-api-recherche-rust-service | `apps-microservices/graph-rag-api-recherche-rust-service` | `deploy-graph-rag-api-recherche-rust-service.yml` |
| prix-traitement | `apps-microservices/prix-traitement` | `deploy-prix-traitement.yml` |
| mcp-leexi-service | `apps-microservices/mcp-leexi-service` | `deploy-mcp-leexi-service.yml` |
| mcp-ringover-service | `apps-microservices/mcp-ringover-service` | `deploy-mcp-ringover-service.yml` |
| mcp-semrush-service | `apps-microservices/mcp-semrush-service` | `deploy-mcp-semrush-service.yml` |
| mcp-google-analytics-service | `apps-microservices/mcp-google-analytics-service` | `deploy-mcp-google-analytics-service.yml` |
| mcp-google-search-console-service | `apps-microservices/mcp-google-search-console-service` | `deploy-mcp-google-search-console-service.yml` |
| mcp-api-recherche-service (« RAG Hellopro ») | `apps-microservices/mcp-api-recherche-service` | `deploy-mcp-api-recherche-service.yml` |
| api-question-caracteristique | `apps-microservices/api-question-caracteristique` | `deploy-api-question-caracteristique.yml` (pas de copie sur la VM) |

### GKE (consumers RabbitMQ)

| Famille | Services | CD |
|---|---|---|
| QC | qc-caracterisation, qc-enrichissement, qc-equivalence, qc-generation-caracteristiques, qc-generation-question1, qc-generation-question2an, qc-generation-valeurs (dossiers `apps-microservices/QC-…`) | `deploy-gke-qc-<nom>.yml` |
| Prix | prix-caracterisation, prix-extraction-devis, prix-extraction-message, prix-extraction-produits, prix-milvus-processor | `deploy-gke-prix-<nom>.yml` |
| Bases vectorielles | di-, document-, echange-, product-, website-database-qdrant-service (ils écrivent dans **Milvus**, le nom « qdrant » est historique) | `deploy-gke-<nom>.yml` |
| GraphRAG | graph-rag-categorie-processor, graph-rag-etl-processor, graph-rag-fournisseur-processor, graph-rag-llm-extractor-processor, graph-rag-normalize-unite-processor, graph-rag-normalize-unite-retry-processor, graph-rag-produit-processor, graph-rag-semantique-vigil-processor | `deploy-gke-graph-rag-<nom>.yml` |
| Autres | deepseek-metrics-collector-service, devis-processor-service, echange-processor-service, embedding-service, nettoyage-bruit-ocr-service, template-llm-service, webhook-service, website-processor-service, product-processor-service | `deploy-gke-<nom>.yml` |

## Services restés sur la VM : livraison par `features/poc`, comme avant

Ces services tournent toujours sur la VM. Continuez à livrer par `features/poc`. Ils passeront en livraison par `prod` le jour de leur migration ; on vous préviendra service par service.

| Service | Pourquoi il reste sur la VM |
|---|---|
| api-classification, api-ingestion, api-rest-milvus, api-recherche, mcp-classification-produit-service | lot reporté (correctifs en cours côté DevSecOps ; api-recherche revenue sur la VM le 15/10) |
| agent-service, mcp-hellodata-service | en stabilisation |
| mcp-google-analytics-minisite-service | migré avec la reprise du projet mini-sites |
| mcp-gateway-service et mcp-gateway-frontend, mcp-zoho-service, mcp-google-templates-runner | pile de la gateway MCP |
| dlq-manager-service, graph-rag-dlq-manager, graph-rag-api-admin-service | gestionnaires DLQ et admin GraphRAG |
| api-html-recherche, image-comparison-service | encore servis par la VM (appels directs et `reverse-proxy`) ; leur Cloud Run est une copie de test |
| crawler-service, crawler-monitor (backend et frontend), embedding-model-service et les serveurs GPU, nextjs-conseils-hp, unit-registry, normalize-unite, mcp-template-neo4j, image-download-service | services VM / GPU, ou nouveaux services |

Attention : **graph-rag-api-admin-service**, **graph-rag-dlq-manager**, **api-html-recherche** et **image-comparison-service** ont un CD vers `prod`, mais il ne met à jour qu'une copie de test (GKE ou Cloud Run). **Leur production reste sur la VM** : livrez-les par `features/poc`.

## En cas de problème

- Le CD a échoué ou a fait un retour arrière : l'email de GitHub et le résumé du job dans *Actions* disent à quelle étape. Rien n'est cassé en production, l'ancienne version tourne toujours.
- Vous ne savez pas si un service est migré : regardez les deux tableaux ci-dessus, ou demandez à l'équipe DevSecOps.
- Vous avez poussé sur `features/poc` le code d'un service migré : rien n'est perdu, ouvrez simplement la même modification en PR vers `prod`.
