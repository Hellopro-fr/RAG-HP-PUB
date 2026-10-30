# Lot V2-c — Bloc gateway B1 + B3 (ex-L7)

> **Vague 2 · lot 5/6** · risque **Fort** · **une journée dédiée, semaine du 12/10** (pas un vendredi).
> Procédure commune : [`../procedure-bascule-route-http.md`](../procedure-bascule-route-http.md) pour les routes ; ce lot a en plus ses gestes propres (ci-dessous) · plan : [`../plan-vague-2.md`](../plan-vague-2.md) § 3 V2-c et § 1bis · suivi : [`../suivi-vague-2.md`](../suivi-vague-2.md).
> Reprend l'ancien lot [`L7.md`](L7.md) (non joué le 25/09 : ces services basculent **avec leur trafic**). Priorités **P2 / P3** de l'[inventaire](../inventaire-services-migration-par-lot.md).

> **Mise à jour du 15/10 (décisions user + équipe)** : jour J = **lundi 19/10** ; **image-comparison-service non migré** ; **services dépendant des MySQL de la VM non migrés pour l'instant** (mcp-gateway-service → `gateway_db`, mcp-zoho-service) ; **services à fort risque de casser les flux** (api-gateway-go, gestionnaires DLQ) : **analyse préalable validée avant toute bascule**. Drift `poc` → `prod` (15/10) : seul mcp-gateway (+ frontend) a du code à rapatrier — exclu pour l'instant.

> **Décision du 15/10 : option B validée** — pas de bascule V2-c le 19/10 ; tous les services du lot restent sur la VM. Les shadows GKE inactifs de ces services seront réduits à 0 réplica après mesure de leurs ressources.

## Analyse de risque du 15/10 (validée : option B)

> Relevés en lecture seule du 15/10 (`data/cutover/`) : `v2c-perimetre-1015-0935.log`, `v2c-appelants-1015-0943.log`, `v2c-gw-graphadmin-1015-0955.log`, `secu-sources-graph-1015-1054.log`.

| Service | Ce que montrent les relevés | Risque pour les flux | Gain | Proposition |
|---|---|---|---|---|
| `api-gateway-go-service` | **2 connexions MySQL `:3307`** (`gateway_db`) ; arrêt au démarrage sans la base ; porte toutes les routes | très fort | — | **hors lot** (MySQL VM, décision équipe) |
| `mcp-gateway-service` + frontend | **5 connexions MySQL `:3307`** | fort | — | **hors lot** (MySQL VM) |
| `mcp-zoho-service` | **1 connexion MySQL `:3307`** ; aucun appel direct en 7 j | moyen | — | **hors lot** (MySQL VM) |
| `mcp-google-templates-runner` | aucun trafic hors contrôle de santé ; tire ses instances de mcp-gateway ; comptes Google déchiffrés sur un seul hôte | lié à mcp-gateway | — | **suit mcp-gateway** |
| `image-comparison-service` | — | — | — | **hors lot** (décision équipe) |
| `graph-rag-api-admin-service` | **client unique : Ecritel `213.182.35.29`** via `api.hellopro.eu` : ~2 800 lectures `batch/get` / jour (08h et 14h UTC), écritures `admin/cypher` (10 / jour à 18h, ~900 le dimanche à 02h) ; dépend de Neo4j `10.0.1.218` et de 4 serveurs gRPC **de la VM** (enabler 15052 / 15055 / 15056 / 15057) | **fort** : écrit dans Neo4j ; sur GKE, chaque appel ferait VM → GKE → VM (gRPC) ; Service interne à créer | **aucun** : la VM et ses serveurs gRPC restent | **ne migre pas le 19/10** ; suit ses serveurs gRPC |
| `graph-rag-dlq-manager` | **aucun usage réel en 7 j** (scans du catalogue) ; historique depuis mars : 54 `requeue`, 31 lectures ; RabbitMQ prod `10.0.1.216` ; shadow GKE branché sur le broker **DEV** | faible | quasi nul : un conteneur inactif de moins sur la VM ; il faut **exposer** le shadow à la VM (Service interne ou `NodePort`) | **option A** ci-dessous |

**Option A — jouer le 19/10 avec `graph-rag-dlq-manager` seul.** Gestes : secret broker prod, Service interne pour la route `SERVICE_GRAPHDLQ`, bascule de la route, jumeau VM en réserve. Risque faible, gain quasi nul ; une nouvelle exposition interne et, avec un Service `LoadBalancer` interne, une règle de transfert facturée (de l'ordre de 18 $ / mois) : **contraire à l'objectif de coût**.

**Option B (recommandée) — pas de bascule V2-c le 19/10.** Tous les services du lot sont soit hors lot par décision (MySQL VM, image-comparison), soit sans gain (graph-rag-api-admin, graph-rag-dlq-manager). La journée du 19/10 sert à un lot qui réduit les coûts ou le risque : **V2-a3-bis** (recherche : identifier et corriger le lot de nuit) ou les **correctifs sécurité post-migration** (F-HP-SEC-035 : politique par route et gateway fermée par défaut ; F-HP-SEC-032 : ACL du tailnet). En parallèle : **réduire à 0 réplica les shadows GKE inactifs** des services hors lot (api-gateway-go, mcp-gateway, mcp-zoho, templates-runner, graph-rag-api-admin, dlq-manager-service), après mesure de leurs ressources réservées (registre § 4, « shadows GKE B1 / B3 »).

## Composition

| Service (nom `docker-compose`) | Cible (nom exact) | Aiguillage | Jumeau VM après bascule |
|---|---|---|---|
| `api-gateway-go-service` | GKE `api-gateway-go` | **vhost nginx VM `api.hellopro.eu`** → IP interne du Service GKE (décision 10) | **arrêté dans le même geste** (écrit seul au démarrage) |
| `mcp-gateway-service` | GKE `mcp-gateway-service` | **vhost nginx VM `mcp.hellopro.eu`** → IP interne GKE | **arrêté dans le même geste** (contrôle de santé toutes les 30 s, alertes Slack) |
| `mcp-zoho-service` | GKE `mcp-zoho-service` | ligne `mcp_servers` | arrêté |
| `mcp-google-templates-runner` | GKE `mcp-google-templates-runner` | URL côté `mcp-gateway` | arrêté |
| `graph-rag-api-admin-service` | GKE `graph-rag-api-admin-service` | route `SERVICE_GRAPHADMIN` | après observation |
| `graph-rag-dlq-manager-service` | GKE `graph-rag-dlq-manager` (sans `-service`) | route `SERVICE_GRAPHDLQ` | après observation |
| `image-comparison-service` | Cloud Run `image-comparison-service` | route `SERVICE_IMAGE_COMPARATOR` (aujourd'hui `reverse-proxy:8050/comparator`) | après observation |

**Hors lot** : `dlq-manager-service` **reste sur la VM** (décision 5, UP, restreint aux IP Hellopro) ; `api-catalog-service` reste sur la VM (la gateway GKE le joint par l'enabler).

## Ce qui bascule dans ce lot

- `api.hellopro.eu` et `mcp.hellopro.eu` : le **nginx de la VM** envoie vers GKE au lieu des conteneurs locaux (décision 10 : DNS inchangé pendant la vague).
- `gateway_db` (MySQL VM) devient la base d'une gateway **qui tourne sur GKE** (enabler `10.11.0.2:3307`) : migration de schéma au démarrage (`AutoMigrate`), jetons système.

## À savoir, service par service

Analyse de code complète du 25/09 : [`L7.md`](L7.md), section « Analyse du code (25/09) ».

| Service | Vigilance |
|---|---|
| `api-gateway-go` | `AutoMigrate` de 3 tables + INSERT de jetons au démarrage. Carte de services issue de `.env.url` (fichier local VM) → ConfigMap. `JWT_SECRET` identique. Défauts Docker à poser (`MYSQL_*`, `API_CATALOG_GRPC`, `ACCOUNT_BASE_URL`). |
| `mcp-gateway-service` | `AutoMigrate` de 36 tables ; contrôle de santé → `UPDATE mcp_servers` + Slack ; `MCP_GATEWAY_PORT=8592` ; `ENCRYPTION_KEY` partagée ; icônes sur le disque VM → stockage cible ; **pas de Service K8s** à ce jour. `account-service-backend` (VM) l'appelle → le repointer **avant** d'arrêter le jumeau. Commit `poc` seul du 30/09 → rapatriement. |
| `mcp-zoho-service` | Pas de Service K8s ; dépend de MySQL au démarrage. |
| `mcp-google-templates-runner` | Reçoit les comptes de service Google déchiffrés : un seul hôte à la fois. |
| `graph-rag-api-admin` | Écrit dans Neo4j sur appel : instantané Neo4j la veille. |
| `graph-rag-dlq-manager` | Endpoints sans authentification (F-HP-SEC-027) : jamais exposés hors cluster. |
| `image-comparison-service` | ⚠️ **Compteur Redis partagé** `comparator:running_count` à isoler, sinon collision avec la VM ; passe aujourd'hui par le `reverse-proxy` (sidecar nginx à prévoir). |

## Prérequis spécifiques au lot

- c.1 Version du code gateway VM = image GKE (le LEAD confirme) ; parité par empreinte de `ENCRYPTION_KEY`, `JWT_SECRET`, `GATEWAY_ADMIN_KEY`, `GOOGLE_TEMPLATES_RUNNER_ADMIN_TOKEN`, `ZOHO_GATEWAY_TOKEN`.
- c.2 Services K8s manquants, Service **interne** (IP `10.0.1.x`) pour `api.` et `mcp.`, ConfigMap `.env.url`, icônes, sidecar `/comparator` `/crawler`, défauts Docker posés.
- **0.22 Script de bascule nginx** d'un vhost (sauvegarde, `nginx -t`, `reload`, contrôle, retour arrière) : à écrire.
- Dump complet de `gateway_db` le matin (c.3), instantané Neo4j la veille.

## Ce qu'on attend du LEAD et des devs concernés

- LEAD : confirmation écrite de la version du code gateway (c.1).
- Devs gateway et MCP : parcours réels sur `api.hellopro.eu` et `mcp.hellopro.eu` après la bascule (c.7).

## Feuille de lot

| Étape | Heure | Résultat | Par |
|---|---|---|---|
| c.1 Parité version + jetons | | | DSO · LEAD |
| c.2 Manifestes (`kubectl diff` relu), pods prêts en shadow | | | DSO |
| Script nginx (0.22) prêt et relu | | | DSO |
| c.3 Dump `gateway_db` (taille vérifiée) | | | DSO |
| c.4 mcp-gateway, zoho, templates-runner, api-gateway-go sur la prod ; jumeaux arrêtés | | | DSO |
| c.5 vhosts nginx `api.` et `mcp.` → GKE | | | DSO |
| c.6 routes graph-rag admin / dlq, comparateur d'images | | | DSO |
| c.7 Tests fonctionnels gateway et MCP | | | devs |
| Relevé 17h / nuit | | | DSO |
| **Décision J+1 9h30** (rollback prêt : vhosts remis, `docker start` des jumeaux, dump si le schéma a divergé) | | | LEAD · DSO |
