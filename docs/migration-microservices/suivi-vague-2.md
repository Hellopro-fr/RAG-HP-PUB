# Suivi de la vague 2 — actions, adresses, demandes externes

> Tableau de bord vivant de la vague 2. Le **pourquoi** et le **comment détaillé** sont dans [`plan-vague-2.md`](plan-vague-2.md) ;
> ici, on coche. Mis à jour par le DSO après chaque action, relu à chaque point d'équipe.
> Les numéros d'action (0.1, a.2…) sont ceux du plan.
> **Par lot, comme en vague 1** : procédure commune [`procedure-bascule-route-http.md`](procedure-bascule-route-http.md) · fiches [`lots/V2-a1.md`](lots/V2-a1.md), [`V2-a2`](lots/V2-a2.md), [`V2-a3`](lots/V2-a3.md), [`V2-b`](lots/V2-b.md), [`V2-c`](lots/V2-c.md), [`V2-d`](lots/V2-d.md) · rapports par service dans [`rapports/`](rapports/).

## Légende

⬜ à faire · 🔄 en cours · ✅ fait · ❌ bloqué · ⏭️ reporté / sans objet · ↩️ rollback joué

---

## 0. État des lots

> **Le tableau qui dit où en est chaque lot.** Mis à jour à chaque geste. Détail du déroulé : la feuille de lot de chaque fiche.

| Lot | Contenu | Aiguillage | Date | Statut | Bascule | Obs. 24 h | Décision J+1 |
|:--:|---|---|---|---|---|---|---|
| **V2-a1** | comparaison-texte, optimize, detection-langue, content-extractor (P4) | routes `.env.url` | lun 5/10 → mar 6/10 | 🔄 **4/4 routes basculées** : comparaison 05/10 15:23 (✅ validée), optimize 06/10 09:30, detection 11:18, extractor 11:42 | comparaison : 8 min (attente du scan du catalogue) | | |
| **V2-a2** | chat-llm, embedding HTTP, graph-rag recherche ×3 (P4) | routes `.env.url` | mer 7/10 | 🔄 **5/5 routes basculées** 07/10 (embedding, graph-rag ×3 à 09:27, chat-llm à 09:38 en `deepseek-v4-flash`), preuves OK ; tests devs en attente | ~1 min par lot (`rescan`) | | |
| **V2-a3** | recherche, classification, rest-milvus, ingestion, prix-traitement (P4) | routes `.env.url` | proposé jeu 8/10 | ⬜ P0 à faire ; correctif `localhost` rest-milvus (dev) | | | |
| **V2-b** | 8 serveurs MCP (P5) | lignes `mcp_servers` | après V2-a3 | ⬜ script `mcp_servers` à écrire | | | |
| **V2-c** | gateway B1 + B3, comparateur d'images (P2, P3, ex-L7) | vhosts nginx `api.`, `mcp.` + routes | sem. du 12/10, journée dédiée | ⬜ script nginx (0.22) à écrire | | | |
| **V2-d** | SSO et fronts : `login.`, `rag.`, `conseils`, `cmf.` (P6-P8) | vhosts nginx | sem. du 12/10, après V2-c | ⬜ | | | |
| *V2-e* | *stockage images et crawler — chantier, pas une bascule* | — | sem. du 19/10 | ⬜ | | | |
| *Fin* | *DNS Gandi en une intervention du titulaire (décision 10)* | A Gandi | fin de vague | ⬜ | | | |

Répartition de la priorité **P4** (16 services) : 14 dans V2-a1 / a2 / a3 ; `image-comparison-service` dans V2-c (route `/comparator` du `reverse-proxy`) ; `crawler-monitor-backend` dans V2-d (avec son front).

## 0bis. État des services

> Un service = une ligne. **Jumeau VM** : `UP` (sert encore, ou repli) · `RÉSERVE` (arrêté, jamais supprimé, décision 4). **Cible** : `shadow` (aucun trafic) · `PROD` (reçoit le trafic). Deux validations : DSO (technique) et dev (parcours réel).

| Lot | Service VM | Cible (nom exact) | Aiguillage | Jumeau VM | Cible | Basculé le | Validé DSO | Validé dev | Obs. 24 h | Notes |
|:--:|---|---|---|:--:|:--:|---|---|---|:--:|---|
| V2-a1 | `api-comparaison-texte-service` | CR `api-comparaison-texte` | `SERVICE_COMPARAISON_TEXTE` | UP | **PROD** | 05/10 12:15 UTC (effectif 12:23:33, scan du catalogue) | ✅ DSO 05/10 (destination prouvée) | ⬜ | ⬜ | P1 ✅ 14:41 ; P2 ✅ 15:15 ; P3 ✅ 15:32 (0 requête sur le jumeau) ; relevé 17h ✅ ; nuit ✅ (18 h : 0 erreur, jumeau 0 requête) ; **GO technique J+1** ; P4 dev ✅ 06/10 (OK ; payload absent des logs = comportement d'origine) |
| V2-a1 | `optimize-service` | CR `optimize-service` | `SERVICE_OPTIMIZE` | UP | **PROD** | 06/10 06:30 UTC (apply + `rescan`) | ✅ DSO 06/10 (preuve : jumeau 0) | ⬜ | ⬜ | ~1 500 à 5 000 req./jour, 0 erreur sur 24 h côté VM (référence) |
| V2-a1 | `api-detection-langue-fr-service` | CR `api-detection-langue-fr` | `SERVICE_DETECTION_SITE_FR` | UP | **PROD** (révision `00006-gq8`, modèle inclus) | 06/10 08:18 UTC → rollback 07/10 08:54 → **rebascule 07/10 09:31 UTC** | ✅ DSO 07/10 (parité directe sans cache) | ⬜ | ⬜ | code rapatrié 02/10 ; jumeau UP (appelé par `crawler-service`) |
| V2-a1 | `content-extractor-api-service` | CR `content-extractor-api-service` | `SERVICE_EXTRACTOR` | UP | **PROD** | 06/10 08:42 UTC (apply + `rescan`) | ✅ DSO 06/10 (preuve) | ⬜ | ⬜ | code + `common_utils` rapatriés 02/10 ; jumeau UP (`crawler-service`) |
| V2-a2 | `api-chat-llm-service` | CR `api-chat-llm` | `SERVICE_CHAT` | UP | **PROD** 07/10 06:38 UTC | | | | ⬜ | |
| V2-a2 | `api-embedding-service` | CR `api-embedding-service` | `SERVICE_EMBEDDING` | UP | **PROD** 07/10 06:27 UTC | | | | ⬜ | ≠ `embedding-service` (L6) |
| V2-a2 | `graph-rag-api-recherche-service` | CR `graph-rag-api-recherche-service` | `SERVICE_GRAPH` | UP | **PROD** 07/10 06:27 UTC | | | | ⬜ | |
| V2-a2 | `graph-rag-api-recherche-optim-service` | CR `graph-rag-api-recherche-optim-service` | `SERVICE_GRAPHOPTIM` | UP | **PROD** 07/10 06:27 UTC | | | | ⬜ | |
| V2-a2 | `graph-rag-api-recherche-rust-service` | CR `graph-rag-api-recherche-rust-service` | `SERVICE_GRAPHRUST` | UP | **PROD** 07/10 06:27 UTC | | | | ⬜ | sortie NAT statique |
| V2-a3 | `api-recherche-service` | CR `api-recherche` | `SERVICE_SEARCH` | UP | shadow | | | | ⬜ | |
| V2-a3 | `api-classification-service` | CR `api-classification` | `SERVICE_CLASSIFICATION` | UP | shadow | | | | ⬜ | 10 réplicas VM ; jumeau UP jusqu'à V2-b |
| V2-a3 | `api-rest-milvus-service` | CR `api-rest-milvus` | `SERVICE_REST_MILVUS` | UP | shadow | | | | ⬜ | correctif `localhost` avant |
| V2-a3 | `api-ingestion-service` | CR `api-ingestion` | `SERVICE_INGESTION` | UP | shadow | | | | ⬜ | écrit (broker prod à câbler) |
| V2-a3 | `prix-traitement` | CR `prix-traitement` | `SERVICE_PRIX_TRAITEMENT` | UP | shadow | | | | ⬜ | |
| V2-b | `mcp-api-recherche-service` | CR `mcp-api-recherche-service` | `mcp_servers` | UP | shadow | | | | ⬜ | après V2-a3 |
| V2-b | `mcp-classification-produit-service` | CR `mcp-classification-produit-service` | `mcp_servers` | UP | shadow | | | | ⬜ | |
| V2-b | `mcp-google-analytics-service` | CR `mcp-google-analytics-service` | `mcp_servers` | UP | shadow | | | | ⬜ | |
| V2-b | `mcp-google-analytics-minisite-service` | CR `mcp-google-analytics-minisite-service` | `mcp_servers` | UP | shadow | | | | ⬜ | |
| V2-b | `mcp-google-search-console-service` | CR `mcp-google-search-console-service` | `mcp_servers` | UP | shadow | | | | ⬜ | |
| V2-b | `mcp-semrush-service` | CR `mcp-semrush-service` | `mcp_servers` | UP | shadow | | | | ⬜ | commit `poc` seul 02/09 |
| V2-b | `mcp-ringover-service` | CR `mcp-ringover-service` | `mcp_servers` | UP | shadow | | | | ⬜ | |
| V2-b | `mcp-leexi-service` | CR `mcp-leexi-service` | `mcp_servers` | UP | shadow | | | | ⬜ | |
| V2-c | `api-gateway-go-service` | GKE `api-gateway-go` | vhost `api.` | UP → arrêté au geste | shadow | | | | ⬜ | |
| V2-c | `mcp-gateway-service` | GKE `mcp-gateway-service` | vhost `mcp.` | UP → arrêté au geste | shadow | | | | ⬜ | |
| V2-c | `mcp-zoho-service` | GKE `mcp-zoho-service` | `mcp_servers` | UP | shadow | | | | ⬜ | |
| V2-c | `mcp-google-templates-runner` | GKE `mcp-google-templates-runner` | URL `mcp-gateway` | UP | shadow | | | | ⬜ | |
| V2-c | `graph-rag-api-admin-service` | GKE `graph-rag-api-admin-service` | `SERVICE_GRAPHADMIN` | UP | shadow | | | | ⬜ | |
| V2-c | `graph-rag-dlq-manager-service` | GKE `graph-rag-dlq-manager` | `SERVICE_GRAPHDLQ` | UP | shadow | | | | ⬜ | |
| V2-c | `image-comparison-service` | CR `image-comparison-service` | `SERVICE_IMAGE_COMPARATOR` | UP | shadow | | | | ⬜ | compteur Redis à isoler |
| V2-d | `account-service-backend` | CR `account-service-backend` | URL appelants | UP | shadow | | | | ⬜ | |
| V2-d | `account-service-frontend` | CR `account-service-frontend` | vhost `login.` | UP | shadow | | | | ⬜ | |
| V2-d | `api-html-recherche-service` | CR `api-html-recherche` | vhost `rag.` | UP | shadow | | | | ⬜ | |
| V2-d | `nextjs-conseils-hp` | CR `nextjs-conseils-hp` | vhost `nextjs-conseils.` | UP | shadow | | | | ⬜ | contenus identiques exigés |
| V2-d | `crawler-monitor-backend` | CR `crawler-monitor-backend` | à qualifier | UP | shadow | | | | ⬜ | |
| V2-d | `redis-client-frontend`, `crawler-monitor-frontend`, `mcp-gateway-frontend` | à créer | vhost `cmf.`, front `mcp.` | UP | — | | | | ⬜ | build racine, `@hellopro/auth` |

**Nouveaux services trouvés sur la VM le 07/10** (présents dans `features/poc`, absents de `prod` et de l'inventaire ; décision user : *s'ils sont déployés sur la VM, ils sont à migrer*, code à rapatrier `poc` → `prod` d'abord) :

| Service | État VM (07/10) | Nature | Cible proposée | Lot | Préalables |
|---|---|---|---|---|---|
| `mcp-hellodata-service` | UP 2 h | MCP HTTP (Go, module autonome) | Cloud Run interne, `min=1`, **`max=1`** (liens CSV en mémoire), **sortie `all-traffic`** (BO et www chez Ecritel) | **V2-a4** puis ligne `mcp_servers` | P0 07/10 : `HELLODATA_BASE_URL=https://bo.hellopro.fr/admin/mcp/hellodata`, `HELLODATA_WEBHOOK_URL=https://www.hellopro.fr/partenaires_externes/mcp/hellodata`, `HELLODATA_PUBLIC_URL` **vide** ; 2 secrets à créer en SM (`HELLODATA_TOKEN` `8052386a…`, `HELLODATA_WEBHOOK_TOKEN` `70a717c5…`, 64 car.) ; rapatriement (dossier seul, aucune lib) |
| `mcp-normalize-unite-service` | UP 4 h | MCP (Go), client gRPC | Cloud Run + connecteur (`/mcp`) | plan standard (décision équipe 07/10) | rapatriement ; **unit-registry reste sur la VM** → nouveau port d'enabler pour `50059` (gRPC) + règle de pare-feu, comme `15055-15058` |
| `unit-registry-service` | UP 4 h | gRPC + publication RabbitMQ (boucle 1 s), MySQL `normalization_db` | **reste sur la VM** (service temporaire, décision équipe 07/10) | — | code rapatrié dans `prod` quand même |
| `mcp-template-neo4j-service` | UP 6 j | lanceur de processus MCP (ports 15100-15199) | **reste sur la VM** (service temporaire, décision équipe 07/10) | — | code rapatrié dans `prod` quand même |
| `agent-service` | UP 45 h, `0.0.0.0:8597` | API LangGraph **sans auth** | **Cloud Run interne**, route de la gateway comme V2-a (**décision user 07/10 : option A**) | **V2-a4** (avec mcp-hellodata) | appelant identifié : **BO chez Ecritel** via `https://api.hellopro.eu/agent-service/agents/{code}/run` (route gateway `agent-service`) ; rapatriement ; F-HP-SEC-033 |
| `neo4j_new` | UP 3 sem., `0.0.0.0:7476`/`7689` | base Neo4j 5.15 | **reste sur la VM** (service temporaire, décision équipe 07/10) | — | — |
| `tailscale` (`tailscale-gateway`) | UP 4 sem. | **nœud VPN** sur l'hôte | **reste sur la VM** | — | usage identifié : liaison avec le **VPS OVH qui héberge OpenClaw** ; reste à restreindre les ACL (F-HP-SEC-032) |

**Restent sur la VM pendant la vague** : `dlq-manager-service` (décision 5), `mcp-neo4j-service` (F-HP-SEC-020), `nextjs-formulaire-hp` (décision 3), services P9 / P10 de l'inventaire.

### Rollbacks

| Date | Lot | Service / route | Déclencheur | Durée | Cause | Reprise |
|---|---|---|---|---|---|---|
| 07/10 11:53 | V2-a1 | detection-langue (`SERVICE_DETECTION_SITE_FR`) | warning dev : modèle fastText absent de l'image Cloud Run | ~1 min (`revert` + `rescan`) | modèle monté depuis l'hôte sur la VM, jamais intégré à l'image ; NLP sauté, décisions dégradées mises en cache | image corrigée (modèle intégré, sha256 figé) puis nouvelle bascule |

---

## 1. État des adresses publiques

> **Décision 10 (02/10)** : pendant la vague, l'aiguillage est le **vhost nginx de la VM** (destination changée, DNS inchangé) ; l'enregistrement A Gandi ne change qu'une fois, à la fin, par le titulaire du compte. Colonnes TTL / certificat : à la bascule DNS finale.

Une ligne par adresse. C'est la vue « où en est chaque aiguillage ».

| Adresse | Aujourd'hui | Cible | Aiguillage | Sous-vague | TTL 300 s | Certificat | Basculée le | Validée (J+1) | Jumeau VM |
|---|---|---|---|---|:--:|:--:|---|---|---|
| `api.hellopro.eu` | VM `:8500` | `api-gateway-go` (GKE) | A Gandi | V2-c | ⬜ | ⬜ | | | à arrêter au geste |
| `mcp.hellopro.eu` | VM `:8581` | front MCP (à créer) | A Gandi | V2-c / V2-d | ⬜ | ⬜ | | | |
| `rag.hellopro.eu` | VM `:8550` | Cloud Run `api-html-recherche` | A Gandi | V2-d | ⬜ | ⬜ | | | laissé up |
| `login.hellopro.eu` | VM `:8601` | Cloud Run `account-service-frontend` | A Gandi | V2-d | ⬜ | ⬜ | | | laissé up |
| `cmf.hellopro.eu` | VM `:3002` | front à créer | A Gandi | V2-d | ⬜ | ⬜ | | | laissé up |
| `formulaire.hellopro.eu` | VM `:8579` | Cloud Run `nextjs-formulaire-hp` (shadow) | — | ⏭️ hors vague 2 (décision 3) | — | — | | | reste seul |
| `nextjs-conseils.hellopro.eu` (derrière `conseils.hellopro.fr`) | VM `:8610` | Cloud Run `nextjs-conseils-hp` | A Gandi (± règle Ecritel) | V2-d (après GO PROD) | ⬜ | ⬜ | | | laissé up |
| `dlq.hellopro.eu` | VM `:8585` (`dlq-manager-service`, **UP**) — **restreint aux IP Hellopro depuis le 30/09** (F-HP-SEC-028 atténué) | à décider (décision 5) | — | — | — | — | | | |
| `mep.hellopro.eu` | VM `:8321` | hors migration applicative | — | à qualifier | — | — | | | |

## 2. Routes internes

### Routes de la gateway VM (`.env.url`) — V2-a

| Route | Service | Cible Cloud Run | P0 (URL en dur, secrets, capacité) | Dev testeur | Basculée le | Validée (J+1) |
|---|---|---|:--:|---|---|---|
| `SERVICE_DETECTION_SITE_FR` | détection de langue | `api-detection-langue-fr` (rév. 00005, code rapatrié) | ✅ 02/10 | | | |
| `SERVICE_COMPARAISON_TEXTE` | comparaison de texte | `api-comparaison-texte` (rév. 00008) | ✅ 02/10 | | | |
| `SERVICE_EXTRACTOR` | content-extractor | `content-extractor-api-service` (rév. 00010, code + `common_utils` rapatriés) | ✅ 02/10 | | | |
| `SERVICE_OPTIMIZE` | optimize | `optimize-service` (rév. 00006) | ✅ 02/10 | | | |
| | chat-llm | `api-chat-llm` | ⬜ | | | |
| | embedding HTTP | `api-embedding-service` | ⬜ | | | |
| | graph-rag recherche | `graph-rag-api-recherche-service` | ⬜ | | | |
| | graph-rag recherche optim | `graph-rag-api-recherche-optim-service` | ⬜ | | | |
| | graph-rag recherche rust | `graph-rag-api-recherche-rust-service` | ⬜ | | | |
| `SERVICE_SEARCH` | recherche | `api-recherche` | ⬜ | | | |
| | classification | `api-classification` | ⬜ | | | |
| | rest-milvus | `api-rest-milvus` | ⬜ | | | |
| | ingestion | `api-ingestion` | ⬜ | | | |
| | prix-traitement | `prix-traitement` | ⬜ | | | |

### Serveurs MCP (`mcp_servers`) — V2-b

| Serveur MCP | Cible Cloud Run | Clés / quotas IP `35.233.35.8` | Dev testeur | Basculé le | Validé |
|---|---|:--:|---|---|---|
| mcp-api-recherche | `mcp-api-recherche-service` | ⬜ | | | |
| mcp-classification-produit | `mcp-classification-produit-service` | ⬜ | | | |
| mcp-google-analytics | `mcp-google-analytics-service` | ⬜ | | | |
| mcp-google-analytics-minisite | `mcp-google-analytics-minisite-service` | ⬜ | | | |
| mcp-google-search-console | `mcp-google-search-console-service` | ⬜ | | | |
| mcp-semrush | `mcp-semrush-service` | ⬜ | | | |
| mcp-ringover | `mcp-ringover-service` | ⬜ | | | |
| mcp-leexi | `mcp-leexi-service` | ⬜ | | | |
| mcp-neo4j | — (F-HP-SEC-020, reste sur la VM) | ⏭️ | | | |

---

## 3. Actions par sous-vague

### V2-0 — Prérequis (jeu 1/10 → ven 2/10)

| # | Action | Qui | Échéance | Statut | Preuve / commentaire |
|---|---|---|---|:--:|---|
| 0.1 | Revue du plan, décisions, un dev nommé par service | CTO, LEAD, DSO, PROD | jeu 1/10 matin | ✅ | 01/10 : plan validé, devs disponibles à partir du 5/10 |
| 0.2 | Mesures VM : trafic horaire nginx, `dlq.hellopro.eu`, taille des volumes | DSO | jeu 1/10 | ✅ | log `data/cutover/carte-v2-0.log` : `api.` pic 10h-17h UTC, nuit non nulle ; `rag.`, `login.` plats sur 24 h (sondes probables) ; volumes **370 Go** images / **205 Go** crawler ; vhosts publics hors plan : `grafana.`, `n8n-dev.`, `pmyadm.` (phpMyAdmin), `neo4j1.`, `mep.` → 0.16 |
| 0.3 | Load balancer HTTPS prod (back-ends Cloud Run) | DSO | ven 2/10 (`plan`) → `apply` dès les certificats prêts | ⏭️ | IP du LB : ; **reporté à la bascule DNS finale** (décision 10) |
| 0.4 | Certificats par validation DNS (CNAME `_acme-challenge` chez Gandi) | DSO | ven 2/10 (autorisations TF) → CNAME **dès le jeton** (ven 2/10, sinon lun 5/10 après-midi) | ⏭️ ; **reporté à la bascule DNS finale** (décision 10) |
| 0.5 | NEG GKE pour `api.` et `mcp.` rattachés au LB | DSO | ven 2/10 | ⬜ | |
| 0.6 | TTL 300 s sur les 6 adresses | DSO | **dès le jeton** (ven 2/10, sinon lun 5/10 après-midi) | ⏭️ | ≥ 48 h avant V2-c / V2-d (sem. du 12/10) ; voir journal Gandi ; **état au 02/10** : les 6 A = `35.245.31.1`, **TTL 10 800 s (3 h)** (TTL par défaut de la zone) → le TTL 300 s doit être posé **au moins 3 h** avant une bascule DNS ; **reporté à la bascule DNS finale** (décision 10) |
| 0.7 | Cloud Armor en observation sur le LB prod | DSO | ven 2/10 | ⬜ | |
| 0.8 | Liste des URL en dur par service → tickets devs | DSO (liste 1-2/10) → devs (à partir du 5/10) | ven 2/10 (tickets prêts) | ⬜ | conditionne l'ordre de V2-a |
| 0.9 | Test VM → Cloud Run (entrée, authentification) | DSO | jeu 1/10 | ✅ | 01/10 : **OUI** — `api-detection-langue-fr` et `api-comparaison-texte` répondent `200` depuis la VM (démarrage à froid 5-7 s, puis 0,55 s) → **V2-a depuis la gateway VM, comme prévu** ; ⚠️ mais ils répondent aussi **sans authentification**, entrée `all` → audit de tous les Cloud Run avant d'y envoyer du trafic (action 0.18) ; `min instances ≥ 1` nécessaire |
| 0.10 | Runbook HTTP + scripts P1 / bascule / relevés | DSO | ven 2/10 | ⬜ | |
| 0.11 | Message à Ecritel | DSO | jeu 1/10 | ⬜ | voir § 4 |
| 0.13 | Usage réel des services P9 sur la VM (logs 7 jours, appelants, routes `.env.url`) | DSO | jeu 1/10 | ✅ | `api-gateway-service`, `api-model`, `api-chatbot` : **aucun conteneur** sur la VM (rien à faire) ; `graph-rag-api-recherche-service-debug` **UP depuis 4 mois**, appelé seulement par **`api-catalog-service`** (`172.20.0.148`, sondage `/openapi.json`) → aucun usage fonctionnel → **arrêt en réserve** (décision 4), après contrôle de `.env.url` ; `SERVICE_CRAWLING=reverse-proxy:8050/crawler` (VM), `SERVICE_OPTIMOTEUR=10.0.1.240:8570` (**déjà sur GKE**, IP interne) ; **02/10 08:08 UTC : `…-service-debug-1` arrêté en réserve** (`vm_reserve.sh`, route `SERVICE_GRAPHDEBUG` gardée dans `.env.url` jusqu'à V2-c, seuls appels = lecture de documentation) |
| 0.14 | **F-HP-SEC-028** : journal d'accès `dlq.hellopro.eu`, puis fermeture de l'accès public (nginx) | DSO | **30/09 – 1/10, prioritaire** | ✅ | 30/09 12:44 UTC : allowlist 8 IP Hellopro + `deny all` ; `403` hors liste, accès bureau / télétravail / Ecritel OK ; aucune modification ni lecture de messages externe dans le journal |
| 0.16 | Vhosts publics hors plan : `pmyadm.hellopro.eu` (phpMyAdmin), `grafana.`, `n8n-dev.`, `neo4j1.`, `mep.` — contrôle d'accès nginx et journal (même méthode que F-HP-SEC-028) | DSO | jeu 1/10 | ✅ | 01/10 : **aucun contrôle d'accès nginx** sur les 5 ; IP hors liste : pmyadm 97, grafana 128, n8n-dev 169, neo4j1 13, mep 130 ; phpMyAdmin 5.2.3 consulté par des robots (pages de doc, scans `.env`/`.git`) → allowlist `vhost_allowlist.sh` (F-HP-SEC-029) : ✅ **phpMyAdmin fermé 01/10 10:48 UTC** (aucune connexion réussie hors liste dans le journal ; 18 tentatives échouées) ; ✅ **grafana et neo4j1 fermés 01/10 11:53 UTC** ; **mep** : appels `launch_mep` / `claim_mep` **légitimes** (confirmé 01/10 : actions depuis des mobiles) → pas d'allowlist ; ✅ **durci 01/10 14:49 UTC** (`api.php` exige une session : 401 sans session ; 429 après 10 connexions/min/IP) ; ✅ **n8n-dev durci 01/10 12:15 UTC** (option A : 404 sur chemins sensibles, 429 après 10 `POST /rest/login`/min/IP) |
| 0.17 | Dépendances VM ↔ cloud : inventaire des appelants restés sur la VM pour chaque service qui migre (compose, `.env.url`, `mcp_servers`, code) ; règle « jumeau arrêté seulement sans appelant VM » | DSO | ven 2/10 | 🔄 | inventaire initial du compose : plan § 7bis |
| 0.18 | **Audit des Cloud Run** : entrée (`all` / `internal`), appel anonyme possible ou non, pour les ~31 services ; un service appelable sans authentification contourne le contrôle de la gateway | DSO | ven 2/10 | ✅ | 01/10 : **29/31 publics et anonymes** (`all` + `allUsers`, fixés par les wrappers CD), tous à 0 instance minimale → **F-HP-SEC-030** ; trafic 7 j (métrique) : **0 requête sur 27 services**, `image-comparison-service` **9 659** (appelant à identifier) ; ✅ **confinement 01/10 17:28 UTC** : `allUsers` retiré des 24 services sans trafic (audit relu) ; image-comparison = robots (rafales de 404) ; ✅ **lot 2 17:55 UTC** (image-comparison + 4 fronts) → **`allUsers` = 0 sur les 31 services** ; reste : correction des wrappers CD à chaque bascule (sinon le CD rouvre), test d'entrée interne VM / GKE (0.19), journaux Cloud Run absents |
| 0.19 | Test d'entrée **interne** (`internal-and-cloud-load-balancing`) sur un Cloud Run sans trafic, appelé depuis la VM, depuis un pod GKE et depuis internet → cible d'entrée des API de V2-a ; et authentification (jeton) côté gateway si besoin | DSO | ven 2/10 | ✅ | 02/10 07:18 UTC (`cr_test_entree_interne.sh`, `api-detection-langue-fr`) : **internet 404 (fermé), VM 200, pod GKE 200** → **cible A validée** : entrée `internal-and-cloud-load-balancing` + appel anonyme, service remis en état (`all`, `allUsers=0`) ; prérequis : le smoke test du CD doit ignorer toute entrée ≠ `all` (`deploy-cloud-run.yml`) |
| 0.20 | Smoke test du CD Cloud Run : ignorer toute entrée ≠ `all` (`deploy-cloud-run.yml`), prérequis des wrappers V2-a | DSO | ven 2/10 | ✅ | PR `fix/cd-smoke-internal-ingress` mergée 02/10 (gate verte) |
| 0.21 | **Rapatriement `poc` → `prod`** des correctifs urgents (plan § 7quater), **assuré par le DSO** (02/10) : PR detection-langue, PR content-extractor + `common_utils`, avec les réglages cible des wrappers ; information aux devs ([message](demande-rapatriement-poc-prod.md)) | DSO | PR prêtes ven 2/10, merge lun 5/10 matin | ✅ (lot 1) | prérequis de la bascule de ces 2 routes ; comparaison-texte et optimize : rien à rapatrier ; 02/10 : PR detection-langue, content-extractor + `common_utils`, wrappers comparaison / optimize **mergées**, déployées |
| 0.22 | **Script de bascule nginx** d'un vhost VM (destination → Cloud Run / IP interne GKE, sauvegarde, `nginx -t`, `reload`, contrôle, retour arrière) | DSO | avant V2-c | ⬜ | décision 10 |
| 0.15 | Clé SSH ajoutée aux métadonnées **du projet** par `gcloud compute scp` (30/09, utilisateur `deploy`) : décider de la garder ou la retirer (accès à toutes les VM qui acceptent les clés projet) | DSO | fin de vague | ⬜ | |
| 0.12 | Jeton Gandi LiveDNS temporaire (`hellopro.eu` seul, expiration ≈ 23/10) → Secret Manager `gandi-livedns-pat` ; scripts `GET`/`PUT`/`GET` | titulaire Gandi (création), DSO | **ven 2/10 si possible, sinon lun 5/10 après-midi** — [procédure](procedure-jeton-gandi.md) | ⏭️ | révocation prévue en fin de vague ; **02/10** : jeton `migrationdns` recréé avec le droit DNS seul (`hellopro.eu`, expire 01/11), rangé dans Secret Manager ; **mais `hellopro.eu` n'est pas sur LiveDNS** (serveurs `a/b/c.dns.gandi.net` = DNS Gandi classique) → l'API LiveDNS répond « Unknown domain » ; `hellopro.fr`, lui, est sur LiveDNS → décision à prendre (interface Gandi, ou passage de `hellopro.eu` à LiveDNS) ; **décision 10 : jeton inutilisable → à supprimer** (titulaire) avec le secret `gandi-livedns-pat` |

### V2-a — Routes gateway (lun 5 → mar 6/10)

| # | Action | Qui | Échéance | Statut | Preuve / commentaire |
|---|---|---|---|:--:|---|
| a.1 | P0 de chaque service (fiche verte) | DSO | veille | ✅ (lot 1) | 02/10 (`p0_route.sh`, `p0_code.sh`, `p0_diff.sh`) : **comparaison-texte** et **optimize** : code VM = Cloud Run = prod ✅ ; **detection-langue** : `scraper.py` de la VM = `features/poc` (correctif PROD du 24/09 : fuite du pool de navigateurs), **absent de prod** ; **content-extractor** : `config.py` VM = `features/poc` (`RESULT_CACHE_VERSION` v2, 30/09), absent de prod → **rapatriement poc → prod avant bascule** ; Redis absent sur Cloud Run (detection, extractor) ; `min_instances` 0 → 1 ; bibliothèques à comparer ; **02/10 : 4 services prêts** — PR de rapatriement + wrappers mergées, CD vert (smoke ignoré, entrée interne), vérifié : entrée interne, `allUsers`=1, `min`=1, internet 404, VM 200 (0,6 s), code VM = image Cloud Run (detection 60/60, extractor 18/18), Redis prod joint depuis Cloud Run |
| a.2 | Bascule des routes une à une (tableau § 2) | DSO | lun 5 → mar 6/10 | ⬜ | script `bascule_route.sh` (plan / apply / check / revert, écriture en place de `.env.url`, sauvegarde horodatée) |
| a.3 | Test du parcours réel après chaque route | devs | au fil de l'eau | ⬜ | |
| a.4 | Relevés midi / 17h / nuit ; décision J+1 | DSO, LEAD | mer 7/10 9h30 | ⬜ | |

### V2-b — MCP (mer 7/10)

| # | Action | Qui | Échéance | Statut | Preuve / commentaire |
|---|---|---|---|:--:|---|
| b.1 | Dump `mcp_servers` | DSO | mer 7/10 9h | ⬜ | fichier : |
| b.2 | Une ligne `mcp_servers` à la fois (tableau § 2) | DSO | mer 7/10 | ⬜ | |
| b.3 | Test d'un outil par serveur MCP | dev MCP | mer 7/10 | ⬜ | |
| b.4 | Clés tierces et quotas depuis `35.233.35.8` | DSO | mar 6/10 | ⬜ | |

### V2-c — Bloc gateway B1 + B3 (journée dédiée, sem. du 12/10)

| # | Action | Qui | Échéance | Statut | Preuve / commentaire |
|---|---|---|---|:--:|---|
| c.1 | Version gateway VM = image GKE ; parité des 5 jetons | DSO ; LEAD confirme | jeu 8/10 | ⬜ | |
| c.2 | Services K8s, ConfigMap `.env.url`, icônes, sidecar `/comparator` `/crawler`, variables Docker | DSO | jeu 8/10 | ⬜ | |
| c.3 | Dump complet `gateway_db` | DSO | J 9h | ⬜ | fichier / taille : |
| c.4 | Bascule mcp-gateway → zoho, templates-runner → api-gateway-go ; jumeaux arrêtés | DSO | J 9h30-11h | ⬜ | |
| c.5 | A Gandi `api.` et `mcp.` → IP LB | DSO | J 11h | ⬜ | voir journal Gandi |
| c.6 | `graph-rag-api-admin`, `graph-rag-dlq-manager` | DSO | J après-midi | ⬜ | |
| c.7 | Tests fonctionnels gateway et MCP | devs | J | ⬜ | |
| c.8 | Décision J+1 (rollback prêt) | DSO, LEAD | J+1 9h30 | ⬜ | |

### V2-d — SSO et fronts (sem. du 12/10, selon décisions)

| # | Action | Qui | Préalable | Statut | Preuve / commentaire |
|---|---|---|---|:--:|---|
| d.1 | `account-service-backend` sur Cloud Run (`all-traffic`) | DSO | V2-c | ⬜ | |
| d.2 | `login.hellopro.eu` | DSO | d.1 + clients OAuth (devs SSO) | ⬜ | |
| d.3 | `rag.hellopro.eu` | DSO | test de connexion par un dev | ⬜ | |
| d.4 | `cmf.hellopro.eu`, front `mcp.` | devs puis DSO | fronts construits | ⬜ | |
| d.5 | `formulaire.hellopro.eu` | — | — | ⏭️ | hors vague 2 (décision 3 du 30/09) |
| d.6 | `conseils.hellopro.fr` (via `nextjs-conseils.hellopro.eu`) | PROD décide, DSO exécute | GO PROD + réponse Ecritel | ⬜ | |

### V2-e — Stockage (sem. du 19/10)

| # | Action | Qui | Échéance | Statut | Preuve / commentaire |
|---|---|---|---|:--:|---|
| e.1 | Cible GCS pour `image_download_data` et `crawler_data` | DSO propose, CTO valide | sem. du 19/10 | ⬜ | tailles au 01/10 : 370 Go et 205 Go |
| e.2 | Code `image-download`, `image-cdn`, `crawler-service` | devs | à planifier | ⬜ | |
| e.3 | Retrait de l'IP publique VM (plus rien n'y pointe) | DSO + Ecritel | fin de vague | ⬜ | |

---

## 4. Demandes externes

### Ecritel

| Date | Objet | Envoyé par | Statut | Réponse (résumé) |
|---|---|---|:--:|---|
| jeu 1/10 | Règles Apache vers `35.245.31.1` : `conseils.hellopro.fr`, `www.hellopro.fr`, autres (message prêt : plan § 5) | DSO | ⬜ | |

### Journal des modifications Gandi (DSO)

Une ligne par modification, **avant** de la faire (valeur d'origine notée = retour arrière garanti).

| Date / heure | Enregistrement | Type | Avant | Après | TTL | Par | Motif |
|---|---|---|---|---|---|---|---|
| 07/10 11:53 | V2-a1 | detection-langue (`SERVICE_DETECTION_SITE_FR`) | warning dev : modèle fastText absent de l'image Cloud Run | ~1 min (`revert` + `rescan`) | modèle monté depuis l'hôte sur la VM, jamais intégré à l'image ; NLP sauté, décisions dégradées mises en cache | image corrigée (modèle intégré, sha256 figé) puis nouvelle bascule | |

---

## 5. Décisions

Le détail de chaque décision (pourquoi, objectif, options, recommandation, conséquence si on ne tranche pas) : [`plan-vague-2.md` § 6](plan-vague-2.md#6-décisions--pourquoi-objectif-options-recommandation).

| # | Décision | Qui | Échéance | Statut | Décision prise |
|---|---|---|---|:--:|---|
| 1 | Plan et calendrier ; un dev par service P4/P5 | CTO, LEAD | jeu 1/10 | ✅ | **01/10 : plan validé, devs prêts à partir du 5/10** |
| 2 | Bascule de `conseils` (SEO, pages PHP non migrées) | PROD, LEAD | avant V2-d | ✅ | **30/09 : GO reco** — back-end seul ; comparaison préalable Cloud Run / VM, **contenus identiques exigés** |
| 3 | Formulaire Next.js | LEAD | jeu 1/10 | ✅ | **30/09 : hors vague 2** — pas en production, fonctionnalités en cours ; Next 15 non urgent |
| 4 | P9 à trancher (`api-gateway-service`, `api-model`, `api-chatbot`, `…-debug`, `SERVICE_CRAWLING`, `SERVICE_OPTIMOTEUR`) | LEAD | jeu 8/10 | ✅ | **01/10 : règle** — non migré = reste sur la VM : **UP** si utilisé et non migrable, **arrêté en réserve** sinon ; classement par l'action 0.13 ; aucune suppression pendant la vague |
| 5 | `dlq-manager-service` / `dlq.hellopro.eu` | métier, CTO | avant V2-c | ✅ | ⚠️ 30/09 : service **UP depuis 2 mois** sur la VM, **exposé sans authentification** (F-HP-SEC-028 CRITICAL) → **accès fermé aux IP Hellopro le 30/09** (0.14 ✅). Journal : outil **utilisé** (requeue quotidien par le bureau, appels Ecritel) → ✅ **01/10 : on laisse sur la VM d'abord** (UP, restreint aux IP Hellopro) ; migration GKE quand F-HP-SEC-027 est corrigé |
| 6 | Cloud Armor : critères de passage en blocage | RSSI | avant V2-d | ✅ | **30/09 : option A** — observation, blocage adresse par adresse après 7 jours sans faux positif, limite de débit sur `login.` (« la sécurité est importante ») |
| 7 | CD GKE prod (F-HP-IND-005) : calage | CTO | jeu 1/10 | ✅ | **30/09 : GO, progressif** — cadrage 1-2/10, puis **un service par jour**, testé et validé avant le suivant (à partir du 19/10) |
| 8 | Certificats par validation DNS (évolution du module LB) | CTO, DSO | jeu 1/10 | ✅ | **30/09 : GO reco** (Certificate Manager, CNAME Gandi) |
| 10 | **Mécanisme de bascule des entrées publiques** : nginx VM pendant la vague, DNS Gandi en une seule intervention du titulaire à la fin | DSO, user | 02/10 | ✅ | **02/10 : option 1 retenue** (pas d'accès DSO à l'interface Gandi ; `hellopro.eu` en DNS classique) |
| 9 | Jeton API Gandi temporaire plutôt que l'interface | CTO, DSO | jeu 1/10 | ✅ | **30/09 : GO** — le jeton va être créé (action 0.12) |

---

## 6. Journal

| Date | Événement |
|---|---|
| 30/09 | Série des consumers close (GO L6). Inventaire vague 2 : 85 services encore sur la VM. Faits confirmés : DNS `hellopro.fr` / `hellopro.eu` pilotés par nous sur Gandi ; Apache `hellopro.fr` = Ecritel ; `*.hellopro.eu` Gandi → VM directe ; `conseils.hellopro.fr` résout vers le front Ecritel (45.223.103.188) ; vhost VM `nextjs-conseils.hellopro.eu` → `:8610`. Plan et suivi rédigés, à valider le 1/10. Décision 3 prise : formulaire hors vague 2 (pas en production). Détail des décisions ajouté au plan (§ 6). Soir : décisions 2, 6, 7, 8, 9 prises ; 4 = revérifier l'usage sur la VM ; **5 : `dlq-manager-service` UP depuis 2 mois et `dlq.hellopro.eu` exposé sans authentification → F-HP-SEC-028 (CRITICAL)**, mesure immédiate. |
| 01/10 | Réserve embedding levée (L6 entièrement validé). Revue : décision 1 (plan validé, devs à partir du 5/10) et décision 4 (règle « non migré = VM, UP ou arrêté en réserve ») ; décision 5 : **on laisse sur la VM d'abord**. Mesures VM (0.2) et usage P9 (0.13) relevés ; nouvelle règle « un jumeau VM n'est arrêté que sans appelant resté sur la VM » (plan § 7bis, action 0.17) ; 5 vhosts publics hors plan à contrôler (0.16). |
| 01/10 soir | Exposition anonyme des Cloud Run fermée (31/31). Jeton Gandi : ven 2/10 si possible, sinon lun 5/10 après-midi ([procédure](procedure-jeton-gandi.md)) ; seuls les CNAME des certificats et le TTL en dépendent, sans effet sur V2-a / V2-b. |
| 02/10 | 0.19 : la VM et GKE sont vus comme internes par Cloud Run → **V2-a en entrée interne, sans jeton ni code** ; correctif du smoke test CD à faire avant les wrappers. |
| 02/10 | Service debug graph-rag mis en réserve (décision 4). Correctif du smoke test CD préparé (0.20). |
| 02/10 | Constat (confirmé par le user) : des correctifs urgents partent sur la VM par `features/poc` sans passer par `prod`. P0 : comparaison-texte et optimize prêts ; detection-langue et content-extractor attendent le rapatriement (0.21). Nouvelle règle : après bascule, les correctifs vont dans `prod`. |
| 02/10 après-midi | V2-a lot 1 prêt : 3 PR (rapatriement detection-langue, content-extractor + `common_utils`, wrappers comparaison / optimize) mergées et déployées, vérifiées (entrée interne, VM 200, internet 404, code = VM, Redis OK). Script de bascule de route prêt. |
| 02/10 15h | Jeton Gandi reçu et rangé (droit DNS seul). `hellopro.eu` est sur le **DNS Gandi classique**, pas sur LiveDNS : l'API du jeton ne s'applique pas. Photo DNS : 6 A en `35.245.31.1`, TTL 3 h. |
| 02/10 15h30 | **Contrainte** : pas d'accès DSO à l'interface Gandi (droits, informations confidentielles) ; seul le titulaire du compte peut agir. Avec `hellopro.eu` en DNS classique, le jeton ne sert pas → mécanisme de bascule des entrées publiques à revoir (proposition : nginx VM d'abord, DNS ensuite, en une intervention du titulaire). |
| 02/10 16h | **Décision 10** : bascule des entrées publiques par le nginx de la VM pendant la vague, DNS en une seule fois à la fin (titulaire Gandi) ; LB / certificats / TTL reportés ; jeton Gandi à supprimer. |
| 05/10 | V2-a1 : comparaison-texte P1 ✅ (14:41). Bascule suspendue à la demande du user le temps de structurer la vague 2 **par lot, comme la vague 1** : procédure commune [`procedure-bascule-route-http.md`](procedure-bascule-route-http.md), fiches `lots/V2-a1` → `V2-d`, tableaux « État des lots » et « État des services » (§ 0, 0bis). |
| 05/10 15:15 | **Première route basculée** : `SERVICE_COMPARAISON_TEXTE` → Cloud Run. Effective au scan du catalogue de 15:23:33 et non à l'écriture : `api-catalog` ne détecte pas l'écriture de `.env.url` (fichier monté seul) et le relit toutes les 15 min → délai réel ≤ 15 min, rollback compris ; mode `rescan` ajouté au script (redémarrage d'`api-catalog`, la gateway garde sa table pendant ce temps). |
| 05/10 15:40 | **Journaux Cloud Run : présents.** Le constat « journaux absents » du 01/10 était un artefact de `gcloud.cmd` sous Git Bash (filtres `gcloud logging read` mal transmis) ; `gcloud run services logs read` montre requêtes et sortie applicative, notre `GET` via la gateway de 12:32:54 UTC y figure (preuve de destination côté Cloud Run). Aucune exclusion FinOps sur Cloud Run. Procédure d'accès des devs ajoutée au guide `acces-logs-services-migres.md` (section Vague 2). |
| 05/10 17h | V2-a1 comparaison-texte : relevé 17h propre (gateway `200` seulement, jumeau VM sans requête, Cloud Run 0 erreur) ; test du dev en cours. V2-a2 : P0 fait (0 appel via la gateway en 7 j sur les 5 routes ; chat-llm = changement de modèle DeepSeek `prod` jamais déployé sur la VM → décision dev) ; questions envoyées au LEAD. |
| 06/10 matin | Réponses devs V2-a2 : pas d'appel direct, usage ponctuel. chat-llm : la VM tourne avec `deepseek-chat`, **retiré par DeepSeek le 24/07** (message du commit `f375968e`) → **option A** retenue : bascule avec `deepseek-v4-flash`. IAM : `monitoring.viewer` posé aux 13 comptes devs (onglet Métriques Cloud Run), 13/13. |
| 06/10 matin | V2-a1 : comparaison-texte **validé** (OK dev) + résumé de chaque comparaison dans les logs (PR DSO mergée, révision `00009-n8z`, vérifié) ; **optimize basculé** 09:30 (`rescan`, preuve OK) ; **detection-langue basculé** 11:18 (référence VM : 20 % de `503`, saturation du jumeau). Catalogue : `failed=1` intermittent = **deadlock MySQL** (`Error 1213`, `internal/repository/endpoint_repo.go:23`) entre scans concurrents — la mise à jour de l'URL (table des services) passe avant l'écriture des endpoints, la route n'est pas affectée ; à remonter aux devs (retry sur 1213 ou concurrence réduite). Crawler : appelle detection-langue et content-extractor en direct (`docker-compose.yml:1410-1411`) → repointage à proposer au dev du crawler après mesure du volume. |
| 06/10 après-midi | V2-a2 prêt (wrappers en entrée interne mergés, `min_instances` 0 ; correctif Rust : Dockerfile sans `Cargo.lock` → copié ; vérifié : internet 404, VM 200). Relevés de midi et 17h : detection `503` à ~1 % (20-60 % sur la VM) ; les `503` de la gateway sont surtout des **abandons de l'appelant** (extractor : Cloud Run a servi `200`) ; classification appelle optimize en direct ; 2 erreurs d'encodage detection = défaut du code (`language_detector.py:482`). Incident doc : `lots/V2-a1.md` vidé par un script, reconstruit ; écritures désormais atomiques. |
| 07/10 matin | J+1 V2-a1 : GO technique (nuit propre). V2-a2 : 5/5 routes basculées (embedding, graph-rag ×3 à 09:27, chat-llm à 09:38), preuves OK. `revert` corrigé (reprenait la dernière sauvegarde, sans effet sur une route basculée plus tôt). Tests devs en retard (projet urgent) → **test de parité DSO** VM ↔ Cloud Run : comparaison, detection, embedding **identiques**, chat-llm `OK` des deux côtés (`deepseek-chat` répond encore : correction de l'affirmation du 06/10) → **V2-a1 et V2-a2 validés DSO** ; **feu vert crawler**. P0 V2-a3 : recherche (4,8-6,8 k appels/jour, Redis manquant), ingestion sur broker **dev**, prix-traitement à rapatrier. |
| 07/10 11:54 | **Rollback detection-langue** : modèle fastText absent de l'image (monté depuis l'hôte sur la VM) → NLP sauté sur Cloud Run, décisions moins sûres écrites dans le cache partagé ; parité detection du matin faussée par ce cache. Route revenue sur la VM ; correctif image en cours. V2-a3 : wrappers mergés (accès `cloudrun-services` au secret de tracking ajouté), déploiement vérifié (404 / 200). Crawler : option B validée par le user, avec contrôle préalable de l'état git de la VM (son `docker-compose.yml` diffère de `origin/features/poc` connu : 35 lignes). |
| 07/10 12:31 | Correctif image detection (modèle fastText intégré, sha256 figé) déployé (`00006-gq8`), parité **directe et sans cache** identique (`nlp_confirmed` calculé par Cloud Run) → **detection rebasculée** sur Cloud Run (preuve : jumeau 0). Test de parité corrigé : appel direct `run.app`, jamais via la gateway. |
| 07/10 14:10 | **7 services nouveaux sur la VM** (`features/poc`, absents de `prod`) : mcp-hellodata, mcp-normalize-unite, unit-registry, mcp-template-neo4j, agent-service, neo4j_new, tailscale. **Décisions user** : plan de migration du tableau « Nouveaux services » **validé** ; rapatriement `poc` → `prod` **par lot, avec les bibliothèques et dépendances** du dépôt (hellodata avant V2-b, template-neo4j avant V2-c) ; **Tailscale : option A** (identifier propriétaire et usage, lire les ACL du tailnet, puis restreindre ; à défaut d'usage justifié, arrêt du conteneur) — F-HP-SEC-032. Inventaire réel de `mcp_servers` relevé (15 serveurs, 2 nouveaux). |
| 07/10 14:30 | **Mise au point équipe** : unit-registry, neo4j_new, tailscale, mcp-template-neo4j **restent sur la VM** (services temporaires ; code rapatrié dans `prod`) ; mcp-hellodata et mcp-normalize-unite suivent le plan standard ; agent-service appelé par le BO (Ecritel) via `api.hellopro.eu/agent-service/…` → migration à décider ; tailscale = liaison VPN avec le VPS OVH d'OpenClaw. |
