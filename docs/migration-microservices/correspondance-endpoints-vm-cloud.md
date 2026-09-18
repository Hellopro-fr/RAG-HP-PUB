# Correspondance des endpoints — VM GPU → Cloud Run / GKE

> **À qui ça s'adresse** : aux développeurs qui veulent savoir, pour *leur* service, comment on l'atteignait avant, comment on l'atteint après, et quelle variable de configuration changer.
>
> **Établi le 2026-09-17** à partir de trois sources réelles, pas de suppositions : `docker-compose.yml` de la VM (117 services), la table de routage `apps-microservices/api-gateway/.env.url` récupérée sur la VM, et l'état live de Cloud Run + GKE.


> 📍 **Publié sur la branche `prod` le 2026-09-18** pour toute l'équipe — `git pull` pour la version à jour.
> Point d'entrée du dossier : [`README.md`](README.md) · procédure de vérification : [`guide-pre-check-service.md`](guide-pre-check-service.md).
> Ce document est **dérivé de l'état réel** (le `docker-compose.yml` de la VM et l'inventaire live du cloud), pas d'une intention.
> Les documents cités ici mais **absents de ce dossier** vivent côté DevSecOps (hors dépôt applicatif) — demande-les si tu en as besoin.
> **Une erreur trouvée est une remontée utile** : signale-la au Lead Dev plutôt que de contourner.

---

## Comment lire ce document

**La première chose à savoir : à la bascule du 19-20 septembre, rien ne change pour vous.** Le périmètre J0 ne concerne que le plan de traitement asynchrone (les consumers RabbitMQ). Toutes les adresses HTTP décrites ici restent servies par la VM ce week-end-là. Ce document sert à **préparer la vague 2**, pas à agir maintenant.

Trois familles, trois niveaux d'effort très différents :

| Famille | Combien | Ce que le dev doit faire |
|---|:--:|---|
| **A. Services HTTP routés par le gateway** | 26 routes | Rien : la route change dans `.env.url`, côté infra. Vos appels `/<name>-service` restent identiques. |
| **B. Appels directs service → service** | ~15 | **C'est ici que se trouve le travail** : une URL en dur ou un défaut de code pointe un nom de conteneur Docker qui n'existera plus. |
| **C. Consumers RabbitMQ** | 34 | **Rien du tout.** Ils s'abonnent à une queue, ils n'ont pas d'adresse. Vous publiez dans RabbitMQ exactement comme avant. |

**Convention Cloud Run** : toutes les URLs suivent `https://<nom-service>-xqksdwdiga-ew.a.run.app`. Le nom du service Cloud Run **perd souvent le suffixe `-service`** du nom de conteneur VM (`api-recherche-service` → `api-recherche`). C'est la source d'erreur la plus fréquente.

**Convention GKE** : un déploiement n'est joignable que s'il a un `Service`. Il n'y en a que **6** dans le namespace `apps-microservices` ; les 36 autres déploiements sont des consumers sans endpoint. Adresse interne : `http://<service>.apps-microservices.svc.cluster.local:<port>`.

---

## A. Routes du gateway (`.env.url`)

Le gateway ne contient aucune liste de services en dur : il construit sa table depuis l'environnement, une variable `SERVICE_<NOM>` créant la route `/<nom>-service`. **Si vous appelez le gateway, vous n'avez rien à changer** — seule la valeur de la variable bouge.

| Route gateway | AVANT (VM) | APRÈS | Bascule |
|---|---|---|---|
| `SERVICE_INGESTION` | `http://api-ingestion-service:8509` | CR **`api-ingestion`** | vague 2 |
| `SERVICE_SEARCH` | `http://api-recherche-service:8510` | CR **`api-recherche`** | vague 2 |
| `SERVICE_CLASSIFICATION` | `http://api-classification-service:8577` | CR **`api-classification`** | vague 2 |
| `SERVICE_CHAT` | `http://api-chat-llm-service:8540` | CR **`api-chat-llm`** | vague 2 |
| `SERVICE_REST_MILVUS` | `http://api-rest-milvus-lb:8517` | CR **`api-rest-milvus`** | vague 2 |
| `SERVICE_OPTIMIZE` | `http://optimize-service:8563` | CR **`optimize-service`** | vague 2 |
| `SERVICE_EMBEDDING` | `http://api-embedding-service:8555` | CR **`api-embedding-service`** | vague 2 |
| `SERVICE_IMAGE_COMPARATOR` | `http://reverse-proxy:8050/comparator` | CR **`image-comparison-service`** (plus de reverse-proxy) | vague 2 |
| `SERVICE_DETECTION_SITE_FR` | `http://api-detection-langue-fr-service:8999` | CR **`api-detection-langue-fr`** | vague 2 |
| `SERVICE_PRIX_TRAITEMENT` | `http://prix-traitement:8591` | CR **`prix-traitement`** | vague 2 |
| `SERVICE_COMPARAISON_TEXTE` | `http://api-comparaison-texte-service:8998` | CR **`api-comparaison-texte`** | vague 2 |
| `SERVICE_EXTRACTOR` | `http://content-extractor-api-service:8600` | CR **`content-extractor-api-service`** | vague 2 |
| `SERVICE_GRAPH` | `http://graph-rag-api-recherche-service:8525` | CR **`graph-rag-api-recherche-service`** | vague 2 |
| `SERVICE_GRAPHOPTIM` | `http://graph-rag-api-recherche-optim-service:8525` | CR **`graph-rag-api-recherche-optim-service`** | vague 2 |
| `SERVICE_GRAPHRUST` | `http://graph-rag-api-recherche-rust-service:8528` | CR **`graph-rag-api-recherche-rust-service`** | vague 2 |
| `SERVICE_GRAPHADMIN` | `http://graph-rag-api-admin-service:8527` | **GKE** `graph-rag-api-admin-service.apps-microservices.svc.cluster.local:8527` | vague 2 |
| `SERVICE_GRAPHDLQ` | `http://graph-rag-dlq-manager-service:8520` | **GKE** `graph-rag-dlq-manager.apps-microservices.svc.cluster.local:8520` (⚠️ nom sans `-service`) | vague 2 |
| `SERVICE_CRAWLING` | `http://reverse-proxy:8050/crawler` | ⬜ **à trancher** — `crawler-service` n'est ni dans les 31 CR ni dans les 42 GKE | non planifié |
| `SERVICE_DEEPSEEK_OCR` | `http://deepseek-ocr:8501` | 🔒 **reste sur la VM** (GPU) | jamais |
| `SERVICE_TRANSCRIPTION` | `http://api-transcription-service:8515` | 🔒 reste VM (service en cours de dev, reclassé hors migration) | — |
| `SERVICE_IMAGE_DOWNLOAD` | `http://image-download-service:8505` | ⏸️ **différé** (hybride NFS, à découpler) | vague 2+ |
| `SERVICE_IMAGE_CDN` | `http://image-cdn-service:8580` | ⏸️ **différé** (chantier stockage GCS) | vague 2+ |
| `SERVICE_QC_TRACKING` | `http://qc-tracking-service:8590` | 🔒 hors périmètre du ticket | — |
| `SERVICE_DUPLICATION` | `http://milvus-collection-duplicator:8521` | 🔒 outil ponctuel, non migré | — |
| `SERVICE_GRAPHDEBUG` | `http://graph-rag-api-recherche-service-debug:8526` | ⚠️ **à supprimer** : profil `disabled`, mais 1318 logs/7 j et deux mois en production (T001-S001-011) | à nettoyer |
| `SERVICE_OPTIMOTEUR` | `http://10.0.1.240:8570` | ⚠️ **adresse IP en dur** vers `opti-moteur-recherche` (namespace GKE `moteur-recherche`, hors ticket 001) | à remplacer par un nom DNS |

> ⚠️ Le gateway lui-même existe en **deux exemplaires** sur le port 8500 : `api-gateway-service` (Python, conservé pour rollback) et `api-gateway-go-service` (Go, **actif depuis le 2026-05-07**). Seul le Go est porté sur GKE. Une seule cible pour `api.hellopro.eu`.

---

## B. Appels directs service → service — **le vrai travail des devs**

Ces appels ne passent pas par le gateway. Ils utilisent un nom de conteneur Docker qui **n'existera plus** une fois le service hors de la VM.

| Appelant | Cible AVANT | Variable | Cible APRÈS |
|---|---|---|---|
| `api-classification` | `http://optimize-service:8563` | `OPTIMIZE_SERVICE_URL` | CR `optimize-service` |
| `mcp-classification-produit` | `http://api-classification-lb:80` | `CLASSIFICATION_API_URL` | CR `api-classification` ✅ **déjà fait** |
| `crawler-service` | `http://api-detection-langue-fr-service:8999` | `DETECTION_LANGUE_API_URL` | CR `api-detection-langue-fr` |
| `crawler-service` | `http://content-extractor-api-service:8600` | `CONTENT_EXTRACTOR_API_URL` | CR `content-extractor-api-service` |
| `crawler-monitor-backend` | `http://image-download-service:8505` | `IMAGE_DOWNLOAD_SERVICE_URL` | ⏸️ différé — reste VM |
| `api-gateway-go`, `api-gateway`, `redis-client-frontend` | `http://account-service-backend:8600` | `ACCOUNT_BASE_URL` / `ACCOUNT_INTERNAL_URL` | CR `account-service-backend` (vague 2, SSO) |
| `account-service-backend`, `mcp-google-templates-runner` | `http://mcp-gateway-service:8592` | `MCP_GATEWAY_INTERNAL_URL` / `MCP_GATEWAY_URL` | ⚠️ **GKE sans `Service`** — à créer (checklist 1d.1) |
| `mcp-gateway-service` | `http://mcp-google-templates-runner:8595` | `GOOGLE_TEMPLATES_RUNNER_URL` | GKE `mcp-google-templates-runner…:8595` ✅ Service existant |
| `mcp-gateway-service` | `http://mcp-zoho-service:8596` | `ZOHO_INTERNAL_URL` | ⚠️ **GKE sans `Service`** — à créer |
| `mcp-gateway-service` | `http://mcp-leexi-service:8589` | `LEEXI_INTERNAL_URL` | CR `mcp-leexi-service` |
| `mcp-gateway-service` | `http://mcp-ringover-service:8586` | `RINGOVER_INTERNAL_URL` | CR `mcp-ringover-service` |
| `mcp-zoho-service` | `http://mcp-zoho-service:8596/mcp` (auto-référence) | `ZOHO_SELF_URL` | GKE, après création du `Service` |
| `document-echange-processor` | `${BASE_API_URL}/deepseek_ocr-service` | `BASE_API_URL` | gateway → inchangé |
| `deepseek-metrics-collector` | `http://api-gateway:8500/v1/log-metrics` | `DEEPSEEK_METRICS_COLLECTOR_URL` | gateway GKE `api-gateway-go…:8500` |
| `llm-service` | `http://vllm-server:8000/v1/chat/completions` | `VLLM_API_URL` | 🔒 reste VM (GPU) |

### Deux pièges à corriger dans le code (F-HP-DEV-005)

**Les défauts gRPC sont faux.** Quatre clients de `libs/common-utils` pointent `:50051` alors que le vrai port est ailleurs :

| Client | Défaut codé | Port réel |
|---|---|---|
| `graph_database_client.py` | `…:50051` | **50055** |
| `graph_milvus_client.py` | `…:50051` | **50056** |
| `graph_normalization_client.py` | `…:50051` | **50057** |
| `spacy_client.py` | `…:50051` | **50058** |

Sur la VM, `docker-compose.yml` surcharge toujours ces variables, donc le défaut n'est jamais exercé. Hors VM, **un service déployé sans la variable démarre sans erreur et échoue silencieusement**. Les manifestes GKE actuels définissent bien les ports — mais tout nouveau portage doit y penser.

**Et des défauts `localhost` qui ne peuvent pas fonctionner en conteneur** : `api-rest-milvus/app/core/credentials.py` appelle `api-recherche` via `http://localhost` — or ce service tourne **déjà sur Cloud Run**. À vérifier : ce chemin de code est-il réellement exercé ?

### Accès au GPU : inchangé et pérenne

Les modèles restent sur la VM. Les services qui les appellent passent par le **proxy haproxy** `10.11.0.2` :

| Backend | Port enabler |
|---|---|
| LLM | `10.11.0.2:15051` |
| Embedding | `10.11.0.2:15052` |
| Reranking | `10.11.0.2:15053` |
| Database recherche | `10.11.0.2:15054` |
| graph-rag Milvus / DB-connector / Normalize / spaCy | `15055` / `15056` / `15057` / `15058` |

---

## C. Consumers RabbitMQ (34) — rien ne change pour vous

`qc-*` (7), `prix-*` (5), `graph-rag-*-processor` (8), les writers `*-database-qdrant-service` (5), les processors (4), `embedding-service`, `template-llm-service`, `nettoyage-bruit-ocr-service`, `deepseek-metrics-collector-service`, `webhook-service`.

Ces services **n'ont aucune adresse** : ils s'abonnent à une queue. Ils tournent déjà sur GKE en shadow et reprendront la production au cutover. Le producteur publie dans RabbitMQ exactement comme avant — **aucune variable à changer**.

Ce qui change est invisible côté application : l'URL du broker, qui passe du broker DEV au broker de production. C'est de la configuration d'infrastructure, injectée par un secret Kubernetes.

Trois consumers VM **n'ont pas d'équivalent GKE** et restent donc sur la VM : `document-echange-processor-service`, `qc-fabricant-reference`, `prix-extraction-siteweb`.

---

## D. Entrées publiques — inchangées à J0

| Hostname | AVANT | APRÈS (vague 2) |
|---|---|---|
| `api.hellopro.eu` | nginx VM → `127.0.0.1:8500` | GKE `api-gateway-go` |
| `rag.hellopro.eu` | nginx VM → `127.0.0.1:8550` | CR `api-html-recherche` |
| `mcp.hellopro.eu` | nginx VM → `127.0.0.1:8581` | GKE `mcp-gateway-frontend` (⚠️ le front est sur 8581, le backend sur 8592) |
| `conseils.hellopro.fr` | reverse proxy → `nextjs-conseils-hp:3003` | CR `nextjs-conseils-hp` — ⚠️ **décision produit/SEO** : le Next.js ne remplace que *progressivement* les pages PHP |
| `formulaire.hellopro.eu`, `www.hellopro.fr` | nginx VM → `127.0.0.1:8579` | CR `nextjs-formulaire-hp` (après migration Next 15) |
| `cmf.hellopro.eu` | nginx VM → `127.0.0.1:3002` | CR `crawler-monitor-frontend` (SSO, vague 2) |
| `dlq.hellopro.eu` | nginx VM → `127.0.0.1:8585` | GKE `dlq-manager-service:8560` |
| `login.hellopro.eu` | nginx VM → `127.0.0.1:8601` | CR `account-service-frontend` (SSO, vague 2) |
| `grafana`, `kibana`, `n8n-dev`, `neo4j1`, `pmyadm` | nginx VM | **à retirer de l'exposition publique** — accès par tunnel IAP (F-HP-SEC-001) |

---

## E. Bases de données et dépendances — adresses inchangées

Les bases ne bougent pas. Ce qui change au cutover, c'est le passage des instances **DEV** aux instances **PROD**, côté secret.

| Dépendance | Adresse prod |
|---|---|
| RabbitMQ | `10.0.1.216:5672` |
| Milvus | `10.0.1.51:19530` (⚠️ les variables s'appellent `ZILLIZ_*` — nommage historique, ce n'est pas Zilliz Cloud) |
| Neo4j | `10.0.1.218:7687` |
| Redis | `10.0.1.220:6379` |
| Qdrant | `10.0.1.237:6333` (serveur présent, mais les services `*-qdrant-*` écrivent en réalité dans Milvus) |
| MySQL gateway | `10.11.0.2:3307` via l'enabler (reste sur la VM) |
| API HelloPro | `https://api.hellopro.fr`, `https://www.hellopro.fr` (ECRITEL) |

---

## F. Ce qu'il faut retenir

**Pour le week-end du 19-20** : ne changez rien. Aucune adresse HTTP ne bouge.

**Pour préparer la vague 2**, cherchez dans votre service :
1. tout `http://<nom>-service:<port>` en dur ou en valeur par défaut → section B ;
2. tout défaut `localhost` → il ne fonctionnera pas en conteneur ;
3. tout port gRPC `50051` sur un client graph-rag → c'est faux, voir le tableau.

**La bonne pratique à adopter** : une variable d'adresse manquante doit **faire échouer le démarrage**, pas dégrader en silence vers un défaut faux. C'est ce qui aurait évité les deux pièges ci-dessus.

---

## Sources et réserves

`docker-compose.yml` de la VM (117 services), `apps-microservices/api-gateway/.env.url` (26 routes, récupéré le 2026-09-17), `docker-compose.override.yml` de la VM (1,5 Ko — n'active que 5 profils : elasticsearch, kibana, init-elasticsearch, dlq-archiver-host, dlq-manager-service), `gcloud run services list` (31 services), `kubectl get svc/deploy -n apps-microservices` (6 Services, 42 déploiements), `cartographie-dns-nginx-vm-gpu.md` (13 vhosts).

Points non tranchés, signalés comme tels : la cible de `SERVICE_CRAWLING` (`crawler-service` absent des deux plateformes), `SERVICE_OPTIMOTEUR` qui pointe une IP en dur, le sort de `SERVICE_GRAPHDEBUG`, et l'attribution exacte de `EMBEDDING_API_URL` (interne ou fournisseur externe — la valeur du `.env` est anonymisée dans le dépôt).

Findings associés : **F-HP-IaC-004** (`.env.url` et l'override hors dépôt), **F-HP-DEV-005** (défauts d'adressage faux).
