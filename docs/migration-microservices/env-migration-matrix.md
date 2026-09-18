# Matrice de migration des variables d'environnement (.env VM → par service CR/GKE)

> **But** : sortir du `.env` centralisé unique (VM GPU) vers un jeu de variables **par service** (Cloud Run `--set-env-vars`/`--set-secrets`, GKE env/secretKeyRef). §A = catalogue de toutes les variables de l'ancien `.env` + leur traitement. §B = jeu par service.
>
> ⚠️ **RÈGLE SÉCURITÉ** : un **secret** n'apparaît JAMAIS en clair ici — uniquement sa **référence Secret Manager** (`nom-secret:latest`). La valeur vit dans Secret Manager (24 déjà poussés, cf. `mapping_secret_env.md`) et se rote après cutover. Seules les valeurs **de config non sensibles** sont écrites en clair.
>
> Sources : `RAG-HP-PUB/env_model` (catalogue anonymisé) · `sprint_003_artifacts/secrets-classification.md` · `mapping_secret_env.md` · wrappers CR `deploy-*.yml` (valeurs par service déjà définies) · `[[reference_env_model]]`. Créé 2026-09-14.


> 📍 **Publié sur la branche `prod` le 2026-09-18** pour toute l'équipe — `git pull` pour la version à jour.
> Point d'entrée du dossier : [`README.md`](README.md) · procédure de vérification : [`guide-pre-check-service.md`](guide-pre-check-service.md).
> Ce document est **dérivé de l'état réel** (le `docker-compose.yml` de la VM et l'inventaire live du cloud), pas d'une intention.
> Les documents cités ici mais **absents de ce dossier** vivent côté DevSecOps (hors dépôt applicatif) — demande-les si tu en as besoin.
> **Une erreur trouvée est une remontée utile** : signale-la au Lead Dev plutôt que de contourner.

**Légende Traitement** : `CONFIG` = valeur en clair par service · `SECRET→SM` = réf Secret Manager · `URL-REWRITE` = adresse à recalculer (DNS interne/CR/LB) · `DROP` = obsolète post-migration · `[À DÉFINIR]` = valeur/cible à trancher.

---

## §A — Catalogue global des variables (ancien `.env`)

### A.1 Bases internes (VPC) — IP privées préservées (accès via VPC connector CR / routage GKE)
| Variable | Nature | Traitement | Cible (valeur config / réf) |
|---|---|---|---|
| `QDRANT_HOST_URL` | config | CONFIG | `10.0.1.237` |
| `QDRANT_PORT` | config | CONFIG | `6333` |
| `QDRANT_API_KEY` | secret | SECRET→SM | `none` en dev (ou `<qdrant>-api-key` si activé) |
| `REDIS_HOST` | config | CONFIG | `10.0.1.220` (⚠️ cutover : DEV vs prod) |
| `REDIS_PORT` | config | CONFIG | `6379` |
| `REDIS_SECRET` | secret | SECRET→SM | `platform-redis-secret:latest` |
| `RABBITMQ_URL` | secret | SECRET→SM | `platform-rabbitmq-url:latest` (dev) → prod au cutover |
| `NEO4J_URI` / `_USER` / `_DATABASE` | config | CONFIG / URL-REWRITE | `neo4j://10.0.1.218:7687` (dev→prod cutover) |
| `NEO4J_PASSWORD` | secret | SECRET→SM | `platform-neo4j-password:latest` |
| `ELASTICSEARCH_URL` | config | URL-REWRITE | ES interne (dev→prod cutover) |
| `ELASTIC_PASSWORD`, `DLQ_ARCHIVER_ES_*`, `DLQ_MANAGER_ES_*`, `KIBANA_PASSWORD` | secret | SECRET→SM | `<dlq/es>-*` dédiés [à confirmer noms SM] |

### A.2 Milvus (variables au nom legacy `ZILLIZ_*`)
> ⚠️ **Nommage legacy** : les variables `ZILLIZ_*` désignent la connexion au **Milvus self-hosted interne** (VPC privé), pas au SaaS Zilliz Cloud. **Zilliz Cloud n'est pas utilisé** (essai 14 j abandonné) → aucune dépendance egress/allowlist externe de ce côté (cf. `[[reference_qdrant_naming_legacy]]` pour le même piège de nommage côté Qdrant). Les creds `ZILLIZ_USER`/`_PASSWORD` = auth Milvus, à reséeder dev→prod au cutover.

| Variable | Nature | Traitement | Cible |
|---|---|---|---|
| `ZILLIZ_URI_DEV` / `ZILLIZ_URI` | config | URL-REWRITE | `milvus.hello.dev.private.com` / `milvus-prod...` (bascule cutover) |
| `ZILLIZ_PORT` | config | CONFIG | `19530` |
| `ZILLIZ_API_KEY` | secret | SECRET→SM | `platform-zilliz-api-key:latest` (`none` si mode user/pass) |
| `ZILLIZ_USER` | secret | SECRET→SM | `platform-zilliz-user:latest` |
| `ZILLIZ_PASSWORD` | secret | SECRET→SM | `platform-zilliz-password:latest` |
| `MILVUS_GLOBAL_MAX_CONCURRENT`, `MILVUS_WRITE_CEILING`, `M_PARAMS`, `EF_PARAMS` | config | CONFIG | valeurs numériques (cf. wrappers) |

### A.3 LLM / API keys externes
| Variable | Nature | Traitement | Cible (réf SM) |
|---|---|---|---|
| `OPENAI_API_KEY` | secret | SECRET→SM | `platform-openai-api-key:latest` |
| `OPENROUTER_API_KEY` | secret | SECRET→SM | `platform-openrouter-api-key:latest` |
| `DEEPSEEK_API_KEY` | secret | SECRET→SM | `platform-deepseek-api-key:latest` |
| `GEMINI_API_KEY` | secret | SECRET→SM | `platform-gemini-api-key:latest` |
| `ANTHROPIC_API_KEY` | secret | SECRET→SM | `platform-anthropic-api-key:latest` [à créer si utilisé] |
| `DEEPSEEK_API_URL`, `DEEPSEEK_MODEL_NAME`, `LLM_PROVIDER`, `MODEL_NAME` | config | CONFIG | valeurs texte |
| `EMBEDDING_API_URL` | config | URL-REWRITE | via enabler gRPC-GPU / LB |
| `EMBEDDING_API_KEY` | secret | SECRET→SM | `platform-embedding-api-key:latest` |
| `TRITON_URL` | config | URL-REWRITE | enabler gRPC→GPU `10.11.0.2:1505x` (cf. `[[reference_grpc_gpu_proxy_enabler]]`) |

### A.4 Auth / JWT / MCP
| Variable | Nature | Traitement | Cible |
|---|---|---|---|
| `JWT_SECRET` | secret | SECRET→SM | `platform-jwt-secret:latest` |
| `JWT_ISSUER` / `JWT_AUDIENCE` / `JWT_EXP_SECONDS` / `JWT_ALGO` | config | CONFIG | ex. `JWT_AUDIENCE=https://rag.hellopro.eu`, `JWT_ALGO=HS256` |
| `AUTH_TOKEN`, `JSON_KEY` | secret | SECRET→SM | dédiés [à confirmer] |
| `AUTH_URL` | config | CONFIG | `https://www.hellopro.fr/.../auth.php` (ECRITEL) |
| `MCP_AUTH_ENABLED` | config | CONFIG | flag |
| `MCP_ENCRYPTION_KEY` | secret | SECRET→SM | `platform-mcp-encryption-key:latest` |
| `MCP_FALLBACK_PASS` | secret | SECRET→SM | `platform-mcp-fallback-pass:latest` |
| `MCP_FALLBACK_USER` / `_EMAIL`, `MCP_ADMIN_EMAILS`, `MCP_ALLOWED_EMAILS`, `MCP_SSO_ENABLED` | config | CONFIG | valeurs texte/flags |

### A.5 API HelloPro (ECRITEL) / Webhook
| Variable | Nature | Traitement | Cible |
|---|---|---|---|
| `HP_TOKEN` | secret | SECRET→SM | `platform-hp-token:latest` |
| `HELLOPRO_API_BEARER_TOKEN` | secret | SECRET→SM | `platform-hellopro-api-bearer-token:latest` |
| `HELLOPRO_API_URL` (fronts) | config | CONFIG | `https://api.hellopro.fr` (ECRITEL — cf. Annexe E egress) |
| `KEY_WEBHOOK` | secret | SECRET→SM | `platform-key-webhook:latest` (⚠️ placeholder — F-HP-SEC-008) |
| `WEBHOOK_UPDATE_PRODUIT_URL`, `DEEPSEEK_METRICS_COLLECTOR_URL` | config | CONFIG | URLs PHP ECRITEL (préservées) |
| `CONSEILS_API_TOKEN` | secret | SECRET→SM | `nextjs-conseils-hp-api-token:latest` (dédié) |

### A.6 Gateway MySQL / Catalog / Account
| Variable | Nature | Traitement | Cible |
|---|---|---|---|
| `MYSQL_ROOT_PASSWORD` | secret | SECRET→SM | `platform-gateway-mysql-root-pass:latest` |
| `DB_USER` / `DB_NAME` / `GATEWAY_MYSQL_PORT` | config | CONFIG | valeurs |
| `DB_PASS` (`GATEWAY_MYSQL_PASS`) | secret | SECRET→SM | `platform-gateway-mysql-pass:latest` |
| `GATEWAY_ADMIN_USER` | config | CONFIG | valeur |
| `GATEWAY_ADMIN_PASSWORD` / `GATEWAY_ADMIN_KEY` | secret | SECRET→SM | `platform-gateway-admin-key:latest` (+ pass dédié) |
| `CATALOG_ADMIN_KEY` | secret | SECRET→SM | `platform-catalog-admin-key:latest` |
| `BDD_CATALOG_BASE_URL` | config | URL-REWRITE | CR/LB interne |
| `BDD_CATALOG_TOKEN` / `BDD_PUBLIC_API_TOKEN` | secret | SECRET→SM | dédiés [à confirmer] |
| `ACCOUNT_ENCRYPTION_KEY`, `ACCOUNT_INTERNAL_TOKEN` | secret | SECRET→SM | `platform-account-internal-token:latest` (+ encryption dédié) |
| `ACCOUNT_PUBLIC_URL`, `ACCOUNT_SECURE_COOKIE` | config | CONFIG | ex. `https://account.hellopro.fr` |
| `ZOHO_GATEWAY_TOKEN` | secret | SECRET→SM | `platform-zoho-gateway-token:latest` |

### A.7 MCP tierces (Semrush / Ringover / Leexi) + Google
| Variable | Nature | Traitement | Cible |
|---|---|---|---|
| `SEMRUSH_API_KEY` | secret | SECRET→SM | `mcp-semrush-api-key:latest` (dédié) |
| `RINGOVER_API_KEY`, `MCP_RINGOVER_ADMIN_TOKEN` | secret | SECRET→SM | `platform-mcp-ringover-admin-token` + `<ringover>-api-key` |
| `RINGOVER_API_BASE_URL`, `RINGOVER_INTERNAL_URL` | config | URL-REWRITE | CR interne |
| `LEEXI_API_KEY_ID` / `_SECRET`, `MCP_LEEXI_ADMIN_TOKEN` | secret | SECRET→SM | `platform-mcp-leexi-admin-token` + `<leexi>-*` |
| `LEEXI_INTERNAL_URL` | config | URL-REWRITE | CR interne |
| `GOOGLE_ANALYTICS_PROJECT_ID(_MINISITE)` | config | CONFIG | ID projet GA |
| `GOOGLE_ANALYTICS_CREDENTIALS_PATH(_MINISITE)`, `GSC_CREDENTIALS_PATH` | secret (fichier) | SECRET→SM (monté fichier) | clé SA Google montée en secret-fichier (cf. `[[reference_cloud_run_reserved_env_vars]]` pattern secret-fichier) |
| `GSC_SITE_URL`, `GSC_SKIP_OAUTH` | config | CONFIG | valeurs |
| `GOOGLE_CLIENT_ID` | config | CONFIG | OAuth client ID |
| `GOOGLE_CLIENT_SECRET` | secret | SECRET→SM | dédié |
| `GOOGLE_TEMPLATES_RUNNER_ADMIN_TOKEN` | secret | SECRET→SM | `platform-mcp-templates-runner-admin-token:latest` |
| `NEO4J_MCP_URI/_USERNAME/_PASSWORD/_DATABASE` | config+secret | CONFIG + SECRET→SM | URI/ user config ; password → SM dédié mcp-neo4j |

### A.8 Observabilité / Divers / Infra
| Variable | Nature | Traitement | Cible |
|---|---|---|---|
| `SLACK_WEBHOOK_URL` | secret | SECRET→SM | `platform-slack-webhook-url:latest` (injecté au deploy CI) |
| `SLACK_ENV_LABEL`, `LOGIN_SLACK_URL` | config | CONFIG | valeurs |
| `GRAFANA_ADMIN` / `GRAFANA_PASSWORD` / `GF_SMTP_*` | secret+config | SECRET→SM + CONFIG | Grafana = stack monitoring (hors scope services applicatifs — reste infra) |
| `GCS_BUCKET_NAME` | config | CONFIG | `hp-rag-data` (public, non sensible) |
| `APIFY_PROXY` | secret | SECRET→SM | dédié (`api-detection-langue-fr`) |
| `ADMIN_PASSWORD_HASH` | secret | SECRET→SM | `crawler-monitor-admin-password-hash:latest` (dédié) |
| `CORS_ALLOWED_ORIGINS` | config | CONFIG | ex. `https://cmf.hellopro.eu` |
| `TRITON_URL`, `AUTO_STASH_ENABLED`, `ENABLE_MOVE`, `ENABLE_PAGE_IMAGE_CONSUMER` | config | CONFIG / DROP | flags (certains DROP si obsolètes) |
| `GKE_HOST`, `BASE_API_URL`, `MCP_GATEWAY_PUBLIC_URL`, `GATEWAY_PUBLIC_URL` | config | URL-REWRITE | LB/DNS public (bascule cutover) |

> **Réservé Cloud Run** : ne JAMAIS passer `PORT`/`K_SERVICE`/`K_REVISION`/`K_CONFIGURATION` (injectés) — cf. `[[reference_cloud_run_reserved_env_vars]]`.

---

## §B — Jeu de variables par service

> Pour chaque service : **CONFIG** (valeurs en clair) + **SECRETS** (réfs SM) + **statut**. Les CR sont extraits des wrappers `deploy-<svc>.yml` (source de vérité runtime) ; les GKE des manifests. Statuts : ✅ défini · ⚠️ placeholder (F-HP-SEC-008) · 🟦 à définir.

### Gabarit
```
### <service>  (plateforme CR|GKE · port · ingress)
CONFIG    : VAR=valeur ; VAR2=valeur2 ; ...
SECRETS   : VAR → <secret-sm>:latest ; ...
Statut    : ✅ / ⚠️ placeholder <lesquels> / 🟦 à définir <lesquels>
Source    : deploy-<svc>.yml | manifest GKE | code
```

### Exemple travaillé — `graph-rag-api-recherche-service` (CR · 8528 · ingress all)
```
CONFIG :
  LLM_SERVICE_URL=10.11.0.2:15051        # enabler gRPC→GPU
  EMBEDDING_SERVICE_URL=10.11.0.2:15052
  RERANKING_SERVICE_URL=10.11.0.2:15053
  DATABASE_SERVICE_URL=10.11.0.2:15054
  (+ ports graph-rag 15055-15058 selon service)
  NEO4J_URI=neo4j://10.0.1.218:7687      # dev → prod au cutover
  HELLOPRO_API_URL=https://api.hellopro.fr   # ECRITEL (egress all-traffic → NAT 35.233.35.8)
  ZILLIZ_URI=milvus-prod.hello.dev.private.com ; ZILLIZ_PORT=19530
SECRETS :
  HELLOPRO_API_BEARER_TOKEN → platform-hellopro-api-bearer-token:latest
  NEO4J_PASSWORD            → platform-neo4j-password:latest
  GEMINI_API_KEY            → platform-gemini-api-key:latest
  (+ OPENAI/DEEPSEEK/OPENROUTER selon usage)
Statut : ✅ config + secrets définis (wrapper) — NEO4J/broker = bascule prod au cutover
Source : deploy-graph-rag-api-recherche-service.yml
```

## §B — Lot 1 : 27 CR portés (extraction wrappers `deploy-*.yml`, 2026-09-14)

> Source de vérité runtime = le `with:` de chaque `deploy-<svc>.yml` (appelant le réutilisable `deploy-cloud-run.yml`). **Vérifié** : aucun secret en clair — chaque entrée `secret_env_vars_json` est une **réf Secret Manager** (`nom:latest`). Défauts du réutilisable pour les champs absents : `port=8080`, `health=/health`, `ingress=internal`, connector vide, `egress=private-ranges-only`, `gate Trivy actif`, `allow_unauthenticated=false`.

**Profils communs** (référencés dans les blocs pour éviter la répétition) :

- **`[ENABLER]`** — gRPC→GPU via proxy haproxy VM `10.11.0.2` (cf. `[[reference_grpc_gpu_proxy_enabler]]`) : `15051`=LLM · `15052`=EMBEDDING · `15053`=RERANKING · `15054`=DATABASE · `15055`=MILVUS(graph) · `15056`=GRAPH_DATABASE · `15057`=NORMALIZATION · `15058`=SPACY.
- **`[BASE-VECT]`** (identique sur les services RAG) : `ZILLIZ_URI=milvus-prod.hello.dev.private.com` ; `ZILLIZ_PORT=19530` ; `ZILLIZ_API_KEY=none` ; `QDRANT_HOST_URL=10.0.1.237` ; `QDRANT_PORT=6333` ; `QDRANT_API_KEY=none` ; `M_PARAMS=32` ; `EF_PARAMS=300`. ⚠️ `ZILLIZ_*` = **Milvus self-hosted** (nommage legacy, cf. §A.2) → dev→prod (`10.0.1.51`) au cutover.
- **`[LLM-SECRETS]`** (réfs SM communes famille RAG, chaque service en prend un sous-ensemble) : `OPENAI_API_KEY→platform-openai-api-key` · `OPENROUTER_API_KEY→platform-openrouter-api-key` · `DEEPSEEK_API_KEY→platform-deepseek-api-key` · `GEMINI_API_KEY→platform-gemini-api-key` · `RABBITMQ_URL→platform-rabbitmq-url` · `KEY_WEBHOOK→platform-key-webhook`.

### B.1 — Synthèse déploiement (27 services)

| Service | Port | Health | Ingress | Auth | Connector | Egress | Gate Trivy |
|---|---|---|---|---|---|---|---|
| api-recherche | 8510 | /openapi.json | all | public | ✅ | private | off |
| api-chat-llm | 8540 | / | all | public | ✅ | private | off |
| optimize-service | 8563 | /openapi.json | all | public | ✅ | private | off |
| api-embedding-service | 8555 | / | all | public | ✅ | private | off |
| api-rest-milvus | 8517 | /health | all | public | ✅ | private | off |
| api-question-caracteristique | 8540 | / | all | public | ✅ | private | off |
| prix-traitement | 8591 | / | all | public | ✅ | private | off |
| api-classification | 8577 | /health | all | public | ✅ | **all-traffic** | off |
| graph-rag-api-recherche-service | 8525 | /health | all | public | ✅ | **all-traffic** | off |
| graph-rag-api-recherche-optim-service | 8525 | /health | all | public | ✅ | **all-traffic** | off |
| graph-rag-api-recherche-rust-service | 8528 | /health | all | public | ✅ | **all-traffic** | **actif** (Rust) |
| mcp-api-recherche-service | 8580 | /health | all | public | ✅ | private | **actif** (Go) |
| mcp-classification-produit-service | 8593 | /health | all | public | — | private | **actif** (Go) |
| mcp-leexi-service | 8589 | /health | all | public | — | private | **actif** (Go) |
| mcp-ringover-service | 8586 | /health | all | public | — | private | **actif** (Go) |
| mcp-semrush-service | 8588 | /status | all | public | — | private | off |
| mcp-google-analytics-service | 8583 | /status | all | public | — | private | off |
| mcp-google-analytics-minisite-service | 8583 | /status | all | public | — | private | off |
| mcp-google-search-console-service | 8584 | /status | all | public | — | private | off |
| nextjs-conseils-hp | 3003 | / | all | public | ✅ | **all-traffic** | off |
| api-html-recherche | 8550 | /login | all | public | ✅ | **all-traffic** | off |
| crawler-monitor-backend | 3001 | /health | **internal** | **IAM** | ✅ | private | **actif** (Go) |
| api-ingestion | 8509 | / | all | public | ✅ | private | off |
| api-comparaison-texte | 8998 | /api/v1/health | all | public | — | private | off |
| api-detection-langue-fr | 8999 | /api/v1/health | all | public | — | private | off |
| content-extractor-api-service | 8600 | /health | all | public | — | private | off |
| image-comparison-service | 8504 | / | all | public | ✅ | private | off |

### B.2 — CONFIG + SECRETS par service

**Famille RAG core** (toutes : `[BASE-VECT]` + `[ENABLER]` + sous-ensemble `[LLM-SECRETS]`)
- **api-recherche** — CONFIG : `SERVICE_NAME=api-recherche` ; `[ENABLER]` EMBEDDING/RERANKING/DATABASE ; `[BASE-VECT]`. Override : `gunicorn -w 2 -k uvicorn.workers.UvicornWorker`, cpu-boost, mémoire 1Gi (cf. `[[reference_cloud_run_gunicorn_workers]]`). SECRETS : `[LLM-SECRETS]` complet (OPENAI/OPENROUTER/DEEPSEEK/GEMINI/RABBITMQ/KEY_WEBHOOK). Statut ✅.
- **api-chat-llm** — CONFIG : `[ENABLER]` LLM ; `[BASE-VECT]`. SECRETS : `[LLM-SECRETS]` complet. Statut ✅.
- **optimize-service** — CONFIG : `SERVICE_NAME=optimize-service` ; `[ENABLER]` LLM. Override cpu-boost. SECRETS : **aucun** (0 `os.getenv`). Statut ✅.
- **api-embedding-service** — CONFIG : `SERVICE_NAME=api-embedding-service` ; `[ENABLER]` EMBEDDING/RERANKING ; `[BASE-VECT]`. SECRETS : `[LLM-SECRETS]` **sans GEMINI** (OPENAI/OPENROUTER/DEEPSEEK/RABBITMQ/KEY_WEBHOOK). Statut ✅.
- **api-rest-milvus** — CONFIG : `[BASE-VECT]` + `ZILLIZ_URI_DEV=milvus.hello.dev.private.com`. SECRETS : `ZILLIZ_USER→platform-zilliz-user` ; `ZILLIZ_PASSWORD→platform-zilliz-password` ; `RABBITMQ_URL→platform-rabbitmq-url` ; OPENAI/OPENROUTER/DEEPSEEK ; **`KEY_WEBHOOK→api-rest-milvus-key-webhook`** (⚠️ secret **dédié**, pas le `platform-key-webhook` partagé). Statut ✅.
- **api-question-caracteristique** — CONFIG : `SERVICE_NAME=api-question-caracteristique` ; `[ENABLER]` complet 15051-15054 ; `[BASE-VECT]`. Override 1Gi + cpu-boost. SECRETS : `[LLM-SECRETS]` complet. Statut ✅.
- **prix-traitement** — CONFIG : `SERVICE_NAME=prix-traitement` ; `[ENABLER]` complet 15051-15054 ; `[BASE-VECT]`. Override 1Gi + cpu-boost. SECRETS : `[LLM-SECRETS]` complet + **`HP_TOKEN→platform-hp-token`** (API HelloPro/ECRITEL). Statut ✅.
- **api-classification** — CONFIG : `SERVICE_NAME=api-classification` ; `[ENABLER]` complet 15051-15054 ; `[BASE-VECT]`. Override 1Gi + cpu-boost. Egress **all-traffic** (appelle ECRITEL → NAT `35.233.35.8`). SECRETS : `[LLM-SECRETS]` complet. Statut ✅.

**Famille graph-rag** (toutes : `[ENABLER]` LLM/EMBEDDING/RERANKING + graph 15055-15058 ; Neo4j ; egress **all-traffic**)
- **graph-rag-api-recherche-service** — CONFIG : `[ENABLER]` 15051-15053 + `MILVUS_SERVICE_URL=…:15055` ; `GRAPH_DATABASE_SERVICE_URL=…:15056` ; `NORMALIZATION_SERVICE_URL=…:15057` ; `SPACY_SERVICE_URL=…:15058` ; `NEO4J_URI=neo4j://10.0.1.218:7687` ; `NEO4J_USER=neo4j` ; `NEO4J_DATABASE=neo4j` ; `LLM_PROVIDER=gemini` ; `SERVICE_NAME=…`. Override 1Gi + cpu-boost. SECRETS : `NEO4J_PASSWORD→platform-neo4j-password` ; `GEMINI_API_KEY→platform-gemini-api-key` ; `HELLOPRO_API_BEARER_TOKEN→platform-hellopro-api-bearer-token`. Statut ✅.
- **graph-rag-api-recherche-optim-service** — **identique** au précédent (mêmes URLs/secrets), `SERVICE_NAME=…-optim`, port 8525. Statut ✅.
- **graph-rag-api-recherche-rust-service** — CONFIG : `API_PORT=8528` ; mêmes `[ENABLER]` graph ; **`NEO4J_URI=bolt://10.0.1.218:7687`** (⚠️ `bolt://` vs `neo4j://` des 2 autres) ; `NEO4J_USER`/`NEO4J_DATABASE` (pas de `LLM_PROVIDER` ni `SERVICE_NAME`). Override cpu-boost. Gate Trivy **actif** (Rust). SECRETS : les 3 mêmes (NEO4J_PASSWORD/GEMINI/HELLOPRO_API_BEARER_TOKEN). Statut ✅.

**Famille MCP (Go / mcp-proxy)**
- **mcp-api-recherche-service** — CONFIG : `MCP_PORT=8580` ; `[ENABLER]` complet 15051-15054. SECRETS : **aucun**. Gate actif (Go). Statut ✅.
- **mcp-classification-produit-service** — CONFIG : `MCP_PORT=8593` ; `CLASSIFICATION_API_URL=https://api-classification-xqksdwdiga-ew.a.run.app` (→ CR api-classification). SECRETS : **aucun**. Gate actif (Go). Statut ✅.
- **mcp-leexi-service** — CONFIG : `MCP_PORT=8589`. SECRETS : `LEEXI_API_KEY_ID→mcp-leexi-api-key-id` ; `LEEXI_API_KEY_SECRET→mcp-leexi-api-key-secret` ; `MCP_LEEXI_ADMIN_TOKEN→platform-mcp-leexi-admin-token`. Gate actif (Go). Statut ✅.
- **mcp-ringover-service** — CONFIG : `MCP_PORT=8586`. SECRETS : `RINGOVER_API_KEY→mcp-ringover-api-key` ; `MCP_RINGOVER_ADMIN_TOKEN→platform-mcp-ringover-admin-token`. Gate actif (Go). Statut ✅.
- **mcp-semrush-service** — CONFIG : aucune. SECRETS : `SEMRUSH_API_KEY→mcp-semrush-api-key`. Health `/status` (mcp-proxy). Statut ✅.

**Famille Google MCP** (secret **monté en fichier** = clé SA JSON ; migration ADC = F-HP-SEC-006)
- **mcp-google-analytics-service** — CONFIG : `GOOGLE_APPLICATION_CREDENTIALS=/secrets/gcp-credentials.json` ; `GOOGLE_PROJECT_ID=ga4-mcp-hellopro` ; `GOOGLE_CREDENTIALS_TYPE=json`. SECRET-FICHIER : `/secrets/gcp-credentials.json → mcp-google-analytics-sa-key`. Statut ✅.
- **mcp-google-analytics-minisite-service** — idem mais `GOOGLE_PROJECT_ID=ga4-mcp-hellopro-minisite` ; SECRET-FICHIER `→ mcp-google-analytics-minisite-sa-key` (build via le Dockerfile de `mcp-google-analytics-service`). Statut ✅.
- **mcp-google-search-console-service** — CONFIG : `GOOGLE_APPLICATION_CREDENTIALS=/secrets/gsc-credentials.json` ; `GSC_CREDENTIALS_PATH=/secrets/gsc-credentials.json` ; `GSC_SKIP_OAUTH=true` ; `GSC_SITE_URL=https://www.hellopro.fr` ⚠️ *[à confirmer avant cutover]*. SECRET-FICHIER : `/secrets/gsc-credentials.json → mcp-gsc-sa-key`. Statut ✅.

**Fronts / HTML**
- **nextjs-conseils-hp** — CONFIG : aucune (build-time). Egress **all-traffic** (appelle ECRITEL). Override 1Gi. SECRETS : `CONSEILS_API_TOKEN→nextjs-conseils-hp-api-token` (dédié). Statut ✅.
- **api-html-recherche** — CONFIG : `JWT_ALGO=HS256` ; `JWT_AUDIENCE=https://rag.hellopro.eu` ⚠️ *[à confirmer]*. Egress **all-traffic**. Override cpu-boost. SECRETS : `JWT_SECRET→platform-jwt-secret`. Statut ✅ (reliquat sécu starlette = F-HP-SEC-015, hors env).

**Utilitaires / divers**
- **crawler-monitor-backend** — CONFIG : aucune. Ingress **internal** + **IAM** (`allow_unauthenticated=false`). SECRETS : `REDIS_URL→platform-redis-url` ; `JWT_SECRET→platform-jwt-secret` ; `ADMIN_PASSWORD_HASH→crawler-monitor-admin-password-hash` (dédié, scrypt). Gate actif (Go). Statut ✅.
- **api-ingestion** — CONFIG : aucune. SECRETS : **`RABBITMQ_URL→platform-rabbitmq-url-dev`** (⚠️ broker **DEV** — shadow écrit en dev ; **basculer sur `platform-rabbitmq-url` au cutover**). Statut ✅ (dev).
- **api-comparaison-texte** — CONFIG : aucune. SECRETS : aucun. Statut ✅.
- **api-detection-langue-fr** — CONFIG : `CAMOUFOX_ENABLED=false` ; `BROWSER_SEMAPHORE_SIZE=2` ; `ADMISSION_MAX_SLOTS=4`. Override cpu=2/2Gi/boost (Chromium). SECRETS : `APIFY_PROXY→api-detection-langue-fr-apify-proxy` (dédié). Statut ✅ (F-HP-MIG-001 Chromium/Camoufox).
- **content-extractor-api-service** — CONFIG : `LOG_LEVEL=info` ; `MAX_PAYLOAD_SIZE_MB=10`. SECRETS : aucun. Statut ✅.
- **image-comparison-service** — CONFIG : `MAX_CONCURRENT_JOBS=2`. Override 1Gi + cpu-boost. SECRETS : `REDIS_URL→platform-redis-url`. ⚠️ cutover : compteur Redis partagé `comparator:running_count` à isoler. Statut ✅.

### B.3 — Points de vigilance Lot 1 (à traiter avant/au cutover)
- **Bascule dev→prod** : `api-ingestion` (`platform-rabbitmq-url-dev`→prod) ; `[BASE-VECT]` `ZILLIZ_URI`/`ZILLIZ_URI_DEV` (Milvus dev→`10.0.1.51`) ; `NEO4J_URI` (déjà pointé `10.0.1.218`, valider prod) ; `RABBITMQ_URL` partagé de la famille RAG (`platform-rabbitmq-url` = à vérifier dev vs prod).
- **Valeurs `[à confirmer]`** : `GSC_SITE_URL` (search-console), `JWT_AUDIENCE` (api-html-recherche).
- **Secrets placeholder** (F-HP-SEC-008) à alimenter en réel au cutover : `platform-key-webhook`, `api-rest-milvus-key-webhook`, tokens gateway/SSO. Les clés API externes (OPENAI/GEMINI/…) sont réelles.
- **Secrets dédiés** (hors nommage `platform-*`) : `api-rest-milvus-key-webhook`, `nextjs-conseils-hp-api-token`, `crawler-monitor-admin-password-hash`, `api-detection-langue-fr-apify-proxy`, `mcp-*-api-key(-id/-secret)`, `mcp-google-*-sa-key`, `mcp-gsc-sa-key`.
- **ADC** : les 3 Google MCP montent une clé SA en fichier → migrer vers Workload Identity (F-HP-SEC-006).
- **Egress `all-traffic`** (ECRITEL, IP NAT `35.233.35.8`) : 6/27 (api-classification, graph-rag ×3, nextjs-conseils-hp, api-html-recherche) — cf. Annexe E de `cutover-checklist.md`.

## §B — Lot 2 : GKE (42 déploiements = 34 consumers + 8 non-consumers, 2026-09-14)

> Source = manifests `infra-microservices/infra-gke-cluster/manifest/apps/<svc>/22-deployment.yaml` + `*-secret*.template.yaml` sur `features/infra-gcp-prod` (branche **locale non poussée**). Namespace **`apps-microservices`**. Tous en **`replicas: 1`**. Images `europe-west1-docker.pkg.dev/hellopro-rag-project/hellopro/<svc>:s004-shadow-v1` (consumers) ou `:shadow-v*` (non-consumers). Pattern : `[[reference_gke_consumer_pattern]]`.

**Profils communs GKE** :
- **`[GKE-BASE]`** (DNS in-cluster, cf. F-HP-MIG-002) : broker **DEV** `rabbitmq-i2-internal.default.svc.cluster.local:5672` (ClusterIP 10.0.77.31 → broker DEV 10.0.1.217, **jamais** prod 10.0.1.216) · Milvus **DEV** `my-release-milvus.default.svc.cluster.local:19530` (10.0.1.59) · Qdrant `qdrant.default.svc.cluster.local:6333` (10.0.1.237, legacy → écrit en Milvus) · Redis `redis.default.svc.cluster.local:6379` (10.0.1.220). ⚠️ **bascule dev→prod au cutover** pour broker + Milvus.
- **`[GKE-SECRET]`** : les env sensibles viennent d'un `secretKeyRef` → Secret K8s `<svc>-rabbitmq` (clé `rabbitmq-url`) ou `<svc>-secrets`/`<svc>-*-secret` (multi-clés), **seedé au déploiement via `kubectl create secret` depuis SM `platform-*-dev`**. Les templates versionnés ne contiennent que des **placeholders** (`amqp://<USER>:<PASSWORD>@…`) — sauf exceptions plaintext ci-dessous (B2.3).
- **`[ENABLER]`** : identique au Lot 1 (proxy gRPC→GPU `10.11.0.2:15051-15058`).
- **Placeholders shadow** (F-HP-SEC-008) : clés LLM / `HP_TOKEN` / `KEY_WEBHOOK` sont des **valeurs en clair factices** (`shadow-placeholder-not-a-real-*`) dans les Deployments → **valeurs réelles injectées au cutover**.

### B2.1 — Consumers (34)

**QC — enrichissement/génération (7)** — pas de port ni probe (Option B, F-HP-OBS-002) ; ressources défaut ; SECRETS `RABBITMQ_URL→qc-<...>-rabbitmq/rabbitmq-url` ; CONFIG = clé LLM + `HP_TOKEN` (placeholders).

| Service | LLM (CONFIG placeholder) |
|---|---|
| QC-caracterisation | `DEEPSEEK_API_KEY` + `HP_TOKEN` |
| QC-enrichissement / -equivalence / -generation-caracteristiques / -generation-question1 / -generation-question2aN / -generation-valeurs | `GEMINI_API_KEY` + `HP_TOKEN` |

*(secret K8s `qc-generation-question2an-rabbitmq` = nom normalisé en minuscules).*

**Writers Milvus/Qdrant (5)** — port `8530`, probe `tcpSocket:8530`, ressources défaut. CONFIG `[GKE-BASE]` Milvus (+ Qdrant sauf `document-*`). SECRETS 4 clés → `<svc>-secrets/{rabbitmq-url,redis-url,zilliz-user,zilliz-password}`.

| Service | CONFIG | Notes |
|---|---|---|
| product-database-qdrant-service | ZILLIZ (Milvus) + QDRANT | ✅ **template de secret présent** |
| di-database-qdrant-service | ZILLIZ + QDRANT | ⚠️ **pas de template** de secret dans le repo |
| echange-database-qdrant-service | ZILLIZ + QDRANT | ⚠️ **pas de template** |
| website-database-qdrant-service | ZILLIZ + QDRANT | ⚠️ **pas de template** |
| document-database-qdrant-service | ZILLIZ (Milvus only, **pas de QDRANT**) | ⚠️ **pas de template** |

**Processors (4)** — port `8530`, probe `tcpSocket:8530`. SECRETS `RABBITMQ_URL→<svc>-rabbitmq/rabbitmq-url` (sauf website = secret multi-clés).
- product-processor-service — ressources défaut. ⚠️ **secret `product-processor-rabbitmq` pointe l'IP LB DEV `@10.0.1.217:5672`** (pilote antérieur à F-HP-MIG-002 DNS ; tous les autres utilisent le DNS in-cluster).
- echange-processor-service / devis-processor-service — ressources défaut, broker DNS.
- website-processor-service — ressources **req 250m/512Mi, lim 1000m/1Gi** (Trafilatura). SECRETS `RABBITMQ_URL / REDIS_URL → website-processor-secrets/{rabbitmq-url,redis-url}`.

**graph-rag processors (8)** — ressources défaut ; SECRETS `RABBITMQ_URL→<svc>-rabbitmq/rabbitmq-url` ; Neo4j atteint **via proxy gRPC** (pas de `NEO4J_*` direct, write-E2E différé cutover).

| Service | port/probe | CONFIG `[ENABLER]` |
|---|---|---|
| graph-rag-categorie-processor | 8570 | `GRAPH_DATABASE_SERVICE_URL=…:15056` |
| graph-rag-etl-processor | 8564 | `…:15056` |
| graph-rag-fournisseur-processor | 8572 | `…:15056` |
| graph-rag-produit-processor | aucun (Option B, metrics 8560 commenté) | `…:15056` |
| graph-rag-llm-extractor-processor | 8561 | aucun (clé DeepSeek vide → cutover) |
| graph-rag-normalize-unite-processor | 8562 | `NORMALIZATION_SERVICE_URL=…:15057` |
| graph-rag-normalize-unite-retry-processor | 8564 | `…:15057` + `MILVUS_SERVICE_URL=…:15055` + `GRAPH_DATABASE_SERVICE_URL=…:15056` |
| graph-rag-semantique-vigil-processor | 8563 | `EMBEDDING_SERVICE_URL=…:15052` + `MILVUS_SERVICE_URL=…:15055` |

**prix (5)** — ressources défaut ; SECRETS `RABBITMQ_URL→prix-<...>-rabbitmq/rabbitmq-url` (sauf milvus-processor).
- prix-caracterisation / prix-extraction-devis / prix-extraction-message / prix-extraction-produits — pas de port/probe (Option B). CONFIG = LLM + `HP_TOKEN` placeholders (caracterisation = DeepSeek sans clé Gemini ; les 3 extraction = `GEMINI_API_KEY`+`HP_TOKEN`). Milvus lazy (ZILLIZ ajouté au cutover pour caracterisation).
- prix-milvus-processor — port `8010`, probe `tcpSocket:8010`. Writer Milvus. CONFIG `[GKE-BASE]` Milvus. SECRETS `ZILLIZ_USER / ZILLIZ_PASSWORD / RABBITMQ_URL → prix-milvus-processor-secrets/{zilliz-user,zilliz-password,rabbitmq-url}` (template présent).

**embedding / gRPC-GPU + transverses (5)** — SECRETS `RABBITMQ_URL→<svc>-rabbitmq/rabbitmq-url` (sauf deepseek/webhook = pas de broker).
- embedding-service — port `8530`, probe `tcpSocket:8530`. CONFIG `EMBEDDING_SERVICE_URL=…:15052`.
- template-llm-service — port `8530`, probe `tcpSocket:8530`. CONFIG `LLM_SERVICE_URL=…:15051`. *(gabarit/POC — présent dans les manifests.)*
- nettoyage-bruit-ocr-service — pas de port/probe (Option B). CONFIG `LLM_SERVICE_URL=…:15051`.
- deepseek-metrics-collector-service — pas de port/probe ; ressources req 50m/128Mi. CONFIG `DEEPSEEK_METRICS_COLLECTOR_URL=http://deepseek-metrics-sink-placeholder.apps-microservices.svc.cluster.local:8500/v1/log-metrics` (sink placeholder). **Pas de secret** (forward HTTP).
- webhook-service — pas de port/probe ; ressources req 50m/128Mi. CONFIG `KEY_WEBHOOK=shadow-placeholder-not-a-real-key` (HMAC, placeholder F-HP-SEC-008 ; cibles BO-PHP statiques dans le code, cutover). **Pas de secret** (broker via env ? non — consumer pur, broker au cutover).

### B2.2 — Non-consumers (8) : B1 cluster gateway + B3 always-on + infra

> Documentés pour complétude (env label = `shadow`). Détail patterns : [[reference_mcp_gateway_shadow_gotchas]], [[reference_b3_always_on_shadow]].

**B1 — cluster gateway (4)** — tous branchés sur `gateway-mysql-shadow` (jamais MySQL VM prod).
- **api-gateway-go** — port `8500`, probe `tcpSocket:8500`, runAsNonRoot/65532. CONFIG `MYSQL_HOST=gateway-mysql-shadow.apps-microservices.svc.cluster.local ; MYSQL_PORT=3306 ; MYSQL_USER=gateway_user ; MYSQL_DB=gateway_db ; REDIS_URL=redis://redis.default…:6379/15 ; GATEWAY_USE_CATALOG=false ; JWT_ALGO=HS256 ; SECURE_COOKIE=false`. SECRETS `MYSQL_PASS / JWT_SECRET / GATEWAY_ADMIN_KEY → api-gateway-go-shadow-secret/*`. ⚠️ `mysql-pass=gateway_pass` **littéral** (F-HP-SEC-004). JWT/admin-key réels au cutover.
- **mcp-gateway-service** — port `8592`, probe `tcpSocket:8592` (route `/health` morte). CONFIG `MCP_GATEWAY_PORT=8592 ; AUTH_ENABLED=true ; SSO_ENABLED=false ; ADMIN_EMAILS=<admin@org>`. SECRETS `MYSQL_DSN / JWT_SECRET / ENCRYPTION_KEY → mcp-gateway-service-shadow-secret/*`. ⚠️ `mysql-dsn` littéral (embarque `gateway_pass`).
- **mcp-zoho-service** — port `8596`, probe `tcpSocket:8596`. CONFIG `ZOHO_ROUTER_PORT=8596 ; ZOHO_STUB_SERVER_ID=<uuid> ; ZOHO_SELF_URL=http://mcp-zoho-service:8596`. SECRETS `MYSQL_DSN / ENCRYPTION_KEY / ZOHO_GATEWAY_TOKEN → mcp-zoho-service-shadow-secret/*`. ⚠️ `mysql-dsn` littéral (`gateway_pass`).
- **mcp-google-templates-runner** — port `8595`, probe `httpGet /admin/health:8595`, runAsNonRoot/1000, command override `sh -c` (contourne entrypoint CRLF). CONFIG `MCP_GATEWAY_URL=http://mcp-gateway-service:8592`. SECRETS `MCP_GATEWAY_ADMIN_TOKEN / RUNNER_ADMIN_TOKEN → mcp-google-templates-runner-shadow-secret/*` (placeholders `<GENERATED_HEX_24>`).

**B3 — always-on (3)** — `replicas 1`, backends non branchés en shadow.
- **graph-rag-api-admin-service** — ports `8527/http` + `8565/metrics`, probe `httpGet /health:8527`. **Aucun env** (Neo4j prod bolt + gRPC 15055-15058 câblés au cutover). Pas de secret.
- **graph-rag-dlq-manager** — port `8520`, probe `httpGet /:8520`. SECRETS `RABBITMQ_URL→graph-rag-dlq-manager-rabbitmq/rabbitmq-url`. ⚠️ **connect broker au boot** (broker DEV joignable requis).
- **dlq-manager-service** — port `8560`, probe `httpGet /:8560`, runAsNonRoot/1001. **Aucun env** (ES + RabbitMQ non câblés). ⚠️ boucle 60s qui **écrit/auto-archive ES** une fois câblé (cutover-critique).

**Infra (1)**
- **gateway-mysql-shadow** — `mysql:8.0` public, `strategy Recreate`, PVC `gateway-mysql-shadow-data`, port `3306`, probe `tcpSocket:3306`. SECRETS `MYSQL_ROOT_PASSWORD / MYSQL_DATABASE / MYSQL_USER / MYSQL_PASSWORD → gateway-mysql-shadow-secret/*`. ⚠️ `mysql-user=gateway_user`, `mysql-database=gateway_db`, `mysql-password=gateway_pass` **littéraux** (F-HP-SEC-004 ; DB jetable isolée, copie de `gateway_db`).

### B2.3bis — Secrets : état au 2026-09-16

- ✅ **Plus aucun secret en clair** dans les manifestes du namespace. Les 22 dernières variables (`GEMINI_API_KEY` ×9, `HP_TOKEN` ×11, `DEEPSEEK_API_KEY`, `KEY_WEBHOOK`) réparties sur **12 déploiements** (7 QC + 4 prix + webhook-service) sont passées en `valueFrom.secretKeyRef` vers un secret **partagé** `platform-llm-hp-secrets` (clés `gemini-api-key`, `deepseek-api-key`, `hp-token`, `key-webhook`). Commit infra `93896bad`, appliqué live, 12/12 pods `Running`.
- Le secret porte encore les **valeurs placeholder** : c'est volontaire. Injecter le vrai `KEY_WEBHOOK` avant le cutover ferait **signer et POSTer de vrais webhooks HMAC vers le BO PHP depuis le shadow**. Reseed des vraies valeurs à **H1** seulement.
- Secret **partagé** plutôt que par service : la même clé Gemini vit dans 9 déploiements — une rotation = une écriture au lieu de neuf.
- ⚠️ `platform-key-webhook` et `api-rest-milvus-key-webhook` ont le **même SHA-256** : le secret « dédié » est une copie à l'identique. Deux entrées ne se justifient que pour une rotation indépendante.
- ⚠️ Ces deux clés font **10 caractères** — court pour une signature HMAC. Rotation vers une clé de longueur correcte à coordonner avec le BO PHP **après** le cutover.

### B2.3 — Points de vigilance Lot 2 (cutover)
- **Bascule dev→prod obligatoire pour CHAQUE consumer** : re-seed / re-pointer le broker (`<svc>-rabbitmq` → prod `10.0.1.216`) + Milvus (`zilliz-user/password` writers → Milvus prod `10.0.1.51`). Aucun consumer ne pointe prod aujourd'hui (voulu).
- ⚠️ **product-processor-service** : secret sur IP LB DEV `10.0.1.217` (≠ DNS in-cluster des autres) — harmoniser au DNS ou re-pointer prod au cutover.
- ⚠️ **4 writers sans template de secret versionné** (di / document / echange / website `-database-qdrant-secrets`) → procédure de création **non tracée dans le repo** = risque reproductibilité/cutover → **F-HP-IaC-003** (générer les 4 templates placeholder + vérifier les clés live + runbook seed en Annexe D.3).
- **Plaintext committé** `gateway_pass` (F-HP-SEC-004) dans 4 templates (`gateway-mysql-shadow`, `api-gateway-go`, `mcp-gateway-service`, `mcp-zoho-service`) — n'authentifie que la DB shadow jetable, mais réel en clair versionné → à rotationner + retirer au cutover.
- **Placeholders shadow** (F-HP-SEC-008) à alimenter au cutover : clés LLM (QC, prix, graph-rag-llm-extractor), `HP_TOKEN` (QC, prix), `KEY_WEBHOOK` (webhook-service), gateway JWT/ENCRYPTION_KEY/admin-key/zoho-token, runner tokens.
- **Boot-coupling** : `graph-rag-dlq-manager` (broker au boot), `dlq-manager-service` (boucle d'archivage ES destructrice), à câbler prudemment.
- **Label `environment`** : les consumers S004 portent `environment: prod` alors qu'ils sont en shadow/DEV → **incohérence cosmétique** qui trompe les sélecteurs Prometheus. À corriger (ou acter) avant industrialisation.
- **ADMIN_EMAILS** (mcp-gateway) = config en clair (email admin), pas un secret.

## §B — Lot 3 (restant)
- **Lot 3 — non encore portés** : account-service back/front, fronts B2 (SSO : redis-client-frontend, crawler-monitor-frontend, mcp-gateway-frontend), différés (prix-siteweb, image-download, image-cdn), mcp-neo4j (différé) → valeurs à définir au portage/cutover.

---

## Statut & prochaines étapes
- [x] §A catalogue global (ancré sur `env_model`, 24 secrets → SM confirmés)
- [x] §B Lot 1 — 27 CR portés (extraction wrappers, 2026-09-14 : synthèse + config/secrets par service + vigilances)
- [x] §B Lot 2 — GKE 42 déploiements (34 consumers + 8 non-consumers B1/B3/infra, 2026-09-14 : familles + config/secrets + vigilances dev→prod)
- [ ] §B Lot 3 — services non portés (au fil du portage / cutover)
- [ ] Réconciliation : variables `.env` **non couvertes** par un service (drop ?) + secrets **placeholder** à alimenter en réel (F-HP-SEC-008, au cutover)
