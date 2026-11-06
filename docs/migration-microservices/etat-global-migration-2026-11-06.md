# État global de la migration VM GPU → Cloud Run / GKE — 6 novembre 2026

> Pour qui : le CTO, le LEAD et les devs qui livrent sur les services migrés.
> Pourquoi maintenant : la migration marque une **pause** à partir du 6/11. La VM a assez de place pour les nouveaux projets (dev sur la VM ; prod à l'étude sur GKE ou Cloud Run). Ce document fixe ce qui est acquis, ce qui reste ouvert, et ce qui doit rester vrai pendant la pause.
> Sources : [`suivi-vague-2.md`](suivi-vague-2.md) (journal), [`reports-et-decisions-vague-2.md`](reports-et-decisions-vague-2.md) (registre), [`demandes-devs-vague-2.md`](demandes-devs-vague-2.md), [`inventaire-services-migration-par-lot.md`](inventaire-services-migration-par-lot.md), [guide de livraison](../runbooks/guide-livraison-services-migres.md). Contrôles du 6/11 en § 5.

## 1. En bref

| Chiffre | Valeur |
|---|---|
| Services en production **hors de la VM** | **51** : 34 consumers RabbitMQ sur GKE, 17 services HTTP et MCP sur Cloud Run |
| Part de l'inventaire (117 services) | ≈ 44 % |
| Part du périmètre migrable (89 services de l'inventaire, hors les 28 qui restent sur la VM par conception) | **50 / 89 ≈ 56 %** (+ `api-question-caracteristique`, créé directement sur Cloud Run, hors inventaire). **Les 39 restants ne sont pas tous migrables sans préalable : 4 le sont, voir § 7** |
| Services revenus sur la VM après un essai | 5 : `api-recherche`, `api-classification`, `api-rest-milvus`, `api-ingestion`, `mcp-classification-produit` (lot V2-a3-bis) |
| Jumeaux VM arrêtés ou en réserve | 34 consumers (vague 1), 6 serveurs MCP (V2-b) ; les jumeaux HTTP de V2-a restent allumés comme repli, sans trafic |
| CD | **51 / 51** services migrés ont leur pipeline sur `prod` (contrôle du 6/11, § 5.1) |
| Décision du 6/11 | **pause de la migration** ; la VM continue de servir le reste ; règles de livraison et garde-fous inchangés |

## 2. Fait

### 2.1 Vague 1 — consumers RabbitMQ → GKE (septembre)

Lots L1 à L6, 34 consumers basculés (QC ×7, prix ×5, bases vectorielles ×5, GraphRAG ×8, autres ×9), jumeaux VM arrêtés, GO validés à J+1 sur relevés. Méthode : [`procedure-bascule-lot-consumers.md`](procedure-bascule-lot-consumers.md).

### 2.2 Vague 2 — services HTTP et MCP → Cloud Run (octobre)

| Lot | Services | Résultat |
|---|---|---|
| V2-0 | prérequis | entrée interne Cloud Run validée sans jeton DNS ; rapatriement `poc` → `prod` des correctifs urgents ; **0 Cloud Run anonyme** (F-HP-SEC-030) ; 6 vhosts d'administration de la VM fermés ou durcis (F-HP-SEC-028, 029) |
| V2-a1 | comparaison-texte, optimize, detection-langue, content-extractor | ✅ 4 routes sur Cloud Run (5-6/10) |
| V2-a2 | chat-llm, embedding HTTP, graph-rag recherche ×3 | ✅ 5 routes (7/10, GO 8/10) |
| V2-a3 | prix-traitement | ✅ (8/10, GO 9/10) ; recherche, classification, rest-milvus, ingestion → revenus sur la VM (V2-a3-bis) |
| V2-b | leexi, ringover, Google Analytics, Search Console, RAG Hellopro, semrush | ✅ 6 serveurs MCP (13-14/10), jumeaux en réserve, mcp-gateway repointée |
| — | api-question-caracteristique | ✅ nouveau service, Cloud Run seulement (pas de copie VM) |

### 2.3 Livraison et exploitation

- **CD** : Cloud Run (wrappers `deploy-<service>.yml` → `deploy-cloud-run.yml`) et GKE (`deploy-gke-<service>.yml` → `deploy-gke-service.yml`, `set image`, rollout, `undo`) sur `push` vers `prod`, avec Slack.
- **Gate** `pr-gate-prod.yml` sur toute PR vers `prod` (Trivy repo-wide, tests).
- **Guide équipes** : [`guide-livraison-services-migres.md`](../runbooks/guide-livraison-services-migres.md) — service migré = PR vers `prod`, service VM = `features/poc`.
- **Garde-fou** `guard-migrated-services-poc.yml` sur `features/poc` : avertissement sur les 51 dossiers migrés.
- **Scripts** : `RAG-HP-PUB-infra/infra-microservices/scripts/migration/vague2/` (bascule de route, relevés, parité, diagnostics, mesures nginx `timing` et GPU).

### 2.4 Diagnostic de la recherche (V2-a3-bis), terminé

La recherche a été remise sur la VM le 15/10 (nuit à 56 % d'erreurs sur Cloud Run). La cause est établie et mesurée (16-21/10) : chaque nuit, de 20h à 01h UTC, le back-office envoie **119 à 300 lots de classification** (fichiers produits, 120 à 700 Ko, 6 à 31 min chacun) qui passent aussi par `/search-service/search`. Ils saturent le reranking et l'embedding, servis par **Triton sur le seul GPU 1** ; le reranking **n'a pas de file de priorité** et attend 430 à 547 s par inférence ; le client abandonne à 60 s. Détail : [note de décision](rapports/decision-retour-vm-api-recherche-2026-10-15.md). **Le même phénomène existe sur la VM** : Cloud Run n'en était que le révélateur.

## 3. En cours ou suspendu

| Sujet | État au 6/11 | Ce qui bloque |
|---|---|---|
| **V2-a3-bis** (recherche, classification, rest-milvus, ingestion, MCP classification-produit) | ⏸ **suspendu**. Devs consultés (D-01 à D-06) : constats partagés, **aucune possibilité d'ajuster pour l'instant** (taille des lots non réductible, GPU 0 réservé à vLLM et aux lancements manuels de DeepSeek OCR, pas de priorité ni de `max_length` dans le reranking à court terme) | un correctif côté reranking ou côté lots ; sans lui, toute rebascule de la recherche reproduira les nuits à 56 % d'erreurs |
| **V2-c** (gateway, mcp-gateway, zoho, templates-runner, DLQ GraphRAG, admin GraphRAG, image-comparison) | ⏸ **option B** (15/10) : aucune bascule ; MySQL de la VM constaté, aucun gain pour les autres | migration des bases MySQL (`gateway_db`), ou décision de les garder sur la VM |
| **V2-a4** (agent-service, mcp-hellodata, mcp-normalize-unite) | ⏸ préparé (PR #871, #872), différé : services en stabilisation | stabilité du code sur `features/poc` |
| **V2-d** (SSO et fronts : login, rag, conseils, cmf, crawler-monitor) | ⬜ non commencé | dépend de V2-c (account-service, `gateway_db`) |
| **V2-e** (stockage images et crawler) | ⬜ chantier, pas une bascule | — |
| **Plan de capacité GPU** (F-HP-FINOPS-003) | GPU 0 réservé au retour de vLLM et aux lancements manuels d'OCR ; GPU 1 saturé la nuit par Triton | arbitrage chef de projet IA |
| **Sécurité post-migration** (registre § 4) | F-HP-SEC-032 (ACL du tailnet, cibles écrites) en tête ; F-HP-SEC-035 (politique par route, gateway fermée par défaut, règle de pare-feu 80/443 ouverte au monde) ; 031, 033, 034, 036, 037 | à traiter dans un ticket DevSecOps dédié, hors migration |

## 4. Reste à faire pour finir la migration

Par ordre de valeur, si la migration reprend :
1. **Correctif du reranking** (priorité, `max_length`) ou des lots de nuit, puis une nuit propre sur la VM, puis **V2-a3-bis** : recherche, classification, rest-milvus, ingestion, MCP classification-produit.
2. **V2-a4** quand agent-service et hellodata sont stables.
3. **Bases MySQL de la VM** (`gateway_db`, `db_hellopro` lu par plusieurs services) : décision d'architecture avant V2-c et V2-d.
4. **V2-c** puis **V2-d**, avec l'entrée publique `api.` / `mcp.` / `login.` / `rag.` (vhosts nginx, puis DNS Gandi en une intervention du titulaire).
5. **V2-e** stockage, puis extinction progressive des jumeaux HTTP restés en repli sur la VM.
6. **Nettoyage** : Cloud Run de test inutiles, shadows GKE à 0 réplica, wrappers CD des copies de test.

Restent sur la VM par conception (P10, 28 services) : serveurs GPU (Triton, embedding, reranking, LLM), MySQL, Elasticsearch, Neo4j local, Redis local, crawler, services temporaires.

## 5. Contrôles du 6 novembre (lecture seule, sur `origin/prod` du 5/11 et `origin/features/poc` du 4/11)

### 5.1 Chaque service migré a-t-il son pipeline ?

**Oui, 51 / 51.** Chaque dossier migré a un wrapper sur `prod` déclenché par `push` sur `prod` (chemins du service et du wrapper) et par `workflow_dispatch`, qui appelle le workflow réutilisable (`deploy-cloud-run.yml` ou `deploy-gke-service.yml`) avec le secret Slack. Le garde-fou `poc` couvre les mêmes 51 dossiers.

À savoir :
- `deploy-content-extractor-api-service.yml` écoute aussi `libs/common-utils/**` (dépendance directe) ; les autres wrappers ne redéploient pas sur une modification de `libs/` — c'est documenté dans le guide (lancer le déploiement à la main).
- `deploy-mcp-google-analytics-minisite-service.yml` écoute le dossier `mcp-google-analytics-service` (même code, autres identifiants) : le service minisite reste sur la VM, ce wrapper ne met à jour qu'une copie de test.
- **18 wrappers déploient une copie de test** d'un service dont la production reste sur la VM : Cloud Run `agent-service`, `api-classification`, `api-html-recherche`, `api-ingestion`, `api-recherche`, `api-rest-milvus`, `crawler-monitor-backend`, `image-comparison-service`, `mcp-classification-produit-service`, `mcp-google-analytics-minisite-service`, `mcp-hellodata-service`, `nextjs-conseils-hp` ; GKE `graph-rag-api-admin-service`, `graph-rag-dlq-manager`, `mcp-gateway-service`. Sans danger pour la production, mais une livraison sur ces dossiers par `prod` **ne touche pas la VM** : ils se livrent par `features/poc` (guide, tableau 2). `opti-moteur-front` (GKE, ticket 007, #907) a son CD nominal avec approbation de production.
- 3 wrappers GKE écartés le 14/10 (dlq-manager, templates-runner, zoho) ne sont pas versionnés : rien à faire.

### 5.2 Y a-t-il de nouveaux services sur `features/poc` ou `prod` ?

**Aucun service inconnu.**
- Dossiers `apps-microservices/` : 101 sur `prod`, 104 sur `features/poc` ; les 3 seulement sur `poc` sont connus et restent sur la VM par décision du 7/10 (`mcp-normalize-unite-service` → V2-a4, `mcp-template-neo4j-service`, `unit-registry-service`). Aucun dossier ajouté depuis le 10/10 sur l'une ou l'autre branche.
- Services du `docker-compose.yml` racine : 134 sur `prod`, 142 sur `poc`. Seulement sur `poc` : `neo4j_new`, `tailscale`, les 3 dossiers ci-dessus et leurs volumes (connus). Ajouté depuis le 10/10 sur les deux branches : **`databasus`** (interface de sauvegarde MySQL, ticket 006, #905) — un service de la VM, hors migration.
- Code `poc` à rapatrier avant toute bascule : à vérifier au moment de la reprise avec `drift_lot.sh` (règle inchangée).

### 5.3 Ce qui doit rester vrai pendant la pause

- Un service migré se livre **par PR vers `prod`** ; pousser son code sur `features/poc` ne le met plus en production (le garde-fou prévient).
- Le CD ne redéploie pas sur une modification de `libs/` : prévenir l'équipe DevSecOps, qui lance les déploiements concernés.
- Les routes de la gateway VM (`.env.url`) et les lignes `mcp_servers` pointent vers Cloud Run pour les 17 services migrés : ne pas les modifier à la main.
- Les jumeaux HTTP de V2-a restent allumés sans trafic : ne pas les supprimer sans relire le registre (repli).
- Le journal nginx `timing` et le bloc `allow-hp` sur `api.hellopro.eu` restent en place (mesure et sécurité).
- Tout nouveau service est déclaré dans l'[inventaire](inventaire-services-migration-par-lot.md) avec sa cible (VM, Cloud Run, GKE) ; un modèle de pipeline est fourni pour chaque cible (§ 6).

## 6. Suites demandées le 6/11

| # | Tâche | État |
|---|---|---|
| 1 | S'assurer que tous les services migrés ont leur pipeline CI/CD | ✅ contrôlé (§ 5.1) ; à refaire à chaque migration ou retour |
| 2 | Vérifier `features/poc` et `prod` pour de nouveaux services | ✅ contrôlé (§ 5.2) ; à refaire à chaque reprise |
| 3 | Document et modèles expliquant chaque CI/CD, pour que les devs ou un assistant écrivent eux-mêmes un pipeline conforme | ✅ [`standard-cicd-deploiement.md`](../runbooks/standard-cicd-deploiement.md) (6/11) : gate, deux workflows réutilisables et leurs entrées, modèles de wrapper Cloud Run, GKE et GKE avec approbation, check-list d'ajout, retour arrière, interdits |

## 7. Suivi par service : migré, migrable sans préalable, migrable avec préalable, reste sur la VM

> Réponse à la question du 6/11 : « les 44 % restants sont-ils migrables en mode SAFE ? » **Non.** Sur les 39 services de l'inventaire encore sur la VM, **4 seulement** se migrent sans préalable, et avec peu de gain. Les 35 autres attendent une décision, un correctif ou un chantier. Dans l'[inventaire](inventaire-services-migration-par-lot.md), « ✅ CR / GKE » veut dire **qu'une copie existe**, pas qu'elle sert la production : ce tableau fait foi.

### 7.1 Migrés — 51 services servent la production hors VM

| Cible | Services |
|---|---|
| GKE, 34 consumers (vague 1) | QC ×7 : caracterisation, enrichissement, equivalence, generation-caracteristiques, generation-question1, generation-question2an, generation-valeurs · prix ×5 : caracterisation, extraction-devis, extraction-message, extraction-produits, milvus-processor · bases vectorielles ×5 : di-, document-, echange-, product-, website-database-qdrant-service · GraphRAG ×8 : categorie, etl, fournisseur, llm-extractor, normalize-unite, normalize-unite-retry, produit, semantique-vigil · autres ×9 : deepseek-metrics-collector, devis-processor, echange-processor, embedding-service, nettoyage-bruit-ocr, template-llm, webhook, website-processor, product-processor |
| Cloud Run, 10 API (V2-a) | api-comparaison-texte, optimize-service, api-detection-langue-fr, content-extractor-api-service, api-chat-llm, api-embedding-service, graph-rag-api-recherche-service, -optim-service, -rust-service, prix-traitement |
| Cloud Run, 6 MCP (V2-b) | mcp-leexi, mcp-ringover, mcp-google-analytics, mcp-google-search-console, mcp-api-recherche (« RAG Hellopro »), mcp-semrush |
| Cloud Run, 1 nouveau | api-question-caracteristique (pas de copie VM) |

### 7.2 Migrables sans préalable (SAFE) — 4 services, gain faible

| Service | Cible | Pourquoi SAFE | Ce qui freine quand même |
|---|---|---|---|
| `mcp-google-analytics-minisite-service` | Cloud Run (copie déjà déployée) | même modèle que `mcp-google-analytics` migré en V2-b ; sans état | **différé par décision** (14/10) : aucun usage depuis mai, reprise avec le projet mini-sites |
| `crawler-monitor-backend` | Cloud Run (copie déployée, entrée interne) | Go, sans état, aucune dépendance MySQL | vérifier que son front (VM, SSO) l'appelle par la gateway ; prévu avec V2-d |
| `mcp-normalize-unite-service` | Cloud Run (à créer) | MCP sans état, nouveau | code seulement sur `features/poc` : rapatrier dans `prod`, écrire le wrapper (standard CI/CD) |
| `graph-rag-dlq-manager` | GKE (shadow prêt) | aucun usage réel en 7 jours ; RabbitMQ seul | **gain nul** et un Service interne à exposer (≈ 18 $/mois) : non recommandé |

### 7.3 Migrables avec un préalable — 23 services

| Préalable | Services | Détail |
|---|---|---|
| **Correctif reranking ou lots de nuit** (V2-a3-bis) | `api-recherche-service`, `api-classification-service` (10 répliques), `mcp-classification-produit-service` | cause prouvée (§ 2.4) ; devs sans levier à court terme (D-06) ; classification-produit suit api-classification |
| **Taille des requêtes** | `api-ingestion-service` | 413 au-delà de 32 Mo sur Cloud Run : découper les envois, ou cible GKE |
| **Correctif DSO** | `api-rest-milvus-service` | `global-stats` en 503 hors rafale (F-HP-DEV-012, correctif de code prévu le 09/10, CPU toujours alloué refusé pour le coût) ; copie Cloud Run déployée à `min=0` |
| **Bases MySQL de la VM** (`gateway_db`, SSO) | `api-gateway-go-service`, `mcp-gateway-service`, `mcp-zoho-service`, `mcp-google-templates-runner` (B1) ; `account-service-backend`, `account-service-frontend`, `redis-client-frontend`, `crawler-monitor-frontend`, `mcp-gateway-frontend` (P8) | décision d'architecture : Cloud SQL, ou MySQL maintenu sur la VM avec accès par l'enabler (option B du 15/10) |
| **Entrée publique à basculer** | `api-html-recherche-service` (`rag.hellopro.eu`, WebSocket vers la recherche), `nextjs-conseils-hp` (`conseils.hellopro.fr`, décision produit / SEO, ProxyPass Ecritel) | vhost nginx ou Apache Ecritel, puis DNS Gandi en fin de vague ; WebSocket à tester sur Cloud Run (délai maximal) |
| **Gain nul ou risque** | `graph-rag-api-admin-service` (écrit dans Neo4j, appels gRPC vers la VM, client Ecritel), `dlq-manager-service` (décision 5 : reste, F-HP-SEC-027), `image-comparison-service` (décision équipe 15/10 : non migré, compteur Redis partagé) | revoir seulement si la VM GPU doit disparaître |
| **Stabilisation du code** (V2-a4) | `agent-service` (+ authentification, F-HP-SEC-033), `mcp-hellodata-service` | correctifs fréquents sur `features/poc` ; préparés (PR #871, #872) |
| **Dette CVE** | `nextjs-formulaire-hp` (Next 14 → 15), `mcp-neo4j-service` (`fastmcp` plafonné par l'upstream, VEX) | ticket 008 |
| **Équivalent à créer** | `prix-extraction-siteweb` (GKE, 14 champs de configuration), `image-download-service` (hybride HTTP + consumer, NFS : découpler ou garder), `image-cdn-service` (chantier stockage V2-e) | — |

### 7.4 Restent sur la VM par conception ou en attente de qualification — 12 + 28

| Catégorie | Services |
|---|---|
| À qualifier avec le LEAD (P9) | `api-transcription-service` (code de dev), `api-chatbot-service` (dormant), `api-model-service`, `api-gateway-service` (gateway FastAPI historique), `api-catalog-service` (suit `api-gateway-go`) |
| Pas d'équivalent, ne pas arrêter | `qc-tracking-service`, `qc-fabricant-reference`, `document-echange-processor-service`, `crawler-service` (exposé par `reverse-proxy`) |
| Outils et bacs à sable | `milvus-collection-duplicator`, `api-recherche-test-modification` (ne pas migrer), `graph-rag-api-recherche-service-debug` (à supprimer) |
| Hors inventaire, sur la VM depuis le 7/10 | `unit-registry-service`, `mcp-template-neo4j-service`, `neo4j_new`, `tailscale` (liaison VPS OpenClaw), `databasus` (ticket 006) |
| P10, 28 services par conception | serveurs GPU (Triton, embedding, reranking, LLM, spaCy…), MySQL, Elasticsearch, Neo4j, Redis, Prometheus, Grafana, nginx, reverse-proxy, enabler gRPC… : liste dans l'[inventaire, § P10](inventaire-services-migration-par-lot.md) |

**Lecture** : si la migration reprend, les 4 services SAFE se traitent en deux demi-journées ; la valeur est dans les préalables de 7.3 (reranking, MySQL, entrée publique), qui sont des décisions d'architecture ou des correctifs applicatifs, pas des bascules.
